"""Direct compositional process-tree alignment, without a Petri-net conversion.

Sequence uses interval splits, XOR selects a child, parallel allocates observed
occurrences to ordered child subsequences, and binary loops use a segment DAG.
Every cached key retains the full occurrence sequence and structural node path.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from hashlib import sha256
from itertools import product
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.contracts.analysis import TraceSet
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class TreeAlignmentSpec:
    log_move_cost: int = 1
    model_move_cost: int = 1
    synchronous_move_cost: int = 0
    silent_move_cost: int = 0
    max_subproblems: int = 20000
    max_candidates: int = 100000
    max_tree_depth: int = 128
    max_tree_nodes: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for field in (
            "log_move_cost",
            "model_move_cost",
            "synchronous_move_cost",
            "silent_move_cost",
            "max_subproblems",
            "max_candidates",
            "max_tree_depth",
            "max_tree_nodes",
        ):
            value = getattr(self, field)
            minimum = 1 if field.startswith("max_") else 0
            if type(value) is not int or value < minimum:
                raise ValueError(field + f" must be an integer >= {minimum}")
        if self.max_tree_depth > 128:
            raise ValueError("max_tree_depth must not exceed 128")


@dataclass(frozen=True, slots=True)
class TreeAlignmentRequest:
    model_digest: str
    parameters: TreeAlignmentSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TreeAlignmentMove:
    kind: Literal["synchronous", "model", "log", "silent"]
    event_index: int | None
    event_id: str | None
    node_path: tuple[int, ...] | None
    activity: str | None
    cost: int


@dataclass(frozen=True, slots=True)
class TreeTraceAlignment:
    case_id: str
    event_ids: tuple[str, ...]
    status: Literal["optimal", "search_limit"]
    cost: int | None
    moves: tuple[TreeAlignmentMove, ...]
    model_word: tuple[str, ...]
    subproblems: int
    candidates: int
    limit_reason: str | None


@dataclass(frozen=True, slots=True)
class TreeAlignmentSet:
    model_digest: str
    traces: tuple[TreeTraceAlignment, ...]
    requested_count: int
    optimal_count: int
    limited_count: int
    total_cost: int | None
    profile: str = "direct_compositional_exact_nonnegative_kind_costs"


class _Limit(Exception):
    pass


def _tree_digest(tree):
    payload = json.dumps(
        asdict(tree), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return (
        "pix.model.process-tree.dp.v1:sha256:"
        + sha256(payload.encode("utf-8")).hexdigest()
    )


class _DynamicProgram:
    def __init__(self, tree, trace, spec):
        self.tree, self.trace, self.spec = tree, trace, spec
        self.cache = {}
        self.subproblems = 0
        self.candidates = 0

    def candidate(self):
        if self.candidates >= self.spec.max_candidates:
            raise _Limit("candidate_budget")
        self.candidates += 1

    def log_moves(self, indices):
        return tuple(
            TreeAlignmentMove(
                "log",
                index,
                self.trace.events[index].event_id,
                None,
                self.trace.events[index].activity,
                self.spec.log_move_cost,
            )
            for index in indices
        )

    @staticmethod
    def best(current, candidate):
        return candidate if current is None or candidate[0] < current[0] else current

    def sequence(self, children, indices):
        # Each prefix of child list consumes a contiguous prefix of indices.
        frontier = {0: (0, ())}
        for path, child in children:
            following = {}
            for start, (prefix_cost, prefix_moves) in sorted(frontier.items()):
                for end in range(start, len(indices) + 1):
                    self.candidate()
                    child_cost, child_moves = self.cost(child, path, indices[start:end])
                    following[end] = self.best(
                        following.get(end),
                        (prefix_cost + child_cost, prefix_moves + child_moves),
                    )
            frontier = following
        return frontier[len(indices)]

    def parallel(self, children, indices):
        selected = None
        for assignment in product(range(len(children)), repeat=len(indices)):
            self.candidate()
            child_results = []
            for child_index, (path, child) in enumerate(children):
                owned = tuple(
                    index
                    for index, owner in zip(indices, assignment)
                    if owner == child_index
                )
                child_results.append(self.cost(child, path, owned))
            total = sum(item[0] for item in child_results)
            if selected is not None and total >= selected[0]:
                continue
            # Merge child alignments while preserving both each child's move
            # order and the original log occurrence order.
            moves = []
            cursors = [0] * len(children)
            for index, owner in zip(indices, assignment):
                child_moves = child_results[owner][1]
                cursor = cursors[owner]
                while child_moves[cursor].event_index is None:
                    moves.append(child_moves[cursor])
                    cursor += 1
                assert child_moves[cursor].event_index == index
                moves.append(child_moves[cursor])
                cursors[owner] = cursor + 1
            for cursor, (_, child_moves) in zip(cursors, child_results):
                moves.extend(child_moves[cursor:])
            selected = total, tuple(moves)
        assert selected is not None
        return selected

    def loop(self, children, indices):
        # Language do (redo do)*. Remove any complete redo/do cycle consuming
        # no observed occurrence: the remaining run is legal and cannot cost
        # more under nonnegative move costs. Thus every retained cycle consumes
        # a nonempty interval and the recurrence is acyclic in trace position.
        do_path, do = children[0]
        frontier = {}
        for end in range(len(indices) + 1):
            self.candidate()
            frontier[end] = self.cost(do, do_path, indices[:end])
        cycle = (children[1], children[0])
        for start in range(len(indices)):
            prefix_cost, prefix_moves = frontier[start]
            for end in range(start + 1, len(indices) + 1):
                self.candidate()
                cycle_cost, cycle_moves = self.sequence(cycle, indices[start:end])
                frontier[end] = self.best(
                    frontier[end],
                    (prefix_cost + cycle_cost, prefix_moves + cycle_moves),
                )
        return frontier[len(indices)]

    def cost(self, tree, path, indices):
        key = path, indices
        if key in self.cache:
            return self.cache[key]
        if self.subproblems >= self.spec.max_subproblems:
            raise _Limit("subproblem_budget")
        self.subproblems += 1
        if tree.operator == "tau":
            moves = self.log_moves(indices) + (
                TreeAlignmentMove(
                    "silent", None, None, path, None, self.spec.silent_move_cost
                ),
            )
            result = (
                len(indices) * self.spec.log_move_cost + self.spec.silent_move_cost,
                moves,
            )
        elif tree.operator == "activity":
            result = (
                len(indices) * self.spec.log_move_cost + self.spec.model_move_cost,
                self.log_moves(indices)
                + (
                    TreeAlignmentMove(
                        "model",
                        None,
                        None,
                        path,
                        tree.activity,
                        self.spec.model_move_cost,
                    ),
                ),
            )
            for position, index in enumerate(indices):
                if self.trace.events[index].activity == tree.activity:
                    self.candidate()
                    moves = (
                        self.log_moves(indices[:position])
                        + (
                            TreeAlignmentMove(
                                "synchronous",
                                index,
                                self.trace.events[index].event_id,
                                path,
                                tree.activity,
                                self.spec.synchronous_move_cost,
                            ),
                        )
                        + self.log_moves(indices[position + 1 :])
                    )
                    result = self.best(
                        result,
                        (
                            (len(indices) - 1) * self.spec.log_move_cost
                            + self.spec.synchronous_move_cost,
                            moves,
                        ),
                    )
        else:
            children = tuple(
                (path + (index,), child) for index, child in enumerate(tree.children)
            )
            if tree.operator == "sequence":
                result = self.sequence(children, indices)
            elif tree.operator == "parallel":
                result = self.parallel(children, indices)
            elif tree.operator == "loop":
                result = self.loop(children, indices)
            else:
                result = None
                for child_path, child in children:
                    self.candidate()
                    result = self.best(result, self.cost(child, child_path, indices))
                assert result is not None
        self.cache[key] = result
        return result

    def run(self):
        try:
            cost, moves = self.cost(self.tree, (), tuple(range(len(self.trace.events))))
            return TreeTraceAlignment(
                self.trace.object_id,
                tuple(event.event_id for event in self.trace.events),
                "optimal",
                cost,
                moves,
                tuple(
                    move.activity
                    for move in moves
                    if move.kind in ("synchronous", "model")
                ),
                self.subproblems,
                self.candidates,
                None,
            )
        except _Limit as error:
            return TreeTraceAlignment(
                self.trace.object_id,
                tuple(event.event_id for event in self.trace.events),
                "search_limit",
                None,
                (),
                (),
                self.subproblems,
                self.candidates,
                str(error),
            )


def align_process_tree_dp(
    log: CaseInput, tree: ProcessTree, spec: TreeAlignmentSpec = TreeAlignmentSpec()
) -> ComputationResult[TreeAlignmentSet]:
    """Exact direct alignment for sequence/XOR/parallel/binary-loop trees.

    Parallel allocations can be exponential; computation budgets produce
    explicit unknown results. No bounded-language truncation is used for loops:
    nonnegative costs justify eliminating cycles with no log occurrence.
    """
    if not isinstance(tree, ProcessTree):
        raise TypeError("tree must be ProcessTree")
    if not isinstance(spec, TreeAlignmentSpec):
        raise TypeError("spec must be TreeAlignmentSpec")
    source = as_case_traces(log)
    parents = (source.computation_id,) if source.computation_id is not None else ()
    pending = [(tree, 0)]
    nodes_seen = 0
    depth_exceeded = False
    while pending:
        node, depth = pending.pop()
        nodes_seen += 1
        if nodes_seen + len(pending) + len(node.children) > spec.max_tree_nodes:
            raise ValueError("tree exceeds the explicit max_tree_nodes")
        if depth > spec.max_tree_depth:
            depth_exceeded = True
            break
        pending.extend((child, depth + 1) for child in node.children)
    # Very deep recursive dataclass trees cannot be safely canonicalized. A
    # depth failure is an explicit exception before digest construction.
    if depth_exceeded:
        raise ValueError("tree exceeds the explicit max_tree_depth")
    digest = _tree_digest(tree)
    request = TreeAlignmentRequest(digest, spec)

    def result(status, value, issues=()):
        return _result(
            "pix.case_centric.process_tree_dp_alignment",
            None,
            request,
            status,
            value,
            source.issues + tuple(issues),
            source_digest=source.source_digest,
            parent_computation_ids=parents,
        )

    if source.status is not ComputeStatus.COMPUTED or not isinstance(
        source.value, TraceSet
    ):
        return result(
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "trace_result_unavailable", "Completed traces are required"
                ),
            ),
        )
    traces = tuple(
        _DynamicProgram(tree, trace, spec).run() for trace in source.value.traces
    )
    limited = sum(trace.status == "search_limit" for trace in traces)
    value = TreeAlignmentSet(
        digest,
        traces,
        len(traces),
        len(traces) - limited,
        limited,
        None if limited else sum(trace.cost for trace in traces),
    )
    issues = tuple(
        ComputeIssue(
            "tree_alignment_search_limit",
            "Direct DP budget exhausted; optimality unknown: " + trace.limit_reason,
            ("case", trace.case_id),
        )
        for trace in traces
        if trace.status == "search_limit"
    )
    return result(
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED, value, issues
    )


RESULT_SCHEMAS = {
    "pix.case_centric.process_tree_dp_alignment": (
        "case-process-tree-dp-alignment",
        TreeAlignmentRequest,
        TreeAlignmentSet,
    ),
}

__all__ = (
    "TreeAlignmentSpec",
    "TreeAlignmentRequest",
    "TreeAlignmentMove",
    "TreeTraceAlignment",
    "TreeAlignmentSet",
    "align_process_tree_dp",
)
