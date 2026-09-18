"""Real public pipelines, source identity and offline export boundaries."""

import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from importlib.resources import files

import pytest

from pix import case_centric as cc
from pix.case_centric.interleavings import discover_interleavings
from pix.case_centric.interleavings_ocel import from_interleavings
from pix.contracts.discovery import ProcessTree
from pix.contracts.graph import (
    GraphCounts,
    GraphDocument,
    GraphEdge,
    GraphEvidence,
    GraphNode,
)
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.models import ModelArtifact, model_document
from pix.ocel import OCEL, canonical_digest
from pix.viewer import (
    GraphPanel,
    TablePanel,
    UnsupportedVisualizationError,
    VisualField,
    VisualizationDocument,
    VisualNode,
    VisualProvenance,
    build_model_visualization,
    build_visualization,
    compare_footprints,
    export_html,
    read_visualization,
    render_html,
    visualization_json_bytes,
    write_visualization,
)


def small_log():
    time = datetime(2026, 9, 15, tzinfo=timezone.utc)
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{index}",
                tuple(
                    CaseEvent(
                        f"e{index}-{pos}",
                        (
                            CaseAttribute("concept:name", "string", label),
                            CaseAttribute("time:timestamp", "date", time),
                        ),
                    )
                    for pos, label in enumerate(labels)
                ),
            )
            for index, labels in enumerate(("AB", "AB", "AC"))
        )
    )


def legacy_graph():
    return GraphDocument(
        "ocdfg",
        "source",
        "calculation",
        (
            GraphNode("A", "A", ("e1",), ("o1", "o2")),
            GraphNode("B", "B", ("e2",), ("o1", "o2")),
        ),
        (
            GraphEdge(
                "edge",
                "A",
                "B",
                "Order",
                GraphCounts(1, 2, 2),
                (
                    GraphEvidence("e1", "e2", "o1", ("source-role",), ("target-role",)),
                    GraphEvidence("e1", "e2", "o2"),
                ),
            ),
        ),
        ("Order",),
    )


def test_native_case_result_keeps_its_identity_and_counts():
    result = cc.discover_dfg(small_log())
    document = build_visualization(result, title="Case flow")
    assert document.title == "Case flow"
    assert document.status == "ok"
    assert document.provenance[0].calculation_id == result.computation_id
    assert document.provenance[0].source_digest == result.source_digest
    graph = next(panel for panel in document.panels if isinstance(panel, GraphPanel))
    assert {node.label for node in graph.nodes} >= {"A", "B", "C"}
    assert len(graph.edges) >= 2


def test_model_artifact_preserves_declared_origin():
    tree = ProcessTree("activity", "Review")
    artifact = ModelArtifact(tree, "discovered", "discovery-id")
    document = build_visualization(artifact)
    assert document.provenance[0].calculation_id == "discovery-id"
    assert (
        document.provenance[0].model_digest == model_document(artifact)["model_digest"]
    )
    assert VisualField("origin", "discovered") in document.provenance[0].details


def test_raw_model_is_not_claimed_discovered():
    document = build_visualization(ProcessTree("activity", "A"))
    assert document.provenance[0].model_digest is not None
    assert document.provenance[0].calculation_id is None
    assert VisualField("origin", "unspecified") in document.provenance[0].details


def test_raw_ocel_canonical_identity_is_the_identifier_string():
    log = OCEL(event_types=(), object_types=(), events=(), objects=(), e2o=())
    document = build_visualization(log)
    assert document.provenance[0].source_digest == canonical_digest(log).identifier


def test_discovery_wrapper_keeps_calculation_and_embedded_model_identities():
    source = cc.split_miner.discover_split_miner(small_log())
    assert source.value.model is not None
    document = build_visualization(source)
    assert document.provenance[0].calculation_id == source.computation_id
    expected = model_document(source.value.model)["model_digest"]
    assert any(item.model_digest == expected for item in document.provenance)
    assert any(isinstance(panel, GraphPanel) for panel in document.panels)


@pytest.mark.parametrize(
    "status,expected",
    [
        (ComputeStatus.COMPUTED, "ok"),
        (ComputeStatus.PARTIAL, "partial"),
        (ComputeStatus.UNAVAILABLE, "unsupported"),
    ],
)
def test_interleavings_ocel_wrapper_uses_candidate_and_report(status, expected):
    log = CaseLog(())
    conversion = from_interleavings(log, log, discover_interleavings(log, log))
    evidence = replace(
        conversion.evidence,
        status=status,
        value=None
        if status is ComputeStatus.UNAVAILABLE
        else conversion.evidence.value,
        issues=()
        if status is ComputeStatus.COMPUTED
        else (ComputeIssue("projection_limit", "Projection coverage is limited"),),
    )
    conversion = replace(
        conversion,
        candidate=None if status is ComputeStatus.UNAVAILABLE else conversion.candidate,
        evidence=evidence,
    )
    document = build_visualization(conversion)
    assert document.status == expected
    assert document.panels
    assert document.provenance[0].calculation_id == evidence.computation_id
    assert document.provenance[0].status == status.value
    if status is not ComputeStatus.COMPUTED:
        assert any("projection_limit" in issue for issue in document.issues)


