"""Independent small-log oracles for the executable native-core proposal."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType
from pix_native_proposal.compute import (
    ComputationContext,
    ComputeStatus,
    InvalidOCELInput,
    TraceSpec,
    discover_dfg,
    reconstruct_traces,
)


def shared_event_log() -> OCEL:
    """Two traces share join; an isolated and a single-event object also exist."""
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(name) for name in (
            "create", "join", "close", "solo", "disconnected"
        )),
        object_types=(ObjectType("order"), ObjectType("unused")),
        events=(
            Event("e1", "create", origin),
            Event("e2", "join", origin + timedelta(seconds=1)),
            Event("e3", "close", origin + timedelta(seconds=2)),
            Event("e4", "solo", origin + timedelta(seconds=3)),
            Event("orphan", "disconnected", origin),
        ),
        objects=tuple(Object(name, "order") for name in (
            "o1", "o2", "isolated", "single"
        )),
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
            [(edge.source_activity, edge.target_activity, edge.occurrence_count)
             for edge in result.value.edges],
            [("create", "join", 1), ("join", "close", 1)],
        )
        self.assertEqual(
            [(e.object_id, e.source_event_id, e.target_event_id)
             for edge in result.value.edges for e in edge.evidence],
            [("o1", "e1", "e2"), ("o2", "e2", "e3")],
        )

    def test_multi_qualifier_is_one_occurrence_with_all_selected_evidence(self) -> None:
        result = reconstruct_traces(self.log, self.spec)
        self.assertEqual(trace_ids(result), {
            "isolated": (), "o1": ("e1", "e2"),
            "o2": ("e2", "e3"), "single": ("e4",),
        })
        first = next(t for t in result.value.traces if t.object_id == "o1").events[0]
        self.assertEqual(first.relations, (
            E2O("e1", "o1", "audit"), E2O("e1", "o1", "input")
        ))
        graph = discover_dfg(self.log, self.spec).value
        self.assertEqual(graph.edges[0].occurrence_count, 1)
        self.assertEqual(graph.edges[0].evidence[0].source_relations, first.relations)

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

    def test_qualifier_filter_selects_only_matching_evidence(self) -> None:
        result = reconstruct_traces(self.log, TraceSpec("order", ("audit",)))
        self.assertEqual(trace_ids(result), {
            "isolated": (), "o1": ("e1",), "o2": (), "single": (),
        })
        event = next(t for t in result.value.traces if t.object_id == "o1").events[0]
        self.assertEqual(event.relations, (E2O("e1", "o1", "audit"),))

    def test_none_empty_filter_and_empty_string_qualifier_are_distinct(self) -> None:
        none = reconstruct_traces(self.log, TraceSpec("order", None))
        empty = reconstruct_traces(self.log, TraceSpec("order", ()))
        blank = reconstruct_traces(self.log, TraceSpec("order", ("",)))
        self.assertEqual(trace_ids(empty), {
            "isolated": (), "o1": (), "o2": (), "single": (),
        })
        self.assertEqual(trace_ids(blank), {
            "isolated": (), "o1": (), "o2": (), "single": ("e4",),
        })
        self.assertEqual(len({r.computation_id for r in (none, empty, blank)}), 3)

    def test_isolated_singleton_and_activity_count_semantics(self) -> None:
        graph = discover_dfg(self.log, self.spec).value
        self.assertEqual(graph.object_count, 4)
        self.assertEqual(graph.empty_object_ids, ("isolated",))
        self.assertEqual(
            [(a.activity, a.event_occurrence_count, a.distinct_event_ids)
             for a in graph.activities],
            [("close", 1, ("e3",)), ("create", 1, ("e1",)),
             ("join", 2, ("e2",)), ("solo", 1, ("e4",))],
        )
        self.assertEqual(
            [(b.activity, tuple((e.object_id, e.event_id) for e in b.evidence))
             for b in graph.starts],
            [("create", (("o1", "e1"),)), ("join", (("o2", "e2"),)),
             ("solo", (("single", "e4"),))],
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

    def test_unknown_type_is_unavailable_but_declared_empty_type_is_computed(self) -> None:
        for operator in (reconstruct_traces, discover_dfg):
            with self.subTest(operator=operator.__name__):
                unknown = operator(self.log, TraceSpec("absent"))
                self.assertIs(unknown.status, ComputeStatus.UNAVAILABLE)
                self.assertIsNone(unknown.value)
                self.assertEqual(unknown.issues[0].code, "unknown_object_type")
                self.assertIsNotNone(unknown.computation_id)
                declared = operator(self.log, TraceSpec("unused"))
                self.assertIs(declared.status, ComputeStatus.COMPUTED)
                self.assertIsNotNone(declared.value)
        empty = OCEL(object_types=(ObjectType("order"),))
        self.assertEqual(reconstruct_traces(empty, self.spec).value.traces, ())
        self.assertEqual(discover_dfg(empty, self.spec).value.edges, ())

    def test_missing_endpoint_is_invalid_without_partial_success_or_identity(self) -> None:
        broken = replace(self.log, e2o=self.log.e2o + (E2O("missing", "ghost", ""),))
        for operator in (reconstruct_traces, discover_dfg):
            result = operator(broken, self.spec)
            self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
            self.assertIsNone(result.value)
            self.assertIsNone(result.source_digest)
            self.assertIsNone(result.computation_id)
            self.assertEqual({i.code for i in result.issues}, {
                "dangling_e2o_event", "dangling_e2o_object"
            })
        with self.assertRaises(InvalidOCELInput):
            ComputationContext.build(broken)

    def test_duplicate_relation_is_invalid_not_silently_deduplicated(self) -> None:
        broken = replace(self.log, e2o=self.log.e2o + (self.log.e2o[0],))
        result = discover_dfg(broken, self.spec)
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "duplicate_e2o")

    def test_tie_rejected_only_when_same_selected_object_contains_both_events(self) -> None:
        # Disconnected orphan shares e1's timestamp and does not make o1 ambiguous.
        self.assertIs(reconstruct_traces(self.log, self.spec).status, ComputeStatus.COMPUTED)
        tied = replace(self.log, events=tuple(
            replace(e, time=self.log.events[0].time) if e.id == "e2" else e
            for e in self.log.events
        ))
        for operator in (reconstruct_traces, discover_dfg):
            result = operator(tied, self.spec)
            self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
            self.assertIsNone(result.value)
            self.assertEqual(result.issues[0].at, ("object", "o1", "events", "e1", "e2"))
        filtered = reconstruct_traces(tied, TraceSpec("order", ("audit",)))
        self.assertIs(filtered.status, ComputeStatus.COMPUTED)
        explicit = reconstruct_traces(tied, TraceSpec("order", tie_policy="event_id"))
        self.assertEqual(trace_ids(explicit)["o1"], ("e1", "e2"))

    def test_offset_equivalent_times_are_ties_and_microseconds_stay_distinct(self) -> None:
        utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
        tied = OCEL(
            event_types=(EventType("A"),), object_types=(ObjectType("order"),),
            objects=(Object("o", "order"),),
            events=(Event("a", "A", utc), Event("b", "A", utc.astimezone(
                timezone(timedelta(hours=9))
            ))),
            e2o=(E2O("a", "o", ""), E2O("b", "o", "")),
        )
        self.assertIs(reconstruct_traces(tied, self.spec).status, ComputeStatus.UNAVAILABLE)
        distant = datetime(9999, 12, 31, 23, 59, 59, 999998, tzinfo=timezone.utc)
        precise = replace(tied, events=(
            Event("z-first", "A", distant),
            Event("a-later", "A", distant + timedelta(microseconds=1)),
        ), e2o=(E2O("z-first", "o", ""), E2O("a-later", "o", "")))
        result = reconstruct_traces(precise, self.spec)
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(trace_ids(result)["o"], ("z-first", "a-later"))

    def test_unrepresentable_utc_time_is_invalid(self) -> None:
        bad_time = datetime.max.replace(tzinfo=timezone(-timedelta(hours=1)))
        broken = replace(self.log, events=tuple(
            replace(e, time=bad_time) if e.id == "e1" else e for e in self.log.events
        ))
        result = reconstruct_traces(broken, self.spec)
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "unrepresentable_canonical_input")

    def test_permutations_preserve_payload_and_computation_identity(self) -> None:
        permuted = replace(
            self.log,
            event_types=self.log.event_types[::-1],
            object_types=self.log.object_types[::-1],
            events=self.log.events[::-1], objects=self.log.objects[::-1],
            e2o=self.log.e2o[::-1], o2o=self.log.o2o[::-1],
        )
        for operator in (reconstruct_traces, discover_dfg):
            self.assertEqual(operator(self.log, self.spec), operator(permuted, self.spec))

    def test_identity_includes_operator_version_source_and_typed_policy(self) -> None:
        original = reconstruct_traces(self.log, self.spec)
        explicit_tie = reconstruct_traces(self.log, TraceSpec("order", tie_policy="event_id"))
        graph = discover_dfg(self.log, self.spec)
        self.assertNotEqual(original.computation_id, explicit_tie.computation_id)
        self.assertNotEqual(original.computation_id, graph.computation_id)
        with patch("pix_native_proposal.compute.OPERATOR_VERSION", "changed"):
            changed = reconstruct_traces(self.log, self.spec)
        self.assertNotEqual(original.computation_id, changed.computation_id)
        equivalent1 = TraceSpec("order", ("input", "audit", "input"))
        equivalent2 = TraceSpec("order", ("audit", "input"))
        self.assertEqual(
            reconstruct_traces(self.log, equivalent1),
            reconstruct_traces(self.log, equivalent2),
        )

    def test_context_is_immutable_and_reused_without_revalidation(self) -> None:
        context = ComputationContext.build(self.log)
        with self.assertRaises(FrozenInstanceError):
            context.source_digest = "changed"
        with self.assertRaises(TypeError):
            context.events_by_id["e1"] = self.log.events[0]
        with self.assertRaises(TypeError):
            context.e2o_by_object["o1"] = ()
        with patch("pix_native_proposal.compute.validate", side_effect=AssertionError), \
             patch("pix_native_proposal.compute.build", side_effect=AssertionError), \
             patch("pix_native_proposal.compute.canonical_digest", side_effect=AssertionError):
            self.assertIs(reconstruct_traces(context, self.spec).status, ComputeStatus.COMPUTED)
            self.assertIs(discover_dfg(context, self.spec).status, ComputeStatus.COMPUTED)

    def test_invalid_parameter_shapes_are_explicit_programming_errors(self) -> None:
        with self.assertRaises(TypeError):
            TraceSpec("order", ["input"])
        with self.assertRaises(ValueError):
            TraceSpec("order", tie_policy="random")
        with self.assertRaises(TypeError):
            TraceSpec("order", tie_policy=1)
        with self.assertRaises(ValueError):
            TraceSpec(" ")
        with self.assertRaises(TypeError):
            discover_dfg(self.log, {"object_type": "order"})
        self.assertIs(discover_dfg(None, self.spec).status, ComputeStatus.INVALID_INPUT)

    def test_invalid_unicode_parameters_fail_at_spec_construction(self) -> None:
        for name, qualifiers in (("\ud800", None), ("order", ("\ud800",))):
            with self.subTest(name=repr(name), qualifiers=repr(qualifiers)):
                with self.assertRaisesRegex(ValueError, "valid UTF-8 text"):
                    TraceSpec(name, qualifiers)


if __name__ == "__main__":
    unittest.main()
