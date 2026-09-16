"""Integer horizon, extended constraints, and independent execution witnesses."""

import random
from collections import deque
from fractions import Fraction
from itertools import product

import pytest

from pix.case_centric.marking_equation import (
    ExtendedMarkingEquationSpec,
    IntegerMarkingEquationSpec,
    ProductMoveCosts,
    SynchronousProductSpec,
    extended_marking_equation,
    integer_marking_equation,
    synchronous_product,
)
from pix.case_centric.model_analysis import marking_equation_bound
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus


def net(places, transitions, arcs, initial, final):
    return PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(t, a) for t, a in transitions),
        tuple(Arc(*a) for a in arcs),
        Marking(tuple(initial)),
        Marking(tuple(final)),
    )


def chain(activities=("A", "B")):
    return net(
        tuple(f"p{i}" for i in range(len(activities) + 1)),
        tuple((f"t{i}", activity) for i, activity in enumerate(activities)),
        tuple(
            arc
            for i in range(len(activities))
            for arc in ((f"p{i}", f"t{i}"), (f"t{i}", f"p{i + 1}"))
        ),
        (("p0", 1),),
        ((f"p{len(activities)}", 1),),
    )


def check_solution(program, solution):
    x = tuple(Fraction(*item) for item in solution)
    assert all(item >= 0 for item in x)
    for row, target in zip(program.equalities, program.equality_rhs):
        assert sum(a * b for a, b in zip(row, x)) == target
    for row, target in zip(program.inequalities, program.inequality_rhs):
        assert sum(a * b for a, b in zip(row, x)) <= target
    return sum(Fraction(*cost) * value for cost, value in zip(program.costs, x))


def bounded_vector_oracle(program, horizon):
    """Independent complete Cartesian enumeration; no production pruning."""
    best, solutions = None, []
    for vector in product(range(horizon + 1), repeat=len(program.variables)):
        if sum(vector) > horizon:
            continue
        if any(
            sum(a * b for a, b in zip(row, vector)) != target
            for row, target in zip(program.equalities, program.equality_rhs)
        ):
            continue
        if any(
            sum(a * b for a, b in zip(row, vector)) > target
            for row, target in zip(program.inequalities, program.inequality_rhs)
        ):
            continue
        cost = sum(Fraction(*c) * v for c, v in zip(program.costs, vector))
        if best is None or cost < best:
            best, solutions = cost, [vector]
        elif cost == best:
            solutions.append(vector)
    return best, solutions


def firing_sequences(model, max_steps):
    """Independent vector arithmetic over actual enabled product moves."""
    places = tuple(p.id for p in model.places)
    initial = tuple(dict(model.initial_marking.tokens).get(p, 0) for p in places)
    final = tuple(dict(model.final_marking.tokens).get(p, 0) for p in places)
    incidence = []
    for transition in model.transitions:
        pre = tuple(
            sum(
                a.weight
                for a in model.arcs
                if a.source == p and a.target == transition.id
            )
            for p in places
        )
        post = tuple(
            sum(
                a.weight
                for a in model.arcs
                if a.source == transition.id and a.target == p
            )
            for p in places
        )
        incidence.append((transition.id, pre, post))
    pending = deque(((initial, ()),))
    accepted = []
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.append(word)
        if len(word) == max_steps:
            continue
        for tid, pre, post in incidence:
            if all(have >= need for have, need in zip(marking, pre)):
                after = tuple(
                    have - need + made for have, need, made in zip(marking, pre, post)
                )
                pending.append((after, word + (tid,)))
    return accepted


def test_integer_optimum_with_exact_global_bound():
    result = integer_marking_equation(
        chain(), IntegerMarkingEquationSpec(max_total_firings=2)
    )
    value = result.value.result
    assert value.status == "optimal" and value.objective == (2, 1)
    assert value.objective_scope == "global_integer"
    assert value.global_lower_bound == (2, 1)
    assert not value.reachability_proven
    assert result.status is ComputeStatus.COMPUTED
    assert result.source_digest == model_digest(chain())
    check_solution(result.value.program, value.solution)


def test_horizon_optimum_is_not_a_global_lower_bound():
    model = net(
        ("p",), (("a", "A"), ("b", "B")), (("a", "p"), ("b", "p", 4)), (), (("p", 4),)
    )
    costs = (("a", (1, 1)), ("b", (5, 1)))
    short = integer_marking_equation(
        model, IntegerMarkingEquationSpec(transition_costs=costs, max_total_firings=1)
    )
    long = integer_marking_equation(
        model, IntegerMarkingEquationSpec(transition_costs=costs, max_total_firings=4)
    )
    assert short.value.result.status == "optimal_within_horizon"
    assert short.value.result.objective == (5, 1)
    assert short.value.result.global_lower_bound == (4, 1)
    assert short.value.result.objective_scope == "integer_horizon"
    assert short.status is ComputeStatus.PARTIAL
    assert long.value.result.status == "optimal"
    assert long.value.result.objective == (4, 1)
    assert short.computation_id != long.computation_id


