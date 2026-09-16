'use strict';

// DOM-level behavior tests; real-browser SVG rendering is validated separately.
const test = require('node:test');
const assert = require('node:assert/strict');
const NS = 'http://www.w3.org/2000/svg';

class Element {
  constructor(tag, namespace = 'http://www.w3.org/1999/xhtml') {
    this.tagName = tag; this.namespaceURI = namespace; this.attributes = new Map();
    this.children = []; this.events = new Map(); this._text = ''; this.value = ''; this.disabled = false;
    this.style = {setProperty: (name, value) => { const old = this.attributes.get('style') || ''; this.attributes.set('style', `${old}${name}:${value};`); }};
    this.classList = {
      add: (...names) => { this.setAttribute('class', [...new Set([...this.classes(), ...names])].join(' ')); },
      remove: name => { this.setAttribute('class', this.classes().filter(item => item !== name).join(' ')); },
      toggle: (name, force) => { const active = force === undefined ? !this.classes().includes(name) : force; active ? this.classList.add(name) : this.classList.remove(name); return active; },
      contains: name => this.classes().includes(name),
    };
  }
  classes() { return (this.attributes.get('class') || '').split(/\s+/).filter(Boolean); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.has(name) ? this.attributes.get(name) : null; }
  removeAttribute(name) { this.attributes.delete(name); }
  get id() { return this.getAttribute('id'); }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  prepend(...children) { this.children.unshift(...children); }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  addEventListener(name, handler) { if (!this.events.has(name)) this.events.set(name, []); this.events.get(name).push(handler); }
  dispatch(name, values = {}) { const event = {target: this, preventDefault() {}, ...values}; for (const handler of this.events.get(name) || []) handler(event); }
  click() { this.dispatch('click'); }
  focus() { this.focused = true; }
  getBoundingClientRect() { return {left: 0, top: 0, width: 1000, height: 600}; }
  setPointerCapture(id) { this.capturedPointer = id; }
  querySelectorAll(selector) {
    const matches = node => selector[0] === '.' ? node.classes().includes(selector.slice(1)) : selector[0] === '[' ? node.attributes.has(selector.slice(1, -1)) : node.tagName.toLowerCase() === selector.toLowerCase();
    return this.children.flatMap(child => [...(matches(child) ? [child] : []), ...child.querySelectorAll(selector)]);
  }
  cloneNode(deep) { const copy = new Element(this.tagName, this.namespaceURI); copy.attributes = new Map(this.attributes); copy._text = this._text; if (deep) copy.children = this.children.map(child => child.cloneNode(true)); return copy; }
}
const escape = value => String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
global.document = {baseURI: 'file:///pix-tests/view.html', createElement: tag => new Element(tag), createElementNS: (namespace, tag) => new Element(tag, namespace)};
global.XMLSerializer = class { serializeToString(node) { return `<${node.tagName}${[...node.attributes].map(([key, value]) => ` ${key}="${escape(value)}"`).join('')}>${escape(node._text)}${node.children.map(child => this.serializeToString(child)).join('')}</${node.tagName}>`; } };
global.PIXNativeGeometry = require('../../src/pix/viewer/assets/native_geometry.js');
global.PIXGraphvizGeometry = require('../../src/pix/viewer/assets/graphviz_geometry.js');
const UI = require('../../src/pix/viewer/assets/visualization.js');
const container = () => new Element('main');
const documentFor = (...panels) => ({schema: 'pix.visualization.v1', title: 'PIX evidence', status: 'ok', issues: [], provenance: [], panels});
const node = (id, kind = 'activity') => ({id, label: id, kind, group: null, metrics: [], details: []});
const edge = (id, source, target) => ({id, source, target, label: id, kind: 'relation', directed: true, metrics: [], details: []});
const graph = (values = {}) => ({kind: 'graph', id: 'graph', title: 'Process', description: 'Observed evidence', nodes: [node('A'), node('B')], edges: [edge('A-B', 'A', 'B')], layout: 'layered', ...values});
const chart = (values = {}) => ({kind: 'chart', id: 'chart', title: 'Values', description: '', chart_type: 'line', x_type: 'number', x_label: 'Time', y_label: 'Duration', x_unit: 'seconds', y_unit: 'seconds', series: [{name: 'Series A', group: null, points: [{x: 0, y: 2, details: []}, {x: 1, y: 4, details: []}]}], ...values});
const timeline = (values = {}) => ({kind: 'timeline', id: 'time', title: 'Observed events', description: '', axis_type: 'relative', unit: 'seconds', lanes: [{id: 'one', label: 'Case 1', group: null}], items: [], ...values});
const chevron = (values = {}) => ({kind: 'chevron', id: 'variant', title: 'Exact variant', description: 'Precedence slots, not time', variant_id: 'v1', frequency: 2, population: 3, lanes: [{id:'o1',label:'Order_1',object_type:'Order',object_id:'order-raw',details:[]},{id:'i1',label:'Item_1',object_type:'Item',object_id:'item-raw',details:[]}], events:[{id:'shared',label:'Pack',start:0,end:1,lane_ids:['o1','i1'],details:[{name:'qualifier',value:'shared'}]},{id:'ship',label:'Ship',start:2,end:2,lane_ids:['o1'],details:[]}], ...values});
const find = (root, selector) => root.querySelectorAll(selector)[0];
const marks = root => root.querySelectorAll('.pv-mark');
const clickNamed = (root, label) => { const target = root.querySelectorAll('button').find(item => item.textContent === label); assert.ok(target, `Button ${label} exists`); target.click(); return target; };
const finiteSVG = root => { for (const element of root.querySelectorAll('svg').flatMap(svg => [svg, ...svg.querySelectorAll('path'), ...svg.querySelectorAll('rect'), ...svg.querySelectorAll('circle'), ...svg.querySelectorAll('text')])) for (const [name, value] of element.attributes) if (['d', 'x', 'y', 'cx', 'cy', 'width', 'height', 'transform', 'viewBox'].includes(name)) assert.doesNotMatch(value, /NaN|Infinity/, `${element.tagName} ${name}`); };

