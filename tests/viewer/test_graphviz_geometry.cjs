"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const crypto = require("node:crypto");
const geometry = require("../../src/pix/viewer/assets/graphviz_geometry.js");
const Viz = require("../../src/pix/viewer/assets/vendor/viz-global.js");
const assets = path.resolve(__dirname, "../../src/pix/viewer/assets");
const node = (id, label = id, kind = "activity") => ({id, label, kind});
const edge = (id, source, target, label = "") => ({id, source, target, label, directed: true});
const fixture = () => ({nodes: [node("a"), node("b"), node("c"), node("alone")], edges: [
  edge("ab1", "a", "b", "order: 12"), edge("ab2", "a", "b", "item: 27"),
  edge("ba", "b", "a", "return: 1"), edge("aa", "a", "a", "retry: 2"), edge("bc", "b", "c", "ship: 8")
]});

function finite(result, graph) {
  assert.equal(result.engine, "graphviz"); assert.equal(result.layout, "dot"); assert.equal(result.engineVersion, "16.0.0");
  assert.deepEqual(result.nodes.map(n => n.id).sort(), graph.nodes.map(n => n.id).sort());
  assert.deepEqual(result.edges.map(e => e.id).sort(), graph.edges.map(e => e.id).sort());
  assert.ok(Number.isFinite(result.width) && result.width > 0 && Number.isFinite(result.height) && result.height > 0);
  const inside = point => {
    assert.ok(Number.isFinite(point.x) && point.x >= 0 && point.x <= result.width, JSON.stringify(point));
    assert.ok(Number.isFinite(point.y) && point.y >= 0 && point.y <= result.height, JSON.stringify(point));
  };
  for (const n of result.nodes) { inside(n); inside({x: n.x + n.width, y: n.y + n.height}); assert.ok(n.width > 0 && n.height > 0); }
  for (const e of result.edges) {
    assert.equal(e.points.length, 2); e.points.forEach(inside);
    assert.ok(e.splines.length > 0);
    for (const s of e.splines) { assert.ok(s.points.length >= 4); assert.equal((s.points.length - 1) % 3, 0); s.points.forEach(inside); }
    e.arrowhead.forEach(inside); e.arrowtail.forEach(inside);
    if (e.labelPosition) { inside(e.labelPosition); assert.ok(e.labelSize.width > 0 && e.labelSize.height > 0); }
  }
}

for (const direction of ["LR", "TB"]) {
  test(`real Graphviz ${direction}: preserves parallel arcs, cycles, self loops and isolated nodes`, async () => {
    const graph = fixture(), before = structuredClone(graph), result = await geometry.layout(graph, {direction});
    finite(result, graph); assert.deepEqual(graph, before); assert.equal(result.notes.length, 0);
    assert.equal(new Set(result.edges.map(e => JSON.stringify(e.splines))).size, graph.edges.length);
    assert.ok(result.edges.every(e => e.labelPosition && e.arrowhead.length === 3));
    assert.notDeepEqual(result.edges.find(e => e.id === "ab1").labelPosition, result.edges.find(e => e.id === "ab2").labelPosition);
  });
  test(`real Graphviz ${direction}: deterministic across input permutations`, async () => {
    const graph = fixture();
    assert.deepEqual(await geometry.layout(graph, {direction}), await geometry.layout({nodes: [...graph.nodes].reverse(), edges: [...graph.edges].reverse()}, {direction}));
  });
}

test("empty graph and isolated repeated labels have positive finite bounds", async () => {
  for (const graph of [{nodes: [], edges: []}, {nodes: [node("x", "same"), node("y", "same")], edges: []}]) finite(await geometry.layout(graph), graph);
});

test("nodeSizes Map, plain records, and node dimensions use point units", async () => {
  const graph = {nodes: [node("a"), node("b")], edges: [edge("e", "a", "b")]};
  for (const sizes of [new Map([["a", {width: 216, height: 108}]]), {a: {width: 216, height: 108}}]) {
    const result = await geometry.layout(graph, {nodeSizes: sizes}), a = result.nodes.find(n => n.id === "a");
    assert.equal(a.width, 216); assert.equal(a.height, 108);
  }
  graph.nodes[0].width = 216; graph.nodes[0].height = 108;
  const result = await geometry.layout(graph); assert.equal(result.nodes.find(n => n.id === "a").width, 216);
});

test("provided label reservations remain at least their requested dimensions", async () => {
  const graph = {nodes: [node("a"), node("b")], edges: [{...edge("e", "a", "b", "count: 100"), labelSize: {width: 240, height: 38}}]};
  const result = await geometry.layout(graph), e = result.edges[0];
  assert.ok(e.labelSize.width >= 240); assert.ok(e.labelSize.height >= 38); assert.ok(e.labelPosition);
  finite(result, graph);
});

