"""Independent small incidence graphs; no reference-library execution."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pix.results as persistence
from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.relations import (
    AttributeAsOfSpec,
    ETOTEdge,
    ETOTGraph,
    ETOTSpec,
    GraphComparisonRequest,
    ObjectGraphSpec,
    ObjectRelationSpec,
    OCELScalar,
    OTGSpec,
    compare_object_graphs,
    discover_etot,
    discover_object_graph,
    discover_otg,
    object_attributes_as_of,
    query_object_relations,
)
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    canonical_digest,
)

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def example():
    """a introduces b then c; b and c finish when d/e appear together."""
    return OCEL(
        event_types=tuple(EventType(item) for item in ("A", "B", "C", "D", "unused")),
        object_types=(
            ObjectType(
                "Order",
                (
                    Attribute("state", ValueType.STRING),
                    Attribute("scheduled", ValueType.TIME),
                ),
            ),
            ObjectType("Item"),
            ObjectType("Ship"),
            ObjectType("Unused"),
        ),
        events=tuple(
            Event(f"e{index}", name, T0 + timedelta(seconds=index - 1))
            for index, name in enumerate(("A", "B", "C", "D"), 1)
        ),
        objects=(
            Object(
                "a",
                "Order",
                (
                    ObjectAttr("state", "future", T0 + timedelta(seconds=5)),
                    ObjectAttr("state", "old", T0 - timedelta(seconds=1)),
                    ObjectAttr("state", "new", T0 + timedelta(seconds=2)),
                    ObjectAttr(
                        "scheduled", T0 + timedelta(days=3), T0 + timedelta(seconds=1)
                    ),
                ),
            ),
            Object("b", "Item"),
            Object("c", "Item"),
            Object("d", "Ship"),
            Object("e", "Ship"),
            Object("z", "Unused"),
        ),
        e2o=tuple(
            E2O(event, obj, "flow")
            for event, objects in (
                ("e1", "a"),
                ("e2", "ab"),
                ("e3", "ac"),
                ("e4", "bcde"),
            )
            for obj in objects
        )
        + (E2O("e2", "a", "audit"),),
        o2o=(
            O2O("a", "b", "contains"),
            O2O("b", "a", "parent"),
            O2O("a", "c", "contains"),
        ),
    )


class ObjectGraphTests(unittest.TestCase):
    def test_five_graphs_hand_counted(self):
        expected = {
            "interaction": {
                ("a", "b"),
                ("a", "c"),
                ("b", "c"),
                ("b", "d"),
                ("b", "e"),
                ("c", "d"),
                ("c", "e"),
                ("d", "e"),
            },
            "descendants": {
                ("a", "b"),
                ("a", "c"),
                ("b", "d"),
                ("b", "e"),
                ("c", "d"),
                ("c", "e"),
            },
            "inheritance": {("a", "c"), ("b", "d"), ("b", "e"), ("c", "d"), ("c", "e")},
            "cobirth": {("d", "e")},
            "codeath": {
                ("b", "c"),
                ("b", "d"),
                ("b", "e"),
                ("c", "d"),
                ("c", "e"),
                ("d", "e"),
            },
        }
        for kind, pairs in expected.items():
            with self.subTest(kind=kind):
                result = discover_object_graph(example(), ObjectGraphSpec(kind))
                self.assertEqual(result.status, ComputeStatus.COMPUTED)
                self.assertEqual(
                    {(edge.source, edge.target) for edge in result.value.edges}, pairs
                )
                self.assertEqual(len(result.value.nodes), 6)
                self.assertEqual(
                    result.value.directed, kind in ("descendants", "inheritance")
                )
                self.assertTrue(
                    all(len(edge.event_ids) == 1 for edge in result.value.edges)
                )

    def test_shared_events_count_once_per_role_and_distinct_witness(self):
        log = example()
        later = replace(
            log,
            events=log.events + (Event("again", "B", T0 + timedelta(seconds=8)),),
            e2o=log.e2o + (E2O("again", "a", "flow"), E2O("again", "b", "flow")),
        )
        graph = discover_object_graph(later).value
        edge = next(
            edge for edge in graph.edges if (edge.source, edge.target) == ("a", "b")
        )
        self.assertEqual(edge.event_ids, ("again", "e2"))
        self.assertFalse(any(edge.source == edge.target for edge in graph.edges))

    def test_qualifiers_empty_and_nonmatching(self):
        for qualifiers in ((), ("unknown",), ("audit",)):
            result = discover_object_graph(
                example(), ObjectGraphSpec(qualifiers=qualifiers)
            )
            self.assertEqual(result.value.edges, ())
            self.assertEqual(len(result.value.nodes), 6)

    def test_order_ties_reject_but_interaction_unaffected(self):
        log = example()
        tied = replace(
            log,
            events=(log.events[0], replace(log.events[1], time=T0)) + log.events[2:],
        )
        self.assertEqual(discover_object_graph(tied).status, ComputeStatus.COMPUTED)
        rejected = discover_object_graph(tied, ObjectGraphSpec("descendants"))
        self.assertEqual(rejected.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(rejected.value)
        accepted = discover_object_graph(
            tied, ObjectGraphSpec("descendants", tie_policy="event_id")
        )
        self.assertEqual(accepted.status, ComputeStatus.COMPUTED)
        self.assertIn("timestamp_tie_broken", {issue.code for issue in accepted.issues})

    def test_same_timestamp_different_event_is_not_cobirth(self):
        log = example()
        independent = replace(
            log,
            events=(Event("one", "A", T0), Event("two", "A", T0)),
            e2o=(E2O("one", "a", "flow"), E2O("two", "b", "flow")),
        )
        result = discover_object_graph(independent, ObjectGraphSpec("cobirth"))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.edges, ())

    def test_source_permutation_context_and_immutability(self):
        log = example()
        digest = canonical_digest(log)
        for kind in ("interaction", "descendants", "inheritance", "cobirth", "codeath"):
            spec = ObjectGraphSpec(kind)
            direct = discover_object_graph(log, spec)
            permutation = replace(
                log,
                objects=tuple(reversed(log.objects)),
                events=tuple(reversed(log.events)),
                e2o=tuple(reversed(log.e2o)),
            )
            self.assertEqual(
                direct, discover_object_graph(ComputationContext(permutation), spec)
            )
        self.assertEqual(digest, canonical_digest(log))
        with self.assertRaises(FrozenInstanceError):
            direct.value.directed = False

    def test_invalid_canonical_input(self):
        invalid = replace(example(), e2o=(E2O("e1", "missing", "flow"),))
        self.assertEqual(
            discover_object_graph(invalid).status, ComputeStatus.INVALID_INPUT
        )

    def test_empty(self):
        log = OCEL()
        for kind in ("interaction", "descendants", "inheritance", "cobirth", "codeath"):
            result = discover_object_graph(log, ObjectGraphSpec(kind))
            self.assertEqual(result.status, ComputeStatus.COMPUTED)
            self.assertEqual(result.value.nodes, ())
            self.assertEqual(result.value.edges, ())


class TypeGraphTests(unittest.TestCase):
    def test_etot_frequency_profiles(self):
        expected = {
            "qualified_relations": 2,
            "event_object_pairs": 1,
            "events": 1,
            "objects": 1,
        }
        for profile, count in expected.items():
            with self.subTest(profile=profile):
                graph = discover_etot(example(), ETOTSpec(frequency=profile)).value
                edge = next(
                    item
                    for item in graph.edges
                    if (item.activity, item.object_type) == ("B", "Order")
                )
                self.assertEqual(edge.frequency, count)
                self.assertNotIn("unused", graph.activities)
                self.assertNotIn("Unused", graph.object_types)
        graph = discover_etot(example(), ETOTSpec(include_declared_types=True)).value
        self.assertIn("unused", graph.activities)
        self.assertIn("Unused", graph.object_types)

    def test_events_and_objects_are_distinct_populations(self):
        graph = discover_etot(example(), ETOTSpec(frequency="events")).value
        self.assertEqual(
            next(
                edge.frequency
                for edge in graph.edges
                if (edge.activity, edge.object_type) == ("D", "Item")
            ),
            1,
        )
        graph = discover_etot(example(), ETOTSpec(frequency="objects")).value
        self.assertEqual(
            next(
                edge.frequency
                for edge in graph.edges
                if (edge.activity, edge.object_type) == ("D", "Item")
            ),
            2,
        )

    def test_otg_hand_counted_and_orientation_profiles(self):
        graph = discover_otg(example()).value
        self.assertEqual(
            {
                (edge.source_type, edge.target_type): edge.object_pair_count
                for edge in graph.edges
                if edge.relation == "interaction"
            },
            {
                ("Item", "Order"): 2,
                ("Item", "Item"): 1,
                ("Item", "Ship"): 4,
                ("Ship", "Ship"): 1,
            },
        )
        self.assertEqual(
            {
                (edge.source_type, edge.target_type): edge.object_pair_count
                for edge in graph.edges
                if edge.relation == "inheritance"
            },
            {("Order", "Item"): 1, ("Item", "Ship"): 4},
        )
        lexical = discover_otg(
            example(), OTGSpec(undirected_orientation="object_id")
        ).value
        self.assertIn(
            ("Order", "Item"),
            {
                (edge.source_type, edge.target_type)
                for edge in lexical.edges
                if edge.relation == "interaction"
            },
        )
        self.assertIn("Unused", graph.object_types)

    def test_empty_and_none_qualifier_distinct(self):
        self.assertEqual(discover_etot(OCEL()).value.edges, ())
        self.assertEqual(discover_otg(OCEL()).value.edges, ())
        self.assertEqual(
            discover_etot(example(), ETOTSpec(qualifiers=())).value.edges, ()
        )
        self.assertEqual(
            discover_otg(example(), OTGSpec(qualifiers=())).value.edges, ()
        )


class QueryTests(unittest.TestCase):
    def test_asof_boundary_no_future_values_and_missing(self):
        spec = AttributeAsOfSpec(
            T0 + timedelta(seconds=2), ("a",), ("state", "unknown", "scheduled")
        )
        result = object_attributes_as_of(example(), spec)
        values = {item.name: item for item in result.value.values}
        self.assertEqual(values["state"].value.native_value, "new")
        self.assertEqual(values["scheduled"].value.native_value, T0 + timedelta(days=3))
        self.assertEqual(values["state"].assigned_at, T0 + timedelta(seconds=2))
        self.assertFalse(values["unknown"].declared)
        self.assertIsNone(values["unknown"].value)
        exclusive = object_attributes_as_of(example(), replace(spec, inclusive=False))
        self.assertEqual(
            next(
                item.value.native_value
                for item in exclusive.value.values
                if item.name == "state"
            ),
            "old",
        )
        before = object_attributes_as_of(
            example(), replace(spec, at=T0 - timedelta(seconds=2))
        )
        self.assertTrue(all(item.value is None for item in before.value.values))

    def test_asof_timezone_normalization_and_identity(self):
        other_zone = (T0 + timedelta(seconds=2)).astimezone(
            timezone(timedelta(hours=9))
        )
        utc = AttributeAsOfSpec(T0 + timedelta(seconds=2), ("a",), ("state",))
        self.assertEqual(
            object_attributes_as_of(example(), utc).value,
            object_attributes_as_of(example(), replace(utc, at=other_zone)).value,
        )

    def test_unknown_object_and_empty_query(self):
        result = object_attributes_as_of(example(), AttributeAsOfSpec(T0, ("missing",)))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(
            object_attributes_as_of(example(), AttributeAsOfSpec(T0, ())).value.values,
            (),
        )

    def test_o2o_direction_qualifier_and_no_reversal(self):
        outbound = query_object_relations(
            example(), ObjectRelationSpec(("a",), qualifiers=("contains",))
        ).value
        self.assertEqual(
            outbound.relations, (O2O("a", "b", "contains"), O2O("a", "c", "contains"))
        )
        inbound = query_object_relations(
            example(), ObjectRelationSpec(("a",), "inbound")
        ).value
        self.assertEqual(inbound.relations, (O2O("b", "a", "parent"),))
        both = query_object_relations(
            example(), ObjectRelationSpec(("a", "b"), "both")
        ).value
        self.assertEqual(len(both.relations), 3)
        self.assertEqual(
            query_object_relations(
                example(), ObjectRelationSpec(("a",), qualifiers=())
            ).value.relations,
            (),
        )
        self.assertEqual(
            query_object_relations(example(), ObjectRelationSpec(("missing",))).status,
            ComputeStatus.UNAVAILABLE,
        )

    def test_spec_validation(self):
        for kwargs in (
            {"at": datetime(2026, 1, 1)},
            {"at": T0, "inclusive": 1},
            {"at": T0, "object_ids": ["a"]},
        ):
            with self.assertRaises((TypeError, ValueError)):
                AttributeAsOfSpec(**kwargs)
        with self.assertRaises(ValueError):
            ObjectGraphSpec("unknown")
        with self.assertRaises(ValueError):
            ObjectRelationSpec(("a",), "reversed")

    def test_typed_attribute_persistence_keeps_all_primitive_types(self):
        values = (
            ("text", ValueType.STRING, "2026-01-01T00:00:00.000000Z"),
            ("date", ValueType.TIME, T0),
            ("count", ValueType.INTEGER, 3),
            ("cost", ValueType.FLOAT, 3.5),
            ("flag", ValueType.BOOLEAN, False),
        )
        log = OCEL(
            object_types=(
                ObjectType(
                    "T", tuple(Attribute(name, kind) for name, kind, value in values)
                ),
            ),
            objects=(
                Object(
                    "o",
                    "T",
                    tuple(ObjectAttr(name, value, T0) for name, kind, value in values),
                ),
            ),
        )
        result = object_attributes_as_of(log, AttributeAsOfSpec(T0))
        restored = persistence.result_from_json(persistence.result_json_bytes(result))
        self.assertEqual(restored, result)
        restored_values = {
            item.name: item.value.native_value for item in restored.value.values
        }
        for name, kind, expected in values:
            with self.subTest(name=name):
                self.assertIs(type(restored_values[name]), type(expected))
                self.assertEqual(restored_values[name], expected)

    def test_invalid_typed_scalar(self):
        for kwargs in (
            {"kind": "time", "text_value": "2026-01-01"},
            {"kind": "integer", "integer_value": True},
            {"kind": "string", "text_value": "valid", "integer_value": 1},
            {"kind": "float", "float_value": float("nan")},
        ):
            with self.assertRaises((TypeError, ValueError)):
                OCELScalar(**kwargs)


class ComparisonTests(unittest.TestCase):
    def test_structure_and_frequency_are_not_collapsed(self):
        reference = ETOTGraph(
            ETOTSpec(),
            ("A", "B"),
            ("O",),
            (ETOTEdge("A", "O", 8), ETOTEdge("B", "O", 2)),
        )
        observed = replace(
            reference,
            activities=("A", "C"),
            edges=(ETOTEdge("A", "O", 3), ETOTEdge("C", "O", 4)),
        )
        result = compare_object_graphs(reference, observed)
        value = result.value
        self.assertEqual(
            (
                value.shared_edge_count,
                value.reference_edge_count,
                value.observed_edge_count,
            ),
            (1, 2, 2),
        )
        self.assertEqual(value.edge_coverage.value, 0.5)
        self.assertEqual(
            (value.structural_jaccard.numerator, value.structural_jaccard.denominator),
            (1, 3),
        )
        self.assertEqual(
            (
                value.reference_frequency,
                value.observed_frequency,
                value.shared_frequency,
            ),
            (10, 7, 3),
        )
        self.assertEqual(
            (value.weighted_jaccard.numerator, value.weighted_jaccard.denominator),
            (3, 14),
        )
        self.assertEqual(value.absolute_frequency_difference, 11)
        self.assertEqual(value.missing_edges, (("B", "O"),))
        self.assertEqual(value.unexpected_edges, (("C", "O"),))
        self.assertIsInstance(result.spec, GraphComparisonRequest)

    def test_empty_denominators_unknown_and_profile_mismatch(self):
        graph = discover_etot(OCEL()).value
        result = compare_object_graphs(graph, graph)
        self.assertIsNone(result.value.edge_coverage.value)
        self.assertIsNone(result.value.weighted_jaccard.value)
        mismatch = replace(graph, spec=ETOTSpec(frequency="events"))
        self.assertEqual(
            compare_object_graphs(graph, mismatch).status, ComputeStatus.UNAVAILABLE
        )
        with self.assertRaises(TypeError):
            compare_object_graphs(graph, discover_otg(OCEL()).value)

    def test_graph_input_reject_duplicate_and_invalid_frequencies(self):
        graph = ETOTGraph(ETOTSpec(), ("A",), ("O",), (ETOTEdge("A", "O", 0),))
        with self.assertRaises(ValueError):
            compare_object_graphs(graph, graph)
        graph = replace(graph, edges=(ETOTEdge("A", "O", 1), ETOTEdge("A", "O", 2)))
        with self.assertRaises(ValueError):
            compare_object_graphs(graph, graph)

    def test_graph_input_rejects_invalid_nodes_direction_and_witnesses(self):
        graph = discover_object_graph(example()).value
        edge = graph.edges[0]
        malformed = (
            replace(graph, directed=True),
            replace(graph, nodes=graph.nodes + (graph.nodes[0],)),
            replace(graph, nodes=()),
            replace(
                graph, edges=(replace(edge, source=edge.target, target=edge.source),)
            ),
            replace(graph, edges=(replace(edge, source=edge.target),)),
            replace(graph, edges=(replace(edge, event_ids=("e2", "e2")),)),
        )
        for bad in malformed:
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    compare_object_graphs(graph, bad)
        etot = discover_etot(example()).value
        with self.assertRaises(ValueError):
            compare_object_graphs(etot, replace(etot, activities=()))
        otg = discover_otg(example()).value
        with self.assertRaises(ValueError):
            compare_object_graphs(
                otg, replace(otg, edges=(replace(otg.edges[0], relation="unknown"),))
            )

    def test_all_graph_kinds_result_persistence(self):
        graphs = [
            discover_object_graph(example(), ObjectGraphSpec(kind))
            for kind in (
                "interaction",
                "descendants",
                "inheritance",
                "cobirth",
                "codeath",
            )
        ]
        graphs.extend((discover_etot(example()), discover_otg(example())))
        results = graphs + [
            compare_object_graphs(graph.value, graph.value) for graph in graphs
        ]
        results.append(query_object_relations(example(), ObjectRelationSpec(("a",))))
        for result in results:
            with self.subTest(operator=result.operator_id):
                self.assertEqual(
                    persistence.result_from_json(persistence.result_json_bytes(result)),
                    result,
                )


if __name__ == "__main__":
    unittest.main()
