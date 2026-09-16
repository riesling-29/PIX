"""Tree DP checked by independently enumerated tree languages and edit tables."""

from dataclasses import replace
from itertools import product

import pytest

from pix.case_centric.tree_alignment import TreeAlignmentSpec, align_process_tree_dp
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces


def leaf(label):
    return ProcessTree("tau") if label is None else ProcessTree("activity", label)


def node(operator, *children):
    return ProcessTree(operator, children=children)


def log(*words):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    CaseEvent(
                        f"e{i}_{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(word)
                ),
            )
            for i, word in enumerate(words)
        )
    )


def shuffles(left, right):
    if not left:
        return {right}
    if not right:
        return {left}
    return {(left[0],) + word for word in shuffles(left[1:], right)} | {
        (right[0],) + word for word in shuffles(left, right[1:])
    }


def language(tree, rounds, path=()):
    # Direct syntax semantics, independently of the alignment recurrences.
    if tree.operator in ("activity", "tau"):
        return {((path, tree.activity),)}
    child_languages = [
        language(child, rounds, path + (i,)) for i, child in enumerate(tree.children)
    ]
    if tree.operator == "xor":
        return set().union(*child_languages)
    if tree.operator == "loop":
        do, redo = child_languages
        result = set(do)
        frontier = set(do)
        for _ in range(rounds):
            frontier = {
                left + middle + right
                for left in frontier
                for middle in redo
                for right in do
            }
            result.update(frontier)
        return result
    frontier = {()}
    for child_language in child_languages:
        if tree.operator == "sequence":
            frontier = {left + right for left in frontier for right in child_language}
        else:
            frontier = set().union(
                *(
                    shuffles(left, right)
                    for left in frontier
                    for right in child_language
                )
            )
    return frontier


def distance(word, model, spec):
    # Weighted word-table oracle; explicit tau tokens must be model-only moves.
    table = [[0] * (len(model) + 1) for _ in range(len(word) + 1)]
    for i in range(len(word) + 1):
        table[i][0] = i * spec.log_move_cost
    for j, (_, label) in enumerate(model, 1):
        table[0][j] = table[0][j - 1] + (
            spec.silent_move_cost if label is None else spec.model_move_cost
        )
    for i, activity in enumerate(word, 1):
        for j, (_, label) in enumerate(model, 1):
            options = [
                table[i - 1][j] + spec.log_move_cost,
                table[i][j - 1]
                + (spec.silent_move_cost if label is None else spec.model_move_cost),
            ]
            if label == activity:
                options.append(table[i - 1][j - 1] + spec.synchronous_move_cost)
            table[i][j] = min(options)
    return table[-1][-1]


TREES = (
    leaf("A"),
    leaf(None),
    node("sequence", leaf("A"), leaf("B"), leaf("A")),
    node("xor", leaf("A"), leaf("B"), leaf(None)),
    node("parallel", leaf("A"), leaf("B")),
    node("parallel", node("sequence", leaf("A"), leaf("B")), leaf("A")),
    node("loop", leaf("A"), leaf("B")),
    node("loop", leaf("A"), leaf(None)),
    node("loop", leaf(None), leaf("B")),
    node("loop", leaf(None), leaf(None)),
)


@pytest.mark.parametrize("tree", TREES)
@pytest.mark.parametrize(
    "spec",
    (
        TreeAlignmentSpec(),
        TreeAlignmentSpec(
            log_move_cost=2,
            model_move_cost=3,
            synchronous_move_cost=1,
            silent_move_cost=2,
        ),
        TreeAlignmentSpec(log_move_cost=0, model_move_cost=0, synchronous_move_cost=3),
    ),
)
def test_direct_dp_matches_language_enumeration_and_weighted_edit_oracle(tree, spec):
    words = tuple(
        word for length in range(3) for word in product(("A", "B"), repeat=length)
    )
    result = align_process_tree_dp(log(*words), tree, spec)
    assert result.status is ComputeStatus.COMPUTED
    for word, actual in zip(words, result.value.traces):
        accepted = language(tree, len(word))
        expected = min(distance(word, model_word, spec) for model_word in accepted)
        assert actual.cost == expected
        assert (
            tuple(
                move.activity for move in actual.moves if move.event_index is not None
            )
            == word
        )
        assert tuple(
            move.event_index for move in actual.moves if move.event_index is not None
        ) == tuple(range(len(word)))
        witness = tuple(
            (move.node_path, move.activity)
            for move in actual.moves
            if move.kind != "log"
        )
        assert witness in accepted
        assert sum(move.cost for move in actual.moves) == actual.cost


