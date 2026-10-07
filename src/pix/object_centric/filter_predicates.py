"""Typed OCEL predicate evidence, separate from sublog materialization.

Missing values are unknown for equality/ranges and false for ``present``.
Negation changes only known decisions. No canonical OCEL null is invented.
Object lifecycles are observed qualified E2O incidences, not execution cases or
proof of actual creation/termination. Equal boundary timestamps do not order
events; duration is the unordered observed timestamp span in microseconds.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.performance import OCPerformanceSpec, measure_performance
from pix.object_centric.relations import (
    AttributeAsOfSpec,
    OCELScalar,
    object_attributes_as_of,
)
from pix.ocel import OCEL

FILTER_PREDICATES_OPERATOR_ID = "pix.object_centric.evaluate_filter_predicates"
_EVENT_METRICS = frozenset(
    (
        "flow",
        "sojourn",
        "synchronization",
        "pooling",
        "lagging",
        "readiness",
        "service",
        "ready_waiting",
        "first_input_waiting",
        "object_frequency",
    )
)


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("timestamp must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include timezone information")
    return value.astimezone(timezone.utc)


def _typed(value: object) -> OCELScalar:
    if isinstance(value, datetime):
        return OCELScalar("time", timestamp_value=_utc(value))
    if type(value) is bool:
        return OCELScalar("boolean", boolean_value=value)
    if type(value) is int:
        return OCELScalar("integer", integer_value=value)
    if type(value) is float:
        return OCELScalar("float", float_value=value)
    if type(value) is str:
        return OCELScalar("string", text_value=value)
    raise TypeError("value must be a canonical OCEL primitive; null is unsupported")


@dataclass(frozen=True, slots=True)
class OCFilterPredicateSpec:
    """One predicate over events or objects, followed by explicit unknown policy.

    Equality is type-strict, including boolean/integer and integer/float.
    Numeric ranges accept integer/float bounds without converting large integers
    to floats; booleans and times are not numeric. Bounds are closed.

    Object attributes require an explicit fixed ``as_of``; latest future values
    are never substituted. ``present`` tests an actual assignment, not schema
    declaration. Qualifiers restrict incidences: on attributes they restrict the
    population to qualifying participants; on lifecycle they restrict observed
    events and retain empty objects as candidates. Object types restrict objects,
    or the participating-object population for an event-attribute predicate.

    Lifecycle start/end/contains/rework require ``activity`` and use no generic
    comparison value. Start/end need one unique earliest/latest event; contains
    means at least one occurrence; rework means at least two distinct events.
    Duration uses generic equality/range against nonnegative integer microseconds.

    Performance delegates one supported scalar event metric to the nested spec,
    which owns its complete population/profile/qualifier selection. Multi-sample
    elapsed/remaining and aggregate activity_frequency require a separate
    aggregation definition and are deliberately not accepted here.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    mode: Literal[
        "event_attribute", "object_attribute", "object_lifecycle", "performance"
    ]
    comparison: Literal["equals", "numeric_range", "present"] = "equals"
    value: OCELScalar | None = None
    minimum: OCELScalar | None = None
    maximum: OCELScalar | None = None
    attribute: str | None = None
    as_of: datetime | None = None
    as_of_inclusive: bool = True
    lifecycle: Literal["start", "end", "contains", "rework", "duration"] | None = None
    activity: str | None = None
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    positive: bool = True
    unknown: Literal["exclude", "include", "error"] = "exclude"
    performance_spec: OCPerformanceSpec | None = None

    def __post_init__(self) -> None:
        if self.mode not in (
            "event_attribute",
            "object_attribute",
            "object_lifecycle",
            "performance",
        ):
            raise ValueError("unknown predicate mode")
        if self.comparison not in ("equals", "numeric_range", "present"):
            raise ValueError("unknown comparison")
        if self.unknown not in ("exclude", "include", "error"):
            raise ValueError("unknown must be exclude, include or error")
        for name in ("positive", "as_of_inclusive"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in ("object_types", "qualifiers"):
            values = getattr(self, name)
            if values is not None:
                if not isinstance(values, tuple):
                    raise TypeError(f"{name} must be tuple or None")
                for item in values:
                    if name == "qualifiers":
                        if not isinstance(item, str):
                            raise TypeError("qualifiers must contain strings")
                    else:
                        _text(item, name)
                object.__setattr__(self, name, tuple(sorted(set(values))))
        for name in ("value", "minimum", "maximum"):
            scalar = getattr(self, name)
            if scalar is not None:
                if not isinstance(scalar, OCELScalar):
                    raise TypeError(f"{name} must be OCELScalar or None")
                if scalar.kind == "time":
                    object.__setattr__(
                        self,
                        name,
                        replace(scalar, timestamp_value=_utc(scalar.timestamp_value)),
                    )
        attribute_mode = self.mode in ("event_attribute", "object_attribute")
        if attribute_mode:
            _text(self.attribute, "attribute")
        elif self.attribute is not None:
            raise ValueError("attribute is only valid for attribute predicates")
        if self.mode == "object_attribute":
            if self.as_of is None:
                raise ValueError("object attributes require explicit as_of")
            object.__setattr__(self, "as_of", _utc(self.as_of))
        elif self.as_of is not None or not self.as_of_inclusive:
            raise ValueError("as_of parameters are only valid for object attributes")
        lifecycle_activity = (
            self.mode == "object_lifecycle" and self.lifecycle != "duration"
        )
        if self.mode == "object_lifecycle":
            if self.lifecycle not in ("start", "end", "contains", "rework", "duration"):
                raise ValueError(
                    "lifecycle must select start/end/contains/rework/duration"
                )
            if lifecycle_activity:
                _text(self.activity, "activity")
            elif self.activity is not None:
                raise ValueError("duration is the full observed lifecycle span")
        elif self.lifecycle is not None or self.activity is not None:
            raise ValueError("lifecycle/activity are only valid for lifecycle mode")
        if self.mode == "performance":
            if not isinstance(self.performance_spec, OCPerformanceSpec):
                raise TypeError("performance requires OCPerformanceSpec")
            if (
                len(self.performance_spec.metrics) != 1
                or self.performance_spec.metrics[0] not in _EVENT_METRICS
            ):
                raise ValueError(
                    "performance requires exactly one supported event metric"
                )
            if self.performance_spec.profile == "opera":
                raise ValueError(
                    "token-replay performance requires explicit timed replay evidence"
                )
            if self.object_types is not None or self.qualifiers is not None:
                raise ValueError(
                    "performance_spec owns object type and qualifier selection"
                )
        elif self.performance_spec is not None:
            raise ValueError("performance_spec is only valid for performance mode")
        if lifecycle_activity:
            if self.comparison != "equals" or any(
                v is not None for v in (self.value, self.minimum, self.maximum)
            ):
                raise ValueError(
                    "activity lifecycle predicates use activity, without comparison values"
                )
        elif self.comparison == "equals":
            if (
                self.value is None
                or self.minimum is not None
                or self.maximum is not None
            ):
                raise ValueError("equals requires value only")
        elif self.comparison == "numeric_range":
            if self.value is not None or (
                self.minimum is None and self.maximum is None
            ):
                raise ValueError("numeric_range requires minimum and/or maximum only")
            if any(
                v is not None and v.kind not in ("integer", "float")
                for v in (self.minimum, self.maximum)
            ):
                raise ValueError("numeric bounds must have integer or float kind")
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum.native_value > self.maximum.native_value
            ):
                raise ValueError("minimum must not exceed maximum")
        elif any(v is not None for v in (self.value, self.minimum, self.maximum)):
            raise ValueError("present takes no comparison values")
        if self.mode == "performance" or (
            self.mode == "object_lifecycle" and self.lifecycle == "duration"
        ):
            if self.comparison == "present":
                raise ValueError(
                    "duration/performance require explicit numeric conditions"
                )
            for scalar in (self.value, self.minimum, self.maximum):
                if scalar is not None and (
                    scalar.kind != "integer" or scalar.integer_value < 0
                ):
                    raise ValueError(
                        "duration/performance conditions require nonnegative integer bounds"
                    )


