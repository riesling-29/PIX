"""Independent BPMN token arithmetic checks finite languages and witnesses."""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
from itertools import permutations
from xml.etree.ElementTree import fromstring

import pytest

from pix.case_centric.split_miner import (
    SplitBPMNFlow,
    SplitBPMNNode,
    SplitMinerSpec,
    _frequency_filter,
    _gateway_tree,
    discover_split_miner,
    split_bpmn_xml,
)
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
                        (CaseAttribute("concept:name", "string", label),),
                    )
                    for index, label in enumerate(word)
                ),
            )
            for case, word in enumerate(words)
        )
    )


def interval_log(*cases):
    epoch = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CaseLog(
        tuple(
            CaseTrace(
                str(case),
                tuple(
                    CaseEvent(
                        f"{case}:{index}",
                        (
                            CaseAttribute("concept:name", "string", label),
                            CaseAttribute(
                                "start_timestamp",
                                "date",
                                epoch + timedelta(seconds=start),
                            ),
                            CaseAttribute(
                                "time:timestamp", "date", epoch + timedelta(seconds=end)
                            ),
                        ),
                    )
                    for index, (label, start, end) in enumerate(intervals)
                ),
            )
            for case, intervals in enumerate(cases)
        )
    )


def language(model, max_length=6, limit=50000):
    """Direct token-on-sequence-flow semantics, without PIX replay/conversion.

    XOR joins consume one incoming token; AND joins consume every incoming.
    XOR splits choose one outgoing; AND splits produce every outgoing.
    Acceptance consumes the final event and leaves no residual tokens.
    """
    assert model is not None
    incoming = {
        n.id: tuple(f.id for f in model.flows if f.target == n.id) for n in model.nodes
    }
    outgoing = {
        n.id: tuple(f.id for f in model.flows if f.source == n.id) for n in model.nodes
    }
    initial = (("INITIAL", 1),)
    agenda, seen, accepted = deque([(initial, ())]), {(initial, ())}, set()
    while agenda:
        marking, word = agenda.popleft()
        if marking == (("FINAL", 1),):
            accepted.add(word)
        current = Counter(dict(marking))
        for node in model.nodes:
            if node.activity is not None and len(word) >= max_length:
                continue
            ins = ("INITIAL",) if node.id == model.start_id else incoming[node.id]
            outs = ("FINAL",) if node.id == model.end_id else outgoing[node.id]
            if node.kind == "exclusive_gateway" and node.direction == "join":
                inputs = [(edge,) for edge in ins]
            else:
                inputs = [ins]
            if node.kind == "exclusive_gateway" and node.direction == "split":
                outputs = [(edge,) for edge in outs]
            else:
                outputs = [outs]
            for consuming in inputs:
                if not consuming or any(current[edge] < 1 for edge in consuming):
                    continue
                for producing in outputs:
                    after = current.copy()
                    after.subtract(consuming)
                    after.update(producing)
                    next_marking = tuple(
                        sorted((edge, count) for edge, count in after.items() if count)
                    )
                    next_word = (
                        word if node.activity is None else (*word, node.activity)
                    )
                    state = (next_marking, next_word)
                    if state not in seen:
                        seen.add(state)
                        assert len(seen) <= limit, (
                            "independent oracle reached its explicit state cap"
                        )
                        agenda.append(state)
    return accepted


@pytest.mark.parametrize(
    "words", [("abcd",), ("abd", "acd"), ("abcd", "acbd"), ((),), ((), "a")]
)
def test_sequence_xor_parallel_and_empty_case_have_hand_defined_languages(words):
    result = discover_split_miner(log(*words))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model) == {tuple(word) for word in words}
    assert result.value.reference_equivalence == "partial_profile"
    assert result.value.soundness == "not_checked"
    assert "bounded_split_profile" in {issue.code for issue in result.issues}


def test_three_way_parallel_has_only_all_six_orders():
    words = ["a" + "".join(order) + "e" for order in permutations("bcd")]
    result = discover_split_miner(log(*words))
    assert language(result.value.model) == {tuple(word) for word in words}
    assert (
        len([n for n in result.value.model.nodes if n.kind == "parallel_gateway"]) == 2
    )


def test_nested_choice_inside_parallel_is_not_flattened_into_or_or_xor():
    words = ("abde", "adbe", "acde", "adce")
    result = discover_split_miner(log(*words))
    assert language(result.value.model) == {tuple(word) for word in words}
    kinds = Counter(n.kind for n in result.value.model.nodes)
    assert kinds["parallel_gateway"] == 2
    assert kinds["exclusive_gateway"] == 2


