"""Evidence-preserving object-centric performance without inferred token clocks.

The default profile measures observed, qualified per-object predecessor times.
``ocpa_eog_1_3_4`` preserves the published EOG formulas (including its local
``elapsed``/``remaining`` meanings), but fixes readiness's activity selection and
represents missing typed inputs as unknown instead of raising or inventing zero.
Neither EOG profile is token replay. ``measure_replay_performance`` separately
propagates explicit clocks over native joint replay's token witnesses.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.trace import _traces
from pix.contracts.analysis import E2OEvidence, TraceSpec, _selection, _text
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.ocel import OCEL

PERFORMANCE_OPERATOR_ID = "pix.object_centric.measure_performance"
_METRICS = frozenset(
    (
        "flow",
        "sojourn",
        "synchronization",
        "pooling",
        "lagging",
        "readiness",
        "elapsed",
        "remaining",
        "service",
        "ready_waiting",
        "first_input_waiting",
        "object_frequency",
        "activity_frequency",
    )
)
_TYPED = frozenset(
    (
        "pooling",
        "lagging",
        "readiness",
        "elapsed",
        "remaining",
        "object_frequency",
        "activity_frequency",
    )
)
_START_METRICS = frozenset(("service", "ready_waiting", "first_input_waiting"))


@dataclass(frozen=True, slots=True)
class OCPerformanceSpec:
    """Select formulas and populations explicitly.

    ``object_type`` scopes typed metrics, not the complete incoming EOG. A
    predecessor of another type still contributes to synchronization and flow.
    ``elapsed``/``remaining`` in the default profile use the first/last observed
    event of each selected object; they do not estimate creation or termination.
    With the OCPA profile these are event-level immediate-neighbour gaps.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    metrics: tuple[str, ...] = ("flow", "sojourn", "synchronization")
    object_type: str | None = None
    activities: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    start_attribute: str | None = None
    profile: Literal["object_predecessor", "ocpa_eog_1_3_4", "opera"] = (
        "object_predecessor"
    )

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, tuple) or not self.metrics:
            raise ValueError("metrics must be a nonempty tuple")
        for metric in self.metrics:
            _text(metric, "metric")
            if metric not in _METRICS:
                raise ValueError(f"unknown metric: {metric}")
        object.__setattr__(self, "metrics", tuple(sorted(set(self.metrics))))
        if self.object_type is not None:
            _text(self.object_type, "object_type")
        if _TYPED.intersection(self.metrics) and self.object_type is None:
            raise ValueError("typed metrics require an explicit object_type")
        if self.activities is not None:
            if not isinstance(self.activities, tuple):
                raise TypeError("activities must be a tuple or None")
            for activity in self.activities:
                _text(activity, "activity")
            object.__setattr__(self, "activities", tuple(sorted(set(self.activities))))
        _selection(self)
        if self.start_attribute is not None:
            _text(self.start_attribute, "start_attribute")
        if self.profile not in ("object_predecessor", "ocpa_eog_1_3_4", "opera"):
            raise ValueError("unknown performance profile")


@dataclass(frozen=True, slots=True)
class OCPerformanceEvidence:
    """A timestamp observation and the exact object relations supporting it.

    ``kind`` distinguishes actual immediate object neighbours from lifecycle
    boundaries. A lifecycle observation is not an arrival of a model token.
    """

    kind: str
    object_id: str
    object_type: str
    source_event_id: str
    target_event_id: str
    source_time: datetime
    target_time: datetime
    source_relations: tuple[E2OEvidence, ...]
    target_relations: tuple[E2OEvidence, ...]


