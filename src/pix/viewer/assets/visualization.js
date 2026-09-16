/* PIX offline visualization. Source labels are text, never HTML. */
(function (root) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const KINDS = {graph: "Graph", matrix: "Matrix", chart: "Chart", timeline: "Timeline", chevron: "Chevron", table: "Table"};
  const DEFAULT_LIMITS = {graphNodes: 1500, graphEdges: 6000, matrixCells: 12000, chartPoints: 15000, timelineItems: 10000, chevronAppearances: 10000, tablePageSize: 50};
  let nextId = 0;
  const display = value => String(value).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/gu, character => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`);
  const scalar = value => value === null || value === undefined ? "Unknown" : typeof value === "boolean" ? (value ? "True" : "False") : String(value);
  const number = value => Number.isFinite(value) ? new Intl.NumberFormat("en", {maximumSignificantDigits: 6}).format(value) : "Unknown";
  const shorten = (value, length = 48) => { const chars = Array.from(display(value)); return chars.length > length ? chars.slice(0, length - 1).join("") + "…" : chars.join(""); };
  const textOf = value => typeof value === "object" && value !== null || typeof value === "string" && /[\\\u0000-\u001f\ufffe\uffff]/u.test(value) ? JSON.stringify(value) : scalar(value);
  function html(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, display(value));
    if (text !== undefined) node.textContent = display(text);
    return node;
  }
  function svgNode(tag, attrs = {}, text) {
    const node = document.createElementNS(NS, tag);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, display(value));
    if (text !== undefined) node.textContent = display(text);
    return node;
  }
  function button(label, action, attrs = {}) {
    const node = html("button", {type: "button", ...attrs}, label);
    node.addEventListener("click", action);
    return node;
  }
  function hashColor(value, lightness = 42) {
    let hash = 2166136261;
    for (const c of String(value)) hash = Math.imul(hash ^ c.codePointAt(0), 16777619);
    return `hsl(${(hash >>> 0) % 360} 43% ${lightness}%)`;
  }
  function metricText(metric) { return `${metric.name}: ${scalar(metric.value)}${metric.unit ? ` ${metric.unit}` : ""}`; }
  function extent(values, zero = false, singletonPadding = null) {
    const finite = values.filter(Number.isFinite);
    if (!finite.length) return [0, 1];
    let low = finite[0], high = finite[0];
    for (const value of finite) { low = Math.min(low, value); high = Math.max(high, value); }
    if (zero) { low = Math.min(low, 0); high = Math.max(high, 0); }
    if (low === high) { const padding = singletonPadding === null ? Math.max(Math.abs(low) * 0.05, 1) : singletonPadding; return [low - padding, high + padding]; }
    return [low, high];
  }
  function linear(domain, range) {
    const magnitude = Math.max(Math.abs(domain[0]), Math.abs(domain[1]), 1);
    const low = domain[0] / magnitude, span = domain[1] / magnitude - low;
    return value => range[0] + ((value / magnitude - low) / span) * (range[1] - range[0]);
  }
  const between = (low, high, fraction) => low * (1 - fraction) + high * fraction;
  function utcFull(seconds) { const date = new Date(seconds * 1000); return Number.isFinite(date.getTime()) ? date.toISOString() : "Outside browser date range"; }
  function timestampSeconds(value) {
    const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
    if (!match) return NaN;
    return Date.parse(match[1] + match[3]) / 1000 + (match[2] ? Number(`0.${match[2]}`) : 0);
  }
  function validateGeometry(graph, geometry) {
    if (!geometry || !Number.isFinite(geometry.width) || !Number.isFinite(geometry.height) || geometry.width <= 0 || geometry.height <= 0 || !Array.isArray(geometry.nodes) || !Array.isArray(geometry.edges)) throw new Error("Layout must return finite positive bounds, nodes, and edges.");
    const verify = (input, output, kind) => {
      const expected = new Set(input.map(item => item.id)), actual = new Set(output.map(item => item.id));
      if (expected.size !== input.length || actual.size !== output.length || expected.size !== actual.size || [...actual].some(id => !expected.has(id))) throw new Error(`Layout changed ${kind} identities.`);
    };
    verify(graph.nodes, geometry.nodes, "node"); verify(graph.edges, geometry.edges, "edge");
    for (const node of geometry.nodes) if (![node.x, node.y, node.width, node.height].every(Number.isFinite) || node.width <= 0 || node.height <= 0) throw new Error("Layout returned an invalid node box.");
    const validPoints = (points, minimum) => Array.isArray(points) && points.length >= minimum && points.every(point => point && Number.isFinite(point.x) && Number.isFinite(point.y));
    for (const edge of geometry.edges) {
      if (!validPoints(edge.points, 2)) throw new Error("Layout returned an invalid edge route.");
      if (edge.splines !== undefined && (!Array.isArray(edge.splines) || !edge.splines.length || edge.splines.some(spline => !validPoints(spline.points, 4) || (spline.points.length - 1) % 3 !== 0))) throw new Error("Layout returned invalid cubic splines.");
      if (edge.labelPosition != null && ![edge.labelPosition.x, edge.labelPosition.y].every(Number.isFinite)) throw new Error("Layout returned an invalid edge label position.");
      for (const name of ["arrowhead", "arrowtail"]) if (edge[name] !== undefined && (!Array.isArray(edge[name]) || edge[name].length && !validPoints(edge[name], 3))) throw new Error("Layout returned an invalid arrow polygon.");
    }
    return geometry;
  }
  const SVG_STYLE = `text{font-family:Inter,Segoe UI,Arial,sans-serif;fill:#293b47;font-size:12px}.pv-node-shape{fill:var(--pv-tint,#fff);stroke:var(--pv-color,#66838b);stroke-width:1.4}.pv-silent{fill:#304750;stroke:#304750}.pv-node-label{font-size:12px;font-weight:600}.pv-node-metric{font-size:10px;fill:#61747d}.pv-edge-line{fill:none;stroke:var(--pv-color,#879ba3);stroke-width:1.6;stroke-linejoin:round}.pv-edge-hit{fill:none;stroke:transparent;stroke-width:14}.pv-edge-label{font-size:10px;paint-order:stroke;stroke:#f8fafb;stroke-width:5px;stroke-linejoin:round}.pv-grid{stroke:#e4eaee;stroke-width:1}.pv-axis{stroke:#9aabb4;stroke-width:1}.pv-tick{font-size:11px;fill:#657781}.pv-axis-label{font-size:12px;font-weight:600}.pv-mark{cursor:pointer;outline:none}.pv-mark.is-selected .pv-node-shape,.pv-mark:focus-visible .pv-node-shape{stroke:#163f51;stroke-width:3}.pv-mark.is-selected .pv-edge-line,.pv-mark:focus-visible .pv-edge-line{stroke-width:4}.pv-mark.is-match{filter:drop-shadow(0 0 3px #d49524)}.pv-mark.is-selected{filter:drop-shadow(0 1px 3px #49687580)}.pv-unknown{fill:#e9edf0;stroke:#b9c6cd;stroke-dasharray:3 3}.pv-cell-label{font-size:11px}.pv-series-line{fill:none;stroke-width:2}.pv-timeline-label{fill:#fff;font-size:11px;font-weight:600}.pv-empty-svg{font-size:16px;fill:#71838c}`;

  function mount(container, sourceDocument, options = {}) {
    if (!container || typeof container.replaceChildren !== "function") throw new Error("A DOM container is required.");
    if (!sourceDocument || sourceDocument.schema !== "pix.visualization.v1" || !Array.isArray(sourceDocument.panels)) throw new Error("Expected a pix.visualization.v1 document.");
    const layoutEngine = options.layoutEngine === undefined ? "graphviz" : options.layoutEngine;
    if (!["graphviz", "native"].includes(layoutEngine)) throw new Error("Choose graphviz or explicit experimental native layout.");
    const pending = [sourceDocument];
    while (pending.length) {
      const value = pending.pop();
      if (typeof value === "bigint" || typeof value === "number" && (!Number.isFinite(value) || Number.isInteger(value) && !Number.isSafeInteger(value))) {
        const message = "This document contains a number outside the browser's supported exact numeric range. Use the original PIX result or JSON artifact; this view cannot safely display it.";
        container.replaceChildren(html("div", {class: "pv-empty pv-error", role: "alert"}, message));
        throw new RangeError(message);
      }
      if (value && typeof value === "object") for (const child of Object.values(value)) pending.push(child);
    }
    const source = structuredClone(sourceDocument);
    const ids = new Set(source.panels.map(panel => panel.id));
    if (ids.size !== source.panels.length) throw new Error("Panel identities must be unique.");
    const limits = {...DEFAULT_LIMITS, ...(options.limits || {})};
    for (const [key, value] of Object.entries(limits)) if (!Number.isSafeInteger(value) || value <= 0) throw new Error(`Display limit ${key} must be a positive integer.`);
    const instance = ++nextId;
    let disposed = false, generation = 0, current = null, currentSVG = null, marks = [], selected = null;
    let bounds = {x: 0, y: 0, width: 900, height: 550}, view = {...bounds}, pointer = null, moved = false;
    let tableQuery = null, currentNotes = [], renderPromise;
    const app = html("div", {class: "pv-app"});
    const header = html("header", {class: "pv-header"});
    const brand = html("div", {class: "pv-brand", "aria-label": "PIX"}, "PIX");
    const heading = html("div", {class: "pv-heading"});
    heading.append(html("p", {class: "pv-eyebrow"}, "PROCESS INTELLIGENCE"), html("h1", {}, source.title));
    const sourceStatus = html("span", {class: `pv-document-status pv-status-${source.status || "ok"}`}, source.status || "ok");
    header.append(brand, heading, sourceStatus);
    const navigation = html("nav", {class: "pv-tabs", "aria-label": "Visualization panels", role: "tablist"});
    const tabs = new Map();
    const toolbar = html("div", {class: "pv-toolbar"});
    const panelTitle = html("div", {class: "pv-panel-title"});
    const tools = html("div", {class: "pv-tools"});
    const search = html("input", {type: "search", placeholder: "Find labels or values…", "aria-label": "Find labels or values", class: "pv-search"});
    const searchStatus = html("span", {class: "pv-search-status", role: "status", "aria-live": "polite"});
    const fitButton = button("Fit", fit, {title: "Fit the full drawing (0)"});
    const readableButton = button("Readable", readable, {title: "Show labels at their designed size; pan to explore (1)"});
    const zoomOut = button("−", () => zoom(1.25), {title: "Zoom out (−)", "aria-label": "Zoom out"});
    const zoomIn = button("+", () => zoom(0.8), {title: "Zoom in (+)", "aria-label": "Zoom in"});
    const save = button("Save SVG", download);
    tools.append(search, searchStatus, fitButton, readableButton, zoomOut, zoomIn, save);
    toolbar.append(panelTitle, tools);
    const warning = html("div", {class: "pv-warning", role: "status"});
    if ((source.issues || []).length) warning.append(html("strong", {}, "Analysis notes"), ...source.issues.map(issue => html("p", {}, issue)));
    else warning.hidden = true;
    const main = html("div", {class: "pv-main"});
    const workspace = html("section", {class: "pv-workspace", role: "tabpanel", tabindex: "0", id: `pv-panel-${instance}`});
    const canvas = html("div", {class: "pv-canvas"});
    const inspector = html("aside", {class: "pv-inspector", "aria-label": "Selection details"});
    const description = html("p", {class: "pv-description"});
    const legend = html("div", {class: "pv-legend", "aria-label": "Legend"});
    const status = html("div", {class: "pv-status", role: "status", "aria-live": "polite"});
    workspace.append(canvas, description, legend, status); main.append(workspace, inspector);
    app.append(header, navigation, toolbar, warning, main); container.replaceChildren(app);

    for (const panel of source.panels) {
      const tab = button(panel.title, () => { controller.ready = selectPanel(panel.id); }, {role: "tab", id: `pv-tab-${instance}-${tabs.size}`, "aria-controls": workspace.id, "aria-selected": "false", tabindex: "-1"});
      tab.addEventListener("keydown", event => {
        const all = [...tabs.keys()], index = all.indexOf(panel.id);
        let next;
        if (event.key === "ArrowRight") next = (index + 1) % all.length;
        if (event.key === "ArrowLeft") next = (index + all.length - 1) % all.length;
        if (event.key === "Home") next = 0;
        if (event.key === "End") next = all.length - 1;
        if (next !== undefined) { event.preventDefault(); tabs.get(all[next]).focus(); controller.ready = selectPanel(all[next]); }
      });
      tabs.set(panel.id, tab); navigation.append(tab);
    }
    search.addEventListener("input", applySearch);
    function fields(parent, values) {
      const list = html("dl", {class: "pv-fields"});
      for (const field of values || []) list.append(html("dt", {}, field.name), html("dd", {}, `${textOf(field.value)}${field.unit ? ` ${field.unit}` : ""}`));
      parent.append(list);
    }
    function overview() {
      inspector.replaceChildren(html("p", {class: "pv-eyebrow"}, "DETAILS"), html("h2", {}, current ? current.title : source.title));
      inspector.append(html("p", {}, "Select an item to inspect its supplied values and evidence. Search highlights items without changing the calculation."));
      if (current) fields(inspector, [{name: "View", value: KINDS[current.kind] || current.kind}, {name: "Panel ID", value: current.id}]);
      const provenance = (source.provenance || []).filter(item => {
        if (!current) return true;
        const panelIds = item.panel_ids || [];
        return panelIds.length ? panelIds.includes(current.id) : !(item.input_path || []).length;
      });
      if (provenance.length) inspector.append(html("h3", {}, "Calculation provenance"));
      for (const item of provenance) {
        const block = html("section", {class: "pv-provenance"});
        fields(block, ["operator_id", "calculation_id", "source_digest", "model_digest", "status"].filter(key => item[key] !== null && item[key] !== undefined).map(key => ({name: key.replace(/_/g, " "), value: item[key]})));
        fields(block, [{name: "Input path", value: item.input_path || []}, {name: "Associated panel IDs", value: (item.panel_ids || []).length ? item.panel_ids : (item.input_path || []).length ? "No associated panels" : "All panels"}]);
        fields(block, item.details); inspector.append(block);
      }
      inspector.append(html("p", {class: "pv-note"}, "Unknown values remain unknown. Display rounding does not alter stored values. Full labels are available in these details."));
    }
    function inspect(record, node) {
      if (moved) return;
      if (selected) selected.classList.remove("is-selected");
      selected = node; if (node) node.classList.add("is-selected");
      inspector.replaceChildren(html("p", {class: "pv-eyebrow"}, "SELECTED ITEM"), html("h2", {}, record.title || "Details"), button("Clear selection", () => { if (selected) selected.classList.remove("is-selected"); selected = null; overview(); }));
      fields(inspector, [{name: "Label", value: record.title || "Details"}, ...(record.fields || [])]);
      if (record.metrics && record.metrics.length) { inspector.append(html("h3", {}, "Metrics")); fields(inspector, record.metrics); }
      if (record.details && record.details.length) { inspector.append(html("h3", {}, "Evidence and attributes")); fields(inspector, record.details); }
    }
    function selectable(node, record, title) {
      node.classList.add("pv-mark"); node.setAttribute("tabindex", "0"); if (node.tagName.toLowerCase() !== "tr") node.setAttribute("role", "button"); node.setAttribute("aria-label", display(title || record.title));
      if (node.namespaceURI === NS) node.append(svgNode("title", {}, title || record.title));
      const entry = {node, text: display(JSON.stringify(record)).toLocaleLowerCase()}; marks.push(entry);
      node.addEventListener("click", () => inspect(record, node));
      node.addEventListener("keydown", event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); moved = false; inspect(record, node); } });
      return node;
    }
    function applySearch() {
      const query = search.value.trim().toLocaleLowerCase();
      if (tableQuery) { tableQuery(query); return; }
      let count = 0;
      for (const mark of marks) { const matches = Boolean(query) && mark.text.includes(query); mark.node.classList.toggle("is-match", matches); if (matches) count++; }
      searchStatus.textContent = query ? `${count} matches` : "";
    }
    function legendItem(label, color, note) {
      const item = html("span", {class: "pv-legend-item"});
      if (color) { const swatch = html("span", {class: "pv-swatch", "aria-hidden": "true"}); swatch.style.backgroundColor = color; item.append(swatch); }
      item.append(html("span", {}, note === undefined ? label : `${label}: ${scalar(note)}`)); legend.append(item);
    }
    function setStatus(message) { status.textContent = [message, ...currentNotes].filter(Boolean).join(" · "); }
    function limitMessage(message) {
      canvas.append(html("div", {class: "pv-empty"}, message));
      setStatus("Display limit reached. The complete supplied document is unchanged.");
    }
    function makeSVG(width, height, label) {
      bounds = {x: 0, y: 0, width: Math.max(1, width), height: Math.max(1, height)};
      const svg = svgNode("svg", {class: "pv-svg", tabindex: "0", role: "group", "aria-label": `${label}. Drag to pan; plus and minus zoom; zero fits. Tab and Enter inspect marks.`, xmlns: NS});
      svg.append(svgNode("title", {}, label), svgNode("desc", {}, current.description || "PIX visualization of supplied analysis values."));
      currentSVG = svg; canvas.append(svg); fit();
      const help = html("div", {class: "pv-help"}, "Drag to pan · Scroll to zoom · Tab + Enter to inspect"); canvas.append(help);
      svg.addEventListener("wheel", event => { event.preventDefault(); zoom(event.deltaY > 0 ? 1.14 : 1 / 1.14, event); }, {passive: false});
      svg.addEventListener("pointerdown", event => {
        if (event.button !== 0) return;
        moved = false; pointer = {id: event.pointerId, x: event.clientX, y: event.clientY, view: {...view}};
      });
      svg.addEventListener("pointermove", event => {
        if (!pointer || pointer.id !== event.pointerId) return;
        const rect = svg.getBoundingClientRect(), dx = event.clientX - pointer.x, dy = event.clientY - pointer.y;
        if (Math.abs(dx) + Math.abs(dy) > 4) { moved = true; if (svg.setPointerCapture) svg.setPointerCapture(event.pointerId); }
        const scale = Math.max(1e-10, Math.min(rect.width / pointer.view.width, rect.height / pointer.view.height));
        view.x = pointer.view.x - dx / scale; view.y = pointer.view.y - dy / scale; updateView();
      });
      const release = () => { pointer = null; };
      svg.addEventListener("pointerup", release); svg.addEventListener("pointercancel", release);
      svg.addEventListener("keydown", event => {
        if (event.target !== svg) return;
        let handled = true;
        if (event.key === "+" || event.key === "=") zoom(0.8);
        else if (event.key === "-") zoom(1.25);
        else if (event.key === "0") fit();
        else if (event.key === "1") readable();
        else if (event.key === "ArrowLeft") view.x -= view.width * 0.1;
        else if (event.key === "ArrowRight") view.x += view.width * 0.1;
        else if (event.key === "ArrowUp") view.y -= view.height * 0.1;
        else if (event.key === "ArrowDown") view.y += view.height * 0.1;
        else handled = false;
        if (handled) { event.preventDefault(); updateView(); }
      });
      return svg;
    }
    function updateView() { if (currentSVG) currentSVG.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`); }
    function fit() { view = {...bounds}; updateView(); }
    function readable() {
      if (!currentSVG) return;
      const rect = currentSVG.getBoundingClientRect();
      view = {x: (bounds.width - Math.max(rect.width, 1)) / 2, y: (bounds.height - Math.max(rect.height, 1)) / 2, width: Math.max(rect.width, 1), height: Math.max(rect.height, 1)}; updateView();
    }
    function zoom(factor, event) {
      if (!currentSVG) return;
      const ratio = view.width * factor / bounds.width;
      if (ratio < 0.005 || ratio > 100) return;
      let x = 0.5, y = 0.5;
      if (event) { const rect = currentSVG.getBoundingClientRect(), scale = Math.max(1e-10, Math.min(rect.width / view.width, rect.height / view.height)); x = (event.clientX - rect.left - (rect.width - view.width * scale) / 2) / (view.width * scale); y = (event.clientY - rect.top - (rect.height - view.height * scale) / 2) / (view.height * scale); }
      view.x += view.width * (1 - factor) * x; view.y += view.height * (1 - factor) * y; view.width *= factor; view.height *= factor; updateView();
    }
    async function renderGraph(panel, token) {
      if (panel.nodes.length > limits.graphNodes || panel.edges.length > limits.graphEdges) { limitMessage(`This graph has ${panel.nodes.length} nodes and ${panel.edges.length} edges. This view allows ${limits.graphNodes} nodes and ${limits.graphEdges} edges; use a smaller analysis view or explicitly raise the display limits.`); return; }
      const engine = options.layout || (layoutEngine === "graphviz" ? root.PIXGraphvizGeometry?.layout : root.PIXNativeGeometry?.layout);
      if (typeof engine !== "function") throw new Error(`PIX ${layoutEngine} geometry is unavailable. No alternative layout was substituted.`);
      setStatus("Arranging the graph…");
      const geometry = validateGeometry(panel, await engine(structuredClone(panel), {layout: panel.layout, direction: options.direction || "LR"}));
      if (disposed || token !== generation) return;
      const svg = makeSVG(geometry.width, geometry.height, panel.title);
      const defs = svgNode("defs"), marker = svgNode("marker", {id: `pv-arrow-${instance}-${token}`, markerWidth: 8, markerHeight: 8, refX: 7, refY: 4, orient: "auto", markerUnits: "userSpaceOnUse"});
      marker.append(svgNode("path", {d: "M 0 0 L 8 4 L 0 8 Z", fill: "#78909a"})); defs.append(marker); svg.append(defs);
      const edgeLayer = svgNode("g"), nodeLayer = svgNode("g"); svg.append(edgeLayer, nodeLayer);
      const routeMap = new Map(geometry.edges.map(edge => [edge.id, edge]));
      let shortened = 0;
      const edgeTypes = new Set(), metricUnits = new Map();
      const shapeBoxes = new Map(geometry.nodes.map(node => [node.id, node]));
      const sourceNodes = new Map(panel.nodes.map(node => [node.id, node]));
      for (const edge of panel.edges) {
        const route = routeMap.get(edge.id), group = svgNode("g");
        const points = route.points.map(point => ({...point}));
        let path;
        if (route.splines) {
          path = route.splines.map(spline => {
            const p = spline.points; let result = `M ${p[0].x} ${p[0].y}`;
            for (let i = 1; i < p.length; i += 3) result += ` C ${p[i].x} ${p[i].y} ${p[i + 1].x} ${p[i + 1].y} ${p[i + 2].x} ${p[i + 2].y}`;
            return result;
          }).join(" ");
        } else {
          points[0] = shapeEndpoint(shapeBoxes.get(edge.source), sourceNodes.get(edge.source).kind, points[1]) || points[0];
          points[points.length - 1] = shapeEndpoint(shapeBoxes.get(edge.target), sourceNodes.get(edge.target).kind, points[points.length - 2]) || points[points.length - 1];
          path = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
        }
        const objectType = (edge.details || []).find(field => field.name === "object_type" && typeof field.value === "string")?.value;
        if (objectType) edgeTypes.add(objectType);
        const color = hashColor(objectType || edge.kind || "relation"); group.style.setProperty("--pv-color", color);
        const line = svgNode("path", {d: path, class: "pv-edge-line"});
        if (edge.directed && route.arrowhead === undefined) line.setAttribute("marker-end", `url(#pv-arrow-${instance}-${token})`);
        if (["variable", "optional", "silent", "inhibitor", "reset"].includes(edge.kind) || (edge.details || []).some(field => field.name === "variable" && field.value === true)) line.setAttribute("stroke-dasharray", "6 4");
        group.append(svgNode("path", {d: path, class: "pv-edge-hit"}), line);
        for (const arrow of [route.arrowhead, route.arrowtail]) if (arrow?.length) group.append(svgNode("polygon", {points: arrow.map(point => `${point.x},${point.y}`).join(" "), fill: color, class: "pv-edge-arrow"}));
        const label = edge.label || ((edge.metrics || []).length ? metricText(edge.metrics[0]) : "");
        if (label) {
          const middle = Math.floor((points.length - 1) / 2), a = points[middle], b = points[middle + 1];
          group.append(svgNode("text", {x: route.labelPosition?.x ?? (a.x + b.x) / 2, y: route.labelPosition ? route.labelPosition.y + 3 : (a.y + b.y) / 2 - 7, "text-anchor": "middle", class: "pv-edge-label"}, shorten(label, 44)));
          if (Array.from(label).length > 44) shortened++;
        }
        selectable(group, {title: edge.label || `${edge.source} → ${edge.target}`, fields: [{name: "ID", value: edge.id}, {name: "Kind", value: edge.kind}, {name: "Source", value: edge.source}, {name: "Target", value: edge.target}, {name: "Directed", value: edge.directed}], metrics: edge.metrics, details: edge.details}, `${edge.label || edge.id}. ${edge.kind}. ${(edge.metrics || []).map(metricText).join("; ")}`); edgeLayer.append(group);
      }
      const boxes = new Map(geometry.nodes.map(node => [node.id, node]));
      const groups = new Set(), kinds = new Set();
      for (const node of panel.nodes) {
        const box = boxes.get(node.id), group = svgNode("g", {transform: `translate(${box.x} ${box.y})`});
        const colorKey = node.group || node.kind; groups.add(node.group); kinds.add(node.kind);
        group.style.setProperty("--pv-color", hashColor(colorKey)); group.style.setProperty("--pv-tint", hashColor(colorKey, 96));
        shape(group, node.kind, box.width, box.height);
        const details = new Map((node.details || []).map(field => [field.name, field.value]));
        if (["place", "state"].includes(node.kind) && typeof details.get("final_count") === "number" && details.get("final_count") > 0) group.append(svgNode("ellipse", {cx: box.width / 2, cy: box.height / 2, rx: Math.max(1, box.width / 2 - 5), ry: Math.max(1, box.height / 2 - 5), fill: "none", stroke: hashColor(colorKey), "stroke-width": 1.2}));
        if (node.kind === "place" && typeof details.get("initial_count") === "number" && details.get("initial_count") > 0) group.append(svgNode("text", {x: box.width / 2, y: box.height - 7, "text-anchor": "middle", class: "pv-node-metric"}, `● ${details.get("initial_count")}`));
        const wrap = root.PIXNativeGeometry && root.PIXNativeGeometry.wrapLabel;
        const maxChars = Math.max(4, Math.floor((box.width - 22) / 7));
        let lines = wrap ? wrap(node.label, maxChars, 3) : [shorten(node.label, maxChars)];
        if (lines && !Array.isArray(lines)) lines = lines.lines;
        if (!Array.isArray(lines)) lines = [shorten(node.label, maxChars)];
        if (lines.some(line => line.endsWith("…"))) shortened++;
        const metrics = (node.metrics || []).slice(0, 2);
        for (const metric of metrics) if (metric.unit) metricUnits.set(JSON.stringify([metric.name, metric.unit]), {name: metric.name, unit: metric.unit});
        if (node.kind !== "silent") {
          const start = box.height / 2 - ((lines.length - 1) * 15 + metrics.length * 12) / 2 + 4;
          lines.forEach((line, index) => group.append(svgNode("text", {x: box.width / 2, y: start + index * 15, "text-anchor": "middle", class: "pv-node-label"}, line)));
          metrics.forEach((metric, index) => { const label = `${metric.name}: ${scalar(metric.value)}`, maxMetricChars = Math.max(4, Math.floor((box.width - 18) / 5.2)); if (Array.from(label).length > maxMetricChars) shortened++; group.append(svgNode("text", {x: box.width / 2, y: start + lines.length * 15 + index * 12, "text-anchor": "middle", class: "pv-node-metric"}, shorten(label, maxMetricChars))); });
        }
        selectable(group, {title: node.label, fields: [{name: "ID", value: node.id}, {name: "Kind", value: node.kind}, ...(node.group ? [{name: "Group", value: node.group}] : [])], metrics: node.metrics, details: node.details}, `${node.label}. ${node.kind}. ${(node.metrics || []).map(metricText).join("; ")}`); nodeLayer.append(group);
      }
      if (!panel.nodes.length) svg.append(svgNode("text", {x: geometry.width / 2, y: geometry.height / 2, "text-anchor": "middle", class: "pv-empty-svg"}, "No nodes supplied"));
      [...new Set([...groups].filter(Boolean).concat([...edgeTypes]))].sort().forEach(group => legendItem(group, hashColor(group)));
      [...kinds].sort().forEach(kind => legendItem(kind, null));
      [...metricUnits.values()].forEach(metric => legendItem(`${metric.name} unit`, null, metric.unit));
      legendItem("Arrowheads indicate directed relations", null);
      if (panel.nodes.some(node => ["place", "state"].includes(node.kind) && (node.details || []).some(field => field.name === "final_count" && field.value > 0))) legendItem("Inner ring", null, "Supplied final count is nonzero");
      if (panel.nodes.some(node => node.kind === "place" && (node.details || []).some(field => field.name === "initial_count" && field.value > 0))) legendItem("● count", null, "Supplied initial tokens");
      if (panel.edges.some(edge => (edge.details || []).some(field => field.name === "variable" && field.value === true))) legendItem("Dashed arc", null, "Variable object cardinality");
      if (shortened) currentNotes.push(`${shortened} labels shortened; select for full text`);
      if (geometry.notes) currentNotes.push(...geometry.notes);
      currentNotes.push(options.layout ? "Custom layout" : geometry.engine === "graphviz" ? `Graphviz ${geometry.engineVersion} · ${geometry.layout || "dot"}` : `Experimental PIX native ${panel.layout || "layered"} layout`);
      setStatus(`${panel.nodes.length} nodes · ${panel.edges.length} edges · widths do not encode frequency`);
    }
    function shapeEndpoint(box, kind, toward) {
      if (!["place", "state", "operator", "gateway", "decision"].includes(kind)) return null;
      const cx = box.x + box.width / 2, cy = box.y + box.height / 2, rx = box.width / 2, ry = box.height / 2;
      const dx = toward.x - cx, dy = toward.y - cy;
      const divisor = ["gateway", "decision"].includes(kind) ? Math.abs(dx) / rx + Math.abs(dy) / ry : Math.hypot(dx / rx, dy / ry);
      return divisor > 0 ? {x: cx + dx / divisor, y: cy + dy / divisor} : {x: cx + rx, y: cy};
    }
    function shape(parent, kind, width, height) {
      const attrs = {class: "pv-node-shape"}, cx = width / 2, cy = height / 2;
      if (["place", "state", "operator"].includes(kind)) parent.append(svgNode("ellipse", {...attrs, cx, cy, rx: cx, ry: cy}));
      else if (["gateway", "decision"].includes(kind)) parent.append(svgNode("polygon", {...attrs, points: `${cx},0 ${width},${cy} ${cx},${height} 0,${cy}`}));
      else if (kind === "resource") parent.append(svgNode("polygon", {...attrs, points: `14,0 ${width - 14},0 ${width},${cy} ${width - 14},${height} 14,${height} 0,${cy}`}));
      else if (kind === "rule") { parent.append(svgNode("path", {...attrs, d: `M0 0 H${width - 12} L${width} 12 V${height} H0 Z M${width - 12} 0 V12 H${width}`})); }
      else parent.append(svgNode("rect", {...attrs, x: 0, y: 0, width, height, rx: kind === "object" ? Math.min(height / 2, 28) : kind === "event" ? 2 : kind === "binding" ? 15 : 8, ...(kind === "silent" ? {class: "pv-node-shape pv-silent"} : {})}));
    }
    function renderMatrix(panel) {
      if (panel.rows.length * panel.columns.length > limits.matrixCells) { limitMessage(`This matrix grid has ${panel.rows.length * panel.columns.length} positions; the display limit is ${limits.matrixCells}. Use a smaller view or explicitly raise the limit.`); return; }
      const left = 180, top = 145, cellW = 94, cellH = 43;
      const svg = makeSVG(Math.max(500, left + panel.columns.length * cellW + 30), Math.max(280, top + panel.rows.length * cellH + 65), panel.title);
      const cells = new Map(panel.cells.map(cell => [JSON.stringify([cell.row, cell.column]), cell]));
      let maxAbs = 1, unknown = 0;
      for (const cell of panel.cells) if (["number", "bigint"].includes(typeof cell.value)) maxAbs = Math.max(maxAbs, Math.abs(Number(cell.value)));
      panel.columns.forEach((label, index) => { const text = svgNode("text", {transform: `translate(${left + index * cellW + cellW / 2} ${top - 15}) rotate(-35)`, "text-anchor": "start", class: "pv-tick"}, shorten(label, 28)); text.append(svgNode("title", {}, label)); svg.append(text); });
      panel.rows.forEach((row, r) => {
        const label = svgNode("text", {x: left - 13, y: top + r * cellH + cellH / 2 + 4, "text-anchor": "end", class: "pv-tick"}, shorten(row, 24)); label.append(svgNode("title", {}, row)); svg.append(label);
        panel.columns.forEach((column, c) => {
          const cell = cells.get(JSON.stringify([row, column])), value = cell ? cell.value : undefined;
          const x = left + c * cellW, y = top + r * cellH, group = svgNode("g");
          let fill = "#fafbfc";
          if (["number", "bigint"].includes(typeof value)) { const normalized = Number(value) / maxAbs; fill = Number.isFinite(normalized) ? `hsl(${value < 0 ? 30 : 199} 48% ${97 - Math.min(1, Math.abs(normalized)) * 28}%)` : "#eef2f4"; }
          else if (value !== undefined && value !== null) fill = hashColor(cell.kind || String(value), 91);
          group.append(svgNode("rect", {x, y, width: cellW, height: cellH, fill, stroke: "#dce5e9", ...(value === null ? {class: "pv-unknown"} : {})}));
          group.append(svgNode("text", {x: x + cellW / 2, y: y + cellH / 2 + 4, "text-anchor": "middle", class: "pv-cell-label"}, value === undefined ? "—" : value === null ? "?" : shorten(typeof value === "number" ? number(value) : scalar(value), 12)));
          if (value === null) unknown++;
          selectable(group, {title: `${row} / ${column}`, fields: [{name: "Row", value: row}, {name: "Column", value: column}, {name: "Value", value: value === undefined ? "Not supplied" : value, unit: panel.unit}, ...(cell ? [{name: "Kind", value: cell.kind}] : [])], details: cell ? cell.details : []}); svg.append(group);
        });
      });
      if (!panel.rows.length || !panel.columns.length) svg.append(svgNode("text", {x: 250, y: 140, "text-anchor": "middle", class: "pv-empty-svg"}, "No matrix values supplied"));
      (panel.legend || []).forEach(item => legendItem(item.name, null, item.value));
      legendItem("?", "#e9edf0", "Unknown"); legendItem("—", null, "Not supplied");
      if (panel.unit) legendItem("Unit", null, panel.unit);
      if (panel.cells.some(cell => typeof cell.value === "number")) { legendItem("Positive numeric fill", "hsl(199 48% 69%)"); legendItem("Negative numeric fill", "hsl(30 48% 69%)"); legendItem("Full color intensity", null, `${number(maxAbs)}${panel.unit ? ` ${panel.unit}` : ""} in absolute value`); }
      setStatus(`${panel.rows.length} rows · ${panel.columns.length} columns · ${panel.cells.length} supplied cells · ${unknown} unknown values`);
    }
    function renderChart(panel) {
      const total = panel.series.reduce((sum, series) => sum + series.points.length, 0);
      if (total > limits.chartPoints) { limitMessage(`This chart has ${total} points; the display limit is ${limits.chartPoints}. Use a smaller view or explicitly raise the limit.`); return; }
      const width = 1050, height = 570, left = 94, right = 1010, top = 45, bottom = 460;
      const svg = makeSVG(width, height, panel.title), points = panel.series.flatMap(series => series.points);
      const categories = [...new Set(points.map(point => String(point.x)))];
      const xValue = point => panel.x_type === "time" ? timestampSeconds(point.x) : Number(point.x);
      const xd = panel.x_type === "category" ? [0, Math.max(categories.length, 1)] : extent(points.map(xValue), false, panel.x_type === "time" ? 1 : null);
      const numericY = points.filter(point => point.y !== null).map(point => Number(point.y));
      if (numericY.some(value => !Number.isFinite(value))) throw new Error("A chart value exceeds the browser's finite coordinate range. Its exact value remains in the source document.");
      const yd = extent(numericY, panel.chart_type === "bar");
      const xs = linear(xd, [left, right]), ys = linear(yd, [bottom, top]);
      const xPosition = point => panel.x_type === "category" ? left + (categories.indexOf(String(point.x)) + 0.5) * (right - left) / Math.max(categories.length, 1) : xs(xValue(point));
      axes(svg, {left, right, top, bottom, yd, ys, xLabel: `${panel.x_label}${panel.x_unit ? ` (${panel.x_unit})` : ""}`, yLabel: `${panel.y_label}${panel.y_unit ? ` (${panel.y_unit})` : ""}`});
      if (panel.x_type === "category") {
        const step = Math.max(1, Math.ceil(categories.length / 10));
        categories.forEach((label, index) => { if (index % step === 0 || index === categories.length - 1) { const text = svgNode("text", {x: left + (index + 0.5) * (right - left) / Math.max(categories.length, 1), y: bottom + 23, "text-anchor": "middle", class: "pv-tick"}, shorten(label, 16)); text.append(svgNode("title", {}, label)); svg.append(text); } });
        if (step > 1) currentNotes.push("X-axis labels sampled; every supplied point remains available");
      } else for (let i = 0; i <= 5; i++) {
        const value = between(xd[0], xd[1], i / 5);
        svg.append(svgNode("text", {x: xs(value), y: bottom + 23, "text-anchor": "middle", class: "pv-tick"}, panel.x_type === "time" ? utcLabel(value, xd[1] - xd[0]) : number(value)));
      }
      let missing = 0;
      panel.series.forEach((series, seriesIndex) => {
        const color = hashColor(series.group || series.name); legendItem(series.name, color);
        let segment = [];
        const flush = () => { if (segment.length > 1) svg.append(svgNode("polyline", {points: segment.map(point => point.join(",")).join(" "), stroke: color, class: "pv-series-line"})); segment = []; };
        series.points.forEach(point => {
          const x = xPosition(point), y = point.y === null ? bottom + 11 : ys(Number(point.y));
          if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error("Chart positions must be finite.");
          if (point.y === null) { missing++; flush(); }
          else if (panel.chart_type === "line") segment.push([x, y]);
          const group = svgNode("g");
          if (point.y === null) group.append(svgNode("path", {d: `M${x - 4} ${y - 4} L${x + 4} ${y + 4} M${x + 4} ${y - 4} L${x - 4} ${y + 4}`, stroke: color, "stroke-width": 2}));
          else if (panel.chart_type === "bar") {
            const slot = panel.x_type === "category" ? (right - left) / Math.max(categories.length, 1) : Math.min(45, (right - left) / Math.max(points.length, 1));
            const barW = Math.max(0.5, slot * 0.72 / Math.max(panel.series.length, 1));
            const bx = x - slot * 0.36 + seriesIndex * barW;
            group.append(svgNode("rect", {x: bx, y: Math.min(y, ys(0)), width: barW, height: Math.max(1, Math.abs(y - ys(0))), rx: 2, fill: color}));
          } else group.append(svgNode("circle", {cx: x, cy: y, r: panel.chart_type === "scatter" ? 5 : 4, fill: color, stroke: "white", "stroke-width": 1.5}));
          selectable(group, {title: series.name, fields: [{name: panel.x_label || "X", value: point.x, unit: panel.x_unit}, {name: panel.y_label || "Y", value: point.y, unit: panel.y_unit}], details: point.details}); svg.append(group);
        }); flush();
      });
      if (!points.some(point => point.y !== null)) svg.append(svgNode("text", {x: (left + right) / 2, y: (top + bottom) / 2, "text-anchor": "middle", class: "pv-empty-svg"}, total ? "All supplied Y values are unknown" : "No chart points supplied"));
      if (panel.x_type === "time") currentNotes.push("Time axis: UTC");
      if (missing) { currentNotes.push(`${missing} unknown Y values appear as crosses below the axis; line segments break at unknown values`); legendItem("Cross below X axis", null, "Unknown Y, no numeric vertical position"); }
      setStatus(`${panel.series.length} series · ${total - missing} plotted points · ${missing} unknown values`);
    }
    function axes(svg, {left, right, top, bottom, yd, ys, xLabel, yLabel}) {
      for (let i = 0; i <= 5; i++) {
        const value = between(yd[0], yd[1], i / 5), y = ys(value);
        svg.append(svgNode("line", {x1: left, y1: y, x2: right, y2: y, class: "pv-grid"}), svgNode("text", {x: left - 12, y: y + 4, "text-anchor": "end", class: "pv-tick"}, number(value)));
      }
      svg.append(svgNode("path", {d: `M${left} ${top} V${bottom} H${right}`, fill: "none", class: "pv-axis"}), svgNode("text", {x: (left + right) / 2, y: bottom + 72, "text-anchor": "middle", class: "pv-axis-label"}, xLabel), svgNode("text", {transform: `translate(22 ${(top + bottom) / 2}) rotate(-90)`, "text-anchor": "middle", class: "pv-axis-label"}, yLabel));
    }
    function utcLabel(seconds, span) {
      const date = new Date(seconds * 1000);
      if (!Number.isFinite(date.getTime())) return number(seconds);
      const iso = date.toISOString();
      if (span < 0.001) {
        let whole = Math.floor(seconds), microseconds = Math.round((seconds - whole) * 1000000);
        if (microseconds === 1000000) { whole++; microseconds = 0; }
        return `${new Date(whole * 1000).toISOString().slice(11, 19)}.${String(microseconds).padStart(6, "0")}`;
      }
      return span >= 172800 ? iso.slice(0, 10) : span >= 3600 ? iso.slice(5, 16).replace("T", " ") : iso.slice(11, 23);
    }
    function renderTimeline(panel) {
      if (panel.items.length > limits.timelineItems) { limitMessage(`This timeline has ${panel.items.length} items; the display limit is ${limits.timelineItems}. Use a smaller view or explicitly raise the limit.`); return; }
      const left = 190, right = 1130, top = 60, tracks = new Map(), laneSizes = new Map(), laneOffsets = new Map();
      for (const lane of panel.lanes) {
        const ends = [], items = panel.items.filter(item => item.lane === lane.id).slice().sort((a, b) => a.start - b.start || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
        for (const item of items) {
          let track = ends.findIndex(end => end < item.start);
          if (track < 0) { track = ends.length; ends.push(item.end === null ? Infinity : item.end); }
          else ends[track] = item.end === null ? Infinity : item.end;
          tracks.set(item.id, track);
        }
        laneSizes.set(lane.id, Math.max(66, ends.length * 42 + 24));
      }
      let bottom = top;
      for (const lane of panel.lanes) { laneOffsets.set(lane.id, bottom); bottom += laneSizes.get(lane.id); }
      if (!panel.lanes.length) bottom += 66;
      const svg = makeSVG(1180, bottom + 90, panel.title);
      const values = panel.items.flatMap(item => item.end === null ? [item.start] : [item.start, item.end]);
      const domain = extent(values.map(Number), false, 1), span = domain[1] / 2 - domain[0] / 2, paddedHigh = domain[1] + span * 0.14;
      if (Number.isFinite(paddedHigh)) domain[1] = paddedHigh;
      const xs = linear(domain, [left, right]);
      const lanes = new Map(panel.lanes.map((lane, index) => [lane.id, index]));
      panel.lanes.forEach((lane, index) => {
        const y = laneOffsets.get(lane.id), laneHeight = laneSizes.get(lane.id);
        svg.append(svgNode("rect", {x: left, y, width: right - left, height: laneHeight, fill: index % 2 ? "#f2f6f8" : "#fafcfd"}), svgNode("line", {x1: left, x2: right, y1: y + laneHeight, y2: y + laneHeight, class: "pv-grid"}));
        const label = svgNode("text", {x: left - 16, y: y + laneHeight / 2 + 4, "text-anchor": "end", class: "pv-tick"}, shorten(lane.label, 24)); label.append(svgNode("title", {}, lane.label)); svg.append(label);
      });
      for (let i = 0; i <= 5; i++) {
        const value = between(domain[0], domain[1], i / 5), x = xs(value);
        svg.append(svgNode("line", {x1: x, x2: x, y1: top - 10, y2: bottom, class: "pv-grid"}), svgNode("text", {x, y: bottom + 28, "text-anchor": "middle", class: "pv-tick"}, panel.axis_type === "timestamp" ? utcLabel(value, domain[1] - domain[0]) : number(value)));
      }
      let open = 0;
      const groups = new Set();
      for (const item of panel.items) {
        if (!lanes.has(item.lane)) throw new Error("Timeline item refers to an unknown lane.");
        const y = laneOffsets.get(item.lane) + tracks.get(item.id) * 42 + 17, x = xs(Number(item.start)), end = item.end === null ? right : xs(Number(item.end)), width = Math.max(2, end - x);
        const group = svgNode("g"), colorKey = item.group || panel.lanes[lanes.get(item.lane)].group || "Intervals", color = hashColor(colorKey); groups.add(colorKey);
        if (item.end === null) {
          open++; group.append(svgNode("rect", {x, y, width, height: 31, rx: 5, fill: color, "fill-opacity": 0.18, stroke: color, "stroke-dasharray": "5 4"}), svgNode("path", {d: `M${right - 9} ${y + 7} L${right} ${y + 15.5} L${right - 9} ${y + 24}`, fill: "none", stroke: color, "stroke-width": 2}));
        } else if (item.end === item.start) group.append(svgNode("polygon", {points: `${x},${y + 7} ${x + 7},${y + 15.5} ${x},${y + 24} ${x - 7},${y + 15.5}`, fill: color}));
        else group.append(svgNode("rect", {x, y, width, height: 31, rx: 5, fill: color}));
        const maxChars = Math.floor((width - 14) / 7);
        if (maxChars > 3) group.append(svgNode("text", {x: x + 8, y: y + 20, class: item.end === null ? "pv-tick" : "pv-timeline-label"}, shorten(item.end === null ? `${item.label} · Open` : item.label, maxChars)));
        selectable(group, {title: item.label, fields: [{name: "ID", value: item.id}, {name: "Lane", value: panel.lanes[lanes.get(item.lane)].label}, {name: "Start", value: item.start, unit: panel.unit}, {name: "End", value: item.end, unit: panel.unit}, ...(panel.axis_type === "timestamp" ? [{name: "Start (UTC)", value: utcFull(Number(item.start))}, {name: "End (UTC)", value: item.end === null ? null : utcFull(Number(item.end))}] : []), ...(item.status !== null ? [{name: "Status", value: item.status}] : [])], details: item.details}); svg.append(group);
      }
      svg.append(svgNode("text", {x: (left + right) / 2, y: bottom + 66, "text-anchor": "middle", class: "pv-axis-label"}, `${panel.axis_type === "timestamp" ? "Time (UTC)" : "Relative time"} · ${panel.unit}`));
      if (!panel.items.length) svg.append(svgNode("text", {x: (left + right) / 2, y: top + 35, "text-anchor": "middle", class: "pv-empty-svg"}, "No timeline items supplied"));
      [...groups].sort().forEach(group => legendItem(group, hashColor(group)));
      if (panel.items.some(item => item.end === item.start)) legendItem("Diamond", null, "Observed instant / zero-duration interval");
      if (open) legendItem("Dashed interval / open arrow", null, "End is unknown; extends only to the view boundary");
      currentNotes.push("Overlapping items use separate tracks within their supplied lane; every interval is retained");
      setStatus(`${panel.lanes.length} lanes · ${panel.items.length} items · ${open} open ends`);
    }
    function renderTable(panel) {
      const wrapper = html("div", {class: "pv-table-wrap"}), table = html("table", {class: "pv-table"});
      const caption = html("caption", {class: "pv-sr-only"}, panel.title), head = html("thead"), row = html("tr"), body = html("tbody");
      panel.columns.forEach(column => row.append(html("th", {scope: "col"}, column))); head.append(row); table.append(caption, head, body); wrapper.append(table);
      const pager = html("div", {class: "pv-pager"}), pageStatus = html("span", {role: "status"});
      let page = 0, filtered = panel.rows.map((values, index) => ({values, index}));
      const previous = button("Previous", () => { page--; draw(); }), next = button("Next", () => { page++; draw(); });
      pager.append(previous, pageStatus, next); canvas.append(wrapper, pager);
      function draw() {
        body.replaceChildren(); marks = []; selected = null;
        const start = page * limits.tablePageSize, values = filtered.slice(start, start + limits.tablePageSize);
        for (const item of values) {
          const tr = html("tr"); item.values.forEach(value => tr.append(html("td", {}, scalar(value))));
          selectable(tr, {title: `Row ${item.index + 1}`, fields: panel.columns.map((column, index) => ({name: column, value: item.values[index]}))}); body.append(tr);
        }
        previous.disabled = page === 0; next.disabled = start + limits.tablePageSize >= filtered.length;
        pageStatus.textContent = filtered.length ? `${start + 1}–${Math.min(start + limits.tablePageSize, filtered.length)} of ${filtered.length}` : "No matching rows";
        setStatus(`${panel.rows.length} source rows · ${filtered.length} rows in this view · ${limits.tablePageSize} per page`);
      }
      tableQuery = query => { filtered = panel.rows.map((values, index) => ({values, index})).filter(item => item.values.some(value => scalar(value).toLocaleLowerCase().includes(query))); page = 0; draw(); searchStatus.textContent = query ? `${filtered.length} matching rows` : ""; };
      draw();
    }
    function renderChevron(panel) {
      if (!Array.isArray(panel.lanes) || !Array.isArray(panel.events)) throw new Error("Chevron lanes and events must be arrays.");
      const laneIds = new Set(panel.lanes.map(lane => lane.id)), eventIds = new Set(panel.events.map(event => event.id));
      if (laneIds.size !== panel.lanes.length || eventIds.size !== panel.events.length) throw new Error("Chevron lane and event identities must be unique.");
      let appearances = 0, slots = 1;
      for (const event of panel.events) {
        if (!Number.isSafeInteger(event.start) || !Number.isSafeInteger(event.end) || event.start < 0 || event.end < event.start || !Array.isArray(event.lane_ids) || !event.lane_ids.length || new Set(event.lane_ids).size !== event.lane_ids.length || event.lane_ids.some(id => !laneIds.has(id))) throw new Error("Chevron event requires an ordered inclusive interval and distinct existing lanes.");
        appearances += event.lane_ids.length; slots = Math.max(slots, event.end + 1);
      }
      if (appearances > limits.chevronAppearances || panel.lanes.length > limits.chevronAppearances || slots > limits.chevronAppearances) { limitMessage(`This chevron view exceeds the ${limits.chevronAppearances} appearance, lane or slot display limit.`); return; }
      const left = 190, top = 66, slotWidth = 154, laneHeight = 72;
      const width = Math.max(700, left + slots * slotWidth + 35), height = Math.max(180, top + panel.lanes.length * laneHeight + 45);
      const svg = makeSVG(width, height, panel.title);
      const lanes = new Map(), typeCounts = new Map();
      const definitions = svgNode("defs"); svg.append(definitions);
      svg.append(svgNode("text", {x: 20, y: 27, class: "pv-axis-label"}, "Object instances"), svgNode("text", {x: left, y: 27, class: "pv-axis-label"}, "Precedence slots · not elapsed time"));
      for (let slot = 0; slot < slots; slot++) {
        const x = left + slot * slotWidth;
        svg.append(svgNode("line", {x1: x, x2: x, y1: top - 13, y2: height - 25, class: "pv-grid"}), svgNode("text", {x: x + slotWidth / 2, y: top - 22, "text-anchor": "middle", class: "pv-tick"}, slot));
      }
      panel.lanes.forEach((lane, index) => {
        const typeIndex = typeCounts.get(lane.object_type) || 0;
        typeCounts.set(lane.object_type, typeIndex + 1);
        const y = top + index * laneHeight, tint = hashColor(lane.object_type, 88 - (typeIndex % 4) * 5), color = hashColor(lane.object_type, 36);
        lanes.set(lane.id, {lane, index, y, tint, color});
        svg.append(svgNode("rect", {x: 0, y, width, height: laneHeight, fill: hashColor(lane.object_type, 97 - (typeIndex % 2) * 2)}), svgNode("rect", {x: 15, y: y + 23, width: 8, height: 22, rx: 3, fill: color}));
        const label = svgNode("text", {x: 34, y: y + 32, class: "pv-chevron-lane-label"}, shorten(lane.label, 21));
        label.append(svgNode("title", {}, `${lane.label} · ${lane.object_type} · ${lane.object_id}`));
        svg.append(label, svgNode("text", {x: 34, y: y + 49, class: "pv-node-metric"}, shorten(lane.object_id, 25)));
      });
      for (const [eventIndex, event] of panel.events.entries()) {
        const x = left + event.start * slotWidth + 5, eventWidth = (event.end - event.start + 1) * slotWidth - 10;
        const group = svgNode("g", {"data-event-id": event.id, class: "pv-chevron-event"});
        const eventTypes = [...new Set(event.lane_ids.map(id => lanes.get(id).lane.object_type))].sort();
        let sharedFill = null;
        if (eventTypes.length > 1) {
          const id = `pv-chevron-${instance}-${generation}-${eventIndex}`, gradient = svgNode("linearGradient", {id, x1: "0%", x2: "100%", y1: "0%", y2: "0%"});
          eventTypes.forEach((type, index) => {
            const color = hashColor(type, 81);
            gradient.append(svgNode("stop", {offset: `${index / eventTypes.length * 100}%`, "stop-color": color}), svgNode("stop", {offset: `${(index + 1) / eventTypes.length * 100}%`, "stop-color": color}));
          });
          definitions.append(gradient); sharedFill = `url(#${id})`;
        }
        for (const laneId of event.lane_ids) {
          const lane = lanes.get(laneId), y = lane.y + 10, h = 51, tip = 13;
          const polygon = svgNode("polygon", {points: `${x},${y} ${x + eventWidth - tip},${y} ${x + eventWidth},${y + h / 2} ${x + eventWidth - tip},${y + h} ${x},${y + h} ${x + tip},${y + h / 2}`, fill: sharedFill || lane.tint, stroke: lane.color, "stroke-width": 1.4, class: "pv-chevron-shape", "data-event-id": event.id, "data-lane-id": laneId});
          const textX = x + eventWidth / 2 + 2, maxChars = Math.max(8, Math.floor((eventWidth - 36) / 7));
          const lines = root.PIXNativeGeometry?.wrapLabel(event.label, maxChars, 2) || [shorten(event.label, maxChars)];
          group.append(polygon);
          lines.forEach((line, index) => group.append(svgNode("text", {x: textX, y: y + 25 - (lines.length - 1) * 7 + index * 15, "text-anchor": "middle", class: "pv-chevron-label"}, line)));
        }
        selectable(group, {title: event.label, fields: [{name: "Event ID", value: event.id}, {name: "Start slot (inclusive)", value: event.start}, {name: "End slot (inclusive)", value: event.end}, {name: "Object lanes", value: event.lane_ids.map(id => ({lane: id, object_id: lanes.get(id).lane.object_id, object_type: lanes.get(id).lane.object_type}))}, {name: "Semantics", value: "One event; aligned appearances on each participating object lane. Slots do not measure duration."}], details: event.details}, `${event.label}. Shared event ${event.id}. ${event.lane_ids.length} object lanes.`);
        svg.append(group);
      }
      if (!panel.events.length) svg.append(svgNode("text", {x: left + 35, y: Math.max(95, height / 2), class: "pv-empty-svg"}, "No chevrons in this execution"));
      for (const type of typeCounts.keys()) legendItem(type, hashColor(type, 36));
      legendItem("Shades", null, "Object instances of the same type");
      legendItem("Chevron color segments", null, "All participating object types, identical across shared appearances");
      legendItem("Aligned appearances", null, "Same event ID across participating objects");
      legendItem("Width", null, "Inclusive precedence slots; not duration");
      if (panel.frequency != null) legendItem("Variant frequency", null, `${panel.frequency} / ${panel.population} executions${panel.population ? ` (${number(panel.frequency / panel.population * 100)}%)` : ""}`);
      setStatus(`${panel.events.length} distinct events · ${appearances} lane appearances · ${panel.lanes.length} object instances · OCPA-style chevrons`);
    }
    async function selectPanel(id) {
      if (disposed) throw new Error("This visualization has been disposed.");
      const panel = source.panels.find(item => item.id === id);
      if (!panel) throw new Error("Unknown visualization panel.");
      const token = ++generation; current = panel; currentSVG = null; marks = []; selected = null; tableQuery = null; currentNotes = []; moved = false; pointer = null;
      search.value = ""; searchStatus.textContent = ""; canvas.replaceChildren(); legend.replaceChildren(); status.textContent = "";
      description.textContent = panel.description || ""; panelTitle.replaceChildren(html("span", {class: "pv-panel-kind"}, KINDS[panel.kind] || panel.kind), html("strong", {}, panel.title));
      for (const [tabId, tab] of tabs) { tab.setAttribute("aria-selected", String(tabId === id)); tab.setAttribute("tabindex", tabId === id ? "0" : "-1"); }
      workspace.setAttribute("aria-labelledby", tabs.get(id).id); overview();
      [fitButton, readableButton, zoomOut, zoomIn, save].forEach(node => { node.disabled = true; });
      try {
        if (panel.kind === "graph") await renderGraph(panel, token);
        else if (panel.kind === "matrix") renderMatrix(panel);
        else if (panel.kind === "chart") renderChart(panel);
        else if (panel.kind === "timeline") renderTimeline(panel);
        else if (panel.kind === "chevron") renderChevron(panel);
        else if (panel.kind === "table") renderTable(panel);
        else throw new Error(`Unsupported panel kind: ${panel.kind}`);
        if (disposed || token !== generation) return;
        [fitButton, readableButton, zoomOut, zoomIn, save].forEach(node => { node.disabled = !currentSVG; });
        applySearch();
      } catch (error) {
        if (disposed || token !== generation) return;
        currentSVG = null; canvas.replaceChildren(html("div", {class: "pv-empty pv-error", role: "alert"}, `Unable to display this panel: ${error.message}`));
        setStatus("The supplied analysis is unchanged. No diagram was substituted.");
        throw error;
      }
    }
    function exportSVG() {
      if (!currentSVG) return null;
      const clone = currentSVG.cloneNode(true), width = Math.max(700, bounds.width);
      const notes = [{text: `${source.title} / ${current.title}`}, {text: `Analysis status: ${source.status || "ok"}`}, ...(current.description ? [{text: current.description}] : []), ...Array.from(legend.children).map(item => ({text: item.textContent, color: item.querySelectorAll(".pv-swatch")[0]?.style.backgroundColor})), {text: status.textContent}, ...(source.issues || []).map(issue => ({text: `Analysis note: ${issue}`}))];
      const lines = notes.flatMap(note => {
        const chars = Array.from(display(note.text)), result = [], length = Math.max(35, Math.floor((width - 70) / 7));
        for (let offset = 0; offset < chars.length; offset += length) result.push({text: chars.slice(offset, offset + length).join(""), color: offset === 0 ? note.color : null});
        return result;
      });
      lines.push({text: "PIX · Panel data and calculation provenance are embedded in SVG metadata."});
      const footerHeight = 42 + lines.length * 18;
      clone.setAttribute("viewBox", `${bounds.x} ${bounds.y} ${width} ${bounds.height + footerHeight}`); clone.setAttribute("width", width); clone.setAttribute("height", bounds.height + footerHeight);
      clone.prepend(svgNode("style", {}, SVG_STYLE + ".pv-chevron-label{font-size:12px;font-weight:600;fill:#253b49}.pv-chevron-shape{stroke-linejoin:round}.pv-mark.is-selected .pv-chevron-shape,.pv-mark:focus-visible .pv-chevron-shape{stroke:#163f51;stroke-width:3}.pv-chevron-lane-label{font-size:12px;font-weight:600}"));
      clone.append(svgNode("metadata", {}, JSON.stringify({schema: source.schema, title: source.title, status: source.status, issues: source.issues, provenance: source.provenance, panel: current})), svgNode("rect", {x: 0, y: bounds.height, width, height: footerHeight, fill: "#fff"}));
      lines.forEach((line, index) => { const y = bounds.height + 26 + index * 18; if (line.color) clone.append(svgNode("rect", {x: 24, y: y - 9, width: 10, height: 10, rx: 2, fill: line.color, class: "pv-export-swatch"})); clone.append(svgNode("text", {x: line.color ? 42 : 24, y, class: "pv-export-note"}, line.text)); });
      for (const node of clone.querySelectorAll("[tabindex]")) node.removeAttribute("tabindex");
      return new XMLSerializer().serializeToString(clone);
    }
    function download() {
      const content = exportSVG(); if (!content) return;
      const blob = new Blob([content], {type: "image/svg+xml;charset=utf-8"}), url = URL.createObjectURL(blob), link = html("a", {href: url, download: `${String(current.id).replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 100) || "pix-visualization"}.svg`});
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    const controller = {ready: null, selectPanel(id) { return (controller.ready = selectPanel(id)); }, fit, readable, exportSVG, dispose() { disposed = true; generation++; pointer = null; container.replaceChildren(); }};
    if (source.panels.length) renderPromise = selectPanel(options.panelId || source.panels[0].id);
    else { overview(); limitMessage("This document contains no visualization panels."); status.textContent = "No panels supplied."; [fitButton, readableButton, zoomOut, zoomIn, save].forEach(node => { node.disabled = true; }); renderPromise = Promise.resolve(); }
    controller.ready = renderPromise;
    return controller;
  }
  const api = {mount};
  root.PIXVisualization = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
