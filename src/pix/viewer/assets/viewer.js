/* PIX read-only SVG presentation. Every source string is inserted as text. */
(function (root) {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  let nextInstanceId = 0;
  const UNITS = {event_pairs: "Event pairs", unique_objects: "Unique objects", occurrences: "Object occurrences"};
  // Preserve original evidence in the document; replace XML-invalid display chars.
  const displayText = value => String(value).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f\ufffe\uffff]/gu, "\ufffd");
  function el(tag, attrs = {}, text) {
    const node = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    if (text !== undefined) node.textContent = displayText(text);
    return node;
  }
  function svgEl(tag, attrs = {}, text) {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, displayText(value)));
    if (text !== undefined) node.textContent = displayText(text);
    return node;
  }
  function button(label, action, title) {
    const node = el("button", {type: "button", title: title || label}, label);
    node.addEventListener("click", action);
    return node;
  }
  function activate(node, action) {
    node.addEventListener("click", action);
    node.addEventListener("keydown", event => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); }
    });
  }
  function clear(node) { node.replaceChildren(); }
  function infoPair(list, name, value, cls) {
    list.append(el("dt", {}, name), el("dd", cls ? {class: cls} : {}, value));
  }

  async function mount(container, graph, options = {}) {
    if (!container || !root.PIXLayout) throw new Error("Viewer container and PIX layout utilities are required");
    const L = root.PIXLayout;
    const instanceId = nextInstanceId++;
    const layout = options.layout || L.createElkLayout(new root.ELK());
    const hidden = new Set();
    const source = structuredClone(graph);
    const isModel = source.kind === "petri_net" || source.kind === "ocpn";
    const nodeMap = new Map(source.nodes.map(node => [node.id, node]));
    const edgeMap = new Map(source.edges.map(edge => [edge.id, edge]));
    const nodeEls = new Map(), edgeEls = new Map(), edgeLabels = new Map();
    const positions = new Map();
    let unit = isModel ? null : "event_pairs", selected = null, evidencePage = 0, disposed = false;
    let bounds = {x: 0, y: 0, width: 500, height: 300}, view = {...bounds};
    let graphWidth = 500, graphHeight = 300;
    clear(container);
    const app = el("div", {class: "pix-app"});
    const header = el("header", {class: "pix-header"});
    const heading = el("div", {class: "pix-heading"});
    heading.append(el("h1", {}, source.title), el("p", {class: "pix-eyebrow"}, isModel ? `${source.kind === "ocpn" ? "Object-centric Petri net" : "Petri net"} · executable model · origin ${source.origin}` : `${source.kind.toUpperCase()} · observed directly-follows relations`));
    header.append(el("div", {class: "pix-wordmark", "aria-label": "PIX"}, "PIX"), heading);
    const toolbar = el("div", {class: "pix-topbar"});
    const controls = el("div", {class: "pix-controls"});
    const unitLabel = el("label", {}, "Edge count ");
    const select = el("select", {"aria-label": "Edge counting unit"});
    Object.entries(UNITS).forEach(([value, label]) => select.append(el("option", {value}, label)));
    unitLabel.append(select);
    const saveButton = button("Save SVG", download, "Download current graph view as SVG");
    saveButton.disabled = true;
    if (!isModel) controls.append(unitLabel);
    controls.append(button("Fit", fit, "Fit all nodes (0)"), button("Readable", readable, "Show labels at their designed size; pan to explore the full graph"), button("−", () => zoom(1.25), "Zoom out (−)"), button("+", () => zoom(0.8), "Zoom in (+)"), button("Reset", reset, "Show all types, clear selection and fit"), saveButton);
    const status = el("div", {class: "pix-status", role: "status", "aria-live": "polite"}, "Computing layout…");
    toolbar.append(controls, status);
    const main = el("main", {class: "pix-main"});
    const canvasWrap = el("section", {class: "pix-canvas-wrap", "aria-label": "Process graph"});
    const svg = svgEl("svg", {class: "pix-graph", tabindex: "0", role: "group", "aria-label": "Interactive process graph. Tab to select nodes and edges. Arrow keys pan, plus and minus zoom, zero fits."});
    const svgTitle = svgEl("title", {}, source.title);
    const svgDesc = svgEl("desc", {}, isModel ? "Executable model. Circles are places, rectangles visible transitions, dark bars silent transitions. Filled tokens show the initial marking; a double ring indicates a nonzero final marking. Arc constraints are not observed frequencies." : "Observed directly-follows relations. Counts refer to the explicitly selected unit. Hidden object types do not alter the analysis or node totals.");
    const defs = svgEl("defs");
    const edgeLayer = svgEl("g", {class: "pix-edges"});
    const nodeLayer = svgEl("g", {class: "pix-nodes"});
    svg.append(svgTitle, svgDesc, defs, edgeLayer, nodeLayer);
    const message = el("div", {class: "pix-canvas-message", role: "status"});
    const help = el("div", {class: "pix-help"}, "Drag to pan · Scroll to zoom · Tab + Enter to inspect");
    canvasWrap.append(svg, message, help);
    const inspector = el("aside", {class: "pix-inspector", "aria-label": "Selection details"});
    main.append(canvasWrap, inspector);
    const legend = el("div", {class: "pix-legend", role: "group", "aria-label": "Object type visibility"});
    legend.append(el("span", {class: "pix-legend-title"}, source.object_types.length ? "Object types" : "Model notation"));
    const filters = new Map();
    source.object_types.forEach(type => {
      const label = el("label", {class: "pix-type"});
      const input = el("input", {type: "checkbox", "aria-label": `Show object type ${type}`});
      input.checked = true;
      input.addEventListener("change", () => { input.checked ? hidden.delete(type) : hidden.add(type); applyVisibility(); });
      const swatch = el("span", {class: "pix-type-swatch", "aria-hidden": "true"});
      swatch.style.backgroundColor = L.typeColor(type);
      label.append(input, swatch, el("span", {}, type));
      legend.append(label); filters.set(type, input);
    });
    legend.append(el("span", {class: "pix-filter-note"}, isModel ? "View filters only · initial/final markings stay fixed · arc width is not frequency" : "View filters only · node totals stay fixed"));
    if (source.kind === "ocpn") legend.append(el("span", {class: "pix-filter-note"}, "Dashed arc = variable object cardinality"));
    app.append(header, toolbar, main, legend); container.append(app);
    showOverview();

    function updateView() {
      svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.width} ${view.height}`);
      const scale = svg.getBoundingClientRect().width / view.width;
      help.textContent = scale < .7 ? "Overview scale · Use Readable for labels · Drag to pan" : "Drag to pan · Scroll to zoom · Tab + Enter to inspect";
    }
    function readable() {
      const box = svg.getBoundingClientRect();
      if (!box.width || !box.height) return;
      const focus = selected?.kind === "node" ? positions.get(selected.id) : null;
      const cx = focus ? focus.x + focus.width / 2 : view.x + view.width / 2;
      const cy = focus ? focus.y + focus.height / 2 : view.y + view.height / 2;
      view = {x: cx - box.width / 2, y: cy - box.height / 2, width: box.width, height: box.height};
      updateView();
    }
    function fit() {
      const box = svg.getBoundingClientRect();
      const ratio = box.width > 0 && box.height > 0 ? box.width / box.height : 1.5;
      let width = graphWidth + 64, height = graphHeight + 64;
      if (width / height < ratio) width = height * ratio; else height = width / ratio;
      bounds = {x: (graphWidth - width) / 2, y: (graphHeight - height) / 2, width, height};
      view = {...bounds}; updateView();
    }
    function zoom(factor, ax = 0.5, ay = 0.5) {
      const width = Math.min(bounds.width * 8, Math.max(bounds.width / 12, view.width * factor));
      const actual = width / view.width;
      view = {x: view.x + view.width * ax * (1 - actual), y: view.y + view.height * ay * (1 - actual), width, height: view.height * actual};
      updateView();
    }
    function reset() { hidden.clear(); filters.forEach(input => {input.checked = true;}); unit = isModel ? null : "event_pairs"; select.value = unit; selected = null; applyVisibility(); updateLabels(); showOverview(); fit(); }
    function updateStatus() { status.textContent = `${source.nodes.length} ${isModel ? "model nodes" : "activities"} · ${L.visibleEdges(source, hidden).length} of ${source.edges.length} ${isModel ? "arcs" : "edges"} visible · ${source.edges.filter(edge => hidden.has(edge.object_type)).length} hidden`; }
    function applyVisibility() {
      edgeEls.forEach((node, id) => {
        const hide = hidden.has(edgeMap.get(id).object_type);
        node.toggleAttribute("hidden", hide);
        node.setAttribute("tabindex", hide ? "-1" : "0");
        node.setAttribute("aria-hidden", String(hide));
      });
      if (selected?.kind === "edge" && hidden.has(edgeMap.get(selected.id).object_type)) { selected = null; showOverview(); }
      updateSelection(); updateStatus();
    }
    function updateSelection() {
      nodeEls.forEach((node, id) => node.classList.toggle("is-selected", selected?.kind === "node" && selected.id === id));
      edgeEls.forEach((node, id) => node.classList.toggle("is-selected", selected?.kind === "edge" && selected.id === id));
    }
    function updateLabels() {
      if (isModel) return;
      edgeLabels.forEach((label, id) => { const edge = edgeMap.get(id); label.count.textContent = L.edgeCount(edge, unit); edgeEls.get(id).setAttribute("aria-label", displayText(`${nodeMap.get(edge.source).label} to ${nodeMap.get(edge.target).label}, ${edge.object_type}, ${L.edgeCount(edge, unit)} ${UNITS[unit]}`)); });
      svgDesc.textContent = `Observed directly-follows relations. Edge labels count ${UNITS[unit].toLowerCase()}. Hidden object types do not alter analysis or node totals.`;
    }
    function showOverview() {
      clear(inspector);
      if (isModel) {
        inspector.append(el("span", {class: "pix-tag"}, "READ-ONLY MODEL"), el("h2", {}, "Inspect model semantics"), el("p", {}, "Circles are places; rectangles are visible transitions; dark bars are silent transitions. Initial tokens appear inside places. A double ring marks a nonzero final marking; exact initial and final counts are shown below each place."));
        const notes = el("ul"); source.notes.forEach(note => notes.append(el("li", {}, note))); inspector.append(notes);
        const details = el("dl");
        infoPair(details, "Declared origin", source.origin);
        infoPair(details, "Model digest", source.model_digest, "pix-source");
        infoPair(details, "Source computation", source.source_computation_id || "Not declared", "pix-source");
        inspector.append(el("h3", {}, "Model provenance"), details);
        if (source.kind === "ocpn") {
          inspector.append(el("h3", {}, "Binding universe"), el("p", {}, `${source.objects.length} concrete object IDs are declared. Bindings select these objects; firing cannot create new object IDs. Multiple tokens for the same object remain distinct token occurrences.`));
          const universe = el("details"), list = el("ul");
          universe.append(el("summary", {}, "Declared objects"));
          source.objects.slice(0, 100).forEach(([id, type]) => list.append(el("li", {}, `${id} · ${type}`)));
          universe.append(list);
          if (source.objects.length > 100) universe.append(el("p", {}, "First 100 shown. The full finite universe is retained in HTML data."));
          inspector.append(universe);
        }
        inspector.append(el("p", {class: "pix-muted"}, "This view displays structural execution semantics. It is not a soundness, boundedness or log-conformance certificate."));
        return;
      }
      inspector.append(el("span", {class: "pix-tag"}, "READ-ONLY ANALYSIS"), el("h2", {}, "Follow the evidence"), el("p", {}, "Select an edge to inspect its event pairs, participating objects and original relation qualifiers. Select an activity to see its source events and objects."));
      const notes = el("ul"); source.notes.forEach(note => notes.append(el("li", {}, note))); inspector.append(notes);
      const details = el("dl");
      infoPair(details, "Source canonical digest", source.source_digest, "pix-source");
      infoPair(details, "Computation", source.computation_id, "pix-source");
      inspector.append(el("h3", {}, "Provenance"), details, el("p", {class: "pix-muted"}, "This HTML includes all displayed analysis evidence, including types hidden in the view."));
    }
    function showNode(id) {
      selected = {kind: "node", id}; updateSelection(); clear(inspector);
      const node = nodeMap.get(id);
      if (isModel) { showModelNode(node); return; }
      inspector.append(el("span", {class: "pix-tag"}, "ACTIVITY"), el("h2", {}, node.label), el("p", {}, `${node.event_count} distinct source events · ${node.object_count} distinct source objects. Totals cover the original analysis, including hidden types.`));
      [ ["Event IDs", node.event_ids], ["Object IDs", node.object_ids] ].forEach(([label, values]) => {
        const details = el("details"), list = el("ul");
        values.slice(0, 100).forEach(value => list.append(el("li", {}, value)));
        details.append(el("summary", {}, `${label} (${values.length})`), list);
        if (values.length > 100) details.append(el("p", {}, "First 100 shown. Full source references remain in the HTML data."));
        inspector.append(details);
      });
    }
    function showEdge(id, page = 0) {
      selected = {kind: "edge", id}; evidencePage = page; updateSelection(); clear(inspector);
      const edge = edgeMap.get(id);
      if (isModel) { showModelEdge(edge); return; }
      inspector.append(el("span", {class: "pix-tag"}, edge.object_type), el("h2", {}, `${nodeMap.get(edge.source).label} → ${nodeMap.get(edge.target).label}`));
      const metrics = el("div", {class: "pix-metrics"});
      Object.entries(UNITS).forEach(([key, label]) => { const tile = el("div", {class: "pix-metric"}); tile.append(el("strong", {}, edge.counts[key]), el("span", {}, label)); metrics.append(tile); });
      inspector.append(metrics, el("p", {}, "An occurrence is one adjacent event pair for one object. A shared event pair can contribute several object occurrences."), el("h3", {}, "Source evidence"));
      const table = el("table", {class: "pix-evidence"});
      const head = el("tr"); ["From event", "To event", "Object"].forEach(label => head.append(el("th", {scope: "col"}, label)));
      const thead = el("thead"); thead.append(head); const tbody = el("tbody");
      const pageSize = 40, maxPage = Math.max(0, Math.ceil(edge.evidence.length / pageSize) - 1);
      edge.evidence.slice(page * pageSize, (page + 1) * pageSize).forEach(item => {
        const row = el("tr");
        [[item.source_event_id, item.source_qualifiers], [item.target_event_id, item.target_qualifiers], [item.object_id, null]].forEach(([idValue, qualifiers]) => {
          const cell = el("td", {}, idValue);
          if (qualifiers) { const detail = el("details"); detail.append(el("summary", {}, "Roles"), el("small", {}, qualifiers.length ? qualifiers.map(value => JSON.stringify(value)).join(", ") : "No qualifier evidence")); cell.append(detail); }
          row.append(cell);
        }); tbody.append(row);
      });
      table.append(thead, tbody); inspector.append(table);
      const pager = el("div", {class: "pix-pages"});
      const prev = button("Previous", () => showEdge(id, Math.max(0, evidencePage - 1)));
      const next = button("Next", () => showEdge(id, Math.min(maxPage, evidencePage + 1)));
      prev.disabled = page === 0; next.disabled = page === maxPage;
      pager.append(prev, el("span", {}, `${page + 1} / ${maxPage + 1}`), next); inspector.append(pager);
    }
    function showModelNode(node) {
      inspector.append(el("span", {class: "pix-tag"}, node.kind === "silent" ? "SILENT TRANSITION" : node.kind.toUpperCase()), el("h2", {}, node.label));
      const details = el("dl"); infoPair(details, "Stable model node ID", node.model_node_id);
      if (node.object_type !== null) infoPair(details, "Object type", node.object_type);
      if (node.kind === "place") {
        infoPair(details, "Initial token count", node.initial_count);
        infoPair(details, "Final token count", node.final_count);
        inspector.append(details);
        if (source.kind === "ocpn") {
          [["Initial object tokens", node.initial_objects], ["Final object tokens", node.final_objects]].forEach(([title, ids]) => {
            inspector.append(el("h3", {}, title));
            if (!ids.length) { inspector.append(el("p", {}, "Empty marking at this place.")); return; }
            const counts = new Map(); ids.forEach(value => counts.set(value, (counts.get(value) || 0) + 1));
            const list = el("ul"); [...counts].forEach(([value, count]) => list.append(el("li", {}, `${value} × ${count}`))); inspector.append(list);
          });
        }
      } else {
        infoPair(details, "Activity", node.kind === "silent" ? "None (silent)" : node.label);
        inspector.append(details, el("p", {}, "Activity labels do not identify transitions. Transitions with the same displayed activity remain separate nodes."));
        if (source.kind === "ocpn") {
          inspector.append(el("h3", {}, "Binding cardinality by type"));
          const policies = new Map();
          source.edges.filter(edge => edge.source === node.id || edge.target === node.id).forEach(edge => policies.set(edge.object_type, edge));
          const list = el("ul"); policies.forEach((edge, type) => list.append(el("li", {}, `${type}: ${L.modelEdgeLabel(edge, source.kind)}. One shared object set applies to every incident arc of this transition/type.`)));
          inspector.append(list);
          if (!policies.size) inspector.append(el("p", {}, "No incident object types; the binding has no object sets."));
        }
      }
    }
    function showModelEdge(edge) {
      const from = nodeMap.get(edge.source), to = nodeMap.get(edge.target);
      inspector.append(el("span", {class: "pix-tag"}, edge.object_type || "WEIGHTED ARC"), el("h2", {}, `${from.label} → ${to.label}`));
      const details = el("dl");
      infoPair(details, "From model node", from.model_node_id); infoPair(details, "To model node", to.model_node_id);
      if (source.kind === "ocpn") {
        infoPair(details, "Object type", edge.object_type);
        infoPair(details, "Arc kind", edge.variable ? "Variable object cardinality" : "Fixed: exactly one object");
        infoPair(details, "Minimum bound objects", edge.min_objects);
        infoPair(details, "Maximum bound objects", edge.max_objects === null ? "No arc upper bound; constrained by the declared finite universe" : edge.max_objects);
        inspector.append(details, el("p", {}, "Each selected object contributes one token on this incidence. Every incident arc for this transition and object type uses the same selected object set."));
        if (edge.variable && edge.min_objects === 0) inspector.append(el("p", {}, "The empty object set is explicitly allowed for this type."));
      } else {
        infoPair(details, "Token weight", edge.weight);
        inspector.append(details, el("p", {}, `A firing ${from.kind === "place" ? "consumes" : "produces"} ${edge.weight} tokens ${from.kind === "place" ? "from" : "at"} this place.`));
      }
      inspector.append(el("p", {class: "pix-muted"}, "These are model constraints, not event counts or observed frequencies."));
    }
    function download() {
      const copy = svg.cloneNode(true);
      copy.setAttribute("xmlns", NS); copy.setAttribute("width", graphWidth + 64); copy.setAttribute("height", graphHeight + 64);
      copy.setAttribute("viewBox", `-32 -32 ${graphWidth + 64} ${graphHeight + 64}`);
      copy.removeAttribute("tabindex"); copy.removeAttribute("class"); copy.setAttribute("style", "background:#f7f8f6");
      const style = svgEl("style"); style.textContent = document.querySelector("style")?.textContent || ""; copy.prepend(style);
      const metadata = svgEl("metadata", {}, JSON.stringify(isModel ? {model_digest: source.model_digest, origin: source.origin, source_computation_id: source.source_computation_id, hidden_object_types: [...hidden], selection: selected, model_notes: source.notes} : {source_digest: source.source_digest, computation_id: source.computation_id, counting_unit: unit, hidden_object_types: [...hidden], selection: selected, analysis_notes: source.notes}));
      copy.append(metadata);
      const xml = new XMLSerializer().serializeToString(copy);
      const url = URL.createObjectURL(new Blob([xml], {type: "image/svg+xml;charset=utf-8"}));
      const link = el("a", {href: url, download: isModel ? "pix-process-model.svg" : "pix-process-graph.svg"}); document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    select.addEventListener("change", () => { unit = select.value; updateLabels(); });
    svg.addEventListener("wheel", event => {
      event.preventDefault(); const rect = svg.getBoundingClientRect();
      zoom(Math.exp(Math.max(-200, Math.min(200, event.deltaY)) * .003), (event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.height);
    }, {passive: false});
    let pan = null;
    svg.addEventListener("pointerdown", event => {
      if (event.button !== 0 || event.target.closest(".pix-node,.pix-edge")) return;
      const rect = svg.getBoundingClientRect();
      pan = {x: event.clientX, y: event.clientY, view: {...view}, width: rect.width, height: rect.height, id: event.pointerId};
      svg.setPointerCapture(event.pointerId); svg.classList.add("is-panning");
    });
    svg.addEventListener("pointermove", event => {
      if (!pan) return;
      view = {...pan.view, x: pan.view.x - (event.clientX - pan.x) / pan.width * pan.view.width, y: pan.view.y - (event.clientY - pan.y) / pan.height * pan.view.height}; updateView();
    });
    const stopPan = () => { pan = null; svg.classList.remove("is-panning"); };
    svg.addEventListener("pointerup", stopPan); svg.addEventListener("pointercancel", stopPan); svg.addEventListener("lostpointercapture", stopPan);
    svg.addEventListener("keydown", event => {
      if (event.target !== svg) return;
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "+", "=", "-", "0"].includes(event.key)) event.preventDefault();
      if (event.key === "+" || event.key === "=") zoom(.8);
      if (event.key === "-") zoom(1.25);
      if (event.key === "0") fit();
      if (event.key === "ArrowLeft") view.x -= view.width * .08;
      if (event.key === "ArrowRight") view.x += view.width * .08;
      if (event.key === "ArrowUp") view.y -= view.height * .08;
      if (event.key === "ArrowDown") view.y += view.height * .08;
      updateView();
    });

    try {
      const positioned = await layout(source);
      if (disposed) return;
      graphWidth = Math.max(1, positioned.width || 0); graphHeight = Math.max(1, positioned.height || 0);
      (positioned.edges || []).forEach((route, routeIndex) => {
        const edge = edgeMap.get(route.id); if (!edge) return;
        const color = edge.object_type === null ? "#637681" : L.typeColor(edge.object_type), markerId = `pix-${instanceId}-arrow-${routeIndex}`;
        const marker = svgEl("marker", {id: markerId, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 8, markerHeight: 8, orient: "auto", markerUnits: "userSpaceOnUse"});
        marker.append(svgEl("path", {d: "M 0 1 L 9 5 L 0 9 z", fill: color})); defs.append(marker);
        const group = svgEl("g", {class: "pix-edge" + (isModel && edge.variable ? " pix-variable-arc" : ""), tabindex: 0, role: "button", "data-edge-id": edge.id});
        const edgeDescription = `${nodeMap.get(edge.source).label} → ${nodeMap.get(edge.target).label}${edge.object_type === null ? "" : " · " + edge.object_type}${isModel ? " · " + L.modelEdgeLabel(edge, source.kind) : ""}`;
        group.append(svgEl("title", {}, edgeDescription));
        if (isModel) { group.setAttribute("data-variable", String(edge.variable)); group.setAttribute("aria-label", displayText(edgeDescription)); }
        const path = L.sectionPath(route);
        group.append(svgEl("path", {class: "pix-edge-hit", d: path}), svgEl("path", {class: "pix-edge-line", d: path, stroke: color, "marker-end": `url(#${markerId})`}));
        const label = (route.labels || [])[0];
        if (label) {
          const text = svgEl("text", {class: "pix-edge-label", x: label.x + label.width / 2, y: label.y + 11, "text-anchor": "middle", fill: color});
          if (isModel) {
            const lines = route.labelLines || [L.modelEdgeLabel(edge, source.kind)];
            lines.forEach((line, index) => text.append(svgEl("tspan", {x: label.x + label.width / 2, dy: index ? 15 : 0}, line)));
            text.classList.add("pix-model-constraint"); group.append(text);
          } else {
            const typeLine = svgEl("tspan", {x: label.x + label.width / 2}, L.wrapLabel(edge.object_type, 21, 1)[0] || "");
            const count = svgEl("tspan", {x: label.x + label.width / 2, dy: 14}, edge.counts[unit]);
            text.append(typeLine, count); group.append(text); edgeLabels.set(edge.id, {count});
          }
        }
        activate(group, () => showEdge(edge.id)); edgeLayer.append(group); edgeEls.set(edge.id, group);
      });
      (positioned.children || []).forEach(position => {
        const node = nodeMap.get(position.id); if (!node) return;
        positions.set(node.id, position);
        if (isModel) { renderModelNode(node, position); return; }
        const group = svgEl("g", {class: "pix-node", transform: `translate(${position.x},${position.y})`, tabindex: 0, role: "button", "data-node-id": node.id, "aria-label": `${node.label}, ${node.event_count} source events, ${node.object_count} source objects`});
        group.append(svgEl("title", {}, node.label), svgEl("rect", {width: position.width, height: position.height, rx: 9}));
        const lines = L.wrapLabel(node.label, 26, 4);
        const label = svgEl("text", {class: "pix-node-label", x: position.width / 2, y: 24, "text-anchor": "middle"});
        lines.forEach((line, index) => label.append(svgEl("tspan", {x: position.width / 2, dy: index ? 17 : 0}, line)));
        group.append(label, svgEl("text", {class: "pix-node-meta", x: position.width / 2, y: position.height - 13, "text-anchor": "middle"}, `${node.event_count} events · ${node.object_count} objects`));
        activate(group, () => showNode(node.id)); nodeLayer.append(group); nodeEls.set(node.id, group);
      });
      if (!source.nodes.length) message.append(el("h2", {}, isModel ? "No model nodes" : "No activity nodes"), el("p", {}, isModel ? "This model has no places or transitions. Its declared origin and model identity remain available." : "The selected analysis contains no event occurrences. Empty objects are retained in the analysis result."));
      else if (!source.edges.length) message.append(el("p", {}, isModel ? "This model contains no arcs. Unlinked nodes remain visible." : "No directly-follows edges in this analysis."));
      updateLabels(); applyVisibility(); fit();
      saveButton.disabled = false;
    } catch (error) {
      status.textContent = "Layout unavailable";
      message.append(el("h2", {}, "Graph layout could not be computed"), el("p", {}, error.message || error));
      throw error;
    }
    function renderModelNode(node, position) {
      const shape = position.shape;
      const group = svgEl("g", {class: `pix-node pix-model-node pix-model-${node.kind}`, transform: `translate(${position.x},${position.y})`, tabindex: 0, role: "button", "data-node-id": node.id, "data-node-kind": node.kind, "data-model-node-id": node.model_node_id, "aria-label": `${node.kind} ${node.label}, model node ${node.model_node_id}${node.kind === "place" ? `, initial ${node.initial_count} tokens, final ${node.final_count} tokens` : ""}`});
      const color = node.object_type === null ? "#566e7b" : L.typeColor(node.object_type);
      group.append(svgEl("title", {}, `${node.label} · model node ${node.model_node_id}`));
      if (node.kind === "place") {
        group.append(svgEl("circle", {class: "pix-place-shape", cx: shape.cx, cy: shape.cy, r: shape.radius, stroke: color}));
        if (node.final_count > 0) group.append(svgEl("circle", {class: "pix-final-ring", cx: shape.cx, cy: shape.cy, r: shape.radius - 5, stroke: color}));
        if (node.initial_count > 3) {
          group.append(svgEl("text", {class: "pix-token-count", x: shape.cx, y: shape.cy + 4, "text-anchor": "middle"}, node.initial_count));
        } else {
          const tokenOffsets = node.initial_count === 1 ? [[0, 0]] : node.initial_count === 2 ? [[-5, 0], [5, 0]] : node.initial_count === 3 ? [[0, -5], [-5, 4], [5, 4]] : [];
          tokenOffsets.forEach(([x, y]) => group.append(svgEl("circle", {class: "pix-initial-token", cx: shape.cx + x, cy: shape.cy + y, r: 3})));
        }
      } else {
        group.append(svgEl("rect", {class: node.kind === "silent" ? "pix-silent-shape" : "pix-transition-shape", x: shape.x, y: shape.y, width: shape.width, height: shape.height, rx: node.kind === "silent" ? 1 : 3}));
      }
      const label = svgEl("text", {class: "pix-node-label", x: position.width / 2, y: position.labelY, "text-anchor": "middle"});
      position.labelLines.forEach((line, index) => label.append(svgEl("tspan", {x: position.width / 2, dy: index ? 17 : 0}, line)));
      group.append(label);
      if (node.kind === "place") {
        const type = svgEl("text", {class: "pix-node-type", x: position.width / 2, y: position.typeLabelY, "text-anchor": "middle", fill: color});
        (position.typeLabelLines || []).forEach((line, index) => type.append(svgEl("tspan", {x: position.width / 2, dy: index ? 15 : 0}, line)));
        group.append(type, svgEl("text", {class: "pix-node-meta pix-marking-count", x: position.width / 2, y: position.markingY, "text-anchor": "middle"}, `I: ${node.initial_count} · F: ${node.final_count}`));
      }
      activate(group, () => showNode(node.id)); nodeLayer.append(group); nodeEls.set(node.id, group);
    }
    const observer = new ResizeObserver(() => { if (!disposed) fit(); }); observer.observe(canvasWrap);
    return {
      getViewState: () => ({unit, hiddenObjectTypes: [...hidden], selected: selected && {...selected}, viewBox: {...view}}),
      getGraph: () => structuredClone(source),
      destroy: () => { disposed = true; observer.disconnect(); clear(container); },
    };
  }
  root.PIXViewer = Object.freeze({mount, displayText});
  if (typeof document !== "undefined") {
    const data = document.getElementById("pix-graph-data");
    if (data) {
      root.pixViewerReady = mount(document.getElementById("pix-viewer"), JSON.parse(data.textContent))
        .then(viewer => {root.pixViewer = viewer; return viewer;});
      // Displayed error remains available; suppress only unhandled-promise noise.
      root.pixViewerReady.catch(() => {});
    }
  }
})(typeof window !== "undefined" ? window : globalThis);
