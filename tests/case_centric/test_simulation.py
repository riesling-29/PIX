"""Independent language and queue arithmetic oracles for native simulation."""

from collections import Counter
from dataclasses import FrozenInstanceError, dataclass
from itertools import permutations

import pytest

from pix.case_centric.simulation import (
    CaseArrival,
    DFGEnumerationSpec,
    DFGPlayoutSpec,
    DurationDistribution,
    FIFOInput,
    FIFOSpec,
    PlayoutSpec,
    RandomTreeSpec,
    SimulationDFG,
    enumerate_dfg,
    generate_process_tree,
    playout_dfg,
    playout_petri_net,
    playout_process_tree,
    simulate_fifo,
)
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus


def choice_net():
    return PetriNet(
        (Place("i"), Place("f")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("i", "a"), Arc("a", "f"), Arc("i", "b"), Arc("b", "f")),
        Marking((("i", 1),)),
        Marking((("f", 1),)),
    )


def accepted(result):
    return {run.activities for run in result.value.runs if run.status == "accepted"}


def test_exhaustive_xor_has_exact_finite_language():
    result = playout_petri_net(choice_net(), PlayoutSpec(mode="exhaustive"))
    assert result.status is ComputeStatus.COMPUTED
    assert accepted(result) == {("A",), ("B",)}
    assert result.value.complete
    assert all(
        run.terminal_marking == choice_net().final_marking for run in result.value.runs
    )


def test_sample_reproducible_and_transition_weights_affect_choices():
    spec = PlayoutSpec(seed=712, samples=30)
    first = playout_petri_net(choice_net(), spec)
    assert first == playout_petri_net(choice_net(), spec)
    other = playout_petri_net(
        choice_net(),
        PlayoutSpec(
            seed=712, samples=30, transition_weights=(("a", 1e100), ("b", 1.0))
        ),
    )
    assert all(run.activities == ("A",) for run in other.value.runs)
    assert first.computation_id != other.computation_id


def test_parallel_tree_oracle_all_permutations():
    tree = ProcessTree(
        "parallel", children=tuple(ProcessTree("activity", a) for a in "ABC")
    )
    result = playout_process_tree(tree, PlayoutSpec(mode="exhaustive"))
    assert result.status is ComputeStatus.COMPUTED
    assert accepted(result) == set(permutations("ABC"))
    assert result.value.backend == "process-tree-via-petri-net"


def test_silent_cycle_is_collapsed_without_losing_exit():
    net = PetriNet(
        (Place("i"), Place("f")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("i", "tau"), Arc("tau", "i"), Arc("i", "a"), Arc("a", "f")),
        Marking((("i", 1),)),
        Marking((("f", 1),)),
    )
    result = playout_petri_net(net, PlayoutSpec(mode="exhaustive", max_steps=1))
    assert accepted(result) == {("A",)}
    assert result.status is ComputeStatus.COMPUTED


def test_silent_dead_cycle_is_empty_language_not_accepted():
    net = PetriNet(
        (Place("i"), Place("f")),
        (Transition("tau"),),
        (Arc("i", "tau"), Arc("tau", "i")),
        Marking((("i", 1),)),
        Marking((("f", 1),)),
    )
    exhaustive = playout_petri_net(net, PlayoutSpec(mode="exhaustive"))
    assert exhaustive.status is ComputeStatus.COMPUTED
    assert accepted(exhaustive) == set()
    sampled = playout_petri_net(net, PlayoutSpec(samples=1, max_steps=3))
    assert sampled.status is ComputeStatus.PARTIAL
    assert sampled.value.runs[0].status == "step_limit"


@pytest.mark.parametrize(
    "bound,value,reason",
    [("max_visible_events", 0, "visible_limit"), ("max_states", 1, "state_limit")],
)
def test_exhaustive_limits_are_not_fitness_success(bound, value, reason):
    result = playout_petri_net(
        choice_net(), PlayoutSpec(mode="exhaustive", **{bound: value})
    )
    assert result.status is ComputeStatus.PARTIAL
    assert not accepted(result)
    assert reason in {issue.code for issue in result.issues}


def test_loop_finite_prefixes_and_unknown_suffix():
    tree = ProcessTree(
        "loop", children=(ProcessTree("activity", "A"), ProcessTree("activity", "B"))
    )
    result = playout_process_tree(
        tree, PlayoutSpec(mode="exhaustive", max_visible_events=5)
    )
    assert accepted(result) == {("A",), ("A", "B", "A"), ("A", "B", "A", "B", "A")}
    assert result.status is ComputeStatus.PARTIAL


