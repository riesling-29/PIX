"""Independent small-language and graph oracles for sequence conformance."""

from dataclasses import replace
from functools import lru_cache
from itertools import product

import pytest

from pix.case_centric.sequence_alignment import (
    BoundedDFGLanguageSpec,
    DFGAlignmentModel,
    DFGAlignmentSpec,
    SequenceAlignmentSpec,
    align_dfg,
    align_log_to_log,
    bounded_dfg_anti_alignment,
    bounded_dfg_multi_alignment,
)
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


def words_up_to(length):
    return [word for size in range(length + 1) for word in product("AB", repeat=size)]


def recursive_distance(left, right, deletion=1, insertion=1, substitution=1):
    """Memoized exhaustive operation-tree recurrence, not the production DP."""

    @lru_cache(None)
    def search(left, right):
        if not left:
            return len(right) * insertion
        if not right:
            return len(left) * deletion
        choices = [
            deletion + search(left[1:], right),
            insertion + search(left, right[1:]),
        ]
        if left[0] == right[0]:
            choices.append(search(left[1:], right[1:]))
        elif substitution is not None:
            choices.append(substitution + search(left[1:], right[1:]))
        return min(choices)

    return search(tuple(left), tuple(right))


def check_witness(moves, observed, expected_model, expected_cost):
    assert tuple(
        move.log_activity for move in moves if move.log_activity is not None
    ) == tuple(observed)
    assert tuple(
        move.model_activity for move in moves if move.model_activity is not None
    ) == tuple(expected_model)
    assert sum(move.cost for move in moves) == expected_cost
    for move in moves:
        if move.kind == "synchronous":
            assert move.log_activity == move.model_activity
            assert move.cost == 0
        elif move.kind == "substitution":
            assert move.log_activity != move.model_activity
        elif move.kind == "log":
            assert move.model_activity is None
        elif move.kind == "model":
            assert move.log_activity is None
        else:
            pytest.fail(f"unknown edit move {move.kind}")


@pytest.mark.parametrize("costs", [(1, 1, 1), (2, 3, None), (0, 1, 2), (3, 0, 0)])
def test_log_log_exhaustive_recursive_oracle(costs):
    words = words_up_to(3)
    spec = SequenceAlignmentSpec(*costs)
    for reference_word in words:
        result = align_log_to_log(log(*words), log(reference_word), spec)
        assert result.status is ComputeStatus.COMPUTED
        for word, item in zip(words, result.value.traces):
            expected = recursive_distance(word, reference_word, *costs)
            assert item.status == "optimal"
            assert item.best_known_cost == expected
            assert len(item.nearest_references) == 1
            check_witness(
                item.nearest_references[0].moves, word, reference_word, expected
            )


def test_log_log_nearest_reference_ties_and_duplicate_cases_retained():
    value = align_log_to_log(log("A"), log("B", "C", "BB", "B")).value
    assert value.traces[0].best_known_cost == 1
    assert tuple(
        item.reference_case_id for item in value.traces[0].nearest_references
    ) == ("0", "1", "3")
    assert value.reference_case_count == 4


def test_substitution_is_explicit_and_optional():
    substituted = (
        align_log_to_log(log("A"), log("B")).value.traces[0].nearest_references[0]
    )
    assert substituted.moves[0].kind == "substitution"
    assert substituted.moves[0].log_event_id == "0-0"
    assert substituted.moves[0].reference_event_id == "0-0"
    no_sub = align_log_to_log(
        log("A"), log("B"), SequenceAlignmentSpec(substitution_cost=None)
    ).value.traces[0]
    assert no_sub.best_known_cost == 2
    assert {move.kind for move in no_sub.nearest_references[0].moves} == {
        "log",
        "model",
    }


