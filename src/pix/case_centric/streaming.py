"""Incremental case-centric monitoring with explicit closure and bounded state.

Events are ordered by a contiguous, zero-based *per-case* sequence. Arrival
order never fabricates a case boundary. DFG counts cover all accepted events;
case details have an explicit retention bound. Replay uses PIX's deterministic
local token repair, not an optimal/approximate online alignment algorithm.
Temporal bounds apply to every earlier source / later target occurrence pair.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from typing import ClassVar

from pix.case_centric.declarative import DeclareConstraint
from pix.compute._common import _derived_result
from pix.compute.replay import _deficit, _firing, _incidence, _silent_closure, _sum
from pix.contracts.models import Marking, PetriNet
from pix.contracts.replay import TokenCounts
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)


def _positive(value: int, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    value.encode("utf-8")


@dataclass(frozen=True, slots=True)
class StreamEvent:
    case_id: str
    event_id: str
    sequence: int
    activity: str | None = None
    timestamp: datetime | None = None
    end: bool = False

    def __post_init__(self):
        _text(self.case_id, "case_id")
        _text(self.event_id, "event_id")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if type(self.end) is not bool:
            raise TypeError("end must be bool")
        if self.end:
            if self.activity is not None:
                raise ValueError("end marker must not have an activity")
        else:
            _text(self.activity, "activity")
        if self.timestamp is not None:
            if (
                not isinstance(self.timestamp, datetime)
                or self.timestamp.tzinfo is None
                or self.timestamp.utcoffset() is None
            ):
                raise ValueError("timestamp must be timezone aware")
            object.__setattr__(
                self, "timestamp", self.timestamp.astimezone(timezone.utc)
            )


@dataclass(frozen=True, slots=True)
class TemporalBounds:
    """Inclusive seconds bounds; every source occurrence before a target counts."""

    source: str
    target: str
    lower_seconds: float
    upper_seconds: float

    def __post_init__(self):
        _text(self.source, "source")
        _text(self.target, "target")
        for value in (self.lower_seconds, self.upper_seconds):
            if type(value) not in (int, float) or not isfinite(value):
                raise ValueError("temporal bounds must be finite numbers")
        if self.lower_seconds > self.upper_seconds:
            raise ValueError("lower bound exceeds upper bound")
        object.__setattr__(self, "lower_seconds", float(self.lower_seconds))
        object.__setattr__(self, "upper_seconds", float(self.upper_seconds))


@dataclass(frozen=True, slots=True)
class StreamingFootprints:
    """Allowed activities, boundary labels and direct succession/parallel pairs."""

    activities: tuple[str, ...]
    starts: tuple[str, ...]
    ends: tuple[str, ...]
    sequence: tuple[tuple[str, str], ...] = ()
    parallel: tuple[tuple[str, str], ...] = ()
    allow_empty: bool = False

    def __post_init__(self):
        if type(self.allow_empty) is not bool:
            raise TypeError("allow_empty must be bool")
        for name in ("activities", "starts", "ends"):
            value = getattr(self, name)
            if (
                not isinstance(value, tuple)
                or any(not isinstance(x, str) or not x.strip() for x in value)
                or len(value) != len(set(value))
            ):
                raise ValueError(f"{name} must contain unique activity strings")
        if not set(self.starts + self.ends) <= set(self.activities):
            raise ValueError("boundary activities must belong to activities")
        for name in ("sequence", "parallel"):
            value = getattr(self, name)
            if not isinstance(value, tuple) or any(
                not isinstance(x, tuple)
                or len(x) != 2
                or any(a not in self.activities for a in x)
                for x in value
            ):
                raise ValueError("footprint pairs must refer to known activities")


@dataclass(frozen=True, slots=True)
class StreamingSpec:
    stream_id: str
    replay_model: PetriNet | None = None
    declare: tuple[DeclareConstraint, ...] = ()
    temporal: tuple[TemporalBounds, ...] = ()
    footprints: StreamingFootprints | None = None
    order_policy: str = "sequence"
    max_cases: int = 1000
    max_activities: int = 1000
    dedup_window: int = 1000
    temporal_history_limit: int = 1000
    silent_max_states: int = 1000
    capacity_policy: str = "reject"
    retirement_filter_bits: int = 16384
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _text(self.stream_id, "stream_id")
        if self.replay_model is not None and not isinstance(
            self.replay_model, PetriNet
        ):
            raise TypeError("replay_model must be PetriNet")
        if not isinstance(self.declare, tuple) or not all(
            isinstance(x, DeclareConstraint) for x in self.declare
        ):
            raise TypeError("declare must be a tuple of DeclareConstraint")
        if not isinstance(self.temporal, tuple) or not all(
            isinstance(x, TemporalBounds) for x in self.temporal
        ):
            raise TypeError("temporal must be a tuple of TemporalBounds")
        if self.footprints is not None and not isinstance(
            self.footprints, StreamingFootprints
        ):
            raise TypeError("footprints must be StreamingFootprints")
        if self.order_policy not in ("sequence", "timestamp"):
            raise ValueError("order_policy must be sequence or timestamp")
        if self.capacity_policy not in ("reject", "evict_oldest"):
            raise ValueError("capacity_policy must be reject or evict_oldest")
        for name in (
            "max_cases",
            "max_activities",
            "dedup_window",
            "temporal_history_limit",
            "silent_max_states",
            "retirement_filter_bits",
        ):
            _positive(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class DeclareMonitorState:
    rule_index: int
    source_count: int = 0
    target_count: int = 0
    last_source: int = -1
    last_target: int = -1
    pending_responses: int = 0
    violated: bool = False
    state: str = "vacuous"
    first_violation_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class TemporalMonitorState:
    rule_index: int
    source_times: tuple[datetime | None, ...] = ()
    pair_count: int = 0
    checked_pairs: int = 0
    violations: int = 0
    unavailable_pairs: int = 0
    omitted_sources: int = 0
    minimum_seconds: float | None = None
    maximum_seconds: float | None = None


@dataclass(frozen=True, slots=True)
class StreamingReplayState:
    marking: Marking
    counts: TokenCounts
    processed_events: int = 0
    log_deviations: int = 0
    silent_firings: int = 0
    status: str = "pending"
    final_reached: bool | None = None


@dataclass(frozen=True, slots=True)
class SeenStreamEvent:
    event_id: str
    sequence: int
    digest: str


@dataclass(frozen=True, slots=True)
class StreamingCase:
    case_id: str
    opened_operation: int
    last_sequence: int = -1
    event_count: int = 0
    first_activity: str | None = None
    last_activity: str | None = None
    last_timestamp: datetime | None = None
    closed: bool = False
    seen: tuple[SeenStreamEvent, ...] = ()
    forgotten_event_ids: int = 0
    event_membership: str = "0"
    declare: tuple[DeclareMonitorState, ...] = ()
    temporal: tuple[TemporalMonitorState, ...] = ()
    replay: StreamingReplayState | None = None
    footprint_violations: int = 0
    footprint_state: str | None = None


@dataclass(frozen=True, slots=True)
class StreamingDFG:
    activities: tuple[tuple[str, int], ...]
    edges: tuple[tuple[str, str, int], ...]
    starts: tuple[tuple[str, int], ...]
    ends: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class StreamingSnapshot:
    """Exact aggregate prefix counts; retained cases are not the entire population."""

    prefix_digest: str
    accepted_operations: int
    accepted_events: int
    created_cases: int
    closed_cases: int
    evicted_cases: int
    evicted_open_cases: int
    retirement_membership: str
    dfg: StreamingDFG
    cases: tuple[StreamingCase, ...]


@dataclass(frozen=True, slots=True)
class StreamingCheckpoint:
    snapshot: StreamingSnapshot
    state_digest: str


@dataclass(frozen=True, slots=True)
class StreamReceipt:
    status: str
    case_id: str
    event_id: str
    prefix_digest: str
    evicted_case_id: str | None = None


def _declare_update(
    old: DeclareMonitorState,
    rule: DeclareConstraint,
    activity: str,
    index: int,
    previous: str | None,
) -> DeclareMonitorState:
    """Finite automata/counters; no prefix trace is retained or batch-replayed."""
    template, a, b = rule.template, rule.source, rule.target
    response = template in ("response", "succession")
    alternate = template in ("alternate_response", "alternate_succession")
    chain = template in ("chain_response", "chain_succession")
    violated = old.violated
    pending = old.pending_responses
    if chain and previous == a:
        violated |= activity != b
        pending = 0
    if alternate and activity == a and pending:
        violated = True
    if activity == b:
        if template in ("precedence", "succession"):
            violated |= old.source_count == 0
        if template in ("alternate_precedence", "alternate_succession"):
            violated |= old.last_source <= old.last_target
        if template in ("chain_precedence", "chain_succession"):
            violated |= previous != a
        if template in ("not_precedence", "not_response", "nonsuccession"):
            violated |= old.source_count > 0
        if template == "nonchainsuccession":
            violated |= previous == a
        if response or alternate or chain:
            pending = 0
    if activity == a and (response or alternate or chain):
        pending += 1
    return replace(
        old,
        source_count=old.source_count + (activity == a),
        target_count=old.target_count + (activity == b),
        last_source=index if activity == a else old.last_source,
        last_target=index if activity == b else old.last_target,
        pending_responses=pending,
        violated=violated,
        first_violation_sequence=index
        if violated and old.first_violation_sequence is None
        else old.first_violation_sequence,
    )


def _declare_state(
    old: DeclareMonitorState, rule: DeclareConstraint, case: StreamingCase
) -> DeclareMonitorState:
    t, a, b = rule.template, old.source_count, old.target_count
    pending = "violated" if case.closed else "pending"
    if old.violated:
        state = "violated"
    elif t == "existence":
        state = "satisfied" if a >= rule.cardinality else pending
    elif t == "absence":
        state = "satisfied" if a < rule.cardinality else "violated"
    elif t in ("exactly", "exactly_one"):
        n = rule.cardinality if t == "exactly" else 1
        state = "satisfied" if a == n else "violated" if a > n else pending
    elif t == "init":
        state = (
            "satisfied"
            if case.first_activity == rule.source
            else "violated"
            if case.event_count
            else pending
        )
    elif t == "end":
        state = (
            "pending"
            if not case.closed
            else "satisfied"
            if case.last_activity == rule.source
            else "violated"
        )
    elif t == "responded_existence":
        state = "vacuous" if not a else "satisfied" if b else pending
    elif t == "coexistence":
        state = "vacuous" if not a and not b else "satisfied" if a and b else pending
    elif t == "noncoexistence":
        state = "violated" if a and b else "satisfied" if a or b else "vacuous"
    elif old.pending_responses:
        state = pending
    elif t in (
        "precedence",
        "alternate_precedence",
        "chain_precedence",
        "not_precedence",
    ):
        state = "satisfied" if b else "vacuous"
    elif t in ("succession", "alternate_succession", "chain_succession"):
        state = "satisfied" if a or b else "vacuous"
    else:
        state = "satisfied" if a else "vacuous"
    return replace(
        old,
        state=state,
        first_violation_sequence=case.last_sequence
        if state == "violated" and old.first_violation_sequence is None
        else old.first_violation_sequence,
    )


def _temporal_update(
    old: TemporalMonitorState, rule: TemporalBounds, event: StreamEvent, limit: int
) -> TemporalMonitorState:
    count, checked, violations, unavailable = (
        old.pair_count,
        old.checked_pairs,
        old.violations,
        old.unavailable_pairs,
    )
    minimum, maximum = old.minimum_seconds, old.maximum_seconds
    if event.activity == rule.target:
        count += len(old.source_times) + old.omitted_sources
        unavailable += old.omitted_sources
        for timestamp in old.source_times:
            if timestamp is None or event.timestamp is None:
                unavailable += 1
                continue
            seconds = (event.timestamp - timestamp).total_seconds()
            checked += 1
            violations += not rule.lower_seconds <= seconds <= rule.upper_seconds
            minimum = seconds if minimum is None else min(minimum, seconds)
            maximum = seconds if maximum is None else max(maximum, seconds)
    times, omitted = old.source_times, old.omitted_sources
    if event.activity == rule.source:
        if len(times) < limit:
            times += (event.timestamp,)
        else:
            omitted += 1
    return TemporalMonitorState(
        old.rule_index,
        times,
        count,
        checked,
        violations,
        unavailable,
        omitted,
        minimum,
        maximum,
    )


def _replay_update(
    old: StreamingReplayState,
    model: PetriNet,
    activity: str | None,
    event_id: str | None,
    limit: int,
) -> StreamingReplayState:
    if old.status == "limited":
        return old
    current = old.marking
    candidates = tuple(t.id for t in model.transitions if t.activity == activity)
    if activity is not None and not candidates:
        return replace(
            old,
            processed_events=old.processed_events + 1,
            log_deviations=old.log_deviations + 1,
        )
    closure = _silent_closure(model, current, limit, activity)
    if closure.limited:
        return replace(old, status="limited")
    final_reached = closure.choice is not None if activity is None else None
    if closure.choice is not None:
        _, path, selected = closure.choice
    elif activity is not None:
        _, _, path, selected = min(
            (
                _sum(_deficit(state, _incidence(model, transition)[0])),
                len(path),
                path,
                transition,
            )
            for state, path in closure.states
            for transition in candidates
        )
    else:
        _, _, _, path = min(
            (
                2 * _sum(_deficit(state, model.final_marking.tokens))
                + _sum(state.tokens)
                - _sum(model.final_marking.tokens),
                _sum(_deficit(state, model.final_marking.tokens)),
                len(path),
                path,
            )
            for state, path in closure.states
        )
        selected = None
    missing, consumed, produced = (
        old.counts.missing,
        old.counts.consumed,
        old.counts.produced,
    )
    for transition in path:
        current, step = _firing(model, current, transition)
        consumed += _sum(step.consumed_tokens)
        produced += _sum(step.produced_tokens)
    if activity is not None:
        inserted = _deficit(current, _incidence(model, selected)[0])
        current, step = _firing(
            model,
            current,
            selected,
            event_id=event_id,
            activity=activity,
            inserted=inserted,
        )
        missing += _sum(inserted)
        consumed += _sum(step.consumed_tokens)
        produced += _sum(step.produced_tokens)
    else:
        inserted = dict(_deficit(current, model.final_marking.tokens))
        marking = Counter(dict(current.tokens))
        marking.update(inserted)
        marking.subtract(dict(model.final_marking.tokens))
        current = Marking(tuple((p, n) for p, n in marking.items() if n))
        missing += sum(inserted.values())
        consumed += _sum(model.final_marking.tokens)
    return StreamingReplayState(
        current,
        TokenCounts(missing, _sum(current.tokens), consumed, produced),
        old.processed_events + (activity is not None),
        old.log_deviations,
        old.silent_firings + len(path),
        "completed" if activity is None else "pending",
        final_reached,
    )


def _digest(value) -> str:
    return computation_identity(
        "pix.case_centric.streaming.state", "1.0.0", "pix.streaming.state.v1", value
    )


def _membership_bits(identifier: str, bits: int) -> int:
    raw = sha256(identifier.encode("utf-8")).digest()
    return sum(
        1 << i
        for i in {
            int.from_bytes(raw[offset : offset + 8], "big") % bits
            for offset in (0, 8, 16)
        }
    )


def _validate_checkpoint(state: StreamingSnapshot, spec: StreamingSpec) -> None:
    """Checksums detect edits; these checks enforce resumable state invariants."""

    def require(condition, message):
        if not condition:
            raise ValueError("invalid checkpoint: " + message)

    def natural(value):
        return type(value) is int and value >= 0

    for name in (
        "accepted_operations",
        "accepted_events",
        "created_cases",
        "closed_cases",
        "evicted_cases",
        "evicted_open_cases",
    ):
        require(
            natural(getattr(state, name)), "negative or noninteger population count"
        )
    require(
        state.accepted_operations == state.accepted_events + state.closed_cases,
        "operation accounting",
    )
    require(
        state.created_cases == len(state.cases) + state.evicted_cases,
        "case population accounting",
    )
    require(state.evicted_open_cases <= state.evicted_cases, "eviction accounting")
    require(
        sum(c.closed for c in state.cases)
        + state.evicted_cases
        - state.evicted_open_cases
        == state.closed_cases,
        "closed population accounting",
    )
    require(len(state.cases) <= spec.max_cases, "case capacity")
    require(
        len({c.case_id for c in state.cases}) == len(state.cases), "duplicate cases"
    )
    require(
        0 <= int(state.retirement_membership, 16) < (1 << spec.retirement_filter_bits),
        "membership bound",
    )
    counts = {}
    for name in ("activities", "starts", "ends"):
        rows = getattr(state.dfg, name)
        require(
            isinstance(rows, tuple)
            and all(
                isinstance(r, tuple)
                and len(r) == 2
                and isinstance(r[0], str)
                and r[0].strip()
                and type(r[1]) is int
                and r[1] > 0
                for r in rows
            ),
            "DFG count row shape",
        )
        require(len(dict(rows)) == len(rows), "duplicate DFG count keys")
        counts[name] = dict(rows)
    activities = set(counts["activities"])
    require(len(activities) <= spec.max_activities, "activity capacity")
    require(
        set(counts["starts"]) <= activities and set(counts["ends"]) <= activities,
        "boundary activity outside alphabet",
    )
    require(
        all(
            n <= counts["activities"][a]
            for name in ("starts", "ends")
            for a, n in counts[name].items()
        ),
        "boundary count exceeds occurrences",
    )
    require(
        isinstance(state.dfg.edges, tuple)
        and all(
            isinstance(r, tuple)
            and len(r) == 3
            and r[0] in activities
            and r[1] in activities
            and type(r[2]) is int
            and r[2] > 0
            for r in state.dfg.edges
        ),
        "DFG edge outside alphabet or invalid count",
    )
    require(
        len({(a, b) for a, b, _ in state.dfg.edges}) == len(state.dfg.edges),
        "duplicate DFG edges",
    )
    require(
        sum(counts["activities"].values()) == state.accepted_events,
        "activity accounting",
    )
    require(
        sum(n for _, _, n in state.dfg.edges)
        == state.accepted_events - sum(counts["starts"].values()),
        "edge accounting",
    )
    require(
        sum(counts["starts"].values()) <= state.created_cases
        and sum(counts["ends"].values()) <= state.closed_cases,
        "boundary population accounting",
    )
    require(
        sum(c.event_count for c in state.cases) <= state.accepted_events,
        "retained event accounting",
    )
    for case in state.cases:
        _text(case.case_id, "case_id")
        mask = _membership_bits(case.case_id, spec.retirement_filter_bits)
        require(
            int(state.retirement_membership, 16) & mask == mask,
            "case membership missing",
        )
        require(
            natural(case.event_count) and type(case.closed) is bool,
            "case event count/closure",
        )
        require(case.closed or case.event_count > 0, "an open case needs an event")
        require(
            natural(case.opened_operation)
            and case.opened_operation < state.accepted_operations,
            "case opening operation",
        )
        require(
            case.last_sequence == case.event_count - (not case.closed),
            "case sequence accounting",
        )
        require(
            (case.first_activity is None) == (case.event_count == 0)
            and (case.last_activity is None) == (case.event_count == 0),
            "case boundary presence",
        )
        require(
            not case.event_count
            or (case.first_activity in activities and case.last_activity in activities),
            "case boundary alphabet",
        )
        require(
            len(case.seen) == min(case.last_sequence + 1, spec.dedup_window),
            "dedup window length",
        )
        require(
            tuple(s.sequence for s in case.seen)
            == tuple(
                range(case.last_sequence + 1 - len(case.seen), case.last_sequence + 1)
            ),
            "dedup sequence window",
        )
        require(
            len({s.event_id for s in case.seen}) == len(case.seen),
            "duplicate retained event IDs",
        )
        for seen in case.seen:
            _text(seen.event_id, "event_id")
            _text(seen.digest, "event digest")
            mask = _membership_bits(seen.event_id, spec.retirement_filter_bits)
            require(
                int(case.event_membership, 16) & mask == mask,
                "event membership missing",
            )
        require(
            case.forgotten_event_ids == case.last_sequence + 1 - len(case.seen),
            "dedup expiration accounting",
        )
        require(
            0 <= int(case.event_membership, 16) < (1 << spec.retirement_filter_bits),
            "event membership bound",
        )
        require(
            len(case.declare) == len(spec.declare)
            and len(case.temporal) == len(spec.temporal),
            "monitor/spec cardinality",
        )
        for index, (monitor, rule) in enumerate(zip(case.declare, spec.declare)):
            require(
                monitor.rule_index == index
                and natural(monitor.source_count)
                and natural(monitor.target_count),
                "Declare counters",
            )
            require(
                monitor.source_count + monitor.target_count <= case.event_count,
                "Declare activation count",
            )
            require(
                -1 <= monitor.last_source < case.event_count
                and -1 <= monitor.last_target < case.event_count,
                "Declare last occurrence",
            )
            require(
                natural(monitor.pending_responses)
                and monitor.pending_responses <= monitor.source_count,
                "Declare pending count",
            )
            require(monitor == _declare_state(monitor, rule, case), "Declare state")
        for index, monitor in enumerate(case.temporal):
            require(
                monitor.rule_index == index
                and len(monitor.source_times) <= spec.temporal_history_limit,
                "temporal state/spec bound",
            )
            require(
                all(
                    natural(getattr(monitor, n))
                    for n in (
                        "pair_count",
                        "checked_pairs",
                        "violations",
                        "unavailable_pairs",
                        "omitted_sources",
                    )
                ),
                "temporal count type",
            )
            require(
                monitor.checked_pairs + monitor.unavailable_pairs == monitor.pair_count
                and monitor.violations <= monitor.checked_pairs,
                "temporal pair accounting",
            )
            require(
                len(monitor.source_times) + monitor.omitted_sources <= case.event_count,
                "temporal source accounting",
            )
        require(
            (case.replay is None) == (spec.replay_model is None),
            "replay model presence",
        )
        if case.replay is not None:
            replay = case.replay
            spec.replay_model.validate_marking(replay.marking)
            require(
                replay.counts.remaining == _sum(replay.marking.tokens),
                "replay marking/accounting disagreement",
            )
            require(
                replay.status in ("pending", "completed", "limited"), "replay status"
            )
            require(
                all(
                    natural(getattr(replay, n))
                    for n in ("processed_events", "log_deviations", "silent_firings")
                ),
                "replay count type",
            )
            require(
                replay.log_deviations <= replay.processed_events <= case.event_count,
                "replay processed accounting",
            )
            require(
                (
                    replay.status == "completed"
                    and case.closed
                    and replay.final_reached is not None
                )
                or (
                    replay.status == "pending"
                    and not case.closed
                    and replay.final_reached is None
                )
                or (replay.status == "limited" and replay.final_reached is None),
                "replay finalization state",
            )
            require(
                replay.status == "limited"
                or replay.processed_events == case.event_count,
                "replay prefix coverage",
            )


class CaseStream:
    """A single-writer deterministic monitor; use external synchronization.

    Rejected input is atomic and leaves state untouched. Retries are idempotent
    inside each retained case's dedup window; expired sequences are rejected.
    Eviction never silently restarts a case: fixed-size membership can reject a
    genuinely new ID on a hash collision, explicitly reported to the caller.
    This is a bounded-retention protocol, not indefinite exactly-once delivery.
    """

    __slots__ = ("_spec", "_state")

    def __init__(self, spec: StreamingSpec):
        if not isinstance(spec, StreamingSpec):
            raise TypeError("spec must be StreamingSpec")
        self._spec = spec
        seed = sha256(spec.stream_id.encode("utf-8")).hexdigest()
        self._state = StreamingSnapshot(
            "pix.stream.prefix.v1:sha256:" + seed,
            0,
            0,
            0,
            0,
            0,
            0,
            "0",
            StreamingDFG((), (), (), ()),
            (),
        )

    @property
    def spec(self) -> StreamingSpec:
        """Configuration cannot change underneath already accepted state."""
        return self._spec

    def _membership(self, case_id: str) -> int:
        return _membership_bits(case_id, self.spec.retirement_filter_bits)

    def ingest(self, event: StreamEvent) -> StreamReceipt:
        if not isinstance(event, StreamEvent):
            raise TypeError("event must be StreamEvent")
        state = self._state
        cases = {case.case_id: case for case in state.cases}
        old = cases.get(event.case_id)
        digest = _digest(event)
        if old is not None:
            for seen in old.seen:
                if seen.event_id == event.event_id or seen.sequence == event.sequence:
                    if seen.digest == digest:
                        return StreamReceipt(
                            "duplicate",
                            event.case_id,
                            event.event_id,
                            state.prefix_digest,
                        )
                    raise ValueError(
                        "duplicate_conflict: event ID or sequence has different content"
                    )
            if event.sequence <= old.last_sequence:
                raise ValueError(
                    "expired_sequence: retry identity fell outside dedup window"
                )
            mask = self._membership(event.event_id)
            if int(old.event_membership, 16) & mask == mask:
                raise ValueError(
                    "expired_event_identity_or_membership_collision: choose a fresh event identity"
                )
            if old.closed:
                raise ValueError("case_closed: a closed case cannot accept new events")
        elif event.sequence != 0:
            raise ValueError("out_of_order: a new case must start at sequence zero")
        elif int(state.retirement_membership, 16) & self._membership(
            event.case_id
        ) == self._membership(event.case_id):
            raise ValueError(
                "retired_case_or_membership_collision: use a new unique case identity"
            )
        if old is not None and event.sequence != old.last_sequence + 1:
            raise ValueError("out_of_order: per-case sequence must be contiguous")
        if self.spec.order_policy == "timestamp" and not event.end:
            if event.timestamp is None:
                raise ValueError(
                    "timestamp_required: timestamp order requires timestamps"
                )
            if (
                old is not None
                and old.last_timestamp is not None
                and event.timestamp < old.last_timestamp
            ):
                raise ValueError("out_of_order: timestamp decreases inside case")
        activities, edges = (
            Counter(dict(state.dfg.activities)),
            Counter({(a, b): n for a, b, n in state.dfg.edges}),
        )
        starts, ends = Counter(dict(state.dfg.starts)), Counter(dict(state.dfg.ends))
        if (
            not event.end
            and event.activity not in activities
            and len(activities) >= self.spec.max_activities
        ):
            raise ValueError(
                "activity_capacity: unseen activity would exceed bounded vocabulary"
            )
        evicted = None
        evicted_open = False
        if old is None:
            if len(cases) >= self.spec.max_cases:
                if self.spec.capacity_policy == "reject":
                    raise ValueError("case_capacity: retained case limit reached")
                victim = min(
                    cases.values(),
                    key=lambda c: (not c.closed, c.opened_operation, c.case_id),
                )
                evicted, evicted_open = victim.case_id, not victim.closed
                del cases[victim.case_id]
            model = self.spec.replay_model
            replay = (
                None
                if model is None
                else StreamingReplayState(
                    model.initial_marking,
                    TokenCounts(
                        0,
                        _sum(model.initial_marking.tokens),
                        0,
                        _sum(model.initial_marking.tokens),
                    ),
                )
            )
            old = StreamingCase(
                event.case_id,
                state.accepted_operations,
                declare=tuple(
                    DeclareMonitorState(i) for i in range(len(self.spec.declare))
                ),
                temporal=tuple(
                    TemporalMonitorState(i) for i in range(len(self.spec.temporal))
                ),
                replay=replay,
            )
        created = event.case_id not in {case.case_id for case in state.cases}
        seen = old.seen + (SeenStreamEvent(event.event_id, event.sequence, digest),)
        forgotten = max(0, len(seen) - self.spec.dedup_window)
        case = replace(
            old,
            last_sequence=event.sequence,
            seen=seen[-self.spec.dedup_window :],
            forgotten_event_ids=old.forgotten_event_ids + forgotten,
            closed=event.end,
            event_membership=hex(
                int(old.event_membership, 16) | self._membership(event.event_id)
            ),
        )
        footprint_violations = old.footprint_violations
        footprint = self.spec.footprints
        if not event.end:
            activities[event.activity] += 1
            if old.last_activity is None:
                starts[event.activity] += 1
            else:
                edges[old.last_activity, event.activity] += 1
            if footprint is not None:
                footprint_violations += event.activity not in footprint.activities
                if old.last_activity is None:
                    footprint_violations += event.activity not in footprint.starts
                elif (
                    (old.last_activity, event.activity) not in footprint.sequence
                    and (old.last_activity, event.activity) not in footprint.parallel
                    and (event.activity, old.last_activity) not in footprint.parallel
                ):
                    footprint_violations += 1
            case = replace(
                case,
                event_count=old.event_count + 1,
                first_activity=old.first_activity or event.activity,
                last_activity=event.activity,
                last_timestamp=event.timestamp
                if event.timestamp is not None
                else old.last_timestamp,
                declare=tuple(
                    _declare_update(
                        s, rule, event.activity, old.event_count, old.last_activity
                    )
                    for s, rule in zip(old.declare, self.spec.declare)
                ),
                temporal=tuple(
                    _temporal_update(s, rule, event, self.spec.temporal_history_limit)
                    for s, rule in zip(old.temporal, self.spec.temporal)
                ),
            )
        else:
            if old.last_activity is not None:
                ends[old.last_activity] += 1
            if footprint is not None:
                footprint_violations += (
                    (old.last_activity not in footprint.ends)
                    if old.event_count
                    else (not footprint.allow_empty)
                )
        case = replace(
            case,
            declare=tuple(
                _declare_state(s, rule, case)
                for s, rule in zip(case.declare, self.spec.declare)
            ),
            replay=None
            if old.replay is None
            else _replay_update(
                old.replay,
                self.spec.replay_model,
                event.activity,
                None if event.end else event.event_id,
                self.spec.silent_max_states,
            ),
            footprint_violations=footprint_violations,
            footprint_state=None
            if footprint is None
            else "violated"
            if footprint_violations
            else "satisfied"
            if event.end
            else "pending",
        )
        cases[event.case_id] = case
        prefix = (
            "pix.stream.prefix.v1:sha256:"
            + sha256((state.prefix_digest + digest).encode("utf-8")).hexdigest()
        )
        self._state = StreamingSnapshot(
            prefix,
            state.accepted_operations + 1,
            state.accepted_events + (not event.end),
            state.created_cases + created,
            state.closed_cases + event.end,
            state.evicted_cases + (evicted is not None),
            state.evicted_open_cases + evicted_open,
            hex(int(state.retirement_membership, 16) | self._membership(event.case_id)),
            StreamingDFG(
                tuple(sorted(activities.items())),
                tuple((a, b, n) for (a, b), n in sorted(edges.items())),
                tuple(sorted(starts.items())),
                tuple(sorted(ends.items())),
            ),
            tuple(sorted(cases.values(), key=lambda c: c.case_id)),
        )
        return StreamReceipt("accepted", event.case_id, event.event_id, prefix, evicted)

    def close_case(self, case_id: str, event_id: str, sequence: int) -> StreamReceipt:
        return self.ingest(StreamEvent(case_id, event_id, sequence, end=True))

    def _issues(self) -> tuple[ComputeIssue, ...]:
        state = self._state
        issues = []
        if any(not c.closed for c in state.cases):
            issues.append(
                ComputeIssue(
                    "open_cases",
                    "Retained open cases have not been finalized; end counts include explicit closures only",
                )
            )
        if state.evicted_cases:
            issues.append(
                ComputeIssue(
                    "case_details_evicted",
                    f"{state.evicted_cases} case details evicted ({state.evicted_open_cases} open); aggregate DFG remains exact for accepted events",
                )
            )
        if any(
            c.replay is not None and c.replay.status == "limited" for c in state.cases
        ):
            issues.append(
                ComputeIssue(
                    "silent_state_limit",
                    "Replay stopped at a bounded silent search; this does not prove unreachability",
                )
            )
        if any(s.omitted_sources for c in state.cases for s in c.temporal):
            issues.append(
                ComputeIssue(
                    "temporal_history_limit",
                    "Some source timestamps omitted; future pairs involving them cannot be evaluated",
                )
            )
        if any(s.unavailable_pairs for c in state.cases for s in c.temporal):
            issues.append(
                ComputeIssue(
                    "temporal_pairs_unavailable",
                    "Missing or omitted timestamps prevent full temporal conformance evaluation",
                )
            )
        if any(c.forgotten_event_ids for c in state.cases):
            issues.append(
                ComputeIssue(
                    "dedup_window_expired",
                    "Old event identities forgotten; expired sequence retries are rejected, not accepted again",
                )
            )
        return tuple(issues)

    def snapshot(self) -> ComputationResult[StreamingSnapshot]:
        issues = self._issues()
        return _derived_result(
            "pix.case_centric.streaming.snapshot",
            self._state.prefix_digest,
            self.spec,
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
            self._state,
            issues,
        )

    def checkpoint(self) -> ComputationResult[StreamingCheckpoint]:
        issues = self._issues()
        return _derived_result(
            "pix.case_centric.streaming.checkpoint",
            self._state.prefix_digest,
            self.spec,
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
            StreamingCheckpoint(self._state, _digest(self._state)),
            issues,
        )

    @classmethod
    def resume(cls, checkpoint: ComputationResult[StreamingCheckpoint]) -> CaseStream:
        if (
            not isinstance(checkpoint, ComputationResult)
            or checkpoint.operator_id != "pix.case_centric.streaming.checkpoint"
            or not isinstance(checkpoint.spec, StreamingSpec)
            or not isinstance(checkpoint.value, StreamingCheckpoint)
        ):
            raise TypeError("expected a PIX streaming checkpoint result")
        state = checkpoint.value.snapshot
        if (
            checkpoint.operator_version != "1.0.0"
            or checkpoint.value.state_digest != _digest(state)
            or checkpoint.source_digest != state.prefix_digest
        ):
            raise ValueError("checkpoint state identity mismatch")
        if checkpoint.computation_id != computation_identity(
            checkpoint.operator_id,
            checkpoint.operator_version,
            checkpoint.source_digest,
            checkpoint.spec,
            checkpoint.parent_computation_ids,
        ):
            raise ValueError("checkpoint request identity mismatch")
        restored = cls(checkpoint.spec)
        _validate_checkpoint(state, restored.spec)
        restored._state = state
        return restored


RESULT_SCHEMAS = {
    "pix.case_centric.streaming.snapshot": (
        "case-stream-snapshot",
        StreamingSpec,
        StreamingSnapshot,
    ),
    "pix.case_centric.streaming.checkpoint": (
        "case-stream-checkpoint",
        StreamingSpec,
        StreamingCheckpoint,
    ),
}

__all__ = [
    "StreamEvent",
    "TemporalBounds",
    "StreamingFootprints",
    "StreamingSpec",
    "DeclareMonitorState",
    "TemporalMonitorState",
    "StreamingReplayState",
    "SeenStreamEvent",
    "StreamingCase",
    "StreamingDFG",
    "StreamingSnapshot",
    "StreamingCheckpoint",
    "StreamReceipt",
    "CaseStream",
]
