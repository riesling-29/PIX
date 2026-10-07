"""Selectable native per-type OCPN discovery with checked joint witnesses.

Alpha, weighted IM, and a DFG path-language net are different local miners.
The DFG net has one visible transition and pre/post places per activity;
silent routes implement starts, ends, directly-follows edges and observed
empty traces. It generalizes to all paths through the observed DFG.

Only unique local activity labels can be synchronized across object types.
No arbitrary duplicate-label correspondence is guessed. An accepting local
path is found with the native Petri-net semantics, then the whole-log joint
binding sequence is actually fired in the merged OCPN. Search exhaustion is
unknown/unavailable, never evidence that the log is non-fitting. Returned
models use observed cardinality intervals, not normative bounds, and a finite
accepting witness is not a joint soundness or upstream-equivalence claim.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import ClassVar

from pix.case_centric.alpha import AlphaSpec, discover_alpha
from pix.case_centric.discovery import (
    CaseRelationGraph,
    RelationDiscoverySpec,
    discover_dfg,
)
from pix.case_centric.inductive import InductiveSpec, discover_inductive
from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.ocpn_discovery import _accepting_path
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.models import (
    Arc,
    Binding,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    OCPNCardinalityProfile,
    OCPNDiscoveryPayload,
    OCPNFittingStep,
    OCPNObservedBinding,
    OCPNTransitionSource,
    OCPNTypeProjection,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OPERATOR_ID = "pix.object_centric.discover_ocpn_by_type"
_ALGORITHMS = ("alpha", "im", "dfg")


@dataclass(frozen=True, slots=True)
class OCPNByTypeDiscoverySpec:
    """Explicit object universe, local miners, ordering and search bounds.

    ``type_algorithms`` overrides ``default_algorithm`` for selected types.
    Alpha keeps its own non-fitting and empty-trace limitations; these are
    reported, not replaced by IM. IM is the native weighted, unfiltered profile.
    ``dfg_spec``'s edge budget must produce a complete graph before conversion.
    """

    object_types: tuple[str, ...]
    cardinality_policy: str
    merge_policy: str
    default_algorithm: str = "im"
    type_algorithms: tuple[tuple[str, str], ...] = ()
    qualifiers: tuple[str, ...] | None = None
    tie_policy: str = "reject"
    alpha_spec: AlphaSpec = AlphaSpec()
    inductive_spec: InductiveSpec = InductiveSpec()
    dfg_spec: RelationDiscoverySpec = RelationDiscoverySpec()
    max_fitting_states_per_object: int = 10000
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.OCPNByTypeDiscoverySpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        # Reuse the existing object universe/cardinality/order policy contract.
        base = OCPNDiscoverySpec(
            self.object_types,
            self.cardinality_policy,
            self.merge_policy,
            self.qualifiers,
            self.tie_policy,
            max_fitting_states_per_object=self.max_fitting_states_per_object,
        )
        object.__setattr__(self, "object_types", base.object_types)
        object.__setattr__(self, "qualifiers", base.qualifiers)
        if self.default_algorithm not in _ALGORITHMS:
            raise ValueError("default_algorithm must be alpha, im or dfg")
        if not isinstance(self.type_algorithms, tuple):
            raise TypeError("type_algorithms must be a tuple of pairs")
        seen = set()
        for row in self.type_algorithms:
            if not isinstance(row, tuple) or len(row) != 2:
                raise TypeError("type_algorithms entries must be (type, algorithm)")
            kind, algorithm = row
            if not isinstance(kind, str) or kind not in self.object_types:
                raise ValueError("algorithm override must name a selected type")
            if kind in seen:
                raise ValueError("duplicate type algorithm override")
            if algorithm not in _ALGORITHMS:
                raise ValueError("type algorithm must be alpha, im or dfg")
            seen.add(kind)
        object.__setattr__(self, "type_algorithms", tuple(sorted(self.type_algorithms)))
        if not isinstance(self.alpha_spec, AlphaSpec):
            raise TypeError("alpha_spec must be AlphaSpec")
        if self.alpha_spec.variant != "classic":
            raise ValueError("alpha selects classic Alpha; Alpha+ is not this profile")
        if not isinstance(self.inductive_spec, InductiveSpec):
            raise TypeError("inductive_spec must be InductiveSpec")
        if self.inductive_spec.variant != "im":
            raise ValueError("im selects unfiltered weighted IM, not IMf or IMd")
        if self.inductive_spec.trace_spec != CaseTraceSpec():
            raise ValueError(
                "type traces use this spec's OCEL ordering, not a case trace override"
            )
        if not isinstance(self.dfg_spec, RelationDiscoverySpec):
            raise TypeError("dfg_spec must be RelationDiscoverySpec")


def _dfg_path_net(graph: CaseRelationGraph) -> PetriNet:
    """An exact Petri-net encoding of the complete DFG's path language."""
    if graph.relation != "directly_follows" or not graph.complete:
        raise ValueError("a complete directly-follows graph is required")
    places = [Place("source"), Place("sink")]
    transitions = []
    arcs = []
    index = {activity: i for i, (activity, _) in enumerate(graph.activity_counts)}
    for activity, i in index.items():
        before, after, transition = f"pre{i}", f"post{i}", f"act{i}"
        places.extend((Place(before), Place(after)))
        transitions.append(Transition(transition, activity))
        arcs.extend((Arc(before, transition), Arc(transition, after)))

    routes = [("source", f"pre{index[a]}") for a, _ in graph.start_counts]
    routes += [(f"post{index[e.source]}", f"pre{index[e.target]}") for e in graph.edges]
    routes += [(f"post{index[a]}", "sink") for a, _ in graph.end_counts]
    if graph.empty_trace_count:
        routes.append(("source", "sink"))
    for i, (source, target) in enumerate(sorted(set(routes))):
        identity = f"route{i}"
        transitions.append(Transition(identity))
        arcs.extend((Arc(source, identity), Arc(identity, target)))
    return PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking((("source", 1),)),
        Marking((("sink", 1),)),
    )


