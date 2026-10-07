"""Clock, graph, and exhaustive-small scheduling oracles for action analysis."""

import unittest
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import combinations, permutations, product

from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputeStatus
from pix.object_centric.actions import (
    ALLEN_RELATIONS,
    ActionCandidate,
    ActionCandidateSpec,
    ActionConfiguration,
    ActionConfigurationSpec,
    ActionPattern,
    ActionRule,
    ActionRuleAssignment,
    ActionScheduleSpec,
    ActionWindow,
    ActionWindowSpec,
    ConstraintInterval,
    StructuralActionImpactSpec,
    TemporalPredicate,
    allen_relation,
    compare_action_windows,
    propose_actions,
    schedule_actions,
    structural_action_impact,
    update_action_configuration,
)
from pix.object_centric.performance import OCPerformanceSpec
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
from pix.results import result_from_json, result_json_bytes

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def at(value):
    return BASE + timedelta(microseconds=value)


def interval(a, b, identity="i", label="fault", objects=()):
    return ConstraintInterval(identity, label, at(a), at(b), objects)


def candidate(name, duration, release=None, deadline=None, priority=0):
    return ActionCandidate(
        name,
        duration,
        None if release is None else at(release),
        None if deadline is None else at(deadline),
        priority,
    )


def schedule(values, **kwargs):
    return schedule_actions(tuple(values), ActionScheduleSpec(BASE, **kwargs))


def chain_model():
    return ObjectCentricPetriNet(
        tuple(TypedPlace(f"p{i}", "order") for i in range(4))
        + (TypedPlace("x", "item"),),
        (Transition("a", "start"), Transition("tau"), Transition("b", "finish")),
        (
            ObjectArc("p0", "a"),
            ObjectArc("a", "p1"),
            ObjectArc("p1", "tau"),
            ObjectArc("tau", "p2"),
            ObjectArc("p2", "b"),
            ObjectArc("b", "p3"),
            ObjectArc("x", "b"),
        ),
        ObjectMarking((ObjectToken("p0", "o"), ObjectToken("x", "i"))),
        ObjectMarking((ObjectToken("p3", "o"),)),
        (("o", "order"), ("i", "item")),
    )


def log_fixture(missing=False):
    # service before=[3,5], after=[1,2,3], so mean delta = 2-4 = -2.
    observations = (
        ("r0", 4, 1),
        ("r1", 8, 3),
        ("c0", 11, 10),
        ("c1", 14, 12),
        ("c2", 18, 15),
    )
    return OCEL(
        event_types=(EventType("work", (Attribute("start", ValueType.TIME),)),),
        object_types=(ObjectType("order"),),
        events=tuple(
            Event(
                i,
                "work",
                at(end),
                () if missing and i == "c0" else (EventAttr("start", at(start)),),
            )
            for i, end, start in observations
        ),
        objects=(Object("o", "order"),),
        e2o=tuple(E2O(i, "o", "flow") for i, _, _ in observations),
    )


class AllenTests(unittest.TestCase):
    def test_all_thirteen_relations_and_converses(self):
        a = interval(2, 5)
        examples = {
            "before": (6, 8),
            "after": (0, 1),
            "meets": (5, 8),
            "met_by": (0, 2),
            "overlaps": (3, 8),
            "overlapped_by": (0, 4),
            "starts": (2, 8),
            "started_by": (2, 4),
            "during": (0, 8),
            "contains": (3, 4),
            "finishes": (0, 5),
            "finished_by": (3, 5),
            "equal": (2, 5),
        }
        self.assertEqual(set(examples), set(ALLEN_RELATIONS))
        for relation, (start, end) in examples.items():
            with self.subTest(relation=relation):
                self.assertEqual(allen_relation(a, interval(start, end)), relation)

    def test_independent_endpoint_order_oracle_partitions_finite_domain(self):
        # Strict endpoint predicates are checked independently over all 225 pairs.
        segments = tuple(combinations(range(6), 2))
        for (a, b), (c, d) in product(segments, repeat=2):
            truth = {
                "before": b < c,
                "after": d < a,
                "meets": b == c,
                "met_by": d == a,
                "overlaps": a < c < b < d,
                "overlapped_by": c < a < d < b,
                "starts": a == c and b < d,
                "started_by": a == c and b > d,
                "during": c < a < b < d,
                "contains": a < c < d < b,
                "finishes": c < a and b == d,
                "finished_by": a < c and b == d,
                "equal": a == c and b == d,
            }
            expected = [name for name, holds in truth.items() if holds]
            self.assertEqual(len(expected), 1)
            self.assertEqual(
                allen_relation(interval(a, b), interval(c, d)), expected[0]
            )

    def test_reject_points_and_naive_timestamps(self):
        for start, end in (
            (at(1), at(1)),
            (at(2), at(1)),
            (datetime(2026, 1, 1), at(2)),
        ):
            with self.assertRaises(ValueError):
                ConstraintInterval("i", "f", start, end)

    def test_timezone_offsets_normalize_before_comparison_and_identity(self):
        offset = timezone(timedelta(hours=9))
        utc = interval(1, 3)
        local = replace(
            utc, start=utc.start.astimezone(offset), end=utc.end.astimezone(offset)
        )
        self.assertEqual(utc, local)
        self.assertIs(local.start.tzinfo, timezone.utc)
        spec = ActionCandidateSpec(
            (ActionPattern("p", "repair", 1, (("a", "fault"),)),)
        )
        self.assertEqual(
            propose_actions((utc,), spec).computation_id,
            propose_actions((local,), spec).computation_id,
        )


