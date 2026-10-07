"""Native learned activity embeddings with explicit fit/inference boundaries.

Word2Vec uses skip-gram or averaged CBOW with negative sampling; Doc2Vec uses
PV-DBOW or averaged PV-DM with negative sampling. All arithmetic is local Python.
The PIX profile fixes a full context window, frequency**0.75 noise distribution,
and a seeded negative-sample objective reused over epochs. It does not reproduce
Gensim's dynamic windows, subsampling, scheduler, threading or numerical results.

Only selected training cases determine vocabulary, weights and model identity.
Doc2Vec transform optimizes a new document vector against frozen learned weights;
it never returns a training document vector merely because case IDs coincide.
Inputs are full observed traces. For prediction, supply an explicit prefix log:
this module cannot infer which observations were available at a historical time.

Count2Vec is a count baseline, implemented by features.FeatureSpec(encoding="count"),
not a learned dense encoding. Transformer inference lives in transformer_embeddings.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from collections import Counter
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from math import exp, isfinite, log1p
from random import Random
from typing import ClassVar, Literal

from pix.compute._common import _result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest, case_traces


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _positive(value: object, name: str) -> None:
    if type(value) not in (int, float) or not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")


def _strings(value: object, name: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(x, str) or not x for x in value
    ):
        raise TypeError(f"{name} must be a tuple of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class EmbeddingSpec:
    method: Literal["skipgram", "cbow", "pv_dbow", "pv_dm"] = "skipgram"
    dimensions: int = 16
    window: int = 2
    minimum_count: int = 1
    negative_samples: int = 5
    epochs: int = 20
    learning_rate: float = 0.025
    seed: int = 0
    max_training_examples: int = 100_000
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.method not in ("skipgram", "cbow", "pv_dbow", "pv_dm"):
            raise ValueError("unknown embedding method")
        for name in (
            "dimensions",
            "window",
            "minimum_count",
            "negative_samples",
            "epochs",
            "max_training_examples",
        ):
            _integer(getattr(self, name), name, 1)
        _integer(self.seed, "seed")
        _positive(self.learning_rate, "learning_rate")
        if self.learning_rate > 1:
            raise ValueError("learning_rate must be <= 1")
        object.__setattr__(self, "learning_rate", float(self.learning_rate))
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class EmbeddingFitRequest:
    parameters: EmbeddingSpec
    training_case_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, EmbeddingSpec):
            raise TypeError("parameters must be EmbeddingSpec")
        if self.training_case_ids is not None:
            _strings(self.training_case_ids, "training_case_ids")
            object.__setattr__(
                self, "training_case_ids", tuple(sorted(self.training_case_ids))
            )


def _digest(facts: object) -> str:
    encoded = json.dumps(
        facts,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        "pix.case-embedding-model.v1:sha256:"
        + sha256(encoded.encode("utf-8")).hexdigest()
    )


def _model_digest(model: EmbeddingModel) -> str:
    facts = asdict(model)
    facts.pop("model_digest")
    return _digest(facts)


def _matrix(value: object, rows: int, dimensions: int, name: str) -> None:
    if not isinstance(value, tuple) or len(value) != rows:
        raise ValueError(f"{name} has incorrect row count")
    if any(not isinstance(row, tuple) or len(row) != dimensions for row in value):
        raise ValueError(f"{name} has incorrect dimensions")
    if any(type(x) is not float or not isfinite(x) for row in value for x in row):
        raise ValueError(f"{name} requires finite floats")


@dataclass(frozen=True, slots=True)
class EmbeddingModel:
    parameters: EmbeddingSpec
    vocabulary: tuple[str, ...]
    token_counts: tuple[int, ...]
    word_vectors: tuple[tuple[float, ...], ...]
    output_vectors: tuple[tuple[float, ...], ...]
    document_vectors: tuple[tuple[float, ...], ...]
    training_case_ids: tuple[str, ...]
    training_source_digest: str
    objective_examples: int
    loss_history: tuple[float, ...]
    model_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, EmbeddingSpec):
            raise TypeError("parameters must be EmbeddingSpec")
        _strings(self.vocabulary, "vocabulary")
        _strings(self.training_case_ids, "training_case_ids")
        if len(self.vocabulary) < 2 or self.vocabulary != tuple(
            sorted(self.vocabulary)
        ):
            raise ValueError("vocabulary must contain at least two sorted tokens")
        if self.training_case_ids != tuple(sorted(self.training_case_ids)):
            raise ValueError("training case IDs must be sorted")
        if not isinstance(self.token_counts, tuple) or len(self.token_counts) != len(
            self.vocabulary
        ):
            raise ValueError("one frequency per vocabulary item is required")
        for count in self.token_counts:
            _integer(count, "token count", self.parameters.minimum_count)
        dimensions = self.parameters.dimensions
        _matrix(self.word_vectors, len(self.vocabulary), dimensions, "word_vectors")
        _matrix(self.output_vectors, len(self.vocabulary), dimensions, "output_vectors")
        doc_count = (
            len(self.training_case_ids)
            if self.parameters.method.startswith("pv_")
            else 0
        )
        _matrix(self.document_vectors, doc_count, dimensions, "document_vectors")
        _integer(self.objective_examples, "objective_examples", 1)
        if (
            not isinstance(self.loss_history, tuple)
            or len(self.loss_history) != self.parameters.epochs + 1
        ):
            raise ValueError(
                "loss_history must contain initial loss and one loss per epoch"
            )
        if any(
            type(value) is not float or not isfinite(value) or value < 0
            for value in self.loss_history
        ):
            raise ValueError("loss history must contain nonnegative finite floats")
        if (
            not isinstance(self.training_source_digest, str)
            or not self.training_source_digest
        ):
            raise ValueError("training source digest is required")
        if self.model_digest != _model_digest(self):
            raise ValueError("embedding model digest does not match its facts")


@dataclass(frozen=True, slots=True)
class EmbeddingTransformRequest:
    fitted_model: EmbeddingModel
    aggregation: Literal["mean", "sum"] = "mean"
    inference_epochs: int = 30
    inference_learning_rate: float = 0.025

    def __post_init__(self) -> None:
        if not isinstance(self.fitted_model, EmbeddingModel):
            raise TypeError("fitted_model must be EmbeddingModel")
        if self.aggregation not in ("mean", "sum"):
            raise ValueError("aggregation must be mean or sum")
        if (
            self.fitted_model.parameters.method.startswith("pv_")
            and self.aggregation != "mean"
        ):
            raise ValueError(
                "Doc2Vec infers a document vector; token sum pooling does not apply"
            )
        _integer(self.inference_epochs, "inference_epochs", 1)
        _positive(self.inference_learning_rate, "inference_learning_rate")
        if self.inference_learning_rate > 1:
            raise ValueError("inference_learning_rate must be <= 1")
        object.__setattr__(
            self, "inference_learning_rate", float(self.inference_learning_rate)
        )


@dataclass(frozen=True, slots=True)
class EmbeddingRow:
    case_id: str
    values: tuple[float, ...]
    known_tokens: int
    unknown_tokens: int
    inference_loss: tuple[float, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("case_id must be nonempty")
        _matrix((self.values,), 1, len(self.values), "row values")
        _integer(self.known_tokens, "known_tokens")
        _integer(self.unknown_tokens, "unknown_tokens")
        if not isinstance(self.inference_loss, tuple) or any(
            type(x) is not float or not isfinite(x) or x < 0
            for x in self.inference_loss
        ):
            raise ValueError("inference_loss must contain nonnegative finite floats")


@dataclass(frozen=True, slots=True)
class EmbeddingMatrix:
    dimensions: int
    rows: tuple[EmbeddingRow, ...]
    model_digest: str
    method: str

    def __post_init__(self) -> None:
        _integer(self.dimensions, "dimensions", 1)
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, EmbeddingRow) for row in self.rows
        ):
            raise TypeError("rows must be a tuple of EmbeddingRow")
        if len({row.case_id for row in self.rows}) != len(self.rows):
            raise ValueError("case IDs must be unique")
        if any(len(row.values) != self.dimensions for row in self.rows):
            raise ValueError("all embedding rows must have the declared dimensions")
        if not isinstance(self.model_digest, str) or not self.model_digest:
            raise ValueError("model digest is required")
        if self.method not in ("skipgram", "cbow", "pv_dbow", "pv_dm"):
            raise ValueError("unknown embedding method")


def _logistic_loss(dot: float, label: int) -> float:
    # softplus(dot) - label*dot, without overflow or cancellation at large |dot|.
    return max(dot, 0.0) - label * dot + log1p(exp(-abs(dot)))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + exp(-value))
    exponential = exp(value)
    return exponential / (1.0 + exponential)


def _step(
    inputs: list[list[float]],
    output: list[float],
    label: int,
    rate: float,
    *,
    train_output: bool = True,
    train_inputs: int | None = None,
) -> None:
    """One simultaneous gradient step on sigmoid binary cross-entropy.

    Repeated input references each receive their occurrence's gradient. In
    inference only the leading document input is mutable; context weights freeze.
    """
    divisor = len(inputs)
    hidden = [sum(vector[d] for vector in inputs) / divisor for d in range(len(output))]
    old_output = output[:]
    delta = (_sigmoid(sum(a * b for a, b in zip(hidden, old_output))) - label) * rate
    for vector in inputs[:train_inputs]:
        for dimension, weight in enumerate(old_output):
            vector[dimension] -= delta * weight / divisor
    if train_output:
        for dimension, value in enumerate(hidden):
            output[dimension] -= delta * value


def _noise_cumulative(counts: tuple[int, ...]) -> tuple[float, ...]:
    values = [0.0]
    for count in counts:
        values.append(values[-1] + count**0.75)
    return tuple(values)


def _negative_targets(
    rng: Random, target: int, cumulative: tuple[float, ...], number: int
) -> tuple[int, ...]:
    # Remove the positive target's mass interval before inverse-CDF sampling.
    # This avoids an O(vocabulary) candidate allocation for every training pair.
    removed = cumulative[target + 1] - cumulative[target]
    available = cumulative[-1] - removed
    samples = []
    for _ in range(number):
        mass = rng.random() * available
        if mass >= cumulative[target]:
            mass += removed
        index = min(len(cumulative) - 2, bisect_right(cumulative, mass) - 1)
        if index == target:  # Floating-point endpoint rounding, never positive noise.
            index = target - 1 if target else 1
        samples.append(index)
    return tuple(samples)


def _positive_examples(documents, spec):
    for document, tokens in enumerate(documents):
        for position, target in enumerate(tokens):
            if target is None:
                continue
            context = tuple(
                tokens[index]
                for index in range(
                    max(0, position - spec.window),
                    min(len(tokens), position + spec.window + 1),
                )
                if index != position and tokens[index] is not None
            )
            if spec.method == "skipgram":
                for neighbour in context:
                    yield document, (target,), neighbour
            elif spec.method == "cbow":
                if context:
                    yield document, context, target
            elif spec.method == "pv_dbow":
                yield document, (), target
            else:
                yield document, context, target


def _inputs(example, method, words, documents):
    document, context, _ = example
    vectors = [words[token] for token in context]
    return [documents[document], *vectors] if method.startswith("pv_") else vectors


def _objective(examples, method, words, outputs, documents):
    total = 0.0
    terms = 0
    for example, negatives in examples:
        vectors = _inputs(example, method, words, documents)
        hidden = [
            sum(vector[d] for vector in vectors) / len(vectors)
            for d in range(len(outputs[0]))
        ]
        for target, label in ((example[2], 1), *((target, 0) for target in negatives)):
            total += _logistic_loss(
                sum(a * b for a, b in zip(hidden, outputs[target])), label
            )
            terms += 1
    return total / terms


def _train_epoch(examples, method, words, outputs, documents, rate, *, infer=False):
    for example, negatives in examples:
        vectors = _inputs(example, method, words, documents)
        for target, label in ((example[2], 1), *((target, 0) for target in negatives)):
            _step(
                vectors,
                outputs[target],
                label,
                rate,
                train_output=not infer,
                train_inputs=1 if infer else None,
            )


def _documents(log: CaseLog, spec: CaseTraceSpec):
    projected = case_traces(log, spec)
    if projected.status is not ComputeStatus.COMPUTED:
        raise ValueError("; ".join(issue.message for issue in projected.issues))
    mapping = {
        trace.object_id: tuple(event.activity for event in trace.events)
        for trace in projected.value.traces
    }
    return tuple((trace.id, mapping[trace.id]) for trace in log.traces)


def _answer(operator, source, request, value, issues=(), status=None):
    return _result(
        operator,
        None,
        request,
        status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        tuple(issues),
        source_digest=source,
    )


def fit_embeddings(
    log: CaseLog,
    spec: EmbeddingSpec = EmbeddingSpec(),
    *,
    training_case_ids: tuple[str, ...] | None = None,
) -> ComputationResult[EmbeddingModel]:
    """Train selected cases only; report initial/per-epoch sampled objective loss.

    A resource limit returns UNAVAILABLE without a truncated training model.
    Loss is a diagnostic for this sampled objective, not prediction accuracy or a
    convergence guarantee. Trace IDs are identifiers, never predictive inputs.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    request = EmbeddingFitRequest(spec, training_case_ids)
    source = case_log_digest(log)
    operator = "pix.case_centric.fit_embeddings"
    try:
        ids = (
            set(training_case_ids)
            if training_case_ids is not None
            else {trace.id for trace in log.traces}
        )
        if ids - {trace.id for trace in log.traces}:
            raise ValueError("training selection contains unknown case IDs")
        training = replace(
            log,
            traces=tuple(
                sorted(
                    (trace for trace in log.traces if trace.id in ids),
                    key=lambda trace: trace.id,
                )
            ),
        )
        rows = _documents(training, spec.trace_spec)
        frequency = Counter(token for _, tokens in rows for token in tokens)
        vocabulary = tuple(
            sorted(
                token
                for token, count in frequency.items()
                if count >= spec.minimum_count
            )
        )
        if len(vocabulary) < 2:
            return _answer(
                operator,
                source,
                request,
                None,
                (
                    ComputeIssue(
                        "insufficient_embedding_vocabulary",
                        "Negative sampling requires at least two retained training tokens",
                    ),
                ),
                ComputeStatus.UNAVAILABLE,
            )
        indices = {token: index for index, token in enumerate(vocabulary)}
        # None retains omitted tokens' positions, preventing artificial adjacency.
        documents = tuple(
            tuple(indices.get(token) for token in tokens) for _, tokens in rows
        )
        counts = tuple(frequency[token] for token in vocabulary)
        cumulative = _noise_cumulative(counts)
        rng = Random(spec.seed)
        examples = []
        for example in _positive_examples(documents, spec):
            if len(examples) >= spec.max_training_examples:
                return _answer(
                    operator,
                    source,
                    request,
                    None,
                    (
                        ComputeIssue(
                            "embedding_training_limit",
                            "Positive training-example limit exceeded; no truncated model returned",
                        ),
                    ),
                    ComputeStatus.UNAVAILABLE,
                )
            examples.append(
                (
                    example,
                    _negative_targets(
                        rng, example[2], cumulative, spec.negative_samples
                    ),
                )
            )
        if not examples:
            return _answer(
                operator,
                source,
                request,
                None,
                (
                    ComputeIssue(
                        "no_embedding_contexts",
                        "No eligible contexts occur within the requested window",
                    ),
                ),
                ComputeStatus.UNAVAILABLE,
            )

        def initial():
            return [
                rng.uniform(-0.5 / spec.dimensions, 0.5 / spec.dimensions)
                for _ in range(spec.dimensions)
            ]

        words = [
            initial() if spec.method != "pv_dbow" else [0.0] * spec.dimensions
            for _ in vocabulary
        ]
        outputs = [[0.0] * spec.dimensions for _ in vocabulary]
        docs = (
            [
                initial()
                if any(token is not None for token in tokens)
                else [0.0] * spec.dimensions
                for tokens in documents
            ]
            if spec.method.startswith("pv_")
            else []
        )
        loss = [_objective(examples, spec.method, words, outputs, docs)]
        for _ in range(spec.epochs):
            _train_epoch(
                examples, spec.method, words, outputs, docs, spec.learning_rate
            )
            loss.append(_objective(examples, spec.method, words, outputs, docs))
            if not isfinite(loss[-1]):
                return _answer(
                    operator,
                    source,
                    request,
                    None,
                    (
                        ComputeIssue(
                            "embedding_numeric_failure",
                            "SGD objective became nonfinite; no trained model returned",
                        ),
                    ),
                    ComputeStatus.UNAVAILABLE,
                )
        facts = dict(
            parameters=asdict(spec),
            vocabulary=vocabulary,
            token_counts=counts,
            word_vectors=tuple(tuple(row) for row in words),
            output_vectors=tuple(tuple(row) for row in outputs),
            document_vectors=tuple(tuple(row) for row in docs),
            training_case_ids=tuple(trace.id for trace in training.traces),
            training_source_digest=case_log_digest(training),
            objective_examples=len(examples),
            loss_history=tuple(loss),
        )
        model = EmbeddingModel(
            **{**facts, "parameters": spec}, model_digest=_digest(facts)
        )
    except (ValueError, OverflowError) as error:
        return _answer(
            operator,
            source,
            request,
            None,
            (ComputeIssue("invalid_embedding_training_data", str(error)),),
            ComputeStatus.INVALID_INPUT,
        )
    return _answer(operator, source, request, model)


