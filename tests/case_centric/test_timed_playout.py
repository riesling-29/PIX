"""Hand-scheduled Petri-net oracles, reservation and censoring counterexamples."""

from dataclasses import FrozenInstanceError, replace

import pytest

from pix.case_centric.extended_nets import (
    ParameterSource,
    StochasticPetriNet,
    StochasticTransition,
)
from pix.case_centric.simulation import DurationDistribution
from pix.case_centric.timed_playout import (
    RESULT_SCHEMAS,
    TimedPlayoutSpec,
    playout_timed_petri_net,
)
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus


def model(places, transitions, arcs, initial, final, durations, weights=None):
    net = PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(key, label) for key, label in transitions),
        tuple(Arc(*arc) for arc in arcs),
        Marking(initial),
        Marking(final),
    )
    return StochasticPetriNet(
        net,
        tuple(
            StochasticTransition(
                key,
                (weights or {}).get(key, 1),
                duration
                if isinstance(duration, DurationDistribution)
                else DurationDistribution("fixed", duration),
            )
            for key, duration in durations.items()
        ),
    )


def sequential(a=2, b=3):
    return model(
        ("p0", "p1", "p2"),
        (("a", "A"), ("b", "B")),
        (("p0", "a"), ("a", "p1"), ("p1", "b"), ("b", "p2")),
        (("p0", 1),),
        (("p2", 1),),
        {"a": a, "b": b},
    )


def parallel(a=2, b=3):
    return model(
        ("s", "pa", "pb", "qa", "qb", "f"),
        (("fork", None), ("a", "A"), ("b", "B"), ("join", None)),
        (
            ("s", "fork"),
            ("fork", "pa"),
            ("fork", "pb"),
            ("pa", "a"),
            ("pb", "b"),
            ("a", "qa"),
            ("b", "qb"),
            ("qa", "join"),
            ("qb", "join"),
            ("join", "f"),
        ),
        (("s", 1),),
        (("f", 1),),
        {"fork": 0, "a": a, "b": b, "join": 0},
    )


def run(data, **kwargs):
    return playout_timed_petri_net(
        data, TimedPlayoutSpec(samples=1, **kwargs)
    ).value.runs[0]


def test_sequential_two_plus_three_is_five_seconds():
    result = playout_timed_petri_net(sequential(), TimedPlayoutSpec(samples=1))
    output = result.value.runs[0]
    assert result.status is ComputeStatus.COMPUTED
    assert [
        (e.activity, e.start_seconds, e.completion_seconds) for e in output.events
    ] == [
        ("A", 0, 2),
        ("B", 2, 5),
    ]
    assert output.completion_seconds == 5
    assert output.status == "accepted"
    assert output.terminal_marking == sequential().net.final_marking
    assert result.value.complete and result.value.accepted_run_count == 1


def test_and_parallel_makespan_three_not_five_and_join_waits_for_both():
    output = run(parallel())
    events = {event.transition_id: event for event in output.events}
    assert events["a"].start_seconds == events["b"].start_seconds == 0
    assert events["a"].completion_seconds == 2
    assert events["b"].completion_seconds == 3
    assert events["join"].start_seconds == 3
    assert output.completion_seconds == 3
    assert [e.activity for e in output.events].count(None) == 2


def test_tied_completions_are_all_available_to_join_before_dispatch():
    for seed in range(12):
        output = run(parallel(2, 2), seed=seed)
        assert output.status == "accepted"
        assert output.completion_seconds == 2
        assert output.events[-1].transition_id == "join"
        assert output.events[-1].start_seconds == 2


def test_completion_batch_exposes_combined_tokens_before_a_conflicting_consumer():
    data = model(
        ("pa", "pb", "q", "bad", "f"),
        (("a", "A"), ("b", "B"), ("c", "Consume one"), ("d", "Consume both")),
        (
            ("pa", "a"),
            ("pb", "b"),
            ("a", "q"),
            ("b", "q"),
            ("q", "c"),
            ("c", "bad"),
            ("q", "d", 2),
            ("d", "f"),
        ),
        (("pa", 1), ("pb", 1)),
        (("f", 1),),
        {"a": 2, "b": 2, "c": 0, "d": 0},
    )
    outputs = [run(data, seed=seed) for seed in range(12)]
    # Interleaving a dispatch between tied completions would always consume
    # the first token through c, preventing d in every sample.
    accepted = [output for output in outputs if output.status == "accepted"]
    assert accepted
    assert all(output.events[-1].transition_id == "d" for output in accepted)
    assert all(output.completion_seconds == 2 for output in accepted)


