"""Hand-counted OC view populations, identity, order and unknown observations."""

import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.interleavings import (
    CaseLink,
    InterleavingSpec,
    discover_interleavings,
)
from pix.case_centric.interleavings_ocel import from_interleavings
from pix.compute.executions import discover_executions
from pix.compute.object_conformance import align_object_log
from pix.compute.ocdfg import discover_ocdfg
from pix.compute.variants import discover_variants
from pix.contracts.analysis import E2OEvidence, OCDFGSpec
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.object_conformance import ObjectAlignmentSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.object_centric.conformance import (
    ObjectReplaySpec,
    replay_flattened_object_log,
    replay_object_log,
)
from pix.object_centric.constraints import (
    AAEdge,
    ActivityNode,
    AOAEdge,
    ConstraintGraphSpec,
    FormulaNode,
    OAEdge,
    ObjectRuleMetricSpec,
    ObjectTypeNode,
    PerformanceEdge,
    QualifierConformance,
    QualifierWitness,
    evaluate_constraint_graph,
    measure_rule_metric,
)
from pix.object_centric.cube import CubePlan, CubeTypeChange, DrillDownSpec, drill_down
from pix.object_centric.performance import (
    OCPerformanceSpec,
    OCReplayPerformanceSpec,
    measure_performance,
    measure_replay_performance,
)
from pix.object_centric.relations import (
    ETOTSpec,
    ObjectGraphSpec,
    ObjectRelationSpec,
    OCELScalar,
    OTGSpec,
    discover_etot,
    discover_object_graph,
    discover_otg,
    query_object_relations,
)
from pix.object_centric.statistics import object_statistics
from pix.object_centric.temporal_summary import temporal_summary
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)
from pix.viewer.visual_contracts import (
    ChartPanel,
    GraphPanel,
    MatrixPanel,
    TimelinePanel,
    VisualizationDocument,
)
from pix.viewer.visual_object_adapters import object_panels
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def example():
    return OCEL(
        event_types=(
            EventType("A"),
            EventType("Order", (Attribute("when", ValueType.TIME),)),
            EventType("B"),
        ),
        object_types=(
            ObjectType("Order", (Attribute("state", ValueType.STRING),)),
            ObjectType("Item"),
        ),
        events=(
            Event("e1", "A", BASE),
            Event(
                "e2", "Order", BASE + timedelta(seconds=10), (EventAttr("when", BASE),)
            ),
            Event("e3", "B", BASE + timedelta(seconds=20)),
        ),
        objects=(
            Object("e1", "Order", (ObjectAttr("state", "ready", BASE),)),
            Object("o2", "Order"),
            Object("unused", "Item"),
        ),
        e2o=tuple(
            E2O(eid, oid, "flow") for eid in ("e1", "e2", "e3") for oid in ("e1", "o2")
        )
        + (E2O("e2", "e1", "audit"),),
        o2o=(O2O("e1", "o2", "contains"), O2O("e1", "o2", "checks")),
    )


def model():
    return ObjectCentricPetriNet(
        tuple(TypedPlace(f"p{i}", "Order") for i in range(4)),
        tuple(Transition(f"t{i}", a) for i, a in enumerate(("A", "Order", "B"))),
        tuple(
            arc
            for i in range(3)
            for arc in (
                ObjectArc(f"p{i}", f"t{i}", True, 2, 2),
                ObjectArc(f"t{i}", f"p{i + 1}", True, 2, 2),
            )
        ),
        ObjectMarking((ObjectToken("p0", "e1"), ObjectToken("p0", "o2"))),
        ObjectMarking((ObjectToken("p3", "e1"), ObjectToken("p3", "o2"))),
        (("e1", "Order"), ("o2", "Order"), ("unused", "Item")),
    )


def constraints():
    formula = FormulaNode("flow", ">", 1, unit="microseconds")
    return ConstraintGraphSpec(
        oa_edges=(
            OAEdge(
                "same-name",
                ObjectTypeNode("Order"),
                ActivityNode("Order"),
                "existence",
                ">=",
                1,
            ),
        ),
        aa_edges=(AAEdge("aa", ActivityNode("A"), ActivityNode("B"), formula),),
        aoa_edges=(
            AOAEdge(
                "response",
                ActivityNode("A"),
                ObjectTypeNode("Order"),
                ActivityNode("B"),
                "followed_by",
                ">=",
                1,
            ),
        ),
        performance_edges=(PerformanceEdge("perf", formula, ActivityNode("Order")),),
    )


