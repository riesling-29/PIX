'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const PIXLayout = require('../../src/pix/viewer/assets/layout.js');
const ELK = require('../../src/pix/viewer/assets/vendor/elk.bundled.js');

function exampleGraph() {
  return {
    object_types: ['Order', 'Item'],
    nodes: [
      { id: 'n3', label: 'Deliver', event_count: 1, object_count: 2 },
      { id: 'n1', label: 'Receive', event_count: 2, object_count: 3 },
      { id: 'n2', label: 'Pack the shared order and its items', event_count: 3, object_count: 4 },
    ],
    edges: [
      { id: 'e4', source: 'n2', target: 'n3', object_type: 'Order', counts: { event_pairs: 1, unique_objects: 2, occurrences: 2 }, evidence: [{ source_event_id: 'pack', target_event_id: 'deliver', object_id: 'o1' }] },
      { id: 'e3', source: 'n2', target: 'n2', object_type: 'Order', counts: { event_pairs: 1, unique_objects: 1, occurrences: 1 }, evidence: [{ source_event_id: 'pack1', target_event_id: 'pack2', object_id: 'o1' }] },
      { id: 'e2', source: 'n1', target: 'n2', object_type: 'Item', counts: { event_pairs: 2, unique_objects: 3, occurrences: 3 }, evidence: [{ source_event_id: 'receive', target_event_id: 'pack', object_id: 'i1' }] },
      { id: 'e1', source: 'n1', target: 'n2', object_type: 'Order', counts: { event_pairs: 2, unique_objects: 2, occurrences: 2 }, evidence: [{ source_event_id: 'receive', target_event_id: 'pack', object_id: 'o1' }] },
    ],
  };
}

function deepFreeze(value) {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(deepFreeze);
    Object.freeze(value);
  }
  return value;
}

function option(options, suffix) {
  const entry = Object.entries(options || {}).find(([key]) => key === suffix || key.endsWith(`.${suffix}`));
  return entry && entry[1];
}

function finitePoint(point) {
  assert.equal(Number.isFinite(point.x), true);
  assert.equal(Number.isFinite(point.y), true);
}

