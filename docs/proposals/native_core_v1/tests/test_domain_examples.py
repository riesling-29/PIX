"""Hand-checkable examples used in the domain architecture review."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

from pix_native_proposal.compute import TraceSpec, discover_dfg, reconstruct_traces


class DomainExampleTests(unittest.TestCase):
    def test_shared_shipment_has_three_distinct_counting_units(self) -> None:
        rows = (
            ("e1", "Create", 0, ("O1",)),
            ("e2", "Create", 1, ("O2",)),
            ("e3", "Pack", 5, ("O1", "O2", "P1")),
            ("e4", "Ship", 10, ("O1", "O2", "P1", "R1")),
            ("e5", "Create", 20, ("O3",)),
            ("e6", "Ship", 30, ("O3", "P2", "R1")),
            ("e7", "Check", 35, ("P2",)),
        )
        base = datetime(2026, 9, 9, 9, tzinfo=timezone.utc)
        object_types = {"O1": "order", "O2": "order", "O3": "order",
                        "P1": "package", "P2": "package", "R1": "resource"}
        log = OCEL(
            event_types=tuple(EventType(name) for name in ("Create", "Pack", "Ship", "Check")),
            object_types=tuple(ObjectType(name) for name in ("order", "package", "resource")),
            events=tuple(Event(eid, act, base + timedelta(minutes=minutes))
                         for eid, act, minutes, _ in rows),
            objects=tuple(Object(oid, kind) for oid, kind in object_types.items()),
            e2o=tuple(E2O(eid, oid, "participant")
                      for eid, _, _, objects in rows for oid in objects),
        )
        traces = reconstruct_traces(log, TraceSpec("order")).value.traces
        self.assertEqual([[e.event_id for e in trace.events] for trace in traces],
                         [["e1", "e3", "e4"], ["e2", "e3", "e4"], ["e5", "e6"]])
        self.assertEqual(sum(len(trace.events) for trace in traces), 8)
        self.assertEqual(len({e.event_id for trace in traces for e in trace.events}), 6)
        edge = next(edge for edge in discover_dfg(log, TraceSpec("order")).value.edges
                    if (edge.source_activity, edge.target_activity) == ("Pack", "Ship"))
        self.assertEqual(edge.occurrence_count, 2)
        self.assertEqual(len({(e.source_event_id, e.target_event_id) for e in edge.evidence}), 1)
        self.assertEqual(len({e.object_id for e in edge.evidence}), 2)

        def components(excluded_type: str | None) -> tuple[frozenset[str], ...]:
            neighbours = {eid: set() for eid, *_ in rows}
            for oid, kind in object_types.items():
                if kind == excluded_type:
                    continue
                linked = {eid for eid, _, _, objects in rows if oid in objects}
                for eid in linked:
                    neighbours[eid].update(linked - {eid})
            unseen = set(neighbours)
            groups = []
            while unseen:
                pending = [min(unseen)]
                found = set()
                while pending:
                    eid = pending.pop()
                    if eid in found:
                        continue
                    found.add(eid)
                    pending.extend(neighbours[eid] - found)
                unseen -= found
                groups.append(frozenset(found))
            return tuple(groups)

        self.assertEqual(len(components(None)), 1)
        self.assertEqual(set(components("resource")), {
            frozenset(("e1", "e2", "e3", "e4")), frozenset(("e5", "e6", "e7")),
        })

    def test_event_graph_equality_can_hide_object_identity_difference(self) -> None:
        # Same activity A at three ordered events. L has one object spanning
        # all three events; M changes the shared object between the two edges.
        left = ({"x", "a"}, {"x", "b"}, {"x", "c"})
        right = ({"x", "a"}, {"x", "y"}, {"y", "c"})

        def profile(rows: tuple[set[str], ...]) -> tuple:
            objects = set().union(*rows)
            edges: dict[tuple[int, int], int] = {}
            degrees = []
            for oid in sorted(objects):
                positions = [i for i, row in enumerate(rows) if oid in row]
                degrees.append(len(positions))
                for source, target in zip(positions, positions[1:]):
                    edges[(source, target)] = edges.get((source, target), 0) + 1
            return tuple(map(len, rows)), edges, tuple(sorted(degrees))

        l_nodes, l_edges, l_degrees = profile(left)
        r_nodes, r_edges, r_degrees = profile(right)
        self.assertEqual(l_nodes, r_nodes)
        self.assertEqual(l_edges, r_edges)
        self.assertEqual(l_degrees, (1, 1, 1, 3))
        self.assertEqual(r_degrees, (1, 1, 2, 2))
        self.assertNotEqual(l_degrees, r_degrees)


if __name__ == "__main__":
    unittest.main()
