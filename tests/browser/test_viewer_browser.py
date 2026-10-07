"""Opt-in real Chromium checks of the production offline SVG/ELK viewer.

Run with PIX_RUN_BROWSER=1 after installing the browser extra and Chromium.
All source graphs are produced by native OCDFG computation from synthetic OCEL.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import OCDFGSpec
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer import build_graph, export_html

playwright = pytest.importorskip("playwright.sync_api")
pytestmark = pytest.mark.browser

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".artifacts" / "browser"
LONG_LABEL = "대한민국 공동 배송 및 품질 검사를 위한 긴 프로세스 활동 이름 " * 5
HOSTILE = '</script><img src="https://invalid.example/x" onerror="window.pwned=1">&\x00'
NS = {"svg": "http://www.w3.org/2000/svg"}


def computed_graph(*, hostile=False, empty=False):
    """Shared/repeated A-B, parallel types, B-B, singleton, and empty objects."""
    parcel_type = HOSTILE if hostile else "parcel"
    final_label = HOSTILE if hostile else LONG_LABEL
    activities = ("Pack", "Ship", "Pack", "Ship", "Ship", final_label, "Check")
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    memberships = (
        ("e0", "o1"),
        ("e1", "o1"),
        ("e2", "o1"),
        ("e3", "o1"),
        ("e4", "o1"),
        ("e5", "o1"),
        ("e0", "o2"),
        ("e1", "o2"),
        ("e0", "p1"),
        ("e1", "p1"),
        ("e6", "singleton"),
    )
    log = OCEL(
        event_types=tuple(EventType(value) for value in dict.fromkeys(activities)),
        object_types=(
            ObjectType("order"),
            ObjectType(parcel_type),
            ObjectType("unused"),
        ),
        events=()
        if empty
        else tuple(
            Event(f"e{index}", activity, origin + timedelta(seconds=index))
            for index, activity in enumerate(activities)
        ),
        objects=(
            Object("o1", "order"),
            Object("o2", "order"),
            Object("p1", parcel_type),
            Object("singleton", "order"),
            Object("isolated", "order"),
        ),
        e2o=()
        if empty
        else tuple(E2O(event, obj, "flow") for event, obj in memberships)
        + (E2O("e0", "o1", "audit"),),
    )
    result = discover_ocdfg(log, OCDFGSpec(("order", parcel_type, "unused")))
    assert result.status is ComputeStatus.COMPUTED
    return build_graph(result, title="PIX native OCDFG · 공동 배송 검증")


def accepting_net():
    """Repeated visible labels are distinct identities; silent remains distinct."""
    return PetriNet(
        places=tuple(Place(name) for name in ("start", "middle", "after", "end")),
        transitions=(
            Transition("approve-1", "Approve"),
            Transition("approve-2", "Approve"),
            Transition("silent"),
        ),
        arcs=(
            Arc("start", "approve-1", 2),
            Arc("approve-1", "middle", 2),
            Arc("middle", "approve-2", 2),
            Arc("approve-2", "after", 2),
            Arc("after", "silent", 2),
            Arc("silent", "end", 2),
        ),
        initial_marking=Marking((("start", 2),)),
        final_marking=Marking((("end", 2),)),
    )


def shared_binding_net():
    return ObjectCentricPetriNet(
        places=(
            TypedPlace("order-ready", "order"),
            TypedPlace("order-done", "order"),
            TypedPlace("item-ready", "item"),
            TypedPlace("item-done", "item"),
        ),
        transitions=(Transition("ship", "Ship"),),
        arcs=(
            ObjectArc("order-ready", "ship"),
            ObjectArc("ship", "order-done"),
            ObjectArc("item-ready", "ship", True, 1, 2),
            ObjectArc("ship", "item-done", True, 1, 2),
        ),
        initial_marking=ObjectMarking(
            (
                ObjectToken("order-ready", "o1"),
                ObjectToken("item-ready", "i1"),
                ObjectToken("item-ready", "i2"),
            )
        ),
        final_marking=ObjectMarking(
            (
                ObjectToken("order-done", "o1"),
                ObjectToken("item-done", "i1"),
                ObjectToken("item-done", "i2"),
            )
        ),
        objects=(("o1", "order"), ("i1", "item"), ("i2", "item")),
    )


@pytest.fixture(scope="session")
def browser():
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip("set PIX_RUN_BROWSER=1 to run actual browser verification")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with playwright.sync_playwright() as manager:
        # An explicitly requested browser run fails if its browser is not installed.
        instance = manager.chromium.launch(headless=True)
        yield instance
        instance.close()


@pytest.fixture
def open_view(browser, tmp_path, request):
    contexts = []
    observations = []

    def open_graph(graph=None, *, width=1280, init_script=None, wait_ready=True):
        graph = computed_graph() if graph is None else graph
        document = export_html(graph, tmp_path / f"graph-{len(contexts)}.html")
        context = browser.new_context(viewport={"width": width, "height": 900})
        contexts.append(context)
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )

        def forbid_network(route):
            external.append(route.request.url)
            route.abort()

        context.route("http://**/*", forbid_network)
        context.route("https://**/*", forbid_network)
        if init_script:
            page.add_init_script(init_script)
        page.goto(document.as_uri(), wait_until="load")
        if wait_ready:
            page.evaluate("async () => { await window.pixViewerReady; }")
        observations.append((page, errors, external))
        return page, graph

    yield open_graph
    for index, (page, errors, external) in enumerate(observations):
        page.screenshot(
            path=str(ARTIFACTS / f"{request.node.name}-{index}.png"), full_page=True
        )
        assert not errors, f"browser errors: {errors}"
        assert not external, f"offline export attempted network requests: {external}"
    for context in contexts:
        context.close()


def graph_data(page):
    return page.evaluate("window.pixViewer.getGraph()")


def node_positions(page):
    return page.locator(".pix-node").evaluate_all(
        "nodes => nodes.map(node => [node.dataset.nodeId, node.getAttribute('transform')])"
    )


def edge_locator(page, edge):
    return page.locator(f'.pix-edge[data-edge-id="{edge["id"]}"]')


def test_actual_layout_preserves_parallel_edges_self_loop_and_singletons(open_view):
    page, graph = open_view()
    assert page.locator(".pix-node").count() == len(graph.nodes) == 4
    assert page.locator(".pix-edge").count() == len(graph.edges) == 5
    data = graph_data(page)
    pack = next(node for node in data["nodes"] if node["label"] == "Pack")
    ship = next(node for node in data["nodes"] if node["label"] == "Ship")
    parallel = [
        edge
        for edge in data["edges"]
        if edge["source"] == pack["id"] and edge["target"] == ship["id"]
    ]
    assert len(parallel) == 2
    assert (
        len(
            {
                edge_locator(page, edge).locator(".pix-edge-line").get_attribute("d")
                for edge in parallel
            }
        )
        == 2
    )
    loop = next(edge for edge in data["edges"] if edge["source"] == edge["target"])
    assert edge_locator(page, loop).locator(".pix-edge-line").get_attribute("d")
    assert "1 objects have no event" in page.locator(".pix-inspector").inner_text()
    assert LONG_LABEL in [node["label"] for node in data["nodes"]]


def test_view_filter_preserves_computation_positions_and_hidden_source_evidence(
    open_view,
):
    page, _ = open_view()
    original = graph_data(page)
    positions = node_positions(page)
    page.get_by_label("Show object type parcel", exact=True).uncheck()
    parcel = [edge for edge in original["edges"] if edge["object_type"] == "parcel"]
    for edge in parcel:
        assert edge_locator(page, edge).get_attribute("aria-hidden") == "true"
        assert edge_locator(page, edge).get_attribute("tabindex") == "-1"
        assert not edge_locator(page, edge).is_visible()
    assert graph_data(page) == original
    assert node_positions(page) == positions
    assert page.evaluate("window.pixViewer.getViewState().hiddenObjectTypes") == [
        "parcel"
    ]
    page.get_by_role("button", name="Reset", exact=True).click()
    assert page.evaluate("window.pixViewer.getViewState().hiddenObjectTypes") == []
    assert node_positions(page) == positions


def test_count_units_and_original_event_object_qualifier_evidence(open_view):
    page, _ = open_view()
    data = graph_data(page)
    edge = next(item for item in data["edges"] if item["counts"]["occurrences"] == 3)
    selected = edge_locator(page, edge)
    positions = node_positions(page)
    for unit, count in (
        ("event_pairs", "2"),
        ("unique_objects", "2"),
        ("occurrences", "3"),
    ):
        page.get_by_label("Edge counting unit", exact=True).select_option(unit)
        assert selected.locator(".pix-edge-label tspan").last.text_content() == count
        assert page.evaluate("window.pixViewer.getViewState().unit") == unit
    selected.locator(".pix-edge-label").click()
    inspector = page.locator(".pix-inspector")
    assert inspector.locator("tbody tr").count() == 3
    assert {
        tuple(cell.inner_text().split("\n")[0] for cell in row.locator("td").all())
        for row in inspector.locator("tbody tr").all()
    } == {("e0", "e1", "o1"), ("e0", "e1", "o2"), ("e2", "e3", "o1")}
    inspector.locator("summary").first.click()
    assert '"audit"' in inspector.inner_text()
    assert '"flow"' in inspector.inner_text()
    assert node_positions(page) == positions


def test_keyboard_selects_nodes_and_edges_without_mouse(open_view):
    page, _ = open_view()
    node = page.locator(".pix-node").first
    node.focus()
    assert node.evaluate("el => el === document.activeElement")
    page.keyboard.press("Enter")
    assert page.evaluate("window.pixViewer.getViewState().selected") == {
        "kind": "node",
        "id": node.get_attribute("data-node-id"),
    }
    edge = page.locator(".pix-edge").first
    edge.focus()
    page.keyboard.press("Space")
    assert page.evaluate("window.pixViewer.getViewState().selected") == {
        "kind": "edge",
        "id": edge.get_attribute("data-edge-id"),
    }
    assert page.get_by_role("heading", name="Source evidence", exact=True).is_visible()
    page.locator(".pix-graph").focus()
    page.keyboard.press("Tab")
    assert edge.evaluate("el => el === document.activeElement")
    page.keyboard.press("Enter")
    assert page.evaluate(
        "window.pixViewer.getViewState().selected.id"
    ) == edge.get_attribute("data-edge-id")


def test_zoom_pan_and_fit_change_only_view_coordinates(open_view):
    page, _ = open_view()
    graph = graph_data(page)
    positions = node_positions(page)
    original = page.evaluate("window.pixViewer.getViewState().viewBox")
    canvas = page.locator(".pix-graph")
    canvas.focus()
    page.keyboard.press("+")
    zoomed = page.evaluate("window.pixViewer.getViewState().viewBox")
    assert zoomed["width"] < original["width"]
    page.keyboard.press("ArrowRight")
    assert page.evaluate("window.pixViewer.getViewState().viewBox.x") > zoomed["x"]
    page.get_by_role("button", name="Fit", exact=True).click()
    assert page.evaluate("window.pixViewer.getViewState().viewBox") == original
    assert graph_data(page) == graph
    assert node_positions(page) == positions


@pytest.mark.parametrize("width", [736, 360])
def test_responsive_view_keeps_controls_and_content_inside_page(open_view, width):
    page, _ = open_view(width=width)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    for label in ("Fit", "Readable", "Reset", "Save SVG"):
        control = page.get_by_role("button", name=label, exact=True)
        bounds = control.bounding_box()
        assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
    page.locator(".pix-node").first.focus()
    page.keyboard.press("Enter")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_hostile_labels_remain_inert_source_text_and_svg_is_valid(open_view, tmp_path):
    page, _ = open_view(computed_graph(hostile=True), width=360)
    assert page.evaluate("window.pwned === undefined")
    assert page.locator("img").count() == 0
    assert HOSTILE in graph_data(page)["object_types"]
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    with page.expect_download() as pending:
        page.get_by_role("button", name="Save SVG", exact=True).click()
    destination = tmp_path / "hostile.svg"
    pending.value.save_as(destination)
    tree = ElementTree.parse(destination)
    assert tree.getroot().tag == f"{{{NS['svg']}}}svg"
    assert "\ufffd" in destination.read_text(encoding="utf-8")


def test_svg_download_retains_style_source_metadata_and_all_geometry(
    open_view, tmp_path
):
    page, graph = open_view()
    page.get_by_label("Edge counting unit", exact=True).select_option("occurrences")
    page.get_by_label("Show object type parcel", exact=True).uncheck()
    with page.expect_download() as pending:
        page.get_by_role("button", name="Save SVG", exact=True).click()
    destination = tmp_path / "graph.svg"
    pending.value.save_as(destination)
    root = ElementTree.parse(destination).getroot()
    assert ".pix-node-label" in root.find("svg:style", NS).text
    metadata = json.loads(root.find("svg:metadata", NS).text)
    assert metadata["source_digest"] == graph.source_digest
    assert metadata["counting_unit"] == "occurrences"
    assert metadata["hidden_object_types"] == ["parcel"]
    assert len(root.findall('.//svg:g[@class="pix-node"]', NS)) == len(graph.nodes)
    exported = page.context.new_page()
    exported.goto(destination.as_uri())
    assert exported.evaluate("""() => {
      const svg = document.documentElement;
      const view = svg.viewBox.baseVal;
      return [...svg.querySelectorAll('.pix-node, .pix-edge:not([hidden])')].every(el => {
        const bounds = el.getBBox(), transform = el.getCTM();
        const corners = [new DOMPoint(bounds.x, bounds.y), new DOMPoint(bounds.x + bounds.width, bounds.y + bounds.height)];
        const inverse = svg.getCTM().inverse();
        return corners.map(p => p.matrixTransform(transform).matrixTransform(inverse)).every(p =>
          p.x >= view.x && p.y >= view.y && p.x <= view.x + view.width && p.y <= view.y + view.height);
      });
    }""")
    assert exported.evaluate("""() => [...document.querySelectorAll('.pix-node')].every(node => {
      const bounds = node.querySelector('rect').getBBox();
      return [...node.querySelectorAll('text')].every(text => {
        const box = text.getBBox();
        return box.x >= bounds.x && box.y >= bounds.y &&
          box.x + box.width <= bounds.x + bounds.width &&
          box.y + box.height <= bounds.y + bounds.height;
      });
    })""")
    dimensions = exported.evaluate("""() => ({
      width: Math.ceil(document.documentElement.width.baseVal.value),
      height: Math.ceil(document.documentElement.height.baseVal.value)
    })""")
    exported.set_viewport_size(dimensions)
    exported.screenshot(path=str(ARTIFACTS / "exported-svg.png"))
    exported.close()


def test_empty_analysis_displays_no_activity_state_without_fake_nodes(open_view):
    page, _ = open_view(computed_graph(empty=True))
    assert page.locator(".pix-node, .pix-edge").count() == 0
    assert page.get_by_role("heading", name="No activity nodes").is_visible()
    assert "5 objects have no event" in page.locator(".pix-inspector").inner_text()


def test_save_is_disabled_until_actual_layout_finishes(open_view):
    delay_layout = """(() => {
      let original;
      Object.defineProperty(window, 'PIXLayout', {
        configurable: true,
        get: () => original,
        set: value => { original = {...value, createElkLayout: engine => {
          const run = value.createElkLayout(engine);
          return async graph => {
            await new Promise(resolve => { window.releaseTestLayout = resolve; });
            return run(graph);
          };
        }}; }
      });
    })();"""
    page, _ = open_view(init_script=delay_layout, wait_ready=False)
    save = page.get_by_role("button", name="Save SVG", exact=True)
    try:
        assert save.is_disabled(), "Saving before layout must not export an empty graph"
    finally:
        page.evaluate("window.releaseTestLayout()")
        page.evaluate("async () => { await window.pixViewerReady; }")
    assert save.is_enabled()


def test_petri_net_draws_model_identity_silent_nodes_weights_and_markings(open_view):
    from pix.viewer import build_model_graph

    graph = build_model_graph(accepting_net(), title="Accepting net · 모델 의미 검증")
    page, _ = open_view(graph)
    data = graph_data(page)
    assert data["kind"] == "petri_net"
    assert page.locator(".pix-node").count() == 7
    assert page.locator(".pix-edge").count() == 6
    assert page.locator("circle.pix-place-shape").count() == 4
    assert page.locator("rect.pix-transition-shape").count() == 2
    assert page.locator("rect.pix-silent-shape").count() == 1
    assert page.get_by_label("Edge counting unit", exact=True).count() == 0
    visible = [node for node in data["nodes"] if node["kind"] == "transition"]
    assert {node["label"] for node in visible} == {"Approve"}
    assert {node["model_node_id"] for node in visible} == {"approve-1", "approve-2"}
    assert len({node["id"] for node in visible}) == 2
    assert {edge["weight"] for edge in data["edges"]} == {2}
    assert not any("counts" in edge for edge in data["edges"])
    assert page.locator(".pix-initial-token").count() == 2
    assert page.locator(".pix-final-ring").count() == 1
    assert (
        next(node for node in data["nodes"] if node["model_node_id"] == "end")[
            "final_count"
        ]
        == 2
    )
    silent = page.locator('.pix-node[data-model-node-id="silent"]')
    silent.focus()
    page.keyboard.press("Enter")
    assert "silent" in page.locator(".pix-inspector").text_content().casefold()
    positions = node_positions(page)
    page.screenshot(path=str(ARTIFACTS / "petri-net-fit-overview.png"), full_page=True)
    page.get_by_role("button", name="Readable", exact=True).click()
    assert page.locator(".pix-graph").evaluate(
        "svg => svg.getScreenCTM().a"
    ) == pytest.approx(1)
    assert graph_data(page) == data
    assert node_positions(page) == positions
    selected_bounds = silent.bounding_box()
    canvas_bounds = page.locator(".pix-graph").bounding_box()
    assert selected_bounds["x"] >= canvas_bounds["x"]
    assert (
        selected_bounds["x"] + selected_bounds["width"]
        <= canvas_bounds["x"] + canvas_bounds["width"]
    )


def test_ocpn_typed_places_fixed_and_variable_arcs_preserve_binding_evidence(
    open_view, tmp_path
):
    from pix.viewer import build_model_graph

    graph = build_model_graph(shared_binding_net(), title="Shared binding · 공동 배송")
    page, _ = open_view(graph)
    data = graph_data(page)
    assert data["kind"] == "ocpn"
    assert page.locator("circle.pix-place-shape").count() == 4
    assert page.locator("rect.pix-transition-shape").count() == 1
    assert page.locator(".pix-edge").count() == 4
    assert page.get_by_label("Edge counting unit", exact=True).count() == 0
    variable = [edge for edge in data["edges"] if edge["variable"]]
    fixed = [edge for edge in data["edges"] if not edge["variable"]]
    assert len(variable) == len(fixed) == 2
    assert page.locator('.pix-variable-arc[data-variable="true"]').count() == 2
    assert page.get_by_text(
        "Dashed arc = variable object cardinality", exact=True
    ).is_visible()
    for edge in variable:
        assert (
            edge_locator(page, edge)
            .locator(".pix-edge-line")
            .evaluate("el => getComputedStyle(el).strokeDasharray")
            != "none"
        )
        assert (
            "[1,2] objects"
            in edge_locator(page, edge).locator(".pix-edge-label").text_content()
        )
    for edge in fixed:
        assert (
            edge_locator(page, edge)
            .locator(".pix-edge-line")
            .evaluate("el => getComputedStyle(el).strokeDasharray")
            == "none"
        )
    assert {
        (edge["min_objects"], edge["max_objects"], edge["object_type"])
        for edge in variable
    } == {(1, 2, "item")}
    assert {
        (edge["min_objects"], edge["max_objects"], edge["object_type"])
        for edge in fixed
    } == {(1, 1, "order")}
    assert next(
        node for node in data["nodes"] if node["model_node_id"] == "item-ready"
    )["initial_objects"] == ["i1", "i2"]
    positions = node_positions(page)
    page.get_by_label("Show object type item", exact=True).uncheck()
    for edge in variable:
        assert not edge_locator(page, edge).is_visible()
    for edge in fixed:
        assert edge_locator(page, edge).is_visible()
    assert graph_data(page) == data
    assert node_positions(page) == positions
    page.get_by_role("button", name="Reset", exact=True).click()
    ready = page.locator('.pix-node[data-model-node-id="item-ready"]')
    ready.focus()
    page.keyboard.press("Enter")
    assert "i1" in page.locator(".pix-inspector").text_content()
    assert "i2" in page.locator(".pix-inspector").text_content()
    edge_locator(page, variable[0]).focus()
    page.keyboard.press("Enter")
    details = page.locator(
        ".pix-inspector dl"
    ).evaluate("""list => Object.fromEntries(
      [...list.querySelectorAll('dt')].map(term => [term.textContent, term.nextElementSibling.textContent]))""")
    assert details["Arc kind"] == "Variable object cardinality"
    assert details["Minimum bound objects"] == "1"
    assert details["Maximum bound objects"] == "2"
    with page.expect_download() as pending:
        page.get_by_role("button", name="Save SVG", exact=True).click()
    destination = tmp_path / "ocpn.svg"
    pending.value.save_as(destination)
    root = ElementTree.parse(destination).getroot()
    metadata = json.loads(root.find("svg:metadata", NS).text)
    assert metadata["model_digest"] == graph.model_digest
    assert "counting_unit" not in metadata
    assert (
        len(
            [
                element
                for element in root.iter()
                if "pix-variable-arc" in element.attrib.get("class", "").split()
            ]
        )
        == 2
    )
    assert len(root.findall('.//svg:circle[@class="pix-place-shape"]', NS)) == 4
