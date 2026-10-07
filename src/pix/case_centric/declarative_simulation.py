"""Native bounded Declare language generation and seeded rejection playout.

Every returned trace satisfies the model under closed finite-trace semantics.
Enumeration is depth-first in the declared alphabet order and certifies only
the requested length interval, never the unbounded language. Prefixes are
pruned solely on irreversible open-monitor violations; a pending obligation
is retained for possible fulfillment by later events.

Sampling draws a length uniformly, then each activity uniformly and
independently. Accepted words therefore have probability proportional to
``len(alphabet) ** -len(word)`` within the satisfying bounded population;
this is deliberately not uniform sampling of satisfying words of all lengths.
The source digest hashes the complete supplied DeclareModel, not an event log.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import ClassVar

from pix.case_centric.declarative import DeclareModel, _obligations
from pix.compute._common import _derived_result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

_MAX_EVENTS = 10_000


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _bounds(spec):
    _integer(spec.min_events, "min_events")
    _integer(spec.max_events, "max_events")
    if spec.min_events > spec.max_events or spec.max_events > _MAX_EVENTS:
        raise ValueError(f"require 0 <= min_events <= max_events <= {_MAX_EVENTS}")
    _integer(spec.max_traces, "max_traces", 1)
    _integer(spec.max_prefix_states, "max_prefix_states", 1)


@dataclass(frozen=True, slots=True)
class DeclareLanguageSpec:
    """Output cap and evaluation budget are distinct from the length domain."""

    SPEC_TYPE: ClassVar[str] = "pix.declare_language.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    min_events: int = 0
    max_events: int = 6
    max_traces: int = 10_000
    max_prefix_states: int = 100_000

    def __post_init__(self):
        _bounds(self)


@dataclass(frozen=True, slots=True)
class DeclareLanguageRequest:
    model: DeclareModel
    options: DeclareLanguageSpec


@dataclass(frozen=True, slots=True)
class DeclareLanguage:
    """``population_size`` is exact only when the bounded search completed.

    A complete empty result establishes emptiness inside the requested bounds;
    it is not a claim that no longer satisfying trace exists.
    """

    traces: tuple[tuple[str, ...], ...]
    evaluated_prefixes: int
    pruned_prefixes: int
    complete: bool
    population_size: int | None
    termination: str
    traversal: str = "depth-first-alphabet-order"


@dataclass(frozen=True, slots=True)
class DeclarePlayoutSpec:
    """Sample with replacement, retaining accepted proposals until a bound.

    ``max_traces`` is the requested number of accepted samples. Rejected
    proposals consume ``max_attempts``; prefix evaluation also has its own
    budget. Before drawing a proposal, capacity for ``max_events`` additional
    prefix evaluations is reserved. This conservative rule prevents a long
    candidate from being censored mid-evaluation and may leave budget unused.
    Neither budget implies the requested count will be reached.
    """

    SPEC_TYPE: ClassVar[str] = "pix.declare_playout.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    seed: int = 0
    min_events: int = 0
    max_events: int = 6
    max_traces: int = 100
    max_attempts: int = 10_000
    max_prefix_states: int = 100_000

    def __post_init__(self):
        _bounds(self)
        if type(self.seed) is not int:
            raise TypeError("seed must be an explicit integer")
        _integer(self.max_attempts, "max_attempts", 1)


@dataclass(frozen=True, slots=True)
class DeclarePlayoutRequest:
    model: DeclareModel
    options: DeclarePlayoutSpec


@dataclass(frozen=True, slots=True)
class DeclarePlayout:
    traces: tuple[tuple[str, ...], ...]
    attempted_proposals: int
    rejected_proposals: int
    interrupted_proposals: int
    evaluated_prefixes: int
    requested_traces: int
    requested_count_reached: bool
    empty_population_proven: bool
    population_size: int | None
    termination: str
    proposal_distribution: str = "uniform-length-then-iid-uniform-activity"
    accepted_distribution: str = "proposal-conditioned-on-closed-model-satisfaction"


def _source_digest(model):
    payload = json.dumps(
        asdict(model),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return "pix.declare-model.v1:sha256:" + sha256(payload.encode("utf-8")).hexdigest()


def _reject(sequence, model, *, closed):
    return any(
        obligation.state == "violated"
        for rule in model.rules
        for obligation in _obligations(sequence, rule, closed)
    )


def _result(operator, model, request, value, reason=None):
    issues = (
        ()
        if reason is None
        else (
            ComputeIssue(
                "declare_" + reason,
                "The evaluation budget ended before the declared calculation completed; "
                "returned traces satisfy all closed rules, but omitted behavior is unknown.",
            ),
        )
    )
    return _derived_result(
        operator,
        _source_digest(model),
        request,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
    )


def generate_declare_language(
    model: DeclareModel,
    spec: DeclareLanguageSpec = DeclareLanguageSpec(),
) -> ComputationResult[DeclareLanguage]:
    """Enumerate the satisfying finite language within inclusive length bounds.

    The first extra accepted word establishes an output-cap truncation; merely
    filling the output exactly does not turn an otherwise complete result into
    a partial result. One mutable path and a stack of child indices keep the
    search frontier proportional to depth, without retaining every prefix copy.
    """
    if type(model) is not DeclareModel or type(spec) is not DeclareLanguageSpec:
        raise TypeError("expected DeclareModel and DeclareLanguageSpec")
    accepted = []
    evaluated = pruned = 0
    reason = None
    path = []
    child_indices = [0]
    entering = True
    while child_indices:
        if entering:
            entering = False
            if evaluated >= spec.max_prefix_states:
                reason = "prefix_state_limit"
                break
            evaluated += 1
            violated = _reject(path, model, closed=False)
            if violated:
                pruned += 1
            elif len(path) >= spec.min_events and not _reject(path, model, closed=True):
                if len(accepted) >= spec.max_traces:
                    reason = "trace_limit"
                    break
                accepted.append(tuple(path))
            if violated or len(path) == spec.max_events:
                child_indices.pop()
                if path:
                    path.pop()
                continue
        if child_indices[-1] == len(model.activities):
            child_indices.pop()
            if path:
                path.pop()
        else:
            index = child_indices[-1]
            child_indices[-1] += 1
            path.append(model.activities[index])
            child_indices.append(0)
            entering = True
    complete = reason is None
    value = DeclareLanguage(
        tuple(accepted),
        evaluated,
        pruned,
        complete,
        len(accepted) if complete else None,
        reason or "bounded_language_complete",
    )
    return _result(
        "pix.case_centric.generate_declare_language",
        model,
        DeclareLanguageRequest(model, spec),
        value,
        reason,
    )


def play_out_declare(
    model: DeclareModel,
    spec: DeclarePlayoutSpec = DeclarePlayoutSpec(),
) -> ComputationResult[DeclarePlayout]:
    """Seeded finite-word rejection sampling with explicit stopping evidence.

    Complete candidates are drawn before prefix evaluation, so pruning does
    not change the proposal distribution or consume a variable number of
    random draws. The accepted population size is not estimated from samples.
    On an empty alphabet the only possible word is epsilon (if bounds allow).
    A rejection-budget failure does not prove that the bounded language is empty.
    """
    if type(model) is not DeclareModel or type(spec) is not DeclarePlayoutSpec:
        raise TypeError("expected DeclareModel and DeclarePlayoutSpec")
    request = DeclarePlayoutRequest(model, spec)
    accepted = []
    attempted = rejected = interrupted = evaluated = 0
    empty = not model.activities and spec.min_events > 0
    if not empty:
        evaluated = 1
        empty = _reject((), model, closed=False)
        if not empty and spec.max_events == 0:
            empty = _reject((), model, closed=True)
    population_size = (
        0 if empty else 1 if not model.activities or spec.max_events == 0 else None
    )
    if empty:
        value = DeclarePlayout(
            (),
            0,
            0,
            0,
            evaluated,
            spec.max_traces,
            False,
            True,
            0,
            "empty_bounded_population",
        )
        return _result("pix.case_centric.play_out_declare", model, request, value)

    rng = random.Random(spec.seed)
    reason = None
    for _ in range(spec.max_attempts):
        # Decide whether another complete proposal fits BEFORE drawing it.
        # Stopping after inspecting its length/activities would censor words
        # with an expensive evaluation and change the accepted distribution.
        reserve = spec.max_events if model.activities else 0
        if evaluated + reserve > spec.max_prefix_states:
            reason = "prefix_state_limit"
            break
        length = (
            rng.randint(spec.min_events, spec.max_events) if model.activities else 0
        )
        sequence = tuple(rng.choice(model.activities) for _ in range(length))
        attempted += 1
        violated = False
        for length in range(1, len(sequence) + 1):
            evaluated += 1
            if _reject(sequence[:length], model, closed=False):
                violated = True
                break
        if violated or _reject(sequence, model, closed=True):
            rejected += 1
        else:
            accepted.append(sequence)
            if len(accepted) == spec.max_traces:
                break
    filled = len(accepted) == spec.max_traces
    if not filled and reason is None:
        reason = "attempt_limit"
    value = DeclarePlayout(
        tuple(accepted),
        attempted,
        rejected,
        interrupted,
        evaluated,
        spec.max_traces,
        filled,
        False,
        population_size,
        reason or "requested_count_reached",
    )
    return _result("pix.case_centric.play_out_declare", model, request, value, reason)


RESULT_SCHEMAS = {
    "pix.case_centric.generate_declare_language": (
        "case-declare-language",
        DeclareLanguageRequest,
        DeclareLanguage,
    ),
    "pix.case_centric.play_out_declare": (
        "case-declare-playout",
        DeclarePlayoutRequest,
        DeclarePlayout,
    ),
}

__all__ = (
    "DeclareLanguageSpec",
    "DeclareLanguage",
    "DeclarePlayoutSpec",
    "DeclarePlayout",
    "generate_declare_language",
    "play_out_declare",
)
