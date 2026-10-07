"""End-to-end native discovery, model execution, persistence and viewer contract."""

import pytest

from pix.api import (
    AlignmentSpec,
    ComputeStatus,
    DiscoverySpec,
    OCDFGSpec,
    TraceSpec,
    align_traces,
    discover_ocdfg,
    discover_process_tree,
    export_ocel,
    process_tree_to_petri_net,
    read_ocel,
    reconstruct_traces,
)
from pix.models import ModelArtifact, read_model, write_model
from pix.ocel import canonical_digest
from pix.results import read_result, write_result
from pix.viewer import build_graph, build_model_graph, export_html


@pytest.mark.parametrize(
    "format,suffix",
    [
        ("json", ".json"),
        ("xml", ".xml"),
        ("sqlite", ".sqlite"),
        ("json", ".json.gz"),
        ("xml", ".xml.gz"),
    ],
)
def test_log_to_model_and_viewer_pipeline(native_log, tmp_path, format, suffix):
    source = tmp_path / ("source" + suffix)
    publication = export_ocel(native_log, source, format=format)
    log = read_ocel(source)
    assert canonical_digest(log) == canonical_digest(native_log)
    assert publication.roundtrip == "passed"
    traces = reconstruct_traces(log, TraceSpec("Order"))
    tree = discover_process_tree(traces, DiscoverySpec())
    net = process_tree_to_petri_net(tree.value)
    artifact = ModelArtifact(net, "discovered", tree.computation_id)
    model_path = write_model(artifact, tmp_path / "model.json")
    restored_model = read_model(model_path)
    assert restored_model == artifact
    model_graph = build_model_graph(restored_model)
    model_viewer = export_html(model_graph, tmp_path / "model.html")
    assert tree.computation_id in model_viewer.read_text(encoding="utf-8")
    aligned = align_traces(traces, net, AlignmentSpec())
    assert aligned.status is ComputeStatus.COMPUTED
    assert aligned.value.coverage.optimal == 3
    assert aligned.value.total_cost == 0
    result_path = write_result(aligned, tmp_path / "alignment.json")
    assert read_result(result_path) == aligned
    ocdfg = discover_ocdfg(log, OCDFGSpec(("Order", "Package")))
    graph = build_graph(ocdfg)
    edge = next(
        edge
        for edge in graph.edges
        if edge.object_type == "Order" and edge.counts.occurrences == 2
    )
    assert edge.counts.event_pairs == 1
    assert edge.counts.unique_objects == 2
    viewer = export_html(graph, tmp_path / "process.html")
    html = viewer.read_text(encoding="utf-8")
    assert graph.computation_id in html
    assert "pixViewerReady" in html
    assert canonical_digest(log) == canonical_digest(native_log)
