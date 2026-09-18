"""Strict BPMN 2.0 XML exchange for PIX's explicit XOR/AND control flow.

One process with one plain start/end event, atomic tasks, and exclusive or
parallel split/join gateways is supported. Sequence-flow order, node/flow IDs,
and task labels are retained. An omitted/Unspecified gateway direction is
inferred only when the actual degree is unambiguous. Optional incoming and
outgoing references, when present, must agree with sequence flows.

Conditions, defaults, event definitions, subprocesses, multi-instance behavior,
extensions, collaboration, and diagram interchange are rejected. Decorative
names outside tasks and document metadata are explicitly reported as ignored;
process/definitions IDs are retained as source provenance, not model identity.
Import validates this profile, not BPMN soundness or complete schema compliance.
"""

from __future__ import annotations

import re
from collections import Counter
from xml.etree.ElementTree import Element, SubElement

from pix.case_centric.split_miner import (
    SplitBPMN,
    SplitBPMNFlow,
    SplitBPMNNode,
)

from .common import (
    ParsedModel,
    XMLLimits,
    fail,
    local,
    parse_xml,
    source_digest,
    xml_bytes,
)

FORMAT = "bpmn"
PROFILE = "pix.bpmn2.xor-and"
NAMESPACE = "http://www.omg.org/spec/BPMN/20100524/MODEL"
_KINDS = {
    "startEvent": "start_event",
    "endEvent": "end_event",
    "task": "task",
    "exclusiveGateway": "exclusive_gateway",
    "parallelGateway": "parallel_gateway",
}
_ID = re.compile(r"[^\W\d][\w.-]*", re.UNICODE)


def _check(element: Element, attributes: set[str], children: set[str]) -> None:
    """Check fully qualified tags and attributes, not merely local names."""
    if element.tag != f"{{{NAMESPACE}}}{local(element)}":
        fail(
            FORMAT,
            "BPMN elements require the BPMN 2.0 MODEL namespace",
            element=local(element),
        )
    unknown = set(element.attrib) - attributes
    if unknown:
        fail(
            FORMAT,
            f"unsupported attributes: {', '.join(sorted(unknown))}",
            element=local(element),
        )
    if element.text and element.text.strip():
        fail(
            FORMAT,
            "unexpected element text",
            element=local(element),
            code="invalid_structure",
        )
    for child in element:
        if (
            child.tag != f"{{{NAMESPACE}}}{local(child)}"
            or local(child) not in children
        ):
            fail(FORMAT, f"unsupported child {child.tag}", element=local(element))
        if child.tail and child.tail.strip():
            fail(
                FORMAT,
                "unexpected text after child",
                element=local(element),
                code="invalid_structure",
            )


def _identifier(value: str | None, element: str) -> str:
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        fail(
            FORMAT,
            "identifiers must be nonempty unqualified XML names",
            element=element,
            code="invalid_id",
        )
    return value


