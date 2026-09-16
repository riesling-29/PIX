"""Strict OCEL 2.1 compact CSV import into the canonical OCEL 2.0 model.

The OCEL 2.1.0pre4 section 9 ``id,activity,timestamp,ot:<type>,...`` dialect
is used, including backslash escapes for /, #, { and backslash in references.
There is no Python-list or PM4Py compatibility dialect. Both
CRLF and LF record endings are accepted. Empty CSV cells are absent values;
JSON empty strings are values, and JSON null is rejected because canonical V1
cannot represent it. Event inference uses the whole attribute column; object
inference uses object type and attribute name. Timeless declarations use the
OCEL epoch; all timed assignments retain their original instants, including
the first assignment (OCEL 2.1.0pre4 section 9). Tied assignments are rejected.
Text integers use signed64 canonical syntax; text floats use Python's shortest
binary64 ``repr`` as the lexical round-trip policy where pre4 is underspecified.
Native JSON integer/float/boolean primitives retain their identity for inference.
Calendar ISO timestamps with explicit numeric/Z offsets are supported; fractional
hours/minutes are rejected rather than interpreted as fractional seconds.

Reference: https://www.ocel-standard.org/specification/formats/csv/
Normative profile: https://www.ocel-standard.org/2.1/ocel20_specification.pdf
Version 2.1.0pre4, 2026-08-24, SHA-256
b4fa1e9bcbc2c99b8c2f1aea4cb708fccb5e635070fd3474e07997f071e3b42e.
The website summary disagrees on escaping and first-assignment timing;
this importer follows the versioned PDF and does not claim certification.
"""

from __future__ import annotations

import csv
import gzip
import json
import math
import re
import zlib
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    AdapterFailure,
    ValueEncoding,
    _map_time,
    _MappingContext,
    map_document,
    mapping_failure,
    schema_failure,
    syntax_failure,
)
from pix.ocel.model import OCEL_EPOCH

COMPACT_PROFILE = "pix.ocel21-compact-csv.2.1.0pre4.v1"
COMPACT_SPEC_SHA256 = "b4fa1e9bcbc2c99b8c2f1aea4cb708fccb5e635070fd3474e07997f071e3b42e"
_REQUIRED = ("id", "activity", "timestamp")
_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")
_TIME = re.compile(
    r"[0-9]{4}-?[0-9]{2}-?[0-9]{2}[Tt ]"
    r"[0-9]{2}:?[0-9]{2}(?::?[0-9]{2}(?:[.,][0-9]+)?)?"
    r"(?:Z|[+-][0-9]{2}(?::?[0-9]{2})?)\Z"
)


@dataclass
class _Value:
    attribute: dict[str, Any]
    at: tuple[str, ...]


@dataclass
class _Assignment:
    attribute: dict[str, Any]
    time: datetime | None
    at: tuple[str, ...]


