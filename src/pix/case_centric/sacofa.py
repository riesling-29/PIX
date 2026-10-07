"""Native semantics-aware prefix anonymization: explicit PIX SaCoFa profiles.

SaCoFa scores prefixes against always/never/sometimes follows and precedes
relations, retains harmless candidates, selects harmful candidates using an
exponential distribution, adds count noise and prunes by semantic class. These
are separate calculations, not an alias to ordinary Laplace anonymization.

For a defensible privacy argument, rules here must be PUBLIC or derived only
from a prior certified-shaped discrete trace-variant release. We do not extract
unbudgeted rules from the raw log. Conditional on those rules, harmful-subset
selection and differential pruning are public postprocessing; fresh per-depth
histogram noise has the case adjacency/sensitivity in TraceVariantPrivacySpec.
When semantics were privately learned, their prior epsilon is composed with the
fresh frequency epsilon. The helper cannot audit whether callers' public rules
were actually chosen independently of their private data.

The harmful-subset exponential family has weight q**sum(clipped_violations),
where q conservatively approximates exp(-semantic_bias). It factorizes into
independent inclusion coins q**harm/(1+q**harm). This exact rational family is a
defined subset-score instantiation of SaCoFa, not PM4Py's double-exponent code.
The bias is NOT a second privacy epsilon: rule scores are already public/DP.

Reference: Fahrenkrog-Petersen et al., SaCoFa, arXiv:2109.08501, sections IV A-C.
The paper also permits rules from external sources. First-occurrence followers
and last-occurrence predecessors match the pinned reference's behavioral
abstraction. An always-precedes failure in a prefix can be repaired by a later
repeated anchor; this scoring convention is not LTL prefix conformance.

The ComputationResult envelope stays private. Publish only sacofa_release(result)
and account for repeated queries. The float count profile retains its explicit
machine-DP non-certification; no end-to-end security audit is claimed.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from fractions import Fraction
from math import floor, isfinite, nextafter
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.privacy import (
    PrivacyDepth,
    PrivateVariantCount,
    TraceVariantPrivacySpec,
    TraceVariantRelease,
    _alphabet,
    _budgets,
    _geometric_parameter,
    _prefix_counts,
    _sample_discrete_laplace,
    _sample_laplace,
    _sensitivity,
)
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.case_centric.anonymize_sacofa"


def _upper_budget_sum(*values: float) -> float:
    exact = sum((Fraction(value) for value in values), Fraction())
    try:
        upper = float(exact)
    except OverflowError as exc:
        raise ValueError("composed privacy budget exceeds the finite profile") from exc
    if Fraction(upper) < exact:
        upper = nextafter(upper, float("inf"))
    if not isfinite(upper):
        raise ValueError("composed privacy budget exceeds the finite profile")
    return upper


@dataclass(frozen=True, slots=True)
class BehavioralRelation:
    anchor: str
    related: str
    kind: Literal["always", "never", "sometimes"]

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value for value in (self.anchor, self.related)
        ):
            raise ValueError("behavioral relation labels must be nonempty text")
        if self.kind not in ("always", "never", "sometimes"):
            raise ValueError("relation kind must be always, never or sometimes")


@dataclass(frozen=True, slots=True)
class SACOFASemantics:
    """Public/previously privatized rules; omitted pairs mean unconstrained.

    ``permitted_starts=None`` imposes no start constraint. The empty tuple permits
    no nonempty start. An empty trace is not a start-activity violation. Origin
    records are provenance assertions, not signatures or a mechanism auditor.
    """

    activities: tuple[str, ...]
    follows: tuple[BehavioralRelation, ...] = ()
    precedes: tuple[BehavioralRelation, ...] = ()
    permitted_starts: tuple[str, ...] | None = None
    origin: Literal["public", "dp_trace_variant_release"] = "public"
    prior_epsilon: float = 0.0
    prior_adjacency: str | None = None
    prior_release_nonce: str | None = None
    prior_max_trace_length: int | None = None
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if (
            not isinstance(self.activities, tuple)
            or not all(isinstance(label, str) and label for label in self.activities)
            or len(set(self.activities)) != len(self.activities)
        ):
            raise ValueError("semantics requires distinct public activity labels")
        object.__setattr__(self, "activities", tuple(sorted(self.activities)))
        for rows in (self.follows, self.precedes):
            if not isinstance(rows, tuple) or not all(
                isinstance(row, BehavioralRelation) for row in rows
            ):
                raise TypeError(
                    "follows and precedes must be tuples of BehavioralRelation"
                )
            pairs = [(row.anchor, row.related) for row in rows]
            if len(set(pairs)) != len(pairs):
                raise ValueError(
                    "behavioral relations must not duplicate a directed pair"
                )
            if any(label not in self.activities for pair in pairs for label in pair):
                raise ValueError(
                    "behavioral relation refers outside the public alphabet"
                )
        if self.permitted_starts is not None:
            if (
                not isinstance(self.permitted_starts, tuple)
                or any(label not in self.activities for label in self.permitted_starts)
                or len(set(self.permitted_starts)) != len(self.permitted_starts)
            ):
                raise ValueError("permitted_starts must select distinct public labels")
        if type(self.prior_epsilon) not in (float, int):
            raise ValueError("prior_epsilon must be finite and nonnegative")
        try:
            valid_epsilon = isfinite(self.prior_epsilon) and self.prior_epsilon >= 0
        except OverflowError:
            valid_epsilon = False
        if not valid_epsilon:
            raise ValueError("prior_epsilon must be finite and nonnegative")
        object.__setattr__(self, "prior_epsilon", float(self.prior_epsilon))
        if self.origin == "public":
            if self.prior_epsilon != 0 or any(
                value is not None
                for value in (
                    self.prior_adjacency,
                    self.prior_release_nonce,
                    self.prior_max_trace_length,
                )
            ):
                raise ValueError(
                    "public semantics has no claimed prior private release"
                )
        elif self.origin == "dp_trace_variant_release":
            if (
                self.prior_epsilon <= 0
                or self.prior_adjacency not in ("add_remove_case", "replace_case")
                or not isinstance(self.prior_release_nonce, str)
                or not self.prior_release_nonce
            ):
                raise ValueError(
                    "private semantics requires prior epsilon, adjacency and release nonce"
                )
            if (
                type(self.prior_max_trace_length) is not int
                or self.prior_max_trace_length < 0
            ):
                raise ValueError("private semantics requires its prior clipping bound")
        else:
            raise ValueError(
                "semantics origin must be public or dp_trace_variant_release"
            )


@dataclass(frozen=True, slots=True)
class SACOFASpec:
    query: TraceVariantPrivacySpec
    semantics: SACOFASemantics
    harmless_threshold: int | None = None
    semantic_bias: float = 1.0
    max_semantic_violations: int = 1
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.query, TraceVariantPrivacySpec):
            raise TypeError("query must be TraceVariantPrivacySpec")
        if not isinstance(self.semantics, SACOFASemantics):
            raise TypeError("semantics must be SACOFASemantics")
        if self.semantics.activities != _alphabet(self.query):
            raise ValueError("query and semantic public alphabets must agree")
        if self.semantics.origin == "dp_trace_variant_release" and (
            self.semantics.prior_adjacency != self.query.adjacency
        ):
            raise ValueError(
                "prior semantics and fresh query must use the same case adjacency"
            )
        if self.harmless_threshold is not None and (
            type(self.harmless_threshold) is not int or self.harmless_threshold < 0
        ):
            raise ValueError("harmless_threshold must be a nonnegative integer or None")
        try:
            valid_bias = (
                type(self.semantic_bias) in (float, int)
                and isfinite(self.semantic_bias)
                and 0 <= self.semantic_bias <= 100
            )
        except OverflowError:
            valid_bias = False
        if not valid_bias:
            raise ValueError("semantic_bias must be finite in [0, 100]")
        object.__setattr__(self, "semantic_bias", float(self.semantic_bias))
        if (
            type(self.max_semantic_violations) is not int
            or not 1 <= self.max_semantic_violations <= 100
        ):
            raise ValueError("max_semantic_violations must be an integer in [1, 100]")
        _upper_budget_sum(self.semantics.prior_epsilon, self.query.epsilon)


@dataclass(frozen=True, slots=True)
class SACOFADepth:
    depth: int
    candidates: int
    harmless_selected: int
    harmful_selected: int
    retained_nonterminal: int


@dataclass(frozen=True, slots=True)
class SACOFARelease:
    release_nonce: str
    profile: str
    privacy_model: str
    semantics: SACOFASemantics
    adjacency: str
    public_activities: tuple[str, ...]
    other_activity: str
    epsilon_frequency: float
    epsilon_prior_semantics: float
    epsilon_composed: float
    max_trace_length: int
    harmless_threshold: int
    harmful_threshold: int
    semantic_bias: float
    max_semantic_violations: int
    subset_q_numerator: int
    subset_q_denominator: int
    depths: tuple[PrivacyDepth, ...]
    selection: tuple[SACOFADepth, ...]
    variants: tuple[PrivateVariantCount, ...]


def sacofa_semantics_from_release(release: TraceVariantRelease) -> SACOFASemantics:
    """Learn the behavioral abstraction solely from an existing DP count release.

    Positive released variants define the presence relations; their frequencies
    do not change always/never/sometimes classifications. No-anchor pairs remain
    unconstrained (sometimes). This is postprocessing and costs no fresh epsilon;
    the prior release epsilon is carried into any later composed SaCoFa result.
    The object is not cryptographically authenticated; provenance remains the
    curator's responsibility. A floating-only release cannot establish these
    semantics as machine-DP input and is rejected by this convenience helper.
    """
    if not isinstance(release, TraceVariantRelease):
        raise TypeError("release must be TraceVariantRelease")
    if release.mechanism != "discrete_laplace" or release.privacy_model != (
        "case_level_discrete_dp_conditional_on_public_configuration_and_secure_rng"
    ):
        raise ValueError("semantics requires the discrete case-level release profile")
    alphabet = release.public_activities
    words = tuple(row.activities for row in release.variants if row.count > 0)
    if any(label not in alphabet for word in words for label in word):
        raise ValueError("released variant refers outside the public alphabet")
    follows: list[BehavioralRelation] = []
    precedes: list[BehavioralRelation] = []
    for anchor in alphabet:
        containing = tuple(word for word in words if anchor in word)
        followers = tuple(set(word[word.index(anchor) + 1 :]) for word in containing)
        predecessors = tuple(
            set(word[: len(word) - 1 - word[::-1].index(anchor)]) for word in containing
        )
        for related in alphabet:
            for observations, output in (
                (followers, follows),
                (predecessors, precedes),
            ):
                if not observations:
                    kind = "sometimes"
                elif all(related in items for items in observations):
                    kind = "always"
                elif all(related not in items for items in observations):
                    kind = "never"
                else:
                    kind = "sometimes"
                output.append(BehavioralRelation(anchor, related, kind))
    starts = tuple(sorted({word[0] for word in words if word}))
    return SACOFASemantics(
        alphabet,
        tuple(follows),
        tuple(precedes),
        starts,
        "dp_trace_variant_release",
        release.epsilon_budget,
        release.adjacency,
        release.release_nonce,
        release.max_trace_length,
    )


def _violations(
    prefix: tuple[str, ...], terminal: bool, semantics: SACOFASemantics
) -> int:
    present = set(prefix)
    violations = int(
        bool(prefix)
        and semantics.permitted_starts is not None
        and prefix[0] not in semantics.permitted_starts
    )
    for rows, direction in (
        (semantics.follows, "follows"),
        (semantics.precedes, "precedes"),
    ):
        for relation in rows:
            if relation.anchor not in present or relation.kind == "sometimes":
                continue
            if direction == "follows":
                observed = (
                    relation.related in prefix[prefix.index(relation.anchor) + 1 :]
                )
            else:
                last = len(prefix) - 1 - prefix[::-1].index(relation.anchor)
                observed = relation.related in prefix[:last]
            if relation.kind == "never" and observed:
                violations += 1
            if (
                relation.kind == "always"
                and not observed
                and (direction == "precedes" or terminal)
            ):
                violations += 1
    return violations


def _select_harmful(q: Fraction, violations: int) -> bool:
    weight = q**violations
    # weight/(1+weight), simplified as numerator/(denominator+numerator).
    return secrets.randbelow(weight.denominator + weight.numerator) < weight.numerator


def _subset_parameter(bias: float) -> Fraction:
    # Below the Decimal exponential's useful relative-to-one resolution, use
    # exp(-b) <= 1/(1+b). This exact rational bound preserves tiny nonzero biases
    # without rounding q to one or failing an otherwise valid public request.
    if bias < 1e-50:
        return Fraction(1) / (1 + Fraction(bias))
    return _geometric_parameter(bias, 1)


def anonymize_sacofa(
    log: CaseInput,
    spec: SACOFASpec,
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[SACOFARelease]:
    """Execute semantic selection, noisy counts and class-aware prefix pruning.

    `query.threshold` applies to harmful candidates. `harmless_threshold=None`
    uses the same threshold; an explicit lower threshold favors harmless paths.
    Candidate selection never receives raw log-derived semantic rules implicitly.
    The source/result envelope and projection diagnostics stay inside the curator.
    """
    if not isinstance(spec, SACOFASpec):
        raise TypeError("spec must be SACOFASpec")
    parent = as_case_traces(log, trace_spec)
    issues = list(parent.issues)
    parents = (parent.computation_id,) if parent.computation_id is not None else ()

    def result(status, value=None):
        return _derived_result(
            OPERATOR_ID,
            parent.source_digest,
            spec,
            status,
            value,
            tuple(issues),
            parent_computation_ids=parents,
        )

    if parent.value is None:
        return result(parent.status)
    if parent.status is not ComputeStatus.COMPUTED:
        issues.append(
            ComputeIssue(
                "sacofa_requires_complete_projection",
                "Partial projection has no SaCoFa release",
            )
        )
        return result(ComputeStatus.UNAVAILABLE)
    query = spec.query
    alphabet = _alphabet(query)
    known = frozenset(alphabet)
    words = tuple(
        tuple(
            event.activity if event.activity in known else query.other_activity
            for event in trace.events[: query.max_trace_length]
        )
        for trace in parent.value.traces
    )
    counters = _prefix_counts(words, query.max_trace_length)
    sensitivity = _sensitivity(query)
    budgets = _budgets(query)
    noise_parameters = tuple(
        _geometric_parameter(epsilon, sensitivity)
        if query.mechanism == "discrete_laplace"
        else None
        for epsilon in budgets
    )
    noise_depths = tuple(
        PrivacyDepth(
            index + 1,
            epsilon,
            sensitivity,
            sensitivity / epsilon,
            parameter.numerator if parameter is not None else None,
            parameter.denominator if parameter is not None else None,
        )
        for index, (epsilon, parameter) in enumerate(zip(budgets, noise_parameters))
    )
    subset_q = _subset_parameter(spec.semantic_bias)
    harmless_threshold = (
        query.threshold if spec.harmless_threshold is None else spec.harmless_threshold
    )
    active: tuple[tuple[str, ...], ...] = ((),)
    variants: list[PrivateVariantCount] = []
    selections: list[SACOFADepth] = []
    for level, epsilon in enumerate(budgets):
        next_prefixes: list[tuple[str, ...]] = []
        total = harmless_selected = harmful_selected = 0
        for prefix in active:
            candidates = [(prefix, True)]
            if level < query.max_trace_length:
                candidates.extend(((*prefix, activity), False) for activity in alphabet)
            for candidate, terminal in candidates:
                total += 1
                score = min(
                    _violations(candidate, terminal, spec.semantics),
                    spec.max_semantic_violations,
                )
                if score:
                    if not _select_harmful(subset_q, score):
                        continue
                    harmful_selected += 1
                else:
                    harmless_selected += 1
                original = counters[level][candidate, terminal]
                parameter = noise_parameters[level]
                if parameter is None:
                    noisy = original + _sample_laplace(sensitivity / epsilon)
                    if not isfinite(noisy):
                        issues.append(
                            ComputeIssue(
                                "sacofa_numerical_failure",
                                "Finite noise evaluation overflowed",
                            )
                        )
                        return result(ComputeStatus.UNAVAILABLE)
                    noisy_count = max(0, floor(noisy + 0.5))
                else:
                    noisy_count = max(0, original + _sample_discrete_laplace(parameter))
                threshold = query.threshold if score else harmless_threshold
                if noisy_count < threshold:
                    continue
                if terminal:
                    if noisy_count > 0:
                        variants.append(PrivateVariantCount(candidate, noisy_count))
                else:
                    next_prefixes.append(candidate)
        active = tuple(next_prefixes)
        selections.append(
            SACOFADepth(
                level + 1, total, harmless_selected, harmful_selected, len(active)
            )
        )
    # The request budget conservatively bounds the exact binary sum of depth
    # budgets. A nearest-rounded sum could slightly understate privacy loss.
    frequency_epsilon = query.epsilon
    prior_epsilon = spec.semantics.prior_epsilon
    value = SACOFARelease(
        secrets.token_hex(16),
        "sacofa_public_rules"
        if spec.semantics.origin == "public"
        else "sacofa_dp_learned_rules",
        "case_level_discrete_dp_conditional_on_public_or_prior_dp_rules_and_secure_rng"
        if query.mechanism == "discrete_laplace"
        else "ideal_arithmetic_laplace_only_machine_dp_not_certified",
        spec.semantics,
        query.adjacency,
        alphabet,
        query.other_activity,
        frequency_epsilon,
        prior_epsilon,
        _upper_budget_sum(frequency_epsilon, prior_epsilon),
        query.max_trace_length,
        harmless_threshold,
        query.threshold,
        spec.semantic_bias,
        spec.max_semantic_violations,
        subset_q.numerator,
        subset_q.denominator,
        noise_depths,
        tuple(selections),
        tuple(sorted(variants, key=lambda row: row.activities)),
    )
    issues.append(
        ComputeIssue(
            "sacofa_envelope_is_private",
            "Only sacofa_release(result) omits private source/request metadata; repeated releases compose",
        )
    )
    if query.mechanism == "laplace":
        issues.append(
            ComputeIssue(
                "floating_point_privacy_not_certified",
                "Ideal Laplace mathematics does not certify this finite sampler",
            )
        )
    return result(ComputeStatus.COMPUTED, value)


def sacofa_release(result: ComputationResult[SACOFARelease]) -> SACOFARelease:
    """Extract the identity-free payload; this is not a public-rule/privacy audit."""
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id != OPERATOR_ID
        or result.status is not ComputeStatus.COMPUTED
        or not isinstance(result.value, SACOFARelease)
    ):
        raise ValueError("expected a completed native SaCoFa result")
    return result.value


RESULT_SCHEMAS = {OPERATOR_ID: ("sacofa-release", SACOFASpec, SACOFARelease)}

__all__ = (
    "BehavioralRelation",
    "SACOFASemantics",
    "SACOFASpec",
    "SACOFADepth",
    "SACOFARelease",
    "sacofa_semantics_from_release",
    "anonymize_sacofa",
    "sacofa_release",
)
