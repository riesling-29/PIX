"""Independent pair/closure oracles and source-event evidence for link analysis."""

import json
import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product

from pix.case_centric.link_analysis import (
    OPERATOR_ID,
    RESULT_SCHEMAS,
    LinkAnalysisPayload,
    LinkAnalysisSpec,
    discover_link_analysis,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
    case_log_digest,
)
from pix.results import _decode, _encode

ORIGIN = datetime(2026, 9, 15, tzinfo=timezone.utc)
MISSING = object()


def attribute(key, value):
    if isinstance(value, CaseAttribute):
        return replace(value, key=key)
    kind = {
        str: "string",
        int: "int",
        float: "float",
        bool: "boolean",
        datetime: "date",
        type(None): "null",
    }[type(value)]
    return CaseAttribute(key, kind, value)


def event(identity, incoming="x", outgoing="x", second=0, **extra):
    attrs = []
    for key, value in (("in", incoming), ("out", outgoing)):
        if value is not MISSING:
            attrs.append(attribute(key, value))
    if second is not None:
        instant = (
            second
            if isinstance(second, datetime)
            else ORIGIN + timedelta(seconds=second)
        )
        attrs.append(attribute("time:timestamp", instant))
    attrs.extend(attribute(key, value) for key, value in extra.items())
    return CaseEvent(identity, tuple(attrs))


def log(*traces):
    return CaseLog(
        tuple(CaseTrace(f"c{i}", tuple(events)) for i, events in enumerate(traces))
    )


def pairs(result):
    return {(link.source_event_id, link.target_event_id) for link in result.value.links}


def links(result):
    return {
        (link.source_event_id, link.target_event_id): link
        for link in result.value.links
    }


