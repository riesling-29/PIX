"""Exact alignment by independent weak components and event allocation.

This PIX profile decomposes the incidence graph into disjoint components. It
does not implement PM4Py's maximal decomposition with shared border transitions.
Connected nets are explicitly unsupported here; no global-search fallback is
named decomposed alignment. Every local problem includes its exact projected
initial/final marking, even when its projected trace is empty.

For a shared activity each event is assigned to one component containing that
activity. Exhaustively minimizing over assignments is exact: every global path
projects to one assignment, and independent local paths can be interleaved in
original event order. Unknown activities incur one global log move. Nonnegative
costs, all allocations exhausted and all local searches completed give the
additive optimality proof. Limits retain bounds and any executable incumbent.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.compute.conformance import _align
from pix.compute.model_semantics import fire, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import AlignmentMove, AlignmentSpec, TraceAlignment
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class DecomposedAlignmentSpec:
    """Local settled-state cap and a per-trace allocation enumeration cap.

    Costs are fixed nonnegative integers inherited from AlignmentSpec. The state
    cap applies to each distinct (component, projected event positions) search;
    repeated subproblems within one trace reuse their evidence. Neither cap
    certifies unreachability. No wall-time or global-memory bound is promised.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    max_allocations: int = 4096
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.alignment, AlignmentSpec):
            raise TypeError("alignment must be AlignmentSpec")
        if type(self.max_allocations) is not int:
            raise TypeError("max_allocations must be an integer")
        if self.max_allocations < 1:
            raise ValueError("max_allocations must be positive")


@dataclass(frozen=True, slots=True)
class DecomposedAlignmentRequest:
    model_digest: str
    parameters: DecomposedAlignmentSpec
    profile: str = "independent_weak_components_event_allocation"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlignmentComponent:
    index: int
    model_digest: str
    model: PetriNet
    visible_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ComponentAlignmentEvidence:
    component_index: int
    model_digest: str
    event_positions: tuple[int, ...]
    alignment: TraceAlignment


@dataclass(frozen=True, slots=True)
class AllocationAlignmentSummary:
    event_owners: tuple[int | None, ...]
    status: Literal["optimal", "search_limit", "unreachable", "invalid_witness"]
    cost: int | None
    lower_bound_cost: int | None
    validation_issue: str | None = None


@dataclass(frozen=True, slots=True)
class DecomposedTraceAlignment:
    object_id: str
    event_ids: tuple[str, ...]
    status: Literal["optimal", "search_limit", "unreachable", "invalid_witness"]
    cost: int | None
    best_known_cost: int | None
    lower_bound_cost: int | None
    moves: tuple[AlignmentMove, ...]
    best_event_owners: tuple[int | None, ...] | None
    component_evidence: tuple[ComponentAlignmentEvidence, ...]
    allocations: tuple[AllocationAlignmentSummary, ...]
    allocation_space_size: int | None
    allocation_space_size_lower_bound: int
    allocations_exhausted: bool
    local_search_count: int
    settled_states: int
    discovered_states: int
    witness_validated: bool


@dataclass(frozen=True, slots=True)
class DecomposedAlignmentSet:
    model_digest: str
    components: tuple[AlignmentComponent, ...]
    traces: tuple[DecomposedTraceAlignment, ...]
    optimal_count: int
    unreachable_count: int
    limited_count: int
    invalid_witness_count: int
    completed_cost_sum: int
    total_cost: int | None
    profile: str = "independent_weak_components_event_allocation"


