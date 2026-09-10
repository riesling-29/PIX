"""Run a small native PIX pipeline in a temporary workspace."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.dont_write_bytecode = True
PROPOSAL_ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(PROPOSAL_ROOT), str(PROPOSAL_ROOT.parents[2] / "src")]

from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

from pix_native_proposal.compute import TraceSpec
from pix_native_proposal.engine import DFGRequest, TraceRequest, compute
from pix_native_proposal.io import export_ocel
from pix_native_proposal.result_json import result_document


def main() -> None:
    log = OCEL(
        event_types=(EventType("Create"), EventType("Pay")),
        object_types=(ObjectType("order"),),
        events=(
            Event("e2", "Pay", datetime(2026, 9, 9, 10, tzinfo=timezone.utc)),
            Event("e1", "Create", datetime(2026, 9, 9, 9, tzinfo=timezone.utc)),
        ),
        objects=(Object("o1", "order"), Object("o2", "order")),
        e2o=(E2O("e1", "o1", "order"), E2O("e2", "o1", "order")),
    )
    traces, graph = compute(
        log,
        requests=(TraceRequest(TraceSpec("order")), DFGRequest(TraceSpec("order"))),
    )
    with TemporaryDirectory(prefix="pix-native-proposal-") as scratch:
        output = Path(scratch)
        exported = [
            export_ocel(log, output / "orders.json", format="ocel20-json"),
            export_ocel(log, output / "orders.sqlite", format="ocel20-sqlite"),
        ]
        print(json.dumps({
            "exports": [
                {
                    "format": item.format,
                    "source_canonical_digest": item.source_canonical_digest.identifier,
                    "roundtrip_canonical_digest": item.roundtrip_canonical_digest.identifier,
                    "reference_schema": item.reference_schema,
                }
                for item in exported
            ],
            "traces": result_document(traces),
            "dfg": result_document(graph),
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
