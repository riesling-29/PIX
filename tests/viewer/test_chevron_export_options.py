"""Chevron presentation options preserve evidence and publication boundaries."""

from importlib.resources import files

import pytest

from pix.viewer import (
    ChevronEvent,
    ChevronLane,
    ChevronPanel,
    VisualizationDocument,
    build_model_graph,
    export_html,
    export_html_report,
    render_html,
)
from pix.viewer.visual_serialization import visual_to_dict

from .test_export import Tags, extract_payload
from .test_graph import sample_graph
from .test_model_graph import petri_fixture


def chevron_document():
    return VisualizationDocument(
        "Shared event presentation",
        (
            ChevronPanel(
                "variant-1",
                "Representative execution",
                (
                    ChevronLane("order", "Order:42", "Order", "42"),
                    ChevronLane("item", "Item:7", "Item", "7"),
                ),
                (
                    ChevronEvent("shared", "Start", 0, 0, ("order", "item")),
                    ChevronEvent("review", "Review", 1, 2, ("order",)),
                    ChevronEvent("inspect", "Inspect", 1, 1, ("item",)),
                ),
            ),
        ),
    )


@pytest.mark.parametrize("engine", ["graphviz", "native"])
@pytest.mark.parametrize("orientation", ["horizontal", "vertical", "auto"])
@pytest.mark.parametrize("style", ["classic", "neutral"])
def test_options_reach_mount_without_changing_shared_event_evidence(
    engine, orientation, style
):
    document = chevron_document()
    rendered = render_html(
        document,
        layout_engine=engine,
        chevron_orientation=orientation,
        chevron_style=style,
    )
    assert f'chevronOrientation: "{orientation}"' in rendered
    assert f'chevronStyle: "{style}"' in rendered
    assert extract_payload(rendered, "pix-visualization-data") == visual_to_dict(
        document
    )
    geometry = (
        files("pix.viewer")
        .joinpath("assets", "chevron_geometry.js")
        .read_text(encoding="utf-8")
    )
    renderer = (
        files("pix.viewer")
        .joinpath("assets", "visualization.js")
        .read_text(encoding="utf-8")
    )
    assert rendered.index(geometry) < rendered.index(renderer)
    tags = Tags()
    tags.feed(rendered)
    assert not any("src" in attrs or tag == "link" for tag, attrs in tags.tags)


@pytest.mark.parametrize("exporter", [render_html, export_html, export_html_report])
def test_all_public_apis_default_to_horizontal_neutral(tmp_path, exporter):
    document = chevron_document()
    if exporter is render_html:
        rendered = exporter(document, layout_engine="native")
    else:
        target = tmp_path / "default.html"
        exporter(document, target, layout_engine="native")
        rendered = target.read_text(encoding="utf-8")
    assert 'chevronOrientation: "horizontal"' in rendered
    assert 'chevronStyle: "neutral"' in rendered
    assert extract_payload(rendered, "pix-visualization-data") == visual_to_dict(
        document
    )


@pytest.mark.parametrize("exporter", [export_html, export_html_report])
@pytest.mark.parametrize("style", ["classic", "neutral"])
def test_publication_wrappers_forward_both_options(tmp_path, exporter, style):
    target = tmp_path / "vertical.html"
    result = exporter(
        chevron_document(),
        target,
        layout_engine="native",
        chevron_orientation="vertical",
        chevron_style=style,
    )
    assert (result if exporter is export_html else result.path) == target
    rendered = target.read_text(encoding="utf-8")
    assert 'chevronOrientation: "vertical"' in rendered
    assert f'chevronStyle: "{style}"' in rendered
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize(
    "option,value,error",
    [
        ("chevron_orientation", None, TypeError),
        ("chevron_orientation", True, TypeError),
        ("chevron_orientation", [], TypeError),
        ("chevron_orientation", "", ValueError),
        ("chevron_orientation", "LR", ValueError),
        ("chevron_orientation", '</script><img src="x">', ValueError),
        ("chevron_style", None, TypeError),
        ("chevron_style", True, TypeError),
        ("chevron_style", {}, TypeError),
        ("chevron_style", "", ValueError),
        ("chevron_style", "Neutral", ValueError),
        ("chevron_style", '</script><img src="x">', ValueError),
    ],
)
@pytest.mark.parametrize("exporter", [export_html, export_html_report])
@pytest.mark.parametrize("graph_kind", ["chevron", "process", "model"])
def test_invalid_options_neither_create_nor_replace_files(
    tmp_path, option, value, error, exporter, graph_kind
):
    graph = {
        "chevron": chevron_document,
        "process": sample_graph,
        "model": lambda: build_model_graph(petri_fixture()),
    }[graph_kind]()
    target = tmp_path / "variant.html"
    with pytest.raises(error, match=option):
        exporter(graph, target, **{option: value})
    assert not list(tmp_path.iterdir())
    target.write_bytes(b"original report")
    with pytest.raises(error, match=option):
        exporter(graph, target, overwrite=True, **{option: value})
    assert target.read_bytes() == b"original report"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("model", [False, True])
@pytest.mark.parametrize("engine", ["graphviz", "elk"])
@pytest.mark.parametrize("style", [None, "classic", "neutral"])
@pytest.mark.parametrize("exporter", [render_html, export_html, export_html_report])
def test_legacy_exports_accept_both_styles_without_changing_presentation(
    tmp_path, model, engine, style, exporter
):
    graph = build_model_graph(petri_fixture()) if model else sample_graph()
    options = {} if style is None else {"chevron_style": style}
    if exporter is render_html:
        rendered = exporter(graph, layout_engine=engine, **options)
    else:
        target = tmp_path / "legacy.html"
        exporter(graph, target, layout_engine=engine, **options)
        rendered = target.read_text(encoding="utf-8")
    assert 'id="pix-graph-data"' in rendered
    assert 'id="pix-visualization-data"' not in rendered
    assert "chevronOrientation" not in rendered
    assert "chevronStyle" not in rendered
    assert rendered == render_html(graph, layout_engine=engine, chevron_style="classic")


@pytest.mark.parametrize("model", [False, True])
@pytest.mark.parametrize(
    "options",
    [
        {"chevron_orientation": "vertical"},
        {"chevron_orientation": "auto"},
    ],
)
def test_legacy_documents_refuse_nonhorizontal_chevron_orientation(
    tmp_path, model, options
):
    graph = build_model_graph(petri_fixture()) if model else sample_graph()
    with pytest.raises(ValueError, match="requires VisualizationDocument"):
        export_html_report(graph, tmp_path / "legacy.html", **options)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("failure", ["missing", "unsafe"])
def test_chevron_asset_failure_preserves_existing_report(
    tmp_path, monkeypatch, failure
):
    import pix.viewer.export as module

    original_asset = module._asset

    def invalid_asset(name):
        if name == "chevron_geometry.js":
            if failure == "missing":
                raise FileNotFoundError("chevron geometry unavailable")
            return "</script><script>bad()</script>"
        return original_asset(name)

    monkeypatch.setattr(module, "_asset", invalid_asset)
    target = tmp_path / "variant.html"
    target.write_bytes(b"original report")
    with pytest.raises(FileNotFoundError if failure == "missing" else ValueError):
        export_html_report(
            chevron_document(), target, overwrite=True, layout_engine="native"
        )
    assert target.read_bytes() == b"original report"
    assert list(tmp_path.iterdir()) == [target]