test('object type colors are deterministic and independent of selection order', () => {
  const first = PIXLayout.typeColor('Order');
  assert.match(first, /^hsl\(/);
  PIXLayout.typeColor('Item');
  PIXLayout.typeColor('배송 📦');
  assert.equal(PIXLayout.typeColor('Order'), first);
  assert.equal(PIXLayout.typeColor('배송 📦'), PIXLayout.typeColor('배송 📦'));
  assert.notEqual(PIXLayout.typeColor('Order'), PIXLayout.typeColor('Item'));
});

test('label wrapping preserves ordinary words and bounds every line', () => {
  const lines = PIXLayout.wrapLabel('Receive a shared order', 12, 4);
  assert.ok(Array.isArray(lines));
  assert.ok(lines.length > 1);
  assert.ok(lines.length <= 4);
  for (const line of lines) assert.ok(Array.from(line).length <= 12);
  assert.equal(lines.join(' ').replace(/\s+/g, ' '), 'Receive a shared order');
});

test('label wrapping counts Unicode code points without splitting surrogate pairs', () => {
  const label = '📦🚚🧾📦🚚🧾📦🚚🧾';
  const lines = PIXLayout.wrapLabel(label, 4, 4);
  assert.equal(lines.join(''), label);
  for (const line of lines) {
    assert.ok(Array.from(line).length <= 4);
    assert.equal(line.isWellFormed(), true);
  }
});

test('long labels are truncated explicitly within the requested line budget', () => {
  const lines = PIXLayout.wrapLabel('배송📦'.repeat(30), 5, 2);
  assert.equal(lines.length, 2);
  assert.ok(lines.at(-1).endsWith('…'));
  for (const line of lines) {
    assert.ok(Array.from(line).length <= 5);
    assert.equal(line.isWellFormed(), true);
  }
});

test('visibility filtering leaves source graph intact and supports both filter forms', () => {
  const graph = deepFreeze(exampleGraph());
  const allIds = graph.edges.map(edge => edge.id);
  assert.deepEqual(PIXLayout.visibleEdges(graph).map(edge => edge.id), allIds);
  const itemIds = graph.edges.filter(edge => edge.object_type === 'Item').map(edge => edge.id);
  assert.deepEqual(PIXLayout.visibleEdges(graph, new Set(['Order'])).map(edge => edge.id), itemIds);
  assert.deepEqual(PIXLayout.visibleEdges(graph, ['Order']).map(edge => edge.id), itemIds);
  assert.deepEqual(PIXLayout.visibleEdges(graph, ['Order', 'Item']), []);
  assert.deepEqual(graph.edges.map(edge => edge.id), allIds);
});

test('count selection preserves the three distinct aggregation units including zero', () => {
  const edge = { counts: { event_pairs: 1, unique_objects: 2, occurrences: 3 } };
  assert.equal(PIXLayout.edgeCount(edge, 'event_pairs'), 1);
  assert.equal(PIXLayout.edgeCount(edge, 'unique_objects'), 2);
  assert.equal(PIXLayout.edgeCount(edge, 'occurrences'), 3);
  assert.equal(PIXLayout.edgeCount({ counts: { occurrences: 0 } }, 'occurrences'), 0);
  assert.throws(() => PIXLayout.edgeCount(edge, 'frequency'));
});

test('invalid or missing counts cannot silently render as frequencies', () => {
  for (const count of [-1, 1.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1, '2', null, undefined]) {
    assert.throws(() => PIXLayout.edgeCount({ counts: { occurrences: count } }, 'occurrences'));
  }
  assert.throws(() => PIXLayout.edgeCount({}, 'occurrences'));
});

test('ELK input has stable ID order, explicit direction, and readable label dimensions', () => {
  const graph = deepFreeze(exampleGraph());
  const elk = PIXLayout.toElkGraph(graph);
  assert.deepEqual(elk.children.map(node => node.id), ['n1', 'n2', 'n3']);
  assert.deepEqual(elk.edges.map(edge => edge.id), ['e1', 'e2', 'e3', 'e4']);
  assert.equal(option(elk.layoutOptions, 'algorithm'), 'layered');
  assert.equal(option(elk.layoutOptions, 'direction'), 'RIGHT');
  for (const node of elk.children) {
    assert.ok(Number.isFinite(node.width) && node.width > 0);
    assert.ok(Number.isFinite(node.height) && node.height > 0);
    assert.ok(Array.isArray(node.labelLines) && node.labelLines.length > 0);
  }
  const reversed = { ...exampleGraph(), nodes: [...graph.nodes].reverse(), edges: [...graph.edges].reverse() };
  assert.deepEqual(PIXLayout.toElkGraph(reversed), elk);
});

test('each directed edge gets dedicated EAST and WEST ports, including loops', () => {
  const elk = PIXLayout.toElkGraph(exampleGraph());
  const ports = new Map();
  for (const node of elk.children) {
    for (const port of node.ports) {
      assert.equal(ports.has(port.id), false);
      ports.set(port.id, { node: node.id, port });
    }
  }
  const usedPorts = [];
  for (const edge of elk.edges) {
    assert.equal(edge.sources.length, 1);
    assert.equal(edge.targets.length, 1);
    const source = ports.get(edge.sources[0]);
    const target = ports.get(edge.targets[0]);
    assert.ok(source && target);
    assert.equal(source.node, edge.data.source);
    assert.equal(target.node, edge.data.target);
    assert.equal(option(source.port.layoutOptions, 'side'), 'EAST');
    assert.equal(option(target.port.layoutOptions, 'side'), 'WEST');
    usedPorts.push(source.port.id, target.port.id);
  }
  assert.equal(new Set(usedPorts).size, elk.edges.length * 2);
});

test('ELK data is a deep clone of the analysis graph', () => {
  const graph = exampleGraph();
  const before = structuredClone(graph);
  const elk = PIXLayout.toElkGraph(deepFreeze(graph));
  elk.children[0].data.label = 'changed by renderer';
  elk.edges[0].data.counts.occurrences = 999;
  elk.edges[0].data.evidence[0].object_id = 'changed by renderer';
  assert.deepEqual(graph, before);
});

test('layout engine mutations cannot change caller-owned graph or evidence', async () => {
  const graph = deepFreeze(exampleGraph());
  const before = structuredClone(graph);
  let calls = 0;
  const layout = PIXLayout.createElkLayout({
    async layout(elk) {
      calls += 1;
      elk.children[0].data.label = 'engine mutation';
      elk.edges[0].data.evidence[0].object_id = 'engine mutation';
      elk.children.forEach((node, index) => { node.x = index * 180; node.y = 20; });
      elk.edges.forEach(edge => {
        edge.sections = [{ startPoint: { x: 10, y: 20 }, endPoint: { x: 100, y: 20 } }];
        for (const label of edge.labels || []) { label.x = 20; label.y = 10; }
      });
      elk.width = 300;
      elk.height = 200;
      return elk;
    },
  });
  const result = await layout(graph);
  assert.equal(calls, 1);
  assert.equal(result.width, 300);
  assert.deepEqual(graph, before);
});

test('empty graph has an explicit finite layout', async () => {
  const layout = PIXLayout.createElkLayout(new ELK());
  const result = await layout(deepFreeze({ nodes: [], edges: [], object_types: [] }));
  assert.deepEqual(result.children, []);
  assert.deepEqual(result.edges, []);
  assert.ok(Number.isFinite(result.width) && result.width >= 0);
  assert.ok(Number.isFinite(result.height) && result.height >= 0);
});

test('vendored ELK routes parallel edges and a self loop with finite geometry', async () => {
  const graph = deepFreeze(exampleGraph());
  const before = structuredClone(graph);
  const result = await PIXLayout.createElkLayout(new ELK())(graph);
  assert.ok(Number.isFinite(result.width) && result.width > 0);
  assert.ok(Number.isFinite(result.height) && result.height > 0);
  for (const node of result.children) {
    finitePoint(node);
    assert.ok(node.width > 0 && node.height > 0);
  }
  const paths = new Map();
  for (const edge of result.edges) {
    assert.ok(Array.isArray(edge.sections) && edge.sections.length > 0);
    for (const section of edge.sections) {
      finitePoint(section.startPoint);
      finitePoint(section.endPoint);
      for (const point of section.bendPoints || []) finitePoint(point);
    }
    const path = PIXLayout.sectionPath(edge);
    assert.match(path, /^M\s*/);
    assert.doesNotMatch(path, /NaN|Infinity|undefined/);
    paths.set(edge.id, path);
  }
  assert.notEqual(paths.get('e1'), paths.get('e2'));
  assert.ok(paths.get('e3').length > 0);
  assert.deepEqual(graph, before);
});

test('section paths preserve every disconnected route section', () => {
  const path = PIXLayout.sectionPath({ sections: [
    { startPoint: { x: 1, y: 2 }, bendPoints: [{ x: 3, y: 4 }], endPoint: { x: 5, y: 6 } },
    { startPoint: { x: 7, y: 8 }, endPoint: { x: 9, y: 10 } },
  ] });
  assert.equal((path.match(/M/g) || []).length, 2);
  assert.equal((path.match(/L/g) || []).length, 3);
  assert.doesNotMatch(path, /NaN|Infinity|undefined/);
  assert.equal(PIXLayout.sectionPath({ sections: [] }), '');
  assert.equal(PIXLayout.sectionPath({}), '');
});

test('malformed route coordinates fail explicitly instead of producing broken SVG', () => {
  const valid = { startPoint: { x: 0, y: 1 }, endPoint: { x: 2, y: 3 } };
  for (const coordinate of [Infinity, -Infinity, NaN, undefined, '0', null]) {
    assert.throws(() => PIXLayout.sectionPath({ sections: [{ ...valid, startPoint: { x: coordinate, y: 1 } }] }));
  }
  assert.throws(() => PIXLayout.sectionPath({ sections: [{ startPoint: { x: 0, y: 1 } }] }));
  assert.throws(() => PIXLayout.sectionPath({ sections: [{ ...valid, bendPoints: [{ x: 1 }] }] }));
});

function replacementEngine(mutate) {
  return {
    async layout(elk) {
      elk.width = 800;
      elk.height = 400;
      elk.children.forEach((node, index) => { node.x = index * 180; node.y = 20; });
      elk.edges.forEach(edge => {
        edge.sections = [{ startPoint: { x: 10, y: 20 }, endPoint: { x: 100, y: 20 } }];
        for (const label of edge.labels || []) { label.x = 20; label.y = 10; }
      });
      mutate(elk);
      return elk;
    },
  };
}

test('replacement engine must retain the complete node and edge identity sets', async t => {
  const malformed = [
    ['omitted nodes', graph => { delete graph.children; }],
    ['omitted edges', graph => { delete graph.edges; }],
    ['removed node', graph => { graph.children.pop(); }],
    ['removed edge', graph => { graph.edges.pop(); }],
    ['missing node ID', graph => { delete graph.children[0].id; }],
    ['missing edge ID', graph => { delete graph.edges[0].id; }],
    ['replaced node ID', graph => { graph.children[0].id = 'new-node'; }],
    ['replaced edge ID', graph => { graph.edges[0].id = 'new-edge'; }],
    ['duplicate node ID', graph => { graph.children[0].id = graph.children[1].id; }],
    ['duplicate edge ID', graph => { graph.edges[0].id = graph.edges[1].id; }],
  ];
  for (const [name, mutate] of malformed) {
    await t.test(name, async () => {
      const layout = PIXLayout.createElkLayout(replacementEngine(mutate));
      await assert.rejects(layout(exampleGraph()), TypeError);
    });
  }
});

test('replacement engine cannot report negative graph or nonpositive node dimensions', async t => {
  const malformed = [
    ['negative graph width', graph => { graph.width = -1; }],
    ['negative graph height', graph => { graph.height = -1; }],
    ['zero node width', graph => { graph.children[0].width = 0; }],
    ['negative node width', graph => { graph.children[0].width = -1; }],
    ['zero node height', graph => { graph.children[0].height = 0; }],
    ['negative node height', graph => { graph.children[0].height = -1; }],
  ];
  for (const [name, mutate] of malformed) {
    await t.test(name, async () => {
      const layout = PIXLayout.createElkLayout(replacementEngine(mutate));
      await assert.rejects(layout(exampleGraph()), TypeError);
    });
  }
});

test('replacement engine must return a visible route for every retained edge', async t => {
  const malformed = [
    ['omitted sections', graph => { delete graph.edges[0].sections; }],
    ['empty sections', graph => { graph.edges[0].sections = []; }],
  ];
  for (const [name, mutate] of malformed) {
    await t.test(name, async () => {
      const layout = PIXLayout.createElkLayout(replacementEngine(mutate));
      await assert.rejects(layout(exampleGraph()), TypeError);
    });
  }
});

function modelGraph(kind = 'petri_net') {
  const objectType = kind === 'ocpn' ? 'Order' : null;
  const node = (id, label, nodeKind, initial = 0, final = 0) => ({
    id, label, kind: nodeKind, object_type: nodeKind === 'place' ? objectType : null,
    initial_count: initial, final_count: final,
  });
  const edge = (id, source, target) => ({
    id, source, target, object_type: objectType, weight: 1,
    variable: false, min_objects: 1, max_objects: 1,
  });
  return {
    kind,
    object_types: objectType ? [objectType] : [],
    nodes: [
      node('p0', 'Available', 'place', 1),
      node('p1', 'Waiting for approval', 'place'),
      node('p2', 'Complete', 'place', 0, 1),
      node('p-isolated', 'Disconnected archive', 'place'),
      node('t1', 'Approve', 'transition'),
      node('t2', 'Approve', 'transition'),
      node('tau', '', 'silent'),
    ],
    edges: [
      edge('a1', 'p0', 't1'),
      edge('a2', 't1', 'p1'),
      edge('a3', 'p1', 't2'),
      edge('a4', 't2', 'p0'),
      edge('a5', 'p1', 'tau'),
      edge('a6', 'tau', 'p2'),
    ],
  };
}

test('Petri net arc labels express weight without frequency semantics', () => {
  const edge = modelGraph().edges[0];
  assert.equal(PIXLayout.modelEdgeLabel(edge, 'petri_net'), '');
  const weightedLabel = PIXLayout.modelEdgeLabel({ ...edge, weight: 3 }, 'petri_net');
  assert.equal(weightedLabel, 'weight 3');
  assert.doesNotMatch(weightedLabel, /occurrences|event pairs|unique objects/);
});

test('Petri net arc weights must be positive safe integers', () => {
  const edge = modelGraph().edges[0];
  for (const weight of [0, -1, 1.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1, '2', null, undefined]) {
    assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, weight }, 'petri_net'));
  }
});

