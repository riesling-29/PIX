"""Late/corrected/retracted facts checked against batch DFG, not arrival order."""

import json
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import permutations

import pytest

from pix.case_centric.discovery import discover_dfg
from pix.case_centric.revisable_stream import (
    DFGCountChange,
    RetainedCaseEvent,
    RevisableCaseStream,
    RevisableCaseStreamSpec,
    SourceOffset,
    _digest,
)
from pix.contracts.result import ComputeStatus
from pix.results import read_result, result_json_bytes

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(label, position, case="c", identity=None):
    return RetainedCaseEvent(
        case,
        identity or f"{case}:{label}",
        label,
        ORIGIN + timedelta(seconds=position),
        position,
    )


def stream(**kwargs):
    return RevisableCaseStream(RevisableCaseStreamSpec("audit", **kwargs))


def edges(engine):
    return {
        (edge.source, edge.target): edge.count
        for edge in engine.snapshot().value.dfg.edges
    }


def assert_batch(engine):
    assert engine.snapshot().value.dfg == discover_dfg(engine.to_case_log()).value


def test_late_insert_retracts_direct_edge_then_delete_restores_it():
    engine = stream()
    engine.upsert_event(event("A", 1), operation_id="a")
    engine.upsert_event(event("C", 3), operation_id="c")
    old = engine.snapshot()
    receipt = engine.upsert_event(event("B", 2), operation_id="late-b")
    current = engine.snapshot()
    assert receipt.revision == 3
    assert current.value.previous_computation_id == old.computation_id
    assert current.value.previous_revision_id == old.value.revision_id
    assert current.value.previous_dfg == old.value.dfg
    assert edges(engine) == {("A", "B"): 1, ("B", "C"): 1}
    assert {(c.key, c.delta) for c in current.value.changes if c.metric == "edge"} == {
        (("A", "C"), -1),
        (("A", "B"), 1),
        (("B", "C"), 1),
    }
    assert_batch(engine)
    engine.delete_event("c", "c:B", operation_id="delete-b", expected_revision=1)
    assert edges(engine) == {("A", "C"): 1}
    tombstone = next(e for e in engine.snapshot().value.events if e.event_id == "c:B")
    assert tombstone.event is None and tombstone.revision == 2
    assert_batch(engine)
    # A retained prior result cannot change when a later revision arrives.
    assert {(e.source, e.target) for e in current.value.dfg.edges} == {
        ("A", "B"),
        ("B", "C"),
    }


@pytest.mark.parametrize("order", list(permutations("ABC")))
@pytest.mark.parametrize("policy", ["timestamp", "sequence"])
def test_every_arrival_permutation_has_same_event_order(policy, order):
    engine = stream(order_policy=policy)
    for label in order:
        engine.upsert_event(event(label, ord(label) - ord("A")), operation_id=label)
        assert_batch(engine)
    assert edges(engine) == {("A", "B"): 1, ("B", "C"): 1}


def test_correction_requires_revision_and_updates_activity_and_time_atomically():
    engine = stream()
    original = event("A", 1)
    engine.upsert_event(original, operation_id="a")
    engine.upsert_event(event("B", 2), operation_id="b")
    before = engine.checkpoint()
    corrected = replace(original, activity="X", timestamp=ORIGIN + timedelta(seconds=3))
    with pytest.raises(ValueError, match="event_conflict"):
        engine.upsert_event(corrected, operation_id="correction")
    with pytest.raises(ValueError, match="revision_conflict"):
        engine.upsert_event(corrected, operation_id="correction", expected_revision=2)
    assert engine.checkpoint() == before
    receipt = engine.upsert_event(
        corrected, operation_id="correction", expected_revision=1
    )
    assert receipt.event_revision == 2
    assert edges(engine) == {("B", "X"): 1}
    assert_batch(engine)


def test_operation_and_offset_retries_conflicts_and_restore_replay():
    engine = stream()
    original, offset = event("A", 1), SourceOffset("source", "partition-0", 7)
    receipt = engine.upsert_event(original, operation_id="a", source_offset=offset)
    before = engine.checkpoint()
    duplicate = engine.upsert_event(original, operation_id="a", source_offset=offset)
    assert duplicate == replace(receipt, status="duplicate")
    assert engine.checkpoint() == before
    with pytest.raises(ValueError, match="operation_conflict"):
        engine.upsert_event(
            replace(original, activity="X"), operation_id="a", source_offset=offset
        )
    with pytest.raises(ValueError, match="offset_conflict"):
        engine.upsert_event(original, operation_id="new-delivery", source_offset=offset)
    with pytest.raises(ValueError, match="offset_regression"):
        engine.upsert_event(
            event("B", 2), operation_id="b", source_offset=replace(offset, offset=6)
        )
    assert engine.checkpoint() == before
    restored = RevisableCaseStream.restore(before)
    assert restored.snapshot() == engine.snapshot()
    assert restored.checkpoint() == before
    assert (
        restored.upsert_event(original, operation_id="a", source_offset=offset)
        == duplicate
    )
    # Event time can be late although the source offset advances.
    restored.upsert_event(
        event("B", 0), operation_id="b", source_offset=replace(offset, offset=8)
    )
    assert edges(restored) == {("B", "A"): 1}


