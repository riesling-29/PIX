/* Graphviz placement for PIX's evidence-rich OCDFG and Petri-net viewer. */
(function (root, factory) {
  "use strict";
  if (typeof module === "object" && module.exports) module.exports = factory(require("./layout.js"));
  else root.PIXLegacyGraphviz = factory(root.PIXLayout);
})(typeof globalThis !== "undefined" ? globalThis : this, function (L) {
  "use strict";

  function point(value) {
    if (!value || !Number.isFinite(value.x) || !Number.isFinite(value.y)) {
      throw new TypeError("Graphviz spline coordinates must be finite");
    }
    return { x: value.x, y: value.y };
  }

  // Graphviz reserves the complete node box, including the model's external
  // labels. Route terminals must touch the actual circle/bar/rectangle instead
  // of that invisible reservation box. Translating the adjacent control point
  // preserves the spline's terminal tangent.
  function attachToShape(points, position, start, arrow) {
    if (!position.shape) return;
    const shape = position.shape;
    const center = { x: position.x + shape.cx, y: position.y + shape.cy };
    const index = start ? 0 : points.length - 1;
    const control = start ? 1 : points.length - 2;
    const old = points[index];
    // Graphviz ends the spline at the arrow's base. Use its tip for clipping,
    // then move both polygon and spline together so the arrow keeps its size.
    const boxCenter = { x: position.x + position.width / 2, y: position.y + position.height / 2 };
    const anchor = arrow.length ? arrow.reduce((nearest, candidate) =>
      Math.hypot(candidate.x - boxCenter.x, candidate.y - boxCenter.y) <
      Math.hypot(nearest.x - boxCenter.x, nearest.y - boxCenter.y) ? candidate : nearest) : old;
    let dx = anchor.x - center.x, dy = anchor.y - center.y;
    if (!dx && !dy) { dx = points[control].x - center.x; dy = points[control].y - center.y; }
    if (!dx && !dy) dx = start ? 1 : -1;
    const scale = shape.kind === "place" ? shape.radius / Math.hypot(dx, dy) :
      1 / Math.max(Math.abs(dx) / (shape.width / 2), Math.abs(dy) / (shape.height / 2));
    const delta = { x: center.x + dx * scale - anchor.x, y: center.y + dy * scale - anchor.y };
    points[control] = { x: points[control].x + delta.x, y: points[control].y + delta.y };
    points[index] = { x: old.x + delta.x, y: old.y + delta.y };
    arrow.forEach(vertex => { vertex.x += delta.x; vertex.y += delta.y; });
  }

  function sectionsFor(edge, source, target) {
    if (!edge || !Array.isArray(edge.splines) || !edge.splines.length) {
      throw new TypeError("Graphviz must return at least one spline for every edge");
    }
    const arrowhead = (edge.arrowhead || []).map(point), arrowtail = (edge.arrowtail || []).map(point);
    for (const arrow of [arrowhead, arrowtail]) {
      if (arrow.length && arrow.length < 3) throw new TypeError("Graphviz arrow polygons require at least three vertices");
    }
    const sections = edge.splines.map((spline, index) => {
      if (!spline || !Array.isArray(spline.points) || spline.points.length < 4 || (spline.points.length - 1) % 3) {
        throw new TypeError("Graphviz splines must contain cubic control-point triples");
      }
      const points = spline.points.map(point);
      if (index === 0) attachToShape(points, source, true, arrowtail);
      if (index === edge.splines.length - 1) attachToShape(points, target, false, arrowhead);
      const cubicBezier = [];
      for (let offset = 1; offset < points.length; offset += 3) {
        cubicBezier.push({ controlPoint1: points[offset], controlPoint2: points[offset + 1], endPoint: points[offset + 2] });
      }
      return { startPoint: points[0], endPoint: points.at(-1), cubicBezier };
    });
    return { sections, arrowhead, arrowtail };
  }

  function uniqueMap(items, label) {
    if (!Array.isArray(items)) throw new TypeError(`Graphviz ${label} must be an array`);
    const result = new Map();
    for (const item of items) {
      if (!item || typeof item.id !== "string" || result.has(item.id)) throw new TypeError(`Graphviz returned invalid or duplicate ${label} IDs`);
      result.set(item.id, item);
    }
    return result;
  }

  function createGraphvizLayout(engine) {
    if (!L || typeof L.createElkLayout !== "function") throw new TypeError("PIX layout contracts are required");
    if (!engine || typeof engine.layout !== "function") throw new TypeError("Graphviz geometry engine must provide layout(graph, options)");
    // Reuse the existing result validator, including exact model labels,
    // cardinalities, dimensions and node/edge completeness checks.
    return L.createElkLayout({ layout: async prepared => {
      const input = {
        nodes: prepared.children.map(child => ({ id: child.id, label: child.labelLines.join("\n"), kind: "activity" })),
        edges: prepared.edges.map(edge => ({
          id: edge.id, source: edge.data.source, target: edge.data.target,
          label: edge.labels[0]?.text || "", directed: true,
          ...(edge.labels.length ? { labelSize: { width: edge.labels[0].width, height: edge.labels[0].height } } : {}),
        })),
      };
      const nodeSizes = new Map(prepared.children.map(child => [child.id, { width: child.width, height: child.height }]));
      const result = await engine.layout(input, { direction: "LR", nodeSizes });
      if (!result || !Number.isFinite(result.width) || !Number.isFinite(result.height) || result.width < 0 || result.height < 0) {
        throw new TypeError("Graphviz returned invalid graph dimensions");
      }
      const geometryNodes = uniqueMap(result.nodes, "nodes"), geometryEdges = uniqueMap(result.edges, "edges");
      if (geometryNodes.size !== prepared.children.length || geometryEdges.size !== prepared.edges.length) {
        throw new TypeError("Graphviz must preserve every node and edge");
      }
      const children = prepared.children.map(child => {
        const geometry = geometryNodes.get(child.id);
        if (!geometry || ![geometry.x, geometry.y, geometry.width, geometry.height].every(Number.isFinite) ||
            Math.abs(geometry.width - child.width) > 0.01 || Math.abs(geometry.height - child.height) > 0.01) {
          throw new TypeError("Graphviz must preserve the reserved node dimensions");
        }
        return { ...child, x: geometry.x, y: geometry.y };
      });
      const byId = new Map(children.map(child => [child.id, child]));
      const edges = prepared.edges.map(edge => {
        const geometry = geometryEdges.get(edge.id);
        if (!geometry) throw new TypeError("Graphviz must preserve every edge ID");
        const labels = edge.labels.map(label => {
          const center = point(geometry.labelPosition);
          return { ...label, x: center.x - label.width / 2, y: center.y - label.height / 2 };
        });
        return { ...edge, labels, ...sectionsFor(geometry, byId.get(edge.data.source), byId.get(edge.data.target)) };
      });
      return { ...prepared, children, edges, width: result.width, height: result.height,
        layoutEngine: "graphviz", layoutEngineVersion: result.engineVersion };
    } });
  }

  return Object.freeze({ createGraphvizLayout });
});
