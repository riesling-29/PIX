"""Object-centric model representations, participation and timed diagnostics.

Per-type ordinary Petri nets are structural projections: token identities,
variable object cardinalities and synchronization across types are not their
execution semantics. The accompanying ledger retains these facts so the native
OCPN can be reconstructed exactly. Subprocess participation is an existential
incidence condition, not a soundness test. Enhanced OCPN diagnostics attach a
native joint replay and its actual timed-token evidence, including unknowns.
"""

from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from typing import ClassVar

from pix.compute._common import _derived_result, _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import model_digest
from pix.contracts.analysis import _text
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.conformance import (
    ObjectReplay,
    ObjectReplaySpec,
    replay_object_log,
)
from pix.object_centric.performance import (
    OCPerformanceSummary,
    OCReplayPerformance,
    OCReplayPerformanceSpec,
    measure_replay_performance,
)
from pix.ocel import OCEL


def _tuple(value, kind, name):
    if not isinstance(value, tuple) or any(
        not isinstance(item, kind) for item in value
    ):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _selection(value, name):
    _tuple(value, str, name)
    for item in value:
        _text(item, name)
    return tuple(sorted(set(value)))


def _aggregate(marking):
    return Marking(
        tuple(sorted(Counter(token.place_id for token in marking.tokens).items()))
    )


@dataclass(frozen=True, slots=True)
class OCPNDecompositionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.ocpn_decomposition.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    profile: str = "unit_incidence_with_concrete_object_ledger"

    def __post_init__(self):
        if self.profile != "unit_incidence_with_concrete_object_ledger":
            raise ValueError("unsupported OCPN decomposition profile")


@dataclass(frozen=True, slots=True)
class ObjectTypePetriNet:
    object_type: str
    petri_net: PetriNet
    object_ids: tuple[str, ...]
    concrete_initial_marking: ObjectMarking
    concrete_final_marking: ObjectMarking
    arc_cardinalities: tuple[ObjectArc, ...]
    start_transition_ids: tuple[str, ...]
    end_transition_ids: tuple[str, ...]

    def __post_init__(self):
        _text(self.object_type, "object_type")
        if not isinstance(self.petri_net, PetriNet):
            raise TypeError("petri_net must be PetriNet")
        object_ids = _selection(self.object_ids, "object_ids")
        if len(object_ids) != len(self.object_ids):
            raise ValueError("duplicate object ID")
        object.__setattr__(self, "object_ids", object_ids)
        _tuple(self.arc_cardinalities, ObjectArc, "arc_cardinalities")
        native = ObjectCentricPetriNet(
            tuple(TypedPlace(p.id, self.object_type) for p in self.petri_net.places),
            self.petri_net.transitions,
            self.arc_cardinalities,
            self.concrete_initial_marking,
            self.concrete_final_marking,
            tuple((obj, self.object_type) for obj in object_ids),
        )
        if any(arc.weight != 1 for arc in self.petri_net.arcs):
            raise ValueError("type projection must use unit arcs")
        if {(arc.source, arc.target) for arc in self.petri_net.arcs} != {
            (arc.source, arc.target) for arc in native.arcs
        }:
            raise ValueError("arc cardinality ledger differs from projected incidence")
        place_ids = {place.id for place in self.petri_net.places}
        incident_transition_ids = {
            arc.target if arc.source in place_ids else arc.source
            for arc in self.petri_net.arcs
        }
        if {
            transition.id for transition in self.petri_net.transitions
        } != incident_transition_ids:
            raise ValueError(
                "type net may contain only transitions incident to that type"
            )
        if self.petri_net.initial_marking != _aggregate(
            self.concrete_initial_marking
        ) or self.petri_net.final_marking != _aggregate(self.concrete_final_marking):
            raise ValueError("aggregate markings differ from concrete object ledger")
        starts = {place for place, _ in self.petri_net.initial_marking.tokens}
        ends = {place for place, _ in self.petri_net.final_marking.tokens}
        expected_start = tuple(
            sorted({arc.target for arc in self.petri_net.arcs if arc.source in starts})
        )
        expected_end = tuple(
            sorted({arc.source for arc in self.petri_net.arcs if arc.target in ends})
        )
        if (
            _selection(self.start_transition_ids, "start_transition_ids")
            != expected_start
        ):
            raise ValueError("start transitions disagree with initial-place incidence")
        if _selection(self.end_transition_ids, "end_transition_ids") != expected_end:
            raise ValueError("end transitions disagree with final-place incidence")
        object.__setattr__(self, "arc_cardinalities", native.arcs)
        object.__setattr__(self, "start_transition_ids", expected_start)
        object.__setattr__(self, "end_transition_ids", expected_end)


