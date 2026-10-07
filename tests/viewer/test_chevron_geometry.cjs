"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const geometry = require("../../src/pix/viewer/assets/chevron_geometry.js");

const lane = (id, type = "Item") => ({id, label: `${type}: ${id}`, object_id: id, object_type: type, details: []});
const event = (id, label, start, end, lane_ids) => ({id, label, start, end, lane_ids, details: []});
// The two supplied design-review representatives, reproduced as semantic input
// here so test execution never depends on ignored artifacts or sample rendering.
function representative(rework = false) {
  const prefix = rework ? "execution-3" : "execution-2";
  const a = rework ? "Item_5" : "Item_3", b = rework ? "Item_6" : "Item_4", order = rework ? "Order_3" : "Order_2";
  const events = [event(`${prefix}:fork`, "Fork", 0, 0, [a, b, order]),
    event(`${prefix}:check`, "Check", 1, rework ? 3 : 2, [b]),
    event(`${prefix}:inspect`, "Inspect", 1, 1, [a]),
    event(`${prefix}:pack`, "Pack", 2, 2, [a])];
  if (rework) events.push(event(`${prefix}:rework`, "Inspect", 3, 3, [a]));
  events.push(event(`${prefix}:join`, "Join", rework ? 4 : 3, rework ? 4 : 3, [a, b, order]));
  return {kind: "chevron", id: "representative", lanes: [lane(a), lane(b), lane(order, "Order")], events};
}
function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
function finiteBounds(result) {
  assert.ok(Number.isFinite(result.width) && result.width > 0);
  assert.ok(Number.isFinite(result.height) && result.height > 0);
  const point = (x, y) => {
    assert.ok(Number.isFinite(x) && x >= 0 && x <= result.width, `x=${x}/${result.width}`);
    assert.ok(Number.isFinite(y) && y >= 0 && y <= result.height, `y=${y}/${result.height}`);
  };
  for (const shape of [...result.lanes, ...result.appearances]) {
    point(shape.x, shape.y); point(shape.x + shape.width, shape.y + shape.height);
    assert.ok(shape.width > 0 && shape.height > 0);
    point(shape.labelX, shape.labelY);
  }
  for (const appearance of result.appearances) {
    assert.equal(appearance.points.split(" ").length, 6);
    for (const pair of appearance.points.split(" ")) point(...pair.split(",").map(Number));
    assert.ok(appearance.labelMaxWidth >= 60);
    assert.ok(appearance.labelLines.length >= 1 && appearance.labelLines.length <= 2);
  }
  for (const tick of result.axis.ticks) {
    point(tick.x, tick.y); point(tick.line.x1, tick.line.y1); point(tick.line.x2, tick.line.y2);
  }
}

for (const rework of [false, true]) {
  for (const orientation of ["horizontal", "vertical"]) {
    for (const style of ["classic", "neutral"]) {
      test(`${style} ${orientation}: representative ${rework ? "6 events / 10 appearances" : "5 events / 9 appearances"} preserves incidence and inclusive slots`, () => {
        const panel = freeze(representative(rework)), original = structuredClone(panel);
        const result = geometry.layout(panel, {orientation, style, availableWidth: 390});
        assert.deepEqual(panel, original); finiteBounds(result);
        assert.equal(result.orientation, orientation);
        assert.equal(result.slots, rework ? 5 : 4);
        assert.equal(result.appearanceCount, rework ? 10 : 9);
        assert.equal(result.appearances.length, result.appearanceCount);
        assert.deepEqual(result.lanes.map(item => item.id), panel.lanes.map(item => item.id));
        const pairs = panel.events.flatMap(item => item.lane_ids.map(id => [item.id, id]));
        assert.deepEqual(result.appearances.map(item => [item.eventId, item.laneId]), pairs);
        const flowAxis = orientation === "horizontal" ? "x" : "y";
        const extent = orientation === "horizontal" ? "width" : "height";
        for (const source of panel.events) {
          const shapes = result.appearances.filter(item => item.eventId === source.id);
          assert.equal(new Set(shapes.map(item => item[flowAxis])).size, 1);
          assert.equal(new Set(shapes.map(item => item[extent])).size, 1);
          assert.equal(shapes[0][extent] + result.metrics.spanInset * 2, (source.end - source.start + 1) * result.metrics.slotStep);
          assert.equal(shapes[0][flowAxis], result.metrics.flowStart + source.start * result.metrics.slotStep + result.metrics.spanInset);
        }
        // Empty order-lane slots remain empty; drawing does not invent events.
        assert.equal(result.appearances.filter(item => item.laneId.startsWith("Order_")).length, 2);
        if (rework) {
          const distinct = panel.events.filter(item => item.label === "Inspect").map(item => item.id);
          assert.equal(distinct.length, 2);
          assert.notEqual(result.appearances.find(item => item.eventId === distinct[0])[flowAxis], result.appearances.find(item => item.eventId === distinct[1])[flowAxis]);
        }
      });
    }
  }
}

