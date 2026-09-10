"""Native OCPN discovery with unique-activity synchronization and a witness.

All input events remain in scope, including zero-object observations. Local
workflow nets are mined independently; visible activities merge only if each
type has at most one such transition. Observed marginal cardinality intervals
constrain binding sizes without claiming joint soundness or normative bounds.
"""

from __future__ import annotations

from collections import Counter, deque

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.model_semantics import fire, fire_binding, is_enabled, model_digest
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.discovery import DiscoverySpec
from pix.contracts.models import (
    Binding,
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
    Transition,
    TypedPlace,
)
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OPERATOR_ID = "pix.discover_ocpn"
OPERATOR_VERSION = "1.0.0"


def _accepting_path(
    net: PetriNet, activities: tuple[str, ...], max_states: int
) -> tuple[tuple[str, ...] | None, bool]:
    """Exhaustive bounded product search; no insertion, deletion or greedy replay."""
    start = (0, net.initial_marking)
    queue = deque((start,))
    parents = {start: None}
    limited = False
    while queue:
        current = queue.popleft()
        position, marking = current
        if position == len(activities) and marking == net.final_marking:
            steps = []
            while parents[current] is not None:
                current, transition_id = parents[current]
                steps.append(transition_id)
            return tuple(reversed(steps)), False
        for transition in net.transitions:
            next_position = position
            if transition.activity is not None:
                if (
                    position == len(activities)
                    or transition.activity != activities[position]
                ):
                    continue
                next_position += 1
            if not is_enabled(net, marking, transition.id):
                continue
            successor = (next_position, fire(net, marking, transition.id))
            if successor in parents:
                continue
            if len(parents) >= max_states:
                limited = True
                continue
            parents[successor] = current, transition.id
            queue.append(successor)
    return None, limited


