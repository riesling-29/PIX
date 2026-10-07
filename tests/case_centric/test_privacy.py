"""Independent sensitivity/likelihood checks and hand-calculated releases.

Finite enumeration is a regression oracle, not a universal privacy proof. The
module's privacy argument depends on public support, sensitivity, composition
and postprocessing. Tests replace private sampler helpers only for arithmetic
verification; those deterministic runs are never deployment privacy evidence.
"""

import json
from dataclasses import FrozenInstanceError, asdict, replace
from decimal import ROUND_DOWN, Decimal, Inexact, Underflow, localcontext
from fractions import Fraction
from itertools import product
from math import exp, isclose

import pytest

from pix.case_centric import privacy
from pix.case_centric.privacy import (
    TraceVariantPrivacySpec,
    anonymize_trace_variants,
    privacy_release,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"private-case-{index}",
                tuple(
                    CaseEvent(
                        f"private-event-{index}-{position}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute("private-customer", "string", "Alice"),
                        ),
                    )
                    for position, activity in enumerate(word)
                ),
            )
            for index, word in enumerate(words)
        )
    )


def spec(**changes):
    return TraceVariantPrivacySpec(
        **dict(dict(activities=("A", "B"), max_trace_length=2, epsilon=3.0), **changes)
    )


def zero_noise(monkeypatch):
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: 0)
    monkeypatch.setattr(privacy, "_sample_laplace", lambda scale: 0.0)


def variants(result):
    return {row.activities: row.count for row in result.value.variants}


def test_hand_counts_clipping_terminal_and_unknown_mapping(monkeypatch):
    zero_noise(monkeypatch)
    actual = anonymize_trace_variants(
        log((), ("A",), ("A", "B"), ("A", "B", "A"), ("unknown",)), spec()
    )
    assert actual.status is ComputeStatus.COMPUTED
    assert variants(actual) == {(): 1, ("A",): 1, ("A", "B"): 2, ("__OTHER__",): 1}
    assert actual.value.max_trace_length == 2
    assert actual.value.depths[-1].depth == 3
    assert sum(row.epsilon_allocated for row in actual.value.depths) == 3
    assert actual.value.privacy_model.startswith("case_level_discrete_dp_")


def test_empty_public_log_still_noises_unobserved_candidates(monkeypatch):
    calls = []

    def positive_noise(q):
        calls.append(q)
        return 1

    monkeypatch.setattr(privacy, "_sample_discrete_laplace", positive_noise)
    request = spec(activities=("A",), other_activity="A", max_trace_length=1)
    actual = anonymize_trace_variants(log(), request)
    assert variants(actual) == {(): 1, ("A",): 1}
    assert len(calls) == 3  # root terminal, A prefix, A terminal
    assert actual.value.public_activities == ("A",)


def test_public_zero_count_bin_can_survive_threshold(monkeypatch):
    draws = iter((0, 0, 4, 0, 2))
    # Depth 1: terminal empty, prefix A, prefix B, prefix OTHER.
    # Depth 2: terminal B; its noisy count is released despite original zero.
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: next(draws))
    actual = anonymize_trace_variants(log(), spec(max_trace_length=1))
    assert variants(actual) == {("B",): 2}
    with pytest.raises(StopIteration):
        next(draws)


def test_pruning_uses_noisy_count_not_original_presence(monkeypatch):
    # Two A traces, but negative noise prunes A; the true count must not revive it.
    draws = iter((0, -5, 0, 0))
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: next(draws))
    actual = anonymize_trace_variants(log(("A",), ("A",)), spec(max_trace_length=1))
    assert variants(actual) == {}
    with pytest.raises(StopIteration):
        next(draws)


@pytest.mark.parametrize("noise, expected", [(-0.75, 1), (-0.25, 2), (0.75, 3)])
def test_continuous_noise_added_before_rounding(monkeypatch, noise, expected):
    monkeypatch.setattr(privacy, "_sample_laplace", lambda scale: noise)
    # All cases clip to the empty variant, producing one terminal query.
    actual = anonymize_trace_variants(
        log(("A",), ("B",)),
        spec(
            mechanism="laplace",
            max_trace_length=0,
        ),
    )
    assert variants(actual) == {(): expected}
    assert "machine_dp_not_certified" in actual.value.privacy_model
    assert any(
        issue.code == "floating_point_privacy_not_certified" for issue in actual.issues
    )