test("classic horizontal preserves the previous viewport and chevron polygon coordinates", () => {
  const result = geometry.layout(representative(), {style: "classic"});
  assert.equal(result.width, 841); assert.equal(result.height, 327);
  assert.deepEqual(result.metrics, {flowStart: 190, crossStart: 66, slotStep: 154, laneStep: 72, spanInset: 5, spanCrossInset: 10, spanThickness: 51, tip: 13, endPadding: 35, crossPadding: 45});
  assert.equal(result.appearances[0].points, "195,76 326,76 339,101.5 326,127 195,127 208,101.5");
  assert.equal(result.lanes[0].labelX, 34); assert.equal(result.lanes[0].labelY, 98);
  assert.deepEqual(result.axis.ticks[0], {value: 0, x: 267, y: 44, line: {x1: 190, y1: 53, x2: 190, y2: 302}});
});

test("neutral short-label defaults fit a 700px canvas without shrinking the geometry", () => {
  const result = geometry.layout(representative());
  assert.equal(result.style, "neutral"); assert.equal(result.orientation, "horizontal");
  assert.equal(result.width, 698); assert.equal(result.metrics.slotStep, 130);
  assert.equal(result.metrics.spanThickness, 58);
  const vertical = geometry.layout(representative(), {style: "neutral", orientation: "vertical"});
  assert.equal(vertical.width, 422); assert.equal(vertical.metrics.slotStep, 108);
  assert.ok(vertical.lanes.every(item => item.labelAnchor === "middle" && item.labelMaxWidth >= 96));
  assert.deepEqual(vertical.appearances.find(item => item.eventId.endsWith(":inspect")).labelLines, ["Inspect"]);
});

test("explicit horizontal and vertical ignore viewport width; only auto responds", () => {
  const panel = representative();
  for (const orientation of ["horizontal", "vertical"]) {
    assert.deepEqual(geometry.layout(panel, {orientation, style: "neutral", availableWidth: 390}), geometry.layout(panel, {orientation, style: "neutral", availableWidth: 2400}));
  }
  const width = geometry.layout(panel, {style: "neutral"}).horizontalWidth;
  assert.equal(geometry.layout(panel, {orientation: "auto", style: "neutral", availableWidth: width}).orientation, "horizontal");
  assert.equal(geometry.layout(panel, {orientation: "auto", style: "neutral", availableWidth: width - 1}).orientation, "vertical");
  assert.equal(geometry.layout(panel, {orientation: "auto", availableWidth: 0}).orientation, "vertical");
});

test("empty panels and lanes without events remain visible in both orientations", () => {
  for (const orientation of ["horizontal", "vertical"]) {
    for (const lanes of [[], [lane("empty")]]) {
      const result = geometry.layout({lanes, events: []}, {orientation, style: "neutral"});
      finiteBounds(result); assert.equal(result.slots, 1); assert.equal(result.appearanceCount, 0);
      assert.equal(result.lanes.length, lanes.length);
    }
  }
});

test("changing dates, descriptions or object names does not change slot membership", () => {
  const original = representative(), changed = structuredClone(original);
  for (const item of changed.events) item.details = [{name: "observed_timestamp", value: "2100-01-01T00:00:00Z"}];
  changed.lanes[0].object_id = "a new identity label";
  const a = geometry.layout(original), b = geometry.layout(changed);
  const membership = result => result.appearances.map(({eventId, laneId, laneIndex, start, end}) => ({eventId, laneId, laneIndex, start, end}));
  assert.deepEqual(membership(a), membership(b));
});

test("hostile and very long multilingual labels stay data with bounded geometry and display text", () => {
  const panel = representative();
  const hostile = '</text><script>alert("x")</script> 작업'.repeat(10000);
  panel.events[0].label = hostile;
  panel.lanes[0].label = hostile;
  panel.lanes[0].object_id = hostile;
  for (const orientation of ["horizontal", "vertical"]) {
    const result = geometry.layout(panel, {orientation, style: "neutral"});
    finiteBounds(result);
    assert.ok(result.width < 2000 && result.height < 2000);
    assert.equal(result.lanes[0].label, hostile);
    assert.ok(result.appearances.every(item => item.labelLines.join("").length < 100));
    assert.ok(result.appearances[0].labelLines.at(-1).endsWith("…"));
    assert.match(result.appearances[0].points, /^[\d., ]+$/);
  }
});

test("lane and event identities are independent of labels and safe for reserved object keys", () => {
  const panel = {lanes: [lane("__proto__"), lane("constructor")], events: [event("__proto__", "same", 0, 0, ["__proto__"]), event("constructor", "same", 1, 1, ["constructor"])]};
  const result = geometry.layout(panel);
  assert.deepEqual(result.appearances.map(item => item.eventId), ["__proto__", "constructor"]);
  assert.notEqual(result.appearances[0].x, result.appearances[1].x);
});

