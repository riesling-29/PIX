"""Independent small-net checks for exact Petri-net linear relaxations."""

from fractions import Fraction
from math import gcd

import pytest

from pix.case_centric._model_algebra import (
    incidence_matrix,
    invariants,
    marking_equation,
)
from pix.compute.model_semantics import enabled_transitions
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition


def matrix_net(matrix, initial=(), target=(), *, columns=None):
    columns = len(matrix[0]) if matrix else (0 if columns is None else columns)
    places = tuple(Place(f"p{i}") for i in range(len(matrix)))
    transitions = tuple(Transition(f"t{i}", f"A{i}") for i in range(columns))
    arcs = []
    for p, row in enumerate(matrix):
        for t, value in enumerate(row):
            if value < 0:
                arcs.append(Arc(f"p{p}", f"t{t}", -value))
            elif value > 0:
                arcs.append(Arc(f"t{t}", f"p{p}", value))
    return PetriNet(places, transitions, tuple(arcs), Marking(initial), Marking(target))


def test_incidence_preserves_weight_and_cancels_self_loop():
    net = PetriNet(
        (Place("b"), Place("a")),
        (Transition("z", "work"),),
        (Arc("a", "z", 3), Arc("z", "a", 2), Arc("z", "b", 4)),
        Marking((("a", 3),)),
        Marking((("a", 2), ("b", 4))),
    )
    assert incidence_matrix(net) == (("a", "b"), ("z",), ((-1,), (4,)))


def test_weighted_place_and_transition_invariants_have_expected_conservation():
    net = matrix_net([[-2, 2], [1, -1]])
    place = invariants(net, "place")
    transition = invariants(net, "transition")
    assert place.node_ids == ("p0", "p1")
    assert place.vectors == ((1, 2),)
    assert transition.node_ids == ("t0", "t1")
    assert transition.vectors == ((1, 1),)
    assert place.rank == transition.rank == 1
    assert place.dimension == transition.dimension == 1


def test_nullspace_is_not_misrepresented_as_a_nonnegative_invariant_cone():
    report = invariants(matrix_net([[-1, -1]]), "transition")
    assert report.vectors == ((1, -1),)


def test_multiple_free_columns_produce_independent_primitive_vectors():
    net = matrix_net([[2, 3, 5]])
    report = invariants(net, "transition")
    assert report.vectors == ((3, -2, 0), (5, 0, -2))
    for vector in report.vectors:
        assert sum(a * b for a, b in zip((2, 3, 5), vector)) == 0
        assert gcd(*vector) == 1
    assert report.dimension == 2


def test_weighted_three_place_chain_requires_rational_row_operations():
    net = matrix_net([[-2, 0], [1, -3], [0, 1]])
    assert invariants(net, "place").vectors == ((1, 2, 6),)
    assert invariants(net, "transition").vectors == ()


def test_place_invariants_preserve_conservation_over_executed_weighted_cycle():
    from pix.compute.model_semantics import fire

    net = matrix_net([[-2, 2], [1, -1]], initial=(("p0", 2),))
    marking = net.initial_marking
    weights = dict(zip(("p0", "p1"), invariants(net).vectors[0]))
    for step in (None, "t0", "t1", "t0", "t1"):
        if step is not None:
            marking = fire(net, marking, step)
        assert sum(weights[place] * count for place, count in marking.tokens) == 2


@pytest.mark.parametrize("kind", ["place", "transition"])
def test_empty_net_invariant_space(kind):
    report = invariants(matrix_net([]), kind)
    assert report.node_ids == report.vectors == ()
    assert report.dimension == report.rank == 0


def test_no_places_and_no_transitions_handle_nonempty_zero_dimensional_matrices():
    no_places = matrix_net([], columns=2)
    assert invariants(no_places, "transition").vectors == ((1, 0), (0, 1))
    no_transitions = matrix_net([[], []])
    assert invariants(no_transitions, "place").vectors == ((1, 0), (0, 1))


def test_exact_fractional_lp_solution_is_not_a_firing_count():
    net = matrix_net([[2, 3]], target=(("p0", 1),))
    report = marking_equation(net)
    assert report.status == "optimal"
    assert report.objective == (1, 3)
    assert report.solution == ((0, 1), (1, 3))
    assert report.bases_checked == report.total_bases == 2
    assert report.reachability_proven is False


def test_two_constraint_optimum_matches_eliminated_one_variable_formula():
    # x0 = 3 - x2, x1 = 2 - x2, 0 <= x2 <= 2.
    # Cost is 12 - 4*x2, hence its minimum is 4 at x2=2.
    net = matrix_net([[1, 0, 1], [0, 1, 1]], target=(("p0", 3), ("p1", 2)))
    report = marking_equation(net, costs={"t0": 2, "t1": 3, "t2": 1})
    assert report.objective == (4, 1)
    assert report.solution == ((1, 1), (0, 1), (2, 1))
    assert report.rank == 2


