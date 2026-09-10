"""Generate inspectable native analysis artifacts from a small OCEL or a file.

Run from an installed PIX environment, e.g.:
  python examples/native_pipeline.py --output .artifacts/native-demo
Outputs are not overwritten unless --overwrite is explicitly supplied.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix.api import (
    AlignmentSpec,
    ComputeStatus,
    DiscoverySpec,
    ExecutionSpec,
    OCDFGSpec,
    TemporalSpec,
    TraceSpec,
    VariantSpec,
    align_traces,
    discover_executions,
    discover_ocdfg,
    discover_process_tree,
    discover_variants,
    export_ocel,
    measure_temporal,
    process_tree_to_petri_net,
    read_ocel,
    reconstruct_traces,
    replay_traces,
    write_result,
)
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.models import ModelArtifact, write_model
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer import build_graph, build_model_graph, export_html


def demo_log() -> OCEL:
    start = datetime(2026, 9, 9, 9, tzinfo=timezone.utc)
    rows = (
        ("e1", 0, "주문 접수", ("O1",)),
        ("e2", 1, "주문 접수", ("O2",)),
        ("e3", 5, "공동 포장", ("O1", "O2", "P1")),
        ("e4", 10, "배송", ("O1", "O2", "P1")),
        ("e5", 20, "주문 접수", ("O3",)),
        ("e6", 30, "배송", ("O3", "P2")),
        ("e7", 35, "배송 확인", ("P2",)),
    )
    return OCEL(
        event_types=tuple(EventType(name) for name in sorted({row[2] for row in rows})),
        object_types=(ObjectType("Order"), ObjectType("Package")),
        events=tuple(
            Event(eid, activity, start + timedelta(minutes=minutes))
            for eid, minutes, activity, _ in rows
        ),
        objects=tuple(
            Object(oid, kind)
            for oid, kind in (
                ("O1", "Order"),
                ("O2", "Order"),
                ("O3", "Order"),
                ("P1", "Package"),
                ("P2", "Package"),
            )
        ),
        e2o=tuple(
            E2O(eid, oid, "participates")
            for eid, _, _, objects in rows
            for oid in objects
        ),
    )


def provided_shipping_model() -> ObjectCentricPetriNet:
    """An explicitly provided OCPN example, not discovered from the input log."""
    return ObjectCentricPetriNet(
        places=(
            TypedPlace("order-ready", "Order"),
            TypedPlace("order-done", "Order"),
            TypedPlace("package-ready", "Package"),
            TypedPlace("package-done", "Package"),
        ),
        transitions=(Transition("ship", "공동 배송"),),
        arcs=(
            ObjectArc("order-ready", "ship", True, 1, 2),
            ObjectArc("ship", "order-done", True, 1, 2),
            ObjectArc("package-ready", "ship"),
            ObjectArc("ship", "package-done"),
        ),
        initial_marking=ObjectMarking(
            (
                ObjectToken("order-ready", "O1"),
                ObjectToken("order-ready", "O2"),
                ObjectToken("package-ready", "P1"),
            )
        ),
        final_marking=ObjectMarking(
            (
                ObjectToken("order-done", "O1"),
                ObjectToken("order-done", "O2"),
                ObjectToken("package-done", "P1"),
            )
        ),
        objects=(("O1", "Order"), ("O2", "Order"), ("P1", "Package")),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, default=Path(".artifacts/native-demo"))
    parser.add_argument("--object-type", default="Order")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    log = read_ocel(args.input) if args.input else demo_log()
    args.output.mkdir(parents=True, exist_ok=True)
    for fmt, suffix in (("json", ".json"), ("xml", ".xml"), ("sqlite", ".sqlite")):
        exported = export_ocel(
            log, args.output / ("ocel" + suffix), format=fmt, overwrite=args.overwrite
        )
        print(f"OCEL {fmt}: {exported.roundtrip}; {exported.path}")
    traces = reconstruct_traces(log, TraceSpec(args.object_type))
    graph = discover_ocdfg(
        log, OCDFGSpec(tuple(kind.name for kind in log.object_types))
    )
    executions = discover_executions(log, ExecutionSpec("connected_components"))
    results = [
        traces,
        graph,
        executions,
        discover_variants(executions, VariantSpec()),
        measure_temporal(log, TemporalSpec(args.object_type)),
    ]
    tree = discover_process_tree(traces, DiscoverySpec())
    results.append(tree)
    if tree.status is ComputeStatus.COMPUTED:
        net = process_tree_to_petri_net(tree.value)
        artifact = ModelArtifact(net, "discovered", tree.computation_id)
        write_model(
            artifact,
            args.output / "model.json",
            overwrite=args.overwrite,
        )
        export_html(
            build_model_graph(artifact, title="PIX · discovered Petri net"),
            args.output / "model.html",
            overwrite=args.overwrite,
        )
        results.extend(
            (align_traces(traces, net, AlignmentSpec()), replay_traces(traces, net))
        )
    for result in results:
        name = result.operator_id.removeprefix("pix.") + ".json"
        output = write_result(result, args.output / name, overwrite=args.overwrite)
        print(f"{result.operator_id}: {result.status.value}; {output.path}")
    if graph.status is ComputeStatus.COMPUTED:
        viewer = export_html(
            build_graph(graph), args.output / "process.html", overwrite=args.overwrite
        )
        print(f"Viewer: {viewer}")
    provided = ModelArtifact(provided_shipping_model(), "provided")
    write_model(provided, args.output / "provided-ocpn.json", overwrite=args.overwrite)
    ocpn_viewer = export_html(
        build_model_graph(provided, title="PIX · provided OCPN example"),
        args.output / "ocpn.html",
        overwrite=args.overwrite,
    )
    print(f"Provided OCPN example (independent of input log): {ocpn_viewer}")


if __name__ == "__main__":
    main()