@dataclass(frozen=True, slots=True)
class OCFilterPredicateDecision:
    """Raw predicate truth and policy selection, with typed scalar evidence.

    ``matched`` precedes negation. ``selected`` applies ``positive`` to known
    truth only, and applies the request's unknown policy to unknown truth.
    """

    entity_kind: Literal["event", "object"]
    entity_id: str
    matched: bool | None
    selected: bool
    reason: str
    witness_event_ids: tuple[str, ...]
    observed: OCELScalar | None = None
    declared: bool | None = None
    assigned_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.entity_kind not in ("event", "object"):
            raise ValueError("unknown entity kind")
        _text(self.entity_id, "entity_id")
        _text(self.reason, "reason")
        for name in ("matched", "declared"):
            if (
                getattr(self, name) is not None
                and type(getattr(self, name)) is not bool
            ):
                raise TypeError(f"{name} must be bool or None")
        if type(self.selected) is not bool:
            raise TypeError("selected must be bool")
        if self.observed is not None and not isinstance(self.observed, OCELScalar):
            raise TypeError("observed must be OCELScalar or None")
        if (
            not isinstance(self.witness_event_ids, tuple)
            or tuple(sorted(set(self.witness_event_ids))) != self.witness_event_ids
        ):
            raise ValueError("witness_event_ids must be sorted unique tuple")
        for identifier in self.witness_event_ids:
            _text(identifier, "witness event ID")
        if self.assigned_at is not None:
            object.__setattr__(self, "assigned_at", _utc(self.assigned_at))