class CandidateTests(unittest.TestCase):
    def rule(self, relation="before", **kwargs):
        return ActionPattern(
            "p",
            "repair",
            4,
            (("a", "fault"), ("b", "alert")),
            (TemporalPredicate(("a",), relation, ("b",)),),
            **kwargs,
        )

    def test_candidate_retains_witness_and_release(self):
        data = (interval(0, 2, "f"), interval(3, 5, "a", "alert"))
        result = propose_actions(data, ActionCandidateSpec((self.rule(),)))
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.matches[0].mapping, (("a", "f"), ("b", "a")))
        self.assertEqual(result.value.candidates[0].release_time, at(5))
        self.assertTrue(result.value.no_action_available)
        self.assertEqual(
            result,
            propose_actions(tuple(reversed(data)), ActionCandidateSpec((self.rule(),))),
        )

    def test_no_match_and_empty_population_are_explicit(self):
        for data in ((), (interval(0, 2, "f"), interval(2, 4, "a", "alert"))):
            result = propose_actions(data, ActionCandidateSpec((self.rule(),)))
            self.assertEqual(result.value.candidates, ())
            self.assertEqual(result.value.matches[0].outcome, "no_match")
            self.assertTrue(result.value.matching_complete)

    def test_search_limit_does_not_prove_false_and_exact_bound_is_complete(self):
        data = (
            interval(9, 10, "f0"),
            interval(0, 1, "f1"),
            interval(2, 3, "a", "alert"),
        )
        limited = propose_actions(
            data, ActionCandidateSpec((self.rule(),), max_mappings_per_pattern=1)
        )
        self.assertIs(limited.status, ComputeStatus.PARTIAL)
        self.assertEqual(limited.value.matches[0].outcome, "search_limit")
        complete = propose_actions(
            data, ActionCandidateSpec((self.rule(),), max_mappings_per_pattern=2)
        )
        self.assertEqual(complete.value.matches[0].outcome, "matched")
        no_match = propose_actions(
            data[:1] + data[2:],
            ActionCandidateSpec((self.rule(),), max_mappings_per_pattern=1),
        )
        self.assertEqual(no_match.value.matches[0].outcome, "no_match")

    def test_slot_reuse_is_explicit_and_shared_object_is_not_assumed(self):
        rule = ActionPattern(
            "p",
            "repair",
            2,
            (("a", "fault"), ("b", "fault")),
            (TemporalPredicate(("a",), "equal", ("b",)),),
        )
        data = (interval(0, 1),)
        self.assertFalse(
            propose_actions(data, ActionCandidateSpec((rule,))).value.candidates
        )
        self.assertTrue(
            propose_actions(
                data, ActionCandidateSpec((rule,), allow_interval_reuse=True)
            ).value.candidates
        )
        shared_rule = self.rule(require_shared_object=True)
        data = (
            interval(0, 1, "f", objects=("o",)),
            interval(2, 3, "a", "alert", ("i",)),
        )
        self.assertFalse(
            propose_actions(data, ActionCandidateSpec((shared_rule,))).value.candidates
        )
        data = (data[0], replace(data[1], object_ids=("o", "i")))
        self.assertEqual(
            propose_actions(data, ActionCandidateSpec((shared_rule,)))
            .value.matches[0]
            .shared_object_ids,
            ("o",),
        )

    def test_nested_hull_and_action_deduplication(self):
        rule = ActionPattern(
            "p",
            "fix",
            2,
            (("a", "a"), ("b", "b"), ("c", "c")),
            (
                TemporalPredicate(("a",), "before", ("b",)),
                TemporalPredicate(("a", "b"), "overlaps", ("c",)),
            ),
        )
        rule2 = ActionPattern("q", "fix", 7, (("c", "c"),))
        data = (
            interval(0, 1, "a", "a"),
            interval(4, 6, "b", "b"),
            interval(3, 8, "c", "c"),
        )
        result = propose_actions(data, ActionCandidateSpec((rule, rule2))).value
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(
            (result.candidates[0].duration_us, result.candidates[0].release_time),
            (7, at(8)),
        )
        self.assertEqual(result.candidates[0].pattern_ids, ("p", "q"))