test('OCPN arc labels distinguish fixed and finite or unbounded variable cardinality', () => {
  const edge = modelGraph('ocpn').edges[0];
  const fixed = PIXLayout.modelEdgeLabel(edge, 'ocpn');
  assert.match(fixed, /Order/);
  assert.match(fixed, /1 object/);
  const finite = PIXLayout.modelEdgeLabel({ ...edge, variable: true, min_objects: 1, max_objects: 3 }, 'ocpn');
  assert.match(finite, /Order/);
  assert.match(finite, /\[1,\s*3\] objects/);
  const unbounded = PIXLayout.modelEdgeLabel({ ...edge, variable: true, min_objects: 0, max_objects: null }, 'ocpn');
  assert.match(unbounded, /Order/);
  assert.match(unbounded, /\[0,\s*∞\] objects/);
  for (const label of [fixed, finite, unbounded]) assert.doesNotMatch(label, /occurrences|event pairs|unique objects/);
});

test('OCPN cardinality ranges reject invalid or inverted bounds', () => {
  const edge = { ...modelGraph('ocpn').edges[0], variable: true };
  for (const min_objects of [-1, 0.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1, '1', null, undefined]) {
    assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, min_objects, max_objects: null }, 'ocpn'));
  }
  for (const max_objects of [-1, 1.5, Infinity, NaN, Number.MAX_SAFE_INTEGER + 1, '3', undefined]) {
    assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, min_objects: 0, max_objects }, 'ocpn'));
  }
  assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, min_objects: 3, max_objects: 2 }, 'ocpn'));
  assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, object_type: null }, 'ocpn'));
  for (const [min_objects, max_objects] of [[0, 1], [1, null], [2, 2]]) {
    assert.throws(() => PIXLayout.modelEdgeLabel({ ...edge, variable: false, min_objects, max_objects }, 'ocpn'));
  }
});

