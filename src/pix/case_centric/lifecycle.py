"""Native source-order lifecycle pairing and explicitly timed adjacent paths.

The default pairing policy leaves an overlapping component unresolved. FIFO and
LIFO are explicit assumptions, never inferred from timestamps. The instance
policy requires a typed instance attribute and still rejects overlapping reuse
of an instance. Start and completion records remain distinct source facts.

Restoration requires the original CaseLog sidecar. This is lossless provenance
restoration, not synthesis of lifecycle records from arbitrary intervals.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseEvent, CaseLog, CaseTrace, case_log_digest
from pix.event_log.adapters import _activity, _facts


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _aware(value: datetime | None, name: str) -> None:
    if value is not None and (
        not isinstance(value, datetime) or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be timezone-aware or None")


@dataclass(frozen=True, slots=True)
class LifecycleSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    transition_key: str = "lifecycle:transition"
    start_value: str = "start"
    complete_value: str = "complete"
    pairing_policy: str = "unambiguous"
    instance_key: str | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        for name in ("transition_key", "start_value", "complete_value"):
            _text(getattr(self, name), name)
        if self.start_value == self.complete_value:
            raise ValueError("start_value and complete_value must differ")
        if self.pairing_policy not in ("unambiguous", "fifo", "lifo", "instance"):
            raise ValueError("unsupported lifecycle pairing policy")
        if self.pairing_policy == "instance":
            _text(self.instance_key, "instance_key")
        elif self.instance_key is not None:
            raise ValueError("instance_key is only used by the instance policy")


@dataclass(frozen=True, slots=True)
class LifecycleInterval:
    id: str
    trace_id: str
    activity: str
    start_event_id: str
    complete_event_id: str
    start_position: int
    complete_position: int
    start_time: datetime | None
    complete_time: datetime | None
    service_seconds: float | None
    instance_value: str | None = None
    time_issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "id",
            "trace_id",
            "activity",
            "start_event_id",
            "complete_event_id",
        ):
            _text(getattr(self, name), name)
        if self.start_event_id == self.complete_event_id:
            raise ValueError("start and complete must be different source events")
        if (
            type(self.start_position) is not int
            or type(self.complete_position) is not int
            or not 0 <= self.start_position < self.complete_position
        ):
            raise ValueError("lifecycle endpoints must follow source order")
        _aware(self.start_time, "start_time")
        _aware(self.complete_time, "complete_time")
        if self.service_seconds is not None:
            if (
                type(self.service_seconds) is not float
                or not isfinite(self.service_seconds)
                or self.service_seconds < 0
            ):
                raise ValueError("service_seconds must be a finite nonnegative float")
            if self.start_time is None or self.complete_time is None:
                raise ValueError("service_seconds requires both observed endpoints")
            if self.service_seconds != _seconds(self.start_time, self.complete_time):
                raise ValueError("service_seconds must equal observed elapsed time")
        if not isinstance(self.time_issue_codes, tuple) or not all(
            isinstance(code, str) and code for code in self.time_issue_codes
        ):
            raise TypeError("time_issue_codes must be a tuple of nonempty strings")


@dataclass(frozen=True, slots=True)
class UnmatchedLifecycleEvent:
    trace_id: str
    event_id: str
    source_position: int
    activity: str | None
    lifecycle: str | None
    reason: str

    def __post_init__(self) -> None:
        for name in ("trace_id", "event_id", "reason"):
            _text(getattr(self, name), name)
        if type(self.source_position) is not int or self.source_position < 0:
            raise ValueError("source_position must be a nonnegative int")


@dataclass(frozen=True, slots=True)
class LifecyclePairing:
    trace_ids: tuple[str, ...]
    source_event_count: int
    intervals: tuple[LifecycleInterval, ...]
    unmatched: tuple[UnmatchedLifecycleEvent, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.trace_ids, tuple)
            or not all(isinstance(value, str) and value for value in self.trace_ids)
            or len(set(self.trace_ids)) != len(self.trace_ids)
        ):
            raise ValueError("trace_ids must be distinct nonempty strings")
        if not isinstance(self.intervals, tuple) or not all(
            isinstance(value, LifecycleInterval) for value in self.intervals
        ):
            raise TypeError("intervals must be a tuple of LifecycleInterval")
        if not isinstance(self.unmatched, tuple) or not all(
            isinstance(value, UnmatchedLifecycleEvent) for value in self.unmatched
        ):
            raise TypeError("unmatched must be a tuple of UnmatchedLifecycleEvent")
        references = [
            (interval.trace_id, position, event_id)
            for interval in self.intervals
            for position, event_id in (
                (interval.start_position, interval.start_event_id),
                (interval.complete_position, interval.complete_event_id),
            )
        ] + [
            (item.trace_id, item.source_position, item.event_id)
            for item in self.unmatched
        ]
        if type(self.source_event_count) is not int or self.source_event_count != len(
            references
        ):
            raise ValueError("each source event must have exactly one disposition")
        if len({event_id for _, _, event_id in references}) != len(references):
            raise ValueError("event references must be distinct")
        positions: dict[str, list[int]] = {trace_id: [] for trace_id in self.trace_ids}
        for trace_id, position, _ in references:
            if trace_id not in positions:
                raise ValueError("event reference uses an unknown trace")
            positions[trace_id].append(position)
        if any(
            sorted(values) != list(range(len(values))) for values in positions.values()
        ):
            raise ValueError(
                "source positions must be a complete permutation per trace"
            )


@dataclass(frozen=True, slots=True)
class AdjacentIntervalSpec:
    """Choose the target endpoint explicitly; there is no timestamp fallback.

    ``completion_to_start`` requires start_timestamp_key. The explicitly chosen
    ``completion_to_completion`` policy requires None instead and measures a
    completion gap, not waiting or service time.
    """

    start_timestamp_key: str | None
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    endpoint_policy: str = "completion_to_start"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if self.endpoint_policy == "completion_to_start":
            _text(self.start_timestamp_key, "start_timestamp_key")
        elif self.endpoint_policy == "completion_to_completion":
            if self.start_timestamp_key is not None:
                raise ValueError(
                    "completion_to_completion does not use a start timestamp key"
                )
        else:
            raise ValueError("unsupported endpoint policy")


@dataclass(frozen=True, slots=True)
class AdjacentInterval:
    id: str
    trace_id: str
    source_event_id: str
    target_event_id: str
    source_activity: str | None
    target_activity: str | None
    source_position: int
    target_position: int
    source_complete_time: datetime | None
    target_time: datetime | None
    duration_seconds: float | None
    issue_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "trace_id", "source_event_id", "target_event_id"):
            _text(getattr(self, name), name)
        if (
            type(self.source_position) is not int
            or type(self.target_position) is not int
            or self.source_position < 0
            or self.target_position != self.source_position + 1
        ):
            raise ValueError("path endpoints must be adjacent in source order")
        _aware(self.source_complete_time, "source_complete_time")
        _aware(self.target_time, "target_time")
        if self.duration_seconds is not None:
            if (
                type(self.duration_seconds) is not float
                or not isfinite(self.duration_seconds)
                or self.duration_seconds < 0
                or self.source_complete_time is None
                or self.target_time is None
                or self.duration_seconds
                != _seconds(self.source_complete_time, self.target_time)
            ):
                raise ValueError(
                    "duration_seconds must equal nonnegative observed elapsed time"
                )


@dataclass(frozen=True, slots=True)
class AdjacentIntervals:
    trace_ids: tuple[str, ...]
    source_event_count: int
    intervals: tuple[AdjacentInterval, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.trace_ids, tuple) or not all(
            isinstance(value, str) and value for value in self.trace_ids
        ):
            raise TypeError("trace_ids must be a tuple of nonempty strings")
        if type(self.source_event_count) is not int or self.source_event_count < 0:
            raise ValueError("source_event_count must be a nonnegative int")
        if not isinstance(self.intervals, tuple) or not all(
            isinstance(value, AdjacentInterval) for value in self.intervals
        ):
            raise TypeError("intervals must be a tuple of AdjacentInterval")


def _seconds(start: datetime, end: datetime) -> float:
    return (
        end.astimezone(timezone.utc) - start.astimezone(timezone.utc)
    ).total_seconds()


def _timestamp(
    log: CaseLog, event: CaseEvent, key: str, prefix: str
) -> tuple[datetime | None, tuple[str, ...]]:
    try:
        attribute = log.attribute(event, key)
    except ValueError:
        return None, (f"{prefix}_ambiguous_timestamp",)
    if attribute is None:
        return None, (f"{prefix}_missing_timestamp",)
    if attribute.type != "date":
        return None, (f"{prefix}_invalid_timestamp_type",)
    if attribute.value.utcoffset() is None:
        return None, (f"{prefix}_naive_timestamp",)
    try:
        # Persisted results use UTC. Normalize here as well so DST-fold equality
        # and restoration are independent of the source tzinfo implementation.
        return attribute.value.astimezone(timezone.utc), ()
    except OverflowError:
        return None, (f"{prefix}_timestamp_out_of_range",)


def _identifier(kind: str, *parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return f"pix.{kind}.v1:sha256:" + sha256(encoded).hexdigest()


def _validate_classifier(log: CaseLog, spec: CaseTraceSpec) -> None:
    if (
        spec.classifier is not None
        and len(
            [
                classifier
                for classifier in log.classifiers
                if classifier.name == spec.classifier and classifier.scope == "event"
            ]
        )
        != 1
    ):
        raise ValueError("classifier must select exactly one declared event classifier")


def _instance(log: CaseLog, event: CaseEvent, key: str) -> str:
    attribute = log.attribute(event, key)
    if attribute is None or attribute.type not in (
        "string",
        "id",
        "date",
        "int",
        "float",
        "boolean",
    ):
        raise ValueError("instance requires a primitive attribute")
    if isinstance(attribute.value, float) and not isfinite(attribute.value):
        raise ValueError("instance must be finite")
    return json.dumps(
        [attribute.type, _facts(attribute.value)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


@dataclass(slots=True)
class _OpenGroup:
    starts: deque[tuple[int, CaseEvent]] = field(default_factory=deque)
    component: list[tuple[int, CaseEvent, str]] = field(default_factory=list)
    ambiguous: bool = False


def pair_lifecycle_events(
    log: CaseLog, spec: LifecycleSpec = LifecycleSpec()
) -> ComputationResult[LifecyclePairing]:
    """Pair start/complete events per trace and selected activity in source order.

    Invalid or unsupported event keys are explicitly unmatched. Valid pairs may
    still have unknown service duration. Ambiguous overlap under the default or
    instance policy leaves the whole overlapping component unmatched, including
    later completions, so no leftover completion is silently paired elsewhere.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, LifecycleSpec):
        raise TypeError("pair_lifecycle_events requires CaseLog and LifecycleSpec")
    digest = case_log_digest(log)
    operator = "pix.case_centric.lifecycle.pair"
    try:
        _validate_classifier(log, spec.trace_spec)
    except ValueError as exc:
        return _derived_result(
            operator,
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue("invalid_classifier", str(exc)),),
        )
    intervals: list[LifecycleInterval] = []
    unmatched: list[UnmatchedLifecycleEvent] = []
    issues: list[ComputeIssue] = []

    def exclude(
        trace: CaseTrace,
        position: int,
        event: CaseEvent,
        activity: str | None,
        lifecycle: str | None,
        reason: str,
    ) -> None:
        unmatched.append(
            UnmatchedLifecycleEvent(
                trace.id, event.id, position, activity, lifecycle, reason
            )
        )
        issues.append(
            ComputeIssue(
                reason,
                "Lifecycle event remains unmatched; source facts are preserved",
                ("trace", trace.id, "event", event.id),
            )
        )

    def emit(
        trace: CaseTrace,
        activity: str,
        instance: str | None,
        start: tuple[int, CaseEvent],
        complete: tuple[int, CaseEvent],
    ) -> None:
        start_time, start_codes = _timestamp(
            log, start[1], spec.trace_spec.timestamp_key, "start"
        )
        complete_time, complete_codes = _timestamp(
            log, complete[1], spec.trace_spec.timestamp_key, "complete"
        )
        codes = start_codes + complete_codes
        seconds = None
        if start_time is not None and complete_time is not None:
            observed = _seconds(start_time, complete_time)
            if observed < 0:
                codes += ("negative_service_interval",)
            else:
                seconds = observed
        identity = _identifier(
            "lifecycle-interval", digest, trace.id, start[1].id, complete[1].id
        )
        intervals.append(
            LifecycleInterval(
                identity,
                trace.id,
                activity,
                start[1].id,
                complete[1].id,
                start[0],
                complete[0],
                start_time,
                complete_time,
                seconds,
                instance,
                codes,
            )
        )
        issues.extend(
            ComputeIssue(
                code,
                "Service duration is unknown for this observed pair",
                ("trace", trace.id, "interval", identity),
            )
            for code in codes
        )

    detect_overlap = spec.pairing_policy in ("unambiguous", "instance")
    for trace in log.traces:
        groups: dict[tuple[str, str | None], _OpenGroup] = {}
        for position, event in enumerate(trace.events):
            try:
                activity = _activity(log, event, spec.trace_spec)
            except ValueError:
                exclude(trace, position, event, None, None, "invalid_activity")
                continue
            try:
                transition = log.attribute(event, spec.transition_key)
            except ValueError:
                exclude(
                    trace,
                    position,
                    event,
                    activity,
                    None,
                    "ambiguous_lifecycle_transition",
                )
                continue
            if transition is None or transition.type != "string":
                exclude(
                    trace,
                    position,
                    event,
                    activity,
                    None,
                    "missing_or_invalid_lifecycle_transition",
                )
                continue
            lifecycle = transition.value
            if lifecycle not in (spec.start_value, spec.complete_value):
                exclude(
                    trace,
                    position,
                    event,
                    activity,
                    lifecycle,
                    "unsupported_lifecycle_transition",
                )
                continue
            instance = None
            if spec.instance_key is not None:
                try:
                    instance = _instance(log, event, spec.instance_key)
                except ValueError:
                    exclude(
                        trace,
                        position,
                        event,
                        activity,
                        lifecycle,
                        "missing_or_invalid_instance",
                    )
                    continue
            key = (activity, instance)
            state = groups.setdefault(key, _OpenGroup())
            starts, component = state.starts, state.component
            if lifecycle == spec.start_value:
                if starts and detect_overlap:
                    state.ambiguous = True
                starts.append((position, event))
                if detect_overlap:
                    component.append((position, event, lifecycle))
                continue
            if not starts:
                exclude(
                    trace, position, event, activity, lifecycle, "unmatched_complete"
                )
                continue
            if state.ambiguous:
                starts.popleft()  # Only an open-count update; no pairing is inferred.
                component.append((position, event, lifecycle))
                if not starts:
                    for item_position, item_event, item_lifecycle in component:
                        exclude(
                            trace,
                            item_position,
                            item_event,
                            activity,
                            item_lifecycle,
                            "ambiguous_overlap",
                        )
                    del groups[key]
                continue
            start = starts.pop() if spec.pairing_policy == "lifo" else starts.popleft()
            emit(trace, activity, instance, start, (position, event))
            if not starts:
                del groups[key]
        for (activity, _), state in groups.items():
            if state.ambiguous:
                for position, event, lifecycle in state.component:
                    exclude(
                        trace, position, event, activity, lifecycle, "ambiguous_overlap"
                    )
            else:
                for position, event in state.starts:
                    exclude(
                        trace,
                        position,
                        event,
                        activity,
                        spec.start_value,
                        "unmatched_start",
                    )
    trace_order = {trace.id: position for position, trace in enumerate(log.traces)}
    intervals.sort(
        key=lambda interval: (trace_order[interval.trace_id], interval.start_position)
    )
    unmatched.sort(key=lambda item: (trace_order[item.trace_id], item.source_position))
    value = LifecyclePairing(
        tuple(trace_order),
        sum(len(trace.events) for trace in log.traces),
        tuple(intervals),
        tuple(unmatched),
    )
    return _derived_result(
        operator,
        digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
    )


