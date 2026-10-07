"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const geometry = require("../../src/pix/viewer/assets/native_geometry.js");

const node = (id, label = id, kind = "activity") => ({ id, label, kind });
const edge = (id, source, target) => ({ id, source, target });
const fixture = () => ({ nodes: [node("a"), node("b"), node("c"), node("z")], edges: [
  edge("ab1", "a", "b"), edge("ab2", "a", "b"), edge("ba", "b", "a"),
  edge("aa1", "a", "a"), edge("aa2", "a", "a"), edge("bc", "b", "c"), edge("ac", "a", "c")
] });

function boundary(point, box) {
  const eps = 1e-7;
  const between = (x, lo, hi) => x >= lo - eps && x <= hi + eps;
  return ((Math.abs(point.x - box.x) < eps || Math.abs(point.x - box.x - box.width) < eps) && between(point.y, box.y, box.y + box.height)) ||
    ((Math.abs(point.y - box.y) < eps || Math.abs(point.y - box.y - box.height) < eps) && between(point.x, box.x, box.x + box.width));
}

function assertGeometry(graph, result) {
  assert.deepEqual(result.nodes.map(n => n.id).sort(), graph.nodes.map(n => n.id).sort());
  assert.deepEqual(result.edges.map(e => e.id).sort(), graph.edges.map(e => e.id).sort());
  assert.ok(Number.isFinite(result.width) && result.width > 0);
  assert.ok(Number.isFinite(result.height) && result.height > 0);
  const byId = new Map(result.nodes.map(n => [n.id, n]));
  for (const n of result.nodes) {
    for (const v of [n.x, n.y, n.width, n.height]) assert.ok(Number.isFinite(v));
    assert.ok(n.width > 0 && n.height > 0 && n.x >= 0 && n.y >= 0);
    assert.ok(n.x + n.width <= result.width + 1e-7 && n.y + n.height <= result.height + 1e-7);
  }
  for (let a = 0; a < result.nodes.length; a++) for (let b = a + 1; b < result.nodes.length; b++) {
    const x = result.nodes[a], y = result.nodes[b];
    assert.ok(x.x + x.width <= y.x || y.x + y.width <= x.x || x.y + x.height <= y.y || y.y + y.height <= x.y,
      `Node interiors overlap: ${x.id}, ${y.id}`);
  }
  for (const e of result.edges) {
    const original = graph.edges.find(x => x.id === e.id);
    assert.ok(e.points.length >= 2);
    for (const p of e.points) {
      assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
      assert.ok(p.x >= 0 && p.y >= 0 && p.x <= result.width + 1e-7 && p.y <= result.height + 1e-7);
    }
    assert.ok(boundary(e.points[0], byId.get(original.source)), `Source boundary: ${e.id}`);
    assert.ok(boundary(e.points.at(-1), byId.get(original.target)), `Target boundary: ${e.id}`);
  }
}

for (const layout of ["layered", "tree", "force", "bipartite"]) for (const direction of ["LR", "TB"]) {
  test(`${layout}/${direction} preserves cycles, multiplicity, loops and disconnected nodes`, () => {
    const graph = fixture(), before = JSON.stringify(graph);
    const result = geometry.layout(graph, { layout, direction });
    assertGeometry(graph, result);
    assert.equal(JSON.stringify(graph), before);
    assert.equal(new Set(result.edges.map(e => JSON.stringify(e.points))).size, graph.edges.length);
  });
  test(`${layout}/${direction} is deterministic under input permutations`, () => {
    const graph = fixture(), reordered = { nodes: [...graph.nodes].reverse(), edges: [...graph.edges].reverse() };
    assert.deepEqual(geometry.layout(graph, { layout, direction }), geometry.layout(reordered, { layout, direction }));
  });
}

test("SCCs use common ranks, condensation follows directed longest paths", () => {
  const graph = fixture(), result = geometry.layout(graph), nodes = new Map(result.nodes.map(n => [n.id, n]));
  assert.equal(nodes.get("a").x, nodes.get("b").x);
  assert.ok(nodes.get("c").x > nodes.get("a").x);
  assert.equal(nodes.get("z").x, nodes.get("a").x);
});

test("tree is a directed BFS forest, force is a distinct fixed-step solution", () => {
  const graph = fixture();
  assert.notDeepEqual(geometry.layout(graph, { layout: "tree" }).nodes, geometry.layout(graph).nodes);
  assert.notDeepEqual(geometry.layout(graph, { layout: "force" }).nodes, geometry.layout(graph).nodes);
});

test("bipartite colors an undirected graph while odd cycles retain every edge", () => {
  const graph = { nodes: [node("p1", "Place", "place"), node("p2", "Place", "place"), node("t", "Transition", "transition")],
    edges: [edge("pt", "p1", "t"), edge("tp", "t", "p2")] };
  const result = geometry.layout(graph, { layout: "bipartite" }), byId = new Map(result.nodes.map(n => [n.id, n]));
  assert.equal(byId.get("p1").x, byId.get("p2").x);
  assert.ok(byId.get("t").x > byId.get("p1").x);
  assertGeometry(fixture(), geometry.layout(fixture(), { layout: "bipartite" }));
});

