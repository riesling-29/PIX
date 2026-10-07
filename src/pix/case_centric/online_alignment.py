"""Native incremental proxy-trie alignments with look-ahead and state decay.

This is a PIX IWS mathematical profile. A finite set of executable accepting
transition paths supplies the proxy. Each event advances/prunes existing states;
no trace-prefix batch alignment is rerun. Every retained state is an executable
alignment witness, but proxy coverage, look-ahead, decay and beam limits prevent
a general optimality claim. Open-prefix cost is not a bound for final alignment.
"""

from __future__ import annotations

from copy import copy
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from math import isfinite
from random import Random
from typing import ClassVar

from pix.case_centric.streaming import (
    CaseStream,
    StreamEvent,
    StreamingCheckpoint,
    StreamingSnapshot,
    StreamingSpec,
    StreamReceipt,
    _digest,
    _validate_checkpoint,
)
from pix.compute._common import _derived_result
from pix.compute.model_semantics import (
    enabled_transitions,
    fire,
    is_enabled,
    model_digest,
)
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)


def _integer(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


@dataclass(frozen=True, slots=True)
class OnlineAlignmentSpec:
    model: PetriNet
    ingestion: StreamingSpec
    proxy_transition_sequences: tuple[tuple[str, ...], ...] | None = None
    proxy_max_traces: int = 100
    proxy_max_steps: int = 100
    proxy_attempts: int = 1000
    random_seed: int = 0
    max_proxy_nodes: int = 10000
    lookahead: int = 3
    decay_time: float = 10.0
    discount_factor: float = 0.9
    max_states_per_case: int = 20
    max_expansions_per_event: int = 10000
    witness_history_limit: int = 200
    log_move_cost: int = 1
    model_move_cost: int = 1
    silent_move_cost: int = 0
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.model, PetriNet) or not isinstance(
            self.ingestion, StreamingSpec
        ):
            raise TypeError("model and ingestion must be PetriNet and StreamingSpec")
        if (
            self.ingestion.replay_model is not None
            or self.ingestion.declare
            or self.ingestion.temporal
            or self.ingestion.footprints is not None
        ):
            raise ValueError(
                "online alignment ingestion only configures identity, ordering and capacity"
            )
        if self.proxy_transition_sequences is not None:
            if (
                not isinstance(self.proxy_transition_sequences, tuple)
                or not self.proxy_transition_sequences
                or any(
                    not isinstance(p, tuple)
                    or any(not isinstance(t, str) or not t for t in p)
                    for p in self.proxy_transition_sequences
                )
            ):
                raise ValueError(
                    "explicit proxy must contain transition-ID tuples; ((),) is the empty accepting path"
                )
        for name in (
            "proxy_max_traces",
            "proxy_max_steps",
            "proxy_attempts",
            "max_proxy_nodes",
            "lookahead",
            "max_states_per_case",
            "max_expansions_per_event",
            "witness_history_limit",
            "log_move_cost",
            "model_move_cost",
        ):
            _integer(getattr(self, name), name)
        _integer(self.random_seed, "random_seed", 0)
        _integer(self.silent_move_cost, "silent_move_cost", 0)
        for name in ("decay_time", "discount_factor"):
            value = getattr(self, name)
            if type(value) not in (int, float) or not isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
            object.__setattr__(self, name, float(value))
        if self.discount_factor > 1:
            raise ValueError("discount_factor must not exceed one")


@dataclass(frozen=True, slots=True)
class OnlineAlignmentProxy:
    transition_sequences: tuple[tuple[str, ...], ...]
    origin: str
    attempted_walks: int
    truncated_walks: int
    excluded_paths: int
    trie_nodes: int
    model_language_complete: bool = False


@dataclass(frozen=True, slots=True)
class OnlineAlignmentMove:
    kind: str
    transition_id: str | None
    activity: str | None
    event_id: str | None
    sequence: int | None
    cost: int
    timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class OnlineAlignmentState:
    node_id: int
    marking: Marking
    cost: int
    decay: float
    deviation_moves: int
    steps: tuple[OnlineAlignmentMove, ...]
    witness_initial_marking: Marking
    omitted_steps: int = 0
    omitted_cost: int = 0
    omitted_log_events: int = 0
    omitted_witness_digest: str = "pix.online-alignment.empty-witness.v1"


