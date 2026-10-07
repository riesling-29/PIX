"""BPMN XML profile preserves control-flow semantics or explicitly refuses it."""

from collections import Counter, deque
from dataclasses import replace
from hashlib import sha256
from xml.etree.ElementTree import SubElement, fromstring, tostring

import pytest

from pix.case_centric.bpmn_conversion import bpmn_to_petri_net
from pix.case_centric.split_miner import (
    SplitBPMN,
    SplitBPMNFlow,
    SplitBPMNNode,
    split_bpmn_xml,
)
from pix.model_io.bpmn import NAMESPACE, dumps_bpmn, loads_bpmn
from pix.model_io.common import ModelIOError, XMLLimits


def _tag(name):
    return f"{{{NAMESPACE}}}{name}"


def _parallel(labels=("A", "B")):
    nodes = (
        SplitBPMNNode("start", "start_event"),
        SplitBPMNNode("split", "parallel_gateway", direction="split"),
        SplitBPMNNode("left", "task", labels[0]),
        SplitBPMNNode("right", "task", labels[1]),
        SplitBPMNNode("join", "parallel_gateway", direction="join"),
        SplitBPMNNode("end", "end_event"),
    )
    edges = (
        ("start", "split"),
        ("split", "left"),
        ("split", "right"),
        ("left", "join"),
        ("right", "join"),
        ("join", "end"),
    )
    return SplitBPMN(
        nodes,
        tuple(SplitBPMNFlow(f"flow_{n}", a, b) for n, (a, b) in enumerate(edges)),
        "start",
        "end",
    )


def _xml():
    return fromstring(split_bpmn_xml(_parallel()))


def _payload(root):
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _language(net, max_length=3):
    """Small independent P/T execution oracle; no conversion witness assumptions."""
    transitions = []
    for transition in net.transitions:
        consume, produce = Counter(), Counter()
        for arc in net.arcs:
            if arc.target == transition.id:
                consume[arc.source] += arc.weight
            if arc.source == transition.id:
                produce[arc.target] += arc.weight
        transitions.append((transition.activity, consume, produce))
    initial = (net.initial_marking.tokens, ())
    pending, visited, accepted = deque([initial]), {initial}, set()
    while pending:
        marking, word = pending.popleft()
        if marking == net.final_marking.tokens:
            accepted.add(word)
        for activity, consume, produce in transitions:
            current = Counter(dict(marking))
            if (activity is not None and len(word) >= max_length) or any(
                current[p] < count for p, count in consume.items()
            ):
                continue
            current.subtract(consume)
            current.update(produce)
            next_state = (
                tuple(sorted((p, n) for p, n in current.items() if n)),
                word if activity is None else (*word, activity),
            )
            if next_state not in visited:
                visited.add(next_state)
                assert len(visited) < 10_000
                pending.append(next_state)
    return accepted


@pytest.mark.parametrize(
    "labels", [("A", "B"), ("same", "same"), ('검토 <&"', "승인\n완료")]
)
def test_existing_writer_import_and_export_roundtrip_preserves_model(labels):
    model = _parallel(labels)
    original = split_bpmn_xml(model)
    parsed = loads_bpmn(original)
    assert parsed.model == model
    assert parsed.format == "bpmn" and parsed.format_version == "2.0"
    assert parsed.profile == "pix.bpmn2.xor-and"
    assert parsed.source_sha256 == sha256(original.encode("utf-8")).hexdigest()
    assert loads_bpmn(dumps_bpmn(parsed)).model == model
    assert loads_bpmn(dumps_bpmn(model)).model == model
    assert dumps_bpmn(model) == dumps_bpmn(model)


def test_parallel_import_executes_both_branches_in_either_order():
    parsed = loads_bpmn(dumps_bpmn(_parallel()))
    net = bpmn_to_petri_net(parsed.model).value.model
    language = _language(net)
    assert language == {("A", "B"), ("B", "A")}
    assert ("A",) not in language and ("B",) not in language


def test_exclusive_import_preserves_choice_instead_of_parallelism():
    model = _parallel()
    model = replace(
        model,
        nodes=tuple(
            replace(n, kind="exclusive_gateway") if n.kind == "parallel_gateway" else n
            for n in model.nodes
        ),
    )
    net = bpmn_to_petri_net(loads_bpmn(dumps_bpmn(model)).model).value.model
    assert _language(net) == {("A",), ("B",)}


@pytest.mark.parametrize("declaration", [None, "Unspecified"])
def test_gateway_direction_can_be_inferred_from_unambiguous_degree(declaration):
    root = _xml()
    for node in root[0].findall(_tag("parallelGateway")):
        if declaration is None:
            del node.attrib["gatewayDirection"]
        else:
            node.set("gatewayDirection", declaration)
    assert loads_bpmn(_payload(root)).model == _parallel()


