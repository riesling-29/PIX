"""Hand-defined languages and exhaustive causal-pair oracles for native Alpha.

The accepting-language oracle applies P/T arc arithmetic directly; it uses no
PIX replay, alignment, firing, or discovery code to judge acceptance.
"""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from itertools import combinations, product

import pytest

from pix.case_centric.alpha import (
    AlphaSpec,
    _maximal_pairs,
    discover_alpha,
    discover_alpha_plus,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(case),
                tuple(
                    CaseEvent(
                        f"{case}:{index}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for index, activity in enumerate(word)
                ),
            )
            for case, word in enumerate(words)
        )
    )


def language(net, max_length=6, state_limit=50_000):
    """Finite visible-word enumeration using only independent marking algebra."""
    initial = tuple(net.initial_marking.tokens)
    final = tuple(net.final_marking.tokens)
    pending = deque([(initial, ())])
    seen = {(initial, ())}
    accepted = set()
    while pending:
        tokens, word = pending.popleft()
        if tokens == final:
            accepted.add(word)
        current = Counter(dict(tokens))
        for transition in net.transitions:
            if transition.activity is not None and len(word) == max_length:
                continue
            incoming = Counter(
                {a.source: a.weight for a in net.arcs if a.target == transition.id}
            )
            if any(current[p] < n for p, n in incoming.items()):
                continue
            outgoing = Counter(
                {a.target: a.weight for a in net.arcs if a.source == transition.id}
            )
            after = current.copy()
            after.subtract(incoming)
            after.update(outgoing)
            new_tokens = tuple(sorted((p, n) for p, n in after.items() if n))
            new_word = (
                word if transition.activity is None else (*word, transition.activity)
            )
            state = (new_tokens, new_word)
            if state not in seen:
                seen.add(state)
                assert len(seen) <= state_limit, (
                    "independent oracle resource bound reached"
                )
                pending.append(state)
    return accepted


@pytest.mark.parametrize("words", [("abcd",), ("abd", "acd"), ("abcd", "acbd")])
@pytest.mark.parametrize("variant", ["classic", "plus"])
def test_sequence_choice_parallel_have_exact_hand_languages(words, variant):
    result = discover_alpha(log(*words), AlphaSpec(variant=variant))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model) == {tuple(w) for w in words}


def test_choice_places_are_maximal_not_duplicate_singleton_places():
    result = discover_alpha(log("abd", "acd"))
    net = result.value.model
    label = {t.id: t.activity for t in net.transitions}
    pairs = {
        (
            frozenset(label[t] for t in p.input_transition_ids),
            frozenset(label[t] for t in p.output_transition_ids),
        )
        for p in result.value.maximal_places
    }
    assert pairs == {
        (frozenset("a"), frozenset("bc")),
        (frozenset("bc"), frozenset("d")),
    }


