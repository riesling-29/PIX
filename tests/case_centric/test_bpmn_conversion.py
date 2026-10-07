"""Independent token arithmetic and BPMN execution oracles for conversion.

Neither oracle calls PIX firing, replay, alignment, model discovery or the
conversion's witness mappings. Finite expected languages include counterexamples
where graph connectivity does not imply an accepting run.
"""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, dataclass, replace
from itertools import permutations, product

import pytest

from pix.case_centric.bpmn_conversion import (
    RESULT_SCHEMAS,
    BPMNConversionRequest,
    BPMNConversionSpec,
    bpmn_to_petri_net,
)
from pix.case_centric.split_miner import SplitBPMN, SplitBPMNFlow, SplitBPMNNode
from pix.compute._common import _derived_result
from pix.contracts.result import ComputeIssue, ComputeStatus


def bpmn(tasks=(), gateways=(), edges=()):
    nodes = [SplitBPMNNode("s", "start_event"), SplitBPMNNode("e", "end_event")]
    nodes.extend(
        SplitBPMNNode(node_id, "task", activity) for node_id, activity in tasks
    )
    nodes.extend(
        SplitBPMNNode(node_id, kind, direction=direction)
        for node_id, kind, direction in gateways
    )
    flows = tuple(
        SplitBPMNFlow(f"f{i}", source, target)
        for i, (source, target) in enumerate(edges)
    )
    return SplitBPMN(tuple(nodes), flows, "s", "e")


def sequence(labels=("A", "B")):
    ids = [f"t{i}" for i in range(len(labels))]
    path = ["s", *ids, "e"]
    return bpmn(tuple(zip(ids, labels)), edges=tuple(zip(path, path[1:])))


def fork(split="exclusive_gateway", join="exclusive_gateway", labels=("A", "B")):
    ids = [f"t{i}" for i in range(len(labels))]
    return bpmn(
        tuple(zip(ids, labels)),
        (("g1", split, "split"), ("g2", join, "join")),
        (
            ("s", "g1"),
            *(("g1", node) for node in ids),
            *((node, "g2") for node in ids),
            ("g2", "e"),
        ),
    )


def pn_language(net, max_length=6, state_limit=100_000):
    incidences = []
    for transition in net.transitions:
        consumed, produced = Counter(), Counter()
        for arc in net.arcs:
            if arc.target == transition.id:
                consumed[arc.source] += arc.weight
            if arc.source == transition.id:
                produced[arc.target] += arc.weight
        incidences.append((transition.activity, consumed, produced))
    pending = deque([(net.initial_marking.tokens, ())])
    seen, accepted = set(pending), set()
    while pending:
        marking, word = pending.popleft()
        if marking == net.final_marking.tokens:
            accepted.add(word)
        current = Counter(dict(marking))
        for label, consumed, produced in incidences:
            if label is not None and len(word) >= max_length:
                continue
            if any(current[place] < n for place, n in consumed.items()):
                continue
            after = current.copy()
            after.subtract(consumed)
            after.update(produced)
            state = (
                tuple(sorted((p, n) for p, n in after.items() if n)),
                word if label is None else (*word, label),
            )
            if state not in seen:
                seen.add(state)
                assert len(seen) <= state_limit, (
                    "independent P/T oracle exceeded its bound"
                )
                pending.append(state)
    return accepted


def flow_language(model, max_length=6):
    """Execute BPMN nodes directly over sequence-flow token multisets.

    This oracle has no Petri net or conversion-witness knowledge. Start is
    executed once up front; each end occurrence consumes a token and increments
    completion count. Complete process-instance acceptance requires one end and
    no remaining work. Node semantics are evaluated directly at each state.
    """
    entering = {
        node.id: tuple(f.id for f in model.flows if f.target == node.id)
        for node in model.nodes
    }
    leaving = {
        node.id: tuple(f.id for f in model.flows if f.source == node.id)
        for node in model.nodes
    }
    initial = (tuple((flow, 1) for flow in leaving[model.start_id]), 0, ())
    pending, seen, accepted = deque([initial]), {initial}, set()
    while pending:
        marking, completed, word = pending.popleft()
        if completed == 1 and not marking:
            accepted.add(word)
        tokens = Counter(dict(marking))
        for node in model.nodes:
            if (
                node.kind == "start_event"
                or node.kind == "task"
                and len(word) >= max_length
            ):
                continue
            incoming, outgoing = entering[node.id], leaving[node.id]
            if node.kind == "exclusive_gateway":
                # Exactly one enabled input and one selected output for XOR.
                options = (
                    ((i,), (o,)) for i in incoming if tokens[i] for o in outgoing
                )
            elif all(tokens[i] for i in incoming):
                options = ((incoming, outgoing),)
            else:
                options = ()
            for consume, produce in options:
                after = tokens.copy()
                after.subtract(consume)
                after.update(produce)
                state = (
                    tuple(sorted((f, n) for f, n in after.items() if n)),
                    completed + int(node.kind == "end_event"),
                    (*word, node.activity) if node.kind == "task" else word,
                )
                if state not in seen:
                    seen.add(state)
                    assert len(seen) <= 100_000, (
                        "independent BPMN oracle exceeded its bound"
                    )
                    pending.append(state)
    return accepted


