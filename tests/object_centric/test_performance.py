"""Independent clock arithmetic and counterexamples for OC performance profiles."""

import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.compute.context import ComputationContext
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.conformance import ObjectReplaySpec, replay_object_log
from pix.object_centric.performance import (
    OCPerformanceSpec,
    OCReplayPerformanceSpec,
    measure_performance,
    measure_replay_performance,
)
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

BASE = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
MINUTE = 60_000_000


def fixture(first=0, second=10, start=15, *, start_type=ValueType.TIME):
    attrs = (
        ()
        if start is None
        else (
            EventAttr(
                "start",
                BASE + timedelta(minutes=start)
                if start_type == ValueType.TIME
                else str(start),
            ),
        )
    )
    return OCEL(
        event_types=(
            EventType("arrive"),
            EventType("join", (Attribute("start", start_type),)),
            EventType("finish"),
        ),
        object_types=(ObjectType("order"), ObjectType("item"), ObjectType("empty")),
        events=(
            Event("a", "arrive", BASE + timedelta(minutes=first)),
            Event("b", "arrive", BASE + timedelta(minutes=second)),
            Event("join", "join", BASE + timedelta(minutes=25), attrs),
            Event("end", "finish", BASE + timedelta(minutes=40)),
        ),
        objects=(Object("o", "order"), Object("i", "item"), Object("unused", "order")),
        e2o=(
            E2O("a", "o", "flow"),
            E2O("b", "i", "flow"),
            E2O("join", "o", "flow"),
            E2O("join", "i", "flow"),
            E2O("end", "o", "flow"),
        ),
    )


def summary(result, metric):
    return next(s for s in result.value.summaries if s.metric == metric)


def value(result, metric):
    return summary(result, metric).samples[0].value


def token_net(silent=False):
    places = [
        ("p", "order"),
        ("q", "order"),
        ("r", "order"),
        ("s", "order"),
        ("u", "item"),
        ("v", "item"),
        ("w", "item"),
    ]
    transitions = [
        Transition("ta", "arrive"),
        Transition("tb", "arrive"),
        Transition("tj", "join"),
        Transition("te", "finish"),
    ]
    edges = [
        ("p", "ta"),
        ("ta", "q0" if silent else "q"),
        ("u", "tb"),
        ("tb", "v"),
        ("q", "tj"),
        ("v", "tj"),
        ("tj", "r"),
        ("tj", "w"),
        ("r", "te"),
        ("te", "s"),
    ]
    if silent:
        places.append(("q0", "order"))
        transitions.append(Transition("tau"))
        edges += [("q0", "tau"), ("tau", "q")]
    return ObjectCentricPetriNet(
        tuple(TypedPlace(*p) for p in places),
        tuple(transitions),
        tuple(ObjectArc(*edge) for edge in edges),
        ObjectMarking((ObjectToken("p", "o"), ObjectToken("u", "i"))),
        ObjectMarking((ObjectToken("s", "o"), ObjectToken("w", "i"))),
        (("o", "order"), ("i", "item"), ("unused", "order")),
    )


def replay_summary(result, metric):
    return next(s for s in result.value.measurements.summaries if s.metric == metric)


