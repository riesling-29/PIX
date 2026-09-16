"""Independent global graph costs and executable recomposition checks."""

from collections import deque
from dataclasses import FrozenInstanceError, replace
from itertools import product

import pytest

import pix.case_centric.decomposed_alignment as implementation
from pix.case_centric.decomposed_alignment import (
    DecomposedAlignmentSpec,
    align_decomposed,
    decompose_alignment_components,
)
from pix.contracts.analysis import ObjectTrace, TraceEvent, TraceSet
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(sequence)
                ),
            )
            for i, sequence in enumerate(sequences)
        )
    )


def sequence_net(prefix, *activities, weight=1):
    return PetriNet(
        tuple(Place(f"{prefix}p{i}") for i in range(len(activities) + 1)),
        tuple(
            Transition(f"{prefix}t{i}", activity)
            for i, activity in enumerate(activities)
        ),
        tuple(
            arc
            for i in range(len(activities))
            for arc in (
                Arc(f"{prefix}p{i}", f"{prefix}t{i}", weight),
                Arc(f"{prefix}t{i}", f"{prefix}p{i + 1}", weight),
            )
        ),
        Marking(((f"{prefix}p0", weight),)),
        Marking(((f"{prefix}p{len(activities)}", weight),)),
    )


def union(*nets):
    return PetriNet(
        tuple(item for net in nets for item in net.places),
        tuple(item for net in nets for item in net.transitions),
        tuple(item for net in nets for item in net.arcs),
        Marking(tuple(item for net in nets for item in net.initial_marking.tokens)),
        Marking(tuple(item for net in nets for item in net.final_marking.tokens)),
    )


def next_marking(net, tokens, transition_id):
    """Independent multiset firing; deliberately does not use PIX fire/enabling."""
    counts = dict(tokens)
    consume = [arc for arc in net.arcs if arc.target == transition_id]
    if any(counts.get(arc.source, 0) < arc.weight for arc in consume):
        return None
    for arc in consume:
        counts[arc.source] -= arc.weight
    for arc in net.arcs:
        if arc.source == transition_id:
            counts[arc.target] = counts.get(arc.target, 0) + arc.weight
    return tuple(sorted((place, count) for place, count in counts.items() if count))


def global_bellman_ford(net, word, spec):
    """Enumerate the whole bounded product graph, then relax all edges.

    This oracle never decomposes or allocates events and never calls native
    alignment, heap search or native model semantics. Fixtures have finite
    reachable state spaces; an explicit safety bound is an assertion only.
    """
    initial = 0, net.initial_marking.tokens
    seen = {initial}
    pending = deque([initial])
    edges = []
    while pending:
        position, marking = state = pending.popleft()
        outgoing = []
        if position < len(word):
            outgoing.append(((position + 1, marking), spec.log_move_cost))
        for transition in net.transitions:
            after = next_marking(net, marking, transition.id)
            if after is None:
                continue
            if transition.activity is None:
                outgoing.append(((position, after), spec.silent_move_cost))
            else:
                outgoing.append(((position, after), spec.model_move_cost))
                if position < len(word) and word[position] == transition.activity:
                    outgoing.append(((position + 1, after), spec.synchronous_move_cost))
        for target, weight in outgoing:
            edges.append((state, target, weight))
            if target not in seen:
                seen.add(target)
                pending.append(target)
        assert len(seen) < 10_000, "oracle fixture must have a small finite state space"
    distances = {initial: 0}
    for _ in range(len(seen) - 1):
        changed = False
        for source, target, weight in edges:
            if source in distances:
                candidate = distances[source] + weight
                if target not in distances or candidate < distances[target]:
                    distances[target] = candidate
                    changed = True
        if not changed:
            break
    return distances.get((len(word), net.final_marking.tokens))


def check_witness(net, trace, actual, spec):
    marking = net.initial_marking.tokens
    position = 0
    activities = {t.id: t.activity for t in net.transitions}
    for move in actual.moves:
        assert move.before_marking == marking
        if move.kind in ("log", "synchronous"):
            event = trace.events[position]
            assert (move.event_id, move.activity) == (event.event_id, event.activity)
            position += 1
        else:
            assert move.event_id is None
        if move.kind != "log":
            assert activities[move.transition_id] == move.activity
            after = next_marking(net, marking, move.transition_id)
            assert after is not None
            marking = after
        else:
            assert move.transition_id is None
        assert (
            move.cost
            == {
                "log": spec.log_move_cost,
                "model": spec.model_move_cost,
                "silent": spec.silent_move_cost,
                "synchronous": spec.synchronous_move_cost,
            }[move.kind]
        )
        assert move.after_marking == marking
    assert position == len(trace.events)
    assert marking == net.final_marking.tokens
    assert sum(move.cost for move in actual.moves) == actual.best_known_cost
    assert actual.witness_validated


