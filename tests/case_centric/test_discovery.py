from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.discovery import (
    BatchDiscoverySpec,
    FootprintSpec,
    LocalProcessModelSpec,
    PrefixTreeSpec,
    RelationDiscoverySpec,
    TransitionSystemSpec,
    discover_batches,
    discover_dfg,
    discover_efg,
    discover_footprints,
    discover_local_process_models,
    discover_prefix_tree,
    discover_transition_system,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log_of(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}-{j}", (CaseAttribute("concept:name", "string", a),)
                    )
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def edge_counts(result):
    return {(e.source, e.target): e.count for e in result.value.edges}


def test_dfg_occurrence_and_case_counts_are_distinct():
    log = log_of("ABABA", "AC", "")
    result = discover_dfg(log)
    assert edge_counts(result) == {("A", "B"): 2, ("B", "A"): 2, ("A", "C"): 1}
    assert edge_counts(discover_dfg(log, RelationDiscoverySpec(counting="cases"))) == {
        ("A", "B"): 1,
        ("B", "A"): 1,
        ("A", "C"): 1,
    }
    assert result.value.activity_counts == (("A", 4), ("B", 2), ("C", 1))
    assert result.value.empty_trace_count == 1
    assert result.value.start_counts == (("A", 2),)
    assert result.value.end_counts == (("A", 1), ("C", 1))


def test_eventual_follows_counts_positions_not_only_unique_label_pairs():
    result = discover_efg(log_of("ABABA", "AC", ""))
    assert edge_counts(result) == {
        ("A", "A"): 3,
        ("A", "B"): 3,
        ("B", "A"): 3,
        ("B", "B"): 1,
        ("A", "C"): 1,
    }
    assert result.value.examined_event_pairs == 11


def test_pair_limit_reports_lower_bound_without_truncating_population_counts():
    result = discover_efg(
        log_of("ABABA", "AC"), RelationDiscoverySpec(max_event_pairs=2)
    )
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.complete is False
    assert edge_counts(result) == {("A", "B"): 1, ("A", "A"): 1}
    assert sum(n for _, n in result.value.activity_counts) == 7
    assert result.value.trace_count == 2
    assert "event_pair_limit" in {i.code for i in result.issues}


def test_exact_pair_budget_does_not_falsely_report_partial():
    assert (
        discover_dfg(log_of("ABC"), RelationDiscoverySpec(max_event_pairs=2)).status
        == ComputeStatus.COMPUTED
    )
    assert (
        discover_efg(log_of("ABC"), RelationDiscoverySpec(max_event_pairs=3)).status
        == ComputeStatus.COMPUTED
    )


def test_footprint_bidirectional_is_observation_not_proven_concurrency():
    model = discover_footprints(log_of("ABCD", "ACBD", "EE", "")).value
    assert model.causal == (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
    assert model.parallel == (("B", "C"), ("C", "B"))
    assert ("A", "D") in model.unrelated
    assert model.loop_activities == ("E",)
    assert model.minimum_trace_length == 0
    assert model.empty_trace_count == 1


def test_footprint_budget_never_returns_incomplete_negative_relations():
    result = discover_footprints(log_of("ABC"), FootprintSpec(max_activity_pairs=2))
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_prefix_tree_keeps_duplicate_counts_and_epsilon_terminal():
    tree = discover_prefix_tree(log_of("ABC", "AB", "AB", "")).value
    states = {s.context: s for s in tree.states}
    assert set(states) == {(), ("A",), ("A", "B"), ("A", "B", "C")}
    assert states[()].initial_count == 4
    assert states[()].final_count == 1
    assert states[("A", "B")].final_count == 2
    assert states[("A", "B")].visits == 3
    assert sorted(e.occurrence_count for e in tree.transitions) == [1, 3, 3]


@pytest.mark.parametrize(
    "view,expected",
    [("sequence", ("B", "A", "A")), ("set", ("A", "B")), ("multiset", ("A", "A", "B"))],
)
def test_transition_state_abstractions(view, expected):
    tree = discover_transition_system(
        log_of("BAA"), TransitionSystemSpec(view=view, window=None)
    ).value
    assert expected in {s.context for s in tree.states if s.final_count}


def test_future_states_use_current_and_following_events_and_zero_window():
    result = discover_transition_system(
        log_of("ABC"), TransitionSystemSpec(direction="future", window=2)
    ).value
    states = {s.context: s for s in result.states}
    assert states[("A", "B")].initial_count == 1
    assert states[()].final_count == 1
    zero = discover_transition_system(
        log_of("ABC"), TransitionSystemSpec(window=0)
    ).value
    assert len(zero.states) == 1
    assert len(zero.transitions) == 3


def test_state_limits_commit_only_whole_traces_and_context_budget_is_explicit():
    result = discover_transition_system(
        log_of("A", "BC"), TransitionSystemSpec(max_states=2)
    )
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.trace_count == 1
    assert {s.context for s in result.value.states} == {(), ("A",)}
    assert (
        discover_prefix_tree(log_of("ABC"), PrefixTreeSpec(max_context_items=3)).status
        == ComputeStatus.PARTIAL
    )


BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def interval_log(*pairs, activity="A", resource="r"):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                (
                    CaseEvent(
                        f"e{i}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute("org:resource", "string", resource),
                            CaseAttribute(
                                "start_timestamp",
                                "date",
                                BASE + timedelta(seconds=start),
                            ),
                            CaseAttribute(
                                "time:timestamp", "date", BASE + timedelta(seconds=end)
                            ),
                        ),
                    ),
                ),
            )
            for i, (start, end) in enumerate(pairs)
        )
    )


