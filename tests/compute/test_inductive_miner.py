"""Public, log-based IM checks with independent language and marking oracles.

The test data comes from OCEL event/object facts. Expected languages below are
hand specified or enumerated from operator semantics, not obtained from a
reference miner. No PM4Py/OCPA code is imported or executed by this suite.
"""

from collections import Counter, defaultdict, deque
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from itertools import combinations, product

import pytest

from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.discovery import DiscoverySpec, ProcessTree
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

IM = "pix.im.v1"
LEGACY = "pix.inductive_cut.v1"
EPOCH = datetime(2026, 2, 1, tzinfo=timezone.utc)


def _ocel(traces):
    return OCEL(
        event_types=tuple(EventType(a) for a in sorted(set("".join(traces)))),
        object_types=(ObjectType("case"),),
        objects=tuple(Object(f"case-{i}", "case") for i in range(len(traces))),
        events=tuple(
            Event(f"event-{i}-{j}", activity, EPOCH + timedelta(seconds=j))
            for i, trace in enumerate(traces)
            for j, activity in enumerate(trace)
        ),
        e2o=tuple(
            E2O(f"event-{i}-{j}", f"case-{i}", "process")
            for i, trace in enumerate(traces)
            for j in range(len(trace))
        ),
    )


def _mine(*traces, algorithm=IM, **kwargs):
    upstream = reconstruct_traces(_ocel(traces), TraceSpec("case"))
    assert upstream.status is ComputeStatus.COMPUTED
    return discover_process_tree(upstream, DiscoverySpec(algorithm=algorithm, **kwargs))


def _steps(net, tokens):
    counts = dict(tokens)
    for transition in net.transitions:
        consumed = {a.source: a.weight for a in net.arcs if a.target == transition.id}
        if any(counts.get(place, 0) < count for place, count in consumed.items()):
            continue
        after = Counter(counts)
        after.subtract(consumed)
        after.update(
            {a.target: a.weight for a in net.arcs if a.source == transition.id}
        )
        yield (
            transition,
            tuple(sorted((place, count) for place, count in after.items() if count)),
        )


def _accepts(net, word):
    initial = (net.initial_marking.tokens, 0)
    queue, seen = deque([initial]), {initial}
    while queue:
        tokens, offset = queue.popleft()
        if tokens == net.final_marking.tokens and offset == len(word):
            return True
        for transition, after in _steps(net, tokens):
            if transition.activity is None:
                following = offset
            elif offset < len(word) and word[offset] == transition.activity:
                following = offset + 1
            else:
                continue
            state = after, following
            if state not in seen:
                assert len(seen) < 5000, "finite acceptance oracle limit reached"
                seen.add(state)
                queue.append(state)
    return False


def _net_language(net, maximum):
    initial = net.initial_marking.tokens, ""
    queue, seen, accepted = deque([initial]), {initial}, set()
    while queue:
        tokens, word = queue.popleft()
        if tokens == net.final_marking.tokens:
            accepted.add(word)
        for transition, after in _steps(net, tokens):
            following = word + (transition.activity or "")
            state = after, following
            if len(following) <= maximum and state not in seen:
                assert len(seen) < 30000, "finite language oracle limit reached"
                seen.add(state)
                queue.append(state)
    return accepted


def _sound(net):
    """Finite full reachability, option to complete, proper completion, no dead transitions."""
    initial, final = net.initial_marking.tokens, net.final_marking.tokens
    sink = dict(final).keys()
    queue, seen, fired = [initial], {initial}, set()
    reverse = defaultdict(set)
    while queue:
        tokens = queue.pop()
        if any(place in sink for place, _ in tokens):
            assert tokens == final, "final-place token coexists with unfinished work"
        for transition, after in _steps(net, tokens):
            fired.add(transition.id)
            reverse[after].add(tokens)
            if after not in seen:
                assert len(seen) < 2000, "finite soundness oracle limit reached"
                seen.add(after)
                queue.append(after)
    assert final in seen
    can_finish, queue = {final}, [final]
    while queue:
        for previous in reverse[queue.pop()] - can_finish:
            can_finish.add(previous)
            queue.append(previous)
    assert can_finish == seen
    assert fired == {transition.id for transition in net.transitions}
    assert not tuple(_steps(net, final))


@lru_cache(maxsize=None)
def _shuffle(left, right):
    if not left:
        return frozenset((right,))
    if not right:
        return frozenset((left,))
    return frozenset(
        {left[0] + suffix for suffix in _shuffle(left[1:], right)}
        | {right[0] + suffix for suffix in _shuffle(left, right[1:])}
    )