@dataclass(frozen=True, slots=True)
class OCPNDecomposition:
    source_model_digest: str
    per_type: tuple[ObjectTypePetriNet, ...]
    unattached_transitions: tuple[Transition, ...]
    shared_transition_ids: tuple[str, ...]
    activity_labels: tuple[str, ...]
    projected_semantic_losses: tuple[str, ...] = (
        "concrete_object_identity_in_ordinary_tokens",
        "variable_arc_object_cardinality_in_unit_arcs",
        "joint_transition_synchronization_across_types",
    )
    reconstruction_guarantee: str = (
        "exact_with_concrete_marking_and_arc_cardinality_ledger"
    )

    def __post_init__(self):
        _text(self.source_model_digest, "source_model_digest")
        _tuple(self.per_type, ObjectTypePetriNet, "per_type")
        _tuple(self.unattached_transitions, Transition, "unattached_transitions")
        if len({row.object_type for row in self.per_type}) != len(self.per_type):
            raise ValueError("duplicate decomposition object type")
        _tuple(self.projected_semantic_losses, str, "projected_semantic_losses")
        expected_losses = (
            "concrete_object_identity_in_ordinary_tokens",
            "variable_arc_object_cardinality_in_unit_arcs",
            "joint_transition_synchronization_across_types",
        )
        if (
            self.projected_semantic_losses != expected_losses
            or self.reconstruction_guarantee
            != "exact_with_concrete_marking_and_arc_cardinality_ledger"
        ):
            raise ValueError("unsupported decomposition semantic guarantee")
        counts = Counter(
            t.id for row in self.per_type for t in row.petri_net.transitions
        )
        if _selection(self.shared_transition_ids, "shared_transition_ids") != tuple(
            sorted(tid for tid, count in counts.items() if count > 1)
        ):
            raise ValueError("shared transition IDs differ from type membership")
        all_labels = {
            t.activity
            for row in self.per_type
            for t in row.petri_net.transitions
            if t.activity is not None
        }
        all_labels.update(
            t.activity for t in self.unattached_transitions if t.activity is not None
        )
        if _selection(self.activity_labels, "activity_labels") != tuple(
            sorted(all_labels)
        ):
            raise ValueError("activity labels differ from transition labels")
        object.__setattr__(
            self,
            "per_type",
            tuple(sorted(self.per_type, key=lambda row: row.object_type)),
        )
        object.__setattr__(
            self,
            "unattached_transitions",
            tuple(sorted(self.unattached_transitions, key=lambda t: t.id)),
        )
        object.__setattr__(
            self,
            "shared_transition_ids",
            tuple(sorted(tid for tid, count in counts.items() if count > 1)),
        )
        object.__setattr__(self, "activity_labels", tuple(sorted(all_labels)))
        reconstructed = _recompose(self)
        if model_digest(reconstructed) != self.source_model_digest:
            raise ValueError(
                "decomposition ledger does not reconstruct source model identity"
            )