@pytest.mark.parametrize(
    "pairs,kind",
    [
        (((0, 2), (0, 2)), "simultaneous"),
        (((0, 2), (0, 3)), "batching_at_start"),
        (((0, 3), (1, 3)), "batching_at_end"),
        (((0, 2), (2, 4)), "sequential"),
        (((0, 3), (1, 4)), "concurrent"),
    ],
)
def test_five_batch_classes(pairs, kind):
    result = discover_batches(interval_log(*pairs))
    assert result.status == ComputeStatus.COMPUTED
    assert len(result.value.batches) == 1
    assert result.value.batches[0].kind == kind
    assert len(result.value.batches[0].intervals) == 2


def test_duplicate_intervals_have_distinct_event_evidence():
    result = discover_batches(interval_log((0, 2), (0, 2), (0, 2))).value
    assert {x.event_id for x in result.batches[0].intervals} == {"e0", "e1", "e2"}


def test_batch_merge_distance_does_not_claim_actual_overlap():
    log = interval_log((0, 2), (4, 6))
    assert not discover_batches(log).value.batches
    merged = discover_batches(
        log, BatchDiscoverySpec(merge_distance_seconds=2)
    ).value.batches[0]
    assert merged.kind == "concurrent"
    assert merged.has_positive_gap is True


def test_batch_integer_distance_roundtrips_through_strict_result_codec(monkeypatch):
    from pix import results
    from pix.case_centric.discovery import RESULT_SCHEMAS

    original = results._schemas
    monkeypatch.setattr(results, "_schemas", lambda: {**original(), **RESULT_SCHEMAS})
    value = discover_batches(
        interval_log((0, 2), (4, 6)), BatchDiscoverySpec(merge_distance_seconds=2)
    )
    assert results.result_from_json(results.result_json_bytes(value)) == value


def test_interval_component_uses_running_max_end_not_previous_end():
    result = discover_batches(interval_log((0, 10), (1, 2), (9, 11))).value
    assert len(result.batches) == 1
    assert len(result.batches[0].intervals) == 3


def test_batch_resources_and_activities_are_not_merged():
    log = interval_log((0, 10), (1, 3))
    second = log.traces[1]
    attributes = tuple(
        replace(a, value="other") if a.key == "org:resource" else a
        for a in second.events[0].attributes
    )
    log = replace(
        log,
        traces=(
            log.traces[0],
            replace(second, events=(replace(second.events[0], attributes=attributes),)),
        ),
    )
    assert not discover_batches(log).value.batches


def test_missing_interval_not_imputed_and_invalid_interval_not_dropped():
    assert discover_batches(log_of("A")).status == ComputeStatus.UNAVAILABLE
    assert discover_batches(interval_log((3, 2))).status == ComputeStatus.UNAVAILABLE
    with pytest.raises(TypeError):
        discover_batches(case_traces(interval_log((0, 1))))


def lpm_for(result, operator, labels):
    return next(
        m
        for m in result.value.models
        if m.tree.operator == operator
        and tuple(c.activity for c in m.tree.children) == labels
    )


def test_lpm_sequence_support_is_exact_nonoverlapping_projected_window():
    result = discover_local_process_models(
        log_of("AXBAB"),
        LocalProcessModelSpec(
            selected_activities=("A", "B"),
            operators=("sequence",),
            max_leaves=2,
            maximum_models=100,
        ),
    )
    model = lpm_for(result, "sequence", ("A", "B"))
    assert model.frequency == 2
    assert model.case_support == 1
    assert model.confidence == 1
    assert model.activity_coverage == 4 / 5
    assert model.bounded_language_fit == 1
    assert model.prefix_determinism == 1
    assert model.language_is_complete
    assert tuple(o.event_ids for o in model.occurrences) == (
        ("e0-0", "e0-2"),
        ("e0-3", "e0-4"),
    )


def test_lpm_parallel_exposes_both_orders_and_bounded_prefix_determinism():
    result = discover_local_process_models(
        log_of("AB", "BA"), LocalProcessModelSpec(operators=("parallel",), max_leaves=2)
    )
    model = lpm_for(result, "parallel", ("A", "B"))
    assert model.frequency == 2
    assert model.language_word_count == 2
    assert model.bounded_language_fit == 1
    assert model.prefix_determinism == 0.75
    assert model.confidence == 1


