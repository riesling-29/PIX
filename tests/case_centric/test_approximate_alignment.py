"""Approximation strategies require executable witnesses and honest bounds."""

from dataclasses import replace
from itertools import product

import pytest

from pix.case_centric.approximate_alignment import (
    FixedHorizonSpec,
    SlidingWindowSpec,
    TandemRepeatSpec,
    align_fixed_horizon,
    align_sliding_window,
    align_tandem_repeats,
)
from pix.compute.conformance import align_traces
from pix.compute.model_semantics import enabled_transitions, fire
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"{i}-{j}", (CaseAttribute("concept:name", "string", label),)
                    )
                    for j, label in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def net_from_edges(places, transitions, edges, initial="p0", final="f"):
    return PetriNet(
        tuple(Place(place) for place in places),
        tuple(Transition(identity, label) for identity, label in transitions),
        tuple(Arc(*edge) for edge in edges),
        Marking(((initial, 1),)),
        Marking(((final, 1),)),
    )


def sequence_net(*activities):
    return net_from_edges(
        tuple(f"p{i}" for i in range(len(activities) + 1)),
        tuple((f"t{i}", label) for i, label in enumerate(activities)),
        tuple(
            edge
            for i in range(len(activities))
            for edge in ((f"p{i}", f"t{i}"), (f"t{i}", f"p{i + 1}"))
        ),
        final=f"p{len(activities)}",
    )


def loop_net():
    return net_from_edges(
        ("p0", "p1"),
        (("a", "A"), ("b", "B")),
        (("p0", "a"), ("a", "p1"), ("p1", "b"), ("b", "p0")),
        final="p0",
    )


def branching_net(dead_bad_branch=False):
    transitions = [("a_bad", "A"), ("a_good", "A"), ("b_bad", "B"), ("b_good", "B")]
    edges = [
        ("p0", "a_bad"),
        ("a_bad", "bad"),
        ("bad", "b_bad"),
        ("b_bad", "after_bad"),
        ("p0", "a_good"),
        ("a_good", "good"),
        ("good", "b_good"),
        ("b_good", "f"),
    ]
    if not dead_bad_branch:
        transitions.append(("x", "X"))
        edges.extend((("after_bad", "x"), ("x", "f")))
    return net_from_edges(("p0", "bad", "good", "after_bad", "f"), transitions, edges)


def assert_executable(result, source, model, costs):
    """Independent full replay validates identities, snapshots and cost profile."""
    transitions = {transition.id: transition for transition in model.transitions}
    assert result.cost_upper_bound is not None
    marking, observed, summed = model.initial_marking, [], 0
    for move in result.moves:
        assert move.before_marking == marking.tokens
        if move.event_id is not None:
            observed.append((move.event_id, move.activity))
        if move.kind == "log":
            assert move.transition_id is None
            expected = costs.log_move_cost
        else:
            assert move.transition_id in enabled_transitions(model, marking)
            transition = transitions[move.transition_id]
            assert transition.activity == move.activity
            if move.kind == "synchronous":
                assert move.event_id is not None
                expected = costs.synchronous_move_cost
            elif move.kind == "silent":
                assert move.activity is None and move.event_id is None
                expected = costs.silent_move_cost
            else:
                assert move.kind == "model" and move.event_id is None
                expected = costs.model_move_cost
            marking = fire(model, marking, move.transition_id)
        assert move.after_marking == marking.tokens
        assert move.cost == expected
        summed += expected
    assert observed == [(event.event_id, event.activity) for event in source.events]
    assert marking == model.final_marking
    assert summed == result.cost_upper_bound


def test_tandem_actual_compression_and_model_loop_expansion():
    data = log("ABABABAB")
    result = align_tandem_repeats(data, loop_net())
    trace = result.value.traces[0]
    assert result.status is ComputeStatus.COMPUTED
    assert trace.original_trace_length == 8
    assert trace.reduced_trace_length == 4
    assert len(trace.repeat_reductions) == 1
    repeat = trace.repeat_reductions[0]
    assert repeat.period == ("A", "B")
    assert repeat.repetitions == 4
    assert repeat.expansion == "model_loop"
    assert trace.status == "optimal"
    assert trace.certificate == "zero_cost"
    assert trace.cost_upper_bound == 0
    assert_executable(
        trace, case_traces(data).value.traces[0], loop_net(), AlignmentSpec()
    )