@dataclass(frozen=True, slots=True)
class OnlineAlignmentCase:
    case_id: str
    event_count: int
    closed: bool
    states: tuple[OnlineAlignmentState, ...]
    reported_cost: int
    unavoidable_log_cost: int
    bound_scope: str
    final_cost_unresolved: bool
    generated_states: int = 0
    expired_states: int = 0
    deduplicated_states: int = 0
    beam_pruned_states: int = 0
    fallback_resets: int = 0
    expansion_limited_events: int = 0


@dataclass(frozen=True, slots=True)
class OnlineAlignmentSnapshot:
    proxy: OnlineAlignmentProxy
    ingestion_state: StreamingSnapshot
    cases: tuple[OnlineAlignmentCase, ...]
    profile: str = "pix.proxy-trie-iws.v1"


@dataclass(frozen=True, slots=True)
class OnlineAlignmentCheckpoint:
    snapshot: OnlineAlignmentSnapshot
    state_digest: str


@dataclass(frozen=True, slots=True)
class _Node:
    identifier: int
    marking: Marking
    segment: tuple[str, ...]
    children: tuple[int, ...]
    terminal_suffixes: tuple[tuple[str, ...], ...]


def _validate_path(model: PetriNet, path: tuple[str, ...]) -> None:
    current = model.initial_marking
    known = {t.id for t in model.transitions}
    for transition in path:
        if transition not in known or not is_enabled(model, current, transition):
            raise ValueError("proxy path contains an unknown or disabled transition")
        current = fire(model, current, transition)
    if current != model.final_marking:
        raise ValueError("proxy path does not reach the exact final marking")


def _compile_paths(spec: OnlineAlignmentSpec, paths: tuple[tuple[str, ...], ...]):
    """Shared visible prefixes preserve complete transition segments, including tau."""
    labels = {t.id: t.activity for t in spec.model.transitions}
    records = [
        {
            "marking": spec.model.initial_marking,
            "segment": (),
            "children": {},
            "final": set(),
        }
    ]
    accepted, excluded = [], 0
    for path in paths:
        _validate_path(spec.model, path)
        segments, segment = [], ()
        for transition in path:
            segment += (transition,)
            if labels[transition] is not None:
                segments.append(segment)
                segment = ()
        trailing = segment
        cursor, required, missing = 0, 0, False
        for edge in segments:
            if not missing and edge in records[cursor]["children"]:
                cursor = records[cursor]["children"][edge]
            else:
                missing = True
                required += 1
        if len(records) + required > spec.max_proxy_nodes:
            excluded += 1
            continue
        cursor = 0
        for edge in segments:
            children = records[cursor]["children"]
            if edge not in children:
                marking = records[cursor]["marking"]
                for transition in edge:
                    marking = fire(spec.model, marking, transition)
                children[edge] = len(records)
                records.append(
                    {
                        "marking": marking,
                        "segment": edge,
                        "children": {},
                        "final": set(),
                    }
                )
            cursor = children[edge]
        records[cursor]["final"].add(trailing)
        accepted.append(path)
    nodes = tuple(
        _Node(
            i,
            record["marking"],
            record["segment"],
            tuple(v for _, v in sorted(record["children"].items())),
            tuple(sorted(record["final"])),
        )
        for i, record in enumerate(records)
    )
    return tuple(accepted), nodes, excluded


