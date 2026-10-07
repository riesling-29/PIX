"""Independent visible-language and transition-border checks."""

from collections import Counter, deque
from dataclasses import dataclass
from itertools import product

import pytest

from pix.case_centric.tree_bordered import (
    RESULT_SCHEMAS,
    TransitionBorderedSpec,
    tree_to_transition_bordered_petri_net,
)
from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeIssue, ComputeStatus


def activity(label):
    return ProcessTree("activity", label)


def operator(kind, *children):
    return ProcessTree(kind, children=tuple(children))


TAU = ProcessTree("tau")
A, B, C, D = map(activity, "ABCD")
convert = tree_to_transition_bordered_petri_net


def accepted(net, bound=4):
    """Finite word-bounded marking exploration, independent of PIX firing."""
    adjacency = {}
    for transition in net.transitions:
        adjacency[transition.id] = (
            {a.source: a.weight for a in net.arcs if a.target == transition.id},
            {a.target: a.weight for a in net.arcs if a.source == transition.id},
        )
    initial = (net.initial_marking.tokens, ())
    pending, seen, words = deque((initial,)), {initial}, set()
    while pending:
        marking, word = pending.popleft()
        if marking == net.final_marking.tokens:
            words.add(word)
        for transition in net.transitions:
            before, after = adjacency[transition.id]
            tokens = Counter(dict(marking))
            if any(tokens[p] < n for p, n in before.items()):
                continue
            next_word = word + (
                (transition.activity,) if transition.activity is not None else ()
            )
            if len(next_word) > bound:
                continue
            tokens.subtract(before)
            tokens.update(after)
            next_marking = tuple(sorted((p, n) for p, n in tokens.items() if n))
            state = (next_marking, next_word)
            if state not in seen:
                seen.add(state)
                pending.append(state)
        assert len(seen) < 50_000, "oracle budget exhausted; not a successful test"
    return words


def shuffles(left, right):
    if not left:
        return {right}
    if not right:
        return {left}
    return {(left[0],) + w for w in shuffles(left[1:], right)} | {
        (right[0],) + w for w in shuffles(left, right[1:])
    }


def denotation(tree, bound=4):
    if tree.operator == "tau":
        return {()}
    if tree.operator == "activity":
        return {(tree.activity,)}
    children = [denotation(child, bound) for child in tree.children]
    if tree.operator == "xor":
        return set.union(*children)
    if tree.operator == "loop":
        words = set(children[0])
        while True:
            extra = {
                x + y + z
                for x, y, z in product(words, children[1], children[0])
                if len(x) + len(y) + len(z) <= bound
            }
            if extra <= words:
                return words
            words.update(extra)
    words = {()}
    for language in children:
        words = {
            word
            for left, right in product(words, language)
            if len(left) + len(right) <= bound
            for word in (
                {left + right} if tree.operator == "sequence" else shuffles(left, right)
            )
        }
    return words


TREES = (
    TAU,
    A,
    operator("sequence", A, B),
    operator("xor", A, B),
    operator("parallel", A, B),
    operator("loop", A, B),
    operator("loop", A, TAU),
    operator("loop", TAU, B),
    operator("loop", TAU, TAU),
    operator("xor", A, A, TAU),
    operator("parallel", A, A, TAU),
    operator("sequence", TAU, A, TAU, B),
    operator("sequence", A, operator("parallel", B, C), D),
    operator("parallel", operator("xor", TAU, A), operator("loop", B, C)),
    operator("loop", operator("sequence", A, B), operator("xor", TAU, C)),
)


@pytest.mark.parametrize("tree", TREES)
def test_language_matches_independent_tree_denotation(tree):
    result = convert(tree)
    assert result.status == ComputeStatus.COMPUTED
    assert accepted(result.value.model) == denotation(tree)


@pytest.mark.parametrize(
    "tree, expected",
    [
        (operator("sequence", A, B), {("A", "B")}),
        (operator("parallel", A, B), {("A", "B"), ("B", "A")}),
        (operator("xor", A, B), {("A",), ("B",)}),
        (operator("loop", A, B), {("A",), ("A", "B", "A")}),
        (operator("loop", TAU, B), {(), ("B",), ("B", "B"), ("B", "B", "B")}),
        (operator("loop", A, TAU), {("A",), ("A", "A"), ("A", "A", "A")}),
        (operator("loop", TAU, TAU), {()}),
    ],
)
def test_hand_calculated_languages(tree, expected):
    assert accepted(convert(tree).value.model, 3) == expected


@pytest.mark.parametrize("tree", TREES)
def test_each_subtree_has_one_transition_entry_and_exit(tree):
    converted = convert(tree).value
    net = converted.model
    paths = {b.tree_path for b in converted.borders}
    expected = set()
    pending = [(tree, ())]
    while pending:
        node, path = pending.pop()
        expected.add(path)
        pending.extend((child, path + (i,)) for i, child in enumerate(node.children))
    assert paths == expected
    assert len(paths) == len(converted.borders)
    for border in converted.borders:
        descendants = {
            identity
            for row in converted.borders
            if row.tree_path[: len(border.tree_path)] == border.tree_path
            for identity in (row.entry_transition_id, row.exit_transition_id)
        }
        internal_places = {
            place.id
            for place in net.places
            if any(a.source in descendants and a.target == place.id for a in net.arcs)
            and any(a.source == place.id and a.target in descendants for a in net.arcs)
        }
        sources = {
            t
            for t in descendants
            if not any(a.source in internal_places and a.target == t for a in net.arcs)
        }
        sinks = {
            t
            for t in descendants
            if not any(a.source == t and a.target in internal_places for a in net.arcs)
        }
        assert sources == {border.entry_transition_id}
        assert sinks == {border.exit_transition_id}


