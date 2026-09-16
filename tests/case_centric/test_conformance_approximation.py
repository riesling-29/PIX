"""Subset mechanisms and certified intervals against independent full graphs."""

from collections import deque
from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

import pix.case_centric.conformance_approximation as approximation
from pix.case_centric.conformance_approximation import (
    SubsetConformanceSpec,
    approximate_conformance,
)
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"case{i}",
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def state_net(edges, initial="s", final="f", weight=1):
    return PetriNet(
        tuple(
            Place(p)
            for p in sorted({initial, final, *(p for a, b, _ in edges for p in (a, b))})
        ),
        tuple(Transition(f"t{i}", label) for i, (_, _, label) in enumerate(edges)),
        tuple(
            arc
            for i, (a, b, _) in enumerate(edges)
            for arc in (Arc(a, f"t{i}", weight), Arc(f"t{i}", b, weight))
        ),
        Marking(((initial, weight),)),
        Marking(((final, weight),)),
    )


def sequence(*word):
    return state_net(
        tuple((f"p{i}", f"p{i + 1}", label) for i, label in enumerate(word)),
        "p0",
        f"p{len(word)}",
    )


def fire_independently(net, tokens, transition):
    counts = dict(tokens)
    inputs = [arc for arc in net.arcs if arc.target == transition]
    if any(counts.get(arc.source, 0) < arc.weight for arc in inputs):
        return None
    for arc in inputs:
        counts[arc.source] -= arc.weight
    for arc in net.arcs:
        if arc.source == transition:
            counts[arc.target] = counts.get(arc.target, 0) + arc.weight
    return tuple(sorted((place, count) for place, count in counts.items() if count))


def oracle(net, word):
    """Full global product graph and Bellman-Ford; no representative selection."""
    initial = 0, net.initial_marking.tokens
    pending, seen, edges = deque([initial]), {initial}, []
    while pending:
        position, marking = state = pending.popleft()
        successors = []
        if position < len(word):
            successors.append(((position + 1, marking), 1))
        for transition in net.transitions:
            after = fire_independently(net, marking, transition.id)
            if after is None:
                continue
            successors.append(((position, after), int(transition.activity is not None)))
            if position < len(word) and transition.activity == word[position]:
                successors.append(((position + 1, after), 0))
        for target, cost in successors:
            edges.append((state, target, cost))
            if target not in seen:
                seen.add(target)
                pending.append(target)
        assert len(seen) < 5000
    distances = {initial: 0}
    for _ in range(len(seen) - 1):
        changed = False
        for source, target, cost in edges:
            if source in distances:
                candidate = distances[source] + cost
                if target not in distances or candidate < distances[target]:
                    distances[target], changed = candidate, True
        if not changed:
            break
    return distances.get((len(word), net.final_marking.tokens))


def check_witness(net, source_trace, actual):
    marking, position = net.initial_marking.tokens, 0
    labels = {t.id: t.activity for t in net.transitions}
    for move in actual.moves:
        assert marking == move.before_marking
        if move.kind in ("synchronous", "log"):
            event = source_trace.events[position]
            assert (move.event_id, move.activity) == (event.event_id, event.activity)
            position += 1
        else:
            assert move.event_id is None
        if move.kind == "log":
            assert move.transition_id is None and move.cost == 1
        else:
            assert move.activity == labels[move.transition_id]
            assert move.cost == int(move.kind == "model")
            marking = fire_independently(net, marking, move.transition_id)
            assert marking is not None
        assert marking == move.after_marking
    assert position == len(source_trace.events)
    assert marking == net.final_marking.tokens
    assert sum(move.cost for move in actual.moves) == actual.upper_bound_cost
    assert actual.witness_validated


