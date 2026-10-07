from collections import Counter, deque
from dataclasses import dataclass
from itertools import product

import pytest

from pix.case_centric.model_conversion import (
    TreeConversionSpec,
    tree_to_bpmn,
    tree_to_powl,
)
from pix.case_centric.powl import powl_to_petri_net
from pix.compute.discovery import discover_process_tree
from pix.contracts.discovery import DiscoverySpec, ProcessTree
from pix.contracts.result import ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def a(label):
    return ProcessTree("activity", label)


def op(kind, *children):
    return ProcessTree(kind, children=tuple(children))


TAU = ProcessTree("tau")
TREES = (
    TAU,
    a("A"),
    op("sequence", a("A"), a("B")),
    op("xor", a("A"), a("B")),
    op("parallel", a("A"), a("B")),
    op("loop", a("A"), a("B")),
    op("loop", a("A"), TAU),
    op("loop", TAU, a("B")),
    op("loop", TAU, TAU),
    op("xor", TAU, TAU),
    op("xor", a("A"), a("A"), TAU, TAU),
    op("sequence", TAU, a("A"), TAU, a("B")),
    op("parallel", TAU, TAU, a("A")),
    op("parallel", a("A"), a("A")),
    op("sequence", a("A"), op("parallel", a("B"), a("C")), a("D")),
    op("parallel", op("xor", TAU, a("A")), op("loop", a("B"), a("C"))),
)


def shuffle(left, right):
    if not left:
        return {right}
    if not right:
        return {left}
    return {(left[0],) + rest for rest in shuffle(left[1:], right)} | {
        (right[0],) + rest for rest in shuffle(left, right[1:])
    }


