/* PIX object-instance chevron geometry. Precedence slots, never durations.
 * No DOM, Graphviz, event discovery, sorting, or data mutation is involved.
 * Explicit orientations remain fixed; only `auto` consults availableWidth.
 */
(function (root, factory) {
  "use strict";
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.PIXChevronGeometry = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const LIMIT = 10000;
  const ORIENTATIONS = ["horizontal", "vertical", "auto"];
  const STYLES = ["classic", "neutral"];
  const record = value => value !== null && typeof value === "object" && !Array.isArray(value);
  const text = (value, name) => {
    if (typeof value !== "string") throw new TypeError(`${name} must be a string.`);
    return value;
  };
  const identity = (value, name) => {
    text(value, name);
    if (!value.length) throw new TypeError(`${name} must not be empty.`);
    return value;
  };

  // Conservative 13px glyph estimates reserve space without reading a browser
  // font. Bound work on adversarial labels; original text stays in the result.
  const preview = value => Array.from(value.slice(0, 1024)).slice(0, 256).join("");
  const glyphWidth = point => /[\s.,:;!'|ilI]/u.test(point) ? 5 :
    point.codePointAt(0) > 255 ? 14 : /[MWmw@#%]/u.test(point) ? 13 : /[A-Z]/u.test(point) ? 10 : 8;
  const measure = value => Array.from(preview(value)).reduce((width, point) => width + glyphWidth(point), 0);
  function wrapLabel(value, maxWidth, maxLines = 2) {
    const excerpt = preview(value), truncated = excerpt.length < value.length;
    const source = excerpt.replace(/\s+/gu, " ").trim();
    if (!source) return [""];
    const points = Array.from(source), lines = [];
    let offset = 0;
    for (let line = 0; line < maxLines && offset < points.length; line++) {
      const start = offset;
      let width = 0, lastSpace = -1;
      const finalLine = line === maxLines - 1;
      const remainingWidth = finalLine ? points.slice(offset).reduce((total, point) => total + glyphWidth(point), 0) : 0;
      const reserve = finalLine && (remainingWidth > maxWidth || truncated) ? 14 : 0;
      while (offset < points.length && width + glyphWidth(points[offset]) <= maxWidth - reserve) {
        if (points[offset] === " ") lastSpace = offset;
        width += glyphWidth(points[offset++]);
      }
      if (offset === start) offset++;
      if (!finalLine && offset < points.length && lastSpace > start) offset = lastSpace + 1;
      let segment = points.slice(start, offset).join("").trim();
      if (finalLine && (offset < points.length || truncated)) segment += "…";
      lines.push(segment);
      while (points[offset] === " ") offset++;
    }
    return lines;
  }

  function validate(panel, appearanceLimit) {
    if (!record(panel) || !Array.isArray(panel.lanes) || !Array.isArray(panel.events)) {
      throw new TypeError("Chevron lanes and events must be arrays.");
    }
    if (panel.lanes.length > appearanceLimit || panel.events.length > appearanceLimit) {
      throw new RangeError(`Chevron geometry exceeds the ${appearanceLimit} appearance, lane or slot limit.`);
    }
    const laneIds = new Set(), eventIds = new Set();
    for (const lane of panel.lanes) {
      if (!record(lane)) throw new TypeError("Chevron lane must be an object.");
      identity(lane.id, "Chevron lane identity");
      text(lane.label, "Chevron lane label");
      text(lane.object_id, "Chevron object identity");
      text(lane.object_type, "Chevron object type");
      if (laneIds.has(lane.id)) throw new Error("Chevron lane and event identities must be unique.");
      laneIds.add(lane.id);
    }
    let slots = 1, appearances = 0;
    for (const event of panel.events) {
      if (!record(event)) throw new TypeError("Chevron event must be an object.");
      identity(event.id, "Chevron event identity");
      text(event.label, "Chevron event label");
      if (eventIds.has(event.id)) throw new Error("Chevron lane and event identities must be unique.");
      eventIds.add(event.id);
      if (!Number.isSafeInteger(event.start) || !Number.isSafeInteger(event.end) || event.start < 0 || event.end < event.start || !Array.isArray(event.lane_ids) || !event.lane_ids.length || new Set(event.lane_ids).size !== event.lane_ids.length || event.lane_ids.some(id => !laneIds.has(id))) {
        throw new Error("Chevron event requires an ordered inclusive interval and distinct existing lanes.");
      }
      appearances += event.lane_ids.length;
      slots = Math.max(slots, event.end + 1);
      if (appearances > appearanceLimit || slots > appearanceLimit) {
        throw new RangeError(`Chevron geometry exceeds the ${appearanceLimit} appearance, lane or slot limit.`);
      }
    }
    return {slots, appearances};
  }

  function horizontalMetrics(panel, style) {
    if (style === "classic") return {flowStart: 190, crossStart: 66, slotStep: 154, laneStep: 72, spanInset: 5, spanCrossInset: 10, spanThickness: 51, tip: 13, endPadding: 35, crossPadding: 45};
    let longestLane = 0, longestEvent = 0;
    for (const lane of panel.lanes) longestLane = Math.max(longestLane, measure(lane.label), measure(lane.object_id));
    for (const event of panel.events) longestEvent = Math.max(longestEvent, measure(event.label));
    return {flowStart: Math.max(150, Math.min(240, Math.ceil(longestLane / 2) + 64)), crossStart: 88, slotStep: Math.max(130, Math.min(240, Math.ceil(longestEvent / 2) + 52)), laneStep: 94, spanInset: 7, spanCrossInset: 18, spanThickness: 58, tip: 12, endPadding: 28, crossPadding: 32};
  }

  function verticalMetrics(panel, style) {
    let longest = 0;
    for (const lane of panel.lanes) longest = Math.max(longest, measure(lane.label), measure(lane.object_id));
    for (const event of panel.events) longest = Math.max(longest, measure(event.label));
    const laneStep = Math.max(style === "classic" ? 176 : 120, Math.min(288, Math.ceil(longest / 2) + 56));
    return {flowStart: style === "classic" ? 108 : 120, crossStart: style === "classic" ? 66 : 42, slotStep: 108, laneStep, spanInset: style === "classic" ? 5 : 7, spanCrossInset: style === "classic" ? 16 : 10, spanThickness: laneStep - (style === "classic" ? 32 : 20), tip: 13, endPadding: 34, crossPadding: style === "classic" ? 28 : 20};
  }

  function pointsFor(x, y, width, height, tip, vertical) {
    const points = vertical
      ? [[x, y], [x + width / 2, y + tip], [x + width, y], [x + width, y + height - tip], [x + width / 2, y + height], [x, y + height - tip]]
      : [[x, y], [x + width - tip, y], [x + width, y + height / 2], [x + width - tip, y + height], [x, y + height], [x + tip, y + height / 2]];
    return points.map(point => point.join(",")).join(" ");
  }

  function layout(panel, options = {}) {
    if (!record(options)) throw new TypeError("Chevron layout options must be an object.");
    const requestedOrientation = options.orientation === undefined ? "horizontal" : options.orientation;
    const style = options.style === undefined ? "neutral" : options.style;
    if (!ORIENTATIONS.includes(requestedOrientation)) throw new TypeError("Chevron orientation must be horizontal, vertical or auto.");
    if (!STYLES.includes(style)) throw new TypeError("Chevron style must be classic or neutral.");
    const availableWidth = options.availableWidth === undefined ? 1024 : options.availableWidth;
    if (!Number.isFinite(availableWidth) || availableWidth < 0) throw new TypeError("Chevron availableWidth must be a finite nonnegative number.");
    const appearanceLimit = options.appearanceLimit === undefined ? LIMIT : options.appearanceLimit;
    if (!Number.isSafeInteger(appearanceLimit) || appearanceLimit <= 0) throw new TypeError("Chevron appearanceLimit must be a positive safe integer.");
    const checked = validate(panel, appearanceLimit), horizontal = horizontalMetrics(panel, style);
    const horizontalWidth = Math.max(style === "classic" ? 700 : 480, horizontal.flowStart + checked.slots * horizontal.slotStep + horizontal.endPadding);
    const orientation = requestedOrientation === "auto" ? (availableWidth >= horizontalWidth ? "horizontal" : "vertical") : requestedOrientation;
    const vertical = orientation === "vertical", metrics = vertical ? verticalMetrics(panel, style) : horizontal;
    const flowSize = metrics.flowStart + checked.slots * metrics.slotStep + metrics.endPadding;
    const crossSize = metrics.crossStart + panel.lanes.length * metrics.laneStep + metrics.crossPadding;
    const width = vertical ? Math.max(320, crossSize) : horizontalWidth;
    const height = vertical ? Math.max(240, flowSize) : Math.max(180, crossSize);
    const lanes = panel.lanes.map((lane, index) => {
      const cross = metrics.crossStart + index * metrics.laneStep;
      return {
        id: lane.id, label: lane.label, object_id: lane.object_id, object_type: lane.object_type, index,
        x: vertical ? cross : 0, y: vertical ? 0 : cross,
        width: vertical ? metrics.laneStep : width, height: vertical ? height : metrics.laneStep,
        labelX: vertical ? cross + metrics.laneStep / 2 : 34,
        labelY: vertical ? 61 : cross + (style === "classic" ? 32 : 38),
        labelMaxWidth: vertical ? metrics.laneStep - 24 : metrics.flowStart - 58,
        labelAnchor: vertical ? "middle" : "start"
      };
    });
    const laneMap = new Map(lanes.map(lane => [lane.id, lane]));
    const appearances = [];
    for (const event of panel.events) {
      const flow = metrics.flowStart + event.start * metrics.slotStep + metrics.spanInset;
      const extent = (event.end - event.start + 1) * metrics.slotStep - metrics.spanInset * 2;
      for (const laneId of event.lane_ids) {
        const lane = laneMap.get(laneId), cross = metrics.crossStart + lane.index * metrics.laneStep + metrics.spanCrossInset;
        const x = vertical ? cross : flow, y = vertical ? flow : cross;
        const spanWidth = vertical ? metrics.spanThickness : extent, spanHeight = vertical ? extent : metrics.spanThickness;
        const labelMaxWidth = spanWidth - (style === "neutral" ? 40 : (vertical ? 24 : 36));
        appearances.push({eventId: event.id, laneId, laneIndex: lane.index, start: event.start, end: event.end,
          x, y, width: spanWidth, height: spanHeight, tip: metrics.tip,
          points: pointsFor(x, y, spanWidth, spanHeight, metrics.tip, vertical),
          labelX: x + spanWidth / 2 + (vertical ? 0 : 2), labelY: y + spanHeight / 2,
          labelMaxWidth, labelLines: wrapLabel(event.label, labelMaxWidth)});
      }
    }
    const ticks = Array.from({length: checked.slots}, (_, value) => {
      const flow = metrics.flowStart + value * metrics.slotStep;
      return vertical
        ? {value, x: metrics.crossStart - 22, y: flow + metrics.slotStep / 2 + 4, line: {x1: metrics.crossStart - 10, y1: flow, x2: width - 18, y2: flow}}
        : {value, x: flow + metrics.slotStep / 2, y: metrics.crossStart - 22, line: {x1: flow, y1: metrics.crossStart - 13, x2: flow, y2: height - 25}};
    });
    return {orientation, requestedOrientation, style, width, height, horizontalWidth,
      slots: checked.slots, appearanceCount: checked.appearances, metrics, lanes, appearances,
      axis: {titleX: vertical ? 20 : metrics.flowStart, titleY: 27, laneTitleX: vertical ? metrics.crossStart : 20, laneTitleY: vertical ? 43 : 27, ticks},
      emptyLabel: {x: vertical ? metrics.crossStart + 20 : metrics.flowStart + 35, y: vertical ? metrics.flowStart + 45 : Math.max(95, height / 2)}};
  }

  return {layout, wrapLabel, LIMIT};
});