def linked_case(times):
    return CaseLog(
        (
            CaseTrace(
                "same-case",
                tuple(
                    CaseEvent(
                        f"same-{i}",
                        (
                            CaseAttribute("concept:name", "string", "Same activity"),
                            CaseAttribute(
                                "time:timestamp", "date", BASE + timedelta(seconds=t)
                            ),
                        ),
                    )
                    for i, t in enumerate(times)
                ),
            ),
        )
    )


def interleaving(boundaries=False):
    left, right = linked_case((0, 10)), linked_case((5, 15))
    result = discover_interleavings(
        left,
        right,
        InterleavingSpec(
            case_links=(CaseLink("same-case", "same-case"),),
            include_boundaries=boundaries,
        ),
    )
    return left, right, result


def panels(result):
    return object_panels(result.value, source=result)


def pick(values, kind):
    return tuple(value for value in values if isinstance(value, kind))


def fields(value):
    return {item.name: item.value for item in value.details}


def test_raw_ocel_keeps_namespaces_shared_events_parallel_qualifiers_and_history():
    value = example()
    graph, timeline, attrs, schema = object_panels(value)
    assert len(graph.nodes) == 6
    assert len(graph.edges) == 9
    assert len({n.id for n in graph.nodes}) == 6
    assert CounterKinds(graph.edges) == {"e2o": 7, "o2o": 2}
    assert len(timeline.items) == 6  # seven E2O roles are six unique pairs
    shared = [item for item in timeline.items if fields(item)["event_id"] == "e2"]
    assert (
        len(shared) == 2 and len({fields(i)["semantic_event_id"] for i in shared}) == 1
    )
    assert len({i.id for i in shared}) == 2
    assert any(json.loads(fields(i)["qualifiers"]) == ["audit", "flow"] for i in shared)
    assert all(i.end == i.start for i in timeline.items)
    assert ("event", "e2", "when", BASE.isoformat(), None, "time") in attrs.rows
    assert ("object", "e1", "state", "ready", BASE.isoformat(), "string") in attrs.rows
    assert ("object", "Item", None, None) in schema.rows


def CounterKinds(values):
    return {
        kind: sum(v.kind == kind for v in values) for kind in {v.kind for v in values}
    }


def test_raw_orphan_is_not_dropped_or_assigned_to_an_object():
    value = example()
    value = replace(value, e2o=tuple(r for r in value.e2o if r.event != "e3"))
    _, time, _, _ = object_panels(value)
    orphan = [i for i in time.items if fields(i)["event_id"] == "e3"]
    assert len(orphan) == 1
    assert "object_id" not in fields(orphan[0])
    assert time.lanes[-1].label == "Events without selected objects"


def test_invalid_ocel_is_not_repaired_for_display():
    value = replace(example(), e2o=(E2O("missing", "e1", "flow"),))
    with pytest.raises(ValueError, match="invalid OCEL"):
        object_panels(value)


@pytest.mark.parametrize(
    "frequency,expected",
    [
        ("qualified_relations", 3),
        ("event_object_pairs", 2),
        ("events", 1),
        ("objects", 2),
    ],
)
def test_etot_counts_explicit_populations_and_equal_names_have_different_ids(
    frequency, expected
):
    (graph,) = panels(discover_etot(example(), ETOTSpec(frequency=frequency)))
    same_name = [n for n in graph.nodes if n.label == "Order"]
    assert len(same_name) == 2 and same_name[0].id != same_name[1].id
    edge = next(
        e
        for e in graph.edges
        if e.source == next(n.id for n in same_name if n.kind == "activity")
    )
    assert (edge.metrics[0].value, edge.metrics[0].unit) == (expected, frequency)


