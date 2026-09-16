"""Aggregate arithmetic and missing-population policy, using actual kernels."""

from dataclasses import replace
from fractions import Fraction
from math import sqrt

import pytest

from pix.case_centric.conformance import AlignmentFitnessSpec, ETPrecisionSpec
from pix.case_centric.evaluation import EvaluationSpec, evaluate_model
from pix.case_centric.model_analysis import ComplexitySpec, ReachabilitySpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(sequence)
                ),
            )
            for i, sequence in enumerate(sequences)
        )
    )


def model(branch=False):
    transitions = (Transition("a", "A"),) + ((Transition("b", "B"),) if branch else ())
    return PetriNet(
        (Place("i"), Place("o")),
        transitions,
        tuple(
            arc
            for transition in transitions
            for arc in (Arc("i", transition.id), Arc(transition.id, "o"))
        ),
        Marking((("i", 1),)),
        Marking((("o", 1),)),
    )


def weights(**values):
    return tuple(
        (name, (values.get(name, 0), 1))
        for name in ("fitness", "precision", "generalization", "simplicity")
    )


def metrics(result):
    return {row.name: row for row in result.value.metrics}


@pytest.mark.parametrize(
    "count,expected,generalization", [(1, 3 / 4, 0), (4, 7 / 8, 1 / 2)]
)
def test_manual_chain_quality(count, expected, generalization):
    result = evaluate_model(log(*[("A",)] * count), model())
    rows = metrics(result)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.weighted_score == expected
    assert result.value.fitness_precision_fscore == (1, 1)
    assert rows["generalization"].score == generalization
    assert (
        rows["fitness"].score
        == rows["precision"].score
        == rows["simplicity"].score
        == 1
    )
    assert all(row.effective_weight == (1, 4) for row in rows.values())
    assert result.value.weighted_score_scope == "all_enabled_metrics"
    assert result.value.case_ids == tuple(f"c{i}" for i in range(count))
    assert (
        result.value.weighted_score_ratio is None
    )  # generalization is native floating-point


def test_branch_quality_counts_unseen_transition_and_escaping_label():
    result = evaluate_model(log(*[("A",)] * 4), model(branch=True))
    rows = metrics(result)
    assert rows["precision"].score == 1 / 2
    assert rows["generalization"].score == 1 / 4
    assert result.value.weighted_score == 11 / 16
    assert result.value.fitness_precision_fscore == (2, 3)


def test_pooled_fitness_and_case_mean_are_explicitly_different():
    data = log(("A",), ("A",), ("A",), ("A",), ())
    pooled = evaluate_model(data, model())
    mean = evaluate_model(
        data, model(), EvaluationSpec(fitness_aggregation="case_mean")
    )
    assert Fraction(*metrics(pooled)["fitness"].exact_ratio) == Fraction(8, 9)
    assert Fraction(*metrics(mean)["fitness"].exact_ratio) == Fraction(4, 5)
    assert pooled.value.weighted_score == pytest.approx(61 / 72)
    assert mean.value.weighted_score == pytest.approx((4 / 5 + 1 + 1 / 2 + 1) / 4)
    assert pooled.computation_id != mean.computation_id


def test_fscore_zero_is_not_an_unknown_value():
    result = evaluate_model(log(("X",)), model())
    assert metrics(result)["fitness"].score == metrics(result)["precision"].score == 0
    assert result.value.fitness_precision_fscore == (0, 1)
    assert result.value.weighted_score == 1 / 4
    assert result.value.undefined_metrics == ()


def test_token_balance_and_alignment_profiles_are_not_interchanged():
    token = evaluate_model(log(("A", "X")), model())
    aligned = evaluate_model(
        log(("A", "X")), model(), EvaluationSpec(fitness_method="alignment")
    )
    assert metrics(token)["fitness"].score == 1
    assert Fraction(*metrics(aligned)["fitness"].exact_ratio) == Fraction(2, 3)
    assert token.value.weighted_score == 3 / 4
    assert aligned.value.weighted_score == pytest.approx(2 / 3)
    assert aligned.value.fitness_precision_fscore == (4, 5)
    assert "token_balance" in metrics(token)["fitness"].profile
    assert "one_minus_cost" in metrics(aligned)["fitness"].profile


def test_empty_source_requires_explicit_missing_metric_policy():
    strict = evaluate_model(log(), model())
    renormalized = evaluate_model(
        log(), model(), EvaluationSpec(missing_metric_policy="renormalize_defined")
    )
    assert strict.status is ComputeStatus.PARTIAL
    assert strict.value.weighted_score is None
    assert strict.value.fitness_precision_fscore is None
    assert strict.value.included_metrics == ()
    assert strict.value.included_weight == (0, 1)
    assert strict.value.undefined_metrics == ("fitness", "precision", "generalization")
    assert renormalized.value.weighted_score == 1
    assert renormalized.value.weighted_score_scope == "defined_metrics_only"
    assert renormalized.value.included_metrics == ("simplicity",)
    assert metrics(renormalized)["simplicity"].effective_weight == (1, 1)
    assert renormalized.status is ComputeStatus.PARTIAL


def test_partial_fitness_does_not_fall_back_to_completed_subset():
    parameters = EvaluationSpec(
        fitness_method="alignment",
        alignment_fitness=AlignmentFitnessSpec(AlignmentSpec(max_states=2)),
    )
    strict = evaluate_model(log(("A",), ("A", "X")), model(), parameters)
    limited = metrics(strict)["fitness"]
    assert limited.completed_case_count == 1 and limited.requested_case_count == 2
    assert limited.score is None and limited.state == "undefined"
    assert limited.result_status is ComputeStatus.PARTIAL
    assert limited.issues and limited.computation_id
    assert strict.value.weighted_score is None
    renormalized = evaluate_model(
        log(("A",), ("A", "X")),
        model(),
        replace(parameters, missing_metric_policy="renormalize_defined"),
    )
    assert renormalized.value.undefined_metrics == ("fitness",)
    assert renormalized.value.weighted_score == pytest.approx((3 - 1 / sqrt(2)) / 3)
    assert renormalized.value.included_metrics == (
        "precision",
        "generalization",
        "simplicity",
    )
    assert renormalized.value.fitness_precision_fscore is None


