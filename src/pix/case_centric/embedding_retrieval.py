"""Exact, finite vector retrieval with fixed encoder and source provenance.

This operator never fits an encoder or substitutes edit distance for embeddings.
Native learned, fixed feature and local-transformer results can be adapted; other
encoders provide explicitly labelled vectors and declared training provenance.
Cosine/dot are descending similarities; Euclidean is an ascending distance.
Boundary ties mean equal computed scores, with no hidden tolerance. Empty or
all-OOV vectors have undefined cosine and invalidate the whole request. Zero
vectors remain legitimate for dot/Euclidean. No approximate index is implied.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from math import dist, fsum, hypot, isfinite
from sys import float_info
from typing import ClassVar, Literal

from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _strings(value, name):
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in value:
        _text(item, name)
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must be unique")


def _hash(value):
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "pix.embedding-retrieval.v1:sha256:" + sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingTrainingProvenance:
    """Declared training boundary, not proof against upstream leakage."""

    kind: Literal["pix_fit", "external_declared", "unknown"]
    source_digest: str | None = None
    case_ids: tuple[str, ...] = ()

    def __post_init__(self):
        if self.kind not in ("pix_fit", "external_declared", "unknown"):
            raise ValueError("unknown training provenance kind")
        _strings(self.case_ids, "training case_ids")
        if self.source_digest is not None:
            _text(self.source_digest, "training source_digest")
        if self.kind == "unknown" and (self.source_digest is not None or self.case_ids):
            raise ValueError("unknown training provenance cannot assert training facts")
        if self.kind != "unknown" and self.source_digest is None:
            raise ValueError("declared training provenance needs a source identity")


@dataclass(frozen=True, slots=True)
class EmbeddingSpace:
    encoder_id: str
    model_digest: str
    dimension_labels: tuple[str, ...]
    transform_digest: str
    training: EmbeddingTrainingProvenance
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("encoder_id", "model_digest", "transform_digest"):
            _text(getattr(self, name), name)
        _strings(self.dimension_labels, "dimension_labels")
        if not self.dimension_labels:
            raise ValueError("at least one labelled embedding dimension is required")
        if not isinstance(self.training, EmbeddingTrainingProvenance):
            raise TypeError("training must be EmbeddingTrainingProvenance")


@dataclass(frozen=True, slots=True)
class RetrievalEmbeddingRow:
    case_id: str
    values: tuple[float, ...]
    known_tokens: int | None = None
    unknown_tokens: int | None = None
    token_count: int | None = None
    truncated: bool = False
    text_sha256: str | None = None

    def __post_init__(self):
        _text(self.case_id, "case_id")
        if not isinstance(self.values, tuple) or any(
            type(x) is not float or not isfinite(x) for x in self.values
        ):
            raise ValueError("embedding values must be finite floats in a tuple")
        for name in ("known_tokens", "unknown_tokens", "token_count"):
            if getattr(self, name) is not None:
                _integer(getattr(self, name), name)
        if all(
            value is not None
            for value in (self.known_tokens, self.unknown_tokens, self.token_count)
        ):
            if self.known_tokens + self.unknown_tokens != self.token_count:
                raise ValueError("token total differs from known plus unknown counts")
        if type(self.truncated) is not bool:
            raise TypeError("truncated must be bool")
        if self.text_sha256 is not None:
            if (
                not isinstance(self.text_sha256, str)
                or len(self.text_sha256) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in self.text_sha256
                )
            ):
                raise ValueError("text_sha256 must be lowercase hexadecimal SHA-256")


@dataclass(frozen=True, slots=True)
class EmbeddingBatch:
    """External vector inputs must declare their encoder and coordinate identity."""

    space: EmbeddingSpace
    source_digest: str
    role: Literal["corpus", "query"]
    rows: tuple[RetrievalEmbeddingRow, ...]
    origin_computation_id: str | None = None
    issues: tuple[ComputeIssue, ...] = ()

    def __post_init__(self):
        if not isinstance(self.space, EmbeddingSpace):
            raise TypeError("space must be EmbeddingSpace")
        _text(self.source_digest, "source_digest")
        if self.role not in ("corpus", "query"):
            raise ValueError("role must be corpus or query")
        if not isinstance(self.rows, tuple) or any(
            not isinstance(row, RetrievalEmbeddingRow) for row in self.rows
        ):
            raise TypeError("rows must be a tuple of RetrievalEmbeddingRow")
        if len({row.case_id for row in self.rows}) != len(self.rows):
            raise ValueError("case identities must be unique within a batch")
        if any(
            len(row.values) != len(self.space.dimension_labels) for row in self.rows
        ):
            raise ValueError("row dimensions must match labelled embedding space")
        if self.origin_computation_id is not None:
            _text(self.origin_computation_id, "origin_computation_id")
        if not isinstance(self.issues, tuple) or any(
            not isinstance(issue, ComputeIssue) for issue in self.issues
        ):
            raise TypeError("issues must be immutable ComputeIssue records")


def as_embedding_batch(result: ComputationResult, *, role: Literal["corpus", "query"]):
    """Preserve a fixed PIX encoder's coordinate and training boundary.

    Only trace-level matrices are accepted: event vectors need an explicit case
    pooling profile. Partial OOV/truncation survives adaptation and retrieval
    rejects it unless allow_partial=True. Feature missing values are not imputed.
    Transformer training data are unknown even when checkpoint bytes are pinned.
    """
    from pix.case_centric.embeddings import EmbeddingMatrix, EmbeddingTransformRequest
    from pix.case_centric.features import FeatureMatrix, FeatureTransformRequest
    from pix.case_centric.transformer_embeddings import (
        TransformerEmbeddingMatrix,
        TransformerEmbeddingRequest,
    )

    if not isinstance(result, ComputationResult):
        raise TypeError("result must be a ComputationResult")
    if result.status not in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL):
        raise ValueError("embedding input must have a computed or partial matrix")
    if result.operator_version != "1.0.0":
        raise ValueError("unsupported encoder operator version")
    matrix, request = result.value, result.spec
    if isinstance(matrix, EmbeddingMatrix) and isinstance(
        request, EmbeddingTransformRequest
    ):
        if result.operator_id != "pix.case_centric.transform_embeddings":
            raise ValueError("learned matrix operator identity does not match")
        model = request.fitted_model
        if (
            matrix.model_digest != model.model_digest
            or matrix.method != model.parameters.method
            or matrix.dimensions != model.parameters.dimensions
        ):
            raise ValueError("matrix differs from its fixed embedding model")
        if result.status is ComputeStatus.COMPUTED and any(
            row.unknown_tokens for row in matrix.rows
        ):
            raise ValueError("omitted tokens require a partial encoder result")
        profile = {
            "method": matrix.method,
            "trace_spec": asdict(model.parameters.trace_spec),
        }
        if matrix.method.startswith("pv_"):
            profile.update(
                inference_epochs=request.inference_epochs,
                inference_learning_rate=request.inference_learning_rate,
            )
        else:
            profile["aggregation"] = request.aggregation
        space = EmbeddingSpace(
            "pix.learned-activity-embedding.v1",
            model.model_digest,
            tuple(f"latent:{i}" for i in range(matrix.dimensions)),
            _hash(profile),
            EmbeddingTrainingProvenance(
                "pix_fit", model.training_source_digest, model.training_case_ids
            ),
        )
        rows = tuple(
            RetrievalEmbeddingRow(
                row.case_id,
                row.values,
                row.known_tokens,
                row.unknown_tokens,
                row.known_tokens + row.unknown_tokens,
            )
            for row in matrix.rows
        )
    elif isinstance(matrix, TransformerEmbeddingMatrix) and isinstance(
        request, TransformerEmbeddingRequest
    ):
        if result.operator_id != "pix.case_centric.transformer_embeddings":
            raise ValueError("transformer matrix operator identity does not match")
        if matrix.level != "trace" or request.parameters.level != "trace":
            raise ValueError(
                "event embeddings require explicit case pooling before retrieval"
            )
        if matrix.checkpoint_sha256 != request.checkpoint_sha256:
            raise ValueError("matrix checkpoint differs from the recorded request")
        if {name for name, _ in request.backend_versions} != {
            "sentence-transformers",
            "transformers",
            "torch",
            "tokenizers",
        }:
            raise ValueError("transformer backend version provenance is incomplete")
        if any(row.truncated for row in matrix.rows) and (
            not request.parameters.allow_truncation
            or result.status is ComputeStatus.COMPUTED
        ):
            raise ValueError("truncation must be allowed and recorded as partial")
        profile = {
            "text_profile": matrix.text_profile,
            "maximum_tokens": matrix.maximum_tokens,
            "normalize": request.parameters.normalize,
            "trace_spec": asdict(request.parameters.trace_spec),
            "backend_versions": tuple(sorted(request.backend_versions)),
        }
        space = EmbeddingSpace(
            "pix.local-transformer-activity.v1",
            matrix.checkpoint_sha256,
            tuple(f"latent:{i}" for i in range(matrix.dimensions)),
            _hash(profile),
            EmbeddingTrainingProvenance("unknown"),
        )
        rows = tuple(
            RetrievalEmbeddingRow(
                row.case_id,
                row.values,
                token_count=row.token_count,
                truncated=row.truncated,
                text_sha256=row.text_sha256,
            )
            for row in matrix.rows
        )
    elif isinstance(matrix, FeatureMatrix) and isinstance(
        request, FeatureTransformRequest
    ):
        if result.operator_id != "pix.case_centric.transform_features":
            raise ValueError("feature matrix operator identity does not match")
        model = request.fitted_model
        if matrix.level != "trace" or model.parameters.level != "trace":
            raise ValueError(
                "event features require explicit case pooling before retrieval"
            )
        if matrix.model_digest != model.model_digest or matrix.columns != model.columns:
            raise ValueError("feature matrix differs from the fixed model schema")
        if any(value is None for row in matrix.rows for value in row.values):
            raise ValueError(
                "missing features must be explicitly resolved before retrieval"
            )
        if result.status is ComputeStatus.COMPUTED and any(
            row.unknown_term_count for row in matrix.rows
        ):
            raise ValueError("omitted feature terms require a partial encoder result")
        space = EmbeddingSpace(
            "pix.fixed-case-features.v1",
            model.model_digest,
            tuple(
                json.dumps(asdict(column), ensure_ascii=False, sort_keys=True)
                for column in matrix.columns
            ),
            _hash(asdict(model.parameters)),
            EmbeddingTrainingProvenance(
                "pix_fit", model.training_source_digest, model.training_case_ids
            ),
        )
        rows = tuple(
            RetrievalEmbeddingRow(
                row.case_id, row.values, unknown_tokens=row.unknown_term_count
            )
            for row in matrix.rows
        )
    else:
        raise TypeError(
            "unsupported encoder result; provide an explicit EmbeddingBatch"
        )
    expected = computation_identity(
        result.operator_id,
        result.operator_version,
        result.source_digest,
        result.spec,
        result.parent_computation_ids,
    )
    if result.computation_id != expected:
        raise ValueError("encoder computation identity does not match its request")
    return EmbeddingBatch(
        space, result.source_digest, role, rows, result.computation_id, result.issues
    )


@dataclass(frozen=True, slots=True)
class EmbeddingRetrievalSpec:
    k: int = 5
    metric: Literal["cosine", "dot", "euclidean"] = "cosine"
    include_boundary_ties: bool = True
    exclude_same_source_case: bool = False
    allow_partial: bool = False
    max_comparisons: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _integer(self.k, "k", 1)
        _integer(self.max_comparisons, "max_comparisons", 1)
        if self.metric not in ("cosine", "dot", "euclidean"):
            raise ValueError("unknown vector retrieval metric")
        for name in (
            "include_boundary_ties",
            "exclude_same_source_case",
            "allow_partial",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class EmbeddingRetrievalRequest:
    parameters: EmbeddingRetrievalSpec
    corpus_space: EmbeddingSpace
    query_space: EmbeddingSpace
    corpus_source_digest: str
    query_source_digest: str
    corpus_content_digest: str
    query_content_digest: str
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.parameters, EmbeddingRetrievalSpec):
            raise TypeError("parameters must be EmbeddingRetrievalSpec")
        for name in ("corpus_space", "query_space"):
            if not isinstance(getattr(self, name), EmbeddingSpace):
                raise TypeError(f"{name} must be EmbeddingSpace")
        for name in (
            "corpus_source_digest",
            "query_source_digest",
            "corpus_content_digest",
            "query_content_digest",
        ):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class EmbeddingNeighbor:
    rank: int
    case_id: str
    score: float
    vector: RetrievalEmbeddingRow

    def __post_init__(self):
        _integer(self.rank, "rank", 1)
        _text(self.case_id, "case_id")
        if type(self.score) is not float or not isfinite(self.score):
            raise ValueError("neighbor score must be a finite float")
        if (
            not isinstance(self.vector, RetrievalEmbeddingRow)
            or self.vector.case_id != self.case_id
        ):
            raise ValueError("neighbor vector identity differs")


@dataclass(frozen=True, slots=True)
class EmbeddingQueryNeighbors:
    query: RetrievalEmbeddingRow
    eligible_count: int
    neighbors: tuple[EmbeddingNeighbor, ...]

    def __post_init__(self):
        if not isinstance(self.query, RetrievalEmbeddingRow):
            raise TypeError("query must be RetrievalEmbeddingRow")
        _integer(self.eligible_count, "eligible_count")
        if not isinstance(self.neighbors, tuple) or any(
            not isinstance(x, EmbeddingNeighbor) for x in self.neighbors
        ):
            raise TypeError("neighbors must be immutable EmbeddingNeighbor records")
        if len(self.neighbors) > self.eligible_count or len(
            {x.case_id for x in self.neighbors}
        ) != len(self.neighbors):
            raise ValueError(
                "neighbor identities/count differ from eligible population"
            )
        previous, expected_rank = None, 0
        for index, neighbor in enumerate(self.neighbors, 1):
            if previous is None or neighbor.score != previous:
                expected_rank = index
            if neighbor.rank != expected_rank:
                raise ValueError("neighbor competition rank differs from score ties")
            previous = neighbor.score


@dataclass(frozen=True, slots=True)
class EmbeddingRetrieval:
    space: EmbeddingSpace
    metric: Literal["cosine", "dot", "euclidean"]
    corpus_source_digest: str
    query_source_digest: str
    corpus_count: int
    query_count: int
    comparison_count: int
    queries: tuple[EmbeddingQueryNeighbors, ...]

    def __post_init__(self):
        if not isinstance(self.space, EmbeddingSpace):
            raise TypeError("space must be EmbeddingSpace")
        if self.metric not in ("cosine", "dot", "euclidean"):
            raise ValueError("unknown retrieval metric")
        for name in ("corpus_source_digest", "query_source_digest"):
            _text(getattr(self, name), name)
        for name in ("corpus_count", "query_count", "comparison_count"):
            _integer(getattr(self, name), name)
        if not isinstance(self.queries, tuple) or any(
            not isinstance(x, EmbeddingQueryNeighbors) for x in self.queries
        ):
            raise TypeError("queries must be immutable EmbeddingQueryNeighbors records")
        if (
            self.query_count != len(self.queries)
            or len({x.query.case_id for x in self.queries}) != self.query_count
        ):
            raise ValueError("query identities/count differ")
        if any(x.eligible_count > self.corpus_count for x in self.queries):
            raise ValueError("eligible count exceeds corpus")
        if self.comparison_count != sum(x.eligible_count for x in self.queries):
            raise ValueError("comparison count differs from eligible population")
        width = len(self.space.dimension_labels)
        for row in self.queries:
            if len(row.query.values) != width or any(
                len(item.vector.values) != width for item in row.neighbors
            ):
                raise ValueError(
                    "retrieval vector width differs from coordinate labels"
                )
            if self.metric == "cosine" and any(
                not -1 <= item.score <= 1 for item in row.neighbors
            ):
                raise ValueError("cosine scores must be between -1 and 1")
            if self.metric == "cosine" and any(
                not any(vector.values)
                for vector in (row.query, *(item.vector for item in row.neighbors))
            ):
                raise ValueError("cosine payload cannot retain a zero-norm vector")
            if self.metric == "euclidean" and any(
                item.score < 0 for item in row.neighbors
            ):
                raise ValueError("Euclidean distances must be nonnegative")
            keys = tuple(
                (
                    item.score if self.metric == "euclidean" else -item.score,
                    item.case_id,
                )
                for item in row.neighbors
            )
            if keys != tuple(sorted(keys)):
                raise ValueError("neighbors are not ordered by score and case identity")


def validate_embedding_retrieval_result(result: ComputationResult) -> None:
    """Validate redundant envelope facts without recomputing vector scores.

    This explicit known-operator hook is used by PIX result persistence. Content
    hashes identify the full inputs; top-k completeness cannot be independently
    re-proved from a payload containing only selected neighbors.
    """
    request, value = result.spec, result.value
    if not isinstance(request, EmbeddingRetrievalRequest):
        raise TypeError("retrieval request type differs")
    if result.source_digest != _hash(
        (request.corpus_content_digest, request.query_content_digest)
    ):
        raise ValueError("retrieval input digest differs from the request")
    if value is None:
        return
    if not isinstance(value, EmbeddingRetrieval):
        raise TypeError("retrieval payload type differs")
    if value.space != request.corpus_space or value.space != request.query_space:
        raise ValueError("retrieval request and payload spaces disagree")
    if (value.metric, value.corpus_source_digest, value.query_source_digest) != (
        request.parameters.metric,
        request.corpus_source_digest,
        request.query_source_digest,
    ):
        raise ValueError("retrieval request and payload metric/source disagree")
    spec = request.parameters
    if value.comparison_count > spec.max_comparisons:
        raise ValueError("retrieval population exceeds requested comparison cap")
    for row in value.queries:
        minimum = min(spec.k, row.eligible_count)
        if len(row.neighbors) < minimum:
            raise ValueError(
                "retrieval has fewer neighbors than requested and eligible"
            )
        if not spec.include_boundary_ties and len(row.neighbors) != minimum:
            raise ValueError("retrieval exceeds requested k without tie permission")
        if len(row.neighbors) > minimum and any(
            item.score != row.neighbors[minimum - 1].score
            for item in row.neighbors[minimum:]
        ):
            raise ValueError("retrieval extra neighbors are not boundary ties")
        if (
            spec.exclude_same_source_case
            and value.corpus_source_digest == value.query_source_digest
        ):
            if any(item.case_id == row.query.case_id for item in row.neighbors):
                raise ValueError("retrieval includes a prohibited self match")
    if result.status is ComputeStatus.PARTIAL and not spec.allow_partial:
        raise ValueError("partial retrieval needs explicit request permission")
    if result.status is ComputeStatus.COMPUTED and result.issues:
        raise ValueError("retrieval issues require partial status")
    incomplete_rows = any(
        vector.unknown_tokens or vector.truncated
        for row in value.queries
        for vector in (row.query, *(item.vector for item in row.neighbors))
    )
    if incomplete_rows and result.status is not ComputeStatus.PARTIAL:
        raise ValueError(
            "retained omitted/truncated inputs require partial retrieval status"
        )


def _answer(request, source, parents, value=None, issues=(), status=None):
    operator = "pix.case_centric.retrieve_embedding_neighbors"
    status = status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED)
    result = ComputationResult(
        operator,
        "1.0.0",
        source,
        request,
        status,
        value,
        issues,
        computation_identity(operator, "1.0.0", source, request, parents),
        parents,
    )
    validate_embedding_retrieval_result(result)
    return result


def _unit(vector):
    scale = max(abs(x) for x in vector)
    if scale == 0:
        raise ValueError("zero-norm vector has undefined cosine similarity")
    scaled = tuple(x / scale for x in vector)
    norm = hypot(*scaled)
    return tuple(x / norm for x in scaled)


def _dot(first, second):
    products = tuple(a * b for a, b in zip(first, second))
    subnormal_products = any(
        a != 0 and b != 0 and abs(product) < float_info.min
        for a, b, product in zip(first, second, products)
    )
    if not subnormal_products and all(isfinite(x) for x in products):
        try:
            return fsum(products)
        except OverflowError:
            pass
    # Exact fallback avoids inf-inf and individually underflowed products whose
    # sum is still representable; convert only the final rational sum to float.
    return float(
        sum((Fraction(a) * Fraction(b) for a, b in zip(first, second)), Fraction())
    )


def retrieve_embedding_neighbors(
    corpus: EmbeddingBatch | ComputationResult,
    queries: EmbeddingBatch | ComputationResult,
    spec: EmbeddingRetrievalSpec = EmbeddingRetrievalSpec(),
) -> ComputationResult[EmbeddingRetrieval]:
    """Compare every eligible vector; fit/query information never enters training.

    Identity exclusion applies only to an equal (source digest, case ID) pair.
    Different logs can legitimately reuse case IDs. Tied scores share competition
    rank (1, 1, 3); a k-boundary tie may return more than k neighbors. The cap
    counts actually eligible pairs, not skipped self matches.
    """
    if not isinstance(spec, EmbeddingRetrievalSpec):
        raise TypeError("spec must be EmbeddingRetrievalSpec")
    corpus = (
        as_embedding_batch(corpus, role="corpus")
        if isinstance(corpus, ComputationResult)
        else corpus
    )
    queries = (
        as_embedding_batch(queries, role="query")
        if isinstance(queries, ComputationResult)
        else queries
    )
    if not isinstance(corpus, EmbeddingBatch) or not isinstance(
        queries, EmbeddingBatch
    ):
        raise TypeError(
            "corpus and queries must be EmbeddingBatch or supported encoder results"
        )
    if corpus.role != "corpus" or queries.role != "query":
        raise ValueError("corpus/query provenance roles do not match operands")
    corpus_digest, query_digest = _hash(asdict(corpus)), _hash(asdict(queries))
    request = EmbeddingRetrievalRequest(
        spec,
        corpus.space,
        queries.space,
        corpus.source_digest,
        queries.source_digest,
        corpus_digest,
        query_digest,
    )
    source = _hash((corpus_digest, query_digest))
    parents = tuple(
        dict.fromkeys(
            x
            for x in (corpus.origin_computation_id, queries.origin_computation_id)
            if x
        )
    )

    def failure(code, message, *, status=ComputeStatus.INVALID_INPUT, at=()):
        return _answer(
            request,
            source,
            parents,
            issues=(ComputeIssue(code, message, at),),
            status=status,
        )

    if corpus.space != queries.space:
        return failure(
            "embedding_space_mismatch",
            "Encoder, model, dimension labels, transform or training provenance differs",
        )
    issues = []
    for batch in (corpus, queries):
        issues.extend(
            ComputeIssue(issue.code, issue.message, (batch.role,) + issue.at)
            for issue in batch.issues
        )
        for row in batch.rows:
            if row.unknown_tokens:
                issues.append(
                    ComputeIssue(
                        "retrieval_omitted_tokens",
                        f"{row.unknown_tokens} tokens/features were omitted by the fixed encoder",
                        (batch.role, row.case_id),
                    )
                )
            if row.truncated:
                issues.append(
                    ComputeIssue(
                        "retrieval_truncated_input",
                        "Input was truncated by the fixed encoder",
                        (batch.role, row.case_id),
                    )
                )
    if issues and not spec.allow_partial:
        return _answer(
            request,
            source,
            parents,
            issues=tuple(issues),
            status=ComputeStatus.INVALID_INPUT,
        )
    same_source = corpus.source_digest == queries.source_digest
    corpus_ids = {row.case_id for row in corpus.rows}
    comparisons = len(corpus.rows) * len(queries.rows)
    if spec.exclude_same_source_case and same_source:
        comparisons -= sum(row.case_id in corpus_ids for row in queries.rows)
    if comparisons > spec.max_comparisons:
        return failure(
            "embedding_retrieval_limit",
            f"{comparisons} eligible comparisons exceed max_comparisons={spec.max_comparisons}",
            status=ComputeStatus.UNAVAILABLE,
        )
    normalized = {}
    if spec.metric == "cosine":
        for batch in (corpus, queries):
            for row in batch.rows:
                try:
                    normalized[(batch.role, row.case_id)] = _unit(row.values)
                except ValueError as error:
                    return failure(
                        "embedding_zero_norm", str(error), at=(batch.role, row.case_id)
                    )
    results = []
    try:
        for query in queries.rows:
            scored = []
            for candidate in corpus.rows:
                if (
                    spec.exclude_same_source_case
                    and same_source
                    and candidate.case_id == query.case_id
                ):
                    continue
                if spec.metric == "cosine":
                    score = max(
                        -1.0,
                        min(
                            1.0,
                            fsum(
                                a * b
                                for a, b in zip(
                                    normalized[("query", query.case_id)],
                                    normalized[("corpus", candidate.case_id)],
                                )
                            ),
                        ),
                    )
                elif spec.metric == "dot":
                    score = _dot(query.values, candidate.values)
                else:
                    score = dist(query.values, candidate.values)
                if not isfinite(score):
                    raise OverflowError(
                        "vector score is not representable as a finite float"
                    )
                scored.append((score, candidate))
            scored.sort(
                key=lambda item: (
                    (item[0] if spec.metric == "euclidean" else -item[0]),
                    item[1].case_id,
                )
            )
            selected = scored[: spec.k]
            if spec.include_boundary_ties and selected:
                selected.extend(
                    item for item in scored[spec.k :] if item[0] == selected[-1][0]
                )
            neighbors, rank, previous = [], 0, None
            for index, (score, candidate) in enumerate(selected, 1):
                if previous is None or score != previous:
                    rank = index
                neighbors.append(
                    EmbeddingNeighbor(rank, candidate.case_id, score, candidate)
                )
                previous = score
            results.append(
                EmbeddingQueryNeighbors(query, len(scored), tuple(neighbors))
            )
    except (ValueError, OverflowError) as error:
        return failure(
            "embedding_numeric_failure", str(error), status=ComputeStatus.UNAVAILABLE
        )
    value = EmbeddingRetrieval(
        corpus.space,
        spec.metric,
        corpus.source_digest,
        queries.source_digest,
        len(corpus.rows),
        len(queries.rows),
        comparisons,
        tuple(results),
    )
    return _answer(request, source, parents, value, tuple(issues))


RESULT_SCHEMAS = {
    "pix.case_centric.retrieve_embedding_neighbors": (
        "case-embedding-neighbors",
        EmbeddingRetrievalRequest,
        EmbeddingRetrieval,
    ),
}

__all__ = [
    "EmbeddingTrainingProvenance",
    "EmbeddingSpace",
    "RetrievalEmbeddingRow",
    "EmbeddingBatch",
    "EmbeddingRetrievalSpec",
    "EmbeddingRetrievalRequest",
    "EmbeddingNeighbor",
    "EmbeddingQueryNeighbors",
    "EmbeddingRetrieval",
    "as_embedding_batch",
    "retrieve_embedding_neighbors",
    "validate_embedding_retrieval_result",
]