test('mount preserves source and renders every graph edge, node and inspectable metric', async () => {
  const host = container(), source = documentFor(graph({nodes: [node('A'), {...node('B'), metrics: [{name: 'Count', value: null, unit: 'events'}]}], edges: [edge('first', 'A', 'B'), edge('second', 'A', 'B'), edge('self', 'B', 'B')]}));
  const before = structuredClone(source), viewer = UI.mount(host, source); await viewer.ready;
  assert.deepEqual(source, before); assert.equal(marks(host).length, 5); finiteSVG(host);
  marks(host).at(-1).click(); assert.match(find(host, '.pv-inspector').textContent, /Unknown events/);
  clickNamed(host, 'Clear selection'); assert.match(find(host, '.pv-inspector').textContent, /Calculation|Select an item/);
});

test('default uses actual Graphviz curves and records its engine version', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(graph())); await viewer.ready;
  assert.match(find(host, '.pv-status').textContent, /Graphviz 16\.0\.0/);
  assert.match(find(host, '.pv-edge-line').getAttribute('d'), / C /);
  assert.ok(host.querySelectorAll('.pv-edge-arrow').length > 0);
});

test('missing default Graphviz never silently substitutes native geometry', async () => {
  const saved = global.PIXGraphvizGeometry; delete global.PIXGraphvizGeometry;
  try {
    const viewer = UI.mount(container(), documentFor(graph()));
    await assert.rejects(viewer.ready, /graphviz geometry is unavailable/);
    const host = container(), explicit = UI.mount(host, documentFor(graph()), {layoutEngine:'native'}); await explicit.ready;
    assert.match(find(host, '.pv-status').textContent, /Experimental PIX native/);
  } finally {global.PIXGraphvizGeometry = saved;}
});