def test_one_loop_and_two_loop_remain_cycles_not_false_concurrency():
    first = discover_split_miner(log("abbc", "abc"))
    assert language(first.value.model, max_length=6) == {
        tuple("a" + "b" * n + "c") for n in range(1, 5)
    }
    assert first.value.short_loops == (("b",),)
    second = discover_split_miner(log("ababc", "abc"))
    assert language(second.value.model, max_length=7) == {
        tuple("ab" * n + "c") for n in range(1, 4)
    }
    assert second.value.short_loops == (("a", "b"),)
    assert not any(row.selected for row in second.value.concurrency)


def test_frequency_filter_drops_a_rare_shortcut_preserving_every_activity():
    source = log(*(["abcd"] * 10), "acd")
    result = discover_split_miner(source, SplitMinerSpec(frequency_percentile=1))
    assert language(result.value.model) == {tuple("abcd")}
    labels = dict(result.value.activities)
    dropped = [
        (labels.get(edge.source), labels.get(edge.target), edge.count)
        for edge in result.value.edges
        if not edge.retained
    ]
    assert dropped == [("a", "c", 1)]
    assert result.value.frequency_threshold == 11
    # A rare activity remains reachable through the backbone; its frequency
    # alone does not authorize deleting an observed activity.
    rare = discover_split_miner(
        log(*(["abd"] * 10), "acd"), SplitMinerSpec(frequency_percentile=1)
    )
    assert language(rare.value.model) == {tuple("abd"), tuple("acd")}


def test_concurrency_epsilon_comparison_is_strict_at_zero():
    source = log("abcd", "acbd")
    result = discover_split_miner(source, SplitMinerSpec(concurrency_epsilon=0))
    assert not any(row.selected for row in result.value.concurrency)
    normal = discover_split_miner(source)
    assert next(
        row for row in normal.value.concurrency if (row.left, row.right) == ("b", "c")
    ).selected


def test_interval_profile_discovers_parallelism_without_reversed_completion_order():
    source = interval_log((("a", 0, 1), ("b", 2, 5), ("c", 3, 6), ("d", 7, 8)))
    result = discover_split_miner(source, SplitMinerSpec(profile="interval_bounded"))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model) == {tuple("abcd"), tuple("acbd")}
    parallel = next(row for row in result.value.concurrency if row.selected)
    assert (parallel.left, parallel.right, parallel.overlap_count) == ("b", "c", 1)
    assert not parallel.forward_count and not parallel.reverse_count
    assert result.value.interval_comparisons > 0
    # The classic profile has only the one observed order.
    assert language(discover_split_miner(source).value.model) == {tuple("abcd")}


def test_interval_touching_and_zero_duration_events_have_stable_causal_order():
    source = interval_log((("a", 0, 1), ("b", 1, 1), ("c", 1, 1), ("d", 1, 2)))
    result = discover_split_miner(source, SplitMinerSpec(profile="interval_bounded"))
    assert language(result.value.model) == {tuple("abcd")}
    assert not result.value.concurrency


def test_interval_profile_does_not_silently_impute_or_project_missing_attributes():
    spec = SplitMinerSpec(profile="interval_bounded")
    missing = discover_split_miner(log("ab"), spec)
    assert missing.status is ComputeStatus.INVALID_INPUT and missing.value is None
    projected = discover_split_miner(case_traces(log("ab")), spec)
    assert projected.status is ComputeStatus.UNAVAILABLE and projected.value is None
    overlapping = discover_split_miner(interval_log((("a", 0, 4), ("a", 1, 5))), spec)
    assert overlapping.status is ComputeStatus.UNAVAILABLE and overlapping.value is None
    limited = discover_split_miner(
        interval_log((("a", 0, 1), ("b", 2, 3))),
        replace(spec, max_interval_comparisons=1),
    )
    assert limited.status is ComputeStatus.UNAVAILABLE and limited.value is None
    assert "interval_comparison_limit" in {issue.code for issue in limited.issues}


