"""Hand-checkable model-view contracts, including unusual valid model states."""

from dataclasses import FrozenInstanceError, replace

import pytest

from pix.compute.model_semantics import model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.graph import ModelGraphDocument, ModelGraphEdge, ModelGraphNode
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.models import ModelArtifact, model_from_json, model_json_bytes
from pix.viewer.model_adapter import build_model_graph


def petri_fixture() -> PetriNet:
    return PetriNet(
        (Place("start"), Place("end"), Place("unlinked")),
        (
            Transition("a", "Approve"),
            Transition("b", "Approve"),
            Transition("silent"),
            Transition("visible-tau", "τ"),
        ),
        (Arc("start", "a", 2), Arc("a", "end", 3), Arc("a", "start", 1)),
        Marking((("start", 5), ("end", 1))),
        Marking((("end", 2), ("start", 1))),
    )


def object_fixture(*, minimum: int = 0, maximum: int | None = None):
    return ObjectCentricPetriNet(
        (
            TypedPlace("in", "Order"),
            TypedPlace("out", "Order"),
            TypedPlace("isolated", "Resource"),
        ),
        (Transition("pack", "Pack"), Transition("unlinked", "Pack")),
        (
            ObjectArc("in", "pack", True, minimum, maximum),
            ObjectArc("pack", "out", True, minimum, maximum),
        ),
        ObjectMarking(
            (ObjectToken("in", "o1"), ObjectToken("in", "o1"), ObjectToken("out", "o1"))
        ),
        ObjectMarking((ObjectToken("out", "o1"), ObjectToken("out", "o2"))),
        (("o1", "Order"), ("o2", "Order"), ("idle", "UnusedType")),
    )


def test_weighted_petri_keeps_labels_markings_and_arc_directions():
    net = petri_fixture()
    graph = build_model_graph(net)
    nodes = {node.model_node_id: node for node in graph.nodes}
    assert len(nodes) == 7 and len(graph.edges) == 3
    assert nodes["a"].label == nodes["b"].label == "Approve"
    assert nodes["a"].id != nodes["b"].id
    assert nodes["silent"].kind == "silent"
    assert nodes["visible-tau"].kind == "transition"
    assert nodes["silent"].label == nodes["visible-tau"].label == "τ"
    assert (nodes["start"].initial_count, nodes["start"].final_count) == (5, 1)
    assert (nodes["end"].initial_count, nodes["end"].final_count) == (1, 2)
    assert nodes["unlinked"].initial_count == nodes["unlinked"].final_count == 0
    arcs = {(edge.source, edge.target): edge for edge in graph.edges}
    assert arcs[nodes["start"].id, nodes["a"].id].weight == 2
    assert arcs[nodes["a"].id, nodes["end"].id].weight == 3
    assert arcs[nodes["a"].id, nodes["start"].id].weight == 1
    assert all(edge.object_type is None and not edge.variable for edge in graph.edges)
    assert all(edge.min_objects == edge.max_objects == 1 for edge in graph.edges)
    assert graph.model_digest == model_digest(net)
    assert graph.objects == graph.object_types == ()
    assert graph.origin == "unspecified" and graph.source_computation_id is None
    assert any("not observed event frequencies" in note for note in graph.notes)


@pytest.mark.parametrize("count", [0, 1, 2, 2**60 + 1])
def test_petri_zero_single_and_large_token_counts_remain_exact(count):
    marking = Marking((("p", count),)) if count else Marking()
    net = PetriNet((Place("p"),), (), (), marking, Marking())
    node = build_model_graph(net).nodes[0]
    assert node.initial_count == count and type(node.initial_count) is int
    assert node.final_count == 0


def test_arbitrary_size_weight_is_not_rounded_or_used_as_cardinality():
    net = replace(petri_fixture(), arcs=(Arc("start", "a", 2**60 + 1),))
    edge = build_model_graph(net).edges[0]
    assert edge.weight == 2**60 + 1 and edge.min_objects == edge.max_objects == 1


@pytest.mark.parametrize("object_centric", [False, True])
def test_completely_empty_nets_are_valid(object_centric):
    net = (
        ObjectCentricPetriNet((), (), (), ObjectMarking(), ObjectMarking(), ())
        if object_centric
        else PetriNet((), (), (), Marking(), Marking())
    )
    graph = build_model_graph(net)
    assert graph.nodes == graph.edges == graph.objects == graph.object_types == ()
    assert graph.kind == ("ocpn" if object_centric else "petri_net")


