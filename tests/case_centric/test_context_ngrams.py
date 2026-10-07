from dataclasses import replace
from math import log

import pytest

from pix.case_centric.context_ngrams import (
    ContextNGramSpec,
    fit_context_ngrams,
    transform_context_ngrams,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute as A
from pix.event_log import CaseEvent, CaseLog, CaseTrace
from pix.results import result_from_json, result_json_bytes


def source(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}-{j}",
                        (
                            A("concept:name", "string", activity),
                            A("tool", "string", "browser"),
                        ),
                    )
                    for j, activity in enumerate(seq)
                ),
            )
            for i, seq in enumerate(sequences)
        )
    )


def encode(data, spec=ContextNGramSpec()):
    fitted = fit_context_ngrams(data, spec)
    assert fitted.status is ComputeStatus.COMPUTED, fitted.issues
    result = transform_context_ngrams(data, fitted.value)
    return fitted, result


def values(matrix, case=0):
    return dict(zip((c.terms for c in matrix.columns), matrix.rows[case].values))


def test_exact_overlaps_boundaries_empty_cases_and_evidence():
    fitted, result = encode(source("ABAB", "AAA", "", "B"))
    assert result.status is ComputeStatus.COMPUTED
    assert values(result.value.matrix)[("A", "B")] == 2
    assert values(result.value.matrix, 1)[("A", "A")] == 2
    assert values(result.value.matrix, 1)[("A", "A", "A")] == 1
    assert not any(values(result.value.matrix, 2).values())
    ab = [
        o.event_ids
        for o in result.value.occurrences
        if o.case_id == "c0" and o.terms == ("A", "B")
    ]
    assert ab == [("e0-0", "e0-1"), ("e0-2", "e0-3")]
    assert result.value.occurrence_count == 9 + 6 + 0 + 1
    assert result_from_json(result_json_bytes(fitted)) == fitted
    assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize("encoding", ["count", "binary", "tfidf"])
def test_count_binary_tfidf_independent_values(encoding):
    _, result = encode(
        source("AAB", "B", ""), ContextNGramSpec(encoding=encoding, ngram_max=1)
    )
    row = values(result.value.matrix)
    expected = {
        "count": (2, 1),
        "binary": (1, 1),
        "tfidf": (2 * (log(4 / 2) + 1), log(4 / 3) + 1),
    }[encoding]
    assert (row[("A",)], row[("B",)]) == pytest.approx(expected)


def test_fit_does_not_read_bad_heldout_attributes_or_learn_vocabulary():
    data = source("AA", "Z")
    bad = CaseTrace(
        "c1",
        (CaseEvent("e1-0", (A("concept:name", "string", "Z"), A("tool", "list"))),),
    )
    data = replace(data, traces=(data.traces[0], bad))
    fitted = fit_context_ngrams(
        data, ContextNGramSpec(token_attributes=("tool",)), training_case_ids=("c0",)
    )
    assert fitted.status is ComputeStatus.COMPUTED
    assert fitted.value.feature_model.document_count == 1
    assert (
        transform_context_ngrams(data, fitted.value).status
        is ComputeStatus.INVALID_INPUT
    )
    plain = fit_context_ngrams(source("A", "Z"), training_case_ids=("c0",)).value
    transformed = transform_context_ngrams(source("Z"), plain)
    assert transformed.status is ComputeStatus.PARTIAL
    assert transformed.value.matrix.rows[0].unknown_term_count == 1
    assert len(plain.feature_model.columns) == 1


def test_typed_context_and_missing_are_distinct():
    base = source("AAA")
    trace = base.traces[0]
    events = tuple(
        replace(e, attributes=(e.attributes[0], A("tool", kind, val)))
        for e, kind, val in zip(
            trace.events, ("int", "string", "boolean"), (1, "1", True)
        )
    )
    data = replace(base, traces=(replace(trace, events=events),))
    _, result = encode(data, ContextNGramSpec(token_attributes=("tool",), ngram_max=1))
    assert len(result.value.matrix.columns) == 3
    assert result.value.matrix.rows[0].values == (1, 1, 1)
    missing = CaseLog(
        (CaseTrace("x", (CaseEvent("y", (A("concept:name", "string", "A"),)),)),)
    )
    assert (
        fit_context_ngrams(missing, ContextNGramSpec(token_attributes=("tool",))).status
        is ComputeStatus.INVALID_INPUT
    )
    assert (
        fit_context_ngrams(
            missing, ContextNGramSpec(token_attributes=("tool",), missing="tag")
        ).status
        is ComputeStatus.COMPUTED
    )


def test_evidence_cap_does_not_cap_counts_and_limits_never_claim_complete():
    data = source("AAAA")
    _, result = encode(data, ContextNGramSpec(max_evidence=1))
    assert result.status is ComputeStatus.PARTIAL
    assert values(result.value.matrix)[("A",)] == 4
    assert result.value.omitted_evidence_count == 8
    for spec in (
        ContextNGramSpec(max_occurrences=2),
        ContextNGramSpec(max_vocabulary=1),
        ContextNGramSpec(max_matrix_cells=1),
    ):
        limited = fit_context_ngrams(data, spec)
        assert limited.status is ComputeStatus.UNAVAILABLE
        assert limited.value is None


def test_same_activity_counts_but_different_bigrams():
    _, result = encode(source("ABBA", "ABAB"))
    a, b = values(result.value.matrix), values(result.value.matrix, 1)
    assert a[("A",)] == b[("A",)] == 2
    assert a[("B",)] == b[("B",)] == 2
    assert a[("B", "B")] == 1 and b[("B", "B")] == 0
