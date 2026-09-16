"""Typed model artifacts preserve real model semantics and reject bad records."""

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

from pix.case_centric.decision_mining import DataPetriNet, data_petri_net_digest
from pix.case_centric.declarative import (
    ActivityFrequency,
    DeclareConstraint,
    DeclareModel,
    LogSkeleton,
    TemporalProfile,
    TemporalProfileEntry,
    TemporalProfileSpec,
)
from pix.case_centric.discovery import (
    StateEdge,
    StateNode,
    TransitionSystem,
    discover_footprints,
    discover_transition_system,
)
from pix.case_centric.heuristics import discover_heuristics
from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import discover_split_miner
from pix.compute.model_semantics import model_digest
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
from pix.models import (
    MODEL_VERSION,
    ModelArtifact,
    model_document,
    model_from_json,
    model_json_bytes,
    read_model,
    write_model,
)
from pix.object_centric.discovery import SAWDiscoverySpec, discover_saw_net
from pix.object_centric.models import causal_net_digest, ocpn_to_causal_net
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def case_log(*words):
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


def pn():
    return PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "A"),),
        (Arc("p", "a"), Arc("a", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )


def ocpn():
    return ObjectCentricPetriNet(
        (TypedPlace("p", "item"), TypedPlace("q", "item")),
        (Transition("a", "A"),),
        (ObjectArc("p", "a"), ObjectArc("a", "q")),
        ObjectMarking((ObjectToken("p", "x"),)),
        ObjectMarking((ObjectToken("q", "x"),)),
        (("x", "item"),),
    )


@pytest.fixture(scope="module")
def models():
    data = case_log(("A", "B"), ("A", "C"))
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
            OCPNDiscoverySpec(
                ("item",),
                "observed_range",
                "unique_activity",
            )
        ),
    )
    assert saw.value is not None, saw.issues
    return {
        "heuristics-net": discover_heuristics(data).value,
        "footprint-model": discover_footprints(data).value,
        "transition-system": discover_transition_system(data).value,
        "declare-model": DeclareModel(
            ("A", "B"), (DeclareConstraint("response", "A", "B"),)
        ),
        "log-skeleton": LogSkeleton(("A",), (), (ActivityFrequency("A", (1,)),)),
        "temporal-profile": TemporalProfile(
            (TemporalProfileEntry("A", "B", 1, 3, 0),), TemporalProfileSpec(), 1, 1
        ),
        "powl": POWLNode(
            "partial_order",
            children=(POWLNode("activity", "A"), POWLNode("activity", "B")),
        ),
        "bpmn-control-flow": discover_split_miner(data).value.model,
        "object-centric-causal-net": ocpn_to_causal_net(ocpn()).value.causal_net,
        "stochastic-arc-weight-net": saw.value,
        "data-petri-net": DataPetriNet(pn(), (), ()),
    }


KINDS = (
    "heuristics-net",
    "footprint-model",
    "transition-system",
    "declare-model",
    "log-skeleton",
    "temporal-profile",
    "powl",
    "bpmn-control-flow",
    "object-centric-causal-net",
    "stochastic-arc-weight-net",
    "data-petri-net",
)


@pytest.mark.parametrize("kind", KINDS)
def test_real_bare_models_roundtrip_with_explicit_semantic_kind(models, kind):
    model = models[kind]
    document = model_document(
        model, origin="discovered", source_computation_id="pix.computation.example"
    )
    assert document["kind"] == kind
    assert isinstance(document["profile"], str) and document["profile"]
    assert "model" in document and "computation" not in document
    artifact = model_from_json(
        model_json_bytes(
            model, origin="discovered", source_computation_id="pix.computation.example"
        )
    )
    assert type(artifact.model) is type(model)
    assert artifact.model == model
    assert artifact.source_computation_id == "pix.computation.example"
    assert model_document(artifact) == document
    with pytest.raises(FrozenInstanceError):
        artifact.origin = "provided"


@pytest.mark.parametrize("kind", KINDS)
def test_extended_models_atomic_publication_and_no_clobber(models, kind, tmp_path):
    path = tmp_path / (kind + ".json")
    write_model(models[kind], path, origin="provided")
    assert read_model(path) == ModelArtifact(models[kind], "provided")
    with pytest.raises(FileExistsError):
        write_model(models[kind], path)