@dataclass
class _Context:
    events: list[dict[str, Any]] = field(default_factory=list)
    objects: dict[str, dict[str, Any]] = field(default_factory=dict)
    event_types: dict[str, dict[str, list[_Value]]] = field(default_factory=dict)
    object_types: dict[str, dict[str, list[_Value]]] = field(default_factory=dict)
    assignments: dict[tuple[str, str], list[_Assignment]] = field(default_factory=dict)
    transformations: list[Transformation] = field(default_factory=list)
    stripped_fields: int = 0


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Read compact CSV; expected failures carry syntax/schema/mapping stages."""

    context = _Context()
    try:
        opener = gzip.open if path.name.lower().endswith(".gz") else open
        with opener(path, "rt", encoding="utf-8", newline="") as stream:
            rows = csv.reader(_validate_quotes(stream), strict=True)
            header = next(rows, None)
            if header is None:
                raise schema_failure("missing_compact_header", "CSV requires a header.")
            _validate_header(header)
            for name in header:
                if name.startswith("ot:"):
                    context.object_types[name[3:]] = {}
            for index, row in enumerate(rows, start=2):
                at = ("rows", str(index))
                if len(row) != len(header):
                    raise schema_failure(
                        "compact_row_width",
                        f"Expected {len(header)} cells, received {len(row)}.",
                        at,
                    )
                _read_row(dict(zip(header, row)), context, at)
    except UnicodeDecodeError as exc:
        raise syntax_failure("invalid_utf8", "Compact CSV must use UTF-8.") from exc
    except csv.Error as exc:
        raise syntax_failure("invalid_compact_csv", str(exc)) from exc
    except (OSError, EOFError, zlib.error) as exc:
        raise syntax_failure("unreadable_compact_csv", str(exc)) from exc

    _reconstruct_histories(context)
    event_types = _infer_schemas(context.event_types, "event", context)
    object_types = _infer_schemas(context.object_types, "object", context)
    document = {
        "eventTypes": event_types,
        "objectTypes": object_types,
        "events": context.events,
        "objects": list(context.objects.values()),
    }
    result, transformations = map_document(document, encoding=ValueEncoding.JSON)
    if context.stripped_fields:
        context.transformations.append(
            Transformation(
                code="compact_control_fields_stripped",
                message="Removed surrounding Unicode whitespace from control/reference fields as required by pre4.",
                count=context.stripped_fields,
            )
        )
    profile = Transformation(
        code="compact_csv_profile",
        message=(
            f"Read {COMPACT_PROFILE}; specification SHA-256 {COMPACT_SPEC_SHA256}. "
            "UTF-8 CSV with CRLF/LF records and pre4 reference escapes; event "
            "column/object type scopes; declarations use epoch, timed assignments "
            "retain their instants. JSON null, tied assignments and "
            "fractional-minute clocks are unsupported canonical/profile cases."
        ),
    )
    return result, transformations + tuple(context.transformations) + (profile,)


def _validate_quotes(stream: TextIO) -> Iterator[str]:
    """Reject bare/misplaced quotes that csv.reader(strict=True) accepts."""

    state = "start"
    for line_number, line in enumerate(stream, start=1):
        for position, char in enumerate(line):
            if state == "quoted":
                if char == '"':
                    state = "closed"
                continue
            if char == "\r" and line[position + 1 : position + 2] != "\n":
                raise syntax_failure(
                    "invalid_compact_csv",
                    "Unquoted record endings require CRLF or LF.",
                    ("lines", str(line_number)),
                )
            if char == '"':
                if state == "start":
                    state = "quoted"
                elif state == "closed":
                    state = "quoted"  # A doubled quote inside a quoted field.
                else:
                    raise syntax_failure(
                        "invalid_compact_csv",
                        "Quote inside an unquoted CSV field.",
                        ("lines", str(line_number)),
                    )
            elif char == "," or char in "\r\n":
                state = "start"
            elif state == "closed":
                raise syntax_failure(
                    "invalid_compact_csv",
                    "Text follows a closing CSV quote.",
                    ("lines", str(line_number)),
                )
            else:
                state = "unquoted"
        yield line


def _validate_header(header: list[str]) -> None:
    if len(header) != len(set(header)):
        raise schema_failure("duplicate_compact_header", "CSV headers must be unique.")
    if tuple(header[:3]) != _REQUIRED:
        raise schema_failure(
            "invalid_compact_header", "The first columns must be id,activity,timestamp."
        )
    for name in header:
        if not name.strip() or (name.startswith("ot:") and not name[3:].strip()):
            raise schema_failure(
                "blank_compact_header",
                "Column and object type names must be nonblank.",
                ("header", name),
            )


def _read_row(row: dict[str, str], context: _Context, at: tuple[str, ...]) -> None:
    identifier, activity, timestamp = (_strip(row[name], context) for name in _REQUIRED)
    if activity.casefold() == "o2o" and identifier:
        kind = "o2o"
        if identifier not in context.objects:
            raise mapping_failure(
                "unknown_compact_o2o_source",
                "An O2O source type must be established by an earlier row's reference.",
                at + ("id",),
            )
    elif identifier and activity and timestamp:
        kind = "event"
    elif not identifier and not activity:
        kind = "change" if timestamp else "declaration"
    else:
        raise schema_failure(
            "invalid_compact_row_kind",
            "id/activity/timestamp do not identify a row kind.",
            at,
        )
    time = _parse_time(timestamp, at + ("timestamp",)) if timestamp else None
    extra = {
        key: value
        for key, value in row.items()
        if key not in _REQUIRED and not key.startswith("ot:") and value != ""
    }
    if extra and kind != "event":
        raise schema_failure(
            "compact_attributes_without_event",
            "Event attribute columns may be populated only on event rows.",
            at,
        )
    event: dict[str, Any] | None = None
    if kind == "event":
        event = {
            "id": identifier,
            "type": activity,
            "time": timestamp,
            "attributes": [],
            "relationships": [],
        }
        context.events.append(event)
        schema = context.event_types.setdefault(activity, {})
        for name, value in extra.items():
            attribute = {"name": name, "value": value}
            event["attributes"].append(attribute)
            schema.setdefault(name, []).append(_Value(attribute, at + (name,)))

    for column, cell in row.items():
        if not column.startswith("ot:"):
            continue
        object_type = column[3:]
        context.object_types.setdefault(object_type, {})
        for object_id, qualifier, attributes in _references(
            cell, at + (column,), context
        ):
            ref_at = at + (column, object_id)
            if kind == "declaration" and qualifier is not None:
                raise schema_failure(
                    "compact_qualifier_without_relation",
                    "Object declaration rows forbid qualifiers.",
                    ref_at,
                )
            if kind == "change" and qualifier is not None:
                raise mapping_failure(
                    "compact_qualifier_without_relation",
                    "Canonical V1 cannot preserve a qualifier on an attribute-only row.",
                    ref_at,
                )
            obj = context.objects.setdefault(
                object_id,
                {
                    "id": object_id,
                    "type": object_type,
                    "attributes": [],
                    "relationships": [],
                },
            )
            if obj["type"] != object_type:
                raise mapping_failure(
                    "conflicting_compact_object_type",
                    f"Object '{object_id}' occurs under different object types.",
                    ref_at,
                )
            relationship = {"objectId": object_id, "qualifier": qualifier or ""}
            if kind == "event":
                assert event is not None
                event["relationships"].append(relationship)
            elif kind == "o2o":
                context.objects[identifier]["relationships"].append(relationship)
            if attributes and kind == "o2o" and time is None:
                raise schema_failure(
                    "missing_compact_attribute_time",
                    "O2O target attributes require a timestamp.",
                    ref_at,
                )
            for name, value in attributes.items():
                attr_at = ref_at + (name,)
                if not name.strip():
                    raise mapping_failure(
                        "blank_compact_attribute_name",
                        "Canonical attributes require nonblank names.",
                        attr_at,
                    )
                attribute = {
                    "name": name,
                    "value": value,
                    "time": timestamp or OCEL_EPOCH.isoformat(),
                }
                context.object_types[object_type].setdefault(name, []).append(
                    _Value(attribute, attr_at)
                )
                context.assignments.setdefault((object_id, name), []).append(
                    _Assignment(attribute, time, attr_at)
                )


def _references(
    cell: str,
    at: tuple[str, ...],
    context: _Context,
) -> Iterator[tuple[str, str | None, dict[str, Any]]]:
    if cell == "":
        return

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise schema_failure(
                    "duplicate_compact_json_member",
                    "JSON attribute names must be unique.",
                    at + (key,),
                )
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise syntax_failure(
            "nonfinite_compact_json_number",
            f"'{value}' is not a JSON number.",
            at,
        )

    def integer(value: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise mapping_failure(
                "integer_out_of_range",
                "JSON integer exceeds interpreter conversion limits.",
                at,
            ) from exc

    decoder = json.JSONDecoder(
        object_pairs_hook=unique,
        parse_constant=constant,
        parse_int=integer,
    )
    cursor = 0
    while cursor < len(cell):
        object_id, cursor = _reference_token(cell, cursor, at, context)
        if not object_id.strip():
            raise schema_failure(
                "invalid_compact_object_reference",
                "Object references need a nonblank ID.",
                at,
            )
        qualifier = None
        if cursor < len(cell) and cell[cursor] == "#":
            cursor += 1
            qualifier, cursor = _reference_token(cell, cursor, at, context)
        attributes: dict[str, Any] = {}
        if cursor < len(cell) and cell[cursor] == "{":
            try:
                attributes, cursor = decoder.raw_decode(cell, cursor)
            except AdapterFailure:
                raise
            except (json.JSONDecodeError, RecursionError, ValueError) as exc:
                raise syntax_failure(
                    "invalid_compact_json",
                    f"Invalid reference JSON: {exc}.",
                    at,
                ) from exc
            for name, value in attributes.items():
                if isinstance(value, (dict, list)):
                    raise schema_failure(
                        "nonprimitive_compact_attribute",
                        "JSON attribute values must be primitives.",
                        at + (name,),
                    )
                if value is None:
                    raise mapping_failure(
                        "unsupported_compact_null",
                        "JSON null is a value; canonical V1 cannot preserve it.",
                        at + (name,),
                    )
                if isinstance(value, float) and not math.isfinite(value):
                    raise mapping_failure(
                        "nonfinite_compact_attribute",
                        "JSON number exceeds finite floats.",
                        at + (name,),
                    )
        if cursor < len(cell) and cell[cursor] != "/":
            raise schema_failure(
                "invalid_compact_object_reference",
                "Expected '/' between references; literal /#{ must be backslash-escaped.",
                at,
            )
        yield object_id, qualifier, attributes
        if cursor < len(cell):
            cursor += 1
            if cursor == len(cell):
                raise schema_failure(
                    "invalid_compact_object_reference",
                    "Trailing '/' creates an empty ID.",
                    at,
                )


def _strip(value: str, context: _Context) -> str:
    result = value.strip()
    context.stripped_fields += result != value
    return result


def _reference_token(
    cell: str,
    cursor: int,
    at: tuple[str, ...],
    context: _Context,
) -> tuple[str, int]:
    result = []
    while cursor < len(cell) and cell[cursor] not in "/#{":
        char = cell[cursor]
        cursor += 1
        if char == "\\":
            if cursor == len(cell) or cell[cursor] not in "/#{\\":
                raise schema_failure(
                    "invalid_compact_reference_escape",
                    "Reference backslashes must escape /, #, { or backslash.",
                    at,
                )
            char = cell[cursor]
            cursor += 1
        result.append(char)
    return _strip("".join(result), context), cursor


def _parse_time(value: str, at: tuple[str, ...]) -> datetime:
    if not _TIME.fullmatch(value):
        raise mapping_failure(
            "invalid_compact_timestamp",
            "Expected an ISO 8601 calendar timestamp with an explicit timezone.",
            at,
        )
    return _map_time(value, at, _MappingContext(encoding=ValueEncoding.JSON))


def _reconstruct_histories(context: _Context) -> None:
    bases = 0
    for (object_id, _name), assignments in context.assignments.items():
        # Stable sorting retains row/reference order, but canonical V1 has no
        # ordering field for tied assignments; reject rather than overwrite.
        assignments.sort(key=lambda item: item.time or OCEL_EPOCH)
        previous: datetime | None = None
        for index, assignment in enumerate(assignments):
            effective_time = assignment.time or OCEL_EPOCH
            if index and effective_time == previous:
                raise mapping_failure(
                    "tied_compact_attribute_assignment",
                    "Canonical V1 cannot preserve multiple assignments at one time.",
                    assignment.at,
                )
            previous = effective_time
            if assignment.time is None:
                bases += 1
            context.objects[object_id]["attributes"].append(assignment.attribute)
    if bases:
        context.transformations.append(
            Transformation(
                code="compact_object_attribute_bases",
                message=(
                    f"Represented {bases} timeless declaration assignments at the "
                    "OCEL epoch. All timed assignments retain their row timestamps."
                ),
                count=bases,
            )
        )


def _infer_schemas(
    schemas: dict[str, dict[str, list[_Value]]],
    kind: str,
    context: _Context,
) -> list[dict[str, Any]]:
    result = []
    event_columns: dict[str, list[_Value]] = {}
    if kind == "event":
        for schema in schemas.values():
            for name, entries in schema.items():
                event_columns.setdefault(name, []).extend(entries)
    event_inference = {
        name: _inferred_type(entries) for name, entries in event_columns.items()
    }
    for type_name, schema in schemas.items():
        attributes = []
        for name, entries in schema.items():
            scope = event_columns[name] if kind == "event" else entries
            value_type = (
                event_inference[name] if kind == "event" else _inferred_type(entries)
            )
            for entry in entries:
                entry.attribute["value"] = _convert(
                    entry.attribute["value"], value_type, entry.at
                )
            attributes.append({"name": name, "type": value_type})
            context.transformations.append(
                Transformation(
                    code="compact_attribute_type_inferred",
                    message=f"Inferred {value_type} from all {len(scope)} supplied scope values.",
                    at=(f"{kind}Types", type_name, name),
                    count=len(entries),
                )
            )
        result.append({"name": type_name, "attributes": attributes})
    return result


def _inferred_type(entries: list[_Value]) -> str:
    return next(
        candidate
        for candidate in ("integer", "float", "boolean", "time", "string")
        if all(_accepts(entry.attribute["value"], candidate) for entry in entries)
    )


def _accepts(value: Any, value_type: str) -> bool:
    if value_type == "integer":
        return type(value) is int or _text_integer(value)
    if value_type == "float":
        if type(value) is float:
            return math.isfinite(value)
        if type(value) is int or _text_integer(value):
            try:
                result = float(value)
                return math.isfinite(result) and int(result) == int(value)
            except OverflowError:
                return False
        if not isinstance(value, str) or not _FLOAT.fullmatch(value):
            return False
        # An integer-looking lexeme outside signed64 remains a string, even
        # when binary64 happens to represent that integer exactly.
        if _INTEGER.fullmatch(value):
            return False
        result = float(value)
        return math.isfinite(result) and repr(result) == value
    if value_type == "boolean":
        return (
            type(value) is bool
            or isinstance(value, str)
            and value.casefold() in {"true", "false"}
        )
    if value_type == "time":
        if not isinstance(value, str) or not _TIME.fullmatch(value):
            return False
        # Check calendar ranges without truncating the eventual mapped value.
        try:
            datetime.fromisoformat(
                value[:-1] + "+00:00" if value.endswith("Z") else value
            )
        except ValueError:
            return False
    return True


def _text_integer(value: Any) -> bool:
    if not isinstance(value, str) or not _INTEGER.fullmatch(value):
        return False
    # A lexical length guard avoids Python's integer conversion digit limit.
    if len(value.lstrip("-")) > 19:
        return False
    return -(2**63) <= int(value) < 2**63


def _convert(value: Any, value_type: str, at: tuple[str, ...]) -> Any:
    if value_type == "integer":
        try:
            return int(value)
        except ValueError as exc:
            raise mapping_failure(
                "integer_out_of_range", "Integer conversion limit exceeded.", at
            ) from exc
    if value_type == "float":
        try:
            result = float(value)
        except (ValueError, OverflowError) as exc:
            raise mapping_failure(
                "float_out_of_range", "Cannot represent value as a float.", at
            ) from exc
        if not math.isfinite(result):
            raise mapping_failure("float_out_of_range", "Float must be finite.", at)
        if _accepts(value, "integer") and int(result) != int(value):
            raise mapping_failure(
                "compact_numeric_precision_loss",
                "Type unification would round an integer.",
                at,
            )
        return result
    if value_type == "boolean":
        return value if isinstance(value, bool) else value.casefold() == "true"
    if value_type == "time":
        _parse_time(value, at)
        return value
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


__all__ = ["COMPACT_PROFILE", "COMPACT_SPEC_SHA256", "load"]
