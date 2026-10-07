"""Native frequency and interval Heuristics Miner profiles.

This module computes a HeuristicsNet, not a Petri net. Each retained dependency,
short loop and AND pair carries its measured value; bindings are maximal cliques
of the AND relation, with singleton alternatives for unconnected neighbours.
Bindings are discovery hypotheses, not a soundness or log-fitness guarantee.

Classic: D(a,b)=(f(a,b)-f(b,a))/(f(a,b)+f(b,a)+1), with D(a,a)=f/(f+1).
The length-two loop measure is (f(aba)+f(bab))/(f(aba)+f(bab)+1).
Output AND(a;b,c)=(f(b,c)+f(c,b))/(f(a,b)+f(a,c)+1); input reverses
the two denominator edges. Threshold comparisons are inclusive.

Interval (++): f counts the first following non-overlapping occurrence after
each occurrence in stable start-time order. D(a,b)=(f(a,b)-f(b,a))/
(f(a,b)+f(b,a)+overlap(a,b)); AND adds overlap(b,c) to the numerator
and removes the +1 regularizer. Threshold comparisons are strict. Closed
interval overlap is selectable; the default strict policy does not treat merely
touching intervals as concurrency. This differs from PM4Py's default. Explicit
observed starts/ends are required; lifecycle pairing and point-time imputation
are deliberately not performed. Start/end frequencies always describe source
trace boundaries, not all minimal/maximal nodes of an interval partial order.

The mathematical definitions were checked against the pinned PM4Py 2.7.23.8
classic/plusplus and heuristics_net/node source, without importing it. This is
an independently written immutable profile, not a claim of release parity:
default DFG pre-cleaning is disabled, filtered isolated activities remain in the
net, short-loop edges do not depend on pre-existing nodes, and AND bindings do
not include a pivot's self-loop. There is no Petri-net conversion here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from math import isfinite
from typing import ClassVar, Literal

from pix.case_centric._input import as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseLog

OPERATOR_ID = "pix.case_centric.discover_heuristics"


@dataclass(frozen=True, slots=True)
class HeuristicsSpec:
    profile: Literal["classic", "plusplus"] = "classic"
    dependency_threshold: float = 0.5
    and_threshold: float = 0.65
    loop_two_threshold: float = 0.5
    min_activity_count: int = 1
    min_edge_count: int = 1
    dfg_noise_threshold: float = 0.0
    start_timestamp_key: str = "start_timestamp"
    overlap_policy: Literal["strict", "closed"] = "strict"
    max_binding_search_states: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.profile not in ("classic", "plusplus"):
            raise ValueError("profile must be classic or plusplus")
        for name in (
            "dependency_threshold",
            "and_threshold",
            "loop_two_threshold",
            "dfg_noise_threshold",
        ):
            value = getattr(self, name)
            if (
                type(value) not in (float, int)
                or not 0 <= value <= 1
                or not isfinite(value)
            ):
                raise ValueError(f"{name} must be a finite number in [0, 1]")
            # The public numeric boundary accepts 0/1 integers, while the
            # immutable request and strict persistence schema store floats.
            # Normalize before computing identity so 0 and 0.0 are one request.
            object.__setattr__(self, name, float(value))
        for name in (
            "min_activity_count",
            "min_edge_count",
            "max_binding_search_states",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if (
            not isinstance(self.start_timestamp_key, str)
            or not self.start_timestamp_key.strip()
        ):
            raise ValueError("start_timestamp_key must be nonblank text")
        if self.overlap_policy not in ("strict", "closed"):
            raise ValueError("overlap_policy must be strict or closed")
        if self.profile == "plusplus" and self.dfg_noise_threshold:
            raise ValueError("DFG pre-cleaning applies only to the classic profile")


@dataclass(frozen=True, slots=True)
class HeuristicsActivity:
    activity: str
    count: int
    start_count: int
    end_count: int


@dataclass(frozen=True, slots=True)
class HeuristicsFrequency:
    source: str
    target: str
    count: int


@dataclass(frozen=True, slots=True)
class HeuristicsDependency:
    source: str
    target: str
    count: int
    reverse_count: int
    overlap_count: int
    measure: float
    selected: bool


@dataclass(frozen=True, slots=True)
class HeuristicsShortLoop:
    activities: tuple[str, ...]
    occurrences: int
    measure: float
    selected: bool


@dataclass(frozen=True, slots=True)
class HeuristicsAndPair:
    activity: str
    direction: Literal["input", "output"]
    left: str
    right: str
    numerator: int
    denominator: int
    measure: float
    selected: bool


@dataclass(frozen=True, slots=True)
class HeuristicsBinding:
    activity: str
    direction: Literal["input", "output"]
    alternatives: tuple[tuple[str, ...], ...]


@dataclass(frozen=True, slots=True)
class HeuristicsNet:
    profile: str
    trace_count: int
    empty_trace_count: int
    activities: tuple[HeuristicsActivity, ...]
    follows: tuple[HeuristicsFrequency, ...]
    overlaps: tuple[HeuristicsFrequency, ...]
    dependencies: tuple[HeuristicsDependency, ...]
    edges: tuple[tuple[str, str], ...]
    short_loops: tuple[HeuristicsShortLoop, ...]
    and_pairs: tuple[HeuristicsAndPair, ...]
    bindings: tuple[HeuristicsBinding, ...]
    excluded_activities: tuple[HeuristicsActivity, ...]
    precleaned_edges: tuple[HeuristicsFrequency, ...]


def _prepare_traces(
    log: CaseLog | ComputationResult[TraceSet], trace_spec: CaseTraceSpec | None
) -> ComputationResult[TraceSet]:
    if not isinstance(log, CaseLog) and trace_spec is not None:
        raise ValueError("trace_spec can only be supplied with CaseLog")
    return as_case_traces(
        log, trace_spec if trace_spec is not None else CaseTraceSpec()
    )


def _interval_counts(
    log: CaseLog, traces: TraceSet, spec: HeuristicsSpec, trace_spec: CaseTraceSpec
):
    labels = {
        event.event_id: event.activity
        for trace in traces.traces
        for event in trace.events
    }
    follows: Counter[tuple[str, str]] = Counter()
    overlap: Counter[tuple[str, str]] = Counter()
    for trace in log.traces:
        observations: list[tuple[datetime, datetime, int, str]] = []
        for index, event in enumerate(trace.events):
            start = log.attribute(event, spec.start_timestamp_key)
            end = log.attribute(event, trace_spec.timestamp_key)
            if any(
                value is None or value.type != "date" or value.value.utcoffset() is None
                for value in (start, end)
            ):
                raise ValueError(
                    f"event {event.id!r} requires explicit timezone-aware start and end timestamps"
                )
            if start.value > end.value:
                raise ValueError(f"event {event.id!r} starts after its completion")
            observations.append((start.value, end.value, index, labels[event.id]))
        observations.sort(key=lambda row: (row[0], row[2]))
        # Scan every unordered pair once; the first eligible successor of each
        # occurrence contributes one edge. Equal starts retain source order.
        for index, (start, end, _, activity) in enumerate(observations):
            successor_found = False
            for other_start, other_end, _, other in observations[index + 1 :]:
                if not successor_found and end <= other_start:
                    follows[activity, other] += 1
                    successor_found = True
                left, right = max(start, other_start), min(end, other_end)
                if left < right or (spec.overlap_policy == "closed" and left == right):
                    overlap[tuple(sorted((activity, other)))] += 1
    return follows, overlap


class _BindingLimit(Exception):
    pass


def _cliques(
    neighbours: set[str], related: set[tuple[str, str]], remaining: list[int]
) -> tuple[tuple[str, ...], ...]:
    """Iterative maximal-clique search, bounded across all input/output sets."""
    if not neighbours:
        return ()
    adjacency = {
        node: {other for other in neighbours if tuple(sorted((node, other))) in related}
        for node in neighbours
    }
    agenda = [(frozenset(), set(neighbours), set())]
    found: list[tuple[str, ...]] = []
    while agenda:
        remaining[0] -= 1
        if remaining[0] < 0:
            raise _BindingLimit
        clique, candidates, excluded = agenda.pop()
        if not candidates and not excluded:
            found.append(tuple(sorted(clique)))
            continue
        pivot = max(
            sorted(candidates | excluded),
            key=lambda node: len(candidates & adjacency[node]),
        )
        for node in sorted(candidates - adjacency[pivot]):
            agenda.append(
                (
                    clique | {node},
                    candidates & adjacency[node],
                    excluded & adjacency[node],
                )
            )
            candidates.remove(node)
            excluded.add(node)
    return tuple(sorted(found))


def discover_heuristics(
    log: CaseLog | ComputationResult[TraceSet],
    spec: HeuristicsSpec = HeuristicsSpec(),
    *,
    trace_spec: CaseTraceSpec | None = None,
) -> ComputationResult[HeuristicsNet]:
    """Discover an auditable HeuristicsNet; ++ requires observed intervals.

    Classic uses source event order and accepts missing timestamps. Failed or
    partial trace preparation is not silently converted into a complete result.
    """
    if not isinstance(spec, HeuristicsSpec):
        raise TypeError("spec must be HeuristicsSpec")
    prepared = _prepare_traces(log, trace_spec)
    parents = (prepared.computation_id,) if prepared.computation_id else ()

    def result(status, value, extra=()):
        return _derived_result(
            OPERATOR_ID,
            prepared.source_digest,
            spec,
            status,
            value,
            prepared.issues + tuple(extra),
            parent_computation_ids=parents,
        )

    if prepared.status != ComputeStatus.COMPUTED or prepared.value is None:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "trace_input_unavailable", "A complete TraceSet is required"
                ),
            ),
        )
    traces = prepared.value
    sequences = [
        tuple(event.activity for event in trace.events) for trace in traces.traces
    ]
    counts = Counter(activity for sequence in sequences for activity in sequence)
    starts = Counter(sequence[0] for sequence in sequences if sequence)
    ends = Counter(sequence[-1] for sequence in sequences if sequence)
    overlap: Counter[tuple[str, str]] = Counter()
    if spec.profile == "plusplus":
        if not isinstance(log, CaseLog):
            return result(
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "interval_source_required",
                        "TraceSet does not preserve start attributes; provide a CaseLog with observed intervals",
                    ),
                ),
            )
        try:
            frequencies, overlap = _interval_counts(
                log, traces, spec, trace_spec or CaseTraceSpec()
            )
        except ValueError as exc:
            return result(
                ComputeStatus.UNAVAILABLE,
                None,
                (ComputeIssue("interval_input_unavailable", str(exc)),),
            )
    else:
        frequencies = Counter(
            pair for sequence in sequences for pair in zip(sequence, sequence[1:])
        )
    eligible = {
        activity
        for activity, count in counts.items()
        if count >= spec.min_activity_count
    }
    usable = Counter(
        {
            pair: count
            for pair, count in frequencies.items()
            if all(a in eligible for a in pair)
        }
    )
    cleaned: Counter[tuple[str, str]] = Counter()
    if spec.dfg_noise_threshold:
        incident_max: dict[str, int] = {}
        for (source, target), count in usable.items():
            incident_max[source] = max(incident_max.get(source, 0), count)
            incident_max[target] = max(incident_max.get(target, 0), count)
        cleaned = Counter(
            {
                pair: count
                for pair, count in usable.items()
                if count
                < spec.dfg_noise_threshold
                * min(incident_max[pair[0]], incident_max[pair[1]])
            }
        )
        for pair in cleaned:
            del usable[pair]
    dependencies: list[HeuristicsDependency] = []
    edges: set[tuple[str, str]] = set()
    for (source, target), count in sorted(usable.items()):
        reverse = usable[target, source]
        concurrent = overlap[tuple(sorted((source, target)))]
        if spec.profile == "classic":
            measure = (
                count / (count + 1)
                if source == target
                else (count - reverse) / (count + reverse + 1)
            )
            selected = measure >= spec.dependency_threshold
        else:
            measure = (count - reverse) / (count + reverse + concurrent)
            selected = measure > spec.dependency_threshold
        selected = selected and count >= spec.min_edge_count
        dependencies.append(
            HeuristicsDependency(
                source, target, count, reverse, concurrent, measure, selected
            )
        )
        if selected:
            edges.add((source, target))
    loops: list[HeuristicsShortLoop] = []
    if spec.profile == "classic":
        for activity in sorted(eligible):
            count = usable[activity, activity]
            if count:
                loops.append(
                    HeuristicsShortLoop(
                        (activity,),
                        count,
                        count / (count + 1),
                        (activity, activity) in edges,
                    )
                )
        triples = Counter(
            (a, b)
            for seq in sequences
            for a, b, c in zip(seq, seq[1:], seq[2:])
            if a == c and a != b
        )
        for left, right in sorted(
            {
                tuple(sorted(pair))
                for pair in triples
                if all(a in eligible for a in pair)
            }
        ):
            count = triples[left, right] + triples[right, left]
            measure = count / (count + 1)
            selected = (
                measure >= spec.loop_two_threshold
                and usable[left, right] >= spec.min_edge_count
                and usable[right, left] >= spec.min_edge_count
            )
            loops.append(HeuristicsShortLoop((left, right), count, measure, selected))
            if selected:
                edges.update(((left, right), (right, left)))
    and_pairs: list[HeuristicsAndPair] = []
    bindings: list[HeuristicsBinding] = []
    remaining = [spec.max_binding_search_states]
    try:
        for activity in sorted(eligible):
            for direction in ("input", "output"):
                neighbours = (
                    {source for source, target in edges if target == activity}
                    if direction == "input"
                    else {target for source, target in edges if source == activity}
                ) - {activity}
                and_related: set[tuple[str, str]] = set()
                for left, right in combinations(sorted(neighbours), 2):
                    numerator = usable[left, right] + usable[right, left]
                    denominator = (
                        usable[left, activity] + usable[right, activity]
                        if direction == "input"
                        else usable[activity, left] + usable[activity, right]
                    )
                    if spec.profile == "classic":
                        denominator += 1
                    else:
                        numerator += overlap[left, right]
                    measure = numerator / denominator
                    selected = (
                        measure >= spec.and_threshold
                        if spec.profile == "classic"
                        else measure > spec.and_threshold
                    )
                    and_pairs.append(
                        HeuristicsAndPair(
                            activity,
                            direction,
                            left,
                            right,
                            numerator,
                            denominator,
                            measure,
                            selected,
                        )
                    )
                    if selected:
                        and_related.add((left, right))
                alternatives = _cliques(neighbours, and_related, remaining)
                bindings.append(HeuristicsBinding(activity, direction, alternatives))
    except _BindingLimit:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "binding_search_limit",
                    "Maximal AND binding enumeration exceeded its explicit search-state limit",
                ),
            ),
        )
    activity_rows = tuple(
        HeuristicsActivity(a, counts[a], starts[a], ends[a]) for a in sorted(counts)
    )
    payload = HeuristicsNet(
        "pix.heuristics.classic.v1"
        if spec.profile == "classic"
        else "pix.heuristics.interval.v1",
        len(sequences),
        sum(not sequence for sequence in sequences),
        tuple(row for row in activity_rows if row.activity in eligible),
        tuple(
            HeuristicsFrequency(a, b, count)
            for (a, b), count in sorted(frequencies.items())
        ),
        tuple(
            HeuristicsFrequency(a, b, count)
            for (a, b), count in sorted(overlap.items())
        ),
        tuple(dependencies),
        tuple(sorted(edges)),
        tuple(loops),
        tuple(and_pairs),
        tuple(bindings),
        tuple(row for row in activity_rows if row.activity not in eligible),
        tuple(
            HeuristicsFrequency(a, b, count)
            for (a, b), count in sorted(cleaned.items())
        ),
    )
    return result(ComputeStatus.COMPUTED, payload)


RESULT_SCHEMAS = {OPERATOR_ID: ("heuristics-net", HeuristicsSpec, HeuristicsNet)}

__all__ = [
    "HeuristicsSpec",
    "HeuristicsNet",
    "HeuristicsActivity",
    "HeuristicsFrequency",
    "HeuristicsDependency",
    "HeuristicsShortLoop",
    "HeuristicsAndPair",
    "HeuristicsBinding",
    "discover_heuristics",
]
