"""Bounded exact planning of optional, nonpreemptive action proposals.

No action is executed. Positive durations, fixed releases/finish deadlines,
finish-to-start dependencies and pairwise nonoverlap are the supported model.
For each action subset and each conflict orientation, the earliest DAG schedule
dominates all later schedules for the supported regular objectives. Exhausting
this finite enumeration proves feasibility/infeasibility or optimality *within
this declared model*. A state limit never supplies a proof of infeasibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.models import _integer, _text, _tuple
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.actions import (
    ActionCandidate,
    ActionCandidateSpec,
    ActionPattern,
    ConstraintInterval,
    ScheduledAction,
    _aware,
    _cycle,
    _digest,
    _us,
    allen_relation,
)

PLAN_ACTIONS_OPERATOR_ID = "pix.object_centric.plan_actions"
ENUMERATE_ACTION_MATCHES_OPERATOR_ID = "pix.object_centric.enumerate_action_matches"
OBJECTIVES = ("min_makespan", "min_total_waiting", "min_cost", "max_utility")


@dataclass(frozen=True, slots=True)
class ActionMatchEnumerationSpec:
    """Global checked-mapping and returned-match bounds, with exact Allen meaning.

    Mapping identity includes every slot binding, not merely the set of interval
    IDs. Distinct witnesses for the same action remain distinct alternatives.
    """

    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_match_enumeration.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    patterns: tuple[ActionPattern, ...]
    max_mappings: int = 10000
    max_matches: int = 1000
    allow_interval_reuse: bool = False

    def __post_init__(self) -> None:
        # Share the legacy pattern input contract, without its first-witness
        # stopping rule or conservative merging of different action witnesses.
        ActionCandidateSpec(self.patterns, self.max_mappings, self.allow_interval_reuse)
        _integer(self.max_matches, "max_matches")
        object.__setattr__(
            self, "patterns", tuple(sorted(self.patterns, key=lambda p: p.id))
        )


@dataclass(frozen=True, slots=True)
class ActionMatchAlternative:
    alternative_id: str
    pattern_id: str
    action_id: str
    mapping: tuple[tuple[str, str], ...]
    shared_object_ids: tuple[str, ...]
    candidate: ActionCandidate


@dataclass(frozen=True, slots=True)
class ActionPatternSearch:
    pattern_id: str
    outcome: str
    checked_mappings: int
    returned_matches: int
    search_complete: bool


@dataclass(frozen=True, slots=True)
class ActionMatchCatalog:
    alternatives: tuple[ActionMatchAlternative, ...]
    patterns: tuple[ActionPatternSearch, ...]
    matching_complete: bool
    checked_mappings: int
    termination: str
    no_action_available: bool = True


def enumerate_action_matches(
    intervals: tuple[ConstraintInterval, ...], spec: ActionMatchEnumerationSpec
) -> ComputationResult[ActionMatchCatalog]:
    """Enumerate bounded witness alternatives, not an execution recommendation.

    Candidate IDs are stable alternative IDs, so two witnesses for the same
    semantic action can coexist in a planning catalog. ``action_id`` on each
    alternative preserves the original action identity. The caller must decide
    which invocations are required/optional and their hard constraints; this
    function does not assert that repeated execution is permitted or beneficial.

    Allen predicates compare interval hulls exactly as ``propose_actions`` does.
    Release is the maximum matched interval end. No-action is a comparison
    alternative; only ``plan_actions`` checks whether hard requirements allow it.
    A bounded partial catalog must never be treated as a complete action universe.
    """
    _tuple(intervals, ConstraintInterval, "intervals")
    if not isinstance(spec, ActionMatchEnumerationSpec):
        raise TypeError("spec must be ActionMatchEnumerationSpec")
    if len({interval.id for interval in intervals}) != len(intervals):
        raise ValueError("duplicate constraint interval ID")
    ordered = tuple(sorted(intervals, key=lambda interval: interval.id))
    alternatives, searches = [], []
    checked = 0
    termination = "search_exhausted"
    for pattern in spec.patterns:
        if termination != "search_exhausted":
            searches.append(ActionPatternSearch(pattern.id, "unknown", 0, 0, False))
            continue
        choices = tuple(
            tuple(interval for interval in ordered if interval.label == label)
            for _, label in pattern.slots
        )
        pattern_checked = pattern_matches = 0
        complete = True
        for values in product(*choices):
            if checked >= spec.max_mappings:
                termination, complete = "mapping_limit", False
                break
            checked += 1
            pattern_checked += 1
            if not spec.allow_interval_reuse and len({row.id for row in values}) != len(
                values
            ):
                continue
            mapping = dict(zip((alias for alias, _ in pattern.slots), values))
            common = set(values[0].object_ids).intersection(
                *(set(row.object_ids) for row in values[1:])
            )
            if pattern.require_shared_object and not common:
                continue

            def hull(slots: tuple[str, ...]) -> ConstraintInterval:
                rows = tuple(mapping[slot] for slot in slots)
                return ConstraintInterval(
                    "hull",
                    "hull",
                    min(row.start for row in rows),
                    max(row.end for row in rows),
                )

            if not all(
                allen_relation(hull(p.left_slots), hull(p.right_slots)) == p.relation
                for p in pattern.predicates
            ):
                continue
            if len(alternatives) >= spec.max_matches:
                termination, complete = "match_limit", False
                break
            witness = tuple((alias, row.id) for alias, row in sorted(mapping.items()))
            identity = _digest(
                "action-match-alternative", (pattern.id, pattern.action_id, witness)
            )
            candidate = ActionCandidate(
                identity,
                pattern.duration_us,
                release_time=max(row.end for row in values),
                pattern_ids=(pattern.id,),
                witness_interval_ids=tuple(sorted({row.id for row in values})),
            )
            alternatives.append(
                ActionMatchAlternative(
                    identity,
                    pattern.id,
                    pattern.action_id,
                    witness,
                    tuple(sorted(common)),
                    candidate,
                )
            )
            pattern_matches += 1
        searches.append(
            ActionPatternSearch(
                pattern.id,
                "matched" if pattern_matches else "no_match" if complete else "unknown",
                pattern_checked,
                pattern_matches,
                complete,
            )
        )
    complete = termination == "search_exhausted"
    payload = ActionMatchCatalog(
        tuple(alternatives), tuple(searches), complete, checked, termination
    )
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "action_match_enumeration_limit",
                "Unsearched or unreturned witness alternatives remain",
            ),
        )
    )
    return _derived_result(
        ENUMERATE_ACTION_MATCHES_OPERATOR_ID,
        _digest("constraint-intervals", ordered),
        spec,
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL,
        payload,
        issues,
    )


@dataclass(frozen=True, slots=True)
class ActionPlanningSpec:
    """Explicit finite planning contract, using integer microseconds and costs.

    Required and optional IDs must partition the supplied candidates. Selecting
    the successor of a precedence pair also requires its predecessor. Conflicts
    apply only when both actions are selected. No implicit single-machine
    resource exists. Budget is a hard total-cost upper bound; utilities are
    supplied values, not inferred causal benefits or success probabilities.
    Omitted cost/utility entries mean zero. Total waiting is release-relative:
    the sum of ``start - max(origin, release_time)`` over selected actions.

    Without an objective, return the first feasible witness. With an objective,
    enumerate until exhaustion or ``max_states``. Ties use lower total cost,
    lower makespan, lexicographic selected IDs, then start times and conflict
    orders. No-action is considered and satisfies the contract only when no
    action is required. Preexisting candidate.priority is intentionally unused.
    """

    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_planning.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    origin: datetime
    horizon_us: int
    required_action_ids: tuple[str, ...] = ()
    optional_action_ids: tuple[str, ...] = ()
    precedence: tuple[tuple[str, str], ...] = ()
    conflicts: tuple[tuple[str, str], ...] = ()
    costs: tuple[tuple[str, int], ...] = ()
    utilities: tuple[tuple[str, int], ...] = ()
    budget: int | None = None
    objective: str | None = None
    max_states: int = 10000

    def __post_init__(self) -> None:
        _aware(self.origin, "origin")
        object.__setattr__(self, "origin", self.origin.astimezone(timezone.utc))
        _integer(self.horizon_us, "horizon_us", minimum=0)
        try:
            self.origin + timedelta(microseconds=self.horizon_us)
        except OverflowError as exc:
            raise ValueError("planning horizon exceeds datetime range") from exc
        _integer(self.max_states, "max_states")
        if self.objective is not None and self.objective not in OBJECTIVES:
            raise ValueError("unknown action planning objective")
        if self.budget is not None:
            _integer(self.budget, "budget", minimum=0)
        for name in ("required_action_ids", "optional_action_ids"):
            values = getattr(self, name)
            _tuple(values, str, name)
            for value in values:
                _text(value, name)
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {name}")
            object.__setattr__(self, name, tuple(sorted(values)))
        if set(self.required_action_ids) & set(self.optional_action_ids):
            raise ValueError("required and optional action IDs overlap")
        for name in ("precedence", "conflicts"):
            values = getattr(self, name)
            _tuple(values, tuple, name)
            normalized = set()
            for pair in values:
                if len(pair) != 2:
                    raise ValueError(f"{name} entries must be pairs")
                for value in pair:
                    _text(value, name)
                normalized.add(tuple(sorted(pair)) if name == "conflicts" else pair)
            object.__setattr__(self, name, tuple(sorted(normalized)))
        for name in ("costs", "utilities"):
            values = getattr(self, name)
            _tuple(values, tuple, name)
            ids = set()
            for pair in values:
                if len(pair) != 2:
                    raise ValueError(f"{name} entries must be (action_id, integer)")
                identity, value = pair
                _text(identity, name)
                if identity in ids:
                    raise ValueError(f"duplicate action in {name}")
                ids.add(identity)
                if type(value) is not int:
                    raise TypeError(f"{name} values must be integers")
                if name == "costs" and value < 0:
                    raise ValueError("costs must be nonnegative")
            object.__setattr__(self, name, tuple(sorted(values)))


@dataclass(frozen=True, slots=True)
class ActionPlanWitness:
    actions: tuple[ScheduledAction, ...]
    selected_action_ids: tuple[str, ...]
    omitted_action_ids: tuple[str, ...]
    conflict_order: tuple[tuple[str, str], ...]
    makespan_us: int
    total_waiting_us: int
    total_cost: int
    total_utility: int


@dataclass(frozen=True, slots=True)
class ActionPlanFailure:
    """One rejected search branch, never a claim about unsearched branches."""

    reason: str
    selected_action_ids: tuple[str, ...]
    action_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionPlan:
    outcome: str
    termination: str
    witness: ActionPlanWitness | None
    objective: str | None
    objective_value: int | None
    search_complete: bool
    explored_states: int
    pending_states: int
    evaluated_schedules: int
    no_action_feasible: bool
    no_action_violations: tuple[str, ...]
    failure_counts: tuple[tuple[str, int], ...]
    failure_examples: tuple[ActionPlanFailure, ...]
    model: str = "positive_nonpreemptive_actions_with_pairwise_conflicts"


def _earliest(
    selected: tuple[str, ...],
    edges: tuple[tuple[str, str], ...],
    by_id: dict[str, ActionCandidate],
    spec: ActionPlanningSpec,
) -> tuple[dict[str, tuple[int, int]], str | None, tuple[str, ...]]:
    """Integer offsets avoid overflowing datetimes of infeasible schedules."""
    predecessors = {key: set() for key in selected}
    followers = {key: set() for key in selected}
    for before, after in edges:
        predecessors[after].add(before)
        followers[before].add(after)
    cycle = _cycle(predecessors)
    if cycle:
        return {}, "cycle", cycle
    pending = {key: len(values) for key, values in predecessors.items()}
    ready = sorted(key for key in selected if not pending[key])
    timing: dict[str, tuple[int, int]] = {}
    while ready:
        key = ready.pop()
        action = by_id[key]
        release = max(0, _us((action.release_time or spec.origin) - spec.origin))
        start = max(release, max((timing[p][1] for p in predecessors[key]), default=0))
        end = start + action.duration_us
        if end > spec.horizon_us:
            return {}, "horizon", (key,)
        if action.deadline is not None and end > _us(action.deadline - spec.origin):
            return {}, "deadline", (key,)
        timing[key] = start, end
        for following in sorted(followers[key]):
            pending[following] -= 1
            if not pending[following]:
                ready.append(following)
    return timing, None, ()


def _witness(
    selected: tuple[str, ...],
    orders: tuple[tuple[str, str], ...],
    timing: dict[str, tuple[int, int]],
    by_id: dict[str, ActionCandidate],
    spec: ActionPlanningSpec,
) -> ActionPlanWitness:
    rows = []
    for key in selected:
        start, end = timing[key]
        release = max(0, _us((by_id[key].release_time or spec.origin) - spec.origin))
        rows.append(
            ScheduledAction(
                key,
                spec.origin + timedelta(microseconds=start),
                spec.origin + timedelta(microseconds=end),
                start - release,
                end - release,
                tuple(a for a, b in spec.precedence if b == key),
                tuple(sorted(a for a, b in orders if b == key)),
            )
        )
    costs, utilities = dict(spec.costs), dict(spec.utilities)
    return ActionPlanWitness(
        tuple(sorted(rows, key=lambda row: (row.start, row.action_id))),
        selected,
        tuple(sorted(set(by_id) - set(selected))),
        tuple(sorted(orders)),
        max((end for _, end in timing.values()), default=0),
        sum(row.waiting_us for row in rows),
        sum(costs.get(key, 0) for key in selected),
        sum(utilities.get(key, 0) for key in selected),
    )


def _objective_value(witness: ActionPlanWitness, objective: str | None) -> int | None:
    return {
        None: None,
        "min_makespan": witness.makespan_us,
        "min_total_waiting": witness.total_waiting_us,
        "min_cost": witness.total_cost,
        "max_utility": witness.total_utility,
    }[objective]


def _rank(witness: ActionPlanWitness, objective: str) -> tuple:
    value = _objective_value(witness, objective)
    return (
        -value if objective == "max_utility" else value,
        witness.total_cost,
        witness.makespan_us,
        witness.selected_action_ids,
        tuple(sorted((row.action_id, row.start) for row in witness.actions)),
        witness.conflict_order,
    )


def plan_actions(
    candidates: tuple[ActionCandidate, ...], spec: ActionPlanningSpec
) -> ComputationResult[ActionPlan]:
    """Return a checkable proposal with bounded exact search and honest outcomes.

    ``optimal`` requires an objective and full enumeration; ``feasible`` has a
    concrete valid witness but makes no optimality claim. ``infeasible`` requires
    exhaustive rejection. ``unknown`` means the bound was reached without a
    witness. A bounded search with a witness has outcome ``feasible`` and PARTIAL
    status, never ``optimal``. ``pending_states`` counts frontier nodes, not the
    number of unexamined schedules. State count is not a wall-clock budget.

    This is exact for the declared ActionCandidate catalog, not a claim that the
    preceding temporal pattern matcher enumerated every real-world action.
    """
    _tuple(candidates, ActionCandidate, "candidates")
    if not isinstance(spec, ActionPlanningSpec):
        raise TypeError("spec must be ActionPlanningSpec")
    by_id = {item.action_id: item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate action IDs must be unique")
    declared = set(spec.required_action_ids + spec.optional_action_ids)
    if declared != set(by_id):
        raise ValueError("required/optional action IDs must partition all candidates")
    referenced = {key for pair in spec.precedence + spec.conflicts for key in pair}
    referenced |= {key for key, _ in spec.costs + spec.utilities}
    if not referenced <= declared:
        raise ValueError("planning constraint references an unknown action")
    # Both branch types count toward the same finite budget. DFS excludes optional
    # actions first, so the no-action subset is examined first when it is legal.
    stack = [("select", 0, spec.required_action_ids, ())]
    best = None
    explored = evaluated = 0
    failures: dict[str, int] = {}
    examples = []
    termination = "search_exhausted"

    def reject(reason: str, selected: tuple[str, ...], ids: tuple[str, ...]) -> None:
        failures[reason] = failures.get(reason, 0) + 1
        if len(examples) < 10:
            examples.append(ActionPlanFailure(reason, selected, ids))

    while stack and explored < spec.max_states:
        stage, index, selected, orders = stack.pop()
        explored += 1
        if stage == "select" and index < len(spec.optional_action_ids):
            key = spec.optional_action_ids[index]
            stack.append(("select", index + 1, tuple(sorted(selected + (key,))), ()))
            stack.append(("select", index + 1, selected, ()))
            continue
        selected_set = set(selected)
        if stage == "select":
            missing = tuple(
                sorted(
                    {
                        a
                        for a, b in spec.precedence
                        if b in selected_set and a not in selected_set
                    }
                )
            )
            if missing:
                reject("missing_predecessor", selected, missing)
                continue
            costs = dict(spec.costs)
            total_cost = sum(costs.get(key, 0) for key in selected)
            if spec.budget is not None and total_cost > spec.budget:
                reject("budget", selected, selected)
                continue
            index = 0
        precedence = tuple((a, b) for a, b in spec.precedence if b in selected_set)
        conflicts = tuple(
            (a, b) for a, b in spec.conflicts if a in selected_set and b in selected_set
        )
        timing, reason, ids = _earliest(selected, precedence + orders, by_id, spec)
        if reason is not None:
            reject(reason, selected, ids)
            continue
        if index < len(conflicts):
            a, b = conflicts[index]
            if a == b:
                reject("self_conflict", selected, (a,))
                continue
            stack.append(("orient", index + 1, selected, orders + ((b, a),)))
            stack.append(("orient", index + 1, selected, orders + ((a, b),)))
            continue
        evaluated += 1
        witness = _witness(selected, orders, timing, by_id, spec)
        if best is None or (
            spec.objective is not None
            and _rank(witness, spec.objective) < _rank(best, spec.objective)
        ):
            best = witness
        if spec.objective is None:
            termination = "feasible_witness"
            break
    if termination != "feasible_witness" and stack:
        termination = "state_limit"
    complete = not stack
    limited = termination == "state_limit"
    outcome = (
        "unknown"
        if limited and best is None
        else "infeasible"
        if best is None
        else "optimal"
        if complete and spec.objective is not None
        else "feasible"
    )
    payload = ActionPlan(
        outcome,
        termination,
        best,
        spec.objective,
        _objective_value(best, spec.objective) if best is not None else None,
        complete,
        explored,
        len(stack),
        evaluated,
        not spec.required_action_ids,
        tuple(f"required_action_omitted:{key}" for key in spec.required_action_ids),
        tuple(sorted(failures.items())),
        tuple(examples),
    )
    issues = (
        (
            ComputeIssue(
                "action_plan_state_limit",
                "Unsearched alternatives remain; optimality and infeasibility are not established",
            ),
        )
        if limited
        else ()
    )
    return _derived_result(
        PLAN_ACTIONS_OPERATOR_ID,
        _digest(
            "action-planning-candidates", tuple(by_id[key] for key in sorted(by_id))
        ),
        spec,
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED,
        payload,
        issues,
    )


RESULT_SCHEMAS = {
    PLAN_ACTIONS_OPERATOR_ID: ("action-plan", ActionPlanningSpec, ActionPlan),
    ENUMERATE_ACTION_MATCHES_OPERATOR_ID: (
        "action-match-catalog",
        ActionMatchEnumerationSpec,
        ActionMatchCatalog,
    ),
}
