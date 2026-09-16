"""Hand-counted precision populations, projected witnesses, and closure limits."""

from dataclasses import replace
from fractions import Fraction
from itertools import product

import pytest

from pix.case_centric.advanced_precision import (
    AutomatonPrecisionSpec,
    DFGPrecisionSpec,
    measure_automaton_precision,
    measure_dfg_precision,
)
from pix.case_centric.conformance import measure_et_precision
from pix.case_centric.sequence_alignment import DFGAlignmentModel
from pix.contracts.conformance import AlignmentSpec
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


def net_from_edges(places, transitions, edges, initial="p0", final="f"):
    return PetriNet(
        tuple(Place(place) for place in places),
        tuple(Transition(identity, label) for identity, label in transitions),
        tuple(Arc(*edge) for edge in edges),
        Marking(((initial, 1),)),
        Marking(((final, 1),)),
    )


def sequence_net(*activities):
    return net_from_edges(
        tuple(f"p{i}" for i in range(len(activities) + 1)),
        tuple((f"t{i}", activity) for i, activity in enumerate(activities)),
        tuple(
            edge
            for i in range(len(activities))
            for edge in ((f"p{i}", f"t{i}"), (f"t{i}", f"p{i + 1}"))
        ),
        final=f"p{len(activities)}",
    )


def duplicate_branch_net():
    return net_from_edges(
        ("p0", "left", "right", "f"),
        (("a_b", "A"), ("a_c", "A"), ("b", "B"), ("c", "C")),
        (
            ("p0", "a_b"),
            ("a_b", "left"),
            ("left", "b"),
            ("b", "f"),
            ("p0", "a_c"),
            ("a_c", "right"),
            ("right", "c"),
            ("c", "f"),
        ),
    )


def shared_branch_net():
    return net_from_edges(
        ("p0", "after_a", "f"),
        (("a", "A"), ("b", "B"), ("c", "C")),
        (
            ("p0", "a"),
            ("a", "after_a"),
            ("after_a", "b"),
            ("b", "f"),
            ("after_a", "c"),
            ("c", "f"),
        ),
    )


def ratio(value):
    return None if value is None else Fraction(*value)


