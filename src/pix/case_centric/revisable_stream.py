"""Exact, retained-fact case stream with explicit corrections and retractions.

This engine retains every accepted operation and every event identity, including
deletion tombstones. It recomputes the batch DFG after each operation; it makes
no bounded-memory, constant-time, watermark-finality or distributed exactly-once
claim. Source offsets and operation IDs protect replay within this retained
history. Mutations are atomic within one Python call, not thread safe.

DFG ends are the ends of *observed prefixes*, including open cases, exactly as
in batch discovery. Closure forbids further edits until an explicit reopen.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256

from pix.case_centric.discovery import (
    CaseRelationGraph,
    RelationDiscoverySpec,
    discover_dfg,
)
from pix.compute._common import _derived_result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    value.encode("utf-8")


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


def _digest(value: object) -> str:
    return "pix.case-revision.v1:sha256:" + sha256(_json(value).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceOffset:
    """A monotone nonnegative offset within one source partition.

    Gaps are allowed. A previously accepted offset may be retried; an unseen
    offset below the accepted maximum is rejected, never silently discarded.
    Event time may decrease independently of source offsets.
    """

    source_id: str
    partition: str
    offset: int

    def __post_init__(self):
        _text(self.source_id, "source_id")
        _text(self.partition, "partition")
        _integer(self.offset, "offset")


@dataclass(frozen=True, slots=True)
class RevisableCaseStreamSpec:
    stream_id: str
    order_policy: str = "timestamp"
    tie_policy: str = "event_id"

    def __post_init__(self):
        _text(self.stream_id, "stream_id")
        if self.order_policy not in ("timestamp", "sequence"):
            raise ValueError("order_policy must be timestamp or sequence")
        if self.tie_policy not in ("event_id", "reject"):
            raise ValueError("tie_policy must be event_id or reject")
        if self.order_policy == "sequence" and self.tie_policy != "reject":
            # Sequence duplicates are rejected regardless; do not advertise an
            # event-ID tie break for an explicit unique sequence contract.
            object.__setattr__(self, "tie_policy", "reject")


@dataclass(frozen=True, slots=True)
class RetainedCaseEvent:
    """Minimal mining facts; sequence gaps are allowed, arrival order is unused."""

    case_id: str
    event_id: str
    activity: str
    timestamp: datetime | None = None
    sequence: int | None = None

    def __post_init__(self):
        for name in ("case_id", "event_id", "activity"):
            _text(getattr(self, name), name)
        if self.sequence is not None:
            _integer(self.sequence, "sequence")
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
class CaseEventRevision:
    """A deleted event retains its identity, case and last revision as a tombstone."""

    case_id: str
    event_id: str
    revision: int
    event: RetainedCaseEvent | None

    def __post_init__(self):
        _text(self.case_id, "case_id")
        _text(self.event_id, "event_id")
        _integer(self.revision, "revision", 1)
        if self.event is not None and (
            not isinstance(self.event, RetainedCaseEvent)
            or self.event.case_id != self.case_id
            or self.event.event_id != self.event_id
        ):
            raise ValueError("event revision identity mismatch")


@dataclass(frozen=True, slots=True)
class DFGCountChange:
    """Signed count delta; negative values explicitly retract previous evidence."""

    metric: str
    key: tuple[str, ...]
    previous: int
    current: int
    delta: int

    def __post_init__(self):
        scalars = ("trace_count", "empty_trace_count", "examined_event_pairs")
        if self.metric not in (
            "activity",
            "edge",
            "edge_cases",
            "start",
            "end",
            *scalars,
        ):
            raise ValueError("unknown DFG metric")
        length = (
            0
            if self.metric in scalars
            else 2
            if self.metric in ("edge", "edge_cases")
            else 1
        )
        if not isinstance(self.key, tuple) or len(self.key) != length:
            raise ValueError("invalid DFG change key")
        for label in self.key:
            _text(label, "activity")
        _integer(self.previous, "previous")
        _integer(self.current, "current")
        if type(self.delta) is not int or self.delta != self.current - self.previous:
            raise ValueError("DFG delta must equal current minus previous")
        if not self.delta:
            raise ValueError("zero changes must be omitted")


@dataclass(frozen=True, slots=True)
class CaseRevisionOperation:
    operation_id: str
    action: str
    case_id: str
    event_id: str | None = None
    event: RetainedCaseEvent | None = None
    expected_revision: int | None = None
    source_offset: SourceOffset | None = None

    def __post_init__(self):
        _text(self.operation_id, "operation_id")
        _text(self.case_id, "case_id")
        if self.action not in ("upsert", "delete", "close", "reopen"):
            raise ValueError("unknown revision action")
        if self.expected_revision is not None:
            _integer(self.expected_revision, "expected_revision", 1)
        if self.source_offset is not None and not isinstance(
            self.source_offset, SourceOffset
        ):
            raise TypeError("source_offset must be SourceOffset")
        if self.action in ("upsert", "delete"):
            _text(self.event_id, "event_id")
        elif (
            self.event_id is not None
            or self.event is not None
            or self.expected_revision is not None
        ):
            raise ValueError("case boundary operations cannot carry event fields")
        if self.action == "upsert":
            if not isinstance(self.event, RetainedCaseEvent):
                raise TypeError("upsert requires RetainedCaseEvent")
            if (self.event.case_id, self.event.event_id) != (
                self.case_id,
                self.event_id,
            ):
                raise ValueError("operation event identity mismatch")
        elif self.event is not None:
            raise ValueError("only upsert may carry event facts")
        if self.action == "delete" and self.expected_revision is None:
            raise ValueError("delete requires expected_revision")


@dataclass(frozen=True, slots=True)
class CaseRevisionReceipt:
    status: str
    operation_id: str
    revision: int
    revision_id: str
    previous_revision_id: str
    event_revision: int | None
    computation_id: str

    def __post_init__(self):
        if self.status not in ("accepted", "unchanged", "duplicate"):
            raise ValueError("unknown revision receipt status")
        _integer(self.revision, "revision", 1)
        if self.event_revision is not None:
            _integer(self.event_revision, "event_revision", 1)
        for name in (
            "operation_id",
            "revision_id",
            "previous_revision_id",
            "computation_id",
        ):
            _text(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class RevisableCaseSnapshot:
    revision: int
    revision_id: str
    previous_revision_id: str | None
    previous_computation_id: str | None
    events: tuple[CaseEventRevision, ...]
    cases: tuple[str, ...]
    closed_cases: tuple[str, ...]
    dfg: CaseRelationGraph
    previous_dfg: CaseRelationGraph | None
    changes: tuple[DFGCountChange, ...]

    def __post_init__(self):
        _integer(self.revision, "revision")
        _text(self.revision_id, "revision_id")
        for name in ("previous_revision_id", "previous_computation_id"):
            if getattr(self, name) is not None:
                _text(getattr(self, name), name)
        if not isinstance(self.events, tuple) or not all(
            isinstance(v, CaseEventRevision) for v in self.events
        ):
            raise TypeError("events must contain immutable CaseEventRevision values")
        if len({v.event_id for v in self.events}) != len(self.events):
            raise ValueError("event revision identities must be unique")
        for name in ("cases", "closed_cases"):
            value = getattr(self, name)
            if not isinstance(value, tuple):
                raise TypeError(f"{name} must be tuple")
            for case_id in value:
                _text(case_id, "case_id")
            if len(set(value)) != len(value):
                raise ValueError(f"{name} identities must be unique")
        if not set(self.closed_cases) <= set(self.cases) or not {
            v.case_id for v in self.events
        } <= set(self.cases):
            raise ValueError("revision facts refer to unknown cases")
        if not isinstance(self.dfg, CaseRelationGraph) or not self.dfg.complete:
            raise ValueError("revisable snapshot requires a complete batch DFG")
        if self.previous_dfg is not None and not isinstance(
            self.previous_dfg, CaseRelationGraph
        ):
            raise TypeError("previous_dfg must be CaseRelationGraph or None")
        if not isinstance(self.changes, tuple) or not all(
            isinstance(v, DFGCountChange) for v in self.changes
        ):
            raise TypeError("changes must contain immutable DFGCountChange values")
        if self.revision == 0:
            if (
                self.previous_revision_id is not None
                or self.previous_computation_id is not None
                or self.previous_dfg is not None
                or self.changes
            ):
                raise ValueError("initial revision cannot have a predecessor")
        elif (
            self.previous_revision_id is None
            or self.previous_computation_id is None
            or self.previous_dfg is None
        ):
            raise ValueError("noninitial revision requires predecessor evidence")
        if self.previous_dfg is not None and self.changes != _changes(
            self.previous_dfg, self.dfg
        ):
            raise ValueError("revision changes do not match previous and current DFG")


def _operation_data(operation: CaseRevisionOperation) -> dict:
    data = asdict(operation)
    if operation.event is not None and operation.event.timestamp is not None:
        data["event"]["timestamp"] = operation.event.timestamp.isoformat()
    return data


def _counts(graph: CaseRelationGraph) -> dict:
    values = {
        (name, ()): getattr(graph, name)
        for name in ("trace_count", "empty_trace_count", "examined_event_pairs")
    }
    for metric, rows in (
        ("activity", graph.activity_counts),
        ("start", graph.start_counts),
        ("end", graph.end_counts),
    ):
        values.update({(metric, (a,)): count for a, count in rows})
    for edge in graph.edges:
        values["edge", (edge.source, edge.target)] = edge.count
        values["edge_cases", (edge.source, edge.target)] = edge.case_count
    return values


def _changes(
    previous: CaseRelationGraph, current: CaseRelationGraph
) -> tuple[DFGCountChange, ...]:
    before, after = _counts(previous), _counts(current)
    return tuple(
        DFGCountChange(
            metric,
            key,
            before.get((metric, key), 0),
            after.get((metric, key), 0),
            after.get((metric, key), 0) - before.get((metric, key), 0),
        )
        for metric, key in sorted(before.keys() | after.keys())
        if before.get((metric, key), 0) != after.get((metric, key), 0)
    )


class RevisableCaseStream:
    """Single-writer exact engine; use ``expected_revision`` for corrections.

    New event IDs require no expected revision. Identical facts may be sent
    again without one. Changing or resurrecting an ID requires the current
    per-event revision. Moving an event to another case is rejected; delete and
    use a new identity if the source has changed the event's case identity.
    """

    def __init__(self, spec: RevisableCaseStreamSpec):
        if not isinstance(spec, RevisableCaseStreamSpec):
            raise TypeError("spec must be RevisableCaseStreamSpec")
        self._spec = spec
        self._events: dict[str, CaseEventRevision] = {}
        self._cases: set[str] = set()
        self._closed: set[str] = set()
        self._operations: list[CaseRevisionOperation] = []
        self._receipts: dict[str, CaseRevisionReceipt] = {}
        self._by_id: dict[str, CaseRevisionOperation] = {}
        self._offsets: dict[SourceOffset, CaseRevisionOperation] = {}
        self._high_water: dict[tuple[str, str], int] = {}
        initial = _digest({"spec": asdict(spec), "revision": 0})
        batch = self._batch(self._events, self._cases)
        self._result = self._make_result(
            0, initial, None, self._events, self._cases, self._closed, batch
        )

    @property
    def spec(self) -> RevisableCaseStreamSpec:
        """The ordering contract cannot change partway through a history."""
        return self._spec

    def _log(self, events: dict[str, CaseEventRevision], cases: set[str]) -> CaseLog:
        traces = []
        for case_id in sorted(cases):
            selected = [
                v.event
                for v in events.values()
                if v.case_id == case_id and v.event is not None
            ]
            key = "timestamp" if self.spec.order_policy == "timestamp" else "sequence"
            ordering = [getattr(event, key) for event in selected]
            if any(value is None for value in ordering):
                raise ValueError(f"{key}_required: order policy requires {key}")
            if self.spec.tie_policy == "reject" and len(set(ordering)) != len(ordering):
                raise ValueError(f"order_tie: duplicate {key} in case {case_id!r}")
            selected.sort(key=lambda event: (getattr(event, key), event.event_id))
            projected = []
            for event in selected:
                attrs = (CaseAttribute("concept:name", "string", event.activity),)
                if event.timestamp is not None:
                    attrs += (CaseAttribute("time:timestamp", "date", event.timestamp),)
                projected.append(CaseEvent(event.event_id, attrs))
            traces.append(CaseTrace(case_id, tuple(projected)))
        return CaseLog(tuple(traces))

    def _batch(self, events, cases):
        # Adjacent-pair work never exceeds retained event count. Raising this
        # batch budget from actual facts guarantees exact counts, not a prefix.
        result = discover_dfg(
            self._log(events, cases),
            RelationDiscoverySpec(max_event_pairs=max(1, len(events))),
        )
        if result.value is None or not result.value.complete:
            raise ValueError("retained facts are not eligible for exact batch DFG")
        return result

    def _make_result(self, revision, identity, previous, events, cases, closed, batch):
        old = None if previous is None else previous.value
        issues = (
            ()
            if cases == closed
            else (
                ComputeIssue(
                    "open_case_prefixes",
                    "DFG ends describe observed prefixes; open cases may receive revisions",
                ),
            )
        )
        value = RevisableCaseSnapshot(
            revision,
            identity,
            None if old is None else old.revision_id,
            None if previous is None else previous.computation_id,
            tuple(sorted(events.values(), key=lambda v: v.event_id)),
            tuple(sorted(cases)),
            tuple(sorted(closed)),
            batch.value,
            None if old is None else old.dfg,
            () if old is None else _changes(old.dfg, batch.value),
        )
        parents = (batch.computation_id,)
        if previous is not None:
            parents += (previous.computation_id,)
        return _derived_result(
            "pix.case_centric.revisable_stream.snapshot",
            identity,
            self.spec,
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
            value,
            issues,
            parent_computation_ids=parents,
        )

    def _apply(self, operation: CaseRevisionOperation) -> CaseRevisionReceipt:
        old_operation = self._by_id.get(operation.operation_id)
        if old_operation is not None:
            if old_operation != operation:
                raise ValueError("operation_conflict: operation_id payload differs")
            return replace(self._receipts[operation.operation_id], status="duplicate")
        offset = operation.source_offset
        if offset is not None:
            previous_offset = self._offsets.get(offset)
            if previous_offset is not None:
                # Operation ID is part of delivery identity. A new operation ID
                # cannot accidentally authorize reuse of a committed offset.
                raise ValueError("offset_conflict: source offset already committed")
            partition = (offset.source_id, offset.partition)
            if offset.offset < self._high_water.get(partition, -1):
                raise ValueError(
                    "offset_regression: unseen offset precedes committed maximum"
                )
        events, cases, closed = dict(self._events), set(self._cases), set(self._closed)
        event_revision = None
        changed = True
        if operation.action in ("upsert", "delete"):
            if operation.case_id in closed:
                raise ValueError("case_closed: reopen case before changing facts")
            old = events.get(operation.event_id)
            if old is not None and old.case_id != operation.case_id:
                raise ValueError(
                    "event_case_conflict: existing event belongs to another case"
                )
            if operation.expected_revision is not None and (
                old is None or old.revision != operation.expected_revision
            ):
                raise ValueError(
                    "revision_conflict: expected event revision does not match"
                )
            if operation.action == "upsert":
                if old is not None and old.event == operation.event:
                    changed = False
                    event_revision = old.revision
                else:
                    if old is not None and operation.expected_revision is None:
                        raise ValueError(
                            "event_conflict: correction requires expected_revision"
                        )
                    event_revision = 1 if old is None else old.revision + 1
                    events[operation.event_id] = CaseEventRevision(
                        operation.case_id,
                        operation.event_id,
                        event_revision,
                        operation.event,
                    )
                cases.add(operation.case_id)
            else:
                if old is None or old.event is None:
                    raise ValueError("event_missing: no live event to delete")
                event_revision = old.revision + 1
                events[operation.event_id] = replace(
                    old, revision=event_revision, event=None
                )
        elif operation.action == "close":
            changed = operation.case_id not in closed
            cases.add(operation.case_id)
            closed.add(operation.case_id)
        else:
            if operation.case_id not in cases:
                raise ValueError("case_missing: cannot reopen an unknown case")
            changed = operation.case_id in closed
            closed.discard(operation.case_id)
        batch = self._batch(events, cases)
        identity = _digest(
            {
                "parent": self._result.value.revision_id,
                "operation": _operation_data(operation),
            }
        )
        revision = self._result.value.revision + 1
        result = self._make_result(
            revision, identity, self._result, events, cases, closed, batch
        )
        receipt = CaseRevisionReceipt(
            "accepted" if changed else "unchanged",
            operation.operation_id,
            revision,
            identity,
            self._result.value.revision_id,
            event_revision,
            result.computation_id,
        )
        # All semantic validation and batch computation precede mutation.
        self._events, self._cases, self._closed, self._result = (
            events,
            cases,
            closed,
            result,
        )
        self._operations.append(operation)
        self._by_id[operation.operation_id] = operation
        self._receipts[operation.operation_id] = receipt
        if offset is not None:
            self._offsets[offset] = operation
            self._high_water[offset.source_id, offset.partition] = offset.offset
        return receipt

    def upsert_event(
        self,
        event: RetainedCaseEvent,
        *,
        operation_id: str,
        expected_revision: int | None = None,
        source_offset: SourceOffset | None = None,
    ) -> CaseRevisionReceipt:
        if not isinstance(event, RetainedCaseEvent):
            raise TypeError("event must be RetainedCaseEvent")
        return self._apply(
            CaseRevisionOperation(
                operation_id,
                "upsert",
                event.case_id,
                event.event_id,
                event,
                expected_revision,
                source_offset,
            )
        )

    def delete_event(
        self,
        case_id: str,
        event_id: str,
        *,
        operation_id: str,
        expected_revision: int,
        source_offset: SourceOffset | None = None,
    ) -> CaseRevisionReceipt:
        return self._apply(
            CaseRevisionOperation(
                operation_id,
                "delete",
                case_id,
                event_id,
                None,
                expected_revision,
                source_offset,
            )
        )

    def close_case(
        self,
        case_id: str,
        *,
        operation_id: str,
        source_offset: SourceOffset | None = None,
    ) -> CaseRevisionReceipt:
        return self._apply(
            CaseRevisionOperation(
                operation_id, "close", case_id, source_offset=source_offset
            )
        )

    def reopen_case(
        self,
        case_id: str,
        *,
        operation_id: str,
        source_offset: SourceOffset | None = None,
    ) -> CaseRevisionReceipt:
        return self._apply(
            CaseRevisionOperation(
                operation_id, "reopen", case_id, source_offset=source_offset
            )
        )

    def snapshot(self) -> ComputationResult[RevisableCaseSnapshot]:
        return self._result

    def to_case_log(self) -> CaseLog:
        """Current retained facts in the declared order, including empty cases."""
        return self._log(self._events, self._cases)

    def checkpoint(self) -> str:
        """Versioned JSON journal; digest detects corruption, not forgery.

        Restore verifies every operation by replay and checks the final result
        identity. Keep this document private if event facts are confidential.
        """
        body = {
            "format": "pix.revisable-case-stream",
            "version": "1.0.0",
            "spec": asdict(self.spec),
            "operations": [_operation_data(op) for op in self._operations],
            "revision_id": self._result.value.revision_id,
            "computation_id": self._result.computation_id,
        }
        return _json({**body, "digest": _digest(body)})

    @classmethod
    def restore(cls, checkpoint: str) -> RevisableCaseStream:
        if not isinstance(checkpoint, str):
            raise TypeError("checkpoint must be a JSON string")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError(f"duplicate JSON key: {key}")
                result[key] = value
            return result

        payload = json.loads(checkpoint, object_pairs_hook=unique)
        expected = {
            "format",
            "version",
            "spec",
            "operations",
            "revision_id",
            "computation_id",
            "digest",
        }
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ValueError("invalid checkpoint fields")
        digest = payload.pop("digest")
        if (
            payload["format"] != "pix.revisable-case-stream"
            or payload["version"] != "1.0.0"
        ):
            raise ValueError("unsupported checkpoint format or version")
        if _digest(payload) != digest:
            raise ValueError("checkpoint digest mismatch")
        if not isinstance(payload["spec"], dict) or not isinstance(
            payload["operations"], list
        ):
            raise ValueError("invalid checkpoint spec or operations")
        restored = cls(RevisableCaseStreamSpec(**payload["spec"]))
        operation_fields = set(CaseRevisionOperation.__dataclass_fields__)
        for raw in payload["operations"]:
            if not isinstance(raw, dict) or set(raw) != operation_fields:
                raise ValueError("invalid checkpoint operation fields")
            data = dict(raw)
            if data["event"] is not None:
                if not isinstance(data["event"], dict):
                    raise ValueError("invalid checkpoint event")
                event = dict(data["event"])
                if event.get("timestamp") is not None:
                    event["timestamp"] = datetime.fromisoformat(event["timestamp"])
                data["event"] = RetainedCaseEvent(**event)
            if data["source_offset"] is not None:
                if not isinstance(data["source_offset"], dict):
                    raise ValueError("invalid checkpoint source offset")
                data["source_offset"] = SourceOffset(**data["source_offset"])
            receipt = restored._apply(CaseRevisionOperation(**data))
            if receipt.status == "duplicate":
                raise ValueError(
                    "checkpoint journal must not contain duplicate operations"
                )
        if (
            restored._result.value.revision_id != payload["revision_id"]
            or restored._result.computation_id != payload["computation_id"]
        ):
            raise ValueError("checkpoint final state identity mismatch")
        return restored


RESULT_SCHEMAS = {
    "pix.case_centric.revisable_stream.snapshot": (
        "revisable-case-stream",
        RevisableCaseStreamSpec,
        RevisableCaseSnapshot,
    ),
}

__all__ = [
    "SourceOffset",
    "RevisableCaseStreamSpec",
    "RetainedCaseEvent",
    "CaseEventRevision",
    "DFGCountChange",
    "CaseRevisionOperation",
    "CaseRevisionReceipt",
    "RevisableCaseSnapshot",
    "RevisableCaseStream",
]