def _tree_language(tree, maximum):
    """Separate compositional bounded semantics; no conversion or miner helpers."""
    if tree.operator == "tau":
        return {""}
    if tree.operator == "activity":
        return {tree.activity} if maximum else set()
    child_languages = [_tree_language(child, maximum) for child in tree.children]
    if tree.operator == "xor":
        return set.union(*child_languages)
    if tree.operator in ("sequence", "parallel"):
        language = {""}
        for child in child_languages:
            language = {
                word
                for left in language
                for right in child
                for word in (
                    (left + right,)
                    if tree.operator == "sequence"
                    else _shuffle(left, right)
                )
                if len(word) <= maximum
            }
        return language
    body, redo = child_languages
    language = set(body)
    while True:
        following = language | {
            prefix + repeat + suffix
            for prefix in language
            for repeat in redo
            for suffix in body
            if len(prefix + repeat + suffix) <= maximum
        }
        if following == language:
            return language
        language = following


def _leaf(label):
    return ProcessTree("activity", label)


def _node(operator, *children):
    return ProcessTree(operator, children=children)


def _alphabet(tree):
    if tree.operator == "activity":
        return {tree.activity}
    return {activity for child in tree.children for activity in _alphabet(child)}


def _root_issues(result):
    return [issue for issue in result.issues if issue.at == ("recursive_cut",)]


@pytest.mark.parametrize(
    ("observations", "root", "maximum", "expected"),
    [
        (("ABC",), "sequence", 4, {"ABC"}),
        (("AB", "CD"), "xor", 4, {"AB", "CD"}),
        (("AB", "BA"), "parallel", 4, {"AB", "BA"}),
        (("ABC", "ACB", "CAB"), "parallel", 4, {"ABC", "ACB", "CAB"}),
        (("AB", "ABRAB"), "loop", 6, {"AB", "ABRAB"}),
        (("", "AB"), "xor", 4, {"", "AB"}),
        (("A", "AAA"), "loop", 4, {"A", "AA", "AAA", "AAAA"}),
        (("", "A", "AAA"), "xor", 4, {"", "A", "AA", "AAA", "AAAA"}),
        (("",), "tau", 4, {""}),
    ],
)
def test_hand_specified_cut_and_base_case_languages(
    observations, root, maximum, expected
):
    result = _mine(*observations)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == root
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, maximum) == expected
    _sound(net)


def test_named_profiles_preserve_default_and_separate_request_identities():
    assert DiscoverySpec().algorithm == LEGACY
    named = DiscoverySpec(algorithm=IM)
    assert named.algorithm == IM
    with pytest.raises(FrozenInstanceError):
        named.algorithm = LEGACY
    legacy = _mine("ABC", algorithm=LEGACY)
    modern = _mine("ABC")
    assert legacy.value == modern.value
    assert legacy.source_digest == modern.source_digest
    assert legacy.parent_computation_ids == modern.parent_computation_ids
    assert legacy.computation_id != modern.computation_id
    assert legacy.operator_version == "1.0.0"


def test_legacy_flower_language_and_tree_remain_backwards_compatible():
    result = _mine("AB", "ACBCA", algorithm=LEGACY)
    assert result.value == _node(
        "loop", _node("xor", _leaf("A"), _leaf("B"), _leaf("C")), ProcessTree("tau")
    )
    assert [issue.code for issue in result.issues] == ["flower_fallthrough"]
    net = process_tree_to_petri_net(result.value)
    assert not _accepts(net, "")
    assert all(_accepts(net, word) for word in ("A", "B", "C", "BA", "ACBCA"))


def test_sequence_with_optional_middle_keeps_observed_order_and_all_traces():
    result = _mine("ABD", "ABCD", "ACD")
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "sequence"
    net = process_tree_to_petri_net(result.value)
    for word in ("ABD", "ABCD", "ACD"):
        assert _accepts(net, word)
    for word in ("", "DABC", "ABDC", "DCBA", "BACD"):
        assert not _accepts(net, word)
    _sound(net)


def test_parallel_boundary_merging_retains_a_parallel_decomposition():
    # All cross-label DFG directions occur, but C is neither an observed start
    # nor an end. A full parallel cut can repair candidate groups. The final
    # tree may flatten child parallel fallthroughs, so its exact grouping is
    # deliberately not used as evidence of which internal cut path was taken.
    result = _mine("ACBA", "BCAB")
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "parallel"
    assert _alphabet(result.value) == set("ABC")
    assert not _root_issues(result), (
        "the root parallel cut must not require a fallthrough"
    )
    net = process_tree_to_petri_net(result.value)
    assert _accepts(net, "ACBA")
    assert _accepts(net, "BCAB")
    assert not _accepts(net, "")
    _sound(net)


