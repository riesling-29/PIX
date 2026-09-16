"""Build a reproducible, offline gallery from native PIX calculations.

Run ``python examples/native_visualization_demo.py --output <directory>``.
Every analysis view below comes from an actual native calculation on explicitly
synthetic data. The final rendering-fixture page is labelled separately; its
numbers demonstrate presentation behavior and are not analytical findings.
"""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix import case_centric as cc
from pix import object_centric as oc
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.analysis import OCDFGSpec
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.object_centric.discovery import SAWDiscoverySpec, discover_saw_net
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer import (
    ChartPanel,
    ChartPoint,
    ChartSeries,
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    TimelineItem,
    TimelineLane,
    TimelinePanel,
    VisualEdge,
    VisualField,
    VisualizationDocument,
    VisualMetric,
    VisualNode,
    build_model_visualization,
    build_variant_duration,
    build_visualization,
    compare_footprints,
    export_html,
    write_visualization,
)

HOSTILE = '</script><img src="https://invalid.example/pix" onerror="window.pwned=1">&'
LONG_LABEL = "공동 배송 품질 검토와 승인 — long activity evidence " * 8


def synthetic_case_log() -> CaseLog:
    """Four cases with choice and a deliberate observed rework loop."""
    start = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
    words = (
        ("Receive", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Revise", "Review", "Approve", "Ship"),
        ("Receive", "Review", "Reject"),
    )
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{i + 1}",
                tuple(
                    CaseEvent(
                        f"case-{i + 1}:event-{j + 1}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute(
                                "time:timestamp",
                                "date",
                                start + timedelta(minutes=i * 60 + j * (i + 2)),
                            ),
                            CaseAttribute("org:resource", "string", f"agent-{j % 3}"),
                        ),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def synthetic_ocel() -> OCEL:
    """Two orders and one shared parcel; qualifiers remain independent rows."""
    start = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(a) for a in ("Receive", "Pack", "Ship")),
        object_types=(ObjectType("order"), ObjectType("parcel")),
        events=tuple(
            Event(f"e{i}", activity, start + timedelta(minutes=i * 5))
            for i, activity in enumerate(("Receive", "Receive", "Pack", "Ship"))
        ),
        objects=(Object("o1", "order"), Object("o2", "order"), Object("p1", "parcel")),
        e2o=(
            E2O("e0", "o1", "created"),
            E2O("e1", "o2", "created"),
            E2O("e2", "o1", "packed"),
            E2O("e2", "o2", "packed"),
            E2O("e2", "p1", "container"),
            E2O("e3", "o1", "shipped"),
            E2O("e3", "o2", "shipped"),
            E2O("e3", "p1", "container"),
            E2O("e3", "o1", "audit"),
        ),
    )


def rendering_fixture() -> VisualizationDocument:
    """Explicit synthetic values exercise all five panels and hostile labels."""
    return VisualizationDocument(
        "Rendering fixture · supplied example values",
        (
            GraphPanel(
                "graph",
                "Graph · inspection and identity",
                (
                    VisualNode(
                        "first",
                        "Receive",
                        metrics=(VisualMetric("events", 3, "events"),),
                    ),
                    VisualNode(
                        "second", LONG_LABEL, details=(VisualField("source", HOSTILE),)
                    ),
                    VisualNode("third", HOSTILE),
                    VisualNode(
                        "isolated", "Isolated object", kind="object", group="parcel"
                    ),
                ),
                (
                    VisualEdge(
                        "forward",
                        "first",
                        "second",
                        "order",
                        details=(VisualField("qualifier", "shipped"),),
                    ),
                    VisualEdge("parallel", "first", "second", "parcel"),
                    VisualEdge("loop", "second", "second", "rework"),
                    VisualEdge("last", "second", "third"),
                ),
                description="Synthetic rendering fixture. Parallel edges, a self-loop and an isolated object are distinct.",
            ),
            MatrixPanel(
                "matrix",
                "Matrix · unknown is explicit",
                ("A", "B"),
                ("A", "B"),
                (
                    MatrixCell("A", "A", 0),
                    MatrixCell("A", "B", 3),
                    MatrixCell("B", "A", None),
                ),
                legend=(
                    VisualField(
                        "value", "Supplied example count; missing and unknown differ"
                    ),
                ),
                unit="occurrences",
            ),
            ChartPanel(
                "chart",
                "Chart · known and unknown observations",
                "bar",
                (
                    ChartSeries(
                        "Supplied observations",
                        (
                            ChartPoint("Known zero", 0),
                            ChartPoint("Known positive", 3),
                            ChartPoint("Unknown", None),
                        ),
                    ),
                ),
                y_label="Supplied count",
                y_unit="observations",
            ),
            TimelinePanel(
                "timeline",
                "Timeline · open and closed intervals",
                (
                    TimelineLane("agent-a", "Agent A"),
                    TimelineLane("agent-b", "Agent B"),
                ),
                (
                    TimelineItem(
                        "closed", "agent-a", 0, 4, "Completed", status="complete"
                    ),
                    TimelineItem(
                        "open", "agent-b", 2, None, "End unknown", status="unknown"
                    ),
                ),
                description="Relative supplied seconds; open interval end is not inferred.",
            ),
            TablePanel(
                "table",
                "Table · exact evidence",
                ("ID", "Value"),
                (
                    ("zero", 0),
                    ("unknown", None),
                    ("hostile", HOSTILE),
                    ("boolean", False),
                ),
            ),
        ),
        issues=(
            "Rendering fixture only: values are supplied examples, not calculated findings.",
        ),
    )


