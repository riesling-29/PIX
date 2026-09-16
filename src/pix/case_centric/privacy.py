"""Native, bounded control-flow anonymization with an explicit privacy model.

The input unit is ONE projected case, not one person, object, event or agent.
Public configuration fixes the activity alphabet (including an OTHER label),
maximum trace length, per-depth budgets and pruning threshold. A case contributes
to at most one bin at each depth, including a terminal bin at length + 1. Hence
each depth's histogram has L1 sensitivity 1 for add/remove-case adjacency and
2 for replace-case adjacency. Sequential depth budgets sum to at most epsilon.
Pruning uses only noisy counts; zero-count public candidates also receive noise.

``laplace`` implements that mathematical mechanism using finite floating-point
inverse-CDF sampling. It does NOT claim certified machine-level differential
privacy. ``discrete_laplace`` uses an exact rational geometric distribution:
P[Z=z]=(1-q)/(1+q)*q**abs(z). Independent geometric differences and uniform secure
integer draws avoid a floating-point noise sampler. Decimal calibration rounds q
UP so sensitivity*log(1/q) <= the allocated epsilon. The discrete guarantee is
conditional on independent uniform OS random bits and the stated public-domain,
adjacency and curator boundaries; it is not a whole-system security certificate.

The ComputationResult envelope contains PRIVATE source identities and inherited
diagnostics. Publish only ``privacy_release(result)``. That helper removes those
identifiers; it cannot certify that caller-chosen configuration was public, track
repeated query budgets, protect timing, or make seeded/test noise private.

This is a PIX profile, not PM4Py release parity. SACOFA's semantic/exponential
selection and PRIPEL's contextual matching/perturbation live in the separate
``sacofa`` and ``pripel`` modules, with their own scope and guarantee limitations.
They are never aliases of this calculation. This module releases no timestamps
or attributes.
Primary definitions: Dwork/Roth, Algorithmic Foundations of Differential Privacy;
Fahrenkrog-Petersen et al., SaCoFa (arXiv:2109.08501), PRIPEL (arXiv:2006.12856).
"""

from __future__ import annotations

import secrets
from collections import Counter
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    localcontext,
)
from fractions import Fraction
from math import floor, fsum, isfinite, log, nextafter
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.case_centric.anonymize_trace_variants"
# Unsupported inline selectors for THIS uniform-noise operator. Separate native
# algorithms exist in sacofa.py and pripel.py; use their explicit entry points.
UNSUPPORTED_PRIVACY_PROFILES = ("sacofa", "pripel")


def _finite_positive(value: object, name: str) -> None:
    try:
        valid = type(value) in (float, int) and isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a positive finite number")


