"""Finite multiplicity oracles, coverage guards and provenance witnesses."""

from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from pix.case_centric.advanced import (
    BoseDriftAnalysis,
    BoseDriftSpec,
    DriftWindow,
    RationalValue,
    RelationCountSublog,
    detect_bose_drift,
)
from pix.case_centric.drift_evaluation import (
    DriftAdjustmentSpec,
    adjust_drift_pvalues,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def rational(value):
    value = Fraction(value)
    return RationalValue(value.numerator, value.denominator)


def raw_result(values, *, family=None, selected=(), max_points=0):
    """Manufactured exact p-values in a structurally valid source-order family."""
    family = len(values) if family is None else family
    spec = BoseDriftSpec(sublog_size=1, window_size=1, max_points=max_points)
    payload = BoseDriftAnalysis(
        ("A",),
        (("A", "always"), ("A", "sometimes"), ("A", "never")),
        tuple(RelationCountSublog((f"c{i}",), (0, 0, 1)) for i in range(family + 1)),
        tuple(
            DriftWindow(
                i, i, f"c{i}", RationalValue(1), rational(p), 1000, i in selected
            )
            for i, p in enumerate(values, 1)
        ),
        selected,
        (),
        "none",
    )
    operator, source = "pix.case_centric.detect_bose_drift", "test:source"
    return ComputationResult(
        operator,
        "1.0.0",
        source,
        spec,
        ComputeStatus.COMPUTED,
        payload,
        (),
        computation_identity(operator, "1.0.0", source, spec),
    )


def adjusted_values(result):
    return tuple(row.adjusted_p_value.as_fraction() for row in result.value.windows)


@pytest.mark.parametrize(
    ("method", "expected"),
    [
        ("holm", (".03", ".06", ".06", ".008")),
        ("bh", (".02", ".04", ".04", ".008")),
        ("none", (".01", ".04", ".03", ".002")),
    ],
)
def test_known_unsorted_four_hypothesis_oracle(method, expected):
    result = adjust_drift_pvalues(
        raw_result((".01", ".04", ".03", ".002")), DriftAdjustmentSpec(method=method)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert adjusted_values(result) == tuple(Fraction(value) for value in expected)
    assert result.value.family_size == 4
    assert result.value.evaluated_window_count == 4
    assert result.value.missing_window_count == 0
    assert result.value.family_complete
    assert result.value.chronology == "source_order"


@pytest.mark.parametrize(
    ("method", "expected"),
    [("holm", (".03", ".03", ".04")), ("bh", (".015", ".015", ".04"))],
)
def test_ties_receive_identical_exact_adjustments(method, expected):
    result = adjust_drift_pvalues(
        raw_result((".01", ".01", ".04")), DriftAdjustmentSpec(method=method)
    )
    assert adjusted_values(result) == tuple(Fraction(value) for value in expected)


def test_large_rational_keeps_exact_arithmetic_and_payload_identity():
    tiny = Fraction(1, 1 << 20_000)
    result = adjust_drift_pvalues(raw_result((tiny, 1)))
    assert adjusted_values(result) == (2 * tiny, Fraction(1))
    assert result.spec.analysis_payload_digest.startswith(
        "pix.bose_drift.payload.v1:sha256:"
    )


@pytest.mark.parametrize("method", ("holm", "bh"))
def test_zero_one_clipping_and_exact_threshold_boundary(method):
    result = adjust_drift_pvalues(
        raw_result((0, ".025", 1)), DriftAdjustmentSpec(method=method)
    )
    assert adjusted_values(result)[0] == 0
    assert adjusted_values(result)[-1] == 1
    assert all(Fraction(0) <= value <= 1 for value in adjusted_values(result))
    equality = adjust_drift_pvalues(
        raw_result((".05",)), DriftAdjustmentSpec(method=method)
    )
    assert equality.value.windows[0].rejected is True


def test_all_windows_used_not_only_selected_or_max_points():
    selected = raw_result((".01", ".04", ".03", ".002"), selected=(4,), max_points=1)
    unselected = raw_result((".01", ".04", ".03", ".002"), max_points=0)
    first, second = adjust_drift_pvalues(selected), adjust_drift_pvalues(unselected)
    assert adjusted_values(first) == adjusted_values(second)
    assert first.value.rejected_boundaries == (1, 4)
    assert len(first.value.windows) == 4
    assert first.value.windows[0].window.selected is False
    assert first.value.windows[0].rejected is True


@pytest.mark.parametrize(
    ("method", "expected"), [("holm", (".04", ".12")), ("bh", (".04", ".08"))]
)
def test_known_incomplete_family_returns_named_upper_bounds_only(method, expected):
    raw = raw_result((".01", ".04"), family=4)
    result = adjust_drift_pvalues(raw, DriftAdjustmentSpec(method=method))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.family_size == 4
    assert result.value.missing_window_count == 2
    assert result.value.adjustment_status == "conservative_upper_bound"
    assert result.value.error_control == "none"
    assert result.value.rejected_boundaries == ()
    assert all(
        row.adjusted_p_value is None and row.rejected is None
        for row in result.value.windows
    )
    assert tuple(
        row.adjusted_p_value_upper_bound.as_fraction() for row in result.value.windows
    ) == tuple(Fraction(value) for value in expected)
    assert {issue.code for issue in result.issues} == {"incomplete_drift_family"}


@pytest.mark.parametrize("method", ("holm", "bh"))
def test_padding_upper_bound_against_all_finite_missing_completions(method):
    partial = adjust_drift_pvalues(
        raw_result((".01", ".04"), family=4), DriftAdjustmentSpec(method=method)
    )
    upper = tuple(
        row.adjusted_p_value_upper_bound.as_fraction() for row in partial.value.windows
    )
    for missing in product(("0", ".001", ".01", ".02", ".04", "1"), repeat=2):
        complete = adjust_drift_pvalues(
            raw_result((".01", ".04") + missing), DriftAdjustmentSpec(method=method)
        )
        assert all(adjusted_values(complete)[i] <= upper[i] for i in range(2))


def test_explicit_larger_family_and_unknown_family_are_distinct():
    raw = raw_result((".01", ".04"))
    larger = adjust_drift_pvalues(raw, DriftAdjustmentSpec(family_size=4))
    unknown = adjust_drift_pvalues(raw, DriftAdjustmentSpec(family_size=None))
    assert larger.value.missing_window_count == 2
    assert unknown.status is ComputeStatus.PARTIAL
    assert unknown.value.family_size is None
    assert unknown.value.missing_window_count is None
    assert unknown.value.adjustment_status == "unresolved"
    assert unknown.value.error_control == "none"
    assert all(
        row.adjusted_p_value is None
        and row.adjusted_p_value_upper_bound is None
        and row.rejected is None
        for row in unknown.value.windows
    )


def test_none_preserves_raw_values_but_makes_no_family_error_claim():
    result = adjust_drift_pvalues(
        raw_result((".01", ".04")), DriftAdjustmentSpec(method="none", family_size=None)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.adjustment_status == "unadjusted"
    assert adjusted_values(result) == (Fraction(1, 100), Fraction(1, 25))
    assert result.value.error_control == "none"
    assert all(row.rejected is None for row in result.value.windows)


def test_family_cannot_omit_planned_unselected_windows():
    result = adjust_drift_pvalues(
        raw_result((".01", ".04"), family=4), DriftAdjustmentSpec(family_size=2)
    )
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "drift_family_too_small"


def test_own_budget_does_not_truncate_family_and_recalculate_m():
    result = adjust_drift_pvalues(
        raw_result((".01", ".04")), DriftAdjustmentSpec(max_windows=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "drift_adjustment_limit"


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"c{i}:e{j}", (CaseAttribute("concept:name", "string", label),)
                    )
                    for j, label in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def test_real_upstream_source_order_raw_oracle_and_budget_failure():
    raw = detect_bose_drift(
        log("AB", "AB", "BA", "BA"), BoseDriftSpec(sublog_size=1, window_size=2)
    )
    result = adjust_drift_pvalues(raw)
    assert adjusted_values(result) == (Fraction(1, 3),)
    assert result.value.windows[0].window.boundary_case_id == "c2"
    capped = detect_bose_drift(
        log("AB", "AB", "BA", "BA"),
        BoseDriftSpec(sublog_size=1, window_size=2, max_permutation_evaluations=5),
    )
    unavailable = adjust_drift_pvalues(capped)
    assert unavailable.status is ComputeStatus.UNAVAILABLE
    assert unavailable.value is None
    assert unavailable.issues == capped.issues
    assert unavailable.parent_computation_ids == (capped.computation_id,)


def test_monte_carlo_profile_is_retained_not_relabelled_as_exact_test():
    raw = detect_bose_drift(
        log("AB", "AB", "BA", "BA"),
        BoseDriftSpec(
            sublog_size=1,
            window_size=2,
            permutation_mode="monte_carlo",
            permutations=17,
            seed=23,
        ),
    )
    result = adjust_drift_pvalues(raw)
    assert result.spec.upstream_spec == raw.spec
    assert result.spec.upstream_spec.permutation_mode == "monte_carlo"
    assert result.value.windows[0].window.permutations_evaluated == 17
    assert result.value.adjustment_status == "exact"
    assert adjusted_values(result) == (raw.value.windows[0].p_value.as_fraction(),)


def test_upstream_invalid_and_partial_issues_are_not_erased():
    raw = detect_bose_drift(CaseLog((CaseTrace("bad", (CaseEvent("e"),)),)))
    result = adjust_drift_pvalues(raw)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues == raw.issues
    issue = ComputeIssue("caller_coverage", "Known upstream coverage issue")
    partial = replace(
        raw_result((".01", ".04")), status=ComputeStatus.PARTIAL, issues=(issue,)
    )
    evaluated = adjust_drift_pvalues(partial)
    assert evaluated.status is ComputeStatus.PARTIAL
    assert evaluated.issues == (issue,)


def test_assumptions_do_not_claim_unconditional_fdr_or_chronology():
    raw = raw_result((".01", ".04"))
    holm, bh = (
        adjust_drift_pvalues(raw),
        adjust_drift_pvalues(raw, DriftAdjustmentSpec(method="bh")),
    )
    assert holm.value.error_control == "conditional_fwer"
    assert bh.value.error_control == "conditional_fdr"
    assert any(
        "overlapping windows do not establish PRDS" in assumption
        for assumption in bh.value.assumptions
    )
    assert any(
        "chronological ordering is not verified" in assumption
        for assumption in holm.value.assumptions
    )


def test_payload_digest_prevents_same_parent_different_p_values_collision():
    raw = raw_result((".01", ".04"))
    changed = replace(
        raw,
        value=replace(
            raw.value,
            windows=(
                replace(raw.value.windows[0], p_value=RationalValue(1, 2)),
                raw.value.windows[1],
            ),
        ),
    )
    first, second = adjust_drift_pvalues(raw), adjust_drift_pvalues(changed)
    assert first.source_digest == raw.source_digest
    assert (
        first.parent_computation_ids
        == second.parent_computation_ids
        == (raw.computation_id,)
    )
    assert first.spec.analysis_payload_digest != second.spec.analysis_payload_digest
    assert first.computation_id != second.computation_id
    assert first == adjust_drift_pvalues(raw)


def test_inconsistent_upstream_request_identity_is_invalid():
    raw = replace(raw_result((".01", ".04")), computation_id="forged:request")
    result = adjust_drift_pvalues(raw)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "invalid_drift_provenance"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: replace(raw, windows=None),
        lambda raw: replace(raw, sublogs=None),
        lambda raw: replace(raw, sublogs=(None, None, None)),
        lambda raw: replace(
            raw, sublogs=(replace(raw.sublogs[0], case_ids=None),) + raw.sublogs[1:]
        ),
        lambda raw: replace(raw, windows=(raw.windows[0], raw.windows[0])),
        lambda raw: replace(
            raw, windows=(replace(raw.windows[0], p_value=RationalValue(2)),)
        ),
        lambda raw: replace(
            raw, windows=(replace(raw.windows[0], boundary_case_id="wrong"),)
        ),
        lambda raw: replace(raw, p_value_adjustment="holm"),
    ],
)
def test_malformed_raw_evidence_is_not_reinterpreted(mutation):
    raw = raw_result((".01", ".04"))
    result = adjust_drift_pvalues(replace(raw, value=mutation(raw.value)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "invalid_drift_windows"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"method": "bonferroni"},
        {"family_size": True},
        {"family_size": 0},
        {"alpha": RationalValue(2)},
        {"alpha": 0.05},
        {"max_windows": True},
    ],
)
def test_spec_rejects_ambiguous_values(kwargs):
    with pytest.raises((TypeError, ValueError)):
        DriftAdjustmentSpec(**kwargs)


def test_public_result_roundtrip_complete_partial_unavailable():
    from pix.results import result_from_json, result_json_bytes

    results = (
        adjust_drift_pvalues(raw_result((".01", ".04"))),
        adjust_drift_pvalues(raw_result((".01",), family=2)),
        adjust_drift_pvalues(
            raw_result((".01",)), DriftAdjustmentSpec(family_size=None)
        ),
        adjust_drift_pvalues(
            raw_result((".01", ".04")), DriftAdjustmentSpec(max_windows=1)
        ),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result
