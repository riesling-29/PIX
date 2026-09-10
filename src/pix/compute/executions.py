"""Native execution extraction over explicit E2O participation policies.

Connectivity never depends on input row order, timestamp tie breaking, or
original O2O relations. The separate ordered graph carries temporal evidence
only for selected in-scope objects and reports unresolved ties explicitly.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict
from itertools import groupby

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.execution import (
    EntityMembership,
    EventOrderEdge,
    EventOrderTie,
    ExecutionEvent,
    ExecutionObject,
    ExecutionRelation,
    ExecutionSet,
    ExecutionSpec,
    ProcessExecution,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel.model import OCEL

OPERATOR_ID = "pix.discover_executions"


def _scope_id(
    context: ComputationContext,
    spec: ExecutionSpec,
    event_ids: set[str],
    object_ids: set[str],
    anchor: str | None,
) -> str:
    payload = {
        "version": "1.0.0",
        "source": context.source_digest,
        "spec": asdict(spec),
        "events": sorted(event_ids),
        "objects": sorted(object_ids),
        "anchor": anchor,
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return "pix.execution:sha256:" + hashlib.sha256(encoded).hexdigest()


def _component_scopes(
    context: ComputationContext,
    object_events: dict[str, set[str]],
) -> list[tuple[set[str], set[str], str | None]]:
    parents = {event.id: event.id for event in context.log.events}

    def root(event_id: str) -> str:
        while event_id != parents[event_id]:
            parents[event_id] = parents[parents[event_id]]
            event_id = parents[event_id]
        return event_id

    for event_ids in object_events.values():
        ordered = sorted(event_ids)
        if not ordered:
            continue
        first = root(ordered[0])
        for event_id in ordered[1:]:
            other = root(event_id)
            if first != other:
                low, high = sorted((first, other))
                parents[high] = low
                first = low

    event_groups: dict[str, set[str]] = defaultdict(set)
    object_groups: dict[str, set[str]] = defaultdict(set)
    for event_id in parents:
        event_groups[root(event_id)].add(event_id)
    for object_id, event_ids in object_events.items():
        if event_ids:
            object_groups[root(min(event_ids))].add(object_id)
    return [
        (event_groups[group], object_groups[group], None)
        for group in sorted(event_groups)
    ]


def _leading_scopes(
    context: ComputationContext,
    spec: ExecutionSpec,
    selected_objects: set[str],
    object_events: dict[str, set[str]],
    event_objects: dict[str, set[str]],
) -> list[tuple[set[str], set[str], str | None]]:
    object_types = context.objects_by_id
    type_count = len({object_types[item].type for item in selected_objects})
    scopes = []
    for anchor in sorted(selected_objects):
        if object_types[anchor].type != spec.leading_object_type:
            continue
        admitted = {anchor}
        type_depth = {spec.leading_object_type: 0}
        frontier = {anchor}
        for depth in range(1, type_count):
            candidates: set[str] = set()
            for object_id in frontier:
                for event_id in object_events[object_id]:
                    candidates.update(event_objects[event_id])
            next_frontier: set[str] = set()
            for object_id in sorted(candidates):
                object_type = object_types[object_id].type
                if object_type not in type_depth:
                    type_depth[object_type] = depth
                if type_depth[object_type] == depth:
                    next_frontier.add(object_id)
            admitted.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        events = set().union(*(object_events[item] for item in admitted))
        scopes.append((events, admitted, anchor))
    return scopes


def _order_evidence(
    context: ComputationContext,
    spec: ExecutionSpec,
    object_events: dict[str, set[str]],
) -> tuple[dict[str, tuple[EventOrderEdge, ...]], dict[str, tuple[EventOrderTie, ...]]]:
    all_edges = {}
    all_ties = {}
    for object_id, event_ids in sorted(object_events.items()):
        ordered = sorted(
            event_ids, key=lambda item: (context.events_by_id[item].time, item)
        )
        ties = []
        for time, group in groupby(
            ordered, key=lambda item: context.events_by_id[item].time
        ):
            same_time = tuple(group)
            if len(same_time) > 1:
                ties.append(EventOrderTie(object_id, same_time, time))
        all_ties[object_id] = tuple(ties)
        if ties and spec.tie_policy == "reject":
            all_edges[object_id] = ()
        else:
            all_edges[object_id] = tuple(
                EventOrderEdge(
                    source,
                    target,
                    object_id,
                    context.events_by_id[source].time
                    == context.events_by_id[target].time,
                )
                for source, target in zip(ordered, ordered[1:])
            )
    return all_edges, all_ties


def discover_executions(
    log: OCEL | ComputationContext,
    spec: ExecutionSpec,
) -> ComputationResult[ExecutionSet]:
    """Extract complete memberships while retaining isolates and boundaries.

    Success means extraction completed. Consumers requiring an ordered graph
    must additionally inspect each execution's ``order_status``. An ambiguous
    graph never silently becomes an empty but complete graph.
    """
    if not isinstance(spec, ExecutionSpec):
        raise TypeError("spec must be ExecutionSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    known_types = {item.name for item in context.log.object_types}
    requested_types = (
        known_types if spec.object_types is None else set(spec.object_types)
    )
    missing_types = requested_types - known_types
    if (
        spec.leading_object_type is not None
        and spec.leading_object_type not in known_types
    ):
        missing_types.add(spec.leading_object_type)
    if missing_types:
        return _result(
            OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("unknown_object_type", ", ".join(sorted(missing_types))),),
        )

    selected_objects = {
        item.id for item in context.log.objects if item.type in requested_types
    }
    selected_relations = {
        ExecutionRelation(item.event, item.object, item.qualifier)
        for item in context.log.e2o
        if item.object in selected_objects
        and (spec.qualifiers is None or item.qualifier in spec.qualifiers)
    }
    object_events: dict[str, set[str]] = {item: set() for item in selected_objects}
    event_objects: dict[str, set[str]] = {item.id: set() for item in context.log.events}
    for relation in selected_relations:
        object_events[relation.object].add(relation.event)
        event_objects[relation.event].add(relation.object)

    if spec.method == "connected_components":
        scopes = _component_scopes(context, object_events)
    else:
        scopes = _leading_scopes(
            context, spec, selected_objects, object_events, event_objects
        )
    all_edges, all_ties = _order_evidence(context, spec, object_events)
    executions = []
    event_memberships: dict[str, list[str]] = {
        item.id: [] for item in context.log.events
    }
    object_memberships: dict[str, list[str]] = {
        item.id: [] for item in context.log.objects
    }
    used_tie_objects = set()
    for event_ids, object_ids, anchor in scopes:
        execution_id = _scope_id(context, spec, event_ids, object_ids, anchor)
        raw_relations = {
            ExecutionRelation(item.event, item.object, item.qualifier)
            for event_id in event_ids
            for item in context.e2o_by_event.get(event_id, ())
        }
        boundary_ids = {item.object for item in raw_relations} - object_ids
        ties = tuple(tie for item in sorted(object_ids) for tie in all_ties[item])
        edges = tuple(sorted(edge for item in object_ids for edge in all_edges[item]))
        unavailable = bool(ties) and spec.tie_policy == "reject"
        if unavailable:
            used_tie_objects.update(tie.object_id for tie in ties)
        executions.append(
            ProcessExecution(
                execution_id=execution_id,
                leading_object_id=anchor,
                events=tuple(
                    ExecutionEvent(
                        item,
                        context.events_by_id[item].type,
                        context.events_by_id[item].time,
                    )
                    for item in sorted(event_ids)
                ),
                objects=tuple(
                    ExecutionObject(item, context.objects_by_id[item].type)
                    for item in sorted(object_ids)
                ),
                boundary_objects=tuple(
                    ExecutionObject(item, context.objects_by_id[item].type)
                    for item in sorted(boundary_ids)
                ),
                relations=tuple(sorted(raw_relations & selected_relations)),
                excluded_relations=tuple(sorted(raw_relations - selected_relations)),
                order_edges=edges,
                order_status="unavailable" if unavailable else "complete",
                order_ties=ties,
            )
        )
        for event_id in event_ids:
            event_memberships[event_id].append(execution_id)
        for object_id in object_ids:
            object_memberships[object_id].append(execution_id)

    result_value = ExecutionSet(
        executions=tuple(sorted(executions, key=lambda item: item.execution_id)),
        event_memberships=tuple(
            EntityMembership(item, tuple(sorted(members)))
            for item, members in sorted(event_memberships.items())
        ),
        object_memberships=tuple(
            EntityMembership(item, tuple(sorted(members)))
            for item, members in sorted(object_memberships.items())
        ),
        unassigned_event_ids=tuple(
            sorted(item for item, members in event_memberships.items() if not members)
        ),
        unassigned_object_ids=tuple(
            sorted(item for item, members in object_memberships.items() if not members)
        ),
        isolated_event_ids=tuple(
            sorted(item for item, members in event_objects.items() if not members)
        ),
        isolated_object_ids=tuple(
            sorted(item for item, members in object_events.items() if not members)
        ),
        excluded_object_ids=tuple(sorted(set(object_memberships) - selected_objects)),
        overlapping_event_ids=tuple(
            sorted(
                item for item, members in event_memberships.items() if len(members) > 1
            )
        ),
        overlapping_object_ids=tuple(
            sorted(
                item for item, members in object_memberships.items() if len(members) > 1
            )
        ),
        unique_event_count=sum(bool(members) for members in event_memberships.values()),
        event_membership_count=sum(map(len, event_memberships.values())),
        unique_object_count=sum(
            bool(members) for members in object_memberships.values()
        ),
        object_membership_count=sum(map(len, object_memberships.values())),
    )
    order_issues = tuple(
        ComputeIssue(
            "ambiguous_event_order",
            "Extraction completed, but equal timestamps leave an object's ordered graph unavailable.",
            ("objects", item),
        )
        for item in sorted(used_tie_objects)
    )
    return _result(
        OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, result_value, order_issues
    )
