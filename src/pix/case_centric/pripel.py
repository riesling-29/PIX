"""Native PRIPEL contextual reconstruction, for PRIVATE diagnostic use.

The supplied trace-variant query fixes output activity sequences. Exact injective
minimum-edit-cost matching assigns at most one source case to each target case.
Occurrence-based enrichment reconstructs attributes and timestamps; bounded
numeric Laplace and categorical/boolean randomized response perturb that context.
This is a PRIPEL framework profile, not PM4Py output or theorem equivalence.

Unlike the reference implementation, attribute domains and time bounds must be
declared publicly. The context epsilon is divided over ALL released scalar
coordinates in the whole synthetic log, not separately per attribute or trace.
In ideal arithmetic, conditional on a fixed query and fixed public domains, the
product of bounded-input local channels has this total likelihood-ratio bound
even when private matching changes many traces. Mixtures over random enrichment
preserve that bound. Composition with a trace-query epsilon additionally requires
that the supplied query actually came from a valid private mechanism.

Numerical/time channels use finite floating-point inverse-CDF sampling; discrete
attribute channels use conservative rational weights and secure integer draws.
The complete pipeline has NO machine-level DP certificate, does not authenticate query
privacy or public configuration, and does not account for repeated requests.
The result ALSO contains PRIVATE matching witnesses and provenance. Neither the
envelope nor its payload is an anonymized release; no safe-export API is provided.
Paper: https://arxiv.org/abs/2006.12856, especially Sections 3.2 and 3.3.
"""

from __future__ import annotations

import secrets
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from math import isfinite, log, nextafter
from typing import ClassVar, Literal

from pix.case_centric.privacy import (
    PrivacyDepth,
    PrivateVariantCount,
    TraceVariantRelease,
    _geometric_parameter,
)
from pix.case_centric.sacofa import (
    SACOFADepth,
    SACOFARelease,
    SACOFASemantics,
    _upper_budget_sum,
)
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces

OPERATOR_ID = "pix.case_centric.reconstruct_pripel_context"


def _finite(value: object, field: str, *, positive: bool = False) -> float:
    try:
        valid = type(value) in (int, float) and isfinite(value)
    except OverflowError:
        valid = False
    if not valid or (positive and value <= 0):
        raise ValueError(
            f"{field} must be a {'positive ' if positive else ''}finite number"
        )
    return float(value)


def _positive_int(value: object, field: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be a positive integer")


@dataclass(frozen=True, slots=True)
class PripelAttributeDomain:
    """Public, fixed event-attribute domain. Unlisted attributes are dropped.

    Numerical attributes are floats clipped to [lower, upper]. Categorical
    values use an explicit tuple of strings; booleans have the fixed two-point
    domain. Missing/invalid attributes are sampled from eligible observed values
    after clipping, or from the public domain if no eligible value exists.
    Attribute presence is fixed by this specification, never copied privately.
    """

    key: str
    kind: Literal["numerical", "categorical", "boolean"]
    values: tuple[str, ...] = ()
    lower: float = 0.0
    upper: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip():
            raise ValueError("attribute key must be nonblank text")
        if self.key in ("concept:name", "time:timestamp"):
            raise ValueError("activity and timestamp have dedicated output fields")
        if self.kind not in ("numerical", "categorical", "boolean"):
            raise ValueError("unsupported contextual attribute kind")
        if not isinstance(self.values, tuple) or not all(
            isinstance(value, str) for value in self.values
        ):
            raise TypeError("values must be an immutable tuple of strings")
        if len(set(self.values)) != len(self.values):
            raise ValueError("categorical values must be unique")
        if self.kind == "categorical" and not self.values:
            raise ValueError("categorical attributes require public values")
        if self.kind != "categorical" and self.values:
            raise ValueError("values are only used for categorical attributes")
        lower = _finite(self.lower, "lower")
        upper = _finite(self.upper, "upper")
        if lower > upper or not isfinite(upper - lower):
            raise ValueError("numerical bounds must define a finite nonnegative range")
        if self.kind != "numerical" and (lower != 0.0 or upper != 1.0):
            raise ValueError("numerical bounds apply only to numerical attributes")
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)


