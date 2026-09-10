"""Hand-checkable alignment paths and adversarial search-boundary cases."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.conformance import align_traces
from pix.compute.model_semantics import fire
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def traces(*sequences):
    event_types = sorted({activity for seq in sequences for activity in seq})
    event_list = []
    relations = []
    for object_index, sequence in enumerate(sequences):
        for event_index, activity in enumerate(sequence):
            identifier = f"e{object_index}_{event_index}"
            event_list.append(
                Event(
                    identifier,
                    activity,
                    datetime(2026, 1, 1, tzinfo=timezone.utc)
                    + timedelta(seconds=event_index),
                )
            )
            relations.append(E2O(identifier, f"o{object_index}", ""))
    log = OCEL(
        object_types=(ObjectType("case"),),
        event_types=tuple(EventType(activity) for activity in event_types),
        objects=tuple(Object(f"o{i}", "case") for i in range(len(sequences))),
        events=tuple(event_list),
        e2o=tuple(relations),
    )
    return reconstruct_traces(log, TraceSpec("case"))


def sequence_net(*activities):
    return PetriNet(
        tuple(Place(f"p{i}") for i in range(len(activities) + 1)),
        tuple(Transition(f"t{i}", label) for i, label in enumerate(activities)),
        tuple(
            arc
            for i in range(len(activities))
            for arc in (
                Arc(f"p{i}", f"t{i}"),
                Arc(f"t{i}", f"p{i + 1}"),
            )
        ),
        Marking((("p0", 1),)),
        Marking(((f"p{len(activities)}", 1),)),
    )


def first(result):
    assert result.value is not None
    return result.value.alignments[0]


def assert_path(net, trace_result, alignment):
    marking = net.initial_marking
    consumed_events = []
    for move in alignment.moves:
        assert move.before_marking == marking.tokens
        if move.transition_id is not None:
            marking = fire(net, marking, move.transition_id)
        assert move.after_marking == marking.tokens
        if move.event_id is not None:
            consumed_events.append(move.event_id)
    assert marking == net.final_marking
    assert consumed_events == [
        event.event_id for event in trace_result.value.traces[0].events
    ]
    assert sum(move.cost for move in alignment.moves) == alignment.cost


def test_exact_fit_has_source_evidence_and_executable_path():
    source = traces(("A", "B"))
    net = sequence_net("A", "B")
    result = align_traces(source, net)
    alignment = first(result)
    assert result.status is ComputeStatus.COMPUTED
    assert alignment.status == "optimal"
    assert alignment.cost == 0
    assert [move.kind for move in alignment.moves] == ["synchronous", "synchronous"]
    assert [move.transition_id for move in alignment.moves] == ["t0", "t1"]
    assert result.parent_computation_ids == (source.computation_id,)
    assert result.spec.model_digest == result.value.model_digest
    assert result.value.total_cost == 0
    assert result.value.object_type == "case"
    assert result.value.mean_completed_cost_ratio == (0, 1)
    assert_path(net, source, alignment)


@pytest.mark.parametrize(
    ("observed", "expected_cost", "required_kind"),
    [
        (("A",), 1, "model"),
        (("A", "X", "B"), 1, "log"),
        (("B", "A"), 2, "log"),
    ],
)
def test_missing_extra_and_reversed_events(observed, expected_cost, required_kind):
    net = sequence_net("A", "B")
    source = traces(observed)
    alignment = first(align_traces(source, net))
    assert alignment.cost == expected_cost
    assert required_kind in {move.kind for move in alignment.moves}
    assert_path(net, source, alignment)


def test_silent_moves_use_explicit_cost_and_continue_after_trace_end():
    net = sequence_net(None, "A", None)
    source = traces(("A",))
    alignment = first(align_traces(source, net, AlignmentSpec(silent_move_cost=2)))
    assert alignment.cost == 4
    assert [move.kind for move in alignment.moves] == [
        "silent",
        "synchronous",
        "silent",
    ]
    assert_path(net, source, alignment)


def test_duplicate_labels_keep_distinct_markings_and_transition_ids():
    net = PetriNet(
        tuple(Place(name) for name in ("start", "dead", "good", "end")),
        (Transition("a_bad", "A"), Transition("a_good", "A"), Transition("b", "B")),
        (
            Arc("start", "a_bad"),
            Arc("a_bad", "dead"),
            Arc("start", "a_good"),
            Arc("a_good", "good"),
            Arc("good", "b"),
            Arc("b", "end"),
        ),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )
    source = traces(("A", "B"))
    alignment = first(align_traces(source, net))
    assert alignment.cost == 0
    assert tuple(move.transition_id for move in alignment.moves) == ("a_good", "b")
    assert_path(net, source, alignment)


def test_goal_is_settled_not_accepted_when_first_generated():
    net = PetriNet(
        tuple(Place(name) for name in ("start", "middle", "end")),
        (Transition("direct", "A"), Transition("s1"), Transition("s2")),
        (
            Arc("start", "direct"),
            Arc("direct", "end"),
            Arc("start", "s1"),
            Arc("s1", "middle"),
            Arc("middle", "s2"),
            Arc("s2", "end"),
        ),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )
    alignment = first(
        align_traces(
            traces(()),
            net,
            AlignmentSpec(
                model_move_cost=10,
                silent_move_cost=1,
            ),
        )
    )
    assert alignment.cost == 2
    assert tuple(move.transition_id for move in alignment.moves) == ("s1", "s2")


def test_log_and_model_moves_may_be_cheaper_than_synchronous():
    alignment = first(
        align_traces(
            traces(("A",)),
            sequence_net("A"),
            AlignmentSpec(
                synchronous_move_cost=10,
            ),
        )
    )
    assert alignment.cost == 2
    assert {move.kind for move in alignment.moves} == {"log", "model"}


def test_empty_trace_accepts_initial_final_with_one_state_budget():
    result = align_traces(traces(()), sequence_net(), AlignmentSpec(max_states=1))
    alignment = first(result)
    assert alignment.status == "optimal"
    assert alignment.settled_states == 1
    assert alignment.moves == ()
    assert alignment.cost == 0


def test_empty_population_has_zero_total_but_no_mean():
    result = align_traces(traces(), sequence_net())
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.coverage.requested == 0
    assert result.value.total_cost == 0
    assert result.value.mean_completed_cost_ratio is None


def test_weighted_arcs_preserve_concrete_marking_evidence():
    net = PetriNet(
        (Place("start"), Place("end")),
        (Transition("t", "A"),),
        (Arc("start", "t", 2), Arc("t", "end", 3)),
        Marking((("start", 2),)),
        Marking((("end", 3),)),
    )
    source = traces(("A",))
    alignment = first(align_traces(source, net))
    assert alignment.cost == 0
    assert alignment.moves[0].after_marking == (("end", 3),)
    assert_path(net, source, alignment)


def test_finite_frontier_exhaustion_is_proven_unreachable():
    net = PetriNet(
        (Place("start"), Place("end")),
        (),
        (),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )
    result = align_traces(traces(("A",)), net, AlignmentSpec(max_states=2))
    alignment = first(result)
    assert result.status is ComputeStatus.COMPUTED
    assert alignment.status == "unreachable"
    assert alignment.cost is None
    assert alignment.settled_states == 2
    assert result.value.coverage.completed == 1
    assert result.value.coverage.unreachable == 1
    assert result.value.total_cost is None
    assert result.value.mean_completed_cost_ratio is None


def test_finite_zero_cost_cycle_does_not_revisit_markings():
    net = PetriNet(
        tuple(Place(name) for name in ("start", "middle", "end")),
        (Transition("out"), Transition("back"), Transition("self")),
        (
            Arc("start", "out"),
            Arc("out", "middle"),
            Arc("middle", "back"),
            Arc("back", "start"),
            Arc("start", "self"),
            Arc("self", "start"),
        ),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )
    alignment = first(align_traces(traces(()), net, AlignmentSpec(max_states=2)))
    assert alignment.status == "unreachable"
    assert alignment.settled_states == 2


def test_unbounded_zero_cost_token_growth_is_limited_not_unreachable():
    net = PetriNet(
        (Place("start"), Place("end")),
        (Transition("grow"),),
        (Arc("start", "grow"), Arc("grow", "start", 2)),
        Marking((("start", 1),)),
        Marking((("end", 1),)),
    )
    result = align_traces(traces(()), net, AlignmentSpec(max_states=7))
    alignment = first(result)
    assert result.status is ComputeStatus.PARTIAL
    assert alignment.status == "search_limit"
    assert alignment.settled_states == 7
    assert alignment.discovered_states == 8
    assert alignment.lower_bound_cost == 0
    assert alignment.cost is None
    assert alignment.moves == ()
    assert result.value.coverage.completed == 0
    assert result.value.coverage.search_limit == 1


def test_mixed_coverage_never_reports_whole_log_complete():
    result = align_traces(
        traces((), ("A",)), sequence_net(), AlignmentSpec(max_states=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.coverage.requested == 2
    assert result.value.coverage.optimal == 1
    assert result.value.coverage.search_limit == 1
    assert result.value.coverage.excluded == 0
    assert result.value.total_cost is None
    assert result.value.mean_completed_cost_ratio == (0, 1)
    assert result.issues[0].at == ("object", "o1")


def test_identity_covers_model_parameters_and_parent_and_is_deterministic():
    source = traces(("A",))
    net = sequence_net("A")
    result = align_traces(source, net)
    assert align_traces(source, net) == result
    assert (
        align_traces(source, net, AlignmentSpec(max_states=5)).computation_id
        != result.computation_id
    )
    assert (
        align_traces(source, sequence_net("B")).computation_id != result.computation_id
    )
    changed_parent = replace(source, computation_id=source.computation_id + "-other")
    assert align_traces(changed_parent, net).computation_id != result.computation_id
    permuted = PetriNet(
        tuple(reversed(net.places)),
        tuple(reversed(net.transitions)),
        tuple(reversed(net.arcs)),
        net.initial_marking,
        net.final_marking,
    )
    assert align_traces(source, permuted) == result


def test_unavailable_parent_retains_identity_and_does_not_fake_zero_cost():
    source = reconstruct_traces(OCEL(), TraceSpec("unknown"))
    result = align_traces(source, sequence_net())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "trace_result_unavailable"
    assert result.issues[1:] == source.issues
    assert "unknown_object_type" in {issue.code for issue in result.issues}
    assert result.parent_computation_ids == (source.computation_id,)


def test_invalid_ocel_trace_preserves_invalid_input_and_source_diagnostics():
    source = reconstruct_traces(
        OCEL(objects=(Object("undeclared", "missing"),)), TraceSpec("missing")
    )
    assert source.status is ComputeStatus.INVALID_INPUT
    result = align_traces(source, sequence_net())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "trace_result_unavailable"
    assert result.issues[1:] == source.issues
    assert source.issues
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == ()


def test_partial_trace_parent_is_unavailable_with_coverage_cause_and_identity():
    source = replace(
        traces(("A",)),
        status=ComputeStatus.PARTIAL,
        issues=(
            ComputeIssue("trace_scope_incomplete", "Some traces were not computed"),
        ),
    )
    result = align_traces(source, sequence_net("A"))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "trace_result_unavailable"
    assert result.issues[1:] == source.issues
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"log_move_cost": -1},
        {"model_move_cost": -1},
        {"silent_move_cost": -1},
        {"synchronous_move_cost": -1},
        {"max_states": 0},
    ],
)
def test_negative_costs_and_nonpositive_limit_rejected(kwargs):
    with pytest.raises(ValueError):
        AlignmentSpec(**kwargs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"log_move_cost": True},
        {"model_move_cost": 1.0},
        {"max_states": False},
    ],
)
def test_costs_and_limit_require_actual_integers(kwargs):
    with pytest.raises(TypeError):
        AlignmentSpec(**kwargs)


def test_huge_integer_costs_keep_exact_aggregate_without_float_overflow():
    huge = 10**400
    result = align_traces(
        traces(("A",)), sequence_net(), AlignmentSpec(log_move_cost=huge)
    )
    assert first(result).cost == huge
    assert result.value.total_cost == huge
    assert result.value.mean_completed_cost_ratio == (huge, 1)


def test_invalid_argument_types_fail_explicitly():
    with pytest.raises(TypeError, match="traces"):
        align_traces(None, sequence_net())
    with pytest.raises(TypeError, match="net"):
        align_traces(traces(()), None)
    with pytest.raises(TypeError, match="spec"):
        align_traces(traces(()), sequence_net(), None)
