"""Self-contained read-only HTML export; no server or runtime CDN is required."""

from __future__ import annotations

import html
import json
import os
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path

from pix._publication import FilePublication, publish_bytes
from pix.contracts.graph import GraphDocument, ModelGraphDocument

from .visual_contracts import VisualizationDocument
from .visual_serialization import visual_to_dict


def _asset(name: str) -> str:
    return (
        files("pix.viewer")
        .joinpath("assets", *name.split("/"))
        .read_text(encoding="utf-8")
    )


def _script_safe(text: str) -> str:
    """HTML raw-text elements must not see source data as markup."""
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _check_browser_integers(value: object) -> None:
    """Reject loss of integer identity at the JavaScript number boundary."""
    if type(value) is int and abs(value) > 2**53 - 1:
        raise ValueError(
            "graph integer exceeds the browser's exact integer range; "
            "export the native model JSON to preserve this value"
        )
    if isinstance(value, dict):
        for item in value.values():
            _check_browser_integers(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _check_browser_integers(item)


_GRAPHVIZ_SCRIPTS = ("vendor/viz-global.js", "graphviz_geometry.js")


def _script_elements(names: tuple[str, ...]) -> str:
    scripts = []
    for name in names:
        source = _asset(name)
        if "</script" in source.lower():
            raise ValueError(f"packaged script contains an unsafe terminator: {name}")
        scripts.append("<script>\n" + source + "\n</script>")
    return "".join(scripts)


def _license_element(layout_engine: str) -> str:
    if layout_engine == "native":
        return ""
    if layout_engine == "graphviz":
        data = {
            "provenance": json.loads(_asset("vendor/graphviz-provenance.json")),
            "license": _asset("vendor/GRAPHVIZ-LICENSE.txt"),
            "viz_license": _asset("vendor/VIZ-LICENSE.txt"),
            "expat_license": _asset("vendor/EXPAT-LICENSE.txt"),
        }
    else:
        data = {
            "provenance": json.loads(_asset("vendor/provenance.json")),
            "license": _asset("vendor/ELK-LICENSE.md"),
        }
    payload = _script_safe(json.dumps(data, ensure_ascii=False))
    return (
        '<script id="pix-viewer-license" type="application/json">'
        + payload
        + "</script>"
    )


def _render_visualization_html(
    document: VisualizationDocument,
    *,
    layout_engine: str,
    chevron_orientation: str,
    chevron_style: str,
) -> str:
    """Panel views use Graphviz by default and PIX's SVG interactions."""
    data = visual_to_dict(document)
    _check_browser_integers(data)
    payload = _script_safe(json.dumps(data, ensure_ascii=False, allow_nan=False))
    names = ("native_geometry.js",)
    if layout_engine == "graphviz":
        names += _GRAPHVIZ_SCRIPTS
    scripts = _script_elements((*names, "chevron_geometry.js", "visualization.js"))
    license_data = _license_element(layout_engine)
    css = _asset("visualization.css")
    if "</style" in css.lower():
        raise ValueError("packaged stylesheet contains an unsafe terminator")
    title = html.escape(document.title, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><main id="pix-viewer"></main>
<noscript>Enable JavaScript to explore this offline visualization.</noscript>
<script id="pix-visualization-data" type="application/json">{payload}</script>
{license_data}
{scripts}
<script>
window.pixVisualization = PIXVisualization.mount(
  document.getElementById("pix-viewer"),
  JSON.parse(document.getElementById("pix-visualization-data").textContent),
  {{layoutEngine: "{layout_engine}", chevronOrientation: "{chevron_orientation}", chevronStyle: "{chevron_style}"}}
);
window.pixViewerReady = window.pixVisualization.ready;
</script>
</body></html>
"""


def render_html(
    graph: GraphDocument | ModelGraphDocument | VisualizationDocument,
    *,
    layout_engine: str = "graphviz",
    chevron_orientation: str = "horizontal",
    chevron_style: str = "neutral",
) -> str:
    """Render graph evidence into an offline, self-contained HTML document.

    The full graph evidence is included in the file, including hidden types.
    Browser visibility is presentation only and does not redact this artifact.
    Graphviz is bundled as WebAssembly: neither a system ``dot`` installation
    nor a network connection is required. Select ``native`` explicitly for the
    experimental VisualizationDocument layout, or ``elk`` for legacy graph
    documents. A layout failure is shown without silently changing engines.
    Chevron panels flow horizontally by default. Select ``vertical`` explicitly,
    or ``auto`` to let the viewport determine their orientation. The default
    ``neutral`` style uses a monochrome presentation; select ``classic`` for
    object-type colors. Style applies only to Chevron panels and has no effect
    on legacy graph documents. Nonhorizontal Chevron orientation requires a
    VisualizationDocument. These options do not change domain data.
    """
    if type(layout_engine) is not str:
        raise TypeError("layout_engine must be a string")
    if layout_engine not in ("graphviz", "native", "elk"):
        raise ValueError("layout_engine must be 'graphviz', 'native' or 'elk'")
    if type(chevron_orientation) is not str:
        raise TypeError("chevron_orientation must be a string")
    if chevron_orientation not in ("horizontal", "vertical", "auto"):
        raise ValueError(
            "chevron_orientation must be 'horizontal', 'vertical' or 'auto'"
        )
    if type(chevron_style) is not str:
        raise TypeError("chevron_style must be a string")
    if chevron_style not in ("classic", "neutral"):
        raise ValueError("chevron_style must be 'classic' or 'neutral'")
    if isinstance(graph, VisualizationDocument):
        if layout_engine == "elk":
            raise ValueError("layout_engine='elk' requires a legacy graph document")
        return _render_visualization_html(
            graph,
            layout_engine=layout_engine,
            chevron_orientation=chevron_orientation,
            chevron_style=chevron_style,
        )
    if not isinstance(graph, (GraphDocument, ModelGraphDocument)):
        raise TypeError(
            "graph must be GraphDocument, ModelGraphDocument or VisualizationDocument"
        )
    if layout_engine == "native":
        raise ValueError("layout_engine='native' requires VisualizationDocument")
    if chevron_orientation != "horizontal":
        raise ValueError(
            "nonhorizontal chevron_orientation requires VisualizationDocument"
        )
    data = asdict(graph)
    is_model = isinstance(graph, ModelGraphDocument)
    data["schema"] = "pix.model-graph" if is_model else "pix.process-graph"
    data["schema_version"] = "1.0"
    if not is_model:
        for node in data["nodes"]:
            node["event_count"] = len(node["event_ids"])
            node["object_count"] = len(node["object_ids"])
    _check_browser_integers(data)
    payload = _script_safe(json.dumps(data, ensure_ascii=False, allow_nan=False))
    license_data = _license_element(layout_engine)
    css = _asset("viewer.css") + "\n" + _asset("model.css")
    if "</style" in css.lower():
        raise ValueError("packaged stylesheet contains an unsafe terminator")
    names = (
        (
            "native_geometry.js",
            *_GRAPHVIZ_SCRIPTS,
            "layout.js",
            "legacy_graphviz.js",
        )
        if layout_engine == "graphviz"
        else ("vendor/elk.bundled.js", "layout.js")
    )
    scripts = _script_elements((*names, "viewer.js"))
    title = html.escape(graph.title, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div id="pix-viewer"></div>
<noscript>This graph needs JavaScript for its local layout and interactions.</noscript>
<script id="pix-graph-data" type="application/json">{payload}</script>
{license_data}
<script>window.PIXViewerLayoutEngine = "{layout_engine}";</script>
{scripts}
</body></html>
"""


def export_html_report(
    graph: GraphDocument | ModelGraphDocument | VisualizationDocument,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    layout_engine: str = "graphviz",
    chevron_orientation: str = "horizontal",
    chevron_style: str = "neutral",
) -> FilePublication:
    """Publish HTML and return its identity and any post-commit cleanup issues."""
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    rendered = render_html(
        graph,
        layout_engine=layout_engine,
        chevron_orientation=chevron_orientation,
        chevron_style=chevron_style,
    ).encode("utf-8")
    return publish_bytes(rendered, path, overwrite=overwrite, prefix=".pix-viewer-")


def export_html(
    graph: GraphDocument | ModelGraphDocument | VisualizationDocument,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
    layout_engine: str = "graphviz",
    chevron_orientation: str = "horizontal",
    chevron_style: str = "neutral",
) -> Path:
    """Publish atomically, preserving the Path-returning convenience API.

    This convenience API intentionally returns the path only. Use
    export_html_report for the file identity and structured cleanup result.
    Cleanup failure after commit does not raise, even with warnings-as-errors.
    Publication failures preserve the primary exception and its cleanup_issues.
    """
    export_html_report(
        graph,
        path,
        overwrite=overwrite,
        layout_engine=layout_engine,
        chevron_orientation=chevron_orientation,
        chevron_style=chevron_style,
    )
    return Path(path)


__all__ = ("export_html", "export_html_report", "render_html")