@pytest.mark.parametrize(
    "observations",
    [
        ("AQA", "BQA", "ARA", "ARB", "BRA", "BRB"),
        ("AQA", "AQB", "ARA", "ARB", "BRA", "BRB"),
    ],
)
def test_loop_completeness_merges_only_the_incompatible_redo_component(observations):
    # Q misses one start/exit boundary combination, while R has both. Treating
    # Q as an independent redo branch would claim stronger restart behavior.
    result = _mine(*observations)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "loop"
    do, redo = result.value.children
    assert _alphabet(do) == set("ABQ")
    assert _alphabet(redo) == {"R"}
    net = process_tree_to_petri_net(result.value)
    for word in observations:
        assert _accepts(net, word)
    _sound(net)


def test_loop_do_merges_forward_and_backward_internal_components():
    # A -> X and Y -> E place X/Y inside do; E -> R -> A remains the redo.
    result = _mine("AXAEYERAE")
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "loop"
    do, redo = result.value.children
    assert _alphabet(do) == set("AXEY")
    assert _alphabet(redo) == {"R"}
    expected = _node(
        "loop",
        _node(
            "sequence",
            _node("loop", _leaf("A"), _leaf("X")),
            _node("loop", _leaf("E"), _leaf("Y")),
        ),
        _leaf("R"),
    )
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, 6) == _tree_language(expected, 6)
    assert _accepts(net, "AXAEYERAE")
    _sound(net)


def test_separate_loop_redo_components_are_alternatives_not_a_sequence():
    result = _mine("ABC", "ABCRABC", "ABCSABC")
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "loop"
    assert _alphabet(result.value.children[0]) == set("ABC")
    assert result.value.children[1].operator == "xor"
    assert _alphabet(result.value.children[1]) == {"R", "S"}
    net = process_tree_to_petri_net(result.value)
    for word in ("ABC", "ABCRABC", "ABCSABC", "ABCRABCSABC"):
        assert _accepts(net, word)
    for word in ("ABCRSABC", "ABCS", "RABC", ""):
        assert not _accepts(net, word)
    _sound(net)


def test_once_per_trace_fallthrough_can_recover_independent_activities():
    # The observed directed three-cycle has no structural cut, but all three
    # activities occur once in each trace; removing A exposes B || C.
    result = _mine("ABC", "CAB")
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "parallel"
    assert [issue.code for issue in _root_issues(result)] == [
        "im_activity_once_fallthrough"
    ]
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, 4) == {"ABC", "ACB", "BAC", "BCA", "CAB", "CBA"}
    _sound(net)


def test_activity_removal_reveals_concurrency_without_once_per_trace_activity():
    observations = ("AABCC", "CABB")
    assert all(
        not all(word.count(activity) == 1 for word in observations)
        for activity in "ABC"
    )
    result = _mine(*observations)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.operator == "parallel"
    assert [issue.code for issue in _root_issues(result)] == [
        "im_activity_concurrent_fallthrough"
    ]
    net = process_tree_to_petri_net(result.value)
    expected = {
        "".join(word)
        for length in (3, 4)
        for word in product("ABC", repeat=length)
        if set(word) == set("ABC")
    }
    assert _net_language(net, 4) == expected
    assert all(_accepts(net, word) for word in observations)
    _sound(net)


def test_strict_tau_loop_reconstructs_repeated_complete_blocks():
    result = _mine("ABAB")
    assert result.status is ComputeStatus.COMPUTED
    assert [issue.code for issue in _root_issues(result)] == ["im_tau_loop_fallthrough"]
    assert "strict" in _root_issues(result)[0].message
    expected = _node(
        "loop", _node("sequence", _leaf("A"), _leaf("B")), ProcessTree("tau")
    )
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, 6) == _tree_language(expected, 6)
    _sound(net)


def test_general_tau_loop_splits_internal_starts_without_strict_end_start_edges():
    observation = "ABACBABC"
    assert "CA" not in observation
    result = _mine(observation)
    assert result.status is ComputeStatus.COMPUTED
    assert [issue.code for issue in _root_issues(result)] == ["im_tau_loop_fallthrough"]
    assert "general" in _root_issues(result)[0].message
    expected = _node(
        "loop",
        _node(
            "sequence",
            _leaf("A"),
            _node("parallel", _leaf("B"), _node("xor", _leaf("C"), ProcessTree("tau"))),
        ),
        ProcessTree("tau"),
    )
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, 6) == _tree_language(expected, 6)
    assert _accepts(net, observation)
    _sound(net)


@pytest.mark.parametrize("include_empty", [False, True])
def test_irreducible_im_flower_includes_epsilon_and_reports_generalization(
    include_empty,
):
    # A bipartite six-cycle with no complete sequence relation. Removing one
    # activity still leaves a connected incomplete relation, so no structural
    # cut is exposed. No trace has an internal start and no label occurs in all.
    observations = ("AD", "AE", "BE", "BF", "CF", "CD")
    if include_empty:
        observations = ("", *observations)
    result = _mine(*observations)
    assert result.status is ComputeStatus.COMPUTED
    assert any("flower" in issue.code for issue in result.issues)
    net = process_tree_to_petri_net(result.value)
    assert _net_language(net, 2) == {""} | {
        "".join(word) for length in (1, 2) for word in product("ABCDEF", repeat=length)
    }
    _sound(net)