@pytest.mark.parametrize(
    "left,right",
    [
        (("A",), ("B",)),
        (("A",), ("A",)),
        (("A", "B"), ("A", "A")),
        ((None, "A"), ("B", None)),
    ],
)
@pytest.mark.parametrize(
    "costs",
    [
        AlignmentSpec(),
        AlignmentSpec(
            log_move_cost=0,
            model_move_cost=2,
            synchronous_move_cost=3,
            silent_move_cost=1,
        ),
        AlignmentSpec(
            log_move_cost=3,
            model_move_cost=0,
            synchronous_move_cost=1,
            silent_move_cost=2,
        ),
        AlignmentSpec(
            log_move_cost=0,
            model_move_cost=0,
            synchronous_move_cost=0,
            silent_move_cost=0,
        ),
    ],
)
def test_matches_independent_global_bellman_ford(left, right, costs):
    net = union(sequence_net("a", *left), sequence_net("b", *right))
    words = tuple(word for length in range(4) for word in product("ABX", repeat=length))
    source = case_traces(log(*words))
    result = align_decomposed(source, net, DecomposedAlignmentSpec(costs))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.optimal_count == len(words)
    assert result.value.total_cost == sum(item.cost for item in result.value.traces)
    for word, trace, actual in zip(words, source.value.traces, result.value.traces):
        assert actual.cost == global_bellman_ford(net, word, costs)
        assert actual.cost == actual.lower_bound_cost
        assert actual.allocations_exhausted
        check_witness(net, trace, actual, costs)


def test_partition_preserves_every_weighted_arc_node_and_marking():
    net = union(sequence_net("a", "A", weight=2), sequence_net("b", "B", weight=3))
    components = decompose_alignment_components(net)
    assert len(components) == 2
    assert {node.id for part in components for node in part.model.places} == {
        node.id for node in net.places
    }
    assert {node.id for part in components for node in part.model.transitions} == {
        node.id for node in net.transitions
    }
    assert set(arc for part in components for arc in part.model.arcs) == set(net.arcs)
    assert (
        Marking(
            tuple(
                pair
                for part in components
                for pair in part.model.initial_marking.tokens
            )
        )
        == net.initial_marking
    )
    result = align_decomposed(log("BA"), net)
    assert result.value.traces[0].cost == 0
    check_witness(
        net,
        case_traces(log("BA")).value.traces[0],
        result.value.traces[0],
        AlignmentSpec(),
    )


@pytest.mark.parametrize(
    "costs",
    [AlignmentSpec(), AlignmentSpec(synchronous_move_cost=3, model_move_cost=0)],
)
def test_finite_cyclic_components_match_global_graph(costs):
    looping = PetriNet(
        (Place("ap"),),
        (Transition("aa", "A"), Transition("tau")),
        (Arc("ap", "aa", 2), Arc("aa", "ap", 2), Arc("ap", "tau"), Arc("tau", "ap")),
        Marking((("ap", 2),)),
        Marking((("ap", 2),)),
    )
    net = union(looping, sequence_net("b", "A", "B"))
    words = tuple(word for length in range(4) for word in product("AB", repeat=length))
    source = case_traces(log(*words))
    result = align_decomposed(source, net, DecomposedAlignmentSpec(costs))
    assert result.status is ComputeStatus.COMPUTED
    for trace, word, actual in zip(source.value.traces, words, result.value.traces):
        assert actual.cost == global_bellman_ford(net, word, costs)
        check_witness(net, trace, actual, costs)


def test_settled_state_cap_includes_accepting_initial_state():
    net = union(sequence_net("a"), sequence_net("b"))
    actual = align_decomposed(
        log("X"), net, DecomposedAlignmentSpec(AlignmentSpec(max_states=1))
    ).value.traces[0]
    assert actual.status == "optimal"
    assert actual.cost == 1
    assert actual.settled_states == 2