test("empty and isolated graphs have finite bounds", () => {
  assert.deepEqual(geometry.layout({ nodes: [], edges: [] }), { width: 80, height: 80, nodes: [], edges: [] });
  for (const layout of ["layered", "tree", "force", "bipartite"]) {
    const graph = { nodes: [node("only")], edges: [] };
    assertGeometry(graph, geometry.layout(graph, { layout }));
  }
});

test("unicode labels wrap by code point and preserve original text inputs", () => {
  const label = "납품 검토 👩🏽‍💻".repeat(50), graph = { nodes: [node("한글🚀", label)], edges: [] };
  const result = geometry.layout(graph);
  assertGeometry(graph, result);
  assert.equal(graph.nodes[0].label, label);
  const lines = geometry.wrapLabel("🚀".repeat(200), 10, 3);
  assert.equal(lines.length, 3);
  assert.ok(lines.every(line => Array.from(line).length <= 10));
  assert.ok(lines.at(-1).endsWith("…"));
  assert.ok(!lines.join("").includes("\ufffd"));
  assert.equal(geometry.typeColor("구매주문"), geometry.typeColor("구매주문"));
});

test("TB preserves measured label box dimensions instead of rotating text boxes", () => {
  const graph = { nodes: [node("long", "Long activity label")], edges: [] };
  const lr = geometry.layout(graph).nodes[0], tb = geometry.layout(graph, { direction: "TB" }).nodes[0];
  assert.equal(lr.width, tb.width); assert.equal(lr.height, tb.height);
});

test("malformed graphs and options fail explicitly", () => {
  for (const graph of [null, {}, { nodes: {}, edges: [] }, { nodes: [null], edges: [] },
    { nodes: [node("a"), node("a")], edges: [] }, { nodes: [node(1)], edges: [] },
    { nodes: [node("")], edges: [] }, { nodes: [{ id: "a", label: null }], edges: [] },
    { nodes: [node("a")], edges: [edge("e", "a", "missing")] },
    { nodes: [node("a")], edges: [edge("e", "a", "a"), edge("e", "a", "a")] }]) {
    assert.throws(() => geometry.layout(graph), TypeError);
  }
  assert.throws(() => geometry.layout(fixture(), { layout: "elk" }), RangeError);
  assert.throws(() => geometry.layout(fixture(), { direction: "RL" }), RangeError);
  assert.throws(() => geometry.layout(fixture(), null), TypeError);
  assert.throws(() => geometry.wrapLabel("a", 0), RangeError);
  assert.throws(() => geometry.typeColor(1), TypeError);
});

test("IDs are opaque strings, including delimiters and object prototype names", () => {
  const graph = { nodes: [node("__proto__"), node("a:b"), node("constructor")],
    edges: [edge("__proto__", "__proto__", "a:b"), edge("constructor", "a:b", "constructor")] };
  assertGeometry(graph, geometry.layout(graph));
});

function intersectsInterior(a, b, box) {
  const eps = 1e-7;
  if (Math.abs(a.x - b.x) < eps) return a.x > box.x + eps && a.x < box.x + box.width - eps &&
    Math.max(a.y, b.y) > box.y + eps && Math.min(a.y, b.y) < box.y + box.height - eps;
  assert.ok(Math.abs(a.y - b.y) < eps, "Column routes must be orthogonal");
  return a.y > box.y + eps && a.y < box.y + box.height - eps &&
    Math.max(a.x, b.x) > box.x + eps && Math.min(a.x, b.x) < box.x + box.width - eps;
}

test("column routing does not cut through node interiors, including long/back edges", () => {
  const graph = { nodes: Array.from({ length: 9 }, (_, i) => node(String(i), "Wide label ".repeat(i % 4 + 1))),
    edges: [edge("01", "0", "1"), edge("12", "1", "2"), edge("23", "2", "3"), edge("34", "3", "4"),
      edge("04", "0", "4"), edge("50", "5", "0"), edge("61", "6", "1"), edge("82", "8", "2"),
      edge("44", "4", "4"), edge("77", "7", "7")] };
  for (const layout of ["layered", "tree", "bipartite"]) for (const direction of ["LR", "TB"]) {
    const result = geometry.layout(graph, { layout, direction });
    assertGeometry(graph, result);
    for (const e of result.edges) for (let i = 1; i < e.points.length; i++) for (const box of result.nodes) {
      assert.ok(!intersectsInterior(e.points[i - 1], e.points[i], box), `Edge ${e.id} enters ${box.id} in ${layout}/${direction}`);
    }
  }
});

test("force rejects quadratic work beyond its explicit size budget", () => {
  const graph = { nodes: Array.from({ length: 1001 }, (_, i) => node(String(i))), edges: [] };
  assert.throws(() => geometry.layout(graph, { layout: "force" }), /at most 1000 nodes/);
});

