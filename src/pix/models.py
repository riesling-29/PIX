"""PIX-native model artifacts with explicit model semantics and provenance.

This JSON format is neither PNML nor BPMN. Executable object-centric artifacts
contain an explicit concrete-object universe. Other registered artifacts retain
their own declared relational, declarative, stochastic or partial-order profile.
Digests detect changed content; they are not signatures or correctness proofs.
The shared codec rejects structural nesting above 128 before publishing; for
process trees, both a child array and a node record count toward this limit.
"""

from __future__ import annotations

import json
import math
import os
import types
from collections import Counter
from dataclasses import dataclass, is_dataclass
from hashlib import sha256
from itertools import combinations
from pathlib import Path
from typing import Literal, Union, get_args, get_origin, get_type_hints

from pix._publication import FilePublication, publish_bytes
from pix.case_centric.decision_mining import DataPetriNet, data_petri_net_digest
from pix.case_centric.declarative import DeclareModel, LogSkeleton, TemporalProfile
from pix.case_centric.discovery import FootprintModel, TransitionSystem
from pix.case_centric.extended_nets import ResetInhibitorNet, StochasticPetriNet
from pix.case_centric.heuristics import HeuristicsNet
from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import SplitBPMN
from pix.compute.model_semantics import model_digest as _net_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import ObjectCentricPetriNet, PetriNet
from pix.object_centric.discovery import StochasticArcWeightNet
from pix.object_centric.models import ObjectCentricCausalNet, causal_net_digest
from pix.results import _decode, _encode, _json_bytes, _members, _reject_constant

MODEL_FORMAT = "pix.model"
MODEL_VERSION = "1.0.0"
Model = (
    PetriNet
    | ObjectCentricPetriNet
    | ProcessTree
    | HeuristicsNet
    | FootprintModel
    | TransitionSystem
    | DeclareModel
    | LogSkeleton
    | TemporalProfile
    | POWLNode
    | SplitBPMN
    | ObjectCentricCausalNet
    | StochasticArcWeightNet
    | DataPetriNet
    | ResetInhibitorNet
    | StochasticPetriNet
)
ModelOrigin = Literal["provided", "discovered", "unspecified"]

_MODELS: dict[type, tuple[str, str]] = {
    PetriNet: ("petri-net", "weighted-place-transition"),
    ObjectCentricPetriNet: (
        "object-centric-petri-net",
        "unit-incidence-concrete-object-universe",
    ),
    ProcessTree: ("process-tree", "block-structured-tree"),
    HeuristicsNet: ("heuristics-net", "pix.heuristics-net.v1"),
    FootprintModel: ("footprint-model", "pix.observed-log-footprints.v1"),
    TransitionSystem: ("transition-system", "pix.observed-context-state-graph.v1"),
    DeclareModel: ("declare-model", "pix.finite-trace-declare.v1"),
    LogSkeleton: ("log-skeleton", "pix.activation-log-skeleton.v1"),
    TemporalProfile: ("temporal-profile", "pix.occurrence-temporal-profile.v1"),
    POWLNode: ("powl", "pix.original-powl.v1"),
    SplitBPMN: ("bpmn-control-flow", "pix.xor-and-bpmn.v1"),
    ObjectCentricCausalNet: (
        "object-centric-causal-net",
        "pix.finite_object_obligation_net.v1",
    ),
    StochasticArcWeightNet: ("stochastic-arc-weight-net", "pix.observed_saw.v1"),
    DataPetriNet: ("data-petri-net", "pix.typed-numeric-decision-guards.v1"),
    ResetInhibitorNet: (
        "reset-inhibitor-net",
        "pix.exclusive-input-reset-inhibitor.v1",
    ),
    StochasticPetriNet: (
        "stochastic-petri-net",
        "pix.weighted-choice-serial-duration.v1",
    ),
}

_LEGACY_MODELS = (PetriNet, ObjectCentricPetriNet, ProcessTree)


