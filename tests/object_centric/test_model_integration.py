"""Reference conditions and independently calculated OC model attachment cases."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from pix.compute.model_semantics import model_digest
from pix.contracts.models import (
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.conformance import ObjectReplaySpec
from pix.object_centric.model_integration import (
    RESULT_SCHEMAS,
    EnhancedOCPNSpec,
    OCPNDecompositionSpec,
    SubprocessParticipationSpec,
    check_subprocess_participation,
    decompose_ocpn,
    enhance_ocpn,
    recompose_ocpn,
)
from pix.object_centric.performance import OCReplayPerformanceSpec
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def marking(*pairs):
    return ObjectMarking(tuple(ObjectToken(*pair) for pair in pairs))


def shipping():
    return ObjectCentricPetriNet(
        tuple(
            TypedPlace(name, kind)
            for name, kind in (
                ("ir", "item"),
                ("id", "item"),
                ("or", "order"),
                ("od", "order"),
            )
        ),
        (Transition("ship", "Ship"),),
        (
            ObjectArc("ir", "ship", True, 1, 2),
            ObjectArc("ship", "id", True, 1, 2),
            ObjectArc("or", "ship"),
            ObjectArc("ship", "od"),
        ),
        marking(("ir", "i1"), ("ir", "i2"), ("or", "o")),
        marking(("id", "i1"), ("id", "i2"), ("od", "o")),
        (("i1", "item"), ("i2", "item"), ("o", "order")),
    )


def sequence(*, repeated_label=False):
    return ObjectCentricPetriNet(
        tuple(TypedPlace(p, "item") for p in ("p0", "p1", "p2")),
        (Transition("a", "A"), Transition("b", "A" if repeated_label else "B")),
        (
            ObjectArc("p0", "a"),
            ObjectArc("a", "p1"),
            ObjectArc("p1", "b"),
            ObjectArc("b", "p2"),
        ),
        marking(("p0", "x")),
        marking(("p2", "x")),
        (("x", "item"),),
    )


def log_of(rows):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(
            EventType(name) for name in sorted({activity for _, activity, _, _ in rows})
        ),
        object_types=(ObjectType("item"),),
        objects=(Object("x", "item"),),
        events=tuple(
            Event(eid, activity, origin + timedelta(seconds=seconds))
            for eid, activity, seconds, _ in rows
        ),
        e2o=tuple(
            E2O(eid, "x", qualifier)
            for eid, _, _, qualifiers in rows
            for qualifier in qualifiers
        ),
    )


def request(
    *, activities=None, metrics=("flow", "sojourn", "synchronization"), **kwargs
):
    return EnhancedOCPNSpec(
        ObjectReplaySpec(("item",), **kwargs),
        OCReplayPerformanceSpec(metrics=metrics, activities=activities),
    )


def test_type_net_decomposition_aggregates_token_counts_and_retains_exact_identity_ledger():
    net = shipping()
    result = decompose_ocpn(net)
    assert result.status is ComputeStatus.COMPUTED
    item, order = result.value.per_type
    assert item.object_type == "item" and item.petri_net.initial_marking == Marking(
        (("ir", 2),)
    )
    assert order.petri_net.initial_marking == Marking((("or", 1),))
    assert all(a.weight == 1 for a in item.petri_net.arcs)
    assert all(a.variable and a.max_objects == 2 for a in item.arc_cardinalities)
    assert item.start_transition_ids == item.end_transition_ids == ("ship",)
    assert result.value.shared_transition_ids == ("ship",)
    assert (
        "joint_transition_synchronization_across_types"
        in result.value.projected_semantic_losses
    )
    assert recompose_ocpn(result.value) == net


def test_repeated_concrete_tokens_are_not_reduced_to_unique_object_count():
    source = shipping()
    source = replace(
        source,
        initial_marking=ObjectMarking(
            source.initial_marking.tokens + (ObjectToken("ir", "i1"),)
        ),
    )
    result = decompose_ocpn(source).value
    item = result.per_type[0]
    assert item.petri_net.initial_marking == Marking((("ir", 3),))
    assert item.object_ids == ("i1", "i2")
    assert item.concrete_initial_marking.tokens.count(ObjectToken("ir", "i1")) == 2
    assert recompose_ocpn(result) == source


def test_orphan_transitions_empty_place_types_and_isolated_objects_survive_recomposition():
    source = shipping()
    source = replace(
        source,
        places=source.places + (TypedPlace("ghost", "empty_type"),),
        transitions=source.transitions
        + (Transition("orphan", "Orphan"), Transition("orphan_tau")),
        objects=source.objects + (("lonely", "unused_type"),),
    )
    result = decompose_ocpn(source).value
    assert tuple(row.object_type for row in result.per_type) == (
        "empty_type",
        "item",
        "order",
        "unused_type",
    )
    assert len(result.unattached_transitions) == 2
    assert result.activity_labels == ("Orphan", "Ship")
    assert recompose_ocpn(result) == source
    assert model_digest(recompose_ocpn(result)) == result.source_model_digest


def test_duplicate_activity_labels_are_not_merged_as_transition_identity():
    source = sequence(repeated_label=True)
    result = decompose_ocpn(source).value
    assert result.activity_labels == ("A",)
    assert tuple(t.id for t in result.per_type[0].petri_net.transitions) == ("a", "b")
    assert result.per_type[0].start_transition_ids == ("a",)
    assert result.per_type[0].end_transition_ids == ("b",)
    assert recompose_ocpn(result) == source


def test_decomposition_validates_marking_arc_and_source_identity_claims():
    value = decompose_ocpn(shipping()).value
    row = value.per_type[0]
    with pytest.raises(ValueError, match="aggregate markings"):
        replace(row, concrete_initial_marking=ObjectMarking())
    with pytest.raises(ValueError, match="incidence"):
        replace(row, arc_cardinalities=())
    with pytest.raises(ValueError, match="source model identity"):
        replace(value, source_model_digest="changed")
    with pytest.raises(ValueError, match="shared transition"):
        replace(value, shared_transition_ids=())
    with pytest.raises(ValueError, match="start transitions"):
        replace(row, start_transition_ids=())
    with pytest.raises(ValueError):
        OCPNDecompositionSpec("execution_equivalent")


def test_participation_is_existential_selected_type_incidence_not_all_types():
    net = shipping()
    # Selecting item alone suffices for Ship although an order is also required
    # for every actual binding. This is exactly an existential incidence test.
    value = check_subprocess_participation(
        net, SubprocessParticipationSpec(("item",), transition_ids=("ship",))
    ).value
    assert value.all_selected_transitions_participate
    assert value.transitions[0].incident_object_types == ("item", "order")
    assert value.transitions[0].selected_incident_place_ids == ("id", "ir")
    assert value.soundness_established is None
    assert value.condition.startswith("for_each_selected_transition_exists")


def test_participation_uses_both_input_and_output_incidence():
    net = ObjectCentricPetriNet(
        (TypedPlace("p", "item"),),
        (Transition("create", "Create"), Transition("consume", "Consume")),
        (ObjectArc("create", "p"), ObjectArc("p", "consume")),
        ObjectMarking(),
        ObjectMarking(),
        (("x", "item"),),
    )
    value = check_subprocess_participation(
        net,
        SubprocessParticipationSpec(("item",), transition_ids=("create", "consume")),
    ).value
    assert value.all_selected_transitions_participate
    assert all(row.selected_incident_place_ids == ("p",) for row in value.transitions)


def test_activity_selection_checks_all_duplicate_labels_instead_of_first_match():
    net = shipping()
    net = replace(net, transitions=net.transitions + (Transition("orphan", "Ship"),))
    selected = check_subprocess_participation(
        net, SubprocessParticipationSpec(("item",), activities=("Ship",))
    ).value
    assert (
        len(selected.transitions) == 2
        and not selected.all_selected_transitions_participate
    )
    assert (
        next(
            row for row in selected.transitions if row.transition_id == "orphan"
        ).has_selected_type_incidence
        is False
    )
    default = check_subprocess_participation(
        net, SubprocessParticipationSpec(("item",))
    ).value
    assert tuple(row.transition_id for row in default.transitions) == ("ship",)
    assert default.all_selected_transitions_participate


def test_empty_participation_condition_is_explicit_vacuous_truth():
    value = check_subprocess_participation(
        shipping(), SubprocessParticipationSpec((), transition_ids=())
    ).value
    assert (
        value.empty_transition_selection and value.all_selected_transitions_participate
    )
    selected = check_subprocess_participation(
        shipping(), SubprocessParticipationSpec((), transition_ids=("ship",))
    ).value
    assert (
        not selected.empty_transition_selection
        and not selected.all_selected_transitions_participate
    )
    inferred = check_subprocess_participation(
        shipping(), SubprocessParticipationSpec(())
    ).value
    assert inferred.empty_transition_selection


@pytest.mark.parametrize(
    "parameters",
    [
        {"object_types": ("missing",)},
        {"object_types": ("item",), "transition_ids": ("missing",)},
        {"object_types": ("item",), "activities": ("missing",)},
    ],
)
def test_participation_rejects_unknown_identifiers(parameters):
    with pytest.raises(ValueError):
        check_subprocess_participation(
            shipping(), SubprocessParticipationSpec(**parameters)
        )
    with pytest.raises(ValueError):
        SubprocessParticipationSpec(
            ("item",), transition_ids=("ship",), activities=("Ship",)
        )


def test_enhanced_ocpn_attaches_actual_token_arrival_gap_and_parent_evidence():
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    net = sequence()
    result = enhance_ocpn(log, net, request(activities=("B",)))
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.parent_computation_ids) == 2
    assert result.value.replay.fitting is True
    b = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "b"
    )
    assert b.observed_event_ids == ("e2",)
    assert (
        b.consumed_token_count == b.produced_token_count == 1
        and b.inserted_token_count == 0
    )
    values = {summary.metric: summary for summary in b.metrics}
    assert values["flow"].total == values["sojourn"].total == 10_000_000
    assert values["synchronization"].total == 0
    assert result.value.performance.token_inputs[0].arrivals[0].source_event_ids == (
        "e1",
    )
    assert result.value.model == net


def test_initial_token_clock_unknown_survives_enhancement_and_is_not_zero_filled():
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    result = enhance_ocpn(log, sequence(), request())
    assert result.status is ComputeStatus.PARTIAL
    a = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "a"
    )
    assert all(
        summary.unknown_count == 1 and summary.known_count == 0 for summary in a.metrics
    )
    assert all(
        summary.samples[0].reason == "token_input_time_unknown" for summary in a.metrics
    )
    assert (
        result.value.replay.fitting is True
    )  # fitness does not establish input clocks


def test_same_activity_diagnostics_attach_only_to_transition_actually_fired():
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "A", 10, ("flow",))))
    result = enhance_ocpn(log, sequence(repeated_label=True), request())
    rows = {row.transition_id: row for row in result.value.transition_diagnostics}
    assert rows["a"].observed_event_ids == ("e1",) and rows["b"].observed_event_ids == (
        "e2",
    )
    assert all(
        summary.population_count == 1
        for row in rows.values()
        for summary in row.metrics
    )
    assert result.value.unassigned_performance_event_ids == ()


def test_multiple_qualifiers_do_not_duplicate_event_firings_or_durations():
    rows = (("e1", "A", 0, ("flow", "resource")), ("e2", "B", 10, ("flow", "resource")))
    result = enhance_ocpn(log_of(rows), sequence(), request(activities=("B",)))
    b = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "b"
    )
    assert len(b.firing_step_indices) == 1
    assert b.metrics[0].population_count == 1


def test_unmapped_events_remain_unassigned_diagnostics_and_deviations():
    log = log_of(
        (
            ("e1", "A", 0, ("flow",)),
            ("other", "Other", 5, ("flow",)),
            ("e2", "B", 10, ("flow",)),
        )
    )
    result = enhance_ocpn(log, sequence(), request())
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.unassigned_performance_event_ids == ("other",)
    assert result.value.replay.log_deviation_count == 1
    assert result.value.replay.fitting is False
    assert not any(
        "other" in row.observed_event_ids for row in result.value.transition_diagnostics
    )


def test_enhancement_does_not_mask_repair_missing_tokens_as_fitting():
    log = log_of((("e2", "B", 10, ("flow",)),))
    result = enhance_ocpn(log, sequence(), request())
    assert result.value.replay.fitting is False
    b = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "b"
    )
    assert b.inserted_token_count == 1
    assert all(
        summary.samples[0].reason == "token_input_time_unknown" for summary in b.metrics
    )


def test_silent_steps_have_token_counts_without_fabricated_observed_durations():
    net = sequence()
    net = replace(
        net,
        places=net.places + (TypedPlace("p1b", "item"),),
        transitions=net.transitions + (Transition("tau"),),
        arcs=tuple(a for a in net.arcs if a.source != "p1")
        + (ObjectArc("p1", "tau"), ObjectArc("tau", "p1b"), ObjectArc("p1b", "b")),
    )
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    result = enhance_ocpn(log, net, request(activities=("B",)))
    tau = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "tau"
    )
    assert (
        len(tau.firing_step_indices) == 1
        and tau.consumed_token_count == tau.produced_token_count == 1
    )
    assert tau.observed_event_ids == () and all(
        summary.population_count == 0 for summary in tau.metrics
    )
    b = next(
        row for row in result.value.transition_diagnostics if row.transition_id == "b"
    )
    assert (
        next(summary for summary in b.metrics if summary.metric == "flow").total
        == 10_000_000
    )


def test_enhancement_identity_covers_model_and_selected_timing_profile():
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    one = enhance_ocpn(log, sequence(), request(activities=("B",)))
    two = enhance_ocpn(log, sequence(), request(activities=("A",)))
    assert (
        one.source_digest == two.source_digest
        and one.computation_id != two.computation_id
    )
    with pytest.raises(FrozenInstanceError):
        one.value.profile = "unverified"
    with pytest.raises(ValueError, match="model identity"):
        replace(one.value, model=shipping())
    forged = replace(one.value.transition_diagnostics[0], consumed_token_count=500)
    with pytest.raises(ValueError, match="disagree with replay"):
        replace(
            one.value,
            transition_diagnostics=(forged, *one.value.transition_diagnostics[1:]),
        )
    with pytest.raises(ValueError, match="disagree with replay"):
        replace(one.value, unassigned_performance_event_ids=("fabricated",))


def test_invalid_log_or_ambiguous_order_does_not_produce_diagnostics():
    invalid = enhance_ocpn(object(), sequence(), request())
    assert invalid.status is ComputeStatus.INVALID_INPUT and invalid.value is None
    tied = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 0, ("flow",))))
    result = enhance_ocpn(tied, sequence(), request())
    assert result.value is None and result.issues
    explicit = enhance_ocpn(
        tied, sequence(), request(tie_policy="event_id", activities=("B",))
    )
    assert explicit.value is not None


@pytest.mark.parametrize(
    "call",
    [
        lambda: decompose_ocpn(shipping()),
        lambda: check_subprocess_participation(
            shipping(), SubprocessParticipationSpec(("item",), activities=("Ship",))
        ),
        lambda: enhance_ocpn(
            log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",)))),
            sequence(),
            request(),
        ),
    ],
)
def test_integration_result_roundtrips_preserve_nested_evidence(call):
    from pix import results

    result = call()
    with patch.object(results, "_schemas", return_value=RESULT_SCHEMAS):
        restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result


def test_empty_model_decomposes_and_recomposes_without_fabricated_components():
    net = ObjectCentricPetriNet((), (), (), ObjectMarking(), ObjectMarking(), ())
    value = decompose_ocpn(net).value
    assert value.per_type == value.unattached_transitions == value.activity_labels == ()
    assert recompose_ocpn(value) == net


def test_equivalent_ocel_result_roundtrip_retains_exact_encoding_and_anchor_ids():
    from pix import results
    from pix.object_centric.equivalent_ocel import (
        RESULT_SCHEMAS as equivalent_schemas,
    )
    from pix.object_centric.equivalent_ocel import (
        EquivalentOCELSpec,
        cluster_equivalent_ocel,
    )

    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    result = cluster_equivalent_ocel(log, EquivalentOCELSpec("item"))
    with patch.object(results, "_schemas", return_value=equivalent_schemas):
        restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result
    assert restored.value.scopes[0].leading_object_id == "x"
    assert restored.value.scopes[0].canonical_encoding


def test_enhancement_rejects_other_replay_timing_even_when_aggregates_and_model_match():
    first_log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    second_log = log_of(
        (
            ("e1", "A", 0, ("flow",)),
            ("other", "Other", 5, ("flow",)),
            ("e2", "B", 10, ("flow",)),
        )
    )
    first = enhance_ocpn(first_log, sequence(), request(activities=("B",))).value
    second = enhance_ocpn(second_log, sequence(), request(activities=("B",))).value
    assert first.transition_diagnostics == second.transition_diagnostics[:1] + (
        replace(
            second.transition_diagnostics[1],
            firing_step_indices=first.transition_diagnostics[1].firing_step_indices,
        ),
    )
    assert (
        first.performance.token_inputs[0].step_index
        != second.performance.token_inputs[0].step_index
    )
    with pytest.raises(ValueError, match="differs from attached replay"):
        replace(first, performance=second.performance)


def test_enhancement_rejects_forged_production_step_and_token_serial():
    log = log_of((("e1", "A", 0, ("flow",)), ("e2", "B", 10, ("flow",))))
    value = enhance_ocpn(log, sequence(), request(activities=("B",))).value
    inputs = value.performance.token_inputs[0]
    arrival = inputs.arrivals[0]
    for changed in (
        replace(arrival, produced_step=0),
        replace(arrival, token_serial=500),
        replace(arrival, source_event_ids=("e2",)),
    ):
        performance = replace(
            value.performance, token_inputs=(replace(inputs, arrivals=(changed,)),)
        )
        with pytest.raises(ValueError, match="provenance differs"):
            replace(value, performance=performance)
