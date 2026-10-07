"""Hand-worked firing and probability oracles for typed extended nets."""

from dataclasses import FrozenInstanceError, replace

import pytest

from pix.case_centric.extended_nets import (
    InhibitorArc,
    ParameterSource,
    ResetArc,
    ResetInhibitorNet,
    StochasticPetriNet,
    StochasticStep,
    StochasticTransition,
    extended_model_capabilities,
    fire_reset_inhibitor,
    reset_inhibitor_enabled_transitions,
    reset_inhibitor_is_enabled,
    sample_stochastic_step,
    stochastic_transition_probabilities,
)
from pix.case_centric.simulation import DurationDistribution, playout_petri_net
from pix.compute.model_semantics import fire, is_enabled
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition


def component(arcs=(), transitions=(Transition("t", "A"),)):
    return PetriNet(
        tuple(Place(p) for p in ("p", "q", "r")),
        transitions,
        arcs,
        Marking(),
        Marking((("q", 1),)),
    )


def marking(**counts):
    return Marking(tuple((p, n) for p, n in counts.items() if n))


@pytest.mark.parametrize("count", [0, 1, 7, 10**1000])
def test_reset_clears_arbitrary_finite_token_count_then_produces(count):
    model = ResetInhibitorNet(component((Arc("t", "p", 3),)), (ResetArc("p", "t"),))
    before = marking(p=count, r=9)
    assert reset_inhibitor_is_enabled(model, before, "t")
    assert reset_inhibitor_enabled_transitions(model, before) == ("t",)
    assert fire_reset_inhibitor(model, before, "t") == marking(p=3, r=9)
    assert before == marking(p=count, r=9)


@pytest.mark.parametrize(
    "count,enabled", [(0, True), (1, True), (2, False), (3, False)]
)
def test_inhibitor_threshold_uses_strict_old_marking_inequality(count, enabled):
    model = ResetInhibitorNet(
        component((Arc("t", "p", 3),)), inhibitor_arcs=(InhibitorArc("p", "t", 2),)
    )
    before = marking(p=count)
    assert reset_inhibitor_is_enabled(model, before, "t") is enabled
    if enabled:
        assert fire_reset_inhibitor(model, before, "t") == marking(p=count + 3)
    else:
        with pytest.raises(ValueError, match="not enabled"):
            fire_reset_inhibitor(model, before, "t")
    assert before == marking(p=count)


def test_default_inhibitor_is_a_zero_test_and_does_not_consume():
    model = ResetInhibitorNet(component(), inhibitor_arcs=(InhibitorArc("p", "t"),))
    assert reset_inhibitor_is_enabled(model, marking(q=8), "t")
    assert fire_reset_inhibitor(model, marking(q=8), "t") == marking(q=8)
    assert not reset_inhibitor_is_enabled(model, marking(p=1), "t")


def test_all_guards_check_old_marking_and_disabled_firing_is_atomic():
    model = ResetInhibitorNet(
        component((Arc("p", "t", 2), Arc("t", "p", 3), Arc("t", "q", 4))),
        (ResetArc("q", "t"),),
        (InhibitorArc("r", "t", 2),),
    )
    for before in (marking(p=1, q=12), marking(p=2, q=12, r=2)):
        saved = before.tokens
        assert not reset_inhibitor_is_enabled(model, before, "t")
        with pytest.raises(ValueError, match="not enabled"):
            fire_reset_inhibitor(model, before, "t")
        assert before.tokens == saved
    before = marking(p=2, q=12, r=1)
    assert fire_reset_inhibitor(model, before, "t") == marking(p=3, q=4, r=1)


def test_no_special_arcs_agrees_with_ordinary_weighted_self_loop():
    base = component((Arc("p", "t", 2), Arc("t", "p", 3)))
    extended = ResetInhibitorNet(base)
    for count in range(5):
        before = marking(p=count)
        assert reset_inhibitor_is_enabled(extended, before, "t") == is_enabled(
            base, before, "t"
        )
        if count >= 2:
            assert fire_reset_inhibitor(extended, before, "t") == fire(
                base, before, "t"
            )


