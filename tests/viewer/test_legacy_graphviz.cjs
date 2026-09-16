'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const L = require('../../src/pix/viewer/assets/layout.js');
const G = require('../../src/pix/viewer/assets/legacy_graphviz.js');
const Graphviz = require('../../src/pix/viewer/assets/graphviz_geometry.js');

function graph() {
  return {kind: 'ocdfg', title: 'Evidence', object_types: ['Order', 'Item'], notes: [], source_digest: 'source', computation_id: 'calculation',
    nodes: ['A', 'B', 'C'].map(id => ({id, label: `Activity ${id}`, event_count: 3, object_count: 4})),
    edges: [['e1', 'A', 'B', 'Order'], ['e2', 'A', 'B', 'Item'], ['e3', 'B', 'B', 'Order'], ['e4', 'B', 'A', 'Order']]
      .map(([id, source, target, object_type]) => ({id, source, target, object_type, counts: {event_pairs: 2, unique_objects: 3, occurrences: 7}, evidence: [{object_id: 'o1'}]}))};
}

function model(kind = 'petri_net') {
  const object_type = kind === 'ocpn' ? 'Order' : null;
  return {...graph(), kind, object_types: object_type ? [object_type] : [], origin: 'user', model_digest: 'model', objects: [],
    nodes: [['p0', 'Available', 'place', 2, 0], ['t1', 'Approve', 'transition', 0, 0], ['tau', '', 'silent', 0, 0], ['p2', 'Done', 'place', 0, 1]]
      .map(([id, label, nodeKind, initial_count, final_count]) => ({id, label, kind: nodeKind, object_type: nodeKind === 'place' ? object_type : null, initial_count, final_count})),
    edges: [['a1', 'p0', 't1'], ['a2', 't1', 'tau'], ['a3', 'tau', 'p2']]
      .map(([id, source, target]) => ({id, source, target, object_type, weight: kind === 'ocpn' ? 1 : 2,
        variable: kind === 'ocpn', min_objects: kind === 'ocpn' ? 0 : 1, max_objects: kind === 'ocpn' ? null : 1}))};
}

function fakeEngine(mutate = () => {}) {
  return {async layout(input, options) {
    const nodes = input.nodes.map((node, i) => ({id: node.id, x: 40 + i * 330, y: 90, ...options.nodeSizes.get(node.id)}));
    const byId = new Map(nodes.map(node => [node.id, node]));
    const edges = input.edges.map((edge, i) => {
      const a = byId.get(edge.source), b = byId.get(edge.target), start = {x: a.x + a.width, y: a.y + a.height / 2};
      const tip = {x: b.x, y: b.y + b.height / 2}, end = {x: tip.x - 10, y: tip.y};
      return {id: edge.id, splines: [{points: [start, {x: start.x + 25, y: start.y + i * 20}, {x: end.x - 25, y: end.y + i * 20}, end]}],
        labelPosition: edge.label ? {x: 200 + i * 35, y: 40} : null,
        arrowhead: [{x: end.x, y: end.y - 4}, tip, {x: end.x, y: end.y + 4}], arrowtail: []};
    });
    const result = {engine: 'graphviz', engineVersion: 'test', width: 1600, height: 500, nodes, edges};
    mutate(result, input, options); return result;
  }};
}

test('legacy Graphviz adapter preserves all IDs, count units, witnesses and immutable source', async () => {
  const source = graph(), before = structuredClone(source), prepared = L.toElkGraph(source);
  let request;
  const result = await G.createGraphvizLayout(fakeEngine((_, input, options) => {request = {input, options};}))(source);
  assert.deepEqual(source, before);
  assert.deepEqual(result.children.map(node => node.id), prepared.children.map(node => node.id));
  assert.deepEqual(result.edges.map(edge => edge.id), prepared.edges.map(edge => edge.id));
  assert.equal(result.layoutEngine, 'graphviz'); assert.equal(result.layoutEngineVersion, 'test');
  for (const edge of result.edges) {
    assert.deepEqual(edge.data, before.edges.find(item => item.id === edge.id));
    assert.match(L.sectionPath(edge), /^M.* C/); assert.equal(edge.arrowhead.length, 3);
    assert.deepEqual(edge.labelLines, prepared.edges.find(item => item.id === edge.id).labelLines);
    const asked = request.input.edges.find(item => item.id === edge.id);
    assert.ok(asked.label.includes('7 unique objects'));
    assert.deepEqual(asked.labelSize, {width: edge.labels[0].width, height: edge.labels[0].height});
  }
  assert.equal(request.options.direction, 'LR');
});

test('parallel edges and loops retain separate cubic routes and label locations', async () => {
  const result = await G.createGraphvizLayout(fakeEngine())(graph());
  assert.equal(new Set(result.edges.map(edge => L.sectionPath(edge))).size, 4);
  assert.equal(new Set(result.edges.map(edge => edge.labels[0].x)).size, 4);
});

