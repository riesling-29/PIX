"""Native object-centric rule metrics and constraint graph evaluation.

The default is a CLOSED observed log, all selected objects (including isolated
ones), unique qualified event/object participation, and every activation.
``first_occurrence`` is a separate OCPA-style profile. It compares first A and
first B; it is not Declare response. Boolean negation and <= use mathematics,
not the bugs in the pinned OCPA implementation. Empty populations are unknown.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from math import isfinite
from typing import Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.object_centric.relations import (
    AttributeAsOfSpec,
    OCELScalar,
    object_attributes_as_of,
)
from pix.ocel import OCEL

Comparator = Literal["<", "<=", ">", ">=", "=", "==", "!="]
OccurrenceProfile = Literal["first_occurrence", "every_activation"]
COMPARATORS = ("<", "<=", ">", ">=", "=", "==", "!=")
BOOLEAN_RELATIONS = (
    "existence",
    "non_existence",
    "coexistence",
    "exclusive",
    "choice",
    "xor_choice",
)
ORDER_RELATIONS = ("followed_by", "directly_followed_by", "precedence", "block")
PARTICIPATION_RELATIONS = ("absent", "present", "singular", "multiple", "cardinality")
ALIASES = {
    "exist": "existence",
    "nonexist": "non_existence",
    "coexist": "coexistence",
    "exclusiveness": "exclusive",
    "xorChoice": "xor_choice",
    "cause": "followed_by",
    "directlyCause": "directly_followed_by",
    "precede": "precedence",
}


def _text(value: object, name: str, *, blank: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not blank and not value.strip():
        raise ValueError(f"{name} must not be blank")


def _number(value: object, name: str) -> None:
    if type(value) not in (int, float) or (
        type(value) is float and not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite number, not bool")


def _compare(left: float | int, operator: str, right: float | int) -> bool:
    return {
        "<": lambda: left < right,
        "<=": lambda: left <= right,
        ">": lambda: left > right,
        ">=": lambda: left >= right,
        "=": lambda: left == right,
        "==": lambda: left == right,
        "!=": lambda: left != right,
    }[operator]()


def _condition(operator: str, threshold: float | int) -> None:
    if operator not in COMPARATORS:
        raise ValueError("unsupported comparison operator")
    _number(threshold, "threshold")


def _selection(spec: object) -> None:
    if spec.qualifiers is not None:
        if not isinstance(spec.qualifiers, tuple):
            raise TypeError("qualifiers must be tuple or None")
        for qualifier in spec.qualifiers:
            _text(qualifier, "qualifier", blank=True)
        object.__setattr__(spec, "qualifiers", tuple(sorted(set(spec.qualifiers))))
    if spec.tie_policy not in ("reject", "event_id"):
        raise ValueError("tie_policy must be reject or event_id")
    if spec.occurrence_profile not in ("first_occurrence", "every_activation"):
        raise ValueError("unknown occurrence profile")


@dataclass(frozen=True, slots=True)
class ObjectRuleMetricSpec:
    object_type: str
    activity: str
    relation: str
    target: str | None = None
    occurrence_profile: OccurrenceProfile = "every_activation"
    population: Literal["objects", "activations", "events"] = "objects"
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"
    min_count: int = 0
    max_count: int | None = None

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        _text(self.activity, "activity")
        object.__setattr__(self, "relation", ALIASES.get(self.relation, self.relation))
        if (
            self.relation
            not in BOOLEAN_RELATIONS + ORDER_RELATIONS + PARTICIPATION_RELATIONS
        ):
            raise ValueError("unknown rule relation")
        if self.relation in ORDER_RELATIONS + (
            "coexistence",
            "exclusive",
            "choice",
            "xor_choice",
        ):
            _text(self.target, "target")
        elif self.target is not None:
            raise ValueError("unary relation does not accept target")
        _selection(self)
        if self.population not in ("objects", "activations", "events"):
            raise ValueError("unknown population")
        if (self.relation in PARTICIPATION_RELATIONS) != (self.population == "events"):
            raise ValueError(
                "participation relations require events population; other relations do not"
            )
        if self.population == "activations" and self.relation not in ORDER_RELATIONS:
            raise ValueError("activation population requires ordered relation")
        if type(self.min_count) is not int or self.min_count < 0:
            raise ValueError("min_count must be nonnegative integer")
        if self.max_count is not None and (
            type(self.max_count) is not int or self.max_count < self.min_count
        ):
            raise ValueError("max_count must be integer >= min_count")
        if self.relation != "cardinality" and (
            self.min_count != 0 or self.max_count is not None
        ):
            raise ValueError("cardinality bounds apply only to cardinality relation")


@dataclass(frozen=True, slots=True)
class RuleMetricWitness:
    unit_id: str
    object_id: str | None
    activation_event_id: str | None
    satisfied: bool
    event_ids: tuple[str, ...]
    object_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ObjectRuleMetric:
    relation: str
    population: str
    occurrence_profile: str
    numerator: int
    denominator: int
    metric: float | int | None
    witnesses: tuple[RuleMetricWitness, ...]


def _incidence(context: ComputationContext, qualifiers: tuple[str, ...] | None):
    event_objects = {event.id: set() for event in context.log.events}
    object_events = {obj.id: set() for obj in context.log.objects}
    for relation in context.log.e2o:
        if qualifiers is None or relation.qualifier in qualifiers:
            event_objects[relation.event].add(relation.object)
            object_events[relation.object].add(relation.event)
    return event_objects, object_events


def _ordered(
    context: ComputationContext, object_events: dict, spec: ObjectRuleMetricSpec
):
    rows = {}
    issues = []
    for obj in sorted(context.log.objects, key=lambda item: item.id):
        if obj.type != spec.object_type:
            continue
        events = tuple(
            sorted(
                (context.events_by_id[eid] for eid in object_events[obj.id]),
                key=lambda item: (item.time, item.id),
            )
        )
        if spec.relation in ORDER_RELATIONS:
            for left, right in zip(events, events[1:]):
                if left.time == right.time:
                    issues.append(
                        ComputeIssue(
                            "ambiguous_event_order"
                            if spec.tie_policy == "reject"
                            else "event_id_order_assumption",
                            "Tied event IDs provide a convention, not evidence of causal order",
                            ("object", obj.id, "events", left.id, right.id),
                        )
                    )
        rows[obj.id] = events
    return rows, tuple(issues)


def _activation_results(events: tuple, spec: ObjectRuleMetricSpec):
    labels = tuple(event.type for event in events)
    left = tuple(i for i, label in enumerate(labels) if label == spec.activity)
    right = tuple(i for i, label in enumerate(labels) if label == spec.target)
    activations = right if spec.relation == "precedence" else left
    if spec.occurrence_profile == "first_occurrence":
        activations = activations[:1]
    results = []
    for index in activations:
        candidates = left if spec.relation == "precedence" else right
        if spec.occurrence_profile == "first_occurrence":
            candidates = candidates[:1]
        if spec.relation == "precedence":
            evidence = tuple(i for i in candidates if i < index)
        elif spec.relation == "directly_followed_by":
            evidence = tuple(i for i in candidates if i == index + 1)
        else:
            evidence = tuple(i for i in candidates if i > index)
        satisfied = not evidence if spec.relation == "block" else bool(evidence)
        # The legacy first-occurrence block rejects equal A/B positions.
        if spec.relation == "block" and spec.occurrence_profile == "first_occurrence":
            satisfied = not candidates or candidates[0] < index
        ids = tuple(events[i].id for i in sorted(set((index,) + evidence)))
        results.append((events[index].id, satisfied, ids))
    return results


def _metric(context: ComputationContext, spec: ObjectRuleMetricSpec):
    event_objects, object_events = _incidence(context, spec.qualifiers)
    rows, issues = _ordered(context, object_events, spec)
    if issues and spec.tie_policy == "reject":
        return None, issues
    witnesses = []
    if spec.population == "events":
        for event in sorted(context.log.events, key=lambda item: item.id):
            if event.type != spec.activity:
                continue
            objects = tuple(
                sorted(
                    oid
                    for oid in event_objects[event.id]
                    if context.objects_by_id[oid].type == spec.object_type
                )
            )
            count = len(objects)
            satisfied = {
                "absent": count == 0,
                "present": count > 0,
                "singular": count == 1,
                "multiple": count > 1,
                "cardinality": count >= spec.min_count
                and (spec.max_count is None or count <= spec.max_count),
            }[spec.relation]
            witnesses.append(
                RuleMetricWitness(
                    event.id, None, event.id, satisfied, (event.id,), objects
                )
            )
    else:
        for object_id, events in rows.items():
            labels = {event.type for event in events}
            a, b = spec.activity in labels, spec.target in labels
            if spec.relation in BOOLEAN_RELATIONS:
                satisfied = {
                    "existence": a,
                    "non_existence": not a,
                    "coexistence": a == b,
                    "exclusive": not (a and b),
                    "choice": a or b,
                    "xor_choice": a != b,
                }[spec.relation]
                ids = tuple(
                    event.id
                    for event in events
                    if event.type in (spec.activity, spec.target)
                )
                witnesses.append(
                    RuleMetricWitness(object_id, object_id, None, satisfied, ids)
                )
            else:
                activations = _activation_results(events, spec)
                if spec.population == "objects":
                    witnesses.append(
                        RuleMetricWitness(
                            object_id,
                            object_id,
                            None,
                            all(row[1] for row in activations),
                            tuple(event.id for event in events),
                        )
                    )
                else:
                    witnesses.extend(
                        RuleMetricWitness(
                            f"{object_id}:{event_id}",
                            object_id,
                            event_id,
                            satisfied,
                            ids,
                        )
                        for event_id, satisfied, ids in activations
                    )
    numerator, denominator = sum(row.satisfied for row in witnesses), len(witnesses)
    return ObjectRuleMetric(
        spec.relation,
        spec.population,
        spec.occurrence_profile,
        numerator,
        denominator,
        numerator / denominator if denominator else None,
        tuple(witnesses),
    ), issues


def measure_rule_metric(
    log: OCEL | ComputationContext, spec: ObjectRuleMetricSpec
) -> ComputationResult[ObjectRuleMetric]:
    """Closed-log support with explicit object/event/activation denominator.

    Object population includes vacuously satisfied no-activation objects.
    Activation population excludes them. Timestamp ties reject ordered queries
    unless event_id tie-breaking was explicitly selected. No population -> None.
    """
    if not isinstance(spec, ObjectRuleMetricSpec):
        raise TypeError("spec must be ObjectRuleMetricSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.measure_rule_metric",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    if spec.object_type not in {item.name for item in context.log.object_types}:
        return _result(
            "pix.object_centric.measure_rule_metric",
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("unknown_object_type", "Object type is not declared"),),
        )
    metric, issues = _metric(context, spec)
    return _result(
        "pix.object_centric.measure_rule_metric",
        context,
        spec,
        ComputeStatus.COMPUTED if metric is not None else ComputeStatus.UNAVAILABLE,
        metric,
        issues,
    )


@dataclass(frozen=True, slots=True)
class ActivityNode:
    name: str

    def __post_init__(self):
        _text(self.name, "activity")


@dataclass(frozen=True, slots=True)
class ObjectTypeNode:
    name: str

    def __post_init__(self):
        _text(self.name, "object type")


@dataclass(frozen=True, slots=True)
class FormulaNode:
    measure: str
    comparator: Comparator
    threshold: float | int
    aggregation: Literal["mean", "min", "max", "sum", "median", "count"] = "mean"
    object_type: str | None = None
    unit: str = "microseconds"
    missing_policy: Literal["unknown", "known_only"] = "unknown"

    def __post_init__(self):
        _text(self.measure, "measure")
        _text(self.unit, "unit")
        _condition(self.comparator, self.threshold)
        if self.aggregation not in ("mean", "min", "max", "sum", "median", "count"):
            raise ValueError("unsupported aggregation")
        if self.object_type is not None:
            _text(self.object_type, "object_type")
        if self.missing_policy not in ("unknown", "known_only"):
            raise ValueError("unknown missing-sample policy")


@dataclass(frozen=True, slots=True)
class OAEdge:
    id: str
    source: ObjectTypeNode
    target: ActivityNode
    label: str
    operator: Comparator
    threshold: float | int

    def __post_init__(self):
        _edge(self, ObjectTypeNode, ActivityNode)
        if (
            ALIASES.get(self.label, self.label)
            not in BOOLEAN_RELATIONS[:2] + PARTICIPATION_RELATIONS[:-1]
        ):
            raise ValueError(
                "OA labels are existence/non_existence or object participation metrics; use PerformanceEdge for timing"
            )


@dataclass(frozen=True, slots=True)
class AAEdge:
    """Performance at source activity; target retained as graph annotation.

    Like the OCPA AA evaluator, the metric is NOT a source->target duration.
    Formula with an explicit measure/unit avoids ambiguous agg-label strings.
    """

    id: str
    source: ActivityNode
    target: ActivityNode
    formula: FormulaNode

    def __post_init__(self):
        _text(self.id, "edge id")
        if (
            not isinstance(self.source, ActivityNode)
            or not isinstance(self.target, ActivityNode)
            or not isinstance(self.formula, FormulaNode)
        ):
            raise TypeError("AA edge requires activity nodes and FormulaNode")


@dataclass(frozen=True, slots=True)
class AOAEdge:
    id: str
    source: ActivityNode
    inner: ObjectTypeNode
    target: ActivityNode
    label: str
    operator: Comparator
    threshold: float | int

    def __post_init__(self):
        _edge(self, ActivityNode, ActivityNode)
        if not isinstance(self.inner, ObjectTypeNode):
            raise TypeError("inner must be ObjectTypeNode")
        if (
            ALIASES.get(self.label, self.label)
            not in BOOLEAN_RELATIONS[2:] + ORDER_RELATIONS
        ):
            raise ValueError("unsupported AOA relation")


@dataclass(frozen=True, slots=True)
class ControlFlowEdge:
    """Observed order/choice strengths; 'causal' is an upstream label only."""

    id: str
    source: ActivityNode
    target: ActivityNode
    object_type: str
    label: Literal["causal", "concur", "choice", "skip"]
    threshold: float | int
    operator: Comparator = ">"

    def __post_init__(self):
        _edge(self, ActivityNode, ActivityNode)
        _text(self.object_type, "object_type")
        if self.label not in ("causal", "concur", "choice", "skip"):
            raise ValueError("unsupported control flow label")
        if self.label == "skip" and self.source != self.target:
            raise ValueError("skip requires identical source and target")


@dataclass(frozen=True, slots=True)
class ObjectRelationEdge:
    id: str
    source: ObjectTypeNode
    target: ActivityNode
    label: Literal["absent", "present", "singular", "multiple"]
    threshold: float | int
    operator: Comparator = ">"

    def __post_init__(self):
        _edge(self, ObjectTypeNode, ActivityNode)
        if self.label not in PARTICIPATION_RELATIONS[:-1]:
            raise ValueError("unsupported object relation label")


@dataclass(frozen=True, slots=True)
class PerformanceEdge:
    id: str
    source: FormulaNode
    target: ActivityNode

    def __post_init__(self):
        _text(self.id, "edge id")
        if not isinstance(self.source, FormulaNode) or not isinstance(
            self.target, ActivityNode
        ):
            raise TypeError("performance edge requires formula and activity")


def _edge(edge, source_type, target_type):
    _text(edge.id, "edge id")
    if not isinstance(edge.source, source_type) or not isinstance(
        edge.target, target_type
    ):
        raise TypeError("edge endpoints have incorrect node types")
    _condition(edge.operator, edge.threshold)


@dataclass(frozen=True, slots=True)
class PerformanceObservation:
    """Caller-supplied sample; value/unit/provenance participate in request hash."""

    id: str
    activity: str
    measure: str
    value: float | int | None
    unit: str
    object_type: str | None = None
    source_computation_id: str | None = None
    reason: str | None = None

    def __post_init__(self):
        for name in ("id", "activity", "measure", "unit"):
            _text(getattr(self, name), name)
        if self.value is not None:
            _number(self.value, "value")
        elif self.reason is None:
            raise ValueError("unknown performance sample requires a reason")
        for name in ("object_type", "source_computation_id"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        if self.reason is not None:
            _text(self.reason, "reason")


def performance_observations(
    log: OCEL | ComputationContext,
    result: ComputationResult,
) -> tuple[PerformanceObservation, ...]:
    """Adapt native event-anchored OCPerformance samples with their provenance.

    Unknown samples are retained. Whole-object activity_frequency has no event
    anchor and is rejected; it cannot silently be assigned to one activity.
    """
    from pix.object_centric.performance import (
        PERFORMANCE_OPERATOR_ID,
        OCPerformance,
        OCPerformanceSpec,
    )

    context, issues = _prepare(log)
    if context is None:
        raise ValueError(f"invalid log: {issues}")
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id != PERFORMANCE_OPERATOR_ID
        or not isinstance(result.spec, OCPerformanceSpec)
        or not isinstance(result.value, OCPerformance)
    ):
        raise TypeError("expected a computed native OCPerformance result")
    if result.source_digest != context.source_digest:
        raise ValueError("performance result belongs to a different log")
    if result.computation_id != computation_identity(
        result.operator_id,
        result.operator_version,
        result.source_digest,
        result.spec,
        result.parent_computation_ids,
    ):
        raise ValueError("performance computation identity is invalid")
    observations = []
    for summary in result.value.summaries:
        for index, sample in enumerate(summary.samples):
            if sample.event_id is None:
                raise ValueError(
                    "performance observations require event-anchored samples; exclude activity_frequency"
                )
            if sample.event_id not in context.events_by_id:
                raise ValueError("performance sample event is not in this log")
            observations.append(
                PerformanceObservation(
                    f"{result.computation_id}:{summary.metric}:{index}",
                    context.events_by_id[sample.event_id].type,
                    summary.metric,
                    sample.value,
                    sample.unit,
                    sample.object_type,
                    result.computation_id,
                    sample.reason,
                )
            )
    return tuple(observations)


@dataclass(frozen=True, slots=True)
class ConstraintGraphSpec:
    oa_edges: tuple[OAEdge, ...] = ()
    aa_edges: tuple[AAEdge, ...] = ()
    aoa_edges: tuple[AOAEdge, ...] = ()
    cf_edges: tuple[ControlFlowEdge, ...] = ()
    object_edges: tuple[ObjectRelationEdge, ...] = ()
    performance_edges: tuple[PerformanceEdge, ...] = ()
    observations: tuple[PerformanceObservation, ...] = ()
    occurrence_profile: OccurrenceProfile = "every_activation"
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self):
        _selection(self)
        ids = []
        for name, kind in (
            ("oa_edges", OAEdge),
            ("aa_edges", AAEdge),
            ("aoa_edges", AOAEdge),
            ("cf_edges", ControlFlowEdge),
            ("object_edges", ObjectRelationEdge),
            ("performance_edges", PerformanceEdge),
            ("observations", PerformanceObservation),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(value, kind) for value in values
            ):
                raise TypeError(f"{name} must be a tuple of {kind.__name__}")
            if len({value.id for value in values}) != len(values):
                raise ValueError(f"duplicate {name} id")
            if name != "observations":
                ids.extend(value.id for value in values)
        if len(ids) != len(set(ids)):
            raise ValueError("edge ids must be globally unique")


@dataclass(frozen=True, slots=True)
class ConstraintEdgeEvaluation:
    edge_id: str
    family: str
    metric: float | int | None
    numerator: int | None
    denominator: int
    condition_met: bool | None
    witness_ids: tuple[str, ...]
    reason: str
    unknown_count: int = 0


@dataclass(frozen=True, slots=True)
class ConstraintGraphEvaluation:
    occurrence_profile: str
    edges: tuple[ConstraintEdgeEvaluation, ...]
    triggered_edge_ids: tuple[str, ...]
    unknown_edge_ids: tuple[str, ...]


def _performance(edge_id, family, activity, formula, observations):
    selected = tuple(
        row
        for row in observations
        if row.activity == activity
        and row.measure == formula.measure
        and row.object_type == formula.object_type
        and row.unit == formula.unit
    )
    # Exact binary-float fractions avoid intermediate overflow in a mean or
    # median whose actual answer is finite (e.g. mean(1e308, 1e308)).
    values = sorted(Fraction(row.value) for row in selected if row.value is not None)
    unknown = len(selected) - len(values)
    if unknown and formula.missing_policy == "unknown":
        return ConstraintEdgeEvaluation(
            edge_id,
            family,
            None,
            None,
            len(selected),
            None,
            tuple(row.id for row in selected),
            "unknown_performance_sample",
            unknown,
        )
    if not values:
        exact = None
    elif formula.aggregation == "count":
        exact = Fraction(len(values))
    elif formula.aggregation == "sum":
        exact = sum(values, Fraction())
    elif formula.aggregation == "mean":
        exact = sum(values, Fraction()) / len(values)
    elif formula.aggregation == "min":
        exact = values[0]
    elif formula.aggregation == "max":
        exact = values[-1]
    else:
        exact = (values[(len(values) - 1) // 2] + values[len(values) // 2]) / 2
    reason = (
        "empty_sample"
        if exact is None
        else "known_sample_only"
        if unknown
        else "supplied_observations"
    )
    try:
        value = (
            None
            if exact is None
            else exact.numerator
            if exact.denominator == 1
            else float(exact)
        )
    except OverflowError:
        value, reason = None, "numeric_range_exceeded"
    return ConstraintEdgeEvaluation(
        edge_id,
        family,
        value,
        None,
        len(values),
        None
        if value is None
        else _compare(exact, formula.comparator, formula.threshold),
        tuple(row.id for row in selected),
        reason,
        unknown,
    )


def _cf(context, edge, spec):
    # CF strengths use FIRST occurrence by definition, irrespective of the AOA
    # every-activation profile. Their numeric similarity is not causal evidence.
    query = ObjectRuleMetricSpec(
        edge.object_type,
        edge.source.name,
        "followed_by",
        edge.target.name,
        "first_occurrence",
        "objects",
        spec.qualifiers,
        spec.tie_policy,
    )
    _, object_events = _incidence(context, spec.qualifiers)
    if edge.label in ("choice", "skip"):
        query = ObjectRuleMetricSpec(
            edge.object_type,
            edge.source.name,
            "existence",
            qualifiers=spec.qualifiers,
            tie_policy=spec.tie_policy,
        )
    rows, issues = _ordered(context, object_events, query)
    if issues and spec.tie_policy == "reject":
        return ConstraintEdgeEvaluation(
            edge.id, "CF", None, None, 0, None, (), "ambiguous_event_order"
        ), issues
    n_a = n_b = both = forward = reverse = 0
    witness_ids = []
    for object_id, events in rows.items():
        labels = tuple(event.type for event in events)
        a, b = edge.source.name in labels, edge.target.name in labels
        n_a += a
        n_b += b
        both += a and b
        if a and b:
            forward += labels.index(edge.source.name) < labels.index(edge.target.name)
            reverse += labels.index(edge.target.name) < labels.index(edge.source.name)
        witness_ids.append(object_id)
    if edge.label == "causal":
        numerator, denominator = forward, both
    elif edge.label == "concur":
        numerator, denominator = 2 * min(forward, reverse), forward + reverse
    elif edge.label == "choice":
        numerator, denominator = n_a + n_b - 2 * both, n_a + n_b
    else:
        numerator, denominator = len(rows) - n_a, len(rows)
    metric = numerator / denominator if denominator else None
    return ConstraintEdgeEvaluation(
        edge.id,
        "CF",
        metric,
        numerator,
        denominator,
        None
        if metric is None
        else _compare(Fraction(numerator, denominator), edge.operator, edge.threshold),
        tuple(witness_ids),
        "empty_population" if metric is None else "observed_first_occurrence_strength",
    ), issues


def evaluate_constraint_graph(
    log: OCEL | ComputationContext, spec: ConstraintGraphSpec
) -> ComputationResult[ConstraintGraphEvaluation]:
    """Evaluate all supplied graph predicates; true means the condition matches.

    No universal violation score is fabricated: the caller decides whether a
    predicate is an alert or an acceptance condition. Unknown metrics remain
    None, including absent performance samples. All rows retain denominators.
    """
    if not isinstance(spec, ConstraintGraphSpec):
        raise TypeError("spec must be ConstraintGraphSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.evaluate_constraint_graph",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    evaluations, all_issues = [], []
    declared_types = {item.name for item in context.log.object_types}
    for family, edges in (
        ("OA", spec.oa_edges),
        ("AOA", spec.aoa_edges),
        ("OR", spec.object_edges),
    ):
        for edge in edges:
            relation = ALIASES.get(edge.label, edge.label)
            object_type = edge.inner.name if family == "AOA" else edge.source.name
            activity = edge.source.name if family == "AOA" else edge.target.name
            target = edge.target.name if family == "AOA" else None
            query = ObjectRuleMetricSpec(
                object_type,
                activity,
                relation,
                target,
                spec.occurrence_profile,
                "events" if relation in PARTICIPATION_RELATIONS else "objects",
                spec.qualifiers,
                spec.tie_policy,
            )
            if object_type not in declared_types:
                metric = None
                issues = (
                    ComputeIssue(
                        "unknown_object_type",
                        "Object type is not declared",
                        ("edge", edge.id),
                    ),
                )
            else:
                metric, issues = _metric(context, query)
            all_issues.extend(issues)
            if metric is None:
                evaluations.append(
                    ConstraintEdgeEvaluation(
                        edge.id, family, None, None, 0, None, (), issues[0].code
                    )
                )
            else:
                value = metric.metric
                evaluations.append(
                    ConstraintEdgeEvaluation(
                        edge.id,
                        family,
                        value,
                        metric.numerator,
                        metric.denominator,
                        None
                        if value is None
                        else _compare(
                            Fraction(metric.numerator, metric.denominator),
                            edge.operator,
                            edge.threshold,
                        ),
                        tuple(row.unit_id for row in metric.witnesses if row.satisfied),
                        "empty_population"
                        if value is None
                        else "closed_object_log_metric",
                    )
                )
    for edge in spec.cf_edges:
        if edge.object_type not in declared_types:
            evaluations.append(
                ConstraintEdgeEvaluation(
                    edge.id, "CF", None, None, 0, None, (), "unknown_object_type"
                )
            )
            all_issues.append(
                ComputeIssue(
                    "unknown_object_type",
                    "Object type is not declared",
                    ("edge", edge.id),
                )
            )
        else:
            evaluation, issues = _cf(context, edge, spec)
            evaluations.append(evaluation)
            all_issues.extend(issues)
    for edge in spec.performance_edges:
        evaluations.append(
            _performance(
                edge.id, "PERF", edge.target.name, edge.source, spec.observations
            )
        )
    for edge in spec.aa_edges:
        evaluations.append(
            _performance(
                edge.id, "AA", edge.source.name, edge.formula, spec.observations
            )
        )
    all_issues.extend(
        ComputeIssue(
            "numeric_range_exceeded",
            "Aggregate cannot be represented by a finite output number",
            ("edge", row.edge_id),
        )
        for row in evaluations
        if row.reason == "numeric_range_exceeded"
    )
    all_issues.extend(
        ComputeIssue(
            "unknown_performance_sample",
            "Selected performance population contains unknown samples",
            ("edge", row.edge_id),
        )
        for row in evaluations
        if row.unknown_count
    )
    evaluations.sort(key=lambda row: row.edge_id)
    payload = ConstraintGraphEvaluation(
        spec.occurrence_profile,
        tuple(evaluations),
        tuple(row.edge_id for row in evaluations if row.condition_met is True),
        tuple(row.edge_id for row in evaluations if row.condition_met is None),
    )
    partial = any(issue.code != "event_id_order_assumption" for issue in all_issues)
    parents = tuple(
        sorted(
            {
                row.source_computation_id
                for row in spec.observations
                if row.source_computation_id
            }
        )
    )
    return _result(
        "pix.object_centric.evaluate_constraint_graph",
        context,
        spec,
        ComputeStatus.PARTIAL if partial else ComputeStatus.COMPUTED,
        payload,
        tuple(all_issues),
        parent_computation_ids=parents,
    )


@dataclass(frozen=True, slots=True)
class E2OQualifierSpec:
    activity: str
    object_type: str
    qualifier: str
    attribute: str
    permitted_values: tuple[OCELScalar, ...]
    attribute_profile: Literal["event_as_of", "latest_observed"] = "event_as_of"

    def __post_init__(self):
        for name in ("activity", "object_type", "attribute"):
            _text(getattr(self, name), name)
        _text(self.qualifier, "qualifier", blank=True)
        if not isinstance(self.permitted_values, tuple) or any(
            not isinstance(value, OCELScalar) for value in self.permitted_values
        ):
            raise TypeError("permitted_values must be typed OCELScalar tuple")
        if self.attribute_profile not in ("event_as_of", "latest_observed"):
            raise ValueError("unknown attribute profile")


@dataclass(frozen=True, slots=True)
class O2OQualifierSpec:
    activity: str
    source_type: str
    target_type: str
    allowed_qualifiers: tuple[str, ...]
    qualifier_policy: Literal["all", "any"] = "all"
    include_self: bool = False

    def __post_init__(self):
        for name in ("activity", "source_type", "target_type"):
            _text(getattr(self, name), name)
        if not isinstance(self.allowed_qualifiers, tuple):
            raise TypeError("allowed_qualifiers must be tuple")
        for qualifier in self.allowed_qualifiers:
            _text(qualifier, "qualifier", blank=True)
        object.__setattr__(
            self, "allowed_qualifiers", tuple(sorted(set(self.allowed_qualifiers)))
        )
        if (
            self.qualifier_policy not in ("all", "any")
            or type(self.include_self) is not bool
        ):
            raise ValueError("invalid qualifier policy/include_self")


@dataclass(frozen=True, slots=True)
class QualifierWitness:
    event_id: str
    source_object_id: str
    target_object_id: str | None
    qualifiers: tuple[str, ...]
    value: OCELScalar | None
    assigned_at: datetime | None
    allowed: bool | None
    reason: str


@dataclass(frozen=True, slots=True)
class QualifierConformance:
    relation_kind: str
    profile: str
    population: int
    allowed_count: int
    forbidden_count: int
    unknown_count: int
    known_allowed_fraction: float | None
    witnesses: tuple[QualifierWitness, ...]


def _qualifier_payload(kind, profile, witnesses):
    allowed = sum(row.allowed is True for row in witnesses)
    forbidden = sum(row.allowed is False for row in witnesses)
    return QualifierConformance(
        kind,
        profile,
        len(witnesses),
        allowed,
        forbidden,
        len(witnesses) - allowed - forbidden,
        allowed / (allowed + forbidden) if allowed + forbidden else None,
        tuple(witnesses),
    )


def evaluate_e2o_qualifiers(
    log: OCEL | ComputationContext, spec: E2OQualifierSpec
) -> ComputationResult[QualifierConformance]:
    """Qualified E2O attribute permissions, preserving missing values as unknown.

    event_as_of delegates to the native as-of kernel at each event's timestamp.
    latest_observed is deliberately distinct and may use a future assignment.
    Typed scalar equality prevents Boolean True and Integer 1 being conflated.
    """
    if not isinstance(spec, E2OQualifierSpec):
        raise TypeError("spec must be E2OQualifierSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.evaluate_e2o_qualifiers",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    if spec.object_type not in {item.name for item in context.log.object_types}:
        return _result(
            "pix.object_centric.evaluate_e2o_qualifiers",
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("unknown_object_type", "Object type is not declared"),),
        )
    witnesses = []
    for relation in sorted(
        context.log.e2o, key=lambda row: (row.event, row.object, row.qualifier)
    ):
        event, obj = (
            context.events_by_id[relation.event],
            context.objects_by_id[relation.object],
        )
        if (
            event.type != spec.activity
            or obj.type != spec.object_type
            or relation.qualifier != spec.qualifier
        ):
            continue
        assignments = tuple(
            assignment
            for assignment in obj.attributes
            if assignment.name == spec.attribute
        )
        at = (
            max((assignment.time for assignment in assignments), default=event.time)
            if spec.attribute_profile == "latest_observed"
            else event.time
        )
        snapshot = object_attributes_as_of(
            context, AttributeAsOfSpec(at, (obj.id,), (spec.attribute,))
        ).value.values[0]
        allowed = (
            None if snapshot.value is None else snapshot.value in spec.permitted_values
        )
        witnesses.append(
            QualifierWitness(
                event.id,
                obj.id,
                None,
                (relation.qualifier,),
                snapshot.value,
                snapshot.assigned_at,
                allowed,
                "missing_attribute"
                if allowed is None
                else "typed_attribute_permission",
            )
        )
    payload = _qualifier_payload("E2O", spec.attribute_profile, witnesses)
    return _result(
        "pix.object_centric.evaluate_e2o_qualifiers",
        context,
        spec,
        ComputeStatus.COMPUTED,
        payload,
    )


def evaluate_o2o_qualifiers(
    log: OCEL | ComputationContext, spec: O2OQualifierSpec
) -> ComputationResult[QualifierConformance]:
    """Check static directed O2O qualifiers for co-participant pairs per event.

    Each (event, source, target) is one sample even with several E2O roles or O2O
    qualifiers. A missing O2O edge is forbidden. Static O2O has no inferred valid time.
    """
    if not isinstance(spec, O2OQualifierSpec):
        raise TypeError("spec must be O2OQualifierSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            "pix.object_centric.evaluate_o2o_qualifiers",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    declared = {item.name for item in context.log.object_types}
    if not {spec.source_type, spec.target_type} <= declared:
        return _result(
            "pix.object_centric.evaluate_o2o_qualifiers",
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("unknown_object_type", "Object type is not declared"),),
        )
    event_objects, _ = _incidence(context, None)
    relations = {}
    for relation in context.log.o2o:
        relations.setdefault((relation.source, relation.target), set()).add(
            relation.qualifier
        )
    witnesses = []
    for event in sorted(context.log.events, key=lambda row: row.id):
        if event.type != spec.activity:
            continue
        sources = sorted(
            oid
            for oid in event_objects[event.id]
            if context.objects_by_id[oid].type == spec.source_type
        )
        targets = sorted(
            oid
            for oid in event_objects[event.id]
            if context.objects_by_id[oid].type == spec.target_type
        )
        for source in sources:
            for target in targets:
                if source == target and not spec.include_self:
                    continue
                qualifiers = tuple(sorted(relations.get((source, target), ())))
                permitted = tuple(
                    qualifier in spec.allowed_qualifiers for qualifier in qualifiers
                )
                allowed = bool(qualifiers) and (
                    all(permitted) if spec.qualifier_policy == "all" else any(permitted)
                )
                witnesses.append(
                    QualifierWitness(
                        event.id,
                        source,
                        target,
                        qualifiers,
                        None,
                        None,
                        allowed,
                        "static_directed_relation"
                        if qualifiers
                        else "missing_relation",
                    )
                )
    payload = _qualifier_payload(
        "O2O", f"static_directed_{spec.qualifier_policy}", witnesses
    )
    return _result(
        "pix.object_centric.evaluate_o2o_qualifiers",
        context,
        spec,
        ComputeStatus.COMPUTED,
        payload,
    )


RESULT_SCHEMAS = {
    "pix.object_centric.measure_rule_metric": (
        "object-rule-metric",
        ObjectRuleMetricSpec,
        ObjectRuleMetric,
    ),
    "pix.object_centric.evaluate_constraint_graph": (
        "object-constraint-graph",
        ConstraintGraphSpec,
        ConstraintGraphEvaluation,
    ),
    "pix.object_centric.evaluate_e2o_qualifiers": (
        "e2o-qualifier-conformance",
        E2OQualifierSpec,
        QualifierConformance,
    ),
    "pix.object_centric.evaluate_o2o_qualifiers": (
        "o2o-qualifier-conformance",
        O2OQualifierSpec,
        QualifierConformance,
    ),
}

__all__ = (
    "ObjectRuleMetricSpec",
    "ObjectRuleMetric",
    "RuleMetricWitness",
    "measure_rule_metric",
    "ActivityNode",
    "ObjectTypeNode",
    "FormulaNode",
    "OAEdge",
    "AAEdge",
    "AOAEdge",
    "ControlFlowEdge",
    "ObjectRelationEdge",
    "PerformanceEdge",
    "PerformanceObservation",
    "performance_observations",
    "ConstraintGraphSpec",
    "ConstraintEdgeEvaluation",
    "ConstraintGraphEvaluation",
    "evaluate_constraint_graph",
    "E2OQualifierSpec",
    "O2OQualifierSpec",
    "QualifierWitness",
    "QualifierConformance",
    "evaluate_e2o_qualifiers",
    "evaluate_o2o_qualifiers",
)
