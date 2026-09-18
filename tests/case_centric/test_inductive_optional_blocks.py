"""Independent finite-language witnesses for explicit strict sequence mining."""

from collections import Counter
from dataclasses import fields
from itertools import combinations, product

import pytest

from pix.case_centric.inductive import (
    InductiveSpec,
    StrictInductiveSpec,
    _from_log,
    _strict_sequence_groups,
    discover_inductive,
    discover_inductive_dfg,
    discover_inductive_strict,
)
from pix.compute._common import _result
from pix.compute.dfg import _graph
from pix.contracts.analysis import ObjectTrace, TraceEvent, TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.results import result_from_json, result_json_bytes


def _traces(*words):
    return _result(
        "test.traces",
        None,
        CaseTraceSpec(),
        ComputeStatus.COMPUTED,
        TraceSet(
            "case",
            tuple(
                ObjectTrace(
                    str(i),
                    "case",
                    tuple(
                        TraceEvent(f"{i}:{j}", a, None, ()) for j, a in enumerate(word)
                    ),
                )
                for i, word in enumerate(words)
            ),
        ),
        source_digest="test-source",
    )


def _finite_language(tree):
    """Direct tree interpretation; no production conversion/replay/miner oracle.

    These deliberately finite expected models use only leaf, sequence and XOR.
    Unexpected loop/parallel generalisation must fail rather than be truncated.
    """
    if tree.operator == "tau":
        return {""}
    if tree.operator == "activity":
        return {tree.activity}
    languages = [_finite_language(child) for child in tree.children]
    if tree.operator == "xor":
        return set().union(*languages)
    assert tree.operator == "sequence", tree
    return {"".join(parts) for parts in product(*languages)}


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
@pytest.mark.parametrize(
    "words,expected",
    [
        (("ABC", "A"), {"ABC", "A"}),  # jointly optional suffix
        (("ABC", "C"), {"ABC", "C"}),  # jointly optional prefix
        (("ABCD", "AD"), {"ABCD", "AD"}),  # jointly optional middle
        (("ABCDE", "AE"), {"ABCDE", "AE"}),  # longer optional interval
        (("ABCD", "ABD", "ACD", "AD"), {"ABCD", "ABD", "ACD", "AD"}),
        (("ABCDE", "ADE", "AE"), {"ABCDE", "ADE", "AE"}),  # nesting
        (("ABCDE", "ABE", "AE"), {"ABCDE", "ABE", "AE"}),
        (("", "ABC", "A"), {"", "ABC", "A"}),
        (("ABC",), {"ABC"}),
    ],
)
def test_strict_finite_languages(variant, words, expected):
    result = discover_inductive_strict(_traces(*words), StrictInductiveSpec(variant))
    assert result.status is ComputeStatus.COMPUTED
    assert _finite_language(result.value) == expected
    assert result.operator_id == "pix.case_centric.discover_inductive_strict"
    assert "strict_sequence.v2" in next(
        issue.message for issue in result.issues if issue.code == "inductive_profile"
    )


def test_overlapping_bypass_intervals_use_current_contracted_groups():
    # Static interval union would produce ABC as one group. Once B has moved
    # into the first group, its emptied old slot cannot move it into C again.
    graph = _from_log(Counter({tuple("ABC"): 1, ("A",): 1, ("C",): 1}))
    groups = ({"A"}, {"B"}, {"C"})
    assert _strict_sequence_groups(graph, groups) == ({"A", "B"}, {"C"})
    assert groups == ({"A"}, {"B"}, {"C"})  # caller partition is not mutated


