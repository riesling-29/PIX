"""PTML exchange for PIX's ordered, binary-loop process trees.

The supported dialect follows the element vocabulary and parent-edge ordering
of PM4Py 2.7.23.8's PTML importer/exporter. This is an independent adapter, with
no PM4Py dependency. A ProM-compatible loop's third child is accepted only when
it is a silent leaf; arbitrary exit behavior is deliberately not rewritten.
"""

from __future__ import annotations

from xml.etree import ElementTree as ET

from pix.contracts.discovery import ProcessTree

from .common import (
    ModelIOError,
    ParsedModel,
    XMLLimits,
    fail,
    local,
    parse_xml,
    source_digest,
    strict,
    xml_bytes,
)

_FORMAT = "ptml"
_PROFILE = "ptml.binary-loop-plus-tau-exit.v1"
_TAGS = {
    "manualTask": "activity",
    "automaticTask": "tau",
    "sequence": "sequence",
    "xor": "xor",
    "and": "parallel",
    "xorLoop": "loop",
}
_REVERSE_TAGS = {value: key for key, value in _TAGS.items()}


def _required(element: ET.Element, attribute: str) -> str:
    value = element.get(attribute)
    if value is None or not value.strip():
        fail(
            _FORMAT,
            f"{local(element)} requires a nonblank {attribute!r} attribute",
            element=element.get("id", local(element)),
            code="invalid_structure",
        )
    return value


def loads_ptml(payload: bytes | str, *, limits: XMLLimits = XMLLimits()) -> ParsedModel:
    """Read one PTML process tree, retaining IDs separately from its semantics.

    Sibling order is the XML document order of ``parentsNode`` edges. All nodes
    must belong to the one declared root. ``limits.max_depth`` additionally
    bounds the logical tree, because the XML representation itself is flat.
    """
    root = parse_xml(payload, _FORMAT, limits)
    for element in root.iter():
        if "}" in element.tag:
            fail(
                _FORMAT,
                "Namespaced PTML elements are outside this profile",
                element=element.tag,
            )
        if element.text and element.text.strip():
            fail(
                _FORMAT,
                "PTML elements cannot contain text content",
                element=local(element),
            )
    if local(root) != "ptml":
        fail(_FORMAT, "Expected a ptml document", code="invalid_structure")
    strict(root, set(), {"processTree"}, _FORMAT)
    if len(root) != 1:
        fail(
            _FORMAT,
            "PTML must contain exactly one processTree",
            code="invalid_structure",
        )
    tree = root[0]
    strict(tree, {"id", "name", "root"}, {*_TAGS, "parentsNode"}, _FORMAT)
    root_id = _required(tree, "root")
    used_ids: set[str] = set()

    def register(element: ET.Element, *, required: bool = True) -> str | None:
        value = _required(element, "id") if required else element.get("id")
        if value is not None:
            if not value.strip():
                fail(_FORMAT, "IDs must not be blank", code="invalid_structure")
            if value in used_ids:
                fail(
                    _FORMAT,
                    f"Duplicate XML ID {value!r}",
                    element=value,
                    code="duplicate_id",
                )
            used_ids.add(value)
        return value

    tree_id = register(tree, required=False)
    nodes: dict[str, ET.Element] = {}
    edges: list[tuple[str, str, str | None]] = []
    for element in tree:
        tag = local(element)
        if tag == "parentsNode":
            strict(element, {"id", "sourceId", "targetId"}, set(), _FORMAT)
            edge_id = register(element, required=False)
            edges.append(
                (
                    _required(element, "sourceId"),
                    _required(element, "targetId"),
                    edge_id,
                )
            )
        else:
            strict(element, {"id", "name"}, set(), _FORMAT)
            node_id = register(element)
            nodes[node_id] = element
            if tag == "manualTask":
                _required(element, "name")
    if root_id not in nodes:
        fail(
            _FORMAT,
            "Declared root does not identify a node",
            element=root_id,
            code="dangling_reference",
        )

    children: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    incoming: dict[str, tuple[str, str | None]] = {}
    for parent_id, child_id, edge_id in edges:
        if parent_id not in nodes or child_id not in nodes:
            fail(
                _FORMAT,
                "Parent edge references an unknown node",
                element=edge_id or child_id,
                code="dangling_reference",
            )
        if child_id in incoming:
            fail(
                _FORMAT,
                "A tree node must have exactly one parent",
                element=child_id,
                code="invalid_structure",
            )
        if parent_id == child_id or child_id == root_id:
            fail(
                _FORMAT,
                "Root-parent or self-loop edges are not a process tree",
                element=child_id,
                code="invalid_structure",
            )
        incoming[child_id] = parent_id, edge_id
        children[parent_id].append(child_id)

    # The one-parent constraint makes cycles reachable from the declared root
    # impossible. The final reachability check also rejects disconnected cycles.
    pending = [(root_id, "/0", 1)]
    preorder: list[tuple[str, str, int]] = []
    while pending:
        node_id, path, depth = pending.pop()
        if depth > limits.max_depth:
            fail(
                _FORMAT,
                "Logical process-tree depth exceeds max_depth",
                element=node_id,
                code="limit_exceeded",
            )
        preorder.append((node_id, path, depth))
        pending.extend(
            (child_id, f"{path}/{index}", depth + 1)
            for index, child_id in reversed(tuple(enumerate(children[node_id])))
        )
    if len(preorder) != len(nodes):
        fail(
            _FORMAT,
            "Every node must be reachable from the declared root; disconnected nodes or cycles found",
            code="invalid_structure",
        )

    identifiers: list[tuple[str, str]] = []
    metadata: list[tuple[str, str]] = []
    if tree_id is not None:
        identifiers.append(("tree", tree_id))
    if "name" in tree.attrib:
        metadata.append(("tree_name", tree.attrib["name"]))
    tau_exits: dict[str, str] = {}
    for node_id, path, _ in preorder:
        operator = _TAGS[local(nodes[node_id])]
        child_ids = children[node_id]
        if operator in {"activity", "tau"} and child_ids:
            fail(
                _FORMAT,
                "A task leaf cannot have children",
                element=node_id,
                code="invalid_structure",
            )
        if operator in {"sequence", "xor", "parallel"} and len(child_ids) < 2:
            fail(
                _FORMAT,
                "A composite operator requires at least two children",
                element=node_id,
                code="invalid_structure",
            )
        if operator == "loop":
            if len(child_ids) == 3:
                exit_id = child_ids[2]
                if local(nodes[exit_id]) != "automaticTask" or children[exit_id]:
                    fail(
                        _FORMAT,
                        "Only a silent third loop exit is supported",
                        element=node_id,
                    )
                tau_exits[exit_id] = path
                metadata.append((f"normalized_tau_exit:{path}", exit_id))
            elif len(child_ids) != 2:
                fail(
                    _FORMAT,
                    "Loops require (do, redo) and optionally a silent exit",
                    element=node_id,
                )

    built: dict[str, ProcessTree] = {}
    for node_id, _, _ in reversed(preorder):
        element = nodes[node_id]
        operator = _TAGS[local(element)]
        child_ids = children[node_id][:2] if operator == "loop" else children[node_id]
        built[node_id] = ProcessTree(
            operator,
            activity=element.get("name") if operator == "activity" else None,
            children=tuple(built[child_id] for child_id in child_ids),
        )

    for node_id, path, _ in preorder:
        is_exit = node_id in tau_exits
        key = f"loop_exit:{tau_exits[node_id]}" if is_exit else f"node:{path}"
        identifiers.append((key, node_id))
        if node_id in incoming and incoming[node_id][1] is not None:
            edge_key = (
                f"loop_exit_edge:{tau_exits[node_id]}" if is_exit else f"edge:{path}"
            )
            identifiers.append((edge_key, incoming[node_id][1]))
        name = nodes[node_id].get("name")
        if name and local(nodes[node_id]) != "manualTask":
            metadata.append((f"name:{key}", name))

    return ParsedModel(
        model=built[root_id],
        format=_FORMAT,
        profile=_PROFILE,
        format_version="unversioned",
        source_sha256=source_digest(payload),
        source_ids=tuple(identifiers),
        metadata=tuple(metadata),
    )


