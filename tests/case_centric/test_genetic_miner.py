"""Evolutionary search checked against independent finite-language arithmetic."""

from dataclasses import FrozenInstanceError, replace
from itertools import combinations, product

import pytest

from pix.case_centric.genetic_miner import (
    RESULT_SCHEMAS,
    GeneticMinerSpec,
    _CandidateLimit,
    _language,
    discover_genetic,
)
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeStatus
from pix.event_log import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(f"{i}:{j}", (CaseAttribute("concept:name", "string", a),))
                    for j, a in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def leaf(label):
    return ProcessTree("activity", activity=label)


def tree(operator, *children):
    return ProcessTree(operator, children=tuple(children))


def sequence(word):
    return (
        tree("sequence", *(leaf(a) for a in word))
        if len(word) > 1
        else (leaf(word[0]) if word else ProcessTree("tau"))
    )


def independent_language(model):
    """Enumerate shuffled words by choosing positions, not PIX's search stack."""
    if model.operator == "activity":
        return {(model.activity,)}
    if model.operator == "tau":
        return {()}
    langs = [independent_language(c) for c in model.children]
    if model.operator == "xor":
        return set.union(*langs)
    result = {()}
    for child in langs:
        next_words = set()
        for left, right in product(result, child):
            if model.operator == "sequence":
                next_words.add(left + right)
            else:
                for left_slots in combinations(
                    range(len(left) + len(right)), len(left)
                ):
                    slots = set(left_slots)
                    li, ri = iter(left), iter(right)
                    next_words.add(
                        tuple(
                            next(li) if i in slots else next(ri)
                            for i in range(len(left) + len(right))
                        )
                    )
        result = next_words
    return result


@pytest.mark.parametrize(
    "model",
    [
        ProcessTree("tau"),
        leaf("a"),
        sequence("abca"),
        tree("xor", sequence("ab"), sequence("ac"), ProcessTree("tau")),
        tree("parallel", sequence("ab"), sequence("ac")),
        tree(
            "sequence",
            tree("xor", leaf("a"), ProcessTree("tau")),
            tree("parallel", leaf("b"), leaf("c")),
        ),
    ],
)
def test_candidate_languages_match_independent_position_oracle(model):
    assert _language(model, GeneticMinerSpec()) == independent_language(model)


def test_objective_has_frequency_weighted_acceptance_and_distinct_precision():
    # Model accepts {a,b,c}; log has a three times and d once.
    model = tree("xor", leaf("a"), leaf("b"), leaf("c"))
    spec = GeneticMinerSpec(
        generations=0,
        initial_population=(model,),
        acceptance_weight=2,
        precision_weight=1,
        simplicity_weight=1,
    )
    result = discover_genetic(log("a", "a", "a", "d"), spec)
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert value.language == (("a",), ("b",), ("c",))
    assert value.objective.observed_case_acceptance == 3 / 4
    assert value.objective.empirical_language_precision == 1 / 3
    assert value.objective.inverse_node_count == 1 / 4
    assert value.objective.score == pytest.approx((2 * 3 / 4 + 1 / 3 + 1 / 4) / 4)
    assert value.rejected_observed_variants == (("d",),)
    assert value.objective.accepted_cases == 3
    assert value.objective.accepted_observed_variants == 1
    assert value.optimality_proven is False


def test_default_seed_accepts_all_observed_words_when_it_fits():
    result = discover_genetic(
        log("abc", "adc", "abc", ""), GeneticMinerSpec(generations=0)
    )
    assert result.value.objective.observed_case_acceptance == 1
    assert result.value.objective.empirical_language_precision == 1
    assert result.value.language == ((), tuple("abc"), tuple("adc"))
    assert independent_language(result.value.model) == set(result.value.language)


