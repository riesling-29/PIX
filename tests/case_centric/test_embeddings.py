"""Actual local SGD, held-out isolation and frozen-inference embedding checks."""

from dataclasses import FrozenInstanceError, replace
from math import log

import pytest

from pix.case_centric.embeddings import (
    EmbeddingSpec,
    EmbeddingTransformRequest,
    _logistic_loss,
    _step,
    fit_embeddings,
    transform_embeddings,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import result_from_json, result_json_bytes


def log_of(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                str(index),
                tuple(
                    CaseEvent(
                        f"{index}:{position}",
                        (CaseAttribute("concept:name", "string", token),),
                    )
                    for position, token in enumerate(sequence)
                ),
            )
            for index, sequence in enumerate(sequences)
        )
    )


def training_log():
    return log_of(*("ABABAB" for _ in range(8)), *("CDCDCD" for _ in range(8)))


@pytest.mark.parametrize("method", ["skipgram", "cbow", "pv_dbow", "pv_dm"])
def test_real_training_reduces_sampled_objective_and_is_seeded(method):
    log_data = training_log()
    spec = EmbeddingSpec(
        method=method, dimensions=4, window=1, epochs=25, learning_rate=0.1, seed=7
    )
    result = fit_embeddings(log_data, spec)
    assert result.status is ComputeStatus.COMPUTED
    model = result.value
    assert model.loss_history[0] == pytest.approx(log(2))
    assert model.loss_history[-1] < model.loss_history[0] * 0.7
    assert model == fit_embeddings(log_data, spec).value
    assert model != fit_embeddings(log_data, replace(spec, seed=8)).value
    assert any(value != 0 for row in model.output_vectors for value in row)
    assert len(model.loss_history) == spec.epochs + 1
    assert len(model.document_vectors) == (16 if method.startswith("pv_") else 0)


@pytest.mark.parametrize("label", [0, 1])
def test_step_matches_independent_finite_difference_gradient(label):
    inputs = [[0.2, -0.5], [0.1, 0.7]]
    output = [0.8, -0.3]
    original_inputs = [row[:] for row in inputs]
    original_output = output[:]
    epsilon, rate = 1e-6, 0.02

    def objective(word_rows, context):
        hidden = [(word_rows[0][d] + word_rows[1][d]) / 2 for d in range(2)]
        return _logistic_loss(sum(hidden[d] * context[d] for d in range(2)), label)

    expected = []
    for row in range(2):
        gradients = []
        for dimension in range(2):
            high, low = [x[:] for x in inputs], [x[:] for x in inputs]
            high[row][dimension] += epsilon
            low[row][dimension] -= epsilon
            gradients.append(
                (objective(high, output) - objective(low, output)) / (2 * epsilon)
            )
        expected.append(gradients)
    expected_output = []
    for dimension in range(2):
        high, low = output[:], output[:]
        high[dimension] += epsilon
        low[dimension] -= epsilon
        expected_output.append(
            (objective(inputs, high) - objective(inputs, low)) / (2 * epsilon)
        )
    _step(inputs, output, label, rate)
    for row in range(2):
        assert inputs[row] == pytest.approx(
            [original_inputs[row][d] - rate * expected[row][d] for d in range(2)]
        )
    assert output == pytest.approx(
        [original_output[d] - rate * expected_output[d] for d in range(2)]
    )


def test_input_occurrence_multiplicity_and_frozen_document_inference_gradient():
    repeated = [0.2, -0.4]
    output = [0.1, 0.6]
    separate = [repeated[:], repeated[:]]
    separate_output = output[:]
    before = repeated[:]
    _step([repeated, repeated], output, 1, 0.1)
    _step(separate, separate_output, 1, 0.1)
    assert repeated == pytest.approx([2 * separate[0][d] - before[d] for d in range(2)])
    assert output == separate_output
    doc, frozen_word, frozen_output = [0.2, -0.4], [0.1, 0.7], [0.5, -0.1]
    _step([doc, frozen_word], frozen_output, 1, 0.1, train_inputs=1, train_output=False)
    assert doc != [0.2, -0.4]
    assert frozen_word == [0.1, 0.7]
    assert frozen_output == [0.5, -0.1]


