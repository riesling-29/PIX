"""Native object-centric model operations and explicit causal-net semantics.

The causal-net profile is a finite concrete-object obligation net. Alternative
marker groups are OR choices; markers in one group are an AND. A marker has an
independent cardinality interval. Equality/disjointness constraints specify
whether the same object can satisfy several channels. Common input/output
object types conserve the union of participating identities. A type occurring
only on one side can introduce/remove obligations, but never object identities.

This is an explicit PIX profile, not a claim that every PM4Py causal-net marker
or OCPA transformation has identical semantics. Conversion refuses unsupported
structure instead of silently discarding it. Reduction preserves visible
binding behavior under stated sufficient conditions; silent divergence and
node identities need not be preserved. Reachability findings are confined to
the model's declared object universe and reported exploration limits.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from itertools import combinations, product
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.contracts.analysis import _text
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _tuple_of(value: object, kind: type, name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(x, kind) for x in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _names(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    _tuple_of(values, str, name)
    for value in values:
        _text(value, name)
    return tuple(sorted(set(values)))


@dataclass(frozen=True, slots=True, order=True)
class CausalChannel:
    """A typed obligation channel, with optional external source/sink boundary."""

    id: str
    object_type: str
    source_transition: str | None
    target_transition: str | None

    def __post_init__(self) -> None:
        _text(self.id, "channel ID")
        _text(self.object_type, "channel object type")
        for value in (self.source_transition, self.target_transition):
            if value is not None:
                _text(value, "channel endpoint")


@dataclass(frozen=True, slots=True, order=True)
class CausalMarker:
    channel_id: str
    min_objects: int = 1
    max_objects: int | None = 1

    def __post_init__(self) -> None:
        _text(self.channel_id, "marker channel")
        _integer(self.min_objects, "minimum objects")
        if self.max_objects is not None:
            _integer(self.max_objects, "maximum objects")
            if self.max_objects < self.min_objects:
                raise ValueError("maximum objects is smaller than minimum")


@dataclass(frozen=True, slots=True)
class CausalMarkerGroup:
    """One AND alternative, including explicit object identity constraints.

    Equality is transitive. Disjointness does not imply inequality when both
    sets are empty. Channels not constrained together may overlap. Constraint
    endpoints must have the same object type, checked by the containing model.
    """

    id: str
    transition_id: str
    markers: tuple[CausalMarker, ...]
    equal_channels: tuple[tuple[str, str], ...] = ()
    disjoint_channels: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "marker group ID")
        _text(self.transition_id, "marker group transition")
        _tuple_of(self.markers, CausalMarker, "markers")
        ids = {marker.channel_id for marker in self.markers}
        if len(ids) != len(self.markers):
            raise ValueError("a group cannot repeat a channel")
        object.__setattr__(
            self,
            "markers",
            tuple(
                sorted(
                    self.markers,
                    key=lambda marker: marker.channel_id,
                )
            ),
        )
        for name in ("equal_channels", "disjoint_channels"):
            pairs = getattr(self, name)
            _tuple_of(pairs, tuple, name)
            normalized = []
            for pair in pairs:
                if len(pair) != 2 or any(x not in ids for x in pair):
                    raise ValueError("constraint endpoints must be group channels")
                if pair[0] == pair[1]:
                    raise ValueError("a constraint must relate distinct channels")
                normalized.append(tuple(sorted(pair)))
            object.__setattr__(self, name, tuple(sorted(set(normalized))))


@dataclass(frozen=True, slots=True)
class ObjectCentricCausalNet:
    transitions: tuple[Transition, ...]
    channels: tuple[CausalChannel, ...]
    input_bindings: tuple[CausalMarkerGroup, ...]
    output_bindings: tuple[CausalMarkerGroup, ...]
    initial_marking: ObjectMarking
    final_marking: ObjectMarking
    objects: tuple[tuple[str, str], ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    PROFILE: ClassVar[str] = "pix.finite_object_obligation_net.v1"

    def __post_init__(self) -> None:
        _tuple_of(self.transitions, Transition, "transitions")
        _tuple_of(self.channels, CausalChannel, "channels")
        _tuple_of(self.objects, tuple, "objects")
        transitions = {transition.id for transition in self.transitions}
        channels = {channel.id: channel for channel in self.channels}
        if len(transitions) != len(self.transitions) or len(channels) != len(
            self.channels
        ):
            raise ValueError("duplicate transition or channel ID")
        if transitions & channels.keys():
            raise ValueError("transition and channel IDs must be disjoint")
        objects = {}
        for row in self.objects:
            if len(row) != 2:
                raise ValueError("objects entries must be (object ID, object type)")
            _text(row[0], "object ID")
            _text(row[1], "object type")
            if row[0] in objects:
                raise ValueError("duplicate object ID")
            objects[row[0]] = row[1]
        for channel in self.channels:
            for endpoint in (channel.source_transition, channel.target_transition):
                if endpoint is not None and endpoint not in transitions:
                    raise ValueError("channel references an unknown transition")
        group_ids: set[str] = set()
        for direction, groups in (
            ("input", self.input_bindings),
            ("output", self.output_bindings),
        ):
            _tuple_of(groups, CausalMarkerGroup, direction + " bindings")
            covered = set()
            mentioned = set()
            for group in groups:
                if group.id in group_ids:
                    raise ValueError("marker group IDs must be globally unique")
                group_ids.add(group.id)
                if group.transition_id not in transitions:
                    raise ValueError("marker group references an unknown transition")
                covered.add(group.transition_id)
                for marker in group.markers:
                    if marker.channel_id not in channels:
                        raise ValueError("marker references an unknown channel")
                    channel = channels[marker.channel_id]
                    endpoint = (
                        channel.target_transition
                        if direction == "input"
                        else channel.source_transition
                    )
                    if endpoint != group.transition_id:
                        raise ValueError(
                            "marker direction disagrees with channel endpoint"
                        )
                    mentioned.add(marker.channel_id)
                for left, right in group.equal_channels + group.disjoint_channels:
                    if channels[left].object_type != channels[right].object_type:
                        raise ValueError(
                            "identity constraints require the same object type"
                        )
            if covered != transitions:
                raise ValueError(
                    "each transition needs an explicit input and output alternative, possibly empty"
                )
            required = {
                channel.id
                for channel in self.channels
                if (
                    channel.target_transition
                    if direction == "input"
                    else channel.source_transition
                )
                is not None
            }
            if mentioned != required:
                raise ValueError(
                    "every connected channel must occur in an endpoint's marker groups"
                )
        self.validate_marking(self.initial_marking)
        self.validate_marking(self.final_marking)
        object.__setattr__(
            self, "transitions", tuple(sorted(self.transitions, key=lambda t: t.id))
        )
        object.__setattr__(
            self, "channels", tuple(sorted(self.channels, key=lambda c: c.id))
        )
        object.__setattr__(
            self,
            "input_bindings",
            tuple(sorted(self.input_bindings, key=lambda g: g.id)),
        )
        object.__setattr__(
            self,
            "output_bindings",
            tuple(sorted(self.output_bindings, key=lambda g: g.id)),
        )
        object.__setattr__(self, "objects", tuple(sorted(self.objects)))

    def validate_marking(self, marking: ObjectMarking) -> None:
        if not isinstance(marking, ObjectMarking):
            raise TypeError("causal marking must be ObjectMarking")
        channels = {channel.id: channel.object_type for channel in self.channels}
        objects = dict(self.objects)
        for token in marking.tokens:
            if token.place_id not in channels or token.object_id not in objects:
                raise ValueError("marking references an unknown channel or object")
            if channels[token.place_id] != objects[token.object_id]:
                raise ValueError("object type disagrees with the obligation channel")


@dataclass(frozen=True, slots=True)
class CausalFiring:
    transition_id: str
    input_binding_id: str
    output_binding_id: str
    consumed: tuple[tuple[str, tuple[str, ...]], ...]
    produced: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        for name in ("transition_id", "input_binding_id", "output_binding_id"):
            _text(getattr(self, name), name)
        for name in ("consumed", "produced"):
            rows = getattr(self, name)
            _tuple_of(rows, tuple, name)
            seen = set()
            normalized = []
            for row in rows:
                if len(row) != 2:
                    raise ValueError(
                        "selection entries must be (channel ID, object IDs)"
                    )
                channel_id, ids = row
                _text(channel_id, "channel ID")
                if channel_id in seen:
                    raise ValueError("duplicate selected channel")
                seen.add(channel_id)
                normalized_ids = _names(ids, "selected objects")
                if len(normalized_ids) != len(ids):
                    raise ValueError("a channel selection cannot repeat an object")
                normalized.append((channel_id, normalized_ids))
            object.__setattr__(self, name, tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class CausalBindingEnumeration:
    bindings: tuple[CausalFiring, ...]
    complete: bool
    candidate_count: int | None
    examined_candidates: int


def causal_net_digest(net: ObjectCentricCausalNet) -> str:
    if not isinstance(net, ObjectCentricCausalNet):
        raise TypeError("net must be ObjectCentricCausalNet")
    body = {"profile": net.PROFILE, "model": asdict(net)}
    encoded = json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "pix.causal-model.v1:sha256:" + sha256(encoded).hexdigest()


def _group_matches(
    group: CausalMarkerGroup, selection: dict[str, tuple[str, ...]]
) -> bool:
    if set(selection) != {marker.channel_id for marker in group.markers}:
        return False
    for marker in group.markers:
        size = len(selection[marker.channel_id])
        if size < marker.min_objects or (
            marker.max_objects is not None and size > marker.max_objects
        ):
            return False
    if any(selection[left] != selection[right] for left, right in group.equal_channels):
        return False
    if any(
        set(selection[left]) & set(selection[right])
        for left, right in group.disjoint_channels
    ):
        return False
    return True


def _causal_delta(
    net: ObjectCentricCausalNet, firing: CausalFiring
) -> tuple[Counter, Counter] | None:
    if not isinstance(net, ObjectCentricCausalNet):
        raise TypeError("net must be ObjectCentricCausalNet")
    if not isinstance(firing, CausalFiring):
        raise TypeError("firing must be CausalFiring")
    inputs = {group.id: group for group in net.input_bindings}
    outputs = {group.id: group for group in net.output_bindings}
    if firing.input_binding_id not in inputs or firing.output_binding_id not in outputs:
        raise ValueError("unknown input or output marker group")
    ingroup, outgroup = (
        inputs[firing.input_binding_id],
        outputs[firing.output_binding_id],
    )
    if (
        ingroup.transition_id != firing.transition_id
        or outgroup.transition_id != firing.transition_id
    ):
        raise ValueError("firing transition disagrees with its marker groups")
    consumed, produced = dict(firing.consumed), dict(firing.produced)
    if not _group_matches(ingroup, consumed) or not _group_matches(outgroup, produced):
        return None
    channels = {channel.id: channel.object_type for channel in net.channels}
    objects = dict(net.objects)
    sides: list[dict[str, set[str]]] = []
    for selection in (consumed, produced):
        types: dict[str, set[str]] = {}
        for channel_id, ids in selection.items():
            object_type = channels[channel_id]
            if any(objects.get(object_id) != object_type for object_id in ids):
                raise ValueError("firing contains an undeclared or mistyped object")
            types.setdefault(object_type, set()).update(ids)
        sides.append(types)
    for object_type in sides[0].keys() & sides[1].keys():
        if sides[0][object_type] != sides[1][object_type]:
            return None
    return (
        Counter(
            ObjectToken(channel, obj) for channel, ids in firing.consumed for obj in ids
        ),
        Counter(
            ObjectToken(channel, obj) for channel, ids in firing.produced for obj in ids
        ),
    )


def is_causal_binding_enabled(
    net: ObjectCentricCausalNet, marking: ObjectMarking, firing: CausalFiring
) -> bool:
    net.validate_marking(marking)
    delta = _causal_delta(net, firing)
    return delta is not None and not (delta[0] - Counter(marking.tokens))


def fire_causal_binding(
    net: ObjectCentricCausalNet, marking: ObjectMarking, firing: CausalFiring
) -> ObjectMarking:
    net.validate_marking(marking)
    delta = _causal_delta(net, firing)
    counts = Counter(marking.tokens)
    if delta is None or delta[0] - counts:
        raise ValueError("causal binding is not enabled")
    counts.subtract(delta[0])
    counts.update(delta[1])
    return ObjectMarking(tuple(counts.elements()))


def causal_firing_objects(
    net: ObjectCentricCausalNet, firing: CausalFiring
) -> tuple[tuple[str, str], ...]:
    """Unique concrete participants, sorted by object ID, including both sides."""
    if _causal_delta(net, firing) is None:
        raise ValueError("invalid causal binding")
    object_types = dict(net.objects)
    ids = {obj for _, objects in firing.consumed + firing.produced for obj in objects}
    return tuple(sorted((obj, object_types[obj]) for obj in ids))


def _selection_options(group: CausalMarkerGroup, available: dict[str, tuple[str, ...]]):
    """Lazy product: never materialize the powerset of a channel's objects."""
    if not group.markers:
        yield ()
        return
    # An empty later domain must be detected before enumerating an earlier
    # powerset. Otherwise no complete candidate is yielded and the caller's
    # candidate budget cannot stop an exponential number of partial choices.
    if any(
        marker.min_objects > len(available.get(marker.channel_id, ()))
        for marker in group.markers
    ):
        return

    def subsets(marker):
        objects = available.get(marker.channel_id, ())
        upper = (
            len(objects)
            if marker.max_objects is None
            else min(len(objects), marker.max_objects)
        )
        for count in range(marker.min_objects, upper + 1):
            for ids in combinations(objects, count):
                yield marker.channel_id, ids

    stack = [subsets(group.markers[0])]
    selected = []
    while stack:
        try:
            value = next(stack[-1])
        except StopIteration:
            stack.pop()
            if selected:
                selected.pop()
            continue
        if len(stack) == len(group.markers):
            yield tuple(selected) + (value,)
        else:
            selected.append(value)
            stack.append(subsets(group.markers[len(stack)]))