@dataclass(frozen=True, slots=True)
class OCFilterPredicates:
    selection_unit: Literal["events", "objects"]
    selected_event_ids: tuple[str, ...]
    selected_object_ids: tuple[str, ...]
    unknown_event_ids: tuple[str, ...]
    unknown_object_ids: tuple[str, ...]
    decisions: tuple[OCFilterPredicateDecision, ...]

    def __post_init__(self) -> None:
        if self.selection_unit not in ("events", "objects"):
            raise ValueError("selection_unit must be events or objects")
        if not isinstance(self.decisions, tuple) or any(
            not isinstance(d, OCFilterPredicateDecision) for d in self.decisions
        ):
            raise TypeError("decisions must be an immutable decision tuple")
        kind = "event" if self.selection_unit == "events" else "object"
        ids = tuple(d.entity_id for d in self.decisions)
        if ids != tuple(sorted(set(ids))) or any(
            d.entity_kind != kind for d in self.decisions
        ):
            raise ValueError("decisions must be sorted unique and match selection_unit")
        for name, entity_kind, selected_field in (
            ("selected_event_ids", "event", True),
            ("selected_object_ids", "object", True),
            ("unknown_event_ids", "event", False),
            ("unknown_object_ids", "object", False),
        ):
            ids = getattr(self, name)
            if not isinstance(ids, tuple) or ids != tuple(sorted(set(ids))):
                raise ValueError(f"{name} must be sorted unique tuple")
            expected = tuple(
                d.entity_id
                for d in self.decisions
                if d.entity_kind == entity_kind
                and (d.selected if selected_field else d.matched is None)
            )
            if ids != expected:
                raise ValueError(f"{name} does not agree with decision evidence")


def _compare(
    observed: OCELScalar | None, declared: bool | None, spec: OCFilterPredicateSpec
):
    if spec.comparison == "present":
        return observed is not None, "present" if observed is not None else (
            "attribute_absent" if declared else "attribute_undeclared"
        )
    if observed is None:
        return None, "attribute_absent" if declared else "attribute_undeclared"
    if spec.comparison == "equals":
        matched = (
            observed.kind == spec.value.kind
            and observed.native_value == spec.value.native_value
        )
    else:
        if observed.kind not in ("integer", "float"):
            return None, "non_numeric_attribute"
        matched = (
            spec.minimum is None or observed.native_value >= spec.minimum.native_value
        ) and (
            spec.maximum is None or observed.native_value <= spec.maximum.native_value
        )
    return matched, "matched" if matched else "predicate_false"


