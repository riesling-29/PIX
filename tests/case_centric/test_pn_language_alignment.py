"""Independent token-vector language and recursive edit-distance oracles."""

from dataclasses import FrozenInstanceError, replace
from functools import lru_cache
from itertools import product

import pytest

from pix.case_centric.pn_language_alignment import (
    RESULT_SCHEMAS,
    BoundedPetriNetLanguageAlignment,
    BoundedPetriNetLanguageRequest,
    BoundedPetriNetLanguageSpec,
    bounded_petri_net_anti_alignment,
    bounded_petri_net_multi_alignment,
)
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"{i}-{j}", (CaseAttribute("concept:name", "string", label),)
                    )
                    for j, label in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def net(places, transitions, arcs, initial, final):
    return PetriNet(
        tuple(Place(place) for place in places),
        tuple(Transition(*transition) for transition in transitions),
        tuple(Arc(*arc) for arc in arcs),
        Marking(tuple(initial)),
        Marking(tuple(final)),
    )


def choice():
    return net(
        ("p", "q"),
        (("a", "A"), ("b", "B")),
        (("p", "a"), ("a", "q"), ("p", "b"), ("b", "q")),
        (("p", 1),),
        (("q", 1),),
    )


def concurrent():
    return net(
        ("p", "q", "r", "s"),
        (("a", "A"), ("b", "B"), ("tau", None)),
        (("p", "a"), ("a", "q"), ("r", "b"), ("b", "s"), ("p", "tau"), ("tau", "p")),
        (("p", 1), ("r", 1)),
        (("q", 1), ("s", 1)),
    )


def weighted():
    return net(
        ("p", "q"),
        (("a", "A"), ("b", "B"), ("tau", None)),
        (
            ("p", "a", 2),
            ("a", "q", 2),
            ("q", "b"),
            ("b", "p"),
            ("p", "tau"),
            ("tau", "p"),
        ),
        (("p", 2),),
        (("q", 2),),
    )


def oracle_language(model, horizon, token_bound):
    """Model as finite Boolean word automata over a proved token-vector box.

    For the chosen conservative fixtures no place exceeds token_bound. Build
    *all* marking vectors first, then ask acceptance of each word separately;
    neither production firing helpers nor its joint language BFS are used.
    """
    places = tuple(place.id for place in model.places)
    vectors = tuple(product(range(token_bound + 1), repeat=len(places)))
    links = {}
    for marking in vectors:
        successors = []
        for transition in model.transitions:
            consumed = tuple(
                sum(
                    arc.weight
                    for arc in model.arcs
                    if arc.source == place and arc.target == transition.id
                )
                for place in places
            )
            produced = tuple(
                sum(
                    arc.weight
                    for arc in model.arcs
                    if arc.target == place and arc.source == transition.id
                )
                for place in places
            )
            if all(tokens >= required for tokens, required in zip(marking, consumed)):
                after = tuple(
                    tokens - take + give
                    for tokens, take, give in zip(marking, consumed, produced)
                )
                if after in vectors:
                    successors.append((transition.activity, after))
        links[marking] = successors
    initial = tuple(
        dict(model.initial_marking.tokens).get(place, 0) for place in places
    )
    final = tuple(dict(model.final_marking.tokens).get(place, 0) for place in places)
    alphabet = sorted({t.activity for t in model.transitions if t.activity is not None})
    accepted = set()
    for length in range(horizon + 1):
        for word in product(alphabet, repeat=length):
            stack, visited = [(initial, 0)], set()
            while stack:
                marking, position = stack.pop()
                if (marking, position) in visited:
                    continue
                visited.add((marking, position))
                if marking == final and position == len(word):
                    accepted.add(word)
                    break
                for activity, target in links[marking]:
                    if activity is None:
                        stack.append((target, position))
                    elif position < len(word) and word[position] == activity:
                        stack.append((target, position + 1))
    return accepted


