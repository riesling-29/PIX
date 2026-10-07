"""Native transformation lineage, populations and raw-fact preservation."""

import json
import math
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pix.case_centric.interleavings import CaseLink
from pix.case_centric.transformations import (
    BoundarySpec,
    CaseGraphSpec,
    CaseMergeSpec,
    CaseSortSpec,
    case_log_to_graph,
    insert_case_boundaries,
    materialize_case_boundaries,
    materialize_case_sort,
    materialize_merged_cases,
    merge_linked_cases,
    sort_case_log,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseSource,
    CaseTrace,
)
from pix.results import _decode, _encode, result_from_json, result_json_bytes

NOW = datetime(2026, 9, 15, tzinfo=timezone.utc)


def event(identity, time=None, activity="a", attributes=()):
    attrs = [CaseAttribute("concept:name", "string", activity)]
    if time is not None:
        attrs.append(
            CaseAttribute("time:timestamp", "date", NOW + timedelta(seconds=time))
        )
    return CaseEvent(identity, tuple(attrs) + attributes)


def source(*traces):
    return CaseLog(
        tuple(CaseTrace(str(i), tuple(events)) for i, events in enumerate(traces))
    )


class CaseSortTests(unittest.TestCase):
    def test_timestamp_sort_and_case_sort_preserve_empty_source_facts(self):
        log = source([event("b", 2), event("a", 1)], [], [event("c", 0)])
        log = replace(
            log,
            metadata=(("x", "raw"),),
            source=CaseSource("original.xes", "xes", "0" * 64, 20),
        )
        plan = sort_case_log(log, CaseSortSpec(case_order="first_event"))
        self.assertEqual([c.source_case_id for c in plan.value.cases], ["2", "0", "1"])
        self.assertEqual(plan.value.cases[1].source_positions, (1, 0))
        output = materialize_case_sort(log, plan)
        self.assertEqual([e.id for e in output.traces[1].events], ["a", "b"])
        self.assertIs(output.traces[1].events[0], log.traces[0].events[1])
        self.assertEqual(output.metadata, log.metadata)
        self.assertEqual(output.source, log.source)
        self.assertEqual([e.id for e in log.traces[0].events], ["b", "a"])

    def test_tie_policies_and_reverse_leave_null_placement_explicit(self):
        log = source([event("z", 1), event("a", 1), event("missing"), event("last", 2)])
        self.assertEqual(sort_case_log(log).status, ComputeStatus.UNAVAILABLE)
        stable = sort_case_log(log, CaseSortSpec(nulls="first", reverse=True))
        self.assertEqual(stable.value.cases[0].event_ids, ("missing", "last", "z", "a"))
        self.assertEqual(stable.status, ComputeStatus.PARTIAL)
        by_id = sort_case_log(log, CaseSortSpec(nulls="last", ties="id", reverse=True))
        self.assertEqual(by_id.value.cases[0].event_ids, ("last", "a", "z", "missing"))
        self.assertEqual(by_id.value.ties[0].ids, ("z", "a"))
        self.assertEqual(
            sort_case_log(log, CaseSortSpec(nulls="last", ties="reject")).status,
            ComputeStatus.UNAVAILABLE,
        )

    def test_numeric_sort_does_not_coerce_nan_or_boolean_and_preserves_large_int(self):
        values = [
            CaseAttribute("n", "float", float("nan")),
            CaseAttribute("n", "int", 2**200),
            CaseAttribute("n", "boolean", True),
            CaseAttribute("n", "float", 2.5),
            CaseAttribute("n", "int", 2),
        ]
        log = source(
            [event(str(i), attributes=(value,)) for i, value in enumerate(values)]
        )
        plan = sort_case_log(
            log, CaseSortSpec(key="n", key_type="number", nulls="last")
        )
        self.assertEqual(plan.value.cases[0].event_ids, ("4", "3", "1", "0", "2"))
        self.assertEqual(plan.value.unavailable_key_event_ids, ("0", "2"))
        materialized = materialize_case_sort(log, plan)
        self.assertTrue(
            math.isnan(materialized.traces[0].events[3].attribute("n").value)
        )

    def test_global_timestamps_and_timezone_conversion(self):
        globals_ = (
            CaseGlobal("event", (CaseAttribute("time:timestamp", "date", NOW),)),
        )
        later = CaseEvent(
            "late",
            (
                CaseAttribute(
                    "time:timestamp",
                    "date",
                    (NOW + timedelta(seconds=1)).astimezone(
                        timezone(timedelta(hours=9))
                    ),
                ),
            ),
        )
        log = replace(source([later, event("default")]), globals=globals_)
        plan = sort_case_log(log)
        self.assertEqual(plan.value.cases[0].event_ids, ("default", "late"))
        self.assertEqual(materialize_case_sort(log, plan).globals, globals_)

    def test_forged_plan_or_changed_source_cannot_materialize(self):
        log = source([event("b", 2), event("a", 1)])
        plan = sort_case_log(log)
        row = replace(
            plan.value.cases[0], event_ids=("b", "a"), source_positions=(0, 1)
        )
        with self.assertRaises(ValueError):
            materialize_case_sort(
                log, replace(plan, value=replace(plan.value, cases=(row,)))
            )
        with self.assertRaises(ValueError):
            materialize_case_sort(source([event("b", 0), event("a", 1)]), plan)