def test_explicit_reference_children_are_optional_and_flow_order_is_retained():
    root = _xml()
    for node in root[0]:
        for child in list(node):
            node.remove(child)
    assert loads_bpmn(_payload(root)).model == _parallel()
    model = _parallel()
    reversed_model = replace(model, flows=tuple(reversed(model.flows)))
    assert loads_bpmn(dumps_bpmn(reversed_model)).model == reversed_model


@pytest.mark.parametrize("tag", ["incoming", "outgoing"])
@pytest.mark.parametrize(
    "change",
    [
        "unknown",
        "duplicate",
        "other",
        "missing_one",
        "nested",
        "attribute",
        "wrong_namespace",
    ],
)
def test_reference_declarations_must_match_actual_sequence_flows(tag, change):
    root = _xml()
    node = (
        root[0].find(_tag("parallelGateway"))
        if tag == "outgoing"
        else root[0].findall(_tag("parallelGateway"))[1]
    )
    references = node.findall(_tag(tag))
    reference = references[0]
    if change == "unknown":
        reference.text = "missing"
    elif change == "duplicate":
        SubElement(node, _tag(tag)).text = reference.text
    elif change == "other":
        reference.text = "flow_0"
    elif change == "missing_one":
        node.remove(reference)
    elif change == "nested":
        SubElement(reference, _tag("task"))
    elif change == "attribute":
        reference.set("unknown", "value")
    else:
        reference.tag = "{https://wrong.example/}outgoing"
    with pytest.raises(ModelIOError):
        loads_bpmn(_payload(root))


@pytest.mark.parametrize(
    "feature",
    [
        "inclusiveGateway",
        "eventBasedGateway",
        "subProcess",
        "boundaryEvent",
        "intermediateCatchEvent",
        "callActivity",
        "sendTask",
        "receiveTask",
        "userTask",
        "dataObjectReference",
        "laneSet",
        "extensionElements",
    ],
)
def test_unsupported_process_elements_are_rejected_without_dropping(feature):
    root = _xml()
    SubElement(root[0], _tag(feature), {"id": "unsupported"})
    with pytest.raises(ModelIOError, match="unsupported child"):
        loads_bpmn(_payload(root))


@pytest.mark.parametrize(
    "owner,feature",
    [
        ("task", "multiInstanceLoopCharacteristics"),
        ("task", "standardLoopCharacteristics"),
        ("startEvent", "timerEventDefinition"),
        ("endEvent", "terminateEventDefinition"),
        ("sequenceFlow", "conditionExpression"),
        ("task", "extensionElements"),
    ],
)
def test_semantic_children_are_rejected(owner, feature):
    root = _xml()
    SubElement(root[0].find(_tag(owner)), _tag(feature))
    with pytest.raises(ModelIOError) as error:
        loads_bpmn(_payload(root))
    assert error.value.code == "unsupported_feature"


@pytest.mark.parametrize(
    "owner,name,value",
    [
        ("parallelGateway", "default", "flow_1"),
        ("parallelGateway", "gatewayDirection", "Mixed"),
        ("task", "isForCompensation", "true"),
        ("startEvent", "isInterrupting", "false"),
        ("sequenceFlow", "{https://vendor.example/}priority", "1"),
    ],
)
def test_semantic_attributes_are_rejected(owner, name, value):
    root = _xml()
    root[0].find(_tag(owner)).set(name, value)
    with pytest.raises(ModelIOError):
        loads_bpmn(_payload(root))


@pytest.mark.parametrize(
    "feature", ["BPMNDiagram", "collaboration", "message", "process"]
)
def test_extra_document_content_is_rejected(feature):
    root = _xml()
    namespace = (
        "http://www.omg.org/spec/BPMN/20100524/DI"
        if feature == "BPMNDiagram"
        else NAMESPACE
    )
    SubElement(root, f"{{{namespace}}}{feature}", {"id": "other"})
    with pytest.raises(ModelIOError):
        loads_bpmn(_payload(root))


@pytest.mark.parametrize(
    "change",
    [
        "duplicate_node",
        "duplicate_flow",
        "container_collision",
        "invalid_id",
        "missing_id",
        "unknown_endpoint",
        "flow_endpoint",
        "false_direction",
        "executable",
        "missing_namespace",
        "wrong_namespace",
        "blank_label",
        "mixed_text",
    ],
)
def test_malformed_or_ambiguous_control_flow_is_rejected(change):
    root = _xml()
    process = root[0]
    task = process.find(_tag("task"))
    flow = process.find(_tag("sequenceFlow"))
    if change == "duplicate_node":
        task.set("id", "start")
    elif change == "duplicate_flow":
        flow.set("id", "left")
    elif change == "container_collision":
        root.set("id", process.attrib["id"])
    elif change == "invalid_id":
        task.set("id", "1 invalid")
    elif change == "missing_id":
        del task.attrib["id"]
    elif change == "unknown_endpoint":
        flow.set("sourceRef", "missing")
    elif change == "flow_endpoint":
        flow.set("targetRef", "flow_1")
    elif change == "false_direction":
        process.find(_tag("parallelGateway")).set("gatewayDirection", "Converging")
    elif change == "executable":
        process.set("isExecutable", "true")
    elif change == "missing_namespace":
        root.tag = "definitions"
    elif change == "wrong_namespace":
        task.tag = "{https://wrong.example/}task"
    elif change == "blank_label":
        task.set("name", " ")
    else:
        process.text = "unexpected behavior"
    with pytest.raises(ModelIOError):
        loads_bpmn(_payload(root))