test('model layout preserves place, visible and silent transition shape distinctions', () => {
  for (const kind of ['petri_net', 'ocpn']) {
    const graph = deepFreeze(modelGraph(kind));
    const input = PIXLayout.toElkGraph(graph);
    const nodes = new Map(input.children.map(node => [node.id, node]));
    const place = nodes.get('p0');
    const transition = nodes.get('t1');
    const silent = nodes.get('tau');
    assert.equal(place.shape.kind, 'place');
    assert.equal(place.shape.width, place.shape.height);
    assert.ok(place.shape.radius > 0);
    assert.equal(place.shape.width, place.shape.radius * 2);
    assert.ok(place.height > place.shape.height, 'place reserves space below its circle');
    assert.equal(transition.shape.kind, 'transition');
    assert.equal(silent.shape.kind, 'silent');
    assert.ok(silent.shape.width < transition.shape.width);
    for (const node of input.children) {
      for (const key of ['x', 'y', 'width', 'height', 'cx', 'cy']) {
        assert.ok(Number.isFinite(node.shape[key]), `${kind} ${node.id} shape.${key}`);
      }
      assert.ok(node.shape.width > 0 && node.shape.height > 0);
      assert.ok(node.shape.x >= 0 && node.shape.y >= 0);
      assert.ok(node.width >= node.shape.x + node.shape.width);
      assert.ok(node.height >= node.shape.y + node.shape.height);
    }
    assert.equal(nodes.get('t1').data.label, nodes.get('t2').data.label);
    assert.notEqual(nodes.get('t1').id, nodes.get('t2').id);
    assert.equal(nodes.get('p0').data.initial_count, 1);
    assert.equal(nodes.get('p2').data.final_count, 1);
    assert.ok(nodes.has('p-isolated'));
    for (const edge of input.edges) {
      assert.equal(Object.hasOwn(edge.data, 'counts'), false);
      assert.doesNotMatch((edge.labels || []).map(label => label.text).join(' '), /occurrences/);
    }
  }
});