@dataclass(frozen=True, slots=True)
class PripelSpec:
    """Explicit contextual request; query privacy is NOT authenticated here.

    ``query`` accepts a trace-variant release or the output of ``sacofa_release``.
    A constructed/copied query is accepted as numerical input, not certified as
    private. All target cases are retained, including empty/unmatched sequences.
    Source cases are clipped to query.max_trace_length before matching/enrichment.
    Resource bounds fail without a partial synthetic output.
    """

    query: TraceVariantRelease | SACOFARelease
    timestamp_lower: datetime
    timestamp_upper: datetime
    attributes: tuple[PripelAttributeDomain, ...] = ()
    epsilon_context: float = 1.0
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    release_policy: Literal["private_analysis_only"] = "private_analysis_only"
    max_target_traces: int = 200
    max_source_traces: int = 10000
    max_matrix_cells: int = 200000
    max_edit_cells: int = 2000000
    max_output_scalars: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.query, (TraceVariantRelease, SACOFARelease)):
            raise TypeError("query must be TraceVariantRelease or SACOFARelease")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if self.release_policy != "private_analysis_only":
            raise ValueError("PRIPEL numerical output is private_analysis_only")
        if not isinstance(self.attributes, tuple) or not all(
            isinstance(domain, PripelAttributeDomain) for domain in self.attributes
        ):
            raise TypeError("attributes must be a tuple of PripelAttributeDomain")
        if len({domain.key for domain in self.attributes}) != len(self.attributes):
            raise ValueError("attribute domains must have unique keys")
        for field in ("timestamp_lower", "timestamp_upper"):
            value = getattr(self, field)
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware datetime")
            object.__setattr__(self, field, value.astimezone(timezone.utc))
        if self.timestamp_lower >= self.timestamp_upper:
            raise ValueError("timestamp bounds must be increasing")
        epsilon = _finite(self.epsilon_context, "epsilon_context", positive=True)
        object.__setattr__(self, "epsilon_context", epsilon)
        for field in (
            "max_target_traces",
            "max_source_traces",
            "max_matrix_cells",
            "max_edit_cells",
            "max_output_scalars",
        ):
            _positive_int(getattr(self, field), field)
        query = self.query
        fields = ("release_nonce", "privacy_model", "adjacency", "other_activity") + (
            ("mechanism",) if isinstance(query, TraceVariantRelease) else ("profile",)
        )
        for field in fields:
            if (
                not isinstance(getattr(query, field), str)
                or not getattr(query, field).strip()
            ):
                raise ValueError(f"query {field} must be nonblank text")
        if isinstance(query, TraceVariantRelease):
            _finite(query.epsilon_budget, "query epsilon_budget", positive=True)
            allocation = _finite(query.epsilon_allocated, "query epsilon_allocated")
            if allocation < 0 or allocation > query.epsilon_budget:
                raise ValueError("query allocation must be within its claimed budget")
            if type(query.threshold) is not int or query.threshold < 0:
                raise ValueError("query threshold must be a nonnegative integer")
        else:
            if not isinstance(query.semantics, SACOFASemantics):
                raise TypeError("SaCoFa semantics must be SACOFASemantics")
            if query.public_activities != query.semantics.activities:
                raise ValueError("SaCoFa semantic and public alphabets must agree")
            _finite(query.epsilon_composed, "query epsilon_composed", positive=True)
            _finite(query.epsilon_frequency, "query epsilon_frequency", positive=True)
            prior = _finite(
                query.epsilon_prior_semantics, "query epsilon_prior_semantics"
            )
            if prior < 0 or query.epsilon_composed < _upper_budget_sum(
                query.epsilon_frequency, prior
            ):
                raise ValueError(
                    "SaCoFa composition must bound frequency and prior budgets"
                )
            bias = _finite(query.semantic_bias, "SaCoFa semantic_bias")
            if not 0 <= bias <= 100:
                raise ValueError("SaCoFa semantic_bias must be within [0, 100]")
            for field in ("harmless_threshold", "harmful_threshold"):
                if type(getattr(query, field)) is not int or getattr(query, field) < 0:
                    raise ValueError(f"SaCoFa {field} must be a nonnegative integer")
            for field in (
                "max_semantic_violations",
                "subset_q_numerator",
                "subset_q_denominator",
            ):
                _positive_int(getattr(query, field), f"SaCoFa {field}")
            if query.subset_q_numerator > query.subset_q_denominator:
                raise ValueError("SaCoFa subset parameter must be at most one")
            if not isinstance(query.selection, tuple) or not all(
                isinstance(row, SACOFADepth) for row in query.selection
            ):
                raise TypeError("SaCoFa selection must be a tuple of SACOFADepth")
            for row in query.selection:
                _positive_int(row.depth, "SaCoFa selection depth")
                for field in (
                    "candidates",
                    "harmless_selected",
                    "harmful_selected",
                    "retained_nonterminal",
                ):
                    if type(getattr(row, field)) is not int or getattr(row, field) < 0:
                        raise ValueError(
                            f"SaCoFa selection {field} must be a nonnegative integer"
                        )
        _upper_budget_sum(_query_budget(query), self.epsilon_context)
        if not isinstance(query.depths, tuple) or not all(
            isinstance(depth, PrivacyDepth) for depth in query.depths
        ):
            raise TypeError("query depths must be a tuple of PrivacyDepth")
        for depth in query.depths:
            _positive_int(depth.depth, "query depth")
            _positive_int(depth.l1_sensitivity, "query depth sensitivity")
            _finite(depth.epsilon_allocated, "query depth epsilon", positive=True)
            _finite(depth.ideal_laplace_scale, "query depth scale", positive=True)
            if (depth.geometric_numerator is None) != (
                depth.geometric_denominator is None
            ):
                raise ValueError(
                    "query geometric parameter must supply numerator and denominator together"
                )
            if depth.geometric_numerator is not None:
                _positive_int(depth.geometric_numerator, "query geometric numerator")
                _positive_int(
                    depth.geometric_denominator, "query geometric denominator"
                )
                if depth.geometric_numerator >= depth.geometric_denominator:
                    raise ValueError("query geometric parameter must be below one")
        normalized_depths = tuple(
            replace(
                depth,
                epsilon_allocated=float(depth.epsilon_allocated),
                ideal_laplace_scale=float(depth.ideal_laplace_scale),
            )
            for depth in query.depths
        )
        if isinstance(query, TraceVariantRelease):
            query = replace(
                query,
                epsilon_budget=float(query.epsilon_budget),
                epsilon_allocated=float(query.epsilon_allocated),
                depths=normalized_depths,
            )
        else:
            query = replace(
                query,
                epsilon_frequency=float(query.epsilon_frequency),
                epsilon_prior_semantics=float(query.epsilon_prior_semantics),
                epsilon_composed=float(query.epsilon_composed),
                semantic_bias=float(query.semantic_bias),
                depths=normalized_depths,
            )
        object.__setattr__(self, "query", query)
        if type(query.max_trace_length) is not int or query.max_trace_length < 0:
            raise ValueError("query max_trace_length must be a nonnegative integer")
        if not isinstance(query.public_activities, tuple) or not all(
            isinstance(activity, str) and activity.strip()
            for activity in query.public_activities
        ):
            raise ValueError("query activities must be immutable nonblank strings")
        if len(set(query.public_activities)) != len(query.public_activities):
            raise ValueError("query public activities must be unique")
        if query.other_activity not in query.public_activities:
            raise ValueError("query other_activity must belong to its public alphabet")
        if not isinstance(query.variants, tuple):
            raise TypeError("query variants must be a tuple")
        words = set()
        for row in query.variants:
            if not isinstance(row, PrivateVariantCount):
                raise TypeError("query variants must contain PrivateVariantCount")
            if not isinstance(row.activities, tuple) or not all(
                isinstance(activity, str) and activity in query.public_activities
                for activity in row.activities
            ):
                raise ValueError(
                    "query variant activity is outside its public alphabet"
                )
            if len(row.activities) > query.max_trace_length:
                raise ValueError("query variant exceeds max_trace_length")
            if type(row.count) is not int or row.count < 0:
                raise ValueError("query variant counts must be nonnegative integers")
            if row.activities in words:
                raise ValueError("query variants must be unique")
            words.add(row.activities)
        if sum(row.count for row in query.variants) > self.max_target_traces:
            raise ValueError("query exceeds max_target_traces")
        coordinates = _coordinate_count(self)
        if coordinates > self.max_output_scalars:
            raise ValueError("query and public schema exceed max_output_scalars")
        coordinate_epsilon = _coordinate_epsilon(self)
        if coordinates and coordinate_epsilon <= 0:
            raise ValueError(
                "epsilon is too small for contextual coordinate allocation"
            )
        ranges = [(self.timestamp_upper - self.timestamp_lower).total_seconds()]
        ranges.extend(
            domain.upper - domain.lower
            for domain in self.attributes
            if domain.kind == "numerical"
        )
        if coordinates and any(
            not isfinite(width / coordinate_epsilon) for width in ranges
        ):
            raise ValueError("context noise scale exceeds the finite numerical profile")


