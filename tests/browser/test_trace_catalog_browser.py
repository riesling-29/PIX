"""Actual offline selection, keyboard, persistence, SVG and narrow viewport."""

import importlib.util
import json
import os
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pix.case_centric import catalog_trace_variants
from pix.viewer import build_visualization, export_html

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.browser


def test_variant_count_selection_in_real_browser(tmp_path):
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip("Set PIX_RUN_BROWSER=1 for actual catalog browser checks")
    playwright = pytest.importorskip("playwright.sync_api")
    definition = importlib.util.spec_from_file_location(
        "catalog_demo", ROOT / "examples/trace_variant_catalog_demo.py"
    )
    demo = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(demo)
    result = catalog_trace_variants(demo.demo_log(), group_attribute="quality_group")
    folder = ROOT / ".artifacts/browser-catalog"
    folder.mkdir(parents=True, exist_ok=True)
    page_file = export_html(
        build_visualization(result, title="Trace 빈도와 복수 선택 · 합성 데이터"),
        folder / "catalog.html",
        layout_engine="native",
        overwrite=True,
    )
    normal = next(g for g in result.value.groups if g.name == "정상")
    evidence = {"checks": [], "requests": [], "errors": []}
    with playwright.sync_playwright() as manager:
        browser = manager.chromium.launch(headless=True)
        evidence["browser"] = browser.version
        context = browser.new_context(
            viewport={"width": 1440, "height": 1100}, accept_downloads=True
        )
        for scheme in ("http", "https"):
            context.route(
                scheme + "://**/*",
                lambda route: (
                    evidence["requests"].append(route.request.url),
                    route.abort(),
                ),
            )
        page = context.new_page()
        page.on("pageerror", lambda error: evidence["errors"].append(str(error)))
        page.on(
            "console",
            lambda msg: (
                evidence["errors"].append(msg.text) if msg.type == "error" else None
            ),
        )
        page.goto(Path(page_file).resolve().as_uri())
        page.evaluate(
            "async () => { await window.pixViewerReady; await window.pixVisualization.ready; }"
        )
        assert page.get_by_role("tab").count() == 1
        assert page.locator("[data-catalog-sequence]").count() == 2
        summary = page.locator(f'[data-catalog-summary="{normal.id}"]').inner_text()
        assert "1/5 variants (20%)" in summary and "60/100 cases (60%)" in summary
        evidence["checks"].append("variant-count percentage and separate case coverage")
        page.get_by_role("button", name="Top 80% variants", exact=True).click()
        assert page.locator("[data-catalog-sequence]").count() == 8
        choice = page.get_by_label("Select 정상 variant 5", exact=True)
        choice.focus()
        page.keyboard.press("Space")
        assert page.locator("[data-catalog-sequence]").count() == 9
        assert (
            page.evaluate("document.activeElement.getAttribute('aria-label')")
            == "Select 정상 variant 5"
        )
        evidence["checks"].append("presets and keyboard selection retain focus")
        before = page.evaluate("window.pixVisualization.exportCatalogSelection()")
        page.get_by_label("Find labels or values", exact=True).fill("재작업")
        assert page.locator("[data-catalog-sequence]").count() == 9
        assert (
            page.evaluate("window.pixVisualization.exportCatalogSelection().groups")
            == before["groups"]
        )
        page.get_by_label("Find labels or values", exact=True).fill("")
        page.get_by_label("Show catalog group 비정상 · 재작업", exact=True).uncheck()
        assert page.locator("[data-catalog-sequence]").count() == 5
        evidence["checks"].append("search and visibility preserve membership")
        with page.expect_download() as download:
            page.get_by_role("button", name="Save selection", exact=True).click()
        selection_file = folder / "selection.json"
        download.value.save_as(selection_file)
        saved = json.loads(selection_file.read_text())
        page.get_by_role("button", name="Clear variants", exact=True).click()
        assert page.locator("[data-catalog-sequence]").count() == 0
        page.get_by_label("Load variant selection", exact=True).set_input_files(
            selection_file
        )
        page.wait_for_function(
            "window.pixVisualization.exportCatalogSelection().groups.some(g => g.selected_variant_ids.length > 0)"
        )
        assert (
            page.evaluate("window.pixVisualization.exportCatalogSelection()") == saved
        )
        bad_file = tmp_path / "different.json"
        bad_file.write_text(json.dumps(dict(saved, catalog_id="different source")))
        page.get_by_label("Load variant selection", exact=True).set_input_files(
            bad_file
        )
        page.get_by_text(
            "Selection belongs to a different catalog or profile.", exact=True
        ).wait_for()
        assert (
            page.evaluate("window.pixVisualization.exportCatalogSelection()") == saved
        )
        evidence["checks"].append("download, restore and source mismatch rejection")
        with page.expect_download() as download:
            page.get_by_role("button", name="Save SVG", exact=True).click()
        svg_file = folder / "catalog-selected.svg"
        download.value.save_as(svg_file)
        root = ElementTree.parse(svg_file).getroot()
        assert (
            json.loads(root.find("{http://www.w3.org/2000/svg}metadata").text)[
                "selection"
            ]
            == saved
        )
        assert not any(
            x.tag.rsplit("}", 1)[-1] in {"script", "foreignObject"} for x in root.iter()
        )
        evidence["checks"].append("SVG retains actual view and selection metadata")
        page.get_by_label("Show catalog group 비정상 · 재작업", exact=True).check()
        page.get_by_role("button", name="Top 80% variants", exact=True).click()
        assert page.evaluate("document.documentElement.scrollHeight") < 3000
        page.screenshot(path=folder / "catalog-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 1
        page.screenshot(path=folder / "catalog-mobile.png", full_page=True)
        evidence["checks"].append("390px page without horizontal overflow")
        assert not evidence["requests"] and not evidence["errors"]
        evidence["checks"].append("offline without page or console errors")
        context.close()
        browser.close()
    (folder / "browser-evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
