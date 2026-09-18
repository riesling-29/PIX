"""Hand-counted replay cutoffs, evidence classes, and hostile witness checks."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.contracts.models import (
    Binding,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.conformance import ObjectReplaySpec, replay_object_log
from pix.object_centric.operational_impact import (
    OperationalImpactSpec,
    PopulationDelta,
    PopulationEvidence,
    assess_operational_impact,
    validate_operational_impact_result,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def marking(*tokens):
    return ObjectMarking(tuple(ObjectToken(*item) for item in tokens))


def model(*, missing=False, silent=False, duplicate=False):
    """Both objects participate in A together; p --A--> q --B--> r."""
    objects = (("a", "Item"), ("b", "Item"))
    places = tuple(TypedPlace(p, "Item") for p in ("p", "q", "r"))
    transitions = (Transition("a", "A"), Transition("b", "B"))
    arcs = tuple(
        ObjectArc(start, end, True, 1, 2)
        for start, end in (("p", "a"), ("a", "q"), ("q", "b"), ("b", "r"))
    )
    initial = marking(("p", "a"), *(() if missing else (("p", "b"),)))
    if duplicate:
        initial = ObjectMarking(initial.tokens + (ObjectToken("p", "a"),))
    if silent:
        places += (TypedPlace("start", "Item"),)
        transitions += (Transition("tau"),)
        arcs += (
            ObjectArc("start", "tau", True, 1, 2),
            ObjectArc("tau", "p", True, 1, 2),
        )
        initial = marking(("start", "a"), ("start", "b"))
    return ObjectCentricPetriNet(
        places, transitions, arcs, initial, marking(("r", "a"), ("r", "b")), objects
    )


def source(net, activities=("A", "B"), *, duplicate_qualifier=False):
    origin = datetime(2026, 9, 17, tzinfo=timezone.utc)
    events = tuple(
        Event(f"e{index}", activity, origin + timedelta(seconds=index))
        for index, activity in enumerate(activities)
    )
    links = tuple(
        E2O(event.id, identity, "flow")
        for event in events
        for identity, _ in net.objects
    )
    if duplicate_qualifier:
        links += tuple(
            E2O(event.id, identity, "audit")
            for event in events
            for identity, _ in net.objects
        )
    return OCEL(
        event_types=tuple(EventType(activity) for activity in sorted(set(activities))),
        object_types=(ObjectType("Item"),),
        events=events,
        objects=tuple(Object(*item) for item in net.objects),
        e2o=links,
    )


def request(before=0, after=None, **kwargs):
    return OperationalImpactSpec(
        ObjectReplaySpec(("Item",), **kwargs), ("a",), before, after
    )


def test_before_after_cutoff_and_signed_population_differences():
    net = model()
    result = assess_operational_impact(source(net), net, request(0, 1))
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert value.baseline.witness_marking == marking(("p", "a"), ("p", "b"))
    assert value.scenario.witness_marking == marking(("q", "a"), ("q", "b"))
    assert value.scenario.binding_justified_marking == value.scenario.witness_marking
    assert value.baseline.processed_event_ids == ()
    assert value.scenario.processed_event_ids == ("e0",)
    delta = value.typed_deltas[0]
    assert delta.prior.total_count == -2
    assert delta.posterior.total_count == 2
    assert delta.prior.lost_object_ids == ("a", "b")
    assert delta.posterior.gained_object_ids == ("a", "b")
    assert value.structural.typed[0].posterior_transition_ids == ("b",)
    assert value.structural.typed[0].prior_marked_object_ids is None
    assert (
        value.interpretation == "model_inferred_population_difference_not_causal_effect"
    )
    reverse = assess_operational_impact(source(net), net, request(1, 0)).value
    assert reverse.typed_deltas[0].prior.total_count == 2
    assert reverse.typed_deltas[0].posterior.total_count == -2


def test_terminal_consumption_and_terminal_repairs_do_not_erase_population():
    net = model()
    log = source(net)
    replay = replay_object_log(log, net, ObjectReplaySpec(("Item",)))
    assert replay.value.ending_marking == ()
    value = assess_operational_impact(log, net, request(), replay=replay).value
    assert value.scenario.witness_marking == net.final_marking
    assert value.scenario.processed_event_ids == ("e0", "e1")
    # An incomplete log requires repair only during terminal finalization.
    short = source(net, ("A",))
    repaired = replay_object_log(short, net, ObjectReplaySpec(("Item",)))
    assert repaired.value.steps[-1].inserted_tokens
    cutoff = assess_operational_impact(
        short, net, request(), replay=repaired
    ).value.scenario
    assert cutoff.witness_marking == marking(("q", "a"), ("q", "b"))
    assert cutoff.inserted_token_count == 0


def test_unique_shared_events_objects_and_duplicate_qualifiers():
    net = model(duplicate=True)
    value = assess_operational_impact(
        source(net, duplicate_qualifier=True), net, request(0, 1)
    ).value
    assert len(value.scenario.witness_marking.tokens) == 3
    assert value.scenario.processed_event_ids == ("e0",)
    assert value.baseline.typed[0].prior.total_object_count == 2
    assert value.scenario.typed[0].prior.total_object_count == 1
    assert value.scenario.typed[0].posterior.total_object_count == 2
    assert value.typed_deltas[0].prior.total_count == -1


def test_silent_inference_is_distinct_from_observed_bindings_and_repairs():
    net = model(silent=True)
    value = assess_operational_impact(source(net), net, request(0, 1)).value
    assert value.baseline.evidence == "observed_binding"
    assert value.baseline.silent_binding_count == 0
    assert value.scenario.evidence == "inferred_silent"
    assert value.scenario.silent_binding_count >= 1
    assert value.scenario.binding_justified_marking is None
    assert value.scenario.typed[0].posterior.observed_binding_object_ids == ()
    assert value.scenario.typed[0].posterior.inferred_silent_object_ids == ("a", "b")
    assert value.scenario.typed[0].posterior.repaired_object_ids == ()


def test_repair_taints_entire_shared_binding_and_propagates_to_later_events():
    net = model(missing=True)
    value = assess_operational_impact(source(net), net, request(1, 2)).value
    assert value.baseline.inserted_token_count == 1
    assert value.baseline.evidence == value.scenario.evidence == "repaired"
    assert value.scenario.binding_justified_marking is None
    assert value.baseline.typed[0].posterior.repaired_object_ids == ("a", "b")
    assert value.scenario.typed[0].posterior.repaired_object_ids == ("a", "b")
    assert value.typed_deltas[0].posterior.repaired_count == 0
    assert value.typed_deltas[0].posterior.total_count == 0


def test_unknown_activity_is_unknown_population_not_empty_or_observed():
    net = model()
    result = assess_operational_impact(
        source(net, ("unmapped", "A", "B")), net, request()
    )
    assert result.status is ComputeStatus.PARTIAL
    value = result.value
    assert value.scenario.evidence == "unknown"
    assert value.scenario.deviation_event_ids == ("e0",)
    assert value.scenario.binding_justified_marking is None
    assert value.scenario.typed[0].prior.unknown_object_ids == ("a", "b")
    assert value.scenario.typed[0].posterior.unknown_object_ids == ("a", "b")
    assert value.scenario.typed[0].posterior.total_object_count is None
    assert value.typed_deltas[0].posterior.total_count is None
    assert value.typed_deltas[0].posterior.gained_object_ids is None
    assert "unknown_operational_population" in {issue.code for issue in result.issues}


def test_partial_replay_retains_known_prefix_and_unknown_requested_suffix():
    net = model(silent=True)
    result = assess_operational_impact(source(net), net, request(silent_max_states=1))
    assert result.status is ComputeStatus.PARTIAL
    value = result.value
    assert value.replay_status == "limited"
    assert value.baseline.evidence == "partial"
    assert value.baseline.witness_marking == net.initial_marking
    assert value.baseline.binding_justified_marking is None
    assert value.scenario.witness_marking is None
    assert value.scenario.processed_event_ids == ()
    assert value.scenario.unprocessed_event_ids == ("e0", "e1")
    assert value.scenario.typed[0].all_objects.unknown_object_ids == ("a", "b")
    assert value.typed_deltas[0].prior.total_count is None


def test_perfect_witness_round_trip_validation_and_parent_identity():
    net = model()
    log = source(net)
    spec = request()
    replay = replay_object_log(log, net, spec.replay_spec)
    provided = assess_operational_impact(log, net, spec, replay=replay)
    generated = assess_operational_impact(log, net, spec)
    assert provided == generated
    assert provided.parent_computation_ids == (replay.computation_id,)
    assert provided.source_digest == replay.source_digest
    assert provided.value.replay_computation_id == replay.computation_id


@pytest.mark.parametrize(
    "tamper", ("binding", "model", "source", "identity", "request", "status")
)
def test_rejects_forged_or_wrong_replay_even_when_dataclasses_accept_it(tamper):
    net = model()
    log = source(net)
    spec = request()
    replay = replay_object_log(log, net, spec.replay_spec)
    if tamper == "binding":
        steps = tuple(
            replace(step, binding=Binding("forged-transition", step.binding.objects))
            if step.kind == "visible"
            else step
            for step in replay.value.steps
        )
        replay = replace(replay, value=replace(replay.value, steps=steps))
    elif tamper == "model":
        net = replace(net, final_marking=marking(("q", "a"), ("q", "b")))
    elif tamper == "source":
        log = replace(
            log,
            events=(
                replace(log.events[0], time=log.events[0].time - timedelta(seconds=1)),
                log.events[1],
            ),
        )
    elif tamper == "identity":
        replay = replace(replay, computation_id="forged-request-identity")
    elif tamper == "request":
        spec = request(max_bindings=99)
    else:
        replay = replace(replay, operator_version="1000.0.0")
    result = assess_operational_impact(log, net, spec, replay=replay)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "replay_verification_failed"


def test_independent_event_cutoff_follows_declared_replay_order_not_wall_clock():
    # Independent objects allow event ID order to disagree with timestamp order.
    net = model()
    log = source(net, ("A", "A"))
    log = replace(
        log,
        events=(replace(log.events[0], id="z"), replace(log.events[1], id="a")),
        e2o=(E2O("z", "a", "flow"), E2O("a", "b", "flow")),
    )
    value = assess_operational_impact(log, net, request(0, 1)).value
    assert value.replay_event_order == ("a", "z")
    assert value.scenario.processed_event_ids == ("a",)
    assert value.scenario.typed[0].posterior.observed_binding_object_ids == ("b",)


def test_cutoff_identity_empty_cutoff_and_invalid_boundary():
    net = model()
    log = source(net)
    same = assess_operational_impact(log, net, request(1, 1))
    other = assess_operational_impact(log, net, request(0, 1))
    assert same.computation_id != other.computation_id
    assert same.value.typed_deltas[0].prior.total_count == 0
    assert same.value.typed_deltas[0].posterior.total_count == 0
    invalid = assess_operational_impact(log, net, request(0, 3))
    assert invalid.status is ComputeStatus.INVALID_INPUT
    assert invalid.value is None
    empty = assess_operational_impact(source(net, ()), net, request()).value
    assert empty.baseline == empty.scenario
    assert empty.scenario.event_count == 0
    assert empty.scenario.witness_marking == net.initial_marking


def test_invalid_source_does_not_become_an_empty_population():
    net = model()
    result = assess_operational_impact("not OCEL", net, request())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.source_digest is None


@pytest.mark.parametrize("count", (-1, 1.0, True, "1"))
def test_cutoff_type_and_range_contract(count):
    with pytest.raises((TypeError, ValueError)):
        request(count, 1)
    with pytest.raises((TypeError, ValueError)):
        request(0, count)


def test_public_contracts_reject_incoherent_evidence_and_deltas():
    with pytest.raises(ValueError, match="disjoint"):
        PopulationEvidence(("a",), (), ("a",))
    with pytest.raises(ValueError, match="sorted unique"):
        PopulationEvidence(("b", "a"))
    with pytest.raises(ValueError, match="unknown populations"):
        PopulationDelta(0, 0, 0, 0, (), (), ("a",))
    with pytest.raises(ValueError, match="membership delta"):
        PopulationDelta(0, 0, 0, 1, (), (), ())
    net = model()
    value = assess_operational_impact(source(net), net, request()).value
    with pytest.raises(FrozenInstanceError):
        value.interpretation = "causal"
    with pytest.raises(ValueError, match="disagree"):
        replace(value, typed_deltas=())
    with pytest.raises(ValueError, match="justification"):
        replace(value.scenario, binding_justified_marking=None)
    with pytest.raises(ValueError, match="unknown operational"):
        replace(value, interpretation="causal_effect")


@pytest.mark.parametrize(
    "profile", ("observed", "repaired", "silent", "unknown", "limited")
)
def test_serialized_result_round_trip(profile):
    from pix.results import result_from_json, result_json_bytes

    net = model(missing=profile == "repaired", silent=profile in ("silent", "limited"))
    log = source(net, ("unmapped", "A", "B") if profile == "unknown" else ("A", "B"))
    spec = request(silent_max_states=1) if profile == "limited" else request()
    result = assess_operational_impact(log, net, spec)
    assert result_from_json(result_json_bytes(result)) == result


def test_timestamp_tie_convention_is_diagnostic_not_partial_population():
    from pix.results import result_from_json, result_json_bytes

    net = model()
    log = source(net)
    log = replace(
        log, events=(log.events[0], replace(log.events[1], time=log.events[0].time))
    )
    result = assess_operational_impact(log, net, request(tie_policy="event_id"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.issues
    assert result.value.scenario.evidence == "observed_binding"
    assert result_from_json(result_json_bytes(result)) == result


def test_isolated_object_types_are_retained_with_known_empty_affected_regions():
    net = model()
    net = replace(net, objects=net.objects + (("order", "Order"),))
    log = source(net)
    log = replace(
        log,
        object_types=(ObjectType("Item"), ObjectType("Order")),
        # An isolated object participates in no event and has no model place.
        e2o=tuple(link for link in log.e2o if link.object != "order"),
    )
    spec = OperationalImpactSpec(ObjectReplaySpec(("Item", "Order")), ("a",))
    result = assess_operational_impact(log, net, spec)
    assert result.status is ComputeStatus.COMPUTED
    order = result.value.scenario.typed[1]
    assert order.object_type == "Order"
    assert order.all_objects.observed_binding_object_ids == ("order",)
    assert order.prior.total_object_count == order.posterior.total_object_count == 0
    assert result.value.typed_deltas[1].prior.total_count == 0


def test_distinct_typed_populations_for_one_synchronized_event():
    net = ObjectCentricPetriNet(
        (
            TypedPlace("ip", "Item"),
            TypedPlace("iq", "Item"),
            TypedPlace("op", "Order"),
            TypedPlace("oq", "Order"),
        ),
        (Transition("join", "Join"),),
        tuple(
            ObjectArc(a, b)
            for a, b in (("ip", "join"), ("op", "join"), ("join", "iq"), ("join", "oq"))
        ),
        marking(("ip", "item"), ("op", "order")),
        marking(("iq", "item"), ("oq", "order")),
        (("item", "Item"), ("order", "Order")),
    )
    log = source(net, ("Join",))
    log = replace(log, object_types=(ObjectType("Item"), ObjectType("Order")))
    spec = OperationalImpactSpec(ObjectReplaySpec(("Item", "Order")), ("join",))
    value = assess_operational_impact(log, net, spec).value
    assert value.scenario.processed_event_ids == ("e0",)
    assert tuple(row.prior.total_count for row in value.typed_deltas) == (-1, -1)
    assert tuple(row.posterior.total_count for row in value.typed_deltas) == (1, 1)


def test_internal_snapshot_evidence_and_membership_cannot_be_relabelled():
    net = model()
    value = assess_operational_impact(source(net), net, request(0, 1)).value
    with pytest.raises(ValueError, match="equal cutoffs"):
        replace(
            value,
            scenario=replace(value.scenario, event_count=0, processed_event_ids=()),
        )
    fake = replace(value.scenario.typed[0], prior=value.scenario.typed[0].posterior)
    snapshot = replace(value.scenario, typed=(fake,))
    with pytest.raises(ValueError, match="regional populations"):
        replace(value, scenario=snapshot)
    unknown = assess_operational_impact(source(net, ("unknown",)), net, request()).value
    with pytest.raises(ValueError, match="unknown classification"):
        replace(unknown.scenario, evidence="repaired", inserted_token_count=1)
    with pytest.raises(ValueError, match="zero-event prefix"):
        replace(
            value.baseline,
            evidence="inferred_silent",
            binding_justified_marking=None,
            silent_binding_count=1,
        )


def test_envelope_redundant_fields_require_same_parent_cutoffs_and_coverage():
    net = model()
    result = assess_operational_impact(source(net), net, request())
    validate_operational_impact_result(result)
    with pytest.raises(ValueError, match="parent identity"):
        validate_operational_impact_result(
            replace(result, parent_computation_ids=("other",))
        )
    with pytest.raises(ValueError, match="cutoffs"):
        validate_operational_impact_result(
            replace(result, spec=replace(result.spec, parameters=request(0, 1)))
        )
    with pytest.raises(ValueError, match="changed transitions"):
        validate_operational_impact_result(
            replace(
                result,
                spec=replace(
                    result.spec,
                    parameters=replace(
                        result.spec.parameters, changed_transition_ids=("b",)
                    ),
                ),
            )
        )


def test_snapshots_cannot_disagree_about_where_one_partial_replay_stopped():
    net = model(silent=True)
    value = assess_operational_impact(
        source(net), net, request(silent_max_states=1)
    ).value
    early = replace(value.scenario, event_count=1, unprocessed_event_ids=("e0",))
    late = replace(
        value.scenario, processed_event_ids=("e0",), unprocessed_event_ids=("e1",)
    )
    with pytest.raises(ValueError, match="stop position"):
        replace(value, baseline=early, scenario=late)
