"""Incremental state verified against hand calculations and independent batches."""

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.case_centric.declarative import (
    DECLARE_TEMPLATES,
    DeclareConformanceSpec,
    DeclareConstraint,
    DeclareModel,
    check_declare,
)
from pix.case_centric.streaming import (
    CaseStream,
    StreamEvent,
    StreamingFootprints,
    StreamingSpec,
    TemporalBounds,
)
from pix.compute.replay import replay_traces
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.replay import ReplaySpec, TokenCounts
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _log(sequence):
    return CaseLog(
        (
            CaseTrace(
                "case",
                tuple(
                    CaseEvent(str(i), (CaseAttribute("concept:name", "string", a),))
                    for i, a in enumerate(sequence)
                ),
            ),
        )
    )


def _event(i, a, case="case", seconds=None):
    return StreamEvent(
        case,
        f"{case}:{i}",
        i,
        a,
        None if seconds is None else ORIGIN + timedelta(seconds=seconds),
    )


def _case(stream, case="case"):
    return next(c for c in stream.snapshot().value.cases if c.case_id == case)


def _sequence_model():
    return PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("p", "a"), Arc("a", "q"), Arc("q", "b"), Arc("b", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )


def test_interleaved_cases_never_create_cross_case_edges_and_close_is_explicit():
    stream = CaseStream(StreamingSpec("interleave"))
    stream.ingest(_event(0, "A", "left"))
    stream.ingest(_event(0, "X", "right"))
    stream.ingest(_event(1, "B", "left"))
    stream.ingest(_event(1, "Y", "right"))
    assert stream.snapshot().value.dfg.edges == (("A", "B", 1), ("X", "Y", 1))
    assert stream.snapshot().value.dfg.ends == ()
    assert stream.snapshot().status is ComputeStatus.PARTIAL
    stream.close_case("left", "left:end", 2)
    assert stream.snapshot().value.dfg.ends == (("B", 1),)
    stream.close_case("right", "right:end", 2)
    assert stream.snapshot().status is ComputeStatus.COMPUTED
    assert stream.snapshot().value.accepted_events == 4
    assert stream.snapshot().value.accepted_operations == 6


def test_dfg_each_prefix_matches_independent_counter():
    stream = CaseStream(StreamingSpec("prefix"))
    prefixes = {"x": [], "y": []}
    for case, activity in [("x", "A"), ("y", "B"), ("x", "A"), ("y", "A"), ("x", "B")]:
        stream.ingest(_event(len(prefixes[case]), activity, case))
        prefixes[case].append(activity)
        dfg = stream.snapshot().value.dfg
        expected = Counter(
            (a, b) for seq in prefixes.values() for a, b in zip(seq, seq[1:])
        )
        assert dfg.edges == tuple((a, b, n) for (a, b), n in sorted(expected.items()))
        assert dict(dfg.activities) == Counter(
            a for seq in prefixes.values() for a in seq
        )


def test_duplicates_are_idempotent_and_conflicts_rejected_atomically():
    stream = CaseStream(StreamingSpec("retry"))
    event = _event(0, "A")
    stream.ingest(event)
    before = stream.checkpoint()
    assert stream.ingest(event).status == "duplicate"
    assert stream.checkpoint() == before
    with pytest.raises(ValueError, match="duplicate_conflict"):
        stream.ingest(replace(event, activity="B"))
    with pytest.raises(ValueError, match="duplicate_conflict"):
        stream.ingest(replace(event, sequence=1))
    assert stream.checkpoint() == before
    stream.close_case("case", "end", 1)
    closed = stream.checkpoint()
    assert stream.close_case("case", "end", 1).status == "duplicate"
    assert stream.checkpoint() == closed
    with pytest.raises(ValueError, match="case_closed"):
        stream.ingest(_event(2, "B"))


def test_expired_retries_cannot_double_count_even_with_new_sequence():
    stream = CaseStream(StreamingSpec("dedup", dedup_window=1))
    stream.ingest(_event(0, "A"))
    stream.ingest(_event(1, "B"))
    before = stream.checkpoint()
    with pytest.raises(ValueError, match="expired_sequence"):
        stream.ingest(_event(0, "A"))
    with pytest.raises(ValueError, match="expired_event_identity"):
        stream.ingest(replace(_event(0, "A"), sequence=2))
    assert stream.checkpoint() == before
    assert "dedup_window_expired" in {i.code for i in before.issues}