def _recompose(decomposition):
    places = []
    transitions = {}
    arcs = []
    objects = []
    initial, final = [], []
    place_ids = set()
    for row in decomposition.per_type:
        for place in row.petri_net.places:
            if place.id in place_ids:
                raise ValueError("place ID occurs in several object types")
            place_ids.add(place.id)
            places.append(TypedPlace(place.id, row.object_type))
        for transition in row.petri_net.transitions:
            if (
                transition.id in transitions
                and transitions[transition.id] != transition
            ):
                raise ValueError("shared transition label differs across types")
            transitions[transition.id] = transition
        arcs.extend(row.arc_cardinalities)
        objects.extend((obj, row.object_type) for obj in row.object_ids)
        initial.extend(row.concrete_initial_marking.tokens)
        final.extend(row.concrete_final_marking.tokens)
    for transition in decomposition.unattached_transitions:
        if transition.id in transitions:
            raise ValueError(
                "an unattached transition occurs in a type net or is duplicated"
            )
        transitions[transition.id] = transition
    return ObjectCentricPetriNet(
        tuple(places),
        tuple(transitions.values()),
        tuple(arcs),
        ObjectMarking(tuple(initial)),
        ObjectMarking(tuple(final)),
        tuple(objects),
    )


def recompose_ocpn(decomposition: OCPNDecomposition) -> ObjectCentricPetriNet:
    """Reconstruct the native model from typed nets and the retained loss ledger."""
    if not isinstance(decomposition, OCPNDecomposition):
        raise TypeError("decomposition must be OCPNDecomposition")
    return _recompose(decomposition)


