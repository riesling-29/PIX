"""OCEL 2.1 bundled CSV/Parquet adapter (bundle format 1.0).

Metadata is authoritative; no type names are reconstructed from filenames.
ZIP archives are read in place and directory imports never follow symlinks.
Schema profile: official OCEL 2.1.0pre4 PDF (2026-08-24), printed pp.52-55,
SHA-256 b4fa1e9bcbc2c99b8c2f1aea4cb708fccb5e635070fd3474e07997f071e3b42e.
"""

from __future__ import annotations

import json
import zipfile
import zlib
from pathlib import Path
from typing import Any

from pix.ocel.build import BuildResult, build
from pix.ocel.ingest.contract import ImportStage, ImportStatus, Transformation
from pix.ocel.ingest.formats._bundle_source import (
    BundleSource,
    safe_name,
    source_evidence,
)
from pix.ocel.ingest.formats._bundle_tables import (
    csv_rows,
    parquet_modules,
    parquet_rows,
)
from pix.ocel.ingest.formats.common import (
    AdapterFailure,
    ValueEncoding,
    _map_types,
    _MappingContext,
    _require_keys,
    _require_mapping,
    _require_nonblank_text,
    _require_text,
    mapping_failure,
    schema_failure,
    syntax_failure,
)
from pix.ocel.ingest.formats.json import (
    _parse_integer,
    _reject_nonfinite_number,
    _unique_members,
)
from pix.ocel.model import E2O, O2O, OCEL_EPOCH, Event, EventAttr, Object, ObjectAttr

