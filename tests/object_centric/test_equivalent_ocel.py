"""Independent small-structure oracles for exact leading-object equivalence."""

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.equivalent_ocel import (
    EquivalentOCELSet,
    EquivalentOCELSpec,
    cluster_equivalent_ocel,
)
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def make(objects, rows, o2o=(), declared=()):
    """Rows: event ID, activity, seconds, qualified participants."""
    return OCEL(
        event_types=tuple(
            EventType(activity) for activity in sorted({r[1] for r in rows})
        ),
        object_types=tuple(
            ObjectType(kind) for kind in sorted(set(objects.values()) | set(declared))
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects.items()),
        events=tuple(
            Event(eid, act, T0 + timedelta(seconds=second))
            for eid, act, second, _ in rows
        ),
        e2o=tuple(
            E2O(eid, oid, role)
            for eid, _, _, participation in rows
            for oid, role in participation
        ),
        o2o=tuple(O2O(*row) for row in o2o),
    )


def two_orders():
    return make(
        {"a": "Order", "b": "Order", "x": "Item", "y": "Item"},
        (
            ("e1", "create", 0, (("a", "owner"), ("x", "part"))),
            ("e2", "finish", 1, (("a", "owner"), ("x", "part"))),
            ("z9", "create", 50, (("b", "owner"), ("y", "part"))),
            ("z8", "finish", 90, (("b", "owner"), ("y", "part"))),
        ),
    )


def renaming(log, objects, events):
    return replace(
        log,
        objects=tuple(replace(o, id=objects[o.id]) for o in reversed(log.objects)),
        events=tuple(replace(e, id=events[e.id]) for e in reversed(log.events)),
        e2o=tuple(
            E2O(events[r.event], objects[r.object], r.qualifier)
            for r in reversed(log.e2o)
        ),
        o2o=tuple(
            O2O(objects[r.source], objects[r.target], r.qualifier)
            for r in reversed(log.o2o)
        ),
    )