def test_tandem_nonloop_expands_as_log_moves_and_can_be_suboptimal():
    data, model = log("AAAA"), sequence_net("A", "A", "A", "A")
    result = align_tandem_repeats(data, model, TandemRepeatSpec(verify_exact=True))
    trace = result.value.traces[0]
    assert trace.repeat_reductions[0].expansion == "log_moves"
    assert trace.reduced_trace_length == 2
    assert trace.cost_upper_bound == 4
    assert trace.certified_optimal_cost == 0
    assert trace.status == "approximate"
    assert trace.certificate == "none"
    assert trace.exact_verification_status == "optimal"
    assert not trace.fallback_used
    assert_executable(trace, case_traces(data).value.traces[0], model, AlignmentSpec())


def test_tandem_multiple_nonoverlapping_runs_preserve_original_event_order():
    data, model = log("AAABBBB"), sequence_net("A", "B")
    result = align_tandem_repeats(data, model).value.traces[0]
    assert result.reduced_trace_length == 4
    assert tuple(item.period for item in result.repeat_reductions) == (("A",), ("B",))
    assert tuple(item.repetitions for item in result.repeat_reductions) == (3, 4)
    assert_executable(result, case_traces(data).value.traces[0], model, AlignmentSpec())


def test_tandem_no_repeats_is_explicit_whole_trace_exact_search():
    result = align_tandem_repeats(log("AXB"), sequence_net("A", "B")).value.traces[0]
    assert result.repeat_reductions == ()
    assert result.certificate == "whole_trace_search"
    assert result.status == "optimal"
    assert result.cost_upper_bound == 1


def test_tandem_silent_closing_step_not_in_copy_can_make_approximation_suboptimal():
    model = net_from_edges(
        ("p0", "q"),
        (("a", "A"), ("tau", None)),
        (("p0", "a"), ("a", "q"), ("q", "tau"), ("tau", "p0")),
        final="p0",
    )
    data = log("AAA")
    result = align_tandem_repeats(
        data, model, TandemRepeatSpec(verify_exact=True)
    ).value.traces[0]
    assert result.repeat_reductions[0].expansion == "log_moves"
    assert result.cost_upper_bound == 1
    assert result.certified_optimal_cost == 0
    assert result.status == "approximate"
    assert_executable(result, case_traces(data).value.traces[0], model, AlignmentSpec())


def test_tandem_period_cap_changes_reduction_but_not_validity():
    data = log("ABCABCABC")
    model = sequence_net("A", "B", "C")
    capped = align_tandem_repeats(
        data, model, TandemRepeatSpec(max_period=2)
    ).value.traces[0]
    reduced = align_tandem_repeats(
        data, model, TandemRepeatSpec(max_period=3)
    ).value.traces[0]
    assert capped.repeat_reductions == ()
    assert reduced.repeat_reductions[0].period == ("A", "B", "C")
    assert_executable(capped, case_traces(data).value.traces[0], model, AlignmentSpec())
    assert_executable(
        reduced, case_traces(data).value.traces[0], model, AlignmentSpec()
    )


def test_sliding_window_top_one_has_explicit_suboptimal_counterexample():
    model, data = branching_net(), log("AB")
    spec = SlidingWindowSpec(window_size=1, max_candidates=1, verify_exact=True)
    trace = align_sliding_window(data, model, spec).value.traces[0]
    assert len(trace.windows) == 2
    assert trace.windows[0].retained[0].marking == Marking((("bad", 1),))
    assert trace.windows[0].retained[0].future_lower_bound == 0
    assert trace.cost_upper_bound == 1
    assert trace.certified_optimal_cost == 0
    assert trace.status == "approximate"
    assert trace.certificate == "none"
    assert not trace.fallback_used
    assert_executable(trace, case_traces(data).value.traces[0], model, spec.alignment)


def test_sliding_larger_beam_preserves_better_duplicate_label_branch():
    spec = SlidingWindowSpec(window_size=1, max_candidates=2)
    trace = align_sliding_window(log("AB"), branching_net(), spec).value.traces[0]
    assert len(trace.windows[0].retained) == 2
    assert trace.cost_upper_bound == 0
    assert trace.status == "optimal"
    assert trace.certificate == "zero_cost"


