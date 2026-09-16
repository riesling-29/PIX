"""Native frequency-DFG pruning with directed connectivity evidence.

The result is a graph view, not a newly filtered event log. Retained frequencies
are unchanged source measurements. Connectivity means every protected activity
is reachable from an allowed start and can reach an allowed end; it does not
establish trace conformance, minimum graph size or causal order.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from math import isfinite
from typing import ClassVar

from pix.case_centric.discovery import CaseRelationGraph, RelationEdge
from pix.compute._common import _derived_result
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)

Path = tuple[str, str | None, str | None]


def _ratio(value: object, name: str, *, lower: int = 0) -> None:
    if (
        type(value) not in (int, float)
        or (isinstance(value, float) and not isfinite(value))
        or not lower <= value <= 1
    ):
        raise ValueError(f"{name} must be finite and between {lower} and 1")


def _fraction(value: float) -> Fraction:
    # The supplied finite decimal spelling is the documented ratio contract.
    return Fraction(str(value))


@dataclass(frozen=True, slots=True)
class DFGFilterSpec:
    """A concrete graph selection profile, including preservation policy.

    Percentage basis:
    * ``rank_minimum_one`` retains ceil((N-1)*p)+1 initial items when N>0;
    * ``rank`` retains ceil(N*p), including no items when p=0;
    * ``frequency_mass`` retains the prefix reaching p of total frequency.
    ``include_ties`` expands that prefix to all equally scored items.

    ``selected`` protects high-ranked/above-threshold endpoints; ``all`` protects
    all source activities; ``none`` performs exact deletion without reachability
    promises. Connected profiles may retain low-scoring bridge nodes or paths.
    Greedy candidate order is ascending score and then lexical identity.
    """

    mode: str = "path_percentage"
    percentage: int | float = 1.0
    percentage_basis: str = "rank_minimum_one"
    minimum_frequency: int = 0
    threshold: int | float = 0.0
    connectivity: str = "selected"
    include_boundary_paths: bool = True
    include_ties: bool = False
    preserve_paths: tuple[tuple[str, str], ...] = ()
    focus_activity: str | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        modes = (
            "activity_frequency",
            "path_frequency",
            "activity_percentage",
            "path_percentage",
            "dependency",
            "noise",
            "to_activity",
            "from_activity",
            "contain_activity",
        )
        if self.mode not in modes:
            raise ValueError("unsupported DFG filter mode")
        _ratio(self.percentage, "percentage")
        _ratio(
            self.threshold, "threshold", lower=-1 if self.mode == "dependency" else 0
        )
        if self.percentage_basis not in ("rank_minimum_one", "rank", "frequency_mass"):
            raise ValueError("unsupported percentage_basis")
        if type(self.minimum_frequency) is not int or self.minimum_frequency < 0:
            raise ValueError("minimum_frequency must be a nonnegative integer")
        if self.connectivity not in ("none", "selected", "all"):
            raise ValueError("connectivity must be none, selected or all")
        if (
            type(self.include_boundary_paths) is not bool
            or type(self.include_ties) is not bool
        ):
            raise TypeError("include_boundary_paths and include_ties must be bool")
        if (
            not isinstance(self.preserve_paths, tuple)
            or any(
                not isinstance(path, tuple)
                or len(path) != 2
                or not all(isinstance(activity, str) and activity for activity in path)
                for path in self.preserve_paths
            )
            or len(set(self.preserve_paths)) != len(self.preserve_paths)
        ):
            raise ValueError("preserve_paths must contain distinct activity pairs")
        if self.mode not in ("activity_percentage", "path_percentage") and (
            self.percentage != 1.0
            or self.percentage_basis != "rank_minimum_one"
            or self.include_ties
        ):
            raise ValueError("percentage options only apply to percentage modes")
        if self.minimum_frequency != 0 and self.mode not in (
            "activity_frequency",
            "path_frequency",
        ):
            raise ValueError("minimum_frequency only applies to frequency modes")
        if self.threshold != 0.0 and self.mode not in ("dependency", "noise"):
            raise ValueError("threshold only applies to dependency/noise modes")
        if not self.include_boundary_paths and self.mode not in (
            "path_percentage",
            "path_frequency",
        ):
            raise ValueError(
                "boundary path ranking only applies to path percentage/frequency"
            )
        if self.mode in ("to_activity", "from_activity", "contain_activity"):
            if not isinstance(self.focus_activity, str) or not self.focus_activity:
                raise ValueError("focus_activity is required")
            if self.preserve_paths:
                raise ValueError("focus restrictions do not accept preserve_paths")
            if self.connectivity != "selected":
                raise ValueError(
                    "focus restrictions use their own directed route guarantee"
                )
        elif self.focus_activity is not None:
            raise ValueError("focus_activity only applies to focus restriction modes")


@dataclass(frozen=True, slots=True)
class DFGFilterRequest:
    spec: DFGFilterSpec
    input_graph_digest: str | None


@dataclass(frozen=True, slots=True)
class DFGFilterDecision:
    """Original entity, exact original score and its final graph disposition."""

    kind: str
    source: str | None
    target: str | None
    original_count: int
    score_numerator: int
    score_denominator: int
    retained: bool
    reason: str
    required_activities: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DFGBoundaryChange:
    kind: str
    activity: str
    original_count: int | None
    output_count: int
    basis: str = "source_activity_occurrences_at_structural_cut"


@dataclass(frozen=True, slots=True)
class DFGFilterResult:
    graph: CaseRelationGraph
    decisions: tuple[DFGFilterDecision, ...]
    protected_activities: tuple[str, ...]
    boundary_changes: tuple[DFGBoundaryChange, ...]
    reachable_from_start: tuple[str, ...]
    can_reach_end: tuple[str, ...]
    all_retained_on_start_end_routes: bool
    has_start_end_route: bool
    connectivity_guarantee: str
    requested_rank_count: int
    score_population_size: int
    original_activity_count: int
    original_path_count: int
    retained_activity_count: int
    retained_path_count: int
    retained_activity_frequency_fraction: float | None
    retained_path_frequency_fraction: float | None


def _validate_graph(graph: CaseRelationGraph) -> None:
    if not isinstance(graph, CaseRelationGraph):
        raise TypeError("expected a native CaseRelationGraph")
    if graph.relation != "directly_follows":
        raise ValueError("DFG filtering does not accept eventual-follow relations")
    for name in ("trace_count", "empty_trace_count", "examined_event_pairs"):
        value = getattr(graph, name)
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    if graph.empty_trace_count > graph.trace_count or type(graph.complete) is not bool:
        raise ValueError("invalid source trace count or completeness")
    if not all(
        isinstance(items, tuple)
        for items in (
            graph.activity_counts,
            graph.edges,
            graph.start_counts,
            graph.end_counts,
        )
    ):
        raise TypeError("DFG records must be immutable tuples")
    if any(
        not isinstance(record, tuple) or len(record) != 2
        for records in (graph.activity_counts, graph.start_counts, graph.end_counts)
        for record in records
    ):
        raise TypeError("activity and boundary records must be immutable pairs")
    if not all(isinstance(edge, RelationEdge) for edge in graph.edges):
        raise TypeError("edges must be RelationEdge records")
    activities = set()
    for activity, count in graph.activity_counts:
        if (
            not isinstance(activity, str)
            or not activity
            or activity in activities
            or type(count) is not int
            or count <= 0
        ):
            raise ValueError(
                "activities require unique labels and positive integer counts"
            )
        activities.add(activity)
    seen = set()
    for edge in graph.edges:
        key = (edge.source, edge.target)
        if (
            key in seen
            or edge.source not in activities
            or edge.target not in activities
        ):
            raise ValueError("DFG has duplicate or dangling edges")
        if (
            type(edge.count) is not int
            or edge.count <= 0
            or type(edge.case_count) is not int
            or not 0 <= edge.case_count <= edge.count
        ):
            raise ValueError("invalid edge occurrence/case count")
        seen.add(key)
    for records in (graph.start_counts, graph.end_counts):
        if len({activity for activity, _ in records}) != len(records):
            raise ValueError("duplicate boundary records")
        if any(
            activity not in activities or type(count) is not int or count <= 0
            for activity, count in records
        ):
            raise ValueError(
                "boundaries require existing activities and positive counts"
            )


def dfg_digest(graph: CaseRelationGraph) -> str:
    """Ordered native frequency-graph identity; integer values use exact hex."""
    _validate_graph(graph)
    values = [
        graph.relation,
        [[activity, hex(count)] for activity, count in graph.activity_counts],
        [
            [edge.source, edge.target, hex(edge.count), hex(edge.case_count)]
            for edge in graph.edges
        ],
        [[activity, hex(count)] for activity, count in graph.start_counts],
        [[activity, hex(count)] for activity, count in graph.end_counts],
        hex(graph.trace_count),
        hex(graph.empty_trace_count),
        hex(graph.examined_event_pairs),
        graph.complete,
    ]
    data = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode()
    return "pix.case-dfg.v1:sha256:" + sha256(data).hexdigest()


def _reachable(
    initial: set[str], edges: dict[tuple[str, str], object], *, reverse: bool = False
) -> set[str]:
    neighbors: dict[str, set[str]] = {}
    for source, target in edges:
        if reverse:
            source, target = target, source
        neighbors.setdefault(source, set()).add(target)
    seen = set(initial)
    queue = deque(sorted(initial))
    while queue:
        for target in sorted(neighbors.get(queue.popleft(), ())):
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def _ranked_selection(
    scores: dict, counts: dict, spec: DFGFilterSpec
) -> tuple[set, int]:
    # Descending exact score, followed by descending typed lexical identity.
    ranked = sorted(scores, key=lambda key: (scores[key], key), reverse=True)
    p = _fraction(spec.percentage)
    if spec.percentage_basis == "frequency_mass":
        target = p * sum(counts.values())
        cumulative, length = 0, 0
        while length < len(ranked) and cumulative < target:
            cumulative += counts[ranked[length]]
            length += 1
    else:
        n = len(ranked)
        raw = ((n - 1) if spec.percentage_basis == "rank_minimum_one" else n) * p
        length = (raw.numerator + raw.denominator - 1) // raw.denominator
        if spec.percentage_basis == "rank_minimum_one" and n:
            length += 1
        length = min(n, max(0, length))
    if spec.include_ties and length:
        cutoff = scores[ranked[length - 1]]
        while length < len(ranked) and scores[ranked[length]] == cutoff:
            length += 1
    return set(ranked[:length]), length


def _real_paths(edges, starts, ends) -> dict[Path, int]:
    return {
        **{
            ("path", source, target): edge.count
            for (source, target), edge in edges.items()
        },
        **{("start", None, activity): count for activity, count in starts.items()},
        **{("end", activity, None): count for activity, count in ends.items()},
    }


def filter_dfg(
    graph: CaseRelationGraph | ComputationResult[CaseRelationGraph],
    spec: DFGFilterSpec = DFGFilterSpec(),
) -> ComputationResult[DFGFilterResult]:
    """Prune weighted DFG nodes/paths with exact scores and removal witnesses.

    Dependency uses (forward-reverse)/(forward+reverse+1), including zero for
    self-loops; boundary dependencies are one. Noise uses the minimum of each
    endpoint's maximum incoming/outgoing frequency. Scores are computed once
    from the original graph. These profiles never call an upstream library.
    """
    if not isinstance(spec, DFGFilterSpec):
        raise TypeError("spec must be DFGFilterSpec")
    operator = "pix.case_centric.filter_dfg"
    parent_ids = ()
    inherited_issues = ()
    parent_partial = False
    source_digest = None
    if isinstance(graph, ComputationResult):
        parent = graph
        expected_id = computation_identity(
            parent.operator_id,
            parent.operator_version,
            parent.source_digest,
            parent.spec,
            parent.parent_computation_ids,
        )
        if parent.computation_id != expected_id:
            raise ValueError("input graph computation identity is inconsistent")
        parent_ids = (parent.computation_id,) if parent.computation_id else ()
        source_digest = parent.source_digest
        inherited_issues = parent.issues
        parent_partial = parent.status is ComputeStatus.PARTIAL
        if parent.value is None:
            return _derived_result(
                operator,
                source_digest,
                DFGFilterRequest(spec, None),
                parent.status,
                None,
                parent.issues,
                parent_computation_ids=parent_ids,
            )
        graph = parent.value
    if not isinstance(graph, CaseRelationGraph):
        raise TypeError("input must be CaseRelationGraph or its computation result")
    try:
        input_digest = dfg_digest(graph)
    except (TypeError, ValueError) as exc:
        return _derived_result(
            operator,
            source_digest,
            DFGFilterRequest(spec, None),
            ComputeStatus.INVALID_INPUT,
            None,
            inherited_issues + (ComputeIssue("invalid_dfg", str(exc)),),
            parent_computation_ids=parent_ids,
        )
    source_digest = source_digest or input_digest
    request = DFGFilterRequest(spec, input_digest)

    def failed(
        code: str, message: str, status: ComputeStatus = ComputeStatus.INVALID_INPUT
    ):
        return _derived_result(
            operator,
            source_digest,
            request,
            status,
            None,
            inherited_issues + (ComputeIssue(code, message),),
            parent_computation_ids=parent_ids,
        )

    if not graph.complete:
        return failed(
            "incomplete_dfg_counts",
            "Frequency pruning requires complete source edge counts; partial lower bounds cannot establish rankings or thresholds",
            ComputeStatus.UNAVAILABLE,
        )
    original_acts = dict(graph.activity_counts)
    original_edges = {(edge.source, edge.target): edge for edge in graph.edges}
    original_starts = dict(graph.start_counts)
    original_ends = dict(graph.end_counts)
    acts, edges = dict(original_acts), dict(original_edges)
    starts, ends = dict(original_starts), dict(original_ends)
    original_paths = _real_paths(edges, starts, ends)
    activity_scores = {activity: Fraction(count) for activity, count in acts.items()}
    path_scores = {path: Fraction(count) for path, count in original_paths.items()}
    decisions: dict[Path, tuple[str, tuple[str, ...]]] = {}
    boundary_changes = []
    requested_rank_count = 0
    population_size = 0
    explicit = {("path", source, target) for source, target in spec.preserve_paths}
    if not explicit <= set(original_paths):
        return failed(
            "unknown_protected_path",
            "preserve_paths contains a path absent from the input DFG",
        )

    def connectivity_lost(protected: set[str]) -> set[str]:
        forward = _reachable(set(starts), edges)
        backward = _reachable(set(ends), edges, reverse=True)
        return protected - (forward & backward & set(acts))

    def remove_activity(activity: str, reason: str) -> None:
        acts.pop(activity, None)
        decisions[("activity", activity, None)] = (reason, ())
        for source, target in tuple(edges):
            if activity in (source, target):
                edges.pop((source, target))
                decisions[("path", source, target)] = (
                    "remove_incident_activity",
                    (activity,),
                )
        if activity in starts:
            starts.pop(activity)
            decisions[("start", None, activity)] = (
                "remove_incident_activity",
                (activity,),
            )
        if activity in ends:
            ends.pop(activity)
            decisions[("end", activity, None)] = (
                "remove_incident_activity",
                (activity,),
            )

    def remove_path(path: Path) -> None:
        kind, source, target = path
        if kind == "path":
            edges.pop((source, target), None)
        elif kind == "start":
            starts.pop(target, None)
        else:
            ends.pop(source, None)

    def restore_path(path: Path) -> None:
        kind, source, target = path
        if kind == "path":
            edges[(source, target)] = original_edges[(source, target)]
        elif kind == "start":
            starts[target] = original_starts[target]
        else:
            ends[source] = original_ends[source]

    def prune_unreachable() -> None:
        retained = _reachable(set(starts), edges) & _reachable(
            set(ends), edges, reverse=True
        )
        for activity in sorted(set(acts) - retained):
            remove_activity(activity, "remove_unreachable")

    if spec.mode in ("to_activity", "from_activity", "contain_activity"):
        focus = spec.focus_activity
        if focus not in acts:
            return failed(
                "unknown_focus_activity", "Focus activity is absent from the input DFG"
            )
        if focus in connectivity_lost({focus}):
            return failed(
                "unreachable_focus_activity",
                "Focus activity is not on an original start-to-end route",
            )
        before = _reachable({focus}, edges, reverse=True)
        after = _reachable({focus}, edges)
        if spec.mode == "to_activity":
            for path in tuple(edges):
                if path[0] == focus:
                    remove_path(("path", *path))
                    decisions[("path", *path)] = ("remove_focus_outgoing", ())
            for activity in ends:
                if activity != focus:
                    decisions[("end", activity, None)] = ("remove_focus_boundary", ())
            ends = {focus: acts[focus]}
            boundary_changes.append(
                DFGBoundaryChange("end", focus, original_ends.get(focus), acts[focus])
            )
            desired = before
        elif spec.mode == "from_activity":
            for path in tuple(edges):
                if path[1] == focus:
                    remove_path(("path", *path))
                    decisions[("path", *path)] = ("remove_focus_incoming", ())
            for activity in starts:
                if activity != focus:
                    decisions[("start", None, activity)] = ("remove_focus_boundary", ())
            starts = {focus: acts[focus]}
            boundary_changes.append(
                DFGBoundaryChange(
                    "start", focus, original_starts.get(focus), acts[focus]
                )
            )
            desired = after
        else:
            desired = before | after
            for activity in tuple(starts):
                if activity not in before:
                    starts.pop(activity)
                    decisions[("start", None, activity)] = ("remove_focus_boundary", ())
            for activity in tuple(ends):
                if activity not in after:
                    ends.pop(activity)
                    decisions[("end", activity, None)] = ("remove_focus_boundary", ())
        for activity in sorted(set(acts) - desired):
            remove_activity(activity, "remove_outside_focus_cone")
        prune_unreachable()
        protected = {focus}
        guarantee = "retained_nodes_on_start_end_routes_in_focus_cone"
    elif spec.mode in ("activity_frequency", "activity_percentage"):
        population_size = len(acts)
        if spec.mode == "activity_percentage":
            required, requested_rank_count = _ranked_selection(
                activity_scores, acts, spec
            )
        else:
            required = {
                activity
                for activity, count in acts.items()
                if count >= spec.minimum_frequency
            }
            requested_rank_count = len(required)
        required |= {
            activity for _, source, target in explicit for activity in (source, target)
        }
        protected = set(acts) if spec.connectivity == "all" else set(required)
        if spec.connectivity != "none" and connectivity_lost(protected):
            return failed(
                "unreachable_protected_activities",
                "The input has protected activities without a start-to-end route",
            )
        for activity in sorted(
            set(acts) - required,
            key=lambda activity: (activity_scores[activity], activity),
        ):
            if spec.connectivity == "none":
                remove_activity(activity, "remove_frequency_or_rank")
                continue
            saved = (dict(acts), dict(edges), dict(starts), dict(ends), dict(decisions))
            remove_activity(activity, "remove_frequency_or_rank")
            lost = connectivity_lost(protected)
            if lost:
                acts, edges, starts, ends, decisions = saved
                decisions[("activity", activity, None)] = (
                    "keep_connectivity",
                    tuple(sorted(lost)),
                )
        if spec.connectivity != "none":
            prune_unreachable()
        guarantee = (
            "all_retained_nodes_on_start_end_routes"
            if spec.connectivity != "none"
            else "none"
        )
    else:
        if spec.mode in ("path_frequency", "path_percentage"):
            candidate_counts = (
                original_paths
                if spec.include_boundary_paths
                else {
                    path: count
                    for path, count in original_paths.items()
                    if path[0] == "path"
                }
            )
            population_size = len(candidate_counts)
            if spec.mode == "path_percentage":
                required, requested_rank_count = _ranked_selection(
                    {path: path_scores[path] for path in candidate_counts},
                    candidate_counts,
                    spec,
                )
            else:
                required = {
                    path
                    for path, count in candidate_counts.items()
                    if count >= spec.minimum_frequency
                }
                requested_rank_count = len(required)
            candidates = set(candidate_counts) - required
            required |= set(original_paths) - set(candidate_counts)
        elif spec.mode == "dependency":
            for (source, target), edge in edges.items():
                reverse = original_edges.get((target, source))
                inverse = reverse.count if reverse else 0
                path_scores[("path", source, target)] = Fraction(
                    edge.count - inverse, edge.count + inverse + 1
                )
            for path in path_scores:
                if path[0] != "path":
                    path_scores[path] = Fraction(1)
            required = {
                path
                for path, score in path_scores.items()
                if score >= _fraction(spec.threshold)
            }
            candidates = set(original_paths) - required
            population_size, requested_rank_count = len(original_paths), len(required)
        else:
            maxima = {activity: 0 for activity in acts}
            for (source, target), edge in edges.items():
                maxima[source] = max(maxima[source], edge.count)
                maxima[target] = max(maxima[target], edge.count)
            for (source, target), edge in edges.items():
                path_scores[("path", source, target)] = Fraction(
                    edge.count, min(maxima[source], maxima[target])
                )
            required = {
                path
                for path in original_paths
                if path[0] != "path" or path_scores[path] >= _fraction(spec.threshold)
            }
            candidates = set(original_paths) - required
            population_size, requested_rank_count = (
                len(edges),
                len(required & {path for path in original_paths if path[0] == "path"}),
            )
        required |= explicit
        candidates -= explicit
        protected = (
            set(acts)
            if spec.connectivity == "all"
            else {
                activity
                for _, source, target in required
                for activity in (source, target)
                if activity is not None
            }
        )
        if spec.connectivity != "none" and connectivity_lost(protected):
            return failed(
                "unreachable_protected_activities",
                "The input has protected activities without a start-to-end route",
            )
        for path in sorted(candidates, key=lambda path: (path_scores[path], path)):
            remove_path(path)
            lost = (
                connectivity_lost(protected) if spec.connectivity != "none" else set()
            )
            if lost:
                restore_path(path)
                decisions[path] = ("keep_connectivity", tuple(sorted(lost)))
            else:
                decisions[path] = ("remove_frequency_or_rank", ())
        if spec.connectivity != "none":
            prune_unreachable()
        guarantee = (
            "all_retained_nodes_on_start_end_routes"
            if spec.connectivity != "none"
            else "none"
        )

    forward = _reachable(set(starts), edges) & set(acts)
    backward = _reachable(set(ends), edges, reverse=True) & set(acts)
    actual_routes = forward & backward
    if spec.connectivity != "none" and (
        not protected <= actual_routes or set(acts) != actual_routes
    ):
        return failed(
            "connectivity_postcondition_failed",
            "The requested directed preservation guarantee could not be established",
            ComputeStatus.UNAVAILABLE,
        )
    output = replace(
        graph,
        activity_counts=tuple(
            (activity, count)
            for activity, count in graph.activity_counts
            if activity in acts
        ),
        edges=tuple(
            edge for edge in graph.edges if (edge.source, edge.target) in edges
        ),
        start_counts=tuple(sorted(starts.items())),
        end_counts=tuple(sorted(ends.items())),
    )
    output_paths = _real_paths(edges, starts, ends)
    all_entities = {
        **{
            ("activity", activity, None): count
            for activity, count in original_acts.items()
        },
        **original_paths,
    }
    evidence = []
    for entity, count in sorted(all_entities.items()):
        kind, source, target = entity
        retained = source in acts if kind == "activity" else entity in output_paths
        score = activity_scores[source] if kind == "activity" else path_scores[entity]
        reason, required_by = decisions.get(
            entity,
            (
                "keep_explicit"
                if entity in explicit
                else "keep_selected_or_unmodified",
                (),
            ),
        )
        if not retained and reason.startswith("keep"):
            reason = "remove_unreachable"
        evidence.append(
            DFGFilterDecision(
                kind,
                source,
                target,
                count,
                score.numerator,
                score.denominator,
                retained,
                reason,
                required_by,
            )
        )
    activity_total = sum(original_acts.values())
    path_total = sum(edge.count for edge in original_edges.values())
    value = DFGFilterResult(
        output,
        tuple(evidence),
        tuple(sorted(protected)),
        tuple(boundary_changes),
        tuple(sorted(forward)),
        tuple(sorted(backward)),
        set(acts) == actual_routes,
        bool(actual_routes),
        guarantee,
        requested_rank_count,
        population_size,
        len(original_acts),
        len(original_edges),
        len(acts),
        len(edges),
        float(Fraction(sum(acts.values()), activity_total)) if activity_total else None,
        float(Fraction(sum(edge.count for edge in edges.values()), path_total))
        if path_total
        else None,
    )
    return _derived_result(
        operator,
        source_digest,
        request,
        ComputeStatus.PARTIAL if parent_partial else ComputeStatus.COMPUTED,
        value,
        inherited_issues,
        parent_computation_ids=parent_ids,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.filter_dfg": (
        "dfg-filter-view",
        DFGFilterRequest,
        DFGFilterResult,
    )
}

__all__ = [
    "DFGFilterSpec",
    "DFGFilterRequest",
    "DFGFilterDecision",
    "DFGBoundaryChange",
    "DFGFilterResult",
    "dfg_digest",
    "filter_dfg",
]