def _typed_float_tokens(value, expected):
    """Normalize int-valued float fields when writing new model contracts.

    Reading remains strict. A union explicitly permitting integers retains its
    integer branch; bool is never converted. Legacy model encoding is untouched.
    """
    origin, args = get_origin(expected), get_args(expected)
    if expected is float and type(value) is int:
        try:
            number = float(value)
        except OverflowError as exc:
            raise ValueError("model numeric value exceeds finite float range") from exc
        if not math.isfinite(number):
            raise ValueError("model numeric value must be finite")
        return number
    if origin in (Union, types.UnionType):
        for option in args:
            try:
                _decode(value, option)
                return value
            except (TypeError, ValueError):
                pass
        for option in args:
            try:
                normalized = _typed_float_tokens(value, option)
                _decode(normalized, option)
                return normalized
            except (TypeError, ValueError):
                pass
        return value
    if origin is tuple and isinstance(value, list):
        kinds = (
            (args[0],) * len(value) if len(args) == 2 and args[1] is Ellipsis else args
        )
        if len(kinds) == len(value):
            return [_typed_float_tokens(item, kind) for item, kind in zip(value, kinds)]
    if (
        isinstance(expected, type)
        and is_dataclass(expected)
        and isinstance(value, dict)
    ):
        hints = get_type_hints(expected)
        return {
            name: _typed_float_tokens(item, hints[name]) if name in hints else item
            for name, item in value.items()
        }
    return value


def _nonnegative(value, field):
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")


def _names(values, field):
    if any(type(value) is not str or not value.strip() for value in values):
        raise ValueError(f"{field} must contain nonblank text")
    if len(set(values)) != len(values):
        raise ValueError(f"{field} must not contain duplicates")
    return set(values)


