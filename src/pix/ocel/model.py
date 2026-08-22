"""Canonical OCEL data model.

This module contains only immutable data contracts. Parsing, normalization,
global validation, and derived graph/trace structures belong elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from math import isfinite
from typing import TypeAlias, TypeVar

from pix.ocel.metadata import OCELImportInfo, OCELWarning, TimezoneInfo


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
class OCELInfo:
    """Deterministic, JSON-friendly structural information about an OCEL.

    The profile contains descriptive counts only. It does not validate the
    dataset or derive process executions, traces, or graph analytics.
    """

    event_type_count: int
    object_type_count: int
    event_count: int
    object_count: int
    e2o_count: int
    o2o_count: int
    event_counts_by_type: tuple[tuple[str, int], ...]
    object_counts_by_type: tuple[tuple[str, int], ...]
    e2o_counts_by_qualifier: tuple[tuple[str, int], ...]
    o2o_counts_by_qualifier: tuple[tuple[str, int], ...]
    disconnected_event_count: int
    objects_without_e2o_count: int
    earliest_event_time: datetime | None
    latest_event_time: datetime | None

    def to_dict(self) -> dict[str, object]:
        """Return a stable representation suitable for people, JSON, and AI."""

        return {
            "eventTypeCount": self.event_type_count,
            "objectTypeCount": self.object_type_count,
            "eventCount": self.event_count,
            "objectCount": self.object_count,
            "e2oCount": self.e2o_count,
            "o2oCount": self.o2o_count,
            "eventCountsByType": dict(self.event_counts_by_type),
            "objectCountsByType": dict(self.object_counts_by_type),
            "e2oCountsByQualifier": dict(self.e2o_counts_by_qualifier),
            "o2oCountsByQualifier": dict(self.o2o_counts_by_qualifier),
            "disconnectedEventCount": self.disconnected_event_count,
            "objectsWithoutE2OCount": self.objects_without_e2o_count,
            "earliestEventTime": _describe_time(self.earliest_event_time),
            "latestEventTime": _describe_time(self.latest_event_time),
        }

    def summary(self) -> str:
        """Return a compact human-readable summary."""

        return (
            f"OCEL(events={self.event_count}, objects={self.object_count}, "
            f"event_types={self.event_type_count}, "
            f"object_types={self.object_type_count}, e2o={self.e2o_count}, "
            f"o2o={self.o2o_count})"
        )


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
    import_info: OCELImportInfo | None = field(
        default=None,
        compare=False,
        hash=False,
        repr=False,
    )
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
        if self.import_info is not None and not isinstance(
            self.import_info, OCELImportInfo
        ):
            raise TypeError("OCEL.import_info must be OCELImportInfo or None")

    @property
    def timezone_type(self) -> str:
        """Return the timezone used by canonical timestamp values."""

        if self.import_info is not None:
            return self.import_info.timezone.canonical_timezone
        return "UTC"

    @property
    def timezone_info(self) -> TimezoneInfo:
        """Return source-to-canonical timezone conversion information."""

        if self.import_info is not None:
            return self.import_info.timezone
        return TimezoneInfo()

    @property
    def warnings(self) -> tuple[OCELWarning, ...]:
        """Return aggregated import warnings retained by the reader."""

        if self.import_info is None:
            return ()
        return self.import_info.warnings

    def info(self) -> OCELInfo:
        """Return deterministic structural information without mutating data."""

        event_counts = _count_by(tuple(event.type for event in self.events))
        object_counts = _count_by(tuple(obj.type for obj in self.objects))
        e2o_qualifiers = _count_by(
            tuple(relation.qualifier for relation in self.e2o)
        )
        o2o_qualifiers = _count_by(
            tuple(relation.qualifier for relation in self.o2o)
        )
        related_events = {relation.event for relation in self.e2o}
        related_objects = {relation.object for relation in self.e2o}
        event_times = tuple(event.time for event in self.events)

        return OCELInfo(
            event_type_count=len(self.event_types),
            object_type_count=len(self.object_types),
            event_count=len(self.events),
            object_count=len(self.objects),
            e2o_count=len(self.e2o),
            o2o_count=len(self.o2o),
            event_counts_by_type=event_counts,
            object_counts_by_type=object_counts,
            e2o_counts_by_qualifier=e2o_qualifiers,
            o2o_counts_by_qualifier=o2o_qualifiers,
            disconnected_event_count=sum(
                event.id not in related_events for event in self.events
            ),
            objects_without_e2o_count=sum(
                obj.id not in related_objects for obj in self.objects
            ),
            earliest_event_time=min(event_times) if event_times else None,
            latest_event_time=max(event_times) if event_times else None,
        )

    def describe(self) -> dict[str, object]:
        """Return a stable structural description for people and AI clients."""

        description = self.info().to_dict()
        description["timezoneType"] = self.timezone_type
        description["timezoneInfo"] = self.timezone_info.to_dict()
        description["warnings"] = tuple(
            warning.to_dict() for warning in self.warnings
        )
        if self.import_info is not None:
            description["importInfo"] = self.import_info.to_dict()
        return description

    def summary(self) -> str:
        """Return a compact human-readable dataset summary."""

        return self.info().summary()

    def get_event(self, event_id: str) -> Event:
        """Return one event by ID, rejecting missing or ambiguous matches."""

        _require_text(event_id, "event_id")
        matches = tuple(event for event in self.events if event.id == event_id)
        return _one_by_id(matches, "event", event_id)

    def get_object(self, object_id: str) -> Object:
        """Return one object by ID, rejecting missing or ambiguous matches."""

        _require_text(object_id, "object_id")
        matches = tuple(obj for obj in self.objects if obj.id == object_id)
        return _one_by_id(matches, "object", object_id)

    def events_by_type(self, event_type: str) -> tuple[Event, ...]:
        """Return events whose declared type name matches exactly."""

        _require_text(event_type, "event_type")
        return tuple(event for event in self.events if event.type == event_type)

    def objects_by_type(self, object_type: str) -> tuple[Object, ...]:
        """Return objects whose declared type name matches exactly."""

        _require_text(object_type, "object_type")
        return tuple(obj for obj in self.objects if obj.type == object_type)

    def e2o_for_event(
        self,
        event_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[E2O, ...]:
        """Return qualified E2O records without collapsing multiplicity."""

        _require_text(event_id, "event_id")
        if qualifier is not None:
            _require_string(qualifier, "qualifier")
        return tuple(
            relation
            for relation in self.e2o
            if relation.event == event_id
            and (qualifier is None or relation.qualifier == qualifier)
        )

    def e2o_for_object(
        self,
        object_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[E2O, ...]:
        """Return E2O records targeting one object."""

        _require_text(object_id, "object_id")
        if qualifier is not None:
            _require_string(qualifier, "qualifier")
        return tuple(
            relation
            for relation in self.e2o
            if relation.object == object_id
            and (qualifier is None or relation.qualifier == qualifier)
        )

    def objects_for_event(
        self,
        event_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[Object, ...]:
        """Return unique objects referenced by one event."""

        relations = self.e2o_for_event(event_id, qualifier=qualifier)
        object_ids = {relation.object for relation in relations}
        return tuple(obj for obj in self.objects if obj.id in object_ids)

    def events_for_object(
        self,
        object_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[Event, ...]:
        """Return unique events referring to one object."""

        relations = self.e2o_for_object(object_id, qualifier=qualifier)
        event_ids = {relation.event for relation in relations}
        return tuple(event for event in self.events if event.id in event_ids)

    def outgoing_o2o(
        self,
        object_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[O2O, ...]:
        """Return directed O2O records originating at one object."""

        _require_text(object_id, "object_id")
        if qualifier is not None:
            _require_string(qualifier, "qualifier")
        return tuple(
            relation
            for relation in self.o2o
            if relation.source == object_id
            and (qualifier is None or relation.qualifier == qualifier)
        )

    def incoming_o2o(
        self,
        object_id: str,
        *,
        qualifier: str | None = None,
    ) -> tuple[O2O, ...]:
        """Return directed O2O records targeting one object."""

        _require_text(object_id, "object_id")
        if qualifier is not None:
            _require_string(qualifier, "qualifier")
        return tuple(
            relation
            for relation in self.o2o
            if relation.target == object_id
            and (qualifier is None or relation.qualifier == qualifier)
        )


def _count_by(values: tuple[str, ...]) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return tuple(sorted(counts.items()))


def _describe_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


_Entity = TypeVar("_Entity", Event, Object)


def _one_by_id(
    matches: tuple[_Entity, ...],
    kind: str,
    identifier: str,
) -> _Entity:
    if not matches:
        raise KeyError(f"unknown {kind} id: {identifier}")
    if len(matches) > 1:
        raise ValueError(f"{kind} id is not unique: {identifier}")
    return matches[0]


__all__ = [
    "Attribute",
    "E2O",
    "Event",
    "EventAttr",
    "EventType",
    "O2O",
    "OCEL",
    "OCELInfo",
    "OCEL_EPOCH",
    "Object",
    "ObjectAttr",
    "ObjectType",
    "Value",
    "ValueType",
]