def build_online_alignment_proxy(
    spec: OnlineAlignmentSpec,
) -> ComputationResult[OnlineAlignmentProxy]:
    """Validate supplied paths or sample bounded seeded accepting model walks.

    No accepted path within the limits is unavailability, not an unsoundness or
    unreachability proof. Complete language coverage is never inferred by sampling.
    """
    if not isinstance(spec, OnlineAlignmentSpec):
        raise TypeError("spec must be OnlineAlignmentSpec")
    paths, attempted, truncated = [], 0, 0
    if spec.proxy_transition_sequences is not None:
        for path in spec.proxy_transition_sequences:
            if len(path) > spec.proxy_max_steps:
                raise ValueError("explicit proxy path exceeds proxy_max_steps")
            _validate_path(spec.model, path)
        paths = list(dict.fromkeys(spec.proxy_transition_sequences))
        supplied_excluded = max(0, len(paths) - spec.proxy_max_traces)
        paths = paths[: spec.proxy_max_traces]
        origin = "explicit_accepting_transition_paths"
    else:
        supplied_excluded, origin = 0, "seeded_bounded_accepting_walks"
        rng = Random(spec.random_seed)
        seen = set()
        for _ in range(spec.proxy_attempts):
            attempted += 1
            marking, path = spec.model.initial_marking, ()
            for _step in range(spec.proxy_max_steps):
                if marking == spec.model.final_marking:
                    break
                choices = enabled_transitions(spec.model, marking)
                if not choices:
                    break
                transition = choices[rng.randrange(len(choices))]
                marking = fire(spec.model, marking, transition)
                path += (transition,)
            if marking != spec.model.final_marking:
                truncated += 1
                continue
            if path not in seen:
                seen.add(path)
                paths.append(path)
            if len(paths) >= spec.proxy_max_traces:
                break
    accepted, nodes, excluded = _compile_paths(spec, tuple(paths))
    source = model_digest(spec.model)
    if not accepted:
        return _derived_result(
            "pix.case_centric.online_alignment.proxy",
            source,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "proxy_unavailable",
                    "No accepting proxy path retained within walk/trace/node limits; model reachability remains unknown",
                ),
            ),
        )
    proxy = OnlineAlignmentProxy(
        accepted, origin, attempted, truncated, excluded + supplied_excluded, len(nodes)
    )
    issues = [
        ComputeIssue(
            "finite_model_proxy",
            "Finite accepting paths do not certify coverage of the entire model language",
        )
    ]
    if proxy.excluded_paths:
        issues.append(
            ComputeIssue(
                "proxy_capacity", "Some paths excluded by explicit trace/node capacity"
            )
        )
    return _derived_result(
        "pix.case_centric.online_alignment.proxy",
        source,
        spec,
        ComputeStatus.PARTIAL,
        proxy,
        tuple(issues),
    )


def _cost(spec: OnlineAlignmentSpec, transition: str) -> int:
    return (
        spec.silent_move_cost
        if next(t.activity for t in spec.model.transitions if t.id == transition)
        is None
        else spec.model_move_cost
    )


def _model_moves(spec, transitions):
    labels = {t.id: t.activity for t in spec.model.transitions}
    return tuple(
        OnlineAlignmentMove(
            "silent" if labels[t] is None else "model",
            t,
            None,
            None,
            None,
            _cost(spec, t),
        )
        for t in transitions
    )


def _suffixes(spec, nodes):
    """Bottom-up finite-trie DP for valid cheapest terminal suffixes."""
    result = {}
    for node in reversed(nodes):
        choices = [
            (sum(_cost(spec, t) for t in path), path, node.identifier)
            for path in node.terminal_suffixes
        ]
        for child_id in node.children:
            suffix_cost, path, terminal_id = result[child_id]
            segment = nodes[child_id].segment
            choices.append(
                (
                    sum(_cost(spec, t) for t in segment) + suffix_cost,
                    segment + path,
                    terminal_id,
                )
            )
        if not choices:
            raise ValueError("proxy contains a node without an accepting continuation")
        result[node.identifier] = min(
            choices, key=lambda c: (c[0], len(c[1]), c[1], c[2])
        )
    return result