class CaseGraphTests(unittest.TestCase):
    def test_typed_nodes_do_not_collide_and_parallel_attribute_relations_survive(self):
        attrs = (
            CaseAttribute("resource", "string", "x"),
            CaseAttribute("alias", "string", "x"),
            CaseAttribute("number", "int", 1),
            CaseAttribute("flag", "boolean", True),
        )
        log = CaseLog(
            (
                CaseTrace(
                    "x",
                    (event("x", attributes=attrs), event("other")),
                    attributes=(CaseAttribute("resource", "string", "x"),),
                ),
            )
        )
        spec = CaseGraphSpec(
            event_attribute_nodes=("resource", "alias", "number", "flag"),
            case_attribute_nodes=("resource",),
            attribute_identity="value",
        )
        result = case_log_to_graph(log, spec)
        nodes = result.value.nodes
        self.assertEqual(len({node.id for node in nodes}), len(nodes))
        self.assertEqual(sum(n.kind == "attribute" for n in nodes), 3)
        self.assertEqual(sum(e.kind == "attribute" for e in result.value.edges), 5)
        self.assertEqual(
            sum(e.kind == "directly_follows" for e in result.value.edges), 1
        )
        self.assertEqual(sum(e.kind == "belongs_to" for e in result.value.edges), 2)

    def test_same_key_value_grouping_preserves_lexical_facts_on_owners(self):
        a = CaseAttribute("n", "int", 2, lexical="02")
        b = CaseAttribute("n", "int", 2, lexical="2")
        log = source([event("1", attributes=(a,)), event("2", attributes=(b,))])
        result = case_log_to_graph(log, CaseGraphSpec(event_attribute_nodes=("n",)))
        self.assertEqual(sum(n.kind == "attribute" for n in result.value.nodes), 1)
        props = [
            p.fact_encoding
            for n in result.value.nodes
            if n.kind == "event"
            for p in n.properties
            if p.key == "n"
        ]
        self.assertNotEqual(*props)
        self.assertIn('"02"', props[0])

    def test_nested_and_nonfinite_facts_are_encoded_without_json_nan(self):
        nested = CaseAttribute(
            "nested",
            "list",
            values=(CaseAttribute("x", "float", float("inf"), lexical="INF"),),
        )
        log = source(
            [
                event(
                    "1",
                    attributes=(nested, CaseAttribute("nan", "float", float("nan"))),
                )
            ]
        )
        result = case_log_to_graph(
            log, CaseGraphSpec(event_attribute_nodes=("nested", "nan"))
        )
        data = json.dumps(_encode(result.value), allow_nan=False)
        self.assertIn("inf", data)
        self.assertIn("nan", data)
        self.assertEqual(
            _decode(_encode(result.value), type(result.value)), result.value
        )

    def test_graph_bounds_fail_without_partial_graph(self):
        log = source([event("1"), event("2")])
        for spec in (CaseGraphSpec(max_nodes=2), CaseGraphSpec(max_edges=1)):
            result = case_log_to_graph(log, spec)
            self.assertEqual(result.status, ComputeStatus.UNAVAILABLE)
            self.assertIsNone(result.value)