def enumerate_enabled_causal_bindings(
    net: ObjectCentricCausalNet,
    marking: ObjectMarking,
    *,
    max_bindings: int,
    max_candidates: int = 100000,
) -> CausalBindingEnumeration:
    """Count enabled choices exactly unless raw assignment exploration is capped.

    Distinct marker-group choices are distinct firings, even if their token
    effects coincide. max_bindings only bounds stored choices. max_candidates
    bounds examined input/output assignments; when exceeded, candidate_count
    is None, not an unproved zero or the number of the returned prefix.
    """
    if not isinstance(net, ObjectCentricCausalNet):
        raise TypeError("net must be ObjectCentricCausalNet")
    net.validate_marking(marking)
    _integer(max_bindings, "max_bindings")
    _integer(max_candidates, "max_candidates", 1)
    channels = {channel.id: channel.object_type for channel in net.channels}
    universe: dict[str, list[str]] = defaultdict(list)
    for obj, kind in net.objects:
        universe[kind].append(obj)
    input_available: dict[str, tuple[str, ...]] = {}
    for channel in net.channels:
        input_available[channel.id] = tuple(
            sorted(
                {
                    token.object_id
                    for token in marking.tokens
                    if token.place_id == channel.id
                }
            )
        )
    all_available = {
        channel.id: tuple(universe[channel.object_type]) for channel in net.channels
    }
    inputs: dict[str, list[CausalMarkerGroup]] = defaultdict(list)
    outputs: dict[str, list[CausalMarkerGroup]] = defaultdict(list)
    for group in net.input_bindings:
        inputs[group.transition_id].append(group)
    for group in net.output_bindings:
        outputs[group.transition_id].append(group)
    found = []
    count = examined = 0
    for transition in net.transitions:
        for ingroup in inputs[transition.id]:
            for consumed in _selection_options(ingroup, input_available):
                # Input assignments count toward the work budget too, so an
                # impossible output cannot make this loop silently unbounded.
                if examined >= max_candidates:
                    return CausalBindingEnumeration(tuple(found), False, None, examined)
                examined += 1
                if not _group_matches(ingroup, dict(consumed)):
                    continue
                consumed_types: dict[str, set[str]] = defaultdict(set)
                for channel_id, ids in consumed:
                    consumed_types[channels[channel_id]].update(ids)
                for outgroup in outputs[transition.id]:
                    output_available = dict(all_available)
                    for marker in outgroup.markers:
                        kind = channels[marker.channel_id]
                        if kind in consumed_types:
                            output_available[marker.channel_id] = tuple(
                                sorted(consumed_types[kind])
                            )
                    for produced in _selection_options(outgroup, output_available):
                        if examined >= max_candidates:
                            return CausalBindingEnumeration(
                                tuple(found), False, None, examined
                            )
                        examined += 1
                        firing = CausalFiring(
                            transition.id, ingroup.id, outgroup.id, consumed, produced
                        )
                        if is_causal_binding_enabled(net, marking, firing):
                            count += 1
                            if len(found) < max_bindings:
                                found.append(firing)
    return CausalBindingEnumeration(
        tuple(found), count <= max_bindings, count, examined
    )


