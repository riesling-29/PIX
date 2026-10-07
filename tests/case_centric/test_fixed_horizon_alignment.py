"""Executable witnesses and counterexamples for integer-tail approximation."""

from dataclasses import FrozenInstanceError, replace
from functools import lru_cache

import pytest

from pix.case_centric._fixed_horizon_alignment import (
    FixedHorizonOutcome,
    FixedHorizonSpec,
    run_fixed_horizon,
)
from pix.contracts.analysis import ObjectTrace, TraceEvent
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition


def trace(*labels):
    return ObjectTrace(
        "case",
        "case",
        tuple(
            TraceEvent(f"event-{index}", label, None, ())
            for index, label in enumerate(labels)
        ),
    )


def net_from_edges(edges, initial="s", final="f", extra_places=()):
    places = {initial, final, *extra_places}
    transitions, arcs = [], []
    for source, tid, activity, target in edges:
        places.update((source, target))
        transitions.append(Transition(tid, activity))
        arcs.extend((Arc(source, tid), Arc(tid, target)))
    return PetriNet(
        tuple(Place(p) for p in sorted(places)),
        tuple(transitions),
        tuple(arcs),
        Marking(((initial, 1),)),
        Marking(((final, 1),)),
    )


def chain(*labels):
    return net_from_edges(
        tuple((f"p{i}", f"t{i}", label, f"p{i + 1}") for i, label in enumerate(labels)),
        initial="p0",
        final=f"p{len(labels)}",
    )


def independent_witness(observed, model, result):
    """Direct incidence arithmetic, without production enabled/fire helpers."""
    tokens = dict(model.initial_marking.tokens)
    transitions = {item.id: item for item in model.transitions}
    event_index = 0
    for move in result.moves:
        before = tuple(
            sorted((place, amount) for place, amount in tokens.items() if amount)
        )
        assert move.before_marking == before
        if move.kind in ("log", "synchronous"):
            event = observed.events[event_index]
            assert (move.event_id, move.activity) == (event.event_id, event.activity)
            event_index += 1
        else:
            assert move.event_id is None
        if move.transition_id is not None:
            transition = transitions[move.transition_id]
            assert move.activity == transition.activity
            assert (move.kind == "silent") == (transition.activity is None)
            for arc in model.arcs:
                if arc.target == transition.id:
                    assert tokens.get(arc.source, 0) >= arc.weight
            for arc in model.arcs:
                if arc.target == transition.id:
                    tokens[arc.source] -= arc.weight
                elif arc.source == transition.id:
                    tokens[arc.target] = tokens.get(arc.target, 0) + arc.weight
        else:
            assert move.kind == "log"
        after = tuple(
            sorted((place, amount) for place, amount in tokens.items() if amount)
        )
        assert move.after_marking == after
    if result.status == "complete":
        assert event_index == len(observed.events)
        assert (
            Marking(tuple((p, n) for p, n in tokens.items() if n))
            == model.final_marking
        )


@lru_cache(None)
def insert_delete_distance(left, right):
    if not left or not right:
        return len(left) + len(right)
    choices = [
        1 + insert_delete_distance(left[1:], right),
        1 + insert_delete_distance(left, right[1:]),
    ]
    if left[0] == right[0]:
        choices.append(insert_delete_distance(left[1:], right[1:]))
    return min(choices)


def test_actual_integer_tail_solves_and_full_selected_prefix_commits():
    observed, model = trace("A", "B", "C", "D"), chain("A", "B", "C", "D")
    outcome = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=2, max_horizon=2)
    )
    assert isinstance(outcome, FixedHorizonOutcome)
    assert outcome.status == "complete"
    assert outcome.fallback_reason is None
    assert sum(move.cost for move in outcome.moves) == 0
    assert outcome.tail_solves > 0
    assert sum(stage.tail_solves for stage in outcome.stages) == outcome.tail_solves
    assert sum(stage.prefix_states for stage in outcome.stages) == outcome.total_states
    committed = [stage for stage in outcome.stages if stage.committed]
    assert [stage.selected_progress for stage in committed] == [2, 2]
    assert sum(stage.certified_tails for stage in committed) > 0
    assert all(
        stage.prefix_complete and stage.uncertified_tails == 0 for stage in committed
    )
    assert len(outcome.moves) == sum(
        len(stage.selected_product_steps) for stage in committed
    )
    independent_witness(observed, model, outcome)


@pytest.mark.parametrize("labels", [(), ("A",), ("A", "A"), ("A", "B", "A")])
def test_perfect_sequential_cases(labels):
    observed, model = trace(*labels), chain(*labels)
    result = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=1, max_horizon=1)
    )
    assert result.status == "complete"
    assert sum(move.cost for move in result.moves) == 0
    independent_witness(observed, model, result)


def test_empty_accepting_product_needs_no_search_or_tail_solver():
    result = run_fixed_horizon(trace(), chain())
    assert (
        result.status,
        result.moves,
        result.stages,
        result.total_states,
        result.tail_solves,
    ) == (
        "complete",
        (),
        (),
        0,
        0,
    )