def build_demo_documents() -> dict[str, VisualizationDocument]:
    log, ocel = synthetic_case_log(), synthetic_ocel()
    dfg, inductive = cc.discover_dfg(log), cc.discover_inductive(log)
    if inductive.status is not ComputeStatus.COMPUTED or inductive.value is None:
        raise RuntimeError(f"Native demo discovery failed: {inductive.issues}")
    tree = inductive.value
    net = process_tree_to_petri_net(tree)
    alignment = cc.align_traces(log, net)
    footprints = cc.discover_footprints(log)
    ocdfg = oc.discover_ocdfg(ocel, OCDFGSpec(("order", "parcel")))
    ocpn_spec = OCPNDiscoverySpec(
        ("order", "parcel"), "observed_range", "unique_activity"
    )
    ocpn = oc.discover_ocpn(ocel, ocpn_spec)
    saw = discover_saw_net(ocel, SAWDiscoverySpec(ocpn_spec))
    split = cc.split_miner.discover_split_miner(log)
    replay = cc.replay_traces(log, net)
    performance = cc.statistics.measure_case_performance(log)
    return {
        "case-flow": build_visualization(dfg, title="Case-centric · observed flow"),
        "case-models": build_visualization(
            inductive,
            net,
            cc.heuristics.discover_heuristics(log),
            cc.discovery.discover_transition_system(log),
            split,
            title="Case-centric · native process models",
        ),
        "case-conformance": build_visualization(
            alignment,
            replay,
            title="Case-centric · alignment and token replay",
        ),
        "case-footprints": build_visualization(
            footprints, title="Case-centric · observed footprints"
        ),
        "case-footprint-comparison": compare_footprints(
            footprints,
            cc.model_discovery.discover_model_footprints(net),
            title="Case-centric · observed and model footprint relations",
        ),
        "case-model-diagnostics": build_model_visualization(
            net,
            annotations=replay,
            metric="firing_count",
            title="Case-centric · recorded transition firing counts",
        ),
        "case-variant-duration": build_variant_duration(
            cc.statistics.measure_statistics(log),
            performance,
            title="Case-centric · variants and observed duration",
        ),
        "case-performance": build_visualization(
            log,
            performance,
            title="Case-centric · timestamps and duration",
        ),
        "case-constraints": build_visualization(
            cc.declarative.discover_declare(log),
            cc.declarative.discover_log_skeleton(log),
            cc.declarative.discover_temporal_profile(log),
            title="Case-centric · constraints and temporal profile",
        ),
        "object-flow": build_visualization(
            ocdfg, title="Object-centric · shared event evidence"
        ),
        "object-models": build_visualization(
            ocpn, saw, title="Object-centric · OCPN and observed arc weights"
        ),
        "object-log": build_visualization(
            ocel,
            oc.statistics.object_statistics(ocel),
            title="Object-centric · objects, events and qualified relations",
        ),
        "rendering-fixture": rendering_fixture(),
        "empty": VisualizationDocument("Empty supplied document"),
        "partial": build_visualization(
            VisualizationDocument(
                "Partial supplied view",
                (
                    GraphPanel(
                        "partial", "Observed prefix", (VisualNode("a", "Receive"),)
                    ),
                ),
                issues=("Incomplete observation: suffix is unknown.",),
                status="partial",
            ),
            cc.discover_inductive(CaseLog(())),
            title="Partial supplied view · unavailable input remains separate",
        ),
    }


def write_gallery(output: Path, *, overwrite: bool = False) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, document in build_demo_documents().items():
        export_html(document, output / f"{name}.html", overwrite=overwrite)
        write_visualization(document, output / f"{name}.json", overwrite=overwrite)
        manifest.append(
            {
                "name": name,
                "title": document.title,
                "status": document.status,
                "panels": [{"id": p.id, "kind": p.kind} for p in document.panels],
            }
        )
    index = output / "index.html"
    if index.exists() and not overwrite:
        raise FileExistsError(index)
    cards = "".join(
        f'<a href="{item["name"]}.html"><strong>{html.escape(item["title"])}</strong><span>{len(item["panels"])} panels · {html.escape(item["status"])}</span></a>'
        for item in manifest
    )
    index.write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PIX native visualization gallery</title><style>body{font:16px Segoe UI,sans-serif;max-width:1080px;margin:48px auto;padding:0 24px;background:#f6f8fa;color:#293b47}h1{font-size:32px}p{line-height:1.65}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}a{display:grid;gap:12px;text-decoration:none;color:inherit;padding:24px;border:1px solid #dce5e9;border-radius:12px;background:white}a:hover,a:focus{border-color:#197a91}span{font-size:14px;color:#647884}</style><h1>PIX native visualization</h1><p>Reproducible native calculations on synthetic case and object-centric event logs. Open each page directly from disk. No server, Graphviz, ELK, CDN or network request is needed for these views. Rendering fixtures and incomplete views are labelled explicitly.</p><main>'
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
        "--output", type=Path, default=Path(".artifacts/visualization-2026-09-15/demo")
    )
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()
    print(write_gallery(arguments.output, overwrite=arguments.overwrite).resolve())


if __name__ == "__main__":
    main()