def test_sequence_and_timestamp_policy_are_explicit_and_atomic():
    stream = CaseStream(StreamingSpec("order", order_policy="timestamp"))
    before = stream.snapshot()
    with pytest.raises(ValueError, match="out_of_order"):
        stream.ingest(_event(1, "A", seconds=1))
    assert stream.snapshot() == before
    stream.ingest(_event(0, "A", seconds=10))
    before = stream.snapshot()
    with pytest.raises(ValueError, match="out_of_order"):
        stream.ingest(_event(1, "B", seconds=9))
    with pytest.raises(ValueError, match="timestamp_required"):
        stream.ingest(_event(1, "B"))
    assert stream.snapshot() == before
    stream.ingest(_event(1, "B", seconds=10))
    arrival = CaseStream(StreamingSpec("sequence-only"))
    arrival.ingest(_event(0, "A", seconds=10))
    arrival.ingest(_event(1, "B", seconds=9))
    assert _case(arrival).event_count == 2


@pytest.mark.parametrize("template", DECLARE_TEMPLATES)
@pytest.mark.parametrize("closed", [False, True])
def test_all_declare_automata_match_batch_on_short_words(template, closed):
    unary = {"existence", "absence", "exactly", "exactly_one", "init", "end"}
    rule = DeclareConstraint(template, "A", None if template in unary else "B")
    model = DeclareModel(("A", "B", "C"), (rule,))
    for length in range(1, 4):
        for seq in product("ABC", repeat=length):
            stream = CaseStream(StreamingSpec("declare", declare=(rule,)))
            for i, a in enumerate(seq):
                stream.ingest(_event(i, a))
            if closed:
                stream.close_case("case", "end", len(seq))
            expected = check_declare(
                _log(seq), model, DeclareConformanceSpec("closed" if closed else "open")
            )
            assert (
                _case(stream).declare[0].state == expected.value.evaluations[0].state
            ), (template, seq, closed)


@pytest.mark.parametrize("template", DECLARE_TEMPLATES)
def test_empty_closed_case_declare_matches_batch(template):
    unary = {"existence", "absence", "exactly", "exactly_one", "init", "end"}
    rule = DeclareConstraint(template, "A", None if template in unary else "B")
    stream = CaseStream(StreamingSpec("empty", declare=(rule,)))
    stream.close_case("case", "end", 0)
    expected = check_declare(_log(()), DeclareModel(("A", "B"), (rule,)))
    assert _case(stream).declare[0].state == expected.value.evaluations[0].state
    assert stream.snapshot().value.dfg.activities == ()


def test_response_pending_is_not_violation_until_close_and_known_chain_failure_is_immediate():
    stream = CaseStream(
        StreamingSpec(
            "pending",
            declare=(
                DeclareConstraint("response", "A", "B"),
                DeclareConstraint("chain_response", "A", "B"),
            ),
        )
    )
    stream.ingest(_event(0, "A"))
    assert [s.state for s in _case(stream).declare] == ["pending", "pending"]
    stream.ingest(_event(1, "C"))
    assert [s.state for s in _case(stream).declare] == ["pending", "violated"]
    assert _case(stream).declare[1].first_violation_sequence == 1
    stream.close_case("case", "end", 2)
    assert [s.state for s in _case(stream).declare] == ["violated", "violated"]
    assert [s.first_violation_sequence for s in _case(stream).declare] == [2, 1]


def test_configurable_cardinality_zero_and_two():
    rules = (
        DeclareConstraint("existence", "A", cardinality=2),
        DeclareConstraint("absence", "A", cardinality=0),
        DeclareConstraint("exactly", "A", cardinality=2),
    )
    stream = CaseStream(StreamingSpec("cardinality", declare=rules))
    stream.ingest(_event(0, "A"))
    assert [s.state for s in _case(stream).declare] == [
        "pending",
        "violated",
        "pending",
    ]
    stream.ingest(_event(1, "A"))
    assert [s.state for s in _case(stream).declare] == [
        "satisfied",
        "violated",
        "satisfied",
    ]
    stream.ingest(_event(2, "A"))
    assert [s.state for s in _case(stream).declare] == [
        "satisfied",
        "violated",
        "violated",
    ]


