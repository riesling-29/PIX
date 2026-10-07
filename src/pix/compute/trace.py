"""Native per-object traces with explicit ordering and qualified E2O evidence."""

from __future__ import annotations

from collections import defaultdict

from pix.compute._common import OPERATOR_VERSION, _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.analysis import (
    E2OEvidence,
    ObjectTrace,
    TraceEvent,
    TraceSet,
    TraceSpec,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

TRACE_OPERATOR_ID = "pix.reconstruct_traces"


def _traces(
    context: ComputationContext,
    spec: TraceSpec,
) -> tuple[TraceSet | None, tuple[ComputeIssue, ...]]:
    if spec.object_type not in context.objects_by_type:
        return None, (
            ComputeIssue(
                "unknown_object_type",
                f"Object type {spec.object_type!r} is not declared in this OCEL",
                ("object_type", spec.object_type),
            ),
        )

    allowed = None if spec.qualifiers is None else frozenset(spec.qualifiers)
    traces: list[ObjectTrace] = []
    issues: list[ComputeIssue] = []
    for obj in context.objects_by_type[spec.object_type]:
        by_event: dict[str, list[E2OEvidence]] = defaultdict(list)
        for relation in context.e2o_by_object[obj.id]:
            if allowed is None or relation.qualifier in allowed:
                by_event[relation.event].append(
                    E2OEvidence(relation.event, relation.object, relation.qualifier)
                )
        events = sorted(
            (context.events_by_id[event_id] for event_id in by_event),
            key=lambda event: (event.time, event.id),
        )
        for previous, following in zip(events, events[1:]):
            if previous.time == following.time:
                if spec.tie_policy == "reject":
                    issues.append(
                        ComputeIssue(
                            "ambiguous_event_order",
                            "Equal timestamps within this object's selected events; "
                            "choose an explicit tie policy to compute a sequence",
                            ("object", obj.id, "events", previous.id, following.id),
                        )
                    )
                else:
                    issues.append(
                        ComputeIssue(
                            "timestamp_tie_broken",
                            "Equal timestamps were ordered by event ID under the "
                            "explicit event_id policy; this is not causal evidence",
                            ("object", obj.id, "events", previous.id, following.id),
                        )
                    )
        traces.append(
            ObjectTrace(
                obj.id,
                obj.type,
                tuple(
                    TraceEvent(
                        event.id, event.type, event.time, tuple(by_event[event.id])
                    )
                    for event in events
                ),
            )
        )
    if any(issue.code == "ambiguous_event_order" for issue in issues):
        return None, tuple(issues)
    return TraceSet(spec.object_type, tuple(traces)), tuple(issues)


def reconstruct_traces(
    log: OCEL | ComputationContext,
    spec: TraceSpec,
) -> ComputationResult[TraceSet]:
    """Compute one E2O trace per selected object, including isolated objects.

    Multiple qualifying E2O records produce one event occurrence with all matching
    relation evidence. Unknown object types and ambiguous selected-object ordering
    are unavailable; invalid OCEL is invalid_input. No partial success is returned.
    """

    if not isinstance(spec, TraceSpec):
        raise TypeError("spec must be TraceSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            TRACE_OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    traces, issues = _traces(context, spec)
    return _result(
        TRACE_OPERATOR_ID,
        context,
        spec,
        ComputeStatus.COMPUTED if traces is not None else ComputeStatus.UNAVAILABLE,
        traces,
        issues,
    )


__all__ = ("OPERATOR_VERSION", "TRACE_OPERATOR_ID", "reconstruct_traces")
