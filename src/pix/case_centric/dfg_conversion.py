"""Two native DFG-to-accepting-Petri-net constructions.

``activity_defines_place`` stores the last activity in a place and labels
each incoming route with its next activity; visible labels may repeat.
``invisibles_no_duplicates`` has one visible transition per activity and
uses silent transitions to route between activity exit/entry places.

Both accept exactly the boundary-constrained walk language of the supplied
DFG, with epsilon iff an empty trace was observed. They do not reconstruct
the original trace language: recombined paths and repetitions can be new.
All arcs are unit-weight; frequency is neither token multiplicity nor a
probability. Observed starts/ends are mandatory, never inferred from roots.
Singleton activities and empty traces are preserved. Artificial boundaries
are identifiers, never activity labels. No upstream runtime is used.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, Literal

from pix.case_centric.discovery import CaseRelationGraph, RelationEdge
from pix.compute._common import _derived_result
from pix.contracts.analysis import (
    ActivityCount,
    BoundaryCount,
    BoundaryEvidence,
    DirectlyFollowsEdge,
    DirectlyFollowsGraph,
    TransitionEvidence,
)
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
    _immutable,
)

OPERATOR_ID = "pix.case_centric.dfg_to_petri_net"
VARIANTS = ("activity_defines_place", "invisibles_no_duplicates")


@dataclass(frozen=True, slots=True)
class DFGConversionSpec:
    variant: Literal["activity_defines_place", "invisibles_no_duplicates"] = (
        "invisibles_no_duplicates"
    )
    max_net_nodes: int = 200_000
    max_net_arcs: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.DFGConversionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(
                "variant must be activity_defines_place or invisibles_no_duplicates"
            )
        for name in ("max_net_nodes", "max_net_arcs"):
            _integer(getattr(self, name), name, 1)


@dataclass(frozen=True, slots=True)
class DFGConversionRequest:
    model_digest: str | None
    parameters: DFGConversionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.DFGConversionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DFGRoute:
    """An observed boundary or edge; None denotes an artificial boundary."""

    source: str | None
    target: str | None
    transition_id: str


@dataclass(frozen=True, slots=True)
class DFGConversion:
    model: PetriNet
    profile: str
    source_model_digest: str
    input_kind: Literal["case_relation_graph", "object_type_projection"]
    projected_object_type: str | None
    activity_places: tuple[tuple[str, tuple[str, ...]], ...]
    activity_transitions: tuple[tuple[str, tuple[str, ...]], ...]
    routes: tuple[DFGRoute, ...]
    allows_empty_trace: bool


class _Unavailable(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _label(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("activity labels must be nonblank strings")
    value.encode("utf-8")


def _counts(rows: tuple, field: str) -> dict[str, int]:
    if not isinstance(rows, tuple):
        raise ValueError(f"{field} must be a tuple")
    output = {}
    for row in rows:
        if not isinstance(row, tuple) or len(row) != 2:
            raise ValueError(f"{field} entries must be (activity, count)")
        activity, count = row
        _label(activity)
        _integer(count, field, 1)
        if activity in output:
            raise ValueError(f"{field} has duplicate activity")
        output[activity] = count
    return output


def _identifiers(values, field: str) -> set[str]:
    if not isinstance(values, tuple):
        raise ValueError(f"{field} must be a tuple")
    for value in values:
        _label(value)
    if len(set(values)) != len(values):
        raise ValueError(f"{field} contains duplicate identifiers")
    return set(values)


def _validated(graph):
    """Validate counts without treating case-counted edges as occurrence flow."""
    if isinstance(graph, CaseRelationGraph):
        if graph.relation != "directly_follows":
            raise ValueError("Only directly-follows relations can be converted")
        if type(graph.complete) is not bool:
            raise ValueError("complete must be bool")
        if not graph.complete:
            raise _Unavailable(
                "dfg_incomplete",
                "A complete DFG is required; partial edges cannot define the full language",
            )
        _integer(graph.examined_event_pairs, "examined_event_pairs")
        trace_count, empty = graph.trace_count, graph.empty_trace_count
        activities = _counts(graph.activity_counts, "activity_counts")
        starts = _counts(graph.start_counts, "start_counts")
        ends = _counts(graph.end_counts, "end_counts")
        if not isinstance(graph.edges, tuple) or not all(
            isinstance(e, RelationEdge) for e in graph.edges
        ):
            raise ValueError("edges must be a tuple of RelationEdge")
        rows = []
        for edge in graph.edges:
            _integer(edge.case_count, "edge.case_count", 1)
            _integer(edge.count, "edge.count", 1)
            if edge.case_count > edge.count:
                raise ValueError("edge.case_count exceeds edge.count")
            rows.append((edge.source, edge.target, edge.count, edge.case_count))
        kind, object_type = "case_relation_graph", None
    else:
        _label(graph.object_type)
        empty_ids = _identifiers(graph.empty_object_ids, "empty_object_ids")
        trace_count, empty = graph.object_count, len(graph.empty_object_ids)
        if not isinstance(graph.activities, tuple) or not all(
            isinstance(a, ActivityCount) for a in graph.activities
        ):
            raise ValueError("activities must be a tuple of ActivityCount")
        activities = _counts(
            tuple((a.activity, a.event_occurrence_count) for a in graph.activities),
            "activities",
        )
        events_by_activity, objects_by_activity, event_activity = {}, {}, {}
        for row in graph.activities:
            events_by_activity[row.activity] = _identifiers(
                row.distinct_event_ids, "distinct_event_ids"
            )
            objects_by_activity[row.activity] = _identifiers(
                row.object_ids, "activity object_ids"
            )
            if (
                not row.distinct_event_ids
                or not row.object_ids
                or max(len(row.distinct_event_ids), len(row.object_ids))
                > row.event_occurrence_count
            ):
                raise ValueError(
                    "Activity evidence disagrees with its occurrence count"
                )
            for event in row.distinct_event_ids:
                if event in event_activity and event_activity[event] != row.activity:
                    raise ValueError("Each event ID must have exactly one activity")
                event_activity[event] = row.activity
        boundaries = []
        boundary_objects = []
        boundary_events = []
        nodes_by_activity = {a: set() for a in activities}
        for name in ("starts", "ends"):
            source_rows = getattr(graph, name)
            if not isinstance(source_rows, tuple) or not all(
                isinstance(b, BoundaryCount) for b in source_rows
            ):
                raise ValueError("boundaries must be tuples of BoundaryCount")
            seen_objects = set()
            object_events = {}
            for row in source_rows:
                if not isinstance(row.evidence, tuple) or not all(
                    isinstance(e, BoundaryEvidence) for e in row.evidence
                ):
                    raise ValueError(
                        "Boundary evidence must be a tuple of BoundaryEvidence"
                    )
                for evidence in row.evidence:
                    _label(evidence.object_id)
                    _label(evidence.event_id)
                    if (
                        evidence.object_id in seen_objects
                        or evidence.object_id in empty_ids
                    ):
                        raise ValueError(
                            "An object cannot have repeated boundaries or be both empty and nonempty"
                        )
                    if evidence.object_id not in objects_by_activity.get(
                        row.activity, set()
                    ) or evidence.event_id not in events_by_activity.get(
                        row.activity, set()
                    ):
                        raise ValueError(
                            "Boundary evidence must reference its activity observations"
                        )
                    seen_objects.add(evidence.object_id)
                    object_events[evidence.object_id] = evidence.event_id
                    nodes_by_activity[row.activity].add(
                        (evidence.object_id, evidence.event_id)
                    )
            boundary_objects.append(seen_objects)
            boundary_events.append(object_events)
            boundaries.append(
                _counts(tuple((b.activity, len(b.evidence)) for b in source_rows), name)
            )
        starts, ends = boundaries
        if boundary_objects[0] != boundary_objects[1]:
            raise ValueError("Starts and ends must refer to the same nonempty objects")
        if any(not ids <= boundary_objects[0] for ids in objects_by_activity.values()):
            raise ValueError("Every observed object must have a start and an end")
        if not isinstance(graph.edges, tuple) or not all(
            isinstance(e, DirectlyFollowsEdge) for e in graph.edges
        ):
            raise ValueError("edges must be a tuple of DirectlyFollowsEdge")
        successors, predecessors = {}, {}
        for edge in graph.edges:
            _integer(edge.occurrence_count, "edge occurrence_count", 1)
            if (
                not isinstance(edge.evidence, tuple)
                or not all(isinstance(e, TransitionEvidence) for e in edge.evidence)
                or len(edge.evidence) != edge.occurrence_count
            ):
                raise ValueError(
                    "Edge occurrence_count must match its TransitionEvidence tuple"
                )
            seen_pairs = set()
            for evidence in edge.evidence:
                pair = (
                    evidence.object_id,
                    evidence.source_event_id,
                    evidence.target_event_id,
                )
                for identifier in pair:
                    _label(identifier)
                if pair in seen_pairs:
                    raise ValueError("Duplicate edge evidence")
                seen_pairs.add(pair)
                if (
                    evidence.object_id
                    not in objects_by_activity.get(edge.source_activity, set())
                    or evidence.object_id
                    not in objects_by_activity.get(edge.target_activity, set())
                    or evidence.source_event_id
                    not in events_by_activity.get(edge.source_activity, set())
                    or evidence.target_event_id
                    not in events_by_activity.get(edge.target_activity, set())
                ):
                    raise ValueError(
                        "Edge evidence must reference its endpoint activity observations"
                    )
                source_node = (evidence.object_id, evidence.source_event_id)
                target_node = (evidence.object_id, evidence.target_event_id)
                if (
                    source_node == target_node
                    or source_node in successors
                    or target_node in predecessors
                ):
                    raise ValueError(
                        "An object event cannot follow itself or have multiple predecessors/successors"
                    )
                successors[source_node] = target_node
                predecessors[target_node] = source_node
                nodes_by_activity[edge.source_activity].add(source_node)
                nodes_by_activity[edge.target_activity].add(target_node)
        incoming, outgoing = dict.fromkeys(activities, 0), dict.fromkeys(activities, 0)
        for edge in graph.edges:
            if (
                edge.source_activity not in activities
                or edge.target_activity not in activities
            ):
                raise ValueError("Edge endpoints must reference known activities")
            incoming[edge.target_activity] += edge.occurrence_count
            outgoing[edge.source_activity] += edge.occurrence_count
        if any(
            count != starts.get(a, 0) + incoming[a]
            or count != ends.get(a, 0) + outgoing[a]
            for a, count in activities.items()
        ):
            raise ValueError(
                "Projection occurrence counts must conserve incoming/outgoing flow and boundaries"
            )
        nodes_by_object = {object_id: set() for object_id in boundary_objects[0]}
        for activity, nodes in nodes_by_activity.items():
            if (
                len(nodes) != activities[activity]
                or {event for _, event in nodes} != events_by_activity[activity]
                or {obj for obj, _ in nodes} != objects_by_activity[activity]
            ):
                raise ValueError(
                    "Activity summaries must match the distinct observed object/event pairs"
                )
            for obj, event in nodes:
                nodes_by_object[obj].add(event)
        for obj, first in boundary_events[0].items():
            cursor = (obj, first)
            visited = set()
            while cursor not in visited:
                visited.add(cursor)
                if cursor not in successors:
                    break
                cursor = successors[cursor]
            if (
                cursor != (obj, boundary_events[1][obj])
                or cursor in successors
                or {event for _, event in visited} != nodes_by_object[obj]
            ):
                raise ValueError(
                    "Every object's evidence must form one complete start-to-end event chain"
                )
        rows = [
            (e.source_activity, e.target_activity, e.occurrence_count, None)
            for e in graph.edges
        ]
        kind, object_type = "object_type_projection", graph.object_type

    _integer(trace_count, "trace_count")
    _integer(empty, "empty_trace_count")
    if empty > trace_count:
        raise ValueError("empty_trace_count exceeds trace_count")
    nonempty = trace_count - empty
    if set(starts) - set(activities) or set(ends) - set(activities):
        raise ValueError("boundaries must reference known activities")
    if sum(starts.values()) != nonempty or sum(ends.values()) != nonempty:
        raise ValueError(
            "Observed boundary counts must cover exactly all nonempty traces"
        )
    if bool(activities) != bool(nonempty):
        raise ValueError("Activity observations and nonempty traces disagree")
    if any(starts.get(a, 0) > n or ends.get(a, 0) > n for a, n in activities.items()):
        raise ValueError("Boundary count exceeds activity occurrence count")
    edges = set()
    for source, target, count, cases in rows:
        _label(source)
        _label(target)
        _integer(count, "edge count", 1)
        if source not in activities or target not in activities:
            raise ValueError("Edge endpoints must reference known activities")
        if count > min(activities[source], activities[target]):
            raise ValueError("Edge count exceeds endpoint occurrence count")
        if cases is not None and cases > nonempty:
            raise ValueError("Edge case count exceeds nonempty traces")
        if (source, target) in edges:
            raise ValueError("duplicate directly-follows edge")
        edges.add((source, target))
    if not trace_count:
        raise _Unavailable(
            "dfg_empty_log",
            "No observed traces are available; an empty log does not imply epsilon",
        )
    return (
        tuple(sorted(activities)),
        tuple(sorted(edges)),
        tuple(sorted(starts)),
        tuple(sorted(ends)),
        bool(empty),
        kind,
        object_type,
    )


def dfg_to_petri_net(
    graph: CaseRelationGraph | DirectlyFollowsGraph | ComputationResult,
    spec: DFGConversionSpec = DFGConversionSpec(),
) -> ComputationResult[DFGConversion]:
    """Convert a complete DFG, explicitly retaining its selected projection.

    ``DirectlyFollowsGraph`` already represents one selected object type and
    becomes a classical one-token model. This is not an OCPN construction or
    an implicit flattening of arbitrary OCEL data. Source and parent evidence
    survive, while the exact graph digest participates in request identity.
    """
    if not isinstance(spec, DFGConversionSpec):
        raise TypeError("spec must be DFGConversionSpec")
    parent = graph if isinstance(graph, ComputationResult) else None
    if parent is None and not isinstance(
        graph, (CaseRelationGraph, DirectlyFollowsGraph)
    ):
        raise TypeError("graph must be a supported DFG or ComputationResult")
    source = parent.source_digest if parent is not None else None
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    inherited = parent.issues if parent is not None else ()
    digest = None

    def result(status, value=None, issues=()):
        return _derived_result(
            OPERATOR_ID,
            source,
            DFGConversionRequest(digest, spec),
            status,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None:
        if parent.status is not ComputeStatus.COMPUTED or parent.value is None:
            return result(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "dfg_input_unavailable",
                        "A complete computed DFG result is required",
                    ),
                ),
            )
        graph = parent.value
    if not isinstance(graph, (CaseRelationGraph, DirectlyFollowsGraph)):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue("invalid_dfg", "Result payload must be a supported DFG"),
            ),
        )
    try:
        if not _immutable(graph):
            raise ValueError("DFG must contain immutable finite fields")
        encoded = json.dumps(
            _identity_value(graph),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = "pix.dfg.v1:sha256:" + sha256(encoded).hexdigest()
        if parent is None:
            source = digest
        activities, edges, starts, ends, empty, kind, object_type = _validated(graph)
    except _Unavailable as exc:
        return result(
            ComputeStatus.UNAVAILABLE, issues=(ComputeIssue(exc.code, str(exc)),)
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT, issues=(ComputeIssue("invalid_dfg", str(exc)),)
        )

    route_count = len(edges) + len(starts) + len(ends) + int(empty)
    if spec.variant == "activity_defines_place":
        place_count, transition_count = len(activities) + 2, route_count
    else:
        place_count, transition_count = (
            2 * len(activities) + 4,
            len(activities) + 2 + route_count,
        )
    if (
        place_count + transition_count > spec.max_net_nodes
        or 2 * transition_count > spec.max_net_arcs
    ):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "dfg_conversion_limit",
                    "Complete construction exceeds the node or arc budget; no truncated net was returned",
                ),
            ),
        )

    places, transitions, arcs, routes = [], [], [], []
    activity_places, activity_transitions = {}, {a: [] for a in activities}
    number = {a: index for index, a in enumerate(activities)}
    logical_routes = (
        tuple((None, a) for a in starts)
        + edges
        + tuple((a, None) for a in ends)
        + (((None, None),) if empty else ())
    )

    def step(identifier, before, after, activity=None):
        transitions.append(Transition(identifier, activity))
        arcs.extend((Arc(before, identifier), Arc(identifier, after)))
        if activity is not None:
            activity_transitions[activity].append(identifier)

    if spec.variant == "activity_defines_place":
        initial, final = "dfg:p:start", "dfg:p:end"
        places.extend((Place(initial), Place(final)))
        for activity in activities:
            place = f"dfg:p:activity:{number[activity]}"
            places.append(Place(place))
            activity_places[activity] = (place,)
        for source_label, target_label in logical_routes:
            route_id = f"dfg:t:route:{len(routes)}"
            before = (
                initial if source_label is None else activity_places[source_label][0]
            )
            after = final if target_label is None else activity_places[target_label][0]
            step(route_id, before, after, target_label)
            routes.append(DFGRoute(source_label, target_label, route_id))
    else:
        initial, final = "dfg:p:start:in", "dfg:p:end:out"
        start_exit, end_entry = "dfg:p:start:out", "dfg:p:end:in"
        places.extend(Place(p) for p in (initial, start_exit, end_entry, final))
        step("dfg:t:start", initial, start_exit)
        step("dfg:t:end", end_entry, final)
        for activity in activities:
            before, after = (
                f"dfg:p:in:{number[activity]}",
                f"dfg:p:out:{number[activity]}",
            )
            places.extend((Place(before), Place(after)))
            activity_places[activity] = (before, after)
            step(f"dfg:t:activity:{number[activity]}", before, after, activity)
        for source_label, target_label in logical_routes:
            route_id = f"dfg:t:route:{len(routes)}"
            before = (
                start_exit if source_label is None else activity_places[source_label][1]
            )
            after = (
                end_entry if target_label is None else activity_places[target_label][0]
            )
            step(route_id, before, after)
            routes.append(DFGRoute(source_label, target_label, route_id))

    model = PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking(((initial, 1),)),
        Marking(((final, 1),)),
    )
    payload = DFGConversion(
        model,
        f"pix.dfg.{spec.variant}.v1",
        digest,
        kind,
        object_type,
        tuple((a, activity_places[a]) for a in activities),
        tuple((a, tuple(activity_transitions[a])) for a in activities),
        tuple(routes),
        empty,
    )
    return result(
        ComputeStatus.COMPUTED,
        payload,
        (
            ComputeIssue(
                "dfg_walk_language",
                "The net accepts observed-boundary DFG walks; original trace-language equivalence and soundness are not certified. Frequencies do not become arc weights.",
            ),
        ),
    )


RESULT_SCHEMAS = {OPERATOR_ID: ("dfg_conversion", DFGConversionRequest, DFGConversion)}

__all__ = (
    "DFGConversionSpec",
    "DFGConversionRequest",
    "DFGRoute",
    "DFGConversion",
    "dfg_to_petri_net",
)
