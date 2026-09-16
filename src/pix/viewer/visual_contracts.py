"""Immutable, renderer-neutral visualization data, without analysis assertions.

These additive contracts deliberately do not relax GraphDocument or
ModelGraphDocument. Pixel positions, HTML, executable callbacks and arbitrary objects
are not part of this interchange format.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import TypeAlias

VisualScalar: TypeAlias = str | int | float | bool | None

_CHART_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


def _text(value: object, name: str, *, nonempty: bool = False) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if nonempty and not value.strip():
        raise ValueError(f"{name} must not be empty")
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{name} must not contain unpaired Unicode surrogates")


def _optional_text(value: object, name: str) -> None:
    if value is not None:
        _text(value, name, nonempty=True)


def _number(value: object, name: str, *, nullable: bool = False) -> None:
    if nullable and value is None:
        return
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a number; booleans are not numbers")
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _scalar(value: object, name: str) -> None:
    if type(value) not in (str, int, float, bool, type(None)):
        raise TypeError(f"{name} must be a primitive scalar")
    if type(value) is float and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if type(value) is str:
        _text(value, name)


def _tuple(value: object, item_type: type, name: str) -> None:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be a tuple")
    if any(type(item) is not item_type for item in value):
        raise TypeError(f"{name} must contain only {item_type.__name__}")


def _unique(values: tuple[str, ...], name: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{name} must be unique")


def _choice(value: object, choices: tuple[str, ...], name: str) -> None:
    _text(value, name)
    if value not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}")


def _panel(panel_id: str, title: str, description: str) -> None:
    _text(panel_id, "panel id", nonempty=True)
    _text(title, "panel title")
    _text(description, "panel description")


@dataclass(frozen=True, slots=True)
class VisualField:
    name: str
    value: VisualScalar

    def __post_init__(self) -> None:
        _text(self.name, "field name", nonempty=True)
        _scalar(self.value, "field value")


def _fields(value: object, name: str) -> None:
    _tuple(value, VisualField, name)
    _unique(tuple(item.name for item in value), f"{name} names")


@dataclass(frozen=True, slots=True)
class VisualMetric:
    name: str
    value: int | float | None
    unit: str

    def __post_init__(self) -> None:
        _text(self.name, "metric name", nonempty=True)
        _number(self.value, "metric value", nullable=True)
        _text(self.unit, "metric unit", nonempty=True)


def _metrics(value: object) -> None:
    _tuple(value, VisualMetric, "metrics")
    _unique(tuple(item.name for item in value), "metric names")


@dataclass(frozen=True, slots=True)
class VisualNode:
    id: str
    label: str
    kind: str = "activity"
    group: str | None = None
    metrics: tuple[VisualMetric, ...] = ()
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "node id", nonempty=True)
        _text(self.label, "node label")
        _text(self.kind, "node kind", nonempty=True)
        _optional_text(self.group, "node group")
        _metrics(self.metrics)
        _fields(self.details, "node details")


@dataclass(frozen=True, slots=True)
class VisualEdge:
    id: str
    source: str
    target: str
    label: str = ""
    kind: str = "flow"
    directed: bool = True
    metrics: tuple[VisualMetric, ...] = ()
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "source", "target", "kind"):
            _text(getattr(self, name), f"edge {name}", nonempty=True)
        _text(self.label, "edge label")
        if type(self.directed) is not bool:
            raise TypeError("edge directed must be a boolean")
        _metrics(self.metrics)
        _fields(self.details, "edge details")


@dataclass(frozen=True, slots=True)
class GraphPanel:
    id: str
    title: str
    nodes: tuple[VisualNode, ...] = ()
    edges: tuple[VisualEdge, ...] = ()
    layout: str = "layered"
    description: str = ""
    kind: str = field(default="graph", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        _tuple(self.nodes, VisualNode, "nodes")
        _tuple(self.edges, VisualEdge, "edges")
        _unique(tuple(node.id for node in self.nodes), "node ids")
        _unique(tuple(edge.id for edge in self.edges), "edge ids")
        _choice(self.layout, ("layered", "tree", "force", "bipartite"), "layout")
        node_ids = {node.id for node in self.nodes}
        if any(
            edge.source not in node_ids or edge.target not in node_ids
            for edge in self.edges
        ):
            raise ValueError("every edge endpoint must reference a node in its panel")
        units: dict[str, str] = {}
        for item in (*self.nodes, *self.edges):
            for metric in item.metrics:
                if metric.name in units and units[metric.name] != metric.unit:
                    raise ValueError(f"incompatible units for metric {metric.name!r}")
                units[metric.name] = metric.unit


@dataclass(frozen=True, slots=True)
class MatrixCell:
    row: str
    column: str
    value: VisualScalar
    kind: str = "value"
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        _text(self.row, "matrix row", nonempty=True)
        _text(self.column, "matrix column", nonempty=True)
        _scalar(self.value, "matrix value")
        _text(self.kind, "matrix cell kind", nonempty=True)
        _fields(self.details, "matrix cell details")


@dataclass(frozen=True, slots=True)
class MatrixPanel:
    id: str
    title: str
    rows: tuple[str, ...]
    columns: tuple[str, ...]
    cells: tuple[MatrixCell, ...] = ()
    legend: tuple[VisualField, ...] = ()
    unit: str | None = None
    description: str = ""
    kind: str = field(default="matrix", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        for name in ("rows", "columns"):
            values = getattr(self, name)
            _tuple(values, str, name)
            for value in values:
                _text(value, name, nonempty=True)
            _unique(values, name)
        _tuple(self.cells, MatrixCell, "matrix cells")
        coordinates = tuple((cell.row, cell.column) for cell in self.cells)
        if len(coordinates) != len(set(coordinates)):
            raise ValueError("matrix cell coordinates must be unique")
        rows, columns = set(self.rows), set(self.columns)
        if any(
            cell.row not in rows or cell.column not in columns for cell in self.cells
        ):
            raise ValueError("matrix cells must reference declared rows and columns")
        _fields(self.legend, "matrix legend")
        if self.cells and not self.legend:
            raise ValueError("a nonempty matrix requires an explicit semantic legend")
        _optional_text(self.unit, "matrix unit")


@dataclass(frozen=True, slots=True)
class ChartPoint:
    x: str | int | float
    y: int | float | None
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        if type(self.x) is str:
            _text(self.x, "point x")
        else:
            _number(self.x, "point x")
        _number(self.y, "point y", nullable=True)
        _fields(self.details, "point details")


@dataclass(frozen=True, slots=True)
class ChartSeries:
    name: str
    points: tuple[ChartPoint, ...] = ()
    group: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, "series name", nonempty=True)
        _tuple(self.points, ChartPoint, "series points")
        _optional_text(self.group, "series group")


@dataclass(frozen=True, slots=True)
class ChartPanel:
    id: str
    title: str
    chart_type: str
    series: tuple[ChartSeries, ...] = ()
    x_type: str = "category"
    x_label: str = ""
    y_label: str = ""
    x_unit: str | None = None
    y_unit: str | None = None
    description: str = ""
    kind: str = field(default="chart", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        _choice(self.chart_type, ("bar", "line", "scatter"), "chart type")
        _choice(self.x_type, ("category", "number", "time"), "x type")
        _tuple(self.series, ChartSeries, "chart series")
        _unique(tuple(series.name for series in self.series), "series names")
        _text(self.x_label, "x label")
        _text(self.y_label, "y label")
        _optional_text(self.x_unit, "x unit")
        _optional_text(self.y_unit, "y unit")
        for series in self.series:
            for point in series.points:
                if self.x_type == "number":
                    _number(point.x, "numeric chart x")
                else:
                    _text(point.x, "chart x")
                if self.x_type == "time":
                    if _CHART_TIMESTAMP.fullmatch(point.x) is None:
                        raise ValueError(
                            "time chart x requires YYYY-MM-DDTHH:MM:SS"
                            "[.1-6 fractional digits](Z|+/-HH:MM)"
                        )
                    try:
                        parsed = datetime.fromisoformat(point.x.replace("Z", "+00:00"))
                    except ValueError as exc:
                        raise ValueError(
                            "time chart x must be a valid RFC3339 timestamp"
                        ) from exc
                    if parsed.utcoffset() is None:
                        raise ValueError("time chart x requires an explicit timezone")


@dataclass(frozen=True, slots=True)
class TimelineLane:
    id: str
    label: str
    group: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "lane id", nonempty=True)
        _text(self.label, "lane label")
        _optional_text(self.group, "lane group")


@dataclass(frozen=True, slots=True)
class TimelineItem:
    id: str
    lane: str
    start: int | float
    end: int | float | None
    label: str = ""
    group: str | None = None
    status: str | None = None
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "timeline item id", nonempty=True)
        _text(self.lane, "timeline item lane", nonempty=True)
        _number(self.start, "timeline start")
        _number(self.end, "timeline end", nullable=True)
        if self.end is not None and self.end < self.start:
            raise ValueError("timeline end must not precede start")
        _text(self.label, "timeline label")
        _optional_text(self.group, "timeline group")
        _optional_text(self.status, "timeline status")
        _fields(self.details, "timeline details")


@dataclass(frozen=True, slots=True)
class TimelinePanel:
    id: str
    title: str
    lanes: tuple[TimelineLane, ...] = ()
    items: tuple[TimelineItem, ...] = ()
    axis_type: str = "relative"
    unit: str = "seconds"
    description: str = ""
    kind: str = field(default="timeline", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        _tuple(self.lanes, TimelineLane, "timeline lanes")
        _tuple(self.items, TimelineItem, "timeline items")
        _unique(tuple(lane.id for lane in self.lanes), "timeline lane ids")
        _unique(tuple(item.id for item in self.items), "timeline item ids")
        lane_ids = {lane.id for lane in self.lanes}
        if any(item.lane not in lane_ids for item in self.items):
            raise ValueError("timeline items must reference a declared lane")
        _choice(self.axis_type, ("relative", "timestamp"), "timeline axis type")
        _text(self.unit, "timeline unit", nonempty=True)
        if self.axis_type == "timestamp" and self.unit != "seconds":
            raise ValueError("timestamp timelines use Unix epoch seconds")


@dataclass(frozen=True, slots=True)
class ChevronLane:
    """One object instance, never an aggregation of an object type."""

    id: str
    label: str
    object_type: str
    object_id: str
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        for name in ("id", "object_type", "object_id"):
            _text(getattr(self, name), f"chevron lane {name}", nonempty=True)
        _text(self.label, "chevron lane label")
        _fields(self.details, "chevron lane details")


@dataclass(frozen=True, slots=True)
class ChevronEvent:
    """One shared event occupying the same inclusive layers in every lane."""

    id: str
    label: str
    start: int
    end: int
    lane_ids: tuple[str, ...]
    details: tuple[VisualField, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "chevron event id", nonempty=True)
        _text(self.label, "chevron event label")
        for name in ("start", "end"):
            value = getattr(self, name)
            if type(value) is not int:
                raise TypeError(f"chevron {name} must be an integer")
            if value < 0:
                raise ValueError(f"chevron {name} must be nonnegative")
        if self.end < self.start:
            raise ValueError("chevron inclusive end must not precede start")
        _tuple(self.lane_ids, str, "chevron event lane ids")
        if not self.lane_ids:
            raise ValueError("a chevron event requires at least one object lane")
        for lane_id in self.lane_ids:
            _text(lane_id, "chevron event lane id", nonempty=True)
        _unique(self.lane_ids, "chevron event lane ids")
        _fields(self.details, "chevron event details")


@dataclass(frozen=True, slots=True)
class ChevronPanel:
    """Object-instance chevrons on precedence layers, not elapsed-time bars."""

    id: str
    title: str
    lanes: tuple[ChevronLane, ...] = ()
    events: tuple[ChevronEvent, ...] = ()
    variant_id: str | None = None
    frequency: int | None = None
    population: int | None = None
    description: str = ""
    kind: str = field(default="chevron", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        _tuple(self.lanes, ChevronLane, "chevron lanes")
        _tuple(self.events, ChevronEvent, "chevron events")
        _unique(tuple(lane.id for lane in self.lanes), "chevron lane ids")
        _unique(tuple(lane.object_id for lane in self.lanes), "chevron object ids")
        _unique(tuple(event.id for event in self.events), "chevron event ids")
        lane_ids = {lane.id for lane in self.lanes}
        if any(
            lane_id not in lane_ids
            for event in self.events
            for lane_id in event.lane_ids
        ):
            raise ValueError("chevron events must reference declared object lanes")
        _optional_text(self.variant_id, "chevron variant id")
        if (self.frequency is None) != (self.population is None):
            raise ValueError(
                "chevron frequency and population must be provided together"
            )
        if self.frequency is not None:
            for name in ("frequency", "population"):
                if type(getattr(self, name)) is not int:
                    raise TypeError(f"chevron {name} must be an integer")
                if getattr(self, name) < 0:
                    raise ValueError(f"chevron {name} must be nonnegative")
            if self.population == 0 or not 0 < self.frequency <= self.population:
                raise ValueError("chevron frequency must be in 1..population")


@dataclass(frozen=True, slots=True)
class TablePanel:
    id: str
    title: str
    columns: tuple[str, ...]
    rows: tuple[tuple[VisualScalar, ...], ...] = ()
    description: str = ""
    kind: str = field(default="table", init=False)

    def __post_init__(self) -> None:
        _panel(self.id, self.title, self.description)
        _tuple(self.columns, str, "table columns")
        for column in self.columns:
            _text(column, "table column", nonempty=True)
        _unique(self.columns, "table columns")
        _tuple(self.rows, tuple, "table rows")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("table row width must match its columns")
            for value in row:
                _scalar(value, "table cell")


VisualPanel: TypeAlias = (
    GraphPanel | MatrixPanel | ChartPanel | TimelinePanel | ChevronPanel | TablePanel
)


@dataclass(frozen=True, slots=True)
class VisualProvenance:
    calculation_id: str | None = None
    source_digest: str | None = None
    model_digest: str | None = None
    operator_id: str | None = None
    status: str | None = None
    details: tuple[VisualField, ...] = ()
    panel_ids: tuple[str, ...] = ()
    input_path: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "calculation_id",
            "source_digest",
            "model_digest",
            "operator_id",
            "status",
        ):
            _optional_text(getattr(self, name), f"provenance {name}")
        _fields(self.details, "provenance details")
        _tuple(self.panel_ids, str, "provenance panel ids")
        for panel_id in self.panel_ids:
            _text(panel_id, "provenance panel id", nonempty=True)
        _unique(self.panel_ids, "provenance panel ids")
        _tuple(self.input_path, int, "provenance input path")
        if any(index < 0 for index in self.input_path):
            raise ValueError("provenance input path indices must be nonnegative")


@dataclass(frozen=True, slots=True)
class VisualizationDocument:
    title: str
    panels: tuple[VisualPanel, ...] = ()
    provenance: tuple[VisualProvenance, ...] = ()
    issues: tuple[str, ...] = ()
    status: str = "ok"
    schema: str = field(default="pix.visualization.v1", init=False)

    def __post_init__(self) -> None:
        _text(self.title, "document title")
        if type(self.panels) is not tuple or any(
            type(panel)
            not in (
                GraphPanel,
                MatrixPanel,
                ChartPanel,
                TimelinePanel,
                ChevronPanel,
                TablePanel,
            )
            for panel in self.panels
        ):
            raise TypeError("panels must be a tuple of supported visual panel types")
        _unique(tuple(panel.id for panel in self.panels), "panel ids")
        _tuple(self.provenance, VisualProvenance, "provenance")
        panel_ids = {panel.id for panel in self.panels}
        if any(
            panel_id not in panel_ids
            for source in self.provenance
            for panel_id in source.panel_ids
        ):
            raise ValueError("provenance panel ids must reference document panels")
        _tuple(self.issues, str, "issues")
        for issue in self.issues:
            _text(issue, "issue")
        _choice(
            self.status, ("ok", "partial", "unsupported", "error"), "document status"
        )