def decompose_ocpn(
    net: ObjectCentricPetriNet, spec: OCPNDecompositionSpec = OCPNDecompositionSpec()
) -> ComputationResult[OCPNDecomposition]:
    """Return per-type PN representations with explicit executable-meaning losses.

    Initial/final ordinary markings sum concrete token multiplicities, including
    repeated tokens for one object. Transition IDs, not labels, join the type
    projections. Direct marked-place incidence identifies start/end transitions;
    no silent reachability or event frequency is inferred from the model.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, OCPNDecompositionSpec
    ):
        raise TypeError("expected ObjectCentricPetriNet and OCPNDecompositionSpec")
    types = sorted(
        {p.object_type for p in net.places} | {kind for _, kind in net.objects}
    )
    rows = []
    memberships = Counter()
    for kind in types:
        places = {p.id for p in net.places if p.object_type == kind}
        arcs = tuple(a for a in net.arcs if a.source in places or a.target in places)
        tids = {a.target if a.source in places else a.source for a in arcs}
        initial = ObjectMarking(
            tuple(
                token
                for token in net.initial_marking.tokens
                if token.place_id in places
            )
        )
        final = ObjectMarking(
            tuple(
                token for token in net.final_marking.tokens if token.place_id in places
            )
        )
        projected = PetriNet(
            tuple(Place(p) for p in sorted(places)),
            tuple(t for t in net.transitions if t.id in tids),
            tuple(Arc(a.source, a.target) for a in arcs),
            _aggregate(initial),
            _aggregate(final),
        )
        initial_places = {token.place_id for token in initial.tokens}
        final_places = {token.place_id for token in final.tokens}
        rows.append(
            ObjectTypePetriNet(
                kind,
                projected,
                tuple(obj for obj, ot in net.objects if ot == kind),
                initial,
                final,
                arcs,
                tuple(sorted({a.target for a in arcs if a.source in initial_places})),
                tuple(sorted({a.source for a in arcs if a.target in final_places})),
            )
        )
        memberships.update(tids)
    value = OCPNDecomposition(
        model_digest(net),
        tuple(rows),
        tuple(t for t in net.transitions if t.id not in memberships),
        tuple(sorted(tid for tid, count in memberships.items() if count > 1)),
        tuple(sorted({t.activity for t in net.transitions if t.activity is not None})),
    )
    return _derived_result(
        "pix.object_centric.decompose_ocpn",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        value,
    )


@dataclass(frozen=True, slots=True)
class SubprocessParticipationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.subprocess_participation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_types: tuple[str, ...]
    transition_ids: tuple[str, ...] | None = None
    activities: tuple[str, ...] | None = None

    def __post_init__(self):
        object.__setattr__(
            self, "object_types", _selection(self.object_types, "object_types")
        )
        for name in ("transition_ids", "activities"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _selection(value, name))
        if self.transition_ids is not None and self.activities is not None:
            raise ValueError("select transition IDs or activities, not both")


@dataclass(frozen=True, slots=True)
class TransitionParticipation:
    transition_id: str
    activity: str | None
    incident_object_types: tuple[str, ...]
    selected_incident_place_ids: tuple[str, ...]
    selected_incident_arc_endpoints: tuple[tuple[str, str], ...]
    has_selected_type_incidence: bool


@dataclass(frozen=True, slots=True)
class SubprocessParticipation:
    selected_object_types: tuple[str, ...]
    selection_profile: str
    transitions: tuple[TransitionParticipation, ...]
    all_selected_transitions_participate: bool
    empty_transition_selection: bool
    condition: str = (
        "for_each_selected_transition_exists_incident_place_of_a_selected_type"
    )
    soundness_established: bool | None = None


def check_subprocess_participation(
    net: ObjectCentricPetriNet, spec: SubprocessParticipationSpec
) -> ComputationResult[SubprocessParticipation]:
    """Check the existential incidence condition named Subprocess.sound in OCPA.

    Explicit activity selection covers every transition with that activity,
    preserving repeated labels. Without transition/activity selection, select
    all transitions incident to the requested types (the condition then holds
    by construction). Empty selections use universal quantification's vacuous
    truth and are explicitly marked empty. No token, cardinality or reachability
    property is concluded from this structural incidence test.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, SubprocessParticipationSpec
    ):
        raise TypeError(
            "expected ObjectCentricPetriNet and SubprocessParticipationSpec"
        )
    types = {p.object_type for p in net.places} | {kind for _, kind in net.objects}
    if set(spec.object_types) - types:
        raise ValueError("unknown selected object type")
    by_id = {t.id: t for t in net.transitions}
    labels = {t.activity for t in net.transitions if t.activity is not None}
    if spec.transition_ids is not None and set(spec.transition_ids) - by_id.keys():
        raise ValueError("unknown selected transition")
    if spec.activities is not None and set(spec.activities) - labels:
        raise ValueError("unknown selected activity")
    places = {p.id: p.object_type for p in net.places}
    incidence = {
        t.id: tuple(a for a in net.arcs if t.id in (a.source, a.target))
        for t in net.transitions
    }

    def selected_places(tid):
        return {
            a.source if a.target == tid else a.target
            for a in incidence[tid]
            if places[a.source if a.target == tid else a.target] in spec.object_types
        }

    if spec.transition_ids is not None:
        selected = set(spec.transition_ids)
        profile = "explicit_transition_ids"
    elif spec.activities is not None:
        selected = {t.id for t in net.transitions if t.activity in spec.activities}
        profile = "all_transitions_with_selected_activity_labels"
    else:
        selected = {t.id for t in net.transitions if selected_places(t.id)}
        profile = "all_transitions_incident_to_selected_types"
    rows = []
    for tid in sorted(selected):
        connected = selected_places(tid)
        rows.append(
            TransitionParticipation(
                tid,
                by_id[tid].activity,
                tuple(
                    sorted(
                        {
                            places[a.source if a.target == tid else a.target]
                            for a in incidence[tid]
                        }
                    )
                ),
                tuple(sorted(connected)),
                tuple(
                    (a.source, a.target)
                    for a in incidence[tid]
                    if a.source in connected or a.target in connected
                ),
                bool(connected),
            )
        )
    value = SubprocessParticipation(
        spec.object_types,
        profile,
        tuple(rows),
        all(row.has_selected_type_incidence for row in rows),
        not rows,
    )
    return _derived_result(
        "pix.object_centric.check_subprocess_participation",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        value,
    )