test("fractional label boxes keep Graphviz dimensions within 0.01 point", async () => {
  const dimensions = [41.135, 96.82, 153.333, 280.715, 540.4];
  const graph = {nodes: dimensions.map((width, i) => ({...node(`n${i}`), width, height: 74.23})), edges: []};
  const result = await geometry.layout(graph);
  result.nodes.forEach((n, i) => {
    assert.ok(Math.abs(n.width - dimensions[i]) < 0.01, `${n.width} != ${dimensions[i]}`);
    assert.ok(Math.abs(n.height - 74.23) < 0.01);
  });
});

test("undirected relation has no arrow polygon and unlabeled arcs have no label reservation", async () => {
  const graph = {nodes: [node("a"), node("b")], edges: [{...edge("e", "a", "b"), directed: false}]};
  const result = await geometry.layout(graph), e = result.edges[0];
  assert.deepEqual(e.arrowhead, []); assert.deepEqual(e.arrowtail, []); assert.equal(e.labelPosition, null); assert.equal(e.labelSize, null);
});

test("metric-only edge labels get layout space even without an explicit label", async () => {
  const graph = {nodes: [node("a"), node("b")], edges: [{...edge("e", "a", "b"), metrics: [{name: "frequency", value: 123, unit: "objects"}]}]};
  const result = await geometry.layout(graph); assert.ok(result.edges[0].labelPosition); assert.ok(result.edges[0].labelSize.width > 100);
});

test("node kinds choose the same ellipse/diamond/box outlines as the PIX renderer", async () => {
  const viz = await Viz.instance(); let request;
  const injected = {graphvizVersion: viz.graphvizVersion, render(graph, options) { request = graph; return viz.render(graph, options); }};
  const kinds = ["place", "state", "operator", "gateway", "decision", "activity", "silent"];
  const graph = {nodes: kinds.map(kind => node(kind, kind, kind)), edges: []};
  finite(await geometry.layout(graph, {viz: injected}), graph);
  const expected = {place: "ellipse", state: "ellipse", operator: "ellipse", gateway: "diamond", decision: "diamond", activity: "box", silent: "box"};
  [...graph.nodes].sort((a, b) => a.id.localeCompare(b.id)).forEach((n, i) => assert.equal(request.nodes[i].attributes.shape, expected[n.kind]));
});

test("hostile text, controls, Unicode and duplicate labels never enter Graphviz syntax or identifiers", async () => {
  const bad = '<TABLE><TR><TD HREF="https://example.invalid">x</TD></TR></TABLE> " \\N \\l </script>\u0000\u0001😀한글';
  const graph = {nodes: [node(bad, bad), node("__proto__", bad)], edges: [edge(bad, bad, "__proto__", bad)]};
  const viz = await Viz.instance(); let request;
  const injected = {graphvizVersion: viz.graphvizVersion, render(g, options) { request = g; return viz.render(g, options); }};
  const result = await geometry.layout(graph, {viz: injected}); finite(result, graph);
  assert.equal(JSON.stringify(request).includes(bad), false);
  assert.ok(request.nodes.every(n => /^n\d+$/.test(n.name) && n.attributes.label === ""));
  assert.match(request.edges[0].attributes.label.html, /^<TABLE BORDER="0"/);
  assert.equal(request.edges[0].attributes.label.html.includes("HREF"), false);
  assert.equal(result.edges[0].id, bad);
});

test("Graphviz cubic control points, arrow polygons and label centers undergo translation only", async () => {
  const graph = fixture(), viz = await Viz.instance(); let output;
  const injected = {graphvizVersion: viz.graphvizVersion, render(g, options) { const r = viz.render(g, options); output = JSON.parse(r.output); return r; }};
  const result = await geometry.layout(graph, {viz: injected});
  const sourceNode = output.objects.find(n => n.name === "n0"), targetNode = result.nodes[0];
  const [cx, cy] = sourceNode.pos.split(",").map(Number), dx = targetNode.x + targetNode.width / 2 - cx, dy = targetNode.y + targetNode.height / 2 - cy;
  const close = (p, q) => { assert.ok(Math.abs(p.x - q[0] - dx) < 1e-8); assert.ok(Math.abs(p.y - q[1] - dy) < 1e-8); };
  for (const edge of output.edges) {
    const resultEdge = result.edges[Number(edge.id.slice(1))], cubics = edge._draw_.filter(op => op.op === "b" || op.op === "B");
    assert.equal(resultEdge.splines.length, cubics.length);
    cubics.forEach((c, i) => c.points.forEach((p, j) => close(resultEdge.splines[i].points[j], p)));
    close(resultEdge.labelPosition, edge.lp.split(",").map(Number));
    const arrow = edge._hdraw_.find(op => op.op === "P"); arrow.points.forEach((p, j) => close(resultEdge.arrowhead[j], p));
  }
});

