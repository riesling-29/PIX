"""Bounded timed P/T playout with input reservation and delayed outputs.

This PIX profile samples weighted dispatch choices, then transition durations.
It is not a GSPN exponential race: inputs are consumed at start, outputs appear
on completion, running instances cannot be interrupted, and independent
instances may overlap. Every completion at an identical floating-point time is
applied as one batch before another dispatch. A zero-duration start creates a
new completion batch at the same clock value, before the next dispatch.

Time is finite binary64 seconds relative to zero. Equality of these numbers,
not a tolerance, defines completion ties. No datetime conversion, timestamp
rounding or artificial order between tied completions is exported. The event
sequence records dispatch order; completion order can differ.
"""

from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import ClassVar

from pix.case_centric.extended_nets import StochasticPetriNet, StochasticTransition
from pix.case_centric.simulation import _digest
from pix.compute._common import _derived_result
from pix.contracts.models import Marking
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class TimedPlayoutSpec:
    """Bounds apply separately to every requested run; no sample is discarded.

    ``max_starts`` prevents further starts but lets admitted instances finish.
    An optional horizon admits completions at the boundary, but no starts at
    that boundary. Thus a horizon of zero observes only the initial marking.
    """

    SPEC_TYPE: ClassVar[str] = "pix.timed_petri_playout.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    seed: int = 0
    samples: int = 100
    max_starts: int = 1000
    horizon_seconds: float | None = None

    def __post_init__(self) -> None:
        if type(self.seed) is not int:
            raise TypeError("seed must be an explicit integer")
        for name in ("samples", "max_starts"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.horizon_seconds is not None:
            if isinstance(self.horizon_seconds, bool) or not isinstance(
                self.horizon_seconds, (int, float)
            ):
                raise TypeError("horizon_seconds must be finite numeric")
            try:
                horizon = float(self.horizon_seconds)
            except OverflowError as exc:
                raise ValueError("horizon_seconds must be finite") from exc
            if not math.isfinite(horizon) or horizon < 0:
                raise ValueError("horizon_seconds must be finite and nonnegative")
            object.__setattr__(self, "horizon_seconds", horizon)


@dataclass(frozen=True, slots=True)
class TimedTransitionExecution:
    """One reserved transition instance, including censored in-flight work."""

    execution_index: int
    transition_id: str
    activity: str | None
    start_seconds: float
    sampled_duration_seconds: float
    planned_completion_seconds: float
    completion_seconds: float | None


@dataclass(frozen=True, slots=True)
class TimedPlayoutRun:
    sample_index: int
    events: tuple[TimedTransitionExecution, ...]
    terminal_marking: Marking
    observation_end_seconds: float
    completion_seconds: float | None
    status: str
    in_flight_execution_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TimedPlayout:
    """All runs, including deadlocked, weight-blocked and bounded witnesses.

    ``complete`` means no observation was censored by a configured bound. It
    does not assert acceptance, soundness, exhaustiveness or model realism.
    Parameter origins are declarations, not evidence of successful estimation.
    """

    scheduling_profile: str
    rng_profile: str
    time_profile: str
    parameters: tuple[StochasticTransition, ...]
    runs: tuple[TimedPlayoutRun, ...]
    accepted_run_count: int
    complete: bool


def _run_seed(seed: int, sample_index: int) -> int:
    # A stable per-run stream keeps a prefix identical if samples is increased.
    material = f"pix.timed-petri.v1:{seed}:{sample_index}".encode("ascii")
    return int.from_bytes(sha256(material).digest(), "big")


def _run(
    model: StochasticPetriNet, spec: TimedPlayoutSpec, sample_index: int
) -> TimedPlayoutRun:
    net = model.net
    rng = random.Random(_run_seed(spec.seed, sample_index))
    parameters = {row.transition_id: row for row in model.parameters}
    transition_ids = tuple(row.id for row in net.transitions)
    labels = {row.id: row.activity for row in net.transitions}
    inputs = {transition_id: [] for transition_id in transition_ids}
    outputs = {transition_id: [] for transition_id in transition_ids}
    for arc in net.arcs:
        if arc.target in inputs:
            inputs[arc.target].append((arc.source, arc.weight))
        else:
            outputs[arc.source].append((arc.target, arc.weight))
    marking = dict(net.initial_marking.tokens)
    clock = 0.0
    events: list[TimedTransitionExecution] = []
    pending: list[tuple[float, int]] = []
    horizon = spec.horizon_seconds

    def current_marking() -> Marking:
        return Marking(
            tuple((place, count) for place, count in marking.items() if count)
        )

    while True:
        # All completions already scheduled at this clock precede dispatch.
        # Their additive output effects commute; execution_index is only a
        # reproducible serialization order, not an inferred causal order.
        while pending and pending[0][0] == clock:
            completion, index = heapq.heappop(pending)
            event = events[index]
            for place, weight in outputs[event.transition_id]:
                marking[place] = marking.get(place, 0) + weight
            events[index] = replace(event, completion_seconds=completion)

        if not pending and current_marking() == net.final_marking:
            status = "accepted"
            break

        enabled = tuple(
            transition_id
            for transition_id in transition_ids
            if all(
                marking.get(place, 0) >= weight
                for place, weight in inputs[transition_id]
            )
        )
        dispatchable = tuple(
            transition_id
            for transition_id in enabled
            if parameters[transition_id].weight > 0
        )

        if not pending and not dispatchable:
            # Zero weights never silently become a uniform choice. Unlike the
            # one-step sampler, a complete simulator retains this outcome.
            status = "weight_deadlock" if enabled else "deadlocked"
            break

        if horizon is not None and clock >= horizon:
            status = "horizon_limit"
            break

        if dispatchable and len(events) < spec.max_starts:
            scale = max(parameters[t].weight for t in dispatchable)
            weights = [parameters[t].weight / scale for t in dispatchable]
            transition = rng.choices(dispatchable, weights=weights, k=1)[0]
            duration = parameters[transition].duration.draw(rng)
            completion = clock + duration
            if not math.isfinite(duration) or not math.isfinite(completion):
                raise ValueError(
                    "sampled duration or simulated time exceeds finite range"
                )
            if duration > 0 and completion == clock:
                raise ValueError(
                    "positive duration is below simulated clock resolution"
                )
            # Consume only after duration validation, before any next dispatch.
            for place, weight in inputs[transition]:
                marking[place] -= weight
            index = len(events)
            events.append(
                TimedTransitionExecution(
                    index,
                    transition,
                    labels[transition],
                    clock,
                    duration,
                    completion,
                    None,
                )
            )
            heapq.heappush(pending, (completion, index))
            continue

        if pending:
            next_completion = pending[0][0]
            if horizon is not None and next_completion > horizon:
                clock = horizon
                status = "horizon_limit"
                break
            clock = next_completion
            continue

        status = "start_limit"
        break

    return TimedPlayoutRun(
        sample_index,
        tuple(events),
        current_marking(),
        clock,
        clock if status == "accepted" else None,
        status,
        tuple(sorted(index for _, index in pending)),
    )


def playout_timed_petri_net(
    model: StochasticPetriNet, spec: TimedPlayoutSpec = TimedPlayoutSpec()
) -> ComputationResult[TimedPlayout]:
    """Sample bounded concurrent executions under PIX reservation semantics.

    Relative weights govern dispatch conflicts; durations do not decide which
    conflicting transition wins. Structural enabling with only zero weights
    waits for in-flight completions, or ends in ``weight_deadlock`` when none
    remain. All requested runs are retained. Bound-limited observations yield
    PARTIAL; an observed deadlock is a computed outcome, never an accepted run.

    Nonfinite time, or a positive duration too small to advance the current
    floating-point clock, raises ValueError instead of fabricating timestamps.
    ``seed`` reproduces this algorithm's random stream in the same supported
    Python runtime; equivalence to another library's seed is not asserted.
    """
    if type(model) is not StochasticPetriNet or type(spec) is not TimedPlayoutSpec:
        raise TypeError("expected StochasticPetriNet and TimedPlayoutSpec")
    runs = tuple(_run(model, spec, index) for index in range(spec.samples))
    limits = sorted({run.status for run in runs if run.status.endswith("_limit")})
    issues = tuple(
        ComputeIssue(
            f"timed_playout_{reason}",
            "Timed playout continuation is unknown after " + reason,
        )
        for reason in limits
    )
    if any(run.status == "weight_deadlock" for run in runs):
        issues += (
            ComputeIssue(
                "timed_playout_zero_enabled_weight",
                "Structurally enabled transitions had no positive dispatch weight; "
                "the blocked runs are retained without a uniform fallback",
            ),
        )
    value = TimedPlayout(
        "nonpreemptive-input-reservation-completion-batches-v1",
        "python-random-weighted-dispatch-sha256-per-run-v1",
        "finite-binary64-seconds-exact-ties-no-datetime-conversion",
        model.parameters,
        runs,
        sum(run.status == "accepted" for run in runs),
        not limits,
    )
    return _derived_result(
        "pix.case_centric.playout_timed_petri_net",
        _digest(model),
        spec,
        ComputeStatus.PARTIAL if limits else ComputeStatus.COMPUTED,
        value,
        issues,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.playout_timed_petri_net": (
        "case-timed-petri-playout",
        TimedPlayoutSpec,
        TimedPlayout,
    ),
}

__all__ = (
    "TimedPlayoutSpec",
    "TimedTransitionExecution",
    "TimedPlayoutRun",
    "TimedPlayout",
    "playout_timed_petri_net",
)
