"""Known vector geometry, fixed-model boundaries and persisted retrieval evidence."""

from dataclasses import replace
from fractions import Fraction
from math import sqrt

import pytest

from pix.case_centric.embedding_retrieval import (
    EmbeddingBatch,
    EmbeddingRetrievalSpec,
    EmbeddingSpace,
    EmbeddingTrainingProvenance,
    RetrievalEmbeddingRow,
    as_embedding_batch,
    retrieve_embedding_neighbors,
    validate_embedding_retrieval_result,
)
from pix.case_centric.embeddings import (
    EmbeddingSpec,
    fit_embeddings,
    transform_embeddings,
)
from pix.case_centric.features import FeatureSpec, fit_features, transform_features
from pix.case_centric.transformer_embeddings import (
    TransformerEmbeddingMatrix,
    TransformerEmbeddingRequest,
    TransformerEmbeddingRow,
    TransformerEmbeddingSpec,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace

SPACE = EmbeddingSpace(
    "test.explicit-encoder.v1",
    "model-123",
    ("east", "north"),
    "identity-transform",
    EmbeddingTrainingProvenance("external_declared", "train-456", ("train",)),
)


def batch(entries, role="corpus", source=None, space=SPACE):
    return EmbeddingBatch(
        space,
        source or role + "-source",
        role,
        tuple(
            RetrievalEmbeddingRow(name, tuple(float(x) for x in vector))
            for name, vector in entries
        ),
    )


def result_value(result):
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def neighbors(result):
    return result_value(result).queries[0].neighbors


def log_of(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"{i}:{j}", (CaseAttribute("concept:name", "string", label),)
                    )
                    for j, label in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def test_cosine_orthogonal_opposite_parallel_and_competition_rank():
    corpus = batch(
        (
            ("opposite", (-1, 0)),
            ("north", (0, 1)),
            ("east-long", (5, 0)),
            ("east", (1, 0)),
        )
    )
    query = batch((("query", (1, 0)),), "query")
    matches = neighbors(
        retrieve_embedding_neighbors(corpus, query, EmbeddingRetrievalSpec(k=4))
    )
    assert [(x.case_id, x.score, x.rank) for x in matches] == [
        ("east", 1.0, 1),
        ("east-long", 1.0, 1),
        ("north", 0.0, 3),
        ("opposite", -1.0, 4),
    ]


@pytest.mark.parametrize(
    "metric,expected",
    [
        ("dot", [("b", 2.0), ("a", 1.0), ("c", 0.0), ("d", -1.0)]),
        ("euclidean", [("a", 0.0), ("b", 1.0), ("c", sqrt(2)), ("d", 2.0)]),
    ],
)
def test_independent_known_dot_and_euclidean(metric, expected):
    corpus = batch((("a", (1, 0)), ("b", (2, 0)), ("c", (0, 1)), ("d", (-1, 0))))
    query = batch((("q", (1, 0)),), "query")
    matches = neighbors(
        retrieve_embedding_neighbors(corpus, query, EmbeddingRetrievalSpec(4, metric))
    )
    assert [(x.case_id, x.score) for x in matches] == expected


@pytest.mark.parametrize("metric", ["cosine", "dot", "euclidean"])
def test_top_k_includes_boundary_ties_or_deterministic_truncation(metric):
    corpus = batch((("c", (1, 0)), ("a", (1, 0)), ("b", (1, 0))))
    query = batch((("q", (1, 0)),), "query")
    result = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(1, metric)
    )
    assert [x.case_id for x in neighbors(result)] == ["a", "b", "c"]
    truncated = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(1, metric, False)
    )
    assert [x.case_id for x in neighbors(truncated)] == ["a"]
    assert result.value.queries[0].eligible_count == 3
    permuted = retrieve_embedding_neighbors(
        replace(corpus, rows=tuple(reversed(corpus.rows))),
        query,
        EmbeddingRetrievalSpec(1, metric),
    )
    assert result.value == permuted.value


