"""POWL tests with an independent accepting-net word enumerator.

The oracle implements only weighted arc arithmetic and explicit expected
languages. It does not invoke PIX firing, discovery, alignment, or replay to
judge the returned net.
"""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from itertools import combinations, permutations

import pytest

from pix.case_centric.powl import (
    RESULT_SCHEMAS,
    POWLConversionSpec,
    POWLDiscoverySpec,
    POWLNode,
    POWLResourceLimit,
    discover_powl,
    powl_to_petri_net,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i),
                tuple(
                    CaseEvent(
                        f"{i}:{j}", (CaseAttribute("concept:name", "string", activity),)
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def language(net, max_length=6, state_limit=200_000):
    initial, final = net.initial_marking.tokens, net.final_marking.tokens
    pending = deque([(initial, ())])
    seen = {(initial, ())}
    accepted = set()
    transitions = tuple(
        (
            t.activity,
            Counter({a.source: a.weight for a in net.arcs if a.target == t.id}),
            Counter({a.target: a.weight for a in net.arcs if a.source == t.id}),
        )
        for t in net.transitions
    )
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        current = Counter(dict(marking))
        for activity, incoming, outgoing in transitions:
            if activity is not None and len(word) == max_length:
                continue
            if any(current[p] < count for p, count in incoming.items()):
                continue
            after = current.copy()
            after.subtract(incoming)
            after.update(outgoing)
            tokens = tuple(sorted((p, count) for p, count in after.items() if count))
            following = word if activity is None else (*word, activity)
            state = (tokens, following)
            if state not in seen:
                seen.add(state)
                assert len(seen) <= state_limit, "independent word oracle exhausted"
                pending.append(state)
    return accepted


def a(label):
    return POWLNode("activity", label)


def sequence(*labels):
    return POWLNode(
        "partial_order",
        children=tuple(a(x) for x in labels),
        order=tuple((i, i + 1) for i in range(len(labels) - 1)),
    )


def test_non_series_parallel_order_has_exact_topological_word_language():
    edges = ((0, 2), (0, 3), (1, 3))
    model = POWLNode("partial_order", children=tuple(a(x) for x in "abcd"), order=edges)
    expected = {
        word
        for word in permutations("abcd")
        if all(word.index("abcd"[i]) < word.index("abcd"[j]) for i, j in edges)
    }
    assert len(expected) == 5
    assert language(powl_to_petri_net(model), 4) == expected


@pytest.mark.parametrize("mask", range(8))
def test_all_three_node_forward_dags_match_independent_permutations(mask):
    possible = tuple(combinations(range(3), 2))
    edges = tuple(edge for i, edge in enumerate(possible) if mask & (1 << i))
    model = POWLNode("partial_order", children=tuple(a(x) for x in "abc"), order=edges)
    expected = {
        word
        for word in permutations("abc")
        if all(word.index("abc"[i]) < word.index("abc"[j]) for i, j in edges)
    }
    assert language(powl_to_petri_net(model), 3) == expected


def test_partial_order_children_can_interleave_inside_submodel():
    model = POWLNode("partial_order", children=(sequence("a", "b"), a("c")))
    assert language(powl_to_petri_net(model), 3) == {
        tuple(w) for w in ("abc", "acb", "cab")
    }


def test_precedence_waits_for_entire_predecessor_submodel():
    model = POWLNode(
        "partial_order", children=(sequence("a", "b"), a("c")), order=((0, 1),)
    )
    assert language(powl_to_petri_net(model), 3) == {tuple("abc")}


def test_xor_branch_is_exclusive_and_duplicate_labels_keep_occurrence_identity():
    model = POWLNode(
        "xor", children=(sequence("a", "b"), sequence("a", "c"), POWLNode("tau"))
    )
    net = powl_to_petri_net(model)
    assert sum(t.activity == "a" for t in net.transitions) == 2
    assert language(net, 3) == {(), ("a", "b"), ("a", "c")}


def test_loop_requires_do_first_and_after_each_redo():
    model = POWLNode(
        "loop", children=(POWLNode("xor", children=(a("a"), a("b"))), a("c"))
    )
    expected = {(x,) for x in "ab"}
    expected |= {(x, "c", y) for x in "ab" for y in "ab"}
    expected |= {(x, "c", y, "c", z) for x in "ab" for y in "ab" for z in "ab"}
    assert language(powl_to_petri_net(model), 5) == expected


def test_silent_loop_is_finite_state_and_does_not_invent_visible_words():
    model = POWLNode("loop", children=(POWLNode("tau"), POWLNode("tau")))
    assert language(powl_to_petri_net(model), 3) == {()}


def test_order_closure_is_canonical_and_contract_is_frozen():
    children = tuple(a(x) for x in "abc")
    first = POWLNode("partial_order", children=children, order=((0, 1), (1, 2)))
    second = POWLNode(
        "partial_order", children=children, order=((0, 2), (1, 2), (0, 1), (0, 1))
    )
    assert first == second
    assert first.order == ((0, 1), (0, 2), (1, 2))
    with pytest.raises(FrozenInstanceError):
        first.kind = "tau"


@pytest.mark.parametrize(
    "order", [((0, 0),), ((0, 1), (1, 0)), ((0, 2),), ((True, 1),), ((0,),), ([0, 1],)]
)
def test_invalid_partial_orders_are_rejected(order):
    with pytest.raises((ValueError, TypeError)):
        POWLNode("partial_order", children=(a("a"), a("b")), order=order)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "activity"},
        {"kind": "tau", "activity": "x"},
        {"kind": "activity", "activity": "x", "children": (a("y"),)},
        {"kind": "xor", "children": (a("x"),)},
        {"kind": "loop", "children": (a("x"),)},
        {"kind": "xor", "children": (a("x"), a("y")), "order": ((0, 1),)},
    ],
)
def test_malformed_operators_do_not_create_ambiguous_models(kwargs):
    with pytest.raises((TypeError, ValueError)):
        POWLNode(**kwargs)


