"""Maximal ordinary P/T decomposition with explicit synchronization boundaries.

Places and arcs have exactly one owner. Silent transitions and every group of
transitions with a repeated activity label must remain inside one component.
Only globally unique visible transitions can occur in several components;
their replicas retain the original transition ID and must fire together.

This is the finest decomposition under Definition 17 of van der Aalst,
"Decomposing Petri nets for process mining: A generic approach", 2013,
https://www.vdaalst.com/publications/p721.pdf. We compute the equivalence
closure of the required ownership constraints, rather than split a graph at
arbitrary edges. The PM4Py 2.7.23.8 decomposition utility was inspected for
scope; no reference library or graph dependency is used here. Isolated nodes
are retained as a documented PIX extension to the paper's no-isolates scope.

Recomposition proves exact IDs, labels, incidence and accepting markings.
It is not a soundness certificate, an independent shuffle decomposition, or
an implementation of decomposed alignment/recomposition search. Weighted
arcs and other executable model classes are explicitly outside this profile.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _immutable,
)

OPERATOR_ID = "pix.case_centric.maximal_decompose_model"
RECOMPOSE_OPERATOR_ID = "pix.case_centric.recompose_maximal_decomposition"
PROFILE = "pix.ordinary_pt.unique_visible_boundary_maximal.v1"
COMPOSITION = "synchronize_by_original_transition_id"


@dataclass(frozen=True, slots=True)
class MaximalDecompositionSpec:
    """Input size bounds for partition construction, after model validation."""

    max_nodes: int = 200_000
    max_arcs: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.MaximalDecompositionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("max_nodes", "max_arcs"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class MaximalDecompositionRequest:
    model_digest: str | None
    parameters: MaximalDecompositionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.MaximalDecompositionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DecompositionComponent:
    component_id: str
    model: PetriNet
    internal_transition_ids: tuple[str, ...]
    boundary_transition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SharedTransition:
    transition_id: str
    activity: str
    component_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArcOwnership:
    arc: Arc
    component_id: str


@dataclass(frozen=True, slots=True)
class DecompositionCertificate:
    source_model_digest: str
    recomposed_model_digest: str
    source_initial_marking: Marking
    source_final_marking: Marking
    recomposed_initial_marking: Marking
    recomposed_final_marking: Marking
    identical_structure: bool
    identical_markings: bool


@dataclass(frozen=True, slots=True)
class MaximalModelDecomposition:
    profile: str
    source_model_digest: str
    components: tuple[DecompositionComponent, ...]
    shared_transitions: tuple[SharedTransition, ...]
    place_ownership: tuple[tuple[str, str], ...]
    arc_ownership: tuple[ArcOwnership, ...]
    certificate: DecompositionCertificate
    composition: str = COMPOSITION
    maximality: str = "finest_under_unique_visible_boundary_constraints"
    reference_equivalence: str = "unverified"


@dataclass(frozen=True, slots=True)
class MaximalRecompositionRequest:
    decomposition: MaximalModelDecomposition | None
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.MaximalRecompositionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


def _checked_net(net):
    """Reconstruct native records, rejecting unsupported/forged model classes."""
    if type(net) is not PetriNet:
        raise TypeError("Only the native ordinary PetriNet class is supported")
    for values, cls in (
        (net.places, Place),
        (net.transitions, Transition),
        (net.arcs, Arc),
    ):
        if not isinstance(values, tuple) or any(type(v) is not cls for v in values):
            raise TypeError("PetriNet must contain native immutable records")
    return PetriNet(
        tuple(Place(p.id) for p in net.places),
        tuple(Transition(t.id, t.activity) for t in net.transitions),
        tuple(Arc(a.source, a.target, a.weight) for a in net.arcs),
        Marking(net.initial_marking.tokens),
        Marking(net.final_marking.tokens),
    )


def _partition(net):
    """Least equivalence relation satisfying non-boundary ownership rules."""
    label_ids = defaultdict(list)
    for transition in net.transitions:
        if transition.activity is not None:
            label_ids[transition.activity].append(transition.id)
    internal = {
        t.id
        for t in net.transitions
        if t.activity is None or len(label_ids[t.activity]) > 1
    }
    place_ids = {p.id for p in net.places}
    incident = {a.source for a in net.arcs} | {a.target for a in net.arcs}
    # Unique-visible isolated transitions have no place-owned component. Each
    # therefore receives its own atom, preserving free firing and its label.
    atoms = (
        place_ids | internal | {t.id for t in net.transitions if t.id not in incident}
    )
    parents = {atom: atom for atom in atoms}
    ranks = dict.fromkeys(atoms, 0)

    def root(atom):
        while parents[atom] != atom:
            parents[atom] = parents[parents[atom]]
            atom = parents[atom]
        return atom

    def union(left, right):
        left, right = root(left), root(right)
        if left == right:
            return
        if ranks[left] < ranks[right]:
            left, right = right, left
        parents[right] = left
        if ranks[left] == ranks[right]:
            ranks[left] += 1

    for ids in label_ids.values():
        if len(ids) > 1:
            for transition_id in ids[1:]:
                union(ids[0], transition_id)
    for arc in net.arcs:
        if arc.source in internal or arc.target in internal:
            union(arc.source, arc.target)
    groups = defaultdict(list)
    for atom in sorted(atoms):
        groups[root(atom)].append(atom)
    groups = sorted(tuple(group) for group in groups.values())
    owners = {
        node: f"component-{index + 1}"
        for index, group in enumerate(groups)
        for node in group
    }
    transitions = {t.id: t for t in net.transitions}
    component_places = defaultdict(list)
    component_transitions = defaultdict(set)
    component_arcs = defaultdict(list)
    component_initial = defaultdict(list)
    component_final = defaultdict(list)
    for place in net.places:
        component_places[owners[place.id]].append(place)
    for row in net.initial_marking.tokens:
        component_initial[owners[row[0]]].append(row)
    for row in net.final_marking.tokens:
        component_final[owners[row[0]]].append(row)
    for transition in net.transitions:
        if transition.id in owners:
            component_transitions[owners[transition.id]].add(transition.id)
    arc_ownership = []
    for arc in net.arcs:
        place = arc.source if arc.source in place_ids else arc.target
        transition = arc.target if arc.source in place_ids else arc.source
        owner = owners[place]
        component_arcs[owner].append(arc)
        component_transitions[owner].add(transition)
        arc_ownership.append(ArcOwnership(arc, owner))
    members = defaultdict(list)
    component_ids = tuple(f"component-{index + 1}" for index in range(len(groups)))
    for component_id in component_ids:
        for transition_id in sorted(component_transitions[component_id]):
            members[transition_id].append(component_id)
    shared = tuple(
        SharedTransition(t.id, t.activity, tuple(members[t.id]))
        for t in net.transitions
        if len(members[t.id]) > 1
    )
    components = []
    for component_id in component_ids:
        local_places = tuple(component_places[component_id])
        local_transition_ids = sorted(component_transitions[component_id])
        model = PetriNet(
            local_places,
            tuple(transitions[t] for t in local_transition_ids),
            tuple(component_arcs[component_id]),
            Marking(tuple(component_initial[component_id])),
            Marking(tuple(component_final[component_id])),
        )
        components.append(
            DecompositionComponent(
                component_id,
                model,
                tuple(t for t in local_transition_ids if len(members[t]) == 1),
                tuple(t for t in local_transition_ids if len(members[t]) > 1),
            )
        )
    return (
        tuple(components),
        shared,
        tuple((p.id, owners[p.id]) for p in net.places),
        tuple(arc_ownership),
    )


def _assemble(components):
    places, transitions, arcs, initial, final = {}, {}, {}, {}, {}
    seen_component_ids = set()
    membership = defaultdict(set)
    for component in components:
        if component.component_id in seen_component_ids:
            raise ValueError("Duplicate component ID")
        seen_component_ids.add(component.component_id)
        net = _checked_net(component.model)
        for place in net.places:
            if place.id in places:
                raise ValueError("Places must have exactly one component owner")
            places[place.id] = place
        for transition in net.transitions:
            if (
                transition.id in transitions
                and transitions[transition.id] != transition
            ):
                raise ValueError(
                    "Transition replicas have inconsistent activity labels"
                )
            transitions[transition.id] = transition
            membership[transition.id].add(component.component_id)
        for arc in net.arcs:
            key = (arc.source, arc.target)
            if key in arcs:
                raise ValueError("Arcs must have exactly one component owner")
            if arc.weight != 1:
                raise ValueError("Weighted arcs are outside this profile")
            arcs[key] = arc
        initial.update(net.initial_marking.tokens)
        final.update(net.final_marking.tokens)
    label_counts = Counter(
        t.activity for t in transitions.values() if t.activity is not None
    )
    label_owners = defaultdict(set)
    for transition_id, owners in membership.items():
        label = transitions[transition_id].activity
        if label is not None:
            label_owners[label].update(owners)
        if len(owners) > 1 and (label is None or label_counts[label] != 1):
            raise ValueError("Only globally unique visible transitions may be shared")
    if any(
        label_counts[label] > 1 and len(owners) != 1
        for label, owners in label_owners.items()
    ):
        raise ValueError(
            "Transitions with duplicate activity labels must stay together"
        )
    return PetriNet(
        tuple(places.values()),
        tuple(transitions.values()),
        tuple(arcs.values()),
        Marking(tuple(initial.items())),
        Marking(tuple(final.items())),
    )


def maximal_decompose_model(
    net: PetriNet | ComputationResult,
    spec: MaximalDecompositionSpec = MaximalDecompositionSpec(),
) -> ComputationResult[MaximalModelDecomposition]:
    """Split connected ordinary nets at globally unique visible transitions.

    A parent may contain a PetriNet directly or in its ``model`` field.
    Partial input coverage remains partial; an unsupported/over-budget input
    returns no incomplete decomposition. Initial/final token multiplicities
    are retained, including multiple source and sink places.
    """
    if not isinstance(spec, MaximalDecompositionSpec):
        raise TypeError("spec must be MaximalDecompositionSpec")
    parent = net if isinstance(net, ComputationResult) else None
    if parent is None and not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet or a computation containing one")
    digest = None
    source = parent.source_digest if parent is not None else None
    inherited = parent.issues if parent is not None else ()
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )

    def result(status, value=None, issues=()):
        if (
            value is not None
            and parent is not None
            and parent.status is ComputeStatus.PARTIAL
        ):
            status = ComputeStatus.PARTIAL
        return _derived_result(
            OPERATOR_ID,
            source,
            MaximalDecompositionRequest(digest, spec),
            status,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None:
        if parent.value is None:
            return result(parent.status)
        net = (
            parent.value
            if isinstance(parent.value, PetriNet)
            else getattr(parent.value, "model", None)
        )
    if type(net) is not PetriNet:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "decomposition_model_class_unsupported",
                    "This profile accepts ordinary native PetriNet models only; object, data, inhibitor and reset semantics are not converted",
                ),
            ),
        )
    try:
        net = _checked_net(net)
        digest = model_digest(net)
    except (TypeError, ValueError, AttributeError, UnicodeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_decomposition_model", str(exc)),),
        )
    if parent is None:
        source = digest
    if any(arc.weight != 1 for arc in net.arcs):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "weighted_decomposition_unsupported",
                    "Maximal decomposition requires unit arcs; weights were not discarded",
                ),
            ),
        )
    if (
        len(net.places) + len(net.transitions) > spec.max_nodes
        or len(net.arcs) > spec.max_arcs
    ):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "decomposition_budget_exceeded",
                    "No incomplete partition was released",
                ),
            ),
        )
    components, shared, places, arcs = _partition(net)
    rebuilt = _assemble(components)
    certificate = DecompositionCertificate(
        digest,
        model_digest(rebuilt),
        net.initial_marking,
        net.final_marking,
        rebuilt.initial_marking,
        rebuilt.final_marking,
        (net.places, net.transitions, net.arcs)
        == (rebuilt.places, rebuilt.transitions, rebuilt.arcs),
        (net.initial_marking, net.final_marking)
        == (rebuilt.initial_marking, rebuilt.final_marking),
    )
    if rebuilt != net:
        raise RuntimeError("Internal decomposition certificate failed")
    return result(
        ComputeStatus.COMPUTED,
        MaximalModelDecomposition(
            PROFILE,
            digest,
            components,
            shared,
            places,
            arcs,
            certificate,
        ),
    )


def _validated_recomposition(value: MaximalModelDecomposition) -> PetriNet:
    """Check the certificate and its ownership witness against the union net."""
    rebuilt = _assemble(value.components)
    digest = model_digest(rebuilt)
    certificate = value.certificate
    if value.profile != PROFILE or value.composition != COMPOSITION:
        raise ValueError("Unsupported decomposition profile or composition")
    if value.maximality != "finest_under_unique_visible_boundary_constraints":
        raise ValueError("Unsupported maximality claim")
    if value.reference_equivalence != "unverified":
        raise ValueError("Reference equivalence has not been verified for this profile")
    if not (
        value.source_model_digest
        == certificate.source_model_digest
        == certificate.recomposed_model_digest
        == digest
    ):
        raise ValueError("Recomposition digest does not match the source certificate")
    if not certificate.identical_structure or not certificate.identical_markings:
        raise ValueError(
            "Certificate does not attest exact structural and marking identity"
        )
    if not (
        certificate.source_initial_marking
        == certificate.recomposed_initial_marking
        == rebuilt.initial_marking
    ):
        raise ValueError("Initial-marking witness differs from reconstructed tokens")
    if not (
        certificate.source_final_marking
        == certificate.recomposed_final_marking
        == rebuilt.final_marking
    ):
        raise ValueError("Final-marking witness differs from reconstructed tokens")
    expected = _partition(rebuilt)
    actual = (
        value.components,
        value.shared_transitions,
        value.place_ownership,
        value.arc_ownership,
    )
    if actual != expected:
        raise ValueError(
            "Ownership, boundary metadata or finest partition does not match the net"
        )
    return rebuilt


def recompose_maximal_decomposition(
    decomposition: MaximalModelDecomposition | ComputationResult,
) -> ComputationResult[PetriNet]:
    """Rebuild and validate the exact accepting net, unifying replica IDs.

    The certificate is checked against the reconstructed net, including all
    ownership metadata and the finest partition. It is never trusted solely
    because its boolean fields claim success. Digest checks detect changed
    content; they are not signatures or external source authenticity proofs.
    """
    parent = decomposition if isinstance(decomposition, ComputationResult) else None
    value = parent.value if parent is not None else decomposition
    if parent is None and not isinstance(value, MaximalModelDecomposition):
        raise TypeError("expected MaximalModelDecomposition or its computation result")
    source = parent.source_digest if parent is not None else value.source_model_digest
    if not isinstance(source, str) or not source:
        source = None
    inherited = parent.issues if parent is not None else ()
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    immutable_payload = isinstance(value, MaximalModelDecomposition) and _immutable(
        value
    )
    request = MaximalRecompositionRequest(value if immutable_payload else None)

    def result(status, model=None, issues=()):
        if (
            model is not None
            and parent is not None
            and parent.status is ComputeStatus.PARTIAL
        ):
            status = ComputeStatus.PARTIAL
        return _derived_result(
            RECOMPOSE_OPERATOR_ID,
            source,
            request,
            status,
            model,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None and value is None:
        return result(parent.status)
    if not immutable_payload:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_decomposition_payload",
                    "A finite immutable MaximalModelDecomposition is required",
                ),
            ),
        )
    try:
        rebuilt = _validated_recomposition(value)
    except (TypeError, ValueError, AttributeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_decomposition_certificate", str(exc)),),
        )
    return result(ComputeStatus.COMPUTED, rebuilt)


def validate_maximal_decomposition_result(result: ComputationResult) -> None:
    """Validate successful persisted witnesses and request/output consistency.

    Failure results may retain rejected input in the request. The partition
    witness is checked once for a nonempty result: matching union digests alone
    cannot distinguish a finest partition from a coarser, valid decomposition.
    This verifies internal consistency, not external source authenticity.
    """
    if result.value is None:
        return
    if result.operator_id == OPERATOR_ID:
        if (
            type(result.spec) is not MaximalDecompositionRequest
            or type(result.value) is not MaximalModelDecomposition
        ):
            raise TypeError(
                "Decomposition result has an incompatible request or payload"
            )
        if result.spec.model_digest != result.value.source_model_digest:
            raise ValueError("Decomposition request and payload model digests disagree")
        model = _validated_recomposition(result.value)
        if (
            len(model.places) + len(model.transitions)
            > result.spec.parameters.max_nodes
            or len(model.arcs) > result.spec.parameters.max_arcs
        ):
            raise ValueError("Decomposition witness exceeds its requested size bounds")
    elif result.operator_id == RECOMPOSE_OPERATOR_ID:
        if (
            type(result.spec) is not MaximalRecompositionRequest
            or type(result.spec.decomposition) is not MaximalModelDecomposition
        ):
            raise TypeError("Recomposition result requires its decomposition witness")
        expected = _validated_recomposition(result.spec.decomposition)
        if type(result.value) is not PetriNet or result.value != expected:
            raise ValueError(
                "Recomposition payload disagrees with its requested witness"
            )
    else:
        raise ValueError("Unsupported maximal-decomposition result operator")


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "case-maximal-model-decomposition",
        MaximalDecompositionRequest,
        MaximalModelDecomposition,
    ),
    RECOMPOSE_OPERATOR_ID: (
        "case-maximal-model-recomposition",
        MaximalRecompositionRequest,
        PetriNet,
    ),
}


__all__ = [
    "ArcOwnership",
    "DecompositionCertificate",
    "DecompositionComponent",
    "MaximalDecompositionRequest",
    "MaximalDecompositionSpec",
    "MaximalModelDecomposition",
    "MaximalRecompositionRequest",
    "SharedTransition",
    "maximal_decompose_model",
    "recompose_maximal_decomposition",
]
