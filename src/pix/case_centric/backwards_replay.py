"""Forward event replay using native backward silent-transition planning.

Visible enabling regresses token requirements; exact final completion reverses
weighted firing equations. Neither the trace nor the model is passed to the
ordinary forward replay engine. Local deterministic choices and repair rules
are a PIX profile, not PM4Py BACKWARDS numerical compatibility or alignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.compute.model_semantics import fire, model_digest
from pix.contracts.analysis import TraceSet
from pix.contracts.models import Marking, PetriNet
from pix.contracts.replay import ReplayStep, TokenCounts, TokenSnapshot
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class BackwardsReplaySpec:
    """Bound admitted (target, required marking) states per event/final search.

    Directly enabled visible transitions prefer the smallest transition ID.
    Otherwise select a shortest legal silent enabling plan, then lexical
    forward silent path and visible transition ID. A complete failed enabling
    search repairs only the selected visible preset, minimizing inserted token
    count then transition ID. This is not minimum repair over a whole trace.
    """

    backward_max_states: int = 1000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if type(self.backward_max_states) is not int:
            raise TypeError("backward_max_states must be an integer")
        if self.backward_max_states < 1:
            raise ValueError("backward_max_states must be positive")


@dataclass(frozen=True, slots=True)
class BackwardsReplayRequest:
    model_digest: str
    parameters: BackwardsReplaySpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class BackwardRegression:
    transition_id: str
    required_after: TokenSnapshot
    required_before: TokenSnapshot


@dataclass(frozen=True, slots=True)
class BackwardSearch:
    event_id: str | None
    mode: Literal["cover_preset", "exact_final"]
    admitted_states: int
    expanded_states: int
    exhausted: bool
    limited: bool
    selected_transition_id: str | None
    target_marking: TokenSnapshot
    regressions: tuple[BackwardRegression, ...]


@dataclass(frozen=True, slots=True)
class BackwardsTraceReplay:
    case_id: str
    status: Literal["completed", "limited"]
    event_count: int
    processed_event_count: int
    log_deviation_count: int
    steps: tuple[ReplayStep, ...]
    searches: tuple[BackwardSearch, ...]
    final_reached: bool | None
    ending_marking: TokenSnapshot
    counts: TokenCounts


@dataclass(frozen=True, slots=True)
class BackwardsReplaySet:
    """Token evidence, not normalized fitness; limited prefix totals separate."""

    model_digest: str
    traces: tuple[BackwardsTraceReplay, ...]
    trace_count: int
    completed_count: int
    limited_count: int
    event_count: int
    processed_event_count: int
    unprocessed_event_count: int
    log_deviation_count: int
    completed_counts: TokenCounts
    attempted_counts: TokenCounts


@dataclass(frozen=True, slots=True)
class _Plan:
    search: BackwardSearch
    path: tuple[str, ...] | None


def _size(tokens: TokenSnapshot) -> int:
    return sum(value for _, value in tokens)


def _covers(have: Marking, need: Marking) -> bool:
    present = dict(have.tokens)
    return all(present.get(place, 0) >= value for place, value in need.tokens)


def _deficit(have: Marking, need: TokenSnapshot) -> TokenSnapshot:
    present = dict(have.tokens)
    return tuple(
        (place, value - present.get(place, 0))
        for place, value in need
        if value > present.get(place, 0)
    )


def _insert(have: Marking, inserted: TokenSnapshot) -> Marking:
    values = dict(have.tokens)
    for place, amount in inserted:
        values[place] = values.get(place, 0) + amount
    return Marking(tuple(values.items()))


def _incidences(net: PetriNet):
    return {
        transition.id: (
            Marking(
                tuple(
                    (arc.source, arc.weight)
                    for arc in net.arcs
                    if arc.target == transition.id
                )
            ),
            Marking(
                tuple(
                    (arc.target, arc.weight)
                    for arc in net.arcs
                    if arc.source == transition.id
                )
            ),
        )
        for transition in net.transitions
    }


def _regress(
    required: Marking, pre: Marking, post: Marking, exact: bool
) -> Marking | None:
    """Inverse weighted equation or minimal sufficient predecessor requirement."""
    if exact and not _covers(required, post):
        return None
    need, inputs, outputs = dict(required.tokens), dict(pre.tokens), dict(post.tokens)
    values = {
        place: inputs.get(place, 0) + max(need.get(place, 0) - outputs.get(place, 0), 0)
        for place in need.keys() | inputs.keys() | outputs.keys()
    }
    return Marking(tuple((place, value) for place, value in values.items() if value))


def _search(current, goals, silent, incidence, spec, event_id, exact):
    """Search backward; stored paths are legal *forward* suffix plans.

    Cover-mode dominance discards a requirement only when an already known
    smaller/equal requirement has a shorter or lexically no-larger suffix for
    the same target. Any future prefix sufficient for the dominated suffix is
    also sufficient for that preferred suffix. Exact-final states never use
    this upward-closed pruning.
    """
    mode = "exact_final" if exact else "cover_preset"
    paths, queue, serial = {}, [], count()
    expanded, limited = 0, False

    def satisfies(required):
        return current == required if exact else _covers(current, required)

    def finish(path=None, target=None, requirement=None, exhausted=False):
        regressions = []
        if path is not None:
            requirement = dict(goals)[target]
            goal_requirement = requirement
            for transition_id in reversed(path):
                before = _regress(requirement, *incidence[transition_id], exact)
                assert before is not None
                regressions.append(
                    BackwardRegression(transition_id, requirement.tokens, before.tokens)
                )
                requirement = before
        else:
            goal_requirement = Marking()
        return _Plan(
            BackwardSearch(
                event_id,
                mode,
                len(paths),
                expanded,
                exhausted,
                limited,
                target,
                goal_requirement.tokens,
                tuple(regressions),
            ),
            path,
        )

    # Evaluate every direct candidate before allocating a multi-source search.
    for target, requirement in goals:
        if satisfies(requirement):
            paths[(target, requirement)] = ()
            expanded = 1
            return finish((), target, requirement)
    for target, requirement in goals:
        if len(paths) >= spec.backward_max_states:
            limited = True
            return finish()
        paths[(target, requirement)] = ()
        heappush(queue, (0, (), target or "", next(serial), target, requirement))
    while queue:
        length, path, _, _, target, requirement = heappop(queue)
        if paths[(target, requirement)] != path:
            continue
        expanded += 1
        if satisfies(requirement):
            # An omitted state could contain a preferred earlier plan. Do not
            # silently turn a successful incumbent into a complete replay rule.
            return finish() if limited else finish(path, target, requirement)
        for transition_id in silent:
            before = _regress(requirement, *incidence[transition_id], exact)
            if before is None:
                continue
            candidate = (transition_id,) + path
            state = (target, before)
            previous = paths.get(state)
            if previous is not None and (len(previous), previous) <= (
                length + 1,
                candidate,
            ):
                continue
            if not exact and any(
                other_target == target
                and _covers(before, other_requirement)
                and (len(other_path), other_path) <= (length + 1, candidate)
                for (other_target, other_requirement), other_path in paths.items()
            ):
                continue
            if state not in paths and len(paths) >= spec.backward_max_states:
                limited = True
                continue
            paths[state] = candidate
            heappush(
                queue,
                (length + 1, candidate, target or "", next(serial), target, before),
            )
    return finish(exhausted=not limited)


def _counts(steps, ending):
    return TokenCounts(
        missing=sum(_size(step.inserted_tokens) for step in steps),
        remaining=_size(ending.tokens),
        consumed=sum(_size(step.consumed_tokens) for step in steps),
        produced=sum(_size(step.produced_tokens) for step in steps),
    )


def _trace(trace, net, spec, incidence, silent):
    current = net.initial_marking
    steps = [
        ReplayStep(
            "initial",
            None,
            None,
            None,
            (),
            current.tokens,
            produced_tokens=current.tokens,
        )
    ]
    searches, processed, deviations = [], 0, 0

    def finish(status, final_reached=None):
        return BackwardsTraceReplay(
            trace.object_id,
            status,
            len(trace.events),
            processed,
            deviations,
            tuple(steps),
            tuple(searches),
            final_reached,
            current.tokens,
            _counts(steps, current),
        )

    def execute(transition_id, event=None, inserted=()):
        nonlocal current
        before = current
        current = fire(net, _insert(current, inserted), transition_id)
        pre, post = incidence[transition_id]
        steps.append(
            ReplayStep(
                "silent" if event is None else "visible",
                event.event_id if event else None,
                event.activity if event else None,
                transition_id,
                before.tokens,
                current.tokens,
                inserted,
                pre.tokens,
                post.tokens,
            )
        )

    for event in trace.events:
        candidates = tuple(
            transition.id
            for transition in net.transitions
            if transition.activity == event.activity
        )
        if not candidates:
            steps.append(
                ReplayStep(
                    "log_deviation",
                    event.event_id,
                    event.activity,
                    None,
                    current.tokens,
                    current.tokens,
                )
            )
            deviations += 1
            processed += 1
            continue
        goals = tuple(
            (transition, incidence[transition][0]) for transition in candidates
        )
        plan = _search(current, goals, silent, incidence, spec, event.event_id, False)
        searches.append(plan.search)
        if plan.search.limited:
            return finish("limited")
        if plan.path is not None:
            for transition_id in plan.path:
                execute(transition_id)
            selected = plan.search.selected_transition_id
            assert selected is not None
        else:
            selected = min(
                candidates,
                key=lambda candidate: (
                    _size(_deficit(current, incidence[candidate][0].tokens)),
                    candidate,
                ),
            )
        inserted = _deficit(current, incidence[selected][0].tokens)
        execute(selected, event, inserted)
        processed += 1
    plan = _search(
        current, ((None, net.final_marking),), silent, incidence, spec, None, True
    )
    searches.append(plan.search)
    if plan.search.limited:
        return finish("limited")
    final_reached = plan.path is not None
    if plan.path is not None:
        for transition_id in plan.path:
            execute(transition_id)
    inserted = _deficit(current, net.final_marking.tokens)
    repaired = dict(_insert(current, inserted).tokens)
    for place, value in net.final_marking.tokens:
        repaired[place] -= value
    ending = Marking(
        tuple((place, value) for place, value in repaired.items() if value)
    )
    steps.append(
        ReplayStep(
            "finalize",
            None,
            None,
            None,
            current.tokens,
            ending.tokens,
            inserted,
            net.final_marking.tokens,
        )
    )
    current = ending
    return finish("completed", final_reached)


def _total(cases):
    return TokenCounts(
        **{
            field: sum(getattr(case.counts, field) for case in cases)
            for field in ("missing", "remaining", "consumed", "produced")
        }
    )


def replay_backwards(
    log: CaseInput,
    net: PetriNet,
    spec: BackwardsReplaySpec = BackwardsReplaySpec(),
) -> ComputationResult[BackwardsReplaySet]:
    """Replay in event order with independently regressed silent enabling plans.

    Unknown activities remain explicit log deviations. Failed backward search
    permits local token insertion only after exhaustion. A resource limit stops
    that trace with unknown outcome and separate attempted prefix accounting.
    Counts include initial production and target-final consumption; zero token
    denominators and unknown activities are not hidden inside fitness scores.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, BackwardsReplaySpec):
        raise TypeError("spec must be BackwardsReplaySpec")
    traces = as_case_traces(log)
    request = BackwardsReplayRequest(model_digest(net), spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()

    def result(status, value=None, issues=()):
        return _result(
            "pix.case_centric.replay_backwards",
            None,
            request,
            status,
            value,
            traces.issues + issues,
            source_digest=traces.source_digest,
            parent_computation_ids=parents,
        )

    if traces.status is not ComputeStatus.COMPUTED or not isinstance(
        traces.value, TraceSet
    ):
        return result(
            ComputeStatus.INVALID_INPUT
            if traces.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "upstream_not_computed", "Backward replay requires completed traces"
                ),
            ),
        )
    incidence = _incidences(net)
    silent = tuple(
        transition.id for transition in net.transitions if transition.activity is None
    )
    cases = tuple(
        _trace(trace, net, spec, incidence, silent) for trace in traces.value.traces
    )
    completed = tuple(case for case in cases if case.status == "completed")
    issues = tuple(
        ComputeIssue(
            "backward_state_limit",
            "Backward planning was truncated",
            ("case", case.case_id),
        )
        for case in cases
        if case.status == "limited"
    )
    events = sum(case.event_count for case in cases)
    processed = sum(case.processed_event_count for case in cases)
    value = BackwardsReplaySet(
        request.model_digest,
        cases,
        len(cases),
        len(completed),
        len(cases) - len(completed),
        events,
        processed,
        events - processed,
        sum(case.log_deviation_count for case in cases),
        _total(completed),
        _total(cases),
    )
    return result(
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED, value, issues
    )


RESULT_SCHEMAS = {
    "pix.case_centric.replay_backwards": (
        "case_backwards_replay_set",
        BackwardsReplayRequest,
        BackwardsReplaySet,
    ),
}

__all__ = (
    "BackwardsReplaySpec",
    "BackwardsReplayRequest",
    "BackwardRegression",
    "BackwardSearch",
    "BackwardsTraceReplay",
    "BackwardsReplaySet",
    "replay_backwards",
)