def checked(model, expected=None, length=6):
    result = bpmn_to_petri_net(model)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value is not None
    actual = pn_language(result.value.model, length)
    assert actual == flow_language(model, length)
    if expected is not None:
        assert actual == expected
    return result


@pytest.mark.parametrize(
    "labels", [(), ("A",), ("A", "B"), ("A", "A"), ("승인", "완료"), ("τ", "tau")]
)
def test_sequence_empty_duplicate_and_unicode_labels(labels):
    result = checked(sequence(labels), {labels})
    visible = [t for t in result.value.model.transitions if t.activity is not None]
    assert len(visible) == len(labels)
    assert len({t.id for t in visible}) == len(labels)


@pytest.mark.parametrize("labels", [("A", "B"), ("A", "A"), ("A", "B", "C")])
def test_xor_selects_one_branch(labels):
    checked(fork(labels=labels), {(label,) for label in labels})


@pytest.mark.parametrize("labels", [("A", "B"), ("A", "A"), ("A", "B", "C")])
def test_and_executes_every_branch_in_every_interleaving(labels):
    checked(
        fork("parallel_gateway", "parallel_gateway", labels), set(permutations(labels))
    )


@pytest.mark.parametrize(
    "split,join",
    [
        ("exclusive_gateway", "parallel_gateway"),
        ("parallel_gateway", "exclusive_gateway"),
    ],
)
def test_connected_graph_can_deadlock_or_leave_multiple_sink_tokens(split, join):
    result = checked(fork(split, join), set())
    assert result.value.soundness == "not_checked"
    assert result.value.reference_equivalence == "unverified"


def test_nested_choice_inside_parallel():
    model = bpmn(
        (("a", "A"), ("b", "B"), ("c", "C")),
        (
            ("ps", "parallel_gateway", "split"),
            ("pj", "parallel_gateway", "join"),
            ("xs", "exclusive_gateway", "split"),
            ("xj", "exclusive_gateway", "join"),
        ),
        (
            ("s", "ps"),
            ("ps", "a"),
            ("a", "pj"),
            ("ps", "xs"),
            ("xs", "b"),
            ("xs", "c"),
            ("b", "xj"),
            ("c", "xj"),
            ("xj", "pj"),
            ("pj", "e"),
        ),
    )
    checked(model, {("A", "B"), ("B", "A"), ("A", "C"), ("C", "A")})


def test_optional_branch_is_silent_bypass():
    model = bpmn(
        (("a", "A"),),
        (("xs", "exclusive_gateway", "split"), ("xj", "exclusive_gateway", "join")),
        (("s", "xs"), ("xs", "a"), ("a", "xj"), ("xs", "xj"), ("xj", "e")),
    )
    checked(model, {(), ("A",)})


@pytest.mark.parametrize("length", [1, 2, 3, 4, 5, 6])
def test_xor_cycle_is_retained_without_unfolding(length):
    model = bpmn(
        (("a", "A"), ("b", "B")),
        (("j", "exclusive_gateway", "join"), ("x", "exclusive_gateway", "split")),
        (("s", "j"), ("j", "a"), ("a", "x"), ("x", "b"), ("b", "j"), ("x", "e")),
    )
    checked(
        model,
        {
            ("A",) + ("B", "A") * repeats
            for repeats in range(length)
            if 1 + 2 * repeats <= length
        },
        length,
    )


def test_silent_gateway_cycle_does_not_create_visible_activity():
    model = bpmn(
        gateways=(
            ("j", "exclusive_gateway", "join"),
            ("x", "exclusive_gateway", "split"),
        ),
        edges=(("s", "j"), ("j", "x"), ("x", "j"), ("x", "e")),
    )
    checked(model, {()})


