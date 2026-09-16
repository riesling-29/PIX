"""Source identity, explicit sequence semantics and object participation tests."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.stream_adapters import (
    CaseLogStreamSpec,
    OCELStreamSpec,
    RecordStreamSpec,
    StreamRecord,
    case_log_stream,
    consume_stream_batch,
    ocel_stream,
    records_stream,
    restore_stream_delivery,
)
from pix.case_centric.streaming import StreamingSpec
from pix.contracts.analysis import TraceSpec
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseGlobal, CaseLog, CaseTrace
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _case_log():
    return CaseLog(
        (
            CaseTrace(
                "left",
                (
                    CaseEvent(
                        "e2",
                        (
                            CaseAttribute("concept:name", "string", "B"),
                            CaseAttribute(
                                "time:timestamp", "date", ORIGIN + timedelta(seconds=2)
                            ),
                        ),
                    ),
                    CaseEvent(
                        "e1",
                        (
                            CaseAttribute("concept:name", "string", "A"),
                            CaseAttribute("time:timestamp", "date", ORIGIN),
                        ),
                    ),
                ),
            ),
            CaseTrace("empty"),
            CaseTrace(
                "right",
                (CaseEvent("e3", (CaseAttribute("concept:name", "string", "X"),)),),
            ),
        )
    )


def _ocel():
    return OCEL(
        event_types=(EventType("A"), EventType("B"), EventType("unused")),
        object_types=(ObjectType("Order"), ObjectType("Item")),
        events=(
            Event("e1", "A", ORIGIN),
            Event("e2", "B", ORIGIN + timedelta(seconds=1)),
            Event("e3", "unused", ORIGIN + timedelta(seconds=2)),
        ),
        objects=(
            Object("o1", "Order"),
            Object("o2", "Order"),
            Object("o3", "Order"),
            Object("i1", "Item"),
        ),
        e2o=(
            E2O("e1", "o1", "request"),
            E2O("e1", "o1", "owner"),
            E2O("e1", "o2", "request"),
            E2O("e1", "i1", "consume"),
            E2O("e2", "o1", "request"),
        ),
    )


def _records():
    return [
        dict(
            case_id="x",
            event_id="x1",
            activity="B",
            sequence=1,
            timestamp=ORIGIN + timedelta(seconds=1),
            amount=2,
        ),
        dict(
            case_id="y",
            event_id="y0",
            activity="X",
            sequence=0,
            timestamp=ORIGIN,
            amount=3,
        ),
        dict(
            case_id="x",
            event_id="x0",
            activity="A",
            sequence=0,
            timestamp=ORIGIN,
            amount=1,
        ),
    ]


def test_case_log_uses_source_trace_order_and_never_sorts_by_timestamp():
    batch = case_log_stream(_case_log(), CaseLogStreamSpec("native", close_cases=True))
    assert batch.status is ComputeStatus.COMPUTED
    assert [(e.activity, e.end) for e in batch.value.events] == [
        ("B", False),
        ("A", False),
        (None, True),
        (None, True),
        ("X", False),
        (None, True),
    ]
    assert [a.source_case_id for a in batch.value.cases] == ["left", "empty", "right"]
    assert batch.value.audit.projected_event_occurrences == 3
    assert batch.value.audit.end_markers == 3 and batch.value.audit.empty_cases == 1
    assert batch.value.audit.input_relations == 0
    assert batch.value.events[-2].timestamp is None
    assert "source_sequence" in {i.code for i in batch.issues}
    assert "unknown_timestamp" in {i.code for i in batch.issues}


def test_case_global_default_and_selected_activity_key_use_native_projection():
    log = CaseLog(
        (CaseTrace("c", (CaseEvent("e"),)),),
        globals=(CaseGlobal("event", (CaseAttribute("task", "string", "Global"),)),),
    )
    batch = case_log_stream(
        log, CaseLogStreamSpec("global", CaseTraceSpec(activity_key="task"))
    )
    assert batch.value.events[0].activity == "Global"
    changed = replace(
        log, attributes=(CaseAttribute("unselected", "string", "changed"),)
    )
    other = case_log_stream(
        changed, CaseLogStreamSpec("global", CaseTraceSpec(activity_key="task"))
    )
    assert other.value.events == batch.value.events
    assert other.source_digest != batch.source_digest


def test_empty_open_cases_are_audited_without_fabricated_events():
    batch = case_log_stream(CaseLog((CaseTrace("empty"),)), CaseLogStreamSpec("empty"))
    assert batch.value.events == () and batch.value.audit.emitted_cases == 1
    assert "empty_open_cases" in {i.code for i in batch.issues}
    delivery = consume_stream_batch(batch, StreamingSpec("run"))
    assert delivery.status is ComputeStatus.PARTIAL
    assert delivery.value.checkpoint.snapshot.cases == ()


def test_case_batch_limit_returns_no_truncated_payload_with_full_source_identity():
    result = case_log_stream(_case_log(), CaseLogStreamSpec("limit", max_events=2))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert result.source_digest is not None


def test_record_sequence_policy_groups_interleaved_cases_and_preserves_source_positions():
    batch = records_stream(_records(), RecordStreamSpec("records", close_cases=True))
    assert batch.status is ComputeStatus.COMPUTED
    assert [e.activity for e in batch.value.events] == ["A", "B", None, "X", None]
    assert [o.source_position for o in batch.value.occurrences] == [2, 0, None, 1, None]
    assert [e.sequence for e in batch.value.events] == [0, 1, 2, 0, 1]
    assert [a.source_case_id for a in batch.value.cases] == ["x", "y"]


def test_record_default_requires_sequence_and_source_order_is_explicit():
    rows = [StreamRecord("c", "b", "B"), StreamRecord("c", "a", "A")]
    missing = records_stream(rows, RecordStreamSpec("required"))
    assert (
        missing.status is ComputeStatus.INVALID_INPUT
        and missing.source_digest is not None
    )
    source = records_stream(rows, RecordStreamSpec("source", order_policy="source"))
    assert [e.activity for e in source.value.events] == ["B", "A"]
    assert "source order" in source.value.ordering


def test_timestamp_sort_requires_time_and_explicit_tie_convention():
    rows = [StreamRecord("c", "z", "Z", ORIGIN), StreamRecord("c", "a", "A", ORIGIN)]
    ambiguous = records_stream(rows, RecordStreamSpec("time", order_policy="timestamp"))
    assert ambiguous.status is ComputeStatus.INVALID_INPUT
    explicit = records_stream(
        rows, RecordStreamSpec("time", order_policy="timestamp", tie_policy="event_id")
    )
    assert [e.activity for e in explicit.value.events] == ["A", "Z"]
    assert "timestamp_tie_broken" in {i.code for i in explicit.issues}
    missing = records_stream(
        [StreamRecord("c", "e", "A")],
        RecordStreamSpec("time", order_policy="timestamp"),
    )
    assert missing.status is ComputeStatus.INVALID_INPUT


def test_timestamp_end_marker_cannot_precede_last_event():
    rows = [
        StreamRecord("c", "e", "A", ORIGIN + timedelta(seconds=1)),
        StreamRecord("c", "end", None, ORIGIN, end=True),
    ]
    result = records_stream(rows, RecordStreamSpec("time", order_policy="timestamp"))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert "end_before_event" in result.issues[0].message


def test_source_fingerprint_includes_unused_columns_and_physical_row_order():
    spec = RecordStreamSpec("identity")
    original = records_stream(_records(), spec)
    rows = _records()
    rows[0]["amount"] = 999
    changed = records_stream(rows, spec)
    assert original.value.events == changed.value.events
    assert original.source_digest != changed.source_digest
    reordered = records_stream(list(reversed(_records())), spec)
    assert original.source_digest != reordered.source_digest
    assert (
        original.computation_id
        != records_stream(_records(), replace(spec, namespace="other")).computation_id
    )


def test_iterator_reusing_one_row_dictionary_is_snapshotted_at_each_yield():
    def rows():
        row = dict(case_id="c", event_id="a", activity="A", sequence=0)
        yield row
        row.update(event_id="b", activity="B", sequence=1)
        yield row

    result = records_stream(rows(), RecordStreamSpec("reused"))
    assert [e.activity for e in result.value.events] == ["A", "B"]
    assert [o.source_event_id for o in result.value.occurrences] == ["a", "b"]


def test_record_idempotency_is_explicit_and_full_content_conflicts_are_not_dropped():
    row = dict(case_id="c", event_id="e", activity="A", sequence=0, unused=1)
    rejected = records_stream([row, row], RecordStreamSpec("dup"))
    assert rejected.status is ComputeStatus.INVALID_INPUT
    collapsed = records_stream(
        [row, dict(row)], RecordStreamSpec("dup", duplicate_policy="idempotent")
    )
    assert len(collapsed.value.events) == 1
    assert collapsed.value.audit.input_event_records == 2
    assert collapsed.value.audit.unique_source_events == 1
    assert collapsed.value.duplicates[0].duplicate_position == 1
    conflict = records_stream(
        [row, {**row, "unused": 2}],
        RecordStreamSpec("dup", duplicate_policy="idempotent"),
    )
    assert conflict.status is ComputeStatus.INVALID_INPUT
    assert "duplicate_conflict" in conflict.issues[0].message


def test_same_source_event_id_in_different_record_cases_is_two_occurrences():
    rows = [
        StreamRecord("a", "shared", "A", sequence=0),
        StreamRecord("b", "shared", "A", sequence=0),
    ]
    batch = records_stream(rows, RecordStreamSpec("ids"))
    assert batch.value.audit.unique_source_events == 2
    assert len({e.event_id for e in batch.value.events}) == 2
    assert [o.source_event_id for o in batch.value.occurrences] == ["shared", "shared"]


def test_duck_dataframe_records_mapping_without_pandas_import():
    class Frame:
        def to_dict(self, *, orient):
            assert orient == "records"
            return [{"case": "c", "id": "e", "task": "A", "pos": 0}]

    spec = RecordStreamSpec(
        "frame",
        case_id_key="case",
        event_id_key="id",
        activity_key="task",
        sequence_key="pos",
    )
    batch = records_stream(Frame(), spec)
    assert batch.value.events[0].activity == "A"
    assert batch.value.occurrences[0].source_event_id == "e"


def test_record_limit_does_not_claim_full_source_identity_if_iterable_not_consumed():
    rows = [StreamRecord("c", f"e{i}", "A", sequence=i) for i in range(3)]
    result = records_stream(iter(rows), RecordStreamSpec("limit", max_events=2))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert result.source_digest is None and result.computation_id is None
    closed = records_stream(
        rows[:1], RecordStreamSpec("limit", max_events=1, close_cases=True)
    )
    assert (
        closed.status is ComputeStatus.UNAVAILABLE and closed.source_digest is not None
    )


def test_ocel_joint_participation_does_not_duplicate_multiple_qualifiers():
    batch = ocel_stream(
        _ocel(), OCELStreamSpec("ocel", (TraceSpec("Order"),), close_cases=True)
    )
    assert batch.status is ComputeStatus.COMPUTED
    audit = batch.value.audit
    assert (
        audit.unique_source_events,
        audit.selected_unique_source_events,
        audit.projected_event_occurrences,
    ) == (3, 2, 3)
    assert (audit.input_relations, audit.selected_relations) == (5, 4)
    assert (audit.emitted_cases, audit.empty_cases, audit.end_markers) == (3, 1, 3)
    assert (audit.excluded_source_events, audit.excluded_objects) == (1, 1)
    shared = [o for o in batch.value.occurrences if o.source_event_id == "e1"]
    assert len(shared) == 2 and len({o.event_id for o in shared}) == 2
    assert len(next(o for o in shared if o.source_case_id == "o1").relations) == 2
    delivery = consume_stream_batch(batch, StreamingSpec("ocel-run"))
    assert delivery.value.checkpoint.snapshot.accepted_events == 3
    assert delivery.value.duplicate_operations == 0


def test_ocel_explicit_types_qualifiers_and_isolated_objects():
    all_types = ocel_stream(
        _ocel(), OCELStreamSpec("all", (TraceSpec("Order"), TraceSpec("Item")))
    )
    assert all_types.value.audit.projected_event_occurrences == 4
    assert all_types.value.audit.selected_relations == 5
    assert all_types.value.audit.excluded_objects == 0
    owners = ocel_stream(
        _ocel(), OCELStreamSpec("owner", (TraceSpec("Order", qualifiers=("owner",)),))
    )
    assert owners.value.audit.projected_event_occurrences == 1
    assert (
        owners.value.audit.selected_relations == 1
        and owners.value.audit.empty_cases == 2
    )
    none = ocel_stream(
        _ocel(),
        OCELStreamSpec("none", (TraceSpec("Order", qualifiers=()),), close_cases=True),
    )
    assert (
        none.value.audit.projected_event_occurrences == 0
        and none.value.audit.end_markers == 3
    )


def test_ocel_timestamp_tie_default_reject_and_full_source_identity():
    original = _ocel()
    tied = replace(
        original,
        events=(
            original.events[0],
            replace(original.events[1], time=ORIGIN),
            original.events[2],
        ),
    )
    result = ocel_stream(tied, OCELStreamSpec("tie", (TraceSpec("Order"),)))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    explicit = ocel_stream(
        tied, OCELStreamSpec("tie", (TraceSpec("Order", tie_policy="event_id"),))
    )
    assert explicit.value is not None and "timestamp_tie_broken" in {
        i.code for i in explicit.issues
    }
    base = ocel_stream(original, OCELStreamSpec("full", (TraceSpec("Order"),)))
    changed = replace(
        original,
        events=original.events[:2]
        + (replace(original.events[2], time=ORIGIN + timedelta(days=1)),),
    )
    other = ocel_stream(changed, OCELStreamSpec("full", (TraceSpec("Order"),)))
    assert (
        base.value.events == other.value.events
        and base.source_digest != other.source_digest
    )


def test_ocel_unknown_type_and_projection_capacity_are_unavailable():
    missing = ocel_stream(_ocel(), OCELStreamSpec("missing", (TraceSpec("Unknown"),)))
    assert missing.status is ComputeStatus.UNAVAILABLE
    capped = ocel_stream(
        _ocel(), OCELStreamSpec("limit", (TraceSpec("Order"),), max_events=2)
    )
    assert capped.status is ComputeStatus.UNAVAILABLE and capped.value is None


def test_record_chunk_continuation_preserves_explicit_source_sequences():
    stream_spec = StreamingSpec("continuation")
    first = records_stream(
        [StreamRecord("c", "a", "A", sequence=0)], RecordStreamSpec("chunks")
    )
    delivery = consume_stream_batch(first, stream_spec)
    stream = restore_stream_delivery(delivery)
    second = records_stream(
        [StreamRecord("c", "b", "B", sequence=1)],
        RecordStreamSpec("chunks", close_cases=True),
    )
    assert [e.sequence for e in second.value.events] == [1, 2]
    assert second.value.cases[0].first_sequence == 1
    finished = consume_stream_batch(second, stream_spec, stream.checkpoint())
    assert finished.value.checkpoint.snapshot.dfg.edges == (("A", "B", 1),)
    assert finished.value.checkpoint.snapshot.closed_cases == 1
    fresh = consume_stream_batch(second, stream_spec)
    assert fresh.status is ComputeStatus.UNAVAILABLE and fresh.value is None


def test_source_policy_chunk_offset_is_declared_not_guessed():
    result = records_stream(
        [StreamRecord("c", "e", "A")],
        RecordStreamSpec("offset", order_policy="source", start_sequences=(("c", 5),)),
    )
    assert result.value.events[0].sequence == 5
    conflict = records_stream(
        [StreamRecord("c", "e", "A", sequence=4)],
        RecordStreamSpec("offset", start_sequences=(("c", 5),)),
    )
    assert conflict.status is ComputeStatus.INVALID_INPUT


def test_delivery_retries_are_idempotent_and_failed_batch_does_not_mutate_prior_checkpoint():
    spec = StreamingSpec("delivery", max_activities=2)
    batch = records_stream(
        [StreamRecord("c", "a", "A", sequence=0)], RecordStreamSpec("delivery")
    )
    first = consume_stream_batch(batch, spec)
    checkpoint = restore_stream_delivery(first).checkpoint()
    repeated = consume_stream_batch(batch, spec, checkpoint)
    assert (
        repeated.value.accepted_operations == 0
        and repeated.value.duplicate_operations == 1
    )
    assert repeated.value.checkpoint == checkpoint.value
    bad = records_stream(
        [
            StreamRecord("c", "b", "B", sequence=1),
            StreamRecord("c", "c", "C", sequence=2),
        ],
        RecordStreamSpec("delivery"),
    )
    failed = consume_stream_batch(bad, spec, checkpoint)
    assert failed.status is ComputeStatus.UNAVAILABLE and failed.value is None
    assert checkpoint.value.snapshot.accepted_events == 1
    assert restore_stream_delivery(first).checkpoint().value == checkpoint.value


def test_delivery_rejects_inconsistent_batch_aliases():
    batch = records_stream(
        [StreamRecord("c", "e", "A", sequence=0)], RecordStreamSpec("alias")
    )
    corrupt = replace(
        batch.value,
        occurrences=(replace(batch.value.occurrences[0], source_case_id="wrong"),),
    )
    with pytest.raises(ValueError, match="source-case"):
        consume_stream_batch(replace(batch, value=corrupt), StreamingSpec("alias-run"))
    with pytest.raises(FrozenInstanceError):
        batch.value.namespace = "other"


def test_delivery_rejects_forged_namespace_and_joint_source_counts():
    batch = ocel_stream(_ocel(), OCELStreamSpec("identity", (TraceSpec("Order"),)))
    with pytest.raises(ValueError, match="namespace/spec"):
        consume_stream_batch(
            replace(batch, value=replace(batch.value, namespace="changed")),
            StreamingSpec("run"),
        )
    audit = replace(batch.value.audit, selected_unique_source_events=3)
    with pytest.raises(ValueError, match="source event/relation accounting"):
        consume_stream_batch(
            replace(batch, value=replace(batch.value, audit=audit)),
            StreamingSpec("run"),
        )


def test_full_record_fingerprint_handles_large_integer_source_attributes():
    rows = [
        dict(
            case_id="c",
            event_id="e",
            activity="A",
            sequence=0,
            opaque_counter=1 << 20000,
        )
    ]
    batch = records_stream(rows, RecordStreamSpec("large-integer"))
    assert batch.status is ComputeStatus.COMPUTED
    changed = [{**rows[0], "opaque_counter": (1 << 20000) + 1}]
    assert (
        batch.source_digest
        != records_stream(changed, RecordStreamSpec("large-integer")).source_digest
    )


def test_public_json_roundtrips_all_batch_types_delivery_and_resume():
    from pix.results import result_from_json, result_json_bytes

    batches = (
        case_log_stream(_case_log(), CaseLogStreamSpec("json-case", close_cases=True)),
        records_stream(_records(), RecordStreamSpec("json-records", close_cases=True)),
        ocel_stream(
            _ocel(),
            OCELStreamSpec(
                "json-ocel", (TraceSpec("Order"), TraceSpec("Item")), close_cases=True
            ),
        ),
    )
    for batch in batches:
        decoded = result_from_json(result_json_bytes(batch))
        assert decoded == batch
        delivery = consume_stream_batch(decoded, StreamingSpec("json-delivery"))
        restored_delivery = result_from_json(result_json_bytes(delivery))
        assert restored_delivery == delivery
        assert (
            restore_stream_delivery(restored_delivery).checkpoint().value
            == delivery.value.checkpoint
        )


def test_invalid_ocel_input_preserves_validation_issue_without_silent_filtering():
    original = _ocel()
    invalid = replace(original, e2o=original.e2o + (E2O("missing", "o1", "request"),))
    result = ocel_stream(invalid, OCELStreamSpec("invalid", (TraceSpec("Order"),)))
    assert result.status is ComputeStatus.INVALID_INPUT and result.value is None
    assert result.issues


def test_record_namespace_encoding_cannot_collide_on_delimiters_or_escaping():
    rows = [
        StreamRecord('a","b', "event", "A", sequence=0),
        StreamRecord("a", 'b","event', "A", sequence=0),
    ]
    batch = records_stream(rows, RecordStreamSpec('quoted:"namespace'))
    assert len({e.case_id for e in batch.value.events}) == 2
    assert len({e.event_id for e in batch.value.events}) == 2


def test_source_boundary_end_markers_are_not_duplicated_or_ignored():
    valid = [
        StreamRecord("c", "a", "A", sequence=0),
        StreamRecord("c", "end", None, sequence=1, end=True),
    ]
    batch = records_stream(valid, RecordStreamSpec("boundaries", close_cases=True))
    assert len(batch.value.events) == 2 and batch.value.audit.end_markers == 1
    assert not batch.value.occurrences[-1].synthetic_end
    after_end = records_stream(
        valid + [StreamRecord("c", "b", "B", sequence=2)],
        RecordStreamSpec("boundaries"),
    )
    assert after_end.status is ComputeStatus.INVALID_INPUT
    assert "event_after_case_end" in after_end.issues[0].message


@pytest.mark.parametrize(
    "field,value",
    [
        ("order_policy", "guess"),
        ("tie_policy", "source"),
        ("duplicate_policy", "drop"),
        ("max_events", 0),
        ("close_cases", 1),
        ("start_sequences", (("c", -1),)),
    ],
)
def test_invalid_record_specs_reject(field, value):
    with pytest.raises((ValueError, TypeError)):
        RecordStreamSpec("invalid", **{field: value})
