"""Native action analysis. These functions propose and measure; they do not act.

Temporal matching uses strict Allen relations on positive-duration intervals.
Scheduling uses deterministic serial list scheduling, not a global optimizer.
Structural reachability is potential influence, not executable reachability;
observed before/after differences are descriptive, not causal effects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
from itertools import product
from typing import ClassVar

from pix.compute._common import _derived_result, _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import model_digest
from pix.contracts.models import (
    ObjectCentricPetriNet,
    ObjectMarking,
    _integer,
    _text,
    _tuple,
)
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
)
from pix.object_centric.performance import OCPerformanceSpec, measure_performance
from pix.ocel import OCEL

CANDIDATES_OPERATOR_ID = "pix.object_centric.propose_actions"
SCHEDULE_OPERATOR_ID = "pix.object_centric.schedule_actions"
STRUCTURAL_IMPACT_OPERATOR_ID = "pix.object_centric.structural_action_impact"
WINDOW_IMPACT_OPERATOR_ID = "pix.object_centric.compare_action_windows"
CONFIGURATION_OPERATOR_ID = "pix.object_centric.update_action_configuration"
ALLEN_RELATIONS = (
    "before",
    "after",
    "meets",
    "met_by",
    "overlaps",
    "overlapped_by",
    "starts",
    "started_by",
    "during",
    "contains",
    "finishes",
    "finished_by",
    "equal",
)


def _aware(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _digest(kind: str, value: object) -> str:
    encoded = json.dumps(
        _identity_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"pix.{kind}.v1:sha256:" + sha256(encoded).hexdigest()


def _us(delta: timedelta) -> int:
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


@dataclass(frozen=True, slots=True)
class ConstraintInterval:
    """A known constraint occurrence, with supplied provenance object IDs."""

    id: str
    label: str
    start: datetime
    end: datetime
    object_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "id")
        _text(self.label, "label")
        _aware(self.start, "start")
        _aware(self.end, "end")
        object.__setattr__(self, "start", self.start.astimezone(timezone.utc))
        object.__setattr__(self, "end", self.end.astimezone(timezone.utc))
        if self.start >= self.end:
            raise ValueError(
                "Allen intervals require start < end; point events need an explicit interval"
            )
        _tuple(self.object_ids, str, "object_ids")
        for item in self.object_ids:
            _text(item, "object_id")
        object.__setattr__(self, "object_ids", tuple(sorted(set(self.object_ids))))


def allen_relation(left: ConstraintInterval, right: ConstraintInterval) -> str:
    """Return exactly one of the 13 Allen base relations, with strict overlap.

    In particular ``overlaps`` requires a.start < b.start < a.end < b.end;
    equality and boundary contact do not count as overlap or strict before.
    """
    if not isinstance(left, ConstraintInterval) or not isinstance(
        right, ConstraintInterval
    ):
        raise TypeError("intervals must be ConstraintInterval")
    a, b, c, d = left.start, left.end, right.start, right.end
    if b < c:
        return "before"
    if a > d:
        return "after"
    if b == c:
        return "meets"
    if a == d:
        return "met_by"
    if a == c:
        return "equal" if b == d else "starts" if b < d else "started_by"
    if b == d:
        return "finishes" if a > c else "finished_by"
    if a < c:
        return "overlaps" if b < d else "contains"
    return "overlapped_by" if b > d else "during"


@dataclass(frozen=True, slots=True)
class TemporalPredicate:
    """Compare hulls of leaf-slot groups; all predicates are conjoined.

    A binary temporal pattern tree is represented by one predicate per inner
    node and the leaf slots below its left and right children. The hull is
    [minimum start, maximum end], not a union of covered instants.
    """

    left_slots: tuple[str, ...]
    relation: str
    right_slots: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.relation not in ALLEN_RELATIONS:
            raise ValueError("unknown Allen relation")
        for name in ("left_slots", "right_slots"):
            slots = getattr(self, name)
            _tuple(slots, str, name)
            if not slots or len(set(slots)) != len(slots):
                raise ValueError(f"{name} must contain unique slots")
            for slot in slots:
                _text(slot, "slot")


@dataclass(frozen=True, slots=True)
class ActionPattern:
    id: str
    action_id: str
    duration_us: int
    slots: tuple[tuple[str, str], ...]
    predicates: tuple[TemporalPredicate, ...] = ()
    require_shared_object: bool = False

    def __post_init__(self) -> None:
        _text(self.id, "id")
        _text(self.action_id, "action_id")
        _integer(self.duration_us, "duration_us")
        _tuple(self.slots, tuple, "slots")
        names = set()
        for slot in self.slots:
            if len(slot) != 2:
                raise ValueError("slots must contain (alias, constraint_label)")
            alias, label = slot
            _text(alias, "slot alias")
            _text(label, "constraint label")
            if alias in names:
                raise ValueError("duplicate slot alias")
            names.add(alias)
        if not names:
            raise ValueError("a pattern requires at least one slot")
        _tuple(self.predicates, TemporalPredicate, "predicates")
        for predicate in self.predicates:
            if not set(predicate.left_slots + predicate.right_slots) <= names:
                raise ValueError("predicate references an unknown slot")
        if not isinstance(self.require_shared_object, bool):
            raise TypeError("require_shared_object must be bool")


@dataclass(frozen=True, slots=True)
class ActionCandidate:
    action_id: str
    duration_us: int
    release_time: datetime | None = None
    deadline: datetime | None = None
    priority: int = 0
    pattern_ids: tuple[str, ...] = ()
    witness_interval_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.action_id, "action_id")
        _integer(self.duration_us, "duration_us")
        if type(self.priority) is not int:
            raise TypeError("priority must be an integer")
        for name in ("release_time", "deadline"):
            if getattr(self, name) is not None:
                _aware(getattr(self, name), name)
                object.__setattr__(
                    self, name, getattr(self, name).astimezone(timezone.utc)
                )
        for name in ("pattern_ids", "witness_interval_ids"):
            _tuple(getattr(self, name), str, name)
            for item in getattr(self, name):
                _text(item, name)


@dataclass(frozen=True, slots=True)
class ActionCandidateSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_candidates.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    patterns: tuple[ActionPattern, ...]
    max_mappings_per_pattern: int = 10000
    allow_interval_reuse: bool = False

    def __post_init__(self) -> None:
        _tuple(self.patterns, ActionPattern, "patterns")
        if len({pattern.id for pattern in self.patterns}) != len(self.patterns):
            raise ValueError("duplicate pattern ID")
        _integer(self.max_mappings_per_pattern, "max_mappings_per_pattern")
        if not isinstance(self.allow_interval_reuse, bool):
            raise TypeError("allow_interval_reuse must be bool")


@dataclass(frozen=True, slots=True)
class ActionPatternMatch:
    pattern_id: str
    outcome: str
    checked_mappings: int
    mapping: tuple[tuple[str, str], ...]
    shared_object_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionCandidates:
    candidates: tuple[ActionCandidate, ...]
    matches: tuple[ActionPatternMatch, ...]
    no_action_available: bool
    matching_complete: bool


def propose_actions(
    intervals: tuple[ConstraintInterval, ...],
    spec: ActionCandidateSpec,
) -> ComputationResult[ActionCandidates]:
    """Find a first deterministic witness per pattern, with bounded search.

    Equal action IDs are merged using maximum duration and maximum release
    time across matching patterns. This is an explicit conservative profile.
    A search cutoff means unknown, not a false pattern or a recommended action.
    """
    _tuple(intervals, ConstraintInterval, "intervals")
    if not isinstance(spec, ActionCandidateSpec):
        raise TypeError("spec must be ActionCandidateSpec")
    if len({item.id for item in intervals}) != len(intervals):
        raise ValueError("duplicate constraint interval ID")
    ordered = tuple(sorted(intervals, key=lambda item: item.id))
    matches, candidates, issues = [], {}, []
    for pattern in spec.patterns:
        choices = tuple(
            tuple(item for item in ordered if item.label == label)
            for _, label in pattern.slots
        )
        count, outcome, witness, common = 0, "no_match", (), set()
        for values in product(*choices):
            if count >= spec.max_mappings_per_pattern:
                outcome = "search_limit"
                break
            count += 1
            if not spec.allow_interval_reuse and len(
                {item.id for item in values}
            ) != len(values):
                continue
            mapping = dict(zip((slot for slot, _ in pattern.slots), values))
            common = set(values[0].object_ids).intersection(
                *(set(item.object_ids) for item in values[1:])
            )
            if pattern.require_shared_object and not common:
                continue

            def hull(slots: tuple[str, ...]) -> ConstraintInterval:
                group = [mapping[slot] for slot in slots]
                return ConstraintInterval(
                    "hull",
                    "hull",
                    min(i.start for i in group),
                    max(i.end for i in group),
                )

            if all(
                allen_relation(hull(p.left_slots), hull(p.right_slots)) == p.relation
                for p in pattern.predicates
            ):
                outcome = "matched"
                witness = tuple(
                    (alias, item.id) for alias, item in sorted(mapping.items())
                )
                release = max(item.end for item in values)
                ids = tuple(sorted({item.id for item in values}))
                old = candidates.get(pattern.action_id)
                candidates[pattern.action_id] = ActionCandidate(
                    pattern.action_id,
                    max(pattern.duration_us, old.duration_us if old else 0),
                    max(release, old.release_time) if old else release,
                    pattern_ids=tuple(
                        sorted((old.pattern_ids if old else ()) + (pattern.id,))
                    ),
                    witness_interval_ids=tuple(
                        sorted(set((old.witness_interval_ids if old else ()) + ids))
                    ),
                )
                break
        if outcome == "search_limit":
            issues.append(
                ComputeIssue(
                    "action_pattern_search_limit",
                    f"Pattern {pattern.id} remains unknown",
                )
            )
        matches.append(
            ActionPatternMatch(
                pattern.id,
                outcome,
                count,
                witness,
                tuple(sorted(common)) if outcome == "matched" else (),
            )
        )
    return _derived_result(
        CANDIDATES_OPERATOR_ID,
        _digest("constraint-intervals", ordered),
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        ActionCandidates(
            tuple(candidates[k] for k in sorted(candidates)),
            tuple(matches),
            True,
            not issues,
        ),
        tuple(issues),
    )


@dataclass(frozen=True, slots=True)
class ActionScheduleSpec:
    """Every supplied candidate is required in the proposal unless no-action is selected.

    Precedence pairs are ordered; conflict pairs require disjoint time spans.
    No-action is a separately available choice, without any utility comparison.
    Higher priority is considered first among precedence-ready candidates.
    """

    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_schedule.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    origin: datetime
    precedence: tuple[tuple[str, str], ...] = ()
    conflicts: tuple[tuple[str, str], ...] = ()
    choose_no_action: bool = False

    def __post_init__(self) -> None:
        _aware(self.origin, "origin")
        object.__setattr__(self, "origin", self.origin.astimezone(timezone.utc))
        for name in ("precedence", "conflicts"):
            _tuple(getattr(self, name), tuple, name)
            for pair in getattr(self, name):
                if len(pair) != 2:
                    raise ValueError(f"{name} entries must be pairs")
                for item in pair:
                    _text(item, name)
        if not isinstance(self.choose_no_action, bool):
            raise TypeError("choose_no_action must be bool")


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    action_id: str
    start: datetime
    end: datetime
    waiting_us: int
    flow_us: int
    precedence_ids: tuple[str, ...]
    conflict_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionSchedule:
    outcome: str
    actions: tuple[ScheduledAction, ...]
    unscheduled: tuple[tuple[str, str], ...]
    cycle_witness: tuple[str, ...]
    makespan_us: int
    total_waiting_us: int
    total_flow_us: int
    no_action_available: bool = True
    optimality: str = "not_assessed"


def _cycle(predecessors: dict[str, set[str]]) -> tuple[str, ...]:
    # Iterative depth-first search retains a concrete closed cycle, not all
    # residual descendants of a cycle as though they were cycle members.
    done = set()
    for root in sorted(predecessors):
        if root in done:
            continue
        path, positions = [root], {root: 0}
        stack = [(root, iter(sorted(predecessors[root])))]
        while stack:
            node, iterator = stack[-1]
            following = next(iterator, None)
            if following is None:
                stack.pop()
                done.add(node)
                positions.pop(node)
                path.pop()
            elif following in positions:
                return tuple(reversed(path[positions[following] :] + [following]))
            elif following not in done:
                positions[following] = len(path)
                path.append(following)
                stack.append((following, iter(sorted(predecessors[following]))))
    return ()


def schedule_actions(
    candidates: tuple[ActionCandidate, ...],
    spec: ActionScheduleSpec,
) -> ComputationResult[ActionSchedule]:
    """Schedule without executing anything; never label greedy failure infeasible.

    A cycle proves infeasibility because all action durations are positive.
    A release/deadline violation before conflicts is also a proof. Failure
    caused by a chosen conflict order is reported as heuristic_incomplete:
    another order may still be feasible. Unconstrained actions can run in
    parallel; no single-machine resource is implicitly imposed.
    """
    _tuple(candidates, ActionCandidate, "candidates")
    if not isinstance(spec, ActionScheduleSpec):
        raise TypeError("spec must be ActionScheduleSpec")
    by_id = {item.action_id: item for item in candidates}
    if len(by_id) != len(candidates):
        raise ValueError("candidate action IDs must be unique")
    for pair in spec.precedence + spec.conflicts:
        if not set(pair) <= by_id.keys():
            raise ValueError("schedule relation references an unknown candidate")
    predecessors = {key: {a for a, b in spec.precedence if b == key} for key in by_id}
    conflicts = {
        key: {b if a == key else a for a, b in spec.conflicts if key in (a, b)}
        for key in by_id
    }
    cycle = _cycle(predecessors)
    source = _digest("action-candidates", tuple(by_id[k] for k in sorted(by_id)))
    if spec.choose_no_action or not candidates:
        payload = ActionSchedule(
            "no_action",
            (),
            tuple((key, "no_action_selected") for key in sorted(by_id)),
            (),
            0,
            0,
            0,
        )
    elif cycle or any(key in conflicts[key] for key in by_id):
        payload = ActionSchedule(
            "infeasible",
            (),
            tuple((key, "infeasible_constraints") for key in sorted(by_id)),
            cycle,
            0,
            0,
            0,
        )
    else:
        scheduled, rejected, pending = {}, {}, set(by_id)
        exact_failure = False
        while pending:
            ready = [key for key in pending if not (predecessors[key] & pending)]
            key = min(ready, key=lambda item: (-by_id[item].priority, item))
            pending.remove(key)
            if predecessors[key] & rejected.keys():
                rejected[key] = "predecessor_unscheduled"
                continue
            item = by_id[key]
            release = max(spec.origin, item.release_time or spec.origin)
            lower = max((scheduled[p].end for p in predecessors[key]), default=release)
            start = max(release, lower)
            duration = timedelta(microseconds=item.duration_us)
            # A conflict-free lower bound is exact only when predecessors had
            # no scheduling delay due to conflict; release alone always is.
            if item.deadline is not None and release + duration > item.deadline:
                rejected[key] = "release_deadline_infeasible"
                exact_failure = True
                continue
            occupied = sorted(
                (scheduled[p] for p in conflicts[key] & scheduled.keys()),
                key=lambda p: (p.start, p.action_id),
            )
            blocking = []
            for other in occupied:
                if start < other.end and other.start < start + duration:
                    start = other.end
                    blocking.append(other.action_id)
            if item.deadline is not None and start + duration > item.deadline:
                rejected[key] = "greedy_order_missed_deadline"
                continue
            end = start + duration
            scheduled[key] = ScheduledAction(
                key,
                start,
                end,
                _us(start - release),
                _us(end - release),
                tuple(sorted(predecessors[key])),
                tuple(blocking),
            )
        actions = tuple(
            sorted(scheduled.values(), key=lambda item: (item.start, item.action_id))
        )
        payload = ActionSchedule(
            "infeasible"
            if exact_failure
            else "heuristic_incomplete"
            if rejected
            else "feasible",
            actions,
            tuple(sorted(rejected.items())),
            (),
            _us(max((item.end for item in actions), default=spec.origin) - spec.origin),
            sum(item.waiting_us for item in actions),
            sum(item.flow_us for item in actions),
        )
    issues = (
        (
            ComputeIssue(
                "action_schedule_greedy_incomplete",
                "A different conflict order may be feasible",
            ),
        )
        if payload.outcome == "heuristic_incomplete"
        else ()
    )
    return _derived_result(
        SCHEDULE_OPERATOR_ID,
        source,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        issues,
    )


@dataclass(frozen=True, slots=True)
class StructuralActionImpactSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.structural_action_impact.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    changed_transition_ids: tuple[str, ...]
    marking: ObjectMarking | None = None

    def __post_init__(self) -> None:
        _tuple(self.changed_transition_ids, str, "changed_transition_ids")
        for item in self.changed_transition_ids:
            _text(item, "changed_transition_id")
        object.__setattr__(
            self,
            "changed_transition_ids",
            tuple(sorted(set(self.changed_transition_ids))),
        )
        if self.marking is not None and not isinstance(self.marking, ObjectMarking):
            raise TypeError("marking must be ObjectMarking or None")


@dataclass(frozen=True, slots=True)
class TypedStructuralImpact:
    object_type: str
    direct_transition_ids: tuple[str, ...]
    prior_transition_ids: tuple[str, ...]
    posterior_transition_ids: tuple[str, ...]
    prior_place_ids: tuple[str, ...]
    posterior_place_ids: tuple[str, ...]
    prior_marked_object_ids: tuple[str, ...] | None
    posterior_marked_object_ids: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class StructuralActionImpact:
    changed_transition_ids: tuple[str, ...]
    direct_object_types: tuple[str, ...]
    typed: tuple[TypedStructuralImpact, ...]
    interpretation: str = "typed_graph_reachability_not_causal_or_executable"


def structural_action_impact(
    net: ObjectCentricPetriNet,
    spec: StructuralActionImpactSpec,
) -> ComputationResult[StructuralActionImpact]:
    """Compute typed predecessors/successors and supplied-marking populations.

    Paths stay within one object type, traversing silent transitions but
    reporting visible functions. Changed transitions are excluded from prior
    and posterior lists even when cycles lead back to them. Marking population
    is unknown when no marking is supplied; it is never inferred from the log.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, StructuralActionImpactSpec
    ):
        raise TypeError("expected ObjectCentricPetriNet and StructuralActionImpactSpec")
    transitions = {t.id: t for t in net.transitions}
    changed = set(spec.changed_transition_ids)
    if not changed <= transitions.keys():
        raise ValueError("unknown changed transition ID")
    if spec.marking is not None:
        net.validate_marking(spec.marking)
    rows, direct_types = [], []
    for kind in sorted({p.object_type for p in net.places}):
        places = {p.id for p in net.places if p.object_type == kind}
        edges = [
            (a.source, a.target)
            for a in net.arcs
            if a.source in places or a.target in places
        ]
        incident = {n for edge in edges for n in edge} & changed
        if incident:
            direct_types.append(kind)

        def reach(reverse: bool) -> set[str]:
            adjacency = {}
            for a, b in edges:
                x, y = (b, a) if reverse else (a, b)
                adjacency.setdefault(x, set()).add(y)
            seen, pending = set(), list(changed)
            while pending:
                node = pending.pop()
                for target in adjacency.get(node, ()):
                    if target not in seen:
                        seen.add(target)
                        pending.append(target)
            return seen

        prior, posterior = reach(True), reach(False)

        def visible(nodes: set[str]) -> tuple[str, ...]:
            return tuple(
                sorted(
                    n
                    for n in nodes - changed
                    if n in transitions and transitions[n].activity is not None
                )
            )

        def objects(nodes: set[str]) -> tuple[str, ...] | None:
            return (
                None
                if spec.marking is None
                else tuple(
                    sorted(
                        {
                            t.object_id
                            for t in spec.marking.tokens
                            if t.place_id in nodes & places
                        }
                    )
                )
            )

        rows.append(
            TypedStructuralImpact(
                kind,
                tuple(sorted(incident)),
                visible(prior),
                visible(posterior),
                tuple(sorted(prior & places)),
                tuple(sorted(posterior & places)),
                objects(prior),
                objects(posterior),
            )
        )
    return _derived_result(
        STRUCTURAL_IMPACT_OPERATOR_ID,
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        StructuralActionImpact(
            spec.changed_transition_ids, tuple(direct_types), tuple(rows)
        ),
    )


