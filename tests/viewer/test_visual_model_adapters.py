"""Hand-expected model semantics survive native visualization adaptation."""

import json
from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

from pix.case_centric.advanced import (
    DecisionGuard,
    DecisionNode,
    DecisionTree,
    GuardCondition,
)
from pix.case_centric.decision_mining import (
    DataGuardClause,
    DataPetriNet,
    DecisionFeatureSpec,
    DecisionPointModel,
    TransitionDataGuard,
)
from pix.case_centric.declarative import (
    ActivityFrequency,
    DeclareConstraint,
    DeclareModel,
    LogSkeleton,
    SkeletonRelation,
    TemporalProfile,
    TemporalProfileEntry,
    TemporalProfileSpec,
)
from pix.case_centric.discovery import discover_footprints, discover_transition_system
from pix.case_centric.heuristics import discover_heuristics
from pix.case_centric.model_discovery import (
    ModelFootprintSpec,
    discover_model_footprints,
)
from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import discover_split_miner
from pix.contracts.discovery import ProcessTree
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
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.models import ModelArtifact, model_from_json, model_json_bytes
from pix.object_centric.discovery import SAWDiscoverySpec, discover_saw_net
from pix.object_centric.models import (
    CausalChannel,
    CausalMarker,
    CausalMarkerGroup,
    ObjectCentricCausalNet,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer.visual_contracts import GraphPanel, MatrixPanel, VisualizationDocument
from pix.viewer.visual_model_adapters import model_panels
from pix.viewer.visual_serialization import dumps_visualization, loads_visualization


def _log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(f"{i}_{j}", (CaseAttribute("concept:name", "string", a),))
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def _pn():
    return PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "same"), Transition("b", "same"), Transition("silent")),
        (
            Arc("p", "a", 2),
            Arc("a", "q", 2),
            Arc("p", "b", 2),
            Arc("b", "q", 2),
            Arc("q", "silent"),
            Arc("silent", "q"),
        ),
        Marking((("p", 2),)),
        Marking((("q", 2),)),
    )


def _ocpn():
    return ObjectCentricPetriNet(
        (TypedPlace("p", "item"), TypedPlace("q", "item")),
        (Transition("a", "A"),),
        (ObjectArc("p", "a", True, 0, None), ObjectArc("a", "q", True, 0, None)),
        ObjectMarking((ObjectToken("p", "x"), ObjectToken("p", "x"))),
        ObjectMarking((ObjectToken("q", "x"), ObjectToken("q", "x"))),
        (("x", "item"), ("idle", "item")),
    )


def _causal():
    # A binding ID deliberately equals a transition ID. The model permits it;
    # the visualization must namespace these identities instead of merging.
    return ObjectCentricCausalNet(
        (Transition("t", "A"),),
        (
            CausalChannel("left", "item", None, "t"),
            CausalChannel("right", "item", None, "t"),
            CausalChannel("sink", "item", "t", None),
        ),
        (
            CausalMarkerGroup(
                "t",
                "t",
                (CausalMarker("left"), CausalMarker("right")),
                equal_channels=(("left", "right"),),
            ),
            CausalMarkerGroup(
                "alternative",
                "t",
                (CausalMarker("left", 0, 2), CausalMarker("right", 0, 2)),
                disjoint_channels=(("left", "right"),),
            ),
        ),
        (CausalMarkerGroup("out", "t", (CausalMarker("sink"),)),),
        ObjectMarking((ObjectToken("left", "x"), ObjectToken("right", "x"))),
        ObjectMarking((ObjectToken("sink", "x"),)),
        (("x", "item"),),
    )


