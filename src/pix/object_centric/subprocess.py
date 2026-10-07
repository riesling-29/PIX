"""Typed, local OCPN subprocesses with an explicit synchronization boundary.

The selected nodes lie on directed *walks* from source to target in one object
type's incidence graph. Cycles remain; source == target selects its strongly
connected component, including the zero-length walk. This is a structural
profile, not evidence of executability, soundness or language equivalence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.compute.model_semantics import model_digest
from pix.contracts.analysis import _text
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    Transition,
    TypedPlace,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.object_centric.models import (
    ObjectHidingSpec,
    ObjectModelTransformation,
    ObjectProjectionSpec,
    ObjectReduction,
    ObjectReductionSpec,
    hide_ocpn,
    project_ocpn,
    reduce_ocpn,
)

_MEANING = "typed_directed_walk_subnet_not_execution_soundness_or_language_evidence"
_LOSSES = (
    "object_universe_restricted_to_selected_type",
    "cut_incidence_can_remove_synchronization_and_enable_additional_bindings",
    "restricted_markings_are_not_inferred_subprocess_entry_or_exit_conditions",
    "source_model_execution_soundness_and_language_are_not_preserved_claims",
)


def _tuple(value, kind, name):
    if not isinstance(value, tuple) or not all(isinstance(x, kind) for x in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _names(values, name):
    _tuple(values, str, name)
    for value in values:
        _text(value, name)
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")
    return tuple(sorted(values))


def _walk(start, adjacency):
    reached, pending = {start}, [start]
    while pending:
        current = pending.pop()
        following = adjacency.get(current, set()) - reached
        reached.update(following)
        pending.extend(following)
    return reached


@dataclass(frozen=True, slots=True)
class ObjectTypedSubprocessSpec:
    """Inclusive source/target node IDs, traversing only one object's type."""

    SPEC_TYPE: ClassVar[str] = "pix.object_typed_subprocess.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_type: str
    source_node_id: str
    target_node_id: str

    def __post_init__(self):
        for name in ("object_type", "source_node_id", "target_node_id"):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class SubprocessCutArc:
    """Original arc and typed endpoint records, before any projection/hiding."""

    arc: ObjectArc
    place: TypedPlace
    transition: Transition

    def __post_init__(self):
        if not isinstance(self.arc, ObjectArc) or not isinstance(
            self.place, TypedPlace
        ):
            raise TypeError("cut arc requires ObjectArc and TypedPlace")
        if not isinstance(self.transition, Transition):
            raise TypeError("cut arc requires Transition")
        if self.place.id == self.transition.id:
            raise ValueError("cut place and transition IDs must be disjoint")
        if {self.arc.source, self.arc.target} != {self.place.id, self.transition.id}:
            raise ValueError("cut arc endpoints differ from its endpoint records")


@dataclass(frozen=True, slots=True)
class SubprocessTransitionContext:
    transition_id: str
    original_object_types: tuple[str, ...]

    def __post_init__(self):
        _text(self.transition_id, "transition_id")
        normalized = _names(self.original_object_types, "original_object_types")
        if not normalized:
            raise ValueError("a selected transition must have typed incidence")
        object.__setattr__(self, "original_object_types", normalized)


