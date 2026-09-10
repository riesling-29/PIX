"""Joint object-centric alignment contracts over one explicit whole-log scope.

No contract here equates zero alignment cost with fitting: object weighting
assigns zero weight to zero-participant moves, and users may choose zero costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

ObjectGroups = tuple[tuple[str, tuple[str, ...]], ...]
ObjectTokenSnapshot = tuple[tuple[str, str], ...]


def _text(value: object, name: str, *, blank: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not blank and not value.strip():
        raise ValueError(f"{name} must not be blank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid Unicode") from exc


@dataclass(frozen=True, slots=True)
class ObjectAlignmentSpec:
    """Exact selected E2O participation; per-object order, one joint scope.

    Whole-log means every event, even one with no selected E2O, is consumed once.
    Objects and E2O participation are selected explicitly. None qualifiers selects
    all qualifiers; () selects none. event_id breaks only same-object time ties;
    it is a convention, not causal evidence. Independent events remain unordered.

    event costs multiply each move's base cost by 1. object costs multiply it by
    the number of distinct participating objects, including 0 for empty bindings.
    max_states bounds settled product states. max_bindings independently bounds
    enumerated enabled model bindings per marking; truncation is never optimal.
    """

    object_types: tuple[str, ...]
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    scope: Literal["whole_log"] = "whole_log"
    cost_mode: Literal["event", "object"] = "event"
    log_move_cost: int = 1
    model_move_cost: int = 1
    silent_move_cost: int = 0
    synchronous_move_cost: int = 0
    max_states: int = 10000
    max_bindings: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.object_types, tuple):
            raise TypeError("object_types must be an explicit tuple")
        for value in self.object_types:
            _text(value, "object_type")
        object.__setattr__(self, "object_types", tuple(sorted(set(self.object_types))))
        if self.qualifiers is not None:
            if not isinstance(self.qualifiers, tuple):
                raise TypeError("qualifiers must be a tuple or None")
            for value in self.qualifiers:
                _text(value, "qualifier", blank=True)
            object.__setattr__(self, "qualifiers", tuple(sorted(set(self.qualifiers))))
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if self.scope != "whole_log":
            raise ValueError("only an explicit whole_log scope is supported")
        if self.cost_mode not in ("event", "object"):
            raise ValueError("cost_mode must be event or object")
        for name in (
            "log_move_cost",
            "model_move_cost",
            "silent_move_cost",
            "synchronous_move_cost",
            "max_states",
            "max_bindings",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            minimum = 1 if name in ("max_states", "max_bindings") else 0
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class ObjectAlignmentRequest:
    model_digest: str
    parameters: ObjectAlignmentSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ObjectEventParticipation:
    event_id: str
    activity: str
    objects: ObjectGroups
    relations: tuple[tuple[str, str, str], ...]


@dataclass(frozen=True, slots=True)
class ObjectPrecedence:
    object_id: str
    predecessor_event_id: str
    successor_event_id: str


@dataclass(frozen=True, slots=True)
class ObjectLogScope:
    """Events are ID-sorted for identity only, not a imposed total log order."""

    events: tuple[ObjectEventParticipation, ...]
    precedence: tuple[ObjectPrecedence, ...]
    selected_objects: tuple[tuple[str, str], ...]
    excluded_object_count: int
    excluded_relation_count: int
    scope: Literal["whole_log"] = "whole_log"


@dataclass(frozen=True, slots=True)
class ObjectAlignmentMove:
    kind: Literal["synchronous", "silent", "model", "log"]
    event_id: str | None
    transition_id: str | None
    activity: str | None
    objects: ObjectGroups
    weight: int
    cost: int
    before_marking: ObjectTokenSnapshot
    after_marking: ObjectTokenSnapshot


@dataclass(frozen=True, slots=True)
class ObjectAlignmentMoveCounts:
    synchronous: int
    silent: int
    model: int
    log: int


@dataclass(frozen=True, slots=True)
class ObjectAlignmentCoverage:
    requested_scopes: int
    optimal_scopes: int
    unreachable_scopes: int
    limited_scopes: int
    excluded_scopes: int
    input_events: int
    selected_objects: int

    @property
    def completed_scopes(self) -> int:
        return self.optimal_scopes + self.unreachable_scopes


@dataclass(frozen=True, slots=True)
class ObjectAlignment:
    """One globally consistent path, or bounded-search evidence without a path.

    A move's objects retains empty groups required by its model transition;
    matching ignores these empty groups and otherwise requires exact equality.
    Marking snapshots preserve repeated (place, object) tokens as multiplicity.
    The bound is in stated cost-profile units. No normalized fitness is supplied.
    """

    model_digest: str
    scope: ObjectLogScope
    status: Literal["optimal", "unreachable", "search_limit", "binding_limit"]
    moves: tuple[ObjectAlignmentMove, ...]
    move_counts: ObjectAlignmentMoveCounts | None
    cost: int | None
    lower_bound_cost: int | None
    settled_states: int
    discovered_states: int
    max_enabled_binding_count: int
    coverage: ObjectAlignmentCoverage
    cost_unit: Literal["event_weighted_integer_cost", "object_weighted_integer_cost"]


__all__ = (
    "ObjectAlignment",
    "ObjectAlignmentCoverage",
    "ObjectAlignmentMove",
    "ObjectAlignmentMoveCounts",
    "ObjectAlignmentRequest",
    "ObjectAlignmentSpec",
    "ObjectEventParticipation",
    "ObjectLogScope",
    "ObjectPrecedence",
)