def test_zero_weight_disables_kernel_and_does_not_create_missing_score(monkeypatch):
    import pix.case_centric.evaluation as module

    def must_not_run(*args, **kwargs):
        raise AssertionError("disabled metric was evaluated")

    monkeypatch.setattr(module, "measure_token_fitness", must_not_run)
    monkeypatch.setattr(module, "measure_et_precision", must_not_run)
    monkeypatch.setattr(module, "measure_token_generalization", must_not_run)
    result = evaluate_model(
        log(), model(), EvaluationSpec(weights=weights(simplicity=1))
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.disabled_metrics == ("fitness", "precision", "generalization")
    assert result.value.undefined_metrics == ()
    assert result.value.weighted_score == 1
    assert result.value.fitness_precision_fscore is None
    assert all(
        metrics(result)[name].computation_id is None
        for name in result.value.disabled_metrics
    )


def test_simplicity_remains_defined_when_other_complexity_analysis_is_partial():
    result = evaluate_model(
        log(("A",)),
        model(),
        EvaluationSpec(
            weights=weights(simplicity=1),
            simplicity=ComplexitySpec(reachability=ReachabilitySpec(max_states=1)),
        ),
    )
    row = metrics(result)["simplicity"]
    assert row.score == 1 and row.state == "defined"
    assert row.result_status is ComputeStatus.PARTIAL
    assert row.issues and result.issues
    assert result.value.weighted_score == 1
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.undefined_metrics == ()


def test_only_rational_metrics_produce_exact_weighted_ratio():
    result = evaluate_model(
        log(("A",)),
        model(branch=True),
        EvaluationSpec(weights=weights(fitness=1, precision=3)),
    )
    assert result.value.weighted_score_ratio == (5, 8)
    assert result.value.weighted_score == 5 / 8
    assert metrics(result)["fitness"].effective_weight == (1, 4)
    assert metrics(result)["precision"].effective_weight == (3, 4)


def test_huge_exact_weights_normalize_without_float_overflow():
    enormous = 10**1000
    result = evaluate_model(
        log(("A",)),
        model(branch=True),
        EvaluationSpec(weights=weights(fitness=enormous, precision=enormous)),
    )
    assert result.value.weighted_score_ratio == (3, 4)
    assert result.value.weighted_score == 3 / 4


def test_child_parent_lineage_and_common_source_are_preserved():
    source = case_traces(log(("A",), ("A",)))
    result = evaluate_model(source, model())
    assert result.value.trace_computation_id == source.computation_id
    assert result.parent_computation_ids[0] == source.computation_id
    assert len(result.parent_computation_ids) == 5
    for row in result.value.metrics:
        assert row.computation_id in result.parent_computation_ids
        if row.name != "simplicity":
            assert row.source_digest == source.source_digest
            assert row.parent_computation_ids == (source.computation_id,)
            assert row.population == "whole_source"
        else:
            assert row.source_digest == result.spec.model_digest
            assert row.population == "whole_model"
    changed = evaluate_model(
        source, model(), EvaluationSpec(precision=ETPrecisionSpec("alignment"))
    )
    assert result.computation_id != changed.computation_id
    assert (
        metrics(result)["precision"].computation_id
        != metrics(changed)["precision"].computation_id
    )


def test_source_issues_survive_even_when_only_model_metric_is_enabled():
    source = case_traces(log(("A",)))
    issue = ComputeIssue("source_note", "Preserve this input evidence.")
    annotated = replace(source, issues=(issue,))
    result = evaluate_model(
        annotated, model(), EvaluationSpec(weights=weights(simplicity=1))
    )
    assert issue in result.issues


def test_partial_source_is_not_silently_evaluated_as_common_population():
    source = case_traces(log(("A",)))
    partial = replace(
        source,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("partial_input", "Only a subset was projected."),),
    )
    result = evaluate_model(partial, model())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None and result.parent_computation_ids == (
        source.computation_id,
    )
    assert result.issues[0].code == "partial_input"


def test_registered_aggregate_roundtrip_complete_partial_and_disabled():
    from pix.results import result_from_json, result_json_bytes

    results = (
        evaluate_model(log(("A",)), model()),
        evaluate_model(log(), model()),
        evaluate_model(
            log(), model(), EvaluationSpec(missing_metric_policy="renormalize_defined")
        ),
        evaluate_model(log(), model(), EvaluationSpec(weights=weights(simplicity=1))),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "invalid",
    [
        weights(),
        weights(fitness=-1),
        (("fitness", (1, 1)),),
        weights(fitness=1) + (("fitness", (1, 1)),),
        tuple((name, (1, 0)) for name, _ in weights()),
        tuple((name, (True, 1)) for name, _ in weights()),
    ],
)
def test_invalid_weight_specs_are_rejected(invalid):
    with pytest.raises((TypeError, ValueError)):
        EvaluationSpec(weights=invalid)


def test_unknown_profiles_and_unapproved_subset_policy_are_rejected():
    with pytest.raises(ValueError):
        EvaluationSpec(population_policy="different_completed_subsets")
    with pytest.raises(ValueError):
        EvaluationSpec(missing_metric_policy="missing_is_zero")
    with pytest.raises(ValueError):
        EvaluationSpec(fitness_method="heuristic")
