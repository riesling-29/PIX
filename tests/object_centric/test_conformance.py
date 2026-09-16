"""Independent token arithmetic fixtures for native OC replay profiles."""

import unittest
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.conformance import (
    ObjectReplaySpec,
    replay_flattened_object_log,
    replay_object_log,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def marking(*tokens):
    return ObjectMarking(tuple(ObjectToken(*token) for token in tokens))


def source(objects, *events):
    """An event is (id, activity, seconds, ((object id, qualifier), ...))."""
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        object_types=tuple(
            ObjectType(kind) for kind in sorted({kind for _, kind in objects})
        ),
        event_types=tuple(
            EventType(kind) for kind in sorted({row[1] for row in events})
        ),
        objects=tuple(Object(*row) for row in objects),
        events=tuple(
            Event(eid, activity, origin + timedelta(seconds=seconds))
            for eid, activity, seconds, _ in events
        ),
        e2o=tuple(
            E2O(eid, obj, qualifier)
            for eid, _, _, participants in events
            for obj, qualifier in participants
        ),
    )


def batch(*, fixed=False, missing=False, residual=False):
    objects = (("a", "T"), ("b", "T"))
    return ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T")),
        (Transition("batch", "A"),),
        (
            ObjectArc("p", "batch", not fixed, 1, 1 if fixed else 2),
            ObjectArc("batch", "q", not fixed, 1, 1 if fixed else 2),
        ),
        marking(
            ("p", "a"),
            *((() if missing else (("p", "b"),)) + ((("p", "a"),) if residual else ())),
        ),
        marking(("q", "a"), ("q", "b")),
        objects,
    )


def assert_token_witness(test, value):
    """Independent arithmetic; no PIX firing/search helper is used."""
    present = Counter()
    missing = consumed = produced = 0
    seen = set()
    for step in value.steps:
        test.assertEqual(present, Counter(step.marking_before))
        present.update(step.inserted_tokens)
        required = Counter(step.consumed_tokens)
        test.assertTrue(all(present[token] >= n for token, n in required.items()))
        present.subtract(required)
        present.update(step.produced_tokens)
        present = +present
        test.assertEqual(present, Counter(step.marking_after))
        missing += len(step.inserted_tokens)
        consumed += len(step.consumed_tokens)
        produced += len(step.produced_tokens)
        if step.event_id is not None:
            test.assertNotIn(step.event_id, seen)
            seen.add(step.event_id)
    test.assertEqual(
        (missing, len(list(present.elements())), consumed, produced),
        (
            value.counts.missing,
            value.counts.remaining,
            value.counts.consumed,
            value.counts.produced,
        ),
    )
    test.assertEqual(produced + missing, consumed + value.counts.remaining)
    test.assertEqual(len(seen), value.processed_event_count)