@dataclass(frozen=True, slots=True)
class ObjectProjectionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_projection.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_types: tuple[str, ...] | None = None
    transition_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for name in ("object_types", "transition_ids"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _names(value, name))


@dataclass(frozen=True, slots=True)
class ObjectHidingSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_hiding.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    transition_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "transition_ids", _names(self.transition_ids, "transition IDs")
        )


@dataclass(frozen=True, slots=True)
class ObjectModelTransformation:
    model: ObjectCentricPetriNet
    removed_place_ids: tuple[str, ...]
    removed_transition_ids: tuple[str, ...]
    removed_arc_endpoints: tuple[tuple[str, str], ...]
    hidden_transition_ids: tuple[str, ...]
    place_mapping: tuple[tuple[str, str], ...]
    behavioral_guarantee: str
    boundary_note: str


def _transform_payload(
    source, target, *, hidden=(), mapping=(), guarantee, boundary=""
):
    places = {p.id for p in target.places}
    transitions = {t.id for t in target.transitions}
    arcs = {(a.source, a.target) for a in target.arcs}
    return ObjectModelTransformation(
        target,
        tuple(p.id for p in source.places if p.id not in places),
        tuple(t.id for t in source.transitions if t.id not in transitions),
        tuple(
            (a.source, a.target)
            for a in source.arcs
            if (a.source, a.target) not in arcs
        ),
        tuple(hidden),
        tuple(mapping),
        guarantee,
        boundary,
    )