def test_nearby_float_times_are_not_merged_by_timestamp_rounding():
    output = run(parallel(0.1 + 0.2, 0.3))
    events = {event.transition_id: event for event in output.events}
    assert events["a"].completion_seconds > events["b"].completion_seconds
    assert output.completion_seconds == 0.1 + 0.2


def test_duplicate_activity_labels_preserve_transition_and_instance_identity():
    data = sequential()
    data = replace(
        data,
        net=replace(
            data.net,
            transitions=(
                Transition("a", "Same"),
                Transition("b", "Same"),
            ),
        ),
    )
    output = run(data)
    assert [e.activity for e in output.events] == ["Same", "Same"]
    assert [e.transition_id for e in output.events] == ["a", "b"]
    assert [e.execution_index for e in output.events] == [0, 1]


def test_mixed_accepted_and_start_limited_cohort_preserves_every_sample():
    data = model(
        ("s", "f"),
        (("a", "A"), ("b", "Retry")),
        (("s", "a"), ("s", "b"), ("a", "f"), ("b", "s")),
        (("s", 1),),
        (("f", 1),),
        {"a": 1, "b": 1},
    )
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=30, max_starts=1))
    assert result.status is ComputeStatus.PARTIAL
    assert len(result.value.runs) == 30
    assert {output.status for output in result.value.runs} == {
        "accepted",
        "start_limit",
    }
    assert result.value.accepted_run_count == sum(
        output.status == "accepted" for output in result.value.runs
    )
    assert 0 < result.value.accepted_run_count < 30


def test_conflicting_starts_reserve_token_exactly_once():
    data = model(
        ("s", "f"),
        (("a", "A"), ("b", "B")),
        (("s", "a"), ("s", "b"), ("a", "f"), ("b", "f")),
        (("s", 1),),
        (("f", 1),),
        {"a": 2, "b": 3},
    )
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=60, seed=9))
    assert len(result.value.runs) == 60
    assert result.value.accepted_run_count == 60
    assert all(len(r.events) == 1 for r in result.value.runs)
    assert {r.events[0].transition_id for r in result.value.runs} == {"a", "b"}


def test_dispatch_weights_are_not_duration_race_rates():
    data = model(
        ("s", "f"),
        (("a", "A"), ("b", "B")),
        (("s", "a"), ("s", "b"), ("a", "f"), ("b", "f")),
        (("s", 1),),
        (("f", 1),),
        {"a": 100, "b": 1},
        {"a": 1, "b": 0},
    )
    assert run(data).events[0].transition_id == "a"
    assert run(data).completion_seconds == 100


def test_one_transition_can_have_multiple_independent_running_instances():
    data = model(
        ("s", "f"),
        (("a", "A"),),
        (("s", "a"), ("a", "f")),
        (("s", 2),),
        (("f", 2),),
        {"a": 3},
    )
    output = run(data)
    assert len(output.events) == 2
    assert [e.start_seconds for e in output.events] == [0, 0]
    assert output.completion_seconds == 3


def test_weighted_incidence_consumes_and_produces_multiplicities():
    data = model(
        ("s", "f"),
        (("a", "A"),),
        (("s", "a", 2), ("a", "f", 3)),
        (("s", 4),),
        (("f", 6),),
        {"a": 3},
    )
    output = run(data)
    assert len(output.events) == 2
    assert output.terminal_marking == Marking((("f", 6),))
    assert output.completion_seconds == 3


def test_zero_time_cycle_is_bounded_with_all_requested_runs_preserved():
    data = model(
        ("s", "unreachable"),
        (("a", None),),
        (("s", "a"), ("a", "s")),
        (("s", 1),),
        (("unreachable", 1),),
        {"a": 0},
    )
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=4, max_starts=7))
    assert result.status is ComputeStatus.PARTIAL
    assert not result.value.complete
    assert len(result.value.runs) == 4
    for output in result.value.runs:
        assert output.status == "start_limit"
        assert output.observation_end_seconds == 0
        assert len(output.events) == 7
        assert all(e.completion_seconds == 0 for e in output.events)
        assert output.completion_seconds is None
        assert output.in_flight_execution_indices == ()