def test_public_footprint_comparison_passes_partial_envelope_to_relation_logic():
    complete = cc.discover_footprints(small_log())
    partial = replace(
        complete,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("prefix", "Only part of the source was observed"),),
    )
    document = compare_footprints(partial, complete, symmetric=True)
    assert document.status == "partial"
    assert any(
        cell.kind == "unknown"
        for panel in document.panels
        if panel.kind == "matrix"
        for cell in panel.cells
    )
    assert document.provenance[0].status == "partial"


def test_model_annotation_requires_explicit_measure_selection():
    model = ProcessTree("activity", "A")
    result = cc.discover_dfg(small_log())
    with pytest.raises(ValueError, match="explicit annotation metric"):
        build_model_visualization(model, annotations=result)
    with pytest.raises(ValueError, match="requires an annotations"):
        build_model_visualization(model, metric="firing_count")


def test_compose_keeps_inputs_separate_and_panel_identifiers_unique():
    result = cc.discover_dfg(small_log())
    document = build_visualization(result, result)
    assert len(document.panels) == 2 * len(build_visualization(result).panels)
    assert len({panel.id for panel in document.panels}) == len(document.panels)
    assert {panel.id.split("/")[0] for panel in document.panels} == {
        "input-0",
        "input-1",
    }
    assert [item.calculation_id for item in document.provenance] == [
        result.computation_id,
        *result.parent_computation_ids,
    ] * 2


def test_composition_distinguishes_which_input_owns_each_source():
    panel = TablePanel("p", "Values", ("value",), ((1,),))
    a = VisualProvenance(calculation_id="a")
    b = VisualProvenance(calculation_id="b")
    together = build_visualization(
        VisualizationDocument("left", (panel,), (a, b)),
        VisualizationDocument("right", (panel,)),
    )
    separate = build_visualization(
        VisualizationDocument("left", (panel,), (a,)),
        VisualizationDocument("right", (panel,), (b,)),
    )
    assert together.panels == separate.panels
    assert together != separate
    assert together.provenance[1].panel_ids == ("input-0/p",)
    assert separate.provenance[1].panel_ids == ("input-1/p",)
    assert separate.provenance[1].input_path == (1,)


def test_nested_composition_preserves_scope_paths_and_roundtrips(tmp_path):
    panel = TablePanel("p", "Values", ("value",), ((1,),))
    first = VisualizationDocument(
        "first", (panel,), (VisualProvenance(calculation_id="a"),)
    )
    second = VisualizationDocument(
        "second", (panel,), (VisualProvenance(calculation_id="b"),)
    )
    nested = build_visualization(build_visualization(first, second), first)
    assert [item.panel_ids for item in nested.provenance] == [
        ("input-0/input-0/p",),
        ("input-0/input-1/p",),
        ("input-1/p",),
    ]
    assert [item.input_path for item in nested.provenance] == [(0, 0), (0, 1), (1,)]
    assert build_visualization(nested) is nested
    assert build_visualization(nested, title="Renamed") == replace(
        nested, title="Renamed"
    )
    path = tmp_path / "nested.json"
    write_visualization(nested, path)
    assert read_visualization(path) == nested


def test_comparison_sources_are_scoped_to_all_joint_panels():
    footprints = cc.discover_footprints(small_log())
    document = compare_footprints(footprints, footprints)
    assert {item.input_path for item in document.provenance} == {(0,), (1,)}
    assert all(
        item.panel_ids == tuple(panel.id for panel in document.panels)
        for item in document.provenance
    )


def test_nested_failed_input_never_acquires_another_inputs_panels():
    source = cc.discover_dfg(small_log())
    failed = replace(source, status=ComputeStatus.UNAVAILABLE, value=None)
    inner = build_visualization(source, failed)
    assert inner.status == "partial"
    failed_provenance = next(
        item for item in inner.provenance if item.status == "unavailable"
    )
    assert failed_provenance.panel_ids == ()
    assert failed_provenance.input_path == (1,)
    outer = build_visualization(inner, ProcessTree("activity", "B"))
    assert outer.status == "partial"
    failed_provenance = next(
        item for item in outer.provenance if item.status == "unavailable"
    )
    assert failed_provenance.panel_ids == ()
    assert failed_provenance.input_path == (0, 1)


def test_result_request_is_inspectable_and_must_match_identity():
    result = cc.discover_dfg(small_log())
    document = build_visualization(result)
    fields = {field.name: field.value for field in document.provenance[0].details}
    assert json.loads(fields["request_json"])
    assert fields["request_type"].endswith(type(result.spec).__name__)
    with pytest.raises(ValueError, match="computation identity"):
        build_visualization(replace(result, computation_id="wrong-id"))


