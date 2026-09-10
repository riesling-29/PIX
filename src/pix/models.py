"""PIX-native model artifacts with explicit model semantics and provenance.

This JSON format is neither PNML nor BPMN. Object-centric artifacts contain an
explicit concrete-object execution universe, not a generic object-free model.
Digests detect changed content; they are not signatures or correctness proofs.
The shared codec rejects structural nesting above 128 before publishing; for
process trees, both a child array and a node record count toward this limit.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from pix._publication import FilePublication, publish_bytes
from pix.compute.model_semantics import model_digest as _net_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import ObjectCentricPetriNet, PetriNet
from pix.results import _decode, _encode, _json_bytes, _members, _reject_constant

MODEL_FORMAT = "pix.model"
MODEL_VERSION = "1.0.0"
Model = PetriNet | ObjectCentricPetriNet | ProcessTree
ModelOrigin = Literal["provided", "discovered", "unspecified"]

_MODELS: dict[type, tuple[str, str]] = {
    PetriNet: ("petri-net", "weighted-place-transition"),
    ObjectCentricPetriNet: (
        "object-centric-petri-net",
        "unit-incidence-concrete-object-universe",
    ),
    ProcessTree: ("process-tree", "block-structured-tree"),
}


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """An immutable native model and its declared origin.

    Discovered models require a source computation reference. This records the
    caller's provenance declaration; loading does not prove that computation
    occurred. Other origins cannot carry a discovery computation reference.
    """

    model: Model
    origin: ModelOrigin = "unspecified"
    source_computation_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.model) not in _MODELS:
            raise TypeError("model must be an explicitly supported native model")
        if type(self.origin) is not str or self.origin not in (
            "provided",
            "discovered",
            "unspecified",
        ):
            raise ValueError("unsupported model origin")
        if self.origin == "discovered":
            source = self.source_computation_id
            if not isinstance(source, str) or not source.strip():
                raise ValueError("discovered models require a source computation ID")
            try:
                source.encode("utf-8")
            except UnicodeEncodeError as error:
                raise ValueError(
                    "source computation ID must be valid Unicode"
                ) from error
        elif self.source_computation_id is not None:
            raise ValueError("only discovered models have a source computation ID")


def _artifact(
    model: Model | ModelArtifact,
    origin: ModelOrigin | None,
    source_computation_id: str | None,
) -> ModelArtifact:
    if isinstance(model, ModelArtifact):
        if origin is not None and origin != model.origin:
            raise ValueError("origin conflicts with supplied model artifact")
        if (
            source_computation_id is not None
            and source_computation_id != model.source_computation_id
        ):
            raise ValueError(
                "source computation conflicts with supplied model artifact"
            )
        return model
    return ModelArtifact(
        model, "unspecified" if origin is None else origin, source_computation_id
    )


def _model_digest(model: Model, encoded: object) -> str:
    if type(model) is ProcessTree:
        body = {
            "kind": "process-tree",
            "schema_version": MODEL_VERSION,
            "semantics_version": "1.0.0",
            "model": encoded,
        }
        return (
            "pix.model.process-tree.v1:sha256:" + sha256(_json_bytes(body)).hexdigest()
        )
    return _net_digest(model)


def _document_digest(document: object) -> str:
    return "pix.model-document.v1:sha256:" + sha256(_json_bytes(document)).hexdigest()


def model_document(
    model: Model | ModelArtifact,
    *,
    origin: ModelOrigin | None = None,
    source_computation_id: str | None = None,
) -> dict[str, object]:
    """Produce an explicit, JSON-compatible native model document.

    Omitted provenance preserves a supplied artifact; a bare model defaults to
    ``unspecified``. Conflicting supplied metadata raises rather than changing
    the model's declared origin. Tree identity is structural, including ordered
    children; it does not identify all trees with equivalent languages.
    """
    artifact = _artifact(model, origin, source_computation_id)
    kind, profile = _MODELS[type(artifact.model)]
    encoded = _encode(artifact.model)
    body = {
        "format": MODEL_FORMAT,
        "version": MODEL_VERSION,
        "kind": kind,
        "profile": profile,
        "model_digest": _model_digest(artifact.model, encoded),
        "provenance": {
            "origin": artifact.origin,
            "source_computation_id": artifact.source_computation_id,
        },
        "model": encoded,
    }
    return {**body, "document_digest": _document_digest(body)}


def model_json_bytes(
    model: Model | ModelArtifact,
    *,
    origin: ModelOrigin | None = None,
    source_computation_id: str | None = None,
) -> bytes:
    return _json_bytes(
        model_document(
            model, origin=origin, source_computation_id=source_computation_id
        )
    )


def model_from_json(data: str | bytes) -> ModelArtifact:
    """Load only registered model contracts, validating both content identities."""
    if not isinstance(data, (str, bytes)):
        raise TypeError("model JSON data must be str or bytes")
    try:
        document = json.loads(
            data, object_pairs_hook=_members, parse_constant=_reject_constant
        )
    except RecursionError as error:
        raise ValueError("model JSON exceeds the nesting limit") from error
    if not isinstance(document, dict) or set(document) != {
        "format",
        "version",
        "kind",
        "profile",
        "model_digest",
        "provenance",
        "model",
        "document_digest",
    }:
        raise ValueError("invalid native model document fields")
    if document["format"] != MODEL_FORMAT or document["version"] != MODEL_VERSION:
        raise ValueError("unsupported native model format or version")
    registered = [
        model_type
        for model_type, (kind, profile) in _MODELS.items()
        if document["kind"] == kind and document["profile"] == profile
    ]
    if len(registered) != 1:
        raise ValueError("unsupported model kind or semantic profile")
    body = {key: value for key, value in document.items() if key != "document_digest"}
    try:
        digest = _document_digest(body)
    except RecursionError as error:
        raise ValueError("model JSON exceeds the nesting limit") from error
    if (
        type(document["document_digest"]) is not str
        or document["document_digest"] != digest
    ):
        raise ValueError("native model document digest mismatch")
    provenance = document["provenance"]
    if not isinstance(provenance, dict) or set(provenance) != {
        "origin",
        "source_computation_id",
    }:
        raise ValueError("invalid model provenance fields")
    model = _decode(document["model"], registered[0])
    artifact = ModelArtifact(
        model,
        _decode(provenance["origin"], ModelOrigin),
        _decode(provenance["source_computation_id"], str | None),
    )
    if type(document["model_digest"]) is not str or document[
        "model_digest"
    ] != _model_digest(model, _encode(model)):
        raise ValueError("native model semantic digest mismatch")
    return artifact


def read_model(path: str | os.PathLike[str]) -> ModelArtifact:
    return model_from_json(Path(path).read_bytes())


def write_model(
    model: Model | ModelArtifact,
    path: str | os.PathLike[str],
    *,
    origin: ModelOrigin | None = None,
    source_computation_id: str | None = None,
    overwrite: bool = False,
) -> FilePublication:
    """Verify a round trip before atomic publication, with no clobber by default.

    The caller supplies the only output path. Content cannot import modules,
    invoke constructors by name, choose a filename or read external resources.
    The returned evidence distinguishes a complete published artifact from any
    staging cleanup issue; warnings filters cannot turn publication into failure.
    """
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    artifact = _artifact(model, origin, source_computation_id)
    payload = model_json_bytes(artifact)
    if model_from_json(payload) != artifact:
        raise ValueError("native model artifact does not round-trip")
    return publish_bytes(payload, path, overwrite=overwrite, prefix=".pix-model-")


__all__ = [
    "MODEL_FORMAT",
    "MODEL_VERSION",
    "ModelArtifact",
    "ModelOrigin",
    "model_document",
    "model_from_json",
    "model_json_bytes",
    "read_model",
    "write_model",
]