def test_silent_and_repeated_label_transition_ids_remain_distinct():
    model = ResetInhibitorNet(
        component(
            transitions=(
                Transition("t2", "A"),
                Transition("tau"),
                Transition("t1", "A"),
            )
        ),
        inhibitor_arcs=(InhibitorArc("p", "t2"),),
    )
    assert reset_inhibitor_enabled_transitions(model, marking(p=1)) == ("t1", "tau")
    assert reset_inhibitor_enabled_transitions(model, Marking()) == ("t1", "t2", "tau")


@pytest.mark.parametrize("threshold", [0, -1, True, 1.5, float("inf"), "1"])
def test_invalid_inhibitor_threshold(threshold):
    with pytest.raises((TypeError, ValueError)):
        InhibitorArc("p", "t", threshold)


@pytest.mark.parametrize(
    "arc",
    [
        ResetArc("t", "p"),
        ResetArc("missing", "t"),
        ResetArc("p", "missing"),
        InhibitorArc("p", "q"),
    ],
)
def test_invalid_special_arc_endpoint(arc):
    args = {"reset_arcs" if isinstance(arc, ResetArc) else "inhibitor_arcs": (arc,)}
    with pytest.raises(ValueError, match="place to a transition"):
        ResetInhibitorNet(component(), **args)


@pytest.mark.parametrize(
    "reset,inhibitors",
    [
        ((ResetArc("p", "t"),) * 2, ()),
        ((), (InhibitorArc("p", "t"),) * 2),
        ((ResetArc("p", "t"),), (InhibitorArc("p", "t"),)),
    ],
)
def test_duplicate_and_conflicting_special_inputs_rejected(reset, inhibitors):
    with pytest.raises(ValueError, match="conflicting"):
        ResetInhibitorNet(component(), reset, inhibitors)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"reset_arcs": (ResetArc("p", "t"),)},
        {"inhibitor_arcs": (InhibitorArc("p", "t"),)},
    ],
)
def test_ordinary_and_special_input_conflict_is_rejected(kwargs):
    with pytest.raises(ValueError, match="conflicting"):
        ResetInhibitorNet(component((Arc("p", "t"),)), **kwargs)


def test_unknown_transition_and_marking_fail_explicitly():
    model = ResetInhibitorNet(component())
    for operation in (reset_inhibitor_is_enabled, fire_reset_inhibitor):
        with pytest.raises(ValueError, match="unknown transition"):
            operation(model, Marking(), "missing")
        with pytest.raises(ValueError, match="unknown place"):
            operation(model, marking(missing=1), "t")
        with pytest.raises(TypeError):
            operation(model, {}, "t")
    with pytest.raises(ValueError, match="unknown place"):
        reset_inhibitor_enabled_transitions(model, marking(missing=1))


def test_contracts_reject_mutable_inputs_and_are_frozen():
    with pytest.raises(TypeError):
        ResetInhibitorNet(component(), [ResetArc("p", "t")])
    with pytest.raises(TypeError):
        ResetArc("p", "t", weight=4)
    model = ResetInhibitorNet(component(), (ResetArc("r", "t"), ResetArc("p", "t")))
    assert model.reset_arcs == (ResetArc("p", "t"), ResetArc("r", "t"))
    with pytest.raises(FrozenInstanceError):
        model.reset_arcs = ()


def stochastic(weights=(1.0, 3.0, 100.0)):
    base = component(
        (Arc("p", "a"), Arc("a", "q"), Arc("p", "b"), Arc("b", "q"), Arc("r", "c")),
        (Transition("a", "Same"), Transition("b", "Same"), Transition("c")),
    )
    return StochasticPetriNet(
        base,
        tuple(
            StochasticTransition(t, w, DurationDistribution("fixed", duration))
            for t, w, duration in zip("abc", weights, (2, 8, 0))
        ),
    )


