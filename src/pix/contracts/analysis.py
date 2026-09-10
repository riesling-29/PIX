"""Standard-library contracts for traces, graphs, and observed durations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal


def _text(value: object, name: str, *, blank: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if not blank and not value.strip():
        raise ValueError(f"{name} must not be blank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid UTF-8 text") from exc


def _selection(spec: object) -> None:
    qualifiers = spec.qualifiers
    if qualifiers is not None:
        if not isinstance(qualifiers, tuple):
            raise TypeError("qualifiers must be a tuple of strings or None")
        for qualifier in qualifiers:
            _text(qualifier, "qualifier", blank=True)
        object.__setattr__(spec, "qualifiers", tuple(sorted(set(qualifiers))))
    if not isinstance(spec.tie_policy, str):
        raise TypeError("tie_policy must be str")
    if spec.tie_policy not in ("reject", "event_id"):
        raise ValueError("tie_policy must be 'reject' or 'event_id'")


@dataclass(frozen=True, slots=True)
class TraceSpec:
    """None selects all qualifiers; () none; ('',) the empty qualifier.

    event_id tie breaking is a lexical convention, never causal evidence.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_type: str
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        _selection(self)


@dataclass(frozen=True, slots=True)
class OCDFGSpec:
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_types: tuple[str, ...]
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self) -> None:
        if not isinstance(self.object_types, tuple):
            raise TypeError("object_types must be an explicit tuple")
        if not self.object_types:
            raise ValueError("object_types must select at least one declared type")
        for value in self.object_types:
            _text(value, "object_type")
        object.__setattr__(self, "object_types", tuple(sorted(set(self.object_types))))
        _selection(self)


@dataclass(frozen=True, slots=True)
class TemporalSpec:
    """Gaps between recorded event timestamps; no inferred starts.

    start_attribute explicitly selects observed start time; weighting applies to
    gap samples only. Service time always counts each selected event once.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_type: str
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    weighting: Literal["event_pairs", "occurrences"] = "event_pairs"
    start_attribute: str | None = None

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        _selection(self)
        if not isinstance(self.weighting, str):
            raise TypeError("weighting must be str")
        if self.weighting not in ("event_pairs", "occurrences"):
            raise ValueError("weighting must be 'event_pairs' or 'occurrences'")
        if self.start_attribute is not None:
            _text(self.start_attribute, "start_attribute")


@dataclass(frozen=True, slots=True)
class E2OEvidence:
    event: str
    object: str
    qualifier: str


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_id: str
    activity: str
    time: datetime
    relations: tuple[E2OEvidence, ...]


@dataclass(frozen=True, slots=True)
class ObjectTrace:
    object_id: str
    object_type: str
    events: tuple[TraceEvent, ...]


@dataclass(frozen=True, slots=True)
class TraceSet:
    object_type: str
    traces: tuple[ObjectTrace, ...]


@dataclass(frozen=True, slots=True)
class TransitionEvidence:
    object_id: str
    source_event_id: str
    target_event_id: str
    source_relations: tuple[E2OEvidence, ...]
    target_relations: tuple[E2OEvidence, ...]


@dataclass(frozen=True, slots=True)
class DirectlyFollowsEdge:
    source_activity: str
    target_activity: str
    occurrence_count: int
    evidence: tuple[TransitionEvidence, ...]


@dataclass(frozen=True, slots=True)
class ActivityCount:
    """Occurrence count is across object traces, not unique source events."""

    activity: str
    event_occurrence_count: int
    distinct_event_ids: tuple[str, ...]
    object_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BoundaryEvidence:
    object_id: str
    event_id: str


@dataclass(frozen=True, slots=True)
class BoundaryCount:
    activity: str
    evidence: tuple[BoundaryEvidence, ...]


@dataclass(frozen=True, slots=True)
class DirectlyFollowsGraph:
    object_type: str
    object_count: int
    empty_object_ids: tuple[str, ...]
    activities: tuple[ActivityCount, ...]
    edges: tuple[DirectlyFollowsEdge, ...]
    starts: tuple[BoundaryCount, ...]
    ends: tuple[BoundaryCount, ...]


@dataclass(frozen=True, slots=True)
class OCDFGEdge:
    object_type: str
    source_activity: str
    target_activity: str
    event_pair_count: int
    unique_object_count: int
    occurrence_count: int
    evidence: tuple[TransitionEvidence, ...]


@dataclass(frozen=True, slots=True)
class OCDFGTypeGraph:
    object_type: str
    object_count: int
    empty_object_ids: tuple[str, ...]
    activities: tuple[ActivityCount, ...]
    edges: tuple[OCDFGEdge, ...]
    starts: tuple[BoundaryCount, ...]
    ends: tuple[BoundaryCount, ...]


@dataclass(frozen=True, slots=True)
class ObjectCentricDFG:
    graphs: tuple[OCDFGTypeGraph, ...]


@dataclass(frozen=True, slots=True)
class TemporalIssue:
    code: str
    message: str
    at: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TemporalSample:
    source_event_id: str | None
    target_event_id: str
    object_ids: tuple[str, ...]
    duration_microseconds: int
    evidence: tuple[TransitionEvidence, ...] = ()
    relations: tuple[E2OEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class DurationSummary:
    """Integer microseconds and an exact rational mean of available samples.

    A zero total with no samples is not a zero duration measurement: min, max,
    and both mean fields are None. Coverage remains explicit.
    """

    population_count: int
    sample_count: int
    unavailable_count: int
    total_microseconds: int
    minimum_microseconds: int | None
    maximum_microseconds: int | None
    mean_numerator: int | None
    mean_denominator: int | None
    samples: tuple[TemporalSample, ...]


@dataclass(frozen=True, slots=True)
class TemporalEdge:
    source_activity: str
    target_activity: str
    duration: DurationSummary


@dataclass(frozen=True, slots=True)
class ObservedTemporal:
    object_type: str
    weighting: str
    gaps: tuple[TemporalEdge, ...]
    service_status: Literal["computed", "unavailable"]
    service: DurationSummary
    service_issues: tuple[TemporalIssue, ...]