test('Graphviz supplied cubic controls, arrow polygons and label center are not rerouted', async () => {
  const host = container(), geometry = {width:400,height:200,nodes:[{id:'A',x:10,y:50,width:100,height:60},{id:'B',x:280,y:50,width:100,height:60}],edges:[{id:'A-B',points:[{x:110,y:80},{x:270,y:80}],splines:[{points:[{x:110,y:80},{x:150,y:5},{x:220,y:5},{x:270,y:80}]}],labelPosition:{x:197,y:19},arrowhead:[{x:270,y:76},{x:280,y:80},{x:270,y:84}],arrowtail:[]}]};
  const viewer=UI.mount(host,documentFor(graph()),{layout:()=>geometry}); await viewer.ready;
  assert.equal(find(host,'.pv-edge-line').getAttribute('d'),'M 110 80 C 150 5 220 5 270 80');
  assert.equal(find(host,'.pv-edge-label').getAttribute('x'),'197');
  assert.equal(find(host,'.pv-edge-label').getAttribute('y'),'22');
  assert.equal(find(host,'.pv-edge-arrow').getAttribute('points'),'270,76 280,80 270,84');
  assert.equal(find(host,'.pv-edge-line').getAttribute('marker-end'),null);
});

test('chevrons share one selectable event across lanes and preserve inclusive width', async () => {
  const host=container(), source=documentFor(chevron()), before=structuredClone(source), viewer=UI.mount(host,source); await viewer.ready;
  assert.deepEqual(source,before); assert.equal(marks(host).length,2);
  assert.equal(host.querySelectorAll('.pv-chevron-shape').length,3);
  const shared=marks(host)[0], polygons=shared.querySelectorAll('.pv-chevron-shape');
  const pointX=polygon=>polygon.getAttribute('points').split(' ').map(point=>Number(point.split(',')[0]));
  assert.deepEqual(pointX(polygons[0]),pointX(polygons[1]));
  const sharedXs=pointX(polygons[0]), shipXs=pointX(marks(host)[1].querySelectorAll('.pv-chevron-shape')[0]);
  assert.equal(Math.max(...sharedXs)-Math.min(...sharedXs),298);
  assert.equal(Math.max(...shipXs)-Math.min(...shipXs),144);
  shared.click(); assert.ok(shared.classList.contains('is-selected'));
  assert.match(find(host,'.pv-inspector').textContent,/Event IDshared/);
  assert.match(find(host,'.pv-inspector').textContent,/order-raw/); assert.match(find(host,'.pv-inspector').textContent,/item-raw/);
  assert.match(find(host,'.pv-legend').textContent,/2 \/ 3 executions/);
  assert.match(viewer.exportSVG(),/OCPA-style chevrons/); finiteSVG(host);
});

test('chevrons preserve separate instances, hostile labels, search and SVG evidence', async () => {
  const panel=chevron({lanes:[{id:'o1',label:'Order_1',object_type:'Order',object_id:'first',details:[]},{id:'i1',label:'Order_2',object_type:'Order',object_id:'second',details:[]}]}), hostile='</script><img onerror="bad">';
  panel.events[0].label=hostile;
  const host=container(), viewer=UI.mount(host,documentFor(panel)); await viewer.ready;
  const polygons=host.querySelectorAll('.pv-chevron-shape'); assert.notEqual(polygons[0].getAttribute('fill'),polygons[1].getAttribute('fill'));
  marks(host)[0].click(); assert.ok(find(host,'.pv-inspector').textContent.includes(hostile));
  assert.equal(host.querySelectorAll('img').length,0);
  const search=find(host,'input'); search.value='Pack'; search.dispatch('input'); assert.equal(marks(host).length,2);
  const output=viewer.exportSVG(); assert.match(output,/&lt;\/script&gt;/); assert.match(output,/"lane_ids"|&quot;lane_ids&quot;/);
});

test('chevrons refuse missing lane identities and expose limits without partial success', async () => {
  const broken=chevron(); broken.events[0].lane_ids=['missing'];
  const view=UI.mount(container(),documentFor(broken)); await assert.rejects(view.ready,/existing lanes/);
  const host=container(), limited=UI.mount(host,documentFor(chevron()),{limits:{chevronAppearances:2}}); await limited.ready;
  assert.equal(limited.exportSVG(),null); assert.match(host.textContent,/display limit/);
});

test('hostile labels remain text through panel, inspector and exported SVG', async () => {
  const label = '<script>alert("bad")</script><img onerror="oops">', host = container();
  const viewer = UI.mount(host, documentFor(graph({nodes: [node(label)], edges: []}))); await viewer.ready;
  assert.equal(host.querySelectorAll('script').length, 0); assert.equal(host.querySelectorAll('img').length, 0);
  marks(host)[0].click(); assert.ok(find(host, '.pv-inspector').textContent.includes(label));
  const output = viewer.exportSVG(); assert.ok(output.includes('&lt;script&gt;')); assert.doesNotMatch(output, /<script>|<img\s/);
});

