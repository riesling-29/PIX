"""Evidence-bearing Karp--Miller coverability for finite weighted P/T nets.

``None`` in an OmegaMarking denotes omega, never an unknown token count. The
tree covers reachable markings; its omega labels are not executable markings.
Every acceleration compares the *raw* successor with ancestors on the same
branch (including its parent), simultaneously. Equal ancestor labels close a
branch. Nodes from unrelated branches are never used for acceleration/pruning.

This follows the classical construction in Reynier and Servais, section 3.1,
Algorithm 1: https://documentserver.uhasselt.be/bitstream/1942/14846/1/hal.pdf
It does not implement their additional monotone-pruning algorithm. Reset,
inhibitor, capacity, timed, and object-centric nets are outside this contract.
Coverability is not exact reachability, liveness, termination, or soundness.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import ClassVar

from pix.compute._common import _result
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")
    value.encode("utf-8")


def _tuple(value: object, kind: type, name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(v, kind) for v in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _ids(value: object, name: str) -> None:
    _tuple(value, str, name)
    for item in value:
        _text(item, name)


def _optional_bool(value: object, name: str) -> None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{name} must be bool or None")


@dataclass(frozen=True, slots=True)
class OmegaMarking:
    """Sparse immutable marking: positive finite integers or None (= omega)."""

    tokens: tuple[tuple[str, int | None], ...] = ()

    def __post_init__(self) -> None:
        _tuple(self.tokens, tuple, "tokens")
        seen = set()
        for pair in self.tokens:
            if len(pair) != 2:
                raise ValueError("tokens entries must be (place_id, count)")
            place, count = pair
            _text(place, "place_id")
            if count is not None:
                _integer(count, "count", 1)
            if place in seen:
                raise ValueError("duplicate marking place")
            seen.add(place)
        object.__setattr__(self, "tokens", tuple(sorted(self.tokens)))


@dataclass(frozen=True, slots=True)
class CoverabilitySpec:
    """Caps tree nodes and fully/partially expanded nodes, including the root.

    ``target`` asks whether a reachable marking covers all its token demands,
    with extra tokens permitted. Absence of a witness is false only after the
    entire tree is complete. Caps never become token bounds or omega values.
    """

    max_nodes: int = 10000
    max_expansions: int = 10000
    target: Marking | None = None
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.coverability.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.max_nodes, "max_nodes", 1)
        _integer(self.max_expansions, "max_expansions", 1)
        if self.target is not None and not isinstance(self.target, Marking):
            raise TypeError("target must be Marking or None")


@dataclass(frozen=True, slots=True)
class CoverabilityNode:
    id: int
    parent_id: int | None
    transition_id: str | None
    marking: OmegaMarking
    enabled_transition_ids: tuple[str, ...]
    duplicate_ancestor_id: int | None = None
    expanded: bool = False

    def __post_init__(self) -> None:
        _integer(self.id, "id")
        if (self.parent_id is None) != (self.transition_id is None):
            raise ValueError("parent and transition must coexist")
        if self.parent_id is not None:
            _integer(self.parent_id, "parent_id")
            _text(self.transition_id, "transition_id")
            if self.parent_id >= self.id:
                raise ValueError("parent must precede child")
        elif self.id != 0:
            raise ValueError("only node zero may be the root")
        if not isinstance(self.marking, OmegaMarking):
            raise TypeError("marking must be OmegaMarking")
        _ids(self.enabled_transition_ids, "enabled_transition_ids")
        if len(set(self.enabled_transition_ids)) != len(self.enabled_transition_ids):
            raise ValueError("duplicate enabled transition")
        if self.duplicate_ancestor_id is not None:
            _integer(self.duplicate_ancestor_id, "duplicate_ancestor_id")
            if self.duplicate_ancestor_id >= self.id:
                raise ValueError("duplicate ancestor must precede node")
        if not isinstance(self.expanded, bool):
            raise TypeError("expanded must be bool")


@dataclass(frozen=True, slots=True)
class CoverabilityAcceleration:
    """Branch-local comparison certificate, possibly involving prior omegas.

    ``successor`` is the raw weighted firing result, before all simultaneous
    accelerations on this edge. The transition path starts at ``ancestor_id``.
    An omega-containing path is symbolic, not a concrete executable witness.
    """

    node_id: int
    ancestor_id: int
    successor: OmegaMarking
    accelerated_place_ids: tuple[str, ...]
    transition_path: tuple[str, ...]

    def __post_init__(self) -> None:
        _integer(self.node_id, "node_id", 1)
        _integer(self.ancestor_id, "ancestor_id")
        if self.ancestor_id >= self.node_id:
            raise ValueError("ancestor must precede node")
        if not isinstance(self.successor, OmegaMarking):
            raise TypeError("successor must be OmegaMarking")
        _ids(self.accelerated_place_ids, "accelerated_place_ids")
        _ids(self.transition_path, "transition_path")
        if not self.accelerated_place_ids or not self.transition_path:
            raise ValueError("acceleration requires growing places and a path")
        if len(set(self.accelerated_place_ids)) != len(self.accelerated_place_ids):
            raise ValueError("duplicate accelerated place")


@dataclass(frozen=True, slots=True)
class PumpingWitness:
    """Executable finite prefix followed by a repeatable self-covering cycle.

    Firing the prefix from the initial marking reaches ``before``. The cycle
    reaches ``after >= before`` with a strict increase in each growing place.
    Weighted P/T monotonicity permits repeating that cycle without bound.
    """

    ancestor_id: int
    node_id: int
    prefix_transition_ids: tuple[str, ...]
    cycle_transition_ids: tuple[str, ...]
    before: Marking
    after: Marking
    growing_place_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _integer(self.ancestor_id, "ancestor_id")
        _integer(self.node_id, "node_id", 1)
        if self.ancestor_id >= self.node_id:
            raise ValueError("ancestor must precede node")
        _ids(self.prefix_transition_ids, "prefix_transition_ids")
        _ids(self.cycle_transition_ids, "cycle_transition_ids")
        _ids(self.growing_place_ids, "growing_place_ids")
        if not isinstance(self.before, Marking) or not isinstance(self.after, Marking):
            raise TypeError("before and after must be Marking")
        before, after = dict(self.before.tokens), dict(self.after.tokens)
        if not self.cycle_transition_ids or not self.growing_place_ids:
            raise ValueError("pumping witness requires a cycle and growing places")
        if any(after.get(p, 0) < count for p, count in before.items()):
            raise ValueError("pumping cycle must cover its starting marking")
        growth = tuple(sorted(p for p, n in after.items() if n > before.get(p, 0)))
        if tuple(sorted(self.growing_place_ids)) != growth:
            raise ValueError("growing places must match the strict increases")


@dataclass(frozen=True, slots=True)
class CoverabilityBoundary:
    source_id: int
    transition_id: str | None
    reason: str

    def __post_init__(self) -> None:
        _integer(self.source_id, "source_id")
        if self.transition_id is not None:
            _text(self.transition_id, "transition_id")
        if self.reason not in ("max_nodes", "max_expansions"):
            raise ValueError("unsupported boundary reason")


@dataclass(frozen=True, slots=True)
class PlaceBound:
    """``bound`` is the exact finite supremum only when bounded is True."""

    place_id: str
    bounded: bool | None
    bound: int | None
    max_observed_finite: int
    omega_node_id: int | None

    def __post_init__(self) -> None:
        _text(self.place_id, "place_id")
        _optional_bool(self.bounded, "bounded")
        _integer(self.max_observed_finite, "max_observed_finite")
        if self.bound is not None:
            _integer(self.bound, "bound")
        if self.omega_node_id is not None:
            _integer(self.omega_node_id, "omega_node_id")
        if (self.bounded is True) != (self.bound is not None):
            raise ValueError("finite bound exists exactly when bounded is True")
        if (self.bounded is False) != (self.omega_node_id is not None):
            raise ValueError("unbounded place requires an omega node")
        if self.bound is not None and self.bound != self.max_observed_finite:
            raise ValueError("complete finite supremum must match observed maximum")


@dataclass(frozen=True, slots=True)
class Coverability:
    model_digest: str
    place_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    nodes: tuple[CoverabilityNode, ...]
    accelerations: tuple[CoverabilityAcceleration, ...]
    pumping_witnesses: tuple[PumpingWitness, ...]
    boundary: tuple[CoverabilityBoundary, ...]
    frontier_node_ids: tuple[int, ...]
    expanded_nodes: int
    complete: bool
    bounded: bool | None
    place_bounds: tuple[PlaceBound, ...]
    dead_transition_ids: tuple[str, ...]
    unobserved_transition_ids: tuple[str, ...]
    target: Marking | None
    target_coverable: bool | None
    target_covering_node_id: int | None

    def __post_init__(self) -> None:
        _text(self.model_digest, "model_digest")
        _ids(self.place_ids, "place_ids")
        _ids(self.transition_ids, "transition_ids")
        _tuple(self.nodes, CoverabilityNode, "nodes")
        _tuple(self.accelerations, CoverabilityAcceleration, "accelerations")
        _tuple(self.pumping_witnesses, PumpingWitness, "pumping_witnesses")
        _tuple(self.boundary, CoverabilityBoundary, "boundary")
        _tuple(self.place_bounds, PlaceBound, "place_bounds")
        _tuple(self.frontier_node_ids, int, "frontier_node_ids")
        for node_id in self.frontier_node_ids:
            _integer(node_id, "frontier node ID")
        _integer(self.expanded_nodes, "expanded_nodes")
        if not isinstance(self.complete, bool):
            raise TypeError("complete must be bool")
        _optional_bool(self.bounded, "bounded")
        _optional_bool(self.target_coverable, "target_coverable")
        _ids(self.dead_transition_ids, "dead_transition_ids")
        _ids(self.unobserved_transition_ids, "unobserved_transition_ids")
        if self.target is not None and not isinstance(self.target, Marking):
            raise TypeError("target must be Marking or None")
        if self.target_covering_node_id is not None:
            _integer(self.target_covering_node_id, "target_covering_node_id")
        if not self.nodes or tuple(n.id for n in self.nodes) != tuple(
            range(len(self.nodes))
        ):
            raise ValueError("tree requires contiguous node IDs starting at zero")
        places, transitions = set(self.place_ids), set(self.transition_ids)
        if len(places) != len(self.place_ids) or len(transitions) != len(
            self.transition_ids
        ):
            raise ValueError("place/transition IDs must be unique")
        if places & transitions:
            raise ValueError("place and transition IDs must be disjoint")
        for node in self.nodes:
            if any(p not in places for p, _ in node.marking.tokens):
                raise ValueError("node marking references unknown place")
            if not set(node.enabled_transition_ids) <= transitions:
                raise ValueError("node references unknown enabled transition")
            if node.transition_id is not None and node.transition_id not in transitions:
                raise ValueError("node references unknown incoming transition")
        refs = self.frontier_node_ids + tuple(b.source_id for b in self.boundary)
        refs += tuple(a.node_id for a in self.accelerations)
        refs += tuple(w.node_id for w in self.pumping_witnesses)
        if self.target_covering_node_id is not None:
            refs += (self.target_covering_node_id,)
        if any(index >= len(self.nodes) for index in refs):
            raise ValueError("reference to missing tree node")
        if self.complete != (not self.boundary and not self.frontier_node_ids):
            raise ValueError("complete tree cannot have a boundary or frontier")
        if self.bounded is True and not self.complete:
            raise ValueError("boundedness proof requires a complete tree")
        if self.bounded is False and not self.pumping_witnesses:
            raise ValueError("unboundedness requires a concrete pumping witness")
        if tuple(p.place_id for p in self.place_bounds) != self.place_ids:
            raise ValueError("place bounds must cover ordered places exactly")
        if self.dead_transition_ids and not self.complete:
            raise ValueError("dead-transition proof requires complete exploration")
        if self.target is None and (
            self.target_coverable is not None
            or self.target_covering_node_id is not None
        ):
            raise ValueError("target assessment requires a target")
        if self.target_coverable is False and not self.complete:
            raise ValueError("negative target assessment requires completion")
        if (self.target_coverable is True) != (
            self.target_covering_node_id is not None
        ):
            raise ValueError("positive target assessment requires a covering node")
        _validate_evidence(self)


def _leq(left, right):
    return all(b is None or (a is not None and a <= b) for a, b in zip(left, right))


def _marking(places, vector):
    return OmegaMarking(tuple((p, n) for p, n in zip(places, vector) if n != 0))


def _path(nodes, ancestor_id, descendant_id):
    result = []
    while descendant_id != ancestor_id:
        if descendant_id is None:
            raise ValueError("certificate ancestor is not on the node's branch")
        node = nodes[descendant_id]
        result.append(node.transition_id)
        descendant_id = node.parent_id
    return tuple(reversed(result))


def _validate_evidence(report):
    """Check internal proof references, not firing correctness without the net."""
    nodes = report.nodes
    places = report.place_ids
    mappings = tuple(dict(node.marking.tokens) for node in nodes)
    vectors = tuple(tuple(m.get(p, 0) for p in places) for m in mappings)
    if None in vectors[0]:
        raise ValueError("initial tree marking must be finite")
    children = {node.id: set() for node in nodes}
    for node in nodes[1:]:
        if node.transition_id in children[node.parent_id]:
            raise ValueError("tree node may have only one child per transition")
        children[node.parent_id].add(node.transition_id)
    for node in nodes:
        if node.parent_id is not None:
            parent = nodes[node.parent_id]
            if node.transition_id not in parent.enabled_transition_ids:
                raise ValueError("edge transition must be enabled at its parent")
        if node.duplicate_ancestor_id is not None:
            _path(nodes, node.duplicate_ancestor_id, node.id)
            if node.marking != nodes[node.duplicate_ancestor_id].marking:
                raise ValueError("duplicate ancestor must have the same marking")
            if node.expanded:
                raise ValueError("ancestor-duplicate leaves cannot be expanded")
            if children[node.id]:
                raise ValueError("ancestor-duplicate leaves cannot have children")
        if node.expanded and children[node.id] != set(node.enabled_transition_ids):
            raise ValueError("expanded node must include every enabled successor")
    expected_frontier = {
        node.id
        for node in nodes
        if not node.expanded and node.duplicate_ancestor_id is None
    }
    if set(report.frontier_node_ids) != expected_frontier or len(
        set(report.frontier_node_ids)
    ) != len(report.frontier_node_ids):
        raise ValueError("frontier must contain exactly all unresolved nodes")
    partial_expansions = 0
    for boundary in report.boundary:
        if boundary.source_id not in expected_frontier:
            raise ValueError("boundary must reference the unresolved frontier")
        if boundary.reason == "max_nodes":
            if (
                boundary.transition_id
                not in nodes[boundary.source_id].enabled_transition_ids
            ):
                raise ValueError("node cap boundary requires an enabled transition")
            partial_expansions += 1
        elif boundary.transition_id is not None:
            raise ValueError("expansion cap precedes selection of a transition")
    if report.expanded_nodes != sum(n.expanded for n in nodes) + partial_expansions:
        raise ValueError("expanded_nodes must match completed and partial expansions")
    unbounded = any(None in vector for vector in vectors)
    expected_bounded = False if unbounded else True if report.complete else None
    if report.bounded is not expected_bounded:
        raise ValueError("boundedness must agree with completion and omega evidence")
    for index, bound in enumerate(report.place_bounds):
        omega = next((n for n, v in enumerate(vectors) if v[index] is None), None)
        maximum = max(v[index] for v in vectors if v[index] is not None)
        expected = PlaceBound(
            places[index],
            False if omega is not None else True if report.complete else None,
            maximum if report.complete and omega is None else None,
            maximum,
            omega,
        )
        if bound != expected:
            raise ValueError("place bounds must agree with tree evidence")
    observed = {tid for node in nodes for tid in node.enabled_transition_ids}
    unseen = tuple(t for t in report.transition_ids if t not in observed)
    if report.dead_transition_ids != (unseen if report.complete else ()):
        raise ValueError(
            "dead transitions must match the complete enabled-transition evidence"
        )
    if report.unobserved_transition_ids != (unseen if not report.complete else ()):
        raise ValueError("unobserved transitions must match incomplete exploration")
    if report.target is not None:
        target_map = dict(report.target.tokens)
        if not set(target_map) <= set(places):
            raise ValueError("target references unknown place")
        target = tuple(target_map.get(p, 0) for p in places)
        covering = tuple(i for i, v in enumerate(vectors) if _leq(target, v))
        expected = True if covering else False if report.complete else None
        if report.target_coverable is not expected:
            raise ValueError("target assessment must agree with tree evidence")
        if (
            report.target_covering_node_id is not None
            and report.target_covering_node_id not in covering
        ):
            raise ValueError("target covering node does not cover the target")
    for acceleration in report.accelerations:
        if acceleration.transition_path != _path(
            nodes, acceleration.ancestor_id, acceleration.node_id
        ):
            raise ValueError("acceleration path must match its tree branch")
        raw_map = dict(acceleration.successor.tokens)
        if not set(raw_map) <= set(places):
            raise ValueError("acceleration successor references unknown place")
        raw = tuple(raw_map.get(p, 0) for p in places)
        ancestor = vectors[acceleration.ancestor_id]
        growth = tuple(
            p
            for p, a, b in zip(places, ancestor, raw)
            if a is not None and b is not None and a < b
        )
        if not _leq(ancestor, raw) or acceleration.accelerated_place_ids != growth:
            raise ValueError(
                "acceleration must identify the raw successor's strict growth"
            )
        if any(mappings[acceleration.node_id].get(p, 0) is not None for p in growth):
            raise ValueError(
                "accelerated places must contain omega at the resulting node"
            )
    by_node = {}
    for acceleration in report.accelerations:
        by_node.setdefault(acceleration.node_id, []).append(acceleration)
    for node in nodes[1:]:
        prior_omega = {p for p, n in nodes[node.parent_id].marking.tokens if n is None}
        now_omega = {p for p, n in node.marking.tokens if n is None}
        certificates = by_node.get(node.id, ())
        growth = {p for a in certificates for p in a.accelerated_place_ids}
        if now_omega != prior_omega | growth:
            raise ValueError("omega changes require matching acceleration certificates")
        if certificates:
            raw = certificates[0].successor
            if any(a.successor != raw for a in certificates):
                raise ValueError(
                    "simultaneous accelerations must share one raw successor"
                )
            after = dict(raw.tokens)
            after.update((p, None) for p in growth)
            if OmegaMarking(tuple(after.items())) != node.marking:
                raise ValueError(
                    "node marking must be the simultaneous acceleration result"
                )
    for witness in report.pumping_witnesses:
        if witness.prefix_transition_ids != _path(nodes, 0, witness.ancestor_id):
            raise ValueError("pumping prefix must match the tree path")
        if witness.cycle_transition_ids != _path(
            nodes, witness.ancestor_id, witness.node_id
        ):
            raise ValueError("pumping cycle must match the tree branch")
        if OmegaMarking(witness.before.tokens) != nodes[witness.ancestor_id].marking:
            raise ValueError("pumping start must match its finite ancestor marking")
        if not any(
            a.node_id == witness.node_id
            and a.ancestor_id == witness.ancestor_id
            and a.successor == OmegaMarking(witness.after.tokens)
            and a.accelerated_place_ids == witness.growing_place_ids
            for a in report.accelerations
        ):
            raise ValueError(
                "pumping witness requires a matching acceleration certificate"
            )


def _compute(net, spec):
    places = tuple(p.id for p in net.places)
    transitions = tuple(t.id for t in net.transitions)
    initial = dict(net.initial_marking.tokens)
    vectors = [tuple(initial.get(p, 0) for p in places)]
    incoming, outgoing = {}, {}
    for tid in transitions:
        ins = {a.source: a.weight for a in net.arcs if a.target == tid}
        outs = {a.target: a.weight for a in net.arcs if a.source == tid}
        incoming[tid] = tuple(ins.get(p, 0) for p in places)
        outgoing[tid] = tuple(outs.get(p, 0) for p in places)

    def enabled(vector):
        return tuple(t for t in transitions if _leq(incoming[t], vector))

    nodes = [
        CoverabilityNode(
            0, None, None, _marking(places, vectors[0]), enabled(vectors[0])
        )
    ]
    queue = deque((0,))
    accelerations, witnesses, boundary = [], [], []
    expansions = 0
    while queue:
        source_id = queue.popleft()
        source = nodes[source_id]
        if expansions >= spec.max_expansions:
            queue.appendleft(source_id)
            boundary.append(CoverabilityBoundary(source_id, None, "max_expansions"))
            break
        expansions += 1
        ancestors = []
        ancestor_id = source_id
        while ancestor_id is not None:
            ancestors.append(ancestor_id)
            ancestor_id = nodes[ancestor_id].parent_id
        ancestors.reverse()
        for tid in source.enabled_transition_ids:
            if len(nodes) >= spec.max_nodes:
                queue.appendleft(source_id)
                boundary.append(CoverabilityBoundary(source_id, tid, "max_nodes"))
                break
            raw = tuple(
                None if n is None else n - need + give
                for n, need, give in zip(
                    vectors[source_id], incoming[tid], outgoing[tid]
                )
            )
            vector = list(raw)
            node_id = len(nodes)
            duplicate = next((a for a in ancestors if vectors[a] == raw), None)
            if duplicate is None:
                for ancestor_id in ancestors:
                    before = vectors[ancestor_id]
                    if not _leq(before, raw):
                        continue
                    growth = tuple(
                        index
                        for index, (a, b) in enumerate(zip(before, raw))
                        if a is not None and b is not None and a < b
                    )
                    if not growth:
                        continue
                    growing_places = tuple(places[index] for index in growth)
                    path = _path(nodes, ancestor_id, source_id) + (tid,)
                    accelerations.append(
                        CoverabilityAcceleration(
                            node_id,
                            ancestor_id,
                            _marking(places, raw),
                            growing_places,
                            path,
                        )
                    )
                    if None not in raw:
                        witnesses.append(
                            PumpingWitness(
                                ancestor_id,
                                node_id,
                                _path(nodes, 0, ancestor_id),
                                path,
                                Marking(_marking(places, before).tokens),
                                Marking(_marking(places, raw).tokens),
                                growing_places,
                            )
                        )
                    for index in growth:
                        vector[index] = None
            vector = tuple(vector)
            # Equality of accelerated labels is also a valid ancestor cutoff.
            duplicate = next((a for a in ancestors if vectors[a] == vector), None)
            nodes.append(
                CoverabilityNode(
                    node_id,
                    source_id,
                    tid,
                    _marking(places, vector),
                    enabled(vector),
                    duplicate,
                )
            )
            vectors.append(vector)
            if duplicate is None:
                queue.append(node_id)
        if boundary:
            break
        nodes[source_id] = replace(source, expanded=True)

    complete = not boundary
    unbounded = any(None in vector for vector in vectors)
    bounded = False if unbounded else True if complete else None
    bounds = []
    for index, place in enumerate(places):
        omega = next((n for n, v in enumerate(vectors) if v[index] is None), None)
        maximum = max(v[index] for v in vectors if v[index] is not None)
        bounds.append(
            PlaceBound(
                place,
                False if omega is not None else True if complete else None,
                maximum if complete and omega is None else None,
                maximum,
                omega,
            )
        )
    observed = {tid for node in nodes for tid in node.enabled_transition_ids}
    unseen = tuple(tid for tid in transitions if tid not in observed)
    target_node = None
    if spec.target is not None:
        demands = dict(spec.target.tokens)
        target = tuple(demands.get(p, 0) for p in places)
        target_node = next((i for i, v in enumerate(vectors) if _leq(target, v)), None)
    target_coverable = (
        None
        if spec.target is None
        else True
        if target_node is not None
        else False
        if complete
        else None
    )
    return Coverability(
        model_digest(net),
        places,
        transitions,
        tuple(nodes),
        tuple(accelerations),
        tuple(witnesses),
        tuple(boundary),
        tuple(queue),
        expansions,
        complete,
        bounded,
        tuple(bounds),
        unseen if complete else (),
        unseen if not complete else (),
        spec.target,
        target_coverable,
        target_node,
    )


def coverability(
    net: PetriNet, spec: CoverabilitySpec = CoverabilitySpec()
) -> ComputationResult[Coverability]:
    """Compute a capped Karp--Miller tree and three-valued proof assessments.

    Bounded is True only for a complete omega-free tree, False on a certified
    pumping witness, and None otherwise. A partial result may still prove a
    positive coverability claim or unboundedness. Dead transitions are listed
    only after completion. Transition labels and final-marking acceptance play
    no role in weighted firing; the optional target is a covering demand.
    """
    if type(net) is not PetriNet or any(type(a) is not Arc for a in net.arcs):
        raise TypeError(
            "coverability supports only standard weighted P/T PetriNet; "
            "reset, inhibitor, and extended net/arc types are unsupported"
        )
    if not isinstance(spec, CoverabilitySpec):
        raise TypeError("spec must be CoverabilitySpec")
    if spec.target is not None:
        net.validate_marking(spec.target)
    value = _compute(net, spec)
    issues = tuple(
        ComputeIssue(
            reason,
            "Coverability tree is incomplete; unresolved properties remain unknown.",
        )
        for reason in sorted({b.reason for b in value.boundary})
    )
    return _result(
        "pix.case_centric.coverability",
        None,
        spec,
        ComputeStatus.COMPUTED if value.complete else ComputeStatus.PARTIAL,
        value,
        issues,
        source_digest=value.model_digest,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.coverability": (
        "case-coverability",
        CoverabilitySpec,
        Coverability,
    ),
}

__all__ = (
    "OmegaMarking",
    "CoverabilitySpec",
    "CoverabilityNode",
    "CoverabilityAcceleration",
    "PumpingWitness",
    "CoverabilityBoundary",
    "PlaceBound",
    "Coverability",
    "coverability",
)