def test_object_graph_witness_count_and_undirectedness():
    (graph,) = panels(discover_object_graph(example(), ObjectGraphSpec("interaction")))
    assert len(graph.nodes) == 3 and len(graph.edges) == 1
    edge = graph.edges[0]
    assert edge.directed is False
    assert edge.metrics[0].value == 3
    assert json.loads(fields(edge)["event_ids"]) == ["e1", "e2", "e3"]


def test_otg_keeps_parallel_relation_kinds_and_object_pair_unit():
    (graph,) = panels(discover_otg(example(), OTGSpec()))
    assert {e.kind for e in graph.edges} >= {"interaction", "cobirth", "codeath"}
    assert all(e.metrics[0].unit == "distinct_object_pairs" for e in graph.edges)
    assert all(
        e.directed == (e.kind in ("descendants", "inheritance")) for e in graph.edges
    )


def test_o2o_query_keeps_original_directions_without_inventing_object_types():
    (graph,) = panels(
        query_object_relations(example(), ObjectRelationSpec(("o2",), "inbound"))
    )
    assert len(graph.edges) == 2
    assert {e.label for e in graph.edges} == {"checks", "contains"}
    assert len({(e.source, e.target) for e in graph.edges}) == 1
    assert all(n.group is None for n in graph.nodes)


def test_ocdfg_three_units_and_complete_qualifier_witnesses():
    result = discover_ocdfg(example(), OCDFGSpec(("Order", "Item")))
    graph, witnesses, bounds = panels(result)
    assert len(graph.edges) == 2
    for e in graph.edges:
        assert [m.value for m in e.metrics] == [1, 2, 2]
        assert [m.unit for m in e.metrics] == [
            "distinct_event_pairs",
            "distinct_objects",
            "object_trace_occurrences",
        ]
    assert len(witnesses.rows) == 4
    assert any("audit" in str(row) for row in witnesses.rows)
    assert ("Item", "empty_object", None, "unused", None) in bounds.rows


def test_ocdfg_inconsistent_counts_rejected():
    value = discover_ocdfg(example(), OCDFGSpec(("Order",))).value
    g = value.graphs[0]
    bad = replace(
        value,
        graphs=(
            replace(g, edges=(replace(g.edges[0], event_pair_count=17), *g.edges[1:])),
        ),
    )
    with pytest.raises(ValueError, match="witnesses"):
        object_panels(bad)


def test_execution_shared_event_has_one_graph_node_and_one_rank_per_many_lanes():
    result = discover_executions(example(), ExecutionSpec("connected_components"))
    values = panels(result)
    graphs = pick(values, GraphPanel)
    assert len(graphs) == 1
    assert sum(n.kind == "event" for n in graphs[0].nodes) == 3
    timeline = next(
        p
        for p in values
        if isinstance(p, TimelinePanel) and p.unit == "precedence_layers"
    )
    assert len(timeline.items) == 6
    assert sorted(set(i.start for i in timeline.items)) == [0, 1, 2]
    assert all(i.end == i.start for i in timeline.items)
    for event_id in ("e1", "e2", "e3"):
        appearances = [i for i in timeline.items if fields(i)["event_id"] == event_id]
        assert len({fields(i)["semantic_event_id"] for i in appearances}) == 1
        assert len({i.start for i in appearances}) == 1


def test_unresolved_execution_ties_do_not_invent_chevrons_or_total_order():
    value = example()
    tied = replace(
        value,
        events=(value.events[0], replace(value.events[1], time=BASE), value.events[2]),
    )
    result = discover_executions(tied, ExecutionSpec("connected_components"))
    assert result.status == ComputeStatus.COMPUTED
    assert result.value.executions[0].order_status == "unavailable"
    values = panels(result)
    assert not any(
        isinstance(p, TimelinePanel) and p.unit == "precedence_layers" for p in values
    )
    time = pick(values, TimelinePanel)[0]
    assert (
        len({i.start for i in time.items if fields(i)["event_id"] in ("e1", "e2")}) == 1
    )
    ties = next(p for p in values if p.title == "Unresolved execution order ties")
    assert len(ties.rows) == 2


