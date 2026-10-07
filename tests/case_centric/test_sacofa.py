"""Semantic truth tables, exact subset probabilities and composed-budget cases."""

import json
from dataclasses import asdict, replace
from fractions import Fraction
from itertools import product

import pytest

from pix import results
from pix.case_centric import privacy, sacofa
from pix.case_centric.privacy import TraceVariantPrivacySpec, anonymize_trace_variants
from pix.case_centric.sacofa import (
    BehavioralRelation as Relation,
)
from pix.case_centric.sacofa import (
    SACOFASemantics,
    SACOFASpec,
    anonymize_sacofa,
    sacofa_release,
    sacofa_semantics_from_release,
)
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"secret-case-{index}",
                tuple(
                    CaseEvent(
                        f"secret-event-{index}-{position}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute("customer", "string", "Alice"),
                        ),
                    )
                    for position, activity in enumerate(word)
                ),
            )
            for index, word in enumerate(words)
        )
    )


def query(**changes):
    return TraceVariantPrivacySpec(
        **dict(
            dict(
                activities=("A", "B"),
                max_trace_length=2,
                epsilon=3.0,
            ),
            **changes,
        )
    )


def semantics(**changes):
    return SACOFASemantics(**dict(dict(activities=("A", "B", "__OTHER__")), **changes))


def zero_noise(monkeypatch):
    monkeypatch.setattr(sacofa, "_sample_discrete_laplace", lambda q: 0)
    monkeypatch.setattr(sacofa, "_sample_laplace", lambda scale: 0)
    monkeypatch.setattr(privacy, "_sample_discrete_laplace", lambda q: 0)


def output(result):
    return {row.activities: row.count for row in result.value.variants}


def test_semantics_changes_candidate_selection_not_just_count_noise(monkeypatch):
    zero_noise(monkeypatch)
    monkeypatch.setattr(sacofa, "_select_harmful", lambda q, score: False)
    rules = semantics(
        follows=(Relation("A", "B", "always"), Relation("A", "__OTHER__", "never")),
        precedes=(Relation("B", "A", "always"),),
        permitted_starts=("A",),
    )
    source = log(("A",), ("A", "B"), ("B",), ("A", "unknown"))
    actual = anonymize_sacofa(source, SACOFASpec(query(), rules))
    ordinary = anonymize_trace_variants(source, query())
    assert output(actual) == {("A", "B"): 1}
    assert output(ordinary) == {
        ("A",): 1,
        ("A", "B"): 1,
        ("B",): 1,
        ("A", "__OTHER__"): 1,
    }
    assert actual.value.profile == "sacofa_public_rules"
    assert actual.value.epsilon_composed == 3
    assert all(row.harmful_selected == 0 for row in actual.value.selection)


@pytest.mark.parametrize(
    "word, terminal, expected",
    [
        ((), False, 0),
        (("A",), False, 0),
        (("A",), True, 1),
        (("A", "B"), True, 0),
        (("B",), False, 2),
        (("A", "__OTHER__"), False, 1),
        (("A", "__OTHER__"), True, 2),
    ],
)
def test_independent_always_never_and_start_truth_table(word, terminal, expected):
    rules = semantics(
        follows=(Relation("A", "B", "always"), Relation("A", "__OTHER__", "never")),
        precedes=(Relation("B", "A", "always"),),
        permitted_starts=("A",),
    )
    assert sacofa._violations(word, terminal, rules) == expected


def test_reference_last_predecessor_prefix_convention_is_explicit():
    rules = semantics(precedes=(Relation("A", "B", "always"),))
    assert sacofa._violations(("A",), False, rules) == 1
    # This prefix score can be repaired by a repeated anchor. It is deliberately
    # NOT labelled a definitive LTL safety violation in the public API.
    assert sacofa._violations(("A", "B", "A"), True, rules) == 0


