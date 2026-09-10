"""Native bounded Dijkstra trace alignment against an accepting weighted net.

Search states are (trace position, marking). Nonnegative integer edge costs
permit Dijkstra's settled-goal optimality proof. Exhausting a finite frontier
proves unreachability; reaching the resource limit never proves unreachability.
This is classical per-object trace alignment, not joint OCPN binding alignment.
"""

from __future__ import annotations

from heapq import heappop, heappush
from itertools import count

from pix.compute._common import _result
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import (
    AlignmentCoverage,
    AlignmentMove,
    AlignmentRequest,
    AlignmentSet,
    AlignmentSpec,
    TraceAlignment,
)
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

ALIGNMENT_OPERATOR_ID = "pix.align_traces"
State = tuple[int, Marking]


def _align(trace: ObjectTrace, net: PetriNet, spec: AlignmentSpec) -> TraceAlignment:
    events = trace.events
    event_ids = tuple(event.event_id for event in events)
    initial: State = (0, net.initial_marking)
    costs: dict[State, int] = {initial: 0}
    parents: dict[State, tuple[State, AlignmentMove]] = {}
    serial = count()
    heap: list[tuple[int, int, State]] = [(0, next(serial), initial)]
    settled: set[State] = set()
    activities = {transition.id: transition.activity for transition in net.transitions}

    def finish(
        status: str,
        state: State | None = None,
        cost: int | None = None,
        lower: int | None = None,
    ) -> TraceAlignment:
        moves: list[AlignmentMove] = []
        while state is not None and state != initial:
            state, move = parents[state]
            moves.append(move)
        return TraceAlignment(
            trace.object_id,
            event_ids,
            status,
            tuple(reversed(moves)),
            cost,
            len(settled),
            len(costs),
            lower,
        )

    while heap:
        cost, _, state = heappop(heap)
        if cost != costs[state] or state in settled:
            continue
        if len(settled) >= spec.max_states:
            return finish("search_limit", lower=cost)
        settled.add(state)
        position, marking = state
        if position == len(events) and marking == net.final_marking:
            return finish("optimal", state, cost, cost)

        # Stable move ordering only resolves equal-cost choices; it does not
        # merge distinct transition IDs or suppress cheaper log/model moves.
        moves: list[tuple[int, str, State, AlignmentMove]] = []
        for transition_id in enabled_transitions(net, marking):
            activity = activities[transition_id]
            after = fire(net, marking, transition_id)
            if activity is None:
                moves.append(
                    (
                        1,
                        transition_id,
                        (position, after),
                        AlignmentMove(
                            "silent",
                            None,
                            transition_id,
                            None,
                            spec.silent_move_cost,
                            marking.tokens,
                            after.tokens,
                        ),
                    )
                )
            else:
                if position < len(events) and events[position].activity == activity:
                    moves.append(
                        (
                            0,
                            transition_id,
                            (position + 1, after),
                            AlignmentMove(
                                "synchronous",
                                events[position].event_id,
                                transition_id,
                                activity,
                                spec.synchronous_move_cost,
                                marking.tokens,
                                after.tokens,
                            ),
                        )
                    )
                moves.append(
                    (
                        2,
                        transition_id,
                        (position, after),
                        AlignmentMove(
                            "model",
                            None,
                            transition_id,
                            activity,
                            spec.model_move_cost,
                            marking.tokens,
                            after.tokens,
                        ),
                    )
                )
        if position < len(events):
            event = events[position]
            moves.append(
                (
                    3,
                    "",
                    (position + 1, marking),
                    AlignmentMove(
                        "log",
                        event.event_id,
                        None,
                        event.activity,
                        spec.log_move_cost,
                        marking.tokens,
                        marking.tokens,
                    ),
                )
            )
        for _, _, following, move in sorted(moves, key=lambda item: item[:2]):
            candidate = cost + move.cost
            previous = costs.get(following)
            if previous is None or candidate < previous:
                costs[following] = candidate
                parents[following] = state, move
                heappush(heap, (candidate, next(serial), following))
    return finish("unreachable")


def align_traces(
    traces: ComputationResult[TraceSet],
    net: PetriNet,
    spec: AlignmentSpec = AlignmentSpec(),
) -> ComputationResult[AlignmentSet]:
    """Return one minimum-cost path per trace or explicit search-limit evidence.

    The selected trace ordering is inherited from the parent computation. The
    request identity additionally covers model semantics and all search/cost
    parameters. No implicit fallback, relabeling or normalized fitness is used.
    Invalid upstream input retains its status and diagnostics; other incomplete
    upstream results are unavailable because this operator requires whole traces.
    """
    if not isinstance(traces, ComputationResult):
        raise TypeError("traces must be a ComputationResult[TraceSet]")
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    if not isinstance(spec, AlignmentSpec):
        raise TypeError("spec must be AlignmentSpec")
    digest = model_digest(net)
    request = AlignmentRequest(digest, spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()
    if traces.status is not ComputeStatus.COMPUTED or not isinstance(
        traces.value, TraceSet
    ):
        return _result(
            ALIGNMENT_OPERATOR_ID,
            None,
            request,
            (
                ComputeStatus.INVALID_INPUT
                if traces.status is ComputeStatus.INVALID_INPUT
                else ComputeStatus.UNAVAILABLE
            ),
            None,
            (
                ComputeIssue(
                    "trace_result_unavailable", "A completed TraceSet is required"
                ),
            )
            + traces.issues,
            source_digest=traces.source_digest,
            parent_computation_ids=parents,
        )
    assert traces.computation_id is not None
    alignments = tuple(_align(trace, net, spec) for trace in traces.value.traces)
    optimal = sum(item.status == "optimal" for item in alignments)
    unreachable = sum(item.status == "unreachable" for item in alignments)
    limited = sum(item.status == "search_limit" for item in alignments)
    coverage = AlignmentCoverage(len(alignments), optimal, unreachable, limited)
    cost_sum = sum(item.cost for item in alignments if item.cost is not None)
    value = AlignmentSet(
        traces.value.object_type,
        digest,
        traces.computation_id,
        alignments,
        coverage,
        cost_sum,
        (cost_sum, optimal) if optimal else None,
        cost_sum if optimal == len(alignments) else None,
    )
    issues = tuple(
        ComputeIssue(
            "alignment_search_limit",
            "Settled-state limit reached; optimality is unknown",
            ("object", item.object_id),
        )
        for item in alignments
        if item.status == "search_limit"
    )
    return _result(
        ALIGNMENT_OPERATOR_ID,
        None,
        request,
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=traces.source_digest,
        parent_computation_ids=parents,
    )


__all__ = ("ALIGNMENT_OPERATOR_ID", "align_traces")
