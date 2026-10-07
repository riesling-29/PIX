"""Independent expected outputs for the composed native path."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType, read_ocel

from pix_native_proposal.compute import ComputeStatus, TraceSpec
from pix_native_proposal.engine import DFGRequest, TraceRequest, compute
from pix_native_proposal.io import export_ocel
from pix_native_proposal.result_json import result_json_bytes


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = OCEL(
            event_types=(EventType("Create"), EventType("Pay")),
            object_types=(ObjectType("order"),),
            events=(
                Event("e2", "Pay", datetime(2026, 9, 9, 10, tzinfo=timezone.utc)),
                Event("e1", "Create", datetime(2026, 9, 9, 9, tzinfo=timezone.utc)),
            ),
            objects=(Object("o1", "order"), Object("o2", "order")),
            e2o=(E2O("e1", "o1", "input"), E2O("e2", "o1", "output")),
        )

    def test_files_feed_identical_native_computation(self) -> None:
        request = DFGRequest(TraceSpec("order"))
        before = compute(self.log, requests=(request,))[0]
        self.assertIs(before.status, ComputeStatus.COMPUTED)
        self.assertEqual(before.value.empty_object_ids, ("o2",))
        edges = before.value.edges
        self.assertEqual(len(edges), 1)
        self.assertEqual((edges[0].source_activity, edges[0].target_activity), ("Create", "Pay"))
        self.assertEqual(edges[0].occurrence_count, 1)
        self.assertEqual(edges[0].evidence[0].object_id, "o1")
        self.assertEqual(edges[0].evidence[0].source_event_id, "e1")
        self.assertEqual(edges[0].evidence[0].target_event_id, "e2")

        with TemporaryDirectory() as scratch:
            for format_name, extension in (("ocel20-json", "json"), ("ocel20-sqlite", "sqlite")):
                path = Path(scratch) / f"log.{extension}"
                exported = export_ocel(self.log, path, format=format_name)
                self.assertEqual(exported.reference_schema, "not_run")
                after = compute(read_ocel(path), requests=(request,))[0]
                self.assertEqual(result_json_bytes(before), result_json_bytes(after))

    def test_success_and_unavailable_stay_separate(self) -> None:
        available, unavailable = compute(
            self.log,
            requests=(TraceRequest(TraceSpec("order")), DFGRequest(TraceSpec("missing"))),
        )
        self.assertIs(available.status, ComputeStatus.COMPUTED)
        self.assertIs(unavailable.status, ComputeStatus.UNAVAILABLE)
        document = json.loads(result_json_bytes(unavailable))
        self.assertIsNone(document["computation"]["value"])
        self.assertEqual(document["computation"]["status"], "unavailable")
        self.assertTrue(document["computation"]["issues"])
        self.assertNotIn("eventTypes", document)
        self.assertEqual(document["format"], "pix.analysis-result")

    def test_requests_are_explicit(self) -> None:
        with self.assertRaises(ValueError):
            compute(self.log, requests=())
        with self.assertRaises(TypeError):
            compute(self.log, requests=("discover_dfg",))
        with self.assertRaises(TypeError):
            TraceRequest("order")


if __name__ == "__main__":
    unittest.main()
