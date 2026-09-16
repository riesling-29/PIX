"""Offline adapter-contract tests; fake outputs are not neural inference evidence."""

import json
import sys
from dataclasses import FrozenInstanceError, replace
from hashlib import sha256
from types import SimpleNamespace

import pytest

import pix.case_centric.transformer_embeddings as implementation
from pix.case_centric.transformer_embeddings import (
    TransformerEmbeddingMatrix,
    TransformerEmbeddingRequest,
    TransformerEmbeddingRow,
    TransformerEmbeddingSpec,
    transformer_embeddings,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log_fixture():
    def event(identity, label):
        return CaseEvent(identity, (CaseAttribute("concept:name", "string", label),))

    return CaseLog(
        (
            CaseTrace("z", (event("e2", "A B"), event("e1", "C"))),
            CaseTrace("a", (event("e3", "A"), event("e4", "B C"))),
            CaseTrace("empty", ()),
        )
    )


@pytest.fixture
def checkpoint(tmp_path):
    (tmp_path / "modules.json").write_text(
        json.dumps(
            [
                {
                    "idx": 0,
                    "name": "0",
                    "path": "",
                    "type": "sentence_transformers.models.Transformer",
                },
                {
                    "idx": 1,
                    "name": "1",
                    "path": "1_Pooling",
                    "type": "sentence_transformers.models.Pooling",
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "weights.safetensors").write_bytes(
        b"adapter-test-data-not-model-weights"
    )
    (tmp_path / "1_Pooling").mkdir()
    return tmp_path


class ContractBackend:
    max_seq_length = 1000

    def __init__(self):
        self.sentences = None
        self.options = None
        self.evaluating = False

    def get_sentence_embedding_dimension(self):
        return 2

    def _first_module(self):
        return SimpleNamespace(do_lower_case=False)

    def tokenizer(self, sentence, **options):
        assert options == {
            "add_special_tokens": True,
            "truncation": False,
            "padding": False,
        }
        return {"input_ids": [1] * (len(sentence) + 2)}

    def eval(self):
        self.evaluating = True

    def encode(self, sentences, **options):
        assert self.evaluating
        self.sentences = sentences
        self.options = options
        return [[float(i), -float(i)] for i in range(len(sentences))]


@pytest.fixture
def backend(monkeypatch):
    value = ContractBackend()
    monkeypatch.setattr(
        implementation, "_versions", lambda: (("adapter-test-double", "1"),)
    )
    monkeypatch.setattr(implementation, "_load_backend", lambda path: value)
    return value


def test_trace_grouping_source_order_and_collision_free_text(checkpoint, backend):
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.COMPUTED
    assert backend.sentences == ['["A B","C"]', '["A","B C"]', "[]"]
    assert [(row.case_id, row.event_id) for row in result.value.rows] == [
        ("z", None),
        ("a", None),
        ("empty", None),
    ]
    assert result.value.rows[0].text_sha256 == sha256(b'["A B","C"]').hexdigest()
    assert result.value.rows[0].values == (0.0, -0.0)
    assert backend.options == {
        "batch_size": 32,
        "show_progress_bar": False,
        "convert_to_numpy": True,
        "normalize_embeddings": False,
        "precision": "float32",
        "prompt": "",
    }
    assert result.spec.backend_versions == (("adapter-test-double", "1"),)
    with pytest.raises(FrozenInstanceError):
        result.value.rows[0].case_id = "changed"


def test_event_ids_and_unseen_text_are_passed_to_tokenizer_without_fitting(
    checkpoint, backend
):
    log = log_fixture()
    result = transformer_embeddings(
        log, TransformerEmbeddingSpec(str(checkpoint), level="event")
    )
    assert result.status is ComputeStatus.COMPUTED
    assert backend.sentences == ['"A B"', '"C"', '"A"', '"B C"']
    assert [(row.case_id, row.event_id) for row in result.value.rows] == [
        ("z", "e2"),
        ("z", "e1"),
        ("a", "e3"),
        ("a", "e4"),
    ]
    assert result.value.dimensions == 2
    assert not hasattr(backend, "fit")


def test_classifier_projection_is_used(checkpoint, backend):
    event = CaseEvent("e", (CaseAttribute("label", "string", "custom"),))
    log = CaseLog((CaseTrace("case", (event,)),))
    spec = TransformerEmbeddingSpec(
        str(checkpoint), trace_spec=CaseTraceSpec(activity_key="label")
    )
    assert transformer_embeddings(log, spec).status is ComputeStatus.COMPUTED
    assert backend.sentences == ['["custom"]']


def test_invalid_projection_does_not_load_backend(checkpoint, monkeypatch):
    def forbidden(path):
        pytest.fail("malformed projection must not load model")

    monkeypatch.setattr(implementation, "_load_backend", forbidden)
    log = CaseLog((CaseTrace("case", (CaseEvent("e"),)),))
    result = transformer_embeddings(log, TransformerEmbeddingSpec(str(checkpoint)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_missing_checkpoint_returns_unavailable_and_never_calls_loader(
    tmp_path, monkeypatch
):
    def forbidden(path):
        pytest.fail("missing local checkpoint must not trigger a model lookup")

    monkeypatch.setattr(implementation, "_load_backend", forbidden)
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(tmp_path / "missing"))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "local_checkpoint_unavailable"


def test_missing_dependency_has_no_synthetic_output(checkpoint, monkeypatch):
    def missing():
        raise implementation.PackageNotFoundError("sentence-transformers")

    monkeypatch.setattr(implementation, "_versions", missing)
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "transformer_dependency_unavailable"
    assert result.spec.checkpoint_sha256 is not None


def test_loader_only_uses_offline_constructor_options(tmp_path, monkeypatch):
    observed = []
    monkeypatch.setattr(implementation, "_validate_weights", lambda path: None)
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(
            SentenceTransformer=lambda *args, **kwargs: observed.append((args, kwargs))
        ),
    )
    implementation._load_backend(tmp_path)
    assert observed == [
        (
            (str(tmp_path),),
            {
                "device": "cpu",
                "local_files_only": True,
                "trust_remote_code": False,
                "backend": "torch",
            },
        )
    ]


def test_weights_and_tokenizer_contents_change_computation_identity(
    checkpoint, backend
):
    spec = TransformerEmbeddingSpec(str(checkpoint))
    first = transformer_embeddings(log_fixture(), spec)
    (checkpoint / "weights.safetensors").write_bytes(b"different-adapter-test-weights")
    second = transformer_embeddings(log_fixture(), spec)
    (checkpoint / "tokenizer.json").write_text("{}", encoding="utf-8")
    third = transformer_embeddings(log_fixture(), spec)
    assert len({r.computation_id for r in (first, second, third)}) == 3
    assert len({r.spec.checkpoint_sha256 for r in (first, second, third)}) == 3


def test_backend_versions_change_identity(checkpoint, backend, monkeypatch):
    spec = TransformerEmbeddingSpec(str(checkpoint))
    first = transformer_embeddings(log_fixture(), spec)
    monkeypatch.setattr(
        implementation, "_versions", lambda: (("adapter-test-double", "2"),)
    )
    second = transformer_embeddings(log_fixture(), spec)
    assert first.computation_id != second.computation_id


def test_truncation_is_rejected_before_encode_by_default(checkpoint, backend):
    backend.max_seq_length = 4
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "transformer_text_too_long"
    assert backend.sentences is None


def test_explicit_truncation_is_partial_with_row_evidence(checkpoint, backend):
    backend.max_seq_length = 4
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint), allow_truncation=True)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert [row.truncated for row in result.value.rows] == [True, True, False]
    assert [issue.at for issue in result.issues] == [("z",), ("a",)]


def test_token_count_includes_saved_transformer_lowercasing(checkpoint, backend):
    backend.max_seq_length = 10
    backend._first_module = lambda: SimpleNamespace(do_lower_case=True)
    backend.tokenizer = lambda text, **kwargs: {
        "input_ids": [1] * (12 if "a" in text else 3)
    }
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "transformer_text_too_long"
    assert backend.sentences is None


def test_peft_external_base_model_cannot_escape_weight_identity(checkpoint, backend):
    (checkpoint / "adapter_config.json").write_text(
        json.dumps({"base_model_name_or_path": "../unhashed-base-model"}),
        encoding="utf-8",
    )
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "local_checkpoint_unavailable"
    assert backend.sentences is None


@pytest.mark.parametrize(
    "filename,settings",
    [
        ("ADAPTER_CONFIG.JSON", {"base_model_name_or_path": "../external"}),
        ("sentence_bert_config.json", {"tokenizer_name_or_path": "../external"}),
        (
            "SENTENCE_ROBERTA_CONFIG.JSON",
            {"tokenizer_args": {"vocab_file": "../external"}},
        ),
        ("config_sentence_transformers.json", {"model_type": "OtherModel"}),
    ],
)
def test_config_cannot_introduce_unhashed_resources_or_fallback_pooling(
    checkpoint, backend, filename, settings
):
    (checkpoint / filename).write_text(json.dumps(settings), encoding="utf-8")
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "local_checkpoint_unavailable"
    assert backend.sentences is None


@pytest.mark.parametrize(
    "diagnostics",
    [
        {"missing_keys": ["attention.weight"], "mismatched_keys": [], "error_msgs": []},
        {"missing_keys": [], "mismatched_keys": ["weight"], "error_msgs": []},
        {"missing_keys": [], "mismatched_keys": [], "error_msgs": ["load error"]},
        {},
    ],
)
def test_incomplete_weights_are_rejected_instead_of_randomly_initialized(
    checkpoint, monkeypatch, diagnostics
):
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoModel=SimpleNamespace(
                from_pretrained=lambda *args, **kwargs: (object(), diagnostics)
            )
        ),
    )
    with pytest.raises(ValueError):
        implementation._validate_weights(checkpoint)


