"""Occurrence-aware activity inspection and relabeling of executable models.

This changes semantic activity names, not viewer captions. Relabeling preserves
the model graph, leaf positions, silent behavior and transition identities.
The visible language is renamed accordingly; non-injective names may hide
distinctions in observations but never merge model occurrences. Tree positions
are stable only while structure is unchanged, not across arbitrary conversions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar

from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import SplitBPMN
from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import ObjectCentricPetriNet, PetriNet
from pix.contracts.result import ComputationResult, ComputeStatus

LabelModel = PetriNet | ObjectCentricPetriNet | ProcessTree | POWLNode | SplitBPMN
_SUPPORTED = (PetriNet, ObjectCentricPetriNet, ProcessTree, POWLNode, SplitBPMN)


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{name} must be valid Unicode") from error


def _limits(nodes, depth):
    if type(nodes) is not int or nodes < 1:
        raise ValueError("max_model_nodes must be a positive integer")
    if type(depth) is not int or not 1 <= depth <= 48:
        raise ValueError("max_depth must be an integer in [1, 48]")


@dataclass(frozen=True, slots=True)
class ModelLabelReadSpec:
    include_silent: bool = True
    max_model_nodes: int = 20_000
    max_depth: int = 48
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if type(self.include_silent) is not bool:
            raise TypeError("include_silent must be bool")
        _limits(self.max_model_nodes, self.max_depth)


@dataclass(frozen=True, slots=True)
class ModelLabelRenameSpec:
    """Map exact occurrence IDs to nonblank labels; silence cannot be renamed."""

    replacements: tuple[tuple[str, str], ...] = ()
    max_model_nodes: int = 20_000
    max_depth: int = 48
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _limits(self.max_model_nodes, self.max_depth)
        if not isinstance(self.replacements, tuple):
            raise TypeError("replacements must be a tuple of occurrence/label pairs")
        seen = set()
        for pair in self.replacements:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError("replacement must be an occurrence/label tuple")
            occurrence, activity = pair
            _text(occurrence, "occurrence ID")
            _text(activity, "activity")
            if occurrence in seen:
                raise ValueError("duplicate replacement occurrence ID")
            seen.add(occurrence)
        object.__setattr__(self, "replacements", tuple(sorted(self.replacements)))


@dataclass(frozen=True, slots=True)
class ModelLabelRequest:
    model_digest: str
    parameters: ModelLabelReadSpec | ModelLabelRenameSpec


@dataclass(frozen=True, slots=True)
class ActivityLabelOccurrence:
    occurrence_id: str
    node_id: str | None
    activity: str | None
    silent: bool
    tree_path: tuple[int, ...] | None = None


@dataclass(frozen=True, slots=True)
class ActivityLabels:
    model_digest: str
    occurrences: tuple[ActivityLabelOccurrence, ...]


@dataclass(frozen=True, slots=True)
class ModelLabelChange:
    occurrence_id: str
    before: str
    after: str


@dataclass(frozen=True, slots=True)
class ModelLabelRenaming:
    model: LabelModel
    source_model_digest: str
    output_model_digest: str
    changes: tuple[ModelLabelChange, ...]
    occurrences: tuple[ActivityLabelOccurrence, ...]


def _path_id(prefix, path):
    return prefix + "/" + ("/".join(map(str, path)) if path else "root")


def _occurrences(model, spec):
    """Validate size before recursive model digest/encoding or rebuilding."""
    if type(model) in (PetriNet, ObjectCentricPetriNet):
        if len(model.places) + len(model.transitions) > spec.max_model_nodes:
            raise ValueError("model exceeds max_model_nodes")
        return tuple(
            ActivityLabelOccurrence(
                "transition/" + node.id, node.id, node.activity, node.activity is None
            )
            for node in model.transitions
        )
    if type(model) is SplitBPMN:
        if len(model.nodes) > spec.max_model_nodes:
            raise ValueError("model exceeds max_model_nodes")
        return tuple(
            ActivityLabelOccurrence("task/" + node.id, node.id, node.activity, False)
            for node in sorted(model.nodes, key=lambda item: item.id)
            if node.kind == "task"
        )
    prefix = "tree" if type(model) is ProcessTree else "powl"
    pending, count, rows = [(model, ())], 0, []
    while pending:
        node, path = pending.pop()
        count += 1
        if count > spec.max_model_nodes or len(path) + 1 > spec.max_depth:
            raise ValueError("model exceeds max_model_nodes or max_depth")
        kind = node.operator if type(model) is ProcessTree else node.kind
        if kind in ("activity", "tau"):
            rows.append(
                ActivityLabelOccurrence(
                    _path_id(prefix, path), None, node.activity, kind == "tau", path
                )
            )
        pending.extend(
            (child, (*path, index))
            for index, child in reversed(tuple(enumerate(node.children)))
        )
    return tuple(rows)


def _input(model, spec):
    # Local import keeps result-codec registration independent of model imports.
    from pix.models import ModelArtifact, model_document

    parents = ()
    if isinstance(model, ModelArtifact):
        if model.source_computation_id is not None:
            parents = (model.source_computation_id,)
        model = model.model
    if type(model) not in _SUPPORTED:
        raise TypeError(
            "activity labels support exactly PetriNet, ObjectCentricPetriNet, "
            "ProcessTree, POWLNode and SplitBPMN; this model is unsupported"
        )
    rows = _occurrences(model, spec)
    return model, rows, model_document(model)["model_digest"], parents


def activity_labels(
    model: LabelModel,
    spec: ModelLabelReadSpec = ModelLabelReadSpec(),
) -> ComputationResult[ActivityLabels]:
    """Read semantic occurrences, optionally including explicit silent leaves.

    A ``ModelArtifact`` is also accepted and retains its discovery computation
    as a parent. BPMN events/gateways are structural nodes, not activity labels.
    Unsupported model families fail explicitly; labels are never deduplicated.
    """
    if not isinstance(spec, ModelLabelReadSpec):
        raise TypeError("spec must be ModelLabelReadSpec")
    _, rows, digest, parents = _input(model, spec)
    if not spec.include_silent:
        rows = tuple(row for row in rows if not row.silent)
    return _derived_result(
        "pix.case_centric.activity_labels",
        digest,
        ModelLabelRequest(digest, spec),
        ComputeStatus.COMPUTED,
        ActivityLabels(digest, rows),
        parent_computation_ids=parents,
    )


def _rename(model, replacements, path=()):
    if type(model) in (PetriNet, ObjectCentricPetriNet):
        return replace(
            model,
            transitions=tuple(
                replace(
                    node,
                    activity=replacements.get("transition/" + node.id, node.activity),
                )
                for node in model.transitions
            ),
        )
    if type(model) is SplitBPMN:
        return replace(
            model,
            nodes=tuple(
                replace(
                    node, activity=replacements.get("task/" + node.id, node.activity)
                )
                if node.kind == "task"
                else node
                for node in model.nodes
            ),
        )
    prefix = "tree" if type(model) is ProcessTree else "powl"
    if not model.children:
        return replace(
            model, activity=replacements.get(_path_id(prefix, path), model.activity)
        )
    return replace(
        model,
        children=tuple(
            _rename(child, replacements, (*path, index))
            for index, child in enumerate(model.children)
        ),
    )


def rename_activity_labels(
    model: LabelModel,
    spec: ModelLabelRenameSpec = ModelLabelRenameSpec(),
) -> ComputationResult[ModelLabelRenaming]:
    """Rename selected visible occurrences without mutating the input model.

    Unknown IDs and attempts to convert silence to an activity fail atomically.
    A no-op mapping is valid and retains the canonical semantic model digest.
    """
    from pix.models import model_document

    if not isinstance(spec, ModelLabelRenameSpec):
        raise TypeError("spec must be ModelLabelRenameSpec")
    source, rows, digest, parents = _input(model, spec)
    by_id = {row.occurrence_id: row for row in rows}
    changes = []
    for occurrence, activity in spec.replacements:
        if occurrence not in by_id:
            raise ValueError(f"unknown activity occurrence ID: {occurrence}")
        before = by_id[occurrence]
        if before.silent:
            raise ValueError("silent occurrences cannot be renamed to activities")
        if before.activity != activity:
            changes.append(ModelLabelChange(occurrence, before.activity, activity))
    output = _rename(source, dict(spec.replacements))
    return _derived_result(
        "pix.case_centric.rename_activity_labels",
        digest,
        ModelLabelRequest(digest, spec),
        ComputeStatus.COMPUTED,
        ModelLabelRenaming(
            output,
            digest,
            model_document(output)["model_digest"],
            tuple(changes),
            _occurrences(output, spec),
        ),
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.activity_labels": (
        "case-model-activity-labels",
        ModelLabelRequest,
        ActivityLabels,
    ),
    "pix.case_centric.rename_activity_labels": (
        "case-model-rename-activity-labels",
        ModelLabelRequest,
        ModelLabelRenaming,
    ),
}


__all__ = [
    "ActivityLabelOccurrence",
    "ActivityLabels",
    "ModelLabelChange",
    "ModelLabelReadSpec",
    "ModelLabelRenameSpec",
    "ModelLabelRenaming",
    "ModelLabelRequest",
    "activity_labels",
    "rename_activity_labels",
]