def recursive_edit(left, right, deletion, insertion, substitution):
    @lru_cache(None)
    def distance(i, j):
        if i == len(left):
            return (len(right) - j) * insertion
        if j == len(right):
            return (len(left) - i) * deletion
        choices = [deletion + distance(i + 1, j), insertion + distance(i, j + 1)]
        if left[i] == right[j]:
            choices.append(distance(i + 1, j + 1))
        elif substitution is not None:
            choices.append(substitution + distance(i + 1, j + 1))
        return min(choices)

    return distance(0, 0)


def assert_firing_witness(model, candidate):
    """Check a returned witness by direct integer incidence arithmetic."""
    marking, activities = dict(model.initial_marking.tokens), []
    transitions = {transition.id: transition for transition in model.transitions}
    for transition_id in candidate.transition_ids:
        transition = transitions[transition_id]
        for arc in model.arcs:
            if arc.target == transition_id:
                assert marking.get(arc.source, 0) >= arc.weight
                marking[arc.source] -= arc.weight
        for arc in model.arcs:
            if arc.source == transition_id:
                marking[arc.target] = marking.get(arc.target, 0) + arc.weight
        if transition.activity is not None:
            activities.append(transition.activity)
    assert tuple(activities) == candidate.activities
    assert {place: count for place, count in marking.items() if count} == dict(
        model.final_marking.tokens
    )


@pytest.mark.parametrize("factory,bound", [(choice, 1), (concurrent, 1), (weighted, 2)])
@pytest.mark.parametrize("costs", [(1, 1, 1), (2, 3, None), (0, 2, 3), (3, 0, 0)])
@pytest.mark.parametrize(
    "operator,aggregate",
    [
        (bounded_petri_net_anti_alignment, min),
        (bounded_petri_net_multi_alignment, sum),
    ],
)
def test_independent_token_vector_and_recursive_edit_oracles(
    factory, bound, costs, operator, aggregate
):
    model = factory()
    observed = ((), ("A",), ("B", "A"), ("B", "A"))
    for horizon in range(5):
        language = oracle_language(model, horizon, bound)
        spec = BoundedPetriNetLanguageSpec(horizon, *costs)
        result = operator(log(*observed), model, spec)
        value = result.value
        assert result.status is ComputeStatus.COMPUTED
        assert value.language_complete and value.evaluations_complete
        assert value.accepted_words == len(language)
        assert value.evaluated_words == len(language)
        assert value.observed_cases == len(observed)
        assert value.discovered_states == value.expanded_states
        if not language:
            assert value.status == "empty_bounded_language"
            assert value.candidates == ()
            continue
        expected = {
            word: tuple(recursive_edit(case, word, *costs) for case in observed)
            for word in language
        }
        scores = {word: aggregate(distances) for word, distances in expected.items()}
        best = max(scores.values()) if aggregate is min else min(scores.values())
        winners = tuple(sorted(word for word, score in scores.items() if score == best))
        assert tuple(item.activities for item in value.candidates) == winners
        assert value.status == "optimal_within_horizon"
        for candidate in value.candidates:
            assert candidate.objective_value == best
            assert candidate.case_distances == tuple(
                (str(i), distance)
                for i, distance in enumerate(expected[candidate.activities])
            )
            assert_firing_witness(model, candidate)


def test_multi_preserves_case_multiplicity_and_anti_uses_minimum():
    population = log("A", "B", "B")
    spec = BoundedPetriNetLanguageSpec(1)
    multi = bounded_petri_net_multi_alignment(population, choice(), spec).value
    assert tuple(item.activities for item in multi.candidates) == (("B",),)
    assert multi.candidates[0].objective_value == 1
    anti = bounded_petri_net_anti_alignment(population, choice(), spec).value
    assert tuple(item.activities for item in anti.candidates) == (("A",), ("B",))
    assert all(item.objective_value == 0 for item in anti.candidates)


def test_shortest_then_lexical_firing_witness_with_duplicate_labels():
    model = net(
        ("p", "q", "r"),
        (("a_tau", None), ("b_direct", "A"), ("c_direct", "A"), ("x_end", "A")),
        (
            ("p", "a_tau"),
            ("a_tau", "r"),
            ("r", "x_end"),
            ("x_end", "q"),
            ("p", "b_direct"),
            ("b_direct", "q"),
            ("p", "c_direct"),
            ("c_direct", "q"),
        ),
        (("p", 1),),
        (("q", 1),),
    )
    value = bounded_petri_net_anti_alignment(
        log("B"), model, BoundedPetriNetLanguageSpec(1)
    ).value
    assert value.accepted_words == 1
    assert value.candidates[0].transition_ids == ("b_direct",)


