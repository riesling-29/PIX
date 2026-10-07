"""Directly-follows counts over object traces, retaining every occurrence."""

from __future__ import annotations

from collections import Counter, defaultdict

from pix.compute._common import OPERATOR_VERSION, _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import (
    ActivityCount,
    BoundaryCount,
    BoundaryEvidence,
    DirectlyFollowsEdge,
    DirectlyFollowsGraph,
    TraceSet,
    TraceSpec,
    TransitionEvidence,
)
from pix.contracts.result import ComputationResult, ComputeStatus
from pix.ocel import OCEL

DFG_OPERATOR_ID = "pix.discover_dfg"


def _graph(traces: TraceSet) -> DirectlyFollowsGraph:
    transitions: dict[tuple[str, str], list[TransitionEvidence]] = defaultdict(list)
    occurrences: Counter[str] = Counter()
    event_ids: dict[str, set[str]] = defaultdict(set)
    object_ids: dict[str, set[str]] = defaultdict(set)
    starts: dict[str, list[BoundaryEvidence]] = defaultdict(list)
    ends: dict[str, list[BoundaryEvidence]] = defaultdict(list)
    for trace in traces.traces:
        for event in trace.events:
            occurrences[event.activity] += 1
            event_ids[event.activity].add(event.event_id)
            object_ids[event.activity].add(trace.object_id)
        for source, target in zip(trace.events, trace.events[1:]):
            transitions[source.activity, target.activity].append(
                TransitionEvidence(
                    trace.object_id,
                    source.event_id,
                    target.event_id,
                    source.relations,
                    target.relations,
                )
            )
        if trace.events:
            first, last = trace.events[0], trace.events[-1]
            starts[first.activity].append(
                BoundaryEvidence(trace.object_id, first.event_id)
            )
            ends[last.activity].append(BoundaryEvidence(trace.object_id, last.event_id))
    return DirectlyFollowsGraph(
        object_type=traces.object_type,
        object_count=len(traces.traces),
        empty_object_ids=tuple(t.object_id for t in traces.traces if not t.events),
        activities=tuple(
            ActivityCount(
                activity,
                occurrences[activity],
                tuple(sorted(event_ids[activity])),
                tuple(sorted(object_ids[activity])),
            )
            for activity in sorted(occurrences)
        ),
        edges=tuple(
            DirectlyFollowsEdge(source, target, len(evidence), tuple(evidence))
            for (source, target), evidence in sorted(transitions.items())
        ),
        starts=tuple(
            BoundaryCount(activity, tuple(evidence))
            for activity, evidence in sorted(starts.items())
        ),
        ends=tuple(
            BoundaryCount(activity, tuple(evidence))
            for activity, evidence in sorted(ends.items())
        ),
    )


def discover_dfg(
    log: OCEL | ComputationContext,
    spec: TraceSpec,
) -> ComputationResult[DirectlyFollowsGraph]:
    """Count (object, source event, target event) occurrences, not relation rows."""
    if not isinstance(spec, TraceSpec):
        raise TypeError("spec must be TraceSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            DFG_OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    traces = reconstruct_traces(context, spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()
    if traces.value is None:
        return _result(
            DFG_OPERATOR_ID,
            context,
            spec,
            traces.status,
            None,
            traces.issues,
            parent_computation_ids=parents,
        )
    return _result(
        DFG_OPERATOR_ID,
        context,
        spec,
        ComputeStatus.COMPUTED,
        _graph(traces.value),
        parent_computation_ids=parents,
    )


__all__ = ("DFG_OPERATOR_ID", "OPERATOR_VERSION", "discover_dfg")