def test_integer_horizon_infeasible_does_not_prove_global_infeasibility():
    result = integer_marking_equation(
        chain(), IntegerMarkingEquationSpec(max_total_firings=1)
    )
    assert result.value.result.status == "infeasible_within_horizon"
    assert result.value.result.objective is None
    assert result.value.result.global_lower_bound == (2, 1)
    assert result.status is ComputeStatus.PARTIAL


def test_integer_lattice_rounding_can_certify_global_optimum():
    model = net(
        ("p",),
        (("a", "A"), ("b", "B")),
        (("a", "p", 2), ("b", "p", 3)),
        (),
        (("p", 3),),
    )
    result = integer_marking_equation(
        model,
        IntegerMarkingEquationSpec(
            transition_costs=(("a", (1, 1)), ("b", (2, 1))), max_total_firings=2
        ),
    ).value
    assert result.result.rational_relaxation.objective == (3, 2)
    assert result.result.global_lower_bound == (2, 1)
    assert result.result.objective == (2, 1)
    assert result.result.status == "optimal"


def test_integer_fractional_costs_are_exact():
    result = integer_marking_equation(
        chain(("A",)),
        IntegerMarkingEquationSpec(
            transition_costs=(("t0", (2, 3)),), max_total_firings=1
        ),
    ).value.result
    assert result.objective == (2, 3) and result.global_lower_bound == (2, 3)


def test_parity_obstruction_is_reported_only_for_tested_horizon():
    model = net(("p",), (("a", "A"),), (("a", "p", 2),), (), (("p", 3),))
    result = integer_marking_equation(
        model, IntegerMarkingEquationSpec(max_total_firings=4)
    ).value.result
    assert result.rational_relaxation.status == "optimal"
    assert result.status == "infeasible_within_horizon"
    assert result.solution is None


def test_rational_infeasibility_is_a_global_equation_refutation():
    model = net(("p", "q"), (("a", "A"),), (("a", "p"),), (), (("q", 1),))
    result = integer_marking_equation(model).value.result
    assert result.status == "infeasible" and result.searched_nodes == 0
    assert result.rational_relaxation.certificate_validated


def test_integer_budget_exhaustion_retains_bound_but_no_optimum():
    result = integer_marking_equation(
        chain(), IntegerMarkingEquationSpec(max_search_nodes=1)
    ).value.result
    assert result.status == "unknown" and result.objective is None
    assert result.global_lower_bound == (2, 1)
    assert not result.integer_search_complete


def test_huge_integer_horizon_with_tiny_node_budget_does_not_expand_eagerly():
    result = integer_marking_equation(
        chain(),
        IntegerMarkingEquationSpec(max_total_firings=10**12, max_search_nodes=1),
    ).value.result
    assert result.status == "unknown" and result.searched_nodes == 1
    assert result.global_lower_bound == (2, 1)


def test_zero_horizon_empty_model_is_valid():
    model = net((), (), (), (), ())
    result = integer_marking_equation(
        model, IntegerMarkingEquationSpec(max_total_firings=0)
    ).value.result
    assert result.status == "optimal" and result.objective == (0, 1)
    assert result.solution == ()


def test_product_keeps_all_duplicate_label_transitions_and_occurrences():
    model = net(
        ("p", "q"),
        (("a", "A"), ("b", "A")),
        (("p", "a"), ("a", "q"), ("p", "b"), ("b", "q")),
        (("p", 1),),
        (("q", 1),),
    )
    result = synchronous_product(model, SynchronousProductSpec(("A", "A"))).value
    assert len(result.transitions) == 8  # 2 model, 2 log, 4 sync
    assert {
        row.trace_index for row in result.transitions if row.move_kind == "synchronous"
    } == {0, 1}
    assert {
        row.model_transition_id
        for row in result.transitions
        if row.move_kind == "synchronous"
    } == {"a", "b"}
    assert result.source_model_digest == model_digest(model)