def _dpn():
    base = PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("p", "a"), Arc("a", "q"), Arc("p", "b"), Arc("b", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    limit = 2**80
    conditions = (
        GuardCondition(0, "amount", "<=", limit),
        GuardCondition(0, "amount", ">", limit),
    )
    tree = DecisionTree(
        ("amount",),
        ("c1", "c2"),
        "training:fixture",
        (
            DecisionNode(0, 2, (("a", 1), ("b", 1)), "a", 0, limit, 1, 2, None),
            DecisionNode(1, 1, (("a", 1),), "a", None, None, None, None, "pure"),
            DecisionNode(2, 1, (("b", 1),), "b", None, None, None, None, "pure"),
        ),
        (
            DecisionGuard((conditions[0],), "a", 1, 1),
            DecisionGuard((conditions[1],), "b", 1, 1),
        ),
        2,
        2,
        1,
        "fitted",
    )
    guards = tuple(
        TransitionDataGuard(tid, (DataGuardClause((condition,)),), 1)
        for tid, condition in zip(("a", "b"), conditions)
    )
    return DataPetriNet(
        base,
        (DecisionFeatureSpec("amount", "amount"),),
        (
            DecisionPointModel(
                "p", ("a", "b"), ("r1", "r2"), ("c1", "c2"), tree, guards, "fitted"
            ),
        ),
    )


@pytest.fixture(scope="module")
def models():
    log = _log(("A", "B"), ("A", "C"), ("A", "B"))
    ocel = OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("item"),),
        events=(Event("e", "A", datetime(2026, 1, 1, tzinfo=timezone.utc)),),
        objects=(Object("x", "item"),),
        e2o=(E2O("e", "x", "flow"),),
    )
    saw = discover_saw_net(
        ocel,
        SAWDiscoverySpec(
            OCPNDiscoverySpec(("item",), "observed_range", "unique_activity")
        ),
    )
    assert saw.value is not None, saw.issues
    return {
        "petri_net": _pn(),
        "ocpn": _ocpn(),
        "process_tree": ProcessTree(
            "sequence",
            children=(ProcessTree("activity", "A"), ProcessTree("activity", "A")),
        ),
        "powl": POWLNode(
            "partial_order",
            children=(
                POWLNode("activity", "A"),
                POWLNode("activity", "A"),
                POWLNode("activity", "C"),
            ),
            order=((0, 2),),
        ),
        "bpmn": discover_split_miner(log).value.model,
        "heuristics": discover_heuristics(log).value,
        "transition_system": discover_transition_system(log).value,
        "footprints": discover_footprints(log).value,
        "declare": DeclareModel(
            ("A", "B", "idle"),
            (
                DeclareConstraint("response", "A", "B"),
                DeclareConstraint("absence", "B", cardinality=2),
            ),
        ),
        "skeleton": LogSkeleton(
            ("A", "B"),
            (SkeletonRelation("always_before", "A", "B", 1, 2),),
            (ActivityFrequency("A", (0, 1)), ActivityFrequency("B", (1,))),
        ),
        "temporal": TemporalProfile(
            (TemporalProfileEntry("A", "B", 1, 3, None),),
            TemporalProfileSpec(ddof=1),
            1,
            1,
        ),
        "causal": _causal(),
        "saw": saw.value,
        "data_petri": _dpn(),
    }


KINDS = (
    "petri_net",
    "ocpn",
    "process_tree",
    "powl",
    "bpmn",
    "heuristics",
    "transition_system",
    "footprints",
    "declare",
    "skeleton",
    "temporal",
    "causal",
    "saw",
    "data_petri",
)


def _details(item):
    return {field.name: field.value for field in item.details}


def _panel(panels, identifier):
    return next(panel for panel in panels if panel.id == identifier)


@pytest.mark.parametrize("kind", KINDS)
def test_all_native_model_types_have_valid_reproducible_panels(models, kind):
    value = models[kind]
    panels = model_panels(value)
    assert panels
    document = VisualizationDocument(kind, panels)
    assert json.loads(json.dumps(asdict(document), ensure_ascii=False))["panels"]
    assert loads_visualization(dumps_visualization(document)) == document
    restored = model_from_json(model_json_bytes(value)).model
    assert model_panels(restored) == panels
    assert model_panels(value) == panels
    assert model_from_json(model_json_bytes(value)).model == value


def test_pn_occurrence_identity_arc_weights_silent_and_markings(models):
    graph = model_panels(models["petri_net"])[0]
    nodes = {n.id: n for n in graph.nodes}
    assert set(nodes) == {"p", "q", "a", "b", "silent"}
    assert nodes["a"].label == nodes["b"].label == "same"
    assert nodes["silent"].kind == "silent" and nodes["silent"].label == "τ"
    assert _details(nodes["p"])["initial_count"] == 2
    assert _details(nodes["q"])["final_count"] == 2
    assert {(e.source, e.target, _details(e)["weight"]) for e in graph.edges} == {
        ("p", "a", 2),
        ("a", "q", 2),
        ("p", "b", 2),
        ("b", "q", 2),
        ("q", "silent", 1),
        ("silent", "q", 1),
    }


def test_ocpn_object_multiset_idle_universe_type_and_variable_policy(models):
    graph, objects = model_panels(models["ocpn"])
    p = next(n for n in graph.nodes if n.id == "p")
    assert json.loads(_details(p)["initial_tokens"]) == ["x", "x"]
    assert _details(p)["initial_count"] == 2
    assert objects.rows == (("idle", "item"), ("x", "item"))
    for edge in graph.edges:
        assert edge.label == "0..∞"
        assert _details(edge) == {
            "object_type": "item",
            "weight": 1,
            "variable": True,
            "min_objects": 0,
            "max_objects": None,
        }