def test_legacy_graph_retains_distinct_count_units_and_role_witnesses():
    document = build_visualization(legacy_graph())
    graph, table = document.panels
    assert isinstance(graph, GraphPanel)
    assert {metric.name: metric.value for metric in graph.edges[0].metrics} == {
        "event_pairs": 1,
        "objects": 2,
        "occurrences": 2,
    }
    assert len(table.rows) == 2
    assert json.loads(table.rows[0][4]) == ["source-role"]
    assert json.loads(table.rows[0][5]) == ["target-role"]


@pytest.mark.parametrize(
    "status,expected",
    [
        (ComputeStatus.UNAVAILABLE, "unsupported"),
        (ComputeStatus.INVALID_INPUT, "error"),
    ],
)
def test_failed_calculation_remains_explicit_without_an_empty_success_graph(
    status, expected
):
    source = cc.discover_dfg(small_log())
    failed = replace(
        source,
        status=status,
        value=None,
        issues=(ComputeIssue("test_missing", "Measurement not available"),),
    )
    document = build_visualization(failed)
    assert document.status == expected and document.panels == ()
    assert "test_missing" in document.issues[0]
    assert document.provenance[0].status == status.value


def test_partial_source_keeps_coverage_issue():
    source = cc.discover_dfg(small_log())
    partial = replace(
        source,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("limited", "Only observed prefix available"),),
    )
    document = build_visualization(partial)
    assert document.status == "partial"
    assert document.panels and "limited" in document.issues[0]


@pytest.mark.parametrize("value", [object(), {"nodes": []}, 17, None])
def test_unknown_input_is_not_serialized_as_a_fake_domain_view(value):
    with pytest.raises(UnsupportedVisualizationError):
        build_visualization(value)


def test_custom_typed_panel_and_atomic_json_publication(tmp_path):
    document = VisualizationDocument(
        "Quality",
        (
            TablePanel(
                "quality",
                "Quality",
                ("Measure", "Value"),
                (("Fitness", 0.5), ("Precision", None)),
            ),
        ),
    )
    path = tmp_path / "view.json"
    write_visualization(document, path)
    assert read_visualization(path) == document
    assert path.read_bytes() == visualization_json_bytes(document)
    with pytest.raises(FileExistsError):
        write_visualization(replace(document, title="Changed"), path)
    assert read_visualization(path).title == "Quality"
    write_visualization(replace(document, title="Changed"), path, overwrite=True)
    assert read_visualization(path).title == "Changed"


@pytest.mark.parametrize("engine", ["graphviz", "native"])
def test_offline_html_uses_selected_engine_and_escapes_source_markup(tmp_path, engine):
    hostile = '</script><img src="https://invalid.example" onerror="window.pwned=1">&'
    document = VisualizationDocument(
        hostile, (GraphPanel("g", "Graph", (VisualNode("a", hostile),)),)
    )
    text = render_html(document, layout_engine=engine)
    assert hostile not in text
    assert "PIXVisualization.mount" in text and "pixViewerReady" in text
    assert "elk.bundled" not in text and "new ELK" not in text
    assert f'{{layoutEngine: "{engine}",' in text
    if engine == "graphviz":
        assert "PIXGraphvizGeometry" in text
        assert 'id="pix-viewer-license"' in text
    else:
        graphviz_source = (
            files("pix.viewer")
            .joinpath("assets", "vendor", "viz-global.js")
            .read_text(encoding="utf-8")
        )
        assert graphviz_source not in text
        assert 'id="pix-viewer-license"' not in text
    assert not re.search(r"<script[^>]+src\s*=", text, flags=re.I)
    payload = re.search(
        r'<script id="pix-visualization-data" type="application/json">(.*?)</script>',
        text,
        flags=re.S,
    )
    assert payload is not None
    assert json.loads(payload.group(1))["title"] == hostile
    path = tmp_path / "view.html"
    assert export_html(document, path, layout_engine=engine) == path
    assert path.read_text(encoding="utf-8") == text


@pytest.mark.parametrize("engine", ["graphviz", "native"])
def test_huge_integer_json_is_lossless_but_browser_export_refuses_rounding(
    tmp_path, engine
):
    document = VisualizationDocument(
        "Exact", (TablePanel("t", "Values", ("value",), ((2**60 + 1,),)),)
    )
    assert str(2**60 + 1).encode() in visualization_json_bytes(document)
    with pytest.raises(ValueError, match="exact integer range"):
        export_html(document, tmp_path / "exact.html", layout_engine=engine)
    assert not list(tmp_path.iterdir())


def test_visualization_document_defaults_to_graphviz_and_refuses_elk(tmp_path):
    document = build_visualization(cc.discover_dfg(small_log()))
    assert '{layoutEngine: "graphviz",' in render_html(document)
    with pytest.raises(ValueError, match="requires a legacy graph"):
        export_html(document, tmp_path / "unsupported.html", layout_engine="elk")
    assert not list(tmp_path.iterdir())


def test_public_facade_exports_resolve_and_rejects_missing_input():
    import pix.viewer as viewer

    assert len(viewer.__all__) == len(set(viewer.__all__))
    for name in viewer.__all__:
        assert getattr(viewer, name) is not None
    with pytest.raises(ValueError):
        build_visualization()
