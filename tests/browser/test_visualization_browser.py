"""Opt-in real Chromium regression tests for the native offline visualization.

Run with PIX_RUN_BROWSER=1. These use a locally installed Node Playwright driver
to avoid depending on Python's optional native greenlet extension. Set
PIX_PLAYWRIGHT_MODULE to a Playwright package directory if it is not installed
in the project's Python browser extra. No package or browser is downloaded.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".artifacts" / "visualization-2026-09-15" / "browser"
pytestmark = pytest.mark.browser
SCENARIOS = (
    "native-panels",
    "inspect-search",
    "pan-zoom-fit",
    "keyboard",
    "export-hostile",
    "all-panel-kinds",
    "object-type-colors",
    "provenance-scope",
    "small-viewport",
    "empty-partial",
)

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2]);
const gallery = process.argv[3], artifacts = process.argv[4];
const results = {browser: null, executable: chromium.executablePath(), requests: [], errors: [], checks: {}, panels: [], screenshots: []};
const read = name => JSON.parse(fs.readFileSync(path.join(gallery, `${name}.json`), 'utf8'));
const scenarios = {};
let browser;
async function open(name, width = 1366) {
  const context = await browser.newContext({viewport:{width,height:900}});
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if(message.type() === 'error') errors.push(message.text()); });
  await context.route(/^https?:/, route => { requests.push(route.request().url()); route.abort(); });
  await page.goto(pathToFileURL(path.join(gallery, `${name}.html`)).href);
  await page.evaluate(async () => { await window.pixViewerReady; });
  return {page, context, errors, requests, name};
}
async function close(view) {
  results.requests.push(...view.requests); results.errors.push(...view.errors);
  await view.context.close();
  assert.deepEqual(view.requests, [], 'offline document attempted a network request');
  assert.deepEqual(view.errors, [], 'console/page errors');
}
async function shot(view, suffix = '') {
  const name = `${view.name}${suffix}.png`;
  await view.page.screenshot({path:path.join(artifacts,name), fullPage:true});
  results.screenshots.push(name);
}
async function select(page, id) { await page.evaluate(id => window.pixVisualization.selectPanel(id), id); }
async function fixture() { return open('rendering-fixture'); }
scenarios['native-panels'] = async () => {
  const manifest = JSON.parse(fs.readFileSync(path.join(gallery,'manifest.json'),'utf8'));
  for (const entry of manifest.filter(entry => /^(case|object)-/.test(entry.name))) {
    const view = await open(entry.name), document = read(entry.name);
    try {
      assert.equal(await view.page.getByRole('tab').count(), document.panels.length);
      for(const panel of document.panels) {
        await select(view.page,panel.id);
        assert.equal(await view.page.locator('.pv-error').count(),0);
        if(panel.kind === 'graph') {
          assert.equal(await view.page.locator('.pv-mark:has(> .pv-node-shape)').count(),panel.nodes.length);
          assert.equal(await view.page.locator('.pv-edge-line').count(),panel.edges.length);
          assert(!(await view.page.locator('.pv-svg').getAttribute('viewBox')).includes('NaN'));
        }
        assert.equal(await view.page.locator('.pv-panel-kind').innerText(),panel.kind.toUpperCase());
        results.panels.push({page:entry.name,id:panel.id,kind:panel.kind});
      }
      if(document.panels.length) await select(view.page,document.panels[0].id);
      await shot(view);
    } finally { await close(view); }
  }
};
scenarios['inspect-search'] = async () => {
  const view = await fixture(), page = view.page, document = read(view.name);
  try {
    const original = await page.locator('#pix-visualization-data').textContent();
    const nodes = page.locator('.pv-mark:has(> .pv-node-shape)');
    assert.equal(await nodes.count(),4); assert.equal(await page.locator('.pv-edge-line').count(),4);
    const paths = await page.locator('.pv-edge-line').evaluateAll(nodes => nodes.map(n => n.getAttribute('d')));
    assert.equal(new Set(paths).size,4,'parallel edges and self-loop require distinct routes');
    await nodes.nth(1).click();
    assert((await page.locator('.pv-inspector').innerText()).includes(document.panels[0].nodes[1].label));
    assert((await page.locator('.pv-inspector').innerText()).includes(document.panels[0].nodes[1].details[0].value));
    await page.getByLabel('Find labels or values',{exact:true}).fill('Receive');
    assert.equal(await page.locator('.pv-mark.is-match').count(),1);
    assert.equal(await page.locator('.pv-search-status').innerText(),'1 matches');
    assert.equal(await page.locator('#pix-visualization-data').textContent(),original);
    await shot(view,'-inspect');
  } finally { await close(view); }
};
scenarios['pan-zoom-fit'] = async () => {
  const view = await fixture(), page = view.page;
  try {
    const svg = page.locator('.pv-svg'), initial = await svg.getAttribute('viewBox');
    await page.getByRole('button',{name:'Zoom in',exact:true}).click();
    assert.notEqual(await svg.getAttribute('viewBox'),initial);
    await page.getByRole('button',{name:'Fit',exact:true}).click();
    assert.equal(await svg.getAttribute('viewBox'),initial);
    const box = await svg.boundingBox();
    await page.mouse.move(box.x+15,box.y+15); await page.mouse.down();
    await page.mouse.move(box.x+75,box.y+55,{steps:5}); await page.mouse.up();
    assert.notEqual(await svg.getAttribute('viewBox'),initial);
    await page.getByRole('button',{name:'Fit',exact:true}).click();
    assert.equal(await svg.getAttribute('viewBox'),initial);
    await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.mouse.wheel(0,-100);
    await page.waitForFunction(initial => document.querySelector('.pv-svg').getAttribute('viewBox') !== initial, initial);
  } finally { await close(view); }
};
scenarios.keyboard = async () => {
  const view = await fixture(), page = view.page;
  try {
    await page.getByRole('tab').first().focus(); await page.keyboard.press('ArrowRight');
    await page.evaluate(() => window.pixVisualization.ready);
    assert.equal(await page.locator('.pv-panel-kind').innerText(),'MATRIX');
    await page.keyboard.press('Home'); await page.evaluate(() => window.pixVisualization.ready);
    assert.equal(await page.locator('.pv-panel-kind').innerText(),'GRAPH');
    const node = page.locator('.pv-mark:has(> .pv-node-shape)').first();
    await node.focus(); await page.keyboard.press('Enter');
    assert.equal(await page.locator('.pv-inspector h2').innerText(),'Receive');
    const svg = page.locator('.pv-svg'), initial = await svg.getAttribute('viewBox');
    await svg.focus(); await page.keyboard.press('+');
    assert.notEqual(await svg.getAttribute('viewBox'),initial);
    await page.keyboard.press('0'); assert.equal(await svg.getAttribute('viewBox'),initial);
    await page.keyboard.press('1');
    assert(Math.abs(await svg.evaluate(node => node.getScreenCTM().a) - 1) < 0.01);
  } finally { await close(view); }
};
scenarios['export-hostile'] = async () => {
  const view = await fixture(), page = view.page;
  try {
    assert.equal(await page.locator('img,iframe,object').count(),0);
    assert.equal(await page.evaluate(() => window.pwned),undefined);
    const content = await page.evaluate(() => window.pixVisualization.exportSVG());
    fs.writeFileSync(path.join(artifacts,'hostile.svg'),content);
    const parsed = await page.evaluate(content => {
      const doc = new DOMParser().parseFromString(content,'image/svg+xml');
      return {errors:doc.querySelectorAll('parsererror').length, scripts:doc.querySelectorAll('script,img,image,foreignObject').length, root:doc.documentElement.localName};
    },content);
    assert.deepEqual(parsed,{errors:0,scripts:0,root:'svg'});
    assert(content.includes('&lt;/script&gt;'));
    const downloadEvent = page.waitForEvent('download');
    await page.getByRole('button',{name:'Save SVG',exact:true}).click();
    const download = await downloadEvent;
    await download.saveAs(path.join(artifacts,'downloaded.svg'));
    assert.equal(fs.readFileSync(path.join(artifacts,'downloaded.svg'),'utf8'),content);
  } finally { await close(view); }
};
scenarios['all-panel-kinds'] = async () => {
  const view = await fixture(), page = view.page;
  try {
    for(const panel of read(view.name).panels) {
      await page.getByRole('tab',{name:panel.title,exact:true}).click();
      await page.evaluate(() => window.pixVisualization.ready);
      assert.equal(await page.locator('.pv-panel-kind').innerText(),panel.kind.toUpperCase());
      if(panel.kind === 'matrix') {
        assert.equal(await page.locator('.pv-cell-label').count(),4);
        assert.equal(await page.locator('.pv-cell-label').allTextContents().then(a=>a.filter(t=>t==='?').length),1);
        assert.equal(await page.locator('.pv-cell-label').allTextContents().then(a=>a.filter(t=>t==='—').length),1);
      }
      if(panel.kind === 'table') {
        assert.equal(await page.locator('.pv-table tbody tr').count(),4);
        assert.equal(await page.getByRole('button',{name:'Save SVG',exact:true}).isDisabled(),true);
        await page.getByLabel('Find labels or values',{exact:true}).fill('hostile');
        assert.equal(await page.locator('.pv-table tbody tr').count(),1);
      } else {
        assert.equal(await page.locator('.pv-svg').count(),1);
        const svg = await page.evaluate(() => window.pixVisualization.exportSVG());
        fs.writeFileSync(path.join(artifacts,`${panel.kind}.svg`),svg);
      }
      await shot(view,`-${panel.kind}`);
    }
  } finally { await close(view); }
};
scenarios['small-viewport'] = async () => {
  const view = await open('rendering-fixture',390), page = view.page;
  try {
    for(const panel of read(view.name).panels) {
      await select(page,panel.id);
      const size = await page.evaluate(() => ({width:window.innerWidth,scroll:document.documentElement.scrollWidth}));
      assert(size.scroll <= size.width + 1,`${panel.kind} document overflows: ${JSON.stringify(size)}`);
      assert(await page.getByLabel('Find labels or values',{exact:true}).isVisible());
      if(panel.kind==='graph') {
        await page.locator('.pv-mark:has(> .pv-node-shape)').nth(1).focus(); await page.keyboard.press('Enter');
        assert((await page.locator('.pv-inspector').innerText()).includes(read(view.name).panels[0].nodes[1].label));
        await page.getByRole('button',{name:'Readable',exact:true}).click();
        const scale = await page.locator('.pv-svg').evaluate(node => node.getScreenCTM().a);
        assert(Math.abs(scale - 1) < 0.01, 'Readable mode must use one SVG unit per CSS pixel');
        const textSize = await page.locator('.pv-node-label').first().evaluate(node => parseFloat(getComputedStyle(node).fontSize) * node.getScreenCTM().a);
        assert(textSize >= 11.9, `Readable label size: ${textSize}`);
        await shot(view,'-mobile-readable');
        await page.getByRole('button',{name:'Fit',exact:true}).click();
      }
      await shot(view,`-mobile-${panel.kind}`);
    }
  } finally { await close(view); }
};
scenarios['object-type-colors'] = async () => {
  const view = await open('object-flow'), page = view.page;
  try {
    const panel = read(view.name).panels.find(panel => panel.kind === 'graph');
    const colors = await page.locator('.pv-edge-line').evaluateAll(lines => lines.map(line => getComputedStyle(line).stroke));
    const byType = new Map();
    for(let i=0;i<panel.edges.length;i++) {
      const type = panel.edges[i].details.find(field => field.name === 'object_type').value;
      if(byType.has(type)) assert.equal(colors[i],byType.get(type));
      else byType.set(type,colors[i]);
    }
    assert.equal(byType.size,2); assert.equal(new Set(byType.values()).size,2);
    const metrics = await page.locator('.pv-node-metric').allTextContents();
    assert(metrics.some(value => value === 'events: 2'));
    assert(!metrics.some(value => value.endsWith('…')),'short metrics should remain readable');
  } finally { await close(view); }
};
scenarios['provenance-scope'] = async () => {
  const view = await open('case-models'), page = view.page, document = read(view.name);
  try {
    assert(document.provenance.some(source => source.panel_ids.length));
    assert(document.provenance.some(source => source.input_path.length));
    for(const panel of document.panels) {
      await select(page,panel.id);
      const expected = document.provenance.filter(source => source.panel_ids.length ? source.panel_ids.includes(panel.id) : !source.input_path.length);
      assert.equal(await page.locator('.pv-provenance').count(),expected.length);
      const visible = await page.locator('.pv-inspector').textContent();
      const expectedIDs = new Set(expected.flatMap(source => [source.calculation_id,source.model_digest,source.source_digest]).filter(Boolean));
      for(const identity of expectedIDs) assert(visible.includes(identity),`missing selected-panel provenance ${identity}`);
      const excluded = document.provenance.filter(source => !expected.includes(source));
      for(const source of excluded) {
        for(const identity of [source.calculation_id,source.model_digest].filter(Boolean)) {
          if(!expectedIDs.has(identity)) assert(!visible.includes(identity),`another input's provenance leaked into ${panel.id}`);
        }
      }
    }
    await select(page,document.panels[0].id);
    await shot(view,'-scoped-provenance');
  } finally { await close(view); }
  const partial = await open('partial');
  try {
    const failed = read('partial').provenance.filter(source => !source.panel_ids.length && source.input_path.length);
    assert(failed.length > 0, 'fixture must contain a real unassociated failed input');
    assert.equal(await partial.page.locator('.pv-provenance').count(),0);
    const visible = await partial.page.locator('.pv-inspector').textContent();
    for(const source of failed) if(source.calculation_id) assert(!visible.includes(source.calculation_id));
  } finally { await close(partial); }
};
scenarios['empty-partial'] = async () => {
  for(const name of ['empty','partial']) {
    const view = await open(name), page = view.page;
    try {
      assert.equal(await page.locator('.pv-document-status').innerText(),name === 'empty' ? 'OK' : 'PARTIAL');
      if(name==='empty') {
        assert.equal(await page.locator('.pv-svg').count(),0);
        assert((await page.locator('.pv-status').innerText()).includes('No panels supplied'));
      } else {
        assert((await page.locator('.pv-warning').innerText()).includes('suffix is unknown'));
        assert.equal(await page.locator('.pv-mark:has(> .pv-node-shape)').count(),1);
      }
      await shot(view);
    } finally { await close(view); }
  }
};
(async()=>{
  fs.mkdirSync(artifacts,{recursive:true});
  browser = await chromium.launch({headless:true}); results.browser = browser.version();
  for(const [name,run] of Object.entries(scenarios)) {
    const start=Date.now();
    try { await run(); results.checks[name]={passed:true,milliseconds:Date.now()-start}; }
    catch(error) { results.checks[name]={passed:false,error:String(error.stack),milliseconds:Date.now()-start}; }
  }
  await browser.close();
  fs.writeFileSync(path.join(artifacts,'browser-results.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify({browser:results.browser,checks:results.checks,panels:results.panels.length,requests:results.requests.length,errors:results.errors.length}));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


@pytest.fixture(scope="module")
def browser_evidence(tmp_path_factory):
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip(
            "set PIX_RUN_BROWSER=1 to run actual native visualization browser tests"
        )
    node = shutil.which("node")
    if node is None:
        pytest.fail(
            "Requested browser run requires Node and a local Playwright package"
        )
    module = Path(
        os.environ.get(
            "PIX_PLAYWRIGHT_MODULE",
            str(ROOT / ".venv/Lib/site-packages/playwright/driver/package"),
        )
    ).resolve()
    if not (module / "package.json").is_file():
        pytest.fail(
            "Requested browser run requires PIX_PLAYWRIGHT_MODULE pointing to an installed package"
        )
    specification = importlib.util.spec_from_file_location(
        "pix_native_visualization_demo", ROOT / "examples/native_visualization_demo.py"
    )
    demo = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(demo)

    def source_hashes():
        tracked = sorted(
            path
            for path in (ROOT / "src/pix/viewer").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        )
        tracked += [
            ROOT / "examples/native_visualization_demo.py",
            Path(__file__).resolve(),
        ]
        return {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in tracked
        }

    before = source_hashes()
    gallery = tmp_path_factory.mktemp("native-visualization-gallery")
    demo.write_gallery(gallery)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    harness = gallery / "browser-harness.cjs"
    harness.write_text(HARNESS, encoding="utf-8")
    completed = subprocess.run(
        [node, str(harness), str(module), str(gallery), str(ARTIFACTS)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(
        (ARTIFACTS / "browser-results.json").read_text(encoding="utf-8")
    )
    result["source_hashes_before"] = before
    result["source_hashes_after"] = source_hashes()
    result["source_changed_during_run"] = [
        path
        for path in sorted(before.keys() | result["source_hashes_after"].keys())
        if result["source_hashes_after"].get(path) != before.get(path)
    ]
    (ARTIFACTS / "browser-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert result["source_changed_during_run"] == [], (
        "Viewer changed during browser run; rerun after source freeze"
    )
    return result


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_native_offline_browser_scenario(browser_evidence, scenario):
    result = browser_evidence["checks"][scenario]
    assert result["passed"], result.get("error", "browser scenario failed")


def test_exported_svg_is_independently_well_formed(browser_evidence):
    assert browser_evidence["checks"]["export-hostile"]["passed"]
    for name in ("hostile", "downloaded", "graph", "matrix", "chart", "timeline"):
        root = ElementTree.parse(ARTIFACTS / f"{name}.svg").getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert not any(
            node.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"}
            for node in root.iter()
        )


def test_all_browser_views_stayed_offline_and_error_free(browser_evidence):
    assert browser_evidence["requests"] == []
    assert browser_evidence["errors"] == []
    assert len(browser_evidence["panels"]) >= 20
