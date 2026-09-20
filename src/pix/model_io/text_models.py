"""Bounded human-authored tree and POWL text profiles, without code execution.

Tree grammar: tau, quoted activity, ->(...), X(...), +(...), *(do,redo).
POWL grammar: JSON objects using kind/activity/children/order and child-index
edges. This is PIX's explicit POWL JSON text profile, not a claim to parse every
reference-library repr. Native node contracts validate execution semantics.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from hashlib import sha256

from pix.case_centric.powl import POWLNode
from pix.contracts.discovery import ProcessTree
from pix.model_io.common import ParsedModel, fail


@dataclass(frozen=True, slots=True)
class TextModelLimits:
    max_bytes: int = 1_000_000
    max_nodes: int = 10_000
    max_depth: int = 64
    max_order_children: int = 128

    def __post_init__(self):
        for key in ("max_bytes", "max_nodes", "max_depth", "max_order_children"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be positive")
        if self.max_depth > 128:
            raise ValueError("max_depth must not exceed 128")


def _text(data, limits, format):
    if not isinstance(limits, TextModelLimits):
        raise TypeError("limits must be TextModelLimits")
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, bytes):
        raise TypeError("model text must be str or bytes")
    if len(data) > limits.max_bytes:
        fail(format, "byte limit exceeded", code="resource_limit")
    try:
        return data, data.decode("utf-8-sig")
    except UnicodeError as error:
        fail(format, str(error), code="invalid_text")


_TOKEN = re.compile(r"""\s*(->|[X+*(),]|tau\b|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')""")
_OPS = {"->": "sequence", "X": "xor", "+": "parallel", "*": "loop"}


def loads_tree_text(
    data: str | bytes, *, limits: TextModelLimits = TextModelLimits()
) -> ParsedModel:
    raw, text = _text(data, limits, "tree-text")
    pos, nodes = 0, 0

    def token():
        nonlocal pos
        match = _TOKEN.match(text, pos)
        if match is None:
            raise ValueError(f"expected a tree token at character {pos}")
        pos = match.end()
        return match[1]

    def node(depth):
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes or depth > limits.max_depth:
            raise ValueError("tree node/depth limit exceeded")
        t = token()
        if t == "tau":
            return ProcessTree("tau")
        if t.startswith(('"', "'")):
            return ProcessTree("activity", ast.literal_eval(t))
        if t not in _OPS or token() != "(":
            raise ValueError("expected operator and opening parenthesis")
        children = [node(depth + 1)]
        separator = token()
        while separator == ",":
            children.append(node(depth + 1))
            separator = token()
        if separator != ")":
            raise ValueError("expected comma or closing parenthesis")
        return ProcessTree(_OPS[t], children=tuple(children))

    try:
        model = node(1)
        if text[pos:].strip():
            raise ValueError(f"trailing input at character {pos}")
    except (ValueError, SyntaxError, RecursionError) as error:
        fail("tree-text", str(error), code="invalid_tree_text")
    return ParsedModel(
        model, "tree-text", "pix.tree-text.v1", "1", sha256(raw).hexdigest()
    )


def dumps_tree_text(
    model: ProcessTree | ParsedModel, *, limits: TextModelLimits = TextModelLimits()
) -> bytes:
    if isinstance(model, ParsedModel):
        model = model.model
    if not isinstance(model, ProcessTree):
        raise TypeError("model must be ProcessTree")
    pending = [(model, 1)]
    count = 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > limits.max_nodes or depth > limits.max_depth:
            fail("tree-text", "node/depth limit exceeded", code="resource_limit")
        pending.extend((child, depth + 1) for child in item.children)

    def encode(item):
        if item.operator == "activity":
            return json.dumps(item.activity, ensure_ascii=False)
        if item.operator == "tau":
            return "tau"
        symbol = {value: key for key, value in _OPS.items()}[item.operator]
        return symbol + "(" + ", ".join(encode(child) for child in item.children) + ")"

    data = encode(model).encode("utf-8")
    _text(data, limits, "tree-text")
    return data


def loads_powl_text(
    data: str | bytes, *, limits: TextModelLimits = TextModelLimits()
) -> ParsedModel:
    raw, text = _text(data, limits, "powl-text")
    nodes = 0

    def unique(pairs):
        if len(dict(pairs)) != len(pairs):
            raise ValueError("duplicate POWL JSON key")
        return dict(pairs)

    def node(value, depth):
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes or depth > limits.max_depth:
            raise ValueError("POWL node/depth limit exceeded")
        if (
            not isinstance(value, dict)
            or set(value) - {"kind", "activity", "children", "order"}
            or "kind" not in value
        ):
            raise ValueError("invalid POWL node fields")
        children, order = value.get("children", []), value.get("order", [])
        if not isinstance(children, list) or not isinstance(order, list):
            raise ValueError("POWL children/order must be arrays")
        if (
            value["kind"] == "partial_order"
            and len(children) > limits.max_order_children
        ):
            raise ValueError("POWL partial-order width limit exceeded")
        if any(not isinstance(edge, list) or len(edge) != 2 for edge in order):
            raise ValueError("POWL order requires index pairs")
        return POWLNode(
            value["kind"],
            value.get("activity"),
            tuple(node(c, depth + 1) for c in children),
            tuple(tuple(e) for e in order),
        )

    try:
        parsed = json.loads(text, object_pairs_hook=unique)
        model = node(parsed, 1)
    except (ValueError, TypeError, RecursionError) as error:
        fail("powl-text", str(error), code="invalid_powl_text")
    return ParsedModel(
        model, "powl-text", "pix.powl-json-text.v1", "1", sha256(raw).hexdigest()
    )


def dumps_powl_text(
    model: POWLNode | ParsedModel, *, limits: TextModelLimits = TextModelLimits()
) -> bytes:
    if isinstance(model, ParsedModel):
        model = model.model
    if not isinstance(model, POWLNode):
        raise TypeError("model must be POWLNode")
    nodes = 0

    def encode(item, depth):
        nonlocal nodes
        nodes += 1
        if nodes > limits.max_nodes or depth > limits.max_depth:
            fail("powl-text", "node/depth limit exceeded", code="resource_limit")
        if (
            item.kind == "partial_order"
            and len(item.children) > limits.max_order_children
        ):
            fail(
                "powl-text", "partial-order width limit exceeded", code="resource_limit"
            )
        value = {"kind": item.kind}
        if item.activity is not None:
            value["activity"] = item.activity
        if item.children:
            value["children"] = [encode(c, depth + 1) for c in item.children]
        if item.order:
            value["order"] = item.order
        return value

    data = json.dumps(encode(model, 1), ensure_ascii=False, indent=2).encode("utf-8")
    _text(data, limits, "powl-text")
    return data


__all__ = [
    "TextModelLimits",
    "loads_tree_text",
    "dumps_tree_text",
    "loads_powl_text",
    "dumps_powl_text",
]