def test_unreachable_final_is_computed_deadlock_not_acceptance():
    data = model(("s", "f"), (), (), (("s", 1),), (("f", 1),), {})
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=3))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.complete
    assert result.value.accepted_run_count == 0
    assert [r.status for r in result.value.runs] == ["deadlocked"] * 3
    assert all(r.completion_seconds is None for r in result.value.runs)


def test_final_marking_with_inflight_instance_is_not_accepted():
    data = model(
        ("pa", "pb", "f", "extra"),
        (("a", "A"), ("b", "B")),
        (("pa", "a"), ("pb", "b"), ("a", "f"), ("b", "extra")),
        (("pa", 1), ("pb", 1)),
        (("f", 1),),
        {"a": 2, "b": 3},
    )
    output = run(data)
    assert output.status == "deadlocked"
    assert output.observation_end_seconds == 3
    assert output.completion_seconds is None
    assert output.terminal_marking == Marking((("f", 1), ("extra", 1)))


def test_horizon_keeps_reserved_inputs_and_scheduled_unfinished_output():
    result = playout_timed_petri_net(
        sequential(), TimedPlayoutSpec(samples=2, horizon_seconds=3)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert len(result.value.runs) == 2
    for output in result.value.runs:
        assert output.status == "horizon_limit"
        assert output.observation_end_seconds == 3
        assert output.terminal_marking == Marking()
        assert output.events[0].completion_seconds == 2
        assert output.events[1].start_seconds == 2
        assert output.events[1].planned_completion_seconds == 5
        assert output.events[1].completion_seconds is None
        assert output.in_flight_execution_indices == (1,)


def test_completion_at_horizon_is_included_but_new_start_is_not():
    output = run(sequential(), horizon_seconds=2)
    assert len(output.events) == 1
    assert output.events[0].completion_seconds == 2
    assert output.terminal_marking == Marking((("p1", 1),))
    assert output.status == "horizon_limit"
    assert run(sequential(), horizon_seconds=5).status == "accepted"


def test_zero_horizon_observes_initial_state_and_accepting_initial_stops():
    output = run(sequential(0, 0), horizon_seconds=0)
    assert output.status == "horizon_limit"
    assert output.events == ()
    assert output.terminal_marking == sequential().net.initial_marking
    empty = model(("p",), (), (), (("p", 1),), (("p", 1),), {})
    assert run(empty, horizon_seconds=0).completion_seconds == 0


def test_start_limit_drains_running_instance_and_accepts_if_final():
    output = run(sequential(), max_starts=1)
    assert output.status == "start_limit"
    assert output.events[0].completion_seconds == 2
    assert output.observation_end_seconds == 2
    assert output.in_flight_execution_indices == ()
    assert run(sequential(), max_starts=2).status == "accepted"


def test_horizon_still_censors_draining_start_limited_work():
    output = run(sequential(), max_starts=1, horizon_seconds=1)
    assert output.status == "horizon_limit"
    assert output.in_flight_execution_indices == (0,)
    assert output.events[0].completion_seconds is None


def test_source_transition_without_inputs_cannot_run_without_bound():
    data = model(
        ("f",),
        (("a", "A"),),
        (("a", "f"),),
        (),
        (("f", 1),),
        {"a": 2},
    )
    output = run(data, max_starts=5)
    assert len(output.events) == 5
    assert output.status == "start_limit"
    assert output.observation_end_seconds == 2
    assert output.terminal_marking == Marking((("f", 5),))


def test_zero_enabled_weight_has_explicit_outcome_not_uniform_fallback():
    data = sequential()
    data = replace(
        data, parameters=tuple(replace(p, weight=0) for p in data.parameters)
    )
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=2))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.accepted_run_count == 0
    assert [r.status for r in result.value.runs] == ["weight_deadlock"] * 2
    assert result.issues[0].code == "timed_playout_zero_enabled_weight"
    assert all(not r.events for r in result.value.runs)