class LinkSemanticsTests(unittest.TestCase):
    def test_global_temporal_order_crosses_case_boundaries(self):
        source = log(
            [event("last", second=2), event("first", second=0)],
            [event("middle", second=1)],
        )
        result = discover_link_analysis(source)
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(
            pairs(result), {("first", "middle"), ("first", "last"), ("middle", "last")}
        )
        self.assertEqual(
            [e.event_id for e in result.value.events], ["first", "middle", "last"]
        )
        self.assertEqual([e.source_index for e in result.value.events], [1, 2, 0])
        self.assertEqual([e.trace_index for e in result.value.events], [0, 1, 0])
        self.assertEqual(source.traces[0].events[0].id, "last")

    def test_equal_timestamp_has_strict_rank_forward_relation(self):
        source = log([event("z"), event("a"), event("m", second=1)])
        result = discover_link_analysis(source)
        self.assertEqual(pairs(result), {("z", "a"), ("z", "m"), ("a", "m")})
        self.assertEqual(links(result)["z", "a"].path_orders, (0, 1))

    def test_first_before_propagation(self):
        source = log([event("a"), event("b"), event("c")])
        spec = LinkAnalysisSpec(keep_first_occurrence=True)
        direct = discover_link_analysis(source, spec)
        self.assertEqual(pairs(direct), {("a", "b"), ("b", "c")})
        self.assertEqual(direct.value.candidate_pair_count, 3)
        self.assertEqual(direct.value.direct_link_count, 2)
        closure = discover_link_analysis(source, replace(spec, propagate=True))
        self.assertEqual(pairs(closure), {("a", "b"), ("a", "c"), ("b", "c")})
        self.assertEqual(links(closure)["a", "c"].path_event_ids, ("a", "b", "c"))
        self.assertFalse(links(closure)["a", "c"].direct)
        self.assertEqual(closure.value.propagated_link_count, 1)
        self.assertEqual(closure.value.witness_event_count, 7)
        # Keeping all direct links preserves the shortest direct witness.
        all_links = discover_link_analysis(source, LinkAnalysisSpec(propagate=True))
        self.assertEqual(links(all_links)["a", "c"].path_event_ids, ("a", "c"))

    def test_branch_merge_shortest_witness_uses_input_order(self):
        source = log(
            [
                event("s", "start", "x"),
                event("z", "x", "y"),
                event("a", "x", "y"),
                event("t", "y", "end"),
            ]
        )
        result = discover_link_analysis(source, LinkAnalysisSpec(propagate=True))
        self.assertEqual(
            pairs(result), {("s", "z"), ("s", "a"), ("s", "t"), ("z", "t"), ("a", "t")}
        )
        self.assertEqual(links(result)["s", "t"].path_event_ids, ("s", "z", "t"))
        first = discover_link_analysis(
            source, LinkAnalysisSpec(propagate=True, keep_first_occurrence=True)
        )
        self.assertEqual(pairs(first), {("s", "z"), ("s", "t"), ("z", "t"), ("a", "t")})

    def test_nonempty_cycles_create_self_pairs(self):
        source = log([event("a", "z", "x"), event("b", "x", "y"), event("c", "y", "z")])
        spec = LinkAnalysisSpec(look_forward=False, propagate=True)
        result = discover_link_analysis(source, spec)
        self.assertEqual(pairs(result), set(product("abc", repeat=2)))
        self.assertEqual(links(result)["a", "a"].path_event_ids, ("a", "b", "c", "a"))
        self.assertEqual(links(result)["b", "b"].path_event_ids, ("b", "c", "a", "b"))
        self.assertEqual(links(result)["c", "c"].path_event_ids, ("c", "a", "b", "c"))
        self.assertFalse(links(result)["a", "a"].direct)
        self.assertEqual(result.value.direct_link_count, 3)
        forward = discover_link_analysis(source, replace(spec, look_forward=True))
        self.assertEqual(pairs(forward), {("a", "b"), ("a", "c"), ("b", "c")})

    def test_first_without_forward_can_select_self_and_earlier_targets(self):
        source = log([event("a"), event("b"), event("c")])
        for propagate in (False, True):
            result = discover_link_analysis(
                source,
                LinkAnalysisSpec(
                    look_forward=False,
                    keep_first_occurrence=True,
                    propagate=propagate,
                ),
            )
            self.assertEqual(pairs(result), {("a", "a"), ("b", "a"), ("c", "a")})
            self.assertEqual(links(result)["a", "a"].path_event_ids, ("a", "a"))
            self.assertTrue(all(e.direct for e in result.value.links))

    def test_acyclic_relation_is_not_reflexive_closure(self):
        result = discover_link_analysis(
            log([event("a", "start", "x"), event("b", "x", "end")]),
            LinkAnalysisSpec(look_forward=False, propagate=True),
        )
        self.assertEqual(pairs(result), {("a", "b")})

    def test_disconnected_components_have_no_invented_links(self):
        source = log(
            [event("a", "u", "x"), event("b", "x", "v")],
            [event("c", "m", "y"), event("d", "y", "n")],
        )
        result = discover_link_analysis(source, LinkAnalysisSpec(propagate=True))
        self.assertEqual(pairs(result), {("a", "b"), ("c", "d")})

    def test_id_renaming_preserves_pairs_order_and_witness_positions(self):
        source = log(
            [
                event("z", "start", "x"),
                event("a", "x", "y"),
                event("m", "x", "y"),
                event("b", "y", "end"),
            ]
        )
        renamed = CaseLog(
            tuple(
                replace(
                    t,
                    id=f"trace-{i}",
                    events=tuple(
                        replace(e, id=f"ID-{100 - j}") for j, e in enumerate(t.events)
                    ),
                )
                for i, t in enumerate(source.traces)
            )
        )
        spec = LinkAnalysisSpec(propagate=True)
        left, right = (
            discover_link_analysis(source, spec),
            discover_link_analysis(renamed, spec),
        )
        self.assertEqual(
            [(e.source_order, e.target_order, e.path_orders) for e in left.value.links],
            [
                (e.source_order, e.target_order, e.path_orders)
                for e in right.value.links
            ],
        )
        self.assertNotEqual(left.source_digest, right.source_digest)

    def test_utc_normalization_precedes_source_order_tie_break(self):
        same_time = ORIGIN.astimezone(timezone(timedelta(hours=9)))
        source = log([event("z", second=same_time), event("a", second=ORIGIN)])
        result = discover_link_analysis(source)
        self.assertEqual(pairs(result), {("z", "a")})
        self.assertTrue(all(e.timestamp == ORIGIN for e in result.value.events))


