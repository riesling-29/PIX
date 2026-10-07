"""Independent metric arithmetic, finite languages, and bounded-state evidence."""

from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from pix.case_centric.conformance import (
    AlignmentFitnessSpec,
    ETPrecisionSpec,
    GeneralizationSpec,
    TokenFitnessSpec,
    measure_alignment_fitness,
    measure_et_precision,
    measure_token_fitness,
    measure_token_generalization,
)
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.replay import ReplaySpec
from pix.contracts.result import ComputeStatus
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


def duplicate_branch_net(silent_detour=False):
    places = tuple(Place(p) for p in ("start", "left", "right", "finish", "detour"))
    transitions = [
        Transition("a1", "A"),
        Transition("a2", "A"),
        Transition("b", "B"),
        Transition("c", "C"),
    ]
    arcs = [
        Arc("start", "a1"),
        Arc("a1", "left"),
        Arc("a2", "right"),
        Arc("left", "b"),
        Arc("b", "finish"),
        Arc("right", "c"),
        Arc("c", "finish"),
    ]
    if silent_detour:
        transitions.append(Transition("tau"))
        arcs += [Arc("start", "tau"), Arc("tau", "detour"), Arc("detour", "a2")]
    else:
        arcs.append(Arc("start", "a2"))
    return PetriNet(
        places,
        tuple(transitions),
        tuple(arcs),
        Marking((("start", 1),)),
        Marking((("finish", 1),)),
    )


def growing_silent_net():
    return PetriNet(
        (Place("p"), Place("f")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "p", 2), Arc("p", "a"), Arc("a", "f")),
        Marking((("p", 1),)),
        Marking((("f", 1),)),
    )


def ratio(value):
    return None if value is None else Fraction(*value)


def insertion_deletion_distance(left, right):
    # Independent bottom-up word-distance oracle, without Petri-net semantics.
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(len(left) + 1):
        table[i][0] = i
    for j in range(len(right) + 1):
        table[0][j] = j
    for i in range(1, len(left) + 1):
        for j in range(1, len(right) + 1):
            table[i][j] = min(
                table[i - 1][j] + 1,
                table[i][j - 1] + 1,
                table[i - 1][j - 1] + (0 if left[i - 1] == right[j - 1] else 2),
            )
    return table[-1][-1]


def test_token_fitness_pooled_tokens_and_case_mean_are_distinct():
    result = measure_token_fitness(log("A", "A", "A", "A", ""), sequence_net("A"))
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert ratio(value.whole_log_fitness_ratio) == Fraction(8, 9)
    assert ratio(value.whole_mean_trace_fitness_ratio) == Fraction(4, 5)
    assert value.whole_fitting_trace_ratio == (4, 5)
    assert value.completed_counts.missing == value.completed_counts.remaining == 1
    assert value.completed_counts.produced == value.completed_counts.consumed == 9
    assert value.traces[-1].strictly_fitting is False


def test_unknown_activity_is_never_strictly_fitting_even_when_token_balance_is_one():
    value = measure_token_fitness(log("AX"), sequence_net("A")).value
    assert ratio(value.whole_log_fitness_ratio) == 1
    assert value.traces[0].log_deviation_count == 1
    assert value.whole_fitting_trace_ratio == (0, 1)


def test_empty_population_is_distinct_from_empty_accepted_trace():
    net = sequence_net()
    assert measure_token_fitness(log(), net).value.whole_log_fitness_ratio is None
    assert ratio(measure_token_fitness(log(""), net).value.whole_log_fitness_ratio) == 1
    assert measure_alignment_fitness(log(), net).value.whole_log_fitness_ratio is None
    accepted = measure_alignment_fitness(log(""), net).value
    assert accepted.shortest_model_completion_cost == 0
    assert accepted.traces[0].best_worst_cost == 0
    assert accepted.whole_log_fitness_ratio == (1, 1)


def test_zero_token_denominator_is_undefined():
    net = PetriNet((), (), (), Marking(), Marking())
    result = measure_token_fitness(log(""), net)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.traces[0].status == "undefined_denominator"
    assert result.value.whole_log_fitness_ratio is None
    assert result.value.whole_mean_trace_fitness_ratio is None


