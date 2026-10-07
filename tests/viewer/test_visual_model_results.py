"""Actual native discovery/conversion outputs retain their model and evidence."""

import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pix.case_centric.alpha import discover_alpha
from pix.case_centric.bpmn_conversion import bpmn_to_petri_net
from pix.case_centric.decision_mining import (
    DecisionTableSpec,
    extract_decision_table,
    mine_data_petri_net,
)
from pix.case_centric.dfg_conversion import DFGConversionSpec, dfg_to_petri_net
from pix.case_centric.discovery import (
    LocalProcessModelSpec,
    discover_dfg,
    discover_local_process_models,
)
from pix.case_centric.extended_discovery import discover_regions
from pix.case_centric.genetic_miner import GeneticMinerSpec, discover_genetic
from pix.case_centric.heuristics import discover_heuristics
from pix.case_centric.heuristics_conversion import heuristics_to_petri_net
from pix.case_centric.marking_equation import (
    ProductMoveCosts,
    SynchronousProductSpec,
    synchronous_product,
)
from pix.case_centric.model_analysis import decompose_model, reduce_model
from pix.case_centric.model_conversion import tree_to_bpmn, tree_to_powl
from pix.case_centric.powl import discover_powl
from pix.case_centric.split_miner import SplitMinerSpec, discover_split_miner
from pix.case_centric.tree_reduction import (
    fold_process_tree,
    reduce_process_tree_for_trace,
)
from pix.case_centric.wfnet_conversion import WfNetConversionSpec, wfnet_to_process_tree
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.ocpn_discovery import discover_ocpn
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.object_centric.conformance import ObjectReplaySpec
from pix.object_centric.model_integration import (
    EnhancedOCPNSpec,
    decompose_ocpn,
    enhance_ocpn,
)
from pix.object_centric.models import (
    causal_net_to_ocpn,
    ocpn_to_causal_net,
    project_ocpn,
    reduce_ocpn,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.results import result_from_json, result_json_bytes
from pix.viewer.visual_contracts import GraphPanel, VisualizationDocument
from pix.viewer.visual_model_results import model_result_view
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization


def _log():
    return CaseLog(
        (
            CaseTrace(
                "c",
                (
                    CaseEvent("e1", (CaseAttribute("concept:name", "string", "A"),)),
                    CaseEvent("e2", (CaseAttribute("concept:name", "string", "B"),)),
                ),
            ),
        )
    )


def _ocel():
    return OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("item"),),
        events=(Event("e", "A", datetime(2026, 1, 1, tzinfo=timezone.utc)),),
        objects=(Object("x", "item"),),
        e2o=(E2O("e", "x", "flow"),),
    )


@pytest.fixture(scope="module")
def discoveries():
    log = _log()
    results = {
        "split": discover_split_miner(log),
        "ocpn": discover_ocpn(
            _ocel(), OCPNDiscoverySpec(("item",), "observed_range", "unique_activity")
        ),
        "alpha": discover_alpha(log),
        "powl": discover_powl(log),
        "region": discover_regions(log),
        "genetic": discover_genetic(
            log, GeneticMinerSpec(population_size=4, elite_count=1, generations=1)
        ),
    }
    for result in results.values():
        assert result.value is not None, result.issues
    return results


@pytest.mark.parametrize(
    "name", ("split", "ocpn", "alpha", "powl", "region", "genetic")
)
def test_real_discovery_wrappers_and_visual_json_roundtrip(discoveries, name):
    result = discoveries[name]
    primary, panels = model_result_view(result.value)
    assert primary == result.value.model
    assert any(isinstance(p, GraphPanel) for p in panels)
    doc = VisualizationDocument(name, panels)
    assert loads_visualization(dumps_visualization(doc)) == doc
    restored = result_from_json(result_json_bytes(result))
    assert model_result_view(restored.value) == (primary, panels)


def test_ocpn_binding_order_and_joint_cardinality_qualification(discoveries):
    value = discoveries["ocpn"].value
    _, panels = model_result_view(value)
    by_id = {p.id: p for p in panels}
    witness = by_id["fitting_witness"]
    assert len(witness.rows) == len(value.fitting_witness)
    for row, step in zip(witness.rows, value.fitting_witness):
        assert row[1] == step.event_id and row[2] == step.binding.transition_id
        assert json.loads(row[3]) == [
            [kind, list(ids)] for kind, ids in step.binding.objects
        ]
    assert (
        dict(by_id["result_summary"].rows)["joint_cardinality_guarantee"]
        == "marginals_only"
    )


def test_split_no_model_reports_unavailability_without_fake_graph(discoveries):
    original = discoveries["split"].value
    value = replace(original, model=None, unresolved_gateway_nodes=("unresolved",))
    model, panels = model_result_view(value)
    assert model is None
    assert not any(isinstance(p, GraphPanel) for p in panels)
    assert panels[0].id == "model_availability"
    assert panels[0].rows[0][0] is False
    assert dict(panels[1].rows)["unresolved_gateway_nodes"] == '["unresolved"]'


@pytest.mark.parametrize("value", (None, {}, "model", SplitMinerSpec()))
def test_unrelated_objects_and_input_specs_are_unsupported(value):
    assert model_result_view(value) is None