@dataclass(frozen=True, slots=True)
class ActionWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        _aware(self.start, "start")
        _aware(self.end, "end")
        object.__setattr__(self, "start", self.start.astimezone(timezone.utc))
        object.__setattr__(self, "end", self.end.astimezone(timezone.utc))
        if self.start >= self.end:
            raise ValueError("window must have positive duration")


@dataclass(frozen=True, slots=True)
class ActionWindowSpec:
    """Compare disjoint half-open windows; delta always equals change-reference.

    Performance is evaluated on the full input first, then sampled by event
    completion in each window. Boundary predecessors are retained. Means
    cover known observations; unknown counts remain explicit. Counts are raw,
    so unequal window durations are not silently normalized into rates.
    """

    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_window.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    reference: ActionWindow
    change: ActionWindow
    performance: OCPerformanceSpec = OCPerformanceSpec()

    def __post_init__(self) -> None:
        if not isinstance(self.reference, ActionWindow) or not isinstance(
            self.change, ActionWindow
        ):
            raise TypeError("reference and change must be ActionWindow")
        if self.reference.end > self.change.start:
            raise ValueError("reference must end no later than change starts")
        if not isinstance(self.performance, OCPerformanceSpec):
            raise TypeError("performance must be OCPerformanceSpec")
        if "activity_frequency" in self.performance.metrics:
            raise ValueError(
                "activity_frequency has no event timestamp; use the window activity_counts instead"
            )


