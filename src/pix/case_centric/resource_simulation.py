"""Bounded job-shop what-if simulation, not arbitrary stochastic Petri nets.

Routes and arrivals are explicit. A ready operation acquires all required
resource units atomically, runs without interruption, and releases them on
completion. Among feasible operations, ready time then input position decides
FIFO priority; infeasible older operations do not reserve resources. Calendars
are absolute half-open availability windows in seconds from a caller-selected
origin. The entire operation must fit one common window. No elapsed time is
silently interpreted as service time, and no causal effect is estimated.
"""

from __future__ import annotations

import heapq
import json
import math
import platform
import random
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import ClassVar

from pix.case_centric.lifecycle import LifecyclePairing
from pix.case_centric.simulation import (
    DurationDistribution,
    FIFOInput,
    _digest,
    _integer,
    _number,
    _text,
    _time_add,
)
from pix.compute._common import _derived_result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class ResourcePool:
    id: str
    capacity: int
    availability_windows: tuple[tuple[float, float], ...] | None = None

    def __post_init__(self) -> None:
        _text(self.id, "resource id")
        _integer(self.capacity, "capacity", 1)
        if self.availability_windows is None:
            return
        if not isinstance(self.availability_windows, tuple):
            raise TypeError("availability_windows must be tuple or None")
        windows = []
        for row in self.availability_windows:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("window must be (start, end)")
            start, end = row
            _number(start, "window start")
            _number(end, "window end")
            if start >= end:
                raise ValueError("availability window requires start < end")
            windows.append((float(start), float(end)))
        merged = []
        for start, end in sorted(windows):
            if merged and start < merged[-1][1]:
                raise ValueError("availability windows must not overlap")
            if merged and start == merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
            else:
                merged.append((start, end))
        object.__setattr__(self, "availability_windows", tuple(merged))