def _append(
    spec: OnlineAlignmentSpec,
    old: OnlineAlignmentState,
    moves: tuple[OnlineAlignmentMove, ...],
    node_id: int,
    decay: float,
) -> OnlineAlignmentState:
    marking = old.marking
    for move in moves:
        if move.transition_id is not None:
            marking = fire(spec.model, marking, move.transition_id)
    steps = old.steps + moves
    discard = max(0, len(steps) - spec.witness_history_limit)
    start, history_digest = old.witness_initial_marking, old.omitted_witness_digest
    for move in steps[:discard]:
        if move.transition_id is not None:
            start = fire(spec.model, start, move.transition_id)
        # A frozen move's typed digest plus previous digest yields a stable chain.
        history_digest = (
            "pix.online.witness.v1:sha256:"
            + sha256((history_digest + _digest(move)).encode()).hexdigest()
        )
    return OnlineAlignmentState(
        node_id,
        marking,
        old.cost + sum(m.cost for m in moves),
        decay,
        old.deviation_moves + sum(m.kind in ("log", "model") for m in moves),
        steps[discard:],
        start,
        old.omitted_steps + discard,
        old.omitted_cost + sum(m.cost for m in steps[:discard]),
        old.omitted_log_events + sum(m.event_id is not None for m in steps[:discard]),
        history_digest,
    )


def _rank(state):
    return (
        state.cost,
        -state.decay,
        state.node_id,
        tuple((m.kind, m.transition_id or "", m.event_id or "") for m in state.steps),
    )