def test_interval_loops_follow_temporal_cover_not_storage_order():
    first = interval_log((("a", 0, 1), ("b", 2, 3), ("a", 4, 5)))
    second = interval_log((("a", 0, 1), ("a", 4, 5), ("b", 2, 3)))
    spec = SplitMinerSpec(profile="interval_bounded")
    left, right = discover_split_miner(first, spec), discover_split_miner(second, spec)
    assert left.value.short_loops == right.value.short_loops == (("a", "b"),)
    assert left.value.edges == right.value.edges
    assert left.value.model == right.value.model


def test_interval_dates_compare_instants_across_dst_folds():
    class FallBack(tzinfo):
        def utcoffset(self, value):
            return timedelta(hours=-5 if value.fold else -4)

        def dst(self, value):
            return timedelta(0)

    zone = FallBack()
    source = CaseLog(
        (
            CaseTrace(
                "case",
                (
                    CaseEvent(
                        "event",
                        (
                            CaseAttribute("concept:name", "string", "a"),
                            CaseAttribute(
                                "start_timestamp",
                                "date",
                                datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0),
                            ),
                            CaseAttribute(
                                "time:timestamp",
                                "date",
                                datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1),
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    result = discover_split_miner(source, SplitMinerSpec(profile="interval_bounded"))
    assert result.status is ComputeStatus.COMPUTED
    assert language(result.value.model) == {("a",)}


def test_frozen_bpmn_contract_rejects_ambiguous_and_dangling_graphs():
    model = discover_split_miner(log("ab")).value.model
    with pytest.raises(TypeError):
        replace(model, nodes=list(model.nodes))
    with pytest.raises(ValueError):
        replace(model, nodes=model.nodes + (model.nodes[0],))
    with pytest.raises(ValueError):
        replace(model, flows=model.flows + (model.flows[0],))
    with pytest.raises(ValueError):
        replace(
            model, flows=(replace(model.flows[0], target="missing"), *model.flows[1:])
        )
    with pytest.raises(ValueError):
        replace(model, start_id="split_task_0")
    with pytest.raises(ValueError):
        replace(model, end_id="missing")
    with pytest.raises(ValueError):
        replace(model, flows=model.flows[1:])
    for values in (
        ("bad id", "task", "a", None),
        ("ok", "task", None, None),
        ("ok", "parallel_gateway", None, None),
        ("ok", "task", "a", "split"),
        ("ok", "start_event", "a", None),
        ("ok", "inclusive_gateway", None, "split"),
    ):
        with pytest.raises(ValueError):
            SplitBPMNNode(*values)
    with pytest.raises(ValueError):
        SplitBPMNFlow("1invalid", "a", "b")


@pytest.mark.parametrize(
    "spec",
    [
        SplitMinerSpec(),
        SplitMinerSpec(frequency_percentile=1),
        SplitMinerSpec(profile="interval_bounded"),
    ],
)
def test_spec_and_payload_result_codec_roundtrip(spec):
    from pix.results import _decode, _encode

    source = interval_log((("a", 0, 1), ("b", 2, 5), ("c", 3, 6), ("d", 7, 8)))
    result = discover_split_miner(source, spec)
    assert _decode(_encode(result.spec), type(result.spec)) == result.spec
    assert _decode(_encode(result.value), type(result.value)) == result.value


def test_prime_relation_cannot_be_mislabeled_as_a_flat_parallel_gateway():
    # The four-vertex path is neither a disjoint union nor a complete join.
    assert _gateway_tree((0, 1, 2, 3), {(0, 1), (1, 2), (2, 3)}) is None
    assert _gateway_tree((0, 1, 2), {(0, 2), (1, 2)}) == (
        "and",
        (("xor", (("leaf", 0), ("leaf", 1))), ("leaf", 2)),
    )
    # Every activity has independent entry/exit evidence. Removing balanced
    # reversals exposes the prime P4 concurrency relation at s and z.
    result = discover_split_miner(
        log("saz", "sbz", "scz", "sdz", "sabz", "sbaz", "sbcz", "scbz", "scdz", "sdcz")
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.model is None
    assert len(result.value.unresolved_gateway_nodes) == 2
    assert "prime_gateway_relation" in {issue.code for issue in result.issues}


def test_deep_gateway_hierarchy_at_default_activity_cap_does_not_use_python_recursion():
    count = SplitMinerSpec().max_activities
    # Alternating isolated/universal vertices create a deeply nested cograph.
    parallel = {(i, j) for i in range(count) for j in range(i + 1, count) if j % 2}
    tree = _gateway_tree(tuple(range(count)), parallel)
    stack, leaves = [tree], set()
    while stack:
        kind, content = stack.pop()
        if kind == "leaf":
            leaves.add(content)
        else:
            stack.extend(content)
    assert leaves == set(range(count))


def test_mixed_interval_causality_is_explicitly_partial():
    source = interval_log((("a", 0, 2), ("b", 1, 3)), (("a", 0, 1), ("b", 2, 3)))
    result = discover_split_miner(source, SplitMinerSpec(profile="interval_bounded"))
    assert result.status is ComputeStatus.PARTIAL
    assert "mixed_interval_relation" in {issue.code for issue in result.issues}
    assert not any(row.selected for row in result.value.concurrency)


def test_filter_backbone_matches_exhaustive_bottleneck_values():
    # A cyclic graph with a tempting high-frequency disconnected cycle.
    weights = {(0, 1): 4, (0, 2): 7, (1, 2): 20, (2, 1): 20, (1, 3): 3, (2, 3): 2}
    kept, threshold, backbone = _frequency_filter(
        weights, set(range(4)), 0, 3, 1, set()
    )
    assert threshold == 20

    def best(edges, begin, end):
        capacities = []

        def walk(node, visited, capacity):
            if node == end:
                capacities.append(capacity)
            for (a, b), frequency in edges.items():
                if a == node and b not in visited:
                    walk(b, visited | {b}, min(capacity, frequency))

        walk(begin, {begin}, sum(edges.values()) + 1)
        return max(capacities)

    preserved = {edge: weights[edge] for edge in kept}
    for node in range(1, 4):
        assert best(preserved, 0, node) == best(weights, 0, node)
    for node in range(3):
        assert best(preserved, node, 3) == best(weights, node, 3)
    assert backbone <= kept


def test_bpmn_xml_is_real_namespace_graph_with_escaped_labels_and_unique_ids():
    source = log(("split_start", 'A<&"', "종료"))
    result = discover_split_miner(source)
    model = result.value.model
    assert language(model) == {("split_start", 'A<&"', "종료")}
    root = fromstring(split_bpmn_xml(model))
    ns = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL"}
    tasks = root.findall(".//b:task", ns)
    assert {task.attrib["name"] for task in tasks} == {"split_start", 'A<&"', "종료"}
    assert len(root.findall(".//b:sequenceFlow", ns)) == len(model.flows)
    assert (
        len(root.findall(".//b:startEvent", ns))
        == len(root.findall(".//b:endEvent", ns))
        == 1
    )
    all_ids = [
        element.attrib["id"] for element in root.iter() if "id" in element.attrib
    ]
    assert len(all_ids) == len(set(all_ids))
    with pytest.raises(FrozenInstanceError):
        model.start_id = "changed"


def test_trace_identity_is_preserved_and_spec_changes_identity():
    raw = log("abcd", "acbd")
    parent = case_traces(raw)
    result = discover_split_miner(parent)
    direct = discover_split_miner(raw)
    assert result.computation_id == direct.computation_id
    assert result.parent_computation_ids == (parent.computation_id,)
    assert result.source_digest == parent.source_digest
    changed = discover_split_miner(raw, SplitMinerSpec(concurrency_epsilon=0.2))
    assert result.computation_id != changed.computation_id
    assert result.value.model == changed.value.model


@pytest.mark.parametrize(
    "kwargs",
    [
        {"profile": "classic"},
        {"profile": "sm2"},
        {"concurrency_epsilon": -0.1},
        {"concurrency_epsilon": float("nan")},
        {"concurrency_epsilon": True},
        {"frequency_percentile": 2},
        {"max_activities": True},
        {"max_interval_comparisons": 0},
        {"profile": "interval_bounded", "frequency_percentile": 0.5},
    ],
)
def test_unsupported_claims_and_invalid_parameters_are_rejected(kwargs):
    with pytest.raises(ValueError):
        SplitMinerSpec(**kwargs)


def test_empty_log_and_resource_limits_do_not_return_a_fake_model():
    assert discover_split_miner(log()).status is ComputeStatus.UNAVAILABLE
    limited = discover_split_miner(log("abc"), SplitMinerSpec(max_activities=2))
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None
    connectivity = discover_split_miner(
        log("abcd", "acbd"), SplitMinerSpec(max_connectivity_edge_visits=1)
    )
    assert connectivity.status is ComputeStatus.UNAVAILABLE
    assert connectivity.value is None
    assert "connectivity_budget" in {issue.code for issue in connectivity.issues}