class LinkEligibilityTests(unittest.TestCase):
    def test_typed_scalar_keys_are_disjoint(self):
        values = [1, 1.0, True, "1", CaseAttribute("x", "id", "1")]
        events = [event(f"s{i}", MISSING, value) for i, value in enumerate(values)]
        events += [event(f"t{i}", value, MISSING) for i, value in enumerate(values)]
        result = discover_link_analysis(log(events))
        self.assertEqual(pairs(result), {(f"s{i}", f"t{i}") for i in range(5)})
        self.assertEqual(result.status, ComputeStatus.PARTIAL)

    def test_null_missing_nonfinite_compound_and_naive_dates_are_excluded(self):
        values = [
            MISSING,
            None,
            float("nan"),
            float("inf"),
            float("-inf"),
            CaseAttribute("x", "list"),
            CaseAttribute("x", "container"),
            datetime(2026, 9, 15),
        ]
        source = log([event(str(i), value, value) for i, value in enumerate(values)])
        result = discover_link_analysis(
            source, LinkAnalysisSpec(look_forward=False, propagate=True)
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.links, ())
        self.assertEqual(len(result.value.exclusions), 16)
        self.assertEqual(
            {e.reason for e in result.value.exclusions},
            {"missing", "null", "nonfinite", "compound", "naive_date"},
        )
        # The source identity supports stored NaN/Infinity, but envelope contains none.
        text = json.dumps(_encode(result), allow_nan=False)
        self.assertNotIn("NaN", text)
        self.assertNotIn("Infinity", text)

    def test_finite_zero_and_empty_string_are_valid_equality_values(self):
        source = log([event("s", "", -0.0), event("t", 0.0, ""), event("u", "", "end")])
        result = discover_link_analysis(source)
        self.assertEqual(pairs(result), {("s", "t"), ("t", "u")})
        self.assertEqual(result.status, ComputeStatus.COMPUTED)

    def test_date_keys_match_equal_instants(self):
        source = log(
            [
                event("a", "start", ORIGIN),
                event("b", ORIGIN.astimezone(timezone(timedelta(hours=9))), "end"),
            ]
        )
        self.assertEqual(pairs(discover_link_analysis(source)), {("a", "b")})

    def test_global_defaults_and_custom_keys(self):
        source = log([event("a", outgoing=MISSING), event("b", incoming=MISSING)])
        source = replace(
            source,
            globals=(
                CaseGlobal(
                    "event",
                    (
                        attribute("out", "x"),
                        attribute("in", "x"),
                    ),
                ),
            ),
        )
        self.assertEqual(discover_link_analysis(source).status, ComputeStatus.COMPUTED)
        self.assertEqual(pairs(discover_link_analysis(source)), {("a", "b")})
        custom = log(
            [
                event("a", output="job", input="none"),
                event("b", output="end", input="job"),
            ]
        )
        self.assertEqual(
            pairs(
                discover_link_analysis(
                    custom, LinkAnalysisSpec(out_key="output", in_key="input")
                )
            ),
            {("a", "b")},
        )

    def test_trace_names_are_not_implicitly_joined_as_event_attributes(self):
        source = log([event("a")], [event("b")])
        source = replace(
            source,
            traces=tuple(
                replace(t, attributes=(attribute("concept:name", "shared"),))
                for t in source.traces
            ),
        )
        result = discover_link_analysis(
            source,
            LinkAnalysisSpec(out_key="case:concept:name", in_key="case:concept:name"),
        )
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.links, ())

    def test_explicit_case_id_scope_gives_direct_and_eventual_case_pairs(self):
        source = log(
            [event("a", second=0), event("b", second=2), event("c", second=4)],
            [event("d", second=1), event("e", second=3)],
        )
        spec = LinkAnalysisSpec(
            out_scope="case_id",
            in_scope="case_id",
            keep_first_occurrence=True,
        )
        direct = discover_link_analysis(source, spec)
        self.assertEqual(direct.status, ComputeStatus.COMPUTED)
        self.assertEqual(pairs(direct), {("a", "b"), ("b", "c"), ("d", "e")})
        eventual = discover_link_analysis(
            source, replace(spec, keep_first_occurrence=False)
        )
        self.assertEqual(pairs(eventual), pairs(direct) | {("a", "c")})
        propagated = discover_link_analysis(source, replace(spec, propagate=True))
        self.assertEqual(pairs(propagated), pairs(eventual))
        self.assertEqual(links(propagated)["a", "c"].path_event_ids, ("a", "b", "c"))

    def test_explicit_trace_attribute_scope_can_connect_distinct_cases(self):
        source = log([event("a")], [event("b")], [event("c")])
        source = replace(
            source,
            traces=tuple(
                replace(
                    t,
                    attributes=(
                        attribute("concept:name", "shared" if i < 2 else "other"),
                    ),
                )
                for i, t in enumerate(source.traces)
            ),
        )
        spec = LinkAnalysisSpec(
            out_scope="trace",
            in_scope="trace",
            out_key="concept:name",
            in_key="concept:name",
        )
        self.assertEqual(pairs(discover_link_analysis(source, spec)), {("a", "b")})
        separate = discover_link_analysis(
            source, replace(spec, out_scope="case_id", in_scope="case_id")
        )
        self.assertEqual(separate.value.links, ())

    def test_trace_scope_defaults_and_overrides(self):
        source = log([event("a")], [event("b")], [event("c")])
        source = replace(
            source, globals=(CaseGlobal("trace", (attribute("batch", 7),)),)
        )
        source = replace(
            source,
            traces=source.traces[:2]
            + (replace(source.traces[2], attributes=(attribute("batch", 8),)),),
        )
        spec = LinkAnalysisSpec(
            out_scope="trace", in_scope="trace", out_key="batch", in_key="batch"
        )
        result = discover_link_analysis(source, spec)
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(pairs(result), {("a", "b")})

    def test_mixed_event_and_case_id_scopes_keep_identity_type(self):
        source = log(
            [
                event("a", outgoing=CaseAttribute("out", "id", "c1")),
                event("b", outgoing="c1"),
            ],
            [event("c"), event("d")],
        )
        result = discover_link_analysis(source, LinkAnalysisSpec(in_scope="case_id"))
        self.assertEqual(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(pairs(result), {("a", "c"), ("a", "d")})

    def test_trace_endpoint_missing_and_ambiguity_are_explicit(self):
        source = log([event("a")])
        spec = LinkAnalysisSpec(out_scope="trace", out_key="unknown")
        result = discover_link_analysis(source, spec)
        self.assertEqual(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.exclusions[0].scope, "trace")
        ambiguous = replace(
            source,
            traces=(
                replace(
                    source.traces[0],
                    attributes=(
                        attribute("unknown", "x"),
                        attribute("unknown", "y"),
                    ),
                ),
            ),
        )
        self.assertEqual(
            discover_link_analysis(ambiguous, spec).status, ComputeStatus.INVALID_INPUT
        )

    def test_missing_naive_wrong_type_and_overflow_times_are_invalid(self):
        for instant in (
            None,
            datetime(2026, 9, 15),
            datetime.min.replace(tzinfo=timezone(timedelta(hours=1))),
        ):
            with self.subTest(instant=instant):
                result = discover_link_analysis(log([event("a", second=instant)]))
                self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
                self.assertIsNone(result.value)
                self.assertEqual(result.issues[0].code, "invalid_link_timestamp")
        source = log([CaseEvent("a", (attribute("time:timestamp", "today"),))])
        self.assertEqual(
            discover_link_analysis(source).status, ComputeStatus.INVALID_INPUT
        )

    def test_duplicate_effective_attribute_is_invalid(self):
        source_event = event("a")
        source = log(
            [
                replace(
                    source_event,
                    attributes=source_event.attributes + (attribute("out", "y"),),
                )
            ]
        )
        result = discover_link_analysis(source)
        self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)
        self.assertEqual(result.issues[0].code, "ambiguous_link_attribute")


