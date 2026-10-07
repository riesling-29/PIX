"""Independent finite path oracles and binding/token evidence for OC playout."""

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from itertools import permutations

import pytest

from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.models import (
    CausalChannel,
    CausalFiring,
    CausalMarker,
    CausalMarkerGroup,
    ObjectCentricCausalNet,
)
from pix.object_centric.simulation import (
    CausalPlayoutSpec,
    ObjectPlayoutSpec,
    playout_causal_net,
    playout_ocpn,
)


def transfer(*, variable=False, objects=("a", "b"), multiplicity=1):
    return ObjectCentricPetriNet(
        (TypedPlace("in", "order"), TypedPlace("out", "order")),
        (Transition("move", "Move"),),
        (ObjectArc("in", "move", variable), ObjectArc("move", "out", variable)),
        ObjectMarking(
            tuple(
                ObjectToken("in", obj) for obj in objects for _ in range(multiplicity)
            )
        ),
        ObjectMarking(
            tuple(
                ObjectToken("out", obj) for obj in objects for _ in range(multiplicity)
            )
        ),
        tuple((obj, "order") for obj in objects),
    )


def exhaustive(**kwargs):
    return ObjectPlayoutSpec(mode="exhaustive", **kwargs)


def test_fixed_objects_independent_permutation_oracle():
    net = transfer(objects=("c", "a", "b"))
    result = playout_ocpn(net, exhaustive())
    actual = {
        tuple(step.binding.objects[0][1][0] for step in run.steps)
        for run in result.value.runs
    }
    assert actual == set(permutations(("a", "b", "c")))
    assert len(result.value.runs) == 6
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.enumeration_complete
    assert not result.value.sampling_complete
    assert all(run.outcome == "accepted" for run in result.value.runs)


def test_variable_cardinality_has_three_exact_identity_preserving_paths():
    net = transfer(variable=True)
    result = playout_ocpn(net, exhaustive())
    actual = {
        tuple(step.binding.objects[0][1] for step in run.steps)
        for run in result.value.runs
    }
    assert actual == {(("a",), ("b",)), (("b",), ("a",)), (("a", "b"),)}
    assert result.value.objects == (("a", "order"), ("b", "order"))
    for run in result.value.runs:
        assert run.final_marking == net.final_marking
        for index, step in enumerate(run.steps):
            assert step.index == index
            assert step.event_id == f"e{index:06d}"
            assert step.event_objects == tuple(
                (obj, "order") for obj in step.binding.objects[0][1]
            )


@pytest.mark.parametrize("variable", [False, True])
@pytest.mark.parametrize("multiplicity", [1, 2, 3])
def test_each_step_matches_independent_multiset_equation(variable, multiplicity):
    net = transfer(variable=variable, objects=("a",), multiplicity=multiplicity)
    result = playout_ocpn(net, exhaustive())
    assert result.value.accepted_count == 1
    assert len(result.value.runs[0].steps) == multiplicity
    for step in result.value.runs[0].steps:
        before = Counter(
            (token.place_id, token.object_id) for token in step.before.tokens
        )
        after = Counter(
            (token.place_id, token.object_id) for token in step.after.tokens
        )
        expected = before.copy()
        for object_id in step.binding.objects[0][1]:
            expected[("in", object_id)] -= 1
            expected[("out", object_id)] += 1
        assert +expected == after
        assert sum(before.values()) == sum(after.values())
    assert net.initial_marking.tokens == tuple(
        ObjectToken("in", "a") for _ in range(multiplicity)
    )


def test_joint_binding_synchronizes_both_object_types():
    net = ObjectCentricPetriNet(
        (
            TypedPlace("oi", "order"),
            TypedPlace("oo", "order"),
            TypedPlace("pi", "parcel"),
            TypedPlace("po", "parcel"),
        ),
        (Transition("ship", "Ship"),),
        (
            ObjectArc("oi", "ship"),
            ObjectArc("ship", "oo"),
            ObjectArc("pi", "ship"),
            ObjectArc("ship", "po"),
        ),
        ObjectMarking((ObjectToken("oi", "o"), ObjectToken("pi", "p"))),
        ObjectMarking((ObjectToken("oo", "o"), ObjectToken("po", "p"))),
        (("o", "order"), ("p", "parcel")),
    )
    run = playout_ocpn(net, exhaustive()).value.runs[0]
    assert run.outcome == "accepted"
    assert run.steps[0].binding.objects == (("order", ("o",)), ("parcel", ("p",)))
    assert run.steps[0].event_objects == (("o", "order"), ("p", "parcel"))
    blocked = replace(net, initial_marking=ObjectMarking((ObjectToken("oi", "o"),)))
    result = playout_ocpn(blocked, exhaustive())
    assert result.value.runs[0].outcome == "deadlock"
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.enumeration_complete