for (const kind of ['petri_net', 'ocpn']) test(`${kind} model shapes, markings and cardinalities survive Graphviz placement`, async () => {
  const source = model(kind), prepared = L.toElkGraph(source), result = await G.createGraphvizLayout(fakeEngine())(source);
  for (const node of result.children) {
    const original = prepared.children.find(item => item.id === node.id);
    for (const key of ['shape', 'labelLines', 'labelY', 'typeLabelLines', 'typeLabelY', 'markingY', 'data']) assert.deepEqual(node[key], original[key]);
  }
  for (const edge of result.edges) {
    const expected = prepared.edges.find(item => item.id === edge.id);
    assert.equal(edge.semanticLabel, expected.semanticLabel); assert.deepEqual(edge.labelLines, expected.labelLines);
    const node = result.children.find(item => item.id === edge.data.target), shape = node.shape;
    const tip = edge.arrowhead[1], dx = tip.x - node.x - shape.cx, dy = tip.y - node.y - shape.cy;
    if (shape.kind === 'place') assert.ok(Math.abs(Math.hypot(dx, dy) - shape.radius) < 1e-8);
    else assert.ok(Math.abs(Math.max(Math.abs(dx) / (shape.width / 2), Math.abs(dy) / (shape.height / 2)) - 1) < 1e-8);
    const base = edge.sections.at(-1).endPoint;
    assert.ok(Math.abs(Math.hypot(tip.x - base.x, tip.y - base.y) - 10) < 1e-8, 'Graphviz arrow length survives attachment');
  }
});

test('empty graph remains visible without initializing Graphviz', async () => {
  const result = await G.createGraphvizLayout({layout() {throw new Error('must not run');}})({...graph(), nodes: [], edges: []});
  assert.equal(result.width, 320); assert.equal(result.height, 180);
});

test('invalid Graphviz engine rejects explicitly', () => {
  for (const engine of [null, {}, {layout: 2}]) assert.throws(() => G.createGraphvizLayout(engine), /Graphviz geometry engine/);
});

const corruptions = [
  ['missing node', r => r.nodes.pop()], ['duplicate node', r => {r.nodes[1] = r.nodes[0];}],
  ['unknown edge', r => {r.edges[0].id = 'unknown';}], ['missing edge', r => r.edges.pop()],
  ['changed dimensions', r => {r.nodes[0].width += 2;}], ['invalid node', r => {r.nodes[0].x = NaN;}],
  ['invalid bounds', r => {r.width = Infinity;}], ['missing spline', r => {r.edges[0].splines = [];}],
  ['invalid spline count', r => r.edges[0].splines[0].points.pop()], ['invalid control', r => {r.edges[0].splines[0].points[1].x = NaN;}],
  ['missing label location', r => {r.edges[0].labelPosition = null;}], ['invalid arrow', r => {r.edges[0].arrowhead[0].x = Infinity;}],
];
for (const [name, mutate] of corruptions) test(`rejects ${name} instead of silently dropping source facts`, async () => {
  await assert.rejects(G.createGraphvizLayout(fakeEngine(mutate))(graph()), TypeError);
});

test('cubic path validation requires finite controls, unambiguous curves and matching final endpoint', () => {
  const section = {startPoint: {x: 1, y: 2}, endPoint: {x: 7, y: 8},
    cubicBezier: [{controlPoint1: {x: 3, y: 4}, controlPoint2: {x: 5, y: 6}, endPoint: {x: 7, y: 8}}]};
  assert.equal(L.sectionPath({sections: [section]}), 'M1,2 C3,4 5,6 7,8');
  for (const change of [{cubicBezier: []}, {bendPoints: []}, {endPoint: {x: 8, y: 8}},
    {cubicBezier: [{...section.cubicBezier[0], controlPoint1: {x: Infinity, y: 0}}]}, {cubicBezier: [null]}]) {
    assert.throws(() => L.sectionPath({sections: [{...section, ...change}]}), TypeError);
  }
});

class Element {
  constructor(tag) {this.tag = tag; this.attrs = new Map(); this.children = []; this.events = new Map(); this._text = ''; this.style = {};
    this.classList = {add: name => {this.attrs.set('class', `${this.attrs.get('class') || ''} ${name}`);}, remove() {}, toggle() {}};}
  setAttribute(name, value) {this.attrs.set(name, String(value));}
  getAttribute(name) {return this.attrs.get(name);}
  toggleAttribute(name, force) {force ? this.attrs.set(name, '') : this.attrs.delete(name);}
  set textContent(value) {this._text = String(value); this.children = [];}
  get textContent() {return this._text + this.children.map(item => item.textContent).join('');}
  append(...children) {this.children.push(...children);}
  replaceChildren(...children) {this.children = children; this._text = '';}
  addEventListener(name, handler) {this.events.set(name, handler);}
  getBoundingClientRect() {return {width: 1000, height: 600};}
}
function viewerContext(values = {}) {
  const context = vm.createContext({structuredClone, Set, Map, PIXLayout: L, PIXLegacyGraphviz: G, PIXGraphvizGeometry: fakeEngine(),
    document: {createElement: tag => new Element(tag), createElementNS: (_, tag) => new Element(tag), getElementById: () => null},
    ResizeObserver: class {observe() {} disconnect() {}}, ...values});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../../src/pix/viewer/assets/viewer.js'), 'utf8'), context);
  return context;
}
function allElements(root) {return [root, ...root.children.flatMap(allElements)];}

