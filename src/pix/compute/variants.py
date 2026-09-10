"""Exact variants of finite, labelled event-object incidence structures.

The equivalence deliberately excludes raw identifiers, absolute timestamps and
attributes. It preserves activities, object types, scope and leading roles,
qualified incidence and the chosen object-specific event order. O2O, excluded
relations and annotations about how a temporal tie was broken are excluded.
Colour refinement only reduces the search space; complete canonical labelings
establish equivalence. An exhausted bound never produces partial exact groups.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass

from pix.compute._common import _result
from pix.contracts.execution import (
    EventOrderEdge,
    ExecutionEvent,
    ExecutionObject,
    ExecutionRelation,
    ExecutionSet,
    ExecutionVariant,
    ProcessExecution,
    VariantSet,
    VariantSpec,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

VARIANT_OPERATOR_ID = "pix.discover_variants"


def discover_variants(
    execution_result: ComputationResult[ExecutionSet], spec: VariantSpec
) -> ComputationResult[VariantSet]:
    """Group complete execution graphs under exact, consistent renaming.

    A failed parent, ambiguous order, malformed graph or exceeded search budget
    produces no variant payload. Each successful group retains the original
    execution IDs, with a deterministic representative. A signature is a
    cross-dataset candidate fingerprint; exact grouping compares the complete
    canonical encoding. Artifact identity also includes source provenance, the
    parent extraction computation and this computation's specification.
    Source-validation failures retain ``invalid_input``. A partial extraction
    cannot establish exact groups and therefore yields ``unavailable``, with
    the upstream status and original diagnostics preserved.
    """
    if not isinstance(spec, VariantSpec):
        raise TypeError("spec must be VariantSpec")
    if not isinstance(execution_result, ComputationResult):
        raise TypeError("execution_result must be ComputationResult")
    source = execution_result.source_digest
    parents = (
        (execution_result.computation_id,)
        if execution_result.computation_id is not None
        else ()
    )

    def result(status, value=None, issues=()):
        return _result(
            VARIANT_OPERATOR_ID,
            None,
            spec,
            status,
            value,
            issues + execution_result.issues,
            parent_computation_ids=parents,
            source_digest=source,
        )

    if execution_result.status is not ComputeStatus.COMPUTED:
        return result(
            ComputeStatus.INVALID_INPUT
            if execution_result.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "parent_not_complete",
                    "Exact variants require a complete extraction; parent status is "
                    f"{execution_result.status.value}.",
                ),
            ),
        )
    if not isinstance(execution_result.value, ExecutionSet):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_execution_result", "The parent value must be ExecutionSet."
                ),
            ),
        )
    if not parents or source is None:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "missing_provenance",
                    "The source digest and parent computation ID are required.",
                ),
            ),
        )

    executions = execution_result.value.executions
    if not isinstance(executions, tuple) or not all(
        isinstance(item, ProcessExecution) for item in executions
    ):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_execution_result",
                    "Executions must be a tuple of ProcessExecution.",
                ),
            ),
        )
    unavailable = tuple(
        execution.execution_id
        for execution in executions
        if execution.order_status != "complete"
    )
    if unavailable:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "order_unavailable",
                    "Every execution needs a complete selected order.",
                    at=unavailable,
                ),
            ),
        )

    forms: dict[str, list[str]] = {}
    states = 0
    seen: set[str] = set()
    for execution in sorted(executions, key=lambda item: item.execution_id):
        try:
            _text(execution.execution_id)
            if execution.execution_id in seen:
                raise ValueError("Execution IDs must be unique.")
            seen.add(execution.execution_id)
            graph = _execution_graph(execution)
            form, cost = _canonical_form(graph, spec.max_search_states - states)
        except (ValueError, TypeError) as error:
            return result(
                ComputeStatus.INVALID_INPUT,
                issues=(
                    ComputeIssue(
                        "invalid_execution_graph",
                        str(error),
                        at=(execution.execution_id,),
                    ),
                ),
            )
        except _SearchLimit:
            return result(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "limit_exceeded",
                        "Exact canonical labeling exceeds max_search_states; no partial "
                        "variant groups are returned.",
                        at=(execution.execution_id,),
                    ),
                ),
            )
        states += cost
        forms.setdefault(form, []).append(execution.execution_id)

    variants: list[ExecutionVariant] = []
    for form, execution_ids in sorted(forms.items()):
        signature = "sha256:" + _digest(form)
        artifact = json.dumps(
            (
                VARIANT_OPERATOR_ID,
                "1.0.0",
                source,
                parents,
                spec.SCHEMA_VERSION,
                spec.equivalence,
                spec.max_search_states,
                form,
            ),
            ensure_ascii=False,
            separators=(",", ":"),
        )
        variants.append(
            ExecutionVariant(
                variant_id="pix:variant:sha256:" + _digest(artifact),
                canonical_signature=signature,
                execution_ids=tuple(execution_ids),
                representative_execution_id=execution_ids[0],
                frequency=len(execution_ids),
            )
        )
    return result(
        ComputeStatus.COMPUTED,
        VariantSet(
            variants=tuple(variants),
            execution_count=len(executions),
            search_states=states,
            equivalence=spec.equivalence,
            exact=True,
        ),
    )


def _text(value: object, *, empty: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError("Graph identifiers and labels must be strings.")
    if not empty and not value.strip():
        raise ValueError("Graph identifiers and labels must not be blank.")
    value.encode("utf-8")


def _execution_graph(execution: ProcessExecution) -> _Graph:
    collections = (
        (execution.events, ExecutionEvent),
        (execution.objects, ExecutionObject),
        (execution.boundary_objects, ExecutionObject),
        (execution.relations, ExecutionRelation),
        (execution.order_edges, EventOrderEdge),
    )
    for values, kind in collections:
        if not isinstance(values, tuple) or not all(
            isinstance(v, kind) for v in values
        ):
            raise TypeError(f"Graph records must be tuples of {kind.__name__}.")
    event_map: dict[str, int] = {}
    object_map: dict[str, int] = {}
    labels: list[tuple[str, ...]] = []
    for event in execution.events:
        _text(event.id)
        _text(event.activity)
        if event.id in event_map:
            raise ValueError("Event IDs must be unique within each execution.")
        event_map[event.id] = len(labels)
        labels.append(("event", event.activity))

    active_objects = {relation.object for relation in execution.relations}
    all_object_ids: set[str] = set()
    scope_ids = {obj.id for obj in execution.objects}
    if execution.leading_object_id is not None:
        _text(execution.leading_object_id)
        if execution.leading_object_id not in scope_ids:
            raise ValueError("The leading object must belong to the execution scope.")
    for objects, scope in (
        (execution.objects, "inside"),
        (execution.boundary_objects, "boundary"),
    ):
        for obj in objects:
            _text(obj.id)
            _text(obj.type)
            if obj.id in all_object_ids:
                raise ValueError("Inside and boundary objects must have distinct IDs.")
            all_object_ids.add(obj.id)
            if scope == "boundary" and obj.id not in active_objects:
                continue
            object_map[obj.id] = len(labels)
            labels.append(
                (
                    "object",
                    obj.type,
                    scope,
                    "leading" if obj.id == execution.leading_object_id else "ordinary",
                )
            )

    relations: list[tuple[str, str, tuple[int, ...]]] = []
    incidences: set[tuple[str, str]] = set()
    distinct_relations: set[ExecutionRelation] = set()
    for relation in execution.relations:
        _text(relation.event)
        _text(relation.object)
        _text(relation.qualifier, empty=True)
        if relation.event not in event_map or relation.object not in object_map:
            raise ValueError("E2O relation references a missing event or object.")
        if relation in distinct_relations:
            raise ValueError("Duplicate qualified E2O relations are not allowed.")
        distinct_relations.add(relation)
        incidences.add((relation.event, relation.object))
        relations.append(
            (
                "e2o",
                relation.qualifier,
                (
                    event_map[relation.event],
                    object_map[relation.object],
                ),
            )
        )

    distinct_orders: set[tuple[str, str, str]] = set()
    for edge in execution.order_edges:
        triple = (edge.source_event, edge.target_event, edge.object_id)
        if (
            edge.source_event not in event_map
            or edge.target_event not in event_map
            or edge.object_id not in scope_ids
        ):
            raise ValueError("Event-order edge references an out-of-scope endpoint.")
        if (
            edge.source_event == edge.target_event
            or (edge.source_event, edge.object_id) not in incidences
            or (edge.target_event, edge.object_id) not in incidences
        ):
            raise ValueError("Event-order edge requires two incident, distinct events.")
        if triple in distinct_orders:
            raise ValueError(
                "Duplicate object-specific event-order edges are not allowed."
            )
        distinct_orders.add(triple)
        relations.append(
            (
                "order",
                "",
                (
                    event_map[edge.source_event],
                    event_map[edge.target_event],
                    object_map[edge.object_id],
                ),
            )
        )
    events_by_object: dict[str, set[str]] = {}
    orders_by_object: dict[str, list[tuple[str, str]]] = {}
    for event_id, object_id in incidences:
        events_by_object.setdefault(object_id, set()).add(event_id)
    for source, target, object_id in distinct_orders:
        orders_by_object.setdefault(object_id, []).append((source, target))
    for object_id in scope_ids:
        incident_events = events_by_object.get(object_id, set())
        object_edges = orders_by_object.get(object_id, [])
        if len(object_edges) != max(0, len(incident_events) - 1):
            raise ValueError(
                "A complete object order must connect every incident event in one path."
            )
        if not incident_events:
            continue
        successor = dict(object_edges)
        predecessors = {target for _, target in object_edges}
        if len(successor) != len(object_edges) or len(predecessors) != len(
            object_edges
        ):
            raise ValueError("A complete object order cannot branch or merge.")
        starts = incident_events - predecessors
        if len(starts) != 1:
            raise ValueError("A complete object order must have exactly one start.")
        reached: set[str] = set()
        current = next(iter(starts))
        while current not in reached:
            reached.add(current)
            if current not in successor:
                break
            current = successor[current]
        if reached != incident_events:
            raise ValueError(
                "A complete object order cannot contain disconnected cycles."
            )
    return _Graph(tuple(labels), tuple(relations))


@dataclass(frozen=True, slots=True)
class _Graph:
    labels: tuple[tuple[str, ...], ...]
    # Every relation has a kind, a qualifier and ordered vertex positions.
    # Order is ternary (source event, target event, object), not an event edge.
    relations: tuple[tuple[str, str, tuple[int, ...]], ...]


class _SearchLimit(Exception):
    pass


def _refine(graph: _Graph) -> tuple[tuple[int, ...], ...]:
    """Return isomorphism-invariant cells; these are not an isomorphism test."""
    labels = sorted(set(graph.labels))
    label_colors = {label: index for index, label in enumerate(labels)}
    colors = tuple(label_colors[label] for label in graph.labels)
    while True:
        neighborhoods: list[list[tuple]] = [[] for _ in graph.labels]
        for kind, qualifier, nodes in graph.relations:
            relation_colors = tuple(colors[node] for node in nodes)
            for position, node in enumerate(nodes):
                neighborhoods[node].append((kind, qualifier, position, relation_colors))
        signatures = tuple(
            (color, tuple(sorted(neighbors)))
            for color, neighbors in zip(colors, neighborhoods)
        )
        distinct = {value: index for index, value in enumerate(sorted(set(signatures)))}
        refined = tuple(distinct[value] for value in signatures)
        if refined == colors:
            break
        colors = refined
    cells: dict[int, list[int]] = {}
    for node, color in enumerate(colors):
        cells.setdefault(color, []).append(node)
    return tuple(tuple(cells[color]) for color in sorted(cells))


def _canonical_form(graph: _Graph, remaining: int) -> tuple[str, int]:
    """Canonicalize completely within a bound on complete vertex labelings.

    Check the product incrementally so a symmetric input cannot allocate a
    factorial-sized permutation pool. The bound is checked before the search;
    exceeding it is deliberately conservative, never an approximate answer.
    """
    cells = _refine(graph)
    candidates = 1
    for cell in cells:
        for factor in range(2, len(cell) + 1):
            candidates *= factor
            if candidates > remaining:
                raise _SearchLimit
    if candidates > remaining:
        raise _SearchLimit

    ordered = [node for cell in cells for node in cell]
    variable_cells: list[tuple[int, tuple[int, ...]]] = []
    offset = 0
    for cell in cells:
        if len(cell) > 1:
            variable_cells.append((offset, cell))
        offset += len(cell)

    best: str | None = None

    def encode() -> None:
        nonlocal best
        renamed = {node: index for index, node in enumerate(ordered)}
        payload = (
            tuple(graph.labels[node] for node in ordered),
            tuple(
                sorted(
                    (kind, qualifier, tuple(renamed[node] for node in nodes))
                    for kind, qualifier, nodes in graph.relations
                )
            ),
        )
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if best is None or encoded < best:
            best = encoded

    def enumerate_cells(depth: int) -> None:
        if depth == len(variable_cells):
            encode()
            return
        start, cell = variable_cells[depth]
        for permutation in itertools.permutations(cell):
            ordered[start : start + len(cell)] = permutation
            enumerate_cells(depth + 1)

    # A non-singleton cell contributes at least two candidates. Thus this
    # recursion depth is logarithmic in the explicit search bound, not |V|.
    enumerate_cells(0)
    assert best is not None
    return best, candidates


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["VARIANT_OPERATOR_ID", "discover_variants"]
