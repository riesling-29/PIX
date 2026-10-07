"""Strict inequalities verified independently by bounded all-segment enumeration."""

import itertools
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

from pix.case_centric.interleavings import (
    CaseLink,
    InterleavingPoint,
    InterleavingSpec,
    discover_interleavings,
    validate_interleaving_result,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseGlobal, CaseLog, CaseTrace
from pix.results import (
    _decode,
    _encode,
    result_document,
    result_from_json,
    result_json_bytes,
)

ORIGIN = datetime(2026, 9, 15, tzinfo=timezone.utc)


def source(times, prefix="e", case_id="c", activities=True):
    return CaseLog(
        (
            CaseTrace(
                case_id,
                tuple(
                    CaseEvent(
                        f"{prefix}{i}",
                        (
                            *(
                                (CaseAttribute("concept:name", "string", f"a{i}"),)
                                if activities
                                else ()
                            ),
                            *(
                                (
                                    CaseAttribute(
                                        "time:timestamp",
                                        "date",
                                        ORIGIN + timedelta(seconds=t),
                                    ),
                                )
                                if t is not None
                                else ()
                            ),
                        ),
                    )
                    for i, t in enumerate(times)
                ),
            ),
        )
    )


def spec(**kwargs):
    return InterleavingSpec(case_links=(CaseLink("c", "c"),), **kwargs)


def selected(result):
    return [
        (w.direction, w.source.event_id, w.target.event_id, w.elapsed_seconds)
        for w in result.value.witnesses
    ]


class InterleavingTests(unittest.TestCase):
    def test_lr_strict_crossing_hand_calculated(self):
        result = discover_interleavings(
            source((0, 10), "l"), source((5, 15), "r"), spec(include_boundaries=False)
        )
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(selected(result), [("LR", "l0", "r0", 5.0)])
        witness = result.value.witnesses[0]
        self.assertEqual([p.event_id for p in witness.left_segment], ["l0", "l1"])
        self.assertEqual([p.event_id for p in witness.right_segment], ["r0", "r1"])

    def test_rl_uses_reference_second_endpoints_not_symmetric_firsts(self):
        result = discover_interleavings(
            source((5, 15), "l"), source((0, 10), "r"), spec(include_boundaries=False)
        )
        self.assertEqual(selected(result), [("RL", "r1", "l1", 5.0)])

    def test_logical_boundaries_never_fabricate_event_ids_or_timestamps(self):
        result = discover_interleavings(
            source((0, 10), "l"), source((5, 15), "r"), spec()
        )
        self.assertEqual(
            selected(result),
            [
                ("RL", "r0", "l1", 5.0),
                ("LR", "l0", "r0", 5.0),
                ("RL", "r1", None, None),
            ],
        )
        boundary = result.value.witnesses[-1].target
        self.assertEqual(boundary.boundary, "end")
        self.assertIsNone(boundary.timestamp)
        self.assertIsNone(boundary.source_position)

    def test_boundary_start_is_explicit(self):
        result = discover_interleavings(
            source((5, 15), "l"), source((0, 10), "r"), spec()
        )
        self.assertEqual(result.value.witnesses[0].source.boundary, "start")
        self.assertIsNone(result.value.witnesses[0].elapsed_seconds)

    def test_ties_touching_nested_and_empty_cases_produce_no_crossing(self):
        for left, right in [
            ((0, 10), (0, 15)),
            ((0, 10), (10, 15)),
            ((0, 20), (5, 10)),
            ((0, 10), (5, 10)),
            ((), (0, 1)),
        ]:
            with self.subTest(left=left, right=right):
                result = discover_interleavings(
                    source(left), source(right), spec(include_boundaries=False)
                )
                self.assertEqual(result.value.witnesses, ())

    def test_sweep_matches_independent_cartesian_oracle_with_ties(self):
        # Oracle uses numeric infinities and all segment pairs, not sweep helpers.
        times = tuple(itertools.combinations_with_replacement(range(4), 3))
        for left_times, right_times, boundaries in itertools.product(
            times, times, (False, True)
        ):
            left, right = source(left_times, "l"), source(right_times, "r")
            lpoints = [(t, f"l{i}") for i, t in enumerate(left_times)]
            rpoints = [(t, f"r{i}") for i, t in enumerate(right_times)]
            if boundaries:
                lpoints = [(float("-inf"), None), *lpoints, (float("inf"), None)]
                rpoints = [(float("-inf"), None), *rpoints, (float("inf"), None)]
            expected = []
            for (l0, l1), (r0, r1) in itertools.product(
                zip(lpoints, lpoints[1:]),
                zip(rpoints, rpoints[1:]),
            ):
                if l0[0] < r0[0] < l1[0] < r1[0]:
                    expected.append(("LR", l0[1], r0[1]))
                elif r0[0] < l0[0] < r1[0] < l1[0]:
                    expected.append(("RL", r1[1], l1[1]))
            actual = discover_interleavings(
                left, right, spec(include_boundaries=boundaries)
            )
            self.assertCountEqual(
                [
                    (w.direction, w.source.event_id, w.target.event_id)
                    for w in actual.value.witnesses
                ],
                expected,
            )

    def test_source_order_is_not_time_order_and_positions_are_retained(self):
        result = discover_interleavings(
            source((10, 0), "l"), source((15, 5), "r"), spec(include_boundaries=False)
        )
        self.assertEqual(selected(result), [("LR", "l1", "r1", 5.0)])
        self.assertEqual(result.value.witnesses[0].source.source_position, 1)

    def test_missing_or_naive_timestamp_invalidates_instead_of_bridging(self):
        right = source((5, 15), "r")
        missing = discover_interleavings(source((0, None, 10)), right, spec())
        self.assertEqual(missing.status, ComputeStatus.INVALID_INPUT)
        self.assertIsNone(missing.value)
        event = CaseEvent(
            "n", (CaseAttribute("time:timestamp", "date", datetime(2026, 9, 15)),)
        )
        naive = discover_interleavings(
            CaseLog((CaseTrace("c", (event,)),)), right, spec()
        )
        self.assertEqual(naive.issues[0].code, "invalid_interleaving_time")
        extreme = CaseEvent(
            "extreme",
            (
                CaseAttribute(
                    "time:timestamp",
                    "date",
                    datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1))),
                ),
            ),
        )
        overflow = discover_interleavings(
            CaseLog((CaseTrace("c", (extreme,)),)),
            right,
            spec(),
        )
        self.assertEqual(overflow.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(overflow.issues[0].code, "invalid_interleaving_time")

    def test_missing_activity_keeps_time_witness_partial(self):
        result = discover_interleavings(
            source((0, 10), activities=False),
            source((5, 15)),
            spec(include_boundaries=False),
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertIsNone(result.value.witnesses[0].source.activity)
        self.assertEqual(result.value.witnesses[0].elapsed_seconds, 5)

    def test_globals_are_resolved_raw_nested_nonfinite_are_untouched(self):
        left = source((0, 10), "l", activities=False)
        raw = CaseAttribute("raw", "float", float("inf"))
        left = replace(
            left,
            attributes=(raw,),
            globals=(
                CaseGlobal(
                    "event", (CaseAttribute("concept:name", "string", "global"),)
                ),
            ),
        )
        result = discover_interleavings(
            left, source((5, 15), "r"), spec(include_boundaries=False)
        )
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.witnesses[0].source.activity, "global")
        self.assertIs(left.attributes[0], raw)
        self.assertEqual(left.traces[0].events[0].attributes[0].key, "time:timestamp")

    def test_duplicate_selected_attribute_is_invalid(self):
        left = source((0, 10))
        event = left.traces[0].events[0]
        left = replace(
            left,
            traces=(
                CaseTrace(
                    "c",
                    (
                        replace(
                            event,
                            attributes=(
                                *event.attributes,
                                CaseAttribute("time:timestamp", "date", ORIGIN),
                            ),
                        ),
                        left.traces[0].events[1],
                    ),
                ),
            ),
        )
        result = discover_interleavings(left, source((5, 15)), spec())
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "ambiguous_attribute")

    def test_explicit_selection_empty_links_and_unknown_case(self):
        left, right = source((0, 10)), source((5, 15))
        empty = discover_interleavings(left, right)
        self.assertEqual(empty.value.linked_event_count, 0)
        self.assertEqual(empty.value.witnesses, ())
        unknown = discover_interleavings(
            left, right, InterleavingSpec((CaseLink("no", "c"),))
        )
        self.assertEqual(unknown.status, ComputeStatus.INVALID_INPUT)
        # Missing timestamps in unlinked cases do not contaminate the population.
        left = replace(
            left, traces=(*left.traces, CaseTrace("unlinked", (CaseEvent("bad"),)))
        )
        self.assertEqual(
            discover_interleavings(left, right, spec()).status, ComputeStatus.COMPUTED
        )

    def test_ids_colliding_across_sides_are_distinct(self):
        result = discover_interleavings(
            source((0, 10)), source((5, 15)), spec(include_boundaries=False)
        )
        w = result.value.witnesses[0]
        self.assertEqual(w.source.event_id, w.target.event_id)
        self.assertNotEqual(w.source.side, w.target.side)

    def test_renaming_preserves_math_and_changes_identity(self):
        first = discover_interleavings(
            source((0, 10), "a"), source((5, 15), "b"), spec()
        )
        second = discover_interleavings(
            source((0, 10), "z"), source((5, 15), "x"), spec()
        )
        self.assertEqual(
            [(w.direction, w.elapsed_seconds) for w in first.value.witnesses],
            [(w.direction, w.elapsed_seconds) for w in second.value.witnesses],
        )
        self.assertNotEqual(first.computation_id, second.computation_id)

    def test_limits_return_no_truncated_value(self):
        left, right = source((0, 10)), source((5, 15))
        for kwargs, code in [
            ({"max_events": 3}, "interleaving_event_limit"),
            ({"max_steps": 1}, "interleaving_step_limit"),
            ({"max_witnesses": 1}, "interleaving_witness_limit"),
        ]:
            result = discover_interleavings(left, right, spec(**kwargs))
            self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
            self.assertIsNone(result.value)
            self.assertEqual(result.issues[0].code, code)
        left2 = replace(left, traces=(*left.traces, CaseTrace("second")))
        bounded = InterleavingSpec(
            (CaseLink("c", "c"), CaseLink("second", "c")), max_case_links=1
        )
        self.assertEqual(
            discover_interleavings(left2, right, bounded).issues[0].code,
            "interleaving_case_link_limit",
        )

    def test_many_to_many_does_not_create_unrequested_links(self):
        left = source((0, 10), "l")
        right = source((5, 15), "r")
        right2 = source((6, 16), "s", "other")
        right = replace(right, traces=(*right.traces, *right2.traces))
        request = InterleavingSpec(
            (CaseLink("c", "c"), CaseLink("c", "other")), include_boundaries=False
        )
        result = discover_interleavings(left, right, request)
        self.assertEqual(
            [w.right_case_id for w in result.value.witnesses], ["c", "other"]
        )
        self.assertEqual(result.value.linked_event_count, 6)

    def test_contracts_identity_roundtrip_and_validation(self):
        result = discover_interleavings(source((0, 10)), source((5, 15)), spec())
        self.assertEqual(
            _decode(_encode(result.value), type(result.value)), result.value
        )
        self.assertEqual(_decode(_encode(result.spec), type(result.spec)), result.spec)
        with self.assertRaises(FrozenInstanceError):
            result.value.steps = 0
        for kwargs in (
            {"max_steps": True},
            {"max_events": 0},
            {"include_boundaries": 1},
        ):
            with self.assertRaises((TypeError, ValueError)):
                InterleavingSpec(**kwargs)
        with self.assertRaises(ValueError):
            InterleavingSpec((CaseLink("c", "c"), CaseLink("c", "c")))
        with self.assertRaises(ValueError):
            InterleavingPoint("left", "c", "fake", None, None, None, "start")
        with self.assertRaises(ValueError):
            replace(result.value.witnesses[0], elapsed_seconds=123.0)

    def test_redundant_envelope_facts_reject_inconsistent_persisted_payloads(self):
        result = discover_interleavings(source((0, 10)), source((5, 15)), spec())
        validate_interleaving_result(result)
        self.assertEqual(result_from_json(result_json_bytes(result)), result)
        inconsistent = (
            replace(
                result,
                value=replace(
                    result.value, left_digest="pix.case-log.v1:sha256:" + "0" * 64
                ),
            ),
            replace(result, value=replace(result.value, case_links=(), witnesses=())),
            replace(result, value=replace(result.value, steps=0)),
            replace(result, value=replace(result.value, linked_event_count=1)),
            replace(
                result,
                value=replace(result.value, witnesses=result.value.witnesses * 2),
            ),
            replace(result, spec=replace(result.spec, include_boundaries=False)),
            replace(result, spec=replace(result.spec, max_steps=1)),
        )
        for invalid in inconsistent:
            with self.assertRaises(ValueError):
                validate_interleaving_result(invalid)
            with self.assertRaises(ValueError):
                result_document(invalid)


if __name__ == "__main__":
    unittest.main()
