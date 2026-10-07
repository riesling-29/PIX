"""Independent word-language and occurrence-mapping checks for POWL conversion."""

from dataclasses import dataclass, replace
from itertools import combinations, permutations, product

import pytest

from pix.case_centric.model_analysis import compare_models
from pix.case_centric.model_conversion import tree_to_powl
from pix.case_centric.powl import POWLNode, powl_to_petri_net
from pix.case_centric.powl_conversion import (
    POWLTreeConversionSpec,
    powl_to_process_tree,
)
from pix.compute._common import _derived_result
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeIssue, ComputeStatus


def a(label):
    return POWLNode("activity", label)


def partial(*children, order=()):
    return POWLNode("partial_order", children=children, order=order)


def shuffle(left, right):
    if not left:
        return {right}
    if not right:
        return {left}
    return {(left[0],) + rest for rest in shuffle(left[1:], right)} | {
        (right[0],) + rest for rest in shuffle(left, right[1:])
    }


def words(tree, bound=5):
    """Direct tree language, with no PIX firing or language implementation."""
    if tree.operator == "tau":
        return {()}
    if tree.operator == "activity":
        return {(tree.activity,)}
    languages = [words(child, bound) for child in tree.children]
    if tree.operator == "xor":
        return set.union(*languages)
    if tree.operator in ("parallel", "sequence"):
        result = {()}
        for language in languages:
            result = {
                word
                for left, right in product(result, language)
                if len(left) + len(right) <= bound
                for word in (
                    shuffle(left, right)
                    if tree.operator == "parallel"
                    else (left + right,)
                )
            }
        return result
    result = set(languages[0])
    while True:
        extended = {
            x + y + z
            for x, y, z in product(result, languages[1], languages[0])
            if len(x) + len(y) + len(z) <= bound
        }
        if extended <= result:
            return result
        result.update(extended)


def test_parallel_retains_ab_and_ba_but_sequence_has_only_ab():
    independent = powl_to_process_tree(partial(a("A"), a("B")))
    ordered = powl_to_process_tree(partial(a("A"), a("B"), order=((0, 1),)))
    assert words(independent.value.model) == {("A", "B"), ("B", "A")}
    assert words(ordered.value.model) == {("A", "B")}
    assert independent.value.model.operator == "parallel"
    assert ordered.value.model.operator == "sequence"


def test_sequence_uses_relation_not_original_child_order():
    source = partial(a("C"), a("A"), a("B"), order=((1, 2), (2, 0)))
    result = powl_to_process_tree(source)
    assert words(result.value.model) == {("A", "B", "C")}
    assert [step.source_path for step in result.value.steps[1:]] == [(1,), (2,), (0,)]


def test_fork_join_is_sequence_of_parallel_children():
    source = partial(
        *(a(label) for label in "ABCD"),
        order=((0, 1), (0, 2), (1, 3), (2, 3)),
    )
    result = powl_to_process_tree(source)
    assert words(result.value.model) == {tuple("ABCD"), tuple("ACBD")}
    assert result.value.model.operator == "sequence"
    assert result.value.model.children[1].operator == "parallel"
    middle = result.value.steps[2]
    assert middle.source_path == ()
    assert middle.source_child_indices == (1, 2)
    assert middle.tree_path == (1,)


def test_unordered_submodel_interleaves_internally():
    source = partial(partial(a("A"), a("B"), order=((0, 1),)), a("C"))
    result = powl_to_process_tree(source)
    assert words(result.value.model) == {tuple(w) for w in ("ABC", "ACB", "CAB")}


def test_ordered_submodel_must_finish_before_successor():
    source = partial(partial(a("A"), a("B")), a("C"), order=((0, 1),))
    assert words(powl_to_process_tree(source).value.model) == {
        tuple("ABC"),
        tuple("BAC"),
    }


N_ORDER = ((0, 2), (0, 3), (1, 3))


def test_n_order_is_refused_without_topological_sort_or_activity_duplication():
    source = partial(*(a(label) for label in "ABCD"), order=N_ORDER)
    result = powl_to_process_tree(source)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "powl_non_series_parallel"
    assert "(0, 1, 2, 3)" in result.issues[0].message
    assert result.source_digest is not None