function assertModelAnchor(point, node) {
  const shape = node.shape;
  const tolerance = 1;
  if (shape.kind === 'place') {
    const distance = Math.hypot(point.x - node.x - shape.cx, point.y - node.y - shape.cy);
    assert.ok(Math.abs(distance - shape.radius) <= tolerance,
      `${node.id} route must meet its place circle (distance ${distance}, radius ${shape.radius})`);
  } else {
    const left = node.x + shape.x;
    const right = left + shape.width;
    assert.ok(Math.min(Math.abs(point.x - left), Math.abs(point.x - right)) <= tolerance,
      `${node.id} route must meet a visible transition boundary`);
    assert.ok(point.y >= node.y + shape.y - tolerance && point.y <= node.y + shape.y + shape.height + tolerance,
      `${node.id} route must meet the transition, not its label reserve`);
  }
}

test('model ELK layouts retain bipartite cycles, duplicate labels and disconnected places', async t => {
  for (const kind of ['petri_net', 'ocpn']) {
    await t.test(kind, async () => {
      const graph = modelGraph(kind);
      if (kind === 'ocpn') Object.assign(graph.edges[1], { variable: true, min_objects: 0, max_objects: null });
      else graph.edges[1].weight = 2;
      const before = structuredClone(graph);
      const result = await PIXLayout.createElkLayout(new ELK())(deepFreeze(graph));
      assert.deepEqual(result.children.map(node => node.id).sort(), graph.nodes.map(node => node.id).sort());
      assert.deepEqual(result.edges.map(edge => edge.id).sort(), graph.edges.map(edge => edge.id).sort());
      assert.ok(result.width > 0 && result.height > 0);
      for (const node of result.children) {
        finitePoint(node);
        assert.ok(node.width > 0 && node.height > 0);
      }
      const nodes = new Map(result.children.map(node => [node.id, node]));
      for (const edge of result.edges) {
        assert.ok(edge.sections.length > 0);
        for (const section of edge.sections) {
          finitePoint(section.startPoint);
          finitePoint(section.endPoint);
          for (const point of section.bendPoints || []) finitePoint(point);
        }
        assert.doesNotMatch(PIXLayout.sectionPath(edge), /NaN|Infinity|undefined/);
        assertModelAnchor(edge.sections[0].startPoint, nodes.get(edge.data.source));
        assertModelAnchor(edge.sections.at(-1).endPoint, nodes.get(edge.data.target));
      }
      assert.deepEqual(graph, before);
    });
  }
});