def test_seed_reproducibility_and_sampling_is_not_exhaustive_claim():
    net = transfer(variable=True)
    spec = ObjectPlayoutSpec(seed=517, samples=30)
    first = playout_ocpn(net, spec)
    assert first == playout_ocpn(net, spec)
    assert first.value.accepted_count == 30
    assert first.value.sampling_complete
    assert not first.value.enumeration_complete
    second = playout_ocpn(net, replace(spec, seed=919))
    assert first.computation_id != second.computation_id
    assert first.value.runs != second.value.runs


def test_binding_cap_exhaustive_reports_exact_omission_and_sampled_refuses_bias():
    net = transfer(variable=True)
    enumerated = playout_ocpn(net, exhaustive(max_bindings_per_marking=2))
    assert enumerated.status is ComputeStatus.PARTIAL
    assert enumerated.value.accepted_count == 2
    cutoffs = [run for run in enumerated.value.runs if run.outcome == "binding_limit"]
    assert len(cutoffs) == 1
    assert cutoffs[0].omitted_binding_count == 1
    sampled = playout_ocpn(
        net, ObjectPlayoutSpec(samples=1, max_bindings_per_marking=2)
    )
    assert sampled.status is ComputeStatus.PARTIAL
    assert sampled.value.runs[0].steps == ()
    assert sampled.value.runs[0].omitted_binding_count == 3
    assert not sampled.value.sampling_complete


