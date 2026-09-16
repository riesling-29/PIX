"""Exact linear algebra for ordinary weighted place/transition Petri nets.

The marking equation is a rational relaxation: a feasible solution need not
be integral, enabled in any order, or reachable. Enumeration limits produce
``unknown``, never an unproved optimum. No upstream solver is used.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from math import comb, gcd, lcm
from typing import Literal

from pix.contracts.models import Marking, PetriNet

Rational = tuple[int, int]
ExactCost = int | Fraction | Rational


@dataclass(frozen=True, slots=True)
class AlgebraInvariants:
    """Primitive integer basis of a rational nullspace, not its positive cone.

    Place vectors satisfy ``v^T C = 0``; transition vectors satisfy ``C v = 0``.
    Negative entries are allowed. An integer basis here spans the nullspace
    over the rationals, and is not necessarily an integer-lattice basis.
    """

    kind: Literal["place", "transition"]
    node_ids: tuple[str, ...]
    vectors: tuple[tuple[int, ...], ...]
    rank: int
    dimension: int


@dataclass(frozen=True, slots=True)
class MarkingEquationReport:
    """Result of minimizing nonnegative costs under ``C x = target-initial``.

    ``objective`` is the proven LP optimum and therefore a lower bound on
    costs of executable firing sequences, if any. ``incumbent_cost`` is only
    the cost of a feasible *relaxation* solution, not an executable sequence.
    The latter is an upper bound on this LP optimum, not on a reachable path.
    Every rational is an exact ``(numerator, denominator)`` pair.
    """

    status: Literal["optimal", "infeasible", "unknown"]
    transition_ids: tuple[str, ...]
    objective: Rational | None
    solution: tuple[Rational, ...] | None
    incumbent_cost: Rational | None
    bases_checked: int
    total_bases: int
    rank: int
    reason: str
    relaxation: str = "nonnegative_rational_marking_equation"
    reachability_proven: bool = False


def incidence_matrix(
    net: PetriNet,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[tuple[int, ...], ...]]:
    """Return sorted place IDs, transition IDs and output-minus-input weights."""
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    places = tuple(place.id for place in net.places)
    transitions = tuple(transition.id for transition in net.transitions)
    place_index = {name: index for index, name in enumerate(places)}
    transition_index = {name: index for index, name in enumerate(transitions)}
    matrix = [[0] * len(transitions) for _ in places]
    for arc in net.arcs:
        if arc.source in place_index:
            matrix[place_index[arc.source]][transition_index[arc.target]] -= arc.weight
        else:
            matrix[place_index[arc.target]][transition_index[arc.source]] += arc.weight
    return places, transitions, tuple(tuple(row) for row in matrix)


def _rref(
    rows: list[list[Fraction]],
    ncols: int,
) -> tuple[list[list[Fraction]], tuple[int, ...]]:
    """Eliminate only the first ncols columns, preserving an augmented RHS."""
    rows = [list(row) for row in rows]
    pivots: list[int] = []
    lead = 0
    for column in range(ncols):
        pivot = next((r for r in range(lead, len(rows)) if rows[r][column]), None)
        if pivot is None:
            continue
        rows[lead], rows[pivot] = rows[pivot], rows[lead]
        divisor = rows[lead][column]
        rows[lead] = [value / divisor for value in rows[lead]]
        for index, row in enumerate(rows):
            if index != lead and row[column]:
                factor = row[column]
                rows[index] = [a - factor * b for a, b in zip(row, rows[lead])]
        pivots.append(column)
        lead += 1
        if lead == len(rows):
            break
    return rows, tuple(pivots)


def _primitive(vector: list[Fraction]) -> tuple[int, ...]:
    denominator = lcm(*(value.denominator for value in vector))
    integers = [
        value.numerator * (denominator // value.denominator) for value in vector
    ]
    divisor = gcd(*integers)
    if divisor:
        integers = [value // divisor for value in integers]
    first = next((value for value in integers if value), 0)
    if first < 0:
        integers = [-value for value in integers]
    return tuple(integers)


def invariants(
    net: PetriNet,
    kind: Literal["place", "transition"] = "place",
) -> AlgebraInvariants:
    """Compute a complete rational nullspace basis by exact row reduction."""
    if kind not in ("place", "transition"):
        raise ValueError("kind must be 'place' or 'transition'")
    places, transitions, incidence = incidence_matrix(net)
    if kind == "place":
        nodes = places
        rows = [
            [Fraction(incidence[p][t]) for p in range(len(places))]
            for t in range(len(transitions))
        ]
    else:
        nodes = transitions
        rows = [[Fraction(value) for value in row] for row in incidence]
    reduced, pivots = _rref(rows, len(nodes))
    vectors: list[tuple[int, ...]] = []
    for free in (column for column in range(len(nodes)) if column not in pivots):
        vector = [Fraction(0) for _ in nodes]
        vector[free] = Fraction(1)
        for row, pivot in enumerate(pivots):
            vector[pivot] = -reduced[row][free]
        vectors.append(_primitive(vector))
    return AlgebraInvariants(kind, nodes, tuple(vectors), len(pivots), len(vectors))


def _fraction(value: ExactCost) -> Fraction:
    if isinstance(value, bool):
        raise TypeError("transition costs must be exact rationals, not bool")
    if isinstance(value, (int, Fraction)):
        result = Fraction(value)
    elif isinstance(value, tuple) and len(value) == 2:
        if not all(
            isinstance(item, int) and not isinstance(item, bool) for item in value
        ):
            raise TypeError("rational costs require two integer components")
        if value[1] == 0:
            raise ValueError("cost denominator must not be zero")
        result = Fraction(*value)
    else:
        raise TypeError(
            "transition costs must be int, Fraction, or (numerator, denominator)"
        )
    if result < 0:
        raise ValueError("transition costs must be nonnegative")
    return result


def _pair(value: Fraction) -> Rational:
    return value.numerator, value.denominator


def marking_equation(
    net: PetriNet,
    initial: Marking | None = None,
    target: Marking | None = None,
    costs: Mapping[str, ExactCost] | None = None,
    max_bases: int = 100_000,
) -> MarkingEquationReport:
    """Solve the nonnegative rational marking-equation LP by vertex enumeration.

    Omitted markings use the accepting net's markings. Omitted transition
    costs default to one; unknown transition IDs are rejected. ``max_bases``
    limits checked column subsets, including singular subsets. Exceeding it
    returns unknown without an objective, even if a feasible vertex was found.

    Rational feasibility is necessary, but not sufficient, for reachability.
    Enumeration is intended for small nets; its number of candidates is
    ``binomial(number_of_transitions, rank(C))``.
    """
    places, transitions, incidence = incidence_matrix(net)
    if not isinstance(max_bases, int) or isinstance(max_bases, bool):
        raise TypeError("max_bases must be a positive integer")
    if max_bases < 1:
        raise ValueError("max_bases must be a positive integer")
    initial = net.initial_marking if initial is None else initial
    target = net.final_marking if target is None else target
    net.validate_marking(initial)
    net.validate_marking(target)
    if costs is not None and not isinstance(costs, Mapping):
        raise TypeError("costs must be a mapping keyed by transition ID")
    costs = {} if costs is None else costs
    if any(key not in transitions for key in costs):
        raise ValueError("costs reference an unknown transition")
    weights = tuple(_fraction(costs.get(transition, 1)) for transition in transitions)
    initial_tokens, target_tokens = dict(initial.tokens), dict(target.tokens)
    ncols = len(transitions)
    augmented = [
        [Fraction(value) for value in row]
        + [Fraction(target_tokens.get(place, 0) - initial_tokens.get(place, 0))]
        for place, row in zip(places, incidence)
    ]
    reduced, pivots = _rref(augmented, ncols)
    rank = len(pivots)
    total = comb(ncols, rank)
    if any(not any(row[:ncols]) and row[ncols] for row in reduced):
        return MarkingEquationReport(
            "infeasible",
            transitions,
            None,
            None,
            None,
            0,
            total,
            rank,
            "inconsistent_linear_equalities",
        )
    if rank == 0:
        zero = tuple((0, 1) for _ in transitions)
        return MarkingEquationReport(
            "optimal",
            transitions,
            (0, 1),
            zero,
            (0, 1),
            0,
            total,
            0,
            "zero_vector_is_optimal_for_nonnegative_costs",
        )
    equations = reduced[:rank]
    best_cost: Fraction | None = None
    best_solution: tuple[Fraction, ...] | None = None
    checked = 0
    for columns in combinations(range(ncols), rank):
        if checked >= max_bases:
            break
        checked += 1
        square = [
            [row[column] for column in columns] + [row[ncols]] for row in equations
        ]
        solved, local_pivots = _rref(square, rank)
        if len(local_pivots) < rank:
            continue
        basic = tuple(row[rank] for row in solved)
        if any(value < 0 for value in basic):
            continue
        solution = [Fraction(0) for _ in transitions]
        for column, value in zip(columns, basic):
            solution[column] = value
        candidate = tuple(solution)
        objective = sum(
            (weight * value for weight, value in zip(weights, candidate)), Fraction(0)
        )
        if best_cost is None or objective < best_cost:
            best_cost, best_solution = objective, candidate
    complete = checked == total
    if not complete:
        status, reason = "unknown", "max_bases_exhausted"
    elif best_solution is None:
        status, reason = "infeasible", "no_nonnegative_basic_feasible_solution"
    else:
        status, reason = "optimal", "all_bases_examined"
    return MarkingEquationReport(
        status,
        transitions,
        _pair(best_cost) if status == "optimal" and best_cost is not None else None,
        tuple(_pair(value) for value in best_solution)
        if best_solution is not None
        else None,
        _pair(best_cost) if best_cost is not None else None,
        checked,
        total,
        rank,
        reason,
    )


__all__ = [
    "AlgebraInvariants",
    "MarkingEquationReport",
    "incidence_matrix",
    "invariants",
    "marking_equation",
]
