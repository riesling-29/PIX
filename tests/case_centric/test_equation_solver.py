"""Independent analytic/certificate/vertex checks for the exact LP solver."""

import random
from dataclasses import FrozenInstanceError
from fractions import Fraction
from itertools import combinations, permutations

import pytest

from pix.case_centric._equation_solver import solve_lp


def q(value):
    return Fraction(*value) if isinstance(value, tuple) else Fraction(value)


def scalar(left, right):
    return sum((q(a) * q(b) for a, b in zip(left, right)), Fraction(0))


def check_certificate(report, cost, eq=(), er=(), le=(), lr=()):
    """Check original-input residuals without inspecting solver internals."""
    assert report.pivots == report.iterations
    assert report.certificate_validated
    if report.solution is not None:
        solution = tuple(map(q, report.solution))
        assert len(solution) == len(cost)
        assert all(value >= 0 for value in solution)
        assert all(scalar(row, solution) == q(rhs) for row, rhs in zip(eq, er))
        assert all(scalar(row, solution) <= q(rhs) for row, rhs in zip(le, lr))
        assert q(report.incumbent_cost) == scalar(cost, solution)
    if report.status == "unknown":
        assert report.objective is None
        assert report.certificate_kind == "feasible_incumbent"
        return
    dual = tuple(map(q, report.dual_equalities + report.dual_inequalities))
    assert len(report.dual_equalities) == len(eq)
    assert len(report.dual_inequalities) == len(le)
    assert all(q(value) <= 0 for value in report.dual_inequalities)
    dual_value = scalar((*er, *lr), dual)
    for index in range(len(cost)):
        coefficient = scalar((row[index] for row in (*eq, *le)), dual)
        assert coefficient <= (q(cost[index]) if report.status == "optimal" else 0)
    if report.status == "optimal":
        assert report.certificate_kind == "primal_dual_optimal"
        assert scalar(cost, report.solution) == q(report.objective) == dual_value
    else:
        assert report.status == "infeasible"
        assert report.certificate_kind == "farkas_infeasible"
        assert dual_value > 0
        assert report.objective is report.solution is report.incumbent_cost is None


@pytest.mark.parametrize(
    "cost,eq,er,le,lr,expected",
    [
        ((1, 2), ((1, 1),), (1,), (), (), 1),
        ((2, 1), ((1, 1),), (1,), (), (), 1),
        ((1, 1), ((2, 3),), (1,), (), (), Fraction(1, 3)),
        ((2, 3, 1), ((1, 0, 1), (0, 1, 1)), (3, 2), (), (), 4),
        ((3,), (), (), ((-1,),), (-2,), 6),
        ((2, 1), ((1, 1),), (3,), ((-1, 0),), (-1,), 4),
        ((0, 0, 1), ((-1, -1, 0), (1, 0, 1)), (0, 1), (), (), 1),
        ((1, 2), ((1, 1), (2, 2), (0, 0)), (1, 2, 0), (), (), 1),
        ((1,), ((-1,), (-2,)), (-2, -4), (), (), 2),
        ((1, 0), (), (), ((0, -1),), (0,), 0),
        ((0,), (), (), ((-1,),), (-5,), 0),
        ((1,), (), (), ((-1,), (1,)), (-2, 2), 2),
        ((1,), ((0,),), (0,), (), (), 0),
        ((1,), (), (), ((0,),), (0,), 0),
        ((1,), (), (), ((0,),), (1,), 0),
        ((1, 2), (), (), (), (), 0),
        ((), (), (), (), (), 0),
        ((), ((), ()), (0, 0), ((),), (1,), 0),
        (
            (Fraction(2, 7),),
            ((Fraction(3, 5),),),
            (Fraction(11, 13),),
            (),
            (),
            Fraction(110, 273),
        ),
        (((1, 7),), (((-2, 3),),), ((-5, 11),), (), (), Fraction(15, 154)),
        ((1,), ((1,),), (10**90 + 1,), (), (), 10**90 + 1),
    ],
)
def test_analytic_optima_with_independent_certificates(cost, eq, er, le, lr, expected):
    report = solve_lp(
        cost, equalities=eq, equality_rhs=er, inequalities=le, inequality_rhs=lr
    )
    assert report.status == "optimal", report
    assert q(report.objective) == expected
    check_certificate(report, cost, eq, er, le, lr)