class EquivalentOCELTests(unittest.TestCase):
    def calculate(self, log, **kwargs):
        result = cluster_equivalent_ocel(log, EquivalentOCELSpec("Order", **kwargs))
        self.assertEqual(result.status, ComputeStatus.COMPUTED, result.issues)
        return result

    def test_equivalent_renamed_orders_have_one_exact_cluster(self):
        result = self.calculate(two_orders())
        value = result.value
        self.assertTrue(value.exact)
        self.assertEqual([c.leading_object_ids for c in value.clusters], [("a", "b")])
        self.assertEqual(value.clusters[0].frequency, 2)
        self.assertEqual(
            value.scopes[0].canonical_encoding, value.scopes[1].canonical_encoding
        )
        self.assertEqual(value.unassigned_event_ids, ())
        self.assertIsNotNone(result.source_digest)
        self.assertIsNotNone(result.computation_id)

    def test_renaming_and_row_permutation_preserve_encoding(self):
        source = two_orders()
        renamed = renaming(
            source,
            {"a": "zz", "b": "aa", "x": "qq", "y": "pp"},
            {"e1": "100", "e2": "000", "z9": "2", "z8": "1"},
        )
        original = self.calculate(source)
        changed = self.calculate(renamed)
        self.assertEqual(
            original.value.clusters[0].canonical_encoding,
            changed.value.clusters[0].canonical_encoding,
        )
        self.assertNotEqual(original.source_digest, changed.source_digest)

    def test_absolute_time_shift_and_dilation_do_not_change_structure(self):
        source = two_orders()
        shifted = replace(
            source,
            events=tuple(
                replace(e, time=T0 + (e.time - T0) * 3 + timedelta(days=5))
                for e in source.events
            ),
        )
        self.assertEqual(
            self.calculate(source).value.clusters,
            self.calculate(shifted).value.clusters,
        )

    def test_activity_changes_separate_groups(self):
        source = two_orders()
        changed = replace(
            source,
            events=tuple(
                replace(e, type="create") if e.id == "z8" else e for e in source.events
            ),
        )
        self.assertEqual(len(self.calculate(changed).value.clusters), 2)

    def test_object_type_changes_separate_groups(self):
        source = two_orders()
        changed = replace(
            source,
            object_types=(*source.object_types, ObjectType("Package")),
            objects=tuple(
                replace(o, type="Package") if o.id == "y" else o for o in source.objects
            ),
        )
        self.assertEqual(len(self.calculate(changed).value.clusters), 2)

    def test_qualified_roles_are_structural(self):
        source = two_orders()
        changed = replace(
            source,
            e2o=tuple(
                replace(r, qualifier="output") if r.object == "y" else r
                for r in source.e2o
            ),
        )
        self.assertEqual(len(self.calculate(changed).value.clusters), 2)

    def test_qualifier_selection_controls_scope_and_preserves_selected_labels(self):
        value = self.calculate(two_orders(), qualifiers=("owner",)).value
        self.assertEqual([s.object_ids for s in value.scopes], [("a",), ("b",)])
        self.assertEqual(value.unassigned_object_ids, ("x", "y"))
        self.assertEqual(len(value.clusters), 1)

    def test_none_and_empty_qualifier_selection_are_different(self):
        source = two_orders()
        value = self.calculate(source, qualifiers=()).value
        self.assertEqual([s.event_ids for s in value.scopes], [(), ()])
        self.assertEqual(value.unassigned_event_ids, ("e1", "e2", "z8", "z9"))
        self.assertNotEqual(
            value.clusters[0].canonical_encoding,
            self.calculate(source).value.clusters[0].canonical_encoding,
        )

    def test_multiple_qualifiers_do_not_duplicate_events_or_orders(self):
        source = two_orders()
        extra = replace(source, e2o=(*source.e2o, E2O("e1", "a", "also")))
        value = self.calculate(extra).value
        scope = value.scopes[0]
        labels, relations = json.loads(scope.canonical_encoding)
        self.assertEqual(sum(label[0] == "event" for label in labels), 2)
        self.assertEqual(sum(r[0] == "order" for r in relations), 2)
        self.assertEqual(sum(r[0] == "e2o" for r in relations), 5)

    def test_local_activity_order_changes_separate_groups(self):
        source = two_orders()
        swapped = replace(
            source,
            events=tuple(
                replace(e, time=T0 + timedelta(seconds=100)) if e.id == "z9" else e
                for e in source.events
            ),
        )
        self.assertEqual(len(self.calculate(swapped).value.clusters), 2)

    def test_default_tie_rejection_is_unavailable_without_partial_groups(self):
        source = two_orders()
        tied = replace(
            source,
            events=tuple(
                replace(e, time=T0 + timedelta(seconds=50)) if e.id == "z8" else e
                for e in source.events
            ),
        )
        result = cluster_equivalent_ocel(tied, EquivalentOCELSpec("Order"))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].code, "ambiguous_event_order")

    def test_explicit_event_id_tie_policy_records_its_evidence(self):
        source = two_orders()
        tied = replace(
            source,
            events=tuple(
                replace(e, time=T0 + timedelta(seconds=50)) if e.id == "z8" else e
                for e in source.events
            ),
        )
        result = self.calculate(tied, tie_policy="event_id")
        self.assertEqual(result.issues[0].code, "event_id_tie_order")
        self.assertEqual(
            len(result.value.clusters), 2
        )  # z8 finish sorts before z9 create.
        self.assertTrue(
            any(edge.tie_broken for edge in result.value.scopes[1].order_edges)
        )

    def test_shared_event_remains_one_vertex_and_overlaps_are_explicit(self):
        source = make(
            {"a": "Order", "b": "Order"},
            (("shared", "act", 0, (("a", "p"), ("b", "p"))),),
        )
        value = self.calculate(source).value
        self.assertEqual(value.overlapping_event_ids, ("shared",))
        self.assertEqual(value.overlapping_object_ids, ("a", "b"))
        self.assertEqual(value.clusters[0].frequency, 2)
        labels, relations = json.loads(value.clusters[0].canonical_encoding)
        self.assertEqual(sum(label[0] == "event" for label in labels), 1)
        self.assertEqual(sum(row[0] == "e2o" for row in relations), 2)

    def test_anchor_role_distinguishes_same_whole_scope(self):
        source = make(
            {"a": "Order", "b": "Order"},
            (
                ("shared", "join", 0, (("a", "p"), ("b", "p"))),
                ("later", "finish", 1, (("a", "p"),)),
            ),
        )
        value = self.calculate(source).value
        self.assertEqual(value.scopes[0].event_ids, value.scopes[1].event_ids)
        self.assertEqual(len(value.clusters), 2)

    def test_birth_ties_are_an_explicit_scope_choice(self):
        source = make(
            {"a": "Order", "x": "Item"},
            (
                ("start", "join", 0, (("a", "p"), ("x", "p"))),
                ("later", "finish", 1, (("x", "p"),)),
            ),
        )
        bidirectional = self.calculate(source).value.scopes[0]
        excluded = self.calculate(source, birth_ties="exclude").value.scopes[0]
        self.assertEqual(bidirectional.object_ids, ("a", "x"))
        self.assertEqual(excluded.object_ids, ("a",))
        self.assertEqual(excluded.event_ids, ("start",))

    def test_ancestors_union_descendants_is_not_connected_component(self):
        # a -> x <- y: y is not an ancestor/descendant of a.
        source = make(
            {"a": "Order", "x": "Item", "y": "Resource"},
            (
                ("a0", "init", 0, (("a", "p"),)),
                ("y0", "init", 1, (("y", "p"),)),
                ("ax", "meet", 2, (("a", "p"), ("x", "p"))),
                ("yx", "meet", 3, (("y", "p"), ("x", "p"))),
            ),
        )
        scope = self.calculate(source).value.scopes[0]
        self.assertEqual(scope.object_ids, ("a", "x"))
        self.assertEqual(scope.event_ids, ("a0", "ax", "yx"))
        self.assertNotIn("y0", scope.event_ids)

    def test_eventless_anchor_is_a_real_empty_scope(self):
        source = make({"a": "Order", "b": "Order", "x": "Item"}, ())
        value = self.calculate(source).value
        self.assertEqual(value.clusters[0].frequency, 2)
        self.assertEqual(value.unassigned_object_ids, ("x",))
        self.assertEqual(value.search_states, 2)

    def test_no_anchors_returns_computed_empty_partition(self):
        source = make({"x": "Item"}, (), declared=("Order",))
        value = self.calculate(source).value
        self.assertEqual(value.scopes, ())
        self.assertEqual(value.clusters, ())
        self.assertEqual(value.search_states, 0)

    def test_unknown_type_is_unavailable(self):
        result = cluster_equivalent_ocel(make({}, ()), EquivalentOCELSpec("Order"))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(result.issues[0].code, "unknown_object_type")

    def test_object_type_selection_prunes_incidence(self):
        value = self.calculate(two_orders(), object_types=("Order",)).value
        self.assertEqual(value.scopes[0].object_ids, ("a",))
        self.assertEqual(value.unassigned_object_ids, ("x", "y"))

    def test_o2o_never_expands_scope(self):
        source = replace(two_orders(), o2o=(O2O("a", "b", "link"),))
        value = self.calculate(source, o2o="qualified").value
        self.assertEqual(value.scopes[0].object_ids, ("a", "x"))
        self.assertEqual(value.scopes[1].object_ids, ("b", "y"))

    def test_o2o_direction_and_qualifier_preserved_only_when_selected(self):
        source = replace(
            two_orders(), o2o=(O2O("a", "x", "link"), O2O("y", "b", "link"))
        )
        self.assertEqual(len(self.calculate(source).value.clusters), 1)
        self.assertEqual(len(self.calculate(source, o2o="qualified").value.clusters), 2)
        self.assertEqual(
            len(
                self.calculate(
                    source, o2o="qualified", o2o_qualifiers=()
                ).value.clusters
            ),
            1,
        )
        reversed_role = replace(
            source, o2o=(O2O("a", "x", "link"), O2O("b", "y", "other"))
        )
        self.assertEqual(
            len(self.calculate(reversed_role, o2o="qualified").value.clusters), 2
        )

    def test_symmetric_regular_nonisomorphic_graphs_do_not_collapse(self):
        # Equal vertex counts, degrees and colour refinements: directed C6 vs 2*C3.
        objects = {"a": "Order", "b": "Order"}
        for prefix in ("x", "y"):
            objects.update({f"{prefix}{i}": "Item" for i in range(6)})
        rows = (
            (
                "e1",
                "join",
                0,
                tuple((oid, "p") for oid in ("a", *(f"x{i}" for i in range(6)))),
            ),
            (
                "e2",
                "join",
                5,
                tuple((oid, "p") for oid in ("b", *(f"y{i}" for i in range(6)))),
            ),
        )
        o2o = tuple((f"x{i}", f"x{(i + 1) % 6}", "edge") for i in range(6)) + tuple(
            (f"y{i}", f"y{(i // 3) * 3 + (i + 1) % 3}", "edge") for i in range(6)
        )
        source = make(objects, rows, o2o)
        result = self.calculate(source, o2o="qualified")
        self.assertEqual(len(result.value.clusters), 2)
        self.assertEqual(result.value.search_states, 1440)
        renamed = renaming(
            source,
            {oid: "renamed_" + oid[::-1] for oid in objects},
            {"e1": "e9", "e2": "e0"},
        )
        self.assertEqual(
            {c.canonical_encoding for c in result.value.clusters},
            {
                c.canonical_encoding
                for c in self.calculate(renamed, o2o="qualified").value.clusters
            },
        )

    def test_fingerprint_collision_does_not_merge_distinct_structures(self):
        source = replace(two_orders(), o2o=(O2O("a", "x", "link"),))
        with patch(
            "pix.object_centric.equivalent_ocel._signature", return_value="same"
        ):
            value = self.calculate(source, o2o="qualified").value
        self.assertEqual(len(value.clusters), 2)
        self.assertEqual({c.canonical_signature for c in value.clusters}, {"same"})

    def test_search_limit_is_global_and_yields_no_partial_clusters(self):
        result = cluster_equivalent_ocel(
            two_orders(), EquivalentOCELSpec("Order", max_search_states=1)
        )
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].code, "limit_exceeded")

    def test_scope_limit_rejects_truncation(self):
        result = cluster_equivalent_ocel(
            two_orders(), EquivalentOCELSpec("Order", max_scopes=1)
        )
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].code, "scope_limit_exceeded")

    def test_input_validation_and_context_path(self):
        invalid = cluster_equivalent_ocel(None, EquivalentOCELSpec("Order"))
        self.assertEqual(invalid.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(
            self.calculate(two_orders()),
            self.calculate(ComputationContext(two_orders())),
        )
        with self.assertRaises(TypeError):
            cluster_equivalent_ocel(two_orders(), None)

    def test_spec_validation_and_immutable_payloads(self):
        invalid = (
            {"max_search_states": True},
            {"max_scopes": 0},
            {"tie_policy": "random"},
            {"birth_ties": "object_id"},
            {"o2o": "all"},
            {"profile": "reference"},
            {"object_types": ("Item",)},
            {"qualifiers": ["q"]},
            {"o2o_qualifiers": ("q",)},
        )
        for kw in invalid:
            with self.subTest(kw=kw), self.assertRaises((TypeError, ValueError)):
                EquivalentOCELSpec("Order", **kw)
        spec = EquivalentOCELSpec("Order", qualifiers=("b", "a", "b"))
        self.assertEqual(spec.qualifiers, ("a", "b"))
        value = self.calculate(two_orders()).value
        self.assertIsInstance(value, EquivalentOCELSet)
        with self.assertRaises(FrozenInstanceError):
            value.search_states = 0
        with self.assertRaises(ValueError):
            replace(value, clusters=())
        with self.assertRaises(ValueError):
            replace(value.clusters[0], canonical_signature="wrong")


if __name__ == "__main__":
    unittest.main()