def loads_bpmn(payload: bytes | str, *, limits: XMLLimits = XMLLimits()) -> ParsedModel:
    """Read a declared, bounded BPMN 2.0 control-flow profile.

    Display metadata is listed in ``presentation_ignored``. Execution-related
    attributes and elements outside the supported profile never disappear
    silently. Explicit ``isExecutable=true`` is rejected because this profile
    neither represents nor guarantees execution-engine semantics.
    """
    root = parse_xml(payload, FORMAT, limits)
    if root.tag != f"{{{NAMESPACE}}}definitions":
        fail(
            FORMAT,
            "expected BPMN 2.0 definitions root",
            element=local(root),
            code="invalid_structure",
        )
    _check(
        root,
        {"id", "name", "targetNamespace", "exporter", "exporterVersion"},
        {"process"},
    )
    if len(root) != 1:
        fail(
            FORMAT,
            "exactly one process is required",
            element="definitions",
            code="invalid_structure",
        )
    if not root.get("targetNamespace", "").strip():
        fail(
            FORMAT,
            "definitions require targetNamespace",
            element="definitions",
            code="invalid_structure",
        )
    process = root[0]
    _check(process, {"id", "name", "isExecutable"}, {*_KINDS, "sequenceFlow"})
    if process.get("isExecutable", "false") not in ("false", "0"):
        fail(
            FORMAT,
            "only a non-executable control-flow process is supported",
            element="process",
        )

    ids: dict[str, str] = {}
    source_ids: list[tuple[str, str]] = []
    ignored: list[str] = []
    retained_metadata: list[tuple[str, str]] = []

    def register(element: Element) -> str:
        kind = local(element)
        value = _identifier(element.get("id"), kind)
        if value in ids:
            fail(
                FORMAT, f"duplicate XML ID {value!r}", element=kind, code="duplicate_id"
            )
        ids[value] = kind
        source_ids.append((kind, value))
        return value

    def metadata(element: Element, names: tuple[str, ...]) -> None:
        owner = (
            local(element)
            if element in (root, process)
            else f"{local(element)}:{element.attrib['id']}"
        )
        for name in names:
            if name in element.attrib:
                key = f"{owner}@{name}"
                ignored.append(key)
                retained_metadata.append((key, element.attrib[name]))

    if "id" in root.attrib:
        register(root)
    register(process)
    metadata(root, ("name", "targetNamespace", "exporter", "exporterVersion"))
    metadata(process, ("name",))
    flows: list[SplitBPMNFlow] = []
    node_elements: list[Element] = []
    for element in process:
        kind = local(element)
        identity = register(element)
        if kind == "sequenceFlow":
            _check(element, {"id", "sourceRef", "targetRef", "name"}, set())
            source = _identifier(element.get("sourceRef"), kind)
            target = _identifier(element.get("targetRef"), kind)
            flows.append(SplitBPMNFlow(identity, source, target))
            metadata(element, ("name",))
        else:
            allowed = {"id", "name"}
            if kind.endswith("Gateway"):
                allowed.add("gatewayDirection")
            _check(element, allowed, {"incoming", "outgoing"})
            if kind != "task":
                metadata(element, ("name",))
            node_elements.append(element)

    node_ids = {element.attrib["id"] for element in node_elements}
    for flow in flows:
        if flow.source not in node_ids or flow.target not in node_ids:
            fail(
                FORMAT,
                f"flow {flow.id!r} refers to an unknown node",
                element="sequenceFlow",
                code="invalid_reference",
            )
    incoming, outgoing = (
        Counter(f.target for f in flows),
        Counter(f.source for f in flows),
    )
    incoming_refs: dict[str, set[str]] = {value: set() for value in node_ids}
    outgoing_refs: dict[str, set[str]] = {value: set() for value in node_ids}
    for flow in flows:
        incoming_refs[flow.target].add(flow.id)
        outgoing_refs[flow.source].add(flow.id)

    nodes: list[SplitBPMNNode] = []
    for element in node_elements:
        kind, identity = local(element), element.attrib["id"]
        for tag, expected in (
            ("incoming", incoming_refs[identity]),
            ("outgoing", outgoing_refs[identity]),
        ):
            children = [child for child in element if local(child) == tag]
            if not children:
                continue
            actual = []
            for child in children:
                if child.attrib or len(child):
                    fail(
                        FORMAT,
                        "flow references must contain only an ID",
                        element=tag,
                        code="invalid_structure",
                    )
                actual.append(_identifier((child.text or "").strip(), tag))
            if len(set(actual)) != len(actual) or set(actual) != expected:
                fail(
                    FORMAT,
                    f"{tag} references disagree with sequence flows at {identity!r}",
                    element=kind,
                    code="invalid_reference",
                )
        direction = None
        if kind.endswith("Gateway"):
            declared = element.get("gatewayDirection", "Unspecified")
            if declared not in ("Unspecified", "Diverging", "Converging"):
                fail(
                    FORMAT,
                    "only split/join gateway directions are supported",
                    element=kind,
                )
            if declared == "Unspecified":
                degree = incoming[identity], outgoing[identity]
                if degree[0] == 1 and degree[1] >= 2:
                    direction = "split"
                elif degree[0] >= 2 and degree[1] == 1:
                    direction = "join"
                else:
                    fail(
                        FORMAT,
                        "gateway degree does not determine a split or join",
                        element=kind,
                        code="invalid_model",
                    )
            else:
                direction = "split" if declared == "Diverging" else "join"
        try:
            nodes.append(
                SplitBPMNNode(
                    identity,
                    _KINDS[kind],
                    element.get("name") if kind == "task" else None,
                    direction,
                )
            )
        except (TypeError, ValueError) as error:
            fail(FORMAT, str(error), element=kind, code="invalid_model")

    starts = [node.id for node in nodes if node.kind == "start_event"]
    ends = [node.id for node in nodes if node.kind == "end_event"]
    if len(starts) != 1 or len(ends) != 1:
        fail(
            FORMAT,
            "exactly one plain start and end event is required",
            element="process",
            code="invalid_model",
        )
    try:
        model = SplitBPMN(tuple(nodes), tuple(flows), starts[0], ends[0])
    except (TypeError, ValueError) as error:
        fail(FORMAT, str(error), element="process", code="invalid_model")
    return ParsedModel(
        model=model,
        format=FORMAT,
        profile=PROFILE,
        format_version="2.0",
        source_sha256=source_digest(payload),
        source_ids=tuple(source_ids),
        presentation_ignored=tuple(ignored),
        metadata=tuple(retained_metadata),
    )


