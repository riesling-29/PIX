"""Hand-worked replay paths, weighted accounting, and incomplete search coverage."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.replay import replay_traces
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.replay import ReplaySpec, TokenCounts
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def traces(*sequences):
    events = []
    relations = []
    for object_number, sequence in enumerate(sequences):
        for event_number, activity in enumerate(sequence):
            event_id = f"e{object_number}.{event_number}"
            events.append(
                Event(event_id, activity, ORIGIN + timedelta(seconds=event_number))
            )
            relations.append(E2O(event_id, f"o{object_number}", ""))
    log = OCEL(
        event_types=tuple(EventType(a) for a in sorted({e.type for e in events})),
        object_types=(ObjectType("order"),),
        events=tuple(events),
        objects=tuple(Object(f"o{i}", "order") for i in range(len(sequences))),
        e2o=tuple(relations),
    )
    return reconstruct_traces(log, TraceSpec("order"))


def marking(**tokens):
    return Marking(tuple(tokens.items()))


def sequence_net():
    return PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("p", "a"), Arc("a", "q"), Arc("q", "b"), Arc("b", "r")),
        marking(p=1),
        marking(r=1),
    )


def case(result):
    assert result.value is not None
    return result.value.traces[0]


def transition_ids(replay):
    return tuple(
        step.transition_id for step in replay.steps if step.transition_id is not None
    )


def test_exact_fit_retains_event_transition_and_marking_evidence():
    result = replay_traces(traces(("A", "B")), sequence_net())
    observed = case(result)
    assert result.status is ComputeStatus.COMPUTED
    assert observed.counts == TokenCounts(0, 0, 3, 3)
    assert observed.final_reached is True
    assert observed.status == "completed"
    assert observed.ending_marking == ()
    assert transition_ids(observed) == ("a", "b")
    step = observed.steps[1]
    assert (step.event_id, step.activity, step.transition_id) == ("e0.0", "A", "a")
    assert step.marking_before == (("p", 1),)
    assert step.marking_after == (("q", 1),)
    assert step.inserted_tokens == ()
    assert observed.steps[0].produced_tokens == (("p", 1),)
    assert observed.steps[-1].consumed_tokens == (("r", 1),)


def test_missing_activity_inserts_input_and_retains_original_surplus():
    observed = case(replay_traces(traces(("B",)), sequence_net()))
    assert observed.counts == TokenCounts(
        missing=1, remaining=1, consumed=2, produced=2
    )
    assert observed.steps[1].inserted_tokens == (("q", 1),)
    assert observed.steps[1].marking_before == (("p", 1),)
    assert observed.steps[1].marking_after == (("p", 1), ("r", 1))
    assert observed.ending_marking == (("p", 1),)
    assert observed.final_reached is False


def test_unknown_activity_is_explicit_log_deviation_with_unchanged_marking():
    result = replay_traces(traces(("A", "Unknown", "B")), sequence_net())
    observed = case(result)
    assert observed.log_deviation_count == 1
    assert observed.processed_event_count == 3
    assert observed.counts == TokenCounts(0, 0, 3, 3)
    deviation = observed.steps[2]
    assert deviation.kind == "log_deviation"
    assert (deviation.event_id, deviation.activity) == ("e0.1", "Unknown")
    assert deviation.transition_id is None
    assert deviation.marking_before == deviation.marking_after == (("q", 1),)
    assert result.value.log_deviation_count == 1


def test_weighted_arcs_final_consumption_and_surplus_are_hand_counted():
    net = PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "A"),),
        (Arc("p", "a", 2), Arc("a", "q", 3)),
        marking(p=1),
        marking(q=2),
    )
    observed = case(replay_traces(traces(("A",)), net))
    assert observed.counts == TokenCounts(
        missing=1, remaining=1, consumed=4, produced=4
    )
    assert observed.steps[1].inserted_tokens == (("p", 1),)
    assert observed.steps[1].consumed_tokens == (("p", 2),)
    assert observed.steps[1].produced_tokens == (("q", 3),)
    assert observed.ending_marking == (("q", 1),)
    assert observed.final_reached is False


def test_silent_path_before_visible_and_after_visible_is_committed_as_evidence():
    net = PetriNet(
        tuple(Place(p) for p in ("p", "q", "r", "s")),
        (Transition("before"), Transition("a", "A"), Transition("after")),
        (
            Arc("p", "before"),
            Arc("before", "q"),
            Arc("q", "a"),
            Arc("a", "r"),
            Arc("r", "after"),
            Arc("after", "s"),
        ),
        marking(p=1),
        marking(s=1),
    )
    observed = case(replay_traces(traces(("A",)), net))
    assert transition_ids(observed) == ("before", "a", "after")
    assert observed.counts == TokenCounts(0, 0, 4, 4)
    assert observed.final_reached is True
    assert observed.steps[1].event_id is None
    assert observed.steps[1].kind == observed.steps[3].kind == "silent"


def test_duplicate_labels_choose_ids_deterministically_without_optimum_claim():
    net = PetriNet(
        tuple(Place(p) for p in ("p", "q", "r", "dead")),
        (Transition("a_dead", "A"), Transition("z_good", "A"), Transition("b", "B")),
        (
            Arc("p", "a_dead"),
            Arc("a_dead", "dead"),
            Arc("p", "z_good"),
            Arc("z_good", "q"),
            Arc("q", "b"),
            Arc("b", "r"),
        ),
        marking(p=1),
        marking(r=1),
    )
    source = traces(("A", "B"))
    observed = case(replay_traces(source, net))
    reordered = replace(net, transitions=net.transitions[::-1], arcs=net.arcs[::-1])
    assert case(replay_traces(source, reordered)) == observed
    assert transition_ids(observed) == ("a_dead", "b")
    assert observed.counts == TokenCounts(1, 1, 3, 3)
    # z_good then b would fit. This explicitly tests a local heuristic, not an alignment.


def test_zero_silent_hops_precede_lexically_smaller_reachable_match():
    net = PetriNet(
        (Place("p"), Place("q"), Place("end")),
        (Transition("tau"), Transition("a_indirect", "A"), Transition("z_direct", "A")),
        (
            Arc("p", "tau"),
            Arc("tau", "q"),
            Arc("q", "a_indirect"),
            Arc("a_indirect", "end"),
            Arc("p", "z_direct"),
            Arc("z_direct", "end"),
        ),
        marking(p=1),
        marking(end=1),
    )
    assert transition_ids(case(replay_traces(traces(("A",)), net))) == ("z_direct",)


def test_exhaustive_silent_closure_selects_least_token_repair():
    net = PetriNet(
        (Place("p"), Place("q"), Place("end")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "q"), Arc("q", "a", 2), Arc("a", "end")),
        marking(p=1),
        marking(end=1),
    )
    observed = case(replay_traces(traces(("A",)), net))
    assert transition_ids(observed) == ("tau", "a")
    assert observed.searches[0].exhaustive is True
    assert observed.steps[2].inserted_tokens == (("q", 1),)
    assert observed.counts == TokenCounts(1, 0, 4, 3)


def test_finite_silent_self_loop_deduplicates_marking_without_false_limit():
    net = PetriNet(
        (Place("p"), Place("q")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "p"), Arc("q", "a"), Arc("a", "q")),
        marking(p=1),
        marking(p=1),
    )
    observed = case(replay_traces(traces(("A",)), net, ReplaySpec(1)))
    assert observed.status == "completed"
    assert observed.searches[0].state_count == 1
    assert observed.searches[0].exhaustive is True
    assert transition_ids(observed) == ("a",)


def test_bound_counts_initial_state_and_never_fabricates_missing_tokens():
    net = PetriNet(
        (Place("p"), Place("q"), Place("end")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "q"), Arc("q", "a"), Arc("a", "end")),
        marking(p=1),
        marking(end=1),
    )
    limited = replay_traces(traces(("A",)), net, ReplaySpec(1))
    observed = case(limited)
    assert limited.status is ComputeStatus.PARTIAL
    assert observed.status == "limited"
    assert observed.counts == TokenCounts(0, 1, 0, 1)
    assert observed.processed_event_count == 0
    assert observed.final_reached is None
    assert transition_ids(observed) == ()
    assert observed.searches[0].limited is True
    assert observed.searches[0].state_count == 1
    assert limited.value.completed_count == 0
    assert limited.value.limited_count == 1
    assert limited.value.unprocessed_event_count == 1
    assert limited.value.completed_counts == TokenCounts()
    enough = replay_traces(traces(("A",)), net, ReplaySpec(2))
    assert enough.status is ComputeStatus.COMPUTED
    assert case(enough).counts == TokenCounts(0, 0, 3, 3)


def test_unbounded_silent_growth_returns_limited_and_retains_prefix():
    net = PetriNet(
        (Place("p"), Place("q")),
        (Transition("grow"), Transition("a", "A")),
        (Arc("grow", "p"), Arc("q", "a"), Arc("a", "q")),
        Marking(),
        Marking(),
    )
    result = replay_traces(traces(("Unknown", "A")), net, ReplaySpec(3))
    observed = case(result)
    assert result.status is ComputeStatus.PARTIAL
    assert observed.processed_event_count == observed.log_deviation_count == 1
    assert observed.searches[0].state_count == 3
    assert observed.counts == TokenCounts()
    assert observed.steps[-1].kind == "log_deviation"


def test_queued_goal_is_checked_when_another_silent_branch_exceeds_budget():
    net = PetriNet(
        tuple(Place(p) for p in ("p", "q", "other", "end")),
        (Transition("a_path"), Transition("z_other"), Transition("visible", "A")),
        (
            Arc("p", "a_path"),
            Arc("a_path", "q"),
            Arc("p", "z_other"),
            Arc("z_other", "other"),
            Arc("q", "visible"),
            Arc("visible", "end"),
        ),
        marking(p=1),
        marking(end=1),
    )
    result = replay_traces(traces(("A",)), net, ReplaySpec(2))
    assert result.status is ComputeStatus.COMPUTED
    assert transition_ids(case(result)) == ("a_path", "visible")
    assert case(result).searches[0].state_count == 2
    assert case(result).counts == TokenCounts(0, 0, 3, 3)


def test_immediate_targets_ignore_unrelated_unbounded_silent_branch():
    net = PetriNet(
        (Place("p"), Place("q"), Place("junk")),
        (Transition("grow"), Transition("a", "A")),
        (Arc("grow", "junk"), Arc("p", "a"), Arc("a", "q")),
        marking(p=1),
        marking(q=1),
    )
    result = replay_traces(traces(("A",)), net, ReplaySpec(1))
    assert result.status is ComputeStatus.COMPUTED
    assert case(result).counts == TokenCounts(0, 0, 2, 2)
    assert transition_ids(case(result)) == ("a",)


def test_queued_final_target_is_checked_despite_an_omitted_branch():
    net = PetriNet(
        (Place("p"), Place("q"), Place("other")),
        (Transition("a_final"), Transition("z_other")),
        (
            Arc("p", "a_final"),
            Arc("a_final", "q"),
            Arc("p", "z_other"),
            Arc("z_other", "other"),
        ),
        marking(p=1),
        marking(q=1),
    )
    result = replay_traces(traces(()), net, ReplaySpec(2))
    assert result.status is ComputeStatus.COMPUTED
    assert case(result).final_reached is True
    assert transition_ids(case(result)) == ("a_final",)
    assert case(result).counts == TokenCounts(0, 0, 2, 2)


def test_final_deficit_and_surplus_are_separate_evidence():
    net = PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (),
        (),
        marking(p=1, r=1),
        marking(p=2, q=1),
    )
    observed = case(replay_traces(traces(()), net))
    assert observed.counts == TokenCounts(2, 1, 3, 2)
    assert observed.final_reached is False
    final = observed.steps[-1]
    assert final.kind == "finalize"
    assert final.marking_before == (("p", 1), ("r", 1))
    assert final.inserted_tokens == (("p", 1), ("q", 1))
    assert final.consumed_tokens == (("p", 2), ("q", 1))
    assert final.marking_after == (("r", 1),)


def test_final_search_limit_preserves_processed_coverage_but_no_completion():
    net = PetriNet(
        (Place("p"), Place("q"), Place("end")),
        (Transition("a", "A"), Transition("tau")),
        (Arc("p", "a"), Arc("a", "q"), Arc("q", "tau"), Arc("tau", "end")),
        marking(p=1),
        marking(end=1),
    )
    result = replay_traces(traces(("A",)), net, ReplaySpec(1))
    observed = case(result)
    assert result.status is ComputeStatus.PARTIAL
    assert observed.processed_event_count == observed.event_count == 1
    assert observed.final_reached is None
    assert observed.counts == TokenCounts(0, 1, 1, 2)
    assert observed.searches[-1].event_id is None
    assert observed.searches[-1].limited is True
    assert result.value.unprocessed_event_count == 0
    assert result.value.completed_count == 0


def test_mixed_completion_coverage_separates_complete_totals_from_prefixes():
    net = PetriNet(
        (Place("p"), Place("q"), Place("end")),
        (Transition("a", "A"), Transition("tau"), Transition("b", "B")),
        (
            Arc("p", "a"),
            Arc("a", "end"),
            Arc("p", "tau"),
            Arc("tau", "q"),
            Arc("q", "b"),
            Arc("b", "end"),
        ),
        marking(p=1),
        marking(end=1),
    )
    result = replay_traces(traces(("A",), ("B",)), net, ReplaySpec(1))
    assert result.status is ComputeStatus.PARTIAL
    assert (
        result.value.trace_count,
        result.value.completed_count,
        result.value.limited_count,
        result.value.excluded_count,
    ) == (2, 1, 1, 0)
    assert result.value.completed_counts == TokenCounts(0, 0, 2, 2)
    assert result.value.attempted_counts == TokenCounts(0, 1, 2, 3)
    assert result.value.event_occurrence_count == 2
    assert result.value.processed_event_count == 1


def test_empty_trace_and_empty_population_have_distinct_coverage():
    empty_net = PetriNet((), (), (), Marking(), Marking())
    one = replay_traces(traces(()), empty_net)
    assert one.value.trace_count == one.value.completed_count == 1
    assert case(one).final_reached is True
    assert case(one).counts == TokenCounts()
    none = replay_traces(traces(), empty_net)
    assert none.status is ComputeStatus.COMPUTED
    assert none.value.trace_count == none.value.completed_count == 0
    assert none.value.completed_counts == TokenCounts()


def test_shared_source_event_is_replayed_per_object_occurrence():
    log = OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("order"),),
        events=(
            Event("shared_a", "A", ORIGIN),
            Event("shared_b", "B", ORIGIN + timedelta(seconds=1)),
        ),
        objects=(Object("o1", "order"), Object("o2", "order")),
        e2o=tuple(
            E2O(e, o, "") for e in ("shared_a", "shared_b") for o in ("o1", "o2")
        ),
    )
    result = replay_traces(reconstruct_traces(log, TraceSpec("order")), sequence_net())
    assert result.value.event_occurrence_count == 4
    assert result.value.completed_counts == TokenCounts(0, 0, 6, 6)
    assert [c.steps[1].event_id for c in result.value.traces] == [
        "shared_a",
        "shared_a",
    ]


def test_request_identity_covers_model_spec_and_parent_trace_view():
    source = traces(("A", "B"))
    net = sequence_net()
    result = replay_traces(source, net)
    assert result.parent_computation_ids == (source.computation_id,)
    assert result.source_digest == source.source_digest
    assert result.spec.model_digest == result.value.model_digest
    assert replay_traces(source, net).computation_id == result.computation_id
    assert (
        replay_traces(source, net, ReplaySpec(99)).computation_id
        != result.computation_id
    )
    changed = replace(net, final_marking=marking(r=2))
    assert replay_traces(source, changed).computation_id != result.computation_id


def test_upstream_unavailability_is_not_an_empty_success():
    source = traces(("A",))
    failed = replace(
        source,
        status=ComputeStatus.UNAVAILABLE,
        value=None,
        issues=(ComputeIssue("test_upstream", "No order"),),
    )
    result = replay_traces(failed, sequence_net())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert [i.code for i in result.issues] == ["upstream_not_computed", "test_upstream"]


def test_invalid_ocel_trace_preserves_invalid_input_and_source_diagnostics():
    source = reconstruct_traces(
        OCEL(objects=(Object("undeclared", "missing"),)), TraceSpec("missing")
    )
    assert source.status is ComputeStatus.INVALID_INPUT
    result = replay_traces(source, sequence_net())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "upstream_not_computed"
    assert result.issues[1:] == source.issues
    assert source.issues
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == ()


def test_unknown_object_type_retains_unavailable_cause_and_parent_identity():
    source = reconstruct_traces(OCEL(), TraceSpec("unknown"))
    assert source.status is ComputeStatus.UNAVAILABLE
    result = replay_traces(source, sequence_net())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "upstream_not_computed"
    assert result.issues[1:] == source.issues
    assert "unknown_object_type" in {issue.code for issue in result.issues}
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)


def test_partial_trace_parent_is_unavailable_with_coverage_cause_and_identity():
    source = replace(
        traces(("A",)),
        status=ComputeStatus.PARTIAL,
        issues=(
            ComputeIssue("trace_scope_incomplete", "Some traces were not computed"),
        ),
    )
    result = replay_traces(source, sequence_net())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "upstream_not_computed"
    assert result.issues[1:] == source.issues
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5, "2"])
def test_invalid_limits_are_rejected(limit):
    with pytest.raises((TypeError, ValueError)):
        ReplaySpec(limit)


def test_result_evidence_is_immutable_and_accounting_rejects_invalid_counts():
    observed = case(replay_traces(traces(("A", "B")), sequence_net()))
    with pytest.raises(FrozenInstanceError):
        observed.counts.missing = 2
    with pytest.raises(FrozenInstanceError):
        observed.steps[0].marking_after = ()
    with pytest.raises(ValueError, match="conserve"):
        TokenCounts(missing=1)
    with pytest.raises(TypeError):
        TokenCounts(missing=True)


def test_public_function_rejects_wrong_contracts():
    with pytest.raises(TypeError):
        replay_traces((), sequence_net())
    with pytest.raises(TypeError):
        replay_traces(traces(()), None)
    with pytest.raises(TypeError):
        replay_traces(traces(()), sequence_net(), None)
