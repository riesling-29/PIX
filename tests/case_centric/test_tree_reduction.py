"""Independent finite-language and edit-distance checks for native reductions."""

from dataclasses import FrozenInstanceError
from functools import lru_cache
from itertools import product

import pytest

from pix.case_centric.tree_reduction import (
    RESULT_SCHEMAS,
    TraceTreeReductionSpec,
    TreeFoldSpec,
    fold_process_tree,
    reduce_process_tree_for_trace,
)
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

TAU = ProcessTree("tau")
A = ProcessTree("activity", "A")
B = ProcessTree("activity", "B")


def node(operator, *children):
    return ProcessTree(operator, children=tuple(children))


@lru_cache(None)
def interleave(left, right):
    if not left:
        return frozenset((right,))
    if not right:
        return frozenset((left,))
    return frozenset(
        {(left[0], *tail) for tail in interleave(left[1:], right)}
        | {(right[0], *tail) for tail in interleave(left, right[1:])}
    )


@lru_cache(None)
def language(tree, max_length=4):
    """Operator-set semantics, independent of the production reducer/Petri net.

    Loops use a finite least fixed point on words up to the visible length cap;
    epsilon iterations cannot invalidate convergence. This is exact at the cap.
    """
    op = tree.operator
    if op == "activity":
        return frozenset(((tree.activity,),)) if max_length else frozenset()
    if op == "tau":
        return frozenset(((),))
    children = tuple(language(c, max_length) for c in tree.children)

    def concatenate(one, two):
        return {(*a, *b) for a in one for b in two if len(a) + len(b) <= max_length}

    if op == "xor":
        return frozenset().union(*children)
    if op == "loop":
        words = set(children[0])
        while True:
            larger = words | concatenate(concatenate(words, children[1]), children[0])
            if larger == words:
                return frozenset(words)
            words = larger
    words = {()}
    for child in children:
        if op == "sequence":
            words = concatenate(words, child)
        else:
            words = {
                w
                for a in words
                for b in child
                if len(a) + len(b) <= max_length
                for w in interleave(a, b)
            }
    return frozenset(words)


def edit_cost(trace, model_word, log_cost=1, model_cost=1):
    # Wagner-Fischer, insertion/deletion only; unequal substitution costs both.
    previous = [j * model_cost for j in range(len(model_word) + 1)]
    for i, event in enumerate(trace, 1):
        current = [i * log_cost]
        for j, activity in enumerate(model_word, 1):
            current.append(
                min(
                    previous[j] + log_cost,
                    current[j - 1] + model_cost,
                    previous[j - 1]
                    + (0 if event == activity else log_cost + model_cost),
                )
            )
        previous = current
    return previous[-1]


def minimum(trace, model_language, log_cost=1, model_cost=1):
    return min(edit_cost(trace, word, log_cost, model_cost) for word in model_language)


def fold_examples():
    leaves = (TAU, A, B)
    yield from leaves
    for op in ("sequence", "xor", "parallel", "loop"):
        for one, two in product(leaves, repeat=2):
            yield node(op, one, two)
    for op in ("sequence", "xor", "parallel"):
        yield node(op, TAU, node(op, A, B), TAU)
        yield node(op, A, A, node(op, A, A))
        yield node(op, node("loop", TAU, A), TAU)
        yield node(op, node("loop", A, TAU), TAU)
        yield node(op, node("xor", TAU, A), node("parallel", TAU, B))
    yield node("loop", node("xor", TAU, TAU), node("sequence", TAU, TAU))
    yield node("loop", node("parallel", A, TAU), node("sequence", B, TAU))
    yield node("xor", node("sequence", A, B), node("sequence", B, A))


FOLD_EXAMPLES = tuple(fold_examples())


@pytest.mark.parametrize("model", FOLD_EXAMPLES)
def test_fold_preserves_independent_visible_language_and_is_idempotent(model):
    result = fold_process_tree(model)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.guarantee == "visible_language_equivalence"
    assert language(result.value.model) == language(model)
    repeated = fold_process_tree(result.value.model)
    assert repeated.value.model == result.value.model
    assert repeated.value.changed is False
    assert repeated.value.rewrites == ()
    assert result.value.output_node_count <= result.value.input_node_count


@pytest.mark.parametrize("op", ("sequence", "parallel"))
def test_duplicate_visible_leaves_are_not_removed_outside_xor(op):
    output = fold_process_tree(node(op, A, A)).value.model
    assert language(output) == {("A", "A")}


