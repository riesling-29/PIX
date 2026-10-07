"""Object-instance chevrons over supplied execution and variant evidence.

The coordinate rule follows the OCPA chevron view: start is longest-path depth;
inclusive end is the earliest successor start minus one, or start at a sink.
These are precedence positions, never observed durations. Variant discovery is
not repeated and canonical signatures are not treated as proofs of equivalence.
"""

from __future__ import annotations

import heapq
import json
from dataclasses import replace

from pix.compute.variants import _execution_graph
from pix.contracts.execution import (
    ExecutionSet,
    ExecutionSpec,
    ProcessExecution,
    VariantSet,
)
from pix.contracts.result import ComputationResult, ComputeStatus
from pix.results import result_document

from .visual_contracts import (
    ChevronEvent,
    ChevronLane,
    ChevronPanel,
    TablePanel,
    VisualField,
    VisualizationDocument,
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _layout(execution: ProcessExecution) -> tuple[dict[str, int], dict[str, int]]:
    if type(execution) is not ProcessExecution:
        raise TypeError("execution must be ProcessExecution")
    if execution.order_status != "complete":
        raise ValueError(
            "chevrons require a complete order; unresolved ties are not ordered"
        )
    # This checks incidence/path closure only; it does not canonicalize or discover.
    _execution_graph(execution)
    events = {event.id: event for event in execution.events}
    scoped = {obj.id for obj in execution.objects}
    objects = scoped | {obj.id for obj in execution.boundary_objects}
    selected = set(execution.relations)
    excluded = set(execution.excluded_relations)
    if len(excluded) != len(execution.excluded_relations) or selected & excluded:
        raise ValueError(
            "selected and excluded relations must be distinct and disjoint"
        )
    if any(row.event not in events or row.object not in objects for row in excluded):
        raise ValueError("excluded E2O evidence references missing execution entities")

    expected_ties: dict[tuple[str, object], set[str]] = {}
    for row in execution.relations:
        if row.object in scoped:
            expected_ties.setdefault((row.object, events[row.event].time), set()).add(
                row.event
            )
    expected_ties = {key: ids for key, ids in expected_ties.items() if len(ids) > 1}
    recorded_ties = {}
    for tie in execution.order_ties:
        key = (tie.object_id, tie.time)
        if key in recorded_ties:
            raise ValueError("duplicate order tie evidence")
        recorded_ties[key] = set(tie.event_ids)
    if recorded_ties != expected_ties:
        raise ValueError("order tie evidence must match scoped equal-time event groups")

    successors: dict[str, set[str]] = {event_id: set() for event_id in events}
    indegree = dict.fromkeys(events, 0)
    for edge in execution.order_edges:
        before, after = events[edge.source_event], events[edge.target_event]
        if before.time > after.time:
            raise ValueError("event order contradicts observed timestamps")
        if edge.tie_broken != (before.time == after.time):
            raise ValueError("equal-time order requires explicit tie_broken evidence")
        if edge.target_event not in successors[edge.source_event]:
            successors[edge.source_event].add(edge.target_event)
            indegree[edge.target_event] += 1
    frontier = [event_id for event_id, degree in indegree.items() if degree == 0]
    heapq.heapify(frontier)
    starts = dict.fromkeys(events, 0)
    visited = 0
    while frontier:
        source = heapq.heappop(frontier)
        visited += 1
        for target in sorted(successors[source]):
            starts[target] = max(starts[target], starts[source] + 1)
            indegree[target] -= 1
            if indegree[target] == 0:
                heapq.heappush(frontier, target)
    if visited != len(events):
        raise ValueError("chevron event-order graph must be acyclic")
    ends = {
        event_id: min(starts[other] for other in following) - 1
        if following
        else starts[event_id]
        for event_id, following in successors.items()
    }
    return starts, ends


def _panel(
    execution: ProcessExecution,
    *,
    title: str | None,
    panel_id: str | None,
    allow_unlaned: bool,
) -> ChevronPanel:
    starts, ends = _layout(execution)
    scoped = {obj.id for obj in execution.objects}
    participants: dict[str, set[str]] = {event.id: set() for event in execution.events}
    qualified: dict[str, list[tuple[str, str]]] = {
        event.id: [] for event in execution.events
    }
    for row in execution.relations:
        qualified[row.event].append((row.object, row.qualifier))
        if row.object in scoped:
            participants[row.event].add(row.object)
    unlaned = tuple(sorted(event for event, ids in participants.items() if not ids))
    if unlaned and not allow_unlaned:
        raise ValueError(
            "events without an in-scope object require the variant document evidence table: "
            + _json(unlaned)
        )
    lanes = tuple(
        ChevronLane(
            obj.id,
            f"{obj.type}: {obj.id}",
            obj.type,
            obj.id,
            (VisualField("leading_object", obj.id == execution.leading_object_id),),
        )
        for obj in sorted(execution.objects, key=lambda obj: (obj.type, obj.id))
    )
    lane_rank = {lane.id: index for index, lane in enumerate(lanes)}
    description = (
        "One lane per in-scope object instance. Shared events retain one ID and identical "
        "positions across participating lanes. Start is longest-path depth; inclusive end "
        "is the earliest successor start minus one (sink: start). Positions are precedence "
        "layers, not durations; equal positions do not prove concurrency. Boundary "
        "objects and excluded qualifiers are evidence, "
        "not additional lanes."
    )
    if execution.order_ties:
        description += " Equal-time order includes explicitly recorded tie breaking."
    if unlaned:
        description += f" {len(unlaned)} events have no in-scope lane; see the unlaned-event evidence table."
    return ChevronPanel(
        panel_id
        if panel_id is not None
        else f"execution/{execution.execution_id}/chevrons",
        title if title is not None else f"Execution {execution.execution_id}",
        lanes,
        tuple(
            ChevronEvent(
                event.id,
                event.activity,
                starts[event.id],
                ends[event.id],
                tuple(sorted(participants[event.id], key=lane_rank.__getitem__)),
                (
                    VisualField("execution_id", execution.execution_id),
                    VisualField("observed_timestamp", event.time.isoformat()),
                    VisualField("coordinate_unit", "precedence layers (inclusive)"),
                    VisualField(
                        "qualified_incidence",
                        _json(qualified[event.id]),
                    ),
                ),
            )
            for event in sorted(
                execution.events, key=lambda event: (starts[event.id], event.id)
            )
            if participants[event.id]
        ),
        description=description,
    )


def build_execution_chevrons(
    execution: ProcessExecution,
    *,
    title: str | None = None,
    panel_id: str | None = None,
) -> ChevronPanel:
    """Lay out a supplied complete execution; never infer missing order or variants.

    Objectless or boundary-only events require ``build_variant_visualization`` so
    their explicit evidence table accompanies the graph. No events are dropped
    silently by this single-panel helper.
    """
    return _panel(execution, title=title, panel_id=panel_id, allow_unlaned=False)


def _membership_integrity(value: ExecutionSet) -> None:
    for kind in ("event", "object"):
        expected: dict[str, set[str]] = {}
        for execution in value.executions:
            for entity in getattr(execution, f"{kind}s"):
                expected.setdefault(entity.id, set()).add(execution.execution_id)
        rows = getattr(value, f"{kind}_memberships")
        if len({row.entity_id for row in rows}) != len(rows):
            raise ValueError(f"duplicate {kind} membership entities")
        recorded = {row.entity_id: set(row.execution_ids) for row in rows}
        if {key: ids for key, ids in recorded.items() if ids} != expected:
            raise ValueError(f"{kind} memberships disagree with execution entities")
        if set(getattr(value, f"unassigned_{kind}_ids")) != {
            key for key, ids in recorded.items() if not ids
        }:
            raise ValueError(f"unassigned {kind} IDs disagree with memberships")
        if getattr(value, f"unique_{kind}_count") != len(expected) or getattr(
            value, f"{kind}_membership_count"
        ) != sum(map(len, expected.values())):
            raise ValueError(f"{kind} membership counts disagree with executions")
        if set(getattr(value, f"overlapping_{kind}_ids")) != {
            key for key, ids in expected.items() if len(ids) > 1
        }:
            raise ValueError(f"overlapping {kind} IDs disagree with memberships")


def _selection_integrity(execution: ProcessExecution, spec: ExecutionSpec) -> None:
    objects = {obj.id: obj for obj in (*execution.objects, *execution.boundary_objects)}

    def selected(row) -> bool:
        return (
            spec.object_types is None or objects[row.object].type in spec.object_types
        ) and (spec.qualifiers is None or row.qualifier in spec.qualifiers)

    if any(not selected(row) for row in execution.relations):
        raise ValueError(
            "selected incidence contradicts extraction type/qualifier selection"
        )
    if any(selected(row) for row in execution.excluded_relations):
        raise ValueError(
            "excluded incidence contradicts extraction type/qualifier selection"
        )
    if spec.object_types is not None and any(
        obj.type not in spec.object_types for obj in execution.objects
    ):
        raise ValueError("in-scope object type contradicts extraction selection")
    if spec.method == "connected_components":
        if execution.leading_object_id is not None:
            raise ValueError(
                "connected-components execution cannot declare a leading object"
            )
    elif (
        execution.leading_object_id is None
        or objects[execution.leading_object_id].type != spec.leading_object_type
    ):
        raise ValueError("leading object must match the extraction leading type")


def build_variant_visualization(
    execution_result: ComputationResult[ExecutionSet],
    variant_result: ComputationResult[VariantSet],
    *,
    title: str | None = None,
) -> VisualizationDocument:
    """Show recorded exact variants with their matching execution parent.

    Validates request identities, parent/source binding, complete member coverage
    and execution evidence. It does not rerun canonical labeling or certify a
    manually altered grouping; request hashes are not signatures of the values.
    """
    for result, operator, kind in (
        (execution_result, "pix.discover_executions", ExecutionSet),
        (variant_result, "pix.discover_variants", VariantSet),
    ):
        if type(result) is not ComputationResult:
            raise TypeError(
                "variant visualization requires original ComputationResult envelopes"
            )
        result_document(result)
        if result.operator_id != operator or type(result.value) is not kind:
            raise ValueError(f"expected a complete {operator} result")
        if result.status is not ComputeStatus.COMPUTED:
            raise ValueError(
                "variant chevrons require computed, complete input results"
            )
    if execution_result.source_digest != variant_result.source_digest:
        raise ValueError("variant and execution source identities differ")
    if variant_result.parent_computation_ids != (execution_result.computation_id,):
        raise ValueError(
            "variant result must name exactly the supplied execution parent"
        )
    executions, variants = execution_result.value, variant_result.value
    execution_map = {
        execution.execution_id: execution for execution in executions.executions
    }
    if len(execution_map) != len(executions.executions):
        raise ValueError("execution IDs must be unique")
    _membership_integrity(executions)
    for execution in executions.executions:
        _layout(execution)
        _selection_integrity(execution, execution_result.spec)
        if execution.order_ties and execution_result.spec.tie_policy == "reject":
            raise ValueError("complete tied order contradicts the reject tie policy")
        if any(
            edge.tie_broken and edge.source_event >= edge.target_event
            for edge in execution.order_edges
        ):
            raise ValueError("tie-broken order contradicts the event_id tie policy")
    if variants.execution_count != len(execution_map):
        raise ValueError("variant population differs from execution count")
    if len({variant.variant_id for variant in variants.variants}) != len(
        variants.variants
    ):
        raise ValueError("variant IDs must be unique")
    members = [
        member for variant in variants.variants for member in variant.execution_ids
    ]
    if len(members) != len(set(members)) or set(members) != set(execution_map):
        raise ValueError(
            "variant memberships must partition the supplied executions exactly"
        )

    panels: list = [
        TablePanel(
            "variant-frequencies",
            "Recorded exact variant frequencies",
            (
                "variant",
                "representative execution",
                "frequency",
                "execution population",
                "member executions",
                "canonical signature",
            ),
            tuple(
                (
                    variant.variant_id,
                    variant.representative_execution_id,
                    variant.frequency,
                    variants.execution_count,
                    _json(variant.execution_ids),
                    variant.canonical_signature,
                )
                for variant in variants.variants
            ),
            description="Frequency counts execution memberships, not distinct global events or objects. Existing exact incidence grouping is displayed without rediscovery.",
        )
    ]
    evidence = []
    unlaned_rows = []
    boundary_rows = []
    order_rows = []
    for index, variant in enumerate(variants.variants):
        if variant.representative_execution_id not in execution_map:
            raise ValueError(
                "variant representative is missing from the execution parent"
            )
        execution = execution_map[variant.representative_execution_id]
        panel = _panel(
            execution,
            title=f"Variant {index + 1} — {variant.frequency}/{variants.execution_count} executions",
            panel_id=f"variant-{index + 1}/chevrons",
            allow_unlaned=True,
        )
        panels.append(
            replace(
                panel,
                variant_id=variant.variant_id,
                frequency=variant.frequency,
                population=variants.execution_count,
            )
        )
        scoped = {obj.id for obj in execution.objects}
        object_map = {
            obj.id: obj for obj in (*execution.objects, *execution.boundary_objects)
        }
        for selection, relations in (
            ("selected", execution.relations),
            ("excluded", execution.excluded_relations),
        ):
            evidence.extend(
                (
                    variant.variant_id,
                    execution.execution_id,
                    row.event,
                    row.object,
                    object_map[row.object].type,
                    row.qualifier,
                    "in-scope" if row.object in scoped else "boundary",
                    selection,
                )
                for row in relations
            )
        boundary_rows.extend(
            (variant.variant_id, execution.execution_id, obj.id, obj.type)
            for obj in execution.boundary_objects
        )
        laned = {event.id for event in panel.events}
        unlaned_rows.extend(
            (
                variant.variant_id,
                execution.execution_id,
                event.id,
                event.activity,
                event.time.isoformat(),
                "No selected in-scope object participation",
            )
            for event in execution.events
            if event.id not in laned
        )
        order_rows.extend(
            (
                variant.variant_id,
                execution.execution_id,
                edge.source_event,
                edge.target_event,
                edge.object_id,
                edge.tie_broken,
            )
            for edge in execution.order_edges
        )
    panels.extend(
        (
            TablePanel(
                "variant-incidence-evidence",
                "Representative qualified incidence",
                (
                    "variant",
                    "execution",
                    "event",
                    "object",
                    "object type",
                    "qualifier",
                    "scope",
                    "selection",
                ),
                tuple(evidence),
            ),
            TablePanel(
                "variant-boundary-objects",
                "Representative boundary objects",
                ("variant", "execution", "object", "object type"),
                tuple(boundary_rows),
                description="Retained as evidence; only in-scope objects receive chevron lanes.",
            ),
            TablePanel(
                "variant-order-evidence",
                "Representative supplied order",
                (
                    "variant",
                    "execution",
                    "source event",
                    "target event",
                    "object",
                    "tie broken",
                ),
                tuple(order_rows),
            ),
            TablePanel(
                "variant-unlaned-events",
                "Events without an in-scope lane",
                (
                    "variant",
                    "execution",
                    "event",
                    "activity",
                    "observed timestamp",
                    "reason",
                ),
                tuple(unlaned_rows),
                description="Objectless and boundary-only events remain explicit instead of being silently omitted.",
            ),
        )
    )
    from .visualization import _comparison_document

    return _comparison_document(
        tuple(panels),
        (execution_result, variant_result),
        "Object-centric variant chevrons" if title is None else title,
    )


__all__ = ("build_execution_chevrons", "build_variant_visualization")
