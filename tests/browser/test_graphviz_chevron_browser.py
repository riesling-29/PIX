"""Opt-in real Chromium regression checks for Graphviz and variant chevrons.

Uses the already-installed Node Playwright driver; never downloads a browser.
Run with PIX_RUN_BROWSER=1. Products remain offline, including Graphviz WASM.
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

from pix.viewer import export_html

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".artifacts/2026-09-17-validation-neutral-chevron-default/graphviz"
pytestmark = pytest.mark.browser
SCENARIOS = (
    "graphviz-default",
    "legacy-default",
    "legacy-filters-counts",
    "chevron-coordinates-frequency",
    "chevron-selection-export",
    "execution-helper",
    "small-viewport",
)

HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2]);
const gallery = process.argv[3], artifacts = process.argv[4];
const read = name => JSON.parse(fs.readFileSync(path.join(gallery, name + '.json'), 'utf8'));
const results = {browser:null,checks:{},requests:[],errors:[],screenshots:[],graphvizVersions:[],chevrons:[]};
const scenarios = {}; let browser;
async function open(name,width=1600) {
  const context = await browser.newContext({viewport:{width,height:1000}});
  const page = await context.newPage(), errors=[], requests=[];
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error') errors.push(message.text());});
  await context.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
  await page.goto(pathToFileURL(path.join(gallery,name+'.html')).href);
  await page.evaluate(async()=>{await window.pixViewerReady;});
  return {page,context,name,errors,requests};
}
async function close(view) {
  results.errors.push(...view.errors); results.requests.push(...view.requests);
  await view.context.close();
  assert.deepEqual(view.requests,[],'offline view requested external content');
  assert.deepEqual(view.errors,[],'page or console errors');
}
async function shot(view,suffix='') {
  const name=view.name+suffix+'.png';
  await view.page.screenshot({path:path.join(artifacts,name),fullPage:true});
  results.screenshots.push(name);
}
async function version(page) {
  assert.equal(await page.evaluate(()=>typeof window.ELK),'undefined');
  const value=await page.evaluate(async()=>(await window.Viz.instance()).graphvizVersion);
  const expected=await page.evaluate(()=>JSON.parse(document.getElementById('pix-viewer-license').textContent).provenance.graphviz.version);
  assert.equal(value,expected); results.graphvizVersions.push(value);
}
async function panel(page,id) {await page.evaluate(id=>window.pixVisualization.selectPanel(id),id);}
scenarios['graphviz-default']=async()=>{
  const view=await open('graphviz-dfg'), page=view.page, graph=read(view.name).panels.find(p=>p.kind==='graph');
  try {
    await version(page);
    assert.equal(await page.locator('.pv-node-shape').count(),graph.nodes.length);
    assert.equal(await page.locator('.pv-edge-line').count(),graph.edges.length);
    assert.equal(await page.locator('.pv-edge-label').count(),graph.edges.filter(e=>e.label||e.metrics.length).length);
    const routes=await page.locator('.pv-edge-line').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('d')));
    assert(routes.every(route=>route.includes(' C ')&&!route.includes('NaN')),'Graphviz cubic routes required');
    assert((await page.locator('.pv-status').textContent()).includes('Graphviz'));
    fs.writeFileSync(path.join(artifacts,'graphviz-dfg.svg'),await page.evaluate(()=>window.pixVisualization.exportSVG()));
    await shot(view);
  } finally {await close(view);}
};
scenarios['legacy-default']=async()=>{
  for(const name of ['legacy-ocdfg','legacy-pn','legacy-ocpn']) {
    const view=await open(name),page=view.page,graph=read(name);
    try {
      await version(page);
      assert.equal(await page.evaluate(()=>window.PIXViewerLayoutEngine),'graphviz');
      assert.equal(await page.locator('.pix-node').count(),graph.nodes.length);
      assert.equal(await page.locator('.pix-edge').count(),graph.edges.length);
      const routes=await page.locator('.pix-edge-line').evaluateAll(nodes=>nodes.map(n=>n.getAttribute('d')));
      assert(routes.every(route=>/\sC\s*-?\d/.test(route)&&!route.includes('NaN')));
      if(name!=='legacy-ocdfg') {
        assert.equal(await page.locator('.pix-final-ring').count(),graph.nodes.filter(n=>n.final_count>0).length);
        assert.equal(await page.getByLabel('Edge counting unit').count(),0);
        assert.equal(graph.origin,'discovered');
        assert((await page.locator('.pix-inspector').textContent()).includes(graph.source_computation_id));
      }
      if(name==='legacy-ocpn') {
        await page.getByLabel('Show object type Item',{exact:true}).uncheck();
        const hidden=await page.locator('.pix-edge').evaluateAll(nodes=>nodes.filter(n=>getComputedStyle(n).display==='none').map(n=>n.dataset.edgeId));
        assert.deepEqual(hidden.sort(),graph.edges.filter(edge=>edge.object_type==='Item').map(edge=>edge.id).sort());
        await page.getByLabel('Show object type Item',{exact:true}).check();
      }
      const downloadEvent=page.waitForEvent('download');
      await page.getByRole('button',{name:'Save SVG',exact:true}).click();
      await (await downloadEvent).saveAs(path.join(artifacts,name+'.svg'));
      await shot(view);
    } finally {await close(view);}
  }
};
scenarios['legacy-filters-counts']=async()=>{
  const view=await open('legacy-ocdfg'),page=view.page,graph=read(view.name);
  try {
    const initial=await page.locator('#pix-graph-data').textContent();
    for(const unit of ['event_pairs','unique_objects','occurrences']) {
      await page.getByLabel('Edge counting unit').selectOption(unit);
      const actual=await page.locator('.pix-edge').evaluateAll(nodes=>Object.fromEntries(nodes.map(n=>[n.dataset.edgeId,n.querySelector('.pix-edge-label tspan:last-child').textContent])));
      for(const edge of graph.edges) assert.equal(actual[edge.id],String(edge.counts[unit]));
      assert.equal(await page.evaluate(()=>window.pixViewer.getViewState().unit),unit);
    }
    await page.getByLabel('Show object type Item',{exact:true}).uncheck();
    const hidden=await page.locator('.pix-edge').evaluateAll(nodes=>nodes.filter(n=>getComputedStyle(n).display==='none').map(n=>n.dataset.edgeId));
    assert.deepEqual(hidden.sort(),graph.edges.filter(edge=>edge.object_type==='Item').map(edge=>edge.id).sort());
    assert.equal(await page.locator('#pix-graph-data').textContent(),initial);
    await page.getByLabel('Show object type Item',{exact:true}).check();
    await shot(view,'-occurrences');
  } finally {await close(view);}
};
scenarios['chevron-coordinates-frequency']=async()=>{
  const view=await open('variant-chevrons'),page=view.page,document=read(view.name);
  try {
    const chevrons=document.panels.filter(p=>p.kind==='chevron');
    assert.deepEqual(chevrons.map(p=>[p.frequency,p.population]).sort(),[[1,3],[2,3]]);
    assert(document.provenance.length>=2);
    for(const [index,chevron] of chevrons.entries()) {
      await panel(page,chevron.id);
      assert.equal(await page.locator('.pv-svg').getAttribute('data-chevron-style'),'classic');
      assert.equal(await page.locator('.pv-chevron-event').count(),chevron.events.length);
      assert.equal(await page.locator('.pv-chevron-shape').count(),chevron.events.reduce((sum,e)=>sum+e.lane_ids.length,0));
      assert.equal(chevron.lanes.filter(l=>l.object_type==='Item').length,2);
      const measured=await page.locator('.pv-chevron-shape').evaluateAll(nodes=>nodes.map(n=>({event:n.dataset.eventId,lane:n.dataset.laneId,x:n.getBBox().x,width:n.getBBox().width,fill:n.getAttribute('fill')})));
      for(const event of chevron.events) {
        const appearances=measured.filter(row=>row.event===event.id);
        assert.equal(appearances.length,event.lane_ids.length);
        assert.equal(new Set(appearances.map(row=>row.x)).size,1,'shared event positions must align');
        assert(appearances.every(row=>row.width===(event.end-event.start+1)*154-10),'inclusive slot width');
        const types=new Set(event.lane_ids.map(id=>chevron.lanes.find(l=>l.id===id).object_type));
        if(types.size>1) {
          assert.equal(new Set(appearances.map(row=>row.fill)).size,1);
          assert(appearances[0].fill.startsWith('url(#'),'shared multi-type events require segmented fill');
        }
      }
      const check=chevron.events.find(e=>e.label==='Check');
      assert(check.end>check.start,'short branch must stretch before join');
      assert((await page.locator('.pv-legend').textContent()).includes(`${chevron.frequency} / 3 executions`));
      assert((await page.locator('.pv-svg').textContent()).includes('not elapsed time'));
      assert.equal(await page.locator('.pv-provenance').count(),document.provenance.length);
      results.chevrons.push({id:chevron.id,frequency:chevron.frequency,population:chevron.population,events:chevron.events.length,appearances:measured.length});
      fs.writeFileSync(path.join(artifacts,`variant-${index+1}.svg`),await page.evaluate(()=>window.pixVisualization.exportSVG()));
      await shot(view,`-${index+1}`);
    }
  } finally {await close(view);}
};
scenarios['chevron-selection-export']=async()=>{
  const view=await open('variant-chevrons',1366),page=view.page,document=read(view.name);
  try {
    const chevron=document.panels.find(p=>p.kind==='chevron'&&p.frequency===2);
    await panel(page,chevron.id);
    const event=chevron.events.find(e=>e.label==='Fork');
    const selected=page.locator('.pv-chevron-event').filter({has:page.locator(`[data-event-id="${event.id}"]`)});
    await selected.locator('polygon').first().click();
    assert.equal(await page.locator('.pv-chevron-event.is-selected polygon').count(),event.lane_ids.length);
    const details=await page.locator('.pv-inspector').textContent();
    assert(details.includes(event.id));
    for(const lane of event.lane_ids) assert(details.includes(lane));
    await page.getByLabel('Find labels or values',{exact:true}).fill('Join');
    assert.equal(await page.locator('.pv-chevron-event.is-match').count(),1);
    const svg=await page.evaluate(()=>window.pixVisualization.exportSVG());
    assert(svg.includes(event.id)&&svg.includes('<linearGradient'));
    const parsed=await page.evaluate(svg=>{const doc=new DOMParser().parseFromString(svg,'image/svg+xml');return {errors:doc.querySelectorAll('parsererror').length,events:doc.querySelectorAll('.pv-chevron-event').length};},svg);
    assert.equal(parsed.errors,0); assert.equal(parsed.events,chevron.events.length);
    const downloadEvent=page.waitForEvent('download');
    await page.getByRole('button',{name:'Save SVG',exact:true}).click();
    await (await downloadEvent).saveAs(path.join(artifacts,'chevron-downloaded.svg'));
    assert.equal(fs.readFileSync(path.join(artifacts,'chevron-downloaded.svg'),'utf8'),svg);
    await shot(view,'-selected-1366');
  } finally {await close(view);}
};
scenarios['execution-helper']=async()=>{
  const view=await open('execution-chevron'),page=view.page,document=read(view.name);
  try {
    assert.equal(document.panels.length,1);
    assert.equal(await page.locator('.pv-chevron-event').count(),document.panels[0].events.length);
    assert.equal(await page.locator('.pv-panel-kind').textContent(),'Chevron');
    await shot(view);
  } finally {await close(view);}
};
scenarios['small-viewport']=async()=>{
  const view=await open('variant-chevrons',390),page=view.page;
  try {
    await panel(page,read(view.name).panels.find(p=>p.kind==='chevron').id);
    const sizes=await page.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
    assert(sizes.scroll<=sizes.width+1);
    await page.getByRole('button',{name:'Readable',exact:true}).click();
    assert(Math.abs(await page.locator('.pv-svg').evaluate(n=>n.getScreenCTM().a)-1)<.01);
    await shot(view,'-mobile-readable');
  } finally {await close(view);}
};
(async()=>{
  fs.mkdirSync(artifacts,{recursive:true}); browser=await chromium.launch({headless:true});results.browser=browser.version();
  for(const [name,run] of Object.entries(scenarios)) {
    const started=Date.now();
    try {await run();results.checks[name]={passed:true,milliseconds:Date.now()-started};}
    catch(error){results.checks[name]={passed:false,error:String(error.stack),milliseconds:Date.now()-started};}
  }
  await browser.close();fs.writeFileSync(path.join(artifacts,'browser-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results.checks));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


@pytest.fixture(scope="module")
def browser_evidence(tmp_path_factory):
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip(
            "set PIX_RUN_BROWSER=1 to run actual Graphviz/chevron browser tests"
        )
    node = shutil.which("node")
    module = Path(
        os.environ.get(
            "PIX_PLAYWRIGHT_MODULE",
            str(ROOT / ".venv/Lib/site-packages/playwright/driver/package"),
        )
    ).resolve()
    if node is None or not (module / "package.json").is_file():
        pytest.fail(
            "Requested browser run requires Node and an installed Playwright package"
        )
    specification = importlib.util.spec_from_file_location(
        "pix_graphviz_variant_demo", ROOT / "examples/graphviz_variant_demo.py"
    )
    demo = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(demo)

    def hashes():
        paths = [
            p
            for p in (ROOT / "src/pix/viewer").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
        paths.extend(
            (ROOT / "examples/graphviz_variant_demo.py", Path(__file__).resolve())
        )
        return {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in sorted(paths)
        }

    before = hashes()
    gallery = tmp_path_factory.mktemp("graphviz-chevron-gallery")
    demo.write_gallery(gallery)
    # These scenarios specifically exercise the retained segmented classic fills
    # and 154-pixel slot geometry. The presentation suite covers the neutral default.
    export_html(
        demo.build_demo_documents()["variant-chevrons"],
        gallery / "variant-chevrons.html",
        chevron_style="classic",
        overwrite=True,
    )
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
    result.update(source_hashes_before=before, source_hashes_after=hashes())
    result["source_changed_during_run"] = [
        key
        for key in sorted(before.keys() | result["source_hashes_after"].keys())
        if before.get(key) != result["source_hashes_after"].get(key)
    ]
    (ARTIFACTS / "browser-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert result["source_changed_during_run"] == [], (
        "Viewer changed during browser run; rerun after source freeze"
    )
    return result


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_graphviz_and_chevrons_in_real_browser(browser_evidence, scenario):
    result = browser_evidence["checks"][scenario]
    assert result["passed"], result.get("error", "browser scenario failed")


def test_exported_graphs_and_chevrons_are_valid_svg(browser_evidence):
    assert all(item["passed"] for item in browser_evidence["checks"].values())
    for name in (
        "graphviz-dfg",
        "legacy-ocdfg",
        "legacy-pn",
        "legacy-ocpn",
        "variant-1",
        "variant-2",
        "chevron-downloaded",
    ):
        root = ElementTree.parse(ARTIFACTS / f"{name}.svg").getroot()
        assert root.tag == "{http://www.w3.org/2000/svg}svg"
        assert not any(
            node.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"}
            for node in root.iter()
        )


def test_graphviz_and_chevrons_remain_offline(browser_evidence):
    assert browser_evidence["errors"] == []
    assert browser_evidence["requests"] == []
    assert browser_evidence["graphvizVersions"]
    assert len(browser_evidence["chevrons"]) == 2