@pytest.mark.parametrize(
    "field,value",
    [
        ("model_digest", "other-model"),
        ("encoder_id", "other-encoder"),
        ("dimension_labels", ("north", "east")),
        ("transform_digest", "other-transform"),
        ("training", EmbeddingTrainingProvenance("unknown")),
    ],
)
def test_equal_width_different_spaces_fail(field, value):
    corpus = batch((("a", (1, 0)),))
    query = batch((("q", (1, 0)),), "query", space=replace(SPACE, **{field: value}))
    result = retrieve_embedding_neighbors(corpus, query)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "embedding_space_mismatch"


def test_source_identity_self_exclusion_and_exact_comparison_cap():
    corpus = batch((("a", (1, 0)), ("b", (0, 1))), source="same")
    query = batch((("a", (1, 0)),), "query", source="same")
    spec = EmbeddingRetrievalSpec(exclude_same_source_case=True, max_comparisons=1)
    result = retrieve_embedding_neighbors(corpus, query, spec)
    assert [x.case_id for x in neighbors(result)] == ["b"]
    assert result.value.comparison_count == 1
    different_source = replace(query, source_digest="different-log")
    limited = retrieve_embedding_neighbors(corpus, different_source, spec)
    assert limited.status is ComputeStatus.UNAVAILABLE
    included = retrieve_embedding_neighbors(
        corpus, different_source, replace(spec, max_comparisons=2)
    )
    assert [x.case_id for x in neighbors(included)] == ["a", "b"]


@pytest.mark.parametrize("role", ["corpus", "query"])
def test_zero_norm_cosine_invalidates_explicitly(role):
    corpus = batch((("a", (0, 0) if role == "corpus" else (1, 0)),))
    query = batch((("q", (0, 0) if role == "query" else (1, 0)),), "query")
    result = retrieve_embedding_neighbors(corpus, query)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "embedding_zero_norm"
    assert result.issues[0].at[0] == role


@pytest.mark.parametrize("metric,score", [("dot", 0.0), ("euclidean", 5.0)])
def test_zero_vector_has_defined_dot_and_euclidean(metric, score):
    result = retrieve_embedding_neighbors(
        batch((("a", (0, 0)),)),
        batch((("q", (3, 4)),), "query"),
        EmbeddingRetrievalSpec(metric=metric),
    )
    assert neighbors(result)[0].score == score


def test_numeric_scaling_avoids_false_cosine_overflow_or_underflow():
    corpus = batch((("huge", (1e308, 1e308)), ("tiny", (1e-308, 1e-308))))
    result = retrieve_embedding_neighbors(corpus, batch((("q", (1, 1)),), "query"))
    assert [x.score for x in neighbors(result)] == pytest.approx([1.0, 1.0])


def test_dot_exact_fallback_handles_huge_cancellation_but_real_overflow_unavailable():
    result = retrieve_embedding_neighbors(
        batch((("a", (1e308, -1e308)),)),
        batch((("q", (1e308, 1e308)),), "query"),
        EmbeddingRetrievalSpec(metric="dot"),
    )
    assert neighbors(result)[0].score == 0.0
    result = retrieve_embedding_neighbors(
        batch((("a", (1e308, 1e308)),)),
        batch((("q", (1e308, 1e308)),), "query"),
        EmbeddingRetrievalSpec(metric="dot"),
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "embedding_numeric_failure"


def test_dot_subnormal_sum_does_not_create_a_false_zero_boundary_tie():
    space = replace(SPACE, dimension_labels=("x", "y", "z"))
    vector = (1e-162, 1e-162, 1e-162)
    expected = float(sum((Fraction(x) * Fraction(x) for x in vector), Fraction()))
    assert expected == 5e-324
    corpus = batch((("nonzero", vector), ("zero", (0, 0, 0))), space=space)
    query = batch((("q", vector),), "query", space=space)
    result = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(1, "dot")
    )
    assert [(item.case_id, item.score) for item in neighbors(result)] == [
        ("nonzero", expected)
    ]


