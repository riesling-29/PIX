"""Renderer-independent, immutable evidence for read-only process graphs.

Coordinates, colors and visibility are view state and deliberately absent here.
Identifiers are separate from labels; parallel object-type edges remain separate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


def _text(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid Unicode") from exc


def _tuple(value: tuple, item_type: type, name: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, item_type) for item in value
    ):
        raise TypeError(f"{name} must be a tuple of {item_type.__name__}")


def _strings(value: tuple[str, ...], name: str) -> None:
    _tuple(value, str, name)
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must not contain duplicates")


@dataclass(frozen=True, slots=True)
class GraphCounts:
    """Three distinct cardinalities over event-event-object evidence."""

    event_pairs: int
    unique_objects: int
    occurrences: int

    def __post_init__(self) -> None:
        for name in ("event_pairs", "unique_objects", "occurrences"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class GraphEvidence:
    source_event_id: str
    target_event_id: str
    object_id: str
    source_qualifiers: tuple[str, ...] = ()
    target_qualifiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("source_event_id", "target_event_id", "object_id"):
            _text(getattr(self, name), name)
        _strings(self.source_qualifiers, "source_qualifiers")
        _strings(self.target_qualifiers, "target_qualifiers")


@dataclass(frozen=True, slots=True)
class GraphNode:
    id: str
    label: str
    event_ids: tuple[str, ...]
    object_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.id, "id")
        _text(self.label, "label")
        if not self.id:
            raise ValueError("node id must not be empty")
        _strings(self.event_ids, "event_ids")
        _strings(self.object_ids, "object_ids")


@dataclass(frozen=True, slots=True)
class GraphEdge:
    id: str
    source: str
    target: str
    object_type: str
    counts: GraphCounts
    evidence: tuple[GraphEvidence, ...]

    def __post_init__(self) -> None:
        for name in ("id", "source", "target", "object_type"):
            _text(getattr(self, name), name)
        if not self.id:
            raise ValueError("edge id must not be empty")
        if not isinstance(self.counts, GraphCounts):
            raise TypeError("counts must be GraphCounts")
        _tuple(self.evidence, GraphEvidence, "evidence")
        triples = {
            (item.source_event_id, item.target_event_id, item.object_id)
            for item in self.evidence
        }
        if len(triples) != len(self.evidence):
            raise ValueError(
                "edge evidence must have unique event-event-object triples"
            )
        expected = GraphCounts(
            len({(source, target) for source, target, _ in triples}),
            len({obj for _, _, obj in triples}),
            len(triples),
        )
        if self.counts != expected or not triples:
            raise ValueError("edge counts must match nonempty evidence")


@dataclass(frozen=True, slots=True)
class GraphDocument:
    """A graph of computed directly-follows relations, never a normative model."""

    kind: Literal["dfg", "ocdfg"]
    source_digest: str
    computation_id: str
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    object_types: tuple[str, ...]
    title: str = "PIX process graph"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ("dfg", "ocdfg"):
            raise ValueError("kind must be 'dfg' or 'ocdfg'")
        for name in ("source_digest", "computation_id", "title"):
            _text(getattr(self, name), name)
        if not self.source_digest or not self.computation_id:
            raise ValueError("source and computation identifiers are required")
        _tuple(self.nodes, GraphNode, "nodes")
        _tuple(self.edges, GraphEdge, "edges")
        _strings(self.object_types, "object_types")
        _strings(self.notes, "notes")
        node_map = {node.id: node for node in self.nodes}
        if len(node_map) != len(self.nodes):
            raise ValueError("node identifiers must be unique")
        edge_ids = {edge.id for edge in self.edges}
        if len(edge_ids) != len(self.edges) or edge_ids.intersection(node_map):
            raise ValueError("edge identifiers must be unique and distinct from nodes")
        node_events = {node.id: set(node.event_ids) for node in self.nodes}
        node_objects = {node.id: set(node.object_ids) for node in self.nodes}
        for edge in self.edges:
            if edge.source not in node_map or edge.target not in node_map:
                raise ValueError("edge endpoints must reference graph nodes")
            if edge.object_type not in self.object_types:
                raise ValueError("edge object type must be declared")
            for item in edge.evidence:
                if (
                    item.source_event_id not in node_events[edge.source]
                    or item.target_event_id not in node_events[edge.target]
                    or item.object_id not in node_objects[edge.source]
                    or item.object_id not in node_objects[edge.target]
                ):
                    raise ValueError("edge evidence must reference its nodes' sources")


__all__ = (
    "GraphCounts",
    "GraphDocument",
    "GraphEdge",
    "GraphEvidence",
    "GraphNode",
)


def _model_text(value: str, name: str) -> None:
    _text(value, name)
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _model_count(value: int, name: str, *, minimum: int = 0) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _object_tokens(value: tuple[str, ...], name: str) -> None:
    # A marking is a multiset: repeated object IDs are meaningful here.
    _tuple(value, str, name)
    for item in value:
        _model_text(item, name)


@dataclass(frozen=True, slots=True)
class ModelGraphNode:
    """Model identity and marking evidence, without observed log statistics."""

    id: str
    label: str
    kind: Literal["place", "transition", "silent"]
    model_node_id: str
    object_type: str | None = None
    initial_count: int = 0
    final_count: int = 0
    initial_objects: tuple[str, ...] = ()
    final_objects: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _model_text(self.id, "node id")
        _model_text(self.model_node_id, "model_node_id")
        _text(self.label, "label")
        if self.kind not in ("place", "transition", "silent"):
            raise ValueError("unsupported model node kind")
        if self.kind == "transition" and not self.label.strip():
            raise ValueError("visible transition label must not be blank")
        if self.object_type is not None:
            _model_text(self.object_type, "object_type")
        _model_count(self.initial_count, "initial_count")
        _model_count(self.final_count, "final_count")
        _object_tokens(self.initial_objects, "initial_objects")
        _object_tokens(self.final_objects, "final_objects")
        if self.kind != "place" and (
            self.object_type is not None
            or self.initial_count
            or self.final_count
            or self.initial_objects
            or self.final_objects
        ):
            raise ValueError("only places have object types or marking tokens")
        if self.object_type is None and (self.initial_objects or self.final_objects):
            raise ValueError("object tokens require a typed place")
        if self.object_type is not None and (
            self.initial_count != len(self.initial_objects)
            or self.final_count != len(self.final_objects)
        ):
            raise ValueError("typed-place counts must match object token multiplicity")


@dataclass(frozen=True, slots=True)
class ModelGraphEdge:
    """Arc weight or object cardinality, never a frequency from an event log."""

    id: str
    source: str
    target: str
    object_type: str | None = None
    weight: int = 1
    variable: bool = False
    min_objects: int = 1
    max_objects: int | None = 1

    def __post_init__(self) -> None:
        for name in ("id", "source", "target"):
            _model_text(getattr(self, name), name)
        if self.object_type is not None:
            _model_text(self.object_type, "object_type")
        _model_count(self.weight, "weight", minimum=1)
        if type(self.variable) is not bool:
            raise TypeError("variable must be bool")
        _model_count(self.min_objects, "min_objects")
        if self.max_objects is not None:
            _model_count(self.max_objects, "max_objects")
            if self.max_objects < self.min_objects:
                raise ValueError("maximum cardinality is smaller than minimum")
        if not self.variable and (self.min_objects != 1 or self.max_objects != 1):
            raise ValueError("fixed arcs require neutral or fixed cardinality 1..1")
        if self.object_type is None and self.variable:
            raise ValueError("object cardinality requires an object type")
        if self.object_type is not None and self.weight != 1:
            raise ValueError("object-centric arcs use unit weight")


@dataclass(frozen=True, slots=True)
class ModelGraphDocument:
    """An executable model view, distinct from a directly-follows graph.

    Origin is a caller declaration, not proof that discovery occurred. OCPN
    objects are the complete finite execution universe, including idle objects.
    """

    kind: Literal["petri_net", "ocpn"]
    model_digest: str
    origin: Literal["provided", "discovered", "unspecified"]
    nodes: tuple[ModelGraphNode, ...]
    edges: tuple[ModelGraphEdge, ...]
    object_types: tuple[str, ...]
    objects: tuple[tuple[str, str], ...] = ()
    source_computation_id: str | None = None
    title: str = "PIX process model"
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ("petri_net", "ocpn"):
            raise ValueError("unsupported model graph kind")
        _model_text(self.model_digest, "model_digest")
        _text(self.title, "title")
        if self.origin not in ("provided", "discovered", "unspecified"):
            raise ValueError("unsupported model origin")
        if self.origin == "discovered":
            _model_text(self.source_computation_id, "source_computation_id")
        elif self.source_computation_id is not None:
            raise ValueError("only discovered models have a source computation ID")
        _tuple(self.nodes, ModelGraphNode, "nodes")
        _tuple(self.edges, ModelGraphEdge, "edges")
        _strings(self.object_types, "object_types")
        for object_type in self.object_types:
            _model_text(object_type, "object_type")
        _strings(self.notes, "notes")
        _tuple(self.objects, tuple, "objects")
        universe: dict[str, str] = {}
        for entry in self.objects:
            if len(entry) != 2:
                raise ValueError("objects entries must be (object_id, object_type)")
            object_id, object_type = entry
            _model_text(object_id, "object_id")
            _model_text(object_type, "object_type")
            if object_id in universe:
                raise ValueError("object IDs must be unique")
            if object_type not in self.object_types:
                raise ValueError("object universe type must be declared")
            universe[object_id] = object_type
        if self.kind == "petri_net" and (self.object_types or self.objects):
            raise ValueError("classical Petri nets have no object universe")
        node_map = {node.id: node for node in self.nodes}
        if len(node_map) != len(self.nodes):
            raise ValueError("model graph node IDs must be unique")
        if len({node.model_node_id for node in self.nodes}) != len(self.nodes):
            raise ValueError("model node IDs must be unique")
        for node in self.nodes:
            if self.kind == "petri_net" and node.object_type is not None:
                raise ValueError("classical Petri net places are untyped")
            if self.kind == "ocpn" and node.kind == "place":
                if node.object_type not in self.object_types:
                    raise ValueError("OCPN place type must be declared")
                for object_id in node.initial_objects + node.final_objects:
                    if universe.get(object_id) != node.object_type:
                        raise ValueError("marking object must match its place type")
        edge_ids = {edge.id for edge in self.edges}
        if len(edge_ids) != len(self.edges) or edge_ids.intersection(node_map):
            raise ValueError("edge IDs must be unique and distinct from nodes")
        incidences: set[tuple[str, str]] = set()
        policies: dict[tuple[str, str], tuple[bool, int, int | None]] = {}
        for edge in self.edges:
            if edge.source not in node_map or edge.target not in node_map:
                raise ValueError("arc endpoints must reference model graph nodes")
            source, target = node_map[edge.source], node_map[edge.target]
            if (source.kind == "place") == (target.kind == "place"):
                raise ValueError("arc must connect a place and a transition")
            pair = edge.source, edge.target
            if pair in incidences:
                raise ValueError("duplicate arc incidence; use explicit multiplicity")
            incidences.add(pair)
            place = source if source.kind == "place" else target
            transition = target if source.kind == "place" else source
            if edge.object_type != place.object_type:
                raise ValueError("arc object type must match its place")
            if self.kind == "ocpn":
                key = transition.id, edge.object_type
                policy = edge.variable, edge.min_objects, edge.max_objects
                if key in policies and policies[key] != policy:
                    raise ValueError(
                        "transition/type arcs require one cardinality policy"
                    )
                policies[key] = policy


__all__ += ("ModelGraphDocument", "ModelGraphEdge", "ModelGraphNode")
