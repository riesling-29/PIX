"""Native process-tree folding and trace-relative nullable-branch reduction.

``language.v1`` preserves the entire visible language, including epsilon. It
flattens associative operators, removes sequence/parallel tau, removes duplicate
XOR alternatives, and removes an explicit XOR tau if another alternative is
nullable. A binary loop is do (redo do)*: a silent redo is NOT removable.

``nullable_disjoint.v1`` replaces a nullable subtree whose alphabet is disjoint
from one specified trace with tau, then applies language-preserving folding.
Its guarantee is narrower: the minimum insertion/deletion alignment cost for
that trace is unchanged, with zero-cost synchronous and silent moves and finite
nonnegative constant log/model move costs. No substitution move, transition
identity cost, probability, timing, resource or arbitrary alignment-cost
guarantee is made. The reduced language is a subset of the original language.

Proof: all visible moves in a removed subtree must be model moves for this
trace. Choosing its epsilon behavior removes only nonnegative costs without
changing the order of the other moves. Conversely, every reduced execution can
be lifted through the witnessed epsilon behavior of the original subtree.
The reduced model must not replace the original for another trace or for
precision/generalization analysis. PM4Py TREE_TR_BASED excludes the root; that
selection convention is the default here, with explicit opt-in root reduction.
This module neither imports nor runs an upstream process-mining implementation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from hashlib import sha256

from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _bounds(spec):
    for name in ("max_nodes", "max_depth"):
        if type(getattr(spec, name)) is not int or getattr(spec, name) < 1:
            raise ValueError(f"{name} must be a positive integer")
    # Two serialization levels per tree level plus result/witness envelopes.
    if spec.max_depth > 48:
        raise ValueError("max_depth must not exceed the supported depth of 48")
    if not isinstance(spec.profile, str) or not spec.profile:
        raise ValueError("profile must be nonempty text")
    try:
        spec.profile.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("profile must be valid UTF-8 text") from exc


@dataclass(frozen=True, slots=True)
class TreeFoldSpec:
    profile: str = "language.v1"
    max_nodes: int = 100_000
    max_depth: int = 48

    def __post_init__(self):
        _bounds(self)


@dataclass(frozen=True, slots=True)
class TraceTreeReductionSpec:
    profile: str = "nullable_disjoint.v1"
    log_move_cost: float = 1.0
    model_move_cost: float = 1.0
    reduce_root: bool = False
    max_nodes: int = 100_000
    max_depth: int = 48

    def __post_init__(self):
        _bounds(self)
        if type(self.reduce_root) is not bool:
            raise TypeError("reduce_root must be bool")
        for name in ("log_move_cost", "model_move_cost"):
            cost = getattr(self, name)
            if isinstance(cost, bool) or not isinstance(cost, (float, int)):
                raise TypeError(f"{name} must be a finite nonnegative number")
            try:
                cost = float(cost)
            except OverflowError as exc:
                raise ValueError(f"{name} must be finite") from exc
            if not math.isfinite(cost) or cost < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
            object.__setattr__(self, name, cost)


@dataclass(frozen=True, slots=True)
class TreeFoldRequest:
    model_digest: str | None
    parameters: TreeFoldSpec


@dataclass(frozen=True, slots=True)
class TraceTreeReductionRequest:
    model_digest: str | None
    trace: tuple[str, ...]
    parameters: TraceTreeReductionSpec


@dataclass(frozen=True, slots=True)
class TreeRewrite:
    # Original input-tree occurrence; repeated equal subtrees have distinct paths.
    source_path: tuple[int, ...]
    rule: str
    # These digests describe the immediate intermediate rewrite, after any child
    # rewrites. They are structural witnesses, not language-equivalence hashes.
    before_structure_digest: str
    after_structure_digest: str
    removed_activities: tuple[str, ...]
    # For nullable pruning: selected tau-leaf paths, relative to that subtree.
    # Sequence/parallel select every child, XOR selects one nullable child, and
    # loop selects an epsilon do with zero redo iterations.
    epsilon_leaf_paths: tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class TreeReduction:
    model: ProcessTree
    source_model_digest: str
    reduced_model_digest: str
    guarantee: str
    input_node_count: int
    output_node_count: int
    rewrites: tuple[TreeRewrite, ...]
    changed: bool


@dataclass(frozen=True, slots=True)
class _Info:
    model: ProcessTree
    alphabet: frozenset[str]
    nullable: bool
    epsilon_paths: tuple[tuple[int, ...], ...]
    digest: str
    node_count: int


def _info(node, children=()):
    op = node.operator
    alphabet = (
        frozenset((node.activity,))
        if op == "activity"
        else frozenset().union(*(child.alphabet for child in children))
    )
    nullable = (
        op == "tau"
        or op in ("sequence", "parallel")
        and all(c.nullable for c in children)
        or op == "xor"
        and any(c.nullable for c in children)
        or op == "loop"
        and children[0].nullable
    )
    epsilon_paths = ()
    if op == "tau":
        epsilon_paths = ((),)
    elif nullable:
        selected = (
            (next(i for i, c in enumerate(children) if c.nullable),)
            if op == "xor"
            else ((0,) if op == "loop" else tuple(range(len(children))))
        )
        epsilon_paths = tuple(
            (i, *p) for i in selected for p in children[i].epsilon_paths
        )
    encoded = json.dumps(
        [op, node.activity, [c.digest for c in children]],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = "pix.process-tree-structure.v1:sha256:" + sha256(encoded).hexdigest()
    return _Info(
        node,
        alphabet,
        bool(nullable),
        epsilon_paths,
        digest,
        1 + sum(c.node_count for c in children),
    )


_TAU = _info(ProcessTree("tau"))


def _model_digest(model):
    from pix.models import model_document

    return model_document(model)["model_digest"]


def _reduce(model, spec, trace):
    is_trace = isinstance(spec, TraceTreeReductionSpec)
    operator = (
        "pix.case_centric.reduce_process_tree_for_trace"
        if is_trace
        else "pix.case_centric.fold_process_tree"
    )
    parent = model if isinstance(model, ComputationResult) else None
    parent_ids = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    issues = parent.issues if parent is not None else ()
    source_digest = parent.source_digest if parent is not None else None
    original_digest = None

    def finish(status, value, extra=()):
        request = (
            TraceTreeReductionRequest(original_digest, trace, spec)
            if is_trace
            else TreeFoldRequest(original_digest, spec)
        )
        return _derived_result(
            operator,
            source_digest,
            request,
            status,
            value,
            issues + extra,
            parent_computation_ids=parent_ids,
        )

    if parent is not None:
        if parent.value is None:
            return finish(parent.status, None)
        model = parent.value
        if not isinstance(model, ProcessTree):
            model = getattr(model, "model", None)
    if not isinstance(model, ProcessTree):
        raise TypeError("model must be ProcessTree or a result containing one")

    # Check occurrence bounds iteratively before recursive inspection/digestion.
    stack, count = [(model, 1)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        # Every pending node and immediate child is already a necessary input
        # occurrence. Reject before allocating a stack wider than the budget.
        if (
            count + len(stack) + len(node.children) > spec.max_nodes
            or depth > spec.max_depth
        ):
            return finish(
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "tree_reduction_limit",
                        "Input tree exceeds the explicit node/depth limit; no reduced model is returned.",
                    ),
                ),
            )
        stack.extend((child, depth + 1) for child in node.children)
    original_digest = _model_digest(model)
    if source_digest is None:
        source_digest = original_digest
    expected_profile = "nullable_disjoint.v1" if is_trace else "language.v1"
    if spec.profile != expected_profile:
        return finish(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "unsupported_tree_reduction_profile",
                    f"Only {expected_profile} is implemented.",
                ),
            ),
        )

    original_infos = {}

    def inspect(node):
        # Cache metadata of immutable shared subtrees; occurrence paths remain
        # separate in rewrites and the explicit input-node bound.
        if id(node) not in original_infos:
            original_infos[id(node)] = _info(
                node, tuple(inspect(c) for c in node.children)
            )
        return original_infos[id(node)]

    inspect(model)
    changes = []
    trace_alphabet = frozenset(trace) if is_trace else frozenset()

    def record(path, rule, before, after, epsilon_paths=()):
        changes.append(
            TreeRewrite(
                path,
                rule,
                before.digest,
                after.digest,
                tuple(sorted(before.alphabet - after.alphabet)),
                epsilon_paths,
            )
        )

    def composed(op, children):
        return _info(
            ProcessTree(op, children=tuple(c.model for c in children)), tuple(children)
        )

    def visit(node, path):
        old = original_infos[id(node)]
        if (
            is_trace
            and (path or spec.reduce_root)
            and old.alphabet
            and old.nullable
            and old.alphabet.isdisjoint(trace_alphabet)
        ):
            record(path, "trace_nullable_disjoint_to_tau", old, _TAU, old.epsilon_paths)
            return _TAU
        if not node.children:
            return old
        children = [visit(c, (*path, i)) for i, c in enumerate(node.children)]
        current = composed(node.operator, children)
        if not current.alphabet:
            record(path, "epsilon_only_to_tau", current, _TAU)
            return _TAU
        op = node.operator
        if op == "loop":
            return current
        flattened = []
        for child in children:
            if child.model.operator == op:
                # Metadata is inexpensive to reconstruct from the folded child;
                # this remains a bottom-up structural rule, not language search.
                flattened.extend(inspect(c) for c in child.model.children)
            else:
                flattened.append(child)
        if len(flattened) != len(children):
            after = composed(op, flattened)
            record(path, "flatten_associative_operator", current, after)
            current, children = after, flattened
        if op in ("sequence", "parallel"):
            retained = [c for c in children if c.model.operator != "tau"]
            rule = "remove_neutral_tau"
        else:
            # Preserve child order; use structure, not label set, for equality.
            seen, retained = set(), []
            for child in children:
                if child.digest not in seen:
                    retained.append(child)
                    seen.add(child.digest)
            if len(retained) != len(children):
                after = retained[0] if len(retained) == 1 else composed(op, retained)
                record(path, "deduplicate_xor_alternatives", current, after)
                current, children = after, retained
            if current.model.operator != "xor":
                return current
            if any(c.nullable and c.model.operator != "tau" for c in children):
                retained = [c for c in children if c.model.operator != "tau"]
            rule = "remove_redundant_xor_tau"
        if len(retained) != len(children):
            after = (
                _TAU
                if not retained
                else retained[0]
                if len(retained) == 1
                else composed(op, retained)
            )
            record(path, rule, current, after)
            current = after
        return current

    reduced = visit(model, ())
    value = TreeReduction(
        reduced.model,
        original_digest,
        _model_digest(reduced.model),
        "fixed_trace_minimum_insertion_deletion_cost"
        if is_trace
        else "visible_language_equivalence",
        count,
        reduced.node_count,
        tuple(changes),
        reduced.model != model,
    )
    return finish(
        ComputeStatus.PARTIAL
        if parent is not None and parent.status == ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED,
        value,
    )


def fold_process_tree(
    model: ProcessTree | ComputationResult,
    spec: TreeFoldSpec = TreeFoldSpec(),
) -> ComputationResult[TreeReduction]:
    """Apply the explicit whole-language-preserving folding rules."""
    if not isinstance(spec, TreeFoldSpec):
        raise TypeError("spec must be TreeFoldSpec")
    return _reduce(model, spec, None)


def reduce_process_tree_for_trace(
    model: ProcessTree | ComputationResult,
    trace: tuple[str, ...],
    spec: TraceTreeReductionSpec = TraceTreeReductionSpec(),
) -> ComputationResult[TreeReduction]:
    """Reduce relative to one exact trace and the documented alignment objective.

    Unknown trace labels are retained in the request; they are not projected
    away. This operation does not calculate an alignment or its cost. All
    observed event provenance remains with the caller; this API takes labels.
    """
    if not isinstance(spec, TraceTreeReductionSpec):
        raise TypeError("spec must be TraceTreeReductionSpec")
    if not isinstance(trace, tuple):
        raise TypeError("trace must be a tuple of activity labels")
    for label in trace:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("trace labels must be nonempty text")
        try:
            label.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise ValueError("trace labels must be valid UTF-8") from exc
    return _reduce(model, spec, trace)


RESULT_SCHEMAS = {
    "pix.case_centric.fold_process_tree": (
        "case-process-tree-fold",
        TreeFoldRequest,
        TreeReduction,
    ),
    "pix.case_centric.reduce_process_tree_for_trace": (
        "case-trace-process-tree-reduction",
        TraceTreeReductionRequest,
        TreeReduction,
    ),
}

__all__ = (
    "TreeFoldSpec",
    "TraceTreeReductionSpec",
    "TreeFoldRequest",
    "TraceTreeReductionRequest",
    "TreeRewrite",
    "TreeReduction",
    "fold_process_tree",
    "reduce_process_tree_for_trace",
)