@pytest.mark.parametrize("method", ["frequency", "random", "k_medoids", "simulation"])
@pytest.mark.parametrize(
    "net",
    [
        sequence("A", "B"),
        state_net((("s", "l", "A"), ("l", "f", "B"), ("s", "r", "A"), ("r", "f", "C"))),
        state_net((("s", "s", "A"), ("s", "f", "B"))),
        state_net((("s", "x", None), ("x", "s", None), ("s", "f", "A")), weight=2),
    ],
)
def test_intervals_contain_global_optimum_and_witness_is_executable(method, net):
    words = tuple(word for length in range(4) for word in product("ABX", repeat=length))
    source = case_traces(log(*words))
    value = approximate_conformance(
        source, net, SubsetConformanceSpec(selection_method=method, subset_size=3)
    ).value
    shortest = oracle(net, ())
    assert value.shortest_visible_length == shortest
    for trace, word, actual in zip(source.value.traces, words, value.traces):
        truth = oracle(net, word)
        assert actual.lower_bound_cost <= truth <= actual.upper_bound_cost
        if actual.exact_cost is not None:
            assert actual.exact_cost == truth
        denominator = len(word) + shortest
        fitness = Fraction(1) if denominator == 0 else 1 - Fraction(truth, denominator)
        assert (
            Fraction(*actual.fitness_lower_ratio)
            <= fitness
            <= Fraction(*actual.fitness_upper_ratio)
        )
        check_witness(net, trace, actual)


def test_only_selected_unique_variants_receive_model_alignment(monkeypatch):
    original, calls = approximation._align, []

    def record(trace, net, spec):
        calls.append(tuple(event.activity for event in trace.events))
        return original(trace, net, spec)

    monkeypatch.setattr(approximation, "_align", record)
    value = approximate_conformance(
        log("AB", "AB", "AB", "AX", "A", "BA"), sequence("A", "B")
    ).value
    assert calls == [(), ("A", "B")]
    assert value.model_search_count == 2
    assert value.selection.selected_variants == (("A", "B"),)
    assert value.representatives[0].frequency == 3


def test_selected_observed_word_differs_from_accepted_model_word():
    value = approximate_conformance(log("AX", "AX", "AB"), sequence("A", "B")).value
    representative = value.representatives[0]
    assert representative.source_variant == ("A", "X")
    assert representative.visible_word == ("A", "B")
    assert representative.exact_cost == 2
    actual = value.traces[-1]
    assert actual.exact_cost == 0
    bound = [
        item
        for item in actual.lower_bound_evidence
        if item.kind == "representative_lipschitz"
    ][0]
    assert bound.edit_distance == 2 and bound.lower_bound_cost == 0


def test_exact_anchor_lipschitz_bound_can_be_stronger_than_length_and_unknown_count():
    value = approximate_conformance(log("BB", "BB", "B"), sequence("A", "A", "A")).value
    actual = value.traces[-1]
    # B is unknown too, but the exact BB anchor proves the full 4-cost result.
    assert actual.exact_cost == 4
    bound = [
        item
        for item in actual.lower_bound_evidence
        if item.kind == "representative_lipschitz"
    ][0]
    assert bound.lower_bound_cost == 4


def test_repeated_cases_keep_their_own_event_ids_and_multiplicity():
    source = case_traces(log("AB", "AB", "A", "A", "A"))
    net = sequence("A", "B")
    value = approximate_conformance(source, net).value
    assert value.representatives[0].frequency == 3
    for trace, actual in zip(source.value.traces, value.traces):
        check_witness(net, trace, actual)
    assert value.lower_cost_sum == value.upper_cost_sum == 3
    assert Fraction(*value.mean_fitness_lower_ratio) == Fraction(4, 5)
    assert Fraction(*value.pooled_fitness_lower_ratio) == Fraction(14, 17)


def test_frequency_ties_and_random_selection_are_canonical_and_seeded():
    net = sequence("A")
    first = approximate_conformance(log("B", "A", "C"), net).value
    assert first.selection.selected_variants == (("A",),)
    spec = SubsetConformanceSpec(
        selection_method="random", subset_size=2, random_seed=14
    )
    left = approximate_conformance(log("B", "A", "C", "C"), net, spec).value
    right = approximate_conformance(log("C", "A", "B", "C"), net, spec).value
    assert left.selection.selected_variants == right.selection.selected_variants
    assert len(set(left.selection.selected_variants)) == 2


def test_weighted_k_medoids_uses_case_counts():
    spec = SubsetConformanceSpec(selection_method="k_medoids", subset_size=1)
    words = ("A",) * 5 + ("AB",) * 4 + ("ABC",) * 4
    value = approximate_conformance(log(*words), sequence("A"), spec).value
    assert value.selection.status == "completed"
    assert value.selection.selected_variants == (("A", "B"),)
    assert value.representatives[0].frequency == 4