def test_existing_three_model_versions_and_digests_remain_unchanged():
    assert MODEL_VERSION == "1.0.0"
    for model in (pn(), ocpn()):
        doc = model_document(model)
        assert doc["model_digest"] == model_digest(model)
        assert model_from_json(model_json_bytes(model)).model == model
    tree = ProcessTree("activity", "A")
    body = {
        "kind": "process-tree",
        "schema_version": "1.0.0",
        "semantics_version": "1.0.0",
        "model": {"operator": "activity", "activity": "A", "children": []},
    }
    encoded = json.dumps(
        body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    expected = "pix.model.process-tree.v1:sha256:" + hashlib.sha256(encoded).hexdigest()
    assert model_document(tree)["model_digest"] == expected


def test_existing_causal_digest_is_reused(models):
    model = models["object-centric-causal-net"]
    assert model_document(model)["model_digest"] == causal_net_digest(model)


def test_data_petri_net_digest_is_reused(models):
    model = models["data-petri-net"]
    assert model_document(model)["model_digest"] == data_petri_net_digest(model)


def test_typed_numeric_data_guards_preserve_integer_thresholds_and_unknown():
    from pix.case_centric.advanced import (
        DecisionGuard,
        DecisionNode,
        DecisionTree,
        GuardCondition,
    )
    from pix.case_centric.decision_mining import (
        DataGuardClause,
        DecisionFeatureSpec,
        DecisionFeatureValue,
        DecisionPointModel,
        TransitionDataGuard,
        evaluate_data_guards,
    )

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
        TransitionDataGuard(
            tid, (DataGuardClause((GuardCondition(0, "amount", op, limit),)),), 1
        )
        for tid, op in (("a", "<="), ("b", ">"))
    )
    model = DataPetriNet(
        base,
        (DecisionFeatureSpec("amount", "amount"),),
        (
            DecisionPointModel(
                "p", ("a", "b"), ("r1", "r2"), ("c1", "c2"), tree, guards, "fitted"
            ),
        ),
    )
    restored = model_from_json(model_json_bytes(model)).model
    assert restored.decisions[0].guards[0].clauses[0].conditions[0].threshold == limit
    assert (
        type(restored.decisions[0].guards[0].clauses[0].conditions[0].threshold) is int
    )
    assert (
        evaluate_data_guards(
            restored,
            base.initial_marking,
            "a",
            (DecisionFeatureValue("amount", limit),),
        ).value.guard_state
        == "true"
    )
    assert (
        evaluate_data_guards(
            restored,
            base.initial_marking,
            "b",
            (DecisionFeatureValue("amount", limit),),
        ).value.guard_state
        == "false"
    )
    assert (
        evaluate_data_guards(
            restored, base.initial_marking, "a", (DecisionFeatureValue("amount", None),)
        ).value.guard_state
        == "unknown"
    )


def test_integer_valued_float_fields_are_canonicalized_before_hashing():
    model = discover_heuristics(case_log(("A", "B", "A"))).value
    assert all(d.measure == 0 for d in model.dependencies if d.source != d.target)
    integers = replace(
        model,
        dependencies=tuple(
            replace(d, measure=int(d.measure)) for d in model.dependencies
        ),
    )
    doc = model_document(integers)
    assert all(type(d["measure"]) is float for d in doc["model"]["dependencies"])
    restored = model_from_json(model_json_bytes(integers)).model
    assert all(type(d.measure) is float for d in restored.dependencies)
    assert model_document(restored)["model_digest"] == doc["model_digest"]