test('search highlights matching facts without hiding or recalculating graph elements', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(graph())); await viewer.ready;
  const input = find(host, 'input'); input.value = 'A-B'; input.dispatch('input');
  assert.equal(marks(host).length, 3); assert.equal(host.querySelectorAll('.is-match').length, 1); assert.match(find(host, '.pv-search-status').textContent, /1 matches/);
  input.value = ''; input.dispatch('input'); assert.equal(host.querySelectorAll('.is-match').length, 0);
});

test('graph keyboard selection, pan, zoom, fit and pointer clicks remain usable', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(graph())); await viewer.ready;
  const svg = find(host, 'svg'), initial = svg.getAttribute('viewBox');
  svg.dispatch('keydown', {key: '+'}); assert.notEqual(svg.getAttribute('viewBox'), initial);
  svg.dispatch('keydown', {key: '0'}); assert.equal(svg.getAttribute('viewBox'), initial);
  svg.dispatch('keydown', {key: 'ArrowRight'}); assert.notEqual(svg.getAttribute('viewBox'), initial); viewer.fit();
  svg.dispatch('pointerdown', {button: 0, pointerId: 1, clientX: 5, clientY: 5}); assert.equal(svg.capturedPointer, undefined, 'Do not steal a mark click with pointer capture');
  svg.dispatch('pointerup', {}); marks(host)[0].dispatch('keydown', {key: 'Enter'}); assert.match(find(host, '.pv-inspector').textContent, /SELECTED ITEM/);
});

test('custom layout preserves identity and errors are visible instead of substituted', async () => {
  const host = container();
  const viewer = UI.mount(host, documentFor(graph()), {layout: () => ({width: 200, height: 200, nodes: [{id: 'wrong', x: 0, y: 0, width: 20, height: 20}], edges: []})});
  await assert.rejects(viewer.ready, /identities/); assert.match(find(host, '.pv-error').textContent, /Unable to display/); assert.equal(viewer.exportSVG(), null);
});

test('late asynchronous graph layout cannot overwrite a newer panel', async () => {
  const host = container(); let resolve;
  const first = graph(), second = {kind: 'table', id: 'table', title: 'Facts', description: '', columns: ['Value'], rows: [[42]]};
  const viewer = UI.mount(host, documentFor(first, second), {layout: () => new Promise(done => { resolve = done; })});
  const pending = viewer.ready; await viewer.selectPanel('table'); resolve(global.PIXNativeGeometry.layout(first)); await pending;
  assert.equal(host.querySelectorAll('svg').length, 0); assert.match(find(host, '.pv-table').textContent, /42/);
});

test('all semantic node shapes are supported and ordinary states are not falsely final', async () => {
  const kinds = ['place', 'silent', 'activity', 'gateway', 'operator', 'object', 'event', 'resource', 'state', 'rule', 'binding'];
  const host = container(), viewer = UI.mount(host, documentFor(graph({nodes: kinds.map(kind => node(kind, kind)), edges: []}))); await viewer.ready;
  assert.equal(marks(host).length, kinds.length); const state = marks(host).find(item => item.getAttribute('aria-label').startsWith('state.'));
  assert.equal(state.querySelectorAll('ellipse').length, 1); finiteSVG(host);
});

test('matrix distinguishes absent, null, zero, signed values and preserves supplied legend', async () => {
  const panel = {kind: 'matrix', id: 'matrix', title: 'Relations', description: '', rows: ['A', 'B'], columns: ['A', 'B'], unit: 'cases', legend: [{name: '→', value: 'Observed direction'}], cells: [{row: 'A', column: 'A', value: 0, kind: 'count', details: []}, {row: 'A', column: 'B', value: null, kind: 'count', details: []}, {row: 'B', column: 'A', value: -2, kind: 'count', details: []}]};
  const host = container(), viewer = UI.mount(host, documentFor(panel)); await viewer.ready;
  assert.equal(marks(host).length, 4); assert.match(find(host, '.pv-legend').textContent, /Observed direction/);
  marks(host)[1].click(); assert.match(find(host, '.pv-inspector').textContent, /Unknown cases/);
  marks(host)[3].click(); assert.match(find(host, '.pv-inspector').textContent, /Not supplied/);
  marks(host)[0].click(); assert.match(find(host, '.pv-inspector').textContent, /0 cases/); finiteSVG(host);
});

