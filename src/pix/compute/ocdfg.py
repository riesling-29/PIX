"""Object-centred directly-follows graphs with explicit counting units.

The graph contains one layer per selected object type. Layers keep their own
activity boundaries and isolated objects; a shared event does not merge layers.
Every edge retains the object/event occurrences from which all counts derive.
"""

from __future__ import annotations

from pix.contracts.analysis import (
    ObjectCentricDFG,
    OCDFGEdge,
    OCDFGSpec,
    OCDFGTypeGraph,
    TraceSpec,
)
from pix.contracts.result import ComputationResult, ComputeStatus
from pix.ocel import OCEL

from ._common import _prepare, _result
from .context import ComputationContext
from .dfg import discover_dfg

OCDFG_OPERATOR_ID = "pix.discover_ocdfg"

__all__ = ("OCDFG_OPERATOR_ID", "discover_ocdfg")


def discover_ocdfg(
    log: OCEL | ComputationContext,
    spec: OCDFGSpec,
) -> ComputationResult[ObjectCentricDFG]:
    """Discover per-type graphs without collapsing event, object, and occurrence counts.

    One event pair can be shared by several objects. One object can also traverse
    the same activity pair repeatedly. ``event_pair_count``,
    ``unique_object_count`` and ``occurrence_count`` consequently answer different
    questions. Qualified E2O records provide evidence but do not multiply an
    object's event occurrences. O2O relationships do not create directly-follows
    edges. A selected unknown type or ambiguous order fails the entire request.
    """

    if not isinstance(spec, OCDFGSpec):
        raise TypeError("spec must be OCDFGSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OCDFG_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )

    results = tuple(
        discover_dfg(
            context,
            TraceSpec(object_type, spec.qualifiers, spec.tie_policy),
        )
        for object_type in spec.object_types
    )
    parent_ids = tuple(
        result.computation_id for result in results if result.computation_id is not None
    )
    failed_issues = tuple(
        issue
        for result in results
        if result.status is not ComputeStatus.COMPUTED
        for issue in result.issues
    )
    if failed_issues:
        return _result(
            OCDFG_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            failed_issues,
            parent_computation_ids=parent_ids,
        )

    layers: list[OCDFGTypeGraph] = []
    for result in results:
        graph = result.value
        assert graph is not None
        edges = tuple(
            OCDFGEdge(
                object_type=graph.object_type,
                source_activity=edge.source_activity,
                target_activity=edge.target_activity,
                event_pair_count=len(
                    {
                        (item.source_event_id, item.target_event_id)
                        for item in edge.evidence
                    }
                ),
                unique_object_count=len({item.object_id for item in edge.evidence}),
                occurrence_count=len(edge.evidence),
                evidence=edge.evidence,
            )
            for edge in graph.edges
        )
        layers.append(
            OCDFGTypeGraph(
                object_type=graph.object_type,
                object_count=graph.object_count,
                empty_object_ids=graph.empty_object_ids,
                activities=graph.activities,
                edges=edges,
                starts=graph.starts,
                ends=graph.ends,
            )
        )

    return _result(
        OCDFG_OPERATOR_ID,
        context,
        spec,
        ComputeStatus.COMPUTED,
        ObjectCentricDFG(tuple(layers)),
        parent_computation_ids=parent_ids,
    )
