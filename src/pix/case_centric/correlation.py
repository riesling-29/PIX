"""Native correlation mining through exact balanced transportation.

Classic pooling, explicit event chunks and supplied-case grouping share the
same mathematical optimizer. The inferred activity flows are estimates, not
observed directly-follows facts or reconstructed case assignments. Balanced
incoming/outgoing occurrence constraints can require penalty-cost reverse or
self edges; such edges remain visible rather than silently removed.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_traces

Rational = tuple[int, int]
OPERATOR_ID = "pix.case_centric.discover_correlation"


def _pair(value: Fraction) -> Rational:
    return value.numerator, value.denominator


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


@dataclass(frozen=True, slots=True)
class CorrelationEvent:
    """An independently identified observation; no fabricated case membership.

    None start denotes a point observation at completion. None completion is
    retained as missing evidence and makes correlation unavailable.
    """

    event_id: str
    activity: str
    completion: datetime | None
    start: datetime | None = None
    case_id: str | None = None

    def __post_init__(self) -> None:
        _text(self.event_id, "event_id")
        _text(self.activity, "activity")
        if self.case_id is not None:
            _text(self.case_id, "case_id")
        for name in ("completion", "start"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, datetime) or value.utcoffset() is None:
                    raise ValueError(
                        f"{name} requires a timezone-aware datetime or None"
                    )
                object.__setattr__(self, name, value.astimezone(timezone.utc))


@dataclass(frozen=True, slots=True)
class CorrelationSpec:
    variant: str = "classic"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    start_attribute: str | None = None
    duration_matching: str = "greedy_min"
    matching_boundary: str = "strict"
    split_size: int = 100_000
    split_order: str = "source"
    penalty_cost: Rational = (100_000_000_000, 1)
    max_events: int = 10_000
    max_activity_pairs: int = 4_096
    max_pair_evaluations: int = 400_000
    max_augmentations: int = 100_000
    max_group_cells: int = 400_000
    max_relaxations: int = 2_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.variant not in ("classic", "classic_split", "trace_based"):
            raise ValueError("unsupported correlation variant")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if self.start_attribute is not None:
            _text(self.start_attribute, "start_attribute")
        if self.duration_matching not in ("greedy_min", "exact_max_cardinality"):
            raise ValueError("unsupported duration_matching")
        if self.matching_boundary not in ("strict", "inclusive"):
            raise ValueError("matching_boundary must be strict or inclusive")
        if self.split_order not in ("source", "completion_start"):
            raise ValueError("split_order must be source or completion_start")
        if (
            not isinstance(self.penalty_cost, tuple)
            or len(self.penalty_cost) != 2
            or any(type(x) is not int for x in self.penalty_cost)
            or self.penalty_cost[0] <= 0
            or self.penalty_cost[1] <= 0
        ):
            raise ValueError("penalty_cost must be a positive rational pair")
        object.__setattr__(self, "penalty_cost", _pair(Fraction(*self.penalty_cost)))
        for name in (
            "split_size",
            "max_events",
            "max_activity_pairs",
            "max_pair_evaluations",
            "max_augmentations",
            "max_group_cells",
            "max_relaxations",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class DurationMatch:
    source_event_id: str
    target_event_id: str
    seconds: Rational


@dataclass(frozen=True, slots=True)
class CorrelationCell:
    source_activity: str
    target_activity: str
    precedence: Rational
    compared_pair_count: int
    preceding_pair_count: int
    duration_seconds: Rational | None
    matching_method: str
    duration_witnesses: tuple[DurationMatch, ...]
    cost: Rational
    penalty_applied: bool


@dataclass(frozen=True, slots=True)
class CorrelationEdge:
    source_activity: str
    target_activity: str
    estimated_frequency: int
    duration_seconds: Rational | None
    unit_cost: Rational
    penalty_applied: bool


@dataclass(frozen=True, slots=True)
class CorrelationModel:
    activities: tuple[tuple[str, int], ...]
    source_event_ids: tuple[str, ...]
    groups: tuple[tuple[str, ...], ...]
    cells: tuple[CorrelationCell, ...]
    edges: tuple[CorrelationEdge, ...]
    objective: Rational
    transported_occurrences: int
    optimization_augmentations: int
    optimization_relaxations: int
    evaluated_pairs: int
    penalty_flow: int


class _Limit(Exception):
    pass


class _Work:
    def __init__(self, spec):
        self.spec = spec
        self.pairs = 0
        self.augmentations = 0
        self.relaxations = 0

    def add_pairs(self, count):
        self.pairs += count
        if self.pairs > self.spec.max_pair_evaluations:
            raise _Limit("max_pair_evaluations")

    def augment(self):
        self.augmentations += 1
        if self.augmentations > self.spec.max_augmentations:
            raise _Limit("max_augmentations")

    def relax(self):
        self.relaxations += 1
        if self.relaxations > self.spec.max_relaxations:
            raise _Limit("max_relaxations")


def _transport(supply, demand, costs, work):
    """Integral min-cost maximum flow; negative residual costs handled exactly."""
    left, right = len(supply), len(demand)
    sink = left + right + 1
    graph = [[] for _ in range(sink + 1)]

    def edge(a, b, capacity, cost):
        forward = [b, len(graph[b]), capacity, cost]
        backward = [a, len(graph[a]), 0, -cost]
        graph[a].append(forward)
        graph[b].append(backward)
        return forward

    for i, capacity in enumerate(supply):
        edge(0, i + 1, capacity, Fraction())
    refs = {}
    for i in range(left):
        for j in range(right):
            cost = costs[i][j]
            if cost is not None:
                capacity = min(supply[i], demand[j])
                refs[(i, j)] = (edge(i + 1, left + j + 1, capacity, cost), capacity)
    for j, capacity in enumerate(demand):
        edge(left + j + 1, sink, capacity, Fraction())
    sent = 0
    while sent < min(sum(supply), sum(demand)):
        distance, predecessor = [None] * len(graph), [None] * len(graph)
        distance[0] = Fraction()
        for _ in range(len(graph) - 1):
            changed = False
            for node, edges in enumerate(graph):
                if distance[node] is None:
                    continue
                for ei, (target, _, capacity, cost) in enumerate(edges):
                    if capacity <= 0:
                        continue
                    work.relax()
                    candidate = distance[node] + cost
                    if distance[target] is None or candidate < distance[target]:
                        distance[target] = candidate
                        predecessor[target] = (node, ei)
                        changed = True
            if not changed:
                break
        if predecessor[sink] is None:
            break
        work.augment()
        amount, node = min(sum(supply), sum(demand)) - sent, sink
        while node:
            previous, ei = predecessor[node]
            amount = min(amount, graph[previous][ei][2])
            node = previous
        node = sink
        while node:
            previous, ei = predecessor[node]
            forward = graph[previous][ei]
            forward[2] -= amount
            graph[node][forward[1]][2] += amount
            node = previous
        sent += amount
    flows = tuple(
        (i, j, original - ref[2])
        for (i, j), (ref, original) in sorted(refs.items())
        if original != ref[2]
    )
    objective = sum((costs[i][j] * amount for i, j, amount in flows), Fraction())
    return sent, objective, flows


def _seconds(first, second):
    delta = second - first
    micros = (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
    return Fraction(micros, 1_000_000)


def _allowed(first, second, boundary):
    return first <= second if boundary == "inclusive" else first < second


def _match(left, right, method, boundary, work):
    ends = sorted(left, key=lambda e: (e.completion, e.event_id))
    starts = sorted(right, key=lambda e: (e.start or e.completion, e.event_id))
    if method == "exact_max_cardinality":
        work.add_pairs(len(ends) * len(starts))
        costs = tuple(
            tuple(
                _seconds(a.completion, b.start or b.completion)
                if _allowed(a.completion, b.start or b.completion, boundary)
                else None
                for b in starts
            )
            for a in ends
        )
        _, _, flows = _transport((1,) * len(ends), (1,) * len(starts), costs, work)
        return tuple(
            DurationMatch(ends[i].event_id, starts[j].event_id, _pair(costs[i][j]))
            for i, j, _ in flows
        )
    pairs = []
    if method == "fifo":
        target = 0
        for source in ends:
            while target < len(starts) and not _allowed(
                source.completion,
                starts[target].start or starts[target].completion,
                boundary,
            ):
                target += 1
            if target < len(starts):
                other = starts[target]
                pairs.append(
                    DurationMatch(
                        source.event_id,
                        other.event_id,
                        _pair(
                            _seconds(source.completion, other.start or other.completion)
                        ),
                    )
                )
                target += 1
    else:
        source = len(ends) - 1
        for other in reversed(starts):
            while source >= 0 and not _allowed(
                ends[source].completion, other.start or other.completion, boundary
            ):
                source -= 1
            if source >= 0:
                first = ends[source]
                pairs.append(
                    DurationMatch(
                        first.event_id,
                        other.event_id,
                        _pair(
                            _seconds(first.completion, other.start or other.completion)
                        ),
                    )
                )
                source -= 1
    return tuple(pairs)


def _average(matches):
    return (
        sum((Fraction(*m.seconds) for m in matches), Fraction()) / len(matches)
        if matches
        else None
    )


def _source_events(log, spec):
    if isinstance(log, CaseLog):
        parent = case_traces(log, spec.trace_spec)
        source, parents, inherited = (
            parent.source_digest,
            (parent.computation_id,),
            parent.issues,
        )
        if parent.value is None:
            return (), source, parents, inherited, True
        events, issues = [], []
        for raw_trace, trace in zip(log.traces, parent.value.traces):
            for raw, event in zip(raw_trace.events, trace.events):
                start = None
                if spec.start_attribute is not None:
                    attribute = log.attribute(raw, spec.start_attribute)
                    if (
                        attribute is None
                        or attribute.type != "date"
                        or attribute.value.utcoffset() is None
                    ):
                        issues.append(
                            ComputeIssue(
                                "missing_correlation_start",
                                "Explicit start observation is unavailable.",
                                (raw.id,),
                            )
                        )
                    else:
                        start = attribute.value
                try:
                    events.append(
                        CorrelationEvent(
                            event.event_id,
                            event.activity,
                            event.time,
                            start,
                            trace.object_id,
                        )
                    )
                except (ValueError, OverflowError) as error:
                    issues.append(
                        ComputeIssue("invalid_correlation_time", str(error), (raw.id,))
                    )
        return tuple(events), source, parents, inherited + tuple(issues), bool(issues)
    if not isinstance(log, tuple) or not all(
        isinstance(e, CorrelationEvent) for e in log
    ):
        raise TypeError("log must be CaseLog or tuple[CorrelationEvent, ...]")
    if len({e.event_id for e in log}) != len(log):
        raise ValueError("CorrelationEvent identities must be unique")
    facts = tuple(
        (
            e.event_id,
            e.activity,
            e.completion.isoformat() if e.completion else None,
            e.start.isoformat() if e.start else None,
            e.case_id,
        )
        for e in log
    )
    digest = hashlib.sha256(
        json.dumps(facts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return log, "pix.correlation-events.v1:sha256:" + digest, (), (), False


def discover_correlation(
    log: CaseLog | tuple[CorrelationEvent, ...],
    spec: CorrelationSpec = CorrelationSpec(),
) -> ComputationResult[CorrelationModel]:
    """Estimate activity flows without assigning missing case identifiers.

    Classic pools observations. Classic-split uses explicit source/completion-start
    chunks, unweighted chunk mean precedence and maximum chunk duration. Trace-based
    uses only supplied cases, pair-weighted precedence and pooled matching samples.
    Exact duration matching means maximum cardinality then minimum total duration,
    not unconstrained minimum-average subset selection. Greedy-min compares pooled
    FIFO/reverse-LIFO averages. Precedence always uses strict completion < start.

    The transportation constraints require incoming=outgoing=activity occurrences,
    including self and penalty edges. Output is an inferred balanced flow model,
    not a claim of causality, recovered traces, or classical observed DFG counts.
    """
    if not isinstance(spec, CorrelationSpec):
        raise TypeError("spec must be CorrelationSpec")
    events, source, parents, inherited, failed = _source_events(log, spec)

    def result(value=None, issues=(), unavailable=False):
        return _derived_result(
            OPERATOR_ID,
            source,
            spec,
            ComputeStatus.UNAVAILABLE if unavailable else ComputeStatus.COMPUTED,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if failed:
        return result(unavailable=True)
    invalid = tuple(
        e.event_id
        for e in events
        if e.completion is None or (e.start is not None and e.completion < e.start)
    )
    if invalid:
        return result(
            issues=(
                ComputeIssue(
                    "invalid_correlation_interval",
                    "Every selected event requires a valid observed interval or point timestamp.",
                    invalid,
                ),
            ),
            unavailable=True,
        )
    counts = Counter(e.activity for e in events)
    activities = tuple(sorted(counts))
    if len(events) > spec.max_events or len(activities) ** 2 > spec.max_activity_pairs:
        return result(
            issues=(
                ComputeIssue(
                    "correlation_resource_limit",
                    "Event or activity-pair limit exceeded.",
                ),
            ),
            unavailable=True,
        )
    if spec.variant == "trace_based":
        if any(e.case_id is None for e in events):
            return result(
                issues=(
                    ComputeIssue(
                        "case_membership_required",
                        "Trace-based correlation requires supplied case membership; none is inferred.",
                    ),
                ),
                unavailable=True,
            )
        grouped = defaultdict(list)
        for event in events:
            grouped[event.case_id].append(event)
        groups = tuple(tuple(group) for group in grouped.values())
    elif spec.variant == "classic_split":
        stream = events
        if spec.split_order == "completion_start":
            stream = tuple(
                sorted(
                    enumerate(events),
                    key=lambda x: (
                        x[1].completion,
                        x[1].start or x[1].completion,
                        x[0],
                    ),
                )
            )
            stream = tuple(e for _, e in stream)
        groups = tuple(
            stream[i : i + spec.split_size]
            for i in range(0, len(stream), spec.split_size)
        )
    else:
        groups = (events,) if events else ()
    if len(groups) * len(activities) ** 2 > spec.max_group_cells:
        return result(
            issues=(
                ComputeIssue(
                    "correlation_resource_limit",
                    "Group matrix cell limit exceeded before materialization.",
                ),
            ),
            unavailable=True,
        )
    work, cells = _Work(spec), []
    penalty = Fraction(*spec.penalty_cost)
    try:
        group_maps = tuple(
            {a: tuple(e for e in group if e.activity == a) for a in activities}
            for group in groups
        )
        for first in activities:
            for second in activities:
                compared = preceding = 0
                probabilities, duration_groups = [], []
                if first != second:
                    for group in group_maps:
                        left, right = group[first], group[second]
                        possible = len(left) * len(right)
                        work.add_pairs(possible)
                        before = sum(
                            a.completion < (b.start or b.completion)
                            for a in left
                            for b in right
                        )
                        compared += possible
                        preceding += before
                        probabilities.append(
                            Fraction(before, possible) if possible else Fraction()
                        )
                        if spec.duration_matching == "greedy_min":
                            fifo = _match(
                                left, right, "fifo", spec.matching_boundary, work
                            )
                            reverse = _match(
                                left,
                                right,
                                "reverse_lifo",
                                spec.matching_boundary,
                                work,
                            )
                            duration_groups.append((fifo, reverse))
                        else:
                            exact = _match(
                                left,
                                right,
                                "exact_max_cardinality",
                                spec.matching_boundary,
                                work,
                            )
                            duration_groups.append((exact,))
                precedence = (
                    (
                        sum(probabilities, Fraction()) / len(groups)
                        if groups
                        else Fraction()
                    )
                    if spec.variant == "classic_split"
                    else (Fraction(preceding, compared) if compared else Fraction())
                )
                selected, method = (), spec.duration_matching
                if spec.variant == "classic_split":
                    options = []
                    for variants in duration_groups:
                        usable = [
                            (_average(matches), index, matches)
                            for index, matches in enumerate(variants)
                            if matches
                        ]
                        if usable:
                            options.append(min(usable, key=lambda x: (x[0], x[1])))
                    if options:
                        duration, chosen, selected = max(options, key=lambda x: x[0])
                        method = (
                            ("fifo" if chosen == 0 else "reverse_lifo")
                            if spec.duration_matching == "greedy_min"
                            else spec.duration_matching
                        )
                    else:
                        duration = None
                else:
                    pooled = tuple(
                        tuple(
                            match
                            for variants in duration_groups
                            for match in variants[index]
                        )
                        for index in range(
                            2 if spec.duration_matching == "greedy_min" else 1
                        )
                    )
                    usable = [
                        (_average(matches), index, matches)
                        for index, matches in enumerate(pooled)
                        if matches
                    ]
                    if usable:
                        duration, chosen, selected = min(
                            usable, key=lambda x: (x[0], x[1])
                        )
                        method = (
                            ("fifo" if chosen == 0 else "reverse_lifo")
                            if spec.duration_matching == "greedy_min"
                            else spec.duration_matching
                        )
                    else:
                        duration = None
                applied = precedence == 0 or duration is None or duration == 0
                cost = (
                    penalty
                    if applied
                    else duration / precedence / min(counts[first], counts[second])
                )
                cells.append(
                    CorrelationCell(
                        first,
                        second,
                        _pair(precedence),
                        compared,
                        preceding,
                        _pair(duration) if duration is not None else None,
                        method,
                        selected,
                        _pair(cost),
                        applied,
                    )
                )
        lookup = {(c.source_activity, c.target_activity): c for c in cells}
        costs = tuple(
            tuple(Fraction(*lookup[(a, b)].cost) for b in activities)
            for a in activities
        )
        supply = tuple(counts[a] for a in activities)
        transported, objective, flows = _transport(supply, supply, costs, work)
    except _Limit as error:
        return result(
            issues=(
                ComputeIssue(
                    "correlation_resource_limit",
                    f"{error} exhausted; no incomplete optimal model returned.",
                ),
            ),
            unavailable=True,
        )
    edges = []
    for i, j, frequency in flows:
        cell = lookup[(activities[i], activities[j])]
        edges.append(
            CorrelationEdge(
                cell.source_activity,
                cell.target_activity,
                frequency,
                cell.duration_seconds,
                cell.cost,
                cell.penalty_applied,
            )
        )
    penalty_flow = sum(e.estimated_frequency for e in edges if e.penalty_applied)
    diagnostics = (
        (
            ComputeIssue(
                "estimated_penalty_edges",
                "Balanced-flow constraints selected penalty edges; these are not temporal or causal evidence.",
            ),
        )
        if penalty_flow
        else ()
    )
    return result(
        CorrelationModel(
            tuple((a, counts[a]) for a in activities),
            tuple(e.event_id for e in events),
            tuple(tuple(e.event_id for e in group) for group in groups),
            tuple(cells),
            tuple(edges),
            _pair(objective),
            transported,
            work.augmentations,
            work.relaxations,
            work.pairs,
            penalty_flow,
        ),
        diagnostics,
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("case-correlation-model", CorrelationSpec, CorrelationModel)
}
__all__ = [
    "CorrelationEvent",
    "CorrelationSpec",
    "CorrelationModel",
    "discover_correlation",
]
