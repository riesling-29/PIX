"""OCEL OLAP semantics: typed snapshots, relation evidence, exact inverse facts."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.cube import (
    DrillDownSpec,
    UnfoldSpec,
    drill_down,
    fold,
    materialize_cube,
    roll_up,
    unfold,
)
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)
from pix.results import result_from_json, result_json_bytes

T = datetime(2026, 9, 15, tzinfo=timezone.utc)


def log_fixture():
    return OCEL(
        object_types=(
            ObjectType("order", (Attribute("region", ValueType.STRING),)),
            ObjectType("item"),
        ),
        event_types=(
            EventType("pack", (Attribute("cost", ValueType.INTEGER),)),
            EventType("ship"),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr("region", "east", T),
                    ObjectAttr("region", "west", T + timedelta(days=2)),
                ),
            ),
            Object("o2", "order", (ObjectAttr("region", "east", T),)),
            Object("o3", "order", (ObjectAttr("region", "west", T),)),
            Object("i", "item"),
        ),
        events=(
            Event("e1", "pack", T + timedelta(days=1), (EventAttr("cost", 7),)),
            Event("e2", "pack", T + timedelta(days=1), (EventAttr("cost", 9),)),
            Event("e3", "ship", T + timedelta(days=3)),
        ),
        e2o=(
            E2O("e1", "o1", "flow"),
            E2O("e1", "o2", "flow"),
            E2O("e1", "o1", "audit"),
            E2O("e1", "i", "contains"),
            E2O("e2", "i", "flow"),
            E2O("e3", "o1", "flow"),
        ),
        o2o=(O2O("o1", "o2", "related"), O2O("o1", "i", "contains")),
    )


def facts(log):
    return (
        tuple((e.id, e.time, e.attributes) for e in log.events),
        tuple((o.id, o.attributes) for o in log.objects),
        log.e2o,
        log.o2o,
    )


class ObjectCentricCubeTests(unittest.TestCase):
    def test_drill_down_groups_equal_asof_values_not_future_values(self):
        log = log_fixture()
        plan = drill_down(log, DrillDownSpec("order", "region", T + timedelta(days=1)))
        self.assertIs(plan.status, ComputeStatus.COMPUTED)
        changes = {c.entity_id: c for c in plan.value.changes}
        self.assertEqual(changes["o1"].after_type, changes["o2"].after_type)
        self.assertNotEqual(changes["o1"].after_type, changes["o3"].after_type)
        self.assertEqual(changes["o1"].attribute_value.text_value, "east")
        self.assertEqual(changes["o1"].assigned_at, T)
        self.assertEqual(len(plan.value.added_object_types), 2)
        self.assertNotEqual(plan.source_digest, plan.value.output_digest)
        transformed = materialize_cube(log, plan)
        self.assertEqual(facts(ComputationContext(log).log), facts(transformed))
        self.assertEqual(
            len(transformed.objects[1].attributes)
            + len(transformed.objects[0].attributes),
            len(ComputationContext(log).log.objects[1].attributes)
            + len(ComputationContext(log).log.objects[0].attributes),
        )

    def test_new_types_keep_complete_original_attribute_declarations(self):
        log = log_fixture()
        result = drill_down(log, DrillDownSpec("order", "region", T))
        self.assertTrue(
            all(
                t.attributes == log.object_types[0].attributes
                for t in result.value.added_object_types
            )
        )
        transformed = ComputationContext(materialize_cube(log, result))
        self.assertEqual(transformed.source_digest, result.value.output_digest)
        self.assertIn("order", transformed.objects_by_type)

    def test_inclusive_asof_boundary_and_later_snapshot_are_distinct(self):
        log = log_fixture()
        early = drill_down(log, DrillDownSpec("order", "region", T + timedelta(days=1)))
        later = drill_down(log, DrillDownSpec("order", "region", T + timedelta(days=2)))
        early_rows = {c.entity_id: c for c in early.value.changes}
        later_rows = {c.entity_id: c for c in later.value.changes}
        self.assertEqual(later_rows["o1"].attribute_value.text_value, "west")
        self.assertEqual(later_rows["o1"].after_type, later_rows["o3"].after_type)
        self.assertNotEqual(early_rows["o1"].after_type, later_rows["o1"].after_type)
        self.assertNotEqual(early.computation_id, later.computation_id)

    def test_missing_and_empty_values_keep_parent_with_unknown_evidence(self):
        log = log_fixture()
        log = replace(
            log,
            objects=log.objects
            + (
                Object("missing", "order"),
                Object("empty", "order", (ObjectAttr("region", "", T),)),
                Object(
                    "future",
                    "order",
                    (ObjectAttr("region", "north", T + timedelta(days=10)),),
                ),
            ),
        )
        plan = drill_down(log, DrillDownSpec("order", "region", T))
        self.assertIs(plan.status, ComputeStatus.PARTIAL)
        self.assertEqual(
            {r.object_id: r.reason for r in plan.value.unclassified},
            {
                "missing": "no_assignment_as_of",
                "empty": "empty_attribute_value",
                "future": "no_assignment_as_of",
            },
        )
        transformed = ComputationContext(materialize_cube(log, plan))
        self.assertTrue(
            all(
                transformed.objects_by_id[obj].type == "order"
                for obj in ("missing", "empty", "future")
            )
        )
        restored = materialize_cube(transformed, roll_up(transformed, plan))
        self.assertEqual(restored, ComputationContext(log).log)

    def test_strict_missing_policy_does_not_build_partial_transformation(self):
        log = log_fixture()
        result = drill_down(
            log,
            DrillDownSpec(
                "order", "region", T - timedelta(seconds=1), missing_policy="reject"
            ),
        )
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(len(result.issues), 3)

    def test_zero_and_false_are_defined_typed_values(self):
        for kind, val in ((ValueType.INTEGER, 0), (ValueType.BOOLEAN, False)):
            with self.subTest(kind=kind):
                log = OCEL(
                    object_types=(ObjectType("T", (Attribute("a", kind),)),),
                    objects=(Object("o", "T", (ObjectAttr("a", val, T),)),),
                )
                result = drill_down(log, DrillDownSpec("T", "a", T))
                self.assertIs(result.status, ComputeStatus.COMPUTED)
                self.assertEqual(len(result.value.changes), 1)
                self.assertEqual(
                    result.value.changes[0].attribute_value.native_value, val
                )

    def test_string_datetime_boolean_and_integer_values_have_distinct_type_keys(self):
        generated = set()
        for kind, val in (
            (ValueType.STRING, "1"),
            (ValueType.INTEGER, 1),
            (ValueType.BOOLEAN, True),
            (ValueType.TIME, T),
            (ValueType.STRING, T.isoformat()),
        ):
            with self.subTest(kind=kind, val=val):
                log = OCEL(
                    object_types=(ObjectType("T", (Attribute("a", kind),)),),
                    objects=(Object("o", "T", (ObjectAttr("a", val, T),)),),
                )
                result = drill_down(log, DrillDownSpec("T", "a", T))
                generated.add(result.value.changes[0].after_type)
        self.assertEqual(len(generated), 5)

    def test_signed_float_zero_groups_by_numeric_equality_without_history_loss(self):
        log = OCEL(
            object_types=(ObjectType("T", (Attribute("a", ValueType.FLOAT),)),),
            objects=(
                Object("positive", "T", (ObjectAttr("a", 0.0, T),)),
                Object("negative", "T", (ObjectAttr("a", -0.0, T),)),
            ),
        )
        result = drill_down(log, DrillDownSpec("T", "a", T))
        self.assertEqual(len(result.value.added_object_types), 1)
        self.assertEqual(len({c.after_type for c in result.value.changes}), 1)
        self.assertEqual(
            facts(materialize_cube(log, result)), facts(ComputationContext(log).log)
        )

    def test_composed_refinements_reverse_in_stack_order(self):
        log = log_fixture()
        drill = drill_down(log, DrillDownSpec("order", "region", T))
        refined_objects = materialize_cube(log, drill)
        selected_type = next(
            c.after_type for c in drill.value.changes if c.entity_id == "o1"
        )
        unroll = unfold(refined_objects, UnfoldSpec("pack", selected_type))
        refined_events = materialize_cube(refined_objects, unroll)
        restored_events = materialize_cube(refined_events, fold(refined_events, unroll))
        restored_all = materialize_cube(
            restored_events, roll_up(restored_events, drill)
        )
        self.assertEqual(restored_all, ComputationContext(log).log)

    def test_roll_up_exactly_restores_all_canonical_facts_and_declarations(self):
        log = log_fixture()
        forward = drill_down(log, DrillDownSpec("order", "region", T))
        transformed = materialize_cube(log, forward)
        reverse = roll_up(transformed, forward)
        self.assertIs(reverse.status, ComputeStatus.COMPUTED)
        restored = materialize_cube(transformed, reverse)
        self.assertEqual(restored, ComputationContext(log).log)
        self.assertEqual(reverse.value.output_digest, forward.source_digest)
        self.assertEqual(reverse.parent_computation_ids, (forward.computation_id,))

    def test_unfold_is_one_event_relabeling_not_event_duplication(self):
        log = log_fixture()
        result = unfold(log, UnfoldSpec("pack", "order"))
        self.assertEqual(len(result.value.changes), 1)
        change = result.value.changes[0]
        self.assertEqual(change.entity_id, "e1")
        self.assertEqual(len(change.relations), 3)
        transformed = materialize_cube(log, result)
        self.assertEqual(facts(transformed), facts(ComputationContext(log).log))
        self.assertEqual(len(transformed.events), 3)
        self.assertEqual(len(transformed.e2o), len(log.e2o))
        self.assertEqual(
            result.value.added_event_types[0].attributes, log.event_types[0].attributes
        )

    def test_qualifier_selection_only_drives_refinement_never_drops_relations(self):
        log = log_fixture()
        result = unfold(log, UnfoldSpec("pack", "order", ("audit",)))
        self.assertEqual(len(result.value.changes[0].relations), 1)
        transformed = materialize_cube(log, result)
        self.assertEqual(transformed.e2o, ComputationContext(log).log.e2o)
        self.assertEqual(transformed.o2o, ComputationContext(log).log.o2o)

    def test_empty_qualifiers_no_match_is_identity_transform(self):
        log = log_fixture()
        result = unfold(log, UnfoldSpec("pack", "order", ()))
        self.assertEqual(result.value.changes, ())
        self.assertEqual(result.value.added_event_types, ())
        self.assertEqual(result.source_digest, result.value.output_digest)
        transformed = materialize_cube(log, result)
        self.assertEqual(
            materialize_cube(transformed, fold(transformed, result)),
            ComputationContext(log).log,
        )

    def test_fold_restores_exact_events_and_retains_preexisting_parent_named_activity(
        self,
    ):
        log = log_fixture()
        log = replace(
            log,
            event_types=log.event_types + (EventType("(pack, order)"),),
            events=log.events + (Event("unrelated", "(pack, order)", T),),
        )
        forward = unfold(log, UnfoldSpec("pack", "order"))
        transformed = materialize_cube(log, forward)
        reverse = fold(transformed, forward)
        restored = materialize_cube(transformed, reverse)
        self.assertEqual(restored, ComputationContext(log).log)
        self.assertEqual(
            ComputationContext(restored).events_by_id["unrelated"].type, "(pack, order)"
        )

    def test_unknown_selection_explicit_and_declared_empty_type_supported(self):
        log = log_fixture()
        for result in (
            drill_down(log, DrillDownSpec("unknown", "region", T)),
            drill_down(log, DrillDownSpec("order", "unknown", T)),
            unfold(log, UnfoldSpec("unknown", "order")),
            unfold(log, UnfoldSpec("pack", "unknown")),
        ):
            with self.subTest(result=result.operator_id):
                self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
        empty = replace(
            log,
            object_types=log.object_types
            + (ObjectType("empty", (Attribute("a", ValueType.STRING),)),),
        )
        result = drill_down(empty, DrillDownSpec("empty", "a", T))
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.changes, ())

    def test_type_name_collision_is_not_implicit_merge(self):
        log = log_fixture()
        forward = drill_down(log, DrillDownSpec("order", "region", T))
        collision = replace(
            log, object_types=log.object_types + forward.value.added_object_types[:1]
        )
        self.assertIs(
            drill_down(collision, forward.spec).status, ComputeStatus.UNAVAILABLE
        )
        forward = unfold(log, UnfoldSpec("pack", "order"))
        collision = replace(
            log, event_types=log.event_types + forward.value.added_event_types
        )
        self.assertIs(unfold(collision, forward.spec).status, ComputeStatus.UNAVAILABLE)

    def test_source_changes_invalidate_forward_materialization_and_reverse(self):
        log = log_fixture()
        plan = drill_down(log, DrillDownSpec("order", "region", T))
        modified = replace(log, e2o=log.e2o[:-1])
        with self.assertRaisesRegex(ValueError, "source digest"):
            materialize_cube(modified, plan)
        transformed = materialize_cube(log, plan)
        changed = replace(transformed, e2o=transformed.e2o[:-1])
        reverse = roll_up(changed, plan)
        self.assertIs(reverse.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(reverse.issues[0].code, "invalid_cube_provenance")

    def test_forged_plan_and_request_identity_are_rejected(self):
        log = log_fixture()
        plan = unfold(log, UnfoldSpec("pack", "order"))
        with self.assertRaises(ValueError):
            materialize_cube(log, replace(plan, computation_id="forged"))
        altered = replace(plan, value=replace(plan.value, output_digest="forged"))
        with self.assertRaises(ValueError):
            materialize_cube(log, altered)
        transformed = materialize_cube(log, plan)
        with self.assertRaises(ValueError):
            fold(transformed, replace(plan, computation_id="forged"))
        result = fold(transformed, altered)
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)

    def test_wrong_inverse_kind_requires_matching_forward(self):
        log = log_fixture()
        with self.assertRaises(ValueError):
            roll_up(log, unfold(log, UnfoldSpec("pack", "order")))
        with self.assertRaises(ValueError):
            fold(log, drill_down(log, DrillDownSpec("order", "region", T)))

    def test_permutation_context_and_equivalent_timezones_preserve_identity(self):
        log = log_fixture()
        spec = DrillDownSpec("order", "region", T)
        result = drill_down(log, spec)
        reordered = replace(
            log,
            events=log.events[::-1],
            objects=log.objects[::-1],
            e2o=log.e2o[::-1],
            o2o=log.o2o[::-1],
        )
        self.assertEqual(result, drill_down(reordered, spec))
        self.assertEqual(result, drill_down(ComputationContext(log), spec))
        timezone_spec = DrillDownSpec(
            "order", "region", T.astimezone(timezone(timedelta(hours=9)))
        )
        self.assertEqual(result, drill_down(log, timezone_spec))

    def test_all_four_operators_roundtrip_through_registered_result_codec(self):
        log = log_fixture()
        for operation, inverse, spec in (
            (drill_down, roll_up, DrillDownSpec("order", "region", T)),
            (unfold, fold, UnfoldSpec("pack", "order", ("audit",))),
        ):
            with self.subTest(operation=operation.__name__):
                forward = operation(log, spec)
                loaded_forward = result_from_json(result_json_bytes(forward))
                self.assertEqual(loaded_forward, forward)
                transformed = materialize_cube(log, loaded_forward)
                reverse = inverse(transformed, loaded_forward)
                loaded_reverse = result_from_json(result_json_bytes(reverse))
                self.assertEqual(loaded_reverse, reverse)
                self.assertEqual(
                    materialize_cube(transformed, loaded_reverse),
                    ComputationContext(log).log,
                )

    def test_typed_time_snapshot_and_partial_plan_roundtrip(self):
        log = OCEL(
            object_types=(ObjectType("T", (Attribute("a", ValueType.TIME),)),),
            objects=(
                Object("o", "T", (ObjectAttr("a", T + timedelta(days=10), T),)),
                Object("missing", "T"),
            ),
        )
        result = drill_down(log, DrillDownSpec("T", "a", T))
        loaded = result_from_json(result_json_bytes(result))
        self.assertEqual(loaded, result)
        self.assertIsInstance(
            loaded.value.changes[0].attribute_value.timestamp_value, datetime
        )
        transformed = materialize_cube(log, loaded)
        reverse = result_from_json(result_json_bytes(roll_up(transformed, loaded)))
        self.assertEqual(
            materialize_cube(transformed, reverse), ComputationContext(log).log
        )

    def test_no_mutation_of_source_or_previous_plan(self):
        log = log_fixture()
        before = repr(log)
        plan = drill_down(log, DrillDownSpec("order", "region", T))
        materialize_cube(log, plan)
        self.assertEqual(repr(log), before)
        self.assertEqual(plan, drill_down(log, plan.spec))

    def test_invalid_request_shapes_and_invalid_log(self):
        with self.assertRaises(ValueError):
            DrillDownSpec("order", "region", datetime(2026, 1, 1))
        with self.assertRaises(ValueError):
            DrillDownSpec("order", "region", T, "guess_latest")
        with self.assertRaises(TypeError):
            UnfoldSpec("pack", "order", ["flow"])
        self.assertIs(
            drill_down(object(), DrillDownSpec("order", "region", T)).status,
            ComputeStatus.INVALID_INPUT,
        )


if __name__ == "__main__":
    unittest.main()