def test_sometimes_and_absent_anchor_are_unconstrained():
    rules = semantics(
        follows=(Relation("A", "B", "sometimes"), Relation("B", "A", "always"))
    )
    assert sacofa._violations(("A",), True, rules) == 0
    assert sacofa._violations((), True, rules) == 0


def test_unconstrained_public_rules_preserve_noiseless_variant_query(monkeypatch):
    zero_noise(monkeypatch)
    source = log((), ("A",), ("A", "B"), ("A", "B", "A"), ("unknown",))
    actual = anonymize_sacofa(source, SACOFASpec(query(), semantics()))
    assert output(actual) == output(anonymize_trace_variants(source, query()))


def test_smart_pruning_thresholds_are_distinct(monkeypatch):
    zero_noise(monkeypatch)
    monkeypatch.setattr(sacofa, "_select_harmful", lambda q, score: True)
    rules = semantics(permitted_starts=("A",))
    request = SACOFASpec(
        query(threshold=2, max_trace_length=1), rules, harmless_threshold=1
    )
    actual = anonymize_sacofa(log(("A",), ("B",)), request)
    assert output(actual) == {("A",): 1}
    assert actual.value.harmless_threshold == 1
    assert actual.value.harmful_threshold == 2


def test_harmful_unobserved_candidates_receive_noise_when_selected(monkeypatch):
    monkeypatch.setattr(sacofa, "_sample_discrete_laplace", lambda q: 1)
    monkeypatch.setattr(sacofa, "_select_harmful", lambda q, score: True)
    actual = anonymize_sacofa(
        log(),
        SACOFASpec(
            query(max_trace_length=1),
            semantics(permitted_starts=()),
        ),
    )
    assert output(actual) == {(): 1, ("A",): 1, ("B",): 1, ("__OTHER__",): 1}
    assert actual.value.selection[0].harmful_selected == 3


def test_semantic_violation_degree_is_clipped_before_exponential_selection(monkeypatch):
    zero_noise(monkeypatch)
    observed = []

    def selected(q, score):
        observed.append(score)
        return True

    monkeypatch.setattr(sacofa, "_select_harmful", selected)
    rules = semantics(
        permitted_starts=(),
        precedes=(
            Relation("A", "A", "always"),
            Relation("A", "B", "always"),
        ),
    )
    anonymize_sacofa(log(("A",)), SACOFASpec(query(), rules, max_semantic_violations=2))
    assert 2 in observed
    assert max(observed) == 2


def test_exact_subset_exponential_distribution_factorization():
    q, harms = Fraction(2, 3), (1, 2, 3)
    subsets = tuple(product((False, True), repeat=3))
    weights = {
        selected: q ** sum(harm for included, harm in zip(selected, harms) if included)
        for selected in subsets
    }
    normalizer = sum(weights.values(), Fraction())
    product_probabilities = []
    for selected in subsets:
        probability = Fraction(1)
        for included, harm in zip(selected, harms):
            weight = q**harm
            probability *= weight / (1 + weight) if included else 1 / (1 + weight)
        assert probability == weights[selected] / normalizer
        product_probabilities.append(probability)
    assert sum(product_probabilities, Fraction()) == 1


@pytest.mark.parametrize(
    "draw, expected", [(0, True), (3, True), (4, False), (12, False)]
)
def test_exact_harmful_coin_threshold(monkeypatch, draw, expected):
    bounds = []

    def random_integer(bound):
        bounds.append(bound)
        return draw

    monkeypatch.setattr(sacofa.secrets, "randbelow", random_integer)
    assert sacofa._select_harmful(Fraction(2, 3), 2) is expected
    assert bounds == [13]  # q**2=4/9 => inclusion probability 4/13.


def test_zero_bias_is_uniform_subset_distribution(monkeypatch):
    zero_noise(monkeypatch)
    parameters = []

    def selected(q, score):
        parameters.append(q)
        return True

    monkeypatch.setattr(sacofa, "_select_harmful", selected)
    actual = anonymize_sacofa(
        log(("A",)),
        SACOFASpec(query(), semantics(permitted_starts=()), semantic_bias=0),
    )
    assert parameters and set(parameters) == {Fraction(1)}
    assert actual.value.subset_q_numerator == actual.value.subset_q_denominator == 1