@pytest.mark.parametrize(
    "sequence",
    [
        (),
        ("A",),
        ("B",),
        ("A", "B"),
        ("A", "Unknown", "B"),
        ("A", "A", "B"),
        ("B", "A"),
    ],
)
def test_streaming_replay_close_matches_existing_batch_replay(sequence):
    net = _sequence_model()
    stream = CaseStream(StreamingSpec("replay", replay_model=net))
    for i, activity in enumerate(sequence):
        stream.ingest(_event(i, activity))
        prefix = _case(stream).replay
        assert prefix.status == "pending"
        assert prefix.final_reached is None
        assert (
            prefix.counts.produced + prefix.counts.missing
            == prefix.counts.consumed + prefix.counts.remaining
        )
    stream.close_case("case", "end", len(sequence))
    observed = _case(stream).replay
    expected = replay_traces(case_traces(_log(sequence)), net).value.traces[0]
    assert observed.counts == expected.counts
    assert observed.marking.tokens == expected.ending_marking
    assert observed.status == expected.status
    assert observed.final_reached == expected.final_reached
    assert observed.processed_events == expected.processed_event_count
    assert observed.log_deviations == expected.log_deviation_count


def test_silent_limit_never_fabricates_repair_or_finalization():
    net = PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "q"), Arc("q", "a"), Arc("a", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )
    stream = CaseStream(StreamingSpec("limit", replay_model=net, silent_max_states=1))
    stream.ingest(_event(0, "Unknown"))
    stream.ingest(_event(1, "A"))
    stream.ingest(_event(2, "A"))
    stream.close_case("case", "end", 3)
    observed = _case(stream).replay
    expected = replay_traces(
        case_traces(_log(("Unknown", "A", "A"))), net, ReplaySpec(1)
    ).value.traces[0]
    assert observed.status == "limited"
    assert observed.counts == expected.counts == TokenCounts(0, 1, 0, 1)
    assert observed.processed_events == expected.processed_event_count == 1
    assert observed.log_deviations == 1
    assert observed.final_reached is None
    assert "silent_state_limit" in {i.code for i in stream.snapshot().issues}


def test_silent_before_and_after_and_duplicate_label_choice_match_batch():
    net = PetriNet(
        tuple(Place(p) for p in ("p", "q", "r", "s", "dead")),
        (
            Transition("tau0"),
            Transition("a_dead", "A"),
            Transition("z_good", "A"),
            Transition("tau1"),
        ),
        (
            Arc("p", "tau0"),
            Arc("tau0", "q"),
            Arc("q", "a_dead"),
            Arc("a_dead", "dead"),
            Arc("q", "z_good"),
            Arc("z_good", "r"),
            Arc("r", "tau1"),
            Arc("tau1", "s"),
        ),
        Marking((("p", 1),)),
        Marking((("s", 1),)),
    )
    stream = CaseStream(StreamingSpec("choice", replay_model=net))
    stream.ingest(_event(0, "A"))
    assert _case(stream).replay.marking == Marking((("dead", 1),))
    stream.close_case("case", "end", 1)
    expected = replay_traces(case_traces(_log("A")), net).value.traces[0]
    assert _case(stream).replay.counts == expected.counts
    assert _case(stream).replay.silent_firings == 1


def test_temporal_all_pairs_and_missing_times_have_explicit_counts():
    stream = CaseStream(
        StreamingSpec("time", temporal=(TemporalBounds("A", "B", 5, 10),))
    )
    for i, (activity, seconds) in enumerate(
        [("A", 0), ("A", 4), ("B", 10), ("B", 11), ("A", None), ("B", 12)]
    ):
        stream.ingest(_event(i, activity, seconds=seconds))
    temporal = _case(stream).temporal[0]
    # Gaps: 10,6; 11,7; 12,8 plus one unavailable timestamp.
    assert (
        temporal.pair_count,
        temporal.checked_pairs,
        temporal.violations,
        temporal.unavailable_pairs,
    ) == (7, 6, 2, 1)
    assert (temporal.minimum_seconds, temporal.maximum_seconds) == (6, 12)
    assert "temporal_pairs_unavailable" in {i.code for i in stream.snapshot().issues}


def test_temporal_same_activity_excludes_self_pair_and_bounded_history_reports_omissions():
    stream = CaseStream(
        StreamingSpec(
            "time-cap",
            temporal=(TemporalBounds("A", "A", 0, 100),),
            temporal_history_limit=1,
        )
    )
    for i in range(3):
        stream.ingest(_event(i, "A", seconds=i))
    temporal = _case(stream).temporal[0]
    assert temporal.pair_count == 3
    assert temporal.checked_pairs == 2
    assert temporal.unavailable_pairs == 1
    assert temporal.omitted_sources == 2
    assert len(temporal.source_times) == 1


