"""Immutable execution and variant contracts, independent of calculation code.

Execution membership is a policy-derived view, not an extra OCEL fact. An
execution's event tuple is stored by ID for reproducibility; it is not a trace.
Only ``order_edges`` carry the explicitly selected temporal order semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal


def _text(value: object, name: str, *, empty: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not empty and not value.strip():
        raise ValueError(f"{name} must not be blank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{name} must contain valid Unicode") from error


def _selection(value: object, name: str, *, empty: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple or None")
    for item in value:
        _text(item, name, empty=empty)


def _tuple(value: object, kind: type, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    if not all(isinstance(item, kind) for item in value):
        raise TypeError(f"every item in {name} must be {kind.__name__}")


def _ids(value: object, name: str) -> None:
    _tuple(value, str, name)
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")


def _time(value: object) -> None:
    if not isinstance(value, datetime):
        raise TypeError("time must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("time must be timezone-aware")


def _count(value: object, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True, slots=True)
class ExecutionSpec:
    """Explicit extraction policy over selected E2O co-participation.

    ``None`` selects all types/qualifiers; ``()`` selects none. Connected
    components cover every event, including singleton events with no selected
    relation. Eventless objects remain unassigned. Leading-object extraction
    produces one execution per selected leading object, including empty ones.
    At each BFS depth it admits all objects of types first reached at that
    depth; types reached earlier are not traversed again. The anchor type is
    fixed at depth zero. No original O2O relation is used by either method.

    Extraction itself is independent of event order. ``reject`` records an
    unavailable ordered graph when a selected object's events tie; ``event_id``
    explicitly breaks such ties lexically without claiming causality.
    """

    method: Literal["connected_components", "leading_object_nearest_type"]
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    leading_object_type: str | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.method not in ("connected_components", "leading_object_nearest_type"):
            raise ValueError("ExecutionSpec.method must explicitly select a method")
        _selection(self.object_types, "object_types")
        _selection(self.qualifiers, "qualifiers", empty=True)
        if self.object_types is not None:
            object.__setattr__(
                self, "object_types", tuple(sorted(set(self.object_types)))
            )
        if self.qualifiers is not None:
            object.__setattr__(self, "qualifiers", tuple(sorted(set(self.qualifiers))))
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if self.method == "leading_object_nearest_type":
            _text(self.leading_object_type, "leading_object_type")
            if (
                self.object_types is not None
                and self.leading_object_type not in self.object_types
            ):
                raise ValueError("leading_object_type must be selected in object_types")
        elif self.leading_object_type is not None:
            raise ValueError("leading_object_type applies only to leading extraction")


@dataclass(frozen=True, slots=True)
class ExecutionEvent:
    id: str
    activity: str
    time: datetime

    def __post_init__(self) -> None:
        _text(self.id, "id")
        _text(self.activity, "activity")
        _time(self.time)


@dataclass(frozen=True, slots=True)
class ExecutionObject:
    id: str
    type: str

    def __post_init__(self) -> None:
        _text(self.id, "id")
        _text(self.type, "type")


@dataclass(frozen=True, slots=True, order=True)
class ExecutionRelation:
    event: str
    object: str
    qualifier: str

    def __post_init__(self) -> None:
        _text(self.event, "event")
        _text(self.object, "object")
        _text(self.qualifier, "qualifier", empty=True)


@dataclass(frozen=True, slots=True, order=True)
class EventOrderEdge:
    source_event: str
    target_event: str
    object_id: str
    tie_broken: bool = False

    def __post_init__(self) -> None:
        _text(self.source_event, "source_event")
        _text(self.target_event, "target_event")
        _text(self.object_id, "object_id")
        if type(self.tie_broken) is not bool:
            raise TypeError("tie_broken must be bool")


@dataclass(frozen=True, slots=True)
class EventOrderTie:
    object_id: str
    event_ids: tuple[str, ...]
    time: datetime

    def __post_init__(self) -> None:
        _text(self.object_id, "object_id")
        _ids(self.event_ids, "event_ids")
        if len(self.event_ids) < 2:
            raise ValueError("an order tie must have at least two events")
        _time(self.time)


@dataclass(frozen=True, slots=True)
class ProcessExecution:
    execution_id: str
    leading_object_id: str | None
    events: tuple[ExecutionEvent, ...]
    objects: tuple[ExecutionObject, ...]
    boundary_objects: tuple[ExecutionObject, ...]
    relations: tuple[ExecutionRelation, ...]
    excluded_relations: tuple[ExecutionRelation, ...]
    order_edges: tuple[EventOrderEdge, ...]
    order_status: Literal["complete", "unavailable"]
    order_ties: tuple[EventOrderTie, ...]

    def __post_init__(self) -> None:
        _text(self.execution_id, "execution_id")
        if self.leading_object_id is not None:
            _text(self.leading_object_id, "leading_object_id")
        for name, kind in (
            ("events", ExecutionEvent),
            ("objects", ExecutionObject),
            ("boundary_objects", ExecutionObject),
            ("relations", ExecutionRelation),
            ("excluded_relations", ExecutionRelation),
            ("order_edges", EventOrderEdge),
            ("order_ties", EventOrderTie),
        ):
            _tuple(getattr(self, name), kind, name)
        if self.order_status not in ("complete", "unavailable"):
            raise ValueError("order_status must be complete or unavailable")


@dataclass(frozen=True, slots=True)
class EntityMembership:
    entity_id: str
    execution_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.entity_id, "entity_id")
        _ids(self.execution_ids, "execution_ids")


@dataclass(frozen=True, slots=True)
class ExecutionSet:
    executions: tuple[ProcessExecution, ...]
    event_memberships: tuple[EntityMembership, ...]
    object_memberships: tuple[EntityMembership, ...]
    unassigned_event_ids: tuple[str, ...]
    unassigned_object_ids: tuple[str, ...]
    isolated_event_ids: tuple[str, ...]
    isolated_object_ids: tuple[str, ...]
    excluded_object_ids: tuple[str, ...]
    overlapping_event_ids: tuple[str, ...]
    overlapping_object_ids: tuple[str, ...]
    unique_event_count: int
    event_membership_count: int
    unique_object_count: int
    object_membership_count: int

    def __post_init__(self) -> None:
        _tuple(self.executions, ProcessExecution, "executions")
        _tuple(self.event_memberships, EntityMembership, "event_memberships")
        _tuple(self.object_memberships, EntityMembership, "object_memberships")
        for name in (
            "unassigned_event_ids",
            "unassigned_object_ids",
            "isolated_event_ids",
            "isolated_object_ids",
            "excluded_object_ids",
            "overlapping_event_ids",
            "overlapping_object_ids",
        ):
            _ids(getattr(self, name), name)
        for name in (
            "unique_event_count",
            "event_membership_count",
            "unique_object_count",
            "object_membership_count",
        ):
            _count(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class VariantSpec:
    """Exact incidence equivalence, preserving the selected ordered graph.

    IDs, absolute timestamps, attributes and O2O are excluded from equivalence.
    Event activity, object type, scope and anchor role, selected E2O qualifiers, and
    object-specific event-order edges are preserved. Boundary objects have a
    distinct scope label; objects only referenced by excluded E2O are ignored.
    The budget bounds complete canonical labeling candidates across the call;
    exhausting it makes the entire result unavailable, without partial groups.
    """

    max_search_states: int = 100_000
    equivalence: Literal["event_object_incidence"] = "event_object_incidence"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.equivalence != "event_object_incidence":
            raise ValueError("only event_object_incidence equivalence is implemented")
        if type(self.max_search_states) is not int:
            raise TypeError("max_search_states must be an integer")
        if self.max_search_states < 1:
            raise ValueError("max_search_states must be positive")


@dataclass(frozen=True, slots=True)
class ExecutionVariant:
    """One exact group; ``canonical_signature`` is a SHA256 candidate fingerprint.

    The grouping operator compares complete canonical encodings, not hashes.
    Across independently computed results a matching fingerprint is not a
    collision-free proof of equivalence.
    """

    variant_id: str
    canonical_signature: str
    execution_ids: tuple[str, ...]
    representative_execution_id: str
    frequency: int

    def __post_init__(self) -> None:
        _text(self.variant_id, "variant_id")
        _text(self.canonical_signature, "canonical_signature")
        _ids(self.execution_ids, "execution_ids")
        _text(self.representative_execution_id, "representative_execution_id")
        _count(self.frequency, "frequency")
        if self.frequency != len(self.execution_ids):
            raise ValueError("frequency must equal execution membership count")
        if self.representative_execution_id not in self.execution_ids:
            raise ValueError("representative_execution_id must belong to the variant")


@dataclass(frozen=True, slots=True)
class VariantSet:
    variants: tuple[ExecutionVariant, ...]
    execution_count: int
    search_states: int
    equivalence: str = "event_object_incidence"
    exact: bool = True

    def __post_init__(self) -> None:
        _tuple(self.variants, ExecutionVariant, "variants")
        _count(self.execution_count, "execution_count")
        _count(self.search_states, "search_states")
        if self.equivalence != "event_object_incidence":
            raise ValueError("unsupported equivalence")
        if self.exact is not True:
            raise ValueError("VariantSet represents only complete exact results")
        if self.execution_count != sum(item.frequency for item in self.variants):
            raise ValueError("execution_count must equal total variant frequencies")