def test_structural_future_bound_avoids_branch_without_required_future_label():
    model = net_from_edges(
        ("p0", "bad", "good", "f"),
        (("a_bad", "A"), ("a_good", "A"), ("x", "X"), ("b", "B")),
        (
            ("p0", "a_bad"),
            ("a_bad", "bad"),
            ("bad", "x"),
            ("x", "f"),
            ("p0", "a_good"),
            ("a_good", "good"),
            ("good", "b"),
            ("b", "f"),
        ),
    )
    result = align_sliding_window(
        log("AB"), model, SlidingWindowSpec(window_size=1, max_candidates=1)
    ).value.traces[0]
    assert result.windows[0].retained[0].marking == Marking((("good", 1),))
    assert result.cost_upper_bound == 0


def test_sliding_dead_beam_is_not_global_unreachability_and_fallback_is_explicit():
    model = branching_net(dead_bad_branch=True)
    spec = SlidingWindowSpec(window_size=1, max_candidates=1, fallback_to_exact=False)
    incomplete = align_sliding_window(log("AB"), model, spec)
    assert incomplete.status is ComputeStatus.PARTIAL
    assert incomplete.value.traces[0].status == "unavailable"
    assert incomplete.value.traces[0].fallback_reason == "retained_window_dead_end"
    assert incomplete.value.traces[0].cost_upper_bound is None
    rescued = align_sliding_window(
        log("AB"), model, replace(spec, fallback_to_exact=True)
    ).value.traces[0]
    assert rescued.fallback_used
    assert rescued.certificate == "exact_fallback"
    assert rescued.cost_upper_bound == 0
    assert rescued.fallback_settled_states > 0


def test_sliding_local_and_total_budgets_do_not_fake_complete_witness():
    model = sequence_net("A", "B")
    spec = SlidingWindowSpec(window_size=1, max_total_states=1, fallback_to_exact=False)
    result = align_sliding_window(log("AB"), model, spec)
    assert result.status is ComputeStatus.PARTIAL
    trace = result.value.traces[0]
    assert trace.status == "search_limit"
    assert trace.windows[0].local_search_limit
    assert trace.strategy_settled_states == 1
    assert trace.cost_upper_bound is None
    assert trace.moves == ()


@pytest.mark.parametrize(
    "algorithm,spec",
    [
        (align_tandem_repeats, TandemRepeatSpec()),
        (align_sliding_window, SlidingWindowSpec(window_size=1, max_candidates=2)),
    ],
)
def test_small_word_upper_bounds_and_witnesses_against_independent_exact_kernel(
    algorithm, spec
):
    words = tuple(word for length in range(5) for word in product("AB", repeat=length))
    data = log(*words)
    for model in (sequence_net("A", "B"), loop_net(), branching_net()):
        projected = case_traces(data)
        approximate = algorithm(projected, model, spec)
        exact = align_traces(projected, model, spec.alignment)
        assert approximate.status is ComputeStatus.COMPUTED
        for source, candidate, optimum in zip(
            projected.value.traces, approximate.value.traces, exact.value.alignments
        ):
            assert optimum.status == "optimal"
            assert candidate.cost_upper_bound >= optimum.cost
            assert candidate.certified_lower_bound <= optimum.cost
            if candidate.status == "optimal":
                assert candidate.cost_upper_bound == optimum.cost
            assert_executable(candidate, source, model, spec.alignment)


@pytest.mark.parametrize(
    "costs", [AlignmentSpec(3, 2, 1, 1), AlignmentSpec(0, 0, 0, 0)]
)
def test_custom_scalar_costs_and_silent_moves_are_preserved(costs):
    model, data = sequence_net(None, "A", None, "B", None), log("AAAB")
    for result in (
        align_tandem_repeats(data, model, TandemRepeatSpec(alignment=costs)),
        align_sliding_window(
            data, model, SlidingWindowSpec(alignment=costs, window_size=2)
        ),
    ):
        trace = result.value.traces[0]
        assert_executable(trace, case_traces(data).value.traces[0], model, costs)
        exact = align_traces(case_traces(data), model, costs).value.alignments[0]
        assert trace.cost_upper_bound >= exact.cost