@pytest.mark.parametrize(
    "cost,eq,er,le,lr",
    [
        ((1,), ((1,),), (-1,), (), ()),
        ((1,), ((0,),), (1,), (), ()),
        ((1,), ((0,),), (-1,), (), ()),
        ((1,), ((1,), (2,)), (1, 3), (), ()),
        ((1,), (), (), ((1,), (-1,)), (1, -2)),
        ((1,), (), (), ((0,),), (-1,)),
        ((1, 1), ((1, 1),), (1,), ((-1, 0),), (-2,)),
        ((), ((),), (1,), (), ()),
        ((), (), (), ((),), (-1,)),
    ],
)
def test_analytic_infeasibility_has_original_input_farkas_certificate(
    cost, eq, er, le, lr
):
    report = solve_lp(
        cost, equalities=eq, equality_rhs=er, inequalities=le, inequality_rhs=lr
    )
    assert report.status == "infeasible", report
    check_certificate(report, cost, eq, er, le, lr)


def test_degenerate_beale_example_transformed_to_nonnegative_cost():
    # z = 1 - (10*x1 - 57*x2 - 9*x3 - 24*x4). The classical
    # cycling example has value 1 at (1,0,1,0), so min z is exactly 0.
    cost = (0, 0, 0, 0, 1)
    eq = ((10, -57, -9, -24, 1),)
    er = (1,)
    le = ((1, -11, -5, 18, 0), (1, -3, -1, 2, 0), (1, 0, 0, 0, 0))
    lr = (0, 0, 1)
    report = solve_lp(
        cost, equalities=eq, equality_rhs=er, inequalities=le, inequality_rhs=lr
    )
    assert report.status == "optimal"
    assert report.objective == (0, 1)
    assert report.pivots < 30
    check_certificate(report, cost, eq, er, le, lr)


def test_large_nearly_dependent_rows_retain_exact_rank_and_unique_solution():
    scale = 10**20
    eq = ((1, 1), (scale, scale + 1))
    report = solve_lp((0, 1), equalities=eq, equality_rhs=(1, scale + 1))
    assert report.status == "optimal"
    assert report.solution == ((0, 1), (1, 1))
    assert report.objective == (1, 1)
    check_certificate(report, (0, 1), eq, (1, scale + 1))


def test_phase_two_budget_returns_feasible_incumbent_without_claiming_bound():
    report = solve_lp((2, 1), equalities=((1, 1),), equality_rhs=(1,), max_iterations=1)
    assert report.status == "unknown"
    assert report.reason == "phase_two_iteration_limit"
    assert report.objective is None
    assert report.solution == ((1, 1), (0, 1))
    assert report.incumbent_cost == (2, 1)
    check_certificate(report, (2, 1), ((1, 1),), (1,))
    complete = solve_lp(
        (2, 1), equalities=((1, 1),), equality_rhs=(1,), max_iterations=2
    )
    assert complete.objective == (1, 1)


def test_phase_one_budget_does_not_expose_an_infeasible_artificial_point():
    report = solve_lp((1,), equalities=((1,),), equality_rhs=(1,), max_iterations=0)
    assert report.status == "unknown"
    assert report.reason == "phase_one_iteration_limit"
    assert report.objective is report.solution is report.incumbent_cost is None
    assert report.certificate_kind == "none"
    assert not report.certificate_validated


def test_cleanup_pivot_is_included_in_the_iteration_budget():
    eq = ((-1, -1, 0), (1, 0, 1))
    report = solve_lp((0, 0, 1), equalities=eq, equality_rhs=(0, 1), max_iterations=1)
    assert report.reason == "phase_one_cleanup_iteration_limit"
    assert report.status == "unknown"
    assert report.iterations == 1
    check_certificate(report, (0, 0, 1), eq, (0, 1))


@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({"costs": (1,)}, "optimal"),
        ({"costs": (), "equalities": ((),), "equality_rhs": (0,)}, "optimal"),
        ({"costs": (), "equalities": ((),), "equality_rhs": (1,)}, "infeasible"),
        (
            {"costs": (1,), "inequalities": ((0,),), "inequality_rhs": (-1,)},
            "infeasible",
        ),
    ],
)
def test_zero_budget_accepts_proofs_that_need_no_pivot(kwargs, status):
    report = solve_lp(**kwargs, max_iterations=0)
    assert report.status == status
    assert report.iterations == 0
    assert report.certificate_validated


def determinant(matrix):
    """Leibniz formula: independent of simplex and Gaussian elimination."""
    size = len(matrix)
    result = Fraction(0)
    for permutation in permutations(range(size)):
        inversions = sum(
            permutation[i] > permutation[j]
            for i in range(size)
            for j in range(i + 1, size)
        )
        product = Fraction((-1) ** inversions)
        for row, column in enumerate(permutation):
            product *= q(matrix[row][column])
        result += product
    return result