@dataclass(frozen=True, slots=True)
class TraceVariantPrivacySpec:
    """Public request; the caller must not derive these parameters privately.

    Each input trace is clipped to its first ``max_trace_length`` activities;
    unknown labels map to the public ``other_activity``. Explicit budgets cover
    max_trace_length + 1 depths, including the separate terminal query. Empty
    budgets allocate conservatively equal shares. All repeated releases compose;
    epsilon is for this request only, not a dataset-wide automatic budget ledger.

    ``max_query_nodes`` rejects an oversized PUBLIC universe before reading data.
    It is not a data-dependent cutoff. The exact discrete sampler restricts each
    depth's epsilon/sensitivity to >= 0.01 for practical geometric sampling.
    """

    activities: tuple[str, ...]
    max_trace_length: int = 5
    epsilon: float = 1.0
    threshold: int = 1
    adjacency: Literal["add_remove_case", "replace_case"] = "add_remove_case"
    mechanism: Literal["laplace", "discrete_laplace"] = "discrete_laplace"
    epsilon_per_depth: tuple[float, ...] = ()
    other_activity: str = "__OTHER__"
    max_query_nodes: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.activities, tuple) or not all(
            isinstance(label, str) and label for label in self.activities
        ):
            raise ValueError("activities must be a tuple of nonempty public labels")
        if len(set(self.activities)) != len(self.activities):
            raise ValueError("public activities must be distinct")
        if not isinstance(self.other_activity, str) or not self.other_activity:
            raise ValueError("other_activity must be a nonempty public label")
        for label in (*self.activities, self.other_activity):
            label.encode("utf-8")
        if (
            type(self.max_trace_length) is not int
            or not 0 <= self.max_trace_length <= 128
        ):
            raise ValueError("max_trace_length must be an integer in [0, 128]")
        if type(self.threshold) is not int or self.threshold < 0:
            raise ValueError("threshold must be a nonnegative integer")
        if type(self.max_query_nodes) is not int or self.max_query_nodes < 1:
            raise ValueError("max_query_nodes must be a positive integer")
        _finite_positive(self.epsilon, "epsilon")
        if self.epsilon > 100:
            raise ValueError("epsilon above 100 is outside this numerical profile")
        if self.adjacency not in ("add_remove_case", "replace_case"):
            raise ValueError("adjacency must be add_remove_case or replace_case")
        if self.mechanism in UNSUPPORTED_PRIVACY_PROFILES:
            raise NotImplementedError(
                f"{self.mechanism} requires its own semantic/contextual mechanism"
            )
        if self.mechanism not in ("laplace", "discrete_laplace"):
            raise ValueError("mechanism must be laplace or discrete_laplace")
        if not isinstance(self.epsilon_per_depth, tuple):
            raise TypeError("epsilon_per_depth must be a tuple")
        levels = self.max_trace_length + 1
        if self.epsilon_per_depth and len(self.epsilon_per_depth) != levels:
            raise ValueError(
                "epsilon_per_depth must include every terminal/prefix depth"
            )
        for value in self.epsilon_per_depth:
            _finite_positive(value, "depth epsilon")
        object.__setattr__(self, "epsilon", float(self.epsilon))
        object.__setattr__(
            self,
            "epsilon_per_depth",
            tuple(float(value) for value in self.epsilon_per_depth),
        )
        budgets = _budgets(self)
        if sum((Fraction(value) for value in budgets), Fraction()) > Fraction(
            self.epsilon
        ):
            raise ValueError("depth privacy budgets exceed epsilon")
        if any(not isfinite(_sensitivity(self) / value) for value in budgets):
            raise ValueError("depth noise scale exceeds the finite numerical profile")
        if (
            self.mechanism == "discrete_laplace"
            and min(budgets) / _sensitivity(self) < 0.01
        ):
            raise ValueError(
                "discrete_laplace requires depth epsilon/sensitivity >= 0.01"
            )
        # Count the full public prefix + terminal universe, stopping early when
        # it already exceeds the cap. No private frequencies affect this check.
        alphabet_size = len(_alphabet(self))
        power, nodes = 1, 1
        for _ in range(self.max_trace_length):
            power *= alphabet_size
            nodes += 2 * power
            if nodes > self.max_query_nodes:
                raise ValueError("public prefix universe exceeds max_query_nodes")
        if nodes > self.max_query_nodes:
            raise ValueError("public prefix universe exceeds max_query_nodes")


@dataclass(frozen=True, slots=True)
class PrivacyDepth:
    depth: int
    epsilon_allocated: float
    l1_sensitivity: int
    ideal_laplace_scale: float
    geometric_numerator: int | None
    geometric_denominator: int | None


@dataclass(frozen=True, slots=True)
class PrivateVariantCount:
    activities: tuple[str, ...]
    count: int


@dataclass(frozen=True, slots=True)
class TraceVariantRelease:
    """Identity-free release; no original counts, identifiers or evidence rows.

    ``privacy_model`` states the mechanism's exact boundary. It does not mean
    an externally supplied instance of this dataclass has passed a privacy audit.
    The nonce identifies a random release, not its private source/request.
    """

    release_nonce: str
    mechanism: str
    privacy_model: str
    adjacency: str
    epsilon_budget: float
    epsilon_allocated: float
    public_activities: tuple[str, ...]
    other_activity: str
    max_trace_length: int
    threshold: int
    depths: tuple[PrivacyDepth, ...]
    variants: tuple[PrivateVariantCount, ...]


def _alphabet(spec: TraceVariantPrivacySpec) -> tuple[str, ...]:
    return tuple(sorted(set((*spec.activities, spec.other_activity))))


def _sensitivity(spec: TraceVariantPrivacySpec) -> int:
    return 1 if spec.adjacency == "add_remove_case" else 2


