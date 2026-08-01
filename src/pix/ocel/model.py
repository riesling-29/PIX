"""Canonical OCEL data model.

This module contains only immutable data contracts. Parsing, normalization,
global validation, and derived graph/trace structures belong elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import TypeAlias


class ValueType(str, Enum):
    """Primitive attribute types defined by OCEL 2.0."""

    STRING = "string"
    TIME = "time"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"


Value: TypeAlias = str | datetime | int | float | bool


# OCEL 2.0 uses time 0 for initial object-attribute values.
# Its reference serializations represent time 0 as the Unix epoch in UTC.
OCEL_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _require_text(value: object, field: str) -> None:
    """Require a non-blank string without changing the original value."""

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    if not value.strip():
        raise ValueError(f"{field} must not be empty")


def _require_string(value: object, field: str) -> None:
    """Require a string while allowing the empty string."""

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")


def _require_aware_time(value: object, field: str) -> None:
    """Require a timezone-aware datetime."""

    if not isinstance(value, datetime):
        raise TypeError(f"{field} must be a datetime")

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must include timezone information")


def _require_value(value: object, field: str) -> None:
    """Validate an OCEL primitive value without coercing it."""

    if isinstance(value, datetime):
        _require_aware_time(value, field)
        return

    # bool must be checked before int because bool is a subclass of int.
    if isinstance(value, bool):
        return

    if isinstance(value, int):
        return

    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{field} must be finite")
        return

    if isinstance(value, str):
        return

    raise TypeError(
        f"{field} must be str, datetime, int, float, or bool; "
        f"got {type(value).__name__}"
    )


def _require_tuple(
    value: object,
    item_type: type[object],
    field: str,
) -> None:
    """Prevent mutable collection values from entering the canonical model."""

    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")

    if not all(isinstance(item, item_type) for item in value):
        raise TypeError(f"every item in {field} must be {item_type.__name__}")


def _require_unique(
    values: tuple[object, ...],
    field: str,
) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{field} must not contain duplicates")


@dataclass(frozen=True, slots=True)
class Attribute:
    """Attribute declaration owned by one event or object type."""

    name: str
    type: ValueType

    def __post_init__(self) -> None:
        _require_text(self.name, "Attribute.name")

        if not isinstance(self.type, ValueType):
            raise TypeError("Attribute.type must be ValueType")


@dataclass(frozen=True, slots=True)
class EventType:
    """Schema declaration for one event type."""

    name: str
    attributes: tuple[Attribute, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.name, "EventType.name")
        _require_tuple(
            self.attributes,
            Attribute,
            "EventType.attributes",
        )
        _require_unique(
            tuple(attribute.name for attribute in self.attributes),
            "EventType attribute names",
        )


@dataclass(frozen=True, slots=True)
class ObjectType:
    """Schema declaration for one object type."""

    name: str
    attributes: tuple[Attribute, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.name, "ObjectType.name")
        _require_tuple(
            self.attributes,
            Attribute,
            "ObjectType.attributes",
        )
        _require_unique(
            tuple(attribute.name for attribute in self.attributes),
            "ObjectType attribute names",
        )


@dataclass(frozen=True, slots=True)
class EventAttr:
    """One attribute value assigned to an event."""

    name: str
    value: Value

    def __post_init__(self) -> None:
        _require_text(self.name, "EventAttr.name")
        _require_value(self.value, "EventAttr.value")


@dataclass(frozen=True, slots=True)
class ObjectAttr:
    """One value assignment in an object's attribute history."""

    name: str
    value: Value
    time: datetime

    def __post_init__(self) -> None:
        _require_text(self.name, "ObjectAttr.name")
        _require_value(self.value, "ObjectAttr.value")
        _require_aware_time(self.time, "ObjectAttr.time")


@dataclass(frozen=True, slots=True)
class Event:
    """An OCEL event."""

    id: str
    type: str
    time: datetime
    attributes: tuple[EventAttr, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "Event.id")
        _require_text(self.type, "Event.type")
        _require_aware_time(self.time, "Event.time")
        _require_tuple(
            self.attributes,
            EventAttr,
            "Event.attributes",
        )
        _require_unique(
            tuple(attribute.name for attribute in self.attributes),
            "Event attribute names",
        )


@dataclass(frozen=True, slots=True)
class Object:
    """An OCEL object with time-indexed attribute assignments."""

    id: str
    type: str
    attributes: tuple[ObjectAttr, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "Object.id")
        _require_text(self.type, "Object.type")
        _require_tuple(
            self.attributes,
            ObjectAttr,
            "Object.attributes",
        )
        _require_unique(
            tuple((attribute.name, attribute.time) for attribute in self.attributes),
            "Object attribute assignments",
        )


@dataclass(frozen=True, slots=True)
class E2O:
    """Qualified event-to-object relation."""

    event: str
    object: str
    qualifier: str

    def __post_init__(self) -> None:
        _require_text(self.event, "E2O.event")
        _require_text(self.object, "E2O.object")
        _require_string(self.qualifier, "E2O.qualifier")


@dataclass(frozen=True, slots=True)
class O2O:
    """Qualified directed object-to-object relation."""

    source: str
    target: str
    qualifier: str

    def __post_init__(self) -> None:
        _require_text(self.source, "O2O.source")
        _require_text(self.target, "O2O.target")
        _require_string(self.qualifier, "O2O.qualifier")


@dataclass(frozen=True, slots=True)
class OCEL:
    """Immutable canonical OCEL dataset.

    This class validates only local data-shape invariants.

    Dataset-wide rules such as unique entity IDs, declared type references,
    attribute-schema compatibility, dangling relations, and deterministic
    ordering belong to validate.py and build.py.
    """

    event_types: tuple[EventType, ...] = ()
    object_types: tuple[ObjectType, ...] = ()
    events: tuple[Event, ...] = ()
    objects: tuple[Object, ...] = ()
    e2o: tuple[E2O, ...] = ()
    o2o: tuple[O2O, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple(
            self.event_types,
            EventType,
            "OCEL.event_types",
        )
        _require_tuple(
            self.object_types,
            ObjectType,
            "OCEL.object_types",
        )
        _require_tuple(
            self.events,
            Event,
            "OCEL.events",
        )
        _require_tuple(
            self.objects,
            Object,
            "OCEL.objects",
        )
        _require_tuple(
            self.e2o,
            E2O,
            "OCEL.e2o",
        )
        _require_tuple(
            self.o2o,
            O2O,
            "OCEL.o2o",
        )


__all__ = [
    "Attribute",
    "E2O",
    "Event",
    "EventAttr",
    "EventType",
    "O2O",
    "OCEL",
    "OCEL_EPOCH",
    "Object",
    "ObjectAttr",
    "ObjectType",
    "Value",
    "ValueType",
]