@dataclass(frozen=True, slots=True)
class WindowMetric:
    metric: str
    unit: str
    reference_known: int
    reference_unknown: int
    change_known: int
    change_unknown: int
    reference_numerator: int | None
    reference_denominator: int | None
    change_numerator: int | None
    change_denominator: int | None
    delta_numerator: int | None
    delta_denominator: int | None
    reference_event_ids: tuple[str, ...]
    change_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionWindowImpact:
    reference_event_ids: tuple[str, ...]
    change_event_ids: tuple[str, ...]
    activity_counts: tuple[tuple[str, int, int, int], ...]
    object_type_counts: tuple[tuple[str, int, int, int], ...]
    metrics: tuple[WindowMetric, ...]
    interpretation: str = "observed_change_minus_reference_not_causal"


def compare_action_windows(
    log: OCEL | ComputationContext,
    spec: ActionWindowSpec,
) -> ComputationResult[ActionWindowImpact]:
    if not isinstance(spec, ActionWindowSpec):
        raise TypeError("spec must be ActionWindowSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            WINDOW_IMPACT_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    performance = measure_performance(context, spec.performance)
    if performance.value is None:
        return _result(
            WINDOW_IMPACT_OPERATOR_ID,
            context,
            spec,
            performance.status,
            None,
            performance.issues,
        )

    def selected(window: ActionWindow) -> tuple[str, ...]:
        return tuple(
            sorted(
                e.id
                for e in context.log.events
                if window.start <= e.time < window.end
                and (
                    spec.performance.activities is None
                    or e.type in spec.performance.activities
                )
            )
        )

    ref, change = selected(spec.reference), selected(spec.change)
    populations = set(ref), set(change)
    counts = []
    for activity in sorted({context.events_by_id[e].type for e in ref + change}):
        a, b = (
            sum(context.events_by_id[e].type == activity for e in pop)
            for pop in populations
        )
        counts.append((activity, a, b, b - a))
    objects = [
        set(
            r.object
            for e in pop
            for r in context.e2o_by_event[e]
            if spec.performance.qualifiers is None
            or r.qualifier in spec.performance.qualifiers
        )
        for pop in populations
    ]
    object_counts = []
    for kind in sorted({context.objects_by_id[o].type for pop in objects for o in pop}):
        a, b = (
            sum(context.objects_by_id[o].type == kind for o in pop) for pop in objects
        )
        object_counts.append((kind, a, b, b - a))
    rows, output_issues = [], []
    for summary in performance.value.summaries:
        chosen = [
            tuple(s for s in summary.samples if s.event_id in pop)
            for pop in populations
        ]
        known = [tuple(s for s in samples if s.value is not None) for samples in chosen]
        unknown = [len(chosen[i]) - len(known[i]) for i in (0, 1)]
        means = [
            Fraction(sum(s.value for s in samples), len(samples)) if samples else None
            for samples in known
        ]
        delta = (
            means[1] - means[0] if all(value is not None for value in means) else None
        )
        if any(unknown) or delta is None:
            output_issues.append(
                ComputeIssue(
                    "action_window_unknown_metric",
                    f"{summary.metric}: unknown observations or an empty known population",
                )
            )
        fractions = tuple(
            x
            for value in (*means, delta)
            for x in (
                (value.numerator, value.denominator)
                if value is not None
                else (None, None)
            )
        )
        rows.append(
            WindowMetric(
                summary.metric,
                summary.unit,
                len(known[0]),
                unknown[0],
                len(known[1]),
                unknown[1],
                *fractions,
                tuple(sorted({s.event_id for s in chosen[0]})),
                tuple(sorted({s.event_id for s in chosen[1]})),
            )
        )
    # The upstream performance result may contain unknowns outside both windows;
    # these do not downgrade the requested window comparison.
    payload = ActionWindowImpact(
        ref, change, tuple(counts), tuple(object_counts), tuple(rows)
    )
    return _result(
        WINDOW_IMPACT_OPERATOR_ID,
        context,
        spec,
        ComputeStatus.PARTIAL if output_issues else ComputeStatus.COMPUTED,
        payload,
        tuple(output_issues),
        parent_computation_ids=(performance.computation_id,),
    )


@dataclass(frozen=True, slots=True)
class ActionRule:
    """Declarative rule metadata; expression is stored, never evaluated here."""

    id: str
    kind: str
    object_type: str
    expression: str

    def __post_init__(self) -> None:
        for name in ("id", "object_type", "expression"):
            _text(getattr(self, name), name)
        if self.kind not in ("integrity", "reaction", "derivation"):
            raise ValueError("rule kind must be integrity, reaction, or derivation")


@dataclass(frozen=True, slots=True)
class ActionRuleAssignment:
    transition_id: str
    kind: str
    rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.transition_id, "transition_id")
        if self.kind not in ("integrity", "reaction", "derivation"):
            raise ValueError("unknown rule assignment kind")
        _tuple(self.rule_ids, str, "rule_ids")
        for item in self.rule_ids:
            _text(item, "rule_id")
        object.__setattr__(self, "rule_ids", tuple(sorted(set(self.rule_ids))))


