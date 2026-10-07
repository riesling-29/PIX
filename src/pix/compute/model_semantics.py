"""Native weighted Petri and concrete-object OCPN firing semantics.

OCPN consumption/production follows multiset bindings (Liss et al.,
Object-Centric Alignments, definitions 4--7):
https://www.vdaalst.com/publications/p1419.pdf
PIX's initial profile additionally exposes explicit variable-cardinality bounds
and limits OCPN incidences to unit arcs. No soundness result is implied.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict

from pix.contracts.models import (
    Binding,
    Marking,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
)


def _petri(net: PetriNet, marking: Marking) -> dict[str, int]:
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    net.validate_marking(marking)
    return dict(marking.tokens)


def _transition(net: PetriNet, transition_id: str) -> None:
    if not isinstance(transition_id, str):
        raise TypeError("transition_id must be a string")
    if not any(t.id == transition_id for t in net.transitions):
        raise ValueError(f"unknown transition: {transition_id}")


def is_enabled(net: PetriNet, marking: Marking, transition_id: str) -> bool:
    """Whether every input arc has its required token count."""
    counts = _petri(net, marking)
    _transition(net, transition_id)
    return all(
        counts.get(arc.source, 0) >= arc.weight
        for arc in net.arcs
        if arc.target == transition_id
    )


def enabled_transitions(net: PetriNet, marking: Marking) -> tuple[str, ...]:
    """All enabled transition IDs, including silent ones; no label merging."""
    counts = _petri(net, marking)
    return tuple(
        transition.id
        for transition in net.transitions
        if all(
            counts.get(arc.source, 0) >= arc.weight
            for arc in net.arcs
            if arc.target == transition.id
        )
    )


def fire(net: PetriNet, marking: Marking, transition_id: str) -> Marking:
    """Return M - input + output, or raise without altering the input."""
    counts = _petri(net, marking)
    if not is_enabled(net, marking, transition_id):
        raise ValueError(f"transition is not enabled: {transition_id}")
    for arc in net.arcs:
        if arc.target == transition_id:
            counts[arc.source] -= arc.weight
        elif arc.source == transition_id:
            counts[arc.target] = counts.get(arc.target, 0) + arc.weight
    return Marking(tuple((place, count) for place, count in counts.items() if count))


def is_final(net: PetriNet, marking: Marking) -> bool:
    """Exact accepting marking, including absence of residual tokens."""
    _petri(net, marking)
    return marking == net.final_marking


def _object_marking(
    net: ObjectCentricPetriNet, marking: ObjectMarking
) -> Counter[ObjectToken]:
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    net.validate_marking(marking)
    return Counter(marking.tokens)


def _binding_incidence(
    net: ObjectCentricPetriNet, binding: Binding
) -> tuple[Counter[ObjectToken], Counter[ObjectToken]] | None:
    if not isinstance(binding, Binding):
        raise TypeError("binding must be a Binding")
    transition = binding.transition_id
    if not any(t.id == transition for t in net.transitions):
        return None
    place_types = {place.id: place.object_type for place in net.places}
    object_types = dict(net.objects)
    bound = dict(binding.objects)
    arcs = tuple(arc for arc in net.arcs if transition in (arc.source, arc.target))
    required_types = {
        place_types[arc.source if arc.target == transition else arc.target]
        for arc in arcs
    }
    if set(bound) != required_types:
        return None
    for object_type, object_ids in binding.objects:
        if any(object_types.get(object_id) != object_type for object_id in object_ids):
            return None
    consumed: Counter[ObjectToken] = Counter()
    produced: Counter[ObjectToken] = Counter()
    for arc in arcs:
        incoming = arc.target == transition
        place_id = arc.source if incoming else arc.target
        object_ids = bound[place_types[place_id]]
        cardinality = len(object_ids)
        if cardinality < arc.min_objects or (
            arc.max_objects is not None and cardinality > arc.max_objects
        ):
            return None
        target = consumed if incoming else produced
        target.update(ObjectToken(place_id, object_id) for object_id in object_ids)
    return consumed, produced


def is_binding_enabled(
    net: ObjectCentricPetriNet, marking: ObjectMarking, binding: Binding
) -> bool:
    """Check exact object availability jointly across every input place.

    A well-typed but inadmissible binding returns False. A malformed external
    marking raises instead of being treated as an ordinary disabled binding.
    """
    counts = _object_marking(net, marking)
    incidence = _binding_incidence(net, binding)
    return incidence is not None and all(
        counts[token] >= count for token, count in incidence[0].items()
    )


def fire_binding(
    net: ObjectCentricPetriNet, marking: ObjectMarking, binding: Binding
) -> ObjectMarking:
    """Fire one explicit binding, preserving per-object token multiplicity."""
    counts = _object_marking(net, marking)
    incidence = _binding_incidence(net, binding)
    if incidence is None or any(
        counts[token] < count for token, count in incidence[0].items()
    ):
        raise ValueError("binding is not enabled")
    consumed, produced = incidence
    counts.subtract(consumed)
    counts.update(produced)
    return ObjectMarking(tuple(counts.elements()))


def is_object_final(net: ObjectCentricPetriNet, marking: ObjectMarking) -> bool:
    """Exact object final marking; extra/missing object tokens are significant."""
    _object_marking(net, marking)
    return marking == net.final_marking


def model_digest(net: PetriNet | ObjectCentricPetriNet) -> str:
    """Versioned semantic identity independent of collection input order.

    IDs, semantic activity labels, cardinalities, object universe and markings
    are part of identity. This is not a graph-isomorphism or language digest.
    """
    if not isinstance(net, (PetriNet, ObjectCentricPetriNet)):
        raise TypeError("net must be a supported native model")
    model_type = "petri-net" if isinstance(net, PetriNet) else "ocpn"
    payload = {
        "model_type": model_type,
        "schema_version": net.SCHEMA_VERSION,
        "semantics_version": "1.0.0",
        "model": asdict(net),
    }
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return f"pix.model.{model_type}.v1:sha256:{hashlib.sha256(encoded).hexdigest()}"


__all__ = [
    "enabled_transitions",
    "fire",
    "fire_binding",
    "is_binding_enabled",
    "is_enabled",
    "is_final",
    "is_object_final",
    "model_digest",
]