def project_ocpn(
    net: ObjectCentricPetriNet, spec: ObjectProjectionSpec = ObjectProjectionSpec()
) -> ComputationResult[ObjectModelTransformation]:
    """Select object types and/or the incident-place subnet of transitions.

    Cuts remove synchronization conditions. The returned marking is the exact
    restriction of the original marking, not inferred subprocess start/end
    conditions. This projection does not claim preservation of accepted runs.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectProjectionSpec
    ):
        raise TypeError("expected OCPN and ObjectProjectionSpec")
    types = {p.object_type for p in net.places} | {kind for _, kind in net.objects}
    requested_types = types if spec.object_types is None else set(spec.object_types)
    tids = {t.id for t in net.transitions}
    requested_transitions = (
        tids if spec.transition_ids is None else set(spec.transition_ids)
    )
    if requested_types - types or requested_transitions - tids:
        raise ValueError("projection references an unknown object type or transition")
    places = {p.id for p in net.places if p.object_type in requested_types}
    if spec.transition_ids is not None:
        incident = {
            a.source if a.target in tids else a.target
            for a in net.arcs
            if a.source in requested_transitions or a.target in requested_transitions
        }
        places.intersection_update(incident)
    selected_transitions = requested_transitions
    if spec.object_types is not None:
        selected_transitions = {
            t
            for t in requested_transitions
            if any(
                (a.source == t and a.target in places)
                or (a.target == t and a.source in places)
                for a in net.arcs
            )
        }
    nodes = places | selected_transitions
    target = ObjectCentricPetriNet(
        tuple(p for p in net.places if p.id in places),
        tuple(t for t in net.transitions if t.id in selected_transitions),
        tuple(a for a in net.arcs if a.source in nodes and a.target in nodes),
        ObjectMarking(
            tuple(t for t in net.initial_marking.tokens if t.place_id in places)
        ),
        ObjectMarking(
            tuple(t for t in net.final_marking.tokens if t.place_id in places)
        ),
        tuple(row for row in net.objects if row[1] in requested_types),
    )
    unchanged = target == net
    value = _transform_payload(
        net,
        target,
        guarantee="identical_model" if unchanged else "structural_projection_only",
        boundary="Markings are restricted; cut arcs can enable additional bindings and erase joint obligations.",
    )
    return _derived_result(
        "pix.object_centric.project_ocpn",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        value,
    )


def hide_ocpn(
    net: ObjectCentricPetriNet, spec: ObjectHidingSpec = ObjectHidingSpec()
) -> ComputationResult[ObjectModelTransformation]:
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectHidingSpec
    ):
        raise TypeError("expected OCPN and ObjectHidingSpec")
    unknown = set(spec.transition_ids) - {t.id for t in net.transitions}
    if unknown:
        raise ValueError("hiding references an unknown transition")
    target = replace(
        net,
        transitions=tuple(
            Transition(t.id, None) if t.id in spec.transition_ids else t
            for t in net.transitions
        ),
    )
    payload = _transform_payload(
        net,
        target,
        hidden=spec.transition_ids,
        guarantee="same_markings_and_binding_relation_visible_label_projection",
    )
    return _derived_result(
        "pix.object_centric.hide_ocpn",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        payload,
    )


@dataclass(frozen=True, slots=True)
class ObjectSubnetSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_subnet.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    node_ids: tuple[str, ...] = ()
    direction: str = "ancestors"
    include_seeds: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "node_ids", _names(self.node_ids, "node IDs"))
        if self.direction not in ("ancestors", "descendants"):
            raise ValueError("direction must be ancestors or descendants")
        if not isinstance(self.include_seeds, bool):
            raise TypeError("include_seeds must be bool")


@dataclass(frozen=True, slots=True)
class ObjectSubnet:
    node_ids: tuple[str, ...]
    place_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    arcs: tuple[ObjectArc, ...]
    meaning: str = "structural_reachability_not_executable_or_sound_subprocess"


def object_subnet(
    net: ObjectCentricPetriNet, spec: ObjectSubnetSpec = ObjectSubnetSpec()
) -> ComputationResult[ObjectSubnet]:
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectSubnetSpec
    ):
        raise TypeError("expected OCPN and ObjectSubnetSpec")
    nodes = {p.id for p in net.places} | {t.id for t in net.transitions}
    if set(spec.node_ids) - nodes:
        raise ValueError("subnet references unknown nodes")
    graph: dict[str, set[str]] = defaultdict(set)
    for arc in net.arcs:
        start, end = (
            (arc.target, arc.source)
            if spec.direction == "ancestors"
            else (arc.source, arc.target)
        )
        graph[start].add(end)
    reached = set(spec.node_ids)
    pending = list(spec.node_ids)
    while pending:
        current = pending.pop()
        for following in graph[current] - reached:
            reached.add(following)
            pending.append(following)
    if not spec.include_seeds:
        reached.difference_update(spec.node_ids)
    value = ObjectSubnet(
        tuple(sorted(reached)),
        tuple(p.id for p in net.places if p.id in reached),
        tuple(t.id for t in net.transitions if t.id in reached),
        tuple(a for a in net.arcs if a.source in reached and a.target in reached),
    )
    return _derived_result(
        "pix.object_centric.object_subnet",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        value,
    )


@dataclass(frozen=True, slots=True)
class ObjectReductionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_reduction.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rules: tuple[str, ...] = (
        "parallel_places",
        "parallel_transitions",
        "silent_self_loop",
        "series_places",
    )
    sacred_node_ids: tuple[str, ...] = ()
    max_steps: int = 1000

    def __post_init__(self) -> None:
        rules = _names(self.rules, "reduction rules")
        if set(rules) - {
            "parallel_places",
            "parallel_transitions",
            "silent_self_loop",
            "series_places",
        }:
            raise ValueError("unsupported reduction rule")
        object.__setattr__(self, "rules", rules)
        object.__setattr__(
            self, "sacred_node_ids", _names(self.sacred_node_ids, "sacred nodes")
        )
        _integer(self.max_steps, "max_steps", 1)


@dataclass(frozen=True, slots=True)
class ObjectReductionStep:
    rule: str
    removed_place_ids: tuple[str, ...]
    removed_transition_ids: tuple[str, ...]
    place_mapping: tuple[tuple[str, str], ...]
    sufficient_condition: str


@dataclass(frozen=True, slots=True)
class ObjectReduction:
    model: ObjectCentricPetriNet
    steps: tuple[ObjectReductionStep, ...]
    original_to_reduced_places: tuple[tuple[str, str], ...]
    fixed_point_reached: bool
    guarantee: str = (
        "visible_activity_and_object_participation_language_under_reported_conditions"
    )
    not_preserved: tuple[str, ...] = (
        "node_identity",
        "silent_step_count",
        "silent_divergence",
    )


def _incidence_signature(net, node, *, place):
    return tuple(
        sorted(
            (
                "out" if a.source == node else "in",
                a.target if a.source == node else a.source,
                a.variable,
                a.min_objects,
                -1 if a.max_objects is None else a.max_objects,
            )
            for a in net.arcs
            if node in (a.source, a.target)
        )
    )


def _remove_transition(net, transition_id):
    return replace(
        net,
        transitions=tuple(t for t in net.transitions if t.id != transition_id),
        arcs=tuple(a for a in net.arcs if transition_id not in (a.source, a.target)),
    )


def _marking_move(marking, old, new, *, discard=False):
    return ObjectMarking(
        tuple(
            ObjectToken(new, token.object_id) if token.place_id == old else token
            for token in marking.tokens
            if not (discard and token.place_id == old)
        )
    )


def _reduce_one(net, spec):
    sacred = set(spec.sacred_node_ids)
    if "parallel_places" in spec.rules:
        for left, right in combinations(net.places, 2):
            if left.object_type != right.object_type:
                continue
            if _incidence_signature(net, left.id, place=True) != _incidence_signature(
                net, right.id, place=True
            ):
                continue
            if any(
                Counter(
                    token.object_id
                    for token in marking.tokens
                    if token.place_id == left.id
                )
                != Counter(
                    token.object_id
                    for token in marking.tokens
                    if token.place_id == right.id
                )
                for marking in (net.initial_marking, net.final_marking)
            ):
                continue
            remove, keep = (
                (right.id, left.id) if right.id not in sacred else (left.id, right.id)
            )
            if remove in sacred:
                continue
            target = replace(
                net,
                places=tuple(p for p in net.places if p.id != remove),
                arcs=tuple(a for a in net.arcs if remove not in (a.source, a.target)),
                initial_marking=_marking_move(
                    net.initial_marking, remove, keep, discard=True
                ),
                final_marking=_marking_move(
                    net.final_marking, remove, keep, discard=True
                ),
            )
            return target, ObjectReductionStep(
                "parallel_places",
                (remove,),
                (),
                ((remove, keep),),
                "same type, same cardinality/incidence, equal per-object initial and final multisets; retain one redundant copy",
            )
    if "parallel_transitions" in spec.rules:
        for left, right in combinations(net.transitions, 2):
            if left.activity != right.activity or _incidence_signature(
                net, left.id, place=False
            ) != _incidence_signature(net, right.id, place=False):
                continue
            remove = right.id if right.id not in sacred else left.id
            if remove not in sacred:
                return _remove_transition(net, remove), ObjectReductionStep(
                    "parallel_transitions",
                    (),
                    (remove,),
                    (),
                    "identical visible/silent activity and typed-cardinality incidence; transition identity quotient",
                )
    if "silent_self_loop" in spec.rules:
        for transition in net.transitions:
            if transition.activity is not None or transition.id in sacred:
                continue
            incoming = {
                (a.source, a.variable, a.min_objects, a.max_objects)
                for a in net.arcs
                if a.target == transition.id
            }
            outgoing = {
                (a.target, a.variable, a.min_objects, a.max_objects)
                for a in net.arcs
                if a.source == transition.id
            }
            if incoming == outgoing:
                return _remove_transition(net, transition.id), ObjectReductionStep(
                    "silent_self_loop",
                    (),
                    (transition.id,),
                    (),
                    "silent transition has identical input/output incidences; every firing leaves the marking unchanged",
                )
    if "series_places" in spec.rules:
        for transition in net.transitions:
            if transition.activity is not None or transition.id in sacred:
                continue
            incoming = [a for a in net.arcs if a.target == transition.id]
            outgoing = [a for a in net.arcs if a.source == transition.id]
            if len(incoming) != 1 or len(outgoing) != 1:
                continue
            before, after = incoming[0], outgoing[0]
            p, q = before.source, after.target
            if p == q or before.variable or after.variable or p in sacred:
                continue
            types = {place.id: place.object_type for place in net.places}
            if types[p] != types[q]:
                continue
            if (
                sum(a.source == p for a in net.arcs) != 1
                or sum(a.target == q for a in net.arcs) != 1
            ):
                continue
            if any(t.place_id == q for t in net.initial_marking.tokens) or any(
                t.place_id == p for t in net.final_marking.tokens
            ):
                continue
            arcs = []
            for arc in net.arcs:
                if transition.id in (arc.source, arc.target):
                    continue
                arcs.append(
                    replace(
                        arc,
                        source=q if arc.source == p else arc.source,
                        target=q if arc.target == p else arc.target,
                    )
                )
            try:
                target = replace(
                    net,
                    places=tuple(place for place in net.places if place.id != p),
                    transitions=tuple(
                        t for t in net.transitions if t.id != transition.id
                    ),
                    arcs=tuple(arcs),
                    initial_marking=_marking_move(net.initial_marking, p, q),
                    final_marking=_marking_move(net.final_marking, p, q),
                )
            except ValueError:
                continue
            return target, ObjectReductionStep(
                "series_places",
                (p,),
                (transition.id,),
                ((p, q),),
                "fixed unit silent p-to-q, same type, p has no other output, q no other input, q initially empty, p finally empty",
            )
    return None


def reduce_ocpn(
    net: ObjectCentricPetriNet, spec: ObjectReductionSpec = ObjectReductionSpec()
) -> ComputationResult[ObjectReduction]:
    """Four conservative Murata-style rules; no unchecked marking erasure."""
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectReductionSpec
    ):
        raise TypeError("expected OCPN and ObjectReductionSpec")
    if set(spec.sacred_node_ids) - (
        {p.id for p in net.places} | {t.id for t in net.transitions}
    ):
        raise ValueError("unknown sacred node")
    target = net
    mappings = {p.id: p.id for p in net.places}
    steps = []
    for _ in range(spec.max_steps):
        reduced = _reduce_one(target, spec)
        if reduced is None:
            break
        target, step = reduced
        steps.append(step)
        for old, new in step.place_mapping:
            mappings = {
                source: new if destination == old else destination
                for source, destination in mappings.items()
            }
    complete = _reduce_one(target, spec) is None
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "reduction_step_limit",
                "Additional safe reductions remain; current model is still a valid reduced model",
            ),
        )
    )
    value = ObjectReduction(
        target, tuple(steps), tuple(sorted(mappings.items())), complete
    )
    return _derived_result(
        "pix.object_centric.reduce_ocpn",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL,
        value,
        issues,
    )


@dataclass(frozen=True, slots=True)
class ObjectInvariantSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_invariant.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_types: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if self.object_types is not None:
            object.__setattr__(
                self, "object_types", _names(self.object_types, "object types")
            )


@dataclass(frozen=True, slots=True)
class TypedPlaceInvariants:
    object_type: str
    place_ids: tuple[str, ...]
    vectors: tuple[tuple[int, ...], ...]
    initial_values_by_object: tuple[tuple[str, tuple[int, ...]], ...]
    final_values_by_object: tuple[tuple[str, tuple[int, ...]], ...]
    conservation_compatible_with_final: bool


@dataclass(frozen=True, slots=True)
class ObjectInvariants:
    by_object_type: tuple[TypedPlaceInvariants, ...]
    meaning: str = (
        "rational_kernel_basis_per_object_identity_not_positive_invariants_or_soundness"
    )


def object_place_invariants(
    net: ObjectCentricPetriNet, spec: ObjectInvariantSpec = ObjectInvariantSpec()
) -> ComputationResult[ObjectInvariants]:
    """v^T C_type=0 holds separately for every concrete object of that type.

    The common object set on all incidences of transition/type makes these
    invariants valid even for variable cardinality. A basis may contain signed
    vectors; conservation compatibility is necessary, not sufficient, for
    reaching the final marking. Cross-type synchronization is not erased into
    a claimed global reachability result.
    """
    from pix.case_centric._model_algebra import invariants

    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectInvariantSpec
    ):
        raise TypeError("expected OCPN and ObjectInvariantSpec")
    types = {p.object_type for p in net.places} | {kind for _, kind in net.objects}
    selected = types if spec.object_types is None else set(spec.object_types)
    if selected - types:
        raise ValueError("unknown object type")
    rows = []
    for kind in sorted(selected):
        places = tuple(p.id for p in net.places if p.object_type == kind)
        arcs = tuple(
            Arc(a.source, a.target)
            for a in net.arcs
            if a.source in places or a.target in places
        )
        projection = PetriNet(
            tuple(Place(p) for p in places), net.transitions, arcs, Marking(), Marking()
        )
        basis = invariants(projection, "place")

        def values(marking):
            counts = Counter(marking.tokens)
            return tuple(
                (
                    obj,
                    tuple(
                        sum(
                            weight * counts[ObjectToken(place, obj)]
                            for place, weight in zip(places, vector)
                        )
                        for vector in basis.vectors
                    ),
                )
                for obj, object_type in net.objects
                if object_type == kind
            )

        initial, final = values(net.initial_marking), values(net.final_marking)
        rows.append(
            TypedPlaceInvariants(
                kind, places, basis.vectors, initial, final, initial == final
            )
        )
    return _derived_result(
        "pix.object_centric.object_place_invariants",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED,
        ObjectInvariants(tuple(rows)),
    )


@dataclass(frozen=True, slots=True)
class ObjectSoundnessSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_soundness.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    max_states: int = 10000
    max_bindings_per_marking: int = 10000

    def __post_init__(self) -> None:
        _integer(self.max_states, "max_states", 1)
        _integer(self.max_bindings_per_marking, "max_bindings_per_marking", 1)


@dataclass(frozen=True, slots=True)
class ObjectReachabilityEdge:
    source_state: int
    target_state: int
    transition_id: str
    objects: tuple[tuple[str, tuple[str, ...]], ...]


@dataclass(frozen=True, slots=True)
class ObjectSoundness:
    assessment: str
    scope: str
    exploration_complete: bool
    states: tuple[ObjectMarking, ...]
    edges: tuple[ObjectReachabilityEdge, ...]
    accepting_state: int | None
    option_to_complete: bool | None
    proper_completion: bool | None
    no_dead_transitions: bool | None
    noncompletable_state_ids: tuple[int, ...]
    observed_deadlock_state_ids: tuple[int, ...]
    improper_completion_state_ids: tuple[int, ...]
    dead_transition_ids: tuple[str, ...]
    global_all_object_universes_soundness: bool | None = None


def analyze_ocpn_soundness(
    net: ObjectCentricPetriNet, spec: ObjectSoundnessSpec = ObjectSoundnessSpec()
) -> ComputationResult[ObjectSoundness]:
    """Finite-universe option-to-complete, proper completion and transition use.

    Exhaustion is required to prove positive properties or dead transitions.
    A discovered nonfinal deadlock or extra-token final cover is already a
    counterexample even when exploration later stops. Empty final markings have
    no distinguished output-place cover test: proper_completion is None.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectSoundnessSpec
    ):
        raise TypeError("expected OCPN and ObjectSoundnessSpec")
    states = [net.initial_marking]
    indices = {net.initial_marking: 0}
    queue = deque([0])
    edges = []
    deadlocks = []
    improper = []
    fired = set()
    complete = True
    final_counts = Counter(net.final_marking.tokens)
    issues = set()
    while queue:
        index = queue.popleft()
        marking = states[index]
        if (
            final_counts
            and marking != net.final_marking
            and not (final_counts - Counter(marking.tokens))
        ):
            improper.append(index)
        enumeration = enumerate_enabled_bindings(
            net, marking, max_bindings=spec.max_bindings_per_marking
        )
        if not enumeration.complete:
            complete = False
            issues.add("binding_limit")
        if enumeration.candidate_count == 0 and marking != net.final_marking:
            deadlocks.append(index)
        for binding in enumeration.bindings:
            following = fire_binding(net, marking, binding)
            fired.add(binding.transition_id)
            if following not in indices:
                if len(states) >= spec.max_states:
                    complete = False
                    issues.add("state_limit")
                    continue
                indices[following] = len(states)
                states.append(following)
                queue.append(indices[following])
            edges.append(
                ObjectReachabilityEdge(
                    index, indices[following], binding.transition_id, binding.objects
                )
            )
    accepting = indices.get(net.final_marking)
    reverse: dict[int, set[int]] = defaultdict(set)
    for edge in edges:
        reverse[edge.target_state].add(edge.source_state)
    can_finish = set() if accepting is None else {accepting}
    pending = list(can_finish)
    while pending:
        for predecessor in reverse[pending.pop()] - can_finish:
            can_finish.add(predecessor)
            pending.append(predecessor)
    noncompletable = (
        tuple(index for index in range(len(states)) if index not in can_finish)
        if complete
        else ()
    )
    option = not noncompletable if complete else (False if deadlocks else None)
    proper = (
        (not improper if complete else (False if improper else None))
        if final_counts
        else None
    )
    dead_transitions = (
        tuple(t.id for t in net.transitions if t.id not in fired) if complete else ()
    )
    no_dead = not dead_transitions if complete else None
    values = (option, no_dead) + ((proper,) if final_counts else ())
    assessment = (
        "disproven"
        if False in values
        else "proven"
        if complete and all(value is True for value in values)
        else "unknown"
    )
    payload = ObjectSoundness(
        assessment,
        "declared_finite_object_universe",
        complete,
        tuple(states),
        tuple(edges),
        accepting,
        option,
        proper,
        no_dead,
        noncompletable,
        tuple(deadlocks),
        tuple(improper),
        dead_transitions,
    )
    warnings = tuple(
        ComputeIssue(
            "object_soundness_" + reason,
            "Exploration stopped at "
            + reason
            + "; unobserved behavior remains unknown",
        )
        for reason in sorted(issues)
    )
    return _derived_result(
        "pix.object_centric.analyze_ocpn_soundness",
        model_digest(net),
        spec,
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL,
        payload,
        warnings,
    )