@pytest.mark.parametrize(
    "split,join,labels",
    tuple(
        product(
            ("exclusive_gateway", "parallel_gateway"),
            ("exclusive_gateway", "parallel_gateway"),
            (("A", "B"), ("A", "A"), ("A", "B", "C")),
        )
    ),
)
def test_witness_incidence_preserves_every_flow_and_node(split, join, labels):
    model = fork(split, join, labels)
    value = checked(model).value
    places = {row.flow_id: row.place_id for row in value.flow_places}
    assert set(places) == {f.id for f in model.flows}
    assert len(set(places.values())) == len(model.flows)
    assert {row.node_id for row in value.node_transitions} == {
        node.id for node in model.nodes
    }
    transitions = {t.id: t for t in value.model.transitions}
    assert set(transitions) == {row.transition_id for row in value.node_transitions}
    for witness in value.node_transitions:
        node = next(n for n in model.nodes if n.id == witness.node_id)
        assert transitions[witness.transition_id].activity == node.activity
        incident_in = {
            arc.source
            for arc in value.model.arcs
            if arc.target == witness.transition_id
        }
        incident_out = {
            arc.target
            for arc in value.model.arcs
            if arc.source == witness.transition_id
        }
        if node.kind == "start_event":
            incident_in -= dict(value.model.initial_marking.tokens).keys()
        if node.kind == "end_event":
            incident_out -= dict(value.model.final_marking.tokens).keys()
        assert incident_in == {places[f] for f in witness.incoming_flow_ids}
        assert incident_out == {places[f] for f in witness.outgoing_flow_ids}


@pytest.mark.parametrize(
    "kind",
    [
        "inclusive_gateway",
        "event_based_gateway",
        "terminate_end_event",
        "timer_start_event",
        "subprocess",
        "multi_instance_task",
    ],
)
def test_unsupported_bpmn_elements_are_rejected_by_source_contract(kind):
    with pytest.raises(ValueError, match="unsupported BPMN node kind"):
        SplitBPMNNode("unsupported", kind)


@pytest.mark.parametrize("kind", ["exclusive_gateway", "parallel_gateway"])
def test_mixed_gateway_is_rejected(kind):
    with pytest.raises(ValueError, match="split/join direction"):
        SplitBPMNNode("mixed", kind, direction="mixed")


def test_task_implicit_split_is_rejected():
    with pytest.raises(ValueError, match="each task one incoming/outgoing"):
        bpmn(
            (("a", "A"), ("b", "B"), ("c", "C")),
            (("j", "exclusive_gateway", "join"),),
            (("s", "a"), ("a", "b"), ("a", "c"), ("b", "j"), ("c", "j"), ("j", "e")),
        )


def test_disconnected_cycle_is_rejected_instead_of_dropped():
    with pytest.raises(ValueError, match="start-to-end path"):
        bpmn((("a", "A"), ("b", "B")), edges=(("s", "e"), ("a", "b"), ("b", "a")))


@pytest.mark.parametrize("field", ["max_net_nodes", "max_net_arcs"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "100", None])
def test_limits_are_positive_integer_contracts(field, value):
    with pytest.raises(ValueError):
        BPMNConversionSpec(**{field: value})


@pytest.mark.parametrize(
    "model",
    [sequence(()), sequence(), fork(), fork("parallel_gateway", "parallel_gateway")],
)
def test_construction_budget_exact_boundary(model):
    baseline = bpmn_to_petri_net(model)
    net = baseline.value.model
    exact = BPMNConversionSpec(len(net.places) + len(net.transitions), len(net.arcs))
    result = bpmn_to_petri_net(model, exact)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value == baseline.value
    for spec in (
        replace(exact, max_net_nodes=exact.max_net_nodes - 1),
        replace(exact, max_net_arcs=exact.max_net_arcs - 1),
    ):
        limited = bpmn_to_petri_net(model, spec)
        assert limited.status is ComputeStatus.UNAVAILABLE
        assert limited.value is None
        assert limited.source_digest == baseline.source_digest
        assert limited.spec.model_digest == baseline.spec.model_digest
        assert limited.issues[-1].code == "bpmn_conversion_limit"


def test_model_content_and_parameters_participate_in_identity():
    a = bpmn_to_petri_net(sequence(("A",)))
    b = bpmn_to_petri_net(sequence(("B",)))
    changed_limit = bpmn_to_petri_net(
        sequence(("A",)), BPMNConversionSpec(max_net_nodes=100)
    )
    assert a == bpmn_to_petri_net(sequence(("A",)))
    assert a.source_digest == a.value.source_model_digest == a.spec.model_digest
    assert a.source_digest != b.source_digest
    assert a.computation_id != b.computation_id
    assert a.source_digest == changed_limit.source_digest
    assert a.computation_id != changed_limit.computation_id


def test_record_order_does_not_change_constructed_net_but_artifact_identity_is_explicit():
    model = fork("parallel_gateway", "parallel_gateway")
    a = bpmn_to_petri_net(model)
    b = bpmn_to_petri_net(
        replace(
            model,
            nodes=tuple(reversed(model.nodes)),
            flows=tuple(reversed(model.flows)),
        )
    )
    assert a.value.model == b.value.model
    assert a.value.flow_places == b.value.flow_places
    assert a.value.node_transitions == b.value.node_transitions
    assert a.source_digest != b.source_digest


@dataclass(frozen=True)
class ParentSpec:
    parameter: int = 1