test('OCPN layout rejects nonfinite maxima before JSON cloning can turn them into unbounded ranges', () => {
  for (const max_objects of [Infinity, -Infinity, NaN]) {
    const graph = modelGraph('ocpn');
    Object.assign(graph.edges[0], { variable: true, min_objects: 0, max_objects });
    assert.throws(() => PIXLayout.toElkGraph(graph));
  }
});

test('OCPN count bounds remain fully visible when a long object type is truncated', () => {
  const graph = modelGraph('ocpn');
  const objectType = '아주 긴 주문 타입 📦 '.repeat(20);
  graph.object_types = [objectType];
  for (const node of graph.nodes) if (node.kind === 'place') node.object_type = objectType;
  for (const edge of graph.edges) edge.object_type = objectType;
  Object.assign(graph.edges[0], {
    variable: true,
    min_objects: Number.MAX_SAFE_INTEGER,
    max_objects: Number.MAX_SAFE_INTEGER,
  });
  const elk = PIXLayout.toElkGraph(deepFreeze(graph));
  const edge = elk.edges.find(item => item.id === graph.edges[0].id);
  const cardinality = `[${Number.MAX_SAFE_INTEGER},${Number.MAX_SAFE_INTEGER}] objects`;
  assert.equal(edge.labelLines.at(-1).replace(/,\s+/g, ','), cardinality);
  assert.equal(edge.labels[0].text.split('\n').at(-1).replace(/,\s+/g, ','), cardinality);
});

test('OCPN multiplicity must use cardinality bounds rather than a Petri net arc weight', () => {
  const graph = modelGraph('ocpn');
  graph.edges[0].weight = 2;
  assert.throws(() => PIXLayout.modelEdgeLabel(graph.edges[0], 'ocpn'));
  assert.throws(() => PIXLayout.toElkGraph(graph));
});