def test_nested_n_order_reports_source_occurrence_path():
    bad = partial(*(a(label) for label in "ABCD"), order=N_ORDER)
    result = powl_to_process_tree(POWLNode("xor", children=(a("X"), bad)))
    assert result.value is None
    assert result.issues[0].at == ("1",)


@pytest.mark.parametrize("mask", range(64))
def test_all_four_node_forward_dags_match_independent_permutations_or_n(mask):
    possible = tuple(combinations(range(4), 2))
    relation = tuple(edge for index, edge in enumerate(possible) if mask & (1 << index))
    source = partial(*(a(label) for label in "ABCD"), order=relation)
    result = powl_to_process_tree(source)
    if result.value is None:
        # On four distinct occurrences, the only obstruction is an induced N.
        assert any(
            set(source.order) == {(perm[x], perm[y]) for x, y in N_ORDER}
            for perm in permutations(range(4))
        )
        assert result.issues[0].code == "powl_non_series_parallel"
    else:
        expected = {
            word
            for word in permutations("ABCD")
            if all(word.index("ABCD"[x]) < word.index("ABCD"[y]) for x, y in relation)
        }
        assert words(result.value.model) == expected


def test_all_five_node_forward_dags_match_language_or_contain_induced_n():
    """1,024 generating DAGs exercise nontrivial subsets in decompositions."""
    possible = tuple(combinations(range(5), 2))
    all_words = tuple(permutations("ABCDE"))
    for mask in range(1024):
        relation = tuple(
            edge for index, edge in enumerate(possible) if mask & (1 << index)
        )
        source = partial(*(a(label) for label in "ABCDE"), order=relation)
        result = powl_to_process_tree(source)
        if result.value is None:
            assert result.issues[0].code == "powl_non_series_parallel"
            assert any(
                {(x, y) for x, y in source.order if x in subset and y in subset}
                == {(perm[x], perm[y]) for x, y in N_ORDER}
                for subset in combinations(range(5), 4)
                for perm in permutations(subset)
            ), mask
        else:
            expected = {
                word
                for word in all_words
                if all(
                    word.index("ABCDE"[x]) < word.index("ABCDE"[y]) for x, y in relation
                )
            }
            assert words(result.value.model) == expected, mask


@pytest.mark.parametrize(
    "source,expected",
    [
        (POWLNode("tau"), {()}),
        (a("A"), {("A",)}),
        (POWLNode("xor", children=(a("A"), POWLNode("tau"))), {(), ("A",)}),
        (
            POWLNode("loop", children=(a("A"), a("B"))),
            {tuple("A"), tuple("ABA"), tuple("ABABA")},
        ),
        (
            POWLNode("loop", children=(POWLNode("tau"), a("B"))),
            {tuple("B" * size) for size in range(6)},
        ),
        (POWLNode("loop", children=(POWLNode("tau"), POWLNode("tau"))), {()}),
        (partial(a("A"), a("A")), {("A", "A")}),
    ],
)
def test_leaves_choice_loops_and_duplicate_labels(source, expected):
    result = powl_to_process_tree(source)
    assert words(result.value.model) == expected
    compared = compare_models(
        powl_to_petri_net(source), process_tree_to_petri_net(result.value.model)
    )
    assert compared.status == ComputeStatus.COMPUTED
    assert compared.value.complete is True
    assert compared.value.equivalent is True


def test_every_leaf_has_distinct_source_and_destination_occurrence_mapping():
    source = partial(a("A"), partial(a("A"), a("A")), order=((1, 0),))
    result = powl_to_process_tree(source)
    leaves = [step for step in result.value.steps if step.rule == "activity"]
    assert {step.source_path for step in leaves} == {(0,), (1, 0), (1, 1)}
    assert len({step.tree_path for step in leaves}) == 3
    for step in leaves:
        target = result.value.model
        for index in step.tree_path:
            target = target.children[index]
        assert target.operator == "activity" and target.activity == "A"


