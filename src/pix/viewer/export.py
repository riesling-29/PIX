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


def render_html(graph: GraphDocument | ModelGraphDocument) -> str:
    """Render graph evidence into an offline, self-contained HTML document.

    The full graph evidence is included in the file, including hidden types.
    Browser visibility is presentation only and does not redact this artifact.
    """
    if not isinstance(graph, (GraphDocument, ModelGraphDocument)):
        raise TypeError("graph must be GraphDocument or ModelGraphDocument")
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
    license_data = _script_safe(
        json.dumps(
            {
                "provenance": json.loads(_asset("vendor/provenance.json")),
                "license": _asset("vendor/ELK-LICENSE.md"),
            },
            ensure_ascii=False,
        )
    )
    css = _asset("viewer.css") + "\n" + _asset("model.css")
    scripts = []
    for name in ("vendor/elk.bundled.js", "layout.js", "viewer.js"):
        source = _asset(name)
        # Packaged code is trusted, but cannot terminate an HTML script element.
        if "</script" in source.lower():
            raise ValueError(f"packaged script contains an unsafe terminator: {name}")
        scripts.append("<script>\n" + source + "\n</script>")
    title = html.escape(graph.title, quote=True)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><div id="pix-viewer"></div>
<noscript>This graph needs JavaScript for its local layout and interactions.</noscript>
<script id="pix-graph-data" type="application/json">{payload}</script>
<script id="pix-viewer-license" type="application/json">{license_data}</script>
{"".join(scripts)}
</body></html>
"""


def export_html_report(
    graph: GraphDocument | ModelGraphDocument,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> FilePublication:
    """Publish HTML and return its identity and any post-commit cleanup issues."""
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    rendered = render_html(graph).encode("utf-8")
    return publish_bytes(rendered, path, overwrite=overwrite, prefix=".pix-viewer-")


def export_html(
    graph: GraphDocument | ModelGraphDocument,
    path: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> Path:
    """Publish atomically, preserving the Path-returning convenience API.

    This convenience API intentionally returns the path only. Use
    export_html_report for the file identity and structured cleanup result.
    Cleanup failure after commit does not raise, even with warnings-as-errors.
    Publication failures preserve the primary exception and its cleanup_issues.
    """
    export_html_report(graph, path, overwrite=overwrite)
    return Path(path)


__all__ = ("export_html", "export_html_report", "render_html")