class OCPerformanceTests(unittest.TestCase):
    def test_three_clocks_have_distinct_meanings_and_exact_evidence(self):
        result = measure_performance(
            fixture(),
            OCPerformanceSpec(
                metrics=(
                    "flow",
                    "sojourn",
                    "synchronization",
                    "service",
                    "ready_waiting",
                    "first_input_waiting",
                ),
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        expected = {
            "flow": 25,
            "sojourn": 15,
            "synchronization": 10,
            "service": 10,
            "ready_waiting": 5,
            "first_input_waiting": 15,
        }
        for metric, minutes in expected.items():
            with self.subTest(metric=metric):
                self.assertEqual(value(result, metric), minutes * MINUTE)
                self.assertEqual(summary(result, metric).unit, "microseconds")
        row = summary(result, "ready_waiting").samples[0]
        self.assertEqual(row.reference_event_ids, ("a", "b"))
        self.assertEqual({e.object_id for e in row.evidence}, {"o", "i"})
        self.assertTrue(all(e.target_event_id == "join" for e in row.evidence))
        self.assertEqual(row.explicit_start_time, BASE + timedelta(minutes=15))

    def test_earliest_arrival_shift_changes_first_input_wait_only(self):
        spec = OCPerformanceSpec(
            metrics=("ready_waiting", "first_input_waiting"),
            activities=("join",),
            start_attribute="start",
        )
        result = measure_performance(fixture(first=-10), spec)
        self.assertEqual(value(result, "ready_waiting"), 5 * MINUTE)
        self.assertEqual(value(result, "first_input_waiting"), 25 * MINUTE)

    def test_latest_arrival_equal_start_zero_ready_waiting(self):
        result = measure_performance(
            fixture(second=15),
            OCPerformanceSpec(
                metrics=("ready_waiting",),
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertEqual(value(result, "ready_waiting"), 0)
        self.assertEqual(summary(result, "ready_waiting").known_count, 1)

    def test_missing_start_is_unknown_not_zero_and_other_metrics_survive(self):
        result = measure_performance(
            fixture(start=None),
            OCPerformanceSpec(
                metrics=("service", "ready_waiting", "flow"),
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(value(result, "flow"), 25 * MINUTE)
        for metric in ("service", "ready_waiting"):
            row = summary(result, metric)
            self.assertEqual(
                (row.population_count, row.known_count, row.unknown_count), (1, 0, 1)
            )
            self.assertIsNone(row.mean_denominator)
            self.assertEqual(row.samples[0].reason, "missing_start_timestamp")

    def test_service_without_start_selection_and_wrong_type_are_unknown(self):
        for log, attr, reason in (
            (fixture(), None, "start_attribute_not_selected"),
            (fixture(start_type=ValueType.STRING), "start", "invalid_start_timestamp"),
        ):
            with self.subTest(reason=reason):
                result = measure_performance(
                    log,
                    OCPerformanceSpec(
                        metrics=("service",), activities=("join",), start_attribute=attr
                    ),
                )
                self.assertEqual(summary(result, "service").samples[0].reason, reason)

    def test_start_after_completion_and_before_latest_input_are_not_clipped(self):
        for start, metric, reason in (
            (30, "service", "start_after_completion"),
            (5, "ready_waiting", "start_before_observed_input"),
        ):
            with self.subTest(start=start):
                result = measure_performance(
                    fixture(start=start),
                    OCPerformanceSpec(
                        metrics=(metric,), activities=("join",), start_attribute="start"
                    ),
                )
                self.assertIsNone(value(result, metric))
                self.assertEqual(summary(result, metric).samples[0].reason, reason)

    def test_typed_formulas_use_shared_object_arrivals(self):
        result = measure_performance(
            fixture(),
            OCPerformanceSpec(
                metrics=("pooling", "lagging", "readiness"),
                object_type="item",
                activities=("join",),
            ),
        )
        self.assertEqual(value(result, "pooling"), 0)
        self.assertEqual(value(result, "lagging"), 10 * MINUTE)
        self.assertEqual(value(result, "readiness"), 10 * MINUTE)

    def test_ocpa_predecessor_participation_profile_is_not_shared_edge_typing(self):
        log = fixture()
        log = replace(
            log,
            objects=log.objects + (Object("unrelated", "item"),),
            e2o=log.e2o + (E2O("a", "unrelated", "flow"),),
        )
        native = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("pooling", "readiness"),
                object_type="item",
                activities=("join",),
            ),
        )
        reference = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("pooling", "readiness"),
                object_type="item",
                activities=("join",),
                profile="ocpa_eog_1_3_4",
            ),
        )
        self.assertEqual(value(native, "pooling"), 0)
        self.assertEqual(value(reference, "pooling"), 10 * MINUTE)
        self.assertEqual(value(native, "readiness"), 10 * MINUTE)
        self.assertEqual(value(reference, "readiness"), 0)
        self.assertNotEqual(native.computation_id, reference.computation_id)

    def test_missing_typed_predecessor_does_not_raise_empty_min_error(self):
        for profile in ("object_predecessor", "ocpa_eog_1_3_4"):
            result = measure_performance(
                fixture(),
                OCPerformanceSpec(
                    metrics=("pooling", "lagging", "readiness"),
                    object_type="empty",
                    activities=("join",),
                    profile=profile,
                ),
            )
            self.assertIs(result.status, ComputeStatus.PARTIAL)
            self.assertTrue(
                all(
                    s.samples[0].reason == "no_typed_predecessor"
                    for s in result.value.summaries
                )
            )

    def test_observed_lifecycle_and_ocpa_local_gap_are_distinct(self):
        log = fixture()
        log = replace(
            log,
            events=log.events + (Event("z", "finish", BASE + timedelta(minutes=60)),),
            e2o=log.e2o + (E2O("z", "o", "flow"),),
        )
        native = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("elapsed", "remaining"),
                object_type="order",
                activities=("join",),
            ),
        )
        reference = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("elapsed", "remaining"),
                object_type="order",
                activities=("join",),
                profile="ocpa_eog_1_3_4",
            ),
        )
        self.assertEqual(value(native, "elapsed"), 25 * MINUTE)
        self.assertEqual(value(reference, "elapsed"), 15 * MINUTE)
        self.assertEqual(value(native, "remaining"), 35 * MINUTE)
        self.assertEqual(value(reference, "remaining"), 15 * MINUTE)
        self.assertEqual(summary(native, "elapsed").samples[0].object_id, "o")
        self.assertEqual(
            summary(native, "remaining").samples[0].evidence[0].kind,
            "observed_lifecycle_last",
        )

    def test_initial_event_unknown_default_explicit_ocpa_boundary_zero(self):
        for profile, expected in (("object_predecessor", None), ("ocpa_eog_1_3_4", 0)):
            result = measure_performance(
                fixture(),
                OCPerformanceSpec(
                    metrics=("flow",), activities=("arrive",), profile=profile
                ),
            )
            self.assertEqual(value(result, "flow"), expected)

    def test_readiness_selects_only_requested_activity(self):
        result = measure_performance(
            fixture(),
            OCPerformanceSpec(
                metrics=("readiness",),
                object_type="item",
                activities=("join",),
                profile="ocpa_eog_1_3_4",
            ),
        )
        self.assertEqual(summary(result, "readiness").population_count, 1)
        self.assertEqual(value(result, "readiness"), 10 * MINUTE)

    def test_distinct_objects_not_qualifier_records_and_isolated_object_zero(self):
        log = fixture()
        log = replace(
            log, e2o=log.e2o + (E2O("join", "o", "audit"), E2O("a", "o", "audit"))
        )
        result = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("object_frequency", "activity_frequency"),
                object_type="order",
                activities=("join",),
            ),
        )
        self.assertEqual(value(result, "object_frequency"), 1)
        rows = {
            s.object_id: s.value for s in summary(result, "activity_frequency").samples
        }
        self.assertEqual(rows, {"o": 1, "unused": 0})
        self.assertEqual(summary(result, "activity_frequency").mean_denominator, 2)

    def test_qualifier_selection_changes_arrival_evidence(self):
        result = measure_performance(
            fixture(),
            OCPerformanceSpec(
                metrics=("flow",), activities=("join",), qualifiers=("audit",)
            ),
        )
        self.assertIsNone(value(result, "flow"))
        self.assertEqual(summary(result, "flow").samples[0].evidence, ())

    def test_timestamp_ties_require_explicit_convention(self):
        log = fixture(first=25)
        rejected = measure_performance(
            log, OCPerformanceSpec(metrics=("flow",), activities=("join",))
        )
        self.assertIs(rejected.status, ComputeStatus.UNAVAILABLE)
        lexical = measure_performance(
            log,
            OCPerformanceSpec(
                metrics=("flow",), activities=("join",), tie_policy="event_id"
            ),
        )
        self.assertEqual(value(lexical, "flow"), 15 * MINUTE)
        self.assertTrue(any(i.code == "timestamp_tie_broken" for i in lexical.issues))

    def test_timestamp_ties_do_not_block_service_or_frequency(self):
        result = measure_performance(
            fixture(first=25),
            OCPerformanceSpec(
                metrics=("service", "object_frequency", "activity_frequency"),
                object_type="order",
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(value(result, "service"), 10 * MINUTE)
        self.assertEqual(value(result, "object_frequency"), 1)
        self.assertEqual(summary(result, "activity_frequency").total, 1)

    def test_ambiguous_order_retains_independent_metrics_in_mixed_request(self):
        result = measure_performance(
            fixture(first=25),
            OCPerformanceSpec(
                metrics=("service", "flow", "elapsed"),
                object_type="order",
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(value(result, "service"), 10 * MINUTE)
        self.assertEqual(
            summary(result, "flow").samples[0].reason, "ambiguous_event_order"
        )
        self.assertEqual(
            summary(result, "elapsed").samples[0].reason, "ambiguous_event_order"
        )

    def test_empty_population_has_no_zero_mean(self):
        result = measure_performance(
            fixture(), OCPerformanceSpec(metrics=("flow",), activities=())
        )
        s = summary(result, "flow")
        self.assertEqual(
            (s.population_count, s.known_count, s.unknown_count), (0, 0, 0)
        )
        self.assertIsNone(s.minimum)
        self.assertIsNone(s.mean_denominator)

    def test_microseconds_are_exact_and_context_and_input_permutation_agree(self):
        log = fixture()
        log = replace(
            log,
            events=tuple(
                replace(e, time=e.time + timedelta(microseconds=1))
                if e.id == "join"
                else e
                for e in log.events
            ),
        )
        spec = OCPerformanceSpec(metrics=("flow",), activities=("join",))
        direct = measure_performance(log, spec)
        self.assertEqual(value(direct, "flow"), 25 * MINUTE + 1)
        self.assertEqual(direct, measure_performance(ComputationContext(log), spec))
        reordered = replace(
            log, events=log.events[::-1], objects=log.objects[::-1], e2o=log.e2o[::-1]
        )
        self.assertEqual(direct, measure_performance(reordered, spec))

    def test_opera_requires_real_timed_token_witness_not_eog_alias(self):
        result = measure_performance(fixture(), OCPerformanceSpec(profile="opera"))
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(
            result.issues[0].code, "unsupported_timed_token_replay_profile"
        )

    def test_bad_requests_and_unknown_input_are_explicit(self):
        for kwargs in (
            {"metrics": ("rediness",)},
            {"metrics": ("pooling",)},
            {"tie_policy": "source"},
            {"profile": "fictional"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                OCPerformanceSpec(**kwargs)
        self.assertIs(measure_performance(object()).status, ComputeStatus.INVALID_INPUT)
        unknown = measure_performance(
            fixture(), OCPerformanceSpec(object_type="missing")
        )
        self.assertIs(unknown.status, ComputeStatus.UNAVAILABLE)


class OCTokenPerformanceTests(unittest.TestCase):
    def test_real_replay_uses_consumed_token_times_and_distinguishes_opera_formula(
        self,
    ):
        log = fixture()
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        self.assertIs(replay.status, ComputeStatus.COMPUTED)
        self.assertTrue(replay.value.fitting)
        metric_names = (
            "flow",
            "sojourn",
            "synchronization",
            "service",
            "ready_waiting",
            "first_input_waiting",
        )
        native = measure_replay_performance(
            log,
            replay,
            OCReplayPerformanceSpec(
                metrics=metric_names, activities=("join",), start_attribute="start"
            ),
        )
        opera = measure_replay_performance(
            log,
            replay,
            OCReplayPerformanceSpec(
                metrics=metric_names + ("waiting",),
                activities=("join",),
                start_attribute="start",
                profile="ocpa_opera_1_3_4",
            ),
        )
        self.assertIs(native.status, ComputeStatus.COMPUTED)
        self.assertEqual(replay_summary(native, "flow").samples[0].value, 25 * MINUTE)
        self.assertEqual(
            replay_summary(native, "sojourn").samples[0].value, 15 * MINUTE
        )
        self.assertEqual(replay_summary(opera, "flow").samples[0].value, 35 * MINUTE)
        self.assertEqual(replay_summary(opera, "sojourn").samples[0].value, 25 * MINUTE)
        self.assertEqual(replay_summary(opera, "waiting").samples[0].value, 15 * MINUTE)
        self.assertEqual(
            replay_summary(native, "ready_waiting").samples[0].value, 5 * MINUTE
        )
        self.assertEqual(
            replay_summary(native, "service").samples[0].value, 10 * MINUTE
        )
        self.assertEqual(native.parent_computation_ids, (replay.computation_id,))
        observed = native.value.token_inputs[0]
        self.assertEqual((observed.known_count, observed.unknown_count), (2, 0))
        self.assertEqual(
            {t.arrival_time for t in observed.arrivals},
            {BASE, BASE + timedelta(minutes=10)},
        )
        self.assertEqual({t.place_id for t in observed.arrivals}, {"q", "v"})
        self.assertNotEqual(native.computation_id, opera.computation_id)

    def test_silent_token_production_inherits_max_input_clock(self):
        log = fixture()
        replay = replay_object_log(
            log, token_net(silent=True), ObjectReplaySpec(("order", "item"))
        )
        result = measure_replay_performance(
            log, replay, OCReplayPerformanceSpec(activities=("join",))
        )
        self.assertEqual(replay_summary(result, "flow").samples[0].value, 25 * MINUTE)
        order = next(
            t for t in result.value.token_inputs[0].arrivals if t.object_id == "o"
        )
        self.assertEqual(
            (order.origin, order.arrival_time, order.source_event_ids),
            ("silent", BASE, ("a",)),
        )
        self.assertEqual(replay.value.steps[order.produced_step].kind, "silent")

    def test_initial_token_arrival_is_unknown_with_full_population(self):
        log = fixture()
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        result = measure_replay_performance(log, replay)
        summary = replay_summary(result, "flow")
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(
            (summary.population_count, summary.known_count, summary.unknown_count),
            (4, 2, 2),
        )
        initial = next(
            t
            for row in result.value.token_inputs
            for t in row.arrivals
            if t.origin == "initial"
        )
        self.assertIsNone(initial.arrival_time)
        self.assertEqual(initial.unknown_reason, "initial_token_time_unknown")

    def test_repaired_input_unknown_but_visible_output_is_observed(self):
        log = fixture()
        net = token_net()
        net = replace(net, initial_marking=ObjectMarking((ObjectToken("p", "o"),)))
        replay = replay_object_log(log, net, ObjectReplaySpec(("order", "item")))
        self.assertFalse(replay.value.fitting)
        result = measure_replay_performance(log, replay)
        b = next(row for row in result.value.token_inputs if row.event_id == "b")
        self.assertEqual(b.arrivals[0].origin, "injected")
        join = next(row for row in result.value.token_inputs if row.event_id == "join")
        self.assertEqual((join.known_count, join.unknown_count), (2, 0))

    def test_repeated_self_loop_cannot_use_future_token_visits(self):
        log = OCEL(
            event_types=(EventType("A"),),
            object_types=(ObjectType("T"),),
            events=tuple(
                Event(str(i), "A", BASE + timedelta(minutes=10 * i)) for i in range(3)
            ),
            objects=(Object("o", "T"),),
            e2o=tuple(E2O(str(i), "o", "") for i in range(3)),
        )
        for initial_count, expected in (
            (1, [None, 10 * MINUTE, 10 * MINUTE]),
            (2, [None, None, 20 * MINUTE]),
        ):
            with self.subTest(initial_count=initial_count):
                marking = ObjectMarking((ObjectToken("p", "o"),) * initial_count)
                net = ObjectCentricPetriNet(
                    (TypedPlace("p", "T"),),
                    (Transition("t", "A"),),
                    (ObjectArc("p", "t"), ObjectArc("t", "p")),
                    marking,
                    marking,
                    (("o", "T"),),
                )
                replay = replay_object_log(log, net, ObjectReplaySpec(("T",)))
                result = measure_replay_performance(
                    log, replay, OCReplayPerformanceSpec(metrics=("flow",))
                )
                self.assertEqual(
                    [row.value for row in replay_summary(result, "flow").samples],
                    expected,
                )
                self.assertEqual(
                    len(
                        {
                            t.token_serial
                            for row in result.value.token_inputs
                            for t in row.arrivals
                        }
                    ),
                    3,
                )

    def test_typed_lagging_profiles_can_differ_and_negative_is_unknown(self):
        log = fixture()
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        native = measure_replay_performance(
            log,
            replay,
            OCReplayPerformanceSpec(
                metrics=("lagging",), object_type="order", activities=("join",)
            ),
        )
        opera = measure_replay_performance(
            log,
            replay,
            OCReplayPerformanceSpec(
                metrics=("lagging",),
                object_type="order",
                activities=("join",),
                profile="ocpa_opera_1_3_4",
            ),
        )
        self.assertEqual(replay_summary(native, "lagging").samples[0].value, 0)
        row = replay_summary(opera, "lagging").samples[0]
        self.assertIsNone(row.value)
        self.assertEqual(row.reason, "negative_timed_metric")

    def test_missing_start_does_not_discard_known_input_time(self):
        log = fixture(start=None)
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        result = measure_replay_performance(
            log,
            replay,
            OCReplayPerformanceSpec(
                metrics=("flow", "service"),
                activities=("join",),
                start_attribute="start",
            ),
        )
        self.assertEqual(replay_summary(result, "flow").known_count, 1)
        self.assertEqual(replay_summary(result, "service").unknown_count, 1)

    def test_partial_token_time_does_not_drop_unknown_inputs_from_maximum(self):
        log = fixture()
        net = token_net()
        net = replace(
            net,
            initial_marking=ObjectMarking(
                net.initial_marking.tokens + (ObjectToken("v", "i"),)
            ),
        )
        replay = replay_object_log(log, net, ObjectReplaySpec(("order", "item")))
        result = measure_replay_performance(
            log, replay, OCReplayPerformanceSpec(activities=("join",))
        )
        inputs = result.value.token_inputs[0]
        self.assertEqual((inputs.known_count, inputs.unknown_count), (1, 1))
        self.assertTrue(
            all(s.unknown_count == 1 for s in result.value.measurements.summaries)
        )

    def test_pooling_only_requires_requested_type_token_times(self):
        log = fixture()
        log = replace(
            log,
            events=tuple(e for e in log.events if e.id != "b"),
            e2o=tuple(r for r in log.e2o if r.event != "b"),
        )
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        for profile in ("token_arrivals", "ocpa_opera_1_3_4"):
            with self.subTest(profile=profile):
                result = measure_replay_performance(
                    log,
                    replay,
                    OCReplayPerformanceSpec(
                        metrics=("pooling",),
                        object_type="order",
                        activities=("join",),
                        profile=profile,
                    ),
                )
                self.assertIs(result.status, ComputeStatus.COMPUTED)
                self.assertEqual(result.value.token_inputs[0].unknown_count, 1)
                self.assertEqual(replay_summary(result, "pooling").samples[0].value, 0)

    def test_silent_initial_inputs_stay_unknown(self):
        log = fixture()
        net = token_net()
        net = replace(
            net,
            places=net.places + (TypedPlace("before_p", "order"),),
            transitions=net.transitions + (Transition("initial_tau"),),
            arcs=net.arcs
            + (ObjectArc("before_p", "initial_tau"), ObjectArc("initial_tau", "p")),
            initial_marking=ObjectMarking(
                (ObjectToken("before_p", "o"), ObjectToken("u", "i"))
            ),
        )
        replay = replay_object_log(log, net, ObjectReplaySpec(("order", "item")))
        result = measure_replay_performance(
            log, replay, OCReplayPerformanceSpec(activities=("arrive",))
        )
        a = next(row for row in result.value.token_inputs if row.event_id == "a")
        self.assertEqual(a.arrivals[0].origin, "silent")
        self.assertEqual(a.arrivals[0].unknown_reason, "silent_input_time_unknown")
        self.assertIsNone(a.arrivals[0].arrival_time)

    def test_limited_replay_retains_unprocessed_events_in_denominator(self):
        log = fixture()
        replay = replay_object_log(
            log,
            token_net(silent=True),
            ObjectReplaySpec(("order", "item"), silent_max_states=1),
        )
        self.assertIs(replay.status, ComputeStatus.PARTIAL)
        result = measure_replay_performance(log, replay)
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(replay_summary(result, "flow").population_count, 4)
        self.assertTrue(
            any(row.reason == "event_not_replayed" for row in result.value.token_inputs)
        )
        self.assertTrue(
            any(issue.code == "replay_incomplete" for issue in result.issues)
        )

    def test_unmapped_activity_is_unknown_instead_of_zero_flow(self):
        log = fixture()
        net = token_net()
        net = replace(
            net,
            transitions=tuple(
                replace(t, activity="not_join") if t.id == "tj" else t
                for t in net.transitions
            ),
        )
        replay = replay_object_log(log, net, ObjectReplaySpec(("order", "item")))
        result = measure_replay_performance(
            log, replay, OCReplayPerformanceSpec(activities=("join",))
        )
        row = replay_summary(result, "flow").samples[0]
        self.assertIsNone(row.value)
        self.assertEqual(row.reason, "log_deviation_without_token_inputs")

    def test_witness_source_identity_and_token_continuity_checked(self):
        log = fixture()
        replay = replay_object_log(
            log, token_net(), ObjectReplaySpec(("order", "item"))
        )
        changed_log = fixture(first=-1)
        self.assertEqual(
            measure_replay_performance(changed_log, replay).issues[0].code,
            "replay_source_mismatch",
        )
        broken = replace(replay, computation_id="bad-id")
        self.assertEqual(
            measure_replay_performance(log, broken).issues[0].code,
            "replay_identity_mismatch",
        )
        steps = replay.value.steps
        with self.assertRaises(ValueError):
            replace(steps[1], consumed_tokens=())
        broken = replace(
            replay, value=replace(replay.value, model_digest="wrong-model")
        )
        result = measure_replay_performance(log, broken)
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)
        self.assertEqual(result.issues[0].code, "invalid_replay_witness")

    def test_requested_ambiguous_waiting_is_not_implicit(self):
        with self.assertRaises(ValueError):
            OCReplayPerformanceSpec(metrics=("waiting",))
        with self.assertRaises(ValueError):
            OCReplayPerformanceSpec(metrics=("remaining",), object_type="order")


if __name__ == "__main__":
    unittest.main()
