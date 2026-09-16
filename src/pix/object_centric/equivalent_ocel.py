"""Exact grouping of normalized, leading-object OCEL structures.

This PIX profile addresses PM4Py's ``cluster_equivalent_ocel`` use case without
its timestamp/lexical object renaming or textual-description equality. Scopes
are the anchor plus ancestors and descendants in an interaction graph oriented
by first selected participation time. Equal births are explicitly bidirectional
or omitted. This is not causality and is not the nearest-type OCPA extraction.

Equivalence preserves one vertex per event, activity, object type, anchor role,
qualified E2O, and each object's selected local event order. IDs, attributes,
absolute times and excluded boundary incidence are omitted. Original O2O is
optionally preserved in equivalence, but never drives scope extraction. Complete
canonical encodings establish equality; a fingerprint is only a convenient key.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations, groupby
from typing import Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.variants import _canonical_form, _execution_graph, _Graph, _SearchLimit
from pix.contracts.execution import (
    EventOrderEdge,
    ExecutionEvent,
    ExecutionObject,
    ExecutionRelation,
    ProcessExecution,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OPERATOR_ID = "pix.object_centric.cluster_equivalent_ocel"


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    value.encode("utf-8")


def _selection(value: object, name: str, *, blank: bool = False) -> None:
    if value is None:
        return
    if not isinstance(value, tuple) or any(not isinstance(x, str) for x in value):
        raise TypeError(f"{name} must be a tuple of strings or None")
    for item in value:
        if not blank:
            _text(item, name)
        else:
            item.encode("utf-8")


@dataclass(frozen=True, slots=True)
class EquivalentOCELSpec:
    """Explicit finite structural equivalence; limits never truncate clusters.

    ``qualifiers`` selects E2O for both scope and equivalence; ``None`` selects
    all and ``()`` none. The selected qualifier labels remain significant.
    ``event_id`` resolves local timestamp ties lexically: rename invariance then
    applies only when renaming preserves that selected order. ``reject`` is the
    default and never fabricates an order. Bidirectional equal births retain
    co-birth connectivity without using object IDs as temporal evidence.
    """

    leading_object_type: str
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    birth_ties: Literal["bidirectional", "exclude"] = "bidirectional"
    o2o: Literal["exclude", "qualified"] = "exclude"
    o2o_qualifiers: tuple[str, ...] | None = None
    max_search_states: int = 100_000
    max_scopes: int = 10_000
    profile: Literal["first_participation_exact_structure"] = (
        "first_participation_exact_structure"
    )

    def __post_init__(self) -> None:
        _text(self.leading_object_type, "leading_object_type")
        for name in ("object_types", "qualifiers", "o2o_qualifiers"):
            values = getattr(self, name)
            _selection(values, name, blank=name != "object_types")
            if values is not None:
                object.__setattr__(self, name, tuple(sorted(set(values))))
        if (
            self.object_types is not None
            and self.leading_object_type not in self.object_types
        ):
            raise ValueError("leading_object_type must be selected in object_types")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if self.birth_ties not in ("bidirectional", "exclude"):
            raise ValueError("birth_ties must be bidirectional or exclude")
        if self.o2o not in ("exclude", "qualified"):
            raise ValueError("o2o must be exclude or qualified")
        if self.o2o == "exclude" and self.o2o_qualifiers is not None:
            raise ValueError("o2o_qualifiers require qualified O2O preservation")
        if self.profile != "first_participation_exact_structure":
            raise ValueError("unsupported equivalence profile")
        for name in ("max_search_states", "max_scopes"):
            value = getattr(self, name)
            if type(value) is not int:
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class EquivalentOCELScope:
    leading_object_id: str
    object_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    order_edges: tuple[EventOrderEdge, ...]
    canonical_encoding: str

    def __post_init__(self) -> None:
        _text(self.leading_object_id, "leading_object_id")
        _text(self.canonical_encoding, "canonical_encoding")
        for name in ("object_ids", "event_ids"):
            values = getattr(self, name)
            _selection(values, name)
            if not isinstance(values, tuple) or len(set(values)) != len(values):
                raise ValueError(f"{name} must be a tuple of unique IDs")
        if self.leading_object_id not in self.object_ids:
            raise ValueError("the anchor must belong to its scope")
        if not isinstance(self.order_edges, tuple) or any(
            not isinstance(edge, EventOrderEdge) for edge in self.order_edges
        ):
            raise TypeError("order_edges must be an immutable tuple")


@dataclass(frozen=True, slots=True)
class EquivalentOCELCluster:
    canonical_encoding: str
    canonical_signature: str
    leading_object_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.canonical_encoding, "canonical_encoding")
        _selection(self.leading_object_ids, "leading_object_ids")
        if (
            not isinstance(self.leading_object_ids, tuple)
            or not self.leading_object_ids
        ):
            raise ValueError("a cluster needs at least one anchor")
        if len(set(self.leading_object_ids)) != len(self.leading_object_ids):
            raise ValueError("cluster anchors must be unique")
        if self.canonical_signature != _signature(self.canonical_encoding):
            raise ValueError("signature disagrees with the canonical encoding")

    @property
    def frequency(self) -> int:
        return len(self.leading_object_ids)


@dataclass(frozen=True, slots=True)
class EquivalentOCELSet:
    spec: EquivalentOCELSpec
    scopes: tuple[EquivalentOCELScope, ...]
    clusters: tuple[EquivalentOCELCluster, ...]
    search_states: int
    unassigned_event_ids: tuple[str, ...]
    unassigned_object_ids: tuple[str, ...]
    overlapping_event_ids: tuple[str, ...]
    overlapping_object_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.spec, EquivalentOCELSpec):
            raise TypeError("spec must be EquivalentOCELSpec")
        for name, kind in (
            ("scopes", EquivalentOCELScope),
            ("clusters", EquivalentOCELCluster),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(row, kind) for row in values
            ):
                raise TypeError(f"{name} must be an immutable tuple of {kind.__name__}")
        if (
            type(self.search_states) is not int
            or not 0 <= self.search_states <= self.spec.max_search_states
        ):
            raise ValueError(
                "search_states must be an integer within the declared bound"
            )
        anchors = [row.leading_object_id for row in self.scopes]
        grouped = [
            anchor for cluster in self.clusters for anchor in cluster.leading_object_ids
        ]
        if len(anchors) != len(set(anchors)) or sorted(anchors) != sorted(grouped):
            raise ValueError("clusters must partition scope anchors exactly once")
        forms = {row.leading_object_id: row.canonical_encoding for row in self.scopes}
        if len({row.canonical_encoding for row in self.clusters}) != len(self.clusters):
            raise ValueError("equivalent structures must belong to one cluster")
        if any(
            forms[anchor] != row.canonical_encoding
            for row in self.clusters
            for anchor in row.leading_object_ids
        ):
            raise ValueError("cluster encoding disagrees with a member scope")
        for name in (
            "unassigned_event_ids",
            "unassigned_object_ids",
            "overlapping_event_ids",
            "overlapping_object_ids",
        ):
            values = getattr(self, name)
            _selection(values, name)
            if not isinstance(values, tuple) or len(values) != len(set(values)):
                raise ValueError(f"{name} must contain immutable unique IDs")

    @property
    def exact(self) -> bool:
        return True


def _signature(encoding: str) -> str:
    return "sha256:" + sha256(encoding.encode("utf-8")).hexdigest()


def _reachable(anchor: str, edges: dict[str, set[str]]) -> set[str]:
    seen = {anchor}
    pending = [anchor]
    while pending:
        for neighbor in edges[pending.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                pending.append(neighbor)
    return seen


def cluster_equivalent_ocel(
    log: OCEL | ComputationContext, spec: EquivalentOCELSpec
) -> ComputationResult[EquivalentOCELSet]:
    """Group complete leading-object scopes under exact consistent renaming.

    Every anchor is considered, including eventless ones. Ancestors and
    descendants are computed separately and unioned: this is deliberately not
    an undirected connected component. Scope witnesses retain original IDs,
    including shared events and objects across scopes. A tie or exhausted bound
    yields ``unavailable`` without partial clusters.
    """
    if not isinstance(spec, EquivalentOCELSpec):
        raise TypeError("spec must be EquivalentOCELSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )

    def unavailable(code: str, message: str, at: tuple[str, ...] = ()):
        return _result(
            OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue(code, message, at),),
        )

    known_types = {row.name for row in context.log.object_types}
    selected_types = (
        known_types if spec.object_types is None else set(spec.object_types)
    )
    missing = (selected_types | {spec.leading_object_type}) - known_types
    if missing:
        return unavailable(
            "unknown_object_type",
            "Requested object types are not declared",
            tuple(sorted(missing)),
        )
    objects = {obj.id: obj for obj in context.log.objects if obj.type in selected_types}
    anchors = sorted(
        oid for oid, obj in objects.items() if obj.type == spec.leading_object_type
    )
    if len(anchors) > spec.max_scopes:
        return unavailable(
            "scope_limit_exceeded",
            "All anchors must fit max_scopes; no prefix is returned",
        )

    selected_relations = tuple(
        relation
        for relation in context.log.e2o
        if relation.object in objects
        and (spec.qualifiers is None or relation.qualifier in spec.qualifiers)
    )
    object_events: dict[str, set[str]] = {oid: set() for oid in objects}
    event_objects: dict[str, set[str]] = defaultdict(set)
    for relation in selected_relations:
        object_events[relation.object].add(relation.event)
        event_objects[relation.event].add(relation.object)
    first = {
        oid: min(context.events_by_id[eid].time for eid in events)
        for oid, events in object_events.items()
        if events
    }
    successors: dict[str, set[str]] = {oid: set() for oid in objects}
    predecessors: dict[str, set[str]] = {oid: set() for oid in objects}
    for participants in event_objects.values():
        for left, right in combinations(sorted(participants), 2):
            directions = (
                ((left, right),)
                if first[left] < first[right]
                else (
                    ((right, left),)
                    if first[right] < first[left]
                    else (
                        ((left, right), (right, left))
                        if spec.birth_ties == "bidirectional"
                        else ()
                    )
                )
            )
            for source, target in directions:
                successors[source].add(target)
                predecessors[target].add(source)

    groups: dict[str, list[str]] = defaultdict(list)
    scopes: list[EquivalentOCELScope] = []
    event_memberships: dict[str, int] = defaultdict(int)
    object_memberships: dict[str, int] = defaultdict(int)
    states = 0
    resolved_ties: set[str] = set()
    for anchor in anchors:
        admitted = _reachable(anchor, successors) | _reachable(anchor, predecessors)
        event_ids = set().union(*(object_events[oid] for oid in admitted))
        relations = tuple(
            sorted(
                ExecutionRelation(row.event, row.object, row.qualifier)
                for row in selected_relations
                if row.object in admitted
            )
        )
        order_edges: list[EventOrderEdge] = []
        for oid in sorted(admitted):
            ordered = sorted(
                object_events[oid],
                key=lambda eid: (context.events_by_id[eid].time, eid),
            )
            for _, same_time in groupby(
                ordered, key=lambda eid: context.events_by_id[eid].time
            ):
                tied = tuple(same_time)
                if len(tied) > 1:
                    if spec.tie_policy == "reject":
                        return unavailable(
                            "ambiguous_event_order",
                            "Exact structure requires an explicit local order for tied events",
                            (anchor, oid, *tied),
                        )
                    resolved_ties.add(oid)
            order_edges.extend(
                EventOrderEdge(
                    left,
                    right,
                    oid,
                    context.events_by_id[left].time == context.events_by_id[right].time,
                )
                for left, right in zip(ordered, ordered[1:])
            )
        ordered_events = tuple(sorted(event_ids))
        ordered_objects = tuple(sorted(admitted))
        execution = ProcessExecution(
            execution_id=anchor,
            leading_object_id=anchor,
            events=tuple(
                ExecutionEvent(
                    eid, context.events_by_id[eid].type, context.events_by_id[eid].time
                )
                for eid in ordered_events
            ),
            objects=tuple(
                ExecutionObject(oid, objects[oid].type) for oid in ordered_objects
            ),
            boundary_objects=(),
            relations=relations,
            excluded_relations=(),
            order_edges=tuple(order_edges),
            order_status="complete",
            order_ties=(),
        )
        graph = _execution_graph(execution)
        if spec.o2o == "qualified":
            object_nodes = {
                oid: len(ordered_events) + index
                for index, oid in enumerate(ordered_objects)
            }
            o2o_edges = tuple(
                (
                    "o2o",
                    row.qualifier,
                    (object_nodes[row.source], object_nodes[row.target]),
                )
                for row in context.log.o2o
                if row.source in admitted
                and row.target in admitted
                and (
                    spec.o2o_qualifiers is None or row.qualifier in spec.o2o_qualifiers
                )
            )
            graph = _Graph(graph.labels, (*graph.relations, *o2o_edges))
        try:
            encoding, cost = _canonical_form(graph, spec.max_search_states - states)
        except _SearchLimit:
            return unavailable(
                "limit_exceeded",
                "Exact canonical labeling exceeds max_search_states; no partial clusters are returned",
                (anchor,),
            )
        states += cost
        groups[encoding].append(anchor)
        scopes.append(
            EquivalentOCELScope(
                anchor, ordered_objects, ordered_events, tuple(order_edges), encoding
            )
        )
        for eid in ordered_events:
            event_memberships[eid] += 1
        for oid in ordered_objects:
            object_memberships[oid] += 1

    clusters = tuple(
        EquivalentOCELCluster(encoding, _signature(encoding), tuple(members))
        for encoding, members in sorted(groups.items())
    )
    value = EquivalentOCELSet(
        spec,
        tuple(scopes),
        clusters,
        states,
        tuple(sorted(e.id for e in context.log.events if not event_memberships[e.id])),
        tuple(
            sorted(o.id for o in context.log.objects if not object_memberships[o.id])
        ),
        tuple(sorted(eid for eid, count in event_memberships.items() if count > 1)),
        tuple(sorted(oid for oid, count in object_memberships.items() if count > 1)),
    )
    result_issues = (
        (
            ComputeIssue(
                "event_id_tie_order",
                "Tied event order follows event IDs; renaming may change that convention",
                tuple(sorted(resolved_ties)),
            ),
        )
        if resolved_ties
        else ()
    )
    return _result(
        OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, value, result_issues
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("equivalent-ocel-structures", EquivalentOCELSpec, EquivalentOCELSet),
}

__all__ = (
    "EquivalentOCELSpec",
    "EquivalentOCELScope",
    "EquivalentOCELCluster",
    "EquivalentOCELSet",
    "cluster_equivalent_ocel",
    "RESULT_SCHEMAS",
)
