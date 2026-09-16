"""Native integer and split-point extended marking equations.

These are necessary arithmetic constraints for execution, not a firing-sequence
solver. Integer enumeration is explicitly restricted by total firing count.
Its bounded optimum is NEVER silently published as a global lower bound.
Unrestricted rational relaxations supply independently certified lower bounds.

For split occurrences i_1,...,i_k, variables are nonnegative segment vectors
x_0,...,x_k and selected split vectors y_1,...,y_k. Each y has sum one and is
restricted to product transitions consuming that exact trace occurrence. With
incidence C and weighted input matrix Pre, constraints are

  C (sum x + sum y) = final - initial,
  initial + C (sum_{j < h} x_j + sum_{j < h} y_j) >= Pre y_h.

The implementation uses k+1 segments, including zero and one split cases.
Occurrence-based selection and weighted consumption are deliberate refinements
over label-based selection and unit consumption in the pinned PM4Py code.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import lcm
from typing import ClassVar

from pix.case_centric._equation_solver import LPReport, solve_lp
from pix.case_centric._model_algebra import incidence_matrix
from pix.case_centric.model_analysis import MarkingEquationSpec
from pix.compute._common import _result
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

Rational = tuple[int, int]


def _positive(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")


def _nonnegative(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


def _ratio(value, name):
    if (
        not isinstance(value, tuple)
        or len(value) != 2
        or not all(
            isinstance(item, int) and not isinstance(item, bool) for item in value
        )
    ):
        raise TypeError(f"{name} must be an integer numerator/denominator pair")
    if value[0] < 0 or value[1] <= 0:
        raise ValueError(
            f"{name} must have nonnegative numerator and positive denominator"
        )
    number = Fraction(*value)
    return number.numerator, number.denominator


def _pair(number):
    return number.numerator, number.denominator


def _trace(trace):
    if not isinstance(trace, tuple) or not all(
        isinstance(a, str) and a.strip() for a in trace
    ):
        raise TypeError("trace must be a tuple of nonempty activity strings")


@dataclass(frozen=True, slots=True)
class ProductMoveCosts:
    log: Rational = (1, 1)
    model: Rational = (1, 1)
    silent: Rational = (0, 1)
    synchronous: Rational = (0, 1)

    def __post_init__(self):
        for name in ("log", "model", "silent", "synchronous"):
            object.__setattr__(self, name, _ratio(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class SynchronousProductSpec:
    trace: tuple[str, ...]
    costs: ProductMoveCosts = ProductMoveCosts()
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.synchronous_product.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _trace(self.trace)
        if not isinstance(self.costs, ProductMoveCosts):
            raise TypeError("costs must be ProductMoveCosts")


@dataclass(frozen=True, slots=True)
class ProductTransition:
    transition_id: str
    move_kind: str
    trace_index: int | None
    model_transition_id: str | None
    cost: Rational


@dataclass(frozen=True, slots=True)
class SynchronousProduct:
    model: PetriNet
    source_model_digest: str
    trace: tuple[str, ...]
    transitions: tuple[ProductTransition, ...]


def _product(net, spec):
    places = tuple(Place("model:" + p.id) for p in net.places) + tuple(
        Place(f"trace:{index}") for index in range(len(spec.trace) + 1)
    )
    transitions, arcs, mapping = [], [], []
    for transition in net.transitions:
        tid = "model:" + transition.id
        transitions.append(Transition(tid, transition.activity))
        mapping.append(
            ProductTransition(
                tid,
                "silent" if transition.activity is None else "model",
                None,
                transition.id,
                spec.costs.silent if transition.activity is None else spec.costs.model,
            )
        )
        for arc in net.arcs:
            if arc.target == transition.id:
                arcs.append(Arc("model:" + arc.source, tid, arc.weight))
            elif arc.source == transition.id:
                arcs.append(Arc(tid, "model:" + arc.target, arc.weight))
    for index, activity in enumerate(spec.trace):
        tid = f"log:{index}"
        transitions.append(Transition(tid, activity))
        arcs.extend((Arc(f"trace:{index}", tid), Arc(tid, f"trace:{index + 1}")))
        mapping.append(ProductTransition(tid, "log", index, None, spec.costs.log))
        for transition in net.transitions:
            if transition.activity != activity:
                continue
            tid = f"sync:{index}:{transition.id}"
            transitions.append(Transition(tid, activity))
            arcs.extend((Arc(f"trace:{index}", tid), Arc(tid, f"trace:{index + 1}")))
            for arc in net.arcs:
                if arc.target == transition.id:
                    arcs.append(Arc("model:" + arc.source, tid, arc.weight))
                elif arc.source == transition.id:
                    arcs.append(Arc(tid, "model:" + arc.target, arc.weight))
            mapping.append(
                ProductTransition(
                    tid, "synchronous", index, transition.id, spec.costs.synchronous
                )
            )
    initial = Marking(
        tuple(("model:" + p, n) for p, n in net.initial_marking.tokens)
        + (("trace:0", 1),)
    )
    final = Marking(
        tuple(("model:" + p, n) for p, n in net.final_marking.tokens)
        + ((f"trace:{len(spec.trace)}", 1),)
    )
    product = PetriNet(places, tuple(transitions), tuple(arcs), initial, final)
    return SynchronousProduct(
        product,
        model_digest(net),
        spec.trace,
        tuple(sorted(mapping, key=lambda row: row.transition_id)),
    )


def synchronous_product(
    net: PetriNet, spec: SynchronousProductSpec
) -> ComputationResult[SynchronousProduct]:
    """Materialize cost-aware log/model/synchronous moves without executing them."""
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, SynchronousProductSpec):
        raise TypeError("spec must be SynchronousProductSpec")
    return _result(
        "pix.case_centric.synchronous_product",
        None,
        spec,
        ComputeStatus.COMPUTED,
        _product(net, spec),
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class IntegerMarkingEquationSpec:
    initial: Marking | None = None
    target: Marking | None = None
    transition_costs: tuple[tuple[str, Rational], ...] = ()
    max_total_firings: int = 20
    max_search_nodes: int = 100000
    max_lp_iterations: int = 10000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.integer_marking_equation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        validated = MarkingEquationSpec(
            self.initial, self.target, self.transition_costs
        )
        object.__setattr__(self, "transition_costs", validated.transition_costs)
        _nonnegative(self.max_total_firings, "max_total_firings")
        _positive(self.max_search_nodes, "max_search_nodes")
        _positive(self.max_lp_iterations, "max_lp_iterations")


@dataclass(frozen=True, slots=True)
class ExtendedMarkingEquationSpec:
    """Rational mode has no firing horizon; integer mode uses both search caps.

    The LP pivot cap applies in either mode. Split indices are exact zero-based
    occurrences, including index zero when explicitly selected. No split is
    selected or silently trimmed on the caller's behalf.
    """

    trace: tuple[str, ...]
    split_indices: tuple[int, ...] = ()
    mode: str = "rational"
    costs: ProductMoveCosts = ProductMoveCosts()
    max_total_firings: int = 20
    max_search_nodes: int = 100000
    max_lp_iterations: int = 10000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.extended_marking_equation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _trace(self.trace)
        if not isinstance(self.split_indices, tuple) or not all(
            isinstance(index, int) and not isinstance(index, bool)
            for index in self.split_indices
        ):
            raise TypeError("split_indices must be a tuple of integers")
        if tuple(sorted(set(self.split_indices))) != self.split_indices:
            raise ValueError("split_indices must be strictly increasing and unique")
        if any(index < 0 or index >= len(self.trace) for index in self.split_indices):
            raise ValueError("split index must identify an existing trace occurrence")
        if self.mode not in ("rational", "integer"):
            raise ValueError("mode must be rational or integer")
        if not isinstance(self.costs, ProductMoveCosts):
            raise TypeError("costs must be ProductMoveCosts")
        _nonnegative(self.max_total_firings, "max_total_firings")
        _positive(self.max_search_nodes, "max_search_nodes")
        _positive(self.max_lp_iterations, "max_lp_iterations")


@dataclass(frozen=True, slots=True)
class EquationVariable:
    kind: str
    segment: int
    transition_id: str


@dataclass(frozen=True, slots=True)
class EquationProgram:
    """Reviewable integer coefficient system; all variables are nonnegative."""

    variables: tuple[EquationVariable, ...]
    costs: tuple[Rational, ...]
    equalities: tuple[tuple[int, ...], ...]
    equality_rhs: tuple[int, ...]
    inequalities: tuple[tuple[int, ...], ...]
    inequality_rhs: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EquationSolution:
    status: str
    mode: str
    objective: Rational | None
    objective_scope: str
    global_lower_bound: Rational | None
    solution: tuple[Rational, ...] | None
    integer_search_complete: bool | None
    searched_nodes: int
    max_total_firings: int | None
    rational_relaxation: LPReport
    reachability_proven: bool = False


@dataclass(frozen=True, slots=True)
class IntegerMarkingEquation:
    program: EquationProgram
    result: EquationSolution
    transition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExtendedMarkingEquation:
    product: SynchronousProduct
    split_indices: tuple[int, ...]
    segment_count: int
    program: EquationProgram
    result: EquationSolution
    transition_firing_counts: tuple[tuple[str, Rational], ...] | None
    split_transition_weights: (
        tuple[tuple[int, tuple[tuple[str, Rational], ...]], ...] | None
    )


def _children(index, vector, budget, cost, sums, costs, rows):
    """Lazy enumeration keeps a huge firing horizon from allocating a huge stack."""
    for value in range(budget + 1):
        yield (
            index + 1,
            vector + (value,),
            budget - value,
            cost + value * costs[index],
            tuple(total + value * row[index] for total, row in zip(sums, rows)),
        )


def _integer_search(program, horizon, cap, lp):
    """Exact finite branch-and-bound over nonnegative counts summing <= horizon."""
    n = len(program.variables)
    costs = tuple(Fraction(*cost) for cost in program.costs)
    lower = Fraction(*lp.objective) if lp.status == "optimal" else None
    if lower is not None:
        denominator = lcm(*(cost.denominator for cost in costs))
        # Every integral vector has objective on this rational cost lattice.
        scaled = lower * denominator
        lower = Fraction(-(-scaled.numerator // scaled.denominator), denominator)
    lower_pair = None if lower is None else _pair(lower)
    if lp.status == "infeasible":
        return EquationSolution(
            "infeasible", "integer", None, "none", None, None, True, 0, horizon, lp
        )
    rows = program.equalities + program.inequalities
    suffix_low, suffix_high = [], []
    for row in rows:
        lows, highs = [0] * (n + 1), [0] * (n + 1)
        for index in range(n - 1, -1, -1):
            lows[index] = min(lows[index + 1], row[index])
            highs[index] = max(highs[index + 1], row[index])
        suffix_low.append(lows)
        suffix_high.append(highs)
    stack = [iter(((0, (), horizon, Fraction(0), (0,) * len(rows)),))]
    checked = 0
    best = None
    best_vector = None
    globally_optimal = False
    while stack and checked < cap:
        try:
            index, vector, budget, cost, sums = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        checked += 1
        if best is not None and cost >= best:
            continue
        possible = True
        for r, target in enumerate(program.equality_rhs):
            if (
                not sums[r] + budget * suffix_low[r][index]
                <= target
                <= sums[r] + budget * suffix_high[r][index]
            ):
                possible = False
                break
        if not possible:
            continue
        offset = len(program.equalities)
        for i, target in enumerate(program.inequality_rhs):
            r = offset + i
            if sums[r] + budget * suffix_low[r][index] > target:
                possible = False
                break
        if not possible:
            continue
        if index == n:
            best, best_vector = cost, vector
            if lower is not None and best == lower:
                globally_optimal = True
                break
            continue
        stack.append(_children(index, vector, budget, cost, sums, costs, rows))
    # Exhausted iterators do not consume nodes. An exactly exhausted cap may
    # still prove a complete search if there is no remaining candidate node.
    while stack and not globally_optimal:
        try:
            next(stack[-1])
            break
        except StopIteration:
            stack.pop()
    complete = not stack
    if globally_optimal:
        status, scope = "optimal", "global_integer"
    elif complete and best is not None:
        status, scope = "optimal_within_horizon", "integer_horizon"
    elif complete:
        status, scope = "infeasible_within_horizon", "none"
    else:
        status, scope = "unknown", "none"
    # A merely incumbent cost is not an optimum. The rational witness remains
    # available for inspection, and its objective can be recomputed from costs.
    objective = (
        _pair(best)
        if best is not None and status in ("optimal", "optimal_within_horizon")
        else None
    )
    return EquationSolution(
        status,
        "integer",
        objective,
        scope,
        lower_pair,
        None if best_vector is None else tuple((count, 1) for count in best_vector),
        complete,
        checked,
        horizon,
        lp,
    )


def _solve(program, mode, horizon, node_cap, lp_cap):
    lp = solve_lp(
        program.costs,
        equalities=program.equalities,
        equality_rhs=program.equality_rhs,
        inequalities=program.inequalities,
        inequality_rhs=program.inequality_rhs,
        max_iterations=lp_cap,
    )
    if mode == "integer":
        return _integer_search(program, horizon, node_cap, lp)
    return EquationSolution(
        lp.status,
        "rational",
        lp.objective,
        "global_relaxation" if lp.status == "optimal" else "none",
        lp.objective,
        lp.solution,
        None,
        0,
        None,
        lp,
    )


def _issues(value):
    issues = []
    if value.status == "unknown":
        issues.append(
            ComputeIssue(
                "equation_search_limit",
                "No optimum was certified before the search limit.",
            )
        )
    if value.status in ("optimal_within_horizon", "infeasible_within_horizon"):
        issues.append(
            ComputeIssue(
                "integer_horizon",
                "Integer conclusion applies only to the declared total-firing horizon.",
            )
        )
    if value.rational_relaxation.status == "unknown":
        issues.append(
            ComputeIssue(
                "rational_relaxation_limit",
                "A global rational lower bound was not certified.",
            )
        )
    return tuple(issues)


def integer_marking_equation(
    net: PetriNet, spec: IntegerMarkingEquationSpec = IntegerMarkingEquationSpec()
) -> ComputationResult[IntegerMarkingEquation]:
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, IntegerMarkingEquationSpec):
        raise TypeError("spec must be IntegerMarkingEquationSpec")
    places, transitions, matrix = incidence_matrix(net)
    initial = net.initial_marking if spec.initial is None else spec.initial
    target = net.final_marking if spec.target is None else spec.target
    net.validate_marking(initial)
    net.validate_marking(target)
    costs = dict(spec.transition_costs)
    if set(costs) - set(transitions):
        raise ValueError("costs reference an unknown transition")
    before, after = dict(initial.tokens), dict(target.tokens)
    program = EquationProgram(
        tuple(EquationVariable("count", 0, tid) for tid in transitions),
        tuple(costs.get(tid, (1, 1)) for tid in transitions),
        matrix,
        tuple(after.get(p, 0) - before.get(p, 0) for p in places),
        (),
        (),
    )
    solved = _solve(
        program,
        "integer",
        spec.max_total_firings,
        spec.max_search_nodes,
        spec.max_lp_iterations,
    )
    value = IntegerMarkingEquation(program, solved, transitions)
    issues = _issues(solved)
    return _result(
        "pix.case_centric.integer_marking_equation",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


def _extended_program(product, spec):
    net = product.model
    places, transitions, matrix = incidence_matrix(net)
    columns = {tid: index for index, tid in enumerate(transitions)}
    mapping = {row.transition_id: row for row in product.transitions}
    splits = len(spec.split_indices)
    variables = tuple(
        EquationVariable("segment", segment, tid)
        for segment in range(splits + 1)
        for tid in transitions
    )
    # Materialize only allowed exact-occurrence y entries; all other y are 0.
    variables += tuple(
        EquationVariable("split", split, tid)
        for split, occurrence in enumerate(spec.split_indices)
        for tid in transitions
        if mapping[tid].trace_index == occurrence
    )
    n = len(variables)
    eq = [tuple(row[columns[var.transition_id]] for var in variables) for row in matrix]
    initial, final = dict(net.initial_marking.tokens), dict(net.final_marking.tokens)
    rhs = [final.get(p, 0) - initial.get(p, 0) for p in places]
    for split in range(splits):
        eq.append(
            tuple(
                int(var.kind == "split" and var.segment == split) for var in variables
            )
        )
        rhs.append(1)
    # Before split h: x_0+...+x_h and y_0+...+y_(h-1).
    pre = {(a.source, a.target): a.weight for a in net.arcs if a.source in set(places)}
    le, bound = [], []
    for split in range(splits):
        for p_index, place in enumerate(places):
            row = []
            for var in variables:
                coefficient = 0
                if (var.kind == "segment" and var.segment <= split) or (
                    var.kind == "split" and var.segment < split
                ):
                    coefficient -= matrix[p_index][columns[var.transition_id]]
                if var.kind == "split" and var.segment == split:
                    coefficient += pre.get((place, var.transition_id), 0)
                row.append(coefficient)
            if any(row):
                le.append(tuple(row))
                bound.append(initial.get(place, 0))
    assert all(len(row) == n for row in eq + le)
    return EquationProgram(
        variables,
        tuple(mapping[var.transition_id].cost for var in variables),
        tuple(eq),
        tuple(rhs),
        tuple(le),
        tuple(bound),
    )


def extended_marking_equation(
    net: PetriNet, spec: ExtendedMarkingEquationSpec
) -> ComputationResult[ExtendedMarkingEquation]:
    """Solve the actual split-point relaxation, with exact occurrence identity.

    Each genuine complete product firing sequence yields a feasible segmented
    vector at every requested split, so the unrestricted rational optimum is
    an admissible lower bound. Segment vectors need not be executable in order;
    satisfying these necessary inequalities never certifies an alignment.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, ExtendedMarkingEquationSpec):
        raise TypeError("spec must be ExtendedMarkingEquationSpec")
    product = _product(net, SynchronousProductSpec(spec.trace, spec.costs))
    program = _extended_program(product, spec)
    solved = _solve(
        program,
        spec.mode,
        spec.max_total_firings,
        spec.max_search_nodes,
        spec.max_lp_iterations,
    )
    counts, split_weights = None, None
    if solved.solution is not None:
        counts_by_transition = {t.id: Fraction(0) for t in product.model.transitions}
        for var, count in zip(program.variables, solved.solution):
            counts_by_transition[var.transition_id] += Fraction(*count)
        counts = tuple(
            (tid, _pair(count)) for tid, count in sorted(counts_by_transition.items())
        )
        split_weights = tuple(
            (
                occurrence,
                tuple(
                    (var.transition_id, count)
                    for var, count in zip(program.variables, solved.solution)
                    if var.kind == "split" and var.segment == split
                ),
            )
            for split, occurrence in enumerate(spec.split_indices)
        )
    value = ExtendedMarkingEquation(
        product,
        spec.split_indices,
        len(spec.split_indices) + 1,
        program,
        solved,
        counts,
        split_weights,
    )
    issues = _issues(solved)
    return _result(
        "pix.case_centric.extended_marking_equation",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.synchronous_product": (
        "case-synchronous-product",
        SynchronousProductSpec,
        SynchronousProduct,
    ),
    "pix.case_centric.integer_marking_equation": (
        "case-integer-marking-equation",
        IntegerMarkingEquationSpec,
        IntegerMarkingEquation,
    ),
    "pix.case_centric.extended_marking_equation": (
        "case-extended-marking-equation",
        ExtendedMarkingEquationSpec,
        ExtendedMarkingEquation,
    ),
}

__all__ = (
    "ProductMoveCosts",
    "SynchronousProductSpec",
    "ProductTransition",
    "SynchronousProduct",
    "synchronous_product",
    "IntegerMarkingEquationSpec",
    "ExtendedMarkingEquationSpec",
    "EquationVariable",
    "EquationProgram",
    "EquationSolution",
    "IntegerMarkingEquation",
    "ExtendedMarkingEquation",
    "integer_marking_equation",
    "extended_marking_equation",
)
