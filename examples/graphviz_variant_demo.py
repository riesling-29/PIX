"""Offline Graphviz graphs and OCPA-style chevrons from native PIX calculations.

Run ``python examples/graphviz_variant_demo.py --output <directory>``. The source
is an explicitly synthetic log: three disconnected order executions, of which
two share a variant and one has rework. Chevron widths represent precedence
slots, not elapsed duration. Graphviz is bundled; no system dot is required.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix import case_centric as cc
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.executions import discover_executions
from pix.compute.ocdfg import discover_ocdfg
from pix.compute.ocpn_discovery import discover_ocpn
from pix.compute.variants import discover_variants
from pix.contracts.analysis import OCDFGSpec
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.models import ModelArtifact
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer import (
    VisualizationDocument,
    build_execution_chevrons,
    build_graph,
    build_model_graph,
    build_variant_visualization,
    build_visualization,
    export_html,
    write_visualization,
)


def synthetic_fork_join_ocel() -> OCEL:
    """Two Item instances branch and join one Order in each execution."""
    origin = datetime(2026, 9, 16, 9, tzinfo=timezone.utc)
    events, objects, relations = [], [], []
    for number in range(1, 4):
        order, left, right = (
            f"Order_{number}",
            f"Item_{2 * number - 1}",
            f"Item_{2 * number}",
        )
        objects.extend(
            (Object(order, "Order"), Object(left, "Item"), Object(right, "Item"))
        )
        rows = [
            ("fork", "Fork", (order, left, right)),
            ("inspect", "Inspect", (left,)),
            ("check", "Check", (right,)),
            ("pack", "Pack", (left,)),
        ]
        if number == 3:
            rows.append(("rework", "Inspect", (left,)))
        rows.append(("join", "Join", (order, left, right)))
        for index, (suffix, activity, participants) in enumerate(rows):
            event_id = f"execution-{number}:{suffix}"
            events.append(
                Event(
                    event_id, activity, origin + timedelta(hours=number, minutes=index)
                )
            )
            relations.extend(
                E2O(event_id, object_id, "flow") for object_id in participants
            )
            if suffix == "join":
                relations.append(E2O(event_id, right, "audit"))
    return OCEL(
        event_types=tuple(
            EventType(activity)
            for activity in ("Fork", "Inspect", "Check", "Pack", "Join")
        ),
        object_types=(ObjectType("Order"), ObjectType("Item")),
        events=tuple(events),
        objects=tuple(objects),
        e2o=tuple(relations),
    )


def synthetic_case_log() -> CaseLog:
    words = (
        ("Receive", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Revise", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Reject"),
    )
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{index}",
                tuple(
                    CaseEvent(
                        f"event-{index}-{position}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for position, activity in enumerate(word)
                ),
            )
            for index, word in enumerate(words)
        )
    )


def build_demo_documents() -> dict:
    source = synthetic_fork_join_ocel()
    execution = discover_executions(source, ExecutionSpec("connected_components"))
    variants = discover_variants(execution, VariantSpec())
    assert (
        execution.status is ComputeStatus.COMPUTED
        and variants.status is ComputeStatus.COMPUTED
    )
    assert sorted(
        len(variant.execution_ids) for variant in variants.value.variants
    ) == [1, 2]
    variant_document = build_variant_visualization(
        execution, variants, title="OCPA-style variants · synthetic order executions"
    )
    standalone = build_execution_chevrons(execution.value.executions[0])
    case_log = synthetic_case_log()
    discovery = cc.discover_inductive(case_log)
    net = process_tree_to_petri_net(discovery.value)
    ocdfg = discover_ocdfg(source, OCDFGSpec(("Order", "Item")))
    ocpn = discover_ocpn(
        source,
        OCPNDiscoverySpec(("Order", "Item"), "observed_range", "unique_activity"),
    )
    assert (
        ocdfg.status is ComputeStatus.COMPUTED and ocpn.status is ComputeStatus.COMPUTED
    )
    return {
        "variant-chevrons": variant_document,
        "execution-chevron": VisualizationDocument(
            "One supplied execution · precedence slots",
            (standalone,),
            tuple(
                replace(item, panel_ids=(standalone.id,))
                for item in variant_document.provenance
                if item.calculation_id == execution.computation_id
            ),
        ),
        "graphviz-dfg": build_visualization(
            cc.discover_dfg(case_log),
            title="Graphviz · observed approval and rework DFG",
        ),
        "legacy-ocdfg": build_graph(
            ocdfg, title="Graphviz · OCDFG count units and object types"
        ),
        "legacy-pn": build_model_graph(
            ModelArtifact(net, "discovered", discovery.computation_id),
            title="Graphviz · case Petri net converted from discovered tree",
        ),
        "legacy-ocpn": build_model_graph(
            ModelArtifact(ocpn.value.model, "discovered", ocpn.computation_id),
            title="Graphviz · discovered object-centric Petri net",
        ),
    }


def write_gallery(output: Path, *, overwrite: bool = False) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    index = output / "index.html"
    if index.exists() and not overwrite:
        raise FileExistsError(index)
    manifest = []
    for name, document in build_demo_documents().items():
        export_html(document, output / f"{name}.html", overwrite=overwrite)
        if isinstance(document, VisualizationDocument):
            write_visualization(document, output / f"{name}.json", overwrite=overwrite)
            panels = [{"id": panel.id, "kind": panel.kind} for panel in document.panels]
        else:
            (output / f"{name}.json").write_text(
                json.dumps(asdict(document), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            panels = []
        manifest.append({"name": name, "title": document.title, "panels": panels})
    cards = "".join(
        f'<a href="{entry["name"]}.html"><strong>{html.escape(entry["title"])}</strong><span>Open interactive HTML</span></a>'
        for entry in manifest
    )
    index.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PIX Graphviz and variant chevrons</title><style>body{font:16px Segoe UI,sans-serif;max-width:1200px;margin:48px auto;padding:0 24px;background:#f6f8fa;color:#293b47}p{line-height:1.65}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}a{display:grid;gap:12px;text-decoration:none;color:inherit;padding:24px;border:1px solid #dce5e9;border-radius:12px;background:white}a:hover,a:focus{border-color:#197a91}span{font-size:14px;color:#647884}</style><h1>PIX · Graphviz and OCPA-style variants</h1><p>Native calculations on synthetic logs. Graphs use bundled Graphviz; chevrons use an object-instance precedence layout. Three executions produce two variants, with frequencies 2/3 and 1/3. A shared event appears at the same horizontal position on all participating object lanes. Chevron widths indicate inclusive precedence slots, never elapsed duration.</p><main>'
        + cards
        + "</main></html>",
        encoding="utf-8",
    )
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return index


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path(".artifacts/graphviz-2026-09-16/demo")
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    print(write_gallery(args.output, overwrite=args.overwrite).resolve())


if __name__ == "__main__":
    main()