class ScheduleTests(unittest.TestCase):
    def test_critical_path_and_parallel_ready_actions(self):
        result = schedule(
            (
                candidate("a", 3),
                candidate("b", 5),
                candidate("c", 2),
                candidate("d", 1),
            ),
            precedence=(("a", "c"), ("b", "c"), ("c", "d")),
        ).value
        # Independent path sums: a-c-d=6; b-c-d=8.
        self.assertEqual(result.makespan_us, max(3 + 2 + 1, 5 + 2 + 1))
        rows = {row.action_id: row for row in result.actions}
        self.assertEqual((rows["a"].start, rows["b"].start), (BASE, BASE))
        self.assertEqual((rows["c"].start, rows["d"].start), (at(5), at(7)))
        self.assertEqual((result.total_waiting_us, result.total_flow_us), (12, 23))
        self.assertEqual(result.outcome, "feasible")
        self.assertEqual(result.optimality, "not_assessed")

    def test_conflict_nonoverlap_release_and_gap_insertion(self):
        values = (candidate("a", 3, release=7), candidate("b", 2), candidate("c", 6))
        result = schedule(values, conflicts=(("a", "b"), ("b", "c"), ("a", "c"))).value
        rows = {row.action_id: row for row in result.actions}
        self.assertEqual(
            (rows["b"].start, rows["a"].start, rows["c"].start), (at(0), at(7), at(10))
        )
        for left, right in combinations(result.actions, 2):
            self.assertTrue(left.end <= right.start or right.end <= left.start)
        self.assertEqual(rows["a"].waiting_us, 0)
        self.assertEqual(rows["c"].conflict_ids, ("b", "a"))

    def test_empty_and_chosen_no_action_return_without_execution(self):
        self.assertEqual(schedule(()).value.outcome, "no_action")
        result = schedule((candidate("a", 2),), choose_no_action=True).value
        self.assertEqual(result.actions, ())
        self.assertEqual(result.unscheduled, (("a", "no_action_selected"),))
        self.assertTrue(result.no_action_available)

    def test_equal_start_conflict_witness_has_stable_id_tiebreak(self):
        values = (candidate("a", 5), candidate("b", 2), candidate("c", 1))
        for ordering in permutations(values):
            payload = schedule(ordering, conflicts=(("a", "c"), ("b", "c"))).value
            row = next(item for item in payload.actions if item.action_id == "c")
            self.assertEqual((row.start, row.conflict_ids), (at(5), ("a",)))

    def test_cycle_has_actual_witness_and_no_infinite_loop(self):
        result = schedule(
            tuple(candidate(i, 1) for i in "abcd"),
            precedence=(("a", "b"), ("b", "c"), ("c", "a"), ("c", "d")),
        ).value
        self.assertEqual(result.outcome, "infeasible")
        self.assertEqual(result.cycle_witness[0], result.cycle_witness[-1])
        self.assertNotIn("d", result.cycle_witness)
        edges = {("a", "b"), ("b", "c"), ("c", "a")}
        self.assertTrue(
            all(
                edge in edges
                for edge in zip(result.cycle_witness, result.cycle_witness[1:])
            )
        )

    def test_release_deadline_and_self_conflict_prove_infeasibility(self):
        result = schedule(
            (candidate("a", 5, release=3, deadline=7), candidate("b", 1)),
            precedence=(("a", "b"),),
        ).value
        self.assertEqual(result.outcome, "infeasible")
        self.assertEqual(dict(result.unscheduled)["b"], "predecessor_unscheduled")
        self.assertEqual(
            schedule((candidate("a", 1),), conflicts=(("a", "a"),)).value.outcome,
            "infeasible",
        )

    def test_greedy_failure_is_unknown_when_reverse_order_is_feasible(self):
        values = (candidate("a", 5), candidate("b", 1, deadline=2))
        result = schedule(values, conflicts=(("a", "b"),))
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertEqual(result.value.outcome, "heuristic_incomplete")
        # Exhaustive single-machine permutation oracle finds b then a feasible.
        feasible_orders = []
        for order in permutations(values):
            clock, valid = 0, True
            for item in order:
                clock += item.duration_us
                valid &= item.deadline is None or at(clock) <= item.deadline
            if valid:
                feasible_orders.append(tuple(item.action_id for item in order))
        self.assertEqual(feasible_orders, [("b", "a")])
        alternative = schedule(
            (values[0], replace(values[1], priority=1)), conflicts=(("a", "b"),)
        ).value
        self.assertEqual(alternative.outcome, "feasible")

    def test_unknown_relation_endpoints_duplicate_ids_and_invalid_contracts_rejected(
        self,
    ):
        with self.assertRaises(ValueError):
            schedule((candidate("a", 1),), precedence=(("a", "missing"),))
        with self.assertRaises(ValueError):
            schedule((candidate("a", 1), candidate("a", 2)))
        for value in (0, -1, True, 0.5):
            with self.assertRaises((ValueError, TypeError)):
                candidate("a", value)