test('legacy viewer uses Graphviz by default and preserves count selector, type filter and arrow polygons', async () => {
  const context = viewerContext(), host = new Element('main'), source = graph();
  const viewer = await context.PIXViewer.mount(host, source);
  const elements = allElements(host);
  const paths = elements.filter(item => item.attrs.get('class') === 'pix-edge-line');
  assert.equal(paths.length, 4); assert.ok(paths.every(item => !item.attrs.has('marker-end')));
  assert.equal(elements.filter(item => item.attrs.get('class') === 'pix-edge-arrow').length, 4);
  const select = elements.find(item => item.tag === 'select'); select.value = 'occurrences'; select.events.get('change')();
  assert.equal(viewer.getViewState().unit, 'occurrences');
  const type = elements.find(item => item.attrs.get('aria-label') === 'Show object type Order'); type.checked = false; type.events.get('change')();
  assert.deepEqual([...viewer.getViewState().hiddenObjectTypes], ['Order']);
  assert.deepEqual(viewer.getGraph(), source); viewer.destroy();
});

test('legacy viewer missing Graphviz fails without falling back to ELK', async () => {
  let elk = false;
  const context = viewerContext({PIXGraphvizGeometry: null, ELK: function () {elk = true;}});
  await assert.rejects(context.PIXViewer.mount(new Element('main'), graph()), /Graphviz layout engine is not available/);
  assert.equal(elk, false);
});

test('explicit custom layout still takes precedence over defaults and unknown engines reject', async () => {
  const context = viewerContext({PIXGraphvizGeometry: null}); let called = false;
  await context.PIXViewer.mount(new Element('main'), {...graph(), nodes: [], edges: []}, {layout: async () => {called = true; return {width: 50, height: 50, children: [], edges: []};}});
  assert.equal(called, true);
  await assert.rejects(context.PIXViewer.mount(new Element('main'), graph(), {layoutEngine: 'unknown'}), /Unknown layout engine/);
});

test('explicit ELK remains available', async () => {
  let called = false;
  const context = viewerContext({PIXViewerLayoutEngine: 'elk', ELK: function () {called = true; return {layout() {throw new Error('empty graph avoids engine');}};}});
  await context.PIXViewer.mount(new Element('main'), {...graph(), nodes: [], edges: []});
  assert.equal(called, true);
});

for (const kind of ['ocdfg', 'petri_net', 'ocpn']) test(`real Graphviz WASM renders the legacy ${kind} document`, async () => {
  const source = kind === 'ocdfg' ? graph() : model(kind), before = structuredClone(source);
  const result = await G.createGraphvizLayout(Graphviz)(source);
  assert.equal(result.layoutEngineVersion, '16.0.0');
  assert.deepEqual(source, before);
  assert.equal(result.children.length, source.nodes.length); assert.equal(result.edges.length, source.edges.length);
  assert.ok(result.width > 0 && result.height > 0);
  for (const edge of result.edges) {
    assert.match(L.sectionPath(edge), /^M.* C/); assert.doesNotMatch(L.sectionPath(edge), /NaN|Infinity/);
    assert.equal(edge.arrowhead.length, 3); assert.ok(edge.labels[0]);
    assert.deepEqual(edge.data, source.edges.find(item => item.id === edge.id));
  }
  assert.deepEqual(result, await G.createGraphvizLayout(Graphviz)({...source, nodes: [...source.nodes].reverse(), edges: [...source.edges].reverse()}));
});

test('real Graphviz legacy viewer renders hostile labels as text and retains separate routes', async () => {
  const source = graph(); source.nodes[0].label = '</script><img src=x onerror=alert(1)> 한글 😀';
  const context = viewerContext({PIXGraphvizGeometry: Graphviz}), host = new Element('main');
  await context.PIXViewer.mount(host, source);
  const elements = allElements(host);
  assert.equal(elements.filter(item => item.tag === 'script' || item.tag === 'img').length, 0);
  const paths = elements.filter(item => item.attrs.get('class') === 'pix-edge-line').map(item => item.attrs.get('d'));
  assert.equal(paths.length, source.edges.length); assert.equal(new Set(paths).size, source.edges.length);
  assert.ok(host.textContent.includes('</script>'));
});
