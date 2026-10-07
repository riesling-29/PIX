/* PIX native graph geometry. No DOM, Graphviz, ELK, random seed, or dependencies.
 * layered: SCC condensation / longest-path ranks; tree: directed BFS forest.
 * bipartite: graph coloring when possible, explicit kind fallback on odd cycles.
 * force: fixed-step spring/repulsion, then deterministic rectangle separation.
 * Column layouts avoid node interiors with intercolumn and outer edge corridors.
 * Force edges are clipped polylines, not an obstacle-avoiding edge router.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PIXNativeGeometry = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  const byId = (a, b) => compare(a.id, b.id);
  const padding = 40;

  function typeColor(type) {
    if (typeof type !== "string") throw new TypeError("Type must be a string");
    let hash = 2166136261;
    for (const point of type) {
      hash ^= point.codePointAt(0);
      hash = Math.imul(hash, 16777619) >>> 0;
    }
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
          if (/\s/u.test(remaining[i])) { split = i; break; }
        }
        lines.push(remaining.slice(0, split).join("").trimEnd());
        remaining = remaining.slice(split);
        while (remaining.length && /\s/u.test(remaining[0])) remaining.shift();
        if (lines.length > maxLines) break;
      }
      if (lines.length > maxLines) break;
    }
    if (lines.length <= maxLines) return lines;
    const shortened = lines.slice(0, maxLines);
    shortened[maxLines - 1] = Array.from(shortened[maxLines - 1]).slice(0, max - 1).join("").trimEnd() + "\u2026";
    return shortened;
  }

  function dimensions(node) {
    const lines = wrapLabel(node.label);
    const labelWidth = Math.max(0, ...lines.map(line => Array.from(line).reduce((sum, char) =>
      sum + (char.codePointAt(0) >= 0x2e80 ? 14 : 8.7), 0)));
    return { id: node.id, width: Math.max(node.kind === "place" ? 80 : 110, labelWidth + 32),
      height: Math.max(56, lines.length * 18 + 24), x: 0, y: 0 };
  }

  function validated(graph, options) {
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
      throw new TypeError("Graph nodes and edges must be arrays");
    }
    if (!options || typeof options !== "object" || Array.isArray(options)) throw new TypeError("Options must be an object");
    const direction = options.direction === undefined ? "LR" : options.direction;
    const mode = options.layout === undefined ? (graph.layout === undefined ? "layered" : graph.layout) : options.layout;
    if (!["LR", "TB"].includes(direction)) throw new RangeError("Direction must be LR or TB");
    if (!["layered", "tree", "force", "bipartite"].includes(mode)) throw new RangeError("Unknown native layout");
    const nodeIds = new Set(), edgeIds = new Set();
    const assertId = (id, kind) => {
      if (typeof id !== "string" || id.length === 0) throw new TypeError(`${kind} ID must be a nonempty string`);
    };
    for (const node of graph.nodes) {
      if (!node || typeof node !== "object") throw new TypeError("Invalid node");
      assertId(node.id, "Node");
      if (nodeIds.has(node.id)) throw new TypeError(`Duplicate node ID: ${node.id}`);
      if (typeof node.label !== "string") throw new TypeError("Node label must be a string");
      nodeIds.add(node.id);
    }
    for (const edge of graph.edges) {
      if (!edge || typeof edge !== "object") throw new TypeError("Invalid edge");
      assertId(edge.id, "Edge");
      assertId(edge.source, "Source");
      assertId(edge.target, "Target");
      if (edgeIds.has(edge.id)) throw new TypeError(`Duplicate edge ID: ${edge.id}`);
      if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) throw new TypeError(`Dangling edge: ${edge.id}`);
      edgeIds.add(edge.id);
    }
    return { nodes: graph.nodes.slice().sort(byId), edges: graph.edges.slice().sort(byId), direction, mode };
  }

  function adjacency(nodes, edges) {
    const forward = new Map(nodes.map(n => [n.id, new Set()]));
    const reverse = new Map(nodes.map(n => [n.id, new Set()]));
    for (const edge of edges) {
      forward.get(edge.source).add(edge.target);
      reverse.get(edge.target).add(edge.source);
    }
    const ordered = map => new Map([...map].map(([id, neighbors]) => [id, [...neighbors].sort(compare)]));
    return { forward: ordered(forward), reverse: ordered(reverse) };
  }

  // Iterative Kosaraju prevents call-stack overflow on long process chains.
  function layeredRanks(nodes, edges) {
    const { forward, reverse } = adjacency(nodes, edges);
    const visited = new Set(), finish = [];
    for (const node of nodes) {
      if (visited.has(node.id)) continue;
      visited.add(node.id);
      const stack = [{ id: node.id, next: 0 }];
      while (stack.length) {
        const frame = stack[stack.length - 1], targets = forward.get(frame.id);
        if (frame.next < targets.length) {
          const target = targets[frame.next++];
          if (!visited.has(target)) { visited.add(target); stack.push({ id: target, next: 0 }); }
        } else { finish.push(frame.id); stack.pop(); }
      }
    }
    const component = new Map(), groups = [];
    for (let i = finish.length - 1; i >= 0; i--) {
      const start = finish[i];
      if (component.has(start)) continue;
      const index = groups.length, group = [], stack = [start];
      component.set(start, index);
      while (stack.length) {
        const id = stack.pop(); group.push(id);
        for (const previous of reverse.get(id)) {
          if (!component.has(previous)) { component.set(previous, index); stack.push(previous); }
        }
      }
      groups.push(group.sort(compare));
    }
    const successors = groups.map(() => new Set()), incoming = groups.map(() => 0), ranks = groups.map(() => 0);
    for (const edge of edges) {
      const source = component.get(edge.source), target = component.get(edge.target);
      if (source !== target && !successors[source].has(target)) { successors[source].add(target); incoming[target]++; }
    }
    const queue = incoming.flatMap((count, index) => count === 0 ? [index] : []);
    for (let next = 0; next < queue.length; next++) {
      const index = queue[next];
      for (const target of successors[index]) {
        ranks[target] = Math.max(ranks[target], ranks[index] + 1);
        if (--incoming[target] === 0) queue.push(target);
      }
    }
    return new Map(nodes.map(node => [node.id, ranks[component.get(node.id)]]));
  }

  function treeRanks(nodes, edges) {
    const { forward, reverse } = adjacency(nodes, edges), ranks = new Map();
    const roots = nodes.filter(node => reverse.get(node.id).length === 0).concat(nodes);
    for (const root of roots) {
      if (ranks.has(root.id)) continue;
      ranks.set(root.id, 0);
      const queue = [root.id];
      for (let next = 0; next < queue.length; next++) {
        const id = queue[next];
        for (const target of forward.get(id)) {
          if (!ranks.has(target)) { ranks.set(target, ranks.get(id) + 1); queue.push(target); }
        }
      }
    }
    return ranks;
  }

  function bipartiteRanks(nodes, edges) {
    const neighbors = new Map(nodes.map(n => [n.id, new Set()]));
    for (const edge of edges) {
      neighbors.get(edge.source).add(edge.target); neighbors.get(edge.target).add(edge.source);
    }
    const ranks = new Map();
    const left = new Set(["object", "place", "resource", "case", "object_type"]);
    const preferred = node => left.has(node.kind) ? 0 : 1;
    const byName = new Map(nodes.map(n => [n.id, n]));
    for (const node of nodes) {
      if (ranks.has(node.id)) continue;
      ranks.set(node.id, preferred(node));
      const queue = [node.id], component = [], conflicts = [];
      for (let next = 0; next < queue.length; next++) {
        const id = queue[next]; component.push(id);
        for (const target of [...neighbors.get(id)].sort(compare)) {
          if (!ranks.has(target)) { ranks.set(target, 1 - ranks.get(id)); queue.push(target); }
          else if (ranks.get(target) === ranks.get(id)) conflicts.push(target);
        }
      }
      // An odd cycle cannot have a valid graph bipartition. Keep all edges and
      // use declared kinds as a two-column presentation, never drop constraints.
      if (conflicts.length) for (const id of component) ranks.set(id, preferred(byName.get(id)));
    }
    return ranks;
  }

  function columns(nodes, ranks) {
    const layers = new Map();
    for (const node of nodes) {
      const rank = ranks.get(node.id);
      if (!layers.has(rank)) layers.set(rank, []);
      layers.get(rank).push(node);
    }
    const geometry = new Map(), gap = 100;
    let x = 0;
    for (const rank of [...layers.keys()].sort((a, b) => a - b)) {
      const layer = layers.get(rank), width = layer.reduce((maximum, node) => Math.max(maximum, node.width), 0);
      let y = 0;
      for (const node of layer) { node.x = x + (width - node.width) / 2; node.y = y; y += node.height + 54; }
      geometry.set(rank, { x, width, gap });
      x += width + gap;
    }
    return geometry;
  }

  function separated(nodes, clearance = 24) {
    // Preserve the force solution where possible; later ID nodes move only if
    // necessary. Each move clears at least one previously placed rectangle.
    const placed = [];
    for (const node of nodes) {
      for (;;) {
        const collisions = placed.filter(other => node.x < other.x + other.width + clearance &&
          node.x + node.width + clearance > other.x && node.y < other.y + other.height + clearance &&
          node.y + node.height + clearance > other.y);
        if (!collisions.length) break;
        node.y = Math.max(...collisions.map(other => other.y + other.height + clearance));
      }
      placed.push(node);
    }
  }

  function forcePositions(nodes, edges) {
    const count = nodes.length;
    if (!count) return;
    if (count > 1000) throw new RangeError("Native force layout supports at most 1000 nodes; use layered layout for larger graphs");
    const index = new Map(nodes.map((node, i) => [node.id, i]));
    const radius = Math.max(140, Math.sqrt(count) * 85);
    const positions = nodes.map((_, i) => ({ x: radius * Math.cos(i * 2 * Math.PI / count),
      y: radius * Math.sin(i * 2 * Math.PI / count) }));
    const springPairs = new Map();
    for (const edge of edges) {
      const a = Math.min(index.get(edge.source), index.get(edge.target));
      const b = Math.max(index.get(edge.source), index.get(edge.target));
      if (a !== b) springPairs.set(`${a}:${b}`, [a, b]);
    }
    const iterations = 120;
    for (let iteration = 0; iteration < iterations; iteration++) {
      const delta = nodes.map(() => ({ x: 0, y: 0 }));
      for (let a = 0; a < count; a++) for (let b = a + 1; b < count; b++) {
        let dx = positions[a].x - positions[b].x, dy = positions[a].y - positions[b].y;
        if (Math.abs(dx) + Math.abs(dy) < 1e-9) { dx = a + 1; dy = -(b + 1); }
        const distance = Math.max(1, Math.hypot(dx, dy));
        const magnitude = 14000 / (distance * distance);
        const fx = dx / distance * magnitude, fy = dy / distance * magnitude;
        delta[a].x += fx; delta[a].y += fy; delta[b].x -= fx; delta[b].y -= fy;
      }
      for (const [a, b] of springPairs.values()) {
        const dx = positions[b].x - positions[a].x, dy = positions[b].y - positions[a].y;
        const distance = Math.max(1, Math.hypot(dx, dy));
        const rest = (Math.hypot(nodes[a].width, nodes[a].height) + Math.hypot(nodes[b].width, nodes[b].height)) / 2 + 70;
        const magnitude = (distance - rest) * 0.035;
        const fx = dx / distance * magnitude, fy = dy / distance * magnitude;
        delta[a].x += fx; delta[a].y += fy; delta[b].x -= fx; delta[b].y -= fy;
      }
      const step = 12 * (1 - iteration / iterations) + 0.5;
      for (let i = 0; i < count; i++) {
        delta[i].x -= positions[i].x * 0.002; delta[i].y -= positions[i].y * 0.002;
        const length = Math.max(1, Math.hypot(delta[i].x, delta[i].y));
        positions[i].x += delta[i].x / length * Math.min(length, step);
        positions[i].y += delta[i].y / length * Math.min(length, step);
      }
    }
    nodes.forEach((node, i) => { node.x = positions[i].x - node.width / 2; node.y = positions[i].y - node.height / 2; });
    separated(nodes);
  }

  function clipped(node, target) {
    const center = { x: node.x + node.width / 2, y: node.y + node.height / 2 };
    const dx = target.x - center.x, dy = target.y - center.y;
    if (dx === 0 && dy === 0) return { x: node.x + node.width, y: center.y };
    const scale = 1 / Math.max(Math.abs(dx) / (node.width / 2), Math.abs(dy) / (node.height / 2));
    return { x: center.x + dx * scale, y: center.y + dy * scale };
  }

  function routes(nodes, edges, ranks, columnGeometry) {
    const byName = new Map(nodes.map(node => [node.id, node]));
    const groups = new Map();
    for (const edge of edges) {
      const key = JSON.stringify([edge.source, edge.target].sort(compare));
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(edge.id);
    }
    return edges.map((edge, index) => {
      const source = byName.get(edge.source), target = byName.get(edge.target);
      const key = JSON.stringify([edge.source, edge.target].sort(compare)), group = groups.get(key);
      const position = group.indexOf(edge.id), fraction = (position + 1) / (group.length + 1);
      const sy = source.y + source.height * (0.2 + fraction * 0.6);
      const ty = target.y + target.height * (0.2 + fraction * 0.6);
      let points;
      if (columnGeometry) {
        const sourceRank = ranks.get(edge.source), targetRank = ranks.get(edge.target);
        const sourceColumn = columnGeometry.get(sourceRank), targetColumn = columnGeometry.get(targetRank);
        const exit = sourceColumn.x + sourceColumn.width + 20 + fraction * 60;
        if (edge.source === edge.target) {
          const top = source.y + source.height * (0.12 + fraction * 0.2);
          const bottom = source.y + source.height * (0.68 + fraction * 0.2);
          points = [{ x: source.x + source.width, y: top }, { x: exit, y: top },
            { x: exit, y: bottom }, { x: source.x + source.width, y: bottom }];
        } else if (sourceRank === targetRank) {
          points = [{ x: source.x + source.width, y: sy }, { x: exit, y: sy },
            { x: exit, y: ty }, { x: target.x + target.width, y: ty }];
        } else if (targetRank === sourceRank + 1) {
          points = [{ x: source.x + source.width, y: sy }, { x: exit, y: sy },
            { x: exit, y: ty }, { x: target.x, y: ty }];
        } else {
          const entry = targetColumn.x - 20 - fraction * 60, track = -30 - index * 14;
          points = [{ x: source.x + source.width, y: sy }, { x: exit, y: sy },
            { x: exit, y: track }, { x: entry, y: track }, { x: entry, y: ty }, { x: target.x, y: ty }];
        }
      } else if (edge.source === edge.target) {
        const extent = 24 + position * 16;
        points = [{ x: source.x + source.width, y: sy }, { x: source.x + source.width + extent, y: sy },
          { x: source.x + source.width + extent, y: source.y + source.height + extent },
          { x: source.x + source.width / 2, y: source.y + source.height + extent },
          { x: source.x + source.width / 2, y: source.y + source.height }];
      } else {
        const a = { x: source.x + source.width / 2, y: source.y + source.height / 2 };
        const b = { x: target.x + target.width / 2, y: target.y + target.height / 2 };
        if (group.length === 1) {
          points = [clipped(source, b), clipped(target, a)];
        } else {
          // Separated rectangles have a gap on at least one axis. Parallel
          // edges use that guaranteed channel, since merely putting a curved
          // midpoint outside both boxes can still cut through an endpoint.
          if (source.x + source.width <= target.x || target.x + target.width <= source.x) {
            const right = source.x < target.x;
            const sx = right ? source.x + source.width : source.x;
            const tx = right ? target.x : target.x + target.width;
            const channel = Math.min(sx, tx) + Math.abs(tx - sx) * fraction;
            points = [{ x: sx, y: sy }, { x: channel, y: sy }, { x: channel, y: ty }, { x: tx, y: ty }];
          } else {
            const down = source.y < target.y;
            const syBoundary = down ? source.y + source.height : source.y;
            const tyBoundary = down ? target.y : target.y + target.height;
            const channel = Math.min(syBoundary, tyBoundary) + Math.abs(tyBoundary - syBoundary) * fraction;
            const sx = source.x + source.width * (0.2 + fraction * 0.6);
            const tx = target.x + target.width * (0.2 + fraction * 0.6);
            points = [{ x: sx, y: syBoundary }, { x: sx, y: channel }, { x: tx, y: channel }, { x: tx, y: tyBoundary }];
          }
        }
      }
      return { id: edge.id, points };
    });
  }

  function layout(graph, options = {}) {
    const input = validated(graph, options), nodes = input.nodes.map(dimensions);
    if (!nodes.length) return { width: padding * 2, height: padding * 2, nodes: [], edges: [] };
    // Transpose the internal dimensions before placement, keeping final labels
    // upright and node boxes at their original text-measured dimensions in TB.
    if (input.direction === "TB") for (const node of nodes) [node.width, node.height] = [node.height, node.width];
    let ranks, geometry;
    if (input.mode === "force") forcePositions(nodes, input.edges);
    else {
      ranks = input.mode === "tree" ? treeRanks(input.nodes, input.edges) : input.mode === "bipartite" ?
        bipartiteRanks(input.nodes, input.edges) : layeredRanks(input.nodes, input.edges);
      geometry = columns(nodes, ranks);
    }
    const edges = routes(nodes, input.edges, ranks, geometry);
    if (input.direction === "TB") {
      for (const node of nodes) { [node.x, node.y] = [node.y, node.x]; [node.width, node.height] = [node.height, node.width]; }
      for (const edge of edges) for (const point of edge.points) [point.x, point.y] = [point.y, point.x];
    }
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const include = (x, y) => { minX = Math.min(minX, x); minY = Math.min(minY, y); maxX = Math.max(maxX, x); maxY = Math.max(maxY, y); };
    for (const node of nodes) { include(node.x, node.y); include(node.x + node.width, node.y + node.height); }
    for (const edge of edges) for (const point of edge.points) include(point.x, point.y);
    const dx = padding - minX, dy = padding - minY;
    for (const node of nodes) { node.x += dx; node.y += dy; }
    for (const edge of edges) for (const point of edge.points) { point.x += dx; point.y += dy; }
    return { width: maxX - minX + padding * 2, height: maxY - minY + padding * 2, nodes, edges };
  }

  return Object.freeze({ layout, wrapLabel, typeColor });
});