@dataclass(frozen=True)
class ModelPayload:
    model: SplitBPMN


def parent(value, status=ComputeStatus.COMPUTED, source="original-log"):
    return _derived_result(
        "test.bpmn-parent",
        source,
        ParentSpec(),
        status,
        value,
        (ComputeIssue("upstream-diagnostic", "retained upstream issue"),),
    )


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("status", [ComputeStatus.COMPUTED, ComputeStatus.PARTIAL])
def test_parent_source_issue_identity_and_partial_status_are_preserved(wrapped, status):
    model = sequence()
    upstream = parent(ModelPayload(model) if wrapped else model, status)
    result = bpmn_to_petri_net(upstream)
    assert result.status is status
    assert result.source_digest == upstream.source_digest
    assert result.parent_computation_ids == (upstream.computation_id,)
    assert result.issues[0] == upstream.issues[0]
    assert result.spec.model_digest == bpmn_to_petri_net(model).source_digest


def test_same_parent_request_different_models_do_not_collide():
    a = bpmn_to_petri_net(parent(sequence(("A",))))
    b = bpmn_to_petri_net(parent(sequence(("B",))))
    assert a.parent_computation_ids == b.parent_computation_ids
    assert a.source_digest == b.source_digest
    assert a.computation_id != b.computation_id


@pytest.mark.parametrize(
    "status", [ComputeStatus.UNAVAILABLE, ComputeStatus.INVALID_INPUT]
)
@pytest.mark.parametrize("source", [None, "source-log"])
def test_failed_parent_propagates_without_inventing_model(status, source):
    upstream = parent(None, status, source)
    result = bpmn_to_petri_net(upstream)
    assert result.status is status
    assert result.source_digest == source
    assert result.value is None
    assert result.issues == upstream.issues
    assert result.spec.model_digest is None


@pytest.mark.parametrize("value", [("not", "a model"), "BPMN XML", 123])
def test_wrong_parent_payload_is_invalid(value):
    result = bpmn_to_petri_net(parent(value))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[-1].code == "invalid_bpmn_model"


@pytest.mark.parametrize("value", [None, {}, "<bpmn/>", sequence().nodes])
def test_bare_untyped_input_is_rejected(value):
    with pytest.raises(TypeError):
        bpmn_to_petri_net(value)


def test_forged_bpmn_is_revalidated():
    model = sequence()
    object.__setattr__(model.nodes[2], "kind", "inclusive_gateway")
    result = bpmn_to_petri_net(model)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


def test_invalid_spec_and_frozen_result():
    with pytest.raises(TypeError):
        bpmn_to_petri_net(sequence(), {})
    result = bpmn_to_petri_net(sequence())
    with pytest.raises(FrozenInstanceError):
        result.value.profile = "changed"
    with pytest.raises(FrozenInstanceError):
        result.spec.model_digest = "changed"


def test_registered_shape_and_nested_codec_roundtrip():
    from pix.results import _decode, _encode

    result = bpmn_to_petri_net(fork("parallel_gateway", "parallel_gateway"))
    kind, request_type, value_type = RESULT_SCHEMAS[result.operator_id]
    assert kind == "bpmn-conversion"
    assert request_type is BPMNConversionRequest
    assert _decode(_encode(result.spec), request_type) == result.spec
    assert _decode(_encode(result.value), value_type) == result.value


@pytest.mark.parametrize("operator", ["sequence", "xor", "parallel", "loop"])
@pytest.mark.parametrize("labels", [("A", "B"), (None, "A"), (None, None), ("A", "A")])
def test_tree_bpmn_petri_pipeline_preserves_denoted_language_and_provenance(
    operator, labels
):
    from pix.case_centric.model_conversion import tree_to_bpmn
    from pix.contracts.discovery import ProcessTree

    left, right = tuple(() if label is None else (label,) for label in labels)
    if operator == "sequence":
        expected = {left + right}
    elif operator == "xor":
        expected = {left, right}
    elif operator == "parallel":
        expected = set(permutations(left + right))
    else:
        expected = {
            left + (right + left) * n
            for n in range(5)
            if len(left + (right + left) * n) <= 4
        }
    tree = ProcessTree(
        operator,
        children=tuple(
            ProcessTree("tau") if label is None else ProcessTree("activity", label)
            for label in labels
        ),
    )
    intermediate = tree_to_bpmn(tree)
    converted = bpmn_to_petri_net(intermediate)
    assert converted.status is ComputeStatus.COMPUTED
    assert pn_language(converted.value.model, 4) == expected
    assert flow_language(intermediate.value.model, 4) == expected
    assert converted.source_digest == intermediate.source_digest
    assert converted.parent_computation_ids == (intermediate.computation_id,)
    assert (
        converted.spec.model_digest
        == bpmn_to_petri_net(intermediate.value.model).source_digest
    )