def test_weighted_tokens_are_not_boolean_places():
    net = PetriNet(
        (Place("i"), Place("f")),
        (Transition("a", "A"),),
        (Arc("i", "a", 2), Arc("a", "f", 2)),
        Marking((("i", 2),)),
        Marking((("f", 2),)),
    )
    result = playout_petri_net(net, PlayoutSpec(samples=1))
    assert accepted(result) == {("A",)}
    assert result.value.runs[0].terminal_marking.tokens == (("f", 2),)


def test_exact_final_residual_token_is_deadlock():
    net = PetriNet(
        (Place("i"), Place("f")),
        (Transition("a", "A"),),
        (Arc("i", "a", 2), Arc("a", "f")),
        Marking((("i", 3),)),
        Marking((("f", 1),)),
    )
    result = playout_petri_net(net, PlayoutSpec(samples=1))
    assert result.value.runs[0].status == "deadlocked"
    assert result.value.runs[0].terminal_marking == Marking((("i", 1), ("f", 1)))


def test_same_label_transitions_do_not_multiply_language():
    net = choice_net()
    net = PetriNet(
        net.places,
        (Transition("a", "A"), Transition("b", "A")),
        net.arcs,
        net.initial_marking,
        net.final_marking,
    )
    result = playout_petri_net(net, PlayoutSpec(mode="exhaustive"))
    assert len(result.value.runs) == 1
    assert accepted(result) == {("A",)}


def test_identity_and_output_are_immutable():
    result = playout_petri_net(choice_net(), PlayoutSpec(samples=1))
    with pytest.raises(FrozenInstanceError):
        result.value.runs = ()


def test_dfg_frequency_routing_and_exact_performance():
    graph = SimulationDFG((("A", 2),), (("B", 2),), (("A", "B", 2),))
    spec = DFGPlayoutSpec(
        samples=2,
        activity_durations=(
            ("A", DurationDistribution(value=3)),
            ("B", DurationDistribution(value=4)),
        ),
        edge_delays=(("A", "B", DurationDistribution(value=5)),),
    )
    result = playout_dfg(graph, spec)
    assert result.status is ComputeStatus.COMPUTED
    assert [
        (e.activity, e.start_seconds, e.completion_seconds)
        for e in result.value.runs[0].events
    ] == [("A", 0, 3), ("B", 8, 12)]
    assert result == playout_dfg(graph, spec)


def test_dfg_end_probability_competes_with_loop_and_reports_cutoff():
    graph = SimulationDFG((("A", 1),), (("A", 1),), (("A", "A", 1),))
    result = playout_dfg(
        graph, DFGPlayoutSpec(seed=0, samples=20, max_visible_events=1)
    )
    assert {run.status for run in result.value.runs} == {"accepted", "visible_limit"}
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.timing_profile == "untimed"
    assert all(
        event.start_seconds is None and event.completion_seconds is None
        for run in result.value.runs
        for event in run.events
    )


def test_dfg_missing_durations_do_not_become_zero():
    graph = SimulationDFG((("A", 1),), (("B", 1),), (("A", "B", 1),))
    with pytest.raises(ValueError, match="every activity"):
        playout_dfg(
            graph,
            DFGPlayoutSpec(activity_durations=(("A", DurationDistribution(value=2)),)),
        )


def test_dfg_dead_end_is_not_success():
    graph = SimulationDFG((("A", 1),), (), ())
    result = playout_dfg(graph, DFGPlayoutSpec(samples=1))
    assert result.value.runs[0].status == "deadlocked"


def leaves(tree):
    return (
        (tree.activity,)
        if tree.operator == "activity"
        else sum((leaves(c) for c in tree.children), ())
    )


def test_random_tree_generation_has_declared_leaf_multiplicity_and_seed():
    spec = RandomTreeSpec(seed=9, activities=("A", "A", "B", "C", "D"))
    result = generate_process_tree(spec)
    assert result == generate_process_tree(spec)
    assert Counter(leaves(result.value)) == Counter(spec.activities)
    assert (
        playout_process_tree(result.value, PlayoutSpec(mode="exhaustive")).status
        is ComputeStatus.COMPUTED
    )


