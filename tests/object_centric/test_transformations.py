"""Hand-expected OCEL transformation views, loss policies, and audit evidence."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.transformations import (
    EventLineage,
    OCELAttributePromotionSpec,
    OCELDeduplicationSpec,
    OCELExplodeSpec,
    OCELMergeSpec,
    OCELParentChildSpec,
    deduplicate_ocel,
    explode_ocel,
    infer_parent_child_references,
    materialize_ocel_transformation,
    merge_ocel_events,
    promote_event_attribute,
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
    canonical_digest,
    validate,
)
from pix.results import result_from_json, result_json_bytes

BASE = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def at(minutes):
    return BASE + timedelta(minutes=minutes)


def event(identifier, minute=0, *, activity="A", attrs=()):
    return Event(identifier, activity, at(minute), attrs)


def log(events, links=(), *, objects=None, event_types=None, object_types=None, o2o=()):
    """Small declared fixtures; no production transformation supplies the oracle."""
    if objects is None:
        objects = (Object("x", "thing"), Object("y", "thing"))
    if object_types is None:
        object_types = (ObjectType("thing"),)
    if event_types is None:
        attrs = (
            Attribute("amount", ValueType.INTEGER),
            Attribute("tag", ValueType.STRING),
        )
        event_types = (EventType("A", attrs), EventType("B", attrs))
    return OCEL(
        event_types=event_types,
        object_types=object_types,
        events=tuple(events),
        objects=objects,
        e2o=tuple(E2O(*link) for link in links),
        o2o=o2o,
    )


def lineage(result):
    return {
        row.source_event_id: row.target_event_ids for row in result.value.event_lineage
    }


def ids(target):
    return {e.id for e in target.events}


class TransformationTestCase(unittest.TestCase):
    def materialized(self, source, result):
        self.assertEqual(result.status, ComputeStatus.COMPUTED, result.issues)
        before = canonical_digest(source)
        target = materialize_ocel_transformation(source, result)
        self.assertTrue(validate(target).valid, validate(target).errors)
        self.assertEqual(canonical_digest(source), before)
        self.assertEqual(
            canonical_digest(target).identifier, result.value.target_digest
        )
        self.assertEqual(set(lineage(result)), ids(source))
        self.assertTrue(
            all(
                set(destinations) <= ids(target)
                for destinations in lineage(result).values()
            )
        )
        return target

    def unavailable(self, result, code):
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertIn(code, {issue.code for issue in result.issues})


class EventDeduplicationTests(TransformationTestCase):
    def test_exact_duplicates_choose_lexical_id_and_preserve_qualifiers(self):
        source = log(
            (
                event("z"),
                event("a"),
                event("different-role"),
                event("different-object"),
                event("later", 1),
            ),
            (
                ("z", "x", "in"),
                ("a", "x", "in"),
                ("different-role", "x", "out"),
                ("different-object", "y", "in"),
                ("later", "x", "in"),
            ),
            o2o=(O2O("x", "y", "contains"), O2O("x", "y", "related")),
        )
        result = deduplicate_ocel(source)
        target = self.materialized(source, result)
        self.assertEqual(
            ids(target), {"a", "different-role", "different-object", "later"}
        )
        self.assertEqual(lineage(result)["z"], ("a",))
        self.assertEqual(lineage(result)["a"], ("a",))
        self.assertEqual(set(target.o2o), set(source.o2o))
        self.assertEqual(target.objects, source.objects)
        self.assertEqual(result.value.removed_e2o, (E2O("z", "x", "in"),))

    def test_attributes_and_activity_are_part_of_duplicate_identity(self):
        source = log(
            (
                event("a", attrs=(EventAttr("amount", 0),)),
                event("b", attrs=(EventAttr("amount", 1),)),
                event("c", attrs=(EventAttr("tag", "0"),)),
                event("d"),
                event("e", activity="B"),
            ),
            tuple((name, "x", "") for name in "abcde"),
        )
        target = self.materialized(source, deduplicate_ocel(source))
        self.assertEqual(ids(target), set("abcde"))

    def test_false_zero_empty_string_are_not_missing(self):
        for kind, value in (
            (ValueType.BOOLEAN, False),
            (ValueType.INTEGER, 0),
            (ValueType.STRING, ""),
        ):
            with self.subTest(kind=kind):
                source = log(
                    (
                        event("a", attrs=(EventAttr("v", value),)),
                        event("b", attrs=(EventAttr("v", value),)),
                        event("missing"),
                    ),
                    event_types=(EventType("A", (Attribute("v", kind),)),),
                )
                target = self.materialized(source, deduplicate_ocel(source))
                self.assertEqual(ids(target), {"a", "missing"})
                self.assertEqual(
                    next(e for e in target.events if e.id == "a").attributes,
                    (EventAttr("v", value),),
                )

    def test_attribute_order_is_irrelevant_after_canonical_normalization(self):
        attrs = (EventAttr("amount", 2), EventAttr("tag", "paid"))
        source = log(
            (event("a", attrs=attrs), event("b", attrs=tuple(reversed(attrs))))
        )
        result = deduplicate_ocel(source)
        self.assertEqual(ids(self.materialized(source, result)), {"a"})
        self.assertEqual(lineage(result), {"a": ("a",), "b": ("a",)})

    def test_qualified_participation_keeps_event_and_all_equivalent_lineage(self):
        source = log(
            (event("a"), event("b"), event("c"), event("original-isolate")),
            (
                ("a", "x", "in"),
                ("b", "x", "in"),
                ("b", "y", "in"),
                ("c", "x", "in"),
                ("c", "y", "in"),
                ("c", "x", "out"),
            ),
        )
        result = deduplicate_ocel(
            source, OCELDeduplicationSpec(mode="qualified_participation")
        )
        target = self.materialized(source, result)
        self.assertEqual(ids(target), ids(source))
        self.assertEqual(
            set(target.e2o),
            {E2O("a", "x", "in"), E2O("b", "y", "in"), E2O("c", "x", "out")},
        )
        self.assertEqual(lineage(result)["c"], ("a", "b", "c"))
        self.assertEqual(lineage(result)["original-isolate"], ("original-isolate",))

    def test_qualified_drop_removes_new_orphan_but_preserves_original_isolate(self):
        source = log(
            (event("a"), event("b"), event("isolate")),
            (("a", "x", "in"), ("b", "x", "in")),
        )
        result = deduplicate_ocel(
            source, OCELDeduplicationSpec("qualified_participation", False)
        )
        target = self.materialized(source, result)
        self.assertEqual(ids(target), {"a", "isolate"})
        self.assertEqual(
            lineage(result), {"a": ("a",), "b": ("a",), "isolate": ("isolate",)}
        )

    def test_qualified_policy_preserves_empty_qualifier_distinct_from_named_role(self):
        source = log((event("a"), event("b")), (("a", "x", ""), ("b", "x", "flow")))
        result = deduplicate_ocel(
            source, OCELDeduplicationSpec("qualified_participation", False)
        )
        target = self.materialized(source, result)
        self.assertEqual(set(target.e2o), set(source.e2o))
        self.assertEqual(ids(target), {"a", "b"})


class EventMergingTests(TransformationTestCase):
    def test_activity_timestamp_merges_disjoint_participants_and_isolates(self):
        source = log(
            (
                event("a"),
                event("b"),
                event("isolate"),
                event("other", activity="B"),
                event("later", 1),
            ),
            (("a", "x", "input"), ("b", "y", "output")),
        )
        result = merge_ocel_events(source)
        target = self.materialized(source, result)
        merged = lineage(result)["a"][0]
        self.assertEqual(lineage(result)["b"], (merged,))
        self.assertEqual(lineage(result)["isolate"], (merged,))
        self.assertEqual(ids(target), {merged, "other", "later"})
        self.assertEqual(
            set(target.e2o), {E2O(merged, "x", "input"), E2O(merged, "y", "output")}
        )

    def test_shared_objects_form_transitive_components_and_keep_isolates(self):
        source = log(
            (event("a"), event("b"), event("c"), event("d"), event("later", 1)),
            (
                ("a", "x", "in"),
                ("b", "x", "out"),
                ("b", "y", "in"),
                ("c", "y", "out"),
                ("later", "x", "in"),
            ),
        )
        result = merge_ocel_events(
            source, OCELMergeSpec(grouping="shared_object_components")
        )
        target = self.materialized(source, result)
        merged = lineage(result)["a"][0]
        self.assertEqual(lineage(result)["b"], (merged,))
        self.assertEqual(lineage(result)["c"], (merged,))
        self.assertEqual(ids(target), {merged, "d", "later"})
        self.assertEqual(
            {(r.object, r.qualifier) for r in target.e2o if r.event == merged},
            {("x", "in"), ("x", "out"), ("y", "in"), ("y", "out")},
        )

    def test_require_equal_refuses_disjoint_attributes(self):
        source = log(
            (
                event("a", attrs=(EventAttr("amount", 2),)),
                event("b", attrs=(EventAttr("tag", "paid"),)),
            )
        )
        self.unavailable(merge_ocel_events(source), "event_attribute_conflict")

    def test_union_nonconflicting_keeps_complete_event_attributes(self):
        source = log(
            (
                event("a", attrs=(EventAttr("amount", 2),)),
                event("b", attrs=(EventAttr("tag", "paid"),)),
            )
        )
        result = merge_ocel_events(
            source, OCELMergeSpec(attribute_policy="union_nonconflicting")
        )
        target = self.materialized(source, result)
        self.assertEqual(len(target.events), 1)
        self.assertEqual(
            set(target.events[0].attributes),
            {EventAttr("amount", 2), EventAttr("tag", "paid")},
        )

    def test_both_attribute_policies_refuse_conflicting_values(self):
        source = log(
            (
                event("a", attrs=(EventAttr("amount", 0),)),
                event("b", attrs=(EventAttr("amount", 1),)),
            )
        )
        for policy in ("require_equal", "union_nonconflicting"):
            with self.subTest(policy=policy):
                self.unavailable(
                    merge_ocel_events(source, OCELMergeSpec(attribute_policy=policy)),
                    "event_attribute_conflict",
                )

    def test_object_history_and_o2o_roles_survive_merging(self):
        history = (
            ObjectAttr("state", "new", at(-5)),
            ObjectAttr("state", "paid", at(2)),
        )
        source = log(
            (event("a"), event("b")),
            (("a", "x", "in"), ("b", "x", "in")),
            objects=(Object("x", "thing", history), Object("y", "thing")),
            object_types=(
                ObjectType("thing", (Attribute("state", ValueType.STRING),)),
            ),
            o2o=(O2O("x", "y", "contains"), O2O("x", "y", "references")),
        )
        target = self.materialized(source, merge_ocel_events(source))
        self.assertEqual(target.objects, source.objects)
        self.assertEqual(set(target.o2o), set(source.o2o))
        self.assertEqual(len(target.e2o), 1)

    def test_generated_merge_id_collision_rejects_or_suffixes(self):
        source = log((event("a"), event("b")))
        identifier = (
            merge_ocel_events(source).value.event_lineage[0].target_event_ids[0]
        )
        occupied = replace(
            source,
            events=source.events + (event(identifier, 1), event(identifier + ":1", 2)),
        )
        self.unavailable(merge_ocel_events(occupied), "generated_id_collision")
        result = merge_ocel_events(occupied, OCELMergeSpec(id_collision="suffix"))
        target = self.materialized(occupied, result)
        self.assertEqual(lineage(result)["a"], (identifier + ":2",))
        self.assertIn(identifier, ids(target))
        self.assertIn(identifier + ":1", ids(target))


def promotion_log():
    return log(
        (
            event("false", 3, activity="Boolean", attrs=(EventAttr("v", False),)),
            event("zero", 2, activity="Integer", attrs=(EventAttr("v", 0),)),
            event("text-zero", 4, activity="Text", attrs=(EventAttr("v", "0"),)),
            event("empty", 1, activity="Text", attrs=(EventAttr("v", ""),)),
            event("empty-earlier", -1, activity="Text", attrs=(EventAttr("v", ""),)),
            event("missing", activity="Text"),
        ),
        event_types=(
            EventType("Boolean", (Attribute("v", ValueType.BOOLEAN),)),
            EventType("Integer", (Attribute("v", ValueType.INTEGER),)),
            EventType("Text", (Attribute("v", ValueType.STRING),)),
        ),
    )


class AttributePromotionTests(TransformationTestCase):
    def test_false_zero_text_zero_and_empty_are_four_objects_with_first_observation(
        self,
    ):
        source = promotion_log()
        result = promote_event_attribute(
            source, OCELAttributePromotionSpec("v", "Value")
        )
        target = self.materialized(source, result)
        self.assertEqual(len(result.value.promoted_objects), 4)
        promoted = {
            (row.value_type, row.value_lexical): row
            for row in result.value.promoted_objects
        }
        self.assertEqual(
            set(promoted),
            {("boolean", "false"), ("integer", "0"), ("string", "0"), ("string", "")},
        )
        self.assertEqual(promoted[("string", "")].first_observation, at(-1))
        self.assertEqual(
            promoted[("string", "")].source_event_ids, ("empty", "empty-earlier")
        )
        self.assertEqual(result.value.skipped_event_ids, ("missing",))
        self.assertEqual(
            result.value.added_object_types,
            ("Value::boolean", "Value::integer", "Value::string"),
        )
        self.assertEqual(len(target.objects), len(source.objects) + 4)
        values_by_id = {
            obj.id: obj.attributes[0]
            for obj in target.objects
            if obj.id not in {"x", "y"}
        }
        for key, row in promoted.items():
            with self.subTest(key=key):
                self.assertEqual(
                    values_by_id[row.object_id].time, row.first_observation
                )
        self.assertIs(
            values_by_id[promoted[("boolean", "false")].object_id].value, False
        )
        self.assertIs(
            type(values_by_id[promoted[("integer", "0")].object_id].value), int
        )
        self.assertEqual(set(target.events), set(source.events))

    def test_activity_selection_and_removal_touch_only_promoted_attributes(self):
        source = promotion_log()
        spec = OCELAttributePromotionSpec(
            "v", "Value", activities=("Text",), remove_event_attribute=True
        )
        result = promote_event_attribute(source, spec)
        target = self.materialized(source, result)
        self.assertEqual(len(result.value.promoted_objects), 2)
        for item in target.events:
            with self.subTest(event=item.id):
                if item.type == "Text":
                    self.assertEqual(item.attributes, ())
                else:
                    self.assertEqual(
                        item, next(e for e in source.events if e.id == item.id)
                    )
        self.assertEqual(target.event_types, ComputationContext(source).log.event_types)

    def test_uniform_policy_rejects_mixed_primitive_types(self):
        self.unavailable(
            promote_event_attribute(
                promotion_log(),
                OCELAttributePromotionSpec("v", "Value", type_policy="require_uniform"),
            ),
            "mixed_promotion_types",
        )

    def test_uniform_policy_uses_single_unsuffixed_type(self):
        source = promotion_log()
        result = promote_event_attribute(
            source,
            OCELAttributePromotionSpec(
                "v", "Value", activities=("Integer",), type_policy="require_uniform"
            ),
        )
        target = self.materialized(source, result)
        self.assertEqual(result.value.added_object_types, ("Value",))
        self.assertEqual(
            [o.type for o in target.objects if o.id not in {"x", "y"}], ["Value"]
        )

    def test_missing_reject_is_explicit_and_unselected_missing_is_ignored(self):
        source = promotion_log()
        self.unavailable(
            promote_event_attribute(
                source, OCELAttributePromotionSpec("v", "Value", missing="reject")
            ),
            "promotion_attribute_missing",
        )
        selected = promote_event_attribute(
            source,
            OCELAttributePromotionSpec(
                "v", "Value", activities=("Integer",), missing="reject"
            ),
        )
        self.materialized(source, selected)
        self.assertEqual(selected.value.skipped_event_ids, ())

    def test_compatible_type_reuse_requires_explicit_policy(self):
        source = promotion_log()
        source = replace(
            source,
            object_types=source.object_types
            + (ObjectType("Value::integer", (Attribute("value", ValueType.INTEGER),)),),
        )
        spec = OCELAttributePromotionSpec("v", "Value", activities=("Integer",))
        self.unavailable(
            promote_event_attribute(source, spec), "promotion_type_collision"
        )
        result = promote_event_attribute(
            source, replace(spec, reuse_compatible_type=True)
        )
        self.materialized(source, result)
        self.assertEqual(result.value.added_object_types, ())

    def test_incompatible_type_reuse_is_rejected(self):
        source = promotion_log()
        source = replace(
            source,
            object_types=source.object_types
            + (ObjectType("Value::integer", (Attribute("value", ValueType.STRING),)),),
        )
        self.unavailable(
            promote_event_attribute(
                source,
                OCELAttributePromotionSpec(
                    "v", "Value", activities=("Integer",), reuse_compatible_type=True
                ),
            ),
            "promotion_type_collision",
        )

    def test_generated_object_id_collision_does_not_overwrite_existing_object(self):
        source = promotion_log()
        spec = OCELAttributePromotionSpec("v", "Value", activities=("Integer",))
        identifier = (
            promote_event_attribute(source, spec).value.promoted_objects[0].object_id
        )
        source = replace(
            source, objects=source.objects + (Object(identifier, "thing"),)
        )
        self.unavailable(
            promote_event_attribute(source, spec), "generated_id_collision"
        )
        result = promote_event_attribute(source, replace(spec, id_collision="suffix"))
        target = self.materialized(source, result)
        self.assertEqual(result.value.promoted_objects[0].object_id, identifier + ":1")
        self.assertIn(Object(identifier, "thing"), target.objects)


class EventExplosionTests(TransformationTestCase):
    def fixture(self):
        return log(
            (
                event("a", attrs=(EventAttr("amount", 0), EventAttr("tag", ""))),
                event("isolate", 1),
            ),
            (
                ("a", "x", "input"),
                ("a", "x", "output"),
                ("a", "y", "input"),
                ("a", "z", "context"),
            ),
            objects=(
                Object("x", "thing"),
                Object("y", "thing"),
                Object("z", "resource"),
            ),
            object_types=(ObjectType("thing"), ObjectType("resource")),
            o2o=(O2O("x", "y", "contains"),),
        )

    def test_explosion_creates_one_clone_per_object_and_keeps_all_roles(self):
        source = self.fixture()
        result = explode_ocel(source)
        target = self.materialized(source, result)
        self.assertEqual(len(lineage(result)["a"]), 3)
        self.assertNotIn("a", ids(target))
        self.assertEqual(lineage(result)["isolate"], ("isolate",))
        for object_id in ("x", "y", "z"):
            with self.subTest(object=object_id):
                related = {r.event for r in target.e2o if r.object == object_id}
                self.assertEqual(len(related), 1)
                clone = next(e for e in target.events if e.id in related)
                self.assertEqual(
                    (clone.type, clone.time, clone.attributes),
                    ("A", at(0), source.events[0].attributes),
                )
                self.assertEqual(
                    {r.qualifier for r in target.e2o if r.event == clone.id},
                    {r.qualifier for r in source.e2o if r.object == object_id},
                )
        self.assertEqual(set(target.o2o), set(source.o2o))
        self.assertEqual(set(target.objects), set(source.objects))

    def test_selection_retains_residual_event_and_selected_objects_other_roles(self):
        source = self.fixture()
        result = explode_ocel(
            source, OCELExplodeSpec(object_types=("thing",), qualifiers=("output",))
        )
        target = self.materialized(source, result)
        destinations = lineage(result)["a"]
        self.assertEqual(len(destinations), 2)
        self.assertIn("a", destinations)
        clone = next(identifier for identifier in destinations if identifier != "a")
        self.assertEqual(
            {r for r in target.e2o if r.event == clone},
            {E2O(clone, "x", "input"), E2O(clone, "x", "output")},
        )
        self.assertEqual(
            {r for r in target.e2o if r.event == "a"},
            {E2O("a", "y", "input"), E2O("a", "z", "context")},
        )

    def test_drop_isolates_is_explicit_with_empty_destination_lineage(self):
        source = self.fixture()
        result = explode_ocel(source, OCELExplodeSpec(isolated_events="drop"))
        target = self.materialized(source, result)
        self.assertNotIn("isolate", ids(target))
        self.assertEqual(lineage(result)["isolate"], ())

    def test_empty_selection_preserves_participating_events(self):
        source = self.fixture()
        result = explode_ocel(
            source, OCELExplodeSpec(object_types=(), isolated_events="drop")
        )
        target = self.materialized(source, result)
        self.assertEqual(ids(target), {"a"})
        self.assertEqual(set(target.e2o), set(source.e2o))

    def test_clone_ids_are_reordering_stable_and_collisions_are_explicit(self):
        source = self.fixture()
        original = explode_ocel(source)
        reordered = replace(
            source,
            events=tuple(reversed(source.events)),
            e2o=tuple(reversed(source.e2o)),
            objects=tuple(reversed(source.objects)),
        )
        self.assertEqual(original, explode_ocel(reordered))
        identifier = lineage(original)["a"][0]
        occupied = replace(source, events=source.events + (event(identifier, 5),))
        self.unavailable(explode_ocel(occupied), "generated_id_collision")
        result = explode_ocel(occupied, OCELExplodeSpec(id_collision="suffix"))
        target = self.materialized(occupied, result)
        self.assertIn(identifier + ":1", lineage(result)["a"])
        self.assertIn(identifier, ids(target))


def parent_log(
    *,
    second_parent=False,
    same_time=False,
    history=(),
    parent_attribute_type=ValueType.STRING,
):
    return log(
        (event("first"), event("same-parent", 1), event("last", 0 if same_time else 3)),
        (
            ("first", "child", "member"),
            ("first", "p", "owner"),
            ("same-parent", "child", "member"),
            ("same-parent", "p", "owner"),
            ("last", "child", "member"),
            ("last", "q" if second_parent else "p", "owner"),
        ),
        objects=(
            Object("child", "item", history),
            Object("p", "order"),
            Object("q", "order"),
        ),
        object_types=(
            ObjectType(
                "item",
                (
                    Attribute("parent_id", parent_attribute_type),
                    Attribute("state", ValueType.STRING),
                ),
            ),
            ObjectType("order"),
        ),
        o2o=(O2O("child", "p", "legacy-role"),),
    )


class ParentChildInferenceTests(TransformationTestCase):
    def test_unique_parent_rejects_conflicting_existing_same_role_o2o(self):
        source = parent_log()
        source = replace(source, o2o=source.o2o + (O2O("child", "q", "pix:parent"),))
        for output in ("attribute_history", "o2o", "both"):
            with self.subTest(output=output):
                result = infer_parent_child_references(
                    source, OCELParentChildSpec("item", "order", output=output)
                )
                self.unavailable(result, "ambiguous_parent")

    def test_other_o2o_roles_do_not_assert_unique_parenthood(self):
        source = parent_log()
        source = replace(
            source, o2o=source.o2o + (O2O("child", "q", "previous-owner"),)
        )
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order", output="both")
        )
        target = self.materialized(source, result)
        self.assertIn(O2O("child", "q", "previous-owner"), target.o2o)
        self.assertIn(O2O("child", "p", "pix:parent"), target.o2o)

    def test_temporal_assignment_preserves_old_o2o_and_adds_observed_parent(self):
        source = parent_log()
        source = replace(source, o2o=source.o2o + (O2O("child", "q", "pix:parent"),))
        result = infer_parent_child_references(
            source,
            OCELParentChildSpec("item", "order", assignment="temporal", output="both"),
        )
        target = self.materialized(source, result)
        self.assertIn(O2O("child", "q", "pix:parent"), target.o2o)
        self.assertIn(O2O("child", "p", "pix:parent"), target.o2o)
        self.assertEqual({a.parent_id for a in result.value.parent_assignments}, {"p"})

    def test_no_candidate_is_noop_without_empty_history_declaration(self):
        source = parent_log()
        source = replace(source, object_types=(ObjectType("item"), ObjectType("order")))
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order", qualifiers=())
        )
        target = self.materialized(source, result)
        self.assertEqual(canonical_digest(source), canonical_digest(target))
        self.assertEqual(result.value.parent_assignments, ())
        self.assertEqual(result.value.modified_object_types, ())

    def test_unique_parent_records_observations_without_redundant_history(self):
        source = parent_log(history=(ObjectAttr("state", "open", at(-5)),))
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order", output="both")
        )
        target = self.materialized(source, result)
        child = next(obj for obj in target.objects if obj.id == "child")
        self.assertEqual(
            set(child.attributes),
            {ObjectAttr("state", "open", at(-5)), ObjectAttr("parent_id", "p", at(0))},
        )
        self.assertEqual(
            [
                (a.time, a.parent_id, a.history_added, a.witness_event_ids)
                for a in result.value.parent_assignments
            ],
            [
                (at(0), "p", True, ("first",)),
                (at(1), "p", False, ("same-parent",)),
                (at(3), "p", False, ("last",)),
            ],
        )
        self.assertEqual(result.value.added_o2o, (O2O("child", "p", "pix:parent"),))
        self.assertIn(O2O("child", "p", "legacy-role"), target.o2o)
        self.assertEqual(target.e2o, ComputationContext(source).log.e2o)

    def test_unique_parent_rejects_multiple_observed_parents(self):
        source = parent_log(second_parent=True)
        self.unavailable(
            infer_parent_child_references(source, OCELParentChildSpec("item", "order")),
            "ambiguous_parent",
        )

    def test_temporal_parent_changes_preserve_other_and_existing_asof_history(self):
        history = (
            ObjectAttr("state", "open", at(-5)),
            ObjectAttr("parent_id", "q", at(-2)),
            ObjectAttr("parent_id", "p", at(2)),
        )
        source = parent_log(second_parent=True, history=history)
        result = infer_parent_child_references(
            source,
            OCELParentChildSpec("item", "order", assignment="temporal", output="both"),
        )
        target = self.materialized(source, result)
        child = next(obj for obj in target.objects if obj.id == "child")
        self.assertEqual(
            set(child.attributes),
            set(history)
            | {
                ObjectAttr("parent_id", "p", at(0)),
                ObjectAttr("parent_id", "q", at(3)),
            },
        )
        for minute, expected in (
            (-3, None),
            (-1, "q"),
            (0, "p"),
            (1, "p"),
            (2, "p"),
            (3, "q"),
            (4, "q"),
        ):
            with self.subTest(minute=minute):
                observed = [
                    a
                    for a in child.attributes
                    if a.name == "parent_id" and a.time <= at(minute)
                ]
                actual = max(observed, key=lambda a: a.time).value if observed else None
                self.assertEqual(actual, expected)
        self.assertEqual(
            set(result.value.added_o2o),
            {O2O("child", "p", "pix:parent"), O2O("child", "q", "pix:parent")},
        )

    def test_temporal_same_timestamp_conflict_is_not_resolved_by_event_id(self):
        source = parent_log(second_parent=True, same_time=True)
        self.unavailable(
            infer_parent_child_references(
                source, OCELParentChildSpec("item", "order", assignment="temporal")
            ),
            "simultaneous_parent_conflict",
        )

    def test_existing_history_collision_at_observation_time_is_rejected(self):
        source = parent_log(history=(ObjectAttr("parent_id", "q", at(0)),))
        self.unavailable(
            infer_parent_child_references(
                source, OCELParentChildSpec("item", "order", assignment="temporal")
            ),
            "parent_history_collision",
        )

    def test_unique_parent_rejects_conflicting_prior_or_future_history(self):
        for minute in (-1, 4):
            with self.subTest(minute=minute):
                source = parent_log(history=(ObjectAttr("parent_id", "q", at(minute)),))
                self.unavailable(
                    infer_parent_child_references(
                        source, OCELParentChildSpec("item", "order")
                    ),
                    "parent_history_conflict",
                )

    def test_compatible_existing_history_reuses_value_and_accumulates_witnesses(self):
        source = parent_log(history=(ObjectAttr("parent_id", "p", at(-1)),))
        source = replace(
            source,
            events=source.events + (event("also-first"),),
            e2o=source.e2o
            + (E2O("also-first", "child", "member"), E2O("also-first", "p", "owner")),
        )
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order")
        )
        target = self.materialized(source, result)
        self.assertEqual(target.objects, ComputationContext(source).log.objects)
        self.assertFalse(any(a.history_added for a in result.value.parent_assignments))
        self.assertEqual(
            result.value.parent_assignments[0].witness_event_ids,
            ("also-first", "first"),
        )

    def test_o2o_only_has_no_history_or_type_mutation_and_explicit_roles(self):
        source = parent_log(second_parent=True)
        result = infer_parent_child_references(
            source,
            OCELParentChildSpec(
                "item",
                "order",
                assignment="temporal",
                output="o2o",
                relation_qualifier="observed-parent",
            ),
        )
        target = self.materialized(source, result)
        self.assertEqual(target.objects, ComputationContext(source).log.objects)
        self.assertEqual(
            target.object_types, ComputationContext(source).log.object_types
        )
        self.assertFalse(any(a.history_added for a in result.value.parent_assignments))
        self.assertEqual(
            set(result.value.added_o2o),
            {
                O2O("child", "p", "observed-parent"),
                O2O("child", "q", "observed-parent"),
            },
        )

    def test_qualifier_selection_requires_both_participants_to_survive(self):
        source = parent_log()
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order", qualifiers=("owner",))
        )
        target = self.materialized(source, result)
        self.assertEqual(result.value.parent_assignments, ())
        self.assertEqual(target.objects, ComputationContext(source).log.objects)
        included = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order", qualifiers=("owner", "member"))
        )
        self.assertEqual(len(included.value.parent_assignments), 3)

    def test_parent_attribute_requires_string_declaration_only_for_history_output(self):
        source = parent_log(parent_attribute_type=ValueType.INTEGER)
        spec = OCELParentChildSpec("item", "order")
        self.unavailable(
            infer_parent_child_references(source, spec),
            "parent_attribute_type_conflict",
        )
        self.materialized(
            source, infer_parent_child_references(source, replace(spec, output="o2o"))
        )

    def test_missing_parent_attribute_declaration_is_added_and_reported(self):
        source = parent_log()
        source = replace(source, object_types=(ObjectType("item"), ObjectType("order")))
        result = infer_parent_child_references(
            source, OCELParentChildSpec("item", "order")
        )
        target = self.materialized(source, result)
        self.assertEqual(result.value.modified_object_types, ("item",))
        self.assertEqual(
            next(t for t in target.object_types if t.name == "item").attributes,
            (Attribute("parent_id", ValueType.STRING),),
        )


class TransformationIdentityTests(TransformationTestCase):
    def test_computed_json_roundtrips_materialize_all_five_operation_payloads(self):
        event_source = log(
            (event("a"), event("b")), (("a", "x", "in"), ("b", "y", "out"))
        )
        promoted_source = promotion_log()
        parents = parent_log(second_parent=True)
        cases = (
            (event_source, deduplicate_ocel(event_source)),
            (event_source, merge_ocel_events(event_source)),
            (event_source, explode_ocel(event_source)),
            (
                promoted_source,
                promote_event_attribute(
                    promoted_source, OCELAttributePromotionSpec("v", "Value")
                ),
            ),
            (
                parents,
                infer_parent_child_references(
                    parents,
                    OCELParentChildSpec(
                        "item", "order", assignment="temporal", output="both"
                    ),
                ),
            ),
        )
        for source, result in cases:
            with self.subTest(operator=result.operator_id):
                encoded = result_json_bytes(result)
                restored = result_from_json(encoded)
                self.assertEqual(restored, result)
                self.assertEqual(result_json_bytes(restored), encoded)
                expected = self.materialized(source, result)
                self.assertEqual(
                    materialize_ocel_transformation(source, restored), expected
                )

    def test_unavailable_json_roundtrips_preserve_refusal_evidence(self):
        conflict = log(
            (
                event("a", attrs=(EventAttr("amount", 0),)),
                event("b", attrs=(EventAttr("amount", 1),)),
            )
        )
        cases = (
            merge_ocel_events(conflict),
            promote_event_attribute(
                promotion_log(),
                OCELAttributePromotionSpec("v", "Value", missing="reject"),
            ),
            explode_ocel(conflict, OCELExplodeSpec(object_types=("unknown",))),
            infer_parent_child_references(
                parent_log(second_parent=True), OCELParentChildSpec("item", "order")
            ),
        )
        for result in cases:
            with self.subTest(operator=result.operator_id):
                self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
                restored = result_from_json(result_json_bytes(result))
                self.assertEqual(restored, result)
                self.assertIsNone(restored.value)
                self.assertTrue(restored.issues)

    def test_invalid_input_json_roundtrips_cover_every_spec(self):
        source = log((event("a"),), (("unknown-event", "x", "in"),))
        calls = (
            (deduplicate_ocel, OCELDeduplicationSpec()),
            (merge_ocel_events, OCELMergeSpec()),
            (promote_event_attribute, OCELAttributePromotionSpec("amount", "Value")),
            (explode_ocel, OCELExplodeSpec()),
            (infer_parent_child_references, OCELParentChildSpec("item", "order")),
        )
        for operation, spec in calls:
            with self.subTest(operation=operation.__name__):
                result = operation(source, spec)
                self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
                self.assertEqual(result_from_json(result_json_bytes(result)), result)

    def test_all_operations_accept_context_and_preserve_valid_canonical_output(self):
        source = parent_log()
        context = ComputationContext(source)
        calls = (
            (deduplicate_ocel, OCELDeduplicationSpec()),
            (merge_ocel_events, OCELMergeSpec()),
            (promote_event_attribute, OCELAttributePromotionSpec("amount", "Value")),
            (explode_ocel, OCELExplodeSpec()),
            (infer_parent_child_references, OCELParentChildSpec("item", "order")),
        )
        for operation, spec in calls:
            with self.subTest(operation=operation.__name__):
                result = operation(source, spec)
                self.assertEqual(result, operation(context, spec))
                target = self.materialized(source, result)
                self.assertEqual(
                    target, materialize_ocel_transformation(context, result)
                )

    def test_all_operations_reject_dangling_e2o_and_incompatible_attribute_types(self):
        valid = parent_log()
        broken = (
            replace(valid, e2o=valid.e2o + (E2O("absent", "child", "member"),)),
            replace(
                valid,
                events=(
                    replace(valid.events[0], attributes=(EventAttr("amount", False),)),
                )
                + valid.events[1:],
            ),
        )
        calls = (
            (deduplicate_ocel, OCELDeduplicationSpec()),
            (merge_ocel_events, OCELMergeSpec()),
            (promote_event_attribute, OCELAttributePromotionSpec("amount", "Value")),
            (explode_ocel, OCELExplodeSpec()),
            (infer_parent_child_references, OCELParentChildSpec("item", "order")),
        )
        for source in broken:
            for operation, spec in calls:
                with self.subTest(operation=operation.__name__, source=source):
                    result = operation(source, spec)
                    self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
                    self.assertIsNone(result.value)
                    self.assertTrue(result.issues)

    def test_materialization_rejects_changed_source_even_when_event_count_is_equal(
        self,
    ):
        source = log((event("a"), event("b")))
        result = merge_ocel_events(source)
        changed = replace(source, events=(event("a", 1), event("b")))
        with self.assertRaisesRegex(ValueError, "source"):
            materialize_ocel_transformation(changed, result)

    def test_materialization_rejects_every_tampered_evidence_and_identity_dimension(
        self,
    ):
        source = log((event("a"), event("b")))
        result = merge_ocel_events(source)
        variants = (
            replace(result, spec=OCELMergeSpec(grouping="shared_object_components")),
            replace(result, computation_id="sha256:tampered"),
            replace(result, operator_version="999.0"),
            replace(result, parent_computation_ids=("sha256:invented",)),
            replace(
                result, value=replace(result.value, target_digest="sha256:tampered")
            ),
            replace(result, value=replace(result.value, source_event_count=99)),
            replace(
                result,
                value=replace(
                    result.value, event_lineage=(EventLineage("a", ("missing",)),)
                ),
            ),
        )
        for altered in variants:
            with self.subTest(altered=altered):
                with self.assertRaises(ValueError):
                    materialize_ocel_transformation(source, altered)

    def test_unavailable_plan_and_unknown_operator_cannot_be_materialized(self):
        source = log(
            (
                event("a", attrs=(EventAttr("amount", 0),)),
                event("b", attrs=(EventAttr("amount", 1),)),
            )
        )
        with self.assertRaisesRegex(ValueError, "computed"):
            materialize_ocel_transformation(source, merge_ocel_events(source))
        result = deduplicate_ocel(source)
        with self.assertRaises(TypeError):
            materialize_ocel_transformation(
                source, replace(result, operator_id="untrusted.module.callable")
            )

    def test_unknown_selection_names_are_explicitly_unavailable(self):
        source = parent_log()
        cases = (
            (
                promote_event_attribute(
                    source,
                    OCELAttributePromotionSpec(
                        "amount", "Value", activities=("absent",)
                    ),
                ),
                "unknown_activity",
            ),
            (
                explode_ocel(source, OCELExplodeSpec(object_types=("absent",))),
                "unknown_object_type",
            ),
            (
                infer_parent_child_references(
                    source, OCELParentChildSpec("absent", "order")
                ),
                "unknown_object_type",
            ),
        )
        for result, code in cases:
            with self.subTest(code=code):
                self.unavailable(result, code)


if __name__ == "__main__":
    unittest.main()