def _merge(context, spec, local_nets, events, participation):
    activities = tuple(sorted({event.type for event in events}))
    visible = {activity: f"activity{i}" for i, activity in enumerate(activities)}
    profiles = []
    policies = {}
    for activity in activities:
        for kind in spec.object_types:
            histogram = Counter(
                len(participation[e.id][kind]) for e in events if e.type == activity
            )
            low, high = min(histogram), max(histogram)
            arc_kind = (
                "absent" if high == 0 else "fixed" if low == high == 1 else "variable"
            )
            profiles.append(
                OCPNCardinalityProfile(
                    activity,
                    kind,
                    tuple(sorted(histogram.items())),
                    arc_kind,
                    low,
                    high,
                )
            )
            policies[activity, kind] = (arc_kind, low, high)
    places, arcs, initial, final, sources = [], [], [], [], []
    transitions = [
        Transition(identity, activity) for activity, identity in visible.items()
    ]
    maps = {}
    for i, kind in enumerate(spec.object_types):
        net = local_nets[kind]
        pmap = {p.id: f"type{i}/{p.id}" for p in net.places}
        tmap = {
            t.id: visible[t.activity] if t.activity is not None else f"type{i}/{t.id}"
            for t in net.transitions
        }
        maps[kind] = tmap
        places.extend(TypedPlace(pmap[p.id], kind) for p in net.places)
        labels = {t.id: t.activity for t in net.transitions}
        for t in net.transitions:
            sources.append(OCPNTransitionSource(kind, t.id, tmap[t.id]))
            if t.activity is None:
                transitions.append(Transition(tmap[t.id]))
        for arc in net.arcs:
            tid = arc.target if arc.source in pmap else arc.source
            activity = labels[tid]
            policy, low, high = (
                ("fixed", 1, 1) if activity is None else policies[activity, kind]
            )
            arcs.append(
                ObjectArc(
                    pmap.get(arc.source, tmap.get(arc.source)),
                    pmap.get(arc.target, tmap.get(arc.target)),
                    policy == "variable",
                    low,
                    high,
                )
            )
        for obj in context.objects_by_type[kind]:
            initial.extend(
                ObjectToken(pmap[p], obj.id)
                for p, count in net.initial_marking.tokens
                for _ in range(count)
            )
            final.extend(
                ObjectToken(pmap[p], obj.id)
                for p, count in net.final_marking.tokens
                for _ in range(count)
            )
    model = ObjectCentricPetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        ObjectMarking(tuple(initial)),
        ObjectMarking(tuple(final)),
        tuple(
            (o.id, o.type) for o in context.log.objects if o.type in spec.object_types
        ),
    )
    return model, tuple(profiles), tuple(sources), maps, visible, policies