def test_parallel_child_alignment_recomposes_real_interleaving():
    tree = node(
        "parallel",
        node("sequence", leaf("A"), leaf("B")),
        node("sequence", leaf("C"), leaf("D")),
    )
    value = align_process_tree_dp(log("ACBD", "ABCD", "CABD", "DCBA"), tree).value
    assert tuple(trace.cost for trace in value.traces[:3]) == (0, 0, 0)
    assert value.traces[3].cost == 4


def test_loop_repeat_count_is_not_a_fixed_language_truncation():
    tree = node("loop", leaf("A"), leaf("B"))
    value = align_process_tree_dp(log("ABABABABA"), tree).value
    assert value.traces[0].cost == 0
    assert value.traces[0].model_word == tuple("ABABABABA")


def test_nested_loop_and_parallel_are_compositional():
    tree = node("loop", node("parallel", leaf("A"), leaf("B")), leaf("C"))
    value = align_process_tree_dp(log("BACAB", "ABCBACBA"), tree).value
    assert tuple(trace.cost for trace in value.traces) == (0, 0)


def test_nullable_nested_loops_terminate_without_unrolling_epsilon_cycles():
    tree = node("loop", node("loop", leaf(None), leaf(None)), leaf("A"))
    value = align_process_tree_dp(log("", "A", "AAA"), tree).value
    assert tuple(trace.cost for trace in value.traces) == (0, 0, 0)


@pytest.mark.parametrize(
    "spec", (TreeAlignmentSpec(max_candidates=1), TreeAlignmentSpec(max_subproblems=1))
)
def test_budget_limit_never_labels_a_trace_unfit_or_optimal(spec):
    result = align_process_tree_dp(
        log("AB"), node("parallel", leaf("A"), leaf("B")), spec
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.traces[0].status == "search_limit"
    assert result.value.traces[0].cost is None
    assert not result.value.traces[0].moves
    assert result.value.total_cost is None


def test_same_length_and_boundary_labels_do_not_collide_in_memoization():
    tree = node(
        "parallel",
        node("sequence", leaf("A"), leaf("B"), leaf("A")),
        node("sequence", leaf("B"), leaf("A"), leaf("B")),
    )
    words = ("ABAABB", "ABABAB", "AAABBB")
    accepted = language(tree, 0)
    value = align_process_tree_dp(log(*words), tree).value
    assert tuple(trace.cost for trace in value.traces) == tuple(
        min(distance(word, model, TreeAlignmentSpec()) for model in accepted)
        for word in words
    )


def test_empty_log_and_empty_trace_and_model_identity():
    tree = leaf("A")
    empty = align_process_tree_dp(log(), tree)
    assert empty.value.total_cost == 0
    assert empty.value.requested_count == 0
    one = align_process_tree_dp(log(""), tree)
    assert one.value.traces[0].cost == 1
    assert one.spec.model_digest == one.value.model_digest
    other = align_process_tree_dp(log(""), leaf("B"))
    assert one.computation_id != other.computation_id


def test_already_projected_trace_identity_and_failed_status_are_retained():
    source = case_traces(log("A"))
    result = align_process_tree_dp(source, leaf("A"))
    assert result.parent_computation_ids == (source.computation_id,)
    invalid = replace(source, status=ComputeStatus.INVALID_INPUT, value=None)
    result = align_process_tree_dp(invalid, leaf("A"))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


def test_explicit_depth_limit_is_checked_before_recursive_digest():
    tree = node("sequence", leaf("A"), node("xor", leaf("B"), leaf("C")))
    with pytest.raises(ValueError, match="max_tree_depth"):
        align_process_tree_dp(log("AB"), tree, TreeAlignmentSpec(max_tree_depth=1))


def test_shared_subtree_expansion_is_bounded_before_digest():
    tree = leaf("A")
    for _ in range(20):
        tree = node("parallel", tree, tree)
    with pytest.raises(ValueError, match="max_tree_nodes"):
        align_process_tree_dp(log("A"), tree, TreeAlignmentSpec(max_tree_nodes=100))


@pytest.mark.parametrize("limited", (False, True))
def test_tree_alignment_typed_persistence_round_trip(monkeypatch, limited):
    import pix.results as persistence
    from pix.case_centric.tree_alignment import RESULT_SCHEMAS

    original = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: {**original(), **RESULT_SCHEMAS}
    )
    spec = TreeAlignmentSpec(max_candidates=1) if limited else TreeAlignmentSpec()
    result = align_process_tree_dp(
        log("BA"), node("parallel", leaf("A"), leaf("B")), spec
    )
    assert persistence.result_from_json(persistence.result_json_bytes(result)) == result
