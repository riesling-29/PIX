from dataclasses import replace

import pytest

from pix.contracts.analysis import (
    ActivityCount,
    DirectlyFollowsEdge,
    DirectlyFollowsGraph,
    E2OEvidence,
    ObjectCentricDFG,
    OCDFGEdge,
    OCDFGSpec,
    OCDFGTypeGraph,
    TraceSpec,
    TransitionEvidence,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.viewer import build_graph


def result_fixture():
    evidence = tuple(
        TransitionEvidence(
            obj,
            "e1",
            "e2",
            (E2OEvidence("e1", obj, ""), E2OEvidence("e1", obj, "item")),
            (E2OEvidence("e2", obj, "item"),),
        )
        for obj in ("o1", "o2")
    )
    dfg = DirectlyFollowsGraph(
        "Order",
        3,
        ("empty",),
        (
            ActivityCount("Pack", 2, ("e1",), ("o1", "o2")),
            ActivityCount("Ship", 2, ("e2",), ("o1", "o2")),
        ),
        (DirectlyFollowsEdge("Pack", "Ship", 2, evidence),),
        (),
        (),
    )
    return ComputationResult(
        "pix.discover_dfg",
        "1",
        "digest",
        TraceSpec("Order"),
        ComputeStatus.COMPUTED,
        dfg,
        (),
        "calc",
    )


def test_adapter_three_count_units_and_original_qualifiers():
    result = result_fixture()
    graph = build_graph(result)
    assert graph.edges[0].counts.event_pairs == 1
    assert graph.edges[0].counts.unique_objects == 2
    assert graph.edges[0].evidence[0].source_qualifiers == ("", "item")
    assert graph.source_digest == "digest" and graph.computation_id == "calc"
    assert any("1 objects have no event" in note for note in graph.notes)
    assert any("equal-time policy: reject" in note for note in graph.notes)
    assert any(
        "E2O qualifier selection: all qualifiers" in note for note in graph.notes
    )
    assert any("pix.discover_dfg (version 1)" in note for note in graph.notes)
    assert result == result_fixture()


def test_adapter_keeps_parallel_object_type_edges_and_deduplicates_node_events():
    result = result_fixture()
    dfg = result.value
    graphs = tuple(
        OCDFGTypeGraph(
            type_name,
            dfg.object_count,
            (),
            dfg.activities,
            (OCDFGEdge(type_name, "Pack", "Ship", 1, 2, 2, dfg.edges[0].evidence),),
            (),
            (),
        )
        for type_name in ("Order", "Package")
    )
    combined = replace(
        result, value=ObjectCentricDFG(graphs), spec=OCDFGSpec(("Order", "Package"))
    )
    graph = build_graph(combined)
    assert len(graph.nodes) == 2 and len(graph.edges) == 2
    assert graph.nodes[0].event_ids == ("e1",)
    assert graph.edges[0].id != graph.edges[1].id
    assert graph.edges[0].source == graph.edges[1].source
    assert graph == build_graph(replace(combined, value=ObjectCentricDFG(graphs[::-1])))


def test_ids_are_stable_when_counts_or_title_change():
    result = result_fixture()
    graph = build_graph(result)
    edge = result.value.edges[0]
    reduced = replace(
        result,
        value=replace(
            result.value,
            edges=(replace(edge, occurrence_count=1, evidence=edge.evidence[:1]),),
        ),
    )
    assert graph.edges[0].id == build_graph(reduced, title="New title").edges[0].id
    assert all(node.id != node.label for node in graph.nodes)


def test_failed_results_and_unsupported_payload_are_not_graphs():
    result = result_fixture()
    failed = replace(
        result,
        status=ComputeStatus.UNAVAILABLE,
        value=None,
        issues=(ComputeIssue("tie", "Order unresolved"),),
    )
    with pytest.raises(ValueError, match="successfully"):
        build_graph(failed)
    with pytest.raises(TypeError, match="DFG"):
        build_graph(replace(result, value=TraceSpec("Order")))
    with pytest.raises(TypeError, match="ComputationResult"):
        build_graph({})


def test_inconsistent_counts_are_rejected():
    result = result_fixture()
    edge = replace(result.value.edges[0], occurrence_count=9)
    with pytest.raises(ValueError, match="counts"):
        build_graph(replace(result, value=replace(result.value, edges=(edge,))))