def test_dfg_hand_counted_frequency_weights_and_empty_cases():
    model = DFGAlignmentModel(
        ("A", "B", "C", "D"),
        (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")),
        ("A", "D"),
        ("D",),
    )
    result = measure_dfg_precision(log("ABD", "ABD", "ACD", ""), model)
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert (value.weighted_enabled, value.weighted_escaping) == (15, 3)
    assert ratio(value.whole_population_ratio) == Fraction(4, 5)
    assert tuple((item.prefix, item.weight) for item in value.prefixes) == (
        ((), 3),
        (("A",), 3),
        (("A", "B"), 2),
        (("A", "C"), 1),
    )
    assert value.requested_cases == 4
    assert value.empty_cases == 1


def test_dfg_end_annotations_do_not_add_termination_edges():
    model = DFGAlignmentModel(("A", "B"), (("A", "B"),), ("A",), ("B",))
    original = measure_dfg_precision(log("AB", "A"), model)
    changed = measure_dfg_precision(
        log("AB", "A"), replace(model, ends=("A",), accepts_empty=True)
    )
    assert original.value == changed.value
    assert original.computation_id != changed.computation_id
    assert original.value.whole_population_ratio == (1, 1)
    assert tuple(item.prefix for item in original.value.prefixes) == ((), ("A",))


def test_dfg_illegal_prefixes_are_reported_without_fabricated_available_labels():
    model = DFGAlignmentModel(("A", "B", "C"), (("A", "B"),), ("A",), ("B",))
    value = measure_dfg_precision(log("XA", "ACB", "ABA"), model).value
    by_prefix = {item.prefix: item for item in value.prefixes}
    assert by_prefix[("X",)].status == "unfit_start"
    assert by_prefix[("A", "C")].status == "unfit_edge"
    assert by_prefix[("A", "B")].status == "no_outgoing"
    assert value.excluded_prefix_count == 3
    assert value.excluded_weight == 3
    assert value.whole_population_ratio is None
    assert all(
        item.enabled_labels is None
        for item in by_prefix.values()
        if item.status != "computed"
    )


def test_dfg_empty_population_and_zero_denominator_are_undefined():
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    for data in (log(), log("")):
        result = measure_dfg_precision(data, model)
        assert result.value.prefixes == ()
        assert result.value.whole_population_ratio is None
    no_starts = measure_dfg_precision(log("A"), replace(model, starts=()))
    assert no_starts.value.weighted_enabled == 0
    assert no_starts.value.computed_prefix_ratio is None


def independent_dfg_counts(words, model):
    """Enumerate candidate prefixes by length, rather than updating an event trie."""
    prefixes = {tuple(word[:length]) for word in words for length in range(len(word))}
    enabled_total = escaping_total = 0
    excluded = 0
    for prefix in prefixes:
        eligible = [
            word
            for word in words
            if len(word) > len(prefix) and tuple(word[: len(prefix)]) == prefix
        ]
        following = {word[len(prefix)] for word in eligible}
        possible = (
            {right for left, right in model.edges if prefix and left == prefix[-1]}
            if prefix
            else set(model.starts)
        )
        legal = not prefix or (
            prefix[0] in model.starts
            and all(
                (prefix[i], prefix[i + 1]) in model.edges
                for i in range(len(prefix) - 1)
            )
            and bool(possible)
        )
        if legal:
            enabled_total += len(eligible) * len(possible)
            escaping_total += len(eligible) * len(possible - following)
        else:
            excluded += 1
    return enabled_total, escaping_total, excluded


def test_dfg_counts_exhaustive_small_graphs_independent_prefix_population():
    words = (
        (),
        ("A",),
        ("B",),
        ("A", "A"),
        ("A", "B"),
        ("A", "B"),
        ("B", "A"),
        ("B", "B"),
    )
    candidates = tuple(product("AB", repeat=2))
    for bits in product((False, True), repeat=4):
        edges = tuple(edge for exists, edge in zip(bits, candidates) if exists)
        for starts in ((), ("A",), ("B",), ("A", "B")):
            model = DFGAlignmentModel(("A", "B"), edges, starts, ("A", "B"))
            result = measure_dfg_precision(log(*words), model).value
            assert (
                result.weighted_enabled,
                result.weighted_escaping,
                result.excluded_prefix_count,
            ) == independent_dfg_counts(words, model)


def test_missing_initial_activity_is_inserted_in_model_automaton():
    result = measure_automaton_precision(log("B"), sequence_net("A", "B"))
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert value.projections[0].symbols == ("A", "B")
    assert value.projections[0].alignment_cost == 1
    assert (value.weighted_enabled, value.weighted_escaping) == (2, 0)
    assert value.whole_population_ratio == (1, 1)
    assert any(
        move.kind == "model" and move.activity == "A"
        for move in value.alignment_evidence.alignments[0].moves
    )


def test_automaton_frequency_counts_repaired_projection_of_every_case():
    value = measure_automaton_precision(
        log("AC", "AC", "X"), sequence_net("A", "B", "C")
    ).value
    assert tuple(item.symbols for item in value.projections) == (("A", "B", "C"),) * 3
    assert tuple((item.prefix, item.weight) for item in value.prefixes) == (
        ((), 3),
        (("A",), 3),
        (("A", "B"), 3),
    )
    assert (value.weighted_enabled, value.weighted_escaping) == (9, 0)
    assert value.whole_population_ratio == (1, 1)


def test_model_completion_adds_automaton_prefix_missing_from_raw_trace():
    model = shared_branch_net()
    repaired = measure_automaton_precision(log("A"), model).value
    raw = measure_et_precision(log("A"), model).value
    assert repaired.projections[0].symbols == ("A", "B")
    assert repaired.weighted_enabled == 3
    assert repaired.weighted_escaping == 1
    assert ratio(repaired.whole_population_ratio) == Fraction(2, 3)
    assert raw.whole_population_ratio == (1, 1)


def test_log_only_moves_do_not_become_automaton_symbols():
    value = measure_automaton_precision(log("XAB"), shared_branch_net()).value
    assert value.projections[0].symbols == ("A", "B")
    assert all("X" not in prefix.prefix for prefix in value.prefixes)
    assert ratio(value.whole_population_ratio) == Fraction(2, 3)


def test_duplicate_label_actual_marking_differs_from_all_prefix_reachable_markings():
    model = duplicate_branch_net()
    automaton = measure_automaton_precision(log("AB"), model).value
    raw = measure_et_precision(log("AB"), model).value
    assert automaton.whole_population_ratio == (1, 1)
    assert ratio(raw.whole_population_ratio) == Fraction(2, 3)
    after_a = next(item for item in automaton.prefixes if item.prefix == ("A",))
    assert after_a.reached_markings == (Marking((("left", 1),)),)
    assert after_a.enabled_symbols == ("B",)


def test_duplicate_label_task_id_mode_counts_distinct_root_choices():
    value = measure_automaton_precision(
        log("AB"),
        duplicate_branch_net(),
        AutomatonPrecisionSpec(symbol_mode="transition_id"),
    ).value
    assert value.projections[0].symbols == ("a_b", "b")
    assert value.prefixes[0].enabled_symbols == ("a_b", "a_c")
    assert value.prefixes[0].escaping_symbols == ("a_c",)
    assert ratio(value.whole_population_ratio) == Fraction(2, 3)


def test_multiple_aligned_branches_union_markings_for_same_visible_prefix():
    value = measure_automaton_precision(
        log("AB", "AC", "AC"), duplicate_branch_net()
    ).value
    after_a = next(item for item in value.prefixes if item.prefix == ("A",))
    assert after_a.weight == 3
    assert after_a.enabled_symbols == after_a.executed_symbols == ("B", "C")
    assert after_a.reached_markings == (
        Marking((("left", 1),)),
        Marking((("right", 1),)),
    )
    assert value.weighted_enabled == 9
    assert value.whole_population_ratio == (1, 1)


def test_silent_moves_affect_markings_but_are_not_symbols():
    value = measure_automaton_precision(
        log("AB"), sequence_net(None, "A", None, "B", None)
    ).value
    assert value.projections[0].symbols == ("A", "B")
    assert value.projections[0].visible_transition_ids == ("t1", "t3")
    assert value.prefixes[0].enabled_symbols == ("A",)
    after_a = next(item for item in value.prefixes if item.prefix == ("A",))
    assert after_a.reached_markings == (Marking((("p2", 1),)),)
    assert after_a.enabled_symbols == ("B",)
    assert after_a.explored_closure_markings == 2
    assert value.whole_population_ratio == (1, 1)


def test_full_marking_silent_closure_retains_both_converging_branches():
    model = net_from_edges(
        ("p0", "q", "rA", "rB", "s", "f"),
        (("tau_a", None), ("tau_b", None), ("tau_c", None), ("a", "A"), ("b", "B")),
        (
            ("p0", "tau_a"),
            ("tau_a", "q"),
            ("tau_a", "rA"),
            ("p0", "tau_b"),
            ("tau_b", "q"),
            ("tau_b", "rB"),
            ("q", "tau_c"),
            ("tau_c", "s"),
            ("s", "a"),
            ("rA", "a"),
            ("a", "f"),
            ("s", "b"),
            ("rB", "b"),
            ("b", "f"),
        ),
    )
    value = measure_automaton_precision(log("A"), model).value
    root = value.prefixes[0]
    assert root.enabled_symbols == ("A", "B")
    assert root.explored_closure_markings == 5
    assert value.whole_population_ratio == (1, 2)


def test_literal_skip_like_symbol_is_a_normal_activity():
    value = measure_automaton_precision(log((">>", "B")), sequence_net(">>", "B")).value
    assert value.projections[0].symbols == (">>", "B")
    assert value.whole_population_ratio == (1, 1)


def test_empty_case_is_aligned_and_root_weighted_but_empty_log_is_not():
    model = sequence_net("A")
    case = measure_automaton_precision(log(""), model).value
    assert case.projections[0].symbols == ("A",)
    assert case.prefixes[0].weight == 1
    assert case.whole_population_ratio == (1, 1)
    empty = measure_automaton_precision(log(), model).value
    assert empty.prefixes == ()
    assert empty.whole_population_ratio is None
    no_actions = measure_automaton_precision(log(""), sequence_net()).value
    assert no_actions.projections[0].symbols == ()
    assert no_actions.prefixes[0].weight == 1
    assert no_actions.whole_population_ratio is None


def test_alignment_cap_retains_only_explicitly_completed_population():
    value = measure_automaton_precision(
        log("A", "X"),
        sequence_net("A"),
        AutomatonPrecisionSpec(alignment=AlignmentSpec(max_states=2)),
    )
    assert value.status is ComputeStatus.PARTIAL
    assert value.value.aligned_cases == 1
    assert value.value.limited_alignment_cases == 1
    assert value.value.prefixes[0].weight == 1
    assert value.value.computed_prefix_ratio == (1, 1)
    assert value.value.whole_population_ratio is None


def test_unreachable_net_does_not_yield_perfect_precision():
    model = net_from_edges(("p0", "f"), (), ())
    result = measure_automaton_precision(log("A"), model)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.unreachable_cases == 1
    assert result.value.prefixes == ()
    assert result.value.whole_population_ratio is None


def test_unbounded_silent_closure_reports_unknown_available_symbols():
    model = net_from_edges(
        ("p0", "f"),
        (("a", "A"), ("tau", None)),
        (("p0", "a"), ("a", "f"), ("p0", "tau"), ("tau", "p0", 2)),
    )
    result = measure_automaton_precision(
        log("A"), model, AutomatonPrecisionSpec(max_closure_states=4)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.aligned_cases == 1
    assert result.value.limited_prefixes == 1
    assert result.value.prefixes[0].enabled_symbols is None
    assert result.value.prefixes[0].explored_closure_markings == 4
    assert result.value.computed_prefix_ratio is None


def test_union_initial_markings_are_also_subject_to_closure_cap():
    result = measure_automaton_precision(
        log("AB", "AC"),
        duplicate_branch_net(),
        AutomatonPrecisionSpec(max_closure_states=1),
    )
    assert result.status is ComputeStatus.PARTIAL
    after_a = next(item for item in result.value.prefixes if item.prefix == ("A",))
    assert after_a.status == "search_limit"
    assert after_a.enabled_symbols is None
    assert result.value.whole_population_ratio is None


def test_identity_covers_symbol_choice_and_closure_limits():
    model = duplicate_branch_net()
    original = measure_automaton_precision(log("AB"), model)
    changed = measure_automaton_precision(
        log("AB"), model, AutomatonPrecisionSpec(symbol_mode="transition_id")
    )
    bounded = measure_automaton_precision(
        log("AB"), model, AutomatonPrecisionSpec(max_closure_states=99)
    )
    assert (
        len({original.computation_id, changed.computation_id, bounded.computation_id})
        == 3
    )


def test_invalid_upstream_propagates_without_precision_calculation():
    source = case_traces(log("A"))
    failed = replace(
        source,
        status=ComputeStatus.INVALID_INPUT,
        value=None,
        issues=(ComputeIssue("fixture_invalid", "invalid fixture"),),
    )
    model = DFGAlignmentModel(("A",), (), ("A",), ("A",))
    for result in (
        measure_dfg_precision(failed, model),
        measure_automaton_precision(failed, sequence_net("A")),
    ):
        assert result.status is ComputeStatus.INVALID_INPUT
        assert result.value is None
        assert result.issues[0].code == "fixture_invalid"


@pytest.mark.parametrize(
    "factory",
    [
        lambda: DFGPrecisionSpec(termination="include"),
        lambda: AutomatonPrecisionSpec(alignment=None),
        lambda: AutomatonPrecisionSpec(symbol_mode="label"),
        lambda: AutomatonPrecisionSpec(max_closure_states=0),
        lambda: AutomatonPrecisionSpec(max_closure_states=True),
    ],
)
def test_precision_spec_validation(factory):
    with pytest.raises((TypeError, ValueError)):
        factory()
