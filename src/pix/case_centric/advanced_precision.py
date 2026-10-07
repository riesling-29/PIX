"""DFG legal-prefix and aligned-model-automaton precision are distinct metrics.

The first metric uses raw observed prefixes and DFG edges. The second aligns
complete cases, projects the model side (including visible model-only moves),
and builds a weighted prefix automaton from those projected executions. Neither
metric counts termination as an action. Scores are exact rational pairs; a zero
denominator is undefined, rather than an automatic score of one.

These are native PIX semantic profiles. Alignment tie choices follow PIX's
deterministic Dijkstra, and no blanket soundness assertion is made for the net.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.sequence_alignment import DFGAlignmentModel
from pix.compute._common import _result
from pix.compute.conformance import align_traces
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import TraceSet
from pix.contracts.conformance import AlignmentSet, AlignmentSpec
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

Ratio = tuple[int, int]


def _ratio(enabled: int, escaping: int) -> Ratio | None:
    if not enabled:
        return None
    value = Fraction(enabled - escaping, enabled)
    return value.numerator, value.denominator


def _parents(source: ComputationResult) -> tuple[str, ...]:
    return (source.computation_id,) if source.computation_id is not None else ()


def _invalid(source: ComputationResult, operator: str, request: object):
    if source.status is ComputeStatus.COMPUTED and isinstance(source.value, TraceSet):
        return None
    return _result(
        operator,
        None,
        request,
        ComputeStatus.INVALID_INPUT
        if source.status is ComputeStatus.INVALID_INPUT
        else ComputeStatus.UNAVAILABLE,
        None,
        source.issues
        + (
            ComputeIssue(
                "trace_result_unavailable", "A completed TraceSet is required"
            ),
        ),
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class DFGPrecisionSpec:
    """Only prefixes followed by a recorded event participate.

    Empty cases do not visit a prefix; the full trace is not visited. End nodes
    and empty-word acceptance do not add termination actions to the denominator.
    """

    termination: Literal["excluded"] = "excluded"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.termination != "excluded":
            raise ValueError("this profile excludes termination actions")


@dataclass(frozen=True, slots=True)
class DFGPrecisionRequest:
    model: DFGAlignmentModel
    parameters: DFGPrecisionSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DFGPrefixPrecision:
    prefix: tuple[str, ...]
    case_ids: tuple[str, ...]
    weight: int
    observed_labels: tuple[str, ...]
    status: Literal["computed", "unfit_start", "unfit_edge", "no_outgoing"]
    enabled_labels: tuple[str, ...] | None
    escaping_labels: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class DFGPrecision:
    prefixes: tuple[DFGPrefixPrecision, ...]
    requested_cases: int
    empty_cases: int
    computed_prefix_count: int
    excluded_prefix_count: int
    computed_weight: int
    excluded_weight: int
    weighted_enabled: int
    weighted_escaping: int
    computed_prefix_ratio: Ratio | None
    whole_population_ratio: Ratio | None
    profile: str = (
        "raw_legal_extension_prefixes_no_terminal_actions_no_empty_case_root_visits"
    )


def measure_dfg_precision(
    log: CaseInput,
    model: DFGAlignmentModel,
    spec: DFGPrecisionSpec = DFGPrecisionSpec(),
) -> ComputationResult[DFGPrecision]:
    """Occurrence-weighted legal-prefix escaping-edge precision of a DFG.

    An observed next activity outside the available set is a fitness deviation,
    not an escaping model edge. Illegal prefixes and sink prefixes are retained
    as excluded evidence; the whole-population ratio is withheld if any exist.
    No DFG edge weight is used as a proxy for observed prefix multiplicity.
    """
    if not isinstance(model, DFGAlignmentModel):
        raise TypeError("model must be DFGAlignmentModel")
    if not isinstance(spec, DFGPrecisionSpec):
        raise TypeError("spec must be DFGPrecisionSpec")
    source = as_case_traces(log)
    request = DFGPrecisionRequest(model, spec)
    operator = "pix.case_centric.dfg_precision"
    invalid = _invalid(source, operator, request)
    if invalid is not None:
        return invalid
    visits, observed = {}, {}
    for trace in source.value.traces:
        prefix = ()
        for event in trace.events:
            visits.setdefault(prefix, []).append(trace.object_id)
            observed.setdefault(prefix, set()).add(event.activity)
            prefix += (event.activity,)
    successors = {label: set() for label in model.activities}
    for left, right in model.edges:
        successors[left].add(right)
    starts, edges = set(model.starts), set(model.edges)
    evidence = []
    for prefix in sorted(visits):
        status = "computed"
        if prefix:
            if prefix[0] not in starts:
                status = "unfit_start"
            elif any(pair not in edges for pair in zip(prefix, prefix[1:])):
                status = "unfit_edge"
            elif not successors.get(prefix[-1]):
                status = "no_outgoing"
        available = (
            (starts if not prefix else successors[prefix[-1]])
            if status == "computed"
            else None
        )
        evidence.append(
            DFGPrefixPrecision(
                prefix,
                tuple(visits[prefix]),
                len(visits[prefix]),
                tuple(sorted(observed[prefix])),
                status,
                tuple(sorted(available)) if available is not None else None,
                tuple(sorted(available - observed[prefix]))
                if available is not None
                else None,
            )
        )
    computed = tuple(item for item in evidence if item.status == "computed")
    excluded = tuple(item for item in evidence if item.status != "computed")
    enabled = sum(item.weight * len(item.enabled_labels) for item in computed)
    escaping = sum(item.weight * len(item.escaping_labels) for item in computed)
    score = _ratio(enabled, escaping)
    value = DFGPrecision(
        tuple(evidence),
        len(source.value.traces),
        sum(not trace.events for trace in source.value.traces),
        len(computed),
        len(excluded),
        sum(item.weight for item in computed),
        sum(item.weight for item in excluded),
        enabled,
        escaping,
        score,
        score if not excluded else None,
    )
    issues = source.issues + tuple(
        ComputeIssue(
            "dfg_prefix_excluded",
            item.status,
            ("prefix", *item.prefix),
        )
        for item in excluded
    )
    return _result(
        operator,
        None,
        request,
        ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class AutomatonPrecisionSpec:
    """One optimal model projection per case; all encountered markings are united.

    symbol_mode='activity' merges duplicate visible labels; 'transition_id'
    distinguishes task identities. Silent transitions never become symbols.
    max_closure_states bounds each prefix's union of silent-reachable markings.
    """

    alignment: AlignmentSpec = AlignmentSpec()
    symbol_mode: Literal["activity", "transition_id"] = "activity"
    max_closure_states: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.alignment, AlignmentSpec):
            raise TypeError("alignment must be AlignmentSpec")
        if self.symbol_mode not in ("activity", "transition_id"):
            raise ValueError("symbol_mode must be activity or transition_id")
        if type(self.max_closure_states) is not int or self.max_closure_states < 1:
            raise ValueError("max_closure_states must be a positive integer")


@dataclass(frozen=True, slots=True)
class AutomatonPrecisionRequest:
    model_digest: str
    parameters: AutomatonPrecisionSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class AlignedModelProjection:
    case_id: str
    status: Literal["optimal", "unreachable", "search_limit"]
    symbols: tuple[str, ...] | None
    visible_transition_ids: tuple[str, ...] | None
    alignment_cost: int | None


@dataclass(frozen=True, slots=True)
class AutomatonPrefixPrecision:
    prefix: tuple[str, ...]
    case_ids: tuple[str, ...]
    weight: int
    executed_symbols: tuple[str, ...]
    reached_markings: tuple[Marking, ...]
    status: Literal["computed", "search_limit"]
    enabled_symbols: tuple[str, ...] | None
    escaping_symbols: tuple[str, ...] | None
    explored_closure_markings: int


@dataclass(frozen=True, slots=True)
class AutomatonPrecision:
    model_digest: str
    projections: tuple[AlignedModelProjection, ...]
    prefixes: tuple[AutomatonPrefixPrecision, ...]
    requested_cases: int
    aligned_cases: int
    unreachable_cases: int
    limited_alignment_cases: int
    limited_prefixes: int
    weighted_enabled: int
    weighted_escaping: int
    computed_prefix_ratio: Ratio | None
    whole_population_ratio: Ratio | None
    alignment_evidence: AlignmentSet
    profile: str = (
        "optimal_model_projection_automaton_actual_marking_union_no_termination"
    )


def _visible_symbols(
    net: PetriNet, markings: set[Marking], spec: AutomatonPrecisionSpec
):
    if len(markings) > spec.max_closure_states:
        return None, 0
    symbols = {transition.id: transition.activity for transition in net.transitions}
    queue = deque(sorted(markings, key=lambda marking: marking.tokens))
    seen, available = set(markings), set()
    while queue:
        marking = queue.popleft()
        for transition in enabled_transitions(net, marking):
            if symbols[transition] is not None:
                available.add(
                    transition
                    if spec.symbol_mode == "transition_id"
                    else symbols[transition]
                )
                continue
            following = fire(net, marking, transition)
            if following not in seen:
                if len(seen) >= spec.max_closure_states:
                    return None, len(seen)
                seen.add(following)
                queue.append(following)
    return tuple(sorted(available)), len(seen)


def measure_automaton_precision(
    log: CaseInput,
    net: PetriNet,
    spec: AutomatonPrecisionSpec = AutomatonPrecisionSpec(),
) -> ComputationResult[AutomatonPrecision]:
    """Aligned-model-prefix automaton precision, distinct from raw-prefix ET.

    Model-only visible moves participate, log-only moves disappear, and silent
    moves affect reached markings. Enabled symbols are collected over the full
    silent closure of the actual marking union for each projected prefix.

    The root weighs every aligned case, including an empty model projection;
    nonempty full projections are excluded as terminal prefixes. Unreachable or
    limited cases, or an incomplete closure, prevent a whole-population score.
    A computed-prefix ratio describes only the explicitly retained population.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, AutomatonPrecisionSpec):
        raise TypeError("spec must be AutomatonPrecisionSpec")
    source = as_case_traces(log)
    request = AutomatonPrecisionRequest(model_digest(net), spec)
    operator = "pix.case_centric.automaton_precision"
    invalid = _invalid(source, operator, request)
    if invalid is not None:
        return invalid
    alignment = align_traces(source, net, spec.alignment)
    aligned = tuple(
        item for item in alignment.value.alignments if item.status == "optimal"
    )
    visits = {(): [item.object_id for item in aligned]} if aligned else {}
    executed = {(): set()} if aligned else {}
    markings = {(): {net.initial_marking}} if aligned else {}
    projections = []
    for item in alignment.value.alignments:
        if item.status != "optimal":
            projections.append(
                AlignedModelProjection(item.object_id, item.status, None, None, None)
            )
            continue
        visible = tuple(
            move
            for move in item.moves
            if move.transition_id is not None and move.activity is not None
        )
        word = tuple(
            move.transition_id if spec.symbol_mode == "transition_id" else move.activity
            for move in visible
        )
        projections.append(
            AlignedModelProjection(
                item.object_id,
                "optimal",
                word,
                tuple(move.transition_id for move in visible),
                item.cost,
            )
        )
        if word:
            executed[()].add(word[0])
        for index in range(1, len(word)):
            prefix = word[:index]
            visits.setdefault(prefix, []).append(item.object_id)
            executed.setdefault(prefix, set()).add(word[index])
            markings.setdefault(prefix, set()).add(
                Marking(visible[index - 1].after_marking)
            )
    evidence = []
    for prefix in sorted(visits):
        available, count = _visible_symbols(net, markings[prefix], spec)
        evidence.append(
            AutomatonPrefixPrecision(
                prefix,
                tuple(visits[prefix]),
                len(visits[prefix]),
                tuple(sorted(executed[prefix])),
                tuple(sorted(markings[prefix], key=lambda marking: marking.tokens)),
                "computed" if available is not None else "search_limit",
                available,
                tuple(sorted(set(available) - executed[prefix]))
                if available is not None
                else None,
                count,
            )
        )
    computed = tuple(item for item in evidence if item.status == "computed")
    limited = tuple(item for item in evidence if item.status == "search_limit")
    enabled = sum(item.weight * len(item.enabled_symbols) for item in computed)
    escaping = sum(item.weight * len(item.escaping_symbols) for item in computed)
    unreachable = sum(
        item.status == "unreachable" for item in alignment.value.alignments
    )
    limited_alignments = sum(
        item.status == "search_limit" for item in alignment.value.alignments
    )
    score = _ratio(enabled, escaping)
    complete = not (unreachable or limited_alignments or limited)
    value = AutomatonPrecision(
        request.model_digest,
        tuple(projections),
        tuple(evidence),
        len(alignment.value.alignments),
        len(aligned),
        unreachable,
        limited_alignments,
        len(limited),
        enabled,
        escaping,
        score,
        score if complete else None,
        alignment.value,
    )
    issues = (
        source.issues
        + alignment.issues
        + tuple(
            ComputeIssue(
                "automaton_silent_closure_limit",
                "Available symbols are unknown",
                ("prefix", *item.prefix),
            )
            for item in limited
        )
    )
    if unreachable:
        issues += (
            ComputeIssue(
                "automaton_unreachable_cases",
                "Cases without accepting alignments are excluded from the automaton",
            ),
        )
    return _result(
        operator,
        None,
        request,
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL,
        value,
        issues,
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.dfg_precision": (
        "case-dfg-precision",
        DFGPrecisionRequest,
        DFGPrecision,
    ),
    "pix.case_centric.automaton_precision": (
        "case-automaton-precision",
        AutomatonPrecisionRequest,
        AutomatonPrecision,
    ),
}

__all__ = (
    "DFGPrecisionSpec",
    "DFGPrecisionRequest",
    "DFGPrefixPrecision",
    "DFGPrecision",
    "measure_dfg_precision",
    "AutomatonPrecisionSpec",
    "AutomatonPrecisionRequest",
    "AlignedModelProjection",
    "AutomatonPrefixPrecision",
    "AutomatonPrecision",
    "measure_automaton_precision",
)