def test_empty_reference_and_empty_case_are_distinct():
    absent = align_log_to_log(log("A"), log())
    assert absent.status is ComputeStatus.COMPUTED
    assert absent.value.traces[0].status == "empty_reference"
    assert absent.value.traces[0].best_known_cost is None
    empty_case = align_log_to_log(log("A"), log(()))
    assert empty_case.value.traces[0].best_known_cost == 1
    assert align_log_to_log(log(), log("A")).value.traces == ()


def test_cell_cap_preserves_incumbent_but_not_claimed_optimum_or_complete_ties():
    result = align_log_to_log(
        log("A"), log("A", "AAAA"), SequenceAlignmentSpec(max_cells=4)
    )
    item = result.value.traces[0]
    assert result.status is ComputeStatus.PARTIAL
    assert item.best_known_cost == 0
    assert item.status == "search_limit"
    assert item.evaluated_references == item.limited_references == 1
    assert len(item.nearest_references) == 1
    none = align_log_to_log(log("A"), log("AA"), SequenceAlignmentSpec(max_cells=1))
    assert none.value.traces[0].best_known_cost is None
    assert none.value.traces[0].nearest_references == ()


def bellman_ford(word, model, deletion, insertion):
    """Construct every product edge before Bellman-Ford, including unreachable states."""
    states = [
        (position, last)
        for position in range(len(word) + 1)
        for last in (None, *model.activities)
    ]
    edges = []
    for source in states:
        position, last = source
        if position < len(word):
            edges.append((source, (position + 1, last), deletion))
        for label in model.activities:
            if (last is None and label in model.starts) or (last, label) in model.edges:
                edges.append((source, (position, label), insertion))
                if position < len(word) and word[position] == label:
                    edges.append((source, (position + 1, label), 0))
    distance = {state: float("inf") for state in states}
    distance[(0, None)] = 0
    for _ in range(len(states) - 1):
        old = dict(distance)
        for source, target, cost in edges:
            distance[target] = min(distance[target], old[source] + cost)
        if old == distance:
            break
    finals = [(len(word), label) for label in model.ends]
    if model.accepts_empty:
        finals.append((len(word), None))
    optimum = min((distance[state] for state in finals), default=float("inf"))
    return None if optimum == float("inf") else optimum


@pytest.mark.parametrize("costs", [(1, 1), (0, 1), (2, 0), (0, 0)])
def test_dfg_exhaustive_two_node_graphs_bellman_ford_oracle(costs):
    alphabet, words = ("A", "B"), words_up_to(2)
    all_edges = tuple(product(alphabet, repeat=2))
    for edge_bits in product((False, True), repeat=4):
        edges = tuple(edge for present, edge in zip(edge_bits, all_edges) if present)
        for starts in ((), ("A",), ("A", "B")):
            for ends in ((), ("B",), ("A", "B")):
                for accepts_empty in (False, True):
                    model = DFGAlignmentModel(
                        alphabet, edges, starts, ends, accepts_empty
                    )
                    result = align_dfg(log(*words), model, DFGAlignmentSpec(*costs))
                    assert result.status is ComputeStatus.COMPUTED
                    for word, aligned in zip(words, result.value.traces):
                        expected = bellman_ford(word, model, *costs)
                        assert aligned.cost == expected, (word, model, costs, aligned)
                        if expected is None:
                            assert aligned.status == "unreachable"
                            continue
                        assert aligned.status == "optimal"
                        model_word = tuple(
                            move.model_activity
                            for move in aligned.moves
                            if move.model_activity is not None
                        )
                        check_witness(aligned.moves, word, model_word, expected)
                        assert not any(
                            move.kind == "substitution" for move in aligned.moves
                        )
                        if model_word:
                            assert model_word[0] in model.starts
                            assert model_word[-1] in model.ends
                            assert all(
                                pair in model.edges
                                for pair in zip(model_word, model_word[1:])
                            )
                        else:
                            assert model.accepts_empty


