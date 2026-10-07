"""Native process-tree conversions preserving choice, order and concurrency.

POWL sequence is a total strict order and parallel is an empty strict order.
BPMN uses explicit exclusive/parallel gateways and plain tasks/events only.
Silent tree branches become sequence-flow bypasses, not fabricated activities.
The generated BPMN is the existing SplitBPMN control-flow profile, with no
message, timer, data condition, probability, inclusive-OR or layout semantics.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pix.case_centric.powl import POWLNode
from pix.case_centric.split_miner import SplitBPMN, SplitBPMNFlow, SplitBPMNNode
from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class TreeConversionSpec:
    max_tree_nodes: int = 20_000
    max_depth: int = 48
    max_output_nodes: int = 100_000
    max_output_flows: int = 200_000
    max_order_pairs: int = 1_000_000
    max_partial_order_children: int = 1024

    def __post_init__(self):
        for key in (
            "max_tree_nodes",
            "max_depth",
            "max_output_nodes",
            "max_output_flows",
            "max_order_pairs",
            "max_partial_order_children",
        ):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"{key} must be a positive integer")
        if self.max_depth > 48:
            raise ValueError(
                "max_depth must not exceed the nested result-codec profile bound 48"
            )


@dataclass(frozen=True, slots=True)
class TreeConversionRequest:
    model_digest: str | None
    parameters: TreeConversionSpec


@dataclass(frozen=True, slots=True)
class TreeConversionStep:
    tree_path: tuple[int, ...]
    rule: str


@dataclass(frozen=True, slots=True)
class TreePOWLConversion:
    model: POWLNode
    source_model_digest: str
    steps: tuple[TreeConversionStep, ...]


@dataclass(frozen=True, slots=True)
class TreeBPMNConversion:
    model: SplitBPMN
    source_model_digest: str
    steps: tuple[TreeConversionStep, ...]
    activity_nodes: tuple[tuple[tuple[int, ...], str], ...]


class _ConversionLimit(Exception):
    pass


def _input_tree(model, spec):
    if not isinstance(spec, TreeConversionSpec):
        raise TypeError("spec must be TreeConversionSpec")
    parent = model if isinstance(model, ComputationResult) else None
    if parent is not None:
        if parent.value is None:
            return None, parent, None
        model = parent.value
        if not isinstance(model, ProcessTree):
            carries_model = hasattr(model, "tree") or hasattr(model, "model")
            model = getattr(model, "tree", getattr(model, "model", None))
            if (
                carries_model
                and model is None
                and parent.status == ComputeStatus.PARTIAL
            ):
                return None, parent, None
    if not isinstance(model, ProcessTree):
        raise TypeError("expected ProcessTree or a result containing a ProcessTree")
    # The native tree digest has no artifact nesting limit. Converting its
    # tuple children to JSON arrays yields exactly the model codec's identity;
    # output/codec depth is checked separately by the explicit profile.
    from pix.models import _model_digest

    digest = _model_digest(model, asdict(model))
    return model, parent, digest


def _result(operator, spec, parent, digest, status, value, extra=()):
    if parent is not None and parent.value is None:
        status, extra = parent.status, ()
    elif (
        parent is not None
        and parent.status == ComputeStatus.PARTIAL
        and status == ComputeStatus.COMPUTED
    ):
        status = ComputeStatus.PARTIAL
    return _derived_result(
        operator,
        parent.source_digest if parent is not None else digest,
        TreeConversionRequest(digest, spec),
        status,
        value,
        (parent.issues if parent is not None else ()) + tuple(extra),
        parent_computation_ids=(parent.computation_id,)
        if parent is not None and parent.computation_id
        else (),
    )


def _check_shape(tree, spec):
    pending, count = [(tree, 1)], 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > spec.max_tree_nodes or depth > spec.max_depth:
            raise _ConversionLimit("Input tree exceeds its node or depth budget")
        pending.extend((child, depth + 1) for child in node.children)


def tree_to_powl(
    model: ProcessTree | ComputationResult,
    spec: TreeConversionSpec = TreeConversionSpec(),
):
    """Convert every native tree operator into its exact POWL counterpart."""
    tree, parent, digest = _input_tree(model, spec)
    operator = "pix.case_centric.tree_to_powl"
    if tree is None:
        return _result(
            operator,
            spec,
            parent,
            digest,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "tree_model_unavailable",
                    "The input computation did not release a complete ProcessTree.",
                ),
            ),
        )
    steps, nodes, pairs = [], 0, 0

    def convert(node, path):
        nonlocal nodes, pairs
        nodes += 1
        if nodes > spec.max_output_nodes:
            raise _ConversionLimit("POWL node budget exceeded")
        if node.operator in ("activity", "tau"):
            steps.append(TreeConversionStep(path, "leaf"))
            return POWLNode(node.operator, node.activity)
        children = tuple(
            convert(child, (*path, i)) for i, child in enumerate(node.children)
        )
        if node.operator in ("sequence", "parallel"):
            if len(children) > spec.max_partial_order_children:
                raise _ConversionLimit("POWL partial-order child budget exceeded")
            order_count = (
                len(children) * (len(children) - 1) // 2
                if node.operator == "sequence"
                else 0
            )
            pairs += order_count
            if pairs > spec.max_order_pairs:
                raise _ConversionLimit("POWL strict-order pair budget exceeded")
            order = (
                tuple(
                    (i, j)
                    for i in range(len(children))
                    for j in range(i + 1, len(children))
                )
                if node.operator == "sequence"
                else ()
            )
            steps.append(
                TreeConversionStep(
                    path,
                    "sequence_to_total_order" if order else "parallel_to_empty_order",
                )
            )
            return POWLNode("partial_order", children=children, order=order)
        steps.append(TreeConversionStep(path, "choice_or_loop"))
        return POWLNode(node.operator, children=children)

    try:
        _check_shape(tree, spec)
        converted = convert(tree, ())
    except _ConversionLimit as exc:
        return _result(
            operator,
            spec,
            parent,
            digest,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("tree_conversion_limit", str(exc)),),
        )
    return _result(
        operator,
        spec,
        parent,
        digest,
        ComputeStatus.COMPUTED,
        TreePOWLConversion(converted, digest, tuple(steps)),
    )


def tree_to_bpmn(
    model: ProcessTree | ComputationResult,
    spec: TreeConversionSpec = TreeConversionSpec(),
):
    """Construct structured task/XOR/AND BPMN with explicit loop gateways.

    Pure silent fragments have no task. Repeated silent XOR alternatives are
    merged because this control-flow contract carries no branch probabilities.
    Duplicate visible labels remain distinct task identities.
    """
    tree, parent, digest = _input_tree(model, spec)
    operator = "pix.case_centric.tree_to_bpmn"
    if tree is None:
        return _result(
            operator,
            spec,
            parent,
            digest,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "tree_model_unavailable",
                    "The input computation did not release a complete ProcessTree.",
                ),
            ),
        )
    nodes, flows, steps, activity_nodes = [], [], [], []

    def node(kind, activity=None, direction=None):
        if len(nodes) >= spec.max_output_nodes:
            raise _ConversionLimit("BPMN node budget exceeded")
        identity = f"tree_node_{len(nodes)}"
        nodes.append(SplitBPMNNode(identity, kind, activity, direction))
        return identity

    def flow(source, target):
        if len(flows) >= spec.max_output_flows:
            raise _ConversionLimit("BPMN flow budget exceeded")
        flows.append(SplitBPMNFlow(f"tree_flow_{len(flows)}", source, target))

    def fragment(current, path):
        if current.operator == "tau":
            steps.append(TreeConversionStep(path, "silent_flow_bypass"))
            return None
        if current.operator == "activity":
            identity = node("task", current.activity)
            activity_nodes.append((path, identity))
            return identity, identity
        if current.operator == "sequence":
            parts = [
                part
                for i, child in enumerate(current.children)
                if (part := fragment(child, (*path, i))) is not None
            ]
            for left, right in zip(parts, parts[1:]):
                flow(left[1], right[0])
            steps.append(TreeConversionStep(path, "ordered_sequence_flows"))
            return (parts[0][0], parts[-1][1]) if parts else None
        if current.operator == "loop":
            entry = node("exclusive_gateway", direction="join")
            exit_ = node("exclusive_gateway", direction="split")
            do, redo = (
                fragment(child, (*path, i)) for i, child in enumerate(current.children)
            )
            if do is None:
                flow(entry, exit_)
            else:
                flow(entry, do[0])
                flow(do[1], exit_)
            if redo is None:
                flow(exit_, entry)
            else:
                flow(exit_, redo[0])
                flow(redo[1], entry)
            steps.append(TreeConversionStep(path, "do_redo_exclusive_loop"))
            return entry, exit_
        parts = [
            fragment(child, (*path, i)) for i, child in enumerate(current.children)
        ]
        if current.operator == "parallel":
            parts = [part for part in parts if part is not None]
        else:
            # A silent branch is represented by one bypass edge; a second
            # identical epsilon alternative carries no extra language meaning.
            if parts.count(None) > 1:
                parts = [part for part in parts if part is not None] + [None]
                steps.append(
                    TreeConversionStep(path, "duplicate_epsilon_choice_removed")
                )
        if not parts:
            return None
        if len(parts) == 1:
            return parts[0]
        kind = (
            "parallel_gateway"
            if current.operator == "parallel"
            else "exclusive_gateway"
        )
        entry, exit_ = node(kind, direction="split"), node(kind, direction="join")
        for part in parts:
            if part is None:
                flow(entry, exit_)
            else:
                flow(entry, part[0])
                flow(part[1], exit_)
        steps.append(
            TreeConversionStep(
                path,
                "parallel_gateways"
                if current.operator == "parallel"
                else "exclusive_gateways",
            )
        )
        return entry, exit_

    try:
        _check_shape(tree, spec)
        start, end = node("start_event"), node("end_event")
        part = fragment(tree, ())
        if part is None:
            flow(start, end)
        else:
            flow(start, part[0])
            flow(part[1], end)
        converted = SplitBPMN(tuple(nodes), tuple(flows), start, end)
    except _ConversionLimit as exc:
        return _result(
            operator,
            spec,
            parent,
            digest,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("tree_conversion_limit", str(exc)),),
        )
    return _result(
        operator,
        spec,
        parent,
        digest,
        ComputeStatus.COMPUTED,
        TreeBPMNConversion(converted, digest, tuple(steps), tuple(activity_nodes)),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.tree_to_powl": (
        "case-tree-to-powl",
        TreeConversionRequest,
        TreePOWLConversion,
    ),
    "pix.case_centric.tree_to_bpmn": (
        "case-tree-to-bpmn",
        TreeConversionRequest,
        TreeBPMNConversion,
    ),
}

__all__ = (
    "TreeConversionSpec",
    "TreeConversionRequest",
    "TreeConversionStep",
    "TreePOWLConversion",
    "TreeBPMNConversion",
    "tree_to_powl",
    "tree_to_bpmn",
)