def test_zero_weight_waits_for_other_running_work_before_blocked_outcome():
    data = parallel()
    data = replace(
        data,
        parameters=tuple(
            replace(p, weight=0) if p.transition_id == "b" else p
            for p in data.parameters
        ),
    )
    output = run(data)
    assert output.status == "weight_deadlock"
    assert output.observation_end_seconds == 2
    assert output.in_flight_execution_indices == ()
    assert output.events[-1].completion_seconds == 2


def test_seed_and_sample_prefix_reproducibility_with_continuous_durations():
    data = sequential(
        DurationDistribution("uniform", 1, 7), DurationDistribution("exponential", 2)
    )
    spec = TimedPlayoutSpec(seed=42, samples=3)
    first = playout_timed_petri_net(data, spec)
    assert first == playout_timed_petri_net(data, spec)
    more = playout_timed_petri_net(data, replace(spec, samples=5))
    assert first.value.runs == more.value.runs[:3]
    assert (
        first.value.runs
        != playout_timed_petri_net(data, replace(spec, seed=43)).value.runs
    )
    assert first.computation_id != more.computation_id


def test_declared_origins_are_preserved_and_change_source_identity():
    data = sequential()
    changed = replace(
        data,
        parameters=(
            replace(
                data.parameters[0],
                duration_origin=ParameterSource("learned", "fit:123"),
            ),
            data.parameters[1],
        ),
    )
    a = playout_timed_petri_net(data, TimedPlayoutSpec(samples=1))
    b = playout_timed_petri_net(changed, TimedPlayoutSpec(samples=1))
    assert b.value.parameters[0].duration_origin == ParameterSource(
        "learned", "fit:123"
    )
    assert a.value.runs == b.value.runs
    assert a.source_digest != b.source_digest
    assert a.computation_id != b.computation_id


def test_finite_weights_do_not_overflow_during_dispatch():
    data = parallel()
    data = replace(
        data, parameters=tuple(replace(p, weight=1e308) for p in data.parameters)
    )
    assert run(data).completion_seconds == 3


@pytest.mark.parametrize("durations", [(1e308, 1e308), (1e308, 1)])
def test_nonrepresentable_clock_progress_is_rejected(durations):
    with pytest.raises(ValueError, match="finite range|clock resolution"):
        run(sequential(*durations))


def test_input_and_outputs_are_immutable_and_input_unchanged():
    data = sequential()
    result = playout_timed_petri_net(data, TimedPlayoutSpec(samples=1))
    assert data == sequential()
    with pytest.raises(FrozenInstanceError):
        result.value.runs[0].status = "accepted"
    with pytest.raises(FrozenInstanceError):
        result.spec.seed = 5


@pytest.mark.parametrize("horizon", [None, 5, 2.5])
def test_typed_result_roundtrip_retains_schedule_and_parameter_origins(
    horizon, monkeypatch
):
    import pix.results as persistence

    monkeypatch.setattr(persistence, "_schemas", lambda: RESULT_SCHEMAS)
    result = playout_timed_petri_net(
        sequential(), TimedPlayoutSpec(samples=2, horizon_seconds=horizon)
    )
    encoded = persistence.result_json_bytes(result)
    restored = persistence.result_from_json(encoded)
    assert restored == result
    assert persistence.result_json_bytes(restored) == encoded


@pytest.mark.parametrize(
    "options",
    [
        {"seed": True},
        {"seed": 1.5},
        {"samples": 0},
        {"samples": True},
        {"max_starts": 0},
        {"max_starts": 1.5},
        {"horizon_seconds": True},
        {"horizon_seconds": float("nan")},
        {"horizon_seconds": float("inf")},
        {"horizon_seconds": -1},
        {"horizon_seconds": "2"},
        {"horizon_seconds": 10**1000},
    ],
)
def test_invalid_spec_rejected(options):
    with pytest.raises((TypeError, ValueError)):
        TimedPlayoutSpec(**options)


def test_ordinary_net_is_not_implicitly_assigned_stochastic_parameters():
    with pytest.raises(TypeError, match="StochasticPetriNet"):
        playout_timed_petri_net(sequential().net)