def test_fifo_hand_calculation_single_capacity():
    data = FIFOInput(
        (CaseArrival("c1", 0, ("A", "B")), CaseArrival("c2", 1, ("A", "B")))
    )
    spec = FIFOSpec(
        (("A", "worker"), ("B", "worker")),
        (("worker", 1),),
        (("A", DurationDistribution(value=3)), ("B", DurationDistribution(value=2))),
    )
    repetition = simulate_fifo(data, spec).value.repetitions[0]
    assert [
        (e.case_id, e.activity, e.ready_seconds, e.start_seconds, e.completion_seconds)
        for e in repetition.events
    ] == [
        ("c1", "A", 0, 0, 3),
        ("c2", "A", 1, 3, 6),
        ("c1", "B", 3, 6, 8),
        ("c2", "B", 6, 8, 10),
    ]
    assert repetition.total_waiting_seconds == 7
    assert repetition.makespan_seconds == 10
    assert repetition.case_completion_seconds == (("c1", 8), ("c2", 10))


def test_fifo_capacity_two_parallel_work_and_fifo_tie_order():
    data = FIFOInput(tuple(CaseArrival(f"c{i}", 0, ("A",)) for i in range(3)))
    spec = FIFOSpec((("A", "r"),), (("r", 2),), (("A", DurationDistribution(value=3)),))
    events = simulate_fifo(data, spec).value.repetitions[0].events
    assert [(e.case_id, e.resource_slot, e.start_seconds) for e in events] == [
        ("c0", 0, 0),
        ("c1", 1, 0),
        ("c2", 0, 3),
    ]


def test_fifo_downstream_ready_order_beats_original_arrival():
    data = FIFOInput(
        (CaseArrival("slow", 0, ("A", "C")), CaseArrival("fast", 1, ("B", "C")))
    )
    spec = FIFOSpec(
        (("A", "r1"), ("B", "r2"), ("C", "r3")),
        (("r1", 1), ("r2", 1), ("r3", 1)),
        (
            ("A", DurationDistribution(value=10)),
            ("B", DurationDistribution(value=1)),
            ("C", DurationDistribution(value=3)),
        ),
    )
    events = simulate_fifo(data, spec).value.repetitions[0].events
    assert [(e.case_id, e.start_seconds) for e in events if e.activity == "C"] == [
        ("fast", 2),
        ("slow", 10),
    ]


def test_fifo_monte_carlo_draws_reproduce_and_never_overlap_capacity_one():
    data = FIFOInput(tuple(CaseArrival(str(i), 0, ("A",)) for i in range(5)))
    spec = FIFOSpec(
        (("A", "r"),),
        (("r", 1),),
        (("A", DurationDistribution("exponential", 2)),),
        seed=92,
        repetitions=3,
    )
    result = simulate_fifo(data, spec)
    assert result == simulate_fifo(data, spec)
    assert len({r.makespan_seconds for r in result.value.repetitions}) == 3
    for repetition in result.value.repetitions:
        assert all(
            a.completion_seconds <= b.start_seconds
            for a, b in zip(repetition.events, repetition.events[1:])
        )


