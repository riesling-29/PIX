"""Export a synthetic OCDFG and explicitly attributed projected case DFG."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pix import case_centric as cc
from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import OCDFGSpec
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.viewer import build_visualization, export_html, write_visualization


def review_document():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    source = OCEL(
        object_types=(ObjectType("Order"),),
        event_types=(EventType("A"), EventType("B")),
        objects=(Object("x", "Order"), Object("y", "Order")),
        events=tuple(
            Event(f"e{i + 1}", activity, origin + timedelta(seconds=i))
            for i, activity in enumerate(("A", "B", "A", "B"))
        ),
        e2o=tuple(E2O(f"e{i}", "x", "flow") for i in range(1, 5))
        + (E2O("e1", "y", "flow"), E2O("e2", "y", "flow")),
    )
    projection = project_object_cases(source, ObjectCaseProjectionSpec("Order"))
    projected = build_visualization(
        cc.discover_dfg(projection.case_log), projection=projection
    )
    return build_visualization(
        discover_ocdfg(source, OCDFGSpec(("Order",))),
        projected,
        title="Synthetic review: shared event pairs and projected Case DFG",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    document = review_document()
    write_visualization(document, args.output / "projection-review.json")
    export_html(document, args.output / "projection-review.html")


if __name__ == "__main__":
    main()
