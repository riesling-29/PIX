"""Observed DFG footprints and Alpha/Heuristics relation selection.

Bidirectional adjacency is a footprint convention, not evidence of physical
concurrency. DFG files do not supply minimum trace length or empty-trace counts.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations
from math import isfinite

from pix.compute._common import _result
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.model_io.dfg import DFGFile, dumps_dfg


@dataclass(frozen=True, slots=True)
class DFGRelationSpec:
    method: str = "alpha"
    dependency_threshold: float = 0.0
    max_activity_pairs: int = 1_000_000

    def __post_init__(self):
        if self.method not in ("alpha", "heuristics"):
            raise ValueError("method must be alpha or heuristics")
        value = self.dependency_threshold
        if (
            type(value) not in (float, int)
            or not isfinite(value)
            or not -1 <= value <= 1
        ):
            raise ValueError("dependency_threshold must be finite in [-1,1]")
        object.__setattr__(self, "dependency_threshold", float(value))
        if self.method == "alpha" and value != 0:
            raise ValueError("Alpha does not use a dependency threshold")
        if type(self.max_activity_pairs) is not int or self.max_activity_pairs < 1:
            raise ValueError("max_activity_pairs must be positive")


@dataclass(frozen=True, slots=True)
class DFGRelationRequest:
    graph: DFGFile
    parameters: DFGRelationSpec

    def __post_init__(self):
        if not isinstance(self.graph, DFGFile) or not isinstance(
            self.parameters, DFGRelationSpec
        ):
            raise TypeError("invalid DFG relation request")


@dataclass(frozen=True, slots=True)
class CausalRelation:
    source: str
    target: str
    forward_count: int
    reverse_count: int
    score: float


@dataclass(frozen=True, slots=True)
class DFGRelations:
    activities: tuple[str, ...]
    directly_follows: tuple[tuple[str, str], ...]
    causal: tuple[CausalRelation, ...]
    parallel: tuple[tuple[str, str], ...]
    unrelated: tuple[tuple[str, str], ...]
    self_succession: tuple[str, ...]
    start_activities: tuple[str, ...]
    end_activities: tuple[str, ...]


def dfg_relations(graph: DFGFile, spec: DFGRelationSpec = DFGRelationSpec()):
    """Heuristics selects scores strictly greater than the explicit threshold.

    For distinct labels score=(forward-reverse)/(forward+reverse+1); self succession
    uses forward/(forward+1). Alpha selects only asymmetric observed adjacency.
    """
    request = DFGRelationRequest(graph, spec)
    source = "pix.dfg-frequency.v1:sha256:" + sha256(dumps_dfg(graph)).hexdigest()
    if (
        len(graph.activities) * (len(graph.activities) - 1) // 2
        > spec.max_activity_pairs
    ):
        return _result(
            "pix.case_centric.dfg_relations",
            None,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("activity_pair_limit", "Footprint pair limit exceeded"),),
            source_digest=source,
        )
    counts = {(a, b): n for a, b, n in graph.edges}
    causal = []
    for (a, b), forward in sorted(counts.items()):
        reverse = counts.get((b, a), 0)
        score = float(
            forward / (forward + 1)
            if a == b
            else (forward - reverse) / (forward + reverse + 1)
        )
        if (spec.method == "alpha" and reverse == 0) or (
            spec.method == "heuristics" and score > spec.dependency_threshold
        ):
            causal.append(
                CausalRelation(
                    a,
                    b,
                    forward,
                    reverse,
                    score if spec.method == "heuristics" else 1.0,
                )
            )
    activities = tuple(sorted(graph.activities))
    value = DFGRelations(
        activities,
        tuple(sorted(counts)),
        tuple(causal),
        tuple(sorted((a, b) for a, b in counts if a != b and (b, a) in counts)),
        tuple(
            (a, b)
            for a, b in combinations(activities, 2)
            if (a, b) not in counts and (b, a) not in counts
        ),
        tuple(a for a in activities if (a, a) in counts),
        tuple(sorted(a for a, _ in graph.start_counts)),
        tuple(sorted(a for a, _ in graph.end_counts)),
    )
    return _result(
        "pix.case_centric.dfg_relations",
        None,
        request,
        ComputeStatus.COMPUTED,
        value,
        source_digest=source,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.dfg_relations": (
        "case-dfg-relations",
        DFGRelationRequest,
        DFGRelations,
    )
}
__all__ = [
    "DFGRelationSpec",
    "DFGRelationRequest",
    "CausalRelation",
    "DFGRelations",
    "dfg_relations",
]