@pytest.mark.parametrize(
    "algorithm,spec",
    [
        (align_tandem_repeats, TandemRepeatSpec()),
        (align_sliding_window, SlidingWindowSpec(window_size=1)),
    ],
)
def test_empty_log_vs_empty_trace_and_unreachable_model(algorithm, spec):
    model = sequence_net("A")
    empty_log = algorithm(log(), model, spec)
    assert empty_log.value.traces == ()
    assert empty_log.value.whole_population_cost_upper_bound == 0
    empty_trace = algorithm(log(""), model, spec).value.traces[0]
    assert empty_trace.cost_upper_bound == 1
    assert empty_trace.status == "optimal"
    dead = net_from_edges(("p0", "f"), (), ())
    unreachable = algorithm(log("A"), dead, spec)
    assert unreachable.status is ComputeStatus.PARTIAL
    assert unreachable.value.traces[0].status == "unreachable"
    assert unreachable.value.traces[0].cost_upper_bound is None


def test_exact_verification_limit_preserves_valid_approximation_upper_bound():
    model, data = sequence_net("A", "B", "C"), log("ABC")
    result = align_sliding_window(
        data,
        model,
        SlidingWindowSpec(
            alignment=AlignmentSpec(max_states=2),
            window_size=1,
            max_candidates=1,
            fallback_to_exact=False,
            verify_exact=True,
        ),
    ).value.traces[0]
    # Each local window needs two states; full-trace verification needs four.
    assert result.exact_verification_status == "search_limit"
    assert result.cost_upper_bound == 0
    assert result.verification_settled_states == 2
    # Independent nonnegative-cost bound still certifies the zero-cost witness.
    assert result.certificate == "zero_cost"
    assert result.status == "optimal"
    assert result.certified_optimal_cost == 0


def test_fixed_horizon_public_wrapper_records_real_strategy_evidence():
    spec = FixedHorizonSpec(
        horizon=2,
        max_horizon=3,
        max_tail_firings=8,
        max_prefix_states=100,
        max_tail_solves=100,
        max_tail_nodes=10000,
    )
    result = align_fixed_horizon(log("AB"), sequence_net("A", "B"), spec)
    trace = result.value.traces[0]
    assert trace.fixed_horizon is not None
    assert trace.fixed_horizon.stages
    assert trace.fixed_horizon.tail_solves > 0
    assert_executable(
        trace,
        case_traces(log("AB")).value.traces[0],
        sequence_net("A", "B"),
        spec.alignment,
    )


def test_request_identity_covers_strategy_controls_and_verification():
    data, model = log("AAAA"), sequence_net("A")
    base = align_tandem_repeats(data, model)
    verification = align_tandem_repeats(
        data, model, TandemRepeatSpec(verify_exact=True)
    )
    period = align_tandem_repeats(data, model, TandemRepeatSpec(max_period=2))
    sliding = align_sliding_window(data, model)
    assert (
        len(
            {
                base.computation_id,
                verification.computation_id,
                period.computation_id,
                sliding.computation_id,
            }
        )
        == 4
    )


def test_upstream_invalid_result_propagates_without_search():
    original = case_traces(log("A"))
    failed = replace(
        original,
        status=ComputeStatus.INVALID_INPUT,
        value=None,
        issues=(ComputeIssue("bad_fixture", "invalid"),),
    )
    for result in (
        align_tandem_repeats(failed, sequence_net("A")),
        align_sliding_window(failed, sequence_net("A")),
        align_fixed_horizon(failed, sequence_net("A")),
    ):
        assert result.status is ComputeStatus.INVALID_INPUT
        assert result.value is None
        assert result.issues[0].code == "bad_fixture"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: TandemRepeatSpec(max_period=0),
        lambda: TandemRepeatSpec(verify_exact=1),
        lambda: SlidingWindowSpec(window_size=0),
        lambda: SlidingWindowSpec(max_candidates=True),
        lambda: SlidingWindowSpec(max_total_states=0),
        lambda: SlidingWindowSpec(max_post_model_moves=-1),
    ],
)
def test_invalid_strategy_contracts(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()