def test_mixed_population_never_reports_partial_cost_as_whole_log_cost():
    net = union(sequence_net("a", "A"), sequence_net("b", "A"))
    result = align_decomposed(
        log("", "A"), net, DecomposedAlignmentSpec(max_allocations=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.optimal_count == result.value.limited_count == 1
    assert result.value.completed_cost_sum == 2
    assert result.value.total_cost is None


def test_shared_activity_is_never_synchronized_twice_or_charged_twice():
    net = union(sequence_net("a", "A"), sequence_net("b", "A"))
    actual = align_decomposed(log("A", "AA", "AXA"), net).value.traces
    assert [item.cost for item in actual] == [1, 0, 1]
    assert [item.allocation_space_size for item in actual] == [2, 4, 4]
    assert (
        sum(move.kind == "log" and move.activity == "X" for move in actual[2].moves)
        == 1
    )
    assert sum(move.kind == "synchronous" for move in actual[0].moves) == 1


def test_occurrence_allocation_must_vary_for_same_label():
    net = union(sequence_net("a", "A", "B"), sequence_net("b", "A", "C"))
    actual = align_decomposed(log("ACAB"), net).value.traces[0]
    assert actual.cost == 0
    assert actual.best_event_owners == (1, 1, 0, 0)
    assert actual.local_search_count == 2 * len(actual.allocations)


def test_repeated_subproblem_cache_preserves_distinct_occurrences():
    net = union(sequence_net("a", "A"), sequence_net("b", "A"), sequence_net("c", "B"))
    actual = align_decomposed(log("AAB"), net).value.traces[0]
    assert actual.cost == 0
    assert actual.local_search_count == 9
    assert actual.local_search_count < 3 * len(actual.allocations)


def test_allocation_cap_retains_executable_incumbent_without_claiming_optimality():
    net = union(sequence_net("a", "A", "B"), sequence_net("b", "A", "C"))
    source = case_traces(log("ACAB"))
    result = align_decomposed(source, net, DecomposedAlignmentSpec(max_allocations=1))
    actual = result.value.traces[0]
    assert result.status is ComputeStatus.PARTIAL
    assert actual.status == "search_limit"
    assert actual.cost is None and result.value.total_cost is None
    assert actual.best_known_cost > 0
    assert actual.lower_bound_cost == 0
    assert actual.allocation_space_size is None
    assert actual.allocation_space_size_lower_bound == 2
    assert not actual.allocations_exhausted
    check_witness(net, source.value.traces[0], actual, AlignmentSpec())


def test_exact_allocation_cap_boundary_is_exhausted():
    net = union(sequence_net("a", "A"), sequence_net("b", "A"))
    actual = align_decomposed(
        log("AA"), net, DecomposedAlignmentSpec(max_allocations=4)
    ).value.traces[0]
    assert actual.status == "optimal"
    assert len(actual.allocations) == actual.allocation_space_size == 4
    assert actual.allocations_exhausted


def test_allocation_cap_larger_than_machine_integer_is_valid_on_small_input():
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    actual = align_decomposed(
        log("AB"), net, DecomposedAlignmentSpec(max_allocations=2**64)
    ).value.traces[0]
    assert actual.status == "optimal"
    assert actual.cost == 0
    assert actual.allocation_space_size == 1


def test_unknown_cost_is_a_sound_bound_for_unvisited_allocations():
    net = union(sequence_net("a", "A"), sequence_net("b", "A"))
    costs = AlignmentSpec(log_move_cost=5, model_move_cost=2)
    actual = align_decomposed(
        log("AX"), net, DecomposedAlignmentSpec(costs, 1)
    ).value.traces[0]
    assert actual.lower_bound_cost == 5
    assert actual.best_known_cost == 7
    assert actual.status == "search_limit"


def test_empty_projection_still_completes_component_with_model_and_silent_moves():
    net = union(sequence_net("a", "A", None), sequence_net("b", None, "B"))
    costs = AlignmentSpec(silent_move_cost=2)
    source = case_traces(log("A"))
    actual = align_decomposed(source, net, DecomposedAlignmentSpec(costs)).value.traces[
        0
    ]
    assert actual.cost == 5
    assert actual.component_evidence[1].event_positions == ()
    assert actual.component_evidence[1].alignment.cost == 3
    check_witness(net, source.value.traces[0], actual, costs)


def test_expensive_synchronous_move_can_be_replaced_with_log_and_model():
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    costs = AlignmentSpec(synchronous_move_cost=3)
    actual = align_decomposed(
        log("AB"), net, DecomposedAlignmentSpec(costs)
    ).value.traces[0]
    assert actual.cost == 4
    assert not any(move.kind == "synchronous" for move in actual.moves)


def test_duplicate_transition_labels_within_one_component_are_preserved():
    left = PetriNet(
        (Place("ap"), Place("aq")),
        (Transition("at1", "A"), Transition("at2", "A")),
        (Arc("ap", "at1"), Arc("ap", "at2"), Arc("at1", "aq"), Arc("at2", "aq")),
        Marking((("ap", 1),)),
        Marking((("aq", 1),)),
    )
    net = union(left, sequence_net("b", "B"))
    actual = align_decomposed(log("BA"), net).value.traces[0]
    assert actual.cost == 0
    assert actual.allocation_space_size == 1
    assert {t.id for t in decompose_alignment_components(net)[0].model.transitions} == {
        "at1",
        "at2",
    }


def test_isolated_place_mismatch_proves_unreachable_without_inventing_tokens():
    isolated = PetriNet(
        (Place("z"),), (), (), Marking((("z", 2),)), Marking((("z", 1),))
    )
    net = union(sequence_net("a", "A"), isolated)
    result = align_decomposed(log("A"), net)
    actual = result.value.traces[0]
    assert result.status is ComputeStatus.COMPUTED
    assert actual.status == "unreachable"
    assert actual.cost is actual.best_known_cost is actual.lower_bound_cost is None
    assert not actual.witness_validated
    assert result.value.unreachable_count == 1
    assert result.value.total_cost is None


def test_local_unreachable_with_shared_labels_proves_all_allocations_unreachable():
    impossible = replace(sequence_net("a", "A"), initial_marking=Marking())
    net = union(impossible, sequence_net("b", "A"))
    actual = align_decomposed(log("AAAA"), net).value.traces[0]
    assert actual.status == "unreachable"
    assert len(actual.allocations) == 1
    assert not actual.allocations_exhausted


def test_isolated_visible_transition_and_unobserved_component_are_supported():
    isolated = PetriNet((), (Transition("free", "X"),), (), Marking(), Marking())
    net = union(isolated, sequence_net("a", "A"))
    actual = align_decomposed(log("XAX"), net).value.traces[0]
    assert actual.cost == 0
    assert len(actual.moves) == 3


def test_local_state_limit_does_not_claim_unreachable_or_a_whole_cost():
    growing = PetriNet(
        (Place("p"),),
        (Transition("grow"),),
        (Arc("p", "grow"), Arc("grow", "p", 2)),
        Marking((("p", 1),)),
        Marking(),
    )
    net = union(growing, sequence_net("a", "A"))
    costs = AlignmentSpec(max_states=8)
    result = align_decomposed(log("A"), net, DecomposedAlignmentSpec(costs))
    actual = result.value.traces[0]
    assert result.status is ComputeStatus.PARTIAL
    assert actual.status == "search_limit"
    assert actual.best_known_cost is actual.cost is None
    assert actual.lower_bound_cost == 0
    assert actual.allocations_exhausted
    assert actual.local_search_count == 2
    assert not actual.witness_validated


def test_duplicate_event_ids_are_handled_by_occurrence_index():
    source = case_traces(log("AB"))
    events = (TraceEvent("same", "A", None, ()), TraceEvent("same", "B", None, ()))
    source = replace(
        source, value=TraceSet("case", (ObjectTrace("case1", "case", events),))
    )
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    actual = align_decomposed(source, net).value.traces[0]
    assert actual.cost == 0
    assert actual.event_ids == ("same", "same")
    check_witness(net, source.value.traces[0], actual, AlignmentSpec())


@pytest.mark.parametrize(
    "net", [sequence_net("a", "A"), PetriNet((), (), (), Marking(), Marking())]
)
def test_no_global_alignment_fallback_for_non_decomposable_net(net, monkeypatch):
    def forbid(*args):
        raise AssertionError(
            "global alignment must not be used under a decomposed label"
        )

    monkeypatch.setattr(implementation, "_align", forbid)
    result = align_decomposed(log("A"), net)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "no_nontrivial_decomposition"


def test_searches_are_genuine_component_subproblems(monkeypatch):
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    original = implementation._align
    searched = []

    def instrument(trace, component, spec):
        assert component != net
        assert len(component.transitions) == 1
        searched.append((tuple(event.activity for event in trace.events), component))
        return original(trace, component, spec)

    monkeypatch.setattr(implementation, "_align", instrument)
    actual = align_decomposed(log("AXB"), net).value.traces[0]
    assert actual.cost == 1
    assert [item[0] for item in searched] == [("A",), ("B",)]


def test_invalid_recomposition_never_leaks_an_optimal_cost(monkeypatch):
    original = implementation._align

    def corrupt(trace, net, spec):
        result = original(trace, net, spec)
        if result.moves:
            bad = replace(result.moves[0], before_marking=())
            return replace(result, moves=(bad, *result.moves[1:]))
        return result

    monkeypatch.setattr(implementation, "_align", corrupt)
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    result = align_decomposed(log("AB"), net)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces[0].status == "invalid_witness"
    assert result.value.total_cost is result.value.traces[0].best_known_cost is None
    assert result.issues[-1].code == "decomposed_alignment_invalid_witness"


def test_empty_log_is_not_an_empty_trace():
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    empty = align_decomposed(log(), net).value
    assert empty.total_cost == empty.optimal_count == 0
    assert empty.traces == ()
    trace = align_decomposed(log(""), net).value.traces[0]
    assert trace.cost == 2
    assert trace.allocations_exhausted


@pytest.mark.parametrize(
    "status,expected",
    [
        (ComputeStatus.INVALID_INPUT, ComputeStatus.INVALID_INPUT),
        (ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE),
        (ComputeStatus.UNAVAILABLE, ComputeStatus.UNAVAILABLE),
    ],
)
def test_upstream_incomplete_status_and_issues_survive(status, expected):
    source = case_traces(log("AB"))
    source = replace(
        source,
        status=status,
        value=source.value if status is ComputeStatus.PARTIAL else None,
        issues=(ComputeIssue("original_problem", "details"),),
    )
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    result = align_decomposed(source, net)
    assert result.status is expected
    assert result.value is None
    assert result.issues[0].code == "original_problem"
    assert result.parent_computation_ids == (source.computation_id,)


def test_identity_covers_model_costs_allocation_cap_and_source():
    net = union(sequence_net("a", "A"), sequence_net("b", "B"))
    source = case_traces(log("AB"))
    baseline = align_decomposed(source, net)
    assert baseline == align_decomposed(source, net)
    variants = [
        align_decomposed(source, replace(net, final_marking=Marking())),
        align_decomposed(source, net, DecomposedAlignmentSpec(max_allocations=1)),
        align_decomposed(
            source, net, DecomposedAlignmentSpec(AlignmentSpec(log_move_cost=3))
        ),
        align_decomposed(log("BA"), net),
    ]
    assert all(result.computation_id != baseline.computation_id for result in variants)
    with pytest.raises(FrozenInstanceError):
        baseline.value.components[0].index = 7


@pytest.mark.parametrize(
    "value,exception",
    [(True, TypeError), (1.0, TypeError), (0, ValueError), (-1, ValueError)],
)
def test_invalid_allocation_limits_are_rejected(value, exception):
    with pytest.raises(exception):
        DecomposedAlignmentSpec(max_allocations=value)


def test_invalid_input_types_are_rejected():
    with pytest.raises(TypeError):
        DecomposedAlignmentSpec(alignment=None)
    with pytest.raises(TypeError):
        decompose_alignment_components(None)
    with pytest.raises(TypeError):
        align_decomposed(log(""), None)
    with pytest.raises(TypeError):
        align_decomposed(log(""), sequence_net("a", "A"), None)


@pytest.mark.parametrize(
    "status", ["optimal", "search_limit", "unreachable", "unavailable"]
)
def test_result_round_trip_uses_explicit_schema_whitelist(monkeypatch, status):
    import pix.results as persistence

    original = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: {**original(), **implementation.RESULT_SCHEMAS}
    )
    left, right = sequence_net("a", "A"), sequence_net("b", "A")
    if status == "unreachable":
        left = replace(left, initial_marking=Marking())
    net = left if status == "unavailable" else union(left, right)
    spec = (
        DecomposedAlignmentSpec(max_allocations=1)
        if status == "search_limit"
        else DecomposedAlignmentSpec()
    )
    result = align_decomposed(log("AA"), net, spec)
    if status != "unavailable":
        assert result.value.traces[0].status == status
    else:
        assert result.status is ComputeStatus.UNAVAILABLE
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result