def dumps_bpmn(model: SplitBPMN | ParsedModel) -> bytes:
    """Export the supported profile as UTF-8 XML, preserving node/flow IDs.

    A ``ParsedModel`` additionally preserves source container IDs and supported
    decorative metadata. A bare ``SplitBPMN`` receives generated container IDs.
    Forged/mutated frozen model values are revalidated before XML is returned.
    """
    parsed = model if isinstance(model, ParsedModel) else None
    if parsed is not None:
        if (
            parsed.format != FORMAT
            or parsed.profile != PROFILE
            or parsed.format_version != "2.0"
            or parsed.profile_version != "1.0.0"
        ):
            fail(
                FORMAT,
                "ParsedModel belongs to a different exchange profile",
                code="invalid_model",
            )
        model = parsed.model
    if type(model) is not SplitBPMN:
        raise TypeError("model must be SplitBPMN")
    try:
        nodes = tuple(
            SplitBPMNNode(n.id, n.kind, n.activity, n.direction) for n in model.nodes
        )
        flows = tuple(SplitBPMNFlow(f.id, f.source, f.target) for f in model.flows)
        validated = SplitBPMN(nodes, flows, model.start_id, model.end_id)
    except (TypeError, ValueError, AttributeError) as error:
        fail(FORMAT, str(error), element="process", code="invalid_model")

    def tag(kind):
        return f"{{{NAMESPACE}}}{kind}"

    # Index incidence once. Scanning every flow for every node would make a
    # valid large model unnecessarily quadratic to export.
    used = {item.id for item in (*validated.nodes, *validated.flows)}
    process_id = "split_process"
    while process_id in used:
        process_id += "_"
    root = Element(tag("definitions"), {"targetNamespace": "https://pix.local/bpmn"})
    process = SubElement(
        root, tag("process"), {"id": process_id, "isExecutable": "false"}
    )
    incoming = {node.id: [] for node in validated.nodes}
    outgoing = {node.id: [] for node in validated.nodes}
    for flow in validated.flows:
        incoming[flow.target].append(flow.id)
        outgoing[flow.source].append(flow.id)
    kinds = {value: key for key, value in _KINDS.items()}
    for node in validated.nodes:
        attributes = {"id": node.id}
        if node.activity is not None:
            attributes["name"] = node.activity
        if node.direction is not None:
            attributes["gatewayDirection"] = (
                "Diverging" if node.direction == "split" else "Converging"
            )
        element = SubElement(process, tag(kinds[node.kind]), attributes)
        for flow_id in incoming[node.id]:
            SubElement(element, tag("incoming")).text = flow_id
        for flow_id in outgoing[node.id]:
            SubElement(element, tag("outgoing")).text = flow_id
    for flow in validated.flows:
        SubElement(
            process,
            tag("sequenceFlow"),
            {"id": flow.id, "sourceRef": flow.source, "targetRef": flow.target},
        )
    if parsed is not None:
        container_ids = {}
        for kind, identity in parsed.source_ids:
            if kind not in ("definitions", "process"):
                continue
            _identifier(identity, kind)
            if kind in container_ids or identity in used:
                fail(
                    FORMAT,
                    "duplicate container identity",
                    element=kind,
                    code="duplicate_id",
                )
            container_ids[kind] = identity
            used.add(identity)
        if "process" in container_ids:
            process.set("id", container_ids["process"])
        if "definitions" in container_ids:
            root.set("id", container_ids["definitions"])
        owners = {
            f"{local(element)}:{element.attrib['id']}": element for element in process
        }
        owners.update({"definitions": root, "process": process})
        seen_metadata = set()
        for key, value in parsed.metadata:
            owner, separator, attribute = key.rpartition("@")
            target = owners.get(owner)
            allowed = (
                {"name", "targetNamespace", "exporter", "exporterVersion"}
                if target is root
                else {"name"}
            )
            if (
                not separator
                or target is None
                or attribute not in allowed
                or key in seen_metadata
            ):
                fail(
                    FORMAT, "invalid source presentation metadata", code="invalid_model"
                )
            if local(target) == "task":
                fail(
                    FORMAT,
                    "task labels belong to the model, not metadata",
                    element="task",
                    code="invalid_model",
                )
            target.set(attribute, value)
            seen_metadata.add(key)
    payload = xml_bytes(root, FORMAT)
    # This also detects metadata/container ID collisions in manually made wrappers.
    loads_bpmn(payload)
    return payload


__all__ = ["dumps_bpmn", "loads_bpmn"]