class LinkBoundsAndContractTests(unittest.TestCase):
    def setUp(self):
        self.source = log([event("a"), event("b"), event("c")])

    def test_event_bound_and_equality(self):
        self.assertEqual(
            discover_link_analysis(self.source, LinkAnalysisSpec(max_events=3)).status,
            ComputeStatus.COMPUTED,
        )
        result = discover_link_analysis(self.source, LinkAnalysisSpec(max_events=2))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].at, ("max_events",))

    def test_direct_relation_bound_never_returns_truncated_pairs(self):
        result = discover_link_analysis(self.source, LinkAnalysisSpec(max_links=2))
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        exact = discover_link_analysis(self.source, LinkAnalysisSpec(max_links=3))
        self.assertEqual(len(exact.value.links), 3)

    def test_closure_relation_bound(self):
        spec = LinkAnalysisSpec(keep_first_occurrence=True, propagate=True, max_links=2)
        result = discover_link_analysis(self.source, spec)
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(
            len(
                discover_link_analysis(
                    self.source, replace(spec, max_links=3)
                ).value.links
            ),
            3,
        )

    def test_work_bound_applies_to_direct_build_and_closure_traversal(self):
        direct = discover_link_analysis(self.source, LinkAnalysisSpec(max_work=2))
        self.assertEqual(direct.status, ComputeStatus.UNAVAILABLE)
        spec = LinkAnalysisSpec(keep_first_occurrence=True, propagate=True)
        full = discover_link_analysis(self.source, spec)
        self.assertEqual(full.value.work_count, 5)  # 2 edges built + 3 examined.
        bounded = discover_link_analysis(self.source, replace(spec, max_work=4))
        self.assertEqual(bounded.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(bounded.value)
        self.assertEqual(
            discover_link_analysis(self.source, replace(spec, max_work=5)).value.links,
            full.value.links,
        )

    def test_witness_budget_does_not_hide_missing_provenance(self):
        spec = LinkAnalysisSpec(keep_first_occurrence=True, propagate=True)
        result = discover_link_analysis(
            self.source, replace(spec, max_witness_events=6)
        )
        self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
        self.assertIsNone(result.value)
        self.assertEqual(result.issues[0].at, ("max_witness_events",))
        self.assertEqual(
            discover_link_analysis(
                self.source, replace(spec, max_witness_events=7)
            ).value.witness_event_count,
            7,
        )

    def test_empty_log_and_no_matching_keys_are_computed(self):
        empty = discover_link_analysis(CaseLog())
        self.assertEqual(empty.status, ComputeStatus.COMPUTED)
        self.assertEqual(empty.value.events, ())
        self.assertEqual(empty.value.links, ())
        self.assertEqual(empty.value.work_count, 0)
        isolated = discover_link_analysis(
            log([event("a", "x", "y")]), LinkAnalysisSpec(propagate=True)
        )
        self.assertEqual(isolated.status, ComputeStatus.COMPUTED)
        self.assertEqual(isolated.value.links, ())

    def test_frozen_contract_and_result_codec_round_trip(self):
        spec = LinkAnalysisSpec(propagate=True)
        result = discover_link_analysis(self.source, spec)
        self.assertEqual(result.source_digest, case_log_digest(self.source))
        self.assertEqual(result, discover_link_analysis(self.source, spec))
        self.assertEqual(
            RESULT_SCHEMAS[OPERATOR_ID],
            ("case_link_analysis", LinkAnalysisSpec, LinkAnalysisPayload),
        )
        for value in (spec, result.value):
            serialized = json.loads(json.dumps(_encode(value), allow_nan=False))
            self.assertEqual(_decode(serialized, type(value)), value)
        with self.assertRaises(FrozenInstanceError):
            result.value.links = ()
        with self.assertRaises(FrozenInstanceError):
            spec.propagate = False

    def test_invalid_spec_and_input_types(self):
        for name in ("max_events", "max_links", "max_work", "max_witness_events"):
            for value in (0, -1, True, 1.5):
                with self.assertRaises(ValueError):
                    LinkAnalysisSpec(**{name: value})
        for name in ("look_forward", "keep_first_occurrence", "propagate"):
            with self.assertRaises(TypeError):
                LinkAnalysisSpec(**{name: 1})
        for name in ("out_key", "in_key", "timestamp_key"):
            with self.assertRaises(ValueError):
                LinkAnalysisSpec(**{name: " "})
        for name in ("out_scope", "in_scope"):
            with self.assertRaises(ValueError):
                LinkAnalysisSpec(**{name: "automatic"})
        with self.assertRaises(TypeError):
            discover_link_analysis([])
        with self.assertRaises(TypeError):
            discover_link_analysis(CaseLog(), object())


class IndependentClosureOracleTests(unittest.TestCase):
    def test_all_three_event_binary_key_logs_against_floyd_warshall(self):
        # 64 key assignments x 8 options. Dense matrix min-plus closure is
        # independent of the implementation's keyed join and BFS traversal.
        n = 3
        for keys in product(("x", "y"), repeat=2 * n):
            source = log(
                [event(str(i), keys[2 * i], keys[2 * i + 1]) for i in range(n)]
            )
            for forward, first, propagate in product((False, True), repeat=3):
                with self.subTest(
                    keys=keys, forward=forward, first=first, propagate=propagate
                ):
                    direct = set()
                    for i in range(n):
                        targets = [
                            j
                            for j in range(n)
                            if keys[2 * i + 1] == keys[2 * j] and (not forward or i < j)
                        ]
                        direct.update(
                            (i, j) for j in (targets[:1] if first else targets)
                        )
                    distance = [
                        [1 if (i, j) in direct else 1000 for j in range(n)]
                        for i in range(n)
                    ]
                    if propagate:
                        for k in range(n):
                            for i in range(n):
                                for j in range(n):
                                    distance[i][j] = min(
                                        distance[i][j], distance[i][k] + distance[k][j]
                                    )
                    expected = {
                        (i, j)
                        for i in range(n)
                        for j in range(n)
                        if distance[i][j] < 1000
                    }
                    result = discover_link_analysis(
                        source,
                        LinkAnalysisSpec(
                            look_forward=forward,
                            keep_first_occurrence=first,
                            propagate=propagate,
                        ),
                    )
                    self.assertEqual(result.status, ComputeStatus.COMPUTED)
                    self.assertEqual(
                        {(e.source_order, e.target_order) for e in result.value.links},
                        expected,
                    )
                    self.assertEqual(result.value.direct_link_count, len(direct))
                    self.assertEqual(
                        result.value.witness_event_count,
                        sum(len(e.path_orders) for e in result.value.links),
                    )
                    for edge in result.value.links:
                        self.assertEqual(edge.path_orders[0], edge.source_order)
                        self.assertEqual(edge.path_orders[-1], edge.target_order)
                        self.assertEqual(
                            len(edge.path_orders) - 1,
                            distance[edge.source_order][edge.target_order],
                        )
                        self.assertEqual(
                            edge.direct,
                            (edge.source_order, edge.target_order) in direct,
                        )
                        self.assertTrue(
                            all(
                                pair in direct
                                for pair in zip(edge.path_orders, edge.path_orders[1:])
                            )
                        )


if __name__ == "__main__":
    unittest.main()