def _joint_witness(
    model, local_nets, local_paths, maps, visible, policies, events, participation
):
    """Synchronize concrete observed objects; every step uses native firing."""
    types = dict(model.objects)
    labels = {
        kind: {t.id: t.activity for t in net.transitions}
        for kind, net in local_nets.items()
    }
    positions = dict.fromkeys(local_paths, 0)
    marking = model.initial_marking
    steps, observed = [], []

    def advance_silent(oid):
        nonlocal marking
        kind, path = types[oid], local_paths[oid]
        while positions[oid] < len(path):
            tid = path[positions[oid]]
            if labels[kind][tid] is not None:
                break
            binding = Binding(maps[kind][tid], ((kind, (oid,)),))
            marking = fire_binding(model, marking, binding)
            steps.append(OCPNFittingStep(None, binding))
            positions[oid] += 1

    for event in events:
        by_type = participation[event.id]
        for oid in sorted(oid for objects in by_type.values() for oid in objects):
            advance_silent(oid)
            path = local_paths[oid]
            if (
                positions[oid] >= len(path)
                or labels[types[oid]][path[positions[oid]]] != event.type
            ):
                raise ValueError(
                    "local accepting path disagrees with whole-log event order"
                )
            positions[oid] += 1
        binding = Binding(
            visible[event.type],
            tuple(
                (kind, tuple(sorted(objects)))
                for kind, objects in by_type.items()
                if policies[event.type, kind][0] != "absent"
            ),
        )
        marking = fire_binding(model, marking, binding)
        observed.append(OCPNObservedBinding(event.id, event.type, binding))
        steps.append(OCPNFittingStep(event.id, binding))
    for oid in sorted(local_paths):
        advance_silent(oid)
    if marking != model.final_marking or any(
        positions[oid] != len(path) for oid, path in local_paths.items()
    ):
        raise ValueError("joint witness does not reach the exact final marking")
    return tuple(observed), tuple(steps)