test('unknown chart values retain X, series and evidence on a separate nonnumeric rail', async () => {
  const panel = chart({series: [{name: 'Alpha', group: null, points: [{x: 0, y: 2, details: []}, {x: 1, y: null, details: [{name: 'Reason', value: 'Missing sensor'}]}, {x: 2, y: -3, details: []}]}]});
  const host = container(), viewer = UI.mount(host, documentFor(panel)); await viewer.ready;
  assert.equal(marks(host).length, 3); assert.equal(host.querySelectorAll('polyline').length, 0, 'No line crosses the unknown observation');
  marks(host)[1].click(); assert.match(find(host, '.pv-inspector').textContent, /Missing sensor/); assert.match(find(host, '.pv-inspector').textContent, /Unknown seconds/);
  assert.match(find(host, '.pv-legend').textContent, /Unknown Y, no numeric vertical position/); finiteSVG(host);
});

for (const chartType of ['bar', 'line', 'scatter']) test(`${chartType} handles negative, zero and categorical observations`, async () => {
  const panel = chart({chart_type: chartType, x_type: 'category', series: [{name: 'Alpha', group: null, points: [{x: 'A', y: -3, details: []}, {x: 'B', y: 0, details: []}, {x: 'C', y: 4, details: []}]}]});
  const host = container(), viewer = UI.mount(host, documentFor(panel)); await viewer.ready; assert.equal(marks(host).length, 3); finiteSVG(host);
});

test('time chart uses an explicit UTC axis and retains supplied timestamp strings', async () => {
  const x = '2026-09-15T13:00:00+09:00', panel = chart({x_type: 'time', series: [{name: 'Work', group: null, points: [{x, y: 2, details: []}]}]});
  const host = container(), viewer = UI.mount(host, documentFor(panel)); await viewer.ready;
  assert.match(find(host, '.pv-status').textContent, /UTC/); marks(host)[0].click(); assert.ok(find(host, '.pv-inspector').textContent.includes(x)); finiteSVG(host);
});

test('instant, closed interval and unknown-end interval have distinct timeline semantics', async () => {
  const panel = timeline({items: [{id: 'instant', lane: 'one', start: 2, end: 2, label: 'Observed', group: null, status: null, details: []}, {id: 'closed', lane: 'one', start: 3, end: 5, label: 'Completed', group: null, status: null, details: []}, {id: 'open', lane: 'one', start: 6, end: null, label: 'Running', group: null, status: null, details: []}]});
  const host = container(), viewer = UI.mount(host, documentFor(panel)); await viewer.ready;
  assert.equal(marks(host).length, 3); assert.equal(marks(host)[0].querySelectorAll('polygon').length, 1); assert.equal(marks(host)[0].querySelectorAll('rect').length, 0);
  assert.match(find(host, '.pv-status').textContent, /1 open ends/); marks(host)[2].click(); assert.match(find(host, '.pv-inspector').textContent, /Unknown seconds/); finiteSVG(host);
});

test('table pagination, view search and keyboard inspection preserve row semantics', async () => {
  const host = container(), viewer = UI.mount(host, documentFor({kind: 'table', id: 'table', title: 'Facts', description: '', columns: ['Object', 'Value'], rows: [['a', 1], ['b', null], ['c', false], ['d', 0]]}), {limits: {tablePageSize: 2}}); await viewer.ready;
  assert.equal(marks(host).length, 2); assert.equal(marks(host)[0].getAttribute('role'), null); assert.equal(viewer.exportSVG(), null);
  clickNamed(host, 'Next'); assert.match(find(host, '.pv-table').textContent, /False/);
  const input = find(host, 'input'); input.value = 'b'; input.dispatch('input'); assert.equal(marks(host).length, 1); assert.match(find(host, '.pv-status').textContent, /4 source rows/);
  marks(host)[0].dispatch('keydown', {key: 'Enter'}); assert.match(find(host, '.pv-inspector').textContent, /Unknown/);
});