def test_same_facts_new_delivery_does_not_increment_entity_revision():
    engine = stream()
    original = event("A", 1)
    engine.upsert_event(original, operation_id="a")
    receipt = engine.upsert_event(original, operation_id="same-facts-new-operation")
    assert receipt.status == "unchanged"
    assert receipt.revision == 2
    assert receipt.event_revision == 1
    assert engine.snapshot().value.changes == ()


def test_close_reopen_and_empty_case_semantics():
    engine = stream()
    engine.upsert_event(event("A", 1), operation_id="a")
    assert engine.snapshot().status is ComputeStatus.PARTIAL
    assert engine.snapshot().value.dfg.end_counts == (("A", 1),)
    engine.close_case("c", operation_id="close")
    assert engine.snapshot().status is ComputeStatus.COMPUTED
    before = engine.checkpoint()
    with pytest.raises(ValueError, match="case_closed"):
        engine.delete_event("c", "c:A", operation_id="delete", expected_revision=1)
    assert engine.checkpoint() == before
    # Duplicate delivery is still harmless after closure.
    assert engine.upsert_event(event("A", 1), operation_id="a").status == "duplicate"
    engine.reopen_case("c", operation_id="reopen")
    engine.delete_event("c", "c:A", operation_id="delete", expected_revision=1)
    assert engine.snapshot().value.dfg.empty_trace_count == 1
    engine.close_case("c", operation_id="close-again")
    engine.close_case("empty", operation_id="empty")
    assert engine.snapshot().value.dfg.empty_trace_count == 2
    assert {(c.metric, c.key, c.delta) for c in engine.snapshot().value.changes} == {
        ("trace_count", (), 1),
        ("empty_trace_count", (), 1),
    }
    assert_batch(engine)
    assert (
        RevisableCaseStream.restore(engine.checkpoint()).snapshot() == engine.snapshot()
    )


def test_tombstones_require_cas_and_event_case_identity_cannot_move():
    engine = stream()
    original = event("A", 1)
    engine.upsert_event(original, operation_id="a")
    engine.delete_event("c", "c:A", operation_id="delete", expected_revision=1)
    before = engine.checkpoint()
    with pytest.raises(ValueError, match="event_conflict"):
        engine.upsert_event(original, operation_id="resurrect")
    with pytest.raises(ValueError, match="event_case_conflict"):
        engine.upsert_event(
            replace(original, case_id="other"), operation_id="move", expected_revision=2
        )
    assert engine.checkpoint() == before
    receipt = engine.upsert_event(
        original, operation_id="resurrect", expected_revision=2
    )
    assert receipt.event_revision == 3
    assert_batch(engine)


def test_case_interleaving_never_creates_cross_case_edge():
    engine = stream()
    for label, pos, case in [
        ("A", 1, "one"),
        ("X", 1, "two"),
        ("B", 2, "one"),
        ("Y", 2, "two"),
    ]:
        engine.upsert_event(event(label, pos, case), operation_id=label)
    assert edges(engine) == {("A", "B"): 1, ("X", "Y"): 1}
    assert_batch(engine)


@pytest.mark.parametrize("policy", ["timestamp", "sequence"])
def test_order_requirements_and_tie_rejection_roll_back(policy):
    engine = stream(order_policy=policy, tie_policy="reject")
    engine.upsert_event(event("A", 1), operation_id="a")
    before = engine.checkpoint()
    with pytest.raises(ValueError, match="order_tie"):
        engine.upsert_event(event("B", 1), operation_id="b")
    missing = replace(event("B", 2), **{policy: None})
    with pytest.raises(ValueError, match=f"{policy}_required"):
        engine.upsert_event(missing, operation_id="b")
    assert engine.checkpoint() == before


def test_event_time_ties_use_declared_identity_tiebreak_not_arrival():
    engine = stream()
    engine.upsert_event(event("B", 1), operation_id="b")
    engine.upsert_event(event("A", 1), operation_id="a")
    assert edges(engine) == {("A", "B"): 1}
    assert engine.spec.tie_policy == "event_id"


def test_checkpoint_corruption_duplicate_keys_and_rehashed_invalid_journal_rejected():
    engine = stream()
    engine.upsert_event(event("A", 1), operation_id="a")
    checkpoint = engine.checkpoint()
    changed = json.loads(checkpoint)
    changed["operations"][0]["event"]["activity"] = "X"
    with pytest.raises(ValueError, match="digest"):
        RevisableCaseStream.restore(json.dumps(changed))
    changed["digest"] = _digest({k: v for k, v in changed.items() if k != "digest"})
    with pytest.raises(ValueError, match="final state identity"):
        RevisableCaseStream.restore(json.dumps(changed))
    duplicated = json.loads(checkpoint)
    duplicated["operations"] *= 2
    duplicated["digest"] = _digest(
        {k: v for k, v in duplicated.items() if k != "digest"}
    )
    with pytest.raises(ValueError, match="duplicate operations"):
        RevisableCaseStream.restore(json.dumps(duplicated))
    with pytest.raises(ValueError, match="duplicate JSON key"):
        RevisableCaseStream.restore('{"format":"a","format":"b"}')


