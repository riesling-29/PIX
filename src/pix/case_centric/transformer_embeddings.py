"""Offline transformer inference for source-ordered case and event text.

PIX prepares text and validates immutable results; the optional neural backend is
sentence-transformers, never PM4Py/OCPA. A caller must provide a complete local
checkpoint. No model is downloaded, fitted, or replaced by synthetic vectors.
The checkpoint determines whether the architecture is BERT or another encoder.
This activity-only JSON text profile is distinct from PM4Py's space-joined text.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
from math import isfinite
from numbers import Real
from pathlib import Path
from typing import ClassVar, Literal

from pix.compute._common import _result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest, case_traces


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _digest(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{name} must be a lowercase hexadecimal SHA-256")


@dataclass(frozen=True, slots=True)
class TransformerEmbeddingSpec:
    local_checkpoint: str
    level: Literal["trace", "event"] = "trace"
    batch_size: int = 32
    normalize: bool = False
    allow_truncation: bool = False
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _text(self.local_checkpoint, "local_checkpoint")
        if self.level not in ("trace", "event"):
            raise ValueError("level must be trace or event")
        if type(self.batch_size) is not int or self.batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        if type(self.normalize) is not bool or type(self.allow_truncation) is not bool:
            raise TypeError("normalize and allow_truncation must be bool")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class TransformerEmbeddingRequest:
    parameters: TransformerEmbeddingSpec
    checkpoint_sha256: str | None = None
    backend_versions: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, TransformerEmbeddingSpec):
            raise TypeError("parameters must be TransformerEmbeddingSpec")
        if self.checkpoint_sha256 is not None:
            _digest(self.checkpoint_sha256, "checkpoint_sha256")
        if not isinstance(self.backend_versions, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or any(not isinstance(x, str) or not x for x in pair)
            for pair in self.backend_versions
        ):
            raise TypeError(
                "backend_versions must contain immutable package/version pairs"
            )
        if len({name for name, _ in self.backend_versions}) != len(
            self.backend_versions
        ):
            raise ValueError("backend version package names must be unique")


@dataclass(frozen=True, slots=True)
class TransformerEmbeddingRow:
    case_id: str
    event_id: str | None
    text_sha256: str
    token_count: int
    truncated: bool
    values: tuple[float, ...]

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        if self.event_id is not None:
            _text(self.event_id, "event_id")
        _digest(self.text_sha256, "text_sha256")
        if type(self.token_count) is not int or self.token_count < 0:
            raise ValueError("token_count must be a nonnegative integer")
        if type(self.truncated) is not bool:
            raise TypeError("truncated must be bool")
        if not isinstance(self.values, tuple) or any(
            type(x) is not float or not isfinite(x) for x in self.values
        ):
            raise ValueError("embedding values must be immutable finite floats")


@dataclass(frozen=True, slots=True)
class TransformerEmbeddingMatrix:
    level: Literal["trace", "event"]
    dimensions: int
    rows: tuple[TransformerEmbeddingRow, ...]
    checkpoint_sha256: str
    maximum_tokens: int
    text_profile: str = "pix.activity-json.v1"

    def __post_init__(self) -> None:
        if self.level not in ("trace", "event"):
            raise ValueError("level must be trace or event")
        for name in ("dimensions", "maximum_tokens"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        _digest(self.checkpoint_sha256, "checkpoint_sha256")
        if self.text_profile != "pix.activity-json.v1":
            raise ValueError("unsupported text profile")
        if not isinstance(self.rows, tuple) or not all(
            isinstance(row, TransformerEmbeddingRow) for row in self.rows
        ):
            raise TypeError("rows must be a tuple of TransformerEmbeddingRow")
        if any(len(row.values) != self.dimensions for row in self.rows):
            raise ValueError("embedding row width differs from dimensions")
        if any((row.event_id is None) != (self.level == "trace") for row in self.rows):
            raise ValueError("row identity differs from matrix level")
        if len({(row.case_id, row.event_id) for row in self.rows}) != len(self.rows):
            raise ValueError("embedding row identities must be unique")
        if any(
            row.truncated != (row.token_count > self.maximum_tokens)
            for row in self.rows
        ):
            raise ValueError("truncation flag differs from recorded token count")


def _checkpoint_digest(directory: Path) -> str:
    """Cover every local file, including tokenizer, configuration, and weights.

    Symlinks/junction escapes are rejected: unhashed external resources would
    otherwise invalidate inference provenance. File contents are streamed.
    """
    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("local checkpoint must be a directory")
    files = []
    for path in root.rglob("*"):
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(
                "checkpoint may not contain symlinks or external junction targets"
            )
        if path.is_file():
            file_name = path.name.casefold()
            if file_name == "adapter_config.json":
                raise ValueError(
                    "PEFT adapters may load an unhashed external base model; "
                    "provide a complete merged checkpoint instead"
                )
            if file_name.startswith("sentence_") and file_name.endswith("_config.json"):
                settings = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(settings, dict) or set(settings) - {
                    "max_seq_length",
                    "do_lower_case",
                }:
                    raise ValueError(
                        "unsupported Transformer settings may refer to unhashed external resources"
                    )
            if file_name == "config_sentence_transformers.json":
                settings = json.loads(path.read_text(encoding="utf-8"))
                if (
                    not isinstance(settings, dict)
                    or settings.get("model_type", "SentenceTransformer")
                    != "SentenceTransformer"
                ):
                    raise ValueError(
                        "checkpoint model_type must be SentenceTransformer"
                    )
            digest = sha256()
            with path.open("rb") as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            files.append((path.relative_to(root).as_posix(), digest.hexdigest()))
    if not files:
        raise ValueError("local checkpoint directory is empty")
    # An actual SentenceTransformer export is required, avoiding fallback model
    # construction with inferred pooling or network model identifiers.
    manifest_path = root / "modules.json"
    if not manifest_path.is_file():
        raise ValueError(
            "checkpoint must be a saved SentenceTransformer with modules.json"
        )
    modules = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(modules, list) or not modules:
        raise ValueError("checkpoint modules.json must contain module definitions")
    for module in modules:
        if not isinstance(module, dict) or not isinstance(module.get("path"), str):
            raise ValueError("invalid checkpoint module path")
        if not (root / module["path"]).resolve().is_relative_to(root):
            raise ValueError("checkpoint module path escapes checkpoint directory")
        # Keep optional inference restricted to packaged standard modules.
        if module.get("type") not in (
            "sentence_transformers.models.Transformer",
            "sentence_transformers.models.Pooling",
            "sentence_transformers.models.Dense",
            "sentence_transformers.models.Normalize",
        ):
            raise ValueError("checkpoint uses an unsupported custom module")
    encoded = json.dumps(
        sorted(files), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _versions() -> tuple[tuple[str, str], ...]:
    return tuple(
        (name, version(name))
        for name in ("sentence-transformers", "transformers", "torch", "tokenizers")
    )


def _load_backend(path: Path):
    from sentence_transformers import SentenceTransformer

    _validate_weights(path)
    return SentenceTransformer(
        str(path),
        device="cpu",
        local_files_only=True,
        trust_remote_code=False,
        backend="torch",
    )


def _validate_weights(path: Path) -> None:
    """Reject freshly initialized missing weights before producing any vectors.

    Transformers ordinarily warns and initializes missing parameters. Its load
    diagnostics distinguish such cases from harmless unused checkpoint keys.
    A strict preflight entails an additional CPU weight load; the optional
    integration intentionally trades load time for explicit completeness.
    """
    from transformers import AutoModel

    modules = json.loads((path / "modules.json").read_text(encoding="utf-8"))
    transformer_paths = [
        path / module["path"]
        for module in modules
        if module["type"] == "sentence_transformers.models.Transformer"
    ]
    if not transformer_paths:
        raise ValueError("checkpoint must contain a standard Transformer module")
    for model_path in transformer_paths:
        loaded, diagnostics = AutoModel.from_pretrained(
            str(model_path),
            local_files_only=True,
            trust_remote_code=False,
            output_loading_info=True,
        )
        del loaded
        required = ("missing_keys", "mismatched_keys", "error_msgs")
        if not isinstance(diagnostics, dict) or any(
            key not in diagnostics for key in required
        ):
            raise ValueError(
                "backend did not provide strict checkpoint loading diagnostics"
            )
        if any(diagnostics[key] for key in required):
            raise ValueError(
                "checkpoint has missing/mismatched weights or loading errors"
            )


def transformer_embeddings(
    log: CaseLog,
    spec: TransformerEmbeddingSpec,
) -> ComputationResult[TransformerEmbeddingMatrix]:
    """Infer one vector per case or event using a caller-provided checkpoint.

    Text is a compact JSON activity array (case) or JSON activity string (event),
    with classifier and source order inherited from CaseTraceSpec. No attributes
    or future labels are added. Tokenization uses the checkpoint vocabulary;
    unseen activities neither train a vocabulary nor receive invented vectors.
    Explicitly allowed truncation yields PARTIAL and identifies affected rows.
    Model inference failures return UNAVAILABLE with no numeric replacement.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, TransformerEmbeddingSpec):
        raise TypeError("spec must be TransformerEmbeddingSpec")
    source = case_log_digest(log)
    request = TransformerEmbeddingRequest(spec)
    projected = case_traces(log, spec.trace_spec)
    parents = (
        (projected.computation_id,) if projected.computation_id is not None else ()
    )

    def finish(status, value=None, issues=()):
        return _result(
            "pix.case_centric.transformer_embeddings",
            None,
            request,
            status,
            value,
            tuple(issues),
            source_digest=source,
            parent_computation_ids=parents,
        )

    if projected.status is not ComputeStatus.COMPUTED:
        return finish(projected.status, issues=projected.issues)
    documents = []
    for trace in projected.value.traces:
        if spec.level == "trace":
            payload = [event.activity for event in trace.events]
            documents.append(
                (
                    trace.object_id,
                    None,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                )
            )
        else:
            for event in trace.events:
                documents.append(
                    (
                        trace.object_id,
                        event.event_id,
                        json.dumps(event.activity, ensure_ascii=False),
                    )
                )
    try:
        checkpoint = Path(spec.local_checkpoint).resolve(strict=True)
        checkpoint_digest = _checkpoint_digest(checkpoint)
        request = TransformerEmbeddingRequest(spec, checkpoint_digest)
    except (OSError, ValueError) as error:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("local_checkpoint_unavailable", str(error)),),
        )
    try:
        request = TransformerEmbeddingRequest(spec, checkpoint_digest, _versions())
        backend = _load_backend(checkpoint)
    except (ImportError, PackageNotFoundError) as error:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("transformer_dependency_unavailable", str(error)),),
        )
    except Exception as error:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("transformer_checkpoint_load_failed", str(error)),),
        )
    try:
        maximum = backend.max_seq_length
        dimensions = backend.get_sentence_embedding_dimension()
        if (
            type(maximum) is not int
            or maximum < 1
            or type(dimensions) is not int
            or dimensions < 1
        ):
            raise ValueError(
                "backend must report positive integer token limit and vector width"
            )
        tokenizer = backend.tokenizer
        lower_case = backend._first_module().do_lower_case
        if type(lower_case) is not bool:
            raise ValueError("unsupported transformer text preprocessing")
        counts = []
        for _, _, sentence in documents:
            token_text = sentence.strip()
            if lower_case:
                token_text = token_text.lower()
            tokens = tokenizer(
                token_text, add_special_tokens=True, truncation=False, padding=False
            )["input_ids"]
            if not isinstance(tokens, (tuple, list)) or not all(
                type(token) is int for token in tokens
            ):
                raise ValueError(
                    "backend tokenizer must return one integer token sequence"
                )
            counts.append(len(tokens))
        issues = tuple(
            ComputeIssue(
                "transformer_text_truncated",
                f"{count} tokens exceed checkpoint limit {maximum}",
                (case_id,) if event_id is None else (case_id, event_id),
            )
            for (case_id, event_id, _), count in zip(documents, counts)
            if count > maximum
        )
        if issues and not spec.allow_truncation:
            return finish(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "transformer_text_too_long",
                        "Truncation is disabled; no embeddings were computed",
                    ),
                    *issues,
                ),
            )
        backend.eval()
        vectors = (
            backend.encode(
                [sentence for _, _, sentence in documents],
                batch_size=spec.batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=spec.normalize,
                precision="float32",
                prompt="",
            )
            if documents
            else []
        )
        if len(vectors) != len(documents):
            raise ValueError("backend returned a different number of rows")
        rows = []
        for (case_id, event_id, sentence), count, vector in zip(
            documents, counts, vectors
        ):
            if any(
                isinstance(value, bool) or not isinstance(value, Real)
                for value in vector
            ):
                raise ValueError("backend vector coordinates must be real numbers")
            values = tuple(float(value) for value in vector)
            if len(values) != dimensions:
                raise ValueError("backend returned an incorrect vector width")
            rows.append(
                TransformerEmbeddingRow(
                    case_id,
                    event_id,
                    sha256(sentence.encode("utf-8")).hexdigest(),
                    count,
                    count > maximum,
                    values,
                )
            )
        if _checkpoint_digest(checkpoint) != checkpoint_digest:
            return finish(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "transformer_checkpoint_changed",
                        "Checkpoint contents changed during inference; results discarded",
                    ),
                ),
            )
        matrix = TransformerEmbeddingMatrix(
            spec.level, dimensions, tuple(rows), checkpoint_digest, maximum
        )
        return finish(
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED, matrix, issues
        )
    except Exception as error:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("transformer_inference_failed", str(error)),),
        )


RESULT_SCHEMAS = {
    "pix.case_centric.transformer_embeddings": (
        "case-transformer-embeddings",
        TransformerEmbeddingRequest,
        TransformerEmbeddingMatrix,
    ),
}

__all__ = [
    "TransformerEmbeddingSpec",
    "TransformerEmbeddingRequest",
    "TransformerEmbeddingRow",
    "TransformerEmbeddingMatrix",
    "transformer_embeddings",
]