@dataclass(frozen=True, slots=True)
class OCPerformanceSample:
    metric: str
    unit: Literal["microseconds", "count"]
    event_id: str | None
    object_id: str | None
    object_type: str | None
    value: int | None
    reason: str | None
    completion_time: datetime | None
    explicit_start_time: datetime | None
    related_object_ids: tuple[str, ...]
    reference_event_ids: tuple[str, ...]
    evidence: tuple[OCPerformanceEvidence, ...]
    type_selection_relations: tuple[E2OEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class OCPerformanceSummary:
    """Exact mean over known samples; unknown population stays in the result."""

    metric: str
    unit: Literal["microseconds", "count"]
    population_count: int
    known_count: int
    unknown_count: int
    total: int
    minimum: int | None
    maximum: int | None
    mean_numerator: int | None
    mean_denominator: int | None
    samples: tuple[OCPerformanceSample, ...]


@dataclass(frozen=True, slots=True)
class OCPerformance:
    profile: str
    object_type: str | None
    selected_event_ids: tuple[str, ...]
    summaries: tuple[OCPerformanceSummary, ...]


RESULT_SCHEMAS = {
    PERFORMANCE_OPERATOR_ID: (
        "object-centric-performance",
        OCPerformanceSpec,
        OCPerformance,
    ),
}


def _us(delta: timedelta) -> int:
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _summarize(metric: str, samples: list[OCPerformanceSample]) -> OCPerformanceSummary:
    values = [sample.value for sample in samples if sample.value is not None]
    total = sum(values)
    return OCPerformanceSummary(
        metric,
        "count" if metric.endswith("frequency") else "microseconds",
        len(samples),
        len(values),
        len(samples) - len(values),
        total,
        min(values) if values else None,
        max(values) if values else None,
        total if values else None,
        len(values) if values else None,
        tuple(samples),
    )


def measure_performance(
    log: OCEL | ComputationContext,
    spec: OCPerformanceSpec = OCPerformanceSpec(),
) -> ComputationResult[OCPerformance]:
    """Measure observed EOG/lifecycle times, explicit service, and frequencies.

    All durations are exact integer microseconds, including mean numerators.
    For observed predecessor completion times A, completion C and start S:
    flow=C-min(A), sojourn=C-max(A), synchronization=max(A)-min(A),
    service=C-S, ready_waiting=S-max(A), first_input_waiting=S-min(A).
    Typed arrival subset T gives pooling=max(T)-min(T), lagging=max(T)-min(A),
    readiness=min(T)-min(A). No observed predecessor means unknown in the
    default profile; the explicit OCPA profile uses its boundary-zero convention.

    Typed default arrival evidence must actually share that object with this
    event. OCPA's profile instead chooses predecessor events participating in
    that type anywhere, which can select a different timestamp population.
    Unknown inputs are retained as rows and excluded only from known means.
    Negative start-derived durations are unknown, not clipped to zero.
    """
    if not isinstance(spec, OCPerformanceSpec):
        raise TypeError("spec must be OCPerformanceSpec")
    context, input_issues = _prepare(log)
    if context is None:
        return _result(
            PERFORMANCE_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            input_issues,
        )
    if spec.object_type is not None and spec.object_type not in context.objects_by_type:
        return _result(
            PERFORMANCE_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "unknown_object_type",
                    "Selected object type is not declared",
                    ("object_type", spec.object_type),
                ),
            ),
        )
    if spec.profile == "opera":
        return _result(
            PERFORMANCE_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "unsupported_timed_token_replay_profile",
                    "Use measure_replay_performance with a native joint replay witness; "
                    "observed EOG neighbours cannot replace token consumption",
                ),
            ),
        )

    selected = tuple(
        sorted(
            event.id
            for event in context.log.events
            if spec.activities is None or event.type in spec.activities
        )
    )
    selected_set = frozenset(selected)
    incoming: dict[str, list[OCPerformanceEvidence]] = {
        e: [] for e in context.events_by_id
    }
    outgoing: dict[str, list[OCPerformanceEvidence]] = {
        e: [] for e in context.events_by_id
    }
    traces = {}
    observations = {}
    issues: list[ComputeIssue] = []
    independent_metrics = {"service", "object_frequency", "activity_frequency"}
    needs_order = any(metric not in independent_metrics for metric in spec.metrics)
    ambiguous_graph = False
    allowed = None if spec.qualifiers is None else frozenset(spec.qualifiers)
    relations = {
        event_id: tuple(
            E2OEvidence(r.event, r.object, r.qualifier)
            for r in records
            if allowed is None or r.qualifier in allowed
        )
        for event_id, records in context.e2o_by_event.items()
    }
    for object_type in sorted(context.objects_by_type) if needs_order else ():
        result, trace_issues = _traces(
            context, TraceSpec(object_type, spec.qualifiers, spec.tie_policy)
        )
        issues.extend(trace_issues)
        if result is None:
            ambiguous_graph = True
            continue
        for trace in result.traces:
            traces[trace.object_id] = trace
            observations[trace.object_id] = {e.event_id: e for e in trace.events}
            for first, second in zip(trace.events, trace.events[1:]):
                evidence = OCPerformanceEvidence(
                    "object_predecessor",
                    trace.object_id,
                    trace.object_type,
                    first.event_id,
                    second.event_id,
                    first.time,
                    second.time,
                    first.relations,
                    second.relations,
                )
                incoming[second.event_id].append(evidence)
                outgoing[first.event_id].append(evidence)

    if ambiguous_graph and not independent_metrics.intersection(spec.metrics):
        return _result(
            PERFORMANCE_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(issues),
        )

    samples: dict[str, list[OCPerformanceSample]] = {
        metric: [] for metric in spec.metrics
    }

    def record(
        metric,
        event_id,
        value,
        reason=None,
        *,
        object_id=None,
        evidence=(),
        reference_ids=(),
        object_ids=(),
        start=None,
        type_relations=(),
    ):
        event = context.events_by_id[event_id] if event_id is not None else None
        samples[metric].append(
            OCPerformanceSample(
                metric,
                "count" if metric.endswith("frequency") else "microseconds",
                event_id,
                object_id,
                spec.object_type if metric in _TYPED else None,
                value,
                reason,
                event.time if event else None,
                start,
                tuple(sorted(set(object_ids))),
                tuple(sorted(set(reference_ids))),
                tuple(evidence),
                tuple(
                    sorted(
                        set(type_relations),
                        key=lambda r: (r.event, r.object, r.qualifier),
                    )
                ),
            )
        )
        if reason is not None:
            issues.append(
                ComputeIssue(
                    reason,
                    f"{metric} has no valid sample for this population member",
                    (
                        "metric",
                        metric,
                        "event",
                        event_id or "",
                        "object",
                        object_id or "",
                    ),
                )
            )

    for event_id in selected:
        event = context.events_by_id[event_id]
        arrivals = tuple(incoming[event_id])
        arrival_times = [e.source_time for e in arrivals]
        arrival_ids = tuple(e.source_event_id for e in arrivals)
        event_objects = tuple(sorted({r.object for r in relations[event_id]}))
        typed_objects = tuple(
            o
            for o in event_objects
            if context.objects_by_id[o].type == spec.object_type
        )
        if spec.profile == "ocpa_eog_1_3_4":
            typed_ids = {
                source_id
                for source_id in arrival_ids
                if any(
                    context.objects_by_id[r.object].type == spec.object_type
                    for r in relations[source_id]
                )
            }
            typed_times = [context.events_by_id[i].time for i in sorted(typed_ids)]
            type_relations = tuple(
                r
                for i in sorted(typed_ids)
                for r in relations[i]
                if context.objects_by_id[r.object].type == spec.object_type
            )
        else:
            typed_ids = {
                e.source_event_id for e in arrivals if e.object_type == spec.object_type
            }
            typed_times = [
                e.source_time for e in arrivals if e.object_type == spec.object_type
            ]
            type_relations = tuple(
                r
                for e in arrivals
                if e.object_type == spec.object_type
                for r in e.source_relations
            )

        start = None
        start_reason = None
        if _START_METRICS.intersection(spec.metrics):
            candidate = next(
                (a.value for a in event.attributes if a.name == spec.start_attribute),
                None,
            )
            if spec.start_attribute is None:
                start_reason = "start_attribute_not_selected"
            elif candidate is None:
                start_reason = "missing_start_timestamp"
            elif not isinstance(candidate, datetime):
                start_reason = "invalid_start_timestamp"
            else:
                start = candidate
                if start > event.time:
                    start_reason = "start_after_completion"

        for metric in spec.metrics:
            if metric == "activity_frequency":
                continue
            if metric == "object_frequency":
                record(
                    metric,
                    event_id,
                    len(typed_objects),
                    object_ids=typed_objects,
                    reference_ids=(event_id,),
                )
                continue
            if ambiguous_graph and metric not in independent_metrics:
                if (
                    metric in ("elapsed", "remaining")
                    and spec.profile == "object_predecessor"
                ):
                    for object_id in typed_objects:
                        record(
                            metric,
                            event_id,
                            None,
                            "ambiguous_event_order",
                            object_id=object_id,
                            object_ids=(object_id,),
                        )
                else:
                    record(
                        metric,
                        event_id,
                        None,
                        "ambiguous_event_order",
                        object_ids=event_objects,
                    )
                continue
            if (
                metric in ("elapsed", "remaining")
                and spec.profile == "object_predecessor"
            ):
                for object_id in typed_objects:
                    trace = traces[object_id]
                    boundary = (
                        trace.events[0] if metric == "elapsed" else trace.events[-1]
                    )
                    observation = observations[object_id][event_id]
                    first, last = (
                        (boundary, observation)
                        if metric == "elapsed"
                        else (observation, boundary)
                    )
                    ev = OCPerformanceEvidence(
                        "observed_lifecycle_first"
                        if metric == "elapsed"
                        else "observed_lifecycle_last",
                        object_id,
                        trace.object_type,
                        first.event_id,
                        last.event_id,
                        first.time,
                        last.time,
                        first.relations,
                        last.relations,
                    )
                    record(
                        metric,
                        event_id,
                        _us(last.time - first.time),
                        object_id=object_id,
                        object_ids=(object_id,),
                        reference_ids=(boundary.event_id,),
                        evidence=(ev,),
                    )
                continue

            evidence = arrivals
            ref_ids = arrival_ids
            value = None
            reason = None
            if metric in _START_METRICS and start_reason is not None:
                reason = start_reason
            elif metric == "service":
                value = _us(event.time - start)
                evidence, ref_ids = (), ()
            elif metric == "remaining":
                evidence = tuple(outgoing[event_id])
                ref_ids = tuple(e.target_event_id for e in evidence)
                value = (
                    _us(max(e.target_time for e in evidence) - event.time)
                    if evidence
                    else 0
                )
            elif not arrival_times:
                if spec.profile == "ocpa_eog_1_3_4" and metric not in _START_METRICS:
                    value = 0
                else:
                    reason = "no_observed_predecessor"
            elif metric in ("pooling", "lagging", "readiness") and not typed_times:
                reason = "no_typed_predecessor"
            else:
                earliest, latest = min(arrival_times), max(arrival_times)
                if metric == "flow":
                    value = _us(event.time - earliest)
                elif metric in ("sojourn", "elapsed"):
                    value = _us(event.time - latest)
                elif metric == "synchronization":
                    value = _us(latest - earliest)
                elif metric == "pooling":
                    value = _us(max(typed_times) - min(typed_times))
                    ref_ids = tuple(sorted(typed_ids))
                elif metric == "lagging":
                    value = _us(max(typed_times) - earliest)
                elif metric == "readiness":
                    value = _us(min(typed_times) - earliest)
                elif metric == "ready_waiting":
                    value = _us(start - latest)
                elif metric == "first_input_waiting":
                    value = _us(start - earliest)
                if value is not None and value < 0:
                    value, reason = None, "start_before_observed_input"
            record(
                metric,
                event_id,
                value,
                reason,
                evidence=evidence,
                reference_ids=ref_ids,
                object_ids=event_objects,
                start=start if metric in _START_METRICS else None,
                type_relations=type_relations
                if metric in ("pooling", "lagging", "readiness")
                else (),
            )

    if "activity_frequency" in spec.metrics:
        for obj in context.objects_by_type[spec.object_type]:
            ids = tuple(
                sorted(
                    {
                        r.event
                        for r in context.e2o_by_object[obj.id]
                        if r.event in selected_set
                        and (allowed is None or r.qualifier in allowed)
                    }
                )
            )
            record(
                "activity_frequency",
                None,
                len(ids),
                object_id=obj.id,
                object_ids=(obj.id,),
                reference_ids=ids,
            )
    summaries = tuple(_summarize(metric, samples[metric]) for metric in spec.metrics)
    status = (
        ComputeStatus.PARTIAL
        if any(s.unknown_count for s in summaries)
        else ComputeStatus.COMPUTED
    )
    return _result(
        PERFORMANCE_OPERATOR_ID,
        context,
        spec,
        status,
        OCPerformance(spec.profile, spec.object_type, selected, summaries),
        tuple(issues),
    )


