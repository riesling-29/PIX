"""Immutable evidence for deterministic, heuristic place/transition token replay.

Markings here are standard-library tuples rather than executable model objects.
Counts include initial token production and final-marking consumption. Limited
prefix counts are separate from totals for completed traces; neither is fitness.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

TokenSnapshot = tuple[tuple[str, int], ...]


def _positive_integer(value: object, name: str, *, minimum: int = 0) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class ReplaySpec:
    """Bound silent closure per event and finalization, including its start state.

    Enabled activity matches use shortest silent paths, then lexical transition
    IDs. If closure exhausts without a match, choose least inserted tokens, then
    shortest/lexical silent path and transition ID. These local choices are not
    a globally optimal alignment. A truncated closure never proves unreachability.
    """

    # Already admitted states are checked even when a further state exceeds this cap.
    silent_max_states: int = 1000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _positive_integer(self.silent_max_states, "silent_max_states", minimum=1)


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    model_digest: str
    parameters: ReplaySpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TokenCounts:
    missing: int = 0
    remaining: int = 0
    consumed: int = 0
    produced: int = 0

    def __post_init__(self) -> None:
        for name in ("missing", "remaining", "consumed", "produced"):
            _positive_integer(getattr(self, name), name)
        if self.produced + self.missing != self.consumed + self.remaining:
            raise ValueError("token accounting must conserve produced + missing")


@dataclass(frozen=True, slots=True)
class ReplayStep:
    kind: Literal["initial", "visible", "silent", "log_deviation", "finalize"]
    event_id: str | None
    activity: str | None
    transition_id: str | None
    marking_before: TokenSnapshot
    marking_after: TokenSnapshot
    inserted_tokens: TokenSnapshot = ()
    consumed_tokens: TokenSnapshot = ()
    produced_tokens: TokenSnapshot = ()


@dataclass(frozen=True, slots=True)
class SilentSearch:
    """None event ID denotes final-marking search.

    state_count counts unique admitted markings, including the initial marking.
    exhaustive is false on either an early successful match or a state limit.
    """

    event_id: str | None
    state_count: int
    exhaustive: bool
    limited: bool


@dataclass(frozen=True, slots=True)
class TraceReplay:
    """Completed means the replay procedure finished, not that the trace fits.

    final_reached compares the reached marking with the exact target before
    finalization inserts/consumes tokens; earlier visible moves may already have
    required inserted tokens. None means final reachability was not determined.
    """

    object_id: str
    status: Literal["completed", "limited"]
    event_count: int
    processed_event_count: int
    log_deviation_count: int
    steps: tuple[ReplayStep, ...]
    searches: tuple[SilentSearch, ...]
    final_marking: TokenSnapshot
    ending_marking: TokenSnapshot
    final_reached: bool | None
    counts: TokenCounts
    limit_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ReplaySet:
    """Per-object occurrence replay against a classical net, not joint OCPN replay.

    attempted_counts include live residual tokens of limited prefixes. They must
    not be interpreted as whole-log totals or averaged together with completions.
    """

    object_type: str
    model_digest: str
    traces: tuple[TraceReplay, ...]
    trace_count: int
    completed_count: int
    limited_count: int
    excluded_count: int
    event_occurrence_count: int
    processed_event_count: int
    unprocessed_event_count: int
    log_deviation_count: int
    completed_counts: TokenCounts
    attempted_counts: TokenCounts


__all__ = (
    "ReplayRequest",
    "ReplaySet",
    "ReplaySpec",
    "ReplayStep",
    "SilentSearch",
    "TokenCounts",
    "TokenSnapshot",
    "TraceReplay",
)
