"""Native case statistics with source-order and observed-time contracts.

Sequence relations use recorded order, including equal/decreasing timestamps.
Time measurements require timezone-aware observations and never repair order.
Missing observations are represented by coverage and None, never invented zero.
No reference library is imported or executed by these calculations.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from itertools import combinations
from statistics import mean, pstdev
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseLog, case_log_digest, case_traces


def _trace_spec(value: object) -> None:
    if not isinstance(value, CaseTraceSpec):
        raise TypeError("trace_spec must be CaseTraceSpec")


def _positive(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class StatisticsSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    eventually_mode: str = "all_pairs"
    max_relation_pairs: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.eventually_mode not in ("all_pairs", "first_per_source_activity"):
            raise ValueError("unsupported eventually_mode")
        _positive(self.max_relation_pairs, "max_relation_pairs")


@dataclass(frozen=True, slots=True)
class ActivityStatistics:
    activity: str
    event_count: int
    case_ids: tuple[str, ...]
    start_case_ids: tuple[str, ...]
    end_case_ids: tuple[str, ...]
    rework_case_ids: tuple[str, ...]
    repeated_event_count: int
    positions: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class CaseVariant:
    activities: tuple[str, ...]
    case_ids: tuple[str, ...]
    count: int
    probability: float
    cumulative_coverage: float


@dataclass(frozen=True, slots=True)
class RelationWitness:
    case_id: str
    source_event_id: str
    target_event_id: str


@dataclass(frozen=True, slots=True)
class SequenceRelation:
    source: str
    target: str
    occurrence_count: int
    case_count: int
    witnesses: tuple[RelationWitness, ...]


@dataclass(frozen=True, slots=True)
class SelfDistance:
    activity: str
    distance: int | None
    intervening_activities: tuple[str, ...]
    witnesses: tuple[RelationWitness, ...]


@dataclass(frozen=True, slots=True)
class CaseStatistics:
    case_count: int
    event_count: int
    empty_case_ids: tuple[str, ...]
    activities: tuple[ActivityStatistics, ...]
    variants: tuple[CaseVariant, ...]
    directly_follows: tuple[SequenceRelation, ...]
    eventually_follows: tuple[SequenceRelation, ...]
    minimum_self_distances: tuple[SelfDistance, ...]


def _finish(parent, operator, spec, value=None, issues=(), failed=False):
    if parent.status is not ComputeStatus.COMPUTED:
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            parent.status,
            None,
            parent.issues,
            parent_computation_ids=(parent.computation_id,),
        )
    return _derived_result(
        operator,
        parent.source_digest,
        spec,
        ComputeStatus.UNAVAILABLE
        if failed
        else (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        parent.issues + tuple(issues),
        parent_computation_ids=(parent.computation_id,),
    )


def _finish_facts(log, operator, spec, value=None, issues=(), failed=False):
    """Attribute calculations have source provenance, not a fake trace parent."""
    return _derived_result(
        operator,
        case_log_digest(log),
        spec,
        ComputeStatus.UNAVAILABLE
        if failed
        else (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        tuple(issues),
    )


def _relations(mapping):
    return tuple(
        SequenceRelation(a, b, len(w), len({x.case_id for x in w}), tuple(w))
        for (a, b), w in sorted(mapping.items())
    )


def measure_statistics(
    log: CaseLog, spec: StatisticsSpec = StatisticsSpec()
) -> ComputationResult[CaseStatistics]:
    """Count complete activity tuples, including empty cases in probabilities.

    Eventually-follows uses i < j. ``first_per_source_activity`` retains the first
    later occurrence of each activity for each source event. These are sequence
    profiles, not the reference library's timestamp-sorted interval relation.
    """
    if not isinstance(spec, StatisticsSpec):
        raise TypeError("spec must be StatisticsSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.measure_statistics"
    if parent.value is None:
        return _finish(parent, operator, spec)
    traces = parent.value.traces
    relation_budget = sum(len(t.events) * (len(t.events) - 1) // 2 for t in traces)
    if relation_budget > spec.max_relation_pairs:
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "relation_limit",
                    "Sequence-pair enumeration exceeds max_relation_pairs; no partial counts returned.",
                ),
            ),
            failed=True,
        )
    counts, starts, ends, cases, reworks = (defaultdict(list) for _ in range(5))
    positions, repeats = defaultdict(Counter), Counter()
    variants, direct, eventual = (defaultdict(list) for _ in range(3))
    distances, middle, self_witness = {}, defaultdict(set), defaultdict(list)
    for trace in traces:
        events = trace.events
        labels = tuple(e.activity for e in events)
        variants[labels].append(trace.object_id)
        frequency = Counter(labels)
        for activity, count in frequency.items():
            cases[activity].append(trace.object_id)
            if count > 1:
                reworks[activity].append(trace.object_id)
                repeats[activity] += count - 1
        if events:
            starts[labels[0]].append(trace.object_id)
            ends[labels[-1]].append(trace.object_id)
        previous = {}
        for i, event in enumerate(events):
            activity = event.activity
            counts[activity].append(event.event_id)
            positions[activity][i] += 1
            if activity in previous:
                p = previous[activity]
                distance = i - p - 1
                old = distances.get(activity)
                if old is None or distance < old:
                    distances[activity] = distance
                    middle[activity].clear()
                    self_witness[activity].clear()
                if distance == distances[activity]:
                    middle[activity].update(labels[p + 1 : i])
                    self_witness[activity].append(
                        RelationWitness(
                            trace.object_id, events[p].event_id, event.event_id
                        )
                    )
            previous[activity] = i
            seen = set()
            for j in range(i + 1, len(events)):
                target = events[j]
                witness = RelationWitness(
                    trace.object_id, event.event_id, target.event_id
                )
                if j == i + 1:
                    direct[(activity, target.activity)].append(witness)
                if spec.eventually_mode == "all_pairs" or target.activity not in seen:
                    eventual[(activity, target.activity)].append(witness)
                seen.add(target.activity)
    grouped, cumulative = [], 0
    for labels, case_ids in sorted(variants.items(), key=lambda x: (-len(x[1]), x[0])):
        cumulative += len(case_ids)
        grouped.append(
            CaseVariant(
                labels,
                tuple(case_ids),
                len(case_ids),
                len(case_ids) / len(traces),
                cumulative / len(traces),
            )
        )
    payload = CaseStatistics(
        len(traces),
        sum(len(t.events) for t in traces),
        tuple(t.object_id for t in traces if not t.events),
        tuple(
            ActivityStatistics(
                a,
                len(counts[a]),
                tuple(cases[a]),
                tuple(starts[a]),
                tuple(ends[a]),
                tuple(reworks[a]),
                repeats[a],
                tuple(sorted(positions[a].items())),
            )
            for a in sorted(counts)
        ),
        tuple(grouped),
        _relations(direct),
        _relations(eventual),
        tuple(
            SelfDistance(
                a, distances.get(a), tuple(sorted(middle[a])), tuple(self_witness[a])
            )
            for a in sorted(counts)
        ),
    )
    return _finish(parent, operator, spec, payload)


@dataclass(frozen=True, slots=True)
class NumericSummary:
    count: int
    total: float | None
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    population_stddev: float | None
    first_quartile: float | None
    third_quartile: float | None


def _summary(values) -> NumericSummary:
    values = tuple(values)
    if not values:
        return NumericSummary(0, None, None, None, None, None, None, None, None)
    avg = mean(values)
    std = pstdev(values)
    try:
        total = math.fsum(values)
    except OverflowError:
        # Recover cancellation even when an intermediate float sum overflows.
        exact_total = sum((Fraction(v) for v in values), Fraction())
        try:
            total = float(exact_total)
        except OverflowError:
            total = math.inf
    ordered = sorted(values)

    def quantile(q):
        position = (len(ordered) - 1) * q
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = position - lower
        if fraction == 0:
            return ordered[lower]
        return float(
            Fraction(ordered[lower]) * Fraction(1 - fraction)
            + Fraction(ordered[upper]) * Fraction(fraction)
        )

    return NumericSummary(
        len(values),
        total if math.isfinite(total) else None,
        min(values),
        max(values),
        avg,
        quantile(0.5),
        std if math.isfinite(std) else None,
        quantile(0.25),
        quantile(0.75),
    )


@dataclass(frozen=True, slots=True)
class CasePerformanceSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    start_attribute: str | None = None
    overlap_boundary: str = "strict"
    max_interval_pairs: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.start_attribute is not None and (
            not isinstance(self.start_attribute, str)
            or not self.start_attribute.strip()
        ):
            raise ValueError("start_attribute must be nonblank text or None")
        if self.overlap_boundary not in ("strict", "inclusive"):
            raise ValueError("overlap_boundary must be strict or inclusive")
        _positive(self.max_interval_pairs, "max_interval_pairs")


@dataclass(frozen=True, slots=True)
class ObservedCaseInterval:
    case_id: str
    start: datetime | None
    end: datetime | None
    duration_seconds: float | None
    status: str
    overlapping_case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ServiceObservation:
    case_id: str
    event_id: str
    activity: str
    start: datetime | None
    end: datetime | None
    seconds: float | None
    status: str


@dataclass(frozen=True, slots=True)
class PathTiming:
    variant: tuple[str, ...]
    position: int
    source: str
    target: str
    samples: tuple[tuple[str, str, str, float], ...]
    unknown_count: int
    summary: NumericSummary


@dataclass(frozen=True, slots=True)
class IntervalPair:
    case_id: str
    source_event_id: str
    target_event_id: str
    source_activity: str
    target_activity: str
    overlap_seconds: float


@dataclass(frozen=True, slots=True)
class CasePerformance:
    """Observed case metrics. cycle_seconds is busy service union / complete
    service case count, not mean case service or sojourn duration. Two cases
    served during the same ten seconds yield 5 seconds, not 10.
    """

    cases: tuple[ObservedCaseInterval, ...]
    duration_summary: NumericSummary
    eligible_case_count: int
    arrival_gaps: tuple[tuple[str, str, float], ...]
    completion_gaps: tuple[tuple[str, str, float], ...]
    arrival_summary: NumericSummary
    completion_summary: NumericSummary
    services: tuple[ServiceObservation, ...]
    service_summaries: tuple[tuple[str, NumericSummary], ...]
    concurrent_intervals: tuple[IntervalPair, ...]
    variant_paths: tuple[PathTiming, ...]
    busy_union_seconds: float | None
    cycle_denominator: int
    cycle_seconds: float | None


def _overlap(a, b, boundary):
    left, right = max(a[0], b[0]), min(a[1], b[1])
    return left <= right if boundary == "inclusive" else left < right


def _utc(time):
    if time is None:
        return None
    try:
        return time.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _union_seconds(intervals):
    intervals = sorted(intervals)
    if not intervals:
        return None
    begin, end = intervals[0]
    total = 0.0
    for next_begin, next_end in intervals[1:]:
        if next_begin > end:
            total += (end - begin).total_seconds()
            begin, end = next_begin, next_end
        elif next_end > end:
            end = next_end
    return total + (end - begin).total_seconds()


def measure_case_performance(
    log: CaseLog, spec: CasePerformanceSpec = CasePerformanceSpec()
) -> ComputationResult[CasePerformance]:
    """Measure completion-time spans and explicitly observed service intervals.

    Cases with any missing or decreasing completion timestamps have unknown span.
    Arrival/completion samples sort valid case boundaries (never trace events).
    cycle_seconds is the union of explicit service intervals / fully timed
    nonempty service case count (not mean case duration). Without an explicit
    start attribute it is unknown. Strict overlap
    requires a positive intersection; inclusive overlap includes touching points.
    """
    if not isinstance(spec, CasePerformanceSpec):
        raise TypeError("spec must be CasePerformanceSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.measure_case_performance"
    if parent.value is None:
        return _finish(parent, operator, spec)
    traces = parent.value.traces
    n = len(traces)
    budget = n * (n - 1) // 2 + sum(
        len(t.events) * (len(t.events) - 1) // 2 for t in traces
    )
    if budget > spec.max_interval_pairs:
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "interval_limit",
                    "Interval-pair enumeration exceeds max_interval_pairs.",
                ),
            ),
            failed=True,
        )
    issues, spans, services, valid_services, paths = [], [], [], {}, defaultdict(list)
    unknown_paths = Counter()
    for source_trace, trace in zip(log.traces, traces):
        events = trace.events
        times = tuple(_utc(e.time) for e in events)
        state = (
            "empty_case"
            if not times
            else "missing_timestamp"
            if None in times
            else "nonmonotonic_timestamps"
            if any(b < a for a, b in zip(times, times[1:]))
            else "observed"
        )
        start, end = (times[0], times[-1]) if state == "observed" else (None, None)
        spans.append((trace.object_id, start, end, state))
        if state != "observed" and state != "empty_case":
            issues.append(
                ComputeIssue(
                    state,
                    "Case span is unknown; source order retained.",
                    (trace.object_id,),
                )
            )
        local_services = []
        if spec.start_attribute is not None:
            for raw, event in zip(source_trace.events, events):
                attr = log.attribute(raw, spec.start_attribute)
                begin = (
                    _utc(attr.value)
                    if attr is not None
                    and attr.type == "date"
                    and attr.value.utcoffset() is not None
                    else None
                )
                finish = _utc(event.time)
                service_status = (
                    "missing_interval"
                    if begin is None or finish is None
                    else "reversed_interval"
                    if finish < begin
                    else "observed"
                )
                seconds = (
                    (finish - begin).total_seconds()
                    if service_status == "observed"
                    else None
                )
                services.append(
                    ServiceObservation(
                        trace.object_id,
                        event.event_id,
                        event.activity,
                        begin,
                        finish,
                        seconds,
                        service_status,
                    )
                )
                if service_status == "observed":
                    local_services.append(services[-1])
                else:
                    issues.append(
                        ComputeIssue(
                            service_status,
                            "Service duration is unknown.",
                            (trace.object_id, event.event_id),
                        )
                    )
        valid_services[trace.object_id] = local_services
        variant = tuple(e.activity for e in events)
        for i, (a, b) in enumerate(zip(events, events[1:])):
            key = (variant, i, a.activity, b.activity)
            paths[key]  # Retain even an entirely unknown path.
            a_time, b_time = _utc(a.time), _utc(b.time)
            if a_time is None or b_time is None or b_time < a_time:
                unknown_paths[key] += 1
                issues.append(
                    ComputeIssue(
                        "unknown_path_gap",
                        "Adjacent completion-time gap is unknown.",
                        (trace.object_id, a.event_id, b.event_id),
                    )
                )
            else:
                paths[key].append(
                    (
                        trace.object_id,
                        a.event_id,
                        b.event_id,
                        (b_time - a_time).total_seconds(),
                    )
                )
    eligible = [x for x in spans if x[3] == "observed"]
    overlaps = defaultdict(list)
    for a, b in combinations(eligible, 2):
        if _overlap(a[1:3], b[1:3], spec.overlap_boundary):
            overlaps[a[0]].append(b[0])
            overlaps[b[0]].append(a[0])
    intervals = tuple(
        ObservedCaseInterval(
            case,
            start,
            end,
            (end - start).total_seconds() if state == "observed" else None,
            state,
            tuple(overlaps[case]),
        )
        for case, start, end, state in spans
    )

    def gaps(index):
        ordered = sorted(eligible, key=lambda x: (x[index], x[0]))
        return tuple(
            (a[0], b[0], (b[index] - a[index]).total_seconds())
            for a, b in zip(ordered, ordered[1:])
        )

    arrivals, completions = gaps(1), gaps(2)
    concurrent = []
    for case, observations in valid_services.items():
        for a, b in combinations(observations, 2):
            if _overlap((a.start, a.end), (b.start, b.end), spec.overlap_boundary):
                concurrent.append(
                    IntervalPair(
                        case,
                        a.event_id,
                        b.event_id,
                        a.activity,
                        b.activity,
                        (min(a.end, b.end) - max(a.start, b.start)).total_seconds(),
                    )
                )
    service_groups = defaultdict(list)
    for sample in services:
        service_groups[sample.activity]
        if sample.seconds is not None:
            service_groups[sample.activity].append(sample.seconds)
    full_service_cases = {
        t.object_id
        for t in traces
        if t.events and len(valid_services[t.object_id]) == len(t.events)
    }
    busy = _union_seconds(
        (s.start, s.end)
        for s in services
        if s.case_id in full_service_cases and s.status == "observed"
    )
    denominator = len(full_service_cases)
    payload = CasePerformance(
        intervals,
        _summary(
            x.duration_seconds for x in intervals if x.duration_seconds is not None
        ),
        len(eligible),
        arrivals,
        completions,
        _summary(x[2] for x in arrivals),
        _summary(x[2] for x in completions),
        tuple(services),
        tuple((a, _summary(samples)) for a, samples in sorted(service_groups.items())),
        tuple(concurrent),
        tuple(
            PathTiming(
                *key,
                tuple(samples),
                unknown_paths[key],
                _summary(x[3] for x in samples),
            )
            for key, samples in sorted(paths.items())
        ),
        busy,
        denominator,
        busy / denominator if busy is not None and denominator else None,
    )
    return _finish(parent, operator, spec, payload, issues)


@dataclass(frozen=True, slots=True)
class AttributeStatisticsSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    scope: str = "event"
    keys: tuple[str, ...] | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.scope not in ("event", "case"):
            raise ValueError("scope must be event or case")
        if self.keys is not None and (
            not isinstance(self.keys, tuple)
            or not all(isinstance(k, str) for k in self.keys)
            or len(set(self.keys)) != len(self.keys)
        ):
            raise ValueError("keys must be a tuple of distinct strings or None")


def _attribute_token(attribute: CaseAttribute) -> str:
    def value(a):
        v = a.value
        if isinstance(v, datetime):
            v = (
                v.isoformat()
                if v.utcoffset() is None
                else v.astimezone(timezone.utc).isoformat()
            )
        elif isinstance(v, float):
            v = v.hex()
        return [
            a.type,
            v,
            [[c.key, value(c)] for c in a.children],
            [[c.key, value(c)] for c in a.values],
        ]

    return json.dumps(value(attribute), ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class AttributeFrequency:
    key: str
    value_json: str
    occurrence_count: int
    case_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AttributeCoverage:
    key: str
    population: int
    observed: int
    missing: int


@dataclass(frozen=True, slots=True)
class AttributeStatistics:
    scope: str
    frequencies: tuple[AttributeFrequency, ...]
    coverage: tuple[AttributeCoverage, ...]


def _entities(log, scope):
    return tuple(
        (trace.id, item)
        for trace in log.traces
        for item in ((trace,) if scope == "case" else trace.events)
    )


def measure_attributes(
    log: CaseLog, spec: AttributeStatisticsSpec = AttributeStatisticsSpec()
) -> ComputationResult[AttributeStatistics]:
    """Count typed top-level effective values; preserve nested value structure.

    Lexical spellings do not distinguish equal typed values. Missing is not null;
        duplicate keys are ambiguous and are never arbitrarily selected. Activity
        classification is unnecessary; the parent is the original CaseLog facts.
    """
    if not isinstance(spec, AttributeStatisticsSpec):
        raise TypeError("spec must be AttributeStatisticsSpec")
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    operator = "pix.case_centric.measure_attributes"
    entities = _entities(log, spec.scope)
    frequencies, observed = defaultdict(list), Counter()
    try:
        keys = (
            spec.keys
            if spec.keys is not None
            else tuple(
                sorted(
                    {
                        a.key
                        for _, item in entities
                        for a in log.effective_attributes(item)
                    }
                )
            )
        )
        for case, item in entities:
            for key in keys:
                attribute = log.attribute(item, key)
                if attribute is not None:
                    observed[key] += 1
                    frequencies[(key, _attribute_token(attribute))].append(
                        (case, item.id)
                    )
    except ValueError as error:
        return _finish_facts(
            log,
            operator,
            spec,
            issues=(ComputeIssue("ambiguous_attribute", str(error)),),
            failed=True,
        )
    payload = AttributeStatistics(
        spec.scope,
        tuple(
            AttributeFrequency(
                key,
                token,
                len(w),
                tuple(dict.fromkeys(x[0] for x in w)),
                tuple(x[1] for x in w),
            )
            for (key, token), w in sorted(frequencies.items())
        ),
        tuple(
            AttributeCoverage(
                key, len(entities), observed[key], len(entities) - observed[key]
            )
            for key in keys
        ),
    )
    return _finish_facts(log, operator, spec, payload)


@dataclass(frozen=True, slots=True)
class FrequentSequenceSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    min_case_support: int = 1
    max_length: int = 5
    contiguous: bool = False
    max_candidates: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        for name in ("min_case_support", "max_length", "max_candidates"):
            _positive(getattr(self, name), name)
        if type(self.contiguous) is not bool:
            raise TypeError("contiguous must be bool")


@dataclass(frozen=True, slots=True)
class SequenceMatch:
    case_id: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FrequentSequence:
    activities: tuple[str, ...]
    case_support: int
    case_coverage: float
    first_matches: tuple[SequenceMatch, ...]


@dataclass(frozen=True, slots=True)
class FrequentSequences:
    case_count: int
    examined_candidates: int
    sequences: tuple[FrequentSequence, ...]


def discover_frequent_sequences(
    log: CaseLog, spec: FrequentSequenceSpec = FrequentSequenceSpec()
) -> ComputationResult[FrequentSequences]:
    """Exact case-support prefix projection within an explicit length bound.

    Each returned sequence has one earliest-position witness per matching case.
    Repeated matches in a case do not inflate support. Exhausting the candidate
    budget returns unavailable, never incomplete results labelled exact.
    """
    if not isinstance(spec, FrequentSequenceSpec):
        raise TypeError("spec must be FrequentSequenceSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_frequent_sequences"
    if parent.value is None:
        return _finish(parent, operator, spec)
    traces = parent.value.traces
    # Projected entries retain all possible last positions for contiguous
    # extension; gapped extension only needs the earliest endpoint per case.
    initial = {i: {(): -1} for i in range(len(traces))}
    stack, output, examined = [((), initial)], [], 0
    while stack:
        prefix, projection = stack.pop()
        extensions = defaultdict(lambda: defaultdict(dict))
        for ti, matches in projection.items():
            events = traces[ti].events
            for positions, last in matches.items():
                indices = (
                    range(last + 1, min(last + 2, len(events)))
                    if spec.contiguous and prefix
                    else range(last + 1, len(events))
                )
                for pos in indices:
                    label = events[pos].activity
                    chain = positions + (pos,)
                    target = extensions[label][ti]
                    if spec.contiguous:
                        target[chain] = pos
                    elif not target or pos < next(iter(target.values())):
                        target.clear()
                        target[chain] = pos
        examined += len(extensions)
        if examined > spec.max_candidates:
            return _finish(
                parent,
                operator,
                spec,
                issues=(
                    ComputeIssue(
                        "candidate_limit",
                        "Frequent sequence candidate limit exceeded; no partial exact output.",
                    ),
                ),
                failed=True,
            )
        for label, projected in sorted(extensions.items(), reverse=True):
            if len(projected) < spec.min_case_support:
                continue
            sequence = prefix + (label,)
            witnesses = tuple(
                SequenceMatch(
                    traces[i].object_id,
                    tuple(traces[i].events[p].event_id for p in min(matches)),
                )
                for i, matches in sorted(projected.items())
            )
            output.append(
                FrequentSequence(
                    sequence, len(projected), len(projected) / len(traces), witnesses
                )
            )
            if len(sequence) < spec.max_length:
                stack.append((sequence, projected))
    return _finish(
        parent,
        operator,
        spec,
        FrequentSequences(
            len(traces),
            examined,
            tuple(sorted(output, key=lambda x: (-x.case_support, x.activities))),
        ),
    )


@dataclass(frozen=True, slots=True)
class ProcessCubeSpec:
    x_key: str
    y_key: str
    scope: str = "case"
    numeric_key: str | None = None
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.scope not in ("case", "event"):
            raise ValueError("scope must be case or event")
        for name in ("x_key", "y_key"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        if self.numeric_key is not None and not isinstance(self.numeric_key, str):
            raise TypeError("numeric_key must be str or None")


@dataclass(frozen=True, slots=True)
class CubeCell:
    x_value_json: str | None
    y_value_json: str | None
    entity_ids: tuple[str, ...]
    case_ids: tuple[str, ...]
    numeric_summary: NumericSummary
    numeric_unknown: int


@dataclass(frozen=True, slots=True)
class ProcessCube:
    population: int
    cells: tuple[CubeCell, ...]


def build_process_cube(
    log: CaseLog, spec: ProcessCubeSpec
) -> ComputationResult[ProcessCube]:
    """Cross-tabulate typed categorical dimensions with an explicit missing cell.

    Count, distinct-case membership and optional finite numeric aggregates share
    the same cell population. Binning and arbitrary aggregate callbacks are not
    part of this profile.
    """
    if not isinstance(spec, ProcessCubeSpec):
        raise TypeError("spec must be ProcessCubeSpec")
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    operator = "pix.case_centric.build_process_cube"
    groups, numbers, unknown = defaultdict(list), defaultdict(list), Counter()
    entities = _entities(log, spec.scope)
    try:
        for case, item in entities:
            attrs = (log.attribute(item, spec.x_key), log.attribute(item, spec.y_key))
            key = tuple(_attribute_token(a) if a is not None else None for a in attrs)
            groups[key].append((case, item.id))
            if spec.numeric_key is not None:
                attr = log.attribute(item, spec.numeric_key)
                try:
                    number = (
                        float(attr.value)
                        if attr is not None and attr.type in ("int", "float")
                        else math.nan
                    )
                except OverflowError:
                    number = math.nan
                if math.isfinite(number):
                    numbers[key].append(number)
                else:
                    unknown[key] += 1
    except ValueError as error:
        return _finish_facts(
            log,
            operator,
            spec,
            issues=(ComputeIssue("ambiguous_attribute", str(error)),),
            failed=True,
        )
    cells = tuple(
        CubeCell(
            *key,
            tuple(x[1] for x in items),
            tuple(dict.fromkeys(x[0] for x in items)),
            _summary(numbers[key]),
            unknown[key],
        )
        for key, items in sorted(
            groups.items(), key=lambda x: tuple((v is not None, v or "") for v in x[0])
        )
    )
    issues = (
        (
            ComputeIssue(
                "numeric_coverage",
                "Some numeric observations are unavailable; per-cell counts retained.",
            ),
        )
        if sum(unknown.values())
        else ()
    )
    if any(c.numeric_summary.count and c.numeric_summary.total is None for c in cells):
        issues += (
            ComputeIssue(
                "numeric_range",
                "At least one cell total exceeds the finite numeric range.",
            ),
        )
    return _finish_facts(log, operator, spec, ProcessCube(len(entities), cells), issues)


@dataclass(frozen=True, slots=True)
class NumericAttributeSpec:
    key: str
    scope: str = "event"
    grid: tuple[float, ...] = ()
    bandwidth: float | None = None
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_kernel_evaluations: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        _positive(self.max_kernel_evaluations, "max_kernel_evaluations")
        if not isinstance(self.key, str):
            raise TypeError("key must be str")
        if self.scope not in ("case", "event"):
            raise ValueError("scope must be case or event")
        if not isinstance(self.grid, tuple) or not all(
            type(x) in (int, float) and math.isfinite(x) for x in self.grid
        ):
            raise ValueError("grid must contain finite numeric coordinates")
        if self.bandwidth is not None and (
            type(self.bandwidth) not in (int, float)
            or not math.isfinite(self.bandwidth)
            or self.bandwidth <= 0
        ):
            raise ValueError("bandwidth must be finite and positive")
        if self.grid and self.bandwidth is None:
            raise ValueError("KDE requires an explicit bandwidth")
        object.__setattr__(self, "grid", tuple(float(x) for x in self.grid))
        if self.bandwidth is not None:
            object.__setattr__(self, "bandwidth", float(self.bandwidth))


@dataclass(frozen=True, slots=True)
class NumericAttributeStatistics:
    population: int
    observations: tuple[tuple[str, str, float], ...]
    unknown_entity_ids: tuple[str, ...]
    summary: NumericSummary
    gaussian_kde: tuple[tuple[float, float | None], ...]


def measure_numeric_attribute(
    log: CaseLog, spec: NumericAttributeSpec
) -> ComputationResult[NumericAttributeStatistics]:
    """Finite observations and Gaussian KDE with a caller-chosen bandwidth.

    Density is sum(exp(-0.5*((x-v)/h)^2))/(n*h*sqrt(2*pi)). No samples produces
    unknown density, and a nonrepresentable result is not replaced with zero.
    """
    if not isinstance(spec, NumericAttributeSpec):
        raise TypeError("spec must be NumericAttributeSpec")
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    operator = "pix.case_centric.measure_numeric_attribute"
    observations, unknown = [], []
    entities = _entities(log, spec.scope)
    try:
        for case, item in entities:
            attribute = log.attribute(item, spec.key)
            if attribute is None or attribute.type not in ("int", "float"):
                unknown.append(item.id)
                continue
            try:
                value = float(attribute.value)
            except OverflowError:
                unknown.append(item.id)
                continue
            if not math.isfinite(value):
                unknown.append(item.id)
            else:
                observations.append((case, item.id, value))
    except ValueError as error:
        return _finish_facts(
            log,
            operator,
            spec,
            issues=(ComputeIssue("ambiguous_attribute", str(error)),),
            failed=True,
        )
    values = tuple(x[2] for x in observations)
    if len(values) * len(spec.grid) > spec.max_kernel_evaluations:
        return _finish_facts(
            log,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "kernel_limit", "Gaussian KDE exceeds max_kernel_evaluations."
                ),
            ),
            failed=True,
        )
    kde, numeric_issue = [], False
    for point in spec.grid:
        if not values:
            density = None
        else:
            log_kernels = []
            for value in values:
                delta = point - value
                z = (
                    delta / spec.bandwidth
                    if math.isfinite(delta)
                    else point / spec.bandwidth - value / spec.bandwidth
                )
                log_kernels.append(-0.5 * z * z)
            maximum = max(log_kernels)
            try:
                if maximum == -math.inf:
                    density = 0.0
                else:
                    log_density = (
                        maximum
                        + math.log(sum(math.exp(x - maximum) for x in log_kernels))
                        - math.log(len(values))
                        - math.log(spec.bandwidth)
                        - 0.5 * math.log(2 * math.pi)
                    )
                    density = math.exp(log_density)
            except OverflowError:
                density = math.inf
            if not math.isfinite(density):
                density, numeric_issue = None, True
        kde.append((float(point), density))
    issues = []
    if unknown:
        issues.append(
            ComputeIssue(
                "numeric_coverage",
                "Missing, nonnumeric or unrepresentable observations are excluded with identities.",
            )
        )
    if numeric_issue:
        issues.append(
            ComputeIssue(
                "numeric_range", "A density cannot be represented as a finite float."
            )
        )
    summary = _summary(values)
    if summary.count and summary.total is None:
        issues.append(
            ComputeIssue(
                "numeric_range", "The numeric total exceeds the finite float range."
            )
        )
    return _finish_facts(
        log,
        operator,
        spec,
        NumericAttributeStatistics(
            len(entities), tuple(observations), tuple(unknown), summary, tuple(kde)
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class PerformanceSpectrumSpec:
    activities: tuple[str, ...]
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    match_mode: str = "projected_contiguous"
    max_matches: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if (
            not isinstance(self.activities, tuple)
            or len(self.activities) < 2
            or not all(isinstance(a, str) and a for a in self.activities)
        ):
            raise ValueError(
                "activities must be a tuple of at least two activity labels"
            )
        if self.match_mode not in (
            "projected_contiguous",
            "source_contiguous",
            "subsequence",
        ):
            raise ValueError("unsupported spectrum match_mode")
        _positive(self.max_matches, "max_matches")


@dataclass(frozen=True, slots=True)
class SpectrumPoint:
    case_id: str
    event_ids: tuple[str, ...]
    times: tuple[datetime, ...]


@dataclass(frozen=True, slots=True)
class PerformanceSpectrum:
    case_count: int
    matched_occurrences: int
    unknown_occurrences: int
    points: tuple[SpectrumPoint, ...]


def discover_performance_spectrum(
    log: CaseLog, spec: PerformanceSpectrumSpec
) -> ComputationResult[PerformanceSpectrum]:
    """Extract source-ordered timestamp vectors, without hidden time sorting.

    Projected-contiguous removes labels outside the pattern alphabet first.
    Source-contiguous retains every recorded event. Subsequence retains every
    position combination matching the pattern; it is not a claim of equivalence
    to the reference library's disconnected maximal-fragment implementation.
    """
    if not isinstance(spec, PerformanceSpectrumSpec):
        raise TypeError("spec must be PerformanceSpectrumSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_performance_spectrum"
    if parent.value is None:
        return _finish(parent, operator, spec)
    points, unknown, matched, examined = [], 0, 0, 0
    alphabet, width = set(spec.activities), len(spec.activities)
    for trace in parent.value.traces:
        events = (
            tuple(e for e in trace.events if e.activity in alphabet)
            if spec.match_mode == "projected_contiguous"
            else trace.events
        )
        if spec.match_mode == "subsequence":
            # Explicit combination budget bounds work even with no final match.
            index_sets = combinations(range(len(events)), width)
        else:
            index_sets = (range(i, i + width) for i in range(len(events) - width + 1))
        for indices in index_sets:
            examined += 1
            if examined > spec.max_matches:
                return _finish(
                    parent,
                    operator,
                    spec,
                    issues=(
                        ComputeIssue(
                            "spectrum_limit",
                            "Spectrum candidate limit exceeded; no incomplete exact vectors.",
                        ),
                    ),
                    failed=True,
                )
            selected = tuple(events[i] for i in indices)
            if tuple(e.activity for e in selected) != spec.activities:
                continue
            matched += 1
            times = tuple(_utc(e.time) for e in selected)
            if None in times or any(b < a for a, b in zip(times, times[1:])):
                unknown += 1
            else:
                points.append(
                    SpectrumPoint(
                        trace.object_id, tuple(e.event_id for e in selected), times
                    )
                )
    issues = (
        (
            ComputeIssue(
                "spectrum_time_coverage",
                "Some matched occurrences have missing or decreasing times.",
            ),
        )
        if unknown
        else ()
    )
    return _finish(
        parent,
        operator,
        spec,
        PerformanceSpectrum(len(parent.value.traces), matched, unknown, tuple(points)),
        issues,
    )


@dataclass(frozen=True, slots=True)
class ChaoticActivitySpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    alpha: float | None = None
    max_activity_event_product: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.alpha is not None and (
            type(self.alpha) not in (int, float)
            or not math.isfinite(self.alpha)
            or self.alpha < 0
        ):
            raise ValueError("alpha must be finite nonnegative or None")
        _positive(self.max_activity_event_product, "max_activity_event_product")
        if self.alpha is not None:
            object.__setattr__(self, "alpha", float(self.alpha))


@dataclass(frozen=True, slots=True)
class ChaoticActivity:
    activity: str
    count: int
    raw_entropy: float
    smoothed_entropy: float
    entropy_gain: float
    score: float


@dataclass(frozen=True, slots=True)
class ChaoticActivities:
    alpha_used: float | None
    raw_total_entropy: float
    activities: tuple[ChaoticActivity, ...]


def _neighborhood_entropies(sequences, alpha):
    counts = Counter(a for sequence in sequences for a in sequence)
    outgoing, incoming = defaultdict(Counter), defaultdict(Counter)
    # Private object tokens cannot collide with literal START/END activities.
    start, end = object(), object()
    for sequence in sequences:
        for a, b in zip((start,) + sequence, sequence + (end,)):
            outgoing[a][b] += 1
            incoming[b][a] += 1
    values = {}
    for activity, count in counts.items():
        entropy = 0.0
        for mapping, boundary in ((outgoing, end), (incoming, start)):
            if alpha == 0.0:
                for frequency in mapping[activity].values():
                    probability = frequency / count
                    entropy -= probability * math.log2(probability)
                continue
            scale = max(count, alpha)
            denominator = count / scale + (alpha / scale) * (len(counts) + 1)
            for neighbor in (*counts, boundary):
                probability = (
                    mapping[activity][neighbor] / scale + alpha / scale
                ) / denominator
                if probability:
                    entropy -= probability * math.log2(probability)
        values[activity] = entropy
    return counts, values


def discover_chaotic_activities(
    log: CaseLog, spec: ChaoticActivitySpec = ChaoticActivitySpec()
) -> ComputationResult[ChaoticActivities]:
    """Compute predecessor/successor entropy and deletion gain.

    Score=(smoothed neighborhood entropy + raw deletion gain)/2. The deletion
    operation bridges neighbors; total entropy is the unweighted activity sum.
    Default smoothing is 1/alphabet size. This descriptive ordering is not a
    causal judgment about incorrect activity execution.
    """
    if not isinstance(spec, ChaoticActivitySpec):
        raise TypeError("spec must be ChaoticActivitySpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_chaotic_activities"
    if parent.value is None:
        return _finish(parent, operator, spec)
    sequences = tuple(tuple(e.activity for e in t.events) for t in parent.value.traces)
    counts = Counter(a for sequence in sequences for a in sequence)
    if len(counts) * sum(map(len, sequences)) > spec.max_activity_event_product:
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "chaotic_limit",
                    "Activity-deletion work exceeds max_activity_event_product.",
                ),
            ),
            failed=True,
        )
    _, raw = _neighborhood_entropies(sequences, 0.0)
    alpha = (
        spec.alpha
        if spec.alpha is not None
        else (1.0 / len(counts) if counts else None)
    )
    smooth = _neighborhood_entropies(sequences, alpha)[1] if counts else {}
    total = sum(raw.values(), 0.0)
    output = []
    for activity, count in counts.items():
        remaining = tuple(
            tuple(a for a in sequence if a != activity) for sequence in sequences
        )
        gain = total - sum(_neighborhood_entropies(remaining, 0.0)[1].values(), 0.0)
        output.append(
            ChaoticActivity(
                activity,
                count,
                raw[activity],
                smooth[activity],
                gain,
                (smooth[activity] + gain) / 2,
            )
        )
    return _finish(
        parent,
        operator,
        spec,
        ChaoticActivities(
            alpha,
            total,
            tuple(sorted(output, key=lambda x: (-x.score, -x.count, x.activity))),
        ),
    )


@dataclass(frozen=True, slots=True)
class EventDistributionSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    granularity: str = "date"
    utc_offset_minutes: int = 0
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.granularity not in ("date", "hour", "month", "weekday", "hour_of_day"):
            raise ValueError("unsupported calendar granularity")
        if (
            type(self.utc_offset_minutes) is not int
            or not -1439 <= self.utc_offset_minutes <= 1439
        ):
            raise ValueError("utc_offset_minutes must be an integer in [-1439,1439]")


@dataclass(frozen=True, slots=True)
class EventTimeBin:
    key: str
    event_ids: tuple[str, ...]
    case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventDistribution:
    event_count: int
    observed_count: int
    unknown_event_ids: tuple[str, ...]
    bins: tuple[EventTimeBin, ...]


def measure_event_distribution(
    log: CaseLog, spec: EventDistributionSpec = EventDistributionSpec()
) -> ComputationResult[EventDistribution]:
    """Calendar bins in an explicit fixed UTC offset, without DST assumptions.

    Weekday keys are ISO 1=Monday..7=Sunday. Date/hour bins retain their date;
    hour_of_day and weekday pool dates. This counts observations, not case starts.
    """
    if not isinstance(spec, EventDistributionSpec):
        raise TypeError("spec must be EventDistributionSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.measure_event_distribution"
    if parent.value is None:
        return _finish(parent, operator, spec)
    zone = timezone(timedelta(minutes=spec.utc_offset_minutes))
    bins, unknown, count = defaultdict(list), [], 0
    for trace in parent.value.traces:
        for event in trace.events:
            count += 1
            if event.time is None:
                unknown.append(event.event_id)
                continue
            try:
                time = event.time.astimezone(zone)
            except (OverflowError, ValueError):
                unknown.append(event.event_id)
                continue
            key = {
                "date": f"{time.year:04d}-{time.month:02d}-{time.day:02d}",
                "hour": f"{time.year:04d}-{time.month:02d}-{time.day:02d}T{time.hour:02d}",
                "month": f"{time.year:04d}-{time.month:02d}",
                "weekday": str(time.isoweekday()),
                "hour_of_day": f"{time.hour:02d}",
            }[spec.granularity]
            bins[key].append((trace.object_id, event.event_id))
    issues = (
        (
            ComputeIssue(
                "time_bin_coverage",
                "Some event timestamps are unavailable or outside the selected calendar range.",
            ),
        )
        if unknown
        else ()
    )
    return _finish(
        parent,
        operator,
        spec,
        EventDistribution(
            count,
            count - len(unknown),
            tuple(unknown),
            tuple(
                EventTimeBin(
                    key,
                    tuple(x[1] for x in values),
                    tuple(dict.fromkeys(x[0] for x in values)),
                )
                for key, values in sorted(bins.items())
            ),
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class IntervalRelationSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    start_attribute: str | None = None
    keep_first_following: bool = False
    tie_policy: str = "source_order"
    max_relation_pairs: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _trace_spec(self.trace_spec)
        if self.start_attribute is not None and (
            not isinstance(self.start_attribute, str)
            or not self.start_attribute.strip()
        ):
            raise ValueError("start_attribute must be nonblank text or None")
        if type(self.keep_first_following) is not bool:
            raise TypeError("keep_first_following must be bool")
        if self.tie_policy not in ("source_order", "reject"):
            raise ValueError("tie_policy must be source_order or reject")
        _positive(self.max_relation_pairs, "max_relation_pairs")


@dataclass(frozen=True, slots=True)
class IntervalEventuallyFollows:
    event_population: int
    selected_event_count: int
    excluded_event_ids: tuple[str, ...]
    candidate_pairs: int
    ordered_event_ids: tuple[tuple[str, tuple[str, ...]], ...]
    relations: tuple[SequenceRelation, ...]


def discover_interval_eventually_follows(
    log: CaseLog, spec: IntervalRelationSpec = IntervalRelationSpec()
) -> ComputationResult[IntervalEventuallyFollows]:
    """Temporal admissibility relation, separate from source-sequence follows.

    Each case is explicitly ordered by interval start in absolute time. Retain
    ordered i<j pairs satisfying completion_i <= start_j. Without a start key,
    completion timestamps denote point events, not inferred service intervals.
    keep_first_following retains only the first admissible successor for each
    source event. Equal starts use source position or reject that case according
    to tie_policy. Missing/reversed intervals are excluded with identities.
    """
    if not isinstance(spec, IntervalRelationSpec):
        raise TypeError("spec must be IntervalRelationSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_interval_eventually_follows"
    if parent.value is None:
        return _finish(parent, operator, spec)
    traces = parent.value.traces
    budget = sum(len(t.events) * (len(t.events) - 1) // 2 for t in traces)
    if budget > spec.max_relation_pairs:
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "relation_limit",
                    "Interval relation candidates exceed max_relation_pairs.",
                ),
            ),
            failed=True,
        )
    relations, ordered, excluded, issues = defaultdict(list), [], [], []
    selected_count, candidates, population = 0, 0, 0
    for raw_trace, trace in zip(log.traces, traces):
        observations = []
        for position, (raw, event) in enumerate(zip(raw_trace.events, trace.events)):
            population += 1
            end = _utc(event.time)
            if spec.start_attribute is None:
                start = end
            else:
                attr = log.attribute(raw, spec.start_attribute)
                start = (
                    _utc(attr.value)
                    if attr is not None
                    and attr.type == "date"
                    and attr.value.utcoffset() is not None
                    else None
                )
            if start is None or end is None or end < start:
                excluded.append(event.event_id)
                issues.append(
                    ComputeIssue(
                        "interval_relation_coverage",
                        "Event has no valid observed interval or point timestamp.",
                        (trace.object_id, event.event_id),
                    )
                )
            else:
                observations.append((start, position, end, event))
        if spec.tie_policy == "reject" and len({x[0] for x in observations}) != len(
            observations
        ):
            excluded.extend(x[3].event_id for x in observations)
            issues.append(
                ComputeIssue(
                    "ambiguous_start_order",
                    "Equal interval starts exclude this case under the reject policy.",
                    (trace.object_id,),
                )
            )
            ordered.append((trace.object_id, ()))
            continue
        observations.sort(key=lambda x: (x[0], x[1]))
        selected_count += len(observations)
        candidates += len(observations) * (len(observations) - 1) // 2
        ordered.append((trace.object_id, tuple(x[3].event_id for x in observations)))
        for i, (_, _, end, source) in enumerate(observations):
            for start, _, _, target in observations[i + 1 :]:
                if end <= start:
                    relations[(source.activity, target.activity)].append(
                        RelationWitness(
                            trace.object_id, source.event_id, target.event_id
                        )
                    )
                    if spec.keep_first_following:
                        break
    return _finish(
        parent,
        operator,
        spec,
        IntervalEventuallyFollows(
            population,
            selected_count,
            tuple(excluded),
            candidates,
            tuple(ordered),
            _relations(relations),
        ),
        issues,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.measure_statistics": (
        "case-statistics",
        StatisticsSpec,
        CaseStatistics,
    ),
    "pix.case_centric.measure_case_performance": (
        "case-performance",
        CasePerformanceSpec,
        CasePerformance,
    ),
    "pix.case_centric.measure_attributes": (
        "case-attribute-statistics",
        AttributeStatisticsSpec,
        AttributeStatistics,
    ),
    "pix.case_centric.discover_frequent_sequences": (
        "case-frequent-sequences",
        FrequentSequenceSpec,
        FrequentSequences,
    ),
    "pix.case_centric.build_process_cube": (
        "case-process-cube",
        ProcessCubeSpec,
        ProcessCube,
    ),
    "pix.case_centric.measure_numeric_attribute": (
        "case-numeric-attribute",
        NumericAttributeSpec,
        NumericAttributeStatistics,
    ),
    "pix.case_centric.discover_performance_spectrum": (
        "case-performance-spectrum",
        PerformanceSpectrumSpec,
        PerformanceSpectrum,
    ),
    "pix.case_centric.discover_chaotic_activities": (
        "case-chaotic-activities",
        ChaoticActivitySpec,
        ChaoticActivities,
    ),
    "pix.case_centric.measure_event_distribution": (
        "case-event-distribution",
        EventDistributionSpec,
        EventDistribution,
    ),
    "pix.case_centric.discover_interval_eventually_follows": (
        "case-interval-eventually-follows",
        IntervalRelationSpec,
        IntervalEventuallyFollows,
    ),
}

__all__ = [
    "StatisticsSpec",
    "CaseStatistics",
    "measure_statistics",
    "CasePerformanceSpec",
    "CasePerformance",
    "measure_case_performance",
    "AttributeStatisticsSpec",
    "AttributeStatistics",
    "measure_attributes",
    "FrequentSequenceSpec",
    "FrequentSequences",
    "discover_frequent_sequences",
    "ProcessCubeSpec",
    "ProcessCube",
    "build_process_cube",
    "NumericAttributeSpec",
    "NumericAttributeStatistics",
    "measure_numeric_attribute",
    "PerformanceSpectrumSpec",
    "PerformanceSpectrum",
    "discover_performance_spectrum",
    "ChaoticActivitySpec",
    "ChaoticActivities",
    "discover_chaotic_activities",
    "EventDistributionSpec",
    "EventDistribution",
    "measure_event_distribution",
    "IntervalRelationSpec",
    "IntervalEventuallyFollows",
    "discover_interval_eventually_follows",
]