def test_all_counts_sources_values_and_query_identities_are_retained():
    corpus = batch((("a", (1, 0)), ("b", (0, 1))))
    query = batch((("q", (2, 0)), ("r", (0, 4))), "query")
    result = retrieve_embedding_neighbors(corpus, query, EmbeddingRetrievalSpec(1))
    value = result_value(result)
    assert (value.corpus_count, value.query_count, value.comparison_count) == (2, 2, 4)
    assert value.corpus_source_digest == "corpus-source"
    assert value.query_source_digest == "query-source"
    assert value.queries[1].query.values == (0.0, 4.0)
    assert value.queries[0].neighbors[0].vector == corpus.rows[0]
    altered = retrieve_embedding_neighbors(
        replace(
            corpus, rows=(replace(corpus.rows[0], values=(2.0, 0.0)), corpus.rows[1])
        ),
        query,
        EmbeddingRetrievalSpec(1),
    )
    assert result.computation_id != altered.computation_id
    assert result.spec.corpus_content_digest != altered.spec.corpus_content_digest


@pytest.mark.parametrize("empty_role", ["corpus", "query", "both"])
def test_empty_populations_report_exact_counts(empty_role):
    corpus = batch(()) if empty_role in ("corpus", "both") else batch((("a", (1, 0)),))
    query = (
        batch((), "query")
        if empty_role in ("query", "both")
        else batch((("q", (1, 0)),), "query")
    )
    value = result_value(retrieve_embedding_neighbors(corpus, query))
    assert value.comparison_count == 0
    assert value.corpus_count == len(corpus.rows)
    assert value.query_count == len(query.rows)
    assert all(not row.neighbors for row in value.queries)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, 1])
def test_nonfinite_and_nonfloat_vectors_rejected(value):
    with pytest.raises(ValueError):
        RetrievalEmbeddingRow("a", (value, 0.0))


def test_token_count_and_text_digest_provenance_cannot_contradict_itself():
    with pytest.raises(ValueError, match="token total"):
        RetrievalEmbeddingRow(
            "a", (1.0, 0.0), known_tokens=3, unknown_tokens=2, token_count=4
        )
    with pytest.raises(ValueError, match="SHA-256"):
        RetrievalEmbeddingRow("a", (1.0, 0.0), text_sha256="not-a-sha256")


def test_duplicate_dimensions_duplicate_rows_width_and_role_rejected():
    with pytest.raises(ValueError):
        replace(SPACE, dimension_labels=("a", "a"))
    with pytest.raises(ValueError):
        batch((("a", (1, 0)), ("a", (0, 1))))
    with pytest.raises(ValueError):
        batch((("a", (1,)),))
    with pytest.raises(ValueError):
        retrieve_embedding_neighbors(
            batch((("q", (1, 0)),), "query"), batch((("q", (1, 0)),), "query")
        )


@pytest.mark.parametrize("method", ["skipgram", "cbow", "pv_dbow", "pv_dm"])
def test_learned_embedding_adapter_and_retrieval_preserve_frozen_training(method):
    training = log_of("ABAB", "BABA")
    model = result_value(
        fit_embeddings(
            training,
            EmbeddingSpec(method=method, dimensions=3, epochs=2, negative_samples=1),
        )
    )
    saved_model = repr(model)
    corpus = transform_embeddings(training, model, inference_epochs=2)
    query = transform_embeddings(log_of("AB"), model, inference_epochs=2)
    adapted = as_embedding_batch(query, role="query")
    assert adapted.space.training.source_digest == model.training_source_digest
    assert adapted.space.training.case_ids == model.training_case_ids
    assert adapted.rows[0].known_tokens == 2
    value = result_value(retrieve_embedding_neighbors(corpus, query))
    assert value.query_count == 1
    assert value.space.model_digest == model.model_digest
    assert repr(model) == saved_model
    assert transform_embeddings(log_of("AB"), model, inference_epochs=2) == query