@pytest.mark.parametrize(
    "minimum,maximum", [(0, None), (0, 0), (1, 1), (2, 5), (0, 2**60 + 1)]
)
def test_ocpn_preserves_variable_policy_and_repeated_object_tokens(minimum, maximum):
    net = object_fixture(minimum=minimum, maximum=maximum)
    graph = build_model_graph(net)
    nodes = {node.model_node_id: node for node in graph.nodes}
    assert graph.kind == "ocpn"
    assert graph.model_digest == model_digest(net)
    assert nodes["in"].initial_objects == ("o1", "o1")
    assert nodes["in"].initial_count == 2 and nodes["in"].final_count == 0
    assert nodes["out"].initial_objects == ("o1",)
    assert nodes["out"].final_objects == ("o1", "o2")
    assert nodes["out"].final_count == 2
    assert graph.objects == net.objects
    assert graph.object_types == ("Order", "Resource", "UnusedType")
    assert all(edge.variable for edge in graph.edges)
    assert all(
        edge.min_objects == minimum
        and edge.max_objects == maximum
        and edge.weight == 1
        and edge.object_type == "Order"
        for edge in graph.edges
    )
    assert any("cannot generate new object IDs" in note for note in graph.notes)
    assert any("one shared object set" in note for note in graph.notes)


def test_fixed_ocpn_arc_has_one_object_with_distinct_type_edges():
    net = ObjectCentricPetriNet(
        (TypedPlace("p", "Order"), TypedPlace("r", "Resource")),
        (Transition("t", "Approve"),),
        (ObjectArc("p", "t"), ObjectArc("r", "t")),
        ObjectMarking(),
        ObjectMarking(),
        (),
    )
    graph = build_model_graph(net)
    assert {edge.object_type for edge in graph.edges} == {"Order", "Resource"}
    assert all(
        not edge.variable and edge.min_objects == edge.max_objects == 1
        for edge in graph.edges
    )
    assert len({edge.id for edge in graph.edges}) == 2


@pytest.mark.parametrize(
    "origin,source",
    [("provided", None), ("unspecified", None), ("discovered", "pix.compute:example")],
)
def test_real_model_artifact_roundtrip_preserves_declared_origin(origin, source):
    artifact = ModelArtifact(object_fixture(), origin, source)
    loaded = model_from_json(model_json_bytes(artifact))
    graph = build_model_graph(loaded, title="공동 포장")
    assert graph.origin == origin and graph.source_computation_id == source
    assert graph.title == "공동 포장"
    assert graph.model_digest == model_digest(artifact.model)
    assert any(f"Model origin: {origin}" in note for note in graph.notes)


def test_graph_identity_is_stable_across_titles_labels_weights_and_collection_order():
    net = petri_fixture()
    graph = build_model_graph(net)
    reordered = replace(
        net,
        places=net.places[::-1],
        transitions=net.transitions[::-1],
        arcs=net.arcs[::-1],
    )
    assert build_model_graph(reordered) == graph
    changed = replace(
        net,
        transitions=tuple(
            replace(item, activity="New") if item.id == "a" else item
            for item in net.transitions
        ),
        arcs=tuple(replace(arc, weight=arc.weight + 1) for arc in net.arcs),
    )
    changed_graph = build_model_graph(changed, title="Changed")
    assert {node.id for node in graph.nodes} == {
        node.id for node in changed_graph.nodes
    }
    assert {edge.id for edge in graph.edges} == {
        edge.id for edge in changed_graph.edges
    }
    assert graph.model_digest != changed_graph.model_digest


def test_unicode_and_control_characters_are_preserved_for_renderer_to_encode():
    net = PetriNet(
        (Place("<p>\x01"),),
        (Transition("t😀", "승인<&>\x01"),),
        (Arc("<p>\x01", "t😀"),),
        Marking(),
        Marking(),
    )
    graph = build_model_graph(net)
    assert {node.model_node_id for node in graph.nodes} == {"<p>\x01", "t😀"}
    assert any(node.label == "승인<&>\x01" for node in graph.nodes)


def test_immutable_contracts_have_no_fake_observed_metrics():
    graph = build_model_graph(petri_fixture())
    with pytest.raises(FrozenInstanceError):
        graph.title = "changed"
    assert not hasattr(graph, "source_digest")
    assert not hasattr(graph.nodes[0], "event_ids")
    assert not hasattr(graph.edges[0], "counts")
    assert not hasattr(graph.edges[0], "evidence")