def restore_lifecycle_events(
    result: ComputationResult[LifecyclePairing], source_log: CaseLog
) -> CaseLog:
    """Rebuild original lifecycle records using verified source-sidecar lineage.

    Arbitrary interval logs cannot be reversed without their original records:
    endpoint attributes, lexical values and unsupported transitions would be
    unknowable. The supplied source must match the recorded digest; recomputed
    evidence must exactly match, preventing forged interval references.
    """
    if not isinstance(source_log, CaseLog) or not isinstance(result, ComputationResult):
        raise TypeError("restore_lifecycle_events requires result and original CaseLog")
    if (
        result.operator_id != "pix.case_centric.lifecycle.pair"
        or not isinstance(result.spec, LifecycleSpec)
        or not isinstance(result.value, LifecyclePairing)
        or result.status not in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL)
    ):
        raise ValueError("result must contain native lifecycle pairing evidence")
    if result.source_digest != case_log_digest(source_log):
        raise ValueError("source sidecar digest differs from lifecycle evidence")
    if pair_lifecycle_events(source_log, result.spec) != result:
        raise ValueError(
            "lifecycle evidence does not match the original source and policy"
        )
    references: dict[str, list[tuple[int, str]]] = {
        trace_id: [] for trace_id in result.value.trace_ids
    }
    for interval in result.value.intervals:
        references[interval.trace_id].extend(
            (
                (interval.start_position, interval.start_event_id),
                (interval.complete_position, interval.complete_event_id),
            )
        )
    for item in result.value.unmatched:
        references[item.trace_id].append((item.source_position, item.event_id))
    events = {event.id: event for trace in source_log.traces for event in trace.events}
    traces = tuple(
        replace(
            trace,
            events=tuple(
                events[event_id] for _, event_id in sorted(references[trace.id])
            ),
        )
        for trace in source_log.traces
    )
    return replace(source_log, traces=traces)


