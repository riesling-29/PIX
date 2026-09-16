import json
import re
import warnings
from dataclasses import replace
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pix.viewer import (
    export_html,
    export_html_report,
    render_html,
)

from .test_graph import sample_graph


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def extract_payload(html, id="pix-graph-data"):
    return json.loads(
        re.search(
            rf'<script id="{id}" type="application/json">(.*?)</script>', html, re.S
        ).group(1)
    )


@pytest.mark.parametrize("engine", ["graphviz", "elk"])
def test_offline_export_includes_original_evidence_and_no_remote_assets(engine):
    html = render_html(sample_graph(), layout_engine=engine)
    payload = extract_payload(html)
    assert payload["schema"] == "pix.process-graph"
    assert payload["edges"][0]["counts"] == {
        "event_pairs": 1,
        "unique_objects": 2,
        "occurrences": 2,
    }
    assert payload["nodes"][0]["event_count"] == 1
    tags = Tags()
    tags.feed(html)
    assert not any("src" in attrs or tag == "link" for tag, attrs in tags.tags)
    provenance = extract_payload(html, "pix-viewer-license")
    if engine == "graphviz":
        assert provenance["provenance"]["package"]["name"] == "@viz-js/viz"
        assert "MIT License" in provenance["viz_license"]
    else:
        assert provenance["provenance"]["version"] == "0.12.0"
    assert "Eclipse Public License" in provenance["license"]
    assert f'window.PIXViewerLayoutEngine = "{engine}"' in html


def test_html_breakout_and_unicode_preserve_data_without_creating_tags():
    hostile = (
        '</script><img src=x onerror="globalThis.pwned=1">한글 😀 &\u2028\u2029\x00'
    )
    graph = replace(sample_graph(hostile), title="</title><script>pwned=1</script>")
    html = render_html(graph)
    assert hostile not in html
    assert extract_payload(html)["nodes"][0]["label"] == hostile
    tags = Tags()
    tags.feed(html)
    assert not any(tag == "img" for tag, _ in tags.tags)
    original = Tags()
    original.feed(render_html(sample_graph()))
    assert [tag for tag, _ in tags.tags if tag == "script"] == [
        tag for tag, _ in original.tags if tag == "script"
    ]


def test_default_graphviz_keeps_the_existing_graph_ui_and_selectors():
    html = render_html(sample_graph())
    assert 'window.PIXViewerLayoutEngine = "graphviz"' in html
    assert 'id="pix-graph-data"' in html
    assert 'id="pix-visualization-data"' not in html
    assert "PIXLegacyGraphviz" in html
    assert "elk.bundled" not in html
    assert extract_payload(html)["object_types"] == ["Order"]
    assert html.index("root.PIXLayout = api") < html.index(
        "root.PIXLegacyGraphviz = factory(root.PIXLayout)"
    )


def test_export_no_clobber_and_explicit_replace(tmp_path):
    path = tmp_path / "graph.html"
    assert export_html(sample_graph(), path) == path
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        export_html(sample_graph("Changed"), path)
    assert path.read_bytes() == original
    export_html(sample_graph("Changed"), path, overwrite=True)
    assert (
        extract_payload(path.read_text(encoding="utf-8"))["nodes"][0]["label"]
        == "Changed"
    )
    assert list(tmp_path.iterdir()) == [path]


def test_publish_race_preserves_winning_file_and_cleans_only_own_temp(
    tmp_path, monkeypatch
):
    import pix.viewer.export as module

    path = tmp_path / "graph.html"
    keep = tmp_path / ".graph.html.user.tmp"
    keep.write_text("retain", encoding="utf-8")
    original_link = module.os.link

    def race(source, target):
        path.write_text("other writer", encoding="utf-8")
        original_link(source, target)

    monkeypatch.setattr(module.os, "link", race)
    with pytest.raises(FileExistsError):
        export_html(sample_graph(), path)
    assert path.read_text(encoding="utf-8") == "other writer"
    assert set(tmp_path.iterdir()) == {path, keep}