@dataclass(frozen=True, slots=True)
class ObjectTypedSubprocess:
    """Exact restricted structure and original synchronization/marking ledger.

    ``model`` carries only restricted original markings and the entire declared
    object universe of the selected type. No boundary tokens are invented.
    Outside markings are retained in full, including token multiplicity.
    """

    source_model_digest: str
    spec: ObjectTypedSubprocessSpec
    reachable: bool
    model: ObjectCentricPetriNet
    transition_context: tuple[SubprocessTransitionContext, ...]
    incoming_cut_arcs: tuple[SubprocessCutArc, ...]
    outgoing_cut_arcs: tuple[SubprocessCutArc, ...]
    omitted_initial_marking: ObjectMarking
    omitted_final_marking: ObjectMarking
    omitted_objects: tuple[tuple[str, str], ...]
    meaning: str = _MEANING

    def __post_init__(self):
        _text(self.source_model_digest, "source_model_digest")
        if not isinstance(self.spec, ObjectTypedSubprocessSpec):
            raise TypeError("spec must be ObjectTypedSubprocessSpec")
        if not isinstance(self.reachable, bool):
            raise TypeError("reachable must be bool")
        if not isinstance(self.model, ObjectCentricPetriNet):
            raise TypeError("model must be ObjectCentricPetriNet")
        if self.meaning != _MEANING:
            raise ValueError("unsupported subprocess meaning")
        if any(p.object_type != self.spec.object_type for p in self.model.places):
            raise ValueError("subprocess places must have the selected object type")
        if any(kind != self.spec.object_type for _, kind in self.model.objects):
            raise ValueError("subprocess objects must have the selected object type")
        nodes = {p.id for p in self.model.places} | {
            t.id for t in self.model.transitions
        }
        if not self.reachable and nodes:
            raise ValueError("unreachable subprocess must have no nodes")
        if not self.reachable and self.spec.source_node_id == self.spec.target_node_id:
            raise ValueError("equal boundaries always have a zero-length walk")
        if self.reachable:
            if {self.spec.source_node_id, self.spec.target_node_id} - nodes:
                raise ValueError("reachable subprocess must include both boundaries")
            forward, reverse = defaultdict(set), defaultdict(set)
            for arc in self.model.arcs:
                forward[arc.source].add(arc.target)
                reverse[arc.target].add(arc.source)
            between = _walk(self.spec.source_node_id, forward) & _walk(
                self.spec.target_node_id, reverse
            )
            if between != nodes:
                raise ValueError("subprocess contains nodes outside its directed walks")
        _tuple(
            self.transition_context, SubprocessTransitionContext, "transition_context"
        )
        ids = [row.transition_id for row in self.transition_context]
        if len(ids) != len(set(ids)) or set(ids) != {
            t.id for t in self.model.transitions
        }:
            raise ValueError(
                "transition context must cover exactly selected transitions"
            )
        if any(
            self.spec.object_type not in row.original_object_types
            for row in self.transition_context
        ):
            raise ValueError("transition context must include the selected object type")
        object.__setattr__(
            self,
            "transition_context",
            tuple(sorted(self.transition_context, key=lambda row: row.transition_id)),
        )
        seen = set()
        contexts = {
            row.transition_id: row.original_object_types
            for row in self.transition_context
        }
        places = {p.id: p for p in self.model.places}
        transitions = {t.id: t for t in self.model.transitions}
        place_records, transition_records = dict(places), dict(transitions)
        original_arcs = list(self.model.arcs)
        for name, entering in (
            ("incoming_cut_arcs", True),
            ("outgoing_cut_arcs", False),
        ):
            rows = getattr(self, name)
            _tuple(rows, SubprocessCutArc, name)
            for row in rows:
                arc = row.arc
                endpoints = arc.source, arc.target
                if endpoints in seen:
                    raise ValueError("duplicate cut arc")
                seen.add(endpoints)
                if (arc.source in nodes, arc.target in nodes) != (
                    (False, True) if entering else (True, False)
                ):
                    raise ValueError(
                        "cut arc must cross the declared boundary direction"
                    )
                if (
                    row.place.id in transition_records
                    or row.transition.id in place_records
                ):
                    raise ValueError(
                        "place and transition IDs must remain disjoint across the boundary"
                    )
                if (
                    row.place.id in place_records
                    and row.place != place_records[row.place.id]
                ):
                    raise ValueError("conflicting original boundary place records")
                if (
                    row.transition.id in transition_records
                    and row.transition != transition_records[row.transition.id]
                ):
                    raise ValueError("conflicting original boundary transition records")
                place_records[row.place.id] = row.place
                transition_records[row.transition.id] = row.transition
                original_arcs.append(arc)
                if row.place.id in places and row.place != places[row.place.id]:
                    raise ValueError("cut place differs from the retained place")
                if row.transition.id in transitions:
                    if row.transition != transitions[row.transition.id]:
                        raise ValueError(
                            "cut transition differs from the retained transition"
                        )
                    if row.place.object_type not in contexts[row.transition.id]:
                        raise ValueError(
                            "cut type is absent from the transition context"
                        )
            object.__setattr__(
                self,
                name,
                tuple(sorted(rows, key=lambda row: (row.arc.source, row.arc.target))),
            )
        reconstructed_types, cardinalities = defaultdict(set), {}
        for arc in original_arcs:
            pid, tid = (
                (arc.source, arc.target)
                if arc.source in place_records
                else (arc.target, arc.source)
            )
            kind = place_records[pid].object_type
            reconstructed_types[tid].add(kind)
            policy = arc.variable, arc.min_objects, arc.max_objects
            key = tid, kind
            if key in cardinalities and cardinalities[key] != policy:
                raise ValueError(
                    "original transition/type cardinality must remain consistent across cuts"
                )
            cardinalities[key] = policy
        if any(
            set(kinds) != reconstructed_types[tid] for tid, kinds in contexts.items()
        ):
            raise ValueError(
                "transition context must match exactly retained and cut incidence types"
            )
        _tuple(self.omitted_objects, tuple, "omitted_objects")
        objects = dict(self.model.objects)
        for row in self.omitted_objects:
            if len(row) != 2:
                raise ValueError(
                    "omitted objects must be (object ID, object type) pairs"
                )
            _text(row[0], "omitted object ID")
            _text(row[1], "omitted object type")
            if row[0] in objects or row[1] == self.spec.object_type:
                raise ValueError(
                    "omitted object IDs must be unique and have unselected types"
                )
            objects[row[0]] = row[1]
        object.__setattr__(self, "omitted_objects", tuple(sorted(self.omitted_objects)))
        for name in ("omitted_initial_marking", "omitted_final_marking"):
            marking = getattr(self, name)
            if not isinstance(marking, ObjectMarking):
                raise TypeError(f"{name} must be ObjectMarking")
            if any(token.place_id in places for token in marking.tokens):
                raise ValueError("omitted markings must be outside the retained places")
            for token in marking.tokens:
                if token.place_id in transition_records:
                    raise ValueError(
                        "omitted markings cannot use a transition as a place"
                    )
                if token.object_id not in objects:
                    raise ValueError(
                        "omitted markings must reference original declared objects"
                    )
                if (
                    token.place_id in place_records
                    and place_records[token.place_id].object_type
                    != objects[token.object_id]
                ):
                    raise ValueError(
                        "omitted token type differs from its boundary place"
                    )

    @property
    def shared_transition_ids(self) -> tuple[str, ...]:
        return tuple(
            row.transition_id
            for row in self.transition_context
            if len(row.original_object_types) > 1
        )


