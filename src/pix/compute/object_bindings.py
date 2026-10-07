"""Finite, deterministic enabled bindings for PIX's unit-incidence OCPN.

Object identities come exclusively from the model's declared universe. Token
multiplicity affects firing but does not make duplicate concrete bindings. The
result counts every enabled binding before lazily selecting a bounded prefix;
it is not a bounded search that can mistake truncation for a dead marking.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from itertools import combinations
from math import comb, prod

from pix.contracts.models import Binding, ObjectCentricPetriNet, ObjectMarking


@dataclass(frozen=True, slots=True)
class BindingEnumeration:
    """Enabled prefix and exact cardinality of the complete binding set.

    ``complete`` means every enabled binding at this marking is present, even
    when the result is empty. ``candidate_count`` includes bindings omitted by
    the cap, and is an arbitrary-precision integer, not an estimate.
    """

    bindings: tuple[Binding, ...]
    complete: bool
    candidate_count: int


@dataclass(frozen=True, slots=True)
class _TypeChoices:
    object_type: str
    object_ids: tuple[str, ...]
    minimum: int
    maximum: int

    def count(self) -> int:
        size = len(self.object_ids)
        if self.minimum > self.maximum:
            return 0
        if self.minimum == 0 and self.maximum == size:
            return 1 << size
        return sum(comb(size, count) for count in range(self.minimum, self.maximum + 1))

    def subsets(self) -> Iterator[tuple[str, ...]]:
        for size in range(self.minimum, self.maximum + 1):
            yield from combinations(self.object_ids, size)


def transition_binding_types(
    net: ObjectCentricPetriNet, transition_id: str
) -> tuple[str, ...]:
    """Sorted required binding type keys, including zero-cardinality types."""
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    if not isinstance(transition_id, str):
        raise TypeError("transition_id must be a string")
    if not any(transition.id == transition_id for transition in net.transitions):
        raise ValueError(f"unknown transition: {transition_id}")
    place_types = {place.id: place.object_type for place in net.places}
    return tuple(
        sorted(
            {
                place_types[arc.source if arc.target == transition_id else arc.target]
                for arc in net.arcs
                if transition_id in (arc.source, arc.target)
            }
        )
    )


def _transition_bindings(
    transition_id: str, choices: tuple[_TypeChoices, ...]
) -> Iterator[Binding]:
    if not choices:
        yield Binding(transition_id, ())
        return

    # itertools.product eagerly caches its input pools. An explicit stack keeps
    # the type product lazy and also avoids recursion limits for many types.
    iterators = [choices[0].subsets()]
    selected: list[tuple[str, tuple[str, ...]]] = []
    while iterators:
        try:
            subset = next(iterators[-1])
        except StopIteration:
            iterators.pop()
            if selected:
                selected.pop()
            continue
        depth = len(iterators) - 1
        entry = choices[depth].object_type, subset
        if len(iterators) == len(choices):
            yield Binding(transition_id, tuple(selected) + (entry,))
        else:
            selected.append(entry)
            iterators.append(choices[len(iterators)].subsets())


def enumerate_enabled_bindings(
    net: ObjectCentricPetriNet,
    marking: ObjectMarking,
    *,
    max_bindings: int,
) -> BindingEnumeration:
    """Enumerate at most ``max_bindings`` across all transitions at a marking.

    Ordering is transition ID, then type ID, then subset cardinality and sorted
    object IDs within each type. Each selected object must have a token at
    *every* input place of its type. Types with output incidence only select
    from all declared objects of that type. An explicit minimum of zero permits
    an empty set but never permits omitting that type from the binding.

    A nonnegative cap of zero performs counting without materializing bindings.
    Reaching a cap exactly is complete; exceeding it is explicitly incomplete.
    The count does not certify termination of repeated firing: source and loop
    transitions can still make the reachable marking space infinite.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    net.validate_marking(marking)
    if not isinstance(max_bindings, int) or isinstance(max_bindings, bool):
        raise TypeError("max_bindings must be an integer")
    if max_bindings < 0:
        raise ValueError("max_bindings must be nonnegative")

    place_types = {place.id: place.object_type for place in net.places}
    universe: dict[str, set[str]] = {}
    for object_id, object_type in net.objects:
        universe.setdefault(object_type, set()).add(object_id)
    available: dict[str, set[str]] = {}
    for token in marking.tokens:
        available.setdefault(token.place_id, set()).add(token.object_id)

    # Contracts require a single interval for all incidences of each
    # transition/type and prohibit repeated arcs. Under this unit-arc profile,
    # the intersection below is sufficient for joint token availability.
    policies: dict[str, dict[str, tuple[int, int | None]]] = {
        transition.id: {} for transition in net.transitions
    }
    presets: dict[tuple[str, str], list[str]] = {}
    for arc in net.arcs:
        incoming = arc.source in place_types
        transition_id = arc.target if incoming else arc.source
        place_id = arc.source if incoming else arc.target
        object_type = place_types[place_id]
        policies[transition_id][object_type] = arc.min_objects, arc.max_objects
        if incoming:
            presets.setdefault((transition_id, object_type), []).append(place_id)

    plans: list[tuple[str, tuple[_TypeChoices, ...], int]] = []
    candidate_count = 0
    for transition_id in sorted(policies):
        choices = []
        for object_type, (minimum, maximum) in sorted(policies[transition_id].items()):
            objects = universe.get(object_type, set()).copy()
            for place_id in presets.get((transition_id, object_type), ()):
                objects.intersection_update(available.get(place_id, ()))
            upper = len(objects) if maximum is None else min(maximum, len(objects))
            choices.append(
                _TypeChoices(object_type, tuple(sorted(objects)), minimum, upper)
            )
        count = prod(choice.count() for choice in choices)
        plans.append((transition_id, tuple(choices), count))
        candidate_count += count

    bindings: list[Binding] = []
    for transition_id, type_choices, count in plans:
        remaining = max_bindings - len(bindings)
        if remaining == 0:
            break
        if count:
            for binding in _transition_bindings(transition_id, type_choices):
                bindings.append(binding)
                remaining -= 1
                if remaining == 0:
                    break
    return BindingEnumeration(
        tuple(bindings), candidate_count <= max_bindings, candidate_count
    )


__all__ = [
    "BindingEnumeration",
    "enumerate_enabled_bindings",
    "transition_binding_types",
]