__all__ = (
    "PERFORMANCE_OPERATOR_ID",
    "OCPerformanceSpec",
    "OCPerformanceEvidence",
    "OCPerformanceSample",
    "OCPerformanceSummary",
    "OCPerformance",
    "measure_performance",
)


REPLAY_PERFORMANCE_OPERATOR_ID = "pix.object_centric.measure_replay_performance"


@dataclass(frozen=True, slots=True)
class OCReplayPerformanceSpec:
    """Timed-token semantics, not the historical OCPA token-visit heuristic.

    FIFO distinguishes repeated identical place/object tokens by production
    order. Silent transitions are assigned zero duration: their production time
    is max(all input times), and is unknown if any input time is unknown.
    ``ocpa_opera_1_3_4`` selects the published arithmetic, not its faulty visit
    matching. OPERA waiting is first-input waiting; use ready_waiting explicitly
    for the time after all model inputs are available.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    metrics: tuple[str, ...] = ("flow", "sojourn", "synchronization")
    object_type: str | None = None
    activities: tuple[str, ...] | None = None
    start_attribute: str | None = None
    profile: Literal["token_arrivals", "ocpa_opera_1_3_4"] = "token_arrivals"
    token_selection: Literal["fifo_production"] = "fifo_production"
    silent_policy: Literal["zero_duration_max_input"] = "zero_duration_max_input"

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, tuple):
            raise TypeError("metrics must be a tuple")
        base = OCPerformanceSpec(
            metrics=tuple(
                "first_input_waiting" if m == "waiting" else m for m in self.metrics
            ),
            object_type=self.object_type,
            activities=self.activities,
            start_attribute=self.start_attribute,
        )
        if any(
            m in ("elapsed", "remaining", "object_frequency", "activity_frequency")
            for m in self.metrics
        ):
            raise ValueError(
                "replay timing supports input/service metrics, not lifecycle/frequency metrics"
            )
        if self.profile not in ("token_arrivals", "ocpa_opera_1_3_4"):
            raise ValueError("unknown replay timing profile")
        if "waiting" in self.metrics and self.profile != "ocpa_opera_1_3_4":
            raise ValueError("select ready_waiting or first_input_waiting explicitly")
        if "readiness" in self.metrics and self.profile == "ocpa_opera_1_3_4":
            raise ValueError(
                "OPERA has no readiness metric; choose token_arrivals profile"
            )
        if (
            self.token_selection != "fifo_production"
            or self.silent_policy != "zero_duration_max_input"
        ):
            raise ValueError("unsupported token timing policy")
        object.__setattr__(self, "metrics", tuple(sorted(set(self.metrics))))
        object.__setattr__(self, "activities", base.activities)


@dataclass(frozen=True, slots=True)
class OCTokenArrival:
    token_serial: int
    place_id: str
    object_id: str
    object_type: str
    arrival_time: datetime | None
    origin: Literal["initial", "injected", "visible", "silent"]
    produced_step: int
    source_event_ids: tuple[str, ...]
    unknown_reason: str | None


@dataclass(frozen=True, slots=True)
class OCTokenInputs:
    event_id: str
    step_index: int | None
    arrivals: tuple[OCTokenArrival, ...]
    known_count: int
    unknown_count: int
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OCReplayPerformance:
    model_digest: str
    replay_status: str
    profile: str
    token_selection: str
    silent_policy: str
    measurements: OCPerformance
    token_inputs: tuple[OCTokenInputs, ...]


def measure_replay_performance(
    log: OCEL | ComputationContext,
    replay: ComputationResult,
    spec: OCReplayPerformanceSpec = OCReplayPerformanceSpec(),
) -> ComputationResult[OCReplayPerformance]:
    """Propagate a clock ledger over concrete replay consumption/production.

    Initial and inserted tokens never receive invented arrival times. Visible
    production uses the event's observed completion, even after repaired input;
    that observation does not certify an upstream fitting execution. Every
    self-loop consumes old tokens before producing replacement tokens. Limited
    replay retains unprocessed requested events as unknown population members.
    Source/request identities and token multiset continuity are checked. This
    validates the supplied witness, not its optimality or OCPA runtime parity.
    Default sojourn=C-max(A), flow=C-min(A). The explicit OCPA profile instead
    uses sojourn=C-min(A), flow=C-min(A)+max(A)-min(A), waiting=S-min(A), and
    typed lagging=max(A_type)-min(A_other_types). Negative results are unknown.
    """
    from pix.object_centric.conformance import (
        OBJECT_TOKEN_REPLAY_OPERATOR_ID,
        ObjectReplay,
    )

    if not isinstance(spec, OCReplayPerformanceSpec):
        raise TypeError("spec must be OCReplayPerformanceSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            REPLAY_PERFORMANCE_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    if not isinstance(replay, ComputationResult):
        raise TypeError("replay must be a ComputationResult")
    parents = (replay.computation_id,) if replay.computation_id else ()

    def unavailable(code, message, *, index=None):
        return _result(
            REPLAY_PERFORMANCE_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    code, message, () if index is None else ("step", str(index))
                ),
            ),
            parent_computation_ids=parents,
        )

    if replay.operator_id != OBJECT_TOKEN_REPLAY_OPERATOR_ID or not isinstance(
        replay.value, ObjectReplay
    ):
        return unavailable(
            "unsupported_replay_witness",
            "A native joint ObjectReplay payload is required",
        )
    if replay.source_digest != context.source_digest:
        return unavailable(
            "replay_source_mismatch", "Replay and OCEL source identities differ"
        )
    expected = computation_identity(
        replay.operator_id,
        replay.operator_version,
        replay.source_digest,
        replay.spec,
        replay.parent_computation_ids,
    )
    if expected != replay.computation_id:
        return unavailable(
            "replay_identity_mismatch", "Replay request identity is inconsistent"
        )
    if spec.object_type is not None and spec.object_type not in context.objects_by_type:
        return unavailable(
            "unknown_object_type", "Selected object type is not declared"
        )
    data = replay.value
    if data.model_digest != getattr(replay.spec, "model_digest", None):
        return unavailable(
            "invalid_replay_witness", "Replay model identity differs from its request"
        )
    if set(e.event_id for e in data.scope.events) != set(context.events_by_id):
        return unavailable(
            "invalid_replay_witness",
            "Whole-log replay event coverage does not match source",
        )
    if not data.steps or data.steps[0].kind != "initial":
        return unavailable(
            "invalid_replay_witness",
            "Replay must start with its initial marking witness",
        )

    ledger = defaultdict(deque)
    inputs = {}
    serial = 0

    def marking():
        return Counter({token: len(queue) for token, queue in ledger.items() if queue})

    for index, step in enumerate(data.steps):
        if step.kind not in (
            "initial",
            "visible",
            "silent",
            "log_deviation",
            "finalize",
        ):
            return unavailable(
                "invalid_replay_witness", "Unknown replay step kind", index=index
            )
        if marking() != Counter(step.marking_before):
            return unavailable(
                "invalid_replay_witness",
                "Token ledger differs from before marking",
                index=index,
            )
        if step.kind == "initial" and index != 0:
            return unavailable(
                "invalid_replay_witness", "Repeated initial step", index=index
            )
        for token in step.inserted_tokens:
            if token.object_id not in context.objects_by_id:
                return unavailable(
                    "invalid_replay_witness", "Unknown inserted object", index=index
                )
            ledger[token].append(
                OCTokenArrival(
                    serial,
                    token.place_id,
                    token.object_id,
                    context.objects_by_id[token.object_id].type,
                    None,
                    "injected",
                    index,
                    (),
                    "injected_token_time_unknown",
                )
            )
            serial += 1
        consumed = []
        for token in step.consumed_tokens:
            if not ledger[token]:
                return unavailable(
                    "invalid_replay_witness",
                    "Consumed token is absent from ledger",
                    index=index,
                )
            consumed.append(ledger[token].popleft())
        event = (
            context.events_by_id.get(step.event_id)
            if step.event_id is not None
            else None
        )
        if step.kind in ("visible", "log_deviation"):
            if event is None or event.id in inputs:
                return unavailable(
                    "invalid_replay_witness",
                    "Unknown or repeated observed event",
                    index=index,
                )
            inputs[event.id] = OCTokenInputs(
                event.id,
                index,
                tuple(consumed),
                sum(t.arrival_time is not None for t in consumed),
                sum(t.arrival_time is None for t in consumed),
                "log_deviation_without_token_inputs"
                if step.kind == "log_deviation"
                else None,
            )
        if step.kind == "visible":
            production_time, origin, source_ids, reason = (
                event.time,
                "visible",
                (event.id,),
                None,
            )
        elif step.kind == "silent":
            production_time = (
                max(t.arrival_time for t in consumed)
                if consumed and all(t.arrival_time is not None for t in consumed)
                else None
            )
            origin = "silent"
            source_ids = tuple(
                sorted({e for t in consumed for e in t.source_event_ids})
            )
            reason = (
                None if production_time is not None else "silent_input_time_unknown"
            )
        else:
            production_time, origin, source_ids, reason = (
                None,
                "initial",
                (),
                "initial_token_time_unknown",
            )
        for token in step.produced_tokens:
            if token.object_id not in context.objects_by_id:
                return unavailable(
                    "invalid_replay_witness", "Unknown produced object", index=index
                )
            ledger[token].append(
                OCTokenArrival(
                    serial,
                    token.place_id,
                    token.object_id,
                    context.objects_by_id[token.object_id].type,
                    production_time,
                    origin,
                    index,
                    source_ids,
                    reason,
                )
            )
            serial += 1
        if marking() != Counter(step.marking_after):
            return unavailable(
                "invalid_replay_witness",
                "Token ledger differs from after marking",
                index=index,
            )
    if marking() != Counter(data.ending_marking):
        return unavailable(
            "invalid_replay_witness", "Ending marking differs from final ledger"
        )
    if len(inputs) != data.processed_event_count:
        return unavailable(
            "invalid_replay_witness", "Processed event count differs from witness"
        )
    expected_counts = (
        sum(len(s.inserted_tokens) for s in data.steps),
        sum(marking().values()),
        sum(len(s.consumed_tokens) for s in data.steps),
        sum(len(s.produced_tokens) for s in data.steps),
    )
    if expected_counts != (
        data.counts.missing,
        data.counts.remaining,
        data.counts.consumed,
        data.counts.produced,
    ):
        return unavailable(
            "invalid_replay_witness", "Token counters differ from witness"
        )
    if data.status == "completed" and set(inputs) != set(context.events_by_id):
        return unavailable(
            "invalid_replay_witness", "Completed replay omits source events"
        )

    selected = tuple(
        sorted(
            e.id
            for e in context.log.events
            if spec.activities is None or e.type in spec.activities
        )
    )
    samples = {metric: [] for metric in spec.metrics}
    output_inputs = []
    output_issues = list(replay.issues)
    if data.status == "limited":
        output_issues.append(
            ComputeIssue(
                "replay_incomplete", "Timed results cover only the replay prefix"
            )
        )
    for event_id in selected:
        event = context.events_by_id[event_id]
        observed = inputs.get(
            event_id, OCTokenInputs(event_id, None, (), 0, 0, "event_not_replayed")
        )
        output_inputs.append(observed)
        arrivals = observed.arrivals
        times = [t.arrival_time for t in arrivals if t.arrival_time is not None]
        typed = [
            t.arrival_time
            for t in arrivals
            if t.object_type == spec.object_type and t.arrival_time is not None
        ]
        other = [
            t.arrival_time
            for t in arrivals
            if t.object_type != spec.object_type and t.arrival_time is not None
        ]
        start = next(
            (a.value for a in event.attributes if a.name == spec.start_attribute), None
        )
        for metric in spec.metrics:
            value = None
            reason = observed.reason
            needs_start = metric in _START_METRICS or metric == "waiting"
            if reason is None and needs_start:
                if spec.start_attribute is None:
                    reason = "start_attribute_not_selected"
                elif start is None:
                    reason = "missing_start_timestamp"
                elif not isinstance(start, datetime):
                    reason = "invalid_start_timestamp"
                elif start > event.time:
                    reason = "start_after_completion"
            if reason is None and metric == "service":
                value = _us(event.time - start)
            elif reason is None:
                relevant = (
                    tuple(t for t in arrivals if t.object_type == spec.object_type)
                    if metric == "pooling"
                    else arrivals
                )
                relevant_times = [
                    t.arrival_time for t in relevant if t.arrival_time is not None
                ]
                if any(t.arrival_time is None for t in relevant):
                    reason = "token_input_time_unknown"
                elif not relevant:
                    reason = (
                        "no_typed_token_inputs"
                        if metric == "pooling"
                        else "no_token_inputs"
                    )
                elif not times:
                    reason = "no_token_inputs"
                elif max(relevant_times) > event.time:
                    reason = "token_arrival_after_completion"
                elif metric in ("pooling", "lagging", "readiness") and not typed:
                    reason = "no_typed_token_inputs"
                elif (
                    metric == "lagging"
                    and spec.profile == "ocpa_opera_1_3_4"
                    and not other
                ):
                    reason = "no_other_type_token_inputs"
                else:
                    earliest, latest = min(times), max(times)
                    opera = spec.profile == "ocpa_opera_1_3_4"
                    if metric == "flow":
                        value = _us(event.time - earliest) + (
                            _us(latest - earliest) if opera else 0
                        )
                    elif metric == "sojourn":
                        value = _us(event.time - (earliest if opera else latest))
                    elif metric == "synchronization":
                        value = _us(latest - earliest)
                    elif metric == "pooling":
                        value = _us(max(typed) - min(typed))
                    elif metric == "lagging":
                        value = _us(max(typed) - (min(other) if opera else earliest))
                    elif metric == "readiness":
                        value = _us(min(typed) - earliest)
                    elif metric == "ready_waiting":
                        value = _us(start - latest)
                    elif metric in ("first_input_waiting", "waiting"):
                        value = _us(start - earliest)
                    if value is not None and value < 0:
                        value, reason = None, "negative_timed_metric"
            samples[metric].append(
                OCPerformanceSample(
                    metric,
                    "microseconds",
                    event_id,
                    None,
                    spec.object_type if metric in _TYPED else None,
                    value,
                    reason,
                    event.time,
                    start if needs_start and isinstance(start, datetime) else None,
                    tuple(sorted({t.object_id for t in arrivals})),
                    tuple(sorted({e for t in arrivals for e in t.source_event_ids})),
                    (),
                )
            )
            if reason is not None:
                output_issues.append(
                    ComputeIssue(
                        reason,
                        f"{metric} has no valid timed-token sample",
                        ("event", event_id, "metric", metric),
                    )
                )
    measurements = OCPerformance(
        spec.profile,
        spec.object_type,
        selected,
        tuple(_summarize(m, samples[m]) for m in spec.metrics),
    )
    payload = OCReplayPerformance(
        data.model_digest,
        data.status,
        spec.profile,
        spec.token_selection,
        spec.silent_policy,
        measurements,
        tuple(output_inputs),
    )
    status = (
        ComputeStatus.PARTIAL
        if data.status == "limited"
        or any(summary.unknown_count for summary in measurements.summaries)
        else ComputeStatus.COMPUTED
    )
    return _result(
        REPLAY_PERFORMANCE_OPERATOR_ID,
        context,
        spec,
        status,
        payload,
        tuple(output_issues),
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS[REPLAY_PERFORMANCE_OPERATOR_ID] = (
    "object-centric-replay-performance",
    OCReplayPerformanceSpec,
    OCReplayPerformance,
)
__all__ += (
    "OCReplayPerformanceSpec",
    "OCTokenArrival",
    "OCTokenInputs",
    "OCReplayPerformance",
    "REPLAY_PERFORMANCE_OPERATOR_ID",
    "measure_replay_performance",
)
