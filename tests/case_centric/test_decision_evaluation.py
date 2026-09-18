"""Held-out evidence uses whole cases and training-only feature vocabularies."""

from dataclasses import replace
from fractions import Fraction

import pytest

from pix.case_centric.decision_evaluation import (
    DecisionEvaluationRow,
    DecisionEvaluationSpec,
    EvaluationFeature,
    decision_rows_from_table,
    encode_decision_rows,
    evaluate_decision_table,
    evaluate_decision_tree,
    fit_decision_encoder,
)
from pix.case_centric.decision_mining import (
    DecisionFeatureSpec,
    DecisionTableSpec,
    extract_decision_table,
)
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus, computation_identity
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace

NUMERIC = (EvaluationFeature("amount", "numeric"),)
CATEGORICAL = (EvaluationFeature("channel", "categorical"),)


def population(*ids):
    return CaseLog(tuple(CaseTrace(case) for case in ids))


def row(case, value, target, *, row_id=None, groups=(), reasons=()):
    return DecisionEvaluationRow(
        row_id or case, case, (value,), target, groups, reasons
    )


def spec(train=("a", "b"), test=("c",), features=NUMERIC, **kwargs):
    return DecisionEvaluationSpec(features, train, test, **kwargs)


def test_manual_occurrence_confusion_and_case_balanced_accuracy():
    rows = (
        row("a", 0, "no"),
        row("b", 10, "yes"),
        row("c", 0, "no"),
        row("d", 10, "no"),
        row("e", 10, "yes", row_id="e:1"),
        row("e", 0, "no", row_id="e:2"),
    )
    result = evaluate_decision_tree(
        population("a", "b", "c", "d", "e"), rows, spec(test=("c", "d", "e"))
    )
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert {(r.actual, r.predicted): r.count for r in value.confusion} == {
        ("no", "no"): 2,
        ("no", "yes"): 1,
        ("yes", "yes"): 1,
    }
    assert value.occurrence_accuracy.as_fraction() == Fraction(3, 4)
    assert value.case_balanced_accuracy.as_fraction() == Fraction(2, 3)
    assert value.occurrence_coverage.as_fraction() == 1
    assert value.case_coverage.as_fraction() == 1
    assert value.scored_case_ids == value.fully_scored_case_ids == ("c", "d", "e")
    assert value.tree.training_case_ids == ("a", "b")
    assert result.computation_id == computation_identity(
        result.operator_id,
        result.operator_version,
        result.source_digest,
        result.spec,
        result.parent_computation_ids,
    )