def decompose_alignment_components(net: PetriNet) -> tuple[AlignmentComponent, ...]:
    """Partition all places/transitions, including isolated nodes, by incidence.

    Components are canonically numbered by their smallest node ID. Weighted
    arcs and token multiplicities are retained. Returning one component does
    not certify useful decomposition; align_decomposed requires at least two.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    adjacent: dict[str, set[str]] = {
        node.id: set() for node in (*net.places, *net.transitions)
    }
    for arc in net.arcs:
        adjacent[arc.source].add(arc.target)
        adjacent[arc.target].add(arc.source)
    remaining = set(adjacent)
    components = []
    while remaining:
        pending = [min(remaining)]
        members = set()
        while pending:
            node = pending.pop()
            if node in members:
                continue
            members.add(node)
            pending.extend(adjacent[node] - members)
        remaining.difference_update(members)
        model = PetriNet(
            tuple(place for place in net.places if place.id in members),
            tuple(t for t in net.transitions if t.id in members),
            tuple(arc for arc in net.arcs if arc.source in members),
            Marking(
                tuple(pair for pair in net.initial_marking.tokens if pair[0] in members)
            ),
            Marking(
                tuple(pair for pair in net.final_marking.tokens if pair[0] in members)
            ),
        )
        components.append(
            AlignmentComponent(
                len(components),
                model_digest(model),
                model,
                tuple(
                    sorted(
                        {
                            t.activity
                            for t in model.transitions
                            if t.activity is not None
                        }
                    )
                ),
            )
        )
    return tuple(components)


def _recompose(
    trace: ObjectTrace,
    net: PetriNet,
    components: tuple[AlignmentComponent, ...],
    owners: tuple[int | None, ...],
    local: tuple[ComponentAlignmentEvidence, ...],
    spec: AlignmentSpec,
) -> tuple[AlignmentMove, ...]:
    """Construct and independently replay a candidate against the original net."""
    cursors = [0] * len(components)
    marking = net.initial_marking
    moves = []
    transitions = {t.id: t.activity for t in net.transitions}
    component_places = [{p.id for p in item.model.places} for item in components]
    component_transitions = [
        {t.id for t in item.model.transitions} for item in components
    ]

    def append(move: AlignmentMove, owner: int | None) -> None:
        nonlocal marking
        before = marking
        if owner is not None:
            projected = tuple(
                pair for pair in before.tokens if pair[0] in component_places[owner]
            )
            if projected != move.before_marking:
                raise ValueError("local before-marking differs from global projection")
        if move.kind == "log":
            if move.transition_id is not None:
                raise ValueError("log move carries a model transition")
            expected_cost = spec.log_move_cost
        else:
            if owner is None or move.transition_id not in component_transitions[owner]:
                raise ValueError("transition does not belong to the assigned component")
            activity = transitions[move.transition_id]
            if activity != move.activity:
                raise ValueError("move activity differs from model transition")
            if move.kind == "silent" and activity is None and move.event_id is None:
                expected_cost = spec.silent_move_cost
            elif (
                move.kind == "model" and activity is not None and move.event_id is None
            ):
                expected_cost = spec.model_move_cost
            elif move.kind == "synchronous" and activity is not None:
                expected_cost = spec.synchronous_move_cost
            else:
                raise ValueError("invalid transition move kind")
            marking = fire(net, marking, move.transition_id)
        if expected_cost != move.cost:
            raise ValueError("move cost differs from the requested cost profile")
        if owner is not None:
            projected = tuple(
                pair for pair in marking.tokens if pair[0] in component_places[owner]
            )
            if projected != move.after_marking:
                raise ValueError("local after-marking differs from global projection")
        moves.append(
            AlignmentMove(
                move.kind,
                move.event_id,
                move.transition_id,
                move.activity,
                move.cost,
                before.tokens,
                marking.tokens,
            )
        )

    for event, owner in zip(trace.events, owners):
        if owner is None:
            append(
                AlignmentMove(
                    "log",
                    event.event_id,
                    None,
                    event.activity,
                    spec.log_move_cost,
                    (),
                    (),
                ),
                None,
            )
            continue
        path = local[owner].alignment.moves
        while cursors[owner] < len(path) and path[cursors[owner]].kind in (
            "model",
            "silent",
        ):
            append(path[cursors[owner]], owner)
            cursors[owner] += 1
        if cursors[owner] == len(path):
            raise ValueError("local alignment fails to consume its assigned event")
        move = path[cursors[owner]]
        if move.kind not in ("log", "synchronous") or (
            move.event_id != event.event_id or move.activity != event.activity
        ):
            raise ValueError("local alignment consumes a different event")
        append(move, owner)
        cursors[owner] += 1
    for owner, evidence in enumerate(local):
        for move in evidence.alignment.moves[cursors[owner] :]:
            if move.kind not in ("model", "silent"):
                raise ValueError("unconsumed local log event")
            append(move, owner)
    if marking != net.final_marking:
        raise ValueError("recomposed witness does not reach the exact final marking")
    expected = (
        sum(item.alignment.cost for item in local)
        + owners.count(None) * spec.log_move_cost
    )
    if sum(move.cost for move in moves) != expected:
        raise ValueError("recomposed witness cost differs from local cost sum")
    return tuple(moves)


def _align_decomposed(
    trace: ObjectTrace,
    net: PetriNet,
    components: tuple[AlignmentComponent, ...],
    spec: DecomposedAlignmentSpec,
) -> DecomposedTraceAlignment:
    by_label: dict[str, tuple[int, ...]] = {}
    for component in components:
        for label in component.visible_labels:
            by_label[label] = (*by_label.get(label, ()), component.index)
    choices = tuple(by_label.get(event.activity, (None,)) for event in trace.events)
    # Cap the integer as well as enumeration: extremely long ambiguous traces
    # must not create an enormous decimal integer in result serialization.
    space_bound = 1
    for choice in choices:
        space_bound = min(space_bound * len(choice), spec.max_allocations + 1)
    space_size = space_bound if space_bound <= spec.max_allocations else None
    unknown_cost = (
        sum(choice == (None,) for choice in choices) * spec.alignment.log_move_cost
    )
    cache: dict[tuple[int, tuple[int, ...]], TraceAlignment] = {}
    summaries = []
    best_cost = None
    best_moves = ()
    best_owners = None
    best_local = ()
    unreachable = False
    for _, owners in zip(range(spec.max_allocations), product(*choices)):
        local = []
        for component in components:
            positions = tuple(
                i for i, owner in enumerate(owners) if owner == component.index
            )
            key = component.index, positions
            if key not in cache:
                projected = ObjectTrace(
                    trace.object_id,
                    trace.object_type,
                    tuple(trace.events[i] for i in positions),
                )
                cache[key] = _align(projected, component.model, spec.alignment)
            local.append(
                ComponentAlignmentEvidence(
                    component.index, component.model_digest, positions, cache[key]
                )
            )
        local = tuple(local)
        if any(item.alignment.status == "unreachable" for item in local):
            # With unrestricted finite-cost log/model moves, an accepting
            # alignment exists iff the local final marking is reachable.
            # Thus one exhausted unreachable component disproves every allocation.
            if best_cost is not None:
                raise RuntimeError(
                    "unreachable component contradicts an accepting witness"
                )
            summaries.append(
                AllocationAlignmentSummary(owners, "unreachable", None, None)
            )
            best_local = local
            unreachable = True
            break
        lower = unknown_cost + sum(item.alignment.lower_bound_cost for item in local)
        if any(item.alignment.status == "search_limit" for item in local):
            summaries.append(
                AllocationAlignmentSummary(owners, "search_limit", None, lower)
            )
            if not best_local:
                best_local = local
            continue
        cost = unknown_cost + sum(item.alignment.cost for item in local)
        try:
            moves = _recompose(trace, net, components, owners, local, spec.alignment)
        except ValueError as error:
            # A bad witness cannot become an optimal result or trusted local
            # lower bound. The only retained bound is unknown-label log cost.
            summaries.append(
                AllocationAlignmentSummary(
                    owners, "invalid_witness", None, unknown_cost, str(error)
                )
            )
            if not best_local:
                best_local = local
            continue
        summaries.append(AllocationAlignmentSummary(owners, "optimal", cost, cost))
        if best_cost is None or cost < best_cost:
            best_cost, best_moves, best_owners, best_local = cost, moves, owners, local
    exhausted = space_size is not None and len(summaries) == space_size
    invalid_witness = any(item.status == "invalid_witness" for item in summaries)
    if unreachable:
        status, lower = "unreachable", None
    else:
        bounds = [item.lower_bound_cost for item in summaries]
        if not exhausted:
            bounds.append(unknown_cost)
        lower = min(bounds)
        status = (
            "invalid_witness"
            if invalid_witness
            else "optimal"
            if exhausted and all(item.status == "optimal" for item in summaries)
            else "search_limit"
        )
    return DecomposedTraceAlignment(
        trace.object_id,
        tuple(event.event_id for event in trace.events),
        status,
        best_cost if status == "optimal" else None,
        best_cost,
        lower,
        best_moves,
        best_owners,
        best_local,
        tuple(summaries),
        space_size,
        space_bound,
        exhausted,
        len(cache),
        sum(item.settled_states for item in cache.values()),
        sum(item.discovered_states for item in cache.values()),
        best_cost is not None,
    )


def align_decomposed(
    log: CaseInput,
    net: PetriNet,
    spec: DecomposedAlignmentSpec = DecomposedAlignmentSpec(),
) -> ComputationResult[DecomposedAlignmentSet]:
    """Align disjoint weak components, then recompose an executable witness.

    For two or more components, duplicate labels across components are handled
    by bounded exact event-allocation enumeration, never duplicate log charges.
    At most one best witness is retained; all evaluated allocation costs/bounds
    are recorded. allocation_space_size is None when larger than the cap, with
    the cap+1 lower bound recorded. A limited search exposes best_known_cost,
    while cost and whole-log total_cost remain None until optimality is proved.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    if not isinstance(spec, DecomposedAlignmentSpec):
        raise TypeError("spec must be DecomposedAlignmentSpec")
    source = as_case_traces(log)
    request = DecomposedAlignmentRequest(model_digest(net), spec)
    parents = (source.computation_id,) if source.computation_id is not None else ()

    def result(status, value, issues=()):
        return _result(
            "pix.case_centric.decomposed_alignment",
            None,
            request,
            status,
            value,
            source.issues + issues,
            source_digest=source.source_digest,
            parent_computation_ids=parents,
        )

    if source.status is not ComputeStatus.COMPUTED or not isinstance(
        source.value, TraceSet
    ):
        return result(
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "trace_result_unavailable", "A completed TraceSet is required"
                ),
            ),
        )
    components = decompose_alignment_components(net)
    if len(components) < 2:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "no_nontrivial_decomposition",
                    "This profile requires at least two weak incidence components; maximal border decomposition is not implemented",
                ),
            ),
        )
    traces = tuple(
        _align_decomposed(trace, net, components, spec) for trace in source.value.traces
    )
    optimal = sum(item.status == "optimal" for item in traces)
    unreachable = sum(item.status == "unreachable" for item in traces)
    limited = sum(item.status == "search_limit" for item in traces)
    invalid = sum(item.status == "invalid_witness" for item in traces)
    completed_cost = sum(item.cost for item in traces if item.cost is not None)
    value = DecomposedAlignmentSet(
        request.model_digest,
        components,
        traces,
        optimal,
        unreachable,
        limited,
        invalid,
        completed_cost,
        completed_cost if optimal == len(traces) else None,
    )
    issues = tuple(
        ComputeIssue(
            "decomposed_alignment_invalid_witness"
            if item.status == "invalid_witness"
            else "decomposed_alignment_search_limit",
            "Recomposed witness failed validation"
            if item.status == "invalid_witness"
            else "Allocation or local settled-state limit reached; optimality is unknown",
            ("case", item.object_id),
        )
        for item in traces
        if item.status in ("search_limit", "invalid_witness")
    )
    return result(
        ComputeStatus.PARTIAL if limited or invalid else ComputeStatus.COMPUTED,
        value,
        issues,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.decomposed_alignment": (
        "case-decomposed-alignment",
        DecomposedAlignmentRequest,
        DecomposedAlignmentSet,
    ),
}

__all__ = (
    "DecomposedAlignmentSpec",
    "DecomposedAlignmentRequest",
    "AlignmentComponent",
    "ComponentAlignmentEvidence",
    "AllocationAlignmentSummary",
    "DecomposedTraceAlignment",
    "DecomposedAlignmentSet",
    "decompose_alignment_components",
    "align_decomposed",
)
