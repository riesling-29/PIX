/* PIX view geometry. ELK owns placement; this module owns display contracts. */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PIXLayout = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const COUNT_UNITS = Object.freeze(["event_pairs", "unique_objects", "occurrences"]);
  const compareId = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;

  function typeColor(type) {
    if (typeof type !== "string") throw new TypeError("Object type must be a string");
    let hash = 2166136261;
    for (const point of type) {
      hash ^= point.codePointAt(0);
      hash = Math.imul(hash, 16777619) >>> 0;
    }
    // The type, never its current position in a filtered list, determines color.
    return `hsl(${hash % 360}, 58%, 36%)`;
  }

  function wrapLabel(text, max = 26, maxLines = 4) {
    if (typeof text !== "string") throw new TypeError("Label must be a string");
    if (!Number.isSafeInteger(max) || max < 1 || !Number.isSafeInteger(maxLines) || maxLines < 1) {
      throw new RangeError("Label limits must be positive safe integers");
    }
    const lines = [];
    for (const paragraph of text.replace(/\r\n?/g, "\n").split("\n")) {
      let remaining = Array.from(paragraph.trim());
      if (!remaining.length) lines.push("");
      while (remaining.length) {
        if (remaining.length <= max) {
          lines.push(remaining.join(""));
          break;
        }
        let split = max;
        for (let i = max; i > 0; i--) {
          if (/\s/u.test(remaining[i])) {
            split = i;
            break;
          }
        }
        lines.push(remaining.slice(0, split).join("").trimEnd());
        remaining = remaining.slice(split);
        while (remaining.length && /\s/u.test(remaining[0])) remaining.shift();
        if (lines.length > maxLines) break;
      }
      if (lines.length > maxLines) break;
    }
    if (lines.length <= maxLines) return lines;
    const truncated = lines.slice(0, maxLines);
    truncated[maxLines - 1] = Array.from(truncated[maxLines - 1]).slice(0, max - 1).join("").trimEnd() + "…";
    return truncated;
  }

  function edgeCount(edge, unit) {
    if (!COUNT_UNITS.includes(unit)) throw new RangeError(`Unknown count unit: ${String(unit)}`);
    const count = edge && edge.counts && edge.counts[unit];
    if (!Number.isSafeInteger(count) || count < 0) throw new TypeError(`Invalid ${unit} count`);
    return count;
  }

  function modelEdgeLabel(edge, graphKind) {
    if (!edge || (graphKind !== "petri_net" && graphKind !== "ocpn")) {
      throw new TypeError("A Petri net or OCPN model edge is required");
    }
    if (!Number.isSafeInteger(edge.weight) || edge.weight < 1) {
      throw new TypeError("Arc weight must be a positive safe integer");
    }
    if (graphKind === "petri_net") return edge.weight === 1 ? "" : `weight ${edge.weight}`;
    if (edge.weight !== 1) throw new TypeError("OCPN object cardinality is expressed by bounds, not Petri net arc weight");
    if (typeof edge.object_type !== "string" || typeof edge.variable !== "boolean") {
      throw new TypeError("OCPN arcs require an object type and explicit variability");
    }
    if (!Number.isSafeInteger(edge.min_objects) || edge.min_objects < 0 ||
        (edge.max_objects !== null && (!Number.isSafeInteger(edge.max_objects) || edge.max_objects < edge.min_objects))) {
      throw new TypeError("Object cardinality bounds must be ordered nonnegative safe integers or an unbounded maximum");
    }
    if (!edge.variable && (edge.min_objects !== 1 || edge.max_objects !== 1)) {
      throw new TypeError("A fixed OCPN arc must bind exactly one object");
    }
    const cardinality = edge.variable ? `[${edge.min_objects},${edge.max_objects === null ? "∞" : edge.max_objects}] objects` : "1 object";
    return `${edge.object_type}\n${cardinality}`;
  }

  function visibleEdges(graph, hiddenTypes = []) {
    if (!graph || !Array.isArray(graph.edges)) throw new TypeError("Graph edges must be an array");
    if (!Array.isArray(hiddenTypes) && !(hiddenTypes instanceof Set)) {
      throw new TypeError("Hidden types must be an array or Set");
    }
    const hidden = new Set(hiddenTypes);
    return graph.edges.filter(edge => !hidden.has(edge.object_type));
  }

  function textWidth(text, fontSize) {
    // A conservative estimate reserves space before browser font measurement.
    // Full-width glyphs and emoji must not use an ASCII-only character width.
    return Array.from(text).reduce((width, char) => {
      const point = char.codePointAt(0);
      return width + (point >= 0x2e80 ? fontSize : fontSize * 0.62);
    }, 0);
  }

  function assertId(value, label) {
    if (typeof value !== "string" || !value.length) throw new TypeError(`${label} must be a nonempty string`);
  }

  function modelNodeGeometry(node, sideDegree = 0) {
    if (!["place", "transition", "silent"].includes(node.kind)) throw new TypeError("Unknown model node kind");
    if (node.object_type !== null && typeof node.object_type !== "string") throw new TypeError("Model node object type must be a string or null");
    for (const value of [node.initial_count, node.final_count]) {
      if (!Number.isSafeInteger(value) || value < 0) throw new TypeError("Marking counts must be nonnegative safe integers");
    }
    const labelLines = wrapLabel(node.label, 26, 4);
    const labelWidth = Math.max(...labelLines.map(line => textWidth(line, 14)));
    if (node.kind === "transition") {
      const width = Math.max(130, labelWidth + 32);
      const height = Math.max(52, labelLines.length * 17 + 28, (sideDegree + 1) * 14);
      return { width, height, labelLines, labelY: (height - (labelLines.length - 1) * 17) / 2 + 4,
        shape: { kind: node.kind, x: 0, y: 0, width, height, cx: width / 2, cy: height / 2 } };
    }
    const radius = Math.max(24, (sideDegree + 1) * 5);
    const shapeWidth = node.kind === "place" ? radius * 2 : 18;
    const shapeHeight = node.kind === "place" ? radius * 2 : Math.max(48, (sideDegree + 1) * 14);
    const typeLabelLines = node.kind === "place" && node.object_type !== null ? wrapLabel(node.object_type, 22, 2) : [];
    const typeWidth = Math.max(0, ...typeLabelLines.map(line => textWidth(line, 11)));
    const markingWidth = node.kind === "place" ? textWidth(`I ${node.initial_count} / F ${node.final_count}`, 11) : 0;
    const width = Math.max(node.kind === "place" ? 96 : 56, shapeWidth + 16, labelWidth + 24, typeWidth + 24, markingWidth + 24);
    const labelY = shapeHeight + 26;
    const typeLabelY = labelY + labelLines.length * 17;
    const markingY = typeLabelY + typeLabelLines.length * 15 + 4;
    const height = node.kind === "place" ? markingY + 18 : typeLabelY + 8;
    return { width, height, labelLines, labelY, typeLabelLines, typeLabelY, markingY,
      shape: { kind: node.kind, x: (width - shapeWidth) / 2, y: 6, width: shapeWidth, height: shapeHeight,
        cx: width / 2, cy: shapeHeight / 2 + 6, ...(node.kind === "place" ? { radius } : {}) } };
  }

  function placeModelPorts(child) {
    const { shape } = child;
    for (const side of ["EAST", "WEST"]) {
      const ports = child.ports.filter(port => port.layoutOptions["elk.port.side"] === side);
      ports.forEach((port, index) => {
        const proportion = (index + 1) / (ports.length + 1);
        let x, y;
        if (shape.kind === "place") {
          const angle = (proportion - 0.5) * 2 * Math.PI / 3;
          x = shape.cx + (side === "EAST" ? 1 : -1) * shape.radius * Math.cos(angle);
          y = shape.cy + shape.radius * Math.sin(angle);
        } else {
          x = side === "EAST" ? shape.x + shape.width : shape.x;
          y = shape.y + shape.height * proportion;
        }
        port.x = x; port.y = y; port.width = 0; port.height = 0;
        // FIXED_POS alone still snaps ELK ports to the outer label bounds.
        // A negative border offset places the route on the actual shape.
        port.layoutOptions["elk.port.borderOffset"] = String(side === "EAST" ? x - child.width : -x);
      });
    }
  }

  function toElkGraph(graph) {
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new TypeError("Graph must contain node and edge arrays");
    }
    const isModel = graph.kind === "petri_net" || graph.kind === "ocpn";
    if (isModel) {
      // JSON serialization maps Infinity to null. Validate before cloning so an
      // invalid finite bound can never be reinterpreted as an unbounded arc.
      graph.edges.forEach(edge => modelEdgeLabel(edge, graph.kind));
      graph.nodes.forEach(node => modelNodeGeometry(node));
    }
    // ELK mutates layout inputs. Clone evidence as well as geometry fields.
    const snapshot = JSON.parse(JSON.stringify(graph));
    const nodes = [...snapshot.nodes].sort(compareId);
    const edges = [...snapshot.edges].sort(compareId);
    const usedIds = new Set();
    for (const item of [...nodes, ...edges]) {
      assertId(item.id, "Graph element ID");
      if (usedIds.has(item.id)) throw new TypeError(`Duplicate graph element ID: ${item.id}`);
      usedIds.add(item.id);
    }
    const uniqueId = preferred => {
      let id = preferred;
      while (usedIds.has(id)) id = "_" + id;
      usedIds.add(id);
      return id;
    };
    const children = nodes.map(node => {
      if (typeof node.label !== "string") throw new TypeError("Node label must be a string");
      const labelLines = wrapLabel(node.label);
      return {
        id: node.id,
        width: Math.max(156, ...labelLines.map(line => textWidth(line, 14) + 36)),
        height: Math.max(78, labelLines.length * 19 + 44),
        labelLines,
        data: node,
        ...(isModel ? modelNodeGeometry(node) : {}),
        layoutOptions: { "elk.portConstraints": isModel ? "FIXED_POS" : "FIXED_ORDER" },
        ports: [],
      };
    });
    const nodeById = new Map(children.map(node => [node.id, node]));
    const elkEdges = edges.map(edge => {
      const source = nodeById.get(edge.source);
      const target = nodeById.get(edge.target);
      if (!source || !target) throw new TypeError(`Unknown endpoint on edge: ${edge.id}`);
      if (!isModel && typeof edge.object_type !== "string") throw new TypeError("Edge object type must be a string");
      const counts = isModel ? [] : COUNT_UNITS.map(unit => edgeCount(edge, unit));
      const sourcePort = uniqueId(`__pix_port_${edge.id}_source`);
      const targetPort = uniqueId(`__pix_port_${edge.id}_target`);
      source.ports.push({ id: sourcePort, width: 1, height: 1, layoutOptions: { "elk.port.side": "EAST" } });
      target.ports.push({ id: targetPort, width: 1, height: 1, layoutOptions: { "elk.port.side": "WEST" } });
      const semanticLabel = isModel ? modelEdgeLabel(edge, snapshot.kind) : null;
      const labelLines = !isModel ? wrapLabel(edge.object_type, 22, 2) :
        snapshot.kind === "ocpn" ? [...wrapLabel(edge.object_type, 22, 2), semanticLabel.slice(semanticLabel.lastIndexOf("\n") + 1)] :
        semanticLabel ? [semanticLabel] : [];
      // Reserve the largest selectable count, so changing units never relayouts.
      const displayLines = isModel ? labelLines : [...labelLines, `${Math.max(...counts)} unique objects`];
      const width = Math.max(56, ...displayLines.map(line => textWidth(line, 11) + 16));
      return {
        id: edge.id,
        sources: [sourcePort],
        targets: [targetPort],
        labelLines,
        ...(isModel ? { semanticLabel } : {}),
        data: edge,
        labels: displayLines.length ? [{
          id: uniqueId(`__pix_label_${edge.id}`),
          text: displayLines.join("\n"),
          width,
          height: displayLines.length * 15 + 8,
          layoutOptions: { "elk.edgeLabels.placement": "CENTER" },
        }] : [],
      };
    });
    for (const child of children) {
      child.ports.sort(compareId);
      child.ports.forEach((port, index) => { port.layoutOptions["elk.port.index"] = String(index); });
      // Distinct ports remain legible even for high-degree activities.
      const east = child.ports.filter(port => port.layoutOptions["elk.port.side"] === "EAST").length;
      const west = child.ports.length - east;
      if (isModel) {
        Object.assign(child, modelNodeGeometry(child.data, Math.max(east, west)));
        placeModelPorts(child);
      } else child.height = Math.max(child.height, (Math.max(east, west) + 1) * 14);
    }
    return {
      id: uniqueId("__pix_root__"),
      layoutOptions: {
        "elk.algorithm": "layered",
        "elk.direction": "RIGHT",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.randomSeed": "1",
        "elk.spacing.nodeNode": "54",
        "elk.spacing.edgeNode": "28",
        "elk.spacing.edgeEdge": "20",
        "elk.layered.spacing.nodeNodeBetweenLayers": "110",
        "elk.layered.spacing.edgeNodeBetweenLayers": "30",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "24",
        "elk.layered.mergeEdges": "false",
        "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES",
        "elk.padding": "[top=36,left=36,bottom=36,right=36]",
      },
      children,
      edges: elkEdges,
    };
  }

  function sectionPath(edge) {
    if (!edge || edge.sections === undefined) return "";
    if (!Array.isArray(edge.sections)) throw new TypeError("Edge sections must be an array");
    const pointText = point => {
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y)) {
        throw new TypeError("Edge geometry must have finite coordinates");
      }
      return `${point.x},${point.y}`;
    };
    return edge.sections.map(section => {
      if (!section || (section.bendPoints !== undefined && !Array.isArray(section.bendPoints))) {
        throw new TypeError("Invalid edge section");
      }
      return `M${pointText(section.startPoint)}` + [...(section.bendPoints || []), section.endPoint].map(point => ` L${pointText(point)}`).join("");
    }).join(" ");
  }

  function createElkLayout(engine) {
    if (!engine || typeof engine.layout !== "function") throw new TypeError("ELK engine must provide layout(graph)");
    return async function layout(graph) {
      const input = toElkGraph(graph);
      if (!input.children.length) return { ...input, width: 320, height: 180 };
      const isModel = graph.kind === "petri_net" || graph.kind === "ocpn";
      // Layout engines may mutate their argument. Keep independent contracts
      // for metadata and label boxes the renderer needs after layout.
      const expectedNodes = new Map(input.children.map(node => [node.id, {
        kind: node.shape?.kind,
        labelLines: [...node.labelLines],
        typeLabelLines: node.typeLabelLines && [...node.typeLabelLines],
      }]));
      const expectedEdges = new Map(input.edges.map(edge => [edge.id, {
        labels: edge.labels.map(label => ({ id: label.id, text: label.text })),
        labelLines: [...edge.labelLines],
        semanticLabel: edge.semanticLabel,
      }]));
      const result = await engine.layout(input);
      if (!result || !Number.isFinite(result.width) || !Number.isFinite(result.height) || result.width < 0 || result.height < 0) {
        throw new TypeError("Layout engine returned invalid graph dimensions");
      }
      const hasSameIds = (actual, expected) => {
        if (!Array.isArray(actual) || actual.length !== expected.length) return false;
        const ids = new Set(expected.map(item => item.id));
        return actual.every(item => item && ids.delete(item.id)) && ids.size === 0;
      };
      if (!hasSameIds(result.children, graph.nodes) || !hasSameIds(result.edges, graph.edges)) {
        throw new TypeError("Layout engine must preserve every node and edge");
      }
      const sameLines = (actual, expected) => Array.isArray(actual) && Array.isArray(expected) &&
        actual.length === expected.length && actual.every((line, index) => typeof line === "string" && line === expected[index]);
      const near = (actual, expected) => Math.abs(actual - expected) <= 1e-6;
      for (const child of result.children) {
        if (![child.x, child.y, child.width, child.height].every(Number.isFinite) || child.width <= 0 || child.height <= 0) {
          throw new TypeError("Layout engine returned invalid node geometry");
        }
        if (isModel) {
          const expected = expectedNodes.get(child.id);
          const shape = child.shape;
          if (!shape || shape.kind !== expected.kind ||
              ![shape.x, shape.y, shape.width, shape.height, shape.cx, shape.cy].every(Number.isFinite) ||
              shape.x < 0 || shape.y < 0 || shape.width <= 0 || shape.height <= 0 ||
              shape.x + shape.width > child.width + 1e-6 || shape.y + shape.height > child.height + 1e-6 ||
              !near(shape.cx, shape.x + shape.width / 2) || !near(shape.cy, shape.y + shape.height / 2)) {
            throw new TypeError("Layout engine returned invalid model shape geometry");
          }
          if (shape.kind === "place" && (!Number.isFinite(shape.radius) || shape.radius <= 0 ||
              !near(shape.width, shape.radius * 2) || !near(shape.height, shape.radius * 2))) {
            throw new TypeError("Layout engine returned invalid place circle geometry");
          }
          if (!sameLines(child.labelLines, expected.labelLines) || !Number.isFinite(child.labelY) ||
              child.labelY < 0 || child.labelY + (child.labelLines.length - 1) * 17 > child.height + 1e-6) {
            throw new TypeError("Layout engine must preserve model labels and their finite positions");
          }
          if (shape.kind !== "transition" && (!sameLines(child.typeLabelLines, expected.typeLabelLines) ||
              ![child.typeLabelY, child.markingY].every(Number.isFinite) ||
              child.typeLabelY < 0 || child.markingY < 0 || child.markingY > child.height ||
              child.typeLabelY + Math.max(0, child.typeLabelLines.length - 1) * 15 > child.height + 1e-6)) {
            throw new TypeError("Layout engine must preserve type labels and marking positions");
          }
        }
      }
      for (const edge of result.edges) {
        if (!sectionPath(edge)) throw new TypeError("Layout engine returned an edge without a route");
        const expected = expectedEdges.get(edge.id);
        const labels = edge.labels === undefined && expected.labels.length === 0 ? [] : edge.labels;
        if (!hasSameIds(labels, expected.labels)) {
          throw new TypeError("Layout engine must preserve required edge labels");
        }
        const expectedLabels = new Map(expected.labels.map(label => [label.id, label]));
        for (const label of labels) {
          if (![label.x, label.y, label.width, label.height].every(Number.isFinite) ||
              label.width <= 0 || label.height <= 0 || label.text !== expectedLabels.get(label.id).text) {
            throw new TypeError("Layout engine returned invalid edge label geometry or text");
          }
        }
        if (isModel && (!sameLines(edge.labelLines, expected.labelLines) || edge.semanticLabel !== expected.semanticLabel)) {
          throw new TypeError("Layout engine must preserve model arc semantics");
        }
      }
      return result;
    };
  }

  return Object.freeze({ typeColor, wrapLabel, toElkGraph, createElkLayout, visibleEdges, edgeCount, modelEdgeLabel, sectionPath });
});
