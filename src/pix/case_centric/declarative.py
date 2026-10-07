"""Native finite-trace Declare, log-skeleton and temporal-profile calculations.

These are explicit PIX mathematical profiles, not replicas of implementation
accidents in a reference library. Source event order is preserved. Restricting
candidate activities never removes intermediate events. Open Declare monitoring
reports observed obligations: ``satisfied`` may change after future events;
``pending`` means an observed obligation needs future evidence or case closure.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timezone
from math import isclose, isfinite, sqrt
from statistics import fmean
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_traces

DECLARE_TEMPLATES = (
    "existence",
    "absence",
    "exactly",
    "exactly_one",
    "init",
    "end",
    "responded_existence",
    "response",
    "alternate_response",
    "chain_response",
    "precedence",
    "alternate_precedence",
    "chain_precedence",
    "succession",
    "alternate_succession",
    "chain_succession",
    "coexistence",
    "noncoexistence",
    "not_response",
    "not_precedence",
    "nonsuccession",
    "nonchainsuccession",
)
_ALIASES = {
    "altresponse": "alternate_response",
    "altprecedence": "alternate_precedence",
    "altsuccession": "alternate_succession",
    "chainresponse": "chain_response",
    "chainprecedence": "chain_precedence",
    "chainsuccession": "chain_succession",
}
_UNARY = {"existence", "absence", "exactly", "exactly_one", "init", "end"}
_CARDINALITY = {"existence", "absence", "exactly"}


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _ratio(value, name, *, upper_closed=True):
    if type(value) not in (int, float) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0 or (value > 1 if upper_closed else value >= 1):
        interval = "[0, 1]" if upper_closed else "[0, 1)"
        raise ValueError(f"{name} must lie in {interval}")
    return float(value)


def _trace_spec(value):
    if not isinstance(value, CaseTraceSpec):
        raise TypeError("trace_spec must be CaseTraceSpec")


def _budget(value, name):
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _nonnegative(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _finish(
    operator, mapped, spec, value=None, *, issues=(), partial=False, extra_parent_ids=()
):
    parents = tuple(
        dict.fromkeys(
            (
                *((mapped.computation_id,) if mapped.computation_id else ()),
                *extra_parent_ids,
            )
        )
    )
    if mapped.value is None or mapped.status is not ComputeStatus.COMPUTED:
        return _derived_result(
            operator,
            mapped.source_digest,
            spec,
            ComputeStatus.INVALID_INPUT
            if mapped.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "case_traces_unavailable", "Complete case traces are required"
                ),
                *mapped.issues,
            ),
            parent_computation_ids=parents,
        )
    return _derived_result(
        operator,
        mapped.source_digest,
        spec,
        ComputeStatus.UNAVAILABLE
        if value is None
        else ComputeStatus.PARTIAL
        if partial
        else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
        parent_computation_ids=parents,
    )


@dataclass(frozen=True, slots=True)
class DeclareConstraint:
    """A→B uses source activation for response, target activation for precedence.

    ``existence(n)`` is count≥n; ``absence(n)`` is count<n; ``exactly(n)``
    is count=n. Negative succession forbids every A-before-B occurrence.
    It is deliberately NOT the Boolean negation of positive succession.
    """

    template: str
    source: str
    target: str | None = None
    cardinality: int = 1
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        canonical = _ALIASES.get(self.template, self.template)
        if canonical not in DECLARE_TEMPLATES:
            raise ValueError(f"unsupported Declare template: {self.template!r}")
        object.__setattr__(self, "template", canonical)
        _text(self.source, "source")
        if canonical in _UNARY:
            if self.target is not None:
                raise ValueError("unary template does not accept target")
        else:
            _text(self.target, "target")
            if self.source == self.target:
                raise ValueError("binary Declare activities must be distinct")
        if type(self.cardinality) is not int or self.cardinality < 0:
            raise ValueError("cardinality must be a nonnegative integer")
        if canonical not in _CARDINALITY and self.cardinality != 1:
            raise ValueError(
                "cardinality is only configurable for existence/absence/exactly"
            )


@dataclass(frozen=True, slots=True)
class DeclareObligation:
    kind: str
    activation_index: int | None
    state: str
    witness_indices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class DeclareTraceEvaluation:
    case_id: str
    rule_index: int
    state: str
    obligations: tuple[DeclareObligation, ...]


@dataclass(frozen=True, slots=True)
class DeclareRuleEvidence:
    rule: DeclareConstraint
    activated_cases: int
    satisfied_cases: int
    vacuous_cases: int
    support: float
    confidence: float | None

    def __post_init__(self):
        if not isinstance(self.rule, DeclareConstraint):
            raise TypeError("rule must be DeclareConstraint")
        for name in ("activated_cases", "satisfied_cases", "vacuous_cases"):
            _nonnegative(getattr(self, name), name)
        if self.satisfied_cases > self.activated_cases:
            raise ValueError("satisfied cases cannot exceed activated cases")
        object.__setattr__(self, "support", _ratio(self.support, "support"))
        if self.confidence is not None:
            object.__setattr__(
                self, "confidence", _ratio(self.confidence, "confidence")
            )
        if (self.activated_cases == 0) != (self.confidence is None):
            raise ValueError(
                "confidence must be None exactly when activation denominator is zero"
            )
        if self.activated_cases and not isclose(
            self.confidence,
            self.satisfied_cases / self.activated_cases,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            raise ValueError("confidence does not match case counts")


@dataclass(frozen=True, slots=True)
class DeclareDiscoverySpec:
    templates: tuple[str, ...] = (
        "existence",
        "absence",
        "exactly_one",
        "init",
        "response",
        "precedence",
        "succession",
        "alternate_response",
        "alternate_precedence",
        "alternate_succession",
        "chain_response",
        "chain_precedence",
        "chain_succession",
        "responded_existence",
        "coexistence",
        "noncoexistence",
        "nonsuccession",
        "nonchainsuccession",
    )
    activities: tuple[str, ...] = ()
    min_support: float = 0.1
    min_confidence: float = 1.0
    cardinality: int = 1
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_candidate_rules: int = 100_000

    def __post_init__(self):
        _trace_spec(self.trace_spec)
        _budget(self.max_candidate_rules, "max_candidate_rules")
        for field in ("templates", "activities"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or not all(
                isinstance(x, str) for x in value
            ):
                raise TypeError(f"{field} must be a tuple of strings")
            if len(set(value)) != len(value):
                raise ValueError(f"duplicate {field}")
        canonical = tuple(_ALIASES.get(x, x) for x in self.templates)
        if not canonical or any(x not in DECLARE_TEMPLATES for x in canonical):
            raise ValueError("templates must select supported Declare templates")
        if len(set(canonical)) != len(canonical):
            raise ValueError("duplicate template aliases")
        object.__setattr__(self, "templates", canonical)
        for activity in self.activities:
            _text(activity, "activity")
        object.__setattr__(self, "min_support", _ratio(self.min_support, "min_support"))
        object.__setattr__(
            self, "min_confidence", _ratio(self.min_confidence, "min_confidence")
        )
        if type(self.cardinality) is not int or self.cardinality < 0:
            raise ValueError("cardinality must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class DeclareModel:
    activities: tuple[str, ...]
    rules: tuple[DeclareConstraint, ...]
    evidence: tuple[DeclareRuleEvidence, ...] = ()
    case_count: int = 0
    profile: str = "pix.finite-trace-declare.v1"

    def __post_init__(self):
        _nonnegative(self.case_count, "case_count")
        if not isinstance(self.rules, tuple) or not all(
            isinstance(x, DeclareConstraint) for x in self.rules
        ):
            raise TypeError("rules must be a tuple of DeclareConstraint")
        if len(set(self.rules)) != len(self.rules):
            raise ValueError("duplicate Declare rules")
        if not isinstance(self.activities, tuple) or not all(
            isinstance(x, str) and x.strip() for x in self.activities
        ):
            raise TypeError("activities must be a tuple of nonblank strings")
        if len(set(self.activities)) != len(self.activities):
            raise ValueError("duplicate activities")
        if any(
            r.source not in self.activities
            or (r.target is not None and r.target not in self.activities)
            for r in self.rules
        ):
            raise ValueError("rule activities must belong to the model alphabet")
        if self.profile != "pix.finite-trace-declare.v1":
            raise ValueError("unsupported Declare profile")
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(x, DeclareRuleEvidence) for x in self.evidence
        ):
            raise TypeError("evidence must be a tuple of DeclareRuleEvidence")
        if self.evidence and tuple(x.rule for x in self.evidence) != self.rules:
            raise ValueError("evidence must correspond to model rules in order")
        for evidence in self.evidence:
            if evidence.activated_cases + evidence.vacuous_cases != self.case_count:
                raise ValueError("evidence case counts disagree with model population")
            expected = (
                evidence.activated_cases / self.case_count if self.case_count else 0
            )
            if not isclose(evidence.support, expected, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("support does not match case counts")


@dataclass(frozen=True, slots=True)
class DeclareConformanceSpec:
    observation: str = "closed"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_obligations: int = 1_000_000

    def __post_init__(self):
        _trace_spec(self.trace_spec)
        _budget(self.max_obligations, "max_obligations")
        if self.observation not in ("closed", "open"):
            raise ValueError("observation must be closed or open")


@dataclass(frozen=True, slots=True)
class DeclareConformanceRequest:
    model: DeclareModel
    options: DeclareConformanceSpec


@dataclass(frozen=True, slots=True)
class DeclareConformance:
    evaluations: tuple[DeclareTraceEvaluation, ...]
    case_count: int
    rule_count: int
    fit_case_ids: tuple[str, ...]
    violating_case_ids: tuple[str, ...]
    pending_case_ids: tuple[str, ...]
    observation: str


def _obligations(sequence, rule, closed):
    a = tuple(i for i, x in enumerate(sequence) if x == rule.source)
    b = tuple(i for i, x in enumerate(sequence) if x == rule.target)
    template = rule.template
    pending = "violated" if closed else "pending"

    def obligation(kind, index, state, witnesses=()):
        return DeclareObligation(kind, index, state, tuple(witnesses))

    if template in _UNARY:
        count = len(a)
        if template == "existence":
            state = "satisfied" if count >= rule.cardinality else pending
        elif template == "absence":
            state = "satisfied" if count < rule.cardinality else "violated"
        elif template in ("exactly", "exactly_one"):
            target_count = rule.cardinality if template == "exactly" else 1
            state = (
                "satisfied"
                if count == target_count
                else "violated"
                if count > target_count
                else pending
            )
        elif template == "init":
            state = (
                ("satisfied" if sequence[0] == rule.source else "violated")
                if sequence
                else pending
            )
        else:
            state = (
                "pending"
                if not closed
                else "satisfied"
                if sequence and sequence[-1] == rule.source
                else "violated"
            )
        return (obligation(template, None, state, a),)

    if template in ("succession", "alternate_succession", "chain_succession"):
        prefix = {
            "succession": "",
            "alternate_succession": "alternate_",
            "chain_succession": "chain_",
        }[template]
        return (
            *_obligations(
                sequence,
                DeclareConstraint(prefix + "response", rule.source, rule.target),
                closed,
            ),
            *_obligations(
                sequence,
                DeclareConstraint(prefix + "precedence", rule.source, rule.target),
                closed,
            ),
        )
    if template == "coexistence":
        return (
            *_obligations(
                sequence,
                DeclareConstraint("responded_existence", rule.source, rule.target),
                closed,
            ),
            *_obligations(
                sequence,
                DeclareConstraint("responded_existence", rule.target, rule.source),
                closed,
            ),
        )
    if template == "noncoexistence":
        return tuple(
            obligation(template, i, "violated" if b else "satisfied", b[:1]) for i in a
        ) + tuple(
            obligation(template, i, "violated" if a else "satisfied", a[:1]) for i in b
        )

    outcomes = []
    if template in (
        "precedence",
        "alternate_precedence",
        "chain_precedence",
        "not_precedence",
    ):
        previous_b = -1
        for i in b:
            position = bisect_left(a, i) - 1
            earlier = a[position] if position >= 0 else None
            if template == "alternate_precedence":
                witnesses = (
                    (earlier,) if earlier is not None and earlier > previous_b else ()
                )
            elif template == "chain_precedence":
                witnesses = (earlier,) if earlier == i - 1 else ()
            else:
                witnesses = (earlier,) if earlier is not None else ()
            fulfilled = (
                not witnesses if template == "not_precedence" else bool(witnesses)
            )
            outcomes.append(
                obligation(
                    template, i, "satisfied" if fulfilled else "violated", witnesses
                )
            )
            previous_b = i
        return tuple(outcomes)

    for ordinal, i in enumerate(a):
        position = bisect_right(b, i)
        later = b[position] if position < len(b) else None
        if template == "responded_existence":
            witnesses = b[:1]
            state = "satisfied" if witnesses else pending
        elif template == "response":
            witnesses = (later,) if later is not None else ()
            state = "satisfied" if witnesses else pending
        elif template == "alternate_response":
            next_a = a[ordinal + 1] if ordinal + 1 < len(a) else len(sequence)
            witnesses = (later,) if later is not None and later < next_a else ()
            state = (
                "satisfied"
                if witnesses
                else "violated"
                if next_a < len(sequence)
                else pending
            )
        elif template == "chain_response":
            witnesses = (later,) if later == i + 1 else ()
            state = (
                "satisfied"
                if witnesses
                else "violated"
                if i + 1 < len(sequence)
                else pending
            )
        elif template in ("not_response", "nonsuccession"):
            witnesses = (later,) if later is not None else ()
            state = "violated" if witnesses else "satisfied"
        elif template == "nonchainsuccession":
            witnesses = (later,) if later == i + 1 else ()
            state = "violated" if witnesses else "satisfied"
        else:
            raise ValueError(f"unsupported template {template!r}")
        outcomes.append(obligation(template, i, state, witnesses))
    return tuple(outcomes)


def _state(obligations):
    states = {x.state for x in obligations}
    return (
        "violated"
        if "violated" in states
        else "pending"
        if "pending" in states
        else "satisfied"
        if states
        else "vacuous"
    )


def discover_declare(
    log: CaseLog, spec: DeclareDiscoverySpec = DeclareDiscoverySpec()
) -> ComputationResult[DeclareModel]:
    """Discover closed-case rules by activation-case support and confidence.

    Support = activated cases / all cases; confidence = satisfied activated
    cases / activated cases. Vacuous binary cases never inflate confidence.
    Unary rules have one case-level obligation per case. No rule is learned
    from an empty population, even when thresholds are zero.
    """
    if not isinstance(spec, DeclareDiscoverySpec):
        raise TypeError("spec must be DeclareDiscoverySpec")
    mapped = case_traces(log, spec.trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.discover_declare", mapped, spec)
    sequences = tuple(tuple(e.activity for e in t.events) for t in mapped.value.traces)
    if not sequences:
        return _finish(
            "pix.case_centric.discover_declare",
            mapped,
            spec,
            issues=(
                ComputeIssue("empty_population", "Declare discovery requires cases"),
            ),
        )
    activities = spec.activities or tuple(
        sorted({x for sequence in sequences for x in sequence})
    )
    candidate_count = sum(
        len(activities)
        if t in _UNARY
        else len(activities) * max(0, len(activities) - 1)
        for t in spec.templates
    )
    if candidate_count > spec.max_candidate_rules:
        return _finish(
            "pix.case_centric.discover_declare",
            mapped,
            spec,
            issues=(
                ComputeIssue(
                    "candidate_rule_limit",
                    f"{candidate_count} rule candidates exceed limit {spec.max_candidate_rules}; no partial model was inferred",
                ),
            ),
        )
    evidence = []
    for template in spec.templates:
        for source in activities:
            targets = (
                (None,)
                if template in _UNARY
                else tuple(x for x in activities if x != source)
            )
            for target in targets:
                rule = DeclareConstraint(
                    template,
                    source,
                    target,
                    spec.cardinality if template in _CARDINALITY else 1,
                )
                states = Counter(
                    _state(_obligations(sequence, rule, True)) for sequence in sequences
                )
                activated = len(sequences) - states["vacuous"]
                support = activated / len(sequences)
                confidence = states["satisfied"] / activated if activated else None
                if (
                    confidence is not None
                    and support >= spec.min_support
                    and confidence >= spec.min_confidence
                ):
                    evidence.append(
                        DeclareRuleEvidence(
                            rule,
                            activated,
                            states["satisfied"],
                            states["vacuous"],
                            support,
                            confidence,
                        )
                    )
    model = DeclareModel(
        activities, tuple(e.rule for e in evidence), tuple(evidence), len(sequences)
    )
    return _finish("pix.case_centric.discover_declare", mapped, spec, model)


def check_declare(
    log: CaseLog,
    model: DeclareModel,
    spec: DeclareConformanceSpec = DeclareConformanceSpec(),
) -> ComputationResult[DeclareConformance]:
    """Evaluate every activation, retaining one sufficient binary witness each.

    Witnesses demonstrate fulfillment or a counterexample; they are not the
    Cartesian product of all matching event pairs. Every activation is kept.
    """
    if not isinstance(model, DeclareModel) or not isinstance(
        spec, DeclareConformanceSpec
    ):
        raise TypeError("expected DeclareModel and DeclareConformanceSpec")
    request = DeclareConformanceRequest(model, spec)
    mapped = case_traces(log, spec.trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.check_declare", mapped, request)
    obligation_count = 0
    for trace in mapped.value.traces:
        counts = Counter(e.activity for e in trace.events)
        for rule in model.rules:
            if rule.template in _UNARY:
                obligation_count += 1
            elif rule.template in (
                "succession",
                "alternate_succession",
                "chain_succession",
                "coexistence",
                "noncoexistence",
            ):
                obligation_count += counts[rule.source] + counts[rule.target]
            elif rule.template in (
                "precedence",
                "alternate_precedence",
                "chain_precedence",
                "not_precedence",
            ):
                obligation_count += counts[rule.target]
            else:
                obligation_count += counts[rule.source]
    if obligation_count > spec.max_obligations:
        return _finish(
            "pix.case_centric.check_declare",
            mapped,
            request,
            issues=(
                ComputeIssue(
                    "declare_obligation_limit",
                    f"{obligation_count} obligations exceed limit {spec.max_obligations}; no activation was dropped",
                ),
            ),
        )
    evaluations, fit, violated, pending_cases = [], [], [], []
    for trace in mapped.value.traces:
        sequence = tuple(e.activity for e in trace.events)
        case_states = set()
        for i, rule in enumerate(model.rules):
            obligations = _obligations(sequence, rule, spec.observation == "closed")
            state = _state(obligations)
            case_states.add(state)
            evaluations.append(
                DeclareTraceEvaluation(trace.object_id, i, state, obligations)
            )
        if "violated" in case_states:
            violated.append(trace.object_id)
        elif "pending" in case_states:
            pending_cases.append(trace.object_id)
        else:
            fit.append(trace.object_id)
    has_pending = any(x.state == "pending" for e in evaluations for x in e.obligations)
    issues = (
        (
            ComputeIssue(
                "pending_obligations",
                "Observed open-case obligations need future events or case closure",
            ),
        )
        if has_pending
        else ()
    )
    value = DeclareConformance(
        tuple(evaluations),
        len(mapped.value.traces),
        len(model.rules),
        tuple(fit),
        tuple(violated),
        tuple(pending_cases),
        spec.observation,
    )
    return _finish(
        "pix.case_centric.check_declare",
        mapped,
        request,
        value,
        issues=issues,
        partial=has_pending,
    )


SKELETON_RELATIONS = (
    "equivalence",
    "always_after",
    "always_before",
    "never_together",
    "directly_follows",
)


@dataclass(frozen=True, slots=True)
class SkeletonRelation:
    kind: str
    source: str
    target: str
    fulfilled: int = 0
    eligible: int = 0

    def __post_init__(self):
        if self.kind not in SKELETON_RELATIONS or self.source == self.target:
            raise ValueError("invalid skeleton relation")
        _text(self.source, "source")
        _text(self.target, "target")
        _nonnegative(self.fulfilled, "fulfilled")
        _nonnegative(self.eligible, "eligible")
        if self.fulfilled > self.eligible:
            raise ValueError("fulfilled cannot exceed eligible")


@dataclass(frozen=True, slots=True)
class ActivityFrequency:
    activity: str
    allowed_counts: tuple[int, ...]
    distribution: tuple[tuple[int, int], ...] = ()

    def __post_init__(self):
        _text(self.activity, "activity")
        if (
            not isinstance(self.allowed_counts, tuple)
            or not self.allowed_counts
            or any(type(x) is not int or x < 0 for x in self.allowed_counts)
        ):
            raise ValueError(
                "allowed_counts must be a nonempty tuple of nonnegative integers"
            )
        if tuple(sorted(set(self.allowed_counts))) != self.allowed_counts:
            raise ValueError("allowed_counts must be sorted and unique")
        if not isinstance(self.distribution, tuple) or any(
            not isinstance(x, tuple)
            or len(x) != 2
            or type(x[0]) is not int
            or x[0] < 0
            or type(x[1]) is not int
            or x[1] <= 0
            for x in self.distribution
        ):
            raise ValueError(
                "distribution must contain nonnegative count and positive case-frequency pairs"
            )
        if tuple(sorted(self.distribution)) != self.distribution or len(
            {x[0] for x in self.distribution}
        ) != len(self.distribution):
            raise ValueError("distribution must be ordered by unique event count")
        if self.distribution and not set(self.allowed_counts) <= {
            x[0] for x in self.distribution
        }:
            raise ValueError("allowed counts must appear in the empirical distribution")


@dataclass(frozen=True, slots=True)
class LogSkeletonSpec:
    noise_threshold: float = 0.0
    activities: tuple[str, ...] = ()
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_relation_candidates: int = 100_000

    def __post_init__(self):
        _trace_spec(self.trace_spec)
        _budget(self.max_relation_candidates, "max_relation_candidates")
        object.__setattr__(
            self,
            "noise_threshold",
            _ratio(self.noise_threshold, "noise_threshold", upper_closed=False),
        )
        if not isinstance(self.activities, tuple) or any(
            not isinstance(x, str) or not x.strip() for x in self.activities
        ):
            raise TypeError("activities must be a tuple of nonblank strings")
        if len(set(self.activities)) != len(self.activities):
            raise ValueError("duplicate activities")


@dataclass(frozen=True, slots=True)
class LogSkeleton:
    activities: tuple[str, ...]
    relations: tuple[SkeletonRelation, ...]
    activity_frequencies: tuple[ActivityFrequency, ...]
    case_count: int = 0
    noise_threshold: float = 0.0
    profile: str = "pix.activation-log-skeleton.v1"

    def __post_init__(self):
        object.__setattr__(
            self,
            "noise_threshold",
            _ratio(self.noise_threshold, "noise_threshold", upper_closed=False),
        )
        _nonnegative(self.case_count, "case_count")
        if self.profile != "pix.activation-log-skeleton.v1":
            raise ValueError("unsupported skeleton profile")
        if not isinstance(self.activities, tuple) or len(set(self.activities)) != len(
            self.activities
        ):
            raise ValueError("activities must be unique tuple")
        for activity in self.activities:
            _text(activity, "activity")
        if not isinstance(self.relations, tuple) or any(
            not isinstance(r, SkeletonRelation) for r in self.relations
        ):
            raise TypeError("relations must be tuple[SkeletonRelation]")
        if any(
            r.source not in self.activities or r.target not in self.activities
            for r in self.relations
        ):
            raise ValueError("unknown skeleton relation activity")
        semantic_keys = tuple(
            (
                r.kind,
                *(
                    sorted((r.source, r.target))
                    if r.kind in ("equivalence", "never_together")
                    else (r.source, r.target)
                ),
            )
            for r in self.relations
        )
        if len(set(semantic_keys)) != len(semantic_keys):
            raise ValueError("duplicate semantic skeleton relations")
        if not isinstance(self.activity_frequencies, tuple) or any(
            not isinstance(f, ActivityFrequency) for f in self.activity_frequencies
        ):
            raise TypeError("activity_frequencies must be tuple[ActivityFrequency]")
        if set(f.activity for f in self.activity_frequencies) != set(
            self.activities
        ) or len(self.activity_frequencies) != len(self.activities):
            raise ValueError("frequency domains must cover each activity exactly once")
        if any(
            f.distribution and sum(n for _, n in f.distribution) != self.case_count
            for f in self.activity_frequencies
        ):
            raise ValueError("frequency distribution disagrees with case population")


@dataclass(frozen=True, slots=True)
class SkeletonDeviation:
    kind: str
    source: str
    target: str | None = None
    activation_indices: tuple[int, ...] = ()
    observed_count: int | None = None
    allowed_counts: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SkeletonTraceEvaluation:
    case_id: str
    checked_constraints: int
    deviations: tuple[SkeletonDeviation, ...]
    fitness: float | None

    @property
    def is_fit(self):
        return not self.deviations


@dataclass(frozen=True, slots=True)
class SkeletonConformance:
    traces: tuple[SkeletonTraceEvaluation, ...]
    fit_case_count: int
    case_count: int


@dataclass(frozen=True, slots=True)
class SkeletonConformanceRequest:
    model: LogSkeleton
    trace_spec: CaseTraceSpec


def _skeleton_obligations(sequence, kind, source, target):
    if kind in ("equivalence", "never_together"):
        ca, cb = sequence.count(source), sequence.count(target)
        if not ca and not cb:
            return ()
        fulfilled = ca == cb if kind == "equivalence" else not (ca and cb)
        return ((None, fulfilled),)
    a = tuple(i for i, x in enumerate(sequence) if x == source)
    b = tuple(i for i, x in enumerate(sequence) if x == target)
    if kind == "always_after":
        return tuple((i, bool(b) and b[-1] > i) for i in a)
    if kind == "always_before":
        return tuple((i, bool(b) and b[0] < i) for i in a)
    return tuple((i, i + 1 < len(sequence) and sequence[i + 1] == target) for i in a)


def discover_log_skeleton(
    log: CaseLog, spec: LogSkeletonSpec = LogSkeletonSpec()
) -> ComputationResult[LogSkeleton]:
    """Learn six constraint families with explicit denominator semantics.

    Temporal/directed relations use every source occurrence. Equivalence and
    exclusion use cases with either activity. Frequency domains retain the most
    common counts until cumulative case mass reaches 1-noise, ties by count.
    """
    if not isinstance(spec, LogSkeletonSpec):
        raise TypeError("spec must be LogSkeletonSpec")
    mapped = case_traces(log, spec.trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.discover_log_skeleton", mapped, spec)
    sequences = tuple(tuple(e.activity for e in t.events) for t in mapped.value.traces)
    if not sequences:
        return _finish(
            "pix.case_centric.discover_log_skeleton",
            mapped,
            spec,
            issues=(
                ComputeIssue(
                    "empty_population", "Log-skeleton discovery requires cases"
                ),
            ),
        )
    activities = spec.activities or tuple(sorted({x for s in sequences for x in s}))
    candidate_count = 4 * len(activities) * max(0, len(activities) - 1)
    if candidate_count > spec.max_relation_candidates:
        return _finish(
            "pix.case_centric.discover_log_skeleton",
            mapped,
            spec,
            issues=(
                ComputeIssue(
                    "candidate_relation_limit",
                    f"{candidate_count} relation candidates exceed limit {spec.max_relation_candidates}; no partial model was inferred",
                ),
            ),
        )
    relations, frequencies = [], []
    for kind in SKELETON_RELATIONS:
        for a in activities:
            for b in activities:
                if a == b or (kind in ("equivalence", "never_together") and a > b):
                    continue
                outcomes = tuple(
                    outcome
                    for sequence in sequences
                    for outcome in _skeleton_obligations(sequence, kind, a, b)
                )
                fulfilled = sum(ok for _, ok in outcomes)
                if outcomes and fulfilled / len(outcomes) >= 1 - spec.noise_threshold:
                    relations.append(
                        SkeletonRelation(kind, a, b, fulfilled, len(outcomes))
                    )
    for activity in activities:
        distribution = Counter(s.count(activity) for s in sequences)
        selected, mass = [], 0
        for count, frequency in sorted(
            distribution.items(), key=lambda item: (-item[1], item[0])
        ):
            selected.append(count)
            mass += frequency
            if mass / len(sequences) >= 1 - spec.noise_threshold:
                break
        frequencies.append(
            ActivityFrequency(
                activity, tuple(sorted(selected)), tuple(sorted(distribution.items()))
            )
        )
    value = LogSkeleton(
        activities,
        tuple(relations),
        tuple(frequencies),
        len(sequences),
        spec.noise_threshold,
    )
    return _finish("pix.case_centric.discover_log_skeleton", mapped, spec, value)


def check_log_skeleton(
    log: CaseLog, model: LogSkeleton, trace_spec: CaseTraceSpec = CaseTraceSpec()
) -> ComputationResult[SkeletonConformance]:
    """Check every discovered relation and activity-count domain on closed cases."""
    if not isinstance(model, LogSkeleton):
        raise TypeError("model must be LogSkeleton")
    _trace_spec(trace_spec)
    request = SkeletonConformanceRequest(model, trace_spec)
    mapped = case_traces(log, trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.check_log_skeleton", mapped, request)
    evaluations = []
    for trace in mapped.value.traces:
        sequence = tuple(e.activity for e in trace.events)
        deviations = []
        for relation in model.relations:
            bad = tuple(
                i
                for i, ok in _skeleton_obligations(
                    sequence, relation.kind, relation.source, relation.target
                )
                if not ok
            )
            if bad:
                deviations.append(
                    SkeletonDeviation(
                        relation.kind,
                        relation.source,
                        relation.target,
                        tuple(i for i in bad if i is not None),
                    )
                )
        counts = Counter(sequence)
        for domain in model.activity_frequencies:
            if counts[domain.activity] not in domain.allowed_counts:
                deviations.append(
                    SkeletonDeviation(
                        "activ_freq",
                        domain.activity,
                        observed_count=counts[domain.activity],
                        allowed_counts=domain.allowed_counts,
                    )
                )
        unknown = tuple(sorted(set(sequence) - set(model.activities)))
        deviations.extend(
            SkeletonDeviation(
                "unknown_activity", x, observed_count=counts[x], allowed_counts=(0,)
            )
            for x in unknown
        )
        checked = len(model.relations) + len(model.activity_frequencies) + len(unknown)
        evaluations.append(
            SkeletonTraceEvaluation(
                trace.object_id,
                checked,
                tuple(deviations),
                1 - len(deviations) / checked if checked else None,
            )
        )
    value = SkeletonConformance(
        tuple(evaluations), sum(e.is_fit for e in evaluations), len(evaluations)
    )
    return _finish("pix.case_centric.check_log_skeleton", mapped, request, value)


_TIME_UNITS = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0, "days": 86400.0}


@dataclass(frozen=True, slots=True)
class TemporalProfileSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    relation: str = "eventually_follows"
    time_unit: str = "seconds"
    ddof: int = 0
    start_timestamp_key: str | None = None
    missing_timestamps: str = "exclude"
    negative_durations: str = "exclude"
    max_observations: int = 1_000_000

    def __post_init__(self):
        _trace_spec(self.trace_spec)
        _budget(self.max_observations, "max_observations")
        if self.relation not in ("eventually_follows", "directly_follows"):
            raise ValueError("unsupported temporal relation")
        if self.time_unit not in _TIME_UNITS:
            raise ValueError("unsupported time unit")
        if type(self.ddof) is not int or self.ddof not in (0, 1):
            raise ValueError("ddof must be 0 (population) or 1 (sample)")
        if self.start_timestamp_key is not None:
            _text(self.start_timestamp_key, "start_timestamp_key")
        if self.missing_timestamps not in ("exclude", "reject"):
            raise ValueError("missing_timestamps must be exclude or reject")
        if self.negative_durations not in ("exclude", "reject", "include"):
            raise ValueError("negative_durations must be exclude, reject or include")


@dataclass(frozen=True, slots=True)
class TemporalProfileEntry:
    source: str
    target: str
    count: int
    mean: float
    standard_deviation: float | None

    def __post_init__(self):
        _text(self.source, "source")
        _text(self.target, "target")
        if type(self.count) is not int or self.count <= 0:
            raise ValueError("profile count must be positive")
        if type(self.mean) not in (int, float) or not isfinite(self.mean):
            raise ValueError("mean must be finite")
        if self.standard_deviation is not None and (
            type(self.standard_deviation) not in (int, float)
            or not isfinite(self.standard_deviation)
            or self.standard_deviation < 0
        ):
            raise ValueError("standard deviation must be finite nonnegative or None")
        object.__setattr__(self, "mean", float(self.mean))
        if self.standard_deviation is not None:
            object.__setattr__(
                self, "standard_deviation", float(self.standard_deviation)
            )


@dataclass(frozen=True, slots=True)
class TemporalProfile:
    entries: tuple[TemporalProfileEntry, ...]
    spec: TemporalProfileSpec
    case_count: int
    observed_pairs: int
    excluded_missing: int = 0
    excluded_negative: int = 0
    profile: str = "pix.occurrence-temporal-profile.v1"

    def __post_init__(self):
        for name in (
            "case_count",
            "observed_pairs",
            "excluded_missing",
            "excluded_negative",
        ):
            _nonnegative(getattr(self, name), name)
        if not isinstance(self.spec, TemporalProfileSpec):
            raise TypeError("spec must be TemporalProfileSpec")
        if not isinstance(self.entries, tuple) or any(
            not isinstance(x, TemporalProfileEntry) for x in self.entries
        ):
            raise TypeError("entries must be tuple[TemporalProfileEntry]")
        if len({(x.source, x.target) for x in self.entries}) != len(self.entries):
            raise ValueError("duplicate temporal profile pairs")
        if self.profile != "pix.occurrence-temporal-profile.v1":
            raise ValueError("unsupported temporal profile")
        if (
            sum(x.count for x in self.entries)
            + self.excluded_missing
            + self.excluded_negative
            != self.observed_pairs
        ):
            raise ValueError(
                "temporal counts do not partition the observed-pair population"
            )
        if self.observed_pairs and not self.case_count:
            raise ValueError("observed pairs require a nonempty case population")
        for entry in self.entries:
            if (entry.count <= self.spec.ddof) != (entry.standard_deviation is None):
                raise ValueError(
                    "standard deviation availability disagrees with sample size and ddof"
                )
            if (
                entry.count == 1
                and self.spec.ddof == 0
                and entry.standard_deviation != 0
            ):
                raise ValueError("singleton population standard deviation must be zero")


@dataclass(frozen=True, slots=True)
class TemporalConformanceSpec:
    zeta: float = 6.0
    unknown_pairs: str = "report"

    def __post_init__(self):
        if (
            type(self.zeta) not in (int, float)
            or not isfinite(self.zeta)
            or self.zeta < 0
        ):
            raise ValueError("zeta must be finite nonnegative")
        object.__setattr__(self, "zeta", float(self.zeta))
        if self.unknown_pairs not in ("report", "ignore"):
            raise ValueError("unknown_pairs must be report or ignore")


@dataclass(frozen=True, slots=True)
class TemporalConformanceRequest:
    model: TemporalProfile
    options: TemporalConformanceSpec


@dataclass(frozen=True, slots=True)
class TemporalDeviation:
    case_id: str
    source_event_id: str
    target_event_id: str
    source: str
    target: str
    duration: float | None
    state: str
    z_score: float | None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class TemporalConformance:
    observations: tuple[TemporalDeviation, ...]
    satisfied_pairs: int
    violated_pairs: int
    unknown_pairs: int
    ignored_pairs: int
    case_count: int
    time_unit: str


def _temporal_observations(log, traces, spec):
    start_times = {}
    if spec.start_timestamp_key is not None:
        for trace in log.traces:
            for event in trace.events:
                attribute = log.attribute(event, spec.start_timestamp_key)
                stamp = (
                    attribute.value
                    if attribute is not None and attribute.type == "date"
                    else None
                )
                start_times[event.id] = (
                    stamp
                    if stamp is not None and stamp.utcoffset() is not None
                    else None
                )
    observations = []
    for trace in traces.traces:
        for i, source in enumerate(trace.events):
            targets = (
                trace.events[i + 1 : i + 2]
                if spec.relation == "directly_follows"
                else trace.events[i + 1 :]
            )
            for target in targets:
                start = (
                    target.time
                    if spec.start_timestamp_key is None
                    else start_times.get(target.event_id)
                )
                end = source.time
                duration, reason = None, None
                if start is None or end is None:
                    reason = "missing_timestamp"
                else:
                    duration = (
                        start.astimezone(timezone.utc) - end.astimezone(timezone.utc)
                    ).total_seconds() / _TIME_UNITS[spec.time_unit]
                    if duration < 0 and spec.negative_durations != "include":
                        duration, reason = None, "negative_duration"
                observations.append(
                    (
                        trace.object_id,
                        source.event_id,
                        target.event_id,
                        source.activity,
                        target.activity,
                        duration,
                        reason,
                    )
                )
    return tuple(observations)


def _temporal_pair_count(traces, spec):
    return sum(
        max(0, len(t.events) - 1)
        if spec.relation == "directly_follows"
        else len(t.events) * (len(t.events) - 1) // 2
        for t in traces.traces
    )


def _temporal_input_issues(observations, spec):
    missing = sum(x[-1] == "missing_timestamp" for x in observations)
    negative = sum(x[-1] == "negative_duration" for x in observations)
    rejected = bool(
        (missing and spec.missing_timestamps == "reject")
        or (negative and spec.negative_durations == "reject")
    )
    issues = tuple(
        ComputeIssue(code, message)
        for count, code, message in (
            (
                missing,
                "missing_timestamp_pairs",
                f"{missing} occurrence pairs lack usable timestamps",
            ),
            (
                negative,
                "negative_duration_pairs",
                f"{negative} occurrence pairs have negative complete-to-start durations",
            ),
        )
        if count
    )
    return missing, negative, rejected, issues


def discover_temporal_profile(
    log: CaseLog, spec: TemporalProfileSpec = TemporalProfileSpec()
) -> ComputationResult[TemporalProfile]:
    """Measure all source-ordered occurrence pairs in explicit units and ddof.

    Repeated labels create multiple observations. No timestamp sorting, absent
    timestamp imputation, business-hours transform, or latest-event pairing is
    implicit. Sample variance with a singleton is unknown, not zero.
    """
    if not isinstance(spec, TemporalProfileSpec):
        raise TypeError("spec must be TemporalProfileSpec")
    mapped = case_traces(log, spec.trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.discover_temporal_profile", mapped, spec)
    pair_count = _temporal_pair_count(mapped.value, spec)
    if pair_count > spec.max_observations:
        return _finish(
            "pix.case_centric.discover_temporal_profile",
            mapped,
            spec,
            issues=(
                ComputeIssue(
                    "temporal_pair_limit",
                    f"{pair_count} occurrence pairs exceed limit {spec.max_observations}; population was not truncated",
                ),
            ),
        )
    try:
        observations = _temporal_observations(log, mapped.value, spec)
    except ValueError as exc:
        return _finish(
            "pix.case_centric.discover_temporal_profile",
            mapped,
            spec,
            issues=(ComputeIssue("invalid_timestamp_mapping", str(exc)),),
        )
    missing, negative, rejected, issues = _temporal_input_issues(observations, spec)
    if rejected:
        return _finish(
            "pix.case_centric.discover_temporal_profile", mapped, spec, issues=issues
        )
    grouped = defaultdict(list)
    for _, _, _, source, target, duration, _ in observations:
        if duration is not None:
            grouped[source, target].append(duration)
    if not grouped:
        return _finish(
            "pix.case_centric.discover_temporal_profile",
            mapped,
            spec,
            issues=(
                *issues,
                ComputeIssue(
                    "empty_temporal_population", "No usable occurrence-pair durations"
                ),
            ),
        )
    entries = []
    for (source, target), values in sorted(grouped.items()):
        mean = fmean(values)
        deviation = (
            sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - spec.ddof))
            if len(values) > spec.ddof
            else None
        )
        entries.append(
            TemporalProfileEntry(source, target, len(values), mean, deviation)
        )
    value = TemporalProfile(
        tuple(entries),
        spec,
        len(mapped.value.traces),
        len(observations),
        missing,
        negative,
    )
    return _finish(
        "pix.case_centric.discover_temporal_profile",
        mapped,
        spec,
        value,
        issues=issues,
        partial=bool(issues),
    )


def check_temporal_profile(
    log: CaseLog,
    model: TemporalProfile,
    spec: TemporalConformanceSpec = TemporalConformanceSpec(),
) -> ComputationResult[TemporalConformance]:
    """Flag |duration-mean| > zeta·std; equality is in range.

    A zero-variance mismatch is a definite deviation with ``z_score=None``;
    infinity is never serialized. Unknown reference pairs are explicit by default.
    """
    if not isinstance(model, TemporalProfile) or not isinstance(
        spec, TemporalConformanceSpec
    ):
        raise TypeError("expected TemporalProfile and TemporalConformanceSpec")
    request = TemporalConformanceRequest(model, spec)
    mapped = case_traces(log, model.spec.trace_spec)
    if mapped.value is None:
        return _finish("pix.case_centric.check_temporal_profile", mapped, request)
    pair_count = _temporal_pair_count(mapped.value, model.spec)
    if pair_count > model.spec.max_observations:
        return _finish(
            "pix.case_centric.check_temporal_profile",
            mapped,
            request,
            issues=(
                ComputeIssue(
                    "temporal_pair_limit",
                    f"{pair_count} occurrence pairs exceed limit {model.spec.max_observations}; population was not truncated",
                ),
            ),
        )
    try:
        observations = _temporal_observations(log, mapped.value, model.spec)
    except ValueError as exc:
        return _finish(
            "pix.case_centric.check_temporal_profile",
            mapped,
            request,
            issues=(ComputeIssue("invalid_timestamp_mapping", str(exc)),),
        )
    _, _, rejected, issues = _temporal_input_issues(observations, model.spec)
    if rejected:
        return _finish(
            "pix.case_centric.check_temporal_profile", mapped, request, issues=issues
        )
    lookup = {(x.source, x.target): x for x in model.entries}
    diagnostics = []
    for case_id, source_id, target_id, source, target, duration, reason in observations:
        state, score = "unknown", None
        entry = lookup.get((source, target))
        if reason is not None:
            pass
        elif entry is None:
            reason = "unprofiled_pair"
            state = "ignored" if spec.unknown_pairs == "ignore" else "unknown"
        elif entry.standard_deviation is None:
            reason = "unknown_variance"
        elif entry.standard_deviation == 0:
            state = "satisfied" if duration == entry.mean else "violated"
            score = 0.0 if state == "satisfied" else None
            reason = None if state == "satisfied" else "zero_variance_mismatch"
        else:
            score = abs(duration - entry.mean) / entry.standard_deviation
            state = "violated" if score > spec.zeta else "satisfied"
            if not isfinite(score):
                score, reason = None, "standardized_distance_overflow"
        diagnostics.append(
            TemporalDeviation(
                case_id,
                source_id,
                target_id,
                source,
                target,
                duration,
                state,
                score,
                reason,
            )
        )
    counts = Counter(x.state for x in diagnostics)
    if counts["unknown"]:
        issues += (
            ComputeIssue(
                "unknown_temporal_pairs",
                f"{counts['unknown']} pairs cannot be judged from the profile",
            ),
        )
    value = TemporalConformance(
        tuple(diagnostics),
        counts["satisfied"],
        counts["violated"],
        counts["unknown"],
        counts["ignored"],
        len(mapped.value.traces),
        model.spec.time_unit,
    )
    return _finish(
        "pix.case_centric.check_temporal_profile",
        mapped,
        request,
        value,
        issues=issues,
        partial=bool(counts["unknown"]),
    )


@dataclass(frozen=True, slots=True)
class FootprintConformanceSpec:
    check_boundaries: bool = True
    check_minimum_length: bool = True
    trace_spec: CaseTraceSpec = CaseTraceSpec()

    def __post_init__(self):
        _trace_spec(self.trace_spec)
        if (
            type(self.check_boundaries) is not bool
            or type(self.check_minimum_length) is not bool
        ):
            raise TypeError("footprint check flags must be bool")


@dataclass(frozen=True, slots=True)
class FootprintReference:
    activities: tuple[str, ...]
    causal: tuple[tuple[str, str], ...]
    parallel: tuple[tuple[str, str], ...]
    loop_activities: tuple[str, ...]
    start_activities: tuple[str, ...]
    end_activities: tuple[str, ...]
    minimum_trace_length: int | None
    accepts_empty_trace: bool | None = None
    accepted_language_exists: bool | None = None
    required_activities: tuple[str, ...] | None = None
    source_profile: str = "explicit"
    reference_source_digest: str | None = None
    reference_computation_id: str | None = None

    def __post_init__(self):
        for field in (
            "activities",
            "loop_activities",
            "start_activities",
            "end_activities",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in value)
                or len(set(value)) != len(value)
            ):
                raise ValueError(f"{field} must be a tuple of unique nonblank strings")
        alphabet = set(self.activities)
        for field in ("causal", "parallel"):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(pair, tuple)
                or len(pair) != 2
                or any(x not in alphabet for x in pair)
                for pair in value
            ):
                raise ValueError(f"invalid {field} relations")
            if len(set(value)) != len(value):
                raise ValueError(f"duplicate {field} relations")
        if any(
            x not in alphabet
            for field in ("loop_activities", "start_activities", "end_activities")
            for x in getattr(self, field)
        ):
            raise ValueError("footprint boundary or loop activity is unknown")
        if set(self.causal) & set(self.parallel):
            raise ValueError("causal and parallel footprint relations overlap")
        if any(a == b or (b, a) in self.causal for a, b in self.causal):
            raise ValueError("causal relations must be irreflexive and asymmetric")
        if any(a == b or (b, a) not in self.parallel for a, b in self.parallel):
            raise ValueError(
                "parallel relations must contain both distinct-label directions"
            )
        if self.minimum_trace_length is not None and (
            type(self.minimum_trace_length) is not int or self.minimum_trace_length < 0
        ):
            raise ValueError("minimum_trace_length must be nonnegative int or None")
        for name in ("accepts_empty_trace", "accepted_language_exists"):
            if (
                getattr(self, name) is not None
                and type(getattr(self, name)) is not bool
            ):
                raise TypeError(f"{name} must be bool or None")
        if self.accepts_empty_trace is True and self.accepted_language_exists is False:
            raise ValueError(
                "epsilon acceptance contradicts an empty accepting language"
            )
        if self.accepts_empty_trace is True and self.minimum_trace_length not in (
            None,
            0,
        ):
            raise ValueError("epsilon acceptance contradicts positive minimum length")
        if self.accepts_empty_trace is False and self.minimum_trace_length == 0:
            raise ValueError("zero minimum length contradicts epsilon rejection")
        if self.required_activities is not None:
            if (
                not isinstance(self.required_activities, tuple)
                or any(x not in alphabet for x in self.required_activities)
                or len(set(self.required_activities)) != len(self.required_activities)
            ):
                raise ValueError(
                    "required activities must be a unique tuple in the alphabet"
                )
        _text(self.source_profile, "source_profile")
        for name in ("reference_source_digest", "reference_computation_id"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class FootprintConformanceRequest:
    model: FootprintReference
    options: FootprintConformanceSpec


@dataclass(frozen=True, slots=True)
class FootprintViolation:
    kind: str
    source: str | None = None
    target: str | None = None
    case_id: str | None = None


@dataclass(frozen=True, slots=True)
class FootprintConformance:
    violations: tuple[FootprintViolation, ...]
    observed_relations: tuple[tuple[str, str], ...]
    allowed_relations: tuple[tuple[str, str], ...]
    matched_relation_count: int
    relation_fitness: float | None
    relation_precision: float | None
    case_count: int
    profile: str = "pix.footprint-relation-inclusion.v1"

    @property
    def is_fit(self):
        return not self.violations


def footprint_reference(model) -> FootprintReference:
    """Adapt complete log/model footprints without inventing unknown negatives.

    Partial model exploration is rejected: missing edges do not establish
    forbidden behavior. Proven minimum length, epsilon and accepting-language
    facts, mandatory activities and reachable/accepting profile are retained.
    Passing a discovery result also retains its provenance identity.
    """
    from pix.case_centric.discovery import FootprintModel
    from pix.case_centric.model_discovery import ModelFootprints

    parent = model if isinstance(model, ComputationResult) else None
    if parent is not None:
        if parent.status is not ComputeStatus.COMPUTED or parent.value is None:
            raise ValueError("a complete computed footprint result is required")
        model = parent.value
    if isinstance(model, FootprintReference):
        if parent is not None:
            raise TypeError("expected a footprint discovery result")
        return model
    source_digest = parent.source_digest if parent is not None else None
    computation_id = parent.computation_id if parent is not None else None
    if isinstance(model, FootprintModel):
        if (
            parent is not None
            and parent.operator_id != "pix.case_centric.discover_footprints"
        ):
            raise ValueError("log footprint parent operator is not a native discovery")
        return FootprintReference(
            model.activities,
            model.causal,
            model.parallel,
            model.loop_activities,
            model.start_activities,
            model.end_activities,
            model.minimum_trace_length,
            model.empty_trace_count > 0,
            model.minimum_trace_length is not None,
            None,
            "observed-case-footprints",
            source_digest,
            computation_id,
        )
    if isinstance(model, ModelFootprints):
        if (
            parent is not None
            and parent.operator_id != "pix.case_centric.discover_model_footprints"
        ):
            raise ValueError(
                "model footprint parent operator is not a native discovery"
            )
        if not model.complete or model.sequence is None:
            raise ValueError(
                "partial model footprints cannot define forbidden relations"
            )
        return FootprintReference(
            model.activities,
            model.sequence,
            model.parallel,
            model.self_succession,
            model.start_activities,
            model.end_activities,
            model.minimum_trace_length if model.minimum_length_proven else None,
            model.accepts_empty_trace,
            model.accepted_language_exists,
            model.always_activities,
            "model-" + model.behavior,
            source_digest or model.model_digest,
            computation_id,
        )
    raise TypeError("model must be native log/model footprints or FootprintReference")


def check_footprints(
    log: CaseLog, model, spec: FootprintConformanceSpec = FootprintConformanceSpec()
) -> ComputationResult[FootprintConformance]:
    """Check directed footprint relation inclusion, boundaries, and minimum length.

    The model may be complete log/model footprints, their computed result,
    or an explicit FootprintReference. Known epsilon rejection and an empty
    accepting language are checked instead of being treated as absent edges.
    Model parallelism allows either observed direction; observed parallelism
    requires both model directions. Fitness divides matched relation types by
    observed types, precision by allowed types. Both are None on their empty
    denominator, are unweighted, and are not escaping-edge/token precision.
    """
    if not isinstance(spec, FootprintConformanceSpec):
        raise TypeError("spec must be FootprintConformanceSpec")
    model = footprint_reference(model)
    model_parents = (
        (model.reference_computation_id,) if model.reference_computation_id else ()
    )
    request = FootprintConformanceRequest(model, spec)
    mapped = case_traces(log, spec.trace_spec)
    if mapped.value is None:
        return _finish(
            "pix.case_centric.check_footprints",
            mapped,
            request,
            extra_parent_ids=model_parents,
        )
    observed, violations = set(), set()
    allowed = (
        set(model.causal)
        | set(model.parallel)
        | {(x, x) for x in model.loop_activities}
    )
    for trace in mapped.value.traces:
        sequence = tuple(e.activity for e in trace.events)
        if model.accepted_language_exists is False:
            violations.add(
                FootprintViolation("no_accepting_behavior", case_id=trace.object_id)
            )
        if not sequence and model.accepts_empty_trace is False:
            violations.add(
                FootprintViolation("empty_trace_not_accepted", case_id=trace.object_id)
            )
        if model.required_activities is not None:
            violations.update(
                FootprintViolation("required_activity", x, case_id=trace.object_id)
                for x in set(model.required_activities) - set(sequence)
            )
        observed.update(zip(sequence, sequence[1:]))
        violations.update(
            FootprintViolation("unknown_activity", x)
            for x in set(sequence) - set(model.activities)
        )
        if spec.check_boundaries and sequence:
            if sequence[0] not in model.start_activities:
                violations.add(
                    FootprintViolation(
                        "start_activity", sequence[0], case_id=trace.object_id
                    )
                )
            if sequence[-1] not in model.end_activities:
                violations.add(
                    FootprintViolation(
                        "end_activity", sequence[-1], case_id=trace.object_id
                    )
                )
        if (
            spec.check_minimum_length
            and model.minimum_trace_length is not None
            and len(sequence) < model.minimum_trace_length
        ):
            violations.add(
                FootprintViolation("minimum_trace_length", case_id=trace.object_id)
            )
    violations.update(
        FootprintViolation("relation", a, b) for a, b in observed - allowed
    )
    matched = len(observed & allowed)
    value = FootprintConformance(
        tuple(
            sorted(
                violations,
                key=lambda x: (x.kind, x.source or "", x.target or "", x.case_id or ""),
            )
        ),
        tuple(sorted(observed)),
        tuple(sorted(allowed)),
        matched,
        matched / len(observed) if observed else None,
        matched / len(allowed) if allowed else None,
        len(mapped.value.traces),
    )
    return _finish(
        "pix.case_centric.check_footprints",
        mapped,
        request,
        value,
        extra_parent_ids=model_parents,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_declare": (
        "case-declare-model",
        DeclareDiscoverySpec,
        DeclareModel,
    ),
    "pix.case_centric.check_declare": (
        "case-declare-conformance",
        DeclareConformanceRequest,
        DeclareConformance,
    ),
    "pix.case_centric.discover_log_skeleton": (
        "case-log-skeleton",
        LogSkeletonSpec,
        LogSkeleton,
    ),
    "pix.case_centric.check_log_skeleton": (
        "case-log-skeleton-conformance",
        SkeletonConformanceRequest,
        SkeletonConformance,
    ),
    "pix.case_centric.discover_temporal_profile": (
        "case-temporal-profile",
        TemporalProfileSpec,
        TemporalProfile,
    ),
    "pix.case_centric.check_temporal_profile": (
        "case-temporal-conformance",
        TemporalConformanceRequest,
        TemporalConformance,
    ),
    "pix.case_centric.check_footprints": (
        "case-footprint-conformance",
        FootprintConformanceRequest,
        FootprintConformance,
    ),
}

__all__ = (
    "DECLARE_TEMPLATES",
    "DeclareConstraint",
    "DeclareModel",
    "DeclareDiscoverySpec",
    "DeclareConformanceSpec",
    "discover_declare",
    "check_declare",
    "LogSkeletonSpec",
    "LogSkeleton",
    "SkeletonRelation",
    "ActivityFrequency",
    "discover_log_skeleton",
    "check_log_skeleton",
    "TemporalProfileSpec",
    "TemporalProfileEntry",
    "TemporalProfile",
    "TemporalConformanceSpec",
    "discover_temporal_profile",
    "check_temporal_profile",
    "FootprintReference",
    "FootprintConformanceSpec",
    "footprint_reference",
    "check_footprints",
)
