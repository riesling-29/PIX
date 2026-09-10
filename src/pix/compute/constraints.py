"""Explicit trace-local declarative rule monitoring without a mixed-rule score."""

from __future__ import annotations

from datetime import datetime, timedelta

from pix.compute._common import _derived_result
from pix.contracts.analysis import (
    E2OEvidence,
    ObjectTrace,
    TraceEvent,
    TraceSet,
    TraceSpec,
)
from pix.contracts.constraint import (
    ConstraintEvaluation,
    ConstraintRule,
    ConstraintSpec,
    ConstraintWitness,
    CountRule,
    NotCoexistenceRule,
    PrecedenceRule,
    ResponseRule,
    RuleEvaluation,
    TimedResponseRule,
    TraceRuleEvaluation,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.evaluate_constraints"
OPERATOR_VERSION = "1.0.0"


def _micros(later: datetime, earlier: datetime) -> int:
    elapsed = later - earlier
    return (elapsed.days * 86400 + elapsed.seconds) * 1_000_000 + elapsed.microseconds


def _validate_traces(value: TraceSet, spec: TraceSpec) -> tuple[ComputeIssue, ...]:
    if value.object_type != spec.object_type or not isinstance(value.traces, tuple):
        raise ValueError("TraceSet must match its TraceSpec and contain tuple traces")
    identities: set[str] = set()
    known_events: dict[str, tuple[str, datetime]] = {}
    issues: list[ComputeIssue] = []
    for trace in value.traces:
        if not isinstance(trace, ObjectTrace) or not isinstance(trace.events, tuple):
            raise TypeError("TraceSet must contain immutable ObjectTrace records")
        if not isinstance(trace.object_id, str) or not trace.object_id.strip():
            raise ValueError("trace object_id must be nonblank text")
        if trace.object_type != value.object_type or trace.object_id in identities:
            raise ValueError("trace object type must match; object IDs must be unique")
        identities.add(trace.object_id)
        event_ids: set[str] = set()
        previous: TraceEvent | None = None
        for event in trace.events:
            if not isinstance(event, TraceEvent):
                raise TypeError("trace events must be TraceEvent records")
            if not isinstance(event.event_id, str) or not event.event_id.strip():
                raise ValueError("event_id must be nonblank text")
            if not isinstance(event.activity, str) or not event.activity.strip():
                raise ValueError("activity must be nonblank text")
            if event.event_id in event_ids:
                raise ValueError("an event may occur only once within an object trace")
            event_ids.add(event.event_id)
            if not isinstance(
                event.time, datetime
            ) or event.time.utcoffset() != timedelta(0):
                raise ValueError("native trace events require canonical UTC timestamps")
            signature = event.activity, event.time
            if known_events.get(event.event_id, signature) != signature:
                raise ValueError(
                    "shared event IDs must preserve activity and timestamp"
                )
            known_events[event.event_id] = signature
            if not isinstance(event.relations, tuple) or not event.relations:
                raise ValueError("selected trace events require E2O evidence")
            for relation in event.relations:
                if not isinstance(relation, E2OEvidence):
                    raise TypeError("relations must contain E2OEvidence")
                if (
                    relation.event != event.event_id
                    or relation.object != trace.object_id
                ):
                    raise ValueError(
                        "E2O evidence must reference this event and object"
                    )
                if not isinstance(relation.qualifier, str):
                    raise TypeError("E2O qualifier must be text")
                if (
                    spec.qualifiers is not None
                    and relation.qualifier not in spec.qualifiers
                ):
                    raise ValueError("E2O evidence does not match qualifier selection")
            if previous is not None:
                if previous.time > event.time:
                    raise ValueError("trace events must be chronologically ordered")
                if previous.time == event.time:
                    if (
                        spec.tie_policy != "event_id"
                        or previous.event_id >= event.event_id
                    ):
                        raise ValueError(
                            "tied timestamps require explicit lexical event_id order"
                        )
                    issues.append(
                        ComputeIssue(
                            "event_id_order_assumption",
                            "Rule occurrence order uses lexical event IDs for tied timestamps; "
                            "this convention does not establish causal order",
                            (
                                "object",
                                trace.object_id,
                                "events",
                                previous.event_id,
                                event.event_id,
                            ),
                        )
                    )
            previous = event
    return tuple(issues)


def _count(rule: CountRule, trace: ObjectTrace, closed: bool) -> ConstraintWitness:
    evidence = tuple(e.event_id for e in trace.events if e.activity == rule.activity)
    count = len(evidence)
    if rule.max_count is not None and count > rule.max_count:
        status, reason = "violated", "maximum_exceeded"
    elif count < rule.min_count:
        status = "violated" if closed else "pending"
        reason = "minimum_unmet_at_close" if closed else "minimum_not_yet_observed"
    elif not closed and rule.max_count is not None:
        status, reason = "pending", "finite_maximum_requires_closed_observation"
    else:
        status, reason = "fulfilled", "count_within_bounds"
    return ConstraintWitness(status, None, evidence, count, None, reason)


def _not_coexistence(
    rule: NotCoexistenceRule, trace: ObjectTrace, closed: bool
) -> ConstraintWitness:
    present = {event.activity for event in trace.events}
    evidence = tuple(
        e.event_id for e in trace.events if e.activity in (rule.activity, rule.target)
    )
    if rule.activity in present and rule.target in present:
        status, reason = "violated", "forbidden_labels_present"
    elif closed:
        status, reason = "fulfilled", "forbidden_coexistence_absent_at_close"
    else:
        status, reason = "pending", "absence_requires_closed_observation"
    return ConstraintWitness(status, None, evidence, len(evidence), None, reason)


def _activation_witnesses(
    rule: ResponseRule | PrecedenceRule | TimedResponseRule,
    trace: ObjectTrace,
    closed: bool,
) -> tuple[ConstraintWitness, ...]:
    witnesses: list[ConstraintWitness] = []
    precedent = isinstance(rule, PrecedenceRule)
    activator = rule.target if precedent else rule.activity
    response = rule.activity if precedent else rule.target
    for index, activation in enumerate(trace.events):
        if activation.activity != activator:
            continue
        candidates = (
            tuple(event for event in trace.events[:index] if event.activity == response)
            if precedent
            else tuple(
                event
                for event in trace.events[index + 1 :]
                if event.activity == response
            )
        )
        if precedent:
            chosen = candidates[-1] if candidates else None
            status = "fulfilled" if chosen else "violated"
            reason = (
                "prior_activity_observed"
                if chosen
                else "required_prior_activity_absent"
            )
        elif isinstance(rule, TimedResponseRule):
            considered = (
                candidates[:1] if rule.response_selection == "first" else candidates
            )
            chosen = next(
                (
                    event
                    for event in considered
                    if rule.min_microseconds
                    <= _micros(event.time, activation.time)
                    <= rule.max_microseconds
                ),
                None,
            )
            if chosen:
                status, reason = "fulfilled", "response_within_inclusive_window"
            elif considered and rule.response_selection == "first":
                chosen = considered[0]
                status, reason = "violated", "first_response_outside_window"
            elif closed:
                status, reason = "violated", "no_response_in_window_at_close"
            elif (
                _micros(trace.events[-1].time, activation.time) > rule.max_microseconds
            ):
                status, reason = "violated", "observed_prefix_passed_response_deadline"
            else:
                status, reason = "pending", "response_window_not_closed"
        else:
            chosen = candidates[0] if candidates else None
            status = "fulfilled" if chosen else "violated" if closed else "pending"
            reason = (
                "later_response_observed"
                if chosen
                else "response_absent_at_close"
                if closed
                else "future_response_unobserved"
            )
        elapsed = (
            None
            if chosen is None
            else (
                _micros(activation.time, chosen.time)
                if precedent
                else _micros(chosen.time, activation.time)
            )
        )
        evidence = (
            (activation.event_id,)
            if chosen is None
            else (
                (chosen.event_id, activation.event_id)
                if precedent
                else (activation.event_id, chosen.event_id)
            )
        )
        if reason == "observed_prefix_passed_response_deadline":
            evidence = (activation.event_id, trace.events[-1].event_id)
        witnesses.append(
            ConstraintWitness(
                status,
                activation.event_id,
                evidence,
                None,
                elapsed,
                reason,
            )
        )
    return tuple(witnesses)


def _evaluate_rule(
    rule: ConstraintRule, traces: TraceSet, closed: bool
) -> RuleEvaluation:
    rows: list[TraceRuleEvaluation] = []
    object_population = isinstance(rule, (CountRule, NotCoexistenceRule))
    for trace in traces.traces:
        if isinstance(rule, CountRule):
            witnesses = (_count(rule, trace, closed),)
        elif isinstance(rule, NotCoexistenceRule):
            witnesses = (_not_coexistence(rule, trace, closed),)
        else:
            witnesses = _activation_witnesses(rule, trace, closed)
        fulfilled = sum(w.status == "fulfilled" for w in witnesses)
        violated = sum(w.status == "violated" for w in witnesses)
        pending = sum(w.status == "pending" for w in witnesses)
        status = "violated" if violated else "pending" if pending else "fulfilled"
        rows.append(
            TraceRuleEvaluation(
                trace.object_id,
                status,
                len(witnesses),
                fulfilled,
                violated,
                pending,
                not object_population and not witnesses,
                witnesses,
            )
        )
    total = sum(row.activation_count for row in rows)
    fulfilled = sum(row.fulfilled_count for row in rows)
    return RuleEvaluation(
        rule.rule_id,
        rule.kind,
        "object_traces" if object_population else "activations",
        total,
        fulfilled,
        sum(row.violated_count for row in rows),
        sum(row.pending_count for row in rows),
        (fulfilled, total) if total else None,
        len(rows),
        sum(row.status == "fulfilled" for row in rows),
        sum(row.status == "violated" for row in rows),
        sum(row.status == "pending" for row in rows),
        sum(row.vacuous for row in rows),
        tuple(rows),
    )


def evaluate_constraints(
    trace_result: ComputationResult[TraceSet],
    spec: ConstraintSpec,
) -> ComputationResult[ConstraintEvaluation]:
    """Evaluate explicit rules on a complete, validated trace reconstruction.

    COMPUTED includes definite violations. PARTIAL means observed obligations
    remain pending. A partial upstream population is unavailable rather than
    silently measuring its successful subset. No activation denominator is
    synthesized for vacuity or an empty selected object population.
    """
    if not isinstance(trace_result, ComputationResult):
        raise TypeError("trace_result must be ComputationResult[TraceSet]")
    if not isinstance(spec, ConstraintSpec):
        raise TypeError("spec must be ConstraintSpec")
    parents = (trace_result.computation_id,) if trace_result.computation_id else ()

    def result(status, value=None, issues=()):
        return _derived_result(
            OPERATOR_ID,
            trace_result.source_digest,
            spec,
            status,
            value,
            issues,
            parent_computation_ids=parents,
            operator_version=OPERATOR_VERSION,
        )

    if trace_result.status is not ComputeStatus.COMPUTED:
        return result(
            ComputeStatus.INVALID_INPUT
            if trace_result.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "upstream_not_computed",
                    f"Trace reconstruction status is {trace_result.status.value}; "
                    "constraint monitoring requires the complete selected population",
                ),
                *trace_result.issues,
            ),
        )
    if (
        not isinstance(trace_result.value, TraceSet)
        or not isinstance(trace_result.spec, TraceSpec)
        or trace_result.operator_id != "pix.reconstruct_traces"
    ):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "trace_input_required",
                    "Expected native TraceSet reconstruction with explicit TraceSpec",
                ),
            ),
        )
    try:
        issues = (
            *trace_result.issues,
            *_validate_traces(trace_result.value, trace_result.spec),
        )
    except (AttributeError, TypeError, ValueError, OverflowError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_trace_input", str(exc)),),
        )
    value = ConstraintEvaluation(
        trace_result.value.object_type,
        trace_result.computation_id,
        spec.observation_policy,
        tuple(
            _evaluate_rule(
                rule, trace_result.value, spec.observation_policy == "closed"
            )
            for rule in spec.rules
        ),
    )
    if not trace_result.value.traces:
        issues += (
            ComputeIssue(
                "empty_population",
                "No selected object traces; all ratios are unavailable",
            ),
        )
    if any(rule.pending_count for rule in value.rules):
        return result(
            ComputeStatus.PARTIAL,
            value,
            (
                *issues,
                ComputeIssue(
                    "pending_obligations",
                    "Open observation leaves obligations pending; ratios use all "
                    "observed obligations, including pending, and are not final conformance scores",
                ),
            ),
        )
    return result(ComputeStatus.COMPUTED, value, issues)


__all__ = ("OPERATOR_ID", "OPERATOR_VERSION", "evaluate_constraints")