def test_negative_count_clamp_and_zero_threshold(monkeypatch):
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: -100)
    actual = anonymize_trace_variants(
        log(("A",)), spec(threshold=0, max_trace_length=1)
    )
    assert variants(actual) == {}


def test_nonuniform_depth_budget_and_replace_sensitivity(monkeypatch):
    zero_noise(monkeypatch)
    request = spec(
        epsilon=3, epsilon_per_depth=(0.5, 1.0, 1.5), adjacency="replace_case"
    )
    actual = anonymize_trace_variants(log(("A",)), request)
    assert [row.l1_sensitivity for row in actual.value.depths] == [2, 2, 2]
    assert [row.ideal_laplace_scale for row in actual.value.depths] == [4, 2, 4 / 3]
    assert actual.value.epsilon_allocated == 3


@pytest.mark.parametrize("epsilon, length", [(1.0, 2), (0.1, 2), (0.3, 6), (0.7, 4)])
def test_binary_equal_allocation_never_overspends(epsilon, length):
    request = spec(
        epsilon=epsilon, max_trace_length=length, activities=("A",), other_activity="A"
    )
    allocations = privacy._budgets(request)
    assert sum(map(Fraction, allocations), Fraction()) <= Fraction(epsilon)
    assert len(allocations) == length + 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"epsilon": 0},
        {"epsilon": -1},
        {"epsilon": float("nan")},
        {"epsilon": float("inf")},
        {"epsilon": True},
        {"epsilon": 101},
        {"epsilon": 10**1000},
        {"max_trace_length": -1},
        {"max_trace_length": True},
        {"threshold": -1},
        {"threshold": 1.5},
        {"threshold": False},
        {"epsilon_per_depth": (1, 1)},
        {"epsilon_per_depth": (1, 1, 2)},
        {"epsilon_per_depth": (1, float("nan"), 1)},
        {"epsilon_per_depth": (0, 1, 1)},
        {"epsilon_per_depth": [1, 1, 1]},
        {"activities": ("A", "A")},
        {"activities": ("",)},
        {"activities": ["A"]},
        {"other_activity": ""},
        {"adjacency": "event"},
        {"mechanism": "auto"},
        {"max_query_nodes": 0},
        {"max_query_nodes": 1},
        {"epsilon": 0.001},
    ],
)
def test_bad_public_configuration_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        spec(**kwargs)


@pytest.mark.parametrize("profile", ["sacofa", "pripel"])
def test_separate_families_are_never_inline_laplace_aliases(profile):
    assert profile in privacy.UNSUPPORTED_PRIVACY_PROFILES
    with pytest.raises(NotImplementedError, match="own semantic/contextual"):
        spec(mechanism=profile)


def test_public_universe_bound_checked_without_reading_private_log():
    with pytest.raises(ValueError, match="public prefix universe"):
        spec(activities=("A", "B", "C"), max_trace_length=100)
    # With one public symbol, the exact count is 1 + 2*length = 5.
    assert spec(activities=("A",), other_activity="A", max_query_nodes=5)
    with pytest.raises(ValueError, match="public prefix universe"):
        spec(activities=("A",), other_activity="A", max_query_nodes=4)


@pytest.mark.parametrize("epsilon", [0.02, 0.125, 1, 10, 100])
@pytest.mark.parametrize("sensitivity", [1, 2])
def test_rational_noise_calibration_conservatively_respects_budget(
    epsilon, sensitivity
):
    parameter = privacy._geometric_parameter(epsilon, sensitivity)
    # A separate, higher precision evaluation checks the calibration inequality.
    with localcontext() as context:
        context.prec = 130
        exact_budget = Decimal.from_float(float(epsilon))
        exact_q = Decimal(parameter.numerator) / Decimal(parameter.denominator)
        ideal_q = (-exact_budget / Decimal(sensitivity)).exp()
        actual_loss = -Decimal(sensitivity) * exact_q.ln()
        assert exact_q > ideal_q
        assert actual_loss <= exact_budget
        assert ideal_q / exact_q > Decimal("0.999999999999999999999999999999")


