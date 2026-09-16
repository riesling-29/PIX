"""Finite-visible-horizon anti/multi alignment on accepting weighted Petri nets.

The search uses exact token markings, including silent transitions, rather than
flattening concurrency into an activity graph. A completed search optimizes the
accepted words of length at most ``max_length``. This is not an unbounded
anti/multi alignment guarantee or a claim of another library's numerical parity.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.sequence_alignment import SequenceAlignmentSpec, _edit
from pix.compute._common import _result
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import TraceSet
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class BoundedPetriNetLanguageSpec:
    """Explicit horizon, directed edit costs and resource ceilings.

    Distances transform each observed case into the candidate model word.
    Matches cost zero; None forbids substitution. Silent firings do not incur
    edit cost or consume the visible horizon. max_states bounds admitted
    (word, marking) states, including the initial state. max_total_cells bounds
    cumulative DP cells, including boundary cells, across candidate/case pairs.
    """

    max_length: int
    log_move_cost: int = 1
    model_move_cost: int = 1
    substitution_cost: int | None = 1
    max_states: int = 100_000
    max_total_cells: int = 10_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.max_length, "max_length")
        _integer(self.log_move_cost, "log_move_cost")
        _integer(self.model_move_cost, "model_move_cost")
        if self.substitution_cost is not None:
            _integer(self.substitution_cost, "substitution_cost")
        _integer(self.max_states, "max_states", 1)
        _integer(self.max_total_cells, "max_total_cells", 1)


@dataclass(frozen=True, slots=True)
class BoundedPetriNetLanguageRequest:
    model_digest: str
    objective: Literal["anti_max_min", "multi_min_sum"]
    parameters: BoundedPetriNetLanguageSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class PetriNetLanguageCandidate:
    activities: tuple[str, ...]
    transition_ids: tuple[str, ...]
    objective_value: int
    case_distances: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BoundedPetriNetLanguageAlignment:
    """Tied best evaluated words and the evidence needed to interpret them.

    Witnesses always fire legally from the initial to the exact final marking.
    If language_complete, each witness has the fewest firings for its word,
    breaking ties lexicographically by transition ID. Without completeness,
    witnesses and objectives are incumbents, never certified optimal results.
    accepted_words counts discovered accepted words; evaluations_complete means
    all of those words were evaluated, even if language_complete is false.
    """

    status: Literal["optimal_within_horizon", "empty_bounded_language", "search_limit"]
    candidates: tuple[PetriNetLanguageCandidate, ...]
    accepted_words: int
    evaluated_words: int
    discovered_states: int
    expanded_states: int
    evaluated_cells: int
    observed_cases: int
    language_complete: bool
    evaluations_complete: bool


def _enumerate(
    net: PetriNet, spec: BoundedPetriNetLanguageSpec
) -> tuple[dict[tuple[str, ...], tuple[str, ...]], int, int, bool]:
    """BFS with lexicographic edges; state identity retains the complete word.

    Marking alone would merge distinct words, while visible length alone would
    merge different token configurations. Deduplicating the joint state safely
    terminates bounded silent cycles. Unbounded silent token growth can still
    exhaust the state ceiling and must leave completeness unknown.
    """
    initial: tuple[tuple[str, ...], Marking] = ((), net.initial_marking)
    parents = {initial: None}
    queue = deque((initial,))
    activities = {transition.id: transition.activity for transition in net.transitions}
    accepted_states: dict[tuple[str, ...], tuple[tuple[str, ...], Marking]] = {}
    limited, expanded = False, 0
    while queue:
        state = queue.popleft()
        word, marking = state
        expanded += 1
        if marking == net.final_marking:
            accepted_states[word] = state
        for transition_id in sorted(enabled_transitions(net, marking)):
            activity = activities[transition_id]
            if activity is not None and len(word) >= spec.max_length:
                continue
            following_word = word if activity is None else word + (activity,)
            following = (following_word, fire(net, marking, transition_id))
            if following in parents:
                continue
            if len(parents) >= spec.max_states:
                limited = True
                continue
            parents[following] = (state, transition_id)
            queue.append(following)
    accepted = {}
    for word, state in accepted_states.items():
        reverse_witness = []
        while parents[state] is not None:
            state, transition_id = parents[state]
            reverse_witness.append(transition_id)
        accepted[word] = tuple(reversed(reverse_witness))
    return accepted, len(parents), expanded, not limited


def _bounded_language(log, net, spec, objective):
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, BoundedPetriNetLanguageSpec):
        raise TypeError("spec must be BoundedPetriNetLanguageSpec")
    traces = as_case_traces(log)
    operator = "pix.case_centric.bounded_petri_net_" + (
        "anti_alignment" if objective == "anti_max_min" else "multi_alignment"
    )
    request = BoundedPetriNetLanguageRequest(model_digest(net), objective, spec)
    parents = (traces.computation_id,) if traces.computation_id is not None else ()

    def result(status, value=None, issues=()):
        return _result(
            operator,
            None,
            request,
            status,
            value,
            traces.issues + issues,
            source_digest=traces.source_digest,
            parent_computation_ids=parents,
        )

    if traces.status is not ComputeStatus.COMPUTED or not isinstance(
        traces.value, TraceSet
    ):
        return result(
            ComputeStatus.INVALID_INPUT
            if traces.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "trace_result_unavailable", "Completed traces are required"
                ),
            ),
        )
    if not traces.value.traces:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "empty_observed_population",
                    "Both objective profiles require at least one observed case",
                ),
            ),
        )
    observed = tuple(
        (trace.object_id, tuple(event.activity for event in trace.events))
        for trace in traces.value.traces
    )
    accepted, discovered, expanded, language_complete = _enumerate(net, spec)
    edit_spec = SequenceAlignmentSpec(
        spec.log_move_cost,
        spec.model_move_cost,
        spec.substitution_cost,
        spec.max_total_cells,
    )
    best, candidates, evaluated, cells = None, [], 0, 0
    evaluations_complete = True
    for word, witness in sorted(accepted.items()):
        required = sum((len(values) + 1) * (len(word) + 1) for _, values in observed)
        if cells + required > spec.max_total_cells:
            evaluations_complete = False
            break
        # _edit is shared internal weighted sequence DP; no graph approximation
        # or external process-mining implementation is invoked here.
        distances = tuple(
            (case_id, _edit(values, word, edit_spec)[0]) for case_id, values in observed
        )
        cells += required
        evaluated += 1
        score = (
            min(value for _, value in distances)
            if objective == "anti_max_min"
            else sum(value for _, value in distances)
        )
        candidate = PetriNetLanguageCandidate(word, witness, score, distances)
        better = best is None or (
            score > best if objective == "anti_max_min" else score < best
        )
        if better:
            best, candidates = score, [candidate]
        elif score == best:
            candidates.append(candidate)
    limited = not language_complete or not evaluations_complete
    status = (
        "search_limit"
        if limited
        else ("optimal_within_horizon" if evaluated else "empty_bounded_language")
    )
    value = BoundedPetriNetLanguageAlignment(
        status,
        tuple(candidates),
        len(accepted),
        evaluated,
        discovered,
        expanded,
        cells,
        len(observed),
        language_complete,
        evaluations_complete,
    )
    issues = []
    if not language_complete:
        issues.append(
            ComputeIssue(
                "petri_net_language_state_limit",
                "Only admitted states were explored; bounded optimality, empty language, "
                "complete ties and globally shortest witnesses remain unproven",
            )
        )
    if not evaluations_complete:
        issues.append(
            ComputeIssue(
                "petri_net_language_cell_limit",
                "Not every discovered word was evaluated; candidates are incumbents only",
            )
        )
    return result(
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
    )


def bounded_petri_net_anti_alignment(
    log: CaseInput,
    net: PetriNet,
    spec: BoundedPetriNetLanguageSpec,
) -> ComputationResult[BoundedPetriNetLanguageAlignment]:
    """Maximize minimum directed edit distance within the visible horizon."""
    return _bounded_language(log, net, spec, "anti_max_min")


def bounded_petri_net_multi_alignment(
    log: CaseInput,
    net: PetriNet,
    spec: BoundedPetriNetLanguageSpec,
) -> ComputationResult[BoundedPetriNetLanguageAlignment]:
    """Minimize summed directed edit distance, preserving case multiplicity."""
    return _bounded_language(log, net, spec, "multi_min_sum")


RESULT_SCHEMAS = {
    "pix.case_centric.bounded_petri_net_anti_alignment": (
        "case_bounded_petri_net_language_alignment",
        BoundedPetriNetLanguageRequest,
        BoundedPetriNetLanguageAlignment,
    ),
    "pix.case_centric.bounded_petri_net_multi_alignment": (
        "case_bounded_petri_net_language_alignment",
        BoundedPetriNetLanguageRequest,
        BoundedPetriNetLanguageAlignment,
    ),
}

__all__ = (
    "BoundedPetriNetLanguageSpec",
    "BoundedPetriNetLanguageRequest",
    "PetriNetLanguageCandidate",
    "BoundedPetriNetLanguageAlignment",
    "bounded_petri_net_anti_alignment",
    "bounded_petri_net_multi_alignment",
)