def test_lpm_loop_maximizes_coverage_before_occurrence_count():
    result = discover_local_process_models(
        log_of("ABABA"),
        LocalProcessModelSpec(operators=("loop",), max_leaves=2, max_word_length=5),
    )
    model = lpm_for(result, "loop", ("A", "B"))
    assert model.frequency == 1
    assert model.occurrences[0].activities == tuple("ABABA")
    assert model.confidence == 1
    assert model.language_word_count == 3  # A, ABA, ABABA
    assert model.bounded_language_fit == 1 / 3
    assert model.language_is_complete is False


def test_lpm_xor_and_same_label_parallel_remain_real_tree_operators():
    result = discover_local_process_models(
        log_of("AA", "B"), LocalProcessModelSpec(max_leaves=2)
    )
    xor = lpm_for(result, "xor", ("A", "B"))
    assert xor.frequency == 3
    repeated = lpm_for(result, "parallel", ("A", "A"))
    assert repeated.language_word_count == 1
    assert repeated.frequency == 1


def test_lpm_candidate_limit_and_word_limit_are_separately_reported():
    bounded = discover_local_process_models(
        log_of("ABC"), LocalProcessModelSpec(max_candidates=1)
    )
    assert bounded.status == ComputeStatus.PARTIAL
    assert bounded.value.candidates_evaluated == 1
    assert bounded.value.search_complete is False
    words = discover_local_process_models(
        log_of("AB", "BA"),
        LocalProcessModelSpec(
            operators=("parallel",), max_leaves=2, max_language_words=1
        ),
    )
    assert words.status == ComputeStatus.PARTIAL
    assert words.value.candidates_skipped_for_language_limit == 1
    work = discover_local_process_models(
        log_of("AAAA"),
        LocalProcessModelSpec(
            operators=("parallel",), max_leaves=4, max_language_expansions=1
        ),
    )
    assert work.status == ComputeStatus.PARTIAL


def test_language_length_bound_does_not_remove_model_activities_from_denominators():
    result = discover_local_process_models(
        log_of("ACB"),
        LocalProcessModelSpec(
            operators=("xor", "sequence"),
            max_leaves=3,
            max_word_length=1,
            max_candidates=5000,
            maximum_models=5000,
        ),
    )
    model = next(
        m
        for m in result.value.models
        if m.tree.operator == "xor"
        and any(c.operator == "activity" and c.activity == "C" for c in m.tree.children)
        and any(
            c.operator == "sequence"
            and tuple(x.activity for x in c.children) == ("A", "B")
            for c in m.tree.children
        )
    )
    assert model.frequency == 1
    assert model.confidence == 0.0  # A and B are still in the model, but unmatched.
    assert model.activity_coverage == 1.0
    assert model.language_is_complete is False


def test_all_empty_log_distinguishes_absent_and_empty_traces():
    assert discover_footprints(log_of()).value.minimum_trace_length is None
    assert discover_footprints(log_of("")).value.minimum_trace_length == 0
    assert discover_local_process_models(log_of("")).value.models == ()
    assert discover_dfg(log_of("")).value.empty_trace_count == 1
    assert discover_prefix_tree(log_of("")).value.states[0].final_count == 1


@pytest.mark.parametrize(
    "fn",
    [
        discover_dfg,
        discover_efg,
        discover_footprints,
        discover_transition_system,
        discover_prefix_tree,
        discover_local_process_models,
    ],
)
def test_provenance_raw_and_preprojected_inputs_agree(fn):
    log = log_of("AB")
    projected = case_traces(log)
    direct, chained = fn(log), fn(projected)
    assert direct == chained
    assert direct.parent_computation_ids == (projected.computation_id,)
    assert direct.source_digest == projected.source_digest
    with pytest.raises(ValueError):
        fn(projected, trace_spec=CaseTraceSpec(activity_key="different"))


@pytest.mark.parametrize(
    "fn",
    [
        discover_dfg,
        discover_efg,
        discover_footprints,
        discover_transition_system,
        discover_prefix_tree,
        discover_local_process_models,
    ],
)
def test_failed_projection_propagates(fn):
    failed = case_traces(CaseLog((CaseTrace("case", (CaseEvent("event"),)),)))
    assert failed.value is None
    result = fn(failed)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.parent_computation_ids == (failed.computation_id,)


@pytest.mark.parametrize(
    "make",
    [
        lambda: RelationDiscoverySpec(counting="foo"),
        lambda: RelationDiscoverySpec(max_event_pairs=True),
        lambda: TransitionSystemSpec(view="foo"),
        lambda: TransitionSystemSpec(window=-1),
        lambda: BatchDiscoverySpec(merge_distance_seconds=float("nan")),
        lambda: LocalProcessModelSpec(max_leaves=11),
        lambda: LocalProcessModelSpec(operators=("fake",)),
    ],
)
def test_invalid_semantic_or_budget_parameters(make):
    with pytest.raises((TypeError, ValueError)):
        make()
