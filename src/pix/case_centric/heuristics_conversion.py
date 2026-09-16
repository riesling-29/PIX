"""Native accepting Petri-net construction from explicit HeuristicsNet bindings.

This is the ``pix.heuristics.bindings.v1`` obligation-token profile: each edge
has a place, each input binding consumes one token from every member edge,
and each output binding produces one token on every member edge. Alternatives
are exclusive choices of AND sets; they are not a dynamic inclusive-OR join.
Input and output alternatives are independent. Silent joins/splits surround
exactly one visible transition per activity; frequencies do not become arc
weights. Repeated occurrences and cycles use the same multiset places.

Observed trace starts/ends supply exclusive source/sink alternatives, even for
activities with incoming/outgoing dependencies. They do not imply parallel
start/end groups. The final marking must contain only the single sink token;
leftover obligations cannot disappear. Empty traces add a source-to-sink tau.
No soundness, boundedness, log-fitness or upstream-conversion parity is claimed.

The miner currently omits self-neighbours when producing bindings. A selected
self-edge therefore cannot be converted unless the caller supplies complete
explicit self bindings; silently ignoring or inventing them changes meaning.
No missing bindings or filtered-away boundaries are reconstructed here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from typing import ClassVar, Literal

from pix.case_centric.heuristics import (
    HeuristicsActivity,
    HeuristicsBinding,
    HeuristicsNet,
)
from pix.compute._common import _derived_result
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
    _immutable,
)

OPERATOR_ID = "pix.case_centric.heuristics_to_petri_net"
PROFILE = "pix.heuristics.bindings.v1"


@dataclass(frozen=True, slots=True)
class HeuristicsConversionSpec:
    """Bounds stop construction rather than return an incomplete net."""

    max_net_nodes: int = 200_000
    max_net_arcs: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.HeuristicsConversionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("max_net_nodes", "max_net_arcs"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class HeuristicsConversionRequest:
    """Include model content even when the source identifies an earlier log."""

    model_digest: str | None
    parameters: HeuristicsConversionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.HeuristicsConversionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class HeuristicsEdgePlace:
    source: str
    target: str
    place_id: str


@dataclass(frozen=True, slots=True)
class HeuristicsBindingTransition:
    activity: str
    direction: Literal["input", "output", "start", "end"]
    members: tuple[str, ...]
    transition_id: str


@dataclass(frozen=True, slots=True)
class HeuristicsConversion:
    model: PetriNet
    profile: str
    source_model_digest: str
    activity_transitions: tuple[tuple[str, str], ...]
    edge_places: tuple[HeuristicsEdgePlace, ...]
    binding_transitions: tuple[HeuristicsBindingTransition, ...]


class _Unsupported(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _integer(value: object, field: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{field} must be an integer >= {minimum}")


def _validate(net: HeuristicsNet):
    if not isinstance(net.profile, str) or not net.profile.strip():
        raise ValueError("HeuristicsNet.profile must be nonblank text")
    _integer(net.trace_count, "trace_count")
    _integer(net.empty_trace_count, "empty_trace_count")
    if net.empty_trace_count > net.trace_count:
        raise ValueError("empty_trace_count exceeds trace_count")
    if not isinstance(net.activities, tuple) or not all(
        isinstance(a, HeuristicsActivity) for a in net.activities
    ):
        raise ValueError("activities must be a tuple of HeuristicsActivity")
    activities = {}
    for row in net.activities:
        if not isinstance(row.activity, str) or not row.activity.strip():
            raise ValueError("activity labels must be nonblank strings")
        row.activity.encode("utf-8")
        if row.activity in activities:
            raise ValueError("duplicate activity label")
        for name in ("count", "start_count", "end_count"):
            _integer(
                getattr(row, name), f"activity {name}", 1 if name == "count" else 0
            )
        if row.start_count > row.count or row.end_count > row.count:
            raise ValueError("activity boundary count exceeds activity count")
        activities[row.activity] = row
    nonempty = net.trace_count - net.empty_trace_count
    if (
        sum(row.start_count for row in net.activities) > nonempty
        or sum(row.end_count for row in net.activities) > nonempty
    ):
        raise ValueError("boundary counts exceed nonempty trace count")
    if activities and not nonempty:
        raise ValueError("activity observations require a nonempty trace")
    if not isinstance(net.edges, tuple):
        raise ValueError("edges must be a tuple")
    edges = set()
    incoming = {activity: set() for activity in activities}
    outgoing = {activity: set() for activity in activities}
    for edge in net.edges:
        if (
            not isinstance(edge, tuple)
            or len(edge) != 2
            or any(not isinstance(a, str) or a not in activities for a in edge)
        ):
            raise ValueError("edges must reference two known activity labels")
        if edge in edges:
            raise ValueError("duplicate dependency edge")
        edges.add(edge)
        incoming[edge[1]].add(edge[0])
        outgoing[edge[0]].add(edge[1])
    if not isinstance(net.bindings, tuple) or not all(
        isinstance(b, HeuristicsBinding) for b in net.bindings
    ):
        raise ValueError("bindings must be a tuple of HeuristicsBinding")
    bindings = {}
    for row in net.bindings:
        if (
            not isinstance(row.activity, str)
            or row.activity not in activities
            or row.direction not in ("input", "output")
        ):
            raise ValueError("binding activity/direction is invalid")
        key = (row.activity, row.direction)
        if key in bindings:
            raise ValueError("duplicate activity/direction binding")
        if not isinstance(row.alternatives, tuple):
            raise ValueError("binding alternatives must be a tuple")
        normalized = []
        for members in row.alternatives:
            if (
                not isinstance(members, tuple)
                or not members
                or any(not isinstance(a, str) or a not in activities for a in members)
            ):
                raise ValueError(
                    "each binding must be a nonempty tuple of known activities"
                )
            if len(set(members)) != len(members):
                raise ValueError("duplicate member in an AND binding")
            normalized.append(tuple(sorted(members)))
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate alternative binding")
        bindings[key] = tuple(sorted(normalized))
    required = {
        (activity, direction)
        for activity in activities
        for direction in ("input", "output")
    }
    if set(bindings) != required:
        raise ValueError(
            "exactly one input and one output binding row is required per activity"
        )
    for (activity, direction), alternatives in bindings.items():
        actual = {member for members in alternatives for member in members}
        expected = incoming[activity] if direction == "input" else outgoing[activity]
        if (activity, activity) in edges and activity not in actual:
            raise _Unsupported(
                "heuristics_self_loop_binding_missing",
                "A retained self-edge is absent from explicit bindings; its loop semantics cannot be inferred",
            )
        if actual != expected:
            raise ValueError(
                "binding members must cover exactly their incident dependency edges"
            )
    starts = tuple(
        sorted(row.activity for row in activities.values() if row.start_count)
    )
    ends = tuple(sorted(row.activity for row in activities.values() if row.end_count))
    if not net.trace_count:
        raise _Unsupported("heuristics_empty_log", "No observed traces are available")
    if activities and (not starts or not ends):
        raise _Unsupported(
            "heuristics_boundary_unavailable",
            "Observed retained start and end activities are required; boundaries are not inferred from graph roots",
        )
    if not activities and nonempty:
        raise _Unsupported(
            "heuristics_activities_unavailable",
            "Nonempty traces have no retained activity; epsilon cannot stand in for their behavior",
        )
    return activities, tuple(sorted(edges)), bindings, starts, ends


def heuristics_to_petri_net(
    net: HeuristicsNet | ComputationResult[HeuristicsNet],
    spec: HeuristicsConversionSpec = HeuristicsConversionSpec(),
) -> ComputationResult[HeuristicsConversion]:
    """Convert complete explicit bindings into an accepting multiset P/T net.

    Bare-model source identity is a canonical typed hash of the complete
    HeuristicsNet. Derived results retain the log's source identity, parent ID
    and issues; the request also includes the exact input-model digest.
    """
    if not isinstance(spec, HeuristicsConversionSpec):
        raise TypeError("spec must be HeuristicsConversionSpec")
    parent = net if isinstance(net, ComputationResult) else None
    if parent is None and not isinstance(net, HeuristicsNet):
        raise TypeError("net must be HeuristicsNet or ComputationResult[HeuristicsNet]")
    source = parent.source_digest if parent is not None else None
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    inherited = parent.issues if parent is not None else ()
    digest = None

    def result(status, value=None, issues=()):
        return _derived_result(
            OPERATOR_ID,
            source,
            HeuristicsConversionRequest(digest, spec),
            status,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None:
        if parent.status is not ComputeStatus.COMPUTED or parent.value is None:
            return result(
                ComputeStatus.UNAVAILABLE,
                issues=(
                    ComputeIssue(
                        "heuristics_input_unavailable",
                        "A complete HeuristicsNet result is required",
                    ),
                ),
            )
        net = parent.value
    if not isinstance(net, HeuristicsNet):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_heuristics_net", "Result payload must be HeuristicsNet"
                ),
            ),
        )
    try:
        if not _immutable(net):
            raise ValueError("HeuristicsNet must contain immutable finite fields")
        encoded = json.dumps(
            _identity_value(net),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = "pix.heuristics-net.v1:sha256:" + sha256(encoded).hexdigest()
        if parent is None:
            source = digest
        activities, edges, bindings, starts, ends = _validate(net)
    except _Unsupported as exc:
        return result(
            ComputeStatus.UNAVAILABLE, issues=(ComputeIssue(exc.code, str(exc)),)
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_heuristics_net", str(exc)),),
        )

    binding_count = sum(len(alternatives) for alternatives in bindings.values())
    boundary_count = len(starts) + len(ends) + bool(net.empty_trace_count)
    node_count = 2 + len(edges) + 3 * len(activities) + binding_count + boundary_count
    arc_count = (
        2 * len(activities)
        + sum(
            len(members) + 1
            for alternatives in bindings.values()
            for members in alternatives
        )
        + 2 * boundary_count
    )
    if node_count > spec.max_net_nodes or arc_count > spec.max_net_arcs:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "heuristics_conversion_limit",
                    "Complete construction exceeds max_net_nodes or max_net_arcs; no partial net was returned",
                ),
            ),
        )

    numbers = {activity: index for index, activity in enumerate(sorted(activities))}
    start_set, end_set = set(starts), set(ends)
    edge_ids = {edge: f"h:p:edge:{index}" for index, edge in enumerate(edges)}
    places = [
        Place("h:p:source"),
        Place("h:p:sink"),
        *(Place(place) for place in edge_ids.values()),
    ]
    transitions = []
    arcs = []
    activity_witnesses = []
    binding_witnesses = []

    def silent(activity, direction, members, incoming, outgoing):
        transition_id = f"h:t:route:{len(binding_witnesses)}"
        transitions.append(Transition(transition_id))
        arcs.extend(Arc(place, transition_id) for place in incoming)
        arcs.extend(Arc(transition_id, place) for place in outgoing)
        binding_witnesses.append(
            HeuristicsBindingTransition(activity, direction, members, transition_id)
        )

    for activity, number in numbers.items():
        before, after, visible = (
            f"h:p:before:{number}",
            f"h:p:after:{number}",
            f"h:t:activity:{number}",
        )
        places.extend((Place(before), Place(after)))
        transitions.append(Transition(visible, activity))
        arcs.extend((Arc(before, visible), Arc(visible, after)))
        activity_witnesses.append((activity, visible))
        for members in bindings[activity, "input"]:
            silent(
                activity,
                "input",
                members,
                tuple(edge_ids[member, activity] for member in members),
                (before,),
            )
        for members in bindings[activity, "output"]:
            silent(
                activity,
                "output",
                members,
                (after,),
                tuple(edge_ids[activity, member] for member in members),
            )
        if activity in start_set:
            silent(activity, "start", (), ("h:p:source",), (before,))
        if activity in end_set:
            silent(activity, "end", (), (after,), ("h:p:sink",))
    if net.empty_trace_count:
        transitions.append(Transition("h:t:epsilon"))
        arcs.extend((Arc("h:p:source", "h:t:epsilon"), Arc("h:t:epsilon", "h:p:sink")))
    model = PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking((("h:p:source", 1),)),
        Marking((("h:p:sink", 1),)),
    )
    payload = HeuristicsConversion(
        model,
        PROFILE,
        digest,
        tuple(activity_witnesses),
        tuple(
            HeuristicsEdgePlace(source, target, edge_ids[source, target])
            for source, target in edges
        ),
        tuple(binding_witnesses),
    )
    return result(
        ComputeStatus.COMPUTED,
        payload,
        (
            ComputeIssue(
                "heuristics_binding_profile",
                "Explicit OR-of-AND bindings and observed exclusive trace boundaries were converted; soundness, boundedness, log fitness and upstream parity are not certified",
            ),
        ),
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "heuristics_conversion",
        HeuristicsConversionRequest,
        HeuristicsConversion,
    )
}

__all__ = (
    "HeuristicsConversionSpec",
    "HeuristicsConversionRequest",
    "HeuristicsEdgePlace",
    "HeuristicsBindingTransition",
    "HeuristicsConversion",
    "heuristics_to_petri_net",
)