@dataclass(frozen=True, slots=True)
class PripelMatch:
    target_index: int
    source_case_id: str | None
    edit_distance: int | None


@dataclass(frozen=True, slots=True)
class PripelContextResult:
    """Private evidence payload, NOT a publishable anonymized event log."""

    run_nonce: str
    synthetic_log: CaseLog
    matches: tuple[PripelMatch, ...]
    coordinate_count: int
    epsilon_per_coordinate: float
    epsilon_context_allocated: float
    epsilon_control_flow_bound: float
    epsilon_composed_ideal_bound: float
    privacy_model: str = "finite_numerical_context_only_machine_dp_not_certified"
    release_policy: str = "private_analysis_only"


def _coordinate_count(spec: PripelSpec) -> int:
    return sum(len(row.activities) * row.count for row in spec.query.variants) * (
        len(spec.attributes) + 1
    )


def _query_budget(query: TraceVariantRelease | SACOFARelease) -> float:
    # Use the conservative request/prior-composition budget, not a rounded
    # nearest-float sum of actual per-depth allocations.
    return float(
        query.epsilon_budget
        if isinstance(query, TraceVariantRelease)
        else query.epsilon_composed
    )


def _allocation_bound(share: float, count: int) -> float:
    exact = Fraction(share) * count
    rounded = float(exact)
    return nextafter(rounded, float("inf")) if Fraction(rounded) < exact else rounded


