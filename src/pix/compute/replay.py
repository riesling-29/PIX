"""Native deterministic token replay with bounded silent reachability evidence.

This is a local heuristic over per-object traces and a classical Petri net. It
does not claim optimal alignments, OCPN joint binding fitness, or model soundness.
Unknown activities are explicit log deviations. Initial tokens count as produced;
the target final marking is consumed at completed finalization. Missing final
tokens are recorded as insertions, with all surplus retained as remaining tokens.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from pix.compute._common import _result
from pix.compute.model_semantics import fire, is_enabled, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.models import Marking, PetriNet
from pix.contracts.replay import (
    ReplayRequest,
    ReplaySet,
    ReplaySpec,
    ReplayStep,
    SilentSearch,
    TokenCounts,
    TokenSnapshot,
    TraceReplay,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

REPLAY_OPERATOR_ID = "pix.replay_traces"


@dataclass(frozen=True, slots=True)
class _Closure:
    states: tuple[tuple[Marking, tuple[str, ...]], ...]
    choice: tuple[Marking, tuple[str, ...], str | None] | None
    limited: bool


def _silent_closure(
    net: PetriNet,
    start: Marking,
    limit: int,
    activity: str | None,
) -> _Closure:
    """BFS; activity None means exact final-marking target, never a silent match."""
    queue = deque([(start, ())])
    paths: dict[Marking, tuple[str, ...]] = {start: ()}
    truncated = False
    silent = tuple(t.id for t in net.transitions if t.activity is None)
    matching = tuple(t.id for t in net.transitions if t.activity == activity)
    while queue:
        current, path = queue.popleft()
        if activity is None:
            if current == net.final_marking:
                return _Closure(tuple(paths.items()), (current, path, None), False)
        else:
            for transition_id in matching:
                if is_enabled(net, current, transition_id):
                    return _Closure(
                        tuple(paths.items()), (current, path, transition_id), False
                    )
        for transition_id in silent:
            if not is_enabled(net, current, transition_id):
                continue
            after = fire(net, current, transition_id)
            if after in paths:
                continue
            if len(paths) >= limit:
                # Previously admitted BFS states precede any omitted successor.
                # Check them for a goal before reporting an incomplete closure.
                truncated = True
                continue
            next_path = path + (transition_id,)
            paths[after] = next_path
            queue.append((after, next_path))
    return _Closure(tuple(paths.items()), None, truncated)


def _sum(tokens: TokenSnapshot) -> int:
    return sum(count for _, count in tokens)


def _deficit(current: Marking, required: TokenSnapshot) -> TokenSnapshot:
    present = dict(current.tokens)
    return tuple(
        (place, count - present.get(place, 0))
        for place, count in required
        if count > present.get(place, 0)
    )


def _insert(current: Marking, tokens: TokenSnapshot) -> Marking:
    present = dict(current.tokens)
    for place, count in tokens:
        present[place] = present.get(place, 0) + count
    return Marking(tuple(present.items()))


def _incidence(
    net: PetriNet, transition_id: str
) -> tuple[TokenSnapshot, TokenSnapshot]:
    inputs = tuple((a.source, a.weight) for a in net.arcs if a.target == transition_id)
    outputs = tuple((a.target, a.weight) for a in net.arcs if a.source == transition_id)
    return tuple(sorted(inputs)), tuple(sorted(outputs))


def _firing(
    net: PetriNet,
    current: Marking,
    transition_id: str,
    *,
    event_id: str | None = None,
    activity: str | None = None,
    inserted: TokenSnapshot = (),
) -> tuple[Marking, ReplayStep]:
    inputs, outputs = _incidence(net, transition_id)
    after = fire(net, _insert(current, inserted), transition_id)
    return after, ReplayStep(
        "silent" if event_id is None else "visible",
        event_id,
        activity,
        transition_id,
        current.tokens,
        after.tokens,
        inserted,
        inputs,
        outputs,
    )


def _follow(
    net: PetriNet, current: Marking, path: tuple[str, ...], steps: list[ReplayStep]
) -> Marking:
    for transition_id in path:
        current, step = _firing(net, current, transition_id)
        steps.append(step)
    return current


def _counts(steps: list[ReplayStep], ending: Marking) -> TokenCounts:
    return TokenCounts(
        missing=sum(_sum(step.inserted_tokens) for step in steps),
        remaining=_sum(ending.tokens),
        consumed=sum(_sum(step.consumed_tokens) for step in steps),
        produced=sum(_sum(step.produced_tokens) for step in steps),
    )


def _replay_trace(trace: ObjectTrace, net: PetriNet, spec: ReplaySpec) -> TraceReplay:
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
    searches: list[SilentSearch] = []
    processed = 0
    log_deviations = 0

    def limited() -> TraceReplay:
        return TraceReplay(
            trace.object_id,
            "limited",
            len(trace.events),
            processed,
            log_deviations,
            tuple(steps),
            tuple(searches),
            net.final_marking.tokens,
            current.tokens,
            None,
            _counts(steps, current),
            "silent_state_limit",
        )

    for event in trace.events:
        candidates = tuple(
            t.id for t in net.transitions if t.activity == event.activity
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
            log_deviations += 1
            processed += 1
            continue

        closure = _silent_closure(net, current, spec.silent_max_states, event.activity)
        searches.append(
            SilentSearch(
                event.event_id,
                len(closure.states),
                closure.choice is None and not closure.limited,
                closure.limited,
            )
        )
        if closure.limited:
            return limited()
        if closure.choice is not None:
            _, path, selected = closure.choice
        else:
            # No enabled match anywhere in the exhaustively explored closure.
            # The repair rule is local and intentionally makes no optimum claim.
            options = (
                (
                    _sum(_deficit(state, _incidence(net, transition)[0])),
                    len(path),
                    path,
                    transition,
                )
                for state, path in closure.states
                for transition in candidates
            )
            _, _, path, selected = min(options)
        assert selected is not None
        current = _follow(net, current, path, steps)
        inserted = _deficit(current, _incidence(net, selected)[0])
        current, step = _firing(
            net,
            current,
            selected,
            event_id=event.event_id,
            activity=event.activity,
            inserted=inserted,
        )
        steps.append(step)
        processed += 1

    closure = _silent_closure(net, current, spec.silent_max_states, None)
    searches.append(
        SilentSearch(
            None,
            len(closure.states),
            closure.choice is None and not closure.limited,
            closure.limited,
        )
    )
    if closure.limited:
        return limited()
    final_reached = closure.choice is not None
    if closure.choice is not None:
        _, path, _ = closure.choice
    else:
        # Finalization selects least missing + surplus, then least missing,
        # shortest silent path, lexical path. It cannot fire visible model moves.
        final_size = _sum(net.final_marking.tokens)
        options = (
            (
                2 * _sum(_deficit(state, net.final_marking.tokens))
                + _sum(state.tokens)
                - final_size,
                _sum(_deficit(state, net.final_marking.tokens)),
                len(path),
                path,
            )
            for state, path in closure.states
        )
        _, _, _, path = min(options)
    current = _follow(net, current, path, steps)
    inserted = _deficit(current, net.final_marking.tokens)
    repaired = dict(_insert(current, inserted).tokens)
    for place, count in net.final_marking.tokens:
        repaired[place] -= count
    ending = Marking(tuple((p, n) for p, n in repaired.items() if n))
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
    return TraceReplay(
        trace.object_id,
        "completed",
        len(trace.events),
        processed,
        log_deviations,
        tuple(steps),
        tuple(searches),
        net.final_marking.tokens,
        ending.tokens,
        final_reached,
        _counts(steps, ending),
    )


def _total(cases: tuple[TraceReplay, ...]) -> TokenCounts:
    return TokenCounts(
        **{
            name: sum(getattr(case.counts, name) for case in cases)
            for name in ("missing", "remaining", "consumed", "produced")
        }
    )


def replay_traces(
    traces: ComputationResult[TraceSet],
    net: PetriNet,
    spec: ReplaySpec = ReplaySpec(),
) -> ComputationResult[ReplaySet]:
    """Replay each object trace independently and retain evidence for every case.

    The result identity includes the input trace computation and semantic model
    digest. A completed replay may have deviations. PARTIAL means at least one
    silent search hit its state bound; no outcome or denominator is fabricated.
    Invalid upstream input retains its status and diagnostics; incomplete upstream
    traces are unavailable rather than replayed as if they were the full input.
    """
    if not isinstance(traces, ComputationResult):
        raise TypeError("traces must be a ComputationResult[TraceSet]")
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, ReplaySpec):
        raise TypeError("spec must be ReplaySpec")
    resolved = ReplayRequest(model_digest(net), spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()
    if traces.status is not ComputeStatus.COMPUTED:
        return _result(
            REPLAY_OPERATOR_ID,
            None,
            resolved,
            (
                ComputeStatus.INVALID_INPUT
                if traces.status is ComputeStatus.INVALID_INPUT
                else ComputeStatus.UNAVAILABLE
            ),
            None,
            (ComputeIssue("upstream_not_computed", "Replay requires completed traces"),)
            + traces.issues,
            source_digest=traces.source_digest,
            parent_computation_ids=parents,
        )
    if not isinstance(traces.value, TraceSet):
        raise TypeError("computed traces must contain TraceSet")

    cases = tuple(_replay_trace(case, net, spec) for case in traces.value.traces)
    completed = tuple(case for case in cases if case.status == "completed")
    issues = tuple(
        ComputeIssue(
            "silent_state_limit",
            "Silent reachability search was truncated",
            ("object", case.object_id),
        )
        for case in cases
        if case.status == "limited"
    )
    event_count = sum(case.event_count for case in cases)
    processed_count = sum(case.processed_event_count for case in cases)
    value = ReplaySet(
        traces.value.object_type,
        resolved.model_digest,
        cases,
        len(cases),
        len(completed),
        len(cases) - len(completed),
        0,
        event_count,
        processed_count,
        event_count - processed_count,
        sum(case.log_deviation_count for case in cases),
        _total(completed),
        _total(cases),
    )
    status = ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED
    return _result(
        REPLAY_OPERATOR_ID,
        None,
        resolved,
        status,
        value,
        issues,
        source_digest=traces.source_digest,
        parent_computation_ids=parents,
    )


__all__ = ("REPLAY_OPERATOR_ID", "replay_traces")