def test_variant_counts_not_fabricated_representative_graph():
    execution = discover_executions(example(), ExecutionSpec("connected_components"))
    values = panels(discover_variants(execution, VariantSpec()))
    assert len(pick(values, ChartPanel)) == 1
    assert not pick(values, GraphPanel)
    assert values[0].y_unit == "execution_memberships"
    assert values[0].series[0].points[0].y == 1
    variant = discover_variants(execution, VariantSpec()).value.variants[0]
    assert object_panels(variant) == values


def test_joint_alignment_single_move_cost_and_shared_lane_appearances():
    result = align_object_log(
        example(), model(), ObjectAlignmentSpec(("Order", "Item"))
    )
    assert result.value is not None, result.issues
    assert result.value.status == "optimal"
    values = panels(result)
    moves = next(p for p in values if p.id == "oc-alignment-moves")
    lane = pick(values, TimelinePanel)[0]
    assert len(moves.rows) == 3 and len(lane.items) == 6
    assert lane.unit == "alignment_steps"
    assert sum(row[5] for row in moves.rows) == result.value.cost == 0
    assert len({fields(i)["semantic_move_id"] for i in lane.items}) == 3
    assert all("cost" not in fields(i) for i in lane.items)
    assert all(row[1] == "synchronous" for row in moves.rows)


def test_limited_alignment_preserves_null_path_cost():
    result = align_object_log(
        example(), model(), ObjectAlignmentSpec(("Order", "Item"), max_states=1)
    )
    assert result.status == ComputeStatus.PARTIAL
    status = next(p for p in panels(result) if p.id == "oc-alignment-status")
    assert status.rows[0][0] in ("search_limit", "binding_limit")
    assert status.rows[0][1] is None


def test_replay_token_multiplicity_and_no_timestamp_axis():
    replay = replay_object_log(example(), model(), ObjectReplaySpec(("Order", "Item")))
    values = panels(replay)
    assert not pick(values, TimelinePanel)
    steps = next(p for p in values if p.id == "oc-replay-steps")
    first_visible = next(r for r in steps.rows if r[1] == "visible")
    assert json.loads(first_visible[7]) == [["p0", "e1"], ["p0", "o2"]]
    status = next(p for p in values if p.id == "oc-replay-status")
    assert status.rows[0][1:3] == (3, 3)


def test_flattened_population_distinguishes_occurrences_from_source_events():
    result = replay_flattened_object_log(
        example(), model(), ObjectReplaySpec(("Order", "Item"))
    )
    values = panels(result)
    table = next(p for p in values if p.id == "oc-flat-replay")
    assert "3 distinct source events" in table.description
    assert "6 projected occurrences" in table.description
    assert sum(row[3] for row in table.rows) == 6


def test_constraint_same_name_nodes_formula_and_aoa_scope_are_not_merged():
    (graph,) = object_panels(constraints())
    names = [n for n in graph.nodes if n.label == "Order"]
    assert {n.kind for n in names} == {"activity", "object_type"}
    assert len({n.id for n in names}) == 2
    assert any(n.kind == "formula" for n in graph.nodes)
    assert any(e.kind == "constraint_scope" for e in graph.edges)
    aa = next(e for e in graph.edges if fields(e).get("constraint_id") == "aa")
    assert (
        fields(aa)["metric_scope"] == "source activity; not source-to-target duration"
    )
    assert fields(aa)["unit"] == "microseconds"


def test_unknown_constraint_evaluation_retains_unknown_not_pass_or_fail():
    result = evaluate_constraint_graph(example(), constraints())
    values = panels(result)
    assert pick(values, GraphPanel)
    rows = values[-1].rows
    aa = next(r for r in rows if r[0] == "aa")
    assert aa[2] is None and aa[5] is None
    assert "does not automatically" in values[-1].description


def test_rule_metric_witnesses_and_population_retained():
    result = measure_rule_metric(
        example(), ObjectRuleMetricSpec("Order", "A", "existence")
    )
    (table,) = panels(result)
    assert len(table.rows) == 2 and all(row[3] for row in table.rows)
    assert "2/2" in table.description


