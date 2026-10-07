"""Sequential executable-prefix/integer-tail alignment approximation.

At each iteration, enumerate every product state at each depth up to the
declared horizon, retaining its cheapest executable prefix. Rank prefixes by
prefix cost plus a *certified global integer marking-equation optimum*. Commit
the entire selected prefix and repeat. An integer tail is a necessary arithmetic
condition, never an executable continuation. In particular, this procedure is
not ordinary full-trace Dijkstra and does not certify global alignment optimality.

This native profile uses scalar nonnegative integer AlignmentSpec costs. It does
not accept PM4Py's per-event/per-transition cost dictionaries. Finite integer
search optima are not global lower bounds: an uncertified tail stops the helper
with explicit diagnostics. There is no implicit rational-tail substitution.
The caller owns any full-trace fallback or independent exact verification.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from typing import ClassVar, Literal

from pix.case_centric.marking_equation import (
    EquationSolution,
    IntegerMarkingEquationSpec,
    ProductMoveCosts,
    SynchronousProductSpec,
    integer_marking_equation,
    synchronous_product,
)
from pix.compute.model_semantics import enabled_transitions, fire
from pix.contracts.analysis import ObjectTrace, TraceEvent
from pix.contracts.conformance import AlignmentMove, AlignmentSpec
from pix.contracts.models import Marking, PetriNet


@dataclass(frozen=True, slots=True)
class FixedHorizonSpec:
    """Bounds are per prefix attempt, except global iterations and tail solves.

    max_tail_firings bounds integer count enumeration; max_tail_nodes and
    max_tail_lp_iterations bound each individual tail solve. AlignmentSpec's
    max_states belongs to the caller's optional exact search, not this helper.
    fallback_to_exact and verify_exact are orchestration settings read by the
    public wrapper; run_fixed_horizon itself never invokes an exact fallback.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    horizon: int = 4
    min_progress: int = 1
    max_horizon: int = 20
    max_prefix_states: int = 1000
    max_iterations: int = 100
    max_tail_solves: int = 1000
    max_tail_firings: int = 20
    max_tail_nodes: int = 10000
    max_tail_lp_iterations: int = 1000
    fallback_to_exact: bool = True
    verify_exact: bool = False
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.fixed_horizon_alignment.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.alignment, AlignmentSpec):
            raise TypeError("alignment must be AlignmentSpec")
        for name in (
            "horizon",
            "min_progress",
            "max_horizon",
            "max_prefix_states",
            "max_iterations",
            "max_tail_solves",
            "max_tail_firings",
            "max_tail_nodes",
            "max_tail_lp_iterations",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            minimum = 0 if name in ("min_progress", "max_tail_firings") else 1
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")
        if self.min_progress > self.horizon:
            raise ValueError("min_progress must not exceed horizon")
        if self.max_horizon < self.horizon:
            raise ValueError("max_horizon must not be smaller than horizon")
        for name in ("fallback_to_exact", "verify_exact"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be a bool")


@dataclass(frozen=True, slots=True)
class FixedHorizonStage:
    iteration: int
    horizon: int
    min_progress: int
    prefix_states: int
    prefix_complete: bool
    tail_solves: int
    certified_tails: int
    infeasible_tails: int
    uncertified_tails: int
    candidate_count: int
    selected_product_steps: tuple[str, ...]
    selected_progress: int
    prefix_cost: int | None
    tail_cost: int | None
    objective: int | None
    committed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class FixedHorizonOutcome:
    moves: tuple[AlignmentMove, ...]
    status: Literal["complete", "search_limit", "unreachable", "stalled"]
    stages: tuple[FixedHorizonStage, ...]
    total_states: int
    tail_solves: int
    fallback_reason: str | None


@dataclass(frozen=True, slots=True)
class _Candidate:
    marking: Marking
    path: tuple[str, ...]
    progress: int
    prefix_cost: int
    tail_cost: int

    @property
    def rank(self):
        return (
            self.prefix_cost + self.tail_cost,
            -self.progress,
            len(self.path),
        )


@dataclass(frozen=True, slots=True)
class _Prefix:
    candidate: _Candidate | None
    states: int
    complete: bool
    solves: int
    certified: int
    infeasible: int
    uncertified: int
    candidates: int
    graph_closed: bool
    saw_final: bool
    limit_reason: str | None


class _TailSolver:
    def __init__(self, product, spec):
        self.net = product.model
        self.costs = tuple(
            (step.transition_id, step.cost) for step in product.transitions
        )
        self.spec = spec
        self.cache: dict[Marking, EquationSolution] = {}
        self.solves = 0

    def solve(self, marking):
        if marking in self.cache:
            return self.cache[marking]
        if self.solves >= self.spec.max_tail_solves:
            return None
        result = integer_marking_equation(
            self.net,
            IntegerMarkingEquationSpec(
                initial=marking,
                transition_costs=self.costs,
                max_total_firings=self.spec.max_tail_firings,
                max_search_nodes=self.spec.max_tail_nodes,
                max_lp_iterations=self.spec.max_tail_lp_iterations,
            ),
        )
        self.solves += 1
        self.cache[marking] = result.value.result
        return self.cache[marking]


def _prefix(product, initial, horizon, minimum, spec, tails):
    """Finite depth-indexed product search, with exact original firing semantics.

    Equal-cost paths to one (marking, depth) keep the first deterministic
    discovery. Candidate ties after objective, progress and length likewise keep
    the first candidate; this is not global lexical ordering of complete paths.
    """
    net = product.model
    metadata = {step.transition_id: step for step in product.transitions}
    costs = {step.transition_id: step.cost[0] for step in product.transitions}
    serial = count()
    queue = [(0, 0, 0, next(serial), initial, ())]
    best = {(initial, 0): 0}
    chosen = None
    states = certified = infeasible = uncertified = candidates = 0
    before_solves = tails.solves
    reachable, successors = set(), set()
    saw_final = False
    reason = None
    while queue:
        cost, negative_progress, depth, _, marking, path = heappop(queue)
        if cost != best.get((marking, depth)):
            continue
        if states >= spec.max_prefix_states:
            reason = "maximum_prefix_states"
            break
        states += 1
        reachable.add(marking)
        progress = -negative_progress
        final = marking == net.final_marking
        saw_final |= final
        # Enumerating outgoing markings at the boundary lets us distinguish a
        # closed finite reachable graph from mere exhaustion of the horizon.
        edges = (
            ()
            if final
            else tuple(
                (tid, fire(net, marking, tid))
                for tid in enabled_transitions(net, marking)
            )
        )
        successors.update(after for _, after in edges)
        if final or (path and progress >= minimum):
            # Nonnegative tail costs make a strictly costlier prefix irrelevant.
            # Equal objectives still require evaluation for deterministic ties.
            if chosen is None or cost <= chosen.rank[0]:
                tail_cost = None
                if final:
                    tail_cost = 0
                else:
                    tail = tails.solve(marking)
                    if tail is None:
                        reason = "maximum_tail_solves"
                        break
                    if tail.status == "infeasible":
                        infeasible += 1
                    elif (
                        tail.status == "optimal"
                        and tail.objective_scope == "global_integer"
                        and tail.objective is not None
                        and tail.objective[1] == 1
                    ):
                        certified += 1
                        tail_cost = tail.objective[0]
                    else:
                        uncertified += 1
                        reason = "uncertified_integer_tail"
                        break
                if tail_cost is not None:
                    candidates += 1
                    candidate = _Candidate(marking, path, progress, cost, tail_cost)
                    if chosen is None or candidate.rank < chosen.rank:
                        chosen = candidate
        if depth >= horizon or final:
            continue
        for tid, after in sorted(edges, key=lambda edge: (costs[edge[0]], edge[0])):
            next_cost = cost + costs[tid]
            key = after, depth + 1
            if key in best and next_cost >= best[key]:
                continue
            best[key] = next_cost
            next_progress = progress + int(metadata[tid].trace_index is not None)
            heappush(
                queue,
                (
                    next_cost,
                    -next_progress,
                    depth + 1,
                    next(serial),
                    after,
                    path + (tid,),
                ),
            )
    complete = reason is None
    return _Prefix(
        chosen,
        states,
        complete,
        tails.solves - before_solves,
        certified,
        infeasible,
        uncertified,
        candidates,
        complete and successors <= reachable,
        saw_final,
        reason,
    )


def _stage(iteration, horizon, minimum, prefix, committed, reason):
    chosen = prefix.candidate
    return FixedHorizonStage(
        iteration,
        horizon,
        minimum,
        prefix.states,
        prefix.complete,
        prefix.solves,
        prefix.certified,
        prefix.infeasible,
        prefix.uncertified,
        prefix.candidates,
        () if chosen is None else chosen.path,
        0 if chosen is None else chosen.progress,
        None if chosen is None else chosen.prefix_cost,
        None if chosen is None else chosen.tail_cost,
        None if chosen is None else chosen.rank[0],
        committed,
        reason,
    )


def _moves(trace, net, product, path):
    metadata = {step.transition_id: step for step in product.transitions}
    activities = {transition.id: transition.activity for transition in net.transitions}
    marking = net.initial_marking
    moves = []
    consumed = 0
    for tid in path:
        step = metadata[tid]
        event = None
        if step.trace_index is not None:
            if step.trace_index != consumed:
                raise RuntimeError("product path violated exact trace occurrence order")
            event = trace.events[consumed]
            consumed += 1
        transition = step.model_transition_id
        after = marking if transition is None else fire(net, marking, transition)
        activity = event.activity if event is not None else activities[transition]
        moves.append(
            AlignmentMove(
                step.move_kind,
                None if event is None else event.event_id,
                transition,
                activity,
                step.cost[0],
                marking.tokens,
                after.tokens,
            )
        )
        marking = after
    return tuple(moves)


def run_fixed_horizon(
    trace: ObjectTrace, net: PetriNet, spec: FixedHorizonSpec = FixedHorizonSpec()
) -> FixedHorizonOutcome:
    """Return a checked executable prefix, never a claim of global optimality.

    Complete means exact final product marking, including every trace occurrence
    and absence of residual model tokens. Unreachable is reserved for a closed
    reachable product graph *before any commitment*. A failed committed branch
    is stalled; the uncommitted alternatives may still admit a valid alignment.
    Horizons grow on absent/stationary/repeated prefix or a positive-tail estimate
    that at least doubles. Unlike the pinned implementation, zero previous tail
    is not a trigger for repeated horizon growth. All growth consumes iterations.
    """
    if not isinstance(trace, ObjectTrace):
        raise TypeError("trace must be ObjectTrace")
    if not isinstance(trace.events, tuple) or not all(
        isinstance(event, TraceEvent) for event in trace.events
    ):
        raise TypeError("trace.events must be a tuple of TraceEvent")
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, FixedHorizonSpec):
        raise TypeError("spec must be FixedHorizonSpec")
    cost = spec.alignment
    product = synchronous_product(
        net,
        SynchronousProductSpec(
            tuple(event.activity for event in trace.events),
            ProductMoveCosts(
                (cost.log_move_cost, 1),
                (cost.model_move_cost, 1),
                (cost.silent_move_cost, 1),
                (cost.synchronous_move_cost, 1),
            ),
        ),
    ).value
    current = product.model.initial_marking
    final = product.model.final_marking
    tails = _TailSolver(product, spec)
    path, stages = (), []
    total_states = 0
    horizon = spec.horizon
    remaining = len(trace.events)
    minimum = min(spec.min_progress, remaining)
    previous_tail = None
    committed_states = {current}

    def outcome(status, reason):
        return FixedHorizonOutcome(
            _moves(trace, net, product, path),
            status,
            tuple(stages),
            total_states,
            tails.solves,
            reason,
        )

    if current == final:
        return outcome("complete", None)
    for iteration in range(1, spec.max_iterations + 1):
        prefix = _prefix(product, current, horizon, minimum, spec, tails)
        total_states += prefix.states
        chosen = prefix.candidate
        if not prefix.complete:
            stages.append(
                _stage(iteration, horizon, minimum, prefix, False, prefix.limit_reason)
            )
            return outcome("search_limit", prefix.limit_reason)
        if prefix.graph_closed and not prefix.saw_final:
            reason = "closed_product_graph" if not path else "committed_dead_end"
            stages.append(_stage(iteration, horizon, minimum, prefix, False, reason))
            return outcome("unreachable" if not path else "stalled", reason)
        repeated = chosen is not None and chosen.marking in committed_states
        estimate_jump = (
            chosen is not None
            and chosen.marking != final
            and previous_tail is not None
            and previous_tail > 0
            and chosen.rank[0] >= 2 * previous_tail
        )
        if chosen is None or repeated or estimate_jump:
            reason = (
                "no_prefix_solution"
                if chosen is None
                else "repeated_product_state"
                if repeated
                else "tail_estimate_increase"
            )
            if horizon < spec.max_horizon:
                stages.append(
                    _stage(
                        iteration,
                        horizon,
                        minimum,
                        prefix,
                        False,
                        "grow_horizon:" + reason,
                    )
                )
                horizon += 1
                minimum = min(minimum + 1, remaining, horizon)
                continue
            if chosen is None or repeated:
                stages.append(
                    _stage(iteration, horizon, minimum, prefix, False, reason)
                )
                return outcome("stalled", reason)
        stages.append(
            _stage(iteration, horizon, minimum, prefix, True, "commit_prefix")
        )
        path += chosen.path
        current = chosen.marking
        remaining -= chosen.progress
        committed_states.add(current)
        previous_tail = chosen.tail_cost
        minimum = min(spec.min_progress, remaining)
        if current == final:
            return outcome("complete", None)
    return outcome("search_limit", "maximum_iterations")


__all__ = (
    "FixedHorizonSpec",
    "FixedHorizonStage",
    "FixedHorizonOutcome",
    "run_fixed_horizon",
)