def test_tree_powl_tree_roundtrip_retains_full_finite_state_language():
    source = ProcessTree(
        "parallel",
        children=(
            ProcessTree(
                "loop", children=(ProcessTree("activity", "A"), ProcessTree("tau"))
            ),
            ProcessTree(
                "xor", children=(ProcessTree("activity", "B"), ProcessTree("tau"))
            ),
        ),
    )
    parent = tree_to_powl(source)
    result = powl_to_process_tree(parent)
    compared = compare_models(
        process_tree_to_petri_net(source), process_tree_to_petri_net(result.value.model)
    )
    assert compared.value.complete and compared.value.equivalent
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)
    assert result.value.source_model_digest == result.spec.model_digest


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_model_nodes": 2},
        {"max_depth": 1},
        {"max_output_nodes": 2},
        {"max_order_pairs": 1},
        {"max_partial_order_children": 2},
        {"max_decomposition_checks": 1},
    ],
)
def test_resource_limits_never_release_truncated_tree(overrides):
    source = partial(a("A"), a("B"), a("C"), order=((0, 1), (1, 2)))
    result = powl_to_process_tree(source, POWLTreeConversionSpec(**overrides))
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "powl_tree_conversion_limit"


def test_exact_decomposition_budget_boundary_and_digest():
    from pix.models import model_document

    source = partial(a("A"), a("B"), order=((0, 1),))
    result = powl_to_process_tree(source)
    assert result.source_digest == model_document(source)["model_digest"]
    checks = result.value.decomposition_checks
    exact = POWLTreeConversionSpec(max_decomposition_checks=checks)
    assert powl_to_process_tree(source, exact).status == ComputeStatus.COMPUTED
    assert (
        powl_to_process_tree(
            source, replace(exact, max_decomposition_checks=checks - 1)
        ).status
        == ComputeStatus.UNAVAILABLE
    )


def test_deep_input_is_unavailable_instead_of_codec_exception():
    source = a("A")
    for _ in range(600):
        source = POWLNode("xor", children=(source, a("B")))
    result = powl_to_process_tree(source)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.source_digest is None
    assert result.computation_id is None


def test_decomposition_generated_depth_has_its_own_bound():
    # The POWL is only two nodes deep, but its tree requires three levels.
    source = partial(a("A"), a("B"), a("C"), order=((0, 2), (1, 2)))
    assert (
        powl_to_process_tree(source, POWLTreeConversionSpec(max_depth=2)).value is None
    )


def test_failed_and_partial_parent_provenance():
    failed = _derived_result(
        "test.parent",
        "test:source",
        POWLTreeConversionSpec(),
        ComputeStatus.UNAVAILABLE,
        None,
        (ComputeIssue("input", "unavailable"),),
    )
    result = powl_to_process_tree(failed)
    assert result.status == failed.status
    assert result.issues == failed.issues
    assert result.source_digest == failed.source_digest
    assert result.parent_computation_ids == (failed.computation_id,)
    partial_result = _derived_result(
        "test.parent",
        "test:source",
        POWLTreeConversionSpec(),
        ComputeStatus.PARTIAL,
        a("A"),
        (ComputeIssue("coverage", "subset only"),),
    )
    converted = powl_to_process_tree(partial_result)
    assert converted.status == ComputeStatus.PARTIAL
    assert converted.issues == partial_result.issues


def test_partial_parent_without_released_model_stays_unavailable():
    @dataclass(frozen=True)
    class Pending:
        model: POWLNode | None = None

    parent = _derived_result(
        "test.parent",
        "test:source",
        POWLTreeConversionSpec(),
        ComputeStatus.PARTIAL,
        Pending(),
        (ComputeIssue("budget", "no model"),),
    )
    assert powl_to_process_tree(parent).status == ComputeStatus.UNAVAILABLE


def test_result_roundtrip_preserves_model_mapping_and_failure():
    from pix import results

    for source in (
        partial(a("A"), a("A"), order=((1, 0),)),
        partial(*(a(label) for label in "ABCD"), order=N_ORDER),
    ):
        result = powl_to_process_tree(source)
        assert results.result_from_json(results.result_json_bytes(result)) == result


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "1"])
def test_invalid_numeric_budget(value):
    with pytest.raises(ValueError):
        POWLTreeConversionSpec(max_decomposition_checks=value)


def test_invalid_spec_or_input_types():
    with pytest.raises(ValueError):
        POWLTreeConversionSpec(max_depth=49)
    with pytest.raises(TypeError):
        powl_to_process_tree(a("A"), None)
    with pytest.raises(TypeError):
        powl_to_process_tree(ProcessTree("activity", "A"))
    with pytest.raises(TypeError):
        powl_to_process_tree(None)