@pytest.mark.parametrize(
    "spec",
    [
        POWLConversionSpec(max_model_nodes=2),
        POWLConversionSpec(max_depth=1),
        POWLConversionSpec(max_net_nodes=2),
        POWLConversionSpec(max_net_arcs=1),
    ],
)
def test_conversion_bound_raises_without_returning_incomplete_net(spec):
    with pytest.raises(POWLResourceLimit):
        powl_to_petri_net(sequence("a", "b"), spec)


def test_discovery_common_precedence_can_produce_non_block_order():
    edges = ((0, 2), (0, 3), (1, 3))
    words = tuple(
        word
        for word in permutations("abcd")
        if all(word.index("abcd"[i]) < word.index("abcd"[j]) for i, j in edges)
    )
    result = discover_powl(log(*words))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.model.kind == "partial_order"
    assert result.value.model.order == edges
    assert language(result.value.petri_net, 4) == set(words)
    assert result.value.branches[0].rule == "common_precedence"
    assert result.value.generalization_rules == (
        "linear_extensions_of_common_precedence",
    )


def test_common_precedence_admits_unobserved_linear_extensions_explicitly():
    result = discover_powl(log("abc", "cba"))
    assert result.value.model.order == ()
    assert language(result.value.petri_net, 3) == set(permutations("abc"))
    exact = discover_powl(
        log("abc", "cba"), POWLDiscoverySpec(variant="exact_variants")
    )
    assert language(exact.value.petri_net, 3) == {tuple("abc"), tuple("cba")}
    assert exact.value.generalization_rules == ()
    assert exact.computation_id != result.computation_id


def test_discovery_repetition_generalizes_positive_primitive_power():
    result = discover_powl(log("ab", "abab"))
    assert result.value.model.kind == "loop"
    assert language(result.value.petri_net, 6) == {tuple("ab" * i) for i in (1, 2, 3)}
    assert result.value.generalization_rules == ("positive_primitive_repetition",)
    assert result.value.branches[0].observed_variants == (tuple("ab"), tuple("abab"))
    disabled = discover_powl(
        log("ab", "abab"), POWLDiscoverySpec(infer_repetition=False)
    )
    assert language(disabled.value.petri_net, 6) == {tuple("ab"), tuple("abab")}


def test_repeated_root_can_have_repeated_labels_without_merging_them():
    result = discover_powl(log("abaaba"))
    assert language(result.value.petri_net, 9) == {tuple("aba" * n) for n in (1, 2, 3)}


