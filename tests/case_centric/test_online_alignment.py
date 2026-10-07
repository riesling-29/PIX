"""Independent finite-language oracles, approximate counterexamples and resumes."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.case_centric.online_alignment import (
    OnlineAlignmentSpec,
    OnlineAlignmentStream,
    build_online_alignment_proxy,
)
from pix.case_centric.streaming import StreamEvent, StreamingSpec, _digest
from pix.compute.model_semantics import fire, is_enabled
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus


def _language_net(*words):
    """Disjoint accepting branches; exactly this finite language, no hidden loops."""
    places, transitions, arcs, paths = {"start", "finish"}, [], [], []
    for branch, word in enumerate(words):
        path, before = [], "start"
        for index, activity in enumerate(word):
            transition = f"b{branch}t{index}"
            after = "finish" if index == len(word) - 1 else f"b{branch}p{index}"
            places.add(after)
            transitions.append(Transition(transition, activity))
            arcs.extend((Arc(before, transition), Arc(transition, after)))
            before = after
            path.append(transition)
        paths.append(tuple(path))
    return PetriNet(
        tuple(Place(p) for p in sorted(places)),
        tuple(transitions),
        tuple(arcs),
        Marking((("start", 1),)),
        Marking((("finish", 1),)),
    ), tuple(paths)


def _spec(*words, **options):
    net, paths = _language_net(*words)
    return OnlineAlignmentSpec(
        net,
        StreamingSpec("iws-tests"),
        proxy_transition_sequences=paths,
        discount_factor=1,
        decay_time=100,
        **options,
    )


def _event(index, activity, case="case"):
    return StreamEvent(case, f"{case}:{index}", index, activity)


def _finish(spec, word):
    stream = OnlineAlignmentStream(spec)
    for index, activity in enumerate(word):
        stream.ingest(_event(index, activity))
    stream.close_case("case", "end", len(word))
    return stream, stream.snapshot().value.cases[0]


def _edit_cost(observed, model_word):
    # Independent insert/delete DP. Unequal-label substitution costs two.
    previous = list(range(len(model_word) + 1))
    for i, activity in enumerate(observed, 1):
        current = [i]
        for j, model_activity in enumerate(model_word, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if activity == model_activity else 2),
                )
            )
        previous = current
    return previous[-1]


def _validate_full_witness(spec, case, word):
    state = case.states[0]
    assert state.omitted_steps == 0
    current = spec.model.initial_marking
    observed, total = [], 0
    labels = {t.id: t.activity for t in spec.model.transitions}
    for move in state.steps:
        total += move.cost
        if move.event_id is not None:
            observed.append(move.activity)
        if move.transition_id is not None:
            assert is_enabled(spec.model, current, move.transition_id)
            if move.kind == "sync":
                assert labels[move.transition_id] == move.activity
            current = fire(spec.model, current, move.transition_id)
    assert observed == list(word)
    assert current == state.marking == spec.model.final_marking
    assert total == state.cost == case.reported_cost


def test_wide_unexpired_beam_matches_independent_oracle_for_short_finite_words():
    languages = ("AB", "AC", "CAB")
    spec = _spec(*languages, lookahead=10, max_states_per_case=100)
    for length in range(4):
        for word in product("ABCX", repeat=length):
            _, case = _finish(spec, word)
            optimum = min(_edit_cost(word, reference) for reference in languages)
            assert case.reported_cost == optimum, word
            _validate_full_witness(spec, case, word)


def test_lookahead_limitation_is_real_approximation_with_valid_upper_bound():
    short = _spec("CA", lookahead=1)
    wide = replace(short, lookahead=2)
    _, limited = _finish(short, "A")
    _, recovered = _finish(wide, "A")
    assert limited.reported_cost == 3
    assert recovered.reported_cost == _edit_cost("A", "CA") == 1
    _validate_full_witness(short, limited, "A")


def test_beam_pruning_can_discard_future_best_explanation():
    spec = _spec("AXYZ", "CAB", lookahead=3, max_states_per_case=1)
    _, narrow = _finish(spec, "AB")
    _, wide = _finish(replace(spec, max_states_per_case=100), "AB")
    assert narrow.reported_cost == 4
    assert narrow.beam_pruned_states > 0
    assert (
        wide.reported_cost
        == min(_edit_cost("AB", word) for word in ("AXYZ", "CAB"))
        == 1
    )
    _validate_full_witness(spec, narrow, "AB")


def test_fixed_decay_expires_candidate_even_with_wide_beam():
    spec = replace(
        _spec("AXYZ", "CAB", lookahead=3, max_states_per_case=100), decay_time=1
    )
    _, fast = _finish(spec, "AB")
    _, patient = _finish(replace(spec, decay_time=100), "AB")
    assert fast.reported_cost == 4
    assert fast.expired_states > 0
    assert patient.reported_cost == 1


def test_discounted_decay_changes_survival_and_cost_without_batch_rerun():
    spec = replace(
        _spec("AXYZ", "CAB", lookahead=3, max_states_per_case=100),
        decay_time=10,
        discount_factor=0.01,
    )
    _, discounted = _finish(spec, "AXB")
    _, fixed = _finish(replace(spec, discount_factor=1), "AXB")
    assert discounted.reported_cost == 3
    assert (
        fixed.reported_cost
        == min(_edit_cost("AXB", word) for word in ("AXYZ", "CAB"))
        == 2
    )
    assert discounted.expired_states > fixed.expired_states


def test_proxy_coverage_loss_is_separate_from_search_approximation():
    spec = _spec("A", "B", lookahead=10, max_states_per_case=100)
    incomplete = replace(
        spec, proxy_transition_sequences=(spec.proxy_transition_sequences[0],)
    )
    stream, case = _finish(incomplete, "B")
    _, full = _finish(spec, "B")
    assert case.reported_cost == 2 and full.reported_cost == 0
    assert not stream.snapshot().value.proxy.model_language_complete
    assert stream.snapshot().status is ComputeStatus.PARTIAL
    assert case.bound_scope == "accepting_model_alignment_upper_bound"
    _validate_full_witness(incomplete, case, "B")


def test_open_prefix_cost_never_claims_final_alignment_bound():
    stream = OnlineAlignmentStream(_spec("AB"))
    stream.ingest(_event(0, "A"))
    case = stream.snapshot().value.cases[0]
    assert case.reported_cost == 0
    assert case.bound_scope == "model_prefix_alignment_upper_bound"
    assert case.final_cost_unresolved and not case.closed
    assert "final_cost_unresolved" in {i.code for i in stream.snapshot().issues}
    stream.close_case("case", "end", 1)
    final = stream.snapshot().value.cases[0]
    assert final.reported_cost == 1
    assert not final.final_cost_unresolved


def test_silent_segments_and_duplicate_labels_preserve_executable_branches():
    places = tuple(Place(p) for p in ("s", "l", "r", "la", "ra", "end", "f"))
    transitions = (
        Transition("tau_l"),
        Transition("tau_r"),
        Transition("a1", "A"),
        Transition("a2", "A"),
        Transition("b", "B"),
        Transition("c", "C"),
        Transition("tau_f"),
    )
    incidences = (
        ("s", "tau_l"),
        ("tau_l", "l"),
        ("s", "tau_r"),
        ("tau_r", "r"),
        ("l", "a1"),
        ("a1", "la"),
        ("r", "a2"),
        ("a2", "ra"),
        ("la", "b"),
        ("b", "end"),
        ("ra", "c"),
        ("c", "end"),
        ("end", "tau_f"),
        ("tau_f", "f"),
    )
    model = PetriNet(
        places,
        transitions,
        tuple(Arc(a, b) for a, b in incidences),
        Marking((("s", 1),)),
        Marking((("f", 1),)),
    )
    spec = OnlineAlignmentSpec(
        model,
        StreamingSpec("tau"),
        (("tau_l", "a1", "b", "tau_f"), ("tau_r", "a2", "c", "tau_f")),
        silent_move_cost=2,
        decay_time=100,
        discount_factor=1,
    )
    stream = OnlineAlignmentStream(spec)
    stream.ingest(_event(0, "A"))
    markings = {s.marking for s in stream.snapshot().value.cases[0].states}
    assert Marking((("la", 1),)) in markings and Marking((("ra", 1),)) in markings
    stream.ingest(_event(1, "C"))
    stream.close_case("case", "end", 2)
    case = stream.snapshot().value.cases[0]
    assert case.reported_cost == 4
    assert tuple(m.transition_id for m in case.states[0].steps if m.transition_id) == (
        "tau_r",
        "a2",
        "c",
        "tau_f",
    )
    _validate_full_witness(spec, case, "AC")


def test_empty_and_silent_only_accepting_proxy_close():
    empty = PetriNet((Place("p"),), (), (), Marking((("p", 1),)), Marking((("p", 1),)))
    spec = OnlineAlignmentSpec(empty, StreamingSpec("empty"), ((),))
    _, case = _finish(spec, "")
    assert case.reported_cost == 0 and case.states[0].steps == ()
    silent = PetriNet(
        (Place("p"), Place("q")),
        (Transition("tau"),),
        (Arc("p", "tau"), Arc("tau", "q")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    silent_spec = OnlineAlignmentSpec(
        silent, StreamingSpec("silent"), (("tau",),), silent_move_cost=3
    )
    _, case = _finish(silent_spec, "")
    assert case.reported_cost == 3 and case.states[0].steps[0].kind == "silent"


@pytest.mark.parametrize("path", [("not-a-transition",), ("b0t1",), ("b0t0",)])
def test_invalid_explicit_proxy_rejected(path):
    spec = replace(_spec("AB"), proxy_transition_sequences=(path,))
    with pytest.raises(ValueError, match="proxy path"):
        build_online_alignment_proxy(spec)


def test_seeded_proxy_generation_is_reproducible_and_no_path_is_not_unreachability():
    explicit = _spec("AB", "AC")
    spec = replace(
        explicit,
        proxy_transition_sequences=None,
        random_seed=73,
        proxy_max_traces=2,
        proxy_attempts=100,
    )
    first = build_online_alignment_proxy(spec)
    assert first == build_online_alignment_proxy(spec)
    assert len(first.value.transition_sequences) == 2
    assert first.value.origin == "seeded_bounded_accepting_walks"
    limited = replace(spec, proxy_max_steps=1)
    result = build_online_alignment_proxy(limited)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert (
        result.value is None
        and "reachability remains unknown" in result.issues[0].message
    )
    with pytest.raises(ValueError, match="proxy_unavailable"):
        OnlineAlignmentStream(limited)


def test_proxy_trace_and_node_capacity_are_reported():
    spec = _spec("A", "BC", max_proxy_nodes=2)
    proxy = build_online_alignment_proxy(spec).value
    assert len(proxy.transition_sequences) == 1 and proxy.excluded_paths == 1
    assert proxy.trie_nodes == 2
    assert (
        build_online_alignment_proxy(replace(spec, max_proxy_nodes=1)).status
        is ComputeStatus.UNAVAILABLE
    )
    assert (
        build_online_alignment_proxy(
            replace(spec, max_proxy_nodes=100, proxy_max_traces=1)
        ).value.excluded_paths
        == 1
    )


def test_incremental_drift_unknown_labels_fallback_and_witness_bounds():
    spec = replace(
        _spec("AB", witness_history_limit=3, max_states_per_case=2),
        decay_time=1,
        discount_factor=0.1,
    )
    stream = OnlineAlignmentStream(spec)
    word = "AXXXXXXXB"
    for i, a in enumerate(word):
        stream.ingest(_event(i, a))
        case = stream.snapshot().value.cases[0]
        assert len(case.states) <= 2
        assert all(len(s.steps) <= 3 for s in case.states)
        assert all(
            s.omitted_cost + sum(m.cost for m in s.steps) == s.cost for s in case.states
        )
    stream.close_case("case", "end", len(word))
    case = stream.snapshot().value.cases[0]
    assert case.reported_cost == 7
    assert case.unavoidable_log_cost == 7
    assert case.fallback_resets > 0
    assert case.states[0].omitted_steps > 0
    assert "alignment_witness_history_omitted" in {
        i.code for i in stream.snapshot().issues
    }
    assert (
        OnlineAlignmentStream.resume(stream.checkpoint()).checkpoint()
        == stream.checkpoint()
    )


def test_expansion_limit_is_explicit_and_keeps_valid_fallback_witness():
    spec = _spec("AB", "CD", "EF", lookahead=10, max_expansions_per_event=1)
    stream, case = _finish(spec, "C")
    assert case.expansion_limited_events == 1
    assert "online_expansion_limit" in {i.code for i in stream.snapshot().issues}
    _validate_full_witness(spec, case, "C")


def test_interleaved_cases_retries_late_events_and_closed_case_are_atomic():
    stream = OnlineAlignmentStream(_spec("AB", "AC"))
    stream.ingest(_event(0, "A", "left"))
    stream.ingest(_event(0, "A", "right"))
    before = stream.checkpoint()
    assert stream.ingest(_event(0, "A", "left")).status == "duplicate"
    assert stream.checkpoint() == before
    for event in (
        replace(_event(0, "A", "left"), activity="B"),
        _event(2, "B", "left"),
    ):
        with pytest.raises(ValueError):
            stream.ingest(event)
        assert stream.checkpoint() == before
    stream.ingest(_event(1, "B", "left"))
    stream.ingest(_event(1, "C", "right"))
    stream.close_case("left", "left:end", 2)
    assert stream.close_case("left", "left:end", 2).status == "duplicate"
    with pytest.raises(ValueError, match="case_closed"):
        stream.ingest(_event(3, "B", "left"))
    stream.close_case("right", "right:end", 2)
    assert [c.reported_cost for c in stream.snapshot().value.cases] == [0, 0]


def test_timestamp_late_input_rejected_without_algorithm_state_change():
    base = _spec("AB")
    spec = replace(base, ingestion=StreamingSpec("timestamp", order_policy="timestamp"))
    stream = OnlineAlignmentStream(spec)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stream.ingest(replace(_event(0, "A"), timestamp=origin + timedelta(seconds=1)))
    before = stream.checkpoint()
    with pytest.raises(ValueError, match="timestamp decreases"):
        stream.ingest(replace(_event(1, "B"), timestamp=origin))
    assert stream.checkpoint() == before


def test_algorithm_exception_does_not_commit_protocol_half_of_event(monkeypatch):
    stream = OnlineAlignmentStream(_spec("AB"))
    before = stream.checkpoint()
    original = OnlineAlignmentStream._advance

    def fail(*args):
        raise RuntimeError("deliberate algorithm failure")

    monkeypatch.setattr(OnlineAlignmentStream, "_advance", fail)
    with pytest.raises(RuntimeError, match="deliberate"):
        stream.ingest(_event(0, "A"))
    assert stream.checkpoint() == before
    monkeypatch.setattr(OnlineAlignmentStream, "_advance", original)
    assert stream.ingest(_event(0, "A")).status == "accepted"


def test_checkpoint_resume_continuation_equivalence_with_trimmed_histories():
    spec = replace(
        _spec("AXYZ", "CAB", lookahead=3, witness_history_limit=2),
        ingestion=StreamingSpec("resume", dedup_window=2),
        discount_factor=0.5,
    )
    stream = OnlineAlignmentStream(spec)
    stream.ingest(_event(0, "A", "one"))
    stream.ingest(_event(0, "C", "two"))
    stream.ingest(_event(1, "X", "one"))
    restored = OnlineAlignmentStream.resume(stream.checkpoint())
    for event in (
        _event(1, "A", "two"),
        _event(2, "B", "one"),
        _event(2, "B", "two"),
        StreamEvent("one", "end1", 3, end=True),
        StreamEvent("two", "end2", 3, end=True),
    ):
        assert restored.ingest(event) == stream.ingest(event)
        assert restored.checkpoint() == stream.checkpoint()
    with pytest.raises(FrozenInstanceError):
        restored.snapshot().value.cases[0].reported_cost = 100
    with pytest.raises(AttributeError):
        restored.spec = spec


def test_bounded_case_eviction_removes_matching_alignment_state():
    spec = replace(
        _spec("AB"),
        ingestion=StreamingSpec(
            "eviction", max_cases=1, capacity_policy="evict_oldest"
        ),
    )
    stream = OnlineAlignmentStream(spec)
    stream.ingest(_event(0, "A", "old"))
    receipt = stream.ingest(_event(0, "B", "new"))
    assert receipt.evicted_case_id == "old"
    assert tuple(c.case_id for c in stream.snapshot().value.cases) == ("new",)
    assert stream.snapshot().value.ingestion_state.evicted_open_cases == 1
    with pytest.raises(ValueError, match="retired_case"):
        stream.ingest(_event(0, "A", "old"))


def test_checkpoint_rejects_cost_and_executable_witness_tampering():
    stream = OnlineAlignmentStream(_spec("AB"))
    stream.ingest(_event(0, "A"))
    checkpoint = stream.checkpoint()
    snapshot = checkpoint.value.snapshot
    case = snapshot.cases[0]
    bad_state = replace(case.states[0], cost=999)
    changed = replace(
        snapshot, cases=(replace(case, states=(bad_state,), reported_cost=999),)
    )
    forged = replace(
        checkpoint,
        value=replace(
            checkpoint.value, snapshot=changed, state_digest=_digest(changed)
        ),
    )
    with pytest.raises(ValueError, match="witness cost accounting"):
        OnlineAlignmentStream.resume(forged)
    with pytest.raises(ValueError, match="request identity"):
        OnlineAlignmentStream.resume(
            replace(checkpoint, spec=replace(checkpoint.spec, random_seed=99))
        )


def test_checkpoint_rejects_duplicate_occurrence_and_wrong_deviation_count():
    stream, _ = _finish(_spec("AA"), "AA")
    checkpoint = stream.checkpoint()
    snapshot = checkpoint.value.snapshot
    case = snapshot.cases[0]
    state = case.states[0]

    def changed(new_state):
        updated = replace(snapshot, cases=(replace(case, states=(new_state,)),))
        return replace(
            checkpoint,
            value=replace(
                checkpoint.value, snapshot=updated, state_digest=_digest(updated)
            ),
        )

    duplicate = replace(state.steps[0], event_id=state.steps[1].event_id, sequence=1)
    with pytest.raises(ValueError, match="witness event sequence"):
        OnlineAlignmentStream.resume(
            changed(replace(state, steps=(duplicate,) + state.steps[1:]))
        )
    with pytest.raises(ValueError, match="omitted witness/trie path"):
        OnlineAlignmentStream.resume(changed(replace(state, deviation_moves=99)))


def test_checkpoint_rejects_valid_alternative_model_path_for_wrong_source_event():
    spec = _spec("A", "B")
    stream, _ = _finish(spec, "A")
    checkpoint = stream.checkpoint()
    snapshot, case = checkpoint.value.snapshot, checkpoint.value.snapshot.cases[0]
    original = case.states[0]
    alternate = replace(
        original,
        node_id=2,
        steps=(replace(original.steps[0], transition_id="b1t0", activity="B"),),
    )
    updated = replace(snapshot, cases=(replace(case, states=(alternate,)),))
    forged = replace(
        checkpoint,
        value=replace(
            checkpoint.value, snapshot=updated, state_digest=_digest(updated)
        ),
    )
    with pytest.raises(ValueError, match="witness/source event identity"):
        OnlineAlignmentStream.resume(forged)


def test_public_proxy_snapshot_checkpoint_json_roundtrips_and_resumed_future():
    from pix.results import result_from_json, result_json_bytes

    spec = _spec("AB", "AC", witness_history_limit=2)
    proxy = build_online_alignment_proxy(spec)
    assert result_from_json(result_json_bytes(proxy)) == proxy
    stream = OnlineAlignmentStream(spec)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    stream.ingest(replace(_event(0, "A"), timestamp=origin))
    stream.ingest(replace(_event(1, "X"), timestamp=origin + timedelta(seconds=2)))
    checkpoint = stream.checkpoint()
    decoded = result_from_json(result_json_bytes(checkpoint))
    assert decoded == checkpoint
    restored = OnlineAlignmentStream.resume(decoded)
    event = replace(_event(2, "C"), timestamp=origin + timedelta(seconds=3))
    assert restored.ingest(event) == stream.ingest(event)
    assert restored.close_case("case", "end", 3) == stream.close_case("case", "end", 3)
    assert restored.snapshot() == stream.snapshot()
    assert result_from_json(result_json_bytes(stream.snapshot())) == stream.snapshot()
    failed = build_online_alignment_proxy(
        replace(spec, proxy_transition_sequences=None, proxy_max_steps=1)
    )
    assert result_from_json(result_json_bytes(failed)) == failed


def test_custom_uniform_move_costs_are_explicit_and_persistable():
    spec = replace(_spec("A"), log_move_cost=7, model_move_cost=3)
    _, case = _finish(spec, "B")
    assert case.reported_cost == 10
    assert case.unavoidable_log_cost == 7
    _validate_full_witness(spec, case, "B")


@pytest.mark.parametrize(
    "field,value",
    [
        ("lookahead", 0),
        ("decay_time", 0),
        ("discount_factor", 1.1),
        ("max_states_per_case", True),
        ("silent_move_cost", -1),
        ("witness_history_limit", 0),
    ],
)
def test_invalid_parameters_rejected(field, value):
    with pytest.raises((TypeError, ValueError)):
        replace(_spec("AB"), **{field: value})
