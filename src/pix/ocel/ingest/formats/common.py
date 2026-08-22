"""Shared strict mapping from OCEL 2.0 records to the PIX model."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pix.ocel.build import BuildResult, build
from pix.ocel.ingest.contract import ImportStage, ImportStatus, Transformation
from pix.ocel.model import (
    E2O,
    O2O,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    Value,
    ValueType,
)


class ValueEncoding(str, Enum):
    JSON = "json"
    XML = "xml"
    SQLITE = "sqlite"


class AdapterFailure(ValueError):
    """Expected source failure translated into an ImportResult issue."""

    def __init__(
        self,
        *,
        status: ImportStatus,
        stage: ImportStage,
        code: str,
        message: str,
        at: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.status = status
        self.stage = stage
        self.code = code
        self.at = at


def syntax_failure(
    code: str,
    message: str,
    at: tuple[str, ...] = (),
) -> AdapterFailure:
    return AdapterFailure(
        status=ImportStatus.SYNTAX_INVALID,
        stage=ImportStage.SYNTAX,
        code=code,
        message=message,
        at=at,
    )


def schema_failure(
    code: str,
    message: str,
    at: tuple[str, ...] = (),
) -> AdapterFailure:
    return AdapterFailure(
        status=ImportStatus.SCHEMA_INVALID,
        stage=ImportStage.SCHEMA,
        code=code,
        message=message,
        at=at,
    )


def mapping_failure(
    code: str,
    message: str,
    at: tuple[str, ...] = (),
) -> AdapterFailure:
    return AdapterFailure(
        status=ImportStatus.MAPPING_INVALID,
        stage=ImportStage.MAPPING,
        code=code,
        message=message,
        at=at,
    )


@dataclass(slots=True)
class _MappingContext:
    encoding: ValueEncoding
    timezone_normalization_count: int = 0
    legacy_timestamp_count: int = 0
    assumed_utc_count: int = 0


def map_document(
    document: object,
    *,
    encoding: ValueEncoding,
) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Map one parsed OCEL 2.0 document without repair or record removal."""

    root = _require_mapping(document, ())
    _require_keys(
        root,
        required={"eventTypes", "objectTypes", "events", "objects"},
        allowed={"eventTypes", "objectTypes", "events", "objects"},
        at=(),
    )
    context = _MappingContext(encoding=encoding)

    event_types, event_schemas = _map_types(
        _require_list(root["eventTypes"], ("eventTypes",)),
        kind="event",
    )
    object_types, object_schemas = _map_types(
        _require_list(root["objectTypes"], ("objectTypes",)),
        kind="object",
    )
    events, e2o = _map_events(
        _require_list(root["events"], ("events",)),
        event_schemas,
        context,
    )
    objects, o2o = _map_objects(
        _require_list(root["objects"], ("objects",)),
        object_schemas,
        context,
    )

    result = build(
        event_types=event_types,
        object_types=object_types,
        events=events,
        objects=objects,
        e2o=e2o,
        o2o=o2o,
    )
    transformations: list[Transformation] = []
    if context.timezone_normalization_count:
        transformations.append(
            Transformation(
                code="timezone_to_utc",
                message=(
                    "Represented "
                    f"{context.timezone_normalization_count} timezone-aware "
                    "timestamp values in UTC without changing their instants."
                ),
                count=context.timezone_normalization_count,
            )
        )
    if context.legacy_timestamp_count:
        transformations.append(
            Transformation(
                code="legacy_timestamp_parsed",
                message=(
                    "Parsed "
                    f"{context.legacy_timestamp_count} legacy timestamp values "
                    "that contained explicit numeric UTC offsets."
                ),
                count=context.legacy_timestamp_count,
            )
        )
    if context.assumed_utc_count:
        transformations.append(
            Transformation(
                code="timezone_assumed_utc",
                message=(
                    "Assumed UTC for "
                    f"{context.assumed_utc_count} timestamp values that did not "
                    "contain timezone information."
                ),
                count=context.assumed_utc_count,
            )
        )
    return result, tuple(transformations)