def test_alignment_pooled_best_worst_and_case_mean():
    value = measure_alignment_fitness(
        log("A", "A", "A", "A", ""), sequence_net("A")
    ).value
    assert value.completed_best_worst_sum == 9
    assert value.completed_cost_sum == 1
    assert ratio(value.whole_log_fitness_ratio) == Fraction(8, 9)
    assert ratio(value.whole_mean_trace_fitness_ratio) == Fraction(4, 5)


@pytest.mark.parametrize("model_word", ((), ("A",), ("A", "B"), ("A", "A")))
def test_alignment_fitness_against_independent_finite_word_distance(model_word):
    sequences = tuple(
        word for length in range(4) for word in product(("A", "B"), repeat=length)
    )
    value = measure_alignment_fitness(log(*sequences), sequence_net(*model_word)).value
    for observed, actual in zip(sequences, value.traces):
        cost = insertion_deletion_distance(observed, model_word)
        worst = len(observed) + len(model_word)
        assert actual.alignment_cost == cost
        assert actual.best_worst_cost == worst
        assert ratio(actual.fitness_ratio) == (
            Fraction(worst - cost, worst) if worst else 1
        )


def test_alignment_custom_positive_deviation_costs():
    value = measure_alignment_fitness(
        log("X"),
        sequence_net("A"),
        AlignmentFitnessSpec(AlignmentSpec(log_move_cost=2, model_move_cost=3)),
    ).value
    assert value.traces[0].alignment_cost == 5
    assert value.traces[0].best_worst_cost == 5
    assert value.whole_log_fitness_ratio == (0, 1)


@pytest.mark.parametrize(
    "costs",
    (
        AlignmentSpec(log_move_cost=0),
        AlignmentSpec(model_move_cost=0),
        AlignmentSpec(silent_move_cost=1),
        AlignmentSpec(synchronous_move_cost=1),
    ),
)
def test_invalid_normalized_fitness_profiles_are_rejected(costs):
    with pytest.raises(ValueError):
        AlignmentFitnessSpec(costs)


def test_empty_model_language_has_no_normalizer_or_fabricated_zero_fitness():
    net = PetriNet(
        (Place("s"), Place("f")), (), (), Marking((("s", 1),)), Marking((("f", 1),))
    )
    result = measure_alignment_fitness(log("A"), net)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.model_completion_status == "unreachable"
    assert result.value.whole_log_fitness_ratio is None
    assert result.value.traces[0].fitness_ratio is None


