"""Convert an observed full-prefix acceptor to an accepting Petri net.

PIX prefix discovery represents a trie as ``TransitionSystem``. This converter
validates full-prefix contexts, the unique parent of every non-root state and
frequency conservation. It does not interpret a general/windowed transition
system as a trie. Only states with positive ``final_count`` permit termination,
including the root for observed empty traces. Frequencies remain evidence,
never arc weights or probabilities; source state and edge identities survive
in explicit mappings. Original event IDs are not present in this input model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import ClassVar

from pix.case_centric.discovery import StateEdge, StateNode, TransitionSystem
from pix.compute._common import _derived_result
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _immutable,
)

OPERATOR_ID = "pix.case_centric.trie_to_petri_net"
PROFILE = "pix.prefix_trie.accepting_state_machine.v1"


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    value.encode("utf-8")


@dataclass(frozen=True, slots=True)
class TrieConversionSpec:
    max_net_nodes: int = 200_000
    max_net_arcs: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.TrieConversionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.max_net_nodes, "max_net_nodes", 1)
        _integer(self.max_net_arcs, "max_net_arcs", 1)


@dataclass(frozen=True, slots=True)
class TrieConversionRequest:
    model_digest: str | None
    parameters: TrieConversionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.TrieConversionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.model_digest is not None:
            _text(self.model_digest, "model_digest")
        if not isinstance(self.parameters, TrieConversionSpec):
            raise TypeError("parameters must be TrieConversionSpec")


@dataclass(frozen=True, slots=True)
class TrieStateMapping:
    state_id: str
    context: tuple[str, ...]
    place_id: str
    visits: int
    initial_count: int
    final_count: int

    def __post_init__(self) -> None:
        _text(self.state_id, "state_id")
        _text(self.place_id, "place_id")
        if not isinstance(self.context, tuple):
            raise TypeError("context must be a tuple")
        for activity in self.context:
            _text(activity, "context activity")
        _integer(self.visits, "visits", 1)
        _integer(self.initial_count, "initial_count")
        _integer(self.final_count, "final_count")


@dataclass(frozen=True, slots=True)
class TrieEdgeMapping:
    source_state_id: str
    target_state_id: str
    activity: str
    occurrence_count: int
    transition_id: str

    def __post_init__(self) -> None:
        for name in ("source_state_id", "target_state_id", "activity", "transition_id"):
            _text(getattr(self, name), name)
        _integer(self.occurrence_count, "occurrence_count", 1)


@dataclass(frozen=True, slots=True)
class TrieTerminalMapping:
    state_id: str
    transition_id: str
    final_count: int

    def __post_init__(self) -> None:
        _text(self.state_id, "state_id")
        _text(self.transition_id, "transition_id")
        _integer(self.final_count, "final_count", 1)


@dataclass(frozen=True, slots=True)
class TrieConversion:
    model: PetriNet
    source_model_digest: str
    state_mappings: tuple[TrieStateMapping, ...]
    edge_mappings: tuple[TrieEdgeMapping, ...]
    terminal_mappings: tuple[TrieTerminalMapping, ...]
    trace_count: int
    allows_empty_trace: bool
    profile: str = PROFILE

    @property
    def model_digest(self) -> str:
        """Source-model identity, also checked by the shared result envelope."""
        return self.source_model_digest

    def __post_init__(self) -> None:
        if not isinstance(self.model, PetriNet):
            raise TypeError("model must be PetriNet")
        _text(self.source_model_digest, "source_model_digest")
        if self.profile != PROFILE:
            raise ValueError("unknown trie conversion profile")
        _integer(self.trace_count, "trace_count", 1)
        if type(self.allows_empty_trace) is not bool:
            raise TypeError("allows_empty_trace must be bool")
        for name, kind in (
            ("state_mappings", TrieStateMapping),
            ("edge_mappings", TrieEdgeMapping),
            ("terminal_mappings", TrieTerminalMapping),
        ):
            rows = getattr(self, name)
            if not isinstance(rows, tuple) or not all(
                isinstance(r, kind) for r in rows
            ):
                raise TypeError(f"{name} must be a tuple of {kind.__name__}")
        graph = TransitionSystem(
            tuple(
                StateNode(
                    r.state_id, r.context, r.visits, r.initial_count, r.final_count
                )
                for r in self.state_mappings
            ),
            tuple(
                StateEdge(
                    r.source_state_id, r.target_state_id, r.activity, r.occurrence_count
                )
                for r in self.edge_mappings
            ),
            self.trace_count,
            True,
        )
        root = _validate(graph)
        if self.source_model_digest != _trie_digest(graph):
            raise ValueError("source model digest disagrees with trie evidence")
        by_state = {r.state_id: r for r in self.state_mappings}
        places = {r.place_id for r in self.state_mappings}
        if len(places) != len(by_state):
            raise ValueError("state place mappings must be unique")
        extra = {p.id for p in self.model.places} - places
        if len(extra) != 1 or len(self.model.places) != len(places) + 1:
            raise ValueError("net must have one place per state and one sink")
        sink = next(iter(extra))
        expected_transitions = [
            (r.transition_id, r.activity) for r in self.edge_mappings
        ]
        expected_arcs = []
        for row in self.edge_mappings:
            expected_arcs.extend(
                (
                    Arc(by_state[row.source_state_id].place_id, row.transition_id),
                    Arc(row.transition_id, by_state[row.target_state_id].place_id),
                )
            )
        terminals = {r.state_id: r for r in self.terminal_mappings}
        if len(terminals) != len(self.terminal_mappings) or set(terminals) != {
            r.state_id for r in self.state_mappings if r.final_count > 0
        }:
            raise ValueError(
                "terminal mappings must match exactly the accepting states"
            )
        for row in self.terminal_mappings:
            if row.final_count != by_state[row.state_id].final_count:
                raise ValueError("terminal frequency differs from state evidence")
            expected_transitions.append((row.transition_id, None))
            expected_arcs.extend(
                (
                    Arc(by_state[row.state_id].place_id, row.transition_id),
                    Arc(row.transition_id, sink),
                )
            )
        if len({t for t, _ in expected_transitions}) != len(expected_transitions):
            raise ValueError("edge and terminal transition mappings must be unique")
        if {(t.id, t.activity) for t in self.model.transitions} != set(
            expected_transitions
        ):
            raise ValueError("net transitions differ from mappings")
        if self.model.arcs != tuple(sorted(expected_arcs)):
            raise ValueError("net arcs differ from mapped unit-weight routes")
        if self.model.initial_marking != Marking(((by_state[root.id].place_id, 1),)):
            raise ValueError("initial marking must contain one token at the root")
        if self.model.final_marking != Marking(((sink, 1),)):
            raise ValueError("final marking must contain one token at the sink")
        if self.allows_empty_trace != (root.final_count > 0):
            raise ValueError("epsilon acceptance must match root final_count")


class _Unavailable(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _validate(graph: TransitionSystem) -> StateNode:
    """Full-prefix identities imply acyclicity and reachability without search."""
    if type(graph.complete) is not bool:
        raise ValueError("complete must be bool")
    if not graph.complete:
        raise _Unavailable("trie_incomplete", "A complete prefix trie is required")
    _integer(graph.trace_count, "trace_count")
    if not isinstance(graph.states, tuple) or not all(
        isinstance(s, StateNode) for s in graph.states
    ):
        raise ValueError("states must be a tuple of StateNode")
    if not isinstance(graph.transitions, tuple) or not all(
        isinstance(e, StateEdge) for e in graph.transitions
    ):
        raise ValueError("transitions must be a tuple of StateEdge")
    if not graph.trace_count and not graph.states and not graph.transitions:
        raise _Unavailable(
            "trie_empty_log", "No observed traces; an empty log does not imply epsilon"
        )
    states, contexts = {}, set()
    for state in graph.states:
        # Reuse the evidence validator without synthesizing any missing counts.
        TrieStateMapping(
            state.id,
            state.context,
            "validation",
            state.visits,
            state.initial_count,
            state.final_count,
        )
        if state.id in states or state.context in contexts:
            raise ValueError("state IDs and prefix contexts must be unique")
        states[state.id] = state
        contexts.add(state.context)
        if state.visits > graph.trace_count:
            raise ValueError("state visits exceed trace_count")
    roots = [s for s in graph.states if not s.context]
    if len(roots) != 1:
        raise ValueError("exactly one empty-context root is required")
    root = roots[0]
    incoming, outgoing = {}, {s.id: 0 for s in graph.states}
    for edge in graph.transitions:
        TrieEdgeMapping(
            edge.source, edge.target, edge.activity, edge.occurrence_count, "validation"
        )
        if edge.source not in states or edge.target not in states:
            raise ValueError("edge references an unknown state")
        before, after = states[edge.source], states[edge.target]
        if after.context != (*before.context, edge.activity):
            raise ValueError("edge must extend its full prefix by exactly its activity")
        if edge.target in incoming:
            raise ValueError("every non-root state must have exactly one incoming edge")
        incoming[edge.target] = edge.occurrence_count
        outgoing[edge.source] += edge.occurrence_count
    for state in graph.states:
        expected_initial = graph.trace_count if state is root else 0
        if state.initial_count != expected_initial:
            raise ValueError(
                "only the root may have initial counts, equal to trace_count"
            )
        if state.visits != incoming.get(state.id, 0) + state.initial_count:
            raise ValueError(
                "incoming frequency and initial counts must equal state visits"
            )
        if state.visits != outgoing[state.id] + state.final_count:
            raise ValueError(
                "outgoing frequency and final counts must equal state visits"
            )
    if sum(s.final_count for s in graph.states) != graph.trace_count:
        raise ValueError("terminal frequencies must sum to trace_count")
    return root


def _trie_digest(graph: TransitionSystem) -> str:
    """Use the existing model artifact identity, preserving source row order."""
    from pix.models import _model_digest

    return _model_digest(graph, asdict(graph))


def trie_to_petri_net(
    trie: TransitionSystem | ComputationResult,
    spec: TrieConversionSpec = TrieConversionSpec(),
) -> ComputationResult[TrieConversion]:
    """Accept exactly the observed finite language of a complete prefix trie.

    A complete general transition-system result is accepted only if its model
    satisfies the same full-prefix/count contract. Incomplete inputs and output
    budgets yield no net, so a truncated language cannot masquerade as complete.
    """
    if not isinstance(spec, TrieConversionSpec):
        raise TypeError("spec must be TrieConversionSpec")
    parent = trie if isinstance(trie, ComputationResult) else None
    if parent is None and not isinstance(trie, TransitionSystem):
        raise TypeError("trie must be TransitionSystem or ComputationResult")
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
            TrieConversionRequest(digest, spec),
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
                        "trie_input_unavailable",
                        "A complete computed prefix-trie result is required",
                    ),
                ),
            )
        trie = parent.value
    if not isinstance(trie, TransitionSystem):
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_trie", "Result payload must be a prefix TransitionSystem"
                ),
            ),
        )
    try:
        if not _immutable(trie):
            raise ValueError("trie must contain immutable finite fields")
        root = _validate(trie)
        digest = _trie_digest(trie)
        if parent is None:
            source = digest
    except _Unavailable as exc:
        return result(
            ComputeStatus.UNAVAILABLE, issues=(ComputeIssue(exc.code, str(exc)),)
        )
    except (TypeError, ValueError, UnicodeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_trie", str(exc)),),
        )

    terminal_count = sum(s.final_count > 0 for s in trie.states)
    transition_count = len(trie.transitions) + terminal_count
    if (
        len(trie.states) + 1 + transition_count > spec.max_net_nodes
        or 2 * transition_count > spec.max_net_arcs
    ):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "trie_conversion_limit",
                    "Complete construction exceeds the node or arc budget; no truncated net was returned",
                ),
            ),
        )
    states, edges = trie.states, trie.transitions
    state_number = {
        s.id: i for i, s in enumerate(sorted(states, key=lambda s: (s.context, s.id)))
    }
    edge_number = {
        (e.source, e.target, e.activity): i
        for i, e in enumerate(
            sorted(edges, key=lambda e: (e.source, e.target, e.activity))
        )
    }
    state_rows = tuple(
        TrieStateMapping(
            s.id,
            s.context,
            f"trie:p:state:{state_number[s.id]}",
            s.visits,
            s.initial_count,
            s.final_count,
        )
        for s in states
    )
    by_state = {r.state_id: r.place_id for r in state_rows}
    edge_rows = tuple(
        TrieEdgeMapping(
            e.source,
            e.target,
            e.activity,
            e.occurrence_count,
            f"trie:t:edge:{edge_number[e.source, e.target, e.activity]}",
        )
        for e in edges
    )
    terminal_rows = tuple(
        TrieTerminalMapping(
            s.id, f"trie:t:terminal:{state_number[s.id]}", s.final_count
        )
        for s in states
        if s.final_count > 0
    )
    sink = "trie:p:sink"
    transitions, arcs = [], []
    for row in edge_rows:
        transitions.append(Transition(row.transition_id, row.activity))
        arcs.extend(
            (
                Arc(by_state[row.source_state_id], row.transition_id),
                Arc(row.transition_id, by_state[row.target_state_id]),
            )
        )
    for row in terminal_rows:
        transitions.append(Transition(row.transition_id))
        arcs.extend(
            (
                Arc(by_state[row.state_id], row.transition_id),
                Arc(row.transition_id, sink),
            )
        )
    model = PetriNet(
        tuple(Place(p) for p in (*by_state.values(), sink)),
        tuple(transitions),
        tuple(arcs),
        Marking(((by_state[root.id], 1),)),
        Marking(((sink, 1),)),
    )
    return result(
        ComputeStatus.COMPUTED,
        TrieConversion(
            model,
            digest,
            state_rows,
            edge_rows,
            terminal_rows,
            trie.trace_count,
            root.final_count > 0,
        ),
        (
            ComputeIssue(
                "trie_observed_language",
                "The net preserves the finite observed prefix-trie language; frequencies remain evidence, not probabilities or token multiplicities.",
            ),
        ),
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("trie_conversion", TrieConversionRequest, TrieConversion)
}

__all__ = (
    "TrieConversionSpec",
    "TrieConversionRequest",
    "TrieStateMapping",
    "TrieEdgeMapping",
    "TrieTerminalMapping",
    "TrieConversion",
    "trie_to_petri_net",
)