def local_ocpn_subprocess(
    net: ObjectCentricPetriNet, spec: ObjectTypedSubprocessSpec
) -> ComputationResult[ObjectTypedSubprocess]:
    """Extract a type-specific inclusive between-subnet.

    Boundaries may be places of the selected type or transitions incident to
    that type. A route through another type never proves local reachability.
    Unreachable boundaries return a computed empty profile, not a failed search.
    Reachability traversal is O(nodes + arcs); output is canonically sorted.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectTypedSubprocessSpec
    ):
        raise TypeError("expected ObjectCentricPetriNet and ObjectTypedSubprocessSpec")
    places = {p.id: p for p in net.places}
    transitions = {t.id: t for t in net.transitions}
    typed_places = {p.id for p in net.places if p.object_type == spec.object_type}
    if spec.object_type not in {p.object_type for p in net.places} | {
        kind for _, kind in net.objects
    }:
        raise ValueError("unknown subprocess object type")
    forward, reverse, memberships = defaultdict(set), defaultdict(set), defaultdict(set)
    typed_nodes = set(typed_places)
    for arc in net.arcs:
        place_id, tid = (
            (arc.source, arc.target)
            if arc.source in places
            else (arc.target, arc.source)
        )
        memberships[tid].add(places[place_id].object_type)
        if place_id in typed_places:
            typed_nodes.add(tid)
            forward[arc.source].add(arc.target)
            reverse[arc.target].add(arc.source)
    if {spec.source_node_id, spec.target_node_id} - typed_nodes:
        raise ValueError(
            "subprocess boundaries must belong to the selected type incidence"
        )
    selected = _walk(spec.source_node_id, forward) & _walk(spec.target_node_id, reverse)
    reachable = spec.target_node_id in selected
    selected_places = typed_places & selected
    selected_transitions = transitions.keys() & selected

    def marking(source, keep):
        return ObjectMarking(
            tuple(
                token
                for token in source.tokens
                if (token.place_id in selected_places) == keep
            )
        )

    model = ObjectCentricPetriNet(
        tuple(p for p in net.places if p.id in selected_places),
        tuple(t for t in net.transitions if t.id in selected_transitions),
        tuple(a for a in net.arcs if a.source in selected and a.target in selected),
        marking(net.initial_marking, True),
        marking(net.final_marking, True),
        tuple(row for row in net.objects if row[1] == spec.object_type),
    )
    incoming, outgoing = [], []
    for arc in net.arcs:
        if (arc.source in selected) == (arc.target in selected):
            continue
        place_id, tid = (
            (arc.source, arc.target)
            if arc.source in places
            else (arc.target, arc.source)
        )
        cut = SubprocessCutArc(arc, places[place_id], transitions[tid])
        (incoming if arc.target in selected else outgoing).append(cut)
    value = ObjectTypedSubprocess(
        model_digest(net),
        spec,
        reachable,
        model,
        tuple(
            SubprocessTransitionContext(tid, tuple(sorted(memberships[tid])))
            for tid in sorted(selected_transitions)
        ),
        tuple(incoming),
        tuple(outgoing),
        marking(net.initial_marking, False),
        marking(net.final_marking, False),
        tuple(row for row in net.objects if row[1] != spec.object_type),
    )
    return _derived_result(
        "pix.object_centric.local_ocpn_subprocess",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        value,
    )


@dataclass(frozen=True, slots=True)
class ObjectSubprocessPipelineSpec:
    """Opt into projection, exact boundary restriction, then hiding/reduction."""

    SPEC_TYPE: ClassVar[str] = "pix.object_subprocess_pipeline.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    subprocess: ObjectTypedSubprocessSpec
    hiding: ObjectHidingSpec | None = None
    reduction: ObjectReductionSpec | None = None

    def __post_init__(self):
        for name, kind in (
            ("subprocess", ObjectTypedSubprocessSpec),
            ("hiding", ObjectHidingSpec),
            ("reduction", ObjectReductionSpec),
        ):
            value = getattr(self, name)
            if not isinstance(value, kind) and not (
                name != "subprocess" and value is None
            ):
                raise TypeError(
                    f"{name} must be {kind.__name__}"
                    + (" or None" if name != "subprocess" else "")
                )


@dataclass(frozen=True, slots=True)
class ObjectSubprocessTransformation:
    """Auditable stage outputs; guarantees apply locally, never to the source."""

    profile: ObjectTypedSubprocess
    spec: ObjectSubprocessPipelineSpec
    projection: ObjectModelTransformation
    boundary_removed_place_ids: tuple[str, ...]
    boundary_removed_transition_ids: tuple[str, ...]
    hiding: ObjectModelTransformation | None
    reduction: ObjectReduction | None
    model: ObjectCentricPetriNet
    semantic_losses: tuple[str, ...] = _LOSSES

    def __post_init__(self):
        if not isinstance(self.profile, ObjectTypedSubprocess) or not isinstance(
            self.projection, ObjectModelTransformation
        ):
            raise TypeError("expected typed subprocess and projection ledger")
        if not isinstance(self.spec, ObjectSubprocessPipelineSpec):
            raise TypeError("spec must be ObjectSubprocessPipelineSpec")
        if self.spec.subprocess != self.profile.spec:
            raise ValueError("pipeline selection differs from the retained profile")
        if (self.hiding is None) != (self.spec.hiding is None):
            raise ValueError("hiding stage must match the requested pipeline")
        if (self.reduction is None) != (self.spec.reduction is None):
            raise ValueError("reduction stage must match the requested pipeline")
        if self.hiding is not None and not isinstance(
            self.hiding, ObjectModelTransformation
        ):
            raise TypeError("hiding must be ObjectModelTransformation or None")
        if self.reduction is not None and not isinstance(
            self.reduction, ObjectReduction
        ):
            raise TypeError("reduction must be ObjectReduction or None")
        if not isinstance(self.model, ObjectCentricPetriNet):
            raise TypeError("model must be ObjectCentricPetriNet")
        removed = _names(self.boundary_removed_place_ids, "boundary_removed_place_ids")
        expected = tuple(
            sorted(
                {p.id for p in self.projection.model.places}
                - {p.id for p in self.profile.model.places}
            )
        )
        if removed != expected:
            raise ValueError("boundary restriction ledger differs from projection")
        object.__setattr__(self, "boundary_removed_place_ids", removed)
        removed_transitions = _names(
            self.boundary_removed_transition_ids, "boundary_removed_transition_ids"
        )
        expected_transitions = tuple(
            sorted(
                {t.id for t in self.projection.model.transitions}
                - {t.id for t in self.profile.model.transitions}
            )
        )
        if removed_transitions != expected_transitions:
            raise ValueError("boundary transition ledger differs from projection")
        object.__setattr__(self, "boundary_removed_transition_ids", removed_transitions)
        retained_places = {p.id for p in self.profile.model.places}
        retained_transitions = {t.id for t in self.profile.model.transitions}
        retained_nodes = retained_places | retained_transitions
        projected = self.projection.model
        restricted = ObjectCentricPetriNet(
            tuple(p for p in projected.places if p.id in retained_places),
            tuple(t for t in projected.transitions if t.id in retained_transitions),
            tuple(
                a
                for a in projected.arcs
                if a.source in retained_nodes and a.target in retained_nodes
            ),
            ObjectMarking(
                tuple(
                    t
                    for t in projected.initial_marking.tokens
                    if t.place_id in retained_places
                )
            ),
            ObjectMarking(
                tuple(
                    t
                    for t in projected.final_marking.tokens
                    if t.place_id in retained_places
                )
            ),
            projected.objects,
        )
        if restricted != self.profile.model:
            raise ValueError(
                "subprocess model must restrict the type projection exactly"
            )
        current = self.profile.model
        if self.hiding is not None:
            expected_hidden = hide_ocpn(current, self.spec.hiding).value
            if self.hiding != expected_hidden:
                raise ValueError(
                    "hiding ledger does not match the boundary-restricted model"
                )
            current = self.hiding.model
        if self.reduction is not None:
            if self.reduction != reduce_ocpn(current, self.spec.reduction).value:
                raise ValueError(
                    "reduction ledger differs from the requested safe reduction"
                )
            current = self.reduction.model
        if self.model != current:
            raise ValueError("final model differs from the final pipeline stage")
        expected_losses = _LOSSES
        if self.hiding is not None and any(
            transition.activity is not None
            and transition.id in self.hiding.hidden_transition_ids
            for transition in self.profile.model.transitions
        ):
            expected_losses += ("selected_visible_activity_labels_are_hidden",)
        if self.reduction is not None and self.reduction.steps:
            expected_losses += self.reduction.not_preserved
        if self.semantic_losses != expected_losses:
            raise ValueError("semantic losses do not match the executed pipeline")


def transform_ocpn_subprocess(
    net: ObjectCentricPetriNet, spec: ObjectSubprocessPipelineSpec
) -> ComputationResult[ObjectSubprocessTransformation]:
    """Explicitly project, restrict the boundary, optionally hide and reduce.

    The type projection retains all places of the type; this pipeline then
    records removed places/transitions to obtain the exact directed-walk subnet.
    Original identity/synchronization evidence always remains in ``profile``.
    Reduction guarantees, if applicable, concern the already projected model.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectSubprocessPipelineSpec
    ):
        raise TypeError(
            "expected ObjectCentricPetriNet and ObjectSubprocessPipelineSpec"
        )
    profile_result = local_ocpn_subprocess(net, spec.subprocess)
    profile = profile_result.value
    projection_result = project_ocpn(
        net,
        ObjectProjectionSpec(
            object_types=(spec.subprocess.object_type,),
        ),
    )
    projection = projection_result.value
    # Exact original marking restriction also preserves a place-only zero-length
    # subnet, including its token multiplicity and isolated declared objects.
    current = profile.model
    hidden, reduced = None, None
    parents = [profile_result.computation_id, projection_result.computation_id]
    issues: tuple[ComputeIssue, ...] = ()
    status = ComputeStatus.COMPUTED
    losses = _LOSSES
    if spec.hiding is not None:
        result = hide_ocpn(current, spec.hiding)
        hidden, current = result.value, result.value.model
        parents.append(result.computation_id)
        if any(
            t.activity is not None and t.id in hidden.hidden_transition_ids
            for t in profile.model.transitions
        ):
            losses += ("selected_visible_activity_labels_are_hidden",)
    if spec.reduction is not None:
        result = reduce_ocpn(current, spec.reduction)
        reduced, current = result.value, result.value.model
        parents.append(result.computation_id)
        status, issues = result.status, result.issues
        if reduced.steps:
            losses += reduced.not_preserved
    removed = tuple(
        sorted(
            {p.id for p in projection.model.places}
            - {p.id for p in profile.model.places}
        )
    )
    removed_transitions = tuple(
        sorted(
            {t.id for t in projection.model.transitions}
            - {t.id for t in profile.model.transitions}
        )
    )
    value = ObjectSubprocessTransformation(
        profile,
        spec,
        projection,
        removed,
        removed_transitions,
        hidden,
        reduced,
        current,
        losses,
    )
    return _derived_result(
        "pix.object_centric.transform_ocpn_subprocess",
        model_digest(net),
        spec,
        status,
        value,
        issues,
        parent_computation_ids=tuple(parents),
    )