def test_same_word_different_markings_must_not_merge():
    model = net(
        ("p", "dead", "r", "q"),
        (("a_dead", "A"), ("a_live", "A"), ("b", "B")),
        (
            ("p", "a_dead"),
            ("a_dead", "dead"),
            ("p", "a_live"),
            ("a_live", "r"),
            ("r", "b"),
            ("b", "q"),
        ),
        (("p", 1),),
        (("q", 1),),
    )
    value = bounded_petri_net_multi_alignment(
        log("AB"), model, BoundedPetriNetLanguageSpec(2)
    ).value
    assert value.accepted_words == 1
    assert value.candidates[0].activities == ("A", "B")
    assert value.candidates[0].transition_ids == ("a_live", "b")


@pytest.mark.parametrize(
    "operator", [bounded_petri_net_anti_alignment, bounded_petri_net_multi_alignment]
)
def test_all_zero_costs_retain_every_accepted_word(operator):
    model = net(
        ("p",),
        (("a", "A"), ("b", "B")),
        (("p", "a"), ("a", "p"), ("p", "b"), ("b", "p")),
        (("p", 1),),
        (("p", 1),),
    )
    value = operator(
        log("A", "BB"), model, BoundedPetriNetLanguageSpec(2, 0, 0, 0)
    ).value
    assert len(value.candidates) == 7
    assert {item.activities for item in value.candidates} == {
        (),
        ("A",),
        ("B",),
        ("A", "A"),
        ("A", "B"),
        ("B", "A"),
        ("B", "B"),
    }
    assert all(item.objective_value == 0 for item in value.candidates)


def test_empty_net_and_transitions_without_arcs():
    empty = net((), (), (), (), ())
    value = bounded_petri_net_multi_alignment(
        log("A"), empty, BoundedPetriNetLanguageSpec(2, max_states=1)
    ).value
    assert value.status == "optimal_within_horizon"
    assert value.candidates[0].activities == ()
    assert value.candidates[0].transition_ids == ()
    model = replace(empty, transitions=(Transition("a", "A"), Transition("tau")))
    value = bounded_petri_net_anti_alignment(
        log(""), model, BoundedPetriNetLanguageSpec(2)
    ).value
    assert value.accepted_words == 3
    assert value.candidates[0].activities == ("A", "A")
    assert value.candidates[0].transition_ids == ("a", "a")


def test_equal_length_witness_ties_compare_complete_transition_sequence():
    model = net(
        ("p", "r", "s", "q"),
        (("a", None), ("b", None), ("y", "A"), ("z", "A")),
        (
            ("p", "a"),
            ("a", "r"),
            ("p", "b"),
            ("b", "s"),
            ("r", "z"),
            ("z", "q"),
            ("s", "y"),
            ("y", "q"),
        ),
        (("p", 1),),
        (("q", 1),),
    )
    value = bounded_petri_net_multi_alignment(
        log("A"), model, BoundedPetriNetLanguageSpec(1)
    ).value
    assert value.candidates[0].transition_ids == ("a", "z")


def test_silent_completion_beyond_horizon_and_silent_cycle():
    model = net(
        ("p", "q", "r"),
        (("a", "A"), ("tau_cycle", None), ("tau_finish", None)),
        (
            ("p", "a"),
            ("a", "q"),
            ("q", "tau_cycle"),
            ("tau_cycle", "q"),
            ("q", "tau_finish"),
            ("tau_finish", "r"),
        ),
        (("p", 1),),
        (("r", 1),),
    )
    value = bounded_petri_net_multi_alignment(
        log("A"), model, BoundedPetriNetLanguageSpec(1)
    ).value
    assert value.status == "optimal_within_horizon"
    assert value.candidates[0].transition_ids == ("a", "tau_finish")
    assert value.discovered_states == 3