def _map_types(
    values: list[object],
    *,
    kind: str,
) -> tuple[
    tuple[EventType, ...] | tuple[ObjectType, ...],
    dict[str, dict[str, ValueType]],
]:
    declarations: list[EventType] | list[ObjectType] = []
    schemas: dict[str, dict[str, ValueType]] = {}
    root_name = f"{kind}Types"

    for index, raw in enumerate(values):
        at = (root_name, str(index))
        item = _require_mapping(raw, at)
        _require_keys(item, required={"name"}, allowed={"name", "attributes"}, at=at)
        name = _require_nonblank_text(item["name"], at + ("name",))
        raw_attributes = _require_list(item.get("attributes", []), at + ("attributes",))
        attributes: list[Attribute] = []
        schema: dict[str, ValueType] = {}
        for attr_index, raw_attribute in enumerate(raw_attributes):
            attr_at = at + ("attributes", str(attr_index))
            attribute = _require_mapping(raw_attribute, attr_at)
            _require_keys(
                attribute,
                required={"name", "type"},
                allowed={"name", "type"},
                at=attr_at,
            )
            attr_name = _require_nonblank_text(
                attribute["name"], attr_at + ("name",)
            )
            if attr_name in schema:
                raise schema_failure(
                    "duplicate_attribute_declaration",
                    f"{kind.title()} type '{name}' declares attribute "
                    f"'{attr_name}' more than once.",
                    attr_at,
                )
            value_type = _map_value_type(attribute["type"], attr_at + ("type",))
            schema[attr_name] = value_type
            attributes.append(Attribute(attr_name, value_type))

        existing = schemas.get(name)
        if existing is not None and existing != schema:
            raise mapping_failure(
                "ambiguous_type_declaration",
                f"Duplicate {kind} type '{name}' has conflicting schemas.",
                at,
            )
        schemas.setdefault(name, schema)
        declaration = (
            EventType(name, tuple(attributes))
            if kind == "event"
            else ObjectType(name, tuple(attributes))
        )
        declarations.append(declaration)

    return tuple(declarations), schemas


def _map_events(
    values: list[object],
    schemas: dict[str, dict[str, ValueType]],
    context: _MappingContext,
) -> tuple[tuple[Event, ...], tuple[E2O, ...]]:
    events: list[Event] = []
    relations: list[E2O] = []
    for index, raw in enumerate(values):
        at = ("events", str(index))
        item = _require_mapping(raw, at)
        _require_keys(
            item,
            required={"id", "type", "time"},
            allowed={"id", "type", "time", "attributes", "relationships"},
            at=at,
        )
        event_id = _require_nonblank_text(item["id"], at + ("id",))
        event_type = _require_nonblank_text(item["type"], at + ("type",))
        event_time = _map_time(item["time"], at + ("time",), context)
        schema = schemas.get(event_type, {})
        attributes = _map_attributes(
            item.get("attributes", []),
            schema=schema,
            context=context,
            at=at + ("attributes",),
            object_attributes=False,
        )
        try:
            events.append(Event(event_id, event_type, event_time, attributes))
        except (TypeError, ValueError) as exc:
            raise mapping_failure(
                "invalid_event",
                f"Event '{event_id}' cannot be mapped: {exc}.",
                at,
            ) from exc

        raw_relations = _require_list(
            item.get("relationships", []), at + ("relationships",)
        )
        for relation_index, raw_relation in enumerate(raw_relations):
            rel_at = at + ("relationships", str(relation_index))
            relation = _require_mapping(raw_relation, rel_at)
            _require_keys(
                relation,
                required={"objectId", "qualifier"},
                allowed={"objectId", "qualifier"},
                at=rel_at,
            )
            object_id = _require_nonblank_text(
                relation["objectId"], rel_at + ("objectId",)
            )
            qualifier = _require_text(relation["qualifier"], rel_at + ("qualifier",))
            relations.append(E2O(event_id, object_id, qualifier))
    return tuple(events), tuple(relations)