def dumps_ptml(model: ProcessTree | ParsedModel) -> bytes:
    """Write deterministic PTML, adding a silent exit to every binary loop.

    Passing the result of :func:`loads_ptml` retains source node/edge/tree IDs
    and display names. Passing its bare ``model`` creates deterministic IDs.
    Whitespace, XML edge interleaving, and attribute order are not preserved.
    """
    identifiers: dict[str, str] = {}
    metadata: dict[str, str] = {}

    def pairs(value, field: str) -> dict[str, str]:
        if not isinstance(value, tuple) or any(
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(isinstance(item, str) for item in pair)
            for pair in value
        ):
            fail(
                _FORMAT,
                f"{field} must contain immutable text pairs",
                code="invalid_model",
            )
        result = dict(value)
        if len(result) != len(value):
            fail(_FORMAT, f"{field} keys must be unique", code="invalid_model")
        return result

    if isinstance(model, ParsedModel):
        if model.format != _FORMAT:
            fail(
                _FORMAT,
                "Cannot use another format's parsed metadata",
                code="invalid_model",
            )
        if (
            model.profile != _PROFILE
            or model.format_version != "unversioned"
            or model.profile_version != "1.0.0"
        ):
            fail(_FORMAT, "Unsupported PTML profile or version", code="invalid_model")
        identifiers = pairs(model.source_ids, "source_ids")
        metadata = pairs(model.metadata, "metadata")
        if len(set(identifiers.values())) != len(identifiers):
            fail(
                _FORMAT,
                "Source identifiers must have unique paths and IDs",
                code="invalid_model",
            )
        model = model.model
    if not isinstance(model, ProcessTree):
        raise TypeError("dumps_ptml requires ProcessTree or a PTML ParsedModel")

    reserved = set(identifiers.values())
    consumed: set[str] = set()
    consumed_metadata = {"tree_name"}

    def identifier(key: str) -> str:
        consumed.add(key)
        if key in identifiers:
            value = identifiers[key]
            if not isinstance(value, str) or not value.strip():
                fail(_FORMAT, "Source IDs must be nonblank text", code="invalid_model")
            return value
        base = "pix_" + key.replace(":", "_").replace("/", "_")
        candidate = base
        suffix = 0
        while candidate in reserved:
            suffix += 1
            candidate = f"{base}_{suffix}"
        reserved.add(candidate)
        return candidate

    root = ET.Element("ptml")
    tree = ET.SubElement(
        root,
        "processTree",
        {
            "id": identifier("tree"),
            "name": metadata.get("tree_name", "PIX Process Tree"),
        },
    )
    pending: list[tuple[ProcessTree, str, str | None, int]] = [(model, "/0", None, 1)]
    records: list[tuple[str, str | None, str]] = []
    maximum = XMLLimits()
    while pending:
        node, path, parent_id, depth = pending.pop()
        if depth > maximum.max_depth or len(records) * 2 + 2 >= maximum.max_elements:
            fail(
                _FORMAT,
                "Process tree exceeds default XML export limits",
                code="limit_exceeded",
            )
        if not isinstance(node, ProcessTree):
            fail(
                _FORMAT,
                "Every tree node must be ProcessTree",
                element=path,
                code="invalid_model",
            )
        try:
            # Frozen contracts can still be forged with object.__setattr__ or
            # deserialization. Recheck every occurrence at the export boundary.
            ProcessTree(node.operator, node.activity, node.children)
        except (AttributeError, TypeError, ValueError) as error:
            fail(
                _FORMAT,
                f"Invalid ProcessTree node: {error}",
                element=path,
                code="invalid_model",
            )
        key = f"node:{path}"
        node_id = identifier(key)
        if node.operator != "activity":
            consumed_metadata.add(f"name:{key}")
        if parent_id is None:
            tree.set("root", node_id)
        ET.SubElement(
            tree,
            _REVERSE_TAGS[node.operator],
            {
                "id": node_id,
                "name": node.activity
                if node.operator == "activity"
                else metadata.get(f"name:{key}", ""),
            },
        )
        records.append((node_id, parent_id, f"edge:{path}"))
        if node.operator == "loop":
            exit_key = f"loop_exit:{path}"
            exit_id = identifier(exit_key)
            normalization_key = f"normalized_tau_exit:{path}"
            consumed_metadata.update((f"name:{exit_key}", normalization_key))
            if normalization_key in metadata and metadata[normalization_key] != exit_id:
                fail(
                    _FORMAT,
                    "Tau-exit metadata does not match its source ID",
                    element=path,
                    code="invalid_model",
                )
            ET.SubElement(
                tree,
                "automaticTask",
                {"id": exit_id, "name": metadata.get(f"name:{exit_key}", "")},
            )
            # Record the exit after the two semantic children below, so edge
            # order remains do, redo, exit independently of node order.
            records.append((exit_id, node_id, f"loop_exit_edge:{path}"))
        pending.extend(
            (child, f"{path}/{index}", node_id, depth + 1)
            for index, child in reversed(tuple(enumerate(node.children)))
        )

    # Stable parent-edge order is the only ordering signal in this dialect.
    # Each loop's synthetic third edge must follow its actual child edges.
    exits = []
    for node_id, parent_id, key in records:
        if parent_id is None:
            continue
        if key.startswith("loop_exit_edge:"):
            exits.append((node_id, parent_id, key))
            continue
        ET.SubElement(
            tree,
            "parentsNode",
            {"id": identifier(key), "sourceId": parent_id, "targetId": node_id},
        )
    for node_id, parent_id, key in exits:
        ET.SubElement(
            tree,
            "parentsNode",
            {"id": identifier(key), "sourceId": parent_id, "targetId": node_id},
        )
    if identifiers.keys() - consumed:
        fail(
            _FORMAT,
            "Source IDs do not match the process-tree structure",
            code="invalid_model",
        )
    if metadata.keys() - consumed_metadata:
        fail(_FORMAT, "Unsupported or stale PTML metadata keys", code="invalid_model")
    try:
        result = xml_bytes(root)
    except ModelIOError as error:
        fail(_FORMAT, str(error), element=error.element, code=error.code)
    if len(result) > maximum.max_bytes:
        fail(
            _FORMAT, "Serialized PTML exceeds default max_bytes", code="limit_exceeded"
        )
    # Verify the same bounded profile accepted by readers before publishing.
    # This also guards against future serializer changes bypassing invariants.
    loads_ptml(result)
    return result


__all__ = ("dumps_ptml", "loads_ptml")