class TestObjectTokenReplay(unittest.TestCase):
    def test_shared_event_consumed_once_with_two_objects(self):
        net = batch()
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        result = replay_object_log(log, net, ObjectReplaySpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.processed_event_count, 1)
        self.assertEqual(result.value.counts.consumed, 4)
        self.assertEqual(result.value.counts.produced, 4)
        self.assertEqual(result.value.token_fitness, 1)
        self.assertTrue(result.value.fitting)
        visible = next(s for s in result.value.steps if s.kind == "visible")
        self.assertEqual(visible.binding.objects, (("T", ("a", "b")),))
        assert_token_witness(self, result.value)

    def test_missing_token_repair_and_surplus_have_exact_accounting(self):
        net = batch(missing=True, residual=True)
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(
            (
                value.counts.missing,
                value.counts.remaining,
                value.counts.consumed,
                value.counts.produced,
            ),
            (1, 1, 4, 4),
        )
        self.assertEqual(value.token_fitness, 0.75)
        self.assertFalse(value.fitting)
        self.assertFalse(value.final_reached)
        self.assertEqual(value.ending_marking, (ObjectToken("p", "a"),))
        assert_token_witness(self, value)

    def test_two_object_types_synchronize_in_single_binding(self):
        net = ObjectCentricPetriNet(
            tuple(
                TypedPlace(place, kind)
                for place, kind in (
                    ("p", "Order"),
                    ("q", "Order"),
                    ("r", "Item"),
                    ("s", "Item"),
                )
            ),
            (Transition("t", "ship"),),
            tuple(
                ObjectArc(a, b)
                for a, b in (("p", "t"), ("r", "t"), ("t", "q"), ("t", "s"))
            ),
            marking(("p", "o"), ("r", "i")),
            marking(("q", "o"), ("s", "i")),
            (("o", "Order"), ("i", "Item")),
        )
        log = source(net.objects, ("e", "ship", 0, (("o", ""), ("i", ""))))
        value = replay_object_log(log, net, ObjectReplaySpec(("Order", "Item"))).value
        self.assertEqual(value.counts.missing, 0)
        self.assertTrue(value.fitting)
        assert_token_witness(self, value)

    def test_independent_events_use_lexical_ready_order_not_global_time(self):
        net = batch(fixed=True)
        log = source(
            net.objects, ("z", "A", 0, (("a", ""),)), ("a", "A", 10, (("b", ""),))
        )
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(value.event_order, ("a", "z"))
        self.assertTrue(value.fitting)
        self.assertEqual(value.scope.precedence, ())
        assert_token_witness(self, value)

    def test_shared_object_precedence_overrides_lexical_order(self):
        net = batch(fixed=True)
        log = source(
            net.objects, ("z", "A", 0, (("a", ""),)), ("a", "A", 10, (("a", ""),))
        )
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(value.event_order, ("z", "a"))
        self.assertEqual(value.counts.missing, 2)  # repeated a plus final b
        assert_token_witness(self, value)

    def test_fixed_arc_cannot_silently_drop_shared_participants(self):
        net = batch(fixed=True)
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(value.log_deviation_count, 1)
        self.assertFalse(value.fitting)
        self.assertEqual(
            value.steps[1].deviation_reason, "inadmissible_event_participation"
        )
        assert_token_witness(self, value)

    def test_qualifier_rows_do_not_duplicate_tokens(self):
        net = batch()
        log = source(net.objects, ("e", "A", 0, (("a", "x"), ("a", "y"), ("b", "x"))))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(len(value.scope.events[0].relations), 3)
        self.assertEqual(value.counts.consumed, 4)
        assert_token_witness(self, value)

    def test_unknown_activity_is_separate_from_token_fitness(self):
        net = batch()
        net = replace(net, final_marking=net.initial_marking)
        log = source(net.objects, ("e", "unknown", 0, (("a", ""),)))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(value.token_fitness, 1)
        self.assertEqual(value.log_deviation_count, 1)
        self.assertFalse(value.fitting)
        self.assertEqual(value.steps[1].deviation_reason, "unknown_activity")

    def test_silent_path_to_enable_and_finalize(self):
        net = ObjectCentricPetriNet(
            tuple(TypedPlace(place, "T") for place in ("p", "q", "r", "s")),
            (Transition("s1"), Transition("s2"), Transition("v", "A")),
            tuple(
                ObjectArc(a, b)
                for a, b in (
                    ("p", "s1"),
                    ("s1", "q"),
                    ("q", "v"),
                    ("v", "r"),
                    ("r", "s2"),
                    ("s2", "s"),
                )
            ),
            marking(("p", "a")),
            marking(("s", "a")),
            (("a", "T"),),
        )
        log = source(net.objects, ("e", "A", 0, (("a", ""),)))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertTrue(value.fitting)
        self.assertEqual(
            [s.binding.transition_id for s in value.steps if s.binding],
            ["s1", "v", "s2"],
        )
        self.assertEqual(value.counts.consumed, 4)
        assert_token_witness(self, value)

    def test_silent_self_loop_deduplicates_markings(self):
        net = batch()
        net = replace(
            net,
            transitions=net.transitions + (Transition("loop"),),
            arcs=net.arcs + (ObjectArc("p", "loop"), ObjectArc("loop", "p")),
        )
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        value = replay_object_log(
            log, net, ObjectReplaySpec(("T",), silent_max_states=1)
        ).value
        self.assertTrue(value.fitting)
        assert_token_witness(self, value)

    def test_unbounded_silent_source_stops_unknown_without_repairs(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"), TypedPlace("q", "T")),
            (Transition("source"), Transition("v", "A")),
            (ObjectArc("source", "p"), ObjectArc("q", "v")),
            marking(),
            marking(),
            (("a", "T"),),
        )
        log = source(net.objects, ("e", "A", 0, (("a", ""),)))
        result = replay_object_log(
            log, net, ObjectReplaySpec(("T",), silent_max_states=3)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.limit_reason, "silent_state_limit")
        self.assertIsNone(result.value.token_fitness)
        self.assertIsNone(result.value.fitting)
        self.assertEqual(result.value.processed_event_count, 0)
        self.assertEqual(result.value.counts.missing, 0)
        assert_token_witness(self, result.value)

    def test_silent_binding_limit_is_distinct_from_state_limit(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"), TypedPlace("q", "T")),
            (Transition("source"), Transition("v", "A")),
            (ObjectArc("source", "p", True, 1, 2), ObjectArc("q", "v")),
            marking(),
            marking(),
            (("a", "T"), ("b", "T")),
        )
        log = source(net.objects, ("e", "A", 0, (("a", ""),)))
        result = replay_object_log(
            log, net, ObjectReplaySpec(("T",), silent_max_states=2, max_bindings=1)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.limit_reason, "silent_binding_limit")
        assert_token_witness(self, result.value)

    def test_duplicate_activity_selects_minimum_missing_candidate(self):
        net = ObjectCentricPetriNet(
            tuple(TypedPlace(place, "T") for place in ("p", "q", "r", "s")),
            (Transition("a", "A"), Transition("b", "A")),
            tuple(
                ObjectArc(a, b)
                for a, b in (("p", "a"), ("r", "a"), ("a", "s"), ("q", "b"), ("b", "s"))
            ),
            marking(),
            marking(("s", "o")),
            (("o", "T"),),
        )
        log = source(net.objects, ("e", "A", 0, (("o", ""),)))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(
            next(s.binding.transition_id for s in value.steps if s.binding), "b"
        )
        self.assertEqual(value.counts.missing, 1)
        assert_token_witness(self, value)

    def test_empty_optional_type_binding_is_retained(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"),),
            (Transition("v", "A"),),
            (ObjectArc("p", "v", True, 0, 1),),
            marking(),
            marking(),
            (("a", "T"),),
        )
        log = source(net.objects, ("e", "A", 0, ()))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertTrue(value.fitting)
        self.assertIsNone(value.token_fitness)
        self.assertEqual(value.steps[1].binding.objects, (("T", ()),))
        assert_token_witness(self, value)

    def test_timestamp_ties_reject_unless_explicit(self):
        net = batch(fixed=True)
        log = source(
            net.objects, ("b", "A", 0, (("a", ""),)), ("a", "A", 0, (("a", ""),))
        )
        self.assertEqual(
            replay_object_log(log, net, ObjectReplaySpec(("T",))).status,
            ComputeStatus.UNAVAILABLE,
        )
        result = replay_object_log(
            log, net, ObjectReplaySpec(("T",), tie_policy="event_id")
        )
        self.assertEqual(result.value.event_order, ("a", "b"))
        self.assertIn("timestamp_tie_broken", [issue.code for issue in result.issues])

    def test_model_universe_mismatch_invalid(self):
        net = batch()
        log = source((("a", "T"),))
        result = replay_object_log(log, net, ObjectReplaySpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(result.value)

    def test_identity_changes_for_model_or_search_policy(self):
        net = batch()
        log = source(net.objects)
        first = replay_object_log(log, net, ObjectReplaySpec(("T",)))
        second = replay_object_log(
            log, net, ObjectReplaySpec(("T",), silent_max_states=2)
        )
        third = replay_object_log(
            log,
            replace(net, final_marking=net.initial_marking),
            ObjectReplaySpec(("T",)),
        )
        self.assertEqual(
            len({first.computation_id, second.computation_id, third.computation_id}), 3
        )
        with self.assertRaises(FrozenInstanceError):
            first.value.fitting = True

    def test_spec_rejects_invalid_limits_and_types(self):
        for kwargs in (
            {"silent_max_states": 0},
            {"max_bindings": 0},
            {"silent_max_states": True},
        ):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises((ValueError, TypeError)),
            ):
                ObjectReplaySpec(("T",), **kwargs)

    def test_witness_and_summary_reject_inconsistent_reconstruction(self):
        net = batch()
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        value = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        for change in (
            {"token_fitness": 0.5},
            {"processed_event_count": 2},
            {"final_reached": False},
            {"fitting": False},
            {"event_order": ("wrong",)},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(value, **change)
        visible = value.steps[1]
        with self.assertRaises(ValueError):
            replace(visible, consumed_tokens=visible.consumed_tokens * 2)
        with self.assertRaises(ValueError):
            replace(visible, marking_after=())

    def test_final_search_limit_preserves_completed_event_prefix_but_no_fitness(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"), TypedPlace("q", "T"), TypedPlace("r", "T")),
            (Transition("v", "A"), Transition("source")),
            (ObjectArc("p", "v"), ObjectArc("v", "q"), ObjectArc("source", "q")),
            marking(("p", "a")),
            marking(("r", "a")),
            (("a", "T"),),
        )
        log = source(net.objects, ("e", "A", 0, (("a", ""),)))
        result = replay_object_log(
            log, net, ObjectReplaySpec(("T",), silent_max_states=2)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.processed_event_count, 1)
        self.assertIsNone(result.value.token_fitness)
        self.assertIsNone(result.value.final_reached)
        self.assertEqual(result.value.steps[-1].kind, "visible")
        assert_token_witness(self, result.value)

    def test_log_input_is_never_mutated(self):
        net = batch()
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        before = repr(log), repr(net)
        replay_object_log(log, net, ObjectReplaySpec(("T",)))
        replay_flattened_object_log(log, net, ObjectReplaySpec(("T",)))
        self.assertEqual((repr(log), repr(net)), before)

    def test_registered_results_roundtrip_with_concrete_token_witness(self):
        from pix.results import result_from_json, result_json_bytes

        net = batch(missing=True, residual=True)
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        for function in (replay_object_log, replay_flattened_object_log):
            with self.subTest(profile=function.__name__):
                result = function(log, net, ObjectReplaySpec(("T",)))
                self.assertEqual(result_from_json(result_json_bytes(result)), result)


class TestFlattenedObjectReplay(unittest.TestCase):
    def test_projection_loses_shared_cardinality_and_counts_event_twice(self):
        net = batch(fixed=True)
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        joint = replay_object_log(log, net, ObjectReplaySpec(("T",))).value
        flat = replay_flattened_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertFalse(joint.fitting)
        self.assertEqual(flat.token_fitness, 1)
        self.assertEqual(flat.source_event_count, 1)
        self.assertEqual(flat.projected_event_occurrence_count, 2)
        self.assertEqual(flat.completed_count, 2)
        self.assertEqual(flat.completed_counts.consumed, 4)

    def test_token_weighting_uses_summed_counts_not_mean_of_fitness(self):
        net = batch(fixed=True)
        log = source(
            net.objects,
            ("e1", "A", 0, (("a", ""),)),
            ("e2", "A", 1, (("a", ""),)),
            ("e3", "A", 2, (("a", ""),)),
            ("e4", "A", 3, (("b", ""),)),
        )
        value = replay_flattened_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertAlmostEqual(value.token_fitness, 2 / 3)
        self.assertNotEqual(
            value.token_fitness, sum(row.token_fitness for row in value.objects) / 2
        )
        self.assertEqual(
            (
                value.completed_counts.missing,
                value.completed_counts.remaining,
                value.completed_counts.consumed,
                value.completed_counts.produced,
            ),
            (2, 2, 6, 6),
        )

    def test_isolated_objects_and_unrepresented_events_explicit(self):
        net = batch(fixed=True)
        log = source(net.objects, ("orphan", "X", 0, ()), ("e", "A", 1, (("a", ""),)))
        value = replay_flattened_object_log(log, net, ObjectReplaySpec(("T",))).value
        self.assertEqual(value.completed_count, 2)
        self.assertEqual(value.unrepresented_event_ids, ("orphan",))
        isolated = next(row for row in value.objects if row.object_id == "b")
        self.assertEqual(isolated.replay.event_count, 0)
        self.assertEqual(isolated.replay.counts.missing, 1)

    def test_flattened_summary_cannot_claim_wrong_coverage(self):
        net = batch(fixed=True)
        log = source(net.objects, ("e", "A", 0, (("a", ""), ("b", ""))))
        value = replay_flattened_object_log(log, net, ObjectReplaySpec(("T",))).value
        for change in (
            {"completed_count": 0},
            {"token_fitness": 0.5},
            {"projected_event_occurrence_count": 1},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(value, **change)


if __name__ == "__main__":
    unittest.main()