def test_dfg_nonaccepting_prefix_must_not_be_treated_as_complete():
    model = DFGAlignmentModel(("A", "B"), (("A", "B"),), ("A",), ("B",))
    result = align_dfg(log("A"), model).value.traces[0]
    assert result.cost == 1
    assert tuple(
        move.model_activity for move in result.moves if move.model_activity
    ) == ("A", "B")


def test_dfg_state_limit_does_not_claim_unreachable():
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    result = align_dfg(log("A"), model, DFGAlignmentSpec(max_states=1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces[0].status == "search_limit"
    assert result.value.traces[0].lower_bound_cost == 0
    assert result.value.traces[0].cost is None


def accepted_words(model, horizon):
    return tuple(
        word
        for size in range(horizon + 1)
        for word in product(model.activities, repeat=size)
        if (
            (not word and model.accepts_empty)
            or (
                bool(word)
                and word[0] in model.starts
                and word[-1] in model.ends
                and all(edge in model.edges for edge in zip(word, word[1:]))
            )
        )
    )


@pytest.mark.parametrize(
    "algorithm,is_anti",
    [(bounded_dfg_anti_alignment, True), (bounded_dfg_multi_alignment, False)],
)
@pytest.mark.parametrize("costs", [(1, 1, 1), (3, 1, None), (0, 0, 0)])
def test_bounded_objectives_against_independent_language_enumeration(
    algorithm, is_anti, costs
):
    observed = ("AA", "AB", "AB", "")
    for edges in ((), (("A", "A"), ("A", "B")), tuple(product("AB", repeat=2))):
        model = DFGAlignmentModel(("A", "B"), edges, ("A", "B"), ("A", "B"), True)
        spec = BoundedDFGLanguageSpec(3, *costs)
        candidates = accepted_words(model, 3)
        scores = {
            word: tuple(recursive_distance(trace, word, *costs) for trace in observed)
            for word in candidates
        }
        objective = {
            word: (min(values) if is_anti else sum(values))
            for word, values in scores.items()
        }
        optimum = (max if is_anti else min)(objective.values())
        expected = tuple(
            sorted(word for word, score in objective.items() if score == optimum)
        )
        result = algorithm(log(*observed), model, spec)
        assert result.status is ComputeStatus.COMPUTED
        assert result.value.status == "optimal_within_horizon"
        assert (
            tuple(candidate.activities for candidate in result.value.candidates)
            == expected
        )
        assert result.value.evaluated_words == len(candidates)
        for candidate in result.value.candidates:
            assert candidate.objective_value == optimum
            assert (
                tuple(value for _, value in candidate.case_distances)
                == scores[candidate.activities]
            )


def test_bounded_multi_uses_case_multiplicity():
    model = DFGAlignmentModel(("A", "B"), (), ("A", "B"), ("A", "B"))
    result = bounded_dfg_multi_alignment(
        log("A", "B", "B"), model, BoundedDFGLanguageSpec(1)
    )
    assert tuple(item.activities for item in result.value.candidates) == (("B",),)
    assert result.value.candidates[0].objective_value == 1


@pytest.mark.parametrize(
    "algorithm", [bounded_dfg_anti_alignment, bounded_dfg_multi_alignment]
)
def test_bounded_limits_empty_language_and_empty_observations(algorithm):
    model = DFGAlignmentModel(("A", "B"), (("A", "B"),), ("A",), ("B",))
    short = algorithm(log("AB"), model, BoundedDFGLanguageSpec(1))
    assert short.value.status == "empty_bounded_language"
    assert short.status is ComputeStatus.COMPUTED
    assert short.value.candidates == ()
    limited = algorithm(log("AB"), model, BoundedDFGLanguageSpec(2, max_prefixes=1))
    assert limited.status is ComputeStatus.PARTIAL
    assert limited.value.status == "search_limit"
    assert limited.value.candidates == ()
    cells = algorithm(log("AB"), model, BoundedDFGLanguageSpec(2, max_total_cells=1))
    assert cells.status is ComputeStatus.PARTIAL
    assert cells.value.evaluated_words == 0
    empty = algorithm(log(), model, BoundedDFGLanguageSpec(2))
    assert empty.status is ComputeStatus.UNAVAILABLE
    assert empty.issues[0].code == "empty_observed_population"


def test_bounded_search_cap_preserves_evaluated_incumbent():
    model = DFGAlignmentModel(("A", "B"), (), ("A", "B"), ("A", "B"))
    result = bounded_dfg_anti_alignment(
        log("A"), model, BoundedDFGLanguageSpec(1, max_prefixes=2)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.evaluated_words == 1
    assert result.value.candidates[0].activities == ("A",)
    assert result.value.candidates[0].objective_value == 0
    exact = bounded_dfg_anti_alignment(log("A"), model, BoundedDFGLanguageSpec(1))
    assert exact.value.candidates[0].activities == ("B",)


def test_zero_horizon_is_explicit_empty_word_decision():
    model = DFGAlignmentModel((), (), (), (), True)
    result = bounded_dfg_anti_alignment(log("A"), model, BoundedDFGLanguageSpec(0))
    assert result.value.candidates[0].activities == ()
    assert result.value.candidates[0].objective_value == 1
    assert result.value.visited_prefixes == result.value.evaluated_words == 1


def test_request_identity_covers_cost_model_reference_and_budget():
    traces = case_traces(log("A"))
    references = log("A")
    base = align_log_to_log(traces, references)
    assert base.parent_computation_ids[0] == traces.computation_id
    assert base.computation_id != align_log_to_log(traces, log("B")).computation_id
    assert (
        base.computation_id
        != align_log_to_log(
            traces, references, SequenceAlignmentSpec(max_cells=99)
        ).computation_id
    )
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    ordinary = align_dfg(traces, model)
    assert (
        ordinary.computation_id
        != align_dfg(traces, replace(model, accepts_empty=True)).computation_id
    )
    anti = bounded_dfg_anti_alignment(traces, model, BoundedDFGLanguageSpec(1))
    multi = bounded_dfg_multi_alignment(traces, model, BoundedDFGLanguageSpec(1))
    assert anti.computation_id != multi.computation_id


def test_incomplete_upstream_propagates_without_calculation():
    original = case_traces(log("A"))
    failed = replace(
        original,
        status=ComputeStatus.INVALID_INPUT,
        value=None,
        issues=(ComputeIssue("fixture_invalid", "deliberately invalid"),),
    )
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    for result in (
        align_dfg(failed, model),
        align_log_to_log(original, failed),
        bounded_dfg_anti_alignment(failed, model, BoundedDFGLanguageSpec(1)),
    ):
        assert result.status is ComputeStatus.INVALID_INPUT
        assert result.value is None
        assert any(issue.code == "fixture_invalid" for issue in result.issues)


def test_complete_upstream_diagnostics_are_retained_without_partial_status():
    original = case_traces(log("A"))
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    result = align_dfg(original, model)
    assert result.status is ComputeStatus.COMPUTED
    assert result.issues == original.issues


@pytest.mark.parametrize(
    "create",
    [
        lambda: SequenceAlignmentSpec(log_move_cost=True),
        lambda: SequenceAlignmentSpec(substitution_cost=-1),
        lambda: SequenceAlignmentSpec(max_cells=0),
        lambda: DFGAlignmentSpec(model_move_cost=-1),
        lambda: DFGAlignmentSpec(max_states=False),
        lambda: DFGAlignmentModel(("A",), (("A", "B"),), ("A",), ("A",)),
        lambda: DFGAlignmentModel(("A",), (), ("B",), ("A",)),
        lambda: DFGAlignmentModel(("A",), (), ("A",), ("A",), 1),
        lambda: BoundedDFGLanguageSpec(-1),
        lambda: BoundedDFGLanguageSpec(1, max_total_cells=0),
    ],
)
def test_invalid_model_and_budget_contracts(create):
    with pytest.raises((TypeError, ValueError)):
        create()
