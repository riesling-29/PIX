"""Explicit native object-binding prefix metrics; no OCPA compatibility claim."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal


def _nonnegative(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    value.encode("utf-8")


def _tuple_of(value: object, kind: type, name: str, *, unique: bool = False) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, kind) for item in value
    ):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")
    if kind is str:
        for item in value:
            _text(item, name)
    if unique and len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")


def _exact_ratio(value: object, numerator: int, denominator: int, name: str) -> None:
    expected = (numerator, denominator) if denominator else None
    if value is not None:
        if not isinstance(value, tuple) or len(value) != 2:
            raise TypeError(f"{name} must be a two-integer tuple or None")
        for item in value:
            _nonnegative(item, name)
    if value != expected:
        raise ValueError(f"{name} must equal its exact count ratio")


@dataclass(frozen=True, slots=True)
class ObjectContextSpec:
    object_types: tuple[str, ...]
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    max_log_states: int = 10000
    max_context_states: int = 10000
    max_bindings: int = 10000
    profile: Literal["pix.object_context.binding_prefix.v1"] = (
        "pix.object_context.binding_prefix.v1"
    )
    scope: Literal["selected_e2o_object_universe"] = "selected_e2o_object_universe"
    participant_policy: Literal["nonempty_selected"] = "nonempty_selected"
    weighting: Literal["micro_behavior_sets"] = "micro_behavior_sets"
    termination: Literal["excluded"] = "excluded"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("object_types", "qualifiers"):
            value = getattr(self, name)
            if name == "qualifiers" and value is None:
                continue
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be a tuple")
            if name == "object_types" and not value:
                raise ValueError("object_types must select at least one type")
            for item in value:
                if not isinstance(item, str):
                    raise TypeError(f"{name} entries must be strings")
                if name == "object_types" and not item.strip():
                    raise ValueError("object type must not be blank")
                item.encode("utf-8")
            object.__setattr__(self, name, tuple(sorted(set(value))))
        for name in ("max_log_states", "max_context_states", "max_bindings"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")
        for name, choices in (
            ("tie_policy", ("reject", "event_id")),
            ("profile", ("pix.object_context.binding_prefix.v1",)),
            ("scope", ("selected_e2o_object_universe",)),
            ("participant_policy", ("nonempty_selected",)),
            ("weighting", ("micro_behavior_sets",)),
            ("termination", ("excluded",)),
        ):
            if getattr(self, name) not in choices:
                raise ValueError(f"unsupported {name}")


@dataclass(frozen=True, slots=True)
class ObjectContextRequest:
    model_digest: str
    parameters: ObjectContextSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True, order=True)
class ObjectContextBehavior:
    """Activity and exact participants; transition identity is not behavior."""

    activity: str
    objects: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        _text(self.activity, "activity")
        _tuple_of(self.objects, tuple, "behavior objects")
        types: set[str] = set()
        objects: set[str] = set()
        if not self.objects:
            raise ValueError("context behaviors require selected participants")
        normalized = []
        for entry in self.objects:
            if len(entry) != 2:
                raise ValueError("behavior objects require type and IDs")
            kind, ids = entry
            _text(kind, "object type")
            _tuple_of(ids, str, "object IDs", unique=True)
            if not ids or kind in types or objects.intersection(ids):
                raise ValueError("behavior participants must be nonempty and unique")
            types.add(kind)
            objects.update(ids)
            normalized.append((kind, tuple(sorted(ids))))
        object.__setattr__(self, "objects", tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True, order=True)
class ObjectHistory:
    object_id: str
    object_type: str
    activities: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.object_id, "object_id")
        _text(self.object_type, "object_type")
        _tuple_of(self.activities, str, "activities")


@dataclass(frozen=True, slots=True)
class ObjectContextEvidence:
    """Model sets/counts are lower-bound diagnostics when complete is false.

    enabled_binding_candidate_count counts all enabled bindings at each visited
    marking, including cap-omitted bindings, before behavior deduplication.
    """

    context_id: str
    histories: tuple[ObjectHistory, ...]
    consumed_event_ids: tuple[str, ...]
    next_event_ids: tuple[str, ...]
    observed_behaviors: tuple[ObjectContextBehavior, ...]
    model_behaviors: tuple[ObjectContextBehavior, ...]
    matching_behaviors: tuple[ObjectContextBehavior, ...]
    complete: bool
    limit_reasons: tuple[str, ...]
    reachable_model_states: int
    enabled_binding_candidate_count: int
    fitness_ratio: tuple[int, int] | None
    precision_ratio: tuple[int, int] | None

    def __post_init__(self) -> None:
        _text(self.context_id, "context_id")
        _tuple_of(self.histories, ObjectHistory, "histories")
        if len({history.object_id for history in self.histories}) != len(
            self.histories
        ):
            raise ValueError("context histories must have unique object IDs")
        for name in ("consumed_event_ids", "next_event_ids", "limit_reasons"):
            _tuple_of(getattr(self, name), str, name, unique=True)
        if not self.next_event_ids:
            raise ValueError("terminal prefixes are excluded from metric contexts")
        if set(self.consumed_event_ids) & set(self.next_event_ids):
            raise ValueError("consumed and next events must be disjoint")
        for name in ("observed_behaviors", "model_behaviors", "matching_behaviors"):
            _tuple_of(getattr(self, name), ObjectContextBehavior, name, unique=True)
        observed = set(self.observed_behaviors)
        modeled = set(self.model_behaviors)
        if not observed or len(observed) > len(self.next_event_ids):
            raise ValueError("observed behaviors must come from next events")
        if set(self.matching_behaviors) != observed & modeled:
            raise ValueError("matching behaviors must equal the behavior intersection")
        if not isinstance(self.complete, bool):
            raise TypeError("context complete must be bool")
        if self.complete == bool(self.limit_reasons):
            raise ValueError(
                "incomplete contexts require limit reasons, complete contexts prohibit them"
            )
        _nonnegative(self.reachable_model_states, "reachable_model_states")
        _nonnegative(
            self.enabled_binding_candidate_count, "enabled_binding_candidate_count"
        )
        if modeled and not self.reachable_model_states:
            raise ValueError("model behaviors require a reachable model state")
        if self.enabled_binding_candidate_count < len(modeled):
            raise ValueError(
                "modeled behavior count exceeds enabled binding candidates"
            )
        matched = len(self.matching_behaviors)
        _exact_ratio(
            self.fitness_ratio,
            matched,
            len(observed) if self.complete else 0,
            "context fitness_ratio",
        )
        _exact_ratio(
            self.precision_ratio,
            matched,
            len(modeled) if self.complete else 0,
            "context precision_ratio",
        )


@dataclass(frozen=True, slots=True)
class ObjectContextCoverage:
    """Requested contexts are unknown if log downset enumeration is capped."""

    source_event_count: int
    selected_event_count: int
    excluded_event_ids: tuple[str, ...]
    requested_contexts: int | None
    enumerated_contexts: int
    completed_contexts: int
    incomplete_contexts: int
    enumerated_log_states: int
    terminal_prefix_count: int
    log_enumeration_complete: bool
    excluded_object_count: int
    excluded_relation_count: int

    def __post_init__(self) -> None:
        for name in (
            "source_event_count",
            "selected_event_count",
            "enumerated_contexts",
            "completed_contexts",
            "incomplete_contexts",
            "enumerated_log_states",
            "terminal_prefix_count",
            "excluded_object_count",
            "excluded_relation_count",
        ):
            _nonnegative(getattr(self, name), name)
        _tuple_of(self.excluded_event_ids, str, "excluded_event_ids", unique=True)
        if self.source_event_count != self.selected_event_count + len(
            self.excluded_event_ids
        ):
            raise ValueError(
                "source event count must balance selected and excluded events"
            )
        if (
            self.enumerated_contexts
            != self.completed_contexts + self.incomplete_contexts
        ):
            raise ValueError(
                "enumerated contexts must balance complete and incomplete counts"
            )
        if (
            self.enumerated_log_states
            != self.enumerated_contexts + self.terminal_prefix_count
        ):
            raise ValueError(
                "log states must balance scored contexts and terminal prefixes"
            )
        if not self.enumerated_log_states or self.terminal_prefix_count > 1:
            raise ValueError(
                "observed downsets require an initial state and at most one terminal prefix"
            )
        if not isinstance(self.log_enumeration_complete, bool):
            raise TypeError("log_enumeration_complete must be bool")
        if self.log_enumeration_complete:
            _nonnegative(self.requested_contexts, "requested_contexts")
            if (
                self.requested_contexts != self.enumerated_contexts
                or self.terminal_prefix_count != 1
            ):
                raise ValueError(
                    "complete log enumeration requires exact population and terminal prefix"
                )
        elif self.requested_contexts is not None or self.completed_contexts:
            raise ValueError(
                "truncated log enumeration has unknown population and no completed contexts"
            )


@dataclass(frozen=True, slots=True)
class ObjectContextMetrics:
    """Ratios concern declared selected-E2O scope, never unselected log events.

    Full-scope ratios are absent after any search truncation. Complete-context
    aggregates remain diagnostics and must not be presented as full-scope scores.
    An empty denominator is absent rather than assigned an arbitrary zero/one.
    """

    model_digest: str
    selected_objects: tuple[tuple[str, str], ...]
    contexts: tuple[ObjectContextEvidence, ...]
    coverage: ObjectContextCoverage
    complete_context_intersection_count: int
    complete_context_observed_count: int
    complete_context_model_count: int
    complete_context_fitness_ratio: tuple[int, int] | None
    complete_context_precision_ratio: tuple[int, int] | None
    full_scope_fitness_ratio: tuple[int, int] | None
    full_scope_precision_ratio: tuple[int, int] | None

    def __post_init__(self) -> None:
        _text(self.model_digest, "model_digest")
        _tuple_of(self.selected_objects, tuple, "selected_objects")
        objects: dict[str, str] = {}
        for entry in self.selected_objects:
            if len(entry) != 2:
                raise ValueError("selected_objects require ID and type")
            identifier, kind = entry
            _text(identifier, "selected object ID")
            _text(kind, "selected object type")
            if identifier in objects:
                raise ValueError("selected object IDs must be unique")
            objects[identifier] = kind
        _tuple_of(self.contexts, ObjectContextEvidence, "contexts")
        if not isinstance(self.coverage, ObjectContextCoverage):
            raise TypeError("coverage must be ObjectContextCoverage")
        if len({row.context_id for row in self.contexts}) != len(self.contexts):
            raise ValueError("context IDs must be unique")
        if len({frozenset(row.consumed_event_ids) for row in self.contexts}) != len(
            self.contexts
        ):
            raise ValueError("each observed downset may appear only once")
        if len({tuple(sorted(row.histories)) for row in self.contexts}) != len(
            self.contexts
        ):
            raise ValueError("each full object history context may appear only once")
        if self.coverage.enumerated_contexts != len(self.contexts):
            raise ValueError("coverage must count the reported contexts")
        completed = tuple(row for row in self.contexts if row.complete)
        if self.coverage.completed_contexts != len(completed):
            raise ValueError("coverage must count the completed contexts")
        selected_events: set[str] = set()
        excluded_events = set(self.coverage.excluded_event_ids)
        for row in self.contexts:
            if {
                history.object_id: history.object_type for history in row.histories
            } != objects:
                raise ValueError(
                    "each context must describe the whole selected object universe"
                )
            row_events = set(row.consumed_event_ids) | set(row.next_event_ids)
            if row_events & excluded_events:
                raise ValueError("excluded events cannot appear in metric contexts")
            selected_events.update(row_events)
            for behavior in row.observed_behaviors + row.model_behaviors:
                if any(
                    objects.get(identifier) != kind
                    for kind, ids in behavior.objects
                    for identifier in ids
                ):
                    raise ValueError(
                        "behavior participants must match the selected object universe"
                    )
        if len(selected_events) > self.coverage.selected_event_count or (
            self.coverage.log_enumeration_complete
            and len(selected_events) != self.coverage.selected_event_count
        ):
            raise ValueError("selected event coverage disagrees with context evidence")
        counts = (
            (
                "complete_context_intersection_count",
                sum(len(row.matching_behaviors) for row in completed),
            ),
            (
                "complete_context_observed_count",
                sum(len(row.observed_behaviors) for row in completed),
            ),
            (
                "complete_context_model_count",
                sum(len(row.model_behaviors) for row in completed),
            ),
        )
        for name, expected in counts:
            _nonnegative(getattr(self, name), name)
            if getattr(self, name) != expected:
                raise ValueError(f"{name} must equal completed-context evidence")
        matched = self.complete_context_intersection_count
        observed = self.complete_context_observed_count
        modeled = self.complete_context_model_count
        _exact_ratio(
            self.complete_context_fitness_ratio,
            matched,
            observed,
            "complete-context fitness",
        )
        _exact_ratio(
            self.complete_context_precision_ratio,
            matched,
            modeled,
            "complete-context precision",
        )
        full = (
            self.coverage.log_enumeration_complete
            and not self.coverage.incomplete_contexts
        )
        _exact_ratio(
            self.full_scope_fitness_ratio,
            matched,
            observed if full else 0,
            "full-scope fitness",
        )
        _exact_ratio(
            self.full_scope_precision_ratio,
            matched,
            modeled if full else 0,
            "full-scope precision",
        )


__all__ = (
    "ObjectContextBehavior",
    "ObjectContextCoverage",
    "ObjectContextEvidence",
    "ObjectContextMetrics",
    "ObjectContextRequest",
    "ObjectContextSpec",
    "ObjectHistory",
)