def _assignments(values: tuple[ActionRuleAssignment, ...], name: str) -> None:
    _tuple(values, ActionRuleAssignment, name)
    if len({(item.transition_id, item.kind) for item in values}) != len(values):
        raise ValueError(f"{name} has duplicate transition/kind keys")


@dataclass(frozen=True, slots=True)
class ActionConfiguration:
    rules: tuple[ActionRule, ...]
    assignments: tuple[ActionRuleAssignment, ...] = ()

    def __post_init__(self) -> None:
        _tuple(self.rules, ActionRule, "rules")
        by_id = {rule.id: rule for rule in self.rules}
        if len(by_id) != len(self.rules):
            raise ValueError("duplicate rule ID")
        _assignments(self.assignments, "assignments")
        for assignment in self.assignments:
            for rule_id in assignment.rule_ids:
                if rule_id not in by_id or by_id[rule_id].kind != assignment.kind:
                    raise ValueError(
                        "assignment references an unknown or differently typed rule"
                    )
        object.__setattr__(
            self, "rules", tuple(sorted(self.rules, key=lambda item: item.id))
        )
        object.__setattr__(
            self,
            "assignments",
            tuple(
                sorted(
                    self.assignments, key=lambda item: (item.transition_id, item.kind)
                )
            ),
        )