test('replacement engine must retain required edge labels and valid label geometry', async t => {
  const malformed = [
    ['omitted labels', graph => { delete graph.edges[0].labels; }],
    ['removed labels', graph => { graph.edges[0].labels = []; }],
    ['missing label ID', graph => { delete graph.edges[0].labels[0].id; }],
    ['replaced label ID', graph => { graph.edges[0].labels[0].id = 'other-label'; }],
    ['missing label x', graph => { delete graph.edges[0].labels[0].x; }],
    ['NaN label x', graph => { graph.edges[0].labels[0].x = NaN; }],
    ['infinite label y', graph => { graph.edges[0].labels[0].y = Infinity; }],
    ['zero label width', graph => { graph.edges[0].labels[0].width = 0; }],
    ['negative label height', graph => { graph.edges[0].labels[0].height = -1; }],
  ];
  for (const kind of ['dfg', 'ocdfg']) {
    for (const [name, mutate] of malformed) {
      await t.test(`${kind}: ${name}`, async () => {
        const layout = PIXLayout.createElkLayout(replacementEngine(mutate));
        await assert.rejects(layout({ ...exampleGraph(), kind }), TypeError);
      });
    }
  }
});

test('replacement engine with complete finite model metadata remains interchangeable', async () => {
  for (const kind of ['petri_net', 'ocpn']) {
    const graph = deepFreeze(modelGraph(kind));
    const result = await PIXLayout.createElkLayout(replacementEngine(() => {}))(graph);
    assert.equal(result.children.length, graph.nodes.length);
    assert.equal(result.edges.length, graph.edges.length);
  }
});

test('replacement model geometry must preserve valid visible model shapes', async t => {
  const malformed = [
    ['missing shape', node => { delete node.shape; }],
    ['wrong shape kind', node => { node.shape.kind = 'transition'; }],
    ['NaN shape x', node => { node.shape.x = NaN; }],
    ['infinite shape y', node => { node.shape.y = Infinity; }],
    ['NaN shape center', node => { node.shape.cx = NaN; }],
    ['infinite shape height', node => { node.shape.height = Infinity; }],
    ['nonpositive shape width', node => { node.shape.width = 0; }],
    ['shape outside node horizontally', node => { node.shape.x = node.width; }],
    ['shape outside node vertically', node => { node.shape.y = node.height; }],
    ['missing place radius', node => { delete node.shape.radius; }],
    ['NaN place radius', node => { node.shape.radius = NaN; }],
    ['infinite place radius', node => { node.shape.radius = Infinity; }],
    ['radius inconsistent with circle size', node => { node.shape.radius /= 2; }],
    ['circle center outside its shape', node => { node.shape.cx += node.shape.width; }],
  ];
  for (const [name, mutateNode] of malformed) {
    await t.test(name, async () => {
      const engine = replacementEngine(graph => mutateNode(graph.children.find(node => node.id === 'p0')));
      await assert.rejects(PIXLayout.createElkLayout(engine)(modelGraph('ocpn')), TypeError);
    });
  }
  await t.test('silent bar cannot become a visible transition', async () => {
    const engine = replacementEngine(graph => { graph.children.find(node => node.id === 'tau').shape.kind = 'transition'; });
    await assert.rejects(PIXLayout.createElkLayout(engine)(modelGraph()), TypeError);
  });
});

test('replacement model must retain textual meaning and finite label positions', async t => {
  const malformed = [
    ['p0', 'omitted label lines', node => { delete node.labelLines; }],
    ['p0', 'nonarray label lines', node => { node.labelLines = 'Available'; }],
    ['p0', 'nonstrings in label lines', node => { node.labelLines = [1]; }],
    ['t1', 'changed visible activity', node => { node.labelLines = ['Ship']; }],
    ['t1', 'omitted label position', node => { delete node.labelY; }],
    ['t1', 'NaN label position', node => { node.labelY = NaN; }],
    ['tau', 'infinite label position', node => { node.labelY = Infinity; }],
    ['p0', 'omitted place type lines', node => { delete node.typeLabelLines; }],
    ['tau', 'omitted silent type lines', node => { delete node.typeLabelLines; }],
    ['p0', 'nonstrings in type lines', node => { node.typeLabelLines = [null]; }],
    ['p0', 'infinite type label position', node => { node.typeLabelY = Infinity; }],
    ['tau', 'omitted type label position', node => { delete node.typeLabelY; }],
    ['p0', 'omitted marking position', node => { delete node.markingY; }],
    ['tau', 'NaN marking position', node => { node.markingY = NaN; }],
  ];
  for (const [id, name, mutateNode] of malformed) {
    await t.test(name, async () => {
      const engine = replacementEngine(graph => mutateNode(graph.children.find(node => node.id === id)));
      await assert.rejects(PIXLayout.createElkLayout(engine)(modelGraph('ocpn')), TypeError);
    });
  }
});