def test_training_selection_isolates_vocabulary_objective_and_digest_from_heldout_data():
    first = log_of("ABABA", "SECRET")
    second = log_of("ABABA", "CHANGED")
    spec = EmbeddingSpec(dimensions=3, epochs=3)
    a = fit_embeddings(first, spec, training_case_ids=("0",))
    b = fit_embeddings(second, spec, training_case_ids=("0",))
    assert a.value == b.value
    assert a.value.vocabulary == ("A", "B")
    assert a.source_digest != b.source_digest
    assert a.computation_id != b.computation_id
    # A held-out invalid activity is never read during training.
    malformed = replace(
        first, traces=(first.traces[0], CaseTrace("1", (CaseEvent("missing"),)))
    )
    assert fit_embeddings(malformed, spec, training_case_ids=("0",)).value == a.value
    assert (
        fit_embeddings(first, spec, training_case_ids=("missing",)).status
        is ComputeStatus.INVALID_INPUT
    )
    assert (
        fit_embeddings(first, spec, training_case_ids=()).status
        is ComputeStatus.UNAVAILABLE
    )


def test_training_order_canonicalized_and_minimum_count_does_not_bridge_context():
    original = log_of("ABAB", "BABA")
    shuffled = replace(original, traces=tuple(reversed(original.traces)))
    spec = EmbeddingSpec(epochs=2, dimensions=2)
    assert fit_embeddings(original, spec).value == fit_embeddings(shuffled, spec).value
    # Retain A and B but remove one rare intervening X; A-X-B must not become A-B.
    result = fit_embeddings(
        log_of("AXB", "A", "B"), EmbeddingSpec(window=1, minimum_count=2)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "no_embedding_contexts"


def test_word_pooling_repetition_empty_and_oov_are_explicit():
    model = fit_embeddings(
        log_of("ABABAB"), EmbeddingSpec(dimensions=3, epochs=5)
    ).value
    words = dict(zip(model.vocabulary, model.word_vectors))
    log_data = log_of("AAB", "AX", "X", "")
    mean = transform_embeddings(log_data, model)
    summed = transform_embeddings(log_data, model, aggregation="sum")
    assert mean.status is ComputeStatus.PARTIAL
    assert mean.value.rows[0].values == pytest.approx(
        [(2 * words["A"][d] + words["B"][d]) / 3 for d in range(3)]
    )
    assert summed.value.rows[0].values == pytest.approx(
        [2 * words["A"][d] + words["B"][d] for d in range(3)]
    )
    assert mean.value.rows[1].values == words["A"]
    assert (mean.value.rows[1].known_tokens, mean.value.rows[1].unknown_tokens) == (
        1,
        1,
    )
    assert mean.value.rows[2].values == (0.0, 0.0, 0.0)
    assert mean.value.rows[3].values == (0.0, 0.0, 0.0)
    assert {issue.at for issue in mean.issues} == {("1",), ("2",)}
    assert mean.computation_id != summed.computation_id
    assert transform_embeddings(log_of(""), model).status is ComputeStatus.COMPUTED


@pytest.mark.parametrize("method", ["pv_dbow", "pv_dm"])
def test_document_inference_learns_only_new_vector_and_is_batch_id_independent(method):
    model = fit_embeddings(
        training_log(),
        EmbeddingSpec(
            method=method, dimensions=4, window=1, epochs=20, learning_rate=0.1
        ),
    ).value
    before = repr(model)
    results = transform_embeddings(
        log_of("ABAB", "CDCD"), model, inference_epochs=50, inference_learning_rate=0.1
    )
    assert results.status is ComputeStatus.COMPUTED
    assert repr(model) == before
    for row in results.value.rows:
        assert row.inference_loss[-1] < row.inference_loss[0]
    assert results.value.rows[0].values != results.value.rows[1].values
    single = transform_embeddings(
        log_of("CDCD"), model, inference_epochs=50, inference_learning_rate=0.1
    )
    assert single.value.rows[0].values == results.value.rows[1].values
    assert single.value.rows[0].inference_loss == results.value.rows[1].inference_loss
    assert single.value.rows[0].values != model.document_vectors[0]
    assert (
        transform_embeddings(
            log_of("ABAB", "CDCD"),
            model,
            inference_epochs=50,
            inference_learning_rate=0.1,
        )
        == results
    )
    with pytest.raises(ValueError, match="sum pooling"):
        transform_embeddings(log_of("AB"), model, aggregation="sum")


def test_empty_and_single_vocabulary_or_no_context_never_return_untrained_model():
    for data in (log_of(), log_of(""), log_of("AAAA"), log_of("A", "B")):
        result = fit_embeddings(data)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
    # Doc2Vec has document prediction examples even for singleton traces.
    assert (
        fit_embeddings(log_of("A", "B"), EmbeddingSpec(method="pv_dbow")).status
        is ComputeStatus.COMPUTED
    )


@pytest.mark.parametrize("method", ["pv_dbow", "pv_dm"])
def test_omitted_document_tokens_cannot_inject_label_information_through_random_seed(
    method,
):
    model = fit_embeddings(
        log_of("ABAB"), EmbeddingSpec(method=method, dimensions=3, epochs=5)
    ).value
    x = transform_embeddings(log_of("AXB"), model).value.rows[0]
    y = transform_embeddings(log_of("AYB"), model).value.rows[0]
    assert x.values == y.values
    assert x.inference_loss == y.inference_loss
    assert (x.known_tokens, x.unknown_tokens) == (2, 1)


def test_empty_training_document_has_zero_vector_not_random_untrained_features():
    model = fit_embeddings(
        log_of("ABAB", ""), EmbeddingSpec(method="pv_dbow", dimensions=3)
    ).value
    assert model.document_vectors[1] == (0.0, 0.0, 0.0)


def test_positive_example_limit_is_not_silent_truncation():
    result = fit_embeddings(log_of("ABABABAB"), EmbeddingSpec(max_training_examples=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "embedding_training_limit"
    assert result.value is None
    model = fit_embeddings(
        log_of("AB"), EmbeddingSpec(method="pv_dbow", max_training_examples=2)
    ).value
    result = transform_embeddings(log_of("ABAB"), model)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "embedding_inference_limit"


def test_model_is_deeply_immutable_and_digest_detects_weight_tampering():
    model = fit_embeddings(log_of("ABAB"), EmbeddingSpec(dimensions=2, epochs=2)).value
    with pytest.raises(FrozenInstanceError):
        model.vocabulary = ("other",)
    with pytest.raises(TypeError):
        model.word_vectors[0][0] = 9.0
    changed = (
        (model.word_vectors[0][0] + 0.01, model.word_vectors[0][1]),
        *model.word_vectors[1:],
    )
    with pytest.raises(ValueError, match="digest"):
        replace(model, word_vectors=changed)
    with pytest.raises(ValueError, match="finite"):
        replace(model, word_vectors=((float("nan"), 0.0), *model.word_vectors[1:]))


@pytest.mark.parametrize(
    "changes",
    [
        {"method": "bert"},
        {"dimensions": True},
        {"dimensions": 0},
        {"window": 0},
        {"epochs": -1},
        {"minimum_count": 0},
        {"negative_samples": 0},
        {"learning_rate": float("nan")},
        {"learning_rate": 0},
        {"learning_rate": 2.0},
        {"seed": -1},
        {"max_training_examples": 0},
    ],
)
def test_spec_rejects_undefined_or_invalid_training_parameters(changes):
    with pytest.raises(ValueError):
        EmbeddingSpec(**changes)


def test_malformed_projection_propagates_and_parameter_identity_contains_classifier():
    invalid = CaseLog((CaseTrace("bad", (CaseEvent("missing"),)),))
    assert fit_embeddings(invalid).status is ComputeStatus.INVALID_INPUT
    model = fit_embeddings(log_of("ABAB"), EmbeddingSpec(epochs=2)).value
    assert transform_embeddings(invalid, model).status is ComputeStatus.INVALID_INPUT
    with pytest.raises(TypeError):
        EmbeddingSpec(trace_spec="bad")
    with pytest.raises(ValueError):
        EmbeddingTransformRequest(model, inference_epochs=0)
    assert model.parameters.trace_spec == CaseTraceSpec()


def test_large_dot_loss_is_finite_and_correct_for_both_labels():
    assert _logistic_loss(1000.0, 1) == 0.0
    assert _logistic_loss(-1000.0, 1) == 1000.0
    assert _logistic_loss(1000.0, 0) == 1000.0
    assert _logistic_loss(-1000.0, 0) == 0.0


def test_integer_learning_rates_normalize_before_identity_and_public_roundtrip():
    data = log_of("ABAB")
    integer_spec = EmbeddingSpec(
        method="pv_dbow", dimensions=2, epochs=1, negative_samples=1, learning_rate=1
    )
    float_spec = replace(integer_spec, learning_rate=1.0)
    assert type(integer_spec.learning_rate) is float
    fitted = fit_embeddings(data, integer_spec)
    assert fitted == fit_embeddings(data, float_spec)
    assert result_from_json(result_json_bytes(fitted)) == fitted
    transformed = transform_embeddings(
        data, fitted.value, inference_epochs=1, inference_learning_rate=1
    )
    assert type(transformed.spec.inference_learning_rate) is float
    assert transformed == transform_embeddings(
        data, fitted.value, inference_epochs=1, inference_learning_rate=1.0
    )
    assert result_from_json(result_json_bytes(transformed)) == transformed