@dataclass(frozen=True, slots=True)
class ActionConfigurationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.action_configuration.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    updates: tuple[ActionRuleAssignment, ...]

    def __post_init__(self) -> None:
        _assignments(self.updates, "updates")
        object.__setattr__(
            self,
            "updates",
            tuple(
                sorted(self.updates, key=lambda item: (item.transition_id, item.kind))
            ),
        )


@dataclass(frozen=True, slots=True)
class ActionAssignmentDelta:
    transition_id: str
    kind: str
    before_rule_ids: tuple[str, ...] | None
    after_rule_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ActionConfigurationUpdate:
    model_digest: str
    configuration: ActionConfiguration
    changes: tuple[ActionAssignmentDelta, ...]
    expression_evaluation: str = "not_performed"


def update_action_configuration(
    net: ObjectCentricPetriNet,
    configuration: ActionConfiguration,
    spec: ActionConfigurationSpec,
) -> ComputationResult[ActionConfigurationUpdate]:
    """Calculate a rule assignment replacement and exact delta, without mutation.

    An update replaces the whole set for one (transition, rule kind), matching
    the reference's integrity-rule map override. Other kinds are independent.
    Empty rule sets explicitly clear an assignment; absent keys stay distinct
    from present empty sets in delta evidence. All rule expressions are opaque
    metadata, and object-type incidence is checked before assignment.
    """
    if (
        not isinstance(net, ObjectCentricPetriNet)
        or not isinstance(configuration, ActionConfiguration)
        or not isinstance(spec, ActionConfigurationSpec)
    ):
        raise TypeError(
            "expected ObjectCentricPetriNet, ActionConfiguration, and ActionConfigurationSpec"
        )
    transitions = {t.id for t in net.transitions}
    place_types = {p.id: p.object_type for p in net.places}
    known_types = set(place_types.values()) | {kind for _, kind in net.objects}
    incidence = {key: set() for key in transitions}
    for arc in net.arcs:
        transition, place = (
            (arc.target, arc.source)
            if arc.source in place_types
            else (arc.source, arc.target)
        )
        incidence[transition].add(place_types[place])
    rules = {rule.id: rule for rule in configuration.rules}
    if any(rule.object_type not in known_types for rule in configuration.rules):
        raise ValueError("rule references an unknown model object type")
    for assignment in configuration.assignments + spec.updates:
        if assignment.transition_id not in transitions:
            raise ValueError("assignment references an unknown model transition")
        for rule_id in assignment.rule_ids:
            if rule_id not in rules or rules[rule_id].kind != assignment.kind:
                raise ValueError(
                    "assignment references an unknown or differently typed rule"
                )
            if rules[rule_id].object_type not in incidence[assignment.transition_id]:
                raise ValueError(
                    "assigned rule object type is not incident to the transition"
                )
    values = {(a.transition_id, a.kind): a for a in configuration.assignments}
    changes = []
    for update in spec.updates:
        key = update.transition_id, update.kind
        old = values.get(key)
        before = None if old is None else old.rule_ids
        if before != update.rule_ids:
            changes.append(ActionAssignmentDelta(*key, before, update.rule_ids))
        values[key] = update
    digest = model_digest(net)
    result = ActionConfigurationUpdate(
        digest,
        ActionConfiguration(configuration.rules, tuple(values.values())),
        tuple(changes),
    )
    return _derived_result(
        CONFIGURATION_OPERATOR_ID,
        _digest("action-configuration", (digest, configuration)),
        spec,
        ComputeStatus.COMPUTED,
        result,
    )