def _map_objects(
    values: list[object],
    schemas: dict[str, dict[str, ValueType]],
    context: _MappingContext,
) -> tuple[tuple[Object, ...], tuple[O2O, ...]]:
    objects: list[Object] = []
    relations: list[O2O] = []
    for index, raw in enumerate(values):
        at = ("objects", str(index))
        item = _require_mapping(raw, at)
        _require_keys(
            item,
            required={"id", "type"},
            allowed={"id", "type", "attributes", "relationships"},
            at=at,
        )
        object_id = _require_nonblank_text(item["id"], at + ("id",))
        object_type = _require_nonblank_text(item["type"], at + ("type",))
        schema = schemas.get(object_type, {})
        attributes = _map_attributes(
            item.get("attributes", []),
            schema=schema,
            context=context,
            at=at + ("attributes",),
            object_attributes=True,
        )
        try:
            objects.append(Object(object_id, object_type, attributes))
        except (TypeError, ValueError) as exc:
            raise mapping_failure(
                "invalid_object",
                f"Object '{object_id}' cannot be mapped: {exc}.",
                at,
            ) from exc

        raw_relations = _require_list(
            item.get("relationships", []), at + ("relationships",)
        )
        for relation_index, raw_relation in enumerate(raw_relations):
            rel_at = at + ("relationships", str(relation_index))
            relation = _require_mapping(raw_relation, rel_at)
            _require_keys(
                relation,
                required={"objectId", "qualifier"},
                allowed={"objectId", "qualifier"},
                at=rel_at,
            )
            target = _require_nonblank_text(
                relation["objectId"], rel_at + ("objectId",)
            )
            qualifier = _require_text(relation["qualifier"], rel_at + ("qualifier",))
            relations.append(O2O(object_id, target, qualifier))
    return tuple(objects), tuple(relations)


def _map_attributes(
    raw: object,
    *,
    schema: dict[str, ValueType],
    context: _MappingContext,
    at: tuple[str, ...],
    object_attributes: bool,
) -> tuple[EventAttr, ...] | tuple[ObjectAttr, ...]:
    values = _require_list(raw, at)
    mapped: list[EventAttr] | list[ObjectAttr] = []
    for index, raw_attribute in enumerate(values):
        attr_at = at + (str(index),)
        attribute = _require_mapping(raw_attribute, attr_at)
        required = {"name", "value", "time"} if object_attributes else {"name", "value"}
        _require_keys(attribute, required=required, allowed=required, at=attr_at)
        name = _require_nonblank_text(attribute["name"], attr_at + ("name",))
        expected = schema.get(name)
        value = (
            _map_value(attribute["value"], expected, attr_at + ("value",), context)
            if expected is not None
            else _map_untyped_value(attribute["value"], attr_at + ("value",), context)
        )
        if object_attributes:
            time = _map_time(attribute["time"], attr_at + ("time",), context)
            mapped.append(ObjectAttr(name, value, time))
        else:
            mapped.append(EventAttr(name, value))
    return tuple(mapped)


def _map_value_type(value: object, at: tuple[str, ...]) -> ValueType:
    text = _require_text(value, at)
    try:
        return ValueType(text)
    except ValueError as exc:
        raise schema_failure(
            "unsupported_attribute_type",
            f"Unsupported OCEL attribute type '{text}'.",
            at,
        ) from exc


def _map_value(
    value: object,
    expected: ValueType,
    at: tuple[str, ...],
    context: _MappingContext,
) -> Value:
    if expected is ValueType.STRING:
        return _require_text(value, at)
    if expected is ValueType.TIME:
        return _map_time(value, at, context)
    if expected is ValueType.INTEGER:
        return _map_integer(value, at, context.encoding)
    if expected is ValueType.FLOAT:
        return _map_float(value, at, context.encoding)
    if expected is ValueType.BOOLEAN:
        return _map_boolean(value, at, context.encoding)
    raise RuntimeError(f"unhandled ValueType: {expected}")


def _map_untyped_value(
    value: object,
    at: tuple[str, ...],
    context: _MappingContext,
) -> Value:
    if context.encoding is not ValueEncoding.JSON:
        return _require_text(value, at)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str):
        return value
    raise mapping_failure(
        "unsupported_untyped_value",
        "Undeclared attributes must contain a primitive non-null value.",
        at,
    )


def _map_time(
    value: object,
    at: tuple[str, ...],
    context: _MappingContext,
) -> datetime:
    text = _require_text(value, at)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        result = datetime.fromisoformat(normalized)
    except ValueError:
        result = _map_legacy_offset_time(text, at)
        context.legacy_timestamp_count += 1
    if result.tzinfo is None or result.utcoffset() is None:
        result = result.replace(tzinfo=timezone.utc)
        context.assumed_utc_count += 1
    if result.utcoffset() != timedelta(0):
        context.timezone_normalization_count += 1
    return result


