"""Adapt native executable models without inferring any event-log statistics."""

from __future__ import annotations

import hashlib
import json

from pix.compute.model_semantics import model_digest
from pix.contracts.graph import ModelGraphDocument, ModelGraphEdge, ModelGraphNode
from pix.contracts.models import ObjectCentricPetriNet, PetriNet
from pix.models import ModelArtifact


def _identity(kind: str, *parts: str) -> str:
    payload = json.dumps([kind, *parts], ensure_ascii=False, separators=(",", ":"))
    return kind + "-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_model_graph(
    model: PetriNet | ObjectCentricPetriNet | ModelArtifact,
    *,
    title: str = "PIX process model",
) -> ModelGraphDocument:
    """Retain node identity, weights, markings, cardinalities and provenance.

    A bare model has unspecified origin. Passing a ModelArtifact preserves its
    declaration; a process-tree artifact is not a supported executable net.
    Equal visible activity labels never merge distinct model transitions.
    """
    if isinstance(model, ModelArtifact):
        net = model.model
        origin = model.origin
        source_computation_id = model.source_computation_id
    else:
        net = model
        origin = "unspecified"
        source_computation_id = None
    if not isinstance(net, (PetriNet, ObjectCentricPetriNet)):
        raise TypeError("model viewer supports native Petri nets and OCPNs")
    object_centric = isinstance(net, ObjectCentricPetriNet)
    nodes: list[ModelGraphNode] = []
    ids = {
        item.id: _identity("model-node", item.id)
        for item in (*net.places, *net.transitions)
    }
    if object_centric:
        initial: dict[str, list[str]] = {place.id: [] for place in net.places}
        final: dict[str, list[str]] = {place.id: [] for place in net.places}
        for token in net.initial_marking.tokens:
            initial[token.place_id].append(token.object_id)
        for token in net.final_marking.tokens:
            final[token.place_id].append(token.object_id)
        for place in net.places:
            nodes.append(
                ModelGraphNode(
                    ids[place.id],
                    place.id,
                    "place",
                    place.id,
                    place.object_type,
                    len(initial[place.id]),
                    len(final[place.id]),
                    tuple(initial[place.id]),
                    tuple(final[place.id]),
                )
            )
    else:
        initial_counts = dict(net.initial_marking.tokens)
        final_counts = dict(net.final_marking.tokens)
        for place in net.places:
            nodes.append(
                ModelGraphNode(
                    ids[place.id],
                    place.id,
                    "place",
                    place.id,
                    initial_count=initial_counts.get(place.id, 0),
                    final_count=final_counts.get(place.id, 0),
                )
            )
    for transition in net.transitions:
        nodes.append(
            ModelGraphNode(
                ids[transition.id],
                "τ" if transition.activity is None else transition.activity,
                "silent" if transition.activity is None else "transition",
                transition.id,
            )
        )
    edges: list[ModelGraphEdge] = []
    place_types = (
        {place.id: place.object_type for place in net.places} if object_centric else {}
    )
    for arc in net.arcs:
        edges.append(
            ModelGraphEdge(
                id=_identity("model-arc", arc.source, arc.target),
                source=ids[arc.source],
                target=ids[arc.target],
                object_type=place_types.get(arc.source, place_types.get(arc.target)),
                weight=1 if object_centric else arc.weight,
                variable=arc.variable if object_centric else False,
                min_objects=arc.min_objects if object_centric else 1,
                max_objects=arc.max_objects if object_centric else 1,
            )
        )
    notes = [
        f"Model origin: {origin}. This is a declared provenance, not a proof of discovery.",
        "This graph renders the supplied executable model. It does not discover "
        "a model from the current event log or assert its fitness or soundness.",
        "Marking counts represent tokens; arc weights and object-cardinality "
        "bounds are model semantics, not observed event frequencies.",
        "Transition identity is its model node ID; equal activity labels remain distinct.",
    ]
    if source_computation_id is not None:
        notes.append(f"Declared discovery computation: {source_computation_id}.")
    if object_centric:
        notes.extend(
            (
                "OCPN bindings select from the explicit finite object universe; "
                "they cannot generate new object IDs. Declared idle objects are retained.",
                "Every incidence of one transition/object type uses one shared object "
                "set and cardinality policy. Variable arcs specify allowed cardinality.",
                "Repeated object tokens at a place are retained as multiset multiplicity.",
            )
        )
    return ModelGraphDocument(
        kind="ocpn" if object_centric else "petri_net",
        model_digest=model_digest(net),
        origin=origin,
        source_computation_id=source_computation_id,
        nodes=tuple(sorted(nodes, key=lambda node: node.id)),
        edges=tuple(sorted(edges, key=lambda edge: edge.id)),
        object_types=tuple(
            sorted(set(place_types.values()) | {kind for _, kind in net.objects})
        )
        if object_centric
        else (),
        objects=net.objects if object_centric else (),
        title=title,
        notes=tuple(notes),
    )


__all__ = ("build_model_graph",)
