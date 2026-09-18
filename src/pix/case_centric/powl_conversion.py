"""Occurrence-preserving conversion of series/parallel POWL to process trees.

Partial orders are decomposed by the connected components of comparability
and incomparability. A parallel component has no cross-component ordering;
series components are totally ordered. XOR and do(redo do)* retain their
operators. No topological sorting is substituted for concurrency, and no
enumeration/duplication of occurrences is used for non-series-parallel orders.

A refusal concerns this structural conversion profile, not the impossibility
of representing a finite visible language by a larger tree with duplicated
activity occurrences. Silent children are not simplified to evade this rule.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from pix.case_centric.powl import POWLNode
from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class POWLTreeConversionSpec:
    max_model_nodes: int = 20_000
    max_depth: int = 48
    max_output_nodes: int = 40_000
    max_order_pairs: int = 1_000_000
    max_partial_order_children: int = 1024
    max_decomposition_checks: int = 2_000_000

    def __post_init__(self):
        for name in (
            "max_model_nodes",
            "max_depth",
            "max_output_nodes",
            "max_order_pairs",
            "max_partial_order_children",
            "max_decomposition_checks",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_depth > 48:
            raise ValueError("max_depth must not exceed the result-codec bound 48")


@dataclass(frozen=True, slots=True)
class POWLTreeConversionRequest:
    model_digest: str | None
    parameters: POWLTreeConversionSpec


@dataclass(frozen=True, slots=True)
class POWLTreeConversionStep:
    """Paths identify occurrences even when labels or submodels are equal.

    For a decomposition step, ``source_child_indices`` identifies the subset of
    the partial-order node's original children represented at ``tree_path``.
    Leaf, XOR and loop steps refer directly to ``source_path`` and have no subset.
    """

    source_path: tuple[int, ...]
    source_child_indices: tuple[int, ...]
    tree_path: tuple[int, ...]
    rule: str


@dataclass(frozen=True, slots=True)
class POWLTreeConversion:
    model: ProcessTree
    source_model_digest: str
    steps: tuple[POWLTreeConversionStep, ...]
    decomposition_checks: int


class _Limit(Exception):
    pass


class _NonSeriesParallel(Exception):
    def __init__(self, path, indices):
        self.path = path
        self.indices = indices


def powl_to_process_tree(
    model: POWLNode | ComputationResult,
    spec: POWLTreeConversionSpec = POWLTreeConversionSpec(),
) -> ComputationResult[POWLTreeConversion]:
    """Return an exact series/parallel tree or explicit unavailability.

    Nested partial-order submodels may interleave; a predecessor's complete
    submodel must finish before a successor starts. These same constraints are
    preserved by the returned sequence/parallel tree. A partial upstream result
    remains partial, although conversion of its released model is complete.
    Inputs exceeding traversal limits are refused before hashing, so a raw
    oversized input may have no digest; any parent provenance is still kept.
    """
    if not isinstance(spec, POWLTreeConversionSpec):
        raise TypeError("spec must be POWLTreeConversionSpec")
    if not isinstance(model, (POWLNode, ComputationResult)):
        raise TypeError("expected POWLNode or a result containing a POWLNode")
    parent = model if isinstance(model, ComputationResult) else None
    candidate = parent.value if parent is not None else model
    if candidate is not None and not isinstance(candidate, POWLNode):
        candidate = getattr(candidate, "model", candidate)
    digest = None

    def result(status, value=None, issues=()):
        if parent is not None and parent.value is None:
            status, issues = parent.status, ()
        elif (
            parent is not None
            and parent.status == ComputeStatus.PARTIAL
            and status == ComputeStatus.COMPUTED
        ):
            status = ComputeStatus.PARTIAL
        return _derived_result(
            "pix.case_centric.powl_to_process_tree",
            parent.source_digest if parent is not None else digest,
            POWLTreeConversionRequest(digest, spec),
            status,
            value,
            (parent.issues if parent is not None else ()) + tuple(issues),
            parent_computation_ids=(parent.computation_id,)
            if parent is not None and parent.computation_id
            else (),
        )

    if candidate is None:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("powl_model_unavailable", "No POWL was released."),),
        )
    if not isinstance(candidate, POWLNode):
        raise TypeError("expected POWLNode or a result containing a POWLNode")

    try:
        pending, input_count, order_pairs = [(candidate, 1)], 0, 0
        while pending:
            current, depth = pending.pop()
            input_count += 1
            order_pairs += len(current.order)
            if input_count > spec.max_model_nodes or depth > spec.max_depth:
                raise _Limit("Input POWL node or depth budget exceeded")
            if order_pairs > spec.max_order_pairs:
                raise _Limit("Input strict-order pair budget exceeded")
            arity = len(current.children)
            if (
                current.kind == "partial_order"
                and arity > spec.max_partial_order_children
            ):
                raise _Limit("Partial-order child budget exceeded")
            if input_count + len(pending) + arity > spec.max_model_nodes:
                raise _Limit("Input POWL node budget exceeded")
            pending.extend((child, depth + 1) for child in current.children)
        from pix.models import _model_digest

        # The bounded occurrence tree uses exactly the native artifact identity.
        digest = _model_digest(candidate, asdict(candidate))
    except _Limit as exc:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("powl_tree_conversion_limit", str(exc)),),
        )

    steps: list[POWLTreeConversionStep] = []
    output_nodes = checks = 0

    def check():
        nonlocal checks
        checks += 1
        if checks > spec.max_decomposition_checks:
            raise _Limit("Partial-order decomposition check budget exceeded")

    def tree(operator, path, activity=None, children=()):
        nonlocal output_nodes
        output_nodes += 1
        if output_nodes > spec.max_output_nodes or len(path) >= spec.max_depth:
            raise _Limit("Output tree node or depth budget exceeded")
        return ProcessTree(operator, activity, children)

    def components(indices, parents):
        groups = {}
        for index in indices:
            root = index
            while parents[root] != root:
                root = parents[root]
            groups.setdefault(root, []).append(index)
        return tuple(tuple(group) for group in groups.values())

    def union(parents, left, right):
        while parents[left] != left:
            parents[left] = parents[parents[left]]
            left = parents[left]
        while parents[right] != right:
            parents[right] = parents[parents[right]]
            right = parents[right]
        if left != right:
            parents[max(left, right)] = min(left, right)

    def decompose(node, order, indices, source_path, target_path):
        if len(indices) == 1:
            index = indices[0]
            return convert(node.children[index], (*source_path, index), target_path)
        if len(target_path) >= spec.max_depth:
            raise _Limit("Output tree depth budget exceeded")
        comparable = {index: index for index in indices}
        incomparable = comparable.copy()
        for position, left in enumerate(indices):
            for right in indices[position + 1 :]:
                check()
                graph = (
                    comparable
                    if (left, right) in order or (right, left) in order
                    else incomparable
                )
                union(graph, left, right)
        parts = components(indices, comparable)
        if len(parts) > 1:
            operator, rule = "parallel", "parallel_components"
        else:
            parts = components(indices, incomparable)
            if len(parts) == 1:
                raise _NonSeriesParallel(source_path, indices)
            # The quotient of incomparability components is a total order.
            ranked = []
            for group in parts:
                predecessors = 0
                for other in parts:
                    if other is group:
                        continue
                    check()
                    predecessors += (other[0], group[0]) in order
                ranked.append((predecessors, group))
            parts = tuple(group for _, group in sorted(ranked))
            operator, rule = "sequence", "series_components"
        steps.append(POWLTreeConversionStep(source_path, indices, target_path, rule))
        children = tuple(
            decompose(node, order, group, source_path, (*target_path, i))
            for i, group in enumerate(parts)
        )
        return tree(operator, target_path, children=children)

    def convert(node, source_path, target_path):
        if node.kind == "partial_order":
            return decompose(
                node,
                set(node.order),
                tuple(range(len(node.children))),
                source_path,
                target_path,
            )
        steps.append(POWLTreeConversionStep(source_path, (), target_path, node.kind))
        children = tuple(
            convert(child, (*source_path, i), (*target_path, i))
            for i, child in enumerate(node.children)
        )
        return tree(node.kind, target_path, node.activity, children)

    try:
        converted = convert(candidate, (), ())
    except _Limit as exc:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("powl_tree_conversion_limit", str(exc)),),
        )
    except _NonSeriesParallel as exc:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "powl_non_series_parallel",
                    "No occurrence-preserving series/parallel decomposition for "
                    f"child subset {exc.indices}; no tree was released.",
                    tuple(str(index) for index in exc.path),
                ),
            ),
        )
    return result(
        ComputeStatus.COMPUTED,
        POWLTreeConversion(converted, digest, tuple(steps), checks),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.powl_to_process_tree": (
        "case-powl-to-process-tree",
        POWLTreeConversionRequest,
        POWLTreeConversion,
    ),
}

__all__ = (
    "POWLTreeConversionSpec",
    "POWLTreeConversionRequest",
    "POWLTreeConversionStep",
    "POWLTreeConversion",
    "powl_to_process_tree",
)