def validate_subprocess_result(result: ComputationResult) -> None:
    """Validate persisted request, source, stage identities and coverage status.

    The original model is still needed to independently prove extraction/cut
    completeness. This checks redundant evidence, not the original graph hash.
    """
    if result.operator_id not in RESULT_SCHEMAS:
        raise ValueError("unexpected subprocess operator")
    _, request_type, value_type = RESULT_SCHEMAS[result.operator_id]
    if not isinstance(result.spec, request_type):
        raise TypeError("subprocess request type differs")
    if result.value is None:
        return
    if not isinstance(result.value, value_type):
        raise TypeError("subprocess payload type differs")
    value = result.value
    if value.spec != result.spec:
        raise ValueError("subprocess payload and request disagree")
    profile = value if isinstance(value, ObjectTypedSubprocess) else value.profile
    if result.source_digest != profile.source_model_digest:
        raise ValueError("subprocess source and payload identity disagree")
    expected_parents = []
    expected_status = ComputeStatus.COMPUTED
    if isinstance(value, ObjectSubprocessTransformation):
        expected_parents.extend(
            (
                computation_identity(
                    "pix.object_centric.local_ocpn_subprocess",
                    "1.0.0",
                    result.source_digest,
                    profile.spec,
                ),
                computation_identity(
                    "pix.object_centric.project_ocpn",
                    "1.0.0",
                    result.source_digest,
                    ObjectProjectionSpec(object_types=(profile.spec.object_type,)),
                ),
            )
        )
        current = profile.model
        if value.hiding is not None:
            expected_parents.append(
                computation_identity(
                    "pix.object_centric.hide_ocpn",
                    "1.0.0",
                    model_digest(current),
                    value.spec.hiding,
                )
            )
            current = value.hiding.model
        if value.reduction is not None:
            expected_parents.append(
                computation_identity(
                    "pix.object_centric.reduce_ocpn",
                    "1.0.0",
                    model_digest(current),
                    value.spec.reduction,
                )
            )
            if not value.reduction.fixed_point_reached:
                expected_status = ComputeStatus.PARTIAL
    if result.parent_computation_ids != tuple(expected_parents):
        raise ValueError("subprocess parent stage identities disagree")
    if result.status is not expected_status:
        raise ValueError("subprocess status differs from reduction coverage")
    if expected_status is ComputeStatus.COMPUTED and result.issues:
        raise ValueError("complete subprocess result cannot report unresolved issues")
    if expected_status is ComputeStatus.PARTIAL and tuple(
        issue.code for issue in result.issues
    ) != ("reduction_step_limit",):
        raise ValueError("partial subprocess result requires the reduction limit issue")


RESULT_SCHEMAS = {
    "pix.object_centric.local_ocpn_subprocess": (
        "object-typed-subprocess",
        ObjectTypedSubprocessSpec,
        ObjectTypedSubprocess,
    ),
    "pix.object_centric.transform_ocpn_subprocess": (
        "object-subprocess-transformation",
        ObjectSubprocessPipelineSpec,
        ObjectSubprocessTransformation,
    ),
}

__all__ = (
    "ObjectTypedSubprocessSpec",
    "SubprocessCutArc",
    "SubprocessTransitionContext",
    "ObjectTypedSubprocess",
    "local_ocpn_subprocess",
    "ObjectSubprocessPipelineSpec",
    "ObjectSubprocessTransformation",
    "transform_ocpn_subprocess",
    "validate_subprocess_result",
)