def _coordinate_epsilon(spec: PripelSpec) -> float:
    count = _coordinate_count(spec)
    if not count:
        return 0.0
    share = spec.epsilon_context / count
    if Fraction(share) * count > Fraction(spec.epsilon_context):
        share = nextafter(share, 0.0)
    return share


def _edit_distance(left: tuple[str, ...], right: tuple[str, ...]) -> int:
    """Unit insertion, deletion and substitution, over activity tokens."""
    previous = list(range(len(right) + 1))
    for i, activity in enumerate(left, 1):
        current = [i]
        for j, other in enumerate(right, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (activity != other),
                )
            )
        previous = current
    return previous[-1]


def _assignment(cost: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, int], ...]:
    """Rectangular Hungarian assignment; exact integer potentials, stable ties.

    Returns min(rows, columns) injective pairs minimizing their total cost.
    When targets outnumber sources, target selection is part of the optimization.
    """
    if not cost or not cost[0]:
        return ()
    transposed = len(cost) > len(cost[0])
    matrix = tuple(zip(*cost)) if transposed else cost
    n, m = len(matrix), len(matrix[0])
    u, v, p, way = [0] * (n + 1), [0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], column = i, 0
        minimum: list[int | None] = [None] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[column] = True
            row, delta, next_column = p[column], None, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                reduced = matrix[row - 1][j - 1] - u[row] - v[j]
                if minimum[j] is None or reduced < minimum[j]:
                    minimum[j], way[j] = reduced, column
                if delta is None or minimum[j] < delta:
                    delta, next_column = minimum[j], j
            assert delta is not None
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                elif minimum[j] is not None:
                    minimum[j] -= delta
            column = next_column
            if p[column] == 0:
                break
        while column:
            previous_column = way[column]
            p[column] = p[previous_column]
            column = previous_column
    pairs = ((p[j] - 1, j - 1) for j in range(1, m + 1) if p[j])
    return tuple(sorted((j, i) if transposed else (i, j) for i, j in pairs))