@pytest.mark.parametrize("words", [("ABC", "A"), ("ABCD", "AD"), ("", "ABC", "C")])
def test_direct_graph_strict_profile_matches_trace_derived_graph(words):
    source = _traces(*words)
    graph = _result(
        "test.dfg",
        None,
        CaseTraceSpec(),
        ComputeStatus.COMPUTED,
        _graph(source.value),
        source_digest=source.source_digest,
    )
    spec = StrictInductiveSpec("imd")
    direct = discover_inductive_dfg(graph, spec)
    derived = discover_inductive_strict(source, spec)
    assert direct.status is derived.status is ComputeStatus.COMPUTED
    assert direct.value == derived.value
    assert direct.operator_id == "pix.case_centric.discover_inductive_strict"
    assert direct.parent_computation_ids == (graph.computation_id,)
    assert result_from_json(result_json_bytes(direct)) == direct


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
def test_strict_sequence_does_not_promise_observed_language_equality(variant):
    result = discover_inductive_strict(
        _traces("ABCD", "ABD", "ACD"), StrictInductiveSpec(variant)
    )
    # Each activity can be independently skipped by a different DFG edge;
    # consequently AD is permitted although it was not present in the log.
    assert _finite_language(result.value) == {"ABCD", "ABD", "ACD", "AD"}


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
@pytest.mark.parametrize(
    "words,operator",
    [(("AB", "BA"), "parallel"), (("A", "ABA", "ACA"), "loop"), (("AB", "CD"), "xor")],
)
def test_other_cut_families_retain_their_existing_contract(variant, words, operator):
    source = _traces(*words)
    legacy = discover_inductive(source, InductiveSpec(variant))
    strict = discover_inductive_strict(source, StrictInductiveSpec(variant))
    assert strict.status is ComputeStatus.COMPUTED
    assert strict.value.operator == operator
    assert strict.value == legacy.value


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
def test_refinement_is_explicit_and_legacy_identity_schema_is_unchanged(variant):
    parent = _traces("ABC", "A")
    legacy = discover_inductive(parent, InductiveSpec(variant))
    strict = discover_inductive(parent, StrictInductiveSpec(variant))
    assert _finite_language(legacy.value) == {"A", "AB", "AC", "ABC"}
    assert _finite_language(strict.value) == {"A", "ABC"}
    assert legacy.operator_id == "pix.case_centric.discover_inductive"
    if variant == "im":
        # Captured by executing the original module at commit 326eef5c703f.
        assert legacy.computation_id == (
            "pix.computation.v1:sha256:"
            "66f6ad19635cbf96f18a706a42f10cc2fd33af2b93616471d8c519fae3a4c77e"
        )
    assert legacy.computation_id != strict.computation_id
    assert legacy.source_digest == strict.source_digest == parent.source_digest
    assert legacy.parent_computation_ids == strict.parent_computation_ids
    assert tuple(field.name for field in fields(InductiveSpec)) == (
        "variant",
        "noise_threshold",
        "fallback",
        "max_depth",
        "max_nodes",
        "trace_spec",
    )
    for result in (legacy, strict):
        assert result_from_json(result_json_bytes(result)) == result


def test_strict_noise_filtering_retains_weighted_optional_block_semantics():
    excluded = discover_inductive_strict(
        _traces(*(["ABC"] * 9 + ["A"])),
        StrictInductiveSpec("imf", noise_threshold=0.1),
    )
    retained = discover_inductive_strict(
        _traces(*(["ABC"] * 8 + ["A"] * 2)),
        StrictInductiveSpec("imf", noise_threshold=0.1),
    )
    assert _finite_language(excluded.value) == {"ABC"}
    assert _finite_language(retained.value) == {"A", "ABC"}
    assert any(issue.code == "inductive_empty_filter" for issue in excluded.issues)


@pytest.mark.parametrize("variant", ["im", "imf"])
def test_strict_preserves_observed_optional_subsequences_without_noise(variant):
    # This checks fitness, not equality with the observed language. Discovering
    # extra combinations is permitted when the cut evidence permits them.
    words = [
        "A" + "".join(part) + "E"
        for size in range(4)
        for part in combinations("BCD", size)
    ]
    for population in combinations(words, 3):
        result = discover_inductive_strict(
            _traces(*population), StrictInductiveSpec(variant)
        )
        assert result.status is ComputeStatus.COMPUTED
        assert set(population) <= _finite_language(result.value)


def test_explicit_strict_wrapper_and_bounds_are_validated():
    with pytest.raises(TypeError, match="StrictInductiveSpec"):
        discover_inductive_strict(_traces("A"), InductiveSpec())
    result = discover_inductive_strict(
        _traces("ABC", "A"), StrictInductiveSpec(max_nodes=2)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(issue.code == "inductive_limit" for issue in result.issues)