RESULT_SCHEMAS = {
    CANDIDATES_OPERATOR_ID: (
        "object-action-candidates",
        ActionCandidateSpec,
        ActionCandidates,
    ),
    SCHEDULE_OPERATOR_ID: (
        "object-action-schedule",
        ActionScheduleSpec,
        ActionSchedule,
    ),
    STRUCTURAL_IMPACT_OPERATOR_ID: (
        "object-action-structural-impact",
        StructuralActionImpactSpec,
        StructuralActionImpact,
    ),
    WINDOW_IMPACT_OPERATOR_ID: (
        "object-action-window-impact",
        ActionWindowSpec,
        ActionWindowImpact,
    ),
    CONFIGURATION_OPERATOR_ID: (
        "object-action-configuration",
        ActionConfigurationSpec,
        ActionConfigurationUpdate,
    ),
}

__all__ = (
    "ALLEN_RELATIONS",
    "ConstraintInterval",
    "TemporalPredicate",
    "ActionPattern",
    "ActionCandidate",
    "ActionCandidateSpec",
    "ActionPatternMatch",
    "ActionCandidates",
    "ActionScheduleSpec",
    "ScheduledAction",
    "ActionSchedule",
    "StructuralActionImpactSpec",
    "TypedStructuralImpact",
    "StructuralActionImpact",
    "ActionWindow",
    "ActionWindowSpec",
    "WindowMetric",
    "ActionWindowImpact",
    "allen_relation",
    "propose_actions",
    "schedule_actions",
    "structural_action_impact",
    "compare_action_windows",
    "ActionRule",
    "ActionRuleAssignment",
    "ActionConfiguration",
    "ActionConfigurationSpec",
    "ActionAssignmentDelta",
    "ActionConfigurationUpdate",
    "update_action_configuration",
)