def test_subnormal_weight_scaling_does_not_reverse_candidate_ranking():
    spec = GeneticMinerSpec(
        generations=0,
        initial_population=(leaf("a"), leaf("b")),
        acceptance_weight=5e-324,
        precision_weight=0,
        simplicity_weight=0,
    )
    tiny = discover_genetic(log("b", "c"), spec)
    ordinary = discover_genetic(log("b", "c"), replace(spec, acceptance_weight=1))
    assert tiny.value.model == ordinary.value.model == leaf("b")
    assert tiny.value.objective.score == ordinary.value.objective.score == 0.5


def test_reproducible_seed_and_real_operators_preserve_elitism():
    spec = GeneticMinerSpec(
        seed=31, generations=10, stagnation_generations=20, population_size=12
    )
    first = discover_genetic(log("abd", "acd", "abbd", ""), spec)
    second = discover_genetic(log("abd", "acd", "abbd", ""), spec)
    assert first == second
    scores = [row.best_score for row in first.value.history]
    assert scores == sorted(scores)
    assert first.value.mutation_changes > 0
    assert first.value.crossover_changes > 0
    assert first.value.evaluated_models > spec.population_size
    assert independent_language(first.value.model) == set(first.value.language)
    assert first.value.history[-1].generation == 10


def test_mutation_can_improve_a_poor_initial_population():
    spec = GeneticMinerSpec(
        seed=3,
        population_size=12,
        generations=40,
        stagnation_generations=40,
        crossover_rate=0,
        mutation_rate=1,
        initial_population=(leaf("a"),),
    )
    result = discover_genetic(log("ab", "ab", "ab"), spec)
    assert result.value.history[-1].best_score > result.value.history[0].best_score
    assert result.value.objective.observed_case_acceptance == 1
    assert result.value.language == (("a", "b"),)
    assert result.value.mutation_changes > 0
    assert result.value.crossover_changes == 0


def test_shared_boundary_can_be_compressed_by_evolution():
    initial = tree("xor", sequence("ab"), sequence("ac"))
    spec = GeneticMinerSpec(
        seed=2,
        population_size=16,
        generations=30,
        stagnation_generations=30,
        crossover_rate=0,
        mutation_rate=1,
        initial_population=(initial,),
    )
    result = discover_genetic(log("ab", "ac"), spec)
    assert result.value.objective.node_count < 7
    assert result.value.objective.observed_case_acceptance == 1
    assert result.value.objective.empirical_language_precision == 1
    assert result.value.history[-1].best_score > result.value.history[0].best_score


