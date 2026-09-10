"""Adapt native discovery results without recomputing or filtering their meaning."""

from __future__ import annotations

import hashlib
import json

from pix.contracts.analysis import (
    DirectlyFollowsGraph,
    ObjectCentricDFG,
)
from pix.contracts.graph import (
    GraphCounts,
    GraphDocument,
    GraphEdge,
    GraphEvidence,
    GraphNode,
)
from pix.contracts.result import ComputationResult, ComputeStatus


def _identity(kind: str, *parts: str) -> str:
    value = json.dumps([kind, *parts], ensure_ascii=False, separators=(",", ":"))
    return kind + "-" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_graph(
    result: ComputationResult, *, title: str = "PIX process graph"
) -> GraphDocument:
    """Build a renderer-neutral graph from a successful native DFG/OCDFG result.

    Activity identity in these discovery contracts is the OCEL event type.
    This adapter does not merge transitions in normative process models.
    """
    if not isinstance(result, ComputationResult):
        raise TypeError("result must be ComputationResult")
    if result.status != ComputeStatus.COMPUTED or result.value is None:
        raise ValueError("only successfully computed results can be visualized")
    value = result.value
    if isinstance(value, DirectlyFollowsGraph):
        kind = "dfg"
        graphs = (value,)
    elif isinstance(value, ObjectCentricDFG):
        kind = "ocdfg"
        graphs = value.graphs
    else:
        raise TypeError("viewer supports DFG and OCDFG results")
    if not result.source_digest or not result.computation_id:
        raise ValueError("result must retain source and computation identifiers")
    events: dict[str, set[str]] = {}
    objects: dict[str, set[str]] = {}
    edges: list[GraphEdge] = []
    empty_objects: set[str] = set()
    for graph in graphs:
        empty_objects.update(graph.empty_object_ids)
        for activity in graph.activities:
            events.setdefault(activity.activity, set()).update(
                activity.distinct_event_ids
            )
            objects.setdefault(activity.activity, set()).update(activity.object_ids)
        for edge in graph.edges:
            evidence = tuple(
                GraphEvidence(
                    item.source_event_id,
                    item.target_event_id,
                    item.object_id,
                    tuple(sorted({rel.qualifier for rel in item.source_relations})),
                    tuple(sorted({rel.qualifier for rel in item.target_relations})),
                )
                for item in edge.evidence
            )
            counts = GraphCounts(
                len(
                    {(item.source_event_id, item.target_event_id) for item in evidence}
                ),
                len({item.object_id for item in evidence}),
                edge.occurrence_count,
            )
            # OCDFG's explicit units must agree with its source evidence.
            if kind == "ocdfg" and (
                counts.event_pairs != edge.event_pair_count
                or counts.unique_objects != edge.unique_object_count
            ):
                raise ValueError("computed edge counts disagree with their evidence")
            edges.append(
                GraphEdge(
                    id=_identity(
                        "edge",
                        graph.object_type,
                        edge.source_activity,
                        edge.target_activity,
                    ),
                    source=_identity("activity", edge.source_activity),
                    target=_identity("activity", edge.target_activity),
                    object_type=graph.object_type,
                    counts=counts,
                    evidence=evidence,
                )
            )
    notes = [
        f"Calculation: {result.operator_id} (version {result.operator_version}).",
        "Directly-follows relations describe the selected analysis; they do not "
        "establish causality or normative permission.",
        "Object-type filters hide view edges only. Node totals and analysis "
        "evidence remain unchanged.",
    ]
    notes.append(
        "Trace order uses event timestamps; equal-time policy: "
        f"{result.spec.tie_policy}. An event-ID tie break is a convention, "
        "not evidence of causal order."
    )
    notes.append(
        "E2O qualifier selection: "
        + (
            "all qualifiers"
            if result.spec.qualifiers is None
            else json.dumps(result.spec.qualifiers, ensure_ascii=False)
        )
        + "."
    )
    if empty_objects:
        notes.append(
            f"{len(empty_objects)} objects have no event in the selected traces; "
            "they do not appear as activity nodes."
        )
    return GraphDocument(
        kind=kind,
        source_digest=result.source_digest,
        computation_id=result.computation_id,
        nodes=tuple(
            GraphNode(
                _identity("activity", activity),
                activity,
                tuple(sorted(events[activity])),
                tuple(sorted(objects[activity])),
            )
            for activity in sorted(events)
        ),
        edges=tuple(sorted(edges, key=lambda edge: edge.id)),
        object_types=tuple(sorted(graph.object_type for graph in graphs)),
        title=title,
        notes=tuple(notes),
    )


__all__ = ("build_graph",)