def _reachable(seeds, edges):
    adjacency = {}
    for source, target in edges:
        adjacency.setdefault(source, set()).add(target)
    seen = set(seeds)
    pending = list(seen)
    while pending:
        for target in adjacency.get(pending.pop(), ()):
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def _validate_graph_model(model):
    """Validate older relational dataclasses that lack constructor guards."""
    if isinstance(model, FootprintModel):
        alphabet = _names(model.activities, "activities")
        for name in ("directly_follows", "causal", "parallel", "unrelated"):
            rows = getattr(model, name)
            if len(set(rows)) != len(rows) or any(
                a not in alphabet or b not in alphabet for a, b in rows
            ):
                raise ValueError(f"{name} must contain unique known activity pairs")
        follows = set(model.directly_follows)
        if set(model.causal) != {(a, b) for a, b in follows if (b, a) not in follows}:
            raise ValueError("causal footprint disagrees with directly-follows")
        if set(model.parallel) != {
            (a, b) for a, b in follows if a != b and (b, a) in follows
        }:
            raise ValueError("parallel footprint disagrees with directly-follows")
        expected = {
            (a, b)
            for a, b in combinations(sorted(alphabet), 2)
            if (a, b) not in follows and (b, a) not in follows
        }
        if set(model.unrelated) != expected:
            raise ValueError("unrelated footprint disagrees with directly-follows")
        for name in ("start_activities", "end_activities", "loop_activities"):
            if not _names(getattr(model, name), name) <= alphabet:
                raise ValueError(f"{name} references an unknown activity")
        if set(model.loop_activities) != {a for a in alphabet if (a, a) in follows}:
            raise ValueError("loop activities disagree with self succession")
        _nonnegative(model.empty_trace_count, "empty_trace_count")
        if model.minimum_trace_length is not None:
            _nonnegative(model.minimum_trace_length, "minimum_trace_length")
        if model.empty_trace_count and model.minimum_trace_length != 0:
            raise ValueError("empty traces require minimum trace length zero")
        if alphabet and (
            model.minimum_trace_length is None
            or _reachable(model.start_activities, follows) != alphabet
            or _reachable(model.end_activities, ((b, a) for a, b in follows))
            != alphabet
        ):
            raise ValueError(
                "footprint activities require observed start-to-end paths and length"
            )
        if not alphabet and model.minimum_trace_length != (
            0 if model.empty_trace_count else None
        ):
            raise ValueError(
                "empty footprint length must distinguish no traces from empty traces"
            )
    elif isinstance(model, TransitionSystem):
        _nonnegative(model.trace_count, "trace_count")
        ids = _names(tuple(state.id for state in model.states), "state IDs")
        incoming, outgoing = Counter(), Counter()
        triples = set()
        for edge in model.transitions:
            key = edge.source, edge.target, edge.activity
            if edge.source not in ids or edge.target not in ids or key in triples:
                raise ValueError(
                    "transition must be unique and reference existing states"
                )
            _names((edge.activity,), "transition activity")
            _nonnegative(edge.occurrence_count, "occurrence_count")
            if edge.occurrence_count == 0:
                raise ValueError("state transitions require positive occurrence counts")
            triples.add(key)
            incoming[edge.target] += edge.occurrence_count
            outgoing[edge.source] += edge.occurrence_count
        for state in model.states:
            for activity in state.context:
                _names((activity,), "context activity")
            for name in ("visits", "initial_count", "final_count"):
                _nonnegative(getattr(state, name), name)
            if (
                state.visits != incoming[state.id] + state.initial_count
                or state.visits != outgoing[state.id] + state.final_count
            ):
                raise ValueError(
                    "state visits disagree with initial/final and edge counts"
                )
        if (
            sum(s.initial_count for s in model.states) != model.trace_count
            or sum(s.final_count for s in model.states) != model.trace_count
        ):
            raise ValueError("state boundaries disagree with trace population")
        graph = tuple((edge.source, edge.target) for edge in model.transitions)
        if (
            any(state.visits == 0 for state in model.states)
            or _reachable((s.id for s in model.states if s.initial_count), graph) != ids
            or _reachable(
                (s.id for s in model.states if s.final_count),
                ((b, a) for a, b in graph),
            )
            != ids
        ):
            raise ValueError(
                "observed states require positive visits and initial-to-final paths"
            )
    elif isinstance(model, HeuristicsNet):
        if model.profile not in (
            "pix.heuristics.classic.v1",
            "pix.heuristics.interval.v1",
        ):
            raise ValueError("unsupported heuristics profile")
        _nonnegative(model.trace_count, "trace_count")
        _nonnegative(model.empty_trace_count, "empty_trace_count")
        if model.empty_trace_count > model.trace_count:
            raise ValueError("empty traces exceed the trace population")
        all_rows = model.activities + model.excluded_activities
        alphabet = _names(
            tuple(row.activity for row in all_rows), "activity partitions"
        )
        retained = {row.activity for row in model.activities}
        for row in all_rows:
            for name in ("count", "start_count", "end_count"):
                _nonnegative(getattr(row, name), name)
            if row.start_count > row.count or row.end_count > row.count:
                raise ValueError("activity boundary count exceeds occurrences")
        nonempty = model.trace_count - model.empty_trace_count
        if (
            sum(r.start_count for r in all_rows) != nonempty
            or sum(r.end_count for r in all_rows) != nonempty
        ):
            raise ValueError("activity boundary counts disagree with trace population")
        for name in ("follows", "overlaps", "precleaned_edges"):
            seen = set()
            for row in getattr(model, name):
                key = row.source, row.target
                if (
                    row.source not in alphabet
                    or row.target not in alphabet
                    or key in seen
                ):
                    raise ValueError(f"{name} must reference unique known pairs")
                _nonnegative(row.count, "frequency count")
                seen.add(key)
        if len(set(model.edges)) != len(model.edges) or any(
            a not in retained or b not in retained for a, b in model.edges
        ):
            raise ValueError("heuristics edges must be unique retained activity pairs")
        for row in model.dependencies:
            if row.source not in retained or row.target not in retained:
                raise ValueError(
                    "dependency references an excluded or unknown activity"
                )
            for name in ("count", "reverse_count", "overlap_count"):
                _nonnegative(getattr(row, name), name)
            if row.selected and (row.source, row.target) not in model.edges:
                raise ValueError("selected dependency is missing its edge")
            if model.profile == "pix.heuristics.classic.v1":
                denominator = (
                    row.count + 1
                    if row.source == row.target
                    else row.count + row.reverse_count + 1
                )
                numerator = (
                    row.count
                    if row.source == row.target
                    else row.count - row.reverse_count
                )
            else:
                denominator = row.count + row.reverse_count + row.overlap_count
                numerator = row.count - row.reverse_count
            if (
                row.count == 0
                or denominator == 0
                or not math.isclose(
                    row.measure, numerator / denominator, rel_tol=1e-12, abs_tol=1e-12
                )
            ):
                raise ValueError(
                    "dependency measure disagrees with the declared profile equation"
                )
        for row in model.short_loops:
            if (
                len(row.activities) not in (1, 2)
                or len(set(row.activities)) != len(row.activities)
                or not set(row.activities) <= retained
            ):
                raise ValueError("loop references unknown retained activities")
            _nonnegative(row.occurrences, "loop occurrences")
            if not math.isclose(
                row.measure,
                row.occurrences / (row.occurrences + 1),
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("short-loop measure disagrees with occurrence counts")
        for row in model.and_pairs:
            if not {row.activity, row.left, row.right} <= retained:
                raise ValueError("AND pair references unknown retained activities")
            _nonnegative(row.numerator, "AND numerator")
            _nonnegative(row.denominator, "AND denominator")
            if row.denominator == 0:
                raise ValueError("AND denominator must be positive")
            if not math.isclose(
                row.measure,
                row.numerator / row.denominator,
                rel_tol=1e-12,
                abs_tol=1e-12,
            ):
                raise ValueError("AND measure disagrees with numerator and denominator")
        binding_ids = set()
        for binding in model.bindings:
            key = binding.activity, binding.direction
            if binding.activity not in retained or key in binding_ids:
                raise ValueError(
                    "bindings require unique retained activity/direction pairs"
                )
            binding_ids.add(key)
            for alternative in binding.alternatives:
                if (
                    not alternative
                    or not _names(alternative, "binding alternative") <= retained
                ):
                    raise ValueError("binding alternatives require retained activities")
                for neighbour in alternative:
                    edge = (
                        (neighbour, binding.activity)
                        if binding.direction == "input"
                        else (binding.activity, neighbour)
                    )
                    if edge not in model.edges:
                        raise ValueError(
                            "binding alternative references a missing edge"
                        )
        if binding_ids != {
            (a, direction) for a in retained for direction in ("input", "output")
        }:
            raise ValueError(
                "every retained activity requires input and output bindings"
            )
        by_binding = {
            (binding.activity, binding.direction): {
                a for alternative in binding.alternatives for a in alternative
            }
            for binding in model.bindings
        }
        for source, target in model.edges:
            if source != target and (
                target not in by_binding[source, "output"]
                or source not in by_binding[target, "input"]
            ):
                raise ValueError(
                    "every non-self edge requires source and target binding coverage"
                )


def _validated_model_encoding(model):
    encoded = _encode(model)
    if type(model) in _LEGACY_MODELS:
        return encoded
    encoded = _typed_float_tokens(encoded, type(model))
    normalized = _decode(encoded, type(model))
    if normalized != model:
        raise ValueError("native model does not preserve its contract on round trip")
    _validate_graph_model(normalized)
    return encoded


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
        if type(self.model) not in _LEGACY_MODELS:
            _validated_model_encoding(self.model)
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
    if type(model) in (PetriNet, ObjectCentricPetriNet):
        return _net_digest(model)
    if type(model) is ObjectCentricCausalNet:
        return causal_net_digest(model)
    if type(model) is DataPetriNet:
        return data_petri_net_digest(model)
    kind, profile = _MODELS[type(model)]
    body = {
        "kind": kind,
        "profile": profile,
        "schema_version": MODEL_VERSION,
        "semantics_version": "1.0.0",
        "model": encoded,
    }
    return f"pix.model.{kind}.v1:sha256:" + sha256(_json_bytes(body)).hexdigest()


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
    encoded = _validated_model_encoding(artifact.model)
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
    ] != _model_digest(model, _validated_model_encoding(model)):
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