def _budgets(spec: TraceVariantPrivacySpec) -> tuple[float, ...]:
    if spec.epsilon_per_depth:
        return spec.epsilon_per_depth
    levels = spec.max_trace_length + 1
    share = spec.epsilon / levels
    # Binary rounding must never silently overspend the declared budget.
    if Fraction(share) * levels > Fraction(spec.epsilon):
        share = nextafter(share, 0.0)
    if share <= 0:
        raise ValueError("epsilon is too small to allocate finite depth budgets")
    return (share,) * levels


def _geometric_parameter(epsilon: float, sensitivity: int) -> Fraction:
    """A rational q strictly above exp(-epsilon/sensitivity).

    Decimal.exp is correctly rounded (half-even). Adding one unit in its last
    place gives a conservative upper bound, including conversion from an exact
    binary input float. A conservative upward error in the negative exponent
    first accounts for non-terminating Decimal division. An 80-digit context is
    ample for the documented epsilon range; equality q=1 is rejected.
    """
    # Caller Decimal precision, rounding mode, exponent bounds and traps must
    # not change calibration or turn a valid request into an arithmetic error.
    calibration_context = Context(
        prec=80,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(calibration_context):
        exact_epsilon = Decimal.from_float(float(epsilon))
        exponent = -(exact_epsilon / Decimal(sensitivity))
        # Sensitivity is 1 or 2, so division of a finite Decimal terminates;
        # nevertheless next_plus also safely covers context rounding of input.
        exponent = exponent.next_plus()
        rounded = exponent.exp()
        upper = rounded.next_plus()
        parameter = Fraction(upper)
    if not 0 < parameter < 1:
        raise ValueError("epsilon is outside the rational calibration range")
    return parameter


def _sample_discrete_laplace(parameter: Fraction) -> int:
    """Exact geometric difference, conditional on uniform independent randbelow.

    No seed, floating probability, cap on random draws or deterministic fallback
    is accepted. A cap/fallback would change the privacy mechanism's support.
    """
    numerator, denominator = parameter.numerator, parameter.denominator
    positive = 0
    while secrets.randbelow(denominator) < numerator:
        positive += 1
    negative = 0
    while secrets.randbelow(denominator) < numerator:
        negative += 1
    return positive - negative


def _sample_laplace(scale: float) -> float:
    """Finite inverse-CDF evaluation; ideal arithmetic guarantee only.

    The midpoint grid avoids log(0) and uses OS randomness. It is still finite
    and must not be advertised as an audited pure-DP floating-point mechanism.
    """
    # Using 52 random bits keeps (r + 0.5) / 2**52 strictly inside (0, 1).
    uniform = (secrets.randbits(52) + 0.5) / (1 << 52)
    sign = -1 if secrets.randbits(1) else 1
    return -sign * scale * log(uniform)


def _prefix_counts(
    words: tuple[tuple[str, ...], ...], max_length: int
) -> tuple[Counter[tuple[tuple[str, ...], bool]], ...]:
    """Private sufficient statistics. These counters are never in a release."""
    counts: tuple[Counter[tuple[tuple[str, ...], bool]], ...] = tuple(
        Counter() for _ in range(max_length + 1)
    )
    for word in words:
        for length in range(1, len(word) + 1):
            counts[length - 1][(word[:length], False)] += 1
        counts[len(word)][(word, True)] += 1
    return counts


def anonymize_trace_variants(
    log: CaseInput,
    spec: TraceVariantPrivacySpec,
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[TraceVariantRelease]:
    """Generate noisy clipped variants; retain the envelope inside the curator.

    One call consumes the configured budget even if no variants survive. Calling
    again is a fresh release, not an idempotent computation or a free retry. No
    deterministic seed or public noise-injection argument is provided. Projection
    errors have no release payload; these diagnostics are private to the curator.
    """
    if not isinstance(spec, TraceVariantPrivacySpec):
        raise TypeError("spec must be TraceVariantPrivacySpec")
    parent = as_case_traces(log, trace_spec)
    issues = list(parent.issues)
    parents = (parent.computation_id,) if parent.computation_id is not None else ()

    def result(status, payload=None):
        return _derived_result(
            OPERATOR_ID,
            parent.source_digest,
            spec,
            status,
            payload,
            tuple(issues),
            parent_computation_ids=parents,
        )

    if parent.value is None:
        return result(parent.status)
    if parent.status is not ComputeStatus.COMPUTED:
        issues.append(
            ComputeIssue(
                "privacy_requires_complete_projection",
                "Partial or failed input projection has no privacy release",
            )
        )
        return result(ComputeStatus.UNAVAILABLE)

    alphabet = _alphabet(spec)
    known = frozenset(alphabet)
    words = tuple(
        tuple(
            event.activity if event.activity in known else spec.other_activity
            for event in trace.events[: spec.max_trace_length]
        )
        for trace in parent.value.traces
    )
    counts = _prefix_counts(words, spec.max_trace_length)
    sensitivity = _sensitivity(spec)
    budgets = _budgets(spec)
    depth_parameters = tuple(
        _geometric_parameter(epsilon, sensitivity)
        if spec.mechanism == "discrete_laplace"
        else None
        for epsilon in budgets
    )
    depths = tuple(
        PrivacyDepth(
            level + 1,
            epsilon,
            sensitivity,
            sensitivity / epsilon,
            parameter.numerator if parameter is not None else None,
            parameter.denominator if parameter is not None else None,
        )
        for level, (epsilon, parameter) in enumerate(zip(budgets, depth_parameters))
    )
    active: tuple[tuple[str, ...], ...] = ((),)
    released: list[PrivateVariantCount] = []
    for level, epsilon in enumerate(budgets):
        following: list[tuple[str, ...]] = []
        for prefix in active:
            candidates = [(prefix, True)]
            if level < spec.max_trace_length:
                candidates.extend(((*prefix, label), False) for label in alphabet)
            for candidate, terminal in candidates:
                original = counts[level][candidate, terminal]
                parameter = depth_parameters[level]
                if parameter is not None:
                    noisy_count = max(0, original + _sample_discrete_laplace(parameter))
                else:
                    noisy = original + _sample_laplace(sensitivity / epsilon)
                    # Add first, then round. int(noise) + original is a different
                    # non-translation-invariant distribution around zero.
                    if not isfinite(noisy):
                        issues.append(
                            ComputeIssue(
                                "privacy_numerical_failure",
                                "Finite Laplace evaluation overflowed",
                            )
                        )
                        return result(ComputeStatus.UNAVAILABLE)
                    noisy_count = max(0, floor(noisy + 0.5))
                if noisy_count < spec.threshold:
                    continue
                if terminal:
                    if noisy_count > 0:
                        released.append(PrivateVariantCount(candidate, noisy_count))
                else:
                    following.append(candidate)
        active = tuple(following)

    model = (
        "case_level_discrete_dp_conditional_on_public_configuration_and_secure_rng"
        if spec.mechanism == "discrete_laplace"
        else "ideal_arithmetic_laplace_only_machine_dp_not_certified"
    )
    payload = TraceVariantRelease(
        secrets.token_hex(16),
        spec.mechanism,
        model,
        spec.adjacency,
        spec.epsilon,
        fsum(budgets),
        alphabet,
        spec.other_activity,
        spec.max_trace_length,
        spec.threshold,
        depths,
        tuple(sorted(released, key=lambda item: item.activities)),
    )
    issues.append(
        ComputeIssue(
            "privacy_envelope_is_private",
            "Only privacy_release(result) excludes source/request identities and diagnostics; "
            "the curator must account for repeated releases and keep configuration public",
        )
    )
    if spec.mechanism == "laplace":
        issues.append(
            ComputeIssue(
                "floating_point_privacy_not_certified",
                "The ideal Laplace theorem does not certify this finite sampler",
            )
        )
    return result(ComputeStatus.COMPUTED, payload)


def privacy_release(
    result: ComputationResult[TraceVariantRelease],
) -> TraceVariantRelease:
    """Return only the publishable-shaped payload, never the private envelope.

    This extraction is not a mechanism auditor or a permission/security boundary.
    It preserves the stated guarantee limitations, including the float profile's
    lack of a machine-level DP certificate. No private metadata is copied.
    """
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id != OPERATOR_ID
        or result.status is not ComputeStatus.COMPUTED
        or not isinstance(result.value, TraceVariantRelease)
    ):
        raise ValueError("expected a completed native trace-variant privacy result")
    return result.value


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "trace-variant-release",
        TraceVariantPrivacySpec,
        TraceVariantRelease,
    ),
}

__all__ = (
    "TraceVariantPrivacySpec",
    "PrivacyDepth",
    "PrivateVariantCount",
    "TraceVariantRelease",
    "UNSUPPORTED_PRIVACY_PROFILES",
    "anonymize_trace_variants",
    "privacy_release",
)
