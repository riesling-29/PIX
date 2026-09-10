"""Native alignment contracts with explicit costs, coverage and search evidence.

An alignment is optimal only for its stated nonnegative integer cost profile.
This contract does not define normalized fitness, soundness or OCPN alignment.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

MarkingSnapshot = tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class AlignmentSpec:
    """Costs are integer profile units; max_states bounds settled product states.

    A state combines an event position and a marking. No equal-cost state is
    revisited. One deterministic minimum-cost path is returned, not all paths.
    """

    log_move_cost: int = 1
    model_move_cost: int = 1
    silent_move_cost: int = 0
    synchronous_move_cost: int = 0
    max_states: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in (
            "log_move_cost",
            "model_move_cost",
            "silent_move_cost",
            "synchronous_move_cost",
            "max_states",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            minimum = 1 if name == "max_states" else 0
            if value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class AlignmentRequest:
    """Resolved parameters, including the independently supplied model identity."""

    model_digest: str
    parameters: AlignmentSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlignmentMove:
    kind: Literal["synchronous", "silent", "model", "log"]
    event_id: str | None
    transition_id: str | None
    activity: str | None
    cost: int
    before_marking: MarkingSnapshot
    after_marking: MarkingSnapshot


@dataclass(frozen=True, slots=True)
class TraceAlignment:
    object_id: str
    event_ids: tuple[str, ...]
    status: Literal["optimal", "unreachable", "search_limit"]
    moves: tuple[AlignmentMove, ...]
    cost: int | None
    settled_states: int
    discovered_states: int
    lower_bound_cost: int | None


@dataclass(frozen=True, slots=True)
class AlignmentCoverage:
    requested: int
    optimal: int
    unreachable: int
    search_limit: int
    excluded: int = 0

    @property
    def completed(self) -> int:
        """Completed searches include proven absence of an accepting alignment."""
        return self.optimal + self.unreachable


@dataclass(frozen=True, slots=True)
class AlignmentSet:
    """Cost aggregates explicitly distinguish complete and partial populations.

    completed_cost_sum and mean_completed_cost_ratio cover optimal alignments,
    with coverage.optimal as the exact ratio's denominator. total_cost only if every
    requested trace has an optimal alignment. An empty population has sum zero
    but no mean. No result here is named fitness.
    """

    object_type: str
    model_digest: str
    source_trace_computation_id: str
    alignments: tuple[TraceAlignment, ...]
    coverage: AlignmentCoverage
    completed_cost_sum: int
    mean_completed_cost_ratio: tuple[int, int] | None
    total_cost: int | None
    cost_unit: str = "integer_cost_profile_units"


__all__ = (
    "AlignmentCoverage",
    "AlignmentMove",
    "AlignmentRequest",
    "AlignmentSet",
    "AlignmentSpec",
    "MarkingSnapshot",
    "TraceAlignment",
)