def test_tree_hierarchy_and_sequence_not_activity_dfg(models):
    graph = model_panels(models["process_tree"])[0]
    assert {(n.id, n.label) for n in graph.nodes} == {
        ("root", "sequence"),
        ("root/0", "A"),
        ("root/1", "A"),
    }
    assert {(e.source, e.target) for e in graph.edges if e.kind == "precedence"} == {
        ("root/0", "root/1")
    }
    assert len([e for e in graph.edges if e.kind == "contains"]) == 2


@pytest.mark.parametrize("powl", (False, True))
def test_loop_do_redo_and_tau_are_explicit(powl):
    cls = POWLNode if powl else ProcessTree
    graph = model_panels(cls("loop", children=(cls("activity", "A"), cls("tau"))))[0]
    assert {(e.target, e.label) for e in graph.edges if e.kind == "contains"} == {
        ("root/0", "do"),
        ("root/1", "redo"),
    }
    assert not [e for e in graph.edges if e.kind == "precedence"]
    assert "do (redo do)*" in graph.description


def test_powl_unordered_children_do_not_acquire_sequence_edges(models):
    graph = model_panels(models["powl"])[0]
    assert {(e.source, e.target) for e in graph.edges if e.kind == "precedence"} == {
        ("root/0", "root/2")
    }
    assert [n.label for n in graph.nodes].count("A") == 2


def test_bpmn_flow_ids_and_gateway_directions(models):
    model = models["bpmn"]
    graph = model_panels(model)[0]
    assert {n.id for n in graph.nodes} == {n.id for n in model.nodes}
    assert {(e.id, e.source, e.target) for e in graph.edges} == {
        (e.id, e.source, e.target) for e in model.flows
    }
    kinds = {n.kind for n in graph.nodes}
    assert {"start_event", "end_event", "task", "exclusive_gateway"} <= kinds
    for node in graph.nodes:
        original = next(n for n in model.nodes if n.id == node.id)
        assert _details(node)["gateway_direction"] == original.direction


def test_heuristics_bindings_keep_and_alternatives_and_evidence(models):
    model = models["heuristics"]
    panels = model_panels(model)
    graph = panels[0]
    groups = [n for n in graph.nodes if n.kind == "binding"]
    assert len(groups) == sum(len(b.alternatives) for b in model.bindings)
    for binding in model.bindings:
        for index, alternative in enumerate(binding.alternatives):
            matching = [
                n
                for n in groups
                if _details(n)["activity"] == binding.activity
                and _details(n)["direction"] == binding.direction
                and _details(n)["alternative_index"] == index
            ]
            assert len(matching) == 1
            assert json.loads(_details(matching[0])["members"]) == list(alternative)
    assert len(_panel(panels, "dependencies").rows) == len(model.dependencies)


def test_state_graph_retains_context_visits_and_edge_activities(models):
    model = models["transition_system"]
    graph = model_panels(model)[0]
    assert {n.id for n in graph.nodes} == {s.id for s in model.states}
    for node in graph.nodes:
        state = next(s for s in model.states if s.id == node.id)
        assert _details(node)["visits"] == state.visits
        assert json.loads(_details(node)["context"]) == list(state.context)
    assert {
        (e.source, e.target, e.label, _details(e)["occurrence_count"])
        for e in graph.edges
    } == {
        (e.source, e.target, e.activity, e.occurrence_count) for e in model.transitions
    }


def test_footprints_distinguish_observed_parallel_from_concurrency():
    model = discover_footprints(_log(("A", "B", "A"), ("C",))).value
    matrix = model_panels(model)[0]
    assert isinstance(matrix, MatrixPanel)
    cells = {(c.row, c.column): c.value for c in matrix.cells}
    assert cells["A", "B"] == cells["B", "A"] == "||"
    assert cells["A", "C"] == "#"
    assert (
        "not proven concurrency" in dict((v.name, v.value) for v in matrix.legend)["||"]
    )


def test_declare_rules_keep_direction_cardinality_and_missing_evidence(models):
    panels = model_panels(models["declare"])
    rules = panels[0]
    assert rules.rows[0] == ("response", "A", "B", 1, None, None, None, None, None)
    assert rules.rows[1][:4] == ("absence", "B", None, 2)
    assert ("idle",) in panels[1].rows
    assert not any(isinstance(p, GraphPanel) for p in panels)