@dataclass(frozen=True, slots=True)
class EnhancedOCPNSpec:
    SPEC_TYPE: ClassVar[str] = "pix.enhanced_ocpn.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    replay: ObjectReplaySpec
    performance: OCReplayPerformanceSpec = OCReplayPerformanceSpec()

    def __post_init__(self):
        if not isinstance(self.replay, ObjectReplaySpec) or not isinstance(
            self.performance, OCReplayPerformanceSpec
        ):
            raise TypeError(
                "enhanced OCPN requires explicit native replay and replay-performance specifications"
            )


@dataclass(frozen=True, slots=True)
class EnhancedOCPNRequest:
    model_digest: str
    parameters: EnhancedOCPNSpec
    SPEC_TYPE: ClassVar[str] = "pix.enhanced_ocpn.request"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _text(self.model_digest, "model_digest")
        if not isinstance(self.parameters, EnhancedOCPNSpec):
            raise TypeError("parameters must be EnhancedOCPNSpec")


@dataclass(frozen=True, slots=True)
class OCPNTransitionDiagnostics:
    transition_id: str
    activity: str | None
    firing_step_indices: tuple[int, ...]
    observed_event_ids: tuple[str, ...]
    consumed_token_count: int
    produced_token_count: int
    inserted_token_count: int
    metrics: tuple[OCPerformanceSummary, ...]


@dataclass(frozen=True, slots=True)
class EnhancedObjectCentricPetriNet:
    model: ObjectCentricPetriNet
    replay: ObjectReplay
    performance: OCReplayPerformance
    transition_diagnostics: tuple[OCPNTransitionDiagnostics, ...]
    unassigned_performance_event_ids: tuple[str, ...]
    profile: str = "native_joint_replay_timed_token_diagnostics"

    def __post_init__(self):
        if (
            not isinstance(self.model, ObjectCentricPetriNet)
            or not isinstance(self.replay, ObjectReplay)
            or not isinstance(self.performance, OCReplayPerformance)
        ):
            raise TypeError(
                "enhanced OCPN requires native model, replay and performance payloads"
            )
        identity = model_digest(self.model)
        if (
            self.replay.model_digest != identity
            or self.performance.model_digest != identity
        ):
            raise ValueError(
                "enhanced OCPN model identity differs from attached diagnostics"
            )
        if self.profile != "native_joint_replay_timed_token_diagnostics":
            raise ValueError("unsupported enhanced OCPN profile")
        _validate_timing_attachment(self.model, self.replay, self.performance)
        _tuple(
            self.transition_diagnostics,
            OCPNTransitionDiagnostics,
            "transition_diagnostics",
        )
        _tuple(
            self.unassigned_performance_event_ids,
            str,
            "unassigned_performance_event_ids",
        )
        expected_rows, expected_unassigned = _attach_diagnostics(
            self.model, self.replay, self.performance
        )
        if (
            self.transition_diagnostics != expected_rows
            or self.unassigned_performance_event_ids != expected_unassigned
        ):
            raise ValueError(
                "enhanced transition diagnostics disagree with replay and timing evidence"
            )


def _summary(metric, unit, samples):
    values = [sample.value for sample in samples if sample.value is not None]
    total = sum(values)
    return OCPerformanceSummary(
        metric,
        unit,
        len(samples),
        len(values),
        len(samples) - len(values),
        total,
        min(values) if values else None,
        max(values) if values else None,
        total if values else None,
        len(values) if values else None,
        tuple(samples),
    )