@dataclass(frozen=True, slots=True)
class ObjectConversionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_conversion.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    max_transition_copies: int = 10000

    def __post_init__(self) -> None:
        _integer(self.max_transition_copies, "max_transition_copies", 1)


@dataclass(frozen=True, slots=True)
class ObjectModelConversion:
    ocpn: ObjectCentricPetriNet | None
    causal_net: ObjectCentricCausalNet | None
    exact: bool
    transition_mapping: tuple[tuple[str, tuple[str, ...]], ...]
    loss_report: tuple[str, ...]
    refusal_reasons: tuple[str, ...]
    profile: str


def _conversion_result(operator, digest, spec, value):
    issues = tuple(
        ComputeIssue("conversion_not_representable", reason)
        for reason in value.refusal_reasons
    )
    return _derived_result(
        operator,
        digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
    )


def ocpn_to_causal_net(
    net: ObjectCentricPetriNet, spec: ObjectConversionSpec = ObjectConversionSpec()
) -> ComputationResult[ObjectModelConversion]:
    """Exact conversion where each place has at most one producer/consumer.

    Shared choice places cannot be replaced by independent causal obligations
    without changing behavior. Such inputs produce a refusal report, not an
    approximate model. Silent transitions and boundary markings are retained.
    """
    if not isinstance(net, ObjectCentricPetriNet) or not isinstance(
        spec, ObjectConversionSpec
    ):
        raise TypeError("expected OCPN and ObjectConversionSpec")
    reasons = []
    channels = []
    for place in net.places:
        producers = [a.source for a in net.arcs if a.target == place.id]
        consumers = [a.target for a in net.arcs if a.source == place.id]
        if len(producers) > 1 or len(consumers) > 1:
            reasons.append(
                f"place {place.id} has multiple producer/consumer transitions; choice cannot be erased"
            )
        else:
            channels.append(
                CausalChannel(
                    place.id,
                    place.object_type,
                    producers[0] if producers else None,
                    consumers[0] if consumers else None,
                )
            )
    if reasons:
        payload = ObjectModelConversion(
            None, None, False, (), (), tuple(reasons), "refused_non_channel_ocpn"
        )
        return _conversion_result(
            "pix.object_centric.ocpn_to_causal_net", model_digest(net), spec, payload
        )
    place_types = {p.id: p.object_type for p in net.places}
    groups = {"input": [], "output": []}
    for transition in net.transitions:
        for direction in groups:
            arcs = [
                a
                for a in net.arcs
                if (
                    a.target == transition.id
                    if direction == "input"
                    else a.source == transition.id
                )
            ]
            markers = tuple(
                CausalMarker(
                    a.source if direction == "input" else a.target,
                    a.min_objects,
                    a.max_objects,
                )
                for a in arcs
            )
            equal = tuple(
                (left.channel_id, right.channel_id)
                for left, right in combinations(markers, 2)
                if place_types[left.channel_id] == place_types[right.channel_id]
            )
            groups[direction].append(
                CausalMarkerGroup(
                    direction + ":" + transition.id, transition.id, markers, equal
                )
            )
    target = ObjectCentricCausalNet(
        net.transitions,
        tuple(channels),
        tuple(groups["input"]),
        tuple(groups["output"]),
        net.initial_marking,
        net.final_marking,
        net.objects,
    )
    payload = ObjectModelConversion(
        None,
        target,
        True,
        tuple((t.id, (t.id,)) for t in net.transitions),
        (),
        (),
        "exact_unit_incidence_channel_net",
    )
    return _conversion_result(
        "pix.object_centric.ocpn_to_causal_net", model_digest(net), spec, payload
    )