def test_zero_horizon_accepts_empty_word_through_silent_path():
    model = net(
        ("p", "q"),
        (("tau", None),),
        (("p", "tau"), ("tau", "q")),
        (("p", 1),),
        (("q", 1),),
    )
    value = bounded_petri_net_anti_alignment(
        log("A"), model, BoundedPetriNetLanguageSpec(0)
    ).value
    assert value.candidates[0].activities == ()
    assert value.candidates[0].transition_ids == ("tau",)
    assert value.candidates[0].objective_value == 1


def test_final_marking_outgoing_transitions_are_explored_and_horizon_changes_objective():
    model = net(
        ("p",), (("a", "A"),), (("p", "a"), ("a", "p")), (("p", 1),), (("p", 1),)
    )
    for horizon in (0, 1, 3):
        value = bounded_petri_net_anti_alignment(
            log(""), model, BoundedPetriNetLanguageSpec(horizon)
        ).value
        assert value.accepted_words == horizon + 1
        assert value.candidates[0].activities == ("A",) * horizon
        assert value.candidates[0].objective_value == horizon


def test_final_marking_requires_exact_tokens_and_weighted_enablement():
    model = net(
        ("p", "q"),
        (("a", "A"),),
        (("p", "a", 2), ("a", "q", 2)),
        (("p", 3),),
        (("q", 2),),
    )
    value = bounded_petri_net_multi_alignment(
        log("A"), model, BoundedPetriNetLanguageSpec(1)
    ).value
    assert value.status == "empty_bounded_language"  # Extra p token is not accepted.
    blocked = replace(model, initial_marking=Marking((("p", 1),)))
    value = bounded_petri_net_multi_alignment(
        log("A"), blocked, BoundedPetriNetLanguageSpec(1)
    ).value
    assert value.status == "empty_bounded_language"
    assert value.discovered_states == 1


