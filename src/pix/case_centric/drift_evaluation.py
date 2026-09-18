"""Multiplicity diagnostics for native Bose drift windows.

The family contains every raw window, including windows not displayed by the
upstream ``max_points`` selection. Neither source order nor a low p-value is a
change timestamp or proof of a process change. Holm's conditional FWER statement
requires valid marginal p-values. Benjamini--Hochberg additionally requires
independence or positive regression dependence (PRDS); overlapping windows do
not establish that assumption.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from typing import ClassVar, Literal

from pix.case_centric.advanced import (
    BoseDriftAnalysis,
    BoseDriftSpec,
    DriftWindow,
    RationalValue,
    RelationCountSublog,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)

OPERATOR_ID = "pix.case_centric.adjust_drift_pvalues"
_RAW_OPERATOR = "pix.case_centric.detect_bose_drift"


def _probability(value: object, name: str) -> None:
    if not isinstance(value, RationalValue):
        raise TypeError(f"{name} must be RationalValue")
    if not 0 <= value.as_fraction() <= 1:
        raise ValueError(f"{name} must lie in [0, 1]")


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


@dataclass(frozen=True, slots=True)
class DriftAdjustmentSpec:
    """Declare the testing family before interpreting adjusted p-values.

    ``family_size='upstream'`` derives the planned number of adjacent windows
    from the retained sublogs and the upstream window size. An integer declares
    a family at least that large, e.g. multiple preplanned diagnostics. Explicit
    ``None`` means the total family is unknown. With an incomplete known family,
    missing p-values are provisionally set to 1 and only conservative upper
    bounds for observed windows are returned; missing tests stay unresolved.
    """

    method: Literal["holm", "bh", "none"] = "holm"
    alpha: RationalValue = RationalValue(1, 20)
    family_size: int | Literal["upstream"] | None = "upstream"
    max_windows: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.method not in ("holm", "bh", "none"):
            raise ValueError("method must be holm, bh or none")
        _probability(self.alpha, "alpha")
        if self.family_size is not None and self.family_size != "upstream":
            if type(self.family_size) is not int or self.family_size < 1:
                raise ValueError("family_size must be upstream, a positive int or None")
        if type(self.max_windows) is not int or self.max_windows < 1:
            raise ValueError("max_windows must be a positive integer")


@dataclass(frozen=True, slots=True)
class DriftAdjustmentRequest:
    parameters: DriftAdjustmentSpec
    analysis_payload_digest: str
    upstream_status: str
    upstream_spec: BoseDriftSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class AdjustedDriftWindow:
    """Raw witness plus an exact adjustment or a separately named upper bound.

    ``rejected`` is unresolved for an incomplete family, even if a conservative
    bound is small. No missing hypothesis receives a synthetic decision.
    """

    window: DriftWindow
    adjusted_p_value: RationalValue | None
    adjusted_p_value_upper_bound: RationalValue | None
    rejected: bool | None


@dataclass(frozen=True, slots=True)
class BoseDriftAdjustment:
    windows: tuple[AdjustedDriftWindow, ...]
    method: Literal["holm", "bh", "none"]
    alpha: RationalValue
    family_size: int | None
    evaluated_window_count: int
    missing_window_count: int | None
    family_complete: bool
    adjustment_status: Literal[
        "exact", "conservative_upper_bound", "unresolved", "unadjusted"
    ]
    chronology: Literal["source_order"]
    error_control: Literal["conditional_fwer", "conditional_fdr", "none"]
    assumptions: tuple[str, ...]
    rejected_boundaries: tuple[int, ...]
    omitted_case_ids: tuple[str, ...]


def _digest(value: BoseDriftAnalysis | None) -> str:
    def integer_safe(item):
        # Exact rational denominators can exceed Python's decimal-string limit.
        if type(item) is int:
            return {"$integer_hex": hex(item)}
        if isinstance(item, (tuple, list)):
            return [integer_safe(member) for member in item]
        if isinstance(item, dict):
            return {key: integer_safe(member) for key, member in item.items()}
        return item

    encoded = json.dumps(
        integer_safe(asdict(value)) if value is not None else None,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return "pix.bose_drift.payload.v1:sha256:" + sha256(encoded).hexdigest()


def _invalid_windows(
    analysis: BoseDriftAnalysis, parameters: BoseDriftSpec
) -> str | None:
    if analysis.p_value_adjustment != "none":
        return "Upstream windows must contain raw, unadjusted p-values"
    if not isinstance(analysis.windows, tuple):
        return "Raw windows must be a tuple"
    if not isinstance(analysis.sublogs, tuple) or not all(
        isinstance(sublog, RelationCountSublog)
        and isinstance(sublog.case_ids, tuple)
        and bool(sublog.case_ids)
        and all(isinstance(case_id, str) and case_id for case_id in sublog.case_ids)
        for sublog in analysis.sublogs
    ):
        return "Sublogs must retain their source-order case-id tuples"
    seen = set()
    for window in analysis.windows:
        if not isinstance(window, DriftWindow):
            return "Raw windows must be DriftWindow records"
        boundary = window.boundary_sublog_index
        if type(boundary) is not int or not (
            parameters.window_size
            <= boundary
            <= len(analysis.sublogs) - parameters.window_size
        ):
            return "Raw window boundary is outside the planned adjacent-window family"
        if boundary in seen:
            return "Raw window boundaries must be unique"
        seen.add(boundary)
        if (
            type(window.boundary_case_index) is not int
            or window.boundary_case_index != boundary * parameters.sublog_size
            or not analysis.sublogs[boundary].case_ids
            or window.boundary_case_id != analysis.sublogs[boundary].case_ids[0]
        ):
            return "Raw window case boundary does not match its source-order sublog"
        try:
            _probability(window.p_value, "raw p-value")
        except (TypeError, ValueError) as error:
            return str(error)
        if (
            type(window.permutations_evaluated) is not int
            or window.permutations_evaluated < 1
        ):
            return "Raw p-values require a positive permutation count"
    return None


def _adjust(p_values: tuple[Fraction, ...], family_size: int, method: str):
    """Step-down Holm or step-up BH, with exact arithmetic and stable ties."""
    ranked = sorted(range(len(p_values)), key=lambda index: (p_values[index], index))
    adjusted = [Fraction(1)] * len(p_values)
    if method == "holm":
        running = Fraction(0)
        for rank, index in enumerate(ranked, 1):
            running = max(running, (family_size - rank + 1) * p_values[index])
            adjusted[index] = min(Fraction(1), running)
    else:
        running = Fraction(1)
        for rank in range(len(ranked), 0, -1):
            index = ranked[rank - 1]
            running = min(running, family_size * p_values[index] / rank)
            adjusted[index] = running
    return tuple(adjusted)


def adjust_drift_pvalues(
    analysis: ComputationResult[BoseDriftAnalysis],
    spec: DriftAdjustmentSpec = DriftAdjustmentSpec(),
) -> ComputationResult[BoseDriftAdjustment]:
    """Adjust all tested windows without using upstream selection or max_points.

    ``adjustment_status='exact'`` describes rational adjustment arithmetic; it
    does not turn an upstream Monte Carlo p-value into an exact permutation
    enumeration. The complete upstream parameter profile is retained.

    Rejection uses ``adjusted_p_value <= alpha``. A rejected null describes a
    feature-distribution diagnostic under the stated assumptions, not verified
    process drift, its cause, or a calendar timestamp. No timestamp is inferred.
    """
    if not isinstance(spec, DriftAdjustmentSpec):
        raise TypeError("spec must be DriftAdjustmentSpec")
    if not isinstance(analysis, ComputationResult):
        raise TypeError("analysis must be ComputationResult[BoseDriftAnalysis]")
    if analysis.operator_id != _RAW_OPERATOR or not isinstance(
        analysis.spec, BoseDriftSpec
    ):
        raise TypeError("analysis must be a native detect_bose_drift result")
    if analysis.value is not None and not isinstance(analysis.value, BoseDriftAnalysis):
        raise TypeError("analysis must contain BoseDriftAnalysis")
    request = DriftAdjustmentRequest(
        spec, _digest(analysis.value), analysis.status.value, analysis.spec
    )
    parents = (analysis.computation_id,) if analysis.computation_id is not None else ()

    def result(status, value=None, issues=()):
        return ComputationResult(
            OPERATOR_ID,
            "1.0.0",
            analysis.source_digest,
            request,
            status,
            value,
            issues,
            computation_identity(
                OPERATOR_ID, "1.0.0", analysis.source_digest, request, parents
            ),
            parents,
        )

    expected_parent = computation_identity(
        analysis.operator_id,
        analysis.operator_version,
        analysis.source_digest,
        analysis.spec,
        analysis.parent_computation_ids,
    )
    if analysis.computation_id != expected_parent:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_drift_provenance",
                    "Upstream computation identity does not match its request envelope",
                ),
            ),
        )
    if analysis.value is None:
        status = (
            ComputeStatus.INVALID_INPUT
            if analysis.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE
        )
        return result(status, issues=analysis.issues)
    raw = analysis.value
    invalid = _invalid_windows(raw, analysis.spec)
    if invalid:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_drift_windows", invalid),),
        )
    if len(raw.windows) > spec.max_windows:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "drift_adjustment_limit",
                    "No correction was computed under the requested window budget",
                ),
            ),
        )
    planned = max(0, len(raw.sublogs) - 2 * analysis.spec.window_size + 1)
    family_size = planned if spec.family_size == "upstream" else spec.family_size
    if family_size is not None and family_size < planned:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "drift_family_too_small",
                    "Declared family cannot omit any upstream planned window",
                ),
            ),
        )
    if not raw.windows:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=analysis.issues
            + (
                ComputeIssue(
                    "empty_drift_family", "No raw p-values are available to adjust"
                ),
            ),
        )
    count = len(raw.windows)
    missing = None if family_size is None else family_size - count
    complete = missing == 0
    issues = list(analysis.issues)
    if family_size is None:
        issues.append(
            ComputeIssue(
                "unknown_drift_family",
                "Total testing-family size is unknown; multiplicity error control is unresolved",
            )
        )
    elif missing:
        issues.append(
            ComputeIssue(
                "incomplete_drift_family",
                f"{missing} of {family_size} planned hypotheses have no raw p-value; missing values remain unresolved",
            )
        )
    values = tuple(window.p_value.as_fraction() for window in raw.windows)
    if spec.method == "none":
        status = "unadjusted"
        adjusted = values
    elif family_size is None:
        status = "unresolved"
        adjusted = (None,) * count
    else:
        status = "exact" if complete else "conservative_upper_bound"
        adjusted = _adjust(values, family_size, spec.method)
    rows = tuple(
        AdjustedDriftWindow(
            window,
            _rational(p_value)
            if p_value is not None and status != "conservative_upper_bound"
            else None,
            _rational(p_value)
            if p_value is not None and status == "conservative_upper_bound"
            else None,
            p_value <= spec.alpha.as_fraction()
            if p_value is not None and complete
            else None,
        )
        for window, p_value in zip(raw.windows, adjusted)
    )
    assumptions = (
        "Source order is caller-supplied; chronological ordering is not verified.",
        "Valid permutation p-values require the declared test's exchangeability assumptions.",
        "The testing family must be fixed independently of observed significance.",
        "Relation-count feature changes do not establish process change or causality.",
    )
    error_control = "none"
    if spec.method == "holm":
        assumptions += (
            "Holm permits arbitrary dependence among valid marginal p-values.",
        )
        if complete:
            error_control = "conditional_fwer"
    elif spec.method == "bh":
        assumptions += (
            "BH FDR control requires independence or PRDS; overlapping windows do not establish PRDS.",
        )
        if complete:
            error_control = "conditional_fdr"
    if status == "conservative_upper_bound":
        assumptions += (
            "Padding missing hypotheses with p=1 yields upper bounds for observed adjusted p-values under any completion of this known family; missing hypotheses remain unresolved.",
        )
    payload = BoseDriftAdjustment(
        rows,
        spec.method,
        spec.alpha,
        family_size,
        count,
        missing,
        complete,
        status,
        "source_order",
        error_control,
        assumptions,
        tuple(
            sorted(
                row.window.boundary_sublog_index for row in rows if row.rejected is True
            )
        ),
        raw.omitted_case_ids,
    )
    return result(
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        tuple(issues),
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "case_bose_drift_adjustment",
        DriftAdjustmentRequest,
        BoseDriftAdjustment,
    )
}

__all__ = (
    "DriftAdjustmentSpec",
    "DriftAdjustmentRequest",
    "AdjustedDriftWindow",
    "BoseDriftAdjustment",
    "adjust_drift_pvalues",
)