def _validate_timing_attachment(net, replay, performance):
    """Rebuild FIFO token provenance; a same-model replay is not enough.

    The replay does not contain original OCEL timestamps, so this checks its
    structural token lineage and known/unknown clock status. Timestamp values
    themselves are calculated against the source OCEL by the public pipeline.
    """
    if performance.replay_status != replay.status:
        raise ValueError("performance replay status differs from attached replay")
    if (
        performance.token_selection != "fifo_production"
        or performance.silent_policy != "zero_duration_max_input"
    ):
        raise ValueError("unsupported attached token timing policy")
    object_types = dict(net.objects)
    ledger = defaultdict(deque)
    serial = 0
    event_inputs = {}
    for index, step in enumerate(replay.steps):
        for token in step.inserted_tokens:
            ledger[token].append(
                (
                    serial,
                    token,
                    "injected",
                    index,
                    (),
                    False,
                    "injected_token_time_unknown",
                )
            )
            serial += 1
        consumed = []
        for token in step.consumed_tokens:
            if not ledger[token]:
                raise ValueError(
                    "attached replay consumes absent timed-token provenance"
                )
            consumed.append(ledger[token].popleft())
        if step.event_id is not None:
            if step.event_id in event_inputs:
                raise ValueError("attached replay repeats an observed event")
            reason = (
                "log_deviation_without_token_inputs"
                if step.kind == "log_deviation"
                else None
            )
            event_inputs[step.event_id] = (index, tuple(consumed), reason)
        if step.kind == "visible":
            origin, sources, known, reason = "visible", (step.event_id,), True, None
        elif step.kind == "silent":
            known = bool(consumed) and all(token[5] for token in consumed)
            origin = "silent"
            sources = tuple(sorted({event for token in consumed for event in token[4]}))
            reason = None if known else "silent_input_time_unknown"
        else:
            origin, sources, known, reason = (
                "initial",
                (),
                False,
                "initial_token_time_unknown",
            )
        for token in step.produced_tokens:
            ledger[token].append((serial, token, origin, index, sources, known, reason))
            serial += 1
    selected = performance.measurements.selected_event_ids
    if len(set(selected)) != len(selected) or set(selected) - {
        event.event_id for event in replay.scope.events
    }:
        raise ValueError("timed event selection differs from attached replay scope")
    if tuple(row.event_id for row in performance.token_inputs) != selected:
        raise ValueError(
            "token input evidence does not cover the selected event population"
        )
    for row in performance.token_inputs:
        expected_index, expected_tokens, expected_reason = event_inputs.get(
            row.event_id, (None, (), "event_not_replayed")
        )
        if (
            row.step_index != expected_index
            or row.reason != expected_reason
            or len(row.arrivals) != len(expected_tokens)
        ):
            raise ValueError(
                "timed event input index or population differs from attached replay"
            )
        known_count = sum(token[5] for token in expected_tokens)
        if (
            row.known_count != known_count
            or row.unknown_count != len(expected_tokens) - known_count
        ):
            raise ValueError(
                "timed input known/unknown counts differ from token lineage"
            )
        for arrival, token_data in zip(row.arrivals, expected_tokens):
            token_serial, token, origin, produced_step, sources, known, reason = (
                token_data
            )
            expected = (
                token_serial,
                token.place_id,
                token.object_id,
                object_types[token.object_id],
                origin,
                produced_step,
                sources,
                reason,
            )
            actual = (
                arrival.token_serial,
                arrival.place_id,
                arrival.object_id,
                arrival.object_type,
                arrival.origin,
                arrival.produced_step,
                arrival.source_event_ids,
                arrival.unknown_reason,
            )
            if actual != expected or (arrival.arrival_time is not None) != known:
                raise ValueError("timed token provenance differs from attached replay")


def _attach_diagnostics(net, replay, performance):
    assigned: dict[str, str] = {}
    step_indices: dict[str, list[int]] = defaultdict(list)
    transition_ids = {transition.id for transition in net.transitions}
    for index, step in enumerate(replay.steps):
        if step.binding is not None:
            if step.binding.transition_id not in transition_ids:
                raise ValueError("replay step refers to an unknown model transition")
            step_indices[step.binding.transition_id].append(index)
            if step.event_id is not None:
                if step.event_id in assigned:
                    raise ValueError("replay assigns an event to multiple firings")
                assigned[step.event_id] = step.binding.transition_id
    rows = []
    for transition in net.transitions:
        selected_steps = tuple(step_indices[transition.id])
        events = tuple(
            sorted(
                event_id for event_id, tid in assigned.items() if tid == transition.id
            )
        )
        metrics = tuple(
            _summary(
                summary.metric,
                summary.unit,
                tuple(
                    sample for sample in summary.samples if sample.event_id in events
                ),
            )
            for summary in performance.measurements.summaries
        )
        rows.append(
            OCPNTransitionDiagnostics(
                transition.id,
                transition.activity,
                selected_steps,
                events,
                sum(
                    len(replay.steps[index].consumed_tokens) for index in selected_steps
                ),
                sum(
                    len(replay.steps[index].produced_tokens) for index in selected_steps
                ),
                sum(
                    len(replay.steps[index].inserted_tokens) for index in selected_steps
                ),
                metrics,
            )
        )
    selected_events = set(performance.measurements.selected_event_ids)
    return tuple(rows), tuple(sorted(selected_events - assigned.keys()))


