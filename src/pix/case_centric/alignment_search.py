"""State-equation A* and exact rational finite-horizon discounted alignment.

The heuristic is a continuous synchronous-product marking-equation relaxation.
SciPy is only a generic optional LP solver. Its floating objective is never used
as an admissible bound: a reconstructed rational dual must satisfy every dual
inequality exactly. Otherwise the explicit conservative bound is zero. The
default is PIX's exact rational simplex, with checked dual/Farkas certificates.
Exact vertex enumeration remains available for small independent comparisons.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from importlib import import_module
from itertools import count
from math import isfinite
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import AlignmentMove, AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

Rational = tuple[int, int]


def _positive(value: object, field: str):
    if type(value) is not int or value < 1:
        raise ValueError(field + " must be a positive integer")


def _pair(value: Fraction) -> Rational:
    return value.numerator, value.denominator


@dataclass(frozen=True, slots=True)
class StateEquationAStarSpec:
    """LP budgets are per trace; a limited heuristic becomes a certified zero.

    The alignment state budget counts expansions, including reopenings. The
    default simplex solver uses rational arithmetic and a per-LP pivot budget.
    Vertex enumeration remains explicit; generic SciPy is an optional backend
    whose numerical objective alone is never trusted.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    backend: Literal["scipy_highs", "exact_vertices", "exact_simplex"] = "exact_simplex"
    max_bases: int = 10000
    max_matrix_cells: int = 2_000_000
    max_lp_solves: int = 10000
    dual_max_denominator: int = 1_000_000
    lp_time_limit_seconds: float = 10.0
    max_lp_iterations: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.alignment, AlignmentSpec):
            raise TypeError("alignment must be AlignmentSpec")
        if self.backend not in ("scipy_highs", "exact_vertices", "exact_simplex"):
            raise ValueError("unsupported LP backend")
        for field in (
            "max_bases",
            "max_matrix_cells",
            "max_lp_solves",
            "dual_max_denominator",
            "max_lp_iterations",
        ):
            _positive(getattr(self, field), field)
        if (
            type(self.lp_time_limit_seconds) is not float
            or not isfinite(self.lp_time_limit_seconds)
            or self.lp_time_limit_seconds <= 0
        ):
            raise ValueError("lp_time_limit_seconds must be a positive finite float")


@dataclass(frozen=True, slots=True)
class DiscountedAStarSpec:
    """Sum(base move cost * discount**zero_based_move_index), within max_moves.

    Depth is part of the search state. Silent and synchronous firings also
    advance depth, whether their base cost is zero or positive. The finite
    horizon is semantic: infinite discounted languages may lack an attained
    minimum. No unbounded discounted optimality is claimed.
    """

    max_moves: int
    discount: Rational = (1, 2)
    search: StateEquationAStarSpec = StateEquationAStarSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if type(self.max_moves) is not int or self.max_moves < 0:
            raise ValueError("max_moves must be a nonnegative integer")
        if (
            not isinstance(self.discount, tuple)
            or len(self.discount) != 2
            or any(type(x) is not int for x in self.discount)
        ):
            raise TypeError("discount must be an integer numerator/denominator pair")
        if not 0 < self.discount[0] <= self.discount[1]:
            raise ValueError("discount requires 0 < numerator <= denominator")
        object.__setattr__(self, "discount", _pair(Fraction(*self.discount)))
        if not isinstance(self.search, StateEquationAStarSpec):
            raise TypeError("search must be StateEquationAStarSpec")


@dataclass(frozen=True, slots=True)
class StateEquationRequest:
    model_digest: str
    parameters: StateEquationAStarSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DiscountedAlignmentRequest:
    model_digest: str
    parameters: DiscountedAStarSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class StateEquationBound:
    position: int
    marking: tuple[tuple[str, int], ...]
    integer_lower_bound: int
    infeasibility_proven: bool
    certificate_status: str
    exact_objective: Rational | None
    dual_rows: tuple[str, ...]
    dual_values: tuple[Rational, ...] | None
    lp_iterations: int | None = None
    certificate_kind: str | None = None


