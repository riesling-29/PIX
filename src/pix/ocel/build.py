"""Deterministic construction for the PIX OCEL data model.

The builder receives already typed OCEL model components, normalizes their
representation, creates an immutable OCEL candidate, and validates the complete
dataset.

It does not parse external formats, infer missing semantics, repair invalid data,
drop records, merge duplicates, or perform semantic coercion.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TypeVar

from pix.ocel.model import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    Value,
)
from pix.ocel.report import Report
from pix.ocel.validate import validate

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Result of deterministic OCEL construction and validation.

    ``candidate`` always contains the constructed immutable OCEL representation,
    even when dataset-wide validation fails.

    ``ocel`` exposes that candidate only when validation succeeds.
    """

    candidate: OCEL
    report: Report

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, OCEL):
            raise TypeError("BuildResult.candidate must be OCEL")

        if not isinstance(self.report, Report):
            raise TypeError("BuildResult.report must be Report")

    @property
    def valid(self) -> bool:
        """Whether the constructed candidate passed semantic validation."""

        return self.report.valid

    @property
    def ocel(self) -> OCEL | None:
        """Return the validated OCEL, or None when validation failed."""

        if self.valid:
            return self.candidate

        return None


def build(
    *,
    event_types: Iterable[EventType] = (),
    object_types: Iterable[ObjectType] = (),
    events: Iterable[Event] = (),
    objects: Iterable[Object] = (),
    e2o: Iterable[E2O] = (),
    o2o: Iterable[O2O] = (),
) -> BuildResult:
    """Build a deterministic OCEL candidate and validate it.

    The input may be any iterable of already constructed PIX OCEL model
    components. Every iterable is materialized exactly once.

    Representation normalization performed here is intentionally limited to:

    - converting input iterables to immutable tuples;
    - normalizing timezone-aware datetimes to UTC;
    - deterministically ordering nested model collections;
    - deterministically ordering root OCEL collections.

    This function deliberately does not:

    - coerce identifiers or qualifiers;
    - infer event/object types;
    - infer attribute declarations;
    - widen INTEGER values to FLOAT;
    - create timestamps or identifiers;
    - remove dangling relations;
    - remove disconnected entities;
    - merge duplicate entities or relations;
    - repair invalid input.
    """

    event_type_items = _materialize(
        event_types,
        EventType,
        "event_types",
    )
    object_type_items = _materialize(
        object_types,
        ObjectType,
        "object_types",
    )
    event_items = _materialize(
        events,
        Event,
        "events",
    )
    object_items = _materialize(
        objects,
        Object,
        "objects",
    )
    e2o_items = _materialize(
        e2o,
        E2O,
        "e2o",
    )
    o2o_items = _materialize(
        o2o,
        O2O,
        "o2o",
    )

    normalized_event_types = tuple(
        sorted(
            (_normalize_event_type(item) for item in event_type_items),
            key=_event_type_key,
        )
    )
    normalized_object_types = tuple(
        sorted(
            (_normalize_object_type(item) for item in object_type_items),
            key=_object_type_key,
        )
    )
    normalized_events = tuple(
        sorted(
            (_normalize_event(item) for item in event_items),
            key=_event_key,
        )
    )
    normalized_objects = tuple(
        sorted(
            (_normalize_object(item) for item in object_items),
            key=_object_key,
        )
    )

    # Relations are sorted but never deduplicated.
    normalized_e2o = tuple(
        sorted(
            e2o_items,
            key=_e2o_key,
        )
    )
    normalized_o2o = tuple(
        sorted(
            o2o_items,
            key=_o2o_key,
        )
    )

    candidate = OCEL(
        event_types=normalized_event_types,
        object_types=normalized_object_types,
        events=normalized_events,
        objects=normalized_objects,
        e2o=normalized_e2o,
        o2o=normalized_o2o,
    )

    report = validate(candidate)

    return BuildResult(
        candidate=candidate,
        report=report,
    )


def _materialize(
    values: Iterable[T],
    item_type: type[T],
    field: str,
) -> tuple[T, ...]:
    """Materialize one input iterable without silently discarding items."""

    try:
        result = tuple(values)
    except TypeError as exc:
        raise TypeError(f"{field} must be iterable") from exc

    if not all(isinstance(item, item_type) for item in result):
        raise TypeError(f"every item in {field} must be {item_type.__name__}")

    return result


def _normalize_event_type(
    event_type: EventType,
) -> EventType:
    return EventType(
        name=event_type.name,
        attributes=tuple(
            sorted(
                event_type.attributes,
                key=_attribute_key,
            )
        ),
    )


