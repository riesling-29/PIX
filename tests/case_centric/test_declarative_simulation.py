"""Independent bounded-language formulas and explicit seeded proposal oracle."""

import random
from dataclasses import dataclass
from itertools import product

import pytest

from pix.case_centric.declarative import (
    DECLARE_TEMPLATES,
    DeclareConstraint,
    DeclareModel,
)
from pix.case_centric.declarative_simulation import (
    DeclareLanguageSpec,
    DeclarePlayoutSpec,
    generate_declare_language,
    play_out_declare,
)
from pix.contracts.result import ComputeStatus

UNARY = {"existence", "absence", "exactly", "exactly_one", "init", "end"}


def independent_truth(word, rule):
    """Use positional quantifiers, without evaluating a PIX obligation."""
    a = [i for i, x in enumerate(word) if x == rule.source]
    b = [i for i, x in enumerate(word) if x == rule.target]
    response = all(any(j > i for j in b) for i in a)
    precedence = all(any(i < j for i in a) for j in b)
    alt_response = all(
        any(j > i and not any(i < k < j for k in a) for j in b) for i in a
    )
    alt_precedence = all(
        any(i < j and not any(i < k < j for k in b) for i in a) for j in b
    )
    chain_response = all(i + 1 in b for i in a)
    chain_precedence = all(j - 1 in a for j in b)
    answers = {
        "existence": len(a) >= rule.cardinality,
        "absence": len(a) < rule.cardinality,
        "exactly": len(a) == rule.cardinality,
        "exactly_one": len(a) == 1,
        "init": bool(word) and word[0] == rule.source,
        "end": bool(word) and word[-1] == rule.source,
        "responded_existence": not a or bool(b),
        "response": response,
        "precedence": precedence,
        "alternate_response": alt_response,
        "alternate_precedence": alt_precedence,
        "chain_response": chain_response,
        "chain_precedence": chain_precedence,
        "succession": response and precedence,
        "alternate_succession": alt_response and alt_precedence,
        "chain_succession": chain_response and chain_precedence,
        "coexistence": bool(a) == bool(b),
        "noncoexistence": not (a and b),
        "not_response": not any(i < j for i in a for j in b),
        "not_precedence": not any(i < j for i in a for j in b),
        "nonsuccession": not any(i < j for i in a for j in b),
        "nonchainsuccession": not any(i + 1 == j for i in a for j in b),
    }
    return bool(answers[rule.template])


def independent_language(model, minimum, maximum):
    return {
        word
        for n in range(minimum, maximum + 1)
        for word in product(model.activities, repeat=n)
        if all(independent_truth(word, rule) for rule in model.rules)
    }


@pytest.mark.parametrize("template", DECLARE_TEMPLATES)
def test_complete_bounded_language_all_templates_against_independent_formulas(template):
    rule = DeclareConstraint(template, "A", None if template in UNARY else "B")
    model = DeclareModel(("A", "B", "C"), (rule,))
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=5))
    expected = independent_language(model, 0, 5)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.complete
    assert set(result.value.traces) == expected
    assert len(result.value.traces) == len(expected) == result.value.population_size
    assert result.value.evaluated_prefixes <= sum(3**n for n in range(6))


@pytest.mark.parametrize(
    "template,cardinality",
    tuple(product(("existence", "absence", "exactly"), (0, 2, 4))),
)
def test_nondefault_cardinality_preserves_prefix_pruning_soundness(
    template, cardinality
):
    model = DeclareModel(
        ("A", "B"), (DeclareConstraint(template, "A", cardinality=cardinality),)
    )
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=5))
    assert set(result.value.traces) == independent_language(model, 0, 5)
    assert result.value.complete


@pytest.mark.parametrize(
    "rules",
    [
        (DeclareConstraint("init", "A"), DeclareConstraint("end", "B")),
        (
            DeclareConstraint("existence", "A"),
            DeclareConstraint("chain_succession", "A", "B"),
        ),
        (
            DeclareConstraint("exactly", "A", cardinality=2),
            DeclareConstraint("alternate_succession", "A", "B"),
        ),
        (
            DeclareConstraint("response", "A", "B"),
            DeclareConstraint("noncoexistence", "A", "B"),
        ),
        (
            DeclareConstraint("precedence", "A", "B"),
            DeclareConstraint("not_response", "A", "B"),
        ),
    ],
)
def test_model_conjunction_and_nonzero_minimum_length(rules):
    model = DeclareModel(("A", "B", "C"), rules)
    result = generate_declare_language(
        model, DeclareLanguageSpec(min_events=2, max_events=5)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert set(result.value.traces) == independent_language(model, 2, 5)


def test_pending_response_and_end_are_not_pruned_before_future_fulfillment():
    model = DeclareModel(
        ("A", "B"),
        (
            DeclareConstraint("existence", "A"),
            DeclareConstraint("response", "A", "B"),
            DeclareConstraint("end", "B"),
        ),
    )
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=2))
    assert result.value.traces == (("A", "B"),)
    assert result.value.complete


