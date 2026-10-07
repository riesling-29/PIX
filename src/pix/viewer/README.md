# PIX read-only process graph viewer

`pix.viewer` presents successful native DFG / OCDFG computations and supplied
executable Petri nets / OCPNs. It does not compute process relations, discover a
normative model, or edit the canonical log.

```python
from pix.compute import discover_ocdfg
from pix.contracts.analysis import OCDFGSpec
from pix.viewer import build_graph, export_html

result = discover_ocdfg(log, OCDFGSpec(("Order", "Package")))
graph = build_graph(result, title="Order fulfilment")
export_html(graph, "orders.html")
```

`build_graph(result)` accepts only a successful DFG/OCDFG result with source and
computation identities. The frozen `pix.contracts.graph` data has no coordinates,
colors, mutable dictionaries, or render-library dependency. Stable activity IDs
are separate from labels; typed parallel edges are preserved. The three edge
counts are checked against their original event-event-object evidence.

`build_model_graph(net_or_artifact, title=...)` accepts `PetriNet`,
`ObjectCentricPetriNet`, or a `pix.models.ModelArtifact` containing either net.
Its separate `ModelGraphDocument` contract has no observed frequency fields.
It preserves the model digest, declared origin, discovery computation reference,
node IDs, arc constraints, and initial/final markings. Equal activity labels do
not merge transitions. A bare model's origin is explicitly unspecified.

For model views, circles are places, rectangles visible transitions, and dark
bars silent transitions. Filled tokens depict the initial marking; a double ring
indicates a nonzero final marking. Exact initial/final token counts appear below
places and their concrete object identities appear in the inspector. PN weights
are token multiplicities. OCPN arc labels show object cardinality; dashed arcs
indicate variable cardinality, including `0..0` and explicitly unbounded maxima.
This notation does not use line thickness as frequency. The declared finite
object universe, including idle objects, is available in the overview inspector.
The viewer does not certify soundness, boundedness or conformance and does not
implement an OCPN discovery algorithm or model editor.

`render_html(graph)` returns a self-contained document. `export_html` writes it
atomically and refuses to replace an existing path unless `overwrite=True` is
specified. Its no-clobber publication uses filesystem hard links: a filesystem
without that facility fails without replacing the destination. The output
includes all graph evidence, including objects hidden later by a view filter;
visibility is not redaction. The HTML carries the selected engine's license and
provenance.
`export_html_report` returns the file hash, byte count and any temporary-file
cleanup issues separately from publication success. The Path-returning
`export_html` convenience API intentionally returns only the path; use
`export_html_report` when cleanup evidence is needed. A failed publication retains
its primary exception and attached cleanup
evidence; it does not replace that error with a cleanup error.
The browser export explicitly rejects integer magnitudes above `2**53 - 1`
instead of rounding weights or bounds. Native model contracts and native model
JSON retain arbitrary-size integers exactly.

## Inspecting the graph

- The count selector distinguishes event pairs, unique objects, and per-object
  occurrences. Edge width is fixed rather than encoding an unstated metric.
- Type checkboxes hide edges while keeping the full-graph layout, colors, node
  totals and source data fixed. The visible and hidden edge counts are explicit.
- Select an edge for all three counts and paginated event/object evidence,
  including E2O qualifiers. Select a node for source references (first 100 shown;
  the full list remains in the HTML data).
- Drag the background to pan, scroll or use `+`/`−` to zoom, and press `0` to fit.
  The SVG is keyboard focusable; arrow keys pan. Tab and Enter select graph items.
- `Fit` provides a complete overview, which can make labels small for long nets.
  `Readable` sets the designed text size and centers the selected node (or current
  view); pan to explore the rest. A low-scale hint makes this distinction visible.
- `Save SVG` exports the current type visibility and counting unit with styles
  and provenance metadata. It fits the full layout, including space reserved for
  hidden edges. This is a static graph image, not a full evidence export.
  Save remains disabled until layout succeeds. Model SVG metadata preserves model
  origin, source reference, model digest and semantic notes.
