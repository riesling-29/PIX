"""Witnesses for finite integer-region discovery.

These witnesses describe the actual integer constraints solved by PIX. They
do not claim that the learned net is sound or the unique generating process.
"""

from __future__ import annotations

from dataclasses import dataclass

from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition


def _nonnegative(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


@dataclass(frozen=True, slots=True)
class IntegerRegion:
    """One feasible place over the alphabet order of the discovery payload.

    ``marking(prefix) = initial + Parikh(prefix) @ (produce - consume)``.
    Initial/final refer to the region after/before artificial start/end, not
    the accepting net's source/sink markings. The capacity bound was checked
    on observed prefixes only; it is not an inhibitor-arc capacity constraint.
    """

    initial: int
    final: int
    consume: tuple[int, ...]
    produce: tuple[int, ...]
    blocked_target_ids: tuple[int, ...]
    arc_weight_cost: int

    def __post_init__(self):
        _nonnegative(self.initial, "initial")
        _nonnegative(self.final, "final")
        for name in ("consume", "produce", "blocked_target_ids"):
            values = getattr(self, name)
            if type(values) is not tuple:
                raise TypeError(f"{name} must be a tuple")
            for value in values:
                _nonnegative(value, name)
        if len(self.consume) != len(self.produce):
            raise ValueError("consume and produce must have equal dimension")
        if self.blocked_target_ids != tuple(sorted(set(self.blocked_target_ids))):
            raise ValueError("blocked_target_ids must be sorted and unique")
        _nonnegative(self.arc_weight_cost, "arc_weight_cost")
        if self.arc_weight_cost != self.initial + self.final + sum(self.consume) + sum(
            self.produce
        ):
            raise ValueError("arc_weight_cost disagrees with region weights")


@dataclass(frozen=True, slots=True)
class SeparationTarget:
    """An unobserved extension of an observed prefix; None denotes completion.

    Unobserved is a synthesis objective, not a declaration that the real
    process forbids this behavior. Multiple prefixes with the same Parikh
    vector can be inseparable by a place/transition region.
    For completion, separation includes residual tokens after the artificial
    end transition; the transition itself need not be disabled.
    """

    prefix: tuple[str, ...]
    next_activity: str | None
    separated: bool

    def __post_init__(self):
        if type(self.prefix) is not tuple or any(
            type(a) is not str or not a.strip() for a in self.prefix
        ):
            raise ValueError("prefix must be a tuple of nonblank activities")
        if self.next_activity is not None and (
            type(self.next_activity) is not str or not self.next_activity.strip()
        ):
            raise ValueError("next_activity must be nonblank text or None")
        if type(self.separated) is not bool:
            raise TypeError("separated must be bool")


def _region_petri_net(alphabet, regions):
    """Canonical accepting-net construction, also checked during decoding."""
    places = [Place("source"), Place("phase"), Place("sink")]
    transitions = [Transition("start"), Transition("end")]
    arcs = [
        Arc("source", "start"),
        Arc("start", "phase"),
        Arc("phase", "end"),
        Arc("end", "sink"),
    ]
    for i, activity in enumerate(alphabet):
        tid = f"activity_{i}"
        transitions.append(Transition(tid, activity))
        arcs.extend((Arc("phase", tid), Arc(tid, "phase")))
    for j, region in enumerate(regions):
        pid = f"region_{j}"
        places.append(Place(pid))
        if region.initial:
            arcs.append(Arc("start", pid, region.initial))
        if region.final:
            arcs.append(Arc(pid, "end", region.final))
        for i, (consume, produce) in enumerate(zip(region.consume, region.produce)):
            if consume:
                arcs.append(Arc(pid, f"activity_{i}", consume))
            if produce:
                arcs.append(Arc(f"activity_{i}", pid, produce))
    return PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking((("source", 1),)),
        Marking((("sink", 1),)),
    )


@dataclass(frozen=True, slots=True)
class RegionDiscovery:
    model: PetriNet
    alphabet: tuple[str, ...]
    regions: tuple[IntegerRegion, ...]
    separation_targets: tuple[SeparationTarget, ...]
    enumerated_assignments: int
    feasible_regions: int
    optimizer_states: int
    objective_arc_weight: int
    objective_place_count: int
    optimal_within_bounds: bool
    all_targets_separated: bool

    def __post_init__(self):
        if not isinstance(self.model, PetriNet):
            raise TypeError("model must be PetriNet")
        if type(self.alphabet) is not tuple or any(
            type(a) is not str or not a.strip() for a in self.alphabet
        ):
            raise ValueError("alphabet must be a tuple of nonblank activities")
        if self.alphabet != tuple(sorted(set(self.alphabet))):
            raise ValueError("alphabet must be sorted and unique")
        if type(self.regions) is not tuple or any(
            not isinstance(r, IntegerRegion) for r in self.regions
        ):
            raise TypeError("regions must be a tuple of IntegerRegion")
        if type(self.separation_targets) is not tuple or any(
            not isinstance(t, SeparationTarget) for t in self.separation_targets
        ):
            raise TypeError("separation_targets must be a tuple of SeparationTarget")
        for name in (
            "enumerated_assignments",
            "feasible_regions",
            "optimizer_states",
            "objective_arc_weight",
            "objective_place_count",
        ):
            _nonnegative(getattr(self, name), name)
        if (
            type(self.optimal_within_bounds) is not bool
            or type(self.all_targets_separated) is not bool
        ):
            raise TypeError("completion indicators must be bool")
        if any(len(r.consume) != len(self.alphabet) for r in self.regions):
            raise ValueError("region dimension differs from alphabet")
        if self.objective_arc_weight != sum(r.arc_weight_cost for r in self.regions):
            raise ValueError("objective_arc_weight disagrees with selected regions")
        if self.objective_place_count != len(self.regions):
            raise ValueError("objective_place_count disagrees with selected regions")
        selected = {i for r in self.regions for i in r.blocked_target_ids}
        if any(i >= len(self.separation_targets) for i in selected):
            raise ValueError("region references an unknown separation target")
        if selected != {
            i for i, t in enumerate(self.separation_targets) if t.separated
        }:
            raise ValueError("separation flags disagree with selected regions")
        if self.all_targets_separated != all(
            t.separated for t in self.separation_targets
        ):
            raise ValueError("all_targets_separated disagrees with target witnesses")
        index = {a: i for i, a in enumerate(self.alphabet)}
        counts = []
        for target in self.separation_targets:
            if any(a not in index for a in target.prefix) or (
                target.next_activity is not None and target.next_activity not in index
            ):
                raise ValueError("separation target references an unknown activity")
            vector = [0] * len(index)
            for activity in target.prefix:
                vector[index[activity]] += 1
            counts.append(tuple(vector))
        for region in self.regions:
            blocked = []
            for j, (target, vector) in enumerate(zip(self.separation_targets, counts)):
                marking = region.initial + sum(
                    n * (p - c)
                    for n, p, c in zip(vector, region.produce, region.consume)
                )
                separated = (
                    marking != region.final
                    if target.next_activity is None
                    else marking < region.consume[index[target.next_activity]]
                )
                if separated:
                    blocked.append(j)
            if tuple(blocked) != region.blocked_target_ids:
                raise ValueError(
                    "region separation claims disagree with its marking equation"
                )
        if self.model != _region_petri_net(self.alphabet, self.regions):
            raise ValueError(
                "model does not correspond to the selected integer regions"
            )


__all__ = ("IntegerRegion", "SeparationTarget", "RegionDiscovery")