def test_complete_weight_diagnostics_allow_unused_checkpoint_head(
    checkpoint, monkeypatch
):
    calls = []

    def load(path, **kwargs):
        calls.append((path, kwargs))
        return object(), {
            "missing_keys": [],
            "mismatched_keys": [],
            "error_msgs": [],
            "unexpected_keys": ["unused.classifier.weight"],
        }

    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=load)),
    )
    implementation._validate_weights(checkpoint)
    assert calls == [
        (
            str(checkpoint),
            {
                "local_files_only": True,
                "trust_remote_code": False,
                "output_loading_info": True,
            },
        )
    ]


@pytest.mark.parametrize(
    "bad_vectors",
    [[], [[1.0]], [[1.0, float("nan")]] * 3, [[True, 0.0]] * 3, [["1", 0.0]] * 3],
)
def test_malformed_backend_values_are_unavailable(checkpoint, backend, bad_vectors):
    backend.encode = lambda *args, **kwargs: bad_vectors
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "transformer_inference_failed"


def test_mid_inference_checkpoint_change_discards_results(checkpoint, backend):
    def mutate(sentences, **kwargs):
        (checkpoint / "weights.safetensors").write_bytes(b"changed-during-inference")
        return [[1.0, 0.0] for _ in sentences]

    backend.encode = mutate
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "transformer_checkpoint_changed"