def test_unbounded_silent_token_growth_is_partial_even_with_incumbent():
    model = net(("p",), (("grow", None),), (("grow", "p"),), (), ())
    result = bounded_petri_net_anti_alignment(
        log("A"), model, BoundedPetriNetLanguageSpec(0, max_states=5)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.status == "search_limit"
    assert result.value.discovered_states == result.value.expanded_states == 5
    assert not result.value.language_complete
    assert result.value.evaluations_complete
    assert result.value.candidates[0].activities == ()
    assert result.value.candidates[0].transition_ids == ()
    assert result.issues[-1].code == "petri_net_language_state_limit"


def test_state_cap_without_candidate_cannot_prove_empty_language():
    result = bounded_petri_net_multi_alignment(
        log("A"), choice(), BoundedPetriNetLanguageSpec(1, max_states=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.status == "search_limit"
    assert result.value.candidates == ()
    assert result.value.accepted_words == 0


def test_exact_state_ceiling_without_rejected_successor_is_complete():
    result = bounded_petri_net_multi_alignment(
        log("A"), choice(), BoundedPetriNetLanguageSpec(1, max_states=3)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.discovered_states == 3


@pytest.mark.parametrize("budget,evaluated", [(1, 0), (4, 1), (7, 1), (8, 2)])
def test_cell_budget_tracks_whole_word_population_evaluations(budget, evaluated):
    result = bounded_petri_net_anti_alignment(
        log("A"), choice(), BoundedPetriNetLanguageSpec(1, max_total_cells=budget)
    )
    assert result.value.language_complete
    assert result.value.evaluated_words == evaluated
    assert result.value.evaluated_cells == evaluated * 4
    assert result.value.evaluations_complete is (evaluated == 2)
    assert result.status is (
        ComputeStatus.COMPUTED if evaluated == 2 else ComputeStatus.PARTIAL
    )
    if evaluated == 1:
        assert result.value.candidates[0].activities == ("A",)
        assert (
            result.value.candidates[0].objective_value == 0
        )  # B optimum not yet evaluated.


def test_both_resource_limits_are_reported():
    result = bounded_petri_net_anti_alignment(
        log("A"),
        choice(),
        BoundedPetriNetLanguageSpec(1, max_states=2, max_total_cells=1),
    )
    assert {
        issue.code for issue in result.issues if issue.code.startswith("petri_net_")
    } == {
        "petri_net_language_state_limit",
        "petri_net_language_cell_limit",
    }


@pytest.mark.parametrize(
    "operator", [bounded_petri_net_anti_alignment, bounded_petri_net_multi_alignment]
)
def test_empty_population_is_unavailable_and_empty_case_remains_valid(operator):
    empty = operator(log(), choice(), BoundedPetriNetLanguageSpec(1))
    assert empty.status is ComputeStatus.UNAVAILABLE
    assert empty.value is None
    assert empty.issues[-1].code == "empty_observed_population"
    actual = operator(log(""), choice(), BoundedPetriNetLanguageSpec(1))
    assert actual.status is ComputeStatus.COMPUTED
    assert actual.value.observed_cases == 1


@pytest.mark.parametrize(
    "status",
    [ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT],
)
def test_unavailable_trace_input_preserves_issues_and_parent(status):
    original = case_traces(log("A"))
    source = replace(
        original,
        status=status,
        value=original.value if status is ComputeStatus.PARTIAL else None,
        issues=(ComputeIssue("upstream", "Original issue"),),
    )
    result = bounded_petri_net_anti_alignment(
        source, choice(), BoundedPetriNetLanguageSpec(1)
    )
    assert result.status is (
        ComputeStatus.INVALID_INPUT
        if status is ComputeStatus.INVALID_INPUT
        else ComputeStatus.UNAVAILABLE
    )
    assert result.value is None
    assert result.issues[0].code == "upstream"
    assert result.parent_computation_ids == (source.computation_id,)


def test_model_and_parameters_and_objective_are_in_identity_and_schema():
    source, model = case_traces(log("A")), choice()
    spec = BoundedPetriNetLanguageSpec(1)
    first = bounded_petri_net_anti_alignment(source, model, spec)
    same = bounded_petri_net_anti_alignment(source, model, spec)
    changed_horizon = bounded_petri_net_anti_alignment(
        source, model, replace(spec, max_length=2)
    )
    changed_model = bounded_petri_net_anti_alignment(
        source, replace(model, final_marking=Marking()), spec
    )
    multi = bounded_petri_net_multi_alignment(source, model, spec)
    assert first == same
    assert (
        len(
            {
                result.computation_id
                for result in (first, changed_horizon, changed_model, multi)
            }
        )
        == 4
    )
    assert first.spec.model_digest == model_digest(model)
    assert first.spec.objective == "anti_max_min"
    assert first.source_digest == source.source_digest
    assert first.parent_computation_ids == (source.computation_id,)
    assert RESULT_SCHEMAS[first.operator_id] == (
        "case_bounded_petri_net_language_alignment",
        BoundedPetriNetLanguageRequest,
        BoundedPetriNetLanguageAlignment,
    )
    with pytest.raises(FrozenInstanceError):
        first.value.observed_cases = 999


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"max_length": -1}, ValueError),
        ({"max_length": True}, TypeError),
        ({"log_move_cost": -1}, ValueError),
        ({"model_move_cost": 0.5}, TypeError),
        ({"substitution_cost": False}, TypeError),
        ({"substitution_cost": -1}, ValueError),
        ({"max_states": 0}, ValueError),
        ({"max_total_cells": 0}, ValueError),
    ],
)
def test_invalid_specs(changes, error):
    parameters = {"max_length": 1} | changes
    with pytest.raises(error):
        BoundedPetriNetLanguageSpec(**parameters)


def test_invalid_input_types_fail_explicitly():
    with pytest.raises(TypeError, match="net"):
        bounded_petri_net_anti_alignment(
            log("A"), object(), BoundedPetriNetLanguageSpec(1)
        )
    with pytest.raises(TypeError, match="spec"):
        bounded_petri_net_multi_alignment(log("A"), choice(), object())
    with pytest.raises(TypeError, match="CaseLog"):
        bounded_petri_net_multi_alignment(
            object(), choice(), BoundedPetriNetLanguageSpec(1)
        )
