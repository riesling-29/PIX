"""Bounded native precision/fitness over concrete-object binding prefixes.

This operator explores observed partial-order prefixes, not arbitrary model
visible histories. A model marking is associated with its complete log downset;
equal token counts or activity labels cannot merge different object histories.
"""

from __future__ import annotations

import json
from collections import deque
from hashlib import sha256

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.compute.object_conformance import (
    build_object_event_scope,
    validate_object_model_scope,
)
from pix.contracts.models import ObjectCentricPetriNet, ObjectMarking
from pix.contracts.object_context import (
    ObjectContextBehavior,
    ObjectContextCoverage,
    ObjectContextEvidence,
    ObjectContextMetrics,
    ObjectContextRequest,
    ObjectContextSpec,
    ObjectHistory,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OBJECT_CONTEXT_OPERATOR_ID = "pix.measure_object_context"


def _ratio(numerator: int, denominator: int) -> tuple[int, int] | None:
    return (numerator, denominator) if denominator else None


def _context_id(histories: tuple[ObjectHistory, ...]) -> str:
    data = [[item.object_id, item.object_type, item.activities] for item in histories]
    encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + sha256(encoded).hexdigest()


def _downsets(predecessors: tuple[int, ...], limit: int):
    """Enumerate each downset once; multiple linearizations carry no weight."""
    queue = deque((0,))
    states = {0}
    successors: dict[int, tuple[int, ...]] = {}
    complete = True
    while queue:
        state = queue.popleft()
        enabled = tuple(
            index
            for index, before in enumerate(predecessors)
            if not state & (1 << index) and before & state == before
        )
        successors[state] = enabled
        for index in enabled:
            following = state | (1 << index)
            if following in states:
                continue
            if len(states) >= limit:
                complete = False
                continue
            states.add(following)
            queue.append(following)
    return (
        tuple(sorted(states, key=lambda state: (state.bit_count(), state))),
        successors,
        complete,
    )


def measure_object_context(
    log: OCEL | ComputationContext,
    net: ObjectCentricPetriNet,
    spec: ObjectContextSpec,
) -> ComputationResult[ObjectContextMetrics]:
    """Compare exact next binding behaviors in the explicitly selected scope.

    Empty-participant observations and model behaviors are outside this metric.
    Terminal prefixes are excluded: these scores do not test final-marking
    acceptance, and are not normalized alignment fitness or OCPA's measure.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    if not isinstance(spec, ObjectContextSpec):
        raise TypeError("spec must be ObjectContextSpec")
    digest = model_digest(net)
    request = ObjectContextRequest(digest, spec)
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OBJECT_CONTEXT_OPERATOR_ID,
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
            OBJECT_CONTEXT_OPERATOR_ID,
            context,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            scope_issues,
        )
    model_issues = validate_object_model_scope(net, scope, spec.object_types)
    if model_issues:
        return _result(
            OBJECT_CONTEXT_OPERATOR_ID,
            context,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            scope_issues + model_issues,
        )
    issues = list(scope_issues)
    excluded = tuple(
        sorted(event.event_id for event in scope.events if not event.objects)
    )
    if excluded:
        issues.append(
            ComputeIssue(
                "context_events_outside_participant_scope",
                "Events with no selected participants are explicitly excluded from this metric",
                excluded,
            )
        )
    events = tuple(
        sorted(
            (event for event in scope.events if event.objects),
            key=lambda event: (
                context.events_by_id[event.event_id].time,
                event.event_id,
            ),
        )
    )
    object_orders: dict[str, list[int]] = {
        object_id: [] for object_id, _ in scope.selected_objects
    }
    predecessors = [0] * len(events)
    for index, event in enumerate(events):
        for _, object_ids in event.objects:
            for object_id in object_ids:
                order = object_orders[object_id]
                if order:
                    predecessors[index] |= 1 << order[-1]
                order.append(index)
    states, successors, log_complete = _downsets(
        tuple(predecessors), spec.max_log_states
    )
    if not log_complete:
        issues.append(
            ComputeIssue(
                "context_log_state_limit",
                "Observed downset enumeration is incomplete; requested context count and full-scope scores are unknown",
            )
        )
    behaviors = tuple(
        ObjectContextBehavior(event.activity, event.objects) for event in events
    )
    transition_activities = {
        transition.id: transition.activity for transition in net.transitions
    }
    seeds: dict[int, set[ObjectMarking]] = {0: {net.initial_marking}}
    tainted: dict[int, set[str]] = {}
    rows: list[ObjectContextEvidence] = []
    terminal_count = 0
    for state in states:
        next_indices = successors[state]
        if not next_indices:
            terminal_count += 1
            continue
        histories = tuple(
            ObjectHistory(
                object_id,
                object_type,
                tuple(
                    events[index].activity
                    for index in object_orders[object_id]
                    if state & (1 << index)
                ),
            )
            for object_id, object_type in scope.selected_objects
        )
        observed = {behaviors[index] for index in next_indices}
        modeled: set[ObjectContextBehavior] = set()
        reasons = set(tainted.get(state, ()))
        if not log_complete:
            reasons.add("log_state_limit")
        known = seeds.pop(state, set())
        queue = deque(sorted(known, key=lambda marking: marking.tokens))
        candidate_count = 0
        # Do not emit speculative model diagnostics after a truncated log
        # population: missing predecessor states could contribute markings.
        if not log_complete:
            queue.clear()
        while queue:
            marking = queue.popleft()
            enumeration = enumerate_enabled_bindings(
                net, marking, max_bindings=spec.max_bindings
            )
            candidate_count += enumeration.candidate_count
            if not enumeration.complete:
                reasons.add("binding_limit")
            for binding in enumeration.bindings:
                activity = transition_activities[binding.transition_id]
                if activity is None:
                    following = fire_binding(net, marking, binding)
                    if following not in known:
                        if len(known) >= spec.max_context_states:
                            reasons.add("context_state_limit")
                        else:
                            known.add(following)
                            queue.append(following)
                    continue
                objects = tuple((kind, ids) for kind, ids in binding.objects if ids)
                if not objects:
                    continue
                behavior = ObjectContextBehavior(activity, objects)
                modeled.add(behavior)
                for index in next_indices:
                    if behaviors[index] != behavior:
                        continue
                    destination = state | (1 << index)
                    if destination not in successors or not successors[destination]:
                        continue
                    following = fire_binding(net, marking, binding)
                    target = seeds.setdefault(destination, set())
                    if following not in target:
                        if len(target) >= spec.max_context_states:
                            tainted.setdefault(destination, set()).add(
                                "context_state_limit"
                            )
                        else:
                            target.add(following)
        if reasons:
            for index in next_indices:
                tainted.setdefault(state | (1 << index), set()).add(
                    "ancestor_context_incomplete"
                )
        matching = observed & modeled
        complete = not reasons
        rows.append(
            ObjectContextEvidence(
                _context_id(histories),
                histories,
                tuple(
                    events[index].event_id
                    for index in range(len(events))
                    if state & (1 << index)
                ),
                tuple(events[index].event_id for index in next_indices),
                tuple(sorted(observed)),
                tuple(sorted(modeled)),
                tuple(sorted(matching)),
                complete,
                tuple(sorted(reasons)),
                len(known),
                candidate_count,
                _ratio(len(matching), len(observed)) if complete else None,
                _ratio(len(matching), len(modeled)) if complete else None,
            )
        )
    completed = tuple(row for row in rows if row.complete)
    intersection = sum(len(row.matching_behaviors) for row in completed)
    observed_count = sum(len(row.observed_behaviors) for row in completed)
    model_count = sum(len(row.model_behaviors) for row in completed)
    full_complete = log_complete and len(completed) == len(rows)
    if not full_complete and log_complete:
        issues.append(
            ComputeIssue(
                "context_model_search_limit",
                "Some contexts or their ancestors have incomplete model reachability; full-scope scores are unavailable",
            )
        )
    if full_complete and (not observed_count or not model_count):
        issues.append(
            ComputeIssue(
                "context_zero_denominator",
                "A zero behavior-set denominator has no ratio; inspect the exact counts",
            )
        )
    value = ObjectContextMetrics(
        digest,
        scope.selected_objects,
        tuple(rows),
        ObjectContextCoverage(
            len(scope.events),
            len(events),
            excluded,
            len(rows) if log_complete else None,
            len(rows),
            len(completed),
            len(rows) - len(completed),
            len(states),
            terminal_count,
            log_complete,
            scope.excluded_object_count,
            scope.excluded_relation_count,
        ),
        intersection,
        observed_count,
        model_count,
        _ratio(intersection, observed_count),
        _ratio(intersection, model_count),
        _ratio(intersection, observed_count) if full_complete else None,
        _ratio(intersection, model_count) if full_complete else None,
    )
    return _result(
        OBJECT_CONTEXT_OPERATOR_ID,
        context,
        request,
        ComputeStatus.COMPUTED if full_complete else ComputeStatus.PARTIAL,
        value,
        tuple(issues),
    )


__all__ = ("OBJECT_CONTEXT_OPERATOR_ID", "measure_object_context")