def test_empty_log_has_known_dimension_and_does_not_call_encode(checkpoint, backend):
    result = transformer_embeddings(
        CaseLog(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.rows == ()
    assert result.value.dimensions == 2
    assert backend.sentences is None


@pytest.mark.parametrize(
    "module_type,path",
    [("custom.module", ""), ("sentence_transformers.models.Transformer", "../outside")],
)
def test_unhashed_or_custom_modules_are_explicitly_unavailable(
    checkpoint, backend, module_type, path
):
    (checkpoint / "modules.json").write_text(
        json.dumps([{"path": path, "type": module_type}]), encoding="utf-8"
    )
    result = transformer_embeddings(
        log_fixture(), TransformerEmbeddingSpec(str(checkpoint))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "local_checkpoint_unavailable"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"level": "object"},
        {"batch_size": True},
        {"batch_size": 0},
        {"normalize": 1},
        {"allow_truncation": 1},
        {"trace_spec": None},
    ],
)
def test_invalid_specs_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        TransformerEmbeddingSpec("local-checkpoint", **kwargs)


def test_contracts_reject_inconsistent_rows_and_digest():
    row = TransformerEmbeddingRow("c", None, "a" * 64, 5, False, (1.0, 0.0))
    with pytest.raises(ValueError):
        TransformerEmbeddingMatrix("event", 2, (row,), "b" * 64, 10)
    with pytest.raises(ValueError):
        TransformerEmbeddingMatrix("trace", 3, (row,), "b" * 64, 10)
    with pytest.raises(ValueError):
        TransformerEmbeddingMatrix("trace", 2, (row, row), "b" * 64, 10)
    with pytest.raises(ValueError):
        replace(row, truncated=True, values=(float("inf"),))
    with pytest.raises(ValueError):
        TransformerEmbeddingRequest(
            TransformerEmbeddingSpec("local-checkpoint"), "not-a-digest"
        )


def test_result_schema_has_operator_kind_spec_and_value():
    assert implementation.RESULT_SCHEMAS == {
        "pix.case_centric.transformer_embeddings": (
            "case-transformer-embeddings",
            TransformerEmbeddingRequest,
            TransformerEmbeddingMatrix,
        )
    }