@pytest.mark.parametrize(
    "scalar,expected",
    [
        (OCELScalar("string", text_value=""), ""),
        (OCELScalar("time", timestamp_value=BASE), BASE.isoformat()),
        (OCELScalar("boolean", boolean_value=False), False),
        (OCELScalar("integer", integer_value=0), 0),
    ],
)
def test_qualifier_conformance_preserves_typed_false_zero_empty_and_unknown(
    scalar, expected
):
    value = QualifierConformance(
        "e2o",
        "fixture",
        1,
        0,
        0,
        1,
        None,
        (QualifierWitness("e1", "o", None, ("role",), scalar, BASE, None, "missing"),),
    )
    (table,) = object_panels(value)
    row = table.rows[0]
    assert row[4] == expected and type(row[4]) is type(expected)
    assert row[5] == scalar.kind and row[7] is None


def test_performance_unknown_samples_and_exact_rational_mean():
    result = measure_performance(
        example(), OCPerformanceSpec(metrics=("flow", "service"))
    )
    values = panels(result)
    summary = next(p for p in values if p.id == "oc-performance-summary")
    service = next(r for r in summary.rows if r[0] == "service")
    assert service[3] == 0 and service[4] == service[2]
    assert service[-2:] == (None, None)
    samples = next(p for p in values if p.id == "oc-performance-samples")
    assert all(
        row[6] is None and row[7] is not None
        for row in samples.rows
        if row[0] == "service"
    )
    assert all(
        item.end == item.start for t in pick(values, TimelinePanel) for item in t.items
    )


def test_replay_performance_unknown_initial_clock_and_concrete_token_serials():
    replay = replay_object_log(example(), model(), ObjectReplaySpec(("Order", "Item")))
    result = measure_replay_performance(example(), replay, OCReplayPerformanceSpec())
    values = panels(result)
    arrivals = next(p for p in values if p.id == "oc-token-arrivals")
    initial = [r for r in arrivals.rows if r[7] == "initial"]
    assert len(initial) == 2 and all(r[6] is None for r in initial)
    assert len({r[2] for r in initial}) == 2
    assert all(r[-1] for r in initial)


def test_temporal_summary_four_separate_units_and_role_multiplicity():
    values = panels(temporal_summary(example()))
    charts = pick(values, ChartPanel)
    assert len(charts) == 4
    assert {p.y_unit for p in charts} == {
        "distinct_events",
        "distinct_objects",
        "distinct_event_object_pairs",
        "qualified_e2o_rows",
    }
    assert (
        next(p for p in charts if p.y_unit == "qualified_e2o_rows")
        .series[0]
        .points[1]
        .y
        == 3
    )
    assert (
        next(p for p in charts if p.y_unit == "distinct_event_object_pairs")
        .series[0]
        .points[1]
        .y
        == 2
    )
    assert all(p.x_type == "time" for p in charts)


def test_cube_matrix_counts_changes_not_source_or_unclassified_population():
    result = drill_down(example(), DrillDownSpec("Order", "state", BASE))
    assert result.status == ComputeStatus.PARTIAL
    values = panels(result)
    matrices = pick(values, MatrixPanel)
    objects = next(p for p in matrices if p.unit == "changed_objects")
    assert sum(c.value for c in objects.cells) == 1
    assert objects.legend and "not source population" in objects.description
    unclassified = next(p for p in values if p.id == "oc-cube-unclassified")
    assert unclassified.rows == (("o2", "no_assignment_as_of"),)
    evidence = next(p for p in values if p.id == "oc-cube-evidence")
    assert evidence.rows[0][4:6] == ("string", "ready")


def test_cube_event_type_change_retains_qualified_relations():
    value = CubePlan(
        "unfold",
        "output",
        (
            CubeTypeChange(
                "event",
                "e",
                "A",
                "B",
                relations=(
                    E2OEvidence("e", "o", "flow"),
                    E2OEvidence("e", "o", "audit"),
                ),
            ),
        ),
    )
    values = object_panels(value)
    evidence = next(p for p in values if p.id == "oc-cube-evidence")
    assert json.loads(evidence.rows[0][-1]) == [["e", "o", "flow"], ["e", "o", "audit"]]


def test_statistics_lifecycle_isolated_object_nulls_and_population_units():
    values = panels(object_statistics(example()))
    assert values[0].rows[-2:] == (
        ("participations", 6, "distinct_event_object_pairs"),
        ("qualified_relations", 7, "qualified_e2o_rows"),
    )
    idle = next(r for r in values[-1].rows if r[0] == "unused")
    assert idle[2:7] == (0, 0, None, None, None)