def test_compute_envelope_unwrapping_remains_root_responsibility(discoveries):
    assert model_result_view(discoveries["split"]) is None


@pytest.fixture(scope="module")
def conversions(discoveries):
    log = _log()
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    net = process_tree_to_petri_net(tree)
    ocpn = discoveries["ocpn"].value.model
    causal = ocpn_to_causal_net(ocpn)
    assert causal.value.causal_net is not None
    decomposition = decompose_ocpn(ocpn)
    result = {
        "heuristics": heuristics_to_petri_net(discover_heuristics(log)),
        "bpmn": bpmn_to_petri_net(discoveries["split"].value.model),
        "dfg_invisibles": dfg_to_petri_net(discover_dfg(log)),
        "dfg_places": dfg_to_petri_net(
            discover_dfg(log), DFGConversionSpec(variant="activity_defines_place")
        ),
        "tree_powl": tree_to_powl(tree),
        "tree_bpmn": tree_to_bpmn(tree),
        "tree_fold": fold_process_tree(tree),
        "trace_tree_reduction": reduce_process_tree_for_trace(tree, ("A",)),
        "wfnet": wfnet_to_process_tree(net),
        "pn_reduction": reduce_model(net),
        "pn_decomposition": decompose_model(net),
        "oc_projection": project_ocpn(ocpn),
        "oc_reduction": reduce_ocpn(ocpn),
        "to_causal": causal,
        "to_ocpn": causal_net_to_ocpn(causal.value.causal_net),
        "oc_decomposition": decomposition,
        "enhanced": enhance_ocpn(
            _ocel(), ocpn, EnhancedOCPNSpec(ObjectReplaySpec(("item",)))
        ),
        "data_petri": mine_data_petri_net(
            extract_decision_table(log, net, DecisionTableSpec(())), net
        ),
    }
    for row in result.values():
        assert row.value is not None, row.issues
    return result


CONVERSIONS = (
    "heuristics",
    "bpmn",
    "dfg_invisibles",
    "dfg_places",
    "tree_powl",
    "tree_bpmn",
    "tree_fold",
    "trace_tree_reduction",
    "wfnet",
    "pn_reduction",
    "pn_decomposition",
    "oc_projection",
    "oc_reduction",
    "to_causal",
    "to_ocpn",
    "oc_decomposition",
    "enhanced",
    "data_petri",
)


@pytest.mark.parametrize("name", CONVERSIONS)
def test_actual_conversion_results_have_roundtrippable_model_and_evidence(
    conversions, name
):
    result = conversions[name]
    view = model_result_view(result.value)
    assert view is not None
    primary, panels = view
    assert panels
    assert any(isinstance(p, GraphPanel) for p in panels)
    doc = VisualizationDocument(name, panels)
    assert loads_visualization(dumps_visualization(doc)) == doc
    restored = result_from_json(result_json_bytes(result))
    assert model_result_view(restored.value) == view


def _panels(value):
    return {p.id: p for p in model_result_view(value)[1]}


def test_bpmn_and_dfg_model_occurrence_ledgers_preserved(conversions):
    bpmn = conversions["bpmn"].value
    assert _panels(bpmn)["conversion_flow_places"].rows == tuple(
        (r.flow_id, r.place_id) for r in bpmn.flow_places
    )
    dfg = conversions["dfg_places"].value
    mapping = _panels(dfg)["conversion_activity_transitions"].rows
    assert (
        tuple((a, tuple(json.loads(ids))) for a, ids in mapping)
        == dfg.activity_transitions
    )
    assert _panels(dfg)["conversion_routes"].rows == tuple(
        (r.source, r.target, r.transition_id) for r in dfg.routes
    )


def test_workflow_certificate_unknown_not_rendered_as_equivalence():
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    net = process_tree_to_petri_net(tree)
    result = wfnet_to_process_tree(net, WfNetConversionSpec(max_states=1))
    value = result.value
    assert value is not None and value.model is None
    primary, panels = model_result_view(value)
    assert primary is None and not any(isinstance(p, GraphPanel) for p in panels)
    assert _panels(value)["model_availability"].rows[0][0] is False
    certificate = _panels(value)["language_certificate"]
    if value.certificate is not None:
        assert (
            dict(certificate.rows)["equivalent"]
            is value.certificate.comparison.equivalent
        )


def test_object_conversion_refusal_has_reasons_and_no_model_graph():
    from pix.contracts.models import (
        ObjectArc,
        ObjectCentricPetriNet,
        ObjectMarking,
        ObjectToken,
        TypedPlace,
    )

    net = ObjectCentricPetriNet(
        (TypedPlace("p", "item"), TypedPlace("q", "item")),
        (Transition("a", "A"), Transition("b", "B")),
        (
            ObjectArc("p", "a"),
            ObjectArc("a", "q"),
            ObjectArc("p", "b"),
            ObjectArc("b", "q"),
        ),
        ObjectMarking((ObjectToken("p", "x"),)),
        ObjectMarking((ObjectToken("q", "x"),)),
        (("x", "item"),),
    )
    value = ocpn_to_causal_net(net).value
    assert value.causal_net is None and value.refusal_reasons
    model, panels = model_result_view(value)
    assert model is None and not any(isinstance(p, GraphPanel) for p in panels)
    assert json.loads(
        dict(_panels(value)["result_summary"].rows)["refusal_reasons"]
    ) == list(value.refusal_reasons)