test("force routes stay outside their endpoint interiors with asymmetric boxes", () => {
  const graph = { nodes: [node("a", "납품".repeat(100)), node("b", "b"), node("c", "c"), node("d", "d")],
    edges: [edge("ab", "a", "b"), edge("ac1", "a", "c"), edge("ac2", "a", "c"), edge("ad", "a", "d")] };
  for (const direction of ["LR", "TB"]) {
    const result = geometry.layout(graph, { layout: "force", direction });
    assertGeometry(graph, result);
    const byId = new Map(result.nodes.map(n => [n.id, n]));
    for (const route of result.edges) {
      const original = graph.edges.find(e => e.id === route.id);
      for (let i = 1; i < route.points.length; i++) for (const id of [original.source, original.target]) {
        const box = byId.get(id), a = route.points[i - 1], b = route.points[i];
        // Independent dense sampling excludes boundary endpoints and detects a
        // bend inside an endpoint rectangle; general obstacle routing is absent.
        for (let part = 1; part < 100; part++) {
          const x = a.x + (b.x - a.x) * part / 100, y = a.y + (b.y - a.y) * part / 100;
          assert.ok(!(x > box.x + 1e-7 && x < box.x + box.width - 1e-7 && y > box.y + 1e-7 && y < box.y + box.height - 1e-7),
            `Force edge ${route.id} enters its endpoint ${id}`);
        }
      }
    }
  }
});

test("fixed-seed force cases check whole segments against both endpoint interiors", () => {
  let seed = 0x9152026;
  const random = maximum => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed % maximum; };
  // Independent slab intersection checks full line segments, including cases
  // where a bend lies outside the endpoint but its incoming segment crosses it.
  const enters = (a, b, box) => {
    let lower = 0, upper = 1;
    for (const [coordinate, size] of [["x", "width"], ["y", "height"]]) {
      const minimum = box[coordinate] + 1e-6, maximum = box[coordinate] + box[size] - 1e-6;
      const delta = b[coordinate] - a[coordinate];
      if (Math.abs(delta) < 1e-10) {
        if (a[coordinate] <= minimum || a[coordinate] >= maximum) return false;
        continue;
      }
      const t1 = (minimum - a[coordinate]) / delta, t2 = (maximum - a[coordinate]) / delta;
      lower = Math.max(lower, Math.min(t1, t2)); upper = Math.min(upper, Math.max(t1, t2));
      if (lower >= upper) return false;
    }
    return lower < upper;
  };
  for (let trial = 0; trial < 24; trial++) {
    const count = 2 + random(28);
    const nodes = Array.from({ length: count }, (_, i) => node(String(i).padStart(2, "0"),
      (i % 2 ? "넓" : "W").repeat(1 + random(100)), i % 3 ? "activity" : "place"));
    const edges = Array.from({ length: 5 + random(80) }, (_, i) => edge(String(i).padStart(3, "0"),
      nodes[random(count)].id, nodes[random(count)].id));
    for (const direction of ["LR", "TB"]) {
      const result = geometry.layout({ nodes, edges }, { layout: "force", direction });
      assertGeometry({ nodes, edges }, result);
      const byId = new Map(result.nodes.map(n => [n.id, n]));
      for (const route of result.edges) {
        const original = edges.find(e => e.id === route.id);
        for (let segment = 1; segment < route.points.length; segment++) for (const endpoint of [original.source, original.target]) {
          assert.ok(!enters(route.points[segment - 1], route.points[segment], byId.get(endpoint)),
            `Trial ${trial}/${direction} edge ${route.id} enters endpoint ${endpoint}`);
        }
      }
    }
  }
});

test("iterative SCC traversal supports long chains without recursion", () => {
  const count = 12000, graph = { nodes: Array.from({ length: count }, (_, i) => node(String(i).padStart(5, "0"))), edges: [] };
  for (let i = 1; i < count; i++) graph.edges.push(edge(`e${i}`, graph.nodes[i - 1].id, graph.nodes[i].id));
  const result = geometry.layout(graph);
  assert.equal(result.nodes.length, count); assert.equal(result.edges.length, count - 1);
  assert.ok(Number.isFinite(result.width));
});

test("wide disconnected layers do not spread node arrays into call arguments", () => {
  const count = 140000, graph = { nodes: Array.from({ length: count }, (_, i) => node(String(i), "")), edges: [] };
  const result = geometry.layout(graph);
  assert.equal(result.nodes.length, count);
  assert.ok(Number.isFinite(result.height));
  assert.ok(result.nodes.at(-1).y + result.nodes.at(-1).height <= result.height);
});

test("same implementation exports a browser global without module loaders", () => {
  const context = vm.createContext({});
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../../src/pix/viewer/assets/native_geometry.js"), "utf8"), context);
  assert.equal(typeof context.PIXNativeGeometry.layout, "function");
  assert.equal(context.PIXNativeGeometry.layout({ nodes: [], edges: [] }).width, 80);
});