_EVENT = {"ocel_id": "string", "ocel_time": "time"}
_OBJECT = {"ocel_id": "string"}
_CHANGES = {**_EVENT, "ocel_changed_field": "string"}
_E2O = {
    "ocel_event_id": "string",
    "ocel_object_id": "string",
    "ocel_qualifier": "string",
}
_O2O = {
    "ocel_source_id": "string",
    "ocel_target_id": "string",
    "ocel_qualifier": "string",
}


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Read an archive or directory and retain all canonical entities/relations."""
    try:
        with BundleSource(path) as source:
            return _load(source)
    except AdapterFailure:
        raise
    except (
        OSError,
        EOFError,
        zipfile.BadZipFile,
        zlib.error,
        NotImplementedError,
        RuntimeError,
    ) as exc:
        raise syntax_failure(
            "unreadable_bundle", f"Cannot read bundle: {exc}."
        ) from exc


def _metadata(source: BundleSource) -> dict[str, Any]:
    try:
        value = json.loads(
            source.read("ocel-meta.json").decode("utf-8"),
            object_pairs_hook=_unique_members,
            parse_constant=_reject_nonfinite_number,
            parse_int=_parse_integer,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise syntax_failure(
            "invalid_bundle_metadata", "Metadata must be valid UTF-8 JSON."
        ) from exc
    root = _require_mapping(value, ("ocel-meta.json",))
    keys = {
        "ocelVersion",
        "bundleFormatVersion",
        "storageFormat",
        "eventTypes",
        "objectTypes",
        "relations",
    }
    _require_keys(root, required=keys, allowed=keys, at=("ocel-meta.json",))
    if root["ocelVersion"] != "2.0" or root["bundleFormatVersion"] != "1.0":
        raise AdapterFailure(
            status=ImportStatus.UNSUPPORTED,
            stage=ImportStage.SCHEMA,
            code="unsupported_bundle_version",
            message="Supported bundle versions are OCEL 2.0 / bundle 1.0.",
        )
    if root["storageFormat"] not in ("csv", "parquet"):
        raise AdapterFailure(
            status=ImportStatus.UNSUPPORTED,
            stage=ImportStage.SCHEMA,
            code="unsupported_bundle_storage",
            message="Bundle storage must be csv or parquet.",
        )
    return root


def _declarations(
    meta: dict[str, Any],
    kind: str,
    used: set[str],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    values = _require_mapping(meta[f"{kind}Types"], (f"{kind}Types",))
    declarations = []
    mappings = {}
    for name, raw in values.items():
        at = (f"{kind}Types", name)
        _require_nonblank_text(name, at)
        item = _require_mapping(raw, at)
        required = {"file", "changesFile"} if kind == "object" else {"file"}
        _require_keys(item, required=required, allowed=required | {"attributes"}, at=at)
        for key in required:
            _declare_file(item[key], meta["storageFormat"], used)
        declarations.append({"name": name, "attributes": item.get("attributes", [])})
        mappings[name] = item
    return declarations, mappings


def _declare_file(value: object, storage: str, used: set[str]) -> str:
    name = safe_name(value)
    if name in used:
        raise schema_failure(
            "duplicate_bundle_table",
            "A path is assigned to multiple logical tables.",
            (name,),
        )
    if not name.endswith(f".{storage}"):
        raise schema_failure(
            "mixed_bundle_storage",
            "Table extension differs from declared storage.",
            (name,),
        )
    used.add(name)
    return name


def _load(source: BundleSource) -> tuple[BuildResult, tuple[Transformation, ...]]:
    meta = _metadata(source)
    used = {"ocel-meta.json"}
    event_declarations, event_maps = _declarations(meta, "event", used)
    object_declarations, object_maps = _declarations(meta, "object", used)
    event_types, event_schemas = _map_types(event_declarations, kind="event")
    object_types, object_schemas = _map_types(object_declarations, kind="object")
    relations = _require_mapping(meta["relations"], ("relations",))
    _require_keys(
        relations, required={"e2o", "o2o"}, allowed={"e2o", "o2o"}, at=("relations",)
    )
    for value in relations.values():
        _declare_file(value, meta["storageFormat"], used)
    missing = sorted(used - source.files.keys())
    if missing:
        raise schema_failure(
            "missing_bundle_member", f"Missing declared files: {', '.join(missing)}."
        )
    for schema, fixed in [(s, _EVENT) for s in event_schemas.values()] + [
        (s, _CHANGES) for s in object_schemas.values()
    ]:
        if schema.keys() & fixed.keys():
            raise schema_failure(
                "reserved_bundle_attribute", "Attribute collides with a fixed column."
            )
    if meta["storageFormat"] == "parquet":
        parquet_modules()
    context = _MappingContext(ValueEncoding.JSON)
    blank_attributes = 0

    def table(
        name: str, fixed: dict[str, str], schema: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        nonlocal blank_attributes
        attrs = {key: value.value for key, value in (schema or {}).items()}
        options = {
            "name": name,
            "columns": {**fixed, **attrs},
            "attributes": set(attrs),
        }
        data = source.read(name)
        if meta["storageFormat"] == "csv":
            rows, blanks = csv_rows(data, context=context, **options)
            blank_attributes += blanks
            return rows
        return parquet_rows(data, **options)

    events = []
    for name, item in event_maps.items():
        for index, row in enumerate(table(item["file"], _EVENT, event_schemas[name])):
            identifier = _require_nonblank_text(
                row["ocel_id"], (item["file"], str(index), "ocel_id")
            )
            attributes = tuple(
                EventAttr(attr, row[attr])
                for attr in event_schemas[name]
                if row[attr] is not None
            )
            events.append(Event(identifier, name, row["ocel_time"], attributes))

    objects = []
    for name, item in object_maps.items():
        records = table(item["file"], _OBJECT, object_schemas[name])
        assignments: dict[str, list[ObjectAttr]] = {}
        identifiers: list[str] = []
        for index, row in enumerate(records):
            identifier = _require_nonblank_text(
                row["ocel_id"], (item["file"], str(index), "ocel_id")
            )
            identifiers.append(identifier)
        changes = table(item["changesFile"], _CHANGES, object_schemas[name])
        counts: dict[str, int] = {}
        for identifier in identifiers:
            counts[identifier] = counts.get(identifier, 0) + 1
        for index, row in enumerate(changes):
            at = (item["changesFile"], str(index))
            identifier = _require_nonblank_text(row["ocel_id"], at + ("ocel_id",))
            if counts.get(identifier) != 1:
                raise mapping_failure(
                    "invalid_bundle_change_source",
                    "Object change must reference exactly one object of its declared type.",
                    at,
                )
            changed = row["ocel_changed_field"]
            if changed not in object_schemas[name]:
                raise mapping_failure(
                    "unknown_changed_field",
                    "Change references an undeclared attribute.",
                    at,
                )
            if row["ocel_time"] == OCEL_EPOCH:
                raise mapping_failure(
                    "epoch_bundle_change",
                    "Time-zero assignments belong in the object table.",
                    at,
                )
            if row[changed] is None:
                raise mapping_failure(
                    "missing_bundle_change_value",
                    "A changed attribute must have a value.",
                    at,
                )
            if any(
                row[attr] is not None
                for attr in object_schemas[name]
                if attr != changed
            ):
                raise mapping_failure(
                    "ambiguous_bundle_change",
                    "Change row contains values for unrelated attributes.",
                    at,
                )
            assignments.setdefault(identifier, []).append(
                ObjectAttr(changed, row[changed], row["ocel_time"])
            )
        for identifier, row in zip(identifiers, records):
            initial = tuple(
                ObjectAttr(attr, row[attr], OCEL_EPOCH)
                for attr in object_schemas[name]
                if row[attr] is not None
            )
            objects.append(
                Object(
                    identifier, name, initial + tuple(assignments.get(identifier, []))
                )
            )

    e2o = []
    for index, row in enumerate(table(relations["e2o"], _E2O)):
        at = (relations["e2o"], str(index))
        e2o.append(
            E2O(
                _require_nonblank_text(row["ocel_event_id"], at),
                _require_nonblank_text(row["ocel_object_id"], at),
                _require_text(row["ocel_qualifier"], at),
            )
        )
    o2o = []
    for index, row in enumerate(table(relations["o2o"], _O2O)):
        at = (relations["o2o"], str(index))
        o2o.append(
            O2O(
                _require_nonblank_text(row["ocel_source_id"], at),
                _require_nonblank_text(row["ocel_target_id"], at),
                _require_text(row["ocel_qualifier"], at),
            )
        )
    try:
        result = build(
            event_types=event_types,
            object_types=object_types,
            events=events,
            objects=objects,
            e2o=e2o,
            o2o=o2o,
        )
    except OverflowError as exc:
        raise mapping_failure(
            "normalization_overflow", "Timestamp outside canonical range."
        ) from exc
    transformations = [
        Transformation(
            "bundle_specification_profile",
            "Interpreted OCEL 2.0 / bundle 1.0 using OCEL 2.1.0pre4 (2026-08-24) "
            "PDF pp.52-55; metadata paths/types and normative table columns are authoritative.",
        )
    ]
    if blank_attributes:
        transformations.append(
            Transformation(
                "bundle_csv_empty_attributes_missing",
                "CSV empty attribute cells denote missing values; the format cannot distinguish empty strings.",
                count=blank_attributes,
            )
        )
    ignored = tuple(sorted(source.files.keys() - used))
    if ignored:
        transformations.append(
            Transformation(
                "bundle_unlisted_entries_ignored",
                "Safe entries absent from metadata were ignored.",
                at=ignored,
                count=len(ignored),
            )
        )
    if context.timezone_normalization_count:
        transformations.append(
            Transformation(
                "timezone_to_utc",
                "Represented timezone-aware timestamps in UTC without changing instants.",
                count=context.timezone_normalization_count,
            )
        )
    return result, tuple(transformations)


__all__ = ["load", "source_evidence"]