@pytest.mark.parametrize("bad", [True, -1, 1.5, "3"])
def test_invalid_offsets_and_sequences_rejected(bad):
    with pytest.raises(ValueError):
        SourceOffset("source", "p", bad)
    with pytest.raises(ValueError):
        RetainedCaseEvent("c", "e", "A", sequence=bad)


def test_immutable_facts_and_invalid_delta_contract():
    original = event("A", 1)
    with pytest.raises(FrozenInstanceError):
        original.activity = "B"
    with pytest.raises(ValueError, match="timezone"):
        replace(original, timestamp=datetime(2026, 1, 1))
    with pytest.raises(ValueError, match="delta"):
        DFGCountChange("edge", ("A", "B"), 2, 1, 1)
    engine = stream()
    engine.upsert_event(original, operation_id="a")
    with pytest.raises(FrozenInstanceError):
        engine.snapshot().value.revision = 7
    with pytest.raises(AttributeError):
        engine.spec = RevisableCaseStreamSpec("different", order_policy="sequence")


def test_repeated_edge_occurrence_and_case_counts_retract_independently():
    engine = stream()
    for index, label in enumerate("ABAB"):
        engine.upsert_event(
            event(label, index, identity=f"e{index}"), operation_id=f"i{index}"
        )
    ab = next(
        e
        for e in engine.snapshot().value.dfg.edges
        if (e.source, e.target) == ("A", "B")
    )
    assert (ab.count, ab.case_count) == (2, 1)
    engine.delete_event("c", "e3", operation_id="delete-last", expected_revision=1)
    ab = next(
        e
        for e in engine.snapshot().value.dfg.edges
        if (e.source, e.target) == ("A", "B")
    )
    assert (ab.count, ab.case_count) == (1, 1)
    changes = {(v.metric, v.key): v.delta for v in engine.snapshot().value.changes}
    assert changes["edge", ("A", "B")] == -1
    assert ("edge_cases", ("A", "B")) not in changes
    assert changes["end", ("A",)] == 1
    assert changes["end", ("B",)] == -1
    assert_batch(engine)


def test_snapshot_rejects_forged_change_or_mutable_fact_container():
    engine = stream()
    engine.upsert_event(event("A", 1), operation_id="a")
    snapshot = engine.snapshot().value
    with pytest.raises(ValueError, match="changes do not match"):
        replace(snapshot, changes=())
    with pytest.raises(TypeError, match="immutable"):
        replace(snapshot, events=list(snapshot.events))


def test_registered_result_roundtrip_preserves_revision_evidence(tmp_path):
    engine = stream()
    engine.upsert_event(event("A", 1), operation_id="a")
    engine.upsert_event(event("C", 3), operation_id="c")
    engine.upsert_event(event("B", 2), operation_id="b")
    path = tmp_path / "revision.json"
    path.write_bytes(result_json_bytes(engine.snapshot()))
    loaded = read_result(path)
    assert loaded == engine.snapshot()
    assert isinstance(loaded.value.events[0].event.timestamp, datetime)
    assert loaded.value.previous_dfg != loaded.value.dfg
    assert loaded.value.changes


def test_failed_candidate_does_not_reserve_operation_id_or_source_offset():
    engine = stream(tie_policy="reject")
    engine.upsert_event(event("A", 1), operation_id="a")
    offset = SourceOffset("source", "p", 1)
    before = engine.checkpoint()
    with pytest.raises(ValueError, match="order_tie"):
        engine.upsert_event(event("B", 1), operation_id="b", source_offset=offset)
    assert engine.checkpoint() == before
    engine.upsert_event(event("B", 2), operation_id="b", source_offset=offset)
    assert edges(engine) == {("A", "B"): 1}


def test_repeated_adjacency_across_cases_changes_case_count_on_last_case_occurrence():
    engine = stream()
    for case, labels in (("first", "ABAB"), ("second", "AB")):
        for index, label in enumerate(labels):
            identity = f"{case}:{index}"
            engine.upsert_event(
                event(label, index, case, identity), operation_id=identity
            )
    edge = next(
        e
        for e in engine.snapshot().value.dfg.edges
        if (e.source, e.target) == ("A", "B")
    )
    assert (edge.count, edge.case_count) == (3, 2)
    engine.delete_event(
        "second", "second:1", operation_id="remove-second-b", expected_revision=1
    )
    edge = next(
        e
        for e in engine.snapshot().value.dfg.edges
        if (e.source, e.target) == ("A", "B")
    )
    assert (edge.count, edge.case_count) == (2, 1)
    assert ("edge_cases", ("A", "B"), -1) in {
        (change.metric, change.key, change.delta)
        for change in engine.snapshot().value.changes
    }