def test_mixed_empty_concurrency_repeat_and_exact_branches_cover_observations():
    words = ("", "ab", "ba", "ccc", "xyx", "q")
    result = discover_powl(log(*words))
    accepted = language(result.value.petri_net, 4)
    assert {tuple(w) for w in words} <= accepted
    assert () in accepted
    assert ("c",) in accepted
    assert ("y", "x") not in accepted
    assert result.value.trace_count == len(words)
    assert result.value.variant_count == len(words)


@pytest.mark.parametrize("words", [("",), ("a",), ("aba", "abb", ""), ("abab", "ab")])
def test_exact_variant_profile_matches_finite_language(words):
    result = discover_powl(log(*words), POWLDiscoverySpec(variant="exact_variants"))
    assert language(result.value.petri_net, 6) == {tuple(w) for w in words}


def test_frequency_does_not_change_model_and_projection_identity_is_preserved():
    source = case_traces(log("ab", "ba", "ab"))
    result = discover_powl(source)
    assert result.value.model == discover_powl(log("ab", "ba")).value.model
    assert result.value.trace_count == 3
    assert result.value.variant_count == 2
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)
    partial = discover_powl(replace(source, status=ComputeStatus.PARTIAL))
    assert partial.status is ComputeStatus.PARTIAL


@pytest.mark.parametrize(
    "spec",
    [
        POWLDiscoverySpec(max_traces=1),
        POWLDiscoverySpec(max_events=3),
        POWLDiscoverySpec(max_order_checks=1),
        POWLDiscoverySpec(conversion=POWLConversionSpec(max_model_nodes=2)),
        POWLDiscoverySpec(conversion=POWLConversionSpec(max_net_nodes=4)),
        POWLDiscoverySpec(conversion=POWLConversionSpec(max_net_arcs=2)),
    ],
)
def test_discovery_limits_are_unavailable_not_partial_models(spec):
    result = discover_powl(log("ab", "ba"), spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any("limit" in issue.code for issue in result.issues)


def test_single_leaf_can_use_one_model_node_and_no_cases_is_unavailable():
    result = discover_powl(
        log("a"), POWLDiscoverySpec(conversion=POWLConversionSpec(max_model_nodes=1))
    )
    assert result.status is ComputeStatus.COMPUTED
    empty = discover_powl(log())
    assert empty.status is ComputeStatus.UNAVAILABLE
    assert empty.value is None


def test_small_primitive_can_be_discovered_from_long_repetition_under_model_bound():
    result = discover_powl(
        log("a" * 1000),
        POWLDiscoverySpec(conversion=POWLConversionSpec(max_model_nodes=3)),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.model_node_count == 3


def test_result_schema_supplies_serialization_kind_spec_and_payload():
    kind, spec_type, value_type = RESULT_SCHEMAS["pix.case_centric.discover_powl"]
    result = discover_powl(log("a"))
    assert kind == "powl_discovery"
    assert isinstance(result.spec, spec_type)
    assert isinstance(result.value, value_type)


@pytest.mark.parametrize(
    "spec",
    [
        POWLDiscoverySpec(),
        POWLDiscoverySpec(variant="exact_variants"),
        POWLDiscoverySpec(max_events=1),
    ],
)
def test_recursive_representation_and_unavailable_result_roundtrip(spec, monkeypatch):
    # Register only this module in the serialization unit test. The main
    # application allowlist is maintained separately by the integration owner.
    import pix.results as results

    monkeypatch.setattr(results, "_schemas", lambda: RESULT_SCHEMAS)
    result = discover_powl(log("", "ab", "ba", "ccc"), spec)
    encoded = results.result_json_bytes(result)
    decoded = results.result_from_json(encoded)
    assert decoded == result


def test_depth_limit_is_checked_before_recursive_conversion():
    model = a("x")
    for _ in range(128):
        model = POWLNode("loop", children=(model, POWLNode("tau")))
    with pytest.raises(POWLResourceLimit):
        powl_to_petri_net(model)


@pytest.mark.parametrize(
    "spec_type,kwargs",
    [
        (POWLConversionSpec, {"max_depth": 129}),
        (POWLConversionSpec, {"max_net_arcs": True}),
        (POWLDiscoverySpec, {"variant": "IM"}),
        (POWLDiscoverySpec, {"infer_repetition": 1}),
        (POWLDiscoverySpec, {"max_events": 0}),
    ],
)
def test_invalid_specs_are_rejected(spec_type, kwargs):
    with pytest.raises((TypeError, ValueError)):
        spec_type(**kwargs)
