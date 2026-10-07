"""Explicit source projections and deterministic delivery to native case streams.

Ordering is a declared projection convention, never inferred causality. Shared
OCEL events produce one occurrence per selected object, with original event IDs
and all selected qualifiers retained in provenance. Delivery is a pure batch
calculation: a failed batch does not mutate a caller's live monitor.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from hashlib import sha256
from typing import ClassVar

from pix.case_centric.streaming import (
    CaseStream,
    StreamEvent,
    StreamingCheckpoint,
    StreamingSpec,
)
from pix.compute._common import _derived_result
from pix.compute.context import ComputationContext, InvalidOCELInput
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import E2OEvidence, TraceSpec
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseLog, case_traces
from pix.ocel import OCEL


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    value.encode("utf-8")


def _common_spec(spec):
    _text(spec.namespace, "namespace")
    if type(spec.close_cases) is not bool:
        raise TypeError("close_cases must be bool")
    if type(spec.max_events) is not int or spec.max_events < 1:
        raise ValueError("max_events must be a positive integer")


def _id(kind, *parts):
    return (
        "pix.stream."
        + kind
        + ":"
        + json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    )


@dataclass(frozen=True, slots=True)
class CaseLogStreamSpec:
    namespace: str
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    close_cases: bool = False
    max_events: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _common_spec(self)
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class RecordStreamSpec:
    namespace: str
    order_policy: str = "sequence"
    tie_policy: str = "reject"
    duplicate_policy: str = "reject"
    close_cases: bool = False
    case_id_key: str = "case_id"
    event_id_key: str = "event_id"
    activity_key: str = "activity"
    timestamp_key: str = "timestamp"
    sequence_key: str = "sequence"
    end_key: str = "end"
    start_sequences: tuple[tuple[str, int], ...] = ()
    max_events: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _common_spec(self)
        if self.order_policy not in ("sequence", "source", "timestamp"):
            raise ValueError("order_policy must be sequence, source or timestamp")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if self.duplicate_policy not in ("reject", "idempotent"):
            raise ValueError("duplicate_policy must be reject or idempotent")
        keys = tuple(
            getattr(self, name)
            for name in (
                "case_id_key",
                "event_id_key",
                "activity_key",
                "timestamp_key",
                "sequence_key",
                "end_key",
            )
        )
        for key in keys:
            _text(key, "record mapping key")
        if len(set(keys)) != len(keys):
            raise ValueError("record mapping keys must be distinct")
        if not isinstance(self.start_sequences, tuple) or any(
            not isinstance(p, tuple)
            or len(p) != 2
            or not isinstance(p[0], str)
            or not p[0].strip()
            or type(p[1]) is not int
            or p[1] < 0
            for p in self.start_sequences
        ):
            raise ValueError(
                "start_sequences must contain (case ID, nonnegative integer) pairs"
            )
        if len(dict(self.start_sequences)) != len(self.start_sequences):
            raise ValueError("duplicate start sequence case")


@dataclass(frozen=True, slots=True)
class OCELStreamSpec:
    namespace: str
    projections: tuple[TraceSpec, ...]
    close_cases: bool = False
    max_events: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _common_spec(self)
        if (
            not isinstance(self.projections, tuple)
            or not self.projections
            or not all(isinstance(p, TraceSpec) for p in self.projections)
        ):
            raise TypeError(
                "projections must explicitly select one or more TraceSpec values"
            )
        if len({p.object_type for p in self.projections}) != len(self.projections):
            raise ValueError(
                "select each object type only once; qualifiers belong to its TraceSpec"
            )


@dataclass(frozen=True, slots=True)
class StreamRecord:
    case_id: str
    event_id: str
    activity: str | None
    timestamp: datetime | None = None
    sequence: int | None = None
    end: bool = False

    def __post_init__(self):
        # Sequence assignment belongs to the chosen adapter ordering policy.
        event = StreamEvent(
            self.case_id,
            self.event_id,
            0 if self.sequence is None else self.sequence,
            self.activity,
            self.timestamp,
            self.end,
        )
        object.__setattr__(self, "timestamp", event.timestamp)


@dataclass(frozen=True, slots=True)
class StreamCaseAlias:
    case_id: str
    source_case_id: str
    object_type: str | None
    event_count: int
    closed: bool
    first_sequence: int = 0


@dataclass(frozen=True, slots=True)
class StreamOccurrence:
    case_id: str
    event_id: str
    source_case_id: str
    source_event_id: str | None
    source_position: int | None
    relations: tuple[E2OEvidence, ...] = ()
    synthetic_end: bool = False


@dataclass(frozen=True, slots=True)
class StreamDuplicate:
    source_case_id: str
    source_event_id: str
    retained_position: int
    duplicate_position: int


@dataclass(frozen=True, slots=True)
class StreamSourceAudit:
    source_kind: str
    input_event_records: int
    unique_source_events: int
    selected_unique_source_events: int
    projected_event_occurrences: int
    input_relations: int
    selected_relations: int
    emitted_cases: int
    empty_cases: int
    end_markers: int
    duplicate_records: int
    excluded_source_events: int
    excluded_objects: int


@dataclass(frozen=True, slots=True)
class StreamBatch:
    namespace: str
    events: tuple[StreamEvent, ...]
    occurrences: tuple[StreamOccurrence, ...]
    cases: tuple[StreamCaseAlias, ...]
    duplicates: tuple[StreamDuplicate, ...]
    audit: StreamSourceAudit
    ordering: str


def _batch(
    namespace, kind, traces, close_cases, *, duplicates=(), start_sequences=None
):
    """traces: (source case, type, [(id,activity,time,position,E2O,end),...])."""
    events, provenance, aliases = [], [], []
    for source_case, object_type, rows in traces:
        case_id = _id("case", namespace, kind, object_type, source_case)
        start = 0 if start_sequences is None else start_sequences.get(source_case, 0)
        count, ended = 0, False
        for sequence, (
            source_event,
            activity,
            timestamp,
            position,
            relations,
            end,
        ) in enumerate(rows):
            occurrence_id = _id(
                "occurrence", namespace, kind, object_type, source_case, source_event
            )
            events.append(
                StreamEvent(
                    case_id, occurrence_id, start + sequence, activity, timestamp, end
                )
            )
            provenance.append(
                StreamOccurrence(
                    case_id,
                    occurrence_id,
                    source_case,
                    source_event,
                    position,
                    relations,
                )
            )
            count += not end
            ended = end
        if close_cases and not ended:
            marker_id = _id("end", namespace, kind, object_type, source_case)
            events.append(StreamEvent(case_id, marker_id, start + len(rows), end=True))
            provenance.append(
                StreamOccurrence(
                    case_id, marker_id, source_case, None, None, synthetic_end=True
                )
            )
            ended = True
        aliases.append(
            StreamCaseAlias(case_id, source_case, object_type, count, ended, start)
        )
    return tuple(events), tuple(provenance), tuple(aliases), tuple(duplicates)


def _source_issues(cases):
    if any(c.event_count == 0 and not c.closed for c in cases):
        return (
            ComputeIssue(
                "empty_open_cases",
                "Empty open cases are represented in batch provenance but cannot instantiate CaseStream without an event or explicit end marker",
            ),
        )
    return ()


def case_log_stream(
    log: CaseLog, spec: CaseLogStreamSpec
) -> ComputationResult[StreamBatch]:
    if not isinstance(log, CaseLog) or not isinstance(spec, CaseLogStreamSpec):
        raise TypeError("expected CaseLog and CaseLogStreamSpec")
    mapped = case_traces(log, spec.trace_spec)
    source = mapped.source_digest
    parents = (mapped.computation_id,) if mapped.computation_id else ()
    if mapped.value is None:
        return _derived_result(
            "pix.case_centric.stream_adapters.case_log",
            source,
            spec,
            mapped.status,
            None,
            mapped.issues,
            parent_computation_ids=parents,
        )
    total = sum(len(trace.events) for trace in mapped.value.traces)
    if total + (len(mapped.value.traces) if spec.close_cases else 0) > spec.max_events:
        return _derived_result(
            "pix.case_centric.stream_adapters.case_log",
            source,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "stream_batch_limit",
                    "Projected operations exceed max_events; no truncated batch is emitted",
                ),
            ),
            parent_computation_ids=parents,
        )
    position, traces = 0, []
    for trace in mapped.value.traces:
        rows = []
        for event in trace.events:
            rows.append(
                (
                    event.event_id,
                    event.activity,
                    event.time,
                    position,
                    event.relations,
                    False,
                )
            )
            position += 1
        traces.append((trace.object_id, trace.object_type, tuple(rows)))
    events, occurrences, aliases, duplicates = _batch(
        spec.namespace, "case_log", traces, spec.close_cases
    )
    audit = StreamSourceAudit(
        "case_log",
        total,
        total,
        total,
        total,
        0,
        0,
        len(aliases),
        sum(c.event_count == 0 for c in aliases),
        sum(e.end for e in events),
        0,
        0,
        0,
    )
    value = StreamBatch(
        spec.namespace,
        events,
        occurrences,
        aliases,
        duplicates,
        audit,
        "case groups in source trace order; within each case source event order; delivery order is not cross-case causality",
    )
    return _derived_result(
        "pix.case_centric.stream_adapters.case_log",
        source,
        spec,
        ComputeStatus.COMPUTED,
        value,
        (*mapped.issues, *_source_issues(aliases)),
        parent_computation_ids=parents,
    )


def _source_fact(value):
    """Fingerprint every input column, preserving scalar types and nested facts."""
    if value is None:
        return ["null"]
    if isinstance(value, datetime):
        return ["datetime", value.isoformat(timespec="microseconds")]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", hex(value)]
    if type(value) is float:
        return ["float", value.hex()]
    if isinstance(value, str):
        return ["str", value]
    if isinstance(value, Mapping):
        if not all(isinstance(k, str) for k in value):
            raise TypeError("record source mapping keys must be strings")
        return ["mapping", [[k, _source_fact(value[k])] for k in sorted(value)]]
    if isinstance(value, (tuple, list)):
        return [
            "tuple" if isinstance(value, tuple) else "list",
            [_source_fact(v) for v in value],
        ]
    if is_dataclass(value) and not isinstance(value, type):
        return [
            "dataclass",
            type(value).__module__ + "." + type(value).__qualname__,
            [[f.name, _source_fact(getattr(value, f.name))] for f in fields(value)],
        ]
    raise TypeError(
        f"unsupported source fact type {type(value).__name__}; normalize explicitly before adapting"
    )


def records_stream(
    records: Iterable[StreamRecord | Mapping] | object, spec: RecordStreamSpec
) -> ComputationResult[StreamBatch]:
    """Accept typed records or `to_dict(orient='records')` providers without pandas.

    `sequence` sorts by declared per-case positions, `source` explicitly accepts
    row order, and `timestamp` requires aware times plus an explicit tie policy.
    No row order is silently interpreted as causal order.
    """
    if not isinstance(spec, RecordStreamSpec):
        raise TypeError("spec must be RecordStreamSpec")
    if hasattr(records, "to_dict") and not isinstance(records, Mapping):
        records = records.to_dict(orient="records")
    if isinstance(records, (str, bytes, Mapping)) or not isinstance(records, Iterable):
        raise TypeError("records must be an iterable of typed records or mappings")
    raw, facts = [], []
    try:
        for index, row in enumerate(records):
            if index >= spec.max_events:
                return _derived_result(
                    "pix.case_centric.stream_adapters.records",
                    None,
                    spec,
                    ComputeStatus.UNAVAILABLE,
                    None,
                    (
                        ComputeIssue(
                            "record_source_not_fully_consumed",
                            "Input exceeds max_events; no full source identity or truncated batch is claimed",
                        ),
                    ),
                )
            facts.append(_source_fact(row))
            # Iterators may reuse one mutable row dictionary between yields.
            # Snapshot its selected scalar fields before requesting the next row.
            raw.append(dict(row) if isinstance(row, Mapping) else row)
    except (ValueError, TypeError) as exc:
        return _derived_result(
            "pix.case_centric.stream_adapters.records",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue("unsupported_record_source", str(exc)),),
        )
    encoded = json.dumps(
        facts, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    source = "pix.stream.record-source.v1:sha256:" + sha256(encoded).hexdigest()
    try:
        grouped, first_rows, duplicates, input_events = {}, {}, [], 0
        for index, row in enumerate(raw):
            if isinstance(row, StreamRecord):
                record = row
            elif isinstance(row, Mapping):
                record = StreamRecord(
                    row[spec.case_id_key],
                    row[spec.event_id_key],
                    row.get(spec.activity_key),
                    row.get(spec.timestamp_key),
                    row.get(spec.sequence_key),
                    row.get(spec.end_key, False),
                )
            else:
                raise TypeError("each record must be StreamRecord or a mapping")
            input_events += not record.end
            key = (record.case_id, record.event_id)
            if key in first_rows:
                earlier, earlier_index = first_rows[key]
                if earlier != record or facts[earlier_index] != facts[index]:
                    raise ValueError(
                        "duplicate_conflict: same case/event ID has different source content"
                    )
                if spec.duplicate_policy == "reject":
                    raise ValueError(
                        "duplicate_record: choose idempotent policy to collapse identical retransmissions"
                    )
                duplicates.append(
                    StreamDuplicate(
                        record.case_id, record.event_id, earlier_index, index
                    )
                )
                continue
            first_rows[key] = (record, index)
            grouped.setdefault(record.case_id, []).append((record, index))
        traces, issues, starts = [], [], dict(spec.start_sequences)
        if not set(starts) <= set(grouped):
            raise ValueError("start_sequences references a case absent from the batch")
        for case_id, rows in grouped.items():
            if spec.order_policy == "sequence":
                if any(r.sequence is None for r, _ in rows):
                    raise ValueError(
                        "explicit_sequence_required: select source or timestamp policy if sequence evidence is absent"
                    )
                rows = sorted(rows, key=lambda r: r[0].sequence)
                first_sequence = rows[0][0].sequence
                if tuple(r.sequence for r, _ in rows) != tuple(
                    range(first_sequence, first_sequence + len(rows))
                ):
                    raise ValueError(
                        "invalid_sequence: unique contiguous per-case positions are required"
                    )
                if case_id in starts and starts[case_id] != first_sequence:
                    raise ValueError(
                        "declared start sequence conflicts with source sequence"
                    )
                starts[case_id] = first_sequence
            elif spec.order_policy == "timestamp":
                normal, ends = (
                    [item for item in rows if not item[0].end],
                    [item for item in rows if item[0].end],
                )
                if any(r.timestamp is None for r, _ in normal):
                    raise ValueError(
                        "timestamp_required: timestamp ordering requires aware times"
                    )
                normal.sort(key=lambda r: (r[0].timestamp, r[0].event_id))
                for left, right in zip(normal, normal[1:]):
                    if left[0].timestamp == right[0].timestamp:
                        if spec.tie_policy == "reject":
                            raise ValueError(
                                "ambiguous_timestamp_order: choose event_id tie policy explicitly"
                            )
                        issues.append(
                            ComputeIssue(
                                "timestamp_tie_broken",
                                "Equal times use event ID lexical order, not causal evidence",
                                (case_id, left[0].event_id, right[0].event_id),
                            )
                        )
                if normal and any(
                    r.timestamp is not None and r.timestamp < normal[-1][0].timestamp
                    for r, _ in ends
                ):
                    raise ValueError(
                        "end_before_event: end timestamp precedes the last case event"
                    )
                rows = normal + ends
            if any(r.end for r, _ in rows[:-1]):
                raise ValueError(
                    "event_after_case_end: the explicit end marker must be the last case operation"
                )
            traces.append(
                (
                    case_id,
                    None,
                    tuple(
                        (r.event_id, r.activity, r.timestamp, index, (), r.end)
                        for r, index in rows
                    ),
                )
            )
        events, occurrences, aliases, duplicates = _batch(
            spec.namespace,
            "records",
            traces,
            spec.close_cases,
            duplicates=duplicates,
            start_sequences=starts,
        )
        if len(events) > spec.max_events:
            return _derived_result(
                "pix.case_centric.stream_adapters.records",
                source,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "stream_batch_limit",
                        "End markers make projected operations exceed max_events",
                    ),
                ),
            )
        unique_events = sum(not record.end for record, _ in first_rows.values())
        audit = StreamSourceAudit(
            "records",
            input_events,
            unique_events,
            unique_events,
            sum(not e.end for e in events),
            0,
            0,
            len(aliases),
            sum(c.event_count == 0 for c in aliases),
            sum(e.end for e in events),
            len(duplicates),
            0,
            0,
        )
        value = StreamBatch(
            spec.namespace,
            events,
            occurrences,
            aliases,
            duplicates,
            audit,
            f"case groups in first-appearance order; per-case {spec.order_policy} order; delivery order is not cross-case causality",
        )
        issues.append(ComputeIssue("explicit_record_order", value.ordering))
        if spec.duplicate_policy == "idempotent" and duplicates:
            issues.append(
                ComputeIssue(
                    "duplicate_records_collapsed",
                    "Identical case/event source records were collapsed with source-position aliases",
                )
            )
        return _derived_result(
            "pix.case_centric.stream_adapters.records",
            source,
            spec,
            ComputeStatus.COMPUTED,
            value,
            (*issues, *_source_issues(aliases)),
        )
    except (KeyError, ValueError, TypeError) as exc:
        return _derived_result(
            "pix.case_centric.stream_adapters.records",
            source,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue("invalid_stream_records", str(exc)),),
        )


def ocel_stream(
    log: OCEL | ComputationContext, spec: OCELStreamSpec
) -> ComputationResult[StreamBatch]:
    if not isinstance(spec, OCELStreamSpec):
        raise TypeError("spec must be OCELStreamSpec")
    try:
        context = (
            log if isinstance(log, ComputationContext) else ComputationContext(log)
        )
    except InvalidOCELInput as exc:
        return _derived_result(
            "pix.case_centric.stream_adapters.ocel",
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            tuple(ComputeIssue(i.code, i.message, i.at) for i in exc.report.errors),
        )
    traces, parents, issues, selected_events, selected_objects = (
        [],
        [],
        [],
        set(),
        set(),
    )
    relation_count = 0
    for projection in spec.projections:
        mapped = reconstruct_traces(context, projection)
        if mapped.computation_id:
            parents.append(mapped.computation_id)
        issues.extend(mapped.issues)
        if mapped.value is None:
            return _derived_result(
                "pix.case_centric.stream_adapters.ocel",
                context.source_digest,
                spec,
                mapped.status,
                None,
                tuple(issues),
                parent_computation_ids=tuple(parents),
            )
        for trace in mapped.value.traces:
            selected_objects.add(trace.object_id)
            rows = []
            for event in trace.events:
                selected_events.add(event.event_id)
                relation_count += len(event.relations)
                rows.append(
                    (
                        event.event_id,
                        event.activity,
                        event.time,
                        None,
                        event.relations,
                        False,
                    )
                )
            traces.append((trace.object_id, trace.object_type, tuple(rows)))
    total = sum(len(rows) for _, _, rows in traces)
    if total + (len(traces) if spec.close_cases else 0) > spec.max_events:
        return _derived_result(
            "pix.case_centric.stream_adapters.ocel",
            context.source_digest,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "stream_batch_limit",
                    "Object projection exceeds max_events; shared occurrences are not silently dropped",
                ),
            ),
            parent_computation_ids=tuple(parents),
        )
    events, occurrences, aliases, duplicates = _batch(
        spec.namespace, "ocel", traces, spec.close_cases
    )
    audit = StreamSourceAudit(
        "ocel",
        len(context.log.events),
        len(context.log.events),
        len(selected_events),
        total,
        len(context.log.e2o),
        relation_count,
        len(aliases),
        sum(c.event_count == 0 for c in aliases),
        sum(e.end for e in events),
        0,
        len(context.log.events) - len(selected_events),
        len(context.log.objects) - len(selected_objects),
    )
    value = StreamBatch(
        spec.namespace,
        events,
        occurrences,
        aliases,
        duplicates,
        audit,
        "explicit object-type groups and stable object ID groups; per-object timestamps with TraceSpec tie policy; no cross-object causal ordering",
    )
    issues.append(
        ComputeIssue(
            "object_projection_occurrences",
            "One shared source event may occur in several object cases; occurrence counts are not distinct source-event counts",
        )
    )
    return _derived_result(
        "pix.case_centric.stream_adapters.ocel",
        context.source_digest,
        spec,
        ComputeStatus.COMPUTED,
        value,
        (*issues, *_source_issues(aliases)),
        parent_computation_ids=tuple(parents),
    )


@dataclass(frozen=True, slots=True)
class StreamDeliverySpec:
    stream_spec: StreamingSpec
    batch_computation_id: str
    initial_checkpoint_id: str | None


@dataclass(frozen=True, slots=True)
class StreamDelivery:
    checkpoint: StreamingCheckpoint
    accepted_operations: int
    duplicate_operations: int
    batch_operations: int


def consume_stream_batch(
    batch: ComputationResult[StreamBatch],
    stream_spec: StreamingSpec,
    initial_checkpoint: ComputationResult[StreamingCheckpoint] | None = None,
) -> ComputationResult[StreamDelivery]:
    """Return delivery evidence and a resumable frozen checkpoint without mutation."""
    if not isinstance(batch, ComputationResult) or not isinstance(
        stream_spec, StreamingSpec
    ):
        raise TypeError("expected a StreamBatch result and StreamingSpec")
    if initial_checkpoint is not None and not isinstance(
        initial_checkpoint, ComputationResult
    ):
        raise TypeError("initial_checkpoint must be a ComputationResult")
    batch_id = batch.computation_id or "unidentified-batch"
    initial_id = (
        initial_checkpoint.computation_id if initial_checkpoint is not None else None
    )
    spec = StreamDeliverySpec(stream_spec, batch_id, initial_id)
    parents = tuple(i for i in (batch.computation_id, initial_id) if i is not None)
    if batch.value is None or batch.status is not ComputeStatus.COMPUTED:
        return _derived_result(
            "pix.case_centric.stream_adapters.consume",
            batch.source_digest,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "stream_batch_unavailable",
                    "A complete identified batch is required",
                ),
                *batch.issues,
            ),
            parent_computation_ids=parents,
        )
    if not isinstance(batch.value, StreamBatch):
        raise TypeError("batch must contain StreamBatch")
    expected_id = computation_identity(
        batch.operator_id,
        batch.operator_version,
        batch.source_digest,
        batch.spec,
        batch.parent_computation_ids,
    )
    if expected_id != batch.computation_id or batch.operator_id not in BATCH_OPERATORS:
        raise ValueError("batch request identity or operator mismatch")
    if (
        not isinstance(batch.spec, RESULT_SCHEMAS[batch.operator_id][1])
        or batch.value.namespace != batch.spec.namespace
        or len(batch.value.events) > batch.spec.max_events
    ):
        raise ValueError("batch namespace/spec/capacity mismatch")
    _validate_batch(batch.value)
    if initial_checkpoint is not None:
        if initial_checkpoint.spec != stream_spec:
            raise ValueError("initial checkpoint stream spec mismatch")
        stream = CaseStream.resume(initial_checkpoint)
    else:
        stream = CaseStream(stream_spec)
    accepted, duplicate = 0, 0
    for index, event in enumerate(batch.value.events):
        try:
            receipt = stream.ingest(event)
        except ValueError as exc:
            return _derived_result(
                "pix.case_centric.stream_adapters.consume",
                batch.source_digest,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "stream_batch_rejected",
                        f"Operation {index}: {exc}; caller checkpoint remains unchanged",
                    ),
                ),
                parent_computation_ids=parents,
            )
        accepted += receipt.status == "accepted"
        duplicate += receipt.status == "duplicate"
    checkpoint = stream.checkpoint()
    value = StreamDelivery(
        checkpoint.value, accepted, duplicate, len(batch.value.events)
    )
    issues = (*batch.issues, *checkpoint.issues, *_source_issues(batch.value.cases))
    return _derived_result(
        "pix.case_centric.stream_adapters.consume",
        batch.source_digest,
        spec,
        ComputeStatus.PARTIAL
        if _source_issues(batch.value.cases)
        else checkpoint.status,
        value,
        issues,
        parent_computation_ids=parents,
    )


def restore_stream_delivery(delivery: ComputationResult[StreamDelivery]) -> CaseStream:
    if (
        not isinstance(delivery, ComputationResult)
        or delivery.operator_id != "pix.case_centric.stream_adapters.consume"
        or not isinstance(delivery.spec, StreamDeliverySpec)
        or not isinstance(delivery.value, StreamDelivery)
    ):
        raise TypeError("expected a successful StreamDelivery result")
    if delivery.computation_id != computation_identity(
        delivery.operator_id,
        delivery.operator_version,
        delivery.source_digest,
        delivery.spec,
        delivery.parent_computation_ids,
    ):
        raise ValueError("delivery request identity mismatch")
    if (
        any(
            type(getattr(delivery.value, name)) is not int
            or getattr(delivery.value, name) < 0
            for name in (
                "accepted_operations",
                "duplicate_operations",
                "batch_operations",
            )
        )
        or delivery.value.accepted_operations + delivery.value.duplicate_operations
        != delivery.value.batch_operations
    ):
        raise ValueError("delivery operation accounting mismatch")
    checkpoint = delivery.value.checkpoint
    wrapped = _derived_result(
        "pix.case_centric.streaming.checkpoint",
        checkpoint.snapshot.prefix_digest,
        delivery.spec.stream_spec,
        ComputeStatus.COMPUTED,
        checkpoint,
        parent_computation_ids=(delivery.computation_id,),
    )
    return CaseStream.resume(wrapped)


def _validate_batch(batch: StreamBatch):
    _text(batch.namespace, "batch namespace")
    kind = batch.audit.source_kind
    if kind not in ("case_log", "records", "ocel"):
        raise ValueError("unknown batch source kind")
    if len(batch.events) != len(batch.occurrences) or len(
        {c.case_id for c in batch.cases}
    ) != len(batch.cases):
        raise ValueError("batch alias/cardinality mismatch")
    cases = {c.case_id: c for c in batch.cases}
    for case in batch.cases:
        if case.case_id != _id(
            "case", batch.namespace, kind, case.object_type, case.source_case_id
        ):
            raise ValueError("batch case namespace alias mismatch")
    grouped = {c.case_id: [] for c in batch.cases}
    for event, origin in zip(batch.events, batch.occurrences):
        if event.case_id not in cases or (event.case_id, event.event_id) != (
            origin.case_id,
            origin.event_id,
        ):
            raise ValueError("batch occurrence alias mismatch")
        if origin.source_case_id != cases[event.case_id].source_case_id or (
            origin.synthetic_end and not event.end
        ):
            raise ValueError("batch source-case/end alias mismatch")
        alias = cases[event.case_id]
        expected = (
            _id("end", batch.namespace, kind, alias.object_type, origin.source_case_id)
            if origin.synthetic_end
            else _id(
                "occurrence",
                batch.namespace,
                kind,
                alias.object_type,
                origin.source_case_id,
                origin.source_event_id,
            )
        )
        if origin.event_id != expected or (
            origin.synthetic_end
            and (
                origin.source_event_id is not None
                or origin.source_position is not None
                or origin.relations
            )
        ):
            raise ValueError("batch occurrence namespace alias mismatch")
        if not origin.synthetic_end:
            _text(origin.source_event_id, "source event ID")
        if any(
            r.event != origin.source_event_id or r.object != origin.source_case_id
            for r in origin.relations
        ):
            raise ValueError("batch relation provenance mismatch")
        grouped[event.case_id].append(event)
    for case_id, events in grouped.items():
        alias = cases[case_id]
        if (
            type(alias.first_sequence) is not int
            or alias.first_sequence < 0
            or tuple(e.sequence for e in events)
            != tuple(range(alias.first_sequence, alias.first_sequence + len(events)))
            or len({e.event_id for e in events}) != len(events)
        ):
            raise ValueError("batch case sequence/event identity mismatch")
        if (
            any(e.end for e in events[:-1])
            or alias.closed != bool(events and events[-1].end)
            or alias.event_count != sum(not e.end for e in events)
        ):
            raise ValueError("batch case boundary/count mismatch")
    audit = batch.audit
    if any(
        type(getattr(audit, f.name)) is not int or getattr(audit, f.name) < 0
        for f in fields(audit)
        if f.name != "source_kind"
    ):
        raise ValueError("batch audit counts must be nonnegative integers")
    source_events = {
        (o.source_case_id, o.source_event_id)
        if kind == "records"
        else o.source_event_id
        for e, o in zip(batch.events, batch.occurrences)
        if not e.end
    }
    if (
        audit.selected_unique_source_events != len(source_events)
        or audit.excluded_source_events
        != audit.unique_source_events - audit.selected_unique_source_events
        or audit.input_event_records < audit.unique_source_events
        or audit.selected_relations > audit.input_relations
        or (
            kind == "ocel"
            and audit.selected_relations
            != sum(len(o.relations) for o in batch.occurrences)
        )
    ):
        raise ValueError("batch source event/relation accounting mismatch")
    if (
        audit.emitted_cases != len(batch.cases)
        or audit.projected_event_occurrences != sum(not e.end for e in batch.events)
        or audit.end_markers != sum(e.end for e in batch.events)
        or audit.empty_cases != sum(c.event_count == 0 for c in batch.cases)
        or audit.duplicate_records != len(batch.duplicates)
    ):
        raise ValueError("batch source audit accounting mismatch")


BATCH_OPERATORS = (
    "pix.case_centric.stream_adapters.case_log",
    "pix.case_centric.stream_adapters.records",
    "pix.case_centric.stream_adapters.ocel",
)
RESULT_SCHEMAS = {
    BATCH_OPERATORS[0]: ("case-log-stream-batch", CaseLogStreamSpec, StreamBatch),
    BATCH_OPERATORS[1]: ("record-stream-batch", RecordStreamSpec, StreamBatch),
    BATCH_OPERATORS[2]: ("ocel-stream-batch", OCELStreamSpec, StreamBatch),
    "pix.case_centric.stream_adapters.consume": (
        "stream-batch-delivery",
        StreamDeliverySpec,
        StreamDelivery,
    ),
}

__all__ = [
    "CaseLogStreamSpec",
    "RecordStreamSpec",
    "OCELStreamSpec",
    "StreamRecord",
    "StreamCaseAlias",
    "StreamOccurrence",
    "StreamDuplicate",
    "StreamSourceAudit",
    "StreamBatch",
    "StreamDeliverySpec",
    "StreamDelivery",
    "case_log_stream",
    "records_stream",
    "ocel_stream",
    "consume_stream_batch",
    "restore_stream_delivery",
]
