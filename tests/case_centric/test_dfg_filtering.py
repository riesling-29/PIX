"""Native DFG filtering checked by fixed graphs and transitive-closure oracles."""

from dataclasses import FrozenInstanceError, replace
from itertools import combinations

import pytest

from pix.case_centric.dfg_filtering import DFGFilterSpec, dfg_digest, filter_dfg
from pix.case_centric.discovery import (
    CaseRelationGraph,
    RelationDiscoverySpec,
    RelationEdge,
    discover_dfg,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import result_from_json, result_json_bytes


def graph(activities, paths, starts, ends, *, complete=True):
    return CaseRelationGraph(
        "directly_follows",
        tuple(activities.items()),
        tuple(
            RelationEdge(a, b, count, min(1, count)) for (a, b), count in paths.items()
        ),
        tuple(starts.items()),
        tuple(ends.items()),
        max(sum(starts.values()), sum(ends.values()), 1),
        0,
        sum(paths.values()),
        complete,
    )


def diamond():
    return graph(
        {"S": 11, "A": 10, "B": 1, "E": 11},
        {("S", "A"): 10, ("A", "E"): 10, ("S", "B"): 1, ("B", "E"): 1},
        {"S": 11},
        {"E": 11},
    )


def nodes(result):
    assert result.value is not None, result.issues
    return {activity for activity, _ in result.value.graph.activity_counts}


def paths(result):
    assert result.value is not None, result.issues
    return {(edge.source, edge.target): edge.count for edge in result.value.graph.edges}


def decision(result, kind, source, target):
    return next(
        item
        for item in result.value.decisions
        if (item.kind, item.source, item.target) == (kind, source, target)
    )


def test_activity_percentage_preserves_necessary_low_frequency_backbone():
    source = diamond()
    result = filter_dfg(
        source, DFGFilterSpec(mode="activity_percentage", percentage=0.1)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert nodes(result) == {"S", "A", "E"}
    assert paths(result) == {("S", "A"): 10, ("A", "E"): 10}
    assert result.value.protected_activities == ("E", "S")
    assert result.value.requested_rank_count == 2
    retained_bridge = decision(result, "activity", "A", None)
    assert retained_bridge.reason == "keep_connectivity"
    assert retained_bridge.required_activities == ("E", "S")
    assert decision(result, "activity", "B", None).retained is False
    assert result.value.all_retained_on_start_end_routes
    assert result.value.graph.trace_count == source.trace_count
    assert dict(result.value.graph.activity_counts)["E"] == 11  # not recounted as 10


@pytest.mark.parametrize(
    "basis,p,expected",
    [
        ("rank_minimum_one", 0.0, {"S"}),
        ("rank", 0.0, set()),
        ("rank", 0.25, {"S"}),
        ("rank", 0.5, {"S", "E"}),
        ("frequency_mass", 0.5, {"S", "E"}),
        ("rank_minimum_one", 1.0, {"S", "A", "B", "E"}),
    ],
)
def test_percentage_definitions_are_explicit_not_conflated(basis, p, expected):
    result = filter_dfg(
        diamond(),
        DFGFilterSpec(
            mode="activity_percentage",
            percentage=p,
            percentage_basis=basis,
            connectivity="none",
        ),
    )
    assert nodes(result) == expected


def test_ties_expand_rank_but_default_ties_are_deterministic():
    source = diamond()
    exact = filter_dfg(
        source,
        DFGFilterSpec(mode="activity_percentage", percentage=0, connectivity="none"),
    )
    tied = filter_dfg(
        source,
        DFGFilterSpec(
            mode="activity_percentage",
            percentage=0,
            connectivity="none",
            include_ties=True,
        ),
    )
    assert nodes(exact) == {"S"}
    assert nodes(tied) == {"S", "E"}
    assert tied.value.requested_rank_count == 2


@pytest.mark.parametrize(
    "connectivity,expected_nodes,expected_paths",
    [
        ("none", {"S", "A", "B", "E"}, {("S", "A"), ("A", "E")}),
        ("selected", {"S", "A", "E"}, {("S", "A"), ("A", "E")}),
        ("all", {"S", "A", "B", "E"}, {("S", "A"), ("A", "E"), ("S", "B"), ("B", "E")}),
    ],
)
def test_path_threshold_none_selected_all_preservation(
    connectivity, expected_nodes, expected_paths
):
    result = filter_dfg(
        diamond(),
        DFGFilterSpec(
            mode="path_frequency", minimum_frequency=5, connectivity=connectivity
        ),
    )
    assert nodes(result) == expected_nodes
    assert set(paths(result)) == expected_paths
    if connectivity == "none":
        assert not result.value.all_retained_on_start_end_routes
        assert result.value.connectivity_guarantee == "none"
    else:
        assert result.value.all_retained_on_start_end_routes


def test_direct_activity_threshold_can_drop_boundary_but_selected_restores_route():
    source = graph(
        {"S": 1, "A": 100, "E": 1}, {("S", "A"): 1, ("A", "E"): 1}, {"S": 1}, {"E": 1}
    )
    threshold = DFGFilterSpec(
        mode="activity_frequency", minimum_frequency=50, connectivity="none"
    )
    raw = filter_dfg(source, threshold)
    assert nodes(raw) == {"A"}
    assert not raw.value.has_start_end_route
    connected = filter_dfg(source, replace(threshold, connectivity="selected"))
    assert nodes(connected) == {"S", "A", "E"}
    assert decision(connected, "activity", "S", None).reason == "keep_connectivity"


def test_path_percentages_include_boundary_paths_only_when_requested():
    source = graph(
        {"A": 100, "B": 100, "C": 10},
        {("A", "B"): 100, ("B", "C"): 10},
        {"A": 200},
        {"C": 200},
    )
    spec = DFGFilterSpec(mode="path_percentage", percentage=0, connectivity="none")
    with_boundaries = filter_dfg(source, spec)
    without = filter_dfg(source, replace(spec, include_boundary_paths=False))
    assert with_boundaries.value.score_population_size == 4
    assert without.value.score_population_size == 2
    assert paths(with_boundaries) == {}
    assert paths(without) == {("A", "B"): 100}
    assert without.value.graph.start_counts == source.start_counts
    assert without.value.graph.end_counts == source.end_counts


def test_cumulative_path_mass_is_frequency_weighted():
    source = graph(
        {"A": 9, "B": 9, "C": 1}, {("A", "B"): 9, ("B", "C"): 1}, {"A": 1}, {"C": 1}
    )
    result = filter_dfg(
        source,
        DFGFilterSpec(
            mode="path_percentage",
            percentage=0.8,
            percentage_basis="frequency_mass",
            include_boundary_paths=False,
            connectivity="none",
        ),
    )
    assert paths(result) == {("A", "B"): 9}
    assert result.value.retained_path_frequency_fraction == 0.9


def test_zero_rank_can_return_empty_graph_without_fabricating_routes():
    result = filter_dfg(
        diamond(),
        DFGFilterSpec(mode="path_percentage", percentage=0, percentage_basis="rank"),
    )
    assert nodes(result) == set()
    assert paths(result) == {}
    assert not result.value.has_start_end_route
    assert result.value.all_retained_on_start_end_routes  # universal empty set


def test_dependency_scores_are_original_exact_ratios_and_self_loop_zero():
    source = graph(
        {"A": 30, "B": 30},
        {("A", "B"): 10, ("B", "A"): 9, ("A", "A"): 3},
        {"A": 1},
        {"B": 1},
    )
    result = filter_dfg(source, DFGFilterSpec(mode="dependency", threshold=0.1))
    assert paths(result) == {("A", "B"): 10}
    forward = decision(result, "path", "A", "B")
    assert (forward.score_numerator, forward.score_denominator) == (1, 20)
    assert forward.reason == "keep_connectivity"
    backward = decision(result, "path", "B", "A")
    assert (backward.score_numerator, backward.score_denominator) == (-1, 20)
    assert not backward.retained
    loop = decision(result, "path", "A", "A")
    assert (loop.score_numerator, loop.score_denominator) == (0, 1)
    assert not loop.retained
    assert decision(result, "start", None, "A").score_numerator == 1


def test_noise_uses_endpoint_minimum_not_activity_total_or_global_maximum():
    source = graph(
        {"A": 10000, "B": 10000, "X": 1000, "C": 1},
        {("A", "X"): 1000, ("A", "B"): 1, ("B", "C"): 1},
        {"A": 1},
        {"X": 1, "C": 1},
    )
    result = filter_dfg(
        source, DFGFilterSpec(mode="noise", threshold=0.16, connectivity="none")
    )
    assert paths(result)[("A", "B")] == 1
    assert decision(result, "path", "A", "B").score_numerator == 1
    assert decision(result, "path", "A", "B").score_denominator == 1


@pytest.mark.parametrize("threshold,kept", [(0.2, True), (0.21, False)])
def test_noise_closed_threshold_and_explicit_preservation(threshold, kept):
    source = graph(
        {"A": 12, "B": 12, "X": 10, "Y": 10},
        {("A", "X"): 10, ("A", "B"): 2, ("Y", "B"): 10},
        {"A": 1, "Y": 1},
        {"X": 1, "B": 1},
    )
    spec = DFGFilterSpec(mode="noise", threshold=threshold, connectivity="none")
    result = filter_dfg(source, spec)
    assert (("A", "B") in paths(result)) is kept
    protected = filter_dfg(source, replace(spec, preserve_paths=(("A", "B"),)))
    assert paths(protected)[("A", "B")] == 2
    assert decision(protected, "path", "A", "B").reason == "keep_explicit"


def test_focus_to_from_and_cone_do_not_claim_every_path_visits_focus():
    source = graph(
        {"A": 10, "T": 9, "D": 10, "B": 1},
        {("A", "T"): 9, ("T", "D"): 9, ("A", "D"): 1, ("B", "D"): 1},
        {"A": 10, "B": 1},
        {"D": 11},
    )
    to = filter_dfg(source, DFGFilterSpec(mode="to_activity", focus_activity="T"))
    away = filter_dfg(source, DFGFilterSpec(mode="from_activity", focus_activity="T"))
    cone = filter_dfg(
        source, DFGFilterSpec(mode="contain_activity", focus_activity="T")
    )
    assert nodes(to) == {"A", "T"}
    assert paths(to) == {("A", "T"): 9}
    assert to.value.graph.end_counts == (("T", 9),)
    assert to.value.boundary_changes[0].original_count is None
    assert (
        to.value.boundary_changes[0].basis
        == "source_activity_occurrences_at_structural_cut"
    )
    assert nodes(away) == {"T", "D"}
    assert away.value.graph.start_counts == (("T", 9),)
    assert paths(cone) == {("A", "T"): 9, ("T", "D"): 9, ("A", "D"): 1}
    assert nodes(cone) == {"A", "T", "D"}
    assert cone.value.boundary_changes == ()


def test_focus_cone_prunes_dead_ancestors_and_rejects_unreachable_anchor():
    source = graph(
        {"A": 1, "T": 2, "D": 1, "X": 1},
        {("A", "T"): 1, ("X", "T"): 1, ("T", "D"): 1},
        {"A": 1},
        {"D": 1},
    )
    result = filter_dfg(
        source, DFGFilterSpec(mode="contain_activity", focus_activity="T")
    )
    assert nodes(result) == {"A", "T", "D"}
    assert decision(result, "activity", "X", None).reason == "remove_unreachable"
    invalid = filter_dfg(source, DFGFilterSpec(mode="to_activity", focus_activity="X"))
    assert invalid.status is ComputeStatus.INVALID_INPUT


def transitive_routes(activities, edges, starts, ends):
    # Floyd-Warshall boolean closure is independent of the implementation's BFS.
    reach = {(a, a) for a in activities} | set(edges)
    for k in activities:
        for i in activities:
            for j in activities:
                if (i, k) in reach and (k, j) in reach:
                    reach.add((i, j))
    return {
        activity
        for activity in activities
        if any((start, activity) in reach for start in starts)
        and any((activity, end) in reach for end in ends)
    }


def test_all_dags_preserve_directed_route_contract_against_closure_oracle():
    activities = ("A", "B", "C", "D")
    possible = tuple(combinations(activities, 2))
    checked = 0
    for mask in range(1 << len(possible)):
        edge_set = {edge for i, edge in enumerate(possible) if mask & (1 << i)}
        if transitive_routes(activities, edge_set, {"A"}, {"D"}) != set(activities):
            continue
        source = graph(
            dict.fromkeys(activities, 10),
            {edge: i + 1 for i, edge in enumerate(sorted(edge_set))},
            {"A": 1},
            {"D": 1},
        )
        result = filter_dfg(
            source,
            DFGFilterSpec(
                mode="path_frequency", minimum_frequency=5, connectivity="all"
            ),
        )
        assert nodes(result) == set(activities)
        assert transitive_routes(
            activities,
            paths(result),
            dict(result.value.graph.start_counts),
            dict(result.value.graph.end_counts),
        ) == set(activities)
        assert result.value.all_retained_on_start_end_routes
        checked += 1
    assert checked == 10


def test_single_node_loop_and_sentinel_labels_do_not_bypass_filtering():
    source = graph(
        {"@@startnode": 3},
        {("@@startnode", "@@startnode"): 2},
        {"@@startnode": 1},
        {"@@startnode": 1},
    )
    result = filter_dfg(source, DFGFilterSpec(mode="dependency", threshold=0.5))
    assert nodes(result) == {"@@startnode"}
    assert paths(result) == {}
    assert result.value.has_start_end_route


def test_empty_graph_is_available_with_no_frequency_denominator():
    source = graph({}, {}, {}, {})
    result = filter_dfg(source)
    assert result.status is ComputeStatus.COMPUTED
    assert nodes(result) == set()
    assert result.value.retained_activity_frequency_fraction is None
    assert result.value.retained_path_frequency_fraction is None


def test_disconnected_input_cannot_claim_all_activity_preservation():
    source = graph({"A": 1, "B": 1, "X": 1}, {("A", "B"): 1}, {"A": 1}, {"B": 1})
    invalid = filter_dfg(source, DFGFilterSpec(connectivity="all"))
    assert invalid.status is ComputeStatus.INVALID_INPUT
    assert invalid.value is None
    assert invalid.issues[-1].code == "unreachable_protected_activities"


def test_discovery_lineage_and_incomplete_counts_propagate():
    log = CaseLog(
        (
            CaseTrace(
                "case",
                tuple(
                    CaseEvent(
                        f"e{i}", (CaseAttribute("concept:name", "string", label),)
                    )
                    for i, label in enumerate("ABC")
                ),
            ),
        )
    )
    source = discover_dfg(log)
    result = filter_dfg(
        source, DFGFilterSpec(mode="path_frequency", minimum_frequency=1)
    )
    assert result.parent_computation_ids == (source.computation_id,)
    assert result.source_digest == source.source_digest
    limited = discover_dfg(log, RelationDiscoverySpec(max_event_pairs=1))
    unavailable = filter_dfg(limited)
    assert unavailable.status is ComputeStatus.UNAVAILABLE
    assert unavailable.value is None
    assert unavailable.issues[-1].code == "incomplete_dfg_counts"


def test_graph_immutability_identity_and_exact_large_integer_scores():
    source = diamond()
    before = dfg_digest(source)
    result = filter_dfg(source)
    assert dfg_digest(source) == before
    assert result == filter_dfg(source)
    assert (
        result.computation_id
        != filter_dfg(source, DFGFilterSpec(percentage=0.5)).computation_id
    )
    with pytest.raises(FrozenInstanceError):
        result.value.retained_activity_count = 0
    huge = 10**200
    large = graph({"A": huge, "B": huge}, {("A", "B"): huge}, {"A": 1}, {"B": 1})
    exact = filter_dfg(large, DFGFilterSpec(mode="dependency", threshold=0.9))
    score = decision(exact, "path", "A", "B")
    assert (score.score_numerator, score.score_denominator) == (huge, huge + 1)


@pytest.mark.parametrize(
    "change",
    [
        {"relation": "eventually_follows"},
        {"complete": "yes"},
        {"activity_counts": (("A", 0),)},
        {"edges": (RelationEdge("unknown", "A", 1, 1),)},
        {"edges": ("not-an-edge",)},
        {"start_counts": (("A", 1), ("A", 1))},
        {"activity_counts": (["A", 1],)},
    ],
)
def test_invalid_graph_records_return_invalid_input(change):
    source = graph({"A": 1}, {}, {"A": 1}, {"A": 1})
    result = filter_dfg(replace(source, **change))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"mode": "unknown"},
        {"percentage": -0.1},
        {"percentage": float("nan")},
        {"minimum_frequency": True},
        {"mode": "dependency", "threshold": -1.1},
        {"connectivity": "weak"},
        {"percentage_basis": "implicit"},
        {"mode": "noise", "percentage": 0.5},
        {"mode": "to_activity"},
        {"focus_activity": "A"},
        {"mode": "noise", "include_boundary_paths": False},
    ],
)
def test_invalid_specs(kwargs):
    with pytest.raises((TypeError, ValueError)):
        DFGFilterSpec(**kwargs)


def test_result_persistence_roundtrip_uses_real_registered_schema():
    result = filter_dfg(
        diamond(), DFGFilterSpec(mode="activity_percentage", percentage=0.1)
    )
    restored = result_from_json(result_json_bytes(result))
    assert restored == result


@pytest.mark.parametrize(
    "spec",
    [
        DFGFilterSpec(percentage=0),
        DFGFilterSpec(mode="dependency", threshold=1),
        DFGFilterSpec(mode="noise", threshold=0, connectivity="none"),
        DFGFilterSpec(mode="path_frequency", minimum_frequency=5, connectivity="all"),
        DFGFilterSpec(mode="to_activity", focus_activity="A"),
    ],
)
def test_all_policy_shapes_and_integer_ratio_arguments_roundtrip(spec):
    result = filter_dfg(diamond(), spec)
    assert result_from_json(result_json_bytes(result)) == result
