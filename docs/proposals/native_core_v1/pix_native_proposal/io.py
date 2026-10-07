"""Executable proposal: verified OCEL JSON/SQLite export using PIX's own core.

This module is outside ``src`` and does not change PIX's public API. Profiles
describe the emitted representation; they do not certify an official schema.
Import provenance is not part of OCEL interchange or Canonical V1 identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pix.ocel import (
    OCEL, OCEL_EPOCH, CanonicalDigest, ImportResult, ValueType,
    build, canonical_digest, import_ocel,
)
from pix.ocel.report import Report


@dataclass(frozen=True, slots=True)
class ExportIssue:
    code: str
    message: str
    at: tuple[str, ...] = ()


class ExportError(ValueError):
    """An unsuccessful export with stage-specific, inspectable evidence."""

    def __init__(
        self, code: str, message: str, *, path: str,
        source_canonical_digest: CanonicalDigest | None = None,
        issues: tuple[ExportIssue, ...] = (),
        semantic_report: Report | None = None,
        import_result: ImportResult | None = None,
    ) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.path = path
        self.source_canonical_digest = source_canonical_digest
        self.issues = issues or (ExportIssue(code, message),)
        self.semantic_report = semantic_report
        self.import_result = import_result


@dataclass(frozen=True, slots=True)
class ExportResult:
    """Evidence for a published artifact; ``not_run`` is not a schema pass."""

    path: str
    format: str
    profile: str
    source_canonical_digest: CanonicalDigest
    output_sha256: str
    output_size: int
    roundtrip_canonical_digest: CanonicalDigest
    pix_semantic: Literal["passed"] = field(default="passed", init=False)
    reference_schema: Literal["not_run"] = field(default="not_run", init=False)
    roundtrip: Literal["passed"] = field(default="passed", init=False)

    def __post_init__(self) -> None:
        if self.source_canonical_digest != self.roundtrip_canonical_digest:
            raise ValueError("a successful export requires equal canonical digests")
        if len(self.output_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.output_sha256
        ):
            raise ValueError("output_sha256 must be lowercase SHA-256 hexadecimal")
        if type(self.output_size) is not int or self.output_size < 0:
            raise ValueError("output_size must be a nonnegative integer")


_FORMATS = {
    "json": "ocel20-json", "ocel20-json": "ocel20-json",
    "sqlite": "ocel20-sqlite", "ocel20-sqlite": "ocel20-sqlite",
}
_PROFILES = {
    "ocel20-json": "pix.ocel20-json.native-primitives.v1",
    "ocel20-sqlite": "pix.ocel20-sqlite.typed-columns.v1",
}
_SQL_TYPES = {
    ValueType.STRING: "TEXT", ValueType.TIME: "TIMESTAMP",
    ValueType.INTEGER: "INTEGER", ValueType.FLOAT: "REAL",
    ValueType.BOOLEAN: "BOOLEAN",
}


def export_ocel(
    log: OCEL, path: str | os.PathLike[str], *, format: str,
    overwrite: bool = False,
) -> ExportResult:
    """Validate, serialize, re-import, compare digests, then publish atomically.

    JSON uses native numeric/boolean primitives and UTC ISO timestamps. SQLite
    uses signed int64 and refuses negative zero or ambiguous column names.
    Neither writer changes or drops canonical data to fit its representation.
    Only JSON and SQLite are implemented; gzip and XML fail explicitly.

    The destination directory must already exist. No-overwrite publication is
    race-safe: Windows rename, or a same-directory hardlink on other platforms.
    Filesystems without the needed atomic operation fail, without a copy fallback.
    Atomic visibility is provided; power-loss durability is not claimed.
    """
    if not isinstance(log, OCEL):
        raise TypeError("log must be pix.ocel.OCEL")
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    source_path = os.fspath(path)
    if not isinstance(source_path, str) or not source_path.strip():
        raise TypeError("path must be a nonempty string path")
    # Avoid resolve(): an existing destination symlink must not redirect writes.
    destination = Path(os.path.abspath(source_path))
    path_text = str(destination)
    selected = _FORMATS.get(format) if isinstance(format, str) else None
    if selected is None:
        raise ExportError(
            "unsupported_format", "This proposal implements only JSON and SQLite.",
            path=path_text,
        )
    if destination.suffix.lower() == ".gz":
        raise ExportError(
            "unsupported_encoding", "Gzip output is not implemented.", path=path_text,
        )

    try:
        built = build(
            event_types=log.event_types, object_types=log.object_types,
            events=log.events, objects=log.objects, e2o=log.e2o, o2o=log.o2o,
        )
    except (ValueError, TypeError, OverflowError) as exc:
        raise ExportError(
            "normalization_failed", str(exc), path=path_text,
        ) from exc
    if not built.valid:
        raise ExportError(
            "semantic_invalid", "Source OCEL failed PIX semantic validation.",
            path=path_text, semantic_report=built.report,
            issues=tuple(ExportIssue(i.code, i.message, i.at) for i in built.report.issues),
        )
    normalized = built.candidate
    try:
        digest = canonical_digest(normalized)
    except (ValueError, OverflowError) as exc:
        raise ExportError(
            "canonicalization_failed", str(exc), path=path_text,
            semantic_report=built.report,
        ) from exc
    if selected == "ocel20-sqlite":
        issues = _sqlite_preflight(normalized)
        if issues:
            raise ExportError(
                "unrepresentable", "SQLite cannot preserve the supplied OCEL exactly.",
                path=path_text, source_canonical_digest=digest, issues=issues,
            )
    # This is only an early diagnostic. Publication also enforces no-overwrite.
    if not overwrite and os.path.lexists(destination):
        raise ExportError(
            "destination_exists", "Destination exists; overwrite was not requested.",
            path=path_text, source_canonical_digest=digest,
        )

    stage: Path | None = None
    phase = "serialize"
    try:
        suffix = ".jsonocel" if selected == "ocel20-json" else ".sqlite"
        descriptor, temporary = tempfile.mkstemp(
            prefix=".pix-export-", suffix=suffix, dir=destination.parent,
        )
        stage = Path(temporary)
        os.close(descriptor)
        if selected == "ocel20-json":
            _write_json(normalized, stage)
        else:
            _write_sqlite(normalized, stage)
        with stage.open("rb") as stream:
            output_sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
            output_size = os.fstat(stream.fileno()).st_size

        phase = "roundtrip"
        imported = import_ocel(stage, format=selected)
        if not imported.valid or imported.canonical_digest != digest:
            raise ExportError(
                "roundtrip_failed", "Serialized artifact did not preserve canonical identity.",
                path=path_text, source_canonical_digest=digest, import_result=imported,
            )
        result = ExportResult(
            path=path_text, format=selected, profile=_PROFILES[selected],
            source_canonical_digest=digest, output_sha256=output_sha256,
            output_size=output_size, roundtrip_canonical_digest=imported.canonical_digest,
        )
        phase = "publish"
        if overwrite:
            os.replace(stage, destination)
            stage = None
        elif os.name == "nt":
            os.rename(stage, destination)  # Windows rename fails if destination exists.
            stage = None
        else:
            os.link(stage, destination)  # Atomic create-if-absent; no overwrite race.
        return result
    except ExportError:
        raise
    except (OSError, sqlite3.Error, ValueError, OverflowError) as exc:
        code = "destination_exists" if isinstance(exc, FileExistsError) else f"{phase}_failed"
        raise ExportError(
            code, str(exc), path=path_text, source_canonical_digest=digest,
        ) from exc
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)  # Never unlink the requested destination.


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _value(value: object) -> object:
    return _time(value) if isinstance(value, datetime) else value


def _write_json(log: OCEL, path: Path) -> None:
    e2o: dict[str, list[dict[str, str]]] = {}
    o2o: dict[str, list[dict[str, str]]] = {}
    for rel in log.e2o:
        e2o.setdefault(rel.event, []).append({"objectId": rel.object, "qualifier": rel.qualifier})
    for rel in log.o2o:
        o2o.setdefault(rel.source, []).append({"objectId": rel.target, "qualifier": rel.qualifier})
    document = {
        "eventTypes": [
            {"name": typ.name, "attributes": [{"name": a.name, "type": a.type.value} for a in typ.attributes]}
            for typ in log.event_types
        ],
        "objectTypes": [
            {"name": typ.name, "attributes": [{"name": a.name, "type": a.type.value} for a in typ.attributes]}
            for typ in log.object_types
        ],
        "events": [
            {"id": e.id, "type": e.type, "time": _time(e.time),
             "attributes": [{"name": a.name, "value": _value(a.value)} for a in e.attributes],
             "relationships": e2o.get(e.id, [])}
            for e in log.events
        ],
        "objects": [
            {"id": obj.id, "type": obj.type,
             "attributes": [{"name": a.name, "value": _value(a.value), "time": _time(a.time)} for a in obj.attributes],
             "relationships": o2o.get(obj.id, [])}
            for obj in log.objects
        ],
    }
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(document, stream, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _sqlite_fold(name: str) -> str:
    # SQLite identifier case-insensitivity is ASCII, not Unicode casefold.
    return name.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))


def _sqlite_preflight(log: OCEL) -> tuple[ExportIssue, ...]:
    issues: list[ExportIssue] = []
    for kind, declarations in (("event", log.event_types), ("object", log.object_types)):
        reserved = {"ocel_id", "ocel_time"}
        if kind == "object":
            reserved.add("ocel_changed_field")
        for typ in declarations:
            seen = set(reserved)
            for attr in typ.attributes:
                folded = _sqlite_fold(attr.name)
                if "\x00" in attr.name or folded in seen:
                    issues.append(ExportIssue(
                        "sqlite_column_collision", "Attribute is reserved, duplicated ignoring ASCII case, or contains NUL.",
                        (kind, typ.name, attr.name),
                    ))
                seen.add(folded)
    for kind, entities in (("event", log.events), ("object", log.objects)):
        for entity in entities:
            for attr in entity.attributes:
                value = attr.value
                if type(value) is int and not -(2**63) <= value < 2**63:
                    issues.append(ExportIssue("sqlite_int64_range", "Integer exceeds signed int64 range.", (kind, entity.id, attr.name)))
                if isinstance(value, float) and value == 0 and math.copysign(1.0, value) < 0:
                    issues.append(ExportIssue("sqlite_negative_zero", "REAL storage does not preserve negative zero.", (kind, entity.id, attr.name)))
    return tuple(issues)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _insert(connection: sqlite3.Connection, table: str, row: dict[str, object]) -> None:
    columns = ", ".join(_quote(name) for name in row)
    placeholders = ", ".join("?" for _ in row)
    connection.execute(
        f"INSERT INTO {_quote(table)} ({columns}) VALUES ({placeholders})",
        tuple(_value(value) for value in row.values()),
    )


def _write_sqlite(log: OCEL, path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.executescript('''
                CREATE TABLE event (ocel_id TEXT PRIMARY KEY, ocel_type TEXT NOT NULL);
                CREATE TABLE object (ocel_id TEXT PRIMARY KEY, ocel_type TEXT NOT NULL);
                CREATE TABLE event_map_type (ocel_type TEXT PRIMARY KEY, ocel_type_map TEXT UNIQUE NOT NULL);
                CREATE TABLE object_map_type (ocel_type TEXT PRIMARY KEY, ocel_type_map TEXT UNIQUE NOT NULL);
                CREATE TABLE event_object (
                    ocel_event_id TEXT NOT NULL, ocel_object_id TEXT NOT NULL, ocel_qualifier TEXT NOT NULL,
                    PRIMARY KEY (ocel_event_id, ocel_object_id, ocel_qualifier));
                CREATE TABLE object_object (
                    ocel_source_id TEXT NOT NULL, ocel_target_id TEXT NOT NULL, ocel_qualifier TEXT NOT NULL,
                    PRIMARY KEY (ocel_source_id, ocel_target_id, ocel_qualifier));
            ''')
            mappings: dict[tuple[str, str], str] = {}
            for kind, declarations in (("event", log.event_types), ("object", log.object_types)):
                for index, typ in enumerate(declarations):
                    # Canonically sorted type declarations yield deterministic,
                    # collision-free names even for 'A', 'a', or 'map_type'.
                    physical = f"t{index:08d}"
                    mappings[kind, typ.name] = f"{kind}_{physical}"
                    _insert(connection, f"{kind}_map_type", {"ocel_type": typ.name, "ocel_type_map": physical})
                    fixed = ["ocel_id TEXT NOT NULL", "ocel_time TIMESTAMP NOT NULL"]
                    fixed.append("ocel_changed_field TEXT" if kind == "object" else "PRIMARY KEY (ocel_id)")
                    columns = [f"{_quote(a.name)} {_SQL_TYPES[a.type]}" for a in typ.attributes]
                    # Table constraints must follow all column declarations.
                    definitions = fixed[:2] + columns + fixed[2:]
                    connection.execute(f"CREATE TABLE {_quote(mappings[kind, typ.name])} ({', '.join(definitions)})")
            for event in log.events:
                _insert(connection, "event", {"ocel_id": event.id, "ocel_type": event.type})
                row = {"ocel_id": event.id, "ocel_time": _time(event.time)}
                row.update({a.name: a.value for a in event.attributes})
                _insert(connection, mappings["event", event.type], row)
            for obj in log.objects:
                _insert(connection, "object", {"ocel_id": obj.id, "ocel_type": obj.type})
                table = mappings["object", obj.type]
                baseline = {"ocel_id": obj.id, "ocel_time": _time(OCEL_EPOCH), "ocel_changed_field": None}
                baseline.update({a.name: a.value for a in obj.attributes if a.time == OCEL_EPOCH})
                # An empty baseline represents the entity, not a fabricated value.
                _insert(connection, table, baseline)
                for attr in obj.attributes:
                    if attr.time != OCEL_EPOCH:
                        _insert(connection, table, {"ocel_id": obj.id, "ocel_time": _time(attr.time),
                                                   "ocel_changed_field": attr.name, attr.name: attr.value})
            for rel in log.e2o:
                _insert(connection, "event_object", {"ocel_event_id": rel.event, "ocel_object_id": rel.object, "ocel_qualifier": rel.qualifier})
            for rel in log.o2o:
                _insert(connection, "object_object", {"ocel_source_id": rel.source, "ocel_target_id": rel.target, "ocel_qualifier": rel.qualifier})
    finally:
        connection.close()


__all__ = ["ExportError", "ExportIssue", "ExportResult", "export_ocel"]
