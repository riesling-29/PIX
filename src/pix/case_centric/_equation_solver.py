"""Exact nonnegative LP relaxation solver; feasibility never proves reachability.

This dependency-free solver minimizes ``costs @ x`` with ``x >= 0``,
``equalities @ x == equality_rhs`` and ``inequalities @ x <= inequality_rhs``.
It uses a two-phase rational simplex with Bland's pivot rule. Every claimed
optimum or infeasibility is checked against the original input using exact
primal/dual or Farkas certificates. No floating-point tolerance is used.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

Rational = tuple[int, int]
ExactNumber = int | Fraction | Rational


@dataclass(frozen=True, slots=True)
class LPReport:
    """Exact LP result, independent of Petri-net execution semantics.

    ``objective`` is present only for a certified optimum. When a limit is
    reached, ``solution`` and ``incumbent_cost`` may describe a feasible LP
    point: its cost is an upper bound on the LP optimum, not a certified lower
    bound and not the cost of an executable firing sequence. ``iterations``
    and ``pivots`` both count basis pivots, including phase-one cleanup.

    For optimal results the dual multipliers certify a matching lower bound.
    For infeasible results they certify ``A.T @ y <= 0, b @ y > 0``;
    inequality multipliers are nonpositive in both cases. Multipliers refer
    to the original rows, including redundant rows, in their input order.
    """

    status: Literal["optimal", "infeasible", "unknown"]
    objective: Rational | None
    solution: tuple[Rational, ...] | None
    incumbent_cost: Rational | None
    pivots: int
    iterations: int
    reason: str
    dual_equalities: tuple[Rational, ...] | None
    dual_inequalities: tuple[Rational, ...] | None
    certificate_validated: bool
    certificate_kind: Literal[
        "primal_dual_optimal", "farkas_infeasible", "feasible_incumbent", "none"
    ]


def _exact(value: ExactNumber) -> Fraction:
    if isinstance(value, bool):
        raise TypeError("LP numbers must be exact rationals, not bool")
    if isinstance(value, (int, Fraction)):
        return Fraction(value)
    if isinstance(value, tuple) and len(value) == 2:
        if any(not isinstance(part, int) or isinstance(part, bool) for part in value):
            raise TypeError("rational pairs must contain two integers")
        if value[1] == 0:
            raise ValueError("rational denominator must not be zero")
        return Fraction(*value)
    raise TypeError("LP numbers must be int, Fraction, or (numerator, denominator)")


def _pair(value: Fraction) -> Rational:
    return value.numerator, value.denominator


def _dot(left: Iterable[Fraction], right: Iterable[Fraction]) -> Fraction:
    return sum((a * b for a, b in zip(left, right)), Fraction(0))


def _pivot(
    rows: list[list[Fraction]],
    basis: list[int],
    transform: list[list[Fraction]],
    leaving: int,
    entering: int,
) -> None:
    divisor = rows[leaving][entering]
    rows[leaving] = [value / divisor for value in rows[leaving]]
    transform[leaving] = [value / divisor for value in transform[leaving]]
    for index in range(len(rows)):
        if index == leaving or not rows[index][entering]:
            continue
        factor = rows[index][entering]
        rows[index] = [a - factor * b for a, b in zip(rows[index], rows[leaving])]
        transform[index] = [
            a - factor * b for a, b in zip(transform[index], transform[leaving])
        ]
    basis[leaving] = entering


def _minimize(
    rows: list[list[Fraction]],
    basis: list[int],
    transform: list[list[Fraction]],
    costs: tuple[Fraction, ...],
    pivots: int,
    limit: int,
) -> tuple[str, int]:
    """Optimize a feasible canonical tableau, counting only basis pivots."""
    while True:
        basic_costs = [costs[column] for column in basis]
        entering = next(
            (
                column
                for column, cost in enumerate(costs)
                if cost - _dot(basic_costs, (row[column] for row in rows)) < 0
            ),
            None,
        )
        if entering is None:
            return "optimal", pivots
        if pivots >= limit:
            return "iteration_limit", pivots
        candidates = [i for i, row in enumerate(rows) if row[entering] > 0]
        if not candidates:
            # Nonnegative original/phase-one costs make this unreachable for
            # valid input. Never turn an internal inconsistency into a claim.
            return "unexpected_unbounded_tableau", pivots
        leaving = min(
            candidates, key=lambda i: (rows[i][-1] / rows[i][entering], basis[i])
        )
        _pivot(rows, basis, transform, leaving, entering)
        pivots += 1


def solve_lp(
    costs: Iterable[ExactNumber],
    *,
    equalities: Iterable[Iterable[ExactNumber]] = (),
    equality_rhs: Iterable[ExactNumber] = (),
    inequalities: Iterable[Iterable[ExactNumber]] = (),
    inequality_rhs: Iterable[ExactNumber] = (),
    max_iterations: int = 10_000,
) -> LPReport:
    """Solve a rational LP with nonnegative variables and objective costs.

    Coefficients and RHS values may be signed; costs must be nonnegative.
    Floats, booleans, malformed matrices and negative iteration limits are
    rejected. A zero limit still permits proofs requiring no basis pivot.
    The limit is a pivot budget, not a wall-clock or memory limit.
    """
    if not isinstance(max_iterations, int) or isinstance(max_iterations, bool):
        raise TypeError("max_iterations must be an integer")
    if max_iterations < 0:
        raise ValueError("max_iterations must be nonnegative")
    cost = tuple(_exact(value) for value in costs)
    if any(value < 0 for value in cost):
        raise ValueError("LP costs must be nonnegative")
    eq = tuple(tuple(_exact(value) for value in row) for row in equalities)
    le = tuple(tuple(_exact(value) for value in row) for row in inequalities)
    eq_rhs = tuple(_exact(value) for value in equality_rhs)
    le_rhs = tuple(_exact(value) for value in inequality_rhs)
    n = len(cost)
    if any(len(row) != n for row in (*eq, *le)):
        raise ValueError("every LP constraint row must have one entry per variable")
    if len(eq) != len(eq_rhs) or len(le) != len(le_rhs):
        raise ValueError("each constraint must have exactly one RHS entry")

    original = (*eq, *le)
    rhs = (*eq_rhs, *le_rhs)
    m = len(original)
    signs = tuple(Fraction(-1 if value < 0 else 1) for value in rhs)
    real_columns = n + len(le)
    artificial_rows = [i for i in range(m) if i < len(eq) or signs[i] < 0]
    artificial = {row: real_columns + j for j, row in enumerate(artificial_rows)}
    column_count = real_columns + len(artificial_rows)
    rows: list[list[Fraction]] = []
    transform: list[list[Fraction]] = []
    basis: list[int] = []
    for index, values in enumerate(original):
        row = [signs[index] * value for value in values]
        row.extend(Fraction(0) for _ in range(column_count - n))
        if index >= len(eq):
            row[n + index - len(eq)] = signs[index]
        if index in artificial:
            row[artificial[index]] = Fraction(1)
            basis.append(artificial[index])
        else:
            basis.append(n + index - len(eq))
        row.append(signs[index] * rhs[index])
        rows.append(row)
        transform.append([Fraction(index == j) for j in range(m)])

    def primal_solution() -> tuple[Fraction, ...]:
        solution = [Fraction(0) for _ in range(n)]
        for row, column in zip(rows, basis):
            if column < n:
                solution[column] = row[-1]
        return tuple(solution)

    def feasible(solution: tuple[Fraction, ...]) -> bool:
        return (
            all(value >= 0 for value in solution)
            and all(_dot(row, solution) == value for row, value in zip(eq, eq_rhs))
            and all(_dot(row, solution) <= value for row, value in zip(le, le_rhs))
        )

    def dual_multipliers(objective: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
        basic_costs = [objective[column] for column in basis]
        return tuple(
            signs[j] * _dot(basic_costs, (row[j] for row in transform))
            for j in range(m)
        )

    def dual_feasible(dual: tuple[Fraction, ...], upper: tuple[Fraction, ...]) -> bool:
        return all(value <= 0 for value in dual[len(eq) :]) and all(
            _dot(dual, (row[j] for row in original)) <= upper[j] for j in range(n)
        )

    def unknown(reason: str, pivots: int) -> LPReport:
        solution = primal_solution()
        valid = feasible(solution)
        return LPReport(
            "unknown",
            None,
            tuple(map(_pair, solution)) if valid else None,
            _pair(_dot(cost, solution)) if valid else None,
            pivots,
            pivots,
            reason,
            None,
            None,
            valid,
            "feasible_incumbent" if valid else "none",
        )

    pivots = 0
    if artificial_rows:
        phase_one_cost = tuple(Fraction(j >= real_columns) for j in range(column_count))
        status, pivots = _minimize(
            rows, basis, transform, phase_one_cost, pivots, max_iterations
        )
        if status != "optimal":
            return unknown(f"phase_one_{status}", pivots)
        phase_one_value = _dot(
            (phase_one_cost[j] for j in basis), (row[-1] for row in rows)
        )
        if phase_one_value > 0:
            dual = dual_multipliers(phase_one_cost)
            valid = dual_feasible(dual, (Fraction(0),) * n) and _dot(dual, rhs) > 0
            if not valid:
                return unknown("infeasibility_certificate_failed", pivots)
            return LPReport(
                "infeasible",
                None,
                None,
                None,
                pivots,
                pivots,
                "positive_phase_one_optimum_with_farkas_certificate",
                tuple(map(_pair, dual[: len(eq)])),
                tuple(map(_pair, dual[len(eq) :])),
                True,
                "farkas_infeasible",
            )
        if phase_one_value != 0:
            return unknown("invalid_phase_one_objective", pivots)

        # A zero artificial basic variable must leave before phase two. An
        # arbitrary nonzero real coefficient is safe here because its RHS is
        # zero. Rows with no such coefficient are redundant and are removed;
        # their effect remains represented by the row transformation matrix.
        index = 0
        while index < len(rows):
            if basis[index] < real_columns:
                index += 1
                continue
            entering = next((j for j in range(real_columns) if rows[index][j]), None)
            if entering is None:
                del rows[index], basis[index], transform[index]
                continue
            if pivots >= max_iterations:
                return unknown("phase_one_cleanup_iteration_limit", pivots)
            _pivot(rows, basis, transform, index, entering)
            pivots += 1
            index += 1
        rows = [row[:real_columns] + [row[-1]] for row in rows]

    phase_two_cost = cost + (Fraction(0),) * len(le)
    status, pivots = _minimize(
        rows, basis, transform, phase_two_cost, pivots, max_iterations
    )
    if status != "optimal":
        return unknown(f"phase_two_{status}", pivots)
    solution = primal_solution()
    dual = dual_multipliers(phase_two_cost)
    value = _dot(cost, solution)
    if not (
        feasible(solution) and dual_feasible(dual, cost) and value == _dot(dual, rhs)
    ):
        return unknown("optimality_certificate_failed", pivots)
    return LPReport(
        "optimal",
        _pair(value),
        tuple(map(_pair, solution)),
        _pair(value),
        pivots,
        pivots,
        "exact_primal_dual_certificate",
        tuple(map(_pair, dual[: len(eq)])),
        tuple(map(_pair, dual[len(eq) :])),
        True,
        "primal_dual_optimal",
    )