@pytest.mark.parametrize(
    "bad", [None, "net", {}, ProcessTree("activity", activity="A")]
)
def test_adapter_rejects_unsupported_inputs(bad):
    with pytest.raises(TypeError):
        build_model_graph(bad)


def test_adapter_rejects_process_tree_artifact():
    with pytest.raises(TypeError):
        build_model_graph(ModelArtifact(ProcessTree("activity", activity="A")))


@pytest.mark.parametrize(
    "field,value",
    [
        ("initial_count", True),
        ("final_count", -1),
        ("initial_objects", ["o"]),
        ("model_node_id", " "),
        ("id", ""),
        ("kind", "activity"),
    ],
)
def test_node_rejects_invalid_required_fields(field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(ModelGraphNode("p", "p", "place", "p"), **{field: value})


def test_node_rejects_inconsistent_marking_semantics():
    with pytest.raises(ValueError, match="only places"):
        ModelGraphNode("t", "A", "transition", "t", initial_count=1)
    with pytest.raises(ValueError, match="typed place"):
        ModelGraphNode("p", "p", "place", "p", initial_objects=("o",))
    with pytest.raises(ValueError, match="multiplicity"):
        ModelGraphNode("p", "p", "place", "p", "Order", 1, 0, ("o", "o"))


@pytest.mark.parametrize(
    "changes",
    [
        {"weight": 0},
        {"weight": True},
        {"variable": 1},
        {"variable": True},
        {"object_type": "Order", "weight": 2},
        {"min_objects": 0},
        {"object_type": "Order", "variable": True, "min_objects": 2, "max_objects": 1},
    ],
)
def test_edge_rejects_invalid_arc_semantics(changes):
    with pytest.raises((TypeError, ValueError)):
        replace(ModelGraphEdge("e", "p", "t"), **changes)


def test_document_rejects_invalid_references_and_nonbipartite_arcs():
    graph = build_model_graph(petri_fixture())
    edge = graph.edges[0]
    with pytest.raises(ValueError, match="endpoints"):
        replace(graph, edges=(replace(edge, target="absent"),))
    with pytest.raises(ValueError, match="place and a transition"):
        replace(graph, edges=(replace(edge, target=edge.source),))
    with pytest.raises(ValueError, match="duplicate arc incidence"):
        replace(graph, edges=(edge, replace(edge, id="different")))
    with pytest.raises(ValueError, match="model node IDs"):
        replace(graph, nodes=graph.nodes + (replace(graph.nodes[0], id="different"),))


def test_document_checks_object_universe_marking_and_type_policy():
    graph = build_model_graph(object_fixture())
    with pytest.raises(ValueError, match="marking object"):
        replace(graph, objects=tuple(item for item in graph.objects if item[0] != "o1"))
    with pytest.raises(ValueError, match="unique"):
        replace(graph, objects=graph.objects + (graph.objects[0],))
    with pytest.raises(ValueError, match="type must be declared"):
        replace(graph, object_types=("Order",))
    with pytest.raises(ValueError, match="one cardinality policy"):
        replace(graph, edges=(replace(graph.edges[0], min_objects=1), graph.edges[1]))
    with pytest.raises(ValueError, match="match its place"):
        replace(graph, edges=(replace(graph.edges[0], object_type="Resource"),))


def test_document_rejects_invalid_provenance_or_kind():
    graph = build_model_graph(petri_fixture())
    with pytest.raises((TypeError, ValueError)):
        replace(graph, origin="discovered")
    with pytest.raises(ValueError, match="only discovered"):
        replace(graph, source_computation_id="compute")
    with pytest.raises(ValueError, match="unsupported model graph kind"):
        replace(graph, kind="dfg")
    with pytest.raises(ValueError, match="no object universe"):
        replace(graph, object_types=("Order",))
    with pytest.raises(ValueError, match="model_digest"):
        replace(graph, model_digest="")


def test_document_direct_constructor_cannot_misrepresent_untyped_ocpn_place():
    with pytest.raises(ValueError, match="place type must be declared"):
        ModelGraphDocument(
            "ocpn",
            "digest",
            "unspecified",
            (ModelGraphNode("p", "p", "place", "p"),),
            (),
            (),
        )