def test_empty_routes_complete_at_arrival():
    data = FIFOInput((CaseArrival("empty", 12, ()),))
    result = simulate_fifo(data, FIFOSpec((), (), ()))
    assert result.value.repetitions[0].case_completion_seconds == (("empty", 12),)
    assert result.value.repetitions[0].makespan_seconds == 0
    assert (
        simulate_fifo(FIFOInput(()), FIFOSpec((), (), ()))
        .value.repetitions[0]
        .makespan_seconds
        == 0
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: PlayoutSpec(seed=None),
        lambda: PlayoutSpec(max_states=0),
        lambda: PlayoutSpec(transition_weights=(("a", -1),)),
        lambda: DurationDistribution(value=float("nan")),
        lambda: DurationDistribution("exponential", 0),
        lambda: DurationDistribution("uniform", 2, 1),
        lambda: DurationDistribution("fixed", 2, 3),
        lambda: SimulationDFG((("A", 0),), (), ()),
        lambda: SimulationDFG((("A", 1), ("A", 2)), (), ()),
        lambda: RandomTreeSpec(activities=()),
        lambda: RandomTreeSpec(operator_weights=(("invalid", 1),)),
        lambda: FIFOSpec((("A", "r"),), (("r", 0),), ()),
        lambda: FIFOSpec((("A", "missing"),), (), ()),
        lambda: CaseArrival("c", -1, ()),
        lambda: FIFOInput((CaseArrival("c", 0, ()), CaseArrival("c", 1, ()))),
    ],
)
def test_invalid_specs_fail_explicitly(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()


def test_unknown_transition_and_missing_service_config_fail():
    with pytest.raises(ValueError, match="unknown"):
        playout_petri_net(
            choice_net(), PlayoutSpec(transition_weights=(("unknown", 1),))
        )
    with pytest.raises(ValueError, match="every observed"):
        simulate_fifo(FIFOInput((CaseArrival("c", 0, ("A",)),)), FIFOSpec((), (), ()))


def test_finite_large_weights_are_scaled_before_sum():
    result = playout_petri_net(
        choice_net(),
        PlayoutSpec(samples=10, transition_weights=(("a", 1e308), ("b", 1e308))),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.value.runs) == 10


def test_sample_state_budget_is_hard_bound():
    result = playout_petri_net(choice_net(), PlayoutSpec(samples=10, max_states=1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.explored_states == 1
    assert result.value.runs[0].status == "state_limit"


def test_overflow_is_explicit_instead_of_nonfinite_time_output():
    data = FIFOInput((CaseArrival("c", 1e308, ("A",)),))
    spec = FIFOSpec(
        (("A", "r"),), (("r", 1),), (("A", DurationDistribution(value=1e308)),)
    )
    with pytest.raises(ValueError, match="finite numeric range"):
        simulate_fifo(data, spec)


def test_acceptance_at_exact_sample_step_state_and_event_limits():
    result = playout_petri_net(
        choice_net(),
        PlayoutSpec(samples=1, max_visible_events=1, max_steps=1, max_states=2),
    )
    assert result.value.runs[0].status == "accepted"
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.explored_states == 2


def test_fifo_reentrant_case_does_not_jump_waiting_job():
    data = FIFOInput(
        (CaseArrival("first", 0, ("A", "B", "A")), CaseArrival("second", 1, ("A",)))
    )
    spec = FIFOSpec(
        (("A", "r1"), ("B", "r2")),
        (("r1", 1), ("r2", 1)),
        (("A", DurationDistribution(value=4)), ("B", DurationDistribution(value=1))),
    )
    events = simulate_fifo(data, spec).value.repetitions[0].events
    assert [
        (e.case_id, e.event_index, e.start_seconds, e.completion_seconds)
        for e in events
        if e.activity == "A"
    ] == [("first", 0, 0, 4), ("second", 0, 4, 8), ("first", 2, 8, 12)]


def test_aggregate_waiting_overflow_has_explicit_numeric_error():
    data = FIFOInput(tuple(CaseArrival(str(i), 0, ("A",)) for i in range(4)))
    spec = FIFOSpec(
        (("A", "r"),), (("r", 1),), (("A", DurationDistribution(value=4e307)),)
    )
    with pytest.raises(ValueError, match="finite numeric range"):
        simulate_fifo(data, spec)


def test_silent_diamond_merge_preserves_both_visible_suffixes():
    net = PetriNet(
        tuple(Place(p) for p in ("i", "l", "r", "m", "f")),
        tuple(Transition(t) for t in ("il", "ir", "lm", "rm"))
        + (Transition("a", "A"), Transition("b", "B")),
        tuple(
            Arc(a, b)
            for a, b in (
                ("i", "il"),
                ("il", "l"),
                ("i", "ir"),
                ("ir", "r"),
                ("l", "lm"),
                ("lm", "m"),
                ("r", "rm"),
                ("rm", "m"),
                ("m", "a"),
                ("a", "f"),
                ("m", "b"),
                ("b", "f"),
            )
        ),
        Marking((("i", 1),)),
        Marking((("f", 1),)),
    )
    result = playout_petri_net(net, PlayoutSpec(mode="exhaustive", max_steps=3))
    assert result.status is ComputeStatus.COMPUTED
    assert accepted(result) == {("A",), ("B",)}


def test_zero_weights_and_all_zero_uniform_fallback():
    result = playout_petri_net(
        choice_net(), PlayoutSpec(samples=20, transition_weights=(("a", 0), ("b", 1)))
    )
    assert accepted(result) == {("B",)}
    fallback = playout_petri_net(
        choice_net(),
        PlayoutSpec(seed=9, samples=20, transition_weights=(("a", 0), ("b", 0))),
    )
    assert accepted(fallback) == {("A",), ("B",)}


def test_dfg_enumeration_global_complete_probability_order():
    # A prefix is likely (.9), but its immediate end is rare (.09).
    # Complete B (.1) must precede complete A (.09), despite prefix priority.
    graph = SimulationDFG(
        (("A", 9), ("B", 1)), (("A", 1), ("B", 1), ("C", 1)), (("A", "C", 9),)
    )
    result = enumerate_dfg(graph)
    assert result.status is ComputeStatus.COMPUTED
    assert [variant.activities for variant in result.value.variants] == [
        ("A", "C"),
        ("B",),
        ("A",),
    ]
    assert [variant.probability for variant in result.value.variants] == pytest.approx(
        [0.81, 0.1, 0.09]
    )
    assert result.value.retained_probability == pytest.approx(1)


def test_dfg_enumeration_geometric_mass_is_not_renormalized():
    graph = SimulationDFG((("A", 1),), (("A", 1),), (("A", "A", 1),))
    result = enumerate_dfg(graph, DFGEnumerationSpec(max_occurrences_per_activity=2))
    assert result.status is ComputeStatus.PARTIAL
    assert [variant.activities for variant in result.value.variants] == [
        ("A",),
        ("A", "A"),
    ]
    assert result.value.retained_probability == pytest.approx(0.75)
    assert result.value.excluded_probability == pytest.approx(0.25)
    assert result.value.pending_probability == 0


def test_dfg_enumeration_top_k_keeps_pending_mass():
    graph = SimulationDFG((("A", 1),), (("A", 1),), (("A", "A", 1),))
    result = enumerate_dfg(
        graph, DFGEnumerationSpec(max_variants=2, max_occurrences_per_activity=100)
    )
    assert result.value.retained_probability == pytest.approx(0.75)
    assert (
        result.value.pending_probability + result.value.excluded_probability
        == pytest.approx(0.25)
    )
    assert "variant_limit" in {issue.code for issue in result.issues}


def test_dfg_enumeration_deadlock_mass_does_not_disappear():
    graph = SimulationDFG((("A", 1), ("B", 1)), (("A", 1),), ())
    result = enumerate_dfg(graph)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.retained_probability == pytest.approx(0.5)
    assert result.value.deadlock_probability == pytest.approx(0.5)


def test_dfg_enumeration_numeric_extreme_weights_log_normalization():
    graph = SimulationDFG((("A", 1e308), ("B", 1e308)), (("A", 1), ("B", 1)), ())
    result = enumerate_dfg(graph)
    assert result.value.retained_probability == pytest.approx(1)
    assert all(
        variant.probability == pytest.approx(0.5) for variant in result.value.variants
    )


def test_dfg_enumeration_exact_state_limit_and_identity():
    graph = SimulationDFG((("A", 1),), (("A", 1),), ())
    complete = enumerate_dfg(graph, DFGEnumerationSpec(max_states=2))
    partial = enumerate_dfg(graph, DFGEnumerationSpec(max_states=1))
    assert complete.status is ComputeStatus.COMPUTED
    assert partial.status is ComputeStatus.PARTIAL
    assert partial.value.pending_probability == 1
    assert complete.computation_id != partial.computation_id


def test_all_case_simulation_results_round_trip_exactly():
    from pix.results import result_from_json, result_json_bytes

    graph = SimulationDFG((("A", 1),), (("A", 1),), ())
    calculations = (
        playout_petri_net(
            choice_net(), PlayoutSpec(samples=1, transition_weights=(("a", 2),))
        ),
        playout_process_tree(ProcessTree("activity", "A"), PlayoutSpec(samples=1)),
        playout_dfg(graph, DFGPlayoutSpec(samples=1)),
        playout_dfg(
            graph,
            DFGPlayoutSpec(
                samples=1,
                activity_durations=(("A", DurationDistribution("uniform", 1, 2)),),
            ),
        ),
        enumerate_dfg(graph),
        enumerate_dfg(graph, DFGEnumerationSpec(max_states=1, target_probability=1)),
        generate_process_tree(
            RandomTreeSpec(activities=("A",), operator_weights=(("sequence", 1),))
        ),
        simulate_fifo(
            FIFOInput((CaseArrival("c", 0, ("A",)),)),
            FIFOSpec(
                (("A", "r"),), (("r", 1),), (("A", DurationDistribution(value=1)),)
            ),
        ),
    )
    for calculation in calculations:
        assert result_from_json(result_json_bytes(calculation)) == calculation


def test_unregistered_spec_subclass_is_rejected_before_result_creation():
    @dataclass(frozen=True, slots=True)
    class OtherSpec(PlayoutSpec):
        unregistered_field: str = "unknown"

    with pytest.raises(TypeError, match="PlayoutSpec"):
        playout_petri_net(choice_net(), OtherSpec(samples=1))