def test_multiple_component_models_do_not_get_merged_or_fake_primary():
    net = PetriNet(
        (Place("p"), Place("q"), Place("idle")),
        (Transition("t", "A"),),
        (Arc("p", "t"), Arc("t", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    value = decompose_model(net).value
    model, panels = model_result_view(value)
    assert model is None
    graphs = [p for p in panels if isinstance(p, GraphPanel)]
    assert len(graphs) == len(value.components) == 2
    assert len({p.id for p in panels}) == len(panels)
    assert {n.id for p in graphs for n in p.nodes} == {"p", "q", "idle", "t"}
    assert not any(p.id == "model_availability" for p in panels)


def test_oc_type_projection_has_concrete_tokens_and_cardinality_ledger(conversions):
    value = conversions["oc_decomposition"].value.per_type[0]
    primary, panels = model_result_view(value)
    assert primary == value.petri_net
    assert _panels(value)["concrete_markings"].rows == tuple(
        (kind, token.place_id, token.object_id)
        for kind, marking in (
            ("initial", value.concrete_initial_marking),
            ("final", value.concrete_final_marking),
        )
        for token in marking.tokens
    )
    assert _panels(value)["arc_cardinalities"].rows == tuple(
        (a.source, a.target, a.variable, a.min_objects, a.max_objects)
        for a in value.arc_cardinalities
    )
    assert (
        loads_visualization(
            dumps_visualization(VisualizationDocument("type", panels))
        ).panels
        == panels
    )


def test_powl_discovery_renders_original_occurrences_and_converted_net_separately(
    discoveries,
):
    value = discoveries["powl"].value
    primary, panels = model_result_view(value)
    assert primary == value.model
    assert "model" in {p.id for p in panels}
    assert "powl_accepting_net:model" in {p.id for p in panels}


def test_result_with_invalid_embedded_net_is_rejected(discoveries):
    original = discoveries["alpha"].value
    # Construct a fresh copy so the shared fixture cannot be corrupted.
    model = replace(original.model)
    object.__setattr__(model, "arcs", (Arc("missing", model.transitions[0].id),))
    with pytest.raises(ValueError):
        model_result_view(replace(original, model=model))


def test_synchronous_product_preserves_move_kind_occurrence_and_rational_cost():
    net = PetriNet(
        (Place("p"), Place("q")),
        (Transition("t", "A"),),
        (Arc("p", "t"), Arc("t", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    result = synchronous_product(
        net,
        SynchronousProductSpec(("A", "A"), ProductMoveCosts(log=(1, 3), model=(2, 3))),
    )
    value = result.value
    primary, panels = model_result_view(value)
    assert primary == value.model
    rows = _panels(value)["conversion_transitions"].rows
    assert {row[1] for row in rows} == {"log", "model", "synchronous"}
    assert {row[2] for row in rows if row[1] == "synchronous"} == {0, 1}
    for row, original in zip(rows, value.transitions):
        assert tuple(json.loads(row[4])) == original.cost
    assert (
        loads_visualization(
            dumps_visualization(VisualizationDocument("product", panels))
        ).panels
        == panels
    )
    assert model_result_view(result_from_json(result_json_bytes(result)).value) == (
        primary,
        panels,
    )


def test_local_models_keep_bounded_metrics_and_exact_occurrence_witnesses():
    result = discover_local_process_models(
        _log(), LocalProcessModelSpec(max_leaves=2, max_candidates=30, maximum_models=4)
    )
    value = result.value
    assert value.models
    primary, panels = model_result_view(value)
    assert primary is None
    graphs = [p for p in panels if isinstance(p, GraphPanel)]
    assert len(graphs) == len(value.models)
    for index, local in enumerate(value.models):
        graph_model, own_panels = model_result_view(local)
        assert graph_model == local.tree
        own = {p.id: p for p in own_panels}
        assert (
            dict(own["result_summary"].rows)["language_is_complete"]
            is local.language_is_complete
        )
        assert tuple(
            (case, tuple(json.loads(events)), tuple(json.loads(acts)))
            for case, events, acts in own["local_occurrences"].rows
        ) == tuple((r.case_id, r.event_ids, r.activities) for r in local.occurrences)
        assert any(p.id == f"local_{index}:model" for p in panels)
    assert (
        loads_visualization(
            dumps_visualization(VisualizationDocument("local", panels))
        ).panels
        == panels
    )


def test_empty_local_discovery_does_not_claim_no_behavior():
    result = discover_local_process_models(
        _log(), LocalProcessModelSpec(minimum_frequency=10, max_leaves=1)
    )
    assert result.value.models == ()
    _, panels = model_result_view(result.value)
    assert not any(isinstance(p, GraphPanel) for p in panels)
    assert "not proof" in next(p.description for p in panels if p.id == "local_models")