test('display limits refuse incomplete drawings and preserve input', async () => {
  const host = container(), source = documentFor(graph()), before = structuredClone(source), viewer = UI.mount(host, source, {limits: {graphNodes: 1}}); await viewer.ready;
  assert.equal(host.querySelectorAll('svg').length, 0); assert.match(find(host, '.pv-status').textContent, /complete supplied document is unchanged/); assert.deepEqual(source, before);
});

test('unsupported unsafe integers and nonfinite numbers cause explicit direct-mount refusal', () => {
  for (const value of [9007199254740992, Infinity, NaN, 1n]) {
    const host = container(); assert.throws(() => UI.mount(host, documentFor({kind: 'table', id: 'table', title: 'Exact', description: '', columns: ['Count'], rows: [[value]]})), /numeric range/); assert.match(find(host, '.pv-error').textContent, /original PIX result/);
  }
});

test('SVG export includes legends, partial status, issues and provenance metadata', async () => {
  const source = documentFor(chart()); source.status = 'partial'; source.issues = ['Budget exhausted < 100']; source.provenance = [{operator_id: 'pix.test', source_digest: 'abc', calculation_id: 'proof', model_digest: null, status: 'partial', details: []}];
  const host = container(), viewer = UI.mount(host, source); await viewer.ready;
  const output = viewer.exportSVG(); assert.match(output, /<metadata>/); assert.match(output, /Analysis status: partial/); assert.match(output, /Series A/); assert.match(output, /Budget exhausted &lt; 100/); assert.match(output, /pix.test/); assert.match(output, /proof/);
});

test('control characters and literal escape sequences remain distinguishable in details', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(graph({nodes: [node('a\u0001'), node('a\\u0001'), node('a\ufffd')], edges: []}))); await viewer.ready;
  const outputs = marks(host).map(mark => { mark.click(); return find(host, '.pv-inspector').textContent; }); assert.equal(new Set(outputs).size, 3);
  assert.doesNotMatch(viewer.exportSVG(), /[\u0000-\u0008]/);
});

test('empty document and empty graph are explicit, and disposal removes the UI', async () => {
  const first = container(), empty = UI.mount(first, documentFor()); await empty.ready; assert.match(find(first, '.pv-status').textContent, /No panels supplied/);
  const host = container(), viewer = UI.mount(host, documentFor(graph({nodes: [], edges: []}))); await viewer.ready; assert.match(host.textContent, /No nodes supplied/); viewer.dispose(); assert.equal(host.children.length, 0); await assert.rejects(viewer.selectPanel('graph'), /disposed/);
});

test('invalid schema, duplicate panels and invalid display limits are rejected', () => {
  assert.throws(() => UI.mount(container(), {}), /pix.visualization.v1/);
  assert.throws(() => UI.mount(container(), documentFor(graph(), graph())), /unique/);
  assert.throws(() => UI.mount(container(), documentFor(graph()), {limits: {graphNodes: -1}}), /positive integer/);
});

test('readable mode provides one SVG unit per CSS pixel and fit restores the overview', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(graph())); await viewer.ready;
  const svg = find(host, 'svg'), initial = svg.getAttribute('viewBox'); clickNamed(host, 'Readable');
  assert.deepEqual(svg.getAttribute('viewBox').split(' ').map(Number).slice(2), [1000, 600]);
  viewer.fit(); assert.equal(svg.getAttribute('viewBox'), initial);
});

test('microsecond-separated RFC3339 observations retain separate representable coordinates', async () => {
  const first = '2026-09-15T12:00:00.000001Z', second = '2026-09-15T12:00:00.000002Z';
  const host = container(), viewer = UI.mount(host, documentFor(chart({x_type: 'time', series: [{name: 'Microseconds', group: null, points: [{x: first, y: 1, details: []}, {x: second, y: 2, details: []}]}]}))); await viewer.ready;
  const positions = marks(host).map(mark => Number(find(mark, 'circle').getAttribute('cx'))); assert.ok(positions[1] > positions[0]);
  marks(host)[0].click(); assert.ok(find(host, '.pv-inspector').textContent.includes(first)); finiteSVG(host);
  const ticks = host.querySelectorAll('.pv-tick').map(item => item.textContent); assert.ok(ticks.includes('12:00:00.000001')); assert.ok(ticks.includes('12:00:00.000002'));
});