@pytest.mark.parametrize(
    "method,option",
    [("skipgram", {"aggregation": "sum"}), ("pv_dbow", {"inference_epochs": 3})],
)
def test_same_model_different_effective_inference_profile_is_incompatible(
    method, option
):
    training = log_of("ABAB", "BABA")
    model = result_value(
        fit_embeddings(
            training,
            EmbeddingSpec(method=method, dimensions=2, epochs=1, negative_samples=1),
        )
    )
    corpus = transform_embeddings(training, model, inference_epochs=2)
    query = transform_embeddings(
        log_of("AB"), model, **({"inference_epochs": 2} | option)
    )
    result = retrieve_embedding_neighbors(corpus, query)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "embedding_space_mismatch"


def test_native_oov_requires_opt_in_and_retains_partial_evidence():
    training = log_of("ABAB")
    model = result_value(
        fit_embeddings(
            training, EmbeddingSpec(dimensions=2, epochs=1, negative_samples=1)
        )
    )
    corpus = transform_embeddings(training, model)
    query = transform_embeddings(log_of("AZ"), model)
    assert query.status is ComputeStatus.PARTIAL
    rejected = retrieve_embedding_neighbors(corpus, query)
    assert rejected.status is ComputeStatus.INVALID_INPUT
    accepted = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(allow_partial=True)
    )
    assert accepted.status is ComputeStatus.PARTIAL
    assert accepted.value.queries[0].query.unknown_tokens == 1
    assert accepted.value.queries[0].query.token_count == 2
    assert any(
        issue.code == "embedding_out_of_vocabulary" and issue.at[0] == "query"
        for issue in accepted.issues
    )
    assert query.computation_id in accepted.parent_computation_ids
    with pytest.raises(ValueError, match="partial"):
        as_embedding_batch(
            replace(query, status=ComputeStatus.COMPUTED, issues=()), role="query"
        )


def test_all_oov_still_fails_cosine_with_partial_opt_in():
    training = log_of("ABAB")
    model = result_value(
        fit_embeddings(
            training, EmbeddingSpec(dimensions=2, epochs=1, negative_samples=1)
        )
    )
    result = retrieve_embedding_neighbors(
        transform_embeddings(training, model),
        transform_embeddings(log_of("ZZ"), model),
        EmbeddingRetrievalSpec(allow_partial=True),
    )
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "embedding_zero_norm"


def test_stale_identity_wrong_version_and_inconsistent_payload_rejected():
    training = log_of("ABAB")
    model = result_value(
        fit_embeddings(
            training, EmbeddingSpec(dimensions=2, epochs=1, negative_samples=1)
        )
    )
    encoded = transform_embeddings(training, model)
    with pytest.raises(ValueError, match="identity"):
        as_embedding_batch(replace(encoded, computation_id="fake"), role="query")
    with pytest.raises(ValueError, match="version"):
        as_embedding_batch(replace(encoded, operator_version="9.0.0"), role="query")
    with pytest.raises(ValueError, match="fixed embedding model"):
        as_embedding_batch(
            replace(encoded, value=replace(encoded.value, model_digest="wrong")),
            role="query",
        )
    altered = replace(
        encoded,
        value=replace(
            encoded.value, rows=(replace(encoded.value.rows[0], values=(1.0, 0.0)),)
        ),
    )
    before = retrieve_embedding_neighbors(encoded, encoded)
    after = retrieve_embedding_neighbors(altered, altered)
    assert before.computation_id != after.computation_id


def transformer_fixture(
    *,
    normalized=False,
    checkpoint="a" * 64,
    source="corpus",
    truncated=False,
    versions=None,
):
    """Explicit contract fixture, not evidence of executing a neural backend."""
    parameters = TransformerEmbeddingSpec(
        "C:/fixed-checkpoint", normalize=normalized, allow_truncation=truncated
    )
    versions = versions or tuple(
        (name, "test-1")
        for name in ("sentence-transformers", "transformers", "torch", "tokenizers")
    )
    request = TransformerEmbeddingRequest(parameters, checkpoint, versions)
    row = TransformerEmbeddingRow(
        "case", None, "b" * 64, 100 if truncated else 4, truncated, (1.0, 0.0)
    )
    matrix = TransformerEmbeddingMatrix("trace", 2, (row,), checkpoint, 20)
    operator = "pix.case_centric.transformer_embeddings"
    issues = (
        (
            ComputeIssue(
                "transformer_truncated", "Truncated by declared profile", ("case",)
            ),
        )
        if truncated
        else ()
    )
    return ComputationResult(
        operator,
        "1.0.0",
        source,
        request,
        ComputeStatus.PARTIAL if truncated else ComputeStatus.COMPUTED,
        matrix,
        issues,
        computation_identity(operator, "1.0.0", source, request),
    )