def test_wrapper_preserves_container_ids_and_explicit_display_metadata():
    root = _xml()
    root.set("id", "DefinitionsSource")
    root.set("exporter", "A source tool")
    root.set("name", "A source document")
    root[0].set("id", "ProcessSource")
    root[0].set("name", "Display process")
    root[0].find(_tag("startEvent")).set("name", "Start display")
    root[0].find(_tag("sequenceFlow")).set("name", "Flow display")
    parsed = loads_bpmn(_payload(root))
    assert ("definitions", "DefinitionsSource") in parsed.source_ids
    assert ("process", "ProcessSource") in parsed.source_ids
    assert "startEvent:start@name" in parsed.presentation_ignored
    again = loads_bpmn(dumps_bpmn(parsed))
    assert again.model == parsed.model
    assert again.metadata == parsed.metadata
    assert again.source_ids == parsed.source_ids
    assert again.presentation_ignored == parsed.presentation_ignored


def test_reserved_container_words_can_be_real_node_ids_without_metadata_collision():
    model = _parallel()
    model = replace(
        model,
        nodes=tuple(
            replace(n, id="process") if n.id == "left" else n for n in model.nodes
        ),
        flows=tuple(
            replace(
                f,
                source="process" if f.source == "left" else f.source,
                target="process" if f.target == "left" else f.target,
            )
            for f in model.flows
        ),
    )
    parsed = loads_bpmn(dumps_bpmn(model))
    assert loads_bpmn(dumps_bpmn(parsed)).model == model


@pytest.mark.parametrize(
    "field,value",
    [
        ("format", "pnml"),
        ("profile", "unknown"),
        ("format_version", "2.1"),
        ("profile_version", "9.0.0"),
        ("source_ids", (("definitions", "left"),)),
        ("metadata", (("process@isExecutable", "true"),)),
        ("metadata", (("task:left@name", "changed"),)),
        ("metadata", (("unknown@name", "missing"),)),
    ],
)
def test_forged_wrapper_cannot_inject_semantics_or_colliding_ids(field, value):
    parsed = replace(loads_bpmn(dumps_bpmn(_parallel())), **{field: value})
    with pytest.raises(ModelIOError):
        dumps_bpmn(parsed)


def test_writer_revalidates_mutated_model_and_xml_characters():
    model = _parallel()
    object.__setattr__(model.nodes[2], "activity", "control\x01character")
    with pytest.raises(ModelIOError):
        dumps_bpmn(model)
    model = _parallel()
    object.__setattr__(model.flows[0], "target", "unknown")
    with pytest.raises(ModelIOError):
        dumps_bpmn(model)


@pytest.mark.parametrize(
    "limits",
    [XMLLimits(max_bytes=20), XMLLimits(max_elements=3), XMLLimits(max_depth=2)],
)
def test_xml_limits_apply_before_a_model_is_returned(limits):
    with pytest.raises(ModelIOError) as error:
        loads_bpmn(dumps_bpmn(_parallel()), limits=limits)
    assert error.value.code == "resource_limit"


def test_no_external_entity_resolution_and_no_wrong_input_types():
    with pytest.raises(ModelIOError) as error:
        loads_bpmn(b'<!DOCTYPE definitions SYSTEM "file:///secret"><definitions/>')
    assert error.value.code == "unsafe_xml"
    with pytest.raises(TypeError):
        loads_bpmn({})
    with pytest.raises(TypeError):
        dumps_bpmn("<definitions/>")


def test_large_sequential_model_preserves_all_identities():
    task_count = 1500
    ids = ["start", *(f"task_{i}" for i in range(task_count)), "end"]
    model = SplitBPMN(
        (
            SplitBPMNNode("start", "start_event"),
            *(
                SplitBPMNNode(identity, "task", f"Activity {index}")
                for index, identity in enumerate(ids[1:-1])
            ),
            SplitBPMNNode("end", "end_event"),
        ),
        tuple(
            SplitBPMNFlow(f"flow_{i}", source, target)
            for i, (source, target) in enumerate(zip(ids, ids[1:]))
        ),
        "start",
        "end",
    )
    assert loads_bpmn(dumps_bpmn(model)).model == model
