"""Manual nets and independent token arithmetic certify analysis boundaries."""

import random
from collections import deque

import pytest

from pix.case_centric.model_analysis import (
    ComplexitySpec,
    InvariantsSpec,
    MarkingEquationSpec,
    ModelComparisonSpec,
    ReachabilitySpec,
    ReductionSpec,
    check_soundness,
    check_workflow_net,
    compare_models,
    decompose_model,
    marking_equation_bound,
    model_complexity,
    model_incidence,
    model_invariants,
    reachability,
    reduce_model,
)
from pix.compute.model_semantics import model_digest
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus


def net(places, transitions, arcs, initial, final):
    return PetriNet(
        tuple(Place(p) for p in places),
        tuple(Transition(t, a) for t, a in transitions),
        tuple(Arc(*a) for a in arcs),
        Marking(tuple(initial)),
        Marking(tuple(final)),
    )


def chain(label="A", prefix=""):
    return net(
        (prefix + "i", prefix + "o"),
        ((prefix + "a", label),),
        ((prefix + "i", prefix + "a"), (prefix + "a", prefix + "o")),
        ((prefix + "i", 1),),
        ((prefix + "o", 1),),
    )


def independent_graph(model, max_states=1000, max_tokens=20):
    """No production firing helper: direct tuple-vector arithmetic oracle."""
    place_ids = tuple(p.id for p in model.places)
    n = len(place_ids)
    before, after = {}, {}
    for t in model.transitions:
        before[t.id] = tuple(
            sum(a.weight for a in model.arcs if a.source == p and a.target == t.id)
            for p in place_ids
        )
        after[t.id] = tuple(
            sum(a.weight for a in model.arcs if a.source == t.id and a.target == p)
            for p in place_ids
        )
    initial = tuple(dict(model.initial_marking.tokens).get(p, 0) for p in place_ids)
    seen = {initial}
    queue = deque((initial,))
    edges = set()
    while queue:
        state = queue.popleft()
        for t in model.transitions:
            if any(state[i] < before[t.id][i] for i in range(n)):
                continue
            target = tuple(
                state[i] - before[t.id][i] + after[t.id][i] for i in range(n)
            )
            if sum(target) > max_tokens:
                continue
            if target not in seen:
                if len(seen) >= max_states:
                    continue
                seen.add(target)
                queue.append(target)
            edges.add((state, t.id, target))
    return seen, edges, place_ids


def accepted_words(model, max_length=4):
    """Finite independent BFS over (count vector, visible word)."""
    _, edges, place_ids = independent_graph(model)
    initial = tuple(dict(model.initial_marking.tokens).get(p, 0) for p in place_ids)
    final = tuple(dict(model.final_marking.tokens).get(p, 0) for p in place_ids)
    labels = {t.id: t.activity for t in model.transitions}
    pending = deque(((initial, ()),))
    seen = {(initial, ())}
    accepted = set()
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        for source, tid, target in edges:
            if source != marking:
                continue
            after_word = word if labels[tid] is None else word + (labels[tid],)
            state = (target, after_word)
            if len(after_word) <= max_length and state not in seen:
                seen.add(state)
                pending.append(state)
    return accepted


def test_sequence_reachability_soundness_and_identities():
    model = chain()
    result = reachability(model)
    assert result.status is ComputeStatus.COMPUTED
    assert result.source_digest == model_digest(model)
    assert result.value.markings == (Marking((("i", 1),)), Marking((("o", 1),)))
    assert [(e.source, e.transition_id, e.target) for e in result.value.edges] == [
        (0, "a", 1)
    ]
    sound = check_soundness(model).value
    assert sound.sound is True and sound.bounded is True
    assert sound.assessment == "proven_finite"
    assert (
        sound.option_to_complete,
        sound.proper_completion,
        sound.no_dead_transitions,
    ) == (True, True, True)
    assert reachability(model, ReachabilitySpec(2, 1)).value.complete
    assert (
        result.computation_id
        != reachability(model, ReachabilitySpec(2, 1)).computation_id
    )


