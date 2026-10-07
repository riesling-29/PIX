"""Hand-checked semantic projections, without a reference mining runtime."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.advanced import (
    DecisionExample,
    DecisionTreeSpec,
    mine_decision_tree,
)
from pix.case_centric.alignment_search import SearchAlignment, SearchAlignmentSet
from pix.case_centric.approximate_alignment import (
    ApproximateAlignmentSet,
    ApproximateTraceAlignment,
)
from pix.case_centric.declarative import FootprintConformance, FootprintViolation
from pix.case_centric.discovery import RelationDiscoverySpec, discover_dfg, discover_efg
from pix.case_centric.execution import align_traces, replay_traces
from pix.case_centric.organization import (
    AttributeNetwork,
    AttributeNetworkEdge,
    NetworkEdge,
    NetworkPayload,
    OrganizationalRole,
    RoleMerge,
    RoleSet,
    discover_roles,
    discover_social_network,
)
from pix.case_centric.sequence_alignment import (
    DFGAlignmentSet,
    DFGTraceAlignment,
    EditMove,
    ReferenceAlignment,
    SequenceAlignmentSet,
    SequenceTraceAlignment,
)
from pix.case_centric.statistics import (
    AttributeStatisticsSpec,
    EventDistributionSpec,
    IntervalRelationSpec,
    NumericAttributeSpec,
    PerformanceSpectrumSpec,
    discover_interval_eventually_follows,
    discover_performance_spectrum,
    measure_attributes,
    measure_case_performance,
    measure_event_distribution,
    measure_numeric_attribute,
    measure_statistics,
)
from pix.case_centric.tree_alignment import (
    TreeAlignmentMove,
    TreeAlignmentSet,
    TreeTraceAlignment,
)
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.conformance import (
    AlignmentCoverage,
    AlignmentMove,
    AlignmentSet,
    TraceAlignment,
)
from pix.contracts.discovery import ProcessTree
from pix.event_log import CaseAttribute, CaseEvent, CaseGlobal, CaseLog, CaseTrace
from pix.viewer.visual_case_adapters import case_panels, variant_duration_panels
from pix.viewer.visual_contracts import VisualizationDocument
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def _event(identifier, label, seconds=0, *, extra=()):
    return CaseEvent(
        identifier,
        (
            CaseAttribute("concept:name", "string", label),
            *(
                (
                    CaseAttribute(
                        "time:timestamp", "date", BASE + timedelta(seconds=seconds)
                    ),
                )
                if seconds is not None
                else ()
            ),
            CaseAttribute("org:resource", "string", "resource-" + label),
            CaseAttribute("amount", "int", 2 if label == "A" else 4),
            *extra,
        ),
    )


def _log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(_event(f"e{i}:{j}", a, j * 10) for j, a in enumerate(word)),
            )
            for i, word in enumerate(words)
        )
    )


def _net():
    return process_tree_to_petri_net(
        ProcessTree(
            "sequence",
            children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
        )
    )


def _metrics(element):
    return {m.name: (m.value, m.unit) for m in element.metrics}


def _details(element):
    return {d.name: d.value for d in element.details}


def _roundtrip(panels):
    document = VisualizationDocument("Case view", panels)
    assert loads_visualization(dumps_visualization(document)) == document
    return panels


def test_dfg_has_distinct_event_case_boundary_counts_and_preserves_loops():
    result = discover_dfg(_log("AAA", "A", ""), RelationDiscoverySpec(counting="cases"))
    graph, coverage = _roundtrip(case_panels(result.value, source=result))
    assert len(graph.nodes) == len(graph.edges) == 1
    assert _metrics(graph.nodes[0]) == {
        "events": (4, "events"),
        "starts": (2, "cases"),
        "ends": (2, "cases"),
    }
    assert graph.edges[0].source == graph.edges[0].target
    assert _metrics(graph.edges[0]) == {
        "selected count": (1, "cases"),
        "case count": (1, "cases"),
    }
    assert coverage.rows == ((3, 1, 2, True),)


def test_efg_partial_counts_are_labeled_lower_bounds_and_full_activity_counts_remain():
    result = discover_efg(_log("ABC"), RelationDiscoverySpec(max_event_pairs=1))
    graph, coverage = case_panels(result.value, source=result)
    assert "lower bounds" in graph.description
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 1
    assert coverage.rows[0][-1] is False
    raw = case_panels(result.value)[0]
    assert "counting request unavailable" in raw.edges[0].metrics[0].unit


def test_social_signed_unknown_weights_direction_and_denominators_survive():
    value = NetworkPayload(
        "pearson",
        "none",
        False,
        ("A", "B", "isolated"),
        (),
        (
            NetworkEdge("A", "B", -0.75, -0.75, 3, 4.0),
            NetworkEdge("B", "B", None, None, 0, None),
        ),
        2,
        3,
        1,
        0,
        4.0,
        3.0,
    )
    graph, coverage = _roundtrip(case_panels(value))
    assert len(graph.nodes) == 3
    assert all(not e.directed for e in graph.edges)
    assert graph.edges[0].metrics[0].value == -0.75
    assert graph.edges[1].metrics[0].value is None
    assert graph.edges[1].label == "unknown"
    assert coverage.rows == ((2, 3, 1, 0, 4.0, 3.0),)


def test_roles_keep_membership_frequency_activities_and_merge_evidence():
    value = RoleSet(
        (OrganizationalRole(("A", "B"), (("same", 3), ("other", 1)), 4),),
        (RoleMerge(("A",), ("B",), 0.5),),
        6,
        4,
        1,
        1,
        ("C",),
    )
    graph, coverage, merges = _roundtrip(case_panels(value))
    assert len(graph.nodes) == 3 and len(graph.edges) == 2
    role = next(n for n in graph.nodes if n.kind == "role")
    assert _details(role)["activities"] == '["A","B"]'
    assert sorted(e.metrics[0].value for e in graph.edges) == [1, 3]
    assert coverage.rows[0][:2] == (6, 4)
    assert merges.rows == (('["A"]', '["B"]', 0.5),)


def test_attribute_network_parallel_edges_keep_timed_denominator_and_unknown_time():
    value = AttributeNetwork(
        (
            AttributeNetworkEdge("same", "same", "handoff", 3, 2, 5.0, 10.0, 3.0, 7.0),
            AttributeNetworkEdge(
                "same", "same", "review", 2, 0, None, None, None, None
            ),
        ),
        (),
        8,
        5,
        0,
        0,
        3,
        1,
    )
    graph, _ = _roundtrip(case_panels(value))
    assert len(graph.nodes) == 1 and len(graph.edges) == 2
    assert {e.label for e in graph.edges} == {"handoff", "review"}
    assert _metrics(graph.edges[0])["timed links"] == (2, "links")
    assert _metrics(graph.edges[1])["mean duration"] == (None, "seconds")


def test_statistics_preserve_empty_variant_and_case_multiplicity():
    result = measure_statistics(_log("ABA", "ABA", "B", ""))
    activities, variants, coverage = _roundtrip(
        case_panels(result.value, source=result)
    )
    assert [(p.x, p.y) for p in activities.series[0].points] == [("A", 4), ("B", 3)]
    assert [p.y for p in variants.series[0].points] == [2, 1, 1]
    empty = next(
        p for p in variants.series[0].points if _details(p)["activities"] == "[]"
    )
    assert empty.y == 1
    assert coverage.rows == ((4, 7, '["c3"]'),)


def test_performance_keeps_parallel_variant_positions_and_null_durations():
    log = CaseLog(
        _log("ABA", "AB").traces + (CaseTrace("missing", (_event("m", "A", None),)),)
    )
    result = measure_case_performance(log)
    durations, graph, _, coverage = _roundtrip(case_panels(result.value, source=result))
    assert [p.y for p in durations.series[0].points] == [20.0, 10.0, None]
    assert len(graph.edges) == 3
    assert len({e.id for e in graph.edges}) == 3
    assert all(_metrics(e)["mean duration"] == (10.0, "seconds") for e in graph.edges)
    assert coverage.rows[0][2] == 1


def test_kde_uses_supplied_grid_values_bandwidth_and_nulls_without_new_calculation():
    result = measure_numeric_attribute(
        _log("A"), NumericAttributeSpec("amount", grid=(2.0, 3.0), bandwidth=0.5)
    )
    observations, kde, _ = _roundtrip(case_panels(result.value, source=result))
    assert observations.series[0].points[0].y == 2.0
    assert tuple((p.x, p.y) for p in kde.series[0].points) == result.value.gaussian_kde
    assert "0.5" in kde.description
    empty = measure_numeric_attribute(
        _log("A"), NumericAttributeSpec("absent", grid=(1.0,), bandwidth=1.0)
    )
    assert case_panels(empty.value, source=empty)[1].series[0].points[0].y is None


def test_calendar_bins_retain_offset_and_do_not_fill_missing_bins():
    result = measure_event_distribution(
        _log("AB"),
        EventDistributionSpec(granularity="hour_of_day", utc_offset_minutes=540),
    )
    chart, coverage = _roundtrip(case_panels(result.value, source=result))
    assert len(chart.series[0].points) == 1
    assert chart.series[0].points[0].y == 2
    assert "540" in chart.description
    assert coverage.rows == ((2, 2, "[]"),)
    assert "unknown without" in case_panels(result.value)[0].description


def test_spectrum_is_individual_timestamp_polylines_not_aggregate_bars():
    result = discover_performance_spectrum(
        _log("ABAB", "AB"), PerformanceSpectrumSpec(("A", "B"))
    )
    chart, coverage = _roundtrip(case_panels(result.value, source=result))
    assert chart.chart_type == "line" and chart.x_type == "time"
    assert len(chart.series) == 3
    assert [p.y for p in chart.series[0].points] == [0, 1]
    assert chart.series[0].points[0].x == BASE.isoformat()
    assert _details(chart.series[0].points[1])["activity"] == "B"
    assert len({s.name for s in chart.series}) == 3
    assert coverage.rows[0][-1] == 3


def test_dotted_chart_preserves_ties_empty_lanes_and_refuses_global_time_as_observation():
    log = CaseLog(
        (
            CaseTrace(
                "tied",
                (
                    _event("a", "A", 0),
                    _event("b", "B", 0),
                    _event("missing", "C", None),
                ),
            ),
            CaseTrace("empty"),
        ),
        globals=(
            CaseGlobal("event", (CaseAttribute("time:timestamp", "date", BASE),)),
        ),
    )
    timeline, unavailable = _roundtrip(case_panels(log))
    assert len(timeline.lanes) == 2 and len(timeline.items) == 2
    assert timeline.items[0].start == timeline.items[1].start == BASE.timestamp()
    assert timeline.items[0].id != timeline.items[1].id
    assert all(item.end == item.start for item in timeline.items)
    assert unavailable.rows[0][:4] == ("tied", "missing", 2, "C")


def test_dotted_naive_or_ambiguous_timestamps_are_explicitly_unavailable():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    CaseEvent(
                        "naive",
                        (
                            CaseAttribute(
                                "time:timestamp", "date", BASE.replace(tzinfo=None)
                            ),
                        ),
                    ),
                    CaseEvent(
                        "ambiguous",
                        (
                            CaseAttribute("time:timestamp", "date", BASE),
                            CaseAttribute("time:timestamp", "date", BASE),
                        ),
                    ),
                ),
            ),
        )
    )
    timeline, unavailable = case_panels(log)
    assert not timeline.items
    assert len(unavailable.rows) == 2


def test_footprint_comparison_direction_and_nonedge_violations_are_preserved():
    value = FootprintConformance(
        (
            FootprintViolation("relation", "A", "B", "c"),
            FootprintViolation("minimum_trace_length", case_id="empty"),
        ),
        (("A", "B"), ("B", "B")),
        (("B", "A"), ("B", "B")),
        1,
        0.5,
        0.5,
        2,
    )
    matrix, violations, scores = _roundtrip(case_panels(value))
    cells = {(c.row, c.column): (c.value, c.kind) for c in matrix.cells}
    assert cells == {
        ("A", "A"): ("#", "absent"),
        ("A", "B"): ("!", "violation"),
        ("B", "A"): ("○", "unobserved"),
        ("B", "B"): ("=", "matched"),
    }
    assert len(matrix.legend) == 4
    assert violations.rows[-1] == ("minimum_trace_length", None, None, "empty")
    assert scores.rows[0][2:4] == (0.5, 0.5)


def test_decision_tree_threshold_branches_training_counts_and_status_are_exact():
    result = mine_decision_tree(
        _log("A", "B"),
        (DecisionExample("c0", (1,), "no"), DecisionExample("c1", (3,), "yes")),
        DecisionTreeSpec(("amount",)),
    )
    graph, training = _roundtrip(case_panels(result.value, source=result))
    assert len(graph.nodes) == 3
    assert graph.nodes[0].label == "amount ≤ 1"
    assert {e.label for e in graph.edges} == {"≤ 1", "> 1"}
    assert graph.nodes[0].metrics[0].value == 2
    assert training.rows[0][:2] == (2, 2)
    assert "not validated" in graph.description


def _standard_alignments():
    moves = (
        AlignmentMove("synchronous", "e0", "t0", ">>", 0, (), ()),
        AlignmentMove("log", "e1", None, "B", 1, (), ()),
        AlignmentMove("model", None, "t1", "C", 1, (), ()),
        AlignmentMove("silent", None, "tau", None, 0, (), ()),
    )
    return AlignmentSet(
        "case",
        "model",
        "traces",
        (
            TraceAlignment("c", ("e0", "e1"), "optimal", moves, 2, 5, 7, 2),
            TraceAlignment("empty", (), "optimal", (), 0, 1, 1, 0),
            TraceAlignment("pending", (), "search_limit", (), None, 1, 2, 0),
        ),
        AlignmentCoverage(3, 2, 0, 1),
        2,
        (2, 2),
        None,
    )


def test_alignment_keeps_all_four_move_kinds_empty_rows_and_pending_status():
    timeline, status, moves = _roundtrip(case_panels(_standard_alignments()))
    assert len(timeline.lanes) == 6 and len(timeline.items) == 8
    assert [r[2] for r in moves.rows] == ["synchronous", "log", "model", "silent"]
    assert moves.rows[0][3:5] == (">>", ">>")
    assert moves.rows[1][3:5] == ("B", None)
    assert moves.rows[2][3:5] == (None, "C")
    assert status.rows[1] == ("empty", "optimal", 0, 0, 0)
    assert status.rows[2] == ("pending", "search_limit", None, 0, 0)
    assert timeline.items[0].label == ">>"
    assert timeline.items[-1].label == "τ (silent)"


def test_rational_search_alignment_preserves_discounted_step_cost_not_integer_base_cost():
    move = AlignmentMove("model", None, "t", "A", 1, (), ())
    value = SearchAlignmentSet(
        "digest",
        "exact",
        "v1",
        (
            SearchAlignment(
                "c",
                (),
                "optimal_within_horizon",
                (move,),
                ((1, 3),),
                (1, 3),
                (0, 1),
                1,
                2,
                0,
                (),
            ),
        ),
        1,
        1,
        0,
        0,
        (1, 3),
        "discounted",
        1,
    )
    _, status, moves = _roundtrip(case_panels(value))
    assert status.rows[0][1:4] == ("optimal_within_horizon", "1/3", "0/1")
    assert moves.rows[0][7] == "1/3"


def test_tree_alignment_retains_node_paths_and_raw_silent_kind():
    value = TreeAlignmentSet(
        "digest",
        (
            TreeTraceAlignment(
                "c",
                (),
                "optimal",
                0,
                (TreeAlignmentMove("silent", None, None, (0, 1), None, 0),),
                (),
                1,
                1,
                None,
            ),
        ),
        1,
        1,
        0,
        0,
    )
    _, _, evidence = _roundtrip(case_panels(value))
    assert evidence.rows[0][2] == "silent"
    assert evidence.rows[0][6] == "[0,1]"


def test_approximate_alignment_cost_is_upper_bound_never_relabeled_optimal():
    trace = ApproximateTraceAlignment(
        "c",
        "sliding",
        "approximate",
        (),
        3,
        None,
        1,
        "none",
        None,
        False,
        None,
        1,
        0,
        0,
        0,
        None,
        (),
        (),
        None,
    )
    value = ApproximateAlignmentSet("digest", "sliding", (trace,), 1, 1, 0, 1, 0, 3, 3)
    _, status, _ = _roundtrip(case_panels(value))
    assert status.rows[0][1:4] == ("approximate", 3, 1)
    assert "upper bound" in status.columns[2]


def test_sequence_alignment_keeps_tied_reference_paths_and_substitution_sides():
    move = EditMove("substitution", "e", "A", "B", "r", 1)
    value = SequenceAlignmentSet(
        (
            SequenceTraceAlignment(
                "c",
                "optimal",
                1,
                (
                    ReferenceAlignment("r1", 1, (move,)),
                    ReferenceAlignment("r2", 1, (move,)),
                ),
                2,
                0,
            ),
            SequenceTraceAlignment("no-reference", "empty_reference", None, (), 0, 0),
        ),
        2,
        1,
        0,
    )
    timeline, status, evidence, references = _roundtrip(case_panels(value))
    assert len(timeline.lanes) == 6 and len(status.rows) == 3
    assert evidence.rows[0][2:5] == ("substitution", "A", "B")
    assert [row[8:] for row in evidence.rows] == [(0, "r1"), (1, "r2")]
    assert status.rows[-1][1] == "empty_reference"
    assert references.rows == (
        (0, "c", "r1"),
        (1, "c", "r2"),
        (2, "no-reference", None),
    )


def test_dfg_alignment_retains_unreachable_and_null_cost():
    value = DFGAlignmentSet(
        (DFGTraceAlignment("c", "unreachable", None, (), 1, 1, None),), 0, 1, 0
    )
    timeline, status, _ = _roundtrip(case_panels(value))
    assert len(timeline.lanes) == 2
    assert not timeline.items
    assert status.rows[0][1:4] == ("unreachable", None, None)


def test_actual_replay_has_token_accounting_and_not_a_fit_claim():
    result = replay_traces(_log("AC", ""), _net())
    timeline, status, evidence, coverage = _roundtrip(
        case_panels(result.value, source=result)
    )
    assert len(timeline.lanes) == 4
    assert "not optimal alignment" in timeline.description
    assert "initial" in {r[2] for r in evidence.rows}
    assert "finalize" in {r[2] for r in evidence.rows}
    assert status.rows[0][4] == 1
    assert coverage.rows[0][0] == 2


@pytest.mark.parametrize(
    "factory",
    [
        lambda log: discover_dfg(log),
        lambda log: discover_efg(log),
        lambda log: discover_interval_eventually_follows(log, IntervalRelationSpec()),
        lambda log: discover_social_network(log),
        lambda log: discover_roles(log),
        lambda log: measure_statistics(log),
        lambda log: measure_case_performance(log),
        lambda log: measure_attributes(log, AttributeStatisticsSpec()),
        lambda log: measure_numeric_attribute(
            log, NumericAttributeSpec("amount", grid=(1.0,), bandwidth=1.0)
        ),
        lambda log: measure_event_distribution(log),
        lambda log: discover_performance_spectrum(
            log, PerformanceSpectrumSpec(("A", "B"))
        ),
        lambda log: align_traces(log, _net()),
        lambda log: replay_traces(log, _net()),
    ],
)
def test_real_calculation_results_have_valid_panels_and_stable_json(factory):
    result = factory(_log("ABA", "AB", ""))
    assert result.value is not None
    _roundtrip(case_panels(result.value, source=result))


def test_labels_are_plain_data_and_generated_identity_does_not_use_delimiters():
    dangerous = '</script><script>alert("x")</script>&雪'
    result = discover_dfg(_log((dangerous, "a:b", "a", "b:c")))
    graph = _roundtrip(case_panels(result.value, source=result))[0]
    assert dangerous in {n.label for n in graph.nodes}
    assert len({n.id for n in graph.nodes}) == 4
    assert all(dangerous not in n.id for n in graph.nodes)


def test_source_mismatch_is_rejected_and_unknown_types_have_no_fake_table():
    left = discover_dfg(_log("AB"))
    right = discover_dfg(_log("AC"))
    with pytest.raises(ValueError, match="does not match"):
        case_panels(left.value, source=right)
    with pytest.raises(TypeError, match="ComputationResult"):
        case_panels(left.value, source=object())
    assert case_panels({"activity": "A", "count": 5}) is None


def test_variant_duration_join_preserves_repeated_positions_empty_cases_and_observed_time():
    log = _log("ABA", "ABA", "")
    statistics, performance = measure_statistics(log), measure_case_performance(log)
    first, empty, cases = _roundtrip(
        variant_duration_panels(
            statistics.value,
            performance.value,
            statistics_source=statistics,
            performance_source=performance,
        )
    )
    assert [n.label for n in first.nodes] == ["A", "B", "A"]
    assert len({n.id for n in first.nodes}) == 3
    assert [e.metrics[0].value for e in first.edges] == [10.0, 10.0]
    assert first.nodes[0].metrics[0].value == 2
    assert empty.nodes[0].kind == "empty_variant"
    assert [r[3] for r in cases.rows] == [20.0, 20.0, None]
    assert "not elapsed time" in first.description


def test_variant_duration_join_rejects_classifier_population_and_membership_conflicts():
    log = _log("AB")
    statistics, performance = measure_statistics(log), measure_case_performance(log)
    changed_spec = replace(
        performance.spec, trace_spec=CaseTraceSpec(activity_key="another")
    )
    with pytest.raises(ValueError, match="classifiers"):
        variant_duration_panels(
            statistics.value,
            performance.value,
            statistics_source=statistics,
            performance_source=replace(performance, spec=changed_spec),
        )
    changed = replace(performance.value, cases=())
    with pytest.raises(ValueError, match="populations"):
        variant_duration_panels(
            statistics.value,
            changed,
            statistics_source=statistics,
            performance_source=replace(performance, value=changed),
        )
    bad_path = replace(performance.value.variant_paths[0], source="wrong")
    changed = replace(performance.value, variant_paths=(bad_path,))
    with pytest.raises(ValueError, match="membership"):
        variant_duration_panels(
            statistics.value,
            changed,
            statistics_source=statistics,
            performance_source=replace(performance, value=changed),
        )
    with pytest.raises(ValueError, match="envelopes"):
        variant_duration_panels(statistics.value, performance.value)


def test_variant_duration_join_rejects_duplicate_case_samples_and_incorrect_sample_count():
    log = _log("AB", "AB")
    statistics, performance = measure_statistics(log), measure_case_performance(log)
    path = performance.value.variant_paths[0]
    for samples in ((path.samples[0], path.samples[0]), (path.samples[0],)):
        changed = replace(
            performance.value, variant_paths=(replace(path, samples=samples),)
        )
        with pytest.raises(ValueError, match="coverage conflicts"):
            variant_duration_panels(
                statistics.value,
                changed,
                statistics_source=statistics,
                performance_source=replace(performance, value=changed),
            )


def test_sequence_alignment_preserves_distinct_ids_containing_display_separators():
    value = SequenceAlignmentSet(
        (
            SequenceTraceAlignment(
                "a", "optimal", 0, (ReferenceAlignment("b → reference c", 0, ()),), 1, 0
            ),
            SequenceTraceAlignment(
                "a → reference b", "optimal", 0, (ReferenceAlignment("c", 0, ()),), 1, 0
            ),
        ),
        2,
        2,
        0,
    )
    timeline, status, _, identities = _roundtrip(case_panels(value))
    assert len(timeline.lanes) == 4
    assert status.rows[0][0] == "a"
    assert status.rows[1][0] == "a → reference b"
    assert identities.rows == ((0, "a", "b → reference c"), (1, "a → reference b", "c"))