@pytest.mark.parametrize(
    "observed,labels",
    [((), (None, None)), (("A",), (None, "A")), (("A",), ("A", None)), ((), ("X",))],
)
def test_silent_and_model_progress_after_last_event(observed, labels):
    observed, model = trace(*observed), chain(*labels)
    result = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=2, max_horizon=2)
    )
    assert result.status == "complete"
    independent_witness(observed, model, result)


def test_scalar_costs_and_exact_occurrence_identity():
    observed, model = trace("A", "Q", "A"), chain("A", "A")
    costs = AlignmentSpec(
        log_move_cost=7, model_move_cost=9, synchronous_move_cost=2, silent_move_cost=3
    )
    result = run_fixed_horizon(
        observed, model, FixedHorizonSpec(alignment=costs, horizon=1, max_horizon=1)
    )
    assert result.status == "complete"
    assert [move.event_id for move in result.moves] == ["event-0", "event-1", "event-2"]
    assert [move.cost for move in result.moves] == [2, 7, 2]
    independent_witness(observed, model, result)


def test_minimum_progress_counts_consumed_events_not_silent_steps():
    observed, model = trace("A"), chain(None, "A")
    strict = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=1, max_horizon=1, min_progress=1)
    )
    permissive = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=1, max_horizon=1, min_progress=0)
    )
    assert strict.status == permissive.status == "complete"
    assert strict.moves[0].kind == "log"
    assert strict.stages[0].selected_progress == 1
    assert sum(move.cost for move in strict.moves) == 2
    assert permissive.moves[0].kind == "silent"
    assert permissive.stages[0].selected_progress == 0
    assert sum(move.cost for move in permissive.moves) == 0
    independent_witness(observed, model, strict)
    independent_witness(observed, model, permissive)


def test_ties_retain_deterministic_first_discovery_after_state_merging():
    model = net_from_edges((("s", "a", "A", "f"), ("s", "b", "B", "f")))
    observed = trace("A", "B")
    spec = FixedHorizonSpec(horizon=2, max_horizon=2, min_progress=2)
    result = run_fixed_horizon(observed, model, spec)
    assert result.status == "complete"
    assert result.stages[0].selected_product_steps == ("sync:0:a", "log:1")
    assert sum(move.cost for move in result.moves) == 1
    # Reversing user-supplied tuple order does not change deterministic semantics.
    reordered = PetriNet(
        tuple(reversed(model.places)),
        tuple(reversed(model.transitions)),
        tuple(reversed(model.arcs)),
        model.initial_marking,
        model.final_marking,
    )
    assert run_fixed_horizon(observed, reordered, spec) == result
    independent_witness(observed, model, result)


def test_integer_feasible_is_not_an_executable_alignment():
    model = PetriNet(
        (Place("s"), Place("q"), Place("f")),
        (Transition("a", "A"),),
        (Arc("s", "a"), Arc("q", "a"), Arc("a", "q"), Arc("a", "f")),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )
    observed = trace("A")
    result = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=1, max_horizon=1)
    )
    assert result.status == "unreachable"
    assert result.fallback_reason == "closed_product_graph"
    assert result.tail_solves > 0
    assert result.moves == ()
    assert result.stages[0].certified_tails > 0
    independent_witness(observed, model, result)


def silent_trap():
    return PetriNet(
        (Place("s"), Place("q"), Place("f")),
        (Transition("loop"), Transition("ghost"), Transition("escape", "X")),
        (
            Arc("s", "loop"),
            Arc("loop", "s"),
            Arc("s", "ghost"),
            Arc("q", "ghost"),
            Arc("ghost", "q"),
            Arc("ghost", "f"),
            Arc("s", "escape"),
            Arc("escape", "f"),
        ),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )


def test_integer_zero_tail_silent_loop_stalls_despite_valid_escape():
    result = run_fixed_horizon(
        trace(),
        silent_trap(),
        FixedHorizonSpec(horizon=1, max_horizon=1, min_progress=0),
    )
    assert result.status == "stalled"
    assert result.fallback_reason == "repeated_product_state"
    assert result.stages[0].selected_product_steps == ("model:loop",)
    assert result.stages[0].tail_cost == 0
    assert result.moves == ()
    assert result.tail_solves > 0


def test_horizon_adapts_and_records_uncommitted_retries():
    result = run_fixed_horizon(
        trace(),
        silent_trap(),
        FixedHorizonSpec(horizon=1, max_horizon=3, min_progress=0),
    )
    assert result.status == "stalled"
    assert [stage.horizon for stage in result.stages] == [1, 2, 3]
    assert [stage.reason for stage in result.stages] == [
        "grow_horizon:repeated_product_state",
        "grow_horizon:repeated_product_state",
        "repeated_product_state",
    ]
    assert not any(stage.committed for stage in result.stages)
    # The same full product marking is cached across retries.
    assert result.tail_solves == 1