def test_weighted_arc_reachability_and_workflow_marking_rejection():
    model = net(
        ("i", "o"),
        (("a", "A"),),
        (("i", "a", 2), ("a", "o", 3)),
        (("i", 2),),
        (("o", 3),),
    )
    report = check_soundness(model).value
    assert report.structure.graph_is_workflow_net
    assert not report.structure.accepting_markings_are_workflow_markings
    assert report.option_to_complete and report.proper_completion
    assert report.sound is False
    assert report.assessment == "not_an_accepting_workflow_net"
    assert reachability(model).value.max_observed_tokens == 3


def test_parallel_split_join_is_sound():
    model = net(
        ("i", "l", "r", "o"),
        (("s", None), ("j", "J")),
        (("i", "s"), ("s", "l"), ("s", "r"), ("l", "j"), ("r", "j"), ("j", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    report = check_soundness(model).value
    assert report.sound and report.reachability.max_observed_tokens == 2
    assert accepted_words(model) == {("J",)}


def test_dead_transition_and_deadlock_are_separate_diagnostics():
    # Structural path exists, but the only transition requires two source tokens.
    model = net(
        ("i", "o"), (("a", "A"),), (("i", "a", 2), ("a", "o")), (("i", 1),), (("o", 1),)
    )
    report = check_soundness(model).value
    assert report.structure.is_accepting_workflow_net
    assert report.sound is False and report.option_to_complete is False
    assert report.no_dead_transitions is False
    assert report.dead_transition_ids == ("a",)
    assert report.deadlock_states == (0,)


def test_livelock_with_possible_exit_is_sound_not_universally_terminating():
    model = net(
        ("i", "p", "o"),
        (("start", "A"), ("loop", None), ("end", "B")),
        (
            ("i", "start"),
            ("start", "p"),
            ("p", "loop"),
            ("loop", "p"),
            ("p", "end"),
            ("end", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    assert check_soundness(model).value.sound is True
    assert accepted_words(model) == {("A", "B")}


def test_nonfinal_closed_livelock_has_no_option_to_complete():
    model = net(
        ("i", "p", "o"),
        (("start", "A"), ("loop", None), ("end", "B")),
        (
            ("i", "start"),
            ("start", "p"),
            ("p", "loop"),
            ("loop", "p"),
            ("p", "end", 2),
            ("end", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    report = check_soundness(model).value
    assert report.sound is False
    assert report.option_to_complete is False
    assert report.deadlock_states == ()
    assert len(report.noncompleting_states) == 2


def test_improper_completion_contains_final_plus_extra_token():
    model = net(
        ("i", "p", "o"),
        (("split", "A"), ("end", "B")),
        (("i", "split"), ("split", "p"), ("split", "o"), ("p", "end"), ("end", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    report = check_soundness(model).value
    assert report.proper_completion is False
    assert report.improper_completion_states
    assert report.sound is False


def test_token_bound_does_not_report_unsoundness_or_unboundedness():
    # Workflow net with increasing tokens; initial transition is admitted.
    model = net(
        ("i", "p", "o"),
        (("s", None), ("grow", "G"), ("end", "E")),
        (
            ("i", "s"),
            ("s", "p"),
            ("p", "grow"),
            ("grow", "p", 2),
            ("p", "end"),
            ("end", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    result = check_soundness(model, ReachabilitySpec(10, 1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.sound is None
    assert result.value.bounded is None
    assert result.value.proper_completion is None
    assert (
        result.value.no_dead_transitions is True
    )  # enabled grow is a witnessed real firing
    assert {b.reason for b in result.value.reachability.boundary} == {"max_tokens"}


def test_state_bound_and_oversized_initial_are_explicit():
    one = reachability(chain(), ReachabilitySpec(1, 1))
    assert one.status is ComputeStatus.PARTIAL
    assert one.value.final_state is None
    assert one.value.boundary[0].reason == "max_states"
    model = net(("p",), (), (), (("p", 2),), ())
    oversized = reachability(model, ReachabilitySpec(2, 1))
    assert not oversized.value.initial_admitted
    assert oversized.value.markings == ()
    assert oversized.issues[0].code == "initial_exceeds_max_tokens"


def test_partial_graph_preserves_concrete_deadlock_refutation():
    model = net(
        ("i", "q", "p", "o"),
        (
            ("dead", None),
            ("live", None),
            ("grow", None),
            ("end", "E"),
            ("blocked", "B"),
        ),
        (
            ("i", "dead"),
            ("dead", "q"),
            ("q", "blocked", 2),
            ("blocked", "o"),
            ("i", "live"),
            ("live", "p"),
            ("p", "grow"),
            ("grow", "p", 2),
            ("p", "end"),
            ("end", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    result = check_soundness(model, ReachabilitySpec(10, 1))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.sound is False and result.value.option_to_complete is False
    assert result.value.deadlock_states
    assert result.value.dead_transition_ids == ()
    assert "blocked" in result.value.unobserved_transition_ids


@pytest.mark.parametrize("extra_arcs", [(("o", "a"),), (("a", "i"),)])
def test_source_incoming_or_sink_outgoing_fail_workflow_structure(extra_arcs):
    model = net(
        ("i", "o"),
        (("a", "A"),),
        (("i", "a"), ("a", "o")) + extra_arcs,
        (("i", 1),),
        (("o", 1),),
    )
    assert not check_workflow_net(model).value.graph_is_workflow_net


def test_disconnected_nodes_fail_workflow_structure():
    model = net(
        ("i", "o", "isolate"),
        (("a", "A"),),
        (("i", "a"), ("a", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    report = check_workflow_net(model).value
    assert not report.graph_is_workflow_net
    assert len(report.source_places) == 2


def test_empty_net_and_isolated_accepting_place_have_explicit_results():
    empty = net((), (), (), (), ())
    assert not check_soundness(empty).value.sound
    assert reachability(empty).value.final_state == 0
    assert model_complexity(empty).value.arc_degree_simplicity == 1
    assert model_complexity(empty).value.extended_cyclomatic == 0
    single = net(("p",), (), (), (("p", 1),), (("p", 1),))
    assert check_soundness(single).value.sound


def test_complexity_simple_chain_and_duplicate_edges():
    model = chain()
    stats = model_complexity(model).value
    assert stats.mean_arc_degree == pytest.approx(4 / 3)
    assert stats.extended_cardoso == 1
    assert stats.extended_cyclomatic == 1
    assert stats.reachability_scc_count == 2
    duplicate = net(
        ("i", "o"),
        (("a", "A"), ("b", "B")),
        (("i", "a"), ("a", "o"), ("i", "b"), ("b", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    value = model_complexity(duplicate).value
    assert value.extended_cardoso == 1  # same postset, distinct activities ignored
    assert value.reachability_distinct_state_edges == 1  # distinct state pairs
    assert value.extended_cyclomatic == 1


def test_cyclomatic_requires_complete_reachability():
    result = model_complexity(
        chain(), ComplexitySpec(reachability=ReachabilitySpec(1, 1))
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.extended_cyclomatic is None
    assert result.value.extended_cardoso == 1


def test_scc_cyclomatic_loop_formula():
    model = net(
        ("p", "o"),
        (("l", None), ("e", "E")),
        (("p", "l"), ("l", "p"), ("p", "e"), ("e", "o")),
        (("p", 1),),
        (("o", 1),),
    )
    report = model_complexity(model).value
    assert report.extended_cyclomatic == 2  # 2 edges - 2 states + 2 SCCs


def test_weighted_arcs_do_not_inflate_arc_degree_or_cardoso():
    model = net(
        ("i", "o"),
        (("a", "A"),),
        (("i", "a", 2), ("a", "o", 2)),
        (("i", 2),),
        (("o", 2),),
    )
    value = model_complexity(model).value
    assert value.arc_count == 2 and value.total_arc_weight == 4
    assert value.mean_arc_degree == pytest.approx(4 / 3)
    assert value.extended_cardoso == 1


def test_silent_and_duplicate_reductions_preserve_visible_language():
    model = net(
        ("i", "o"),
        (("tau", None), ("a", "A"), ("b", "A")),
        (("i", "tau"), ("tau", "i"), ("i", "a"), ("a", "o"), ("i", "b"), ("b", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    reduced = reduce_model(model).value
    assert {step.rule for step in reduced.steps} == {
        "silent_identity",
        "duplicate_transition",
    }
    assert len(reduced.model.transitions) == 1
    assert accepted_words(model) == accepted_words(reduced.model) == {("A",)}
    assert reduced.original_model_digest == model_digest(model)
    assert reduced.reduced_model_digest == model_digest(reduced.model)
    assert compare_models(model, reduced.model).value.equivalent is True


def test_duplicate_place_reduction_requires_equal_markings_and_incidence():
    model = net(
        ("i", "p", "q", "o"),
        (("s", "S"), ("j", "J")),
        (
            ("i", "s"),
            ("s", "p", 2),
            ("s", "q", 2),
            ("p", "j", 2),
            ("q", "j", 2),
            ("j", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    result = reduce_model(model, ReductionSpec(("duplicate_place",))).value
    assert len(result.steps) == 1 and result.steps[0].removed_node == "q"
    assert result.steps[0].retained_node == "p"
    assert accepted_words(model) == accepted_words(result.model) == {("S", "J")}
    unequal_final = PetriNet(
        model.places,
        model.transitions,
        model.arcs,
        model.initial_marking,
        Marking((("o", 1), ("q", 1))),
    )
    assert (
        reduce_model(unequal_final, ReductionSpec(("duplicate_place",))).value.steps
        == ()
    )


def test_nonidentity_silent_step_and_different_labels_are_not_removed():
    model = net(
        ("i", "o"),
        (("tau", None), ("a", "A"), ("b", "B")),
        (("i", "tau"), ("tau", "o"), ("i", "a"), ("a", "o"), ("i", "b"), ("b", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    assert reduce_model(model).value.steps == ()
    assert reduce_model(model, ReductionSpec(())).value.model == model


def test_decomposition_retains_isolates_and_shuffle_components():
    a, b = chain("A", "a"), chain("B", "b")
    combined = PetriNet(
        a.places + b.places + (Place("isolated"),),
        a.transitions + b.transitions,
        a.arcs + b.arcs,
        Marking(a.initial_marking.tokens + b.initial_marking.tokens),
        Marking(a.final_marking.tokens + b.final_marking.tokens),
    )
    report = decompose_model(combined).value
    assert len(report.components) == 3
    assert report.composition == "independent_shuffle_product"
    assert ("isolated",) in report.component_node_ids
    assert accepted_words(combined) == {("A", "B"), ("B", "A")}
    assert sorted(len(component.transitions) for component in report.components) == [
        0,
        1,
        1,
    ]


def test_language_equivalence_ignores_node_names_and_silent_steps():
    left = chain()
    right = net(
        ("p", "m", "f"),
        (("x", None), ("y", "A")),
        (("p", "x"), ("x", "m"), ("m", "y"), ("y", "f")),
        (("p", 1),),
        (("f", 1),),
    )
    result = compare_models(left, right)
    assert result.value.equivalent is True
    assert result.value.similarity is None
    assert result.spec.other_model_digest == model_digest(right)
    assert result.source_digest == model_digest(left)
    assert result.computation_id != compare_models(left, chain("B")).computation_id


def test_language_comparison_returns_executable_distinguishing_word():
    report = compare_models(chain("A"), chain("B")).value
    assert report.equivalent is False
    assert report.distinguishing_trace == ("A",)
    assert report.accepted_by == "left"
    assert report.distinguishing_trace in accepted_words(chain("A"))
    assert report.distinguishing_trace not in accepted_words(chain("B"))


def test_empty_word_distinguishes_models():
    empty = net((), (), (), (), ())
    result = compare_models(empty, chain()).value
    assert result.equivalent is False
    assert result.distinguishing_trace == () and result.accepted_by == "left"


def test_language_equivalence_handles_infinite_visible_language():
    left = net(
        ("p",), (("a", "A"),), (("p", "a"), ("a", "p")), (("p", 1),), (("p", 1),)
    )
    right = net(
        ("q",),
        (("a1", "A"), ("a2", "A"), ("s", None)),
        (("q", "a1"), ("a1", "q"), ("q", "a2"), ("a2", "q"), ("q", "s"), ("s", "q")),
        (("q", 1),),
        (("q", 1),),
    )
    assert compare_models(left, right).value.equivalent is True


def test_duplicate_label_nondeterminism_is_not_dropped():
    left = net(
        ("i", "p", "q", "o"),
        (("a1", "A"), ("a2", "A"), ("b", "B"), ("c", "C")),
        (
            ("i", "a1"),
            ("a1", "p"),
            ("i", "a2"),
            ("a2", "q"),
            ("p", "b"),
            ("b", "o"),
            ("q", "c"),
            ("c", "o"),
        ),
        (("i", 1),),
        (("o", 1),),
    )
    right = net(
        ("i", "p", "o"),
        (("a", "A"), ("b", "B")),
        (("i", "a"), ("a", "p"), ("p", "b"), ("b", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    report = compare_models(left, right).value
    assert report.distinguishing_trace == ("A", "C") and report.accepted_by == "left"


def test_comparison_limits_are_unknown_not_equivalent_or_unequal():
    for spec in (
        ModelComparisonSpec(max_product_states=1),
        ModelComparisonSpec(reachability=ReachabilitySpec(1, 1)),
    ):
        result = compare_models(chain(), chain(), spec)
        assert result.status is ComputeStatus.PARTIAL
        assert result.value.equivalent is None and not result.value.complete


def test_label_and_structural_scores_do_not_assert_behavioral_equivalence():
    a, renamed = chain(), chain(prefix="x")
    label = compare_models(a, renamed, ModelComparisonSpec("label_set")).value
    structure = compare_models(
        a, renamed, ModelComparisonSpec("identity_structure")
    ).value
    assert label.similarity == (1, 1) and label.equivalent is None
    assert structure.similarity == (0, 1) and structure.equivalent is None
    assert compare_models(
        a, a, ModelComparisonSpec("identity_structure")
    ).value.similarity == (1, 1)
    assert compare_models(
        a, chain("B"), ModelComparisonSpec("label_set")
    ).value.similarity == (0, 1)
    empty = net((), (), (), (), ())
    assert compare_models(
        empty, empty, ModelComparisonSpec("label_set")
    ).value.similarity == (1, 1)


@pytest.mark.parametrize("seed", range(12))
def test_random_token_conserving_nets_match_independent_reachability_oracle(seed):
    rng = random.Random(seed)
    places = tuple(f"p{i}" for i in range(4))
    transitions = tuple((f"t{i}", None if i % 2 else f"A{i}") for i in range(6))
    arcs = []
    for tid, _ in transitions:
        source, target = rng.choice(places), rng.choice(places)
        arcs.extend(((source, tid), (tid, target)))
    model = net(places, transitions, tuple(arcs), (("p0", 2),), (("p3", 2),))
    expected, expected_edges, place_ids = independent_graph(model)
    result = reachability(model).value
    actual = {
        tuple(dict(m.tokens).get(p, 0) for p in place_ids) for m in result.markings
    }
    assert result.complete and actual == expected
    vectors = [
        tuple(dict(m.tokens).get(p, 0) for p in place_ids) for m in result.markings
    ]
    assert {
        (vectors[e.source], e.transition_id, vectors[e.target]) for e in result.edges
    } == expected_edges
    # Independently count SCCs by mutual reachability equivalence.
    relation = {(source, target) for source, _, target in expected_edges} | {
        (state, state) for state in expected
    }
    changed = True
    while changed:
        extended = relation | {
            (a, c) for a, b in relation for bb, c in relation if b == bb
        }
        changed = extended != relation
        relation = extended
    groups = {
        frozenset(
            other
            for other in expected
            if (state, other) in relation and (other, state) in relation
        )
        for state in expected
    }
    assert model_complexity(model).value.reachability_scc_count == len(groups)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_reachability_caps_are_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        ReachabilitySpec(max_states=value)
    with pytest.raises((TypeError, ValueError)):
        ReachabilitySpec(max_tokens=value)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, "2"])
def test_invalid_complexity_baseline_is_rejected(value):
    with pytest.raises((TypeError, ValueError)):
        ComplexitySpec(k=value)


def test_unsupported_profiles_and_wrong_inputs_raise_instead_of_fallback():
    with pytest.raises(ValueError):
        ReductionSpec(("arbitrary_implicit_place",))
    with pytest.raises(ValueError):
        ModelComparisonSpec("embedding")
    with pytest.raises(TypeError):
        reachability("model")
    with pytest.raises(TypeError):
        check_soundness(chain(), "spec")


def test_algebra_wrappers_retain_exact_values_and_model_identity():
    model = chain()
    matrix = model_incidence(model)
    assert matrix.value.output_minus_input == ((-1,), (1,))
    places = model_invariants(model)
    assert places.value.vectors == ((1, 1),)
    transitions = model_invariants(model, InvariantsSpec("transition"))
    assert transitions.value.vectors == ()
    bound = marking_equation_bound(model)
    assert bound.value.objective == (1, 1)
    assert bound.value.reachability_proven is False
    for result in (matrix, places, transitions, bound):
        assert result.status is ComputeStatus.COMPUTED
        assert result.source_digest == model_digest(model)
        assert result.operator_id.startswith("pix.case_centric.")


def test_marking_equation_unknown_and_infeasible_are_not_conflated():
    model = net(
        ("i", "o"),
        (("a", "A"), ("b", "B")),
        (("i", "a"), ("a", "o"), ("i", "b"), ("b", "o")),
        (("i", 1),),
        (("o", 1),),
    )
    capped = marking_equation_bound(model, MarkingEquationSpec(max_bases=1))
    assert capped.status is ComputeStatus.PARTIAL
    assert capped.value.status == "unknown" and capped.value.objective is None
    impossible = marking_equation_bound(
        model, MarkingEquationSpec(target=Marking((("o", 2),)))
    )
    assert impossible.status is ComputeStatus.COMPUTED
    assert (
        impossible.value.status == "infeasible" and impossible.value.objective is None
    )


def test_marking_equation_costs_and_markings_change_request_identity():
    model = chain()
    standard = marking_equation_bound(model)
    weighted = marking_equation_bound(
        model, MarkingEquationSpec(transition_costs=(("a", (3, 2)),))
    )
    assert weighted.value.objective == (3, 2)
    assert weighted.computation_id != standard.computation_id
    zero = marking_equation_bound(
        model, MarkingEquationSpec(target=model.initial_marking)
    )
    assert zero.value.objective == (0, 1)
    assert zero.computation_id != standard.computation_id
    normalized = MarkingEquationSpec(transition_costs=(("a", (6, 4)),))
    assert normalized.transition_costs == (("a", (3, 2)),)


@pytest.mark.parametrize(
    "costs",
    [
        (("a", (-1, 1)),),
        (("a", (1, 0)),),
        (("a", (True, 1)),),
        (("a", 0.5),),
        (("a", (1, 1)), ("a", (2, 1))),
        (("", (1, 1)),),
    ],
)
def test_marking_equation_contract_rejects_invalid_costs(costs):
    with pytest.raises((TypeError, ValueError)):
        MarkingEquationSpec(transition_costs=costs)


def test_marking_equation_rejects_costs_for_missing_transition():
    with pytest.raises(ValueError, match="unknown transition"):
        marking_equation_bound(
            chain(), MarkingEquationSpec(transition_costs=(("missing", (1, 1)),))
        )


def test_marking_equation_feasibility_does_not_assert_enabled_firing_order():
    # Both transitions need a token in q to enable; q starts and ends empty.
    model = net(
        ("p", "q", "r"),
        (("a", "A"), ("b", "B")),
        (("p", "a"), ("q", "a"), ("a", "r"), ("a", "q"), ("q", "b"), ("b", "q")),
        (("p", 1),),
        (("r", 1),),
    )
    assert marking_equation_bound(model).value.status == "optimal"
    assert marking_equation_bound(model).value.reachability_proven is False
    assert reachability(model).value.final_state is None


def test_registered_analysis_results_roundtrip():
    from pix.results import result_from_json, result_json_bytes

    model = chain()
    results = (
        reachability(model),
        check_workflow_net(model),
        check_soundness(model),
        model_complexity(model),
        reduce_model(model),
        decompose_model(model),
        compare_models(model, model),
        model_incidence(model),
        model_invariants(model),
        marking_equation_bound(model),
        reachability(model, ReachabilitySpec(1, 1)),
        compare_models(model, model, ModelComparisonSpec(max_product_states=1)),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result
