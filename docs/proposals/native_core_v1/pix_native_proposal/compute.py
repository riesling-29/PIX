"""Executable proposal for native, evidence-bearing per-object computations.

This is deliberately outside production ``pix``. The DFG operator counts adjacent
event occurrences within each object's E2O trace; it is not a complete OCDFG
discovery implementation or process-execution discovery. O2O never connects traces.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import Enum
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Generic, Literal, TypeVar

from pix.ocel import E2O, OCEL, Event, Issue, Object, Report, build
from pix.ocel import canonical_digest, validate


TRACE_OPERATOR_ID = "pix.reconstruct_traces"
DFG_OPERATOR_ID = "pix.discover_dfg"
OPERATOR_VERSION = "1.0.0-proposal.1"


class ComputeStatus(str, Enum):
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True, slots=True)
class TraceSpec:
    """One declared object type and an explicit event-ordering/filter contract.

    ``qualifiers=None`` selects all E2O qualifiers; ``()`` selects none; ``('',)``
    selects the valid empty-string qualifier. A qualifier set is normalized so
    equivalent requests receive the same computation identity. ``event_id`` breaks
    equal-time ties lexically; this is a convention, never evidence of causality.
    """

    object_type: str
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self) -> None:
        if not isinstance(self.object_type, str):
            raise TypeError("object_type must be str")
        if not self.object_type.strip():
            raise ValueError("object_type must not be blank")
        if self.qualifiers is not None:
            if not isinstance(self.qualifiers, tuple) or not all(
                isinstance(value, str) for value in self.qualifiers
            ):
                raise TypeError("qualifiers must be a tuple of strings or None")
            object.__setattr__(self, "qualifiers", tuple(sorted(set(self.qualifiers))))
        if not isinstance(self.tie_policy, str):
            raise TypeError("tie_policy must be str")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be 'reject' or 'event_id'")
        try:
            self.object_type.encode("utf-8")
            for qualifier in self.qualifiers or ():
                qualifier.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("object_type and qualifiers must be valid UTF-8 text") from exc


@dataclass(frozen=True, slots=True)
class ComputeIssue:
    code: str
    message: str
    at: tuple[str, ...] = ()


class InvalidOCELInput(ValueError):
    """Context construction failed; the original semantic report is retained."""

    def __init__(self, report: Report) -> None:
        super().__init__("Cannot prepare computation context for invalid OCEL")
        self.report = report


@dataclass(frozen=True, slots=True, init=False)
class ComputationContext:
    """Validated immutable input and indexes, reusable across native operators.

    Construction is the only supported way to create a context. Index dictionaries
    are private snapshots wrapped in read-only proxies, with immutable values.
    Datetimes are normalized by PIX's existing builder before ordering: no floating
    Unix timestamp conversion is used. A context has no mutable analysis cache.
    """

    log: OCEL
    source_digest: str
    events_by_id: Mapping[str, Event]
    objects_by_type: Mapping[str, tuple[Object, ...]]
    e2o_by_object: Mapping[str, tuple[E2O, ...]]

    def __init__(self, log: OCEL) -> None:
        if not isinstance(log, OCEL):
            raise TypeError("log must be OCEL")
        report = validate(log)
        if not report.valid:
            raise InvalidOCELInput(report)
        try:
            built = build(
                event_types=log.event_types,
                object_types=log.object_types,
                events=log.events,
                objects=log.objects,
                e2o=log.e2o,
                o2o=log.o2o,
            )
            normalized = built.ocel
            if normalized is None:
                raise InvalidOCELInput(built.report)
            normalized = replace(normalized, import_info=log.import_info)
            digest = canonical_digest(normalized).identifier
        except (OverflowError, TypeError, ValueError) as exc:
            if isinstance(exc, InvalidOCELInput):
                raise
            raise InvalidOCELInput(Report((Issue(
                code="unrepresentable_canonical_input",
                message=f"Cannot normalize canonical input: {exc}",
            ),))) from exc

        objects: dict[str, list[Object]] = {
            item.name: [] for item in normalized.object_types
        }
        relations: dict[str, list[E2O]] = {
            obj.id: [] for obj in normalized.objects
        }
        for obj in normalized.objects:
            objects[obj.type].append(obj)
        for relation in normalized.e2o:
            relations[relation.object].append(relation)

        object.__setattr__(self, "log", normalized)
        object.__setattr__(self, "source_digest", digest)
        object.__setattr__(self, "events_by_id", MappingProxyType({
            event.id: event for event in normalized.events
        }))
        object.__setattr__(self, "objects_by_type", MappingProxyType({
            name: tuple(values) for name, values in objects.items()
        }))
        object.__setattr__(self, "e2o_by_object", MappingProxyType({
            object_id: tuple(values) for object_id, values in relations.items()
        }))

    @classmethod
    def build(cls, log: OCEL) -> ComputationContext:
        return cls(log)


@dataclass(frozen=True, slots=True)
class TraceEvent:
    event_id: str
    activity: str
    time: datetime
    relations: tuple[E2O, ...]


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
    source_relations: tuple[E2O, ...]
    target_relations: tuple[E2O, ...]


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


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ComputationResult(Generic[T]):
    operator_id: str
    operator_version: str
    source_digest: str | None
    spec: TraceSpec
    status: ComputeStatus
    value: T | None
    issues: tuple[ComputeIssue, ...]
    computation_id: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TraceSpec):
            raise TypeError("spec must be TraceSpec")
        if not isinstance(self.status, ComputeStatus):
            raise TypeError("status must be ComputeStatus")
        if not isinstance(self.issues, tuple) or not all(
            isinstance(issue, ComputeIssue) for issue in self.issues
        ):
            raise TypeError("issues must be a tuple of ComputeIssue")
        if self.status is ComputeStatus.COMPUTED:
            if self.value is None or self.source_digest is None:
                raise ValueError("computed result requires value and source identity")
        elif self.value is not None or not self.issues:
            raise ValueError("failed result requires issues and no value")
        if (self.source_digest is None) != (self.computation_id is None):
            raise ValueError("source and computation identities must coexist")


def _result(
    operator_id: str,
    context: ComputationContext | None,
    spec: TraceSpec,
    status: ComputeStatus,
    value: T | None,
    issues: tuple[ComputeIssue, ...] = (),
) -> ComputationResult[T]:
    source_digest = context.source_digest if context is not None else None
    computation_id = None
    if source_digest is not None:
        request = {
            "identity_schema": "pix.proposal.computation.v1",
            "operator_id": operator_id,
            "operator_version": OPERATOR_VERSION,
            "source_digest": source_digest,
            "parameter_type": "pix.proposal.TraceSpec.v1",
            "parameters": asdict(spec),
        }
        encoded = json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        computation_id = "pix.computation.v1:sha256:" + sha256(encoded).hexdigest()
    return ComputationResult(
        operator_id=operator_id,
        operator_version=OPERATOR_VERSION,
        source_digest=source_digest,
        spec=spec,
        status=status,
        value=value,
        issues=issues,
        computation_id=computation_id,
    )


def _prepare(
    log: OCEL | ComputationContext,
) -> tuple[ComputationContext | None, tuple[ComputeIssue, ...]]:
    if isinstance(log, ComputationContext):
        return log, ()
    if not isinstance(log, OCEL):
        return None, (ComputeIssue("invalid_log_type", "Expected OCEL or context"),)
    try:
        return ComputationContext(log), ()
    except InvalidOCELInput as exc:
        return None, tuple(
            ComputeIssue(issue.code, issue.message, issue.at)
            for issue in exc.report.errors
        )


def _traces(
    context: ComputationContext, spec: TraceSpec,
) -> tuple[TraceSet | None, tuple[ComputeIssue, ...]]:
    if spec.object_type not in context.objects_by_type:
        return None, (ComputeIssue(
            "unknown_object_type",
            f"Object type {spec.object_type!r} is not declared in this OCEL",
            ("object_type", spec.object_type),
        ),)

    allowed = None if spec.qualifiers is None else frozenset(spec.qualifiers)
    traces: list[ObjectTrace] = []
    issues: list[ComputeIssue] = []
    for obj in context.objects_by_type[spec.object_type]:
        by_event: dict[str, list[E2O]] = defaultdict(list)
        for relation in context.e2o_by_object[obj.id]:
            if allowed is None or relation.qualifier in allowed:
                by_event[relation.event].append(relation)
        events = sorted(
            (context.events_by_id[event_id] for event_id in by_event),
            key=lambda event: (event.time, event.id),
        )
        if spec.tie_policy == "reject":
            for previous, following in zip(events, events[1:]):
                if previous.time == following.time:
                    issues.append(ComputeIssue(
                        "ambiguous_event_order",
                        "Equal timestamps within this object's selected events; "
                        "choose an explicit tie policy to compute a sequence",
                        ("object", obj.id, "events", previous.id, following.id),
                    ))
        traces.append(ObjectTrace(
            obj.id,
            obj.type,
            tuple(TraceEvent(
                event.id, event.type, event.time, tuple(by_event[event.id])
            ) for event in events),
        ))
    if issues:
        return None, tuple(issues)
    return TraceSet(spec.object_type, tuple(traces)), ()


def reconstruct_traces(
    log: OCEL | ComputationContext, spec: TraceSpec,
) -> ComputationResult[TraceSet]:
    """Compute one E2O trace per selected object, including isolated objects.

    Multiple qualifying E2O records produce one event occurrence with all matching
    relation evidence. Unknown object types and ambiguous selected-object ordering
    are unavailable; invalid OCEL is invalid_input. No partial success is returned.
    """

    if not isinstance(spec, TraceSpec):
        raise TypeError("spec must be TraceSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            TRACE_OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    traces, issues = _traces(context, spec)
    return _result(
        TRACE_OPERATOR_ID, context, spec,
        ComputeStatus.COMPUTED if traces is not None else ComputeStatus.UNAVAILABLE,
        traces, issues,
    )


def discover_dfg(
    log: OCEL | ComputationContext, spec: TraceSpec,
) -> ComputationResult[DirectlyFollowsGraph]:
    """Count per-object adjacent event transitions and retain their source IDs.

    A shared event can occur in multiple object traces. Counts mean the number of
    (object, source-event, target-event) occurrences, never relation-row count or
    unique global event-pair count. O2O relations do not add adjacency. Start/end
    evidence and activity coverage preserve single-event traces without fake edges.
    """

    if not isinstance(spec, TraceSpec):
        raise TypeError("spec must be TraceSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            DFG_OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    traces, issues = _traces(context, spec)
    if traces is None:
        return _result(
            DFG_OPERATOR_ID, context, spec, ComputeStatus.UNAVAILABLE, None, issues
        )

    transitions: dict[tuple[str, str], list[TransitionEvidence]] = defaultdict(list)
    occurrences: Counter[str] = Counter()
    event_ids: dict[str, set[str]] = defaultdict(set)
    object_ids: dict[str, set[str]] = defaultdict(set)
    starts: dict[str, list[BoundaryEvidence]] = defaultdict(list)
    ends: dict[str, list[BoundaryEvidence]] = defaultdict(list)
    for trace in traces.traces:
        for event in trace.events:
            occurrences[event.activity] += 1
            event_ids[event.activity].add(event.event_id)
            object_ids[event.activity].add(trace.object_id)
        for source, target in zip(trace.events, trace.events[1:]):
            transitions[source.activity, target.activity].append(TransitionEvidence(
                trace.object_id, source.event_id, target.event_id,
                source.relations, target.relations,
            ))
        if trace.events:
            first, last = trace.events[0], trace.events[-1]
            starts[first.activity].append(BoundaryEvidence(
                trace.object_id, first.event_id
            ))
            ends[last.activity].append(BoundaryEvidence(trace.object_id, last.event_id))

    graph = DirectlyFollowsGraph(
        object_type=spec.object_type,
        object_count=len(traces.traces),
        empty_object_ids=tuple(
            trace.object_id for trace in traces.traces if not trace.events
        ),
        activities=tuple(ActivityCount(
            activity, occurrences[activity], tuple(sorted(event_ids[activity])),
            tuple(sorted(object_ids[activity])),
        ) for activity in sorted(occurrences)),
        edges=tuple(DirectlyFollowsEdge(
            source, target, len(evidence), tuple(evidence),
        ) for (source, target), evidence in sorted(transitions.items())),
        starts=tuple(BoundaryCount(activity, tuple(evidence))
                     for activity, evidence in sorted(starts.items())),
        ends=tuple(BoundaryCount(activity, tuple(evidence))
                   for activity, evidence in sorted(ends.items())),
    )
    return _result(DFG_OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, graph)