@pytest.mark.parametrize("count", [float("inf"), float("nan"), True, 1.5])
def test_infinite_and_noninteger_token_counts_are_not_markings(count):
    with pytest.raises(TypeError):
        Marking((("p", count),))


@pytest.mark.parametrize("arc_type", [ResetArc, InhibitorArc])
@pytest.mark.parametrize("identifier", ["", " ", "\ud800", 1, None])
def test_invalid_special_arc_identifiers(arc_type, identifier):
    with pytest.raises((TypeError, ValueError)):
        arc_type(identifier, "t")


@pytest.mark.parametrize("duration", [True, -1, float("inf"), float("nan"), 10**1000])
def test_invalid_sampled_step_contract(duration):
    with pytest.raises((TypeError, ValueError)):
        StochasticStep("a", "A", duration, Marking())


def test_local_probabilities_exact_oracle_excludes_disabled_high_weight():
    model = stochastic()
    assert stochastic_transition_probabilities(model, marking(p=1)) == (
        ("a", 0.25),
        ("b", 0.75),
    )
    assert stochastic_transition_probabilities(model, Marking()) == ()
    assert stochastic_transition_probabilities(model, marking(r=2)) == (("c", 1.0),)


def test_probabilities_scale_before_sum_to_avoid_overflow():
    assert stochastic_transition_probabilities(
        stochastic((1e308, 1e308, 1)), marking(p=1)
    ) == (("a", 0.5), ("b", 0.5))


def test_all_zero_enabled_mass_is_an_explicit_error_not_uniform_fallback():
    with pytest.raises(ValueError, match="no positive"):
        stochastic_transition_probabilities(stochastic((0, 0, 1)), marking(p=1))
    with pytest.raises(ValueError, match="no positive"):
        sample_stochastic_step(stochastic((0, 0, 1)), marking(p=1), seed=10)


def test_sampling_zero_weight_and_fixed_duration_are_deterministic():
    model = stochastic((0, 3, 100))
    before = marking(p=1)
    for seed in range(10):
        step = sample_stochastic_step(model, before, seed=seed)
        assert step.transition_id == "b"
        assert step.activity == "Same"
        assert step.duration_seconds == 8.0
        assert step.marking == marking(q=1)
    assert before == marking(p=1)


def test_seeded_sampling_and_canonical_input_order():
    model = stochastic()
    shuffled = replace(model, parameters=tuple(reversed(model.parameters)))
    first = sample_stochastic_step(model, marking(p=1), seed=192)
    assert first == sample_stochastic_step(model, marking(p=1), seed=192)
    assert first == sample_stochastic_step(shuffled, marking(p=1), seed=192)
    assert model == shuffled


def test_sampling_preserves_silent_identity_and_zero_duration():
    step = sample_stochastic_step(stochastic(), marking(r=1), seed=3)
    assert step.transition_id == "c"
    assert step.activity is None
    assert step.duration_seconds == 0.0
    assert step.marking == Marking()


@pytest.mark.parametrize(
    "kind,value,upper", [("uniform", 2, 4), ("exponential", 2, None)]
)
def test_distribution_semantics_and_reproducibility(kind, value, upper):
    model = stochastic((0, 1, 0))
    row = replace(
        model.parameters[1], duration=DurationDistribution(kind, value, upper)
    )
    model = replace(model, parameters=(model.parameters[0], row, model.parameters[2]))
    step = sample_stochastic_step(model, marking(p=1), seed=123)
    assert step == sample_stochastic_step(model, marking(p=1), seed=123)
    assert step.duration_seconds >= 0
    if kind == "uniform":
        assert 2 <= step.duration_seconds <= 4


def test_stochastic_deadlock_invalid_marking_and_invalid_seed():
    with pytest.raises(ValueError, match="no structurally enabled"):
        sample_stochastic_step(stochastic(), Marking(), seed=0)
    with pytest.raises(ValueError, match="unknown place"):
        stochastic_transition_probabilities(stochastic(), marking(missing=1))
    with pytest.raises(TypeError, match="seed"):
        sample_stochastic_step(stochastic(), marking(p=1), seed=True)


