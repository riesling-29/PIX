"""Loss-explicit reader for PM4Py's classic three-table OCEL SQLite dialect.

This compatibility dialect is not the OCEL 2 SQLite serialization. Its physical
contract was checked against PM4Py commit 3329bbcbadce8764f7df660fd88636c30793fbd0,
``objects/ocel/{importer,exporter}/sqlite/variants/pandas_*`` and the accompanying
``tests/input_data/ocel/example_log.sqlite`` schema. No PM4Py code is imported.
"""

from __future__ import annotations

import math
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    ValueEncoding,
    _map_time,
    _MappingContext,
    _require_nonblank_text,
    map_document,
    mapping_failure,
    schema_failure,
    syntax_failure,
)
from pix.ocel.model import OCEL_EPOCH

_FIXED = {
    "EVENTS": {"ocel:eid", "ocel:activity", "ocel:timestamp"},
    "OBJECTS": {"ocel:oid", "ocel:type"},
    "RELATIONS": {
        "ocel:eid",
        "ocel:activity",
        "ocel:timestamp",
        "ocel:oid",
        "ocel:type",
    },
}


_SQLITE_CASE = str.maketrans("abcdefghijklmnopqrstuvwxyz", "ABCDEFGHIJKLMNOPQRSTUVWXYZ")


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Read a closed, standalone classic SQLite export without modifying it."""
    connection: sqlite3.Connection | None = None
    try:
        _require_standalone_database(path)
        connection = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("BEGIN")
        document, transformations = _read_document(connection)
    except (sqlite3.DatabaseError, OSError) as exc:
        raise syntax_failure(
            "invalid_sqlite", f"Invalid or unreadable SQLite database: {exc}."
        ) from exc
    finally:
        if connection is not None:
            connection.close()
    result, mapped = map_document(document, encoding=ValueEncoding.SQLITE)
    return result, tuple(transformations) + mapped


def _require_standalone_database(path: Path) -> None:
    # A read-only WAL connection can still create sidecars, and a hash of the
    # main file cannot identify committed data held in WAL. Do not open it or
    # ignore its journal through immutable=1. See sqlite.org/wal.html, §§4–5.
    resolved = path.resolve()
    with resolved.open("rb") as stream:
        header = stream.read(20)
    if (header.startswith(b"SQLite format 3\x00") and 2 in header[18:20]) or any(
        resolved.with_name(resolved.name + suffix).exists()
        for suffix in ("-wal", "-shm", "-journal")
    ):
        raise schema_failure(
            "unsupported_legacy_sqlite_journal",
            "Classic SQLite import requires a closed standalone rollback-journal "
            "export. WAL-mode databases and journal sidecars are unsupported: "
            "their source evidence cannot be represented by a main-file hash. "
            "Create a separate single-file export before importing.",
        )


def _read_document(
    connection: sqlite3.Connection,
) -> tuple[dict[str, object], list[Transformation]]:
    transformations = [
        Transformation(
            code="legacy_sqlite_migration",
            message=(
                "Migrated the PM4Py classic EVENTS/OBJECTS/RELATIONS compatibility "
                "dialect, not official OCEL 2 SQLite. Source ids and disconnected "
                "entities are retained. No object-object links or change history "
                "are inferred. SQL declarations, constraints, indexes and record "
                "order are not canonical data. Duplicated relation facts are checked "
                "against their referenced records."
            ),
        )
    ]
    catalog = list(
        connection.execute(
            "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    )
    tables: dict[str, str] = {}
    for name, kind, sql in catalog:
        logical = name.translate(_SQLITE_CASE)
        if logical not in _FIXED:
            if not name.startswith("sqlite_"):
                transformations.append(
                    Transformation(
                        code="legacy_sqlite_extra_content_not_preserved",
                        message=f"Extra SQLite {kind} '{name}' is outside the classic dialect and was not read.",
                        at=(name,),
                        count=1,
                    )
                )
            continue
        if logical in tables:
            raise schema_failure(
                "ambiguous_legacy_sqlite_table",
                "Core table names are ambiguous.",
                (name,),
            )
        if (
            kind != "table"
            or not isinstance(sql, str)
            or re.match(r"\s*CREATE\s+VIRTUAL\s+TABLE\b", sql, re.IGNORECASE)
        ):
            raise schema_failure(
                "unsupported_legacy_sqlite_table",
                "Classic OCEL requires ordinary stored tables, not views or virtual tables.",
                (name,),
            )
        tables[logical] = name
    missing = sorted(_FIXED.keys() - tables.keys())
    if missing:
        raise schema_failure(
            "missing_legacy_sqlite_table",
            f"Missing classic OCEL SQLite table(s): {', '.join(missing)}.",
        )

    rows: dict[str, list[dict[str, object]]] = {}
    for logical, physical in tables.items():
        columns = _columns(connection, physical)
        missing_columns = sorted(_FIXED[logical] - set(columns))
        if missing_columns:
            raise schema_failure(
                "missing_legacy_sqlite_column",
                f"Table '{physical}' requires exact column names: {', '.join(missing_columns)}.",
                (physical,),
            )
        rows[logical] = [
            dict(zip(columns, row, strict=True))
            for row in connection.execute(
                f"SELECT {', '.join(_quote(name) for name in columns)} FROM {_quote(physical)}"
            )
        ]
        if logical == "RELATIONS":
            for name in sorted(set(columns) - _FIXED[logical]):
                transformations.append(
                    Transformation(
                        code="legacy_sqlite_extra_content_not_preserved",
                        message=(
                            f"Extra relation column '{name}' is not represented by "
                            "the unqualified classic OCEL relationship model."
                        ),
                        at=(physical, name),
                        count=len(rows[logical]),
                    )
                )
        else:
            for name in sorted(set(columns) - _FIXED[logical]):
                _require_nonblank_text(name, (physical, name))
                null_count = sum(row[name] is None for row in rows[logical])
                if null_count:
                    transformations.append(
                        Transformation(
                            code="legacy_sqlite_null_attributes_omitted",
                            message=(
                                "SQL NULL attribute cells are treated as missing values; "
                                "canonical values have no null representation. An "
                                "all-null attribute has no inferred declaration."
                            ),
                            at=(physical, name),
                            count=null_count,
                        )
                    )

    events, event_types, event_index = _records(rows["EVENTS"], "EVENTS")
    objects, object_types, object_index = _records(rows["OBJECTS"], "OBJECTS")
    _relations(rows["RELATIONS"], event_index, object_index, transformations)
    attr_count = sum(len(record["attributes"]) for record in objects)
    transformations.append(
        Transformation(
            code="legacy_type_inference",
            message=(
                "Inferred per-activity/object-type schemas from stored SQLite TEXT, "
                "INTEGER and finite REAL values. SQL type names do not imply boolean "
                "or time semantics. Mixed types are rejected without numeric widening; "
                "SQLite storage cannot recover types lost before import."
            ),
            count=sum(
                len(record["attributes"]) for record in event_types + object_types
            ),
        )
    )
    if rows["RELATIONS"]:
        transformations.append(
            Transformation(
                code="legacy_empty_qualifier",
                message="Mapped classic event-object links with empty qualifiers; no role is inferred.",
                count=len(rows["RELATIONS"]),
            )
        )
    if attr_count:
        transformations.append(
            Transformation(
                code="legacy_timeless_object_attributes",
                message=(
                    "Mapped timeless object attributes to OCEL_EPOCH "
                    "(1970-01-01T00:00:00Z); this is not an observed change time."
                ),
                count=attr_count,
            )
        )
    return {
        "events": events,
        "objects": objects,
        "eventTypes": event_types,
        "objectTypes": object_types,
    }, transformations


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    rows = list(connection.execute(f"PRAGMA table_xinfo({_quote(table)})"))
    if not rows:
        raise schema_failure(
            "missing_legacy_sqlite_column",
            "Core table has no readable columns.",
            (table,),
        )
    if any(row[6] != 0 for row in rows):
        raise schema_failure(
            "unsupported_legacy_sqlite_column",
            "Generated or hidden core-table columns are not supported.",
            (table,),
        )
    columns = [row[1] for row in rows]
    if len({name.translate(_SQLITE_CASE) for name in columns}) != len(columns):
        raise schema_failure(
            "ambiguous_legacy_sqlite_column", "Column names are ambiguous.", (table,)
        )
    return columns


def _records(
    rows: list[dict[str, object]],
    table: str,
) -> tuple[
    list[dict[str, object]], list[dict[str, object]], dict[str, dict[str, object]]
]:
    is_event = table == "EVENTS"
    id_column = "ocel:eid" if is_event else "ocel:oid"
    type_column = "ocel:activity" if is_event else "ocel:type"
    records: list[dict[str, object]] = []
    index: dict[str, dict[str, object]] = {}
    schemas: dict[str, dict[str, str]] = {}
    for position, row in enumerate(rows):
        at = (table, str(position))
        identifier = _require_nonblank_text(row[id_column], at + (id_column,))
        name = _require_nonblank_text(row[type_column], at + (type_column,))
        if identifier in index:
            raise mapping_failure(
                "duplicate_legacy_sqlite_id",
                "Repeated source id is ambiguous; no row is merged.",
                at + (id_column,),
            )
        schema = schemas.setdefault(name, {})
        attributes: list[dict[str, object]] = []
        for attr, value in row.items():
            if attr in _FIXED[table] or value is None:
                continue
            value_type = _attribute_type(value, at + (attr,))
            previous = schema.get(attr)
            if previous is not None and previous != value_type:
                raise mapping_failure(
                    "legacy_attribute_type_conflict",
                    f"Type '{name}' attribute '{attr}' has both {previous} and {value_type} values.",
                    at + (attr,),
                )
            schema[attr] = value_type
            attribute: dict[str, object] = {"name": attr, "value": value}
            if not is_event:
                attribute["time"] = OCEL_EPOCH.isoformat()
            attributes.append(attribute)
        record: dict[str, object] = {
            "id": identifier,
            "type": name,
            "attributes": attributes,
            "relationships": [],
        }
        if is_event:
            record["time"] = row["ocel:timestamp"]
        records.append(record)
        index[identifier] = record
    declarations: list[dict[str, object]] = [
        {
            "name": name,
            "attributes": [
                {"name": attr, "type": kind} for attr, kind in sorted(schema.items())
            ],
        }
        for name, schema in sorted(schemas.items())
    ]
    return records, declarations, index


def _attribute_type(value: object, at: tuple[str, ...]) -> str:
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float) and math.isfinite(value):
        return "float"
    raise mapping_failure(
        "unsupported_legacy_sqlite_attribute",
        "Classic SQLite attributes must be TEXT, INTEGER or finite REAL values; BLOB is unsupported.",
        at,
    )


def _relations(
    rows: list[dict[str, object]],
    events: dict[str, dict[str, object]],
    objects: dict[str, dict[str, object]],
    transformations: list[Transformation],
) -> None:
    event_times: dict[str, datetime] = {}
    context = _MappingContext(ValueEncoding.SQLITE)
    for position, row in enumerate(rows):
        at = ("RELATIONS", str(position))
        eid = _require_nonblank_text(row["ocel:eid"], at + ("ocel:eid",))
        oid = _require_nonblank_text(row["ocel:oid"], at + ("ocel:oid",))
        event, obj = events.get(eid), objects.get(oid)
        if event is None or obj is None:
            raise mapping_failure(
                "dangling_legacy_sqlite_relation",
                f"Relation references absent event '{eid}' or object '{oid}'; no link is dropped.",
                at,
            )
        for field, expected in (
            ("ocel:activity", event["type"]),
            ("ocel:type", obj["type"]),
        ):
            if row[field] != expected:
                raise mapping_failure(
                    "contradictory_legacy_sqlite_relation",
                    f"Duplicated relation field '{field}' disagrees with its referenced record.",
                    at + (field,),
                )
        if eid not in event_times:
            event_times[eid] = _map_time(
                event["time"],
                ("EVENTS", eid, "ocel:timestamp"),
                _MappingContext(ValueEncoding.SQLITE),
            )
        if (
            _map_time(row["ocel:timestamp"], at + ("ocel:timestamp",), context)
            != event_times[eid]
        ):
            raise mapping_failure(
                "contradictory_legacy_sqlite_relation",
                "Duplicated relation timestamp denotes a different instant from its event.",
                at + ("ocel:timestamp",),
            )
        relationships = event["relationships"]
        assert isinstance(relationships, list)
        relationships.append({"objectId": oid, "qualifier": ""})
    for code, count, message in (
        (
            "timezone_assumed_utc",
            context.assumed_utc_count,
            "Assumed UTC for timezone-less duplicated relation timestamps during consistency checks.",
        ),
        (
            "timezone_to_utc",
            context.timezone_normalization_count,
            "Compared duplicated relation timestamps as UTC instants without changing their times.",
        ),
        (
            "legacy_timestamp_parsed",
            context.legacy_timestamp_count,
            "Parsed duplicated relation timestamps containing legacy explicit numeric UTC offsets.",
        ),
    ):
        if count:
            transformations.append(
                Transformation(
                    code=code,
                    count=count,
                    message=message,
                    at=("RELATIONS", "ocel:timestamp"),
                )
            )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


__all__ = ["load"]