def test_same_log_collection_permutations_are_deterministic():
    log = _ocel(("ABC", "ACB", "CAB", "ABC"))
    permuted = replace(
        log,
        events=log.events[::-1],
        event_types=log.event_types[::-1],
        objects=log.objects[::-1],
        e2o=log.e2o[::-1],
    )
    spec = DiscoverySpec(algorithm=IM)
    first = discover_process_tree(reconstruct_traces(log, TraceSpec("case")), spec)
    second = discover_process_tree(
        reconstruct_traces(permuted, TraceSpec("case")), spec
    )
    assert first == second
    assert process_tree_to_petri_net(first.value) == process_tree_to_petri_net(
        second.value
    )


def test_im_uses_selected_qualified_traces_and_keeps_canonical_source_identity():
    original = _ocel(("ABC", "ABC"))
    log = replace(
        original,
        e2o=tuple(
            replace(relation, qualifier="audit")
            if relation.event == "event-0-1"
            else relation
            for relation in original.e2o
        ),
    )
    whole = reconstruct_traces(log, TraceSpec("case"))
    selected = reconstruct_traces(log, TraceSpec("case", qualifiers=("process",)))
    none = reconstruct_traces(log, TraceSpec("case", qualifiers=()))
    spec = DiscoverySpec(algorithm=IM)
    complete_model = discover_process_tree(whole, spec)
    selected_model = discover_process_tree(selected, spec)
    silent_model = discover_process_tree(none, spec)
    assert (
        complete_model.source_digest
        == selected_model.source_digest
        == silent_model.source_digest
    )
    assert complete_model.parent_computation_ids == (whole.computation_id,)
    assert selected_model.parent_computation_ids == (selected.computation_id,)
    assert complete_model.computation_id != selected_model.computation_id
    assert not _accepts(process_tree_to_petri_net(complete_model.value), "AC")
    assert _accepts(process_tree_to_petri_net(selected_model.value), "AC")
    assert _accepts(process_tree_to_petri_net(selected_model.value), "ABC")
    assert silent_model.value == ProcessTree("tau")
    assert len(log.events) == len(log.e2o) == 6


@pytest.mark.parametrize(
    "source_tree",
    [
        _node("sequence", _leaf("A"), _node("xor", _leaf("B"), _leaf("C")), _leaf("D")),
        _node("parallel", _node("sequence", _leaf("A"), _leaf("B")), _leaf("C")),
        _node(
            "loop",
            _node("sequence", _leaf("A"), _leaf("B")),
            _node("xor", _leaf("R"), _leaf("S")),
        ),
        _node(
            "sequence",
            _leaf("A"),
            _node("parallel", _leaf("B"), _node("xor", _leaf("C"), ProcessTree("tau"))),
            _leaf("D"),
        ),
        _node(
            "parallel",
            _node("loop", _leaf("A"), _leaf("R")),
            _node("xor", _leaf("B"), ProcessTree("tau")),
        ),
    ],
)
def test_bounded_structured_languages_are_preserved_by_discovery(source_tree):
    observations = tuple(sorted(_tree_language(source_tree, 5)))
    assert observations
    result = _mine(*observations)
    assert result.status is ComputeStatus.COMPUTED
    net = process_tree_to_petri_net(result.value)
    for word in observations:
        assert _accepts(net, word), (word, result.value)
    _sound(net)


def test_all_ternary_pairs_up_to_length_four_retain_observed_behavior():
    # 7,260 pairs including epsilon. This verifies zero-noise fitting only;
    # it does not infer precision, rediscoverability, or reference output parity.
    words = [""] + [
        "".join(word)
        for length in range(1, 5)
        for word in product("ABC", repeat=length)
    ]
    for observations in combinations(words, 2):
        result = _mine(*observations)
        assert result.status is ComputeStatus.COMPUTED, (observations, result.issues)
        net = process_tree_to_petri_net(result.value)
        for word in observations:
            assert _accepts(net, word), (observations, word, result.value)


def test_im_depth_limit_is_explicit_and_does_not_return_a_partial_tree():
    result = _mine("ABC", max_depth=1)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(issue.code == "discovery_depth_limit" for issue in result.issues)


@pytest.mark.parametrize("noise", [0.1, -1, float("inf"), float("nan")])
def test_im_profile_does_not_accept_unimplemented_filtering(noise):
    with pytest.raises(ValueError):
        DiscoverySpec(algorithm=IM, noise_threshold=noise)