def test_k_medoids_iteration_limit_is_explicit_without_invalidating_bounds():
    spec = SubsetConformanceSpec(
        selection_method="k_medoids", subset_size=1, k_medoids_max_iterations=1
    )
    result = approximate_conformance(
        log(*(("A",) * 5 + ("AB",) * 4 + ("ABC",) * 4)), sequence("A"), spec
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.selection.status == "iteration_limit"
    assert result.value.selection.selected_variants == (("A", "B"),)
    assert all(item.upper_bound_cost is not None for item in result.value.traces)


@pytest.mark.parametrize("method", ["frequency", "k_medoids"])
def test_distance_caps_preserve_only_sound_bounds_and_baseline_witness(method):
    net = sequence("A", "B")
    words = ("AB", "AB", "AXAX", "BBA")
    source = case_traces(log(*words))
    spec = SubsetConformanceSpec(
        selection_method=method, max_distance_cells=1, max_total_distance_cells=1
    )
    result = approximate_conformance(source, net, spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.limited_distance_pairs > 0
    for word, trace, actual in zip(words, source.value.traces, result.value.traces):
        truth = oracle(net, word)
        assert actual.lower_bound_cost <= truth <= actual.upper_bound_cost
        check_witness(net, trace, actual)
    if method == "k_medoids":
        assert result.value.selection.status == "distance_limit"


def test_no_complete_shortest_search_never_invents_fitness_denominator():
    net = state_net((("s", "s", None), ("s", "f", "A")))
    result = approximate_conformance(
        log("A", "B"), net, SubsetConformanceSpec(max_alignment_states=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.shortest_visible_length is None
    assert result.value.mean_fitness_lower_ratio is None
    for actual in result.value.traces:
        assert actual.normalization_denominator is None
        assert actual.fitness_lower_ratio is actual.fitness_upper_ratio is None
        assert actual.upper_bound_cost is None
        assert actual.status == "search_limit"


def test_simulation_can_supply_witness_even_when_shortest_search_is_limited():
    source = case_traces(log("A", "B"))
    net = sequence("A")
    spec = SubsetConformanceSpec(selection_method="simulation", max_alignment_states=1)
    result = approximate_conformance(source, net, spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.shortest_visible_length is None
    assert result.value.representatives[0].status == "simulated"
    for trace, actual in zip(source.value.traces, result.value.traces):
        assert actual.upper_bound_cost is not None
        assert actual.fitness_lower_ratio is None
        check_witness(net, trace, actual)


def test_simulation_step_and_attempt_limits_are_reported():
    net = sequence(None, None, "A")
    spec = SubsetConformanceSpec(
        selection_method="simulation", simulation_max_steps=2, simulation_max_attempts=3
    )
    result = approximate_conformance(log("A"), net, spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.selection.status == "simulation_limit"
    assert result.value.selection.simulation_attempts == 3
    assert result.value.representatives == ()
    assert result.value.traces[0].upper_bound_cost == 2


def test_trailing_silent_and_repeated_transition_occurrences_are_preserved():
    net = state_net((("s", "s", "A"), ("s", "x", "B"), ("x", "f", None)))
    source = case_traces(log("AAB", "AAB", "AXAB"))
    value = approximate_conformance(source, net).value
    assert value.representatives[0].transition_ids == ("t0", "t0", "t1", "t2")
    for trace, actual in zip(source.value.traces, value.traces):
        check_witness(net, trace, actual)
        assert actual.moves[-1].kind == "silent"


def test_empty_language_is_proven_by_exhaustion_not_by_simulation_failure():
    net = state_net(())
    result = approximate_conformance(log("A", ""), net)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.unreachable_case_count == 2
    assert result.value.lower_cost_sum is result.value.upper_cost_sum is None
    assert result.value.model_search_count == 1
    assert result.value.selection.status == "not_required"


def test_empty_population_and_empty_accepted_trace_are_distinct(monkeypatch):
    net = sequence()
    original = approximation._align

    def forbid(*args):
        raise AssertionError("empty population requires no model search")

    monkeypatch.setattr(approximation, "_align", forbid)
    value = approximate_conformance(log(), net).value
    assert value.traces == () and value.model_search_count == 0
    assert value.lower_cost_sum == value.upper_cost_sum == 0
    assert value.mean_fitness_lower_ratio is None
    monkeypatch.setattr(approximation, "_align", original)
    value = approximate_conformance(log(""), net).value
    assert value.model_search_count == 1
    assert value.traces[0].normalization_denominator == 0
    assert value.traces[0].exact_cost == 0
    assert (
        value.traces[0].fitness_lower_ratio
        == value.traces[0].fitness_upper_ratio
        == (1, 1)
    )


def test_rejected_empty_witness_cannot_crash_or_publish_whole_fitness(monkeypatch):
    original = approximation._realize

    def reject_empty(trace, net, path, operations):
        if not trace.events:
            raise ValueError("injected witness rejection")
        return original(trace, net, path, operations)

    monkeypatch.setattr(approximation, "_realize", reject_empty)
    result = approximate_conformance(log("", "A"), sequence())
    assert result.status is ComputeStatus.PARTIAL
    empty, nonempty = result.value.traces
    assert empty.status == "invalid_witness"
    assert (
        empty.upper_bound_cost
        is empty.fitness_lower_ratio
        is empty.fitness_upper_ratio
        is None
    )
    assert nonempty.upper_bound_cost == 1
    assert result.value.upper_cost_sum is None
    assert (
        result.value.mean_fitness_lower_ratio
        is result.value.pooled_fitness_lower_ratio
        is None
    )


@pytest.mark.parametrize("method", ["frequency", "random", "k_medoids"])
def test_all_unique_variants_selected_produces_exact_costs(method):
    net = sequence("A", "B")
    value = approximate_conformance(
        log("AB", "AA", "B", ""),
        net,
        SubsetConformanceSpec(selection_method=method, subset_size=100),
    ).value
    assert value.selection.effective_size == 4
    assert value.exact_case_count == 4
    assert value.lower_cost_sum == value.upper_cost_sum


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.INVALID_INPUT, ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE],
)
def test_upstream_diagnostics_and_parent_identity_survive(status):
    source = case_traces(log("A"))
    source = replace(
        source,
        status=status,
        value=source.value if status is ComputeStatus.PARTIAL else None,
        issues=(ComputeIssue("original_issue", "details"),),
    )
    result = approximate_conformance(source, sequence("A"))
    assert result.status is (
        ComputeStatus.INVALID_INPUT
        if status is ComputeStatus.INVALID_INPUT
        else ComputeStatus.UNAVAILABLE
    )
    assert result.issues[0].code == "original_issue"
    assert result.parent_computation_ids == (source.computation_id,)


@pytest.mark.parametrize("method", ["frequency", "random", "k_medoids", "simulation"])
def test_result_roundtrip_through_schema_whitelist(method, monkeypatch):
    import pix.results as persistence

    original = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: {**original(), **approximation.RESULT_SCHEMAS}
    )
    result = approximate_conformance(
        log("A", "B"), sequence("A"), SubsetConformanceSpec(selection_method=method)
    )
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result


def test_model_and_parameter_changes_affect_identity():
    source = case_traces(log("AB", "AX"))
    first = approximate_conformance(source, sequence("A"))
    assert first == approximate_conformance(source, sequence("A"))
    assert (
        first.computation_id
        != approximate_conformance(source, sequence("B")).computation_id
    )
    assert (
        first.computation_id
        != approximate_conformance(
            source, sequence("A"), SubsetConformanceSpec(subset_size=2)
        ).computation_id
    )


@pytest.mark.parametrize(
    "field",
    [
        "subset_size",
        "k_medoids_max_iterations",
        "max_alignment_states",
        "max_distance_cells",
        "max_total_distance_cells",
        "simulation_max_steps",
        "simulation_max_attempts",
    ],
)
def test_nonpositive_or_boolean_resource_parameters_are_rejected(field):
    with pytest.raises(ValueError):
        SubsetConformanceSpec(**{field: 0})
    with pytest.raises(TypeError):
        SubsetConformanceSpec(**{field: True})


def test_invalid_contract_types_are_rejected():
    with pytest.raises(ValueError):
        SubsetConformanceSpec(selection_method="missing")
    with pytest.raises(ValueError):
        SubsetConformanceSpec(random_seed=-1)
    with pytest.raises(TypeError):
        approximate_conformance(log("A"), None)
    with pytest.raises(TypeError):
        approximate_conformance(log("A"), sequence("A"), None)