@pytest.mark.parametrize(
    "kind, places, transitions, arcs",
    [
        ("sequence", 5, 4, 8),
        ("xor", 4, 4, 8),
        ("parallel", 6, 4, 10),
        ("loop", 4, 4, 8),
    ],
)
def test_transition_bordered_pattern_size_and_unit_incidence(
    kind, places, transitions, arcs
):
    model = convert(operator(kind, A, B)).value.model
    assert (len(model.places), len(model.transitions), len(model.arcs)) == (
        places,
        transitions,
        arcs,
    )
    assert all(arc.weight == 1 for arc in model.arcs)
    assert sum(t.activity is None for t in model.transitions) == 2


def test_repeated_labels_are_separate_transitions_and_tau_is_silent():
    converted = convert(operator("sequence", A, A, TAU)).value
    leaves = converted.borders[1:]
    ids = [row.entry_transition_id for row in leaves]
    assert len(set(ids)) == 3
    by_id = {t.id: t.activity for t in converted.model.transitions}
    assert [by_id[i] for i in ids] == ["A", "A", None]
    assert all(row.entry_transition_id == row.exit_transition_id for row in leaves)


@pytest.mark.parametrize(
    "parameter", ["max_tree_nodes", "max_depth", "max_net_nodes", "max_net_arcs"]
)
def test_limits_release_no_model(parameter):
    result = convert(
        operator("sequence", A, B), TransitionBorderedSpec(**{parameter: 1})
    )
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "tree_bordered_limit"


def test_exact_output_limits_and_deterministic_identity():
    tree = operator("parallel", A, B)
    exact = TransitionBorderedSpec(
        max_tree_nodes=3, max_depth=2, max_net_nodes=10, max_net_arcs=10
    )
    result = convert(tree, exact)
    assert result.status == ComputeStatus.COMPUTED
    assert convert(tree, exact) == result
    assert convert(tree, TransitionBorderedSpec(max_net_nodes=9)).value is None
    assert convert(tree, TransitionBorderedSpec(max_net_arcs=9)).value is None


def test_deep_input_limit_does_not_recurse_or_fabricate_source_identity():
    tree = A
    for _ in range(600):
        tree = operator("sequence", tree, B)
    result = convert(tree)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.source_digest is None
    assert result.spec.model_digest is None


def test_source_identity_matches_native_model_codec():
    from pix.models import model_document

    tree = operator("sequence", A, operator("parallel", B, C))
    result = convert(tree)
    assert result.source_digest == model_document(tree)["model_digest"]
    assert result.value.source_model_digest == result.source_digest


@pytest.mark.parametrize("status", [ComputeStatus.COMPUTED, ComputeStatus.PARTIAL])
def test_parent_provenance_and_coverage_are_retained(status):
    @dataclass(frozen=True)
    class Carrier:
        tree: ProcessTree

    issues = (
        (ComputeIssue("limited_log", "Input covers a subset"),)
        if status == ComputeStatus.PARTIAL
        else ()
    )
    parent = _derived_result(
        "test.tree", "test:source", TransitionBorderedSpec(), status, Carrier(A), issues
    )
    result = convert(parent)
    assert result.status == status
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)
    assert result.issues == issues


def test_failed_input_and_unreleased_partial_model():
    failed = _derived_result(
        "test.tree",
        "test:source",
        TransitionBorderedSpec(),
        ComputeStatus.INVALID_INPUT,
        None,
        (ComputeIssue("bad_tree", "Cannot produce a tree"),),
    )
    result = convert(failed)
    assert result.status == ComputeStatus.INVALID_INPUT
    assert result.issues == failed.issues
    assert result.parent_computation_ids == (failed.computation_id,)

    @dataclass(frozen=True)
    class Carrier:
        model: ProcessTree | None = None

    partial = _derived_result(
        "test.tree",
        "test:source",
        TransitionBorderedSpec(),
        ComputeStatus.PARTIAL,
        Carrier(),
        failed.issues,
    )
    result = convert(partial)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[-1].code == "tree_model_unavailable"
    assert result.parent_computation_ids == (partial.computation_id,)


def test_result_codec_roundtrip_preserves_model_and_border_witnesses(monkeypatch):
    from pix import results

    original = results._schemas
    monkeypatch.setattr(results, "_schemas", lambda: {**original(), **RESULT_SCHEMAS})
    result = convert(operator("loop", operator("parallel", A, A), TAU))
    assert results.result_from_json(results.result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "name", ["max_tree_nodes", "max_depth", "max_net_nodes", "max_net_arcs"]
)
@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_limits(name, value):
    with pytest.raises(ValueError):
        TransitionBorderedSpec(**{name: value})


def test_bad_input_contracts():
    with pytest.raises(TypeError):
        convert("A")
    with pytest.raises(TypeError):
        convert(A, {})
    with pytest.raises(ValueError):
        TransitionBorderedSpec(max_depth=49)