class StructuralTests(unittest.TestCase):
    def test_typed_reachability_crosses_silent_but_not_other_types(self):
        model = chain_model()
        result = structural_action_impact(
            model, StructuralActionImpactSpec(("b",))
        ).value
        rows = {row.object_type: row for row in result.typed}
        self.assertEqual(result.direct_object_types, ("item", "order"))
        self.assertEqual(rows["order"].prior_transition_ids, ("a",))
        self.assertEqual(rows["item"].prior_transition_ids, ())
        self.assertEqual(rows["order"].posterior_place_ids, ("p3",))
        self.assertIsNone(rows["order"].prior_marked_object_ids)

    def test_supplied_marking_preserves_object_identity_and_unknown_vs_empty(self):
        model = chain_model()
        payload = structural_action_impact(
            model, StructuralActionImpactSpec(("b",), model.initial_marking)
        ).value
        rows = {row.object_type: row for row in payload.typed}
        self.assertEqual(rows["order"].prior_marked_object_ids, ("o",))
        self.assertEqual(rows["item"].prior_marked_object_ids, ("i",))
        self.assertEqual(rows["order"].posterior_marked_object_ids, ())
        with self.assertRaises(ValueError):
            structural_action_impact(model, StructuralActionImpactSpec(("missing",)))

    def test_empty_change_and_cycle_termination(self):
        model = chain_model()
        self.assertEqual(
            structural_action_impact(
                model, StructuralActionImpactSpec(())
            ).value.direct_object_types,
            (),
        )
        cyclic = replace(model, arcs=model.arcs + (ObjectArc("p3", "a"),))
        rows = structural_action_impact(
            cyclic, StructuralActionImpactSpec(("a",))
        ).value.typed
        order = next(row for row in rows if row.object_type == "order")
        self.assertEqual(order.posterior_transition_ids, ("b",))
        self.assertEqual(order.prior_transition_ids, ("b",))


