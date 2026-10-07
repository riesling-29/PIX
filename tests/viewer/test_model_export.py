from dataclasses import replace

import pytest

from pix.contracts.models import Arc
from pix.models import ModelArtifact
from pix.viewer import build_model_graph, export_html, render_html

from .test_export import extract_payload
from .test_model_graph import object_fixture, petri_fixture


@pytest.mark.parametrize("engine", ["graphviz", "elk"])
def test_model_html_retains_constraints_without_observed_metrics(engine):
    graph = build_model_graph(
        ModelArtifact(petri_fixture(), "discovered", "calculation-1")
    )
    payload = extract_payload(render_html(graph, layout_engine=engine))
    assert payload["schema"] == "pix.model-graph"
    assert payload["kind"] == "petri_net"
    assert payload["source_computation_id"] == "calculation-1"
    assert payload["origin"] == "discovered"
    assert len(payload["nodes"]) == 7
    assert all("event_count" not in node for node in payload["nodes"])
    assert all(
        "counts" not in edge and "evidence" not in edge for edge in payload["edges"]
    )


@pytest.mark.parametrize("maximum", [0, None, 5])
@pytest.mark.parametrize("engine", ["graphviz", "elk"])
def test_ocpn_html_distinguishes_zero_unbounded_and_capped_cardinality(maximum, engine):
    net = object_fixture(minimum=0, maximum=maximum)
    payload = extract_payload(render_html(build_model_graph(net), layout_engine=engine))
    assert payload["objects"] == [[item[0], item[1]] for item in net.objects]
    assert all(edge["max_objects"] == maximum for edge in payload["edges"])
    initial = next(node for node in payload["nodes"] if node["model_node_id"] == "in")
    assert initial["initial_objects"] == ["o1", "o1"]
    assert initial["initial_count"] == 2


@pytest.mark.parametrize("object_centric", [False, True])
@pytest.mark.parametrize("engine", ["graphviz", "elk"])
def test_export_rejects_large_integers_before_file_publication(
    tmp_path, object_centric, engine
):
    if object_centric:
        net = object_fixture(maximum=2**53)
    else:
        net = replace(petri_fixture(), arcs=(Arc("start", "a", 2**53 + 1),))
    target = tmp_path / "model.html"
    with pytest.raises(ValueError, match="exact integer range"):
        export_html(build_model_graph(net), target, layout_engine=engine)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("engine", ["graphviz", "elk"])
def test_largest_safe_integer_is_retained_exactly(engine):
    graph = build_model_graph(object_fixture(maximum=2**53 - 1))
    payload = extract_payload(render_html(graph, layout_engine=engine))
    assert all(edge["max_objects"] == 9007199254740991 for edge in payload["edges"])
