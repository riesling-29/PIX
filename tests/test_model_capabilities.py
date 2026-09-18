"""Declared operation boundaries agree with callable APIs and counterexamples."""

from dataclasses import FrozenInstanceError, replace
from importlib import import_module

import pytest

from pix.case_centric.discovery import StateEdge, StateNode, TransitionSystem
from pix.case_centric.extended_nets import InhibitorArc, ResetInhibitorNet
from pix.case_centric.model_analysis import reachability
from pix.compute.model_semantics import is_enabled
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.model_capabilities import list_model_capabilities, model_capabilities
from pix.models import _MODELS, ModelArtifact


def resolve(path):
    module, name = path.rsplit(".", 1)
    return getattr(import_module(module), name)


def test_registry_has_explicit_unique_contract_for_each_registered_model():
    rows = list_model_capabilities()
    assert len(rows) == len({row.python_type for row in rows}) == 16
    assert len({row.model_kind for row in rows}) == 16
    for model_type, (kind, profile) in _MODELS.items():
        capability = model_capabilities(model_type)
        assert capability.model_kind == kind
        assert capability.semantic_profile == profile
        assert capability.persistence.support == "direct"


@pytest.mark.parametrize(
    "row", list_model_capabilities(), ids=lambda row: row.model_kind
)
def test_all_advertised_import_paths_are_real_functions(row):
    assert model_capabilities(resolve(row.python_type)) is row
    paths = list(row.analysis_entrypoints)
    for name in (
        "persistence",
        "activity_labels",
        "firing",
        "conversion",
        "alignment",
        "reachability",
    ):
        operation = getattr(row, name)
        if operation.support == "unsupported":
            assert not operation.entrypoints
            assert not operation.conversion_entrypoints
            assert operation.limitations
        else:
            assert operation.entrypoints
        if operation.support == "via_conversion":
            assert operation.conversion_entrypoints
        paths.extend(operation.entrypoints)
        paths.extend(operation.conversion_entrypoints)
    assert all(callable(resolve(path)) for path in paths)


def test_tree_direct_alignment_differs_from_petri_net_conversion_for_firing():
    row = model_capabilities(ProcessTree)
    assert row.alignment.support == "direct"
    assert row.firing.support == row.reachability.support == "via_conversion"
    assert row.firing.conversion_entrypoints == (
        "pix.compute.discovery.process_tree_to_petri_net",
    )


def test_transition_system_conversion_advertises_only_validated_full_prefix_tries():
    trie = TransitionSystem(
        (StateNode("root", (), 1, 1, 0), StateNode("a", ("A",), 1, 0, 1)),
        (StateEdge("root", "a", "A", 1),),
        1,
        True,
    )
    capability = model_capabilities(trie).conversion
    assert capability.support == "direct"
    assert capability.entrypoints == (
        "pix.case_centric.trie_conversion.trie_to_petri_net",
    )
    assert "full-prefix" in " ".join(capability.limitations)
    converter = resolve(capability.entrypoints[0])
    assert converter(trie).status is ComputeStatus.COMPUTED
    windowed = replace(
        trie, states=(trie.states[0], replace(trie.states[1], context=()))
    )
    assert converter(windowed).status in (
        ComputeStatus.INVALID_INPUT,
        ComputeStatus.UNAVAILABLE,
    )


@pytest.mark.parametrize(
    "kind", ["heuristics-net", "powl", "bpmn-control-flow", "object-centric-causal-net"]
)
def test_conversion_required_for_non_native_alignment_is_explicit(kind):
    row = next(row for row in list_model_capabilities() if row.model_kind == kind)
    assert row.alignment.support == "via_conversion"
    assert row.alignment.conversion_entrypoints
    assert row.alignment.limitations


@pytest.mark.parametrize(
    "kind",
    [
        "footprint-model",
        "transition-system",
        "declare-model",
        "log-skeleton",
        "temporal-profile",
        "stochastic-arc-weight-net",
    ],
)
def test_persisted_observational_or_declarative_models_are_not_generic_executable_nets(
    kind,
):
    row = next(row for row in list_model_capabilities() if row.model_kind == kind)
    assert row.persistence.support == "direct"
    assert (
        row.firing.support
        == row.alignment.support
        == row.reachability.support
        == "unsupported"
    )


def test_reset_inhibitor_counterexample_prevents_ordinary_reachability_claim():
    from pix.case_centric.extended_nets import reset_inhibitor_is_enabled

    base = PetriNet(
        (Place("i"), Place("blocked"), Place("o")),
        (Transition("t", "A"),),
        (Arc("i", "t"), Arc("t", "o")),
        Marking((("i", 1), ("blocked", 1))),
        Marking((("o", 1),)),
    )
    extended = ResetInhibitorNet(base, inhibitor_arcs=(InhibitorArc("blocked", "t"),))
    assert is_enabled(base, base.initial_marking, "t")
    assert not reset_inhibitor_is_enabled(extended, base.initial_marking, "t")
    row = model_capabilities(extended)
    assert row.firing.support == "direct"
    assert row.reachability.support == row.alignment.support == "unsupported"
    with pytest.raises(TypeError, match="PetriNet"):
        reachability(extended)


@pytest.mark.parametrize("kind", ["data-petri-net", "stochastic-petri-net"])
def test_extended_firing_does_not_imply_semantics_preserving_base_alignment(kind):
    row = next(row for row in list_model_capabilities() if row.model_kind == kind)
    assert row.persistence.support == row.firing.support == "direct"
    assert row.alignment.support == row.reachability.support == "unsupported"


def test_exact_type_or_artifact_lookup_and_immutable_results():
    tree = ProcessTree("activity", "A")
    assert model_capabilities(tree) == model_capabilities(ProcessTree)
    assert model_capabilities(ModelArtifact(tree)) == model_capabilities(tree)
    with pytest.raises(FrozenInstanceError):
        model_capabilities(tree).semantic_profile = "invented"
    with pytest.raises(TypeError):
        model_capabilities("ProcessTree")

    class ExternalTree(ProcessTree):
        pass

    with pytest.raises(TypeError):
        model_capabilities(ExternalTree("activity", "A"))
