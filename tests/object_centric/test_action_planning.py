"""Independent time-grid oracles for finite, exact action proposal planning."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import combinations, product

import pytest

from pix.contracts.result import ComputeStatus
from pix.object_centric.action_planning import (
    ActionMatchEnumerationSpec,
    ActionPlanningSpec,
    enumerate_action_matches,
    plan_actions,
)
from pix.object_centric.actions import (
    ActionCandidate,
    ActionCandidateSpec,
    ActionPattern,
    ActionScheduleSpec,
    ConstraintInterval,
    TemporalPredicate,
    propose_actions,
    schedule_actions,
)
from pix.results import result_from_json, result_json_bytes

BASE = datetime(2026, 9, 17, tzinfo=timezone.utc)


def at(microseconds):
    return BASE + timedelta(microseconds=microseconds)


def candidate(identity, duration, *, release=None, deadline=None, priority=0):
    return ActionCandidate(
        identity,
        duration,
        at(release) if release is not None else None,
        at(deadline) if deadline is not None else None,
        priority,
    )


def run(actions, *, required=None, optional=(), **kwargs):
    if required is None:
        required = tuple(a.action_id for a in actions if a.action_id not in optional)
    horizon = kwargs.pop("horizon_us", 20)
    return plan_actions(
        actions, ActionPlanningSpec(BASE, horizon, required, optional, **kwargs)
    )


def timing(witness):
    return {row.action_id: (row.start, row.end) for row in witness.actions}


def interval(identity, label, start, end, objects=("order",)):
    return ConstraintInterval(identity, label, at(start), at(end), objects)


def test_enumeration_retains_every_witness_for_same_action():
    intervals = (interval("i1", "fault", 0, 1), interval("i2", "fault", 2, 3))
    pattern = ActionPattern("p", "repair", 2, (("s", "fault"),))
    legacy = propose_actions(intervals, ActionCandidateSpec((pattern,)))
    assert len(legacy.value.candidates) == 1
    result = enumerate_action_matches(intervals, ActionMatchEnumerationSpec((pattern,)))
    assert result.status == ComputeStatus.COMPUTED
    assert result.value.matching_complete
    assert result.value.no_action_available
    alternatives = result.value.alternatives
    assert len(alternatives) == 2
    assert {row.action_id for row in alternatives} == {"repair"}
    assert {row.mapping for row in alternatives} == {(("s", "i1"),), (("s", "i2"),)}
    assert len({row.alternative_id for row in alternatives}) == 2
    assert all(row.candidate.action_id == row.alternative_id for row in alternatives)
    assert [row.candidate.release_time for row in alternatives] == [at(1), at(3)]
    assert result == enumerate_action_matches(tuple(reversed(intervals)), result.spec)
    # Alternative IDs can be passed directly to planning without collapsing the
    # semantic action ID, and no-action remains available for optional invocations.
    planned = run(
        tuple(row.candidate for row in alternatives),
        optional=tuple(row.alternative_id for row in alternatives),
    ).value
    assert planned.witness.actions == ()


def test_slot_swaps_remain_distinct_even_with_identical_interval_id_set():
    intervals = (interval("i1", "fault", 0, 1), interval("i2", "fault", 0, 1))
    pattern = ActionPattern("p", "repair", 1, (("left", "fault"), ("right", "fault")))
    catalog = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec((pattern,))
    ).value
    assert len(catalog.alternatives) == 2
    assert {row.candidate.witness_interval_ids for row in catalog.alternatives} == {
        ("i1", "i2")
    }
    assert len({row.mapping for row in catalog.alternatives}) == 2
    assert len({row.alternative_id for row in catalog.alternatives}) == 2
    assert catalog.checked_mappings == 4


def test_shared_object_join_and_strict_allen_predicate():
    intervals = (
        interval("a", "a", 0, 1, ("o", "extra")),
        interval("b", "b", 2, 3, ("o", "other")),
        interval("c", "b", 2, 3, ("unrelated",)),
        interval("d", "b", 1, 3, ("o",)),  # meets, not strict before
    )
    pattern = ActionPattern(
        "p",
        "act",
        1,
        (("x", "a"), ("y", "b")),
        (TemporalPredicate(("x",), "before", ("y",)),),
        True,
    )
    result = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec((pattern,))
    ).value
    assert len(result.alternatives) == 1
    alternative = result.alternatives[0]
    assert alternative.mapping == (("x", "a"), ("y", "b"))
    assert alternative.shared_object_ids == ("o",)
    assert alternative.candidate.release_time == at(3)


def test_hull_predicates_reuse_existing_allen_meaning():
    intervals = (
        interval("a", "a", 0, 2),
        interval("b", "b", 4, 5),
        interval("c", "c", 1, 3),
    )
    pattern = ActionPattern(
        "p",
        "act",
        1,
        (("x", "a"), ("y", "b"), ("z", "c")),
        (TemporalPredicate(("x", "y"), "contains", ("z",)),),
    )
    result = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec((pattern,))
    ).value
    assert len(result.alternatives) == 1
    assert result.matching_complete


def test_interval_reuse_only_when_explicitly_allowed():
    intervals = (interval("i", "a", 0, 1),)
    pattern = ActionPattern("p", "act", 1, (("x", "a"), ("y", "a")))
    spec = ActionMatchEnumerationSpec((pattern,))
    assert enumerate_action_matches(intervals, spec).value.alternatives == ()
    reused = enumerate_action_matches(
        intervals, replace(spec, allow_interval_reuse=True)
    ).value
    assert len(reused.alternatives) == 1
    assert reused.alternatives[0].mapping == (("x", "i"), ("y", "i"))


def test_global_mapping_bound_preserves_unknown_unvisited_patterns():
    intervals = (interval("i1", "a", 0, 1), interval("i2", "a", 2, 3))
    patterns = tuple(ActionPattern(key, "act", 1, (("x", "a"),)) for key in ("p", "q"))
    result = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec(patterns, max_mappings=1)
    )
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.termination == "mapping_limit"
    assert result.value.checked_mappings == 1
    assert not result.value.matching_complete
    first, second = result.value.patterns
    assert first.outcome == "matched" and not first.search_complete
    assert second.outcome == "unknown" and not second.search_complete
    assert len(result.value.alternatives) == 1


def test_exact_output_bound_does_not_falsely_mark_complete_catalog_partial():
    intervals = (interval("i1", "a", 0, 1), interval("i2", "a", 2, 3))
    pattern = ActionPattern("p", "act", 1, (("x", "a"),))
    complete = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec((pattern,), 2, 2)
    )
    assert complete.status == ComputeStatus.COMPUTED
    assert complete.value.matching_complete
    limited = enumerate_action_matches(
        intervals, ActionMatchEnumerationSpec((pattern,), 100, 1)
    )
    assert limited.status == ComputeStatus.PARTIAL
    assert limited.value.termination == "match_limit"
    assert limited.value.checked_mappings == 2
    assert len(limited.value.alternatives) == 1


def test_no_matching_label_is_proved_without_consuming_mapping_budget():
    pattern = ActionPattern("p", "act", 1, (("x", "missing"),))
    result = enumerate_action_matches(
        (), ActionMatchEnumerationSpec((pattern,), 1, 1)
    ).value
    assert result.matching_complete
    assert result.checked_mappings == 0
    assert result.patterns[0].outcome == "no_match"


def test_enumeration_validates_and_preserves_contract_identity():
    pattern = ActionPattern("p", "act", 1, (("x", "a"),))
    with pytest.raises(ValueError):
        ActionMatchEnumerationSpec((pattern, pattern))
    with pytest.raises(ValueError):
        ActionMatchEnumerationSpec((pattern,), max_matches=0)
    with pytest.raises(TypeError):
        ActionMatchEnumerationSpec((pattern,), max_mappings=True)
    row = interval("i", "a", 0, 1)
    with pytest.raises(ValueError, match="duplicate constraint"):
        enumerate_action_matches((row, row), ActionMatchEnumerationSpec((pattern,)))
    result = enumerate_action_matches((row,), ActionMatchEnumerationSpec((pattern,)))
    assert result.operator_id == "pix.object_centric.enumerate_action_matches"
    assert result.source_digest.startswith("pix.constraint-intervals.v1:sha256:")
    with pytest.raises(FrozenInstanceError):
        result.value.alternatives[0].action_id = "changed"


def test_both_new_result_contracts_roundtrip_complete_partial_and_infeasible():
    actions = (candidate("a", 2), candidate("b", 1))
    intervals = (interval("i1", "a", 0, 1), interval("i2", "a", 2, 3))
    pattern = ActionPattern("p", "act", 1, (("x", "a"),))
    results = (
        run(actions, precedence=(("a", "b"),), objective="min_makespan"),
        run(actions, conflicts=(("a", "b"),), max_states=1),
        run(actions, conflicts=(("a", "b"),), max_states=2, objective="min_cost"),
        run(actions, horizon_us=0),
        enumerate_action_matches(intervals, ActionMatchEnumerationSpec((pattern,))),
        enumerate_action_matches(
            intervals, ActionMatchEnumerationSpec((pattern,), max_matches=1)
        ),
    )
    for original in results:
        encoded = result_json_bytes(original)
        assert result_from_json(encoded) == original
        assert result_json_bytes(result_from_json(encoded)) == encoded


def test_precedence_hand_oracle_and_no_implicit_single_machine():
    actions = (candidate("a", 2), candidate("b", 1))
    result = run(actions, precedence=(("a", "b"),), objective="min_makespan")
    assert result.status == ComputeStatus.COMPUTED
    assert result.value.outcome == "optimal"
    assert result.value.search_complete
    assert result.value.objective_value == 3
    assert timing(result.value.witness) == {"a": (at(0), at(2)), "b": (at(2), at(3))}
    parallel = run(actions, objective="min_makespan").value
    assert parallel.witness.makespan_us == 2
    assert parallel.witness.total_waiting_us == 0


def test_required_cycle_is_proved_and_cycle_witness_is_closed():
    result = run(
        (candidate("a", 1), candidate("b", 1)),
        precedence=(("a", "b"), ("b", "a")),
        objective="min_makespan",
    )
    assert result.value.outcome == "infeasible"
    assert result.value.search_complete
    assert result.value.witness is None
    failure = result.value.failure_examples[0]
    assert failure.reason == "cycle"
    assert failure.action_ids[0] == failure.action_ids[-1]
    assert set(failure.action_ids) == {"a", "b"}


def test_no_action_does_not_discharge_hard_required_deadline():
    result = run((candidate("a", 2, deadline=1),), objective="min_cost").value
    assert result.outcome == "infeasible"
    assert not result.no_action_feasible
    assert result.no_action_violations == ("required_action_omitted:a",)
    assert result.failure_counts == (("deadline", 1),)
    assert result.witness is None


def test_no_action_is_feasible_and_can_be_optimal_if_all_actions_optional():
    actions = (candidate("a", 2, deadline=1),)
    result = run(
        actions, optional=("a",), objective="min_cost", costs=(("a", 4),)
    ).value
    assert result.outcome == "optimal"
    assert result.no_action_feasible
    assert result.witness.actions == ()
    assert result.witness.omitted_action_ids == ("a",)
    assert result.objective_value == 0


def test_deliberate_idle_finds_order_missed_by_greedy_scheduler():
    actions = (candidate("a", 4, deadline=7), candidate("b", 1, release=2, deadline=3))
    greedy = schedule_actions(
        actions, ActionScheduleSpec(BASE, conflicts=(("a", "b"),))
    )
    assert greedy.value.outcome == "heuristic_incomplete"
    result = run(actions, conflicts=(("a", "b"),), horizon_us=7).value
    assert result.outcome == "feasible"
    assert timing(result.witness) == {"a": (at(3), at(7)), "b": (at(2), at(3))}
    assert result.witness.conflict_order == (("b", "a"),)
    assert result.objective is None


def test_objective_changes_schedule_not_merely_metadata():
    actions = (candidate("a", 10), candidate("b", 1, release=2))
    common = {"conflicts": (("a", "b"),), "horizon_us": 13}
    makespan = run(actions, objective="min_makespan", **common).value.witness
    waiting = run(actions, objective="min_total_waiting", **common).value.witness
    assert (makespan.makespan_us, makespan.total_waiting_us) == (11, 8)
    assert (waiting.makespan_us, waiting.total_waiting_us) == (13, 3)
    assert timing(makespan)["a"] == (at(0), at(10))
    assert timing(waiting)["a"] == (at(3), at(13))


def test_optional_dependencies_budget_and_utility_oracle():
    actions = tuple(candidate(identity, 1) for identity in ("p", "q", "r", "x"))
    common = {
        "required": ("r",),
        "optional": ("p", "q", "x"),
        "precedence": (("p", "q"),),
        "conflicts": tuple(combinations(("p", "q", "r", "x"), 2)),
        "costs": (("p", 5), ("q", 1), ("x", 1)),
        "utilities": (("q", 10), ("x", 8)),
        "horizon_us": 3,
    }
    utility = run(actions, objective="max_utility", **common).value
    assert utility.witness.selected_action_ids == ("p", "q", "r")
    assert (utility.objective_value, utility.witness.total_cost) == (10, 6)
    constrained = run(actions, objective="max_utility", budget=5, **common).value
    assert constrained.witness.selected_action_ids == ("r", "x")
    assert constrained.objective_value == 8
    minimum = run(actions, objective="min_cost", **common).value
    assert minimum.witness.selected_action_ids == ("r",)
    assert minimum.objective_value == 0
    assert "missing_predecessor" in dict(utility.failure_counts)


def test_negative_utility_optional_action_is_not_assumed_beneficial():
    result = run(
        (candidate("a", 1),),
        optional=("a",),
        utilities=(("a", -5),),
        objective="max_utility",
    ).value
    assert result.witness.selected_action_ids == ()
    assert result.objective_value == 0


def test_budget_exhaustion_without_witness_is_unknown_not_infeasible():
    result = run(
        (candidate("a", 1), candidate("b", 1)),
        conflicts=(("a", "b"),),
        objective="min_makespan",
        max_states=1,
    )
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.outcome == "unknown"
    assert result.value.termination == "state_limit"
    assert result.value.witness is None
    assert result.value.explored_states == 1
    assert result.value.pending_states == 2
    assert not result.value.search_complete
    assert result.issues[0].code == "action_plan_state_limit"


def test_budget_exhaustion_with_witness_is_feasible_not_optimal():
    result = run(
        (candidate("a", 1), candidate("b", 1)),
        conflicts=(("a", "b"),),
        objective="min_makespan",
        max_states=2,
    )
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.outcome == "feasible"
    assert result.value.objective_value == 2
    assert result.value.witness is not None
    assert not result.value.search_complete


def test_feasibility_has_no_hidden_objective_and_can_stop_early():
    actions = (candidate("a", 10), candidate("b", 1, release=2))
    result = run(actions, conflicts=(("a", "b"),), horizon_us=13)
    assert result.status == ComputeStatus.COMPUTED
    assert result.value.outcome == "feasible"
    assert result.value.termination == "feasible_witness"
    assert result.value.objective_value is None
    assert result.value.pending_states == 1
    assert not result.value.search_complete


@pytest.mark.parametrize(
    "constraints,reason",
    [
        ({"horizon_us": 1}, "horizon"),
        ({"budget": 1, "costs": (("a", 2),)}, "budget"),
        ({"conflicts": (("a", "a"),)}, "self_conflict"),
        ({"precedence": (("a", "a"),)}, "cycle"),
    ],
)
def test_each_hard_constraint_rejects_required_action(constraints, reason):
    result = run((candidate("a", 2),), **constraints).value
    assert result.outcome == "infeasible"
    assert reason in dict(result.failure_counts)


def test_finish_at_deadline_and_horizon_is_allowed_release_before_origin_clamped():
    result = run((candidate("a", 2, release=-1, deadline=2),), horizon_us=2).value
    assert result.outcome == "feasible"
    assert timing(result.witness) == {"a": (at(0), at(2))}
    assert result.witness.total_waiting_us == 0


def test_empty_plan_with_zero_horizon_is_an_exact_valid_no_action():
    result = run((), horizon_us=0, objective="min_makespan").value
    assert result.outcome == "optimal"
    assert result.witness.actions == ()
    assert result.objective_value == 0
    assert result.no_action_feasible


def test_datetime_overflow_rejected_but_infeasible_long_duration_is_safe():
    with pytest.raises(ValueError, match="datetime range"):
        ActionPlanningSpec(BASE, 10**30)
    result = run((candidate("a", 10**30),)).value
    assert result.outcome == "infeasible"
    assert result.failure_counts == (("horizon", 1),)


@pytest.mark.parametrize(
    "kwargs,exception",
    [
        ({"required_action_ids": ["a"]}, TypeError),
        ({"required_action_ids": ("a", "a")}, ValueError),
        ({"required_action_ids": ("a",), "optional_action_ids": ("a",)}, ValueError),
        ({"horizon_us": True}, TypeError),
        ({"horizon_us": -1}, ValueError),
        ({"max_states": 0}, ValueError),
        ({"max_states": True}, TypeError),
        ({"objective": "best"}, ValueError),
        ({"budget": -1}, ValueError),
        ({"costs": (("a", -1),)}, ValueError),
        ({"costs": (("a", True),)}, TypeError),
        ({"utilities": (("a", 1), ("a", 2))}, ValueError),
        ({"conflicts": (("a",),)}, ValueError),
        ({"origin": datetime(2026, 1, 1)}, ValueError),
    ],
)
def test_spec_rejects_ambiguous_contracts(kwargs, exception):
    base = {"origin": BASE, "horizon_us": 20}
    base.update(kwargs)
    with pytest.raises(exception):
        ActionPlanningSpec(**base)


def test_unknown_or_unclassified_candidate_is_not_silently_ignored():
    actions = (candidate("a", 1),)
    with pytest.raises(ValueError, match="partition"):
        plan_actions(actions, ActionPlanningSpec(BASE, 20))
    with pytest.raises(ValueError, match="unknown action"):
        run(actions, conflicts=(("a", "unknown"),))
    with pytest.raises(ValueError, match="unique"):
        run(actions + actions, required=("a",))


def test_inputs_results_and_provenance_are_immutable_and_reproducible():
    a, b = candidate("a", 2), candidate("b", 1)
    spec = ActionPlanningSpec(
        BASE,
        10,
        ("b", "a"),
        conflicts=(("b", "a"), ("a", "b")),
        objective="min_makespan",
    )
    first = plan_actions((a, b), spec)
    second = plan_actions((b, a), spec)
    assert first == second
    assert first.source_digest.startswith("pix.action-planning-candidates.v1:sha256:")
    assert first.operator_id == "pix.object_centric.plan_actions"
    assert first.spec == spec
    assert (
        first.computation_id
        != plan_actions((a, b), replace(spec, max_states=20)).computation_id
    )
    with pytest.raises(FrozenInstanceError):
        first.value.witness.total_cost = 10
    with pytest.raises(FrozenInstanceError):
        spec.objective = "min_cost"


def brute_force(actions, spec):
    """Independent enumerator of all integer start times, including idle time."""
    by_id = {row.action_id: row for row in actions}
    costs, utilities = dict(spec.costs), dict(spec.utilities)
    objective_values = []
    for bits in product((False, True), repeat=len(spec.optional_action_ids)):
        selected = set(spec.required_action_ids) | {
            key for key, keep in zip(spec.optional_action_ids, bits) if keep
        }
        if any(b in selected and a not in selected for a, b in spec.precedence):
            continue
        total_cost = sum(costs.get(key, 0) for key in selected)
        if spec.budget is not None and total_cost > spec.budget:
            continue
        selected = sorted(selected)
        for starts in product(range(spec.horizon_us + 1), repeat=len(selected)):
            start = dict(zip(selected, starts))
            end = {key: start[key] + by_id[key].duration_us for key in selected}
            if any(
                start[key]
                < max(
                    0,
                    int(
                        ((by_id[key].release_time or BASE) - BASE).total_seconds()
                        * 1_000_000
                    ),
                )
                or end[key] > spec.horizon_us
                or (
                    by_id[key].deadline is not None
                    and at(end[key]) > by_id[key].deadline
                )
                for key in selected
            ):
                continue
            if any(end[a] > start[b] for a, b in spec.precedence if b in selected):
                continue
            if any(
                start[a] < end[b] and start[b] < end[a]
                for a, b in spec.conflicts
                if a in selected and b in selected
            ):
                continue
            wait = sum(
                start[key]
                - max(
                    0,
                    int(
                        ((by_id[key].release_time or BASE) - BASE).total_seconds()
                        * 1_000_000
                    ),
                )
                for key in selected
            )
            objective_values.append(
                {
                    "min_makespan": max(end.values(), default=0),
                    "min_total_waiting": wait,
                    "min_cost": total_cost,
                    "max_utility": sum(utilities.get(key, 0) for key in selected),
                }[spec.objective]
            )
    if not objective_values:
        return None
    return (max if spec.objective == "max_utility" else min)(objective_values)


@pytest.mark.parametrize(
    "objective", ["min_makespan", "min_total_waiting", "min_cost", "max_utility"]
)
@pytest.mark.parametrize("precedence", [(), (("a", "b"),), (("a", "b"), ("b", "a"))])
@pytest.mark.parametrize("conflict", [False, True])
@pytest.mark.parametrize("optional", [(), ("b",)])
def test_exhaustive_time_grid_oracle(objective, precedence, conflict, optional):
    # 48 cases each compare ALL integer starts, subsets and deliberate idle times.
    actions = (candidate("a", 2), candidate("b", 1, release=1, deadline=3))
    spec = ActionPlanningSpec(
        BASE,
        4,
        ("a",) if optional else ("a", "b"),
        optional,
        precedence,
        (("a", "b"),) if conflict else (),
        costs=(("a", 1), ("b", 2)),
        utilities=(("a", -1), ("b", 4)),
        budget=3,
        objective=objective,
    )
    expected = brute_force(actions, spec)
    actual = plan_actions(actions, spec).value
    assert actual.search_complete
    assert actual.objective_value == expected
    assert actual.outcome == ("infeasible" if expected is None else "optimal")


def test_exhaustive_three_action_duration_release_and_resource_oracle():
    for durations in product((1, 2), repeat=3):
        actions = tuple(
            candidate(key, duration, release=(1 if key == "b" else 0))
            for key, duration in zip(("a", "b", "c"), durations)
        )
        for conflicts in (
            (),
            (("a", "b"),),
            (("a", "b"), ("b", "c")),
            tuple(combinations(("a", "b", "c"), 2)),
        ):
            spec = ActionPlanningSpec(
                BASE,
                5,
                ("a", "b", "c"),
                conflicts=conflicts,
                precedence=(("a", "c"),),
                objective="min_total_waiting",
            )
            expected = brute_force(actions, spec)
            actual = plan_actions(actions, spec).value
            assert actual.objective_value == expected
            assert actual.outcome == ("infeasible" if expected is None else "optimal")
