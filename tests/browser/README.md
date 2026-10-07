# Offline viewer browser checks

These opt-in tests use real headless Chromium against HTML exported by production
`pix.viewer`. Synthetic OCEL is computed by native `discover_ocdfg`; model views
use accepting Petri net and OCPN contracts with explicit marking/binding examples.
No PM4Py, OCPA, Graphviz, mock layout, server, or runtime CDN is used. The delayed-layout
test postpones the actual ELK call only to exercise the pending state.

From the PIX root in PowerShell:

```powershell
uv pip install --python .venv\Scripts\python.exe -e '.[dev,browser]'
.venv\Scripts\python.exe -m playwright install chromium
$env:PIX_RUN_BROWSER = '1'
.venv\Scripts\python.exe -m pytest tests/browser -q
Remove-Item Env:PIX_RUN_BROWSER
```

Without Playwright or the explicit environment opt-in, these browser tests skip;
when opted in, a missing browser installation fails with Playwright's instructions.
The default unit suite does not need a browser. Runtime network requests and
browser errors fail every exported HTML scenario. Screenshots are written into
the ignored `.artifacts/browser` directory for human inspection.

Coverage includes native counts and source evidence; parallel object-type edges;
repeated activity self-loops; singleton activities and empty objects; keyboard
selection; filters retaining source data and node positions; 736/360px layouts;
long Korean labels; hostile HTML/XML text; styled SVG downloads and graph bounds;
empty analyses; and export readiness.
Model checks cover separate identities for repeated visible labels, silent
transitions, weighted arcs, initial/final markings, typed places, fixed/variable
object cardinalities, and original concrete object IDs.

These checks verify small correctness examples, not a large-log performance limit,
cross-browser certification, or every possible edge crossing and label overlap.
The fit-all view is an overview: on a phone, and for a seven-node horizontal Petri
net even at 1280px, labels require the Readable control, zoom, or selection for
reading. The suite verifies that Readable gives a 1:1 SVG/CSS scale and centres
the selected model node without altering graph data or positions. Screenshots
capture both overview and readable views, not simultaneous readability of every
node in every viewport.
