"""Explicit declarative rules and trace-local observation evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{name} must be valid UTF-8 text") from exc


def _natural(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _binary(rule: object, kind: str) -> None:
    _text(rule.rule_id, "rule_id")
    _text(rule.activity, "activity")
    _text(rule.target, "target")
    if rule.kind != kind:
        raise ValueError(f"kind must be {kind!r}")


@dataclass(frozen=True, slots=True)
class CountRule:
    """Inclusive bounds; existence=(1,None), absence=(0,0), exactly n=(n,n)."""

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rule_id: str
    activity: str
    min_count: int = 0
    max_count: int | None = None
    kind: Literal["count"] = "count"

    def __post_init__(self) -> None:
        _text(self.rule_id, "rule_id")
        _text(self.activity, "activity")
        _natural(self.min_count, "min_count")
        if self.kind != "count":
            raise ValueError("kind must be 'count'")
        if self.max_count is not None:
            _natural(self.max_count, "max_count")
            if self.max_count < self.min_count:
                raise ValueError("max_count must be at least min_count")


@dataclass(frozen=True, slots=True)
class ResponseRule:
    """Each observed activity occurrence requires a strictly later target."""

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rule_id: str
    activity: str
    target: str
    kind: Literal["response"] = "response"

    def __post_init__(self) -> None:
        _binary(self, "response")


@dataclass(frozen=True, slots=True)
class PrecedenceRule:
    """Each observed target occurrence requires a strictly earlier activity."""

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rule_id: str
    activity: str
    target: str
    kind: Literal["precedence"] = "precedence"

    def __post_init__(self) -> None:
        _binary(self, "precedence")


@dataclass(frozen=True, slots=True)
class NotCoexistenceRule:
    """An object trace must not contain both labels; identical labels ban presence."""

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rule_id: str
    activity: str
    target: str
    kind: Literal["not_coexistence"] = "not_coexistence"

    def __post_init__(self) -> None:
        _binary(self, "not_coexistence")


@dataclass(frozen=True, slots=True)
class TimedResponseRule:
    """Inclusive microsecond window; any qualifying versus first later response.

    A target may fulfill several activations. A self-label never witnesses the
    same occurrence: its target must have a strictly later sequence index.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rule_id: str
    activity: str
    target: str
    min_microseconds: int
    max_microseconds: int
    response_selection: Literal["any", "first"]
    kind: Literal["timed_response"] = "timed_response"

    def __post_init__(self) -> None:
        _binary(self, "timed_response")
        _natural(self.min_microseconds, "min_microseconds")
        _natural(self.max_microseconds, "max_microseconds")
        if self.max_microseconds < self.min_microseconds:
            raise ValueError("max_microseconds must be at least min_microseconds")
        if self.response_selection not in ("any", "first"):
            raise ValueError("response_selection must be 'any' or 'first'")


ConstraintRule = (
    CountRule | ResponseRule | PrecedenceRule | NotCoexistenceRule | TimedResponseRule
)


@dataclass(frozen=True, slots=True)
class ConstraintSpec:
    """Closed declares complete object traces; open declares chronological prefixes.

    The observation assumption is required. Open extensions preserve the chosen
    nondecreasing-time order. Unobserved future activations are never counted.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    rules: tuple[ConstraintRule, ...]
    observation_policy: Literal["open", "closed"]

    def __post_init__(self) -> None:
        if not isinstance(self.rules, tuple) or not self.rules:
            raise ValueError("rules must be a nonempty tuple")
        supported = (
            CountRule,
            ResponseRule,
            PrecedenceRule,
            NotCoexistenceRule,
            TimedResponseRule,
        )
        if not all(type(rule) in supported for rule in self.rules):
            raise TypeError("rules must contain supported constraint contracts")
        if len({rule.rule_id for rule in self.rules}) != len(self.rules):
            raise ValueError("rule_id must be unique within a request")
        if self.observation_policy not in ("open", "closed"):
            raise ValueError("observation_policy must be 'open' or 'closed'")


@dataclass(frozen=True, slots=True)
class ConstraintWitness:
    """One counted obligation; None activation ID denotes an object obligation.

    Empty absence evidence must be interpreted against its full source trace
    and observation policy. Elapsed time is exact for a selected event pair.
    """

    status: Literal["fulfilled", "violated", "pending"]
    activation_event_id: str | None
    evidence_event_ids: tuple[str, ...]
    observed_count: int | None
    elapsed_microseconds: int | None
    reason: str


@dataclass(frozen=True, slots=True)
class TraceRuleEvaluation:
    object_id: str
    status: Literal["fulfilled", "violated", "pending"]
    activation_count: int
    fulfilled_count: int
    violated_count: int
    pending_count: int
    vacuous: bool
    witnesses: tuple[ConstraintWitness, ...]


@dataclass(frozen=True, slots=True)
class RuleEvaluation:
    rule_id: str
    kind: Literal[
        "count", "response", "precedence", "not_coexistence", "timed_response"
    ]
    population: Literal["object_traces", "activations"]
    activation_count: int
    fulfilled_count: int
    violated_count: int
    pending_count: int
    fulfillment_ratio: tuple[int, int] | None
    object_count: int
    fulfilled_object_count: int
    violated_object_count: int
    pending_object_count: int
    vacuous_object_count: int
    traces: tuple[TraceRuleEvaluation, ...]


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    object_type: str
    source_trace_computation_id: str
    observation_policy: Literal["open", "closed"]
    rules: tuple[RuleEvaluation, ...]


__all__ = (
    "ConstraintEvaluation",
    "ConstraintRule",
    "ConstraintSpec",
    "ConstraintWitness",
    "CountRule",
    "NotCoexistenceRule",
    "PrecedenceRule",
    "ResponseRule",
    "RuleEvaluation",
    "TimedResponseRule",
    "TraceRuleEvaluation",
)
