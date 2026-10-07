"""Hand-counted temporal populations and representation invariance."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from pix.compute.context import ComputationContext
from pix.contracts.result import ComputeStatus
from pix.object_centric.temporal_summary import TemporalSummarySpec, temporal_summary
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType
from pix.results import result_from_json, result_json_bytes

T = datetime(2026, 9, 15, 9, 0, 0, 123456, tzinfo=timezone.utc)


def fixture():
    return OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("item"), ObjectType("order"), ObjectType("empty")),
        events=(
            Event("e1", "A", T),
            Event("e2", "A", T),
            Event("e3", "B", T),
            Event("e4", "B", T + timedelta(microseconds=1)),
        ),
        objects=(Object("o", "order"), Object("i", "item"), Object("isolated", "item")),
        e2o=(
            E2O("e1", "o", "input"),
            E2O("e1", "o", "output"),
            E2O("e1", "i", "input"),
            E2O("e2", "o", ""),
            E2O("e4", "o", "output"),
        ),
    )


class TemporalSummaryTests(unittest.TestCase):
    def test_hand_counted_simultaneous_populations_do_not_inflate(self):
        result = temporal_summary(fixture())
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        summary = result.value
        self.assertEqual(
            (
                summary.source_event_count,
                summary.selected_event_count,
                summary.participating_event_count,
                summary.object_count,
                summary.participation_count,
                summary.e2o_relation_count,
            ),
            (4, 4, 3, 2, 4, 5),
        )
        group = summary.buckets[0]
        self.assertEqual(group.event_ids, ("e1", "e2", "e3"))
        self.assertEqual(group.event_count, 3)
        self.assertEqual(group.activities, ("A", "B"))
        self.assertEqual(group.activity_counts, (("A", 2), ("B", 1)))
        self.assertEqual(group.object_ids, ("i", "o"))
        self.assertEqual(group.object_type_counts, (("item", 1), ("order", 1)))
        self.assertEqual(
            (group.object_count, group.participation_count, group.e2o_relation_count),
            (2, 3, 4),
        )
        self.assertEqual(
            group.qualifier_relation_counts, (("", 1), ("input", 2), ("output", 1))
        )
        self.assertEqual(group.relation_activity_counts, (("A", 4),))
        self.assertEqual(group.events_without_selected_relations, ("e3",))
        pair = next(
            p for p in group.participations if p.event_id == "e1" and p.object_id == "o"
        )
        self.assertEqual(pair.qualifiers, ("input", "output"))

    def test_same_object_reappears_without_becoming_distinct_object(self):
        result = temporal_summary(fixture()).value
        self.assertEqual(result.object_count, 2)
        self.assertEqual(sum(group.object_count for group in result.buckets), 3)
        self.assertEqual(result.buckets[1].object_ids, ("o",))

    def test_exact_microseconds_are_separate_buckets(self):
        groups = temporal_summary(fixture()).value.buckets
        self.assertEqual(
            tuple(g.time for g in groups), (T, T + timedelta(microseconds=1))
        )
        self.assertEqual(tuple(g.event_count for g in groups), (3, 1))

    def test_reference_population_retains_relation_weighted_activity_count(self):
        result = temporal_summary(
            fixture(),
            TemporalSummarySpec(event_population="selected_participating_events"),
        )
        self.assertEqual(result.value.selected_event_count, 3)
        group = result.value.buckets[0]
        self.assertEqual(group.event_ids, ("e1", "e2"))
        self.assertEqual(group.activity_counts, (("A", 2),))
        self.assertEqual(group.relation_activity_counts, (("A", 4),))
        self.assertEqual(group.events_without_selected_relations, ())

    def test_qualifier_selection_does_not_change_distinct_event_population(self):
        result = temporal_summary(
            fixture(), TemporalSummarySpec(qualifiers=("input",))
        ).value
        self.assertEqual(
            (
                result.selected_event_count,
                result.participating_event_count,
                result.participation_count,
                result.e2o_relation_count,
            ),
            (4, 1, 2, 2),
        )
        self.assertEqual(result.buckets[0].activity_counts, (("A", 2), ("B", 1)))
        self.assertEqual(
            result.buckets[0].events_without_selected_relations, ("e2", "e3")
        )

    def test_empty_qualifier_and_empty_selection_have_distinct_meanings(self):
        empty_role = temporal_summary(
            fixture(), TemporalSummarySpec(qualifiers=("",))
        ).value
        self.assertEqual(
            (empty_role.participation_count, empty_role.e2o_relation_count), (1, 1)
        )
        none = temporal_summary(fixture(), TemporalSummarySpec(qualifiers=())).value
        self.assertEqual(
            (none.selected_event_count, none.object_count, none.participation_count),
            (4, 0, 0),
        )
        participating = temporal_summary(
            fixture(),
            TemporalSummarySpec(
                qualifiers=(), event_population="selected_participating_events"
            ),
        ).value
        self.assertEqual(
            (participating.selected_event_count, participating.buckets), (0, ())
        )

    def test_activity_and_type_selections_are_independent(self):
        value = temporal_summary(
            fixture(), TemporalSummarySpec(activities=("A",), object_types=("order",))
        ).value
        self.assertEqual(
            (
                value.selected_event_count,
                value.object_count,
                value.participation_count,
                value.e2o_relation_count,
            ),
            (2, 1, 2, 3),
        )
        self.assertEqual(value.buckets[0].relation_activity_counts, (("A", 3),))
        empty_type = temporal_summary(
            fixture(), TemporalSummarySpec(object_types=("empty",))
        ).value
        self.assertEqual(
            (empty_type.selected_event_count, empty_type.object_count), (4, 0)
        )

    def test_empty_log_and_activity_population(self):
        for log, spec in (
            (OCEL(), TemporalSummarySpec()),
            (fixture(), TemporalSummarySpec(activities=())),
            (fixture(), TemporalSummarySpec(activities=("unobserved",))),
        ):
            with self.subTest(spec=spec):
                result = temporal_summary(log, spec)
                self.assertIs(result.status, ComputeStatus.COMPUTED)
                self.assertEqual(result.value.buckets, ())
                self.assertEqual(result.value.selected_event_count, 0)

    def test_permutation_and_reusable_context_have_identical_identity_and_payload(self):
        log = fixture()
        result = temporal_summary(log)
        reordered = replace(
            log, events=log.events[::-1], objects=log.objects[::-1], e2o=log.e2o[::-1]
        )
        self.assertEqual(result, temporal_summary(reordered))
        self.assertEqual(result, temporal_summary(ComputationContext(log)))

    def test_equivalent_timezone_instants_are_grouped_without_float_conversion(self):
        log = fixture()
        local = timezone(timedelta(hours=9))
        equivalent = replace(
            log,
            events=tuple(replace(e, time=e.time.astimezone(local)) for e in log.events),
        )
        self.assertEqual(temporal_summary(log), temporal_summary(equivalent))
        mixed = replace(
            log,
            events=tuple(
                replace(e, time=e.time.astimezone(local)) if e.id == "e1" else e
                for e in log.events
            ),
        )
        self.assertEqual(temporal_summary(log), temporal_summary(mixed))

    def test_spec_normalization_and_immutable_contracts(self):
        first = TemporalSummarySpec(
            activities=("B", "A", "A"), qualifiers=("output", "input", "input")
        )
        second = TemporalSummarySpec(
            activities=("A", "B"), qualifiers=("input", "output")
        )
        self.assertEqual(
            temporal_summary(fixture(), first), temporal_summary(fixture(), second)
        )
        with self.assertRaises(FrozenInstanceError):
            first.event_population = "selected_participating_events"
        with self.assertRaises(FrozenInstanceError):
            temporal_summary(fixture()).value.buckets[0].event_count = 99

    def test_registered_result_codec_preserves_timestamp_and_participation_evidence(
        self,
    ):
        result = temporal_summary(fixture())
        encoded = result_json_bytes(result)
        restored = result_from_json(encoded)
        self.assertEqual(restored, result)
        self.assertEqual(result_json_bytes(restored), encoded)
        self.assertIsInstance(restored.value.buckets[0].time, datetime)
        self.assertEqual(restored.value.buckets[0].time, T)
        self.assertEqual(
            restored.value.buckets[0].participations,
            result.value.buckets[0].participations,
        )

    def test_duplicate_exact_relation_is_invalid_not_an_extra_occurrence(self):
        log = fixture()
        duplicated = replace(log, e2o=log.e2o + (log.e2o[0],))
        result = temporal_summary(duplicated)
        self.assertIs(result.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(result.value)

    def test_bad_request_and_invalid_log_are_explicit(self):
        for kwargs in (
            {"activities": ["A"]},
            {"object_types": (1,)},
            {"qualifiers": "input"},
            {"event_population": "ordered"},
        ):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises((TypeError, ValueError)),
            ):
                TemporalSummarySpec(**kwargs)
        with self.assertRaises(TypeError):
            temporal_summary(fixture(), object())
        self.assertIs(temporal_summary(object()).status, ComputeStatus.INVALID_INPUT)
        result = temporal_summary(
            fixture(), TemporalSummarySpec(object_types=("missing",))
        )
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(result.issues[0].code, "unknown_object_type")


if __name__ == "__main__":
    unittest.main()