def test_alpha_plus_one_loop_reuses_an_existing_place():
    result = discover_alpha_plus(log("abbc", "ac"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.length_one_activities == ("b",)
    assert language(result.value.model, max_length=6) == {
        tuple("a" + "b" * repetitions + "c") for repetitions in range(5)
    }
    b = next(t.id for t in result.value.model.transitions if t.activity == "b")
    incoming = {a.source for a in result.value.model.arcs if a.target == b}
    outgoing = {a.target for a in result.value.model.arcs if a.source == b}
    assert len(incoming) == 1
    assert incoming == outgoing


def test_alpha_plus_two_loop_distinguished_from_concurrency():
    result = discover_alpha_plus(log("a", "ababa"))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.length_two_pairs == (("a", "b"),)
    assert language(result.value.model, max_length=7) == {
        tuple("a" + "ba" * repetitions) for repetitions in range(4)
    }
    assert not result.value.parallel_pairs


def test_length_one_at_boundary_and_epsilon_use_collision_safe_silent_nodes():
    result = discover_alpha_plus(log(("artificial_start", "artificial_start"), ()))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model, max_length=3) == {
        ("artificial_start",) * i for i in range(4)
    }
    assert len({t.id for t in result.value.model.transitions}) == 3
    assert sum(t.activity is None for t in result.value.model.transitions) == 2


def test_formal_and_reference_attachment_policy_are_not_conflated():
    raw = log("abbc", "ad")
    exact = discover_alpha_plus(raw)
    assert exact.status is ComputeStatus.UNAVAILABLE
    assert exact.value is None
    assert "alpha_plus_unresolved_loop_context" in {i.code for i in exact.issues}
    containing = discover_alpha_plus(
        raw, AlphaSpec(variant="plus", loop_attachment="containing")
    )
    assert containing.status is ComputeStatus.COMPUTED
    assert ("a", "b", "d") in language(containing.value.model, 3)


def test_classic_short_loops_are_not_claimed_as_reconstructed():
    result = discover_alpha(log("abbc"))
    assert result.status is ComputeStatus.COMPUTED
    assert "classic_short_loop_limitation" in {i.code for i in result.issues}
    assert "rediscoverability_not_certified" in {i.code for i in result.issues}


def test_one_sided_two_loop_evidence_is_reported():
    result = discover_alpha_plus(log("aba"))
    assert not result.value.length_two_pairs
    assert "one_sided_short_loop_evidence" in {i.code for i in result.issues}


def test_empty_input_and_unsupported_epsilon_are_explicit():
    assert discover_alpha(log()).status is ComputeStatus.UNAVAILABLE
    assert discover_alpha(log(())).status is ComputeStatus.UNAVAILABLE
    plus = discover_alpha_plus(log(()))
    assert plus.status is ComputeStatus.COMPUTED
    assert language(plus.value.model) == {()}


@pytest.mark.parametrize(
    "spec",
    [
        AlphaSpec(max_candidates=1),
        AlphaSpec(max_checks=1),
        AlphaSpec(max_activities=1),
    ],
)
def test_limits_never_return_a_truncated_accepting_net(spec):
    result = discover_alpha(log("abcd", "acbd"), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(i.code in ("candidate_limit", "activity_limit") for i in result.issues)


def test_source_order_and_projection_provenance_are_retained():
    raw = log("ba")
    traces = case_traces(raw)
    direct = discover_alpha(raw)
    derived = discover_alpha(traces)
    assert direct == derived
    assert derived.source_digest == traces.source_digest
    assert derived.parent_computation_ids == (traces.computation_id,)
    assert language(derived.value.model) == {("b", "a")}
    assert "unknown_timestamp" in {i.code for i in derived.issues}
    with pytest.raises(FrozenInstanceError):
        derived.value.variant = "mutated"


def test_multiplicity_changes_identity_but_not_discovered_structure():
    once = discover_alpha(log("abc"))
    twice = discover_alpha(log("abc", "abc"))
    assert once.value == twice.value
    assert once.computation_id != twice.computation_id


def test_invalid_and_partial_trace_inputs_are_not_upgraded_to_complete():
    unavailable = case_traces(CaseLog((CaseTrace("x", (CaseEvent("e"),)),)))
    failed = discover_alpha(unavailable)
    assert failed.status is ComputeStatus.UNAVAILABLE
    assert failed.value is None
    parent = case_traces(log("ab"))
    partial = replace(parent, status=ComputeStatus.PARTIAL)
    assert discover_alpha(partial).status is ComputeStatus.PARTIAL


def test_explicit_activity_mapping_is_part_of_parent_identity():
    raw = CaseLog(
        (CaseTrace("x", (CaseEvent("e", (CaseAttribute("step", "string", "a"),)),)),)
    )
    result = discover_alpha(raw, trace_spec=CaseTraceSpec(activity_key="step"))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model) == {("a",)}
    with pytest.raises(ValueError):
        discover_alpha(
            case_traces(log("a")), trace_spec=CaseTraceSpec(activity_key="step")
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"variant": "im"},
        {"loop_attachment": "heuristic"},
        {"max_candidates": True},
        {"max_checks": 0},
        {"max_activities": -1},
        {"loop_attachment": "containing"},
    ],
)
def test_invalid_specs_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        AlphaSpec(**kwargs)


def test_all_three_activity_relations_match_exhaustive_powerset_oracle():
    """512 directed relations, including self-loops; no miner expansion reused."""
    alphabet = (0, 1, 2)
    possible = tuple(product(alphabet, repeat=2))
    subsets = tuple(
        frozenset(group)
        for size in range(1, 4)
        for group in combinations(alphabet, size)
    )
    for mask in range(1 << len(possible)):
        follows = {pair for index, pair in enumerate(possible) if mask & (1 << index)}
        causal = {(a, b) for a, b in follows if (b, a) not in follows}
        valid = {
            (left, right)
            for left in subsets
            for right in subsets
            if all((a, b) in causal for a in left for b in right)
            and all(
                (a, b) not in follows and (b, a) not in follows
                for side in (left, right)
                for a in side
                for b in side
            )
        }
        maximal = {
            pair
            for pair in valid
            if not any(
                pair != other and pair[0] <= other[0] and pair[1] <= other[1]
                for other in valid
            )
        }
        actual, candidates, checks = _maximal_pairs(
            alphabet, follows, causal, AlphaSpec()
        )
        assert set(actual) == maximal, follows
        assert candidates == len(valid)
        assert checks <= AlphaSpec().max_checks