@pytest.mark.parametrize("bias", [1e-60, 1e-100, 5e-324])
def test_tiny_nonzero_public_bias_has_a_valid_exact_rational_parameter(bias):
    parameter = sacofa._subset_parameter(bias)
    assert 0 < parameter < 1
    assert parameter == 1 / (1 + Fraction(bias))


def test_semantics_learned_only_from_prior_dp_release_and_budget_composed(monkeypatch):
    zero_noise(monkeypatch)
    source = log(("A", "B"), ("A", "B"), ("A",))
    prior = anonymize_trace_variants(source, query(epsilon=1.5)).value
    learned = sacofa_semantics_from_release(prior)
    follows = {(row.anchor, row.related): row.kind for row in learned.follows}
    precedes = {(row.anchor, row.related): row.kind for row in learned.precedes}
    assert follows["A", "B"] == "sometimes"
    assert follows["B", "A"] == "never"
    assert precedes["B", "A"] == "always"
    assert follows["__OTHER__", "A"] == "sometimes"  # no anchor evidence
    assert learned.permitted_starts == ("A",)
    actual = anonymize_sacofa(source, SACOFASpec(query(), learned))
    assert actual.value.profile == "sacofa_dp_learned_rules"
    assert actual.value.epsilon_prior_semantics == 1.5
    assert actual.value.epsilon_frequency == 3
    assert actual.value.epsilon_composed == 4.5
    assert actual.value.semantics.prior_release_nonce == prior.release_nonce


def test_repeated_anchor_first_followers_and_last_predecessors(monkeypatch):
    zero_noise(monkeypatch)
    release = anonymize_trace_variants(
        log(("A", "B", "A")), query(max_trace_length=3)
    ).value
    learned = sacofa_semantics_from_release(release)
    follows = {(row.anchor, row.related): row.kind for row in learned.follows}
    precedes = {(row.anchor, row.related): row.kind for row in learned.precedes}
    assert follows["A", "A"] == follows["A", "B"] == "always"
    assert precedes["A", "A"] == precedes["A", "B"] == "always"


def test_empty_prior_release_has_explicit_no_evidence_semantics(monkeypatch):
    zero_noise(monkeypatch)
    learned = sacofa_semantics_from_release(
        anonymize_trace_variants(log(), query()).value
    )
    assert learned.permitted_starts == ()
    assert all(row.kind == "sometimes" for row in (*learned.follows, *learned.precedes))


def test_float_prior_cannot_establish_machine_dp_semantics(monkeypatch):
    zero_noise(monkeypatch)
    monkeypatch.setattr(privacy, "_sample_laplace", lambda scale: 0)
    prior = anonymize_trace_variants(log(("A",)), query(mechanism="laplace")).value
    with pytest.raises(ValueError, match="discrete case-level"):
        sacofa_semantics_from_release(prior)
    with pytest.raises(TypeError):
        sacofa_semantics_from_release(log(("A",)))


def test_prior_adjacency_cannot_be_silently_reinterpreted(monkeypatch):
    zero_noise(monkeypatch)
    prior = sacofa_semantics_from_release(
        anonymize_trace_variants(log(("A",)), query()).value
    )
    with pytest.raises(ValueError, match="same case adjacency"):
        SACOFASpec(query(adjacency="replace_case"), prior)


@pytest.mark.parametrize("left, right", [(1.0, 0.2), (0.1, 0.4), (0.7, 0.1)])
def test_composed_epsilon_never_rounds_below_exact_binary_budget(left, right):
    composed = sacofa._upper_budget_sum(left, right)
    assert Fraction(composed) >= Fraction(left) + Fraction(right)