def test_footprints_parallel_orientation_allowed_and_end_requires_closure():
    fp = StreamingFootprints(
        ("A", "B", "C", "D"),
        ("A",),
        ("D",),
        (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")),
        (("B", "C"),),
    )
    stream = CaseStream(StreamingSpec("footprints", footprints=fp))
    for i, a in enumerate("ACBD"):
        stream.ingest(_event(i, a))
    assert _case(stream).footprint_state == "pending"
    stream.close_case("case", "end", 4)
    assert _case(stream).footprint_state == "satisfied"
    bad = CaseStream(StreamingSpec("bad-footprints", footprints=fp))
    bad.ingest(_event(0, "C"))
    assert _case(bad).footprint_state == "violated"
    bad.close_case("case", "end", 1)
    assert _case(bad).footprint_violations == 2


def test_footprints_empty_case_policy_is_explicit():
    for allowed in (False, True):
        stream = CaseStream(
            StreamingSpec(
                "empty-footprint",
                footprints=StreamingFootprints((), (), (), allow_empty=allowed),
            )
        )
        stream.close_case("case", "end", 0)
        assert _case(stream).footprint_state == ("satisfied" if allowed else "violated")


def test_checkpoint_resume_state_and_request_identity_equivalence():
    spec = StreamingSpec(
        "resume",
        replay_model=_sequence_model(),
        declare=(DeclareConstraint("response", "A", "B"),),
        temporal=(TemporalBounds("A", "B", 1, 20),),
    )
    stream = CaseStream(spec)
    stream.ingest(_event(0, "A", "x", 0))
    stream.ingest(_event(0, "A", "y", 2))
    checkpoint = stream.checkpoint()
    restored = CaseStream.resume(checkpoint)
    assert restored.checkpoint() == checkpoint
    for event in (
        _event(1, "B", "x", 8),
        _event(1, "B", "y", 9),
        StreamEvent("x", "x:end", 2, end=True),
        StreamEvent("y", "y:end", 2, end=True),
    ):
        assert stream.ingest(event) == restored.ingest(event)
    assert restored.checkpoint() == stream.checkpoint()
    assert restored.snapshot() == stream.snapshot()
    with pytest.raises(FrozenInstanceError):
        checkpoint.value.snapshot.accepted_events = 999


def test_checkpoint_tamper_and_wrong_spec_are_rejected():
    stream = CaseStream(StreamingSpec("tamper"))
    stream.ingest(_event(0, "A"))
    checkpoint = stream.checkpoint()
    with pytest.raises(ValueError, match="state identity"):
        CaseStream.resume(
            replace(
                checkpoint,
                value=replace(
                    checkpoint.value,
                    snapshot=replace(checkpoint.value.snapshot, accepted_events=99),
                ),
            )
        )
    with pytest.raises(ValueError, match="request identity"):
        CaseStream.resume(replace(checkpoint, spec=StreamingSpec("other")))


def test_checkpoint_json_roundtrip_all_nested_contracts():
    import pix.results as persistence

    stream = CaseStream(
        StreamingSpec(
            "serialized",
            replay_model=_sequence_model(),
            declare=(DeclareConstraint("response", "A", "B"),),
            temporal=(TemporalBounds("A", "B", 1, 10),),
            footprints=StreamingFootprints(("A", "B"), ("A",), ("B",), (("A", "B"),)),
        )
    )
    stream.ingest(_event(0, "A", seconds=0))
    checkpoint = stream.checkpoint()
    decoded = persistence.result_from_json(persistence.result_json_bytes(checkpoint))
    assert decoded == checkpoint
    restored = CaseStream.resume(decoded)
    event = _event(1, "B", seconds=8)
    assert restored.ingest(event) == stream.ingest(event)
    assert restored.close_case("case", "end", 2) == stream.close_case("case", "end", 2)
    assert restored.snapshot() == stream.snapshot()
    assert (
        persistence.result_from_json(persistence.result_json_bytes(stream.snapshot()))
        == stream.snapshot()
    )


def test_configuration_cannot_be_reassigned_after_construction():
    stream = CaseStream(StreamingSpec("immutable-spec"))
    with pytest.raises(AttributeError):
        stream.spec = StreamingSpec("other")


def test_recomputed_checksum_does_not_replace_resume_invariant_validation():
    from pix.case_centric.streaming import _digest

    stream = CaseStream(
        StreamingSpec("invalid-state", max_activities=1, replay_model=_sequence_model())
    )
    stream.ingest(_event(0, "A"))
    checkpoint = stream.checkpoint()
    original = checkpoint.value.snapshot

    def changed(state):
        return replace(
            checkpoint,
            value=replace(
                checkpoint.value, snapshot=state, state_digest=_digest(state)
            ),
        )

    bad_edges = replace(
        original, dfg=replace(original.dfg, edges=(("OUTSIDE", "ALPHABET", 1),))
    )
    with pytest.raises(ValueError, match="edge outside alphabet"):
        CaseStream.resume(changed(bad_edges))
    case = original.cases[0]
    bad_counts = replace(
        original,
        cases=(replace(case, replay=replace(case.replay, counts=TokenCounts())),),
    )
    with pytest.raises(ValueError, match="marking/accounting"):
        CaseStream.resume(changed(bad_counts))
    bad_sequence = replace(original, cases=(replace(case, last_sequence=10),))
    with pytest.raises(ValueError, match="sequence accounting"):
        CaseStream.resume(changed(bad_sequence))
    bad_membership = replace(original, retirement_membership="0")
    with pytest.raises(ValueError, match="case membership missing"):
        CaseStream.resume(changed(bad_membership))


def test_empty_checkpoint_and_evicted_closed_checkpoint_resume():
    empty = CaseStream(StreamingSpec("empty-checkpoint"))
    assert CaseStream.resume(empty.checkpoint()).checkpoint() == empty.checkpoint()
    stream = CaseStream(
        StreamingSpec("closed-retained", max_cases=1, capacity_policy="evict_oldest")
    )
    stream.close_case("first", "end", 0)
    stream.ingest(_event(0, "A", "second"))
    assert CaseStream.resume(stream.checkpoint()).checkpoint() == stream.checkpoint()


def test_eviction_is_bounded_diagnostic_and_does_not_restart_retired_case():
    stream = CaseStream(
        StreamingSpec(
            "evict", max_cases=1, capacity_policy="evict_oldest", dedup_window=1
        )
    )
    stream.ingest(_event(0, "A", "old"))
    receipt = stream.ingest(_event(0, "B", "new"))
    assert receipt.evicted_case_id == "old"
    snapshot = stream.snapshot()
    assert len(snapshot.value.cases) == 1
    assert snapshot.value.evicted_cases == snapshot.value.evicted_open_cases == 1
    assert snapshot.value.dfg.activities == (("A", 1), ("B", 1))
    assert snapshot.value.dfg.edges == ()
    assert "case_details_evicted" in {i.code for i in snapshot.issues}
    with pytest.raises(ValueError, match="retired_case_or_membership_collision"):
        stream.ingest(_event(0, "A", "old"))
    restored = CaseStream.resume(stream.checkpoint())
    with pytest.raises(ValueError, match="retired_case_or_membership_collision"):
        restored.ingest(_event(0, "A", "old"))


def test_fixed_membership_collision_rejects_new_id_instead_of_inventing_identity():
    stream = CaseStream(
        StreamingSpec(
            "collision",
            max_cases=1,
            capacity_policy="evict_oldest",
            retirement_filter_bits=1,
        )
    )
    stream.ingest(_event(0, "A", "first"))
    before = stream.snapshot()
    with pytest.raises(ValueError, match="membership_collision"):
        stream.ingest(_event(0, "A", "second"))
    assert stream.snapshot() == before


def test_capacity_rejection_is_atomic_and_closed_cases_evict_first():
    stream = CaseStream(StreamingSpec("cap", max_cases=1, max_activities=1))
    stream.ingest(_event(0, "A"))
    before = stream.snapshot()
    with pytest.raises(ValueError, match="activity_capacity"):
        stream.ingest(_event(1, "B"))
    with pytest.raises(ValueError, match="case_capacity"):
        stream.ingest(_event(0, "A", "other"))
    assert stream.snapshot() == before
    evict = CaseStream(
        StreamingSpec("closed-first", max_cases=2, capacity_policy="evict_oldest")
    )
    evict.ingest(_event(0, "A", "old-open"))
    evict.ingest(_event(0, "A", "new-closed"))
    evict.close_case("new-closed", "end", 1)
    assert evict.ingest(_event(0, "A", "fresh")).evicted_case_id == "new-closed"
    assert evict.snapshot().value.evicted_open_cases == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_cases", 0),
        ("dedup_window", True),
        ("order_policy", "sort"),
        ("capacity_policy", "silent_drop"),
        ("declare", []),
    ],
)
def test_invalid_stream_specs_rejected(field, value):
    with pytest.raises((ValueError, TypeError)):
        StreamingSpec("invalid", **{field: value})


def test_event_and_temporal_validation():
    with pytest.raises(ValueError):
        StreamEvent("c", "e", 0, "A", datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        StreamEvent("c", "e", 0, "A", end=True)
    with pytest.raises(ValueError):
        TemporalBounds("A", "B", float("nan"), 1)
    with pytest.raises(ValueError):
        TemporalBounds("A", "B", 2, 1)