def test_transformer_adapter_keeps_checkpoint_unknown_training_and_text_counts():
    corpus, query = transformer_fixture(), transformer_fixture(source="query")
    value = result_value(retrieve_embedding_neighbors(corpus, query))
    assert value.space.model_digest == "a" * 64
    assert value.space.training == EmbeddingTrainingProvenance("unknown")
    assert value.queries[0].query.token_count == 4
    assert value.queries[0].query.text_sha256 == "b" * 64


@pytest.mark.parametrize(
    "kwargs",
    [
        {"normalized": True},
        {"checkpoint": "c" * 64},
        {
            "versions": tuple(
                (name, "test-2")
                for name in (
                    "sentence-transformers",
                    "transformers",
                    "torch",
                    "tokenizers",
                )
            )
        },
    ],
)
def test_transformer_inference_schema_checkpoint_and_backend_mismatches_fail(kwargs):
    result = retrieve_embedding_neighbors(
        transformer_fixture(), transformer_fixture(source="query", **kwargs)
    )
    assert result.status is ComputeStatus.INVALID_INPUT


def test_transformer_truncation_remains_partial_even_after_retrieval():
    encoded = transformer_fixture(truncated=True)
    result = retrieve_embedding_neighbors(
        encoded, encoded, EmbeddingRetrievalSpec(allow_partial=True)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.queries[0].query.truncated
    with pytest.raises(ValueError, match="partial"):
        as_embedding_batch(
            replace(encoded, status=ComputeStatus.COMPUTED, issues=()), role="query"
        )


def test_transformer_truncation_permission_does_not_change_coordinate_space():
    corpus, query = (
        transformer_fixture(),
        transformer_fixture(truncated=True, source="query"),
    )
    result = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(allow_partial=True)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.queries[0].query.truncated
    request = replace(
        corpus.spec, backend_versions=tuple(reversed(corpus.spec.backend_versions))
    )
    reordered = replace(
        corpus,
        spec=request,
        computation_id=computation_identity(
            corpus.operator_id, corpus.operator_version, corpus.source_digest, request
        ),
    )
    assert (
        as_embedding_batch(corpus, role="corpus").space
        == as_embedding_batch(reordered, role="query").space
    )


def test_fixed_feature_adapter_preserves_labelled_dimensions_and_no_query_refit():
    training = log_of("AA", "BB")
    model = result_value(fit_features(training, FeatureSpec(encoding="tfidf")))
    corpus = transform_features(training, model)
    query = transform_features(log_of("A"), model)
    value = result_value(retrieve_embedding_neighbors(corpus, query))
    assert value.space.encoder_id == "pix.fixed-case-features.v1"
    assert value.space.model_digest == model.model_digest
    assert '"terms": ["A"]' in value.space.dimension_labels[0]
    assert value.queries[0].neighbors[0].case_id == "0"
    assert model.document_count == 2


def test_feature_missing_values_and_event_vectors_require_explicit_resolution():
    training = log_of("AA", "BB")
    model = result_value(
        fit_features(training, FeatureSpec(numeric_attributes=("missing",)))
    )
    with pytest.raises(ValueError, match="missing"):
        as_embedding_batch(transform_features(training, model), role="corpus")
    event_model = result_value(fit_features(training, FeatureSpec(level="event")))
    with pytest.raises(ValueError, match="pooling"):
        as_embedding_batch(transform_features(training, event_model), role="corpus")


@pytest.mark.parametrize("metric", ["cosine", "dot", "euclidean"])
def test_public_result_serialization_roundtrip(metric):
    from pix._mining_registry import mining_schemas
    from pix.results import result_from_json, result_json_bytes

    if "pix.case_centric.retrieve_embedding_neighbors" not in mining_schemas():
        pytest.skip("root registry integration is not yet present")
    result = retrieve_embedding_neighbors(
        batch((("a", (1, 0)), ("b", (0, 1)))),
        batch((("q", (1, 0)),), "query"),
        EmbeddingRetrievalSpec(metric=metric),
    )
    assert result_from_json(result_json_bytes(result)) == result


def test_payload_score_width_and_rank_invariants_reject_impossible_evidence():
    result = retrieve_embedding_neighbors(
        batch((("a", (1, 0)),)), batch((("q", (1, 0)),), "query")
    )
    payload, row = result.value, result.value.queries[0]
    with pytest.raises(ValueError, match="rank"):
        replace(row, neighbors=(replace(row.neighbors[0], rank=2),))
    wrong_score = replace(row, neighbors=(replace(row.neighbors[0], score=100.0),))
    with pytest.raises(ValueError, match="cosine"):
        replace(payload, queries=(wrong_score,))
    wrong_width = replace(row, query=replace(row.query, values=(1.0,)))
    with pytest.raises(ValueError, match="width"):
        replace(payload, queries=(wrong_width,))
    wrong_norm = replace(row, query=replace(row.query, values=(0.0, 0.0)))
    with pytest.raises(ValueError, match="zero-norm"):
        replace(payload, queries=(wrong_norm,))


def test_retrieval_envelope_rejects_payload_request_contradictions():
    from pix.results import result_json_bytes

    result = retrieve_embedding_neighbors(
        batch((("a", (1, 0)),)), batch((("q", (1, 0)),), "query")
    )
    changed = replace(
        result,
        value=replace(result.value, metric="euclidean", corpus_source_digest="wrong"),
    )
    with pytest.raises(ValueError, match="metric/source"):
        validate_embedding_retrieval_result(changed)
    with pytest.raises(ValueError, match="input digest"):
        validate_embedding_retrieval_result(replace(result, source_digest="wrong"))
    with pytest.raises(ValueError, match="metric/source"):
        result_json_bytes(changed)


def test_public_persistence_rejects_partial_token_evidence_relabelled_computed():
    from pix.results import result_json_bytes

    corpus = batch((("a", (1, 0)),))
    query = batch((("q", (1, 0)),), "query")
    query = replace(query, rows=(replace(query.rows[0], unknown_tokens=1),))
    partial = retrieve_embedding_neighbors(
        corpus, query, EmbeddingRetrievalSpec(allow_partial=True)
    )
    with pytest.raises(ValueError, match="partial retrieval status"):
        result_json_bytes(replace(partial, status=ComputeStatus.COMPUTED, issues=()))


@pytest.mark.parametrize("status", ["partial", "invalid", "limit"])
def test_public_roundtrip_preserves_partial_and_failure_status(status):
    from pix._mining_registry import mining_schemas
    from pix.results import result_from_json, result_json_bytes

    if "pix.case_centric.retrieve_embedding_neighbors" not in mining_schemas():
        pytest.skip("root registry integration is not yet present")
    corpus = batch((("a", (1, 0)), ("b", (0, 1))))
    query = batch((("q", (1, 0)),), "query")
    if status in ("partial", "invalid"):
        query = replace(query, rows=(replace(query.rows[0], unknown_tokens=1),))
    spec = EmbeddingRetrievalSpec(
        allow_partial=status == "partial",
        max_comparisons=1 if status == "limit" else 100,
    )
    result = retrieve_embedding_neighbors(corpus, query, spec)
    assert (
        result.status.value
        == {"partial": "partial", "invalid": "invalid_input", "limit": "unavailable"}[
            status
        ]
    )
    assert result_from_json(result_json_bytes(result)) == result