def test_discrete_sampler_uses_exact_integer_coins(monkeypatch):
    requested = []
    draws = iter((0, 0, 2, 0, 2))

    def coin(bound):
        requested.append(bound)
        return next(draws)

    monkeypatch.setattr(privacy.secrets, "randbelow", coin)
    # q=2/3: first geometric=2 successes, second=1 => difference=1.
    assert privacy._sample_discrete_laplace(Fraction(2, 3)) == 1
    assert requested == [3] * 5


def test_calibration_is_independent_of_caller_decimal_context():
    reference = privacy._geometric_parameter(10.0, 2)
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.Emax = 2
        context.Emin = -2
        context.traps[Inexact] = True
        context.traps[Underflow] = True
        assert privacy._geometric_parameter(10.0, 2) == reference


@pytest.mark.parametrize("draw, sign", [(0, 0), ((1 << 52) - 1, 0), (0, 1)])
def test_float_sampler_grid_endpoints_are_finite(monkeypatch, draw, sign):
    draws = iter((draw, sign))
    monkeypatch.setattr(privacy.secrets, "randbits", lambda bits: next(draws))
    value = privacy._sample_laplace(2)
    assert abs(value) < 100
    assert (value < 0) == bool(sign)


def independent_depth_vector(words, level, alphabet, maximum):
    # Explicitly enumerate the PUBLIC coordinates instead of invoking PIX's
    # Counter construction or activity-prefix pruning implementation.
    parent_words = list(product(alphabet, repeat=level))
    coordinates = [(word, True) for word in parent_words]
    if level < maximum:
        coordinates += [(word, False) for word in product(alphabet, repeat=level + 1)]
    return tuple(
        sum(
            (
                word == prefix
                if terminal
                else len(word) >= level + 1 and word[: level + 1] == prefix
            )
            for word in words
        )
        for prefix, terminal in coordinates
    )


def test_exhaustive_case_adjacency_histogram_sensitivities():
    alphabet = ("A", "B")
    words = [(), *product(alphabet, repeat=1), *product(alphabet, repeat=2)]
    for level in range(3):
        for base_word, added_word in product(words, repeat=2):
            base = independent_depth_vector((base_word,), level, alphabet, 2)
            added = independent_depth_vector(
                (base_word, added_word), level, alphabet, 2
            )
            replacement = independent_depth_vector((added_word,), level, alphabet, 2)
            assert sum(abs(a - b) for a, b in zip(base, added)) <= 1
            assert sum(abs(a - b) for a, b in zip(base, replacement)) <= 2


def test_exact_finite_enumeration_of_discrete_likelihood_ratios():
    # Two-bin histogram, all neighboring 0..2 count vectors, outputs -2..3.
    # The normalizer cancels. Exact rational arithmetic avoids tolerance hiding
    # a failed bound. This is independently derived from the geometric PMF.
    q = Fraction(2, 3)
    cases = tuple(product(range(3), repeat=2))
    for before, after in product(cases, repeat=2):
        sensitivity = sum(abs(a - b) for a, b in zip(before, after))
        if sensitivity not in (1, 2):
            continue
        for output in product(range(-2, 4), repeat=2):
            exponent = sum(abs(y - x) for y, x in zip(output, before)) - sum(
                abs(y - x) for y, x in zip(output, after)
            )
            ratio = q**exponent
            assert ratio <= q ** (-sensitivity)


def test_independent_continuous_density_composition_bound():
    # For one A case versus no cases, released coordinates at depth 1/2 each
    # differ by one. Calibrated scales sum the losses to <= total epsilon.
    epsilons = (0.25, 0.75)
    for first, second in product((-5, -0.5, 0, 0.25, 1, 4), repeat=2):
        log_ratio = sum(
            epsilon * (abs(y) - abs(y - 1))
            for epsilon, y in zip(epsilons, (first, second))
        )
        assert exp(log_ratio) <= exp(sum(epsilons)) + 1e-12