def _normalize_object_type(
    object_type: ObjectType,
) -> ObjectType:
    return ObjectType(
        name=object_type.name,
        attributes=tuple(
            sorted(
                object_type.attributes,
                key=_attribute_key,
            )
        ),
    )


def _normalize_event(
    event: Event,
) -> Event:
    attributes = tuple(
        sorted(
            (_normalize_event_attr(attribute) for attribute in event.attributes),
            key=_event_attr_key,
        )
    )

    return Event(
        id=event.id,
        type=event.type,
        time=_normalize_time(event.time),
        attributes=attributes,
    )


def _normalize_object(
    obj: Object,
) -> Object:
    attributes = tuple(
        sorted(
            (_normalize_object_attr(attribute) for attribute in obj.attributes),
            key=_object_attr_key,
        )
    )

    return Object(
        id=obj.id,
        type=obj.type,
        attributes=attributes,
    )


def _normalize_event_attr(
    attribute: EventAttr,
) -> EventAttr:
    return EventAttr(
        name=attribute.name,
        value=_normalize_value(attribute.value),
    )


def _normalize_object_attr(
    attribute: ObjectAttr,
) -> ObjectAttr:
    return ObjectAttr(
        name=attribute.name,
        value=_normalize_value(attribute.value),
        time=_normalize_time(attribute.time),
    )


def _normalize_value(
    value: Value,
) -> Value:
    if isinstance(value, datetime):
        return _normalize_time(value)

    return value


def _normalize_time(
    value: datetime,
) -> datetime:
    """Represent the same instant in UTC."""

    return value.astimezone(timezone.utc)


def _attribute_key(
    attribute: Attribute,
) -> tuple[str, str]:
    return (
        attribute.name,
        attribute.type.value,
    )


def _event_type_key(
    event_type: EventType,
) -> tuple[
    str,
    tuple[tuple[str, str], ...],
]:
    return (
        event_type.name,
        tuple(_attribute_key(attribute) for attribute in event_type.attributes),
    )


def _object_type_key(
    object_type: ObjectType,
) -> tuple[
    str,
    tuple[tuple[str, str], ...],
]:
    return (
        object_type.name,
        tuple(_attribute_key(attribute) for attribute in object_type.attributes),
    )


def _event_attr_key(
    attribute: EventAttr,
) -> tuple[
    str,
    tuple[str, str],
]:
    return (
        attribute.name,
        _value_key(attribute.value),
    )


def _object_attr_key(
    attribute: ObjectAttr,
) -> tuple[
    str,
    str,
    tuple[str, str],
]:
    return (
        attribute.name,
        _time_key(attribute.time),
        _value_key(attribute.value),
    )


def _event_key(
    event: Event,
) -> tuple[
    str,
    str,
    str,
    tuple[tuple[str, tuple[str, str]], ...],
]:
    return (
        event.id,
        event.type,
        _time_key(event.time),
        tuple(_event_attr_key(attribute) for attribute in event.attributes),
    )


def _object_key(
    obj: Object,
) -> tuple[
    str,
    str,
    tuple[
        tuple[
            str,
            str,
            tuple[str, str],
        ],
        ...,
    ],
]:
    return (
        obj.id,
        obj.type,
        tuple(_object_attr_key(attribute) for attribute in obj.attributes),
    )


def _e2o_key(
    relation: E2O,
) -> tuple[str, str, str]:
    return (
        relation.event,
        relation.object,
        relation.qualifier,
    )


def _o2o_key(
    relation: O2O,
) -> tuple[str, str, str]:
    return (
        relation.source,
        relation.target,
        relation.qualifier,
    )


def _value_key(
    value: Value,
) -> tuple[str, str]:
    """Create a deterministic sorting key without changing the value."""

    if isinstance(value, datetime):
        return (
            "time",
            _time_key(value),
        )

    # bool must be checked before int because bool is a subclass of int.
    if isinstance(value, bool):
        return (
            "boolean",
            "true" if value else "false",
        )

    if isinstance(value, int):
        return (
            "integer",
            str(value),
        )

    if isinstance(value, float):
        return (
            "float",
            value.hex(),
        )

    if isinstance(value, str):
        return (
            "string",
            value,
        )

    # model.py prevents unsupported canonical values from reaching this point.
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _time_key(
    value: datetime,
) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


__all__ = [
    "BuildResult",
    "build",
]