def test_irreversible_pruning_reduces_exploration_without_losing_language():
    model = DeclareModel(("A", "B"), (DeclareConstraint("absence", "B"),))
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=7))
    assert set(result.value.traces) == {("A",) * n for n in range(8)}
    assert result.value.evaluated_prefixes == 15
    assert result.value.pruned_prefixes == 7


def test_exhaustive_order_is_explicit_and_deterministic():
    model = DeclareModel(("B", "A"), ())
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=2))
    assert result.value.traces == (
        (),
        ("B",),
        ("B", "B"),
        ("B", "A"),
        ("A",),
        ("A", "B"),
        ("A", "A"),
    )
    assert result.value.traversal == "depth-first-alphabet-order"
    assert result == generate_declare_language(model, DeclareLanguageSpec(max_events=2))


def test_exact_output_and_state_caps_are_complete_only_if_no_word_is_omitted():
    model = DeclareModel(("A",), ())
    exact = generate_declare_language(
        model, DeclareLanguageSpec(max_events=2, max_traces=3, max_prefix_states=3)
    )
    trace_limit = generate_declare_language(
        model, DeclareLanguageSpec(max_events=2, max_traces=2)
    )
    state_limit = generate_declare_language(
        model, DeclareLanguageSpec(max_events=2, max_prefix_states=2)
    )
    assert exact.status is ComputeStatus.COMPUTED
    assert exact.value.population_size == 3
    for result, code in (
        (trace_limit, "trace_limit"),
        (state_limit, "prefix_state_limit"),
    ):
        assert result.status is ComputeStatus.PARTIAL
        assert not result.value.complete
        assert result.value.population_size is None
        assert result.value.traces == ((), ("A",))
        assert result.value.termination == code
        assert result.issues[0].code == "declare_" + code


def test_empty_alphabet_epsilon_and_empty_length_population():
    model = DeclareModel((), ())
    epsilon = generate_declare_language(model, DeclareLanguageSpec(max_events=50))
    nonempty = generate_declare_language(
        model, DeclareLanguageSpec(min_events=1, max_events=50)
    )
    assert epsilon.value.traces == ((),)
    assert epsilon.value.population_size == 1
    assert nonempty.value.traces == ()
    assert nonempty.value.population_size == 0
    assert epsilon.status is nonempty.status is ComputeStatus.COMPUTED


def test_bounded_empty_does_not_imply_unbounded_unsatisfiability():
    model = DeclareModel(("A",), (DeclareConstraint("existence", "A", cardinality=3),))
    short = generate_declare_language(model, DeclareLanguageSpec(max_events=2))
    longer = generate_declare_language(model, DeclareLanguageSpec(max_events=3))
    assert short.value.complete and short.value.population_size == 0
    assert longer.value.traces == (("A", "A", "A"),)


def test_contradictory_model_has_proven_empty_bounded_language():
    model = DeclareModel(
        ("A", "B"),
        (DeclareConstraint("existence", "A"), DeclareConstraint("absence", "A")),
    )
    result = generate_declare_language(model, DeclareLanguageSpec(max_events=10))
    assert result.value.complete and result.value.population_size == 0
    assert result.status is ComputeStatus.COMPUTED


def test_deep_singleton_frontier_uses_linear_storage_without_python_recursion():
    import tracemalloc

    model = DeclareModel(("A",), ())
    tracemalloc.start()
    try:
        result = generate_declare_language(
            model,
            DeclareLanguageSpec(
                min_events=10_000,
                max_events=10_000,
                max_traces=1,
                max_prefix_states=10_001,
            ),
        )
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.traces == (("A",) * 10_000,)
    # Storing each immutable prefix would retain roughly 50 million object
    # references (>400 MB). This broad bound detects that algorithmic defect
    # without asserting a platform-specific small allocation count.
    assert peak < 32_000_000


def independent_proposals(model, spec):
    rng = random.Random(spec.seed)
    accepted = []
    for attempt in range(1, spec.max_attempts + 1):
        length = rng.randint(spec.min_events, spec.max_events)
        word = tuple(rng.choice(model.activities) for _ in range(length))
        if all(independent_truth(word, rule) for rule in model.rules):
            accepted.append(word)
            if len(accepted) == spec.max_traces:
                break
    return tuple(accepted), attempt