def _uniform_open() -> float:
    # Secure, unseeded finite-grid draws. This is not an exact real sampler.
    return (secrets.randbelow((1 << 53) - 1) + 1) / (1 << 53)


def _laplace(scale: float) -> float:
    value = _uniform_open() - 0.5
    return (-1.0 if value < 0 else 1.0) * -scale * log(1 - 2 * abs(value))


def _noisy_number(value: float, lower: float, upper: float, epsilon: float) -> float:
    if lower == upper:
        return lower
    noisy = value + _laplace((upper - lower) / epsilon)
    # Overflow to +/-inf clips to a public endpoint. NaN is never valid output.
    if noisy != noisy:
        raise ArithmeticError("context perturbation produced NaN")
    return max(lower, min(upper, noisy))


def _response_weights(size: int, epsilon: float) -> tuple[int, int]:
    """Integer weights: likelihood ratio denominator/numerator <= exp(epsilon).

    Tiny epsilon uses exactly uniform response (zero privacy cost). Huge epsilon
    is conservatively capped at 100 for rational calibration. The shared helper
    rounds its geometric parameter upward independently of caller Decimal state.
    """
    parameter = (
        Fraction(1) if epsilon < 1e-70 else _geometric_parameter(min(epsilon, 100.0), 1)
    )
    return parameter.denominator, parameter.numerator


def _randomized_response(value, values: tuple, epsilon: float):
    if len(values) == 1:
        return values[0]
    keep_weight, other_weight = _response_weights(len(values), epsilon)
    draw = secrets.randbelow(keep_weight + (len(values) - 1) * other_weight)
    if draw < keep_weight:
        return value
    index = values.index(value)
    alternative = (draw - keep_weight) // other_weight
    return values[alternative if alternative < index else alternative + 1]


def _eligible(attribute: CaseAttribute | None, domain: PripelAttributeDomain):
    if attribute is None:
        return None
    value = attribute.value
    if domain.kind == "boolean":
        return value if type(value) is bool else None
    if domain.kind == "categorical":
        return value if type(value) is str and value in domain.values else None
    try:
        if type(value) in (float, int) and isfinite(value):
            return max(domain.lower, min(domain.upper, float(value)))
    except OverflowError:
        pass
    return None


def _fallback(domain: PripelAttributeDomain, observed: list):
    if observed:
        return observed[secrets.randbelow(len(observed))]
    if domain.kind == "numerical":
        return domain.lower + (domain.upper - domain.lower) * _uniform_open()
    values = domain.values if domain.kind == "categorical" else (False, True)
    return values[secrets.randbelow(len(values))]


def _timestamp(spec: PripelSpec, offset: float) -> datetime:
    """Public exact-microsecond clamp avoids datetime overflow after float noise.

    ``timedelta.total_seconds`` loses microseconds for long intervals. Converting
    via exact binary rational microseconds and clamping before date arithmetic
    keeps even datetime.min/max domains inside their declared endpoints.
    """
    span = spec.timestamp_upper - spec.timestamp_lower
    maximum = (span.days * 86400 + span.seconds) * 1000000 + span.microseconds
    microseconds = max(0, min(maximum, round(Fraction(offset) * 1000000)))
    return spec.timestamp_lower + timedelta(microseconds=microseconds)