def test_alignment_state_limit_keeps_whole_fitness_unknown():
    result = measure_alignment_fitness(
        log("A"), sequence_net("A"), AlignmentFitnessSpec(AlignmentSpec(max_states=1))
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.model_completion_status == "search_limit"
    assert result.value.whole_log_fitness_ratio is None


def test_replay_limit_excludes_live_prefix_from_token_fitness_and_generalization():
    net = growing_silent_net()
    fit = measure_token_fitness(log("B"), net, TokenFitnessSpec(ReplaySpec(2)))
    gen = measure_token_generalization(log("B"), net, GeneralizationSpec(ReplaySpec(2)))
    assert fit.status is gen.status is ComputeStatus.PARTIAL
    assert fit.value.completed_count == 0
    assert fit.value.whole_log_fitness_ratio is None
    assert gen.value.whole_population_score is None


def test_token_and_alignment_et_are_distinct_on_duplicate_label_choices():
    net = duplicate_branch_net()
    token = measure_et_precision(log("AB"), net, ETPrecisionSpec("token")).value
    aligned = measure_et_precision(log("AB"), net, ETPrecisionSpec("alignment")).value
    assert ratio(token.whole_population_ratio) == 1
    assert ratio(aligned.whole_population_ratio) == Fraction(2, 3)
    assert token.prefixes[1].enabled_labels == ("B",)
    assert aligned.prefixes[1].enabled_labels == ("B", "C")
    assert len(aligned.prefixes[1].stop_markings) == 2


def test_align_et_uses_all_minimum_silent_cost_stops_not_all_reachable_branches():
    value = measure_et_precision(
        log("AB"), duplicate_branch_net(silent_detour=True)
    ).value
    assert value.prefixes[1].minimum_silent_firings == 0
    assert value.prefixes[1].enabled_labels == ("B",)
    assert ratio(value.whole_population_ratio) == 1


def test_et_empty_case_weights_root_but_terminal_prefixes_are_not_scored():
    value = measure_et_precision(log("", "AB"), duplicate_branch_net()).value
    assert tuple(item.prefix for item in value.prefixes) == ((), ("A",))
    assert tuple(item.weight for item in value.prefixes) == (2, 1)
    assert ratio(value.whole_population_ratio) == Fraction(3, 4)


def test_et_unfit_prefix_is_excluded_with_explicit_population_gap():
    result = measure_et_precision(log("AXB"), duplicate_branch_net())
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.unfit_prefix_count == 1
    assert result.value.unfit_weight == 1
    assert ratio(result.value.computed_prefix_ratio) == Fraction(1, 3)
    assert result.value.whole_population_ratio is None


def test_et_closure_cap_never_claims_observed_visible_labels_are_exhaustive():
    result = measure_et_precision(
        log("A"), growing_silent_net(), ETPrecisionSpec(max_states=2)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.prefixes[0].status == "search_limit"
    assert result.value.prefixes[0].enabled_labels is None
    assert result.value.whole_population_ratio is None


def test_et_finite_silent_cycle_exhausts_exactly_at_cap():
    net = PetriNet(
        (Place("p"), Place("f")),
        (Transition("tau"), Transition("a", "A")),
        (Arc("p", "tau"), Arc("tau", "p"), Arc("p", "a"), Arc("a", "f")),
        Marking((("p", 1),)),
        Marking((("f", 1),)),
    )
    result = measure_et_precision(log("A"), net, ETPrecisionSpec(max_states=1))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.whole_population_ratio == (1, 1)


def test_et_zero_denominator_and_empty_population_are_not_default_perfect_scores():
    net = sequence_net()
    assert measure_et_precision(log(""), net).value.whole_population_ratio is None
    assert measure_et_precision(log(), net).value.whole_population_ratio is None


def test_generalization_uses_transition_ids_silent_firings_and_unseen_penalty():
    net = sequence_net(None, "A")
    net = replace(
        net,
        transitions=net.transitions + (Transition("unused", "A"),),
        places=net.places + (Place("unreachable"),),
        arcs=net.arcs + (Arc("unreachable", "unused"), Arc("unused", "unreachable")),
    )
    value = measure_token_generalization(log("A", "A", "A", "A"), net).value
    assert [(item.transition_id, item.firing_count) for item in value.transitions] == [
        ("t0", 4),
        ("t1", 4),
        ("unused", 0),
    ]
    assert value.whole_population_score == pytest.approx(1 / 3)
    assert measure_token_generalization(log(), net).value.whole_population_score is None


@pytest.mark.parametrize(
    "operation",
    (
        measure_alignment_fitness,
        measure_token_fitness,
        measure_et_precision,
        measure_token_generalization,
    ),
)
def test_model_and_source_identity_and_failed_input_propagation(operation):
    source = case_traces(log("A"))
    one = operation(source, sequence_net("A"))
    two = operation(source, sequence_net("B"))
    assert one.computation_id != two.computation_id
    assert one.spec.model_digest == one.value.model_digest
    assert one.parent_computation_ids == (source.computation_id,)
    failed = replace(source, status=ComputeStatus.INVALID_INPUT, value=None)
    result = operation(failed, sequence_net("A"))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


@pytest.mark.parametrize(
    "operation",
    (
        measure_alignment_fitness,
        measure_token_fitness,
        measure_et_precision,
        measure_token_generalization,
    ),
)
def test_quality_contract_round_trip_through_explicit_schema_whitelist(
    operation, monkeypatch
):
    # Namespace integration belongs to root; this tests actual decoder/type
    # support without changing its product whitelist from this worker.
    import pix.results as persistence
    from pix.case_centric.conformance import RESULT_SCHEMAS

    original = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: {**original(), **RESULT_SCHEMAS}
    )
    result = operation(log("AB", "AB", "AX"), duplicate_branch_net())
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result
