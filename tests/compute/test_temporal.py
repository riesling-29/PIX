"""Hand-counted observed durations, weighting, and incomplete-service evidence."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.compute.temporal import measure_temporal
from pix.contracts.analysis import TemporalSpec
from pix.contracts.result import ComputeStatus
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectType,
    ValueType,
)

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def weighted_log() -> OCEL:
    """Two objects share a ten-second pair; one sees a twenty-second pair."""
    return OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("order"), ObjectType("unused")),
        events=(
            Event("a1", "A", ORIGIN),
            Event("b1", "B", ORIGIN + timedelta(seconds=10)),
            Event("a2", "A", ORIGIN + timedelta(seconds=30)),
            Event("b2", "B", ORIGIN + timedelta(seconds=50)),
        ),
        objects=tuple(Object(name, "order") for name in ("o1", "o2", "o3")),
        e2o=(
            E2O("a1", "o1", "flow"),
            E2O("a1", "o1", "audit"),
            E2O("b1", "o1", "flow"),
            E2O("a1", "o2", "flow"),
            E2O("b1", "o2", "flow"),
            E2O("a2", "o3", "flow"),
            E2O("b2", "o3", "flow"),
        ),
    )


def service_log() -> OCEL:
    """Start times are valid, absent, wrongly typed, and after completion."""
    return OCEL(
        event_types=(
            EventType("valid", (Attribute("start", ValueType.TIME),)),
            EventType("missing", (Attribute("start", ValueType.TIME),)),
            EventType("text", (Attribute("start", ValueType.STRING),)),
            EventType("negative", (Attribute("start", ValueType.TIME),)),
        ),
        object_types=(ObjectType("order"),),
        events=(
            Event(
                "e1",
                "valid",
                ORIGIN,
                (EventAttr("start", ORIGIN - timedelta(microseconds=250001)),),
            ),
            Event("e2", "missing", ORIGIN + timedelta(seconds=1)),
            Event(
                "e3",
                "text",
                ORIGIN + timedelta(seconds=2),
                (EventAttr("start", "2026-01-01T00:00:00Z"),),
            ),
            Event(
                "e4",
                "negative",
                ORIGIN + timedelta(seconds=3),
                (EventAttr("start", ORIGIN + timedelta(seconds=4)),),
            ),
        ),
        objects=(Object("o1", "order"),),
        e2o=tuple(E2O(f"e{index}", "o1", "flow") for index in range(1, 5)),
    )


class TemporalMeasurementTests(unittest.TestCase):
    def test_shared_pairs_and_object_occurrences_have_different_denominators(self):
        pair_result = measure_temporal(
            weighted_log(), TemporalSpec("order", weighting="event_pairs")
        )
        occurrence_result = measure_temporal(
            weighted_log(), TemporalSpec("order", weighting="occurrences")
        )
        self.assertIs(pair_result.status, ComputeStatus.COMPUTED)
        self.assertIs(occurrence_result.status, ComputeStatus.COMPUTED)
        pair = pair_result.value.gaps[0].duration
        occurrence = occurrence_result.value.gaps[0].duration
        self.assertEqual((pair.population_count, pair.sample_count), (2, 2))
        self.assertEqual(
            (pair.total_microseconds, pair.unavailable_count), (30_000_000, 0)
        )
        self.assertEqual((pair.mean_numerator, pair.mean_denominator), (30_000_000, 2))
        self.assertEqual((occurrence.population_count, occurrence.sample_count), (3, 3))
        self.assertEqual(occurrence.total_microseconds, 40_000_000)
        self.assertEqual(
            (occurrence.mean_numerator, occurrence.mean_denominator), (40_000_000, 3)
        )
        self.assertEqual(
            (pair.minimum_microseconds, pair.maximum_microseconds),
            (10_000_000, 20_000_000),
        )
        self.assertNotEqual(
            pair_result.computation_id, occurrence_result.computation_id
        )

    def test_shared_pair_retains_both_objects_without_counting_qualifiers_twice(self):
        result = measure_temporal(weighted_log(), TemporalSpec("order"))
        edge = result.value.gaps[0]
        self.assertEqual((edge.source_activity, edge.target_activity), ("A", "B"))
        sample = next(
            item for item in edge.duration.samples if item.source_event_id == "a1"
        )
        self.assertEqual(sample.target_event_id, "b1")
        self.assertEqual(sample.object_ids, ("o1", "o2"))
        self.assertEqual(sample.duration_microseconds, 10_000_000)
        self.assertEqual(len(sample.evidence), 2)

    def test_no_start_attribute_reports_unknown_service_instead_of_zero(self):
        result = measure_temporal(weighted_log(), TemporalSpec("order"))
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.service_status, "unavailable")
        service = result.value.service
        self.assertEqual(
            (service.population_count, service.sample_count, service.unavailable_count),
            (4, 0, 4),
        )
        self.assertEqual(service.samples, ())
        self.assertIsNone(service.minimum_microseconds)
        self.assertIsNone(service.maximum_microseconds)
        self.assertIsNone(service.mean_numerator)
        self.assertIsNone(service.mean_denominator)
        self.assertTrue(result.value.service_issues)

    def test_partial_service_retains_valid_sample_and_reports_excluded_population(self):
        result = measure_temporal(
            service_log(), TemporalSpec("order", start_attribute="start")
        )
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertTrue(result.issues)
        self.assertEqual(result.value.service_status, "unavailable")
        service = result.value.service
        self.assertEqual(
            (service.population_count, service.sample_count, service.unavailable_count),
            (4, 1, 3),
        )
        self.assertEqual(service.total_microseconds, 250001)
        self.assertEqual(
            (service.mean_numerator, service.mean_denominator), (250001, 1)
        )
        self.assertEqual([sample.target_event_id for sample in service.samples], ["e1"])
        self.assertEqual(service.samples[0].source_event_id, None)
        self.assertEqual(service.samples[0].object_ids, ("o1",))
        self.assertEqual(len(result.value.gaps), 3)
        self.assertEqual(
            {(issue.code, issue.at[1]) for issue in result.value.service_issues},
            {
                ("missing_service_start", "e2"),
                ("invalid_service_start", "e3"),
                ("negative_service_duration", "e4"),
            },
        )

    def test_zero_service_is_observed_only_when_start_equals_completion(self):
        base = service_log()
        event = replace(base.events[0], attributes=(EventAttr("start", ORIGIN),))
        log = replace(base, events=(event,), e2o=(E2O("e1", "o1", "flow"),))
        result = measure_temporal(log, TemporalSpec("order", start_attribute="start"))
        self.assertEqual(result.value.service_status, "computed")
        self.assertEqual(result.value.service.sample_count, 1)
        self.assertEqual(result.value.service.unavailable_count, 0)
        self.assertEqual(result.value.service.minimum_microseconds, 0)
        self.assertEqual(result.value.service.maximum_microseconds, 0)

    def test_service_uses_instants_across_different_recorded_timezone_offsets(self):
        base = service_log()
        completed = datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9)))
        started = datetime(2025, 12, 31, 23, 59, tzinfo=timezone.utc)
        event = replace(
            base.events[0], time=completed, attributes=(EventAttr("start", started),)
        )
        log = replace(base, events=(event,), e2o=(E2O("e1", "o1", "flow"),))
        result = measure_temporal(log, TemporalSpec("order", start_attribute="start"))
        self.assertEqual(result.value.service_status, "computed")
        self.assertEqual(result.value.service.total_microseconds, 60_000_000)
        self.assertEqual(result.value.service.samples[0].target_event_id, "e1")

    def test_service_population_is_unique_events_under_either_gap_weighting(self):
        base = weighted_log()
        log = replace(
            base,
            event_types=tuple(
                EventType(name, (Attribute("start", ValueType.TIME),))
                for name in ("A", "B")
            ),
            events=tuple(
                replace(
                    event,
                    attributes=(EventAttr("start", event.time - timedelta(seconds=1)),),
                )
                for event in base.events
            ),
        )
        for weighting in ("event_pairs", "occurrences"):
            with self.subTest(weighting=weighting):
                result = measure_temporal(
                    log,
                    TemporalSpec("order", weighting=weighting, start_attribute="start"),
                )
                self.assertEqual(result.value.service_status, "computed")
                self.assertEqual(result.value.service.sample_count, 4)
                self.assertEqual(result.value.service.total_microseconds, 4_000_000)

    def test_qualifier_selection_changes_adjacency_and_service_population(self):
        log = OCEL(
            event_types=tuple(EventType(name) for name in ("A", "B", "C")),
            object_types=(ObjectType("order"),),
            events=(
                Event("e1", "A", ORIGIN),
                Event("e2", "B", ORIGIN + timedelta(seconds=10)),
                Event("e3", "C", ORIGIN + timedelta(seconds=30)),
            ),
            objects=(Object("o1", "order"),),
            e2o=(
                E2O("e1", "o1", "flow"),
                E2O("e2", "o1", "audit"),
                E2O("e3", "o1", "flow"),
            ),
        )
        result = measure_temporal(log, TemporalSpec("order", qualifiers=("flow",)))
        self.assertEqual(len(result.value.gaps), 1)
        edge = result.value.gaps[0]
        self.assertEqual((edge.source_activity, edge.target_activity), ("A", "C"))
        self.assertEqual(edge.duration.total_microseconds, 30_000_000)
        self.assertEqual(result.value.service.population_count, 2)

    def test_empty_declared_type_is_distinct_from_unknown_type(self):
        empty = measure_temporal(weighted_log(), TemporalSpec("unused"))
        unknown = measure_temporal(weighted_log(), TemporalSpec("absent"))
        self.assertIs(empty.status, ComputeStatus.COMPUTED)
        self.assertEqual(empty.value.gaps, ())
        self.assertEqual(empty.value.service.population_count, 0)
        self.assertEqual(empty.value.service.sample_count, 0)
        self.assertEqual(empty.value.service.unavailable_count, 0)
        self.assertEqual(empty.value.service.total_microseconds, 0)
        self.assertIsNone(empty.value.service.mean_numerator)
        self.assertIsNone(empty.value.service.mean_denominator)
        self.assertEqual(empty.value.service_status, "unavailable")
        self.assertIs(unknown.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(unknown.value)

    def test_empty_qualifier_filter_has_no_events_or_durations(self):
        result = measure_temporal(weighted_log(), TemporalSpec("order", qualifiers=()))
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.gaps, ())
        self.assertEqual(result.value.service.population_count, 0)

    def test_ambiguous_order_requires_explicit_policy_even_for_zero_gap(self):
        base = weighted_log()
        log = replace(
            base, events=tuple(replace(event, time=ORIGIN) for event in base.events)
        )
        rejected = measure_temporal(log, TemporalSpec("order"))
        accepted = measure_temporal(log, TemporalSpec("order", tie_policy="event_id"))
        self.assertIs(rejected.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(rejected.value)
        self.assertIs(accepted.status, ComputeStatus.COMPUTED)
        self.assertTrue(accepted.value.gaps)
        self.assertTrue(
            all(edge.duration.maximum_microseconds == 0 for edge in accepted.value.gaps)
        )

    def test_year_scale_microseconds_do_not_round_through_float_seconds(self):
        start = datetime(1, 1, 1, tzinfo=timezone.utc)
        finish = datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)
        base = weighted_log()
        log = replace(
            base,
            events=(Event("a1", "A", start), Event("b1", "B", finish)),
            objects=(Object("o1", "order"),),
            e2o=(E2O("a1", "o1", "flow"), E2O("b1", "o1", "flow")),
        )
        result = measure_temporal(log, TemporalSpec("order"))
        # Gregorian ordinal arithmetic gives 3,652,059 days minus one microsecond.
        self.assertEqual(
            result.value.gaps[0].duration.total_microseconds, 315_537_897_599_999_999
        )
        self.assertIsInstance(result.value.gaps[0].duration.total_microseconds, int)

    def test_input_collection_order_does_not_change_temporal_result(self):
        log = weighted_log()
        reversed_log = replace(
            log,
            events=tuple(reversed(log.events)),
            objects=tuple(reversed(log.objects)),
            e2o=tuple(reversed(log.e2o)),
        )
        original = measure_temporal(log, TemporalSpec("order"))
        reordered = measure_temporal(reversed_log, TemporalSpec("order"))
        self.assertEqual(original.value, reordered.value)
        self.assertEqual(original.source_digest, reordered.source_digest)
        self.assertEqual(original.computation_id, reordered.computation_id)

    def test_invalid_log_is_reported_without_partial_numeric_result(self):
        log = weighted_log()
        invalid = replace(log, e2o=log.e2o + (E2O("missing", "o1", "flow"),))
        result = measure_temporal(invalid, TemporalSpec("order"))
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(result.value)
        self.assertTrue(result.issues)


if __name__ == "__main__":
    unittest.main()
