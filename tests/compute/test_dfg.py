"""Native DFG occurrence and boundary counts checked against small-log oracles."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.compute.dfg import discover_dfg
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType


def shared_event_log() -> OCEL:
    """Two traces share join; an isolated and a single-event object also exist."""
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(
            EventType(name)
            for name in ("create", "join", "close", "solo", "disconnected")
        ),
        object_types=(ObjectType("order"), ObjectType("unused")),
        events=(
            Event("e1", "create", origin),
            Event("e2", "join", origin + timedelta(seconds=1)),
            Event("e3", "close", origin + timedelta(seconds=2)),
            Event("e4", "solo", origin + timedelta(seconds=3)),
            Event("orphan", "disconnected", origin),
        ),
        objects=tuple(
            Object(name, "order") for name in ("o1", "o2", "isolated", "single")
        ),
        e2o=(
            E2O("e1", "o1", "input"),
            E2O("e1", "o1", "audit"),
            E2O("e2", "o1", "input"),
            E2O("e2", "o2", "input"),
            E2O("e3", "o2", "input"),
            E2O("e4", "single", ""),
        ),
        o2o=(O2O("isolated", "o2", "related"), O2O("o1", "o2", "related")),
    )


def trace_ids(result):
    return {
        trace.object_id: tuple(event.event_id for event in trace.events)
        for trace in result.value.traces
    }


class NativeComputationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.log = shared_event_log()
        self.spec = TraceSpec("order")

    def test_shared_event_does_not_add_cross_object_edges(self) -> None:
        result = discover_dfg(self.log, self.spec)
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(
            [
                (edge.source_activity, edge.target_activity, edge.occurrence_count)
                for edge in result.value.edges
            ],
            [("create", "join", 1), ("join", "close", 1)],
        )
        self.assertEqual(
            [
                (e.object_id, e.source_event_id, e.target_event_id)
                for edge in result.value.edges
                for e in edge.evidence
            ],
            [("o1", "e1", "e2"), ("o2", "e2", "e3")],
        )

    def test_o2o_does_not_inherit_events_or_connect_traces(self) -> None:
        without_o2o = replace(self.log, o2o=())
        self.assertEqual(
            reconstruct_traces(self.log, self.spec).value,
            reconstruct_traces(without_o2o, self.spec).value,
        )
        self.assertEqual(
            discover_dfg(self.log, self.spec).value,
            discover_dfg(without_o2o, self.spec).value,
        )
        # The dataset identity still includes O2O, despite this operator ignoring it.
        self.assertNotEqual(
            discover_dfg(self.log, self.spec).source_digest,
            discover_dfg(without_o2o, self.spec).source_digest,
        )

    def test_isolated_singleton_and_activity_count_semantics(self) -> None:
        graph = discover_dfg(self.log, self.spec).value
        self.assertEqual(graph.object_count, 4)
        self.assertEqual(graph.empty_object_ids, ("isolated",))
        self.assertEqual(
            [
                (a.activity, a.event_occurrence_count, a.distinct_event_ids)
                for a in graph.activities
            ],
            [
                ("close", 1, ("e3",)),
                ("create", 1, ("e1",)),
                ("join", 2, ("e2",)),
                ("solo", 1, ("e4",)),
            ],
        )
        self.assertEqual(
            [
                (b.activity, tuple((e.object_id, e.event_id) for e in b.evidence))
                for b in graph.starts
            ],
            [
                ("create", (("o1", "e1"),)),
                ("join", (("o2", "e2"),)),
                ("solo", (("single", "e4"),)),
            ],
        )
        self.assertEqual(
            [(b.activity, tuple(e.object_id for e in b.evidence)) for b in graph.ends],
            [("close", ("o2",)), ("join", ("o1",)), ("solo", ("single",))],
        )

    def test_shared_event_pair_counts_once_per_object(self) -> None:
        log = replace(self.log, e2o=self.log.e2o + (E2O("e1", "o2", "input"),))
        graph = discover_dfg(log, self.spec).value
        edge = next(e for e in graph.edges if e.source_activity == "create")
        self.assertEqual(edge.occurrence_count, 2)
        self.assertEqual(tuple(e.object_id for e in edge.evidence), ("o1", "o2"))

    def test_duplicate_relation_is_invalid_not_silently_deduplicated(self) -> None:
        broken = replace(self.log, e2o=self.log.e2o + (self.log.e2o[0],))
        result = discover_dfg(broken, self.spec)
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "duplicate_e2o")
