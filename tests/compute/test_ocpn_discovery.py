"""Hand-checkable native OCPN discovery, binding evidence and counterexamples."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import combinations, product
from random import Random

import pytest

import pix.compute.ocpn_discovery as discovery
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding, is_binding_enabled
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Binding, ObjectMarking, OCPNCardinalityProfile
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def log_of(rows, objects, *, types=None):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(name) for name in sorted({row[1] for row in rows})),
        object_types=tuple(
            ObjectType(name)
            for name in (types or sorted({kind for _, kind in objects}))
        ),
        events=tuple(
            Event(eid, activity, base + timedelta(seconds=index))
            for index, (eid, activity, _) in enumerate(rows)
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects),
        e2o=tuple(E2O(eid, oid, "participant") for eid, _, ids in rows for oid in ids),
    )


def spec(types=("order", "item"), **kwargs):
    return OCPNDiscoverySpec(types, "observed_range", "unique_activity", **kwargs)


def assert_checked_witness(result, log):
    assert result.status is ComputeStatus.COMPUTED, result.issues
    value = result.value
    assert [row.event_id for row in value.observed_event_bindings] == [
        event.id for event in sorted(log.events, key=lambda e: (e.time, e.id))
    ]
    marking = value.model.initial_marking
    for step in value.fitting_witness:
        assert is_binding_enabled(value.model, marking, step.binding)
        marking = fire_binding(value.model, marking, step.binding)
    assert marking == value.model.final_marking
    return value


def test_one_shared_transition_fires_concrete_objects_jointly():
    log = log_of(
        (("e1", "A", ("o1", "i1")), ("e2", "B", ("o1", "i1"))),
        (("o1", "order"), ("i1", "item")),
    )
    value = assert_checked_witness(discovery.discover_ocpn(log, spec()), log)
    assert [(t.activity) for t in value.model.transitions] == ["A", "B"]
    assert len(value.transition_sources) == 4
    assert all(profile.histogram == ((1, 1),) for profile in value.cardinality_profiles)
    assert all(not arc.variable for arc in value.model.arcs)


def test_repeated_type_participation_retains_histogram_one_and_two():
    log = log_of(
        (("e1", "A", ("o1", "i1")), ("e2", "A", ("o2", "i2", "i3"))),
        (
            ("o1", "order"),
            ("o2", "order"),
            ("i1", "item"),
            ("i2", "item"),
            ("i3", "item"),
        ),
    )
    value = assert_checked_witness(discovery.discover_ocpn(log, spec()), log)
    profiles = {(p.activity, p.object_type): p for p in value.cardinality_profiles}
    assert profiles["A", "item"].histogram == ((1, 1), (2, 1))
    assert profiles["A", "item"].arc_kind == "variable"
    assert profiles["A", "order"].histogram == ((1, 2),)
    assert len(value.observed_event_bindings[1].binding.objects[0][1]) == 2


def test_zero_participation_is_counted_and_binding_uses_empty_type_set():
    log = log_of(
        (("e1", "A", ("o1",)), ("e2", "A", ("i1",))), (("o1", "order"), ("i1", "item"))
    )
    result = discovery.discover_ocpn(log, spec())
    value = assert_checked_witness(result, log)
    assert all(
        profile.histogram == ((0, 1), (1, 1)) for profile in value.cardinality_profiles
    )
    assert dict(value.observed_event_bindings[0].binding.objects)["item"] == ()
    # Marginal intervals cannot preserve the observed exclusive participation.
    transition_id = value.model.transitions[0].id
    empty = Binding(transition_id, (("item", ()), ("order", ())))
    assert is_binding_enabled(value.model, value.model.initial_marking, empty)
    assert (
        fire_binding(value.model, value.model.initial_marking, empty)
        == value.model.initial_marking
    )
    assert value.joint_cardinality_guarantee == "marginals_only"
    assert "observational_cardinality_bounds" in {i.code for i in result.issues}


def test_interval_holes_remain_visible_in_evidence():
    log = log_of(
        (("e1", "A", ("i1",)), ("e2", "A", ("i2", "i3", "i4"))),
        tuple((f"i{i}", "item") for i in range(1, 5)),
    )
    result = discovery.discover_ocpn(log, spec(("item",)))
    value = assert_checked_witness(result, log)
    assert value.cardinality_profiles[0].histogram == ((1, 1), (3, 1))
    binding = Binding(value.model.transitions[0].id, (("item", ("i1", "i2")),))
    assert is_binding_enabled(value.model, value.model.initial_marking, binding)
    assert "cardinality_interval_generalization" in {i.code for i in result.issues}


def test_orphan_events_and_excluded_object_types_are_not_dropped():
    log = log_of(
        (("e1", "A", ("o1",)), ("e2", "A", ()), ("e3", "Unrelated", ("i1",))),
        (("o1", "order"), ("i1", "item")),
    )
    result = discovery.discover_ocpn(log, spec(("order",)))
    value = assert_checked_witness(result, log)
    assert value.model.objects == (("o1", "order"),)
    assert value.observed_event_bindings[-1].binding.objects == ()
    profile = next(p for p in value.cardinality_profiles if p.activity == "Unrelated")
    assert profile.arc_kind == "absent" and profile.histogram == ((0, 1),)
    assert {"zero_incidence_activities", "zero_participation_events"} <= {
        i.code for i in result.issues
    }


def test_isolated_object_has_initial_final_tokens_and_silent_accepting_path():
    log = log_of(
        (("e1", "A", ("o1",)),), (("o1", "order"), ("o2", "order"), ("i1", "item"))
    )
    value = assert_checked_witness(discovery.discover_ocpn(log, spec()), log)
    assert len(value.model.initial_marking.tokens) == 3
    assert len(value.model.final_marking.tokens) == 3
    assert {obj for p in value.projections for obj in p.isolated_object_ids} == {
        "o2",
        "i1",
    }
    assert any(step.event_id is None for step in value.fitting_witness)


def test_empty_event_log_still_verifies_selected_isolated_population():
    log = log_of((), (("o1", "order"),))
    value = assert_checked_witness(discovery.discover_ocpn(log, spec(("order",))), log)
    assert value.observed_event_bindings == ()
    assert len(value.fitting_witness) == 1


def test_multiple_qualifiers_count_one_object_and_filter_is_explicit():
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    log = replace(log, e2o=(*log.e2o, E2O("e1", "o1", "resource")))
    all_result = discovery.discover_ocpn(log, spec(("order",)))
    assert all_result.value.cardinality_profiles[0].histogram == ((1, 1),)
    selected = discovery.discover_ocpn(log, spec(("order",), qualifiers=("resource",)))
    assert_checked_witness(selected, log)
    assert selected.value.cardinality_profiles == all_result.value.cardinality_profiles
    none = discovery.discover_ocpn(log, spec(("order",), qualifiers=()))
    assert_checked_witness(none, log)
    assert none.value.cardinality_profiles[0].histogram == ((0, 1),)
    assert (
        len({all_result.computation_id, selected.computation_id, none.computation_id})
        == 3
    )


def test_order_tie_rejected_and_explicit_identity_order_is_auditable():
    log = log_of((("e1", "A", ("o1",)), ("e2", "B", ("o1",))), (("o1", "order"),))
    log = replace(
        log, events=(log.events[0], replace(log.events[1], time=log.events[0].time))
    )
    rejected = discovery.discover_ocpn(log, spec(("order",)))
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert "ambiguous_event_order" in {i.code for i in rejected.issues}
    ordered = discovery.discover_ocpn(log, spec(("order",), tie_policy="event_id"))
    assert_checked_witness(ordered, log)
    assert "event_id_tie_break" in {issue.code for issue in ordered.issues}


def test_duplicate_activity_nodes_are_refused_instead_of_label_collapsed(monkeypatch):
    original = discovery.discover_process_tree

    def duplicate(trace_result, options):
        result = original(trace_result, options)
        return replace(
            result,
            value=ProcessTree(
                "sequence",
                children=(ProcessTree("activity", "A"), ProcessTree("activity", "A")),
            ),
        )

    monkeypatch.setattr(discovery, "discover_process_tree", duplicate)
    log = log_of((("e1", "A", ("o1",)), ("e2", "A", ("o1",))), (("o1", "order"),))
    result = discovery.discover_ocpn(log, spec(("order",)))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "ambiguous_activity_merge" in {i.code for i in result.issues}


def test_nonfitting_local_model_is_not_reported_as_computed(monkeypatch):
    original = discovery.discover_process_tree

    def wrong(trace_result, options):
        return replace(
            original(trace_result, options), value=ProcessTree("activity", "B")
        )

    monkeypatch.setattr(discovery, "discover_process_tree", wrong)
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    result = discovery.discover_ocpn(log, spec(("order",)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert "local_trace_not_fitting" in {i.code for i in result.issues}


def test_fitting_state_bound_is_unavailable_without_false_certificate():
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    result = discovery.discover_ocpn(
        log, spec(("order",), max_fitting_states_per_object=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "fitting_search_limit" in {i.code for i in result.issues}


@pytest.mark.parametrize(
    "log,types,code",
    [
        (log_of((), (("o1", "order"),)), ("missing",), "unknown_object_type"),
        (log_of((), (), types=("order",)), ("order",), "empty_type_population"),
    ],
)
def test_selected_types_never_silently_skipped(log, types, code):
    result = discovery.discover_ocpn(log, spec(types))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == code


def test_raw_invalid_input_preserves_original_errors():
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    log = replace(log, e2o=(E2O("e1", "missing", "participant"),))
    result = discovery.discover_ocpn(log, spec(("order",)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None and result.computation_id is None
    assert any("object" in issue.code for issue in result.issues)
    assert (
        discovery.discover_ocpn("not-log", spec(("order",))).status
        is ComputeStatus.INVALID_INPUT
    )


def test_context_permutation_and_selection_order_have_identical_provenance():
    log = log_of((("e1", "A", ("o1", "i1")),), (("o1", "order"), ("i1", "item")))
    permutation = replace(
        log,
        events=tuple(reversed(log.events)),
        objects=tuple(reversed(log.objects)),
        e2o=tuple(reversed(log.e2o)),
    )
    left = discovery.discover_ocpn(log, spec())
    right = discovery.discover_ocpn(
        ComputationContext(permutation), spec(("item", "order"))
    )
    assert left == right
    assert left.parent_computation_ids == tuple(
        identity
        for p in left.value.projections
        for identity in (p.trace_computation_id, p.discovery_computation_id)
    )
    assert len(set(left.parent_computation_ids)) == 4


def _bindings(net):
    type_by_place = {place.id: place.object_type for place in net.places}
    objects = {
        kind: tuple(oid for oid, object_type in net.objects if object_type == kind)
        for kind in set(type_by_place.values())
    }
    for transition in net.transitions:
        required = {}
        for arc in net.arcs:
            if arc.source == transition.id or arc.target == transition.id:
                kind = type_by_place[
                    arc.target if arc.source == transition.id else arc.source
                ]
                required[kind] = arc.min_objects, arc.max_objects
        names = sorted(required)
        choices = [
            tuple(
                combo
                for n in range(
                    required[kind][0], min(required[kind][1], len(objects[kind])) + 1
                )
                for combo in combinations(objects[kind], n)
            )
            for kind in names
        ]
        for selected in product(*choices):
            yield Binding(transition.id, tuple(zip(names, selected)))


def test_locally_sound_projection_merge_can_have_reachable_joint_deadlock():
    log = log_of(
        (
            ("e1", "A", ("o1", "i1")),
            ("e2", "B", ("i1",)),
            ("e3", "A", ("o1", "i2")),
            ("e4", "B", ("i2",)),
        ),
        (("o1", "order"), ("i1", "item"), ("i2", "item")),
    )
    result = discovery.discover_ocpn(log, spec())
    value = assert_checked_witness(result, log)
    # Stop immediately after the last observed event, before the order exits.
    marking = value.model.initial_marking
    for step in value.fitting_witness:
        marking = fire_binding(value.model, marking, step.binding)
        if step.event_id == "e4":
            break
    bindings = tuple(_bindings(value.model))
    silent_ids = {t.id for t in value.model.transitions if t.activity is None}
    successors = [
        fire_binding(value.model, marking, binding)
        for binding in bindings
        if binding.transition_id in silent_ids
        and is_binding_enabled(value.model, marking, binding)
    ]
    deadlocks = [
        m
        for m in successors
        if m != value.model.final_marking
        and not any(is_binding_enabled(value.model, m, b) for b in bindings)
    ]
    assert deadlocks, (
        "Choosing local loop redo must expose the joint synchronization deadlock"
    )
    assert "joint_soundness_not_established" in {i.code for i in result.issues}


@pytest.mark.parametrize(
    "updates",
    [
        {"object_types": ()},
        {"object_types": ("order", "order")},
        {"object_types": ["order"]},
        {"object_types": (" ",)},
        {"cardinality_policy": "fixed"},
        {"merge_policy": "label"},
        {"tie_policy": "arbitrary"},
        {"classic_algorithm": "pm4py"},
        {"max_depth": 0},
        {"max_depth": 129},
        {"max_depth": True},
        {"max_fitting_states_per_object": 0},
        {"max_fitting_states_per_object": 1.5},
        {"qualifiers": ["x"]},
        {"qualifiers": ("x", "x")},
    ],
)
def test_explicit_spec_rejects_unsupported_or_mutable_policy(updates):
    fields = dict(
        object_types=("order",),
        cardinality_policy="observed_range",
        merge_policy="unique_activity",
    )
    with pytest.raises((TypeError, ValueError)):
        OCPNDiscoverySpec(**(fields | updates))


def test_cardinality_evidence_cannot_claim_different_bounds_or_arc_kind():
    profile = OCPNCardinalityProfile("A", "order", ((0, 1), (1, 2)), "variable", 0, 1)
    with pytest.raises(ValueError):
        replace(profile, arc_kind="fixed")
    with pytest.raises(ValueError):
        replace(profile, min_objects=1)
    with pytest.raises(ValueError):
        replace(profile, histogram=((1, 1), (1, 2)))


def test_witness_contract_rejects_omitted_or_relabelled_observations():
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    payload = discovery.discover_ocpn(log, spec(("order",))).value
    with pytest.raises(ValueError):
        replace(payload, fitting_witness=())
    with pytest.raises(ValueError):
        replace(
            payload,
            observed_event_bindings=(
                replace(payload.observed_event_bindings[0], activity="B"),
            ),
        )
    with pytest.raises(TypeError):
        replace(payload, model=ObjectMarking())


def test_requested_spec_type_is_not_coerced():
    with pytest.raises(TypeError):
        discovery.discover_ocpn(OCEL(), {"object_types": ("order",)})


def test_shared_native_shipping_fixture_has_verified_joint_witness(native_log):
    assert_checked_witness(
        discovery.discover_ocpn(native_log, spec(("Order", "Package", "Resource"))),
        native_log,
    )


@pytest.mark.parametrize("algorithm", ("pix.inductive_cut.v1", "pix.im.v1"))
@pytest.mark.parametrize("seed", range(100))
def test_seeded_multitype_logs_have_executable_event_identity_witnesses(
    seed, algorithm
):
    random = Random(seed)
    objects = (("o1", "order"), ("o2", "order"), ("i1", "item"), ("i2", "item"))
    rows = tuple(
        (
            f"e{index:02d}",
            random.choice(("A", "B", "C")),
            tuple(oid for oid, _ in objects if random.randrange(3) == 0),
        )
        for index in range(random.randrange(1, 9))
    )
    log = log_of(rows, objects)
    result = discovery.discover_ocpn(log, spec(classic_algorithm=algorithm))
    assert_checked_witness(result, log)
    for observed in result.value.observed_event_bindings:
        expected = {
            oid for eid, _, ids in rows if eid == observed.event_id for oid in ids
        }
        assert {oid for _, ids in observed.binding.objects for oid in ids} == expected


@pytest.mark.parametrize(
    "mutation",
    (
        "initial",
        "final",
        "profiles",
        "histogram",
        "projections",
        "object_count",
        "isolates",
        "sources",
        "duplicate_profiles",
        "duplicate_projections",
    ),
)
def test_payload_rejects_self_contradictory_certificate_and_evidence(mutation):
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    payload = discovery.discover_ocpn(log, spec(("order",))).value
    with pytest.raises(ValueError):
        if mutation == "initial":
            replace(
                payload, model=replace(payload.model, initial_marking=ObjectMarking())
            )
        elif mutation == "final":
            replace(
                payload, model=replace(payload.model, final_marking=ObjectMarking())
            )
        elif mutation == "profiles":
            replace(payload, cardinality_profiles=())
        elif mutation == "histogram":
            replace(
                payload,
                cardinality_profiles=(
                    replace(payload.cardinality_profiles[0], histogram=((1, 2),)),
                ),
            )
        elif mutation == "projections":
            replace(payload, projections=())
        elif mutation == "object_count":
            replace(
                payload, projections=(replace(payload.projections[0], object_count=2),)
            )
        elif mutation == "isolates":
            replace(
                payload,
                projections=(
                    replace(payload.projections[0], isolated_object_ids=("o1",)),
                ),
            )
        elif mutation == "sources":
            replace(payload, transition_sources=())
        elif mutation == "duplicate_profiles":
            replace(payload, cardinality_profiles=payload.cardinality_profiles * 2)
        else:
            replace(payload, projections=payload.projections * 2)


def test_discovery_depth_limit_preserves_local_diagnostic():
    log = log_of((("e1", "A", ("o1",)), ("e2", "B", ("o1",))), (("o1", "order"),))
    result = discovery.discover_ocpn(log, spec(("order",), max_depth=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert {"discovery_depth_limit", "local_discovery_not_computed"} <= {
        i.code for i in result.issues
    }


def test_weighted_local_arcs_are_not_reinterpreted_as_object_cardinality(monkeypatch):
    original = discovery.process_tree_to_petri_net

    def weighted(tree):
        model = original(tree)
        return replace(model, arcs=tuple(replace(arc, weight=2) for arc in model.arcs))

    monkeypatch.setattr(discovery, "process_tree_to_petri_net", weighted)
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    result = discovery.discover_ocpn(log, spec(("order",)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "weighted_local_arc_unsupported"


def test_certificate_mapping_cannot_hide_same_type_duplicate_transition_merge():
    log = log_of((("e1", "A", ("o1",)),), (("o1", "order"),))
    payload = discovery.discover_ocpn(log, spec(("order",))).value
    extra = replace(
        payload.transition_sources[0], local_transition_id="second-local-node"
    )
    with pytest.raises(ValueError, match="multiple local transitions"):
        replace(payload, transition_sources=(*payload.transition_sources, extra))
