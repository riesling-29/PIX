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


def test_offline_export_includes_original_evidence_and_no_remote_assets():
    html = render_html(sample_graph())
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
    assert provenance["provenance"]["version"] == "0.12.0"
    assert "Eclipse Public License" in provenance["license"]


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
    assert len([tag for tag, _ in tags.tags if tag == "script"]) == 5


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