def vertex_oracle(cost, eq, er, le, lr):
    """Enumerate ALL vertices by active constraints and Cramer's rule.

    Nonnegativity makes this polyhedron pointed. Thus, if nonempty, it has
    a vertex; nonnegative cost also has a finite optimum attained at a vertex.
    Intended only for these tiny, rational, low-dimensional test problems.
    """
    size = len(cost)
    boundaries = list(zip((*eq, *le), (*er, *lr)))
    boundaries.extend((tuple(int(i == j) for j in range(size)), 0) for i in range(size))
    best = None
    for active in combinations(boundaries, size):
        matrix = [list(row) for row, _ in active]
        rhs = [q(value) for _, value in active]
        divisor = determinant(matrix)
        if not divisor:
            continue
        point = []
        for column in range(size):
            replaced = [row[:] for row in matrix]
            for row in range(size):
                replaced[row][column] = rhs[row]
            point.append(determinant(replaced) / divisor)
        if any(value < 0 for value in point):
            continue
        if any(scalar(row, point) != q(value) for row, value in zip(eq, er)):
            continue
        if any(scalar(row, point) > q(value) for row, value in zip(le, lr)):
            continue
        value = scalar(cost, point)
        best = value if best is None else min(best, value)
    return best


@pytest.mark.parametrize("seed", range(12))
def test_exact_simplex_matches_independent_exhaustive_vertex_oracle(seed):
    rng = random.Random(seed)
    # 360 mixed problems, including inconsistent rows and unbounded regions.
    # Random rational costs/coefficients exercise exact pivots and certificates.
    for _ in range(30):
        n = rng.randrange(1, 4)
        cost = tuple(Fraction(rng.randrange(4), rng.randrange(1, 4)) for _ in range(n))
        eq = tuple(
            tuple(rng.randrange(-2, 3) for _ in range(n))
            for _ in range(rng.randrange(3))
        )
        er = tuple(Fraction(rng.randrange(-3, 5), rng.randrange(1, 3)) for _ in eq)
        le = tuple(
            tuple(rng.randrange(-2, 3) for _ in range(n))
            for _ in range(rng.randrange(5))
        )
        lr = tuple(Fraction(rng.randrange(-3, 5), rng.randrange(1, 3)) for _ in le)
        expected = vertex_oracle(cost, eq, er, le, lr)
        report = solve_lp(
            cost, equalities=eq, equality_rhs=er, inequalities=le, inequality_rhs=lr
        )
        assert report.status == ("infeasible" if expected is None else "optimal"), (
            cost,
            eq,
            er,
            le,
            lr,
            report,
        )
        if expected is not None:
            assert q(report.objective) == expected
        check_certificate(report, cost, eq, er, le, lr)


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"costs": (-1,)}, ValueError),
        ({"costs": (True,)}, TypeError),
        ({"costs": (0.1,)}, TypeError),
        ({"costs": ((1, 0),)}, ValueError),
        ({"costs": ((1, True),)}, TypeError),
        ({"costs": ((1.0, 2),)}, TypeError),
        ({"costs": ((1, 2, 3),)}, TypeError),
        ({"costs": (1,), "equalities": ((1, 2),), "equality_rhs": (1,)}, ValueError),
        ({"costs": (1,), "equalities": ((1,),)}, ValueError),
        ({"costs": (1,), "inequality_rhs": (1,)}, ValueError),
        (
            {"costs": (1,), "inequalities": ((True,),), "inequality_rhs": (1,)},
            TypeError,
        ),
        ({"costs": (1,), "equalities": ((1,),), "equality_rhs": (1.0,)}, TypeError),
        ({"costs": (1,), "max_iterations": True}, TypeError),
        ({"costs": (1,), "max_iterations": 1.5}, TypeError),
        ({"costs": (1,), "max_iterations": -1}, ValueError),
    ],
)
def test_rejects_ambiguous_or_malformed_inputs(kwargs, error):
    with pytest.raises(error):
        solve_lp(**kwargs)


def test_iterable_inputs_are_materialized_once_and_report_is_immutable():
    report = solve_lp(
        (value for value in (2, 1)),
        equalities=((value for value in row) for row in ((1, 1),)),
        equality_rhs=(value for value in (1,)),
    )
    assert report.objective == (1, 1)
    with pytest.raises(FrozenInstanceError):
        report.status = "unknown"