class WindowTests(unittest.TestCase):
    def spec(self, metric="service"):
        return ActionWindowSpec(
            ActionWindow(at(0), at(10)),
            ActionWindow(at(10), at(20)),
            OCPerformanceSpec(metrics=(metric,), start_attribute="start"),
        )

    def test_exact_service_means_and_one_consistent_delta_direction(self):
        result = compare_action_windows(log_fixture(), self.spec())
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        row = result.value.metrics[0]
        self.assertEqual((row.reference_numerator, row.reference_denominator), (4, 1))
        self.assertEqual((row.change_numerator, row.change_denominator), (2, 1))
        self.assertEqual((row.delta_numerator, row.delta_denominator), (-2, 1))
        self.assertEqual(result.value.activity_counts, (("work", 2, 3, 1),))
        self.assertEqual(result.value.object_type_counts, (("order", 1, 1, 0),))
        self.assertEqual(len(result.parent_computation_ids), 1)

    def test_unknown_is_counted_and_not_zero(self):
        result = compare_action_windows(log_fixture(missing=True), self.spec())
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        row = result.value.metrics[0]
        self.assertEqual((row.change_known, row.change_unknown), (2, 1))
        self.assertEqual((row.change_numerator, row.change_denominator), (5, 2))
        self.assertEqual((row.delta_numerator, row.delta_denominator), (-3, 2))

    def test_half_open_windows_and_predecessors_outside_window_are_preserved(self):
        spec = ActionWindowSpec(
            ActionWindow(at(8), at(11)),
            ActionWindow(at(11), at(19)),
            OCPerformanceSpec(metrics=("flow",)),
        )
        result = compare_action_windows(log_fixture(), spec)
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        self.assertEqual(result.value.reference_event_ids, ("r1",))
        self.assertEqual(result.value.change_event_ids, ("c0", "c1", "c2"))
        row = result.value.metrics[0]
        self.assertEqual((row.reference_numerator, row.reference_denominator), (4, 1))
        self.assertEqual((row.change_numerator, row.change_denominator), (10, 3))
        self.assertEqual((row.delta_numerator, row.delta_denominator), (-2, 3))

    def test_empty_known_population_is_unknown_not_zero(self):
        spec = replace(self.spec(), reference=ActionWindow(at(-10), at(-1)))
        result = compare_action_windows(log_fixture(), spec)
        self.assertIs(result.status, ComputeStatus.PARTIAL)
        self.assertIsNone(result.value.metrics[0].delta_numerator)
        self.assertEqual(result.value.metrics[0].reference_known, 0)

    def test_invalid_windows_unavailable_profile_and_non_event_metric(self):
        with self.assertRaises(ValueError):
            replace(self.spec(), change=ActionWindow(at(5), at(15)))
        with self.assertRaises(ValueError):
            replace(
                self.spec(),
                performance=OCPerformanceSpec(
                    metrics=("activity_frequency",), object_type="order"
                ),
            )
        result = compare_action_windows(
            log_fixture(),
            replace(self.spec(), performance=OCPerformanceSpec(profile="opera")),
        )
        self.assertIs(result.status, ComputeStatus.UNAVAILABLE)

    def test_spec_and_payload_immutable_and_identity_tracks_parameter_changes(self):
        first = compare_action_windows(log_fixture(), self.spec())
        second = compare_action_windows(
            log_fixture(), replace(self.spec(), change=ActionWindow(at(10), at(19)))
        )
        self.assertEqual(first.source_digest, second.source_digest)
        self.assertNotEqual(first.computation_id, second.computation_id)
        with self.assertRaises(FrozenInstanceError):
            first.value.interpretation = "causal"