def test_stagnation_is_an_explicit_normal_stop_not_optimality():
    spec = GeneticMinerSpec(
        generations=20, stagnation_generations=3, crossover_rate=0, mutation_rate=0
    )
    result = discover_genetic(log("ab"), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.stop_reason == "stagnation"
    assert result.value.history[-1].generation == 3
    assert not result.value.optimality_proven
    assert result.value.crossover_changes == result.value.mutation_changes == 0


def test_evaluation_limit_retains_exact_scored_incumbent_as_partial():
    spec = GeneticMinerSpec(seed=9, max_evaluations=1, generations=10)
    result = discover_genetic(log("ab", "ac"), spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.evaluated_models == 1
    assert result.value.stop_reason == "evaluation_limit"
    assert result.value.objective.observed_case_acceptance == 1
    assert "genetic_evaluation_limit" in {issue.code for issue in result.issues}
    assert set(result.value.language) == independent_language(result.value.model)


def test_oversized_language_is_rejected_never_truncated_to_score():
    model = tree("parallel", *(leaf(a) for a in "abcd"))
    spec = GeneticMinerSpec(
        generations=0, max_language_words=10, initial_population=(model,)
    )
    result = discover_genetic(log("abcd"), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "no_admissible_population"
    with pytest.raises(_CandidateLimit):
        _language(model, spec)


def test_bad_seed_rejection_does_not_discard_valid_seed():
    spec = GeneticMinerSpec(
        generations=0, max_nodes=2, initial_population=(sequence("ab"), leaf("a"))
    )
    result = discover_genetic(log("a"), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.model == leaf("a")
    assert result.value.rejected_models == 1


def test_deep_external_seed_rejected_before_recursive_request_serialization():
    model = leaf("a")
    for _ in range(350):
        model = tree("sequence", leaf("a"), model)
    with pytest.raises(ValueError, match="depth cannot exceed 32"):
        GeneticMinerSpec(initial_population=(model, leaf("a")))


def test_shared_subtrees_cannot_expand_initial_request_exponentially():
    model = leaf("a")
    for _ in range(31):
        model = tree("sequence", model, model)
    with pytest.raises(ValueError, match="10000 expanded node"):
        GeneticMinerSpec(initial_population=(model,), max_nodes=1)


def test_language_work_bound_can_refuse_even_small_language():
    spec = GeneticMinerSpec(
        generations=0, max_language_operations=1, initial_population=(sequence("ab"),)
    )
    assert discover_genetic(log("ab"), spec).status is ComputeStatus.UNAVAILABLE


def test_empty_log_and_observed_empty_case_are_different():
    assert discover_genetic(log()).status is ComputeStatus.UNAVAILABLE
    result = discover_genetic(log(""), GeneticMinerSpec(generations=4))
    assert result.value.model.operator == "tau"
    assert result.value.objective.observed_case_acceptance == 1
    assert result.value.language == ((),)


def test_explicit_case_projection_preserves_identity_and_partial_status():
    source = case_traces(log("ab"))
    partial = replace(source, status=ComputeStatus.PARTIAL)
    result = discover_genetic(partial, GeneticMinerSpec(generations=0))
    assert result.status is ComputeStatus.PARTIAL
    assert result.parent_computation_ids == (source.computation_id,)
    assert result.source_digest == source.source_digest
    unavailable = replace(source, status=ComputeStatus.UNAVAILABLE, value=None)
    failed = discover_genetic(unavailable)
    assert failed.status is ComputeStatus.UNAVAILABLE
    assert failed.value is None


def test_parameter_identity_and_frozen_contracts():
    data = log("ab")
    spec = GeneticMinerSpec(generations=0)
    first = discover_genetic(data, spec)
    second = discover_genetic(data, replace(spec, seed=1))
    assert first.computation_id != second.computation_id
    with pytest.raises(FrozenInstanceError):
        first.value.stop_reason = "optimal"
    with pytest.raises(FrozenInstanceError):
        spec.seed = 8


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"crossover_rate": 0},
        {"mutation_rate": 1},
        {"acceptance_weight": 2},
        {"precision_weight": 1},
        {"simplicity_weight": 0},
        {
            "crossover_rate": 1,
            "mutation_rate": 0,
            "acceptance_weight": 2,
            "precision_weight": 1,
            "simplicity_weight": 1,
        },
    ],
)
def test_public_result_roundtrip_preserves_integer_options_and_identity(
    options, monkeypatch
):
    import pix.results as persistence

    # The integration owner maintains the global allowlist separately.
    monkeypatch.setattr(persistence, "_schemas", lambda: RESULT_SCHEMAS)
    spec = GeneticMinerSpec(generations=1, **options)
    result = discover_genetic(log("ab", "ac"), spec)
    encoded = persistence.result_json_bytes(result)
    restored = persistence.result_from_json(encoded)
    assert restored == result
    assert restored.computation_id == result.computation_id
    assert persistence.result_json_bytes(restored) == encoded
    for name, value in options.items():
        assert type(getattr(restored.spec, name)) is type(value)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seed": True},
        {"population_size": 1},
        {"elite_count": 24},
        {"tournament_size": 25},
        {"generations": -1},
        {"max_depth": 33},
        {"max_evaluations": 0},
        {"mutation_rate": float("nan")},
        {"crossover_rate": 2},
        {"acceptance_weight": -1},
        {"acceptance_weight": 0, "precision_weight": 0, "simplicity_weight": 0},
        {"acceptance_weight": 1e308, "precision_weight": 1e308},
        {"initial_population": []},
        {"initial_population": (tree("loop", leaf("a"), leaf("b")),)},
    ],
)
def test_invalid_spec_is_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        GeneticMinerSpec(**kwargs)