@pytest.mark.parametrize("seed", [0, 9, -5, 7381923])
def test_seeded_rejection_matches_explicit_proposal_distribution(seed):
    model = DeclareModel(
        ("A", "B", "C"),
        (DeclareConstraint("existence", "A"), DeclareConstraint("response", "A", "B")),
    )
    spec = DeclarePlayoutSpec(seed=seed, min_events=1, max_events=5, max_traces=50)
    expected, attempts = independent_proposals(model, spec)
    result = play_out_declare(model, spec)
    assert result.value.traces == expected
    assert result.value.attempted_proposals == attempts
    assert result.value.rejected_proposals == attempts - 50
    assert result.value.interrupted_proposals == 0
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.population_size is None
    assert result.value.requested_count_reached
    assert (
        result.value.proposal_distribution == "uniform-length-then-iid-uniform-activity"
    )
    assert result == play_out_declare(model, spec)


def test_samples_allow_duplicates_and_never_claim_uniform_all_length_language():
    model = DeclareModel(("A", "B"), ())
    spec = DeclarePlayoutSpec(seed=17, max_events=2, max_traces=100)
    result = play_out_declare(model, spec)
    expected, _ = independent_proposals(model, spec)
    assert result.value.traces == expected
    assert len(set(result.value.traces)) < len(result.value.traces)
    # P(epsilon)=1/3, P(A)=1/6, P(AA)=1/12 under this proposal, rather than
    # 1/7 for each word. The policy is tested by exact PRNG draws, not flaky
    # sample-frequency thresholds.
    assert (
        result.value.accepted_distribution
        == "proposal-conditioned-on-closed-model-satisfaction"
    )