class BoundaryTests(unittest.TestCase):
    def test_missing_endpoints_do_not_substitute_interior_timestamps(self):
        log = source([event("first"), event("middle", 2), event("last")])
        plan = insert_case_boundaries(
            log, BoundarySpec(timestamp_policy="endpoint", missing_timestamp="omit")
        )
        self.assertIsNone(plan.value.cases[0].start.timestamp)
        self.assertIsNone(plan.value.cases[0].end.timestamp)
        self.assertEqual(
            plan.value.unavailable_boundary_times, (("0", "start"), ("0", "end"))
        )

    def test_boundaries_are_distinct_synthetic_facts_and_keep_original_events(self):
        log = source([event("1", 2), event("2", 1)], [])
        plan = insert_case_boundaries(log)
        self.assertEqual(plan.value.synthetic_event_count, 4)
        self.assertEqual(plan.value.original_event_count, 2)
        materialized = materialize_case_boundaries(log, plan)
        self.assertEqual([len(t.events) for t in materialized.traces], [4, 2])
        self.assertIs(materialized.traces[0].events[1], log.traces[0].events[0])
        self.assertEqual(
            materialized.traces[0].events[0].attribute("pix:synthetic").value,
            "boundary:start",
        )
        self.assertIsNone(materialized.traces[0].events[0].timestamp)
        ids = [e.id for trace in materialized.traces for e in trace.events]
        self.assertEqual(len(ids), len(set(ids)))

    def test_synthetic_events_do_not_inherit_resource_or_time_globals(self):
        defaults = (
            CaseAttribute("org:resource", "string", "actual_worker"),
            CaseAttribute("time:timestamp", "date", NOW),
            CaseAttribute("pix:synthetic", "string", "old"),
        )
        log = replace(source([event("1")]), globals=(CaseGlobal("event", defaults),))
        output = materialize_case_boundaries(log, insert_case_boundaries(log))
        synthetic = output.traces[0].events[0]
        self.assertEqual(output.attribute(synthetic, "org:resource").type, "null")
        self.assertEqual(output.attribute(synthetic, "time:timestamp").type, "null")
        self.assertEqual(
            output.attribute(synthetic, "pix:synthetic").value, "boundary:start"
        )
        self.assertEqual(
            output.attribute(output.traces[0].events[1], "org:resource").value,
            "actual_worker",
        )
        self.assertEqual(output.globals, log.globals)

    def test_outside_timestamp_uses_first_last_source_endpoints(self):
        log = source([event("first", 20), event("last", 10)])
        plan = insert_case_boundaries(
            log, BoundarySpec(timestamp_policy="outside", offset_microseconds=2000000)
        )
        self.assertEqual(
            plan.value.cases[0].start.timestamp, NOW + timedelta(seconds=18)
        )
        self.assertEqual(plan.value.cases[0].end.timestamp, NOW + timedelta(seconds=12))

    def test_empty_timestamp_collision_and_overflow_policies(self):
        self.assertEqual(
            insert_case_boundaries(
                source([]), BoundarySpec(timestamp_policy="endpoint")
            ).status,
            ComputeStatus.UNAVAILABLE,
        )
        omitted = insert_case_boundaries(
            source([]),
            BoundarySpec(timestamp_policy="outside", missing_timestamp="omit"),
        )
        self.assertEqual(omitted.status, ComputeStatus.PARTIAL)
        self.assertEqual(
            omitted.value.unavailable_boundary_times, (("0", "start"), ("0", "end"))
        )
        self.assertEqual(
            insert_case_boundaries(
                source([]), BoundarySpec(empty_cases="preserve")
            ).value.synthetic_event_count,
            0,
        )
        log = source([event("1", activity="__PIX_START__")])
        self.assertEqual(
            insert_case_boundaries(log).status, ComputeStatus.INVALID_INPUT
        )
        self.assertEqual(
            insert_case_boundaries(
                log, BoundarySpec(activity_collision="allow")
            ).value.colliding_activity_event_ids,
            ("1",),
        )
        minimum = CaseEvent(
            "min",
            (
                CaseAttribute(
                    "time:timestamp", "date", datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
        )
        self.assertEqual(
            insert_case_boundaries(
                source([minimum]), BoundarySpec(timestamp_policy="outside")
            ).status,
            ComputeStatus.UNAVAILABLE,
        )

    def test_forged_synthetic_label_and_request_are_rejected(self):
        log = source([event("1")])
        plan = insert_case_boundaries(log)
        row = plan.value.cases[0]
        forged = replace(
            plan,
            value=replace(
                plan.value,
                cases=(replace(row, start=replace(row.start, activity="forged")),),
            ),
        )
        with self.assertRaises(ValueError):
            materialize_case_boundaries(log, forged)
        with self.assertRaises(ValueError):
            materialize_case_boundaries(
                log, replace(plan, spec=replace(plan.spec, start_activity="different"))
            )


class MergeTests(unittest.TestCase):
    def test_identity_tie_order_uses_original_ids_independently_of_resource_budget(
        self,
    ):
        left, right = source([event("z", 1), event("a", 1)]), source([event("b", 1)])
        spec = CaseMergeSpec(case_links=(CaseLink("0", "0"),), ties="id")
        for current in (spec, replace(spec, max_output_events=3)):
            plan = merge_linked_cases(left, right, current)
            self.assertEqual(
                [
                    (e.source_side, e.source_event_id)
                    for e in plan.value.cases[0].events
                ],
                [("left", "a"), ("left", "z"), ("right", "b")],
            )

    def test_many_to_many_relation_counts_and_event_identity_lineage(self):
        left = source([event("shared_id", 1)], [event("second", 5)], [])
        right = source([event("shared_id", 2), event("r2", 4)], [event("unlinked", 3)])
        spec = CaseMergeSpec(case_links=(CaseLink("0", "0"), CaseLink("1", "0")))
        plan = merge_linked_cases(left, right, spec)
        self.assertEqual(plan.value.output_event_count, 6)
        self.assertEqual(plan.value.unique_source_event_count, 4)
        self.assertEqual(plan.value.duplicated_occurrence_count, 2)
        self.assertEqual(plan.value.excluded_right_case_ids, ("1",))
        self.assertEqual(
            [(e.source_side, e.source_event_id) for e in plan.value.cases[1].events],
            [("right", "shared_id"), ("right", "r2"), ("left", "second")],
        )
        output = materialize_merged_cases(left, right, plan)
        ids = [e.id for trace in output.log.traces for e in trace.events]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIs(output.left_source, left)
        self.assertIs(output.right_source, right)
        self.assertEqual(len(output.log.traces), 3)

    def test_duplicate_relation_rows_are_explicit_occurrences(self):
        link = CaseLink("0", "0")
        with self.assertRaises(ValueError):
            CaseMergeSpec(case_links=(link, link))
        left, right = source([]), source([event("r", 1)])
        plan = merge_linked_cases(
            left,
            right,
            CaseMergeSpec(case_links=(link, link), duplicate_links="repeat"),
        )
        self.assertEqual(plan.value.output_event_count, 2)
        self.assertEqual(plan.value.duplicated_occurrence_count, 1)
        self.assertEqual([e.relation_index for e in plan.value.cases[0].events], [0, 1])

    def test_unlinked_right_retention_and_bounds(self):
        left, right = source([]), source([event("1", 0)], [event("2", 1)])
        spec = CaseMergeSpec(unlinked_right="retain")
        self.assertEqual(len(merge_linked_cases(left, right, spec).value.cases), 3)
        self.assertEqual(
            merge_linked_cases(left, right, replace(spec, max_output_cases=2)).status,
            ComputeStatus.UNAVAILABLE,
        )
        self.assertEqual(
            merge_linked_cases(left, right, replace(spec, max_output_events=1)).status,
            ComputeStatus.UNAVAILABLE,
        )
        invalid = merge_linked_cases(
            left, right, CaseMergeSpec(case_links=(CaseLink("missing", "0"),))
        )
        self.assertEqual(invalid.status, ComputeStatus.INVALID_INPUT)

    def test_conflicting_globals_raw_nonfinite_and_case_metadata_preserved_separately(
        self,
    ):
        lexical = CaseAttribute("cost", "float", float("nan"), lexical="NaN")
        left = replace(
            source([event("l", attributes=(lexical,))]),
            globals=(
                CaseGlobal(
                    "event",
                    (
                        CaseAttribute("org:resource", "string", "left"),
                        CaseAttribute("left_only", "int", 9),
                    ),
                ),
            ),
            metadata=(("owner", "left"),),
            classifiers=(CaseClassifier("activity", ("concept:name",)),),
        )
        right = replace(
            source([event("r")]),
            globals=(
                CaseGlobal(
                    "event", (CaseAttribute("org:resource", "string", "right"),)
                ),
            ),
            metadata=(("owner", "right"),),
            classifiers=(CaseClassifier("activity", ("concept:name",)),),
        )
        plan = merge_linked_cases(
            left, right, CaseMergeSpec(case_links=(CaseLink("0", "0"),), order="source")
        )
        output = materialize_merged_cases(left, right, plan)
        a, b = output.log.traces[0].events
        self.assertEqual(a.attribute("org:resource").value, "left")
        self.assertEqual(b.attribute("org:resource").value, "right")
        self.assertIsNone(output.log.attribute(b, "left_only"))
        self.assertIs(a.attribute("cost"), lexical)
        self.assertTrue(math.isnan(a.attribute("cost").value))
        self.assertEqual(output.log.globals, ())
        self.assertEqual(
            [c.name for c in output.log.classifiers],
            ["left:activity", "right:activity"],
        )
        self.assertEqual(output.right_source.globals, right.globals)
        self.assertIn(("right:owner", "right"), output.log.metadata)

    def test_missing_timestamp_and_tie_policies(self):
        left, right = source([event("l", 1)]), source([event("r")])
        spec = CaseMergeSpec(case_links=(CaseLink("0", "0"),))
        self.assertEqual(
            merge_linked_cases(left, right, spec).status, ComputeStatus.UNAVAILABLE
        )
        placed = merge_linked_cases(left, right, replace(spec, nulls="first"))
        self.assertEqual(placed.status, ComputeStatus.PARTIAL)
        self.assertEqual(placed.value.cases[0].events[0].source_side, "right")
        tied = source([event("r", 1)])
        self.assertEqual(
            merge_linked_cases(left, tied, replace(spec, ties="reject")).status,
            ComputeStatus.UNAVAILABLE,
        )

    def test_materialization_rejects_forged_occurrence_and_changed_right_source(self):
        left, right = source([event("l", 1)]), source([event("r", 2)])
        plan = merge_linked_cases(
            left, right, CaseMergeSpec(case_links=(CaseLink("0", "0"),))
        )
        row = plan.value.cases[0]
        forged = replace(
            plan,
            value=replace(
                plan.value, cases=(replace(row, events=tuple(reversed(row.events))),)
            ),
        )
        with self.assertRaises(ValueError):
            materialize_merged_cases(left, right, forged)
        with self.assertRaises(ValueError):
            materialize_merged_cases(left, source([event("r", 3)]), plan)


class TransformationContractTests(unittest.TestCase):
    def test_all_specs_and_payloads_typed_roundtrip(self):
        log = source([event("1", 1), event("2", 2)])
        results = (
            sort_case_log(log),
            case_log_to_graph(log),
            insert_case_boundaries(log),
            merge_linked_cases(
                log, log, CaseMergeSpec(case_links=(CaseLink("0", "0"),))
            ),
        )
        for result in results:
            self.assertEqual(
                _decode(_encode(result.spec), type(result.spec)), result.spec
            )
            self.assertEqual(
                _decode(_encode(result.value), type(result.value)), result.value
            )
            self.assertEqual(result_from_json(result_json_bytes(result)), result)

    def test_python_equal_but_differently_typed_forgery_is_rejected(self):
        log = source([event("1", 1)])
        sort_plan = sort_case_log(log)
        with self.assertRaises(ValueError):
            materialize_case_sort(
                log,
                replace(sort_plan, value=replace(sort_plan.value, event_count=True)),
            )
        boundary_plan = insert_case_boundaries(log)
        with self.assertRaises(ValueError):
            materialize_case_boundaries(
                log,
                replace(
                    boundary_plan,
                    value=replace(boundary_plan.value, original_event_count=True),
                ),
            )
        merge_plan = merge_linked_cases(log, source(), CaseMergeSpec())
        with self.assertRaises(ValueError):
            materialize_merged_cases(
                log,
                source(),
                replace(
                    merge_plan, value=replace(merge_plan.value, output_event_count=1.0)
                ),
            )

    def test_ambiguous_attribute_is_not_arbitrarily_selected(self):
        bad = CaseEvent(
            "bad",
            (
                CaseAttribute("time:timestamp", "date", NOW),
                CaseAttribute("time:timestamp", "date", NOW),
            ),
        )
        log = source([bad])
        for result in (
            sort_case_log(log),
            case_log_to_graph(log),
            insert_case_boundaries(log),
            merge_linked_cases(log, source(), CaseMergeSpec()),
        ):
            self.assertEqual(result.status, ComputeStatus.INVALID_INPUT)


if __name__ == "__main__":
    unittest.main()