@dataclass(frozen=True, slots=True)
class SearchAlignment:
    case_id: str
    event_ids: tuple[str, ...]
    status: Literal[
        "optimal",
        "unreachable",
        "search_limit",
        "optimal_within_horizon",
        "unreachable_within_horizon",
    ]
    moves: tuple[AlignmentMove, ...]
    step_costs: tuple[Rational, ...]
    cost: Rational | None
    lower_bound_cost: Rational | None
    expanded_states: int
    discovered_states: int
    reopened_states: int
    heuristic_evidence: tuple[StateEquationBound, ...]


@dataclass(frozen=True, slots=True)
class SearchAlignmentSet:
    model_digest: str
    backend: str
    backend_version: str
    traces: tuple[SearchAlignment, ...]
    requested_count: int
    optimal_count: int
    unreachable_count: int
    limited_count: int
    total_cost: Rational | None
    cost_profile: str
    max_moves: int | None


def _state_equation(
    net: PetriNet,
    trace: ObjectTrace,
    position: int,
    marking: Marking,
    spec: StateEquationAStarSpec,
):
    """Net-token balance plus one equality per remaining event occurrence.

    Variables: model firings, each log-only move, each matching event/transition
    synchronous firing. The trace-chain marking equation is equivalently one
    unit consumed per remaining event; ordering/enabling are relaxed, never
    asserted by LP feasibility.
    """
    remaining = trace.events[position:]
    transitions = net.transitions
    by_label: dict[str, list[int]] = {}
    for index, transition in enumerate(transitions):
        if transition.activity is not None:
            by_label.setdefault(transition.activity, []).append(index)
    row_count = len(net.places) + len(remaining)
    match_count = sum(len(by_label.get(event.activity, ())) for event in remaining)
    column_count = len(transitions) + len(remaining) + match_count
    cells = row_count * column_count
    if spec.backend == "exact_simplex" and row_count and column_count:
        # Phase one adds one artificial variable per equality; preserving
        # original-row certificates also requires a square row-transform
        # matrix. Bound that workspace before constructing the relaxation.
        cells = row_count * (column_count + 2 * row_count + 1)
    if cells > spec.max_matrix_cells:
        return None
    matches = tuple(
        (event_index, transition_index)
        for event_index, event in enumerate(remaining)
        for transition_index in by_label.get(event.activity, ())
    )
    place_index = {place.id: i for i, place in enumerate(net.places)}
    transition_index = {transition.id: i for i, transition in enumerate(transitions)}
    incidence = [[0] * len(transitions) for _ in net.places]
    for arc in net.arcs:
        if arc.source in place_index:
            incidence[place_index[arc.source]][transition_index[arc.target]] -= (
                arc.weight
            )
        else:
            incidence[place_index[arc.target]][transition_index[arc.source]] += (
                arc.weight
            )
    columns = []
    costs = []
    for index, transition in enumerate(transitions):
        columns.append([row[index] for row in incidence] + [0] * len(remaining))
        costs.append(
            spec.alignment.silent_move_cost
            if transition.activity is None
            else spec.alignment.model_move_cost
        )
    for index in range(len(remaining)):
        columns.append(
            [0] * len(net.places) + [int(i == index) for i in range(len(remaining))]
        )
        costs.append(spec.alignment.log_move_cost)
    for event_index, transition_index in matches:
        columns.append(
            [row[transition_index] for row in incidence]
            + [int(i == event_index) for i in range(len(remaining))]
        )
        costs.append(spec.alignment.synchronous_move_cost)
    matrix = tuple(tuple(column[row] for column in columns) for row in range(row_count))
    current, target = dict(marking.tokens), dict(net.final_marking.tokens)
    rhs = tuple(
        target.get(place.id, 0) - current.get(place.id, 0) for place in net.places
    ) + (1,) * len(remaining)
    row_names = tuple("place:" + place.id for place in net.places) + tuple(
        "event:" + event.event_id for event in remaining
    )
    return matrix, rhs, tuple(costs), row_names