test('singleton timestamp chart uses a local seconds window rather than years', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(chart({x_type: 'time', series: [{name: 'Instant', group: null, points: [{x: '2026-09-15T12:00:00Z', y: 2, details: []}]}]}))); await viewer.ready;
  const ticks = host.querySelectorAll('.pv-tick').map(item => item.textContent);
  assert.ok(ticks.some(value => value.startsWith('11:59:59'))); assert.ok(ticks.some(value => value.startsWith('12:00:01')));
  assert.ok(!ticks.some(value => /^202[0-9]-/.test(value)));
});

test('overlapping and coincident timeline observations remain visible on separate tracks', async () => {
  const host = container(), viewer = UI.mount(host, documentFor(timeline({items: ['a', 'b', 'c'].map(id => ({id, lane: 'one', start: 2, end: 5, label: id, group: null, status: null, details: []}))}))); await viewer.ready;
  const positions = marks(host).map(mark => find(mark, 'rect').getAttribute('y')); assert.equal(new Set(positions).size, 3);
  assert.match(find(host, '.pv-status').textContent, /separate tracks/); finiteSVG(host);
});

test('multi-series SVG footer preserves the color-to-series legend association', async () => {
  const series = ['Alpha', 'Beta'].map((name, index) => ({name, group: null, points: [{x: 0, y: index + 1, details: []}, {x: 1, y: index + 2, details: []}]}));
  const host = container(), viewer = UI.mount(host, documentFor(chart({series}))); await viewer.ready;
  const output = viewer.exportSVG(), swatches = [...output.matchAll(/<rect[^>]+fill="([^"]+)"[^>]+class="pv-export-swatch"/g)].map(match => match[1]);
  assert.equal(swatches.length, 2); assert.equal(new Set(swatches).size, 2); assert.match(output, /Alpha/); assert.match(output, /Beta/);
});

test('Petri initial/final markings and variable arcs use only supplied explicit evidence', async () => {
  const nodes = [{...node('p', 'place'), details: [{name: 'initial_count', value: 2}, {name: 'final_count', value: 1}]}, node('t', 'silent')];
  const arcs = [{...edge('arc', 'p', 't'), kind: 'arc', details: [{name: 'variable', value: true}]}];
  const host = container(), viewer = UI.mount(host, documentFor(graph({nodes, edges: arcs}))); await viewer.ready;
  assert.match(find(host, '.pv-legend').textContent, /Supplied initial tokens/); assert.match(find(host, '.pv-legend').textContent, /Variable object cardinality/);
  const place = marks(host).find(mark => mark.getAttribute('aria-label').startsWith('p.')); assert.equal(place.querySelectorAll('ellipse').length, 2); assert.match(place.textContent, /● 2/);
  assert.equal(find(host, '.pv-edge-line').getAttribute('stroke-dasharray'), '6 4');
});

test('object-typed edges keep distinct consistent colors and a visible object-type legend', async () => {
  const edges = ['Order', 'Parcel'].map(type => ({...edge(type, 'A', 'B'), details: [{name: 'object_type', value: type}]}));
  const host = container(), viewer = UI.mount(host, documentFor(graph({edges}))); await viewer.ready;
  const colors = marks(host).slice(0, 2).map(mark => mark.getAttribute('style')); assert.equal(new Set(colors).size, 2);
  assert.match(find(host, '.pv-legend').textContent, /Order/); assert.match(find(host, '.pv-legend').textContent, /Parcel/);
});

test('short node metric values are complete while their units remain visible in the legend', async () => {
  const metrics = [{name: 'events', value: 4, unit: 'events'}, {name: 'starts', value: 4, unit: 'cases'}];
  const host = container(), viewer = UI.mount(host, documentFor(graph({nodes: [{...node('Receive'), metrics}], edges: []}))); await viewer.ready;
  const labels = host.querySelectorAll('.pv-node-metric').map(item => item.textContent); assert.deepEqual(labels, ['events: 4', 'starts: 4']);
  assert.match(find(host, '.pv-legend').textContent, /events unit: events/); assert.match(find(host, '.pv-legend').textContent, /starts unit: cases/);
});