class OnlineAlignmentStream:
    """Single-writer IWS monitor with bounded beam, witnesses and case retention."""

    __slots__ = ("_spec", "_proxy", "_nodes", "_suffix", "_protocol", "_cases")

    def __init__(self, spec: OnlineAlignmentSpec):
        proxy_result = build_online_alignment_proxy(spec)
        if proxy_result.value is None:
            raise ValueError(
                "proxy_unavailable: inspect build_online_alignment_proxy result; no reachability verdict is implied"
            )
        self._initialize(spec, proxy_result.value)

    def _initialize(self, spec, proxy):
        if (
            not isinstance(proxy, OnlineAlignmentProxy)
            or not proxy.transition_sequences
            or len(proxy.transition_sequences) > spec.proxy_max_traces
            or any(
                len(path) > spec.proxy_max_steps for path in proxy.transition_sequences
            )
            or len(set(proxy.transition_sequences)) != len(proxy.transition_sequences)
        ):
            raise ValueError(
                "proxy path count/length exceeds configured bounds or duplicates paths"
            )
        if (
            proxy.model_language_complete is not False
            or proxy.origin
            not in (
                "explicit_accepting_transition_paths",
                "seeded_bounded_accepting_walks",
            )
            or any(
                type(getattr(proxy, field)) is not int or getattr(proxy, field) < 0
                for field in (
                    "attempted_walks",
                    "truncated_walks",
                    "excluded_paths",
                    "trie_nodes",
                )
            )
            or proxy.truncated_walks > proxy.attempted_walks
            or proxy.attempted_walks > spec.proxy_attempts
        ):
            raise ValueError("invalid proxy coverage/origin/counters")
        accepted, nodes, excluded = _compile_paths(spec, proxy.transition_sequences)
        if (
            accepted != proxy.transition_sequences
            or excluded
            or len(nodes) != proxy.trie_nodes
        ):
            raise ValueError("proxy node/path state differs from configured bounds")
        self._spec, self._proxy, self._nodes = spec, proxy, nodes
        self._suffix = _suffixes(spec, nodes)
        self._protocol = CaseStream(spec.ingestion)
        self._cases = {}

    @property
    def spec(self) -> OnlineAlignmentSpec:
        return self._spec

    def _initial(self, case_id):
        initial = OnlineAlignmentState(
            0,
            self.spec.model.initial_marking,
            0,
            self.spec.decay_time,
            0,
            (),
            self.spec.model.initial_marking,
        )
        return OnlineAlignmentCase(
            case_id,
            0,
            False,
            (initial,),
            0,
            0,
            "model_prefix_alignment_upper_bound",
            True,
        )

    def _decay(self, remaining, deviations):
        return max(
            0.0,
            min(
                remaining, self.spec.decay_time * self.spec.discount_factor**deviations
            ),
        )

    def _advance(self, case, event):
        generated = []
        labels = {t.id: t.activity for t in self.spec.model.transitions}
        budget, limited = self.spec.max_expansions_per_event, False
        for state in case.states:
            log_move = OnlineAlignmentMove(
                "log",
                None,
                event.activity,
                event.event_id,
                event.sequence,
                self.spec.log_move_cost,
                event.timestamp,
            )
            generated.append(
                _append(
                    self.spec,
                    state,
                    (log_move,),
                    state.node_id,
                    self._decay(state.decay - 1, state.deviation_moves + 1),
                )
            )
            stack = [(state.node_id, ())]
            while stack:
                node_id, path = stack.pop()
                if len(path) >= self.spec.lookahead:
                    continue
                for child_id in reversed(self._nodes[node_id].children):
                    if budget <= 0:
                        limited = True
                        break
                    budget -= 1
                    child = self._nodes[child_id]
                    candidate_path = path + (child_id,)
                    if labels[child.segment[-1]] == event.activity:
                        skipped = tuple(
                            t
                            for n in candidate_path[:-1]
                            for t in self._nodes[n].segment
                        )
                        moves = _model_moves(
                            self.spec, skipped + child.segment[:-1]
                        ) + (
                            OnlineAlignmentMove(
                                "sync",
                                child.segment[-1],
                                event.activity,
                                event.event_id,
                                event.sequence,
                                0,
                                event.timestamp,
                            ),
                        )
                        deviations = state.deviation_moves + sum(
                            m.kind == "model" for m in moves
                        )
                        decay = (
                            self.spec.decay_time
                            if len(candidate_path) == 1
                            else self._decay(state.decay - 1, deviations)
                        )
                        generated.append(
                            _append(self.spec, state, moves, child_id, decay)
                        )
                    stack.append((child_id, candidate_path))
                if limited:
                    break
        alive = sorted((s for s in generated if s.decay > 0), key=_rank)
        unique = {}
        for state in alive:
            unique.setdefault(state.node_id, state)
        survivors = tuple(unique.values())[: self.spec.max_states_per_case]
        fallback = 0
        if not survivors:
            survivors = (replace(min(generated, key=_rank), decay=1.0),)
            fallback = 1
        return replace(
            case,
            event_count=case.event_count + 1,
            states=survivors,
            reported_cost=survivors[0].cost,
            unavoidable_log_cost=case.unavoidable_log_cost
            + (self.spec.log_move_cost if event.activity not in labels.values() else 0),
            generated_states=case.generated_states + len(generated),
            expired_states=case.expired_states + len(generated) - len(alive),
            deduplicated_states=case.deduplicated_states + len(alive) - len(unique),
            beam_pruned_states=case.beam_pruned_states
            + max(0, len(unique) - self.spec.max_states_per_case),
            fallback_resets=case.fallback_resets + fallback,
            expansion_limited_events=case.expansion_limited_events + limited,
        )

    def _close(self, case):
        completed = []
        for state in case.states:
            _, suffix, terminal_id = self._suffix[state.node_id]
            completed.append(
                _append(
                    self.spec,
                    state,
                    _model_moves(self.spec, suffix),
                    terminal_id,
                    state.decay,
                )
            )
        chosen = min(completed, key=_rank)
        if chosen.marking != self.spec.model.final_marking:
            raise ValueError("internal accepting-proxy completion invariant failed")
        return replace(
            case,
            closed=True,
            states=(chosen,),
            reported_cost=chosen.cost,
            bound_scope="accepting_model_alignment_upper_bound",
            final_cost_unresolved=False,
        )

    def ingest(self, event: StreamEvent) -> StreamReceipt:
        # CaseStream holds an immutable spec and frozen snapshot; its ingestion
        # replaces the snapshot rather than mutating it. A shallow transactional
        # clone avoids checkpoint hashing/validation on every normal event.
        candidate_protocol = copy(self._protocol)
        receipt = candidate_protocol.ingest(event)
        if receipt.status == "duplicate":
            return receipt
        cases = dict(self._cases)
        if receipt.evicted_case_id is not None:
            cases.pop(receipt.evicted_case_id, None)
        case = cases.get(event.case_id, self._initial(event.case_id))
        cases[event.case_id] = (
            self._close(case) if event.end else self._advance(case, event)
        )
        self._protocol, self._cases = candidate_protocol, cases
        return receipt

    def close_case(self, case_id: str, event_id: str, sequence: int) -> StreamReceipt:
        return self.ingest(StreamEvent(case_id, event_id, sequence, end=True))

    def _snapshot(self):
        return OnlineAlignmentSnapshot(
            self._proxy,
            self._protocol.snapshot().value,
            tuple(self._cases[k] for k in sorted(self._cases)),
        )

    def _issues(self):
        issues = [
            ComputeIssue(
                "approximate_online_alignment",
                "Finite proxy, look-ahead, decay and beam selection do not establish minimum cost; valid witnesses supply upper bounds only",
            )
        ]
        issues.extend(self._protocol.snapshot().issues)
        if any(not c.closed for c in self._cases.values()):
            issues.append(
                ComputeIssue(
                    "final_cost_unresolved",
                    "Open-case costs bound prefix alignments only; final-marking completion cost has not been included",
                )
            )
        if any(c.expansion_limited_events for c in self._cases.values()):
            issues.append(
                ComputeIssue(
                    "online_expansion_limit",
                    "Some matching descendants were not explored within the event expansion budget",
                )
            )
        if any(s.omitted_steps for c in self._cases.values() for s in c.states):
            issues.append(
                ComputeIssue(
                    "alignment_witness_history_omitted",
                    "Only a bounded alignment suffix is retained, with its starting marking, omitted counts/cost and digest",
                )
            )
        if self._proxy.excluded_paths:
            issues.append(
                ComputeIssue(
                    "proxy_capacity",
                    "Some requested proxy paths were excluded by trace/node bounds",
                )
            )
        return tuple(issues)

    def snapshot(self) -> ComputationResult[OnlineAlignmentSnapshot]:
        value = self._snapshot()
        return _derived_result(
            "pix.case_centric.online_alignment.snapshot",
            value.ingestion_state.prefix_digest,
            self.spec,
            ComputeStatus.PARTIAL,
            value,
            self._issues(),
        )

    def checkpoint(self) -> ComputationResult[OnlineAlignmentCheckpoint]:
        value = self._snapshot()
        return _derived_result(
            "pix.case_centric.online_alignment.checkpoint",
            value.ingestion_state.prefix_digest,
            self.spec,
            ComputeStatus.PARTIAL,
            OnlineAlignmentCheckpoint(value, _digest(value)),
            self._issues(),
        )

    @classmethod
    def resume(cls, checkpoint: ComputationResult[OnlineAlignmentCheckpoint]):
        if (
            not isinstance(checkpoint, ComputationResult)
            or checkpoint.operator_id != "pix.case_centric.online_alignment.checkpoint"
            or not isinstance(checkpoint.spec, OnlineAlignmentSpec)
            or not isinstance(checkpoint.value, OnlineAlignmentCheckpoint)
        ):
            raise TypeError("expected PIX online alignment checkpoint")
        snapshot = checkpoint.value.snapshot
        if (
            checkpoint.operator_version != "1.0.0"
            or checkpoint.source_digest != snapshot.ingestion_state.prefix_digest
            or checkpoint.value.state_digest != _digest(snapshot)
        ):
            raise ValueError("online checkpoint state identity mismatch")
        if checkpoint.computation_id != computation_identity(
            checkpoint.operator_id,
            checkpoint.operator_version,
            checkpoint.source_digest,
            checkpoint.spec,
            checkpoint.parent_computation_ids,
        ):
            raise ValueError("online checkpoint request identity mismatch")
        result = cls.__new__(cls)
        result._initialize(checkpoint.spec, snapshot.proxy)
        _validate_checkpoint(snapshot.ingestion_state, result.spec.ingestion)
        protocol_value = StreamingCheckpoint(
            snapshot.ingestion_state, _digest(snapshot.ingestion_state)
        )
        protocol_checkpoint = _derived_result(
            "pix.case_centric.streaming.checkpoint",
            snapshot.ingestion_state.prefix_digest,
            result.spec.ingestion,
            ComputeStatus.COMPUTED,
            protocol_value,
        )
        result._protocol = CaseStream.resume(protocol_checkpoint)
        _validate_alignment_cases(result.spec, result._nodes, snapshot)
        result._cases = {c.case_id: c for c in snapshot.cases}
        return result


