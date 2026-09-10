from dataclasses import FrozenInstanceError, replace

import pytest

from pix.contracts.graph import (
    GraphCounts,
    GraphDocument,
    GraphEdge,
    GraphEvidence,
    GraphNode,
)


def sample_graph(label="Pack"):
    evidence = (
        GraphEvidence("e1", "e2", "o1", ("",), ("item",)),
        GraphEvidence("e1", "e2", "o2", ("item",), ("item",)),
    )
    return GraphDocument(
        "ocdfg",
        "source-digest",
        "computation-id",
        (
            GraphNode("a", label, ("e1",), ("o1", "o2")),
            GraphNode("b", "Ship", ("e2",), ("o1", "o2")),
        ),
        (GraphEdge("ab", "a", "b", "Order", GraphCounts(1, 2, 2), evidence),),
        ("Order",),
    )


def test_graph_preserves_counts_evidence_and_separate_identity():
    graph = sample_graph()
    assert graph.edges[0].counts == GraphCounts(1, 2, 2)
    assert graph.edges[0].evidence[0].source_qualifiers == ("",)
    same_label = replace(graph.nodes[1], label=graph.nodes[0].label)
    assert replace(graph, nodes=(graph.nodes[0], same_label)).nodes[1].id == "b"
    with pytest.raises(FrozenInstanceError):
        graph.nodes = ()


@pytest.mark.parametrize(
    "field,value",
    [
        ("event_pairs", -1),
        ("unique_objects", True),
        ("occurrences", 1.0),
    ],
)
def test_count_contract_rejects_invalid_numbers(field, value):
    with pytest.raises(ValueError):
        GraphCounts(
            **{**dict(event_pairs=1, unique_objects=1, occurrences=1), field: value}
        )


def test_counts_must_match_evidence_and_duplicate_triples_are_rejected():
    edge = sample_graph().edges[0]
    with pytest.raises(ValueError, match="counts"):
        replace(edge, counts=GraphCounts(2, 2, 2))
    with pytest.raises(ValueError, match="unique"):
        replace(edge, evidence=edge.evidence + edge.evidence[:1])


def test_node_and_edge_references_are_verified():
    graph = sample_graph()
    with pytest.raises(ValueError, match="endpoints"):
        replace(graph, edges=(replace(graph.edges[0], target="absent"),))
    with pytest.raises(ValueError, match="sources"):
        replace(
            graph, nodes=(replace(graph.nodes[0], event_ids=("wrong",)), graph.nodes[1])
        )
    with pytest.raises(ValueError, match="declared"):
        replace(graph, object_types=("Other",))


def test_graph_requires_immutable_sequences_and_unique_ids():
    graph = sample_graph()
    with pytest.raises(TypeError, match="tuple"):
        replace(graph, nodes=list(graph.nodes))
    with pytest.raises(ValueError, match="unique"):
        replace(graph, nodes=graph.nodes + graph.nodes[:1])
    with pytest.raises(ValueError, match="distinct"):
        replace(graph, edges=(replace(graph.edges[0], id="a"),))
    with pytest.raises(ValueError, match="Unicode"):
        replace(graph.nodes[0], label="\ud800")


def test_empty_graph_retains_provenance():
    graph = GraphDocument("dfg", "digest", "calculation", (), (), ("Order",))
    assert not graph.nodes and graph.source_digest == "digest"