def tree_words(tree, bound=4):
    if tree.operator == "tau":
        return {()}
    if tree.operator == "activity":
        return {(tree.activity,)}
    languages = [tree_words(c, bound) for c in tree.children]
    if tree.operator == "xor":
        return set.union(*languages)
    if tree.operator in ("sequence", "parallel"):
        result = {()}
        for language in languages:
            result = {
                word
                for left, right in product(result, language)
                if len(left) + len(right) <= bound
                for word in (
                    [left + right]
                    if tree.operator == "sequence"
                    else shuffle(left, right)
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


def bpmn_words(model, bound=4):
    """Direct BPMN sequence-flow token oracle, independent of PN conversion."""
    incoming, outgoing = {}, {}
    for node in model.nodes:
        incoming[node.id] = tuple(f.id for f in model.flows if f.target == node.id)
        outgoing[node.id] = tuple(f.id for f in model.flows if f.source == node.id)
    initial = tuple((f, 1) for f in outgoing[model.start_id])
    final = tuple((f, 1) for f in incoming[model.end_id])
    pending, seen, accepted = deque([(initial, ())]), {(initial, ())}, set()
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        counts = dict(marking)
        for node in model.nodes:
            if node.kind in ("start_event", "end_event"):
                continue
            ins, outs = incoming[node.id], outgoing[node.id]
            input_sets = (
                [(f,) for f in ins]
                if node.kind == "exclusive_gateway" and node.direction == "join"
                else [ins]
            )
            output_sets = (
                [(f,) for f in outs]
                if node.kind == "exclusive_gateway" and node.direction == "split"
                else [outs]
            )
            for consumed, produced in product(input_sets, output_sets):
                if not all(counts.get(f, 0) for f in consumed):
                    continue
                extended = word + ((node.activity,) if node.kind == "task" else ())
                if len(extended) > bound:
                    continue
                after = Counter(counts)
                after.subtract(consumed)
                after.update(produced)
                state = (tuple(sorted((f, n) for f, n in after.items() if n)), extended)
                if state not in seen:
                    seen.add(state)
                    pending.append(state)
    return accepted


def petri_words(net, bound=4):
    """Direct weighted-arc vector oracle, independent of PIX firing helpers."""
    incoming, outgoing = {}, {}
    for t in net.transitions:
        incoming[t.id] = {
            edge.source: edge.weight for edge in net.arcs if edge.target == t.id
        }
        outgoing[t.id] = {
            edge.target: edge.weight for edge in net.arcs if edge.source == t.id
        }
    initial, final = net.initial_marking.tokens, net.final_marking.tokens
    pending, seen, accepted = deque([(initial, ())]), {(initial, ())}, set()
    while pending:
        marking, word = pending.popleft()
        if marking == final:
            accepted.add(word)
        counts = dict(marking)
        for transition in net.transitions:
            inputs, outputs = incoming[transition.id], outgoing[transition.id]
            if not all(
                counts.get(place, 0) >= weight for place, weight in inputs.items()
            ):
                continue
            extended = word + (
                (transition.activity,) if transition.activity is not None else ()
            )
            if len(extended) > bound:
                continue
            after = Counter(counts)
            after.subtract(inputs)
            after.update(outputs)
            state = tuple(sorted((p, n) for p, n in after.items() if n)), extended
            if state not in seen:
                seen.add(state)
                pending.append(state)
    return accepted


@pytest.mark.parametrize("tree", TREES)
def test_tree_bpmn_language_matches_independent_tree_denotation(tree):
    converted = tree_to_bpmn(tree)
    assert converted.status == ComputeStatus.COMPUTED
    assert bpmn_words(converted.value.model) == tree_words(tree)


@pytest.mark.parametrize("tree", TREES)
def test_tree_powl_language_matches_independent_tree_denotation(tree):
    converted = tree_to_powl(tree)
    assert converted.status == ComputeStatus.COMPUTED
    assert petri_words(powl_to_petri_net(converted.value.model)) == tree_words(tree)


@pytest.mark.parametrize("tree", TREES)
def test_tree_bpmn_petri_chain_keeps_language_and_provenance(tree):
    from pix.case_centric.bpmn_conversion import bpmn_to_petri_net

    bpmn = tree_to_bpmn(tree)
    converted = bpmn_to_petri_net(bpmn)
    assert converted.status == ComputeStatus.COMPUTED
    assert converted.source_digest == bpmn.source_digest
    assert converted.parent_computation_ids == (bpmn.computation_id,)
    assert petri_words(converted.value.model) == tree_words(tree)


def test_powl_sequence_total_order_and_parallel_empty_order():
    sequential = tree_to_powl(op("sequence", a("A"), a("B"), a("C"))).value.model
    concurrent = tree_to_powl(op("parallel", a("A"), a("B"), a("C"))).value.model
    assert sequential.kind == concurrent.kind == "partial_order"
    assert sequential.order == ((0, 1), (0, 2), (1, 2))
    assert concurrent.order == ()


def test_bpmn_duplicate_visible_labels_remain_distinct_and_tau_is_not_a_task():
    result = tree_to_bpmn(op("xor", a("A"), a("A"), TAU, TAU)).value
    tasks = [n for n in result.model.nodes if n.kind == "task"]
    assert len(tasks) == 2
    assert tasks[0].id != tasks[1].id
    assert all(task.activity == "A" for task in tasks)
    assert len(result.activity_nodes) == 2
    assert "duplicate_epsilon_choice_removed" in {step.rule for step in result.steps}


@pytest.mark.parametrize("convert", [tree_to_bpmn, tree_to_powl])
def test_tree_limits_return_no_truncated_model(convert):
    result = convert(
        op("sequence", a("A"), a("B")), TreeConversionSpec(max_tree_nodes=2)
    )
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_exact_output_limits_and_order_pair_budget():
    source = op("sequence", a("A"), a("B"))
    model = tree_to_bpmn(source).value.model
    exact = TreeConversionSpec(
        max_output_nodes=len(model.nodes), max_output_flows=len(model.flows)
    )
    assert tree_to_bpmn(source, exact).status == ComputeStatus.COMPUTED
    assert (
        tree_to_bpmn(
            source, TreeConversionSpec(max_output_flows=len(model.flows) - 1)
        ).status
        == ComputeStatus.UNAVAILABLE
    )
    assert (
        tree_to_powl(
            op("sequence", a("A"), a("B"), a("C")),
            TreeConversionSpec(max_order_pairs=2),
        ).status
        == ComputeStatus.UNAVAILABLE
    )
    assert (
        tree_to_powl(
            op("parallel", a("A"), a("B")),
            TreeConversionSpec(max_partial_order_children=1),
        ).status
        == ComputeStatus.UNAVAILABLE
    )


@pytest.mark.parametrize("convert", [tree_to_bpmn, tree_to_powl])
def test_deep_tree_is_reported_by_conversion_budget_not_artifact_codec(convert):
    model = a("A")
    for _ in range(70):
        model = op("sequence", model, a("B"))
    result = convert(model)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.source_digest is not None


def test_source_digest_matches_native_model_artifact():
    from pix.models import model_document

    model = op("sequence", a("A"), op("parallel", a("B"), a("C")))
    assert tree_to_powl(model).source_digest == model_document(model)["model_digest"]


@pytest.mark.parametrize("convert", [tree_to_bpmn, tree_to_powl])
def test_parent_provenance_and_failed_input(convert):
    log = CaseLog(
        (
            CaseTrace(
                "c", (CaseEvent("e", (CaseAttribute("concept:name", "string", "A"),)),)
            ),
        )
    )
    parent = discover_process_tree(case_traces(log), DiscoverySpec())
    result = convert(parent)
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)
    failed = case_traces(CaseLog((CaseTrace("bad", (CaseEvent("missing"),)),)))
    unavailable = convert(failed)
    assert unavailable.value is None
    assert unavailable.status == failed.status
    assert unavailable.parent_computation_ids == (failed.computation_id,)


@pytest.mark.parametrize("convert", [tree_to_bpmn, tree_to_powl])
def test_incomplete_conversion_without_released_tree_stays_unavailable(convert):
    from pix.compute._common import _derived_result
    from pix.contracts.result import ComputeIssue

    @dataclass(frozen=True)
    class NoReleasedTree:
        model: ProcessTree | None = None

    parent = _derived_result(
        "test.incomplete-conversion",
        "test:model",
        TreeConversionSpec(),
        ComputeStatus.PARTIAL,
        NoReleasedTree(),
        (ComputeIssue("budget", "No tree was released"),),
    )
    result = convert(parent)
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)