def _equal_connected(group, channels):
    if len(channels) <= 1:
        return True
    adjacency: dict[str, set[str]] = defaultdict(set)
    for left, right in group.equal_channels:
        adjacency[left].add(right)
        adjacency[right].add(left)
    visited = {channels[0]}
    pending = [channels[0]]
    while pending:
        for nxt in adjacency[pending.pop()] - visited:
            visited.add(nxt)
            pending.append(nxt)
    return set(channels) <= visited


def causal_net_to_ocpn(
    net: ObjectCentricCausalNet, spec: ObjectConversionSpec = ObjectConversionSpec()
) -> ComputationResult[ObjectModelConversion]:
    """Unfold alternative marker groups into transitions when exactly representable.

    PIX OCPN requires the same selected object set on every incidence of a
    transition/type. Independent or disjoint channels cannot be encoded by
    widening arc intervals; the conversion reports and refuses them.
    """
    if not isinstance(net, ObjectCentricCausalNet) or not isinstance(
        spec, ObjectConversionSpec
    ):
        raise TypeError("expected causal net and ObjectConversionSpec")
    channel_types = {c.id: c.object_type for c in net.channels}
    inputs: dict[str, list] = defaultdict(list)
    outputs: dict[str, list] = defaultdict(list)
    for group in net.input_bindings:
        inputs[group.transition_id].append(group)
    for group in net.output_bindings:
        outputs[group.transition_id].append(group)
    reasons = []
    copies = sum(len(inputs[t.id]) * len(outputs[t.id]) for t in net.transitions)
    if copies > spec.max_transition_copies:
        reasons.append(
            f"requires {copies} transition copies, exceeding max_transition_copies"
        )
    for group in net.input_bindings + net.output_bindings:
        if group.disjoint_channels:
            reasons.append(
                f"group {group.id} has disjoint channel constraints outside the shared-object OCPN profile"
            )
        typed: dict[str, list[str]] = defaultdict(list)
        for marker in group.markers:
            typed[channel_types[marker.channel_id]].append(marker.channel_id)
        for kind, channels in typed.items():
            if not _equal_connected(group, channels):
                reasons.append(
                    f"group {group.id} permits independent object selections for type {kind}"
                )
    transitions = []
    arcs = []
    mapping = []
    losses = []
    if not reasons:
        used_ids = set(channel_types) | {t.id for t in net.transitions}
        for transition in net.transitions:
            new_ids = []
            for index, (ingroup, outgroup) in enumerate(
                product(inputs[transition.id], outputs[transition.id])
            ):
                policies: dict[str, tuple[int, int | None]] = {}
                for marker in ingroup.markers + outgroup.markers:
                    kind = channel_types[marker.channel_id]
                    previous = policies.get(kind)
                    minimum, maximum = marker.min_objects, marker.max_objects
                    if previous is not None:
                        minimum = max(minimum, previous[0])
                        maximum = (
                            previous[1]
                            if maximum is None
                            else maximum
                            if previous[1] is None
                            else min(maximum, previous[1])
                        )
                    policies[kind] = minimum, maximum
                if any(
                    maximum is not None and maximum < minimum
                    for minimum, maximum in policies.values()
                ):
                    losses.append(
                        f"unsatisfiable alternative pair {ingroup.id}/{outgroup.id} removed; it has no legal firing"
                    )
                    continue
                tid = transition.id
                if len(inputs[transition.id]) * len(outputs[transition.id]) > 1:
                    tid = f"causal:{transition.id}:{index}"
                    while tid in used_ids:
                        tid = ":" + tid
                    used_ids.add(tid)
                transitions.append(Transition(tid, transition.activity))
                new_ids.append(tid)
                for direction, group in (("input", ingroup), ("output", outgroup)):
                    for marker in group.markers:
                        minimum, maximum = policies[channel_types[marker.channel_id]]
                        source, target = (
                            (marker.channel_id, tid)
                            if direction == "input"
                            else (tid, marker.channel_id)
                        )
                        arcs.append(
                            ObjectArc(
                                source,
                                target,
                                (minimum, maximum) != (1, 1),
                                minimum,
                                maximum,
                            )
                        )
            mapping.append((transition.id, tuple(new_ids)))
        if any(len(ids) != 1 or ids[0] != original for original, ids in mapping):
            losses.append(
                "alternative group IDs are represented by transition copies; use transition_mapping to recover original transition identity"
            )
        target = ObjectCentricPetriNet(
            tuple(TypedPlace(c.id, c.object_type) for c in net.channels),
            tuple(transitions),
            tuple(arcs),
            net.initial_marking,
            net.final_marking,
            net.objects,
        )
    else:
        target = None
    payload = ObjectModelConversion(
        target,
        None,
        not reasons,
        tuple(mapping),
        tuple(losses),
        tuple(sorted(set(reasons))),
        "exact_shared_object_group_unfolding"
        if not reasons
        else "refused_nonrepresentable_marker_groups",
    )
    return _conversion_result(
        "pix.object_centric.causal_net_to_ocpn", causal_net_digest(net), spec, payload
    )


