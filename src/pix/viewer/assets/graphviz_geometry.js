/* PIX Graphviz geometry bridge. Pinned Viz.js contains Graphviz WebAssembly.
 * Graphviz owns placement, cubic splines, arrow polygons and edge label centers.
 * Original IDs/text never enter DOT or HTML: only generated IDs and numeric
 * label reservations cross the bridge. PIX renders the original domain data.
 */
(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PIXGraphvizGeometry = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (root) {
  "use strict";
  const padding = 28;
  const compare = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  let instancePromise;

  function text(value, name) {
    if (typeof value !== "string") throw new TypeError(`${name} must be a string`);
    // A lone surrogate cannot round-trip through the UTF-8 Graphviz boundary.
    // Reject it even though labels remain on the PIX side of that boundary.
    for (let i = 0; i < value.length; i++) {
      const unit = value.charCodeAt(i);
      if (unit >= 0xd800 && unit <= 0xdbff) {
        const next = value.charCodeAt(++i);
        if (!(next >= 0xdc00 && next <= 0xdfff)) throw new TypeError(`${name} contains an unpaired surrogate`);
      } else if (unit >= 0xdc00 && unit <= 0xdfff) throw new TypeError(`${name} contains an unpaired surrogate`);
    }
    return value;
  }
  const displayed = value => value.replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/gu,
    c => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`);
  const measure = (value, size) => Array.from(value).reduce((sum, character) =>
    sum + (character.codePointAt(0) >= 0x2e80 ? size : size * 0.67), 0);

  function wrapped(value) {
    const native = root.PIXNativeGeometry;
    if (native && typeof native.wrapLabel === "function") return native.wrapLabel(value, 28, 3);
    const lines = [];
    for (const paragraph of value.replace(/\r\n?/g, "\n").split("\n")) {
      const points = Array.from(paragraph);
      if (!points.length) lines.push("");
      for (let i = 0; i < points.length; i += 28) lines.push(points.slice(i, i + 28).join(""));
    }
    return lines.slice(0, 3);
  }
  function positive(value, name) {
    if (typeof value !== "number" || !Number.isFinite(value) || value <= 0 || value > 1000000) {
      throw new RangeError(`${name} must be finite, positive and at most 1000000`);
    }
    return value;
  }
  function size(value, name) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new TypeError(`${name} must contain width and height`);
    return {width: positive(value.width, `${name}.width`), height: positive(value.height, `${name}.height`)};
  }
  function nodeSize(node, sizes) {
    const supplied = sizes instanceof Map ? sizes.get(node.id) : sizes && Object.hasOwn(sizes, node.id) ? sizes[node.id] : undefined;
    if (supplied !== undefined) return size(supplied, "nodeSizes entry");
    if (node.width !== undefined || node.height !== undefined) return size(node, "node");
    if (node.kind === "silent") return {width: 22, height: 54};
    const lines = wrapped(displayed(node.label));
    const metrics = (node.metrics || []).slice(0, 2);
    const metricWidth = Math.max(0, ...metrics.map(metric => measure(`${metric.name}: ${metric.value === null ? "unknown" : metric.value}`, 10)));
    let width = Math.max(112, ...lines.map(line => measure(line, 12) + 36), metricWidth + 30);
    let height = Math.max(58, lines.length * 16 + metrics.length * 13 + 24);
    if (["place", "state", "operator"].includes(node.kind)) { width *= 1.25; height *= 1.2; }
    if (["gateway", "decision"].includes(node.kind)) { width *= 1.7; height *= 1.7; }
    return {width, height};
  }
  function edgeLabel(edge) {
    if (edge.label) return text(edge.label, "edge label");
    const metric = (edge.metrics || [])[0];
    if (!metric) return "";
    return `${metric.name}: ${metric.value === null ? "unknown" : metric.value}${metric.unit ? ` ${metric.unit}` : ""}`;
  }
  function labelSize(edge) {
    const value = displayed(edgeLabel(edge));
    if (!value && edge.labelSize === undefined) return null;
    const lines = value.replace(/\r\n?/g, "\n").split("\n");
    const measured = {width: Math.max(1, ...lines.map(line => measure(line, 10) + 12)), height: Math.max(18, lines.length * 14 + 4)};
    if (edge.labelSize === undefined) return measured;
    const supplied = size(edge.labelSize, "edge.labelSize");
    return {width: Math.max(measured.width, supplied.width), height: Math.max(measured.height, supplied.height)};
  }
  function validate(graph, options) {
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new TypeError("Graph nodes and edges must be arrays");
    if (!options || typeof options !== "object" || Array.isArray(options)) throw new TypeError("Options must be an object");
    const direction = options.direction === undefined ? "LR" : options.direction;
    if (!["LR", "TB"].includes(direction)) throw new RangeError("Direction must be LR or TB");
    if (options.nodeSizes !== undefined && (!(options.nodeSizes instanceof Map) &&
      (!options.nodeSizes || typeof options.nodeSizes !== "object" || Array.isArray(options.nodeSizes)))) throw new TypeError("nodeSizes must be a Map or object");
    const nodes = [...graph.nodes].sort(compare), edges = [...graph.edges].sort(compare), ids = new Set(), edgeIds = new Set();
    for (const node of nodes) {
      if (!node || typeof node !== "object") throw new TypeError("Node must be an object");
      if (!text(node.id, "Node ID") || ids.has(node.id)) throw new TypeError("Node IDs must be unique and nonempty");
      ids.add(node.id); text(node.label, "Node label");
      if (node.metrics !== undefined && !Array.isArray(node.metrics)) throw new TypeError("Node metrics must be an array");
    }
    for (const edge of edges) {
      if (!edge || typeof edge !== "object") throw new TypeError("Edge must be an object");
      if (!text(edge.id, "Edge ID") || edgeIds.has(edge.id)) throw new TypeError("Edge IDs must be unique and nonempty");
      edgeIds.add(edge.id);
      if (!ids.has(edge.source) || !ids.has(edge.target)) throw new TypeError("Edge references an unknown node");
      if (edge.label !== undefined) text(edge.label, "Edge label");
      if (edge.directed !== undefined && typeof edge.directed !== "boolean") throw new TypeError("Edge directed must be boolean");
      if (edge.metrics !== undefined && !Array.isArray(edge.metrics)) throw new TypeError("Edge metrics must be an array");
    }
    return {nodes, edges, direction};
  }
  async function instance(injected) {
    if (injected !== undefined) {
      if (!injected || typeof injected.render !== "function") throw new TypeError("viz must be a Graphviz instance with render()");
      return injected;
    }
    if (!instancePromise) {
      const library = root.Viz || (typeof require === "function" ? require("./vendor/viz-global.js") : null);
      if (!library || typeof library.instance !== "function") throw new Error("Graphviz WebAssembly is unavailable. Load the bundled Viz.js before the PIX viewer.");
      instancePromise = Promise.resolve().then(() => library.instance()).catch(error => { instancePromise = null; throw error; });
    }
    return instancePromise;
  }
  function coordinate(value, name) {
    if (!Array.isArray(value) || value.length !== 2 || !value.every(Number.isFinite)) throw new Error(`Graphviz returned invalid ${name}`);
    return {x: value[0], y: value[1]};
  }
  function pair(value, name) {
    if (typeof value !== "string") throw new Error(`Graphviz omitted ${name}`);
    return coordinate(value.split(",").map(Number), name);
  }
  function polygons(operations, name) {
    return (operations || []).filter(op => op.op === "P" || op.op === "p")
      .flatMap(op => op.points.map(point => coordinate(point, name)));
  }

  async function layout(graph, options = {}) {
    const input = validate(graph, options);
    const sizes = input.nodes.map(node => nodeSize(node, options.nodeSizes));
    const labels = input.edges.map(labelSize);
    const viz = await instance(options.viz);
    const nameToOriginal = new Map(input.nodes.map((node, index) => [`n${index}`, node]));
    const originalToName = new Map(input.nodes.map((node, index) => [node.id, `n${index}`]));
    const request = {name: "pix", directed: true, strict: false,
      graphAttributes: {rankdir: input.direction, splines: "spline", nodesep: 0.48, ranksep: 0.8, concentrate: false, outputorder: "edgesfirst"},
      nodeAttributes: {label: "", fixedsize: true, margin: 0},
      edgeAttributes: {fontname: "Arial", fontsize: 10, arrowsize: 0.8},
      nodes: input.nodes.map((node, index) => ({name: `n${index}`, attributes: {
        id: `n${index}`, label: "", width: sizes[index].width / 72, height: sizes[index].height / 72,
        shape: ["place", "state", "operator"].includes(node.kind) ? "ellipse" : ["gateway", "decision"].includes(node.kind) ? "diamond" : "box"
      }})),
      edges: input.edges.map((edge, index) => ({tail: originalToName.get(edge.source), head: originalToName.get(edge.target), attributes: {
        id: `e${index}`, dir: edge.directed === false ? "none" : "forward",
        label: labels[index] ? {html: `<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0" CELLPADDING="0"><TR><TD WIDTH="${Math.ceil(labels[index].width)}" HEIGHT="${Math.ceil(labels[index].height)}"> </TD></TR></TABLE>`} : ""
      }}))};
    const result = viz.render(request, {engine: "dot", format: "json", yInvert: true});
    if (!result || result.status !== "success" || typeof result.output !== "string") {
      const message = (result && result.errors || []).map(error => error.message).join("; ");
      throw new Error(`Graphviz layout failed${message ? `: ${message}` : ""}`);
    }
    const output = JSON.parse(result.output), outputNodes = output.objects || [], outputEdges = output.edges || [];
    if (outputNodes.length !== input.nodes.length || outputEdges.length !== input.edges.length) throw new Error("Graphviz changed the graph identity counts");
    const graphvizNodes = new Map(), seenNodes = new Set(), seenEdges = new Set();
    const nodes = outputNodes.map(node => {
      const original = nameToOriginal.get(node.name);
      if (!original || node.id !== node.name || seenNodes.has(node.name)) throw new Error("Graphviz changed a node identity");
      seenNodes.add(node.name); graphvizNodes.set(node._gvid, original.id);
      const center = pair(node.pos, "node center"), width = positive(Number(node.width) * 72, "Graphviz node width"), height = positive(Number(node.height) * 72, "Graphviz node height");
      return {id: original.id, x: center.x - width / 2, y: center.y - height / 2, width, height};
    });
    const edges = outputEdges.map(edge => {
      const match = /^e(0|[1-9]\d*)$/.exec(edge.id || ""), index = match ? Number(match[1]) : -1;
      const original = input.edges[index];
      if (!original || seenEdges.has(edge.id) || graphvizNodes.get(edge.tail) !== original.source || graphvizNodes.get(edge.head) !== original.target) throw new Error("Graphviz changed an edge identity");
      seenEdges.add(edge.id);
      const splines = (edge._draw_ || []).filter(op => op.op === "b" || op.op === "B").map(op => {
        if (!Array.isArray(op.points) || op.points.length < 4 || (op.points.length - 1) % 3) throw new Error("Graphviz returned an invalid cubic spline");
        return {points: op.points.map(point => coordinate(point, "spline point"))};
      });
      if (!splines.length) throw new Error("Graphviz omitted an edge spline");
      const points = [Object.assign({}, splines[0].points[0]), Object.assign({}, splines[splines.length - 1].points.at(-1))];
      return {id: original.id, points, splines,
        labelPosition: labels[index] ? pair(edge.lp, "edge label center") : null,
        labelSize: labels[index], arrowhead: polygons(edge._hdraw_, "arrowhead"), arrowtail: polygons(edge._tdraw_, "arrowtail")};
    });
    let minX = 0, minY = 0, maxX = 0, maxY = 0;
    const include = point => { minX = Math.min(minX, point.x); minY = Math.min(minY, point.y); maxX = Math.max(maxX, point.x); maxY = Math.max(maxY, point.y); };
    if (typeof output.bb === "string") {
      const box = output.bb.split(",").map(Number);
      if (box.length !== 4 || !box.every(Number.isFinite)) throw new Error("Graphviz returned an invalid bounding box");
      include({x: box[0], y: box[1]}); include({x: box[2], y: box[3]});
    }
    for (const node of nodes) { include(node); include({x: node.x + node.width, y: node.y + node.height}); }
    for (const edge of edges) {
      for (const spline of edge.splines) for (const point of spline.points) include(point);
      for (const point of [...edge.arrowhead, ...edge.arrowtail]) include(point);
      if (edge.labelPosition) {
        include({x: edge.labelPosition.x - edge.labelSize.width / 2, y: edge.labelPosition.y - edge.labelSize.height / 2});
        include({x: edge.labelPosition.x + edge.labelSize.width / 2, y: edge.labelPosition.y + edge.labelSize.height / 2});
      }
    }
    const dx = padding - minX, dy = padding - minY;
    const translate = point => { point.x += dx; point.y += dy; };
    nodes.forEach(translate);
    for (const edge of edges) {
      edge.points.forEach(translate); edge.splines.forEach(spline => spline.points.forEach(translate));
      edge.arrowhead.forEach(translate); edge.arrowtail.forEach(translate);
      if (edge.labelPosition) translate(edge.labelPosition);
    }
    return {engine: "graphviz", engineVersion: String(viz.graphvizVersion), layout: "dot",
      width: Math.max(2 * padding, maxX - minX + 2 * padding), height: Math.max(2 * padding, maxY - minY + 2 * padding),
      nodes: nodes.sort(compare), edges: edges.sort(compare),
      notes: (result.errors || []).map(error => `Graphviz ${error.level || "message"}: ${error.message}`)};
  }
  return Object.freeze({layout});
});
