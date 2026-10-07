"""Native OCEL relation graphs and temporal attribute queries.

Graph relations are observations, not proof of real-world causation. Qualifier
selection never duplicates an object occurrence. Ordered lifecycle graphs reject
ties by default; lexical ordering is an explicit, recorded convention.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from itertools import combinations
from math import isfinite
from typing import Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
)
from pix.ocel import O2O, OCEL
from pix.ocel.model import Value

GraphKind = Literal["interaction", "descendants", "inheritance", "cobirth", "codeath"]
GRAPH_KINDS = ("interaction", "descendants", "inheritance", "cobirth", "codeath")


def _strings(value: object, name: str, *, blank: bool = False) -> None:
    if value is not None:
        if not isinstance(value, tuple):
            raise TypeError(f"{name} must be a tuple or None")
        if any(not isinstance(item, str) for item in value):
            raise TypeError(f"{name} must contain strings")
        if not blank and any(not item.strip() for item in value):
            raise ValueError(f"{name} must not contain blank strings")


def _selection(spec: object) -> None:
    _strings(spec.qualifiers, "qualifiers", blank=True)
    if spec.qualifiers is not None:
        object.__setattr__(spec, "qualifiers", tuple(sorted(set(spec.qualifiers))))


def _ordering(spec: object) -> None:
    _selection(spec)
    if spec.tie_policy not in ("reject", "event_id"):
        raise ValueError("tie_policy must be reject or event_id")


@dataclass(frozen=True, slots=True)
class ObjectGraphSpec:
    kind: GraphKind = "interaction"
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self) -> None:
        if self.kind not in GRAPH_KINDS:
            raise ValueError("unknown object graph kind")
        _ordering(self)


@dataclass(frozen=True, slots=True)
class ObjectGraphNode:
    object_id: str
    object_type: str


@dataclass(frozen=True, slots=True)
class ObjectGraphEdge:
    source: str
    target: str
    event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ObjectGraph:
    spec: ObjectGraphSpec
    directed: bool
    nodes: tuple[ObjectGraphNode, ...]
    edges: tuple[ObjectGraphEdge, ...]


def _incidence(context: ComputationContext, qualifiers: tuple[str, ...] | None):
    allowed = None if qualifiers is None else set(qualifiers)
    event_objects: dict[str, set[str]] = {
        event.id: set() for event in context.log.events
    }
    object_events: dict[str, set[str]] = {obj.id: set() for obj in context.log.objects}
    for relation in context.log.e2o:
        if allowed is None or relation.qualifier in allowed:
            event_objects[relation.event].add(relation.object)
            object_events[relation.object].add(relation.event)
    return event_objects, object_events


def _object_graph(context: ComputationContext, spec: ObjectGraphSpec):
    event_objects, object_events = _incidence(context, spec.qualifiers)
    issues: list[ComputeIssue] = []
    first: dict[str, str] = {}
    last: dict[str, str] = {}
    rank = {
        event.id: index
        for index, event in enumerate(
            sorted(context.log.events, key=lambda item: (item.time, item.id))
        )
    }
    if spec.kind != "interaction":
        for object_id, event_ids in sorted(object_events.items()):
            ordered = sorted(event_ids, key=rank.__getitem__)
            if ordered:
                first[object_id], last[object_id] = ordered[0], ordered[-1]
            for left, right in zip(ordered, ordered[1:]):
                if context.events_by_id[left].time == context.events_by_id[right].time:
                    issues.append(
                        ComputeIssue(
                            "ambiguous_event_order"
                            if spec.tie_policy == "reject"
                            else "timestamp_tie_broken",
                            "Lifecycle order has equal timestamps; event_id ordering is not causal evidence",
                            ("object", object_id, "events", left, right),
                        )
                    )
        if spec.tie_policy == "reject" and issues:
            return None, tuple(issues)
    witnesses: dict[tuple[str, str], set[str]] = defaultdict(set)
    for event_id, object_ids in event_objects.items():
        for source, target in combinations(sorted(object_ids), 2):
            if spec.kind == "interaction":
                witnesses[source, target].add(event_id)
            elif spec.kind in ("cobirth", "codeath"):
                endpoints = first if spec.kind == "cobirth" else last
                if endpoints[source] == event_id == endpoints[target]:
                    witnesses[source, target].add(event_id)
            else:
                for left, right in ((source, target), (target, source)):
                    if spec.kind == "descendants":
                        selected = (
                            rank[first[left]] < rank[event_id]
                            and first[right] == event_id
                        )
                    else:
                        selected = last[left] == event_id == first[right]
                    if selected:
                        witnesses[left, right].add(event_id)
    if spec.kind == "inheritance":
        # Simultaneously born and terminated objects do not imply inheritance.
        reciprocal = {pair for pair in witnesses if (pair[1], pair[0]) in witnesses}
        for pair in reciprocal:
            del witnesses[pair]
    return ObjectGraph(
        spec,
        spec.kind in ("descendants", "inheritance"),
        tuple(
            ObjectGraphNode(obj.id, obj.type)
            for obj in sorted(context.log.objects, key=lambda obj: obj.id)
        ),
        tuple(
            ObjectGraphEdge(source, target, tuple(sorted(events)))
            for (source, target), events in sorted(witnesses.items())
        ),
    ), tuple(issues)


def discover_object_graph(
    log: OCEL | ComputationContext,
    spec: ObjectGraphSpec = ObjectGraphSpec(),
) -> ComputationResult[ObjectGraph]:
    """Discover five qualified-incidence graph profiles, retaining isolated nodes.

    Interaction joins co-participants; descendants joins an already observed
    participant to a first-observed participant. Inheritance joins last to first
    at the same event, excluding reciprocal pairs. Cobirth/codeath require the
    same first/last EVENT, not merely equal timestamps. No O2O edge is inferred.
    """
    if not isinstance(spec, ObjectGraphSpec):
        raise TypeError("spec must be ObjectGraphSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.discover_object_graph",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    value, issues = _object_graph(context, spec)
    return _result(
        "pix.object_centric.discover_object_graph",
        context,
        spec,
        ComputeStatus.COMPUTED if value is not None else ComputeStatus.UNAVAILABLE,
        value,
        issues,
    )


@dataclass(frozen=True, slots=True)
class ETOTSpec:
    qualifiers: tuple[str, ...] | None = None
    frequency: Literal[
        "qualified_relations", "event_object_pairs", "events", "objects"
    ] = "qualified_relations"
    include_declared_types: bool = False

    def __post_init__(self) -> None:
        _selection(self)
        if self.frequency not in (
            "qualified_relations",
            "event_object_pairs",
            "events",
            "objects",
        ):
            raise ValueError("unknown ET-OT frequency profile")
        if type(self.include_declared_types) is not bool:
            raise TypeError("include_declared_types must be bool")


@dataclass(frozen=True, slots=True)
class ETOTEdge:
    activity: str
    object_type: str
    frequency: int


@dataclass(frozen=True, slots=True)
class ETOTGraph:
    spec: ETOTSpec
    activities: tuple[str, ...]
    object_types: tuple[str, ...]
    edges: tuple[ETOTEdge, ...]


def discover_etot(
    log: OCEL | ComputationContext, spec: ETOTSpec = ETOTSpec()
) -> ComputationResult[ETOTGraph]:
    """Activity-to-object-type incidence; the counted population is explicit.

    Qualified relations counts each distinct E2O role. Event-object pairs removes
    role multiplicity, events counts unique events, objects unique objects, per
    activity/type edge. Unobserved schema declarations are opt-in nodes.
    """
    if not isinstance(spec, ETOTSpec):
        raise TypeError("spec must be ETOTSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.discover_etot",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    occurrences: dict[tuple[str, str], set[object]] = defaultdict(set)
    for relation in context.log.e2o:
        if spec.qualifiers is not None and relation.qualifier not in spec.qualifiers:
            continue
        key = (
            context.events_by_id[relation.event].type,
            context.objects_by_id[relation.object].type,
        )
        token = {
            "qualified_relations": (
                relation.event,
                relation.object,
                relation.qualifier,
            ),
            "event_object_pairs": (relation.event, relation.object),
            "events": relation.event,
            "objects": relation.object,
        }[spec.frequency]
        occurrences[key].add(token)
    activities = {key[0] for key in occurrences}
    object_types = {key[1] for key in occurrences}
    if spec.include_declared_types:
        activities.update(item.name for item in context.log.event_types)
        object_types.update(item.name for item in context.log.object_types)
    value = ETOTGraph(
        spec,
        tuple(sorted(activities)),
        tuple(sorted(object_types)),
        tuple(
            ETOTEdge(*key, len(tokens)) for key, tokens in sorted(occurrences.items())
        ),
    )
    return _result(
        "pix.object_centric.discover_etot", context, spec, ComputeStatus.COMPUTED, value
    )


@dataclass(frozen=True, slots=True)
class OTGSpec:
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    undirected_orientation: Literal["type_id", "object_id"] = "type_id"

    def __post_init__(self) -> None:
        _ordering(self)
        if self.undirected_orientation not in ("type_id", "object_id"):
            raise ValueError("undirected_orientation must be type_id or object_id")


@dataclass(frozen=True, slots=True)
class OTGEdge:
    source_type: str
    relation: GraphKind
    target_type: str
    object_pair_count: int


@dataclass(frozen=True, slots=True)
class OTGGraph:
    spec: OTGSpec
    object_types: tuple[str, ...]
    edges: tuple[OTGEdge, ...]


def discover_otg(
    log: OCEL | ComputationContext, spec: OTGSpec = OTGSpec()
) -> ComputationResult[OTGGraph]:
    """Aggregate five object graphs by type, counting DISTINCT object pairs.

    type_id canonicalizes the endpoints of undirected type edges. object_id keeps
    the orientation induced by object IDs (the pinned PM4Py convention); those
    counts can change under object renaming, so the profiles remain distinct.
    """
    if not isinstance(spec, OTGSpec):
        raise TypeError("spec must be OTGSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.discover_otg",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    counts: dict[tuple[str, str, str], int] = defaultdict(int)
    all_issues: list[ComputeIssue] = []
    for kind in GRAPH_KINDS:
        graph, issues = _object_graph(
            context, ObjectGraphSpec(kind, spec.qualifiers, spec.tie_policy)
        )
        all_issues.extend(issue for issue in issues if issue not in all_issues)
        if graph is None:
            return _result(
                "pix.object_centric.discover_otg",
                context,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                tuple(all_issues),
            )
        for edge in graph.edges:
            left = context.objects_by_id[edge.source].type
            right = context.objects_by_id[edge.target].type
            if not graph.directed and spec.undirected_orientation == "type_id":
                left, right = sorted((left, right))
            counts[left, kind, right] += 1
    value = OTGGraph(
        spec,
        tuple(sorted({obj.type for obj in context.log.objects})),
        tuple(OTGEdge(*key, count) for key, count in sorted(counts.items())),
    )
    return _result(
        "pix.object_centric.discover_otg",
        context,
        spec,
        ComputeStatus.COMPUTED,
        value,
        tuple(all_issues),
    )


@dataclass(frozen=True, slots=True)
class AttributeAsOfSpec:
    at: datetime
    object_ids: tuple[str, ...] | None = None
    names: tuple[str, ...] | None = None
    inclusive: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.at, datetime):
            raise TypeError("at must be datetime")
        if self.at.tzinfo is None or self.at.utcoffset() is None:
            raise ValueError("at must include timezone information")
        if type(self.inclusive) is not bool:
            raise TypeError("inclusive must be bool")
        for key in ("object_ids", "names"):
            value = getattr(self, key)
            _strings(value, key)
            if value is not None:
                object.__setattr__(self, key, tuple(sorted(set(value))))


@dataclass(frozen=True, slots=True)
class OCELScalar:
    """A typed primitive; persisted timestamp values cannot become plain strings."""

    kind: Literal["string", "time", "integer", "float", "boolean"]
    text_value: str | None = None
    timestamp_value: datetime | None = None
    integer_value: int | None = None
    float_value: float | None = None
    boolean_value: bool | None = None

    def __post_init__(self) -> None:
        fields = {
            "string": ("text_value", str),
            "time": ("timestamp_value", datetime),
            "integer": ("integer_value", int),
            "float": ("float_value", float),
            "boolean": ("boolean_value", bool),
        }
        if self.kind not in fields:
            raise ValueError("unknown OCEL scalar kind")
        selected, expected_type = fields[self.kind]
        if type(getattr(self, selected)) is not expected_type:
            raise TypeError("scalar kind and value type must agree")
        if any(
            getattr(self, name) is not None
            for name, _ in fields.values()
            if name != selected
        ):
            raise ValueError("only the selected scalar field may have a value")
        if self.kind == "time" and (
            self.timestamp_value.tzinfo is None
            or self.timestamp_value.utcoffset() is None
        ):
            raise ValueError("scalar timestamp must include timezone information")
        if self.kind == "float" and not isfinite(self.float_value):
            raise ValueError("scalar float must be finite")

    @property
    def native_value(self) -> Value:
        return {
            "string": self.text_value,
            "time": self.timestamp_value,
            "integer": self.integer_value,
            "float": self.float_value,
            "boolean": self.boolean_value,
        }[self.kind]


def _scalar(value: Value) -> OCELScalar:
    if isinstance(value, datetime):
        return OCELScalar("time", timestamp_value=value)
    if type(value) is bool:
        return OCELScalar("boolean", boolean_value=value)
    if type(value) is int:
        return OCELScalar("integer", integer_value=value)
    if type(value) is float:
        return OCELScalar("float", float_value=value)
    return OCELScalar("string", text_value=value)


@dataclass(frozen=True, slots=True)
class AttributeAsOfValue:
    object_id: str
    name: str
    declared: bool
    value: OCELScalar | None
    assigned_at: datetime | None


@dataclass(frozen=True, slots=True)
class AttributeSnapshot:
    at: datetime
    inclusive: bool
    values: tuple[AttributeAsOfValue, ...]


def object_attributes_as_of(
    log: OCEL | ComputationContext, spec: AttributeAsOfSpec
) -> ComputationResult[AttributeSnapshot]:
    """Latest qualified assignment at/before a boundary; never use future values.

    Missing assignments remain None with their declaration status. Datetimes
    (including the OCEL initial epoch assignment) keep their actual timestamps.
    This temporal query does not attach invented lifetimes to static O2O edges.
    """
    if not isinstance(spec, AttributeAsOfSpec):
        raise TypeError("spec must be AttributeAsOfSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.object_attributes_as_of",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    selected = (
        set(context.objects_by_id) if spec.object_ids is None else set(spec.object_ids)
    )
    unknown = selected - context.objects_by_id.keys()
    if unknown:
        return _result(
            "pix.object_centric.object_attributes_as_of",
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(
                ComputeIssue(
                    "unknown_object", "Object is not in this log", ("object", item)
                )
                for item in sorted(unknown)
            ),
        )
    declarations = {
        item.name: {attr.name for attr in item.attributes}
        for item in context.log.object_types
    }
    values: list[AttributeAsOfValue] = []
    for object_id in sorted(selected):
        obj = context.objects_by_id[object_id]
        names = declarations[obj.type] if spec.names is None else set(spec.names)
        latest = {}
        for assignment in obj.attributes:
            eligible = (
                assignment.time <= spec.at
                if spec.inclusive
                else assignment.time < spec.at
            )
            if eligible and (
                assignment.name not in latest
                or assignment.time > latest[assignment.name].time
            ):
                latest[assignment.name] = assignment
        for name in sorted(names):
            assignment = latest.get(name)
            values.append(
                AttributeAsOfValue(
                    object_id,
                    name,
                    name in declarations[obj.type],
                    None if assignment is None else _scalar(assignment.value),
                    None if assignment is None else assignment.time,
                )
            )
    return _result(
        "pix.object_centric.object_attributes_as_of",
        context,
        spec,
        ComputeStatus.COMPUTED,
        AttributeSnapshot(spec.at, spec.inclusive, tuple(values)),
    )


@dataclass(frozen=True, slots=True)
class ObjectRelationSpec:
    object_ids: tuple[str, ...]
    direction: Literal["outbound", "inbound", "both"] = "outbound"
    qualifiers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.object_ids is None:
            raise TypeError("object_ids must be a tuple")
        _strings(self.object_ids, "object_ids")
        object.__setattr__(self, "object_ids", tuple(sorted(set(self.object_ids))))
        _selection(self)
        if self.direction not in ("outbound", "inbound", "both"):
            raise ValueError("direction must be outbound, inbound or both")


@dataclass(frozen=True, slots=True)
class ObjectRelations:
    relations: tuple[O2O, ...]


def query_object_relations(
    log: OCEL | ComputationContext, spec: ObjectRelationSpec
) -> ComputationResult[ObjectRelations]:
    """Select explicit directed O2O records without reversing their stored direction."""
    if not isinstance(spec, ObjectRelationSpec):
        raise TypeError("spec must be ObjectRelationSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.query_object_relations",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    unknown = set(spec.object_ids) - context.objects_by_id.keys()
    if unknown:
        return _result(
            "pix.object_centric.query_object_relations",
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(
                ComputeIssue(
                    "unknown_object", "Object is not in this log", ("object", item)
                )
                for item in sorted(unknown)
            ),
        )
    selected = set(spec.object_ids)
    records = tuple(
        sorted(
            (
                relation
                for relation in context.log.o2o
                if (spec.qualifiers is None or relation.qualifier in spec.qualifiers)
                and (
                    (
                        spec.direction in ("outbound", "both")
                        and relation.source in selected
                    )
                    or (
                        spec.direction in ("inbound", "both")
                        and relation.target in selected
                    )
                )
            ),
            key=lambda relation: (relation.source, relation.target, relation.qualifier),
        )
    )
    return _result(
        "pix.object_centric.query_object_relations",
        context,
        spec,
        ComputeStatus.COMPUTED,
        ObjectRelations(records),
    )


@dataclass(frozen=True, slots=True)
class ExactRatio:
    numerator: int
    denominator: int

    @property
    def value(self) -> float | None:
        return self.numerator / self.denominator if self.denominator else None


@dataclass(frozen=True, slots=True)
class GraphComparisonRequest:
    reference: ObjectGraph | ETOTGraph | OTGGraph
    observed: ObjectGraph | ETOTGraph | OTGGraph


@dataclass(frozen=True, slots=True)
class GraphComparison:
    reference_edge_count: int
    observed_edge_count: int
    shared_edge_count: int
    missing_edges: tuple[tuple[str, ...], ...]
    unexpected_edges: tuple[tuple[str, ...], ...]
    edge_coverage: ExactRatio
    observed_edge_support: ExactRatio
    structural_jaccard: ExactRatio
    reference_frequency: int
    observed_frequency: int
    shared_frequency: int
    frequency_coverage: ExactRatio
    observed_frequency_support: ExactRatio
    weighted_jaccard: ExactRatio
    absolute_frequency_difference: int


def _edge_frequencies(
    graph: ObjectGraph | ETOTGraph | OTGGraph,
) -> dict[tuple[str, ...], int]:
    if isinstance(graph, ObjectGraph):
        if not isinstance(graph.spec, ObjectGraphSpec):
            raise TypeError("object graph requires ObjectGraphSpec")
        if type(graph.directed) is not bool or graph.directed != (
            graph.spec.kind in ("descendants", "inheritance")
        ):
            raise ValueError("graph directedness disagrees with its relation kind")
        if not isinstance(graph.nodes, tuple) or any(
            not isinstance(node, ObjectGraphNode) for node in graph.nodes
        ):
            raise TypeError("object graph nodes must be an immutable node tuple")
        node_ids = tuple(node.object_id for node in graph.nodes)
        _strings(node_ids, "object node IDs")
        _strings(tuple(node.object_type for node in graph.nodes), "object node types")
        if len(set(node_ids)) != len(node_ids):
            raise ValueError("object graph has duplicate nodes")
        if not isinstance(graph.edges, tuple) or any(
            not isinstance(edge, ObjectGraphEdge) for edge in graph.edges
        ):
            raise TypeError("object graph edges must be an immutable edge tuple")
        for edge in graph.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError("object graph edge references a missing node")
            if edge.source == edge.target:
                raise ValueError("object relation graphs do not contain self loops")
            if not graph.directed and edge.source > edge.target:
                raise ValueError(
                    "undirected object edges require canonical endpoint order"
                )
            if edge.event_ids is None:
                raise TypeError("object graph witnesses must be a tuple")
            _strings(edge.event_ids, "witness event IDs")
            if len(set(edge.event_ids)) != len(edge.event_ids):
                raise ValueError("object graph witnesses must be unique")
        pairs = [
            ((edge.source, edge.target), len(edge.event_ids)) for edge in graph.edges
        ]
    elif isinstance(graph, ETOTGraph):
        if not isinstance(graph.spec, ETOTSpec):
            raise TypeError("ET-OT graph requires ETOTSpec")
        for nodes in (graph.activities, graph.object_types):
            if nodes is None:
                raise TypeError("ET-OT node sets must be tuples")
            _strings(nodes, "ET-OT nodes")
            if len(set(nodes)) != len(nodes):
                raise ValueError("ET-OT graph has duplicate nodes")
        if not isinstance(graph.edges, tuple) or any(
            not isinstance(edge, ETOTEdge) for edge in graph.edges
        ):
            raise TypeError("ET-OT edges must be an immutable edge tuple")
        if any(
            edge.activity not in graph.activities
            or edge.object_type not in graph.object_types
            for edge in graph.edges
        ):
            raise ValueError("ET-OT edge references a missing node")
        pairs = [
            ((edge.activity, edge.object_type), edge.frequency) for edge in graph.edges
        ]
    elif isinstance(graph, OTGGraph):
        if not isinstance(graph.spec, OTGSpec):
            raise TypeError("OTG requires OTGSpec")
        if graph.object_types is None:
            raise TypeError("OTG node set must be a tuple")
        _strings(graph.object_types, "OTG nodes")
        if len(set(graph.object_types)) != len(graph.object_types):
            raise ValueError("OTG has duplicate nodes")
        if not isinstance(graph.edges, tuple) or any(
            not isinstance(edge, OTGEdge) for edge in graph.edges
        ):
            raise TypeError("OTG edges must be an immutable edge tuple")
        for edge in graph.edges:
            if (
                edge.source_type not in graph.object_types
                or edge.target_type not in graph.object_types
            ):
                raise ValueError("OTG edge references a missing node")
            if edge.relation not in GRAPH_KINDS:
                raise ValueError("OTG edge has unknown relation kind")
            if (
                graph.spec.undirected_orientation == "type_id"
                and edge.relation not in ("descendants", "inheritance")
                and edge.source_type > edge.target_type
            ):
                raise ValueError(
                    "undirected type edges require canonical endpoint order"
                )
        pairs = [
            (
                (edge.source_type, edge.relation, edge.target_type),
                edge.object_pair_count,
            )
            for edge in graph.edges
        ]
    else:
        raise TypeError("graph must be ObjectGraph, ETOTGraph or OTGGraph")
    if len({pair for pair, count in pairs}) != len(pairs):
        raise ValueError("graph has duplicate edge keys")
    if any(type(count) is not int or count <= 0 for pair, count in pairs):
        raise ValueError("graph edge frequencies must be positive integers")
    return dict(pairs)


def compare_object_graphs(
    reference: ObjectGraph | ETOTGraph | OTGGraph,
    observed: ObjectGraph | ETOTGraph | OTGGraph,
) -> ComputationResult[GraphComparison]:
    """Compare same-profile edges; structure and frequency are separate metrics.

    Coverage divides overlap by reference mass; support divides it by observed
    mass. Frequency overlap uses min(counts). Zero denominators remain undefined.
    Nodes and execution behavior are outside these edge metrics; none is called
    alignment fitness. The full input graphs participate in computation identity.
    """
    if type(reference) is not type(observed):
        raise TypeError("graphs must have the same graph type")
    expected, actual = _edge_frequencies(reference), _edge_frequencies(observed)
    request = GraphComparisonRequest(reference, observed)
    encoded = json.dumps(
        _identity_value(request),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    source_digest = "pix.object-graph-pair.v1:sha256:" + sha256(encoded).hexdigest()
    if reference.spec != observed.spec:
        return _result(
            "pix.object_centric.compare_object_graphs",
            None,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "incompatible_graph_profiles",
                    "Graph definitions, ordering and frequency profiles must match",
                ),
            ),
            source_digest=source_digest,
        )
    expected_keys, actual_keys = set(expected), set(actual)
    shared = len(expected_keys & actual_keys)
    union = expected_keys | actual_keys
    expected_mass, actual_mass = sum(expected.values()), sum(actual.values())
    shared_mass = sum(min(expected.get(key, 0), actual.get(key, 0)) for key in union)
    value = GraphComparison(
        len(expected),
        len(actual),
        shared,
        tuple(sorted(expected_keys - actual_keys)),
        tuple(sorted(actual_keys - expected_keys)),
        ExactRatio(shared, len(expected)),
        ExactRatio(shared, len(actual)),
        ExactRatio(shared, len(union)),
        expected_mass,
        actual_mass,
        shared_mass,
        ExactRatio(shared_mass, expected_mass),
        ExactRatio(shared_mass, actual_mass),
        ExactRatio(shared_mass, expected_mass + actual_mass - shared_mass),
        sum(abs(expected.get(key, 0) - actual.get(key, 0)) for key in union),
    )
    return _result(
        "pix.object_centric.compare_object_graphs",
        None,
        request,
        ComputeStatus.COMPUTED,
        value,
        source_digest=source_digest,
    )


RESULT_SCHEMAS = {
    "pix.object_centric.discover_object_graph": (
        "object-relation-graph",
        ObjectGraphSpec,
        ObjectGraph,
    ),
    "pix.object_centric.discover_etot": ("etot", ETOTSpec, ETOTGraph),
    "pix.object_centric.discover_otg": ("otg", OTGSpec, OTGGraph),
    "pix.object_centric.object_attributes_as_of": (
        "object-attribute-snapshot",
        AttributeAsOfSpec,
        AttributeSnapshot,
    ),
    "pix.object_centric.query_object_relations": (
        "object-relations",
        ObjectRelationSpec,
        ObjectRelations,
    ),
    "pix.object_centric.compare_object_graphs": (
        "object-graph-comparison",
        GraphComparisonRequest,
        GraphComparison,
    ),
}

__all__ = [
    "ObjectGraphSpec",
    "ObjectGraphNode",
    "ObjectGraphEdge",
    "ObjectGraph",
    "discover_object_graph",
    "ETOTSpec",
    "ETOTEdge",
    "ETOTGraph",
    "discover_etot",
    "OTGSpec",
    "OTGEdge",
    "OTGGraph",
    "discover_otg",
    "AttributeAsOfSpec",
    "OCELScalar",
    "AttributeAsOfValue",
    "AttributeSnapshot",
    "object_attributes_as_of",
    "ObjectRelationSpec",
    "ObjectRelations",
    "query_object_relations",
    "ExactRatio",
    "GraphComparisonRequest",
    "GraphComparison",
    "compare_object_graphs",
]
