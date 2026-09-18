"""Exact, retained-fact OCEL revisions with replayable checkpoints.

This is an in-process revision engine, not a bounded-memory online algorithm.
Each accepted correction validates the complete candidate and recomputes batch
executions. Declared schemas and O2O facts are fixed at construction. Import
provenance is excluded; canonical event/object attributes and qualified E2O/O2O
facts are retained. Source offsets are opaque, typed deduplication tokens, not
watermarks: integer 1 and string "1" are distinct and may arrive out of order.

Changing an existing entity, restoring a deleted ID, or deleting one requires the current stream revision
as a compare-and-swap token. Exact operation retries return their original receipt
even after later edits or closing. Neither checkpoint digests nor receipt hashes
are signatures; restore verifies internal replay consistency, not authorship.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from threading import RLock
from typing import Literal

from pix.compute._common import _derived_result
from pix.compute.context import ComputationContext
from pix.compute.executions import discover_executions
from pix.contracts.execution import ExecutionSet, ExecutionSpec
from pix.contracts.result import ComputationResult
from pix.ocel import E2O, O2O, OCEL, Event, Object
from pix.ocel.canonical.v1 import _event, _object, serialize_v1
from pix.ocel.model import (
    Attribute,
    EventAttr,
    EventType,
    ObjectAttr,
    ObjectType,
    ValueType,
)

OPERATOR_ID = "pix.object_centric.revisable_stream_snapshot"
CHECKPOINT_FORMAT = "pix.object-centric-revisions.v1"


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    value.encode("utf-8")


def _revision(value: object, *, optional: bool = False) -> None:
    if optional and value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError("expected_revision must be a nonnegative integer")


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _hash(value: object) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OCSourceOffset:
    source_id: str
    offset: str | int

    def __post_init__(self) -> None:
        _text(self.source_id, "source_id")
        if type(self.offset) not in (str, int):
            raise TypeError("offset must be a string or integer, not bool")
        if isinstance(self.offset, str):
            _text(self.offset, "offset")


@dataclass(frozen=True, slots=True)
class OCRevisionSpec:
    execution_spec: ExecutionSpec = ExecutionSpec("connected_components")

    def __post_init__(self) -> None:
        if not isinstance(self.execution_spec, ExecutionSpec):
            raise TypeError("execution_spec must be ExecutionSpec")


@dataclass(frozen=True, slots=True)
class OCExecutionChange:
    """Overlap evidence; merge/split apply only to connected components.

    The shared IDs identify surviving events connecting before/after memberships.
    Execution IDs are batch content identities and may change when unrelated facts
    change. Such ID-only changes are omitted from this evidence.
    """

    kind: Literal["merge", "split", "changed", "created", "deleted", "overlap"]
    before_execution_ids: tuple[str, ...]
    after_execution_ids: tuple[str, ...]
    shared_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in (
            "merge",
            "split",
            "changed",
            "created",
            "deleted",
            "overlap",
        ):
            raise ValueError("unknown execution change kind")
        for name in ("before_execution_ids", "after_execution_ids", "shared_event_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple")
            for value in values:
                _text(value, name)
            if len(values) != len(set(values)):
                raise ValueError(f"{name} must contain unique IDs")
        before, after = len(self.before_execution_ids), len(self.after_execution_ids)
        if not before and not after:
            raise ValueError("execution change requires a before or after membership")
        if self.kind == "merge" and not (before > 1 and after == 1):
            raise ValueError("merge requires multiple before executions and one after")
        if self.kind == "split" and not (before == 1 and after > 1):
            raise ValueError("split requires one before execution and multiple after")
        if self.kind == "created" and (before or not after or self.shared_event_ids):
            raise ValueError("created execution cannot have predecessor evidence")
        if self.kind == "deleted" and (after or not before or self.shared_event_ids):
            raise ValueError("deleted execution cannot have successor evidence")


@dataclass(frozen=True, slots=True)
class OCRevisionReceipt:
    revision: int
    operation_id: str
    source_offset: OCSourceOffset
    operation: str
    before_source_digest: str
    after_source_digest: str
    before_execution_computation_id: str
    after_execution_computation_id: str
    changes: tuple[OCExecutionChange, ...]
    closed: bool
    replayed: bool = False

    def __post_init__(self) -> None:
        _revision(self.revision)
        if self.revision == 0:
            raise ValueError("accepted receipt revision must be positive")
        for name in (
            "operation_id",
            "before_source_digest",
            "after_source_digest",
            "before_execution_computation_id",
            "after_execution_computation_id",
        ):
            _text(getattr(self, name), name)
        if self.operation not in (
            "upsert_event",
            "delete_event",
            "upsert_object",
            "delete_object",
            "close",
            "reopen",
        ):
            raise ValueError("unknown receipt operation")
        if not isinstance(self.source_offset, OCSourceOffset):
            raise TypeError("receipt source_offset must be OCSourceOffset")
        if not isinstance(self.changes, tuple) or not all(
            isinstance(change, OCExecutionChange) for change in self.changes
        ):
            raise TypeError("changes must be a tuple of OCExecutionChange")
        if type(self.closed) is not bool or type(self.replayed) is not bool:
            raise TypeError("closed and replayed must be booleans")


@dataclass(frozen=True, slots=True)
class OCRevisionSnapshotRequest:
    parameters: OCRevisionSpec
    revision: int
    closed: bool
    journal_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, OCRevisionSpec):
            raise TypeError("parameters must be OCRevisionSpec")
        _revision(self.revision)
        if type(self.closed) is not bool:
            raise TypeError("closed must be bool")
        if not isinstance(self.journal_digest, str) or len(self.journal_digest) != 64:
            raise ValueError("journal_digest must be a SHA-256 hexadecimal digest")
        if any(c not in "0123456789abcdef" for c in self.journal_digest):
            raise ValueError("journal_digest must be lowercase hexadecimal")


@dataclass(frozen=True, slots=True)
class OCRevisionSnapshot:
    canonical_facts_json: str
    executions: ExecutionSet
    revision: int
    closed: bool
    last_receipt: OCRevisionReceipt | None

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_facts_json, str):
            raise TypeError("canonical_facts_json must be JSON text")
        try:
            facts = _decode_log(
                json.loads(self.canonical_facts_json, object_pairs_hook=_unique_members)
            )
        except (KeyError, TypeError, AttributeError, OverflowError) as error:
            raise ValueError("malformed snapshot canonical facts") from error
        if serialize_v1(facts).decode("utf-8") != self.canonical_facts_json:
            raise ValueError("snapshot facts must use deterministic canonical JSON")
        if not isinstance(self.executions, ExecutionSet):
            raise TypeError("executions must be ExecutionSet")
        _revision(self.revision)
        if type(self.closed) is not bool:
            raise TypeError("closed must be bool")
        if self.revision == 0:
            if self.last_receipt is not None or self.closed:
                raise ValueError("initial snapshot must be open without a receipt")
        elif not isinstance(self.last_receipt, OCRevisionReceipt):
            raise TypeError("revised snapshot requires its last receipt")
        elif (
            self.last_receipt.revision != self.revision
            or self.last_receipt.closed != self.closed
        ):
            raise ValueError(
                "last receipt must match the snapshot revision and lifecycle"
            )
        if self.last_receipt is not None and (
            self.last_receipt.after_source_digest
            != ComputationContext(facts).source_digest
        ):
            raise ValueError("last receipt source identity differs from snapshot facts")

    @property
    def log(self) -> OCEL:
        """Lossless typed facts, including time-valued attributes."""
        return _decode_log(json.loads(self.canonical_facts_json))


@dataclass(frozen=True, slots=True)
class _Operation:
    operation_id: str
    source_offset: OCSourceOffset
    kind: str
    expected_revision: int | None
    event: Event | None = None
    relations: tuple[E2O, ...] = ()
    object: Object | None = None
    entity_id: str | None = None


def _operation_document(op: _Operation) -> dict:
    return {
        "operation_id": op.operation_id,
        "source_offset": {
            "source_id": op.source_offset.source_id,
            "offset": op.source_offset.offset,
        },
        "kind": op.kind,
        "expected_revision": op.expected_revision,
        "event": None if op.event is None else _event(op.event),
        "relations": [
            {"event": r.event, "object": r.object, "qualifier": r.qualifier}
            for r in op.relations
        ],
        "object": None if op.object is None else _object(op.object),
        "entity_id": op.entity_id,
    }


def _execution_changes(
    before: ExecutionSet,
    after: ExecutionSet,
    spec: ExecutionSpec,
) -> tuple[OCExecutionChange, ...]:
    old, new = before.executions, after.executions
    old_ids = [{e.id for e in row.events} for row in old]
    new_ids = [{e.id for e in row.events} for row in new]
    # Empty leading-object executions still match by their explicit anchor.
    neighbors = {
        ("b", i): {
            ("a", j)
            for j, other in enumerate(new)
            if old_ids[i] & new_ids[j]
            or (
                row.leading_object_id is not None
                and row.leading_object_id == other.leading_object_id
            )
        }
        for i, row in enumerate(old)
    }
    for j in range(len(new)):
        neighbors[("a", j)] = {
            ("b", i) for i in range(len(old)) if ("a", j) in neighbors[("b", i)]
        }
    changes = []
    pending = set(neighbors)
    while pending:
        start = min(pending)
        seen, frontier = set(), {start}
        while frontier:
            seen.update(frontier)
            frontier = set().union(*(neighbors[n] for n in frontier)) - seen
        pending -= seen
        bi = sorted(i for side, i in seen if side == "b")
        ai = sorted(i for side, i in seen if side == "a")
        if {replace(old[i], execution_id="comparison") for i in bi} == {
            replace(new[i], execution_id="comparison") for i in ai
        }:
            continue
        kind = "changed"
        if not bi:
            kind = "created"
        elif not ai:
            kind = "deleted"
        elif spec.method != "connected_components":
            kind = "overlap"
        elif len(bi) > 1 and len(ai) == 1:
            kind = "merge"
        elif len(bi) == 1 and len(ai) > 1:
            kind = "split"
        elif len(bi) > 1 and len(ai) > 1:
            kind = "overlap"
        shared = set().union(*(old_ids[i] for i in bi)) & set().union(
            *(new_ids[i] for i in ai)
        )
        changes.append(
            OCExecutionChange(
                kind,
                tuple(sorted(old[i].execution_id for i in bi)),
                tuple(sorted(new[i].execution_id for i in ai)),
                tuple(sorted(shared)),
            )
        )
    return tuple(
        sorted(
            changes,
            key=lambda row: (
                row.before_execution_ids,
                row.after_execution_ids,
                row.kind,
            ),
        )
    )


class OCRevisableStream:
    """Single-process atomic revision store with full history retention.

    Snapshots always use the same batch ``discover_executions`` definition.
    There is no memory cap, eviction, incremental-time guarantee, transport,
    authentication, or process-crash durable storage. Checkpoint text can be
    published by the caller using their own durability policy.
    """

    def __init__(self, log: OCEL, spec: OCRevisionSpec = OCRevisionSpec()) -> None:
        if not isinstance(spec, OCRevisionSpec):
            raise TypeError("spec must be OCRevisionSpec")
        if not isinstance(log, OCEL):
            raise TypeError("log must be OCEL")
        self._context = ComputationContext(replace(log, import_info=None))
        self._base = self._context.log
        self._base_digest = self._context.source_digest
        self._spec = spec
        self._executions = discover_executions(self._context, spec.execution_spec)
        self._require_executions(self._executions)
        self._seen_event_ids = set(self._context.events_by_id)
        self._seen_object_ids = set(self._context.objects_by_id)
        self._closed = False
        self._journal: list[_Operation] = []
        self._receipts: list[OCRevisionReceipt] = []
        self._by_id: dict[str, int] = {}
        self._by_offset: dict[OCSourceOffset, int] = {}
        self._lock = RLock()

    @property
    def revision(self) -> int:
        with self._lock:
            return len(self._journal)

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def log(self) -> OCEL:
        with self._lock:
            return self._context.log

    def upsert_event(
        self,
        event: Event,
        relations: tuple[E2O, ...],
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int | None = None,
    ) -> OCRevisionReceipt:
        """Insert/correct an event; ``relations`` replaces ALL its E2O facts."""
        if not isinstance(event, Event):
            raise TypeError("event must be Event")
        if not isinstance(relations, tuple) or not all(
            isinstance(r, E2O) for r in relations
        ):
            raise TypeError("relations must be a tuple of E2O")
        if any(r.event != event.id for r in relations):
            raise ValueError("every relation must reference the upserted event")
        # UTC/attribute and relation order normalization also normalizes retries.
        normalized = replace(
            event,
            attributes=tuple(
                sorted(
                    event.attributes,
                    key=lambda a: a.name,
                )
            ),
        )
        ordered = tuple(
            sorted(relations, key=lambda r: (r.event, r.object, r.qualifier))
        )
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "upsert_event",
                expected_revision,
                event=normalized,
                relations=ordered,
            )
        )

    def delete_event(
        self,
        event_id: str,
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int,
    ) -> OCRevisionReceipt:
        """Delete one event and all its E2O facts, without deleting objects."""
        _text(event_id, "event_id")
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "delete_event",
                expected_revision,
                entity_id=event_id,
            )
        )

    def upsert_object(
        self,
        obj: Object,
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int | None = None,
    ) -> OCRevisionReceipt:
        if not isinstance(obj, Object):
            raise TypeError("obj must be Object")
        obj = replace(
            obj,
            attributes=tuple(
                sorted(
                    obj.attributes,
                    key=lambda a: (a.name, a.time),
                )
            ),
        )
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "upsert_object",
                expected_revision,
                object=obj,
            )
        )

    def delete_object(
        self,
        object_id: str,
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int,
    ) -> OCRevisionReceipt:
        """Delete only an unreferenced object; E2O and O2O references reject."""
        _text(object_id, "object_id")
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "delete_object",
                expected_revision,
                entity_id=object_id,
            )
        )

    def close(
        self,
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int,
    ) -> OCRevisionReceipt:
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "close",
                expected_revision,
            )
        )

    def reopen(
        self,
        *,
        operation_id: str,
        source_offset: OCSourceOffset,
        expected_revision: int,
    ) -> OCRevisionReceipt:
        return self._apply(
            _Operation(
                operation_id,
                source_offset,
                "reopen",
                expected_revision,
            )
        )

    def _apply(self, op: _Operation) -> OCRevisionReceipt:
        _text(op.operation_id, "operation_id")
        if not isinstance(op.source_offset, OCSourceOffset):
            raise TypeError("source_offset must be OCSourceOffset")
        _revision(op.expected_revision, optional=True)
        with self._lock:
            known_id = self._by_id.get(op.operation_id)
            known_offset = self._by_offset.get(op.source_offset)
            if known_id is not None or known_offset is not None:
                if known_id != known_offset or known_id is None:
                    raise ValueError(
                        "operation ID or source offset conflicts with history"
                    )
                if _operation_document(op) != _operation_document(
                    self._journal[known_id]
                ):
                    raise ValueError("retry payload conflicts with accepted operation")
                return replace(self._receipts[known_id], replayed=True)
            if (
                op.expected_revision is not None
                and op.expected_revision != self.revision
            ):
                raise ValueError("stale expected_revision")
            if self._closed and op.kind != "reopen":
                raise ValueError("stream is closed; explicitly reopen before editing")
            log = self._context.log
            next_closed = self._closed
            if op.kind == "upsert_event":
                previous = self._context.events_by_id.get(op.event.id)
                if previous is None and op.event.id in self._seen_event_ids:
                    self._require_current(op)
                old_relations = tuple(r for r in log.e2o if r.event == op.event.id)
                changed = previous is not None and (
                    _event(previous) != _event(op.event)
                    or old_relations != op.relations
                )
                if changed and op.expected_revision is None:
                    raise ValueError("event correction requires expected_revision")
                candidate = replace(
                    log,
                    events=tuple(e for e in log.events if e.id != op.event.id)
                    + (op.event,),
                    e2o=tuple(r for r in log.e2o if r.event != op.event.id)
                    + op.relations,
                )
            elif op.kind == "delete_event":
                self._require_current(op)
                if op.entity_id not in self._context.events_by_id:
                    raise ValueError("event to delete does not exist")
                candidate = replace(
                    log,
                    events=tuple(e for e in log.events if e.id != op.entity_id),
                    e2o=tuple(r for r in log.e2o if r.event != op.entity_id),
                )
            elif op.kind == "upsert_object":
                previous = self._context.objects_by_id.get(op.object.id)
                if previous is None and op.object.id in self._seen_object_ids:
                    self._require_current(op)
                if previous is not None and _object(previous) != _object(op.object):
                    self._require_current(op)
                candidate = replace(
                    log,
                    objects=tuple(o for o in log.objects if o.id != op.object.id)
                    + (op.object,),
                )
            elif op.kind == "delete_object":
                self._require_current(op)
                if op.entity_id not in self._context.objects_by_id:
                    raise ValueError("object to delete does not exist")
                if any(r.object == op.entity_id for r in log.e2o) or any(
                    op.entity_id in (r.source, r.target) for r in log.o2o
                ):
                    raise ValueError("cannot delete a referenced object")
                candidate = replace(
                    log,
                    objects=tuple(o for o in log.objects if o.id != op.entity_id),
                )
            elif op.kind in ("close", "reopen"):
                self._require_current(op)
                next_closed = op.kind == "close"
                if next_closed == self._closed:
                    raise ValueError("requested lifecycle state is already active")
                candidate = log
            else:
                raise ValueError("unknown revision operation")
            # Prepare everything before committing any state or deduplication token.
            context = ComputationContext(candidate)
            executions = discover_executions(context, self._spec.execution_spec)
            self._require_executions(executions)
            changes = _execution_changes(
                self._executions.value,
                executions.value,
                self._spec.execution_spec,
            )
            receipt = OCRevisionReceipt(
                self.revision + 1,
                op.operation_id,
                op.source_offset,
                op.kind,
                self._context.source_digest,
                context.source_digest,
                self._executions.computation_id,
                executions.computation_id,
                changes,
                next_closed,
            )
            index = len(self._journal)
            self._context, self._executions, self._closed = (
                context,
                executions,
                next_closed,
            )
            self._journal.append(op)
            self._receipts.append(receipt)
            self._by_id[op.operation_id] = index
            self._by_offset[op.source_offset] = index
            if op.event is not None:
                self._seen_event_ids.add(op.event.id)
            if op.object is not None:
                self._seen_object_ids.add(op.object.id)
            return receipt

    @staticmethod
    def _require_executions(result: ComputationResult[ExecutionSet]) -> None:
        if result.value is None:
            detail = "; ".join(
                f"{issue.code}: {issue.message}" for issue in result.issues
            )
            raise ValueError(
                f"execution policy is unavailable for retained facts: {detail}"
            )

    def _require_current(self, op: _Operation) -> None:
        if op.expected_revision is None or op.expected_revision != self.revision:
            raise ValueError("this operation requires the current expected_revision")

    def snapshot(self) -> ComputationResult[OCRevisionSnapshot]:
        with self._lock:
            request = OCRevisionSnapshotRequest(
                self._spec,
                self.revision,
                self._closed,
                _hash(
                    {
                        "base_source_digest": self._base_digest,
                        "operations": [_operation_document(op) for op in self._journal],
                    }
                ),
            )
            return _derived_result(
                OPERATOR_ID,
                self._context.source_digest,
                request,
                self._executions.status,
                OCRevisionSnapshot(
                    serialize_v1(self._context.log).decode("utf-8"),
                    self._executions.value,
                    self.revision,
                    self._closed,
                    self._receipts[-1] if self._receipts else None,
                ),
                self._executions.issues,
                parent_computation_ids=(self._executions.computation_id,),
            )

    def checkpoint(self) -> str:
        """Return deterministic JSON with all accepted operations and base facts."""
        with self._lock:
            from dataclasses import asdict

            body = {
                "format": CHECKPOINT_FORMAT,
                "base": json.loads(serialize_v1(self._base)),
                "spec": asdict(self._spec),
                "operations": [_operation_document(op) for op in self._journal],
                "state": {
                    "revision": self.revision,
                    "closed": self._closed,
                    "source_digest": self._context.source_digest,
                    "snapshot_identity": self.snapshot().computation_id,
                    "facts": json.loads(serialize_v1(self._context.log)),
                },
            }
            return _json({"body": body, "sha256": _hash(body)})

    @classmethod
    def restore(cls, checkpoint: str | bytes) -> OCRevisableStream:
        """Reject corruption, invalid edits, and final states inconsistent with replay."""
        if not isinstance(checkpoint, (str, bytes)):
            raise TypeError("checkpoint must be JSON text or bytes")
        try:
            payload = json.loads(
                checkpoint,
                object_pairs_hook=_unique_members,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid JSON constant {value}")
                ),
            )
            if set(payload) != {"body", "sha256"}:
                raise ValueError("invalid checkpoint envelope")
            body = payload["body"]
            if payload["sha256"] != _hash(body) or body["format"] != CHECKPOINT_FORMAT:
                raise ValueError("checkpoint format or digest mismatch")
            config = dict(body["spec"]["execution_spec"])
            for name in ("object_types", "qualifiers"):
                if config[name] is not None:
                    config[name] = tuple(config[name])
            restored = cls(
                _decode_log(body["base"]), OCRevisionSpec(ExecutionSpec(**config))
            )
            for item in body["operations"]:
                offset = OCSourceOffset(**item["source_offset"])
                common = {
                    "operation_id": item["operation_id"],
                    "source_offset": offset,
                    "expected_revision": item["expected_revision"],
                }
                kind = item["kind"]
                if kind == "upsert_event":
                    restored.upsert_event(
                        _decode_event(item["event"]),
                        tuple(E2O(**r) for r in item["relations"]),
                        **common,
                    )
                elif kind == "upsert_object":
                    restored.upsert_object(_decode_object(item["object"]), **common)
                elif kind == "delete_event":
                    restored.delete_event(item["entity_id"], **common)
                elif kind == "delete_object":
                    restored.delete_object(item["entity_id"], **common)
                elif kind in ("close", "reopen"):
                    getattr(restored, kind)(**common)
                else:
                    raise ValueError("unknown checkpoint operation")
            # Exact regenerated document comparison catches unknown fields,
            # normalized/coerced payloads, duplicate journal retries and state lies.
            if restored.checkpoint() != _json(payload):
                raise ValueError("checkpoint does not match verified replay")
            return restored
        except (KeyError, TypeError, AttributeError, OverflowError) as error:
            raise ValueError("malformed OCEL revision checkpoint") from error


def _unique_members(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate checkpoint key: {key}")
        result[key] = value
    return result


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _value(document: dict):
    kind, value = document["type"], document["value"]
    if kind == "time":
        return _time(value)
    if kind == "integer":
        return int(value)
    if kind == "float":
        return float.fromhex(value)
    if kind == "boolean" and type(value) is bool:
        return value
    if kind == "string" and isinstance(value, str):
        return value
    raise ValueError("invalid checkpoint attribute value")


def _decode_event(row: dict) -> Event:
    return Event(
        row["id"],
        row["type"],
        _time(row["time"]),
        tuple(EventAttr(a["name"], _value(a["value"])) for a in row["attributes"]),
    )


def _decode_object(row: dict) -> Object:
    return Object(
        row["id"],
        row["type"],
        tuple(
            ObjectAttr(a["name"], _value(a["value"]), _time(a["time"]))
            for a in row["attributes"]
        ),
    )


def _decode_log(row: dict) -> OCEL:
    def types(key, constructor):
        return tuple(
            constructor(
                r["name"],
                tuple(
                    Attribute(a["name"], ValueType(a["type"])) for a in r["attributes"]
                ),
            )
            for r in row[key]
        )

    log = OCEL(
        types("eventTypes", EventType),
        types("objectTypes", ObjectType),
        tuple(_decode_event(r) for r in row["events"]),
        tuple(_decode_object(r) for r in row["objects"]),
        tuple(E2O(**r) for r in row["e2o"]),
        tuple(O2O(**r) for r in row["o2o"]),
    )
    if serialize_v1(log).decode("utf-8") != _json(row):
        raise ValueError("checkpoint facts do not use canonical representation")
    return log


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "object-revision-snapshot",
        OCRevisionSnapshotRequest,
        OCRevisionSnapshot,
    ),
}

__all__ = (
    "OCSourceOffset",
    "OCRevisionSpec",
    "OCExecutionChange",
    "OCRevisionReceipt",
    "OCRevisionSnapshotRequest",
    "OCRevisionSnapshot",
    "OCRevisableStream",
    "OPERATOR_ID",
    "RESULT_SCHEMAS",
)
