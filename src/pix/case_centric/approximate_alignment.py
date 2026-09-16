"""Executable approximate alignments with named reduction/window strategies.

Tandem reduction, a top-k marking beam over sliding windows, and sequential
fixed-horizon integer-tail search are distinct algorithms. A validated complete
witness supplies an upper bound, never an implicit optimality or fitness claim.
An optional full-trace exact fallback or verification is recorded explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from heapq import heappop, heappush
from itertools import count
from typing import ClassVar, Literal

from pix.case_centric._fixed_horizon_alignment import (
    FixedHorizonOutcome,
    FixedHorizonSpec,
    run_fixed_horizon,
)
from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.compute.conformance import _align
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import AlignmentMove, AlignmentSpec
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _positive(value: object, field: str, minimum: int = 1) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")


def _common_spec(spec) -> None:
    if not isinstance(spec.alignment, AlignmentSpec):
        raise TypeError("alignment must be AlignmentSpec")
    for name in ("fallback_to_exact", "verify_exact"):
        if type(getattr(spec, name)) is not bool:
            raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class TandemRepeatSpec:
    """Greedy primitive repeats retain the first and last of >=3 copies.

    max_period bounds compression work, not the accepted model language.
    Non-loop retained copies expand removed events as log moves, preserving
    every original event and the executable accepting model projection.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    max_period: int = 100
    fallback_to_exact: bool = True
    verify_exact: bool = False
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _common_spec(self)
        _positive(self.max_period, "max_period")