test("bundle source and browser global instantiate offline with every fetch rejected", async () => {
  let networkCalls = 0;
  const context = vm.createContext({console, URL, WebAssembly, TextEncoder, TextDecoder, setTimeout, clearTimeout, crypto: crypto.webcrypto,
    document: {baseURI: "file:///offline/graph.html", currentScript: null},
    fetch() { networkCalls++; throw new Error("network forbidden"); }});
  vm.runInContext(fs.readFileSync(path.join(assets, "vendor/viz-global.js"), "utf8"), context);
  vm.runInContext(fs.readFileSync(path.join(assets, "graphviz_geometry.js"), "utf8"), context);
  const graph = fixture(), result = await context.PIXGraphvizGeometry.layout(graph);
  assert.equal(result.engineVersion, "16.0.0"); assert.equal(result.edges.length, graph.edges.length); assert.equal(networkCalls, 0);
});

test("vendor byte hashes, licenses, source links, SRI evidence and inline safety stay pinned", () => {
  const provenance = JSON.parse(fs.readFileSync(path.join(assets, "vendor/graphviz-provenance.json"), "utf8"));
  assert.equal(provenance.package.version, "3.30.0"); assert.equal(provenance.graphviz.version, "16.0.0");
  assert.ok(provenance.verification.npm_registry_signature_valid);
  for (const artifact of provenance.files) {
    const bytes = fs.readFileSync(path.join(assets, "vendor", artifact.name));
    assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), artifact.sha256);
  }
  assert.match(provenance.graphviz.source, /16\.0\.0/);
  assert.match(fs.readFileSync(path.join(assets, "vendor/GRAPHVIZ-LICENSE.txt"), "utf8"), /Eclipse Public License - v 2\.0/);
  assert.match(fs.readFileSync(path.join(assets, "vendor/EXPAT-LICENSE.txt"), "utf8"), /Expat maintainers/);
  assert.doesNotMatch(fs.readFileSync(path.join(assets, "vendor/viz-global.js"), "utf8"), /<\/script|<!--|[\u2028\u2029]/i);
});

for (const [name, transform, options, pattern] of [
  ["duplicate node", g => g.nodes.push(node("a")), {}, /unique/],
  ["duplicate edge", g => g.edges.push({...g.edges[0]}), {}, /unique/],
  ["unknown endpoint", g => g.edges[0].target = "missing", {}, /unknown node/],
  ["empty ID", g => g.nodes[0].id = "", {}, /nonempty/],
  ["unpaired high surrogate", g => g.nodes[0].label = "\ud800", {}, /surrogate/],
  ["unpaired low surrogate", g => g.edges[0].label = "\udfff", {}, /surrogate/],
  ["nonnumeric dimensions", g => g.nodes[0].width = "100", {}, /finite/],
  ["infinite dimensions", g => { g.nodes[0].width = Infinity; g.nodes[0].height = 50; }, {}, /finite/],
  ["zero label size", g => g.edges[0].labelSize = {width: 0, height: 1}, {}, /finite/],
  ["invalid direction", () => {}, {direction: "RL"}, /Direction/],
  ["invalid nodeSizes", () => {}, {nodeSizes: []}, /nodeSizes/],
  ["invalid direction flag", g => g.edges[0].directed = 1, {}, /boolean/]
]) test(`rejects ${name}`, async () => {
  const graph = fixture(); transform(graph); await assert.rejects(() => geometry.layout(graph, options), pattern);
});

test("Graphviz failures never silently switch to a different layout engine", async () => {
  await assert.rejects(() => geometry.layout(fixture(), {viz: {graphvizVersion: "test", render() { return {status: "failure", errors: [{message: "fixture failure"}]}; }}}), /Graphviz layout failed: fixture failure/);
});

test("Graphviz warnings are surfaced without changing graph data", async () => {
  const viz = await Viz.instance();
  const result = await geometry.layout(fixture(), {viz: {graphvizVersion: viz.graphvizVersion, render(g, options) { const r = viz.render(g, options); r.errors.push({level: "warning", message: "fixture warning"}); return r; }}});
  assert.deepEqual(result.notes, ["Graphviz warning: fixture warning"]);
});