@pytest.mark.parametrize("kind", ["sequence", "xor", "parallel", "loop"])
@pytest.mark.parametrize("target", ["bpmn", "powl"])
def test_certified_workflow_net_to_bpmn_or_powl_pipeline(kind, target):
    from pix.case_centric.wfnet_conversion import wfnet_to_process_tree
    from pix.compute.discovery import process_tree_to_petri_net

    original = op(kind, a("A"), a("B"))
    reduced = wfnet_to_process_tree(process_tree_to_petri_net(original))
    assert reduced.status == ComputeStatus.COMPUTED
    assert reduced.value.certificate.comparison.equivalent is True
    result = (tree_to_bpmn if target == "bpmn" else tree_to_powl)(reduced)
    assert result.status == ComputeStatus.COMPUTED
    assert result.source_digest == reduced.source_digest
    assert result.parent_computation_ids == (reduced.computation_id,)
    language = (
        bpmn_words(result.value.model)
        if target == "bpmn"
        else petri_words(powl_to_petri_net(result.value.model))
    )
    assert language == tree_words(original)


@pytest.mark.parametrize("kind", ["sequence", "xor", "parallel", "loop"])
def test_bpmn_to_powl_through_certified_workflow_conversion(kind):
    from pix.case_centric.bpmn_conversion import bpmn_to_petri_net
    from pix.case_centric.wfnet_conversion import wfnet_to_process_tree

    original = op(kind, a("A"), a("B"))
    bpmn = tree_to_bpmn(original)
    net = bpmn_to_petri_net(bpmn)
    tree_result = wfnet_to_process_tree(net)
    assert tree_result.status == ComputeStatus.COMPUTED
    assert tree_result.value.certificate.comparison.equivalent is True
    converted = tree_to_powl(tree_result)
    assert converted.status == ComputeStatus.COMPUTED
    assert converted.source_digest == bpmn.source_digest
    assert converted.parent_computation_ids == (tree_result.computation_id,)
    assert petri_words(powl_to_petri_net(converted.value.model)) == tree_words(original)


@pytest.mark.parametrize("convert", [tree_to_bpmn, tree_to_powl])
def test_codec_roundtrip_preserves_nested_models_and_witnesses(convert, monkeypatch):
    from pix import results
    from pix.case_centric.model_conversion import RESULT_SCHEMAS

    original = results._schemas
    monkeypatch.setattr(results, "_schemas", lambda: {**original(), **RESULT_SCHEMAS})
    result = convert(op("sequence", a("A"), op("parallel", a("B"), a("B"))))
    assert results.result_from_json(results.result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "kwargs", [{"max_depth": 49}, {"max_tree_nodes": True}, {"max_output_nodes": 0}]
)
def test_invalid_budgets(kwargs):
    with pytest.raises(ValueError):
        TreeConversionSpec(**kwargs)