@dataclass(frozen=True, slots=True)
class SlidingWindowSpec:
    """Nonoverlapping windows retain a beam of distinct endpoint markings.

    The ranking cost includes a structural future-activity lower bound. This
    overapproximation ignores token multiplicities and joint-input requirements;
    it does not prove future executability. The last window must reach final.
    alignment.max_states bounds each local product search; max_total_states
    bounds their sum for each original case. Beam pruning is intentional.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    window_size: int = 20
    max_candidates: int = 5
    max_post_model_moves: int = 1
    max_total_states: int = 100000
    fallback_to_exact: bool = True
    verify_exact: bool = False
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _common_spec(self)
        _positive(self.window_size, "window_size")
        _positive(self.max_candidates, "max_candidates")
        _positive(self.max_post_model_moves, "max_post_model_moves", 0)
        _positive(self.max_total_states, "max_total_states")


@dataclass(frozen=True, slots=True)
class TandemRepeatRequest:
    model_digest: str
    parameters: TandemRepeatSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class SlidingWindowRequest:
    model_digest: str
    parameters: SlidingWindowSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class FixedHorizonRequest:
    model_digest: str
    parameters: FixedHorizonSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TandemRepeatReduction:
    original_start: int
    reduced_start: int
    period: tuple[str, ...]
    repetitions: int
    expansion: Literal["model_loop", "log_moves"]


@dataclass(frozen=True, slots=True)
class WindowCandidate:
    marking: Marking
    accumulated_cost: int
    future_lower_bound: int


@dataclass(frozen=True, slots=True)
class SlidingWindowStage:
    start: int
    end: int
    final_window: bool
    input_candidates: int
    endpoint_candidates: int
    retained: tuple[WindowCandidate, ...]
    settled_states: int
    local_search_limit: bool


@dataclass(frozen=True, slots=True)
class ApproximateTraceAlignment:
    case_id: str
    strategy: str
    status: Literal[
        "optimal", "approximate", "search_limit", "unreachable", "unavailable"
    ]
    moves: tuple[AlignmentMove, ...]
    cost_upper_bound: int | None
    certified_optimal_cost: int | None
    certified_lower_bound: int | None
    certificate: Literal[
        "none",
        "zero_cost",
        "whole_trace_search",
        "exact_verification",
        "exact_fallback",
    ]
    exact_verification_status: str | None
    fallback_used: bool
    fallback_reason: str | None
    strategy_settled_states: int
    verification_settled_states: int
    fallback_settled_states: int
    original_trace_length: int
    reduced_trace_length: int | None
    repeat_reductions: tuple[TandemRepeatReduction, ...]
    windows: tuple[SlidingWindowStage, ...]
    fixed_horizon: FixedHorizonOutcome | None


@dataclass(frozen=True, slots=True)
class ApproximateAlignmentSet:
    model_digest: str
    strategy: str
    traces: tuple[ApproximateTraceAlignment, ...]
    requested_cases: int
    complete_witness_cases: int
    certified_optimal_cases: int
    approximate_cases: int
    incomplete_cases: int
    completed_cost_upper_bound_sum: int
    whole_population_cost_upper_bound: int | None
    cost_profile: str = (
        "nonnegative_integer_alignment_spec_no_implicit_normalized_fitness"
    )


@dataclass(frozen=True, slots=True)
class _StrategyResult:
    status: str
    moves: tuple[AlignmentMove, ...]
    states: int = 0
    reason: str | None = None
    exact_whole_trace: bool = False
    reduced_length: int | None = None
    repeats: tuple[TandemRepeatReduction, ...] = ()
    windows: tuple[SlidingWindowStage, ...] = ()
    fixed: FixedHorizonOutcome | None = None


def _primitive(word: tuple[str, ...]) -> bool:
    return not any(
        len(word) % width == 0 and word == word[:width] * (len(word) // width)
        for width in range(1, len(word))
    )


def _reduce(trace: ObjectTrace, max_period: int):
    labels = tuple(event.activity for event in trace.events)
    kept, repeats, position = [], [], 0
    while position < len(labels):
        chosen = None
        for width in range(1, min(max_period, (len(labels) - position) // 3) + 1):
            period = labels[position : position + width]
            if not _primitive(period):
                continue
            copies = 1
            while (
                labels[position + copies * width : position + (copies + 1) * width]
                == period
            ):
                copies += 1
            if copies >= 3:
                rank = ((copies - 2) * width, copies * width, -width)
                if chosen is None or rank > chosen[0]:
                    chosen = rank, width, copies, period
        if chosen is None:
            kept.append(position)
            position += 1
            continue
        _, width, copies, period = chosen
        repeats.append((position, len(kept), period, copies))
        kept.extend(range(position, position + width))
        kept.extend(range(position + (copies - 1) * width, position + copies * width))
        position += width * copies
    return replace(trace, events=tuple(trace.events[index] for index in kept)), tuple(
        repeats
    )


def _tandem(
    trace: ObjectTrace, net: PetriNet, spec: TandemRepeatSpec
) -> _StrategyResult:
    reduced, repeats = _reduce(trace, spec.max_period)
    aligned = _align(reduced, net, spec.alignment)
    if aligned.status != "optimal":
        return _StrategyResult(
            aligned.status,
            (),
            aligned.settled_states,
            "reduced_trace_" + aligned.status,
            reduced_length=len(reduced.events),
        )
    moves = list(aligned.moves)
    evidence = []
    for original_start, reduced_start, period, repetitions in reversed(repeats):
        first_id = trace.events[original_start].event_id
        last_id = trace.events[original_start + len(period) - 1].event_id
        begin = next(
            index for index, move in enumerate(moves) if move.event_id == first_id
        )
        end = next(
            index + 1 for index, move in enumerate(moves) if move.event_id == last_id
        )
        fragment = moves[begin:end]
        loop = fragment[0].before_marking == fragment[-1].after_marking and any(
            move.transition_id is not None for move in fragment
        )
        insertion = []
        offset_by_id = {
            trace.events[original_start + offset].event_id: offset
            for offset in range(len(period))
        }
        for copy in range(1, repetitions - 1):
            if loop:
                for move in fragment:
                    event_id = (
                        trace.events[
                            original_start
                            + copy * len(period)
                            + offset_by_id[move.event_id]
                        ].event_id
                        if move.event_id is not None
                        else None
                    )
                    insertion.append(replace(move, event_id=event_id))
            else:
                marking = fragment[-1].after_marking
                for offset in range(len(period)):
                    event = trace.events[original_start + copy * len(period) + offset]
                    insertion.append(
                        AlignmentMove(
                            "log",
                            event.event_id,
                            None,
                            event.activity,
                            spec.alignment.log_move_cost,
                            marking,
                            marking,
                        )
                    )
        moves[end:end] = insertion
        evidence.append(
            TandemRepeatReduction(
                original_start,
                reduced_start,
                period,
                repetitions,
                "model_loop" if loop else "log_moves",
            )
        )
    return _StrategyResult(
        "complete",
        tuple(moves),
        aligned.settled_states,
        exact_whole_trace=not repeats,
        reduced_length=len(reduced.events),
        repeats=tuple(reversed(evidence)),
    )


def _reachable_labels(net: PetriNet, marking: Marking) -> frozenset[str]:
    """Safe structural overapproximation, including source-transition outputs."""
    present = {place for place, _ in marking.tokens}
    inputs = {transition.id: set() for transition in net.transitions}
    outputs = {transition.id: set() for transition in net.transitions}
    for arc in net.arcs:
        if arc.target in inputs:
            inputs[arc.target].add(arc.source)
        else:
            outputs[arc.source].add(arc.target)
    discovered = set()
    changed = True
    while changed:
        changed = False
        for transition in net.transitions:
            if transition.id not in discovered and (
                not inputs[transition.id] or inputs[transition.id] & present
            ):
                discovered.add(transition.id)
                present.update(outputs[transition.id])
                changed = True
    return frozenset(
        transition.activity
        for transition in net.transitions
        if transition.id in discovered and transition.activity is not None
    )


@dataclass(frozen=True, slots=True)
class _Endpoint:
    marking: Marking
    moves: tuple[AlignmentMove, ...]
    cost: int
    future: int


def _window_search(events, net, initial, final, remaining, spec, cap):
    labels = {transition.id: transition.activity for transition in net.transitions}
    bound_cache = {}

    def bound(marking):
        if final is not None:
            return 0
        if marking not in bound_cache:
            reachable = _reachable_labels(net, marking)
            bound_cache[marking] = (
                sum(label not in reachable for label in remaining)
                * spec.alignment.log_move_cost
            )
        return bound_cache[marking]

    serial = count()
    initial_state = (0, initial, 0)
    costs, parents = {initial_state: 0}, {}
    heap = [(bound(initial), 0, next(serial), 0, initial_state)]
    settled, endpoints, endpoint_markings = set(), [], set()
    limited = False

    def witness(state):
        path = []
        while state != initial_state:
            state, move = parents[state]
            path.append(move)
        return tuple(reversed(path))

    while heap:
        _, _, _, cost, state = heappop(heap)
        if state in settled or costs[state] != cost:
            continue
        if len(settled) >= cap:
            limited = True
            break
        settled.add(state)
        position, marking, post = state
        consumed = position == len(events)
        if consumed and (final is None or marking == final):
            if marking not in endpoint_markings:
                endpoints.append(
                    _Endpoint(marking, witness(state), cost, bound(marking))
                )
                endpoint_markings.add(marking)
                if final is not None or len(endpoints) >= spec.max_candidates:
                    break
        event = events[position] if not consumed else None
        choices = []
        for transition in enabled_transitions(net, marking):
            activity = labels[transition]
            after = fire(net, marking, transition)
            if (
                event is not None
                and activity is not None
                and event.activity == activity
            ):
                choices.append(
                    (
                        (position + 1, after, 0),
                        AlignmentMove(
                            "synchronous",
                            event.event_id,
                            transition,
                            activity,
                            spec.alignment.synchronous_move_cost,
                            marking.tokens,
                            after.tokens,
                        ),
                    )
                )
            if not consumed or final is not None or post < spec.max_post_model_moves:
                choices.append(
                    (
                        (
                            position,
                            after,
                            post + 1 if consumed and final is None else 0,
                        ),
                        AlignmentMove(
                            "silent" if activity is None else "model",
                            None,
                            transition,
                            activity,
                            spec.alignment.silent_move_cost
                            if activity is None
                            else spec.alignment.model_move_cost,
                            marking.tokens,
                            after.tokens,
                        ),
                    )
                )
        if event is not None:
            choices.append(
                (
                    (position + 1, marking, 0),
                    AlignmentMove(
                        "log",
                        event.event_id,
                        None,
                        event.activity,
                        spec.alignment.log_move_cost,
                        marking.tokens,
                        marking.tokens,
                    ),
                )
            )
        for following, move in choices:
            candidate = cost + move.cost
            if following not in costs or candidate < costs[following]:
                costs[following], parents[following] = candidate, (state, move)
                heappush(
                    heap,
                    (
                        candidate + bound(following[1]),
                        -following[0],
                        next(serial),
                        candidate,
                        following,
                    ),
                )
    return tuple(endpoints), len(settled), limited


def _sliding(
    trace: ObjectTrace, net: PetriNet, spec: SlidingWindowSpec
) -> _StrategyResult:
    windows = tuple(
        (start, min(start + spec.window_size, len(trace.events)))
        for start in range(0, len(trace.events), spec.window_size)
    ) or ((0, 0),)
    candidates = (_Endpoint(net.initial_marking, (), 0, 0),)
    evidence, total, encountered_limit = [], 0, False
    for index, (start, end) in enumerate(windows):
        final = index == len(windows) - 1
        extensions, local_states, limited = [], 0, False
        for candidate in candidates:
            cap = min(spec.alignment.max_states, spec.max_total_states - total)
            if cap <= 0:
                limited = True
                break
            found, states, local_limit = _window_search(
                trace.events[start:end],
                net,
                candidate.marking,
                net.final_marking if final else None,
                tuple(event.activity for event in trace.events[end:]),
                spec,
                cap,
            )
            total += states
            local_states += states
            limited |= local_limit
            extensions.extend(
                _Endpoint(
                    endpoint.marking,
                    candidate.moves + endpoint.moves,
                    candidate.cost + endpoint.cost,
                    endpoint.future,
                )
                for endpoint in found
            )
        extensions.sort(
            key=lambda endpoint: (
                endpoint.cost + endpoint.future,
                endpoint.cost,
                endpoint.marking.tokens,
            )
        )
        distinct = {}
        for endpoint in extensions:
            distinct.setdefault(endpoint.marking, endpoint)
        retained = tuple(distinct.values())[: 1 if final else spec.max_candidates]
        evidence.append(
            SlidingWindowStage(
                start,
                end,
                final,
                len(candidates),
                len(extensions),
                tuple(
                    WindowCandidate(item.marking, item.cost, item.future)
                    for item in retained
                ),
                local_states,
                limited,
            )
        )
        encountered_limit |= limited
        if not retained:
            return _StrategyResult(
                "search_limit" if encountered_limit else "unavailable",
                (),
                total,
                "window_search_limit"
                if encountered_limit
                else "retained_window_dead_end",
                windows=tuple(evidence),
            )
        candidates = retained
    return _StrategyResult(
        "complete",
        candidates[0].moves,
        total,
        "local_search_limit_with_complete_witness" if encountered_limit else None,
        exact_whole_trace=len(windows) == 1 and not encountered_limit,
        windows=tuple(evidence),
    )


def _fixed(trace, net, spec):
    outcome = run_fixed_horizon(trace, net, spec)
    return _StrategyResult(
        outcome.status,
        outcome.moves if outcome.status == "complete" else (),
        outcome.total_states,
        outcome.fallback_reason,
        fixed=outcome,
    )


def _validate(
    trace: ObjectTrace,
    net: PetriNet,
    spec: AlignmentSpec,
    moves: tuple[AlignmentMove, ...],
) -> bool:
    """Check every input identity, label, cost, marking snapshot and enabled firing."""
    transitions = {transition.id: transition.activity for transition in net.transitions}
    marking, position = net.initial_marking, 0
    for move in moves:
        if move.before_marking != marking.tokens:
            return False
        if move.kind in ("log", "synchronous"):
            if position >= len(trace.events):
                return False
            event = trace.events[position]
            if move.event_id != event.event_id or move.activity != event.activity:
                return False
            position += 1
        elif move.event_id is not None:
            return False
        if move.transition_id is None:
            if move.kind != "log" or move.cost != spec.log_move_cost:
                return False
        else:
            if move.transition_id not in enabled_transitions(net, marking):
                return False
            activity = transitions[move.transition_id]
            if activity != move.activity:
                return False
            expected = (
                spec.synchronous_move_cost
                if move.kind == "synchronous"
                else spec.silent_move_cost
                if move.kind == "silent" and activity is None
                else spec.model_move_cost
                if move.kind == "model" and activity is not None
                else None
            )
            if expected is None or move.cost != expected:
                return False
            marking = fire(net, marking, move.transition_id)
        if move.after_marking != marking.tokens:
            return False
    return position == len(trace.events) and marking == net.final_marking


def _one(trace, net, spec, strategy, run):
    outcome = run(trace, net, spec)
    moves = outcome.moves
    full = outcome.status == "complete" and _validate(trace, net, spec.alignment, moves)
    fallback_used, fallback_states, verify_states = False, 0, 0
    reason = outcome.reason
    certificate, exact_status, exact_cost = "none", None, None
    lower = 0
    if outcome.status == "complete" and not full:
        reason = "strategy_witness_validation_failed"
    status = (
        outcome.status
        if outcome.status in ("search_limit", "unreachable")
        else "unavailable"
    )
    if full:
        cost = sum(move.cost for move in moves)
        if outcome.exact_whole_trace:
            certificate, exact_cost, lower = "whole_trace_search", cost, cost
        elif cost == 0:
            certificate, exact_cost = "zero_cost", 0
        status = "optimal" if certificate != "none" else "approximate"
    elif spec.fallback_to_exact:
        fallback_used = True
        fallback = _align(trace, net, spec.alignment)
        fallback_states = fallback.settled_states
        if fallback.status == "optimal":
            moves, full, status = fallback.moves, True, "optimal"
            if not _validate(trace, net, spec.alignment, moves):
                raise RuntimeError("native exact fallback returned an invalid witness")
            certificate, exact_cost, lower = (
                "exact_fallback",
                fallback.cost,
                fallback.cost,
            )
        else:
            moves, status = (), fallback.status
            lower = fallback.lower_bound_cost
        reason = reason or "strategy_" + outcome.status
    if (
        full
        and spec.verify_exact
        and certificate not in ("exact_fallback", "whole_trace_search")
    ):
        verified = _align(trace, net, spec.alignment)
        verify_states, exact_status = verified.settled_states, verified.status
        if verified.status == "optimal":
            exact_cost, lower = verified.cost, verified.cost
            if verified.cost > sum(move.cost for move in moves):
                raise RuntimeError(
                    "exact cost exceeded a validated executable upper bound"
                )
            if verified.cost == sum(move.cost for move in moves):
                certificate, status = "exact_verification", "optimal"
        elif verified.status == "search_limit":
            lower = max(lower or 0, verified.lower_bound_cost or 0)
        else:
            raise RuntimeError(
                "exact search rejected a validated executable accepting witness"
            )
    return ApproximateTraceAlignment(
        trace.object_id,
        strategy,
        status,
        moves if full else (),
        sum(move.cost for move in moves) if full else None,
        exact_cost,
        lower,
        certificate,
        exact_status,
        fallback_used,
        reason,
        outcome.states,
        verify_states,
        fallback_states,
        len(trace.events),
        outcome.reduced_length,
        outcome.repeats,
        outcome.windows,
        outcome.fixed,
    )


def _apply(log, net, spec, strategy, request_type, run):
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    source = as_case_traces(log)
    request = request_type(model_digest(net), spec)
    operator = "pix.case_centric.align_" + strategy
    parents = (source.computation_id,) if source.computation_id is not None else ()
    if source.status is not ComputeStatus.COMPUTED or not isinstance(
        source.value, TraceSet
    ):
        return _result(
            operator,
            None,
            request,
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            source.issues
            + (
                ComputeIssue(
                    "trace_result_unavailable", "A complete TraceSet is required"
                ),
            ),
            source_digest=source.source_digest,
            parent_computation_ids=parents,
        )
    traces = tuple(
        _one(trace, net, spec, strategy, run) for trace in source.value.traces
    )
    incomplete = tuple(item for item in traces if item.cost_upper_bound is None)
    completed_cost = sum(
        item.cost_upper_bound for item in traces if item.cost_upper_bound is not None
    )
    value = ApproximateAlignmentSet(
        request.model_digest,
        strategy,
        traces,
        len(traces),
        len(traces) - len(incomplete),
        sum(item.status == "optimal" for item in traces),
        sum(item.status == "approximate" for item in traces),
        len(incomplete),
        completed_cost,
        completed_cost if not incomplete else None,
    )
    issues = source.issues + tuple(
        ComputeIssue(
            "approximation_incomplete",
            item.fallback_reason or item.status,
            ("case", item.case_id),
        )
        for item in incomplete
    )
    return _result(
        operator,
        None,
        request,
        ComputeStatus.PARTIAL if incomplete else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=source.source_digest,
        parent_computation_ids=parents,
    )


def align_tandem_repeats(
    log: CaseInput, net: PetriNet, spec: TandemRepeatSpec = TandemRepeatSpec()
) -> ComputationResult[ApproximateAlignmentSet]:
    """Compress repeated activity blocks, align, and validate expanded witnesses."""
    if not isinstance(spec, TandemRepeatSpec):
        raise TypeError("spec must be TandemRepeatSpec")
    return _apply(log, net, spec, "tandem_repeats", TandemRepeatRequest, _tandem)


def align_sliding_window(
    log: CaseInput, net: PetriNet, spec: SlidingWindowSpec = SlidingWindowSpec()
) -> ComputationResult[ApproximateAlignmentSet]:
    """Retain and extend a bounded beam of endpoint markings over windows."""
    if not isinstance(spec, SlidingWindowSpec):
        raise TypeError("spec must be SlidingWindowSpec")
    return _apply(log, net, spec, "sliding_window", SlidingWindowRequest, _sliding)


def align_fixed_horizon(
    log: CaseInput, net: PetriNet, spec: FixedHorizonSpec = FixedHorizonSpec()
) -> ComputationResult[ApproximateAlignmentSet]:
    """Commit executable finite prefixes ranked by certified integer tail costs."""
    if not isinstance(spec, FixedHorizonSpec):
        raise TypeError("spec must be FixedHorizonSpec")
    return _apply(log, net, spec, "fixed_horizon", FixedHorizonRequest, _fixed)


RESULT_SCHEMAS = {
    "pix.case_centric.align_tandem_repeats": (
        "case-approximate-alignment",
        TandemRepeatRequest,
        ApproximateAlignmentSet,
    ),
    "pix.case_centric.align_sliding_window": (
        "case-approximate-alignment",
        SlidingWindowRequest,
        ApproximateAlignmentSet,
    ),
    "pix.case_centric.align_fixed_horizon": (
        "case-approximate-alignment",
        FixedHorizonRequest,
        ApproximateAlignmentSet,
    ),
}

__all__ = (
    "TandemRepeatSpec",
    "SlidingWindowSpec",
    "FixedHorizonSpec",
    "TandemRepeatRequest",
    "SlidingWindowRequest",
    "FixedHorizonRequest",
    "TandemRepeatReduction",
    "WindowCandidate",
    "SlidingWindowStage",
    "ApproximateTraceAlignment",
    "ApproximateAlignmentSet",
    "align_tandem_repeats",
    "align_sliding_window",
    "align_fixed_horizon",
)
