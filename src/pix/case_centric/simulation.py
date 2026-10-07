"""Native, seeded simulation with explicit finite exploration boundaries.

Petri-net sampling chooses enabled transitions by nonnegative relative weights;
these weights are probabilities, not rates of a timed stochastic Petri net.
Extensive playout enumerates visible-language witnesses, collapsing states
with the same marking and visible prefix. The exact final marking terminates
a run. Reaching a bound is evidence of an unknown continuation, never success.
FIFO simulation schedules sequential case routes on named resource pools;
there is no preemption, resource acquisition in groups, or inferred duration.
"""

from __future__ import annotations

import heapq
import json
import math
import random
from collections import deque
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _number(value: float, name: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise TypeError(f"{name} must be finite numeric")
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError(
            f"{name} must be {'positive' if positive else 'nonnegative'} and finite"
        )


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")


def _digest(value: object) -> str:
    return sha256(
        json.dumps(
            asdict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _choice(rng: random.Random, items: list | tuple, weights: list | tuple):
    # Finite individual weights may have an overflowing sum. Scaling preserves
    # their relative probabilities within floating-point precision.
    scale = max(weights)
    if scale == 0:
        return rng.choice(items)
    return rng.choices(items, [weight / scale for weight in weights], k=1)[0]


def _time_add(start: float, duration: float) -> float:
    end = start + duration
    if not math.isfinite(end):
        raise ValueError("simulated time exceeds finite numeric range")
    return end


def _finish(
    operator: str,
    source: str,
    spec: object,
    value: object,
    reasons: tuple[str, ...] = (),
) -> ComputationResult:
    issues = tuple(
        ComputeIssue(code, "Simulation continuation is unknown: " + code)
        for code in sorted(set(reasons))
    )
    return _derived_result(
        operator,
        source,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
    )


@dataclass(frozen=True, slots=True)
class PlayoutSpec:
    SPEC_TYPE: ClassVar[str] = "pix.case_playout.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    mode: str = "sampled"
    seed: int = 0
    samples: int = 100
    max_visible_events: int = 100
    max_steps: int = 1000
    max_states: int = 100000
    transition_weights: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if self.mode not in ("sampled", "exhaustive"):
            raise ValueError("mode must be sampled or exhaustive")
        if type(self.seed) is not int:
            raise TypeError("seed must be an explicit integer")
        for name in ("samples", "max_steps", "max_states"):
            _integer(getattr(self, name), name, 1)
        _integer(self.max_visible_events, "max_visible_events")
        if not isinstance(self.transition_weights, tuple):
            raise TypeError("transition_weights must be a tuple")
        seen = set()
        for row in self.transition_weights:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("weight entry must be (transition_id, weight)")
            key, weight = row
            _text(key, "transition id")
            _number(weight, "transition weight")
            if key in seen:
                raise ValueError("duplicate transition weight")
            seen.add(key)
        object.__setattr__(
            self,
            "transition_weights",
            tuple(
                sorted((key, float(weight)) for key, weight in self.transition_weights)
            ),
        )


@dataclass(frozen=True, slots=True)
class PlayoutRun:
    activities: tuple[str, ...]
    transition_ids: tuple[str, ...]
    terminal_marking: Marking
    status: str


@dataclass(frozen=True, slots=True)
class Playout:
    """Runs include accepted, deadlocked and explicitly truncated witnesses.

    For exhaustive mode, ``complete`` certifies the finite visible language
    under terminal-final semantics; it does not enumerate every silent path.
    For sampled mode it only means every requested sample terminated.
    """

    backend: str
    mode: str
    runs: tuple[PlayoutRun, ...]
    explored_states: int
    complete: bool


def playout_petri_net(
    net: PetriNet, spec: PlayoutSpec = PlayoutSpec()
) -> ComputationResult[Playout]:
    """Seeded basic/weighted sampling or BFS finite visible-language playout.

    Missing weights default to one; if all enabled weights are zero, the
    fallback is uniform choice. Exhaustive mode ignores sampling weights and
    enumerates structurally enabled behavior.
    """
    if not isinstance(net, PetriNet) or type(spec) is not PlayoutSpec:
        raise TypeError("expected PetriNet and PlayoutSpec")
    labels = {t.id: t.activity for t in net.transitions}
    weights = dict(spec.transition_weights)
    if set(weights) - set(labels):
        raise ValueError("transition weights reference unknown transitions")
    runs: list[PlayoutRun] = []
    reasons: list[str] = []
    explored = 0
    if spec.mode == "sampled":
        rng = random.Random(spec.seed)
        for _ in range(spec.samples):
            marking, activities, path = net.initial_marking, (), ()
            while True:
                if explored >= spec.max_states:
                    status = "state_limit"
                    break
                explored += 1
                if marking == net.final_marking:
                    status = "accepted"
                    break
                enabled = enabled_transitions(net, marking)
                if not enabled:
                    status = "deadlocked"
                    break
                if len(path) >= spec.max_steps:
                    status = "step_limit"
                    break
                transition = _choice(
                    rng, enabled, [weights.get(t, 1.0) for t in enabled]
                )
                label = labels[transition]
                if label is not None and len(activities) >= spec.max_visible_events:
                    status = "visible_limit"
                    break
                marking = fire(net, marking, transition)
                path += (transition,)
                if label is not None:
                    activities += (label,)
            runs.append(PlayoutRun(activities, path, marking, status))
            if status.endswith("limit"):
                reasons.append(status)
            if status == "state_limit":
                break
    else:
        queue = deque([(net.initial_marking, (), ())])
        seen = {(net.initial_marking, ())}
        while queue:
            marking, activities, path = queue.popleft()
            explored += 1
            if marking == net.final_marking:
                runs.append(PlayoutRun(activities, path, marking, "accepted"))
                continue
            enabled = enabled_transitions(net, marking)
            if not enabled:
                runs.append(PlayoutRun(activities, path, marking, "deadlocked"))
                continue
            for transition in enabled:
                label = labels[transition]
                next_activities = activities + ((label,) if label is not None else ())
                next_marking = fire(net, marking, transition)
                key = next_marking, next_activities
                if key in seen:
                    continue
                reason = (
                    "visible_limit"
                    if len(next_activities) > spec.max_visible_events
                    else "step_limit"
                    if len(path) >= spec.max_steps
                    else "state_limit"
                    if len(seen) >= spec.max_states
                    else None
                )
                if reason:
                    runs.append(PlayoutRun(activities, path, marking, reason))
                    reasons.append(reason)
                    continue
                seen.add(key)
                queue.append((next_marking, next_activities, path + (transition,)))
    value = Playout(
        "weighted-place-transition-net", spec.mode, tuple(runs), explored, not reasons
    )
    return _finish(
        "pix.case_centric.playout_petri_net",
        model_digest(net),
        spec,
        value,
        tuple(reasons),
    )


def playout_process_tree(
    tree: ProcessTree, spec: PlayoutSpec = PlayoutSpec()
) -> ComputationResult[Playout]:
    """Execute PIX's language-preserving tree-to-Petri-net conversion.

    Sampling follows enabled net transitions, not uniform sampling over trees,
    traces or branch choices. Parallel interleavings therefore need not be
    equiprobable. The backend is named in the output.
    """
    if not isinstance(tree, ProcessTree):
        raise TypeError("tree must be ProcessTree")
    result = playout_petri_net(process_tree_to_petri_net(tree), spec)
    value = Playout(
        "process-tree-via-petri-net",
        result.value.mode,
        result.value.runs,
        result.value.explored_states,
        result.value.complete,
    )
    return _finish(
        "pix.case_centric.playout_process_tree",
        _digest(tree),
        spec,
        value,
        tuple(issue.code for issue in result.issues),
    )


@dataclass(frozen=True, slots=True)
class DurationDistribution:
    """Seconds: fixed(value), exponential(mean), uniform(lower, upper).

    Explicit zero-duration fixed/uniform activities are allowed. Exponential
    distributions require a strictly positive mean.
    """

    kind: str = "fixed"
    value: float = 0.0
    upper: float | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("fixed", "exponential", "uniform"):
            raise ValueError("unsupported duration distribution")
        _number(self.value, "duration", positive=self.kind == "exponential")
        if self.kind == "uniform":
            if self.upper is None:
                raise ValueError("uniform requires an upper bound")
            _number(self.upper, "upper duration")
            if self.upper < self.value:
                raise ValueError("upper duration must be >= lower duration")
        elif self.upper is not None:
            raise ValueError("upper is only used for uniform distribution")
        object.__setattr__(self, "value", float(self.value))
        if self.upper is not None:
            object.__setattr__(self, "upper", float(self.upper))

    def draw(self, rng: random.Random) -> float:
        if self.kind == "fixed":
            return float(self.value)
        if self.kind == "uniform":
            return rng.uniform(self.value, self.upper)
        duration = rng.expovariate(1.0) * self.value
        if not math.isfinite(duration):
            raise ValueError("sampled duration exceeds finite numeric range")
        return duration


@dataclass(frozen=True, slots=True)
class SimulationDFG:
    """Positive start/end/edge weights; they need not satisfy flow balance."""

    starts: tuple[tuple[str, float], ...]
    ends: tuple[tuple[str, float], ...]
    edges: tuple[tuple[str, str, float], ...]

    def __post_init__(self) -> None:
        for field, width in (("starts", 2), ("ends", 2), ("edges", 3)):
            rows = getattr(self, field)
            if not isinstance(rows, tuple):
                raise TypeError(f"{field} must be a tuple")
            seen = set()
            for row in rows:
                if not isinstance(row, tuple) or len(row) != width:
                    raise ValueError("invalid DFG row")
                for key in row[:-1]:
                    _text(key, "activity")
                _number(row[-1], "DFG weight", positive=True)
                if row[:-1] in seen:
                    raise ValueError("duplicate DFG entry")
                seen.add(row[:-1])
            object.__setattr__(
                self, field, tuple(sorted(row[:-1] + (float(row[-1]),) for row in rows))
            )
        if not self.starts:
            raise ValueError("at least one start activity is required")


@dataclass(frozen=True, slots=True)
class DFGPlayoutSpec:
    SPEC_TYPE: ClassVar[str] = "pix.dfg_playout.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    seed: int = 0
    samples: int = 100
    max_visible_events: int = 100
    activity_durations: tuple[tuple[str, DurationDistribution], ...] = ()
    edge_delays: tuple[tuple[str, str, DurationDistribution], ...] = ()

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be integer")
        _integer(self.samples, "samples", 1)
        _integer(self.max_visible_events, "max_visible_events", 1)
        for field, width in (("activity_durations", 2), ("edge_delays", 3)):
            rows = getattr(self, field)
            if not isinstance(rows, tuple):
                raise TypeError(f"{field} must be tuple")
            seen = set()
            for row in rows:
                if not isinstance(row, tuple) or len(row) != width:
                    raise ValueError("invalid duration row")
                for key in row[:-1]:
                    _text(key, "activity")
                if type(row[-1]) is not DurationDistribution:
                    raise TypeError("expected DurationDistribution")
                if row[:-1] in seen:
                    raise ValueError("duplicate duration key")
                seen.add(row[:-1])
            object.__setattr__(self, field, tuple(sorted(rows)))


@dataclass(frozen=True, slots=True)
class SimulatedEvent:
    activity: str
    start_seconds: float | None
    completion_seconds: float | None


@dataclass(frozen=True, slots=True)
class DFGRun:
    events: tuple[SimulatedEvent, ...]
    status: str


@dataclass(frozen=True, slots=True)
class DFGPlayout:
    runs: tuple[DFGRun, ...]
    timing_profile: str


def playout_dfg(
    graph: SimulationDFG, spec: DFGPlayoutSpec = DFGPlayoutSpec()
) -> ComputationResult[DFGPlayout]:
    """Weighted routing, with an end edge competing against outgoing edges.

    An entirely absent timing profile produces unknown time coordinates
    marked untimed. Once timing is requested, every activity and edge requires
    an explicit distribution; unknown durations are never filled with zero.
    """
    if not isinstance(graph, SimulationDFG) or type(spec) is not DFGPlayoutSpec:
        raise TypeError("expected SimulationDFG and DFGPlayoutSpec")
    activities = set(dict(graph.starts)) | set(dict(graph.ends))
    activities.update(a for edge in graph.edges for a in edge[:2])
    durations = dict(spec.activity_durations)
    delays = {(a, b): d for a, b, d in spec.edge_delays}
    edges = {(a, b) for a, b, _ in graph.edges}
    timed = bool(durations or delays)
    if timed and (set(durations) != activities or set(delays) != edges):
        raise ValueError(
            "performance playout requires every activity duration and edge delay"
        )
    outgoing: dict[str, list[tuple[str | None, float]]] = {a: [] for a in activities}
    for a, b, weight in graph.edges:
        outgoing[a].append((b, weight))
    for a, weight in graph.ends:
        outgoing[a].append((None, weight))
    rng = random.Random(spec.seed)
    runs, reasons = [], []
    for _ in range(spec.samples):
        current = _choice(
            rng, [a for a, _ in graph.starts], [w for _, w in graph.starts]
        )
        now = 0.0
        events = []
        while True:
            duration = durations[current].draw(rng) if timed else 0.0
            completion = _time_add(now, duration)
            events.append(
                SimulatedEvent(
                    current, now if timed else None, completion if timed else None
                )
            )
            now = completion
            choices = outgoing[current]
            if not choices:
                status = "deadlocked"
                break
            next_activity = _choice(
                rng, [a for a, _ in choices], [w for _, w in choices]
            )
            if next_activity is None:
                status = "accepted"
                break
            if len(events) >= spec.max_visible_events:
                status = "visible_limit"
                reasons.append(status)
                break
            if timed:
                now = _time_add(now, delays[current, next_activity].draw(rng))
            current = next_activity
        runs.append(DFGRun(tuple(events), status))
    return _finish(
        "pix.case_centric.playout_dfg",
        _digest(graph),
        spec,
        DFGPlayout(tuple(runs), "explicit-seconds" if timed else "untimed"),
        tuple(reasons),
    )


@dataclass(frozen=True, slots=True)
class DFGEnumerationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.dfg_enumeration.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    max_variants: int = 1000
    max_visible_events: int = 100
    max_occurrences_per_activity: int = 2
    max_states: int = 100000
    target_probability: float = 1.0

    def __post_init__(self) -> None:
        for name in (
            "max_variants",
            "max_visible_events",
            "max_occurrences_per_activity",
            "max_states",
        ):
            _integer(getattr(self, name), name, 1)
        _number(self.target_probability, "target_probability", positive=True)
        if self.target_probability > 1:
            raise ValueError("target_probability must be <= 1")
        object.__setattr__(self, "target_probability", float(self.target_probability))


@dataclass(frozen=True, slots=True)
class ProbabilisticVariant:
    activities: tuple[str, ...]
    probability: float
    log_probability: float


@dataclass(frozen=True, slots=True)
class DFGEnumeration:
    """Unconditioned Markov path mass, never renormalized after pruning.

    Excluded mass belongs to paths crossing an explicit activity/length cap;
    pending mass belongs to queued prefixes when an exploration/result limit
    stops the computation. Either may include not-yet-known nontermination.
    Floating probabilities can underflow; log probabilities remain available
    for emitted variants. No probability error bound is asserted.
    """

    variants: tuple[ProbabilisticVariant, ...]
    explored_states: int
    retained_probability: float
    deadlock_probability: float
    excluded_probability: float
    pending_probability: float
    complete: bool


def _log_weights(weights: tuple[float, ...]) -> tuple[float, ...]:
    logs = tuple(math.log(weight) for weight in weights)
    maximum = max(logs)
    normalization = maximum + math.log(
        math.fsum(math.exp(value - maximum) for value in logs)
    )
    return tuple(value - normalization for value in logs)


def enumerate_dfg(
    graph: SimulationDFG, spec: DFGEnumerationSpec = DFGEnumerationSpec()
) -> ComputationResult[DFGEnumeration]:
    """Best-first enumeration of complete DFG traces by Markov probability.

    A completed trace is queued with its end-edge probability, so output
    probability order is global, not merely the order of parent prefixes.
    Limits preserve retained/excluded/pending probability mass separately.
    No fabricated timestamps or integer trace frequencies are produced.
    """
    if not isinstance(graph, SimulationDFG) or type(spec) is not DFGEnumerationSpec:
        raise TypeError("expected SimulationDFG and DFGEnumerationSpec")
    outgoing: dict[str, list[tuple[str | None, float]]] = {}
    for a, b, weight in graph.edges:
        outgoing.setdefault(a, []).append((b, weight))
    for a, weight in graph.ends:
        outgoing.setdefault(a, []).append((None, weight))
    transitions = {
        a: tuple(
            (row[0], lp)
            for row, lp in zip(rows, _log_weights(tuple(w for _, w in rows)))
        )
        for a, rows in outgoing.items()
    }
    queue = []
    ordinal = 0
    for (activity, _), log_probability in zip(
        graph.starts, _log_weights(tuple(w for _, w in graph.starts))
    ):
        heapq.heappush(queue, (-log_probability, ordinal, (activity,), False))
        ordinal += 1
    variants = []
    deadlock = []
    excluded = []
    reasons = []
    explored = 0
    retained = 0.0
    while queue:
        reason = (
            "state_limit"
            if explored >= spec.max_states
            else "variant_limit"
            if len(variants) >= spec.max_variants
            else "probability_target"
            if retained >= spec.target_probability
            else None
        )
        if reason:
            reasons.append(reason)
            break
        cost, _, activities, terminal = heapq.heappop(queue)
        explored += 1
        if terminal:
            variants.append(ProbabilisticVariant(activities, math.exp(-cost), -cost))
            retained = math.fsum(variant.probability for variant in variants)
            continue
        options = transitions.get(activities[-1], ())
        if not options:
            deadlock.append(math.exp(-cost))
            continue
        for activity, log_probability in options:
            next_cost = cost - log_probability
            if activity is not None and (
                len(activities) >= spec.max_visible_events
                or activities.count(activity) >= spec.max_occurrences_per_activity
            ):
                excluded.append(math.exp(-next_cost))
                reasons.append("activity_or_length_limit")
                continue
            next_activities = (
                activities if activity is None else activities + (activity,)
            )
            heapq.heappush(
                queue, (next_cost, ordinal, next_activities, activity is None)
            )
            ordinal += 1
    value = DFGEnumeration(
        tuple(variants),
        explored,
        retained,
        math.fsum(deadlock),
        math.fsum(excluded),
        math.fsum(math.exp(-item[0]) for item in queue),
        not reasons,
    )
    return _finish(
        "pix.case_centric.enumerate_dfg", _digest(graph), spec, value, tuple(reasons)
    )


@dataclass(frozen=True, slots=True)
class RandomTreeSpec:
    SPEC_TYPE: ClassVar[str] = "pix.random_process_tree.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    seed: int = 0
    activities: tuple[str, ...] = ("A", "B", "C")
    operator_weights: tuple[tuple[str, float], ...] = (
        ("sequence", 1.0),
        ("xor", 1.0),
        ("parallel", 1.0),
    )

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be integer")
        if not isinstance(self.activities, tuple) or not self.activities:
            raise ValueError("activities must be a nonempty tuple")
        if len(self.activities) > 128:
            raise ValueError("random generation supports at most 128 activity leaves")
        for activity in self.activities:
            _text(activity, "activity")
        if not isinstance(self.operator_weights, tuple) or not self.operator_weights:
            raise ValueError("operator_weights must be nonempty tuple")
        seen = set()
        for row in self.operator_weights:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("operator weight must be (operator, weight)")
            operator, weight = row
            if (
                operator not in ("sequence", "xor", "parallel", "loop")
                or operator in seen
            ):
                raise ValueError("unsupported or duplicate operator")
            _number(weight, "operator weight", positive=True)
            seen.add(operator)
        object.__setattr__(
            self,
            "operator_weights",
            tuple(
                sorted((key, float(weight)) for key, weight in self.operator_weights)
            ),
        )


def generate_process_tree(
    spec: RandomTreeSpec = RandomTreeSpec(),
) -> ComputationResult[ProcessTree]:
    """Generate a seeded binary tree using each supplied activity leaf once.

    Recursively choose a split uniformly and an operator by relative weight.
    This is a stated native distribution, not uniform over all process trees.
    Repeated labels are retained as distinct leaves; loop leaves may repeat
    during execution even though each appears once in the model.
    """
    if type(spec) is not RandomTreeSpec:
        raise TypeError("spec must be RandomTreeSpec")
    rng = random.Random(spec.seed)

    def build(labels: tuple[str, ...]) -> ProcessTree:
        if len(labels) == 1:
            return ProcessTree("activity", labels[0])
        split = rng.randrange(1, len(labels))
        operator = _choice(
            rng,
            [a for a, _ in spec.operator_weights],
            [w for _, w in spec.operator_weights],
        )
        return ProcessTree(
            operator, children=(build(labels[:split]), build(labels[split:]))
        )

    return _finish(
        "pix.case_centric.generate_process_tree",
        _digest(spec),
        spec,
        build(spec.activities),
    )


@dataclass(frozen=True, slots=True)
class CaseArrival:
    case_id: str
    arrival_seconds: float
    activities: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _number(self.arrival_seconds, "arrival_seconds")
        object.__setattr__(self, "arrival_seconds", float(self.arrival_seconds))
        if not isinstance(self.activities, tuple):
            raise TypeError("activities must be tuple")
        for activity in self.activities:
            _text(activity, "activity")


@dataclass(frozen=True, slots=True)
class FIFOInput:
    arrivals: tuple[CaseArrival, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.arrivals, tuple) or not all(
            isinstance(a, CaseArrival) for a in self.arrivals
        ):
            raise TypeError("arrivals must be tuple of CaseArrival")
        if len({a.case_id for a in self.arrivals}) != len(self.arrivals):
            raise ValueError("case IDs must be unique")


@dataclass(frozen=True, slots=True)
class FIFOSpec:
    SPEC_TYPE: ClassVar[str] = "pix.fifo_simulation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    activity_resources: tuple[tuple[str, str], ...]
    resource_capacities: tuple[tuple[str, int], ...]
    activity_durations: tuple[tuple[str, DurationDistribution], ...]
    seed: int = 0
    repetitions: int = 1

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be integer")
        _integer(self.repetitions, "repetitions", 1)
        for field in (
            "activity_resources",
            "resource_capacities",
            "activity_durations",
        ):
            rows = getattr(self, field)
            if not isinstance(rows, tuple):
                raise TypeError(f"{field} must be a tuple")
            keys = set()
            for row in rows:
                if not isinstance(row, tuple) or len(row) != 2:
                    raise ValueError("configuration rows must be pairs")
                key, value = row
                _text(key, "configuration key")
                if key in keys:
                    raise ValueError("duplicate configuration key")
                keys.add(key)
                if field == "activity_resources":
                    _text(value, "resource")
                elif field == "resource_capacities":
                    _integer(value, "capacity", 1)
                elif type(value) is not DurationDistribution:
                    raise TypeError("activity duration must be DurationDistribution")
            object.__setattr__(self, field, tuple(sorted(rows)))
        if set(dict(self.activity_resources).values()) - set(
            dict(self.resource_capacities)
        ):
            raise ValueError("activity references undeclared resource pool")


@dataclass(frozen=True, slots=True)
class FIFOEvent:
    case_id: str
    event_index: int
    activity: str
    resource: str
    resource_slot: int
    ready_seconds: float
    start_seconds: float
    completion_seconds: float
    waiting_seconds: float


@dataclass(frozen=True, slots=True)
class FIFORepetition:
    events: tuple[FIFOEvent, ...]
    case_completion_seconds: tuple[tuple[str, float], ...]
    makespan_seconds: float
    total_waiting_seconds: float


@dataclass(frozen=True, slots=True)
class FIFOSimulation:
    scheduling_profile: str
    repetitions: tuple[FIFORepetition, ...]


def simulate_fifo(data: FIFOInput, spec: FIFOSpec) -> ComputationResult[FIFOSimulation]:
    """Monte Carlo nonpreemptive FIFO over fixed sequential case routes.

    Ready jobs are ordered by (ready time, source case position, event index).
    Each consumes one slot of its named pool until completion. Cases can join
    another pool only after their prior event completes. Independent draws use
    one reproducible random stream across repetitions. Makespan is last case
    completion minus the earliest case arrival; empty input has makespan zero.
    """
    if not isinstance(data, FIFOInput) or type(spec) is not FIFOSpec:
        raise TypeError("expected FIFOInput and FIFOSpec")
    resources, capacities, durations = (
        dict(spec.activity_resources),
        dict(spec.resource_capacities),
        dict(spec.activity_durations),
    )
    activities = {activity for case in data.arrivals for activity in case.activities}
    if activities - set(resources) or activities - set(durations):
        raise ValueError("every observed activity requires resource and duration")
    rng = random.Random(spec.seed)
    repetitions = []
    for _ in range(spec.repetitions):
        slots = {
            resource: [(0.0, slot) for slot in range(capacity)]
            for resource, capacity in capacities.items()
        }
        queue = [
            (case.arrival_seconds, index, 0)
            for index, case in enumerate(data.arrivals)
            if case.activities
        ]
        heapq.heapify(queue)
        completed = {
            case.case_id: float(case.arrival_seconds) for case in data.arrivals
        }
        events = []
        while queue:
            ready, case_index, event_index = heapq.heappop(queue)
            case = data.arrivals[case_index]
            activity = case.activities[event_index]
            resource = resources[activity]
            available, slot = heapq.heappop(slots[resource])
            start = max(ready, available)
            completion = _time_add(start, durations[activity].draw(rng))
            heapq.heappush(slots[resource], (completion, slot))
            events.append(
                FIFOEvent(
                    case.case_id,
                    event_index,
                    activity,
                    resource,
                    slot,
                    ready,
                    start,
                    completion,
                    start - ready,
                )
            )
            completed[case.case_id] = completion
            if event_index + 1 < len(case.activities):
                heapq.heappush(queue, (completion, case_index, event_index + 1))
        makespan = (
            (
                max(completed.values())
                - min(case.arrival_seconds for case in data.arrivals)
            )
            if completed
            else 0.0
        )
        total_waiting = 0.0
        for event in events:
            total_waiting = _time_add(total_waiting, event.waiting_seconds)
        repetitions.append(
            FIFORepetition(
                tuple(events), tuple(sorted(completed.items())), makespan, total_waiting
            )
        )
    return _finish(
        "pix.case_centric.simulate_fifo",
        _digest(data),
        spec,
        FIFOSimulation("nonpreemptive-single-pool-per-event-fifo", tuple(repetitions)),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.playout_petri_net": ("case-petri-playout", PlayoutSpec, Playout),
    "pix.case_centric.playout_process_tree": (
        "case-tree-playout",
        PlayoutSpec,
        Playout,
    ),
    "pix.case_centric.playout_dfg": ("case-dfg-playout", DFGPlayoutSpec, DFGPlayout),
    "pix.case_centric.enumerate_dfg": (
        "case-dfg-enumeration",
        DFGEnumerationSpec,
        DFGEnumeration,
    ),
    "pix.case_centric.generate_process_tree": (
        "generated-process-tree",
        RandomTreeSpec,
        ProcessTree,
    ),
    "pix.case_centric.simulate_fifo": (
        "case-fifo-simulation",
        FIFOSpec,
        FIFOSimulation,
    ),
}

__all__ = (
    "PlayoutSpec",
    "PlayoutRun",
    "Playout",
    "playout_petri_net",
    "playout_process_tree",
    "DurationDistribution",
    "SimulationDFG",
    "DFGPlayoutSpec",
    "SimulatedEvent",
    "DFGRun",
    "DFGPlayout",
    "playout_dfg",
    "RandomTreeSpec",
    "generate_process_tree",
    "CaseArrival",
    "DFGEnumerationSpec",
    "ProbabilisticVariant",
    "DFGEnumeration",
    "enumerate_dfg",
    "FIFOInput",
    "FIFOSpec",
    "FIFOEvent",
    "FIFORepetition",
    "FIFOSimulation",
    "simulate_fifo",
)
