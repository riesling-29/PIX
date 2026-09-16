"""Hand-specified languages and independent token exploration for IM profiles."""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from itertools import combinations, product

import pytest

from pix.case_centric.inductive import (
    InductiveSpec,
    discover_inductive,
    discover_inductive_dfg,
)
from pix.compute._common import _result
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.analysis import (
    ActivityCount,
    BoundaryCount,
    BoundaryEvidence,
    DirectlyFollowsEdge,
    DirectlyFollowsGraph,
    ObjectTrace,
    TraceEvent,
    TraceSet,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeIssue, ComputeStatus


def traces(*words):
    value = TraceSet(
        "case",
        tuple(
            ObjectTrace(
                str(i),
                "case",
                tuple(TraceEvent(f"{i}:{j}", a, None, ()) for j, a in enumerate(word)),
            )
            for i, word in enumerate(words)
        ),
    )
    return _result(
        "test.traces",
        None,
        CaseTraceSpec(),
        ComputeStatus.COMPUTED,
        value,
        source_digest="test-source",
    )


def mine(*words, variant="im", **kwargs):
    return discover_inductive(traces(*words), InductiveSpec(variant=variant, **kwargs))


def accepts(tree, word):
    """Independent finite marking/offset search, with no replay/alignment call."""
    net = process_tree_to_petri_net(tree)
    initial = net.initial_marking.tokens, 0
    seen, queue = {initial}, deque([initial])
    while queue:
        marking, index = queue.popleft()
        if marking == net.final_marking.tokens and index == len(word):
            return True
        for transition in net.transitions:
            if transition.activity is not None and (
                index == len(word) or word[index] != transition.activity
            ):
                continue
            needed = Counter(
                {
                    arc.source: arc.weight
                    for arc in net.arcs
                    if arc.target == transition.id
                }
            )
            if any(dict(marking).get(place, 0) < n for place, n in needed.items()):
                continue
            after = Counter(dict(marking))
            after.subtract(needed)
            after.update(
                {
                    arc.target: arc.weight
                    for arc in net.arcs
                    if arc.source == transition.id
                }
            )
            following = (
                tuple(sorted((p, n) for p, n in after.items() if n)),
                index + (transition.activity is not None),
            )
            if following not in seen:
                assert len(seen) < 20000, "independent finite-language oracle exhausted"
                seen.add(following)
                queue.append(following)
    return False


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
@pytest.mark.parametrize(
    "words,accepted,rejected",
    [
        (("ABC",), ("ABC",), ("", "AB", "ACB", "ABCC")),
        (("AB", "CD"), ("AB", "CD"), ("AC", "AD", "ABCD", "")),
        (("AB", "BA"), ("AB", "BA"), ("A", "B", "ABA", "")),
        (("A", "ABA", "ACA"), ("A", "ABA", "ACA", "ABACA"), ("", "B", "AB", "AAB")),
        (("", "AB"), ("", "AB"), ("A", "BA")),
    ],
)
def test_hand_languages(variant, words, accepted, rejected):
    result = mine(*words, variant=variant)
    assert result.status is ComputeStatus.COMPUTED
    for word in accepted:
        assert accepts(result.value, word), (variant, words, word, result)
    for word in rejected:
        assert not accepts(result.value, word), (variant, words, word, result)


@pytest.mark.parametrize("variant", ["im", "imf", "imd"])
def test_empty_population_is_not_a_population_of_empty_cases(variant):
    assert mine(variant=variant).status is ComputeStatus.UNAVAILABLE
    assert mine("", "", variant=variant).value.operator == "tau"


def test_imf_empty_frequency_is_not_variant_frequency():
    # 1/10 is exactly the exclusion boundary; 2/10 is retained.
    excluded = mine(*(["A"] * 9 + [""]), variant="imf", noise_threshold=0.1)
    retained = mine(*(["A"] * 8 + [""] * 2), variant="imf", noise_threshold=0.1)
    assert not accepts(excluded.value, "")
    assert accepts(retained.value, "")
    assert accepts(excluded.value, "A")
    assert any(i.code == "inductive_empty_filter" for i in excluded.issues)
    # Proportion changes from 1/10 to 1/2 if multiplicity is incorrectly dropped.
    assert excluded.value != retained.value


def test_imf_keeps_rare_branch_when_unfiltered_xor_exists():
    result = mine(*(["AB"] * 100 + ["CD"]), variant="imf", noise_threshold=0.9)
    assert accepts(result.value, "CD")
    assert accepts(result.value, "AB")
    assert not any(i.code == "inductive_dfg_filter" for i in result.issues)


def test_imf_actual_filtering_changes_language_and_preserves_fitness_distinction():
    # Strong A->A, one alternating outlier. Removing rare A->B unmasks B;A.
    population = ["AA"] * 20 + ["ABAB"]
    unfiltered = mine(*population, variant="imf", noise_threshold=0)
    filtered = mine(*population, variant="imf", noise_threshold=0.2)
    assert accepts(unfiltered.value, "ABAB")
    assert accepts(filtered.value, "AA")
    assert not accepts(filtered.value, "ABAB")
    assert any(i.code == "inductive_filtered_cut" for i in filtered.issues)
    assert any(i.code == "inductive_dfg_filter" for i in filtered.issues)
    # Original population: 20 fit, one nonfit. Do not claim filtered model
    # fitness against a population from which the one nonfit case was hidden.
    statuses = [accepts(filtered.value, word) for word in population]
    assert (statuses.count(True), statuses.count(False)) == (20, 1)


def test_imf_recursive_frequency_survives_sequence_projection():
    low = mine(*(["AB"] * 9 + ["A"]), variant="imf", noise_threshold=0.1)
    high = mine(*(["AB"] * 8 + ["A"] * 2), variant="imf", noise_threshold=0.1)
    assert not accepts(low.value, "A")
    assert accepts(high.value, "A")
    assert accepts(low.value, "AB")


def dfg_result(*words):
    alphabet = sorted(set("".join(words)))
    edge_counts = Counter(edge for word in words for edge in zip(word, word[1:]))
    value = DirectlyFollowsGraph(
        "case",
        len(words),
        tuple(str(i) for i, word in enumerate(words) if not word),
        tuple(
            ActivityCount(a, sum(word.count(a) for word in words), (), ())
            for a in alphabet
        ),
        tuple(
            DirectlyFollowsEdge(a, b, n, ())
            for (a, b), n in sorted(edge_counts.items())
        ),
        tuple(
            BoundaryCount(
                a,
                tuple(
                    BoundaryEvidence(str(i), f"{i}:0")
                    for i, word in enumerate(words)
                    if word and word[0] == a
                ),
            )
            for a in alphabet
            if any(word and word[0] == a for word in words)
        ),
        tuple(
            BoundaryCount(
                a,
                tuple(
                    BoundaryEvidence(str(i), f"{i}:{len(word) - 1}")
                    for i, word in enumerate(words)
                    if word and word[-1] == a
                ),
            )
            for a in alphabet
            if any(word and word[-1] == a for word in words)
        ),
    )
    return _result(
        "test.dfg",
        None,
        CaseTraceSpec(),
        ComputeStatus.COMPUTED,
        value,
        source_digest="test-source",
    )


@pytest.mark.parametrize(
    "words",
    [
        ("ABC",),
        ("AB", "CD"),
        ("AB", "BA"),
        ("", "AB"),
        ("A", "ABA", "ACA"),
        ("ABC", "A"),
    ],
)
def test_imd_direct_graph_matches_derived_graph_without_synthetic_traces(words):
    direct = discover_inductive_dfg(dfg_result(*words))
    derived = mine(*words, variant="imd")
    assert direct.value == derived.value
    assert direct.parent_computation_ids == (dfg_result(*words).computation_id,)


def test_imd_loses_trace_correlations_explicitly():
    # Both have edges A->X, B->X, X->C, X->D once, starts A/B, ends C/D.
    assert (
        mine("AXC", "BXD", variant="imd").value
        == mine("AXD", "BXC", variant="imd").value
    )


def test_plain_sequence_profile_has_explicit_optional_block_difference():
    result = mine("ABC", "A")
    assert accepts(result.value, "AB")  # independent optional B/C, not joint BC
    assert accepts(result.value, "AC")
    assert "plain-sequence" in next(
        i.message for i in result.issues if i.code == "inductive_profile"
    )


def test_limits_do_not_silently_return_flower():
    limited = mine("ABC", max_depth=1)
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None
    assert any(i.code == "inductive_limit" for i in limited.issues)
    assert not any(i.code == "inductive_flower" for i in limited.issues)
    graph = mine("AA", variant="imd", fallback="unavailable")
    assert graph.status is ComputeStatus.UNAVAILABLE
    explicit = mine("AA", variant="imd", fallback="flower")
    assert explicit.status is ComputeStatus.COMPUTED
    assert any(i.code == "inductive_flower" for i in explicit.issues)


@pytest.mark.parametrize(
    "limits", [{"max_depth": 1}, {"max_nodes": 1}, {"max_nodes": 2}]
)
def test_fallthrough_emitted_tree_obeys_node_and_depth_bounds(limits):
    log_result = mine("AA", variant="imd", **limits)
    graph_result = discover_inductive_dfg(
        dfg_result("AA"), InductiveSpec(variant="imd", **limits)
    )
    for result in (log_result, graph_result):
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert any(i.code == "inductive_limit" for i in result.issues)


def test_spec_is_immutable_validated_and_part_of_identity():
    spec = InductiveSpec()
    with pytest.raises(FrozenInstanceError):
        spec.variant = "imd"
    for kwargs in (
        {"noise_threshold": 0.1},
        {"noise_threshold": float("nan")},
        {"noise_threshold": True},
        {"variant": "imf", "noise_threshold": -1},
        {"max_depth": 0},
        {"max_nodes": True},
        {"variant": "IM"},
    ):
        with pytest.raises((ValueError, TypeError)):
            InductiveSpec(**kwargs)
    base = mine("AB")
    assert base.computation_id != mine("AB", variant="imd").computation_id
    assert base.computation_id != mine("AB", max_depth=64).computation_id
    parent = traces("AB")
    assert base.source_digest == parent.source_digest
    assert base.parent_computation_ids == (parent.computation_id,)


def test_bad_trace_and_upstream_failure_are_not_success():
    parent = traces("AB")
    malformed = replace(
        parent, value=TraceSet("case", (parent.value.traces[0], parent.value.traces[0]))
    )
    assert discover_inductive(malformed).status is ComputeStatus.INVALID_INPUT
    partial = replace(
        parent,
        status=ComputeStatus.PARTIAL,
        issues=(ComputeIssue("limited", "sample"),),
    )
    assert discover_inductive(partial).status is ComputeStatus.UNAVAILABLE
    warning = replace(
        parent, issues=(ComputeIssue("ordering", "source order selected"),)
    )
    assert discover_inductive(warning).issues[0] == warning.issues[0]


def test_direct_graph_rejects_bad_counts_and_missing_boundaries():
    parent = dfg_result("AB")
    malformed = replace(
        parent,
        value=replace(
            parent.value, edges=(replace(parent.value.edges[0], occurrence_count=-1),)
        ),
    )
    assert discover_inductive_dfg(malformed).status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize(
    "alter",
    [
        lambda value: replace(value, object_count=True),
        lambda value: replace(
            value,
            activities=(
                replace(value.activities[0], event_occurrence_count=-1),
                value.activities[1],
            ),
        ),
        lambda value: replace(value, starts=value.starts + value.starts),
        lambda value: replace(value, empty_object_ids=("0",)),
        lambda value: replace(value, activities=(), edges=(), starts=(), ends=()),
        lambda value: replace(
            value, edges=(replace(value.edges[0], occurrence_count=2),)
        ),
        lambda value: replace(
            value, empty_object_ids=("ghost", "ghost"), object_count=3
        ),
    ],
)
def test_direct_graph_rejects_inconsistent_population_and_frequency_evidence(alter):
    parent = dfg_result("AB")
    result = discover_inductive_dfg(replace(parent, value=alter(parent.value)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


def test_direct_graph_empty_cases_require_actual_population_evidence():
    assert discover_inductive_dfg(dfg_result()).status is ComputeStatus.UNAVAILABLE
    assert discover_inductive_dfg(dfg_result("", "")).value.operator == "tau"
    parent = dfg_result("AB")
    malformed = replace(parent, value=replace(parent.value, starts=()))
    assert discover_inductive_dfg(malformed).status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize("variant", ["im", "imf"])
def test_small_exhaustive_observed_language_retained_without_noise(variant):
    words = [
        "".join(letters) for n in range(1, 4) for letters in product("AB", repeat=n)
    ]
    for population in combinations(words, 2):
        result = mine(*population, variant=variant)
        assert result.status is ComputeStatus.COMPUTED
        for word in population:
            assert accepts(result.value, word), (
                variant,
                population,
                word,
                result.value,
            )


def test_imd_graph_relation_fitness_does_not_imply_original_trace_fitness():
    result = mine("A", "BAB", variant="imd")
    assert result.value.operator == "parallel"
    # DFG sees A->B/B->A with both starts and ends, but not the correlation
    # between missing B in the first trace and repeated B in the second one.
    assert accepts(result.value, "AB") and accepts(result.value, "BA")
    assert not accepts(result.value, "A") and not accepts(result.value, "BAB")