def test_skeleton_frequency_zero_and_activation_denominator(models):
    relation, frequencies = model_panels(models["skeleton"])
    assert relation.rows == (("always_before", "A", "B", 1, 2),)
    assert json.loads(frequencies.rows[0][1]) == [0, 1]


def test_temporal_null_deviation_units_and_population(models):
    temporal, policy = model_panels(models["temporal"])
    assert temporal.rows == (("A", "B", 1, 3.0, None),)
    assert dict(policy.rows)["ddof"] == 1
    assert dict(policy.rows)["time_unit"] == "seconds"
    assert "observed pairs: 1" in temporal.description


def test_causal_binding_identity_collision_and_object_constraints(models):
    panels = model_panels(models["causal"])
    graph = panels[0]
    matching = [n for n in graph.nodes if _details(n).get("model_id") == "t"]
    assert len(matching) == 2 and len({n.id for n in matching}) == 2
    assert {n.kind for n in matching} == {"transition", "binding"}
    groups = {row[1]: row for row in panels[1].rows}
    assert json.loads(groups["t"][4]) == [["left", "right"]]
    assert json.loads(groups["alternative"][5]) == [["left", "right"]]
    assert len([e for e in graph.edges if e.kind == "marker"]) == 5
    left = next(n for n in graph.nodes if _details(n).get("model_id") == "left")
    assert _details(left)["external_source"] is True


def test_saw_histograms_denominators_and_correlated_witnesses(models):
    model = models["saw"]
    panels = model_panels(model)
    distribution = _panel(panels, "saw_distributions")
    assert len(distribution.rows) == len(model.arc_distributions)
    for row, original in zip(distribution.rows, model.arc_distributions):
        assert json.loads(row[5]) == [list(item) for item in original.histogram]
        assert row[6] == original.sample_count
        assert json.loads(row[7]) == list(original.witness_indices)
    assert len(_panel(panels, "saw_witness").rows) == len(
        model.discovery.fitting_witness
    )
    assert (
        dict(_panel(panels, "saw_policy").rows)["joint_probability_policy"]
        == "not_inferred"
    )


def test_data_guards_preserve_large_integer_thresholds_and_training_ids(models):
    panels = model_panels(models["data_petri"])
    guards = _panel(panels, "guards")
    assert guards.rows[0][:4] == ("p", "a", "fitted", 1)
    condition = json.loads(guards.rows[0][4])[0][0]
    assert condition["threshold"] == 2**80
    assert type(condition["threshold"]) is int
    assert str(2**80) in guards.rows[0][5]
    evidence = _panel(panels, "decision_evidence")
    assert json.loads(evidence.rows[0][2]) == ["r1", "r2"]


def test_untrained_data_guard_is_unknown(models):
    model = models["data_petri"]
    point = DecisionPointModel("p", ("a", "b"), (), (), None, (), "untrained")
    result = model_panels(replace(model, decisions=(point,)))
    assert _panel(result, "guards").rows == (
        ("p", None, "untrained", None, None, "unknown"),
    )


def test_empty_data_guard_conjunction_and_disjunction_are_not_confused(models):
    model = models["data_petri"]
    point = replace(
        model.decisions[0],
        guards=(
            TransitionDataGuard("a", (DataGuardClause(()),), 1),
            TransitionDataGuard("b", (), 1),
        ),
    )
    result = model_panels(replace(model, decisions=(point,)))
    rows = _panel(result, "guards").rows
    assert json.loads(rows[0][4]) == [[]] and rows[0][5] == "(true)"
    assert json.loads(rows[1][4]) == [] and rows[1][5] == "false"


def test_causal_empty_binding_alternatives_are_retained():
    value = ObjectCentricCausalNet(
        (Transition("t"),),
        (),
        (CausalMarkerGroup("in", "t", ()),),
        (CausalMarkerGroup("out", "t", ()),),
        ObjectMarking(),
        ObjectMarking(),
        (),
    )
    graph = model_panels(value)[0]
    bindings = [n for n in graph.nodes if n.kind == "binding"]
    assert len(bindings) == 2
    assert all(_details(n)["empty"] for n in bindings)
    assert len(graph.edges) == 2


