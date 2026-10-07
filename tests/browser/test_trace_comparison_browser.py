"""Opt-in real-browser checks for the production group comparison workflow."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pix.case_centric import compare_trace_groups
from pix.case_centric.trace_comparison import TraceComparisonSpec
from pix.viewer import build_visualization, export_html, write_visualization

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.browser

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2]);
const folder = process.argv[3], document = JSON.parse(fs.readFileSync(path.join(folder,'comparison.json'),'utf8'));
const panel = document.panels[0], evidence = {checks:[], requests:[], errors:[], browser:null};
(async()=>{
  const options = JSON.parse(process.env.PIX_BROWSER_LAUNCH_OPTIONS || '{}');
  const browser = await chromium.launch({headless:true,...options});
  evidence.browser = browser.version();
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1100},acceptDownloads:true});
    await context.route(/^https?:/, route=>{evidence.requests.push(route.request().url()); route.abort();});
    const page = await context.newPage();
    page.on('pageerror',e=>evidence.errors.push(String(e)));
    page.on('console',m=>{if(m.type()==='error') evidence.errors.push(m.text());});
    await page.goto(pathToFileURL(path.join(folder,'comparison.html')).href);
    await page.evaluate(async()=>{await window.pixViewerReady; await window.pixVisualization.ready;});
    assert.equal(await page.getByRole('tab').count(),1);
    assert.equal(await page.locator('[data-comparison-group]').count(),3);
    assert((await page.locator('[data-comparison-kind="log"]').count())>0);
    assert((await page.locator('[data-comparison-kind="model"]').count())>0);
    await page.screenshot({path:path.join(folder,'comparison-desktop.png')});
    evidence.checks.push('three labelled groups on one canvas');
    const target=panel.groups.find(g=>g.name==='비정상 · 재작업');
    const alternate=target.candidate_ids.find(id=>id!==target.selected_candidate_id);
    await page.getByLabel(`Representative for ${target.name}`,{exact:true}).selectOption(alternate);
    assert.match(await page.locator('.pv-svg').textContent(),/보류/);
    const ref=panel.groups.find(g=>g.name==='정상');
    await page.getByLabel('Reference group',{exact:true}).selectOption(target.id);
    assert.equal(await page.locator('[data-comparison-group]').first().getAttribute('data-comparison-group'),target.id);
    const allCells=await page.locator('[data-comparison-kind]').count();
    await page.getByLabel('Differences only',{exact:true}).check();
    assert((await page.locator('[data-comparison-kind]').count())<allCells);
    assert((await page.locator('[data-comparison-kind="model"]').count())>0);
    const third=panel.groups.find(g=>![ref.id,target.id].includes(g.id));
    await page.getByLabel(`Show group ${third.name}`,{exact:true}).uncheck();
    assert.equal(await page.locator('[data-comparison-group]').count(),2);
    evidence.checks.push('representative, reference, visibility and difference controls');
    const svg=await page.evaluate(()=>window.pixVisualization.exportSVG());
    const exportedText=await page.evaluate(svg=>new DOMParser().parseFromString(svg,'image/svg+xml').documentElement.textContent,svg);
    assert(exportedText.includes('Only differing columns displayed'));
    assert(exportedText.includes(`Reference group: ${target.name}`));
    fs.writeFileSync(path.join(folder,'selected-comparison.svg'),svg);
    const downloadPromise=page.waitForEvent('download');
    await page.getByRole('button',{name:'Save SVG',exact:true}).click();
    const download=await downloadPromise; await download.saveAs(path.join(folder,'downloaded-comparison.svg'));
    evidence.checks.push('download preserves selected view');
    await page.setViewportSize({width:390,height:844});
    assert((await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth))<=1,'mobile page overflows horizontally');
    await page.screenshot({path:path.join(folder,'comparison-mobile.png'),fullPage:true});
    evidence.checks.push('390px viewport without page overflow');
    await page.setViewportSize({width:1440,height:1100});
    await page.getByLabel('Differences only',{exact:true}).uncheck();
    await page.getByLabel('Reference group',{exact:true}).selectOption(ref.id);
    await page.getByLabel(`Representative for ${target.name}`,{exact:true}).selectOption(target.selected_candidate_id);
    await page.getByLabel(`Show group ${third.name}`,{exact:true}).check();
    await page.screenshot({path:path.join(folder,'comparison-desktop.png')});
    assert.deepEqual(evidence.requests,[]); assert.deepEqual(evidence.errors,[]);
    evidence.checks.push('offline and no console/page errors');
    await context.close();
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(folder,'browser-evidence.json'),JSON.stringify(evidence,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


def test_labelled_representatives_in_real_browser(tmp_path):
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip("Set PIX_RUN_BROWSER=1 for real group comparison browser checks")
    node = shutil.which("node")
    module = os.environ.get("PIX_PLAYWRIGHT_MODULE")
    assert node and module, (
        "Set PIX_PLAYWRIGHT_MODULE to an installed Playwright package"
    )
    folder = Path(os.environ.get("PIX_COMPARISON_BROWSER_ARTIFACTS", str(tmp_path)))
    folder.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "comparison_demo", ROOT / "examples/trace_group_comparison_demo.py"
    )
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    result = compare_trace_groups(
        demo.demo_log(),
        group_attribute="quality_group",
        spec=TraceComparisonSpec(reference_group="정상"),
    )
    document = build_visualization(result, title="그룹별 대표 Trace 비교 · 합성 데이터")
    export_html(
        document, folder / "comparison.html", layout_engine="native", overwrite=True
    )
    write_visualization(document, folder / "comparison.json", overwrite=True)
    harness = folder / "browser-harness.cjs"
    harness.write_text(HARNESS, encoding="utf-8")
    run = subprocess.run(
        [node, str(harness), module, str(folder)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    evidence = json.loads((folder / "browser-evidence.json").read_text())
    assert len(evidence["checks"]) == 5
    assert not evidence["errors"] and not evidence["requests"]
    for name in ("selected-comparison.svg", "downloaded-comparison.svg"):
        root = ElementTree.parse(folder / name).getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert not any(
            x.tag.rsplit("}", 1)[-1] in {"script", "foreignObject"} for x in root.iter()
        )
