"""Typed extended-net contracts and explicit, local execution semantics.

Reset/inhibitor nets use a restricted incidence profile: each place/transition
input pair has exactly one of ordinary, reset or inhibitor semantics. Output
arcs may return tokens to reset or inhibited places. Enabling observes the
pre-firing marking; firing consumes ordinary inputs, clears reset places, then
produces outputs atomically. No token bound or reachability claim is implied.

The stochastic profile chooses a structurally enabled transition using relative
weights and then samples its serial duration in seconds. Weights are not rates;
there is no race, concurrent timing, GSPN priority or memory policy. This is a
persistable model separate from simulation call options. Zero enabled weight
mass is an error, rather than an implicit uniform-choice assumption.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import ClassVar, Literal

from pix.case_centric.simulation import DurationDistribution
from pix.compute.model_semantics import enabled_transitions, fire
from pix.contracts.models import Marking, PetriNet


def _text(value: object, name: str) -> None:
    if type(value) is not str:
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must be nonblank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must contain valid Unicode") from exc


def _tuple(value: object, kind: type, name: str) -> None:
    if type(value) is not tuple or any(type(item) is not kind for item in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


@dataclass(frozen=True, slots=True, order=True)
class ResetArc:
    """Place-to-transition input that clears all tokens, including zero."""

    source: str
    target: str

    def __post_init__(self) -> None:
        _text(self.source, "ResetArc.source")
        _text(self.target, "ResetArc.target")


@dataclass(frozen=True, slots=True, order=True)
class InhibitorArc:
    """Enable only when pre-firing M(source) < threshold; consume nothing."""

    source: str
    target: str
    threshold: int = 1

    def __post_init__(self) -> None:
        _text(self.source, "InhibitorArc.source")
        _text(self.target, "InhibitorArc.target")
        if type(self.threshold) is not int:
            raise TypeError("InhibitorArc.threshold must be an integer")
        if self.threshold < 1:
            raise ValueError("InhibitorArc.threshold must be positive")


@dataclass(frozen=True, slots=True)
class ResetInhibitorNet:
    """Weighted P/T structure plus exclusive typed reset/inhibitor inputs.

    This wrapper is deliberately not a PetriNet subtype. Passing it to ordinary
    P/T conformance or soundness operations must not discard its extra arcs.
    The contained ``net`` is the ordinary incidence component, not an equivalent
    executable model. Multiple arc kinds for the same input pair are rejected.
    """

    net: PetriNet
    reset_arcs: tuple[ResetArc, ...] = ()
    inhibitor_arcs: tuple[InhibitorArc, ...] = ()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if type(self.net) is not PetriNet:
            raise TypeError("net must be an ordinary PetriNet")
        _tuple(self.reset_arcs, ResetArc, "reset_arcs")
        _tuple(self.inhibitor_arcs, InhibitorArc, "inhibitor_arcs")
        places = {p.id for p in self.net.places}
        transitions = {t.id for t in self.net.transitions}
        seen = {(a.source, a.target) for a in self.net.arcs}
        for arc in (*self.reset_arcs, *self.inhibitor_arcs):
            if arc.source not in places or arc.target not in transitions:
                raise ValueError("extended arc must connect a place to a transition")
            pair = arc.source, arc.target
            if pair in seen:
                raise ValueError("duplicate or conflicting input arc incidence")
            seen.add(pair)
        object.__setattr__(self, "reset_arcs", tuple(sorted(self.reset_arcs)))
        object.__setattr__(self, "inhibitor_arcs", tuple(sorted(self.inhibitor_arcs)))

    def validate_marking(self, marking: Marking) -> None:
        self.net.validate_marking(marking)


def _reset_input(net: ResetInhibitorNet, marking: Marking) -> dict[str, int]:
    if type(net) is not ResetInhibitorNet:
        raise TypeError("net must be a ResetInhibitorNet")
    net.validate_marking(marking)
    return dict(marking.tokens)


def _known_transition(net: PetriNet, transition_id: str) -> None:
    _text(transition_id, "transition_id")
    if not any(t.id == transition_id for t in net.transitions):
        raise ValueError(f"unknown transition: {transition_id}")


def _reset_enabled(
    net: ResetInhibitorNet, counts: dict[str, int], transition_id: str
) -> bool:
    return all(
        counts.get(a.source, 0) >= a.weight
        for a in net.net.arcs
        if a.target == transition_id
    ) and all(
        counts.get(a.source, 0) < a.threshold
        for a in net.inhibitor_arcs
        if a.target == transition_id
    )


def reset_inhibitor_is_enabled(
    net: ResetInhibitorNet, marking: Marking, transition_id: str
) -> bool:
    counts = _reset_input(net, marking)
    _known_transition(net.net, transition_id)
    return _reset_enabled(net, counts, transition_id)


def reset_inhibitor_enabled_transitions(
    net: ResetInhibitorNet, marking: Marking
) -> tuple[str, ...]:
    counts = _reset_input(net, marking)
    return tuple(t.id for t in net.net.transitions if _reset_enabled(net, counts, t.id))


def fire_reset_inhibitor(
    net: ResetInhibitorNet, marking: Marking, transition_id: str
) -> Marking:
    """Check old M; consume ordinary inputs, reset, produce into a new M."""
    counts = _reset_input(net, marking)
    _known_transition(net.net, transition_id)
    if not _reset_enabled(net, counts, transition_id):
        raise ValueError(f"transition is not enabled: {transition_id}")
    for arc in net.net.arcs:
        if arc.target == transition_id:
            counts[arc.source] -= arc.weight
    for arc in net.reset_arcs:
        if arc.target == transition_id:
            counts[arc.source] = 0
    for arc in net.net.arcs:
        if arc.source == transition_id:
            counts[arc.target] = counts.get(arc.target, 0) + arc.weight
    return Marking(tuple((p, n) for p, n in counts.items() if n))


@dataclass(frozen=True, slots=True)
class ParameterSource:
    """Declared origin, not a certificate that PIX learned the parameter.

    Learned parameters require a reference, such as a result digest or a named
    estimation record. Assumptions may carry an explanatory reference as well.
    """

    kind: Literal["assumed", "learned"] = "assumed"
    reference: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("assumed", "learned"):
            raise ValueError("parameter source must be assumed or learned")
        if self.reference is not None:
            _text(self.reference, "source reference")
        if self.kind == "learned" and self.reference is None:
            raise ValueError("learned parameters require a source reference")


@dataclass(frozen=True, slots=True)
class StochasticTransition:
    transition_id: str
    weight: float
    duration: DurationDistribution
    weight_origin: ParameterSource = ParameterSource()
    duration_origin: ParameterSource = ParameterSource()

    def __post_init__(self) -> None:
        _text(self.transition_id, "transition_id")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise TypeError("weight must be finite numeric")
        try:
            weight = float(self.weight)
        except OverflowError as exc:
            raise ValueError("weight must be finite and nonnegative") from exc
        if not math.isfinite(weight) or weight < 0:
            raise ValueError("weight must be finite and nonnegative")
        if type(self.duration) is not DurationDistribution:
            raise TypeError("duration must be DurationDistribution")
        for name in ("weight_origin", "duration_origin"):
            if type(getattr(self, name)) is not ParameterSource:
                raise TypeError(f"{name} must be ParameterSource")
        object.__setattr__(self, "weight", weight)


@dataclass(frozen=True, slots=True)
class StochasticPetriNet:
    """Complete per-transition weights and serial durations over a P/T net.

    Parameters cover every transition, including silent ones. Zero weights are
    allowed but do not change structural enabling. No defaults are invented
    for missing rows. Probabilities use finite floating-point arithmetic;
    ratios below that range may underflow to zero.
    """

    net: PetriNet
    parameters: tuple[StochasticTransition, ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if type(self.net) is not PetriNet:
            raise TypeError("net must be an ordinary PetriNet")
        _tuple(self.parameters, StochasticTransition, "parameters")
        ids = [p.transition_id for p in self.parameters]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate stochastic transition parameters")
        if set(ids) != {t.id for t in self.net.transitions}:
            raise ValueError("parameters must cover exactly the net's transitions")
        object.__setattr__(
            self,
            "parameters",
            tuple(sorted(self.parameters, key=lambda p: p.transition_id)),
        )

    def validate_marking(self, marking: Marking) -> None:
        self.net.validate_marking(marking)


def stochastic_transition_probabilities(
    net: StochasticPetriNet, marking: Marking
) -> tuple[tuple[str, float], ...]:
    """Local weighted choice, empty for deadlock; reject zero enabled mass.

    Exact final marking is not treated as absorbing by this local operation.
    A complete-run simulator must apply its declared termination policy.
    """
    if type(net) is not StochasticPetriNet:
        raise TypeError("net must be a StochasticPetriNet")
    ids = enabled_transitions(net.net, marking)
    if not ids:
        return ()
    weights = {p.transition_id: p.weight for p in net.parameters}
    scale = max(weights[t] for t in ids)
    if scale == 0:
        raise ValueError("enabled transitions have no positive stochastic weight")
    scaled = tuple(weights[t] / scale for t in ids)
    total = math.fsum(scaled)
    return tuple((t, w / total) for t, w in zip(ids, scaled))


@dataclass(frozen=True, slots=True)
class StochasticStep:
    transition_id: str
    activity: str | None
    duration_seconds: float
    marking: Marking

    def __post_init__(self) -> None:
        _text(self.transition_id, "transition_id")
        if self.activity is not None:
            _text(self.activity, "activity")
        if isinstance(self.duration_seconds, bool) or not isinstance(
            self.duration_seconds, (float, int)
        ):
            raise TypeError("duration_seconds must be finite numeric")
        try:
            duration = float(self.duration_seconds)
        except OverflowError as exc:
            raise ValueError("duration_seconds must be finite and nonnegative") from exc
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("duration_seconds must be finite and nonnegative")
        if type(self.marking) is not Marking:
            raise TypeError("marking must be a Marking")
        object.__setattr__(self, "duration_seconds", duration)


def sample_stochastic_step(
    net: StochasticPetriNet, marking: Marking, *, seed: int
) -> StochasticStep:
    """Sample one reproducible weighted transition then its serial duration.

    Reusing a seed repeats the same random stream; callers generating paths
    must supply independent per-step seeds. This function is not a timed race.
    """
    if type(seed) is not int:
        raise TypeError("seed must be an explicit integer")
    probabilities = stochastic_transition_probabilities(net, marking)
    if not probabilities:
        raise ValueError("no structurally enabled transition")
    rng = random.Random(seed)
    ids, weights = zip(*probabilities)
    transition = rng.choices(ids, weights=weights, k=1)[0]
    parameter = next(p for p in net.parameters if p.transition_id == transition)
    duration = parameter.duration.draw(rng)
    label = next(t.activity for t in net.net.transitions if t.id == transition)
    return StochasticStep(
        transition, label, duration, fire(net.net, marking, transition)
    )


@dataclass(frozen=True, slots=True)
class ExtendedNetCapabilities:
    model_type: str
    semantics: str
    supported_operations: tuple[str, ...]
    unsupported_operations: tuple[str, ...]


def extended_model_capabilities(
    model: ResetInhibitorNet | StochasticPetriNet,
) -> ExtendedNetCapabilities:
    """An operation boundary, never a soundness or replacement certificate."""
    unsupported = (
        "ordinary-petri-net-conformance",
        "alignments",
        "woflan-soundness",
        "complete-reachability",
    )
    if type(model) is ResetInhibitorNet:
        return ExtendedNetCapabilities(
            "reset-inhibitor-net",
            "exclusive-input-incidence.atomic-reset-after-consume-before-produce.v1",
            ("typed-persistence", "enabling", "atomic-firing"),
            unsupported,
        )
    if type(model) is StochasticPetriNet:
        return ExtendedNetCapabilities(
            "stochastic-petri-net",
            "weighted-choice.serial-duration.zero-mass-error.v1",
            (
                "typed-persistence",
                "local-transition-probabilities",
                "sampled-serial-step",
                "nonpreemptive-reservation-timed-playout",
            ),
            unsupported + ("timed-race", "gspn"),
        )
    raise TypeError("model must be ResetInhibitorNet or StochasticPetriNet")


__all__ = (
    "ResetArc",
    "InhibitorArc",
    "ResetInhibitorNet",
    "ParameterSource",
    "StochasticTransition",
    "StochasticPetriNet",
    "StochasticStep",
    "ExtendedNetCapabilities",
    "reset_inhibitor_is_enabled",
    "reset_inhibitor_enabled_transitions",
    "fire_reset_inhibitor",
    "stochastic_transition_probabilities",
    "sample_stochastic_step",
    "extended_model_capabilities",
)