def _certify_dual(matrix, rhs, costs, approximate, max_denominator):
    """Return an exact feasible dual certificate or None; no tolerance proof."""
    if len(approximate) != len(rhs):
        return None
    try:
        dual = tuple(
            Fraction(float(value)).limit_denominator(max_denominator)
            for value in approximate
        )
    except (ValueError, OverflowError, TypeError):
        return None
    return _certify_exact_dual(matrix, rhs, costs, dual)


def _certify_exact_dual(matrix, rhs, costs, dual):
    """Check an exact lower-bound dual; zero costs also check Farkas columns."""
    if len(dual) != len(rhs):
        return None
    for column, cost in enumerate(costs):
        if (
            sum(
                (Fraction(row[column]) * value for row, value in zip(matrix, dual)),
                Fraction(),
            )
            > cost
        ):
            return None
    objective = sum(
        (Fraction(value) * coefficient for value, coefficient in zip(rhs, dual)),
        Fraction(),
    )
    return objective, dual


def _exact_lp(matrix, rhs, costs, max_bases):
    # A synthetic incidence-only net encodes the *relaxation*, not a discovered
    # executable model. Public exact arithmetic helper certifies optimum/status.
    from pix.case_centric._model_algebra import marking_equation

    places = tuple(Place(f"r{i:08d}") for i in range(len(rhs)))
    transitions = tuple(Transition(f"x{i:08d}") for i in range(len(costs)))
    arcs = tuple(
        Arc(places[row].id, transitions[column].id, -value)
        if value < 0
        else Arc(transitions[column].id, places[row].id, value)
        for row, values in enumerate(matrix)
        for column, value in enumerate(values)
        if value
    )
    initial = Marking(
        tuple((places[i].id, -value) for i, value in enumerate(rhs) if value < 0)
    )
    final = Marking(
        tuple((places[i].id, value) for i, value in enumerate(rhs) if value > 0)
    )
    net = PetriNet(places, transitions, arcs, initial, final)
    return marking_equation(
        net,
        costs={transition.id: cost for transition, cost in zip(transitions, costs)},
        max_bases=max_bases,
    )


class _LPBackendUnavailable(Exception):
    """The explicitly requested backend cannot execute in this environment."""