def test_xor_preserves_branch_order_and_deduplicates_full_structure_only():
    ab = node("sequence", A, B)
    ba = node("sequence", B, A)
    output = fold_process_tree(node("xor", ab, ba, ab)).value
    assert output.model.children == (ab, ba)
    assert language(output.model) == {("A", "B"), ("B", "A")}
    assert any(r.rule == "deduplicate_xor_alternatives" for r in output.rewrites)


def test_tau_is_retained_in_xor_when_no_other_alternative_is_nullable():
    output = fold_process_tree(node("xor", A, TAU)).value.model
    assert output.operator == "xor"
    assert language(output) == {(), ("A",)}


@pytest.mark.parametrize(
    "do,redo,expected",
    [
        (TAU, A, {(), ("A",), ("A", "A"), ("A", "A", "A")}),
        (A, TAU, {("A",), ("A", "A"), ("A", "A", "A")}),
        (TAU, TAU, {()}),
    ],
)
def test_binary_loop_epsilon_and_repeat_counterexamples(do, redo, expected):
    reduced = fold_process_tree(node("loop", do, redo)).value.model
    assert language(reduced, 3) == expected


def test_redundant_xor_tau_is_removed_only_when_another_child_can_skip():
    star = node("loop", TAU, A)
    plus = node("loop", A, TAU)
    assert fold_process_tree(node("xor", TAU, star)).value.model == star
    assert fold_process_tree(node("xor", TAU, plus)).value.model.operator == "xor"


def trace_models():
    optional = node("xor", TAU, B)
    for op in ("sequence", "parallel", "xor", "loop"):
        yield node(op, A, optional)
        yield node(op, optional, A)
    yield node("loop", node("sequence", A, optional), node("xor", TAU, B))
    yield node("loop", node("parallel", TAU, optional), A)
    yield node("sequence", optional, optional, A)
    yield node("xor", TAU, node("parallel", optional, optional))
    yield node("parallel", A, node("loop", TAU, B))
    yield node("loop", node("xor", TAU, A), node("xor", TAU, B))


TRACE_MODELS = tuple(trace_models())
TRACES = (
    (),
    ("A",),
    ("B",),
    ("A", "B"),
    ("B", "A"),
    ("A", "A"),
    ("UNKNOWN",),
    ("A", "UNKNOWN", "A"),
)


@pytest.mark.parametrize("model", TRACE_MODELS)
@pytest.mark.parametrize("costs", ((1, 1), (0, 1), (1, 0), (0, 0), (2, 3), (0.25, 1.5)))
def test_trace_reduction_preserves_independent_optimal_edit_cost_for_loops_and_parallel(
    model, costs
):
    before = language(model, 5)
    for trace in TRACES:
        result = reduce_process_tree_for_trace(
            model,
            trace,
            TraceTreeReductionSpec(
                log_move_cost=costs[0], model_move_cost=costs[1], reduce_root=True
            ),
        )
        assert result.status is ComputeStatus.COMPUTED
        after = language(result.value.model, 5)
        assert after <= before
        assert minimum(trace, after, *costs) == minimum(trace, before, *costs)
        assert result.spec.trace == trace
        assert result.value.guarantee == "fixed_trace_minimum_insertion_deletion_cost"


def test_trace_specific_reduction_does_not_claim_entire_language_equivalence():
    original = node("sequence", A, node("xor", TAU, B))
    reduced = reduce_process_tree_for_trace(original, ("A",)).value
    assert reduced.model == A
    assert language(reduced.model) < language(original)
    assert minimum(("A", "B"), language(reduced.model)) == 1
    assert minimum(("A", "B"), language(original)) == 0


def test_root_is_not_pruned_by_default_but_explicit_root_profile_reduces_it():
    original = node("xor", TAU, A)
    assert reduce_process_tree_for_trace(original, ()).value.model == original
    assert (
        reduce_process_tree_for_trace(
            original, (), TraceTreeReductionSpec(reduce_root=True)
        ).value.model
        == TAU
    )


def test_mandatory_nontrace_activity_is_not_pruned():
    original = node("sequence", A, B)
    reduced = reduce_process_tree_for_trace(original, ("A",)).value.model
    assert reduced == original
    assert minimum(("A",), language(reduced)) == 1
    assert minimum(("A",), language(A)) == 0  # unsafe mandatory pruning counterexample


