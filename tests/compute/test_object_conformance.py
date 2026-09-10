"""Joint OCPN scope, participation, partial order and resource-limit contracts."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding
from pix.compute.object_conformance import (
    align_object_log,
    build_object_event_scope,
    validate_object_model_scope,
)
from pix.contracts.models import (
    Binding,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.object_conformance import ObjectAlignmentSpec
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def marking(*pairs):
    return ObjectMarking(tuple(ObjectToken(*pair) for pair in pairs))


def log(objects, events=(), *, declared_types=()):
    """Events are (id, activity, second, ((object ID, qualifier), ...))."""
    return OCEL(
        object_types=tuple(
            ObjectType(kind)
            for kind in sorted({kind for _, kind in objects} | set(declared_types))
        ),
        event_types=tuple(
            EventType(activity) for activity in sorted({item[1] for item in events})
        ),
        objects=tuple(Object(*item) for item in objects),
        events=tuple(
            Event(identifier, activity, ORIGIN + timedelta(seconds=second))
            for identifier, activity, second, _ in events
        ),
        e2o=tuple(
            E2O(identifier, obj, qualifier)
            for identifier, _, _, participation in events
            for obj, qualifier in participation
        ),
    )


def batch_net(
    *,
    objects=(("a", "T"), ("b", "T")),
    minimum=1,
    maximum=2,
    variable=True,
    self_loop=False,
):
    return ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T")),
        (Transition("batch", "A"),),
        (
            ObjectArc("p", "batch", variable, minimum, maximum),
            ObjectArc("batch", "p" if self_loop else "q", variable, minimum, maximum),
        ),
        marking(*(("p", identifier) for identifier, _ in objects)),
        marking(
            *(("p" if self_loop else "q", identifier) for identifier, _ in objects)
        ),
        objects,
    )


def assert_path(test, net, result):
    outcome = result.value
    current = net.initial_marking
    consumed = set()
    events = {event.event_id: event for event in outcome.scope.events}
    predecessors = {identifier: set() for identifier in events}
    for edge in outcome.scope.precedence:
        predecessors[edge.successor_event_id].add(edge.predecessor_event_id)
    for move in outcome.moves:
        test.assertEqual(
            move.before_marking,
            tuple((t.place_id, t.object_id) for t in current.tokens),
        )
        if move.event_id is not None:
            test.assertNotIn(move.event_id, consumed)
            test.assertLessEqual(predecessors[move.event_id], consumed)
            consumed.add(move.event_id)
        if move.transition_id is not None:
            current = fire_binding(
                net, current, Binding(move.transition_id, move.objects)
            )
        test.assertEqual(
            move.after_marking, tuple((t.place_id, t.object_id) for t in current.tokens)
        )
        if move.kind == "synchronous":
            test.assertEqual(
                tuple((kind, ids) for kind, ids in move.objects if ids),
                events[move.event_id].objects,
            )
    test.assertEqual(current, net.final_marking)
    test.assertEqual(consumed, set(events))
    test.assertEqual(sum(move.cost for move in outcome.moves), outcome.cost)


class TestJointObjectAlignment(unittest.TestCase):
    def test_shared_multi_object_event_fires_exactly_once(self):
        net = batch_net()
        source = log(net.objects, (("e", "A", 0, (("a", ""), ("b", ""))),))
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.status, "optimal")
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.move_counts.synchronous, 1)
        self.assertEqual(result.value.moves[0].objects, (("T", ("a", "b")),))
        self.assertEqual(result.value.coverage.input_events, 1)
        self.assertEqual(result.value.coverage.selected_objects, 2)
        assert_path(self, net, result)

    def test_fixed_arc_cannot_sync_a_subset_of_shared_event_participants(self):
        net = batch_net(minimum=1, maximum=1, variable=False)
        source = log(net.objects, (("e", "A", 0, (("a", ""), ("b", ""))),))
        for mode, expected in (("event", 3), ("object", 4)):
            with self.subTest(mode=mode):
                result = align_object_log(
                    source, net, ObjectAlignmentSpec(("T",), cost_mode=mode)
                )
                self.assertEqual(result.value.cost, expected)
                self.assertEqual(result.value.move_counts.synchronous, 0)
                self.assertEqual(result.value.move_counts.log, 1)
                self.assertEqual(result.value.move_counts.model, 2)
                assert_path(self, net, result)

    def test_duplicate_qualifiers_preserve_evidence_without_duplicate_consumption(self):
        net = batch_net()
        source = log(
            net.objects, (("e", "A", 0, (("a", "x"), ("a", "y"), ("b", "x"))),)
        )
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.cost, 0)
        event = result.value.scope.events[0]
        self.assertEqual(event.objects, (("T", ("a", "b")),))
        self.assertEqual(len(event.relations), 3)
        self.assertEqual(result.value.move_counts.synchronous, 1)

    def test_qualifier_filter_changes_participation_but_keeps_all_model_objects(self):
        net = batch_net()
        source = log(net.objects, (("e", "A", 0, (("a", "selected"), ("b", "other"))),))
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), qualifiers=("selected",))
        )
        self.assertEqual(result.value.scope.events[0].objects, (("T", ("a",)),))
        self.assertEqual(result.value.scope.selected_objects, net.objects)
        self.assertEqual(result.value.scope.excluded_relation_count, 1)
        self.assertEqual(result.value.cost, 1)
        assert_path(self, net, result)

    def test_no_selected_participants_event_remains_in_whole_log(self):
        net = batch_net(self_loop=True)
        source = log(net.objects, (("e", "A", 0, (("a", "q"),)),))
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), qualifiers=())
        )
        self.assertEqual(result.value.coverage.input_events, 1)
        self.assertEqual(result.value.scope.events[0].objects, ())
        self.assertEqual(result.value.cost, 1)
        self.assertEqual(result.value.move_counts.log, 1)

    def test_explicit_zero_binding_syncs_without_consuming_objects(self):
        net = batch_net(minimum=0, maximum=0, self_loop=True)
        source = log(net.objects, (("zero", "A", 0, ()),))
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.moves[0].objects, (("T", ()),))
        self.assertEqual(
            result.value.moves[0].before_marking, result.value.moves[0].after_marking
        )
        self.assertEqual(result.value.move_counts.synchronous, 1)

    def test_zero_object_weight_does_not_hide_log_deviation(self):
        net = batch_net(self_loop=True)
        source = log(net.objects, (("zero", "UNKNOWN", 0, ()),))
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), cost_mode="object")
        )
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.move_counts.log, 1)
        self.assertEqual(result.value.moves[0].weight, 0)
        self.assertEqual(result.value.cost_unit, "object_weighted_integer_cost")

    def test_objectless_log_with_no_object_types_has_explicit_empty_binding(self):
        net = ObjectCentricPetriNet(
            (), (Transition("t", "A"),), (), ObjectMarking(), ObjectMarking(), ()
        )
        source = log((), (("e", "A", 0, ()),))
        result = align_object_log(source, net, ObjectAlignmentSpec(()))
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.moves[0].objects, ())
        self.assertEqual(result.value.move_counts.synchronous, 1)

    def test_silent_completion_obeys_entire_final_marking(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"), TypedPlace("q", "T"), TypedPlace("r", "T")),
            (Transition("a", "A"), Transition("tau")),
            (
                ObjectArc("p", "a"),
                ObjectArc("a", "q"),
                ObjectArc("q", "tau"),
                ObjectArc("tau", "r"),
            ),
            marking(("p", "x")),
            marking(("r", "x")),
            (("x", "T"),),
        )
        source = log(net.objects, (("e", "A", 0, (("x", ""),)),))
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), silent_move_cost=3)
        )
        self.assertEqual(result.value.cost, 3)
        self.assertEqual(
            [move.kind for move in result.value.moves], ["synchronous", "silent"]
        )
        assert_path(self, net, result)

    def test_equal_timestamps_on_same_object_are_unavailable_by_default(self):
        net = batch_net(objects=(("a", "T"),), self_loop=True)
        source = log(
            net.objects, (("b", "A", 0, (("a", ""),)), ("a", "A", 0, (("a", ""),)))
        )
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].code, "ambiguous_event_order")

    def test_explicit_tie_policy_only_orders_events_sharing_selected_object(self):
        net = batch_net(self_loop=True)
        source = log(
            net.objects,
            (
                ("b", "A", 0, (("a", ""),)),
                ("a", "A", 0, (("a", ""),)),
                ("c", "A", 0, (("b", ""),)),
            ),
        )
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), tie_policy="event_id")
        )
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(
            [issue.code for issue in result.issues], ["timestamp_tie_broken"]
        )
        self.assertEqual(result.issues[0].at, ("object", "a", "events", "a", "b"))
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(
            [
                (edge.predecessor_event_id, edge.successor_event_id)
                for edge in result.value.scope.precedence
            ],
            [("a", "b")],
        )
        assert_path(self, net, result)

    def test_independent_timestamp_ties_do_not_require_linearization(self):
        net = batch_net(self_loop=True)
        source = log(
            net.objects, (("a", "A", 0, (("a", ""),)), ("b", "A", 0, (("b", ""),)))
        )
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.scope.precedence, ())
        self.assertEqual(result.value.cost, 0)
        self.assertFalse(result.issues)

    def test_explicit_tie_policy_without_actual_shared_tie_has_no_diagnostic(self):
        net = batch_net(self_loop=True)
        source = log(
            net.objects, (("a", "A", 0, (("a", ""),)), ("b", "A", 1, (("a", ""),)))
        )
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), tie_policy="event_id")
        )
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertFalse(result.issues)
        self.assertEqual(result.value.cost, 0)

    def test_scope_helper_retains_actual_tie_diagnostics_with_valid_scope(self):
        source = log(
            (("a", "T"),), (("a", "A", 0, (("a", ""),)), ("b", "A", 0, (("a", ""),)))
        )
        scope, issues = build_object_event_scope(
            ComputationContext(source), object_types=("T",), tie_policy="event_id"
        )
        self.assertIsNotNone(scope)
        self.assertEqual([issue.code for issue in issues], ["timestamp_tie_broken"])
        self.assertEqual(
            [
                (edge.predecessor_event_id, edge.successor_event_id)
                for edge in scope.precedence
            ],
            [("a", "b")],
        )

    def test_tie_diagnostic_survives_incomplete_alignment_search(self):
        net = batch_net(self_loop=True)
        source = log(
            net.objects, (("a", "A", 0, (("a", ""),)), ("b", "A", 0, (("a", ""),)))
        )
        result = align_object_log(
            source,
            net,
            ObjectAlignmentSpec(("T",), tie_policy="event_id", max_bindings=1),
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.status, "binding_limit")
        self.assertEqual(
            [issue.code for issue in result.issues],
            ["timestamp_tie_broken", "object_alignment_binding_limit"],
        )

    def test_order_constraints_do_not_use_excluded_relation_types(self):
        net = batch_net(self_loop=True)
        source = log(
            net.objects + (("r", "Resource"),),
            (
                ("e1", "A", 0, (("a", ""), ("r", ""))),
                ("e2", "A", 1, (("b", ""), ("r", ""))),
            ),
        )
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.scope.precedence, ())
        self.assertEqual(result.value.scope.excluded_object_count, 1)
        self.assertEqual(result.value.scope.excluded_relation_count, 2)
        self.assertEqual(result.value.cost, 0)

    def test_initial_accepting_empty_log_needs_only_one_state(self):
        net = batch_net(self_loop=True)
        result = align_object_log(
            log(net.objects), net, ObjectAlignmentSpec(("T",), max_states=1)
        )
        self.assertEqual(result.value.status, "optimal")
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.settled_states, 1)
        self.assertEqual(result.value.moves, ())

    def test_empty_event_log_still_requires_model_completion_for_isolated_objects(self):
        net = batch_net()
        result = align_object_log(log(net.objects), net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.cost, 1)
        self.assertEqual(result.value.move_counts.model, 1)
        self.assertEqual(result.value.moves[0].objects, (("T", ("a", "b")),))

    def test_extra_residual_object_token_prevents_acceptance(self):
        net = batch_net(objects=(("a", "T"),), self_loop=True)
        net = replace(net, final_marking=marking(("p", "a"), ("p", "a")))
        result = align_object_log(log(net.objects), net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.status, "unreachable")
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertIsNone(result.value.cost)
        self.assertEqual(result.value.coverage.completed_scopes, 1)

    def test_repeated_object_tokens_are_preserved_during_firing(self):
        net = batch_net(objects=(("a", "T"),))
        net = replace(
            net,
            initial_marking=marking(("p", "a"), ("p", "a")),
            final_marking=marking(("q", "a"), ("p", "a")),
        )
        source = log(net.objects, (("e", "A", 0, (("a", ""),)),))
        result = align_object_log(source, net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.value.cost, 0)
        self.assertEqual(result.value.moves[0].after_marking, (("p", "a"), ("q", "a")))
        assert_path(self, net, result)

    def test_state_limit_keeps_lower_bound_and_does_not_claim_fitness(self):
        net = batch_net()
        result = align_object_log(
            log(net.objects), net, ObjectAlignmentSpec(("T",), max_states=1)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.status, "search_limit")
        self.assertIsNone(result.value.cost)
        self.assertIsNone(result.value.move_counts)
        self.assertEqual(result.value.lower_bound_cost, 1)
        self.assertEqual(result.value.coverage.limited_scopes, 1)
        self.assertEqual(result.value.coverage.completed_scopes, 0)

    def test_binding_limit_prevents_optimality_even_if_sync_binding_is_in_prefix(self):
        net = batch_net()
        source = log(net.objects, (("e", "A", 0, (("a", ""),)),))
        result = align_object_log(
            source, net, ObjectAlignmentSpec(("T",), max_bindings=1)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.status, "binding_limit")
        self.assertEqual(result.value.max_enabled_binding_count, 3)
        self.assertEqual(result.value.lower_bound_cost, 0)
        self.assertIsNone(result.value.cost)
        self.assertEqual(result.value.moves, ())

    def test_15000_optional_objects_binding_limit_result_roundtrips_losslessly(self):
        from pix.results import result_from_json, result_json_bytes

        objects = tuple((f"o{i}", "T") for i in range(15000))
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"),),
            (Transition("source"),),
            (ObjectArc("source", "p", variable=True, min_objects=0),),
            ObjectMarking(),
            marking(("p", "o0")),
            objects,
        )
        result = align_object_log(
            log(objects), net, ObjectAlignmentSpec(("T",), max_bindings=1)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.status, "binding_limit")
        self.assertEqual(result.value.max_enabled_binding_count, 1 << 15000)
        blob = result_json_bytes(result)
        restored = result_from_json(blob)
        self.assertEqual(restored, result)
        self.assertEqual(result_json_bytes(restored), blob)

    def test_zero_cost_source_token_growth_is_bounded_not_declared_unreachable(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"), TypedPlace("never", "T")),
            (Transition("grow"),),
            (ObjectArc("grow", "p"),),
            ObjectMarking(),
            marking(("never", "a")),
            (("a", "T"),),
        )
        result = align_object_log(
            log(net.objects), net, ObjectAlignmentSpec(("T",), max_states=5)
        )
        self.assertEqual(result.value.status, "search_limit")
        self.assertEqual(result.value.settled_states, 5)
        self.assertEqual(result.value.discovered_states, 6)
        self.assertEqual(result.value.lower_bound_cost, 0)

    def test_model_universe_must_include_isolated_selected_log_objects(self):
        net = batch_net(objects=(("a", "T"),), self_loop=True)
        result = align_object_log(
            log(net.objects + (("isolate", "T"),)), net, ObjectAlignmentSpec(("T",))
        )
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "object_missing_from_model")
        self.assertIsNotNone(result.source_digest)

    def test_model_objects_cannot_be_silently_sliced_out_of_scope(self):
        net = batch_net(self_loop=True)
        result = align_object_log(log((("a", "T"),)), net, ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIn(
            "model_object_outside_scope", {issue.code for issue in result.issues}
        )

    def test_object_type_mismatch_is_an_input_problem_not_a_log_deviation(self):
        net = batch_net(objects=(("a", "T"),), self_loop=True)
        result = align_object_log(
            log((("a", "Other"),)), net, ObjectAlignmentSpec(("Other",))
        )
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIn("object_type_mismatch", {issue.code for issue in result.issues})
        self.assertIn(
            "model_type_outside_scope", {issue.code for issue in result.issues}
        )

    def test_invalid_ocel_preserves_semantic_diagnostic(self):
        source = OCEL(objects=(Object("undeclared", "T"),))
        result = align_object_log(source, batch_net(), ObjectAlignmentSpec(("T",)))
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(result.source_digest)
        self.assertTrue(result.issues)
        self.assertNotEqual(result.issues[0].code, "object_missing_from_model")

    def test_unknown_selection_is_explicitly_unavailable(self):
        net = batch_net(self_loop=True)
        result = align_object_log(
            log(net.objects), net, ObjectAlignmentSpec(("Unknown",))
        )
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(result.issues[0].code, "unknown_object_type")

    def test_model_type_with_no_objects_is_still_part_of_scope(self):
        net = ObjectCentricPetriNet(
            (TypedPlace("p", "T"),), (), (), ObjectMarking(), ObjectMarking(), ()
        )
        result = align_object_log(log(()), net, ObjectAlignmentSpec(()))
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "model_type_outside_scope")

    def test_context_reuse_and_permutations_preserve_identity(self):
        net = batch_net()
        source = log(net.objects, (("e", "A", 0, (("a", ""), ("b", ""))),))
        spec = ObjectAlignmentSpec(("T",))
        baseline = align_object_log(source, net, spec)
        self.assertEqual(
            align_object_log(ComputationContext(source), net, spec), baseline
        )
        permuted = replace(
            source,
            objects=tuple(reversed(source.objects)),
            e2o=tuple(reversed(source.e2o)),
        )
        self.assertEqual(align_object_log(permuted, net, spec), baseline)
        self.assertNotEqual(
            align_object_log(source, net, replace(spec, max_states=77)).computation_id,
            baseline.computation_id,
        )
        self.assertNotEqual(
            align_object_log(
                source, net, replace(spec, max_bindings=99)
            ).computation_id,
            baseline.computation_id,
        )
        self.assertNotEqual(
            align_object_log(
                source, net, replace(spec, cost_mode="object")
            ).computation_id,
            baseline.computation_id,
        )
        self.assertNotEqual(
            align_object_log(
                source, replace(net, final_marking=net.initial_marking), spec
            ).computation_id,
            baseline.computation_id,
        )
        self.assertEqual(baseline.spec.parameters.scope, "whole_log")
        self.assertEqual(baseline.spec.model_digest, baseline.value.model_digest)

    def test_result_and_scope_are_immutable(self):
        net = batch_net(self_loop=True)
        result = align_object_log(log(net.objects), net, ObjectAlignmentSpec(("T",)))
        with self.assertRaises(FrozenInstanceError):
            result.value.scope.scope = "changed"

    def test_spec_validation_rejects_implicit_scope_bad_costs_and_mutable_filters(self):
        for kwargs in (
            {"scope": "execution"},
            {"cost_mode": "unknown"},
            {"tie_policy": "time"},
            {"max_states": 0},
            {"max_bindings": 0},
            {"log_move_cost": -1},
            {"model_move_cost": -1},
            {"silent_move_cost": -1},
            {"synchronous_move_cost": -1},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ObjectAlignmentSpec(("T",), **kwargs)
        for kwargs in (
            {"qualifiers": []},
            {"max_states": True},
            {"max_bindings": 1.0},
            {"log_move_cost": False},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(TypeError):
                ObjectAlignmentSpec(("T",), **kwargs)
        with self.assertRaises(TypeError):
            ObjectAlignmentSpec(["T"])
        with self.assertRaises(ValueError):
            ObjectAlignmentSpec(("\ud800",))

    def test_public_scope_helpers_validate_and_report_their_contracts(self):
        net = batch_net(self_loop=True)
        context = ComputationContext(log(net.objects))
        scope, issues = build_object_event_scope(context, object_types=("T",))
        self.assertFalse(issues)
        self.assertFalse(validate_object_model_scope(net, scope, ("T",)))
        with self.assertRaises(TypeError):
            build_object_event_scope(context.log, object_types=("T",))
        with self.assertRaises(TypeError):
            validate_object_model_scope(None, scope, ("T",))
        with self.assertRaises(TypeError):
            validate_object_model_scope(net, None, ("T",))
        with self.assertRaises(TypeError):
            align_object_log(context, None, ObjectAlignmentSpec(("T",)))
        with self.assertRaises(TypeError):
            align_object_log(context, net, None)


if __name__ == "__main__":
    unittest.main()