def enhance_ocpn(
    log: OCEL | ComputationContext, net: ObjectCentricPetriNet, spec: EnhancedOCPNSpec
) -> ComputationResult[EnhancedObjectCentricPetriNet]:
    """Attach native joint replay, timed token inputs and transition diagnostics.

    Event metrics attach to the transition actually fired in the replay, not
    every transition sharing its label. Silent firings retain token counts but
    receive no fabricated observed event/service time. Repaired runs and unknown
    initial/injected token clocks remain explicit in the attached evidence.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, EnhancedOCPNSpec
    ):
        raise TypeError("expected ObjectCentricPetriNet and EnhancedOCPNSpec")
    request = EnhancedOCPNRequest(model_digest(net), spec)
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.enhance_ocpn",
            None,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    replay = replay_object_log(context, net, spec.replay)
    parents = (replay.computation_id,) if replay.computation_id else ()
    if replay.value is None:
        return _result(
            "pix.object_centric.enhance_ocpn",
            context,
            request,
            replay.status,
            None,
            replay.issues,
            parent_computation_ids=parents,
        )
    performance = measure_replay_performance(context, replay, spec.performance)
    parents += (performance.computation_id,) if performance.computation_id else ()
    if performance.value is None:
        return _result(
            "pix.object_centric.enhance_ocpn",
            context,
            request,
            performance.status,
            None,
            performance.issues,
            parent_computation_ids=parents,
        )
    rows, unassigned = _attach_diagnostics(net, replay.value, performance.value)
    value = EnhancedObjectCentricPetriNet(
        net, replay.value, performance.value, rows, unassigned
    )
    warnings = tuple(dict.fromkeys(replay.issues + performance.issues))
    status = (
        ComputeStatus.PARTIAL
        if ComputeStatus.PARTIAL in (replay.status, performance.status)
        else ComputeStatus.COMPUTED
    )
    if unassigned and status is ComputeStatus.COMPUTED:
        status = ComputeStatus.PARTIAL
        warnings += (
            ComputeIssue(
                "enhanced_unassigned_events",
                "Selected event diagnostics have no fired model transition",
            ),
        )
    return _result(
        "pix.object_centric.enhance_ocpn",
        context,
        request,
        status,
        value,
        warnings,
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS = {
    "pix.object_centric.decompose_ocpn": (
        "ocpn-type-petri-decomposition",
        OCPNDecompositionSpec,
        OCPNDecomposition,
    ),
    "pix.object_centric.check_subprocess_participation": (
        "subprocess-participation",
        SubprocessParticipationSpec,
        SubprocessParticipation,
    ),
    "pix.object_centric.enhance_ocpn": (
        "enhanced-ocpn",
        EnhancedOCPNRequest,
        EnhancedObjectCentricPetriNet,
    ),
}

__all__ = (
    "OCPNDecompositionSpec",
    "ObjectTypePetriNet",
    "OCPNDecomposition",
    "decompose_ocpn",
    "recompose_ocpn",
    "SubprocessParticipationSpec",
    "TransitionParticipation",
    "SubprocessParticipation",
    "check_subprocess_participation",
    "EnhancedOCPNSpec",
    "EnhancedOCPNRequest",
    "OCPNTransitionDiagnostics",
    "EnhancedObjectCentricPetriNet",
    "enhance_ocpn",
)
