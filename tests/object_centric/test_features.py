"""Independent hand calculations for native object-centric feature profiles."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.contracts.execution import ExecutionSpec
from pix.contracts.result import ComputeStatus
from pix.object_centric.features import (
    EVENT_FEATURES,
    EXECUTION_FEATURES,
    ObjectFeature,
    ObjectFeatureAggregationSpec,
    ObjectFeatureEncodingSpec,
    ObjectFeatureFitSpec,
    ObjectFeatureSpec,
    ObjectFeatureSplitSpec,
    ObjectFeatureTransformSpec,
    aggregate_object_features,
    encode_object_features,
    extract_object_features,
    fit_object_feature_encoder,
    split_object_features,
    transform_object_features,
)
from pix.ocel import (
    E2O,
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

BASE = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
MINUTE = 60_000_000


def at(minutes):
    return BASE + timedelta(minutes=minutes)


def join_log():
    attributes = (
        Attribute("start", ValueType.TIME),
        Attribute("amount", ValueType.INTEGER),
        Attribute("resource", ValueType.STRING),
    )

    def event(identifier, activity, minute, start, amount, resource):
        return Event(
            identifier,
            activity,
            at(minute),
            (
                EventAttr("start", at(start)),
                EventAttr("amount", amount),
                EventAttr("resource", resource),
            ),
        )

    return OCEL(
        event_types=tuple(
            EventType(name, attributes) for name in ("arrive", "join", "finish")
        ),
        object_types=(ObjectType("order"), ObjectType("item"), ObjectType("absent")),
        events=(
            event("event-a", "arrive", 0, -1, 2, "r"),
            event("event-b", "arrive", 10, 9, 4, "r"),
            event("event-join", "join", 25, 15, 8, "r"),
            event("event-end", "finish", 40, 30, 16, "s"),
        ),
        objects=(Object("order-1", "order"), Object("item-1", "item")),
        e2o=(
            E2O("event-a", "order-1", "flow"),
            E2O("event-b", "item-1", "flow"),
            E2O("event-join", "order-1", "flow"),
            E2O("event-join", "item-1", "flow"),
            E2O("event-end", "order-1", "flow"),
        ),
    )


def simple_log(records, links, objects=None):
    """records are (event ID, activity, minute), links are (event ID, object ID)."""
    if objects is None:
        objects = tuple(
            Object(identifier, "thing") for identifier in sorted({o for _, o in links})
        )
    return OCEL(
        event_types=tuple(EventType(name) for name in sorted({r[1] for r in records})),
        object_types=tuple(
            ObjectType(name) for name in sorted({o.type for o in objects})
        ),
        events=tuple(
            Event(identifier, activity, at(minute))
            for identifier, activity, minute in records
        ),
        objects=objects,
        e2o=tuple(E2O(event, obj, "flow") for event, obj in links),
    )


def value(cell):
    return {
        "integer": cell.integer,
        "real": cell.real,
        "text": cell.text,
        "boolean": cell.boolean,
        "time": cell.time,
        "items": cell.items,
        "unknown": None,
    }[cell.kind]


def event_row(result, identifier):
    return next(row for row in result.value.rows if row.event_id == identifier)


class OCFeatureCalculationTests(unittest.TestCase):
    def test_all_27_ocpa_event_feature_families_have_hand_calculated_values(self):
        cases = (
            (ObjectFeature("number_of_objects"), 2),
            (ObjectFeature("event_activity", activity="join"), 1),
            (ObjectFeature("service_time", attribute="start"), 10 * MINUTE),
            (ObjectFeature("event_identity"), 1),
            (ObjectFeature("event_type_count", object_type="item"), 1),
            (ObjectFeature("preceding_activities", activity="arrive"), 2),
            (ObjectFeature("previous_activity_count", activity="arrive"), 2),
            (ObjectFeature("current_activities", activity="arrive"), 1),
            (
                ObjectFeature(
                    "agg_previous_char_values", attribute="amount", aggregation="sum"
                ),
                6,
            ),
            (
                ObjectFeature(
                    "preceding_char_values", attribute="amount", aggregation="mean"
                ),
                3.0,
            ),
            (ObjectFeature("characteristic_value", attribute="amount"), 8),
            (
                ObjectFeature(
                    "current_resource_workload",
                    attribute="resource",
                    horizon_microseconds=25 * MINUTE,
                ),
                2,
            ),
            (
                ObjectFeature(
                    "current_total_workload", horizon_microseconds=25 * MINUTE
                ),
                2,
            ),
            (ObjectFeature("event_resource", attribute="resource", value="r"), 1),
            (
                ObjectFeature(
                    "current_total_object_count", horizon_microseconds=25 * MINUTE
                ),
                2,
            ),
            (ObjectFeature("previous_object_count"), 2),
            (ObjectFeature("previous_type_count", object_type="item"), 1),
            (ObjectFeature("event_objects", value="item-1"), 1),
            (ObjectFeature("execution_duration"), 40 * MINUTE),
            (ObjectFeature("elapsed_time"), 25 * MINUTE),
            (ObjectFeature("remaining_time"), 15 * MINUTE),
            (ObjectFeature("lagging_time", object_type="item"), 10 * MINUTE),
            (ObjectFeature("pooling_time", object_type="item"), 0),
            (ObjectFeature("waiting_time", attribute="start"), 5 * MINUTE),
            (ObjectFeature("sojourn_time"), 15 * MINUTE),
            (ObjectFeature("synchronization_time"), 10 * MINUTE),
            (ObjectFeature("flow_time"), 25 * MINUTE),
        )
        self.assertEqual(len(cases), 27)
        self.assertEqual({f.name for f, _ in cases}, set(EVENT_FEATURES[:27]))
        result = extract_object_features(
            join_log(), ObjectFeatureSpec(tuple(f for f, _ in cases))
        )
        self.assertIsNotNone(result.value)
        row = event_row(result, "event-join")
        for (feature, expected), cell in zip(cases, row.cells):
            with self.subTest(feature=feature.name):
                self.assertEqual(value(cell), expected)
                self.assertEqual(
                    cell.role,
                    "target"
                    if feature.name in ("execution_duration", "remaining_time")
                    else "input",
                )
        self.assertEqual(row.object_members, ("item-1", "order-1"))

    def test_all_ten_execution_features_keep_target_role(self):
        cases = (
            (ObjectFeature("number_of_events"), 4),
            (ObjectFeature("number_of_ending_events"), 1),
            (ObjectFeature("throughput_time"), 40 * MINUTE),
            (ObjectFeature("execution"), 1),
            (ObjectFeature("number_of_objects"), 2),
            (ObjectFeature("unique_activities"), 3),
            (ObjectFeature("number_of_starting_events"), 2),
            (ObjectFeature("delta_last_event"), 15 * MINUTE),
            (ObjectFeature("service_time", attribute="start"), 22 * MINUTE),
            (ObjectFeature("avg_service_time", attribute="start"), 5.5 * MINUTE),
        )
        self.assertEqual({f.name for f, _ in cases}, set(EXECUTION_FEATURES))
        result = extract_object_features(
            join_log(),
            ObjectFeatureSpec(tuple(f for f, _ in cases), granularity="execution"),
        )
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(len(result.value.rows), 1)
        for (feature, expected), cell in zip(cases, result.value.rows[0].cells):
            with self.subTest(feature=feature.name):
                self.assertEqual(value(cell), expected)
                self.assertEqual(cell.role, "target")
        self.assertEqual(
            (result.value.observed_cell_count, result.value.target_cell_count), (0, 10)
        )

    def test_missing_service_and_predecessor_observation_remain_unknown(self):
        log = join_log()
        first = replace(
            log.events[0],
            attributes=tuple(a for a in log.events[0].attributes if a.name != "start"),
        )
        log = replace(log, events=(first,) + log.events[1:])
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("service_time", attribute="start"),
                    ObjectFeature("flow_time"),
                )
            ),
        )
        self.assertTrue(
            all(c.kind == "unknown" for c in event_row(result, "event-a").cells)
        )
        self.assertEqual(
            event_row(result, "event-a").cells[1].reason,
            "predecessor_arrival_unobserved",
        )
        execution = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("service_time", attribute="start"),
                    ObjectFeature("avg_service_time", attribute="start"),
                ),
                granularity="execution",
            ),
        )
        self.assertTrue(
            all(
                c.reason == "incomplete_service_coverage"
                for c in execution.value.rows[0].cells
            )
        )

    def test_lagging_absent_global_type_does_not_raise_and_selected_absence_is_unknown(
        self,
    ):
        result = extract_object_features(
            join_log(),
            ObjectFeatureSpec(
                (
                    ObjectFeature("lagging_time", object_type="item"),
                    ObjectFeature("lagging_time", object_type="absent"),
                )
            ),
        )
        cells = event_row(result, "event-join").cells
        self.assertEqual(value(cells[0]), 10 * MINUTE)
        self.assertEqual(cells[1].reason, "object_type_arrival_unobserved")

    def test_pooling_uses_immediate_object_arc_not_all_common_participants(self):
        log = simple_log(
            (("p", "P", 0), ("q", "Q", 5), ("j", "J", 10)),
            (("p", "a"), ("p", "b"), ("q", "b"), ("j", "a"), ("j", "b")),
            (Object("a", "A"), Object("b", "B")),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("pooling_time", object_type="B"),
                    ObjectFeature("lagging_time", object_type="B"),
                )
            ),
        )
        # p precedes j through a only; b's immediate arrival at j is q, not p.
        self.assertEqual(
            tuple(map(value, event_row(result, "j").cells)), (0, 5 * MINUTE)
        )

    def test_missing_historical_resource_prevents_false_precise_workload(self):
        log = join_log()
        missing = replace(
            log.events[0],
            attributes=tuple(
                a for a in log.events[0].attributes if a.name != "resource"
            ),
        )
        log = replace(log, events=(missing,) + log.events[1:])
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature(
                        "current_resource_workload",
                        attribute="resource",
                        horizon_microseconds=25 * MINUTE,
                    ),
                    ObjectFeature(
                        "current_resource_workload",
                        attribute="resource",
                        horizon_microseconds=15 * MINUTE,
                    ),
                    ObjectFeature(
                        "current_total_workload", horizon_microseconds=25 * MINUTE
                    ),
                )
            ),
        )
        cells = event_row(result, "event-join").cells
        self.assertEqual(cells[0].reason, "historical_resource_coverage_incomplete")
        self.assertEqual(
            value(cells[1]), 1
        )  # Missing resource is outside this smaller window.
        self.assertEqual(
            value(cells[2]), 2
        )  # Total completion count needs no resource assignment.

    def test_qualifier_duplicates_do_not_multiply_participation(self):
        log = join_log()
        log = replace(log, e2o=log.e2o + (E2O("event-join", "item-1", "also"),))
        result = extract_object_features(
            log, ObjectFeatureSpec((ObjectFeature("number_of_objects"),))
        )
        self.assertEqual(value(event_row(result, "event-join").cells[0]), 2)
        selected = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("number_of_objects"),),
                execution=ExecutionSpec("connected_components", qualifiers=("also",)),
            ),
        )
        self.assertEqual(value(event_row(selected, "event-join").cells[0]), 1)

    def test_strict_prefix_excludes_current_and_all_ties(self):
        log = simple_log(
            (("event-a", "A", 0), ("event-b", "B", 0), ("event-c", "A", 1)),
            (("event-a", "o"), ("event-b", "o"), ("event-c", "o")),
        )
        features = (
            ObjectFeature("prefix_event_count"),
            ObjectFeature("previous_activity_count", activity="B"),
        )
        strict = extract_object_features(log, ObjectFeatureSpec(features))
        through = extract_object_features(
            log, ObjectFeatureSpec(features, prefix_policy="through_timestamp")
        )
        self.assertEqual(tuple(map(value, event_row(strict, "event-a").cells)), (0, 0))
        self.assertEqual(tuple(map(value, event_row(through, "event-a").cells)), (2, 1))
        self.assertEqual(value(event_row(strict, "event-c").cells[0]), 2)
        self.assertNotEqual(strict.computation_id, through.computation_id)

    def test_trailing_window_has_explicit_left_and_right_boundaries(self):
        requests = (
            ObjectFeature("current_total_workload", horizon_microseconds=15 * MINUTE),
        )
        strict = extract_object_features(join_log(), ObjectFeatureSpec(requests))
        through = extract_object_features(
            join_log(), ObjectFeatureSpec(requests, prefix_policy="through_timestamp")
        )
        # At 09:25, 09:10 is included, 09:00 is outside, and 09:25 is profile-dependent.
        self.assertEqual(value(event_row(strict, "event-join").cells[0]), 1)
        self.assertEqual(value(event_row(through, "event-join").cells[0]), 2)

    def test_new_interactions_are_not_recounted_for_repeated_pairs(self):
        log = simple_log(
            (("event-01", "A", 0), ("event-02", "A", 1), ("event-03", "A", 2)),
            (
                ("event-01", "a"),
                ("event-01", "b"),
                ("event-02", "a"),
                ("event-02", "b"),
                ("event-03", "a"),
                ("event-03", "b"),
                ("event-03", "c"),
            ),
        )
        result = extract_object_features(
            log, ObjectFeatureSpec((ObjectFeature("new_interactions"),))
        )
        self.assertEqual(
            [
                value(event_row(result, e).cells[0])
                for e in ("event-01", "event-02", "event-03")
            ],
            [1, 0, 2],
        )

    def test_start_end_features_use_whole_identifiers(self):
        log = simple_log(
            (("event-start", "A", 0), ("event-end", "B", 1)),
            (("event-start", "o"), ("event-end", "o")),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("start_object_type_count", object_type="thing"),
                    ObjectFeature("end_object_type_count", object_type="thing"),
                )
            ),
        )
        self.assertEqual(
            tuple(map(value, event_row(result, "event-start").cells)), (1, 0)
        )
        self.assertEqual(
            tuple(map(value, event_row(result, "event-end").cells)), (0, 1)
        )
        self.assertEqual(event_row(result, "event-end").cells[1].role, "target")

    def test_object_wip_counts_earlier_overlapping_objects_and_self(self):
        log = simple_log(
            (
                ("a-start", "A", 0),
                ("a-end", "B", 10),
                ("b-start", "A", 2),
                ("b-end", "B", 3),
            ),
            (("a-start", "a"), ("a-end", "a"), ("b-start", "b"), ("b-end", "b")),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("work_in_progress"),
                    ObjectFeature("lifecycle_duration"),
                ),
                granularity="object",
            ),
        )
        rows = {r.object_id: r for r in result.value.rows}
        self.assertEqual(tuple(map(value, rows["a"].cells)), (2, 10 * MINUTE))
        self.assertEqual(tuple(map(value, rows["b"].cells)), (2, MINUTE))
        self.assertTrue(
            all(c.role == "target" for r in result.value.rows for c in r.cells)
        )

    def test_object_lifecycle_uses_time_extrema_independent_of_input_order(self):
        log = join_log()
        log = replace(
            log, events=tuple(reversed(log.events)), e2o=tuple(reversed(log.e2o))
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("lifecycle_duration"),
                    ObjectFeature("first_activity"),
                    ObjectFeature("last_activity"),
                ),
                granularity="object",
            ),
        )
        row = next(r for r in result.value.rows if r.object_id == "order-1")
        self.assertEqual(
            tuple(map(value, row.cells)), (40 * MINUTE, ("arrive",), ("finish",))
        )

    def test_object_prefix_preserves_false_zero_empty_string_and_as_of_history(self):
        log = simple_log(
            (("event-a", "A", 0), ("event-b", "B", 10), ("event-c", "A", 20)),
            (("event-a", "o"), ("event-b", "o"), ("event-c", "o")),
        )
        declarations = (
            Attribute("flag", ValueType.BOOLEAN),
            Attribute("count", ValueType.INTEGER),
            Attribute("text", ValueType.STRING),
        )
        obj = Object(
            "o",
            "thing",
            (
                ObjectAttr("flag", False, at(0)),
                ObjectAttr("flag", True, at(15)),
                ObjectAttr("count", 0, at(0)),
                ObjectAttr("text", "", at(0)),
            ),
        )
        log = replace(
            log, object_types=(ObjectType("thing", declarations),), objects=(obj,)
        )
        features = (
            ObjectFeature("prefix_event_count"),
            ObjectFeature("object_attribute", attribute="flag"),
            ObjectFeature("object_attribute", attribute="count"),
            ObjectFeature("object_attribute", attribute="text"),
            ObjectFeature("previous_activity_count", activity="A"),
            ObjectFeature("last_activity"),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                features, granularity="event_object_prefix", as_of=at(10)
            ),
        )
        self.assertEqual(
            {r.event_id for r in result.value.rows}, {"event-a", "event-b"}
        )
        row = event_row(result, "event-b")
        self.assertEqual(tuple(map(value, row.cells)), (1, False, 0, "", 1, ("A",)))
        self.assertEqual(
            [c.kind for c in row.cells[1:4]], ["boolean", "integer", "text"]
        )
        unbounded = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("object_attribute", attribute="flag"),),
                granularity="object",
            ),
        )
        self.assertEqual(unbounded.value.rows[0].cells[0].reason, "as_of_required")
        bounded = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("object_attribute", attribute="flag"),),
                granularity="object",
                as_of=at(10),
            ),
        )
        self.assertIs(value(bounded.value.rows[0].cells[0]), False)

    def test_append_future_does_not_change_prefix_inputs(self):
        log = simple_log((("a", "A", 0), ("b", "B", 1)), (("a", "o"), ("b", "o")))
        future = replace(
            log,
            events=log.events + (Event("c", "A", at(20)),),
            e2o=log.e2o + (E2O("c", "o", "flow"),),
        )
        spec = ObjectFeatureSpec(
            (
                ObjectFeature("prefix_event_count"),
                ObjectFeature("previous_activity_count", activity="A"),
                ObjectFeature("elapsed_time"),
            ),
            granularity="event_object_prefix",
        )
        before, after = (
            extract_object_features(log, spec),
            extract_object_features(future, spec),
        )
        self.assertEqual(event_row(before, "b").cells, event_row(after, "b").cells)

    def test_future_join_cannot_merge_the_current_observed_prefix(self):
        past = simple_log((("a", "A", 0), ("b", "B", 5)), (("a", "oa"), ("b", "ob")))
        future = replace(
            past,
            events=past.events + (Event("join", "A", at(20)),),
            e2o=past.e2o + (E2O("join", "oa", "flow"), E2O("join", "ob", "flow")),
        )
        spec = ObjectFeatureSpec(
            (
                ObjectFeature("prefix_event_count"),
                ObjectFeature("previous_object_count"),
                ObjectFeature("previous_activity_count", activity="A"),
                ObjectFeature("elapsed_time"),
            )
        )
        before, after = (
            extract_object_features(past, spec),
            extract_object_features(future, spec),
        )
        self.assertEqual(tuple(map(value, event_row(before, "b").cells)), (0, 0, 0, 0))
        self.assertEqual(event_row(before, "b").cells, event_row(after, "b").cells)

    def test_relation_features_count_actual_shared_birth_death_and_handover(self):
        log = simple_log(
            (("a-start", "A", 0), ("handover", "H", 10), ("b-end", "B", 20)),
            (("a-start", "a"), ("handover", "a"), ("handover", "b"), ("b-end", "b")),
            (Object("a", "thing"), Object("b", "thing"), Object("isolated", "thing")),
        )
        features = tuple(
            ObjectFeature(name)
            for name in (
                "interaction_count",
                "degree_centrality",
                "descendant_count",
                "ascendant_count",
                "inheritance_out_count",
                "inheritance_in_count",
                "cobirth_count",
                "codeath_count",
            )
        )
        result = extract_object_features(
            log, ObjectFeatureSpec(features, granularity="object")
        )
        rows = {row.object_id: row for row in result.value.rows}
        self.assertEqual(tuple(map(value, rows["a"].cells)), (1, 0.5, 1, 0, 1, 0, 0, 0))
        self.assertEqual(tuple(map(value, rows["b"].cells)), (1, 0.5, 0, 1, 0, 1, 0, 0))
        self.assertEqual(value(rows["isolated"].cells[1]), 0)
        shared = simple_log(
            (("birth", "A", 0), ("death", "B", 10)),
            (("birth", "a"), ("birth", "b"), ("death", "a"), ("death", "b")),
        )
        result = extract_object_features(
            shared,
            ObjectFeatureSpec(
                (ObjectFeature("cobirth_count"), ObjectFeature("codeath_count")),
                granularity="object",
            ),
        )
        self.assertTrue(
            all(tuple(map(value, row.cells)) == (1, 1) for row in result.value.rows)
        )

    def test_activity_path_counts_are_frequencies_and_ties_are_unknown(self):
        log = simple_log(
            (("a1", "A", 0), ("b1", "B", 1), ("a2", "A", 2), ("b2", "B", 3)),
            (("a1", "o"), ("b1", "o"), ("a2", "o"), ("b2", "o")),
        )
        features = (
            ObjectFeature("activity_pair_count", activity="A", value="B"),
            ObjectFeature("activity_count", activity="A"),
            ObjectFeature("unique_activities"),
            ObjectFeature("lifecycle_start"),
            ObjectFeature("lifecycle_end"),
        )
        result = extract_object_features(
            log, ObjectFeatureSpec(features, granularity="object")
        )
        self.assertEqual(
            tuple(map(value, result.value.rows[0].cells)), (2, 2, 2, at(0), at(3))
        )
        tied = replace(
            log,
            events=log.events[:1]
            + (replace(log.events[1], time=at(0)),)
            + log.events[2:],
        )
        result = extract_object_features(
            tied, ObjectFeatureSpec(features, granularity="object")
        )
        self.assertEqual(result.value.rows[0].cells[0].reason, "ambiguous_event_order")

    def test_related_event_and_last_activity_attributes_use_declared_aggregation(self):
        features = (
            ObjectFeature(
                "related_event_attribute", attribute="amount", aggregation="sum"
            ),
            ObjectFeature(
                "last_activity_attribute",
                attribute="amount",
                activity="arrive",
                aggregation="maximum",
            ),
        )
        result = extract_object_features(
            join_log(), ObjectFeatureSpec(features, granularity="object", as_of=at(40))
        )
        rows = {row.object_id: row for row in result.value.rows}
        self.assertEqual(tuple(map(value, rows["order-1"].cells)), (26, 2))
        self.assertEqual(tuple(map(value, rows["item-1"].cells)), (12, 4))
        self.assertTrue(
            all(c.role == "input" for r in result.value.rows for c in r.cells)
        )

    def test_calendar_features_use_canonical_utc_instant(self):
        log = join_log()
        offset = timezone(timedelta(hours=9))
        shifted = replace(log.events[0], time=log.events[0].time.astimezone(offset))
        log = replace(log, events=(shifted,) + log.events[1:])
        features = tuple(
            ObjectFeature("calendar_" + name)
            for name in ("year", "month", "day", "weekday", "hour")
        )
        result = extract_object_features(log, ObjectFeatureSpec(features))
        self.assertEqual(
            tuple(map(value, event_row(result, "event-a").cells)), (2026, 9, 15, 1, 9)
        )

    def test_objects_born_separately_and_meeting_later_are_not_descendants(self):
        log = simple_log(
            (("a-born", "A", 0), ("b-born", "B", 1), ("later-meeting", "M", 10)),
            (
                ("a-born", "a"),
                ("b-born", "b"),
                ("later-meeting", "a"),
                ("later-meeting", "b"),
            ),
        )
        features = (
            ObjectFeature("descendant_count"),
            ObjectFeature("ascendant_count"),
            ObjectFeature("interaction_count"),
        )
        result = extract_object_features(
            log, ObjectFeatureSpec(features, granularity="object")
        )
        self.assertTrue(
            all(tuple(map(value, row.cells)) == (0, 0, 1) for row in result.value.rows)
        )

    def test_asof_centrality_population_uses_observed_objects_not_future_only_objects(
        self,
    ):
        log = simple_log(
            (("join", "J", 0), ("future", "F", 10)),
            (("join", "a"), ("join", "b"), ("future", "c")),
        )
        spec = ObjectFeatureSpec(
            (ObjectFeature("degree_centrality"),), granularity="object", as_of=at(1)
        )
        result = extract_object_features(log, spec)
        rows = {r.object_id: r for r in result.value.rows}
        self.assertEqual(value(rows["a"].cells[0]), 1)
        self.assertEqual(value(rows["b"].cells[0]), 1)
        # An attribute history establishes c's existence before any participation.
        known_c = Object("c", "thing", (ObjectAttr("known", True, at(0)),))
        observed = replace(
            log,
            object_types=(
                ObjectType("thing", (Attribute("known", ValueType.BOOLEAN),)),
            ),
            objects=tuple(known_c if o.id == "c" else o for o in log.objects),
        )
        result = extract_object_features(observed, spec)
        rows = {r.object_id: r for r in result.value.rows}
        self.assertEqual(value(rows["a"].cells[0]), 0.5)
        self.assertEqual(value(rows["b"].cells[0]), 0.5)
        self.assertEqual(value(rows["c"].cells[0]), 0)

    def test_singleton_cooccurrence_is_not_two_opposed_inheritances(self):
        log = simple_log((("only", "A", 0),), (("only", "a"), ("only", "b")))
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("inheritance_in_count"),
                    ObjectFeature("inheritance_out_count"),
                    ObjectFeature("cobirth_count"),
                    ObjectFeature("codeath_count"),
                ),
                granularity="object",
            ),
        )
        self.assertTrue(
            all(
                tuple(map(value, row.cells)) == (0, 0, 1, 1)
                for row in result.value.rows
            )
        )

    def test_attribute_aggregation_does_not_impute_missing_or_treat_bool_as_numeric(
        self,
    ):
        log = join_log()
        first = replace(
            log.events[0],
            attributes=tuple(a for a in log.events[0].attributes if a.name != "amount"),
        )
        log = replace(log, events=(first,) + log.events[1:])
        features = (
            ObjectFeature(
                "agg_previous_char_values", attribute="amount", aggregation="sum"
            ),
            ObjectFeature(
                "agg_previous_char_values", attribute="amount", aggregation="count"
            ),
        )
        result = extract_object_features(log, ObjectFeatureSpec(features))
        self.assertTrue(
            all(c.kind == "unknown" for c in event_row(result, "event-join").cells)
        )

    def test_empty_prefix_elapsed_time_is_unknown_not_observed_zero(self):
        result = extract_object_features(
            join_log(),
            ObjectFeatureSpec(
                (ObjectFeature("elapsed_time"),), granularity="event_object_prefix"
            ),
        )
        self.assertEqual(event_row(result, "event-a").cells[0].kind, "unknown")


class OCFeatureEncodingTests(unittest.TestCase):
    def tied_log(self):
        return simple_log(
            (("a", "A", 0), ("b", "B", 0), ("c", "C", 10)),
            (("a", "o"), ("b", "o"), ("c", "o")),
        )

    def test_tied_graph_is_unavailable_but_sequences_keep_timestamp_group(self):
        result = extract_object_features(
            self.tied_log(),
            ObjectFeatureSpec(
                (
                    ObjectFeature("number_of_objects"),
                    ObjectFeature("preceding_activities", activity="A"),
                ),
                prefix_policy="through_timestamp",
            ),
        )
        self.assertEqual(len(result.value.graphs), 1)
        graph = result.value.graphs[0]
        self.assertNotEqual(graph.order_status, "complete")
        self.assertEqual(graph.edges, ())
        self.assertTrue(
            all(r.cells[1].reason == "ambiguous_event_order" for r in result.value.rows)
        )
        sequence = encode_object_features(result)
        self.assertEqual(sorted(len(g.row_ids) for g in sequence.value.groups), [1, 2])
        self.assertEqual({g.timestamp for g in sequence.value.groups}, {at(0), at(10)})
        encoded_graph = encode_object_features(
            result, ObjectFeatureEncodingSpec("graph")
        )
        self.assertEqual(encoded_graph.value.graphs, result.value.graphs)

    def test_explicit_tie_breaking_changes_graph_not_timestamp_grouping(self):
        result = extract_object_features(
            self.tied_log(),
            ObjectFeatureSpec(
                (ObjectFeature("number_of_objects"),),
                execution=ExecutionSpec("connected_components", tie_policy="event_id"),
            ),
        )
        self.assertEqual(result.value.graphs[0].order_status, "complete")
        self.assertEqual(
            set(result.value.graphs[0].edges), {("a", "b", "o"), ("b", "c", "o")}
        )
        sequence = encode_object_features(result)
        self.assertEqual(sorted(len(g.row_ids) for g in sequence.value.groups), [1, 2])

    def test_time_windows_are_half_open_and_do_not_average_targets(self):
        result = extract_object_features(
            join_log(),
            ObjectFeatureSpec(
                (
                    ObjectFeature("characteristic_value", attribute="amount"),
                    ObjectFeature("remaining_time"),
                )
            ),
        )
        encoded = encode_object_features(
            result, ObjectFeatureEncodingSpec("time_window", 10 * MINUTE, at(0))
        )
        groups = {g.timestamp: g for g in encoded.value.groups}
        self.assertEqual(set(groups), {at(0), at(10), at(20), at(40)})
        for timestamp, expected in ((at(0), 2), (at(10), 4), (at(20), 8), (at(40), 16)):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(groups[timestamp].numeric_means, (expected, None))
                self.assertEqual(groups[timestamp].numeric_coverage, (1, 0))

    def test_window_before_origin_uses_floor_not_truncation(self):
        result = extract_object_features(
            join_log(), ObjectFeatureSpec((ObjectFeature("event_identity"),))
        )
        encoded = encode_object_features(
            result, ObjectFeatureEncodingSpec("time_window", 10 * MINUTE, at(5))
        )
        self.assertIn(at(-5), {g.timestamp for g in encoded.value.groups})

    def test_tabular_encoding_retains_one_group_per_row(self):
        result = extract_object_features(join_log())
        encoded = encode_object_features(result, ObjectFeatureEncodingSpec("tabular"))
        self.assertEqual(len(encoded.value.groups), 4)
        self.assertEqual(
            {g.row_ids[0] for g in encoded.value.groups},
            {r.row_id for r in result.value.rows},
        )
        self.assertTrue(all(len(g.row_ids) == 1 for g in encoded.value.groups))
        self.assertEqual(encoded.value.rows, result.value.rows)
        self.assertEqual(encoded.value.features, result.value.features)

    def test_default_one_hot_encoder_expands_training_categories_only(self):
        log = simple_log(
            (("a", "A", 0), ("b", "B", 1), ("c", "C", 2)),
            (("a", "o"), ("b", "o"), ("c", "o")),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("activity"), ObjectFeature("remaining_time"))
            ),
        )
        train = tuple(event_row(result, e).row_id for e in ("a", "b"))
        fitted = fit_object_feature_encoder(result, ObjectFeatureFitSpec(train))
        encoded = transform_object_features(result, fitted)
        self.assertEqual(
            encoded.value.columns, ((0, "text:A"), (0, "text:B"), (1, None))
        )
        rows = {r.row_id: r for r in encoded.value.rows}
        self.assertEqual(rows[event_row(result, "a").row_id].values, (1.0, 0.0, None))
        self.assertEqual(rows[event_row(result, "b").row_id].values, (0.0, 1.0, None))
        heldout = rows[event_row(result, "c").row_id]
        self.assertEqual(heldout.values, (None, None, None))
        self.assertEqual(
            heldout.reasons, ("unseen_category", "unseen_category", "target_excluded")
        )
        self.assertEqual(encoded.value.unknown_value_count, 2)

    def test_numeric_constant_training_column_does_not_divide_by_zero(self):
        result = extract_object_features(
            join_log(), ObjectFeatureSpec((ObjectFeature("event_identity"),))
        )
        fitted = fit_object_feature_encoder(
            result, ObjectFeatureFitSpec((result.value.rows[0].row_id,))
        )
        self.assertEqual(fitted.value.columns[0].scale, 0)
        encoded = transform_object_features(result, fitted)
        self.assertTrue(all(r.values == (0.0,) for r in encoded.value.rows))

    def test_train_statistics_exclude_heldout_extreme_category_and_targets(self):
        log = join_log()
        end = replace(
            log.events[-1],
            attributes=(
                EventAttr("start", at(30)),
                EventAttr("amount", 1_000_000),
                EventAttr("resource", "held-out-only"),
            ),
        )
        log = replace(log, events=log.events[:-1] + (end,))
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("characteristic_value", attribute="amount"),
                    ObjectFeature("characteristic_value", attribute="resource"),
                    ObjectFeature("remaining_time"),
                )
            ),
        )
        train_ids = tuple(
            event_row(result, event).row_id for event in ("event-a", "event-b")
        )
        fitted = fit_object_feature_encoder(
            result, ObjectFeatureFitSpec(train_ids, categorical_encoding="ordinal")
        )
        numeric, category, target = fitted.value.columns
        self.assertEqual(
            (numeric.mode, numeric.mean, numeric.scale, numeric.observed_train_count),
            ("numeric", 3, 1, 2),
        )
        self.assertEqual(category.categories, ("text:r",))
        self.assertEqual(target.mode, "target_excluded")
        transformed = transform_object_features(result, fitted)
        rows = {r.row_id: r for r in transformed.value.rows}
        self.assertEqual(
            rows[event_row(result, "event-a").row_id].values, (-1.0, 0.0, None)
        )
        self.assertEqual(
            rows[event_row(result, "event-b").row_id].values, (1.0, 0.0, None)
        )
        heldout = rows[event_row(result, "event-end").row_id]
        self.assertEqual(heldout.values, (999_997.0, None, None))
        self.assertEqual(heldout.reasons, (None, "unseen_category", "target_excluded"))
        self.assertEqual(transformed.value.unknown_value_count, 1)

    def test_unknown_training_and_transform_ids_are_invalid(self):
        result = extract_object_features(join_log())
        invalid = fit_object_feature_encoder(result, ObjectFeatureFitSpec(("missing",)))
        self.assertIs(invalid.status, ComputeStatus.INVALID_INPUT)
        fitted = fit_object_feature_encoder(
            result, ObjectFeatureFitSpec((result.value.rows[0].row_id,))
        )
        invalid = transform_object_features(
            result, fitted, ObjectFeatureTransformSpec(("missing",))
        )
        self.assertIs(invalid.status, ComputeStatus.INVALID_INPUT)

    def test_encoder_rejects_changed_feature_definition(self):
        first = extract_object_features(join_log())
        fitted = fit_object_feature_encoder(
            first, ObjectFeatureFitSpec((first.value.rows[0].row_id,))
        )
        second = extract_object_features(
            join_log(), ObjectFeatureSpec((ObjectFeature("event_identity"),))
        )
        result = transform_object_features(second, fitted)
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "encoder_feature_mismatch")


class OCFeatureAggregationTests(unittest.TestCase):
    def event_source(self, log):
        return extract_object_features(
            log,
            ObjectFeatureSpec(
                (
                    ObjectFeature("characteristic_value", attribute="amount"),
                    ObjectFeature("event_identity"),
                )
            ),
        )

    def object_target(self, log, as_of=None):
        return extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("number_of_events"),), granularity="object", as_of=as_of
            ),
        )

    def test_related_events_support_all_five_aggregations_without_duplicate_relations(
        self,
    ):
        log = join_log()
        log = replace(log, e2o=log.e2o + (E2O("event-join", "order-1", "second-role"),))
        source, target = self.event_source(log), self.object_target(log)
        cases = (
            ("minimum", 2, 4),
            ("maximum", 16, 8),
            ("sum", 26, 12),
            ("mean", 26 / 3, 6),
            ("count", 3, 2),
        )
        for operation, order_value, item_value in cases:
            with self.subTest(operation=operation):
                result = aggregate_object_features(
                    source,
                    target,
                    ObjectFeatureAggregationSpec(
                        "event_to_object", aggregation=operation, feature_indices=(0,)
                    ),
                )
                self.assertIs(result.status, ComputeStatus.COMPUTED)
                self.assertEqual(result.value.features, source.value.features[:1])
                rows = {r.object_id: r for r in result.value.rows}
                self.assertEqual(value(rows["order-1"].cells[0]), order_value)
                self.assertEqual(value(rows["item-1"].cells[0]), item_value)
                self.assertEqual(
                    {r.row_id for r in result.value.rows},
                    {r.row_id for r in target.value.rows},
                )

    def test_last_event_and_last_occurrence_of_selected_activity_are_distinct(self):
        log = join_log()
        repeated = Event(
            "arrive-again",
            "arrive",
            at(35),
            (
                EventAttr("start", at(34)),
                EventAttr("amount", 12),
                EventAttr("resource", "r"),
            ),
        )
        log = replace(
            log,
            events=log.events + (repeated,),
            e2o=log.e2o + (E2O("arrive-again", "order-1", "flow"),),
        )
        source, target = self.event_source(log), self.object_target(log)
        last = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec(
                "event_to_object",
                aggregation="maximum",
                feature_indices=(0,),
                last_source_time_only=True,
            ),
        )
        last_arrival = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec(
                "event_to_object",
                aggregation="maximum",
                feature_indices=(0,),
                source_activity="arrive",
                last_source_time_only=True,
            ),
        )
        rows = {r.object_id: r for r in last.value.rows}
        filtered = {r.object_id: r for r in last_arrival.value.rows}
        self.assertEqual(value(rows["order-1"].cells[0]), 16)
        self.assertEqual(value(filtered["order-1"].cells[0]), 12)
        self.assertEqual(value(filtered["item-1"].cells[0]), 4)

    def test_related_object_full_log_summary_is_target_at_past_event(self):
        log = join_log()
        source = self.object_target(log)
        target = extract_object_features(log)
        result = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec("object_to_event", aggregation="minimum"),
        )
        self.assertEqual(value(event_row(result, "event-join").cells[0]), 2)
        self.assertEqual(value(event_row(result, "event-a").cells[0]), 3)
        self.assertTrue(all(r.cells[0].role == "target" for r in result.value.rows))
        fitted = fit_object_feature_encoder(
            result, ObjectFeatureFitSpec((event_row(result, "event-a").row_id,))
        )
        self.assertEqual(fitted.value.columns[0].mode, "target_excluded")

    def test_later_asof_input_summary_is_promoted_to_target_when_attached_to_past(self):
        log = join_log()
        source = self.object_target(log, as_of=at(40))
        self.assertTrue(all(r.cells[0].role == "input" for r in source.value.rows))
        target = extract_object_features(log)
        result = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec("object_to_event", aggregation="maximum"),
        )
        self.assertEqual(value(event_row(result, "event-a").cells[0]), 3)
        self.assertEqual(event_row(result, "event-a").cells[0].role, "target")
        self.assertEqual(event_row(result, "event-end").cells[0].role, "input")

    def test_interaction_neighbors_exclude_self_and_count_unique_objects(self):
        log = join_log()
        source = self.object_target(log, as_of=at(40))
        target = self.object_target(log, as_of=at(40))
        result = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec("object_interaction", aggregation="sum"),
        )
        rows = {r.object_id: r for r in result.value.rows}
        self.assertEqual(value(rows["order-1"].cells[0]), 2)
        self.assertEqual(value(rows["item-1"].cells[0]), 3)
        self.assertTrue(all(r.cells[0].role == "input" for r in rows.values()))

    def test_unknown_related_observation_remains_unknown(self):
        log = join_log()
        missing = replace(
            log.events[0],
            attributes=tuple(a for a in log.events[0].attributes if a.name != "amount"),
        )
        log = replace(log, events=(missing,) + log.events[1:])
        result = aggregate_object_features(
            self.event_source(log),
            self.object_target(log),
            ObjectFeatureAggregationSpec(
                "event_to_object", aggregation="sum", feature_indices=(0,)
            ),
        )
        rows = {r.object_id: r for r in result.value.rows}
        self.assertEqual(rows["order-1"].cells[0].reason, "source_feature_unknown")
        self.assertEqual(value(rows["item-1"].cells[0]), 12)
        self.assertIs(result.status, ComputeStatus.PARTIAL)

    def test_source_digest_granularity_and_feature_index_mismatches_are_invalid(self):
        log = join_log()
        source, target = self.event_source(log), self.object_target(log)
        changed = replace(
            log, events=log.events[:-1] + (replace(log.events[-1], time=at(41)),)
        )
        cases = (
            (
                source,
                self.object_target(changed),
                ObjectFeatureAggregationSpec("event_to_object"),
                "feature_source_mismatch",
            ),
            (
                source,
                source,
                ObjectFeatureAggregationSpec("event_to_object"),
                "feature_granularity_mismatch",
            ),
            (
                source,
                target,
                ObjectFeatureAggregationSpec("event_to_object", feature_indices=(99,)),
                "unknown_feature_index",
            ),
        )
        for left, right, spec, code in cases:
            with self.subTest(code=code):
                result = aggregate_object_features(left, right, spec)
                self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
                self.assertEqual(result.issues[0].code, code)

    def test_unique_entity_rejects_conflicting_shared_execution_values(self):
        log = simple_log(
            (
                ("o1-start", "Receive", 0),
                ("o2-start", "Receive", 1),
                ("pack1", "Pack", 2),
                ("pack2", "Pack", 3),
                ("ship", "Ship", 4),
                ("finish", "Finish", 5),
            ),
            (
                ("o1-start", "o1"),
                ("o2-start", "o2"),
                ("pack1", "o1"),
                ("pack1", "i1"),
                ("pack2", "o2"),
                ("pack2", "i2"),
                ("ship", "i1"),
                ("ship", "i2"),
                ("ship", "s"),
                ("finish", "s"),
            ),
            (
                Object("o1", "order"),
                Object("o2", "order"),
                Object("i1", "item"),
                Object("i2", "item"),
                Object("s", "shipment"),
            ),
        )
        extraction = ExecutionSpec(
            "leading_object_nearest_type", leading_object_type="order"
        )
        source = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("execution_duration"), ObjectFeature("event_identity")),
                execution=extraction,
            ),
        )
        target = self.object_target(log)
        unique = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec("event_to_object", aggregation="sum"),
        )
        row = next(r for r in unique.value.rows if r.object_id == "s")
        self.assertEqual(row.cells[0].reason, "conflicting_execution_membership_values")
        self.assertEqual(value(row.cells[1]), 2)
        membership = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec(
                "event_to_object", aggregation="sum", weighting="membership"
            ),
        )
        row = next(r for r in membership.value.rows if r.object_id == "s")
        self.assertEqual(tuple(map(value, row.cells)), (18 * MINUTE, 4))

    def test_aggregated_table_composes_and_remains_encodable(self):
        log = join_log()
        source, target = self.event_source(log), self.object_target(log)
        first = aggregate_object_features(
            source,
            target,
            ObjectFeatureAggregationSpec(
                "event_to_object", aggregation="sum", feature_indices=(0,)
            ),
        )
        second = aggregate_object_features(
            first,
            extract_object_features(log),
            ObjectFeatureAggregationSpec("object_to_event", aggregation="minimum"),
        )
        self.assertEqual(value(event_row(second, "event-join").cells[0]), 12)
        self.assertEqual(event_row(second, "event-join").cells[0].role, "target")
        encoded = encode_object_features(second, ObjectFeatureEncodingSpec("tabular"))
        self.assertEqual(encoded.value.rows, second.value.rows)
        self.assertEqual(len(encoded.value.groups), 4)

    def test_encoder_cannot_reuse_minimum_definition_for_maximum_sum_or_mean(self):
        log = join_log()
        source, target = self.event_source(log), self.object_target(log, as_of=at(40))
        aggregates = {
            operation: aggregate_object_features(
                source,
                target,
                ObjectFeatureAggregationSpec(
                    "event_to_object", aggregation=operation, feature_indices=(0,)
                ),
            )
            for operation in ("minimum", "maximum", "sum", "mean")
        }
        self.assertEqual(len({r.value.definition_id for r in aggregates.values()}), 4)
        minimum = aggregates["minimum"]
        fitted = fit_object_feature_encoder(
            minimum, ObjectFeatureFitSpec(tuple(r.row_id for r in minimum.value.rows))
        )
        self.assertEqual(fitted.value.definition_id, minimum.value.definition_id)
        self.assertIs(
            transform_object_features(minimum, fitted).status, ComputeStatus.COMPUTED
        )
        for operation in ("maximum", "sum", "mean"):
            with self.subTest(operation=operation):
                transformed = transform_object_features(aggregates[operation], fitted)
                self.assertIs(transformed.status, ComputeStatus.INVALID_INPUT)
                self.assertEqual(transformed.issues[0].code, "encoder_feature_mismatch")


class OCFeaturePartitionTests(unittest.TestCase):
    def test_independent_components_split_reproducibly_without_entity_overlap(self):
        log = simple_log(
            (("a1", "A", 0), ("a2", "B", 1), ("b1", "A", 2), ("b2", "B", 3)),
            (("a1", "a"), ("a2", "a"), ("b1", "b"), ("b2", "b")),
        )
        result = extract_object_features(log)
        spec = ObjectFeatureSplitSpec(train_fraction=0.5, seed="test")
        split = split_object_features(result, spec)
        repeated = split_object_features(result, spec)
        self.assertEqual(split, repeated)
        self.assertIs(split.status, ComputeStatus.COMPUTED)
        self.assertEqual(split.value.independent_group_count, 2)
        self.assertEqual(
            (len(split.value.train_row_ids), len(split.value.test_row_ids)), (2, 2)
        )
        self.assertEqual(split.value.shared_event_ids, ())
        self.assertEqual(split.value.shared_object_ids, ())
        self.assertFalse(
            set(split.value.train_execution_ids) & set(split.value.test_execution_ids)
        )

    def test_shared_leading_executions_cannot_be_claimed_independent(self):
        log = simple_log(
            (("a", "A", 0), ("b", "B", 1)),
            (("a", "o1"), ("a", "shared"), ("b", "o2"), ("b", "shared")),
            (Object("o1", "order"), Object("o2", "order"), Object("shared", "item")),
        )
        result = extract_object_features(
            log,
            ObjectFeatureSpec(
                (ObjectFeature("event_identity"),),
                execution=ExecutionSpec(
                    "leading_object_nearest_type", leading_object_type="order"
                ),
            ),
        )
        self.assertEqual(len(result.value.graphs), 2)
        safe = split_object_features(result, ObjectFeatureSplitSpec(train_fraction=0.5))
        self.assertEqual(safe.value.independent_group_count, 1)
        self.assertEqual(safe.value.test_row_ids, ())
        self.assertIn("insufficient_independent_groups", {i.code for i in safe.issues})
        unsafe = split_object_features(
            result,
            ObjectFeatureSplitSpec(train_fraction=0.5, group_shared_entities=False),
        )
        self.assertEqual(unsafe.value.independent_group_count, 2)
        self.assertIn("shared", unsafe.value.shared_object_ids)
        self.assertIn("partition_entity_leakage", {i.code for i in unsafe.issues})
        self.assertIs(unsafe.status, ComputeStatus.PARTIAL)

    def test_object_rows_also_group_by_shared_event_membership(self):
        result = extract_object_features(
            join_log(),
            ObjectFeatureSpec(
                (ObjectFeature("number_of_events"),), granularity="object", as_of=at(40)
            ),
        )
        split = split_object_features(
            result, ObjectFeatureSplitSpec(train_fraction=0.5)
        )
        self.assertEqual(split.value.independent_group_count, 1)
        self.assertEqual(split.value.test_row_ids, ())

    def test_empty_table_does_not_invent_a_split_fraction(self):
        log = OCEL()
        result = extract_object_features(log)
        split = split_object_features(result)
        self.assertEqual(split.value.independent_group_count, 0)
        self.assertIsNone(split.value.actual_train_fraction)
        self.assertEqual(split.value.train_row_ids, ())
        self.assertEqual(split.value.test_row_ids, ())


if __name__ == "__main__":
    unittest.main()