@pytest.mark.parametrize(
    "family",
    (
        "footprints",
        "transition_system",
        "heuristics",
        "temporal",
        "declare",
        "skeleton",
        "pn",
    ),
)
def test_empty_models_remain_empty_without_fabricated_activity(family):
    empty = _log()
    values = {
        "footprints": lambda: discover_footprints(empty).value,
        "transition_system": lambda: discover_transition_system(empty).value,
        "heuristics": lambda: discover_heuristics(empty).value,
        "temporal": lambda: TemporalProfile((), TemporalProfileSpec(), 0, 0),
        "declare": lambda: DeclareModel((), ()),
        "skeleton": lambda: LogSkeleton((), (), ()),
        "pn": lambda: PetriNet((), (), (), Marking(), Marking()),
    }
    panels = model_panels(values[family]())
    document = VisualizationDocument(family, panels)
    assert loads_visualization(dumps_visualization(document)) == document
    for panel in panels:
        if isinstance(panel, GraphPanel):
            assert not panel.nodes and not panel.edges
        if isinstance(panel, MatrixPanel):
            assert not panel.rows and not panel.columns and not panel.cells


def test_incomplete_model_footprints_never_render_missing_as_negative():
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    partial = discover_model_footprints(tree, ModelFootprintSpec(max_states=1)).value
    assert (
        not partial.complete and partial.sequence is None and partial.unrelated is None
    )
    panels = model_panels(partial)
    matrix = panels[0]
    assert {c.value for c in matrix.cells} <= {"?", "follows", "self", "||"}
    assert "#" not in {c.value for c in matrix.cells}
    properties = dict(_panel(panels, "model_properties").rows)
    assert properties["sequence"] is None
    assert properties["unrelated"] is None


def test_model_footprints_actual_commuting_witnesses_separate():
    tree = ProcessTree(
        "parallel",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    value = discover_model_footprints(tree).value
    assert value.complete
    panels = model_panels(value)
    assert (
        len(_panel(panels, "commuting_witnesses").rows)
        == len(value.commuting_witnesses)
        > 0
    )
    assert len(_panel(panels, "relation_witnesses").rows) == len(
        value.relation_witnesses
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"sequence": (("A", "B"),)},
        {"parallel": (("A", "B"),)},
        {"behavior": "anything"},
        {"analysis_steps": -1},
        {"minimum_trace_length": -7},
        {"start_activities": ("outside",)},
        {"accepted_language_exists": True},
        {"complete": True},
        {"minimum_length_proven": True},
    ),
)
def test_malformed_model_footprint_claims_are_rejected(changes):
    tree = ProcessTree(
        "sequence",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    value = discover_model_footprints(tree, ModelFootprintSpec(max_states=1)).value
    with pytest.raises(ValueError):
        model_panels(replace(value, **changes))


@pytest.mark.parametrize("behavior", ("reachable", "accepting"))
@pytest.mark.parametrize("analysis_steps", (1, 5, 10, 30, 100, 1000))
@pytest.mark.parametrize("max_states", (1, 2, 100))
def test_real_bounded_footprint_results_preserve_unknowns(
    behavior, analysis_steps, max_states
):
    tree = ProcessTree(
        "parallel",
        children=(ProcessTree("activity", "A"), ProcessTree("activity", "B")),
    )
    value = discover_model_footprints(
        tree,
        ModelFootprintSpec(
            behavior=behavior, max_states=max_states, max_analysis_steps=analysis_steps
        ),
    ).value
    panels = model_panels(value)
    assert (
        loads_visualization(
            dumps_visualization(VisualizationDocument("bounded", panels))
        ).panels
        == panels
    )


@pytest.mark.parametrize("value", (None, {}, "petri_net", 1, object()))
def test_unsupported_inputs_return_none(value):
    assert model_panels(value) is None


def test_artifact_unwrapping_is_root_responsibility(models):
    assert model_panels(ModelArtifact(models["petri_net"])) is None


def test_malformed_supported_legacy_graph_raises(models):
    model = models["footprints"]
    with pytest.raises(ValueError):
        model_panels(replace(model, causal=(("A", "not-declared"),)))
    model = models["transition_system"]
    with pytest.raises(ValueError):
        model_panels(replace(model, trace_count=-1))


def test_malformed_legacy_net_cannot_bypass_constructor_validation():
    net = _pn()
    object.__setattr__(net, "arcs", (Arc("missing", "a"),))
    with pytest.raises(ValueError):
        model_panels(net)


def test_hostile_labels_are_inert_and_do_not_collide():
    labels = ("</script><img src=x onerror=alert(1)>", 'a","b', "a|b", "한글 & < >")
    model = ProcessTree(
        "parallel", children=tuple(ProcessTree("activity", label) for label in labels)
    )
    graph = model_panels(model)[0]
    assert {n.label for n in graph.nodes if n.kind == "activity"} == set(labels)
    assert len({n.id for n in graph.nodes}) == 5
    transported = json.loads(json.dumps(asdict(graph), ensure_ascii=False))
    assert transported["nodes"]