def reconstruct_pripel_context(
    log: CaseLog, spec: PripelSpec
) -> ComputationResult[PripelContextResult]:
    """Match, enrich and perturb a supplied control-flow query, privately.

    This function does real contextual PRIPEL computation. It does not certify
    an anonymized release, trust a query's claimed privacy, or copy arbitrary
    source identifiers/attributes into synthetic events. Matching witnesses and
    the enclosing source identity are deliberately retained for private audits.
    The ideal scalar-channel argument excludes private diagnostics and observable
    resource/input failures; it concerns synthetic output on eligible inputs.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, PripelSpec):
        raise TypeError("spec must be PripelSpec")
    parent = case_traces(log, spec.trace_spec)
    issues = list(parent.issues)

    def finish(status, payload=None):
        return _derived_result(
            OPERATOR_ID,
            parent.source_digest,
            spec,
            status,
            payload,
            tuple(issues),
            parent_computation_ids=(parent.computation_id,)
            if parent.computation_id
            else (),
        )

    if parent.status is not ComputeStatus.COMPUTED:
        return finish(parent.status)
    targets = tuple(
        row.activities for row in spec.query.variants for _ in range(row.count)
    )
    traces = parent.value.traces
    if (
        len(traces) > spec.max_source_traces
        or len(traces) * len(targets) > spec.max_matrix_cells
    ):
        issues.append(
            ComputeIssue(
                "pripel_matching_limit",
                "Source/matching matrix resource bound exceeded",
            )
        )
        return finish(ComputeStatus.UNAVAILABLE)
    alphabet = set(spec.query.public_activities)
    source_events = tuple(
        trace.events[: spec.query.max_trace_length] for trace in traces
    )
    source_words = tuple(
        tuple(
            event.activity if event.activity in alphabet else spec.query.other_activity
            for event in events
        )
        for events in source_events
    )
    edit_work = sum(
        (len(target) + 1) * (len(word) + 1)
        for target in set(targets)
        for word in set(source_words)
    )
    if edit_work > spec.max_edit_cells:
        issues.append(
            ComputeIssue(
                "pripel_edit_limit",
                "Unique activity-pair edit-distance resource bound exceeded",
            )
        )
        return finish(ComputeStatus.UNAVAILABLE)
    cache = {
        (target, word): _edit_distance(target, word)
        for target in set(targets)
        for word in set(source_words)
    }
    cost = tuple(
        tuple(cache[target, word] for word in source_words) for target in targets
    )
    matching = dict(_assignment(cost))
    event_by_id = {event.id: event for trace in log.traces for event in trace.events}
    width = (spec.timestamp_upper - spec.timestamp_lower).total_seconds()
    values: dict[str, list] = {domain.key: [] for domain in spec.attributes}
    contexts = {}
    offsets = {}
    starts, all_gaps, pair_gaps = [], [], defaultdict(list)
    try:
        for events, word in zip(source_events, source_words):
            previous = None
            for position, event in enumerate(events):
                native = event_by_id[event.event_id]
                context = tuple(
                    _eligible(log.attribute(native, domain.key), domain)
                    for domain in spec.attributes
                )
                contexts[event.event_id] = context
                for domain, value in zip(spec.attributes, context):
                    if value is not None:
                        values[domain.key].append(value)
                offset = (
                    None
                    if event.time is None
                    else max(
                        0.0,
                        min(
                            width,
                            (
                                event.time.astimezone(timezone.utc)
                                - spec.timestamp_lower
                            ).total_seconds(),
                        ),
                    )
                )
                offsets[event.event_id] = offset
                if position == 0 and offset is not None:
                    starts.append(offset)
                if previous is not None and offset is not None and offset >= previous:
                    gap = offset - previous
                    all_gaps.append(gap)
                    pair_gaps[word[position - 1], word[position]].append(gap)
                previous = offset
    except (ValueError, OverflowError) as exc:
        issues.append(ComputeIssue("pripel_context_invalid", str(exc)))
        return finish(ComputeStatus.INVALID_INPUT)
    coordinate_epsilon = _coordinate_epsilon(spec)
    nonce, generated, witnesses = secrets.token_hex(16), [], []

    def choose(sequence, default):
        return sequence[secrets.randbelow(len(sequence))] if sequence else default

    for target_index, target in enumerate(targets):
        source_index = matching.get(target_index)
        witnesses.append(
            PripelMatch(
                target_index,
                None if source_index is None else traces[source_index].object_id,
                None if source_index is None else cost[target_index][source_index],
            )
        )
        stacks = defaultdict(deque)
        if source_index is not None:
            for event, activity in zip(
                source_events[source_index], source_words[source_index]
            ):
                stacks[activity].append(event)
        enriched, previous_offset = [], None
        for position, activity in enumerate(target):
            donor = stacks[activity].popleft() if stacks[activity] else None
            context = (
                contexts[donor.event_id] if donor else (None,) * len(spec.attributes)
            )
            context = tuple(
                value if value is not None else _fallback(domain, values[domain.key])
                for domain, value in zip(spec.attributes, context)
            )
            offset = offsets[donor.event_id] if donor else None
            if offset is None or (
                previous_offset is not None and offset < previous_offset
            ):
                if previous_offset is None:
                    offset = choose(starts, 0.0)
                else:
                    distribution = pair_gaps.get(
                        (target[position - 1], activity), all_gaps
                    )
                    offset = min(width, previous_offset + choose(distribution, 0.0))
            enriched.append((activity, context, offset))
            previous_offset = offset
        noisy_events, previous_original, previous_noisy = [], None, None
        for position, (activity, context, offset) in enumerate(enriched):
            original_value = (
                offset if previous_original is None else offset - previous_original
            )
            perturbed = _noisy_number(original_value, 0.0, width, coordinate_epsilon)
            noisy_offset = (
                perturbed
                if previous_noisy is None
                else min(width, previous_noisy + perturbed)
            )
            attributes = [
                CaseAttribute("concept:name", "string", activity),
                CaseAttribute("time:timestamp", "date", _timestamp(spec, noisy_offset)),
            ]
            for domain, value in zip(spec.attributes, context):
                if domain.kind == "numerical":
                    value = _noisy_number(
                        value, domain.lower, domain.upper, coordinate_epsilon
                    )
                    kind = "float"
                else:
                    value = _randomized_response(
                        value,
                        domain.values
                        if domain.kind == "categorical"
                        else (False, True),
                        coordinate_epsilon,
                    )
                    kind = "string" if domain.kind == "categorical" else "boolean"
                attributes.append(CaseAttribute(domain.key, kind, value))
            noisy_events.append(
                CaseEvent(
                    f"pripel-{nonce}-{target_index}-{position}", tuple(attributes)
                )
            )
            previous_original, previous_noisy = offset, noisy_offset
        generated.append(
            CaseTrace(f"pripel-{nonce}-{target_index}", tuple(noisy_events))
        )
    issues.extend(
        (
            ComputeIssue(
                "pripel_private_diagnostics_only",
                "Payload and envelope contain PRIVATE matching/provenance; no anonymized export certificate",
            ),
            ComputeIssue(
                "pripel_finite_privacy_not_certified",
                "Ideal channel-composition argument does not certify finite sampling, query privacy or public configuration",
            ),
            ComputeIssue(
                "pripel_profile_difference",
                "Public domains, whole-log coordinate composition and perturbed time gaps differ from the pinned PM4Py implementation",
            ),
        )
    )
    count = _coordinate_count(spec)
    payload = PripelContextResult(
        nonce,
        CaseLog(
            tuple(generated),
            metadata=(
                ("generation", "pripel_contextual_profile"),
                ("release_policy", "private_analysis_only"),
            ),
        ),
        tuple(witnesses),
        count,
        coordinate_epsilon,
        _allocation_bound(coordinate_epsilon, count),
        _query_budget(spec.query),
        _upper_budget_sum(_query_budget(spec.query), spec.epsilon_context),
    )
    return finish(ComputeStatus.COMPUTED, payload)


RESULT_SCHEMAS = {
    OPERATOR_ID: ("pripel-context-result", PripelSpec, PripelContextResult),
}

__all__ = (
    "PripelAttributeDomain",
    "PripelSpec",
    "PripelMatch",
    "PripelContextResult",
    "reconstruct_pripel_context",
)