def test_nullable_subtree_with_a_trace_activity_is_not_pruned():
    optional = node("xor", TAU, A)
    result = reduce_process_tree_for_trace(
        optional, ("A",), TraceTreeReductionSpec(reduce_root=True)
    )
    assert result.value.model == optional
    assert minimum(("A",), language(optional)) == 0
    assert minimum(("A",), language(TAU)) == 1  # unsafe overlap pruning counterexample


def epsilon_derivation(tree, selected_paths):
    """Check witness against input operators, independently of nullable code."""
    if tree.operator == "tau":
        return selected_paths == {()}
    if tree.operator == "activity":
        return False
    partitions = {
        i: {p[1:] for p in selected_paths if p and p[0] == i}
        for i in range(len(tree.children))
    }
    used = {i for i, p in partitions.items() if p}
    if tree.operator == "xor" and len(used) != 1:
        return False
    if tree.operator == "loop" and used != {0}:
        return False
    if tree.operator in ("parallel", "sequence") and used != set(partitions):
        return False
    return all(epsilon_derivation(tree.children[i], partitions[i]) for i in used)


def test_trace_pruning_witness_identifies_original_occurrence_and_epsilon_derivation():
    # Composite epsilon derivation includes parallel, XOR, sequence, loop.
    optional = node(
        "sequence", node("parallel", TAU, node("xor", B, TAU)), node("loop", TAU, B)
    )
    original = node("parallel", A, optional, optional)
    result = reduce_process_tree_for_trace(original, ("A",)).value
    witnesses = [
        w for w in result.rewrites if w.rule == "trace_nullable_disjoint_to_tau"
    ]
    assert [w.source_path for w in witnesses] == [(1,), (2,)]
    for witness in witnesses:
        assert witness.removed_activities == ("B",)
        assert epsilon_derivation(optional, set(witness.epsilon_leaf_paths))
        assert witness.before_structure_digest != witness.after_structure_digest


def parent(model, status=ComputeStatus.COMPUTED):
    return ComputationResult(
        "test.tree_source",
        "1.0.0",
        "source-events",
        TreeFoldSpec(),
        status,
        model if status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL) else None,
        (ComputeIssue("source_issue", "Retain the upstream issue"),),
        "parent-computation",
    )


def test_parent_source_status_issues_and_identity_are_preserved():
    source = parent(node("sequence", TAU, A), ComputeStatus.PARTIAL)
    result = fold_process_tree(source)
    assert result.status is ComputeStatus.PARTIAL
    assert result.source_digest == source.source_digest
    assert result.parent_computation_ids == (source.computation_id,)
    assert source.issues == result.issues
    assert result.value.model == A


@pytest.mark.parametrize(
    "status", (ComputeStatus.INVALID_INPUT, ComputeStatus.UNAVAILABLE)
)
def test_failed_parent_is_propagated_without_a_reduced_model(status):
    source = parent(A, status)
    result = reduce_process_tree_for_trace(source, ("A",))
    assert result.status is status
    assert result.value is None
    assert result.source_digest == source.source_digest
    assert result.issues == source.issues
    assert result.parent_computation_ids == (source.computation_id,)


def test_digest_includes_model_trace_order_and_cost_parameters_under_same_parent():
    source = parent(node("sequence", A, node("xor", TAU, B)))
    outputs = [
        reduce_process_tree_for_trace(source, ("A", "B")),
        reduce_process_tree_for_trace(source, ("B", "A")),
        reduce_process_tree_for_trace(
            source, ("A", "B"), TraceTreeReductionSpec(model_move_cost=2)
        ),
        reduce_process_tree_for_trace(parent(node("parallel", A, B)), ("A", "B")),
    ]
    assert len({r.computation_id for r in outputs}) == 4
    assert len({r.source_digest for r in outputs}) == 1
    assert len({r.parent_computation_ids for r in outputs}) == 1


@pytest.mark.parametrize(
    "api,spec",
    [
        (fold_process_tree, TreeFoldSpec(profile="future.not_implemented")),
        (
            lambda model, spec: reduce_process_tree_for_trace(model, (), spec),
            TraceTreeReductionSpec(profile="arbitrary_transition_costs"),
        ),
    ],
)
def test_unimplemented_profiles_are_explicitly_unavailable(api, spec):
    result = api(A, spec)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "unsupported_tree_reduction_profile"
    assert result.computation_id