- Empty graphs, long Unicode labels, and layout failures have visible states.
  Display text replaces XML-invalid control characters with U+FFFD; source data
  remains unchanged in the HTML's JSON payload.

## Layout boundary

**Graphviz is the default for every graph view**, including `GraphDocument`,
`ModelGraphDocument` and graph panels in `VisualizationDocument`. Graphviz
**16.0.0** is pinned through **`@viz-js/viz` 3.30.0** and vendored with inline
WebAssembly under `assets/vendor`. It requires no CDN, Node installation,
system `dot` process or Python `graphviz` package at runtime. Graphviz computes
node positions, splines and edge-label positions; PIX retains semantic IDs,
evidence, SVG rendering and interactions. This does not delegate mining to PM4Py
or OCPA. The default change follows the
[2026-09-16 requirements](../../../docs/requirements/2026-09-16_GRAPHVIZ_AND_OC_VARIANT_VISUALIZATION.md).

`render_html`, `export_html` and `export_html_report` accept
`layout_engine="graphviz"` by default. `layout_engine="native"` explicitly selects
experimental PIX geometry for `VisualizationDocument` only; `layout_engine="elk"`
selects pinned ELK.js **0.12.0** for legacy graph documents only. Unsupported
combinations are rejected. A layout failure is visible and does not silently
select another engine. Existing type filters, count selectors and evidence
inspection remain available on legacy graphs.

`assets/layout.js` retains the legacy ELK geometry adapter; browser rendering lives
in `viewer.js`. The new document renderer lives in `visualization.js`.

For an embedding, `PIXViewer.mount(element, graph, {layout})` accepts an async
layout function. Its input is a graph copy; its output follows the ELK JSON
geometry shape and preserves the label/shape metadata produced by
`PIXLayout.toElkGraph`. `PIXLayout.createElkLayout(engine)` supplies the checked adapter
for compatible engines and verifies preservation of nodes and edges. A custom
renderer may instead consume `GraphDocument` directly.

## Object-centric variant chevrons

`build_variant_visualization(execution_result, variant_result, title=...)` combines
matching native execution and variant results with checked parent provenance.
It draws a representative execution per classified variant, preserving frequency,
population and member evidence. PIX's exact qualified-incidence variant definition
does not change to OCPA's default approximate variant definition.

`build_execution_chevrons(execution, title=..., panel_id=...)` provides a lower-level
`ChevronPanel` for one execution. Every lane is an object instance, colored by
object type. A shared event has one semantic ID and one inclusive `[start, end]`
slot interval, displayed on each participating lane. The start is its longest-path
precedence level; its end is one slot before its earliest successor, or its own
start when it is a sink. Width is not duration. The dedicated chevron renderer
uses these domain slots independently of Graphviz.

The auto-export exposes `window.pixViewerReady` and, after it resolves,
`window.pixViewer`. The controller provides `getViewState()`, `getGraph()` (a
copy), and `destroy()`. This is a modern-browser viewer using SVG, ResizeObserver
and structuredClone. Large-network throughput is not established; no size or
latency guarantee is claimed.

## Verification and vendor updates

```text
python -m pytest tests/viewer
node --test tests/viewer/test_layout.cjs tests/viewer/test_graphviz_geometry.cjs tests/viewer/test_legacy_graphviz.cjs tests/viewer/test_visualization_ui.cjs
cd tools/viewer_vendor
npm ci --ignore-scripts
npm run check
```

The vendor folder records the exact registry archive, source revision, license,
SHA256 and byte count. Graphviz metadata is in
`assets/vendor/graphviz-provenance.json`; Viz.js, Graphviz and Expat license files
are included separately. Source-build reproducibility is not claimed. The
`tools/viewer_vendor` npm commands above currently verify and reproduce the
explicit legacy ELK option only. No npm dependencies are loaded by the Python
calculation engine. Changing either layout engine requires rerunning geometry
tests, packaged-file checks and actual-browser inspection.
