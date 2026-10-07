# Visualization style review — 2026-09-16

Open [visualization_styles.html](visualization_styles.html) in a browser to review
four presentation examples: an approval DFG, an agent retry DFG, a typed OCDFG,
and an object-instance variant chevron. This is a self-contained design prototype,
not a change to the installed PIX viewer's default appearance.

The embedded data comes from synthetic logs calculated by PIX. Graph node
coordinates, edge paths and counts were retained from the Graphviz comparison
samples; chevron lanes and shared events were retained from the native variant
example. Source identifiers, hashes and calculation provenance remain embedded.
References to `.artifacts/` identify local review evidence, not runtime files
needed to open this example.

The prototype keeps activity labels at 13 CSS pixels and metrics at 11 CSS pixels.
It measures their actual rendered size and sets the minimum graph scale so that
labels fit inside nodes. Smaller viewports support dragging to see the graph.
Optional host design controls are guarded; opening the file directly does not
require the host or a network connection.

The corrected prototype was checked in Chromium 151.0.7922.34 with four samples,
three viewport widths (1024, 736 and 390 CSS pixels), three view modes and two
finishes: 72 combinations. No text overflow inside nodes, node overlap or script
error was observed. At 1024 pixels, all graph nodes fit in the default view. Data
and edge paths were unchanged. These observations apply to that browser, font
environment and sample set; they do not establish readability for all graphs.

Reviewed HTML SHA-256:
`51f0750d218345554d6360ec0207c4c83e5d6a744caff04ab21dffd50fddeef2`.

Full local measurements and screenshots are under
`.artifacts/aesthetic-study-2026-09-16/text-fit-qa/`; those generated artifacts and
downloaded event logs remain excluded from Git.