def test_type_errors_do_not_create_artifacts(tmp_path):
    path = tmp_path / "bad.html"
    with pytest.raises(TypeError):
        export_html({}, path)
    with pytest.raises(TypeError):
        export_html(sample_graph(), path, overwrite="yes")
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "engine,error",
    [
        (None, TypeError),
        (True, TypeError),
        ([], TypeError),
        ("", ValueError),
        ("dot", ValueError),
        ('graphviz";alert(1)', ValueError),
        ("native", ValueError),
    ],
)
def test_invalid_legacy_engine_rejects_before_publication(tmp_path, engine, error):
    with pytest.raises(error, match="layout_engine"):
        export_html(sample_graph(), tmp_path / "graph.html", layout_engine=engine)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("exporter", [export_html, export_html_report])
def test_publication_wrapper_honors_explicit_elk(tmp_path, exporter):
    path = tmp_path / "elk.html"
    exporter(sample_graph(), path, layout_engine="elk")
    html = path.read_text(encoding="utf-8")
    assert 'window.PIXViewerLayoutEngine = "elk"' in html
    assert extract_payload(html, "pix-viewer-license")["provenance"]["package"] == (
        "elkjs"
    )


def test_missing_graphviz_asset_does_not_fall_back_or_replace_file(
    tmp_path, monkeypatch
):
    import pix.viewer.export as module

    target = tmp_path / "graph.html"
    target.write_text("existing report", encoding="utf-8")
    original_asset = module._asset

    def missing(name):
        if name == "vendor/viz-global.js":
            raise FileNotFoundError("Graphviz bundle unavailable")
        return original_asset(name)

    monkeypatch.setattr(module, "_asset", missing)
    with pytest.raises(FileNotFoundError, match="Graphviz bundle unavailable"):
        export_html(sample_graph(), target, overwrite=True)
    assert target.read_text(encoding="utf-8") == "existing report"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("asset", ["graphviz_geometry.js", "viewer.css"])
def test_packaged_raw_text_terminator_rejects_before_publication(
    tmp_path, monkeypatch, asset
):
    import pix.viewer.export as module

    original_asset = module._asset

    def unsafe(name):
        if name == asset:
            return "</style><script>bad()</script>"
        return original_asset(name)

    monkeypatch.setattr(module, "_asset", unsafe)
    with pytest.raises(ValueError, match="unsafe terminator"):
        export_html(sample_graph(), tmp_path / "graph.html")
    assert not list(tmp_path.iterdir())


def test_empty_graph_and_long_labels_export_without_layout_dependency(tmp_path):
    graph = replace(sample_graph(), nodes=(), edges=(), title="분석" * 1000)
    path = export_html(graph, tmp_path / "empty.html")
    assert extract_payload(path.read_text(encoding="utf-8"))["nodes"] == []


def test_publication_report_distinguishes_success_from_cleanup_failure(
    tmp_path, monkeypatch
):
    original_unlink = Path.unlink

    def fail_own_cleanup(path, *args, **kwargs):
        if path.name.startswith(".pix-viewer-"):
            raise PermissionError("temporary file retained")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_own_cleanup)
    path = tmp_path / "saved.html"
    publication = export_html_report(sample_graph(), path)
    assert path.exists()
    assert publication.path == path
    assert publication.byte_count == path.stat().st_size
    assert publication.output_sha256 == sha256(path.read_bytes()).hexdigest()
    assert len(publication.cleanup_issues) == 1
    assert publication.cleanup_issues[0].path.exists()
    assert "retained" in publication.cleanup_issues[0].message


def test_path_wrapper_returns_after_commit_even_with_warnings_as_errors(
    tmp_path, monkeypatch
):
    def fail_cleanup(path, *args, **kwargs):
        raise PermissionError("cleanup denied")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    path = tmp_path / "saved.html"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert export_html(sample_graph(), path) == path
    assert path.exists()


def test_primary_publication_failure_survives_cleanup_failure(tmp_path, monkeypatch):
    import pix._publication as module

    def fail_link(source, target):
        raise PermissionError("primary publication failure")

    def fail_cleanup(path, *args, **kwargs):
        raise OSError("secondary cleanup failure")

    monkeypatch.setattr(module.os, "link", fail_link)
    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    path = tmp_path / "not-published.html"
    with pytest.raises(PermissionError, match="primary publication failure") as caught:
        export_html_report(sample_graph(), path)
    assert not path.exists()
    assert len(caught.value.cleanup_issues) == 1
    assert "secondary cleanup" in caught.value.cleanup_issues[0].message
