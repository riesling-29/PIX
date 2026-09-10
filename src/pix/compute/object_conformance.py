"""Joint OCPN alignment against an E2O-derived event partial order.

The product state contains an event downset and one complete object marking.
Independent events may interleave freely; a shared event is consumed just once.
No per-type alignment sum or arbitrary global timestamp serialization is used.
"""

from __future__ import annotations

from collections import defaultdict
from heapq import heappop, heappush
from itertools import count

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.contracts.models import ObjectCentricPetriNet, ObjectMarking
from pix.contracts.object_conformance import (
    ObjectAlignment,
    ObjectAlignmentCoverage,
    ObjectAlignmentMove,
    ObjectAlignmentMoveCounts,
    ObjectAlignmentRequest,
    ObjectAlignmentSpec,
    ObjectEventParticipation,
    ObjectLogScope,
    ObjectPrecedence,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OBJECT_ALIGNMENT_OPERATOR_ID = "pix.align_object_log"
State = tuple[int, ObjectMarking]


def build_object_event_scope(
    context: ComputationContext,
    *,
    object_types: tuple[str, ...],
    qualifiers: tuple[str, ...] | None = None,
    tie_policy: str = "reject",
) -> tuple[ObjectLogScope | None, tuple[ComputeIssue, ...]]:
    """Build a reusable whole-log event DAG using only selected-object order.

    All events remain, including empty selected participation. This helper does
    not validate a model universe; consumers call validate_object_model_scope.
    A non-None scope may carry informational diagnostics for actual time ties
    ordered by the explicitly selected event_id convention.
    """
    if not isinstance(context, ComputationContext):
        raise TypeError("context must be a ComputationContext")
    selection = ObjectAlignmentSpec(object_types, qualifiers, tie_policy)
    unknown = set(selection.object_types) - set(context.objects_by_type)
    if unknown:
        return None, tuple(
            ComputeIssue(
                "unknown_object_type",
                "Selected object type is not declared",
                ("object_type", item),
            )
            for item in sorted(unknown)
        )
    selected_types = set(selection.object_types)
    selected_objects = tuple(
        sorted(
            (obj.id, obj.type)
            for obj in context.log.objects
            if obj.type in selected_types
        )
    )
    selected = dict(selected_objects)
    allowed = None if selection.qualifiers is None else set(selection.qualifiers)
    relations: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    object_events: dict[str, set[str]] = defaultdict(set)
    included_relations = 0
    for relation in context.log.e2o:
        if relation.object not in selected or (
            allowed is not None and relation.qualifier not in allowed
        ):
            continue
        relations[relation.event].append(
            (relation.event, relation.object, relation.qualifier)
        )
        object_events[relation.object].add(relation.event)
        included_relations += 1
    precedence: list[ObjectPrecedence] = []
    issues: list[ComputeIssue] = []
    warnings: list[ComputeIssue] = []
    for object_id in sorted(object_events):
        events = sorted(
            (context.events_by_id[event_id] for event_id in object_events[object_id]),
            key=lambda event: (event.time, event.id),
        )
        for before, after in zip(events, events[1:]):
            if before.time == after.time and selection.tie_policy == "reject":
                issues.append(
                    ComputeIssue(
                        "ambiguous_event_order",
                        "Equal timestamps on a shared selected object require an explicit tie policy",
                        ("object", object_id, "events", before.id, after.id),
                    )
                )
            elif before.time == after.time:
                warnings.append(
                    ComputeIssue(
                        "timestamp_tie_broken",
                        "Equal timestamps on a shared selected object were ordered by the explicit event_id convention; this is not causal evidence",
                        ("object", object_id, "events", before.id, after.id),
                    )
                )
            precedence.append(ObjectPrecedence(object_id, before.id, after.id))
    if issues:
        return None, tuple(issues)
    participation: list[ObjectEventParticipation] = []
    for event in sorted(context.log.events, key=lambda item: item.id):
        grouped: dict[str, set[str]] = defaultdict(set)
        event_relations = tuple(sorted(relations[event.id]))
        for _, object_id, _ in event_relations:
            grouped[selected[object_id]].add(object_id)
        participation.append(
            ObjectEventParticipation(
                event.id,
                event.type,
                tuple(
                    (kind, tuple(sorted(ids))) for kind, ids in sorted(grouped.items())
                ),
                event_relations,
            )
        )
    return ObjectLogScope(
        tuple(participation),
        tuple(precedence),
        selected_objects,
        len(context.log.objects) - len(selected_objects),
        len(context.log.e2o) - included_relations,
    ), tuple(warnings)


def validate_object_model_scope(
    net: ObjectCentricPetriNet,
    scope: ObjectLogScope,
    selected_types: tuple[str, ...],
) -> tuple[ComputeIssue, ...]:
    """Require the supplied model's entire concrete universe to match selection.

    No initial/final marking or out-of-scope object is silently removed. A place
    type without objects still belongs to model semantics and must be selected.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    if not isinstance(scope, ObjectLogScope):
        raise TypeError("scope must be ObjectLogScope")
    issues: list[ComputeIssue] = []
    model_objects = dict(net.objects)
    log_objects = dict(scope.selected_objects)
    for identifier in sorted(set(log_objects) - set(model_objects)):
        issues.append(
            ComputeIssue(
                "object_missing_from_model",
                "Selected log object is absent from model universe",
                ("object", identifier),
            )
        )
    for identifier in sorted(set(model_objects) - set(log_objects)):
        issues.append(
            ComputeIssue(
                "model_object_outside_scope",
                "Model object is not in the selected log universe",
                ("object", identifier),
            )
        )
    for identifier in sorted(set(model_objects) & set(log_objects)):
        if model_objects[identifier] != log_objects[identifier]:
            issues.append(
                ComputeIssue(
                    "object_type_mismatch",
                    "Log and model assign different object types",
                    ("object", identifier),
                )
            )
    model_types = {place.object_type for place in net.places} | set(
        model_objects.values()
    )
    for kind in sorted(model_types - set(selected_types)):
        issues.append(
            ComputeIssue(
                "model_type_outside_scope",
                "Model object type is not selected",
                ("object_type", kind),
            )
        )
    return tuple(issues)


def _snapshot(marking: ObjectMarking) -> tuple[tuple[str, str], ...]:
    return tuple((token.place_id, token.object_id) for token in marking.tokens)


def _align_scope(
    scope: ObjectLogScope,
    net: ObjectCentricPetriNet,
    spec: ObjectAlignmentSpec,
    digest: str,
) -> ObjectAlignment:
    events = scope.events
    index = {event.event_id: i for i, event in enumerate(events)}
    predecessors = [0] * len(events)
    for edge in scope.precedence:
        predecessors[index[edge.successor_event_id]] |= (
            1 << index[edge.predecessor_event_id]
        )
    full = (1 << len(events)) - 1
    activities = {transition.id: transition.activity for transition in net.transitions}
    initial: State = (0, net.initial_marking)
    costs: dict[State, int] = {initial: 0}
    parents: dict[State, tuple[State, ObjectAlignmentMove]] = {}
    serial = count()
    heap: list[tuple[int, int, State]] = [(0, next(serial), initial)]
    settled: set[State] = set()
    max_bindings_seen = 0

    def weight(objects: tuple[tuple[str, tuple[str, ...]], ...]) -> int:
        return 1 if spec.cost_mode == "event" else sum(len(ids) for _, ids in objects)

    def finish(
        status: str,
        state: State | None = None,
        cost: int | None = None,
        lower: int | None = None,
    ) -> ObjectAlignment:
        moves: list[ObjectAlignmentMove] = []
        while state is not None and state != initial:
            state, move = parents[state]
            moves.append(move)
        ordered_moves = tuple(reversed(moves))
        counts = None
        if status == "optimal":
            counts = ObjectAlignmentMoveCounts(
                *(
                    sum(move.kind == kind for move in ordered_moves)
                    for kind in ("synchronous", "silent", "model", "log")
                )
            )
        return ObjectAlignment(
            digest,
            scope,
            status,
            ordered_moves,
            counts,
            cost,
            lower,
            len(settled),
            len(costs),
            max_bindings_seen,
            ObjectAlignmentCoverage(
                1,
                int(status == "optimal"),
                int(status == "unreachable"),
                int(status in ("search_limit", "binding_limit")),
                0,
                len(events),
                len(scope.selected_objects),
            ),
            "event_weighted_integer_cost"
            if spec.cost_mode == "event"
            else "object_weighted_integer_cost",
        )

    while heap:
        cost, _, state = heappop(heap)
        if cost != costs[state] or state in settled:
            continue
        if len(settled) >= spec.max_states:
            return finish("search_limit", lower=cost)
        settled.add(state)
        consumed, marking = state
        if consumed == full and marking == net.final_marking:
            return finish("optimal", state, cost, cost)
        bindings = enumerate_enabled_bindings(
            net, marking, max_bindings=spec.max_bindings
        )
        max_bindings_seen = max(max_bindings_seen, bindings.candidate_count)
        if not bindings.complete:
            # Even an already generated goal is not certified when model moves
            # have been omitted. Current Dijkstra distance remains a lower bound.
            return finish("binding_limit", lower=cost)
        enabled_events = tuple(
            i
            for i in range(len(events))
            if not consumed & (1 << i) and predecessors[i] & consumed == predecessors[i]
        )
        before = _snapshot(marking)
        moves: list[tuple[int, str, str, State, ObjectAlignmentMove]] = []
        for binding in bindings.bindings:
            activity = activities[binding.transition_id]
            after = fire_binding(net, marking, binding)
            after_snapshot = _snapshot(after)
            participation = tuple((kind, ids) for kind, ids in binding.objects if ids)
            move_weight = weight(binding.objects)
            if activity is None:
                moves.append(
                    (
                        1,
                        binding.transition_id,
                        "",
                        (consumed, after),
                        ObjectAlignmentMove(
                            "silent",
                            None,
                            binding.transition_id,
                            None,
                            binding.objects,
                            move_weight,
                            move_weight * spec.silent_move_cost,
                            before,
                            after_snapshot,
                        ),
                    )
                )
            else:
                for i in enabled_events:
                    event = events[i]
                    if event.activity == activity and event.objects == participation:
                        moves.append(
                            (
                                0,
                                binding.transition_id,
                                event.event_id,
                                (consumed | (1 << i), after),
                                ObjectAlignmentMove(
                                    "synchronous",
                                    event.event_id,
                                    binding.transition_id,
                                    activity,
                                    binding.objects,
                                    move_weight,
                                    move_weight * spec.synchronous_move_cost,
                                    before,
                                    after_snapshot,
                                ),
                            )
                        )
                moves.append(
                    (
                        2,
                        binding.transition_id,
                        "",
                        (consumed, after),
                        ObjectAlignmentMove(
                            "model",
                            None,
                            binding.transition_id,
                            activity,
                            binding.objects,
                            move_weight,
                            move_weight * spec.model_move_cost,
                            before,
                            after_snapshot,
                        ),
                    )
                )
        for i in enabled_events:
            event = events[i]
            move_weight = weight(event.objects)
            moves.append(
                (
                    3,
                    "",
                    event.event_id,
                    (consumed | (1 << i), marking),
                    ObjectAlignmentMove(
                        "log",
                        event.event_id,
                        None,
                        event.activity,
                        event.objects,
                        move_weight,
                        move_weight * spec.log_move_cost,
                        before,
                        before,
                    ),
                )
            )
        for _, _, _, following, move in sorted(moves, key=lambda item: item[:3]):
            candidate = cost + move.cost
            previous = costs.get(following)
            if previous is None or candidate < previous:
                costs[following] = candidate
                parents[following] = state, move
                heappush(heap, (candidate, next(serial), following))
    return finish("unreachable")


def align_object_log(
    log: OCEL | ComputationContext,
    net: ObjectCentricPetriNet,
    spec: ObjectAlignmentSpec,
) -> ComputationResult[ObjectAlignment]:
    """Compute one bounded joint alignment of every event in the explicit scope.

    Supplied model markings are normative inputs, never inferred or filtered.
    A proven unreachable result completes the search; bounded searches return
    PARTIAL with scope coverage and a lower bound, not an invented fitness.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    if not isinstance(spec, ObjectAlignmentSpec):
        raise TypeError("spec must be ObjectAlignmentSpec")
    digest = model_digest(net)
    request = ObjectAlignmentRequest(digest, spec)
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OBJECT_ALIGNMENT_OPERATOR_ID,
            None,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    scope, scope_issues = build_object_event_scope(
        context,
        object_types=spec.object_types,
        qualifiers=spec.qualifiers,
        tie_policy=spec.tie_policy,
    )
    if scope is None:
        return _result(
            OBJECT_ALIGNMENT_OPERATOR_ID,
            context,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            scope_issues,
        )
    model_issues = validate_object_model_scope(net, scope, spec.object_types)
    if model_issues:
        return _result(
            OBJECT_ALIGNMENT_OPERATOR_ID,
            context,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            scope_issues + model_issues,
        )
    alignment = _align_scope(scope, net, spec, digest)
    limited = alignment.status in ("search_limit", "binding_limit")
    issues = scope_issues + (
        ()
        if not limited
        else (
            ComputeIssue(
                "object_alignment_" + alignment.status,
                "Joint search is incomplete; minimum alignment cost is unknown",
                ("scope", spec.scope),
            ),
        )
    )
    return _result(
        OBJECT_ALIGNMENT_OPERATOR_ID,
        context,
        request,
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED,
        alignment,
        issues,
    )


__all__ = (
    "OBJECT_ALIGNMENT_OPERATOR_ID",
    "align_object_log",
    "build_object_event_scope",
    "validate_object_model_scope",
)
