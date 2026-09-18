"""Exact retained OCEL revisions: batch oracle and hand-derived bridge evidence."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from pix.compute.context import ComputationContext, InvalidOCELInput
from pix.compute.executions import discover_executions
from pix.contracts.execution import ExecutionSpec
from pix.contracts.result import ComputeStatus
from pix.object_centric.revisable_stream import (
    OCRevisableStream,
    OCRevisionSpec,
    OCSourceOffset,
)
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType
from pix.ocel.canonical.v1 import serialize_v1
from pix.ocel.model import Attribute, EventAttr, ObjectAttr, ValueType

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def initial():
    return OCEL(
        event_types=(EventType("A"), EventType("Bridge"), EventType("Corrected")),
        object_types=(ObjectType("Order"), ObjectType("Item")),
        events=(Event("a", "A", T0), Event("b", "A", T0 + timedelta(seconds=2))),
        objects=(Object("o1", "Order"), Object("o2", "Order")),
        e2o=(E2O("a", "o1", "flow"), E2O("b", "o2", "flow")),
    )


def bridge():
    return Event("bridge", "Bridge", T0 + timedelta(seconds=1))


def links():
    return (
        E2O("bridge", "o1", "flow"),
        E2O("bridge", "o2", "flow"),
        E2O("bridge", "o2", "audit"),
    )


def request(number=1, **extra):
    return {
        "operation_id": f"op-{number}",
        "source_offset": OCSourceOffset("feed", number),
        **extra,
    }


def assert_batch(stream):
    actual = stream.snapshot()
    expected = discover_executions(stream.log, actual.spec.parameters.execution_spec)
    assert actual.value.executions == expected.value
    assert actual.source_digest == expected.source_digest
    assert actual.parent_computation_ids == (expected.computation_id,)
    assert serialize_v1(actual.value.log) == serialize_v1(stream.log)
    return actual


def test_bridge_merges_then_deletion_splits_without_losing_qualifiers():
    stream = OCRevisableStream(initial())
    before = assert_batch(stream)
    assert len(before.value.executions.executions) == 2
    receipt = stream.upsert_event(bridge(), links(), **request())
    assert len(receipt.changes) == 1
    change = receipt.changes[0]
    assert change.kind == "merge"
    assert len(change.before_execution_ids) == 2
    assert len(change.after_execution_ids) == 1
    assert change.shared_event_ids == ("a", "b")
    merged = assert_batch(stream)
    assert len(merged.value.executions.executions) == 1
    assert len(stream.log.e2o) == 5
    assert {r.qualifier for r in merged.value.executions.executions[0].relations} == {
        "flow",
        "audit",
    }
    receipt = stream.delete_event("bridge", **request(2, expected_revision=1))
    assert receipt.changes[0].kind == "split"
    assert receipt.changes[0].shared_event_ids == ("a", "b")
    assert len(assert_batch(stream).value.executions.executions) == 2
    assert serialize_v1(stream.log) == serialize_v1(initial())


def test_correction_replaces_e2o_and_requires_current_revision():
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    checkpoint = stream.checkpoint()
    with pytest.raises(ValueError, match="correction requires"):
        stream.upsert_event(bridge(), (links()[0],), **request(2))
    assert stream.checkpoint() == checkpoint
    with pytest.raises(ValueError, match="stale"):
        stream.upsert_event(bridge(), (links()[0],), **request(2, expected_revision=0))
    assert stream.checkpoint() == checkpoint
    receipt = stream.upsert_event(
        bridge(), (links()[0],), **request(2, expected_revision=1)
    )
    assert receipt.changes[0].kind == "split"
    assert [r for r in stream.log.e2o if r.event == "bridge"] == [links()[0]]
    assert_batch(stream)


def test_activity_and_late_timestamp_correction_use_batch_order():
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    updated = replace(bridge(), type="Corrected", time=T0 - timedelta(seconds=1))
    receipt = stream.upsert_event(updated, links(), **request(2, expected_revision=1))
    assert receipt.changes[0].kind == "changed"
    snapshot = assert_batch(stream)
    edges = snapshot.value.executions.executions[0].order_edges
    assert {e.target_event for e in edges if e.source_event == "bridge"} == {"a", "b"}


def test_exact_retry_returns_original_receipt_after_later_edits_and_close():
    stream = OCRevisableStream(initial())
    first = stream.upsert_event(bridge(), links(), **request())
    stream.delete_event("bridge", **request(2, expected_revision=1))
    stream.close(**request(3, expected_revision=2))
    before = stream.checkpoint()
    repeated = stream.upsert_event(bridge(), tuple(reversed(links())), **request())
    assert repeated == replace(first, replayed=True)
    assert repeated.revision == 1
    assert stream.revision == 3
    assert stream.checkpoint() == before


@pytest.mark.parametrize(
    "kind", ["payload", "operation_id", "offset", "expected_revision"]
)
def test_reused_tokens_reject_conflict_atomically(kind):
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    kwargs = request()
    event = bridge()
    if kind == "payload":
        event = replace(event, type="Corrected")
    elif kind == "operation_id":
        kwargs["operation_id"] = "another"
    elif kind == "offset":
        kwargs["source_offset"] = OCSourceOffset("feed", "one")
    else:
        kwargs["expected_revision"] = 1
    before = stream.checkpoint()
    with pytest.raises(ValueError, match="conflict"):
        stream.upsert_event(event, links(), **kwargs)
    assert stream.checkpoint() == before


def test_opaque_offsets_are_typed_and_not_watermarks():
    stream = OCRevisableStream(initial())
    stream.upsert_object(Object("x", "Item"), **request(10))
    stream.upsert_object(Object("y", "Item"), **request(1))
    stream.upsert_object(
        Object("z", "Item"),
        operation_id="str-offset",
        source_offset=OCSourceOffset("feed", "1"),
    )
    assert stream.revision == 3
    assert (
        OCRevisableStream.restore(stream.checkpoint()).checkpoint()
        == stream.checkpoint()
    )


@pytest.mark.parametrize(
    "relations",
    [
        (E2O("bridge", "missing", "flow"),),
        (E2O("bridge", "o1", "flow"), E2O("bridge", "o1", "flow")),
    ],
)
def test_invalid_relation_revision_rolls_back_and_does_not_consume_tokens(relations):
    stream = OCRevisableStream(initial())
    before = stream.checkpoint()
    with pytest.raises(InvalidOCELInput):
        stream.upsert_event(bridge(), relations, **request())
    assert stream.checkpoint() == before
    stream.upsert_event(bridge(), links(), **request())
    assert stream.revision == 1


def test_wrong_event_relation_declared_type_and_mutable_relations_rejected():
    stream = OCRevisableStream(initial())
    before = stream.checkpoint()
    with pytest.raises(ValueError, match="upserted"):
        stream.upsert_event(bridge(), (E2O("a", "o1", ""),), **request())
    with pytest.raises(TypeError):
        stream.upsert_event(bridge(), list(links()), **request())
    with pytest.raises(InvalidOCELInput):
        stream.upsert_event(replace(bridge(), type="undeclared"), links(), **request())
    assert stream.checkpoint() == before


def test_object_insert_correction_delete_and_referenced_refusal():
    stream = OCRevisableStream(initial())
    stream.upsert_object(Object("x", "Item"), **request())
    before = stream.checkpoint()
    with pytest.raises(ValueError, match="requires"):
        stream.upsert_object(Object("x", "Order"), **request(2))
    with pytest.raises(ValueError, match="referenced"):
        stream.delete_object("o1", **request(2, expected_revision=1))
    assert stream.checkpoint() == before
    stream.upsert_object(Object("x", "Order"), **request(2, expected_revision=1))
    stream.delete_object("x", **request(3, expected_revision=2))
    assert serialize_v1(stream.log) == serialize_v1(initial())
    assert_batch(stream)


def test_o2o_is_retained_and_blocks_object_deletion():
    log = replace(
        initial(),
        objects=initial().objects + (Object("x", "Item"),),
        o2o=(O2O("x", "o1", "contains"),),
    )
    stream = OCRevisableStream(log)
    with pytest.raises(ValueError, match="referenced"):
        stream.delete_object("x", **request(expected_revision=0))
    restored = OCRevisableStream.restore(stream.checkpoint())
    assert restored.log.o2o == log.o2o


def test_close_reopen_are_explicit_and_snapshot_identity_tracks_lifecycle():
    stream = OCRevisableStream(initial())
    first = stream.snapshot()
    stream.close(**request(expected_revision=0))
    closed = stream.snapshot()
    assert closed.value.closed
    assert closed.source_digest == first.source_digest
    assert closed.computation_id != first.computation_id
    with pytest.raises(ValueError, match="closed"):
        stream.upsert_event(bridge(), links(), **request(2))
    stream.reopen(**request(2, expected_revision=1))
    stream.upsert_event(bridge(), links(), **request(3))
    assert not assert_batch(stream).value.closed


def test_reopen_open_and_missing_delete_reject_without_state_change():
    stream = OCRevisableStream(initial())
    checkpoint = stream.checkpoint()
    with pytest.raises(ValueError, match="already"):
        stream.reopen(**request(expected_revision=0))
    for method in (stream.delete_event, stream.delete_object):
        with pytest.raises(ValueError, match="does not exist"):
            method("missing", **request(expected_revision=0))
    assert stream.checkpoint() == checkpoint


def test_checkpoint_replay_includes_corrections_deletes_lifecycle_and_deduplication():
    stream = OCRevisableStream(initial())
    original = stream.upsert_event(bridge(), links(), **request())
    stream.upsert_event(
        replace(bridge(), type="Corrected"), links(), **request(2, expected_revision=1)
    )
    stream.delete_event("bridge", **request(3, expected_revision=2))
    stream.close(**request(4, expected_revision=3))
    restored = OCRevisableStream.restore(stream.checkpoint().encode())
    assert restored.checkpoint() == stream.checkpoint()
    assert restored.snapshot() == stream.snapshot()
    assert restored.upsert_event(bridge(), links(), **request()) == replace(
        original, replayed=True
    )
    restored.reopen(**request(5, expected_revision=4))
    assert not restored.closed


def _resign(document):
    raw = json.dumps(
        document["body"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    document["sha256"] = sha256(raw.encode()).hexdigest()
    return json.dumps(document)


@pytest.mark.parametrize(
    "mutation",
    ["digest", "state", "base", "unknown", "duplicate_operation", "operation_payload"],
)
def test_corrupt_or_replay_inconsistent_checkpoint_rejected(mutation):
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    doc = json.loads(stream.checkpoint())
    if mutation == "digest":
        doc["sha256"] = "0" * 64
    elif mutation == "state":
        doc["body"]["state"]["revision"] = 999
    elif mutation == "base":
        doc["body"]["base"]["e2o"][0]["object"] = "missing"
    elif mutation == "unknown":
        doc["body"]["operations"][0]["ignored"] = "cannot be ignored"
    elif mutation == "duplicate_operation":
        doc["body"]["operations"].append(doc["body"]["operations"][0])
    else:
        doc["body"]["operations"][0]["event"]["type"] = "Corrected"
    data = json.dumps(doc) if mutation == "digest" else _resign(doc)
    with pytest.raises(ValueError):
        OCRevisableStream.restore(data)


@pytest.mark.parametrize(
    "data",
    [
        '{"body": {}, "body": {}, "sha256":"x"}',
        "NaN",
        "[]",
        '{"body":null,"sha256":"x"}',
    ],
)
def test_malformed_checkpoint_rejected(data):
    with pytest.raises(ValueError):
        OCRevisableStream.restore(data)


def attribute_log():
    attrs = tuple(
        Attribute(name, kind)
        for name, kind in (
            ("date", ValueType.TIME),
            ("looks_date", ValueType.STRING),
            ("fraction", ValueType.FLOAT),
            ("active", ValueType.BOOLEAN),
            ("count", ValueType.INTEGER),
        )
    )
    values = (T0, "2026-01-01T00:00:00.000000Z", -0.0, True, 2**100)
    return OCEL(
        event_types=(EventType("A", attrs),),
        object_types=(ObjectType("T", attrs),),
        events=(
            Event(
                "e", "A", T0, tuple(EventAttr(a.name, v) for a, v in zip(attrs, values))
            ),
        ),
        objects=(
            Object(
                "o",
                "T",
                tuple(ObjectAttr(a.name, v, T0) for a, v in zip(attrs, values)),
            ),
        ),
        e2o=(E2O("e", "o", "한글"), E2O("e", "o", "")),
    )


def test_checkpoint_preserves_all_canonical_primitive_types_and_object_history():
    stream = OCRevisableStream(attribute_log())
    restored = OCRevisableStream.restore(stream.checkpoint())
    assert serialize_v1(restored.log) == serialize_v1(attribute_log())
    values = {
        a.name: a.value for a in restored.snapshot().value.log.events[0].attributes
    }
    assert isinstance(values["date"], datetime)
    assert isinstance(values["looks_date"], str)
    assert values["fraction"].hex() == "-0x0.0p+0"
    assert type(values["active"]) is bool
    assert values["count"] == 2**100


def test_negative_zero_correction_cannot_bypass_revision_token():
    stream = OCRevisableStream(attribute_log())
    event = stream.log.events[0]
    corrected = replace(
        event,
        attributes=tuple(
            replace(a, value=0.0) if a.name == "fraction" else a
            for a in event.attributes
        ),
    )
    with pytest.raises(ValueError, match="correction"):
        stream.upsert_event(corrected, stream.log.e2o, **request())
    stream.upsert_event(corrected, stream.log.e2o, **request(expected_revision=0))
    assert (
        OCRevisableStream.restore(stream.checkpoint()).snapshot() == stream.snapshot()
    )


def test_snapshot_and_returned_facts_are_immutable():
    stream = OCRevisableStream(initial())
    result = stream.snapshot()
    with pytest.raises(FrozenInstanceError):
        result.value.closed = True
    with pytest.raises(FrozenInstanceError):
        stream.log.events[0].type = "changed"
    assert stream.revision == 0


def test_qualifier_filtering_batch_equivalence_and_excluded_evidence():
    stream = OCRevisableStream(
        initial(),
        OCRevisionSpec(ExecutionSpec("connected_components", qualifiers=("audit",))),
    )
    stream.upsert_event(bridge(), links(), **request())
    snapshot = assert_batch(stream)
    assert len(snapshot.value.executions.executions) == 3
    relations = [
        r
        for execution in snapshot.value.executions.executions
        for r in execution.relations
    ]
    assert len(relations) == 1 and relations[0].qualifier == "audit"
    assert OCRevisableStream.restore(stream.checkpoint()).snapshot() == snapshot


def test_leading_policy_empty_anchor_and_overlap_are_not_called_merges():
    stream = OCRevisableStream(
        initial(),
        OCRevisionSpec(
            ExecutionSpec("leading_object_nearest_type", leading_object_type="Order")
        ),
    )
    receipt = stream.upsert_event(bridge(), links(), **request())
    assert {row.kind for row in receipt.changes} <= {"overlap", "created", "deleted"}
    assert_batch(stream)
    stream.upsert_object(Object("empty", "Order"), **request(2))
    assert len(assert_batch(stream).value.executions.executions) == 3


def test_tied_timestamp_has_batch_unavailable_order_evidence_not_fake_order():
    stream = OCRevisableStream(initial())
    stream.upsert_event(replace(bridge(), time=T0), links(), **request())
    result = assert_batch(stream)
    assert result.status == ComputeStatus.COMPUTED
    assert result.value.executions.executions[0].order_status == "unavailable"
    assert any(issue.code == "ambiguous_event_order" for issue in result.issues)


def test_initial_invalid_log_rejected_and_empty_log_snapshots_work():
    with pytest.raises(InvalidOCELInput):
        OCRevisableStream(replace(initial(), e2o=(E2O("missing", "o1", ""),)))
    stream = OCRevisableStream(OCEL())
    assert assert_batch(stream).value.executions.executions == ()
    assert (
        OCRevisableStream.restore(stream.checkpoint()).snapshot() == stream.snapshot()
    )


def test_unrelated_fact_change_does_not_invent_execution_membership_changes():
    stream = OCRevisableStream(initial())
    receipt = stream.upsert_object(Object("unassigned", "Item"), **request())
    assert receipt.before_source_digest != receipt.after_source_digest
    assert receipt.changes == ()
    assert_batch(stream)


@pytest.mark.parametrize("offset", [True, None, 1.5, (), ""])
def test_invalid_source_offsets_rejected(offset):
    with pytest.raises((ValueError, TypeError)):
        OCSourceOffset("source", offset)


def test_result_source_identity_matches_canonical_facts():
    stream = OCRevisableStream(initial())
    assert (
        stream.snapshot().source_digest == ComputationContext(initial()).source_digest
    )


def test_typed_result_json_roundtrip_preserves_datetime_attributes():
    from pix import results

    stream = OCRevisableStream(attribute_log())
    event = stream.log.events[0]
    stream.upsert_event(
        replace(event, time=T0 + timedelta(seconds=1)),
        stream.log.e2o,
        **request(expected_revision=0),
    )
    snapshot = stream.snapshot()
    loaded = results.result_from_json(results.result_json_bytes(snapshot))
    assert loaded == snapshot
    assert serialize_v1(loaded.value.log) == serialize_v1(stream.log)


def test_checkpoint_replays_typed_event_and_object_attribute_corrections():
    stream = OCRevisableStream(attribute_log())
    event = replace(stream.log.events[0], time=T0 + timedelta(seconds=1))
    stream.upsert_event(event, stream.log.e2o, **request(expected_revision=0))
    obj = stream.log.objects[0]
    changed = replace(
        obj,
        attributes=obj.attributes
        + (ObjectAttr("date", T0, T0 + timedelta(seconds=2)),),
    )
    stream.upsert_object(changed, **request(2, expected_revision=1))
    restored = OCRevisableStream.restore(stream.checkpoint())
    assert restored.snapshot() == stream.snapshot()
    assert serialize_v1(restored.log) == serialize_v1(stream.log)


def test_equivalent_timezone_and_attribute_order_retry_is_idempotent():
    stream = OCRevisableStream(attribute_log())
    event = replace(stream.log.events[0], time=T0 + timedelta(seconds=1))
    receipt = stream.upsert_event(event, stream.log.e2o, **request(expected_revision=0))
    shifted = replace(
        event,
        time=event.time.astimezone(timezone(timedelta(hours=9))),
        attributes=tuple(reversed(event.attributes)),
    )
    repeated = stream.upsert_event(
        shifted, tuple(reversed(stream.log.e2o)), **request(expected_revision=0)
    )
    assert repeated == replace(receipt, replayed=True)


def test_history_identity_distinguishes_different_bases_converging_to_same_facts():
    left = OCRevisableStream(initial())
    right = OCRevisableStream(
        replace(
            initial(),
            events=(replace(initial().events[0], type="Bridge"), initial().events[1]),
        )
    )
    correction = replace(initial().events[0], type="Corrected")
    relation = (E2O("a", "o1", "flow"),)
    for stream in (left, right):
        stream.upsert_event(correction, relation, **request(expected_revision=0))
    a, b = left.snapshot(), right.snapshot()
    assert a.source_digest == b.source_digest
    assert a.value != b.value
    assert a.computation_id != b.computation_id
    assert OCRevisableStream.restore(left.checkpoint()).snapshot() == a


def test_unchanged_leading_overlap_has_no_false_change_on_lifecycle_or_isolate():
    base = replace(
        initial(),
        events=(initial().events[0],),
        e2o=(E2O("a", "o1", "flow"), E2O("a", "o2", "flow")),
    )
    spec = OCRevisionSpec(
        ExecutionSpec("leading_object_nearest_type", leading_object_type="Order")
    )
    stream = OCRevisableStream(base, spec)
    assert len(stream.snapshot().value.executions.executions) == 2
    close = stream.close(**request(expected_revision=0))
    assert close.changes == ()
    stream.reopen(**request(2, expected_revision=1))
    inserted = stream.upsert_object(Object("unassigned", "Item"), **request(3))
    assert inserted.changes == ()


@pytest.mark.parametrize(
    "spec",
    [
        ExecutionSpec("connected_components", object_types=("missing",)),
        ExecutionSpec("leading_object_nearest_type", leading_object_type="missing"),
    ],
)
def test_unavailable_execution_policy_rejected_at_construction(spec):
    with pytest.raises(ValueError, match="unknown_object_type"):
        OCRevisableStream(initial(), OCRevisionSpec(spec))


def test_deleted_event_id_requires_cas_to_resurrect_after_checkpoint():
    stream = OCRevisableStream(initial())
    stream.delete_event("a", **request(expected_revision=0))
    restored = OCRevisableStream.restore(stream.checkpoint())
    for target in (stream, restored):
        before = target.checkpoint()
        with pytest.raises(ValueError, match="requires"):
            target.upsert_event(
                initial().events[0], (E2O("a", "o1", "flow"),), **request(2)
            )
        assert target.checkpoint() == before
        target.upsert_event(
            initial().events[0],
            (E2O("a", "o1", "flow"),),
            **request(2, expected_revision=1),
        )
        assert serialize_v1(target.log) == serialize_v1(initial())


def test_deleted_object_id_requires_cas_to_resurrect_after_checkpoint():
    stream = OCRevisableStream(initial())
    stream.upsert_object(Object("x", "Item"), **request())
    stream.delete_object("x", **request(2, expected_revision=1))
    restored = OCRevisableStream.restore(stream.checkpoint())
    with pytest.raises(ValueError, match="requires"):
        restored.upsert_object(Object("x", "Item"), **request(3))
    restored.upsert_object(Object("x", "Item"), **request(3, expected_revision=2))
    assert restored.revision == 3


def test_snapshot_contract_rejects_invalid_facts_and_mismatched_receipt():
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    snapshot = stream.snapshot().value
    with pytest.raises(ValueError):
        replace(snapshot, canonical_facts_json="{}")
    with pytest.raises(ValueError, match="source identity"):
        replace(
            snapshot,
            last_receipt=replace(snapshot.last_receipt, after_source_digest="other"),
        )


def test_concurrent_corrections_using_same_revision_have_one_winner():
    from concurrent.futures import ThreadPoolExecutor

    stream = OCRevisableStream(initial())

    def correct(number):
        try:
            return stream.upsert_event(
                replace(
                    initial().events[0],
                    type="Corrected",
                    time=T0 + timedelta(seconds=number),
                ),
                (E2O("a", "o1", "flow"),),
                **request(number, expected_revision=0),
            )
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = tuple(pool.map(correct, (1, 2)))
    assert sum(receipt is not None for receipt in receipts) == 1
    assert stream.revision == 1
    assert_batch(stream)


def test_seeded_revision_sequence_matches_batch_and_replays_exactly():
    from random import Random

    rng = Random(972)
    stream = OCRevisableStream(initial())
    for index in range(1, 61):
        event_id = f"dynamic-{rng.randrange(8)}"
        if rng.randrange(3) == 0 and event_id in {e.id for e in stream.log.events}:
            stream.delete_event(
                event_id, **request(index, expected_revision=stream.revision)
            )
        else:
            selected = rng.sample(("o1", "o2"), rng.randrange(3))
            relations = tuple(
                E2O(event_id, obj, qualifier)
                for obj in selected
                for qualifier in rng.sample(("", "flow", "audit"), 2)
            )
            stream.upsert_event(
                Event(
                    event_id,
                    rng.choice(("A", "Bridge", "Corrected")),
                    T0 + timedelta(seconds=rng.randrange(10)),
                ),
                relations,
                **request(index, expected_revision=stream.revision),
            )
        assert_batch(stream)
        if index % 10 == 0:
            assert (
                OCRevisableStream.restore(stream.checkpoint()).snapshot()
                == stream.snapshot()
            )


@pytest.mark.parametrize(
    "section, field, value",
    [
        ("state", "revision", True),
        ("state", "revision", 1.0),
        ("state", "closed", 0),
        ("base", "version", True),
    ],
)
def test_checkpoint_does_not_equate_boolean_integer_and_float(section, field, value):
    stream = OCRevisableStream(initial())
    stream.upsert_event(bridge(), links(), **request())
    document = json.loads(stream.checkpoint())
    document["body"][section][field] = value
    with pytest.raises(ValueError):
        OCRevisableStream.restore(_resign(document))