class _Bounder:
    def __init__(self, net, trace, spec, solver):
        self.net, self.trace, self.spec, self.solver = net, trace, spec, solver
        self.evidence = {}
        self.solves = 0

    def bound(self, position, marking):
        key = position, marking
        if key in self.evidence:
            return self.evidence[key]
        status = "heuristic_solve_limit_zero_bound"
        objective = None
        dual = None
        rows = ()
        infeasible = False
        lower = 0
        iterations = None
        certificate_kind = None
        if self.solves < self.spec.max_lp_solves:
            problem = _state_equation(
                self.net, self.trace, position, marking, self.spec
            )
            if problem is None:
                status = "heuristic_matrix_limit_zero_bound"
            else:
                matrix, rhs, costs, rows = problem
                self.solves += 1
                if not costs:
                    infeasible = any(rhs)
                    status = "exact_infeasible" if infeasible else "exact_optimum"
                    objective = None if infeasible else Fraction()
                elif not rows:
                    status, objective = "exact_optimum", Fraction()
                elif self.spec.backend == "exact_simplex":
                    result = self.solver(
                        costs,
                        equalities=matrix,
                        equality_rhs=rhs,
                        max_iterations=self.spec.max_lp_iterations,
                    )
                    iterations = result.iterations
                    status = "simplex_unknown_zero_bound"
                    # A feasible incumbent is an upper bound on the LP optimum,
                    # never an admissible path lower bound. Accept only the
                    # matching original-row certificate, checked exactly again
                    # at the search boundary before rounding or pruning.
                    if result.status in ("optimal", "infeasible"):
                        status = "simplex_uncertified_zero_bound"
                        expected_kind = (
                            "primal_dual_optimal"
                            if result.status == "optimal"
                            else "farkas_infeasible"
                        )
                        if (
                            result.certificate_validated
                            and result.certificate_kind == expected_kind
                            and result.dual_equalities is not None
                        ):
                            exact_dual = tuple(
                                Fraction(*value) for value in result.dual_equalities
                            )
                            certificate = _certify_exact_dual(
                                matrix,
                                rhs,
                                costs
                                if result.status == "optimal"
                                else (0,) * len(costs),
                                exact_dual,
                            )
                            if certificate is not None:
                                dual_objective, checked_dual = certificate
                                if (
                                    result.status == "optimal"
                                    and result.objective is not None
                                    and dual_objective == Fraction(*result.objective)
                                ):
                                    status = "exact_optimum"
                                    objective = dual_objective
                                    dual = checked_dual
                                    certificate_kind = expected_kind
                                elif (
                                    result.status == "infeasible" and dual_objective > 0
                                ):
                                    status, infeasible = "exact_infeasible", True
                                    dual = checked_dual
                                    certificate_kind = expected_kind
                elif self.spec.backend == "exact_vertices":
                    result = _exact_lp(matrix, rhs, costs, self.spec.max_bases)
                    status = {
                        "optimal": "exact_optimum",
                        "infeasible": "exact_infeasible",
                        "unknown": "exact_vertex_limit_zero_bound",
                    }[result.status]
                    infeasible = result.status == "infeasible"
                    objective = (
                        Fraction(*result.objective)
                        if result.objective is not None
                        else None
                    )
                else:
                    try:
                        result = self.solver(
                            costs,
                            A_eq=matrix,
                            b_eq=rhs,
                            bounds=(0, None),
                            method="highs",
                            options={"time_limit": self.spec.lp_time_limit_seconds},
                        )
                    except (ImportError, OSError) as error:
                        raise _LPBackendUnavailable(type(error).__name__) from error
                    except (ValueError, RuntimeError, OverflowError):
                        result = None
                    status = "solver_failure_zero_bound"
                    if result is not None and result.success:
                        certificate = _certify_dual(
                            matrix,
                            rhs,
                            costs,
                            result.eqlin.marginals,
                            self.spec.dual_max_denominator,
                        )
                        if certificate is not None:
                            objective, dual = certificate
                            status = "certified_dual"
                        else:
                            status = "uncertified_dual_zero_bound"
                    elif result is not None and result.status == 2:
                        # Floating solver status is not an exact Farkas proof.
                        status = "solver_infeasible_unverified_zero_bound"
        if objective is not None:
            lower = max(0, -(-objective.numerator // objective.denominator))
        record = StateEquationBound(
            position,
            marking.tokens,
            lower,
            infeasible,
            status,
            _pair(objective) if objective is not None else None,
            rows,
            tuple(_pair(value) for value in dual) if dual is not None else None,
            iterations,
            certificate_kind,
        )
        self.evidence[key] = record
        return record


def _moves(net, trace, position, marking, costs):
    labels = {transition.id: transition.activity for transition in net.transitions}
    options = []
    for transition in enabled_transitions(net, marking):
        label = labels[transition]
        after = fire(net, marking, transition)
        if label is None:
            options.append(
                (
                    1,
                    transition,
                    position,
                    after,
                    AlignmentMove(
                        "silent",
                        None,
                        transition,
                        None,
                        costs.silent_move_cost,
                        marking.tokens,
                        after.tokens,
                    ),
                )
            )
        else:
            if (
                position < len(trace.events)
                and trace.events[position].activity == label
            ):
                options.append(
                    (
                        0,
                        transition,
                        position + 1,
                        after,
                        AlignmentMove(
                            "synchronous",
                            trace.events[position].event_id,
                            transition,
                            label,
                            costs.synchronous_move_cost,
                            marking.tokens,
                            after.tokens,
                        ),
                    )
                )
            options.append(
                (
                    2,
                    transition,
                    position,
                    after,
                    AlignmentMove(
                        "model",
                        None,
                        transition,
                        label,
                        costs.model_move_cost,
                        marking.tokens,
                        after.tokens,
                    ),
                )
            )
    if position < len(trace.events):
        event = trace.events[position]
        options.append(
            (
                3,
                "",
                position + 1,
                marking,
                AlignmentMove(
                    "log",
                    event.event_id,
                    None,
                    event.activity,
                    costs.log_move_cost,
                    marking.tokens,
                    marking.tokens,
                ),
            )
        )
    return tuple(
        (position, marking, move)
        for _, _, position, marking, move in sorted(options, key=lambda item: item[:2])
    )


def _search(trace, net, spec, solver, discounted=None):
    bounder = _Bounder(net, trace, spec, solver)
    horizon = discounted.max_moves if discounted is not None else None
    gamma = Fraction(*discounted.discount) if discounted is not None else Fraction(1)
    # Any future step costs at least gamma**(H-1) times its undiscounted cost.
    heuristic_scale = (
        gamma ** max(0, horizon - 1) if horizon is not None else Fraction(1)
    )
    initial = (0, net.initial_marking, 0)
    best = {initial: Fraction()}
    expanded = {}
    parents = {}
    serial = count()
    first = bounder.bound(0, net.initial_marking)
    heap = (
        []
        if first.infeasibility_proven
        else [
            (
                heuristic_scale * first.integer_lower_bound,
                Fraction(),
                next(serial),
                initial,
            )
        ]
    )
    expansion_count = reopened = 0

    def finish(status, state=None, cost=None, lower=None):
        path, step_costs = [], []
        while state is not None and state != initial:
            before, move, step_cost = parents[state]
            path.append(move)
            step_costs.append(_pair(step_cost))
            state = before
        return SearchAlignment(
            trace.object_id,
            tuple(event.event_id for event in trace.events),
            status,
            tuple(reversed(path)),
            tuple(reversed(step_costs)),
            _pair(cost) if cost is not None else None,
            _pair(lower) if lower is not None else None,
            expansion_count,
            len(best),
            reopened,
            tuple(bounder.evidence.values()),
        )

    while heap:
        priority, cost, _, state = heappop(heap)
        if best[state] != cost or (state in expanded and expanded[state] <= cost):
            continue
        if expansion_count >= spec.alignment.max_states:
            return finish("search_limit", lower=priority)
        expansion_count += 1
        if state in expanded:
            reopened += 1
        expanded[state] = cost
        position, marking, depth = state
        if position == len(trace.events) and marking == net.final_marking:
            return finish(
                "optimal_within_horizon" if horizon is not None else "optimal",
                state,
                cost,
                cost,
            )
        if horizon is not None and depth >= horizon:
            continue
        for following_position, following_marking, move in _moves(
            net, trace, position, marking, spec.alignment
        ):
            following_depth = depth + 1 if horizon is not None else 0
            following = following_position, following_marking, following_depth
            step_cost = Fraction(move.cost) * gamma**depth
            candidate = cost + step_cost
            if following in best and candidate >= best[following]:
                continue
            estimate = bounder.bound(following_position, following_marking)
            if estimate.infeasibility_proven:
                continue
            best[following] = candidate
            parents[following] = state, move, step_cost
            heappush(
                heap,
                (
                    candidate + heuristic_scale * estimate.integer_lower_bound,
                    candidate,
                    next(serial),
                    following,
                ),
            )
    return finish(
        "unreachable_within_horizon" if horizon is not None else "unreachable"
    )


def _backend(spec):
    if spec.backend == "exact_simplex":
        from pix.case_centric._equation_solver import solve_lp

        return solve_lp, "pix_exact_rational_simplex_v1"
    if spec.backend == "exact_vertices":
        return None, "pix_exact_rational_vertices_v1"
    package = import_module("scipy")
    solver = import_module("scipy.optimize").linprog
    return solver, str(package.__version__)


def _apply(log, net, spec, discounted):
    source = as_case_traces(log)
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    digest = model_digest(net)
    operator = (
        "pix.case_centric.discounted_astar"
        if discounted is not None
        else "pix.case_centric.state_equation_astar"
    )
    request = (
        DiscountedAlignmentRequest(digest, discounted)
        if discounted is not None
        else StateEquationRequest(digest, spec)
    )
    parents = (source.computation_id,) if source.computation_id is not None else ()

    def result(status, value, issues=()):
        return _result(
            operator,
            None,
            request,
            status,
            value,
            source.issues + tuple(issues),
            source_digest=source.source_digest,
            parent_computation_ids=parents,
        )

    if source.status is not ComputeStatus.COMPUTED or not isinstance(
        source.value, TraceSet
    ):
        return result(
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "trace_result_unavailable", "Completed traces are required"
                ),
            ),
        )
    try:
        solver, version = _backend(spec)
    except (ImportError, OSError) as error:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "lp_backend_unavailable",
                    "Requested optional LP backend is unavailable: "
                    + type(error).__name__,
                ),
            ),
        )
    try:
        traces = tuple(
            _search(trace, net, spec, solver, discounted)
            for trace in source.value.traces
        )
    except _LPBackendUnavailable as error:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "lp_backend_unavailable",
                    "Requested LP backend failed to load while solving: " + str(error),
                ),
            ),
        )
    optimal = sum(
        trace.status in ("optimal", "optimal_within_horizon") for trace in traces
    )
    unreachable = sum(
        trace.status in ("unreachable", "unreachable_within_horizon")
        for trace in traces
    )
    limited = sum(trace.status == "search_limit" for trace in traces)
    total = sum(
        (Fraction(*trace.cost) for trace in traces if trace.cost is not None),
        Fraction(),
    )
    value = SearchAlignmentSet(
        digest,
        spec.backend,
        version,
        traces,
        len(traces),
        optimal,
        unreachable,
        limited,
        _pair(total) if optimal == len(traces) else None,
        "discounted_rational_move_index"
        if discounted is not None
        else "integer_alignment_cost",
        discounted.max_moves if discounted is not None else None,
    )
    issues = []
    if limited:
        issues.append(
            ComputeIssue(
                "alignment_search_limit",
                "Search budget exhausted; optimality is unknown",
            )
        )
    fallback = sum(
        "zero_bound" in bound.certificate_status
        for trace in traces
        for bound in trace.heuristic_evidence
    )
    if fallback:
        issues.append(
            ComputeIssue(
                "heuristic_conservative_zero_bound",
                f"{fallback} LP bounds lacked a usable certificate or exceeded a heuristic budget; exact search used bound zero",
            )
        )
    return result(
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED, value, issues
    )