def test_release_excludes_source_identity_original_ids_counts_and_attributes(
    monkeypatch,
):
    zero_noise(monkeypatch)
    actual = anonymize_trace_variants(log(("A",)), spec())
    released = privacy_release(actual)
    assert released is actual.value
    document = json.dumps(asdict(released))
    assert "private-case" not in document
    assert "private-event" not in document
    assert "Alice" not in document
    assert actual.source_digest not in document
    assert actual.computation_id not in document
    assert "source_digest" not in document
    assert "original_count" not in document
    assert "issues" not in document
    assert (
        actual.value.release_nonce
        != anonymize_trace_variants(log(("A",)), spec()).value.release_nonce
    )
    with pytest.raises(FrozenInstanceError):
        released.threshold = 9


def test_same_request_identity_does_not_mean_same_random_release(monkeypatch):
    draws = iter((0, 2))
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: next(draws))
    request = spec(max_trace_length=0)
    first = anonymize_trace_variants(log(()), request)
    second = anonymize_trace_variants(log(()), request)
    assert first.computation_id == second.computation_id  # identity of request
    assert first.value.release_nonce != second.value.release_nonce
    assert variants(first) != variants(second)  # each call spends a fresh budget


def test_real_secure_sampler_smoke_does_not_expose_seed_argument():
    actual = anonymize_trace_variants(log(("A",)), spec(max_trace_length=0))
    assert actual.status is ComputeStatus.COMPUTED
    assert all(row.count > 0 for row in actual.value.variants)
    with pytest.raises(TypeError):
        anonymize_trace_variants(log(), spec(), seed=0)


def test_partial_input_cannot_masquerade_as_full_case_privacy_release():
    parent = case_traces(log(("A",)))
    partial = replace(
        parent,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("test_partial", "Missing one classified case"),),
    )
    actual = anonymize_trace_variants(partial, spec())
    assert actual.status is ComputeStatus.UNAVAILABLE
    assert actual.value is None
    assert any(
        issue.code == "privacy_requires_complete_projection" for issue in actual.issues
    )
    with pytest.raises(ValueError, match="completed native"):
        privacy_release(actual)


def test_invalid_input_preserves_private_failure_without_release():
    invalid = CaseLog((CaseTrace("bad", (CaseEvent("missing-label"),)),))
    actual = anonymize_trace_variants(invalid, spec())
    assert actual.status is ComputeStatus.UNAVAILABLE
    assert actual.value is None
    with pytest.raises(ValueError):
        privacy_release(actual)
    with pytest.raises(TypeError):
        anonymize_trace_variants(log(), object())


def test_projection_identity_preserved(monkeypatch):
    zero_noise(monkeypatch)
    parent = case_traces(log(("A",)))
    actual = anonymize_trace_variants(parent, spec(), trace_spec=CaseTraceSpec())
    assert actual.source_digest == parent.source_digest
    assert actual.parent_computation_ids == (parent.computation_id,)
    assert privacy.RESULT_SCHEMAS[actual.operator_id] == (
        "trace-variant-release",
        TraceVariantPrivacySpec,
        privacy.TraceVariantRelease,
    )


def test_ideal_budget_and_private_full_prefix_oracle_agree():
    words = ((), ("A",), ("A", "B"), ("B", "B"))
    counters = privacy._prefix_counts(words, 2)
    assert counters[0][(), True] == 1
    assert counters[0][("A",), False] == 2
    assert counters[1][("A",), True] == 1
    assert counters[1][("A", "B"), False] == 1
    assert counters[2][("A", "B"), True] == 1
    assert sum(sum(row.values()) for row in counters) == 9
    assert isclose(sum(privacy._budgets(spec())), 3)


def test_private_result_roundtrip_has_exact_rational_parameters(monkeypatch):
    from pix import results

    zero_noise(monkeypatch)
    # Integration allowlisting belongs to the root worker. Isolate this module's
    # schema here while exercising the real serializer and identity validators.
    monkeypatch.setattr(results, "_schemas", lambda: privacy.RESULT_SCHEMAS)
    actual = anonymize_trace_variants(
        log(("A",)),
        spec(
            epsilon=3,
            epsilon_per_depth=(1, 1, 1),
        ),
    )
    encoded = results.result_json_bytes(actual)
    assert results.result_from_json(encoded) == actual
    assert type(actual.spec.epsilon) is float
    assert all(type(value) is float for value in actual.spec.epsilon_per_depth)