def test_strictly_suboptimal_commitment_has_valid_witness_but_no_optimal_claim():
    model = net_from_edges(
        (
            ("s", "a_bad", "A", "b0"),
            ("b0", "bad_c", "C", "b1"),
            ("b1", "bad_b", "B", "f"),
            ("s", "a_good", "A", "g0"),
            ("g0", "good_x", "X", "g1"),
            ("g1", "good_b", "B", "g2"),
            ("g2", "good_c", "C", "f"),
        )
    )
    observed = trace("A", "B", "C")
    result = run_fixed_horizon(
        observed,
        model,
        FixedHorizonSpec(horizon=1, max_horizon=1, max_tail_nodes=100000),
    )
    assert result.status == "complete"
    assert result.moves[0].transition_id == "a_bad"
    assert sum(move.cost for move in result.moves) == 2
    exact_cost = min(
        insert_delete_distance(tuple("ABC"), word)
        for word in (tuple("ACB"), tuple("AXBC"))
    )
    assert exact_cost == 1
    independent_witness(observed, model, result)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("max_prefix_states", 1, "maximum_prefix_states"),
        ("max_tail_solves", 1, "maximum_tail_solves"),
        ("max_tail_nodes", 1, "uncertified_integer_tail"),
        ("max_tail_firings", 0, "uncertified_integer_tail"),
        ("max_tail_lp_iterations", 1, "uncertified_integer_tail"),
    ],
)
def test_limits_are_not_certified_integer_objectives(field, value, reason):
    observed, model = trace("A", "B", "C"), chain("A", "B", "C")
    spec = replace(FixedHorizonSpec(horizon=1, max_horizon=1), **{field: value})
    result = run_fixed_horizon(observed, model, spec)
    assert result.status == "search_limit"
    assert result.fallback_reason == reason
    assert not result.stages[-1].committed
    if reason == "uncertified_integer_tail":
        assert result.stages[-1].uncertified_tails > 0
    independent_witness(observed, model, result)


def test_iteration_limit_preserves_only_committed_executable_prefix():
    observed, model = trace("A", "B", "C"), chain("A", "B", "C")
    result = run_fixed_horizon(
        observed, model, FixedHorizonSpec(horizon=1, max_horizon=1, max_iterations=1)
    )
    assert result.status == "search_limit"
    assert result.fallback_reason == "maximum_iterations"
    assert len(result.moves) == 1
    assert result.moves[0].event_id == "event-0"
    independent_witness(observed, model, result)


def test_weighted_arcs_residual_marking_and_transition_identity():
    model = PetriNet(
        (Place("s"), Place("f")),
        (Transition("a", "A"), Transition("other_a", "A")),
        (Arc("s", "a", 2), Arc("a", "f", 2), Arc("s", "other_a"), Arc("other_a", "f")),
        Marking((("s", 2),)),
        Marking((("f", 2),)),
    )
    observed = trace("A")
    result = run_fixed_horizon(observed, model)
    assert result.status == "complete"
    assert [step.transition_id for step in result.moves] == ["a"]
    independent_witness(observed, model, result)


def test_fallback_flags_do_not_trigger_hidden_search_in_helper():
    spec = FixedHorizonSpec(horizon=1, max_horizon=1, min_progress=0)
    first = run_fixed_horizon(trace(), silent_trap(), spec)
    second = run_fixed_horizon(
        trace(),
        silent_trap(),
        replace(spec, fallback_to_exact=False, verify_exact=True),
    )
    assert first == second
    assert first.status == "stalled"


@pytest.mark.parametrize(
    "field",
    [
        "horizon",
        "min_progress",
        "max_horizon",
        "max_prefix_states",
        "max_iterations",
        "max_tail_solves",
        "max_tail_firings",
        "max_tail_nodes",
        "max_tail_lp_iterations",
    ],
)
def test_spec_rejects_bool_and_negative_integer_bounds(field):
    with pytest.raises(TypeError):
        FixedHorizonSpec(**{field: True})
    with pytest.raises(ValueError):
        FixedHorizonSpec(**{field: -1})


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"horizon": 0}, ValueError),
        ({"max_horizon": 1}, ValueError),
        ({"horizon": 1, "min_progress": 2}, ValueError),
        ({"alignment": {}}, TypeError),
        ({"fallback_to_exact": 1}, TypeError),
        ({"verify_exact": "yes"}, TypeError),
    ],
)
def test_spec_relations_and_types(kwargs, error):
    with pytest.raises(error):
        FixedHorizonSpec(**kwargs)


def test_public_contracts_are_frozen_and_inputs_are_checked():
    spec = FixedHorizonSpec()
    with pytest.raises(FrozenInstanceError):
        spec.horizon = 3
    with pytest.raises(TypeError, match="trace"):
        run_fixed_horizon((), chain())
    with pytest.raises(TypeError, match="net"):
        run_fixed_horizon(trace(), None)
    with pytest.raises(TypeError, match="spec"):
        run_fixed_horizon(trace(), chain(), None)
    with pytest.raises(TypeError, match="TraceEvent"):
        run_fixed_horizon(ObjectTrace("x", "case", ("A",)), chain())