@dataclass(frozen=True, slots=True)
class ResourceSimulationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.resource_simulation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    activity_requirements: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    resource_pools: tuple[ResourcePool, ...]
    activity_durations: tuple[tuple[str, DurationDistribution], ...]
    seed: int = 0
    repetitions: int = 1
    horizon_seconds: float | None = None
    max_dispatches: int = 100000

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be integer")
        _integer(self.repetitions, "repetitions", 1)
        _integer(self.max_dispatches, "max_dispatches", 1)
        if self.horizon_seconds is not None:
            _number(self.horizon_seconds, "horizon_seconds")
            object.__setattr__(self, "horizon_seconds", float(self.horizon_seconds))
        if not isinstance(self.resource_pools, tuple) or not all(
            type(pool) is ResourcePool for pool in self.resource_pools
        ):
            raise TypeError("resource_pools must be tuple of ResourcePool")
        pools = {pool.id for pool in self.resource_pools}
        if len(pools) != len(self.resource_pools):
            raise ValueError("duplicate resource pool")
        object.__setattr__(
            self,
            "resource_pools",
            tuple(sorted(self.resource_pools, key=lambda p: p.id)),
        )
        for name in ("activity_requirements", "activity_durations"):
            rows = getattr(self, name)
            if not isinstance(rows, tuple):
                raise TypeError(f"{name} must be tuple")
            seen = set()
            normalized = []
            for row in rows:
                if not isinstance(row, tuple) or len(row) != 2:
                    raise ValueError("activity configuration must be pairs")
                activity, value = row
                _text(activity, "activity")
                if activity in seen:
                    raise ValueError("duplicate activity configuration")
                seen.add(activity)
                if name == "activity_durations":
                    if type(value) is not DurationDistribution:
                        raise TypeError("expected DurationDistribution")
                else:
                    if not isinstance(value, tuple):
                        raise TypeError("resource requirements must be tuple")
                    used = set()
                    for entry in value:
                        if not isinstance(entry, tuple) or len(entry) != 2:
                            raise ValueError("requirement must be (pool_id, units)")
                        pool, units = entry
                        _text(pool, "pool_id")
                        _integer(units, "required units", 1)
                        if pool not in pools or pool in used:
                            raise ValueError("unknown or duplicate required resource")
                        used.add(pool)
                    value = tuple(sorted(value))
                normalized.append((activity, value))
            object.__setattr__(self, name, tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class ResourceSimulationEvent:
    case_id: str
    event_index: int
    activity: str
    requirements: tuple[tuple[str, int], ...]
    ready_seconds: float
    start_seconds: float
    sampled_service_seconds: float
    planned_completion_seconds: float
    completion_seconds: float | None
    waiting_seconds: float


@dataclass(frozen=True, slots=True)
class ResourceSimulationCase:
    case_id: str
    arrival_seconds: float
    operation_count: int
    completed_operations: int
    completion_seconds: float | None
    status: str
    reason: str | None


@dataclass(frozen=True, slots=True)
class ResourceRepetition:
    repetition: int
    events: tuple[ResourceSimulationEvent, ...]
    cases: tuple[ResourceSimulationCase, ...]
    observation_end_seconds: float
    completed_case_count: int
    mean_completed_flow_seconds: float | None
    total_dispatched_waiting_seconds: float
    throughput_per_second: float | None
    complete: bool


@dataclass(frozen=True, slots=True)
class ResourceSimulation:
    scheduling_profile: str
    calendar_profile: str
    rng_profile: str
    rng_runtime_version: str
    duration_assumption: str
    repetitions: tuple[ResourceRepetition, ...]


def _seed(seed: int, repetition: int, case_id: str, event_index: int) -> int:
    raw = json.dumps(
        [seed, repetition, case_id, event_index],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return int.from_bytes(sha256(raw.encode("utf-8")).digest(), "big")


def _next_open(
    now: float, duration: float, pools: tuple[ResourcePool, ...]
) -> float | None:
    """Find the first full-operation intersection, without reserving capacity."""
    candidate = now
    while True:
        moved = False
        for pool in pools:
            if pool.availability_windows is None:
                continue
            found = False
            for start, end in pool.availability_windows:
                proposed = max(candidate, start)
                # A zero-time operation still requires availability at its start.
                if proposed < end and _time_add(proposed, duration) <= end:
                    found = True
                    if proposed > candidate:
                        candidate = proposed
                        moved = True
                    break
            if not found:
                return None
        if not moved:
            return candidate


def _run(data: FIFOInput, spec: ResourceSimulationSpec, repetition: int):
    requirements = dict(spec.activity_requirements)
    durations = dict(spec.activity_durations)
    pools = {pool.id: pool for pool in spec.resource_pools}
    available = {pool.id: pool.capacity for pool in spec.resource_pools}
    arrivals = sorted((case.arrival_seconds, i) for i, case in enumerate(data.arrivals))
    arrival_index = 0
    # Entries are (ready time, source case position, operation index).
    waiting = []
    running = []
    events = []
    done = [0] * len(data.arrivals)
    completions = {}
    sampled = {}
    now = 0.0
    reason = None
    while True:
        while running and running[0][0] <= now:
            completion, case_index, event_index, record_index = heapq.heappop(running)
            event = events[record_index]
            events[record_index] = replace(event, completion_seconds=completion)
            for pool, units in event.requirements:
                available[pool] += units
            done[case_index] += 1
            if done[case_index] == len(data.arrivals[case_index].activities):
                completions[case_index] = completion
            else:
                waiting.append((completion, case_index, event_index + 1))
        while arrival_index < len(arrivals) and arrivals[arrival_index][0] <= now:
            arrival, case_index = arrivals[arrival_index]
            arrival_index += 1
            if data.arrivals[case_index].activities:
                waiting.append((arrival, case_index, 0))
            else:
                completions[case_index] = arrival
        dispatched = False
        for ready, case_index, event_index in sorted(waiting):
            case = data.arrivals[case_index]
            activity = case.activities[event_index]
            needs = requirements[activity]
            key = case_index, event_index
            if key not in sampled:
                sampled[key] = durations[activity].draw(
                    random.Random(
                        _seed(spec.seed, repetition, case.case_id, event_index)
                    )
                )
            duration = sampled[key]
            if any(available[pool] < units for pool, units in needs):
                continue
            if (
                _next_open(now, duration, tuple(pools[pool] for pool, _ in needs))
                != now
            ):
                continue
            if len(events) >= spec.max_dispatches:
                reason = "dispatch_limit"
                break
            completion = _time_add(now, duration)
            for pool, units in needs:
                available[pool] -= units
            record_index = len(events)
            events.append(
                ResourceSimulationEvent(
                    case.case_id,
                    event_index,
                    activity,
                    needs,
                    ready,
                    now,
                    duration,
                    completion,
                    None,
                    now - ready,
                )
            )
            heapq.heappush(running, (completion, case_index, event_index, record_index))
            waiting.remove((ready, case_index, event_index))
            dispatched = True
            # Complete zero-duration work before assigning the next FIFO slot.
            if completion == now:
                break
        if reason is not None:
            break
        if dispatched:
            continue
        if len(completions) == len(data.arrivals):
            break
        next_times = []
        if running:
            next_times.append(running[0][0])
        if arrival_index < len(arrivals):
            next_times.append(arrivals[arrival_index][0])
        for _, case_index, event_index in waiting:
            activity = data.arrivals[case_index].activities[event_index]
            needs = requirements[activity]
            if any(pools[pool].capacity < units for pool, units in needs):
                continue
            opening = _next_open(
                now,
                sampled[case_index, event_index],
                tuple(pools[pool] for pool, _ in needs),
            )
            if opening is not None and opening > now:
                next_times.append(opening)
        if not next_times:
            reason = "deadlocked"
            break
        next_time = min(next_times)
        if spec.horizon_seconds is not None and next_time > spec.horizon_seconds:
            now = spec.horizon_seconds
            reason = "horizon_limit"
            break
        now = next_time
    rows = []
    for i, case in enumerate(data.arrivals):
        completed = i in completions
        case_reason = None
        if not completed:
            case_reason = reason
            if reason == "deadlocked":
                needs = requirements[case.activities[done[i]]]
                case_reason = (
                    "demand_exceeds_capacity"
                    if any(pools[pool].capacity < units for pool, units in needs)
                    else "no_common_calendar_window"
                )
        rows.append(
            ResourceSimulationCase(
                case.case_id,
                case.arrival_seconds,
                len(case.activities),
                done[i],
                completions.get(i),
                "completed" if completed else reason,
                case_reason,
            )
        )
    elapsed = now - min((case.arrival_seconds for case in data.arrivals), default=0.0)
    flows = [completions[i] - data.arrivals[i].arrival_seconds for i in completions]
    return ResourceRepetition(
        repetition,
        tuple(events),
        tuple(rows),
        now,
        len(completions),
        math.fsum(value / len(flows) for value in flows) if flows else None,
        math.fsum(event.waiting_seconds for event in events),
        len(completions) / elapsed if elapsed > 0 else None,
        len(completions) == len(data.arrivals),
    )


def simulate_resources(
    data: FIFOInput, spec: ResourceSimulationSpec
) -> ComputationResult[ResourceSimulation]:
    """Run explicit arrivals/routes; retain censored cases and planned work.

    Completion is observed only up to the horizon. A dispatched event may have
    a planned completion but no observed completion. Waiting totals cover
    dispatched operations only, not unknown waits of unstarted operations.
    Throughput divides completed cases by the observed interval from first
    arrival; a zero/negative interval has unknown throughput (None).
    """
    if type(data) is not FIFOInput or type(spec) is not ResourceSimulationSpec:
        raise TypeError("expected FIFOInput and ResourceSimulationSpec")
    activities = {activity for case in data.arrivals for activity in case.activities}
    if activities - set(dict(spec.activity_requirements)) or activities - set(
        dict(spec.activity_durations)
    ):
        raise ValueError(
            "every route activity requires explicit resources and duration"
        )
    repetitions = tuple(_run(data, spec, index) for index in range(spec.repetitions))
    reasons = sorted(
        {case.reason for run in repetitions for case in run.cases if case.reason}
    )
    return _derived_result(
        "pix.case_centric.simulate_resources",
        _digest(data),
        spec,
        ComputeStatus.PARTIAL if reasons else ComputeStatus.COMPUTED,
        ResourceSimulation(
            "nonpreemptive-atomic-multipool-feasible-fifo",
            "absolute-half-open-full-operation-windows",
            "python-random-mt19937-sha256-keyed-case-operation-v1",
            platform.python_version(),
            "explicit-caller-distributions-independent-by-case-and-operation",
            repetitions,
        ),
        tuple(
            ComputeIssue(reason, "Some input cases did not complete: " + reason)
            for reason in reasons
        ),
    )


@dataclass(frozen=True, slots=True)
class ResourceComparisonSpec:
    SPEC_TYPE: ClassVar[str] = "pix.resource_scenario_comparison.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    scenarios: tuple[tuple[str, ResourceSimulationSpec], ...]
    common_random_numbers: bool = True
    seed: int = 0
    repetitions: int = 1

    def __post_init__(self) -> None:
        if type(self.common_random_numbers) is not bool or type(self.seed) is not int:
            raise TypeError("common_random_numbers must be bool and seed integer")
        _integer(self.repetitions, "repetitions", 1)
        if not isinstance(self.scenarios, tuple) or len(self.scenarios) < 2:
            raise ValueError("at least two scenarios are required")
        seen = set()
        for row in self.scenarios:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("scenario must be (name, specification)")
            name, spec = row
            _text(name, "scenario name")
            if name in seen or type(spec) is not ResourceSimulationSpec:
                raise ValueError("duplicate scenario or invalid specification")
            seen.add(name)
        horizons = {spec.horizon_seconds for _, spec in self.scenarios}
        if len(horizons) != 1:
            raise ValueError(
                "comparison scenarios must use a common observation horizon"
            )


@dataclass(frozen=True, slots=True)
class ScenarioSimulation:
    name: str
    effective_seed: int
    result: ResourceSimulation


@dataclass(frozen=True, slots=True)
class ScenarioDifference:
    scenario: str
    baseline: str
    repetition: int
    paired_completed_case_ids: tuple[str, ...]
    completed_count_difference: int
    mean_paired_flow_difference_seconds: float | None


@dataclass(frozen=True, slots=True)
class ResourceComparison:
    cohort_case_ids: tuple[str, ...]
    common_random_numbers: bool
    scenarios: tuple[ScenarioSimulation, ...]
    differences: tuple[ScenarioDifference, ...]
    interpretation: str


def compare_resource_scenarios(
    data: FIFOInput, spec: ResourceComparisonSpec
) -> ComputationResult[ResourceComparison]:
    """Paired simulated differences conditional on assumptions, not causation.

    The comparison seed/repetitions override nested scenario values explicitly.
    Common random numbers use the same per-case/operation stream, independent
    of dispatch order. Different distribution families do not promise variance
    reduction. Case-flow differences use only cases completed in both scenarios;
    their IDs and all original censored cases remain in the result.
    """
    if type(data) is not FIFOInput or type(spec) is not ResourceComparisonSpec:
        raise TypeError("expected FIFOInput and ResourceComparisonSpec")
    scenarios, issues, differences = [], [], []
    for name, scenario in spec.scenarios:
        seed = spec.seed if spec.common_random_numbers else _seed(spec.seed, 0, name, 0)
        result = simulate_resources(
            data, replace(scenario, seed=seed, repetitions=spec.repetitions)
        )
        scenarios.append(ScenarioSimulation(name, seed, result.value))
        issues.extend(ComputeIssue(i.code, i.message, (name,)) for i in result.issues)
    baseline = scenarios[0]
    for scenario in scenarios[1:]:
        for left, right in zip(
            baseline.result.repetitions, scenario.result.repetitions
        ):
            paired = [
                (a, b)
                for a, b in zip(left.cases, right.cases)
                if a.completion_seconds is not None and b.completion_seconds is not None
            ]
            differences.append(
                ScenarioDifference(
                    scenario.name,
                    baseline.name,
                    left.repetition,
                    tuple(a.case_id for a, _ in paired),
                    right.completed_case_count - left.completed_case_count,
                    math.fsum(
                        (b.completion_seconds - a.completion_seconds) / len(paired)
                        for a, b in paired
                    )
                    if paired
                    else None,
                )
            )
    return _derived_result(
        "pix.case_centric.compare_resource_scenarios",
        _digest(data),
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        ResourceComparison(
            tuple(case.case_id for case in data.arrivals),
            spec.common_random_numbers,
            tuple(scenarios),
            tuple(differences),
            "simulation-only-conditional-on-explicit-inputs-not-a-causal-estimate",
        ),
        tuple(issues),
    )


@dataclass(frozen=True, slots=True)
class ResourceDurationFitSpec:
    SPEC_TYPE: ClassVar[str] = "pix.resource_duration_fit.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    assumed_family: str = "fixed"

    def __post_init__(self) -> None:
        if self.assumed_family not in ("fixed", "exponential"):
            raise ValueError("assumed_family must be fixed or exponential")


@dataclass(frozen=True, slots=True)
class FittedResourceDuration:
    activity: str
    observed_count: int
    unknown_duration_count: int
    observed_mean_seconds: float | None
    assumed_distribution: DurationDistribution | None


@dataclass(frozen=True, slots=True)
class ResourceDurationFit:
    activities: tuple[FittedResourceDuration, ...]
    unmatched_source_event_count: int
    interpretation: str


def fit_resource_durations(
    pairing: ComputationResult[LifecyclePairing],
    spec: ResourceDurationFitSpec = ResourceDurationFitSpec(),
) -> ComputationResult[ResourceDurationFit]:
    """Fit a mean only from paired lifecycle service intervals.

    The distribution family is a user assumption; no goodness-of-fit claim is
    made. Zero observed means cannot parameterize an exponential distribution.
    Missing endpoints and unmatched lifecycle records remain coverage evidence.
    An unmatched record of the same case/activity inside an interval makes its
    service duration unknown: elapsed start-to-complete time can include pauses.
    Unmatched records have no trustworthy instance identity, so this exclusion
    is deliberately conservative even for explicitly instance-paired intervals.
    Routing, arrival rates and resource ownership are not inferred here.
    """
    if (
        not isinstance(pairing, ComputationResult)
        or not isinstance(pairing.value, LifecyclePairing)
        or type(spec) is not ResourceDurationFitSpec
    ):
        raise TypeError(
            "expected computed LifecyclePairing and ResourceDurationFitSpec"
        )
    groups = {}
    interrupted = set()
    for interval in pairing.value.intervals:
        unresolved = any(
            event.trace_id == interval.trace_id
            and event.activity == interval.activity
            and interval.start_position
            < event.source_position
            < interval.complete_position
            for event in pairing.value.unmatched
        )
        if unresolved:
            interrupted.add(interval.activity)
        groups.setdefault(interval.activity, []).append(
            None if unresolved else interval.service_seconds
        )
    rows, issues = [], list(pairing.issues)
    for activity, values in sorted(groups.items()):
        if activity in interrupted:
            issues.append(
                ComputeIssue(
                    "interrupted_service_interval",
                    "Unresolved lifecycle records inside an interval prevent service-time inference",
                    (activity,),
                )
            )
        observed = [value for value in values if value is not None]
        mean = (
            math.fsum(value / len(observed) for value in observed) if observed else None
        )
        distribution = None
        if mean is not None and (spec.assumed_family != "exponential" or mean > 0):
            distribution = DurationDistribution(spec.assumed_family, mean)
        if distribution is None:
            issues.append(
                ComputeIssue(
                    "unfittable_duration", "No valid mean parameter", (activity,)
                )
            )
        if len(observed) != len(values):
            issues.append(
                ComputeIssue(
                    "unknown_service_duration", "Missing service intervals", (activity,)
                )
            )
        rows.append(
            FittedResourceDuration(
                activity, len(observed), len(values) - len(observed), mean, distribution
            )
        )
    if pairing.value.unmatched:
        issues.append(
            ComputeIssue(
                "unmatched_lifecycle_events",
                "Unmatched records were not treated as zero duration",
            )
        )
    return _derived_result(
        "pix.case_centric.fit_resource_durations",
        pairing.source_digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        ResourceDurationFit(
            tuple(rows),
            len(pairing.value.unmatched),
            "observed-lifecycle-means-with-user-assumed-distribution-family",
        ),
        tuple(issues),
        parent_computation_ids=(pairing.computation_id,),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.simulate_resources": (
        "case-resource-simulation",
        ResourceSimulationSpec,
        ResourceSimulation,
    ),
    "pix.case_centric.compare_resource_scenarios": (
        "case-resource-comparison",
        ResourceComparisonSpec,
        ResourceComparison,
    ),
    "pix.case_centric.fit_resource_durations": (
        "case-resource-duration-fit",
        ResourceDurationFitSpec,
        ResourceDurationFit,
    ),
}

__all__ = (
    "ResourcePool",
    "ResourceSimulationSpec",
    "ResourceSimulationEvent",
    "ResourceSimulationCase",
    "ResourceRepetition",
    "ResourceSimulation",
    "simulate_resources",
    "ResourceComparisonSpec",
    "ScenarioSimulation",
    "ScenarioDifference",
    "ResourceComparison",
    "compare_resource_scenarios",
    "ResourceDurationFitSpec",
    "FittedResourceDuration",
    "ResourceDurationFit",
    "fit_resource_durations",
)