def test_product_preserves_weighted_arcs_and_silent_costs():
    model = net(
        ("p", "q"),
        (("a", "A"), ("s", None)),
        (("p", "a", 2), ("a", "q", 3), ("q", "s"), ("s", "q")),
        (("p", 2),),
        (("q", 3),),
    )
    value = synchronous_product(
        model, SynchronousProductSpec(("A",), ProductMoveCosts(silent=(1, 7)))
    ).value
    assert Arc("model:p", "sync:0:a", 2) in value.model.arcs
    assert Arc("sync:0:a", "model:q", 3) in value.model.arcs
    silent = next(row for row in value.transitions if row.move_kind == "silent")
    assert silent.cost == (1, 7) and silent.trace_index is None


def test_product_model_order_and_empty_trace():
    model = chain(("A",))
    empty = synchronous_product(model, SynchronousProductSpec(())).value
    assert empty.model.initial_marking.tokens == (("model:p0", 1), ("trace:0", 1))
    assert empty.model.final_marking.tokens == (("model:p1", 1), ("trace:0", 1))
    assert {row.move_kind for row in empty.transitions} == {"model"}
    assert firing_sequences(empty.model, 2) == [("model:t0",)]


def test_extended_zero_split_matches_ordinary_product_relaxation():
    model = chain()
    for trace in (("A", "B"), ("B", "A"), (), ("A",)):
        result = extended_marking_equation(
            model, ExtendedMarkingEquationSpec(trace)
        ).value
        costs = tuple(
            (row.transition_id, row.cost) for row in result.product.transitions
        )
        from pix.case_centric.model_analysis import MarkingEquationSpec

        ordinary = marking_equation_bound(
            result.product.model, MarkingEquationSpec(transition_costs=costs)
        ).value
        assert result.result.objective == ordinary.objective
        assert result.segment_count == 1
        assert result.split_transition_weights == ()


@pytest.mark.parametrize("splits", [(0,), (1,), (0, 1)])
def test_extended_split_strengthens_reversed_trace_bound(splits):
    model = chain()
    ordinary = extended_marking_equation(
        model, ExtendedMarkingEquationSpec(("B", "A"))
    ).value.result
    extended = extended_marking_equation(
        model, ExtendedMarkingEquationSpec(("B", "A"), splits)
    ).value
    assert ordinary.objective == (0, 1)
    assert extended.result.objective == (2, 1)
    assert extended.result.global_lower_bound == (2, 1)
    assert extended.result.objective_scope == "global_relaxation"
    assert extended.segment_count == len(splits) + 1
    assert extended.result.rational_relaxation.certificate_validated
    assert check_solution(extended.program, extended.result.solution) == 2


def test_extended_weighted_self_loop_requires_actual_input_count_at_split():
    # Plain incidence loses the p self-loop consumption, while Pre retains it.
    model = net(
        ("p", "q"),
        (("a", "A"),),
        (("p", "a", 2), ("a", "p", 2), ("a", "q")),
        (("p", 1),),
        (("p", 1), ("q", 1)),
    )
    plain = extended_marking_equation(model, ExtendedMarkingEquationSpec(("A",))).value
    split = extended_marking_equation(
        model, ExtendedMarkingEquationSpec(("A",), (0,))
    ).value
    assert plain.result.objective == (0, 1)
    # Rational y may mix half sync with half log; integer y must select one.
    assert split.result.objective == (1, 1)
    integer = extended_marking_equation(
        model, ExtendedMarkingEquationSpec(("A",), (0,), "integer", max_total_firings=3)
    ).value
    assert integer.result.objective == (2, 1)
    assert integer.result.global_lower_bound == (1, 1)
    assert integer.result.objective_scope == "integer_horizon"
    assert not split.result.reachability_proven
    assert firing_sequences(split.product.model, 4) == []


def test_repeated_activity_split_uses_exact_occurrence_not_only_activity():
    result = extended_marking_equation(
        chain(("A", "A")), ExtendedMarkingEquationSpec(("A", "A"), (1,))
    ).value
    lookup = {row.transition_id: row for row in result.product.transitions}
    split_vars = [var for var in result.program.variables if var.kind == "split"]
    assert split_vars
    assert all(lookup[var.transition_id].trace_index == 1 for var in split_vars)
    assert result.result.objective == (0, 1)


@pytest.mark.parametrize("trace", [("A",), ("B",), ()])
def test_extended_integer_small_cases_match_actual_minimum_execution_cost(trace):
    splits = tuple(range(len(trace)))
    spec = ExtendedMarkingEquationSpec(
        trace, splits, "integer", max_total_firings=3, max_search_nodes=100000
    )
    value = extended_marking_equation(chain(("A",)), spec).value
    executions = firing_sequences(value.product.model, 3)
    costs = {
        row.transition_id: Fraction(*row.cost) for row in value.product.transitions
    }
    true_cost = min(sum(costs[tid] for tid in sequence) for sequence in executions)
    assert Fraction(*value.result.objective) == true_cost
    assert value.result.status == "optimal"
    assert not value.result.reachability_proven


