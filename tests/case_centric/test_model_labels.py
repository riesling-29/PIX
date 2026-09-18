"""Occurrence identity and independently enumerated relabeling semantics."""

from collections import Counter, deque
from dataclasses import FrozenInstanceError

import pytest

from pix.case_centric.model_labels import (
    ModelLabelReadSpec,
    ModelLabelRenameSpec,
    activity_labels,
    rename_activity_labels,
)
from pix.case_centric.powl import POWLNode, powl_to_petri_net
from pix.case_centric.split_miner import SplitBPMN, SplitBPMNFlow, SplitBPMNNode
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.model_semantics import fire_binding, model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import (
    Arc,
    Binding,
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
from pix.contracts.result import ComputeStatus
from pix.models import ModelArtifact, model_document


def chain():
    return PetriNet(
        tuple(Place(p) for p in ("i", "m", "n", "o")),
        (Transition("first", "A"), Transition("second", "A"), Transition("silent")),
        (
            Arc("i", "first"),
            Arc("first", "m"),
            Arc("m", "second"),
            Arc("second", "n"),
            Arc("n", "silent"),
            Arc("silent", "o"),
        ),
        Marking((("i", 1),)),
        Marking((("o", 1),)),
    )


def language(net, max_length=4):
    """Token arithmetic oracle, independent of production firing/reachability."""
    initial = net.initial_marking.tokens
    pending = deque(((initial, ()),))
    seen, accepted = {(initial, ())}, set()
    while pending:
        marking, word = pending.popleft()
        if marking == net.final_marking.tokens:
            accepted.add(word)
        for transition in net.transitions:
            tokens = Counter(dict(marking))
            inputs = {a.source: a.weight for a in net.arcs if a.target == transition.id}
            if any(tokens[p] < weight for p, weight in inputs.items()):
                continue
            if transition.activity is not None and len(word) >= max_length:
                continue
            tokens.subtract(inputs)
            tokens.update(
                {a.target: a.weight for a in net.arcs if a.source == transition.id}
            )
            after = tuple(sorted((p, weight) for p, weight in tokens.items() if weight))
            trace = (
                word if transition.activity is None else (*word, transition.activity)
            )
            state = (after, trace)
            if state not in seen:
                seen.add(state)
                assert len(seen) < 10000, (
                    "manual oracle unexpectedly exceeded its budget"
                )
                pending.append(state)
    return accepted


def rename(model, *pairs):
    return rename_activity_labels(model, ModelLabelRenameSpec(tuple(pairs)))


def test_repeated_transition_labels_preserve_identity_and_rename_visible_language():
    net = chain()
    source_digest = model_digest(net)
    rows = activity_labels(net).value.occurrences
    assert [(r.occurrence_id, r.activity, r.silent) for r in rows] == [
        ("transition/first", "A", False),
        ("transition/second", "A", False),
        ("transition/silent", None, True),
    ]
    result = rename(net, ("transition/first", "X"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.source_digest == source_digest == result.value.source_model_digest
    assert result.value.output_model_digest == model_digest(result.value.model)
    assert result.value.output_model_digest != source_digest
    assert language(net) == {("A", "A")}
    assert language(result.value.model) == {("X", "A")}
    assert model_digest(net) == source_digest
    assert result.value.model.arcs == net.arcs
    assert result.value.model.places == net.places
    assert result.value.model.initial_marking == net.initial_marking
    assert result.value.model.final_marking == net.final_marking
    assert [t.id for t in result.value.model.transitions] == [
        t.id for t in net.transitions
    ]


def test_label_collisions_do_not_merge_occurrences():
    result = rename(
        chain(), ("transition/first", "Same"), ("transition/second", "Same")
    )
    assert len(result.value.model.transitions) == 3
    assert language(result.value.model) == {("Same", "Same")}
    assert [change.occurrence_id for change in result.value.changes] == [
        "transition/first",
        "transition/second",
    ]


def test_silence_is_explicit_and_not_an_empty_label():
    net = chain()
    assert (
        len(
            activity_labels(
                net, ModelLabelReadSpec(include_silent=False)
            ).value.occurrences
        )
        == 2
    )
    with pytest.raises(ValueError, match="silent"):
        rename(net, ("transition/silent", "Tau is not an activity"))
    assert next(t for t in net.transitions if t.id == "silent").activity is None


@pytest.mark.parametrize("activity", [None, "", "  ", 1, True, "\ud800"])
def test_invalid_replacement_labels_are_rejected(activity):
    with pytest.raises(ValueError):
        ModelLabelRenameSpec((("transition/first", activity),))


def test_replacement_ids_are_exact_and_atomic():
    net = chain()
    with pytest.raises(ValueError, match="unknown"):
        rename(net, ("transition/first", "Valid"), ("A", "Bad label lookup"))
    assert language(net) == {("A", "A")}
    with pytest.raises(ValueError, match="duplicate"):
        ModelLabelRenameSpec((("transition/first", "X"), ("transition/first", "Y")))


def test_noop_digest_identity_and_request_canonicalization():
    net = chain()
    noop = rename(net)
    assert noop.value.model == net
    assert noop.value.source_model_digest == noop.value.output_model_digest
    assert noop.value.changes == ()
    first = rename(net, ("transition/second", "Y"), ("transition/first", "X"))
    second = rename(net, ("transition/first", "X"), ("transition/second", "Y"))
    assert first == second
    assert first.computation_id != noop.computation_id


@pytest.mark.parametrize("kind", [ProcessTree, POWLNode])
def test_tree_occurrence_paths_distinguish_identical_shared_leaf_instances(kind):
    leaf = kind("activity", "A")
    if kind is ProcessTree:
        model = kind("parallel", children=(leaf, leaf, kind("tau")))
        converter, prefix = process_tree_to_petri_net, "tree"
    else:
        model = kind("partial_order", children=(leaf, leaf, kind("tau")))
        converter, prefix = powl_to_petri_net, "powl"
    rows = activity_labels(model).value.occurrences
    assert [r.occurrence_id for r in rows] == [
        prefix + "/0",
        prefix + "/1",
        prefix + "/2",
    ]
    assert [r.tree_path for r in rows] == [(0,), (1,), (2,)]
    converted = rename(model, (prefix + "/1", "B")).value.model
    assert language(converter(model)) == {("A", "A")}
    assert language(converter(converted)) == {("A", "B"), ("B", "A")}
    assert model.children[0] is model.children[1]
    assert converted.children[0].activity == "A"
    assert converted.children[1].activity == "B"
    with pytest.raises(ValueError, match="silent"):
        rename(model, (prefix + "/2", "C"))


@pytest.mark.parametrize("kind,prefix", [(ProcessTree, "tree"), (POWLNode, "powl")])
def test_single_root_leaf_has_an_address(kind, prefix):
    model = kind("activity", "old")
    assert activity_labels(model).value.occurrences[0].occurrence_id == prefix + "/root"
    assert rename(model, (prefix + "/root", "new")).value.model.activity == "new"


def test_powl_relabel_retains_partial_order_and_nested_occurrences():
    model = POWLNode(
        "partial_order",
        children=(
            POWLNode("activity", "A"),
            POWLNode(
                "xor", children=(POWLNode("activity", "A"), POWLNode("activity", "B"))
            ),
        ),
        order=((0, 1),),
    )
    result = rename(model, ("powl/1/0", "C")).value.model
    assert result.order == model.order == ((0, 1),)
    assert language(powl_to_petri_net(result)) == {("A", "C"), ("A", "B")}


def bpmn():
    return SplitBPMN(
        (
            SplitBPMNNode("start", "start_event"),
            SplitBPMNNode("one", "task", "A"),
            SplitBPMNNode("two", "task", "A"),
            SplitBPMNNode("end", "end_event"),
        ),
        (
            SplitBPMNFlow("f1", "start", "one"),
            SplitBPMNFlow("f2", "one", "two"),
            SplitBPMNFlow("f3", "two", "end"),
        ),
        "start",
        "end",
    )


def test_bpmn_structural_nodes_are_not_activities_and_graph_is_preserved():
    from pix.case_centric.bpmn_conversion import bpmn_to_petri_net

    model = bpmn()
    assert [r.occurrence_id for r in activity_labels(model).value.occurrences] == [
        "task/one",
        "task/two",
    ]
    output = rename(model, ("task/two", "B")).value.model
    assert output.flows == model.flows
    assert (output.start_id, output.end_id) == (model.start_id, model.end_id)
    assert language(bpmn_to_petri_net(output).value.model) == {("A", "B")}
    with pytest.raises(ValueError, match="unknown"):
        rename(model, ("task/start", "Not a task"))


def ocpn():
    return ObjectCentricPetriNet(
        (TypedPlace("i", "Item"), TypedPlace("o", "Item")),
        (Transition("ship", "Ship"),),
        (ObjectArc("i", "ship", True, 1, 2), ObjectArc("ship", "o", True, 1, 2)),
        objects=(("item1", "Item"), ("item2", "Item")),
        initial_marking=ObjectMarking(
            (ObjectToken("i", "item1"), ObjectToken("i", "item2"))
        ),
        final_marking=ObjectMarking(
            (ObjectToken("o", "item1"), ObjectToken("o", "item2"))
        ),
    )


def test_ocpn_relabel_preserves_concrete_tokens_cardinality_and_binding_identity():
    model = ocpn()
    output = rename(model, ("transition/ship", "Dispatch")).value.model
    binding = Binding("ship", (("Item", ("item1", "item2")),))
    assert fire_binding(model, model.initial_marking, binding) == model.final_marking
    assert fire_binding(output, output.initial_marking, binding) == output.final_marking
    assert output.arcs == model.arcs
    assert output.objects == model.objects
    assert output.initial_marking == model.initial_marking


def test_provenance_and_immutability_are_retained():
    model = chain()
    artifact = ModelArtifact(model, "discovered", "discovery:source")
    read = activity_labels(artifact)
    renamed = rename(artifact, ("transition/first", "X"))
    assert (
        read.parent_computation_ids
        == renamed.parent_computation_ids
        == ("discovery:source",)
    )
    assert read.source_digest == model_document(model)["model_digest"]
    with pytest.raises(FrozenInstanceError):
        renamed.value.model = model
    with pytest.raises(FrozenInstanceError):
        read.value.occurrences[0].activity = "Changed"


def test_unsupported_models_and_subclasses_are_not_generic_dataclass_rewritten():
    from pix.case_centric.discovery import FootprintModel

    class CustomTree(ProcessTree):
        pass

    for model in (
        FootprintModel((), (), (), (), (), (), (), (), 0, 0),
        CustomTree("activity", "A"),
        object(),
    ):
        with pytest.raises(TypeError, match="unsupported"):
            activity_labels(model)
        with pytest.raises(TypeError, match="unsupported"):
            rename(model)


def test_size_and_depth_bounds_reject_before_publishing_partial_output():
    model = ProcessTree("activity", "A")
    for _ in range(5):
        model = ProcessTree("sequence", children=(model, ProcessTree("tau")))
    with pytest.raises(ValueError, match="max_depth"):
        activity_labels(model, ModelLabelReadSpec(max_depth=3))
    with pytest.raises(ValueError, match="max_model_nodes"):
        rename_activity_labels(chain(), ModelLabelRenameSpec(max_model_nodes=2))


@pytest.mark.parametrize(
    "spec",
    [
        lambda: ModelLabelReadSpec(include_silent=1),
        lambda: ModelLabelReadSpec(max_depth=49),
        lambda: ModelLabelReadSpec(max_model_nodes=True),
        lambda: ModelLabelRenameSpec(replacements=[("id", "A")]),
        lambda: ModelLabelRenameSpec(replacements=(("id",),)),
        lambda: ModelLabelRenameSpec(replacements=(("", "A"),)),
    ],
)
def test_invalid_specs_fail_explicitly(spec):
    with pytest.raises((TypeError, ValueError)):
        spec()


@pytest.mark.parametrize(
    "factory",
    [
        chain,
        ocpn,
        bpmn,
        lambda: ProcessTree("activity", "A"),
        lambda: POWLNode("activity", "A"),
    ],
)
def test_results_round_trip_with_exact_model_type_occurrences_and_provenance(factory):
    from pix.results import result_from_json, result_json_bytes

    model = factory()
    artifact = ModelArtifact(model, "discovered", "discovery:fixture")
    inspection = activity_labels(artifact)
    occurrence = next(row for row in inspection.value.occurrences if not row.silent)
    renamed = rename(artifact, (occurrence.occurrence_id, "검사 / Inspect <v2>"))
    for result in (inspection, renamed):
        decoded = result_from_json(result_json_bytes(result))
        assert decoded == result
        assert decoded.parent_computation_ids == ("discovery:fixture",)
    assert type(result_from_json(result_json_bytes(renamed)).value.model) is type(model)