def test_semantic_prior_uses_safe_request_bound_not_rounded_allocation(monkeypatch):
    zero_noise(monkeypatch)
    prior = anonymize_trace_variants(log(("A",)), query(epsilon=0.2)).value
    # The payload's epsilon_allocated is a numerical report; the declared request
    # bound is the conservative guarantee even if reporting rounded down.
    altered_report = replace(prior, epsilon_allocated=0.19)
    rules = sacofa_semantics_from_release(altered_report)
    assert rules.prior_epsilon == prior.epsilon_budget == 0.2
    actual = anonymize_sacofa(log(("A",)), SACOFASpec(query(epsilon=1.0), rules))
    assert Fraction(actual.value.epsilon_composed) >= Fraction(1.0) + Fraction(0.2)


def test_float_count_profile_keeps_noncertification(monkeypatch):
    zero_noise(monkeypatch)
    actual = anonymize_sacofa(
        log(("A",)), SACOFASpec(query(mechanism="laplace"), semantics())
    )
    assert "machine_dp_not_certified" in actual.value.privacy_model
    assert any(
        row.code == "floating_point_privacy_not_certified" for row in actual.issues
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"semantic_bias": -1},
        {"semantic_bias": float("nan")},
        {"semantic_bias": True},
        {"semantic_bias": 10**1000},
        {"max_semantic_violations": 0},
        {"max_semantic_violations": 101},
        {"max_semantic_violations": True},
        {"harmless_threshold": -1},
        {"harmless_threshold": True},
    ],
)
def test_bad_sacofa_settings_rejected(changes):
    with pytest.raises((ValueError, TypeError)):
        SACOFASpec(query(), semantics(), **changes)


def test_bad_rule_contracts_rejected():
    with pytest.raises(ValueError):
        Relation("A", "B", "perhaps")
    with pytest.raises(ValueError):
        Relation("", "B", "always")
    with pytest.raises(ValueError):
        semantics(follows=(Relation("A", "B", "always"), Relation("A", "B", "never")))
    with pytest.raises(ValueError):
        semantics(precedes=(Relation("A", "X", "always"),))
    with pytest.raises(ValueError):
        semantics(permitted_starts=("X",))
    with pytest.raises(ValueError):
        semantics(prior_epsilon=1)
    with pytest.raises(ValueError):
        semantics(origin="dp_trace_variant_release")
    with pytest.raises(ValueError):
        SACOFASpec(query(), SACOFASemantics(("A",)))


def test_private_envelope_and_real_result_roundtrip(monkeypatch):
    zero_noise(monkeypatch)
    actual = anonymize_sacofa(log(("A",)), SACOFASpec(query(), semantics()))
    released = sacofa_release(actual)
    document = json.dumps(asdict(released))
    assert actual.source_digest not in document
    assert actual.computation_id not in document
    assert "secret-case" not in document and "secret-event" not in document
    assert "Alice" not in document
    monkeypatch.setattr(results, "_schemas", lambda: sacofa.RESULT_SCHEMAS)
    assert results.result_from_json(results.result_json_bytes(actual)) == actual


def test_partial_input_is_unavailable_and_preserves_private_identity():
    source = case_traces(log(("A",)))
    source = replace(
        source,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("missing", "Incomplete"),),
    )
    actual = anonymize_sacofa(source, SACOFASpec(query(), semantics()))
    assert actual.status is ComputeStatus.UNAVAILABLE
    assert actual.source_digest == source.source_digest
    assert actual.value is None
    with pytest.raises(ValueError):
        sacofa_release(actual)


def test_real_secure_sacofa_smoke_no_seed_argument():
    actual = anonymize_sacofa(
        log(("A",)),
        SACOFASpec(query(max_trace_length=1), semantics(permitted_starts=("A",))),
    )
    assert actual.status is ComputeStatus.COMPUTED
    assert all(row.count > 0 for row in actual.value.variants)
    with pytest.raises(TypeError):
        anonymize_sacofa(log(), SACOFASpec(query(), semantics()), seed=1)
