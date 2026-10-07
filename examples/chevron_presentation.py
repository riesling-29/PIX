"""Compare real PIX Chevron exports in both directions and both styles.

Run ``python examples/chevron_presentation.py --output <directory>``.
The input is the synthetic three-execution log from graphviz_variant_demo.
Every file contains the same calculations and source evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from graphviz_variant_demo import synthetic_fork_join_ocel

from pix.compute.executions import discover_executions
from pix.compute.variants import discover_variants
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.viewer import build_variant_visualization, export_html, write_visualization


def write_examples(output: Path, *, overwrite: bool = False) -> Path:
    executions = discover_executions(
        synthetic_fork_join_ocel(), ExecutionSpec("connected_components")
    )
    variants = discover_variants(executions, VariantSpec())
    view = build_variant_visualization(
        executions,
        variants,
        title="Object-centric variants · synthetic order executions",
    )
    first = max(
        (panel for panel in view.panels if panel.kind == "chevron"),
        key=lambda panel: panel.frequency,
    )
    view = replace(view, panels=(first, *(p for p in view.panels if p.id != first.id)))
    output.mkdir(parents=True, exist_ok=True)
    index = output / "index.html"
    if index.exists() and not overwrite:
        raise FileExistsError(index)
    write_visualization(view, output / "variants.json", overwrite=overwrite)
    export_html(view, output / "default.html", overwrite=overwrite)
    links = ['<li><a href="default.html">Default: neutral / horizontal</a></li>']
    for style in ("neutral", "classic"):
        for orientation in ("horizontal", "vertical", "auto"):
            name = f"{style}-{orientation}.html"
            export_html(
                view,
                output / name,
                overwrite=overwrite,
                chevron_orientation=orientation,
                chevron_style=style,
            )
            links.append(f'<li><a href="{name}">{style} / {orientation}</a></li>')
    index.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>PIX Chevron presentation</title><style>"
        "body{font:16px/1.6 system-ui;max-width:760px;margin:48px auto;padding:0 24px;"
        "color-scheme:light dark;background:light-dark(#fafafa,#171819);"
        "color:light-dark(#272a2d,#eceeef)}a{color:inherit}li{padding:8px 0}"
        "</style><h1>PIX Chevron presentation</h1>"
        "<p>Default: neutral horizontal. One synthetic log, two calculated variants. Fixed directions stay fixed; "
        "only auto responds to width. Span length means inclusive precedence slots, "
        "not elapsed time.</p><ul>" + "".join(links) + "</ul></html>",
        encoding="utf-8",
    )
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".artifacts/2026-09-17-visualization-chevron-presentation"),
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(write_examples(args.output, overwrite=args.overwrite).resolve())


if __name__ == "__main__":
    main()