def derive_adjacent_intervals(
    log: CaseLog, spec: AdjacentIntervalSpec
) -> ComputationResult[AdjacentIntervals]:
    """Measure every source-adjacent path using the explicitly selected endpoints.

    These are observed endpoint gaps. Concurrency can produce negative gaps;
    they retain endpoint evidence with unknown duration, never zero-clamping.
    No business calendar, causal ordering, waiting or service claim is inferred.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, AdjacentIntervalSpec):
        raise TypeError(
            "derive_adjacent_intervals requires CaseLog and AdjacentIntervalSpec"
        )
    digest = case_log_digest(log)
    operator = "pix.case_centric.lifecycle.adjacent_intervals"
    try:
        _validate_classifier(log, spec.trace_spec)
    except ValueError as exc:
        return _derived_result(
            operator,
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue("invalid_classifier", str(exc)),),
        )
    intervals: list[AdjacentInterval] = []
    issues: list[ComputeIssue] = []
    target_key = (
        spec.start_timestamp_key
        if spec.endpoint_policy == "completion_to_start"
        else spec.trace_spec.timestamp_key
    )
    for trace in log.traces:
        for position, (source, target) in enumerate(
            zip(trace.events, trace.events[1:])
        ):
            source_time, source_codes = _timestamp(
                log, source, spec.trace_spec.timestamp_key, "source"
            )
            target_time, target_codes = _timestamp(log, target, target_key, "target")
            codes = source_codes + target_codes
            activities: list[str | None] = []
            for prefix, event in (("source", source), ("target", target)):
                try:
                    activities.append(_activity(log, event, spec.trace_spec))
                except ValueError:
                    activities.append(None)
                    codes += (f"{prefix}_invalid_activity",)
            duration = None
            if source_time is not None and target_time is not None:
                observed = _seconds(source_time, target_time)
                if observed < 0:
                    codes += ("negative_adjacent_interval",)
                else:
                    duration = observed
            identity = _identifier(
                "adjacent-interval",
                digest,
                trace.id,
                source.id,
                target.id,
                spec.endpoint_policy,
                target_key,
            )
            intervals.append(
                AdjacentInterval(
                    identity,
                    trace.id,
                    source.id,
                    target.id,
                    activities[0],
                    activities[1],
                    position,
                    position + 1,
                    source_time,
                    target_time,
                    duration,
                    codes,
                )
            )
            issues.extend(
                ComputeIssue(
                    code,
                    "Adjacent interval has incomplete or incompatible evidence",
                    ("trace", trace.id, "interval", identity),
                )
                for code in codes
            )
    value = AdjacentIntervals(
        tuple(trace.id for trace in log.traces),
        sum(len(trace.events) for trace in log.traces),
        tuple(intervals),
    )
    return _derived_result(
        operator,
        digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.lifecycle.pair": (
        "lifecycle_pairing",
        LifecycleSpec,
        LifecyclePairing,
    ),
    "pix.case_centric.lifecycle.adjacent_intervals": (
        "adjacent_intervals",
        AdjacentIntervalSpec,
        AdjacentIntervals,
    ),
}

__all__ = [
    "LifecycleSpec",
    "LifecycleInterval",
    "UnmatchedLifecycleEvent",
    "LifecyclePairing",
    "pair_lifecycle_events",
    "restore_lifecycle_events",
    "AdjacentIntervalSpec",
    "AdjacentInterval",
    "AdjacentIntervals",
    "derive_adjacent_intervals",
]
