"""Strict deterministic JSON codec for ``pix.visualization.v1``.

No evaluation, dynamic imports or type-name construction is used. Unknown
fields, kinds, duplicate JSON keys and nonfinite numeric values are errors.
"""

from __future__ import annotations

import json
from dataclasses import fields

from pix.viewer.visual_contracts import (
    ChartPanel,
    ChartPoint,
    ChartSeries,
    ChevronEvent,
    ChevronLane,
    ChevronPanel,
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    TimelineItem,
    TimelineLane,
    TimelinePanel,
    VisualEdge,
    VisualField,
    VisualizationDocument,
    VisualMetric,
    VisualNode,
    VisualProvenance,
)

_TYPES = (
    ChartPanel,
    ChartPoint,
    ChartSeries,
    ChevronEvent,
    ChevronLane,
    ChevronPanel,
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    TimelineItem,
    TimelineLane,
    TimelinePanel,
    VisualEdge,
    VisualField,
    VisualizationDocument,
    VisualMetric,
    VisualNode,
    VisualProvenance,
)
_PANELS = {
    "graph": GraphPanel,
    "matrix": MatrixPanel,
    "chart": ChartPanel,
    "timeline": TimelinePanel,
    "chevron": ChevronPanel,
    "table": TablePanel,
}
_NESTED = {
    (VisualNode, "metrics"): VisualMetric,
    (VisualEdge, "metrics"): VisualMetric,
    (GraphPanel, "nodes"): VisualNode,
    (GraphPanel, "edges"): VisualEdge,
    (MatrixPanel, "cells"): MatrixCell,
    (MatrixPanel, "legend"): VisualField,
    (ChartSeries, "points"): ChartPoint,
    (ChartPanel, "series"): ChartSeries,
    (TimelinePanel, "lanes"): TimelineLane,
    (TimelinePanel, "items"): TimelineItem,
    (ChevronPanel, "lanes"): ChevronLane,
    (ChevronPanel, "events"): ChevronEvent,
    (VisualizationDocument, "provenance"): VisualProvenance,
}
for _owner in (
    VisualNode,
    VisualEdge,
    MatrixCell,
    ChartPoint,
    TimelineItem,
    ChevronLane,
    ChevronEvent,
    VisualProvenance,
):
    _NESTED[(_owner, "details")] = VisualField
_SCALAR_LISTS = {
    (MatrixPanel, "rows"),
    (MatrixPanel, "columns"),
    (TablePanel, "columns"),
    (ChevronEvent, "lane_ids"),
    (VisualizationDocument, "issues"),
    (VisualProvenance, "panel_ids"),
    (VisualProvenance, "input_path"),
}


def _list(value: object, name: str) -> list:
    if type(value) is not list:
        raise TypeError(f"{name} must be a JSON array")
    return value


def _decode(cls: type, value: object) -> object:
    if type(value) is not dict:
        raise TypeError(f"{cls.__name__} must be a JSON object")
    if any(type(key) is not str for key in value):
        raise TypeError(f"{cls.__name__} keys must be strings")
    expected = {item.name for item in fields(cls)}
    if value.keys() != expected:
        missing = sorted(expected - value.keys())
        unknown = sorted(str(key) for key in value.keys() - expected)
        raise ValueError(
            f"{cls.__name__} fields differ: missing={missing}, unknown={unknown}"
        )
    kwargs = {}
    for item in fields(cls):
        raw = value[item.name]
        if not item.init:
            if type(raw) is not str or raw != item.default:
                raise ValueError(f"unsupported {item.name}: expected {item.default!r}")
            continue
        owner_field = (cls, item.name)
        if owner_field in _NESTED:
            child = _NESTED[owner_field]
            kwargs[item.name] = tuple(
                _decode(child, entry) for entry in _list(raw, item.name)
            )
        elif owner_field in _SCALAR_LISTS:
            kwargs[item.name] = tuple(_list(raw, item.name))
        elif owner_field == (TablePanel, "rows"):
            kwargs[item.name] = tuple(
                tuple(_list(row, "table row")) for row in _list(raw, "table rows")
            )
        elif owner_field == (VisualizationDocument, "panels"):
            panels = []
            for panel in _list(raw, "panels"):
                if type(panel) is not dict or type(panel.get("kind")) is not str:
                    raise TypeError("each panel must be an object with a string kind")
                kind = panel["kind"]
                if kind not in _PANELS:
                    raise ValueError(f"unsupported visualization panel kind: {kind!r}")
                panels.append(_decode(_PANELS[kind], panel))
            kwargs[item.name] = tuple(panels)
        else:
            kwargs[item.name] = raw
    return cls(**kwargs)


def _encode(value: object) -> object:
    if type(value) in _TYPES:
        return {item.name: _encode(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_encode(item) for item in value]
    if type(value) in (str, int, float, bool, type(None)):
        return value
    raise TypeError(f"unsupported visualization value type: {type(value).__name__}")


def visual_from_dict(value: dict) -> VisualizationDocument:
    """Validate a complete JSON-shaped dictionary; defaults must be explicit."""
    return _decode(VisualizationDocument, value)


def visual_to_dict(document: VisualizationDocument) -> dict:
    """Return independent JSON primitives, revalidating even forged instances."""
    if type(document) is not VisualizationDocument:
        raise TypeError("expected VisualizationDocument")
    try:
        encoded = _encode(document)
        visual_from_dict(encoded)
    except RecursionError as exc:
        raise ValueError("cyclic or excessively nested visualization data") from exc
    return encoded


def dumps_visualization(
    document: VisualizationDocument, *, indent: int | None = None
) -> str:
    """Stable sorted-key JSON; insertion order of all panel data is preserved."""
    if indent is not None and (type(indent) is not int or not 0 <= indent <= 8):
        raise ValueError("indent must be None or an integer between 0 and 8")
    return json.dumps(
        visual_to_dict(document),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":") if indent is None else None,
        indent=indent,
    )


def _object_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON number: {value}")


def loads_visualization(
    text: str | bytes,
    *,
    max_bytes: int = 64 * 1024 * 1024,
) -> VisualizationDocument:
    """Read bounded UTF-8 JSON without accepting duplicate or extension values.

    The byte budget bounds input only, not runtime memory. Raise it explicitly
    for intentionally large documents; no panels or observations are truncated.
    """
    if type(text) not in (str, bytes):
        raise TypeError("visualization JSON must be str or UTF-8 bytes")
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("max_bytes must be a positive integer")
    try:
        if type(text) is bytes:
            size = len(text)
            if size > max_bytes:
                raise ValueError("visualization JSON exceeds max_bytes")
            text = text.decode("utf-8")
        else:
            size = len(text.encode("utf-8"))
        if size > max_bytes:
            raise ValueError("visualization JSON exceeds max_bytes")
        value = json.loads(
            text, object_pairs_hook=_object_pairs, parse_constant=_reject_constant
        )
        return visual_from_dict(value)
    except RecursionError as exc:
        raise ValueError("excessively nested visualization JSON") from exc
    except UnicodeError as exc:
        raise ValueError("visualization JSON must be valid UTF-8") from exc
