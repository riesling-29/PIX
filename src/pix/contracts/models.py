"""Immutable executable model contracts, independent of PIX computation.

The OCPN profile uses unit arcs and one object set per transition/object type.
Variable arc bounds are explicit PIX constraints, not inferred frequencies.
This is a structural contract, not a soundness or boundedness certificate.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import ClassVar


def _text(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value.strip():
        raise ValueError(f"{field} must not be blank")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError(f"{field} must contain valid Unicode") from error


def _integer(value: object, field: str, *, minimum: int = 1) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if value < minimum:
        raise ValueError(f"{field} must be at least {minimum}")


def _tuple(value: object, item_type: type, field: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")
    if not all(isinstance(item, item_type) for item in value):
        raise TypeError(f"{field} items must be {item_type.__name__}")


@dataclass(frozen=True, slots=True, order=True)
class Place:
    id: str

    def __post_init__(self) -> None:
        _text(self.id, "Place.id")


@dataclass(frozen=True, slots=True)
class Transition:
    """Stable model node identity and semantic activity; None means silent.

    Activity is not a unique node ID. Different transitions may have the same
    activity. Display-only labels, coordinates and styles belong to the viewer.
    """

    id: str
    activity: str | None = None

    def __post_init__(self) -> None:
        _text(self.id, "Transition.id")
        if self.activity is not None:
            _text(self.activity, "Transition.activity")


@dataclass(frozen=True, slots=True, order=True)
class Arc:
    source: str
    target: str
    weight: int = 1

    def __post_init__(self) -> None:
        _text(self.source, "Arc.source")
        _text(self.target, "Arc.target")
        _integer(self.weight, "Arc.weight")


@dataclass(frozen=True, slots=True)
class Marking:
    """Sparse multiset: unique place entries with positive integer counts."""

    tokens: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        _tuple(self.tokens, tuple, "Marking.tokens")
        places: set[str] = set()
        for item in self.tokens:
            if len(item) != 2:
                raise ValueError("Marking.tokens entries must be (place_id, count)")
            place, count = item
            _text(place, "Marking place")
            _integer(count, "Marking count")
            if place in places:
                raise ValueError(f"duplicate marking place: {place}")
            places.add(place)
        object.__setattr__(self, "tokens", tuple(sorted(self.tokens)))


def _validate_graph(places: tuple, transitions: tuple, arcs: tuple) -> None:
    place_ids = {place.id for place in places}
    transition_ids = {transition.id for transition in transitions}
    if len(place_ids) != len(places):
        raise ValueError("duplicate place ID")
    if len(transition_ids) != len(transitions):
        raise ValueError("duplicate transition ID")
    if place_ids & transition_ids:
        raise ValueError("place and transition IDs must be disjoint")
    endpoints: set[tuple[str, str]] = set()
    for arc in arcs:
        if not (
            (arc.source in place_ids and arc.target in transition_ids)
            or (arc.source in transition_ids and arc.target in place_ids)
        ):
            raise ValueError("arc must connect an existing place and transition")
        pair = (arc.source, arc.target)
        if pair in endpoints:
            raise ValueError("duplicate arc incidence; use explicit multiplicity")
        endpoints.add(pair)


@dataclass(frozen=True, slots=True)
class PetriNet:
    """Accepting weighted place/transition net with explicit end markings."""

    places: tuple[Place, ...]
    transitions: tuple[Transition, ...]
    arcs: tuple[Arc, ...]
    initial_marking: Marking
    final_marking: Marking
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _tuple(self.places, Place, "PetriNet.places")
        _tuple(self.transitions, Transition, "PetriNet.transitions")
        _tuple(self.arcs, Arc, "PetriNet.arcs")
        _validate_graph(self.places, self.transitions, self.arcs)
        self.validate_marking(self.initial_marking)
        self.validate_marking(self.final_marking)
        object.__setattr__(self, "places", tuple(sorted(self.places)))
        object.__setattr__(
            self, "transitions", tuple(sorted(self.transitions, key=lambda t: t.id))
        )
        object.__setattr__(self, "arcs", tuple(sorted(self.arcs)))

    def validate_marking(self, marking: Marking) -> None:
        if not isinstance(marking, Marking):
            raise TypeError("Petri net marking must be a Marking")
        place_ids = {place.id for place in self.places}
        if any(place not in place_ids for place, _ in marking.tokens):
            raise ValueError("marking references an unknown place")


@dataclass(frozen=True, slots=True, order=True)
class TypedPlace:
    id: str
    object_type: str

    def __post_init__(self) -> None:
        _text(self.id, "TypedPlace.id")
        _text(self.object_type, "TypedPlace.object_type")


@dataclass(frozen=True, slots=True, order=True)
class ObjectArc:
    """Unit incidence with an explicit object-cardinality interval.

    A fixed arc always requires one bound object. A variable arc permits the
    stated interval; ``min_objects=0`` explicitly permits empty participation.
    All incidences for a transition/type must share the same interval.
    """

    source: str
    target: str
    variable: bool = False
    min_objects: int = 1
    max_objects: int | None = None

    def __post_init__(self) -> None:
        _text(self.source, "ObjectArc.source")
        _text(self.target, "ObjectArc.target")
        if not isinstance(self.variable, bool):
            raise TypeError("ObjectArc.variable must be bool")
        _integer(self.min_objects, "ObjectArc.min_objects", minimum=0)
        if self.max_objects is not None:
            _integer(self.max_objects, "ObjectArc.max_objects", minimum=0)
            if self.max_objects < self.min_objects:
                raise ValueError("maximum cardinality is smaller than minimum")
        if not self.variable:
            if self.min_objects != 1 or self.max_objects not in (None, 1):
                raise ValueError("fixed arcs require exactly one object")
            object.__setattr__(self, "max_objects", 1)


@dataclass(frozen=True, slots=True, order=True)
class ObjectToken:
    place_id: str
    object_id: str

    def __post_init__(self) -> None:
        _text(self.place_id, "ObjectToken.place_id")
        _text(self.object_id, "ObjectToken.object_id")


@dataclass(frozen=True, slots=True)
class ObjectMarking:
    """A multiset of concrete (place, object) tokens; repeats are preserved."""

    tokens: tuple[ObjectToken, ...] = ()

    def __post_init__(self) -> None:
        _tuple(self.tokens, ObjectToken, "ObjectMarking.tokens")
        object.__setattr__(self, "tokens", tuple(sorted(self.tokens)))


@dataclass(frozen=True, slots=True)
class Binding:
    """Explicit transition and selected object sets, keyed by object type."""

    transition_id: str
    objects: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        _text(self.transition_id, "Binding.transition_id")
        _tuple(self.objects, tuple, "Binding.objects")
        seen_types: set[str] = set()
        seen_objects: set[str] = set()
        normalized = []
        for item in self.objects:
            if len(item) != 2:
                raise ValueError("binding entries must be (object_type, object_ids)")
            object_type, ids = item
            _text(object_type, "Binding object type")
            _tuple(ids, str, "Binding object IDs")
            if object_type in seen_types:
                raise ValueError("duplicate binding object type")
            seen_types.add(object_type)
            for object_id in ids:
                _text(object_id, "Binding object ID")
                if object_id in seen_objects:
                    raise ValueError("duplicate binding object ID")
                seen_objects.add(object_id)
            normalized.append((object_type, tuple(sorted(ids))))
        object.__setattr__(self, "objects", tuple(sorted(normalized)))


@dataclass(frozen=True, slots=True)
class ObjectCentricPetriNet:
    """Accepting unit-incidence OCPN over an explicit finite object universe.

    Markings and all fired bindings refer to declared objects. Source and sink
    transitions may create/consume their tokens, but cannot create object IDs.
    Extra declared objects without tokens are retained in the model identity.
    """

    places: tuple[TypedPlace, ...]
    transitions: tuple[Transition, ...]
    arcs: tuple[ObjectArc, ...]
    initial_marking: ObjectMarking
    final_marking: ObjectMarking
    objects: tuple[tuple[str, str], ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _tuple(self.places, TypedPlace, "ObjectCentricPetriNet.places")
        _tuple(self.transitions, Transition, "ObjectCentricPetriNet.transitions")
        _tuple(self.arcs, ObjectArc, "ObjectCentricPetriNet.arcs")
        _tuple(self.objects, tuple, "ObjectCentricPetriNet.objects")
        object_ids: set[str] = set()
        for item in self.objects:
            if len(item) != 2:
                raise ValueError("objects entries must be (object_id, object_type)")
            object_id, object_type = item
            _text(object_id, "object ID")
            _text(object_type, "object type")
            if object_id in object_ids:
                raise ValueError("duplicate declared object ID")
            object_ids.add(object_id)
        _validate_graph(self.places, self.transitions, self.arcs)
        place_types = {place.id: place.object_type for place in self.places}
        policies: dict[tuple[str, str], tuple[bool, int, int | None]] = {}
        for arc in self.arcs:
            if arc.source in place_types:
                transition, object_type = arc.target, place_types[arc.source]
            else:
                transition, object_type = arc.source, place_types[arc.target]
            key = transition, object_type
            policy = arc.variable, arc.min_objects, arc.max_objects
            if key in policies and policies[key] != policy:
                raise ValueError(
                    "transition/object type arcs require one cardinality policy"
                )
            policies[key] = policy
        self.validate_marking(self.initial_marking)
        self.validate_marking(self.final_marking)
        object.__setattr__(self, "places", tuple(sorted(self.places)))
        object.__setattr__(
            self, "transitions", tuple(sorted(self.transitions, key=lambda t: t.id))
        )
        object.__setattr__(
            self, "arcs", tuple(sorted(self.arcs, key=lambda a: (a.source, a.target)))
        )
        object.__setattr__(self, "objects", tuple(sorted(self.objects)))

    def validate_marking(self, marking: ObjectMarking) -> None:
        if not isinstance(marking, ObjectMarking):
            raise TypeError("OCPN marking must be an ObjectMarking")
        place_types = {place.id: place.object_type for place in self.places}
        object_types = dict(self.objects)
        for token in marking.tokens:
            if token.place_id not in place_types:
                raise ValueError("object marking references an unknown place")
            if token.object_id not in object_types:
                raise ValueError("object marking references an undeclared object")
            if place_types[token.place_id] != object_types[token.object_id]:
                raise ValueError("object token type does not match its place")


@dataclass(frozen=True, slots=True)
class OCPNCardinalityProfile:
    """Exact marginal evidence, separate from the inferred arc interval."""

    activity: str
    object_type: str
    histogram: tuple[tuple[int, int], ...]
    arc_kind: str
    min_objects: int
    max_objects: int

    def __post_init__(self) -> None:
        _text(self.activity, "activity")
        _text(self.object_type, "object_type")
        _tuple(self.histogram, tuple, "histogram")
        if not self.histogram:
            raise ValueError("cardinality histogram must not be empty")
        counts = set()
        for row in self.histogram:
            if len(row) != 2:
                raise ValueError("histogram entries must be (cardinality, event_count)")
            _integer(row[0], "cardinality", minimum=0)
            _integer(row[1], "event_count")
            if row[0] in counts:
                raise ValueError("duplicate histogram cardinality")
            counts.add(row[0])
        _integer(self.min_objects, "min_objects", minimum=0)
        _integer(self.max_objects, "max_objects", minimum=0)
        if (self.min_objects, self.max_objects) != (min(counts), max(counts)):
            raise ValueError("observed_range bounds must match histogram extrema")
        kind = "absent" if counts == {0} else "fixed" if counts == {1} else "variable"
        if self.arc_kind != kind:
            raise ValueError("arc kind does not match observed cardinalities")
        object.__setattr__(self, "histogram", tuple(sorted(self.histogram)))


@dataclass(frozen=True, slots=True)
class OCPNTypeProjection:
    object_type: str
    trace_computation_id: str
    discovery_computation_id: str
    model_digest: str
    object_count: int
    isolated_object_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "object_type",
            "trace_computation_id",
            "discovery_computation_id",
            "model_digest",
        ):
            _text(getattr(self, name), name)
        _integer(self.object_count, "object_count")
        _tuple(self.isolated_object_ids, str, "isolated_object_ids")
        if len(set(self.isolated_object_ids)) != len(self.isolated_object_ids):
            raise ValueError("isolated object IDs must be unique")
        if len(self.isolated_object_ids) > self.object_count:
            raise ValueError("isolate count exceeds projection population")


@dataclass(frozen=True, slots=True)
class OCPNTransitionSource:
    object_type: str
    local_transition_id: str
    merged_transition_id: str

    def __post_init__(self) -> None:
        for name in ("object_type", "local_transition_id", "merged_transition_id"):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class OCPNObservedBinding:
    event_id: str
    activity: str
    binding: Binding

    def __post_init__(self) -> None:
        _text(self.event_id, "event_id")
        _text(self.activity, "activity")
        if not isinstance(self.binding, Binding):
            raise TypeError("binding must be Binding")


@dataclass(frozen=True, slots=True)
class OCPNFittingStep:
    """One executed step; None event_id means a type-local silent move."""

    event_id: str | None
    binding: Binding

    def __post_init__(self) -> None:
        if self.event_id is not None:
            _text(self.event_id, "event_id")
        if not isinstance(self.binding, Binding):
            raise TypeError("binding must be Binding")


def _validate_fitting_witness(
    model: ObjectCentricPetriNet, witness: tuple[OCPNFittingStep, ...]
) -> None:
    """Check an already supplied finite certificate, without computing a path.

    This stdlib-only contract check mirrors the unit-incidence arithmetic, so
    external artifacts cannot claim acceptance with disabled/unfinished steps.
    It performs no discovery, search, or implicit binding construction.
    """
    object_types = dict(model.objects)
    place_types = {place.id: place.object_type for place in model.places}
    incidence = {transition.id: [] for transition in model.transitions}
    for arc in model.arcs:
        incoming = arc.source in place_types
        transition_id = arc.target if incoming else arc.source
        place_id = arc.source if incoming else arc.target
        incidence[transition_id].append((incoming, place_id, arc))
    marking = Counter(model.initial_marking.tokens)
    for step in witness:
        binding = dict(step.binding.objects)
        arcs = incidence[step.binding.transition_id]
        required = {place_types[place_id] for _, place_id, _ in arcs}
        if set(binding) != required:
            raise ValueError("witness binding object types differ from incidence")
        for kind, object_ids in binding.items():
            if any(object_types.get(obj) != kind for obj in object_ids):
                raise ValueError(
                    "witness binding contains an unknown or mistyped object"
                )
        consumed: Counter[ObjectToken] = Counter()
        produced: Counter[ObjectToken] = Counter()
        for incoming, place_id, arc in arcs:
            object_ids = binding[place_types[place_id]]
            if len(object_ids) < arc.min_objects or (
                arc.max_objects is not None and len(object_ids) > arc.max_objects
            ):
                raise ValueError("witness binding violates arc cardinality")
            target = consumed if incoming else produced
            target.update(ObjectToken(place_id, obj) for obj in object_ids)
        if any(marking[token] < count for token, count in consumed.items()):
            raise ValueError("witness contains a disabled binding")
        marking.subtract(consumed)
        marking.update(produced)
    if +marking != Counter(model.final_marking.tokens):
        raise ValueError("witness does not reach the exact final marking")


@dataclass(frozen=True, slots=True)
class OCPNDiscoveryPayload:
    """Discovered model plus observational evidence and a finite fitting run.

    The witness establishes only that this selected object universe and this
    whole input log have an accepting run. It does not certify joint soundness,
    exact joint cardinality support, or a generalizable process constraint.
    """

    model: ObjectCentricPetriNet
    cardinality_profiles: tuple[OCPNCardinalityProfile, ...]
    projections: tuple[OCPNTypeProjection, ...]
    transition_sources: tuple[OCPNTransitionSource, ...]
    observed_event_bindings: tuple[OCPNObservedBinding, ...]
    fitting_witness: tuple[OCPNFittingStep, ...]
    event_scope: str = "whole_log"
    cardinality_scope: str = "per_activity_all_events"
    joint_cardinality_guarantee: str = "marginals_only"
    fitting_guarantee: str = "observed_log_accepting_run"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.model, ObjectCentricPetriNet):
            raise TypeError("model must be ObjectCentricPetriNet")
        for name, item_type in (
            ("cardinality_profiles", OCPNCardinalityProfile),
            ("projections", OCPNTypeProjection),
            ("transition_sources", OCPNTransitionSource),
            ("observed_event_bindings", OCPNObservedBinding),
            ("fitting_witness", OCPNFittingStep),
        ):
            _tuple(getattr(self, name), item_type, name)
        for name, required in (
            ("event_scope", "whole_log"),
            ("cardinality_scope", "per_activity_all_events"),
            ("joint_cardinality_guarantee", "marginals_only"),
            ("fitting_guarantee", "observed_log_accepting_run"),
        ):
            if getattr(self, name) != required:
                raise ValueError(f"unsupported {name}")
        transitions = {item.id: item.activity for item in self.model.transitions}
        visible_activities = [
            activity for activity in transitions.values() if activity is not None
        ]
        if len(set(visible_activities)) != len(visible_activities):
            raise ValueError(
                "unique_activity discovery requires one visible transition per activity"
            )
        events = {item.event_id: item for item in self.observed_event_bindings}
        if len(events) != len(self.observed_event_bindings):
            raise ValueError("duplicate observed event")
        for item in self.observed_event_bindings:
            if transitions.get(item.binding.transition_id) != item.activity:
                raise ValueError("observed binding activity differs from model")
        witnessed = []
        for step in self.fitting_witness:
            if step.binding.transition_id not in transitions:
                raise ValueError("witness references an unknown transition")
            if step.event_id is None:
                if transitions[step.binding.transition_id] is not None:
                    raise ValueError("unobserved witness steps must be silent")
            else:
                if (
                    step.event_id not in events
                    or events[step.event_id].binding != step.binding
                ):
                    raise ValueError("witness differs from observed event binding")
                witnessed.append(step.event_id)
        if tuple(witnessed) != tuple(events):
            raise ValueError("witness must consume every observed event once in order")
        projection_types = {item.object_type for item in self.projections}
        if not projection_types or len(projection_types) != len(self.projections):
            raise ValueError("projections must contain unique selected object types")
        objects = dict(self.model.objects)
        if set(objects.values()) != projection_types:
            raise ValueError("projection types differ from the model object universe")
        if {place.object_type for place in self.model.places} != projection_types:
            raise ValueError("projection types differ from the model place types")
        participants = {
            obj
            for item in self.observed_event_bindings
            for _, ids in item.binding.objects
            for obj in ids
        }
        for projection in self.projections:
            typed_objects = {
                obj for obj, kind in objects.items() if kind == projection.object_type
            }
            if projection.object_count != len(typed_objects):
                raise ValueError("projection object count differs from the model")
            if set(projection.isolated_object_ids) != typed_objects - participants:
                raise ValueError(
                    "isolated object evidence differs from observed bindings"
                )
        activities = {item.activity for item in self.observed_event_bindings}
        if {
            activity for activity in transitions.values() if activity is not None
        } != activities:
            raise ValueError(
                "visible model activities differ from whole-log observations"
            )
        profiles = {
            (item.activity, item.object_type): item
            for item in self.cardinality_profiles
        }
        if len(profiles) != len(self.cardinality_profiles) or set(profiles) != {
            (activity, kind) for activity in activities for kind in projection_types
        }:
            raise ValueError(
                "cardinality profiles must cover every activity and selected type"
            )
        for (activity, kind), profile in profiles.items():
            counts = Counter(
                len(dict(item.binding.objects).get(kind, ()))
                for item in self.observed_event_bindings
                if item.activity == activity
            )
            if tuple(sorted(counts.items())) != profile.histogram:
                raise ValueError("cardinality histogram differs from observed bindings")
        local_sources = set()
        place_types = {place.id: place.object_type for place in self.model.places}
        actual_incidence = {
            (
                arc.target if arc.source in place_types else arc.source,
                place_types[arc.source if arc.source in place_types else arc.target],
            )
            for arc in self.model.arcs
        }
        mapped_incidence = set()
        for source in self.transition_sources:
            local_key = source.object_type, source.local_transition_id
            if local_key in local_sources:
                raise ValueError("duplicate local transition source")
            local_sources.add(local_key)
            merged_key = source.merged_transition_id, source.object_type
            if merged_key in mapped_incidence:
                raise ValueError(
                    "multiple local transitions cannot map to one merged transition and type"
                )
            mapped_incidence.add(merged_key)
        if mapped_incidence != actual_incidence:
            raise ValueError("transition source mapping differs from model incidence")
        for arc in self.model.arcs:
            incoming = arc.source in place_types
            activity = transitions[arc.target if incoming else arc.source]
            kind = place_types[arc.source if incoming else arc.target]
            if activity is None:
                expected = False, 1, 1
            else:
                profile = profiles[activity, kind]
                expected = (
                    profile.arc_kind == "variable",
                    profile.min_objects,
                    profile.max_objects,
                )
            if (arc.variable, arc.min_objects, arc.max_objects) != expected:
                raise ValueError(
                    "model arc differs from inferred observed-range policy"
                )
        _validate_fitting_witness(self.model, self.fitting_witness)


__all__ = [
    "Arc",
    "Binding",
    "Marking",
    "ObjectArc",
    "ObjectCentricPetriNet",
    "ObjectMarking",
    "ObjectToken",
    "OCPNCardinalityProfile",
    "OCPNDiscoveryPayload",
    "OCPNFittingStep",
    "OCPNObservedBinding",
    "OCPNTransitionSource",
    "OCPNTypeProjection",
    "PetriNet",
    "Place",
    "Transition",
    "TypedPlace",
]