def test_every_actual_sequence_satisfies_split_constraints():
    value = extended_marking_equation(
        chain(), ExtendedMarkingEquationSpec(("B", "A"), (0, 1))
    ).value
    metadata = {row.transition_id: row for row in value.product.transitions}
    costs = {
        row.transition_id: Fraction(*row.cost) for row in value.product.transitions
    }
    for sequence in firing_sequences(value.product.model, 4):
        segment = 0
        counts = {}
        for tid in sequence:
            index = metadata[tid].trace_index
            if index in value.split_indices:
                split = value.split_indices.index(index)
                key = ("split", split, tid)
                segment = split + 1
            else:
                key = ("segment", segment, tid)
            counts[key] = counts.get(key, 0) + 1
        vector = tuple(
            (counts.get((var.kind, var.segment, var.transition_id), 0), 1)
            for var in value.program.variables
        )
        cost = check_solution(value.program, vector)
        assert cost == sum(costs[tid] for tid in sequence)
        assert Fraction(*value.result.global_lower_bound) <= cost


def test_extended_integer_horizon_and_search_budget_are_explicit():
    value = extended_marking_equation(
        chain(),
        ExtendedMarkingEquationSpec(("A", "B"), (0, 1), "integer", max_total_firings=1),
    ).value.result
    assert value.status == "infeasible_within_horizon"
    assert value.global_lower_bound == (0, 1)
    assert value.objective is None
    limited = extended_marking_equation(
        chain(),
        ExtendedMarkingEquationSpec(("A", "B"), (0, 1), "integer", max_search_nodes=1),
    ).value.result
    assert limited.status == "unknown"
    assert limited.objective is None


@pytest.mark.parametrize("seed", range(12))
def test_integer_pruning_matches_independent_cartesian_enumeration(seed):
    rng = random.Random(seed)
    transitions = tuple((f"t{i}", f"A{i}") for i in range(3))
    amounts = [rng.randrange(1, 5) for _ in transitions]
    costs = tuple(
        (tid, (rng.randrange(0, 6), rng.randrange(1, 4))) for tid, _ in transitions
    )
    model = net(
        ("p",),
        transitions,
        tuple((tid, "p", amount) for (tid, _), amount in zip(transitions, amounts)),
        (),
        (("p", rng.randrange(1, 8)),),
    )
    value = integer_marking_equation(
        model, IntegerMarkingEquationSpec(transition_costs=costs, max_total_firings=3)
    ).value
    expected, vectors = bounded_vector_oracle(value.program, 3)
    if expected is None:
        assert value.result.status in ("infeasible", "infeasible_within_horizon")
        assert value.result.objective is None
    else:
        assert Fraction(*value.result.objective) == expected
        assert tuple(pair[0] for pair in value.result.solution) in vectors


def test_result_roundtrips_and_request_identities():
    from pix.results import result_from_json, result_json_bytes

    model = chain(("A",))
    results = (
        synchronous_product(model, SynchronousProductSpec(("A",))),
        integer_marking_equation(model),
        integer_marking_equation(
            model, IntegerMarkingEquationSpec(max_total_firings=0)
        ),
        extended_marking_equation(model, ExtendedMarkingEquationSpec(("A",), (0,))),
        extended_marking_equation(
            model, ExtendedMarkingEquationSpec(("A",), (), "integer")
        ),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result
    changed = extended_marking_equation(
        model, ExtendedMarkingEquationSpec(("B",), (0,))
    )
    assert changed.computation_id != results[3].computation_id


@pytest.mark.parametrize("splits", [(1, 0), (0, 0), (-1,), (2,), (True,)])
def test_invalid_splits_are_rejected(splits):
    with pytest.raises((TypeError, ValueError)):
        ExtendedMarkingEquationSpec(("A", "B"), splits)


@pytest.mark.parametrize("bad", [-1, True, 1.5])
def test_invalid_integer_horizon_is_rejected(bad):
    with pytest.raises((TypeError, ValueError)):
        IntegerMarkingEquationSpec(max_total_firings=bad)


def test_unsupported_mode_and_invalid_costs_are_rejected():
    with pytest.raises(ValueError):
        ExtendedMarkingEquationSpec(("A",), mode="approximate")
    with pytest.raises(ValueError):
        ProductMoveCosts(log=(-1, 1))
    with pytest.raises(TypeError):
        ProductMoveCosts(synchronous=0.1)
    with pytest.raises(TypeError):
        SynchronousProductSpec(["A"])