def test_exact_binding_cap_does_not_report_incomplete():
    result = playout_ocpn(
        transfer(variable=True), exhaustive(max_bindings_per_marking=3)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.accepted_count == 3


def silent_exit_net():
    return ObjectCentricPetriNet(
        (TypedPlace("in", "order"), TypedPlace("out", "order")),
        (Transition("loop", None), Transition("exit", "Exit")),
        (
            ObjectArc("in", "loop"),
            ObjectArc("loop", "in"),
            ObjectArc("in", "exit"),
            ObjectArc("exit", "out"),
        ),
        ObjectMarking((ObjectToken("in", "a"),)),
        ObjectMarking((ObjectToken("out", "a"),)),
        (("a", "order"),),
    )


def test_silent_cycle_is_unfinished_and_other_paths_can_accept():
    result = playout_ocpn(silent_exit_net(), exhaustive(max_silent_steps=2))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.accepted_count == 3
    assert result.value.deadlock_count == 0
    assert result.value.cutoff_count == 1
    cutoff = next(run for run in result.value.runs if run.outcome == "silent_limit")
    assert len(cutoff.steps) == 2
    assert all(
        step.event_id is None and step.event_objects == () for step in cutoff.steps
    )
    assert cutoff.blocked_binding.transition_id == "loop"
    assert not result.value.enumeration_complete


def test_visible_bound_allows_silent_completion_and_exact_limit_acceptance():
    net = ObjectCentricPetriNet(
        (
            TypedPlace("in", "order"),
            TypedPlace("middle", "order"),
            TypedPlace("out", "order"),
        ),
        (Transition("a", "A"), Transition("tau", None)),
        (
            ObjectArc("in", "a"),
            ObjectArc("a", "middle"),
            ObjectArc("middle", "tau"),
            ObjectArc("tau", "out"),
        ),
        ObjectMarking((ObjectToken("in", "a"),)),
        ObjectMarking((ObjectToken("out", "a"),)),
        (("a", "order"),),
    )
    result = playout_ocpn(net, exhaustive(max_visible_events=1, max_steps=2))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.runs[0].visible_event_count == 1
    assert result.value.runs[0].steps[1].event_id is None
    zero = playout_ocpn(net, exhaustive(max_visible_events=0))
    assert zero.status is ComputeStatus.PARTIAL
    assert zero.value.runs[0].outcome == "visible_limit"
    assert zero.value.runs[0].steps == ()


@pytest.mark.parametrize(
    "bound,outcome", [("max_states", "state_limit"), ("max_steps", "step_limit")]
)
def test_global_and_path_budgets_are_explicit_unknown(bound, outcome):
    result = playout_ocpn(transfer(), exhaustive(**{bound: 1}))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.accepted_count == 0
    assert any(run.outcome == outcome for run in result.value.runs)
    assert not result.value.enumeration_complete
    if bound == "max_states":
        assert result.value.generated_states == 1


def test_sampling_global_cap_records_unstarted_samples():
    result = playout_ocpn(
        transfer(objects=("a",)), ObjectPlayoutSpec(samples=3, max_states=2)
    )
    assert result.value.accepted_count == 1
    assert result.value.unstarted_samples == 2
    assert result.value.generated_states == 2
    assert result.status is ComputeStatus.PARTIAL


def test_exact_acceptance_rejects_residual_object_tokens():
    net = transfer(objects=("a",))
    net = replace(net, final_marking=ObjectMarking())
    result = playout_ocpn(net, exhaustive())
    assert result.value.accepted_count == 0
    assert result.value.deadlock_count == 1
    assert result.value.runs[0].final_marking.tokens == (ObjectToken("out", "a"),)


def test_initial_final_is_empty_accepted_run_even_with_enabled_bindings():
    net = silent_exit_net()
    net = replace(net, final_marking=net.initial_marking)
    result = playout_ocpn(net, exhaustive(max_states=1))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.runs[0].steps == ()
    assert result.value.runs[0].outcome == "accepted"


def test_source_and_sink_change_tokens_without_creating_object_identities():
    source = ObjectCentricPetriNet(
        (TypedPlace("out", "order"),),
        (Transition("create_token", "Open"),),
        (ObjectArc("create_token", "out"),),
        ObjectMarking(),
        ObjectMarking((ObjectToken("out", "a"),)),
        (("a", "order"),),
    )
    source_result = playout_ocpn(source, exhaustive())
    assert source_result.value.accepted_count == 1
    step = source_result.value.runs[0].steps[0]
    assert step.before.tokens == ()
    assert step.after.tokens == (ObjectToken("out", "a"),)
    assert step.event_objects == (("a", "order"),)
    sink = ObjectCentricPetriNet(
        (TypedPlace("in", "order"),),
        (Transition("consume_token", "Close"),),
        (ObjectArc("in", "consume_token"),),
        ObjectMarking((ObjectToken("in", "a"),)),
        ObjectMarking(),
        (("a", "order"),),
    )
    sink_result = playout_ocpn(sink, exhaustive())
    assert sink_result.value.runs[0].final_marking == ObjectMarking()
    assert source_result.value.objects == sink_result.value.objects == (("a", "order"),)


def test_explicit_zero_cardinality_binding_is_not_missing_type_key():
    net = ObjectCentricPetriNet(
        (TypedPlace("in", "order"), TypedPlace("out", "order")),
        (Transition("move", "Move"),),
        (ObjectArc("in", "move", True, 0, 1), ObjectArc("move", "out", True, 0, 1)),
        ObjectMarking((ObjectToken("in", "a"),)),
        ObjectMarking((ObjectToken("out", "a"),)),
        (("a", "order"),),
    )
    result = playout_ocpn(net, exhaustive(max_visible_events=1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.accepted_count == 1
    empty = next(
        run
        for run in result.value.runs
        if run.steps and run.steps[0].binding.objects == (("order", ()),)
    )
    assert empty.steps[0].event_objects == ()
    assert empty.steps[0].event_id == "e000000"
    assert empty.steps[0].before == empty.steps[0].after
    assert empty.outcome == "visible_limit"


def test_silent_budget_resets_after_each_visible_event():
    net = ObjectCentricPetriNet(
        tuple(TypedPlace(place, "order") for place in ("p0", "p1", "p2", "p3")),
        (Transition("tau1", None), Transition("a", "A"), Transition("tau2", None)),
        (
            ObjectArc("p0", "tau1"),
            ObjectArc("tau1", "p1"),
            ObjectArc("p1", "a"),
            ObjectArc("a", "p2"),
            ObjectArc("p2", "tau2"),
            ObjectArc("tau2", "p3"),
        ),
        ObjectMarking((ObjectToken("p0", "a"),)),
        ObjectMarking((ObjectToken("p3", "a"),)),
        (("a", "order"),),
    )
    result = playout_ocpn(net, exhaustive(max_silent_steps=1))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.runs[0].outcome == "accepted"
    assert [step.event_id for step in result.value.runs[0].steps] == [
        None,
        "e000000",
        None,
    ]


@pytest.mark.parametrize(
    "field", ["samples", "max_states", "max_steps", "max_bindings_per_marking"]
)
def test_invalid_positive_bound(field):
    with pytest.raises(ValueError):
        ObjectPlayoutSpec(**{field: 0})


@pytest.mark.parametrize(
    "field",
    [
        "seed",
        "samples",
        "max_states",
        "max_steps",
        "max_visible_events",
        "max_silent_steps",
        "max_bindings_per_marking",
    ],
)
def test_boolean_is_not_numeric_parameter(field):
    with pytest.raises(TypeError):
        ObjectPlayoutSpec(**{field: True})


def test_invalid_mode_type_and_immutable_result():
    with pytest.raises(ValueError):
        ObjectPlayoutSpec(mode="stochastic_timed")
    with pytest.raises(TypeError):
        playout_ocpn(None)
    with pytest.raises(TypeError):
        playout_ocpn(transfer(), None)
    result = playout_ocpn(transfer(), exhaustive())
    with pytest.raises(FrozenInstanceError):
        result.value.generated_states = 1


def causal_transfer(*, variable=False, objects=("a", "b"), multiplicity=1):
    maximum = None if variable else 1
    return ObjectCentricCausalNet(
        (Transition("move", "Move"),),
        (
            CausalChannel("in", "order", None, "move"),
            CausalChannel("out", "order", "move", None),
        ),
        (CausalMarkerGroup("inputs", "move", (CausalMarker("in", 1, maximum),)),),
        (CausalMarkerGroup("outputs", "move", (CausalMarker("out", 1, maximum),)),),
        ObjectMarking(
            tuple(
                ObjectToken("in", obj) for obj in objects for _ in range(multiplicity)
            )
        ),
        ObjectMarking(
            tuple(
                ObjectToken("out", obj) for obj in objects for _ in range(multiplicity)
            )
        ),
        tuple((obj, "order") for obj in objects),
    )


@pytest.mark.parametrize("variable", [False, True])
def test_causal_genuine_concrete_binding_paths_match_hand_oracle(variable):
    result = playout_causal_net(
        causal_transfer(variable=variable), CausalPlayoutSpec(mode="exhaustive")
    )
    paths = {
        tuple(step.binding.consumed[0][1] for step in run.steps)
        for run in result.value.runs
    }
    expected = {(("a",), ("b",)), (("b",), ("a",))}
    if variable:
        expected.add((("a", "b"),))
    assert paths == expected
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.enumeration_complete
    assert result.operator_id == "pix.object_centric.playout_causal_net"
    assert result.source_digest.startswith("pix.causal-model.v1:")
    for run in result.value.runs:
        assert run.outcome == "accepted"
        for step in run.steps:
            assert isinstance(step.binding, CausalFiring)
            assert step.binding.input_binding_id == "inputs"
            assert step.binding.output_binding_id == "outputs"
            assert step.event_objects == tuple(
                (obj, "order") for obj in step.binding.consumed[0][1]
            )


def test_causal_alternative_groups_are_separate_firings_and_not_forced_AND():
    net = causal_transfer(objects=("a",))
    net = replace(
        net,
        channels=net.channels + (CausalChannel("other", "order", "move", None),),
        output_bindings=net.output_bindings
        + (CausalMarkerGroup("alternative", "move", (CausalMarker("other"),)),),
    )
    result = playout_causal_net(net, CausalPlayoutSpec(mode="exhaustive"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.accepted_count == result.value.deadlock_count == 1
    assert {run.steps[0].binding.output_binding_id for run in result.value.runs} == {
        "outputs",
        "alternative",
    }
    assert all(len(run.steps[0].binding.produced) == 1 for run in result.value.runs)


def test_causal_AND_markers_consume_both_channels_and_preserve_union_identity():
    net = ObjectCentricCausalNet(
        (Transition("join", "Join"),),
        (
            CausalChannel("left", "order", None, "join"),
            CausalChannel("right", "order", None, "join"),
            CausalChannel("out", "order", "join", None),
        ),
        (
            CausalMarkerGroup(
                "input_and",
                "join",
                (CausalMarker("left"), CausalMarker("right")),
                equal_channels=(("left", "right"),),
            ),
        ),
        (CausalMarkerGroup("output", "join", (CausalMarker("out"),)),),
        ObjectMarking((ObjectToken("left", "a"), ObjectToken("right", "a"))),
        ObjectMarking((ObjectToken("out", "a"),)),
        (("a", "order"),),
    )
    result = playout_causal_net(net, CausalPlayoutSpec(mode="exhaustive"))
    assert result.value.accepted_count == 1
    step = result.value.runs[0].steps[0]
    assert step.binding.consumed == (("left", ("a",)), ("right", ("a",)))
    assert step.binding.produced == (("out", ("a",)),)
    assert step.event_objects == (("a", "order"),)
    assert len(step.before.tokens) == 2 and len(step.after.tokens) == 1


def test_causal_each_firing_obeys_independent_obligation_multiset_equation():
    net = causal_transfer(objects=("a",), multiplicity=3)
    run = playout_causal_net(net, CausalPlayoutSpec(mode="exhaustive")).value.runs[0]
    assert run.outcome == "accepted"
    assert len(run.steps) == 3
    for step in run.steps:
        expected = Counter(
            (token.place_id, token.object_id) for token in step.before.tokens
        )
        for channel, ids in step.binding.consumed:
            for obj in ids:
                expected[(channel, obj)] -= 1
        for channel, ids in step.binding.produced:
            for obj in ids:
                expected[(channel, obj)] += 1
        assert +expected == Counter(
            (token.place_id, token.object_id) for token in step.after.tokens
        )


@pytest.mark.parametrize("mode", ["sampled", "exhaustive"])
def test_causal_candidate_limit_unknown_zero_is_not_deadlock(mode):
    result = playout_causal_net(
        causal_transfer(),
        CausalPlayoutSpec(
            mode=mode,
            samples=1,
            max_candidates_per_marking=1,
        ),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.deadlock_count == 0
    assert result.value.accepted_count == 0
    assert result.value.runs[0].outcome == "candidate_limit"
    assert result.value.runs[0].omitted_binding_count is None
    assert result.value.runs[0].steps == ()
    assert not result.value.enumeration_complete


def test_causal_known_binding_limit_reports_exact_omitted_count():
    result = playout_causal_net(
        causal_transfer(),
        CausalPlayoutSpec(
            mode="exhaustive",
            max_bindings_per_marking=1,
        ),
    )
    assert result.status is ComputeStatus.PARTIAL
    cutoff = next(run for run in result.value.runs if run.outcome == "binding_limit")
    assert cutoff.omitted_binding_count == 1
    assert result.value.accepted_count == 1


def test_causal_seeded_samples_and_model_type_boundary():
    net = causal_transfer(variable=True)
    spec = CausalPlayoutSpec(samples=12, seed=314)
    result = playout_causal_net(net, spec)
    assert result == playout_causal_net(net, spec)
    assert result.value.accepted_count == 12
    assert result.value.sampling_complete and not result.value.enumeration_complete
    with pytest.raises(TypeError):
        playout_causal_net(transfer())
    with pytest.raises(TypeError):
        playout_ocpn(net)
    with pytest.raises(TypeError):
        playout_causal_net(net, ObjectPlayoutSpec())
    with pytest.raises(TypeError):
        playout_ocpn(transfer(), CausalPlayoutSpec())


@pytest.mark.parametrize(
    "invalid,error", [(0, ValueError), (True, TypeError), (1.5, TypeError)]
)
def test_causal_candidate_budget_validation(invalid, error):
    with pytest.raises(error):
        CausalPlayoutSpec(max_candidates_per_marking=invalid)


@pytest.mark.parametrize("kind", ["ocpn", "causal", "ocpn_partial", "causal_partial"])
def test_registered_contract_json_roundtrip_retains_exact_firing_evidence(kind):
    """Exercise real application registry, encoder and decoder together."""
    import pix.results as persistence

    if kind == "ocpn":
        result = playout_ocpn(transfer(), exhaustive())
    elif kind == "ocpn_partial":
        result = playout_ocpn(silent_exit_net(), exhaustive(max_silent_steps=1))
    elif kind == "causal":
        result = playout_causal_net(
            causal_transfer(), CausalPlayoutSpec(mode="exhaustive")
        )
    else:
        result = playout_causal_net(
            causal_transfer(),
            CausalPlayoutSpec(
                mode="exhaustive",
                max_candidates_per_marking=1,
            ),
        )
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result