def test_training_vocabulary_has_no_heldout_or_unknown_outcome_fit():
    rows = (
        row("a", "web", "yes"),
        row("b", "store", "no"),
        row("unlabelled", "unlabelled-only", None),
        row("c", "future", "yes"),
        row("d", "store", "no"),
    )
    encoder = fit_decision_encoder(rows, CATEGORICAL, ("a", "b", "unlabelled"))
    assert encoder.categories == (("store", "web"),)
    assert encoder.training_row_ids == ("a", "b")
    transformed = encode_decision_rows(encoder, (rows[-2], rows[-1]))
    assert transformed[0].values == (0, 0)
    assert transformed[0].unknown_category_mask == (True,)
    assert transformed[0].missing_mask == (False,)
    assert transformed[1].values == (1, 0)
    result = evaluate_decision_tree(
        population("a", "b", "unlabelled", "c", "d"),
        rows,
        spec(train=("a", "b", "unlabelled"), test=("c", "d"), features=CATEGORICAL),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.occurrence_accuracy.as_fraction() == 1
    assert result.value.occurrence_coverage.as_fraction() == Fraction(1, 2)
    assert result.value.test_rows[0].prediction is None
    assert result.value.test_rows[0].reasons == ("unknown_category:channel",)
    changed = replace(rows[-2], values=("different-future",), target="new-target")
    altered = evaluate_decision_tree(
        population("a", "b", "unlabelled", "c", "d"),
        rows[:-2] + (changed, rows[-1]),
        spec(train=("a", "b", "unlabelled"), test=("c", "d"), features=CATEGORICAL),
    )
    assert altered.value.encoder == result.value.encoder
    assert altered.value.tree == result.value.tree
    assert altered.computation_id != result.computation_id


def test_training_only_vocabulary_excludes_ineligible_and_incomplete_rows():
    features = CATEGORICAL + NUMERIC
    rows = (
        DecisionEvaluationRow("a", "a", ("usable", 1), "yes"),
        DecisionEvaluationRow("b", "b", ("missing-numeric", None), "yes"),
        DecisionEvaluationRow(
            "c", "c", ("ambiguous", 1), "yes", exclusion_reasons=("ambiguous_witness",)
        ),
    )
    encoder = fit_decision_encoder(rows, features, ("a", "b", "c"))
    assert encoder.categories == (("usable",), ())
    assert encoder.training_row_ids == ("a",)


def test_missing_values_and_unknown_targets_are_excluded_not_scored_as_zero():
    rows = (
        row("a", 0, "no"),
        row("b", 10, "yes"),
        row("c", None, "no"),
        row("d", 10, None),
        row("e", 0, "unseen-class"),
    )
    result = evaluate_decision_tree(
        population("a", "b", "c", "d", "e"), rows, spec(test=("c", "d", "e"))
    )
    assert result.value.scored_row_count == 1
    assert result.value.occurrence_accuracy.as_fraction() == 0
    assert result.value.occurrence_coverage.as_fraction() == Fraction(1, 3)
    assert result.value.test_rows[0].missing_mask == (True,)
    assert result.value.test_rows[0].reasons == ("missing_feature:amount",)
    assert result.value.test_rows[1].reasons == ("unknown_outcome",)
    assert result.value.test_rows[2].prediction == "no"


def test_case_selection_cannot_split_repeated_occurrences():
    with pytest.raises(ValueError, match="overlap"):
        spec(train=("a", "b"), test=("b",))
    rows = (
        row("a", 0, "no", row_id="a:1"),
        row("a", 1, "no", row_id="a:2"),
        row("b", 10, "yes"),
        row("c", 10, "yes"),
    )
    result = evaluate_decision_tree(population("a", "b", "c"), rows, spec())
    assert result.value.tree.training_case_ids == ("a:1", "a:2", "b")
    assert result.value.training_case_ids == ("a", "b")
    assert tuple(r.case_id for r in result.value.test_rows) == ("c",)


@pytest.mark.parametrize("excluded", [False, True])
def test_shared_groups_reject_even_excluded_rows(excluded):
    rows = (
        row("a", 0, "no", groups=("object:shared",)),
        row("b", 10, "yes"),
        row(
            "c",
            10,
            "yes",
            groups=("object:shared",),
            reasons=("excluded",) if excluded else (),
        ),
    )
    with pytest.raises(ValueError, match="share group"):
        evaluate_decision_tree(population("a", "b", "c"), rows, spec())


def test_cases_without_rows_remain_in_case_coverage_denominator():
    rows = (row("a", 0, "no"), row("b", 10, "yes"), row("c", 10, "yes"))
    result = evaluate_decision_tree(
        population("a", "b", "c", "d"), rows, spec(test=("c", "d"))
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.missing_test_case_ids == ("d",)
    assert result.value.occurrence_coverage.as_fraction() == 1
    assert result.value.case_coverage.as_fraction() == Fraction(1, 2)


def test_no_usable_training_is_unavailable_and_no_heldout_fit():
    rows = (row("a", None, "no"), row("b", 10, None), row("c", 10, "yes"))
    result = evaluate_decision_tree(population("a", "b", "c"), rows, spec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "empty_training_population" in {issue.code for issue in result.issues}


def test_training_budget_does_not_fallback_to_in_sample_evaluation():
    rows = (row("a", 0, "no"), row("b", 10, "yes"), row("c", 10, "yes"))
    result = evaluate_decision_tree(
        population("a", "b", "c"), rows, spec(max_examples=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "decision_example_limit" in {issue.code for issue in result.issues}


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"max_rows": 2}, "decision_evaluation_row_limit"),
        ({"max_encoded_values": 2}, "decision_encoding_limit"),
    ],
)
def test_encoding_budgets_fail_before_allocating_or_fitting(kwargs, code):
    rows = (row("a", "web", "no"), row("b", "store", "yes"), row("c", "web", "no"))
    result = evaluate_decision_tree(
        population("a", "b", "c"), rows, spec(features=CATEGORICAL, **kwargs)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert code in {issue.code for issue in result.issues}


def test_empty_test_population_has_unknown_metrics():
    rows = (row("a", 0, "no"), row("b", 10, "yes"))
    result = evaluate_decision_tree(population("a", "b"), rows, spec(test=()))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.occurrence_accuracy is None
    assert result.value.case_balanced_accuracy is None
    assert result.value.case_coverage is None


def test_empty_category_is_observed_and_encoded_column_names_do_not_collide():
    features = (
        EvaluationFeature("a", "categorical"),
        EvaluationFeature('a", "b', "categorical"),
    )
    rows = (DecisionEvaluationRow("a", "a", ('b", "c', ""), "yes"),)
    encoder = fit_decision_encoder(rows, features, ("a",))
    assert encoder.categories == (('b", "c',), ("",))
    assert len(set(encoder.columns)) == 2
    assert encode_decision_rows(encoder, rows)[0].values == (1, 1)


@pytest.mark.parametrize("value", [True, float("nan"), float("inf"), object()])
def test_invalid_raw_value_rejected(value):
    with pytest.raises(ValueError):
        row("a", value, "yes")


def test_invalid_dimensions_types_population_and_duplicate_rows_rejected():
    with pytest.raises(ValueError, match="type"):
        fit_decision_encoder((row("a", "string", "yes"),), NUMERIC, ("a",))
    with pytest.raises(ValueError, match="dimensions"):
        fit_decision_encoder(
            (DecisionEvaluationRow("a", "a", (), "yes"),), NUMERIC, ("a",)
        )
    rows = (row("a", 0, "yes"), row("a", 1, "yes"))
    with pytest.raises(ValueError, match="unique"):
        evaluate_decision_tree(population("a", "b", "c"), rows, spec())
    with pytest.raises(ValueError, match="outside"):
        evaluate_decision_tree(population("a", "b"), (row("a", 0, "yes"),), spec())


def choice_model():
    return PetriNet(
        tuple(Place(place) for place in ("start", "choice", "end")),
        tuple(Transition("t" + label, label) for label in ("A", "B", "C")),
        (
            Arc("start", "tA"),
            Arc("tA", "choice"),
            Arc("choice", "tB"),
            Arc("tB", "end"),
            Arc("choice", "tC"),
            Arc("tC", "end"),
        ),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )


def decision_log():
    return CaseLog(
        tuple(
            CaseTrace(
                case,
                (
                    CaseEvent(
                        case + ":prefix",
                        (
                            CaseAttribute("concept:name", "string", "A"),
                            CaseAttribute("amount", "int", amount),
                        ),
                    ),
                    CaseEvent(
                        case + ":outcome",
                        (
                            CaseAttribute("concept:name", "string", outcome),
                            CaseAttribute("amount", "int", 9999),
                        ),
                    ),
                ),
            )
            for case, amount, outcome in (("a", 0, "B"), ("b", 10, "C"), ("c", 10, "C"))
        )
    )


def test_real_conformance_table_adapter_preserves_prior_event_features_and_provenance():
    table = extract_decision_table(
        decision_log(),
        choice_model(),
        DecisionTableSpec((DecisionFeatureSpec("amount", "amount"),)),
    )
    rows = decision_rows_from_table(table.value, "choice")
    assert [row.values for row in rows] == [(0,), (10,), (10,)]
    result = evaluate_decision_table(table, "choice", spec())
    assert result.status is ComputeStatus.COMPUTED
    assert result.source_digest == table.source_digest
    assert table.computation_id in result.parent_computation_ids
    assert result.spec.evidence_payload_digest is not None
    assert result.value.occurrence_accuracy.as_fraction() == 1
    assert result.value.test_rows[0].prediction == "tC"
    assert result.value.tree.training_case_ids == tuple(
        sorted(row.row_id for row in rows[:2])
    )


def test_table_adapter_rejects_schema_identity_and_place_changes():
    table = extract_decision_table(
        decision_log(),
        choice_model(),
        DecisionTableSpec((DecisionFeatureSpec("amount", "amount"),)),
    )
    with pytest.raises(ValueError, match="schema"):
        evaluate_decision_table(table, "choice", spec(features=CATEGORICAL))
    with pytest.raises(ValueError, match="identity"):
        evaluate_decision_table(
            replace(table, computation_id="tampered"), "choice", spec()
        )
    with pytest.raises(ValueError, match="unknown decision place"):
        evaluate_decision_table(table, "absent", spec())


def test_truncated_upstream_occurrences_never_claim_complete_case_coverage():
    model = choice_model()
    model = replace(
        model,
        transitions=model.transitions + (Transition("tR", "R"),),
        arcs=model.arcs + (Arc("end", "tR"), Arc("tR", "start")),
    )
    dataset = CaseLog(
        tuple(
            CaseTrace(
                case,
                tuple(
                    CaseEvent(
                        f"{case}:{index}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute("amount", "int", amount),
                        ),
                    )
                    for index, activity in enumerate(word)
                ),
            )
            for case, word, amount in (
                ("a", "AB", 0),
                ("b", "AC", 10),
                ("c", "ACRAC", 10),
            )
        )
    )
    table = extract_decision_table(
        dataset,
        model,
        DecisionTableSpec((DecisionFeatureSpec("amount", "amount"),), max_rows=3),
    )
    assert table.value.decision_occurrence_count == 4
    assert table.value.omitted_row_count == 1
    result = evaluate_decision_table(table, "choice", spec())
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.occurrence_accuracy.as_fraction() == 1
    assert result.value.retained_occurrence_coverage.as_fraction() == 1
    assert result.value.occurrence_coverage is None
    assert result.value.coverage_population_complete is False
    assert result.value.upstream_omitted_row_count == 1
    assert result.value.fully_scored_case_ids == ()
    assert result.value.case_coverage.as_fraction() == 1
    assert "decision_population_unknown" in {issue.code for issue in result.issues}


def test_row_order_is_canonical_and_does_not_change_result_identity():
    rows = (row("a", 0, "no"), row("b", 10, "yes"), row("c", 10, "yes"))
    first = evaluate_decision_tree(population("a", "b", "c"), rows, spec())
    second = evaluate_decision_tree(
        population("a", "b", "c"), tuple(reversed(rows)), spec()
    )
    assert first == second


def test_split_search_budget_propagates_partial_model_with_explicit_coverage():
    rows = (
        row("a", 0, "no"),
        row("b", 10, "yes"),
        row("c", 20, "no"),
        row("d", 10, "yes"),
    )
    result = evaluate_decision_tree(
        population("a", "b", "c", "d"),
        rows,
        spec(train=("a", "b", "c"), test=("d",), max_split_evaluations=1),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.tree.status == "resource_limit"
    assert result.value.occurrence_coverage.as_fraction() == 1
    assert result.value.occurrence_accuracy.as_fraction() == 0
    assert "decision_split_limit" in {issue.code for issue in result.issues}


def test_partial_case_reports_scored_accuracy_separate_from_complete_coverage():
    rows = (
        row("a", 0, "no"),
        row("b", 10, "yes"),
        row("c", 10, "yes", row_id="c:observed"),
        row("c", None, "yes", row_id="c:missing"),
    )
    result = evaluate_decision_tree(population("a", "b", "c"), rows, spec())
    assert result.value.occurrence_accuracy.as_fraction() == 1
    assert result.value.case_balanced_accuracy.as_fraction() == 1
    assert result.value.occurrence_coverage.as_fraction() == Fraction(1, 2)
    assert result.value.case_coverage.as_fraction() == 1
    assert result.value.scored_case_ids == ("c",)
    assert result.value.fully_scored_case_ids == ()


def test_complete_partial_and_unavailable_results_roundtrip():
    from pix.results import result_from_json, result_json_bytes

    dataset = population("a", "b", "c")
    rows = (row("a", 0, "no"), row("b", 10, "yes"), row("c", 10, "yes"))
    results = (
        evaluate_decision_tree(dataset, rows, spec()),
        evaluate_decision_tree(dataset, rows[:-1] + (row("c", None, None),), spec()),
        evaluate_decision_tree(dataset, rows, spec(max_examples=1)),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result