def test_interleaving_identical_source_ids_stay_separate_and_cross_link_has_time_unit():
    _, _, result = interleaving()
    graph, time, links = panels(result)
    assert len(graph.nodes) == 4 and len({n.id for n in graph.nodes}) == 4
    assert {n.group for n in graph.nodes} == {"left", "right"}
    assert len([e for e in graph.edges if e.kind == "within_process_segment"]) == 2
    cross = next(e for e in graph.edges if e.kind == "cross_process_candidate")
    assert (cross.label, cross.metrics[0].value, cross.metrics[0].unit) == (
        "LR",
        5.0,
        "seconds",
    )
    assert len(time.lanes) == 2 and len(time.items) == 4
    assert links.rows == (("same-case", "same-case"),)


def test_interleaving_boundaries_have_no_invented_clock_or_event_id():
    _, _, result = interleaving(True)
    graph, time, _ = panels(result)
    boundaries = [n for n in graph.nodes if n.kind == "logical_boundary"]
    assert boundaries
    assert all(
        fields(n)["event_id"] is None and fields(n)["observed_time"] is None
        for n in boundaries
    )
    assert len(time.items) == 4


def test_interleaving_bridge_keeps_candidate_links_and_original_own_case_qualifiers():
    left, right, result = interleaving()
    conversion = from_interleavings(left, right, result)
    values = object_panels(conversion)
    full = next(p for p in values if p.id == "ocel-incidence")
    assert len([e for e in full.edges if e.label == "case"]) == 4
    assert len([e for e in full.edges if e.label == "interleaving_candidate"]) == 1
    report = next(p for p in values if p.id == "oc-interleaving-projection")
    assert len(report.edges) == 1 and report.edges[0].metrics[0].value == 1


def test_all_supported_families_round_trip_visualization_json_without_mutating_input():
    log = example()
    extraction = discover_executions(log, ExecutionSpec("connected_components"))
    replay = replay_object_log(log, model(), ObjectReplaySpec(("Order", "Item")))
    left, right, crossing = interleaving()
    conversion = from_interleavings(left, right, crossing)
    results = (
        discover_object_graph(log),
        discover_etot(log),
        discover_otg(log),
        query_object_relations(log, ObjectRelationSpec(("e1",))),
        discover_ocdfg(log, OCDFGSpec(("Order",))),
        extraction,
        discover_variants(extraction, VariantSpec()),
        align_object_log(log, model(), ObjectAlignmentSpec(("Order", "Item"))),
        replay,
        replay_flattened_object_log(log, model(), ObjectReplaySpec(("Order", "Item"))),
        evaluate_constraint_graph(log, constraints()),
        measure_rule_metric(log, ObjectRuleMetricSpec("Order", "A", "existence")),
        measure_performance(log),
        measure_replay_performance(log, replay),
        temporal_summary(log),
        drill_down(log, DrillDownSpec("Order", "state", BASE)),
        object_statistics(log),
        crossing,
        conversion.evidence,
    )
    for result in results:
        value = result.value
        document = VisualizationDocument(result.operator_id, panels(result))
        assert loads_visualization(dumps_visualization(document)) == document
        assert result.value is value
    for value in (log, constraints(), conversion, extraction.value.executions[0]):
        document = VisualizationDocument("raw", object_panels(value))
        assert loads_visualization(dumps_visualization(document)) == document


def test_unknown_payload_returns_none_and_wrong_envelope_is_rejected():
    assert object_panels(object()) is None
    result = temporal_summary(example())
    with pytest.raises(ValueError, match="differs"):
        object_panels(example(), source=result)
    with pytest.raises(TypeError, match="ComputationResult"):
        object_panels(result.value, source=example())


def test_empty_ocel_and_empty_families_do_not_fabricate_counts_or_events():
    empty = OCEL()
    graph, time, attrs, schema = object_panels(empty)
    assert graph.nodes == graph.edges == time.items == time.lanes == attrs.rows == ()
    values = panels(temporal_summary(empty))
    assert all(not chart.series[0].points for chart in pick(values, ChartPanel))
    assert object_panels(CubePlan("fold", "x", ()))[0].cells == ()
    assert schema.rows == ()