@pytest.mark.parametrize("spec_type", (TreeFoldSpec, TraceTreeReductionSpec))
@pytest.mark.parametrize(
    "field,value",
    [
        ("max_nodes", 0),
        ("max_nodes", True),
        ("max_nodes", 2.1),
        ("max_depth", 0),
        ("max_depth", False),
        ("max_depth", 49),
        ("profile", ""),
        ("profile", None),
        ("profile", "\ud800"),
    ],
)
def test_invalid_specs(spec_type, field, value):
    with pytest.raises((ValueError, TypeError)):
        spec_type(**{field: value})


@pytest.mark.parametrize("name", ("log_move_cost", "model_move_cost"))
@pytest.mark.parametrize("value", (-1, float("nan"), float("inf"), True, "1", 10**500))
def test_unsupported_costs_cannot_claim_trace_alignment_guarantee(name, value):
    with pytest.raises((ValueError, TypeError)):
        TraceTreeReductionSpec(**{name: value})


@pytest.mark.parametrize("trace", ([], "A", (None,), (1,), ("",), (" ",), ("\ud800",)))
def test_invalid_trace_is_not_silently_projected_or_coerced(trace):
    with pytest.raises((TypeError, ValueError)):
        reduce_process_tree_for_trace(A, trace)


def test_case_and_unicode_labels_are_exact_and_not_normalized():
    lower = ProcessTree("activity", "a")
    optional = node("xor", TAU, lower)
    assert (
        reduce_process_tree_for_trace(
            optional, ("A",), TraceTreeReductionSpec(reduce_root=True)
        ).value.model
        == TAU
    )
    composed = ProcessTree("activity", "é")
    original = node("xor", TAU, composed)
    assert (
        reduce_process_tree_for_trace(
            original, ("e\u0301",), TraceTreeReductionSpec(reduce_root=True)
        ).value.model
        == TAU
    )


def test_node_and_depth_limits_do_not_return_a_truncated_model():
    original = node("sequence", A, node("xor", TAU, B))
    assert (
        fold_process_tree(original, TreeFoldSpec(max_nodes=5, max_depth=3)).status
        is ComputeStatus.COMPUTED
    )
    for spec in (TreeFoldSpec(max_nodes=4), TreeFoldSpec(max_depth=2)):
        result = fold_process_tree(original, spec)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert result.issues[0].code == "tree_reduction_limit"
    limited_parent = fold_process_tree(parent(original), TreeFoldSpec(max_nodes=4))
    assert limited_parent.source_digest == "source-events"
    assert limited_parent.parent_computation_ids == ("parent-computation",)


def test_deep_tree_is_checked_iteratively_before_recursive_hashing():
    original = A
    for _ in range(500):
        original = node("sequence", original, TAU)
    result = fold_process_tree(original)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_wide_tree_over_budget_is_rejected_before_semantic_inspection():
    original = node("parallel", *((A,) * 20_000))
    result = fold_process_tree(original, TreeFoldSpec(max_nodes=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.spec.model_digest is None


def test_frozen_results_and_cost_identity_normalization():
    one = TraceTreeReductionSpec(model_move_cost=1, log_move_cost=0)
    two = TraceTreeReductionSpec(model_move_cost=1.0, log_move_cost=0.0)
    assert (
        reduce_process_tree_for_trace(A, (), one).computation_id
        == reduce_process_tree_for_trace(A, (), two).computation_id
    )
    result = fold_process_tree(A)
    with pytest.raises(FrozenInstanceError):
        result.value.model = B
    with pytest.raises(FrozenInstanceError):
        one.reduce_root = True


def test_declared_result_schemas_encode_and_decode_with_exact_contract():
    import pix.results as codec

    schemas = codec._schemas()
    for operator, contract in RESULT_SCHEMAS.items():
        assert schemas[operator] == contract
    original = node("sequence", A, node("xor", TAU, B))
    for result in (
        fold_process_tree(original),
        reduce_process_tree_for_trace(original, ("A",)),
        reduce_process_tree_for_trace(
            original, (), TraceTreeReductionSpec(profile="unknown")
        ),
    ):
        assert codec.result_from_json(codec.result_json_bytes(result)) == result


def test_supported_depth_boundary_survives_result_codec():
    import pix.results as codec

    original = A
    for _ in range(47):
        original = node("loop", original, B)
    result = fold_process_tree(original)
    assert result.status is ComputeStatus.COMPUTED
    assert codec.result_from_json(codec.result_json_bytes(result)) == result
