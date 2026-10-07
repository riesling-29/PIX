"""Native transition-bordered process-tree conversion.

Every subtree occurrence has one entry and one exit transition. A leaf uses
the same transition for both; a composite has silent border transitions.
Sequence connects successive children, XOR offers one child, parallel forks
and joins all children, and a binary loop has language do (redo do)*. Only the
root receives the initial/final marking places. These are the transition-
bordered structural patterns documented by the pinned PM4Py 2.7.23.8 variant,
not ordinary place-bordered conversion with two extra transitions around it.

This independent construction preserves visible tree language and distinct
leaf identities, including repeated labels and tau. It does not preserve
timing, probabilities, transition counts or upstream generated identifiers.
No PM4Py code is imported or executed. Resource exhaustion releases no net.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.case_centric.tree_to_transition_bordered_petri_net"
PROFILE = "pix.tree.transition_bordered.v1"


@dataclass(frozen=True, slots=True)
class TransitionBorderedSpec:
    max_tree_nodes: int = 20_000
    max_depth: int = 48
    max_net_nodes: int = 100_000
    max_net_arcs: int = 200_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.TransitionBorderedSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("max_tree_nodes", "max_depth", "max_net_nodes", "max_net_arcs"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_depth > 48:
            raise ValueError("max_depth must not exceed the supported bound of 48")


@dataclass(frozen=True, slots=True)
class TransitionBorderedRequest:
    model_digest: str | None
    parameters: TransitionBorderedSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.TransitionBorderedRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TreeTransitionBorder:
    """Occurrence identity, not label identity; leaves have equal borders."""

    tree_path: tuple[int, ...]
    operator: str
    entry_transition_id: str
    exit_transition_id: str


@dataclass(frozen=True, slots=True)
class TransitionBorderedConversion:
    model: PetriNet
    profile: str
    source_model_digest: str
    borders: tuple[TreeTransitionBorder, ...]


class _Limit(Exception):
    pass


def _shape(tree, spec):
    """Bound traversal before recursive hashing or model construction."""
    pending, count, nodes, arcs = [(tree, 1)], 0, 2, 2
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > spec.max_tree_nodes or depth > spec.max_depth:
            raise _Limit("Input tree exceeds its node or depth budget")
        arity = len(node.children)
        if not arity:
            nodes += 1
        elif node.operator == "sequence":
            nodes += arity + 3
            arcs += 2 * arity + 2
        elif node.operator == "parallel":
            nodes += 2 * arity + 2
            arcs += 4 * arity
        else:  # XOR and binary loop: two places and two silent transitions.
            nodes += 4
            arcs += 2 * arity + 2
        if count + len(pending) + arity > spec.max_tree_nodes:
            raise _Limit("Input tree exceeds its node budget")
        pending.extend((child, depth + 1) for child in node.children)
    return nodes, arcs


def tree_to_transition_bordered_petri_net(
    model: ProcessTree | ComputationResult,
    spec: TransitionBorderedSpec = TransitionBorderedSpec(),
):
    """Convert a native tree with a transition-border witness for every path.

    Explicit limits are checked before any net is built. An input traversal
    limit may leave the raw tree digest unavailable, rather than traversing an
    oversized input solely to identify it. Parent provenance is always kept.
    Partial parent results with a released tree remain partial on conversion.
    """
    if not isinstance(spec, TransitionBorderedSpec):
        raise TypeError("spec must be TransitionBorderedSpec")
    parent = model if isinstance(model, ComputationResult) else None
    digest = None

    def finish(status, value=None, extra=()):
        if parent is not None and parent.value is None:
            status, extra = parent.status, ()
        elif (
            parent is not None
            and parent.status == ComputeStatus.PARTIAL
            and status == ComputeStatus.COMPUTED
        ):
            status = ComputeStatus.PARTIAL
        return _derived_result(
            OPERATOR_ID,
            parent.source_digest if parent is not None else digest,
            TransitionBorderedRequest(digest, spec),
            status,
            value,
            (parent.issues if parent is not None else ()) + tuple(extra),
            parent_computation_ids=(parent.computation_id,)
            if parent is not None and parent.computation_id
            else (),
        )

    if parent is not None:
        model = parent.value
        if model is not None and not isinstance(model, ProcessTree):
            if hasattr(model, "tree") or hasattr(model, "model"):
                model = getattr(model, "tree", getattr(model, "model", None))
        if model is None:
            return finish(
                ComputeStatus.UNAVAILABLE,
                extra=(
                    ComputeIssue(
                        "tree_model_unavailable",
                        "The input computation did not release a ProcessTree.",
                    ),
                ),
            )
    if not isinstance(model, ProcessTree):
        raise TypeError("expected ProcessTree or a result containing a ProcessTree")

    try:
        expected_nodes, expected_arcs = _shape(model, spec)
        from pix.models import _model_digest

        digest = _model_digest(model, asdict(model))
        if expected_nodes > spec.max_net_nodes or expected_arcs > spec.max_net_arcs:
            raise _Limit("The complete transition-bordered net exceeds its budget")
    except _Limit as exc:
        return finish(
            ComputeStatus.UNAVAILABLE,
            extra=(ComputeIssue("tree_bordered_limit", str(exc)),),
        )

    places, transitions, arcs, borders = [], [], [], []

    def place(name):
        identity = "tb_p_" + name
        places.append(Place(identity))
        return identity

    def transition(name, activity=None):
        identity = "tb_t_" + name
        transitions.append(Transition(identity, activity))
        return identity

    def link(source, target):
        arcs.append(Arc(source, target))

    def fragment(node, path):
        key = "root" if not path else "_".join(map(str, path))
        if not node.children:
            leaf = transition(key, node.activity)
            borders.append(TreeTransitionBorder(path, node.operator, leaf, leaf))
            return leaf, leaf
        entry, exit_ = transition(key + "_in"), transition(key + "_out")
        borders.append(TreeTransitionBorder(path, node.operator, entry, exit_))
        children = tuple(
            fragment(child, (*path, i)) for i, child in enumerate(node.children)
        )
        if node.operator == "sequence":
            chain = [place(f"{key}_step_{i}") for i in range(len(children) + 1)]
            link(entry, chain[0])
            link(chain[-1], exit_)
            for index, (start, end) in enumerate(children):
                link(chain[index], start)
                link(end, chain[index + 1])
        elif node.operator == "parallel":
            for index, (start, end) in enumerate(children):
                before = place(f"{key}_branch_{index}_in")
                after = place(f"{key}_branch_{index}_out")
                link(entry, before)
                link(before, start)
                link(end, after)
                link(after, exit_)
        else:
            before, after = place(key + "_in"), place(key + "_out")
            link(entry, before)
            link(after, exit_)
            for index, (start, end) in enumerate(children):
                backward = node.operator == "loop" and index == 1
                link(after if backward else before, start)
                link(end, before if backward else after)
        return entry, exit_

    start, end = fragment(model, ())
    source, sink = place("source"), place("sink")
    link(source, start)
    link(end, sink)
    net = PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking(((source, 1),)),
        Marking(((sink, 1),)),
    )
    return finish(
        ComputeStatus.COMPUTED,
        TransitionBorderedConversion(net, PROFILE, digest, tuple(borders)),
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "case-tree-transition-bordered",
        TransitionBorderedRequest,
        TransitionBorderedConversion,
    ),
}

__all__ = (
    "TransitionBorderedSpec",
    "TransitionBorderedRequest",
    "TreeTransitionBorder",
    "TransitionBorderedConversion",
    "tree_to_transition_bordered_petri_net",
)