def test_ocel_fact_row_permutation_does_not_change_visual_semantics_or_layout_input():
    log = example()
    permuted = replace(
        log,
        events=tuple(reversed(log.events)),
        objects=tuple(reversed(log.objects)),
        e2o=tuple(reversed(log.e2o)),
        o2o=tuple(reversed(log.o2o)),
    )
    assert object_panels(log) == object_panels(permuted)


def test_execution_boundary_objects_and_excluded_qualifiers_are_visible_but_not_selected_edges():
    log = example()
    log = replace(log, e2o=log.e2o + (E2O("e2", "unused", "context"),))
    result = discover_executions(
        log,
        ExecutionSpec(
            "connected_components", object_types=("Order",), qualifiers=("flow",)
        ),
    )
    values = panels(result)
    graph = pick(values, GraphPanel)[0]
    boundary = next(n for n in graph.nodes if fields(n).get("object_id") == "unused")
    assert fields(boundary)["scope"] == "boundary"
    assert not any(edge.target == boundary.id for edge in graph.edges)
    excluded = next(p for p in values if p.title == "Excluded execution relations")
    assert set(excluded.rows) == {("e2", "e1", "audit"), ("e2", "unused", "context")}
    lanes = next(
        p for p in values if isinstance(p, TimelinePanel) and p.axis_type == "timestamp"
    )
    boundary_lane = next(lane for lane in lanes.lanes if lane.label == "unused")
    assert not any(item.lane == boundary_lane.id for item in lanes.items)


def test_explicit_tie_break_is_marked_in_order_graph_not_presented_as_observed_clock_gap():
    log = example()
    log = replace(
        log, events=(log.events[0], replace(log.events[1], time=BASE), log.events[2])
    )
    result = discover_executions(
        log, ExecutionSpec("connected_components", tie_policy="event_id")
    )
    values = panels(result)
    graph = pick(values, GraphPanel)[0]
    assert len([e for e in graph.edges if fields(e).get("tie_broken")]) == 2
    ranks = next(
        p
        for p in values
        if isinstance(p, TimelinePanel) and p.unit == "precedence_layers"
    )
    assert {i.start for i in ranks.items if fields(i)["event_id"] in ("e1", "e2")} == {
        0,
        1,
    }
    clock = next(
        p for p in values if isinstance(p, TimelinePanel) and p.axis_type == "timestamp"
    )
    assert (
        len({i.start for i in clock.items if fields(i)["event_id"] in ("e1", "e2")})
        == 1
    )


def test_typed_identifier_framing_preserves_delimiter_looking_ids_and_unicode():
    log = OCEL(
        event_types=(EventType('<A & "동작">'),),
        object_types=(ObjectType("T"),),
        events=(Event("e|o", '<A & "동작">', BASE), Event("e", '<A & "동작">', BASE)),
        objects=(Object("o", "T"), Object("o|o", "T")),
        e2o=(E2O("e|o", "o", ""), E2O("e", "o|o", "")),
    )
    doc = VisualizationDocument("Unicode", object_panels(log))
    graph = doc.panels[0]
    assert len({e.id for e in graph.edges}) == 2
    assert all(e.label == "" and fields(e)["qualifier"] == "" for e in graph.edges)
    assert loads_visualization(dumps_visualization(doc)) == doc


def test_ocel_timestamp_attributes_are_distinct_from_iso_looking_strings():
    def source(kind, value):
        return OCEL(
            event_types=(EventType("A", (Attribute("when", kind),)),),
            events=(Event("e", "A", BASE, (EventAttr("when", value),)),),
        )

    timestamp = object_panels(source(ValueType.TIME, BASE))
    text = object_panels(source(ValueType.STRING, BASE.isoformat()))
    assert timestamp != text
    assert timestamp[2].rows[0][-1] == "time"
    assert text[2].rows[0][-1] == "string"
    assert timestamp[3].rows[0][-1] == "time"
    assert text[3].rows[0][-1] == "string"