def discover_ocpn(
    log: OCEL | ComputationContext, spec: OCPNDiscoverySpec
) -> ComputationResult[OCPNDiscoveryPayload]:
    """Mine type projections, synchronize unique activities, verify whole log.

    ``computed`` means the selected finite population has the attached accepting
    binding run. A duplicate local activity, unknown/empty selected type,
    ambiguous ordering, or exhausted fitting bound returns ``unavailable``.
    No selected type or source event is silently dropped.
    """
    if not isinstance(spec, OCPNDiscoverySpec):
        raise TypeError("spec must be OCPNDiscoverySpec")
    context, input_issues = _prepare(log)
    parents: list[str] = []
    issues: list[ComputeIssue] = list(input_issues)

    def result(status, value=None, extra=()):
        return _result(
            OPERATOR_ID,
            context,
            spec,
            status,
            value,
            (*issues, *extra),
            parent_computation_ids=tuple(parents),
            operator_version=OPERATOR_VERSION,
        )

    def unavailable(code, message, at=()):
        return result(
            ComputeStatus.UNAVAILABLE, extra=(ComputeIssue(code, message, at),)
        )

    if context is None:
        return result(ComputeStatus.INVALID_INPUT)
    for object_type in spec.object_types:
        if object_type not in context.objects_by_type:
            return unavailable(
                "unknown_object_type",
                f"Unknown selected object type {object_type!r}",
                ("object_type", object_type),
            )
        if not context.objects_by_type[object_type]:
            return unavailable(
                "empty_type_population",
                f"Selected type {object_type!r} has no objects; no type projection can be mined",
                ("object_type", object_type),
            )
    local_nets = {}
    local_paths = {}
    projections = []
    for object_type in spec.object_types:
        trace_result = reconstruct_traces(
            context, TraceSpec(object_type, spec.qualifiers, spec.tie_policy)
        )
        if trace_result.computation_id:
            parents.append(trace_result.computation_id)
        if trace_result.status is not ComputeStatus.COMPUTED:
            issues.extend(trace_result.issues)
            return unavailable(
                "projection_not_computed",
                "Every selected type requires a complete ordered trace population",
                ("object_type", object_type),
            )
        trace_set = trace_result.value
        if spec.tie_policy == "event_id" and any(
            first.time == second.time
            for trace in trace_set.traces
            for first, second in zip(trace.events, trace.events[1:])
        ):
            issues.append(
                ComputeIssue(
                    "event_id_tie_break",
                    "Equal timestamps in this type projection are ordered by the "
                    "explicit event_id policy; this does not establish causality",
                    ("object_type", object_type),
                )
            )
        tree_result = discover_process_tree(
            trace_result, DiscoverySpec(spec.classic_algorithm, 0.0, spec.max_depth)
        )
        if tree_result.computation_id:
            parents.append(tree_result.computation_id)
        issues.extend(
            ComputeIssue(
                issue.code, issue.message, ("object_type", object_type, *issue.at)
            )
            for issue in tree_result.issues
        )
        if tree_result.status is not ComputeStatus.COMPUTED:
            return unavailable(
                "local_discovery_not_computed",
                "Every type projection requires a complete native model",
                ("object_type", object_type),
            )
        net = process_tree_to_petri_net(tree_result.value)
        duplicates = Counter(
            t.activity for t in net.transitions if t.activity is not None
        )
        ambiguous = tuple(
            sorted(activity for activity, count in duplicates.items() if count > 1)
        )
        if ambiguous:
            return unavailable(
                "ambiguous_activity_merge",
                f"Multiple local transitions for activities {ambiguous!r}; unique_activity cannot identify a safe cross-type correspondence",
                ("object_type", object_type),
            )
        if any(arc.weight != 1 for arc in net.arcs):
            return unavailable(
                "weighted_local_arc_unsupported",
                "OCPN discovery requires unit local incidences; weights are not cardinalities",
                ("object_type", object_type),
            )
        for trace in trace_set.traces:
            path, limited = _accepting_path(
                net,
                tuple(event.activity for event in trace.events),
                spec.max_fitting_states_per_object,
            )
            if path is None:
                return unavailable(
                    "fitting_search_limit" if limited else "local_trace_not_fitting",
                    "No accepting local trace witness was established within the explicit state bound"
                    if limited
                    else "Discovered local model does not accept an observed trace",
                    ("object", trace.object_id),
                )
            local_paths[trace.object_id] = path
        local_nets[object_type] = net
        projections.append(
            OCPNTypeProjection(
                object_type,
                trace_result.computation_id,
                tree_result.computation_id,
                model_digest(net),
                len(trace_set.traces),
                tuple(
                    trace.object_id for trace in trace_set.traces if not trace.events
                ),
            )
        )

    selected_types = set(spec.object_types)
    allowed = None if spec.qualifiers is None else set(spec.qualifiers)
    events = tuple(sorted(context.log.events, key=lambda event: (event.time, event.id)))
    participation = {}
    for event in events:
        by_type = {object_type: set() for object_type in spec.object_types}
        for relation in context.e2o_by_event[event.id]:
            object_type = context.objects_by_id[relation.object].type
            if object_type in selected_types and (
                allowed is None or relation.qualifier in allowed
            ):
                by_type[object_type].add(relation.object)
        participation[event.id] = by_type
    activities = tuple(sorted({event.type for event in events}))
    visible_ids = {
        activity: f"a{index:08d}" for index, activity in enumerate(activities)
    }
    profiles = []
    policies = {}
    for activity in activities:
        for object_type in spec.object_types:
            histogram = Counter(
                len(participation[event.id][object_type])
                for event in events
                if event.type == activity
            )
            low, high = min(histogram), max(histogram)
            kind = (
                "absent" if high == 0 else "fixed" if low == high == 1 else "variable"
            )
            profiles.append(
                OCPNCardinalityProfile(
                    activity,
                    object_type,
                    tuple(sorted(histogram.items())),
                    kind,
                    low,
                    high,
                )
            )
            policies[activity, object_type] = kind, low, high
    issues.append(
        ComputeIssue(
            "observational_cardinality_bounds",
            "Arc intervals are inferred marginal observed ranges; they are not normative constraints and do not preserve exact joint cardinality combinations",
        )
    )
    issues.append(
        ComputeIssue(
            "joint_soundness_not_established",
            "The finite observed log has a checked accepting run; reachable joint deadlocks and unobserved behavior are not ruled out",
        )
    )
    if any(
        item.max_objects - item.min_objects + 1 > len(item.histogram)
        for item in profiles
    ):
        issues.append(
            ComputeIssue(
                "cardinality_interval_generalization",
                "Some observed ranges permit intermediate cardinalities absent from their exact histograms",
            )
        )
    places = []
    transitions = [
        Transition(identity, activity) for activity, identity in visible_ids.items()
    ]
    arcs = []
    initial = []
    final = []
    sources = []
    maps = {}
    represented = set()
    for index, object_type in enumerate(spec.object_types):
        net = local_nets[object_type]
        place_map = {place.id: f"type{index:08d}/{place.id}" for place in net.places}
        transition_map = {
            t.id: visible_ids[t.activity]
            if t.activity is not None
            else f"type{index:08d}/{t.id}"
            for t in net.transitions
        }
        maps[object_type] = transition_map
        places.extend(
            TypedPlace(place_map[place.id], object_type) for place in net.places
        )
        by_id = {transition.id: transition for transition in net.transitions}
        for transition in net.transitions:
            sources.append(
                OCPNTransitionSource(
                    object_type, transition.id, transition_map[transition.id]
                )
            )
            if transition.activity is None:
                transitions.append(Transition(transition_map[transition.id]))
            else:
                represented.add(transition.activity)
        for arc in net.arcs:
            transition_id = arc.target if arc.source in place_map else arc.source
            activity = by_id[transition_id].activity
            kind, low, high = (
                ("fixed", 1, 1) if activity is None else policies[activity, object_type]
            )
            source = place_map.get(arc.source, transition_map.get(arc.source))
            target = place_map.get(arc.target, transition_map.get(arc.target))
            arcs.append(ObjectArc(source, target, kind == "variable", low, high))
        for obj in context.objects_by_type[object_type]:
            initial.extend(
                ObjectToken(place_map[place], obj.id)
                for place, count in net.initial_marking.tokens
                for _ in range(count)
            )
            final.extend(
                ObjectToken(place_map[place], obj.id)
                for place, count in net.final_marking.tokens
                for _ in range(count)
            )
    if set(activities) - represented:
        issues.append(
            ComputeIssue(
                "zero_incidence_activities",
                f"Activities {tuple(sorted(set(activities) - represented))!r} have no selected object participation and are retained as zero-incidence transitions",
            )
        )
    zero_event_ids = tuple(
        event.id for event in events if not any(participation[event.id].values())
    )
    if zero_event_ids:
        issues.append(
            ComputeIssue(
                "zero_participation_events",
                f"Retained {len(zero_event_ids)} whole-log events with zero selected objects",
                ("events", *zero_event_ids),
            )
        )
    model = ObjectCentricPetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        ObjectMarking(tuple(initial)),
        ObjectMarking(tuple(final)),
        tuple(
            (obj.id, obj.type)
            for obj in context.log.objects
            if obj.type in selected_types
        ),
    )
    type_by_object = dict(model.objects)
    local_transition_by_type = {
        object_type: {t.id: t for t in net.transitions}
        for object_type, net in local_nets.items()
    }
    indices = dict.fromkeys(local_paths, 0)
    marking = model.initial_marking
    witness = []
    observed = []

    def silent_prelude(object_id):
        nonlocal marking
        object_type = type_by_object[object_id]
        path = local_paths[object_id]
        while indices[object_id] < len(path):
            transition_id = path[indices[object_id]]
            if (
                local_transition_by_type[object_type][transition_id].activity
                is not None
            ):
                break
            binding = Binding(
                maps[object_type][transition_id], ((object_type, (object_id,)),)
            )
            marking = fire_binding(model, marking, binding)
            witness.append(OCPNFittingStep(None, binding))
            indices[object_id] += 1

    try:
        for event in events:
            by_type = participation[event.id]
            for object_id in sorted(obj for ids in by_type.values() for obj in ids):
                silent_prelude(object_id)
                object_type = type_by_object[object_id]
                path = local_paths[object_id]
                if (
                    indices[object_id] >= len(path)
                    or local_transition_by_type[object_type][
                        path[indices[object_id]]
                    ].activity
                    != event.type
                ):
                    raise ValueError(
                        "local accepting witness and event identity order disagree"
                    )
                indices[object_id] += 1
            binding = Binding(
                visible_ids[event.type],
                tuple(
                    (object_type, tuple(sorted(by_type[object_type])))
                    for object_type in spec.object_types
                    if policies[event.type, object_type][0] != "absent"
                ),
            )
            marking = fire_binding(model, marking, binding)
            observed.append(OCPNObservedBinding(event.id, event.type, binding))
            witness.append(OCPNFittingStep(event.id, binding))
        for object_id in sorted(local_paths):
            silent_prelude(object_id)
        if (
            any(indices[obj] != len(path) for obj, path in local_paths.items())
            or marking != model.final_marking
        ):
            raise ValueError(
                "joint witness does not reach the exact declared final marking"
            )
    except ValueError as exc:
        return unavailable("joint_fitting_not_established", str(exc))
    payload = OCPNDiscoveryPayload(
        model,
        tuple(profiles),
        tuple(projections),
        tuple(sources),
        tuple(observed),
        tuple(witness),
    )
    return result(ComputeStatus.COMPUTED, payload)


__all__ = ("discover_ocpn", "OPERATOR_ID", "OPERATOR_VERSION")