test('active panel shows only its scoped provenance plus document-wide provenance', async () => {
  const first = graph({id: 'input-0/graph'}), second = chart({id: 'input-1/chart'}), source = documentFor(first, second);
  const provenance = (operator, panelIds, inputPath) => ({operator_id: operator, source_digest: null, calculation_id: null, model_digest: null, status: 'computed', details: [], panel_ids: panelIds, input_path: inputPath});
  source.provenance = [provenance('pix.global', [], []), provenance('pix.first', [first.id], [0]), provenance('pix.second', [second.id], [1, 0]), provenance('pix.shared', [first.id, second.id], [2])];
  const host = container(), viewer = UI.mount(host, source); await viewer.ready;
  let inspector = find(host, '.pv-inspector'); assert.match(inspector.textContent, /pix.global/); assert.match(inspector.textContent, /pix.first/); assert.match(inspector.textContent, /pix.shared/); assert.doesNotMatch(inspector.textContent, /pix.second/);
  assert.match(inspector.textContent, /Associated panel IDsAll panels/); assert.match(inspector.textContent, /Input path\[0\]/); assert.match(inspector.textContent, /input-0\/graph/);
  await viewer.selectPanel(second.id); inspector = find(host, '.pv-inspector'); assert.match(inspector.textContent, /pix.global/); assert.match(inspector.textContent, /pix.second/); assert.match(inspector.textContent, /pix.shared/); assert.doesNotMatch(inspector.textContent, /pix.first/); assert.match(inspector.textContent, /Input path\[1,0\]/);
  marks(host)[0].click(); clickNamed(host, 'Clear selection'); assert.doesNotMatch(find(host, '.pv-inspector').textContent, /pix.first/);
});

test('SVG metadata retains exact panel associations and nested input paths', async () => {
  const source = documentFor(graph()); source.provenance = [{operator_id: 'pix.nested', source_digest: 'source', calculation_id: 'proof', model_digest: null, status: 'computed', details: [], panel_ids: ['graph'], input_path: [3, 0, 2]}];
  const host = container(), viewer = UI.mount(host, source); await viewer.ready;
  const metadata = viewer.exportSVG().match(/<metadata>([\s\S]*?)<\/metadata>/)[1].replaceAll('&quot;', '"').replaceAll('&lt;', '<').replaceAll('&gt;', '>').replaceAll('&amp;', '&');
  const decoded = JSON.parse(metadata); assert.deepEqual(decoded.provenance, source.provenance); assert.deepEqual(decoded.provenance[0].panel_ids, ['graph']); assert.deepEqual(decoded.provenance[0].input_path, [3, 0, 2]);
});

test('failed input without associated panels is not global or leaked into another input panel', async () => {
  const source = documentFor(graph(), chart());
  const failure = {operator_id: 'pix.failed_input', source_digest: 'failed-source', calculation_id: 'failed-proof', model_digest: null, status: 'error', details: [], panel_ids: [], input_path: [1, 0]};
  source.provenance = [{...failure, operator_id: 'pix.document', source_digest: 'global-source', calculation_id: 'global-proof', status: 'computed', input_path: []}, failure];
  const host = container(), viewer = UI.mount(host, source); await viewer.ready;
  assert.match(find(host, '.pv-inspector').textContent, /pix.document/); assert.doesNotMatch(find(host, '.pv-inspector').textContent, /pix.failed_input|failed-source|failed-proof/);
  await viewer.selectPanel('chart'); assert.doesNotMatch(find(host, '.pv-inspector').textContent, /pix.failed_input|failed-source|failed-proof/);
  const output = viewer.exportSVG(); assert.match(output, /pix.failed_input/); assert.match(output, /failed-proof/);
  const empty = container(), emptySource = documentFor(); emptySource.provenance = [failure]; const emptyViewer = UI.mount(empty, emptySource); await emptyViewer.ready;
  assert.match(find(empty, '.pv-inspector').textContent, /pix.failed_input/); assert.match(find(empty, '.pv-inspector').textContent, /Associated panel IDsNo associated panels/); assert.doesNotMatch(find(empty, '.pv-inspector').textContent, /All panels/);
});