def refresh_document(document):
    body = {k: v for k, v in document.items() if k != "document_digest"}
    document["document_digest"] = (
        "pix.model-document.v1:sha256:"
        + hashlib.sha256(
            json.dumps(
                body,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
    )
    return json.dumps(document)


@pytest.mark.parametrize(
    "field,value",
    [("kind", "os.system"), ("profile", "python:any"), ("version", "99.0.0")],
)
def test_arbitrary_type_profile_or_version_never_dispatches(models, field, value):
    doc = copy.deepcopy(model_document(models["powl"]))
    doc[field] = value
    with pytest.raises(ValueError):
        model_from_json(refresh_document(doc))


@pytest.mark.parametrize("kind", KINDS)
def test_extra_or_missing_model_fields_rejected_even_with_rehashed_envelope(
    models, kind
):
    doc = copy.deepcopy(model_document(models[kind]))
    doc["model"]["python_class"] = "arbitrary.module.Type"
    with pytest.raises(ValueError):
        model_from_json(refresh_document(doc))


def test_footprint_algebra_and_known_references_are_checked(models):
    model = models["footprint-model"]
    with pytest.raises(ValueError, match="causal footprint"):
        model_document(replace(model, causal=()))
    with pytest.raises(ValueError, match="known activity"):
        model_document(replace(model, directly_follows=(("unknown", "A"),)))
    doc = copy.deepcopy(model_document(model))
    doc["model"]["parallel"] = [["A", "B"]]
    with pytest.raises(ValueError, match="parallel footprint"):
        model_from_json(refresh_document(doc))


def test_transition_system_population_and_references_are_checked(models):
    model = models["transition-system"]
    with pytest.raises(ValueError, match="existing states"):
        model_document(
            replace(
                model, transitions=(replace(model.transitions[0], source="unknown"),)
            )
        )
    with pytest.raises(ValueError, match="state visits"):
        model_document(
            replace(
                model, states=(replace(model.states[0], visits=999), *model.states[1:])
            )
        )


def test_heuristics_finite_immutable_and_endpoint_checks(models):
    model = models["heuristics-net"]
    with pytest.raises(ValueError, match="retained activity"):
        model_document(replace(model, edges=(("missing", "A"),)))
    with pytest.raises((TypeError, ValueError)):
        model_document(replace(model, activities=list(model.activities)))
    with pytest.raises(ValueError, match="non-finite"):
        model_document(
            replace(
                model,
                dependencies=(replace(model.dependencies[0], measure=float("nan")),),
            )
        )
    with pytest.raises(ValueError):
        model_document(
            replace(model, dependencies=(replace(model.dependencies[0], measure=True),))
        )


def test_payload_wrapper_is_not_a_bare_model():
    with pytest.raises(TypeError, match="explicitly supported"):
        model_document(discover_heuristics(case_log(("A",))))


def test_saw_keeps_distribution_witness_and_no_invented_joint_probability(models):
    model = models["stochastic-arc-weight-net"]
    restored = model_from_json(model_json_bytes(model)).model
    assert restored.arc_distributions == model.arc_distributions
    assert restored.discovery.fitting_witness == model.discovery.fitting_witness
    assert restored.joint_probability_policy == "not_inferred"
    doc = copy.deepcopy(model_document(model))
    doc["model"]["joint_probability_policy"] = "independent_product"
    with pytest.raises(ValueError, match="joint_probability"):
        model_from_json(refresh_document(doc))


def test_missing_heuristics_bindings_and_false_dependency_measure_are_rejected():
    model = discover_heuristics(case_log(("A", "B"))).value
    with pytest.raises(ValueError, match="requires input and output"):
        model_document(replace(model, bindings=()))
    with pytest.raises(ValueError, match="binding coverage"):
        model_document(
            replace(
                model,
                bindings=tuple(replace(b, alternatives=()) for b in model.bindings),
            )
        )
    with pytest.raises(ValueError, match="profile equation"):
        model_document(
            replace(
                model, dependencies=(replace(model.dependencies[0], measure=999.0),)
            )
        )


def test_orphan_observed_state_cycle_does_not_invent_cases():
    model = TransitionSystem(
        (StateNode("s", ("A",), 1, 0, 0),), (StateEdge("s", "s", "A", 1),), 0, True
    )
    with pytest.raises(ValueError, match="initial-to-final"):
        model_document(model)


def test_nonempty_footprint_cannot_discard_observed_boundaries(models):
    model = models["footprint-model"]
    with pytest.raises(ValueError, match="start-to-end"):
        model_document(replace(model, start_activities=(), end_activities=()))
    with pytest.raises(ValueError, match="start-to-end"):
        model_document(replace(model, minimum_trace_length=None))


@pytest.mark.parametrize(
    "words",
    [
        (),
        ((),),
        (("A",),),
        (("A", "A"),),
        (("A", "B", "A"),),
        (("A", "B", "C"), ("A", "C", "B")),
        ((), ("A", "B"), ("B", "A")),
    ],
)
def test_boundary_and_binding_guards_preserve_valid_generated_corner_cases(words):
    data = case_log(*words)
    for discover in (
        discover_footprints,
        discover_transition_system,
        discover_heuristics,
    ):
        model = discover(data).value
        assert model_from_json(model_json_bytes(model)).model == model
