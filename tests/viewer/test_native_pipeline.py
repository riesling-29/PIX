from datetime import datetime, timedelta, timezone

from pix.compute import discover_dfg, discover_ocdfg
from pix.contracts.analysis import OCDFGSpec, TraceSpec
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType, canonical_digest
from pix.viewer import build_graph, export_html


def test_native_ocdfg_to_offline_viewer_preserves_parallel_loops_and_log(tmp_path):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    log = OCEL(
        event_types=(EventType("Pack"), EventType("Ship")),
        object_types=(ObjectType("Order"), ObjectType("Package")),
        events=(
            Event("e1", "Pack", start),
            Event("e2", "Ship", start + timedelta(minutes=1)),
            Event("e3", "Ship", start + timedelta(minutes=2)),
        ),
        objects=(
            Object("o1", "Order"),
            Object("o2", "Order"),
            Object("p1", "Package"),
            Object("empty", "Order"),
        ),
        e2o=tuple(
            E2O(event, obj, "item")
            for event in ("e1", "e2", "e3")
            for obj in ("o1", "o2", "p1")
        ),
    )
    digest = canonical_digest(log)
    result = discover_ocdfg(log, OCDFGSpec(("Order", "Package")))
    graph = build_graph(result)
    assert len(graph.edges) == 4
    assert len([edge for edge in graph.edges if edge.source == edge.target]) == 2
    assert {edge.counts.event_pairs for edge in graph.edges} == {1}
    assert {
        edge.counts.unique_objects
        for edge in graph.edges
        if edge.object_type == "Order"
    } == {2}
    assert {
        edge.counts.unique_objects
        for edge in graph.edges
        if edge.object_type == "Package"
    } == {1}
    ship = next(node for node in graph.nodes if node.label == "Ship")
    assert ship.event_ids == ("e2", "e3")
    assert ship.object_ids == ("o1", "o2", "p1")
    target = export_html(graph, tmp_path / "ocdfg.html")
    assert target.is_file()
    assert canonical_digest(log) == digest


def test_native_empty_dfg_exports_explicit_empty_view(tmp_path):
    log = OCEL(object_types=(ObjectType("Order"),), objects=(Object("empty", "Order"),))
    result = discover_dfg(log, TraceSpec("Order"))
    graph = build_graph(result)
    assert graph.nodes == graph.edges == ()
    assert graph.object_types == ("Order",)
    assert "1 objects have no event" in " ".join(graph.notes)
    assert export_html(graph, tmp_path / "empty.html").is_file()