def test_cycle_creates_unbounded_feasible_region_but_finite_cost_optimum():
    # -x0+x1=-1; x0=1+x1, x1>=0, so the minimum cost is 2 at (1,0).
    net = matrix_net([[-1, 1], [1, -1]], initial=(("p0", 1),), target=(("p1", 1),))
    report = marking_equation(net, costs={"t0": 2, "t1": 0})
    assert report.status == "optimal"
    assert report.objective == (2, 1)
    assert report.solution == ((1, 1), (0, 1))


def test_infeasible_linear_equalities_prove_infeasibility_before_enumeration():
    net = matrix_net([[1], [1]], target=(("p0", 1), ("p1", 2)))
    report = marking_equation(net)
    assert report.status == "infeasible"
    assert report.reason == "inconsistent_linear_equalities"
    assert report.bases_checked == 0
    assert report.solution is report.objective is None


def test_consistent_equalities_can_still_be_nonnegative_infeasible():
    net = matrix_net([[1]], initial=(("p0", 1),))
    report = marking_equation(net)
    assert report.status == "infeasible"
    assert report.reason == "no_nonnegative_basic_feasible_solution"
    assert report.bases_checked == report.total_bases == 1


def test_singular_column_subsets_count_against_budget():
    net = matrix_net([[1, 0, 1], [0, 0, 1]], target=(("p0", 1), ("p1", 1)))
    limited = marking_equation(net, max_bases=1)
    assert limited.status == "unknown"
    assert limited.incumbent_cost is limited.objective is limited.solution is None
    assert limited.bases_checked == 1
    complete = marking_equation(net, max_bases=3)
    assert complete.status == "optimal"
    assert complete.objective == (1, 1)
    assert complete.bases_checked == complete.total_bases == 3


def test_budget_exhaustion_does_not_publish_incumbent_as_lower_bound():
    net = matrix_net([[1, 1, 2]], target=(("p0", 2),))
    costs = {"t0": 2, "t1": 1, "t2": 1}
    limited = marking_equation(net, costs=costs, max_bases=1)
    assert limited.status == "unknown"
    assert limited.objective is None
    assert limited.incumbent_cost == (4, 1)
    assert limited.solution == ((2, 1), (0, 1), (0, 1))
    complete = marking_equation(net, costs=costs, max_bases=3)
    assert complete.objective == (1, 1)


def test_marking_equation_feasible_but_no_transition_enabled():
    # The empty q self-loop is required for firing but cancels in C.
    net = PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("t", "A"),),
        (Arc("p", "t"), Arc("q", "t"), Arc("t", "q"), Arc("t", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )
    assert enabled_transitions(net, net.initial_marking) == ()
    report = marking_equation(net)
    assert report.status == "optimal"
    assert report.solution == ((1, 1),)
    assert report.reachability_proven is False


def test_zero_rank_optimum_handles_unbounded_feasible_region():
    net = matrix_net([[0, 0]])
    report = marking_equation(net, costs={"t0": 0})
    assert report.objective == (0, 1)
    assert report.solution == ((0, 1), (0, 1))
    assert report.bases_checked == 0


def test_empty_transition_set_different_markings_is_infeasible():
    net = matrix_net([[]], target=(("p0", 1),))
    assert marking_equation(net).status == "infeasible"
    empty = marking_equation(matrix_net([]))
    assert empty.status == "optimal"
    assert empty.solution == ()


def test_exact_large_integers_and_rational_costs_preserve_precision():
    weight = 2**60 + 3
    net = matrix_net([[weight]], target=(("p0", 1),))
    report = marking_equation(net, costs={"t0": Fraction(7, 11)})
    expected = Fraction(7, 11 * weight)
    assert report.objective == (expected.numerator, expected.denominator)
    assert report.solution == ((1, weight),)
    assert marking_equation(net, costs={"t0": (7, 11)}) == report


def test_explicit_markings_override_accepting_markings():
    net = matrix_net([[-1], [1]], initial=(("p0", 5),), target=(("p1", 5),))
    report = marking_equation(net, Marking((("p0", 2),)), Marking((("p1", 2),)))
    assert report.objective == (2, 1)


@pytest.mark.parametrize(
    "max_bases,error",
    [(0, ValueError), (-1, ValueError), (True, TypeError), (2.0, TypeError)],
)
def test_invalid_budgets(max_bases, error):
    with pytest.raises(error):
        marking_equation(matrix_net([[1]]), max_bases=max_bases)


@pytest.mark.parametrize(
    "cost,error",
    [
        (-1, ValueError),
        ((1, 0), ValueError),
        (True, TypeError),
        (0.5, TypeError),
        ((1.0, 2), TypeError),
        ("1", TypeError),
    ],
)
def test_invalid_costs(cost, error):
    with pytest.raises(error):
        marking_equation(matrix_net([[1]]), costs={"t0": cost})


def test_unknown_cost_transition_and_marking_place_are_rejected():
    net = matrix_net([[1]])
    with pytest.raises(ValueError, match="unknown transition"):
        marking_equation(net, costs={"missing": 1})
    with pytest.raises(ValueError, match="unknown place"):
        marking_equation(net, target=Marking((("missing", 1),)))
    with pytest.raises(ValueError, match="kind"):
        invariants(net, "unsupported")
    with pytest.raises(TypeError, match="PetriNet"):
        incidence_matrix(object())
