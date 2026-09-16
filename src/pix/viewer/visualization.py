"""Public, renderer-independent native visualization assembly and JSON I/O.

Adapters read results. They never discover a model, replay a log, or reinterpret
an unknown measurement as zero. Multiple inputs remain independently attributed
panels; putting them in one document does not assert an analytical join.
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path
from typing import get_args

from pix._publication import FilePublication, publish_bytes
from pix.case_centric.interleavings_ocel import InterleavingsOCELConversion
from pix.contracts.graph import GraphDocument, ModelGraphDocument
from pix.contracts.result import ComputationResult, ComputeStatus, computation_identity
from pix.event_log import CaseLog
from pix.event_log.adapters import case_log_digest
from pix.models import Model, ModelArtifact, model_document
from pix.ocel import OCEL, canonical_digest
from pix.results import RESULT_VERSION, _encode

from .visual_contracts import (
    GraphPanel,
    TablePanel,
    VisualEdge,
    VisualField,
    VisualizationDocument,
    VisualMetric,
    VisualNode,
    VisualProvenance,
)


class UnsupportedVisualizationError(TypeError):
    """No domain adapter exists for the explicitly supplied native value."""


def _text_list(values: tuple) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _legacy_graph_panels(value: GraphDocument | ModelGraphDocument) -> tuple:
    if isinstance(value, GraphDocument):
        nodes = tuple(
            VisualNode(
                node.id,
                node.label,
                metrics=(
                    VisualMetric("events", len(node.event_ids), "unique events"),
                    VisualMetric("objects", len(node.object_ids), "unique objects"),
                ),
                details=(
                    VisualField("event_ids", _text_list(node.event_ids)),
                    VisualField("object_ids", _text_list(node.object_ids)),
                ),
            )
            for node in value.nodes
        )
        edges = tuple(
            VisualEdge(
                edge.id,
                edge.source,
                edge.target,
                label=edge.object_type,
                metrics=(
                    VisualMetric("event_pairs", edge.counts.event_pairs, "event pairs"),
                    VisualMetric(
                        "objects", edge.counts.unique_objects, "unique objects"
                    ),
                    VisualMetric(
                        "occurrences",
                        edge.counts.occurrences,
                        "event-event-object triples",
                    ),
                ),
                details=(VisualField("object_type", edge.object_type),),
            )
            for edge in value.edges
        )
        evidence = TablePanel(
            "relation-evidence",
            "Directly-follows evidence",
            (
                "edge",
                "source event",
                "target event",
                "object",
                "source qualifiers",
                "target qualifiers",
            ),
            tuple(
                (
                    edge.id,
                    item.source_event_id,
                    item.target_event_id,
                    item.object_id,
                    _text_list(item.source_qualifiers),
                    _text_list(item.target_qualifiers),
                )
                for edge in value.edges
                for item in edge.evidence
            ),
            description="One row per observed event-event-object triple; count units stay separate.",
        )
        return (GraphPanel("process-graph", value.title, nodes, edges), evidence)
    nodes = tuple(
        VisualNode(
            node.id,
            node.label,
            kind=node.kind,
            group=node.object_type,
            metrics=(
                VisualMetric("initial_tokens", node.initial_count, "tokens"),
                VisualMetric("final_tokens", node.final_count, "tokens"),
            ),
            details=(
                VisualField("model_node_id", node.model_node_id),
                VisualField("initial_objects", _text_list(node.initial_objects)),
                VisualField("final_objects", _text_list(node.final_objects)),
            ),
        )
        for node in value.nodes
    )
    edges = tuple(
        VisualEdge(
            edge.id,
            edge.source,
            edge.target,
            label=(
                f"{edge.min_objects}..{'*' if edge.max_objects is None else edge.max_objects}"
                if edge.variable
                else (str(edge.weight) if edge.weight != 1 else "")
            ),
            kind="variable_arc" if edge.variable else "arc",
            metrics=(VisualMetric("arc_weight", edge.weight, "tokens"),),
            details=(
                VisualField("object_type", edge.object_type),
                VisualField("variable", edge.variable),
                VisualField("min_objects", edge.min_objects),
                VisualField("max_objects", edge.max_objects),
            ),
        )
        for edge in value.edges
    )
    return (GraphPanel("model", value.title, nodes, edges),)


def _source_metadata(value: object) -> tuple[VisualProvenance, ...]:
    if isinstance(value, InterleavingsOCELConversion):
        return _source_metadata(value.evidence)
    if isinstance(value, ComputationResult):
        expected = computation_identity(
            value.operator_id,
            value.operator_version,
            value.source_digest,
            value.spec,
            value.parent_computation_ids,
        )
        if value.computation_id != expected:
            raise ValueError(
                "visualization source request does not match its computation identity"
            )
        return (
            VisualProvenance(
                calculation_id=value.computation_id,
                source_digest=value.source_digest,
                operator_id=value.operator_id,
                status=value.status.value,
                details=(
                    VisualField("operator_version", value.operator_version),
                    VisualField(
                        "request_type",
                        f"{type(value.spec).__module__}.{type(value.spec).__qualname__}",
                    ),
                    VisualField("request_encoding", f"pix.result/{RESULT_VERSION}"),
                    VisualField(
                        "request_json",
                        json.dumps(
                            _encode(value.spec, large_integers=True),
                            ensure_ascii=False,
                            allow_nan=False,
                            sort_keys=True,
                        ),
                    ),
                ),
            ),
            *(
                VisualProvenance(
                    calculation_id=parent, details=(VisualField("role", "parent"),)
                )
                for parent in value.parent_computation_ids
            ),
        )
    if isinstance(value, GraphDocument):
        return (
            VisualProvenance(
                calculation_id=value.computation_id, source_digest=value.source_digest
            ),
        )
    if isinstance(value, ModelGraphDocument):
        return (
            VisualProvenance(
                calculation_id=value.source_computation_id,
                model_digest=value.model_digest,
                details=(VisualField("origin", value.origin),),
            ),
        )
    if isinstance(value, OCEL):
        return (VisualProvenance(source_digest=canonical_digest(value).identifier),)
    if isinstance(value, CaseLog):
        return (VisualProvenance(source_digest=case_log_digest(value)),)
    if isinstance(value, ModelArtifact):
        document = model_document(value)
        return (
            VisualProvenance(
                calculation_id=value.source_computation_id,
                model_digest=document["model_digest"],
                details=(VisualField("origin", value.origin),),
            ),
        )
    return ()


def build_visualization(
    *values: object, title: str | None = None
) -> VisualizationDocument:
    """Adapt native logs, models and results to explicit visual panels.

    Each input owns its panels and provenance. This operation does not merge
    metrics across logs or decorate a model with unrelated analysis. Callers can
    also construct typed panels directly and pass a VisualizationDocument.
    """
    if not values:
        raise ValueError("at least one native visualization input is required")
    if title is not None and type(title) is not str:
        raise TypeError("title must be a string or None")
    if len(values) == 1 and isinstance(values[0], VisualizationDocument):
        return values[0] if title is None else replace(values[0], title=title)
    from .visual_case_adapters import case_panels
    from .visual_model_adapters import model_panels
    from .visual_model_results import model_result_view
    from .visual_object_adapters import object_panels

    panels = []
    provenance = []
    issues = []
    statuses = []
    for index, value in enumerate(values):
        if isinstance(value, VisualizationDocument):
            current = value.panels
            input_provenance = list(value.provenance)
            issues.extend(value.issues)
            statuses.append(value.status)
        else:
            input_provenance = list(_source_metadata(value))
            source = (
                value.evidence
                if isinstance(value, InterleavingsOCELConversion)
                else value
                if isinstance(value, ComputationResult)
                else None
            )
            payload = (
                value
                if isinstance(value, InterleavingsOCELConversion)
                else (source.value if source is not None else value)
            )
            if isinstance(payload, ModelArtifact):
                if source is not None:
                    input_provenance.extend(_source_metadata(payload))
                payload = payload.model
            if source is not None:
                issues.extend(
                    f"{issue.code}: {issue.message}" for issue in source.issues
                )
                statuses.append(
                    {
                        ComputeStatus.COMPUTED: "ok",
                        ComputeStatus.PARTIAL: "partial",
                        ComputeStatus.UNAVAILABLE: "unsupported",
                        ComputeStatus.INVALID_INPUT: "error",
                    }[source.status]
                )
            else:
                statuses.append("ok")
            if isinstance(payload, InterleavingsOCELConversion):
                # Its envelope contains the report, while this adapter needs
                # the candidate OCEL and retained case-log sidecars as well.
                current = object_panels(payload)
            elif isinstance(payload, (GraphDocument, ModelGraphDocument)):
                current = _legacy_graph_panels(payload)
                issues.extend(payload.notes)
            elif source is not None and payload is None:
                current = ()
            else:
                current = model_panels(payload)
                if current is not None:
                    if type(payload) in get_args(Model) and not isinstance(
                        value, ModelArtifact
                    ):
                        document = model_document(payload)
                        input_provenance.append(
                            VisualProvenance(
                                model_digest=document["model_digest"],
                                details=(VisualField("origin", "unspecified"),),
                            )
                        )
                else:
                    model_view = model_result_view(payload)
                    if model_view is not None:
                        embedded_model, current = model_view
                        if embedded_model is not None:
                            input_provenance.append(
                                VisualProvenance(
                                    model_digest=model_document(embedded_model)[
                                        "model_digest"
                                    ],
                                    details=(VisualField("role", "embedded model"),),
                                )
                            )
                    else:
                        current = case_panels(payload, source=source)
                if current is None:
                    current = object_panels(payload, source=source)
                if current is None:
                    raise UnsupportedVisualizationError(
                        f"No native visualization adapter for {type(payload).__module__}.{type(payload).__name__}; "
                        "provide an explicitly typed VisualizationDocument for a custom view"
                    )
        prefix = "" if len(values) == 1 else f"input-{index}/"
        panels.extend(
            replace(panel, id=f"{prefix}{panel.id}") if prefix else panel
            for panel in current
        )
        for item in input_provenance:
            scope = (
                item.panel_ids
                if item.panel_ids or item.input_path
                else tuple(panel.id for panel in current)
            )
            provenance.append(
                replace(
                    item,
                    panel_ids=tuple(f"{prefix}{panel_id}" for panel_id in scope),
                    input_path=(index, *item.input_path),
                )
            )
    status = "ok"
    for candidate in ("partial", "unsupported", "error"):
        if candidate in statuses:
            status = (
                "partial"
                if candidate == "unsupported"
                and any(item in ("ok", "partial") for item in statuses)
                else candidate
            )
    actual_title = (
        title
        if title is not None
        else (panels[0].title if len(panels) == 1 else "PIX Process Intelligence")
    )
    return VisualizationDocument(
        actual_title, tuple(panels), tuple(provenance), tuple(issues), status
    )


def _comparison_document(
    panels: tuple, sources: tuple, title: str
) -> VisualizationDocument:
    provenance = []
    issues = []
    status = "ok"
    panel_ids = tuple(panel.id for panel in panels)
    for index, source in enumerate(sources):
        provenance.extend(
            replace(item, panel_ids=panel_ids, input_path=(index,))
            for item in _source_metadata(source)
        )
        if isinstance(source, ComputationResult):
            issues.extend(f"{issue.code}: {issue.message}" for issue in source.issues)
            if source.status != ComputeStatus.COMPUTED:
                status = "partial"
        elif type(source) in get_args(Model):
            provenance.append(
                VisualProvenance(
                    model_digest=model_document(source)["model_digest"],
                    panel_ids=panel_ids,
                    input_path=(index,),
                )
            )
    return VisualizationDocument(
        title, panels, tuple(provenance), tuple(issues), status
    )


def build_model_visualization(
    model: object,
    *,
    annotations: ComputationResult | None = None,
    metric: str | None = None,
    title: str | None = None,
) -> VisualizationDocument:
    """Show a native model, optionally with explicitly bound recorded diagnostics."""
    if type(model) not in get_args(Model) and not isinstance(model, ModelArtifact):
        raise TypeError("model must be a native model or ModelArtifact")
    if annotations is None:
        if metric is not None:
            raise ValueError("metric requires an annotations result")
        return build_visualization(model, title=title)
    if not isinstance(annotations, ComputationResult):
        raise TypeError("annotations must be a ComputationResult")
    if type(metric) is not str or not metric:
        raise ValueError("choose an explicit annotation metric")
    from .visual_annotations import model_annotation_panels

    panels = model_annotation_panels(model, annotations, metric=metric)
    return _comparison_document(
        panels, (model, annotations), "Model diagnostics" if title is None else title
    )


def compare_footprints(
    left: object, right: object, *, symmetric: bool = False, title: str | None = None
) -> VisualizationDocument:
    """Compare supplied footprint relations; source alphabets and unknowns stay explicit."""
    if type(symmetric) is not bool:
        raise TypeError("symmetric must be bool")
    from .visual_annotations import footprint_comparison_panels

    panels = footprint_comparison_panels(left, right, symmetric=symmetric)
    return _comparison_document(
        panels, (left, right), "Footprint comparison" if title is None else title
    )


def build_variant_duration(
    statistics: ComputationResult,
    performance: ComputationResult,
    *,
    title: str | None = None,
) -> VisualizationDocument:
    """Pair matching populations explicitly; path geometry is not elapsed time."""
    if not isinstance(statistics, ComputationResult) or not isinstance(
        performance, ComputationResult
    ):
        raise TypeError(
            "statistics and performance must be original ComputationResult values"
        )
    from .visual_case_adapters import variant_duration_panels

    panels = variant_duration_panels(
        statistics.value,
        performance.value,
        statistics_source=statistics,
        performance_source=performance,
    )
    return _comparison_document(
        panels,
        (statistics, performance),
        "Variant duration" if title is None else title,
    )


def visualization_json_bytes(document: VisualizationDocument) -> bytes:
    from .visual_serialization import dumps_visualization

    return dumps_visualization(document).encode("utf-8")


def read_visualization(path: str | os.PathLike[str]) -> VisualizationDocument:
    from .visual_serialization import loads_visualization

    return loads_visualization(Path(path).read_bytes())


def write_visualization(
    document: VisualizationDocument,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> FilePublication:
    """Atomically publish lossless visual data; this is not an analysis result file."""
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    from .visual_serialization import loads_visualization

    payload = visualization_json_bytes(document)
    if loads_visualization(payload) != document:
        raise ValueError("visualization does not preserve its contract on round trip")
    return publish_bytes(
        payload,
        path,
        overwrite=overwrite,
        prefix=".pix-visual-",
    )


__all__ = (
    "UnsupportedVisualizationError",
    "build_visualization",
    "build_model_visualization",
    "compare_footprints",
    "build_variant_duration",
    "visualization_json_bytes",
    "read_visualization",
    "write_visualization",
)