def test_rejection_budget_cannot_certify_unsatisfiability_or_guarantee_fill():
    model = DeclareModel(
        ("A", "B"),
        (DeclareConstraint("existence", "A"), DeclareConstraint("absence", "A")),
    )
    result = play_out_declare(
        model, DeclarePlayoutSpec(max_events=2, max_traces=2, max_attempts=5)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces == ()
    assert result.value.attempted_proposals == result.value.rejected_proposals == 5
    assert not result.value.empty_population_proven
    assert result.value.population_size is None
    assert result.value.termination == "attempt_limit"


def test_partial_samples_remain_valid_under_attempt_budget():
    model = DeclareModel(("A", "B"), (DeclareConstraint("init", "A"),))
    spec = DeclarePlayoutSpec(seed=9, max_events=3, max_traces=100, max_attempts=8)
    result = play_out_declare(model, spec)
    expected, attempts = independent_proposals(model, spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces == expected
    assert result.value.attempted_proposals == attempts == 8
    assert all(word[0] == "A" for word in result.value.traces)


def test_prefix_budget_reserves_complete_candidate_before_drawing():
    model = DeclareModel(("A",), ())
    result = play_out_declare(
        model, DeclarePlayoutSpec(min_events=3, max_events=3, max_prefix_states=2)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.evaluated_prefixes == 1
    assert result.value.traces == ()
    assert result.value.attempted_proposals == result.value.interrupted_proposals == 0
    assert result.value.rejected_proposals == 0
    assert result.value.termination == "prefix_state_limit"


def test_prefix_budget_retains_only_complete_independently_drawn_proposals():
    model = DeclareModel(("A",), ())
    result = play_out_declare(
        model, DeclarePlayoutSpec(min_events=3, max_events=3, max_prefix_states=7)
    )
    assert result.value.traces == (("A", "A", "A"),) * 2
    assert result.value.evaluated_prefixes == 7
    assert result.value.attempted_proposals == 2
    assert result.value.interrupted_proposals == 0
    assert result.status is ComputeStatus.PARTIAL


def test_empty_alphabet_sampler_draws_epsilon_only_when_admissible():
    model = DeclareModel((), ())
    result = play_out_declare(
        model, DeclarePlayoutSpec(max_traces=4, max_prefix_states=1)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.traces == ((),) * 4
    assert result.value.population_size == 1
    assert result.value.evaluated_prefixes == 1
    empty = play_out_declare(model, DeclarePlayoutSpec(min_events=1))
    assert empty.status is ComputeStatus.COMPUTED
    assert empty.value.empty_population_proven
    assert empty.value.population_size == 0
    assert not empty.value.requested_count_reached


def test_root_irreversible_violation_is_proven_empty_without_sampling():
    model = DeclareModel(("A",), (DeclareConstraint("absence", "A", cardinality=0),))
    result = play_out_declare(model)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.empty_population_proven and result.value.population_size == 0
    assert result.value.attempted_proposals == 0
    assert result.value.evaluated_prefixes == 1


def test_epsilon_only_length_domain_is_solved_exactly():
    model = DeclareModel(("A",), (DeclareConstraint("existence", "A"),))
    empty = play_out_declare(model, DeclarePlayoutSpec(max_events=0))
    accepted = play_out_declare(
        DeclareModel(("A",), ()),
        DeclarePlayoutSpec(max_events=0, max_traces=3, max_prefix_states=1),
    )
    assert empty.status is ComputeStatus.COMPUTED
    assert empty.value.empty_population_proven and empty.value.population_size == 0
    assert empty.value.attempted_proposals == 0
    assert accepted.value.traces == ((), (), ())
    assert accepted.value.population_size == 1


def test_model_and_budget_are_in_request_identity_and_source_is_model_hash():
    model = DeclareModel(("A", "B"), ())
    one = generate_declare_language(model, DeclareLanguageSpec(max_events=1))
    two = generate_declare_language(model, DeclareLanguageSpec(max_events=2))
    other = generate_declare_language(
        DeclareModel(("A", "B"), (DeclareConstraint("init", "A"),))
    )
    assert one.source_digest == two.source_digest
    assert one.computation_id != two.computation_id
    assert one.source_digest != other.source_digest
    assert one.spec.model == model
    assert one.source_digest.startswith("pix.declare-model.v1:sha256:")
    assert len(one.source_digest.rsplit(":", 1)[1]) == 64
    first = play_out_declare(model, DeclarePlayoutSpec(seed=2, max_traces=2))
    second = play_out_declare(model, DeclarePlayoutSpec(seed=3, max_traces=2))
    assert first.source_digest == second.source_digest
    assert first.computation_id != second.computation_id


@pytest.mark.parametrize("kind", [DeclareLanguageSpec, DeclarePlayoutSpec])
@pytest.mark.parametrize(
    "options",
    [
        {"min_events": -1},
        {"max_events": -1},
        {"max_events": True},
        {"min_events": 2, "max_events": 1},
        {"max_events": 10_001},
        {"max_traces": 0},
        {"max_traces": False},
        {"max_prefix_states": 0},
    ],
)
def test_invalid_bounds_rejected(kind, options):
    with pytest.raises((TypeError, ValueError)):
        kind(**options)


def test_sampling_seed_and_attempt_budget_validation():
    with pytest.raises(TypeError):
        DeclarePlayoutSpec(seed=True)
    with pytest.raises(ValueError):
        DeclarePlayoutSpec(max_attempts=0)


def test_unregistered_spec_subclasses_are_rejected():
    @dataclass(frozen=True, slots=True)
    class OtherLanguageSpec(DeclareLanguageSpec):
        extra: str = "unregistered"

    @dataclass(frozen=True, slots=True)
    class OtherPlayoutSpec(DeclarePlayoutSpec):
        extra: str = "unregistered"

    with pytest.raises(TypeError):
        generate_declare_language(DeclareModel((), ()), OtherLanguageSpec())
    with pytest.raises(TypeError):
        play_out_declare(DeclareModel((), ()), OtherPlayoutSpec())


def test_result_schemas_are_self_describing_and_include_model():
    from pix.case_centric.declarative_simulation import RESULT_SCHEMAS

    model = DeclareModel(("A",), ())
    for result in (generate_declare_language(model), play_out_declare(model)):
        _, spec_type, value_type = RESULT_SCHEMAS[result.operator_id]
        assert type(result.spec) is spec_type
        assert type(result.value) is value_type
        assert result.spec.model == model


def test_registered_results_round_trip_with_model_evidence_and_partial_states():
    from pix.case_centric.declarative import DeclareRuleEvidence
    from pix.results import result_from_json, result_json_bytes

    rule = DeclareConstraint("existence", "A")
    model = DeclareModel(
        ("A", "B"), (rule,), (DeclareRuleEvidence(rule, 1, 1, 0, 1, 1),), 1
    )
    calculations = (
        generate_declare_language(model, DeclareLanguageSpec(max_events=2)),
        generate_declare_language(
            model, DeclareLanguageSpec(max_events=2, max_traces=1)
        ),
        generate_declare_language(model, DeclareLanguageSpec(max_prefix_states=1)),
        play_out_declare(model, DeclarePlayoutSpec(seed=4, max_traces=3)),
        play_out_declare(
            model, DeclarePlayoutSpec(seed=4, max_traces=3, max_attempts=1)
        ),
        play_out_declare(model, DeclarePlayoutSpec(max_prefix_states=1)),
        play_out_declare(model, DeclarePlayoutSpec(max_events=0)),
        play_out_declare(DeclareModel((), ()), DeclarePlayoutSpec(max_traces=2)),
    )
    for result in calculations:
        assert result_from_json(result_json_bytes(result)) == result
