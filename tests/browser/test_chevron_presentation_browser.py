"""Real production exports: fixed/auto orientation and neutral chevron marks.

Opt in with PIX_RUN_BROWSER=1. This uses the installed Node Playwright driver,
never a mocked DOM/layout and never downloads browser/runtime dependencies.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from pix.viewer import export_html, write_visualization

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / ".artifacts/2026-09-17-validation-neutral-chevron-default/presentation"
pytestmark = pytest.mark.browser
SCENARIOS = (
    "fixed-orientations",
    "default-neutral",
    "auto-resize-state",
    "neutral-selection-svg",
    "hostile-labels",
)

HARNESS = r"""
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.argv[2]);
const gallery = process.argv[3], artifacts = process.argv[4];
const read = name => JSON.parse(fs.readFileSync(path.join(gallery,name+'.json'),'utf8'));
const results = {browser:null,checks:{},requests:[],errors:[],screenshots:[],observations:[]};
let browser;
async function open(name,width=1024) {
  const context=await browser.newContext({viewport:{width,height:960}}),page=await context.newPage(),errors=[],requests=[];
  page.on('pageerror',error=>errors.push(String(error)));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  await context.route(/^https?:/,route=>{requests.push(route.request().url());route.abort();});
  await page.goto(pathToFileURL(path.join(gallery,name+'.html')).href);
  await page.evaluate(async()=>{await window.pixViewerReady;await window.pixVisualization.ready;});
  return {page,context,name,errors,requests};
}
async function close(view) {
  results.errors.push(...view.errors);results.requests.push(...view.requests);await view.context.close();
  assert.deepEqual(view.requests,[],'offline export requested external content');
  assert.deepEqual(view.errors,[],'page or console errors');
}
async function panel(page,id) {await page.evaluate(id=>window.pixVisualization.selectPanel(id),id);}
async function shot(view,suffix) {
  const name=view.name+'-'+suffix+'.png';
  await view.page.locator('.pv-canvas').screenshot({path:path.join(artifacts,name)});results.screenshots.push(name);
}
async function identities(page,expected) {
  const actual=await page.locator('.pv-chevron-shape').evaluateAll(nodes=>nodes.map(n=>({event:n.dataset.eventId,lane:n.dataset.laneId,start:Number(n.dataset.start),end:Number(n.dataset.end)})));
  const wanted=expected.events.flatMap(e=>e.lane_ids.map(lane=>({event:e.id,lane,start:e.start,end:e.end})));
  assert.deepEqual(actual,wanted);return actual.length;
}
async function geometry(page,expected,orientation) {
  assert.equal(await page.locator('.pv-svg').getAttribute('data-chevron-orientation'),orientation);
  const actual=await page.locator('.pv-chevron-shape').evaluateAll(nodes=>nodes.map(n=>{const b=n.getBBox();return {event:n.dataset.eventId,x:b.x,y:b.y,width:b.width,height:b.height};}));
  for(const event of expected.events) {
    const rows=actual.filter(r=>r.event===event.id),axis=orientation==='horizontal'?'x':'y',size=orientation==='horizontal'?'width':'height';
    assert.equal(new Set(rows.map(r=>r[axis])).size,1,'shared event flow positions must align');
    assert.equal(new Set(rows.map(r=>r[size])).size,1,'shared event inclusive spans must agree');
  }
  const overflow=await page.evaluate(()=>document.documentElement.scrollWidth-innerWidth);
  assert(overflow<=1,`page overflow ${overflow}`);
}
async function labelBounds(page) {
  return page.locator('.pv-chevron-event').evaluateAll(groups=>groups.flatMap(group=>{
    let box=null; const failures=[];
    for(const node of group.children) {
      if(node.classList.contains('pv-chevron-shape')) box=node.getBBox();
      if(node.classList.contains('pv-chevron-label')) {
        const b=node.getBBox();
        if(!box||b.x<box.x-1||b.y<box.y-1||b.x+b.width>box.x+box.width+1||b.y+b.height>box.y+box.height+1)
          failures.push({event:group.dataset.eventId,text:node.textContent,label:{x:b.x,y:b.y,w:b.width,h:b.height},span:box?{x:box.x,y:box.y,w:box.width,h:box.height}:null});
      }
    }
    return failures;
  }));
}
async function laneLabelBounds(page,panel,orientation) {
  return page.evaluate(({panel,orientation})=>{
    const geometry=window.PIXChevronGeometry.layout(panel,{orientation,style:'neutral',availableWidth:document.querySelector('.pv-canvas').getBoundingClientRect().width});
    return [...document.querySelectorAll('.pv-chevron-lane-label')].flatMap((label,index)=>{
      const box=geometry.lanes[index], failures=[];
      for(const node of [label,label.nextElementSibling]) {
        const b=node.getBBox();
        if(b.width>box.labelMaxWidth+1)failures.push({lane:box.id,text:node.textContent,width:b.width,available:box.labelMaxWidth});
      }
      return failures;
    });
  },{panel,orientation});
}
const scenarios={};
scenarios['fixed-orientations']=async()=>{
  for(const style of ['classic','neutral']) for(const orientation of ['horizontal','vertical']) {
    const name=style+'-'+orientation,view=await open(name),page=view.page,document=read(name);
    try {
      for(const width of [1024,390]) {
        await page.setViewportSize({width,height:960});
        for(const chevron of document.panels.filter(p=>p.kind==='chevron')) {
          await panel(page,chevron.id);await geometry(page,chevron,orientation);
          const appearances=await identities(page,chevron);assert([9,10].includes(appearances));
          assert.equal(await page.locator('.pv-svg').getAttribute('data-chevron-style'),style);
          if(style==='classic'&&orientation==='horizontal') {
            const spans=await page.locator('.pv-chevron-shape').evaluateAll(nodes=>nodes.map(n=>({width:n.getBBox().width,start:Number(n.dataset.start),end:Number(n.dataset.end)})));
            for(const row of spans)assert.equal(row.width,(row.end-row.start+1)*154-10,'explicit classic must retain its original inclusive-slot geometry');
            assert.equal(await page.locator('.pv-chevron-glyph').count(),0);
          }
          if(style==='neutral') {
            assert.deepEqual(await labelBounds(page),[],'short labels must fit their reserved spans');
            const inspect=chevron.events.find(e=>e.label==='Inspect');
            assert.equal(await page.locator('.pv-chevron-event').filter({has:page.locator(`[data-event-id="${inspect.id}"]`)}).locator('.pv-chevron-label').count(),inspect.lane_ids.length,'short Inspect label should stay on one line');
            if(width===1024) {
              const clipped=await page.locator('.pv-chevron-shape').evaluateAll(nodes=>{
                const canvas=document.querySelector('.pv-canvas').getBoundingClientRect();
                return nodes.filter(node=>{const b=node.getBoundingClientRect();return b.left<canvas.left-1||b.top<canvas.top-1||b.right>canvas.right+1||b.bottom>canvas.bottom+1;}).map(n=>n.dataset.eventId);
              });
              assert.deepEqual(clipped,[],'desktop default should show every appearance including Join');
            }
          }
          if(style==='classic'&&width===1024&&chevron.frequency===2)await shot(view,'fixed');
          results.observations.push({style,orientation,width,panel:chevron.id,appearances});
        }
      }
    } finally {await close(view);}
  }
};
scenarios['default-neutral']=async()=>{
  const view=await open('default'),page=view.page,document=read('default');
  try {
    for(const chevron of document.panels.filter(p=>p.kind==='chevron')) {
      await panel(page,chevron.id);
      assert.equal(await page.locator('.pv-svg').getAttribute('data-chevron-style'),'neutral');
      assert.equal(await page.locator('.pv-svg').getAttribute('data-chevron-orientation-requested'),'horizontal');
      await geometry(page,chevron,'horizontal');
      const appearances=await identities(page,chevron);
      assert.equal(await page.locator('.pv-chevron-glyph').count(),appearances);
      assert.equal(await page.locator('.pv-chevron-span').count(),appearances);
      assert.equal(await page.locator('.pv-chevron-shape').first().evaluate(n=>getComputedStyle(n).fill),'rgba(0, 0, 0, 0)');
      assert.equal(await page.locator('.pv-chevron-glyph').first().evaluate(n=>getComputedStyle(n).fill),'rgb(104, 117, 132)');
      assert.deepEqual(await labelBounds(page),[],'default labels must fit their reserved spans');
      const svg=await page.evaluate(()=>window.pixVisualization.exportSVG());
      const metadata=await page.evaluate(svg=>JSON.parse(new DOMParser().parseFromString(svg,'image/svg+xml').querySelector('metadata').textContent),svg);
      assert.deepEqual(metadata.panel,chevron);assert.deepEqual(metadata.provenance,document.provenance);
      await shot(view,chevron.id.split('/')[0]);
    }
    await page.setViewportSize({width:390,height:960});
    await panel(page,document.panels[0].id);
    await geometry(page,document.panels[0],'horizontal');
  } finally {await close(view);}
};
scenarios['auto-resize-state']=async()=>{
  for(const style of ['classic','neutral']) {
    const name=style+'-auto',view=await open(name,1600),page=view.page,document=read(name),chevron=document.panels[0];
    try {
      await geometry(page,chevron,'horizontal');
      const event=chevron.events.find(e=>e.label==='Fork');
      await page.locator('.pv-chevron-event').filter({has:page.locator(`[data-event-id="${event.id}"]`)}).focus();
      await page.keyboard.press('Enter');
      await page.getByLabel('Find labels or values',{exact:true}).fill('Join');
      for(const [width,orientation] of [[390,'vertical'],[1600,'horizontal']]) {
        await page.setViewportSize({width,height:960});
        await page.waitForFunction(orientation=>document.querySelector('.pv-svg')?.dataset.chevronOrientation===orientation,orientation);
        await page.evaluate(async()=>{await window.pixVisualization.ready;});
        await geometry(page,chevron,orientation);await identities(page,chevron);
        assert.equal(await page.locator('.pv-chevron-event.is-selected').getAttribute('data-event-id'),event.id);
        assert.equal(await page.locator('.pv-chevron-event.is-selected .pv-chevron-shape').count(),event.lane_ids.length);
        assert.equal(await page.getByLabel('Find labels or values',{exact:true}).inputValue(),'Join');
        assert.equal(await page.locator('.pv-chevron-event.is-match').count(),1);
        assert((await page.locator('.pv-inspector').textContent()).includes(event.id));
      }
    } finally {await close(view);}
  }
};
scenarios['neutral-selection-svg']=async()=>{
  for(const orientation of ['horizontal','vertical']) {
    const name='neutral-'+orientation,view=await open(name),page=view.page,document=read(name);
    try {
      for(const chevron of document.panels.filter(p=>p.kind==='chevron')) {
        await panel(page,chevron.id);await shot(view,chevron.id.split('/')[0]);
        const event=chevron.events.find(e=>e.label==='Fork');
        const target=page.locator('.pv-chevron-event').filter({has:page.locator(`[data-event-id="${event.id}"]`)});
        await target.locator('.pv-chevron-glyph').first().click();
        assert.equal(await page.locator('.pv-chevron-event.is-selected .pv-chevron-glyph').count(),event.lane_ids.length);
        assert.equal(await page.locator('.pv-chevron-event.is-selected .pv-chevron-shared-link').evaluate(n=>getComputedStyle(n).opacity),'1');
        const collisions=await page.locator('.pv-chevron-event.is-selected').evaluate(group=>{
          const links=[...group.querySelectorAll('.pv-chevron-shared-link')],hits=[];
          for(const text of group.querySelectorAll('.pv-chevron-label')) {
            const b=text.getBBox();let found=false;
            for(let x=Math.ceil(b.x);x<=b.x+b.width&&!found;x++)for(let y=Math.ceil(b.y);y<=b.y+b.height&&!found;y++)
              if(links.some(link=>link.isPointInStroke(new DOMPoint(x,y))))found=true;
            if(found)hits.push(text.textContent);
          }
          return hits;
        });
        assert.deepEqual(collisions,[],'shared-event connector must not run through activity labels');
        await shot(view,chevron.id.split('/')[0]+'-selected');
        const svg=await page.evaluate(()=>window.pixVisualization.exportSVG());
        const parsed=await page.evaluate(svg=>{
          const doc=new DOMParser().parseFromString(svg,'image/svg+xml');
          return {errors:doc.querySelectorAll('parsererror').length,orientation:doc.documentElement.dataset.chevronOrientation,style:doc.documentElement.dataset.chevronStyle,
            shapes:[...doc.querySelectorAll('.pv-chevron-shape')].map(n=>({event:n.dataset.eventId,lane:n.dataset.laneId,start:Number(n.dataset.start),end:Number(n.dataset.end)})),
            metadata:JSON.parse(doc.querySelector('metadata').textContent),css:[...doc.querySelectorAll('style')].map(n=>n.textContent).join('\n')};
        },svg);
        assert.equal(parsed.errors,0);assert.equal(parsed.orientation,orientation);assert.equal(parsed.style,'neutral');
        assert.deepEqual(parsed.metadata.panel,chevron);assert.deepEqual(parsed.metadata.provenance,document.provenance);
        assert.deepEqual(parsed.shapes,chevron.events.flatMap(e=>e.lane_ids.map(lane=>({event:e.id,lane,start:e.start,end:e.end}))));
        assert(parsed.css.includes('.pv-chevron-neutral-view .pv-chevron-glyph'));assert(parsed.css.includes('.pv-chevron-span'));
        const download=page.waitForEvent('download');await page.getByRole('button',{name:'Save SVG',exact:true}).click();
        const targetPath=path.join(artifacts,name+'-'+chevron.id.split('/')[0]+'.svg');await(await download).saveAs(targetPath);
        assert.equal(fs.readFileSync(targetPath,'utf8'),svg);
        // A saved SVG must paint its own neutral glyphs without the HTML stylesheet.
        const standalone=await view.context.newPage();await standalone.goto(pathToFileURL(targetPath).href);
        assert.equal(await standalone.locator('.pv-chevron-event:not(.is-selected) .pv-chevron-glyph').first().evaluate(n=>getComputedStyle(n).fill),'rgb(104, 117, 132)');
        assert.equal(await standalone.locator('.pv-chevron-shape').first().evaluate(n=>getComputedStyle(n).stroke),'rgba(0, 0, 0, 0)');
        await standalone.close();
      }
    } finally {await close(view);}
  }
};
scenarios['hostile-labels']=async()=>{
  for(const orientation of ['horizontal','vertical']) {
    const name='hostile-'+orientation,view=await open(name),page=view.page,document=read(name),chevron=document.panels[0];
    try {
      assert.equal(await page.evaluate(()=>typeof window.__pixInjection),'undefined');
      assert.equal(await page.locator('.pv-canvas img,.pv-canvas script,.pv-canvas foreignObject').count(),0);
      assert.deepEqual(await labelBounds(page),[],'multilingual labels must fit reserved spans');
      assert.deepEqual(await laneLabelBounds(page,chevron,orientation),[],'multilingual lane labels must fit their header reservation');
      for(const event of chevron.events) {
        await page.locator('.pv-chevron-event').filter({has:page.locator(`[data-event-id="${event.id}"]`)}).focus();await page.keyboard.press('Enter');
        assert.equal(await page.locator('.pv-inspector h2').textContent(),event.label);
      }
      const svg=await page.evaluate(()=>window.pixVisualization.exportSVG());
      assert.equal(await page.evaluate(svg=>new DOMParser().parseFromString(svg,'image/svg+xml').querySelectorAll('parsererror,img,script,foreignObject').length,svg),0);
      await shot(view,'long-labels');
    } finally {await close(view);}
  }
};
(async()=>{
  fs.mkdirSync(artifacts,{recursive:true});browser=await chromium.launch({headless:true});results.browser=browser.version();
  for(const [name,run]of Object.entries(scenarios)){
    const started=Date.now();try{await run();results.checks[name]={passed:true,milliseconds:Date.now()-started};}
    catch(error){results.checks[name]={passed:false,error:String(error.stack),milliseconds:Date.now()-started};}
  }
  await browser.close();fs.writeFileSync(path.join(artifacts,'browser-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results.checks));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""


def _write_exports(directory: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "pix_chevron_presentation_demo", ROOT / "examples/graphviz_variant_demo.py"
    )
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    source = demo.build_demo_documents()["variant-chevrons"]
    first = next(
        panel
        for panel in source.panels
        if panel.kind == "chevron" and panel.frequency == 2
    )
    source = replace(
        source,
        panels=(first,)
        + tuple(panel for panel in source.panels if panel.id != first.id),
    )
    directory.mkdir(parents=True, exist_ok=True)
    for style in ("classic", "neutral"):
        for orientation in ("horizontal", "vertical", "auto"):
            name = f"{style}-{orientation}"
            export_html(
                source,
                directory / f"{name}.html",
                chevron_orientation=orientation,
                chevron_style=style,
                overwrite=True,
            )
            write_visualization(source, directory / f"{name}.json", overwrite=True)
    export_html(source, directory / "default.html", overwrite=True)
    write_visualization(source, directory / "default.json", overwrite=True)
    labels = (
        '<img src=x onerror="window.__pixInjection=1"> & <script>window.__pixInjection=1</script>',
        "검사 승인 확인 및 품질 검증 " * 12,
        "WWWWMMMMWWWWMMMMWWWWMMMMWWWWMMMM",
        "材料確認・納品準備・品質保証・出荷承認",
        "Approve / prüfen / révision / Δοκιμή / 🔍 " * 5,
    )
    hostile_panel = replace(
        first,
        lanes=tuple(
            replace(
                lane,
                label=f"다국어 객체 제목 {index} " * 10,
                object_id=f"객체 식별자 {index} " * 12,
                object_type="材料確認・納品準備・품질 검사 " * 6,
            )
            for index, lane in enumerate(first.lanes)
        ),
        events=tuple(
            replace(event, label=labels[index % len(labels)])
            for index, event in enumerate(first.events)
        ),
    )
    hostile = replace(source, panels=(hostile_panel,) + source.panels[1:])
    for orientation in ("horizontal", "vertical"):
        name = f"hostile-{orientation}"
        export_html(
            hostile,
            directory / f"{name}.html",
            chevron_orientation=orientation,
            chevron_style="neutral",
            overwrite=True,
        )
        write_visualization(hostile, directory / f"{name}.json", overwrite=True)


@pytest.fixture(scope="module")
def browser_evidence(tmp_path_factory):
    if os.environ.get("PIX_RUN_BROWSER") != "1":
        pytest.skip(
            "set PIX_RUN_BROWSER=1 for real chevron presentation browser checks"
        )
    node = shutil.which("node")
    module = Path(
        os.environ.get(
            "PIX_PLAYWRIGHT_MODULE",
            str(ROOT / ".venv/Lib/site-packages/playwright/driver/package"),
        )
    ).resolve()
    if node is None or not (module / "package.json").is_file():
        pytest.fail("Requested browser run requires Node and installed Playwright")

    def hashes():
        paths = [
            p
            for p in (ROOT / "src/pix/viewer").rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        ]
        return {
            p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)
        }

    before = hashes()
    gallery = tmp_path_factory.mktemp("chevron-presentation")
    _write_exports(gallery)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    harness = ARTIFACTS / "browser-harness.cjs"
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
    result.update(
        gallery=str(gallery), source_hashes_before=before, source_hashes_after=hashes()
    )
    result["source_changed_during_run"] = [
        key
        for key in sorted(before.keys() | result["source_hashes_after"].keys())
        if before.get(key) != result["source_hashes_after"].get(key)
    ]
    (ARTIFACTS / "browser-results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert result["source_changed_during_run"] == [], (
        "Viewer changed during browser run; rerun after freeze"
    )
    return result


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_chevron_presentation_in_real_browser(browser_evidence, scenario):
    result = browser_evidence["checks"][scenario]
    assert result["passed"], result.get("error", "browser scenario failed")