def _decision(
    spec,
    kind,
    identifier,
    matched,
    reason,
    witnesses=(),
    observed=None,
    declared=None,
    assigned_at=None,
):
    selected = (
        spec.unknown == "include" if matched is None else matched == spec.positive
    )
    return OCFilterPredicateDecision(
        kind,
        identifier,
        matched,
        selected,
        reason,
        tuple(sorted(set(witnesses))),
        observed,
        declared,
        assigned_at,
    )


def _incidences(context, spec):
    objects = {
        obj.id
        for obj in context.log.objects
        if spec.object_types is None or obj.type in spec.object_types
    }
    event_objects = {event.id: set() for event in context.log.events}
    object_events = {identifier: set() for identifier in objects}
    for relation in context.log.e2o:
        if relation.object in objects and (
            spec.qualifiers is None or relation.qualifier in spec.qualifiers
        ):
            event_objects[relation.event].add(relation.object)
            object_events[relation.object].add(relation.event)
    return event_objects, object_events


def _lifecycle(context, spec, object_events):
    decisions = []
    for identifier, ids in sorted(object_events.items()):
        events = [context.events_by_id[i] for i in sorted(ids)]
        observed = None
        if spec.lifecycle in ("contains", "rework"):
            witnesses = tuple(e.id for e in events if e.type == spec.activity)
            observed = _typed(len(witnesses))
            matched = len(witnesses) >= (1 if spec.lifecycle == "contains" else 2)
            reason = "matched" if matched else "predicate_false"
        elif not events:
            matched, reason, witnesses = None, "no_observed_events", ()
        elif spec.lifecycle == "duration":
            first, last = min(e.time for e in events), max(e.time for e in events)
            delta = last - first
            observed = _typed(
                (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds
            )
            witnesses = tuple(e.id for e in events if e.time in (first, last))
            matched, reason = _compare(observed, None, spec)
        else:
            boundary = (min if spec.lifecycle == "start" else max)(
                e.time for e in events
            )
            witnesses = tuple(e.id for e in events if e.time == boundary)
            if len(witnesses) != 1:
                matched, reason = None, "ambiguous_lifecycle_boundary"
            else:
                observed = _typed(context.events_by_id[witnesses[0]].type)
                matched = observed.text_value == spec.activity
                reason = "matched" if matched else "predicate_false"
        decisions.append(
            _decision(spec, "object", identifier, matched, reason, witnesses, observed)
        )
    return decisions


def evaluate_filter_predicates(
    log: OCEL | ComputationContext, spec: OCFilterPredicateSpec
) -> ComputationResult[OCFilterPredicates]:
    """Evaluate one predicate, retaining unknowns and parent calculation identity.

    Selection IDs cover only the stated selection_unit. Materialization and
    object/event closure belong to filter_ocel, not this evidence operator.
    """
    if not isinstance(spec, OCFilterPredicateSpec):
        raise TypeError("spec must be OCFilterPredicateSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            FILTER_PREDICATES_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    unknown_types = set(spec.object_types or ()) - {
        t.name for t in context.log.object_types
    }
    if unknown_types:
        return _result(
            FILTER_PREDICATES_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(
                ComputeIssue(
                    "unknown_object_type",
                    "Selected type is not declared",
                    ("object_type", t),
                )
                for t in sorted(unknown_types)
            ),
        )
    parents = ()
    issues = ()
    if spec.mode == "performance":
        parent = measure_performance(context, spec.performance_spec)
        parents = (parent.computation_id,)
        if parent.value is None:
            return _result(
                FILTER_PREDICATES_OPERATOR_ID,
                context,
                spec,
                parent.status,
                None,
                parent.issues,
                parent_computation_ids=parents,
            )
        issues = parent.issues
        samples = parent.value.summaries[0].samples
        indexed = {sample.event_id: sample for sample in samples}
        if len(indexed) != len(samples) or set(indexed) != set(
            parent.value.selected_event_ids
        ):
            return _result(
                FILTER_PREDICATES_OPERATOR_ID,
                context,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "ambiguous_performance_population",
                        "Metric must have exactly one sample per selected event",
                    ),
                ),
                parent_computation_ids=parents,
            )
        decisions = []
        for identifier, sample in sorted(indexed.items()):
            observed = None if sample.value is None else _typed(sample.value)
            matched, reason = (
                (None, sample.reason or "unknown_performance")
                if observed is None
                else _compare(observed, None, spec)
            )
            decisions.append(
                _decision(
                    spec,
                    "event",
                    identifier,
                    matched,
                    reason,
                    sample.reference_event_ids,
                    observed,
                )
            )
    else:
        event_objects, object_events = _incidences(context, spec)
        if spec.mode == "object_lifecycle":
            decisions = _lifecycle(context, spec, object_events)
        elif spec.mode == "object_attribute":
            identifiers = tuple(
                sorted(
                    i
                    for i, events in object_events.items()
                    if spec.qualifiers is None or events
                )
            )
            parent = object_attributes_as_of(
                context,
                AttributeAsOfSpec(
                    spec.as_of, identifiers, (spec.attribute,), spec.as_of_inclusive
                ),
            )
            parents = (parent.computation_id,)
            if parent.value is None:
                return _result(
                    FILTER_PREDICATES_OPERATOR_ID,
                    context,
                    spec,
                    parent.status,
                    None,
                    parent.issues,
                    parent_computation_ids=parents,
                )
            decisions = []
            for row in parent.value.values:
                observed = None if row.value is None else _typed(row.value.native_value)
                matched, reason = _compare(observed, row.declared, spec)
                decisions.append(
                    _decision(
                        spec,
                        "object",
                        row.object_id,
                        matched,
                        reason,
                        (),
                        observed,
                        row.declared,
                        row.assigned_at,
                    )
                )
        else:
            declarations = {
                t.name: {a.name for a in t.attributes} for t in context.log.event_types
            }
            decisions = []
            for event in sorted(context.log.events, key=lambda e: e.id):
                if (
                    spec.object_types is not None or spec.qualifiers is not None
                ) and not event_objects[event.id]:
                    continue
                assignment = next(
                    (a for a in event.attributes if a.name == spec.attribute), None
                )
                observed = None if assignment is None else _typed(assignment.value)
                declared = spec.attribute in declarations[event.type]
                matched, reason = _compare(observed, declared, spec)
                decisions.append(
                    _decision(
                        spec,
                        "event",
                        event.id,
                        matched,
                        reason,
                        (event.id,),
                        observed,
                        declared,
                    )
                )
    unknowns = tuple(d for d in decisions if d.matched is None)
    issues += tuple(
        ComputeIssue(
            d.reason,
            "Predicate truth is unknown; policy is " + spec.unknown,
            (d.entity_kind, d.entity_id),
        )
        for d in unknowns
    )
    if unknowns and spec.unknown == "error":
        return _result(
            FILTER_PREDICATES_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            issues,
            parent_computation_ids=parents,
        )
    unit = "events" if spec.mode in ("event_attribute", "performance") else "objects"
    value = OCFilterPredicates(
        unit,
        tuple(
            d.entity_id for d in decisions if d.entity_kind == "event" and d.selected
        ),
        tuple(
            d.entity_id for d in decisions if d.entity_kind == "object" and d.selected
        ),
        tuple(d.entity_id for d in unknowns if d.entity_kind == "event"),
        tuple(d.entity_id for d in unknowns if d.entity_kind == "object"),
        tuple(decisions),
    )
    return _result(
        FILTER_PREDICATES_OPERATOR_ID,
        context,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS = {
    FILTER_PREDICATES_OPERATOR_ID: (
        "object-centric-filter-predicates",
        OCFilterPredicateSpec,
        OCFilterPredicates,
    ),
}

__all__ = [
    "FILTER_PREDICATES_OPERATOR_ID",
    "OCFilterPredicateSpec",
    "OCFilterPredicateDecision",
    "OCFilterPredicates",
    "evaluate_filter_predicates",
]