def transform_embeddings(
    log: CaseLog,
    fitted_model: EmbeddingModel,
    *,
    aggregation: Literal["mean", "sum"] = "mean",
    inference_epochs: int = 30,
    inference_learning_rate: float = 0.025,
) -> ComputationResult[EmbeddingMatrix]:
    """Pool fixed Word2Vec weights or infer Doc2Vec against frozen model weights.

    OOV tokens are ignored with explicit counts and PARTIAL status. Empty/all-OOV
    rows use the documented zero-vector convention; no semantic value is inferred
    from an unknown token. PV inference randomness depends on ordered tokens and
    model identity, never input batch position, case identifier, or earlier calls.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    request = EmbeddingTransformRequest(
        fitted_model, aggregation, inference_epochs, inference_learning_rate
    )
    source = case_log_digest(log)
    spec = fitted_model.parameters
    operator = "pix.case_centric.transform_embeddings"
    try:
        input_rows = _documents(log, spec.trace_spec)
    except ValueError as error:
        return _answer(
            operator,
            source,
            request,
            None,
            (ComputeIssue("invalid_embedding_input", str(error)),),
            ComputeStatus.INVALID_INPUT,
        )
    indices = {token: index for index, token in enumerate(fitted_model.vocabulary)}
    cumulative = _noise_cumulative(fitted_model.token_counts)
    rows, issues = [], []
    for case_id, tokens in input_rows:
        positions = tuple(indices.get(token) for token in tokens)
        known = tuple(index for index in positions if index is not None)
        unknown = len(tokens) - len(known)
        if unknown:
            issues.append(
                ComputeIssue(
                    "embedding_out_of_vocabulary",
                    f"{unknown} tokens omitted; training vocabulary remains fixed",
                    (case_id,),
                )
            )
        loss = ()
        if not known:
            vector = (0.0,) * spec.dimensions
        elif not spec.method.startswith("pv_"):
            divisor = len(known) if aggregation == "mean" else 1
            vector = tuple(
                sum(fitted_model.word_vectors[index][dimension] for index in known)
                / divisor
                for dimension in range(spec.dimensions)
            )
        else:
            raw_seed = json.dumps(
                (spec.seed, fitted_model.model_digest, positions),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            rng = Random(int.from_bytes(sha256(raw_seed).digest(), "big"))
            examples = []
            for example in _positive_examples((positions,), spec):
                if len(examples) >= spec.max_training_examples:
                    return _answer(
                        operator,
                        source,
                        request,
                        None,
                        (
                            ComputeIssue(
                                "embedding_inference_limit",
                                "Document inference example limit exceeded",
                                (case_id,),
                            ),
                        ),
                        ComputeStatus.UNAVAILABLE,
                    )
                examples.append(
                    (
                        example,
                        _negative_targets(
                            rng, example[2], cumulative, spec.negative_samples
                        ),
                    )
                )
            words = [list(row) for row in fitted_model.word_vectors]
            outputs = [list(row) for row in fitted_model.output_vectors]
            docs = [
                [
                    rng.uniform(-0.5 / spec.dimensions, 0.5 / spec.dimensions)
                    for _ in range(spec.dimensions)
                ]
            ]
            losses = [_objective(examples, spec.method, words, outputs, docs)]
            for _ in range(inference_epochs):
                _train_epoch(
                    examples,
                    spec.method,
                    words,
                    outputs,
                    docs,
                    inference_learning_rate,
                    infer=True,
                )
                losses.append(_objective(examples, spec.method, words, outputs, docs))
                if not isfinite(losses[-1]):
                    return _answer(
                        operator,
                        source,
                        request,
                        None,
                        (
                            ComputeIssue(
                                "embedding_numeric_failure",
                                "Document inference became nonfinite; no embedding returned",
                                (case_id,),
                            ),
                        ),
                        ComputeStatus.UNAVAILABLE,
                    )
            loss, vector = tuple(losses), tuple(docs[0])
        rows.append(EmbeddingRow(case_id, vector, len(known), unknown, loss))
    return _answer(
        operator,
        source,
        request,
        EmbeddingMatrix(
            spec.dimensions, tuple(rows), fitted_model.model_digest, spec.method
        ),
        issues,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.fit_embeddings": (
        "case-embedding-model",
        EmbeddingFitRequest,
        EmbeddingModel,
    ),
    "pix.case_centric.transform_embeddings": (
        "case-embedding-matrix",
        EmbeddingTransformRequest,
        EmbeddingMatrix,
    ),
}

__all__ = [
    "EmbeddingSpec",
    "EmbeddingFitRequest",
    "EmbeddingModel",
    "EmbeddingTransformRequest",
    "EmbeddingRow",
    "EmbeddingMatrix",
    "fit_embeddings",
    "transform_embeddings",
]