def discover_ocpn_by_type(
    log: OCEL | ComputationContext,
    spec: OCPNByTypeDiscoverySpec,
) -> ComputationResult[OCPNDiscoveryPayload]:
    """Mine selected type projections, merge typed places and verify the log.

    A complete result contains every whole-log event, even events with no
    selected objects. No type, non-fitting trace, or unsupported local model
    is silently omitted. Bounded search failure returns unavailable, with a
    distinct unknown issue; it does not certify non-conformance.
    """
    if not isinstance(spec, OCPNByTypeDiscoverySpec):
        raise TypeError("spec must be OCPNByTypeDiscoverySpec")
    context, input_issues = _prepare(log)
    issues, parents = list(input_issues), []

    def result(status, value=None):
        return _result(
            OPERATOR_ID,
            context,
            spec,
            status,
            value,
            tuple(issues),
            parent_computation_ids=tuple(parents),
        )

    def unavailable(code, message, at=()):
        issues.append(ComputeIssue(code, message, at))
        return result(ComputeStatus.UNAVAILABLE)

    if context is None:
        return result(ComputeStatus.INVALID_INPUT)
    local_nets, local_paths, projections = {}, {}, []
    overrides = dict(spec.type_algorithms)
    for kind in spec.object_types:
        if kind not in context.objects_by_type:
            return unavailable(
                "unknown_object_type",
                f"Unknown selected type {kind!r}",
                ("object_type", kind),
            )
        if not context.objects_by_type[kind]:
            return unavailable(
                "empty_type_population",
                "A selected type has no objects",
                ("object_type", kind),
            )
        traced = reconstruct_traces(
            context, TraceSpec(kind, spec.qualifiers, spec.tie_policy)
        )
        if traced.computation_id:
            parents.append(traced.computation_id)
        issues.extend(traced.issues)
        if traced.status is not ComputeStatus.COMPUTED:
            return unavailable(
                "projection_not_computed",
                "Complete ordered type traces are required",
                ("object_type", kind),
            )
        if spec.tie_policy == "event_id" and any(
            a.time == b.time
            for trace in traced.value.traces
            for a, b in zip(trace.events, trace.events[1:])
        ):
            issues.append(
                ComputeIssue(
                    "event_id_tie_break",
                    "Explicit event ID ordering does not establish causality",
                    ("object_type", kind),
                )
            )
        algorithm = overrides.get(kind, spec.default_algorithm)
        if algorithm == "alpha":
            discovered = discover_alpha(traced, spec.alpha_spec)
        elif algorithm == "im":
            discovered = discover_inductive(traced, spec.inductive_spec)
        else:
            discovered = discover_dfg(traced, spec.dfg_spec)
        if discovered.computation_id:
            parents.append(discovered.computation_id)
        issues.extend(
            ComputeIssue(i.code, i.message, ("object_type", kind, *i.at))
            for i in discovered.issues
        )
        if discovered.status is not ComputeStatus.COMPUTED:
            return unavailable(
                "local_discovery_not_computed",
                f"{algorithm} did not produce a complete local model",
                ("object_type", kind),
            )
        net = (
            discovered.value.model
            if algorithm == "alpha"
            else process_tree_to_petri_net(discovered.value)
            if algorithm == "im"
            else _dfg_path_net(discovered.value)
        )
        counts = Counter(t.activity for t in net.transitions if t.activity is not None)
        ambiguous = tuple(sorted(a for a, count in counts.items() if count > 1))
        if ambiguous:
            return unavailable(
                "ambiguous_activity_merge",
                f"Multiple local transitions for {ambiguous!r}; no safe unique-activity correspondence",
                ("object_type", kind),
            )
        if any(arc.weight != 1 for arc in net.arcs):
            return unavailable(
                "weighted_local_arc_unsupported",
                "Local token multiplicity is not object cardinality",
                ("object_type", kind),
            )
        incident = {
            endpoint for arc in net.arcs for endpoint in (arc.source, arc.target)
        }
        if any(t.id not in incident for t in net.transitions):
            return unavailable(
                "untyped_local_transition",
                "A local transition without place incidence cannot retain its participating object type",
                ("object_type", kind),
            )
        for trace in traced.value.traces:
            path, limited = _accepting_path(
                net,
                tuple(e.activity for e in trace.events),
                spec.max_fitting_states_per_object,
            )
            if path is None:
                return unavailable(
                    "fitting_search_unknown" if limited else "local_trace_not_fitting",
                    "State budget exhausted; observed-log fitness is unknown"
                    if limited
                    else "Exhaustive local search found no accepting path for this trace",
                    ("object_type", kind, "object", trace.object_id),
                )
            local_paths[trace.object_id] = path
        local_nets[kind] = net
        projections.append(
            OCPNTypeProjection(
                kind,
                traced.computation_id,
                discovered.computation_id,
                model_digest(net),
                len(traced.value.traces),
                tuple(t.object_id for t in traced.value.traces if not t.events),
            )
        )
        issues.append(
            ComputeIssue(
                "local_discovery_profile",
                f"{algorithm} native profile selected; pinned upstream equivalence is not asserted",
                ("object_type", kind),
            )
        )
    events = tuple(sorted(context.log.events, key=lambda e: (e.time, e.id)))
    selected = set(spec.object_types)
    allowed = None if spec.qualifiers is None else set(spec.qualifiers)
    participation = {}
    for event in events:
        by_type = {kind: set() for kind in spec.object_types}
        for relation in context.e2o_by_event[event.id]:
            kind = context.objects_by_id[relation.object].type
            if kind in selected and (allowed is None or relation.qualifier in allowed):
                by_type[kind].add(relation.object)
        participation[event.id] = by_type
    model, profiles, sources, maps, visible, policies = _merge(
        context, spec, local_nets, events, participation
    )
    try:
        observed, witness = _joint_witness(
            model,
            local_nets,
            local_paths,
            maps,
            visible,
            policies,
            events,
            participation,
        )
        payload = OCPNDiscoveryPayload(
            model, profiles, tuple(projections), sources, observed, witness
        )
    except ValueError as exc:
        return unavailable("joint_fitting_not_established", str(exc))
    issues.extend(
        (
            ComputeIssue(
                "observational_cardinality_bounds",
                "Marginal observed intervals are not normative bounds or exact joint cardinality support",
            ),
            ComputeIssue(
                "joint_soundness_not_established",
                "The checked finite accepting run does not rule out other joint deadlocks or non-fitting behavior",
            ),
        )
    )
    if any(p.max_objects - p.min_objects + 1 > len(p.histogram) for p in profiles):
        issues.append(
            ComputeIssue(
                "cardinality_interval_generalization",
                "Some intervals allow unobserved intermediate cardinalities",
            )
        )
    zero_events = tuple(e.id for e in events if not any(participation[e.id].values()))
    if zero_events:
        issues.append(
            ComputeIssue(
                "zero_participation_events",
                "Whole-log events with no selected objects are retained",
                ("events", *zero_events),
            )
        )
    absent_activities = tuple(
        a
        for a in visible
        if all(policies[a, kind][0] == "absent" for kind in spec.object_types)
    )
    if absent_activities:
        issues.append(
            ComputeIssue(
                "zero_incidence_activities",
                "Unconnected visible transitions retain activities with no selected participants",
                ("activities", *absent_activities),
            )
        )
    if "dfg" in (
        overrides.get(kind, spec.default_algorithm) for kind in spec.object_types
    ):
        issues.append(
            ComputeIssue(
                "dfg_path_language",
                "DFG routing permits every start-to-end path through observed edges, including unobserved recombinations and repeats",
            )
        )
    return result(ComputeStatus.COMPUTED, payload)


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "ocpn-by-type-discovery",
        OCPNByTypeDiscoverySpec,
        OCPNDiscoveryPayload,
    ),
}

__all__ = ("OCPNByTypeDiscoverySpec", "discover_ocpn_by_type", "RESULT_SCHEMAS")