@pytest.mark.parametrize(
    "weight", [-1, float("nan"), float("inf"), -float("inf"), True, "1", None, 10**1000]
)
def test_invalid_stochastic_weights(weight):
    with pytest.raises((ValueError, TypeError)):
        StochasticTransition("a", weight, DurationDistribution())


@pytest.mark.parametrize(
    "rows", [(), ("unknown",), ("a", "a", "c"), ("a", "b"), ("a", "b", "c", "extra")]
)
def test_parameters_require_exact_unique_transition_coverage(rows):
    with pytest.raises(ValueError):
        StochasticPetriNet(
            stochastic().net,
            tuple(StochasticTransition(t, 1, DurationDistribution()) for t in rows),
        )


def test_stochastic_contract_inputs_and_source_origins_are_validated():
    with pytest.raises(TypeError):
        StochasticPetriNet(stochastic().net, list(stochastic().parameters))
    with pytest.raises(TypeError):
        StochasticTransition("a", 1, None)
    with pytest.raises(TypeError):
        StochasticTransition("a", 1, DurationDistribution(), weight_origin={})
    with pytest.raises(ValueError):
        ParameterSource("learned")
    with pytest.raises(ValueError):
        ParameterSource("observed", "ref")
    with pytest.raises(ValueError):
        ParameterSource("assumed", " ")
    row = StochasticTransition(
        "a",
        2,
        DurationDistribution(),
        ParameterSource("learned", "result:frequency-12"),
    )
    assert row.weight_origin.kind == "learned"
    assert row.duration_origin.kind == "assumed"
    with pytest.raises(FrozenInstanceError):
        row.weight = 10


@pytest.mark.parametrize(
    "model", [ResetInhibitorNet(component(), (ResetArc("p", "t"),)), stochastic()]
)
def test_ordinary_operations_do_not_silently_drop_extended_semantics(model):
    assert not isinstance(model, PetriNet)
    with pytest.raises(TypeError):
        is_enabled(model, Marking(), "t")
    with pytest.raises(TypeError):
        playout_petri_net(model)
    capability = extended_model_capabilities(model)
    assert "typed-persistence" in capability.supported_operations
    assert "alignments" in capability.unsupported_operations
    assert "woflan-soundness" in capability.unsupported_operations
    assert "complete-reachability" in capability.unsupported_operations


def test_no_unsupported_capability_inference():
    with pytest.raises(TypeError):
        extended_model_capabilities(component())
    assert (
        "timed-race" in extended_model_capabilities(stochastic()).unsupported_operations
    )


@pytest.mark.parametrize(
    "model",
    [
        ResetInhibitorNet(
            component(), (ResetArc("p", "t"),), (InhibitorArc("r", "t", 3),)
        ),
        stochastic(),
    ],
)
def test_typed_model_persistence_round_trip(model):
    # Root integration registers these models in PIX's explicit model whitelist.
    from pix.models import model_from_json, model_json_bytes

    restored = model_from_json(model_json_bytes(model)).model
    assert type(restored) is type(model)
    assert restored == model
    assert model_json_bytes(restored) == model_json_bytes(model)


def test_persistence_preserves_separate_parameter_origins_and_changes_identity():
    from pix.models import model_from_json, model_json_bytes

    model = stochastic()
    learned = replace(
        model.parameters[0],
        weight_origin=ParameterSource("learned", "fixture:frequency"),
    )
    changed = replace(model, parameters=(learned, *model.parameters[1:]))
    assert model_from_json(model_json_bytes(changed)).model == changed
    assert model_json_bytes(changed) != model_json_bytes(model)
    duration = replace(model.parameters[0], duration=DurationDistribution("fixed", 9))
    assert model_json_bytes(
        replace(model, parameters=(duration, *model.parameters[1:]))
    ) != model_json_bytes(model)