def align_state_equation_astar(
    log: CaseInput,
    net: PetriNet,
    spec: StateEquationAStarSpec = StateEquationAStarSpec(),
) -> ComputationResult[SearchAlignmentSet]:
    """Optimal accepting alignment by A* with a certified state-equation bound.

    Inconsistent reconstructed lower bounds are safe because cheaper states are
    reopened. Only exact rational infeasibility is used for pruning. A generic
    solver failure can degrade speed but cannot prove an unreachable trace.
    """
    if not isinstance(spec, StateEquationAStarSpec):
        raise TypeError("spec must be StateEquationAStarSpec")
    return _apply(log, net, spec, None)


def align_discounted_astar(
    log: CaseInput, net: PetriNet, spec: DiscountedAStarSpec
) -> ComputationResult[SearchAlignmentSet]:
    """Minimize exact discounted cost inside the explicit move-count horizon."""
    if not isinstance(spec, DiscountedAStarSpec):
        raise TypeError("spec must be DiscountedAStarSpec")
    return _apply(log, net, spec.search, spec)


RESULT_SCHEMAS = {
    "pix.case_centric.state_equation_astar": (
        "case-state-equation-alignment",
        StateEquationRequest,
        SearchAlignmentSet,
    ),
    "pix.case_centric.discounted_astar": (
        "case-discounted-alignment",
        DiscountedAlignmentRequest,
        SearchAlignmentSet,
    ),
}

__all__ = (
    "StateEquationAStarSpec",
    "DiscountedAStarSpec",
    "StateEquationRequest",
    "DiscountedAlignmentRequest",
    "StateEquationBound",
    "SearchAlignment",
    "SearchAlignmentSet",
    "align_state_equation_astar",
    "align_discounted_astar",
)