RESULT_SCHEMAS = {
    "pix.object_centric.project_ocpn": (
        "object-model-projection",
        ObjectProjectionSpec,
        ObjectModelTransformation,
    ),
    "pix.object_centric.hide_ocpn": (
        "object-model-hiding",
        ObjectHidingSpec,
        ObjectModelTransformation,
    ),
    "pix.object_centric.object_subnet": (
        "object-subnet",
        ObjectSubnetSpec,
        ObjectSubnet,
    ),
    "pix.object_centric.reduce_ocpn": (
        "object-model-reduction",
        ObjectReductionSpec,
        ObjectReduction,
    ),
    "pix.object_centric.object_place_invariants": (
        "object-place-invariants",
        ObjectInvariantSpec,
        ObjectInvariants,
    ),
    "pix.object_centric.analyze_ocpn_soundness": (
        "object-finite-universe-soundness",
        ObjectSoundnessSpec,
        ObjectSoundness,
    ),
    "pix.object_centric.ocpn_to_causal_net": (
        "ocpn-to-causal-net",
        ObjectConversionSpec,
        ObjectModelConversion,
    ),
    "pix.object_centric.causal_net_to_ocpn": (
        "causal-net-to-ocpn",
        ObjectConversionSpec,
        ObjectModelConversion,
    ),
}

__all__ = (
    "CausalChannel",
    "CausalMarker",
    "CausalMarkerGroup",
    "ObjectCentricCausalNet",
    "CausalFiring",
    "CausalBindingEnumeration",
    "causal_net_digest",
    "is_causal_binding_enabled",
    "fire_causal_binding",
    "causal_firing_objects",
    "enumerate_enabled_causal_bindings",
    "ObjectProjectionSpec",
    "ObjectHidingSpec",
    "ObjectModelTransformation",
    "project_ocpn",
    "hide_ocpn",
    "ObjectSubnetSpec",
    "ObjectSubnet",
    "object_subnet",
    "ObjectReductionSpec",
    "ObjectReductionStep",
    "ObjectReduction",
    "reduce_ocpn",
    "ObjectInvariantSpec",
    "TypedPlaceInvariants",
    "ObjectInvariants",
    "object_place_invariants",
    "ObjectSoundnessSpec",
    "ObjectReachabilityEdge",
    "ObjectSoundness",
    "analyze_ocpn_soundness",
    "ObjectConversionSpec",
    "ObjectModelConversion",
    "ocpn_to_causal_net",
    "causal_net_to_ocpn",
)