_LEGACY_OFFSET_TIME = re.compile(
    r"^(?P<weekday>Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"(?P<day>\d{2}) (?P<year>\d{4}) "
    r"(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2}) "
    r"GMT(?P<sign>[+-])(?P<offset_hour>\d{2})(?P<offset_minute>\d{2})"
    r"(?: \(.+\))?$"
)
_MONTHS = {
    name: index
    for index, name in enumerate(
        (
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ),
        start=1,
    )
}
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _map_legacy_offset_time(text: str, at: tuple[str, ...]) -> datetime:
    match = _LEGACY_OFFSET_TIME.match(text)
    if match is None:
        raise mapping_failure(
            "invalid_timestamp",
            f"Timestamp '{text}' is not a supported date-time value.",
            at,
        )
    groups = match.groupdict()
    direction = 1 if groups["sign"] == "+" else -1
    try:
        offset = timezone(
            direction
            * timedelta(
                hours=int(groups["offset_hour"]),
                minutes=int(groups["offset_minute"]),
            )
        )
        result = datetime(
            int(groups["year"]),
            _MONTHS[groups["month"]],
            int(groups["day"]),
            int(groups["hour"]),
            int(groups["minute"]),
            int(groups["second"]),
            tzinfo=offset,
        )
    except ValueError as exc:
        raise mapping_failure(
            "invalid_timestamp",
            f"Timestamp '{text}' contains an invalid date or offset.",
            at,
        ) from exc
    if _WEEKDAYS[result.weekday()] != groups["weekday"]:
        raise mapping_failure(
            "invalid_timestamp_weekday",
            f"Timestamp '{text}' contains a mismatched weekday.",
            at,
        )
    return result


_INTEGER = re.compile(r"^[+-]?\d+$")


def _map_integer(
    value: object,
    at: tuple[str, ...],
    encoding: ValueEncoding,
) -> int:
    if isinstance(value, bool):
        raise mapping_failure("integer_required", "Expected an integer value.", at)
    if isinstance(value, int):
        return value
    if (
        encoding is not ValueEncoding.JSON
        and isinstance(value, str)
        and _INTEGER.match(value)
    ):
        return int(value)
    raise mapping_failure("integer_required", "Expected an integer value.", at)


def _map_float(
    value: object,
    at: tuple[str, ...],
    encoding: ValueEncoding,
) -> float:
    if isinstance(value, bool):
        raise mapping_failure("float_required", "Expected a finite float value.", at)
    if isinstance(value, (int, float)):
        result = float(value)
    elif encoding is not ValueEncoding.JSON and isinstance(value, str):
        try:
            result = float(value)
        except ValueError as exc:
            raise mapping_failure(
                "float_required", "Expected a finite float value.", at
            ) from exc
    else:
        raise mapping_failure("float_required", "Expected a finite float value.", at)
    if not math.isfinite(result):
        raise mapping_failure("float_required", "Expected a finite float value.", at)
    return result


def _map_boolean(
    value: object,
    at: tuple[str, ...],
    encoding: ValueEncoding,
) -> bool:
    if isinstance(value, bool):
        return value
    if encoding is not ValueEncoding.JSON:
        if value in (1, "1", "true"):
            return True
        if value in (0, "0", "false"):
            return False
    raise mapping_failure("boolean_required", "Expected a boolean value.", at)


def _require_mapping(value: object, at: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise schema_failure("object_required", "Expected a JSON-style object.", at)
    return value


def _require_list(value: object, at: tuple[str, ...]) -> list[object]:
    if not isinstance(value, list):
        raise schema_failure("array_required", "Expected an array.", at)
    return value


def _require_text(value: object, at: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise mapping_failure("string_required", "Expected a string value.", at)
    return value


def _require_nonblank_text(value: object, at: tuple[str, ...]) -> str:
    text = _require_text(value, at)
    if not text.strip():
        raise mapping_failure(
            "nonblank_string_required",
            "Expected a nonblank string.",
            at,
        )
    return text


def _require_keys(
    value: dict[str, Any],
    *,
    required: set[str],
    allowed: set[str],
    at: tuple[str, ...],
) -> None:
    missing = sorted(required.difference(value))
    if missing:
        raise schema_failure(
            "missing_required_member",
            f"Missing required member(s): {', '.join(missing)}.",
            at,
        )
    unexpected = sorted(set(value).difference(allowed))
    if unexpected:
        raise schema_failure(
            "unexpected_member",
            f"Unexpected member(s): {', '.join(unexpected)}.",
            at,
        )


__all__ = [
    "AdapterFailure",
    "ValueEncoding",
    "map_document",
    "mapping_failure",
    "schema_failure",
    "syntax_failure",
]