class ConfigurationTests(unittest.TestCase):
    def configuration(self):
        return ActionConfiguration(
            (
                ActionRule("r1", "integrity", "order", "amount > 0"),
                ActionRule("r2", "integrity", "order", "amount > 10"),
                ActionRule("r3", "reaction", "order", "opaque expression"),
            ),
            (
                ActionRuleAssignment("a", "integrity", ("r1",)),
                ActionRuleAssignment("a", "reaction", ("r3",)),
            ),
        )

    def test_replace_not_union_and_leave_other_kinds_untouched(self):
        config = self.configuration()
        result = update_action_configuration(
            chain_model(),
            config,
            ActionConfigurationSpec((ActionRuleAssignment("a", "integrity", ("r2",)),)),
        )
        self.assertIs(result.status, ComputeStatus.COMPUTED)
        assignments = {
            (a.transition_id, a.kind): a.rule_ids
            for a in result.value.configuration.assignments
        }
        self.assertEqual(
            assignments, {("a", "integrity"): ("r2",), ("a", "reaction"): ("r3",)}
        )
        self.assertEqual(config.assignments[0].rule_ids, ("r1",))
        delta = result.value.changes[0]
        self.assertEqual(
            (delta.before_rule_ids, delta.after_rule_ids), (("r1",), ("r2",))
        )
        self.assertEqual(result.value.expression_evaluation, "not_performed")

    def test_empty_assignment_distinct_from_absence_and_repeated_update_idempotent(
        self,
    ):
        config = self.configuration()
        spec = ActionConfigurationSpec((ActionRuleAssignment("b", "integrity", ()),))
        first = update_action_configuration(chain_model(), config, spec).value
        self.assertEqual(
            (first.changes[0].before_rule_ids, first.changes[0].after_rule_ids),
            (None, ()),
        )
        second = update_action_configuration(
            chain_model(), first.configuration, spec
        ).value
        self.assertEqual(second.changes, ())
        self.assertEqual(first.configuration, second.configuration)

    def test_unknown_ids_kind_and_nonincident_object_type_rejected(self):
        config = self.configuration()
        for update in (
            ActionRuleAssignment("missing", "integrity", ("r1",)),
            ActionRuleAssignment("a", "integrity", ("missing",)),
            ActionRuleAssignment("a", "integrity", ("r3",)),
        ):
            with self.assertRaises(ValueError):
                update_action_configuration(
                    chain_model(), config, ActionConfigurationSpec((update,))
                )
        item_rule = ActionConfiguration((ActionRule("item", "integrity", "item", "x"),))
        with self.assertRaises(ValueError):
            update_action_configuration(
                chain_model(),
                item_rule,
                ActionConfigurationSpec(
                    (ActionRuleAssignment("a", "integrity", ("item",)),)
                ),
            )


class ActionPersistenceTests(unittest.TestCase):
    def test_all_five_nonempty_public_result_envelopes_roundtrip(self):
        model = chain_model()
        matched = propose_actions(
            (
                interval(0, 2, "fault", objects=("o",)),
                interval(3, 5, "alert", "alert", ("o",)),
            ),
            ActionCandidateSpec(
                (
                    ActionPattern(
                        "repair_pattern",
                        "repair",
                        4,
                        (("f", "fault"), ("a", "alert")),
                        (TemporalPredicate(("f",), "before", ("a",)),),
                        require_shared_object=True,
                    ),
                )
            ),
        )
        scheduled = schedule_actions(matched.value.candidates, ActionScheduleSpec(BASE))
        structural = structural_action_impact(
            model,
            StructuralActionImpactSpec(("b",), model.initial_marking),
        )
        window = compare_action_windows(
            log_fixture(missing=True),
            ActionWindowSpec(
                ActionWindow(at(0), at(10)),
                ActionWindow(at(10), at(20)),
                OCPerformanceSpec(metrics=("service",), start_attribute="start"),
            ),
        )
        config = ActionConfiguration(
            (
                ActionRule("r1", "integrity", "order", "amount > 0"),
                ActionRule("r2", "integrity", "order", "amount > 10"),
            ),
            (ActionRuleAssignment("a", "integrity", ("r1",)),),
        )
        updated = update_action_configuration(
            model,
            config,
            ActionConfigurationSpec((ActionRuleAssignment("a", "integrity", ("r2",)),)),
        )
        self.assertTrue(matched.value.matches[0].mapping)
        self.assertTrue(scheduled.value.actions)
        self.assertTrue(structural.spec.marking.tokens)
        self.assertIs(window.status, ComputeStatus.PARTIAL)
        self.assertTrue(window.issues)
        self.assertTrue(updated.value.changes)
        self.assertEqual(
            len(
                {
                    result.operator_id
                    for result in (matched, scheduled, structural, window, updated)
                }
            ),
            5,
        )
        for original in (matched, scheduled, structural, window, updated):
            with self.subTest(operator=original.operator_id):
                encoded = result_json_bytes(original)
                restored = result_from_json(encoded)
                self.assertEqual(restored, original)
                self.assertEqual(type(restored.spec), type(original.spec))
                self.assertEqual(type(restored.value), type(original.value))
                self.assertEqual(
                    restored.parent_computation_ids, original.parent_computation_ids
                )
                self.assertEqual(result_json_bytes(restored), encoded)


if __name__ == "__main__":
    unittest.main()