test("invalid contracts fail before rendering ambiguous or unsafe geometry", () => {
  const mutations = [
    p => p.lanes.push({...p.lanes[0]}), p => p.events.push({...p.events[0]}),
    p => p.events[0].lane_ids = ["missing"], p => p.events[0].lane_ids = [],
    p => p.events[0].lane_ids.push(p.events[0].lane_ids[0]),
    p => p.events[0].start = -1, p => p.events[0].start = .5,
    p => p.events[0].end = -1, p => p.events[0].end = Infinity,
    p => p.events[0].end = Number.MAX_SAFE_INTEGER,
    p => p.events[0].id = "", p => p.lanes[0].id = {},
    p => p.events[0].label = null, p => p.lanes[0].object_type = null,
    p => p.events[0] = null, p => p.lanes[0] = null
  ];
  for (const mutate of mutations) { const panel = representative(); mutate(panel); assert.throws(() => geometry.layout(panel)); }
  for (const panel of [null, [], {}, {lanes: [], events: null}]) assert.throws(() => geometry.layout(panel));
});

test("geometry limits bound slot, appearance and lane allocation", () => {
  const panel = {lanes: [lane("a")], events: [event("e", "e", 0, geometry.LIMIT - 1, ["a"])]};
  assert.equal(geometry.layout(panel).axis.ticks.length, geometry.LIMIT);
  panel.events[0].end++;
  assert.throws(() => geometry.layout(panel), /10000/);
  const lanes = Array.from({length: geometry.LIMIT + 1}, (_, index) => lane(String(index)));
  assert.throws(() => geometry.layout({lanes, events: []}), /10000/);
  const accepted = lanes.slice(0, geometry.LIMIT);
  const events = [event("a", "a", 0, 0, accepted.map(item => item.id)), event("b", "b", 1, 1, ["0"])];
  assert.throws(() => geometry.layout({lanes: accepted, events}), /10000/);
});

test("the configurable appearance limit accepts raised limits and enforces smaller limits", () => {
  const raised = geometry.LIMIT + 1;
  const panel = {lanes: [lane("a")], events: [event("e", "e", 0, raised - 1, ["a"])]};
  assert.throws(() => geometry.layout(panel), /10000/);
  const result = geometry.layout(panel, {appearanceLimit: raised});
  assert.equal(result.slots, raised);
  assert.equal(result.axis.ticks.length, raised);
  const compact = {lanes: [lane("a")], events: [event("e", "e", 0, 1, ["a"])]};
  assert.throws(() => geometry.layout(compact, {appearanceLimit: 1}), /1 appearance, lane or slot limit/);
  assert.equal(geometry.layout(compact, {appearanceLimit: 2}).slots, 2);
  assert.throws(() => geometry.layout(representative(), {appearanceLimit: 8}), /8 appearance, lane or slot limit/);
  const lanes = Array.from({length: raised}, (_, index) => lane(String(index)));
  const many = geometry.layout({lanes, events: [event("shared", "Shared", 0, 0, lanes.map(item => item.id))]}, {appearanceLimit: raised});
  assert.equal(many.lanes.length, raised);
  assert.equal(many.appearanceCount, raised);
});

test("label wrapping reserves space for 13px wide Latin and 14px CJK glyphs", () => {
  assert.deepEqual(geometry.wrapLabel("Inspect", 60, 2), ["Inspect"]);
  assert.deepEqual(geometry.wrapLabel("WWWWWWW", 40, 2), ["WWW", "WW…"]);
  assert.deepEqual(geometry.wrapLabel("가나다라마바사", 40, 2), ["가나", "다…"]);
  assert.deepEqual(geometry.wrapLabel("ABC DEFG", 40, 2), ["ABC", "DEFG"]);
});

test("unknown or invalid options reject instead of silently changing orientation", () => {
  const panel = representative();
  for (const options of [null, [], {orientation: "LR"}, {orientation: null}, {style: "unknown"}, {availableWidth: "390"}, {availableWidth: NaN}, {availableWidth: Infinity}, {availableWidth: -1}, {appearanceLimit: 0}, {appearanceLimit: -1}, {appearanceLimit: 1.5}, {appearanceLimit: "10000"}, {appearanceLimit: NaN}, {appearanceLimit: Infinity}, {appearanceLimit: Number.MAX_SAFE_INTEGER + 1}]) assert.throws(() => geometry.layout(panel, options));
});

test("standalone browser script exposes the same dependency-free API", () => {
  const script = fs.readFileSync(path.resolve(__dirname, "../../src/pix/viewer/assets/chevron_geometry.js"), "utf8");
  const sandbox = {};
  vm.runInNewContext(script, sandbox);
  assert.equal(typeof sandbox.PIXChevronGeometry.layout, "function");
  const actual = sandbox.PIXChevronGeometry.layout(representative(), {orientation: "vertical", style: "neutral"});
  assert.deepEqual(JSON.parse(JSON.stringify(actual)), geometry.layout(representative(), {orientation: "vertical", style: "neutral"}));
});