def _validate_alignment_cases(spec, nodes, snapshot):
    def require(condition, message):
        if not condition:
            raise ValueError("invalid online checkpoint: " + message)

    protocol_cases = {c.case_id: c for c in snapshot.ingestion_state.cases}
    require(snapshot.profile == "pix.proxy-trie-iws.v1", "profile")
    require(
        len(snapshot.cases) == len(protocol_cases)
        and {c.case_id for c in snapshot.cases} == set(protocol_cases),
        "case identities",
    )
    labels = {t.id: t.activity for t in spec.model.transitions}
    prefix_paths = {0: ()}
    for node in nodes:
        for child_id in node.children:
            prefix_paths[child_id] = (
                prefix_paths[node.identifier] + nodes[child_id].segment
            )
    for case in snapshot.cases:
        protocol = protocol_cases[case.case_id]
        require(
            case.closed == protocol.closed and case.event_count == protocol.event_count,
            "case event/closure accounting",
        )
        require(
            1 <= len(case.states) <= spec.max_states_per_case
            and (not case.closed or len(case.states) == 1),
            "beam bound",
        )
        require(
            case.reported_cost == min(s.cost for s in case.states)
            and case.unavoidable_log_cost <= case.reported_cost,
            "reported cost",
        )
        require(case.final_cost_unresolved == (not case.closed), "final-cost status")
        require(
            case.bound_scope
            == (
                "accepting_model_alignment_upper_bound"
                if case.closed
                else "model_prefix_alignment_upper_bound"
            ),
            "bound scope",
        )
        require(
            all(
                type(getattr(case, name)) is int and getattr(case, name) >= 0
                for name in (
                    "event_count",
                    "reported_cost",
                    "unavoidable_log_cost",
                    "generated_states",
                    "expired_states",
                    "deduplicated_states",
                    "beam_pruned_states",
                    "fallback_resets",
                    "expansion_limited_events",
                )
            ),
            "case counters",
        )
        require(
            len({s.node_id for s in case.states}) == len(case.states),
            "duplicate trie state",
        )
        for state in case.states:
            require(
                type(state.node_id) is int and 0 <= state.node_id < len(nodes),
                "trie node",
            )
            require(
                len(state.steps) <= spec.witness_history_limit
                and isfinite(state.decay)
                and 0 < state.decay <= max(1.0, spec.decay_time),
                "state retention/decay",
            )
            require(
                all(
                    type(getattr(state, name)) is int and getattr(state, name) >= 0
                    for name in (
                        "cost",
                        "deviation_moves",
                        "omitted_steps",
                        "omitted_cost",
                        "omitted_log_events",
                    )
                ),
                "state counters",
            )
            require(
                state.cost == state.omitted_cost + sum(m.cost for m in state.steps),
                "witness cost accounting",
            )
            require(
                state.omitted_log_events
                + sum(m.event_id is not None for m in state.steps)
                == case.event_count,
                "witness event accounting",
            )
            observed = tuple(m for m in state.steps if m.event_id is not None)
            require(
                tuple(m.sequence for m in observed)
                == tuple(range(state.omitted_log_events, case.event_count)),
                "witness event sequence",
            )
            require(
                len({m.event_id for m in observed}) == len(observed),
                "duplicate witness event IDs",
            )
            seen = {s.sequence: s for s in protocol.seen}
            for move in observed:
                event = StreamEvent(
                    case.case_id,
                    move.event_id,
                    move.sequence,
                    move.activity,
                    move.timestamp,
                )
                if move.sequence in seen:
                    require(
                        seen[move.sequence].event_id == move.event_id
                        and seen[move.sequence].digest == _digest(event),
                        "witness/source event identity",
                    )
            current = state.witness_initial_marking
            spec.model.validate_marking(current)
            if not state.omitted_steps:
                require(
                    current == spec.model.initial_marking
                    and state.omitted_cost == 0
                    and state.omitted_log_events == 0,
                    "untrimmed witness origin",
                )
            for move in state.steps:
                require(type(move.cost) is int and move.cost >= 0, "move cost type")
                require(move.kind in ("sync", "log", "model", "silent"), "move kind")
                if move.kind == "log":
                    require(
                        move.transition_id is None
                        and move.cost == spec.log_move_cost
                        and move.event_id is not None,
                        "log move",
                    )
                else:
                    require(
                        move.transition_id in labels
                        and is_enabled(spec.model, current, move.transition_id),
                        "executable transition witness",
                    )
                    label = labels[move.transition_id]
                    if move.kind == "sync":
                        require(
                            label is not None
                            and label == move.activity
                            and move.event_id is not None
                            and move.cost == 0,
                            "synchronous move",
                        )
                    else:
                        require(
                            move.event_id is None
                            and move.activity is None
                            and move.sequence is None
                            and move.timestamp is None
                            and move.cost == _cost(spec, move.transition_id)
                            and (move.kind == "silent") == (label is None),
                            "model/silent move",
                        )
                    current = fire(spec.model, current, move.transition_id)
            require(current == state.marking, "witness ending marking")
            require(
                state.marking
                == (
                    spec.model.final_marking
                    if case.closed
                    else nodes[state.node_id].marking
                ),
                "trie/final marking",
            )
            # The retained suffix must belong to this actual executable trie
            # path. Uniform move prices also permit exact accounting of omitted
            # model/log/synchronous steps without retaining historical events.
            retained_model = tuple(
                m.transition_id for m in state.steps if m.transition_id is not None
            )
            endings = nodes[state.node_id].terminal_suffixes if case.closed else ((),)
            compatible_origin = False
            for ending in endings:
                path = prefix_paths[state.node_id] + ending
                omitted_model_count = len(path) - len(retained_model)
                if (
                    omitted_model_count < 0
                    or path[omitted_model_count:] != retained_model
                ):
                    continue
                omitted_path = path[:omitted_model_count]
                start = spec.model.initial_marking
                for transition in omitted_path:
                    start = fire(spec.model, start, transition)
                silent = sum(labels[t] is None for t in omitted_path)
                visible = omitted_model_count - silent
                synchronous = (
                    omitted_model_count + state.omitted_log_events - state.omitted_steps
                )
                if not 0 <= synchronous <= min(visible, state.omitted_log_events):
                    continue
                expected_cost = (
                    silent * spec.silent_move_cost
                    + (visible - synchronous) * spec.model_move_cost
                    + (state.omitted_log_events - synchronous) * spec.log_move_cost
                )
                deviations = (
                    visible
                    - synchronous
                    + state.omitted_log_events
                    - synchronous
                    + sum(m.kind in ("log", "model") for m in state.steps)
                )
                if (
                    start == state.witness_initial_marking
                    and expected_cost == state.omitted_cost
                    and deviations == state.deviation_moves
                ):
                    compatible_origin = True
                    break
            require(compatible_origin, "omitted witness/trie path accounting")


RESULT_SCHEMAS = {
    "pix.case_centric.online_alignment.proxy": (
        "online-alignment-proxy",
        OnlineAlignmentSpec,
        OnlineAlignmentProxy,
    ),
    "pix.case_centric.online_alignment.snapshot": (
        "online-alignment-snapshot",
        OnlineAlignmentSpec,
        OnlineAlignmentSnapshot,
    ),
    "pix.case_centric.online_alignment.checkpoint": (
        "online-alignment-checkpoint",
        OnlineAlignmentSpec,
        OnlineAlignmentCheckpoint,
    ),
}

__all__ = [
    "OnlineAlignmentSpec",
    "OnlineAlignmentProxy",
    "OnlineAlignmentMove",
    "OnlineAlignmentState",
    "OnlineAlignmentCase",
    "OnlineAlignmentSnapshot",
    "OnlineAlignmentCheckpoint",
    "OnlineAlignmentStream",
    "build_online_alignment_proxy",
]
