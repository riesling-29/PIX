"""Native case-centric quality metrics with explicit populations and evidence.

The arithmetic follows named metric families, but replay choices are PIX's
deterministic profile. This module does not assert PM4Py numerical parity.
Search limits never become non-fitting traces or whole-population scores.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from fractions import Fraction
from heapq import heappop, heappush
from itertools import count
from math import sqrt
from typing import ClassVar, Literal

from pix.case_centric._input import as_case_traces
from pix.compute._common import _result
from pix.compute.conformance import _align, align_traces
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.compute.replay import _silent_closure, replay_traces
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import AlignmentSet, AlignmentSpec, TraceAlignment
from pix.contracts.models import Marking, PetriNet
from pix.contracts.replay import ReplaySet, ReplaySpec, TokenCounts
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog

CaseInput = CaseLog | ComputationResult[TraceSet]
Ratio = tuple[int, int]


def _ratio(value: Fraction | None) -> Ratio | None:
    return None if value is None else (value.numerator, value.denominator)


def _parents(source: ComputationResult) -> tuple[str, ...]:
    return (source.computation_id,) if source.computation_id is not None else ()


def _check(source: ComputationResult, net: PetriNet, request: object, operator: str):
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
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
        + (ComputeIssue("trace_result_unavailable", "Completed traces are required"),),
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class TokenFitnessSpec:
    replay: ReplaySpec = ReplaySpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.replay, ReplaySpec):
            raise TypeError("replay must be ReplaySpec")


@dataclass(frozen=True, slots=True)
class TokenFitnessRequest:
    model_digest: str
    parameters: TokenFitnessSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TraceTokenFitness:
    case_id: str
    status: Literal["computed", "undefined_denominator", "search_limit"]
    fitness_ratio: Ratio | None
    strictly_fitting: bool | None
    counts: TokenCounts
    log_deviation_count: int


@dataclass(frozen=True, slots=True)
class TokenFitness:
    model_digest: str
    traces: tuple[TraceTokenFitness, ...]
    requested_count: int
    completed_count: int
    defined_count: int
    limited_count: int
    completed_counts: TokenCounts
    completed_log_fitness_ratio: Ratio | None
    whole_log_fitness_ratio: Ratio | None
    mean_defined_trace_fitness_ratio: Ratio | None
    whole_mean_trace_fitness_ratio: Ratio | None
    completed_fitting_count: int
    whole_fitting_trace_ratio: Ratio | None
    replay_evidence: ReplaySet
    profile: str = "token_balance_initial_production_final_consumption"


def _token_score(tokens: TokenCounts) -> Fraction | None:
    if not tokens.consumed or not tokens.produced:
        return None
    return (
        Fraction(tokens.consumed - tokens.missing, tokens.consumed)
        + Fraction(tokens.produced - tokens.remaining, tokens.produced)
    ) / 2


def measure_token_fitness(
    log: CaseInput,
    net: PetriNet,
    spec: TokenFitnessSpec = TokenFitnessSpec(),
) -> ComputationResult[TokenFitness]:
    """Compute .5(1-m/c)+.5(1-r/p), retaining counts and replay evidence.

    Undefined token denominators remain None. Unknown labels are explicit log
    deviations and prohibit strict fitness, even when token-balance fitness is
    one. Completed totals exclude limited prefixes; whole scores require all
    requested cases. The average of cases is distinct from pooled token counts.
    """
    if not isinstance(spec, TokenFitnessSpec):
        raise TypeError("spec must be TokenFitnessSpec")
    source = as_case_traces(log)
    request = TokenFitnessRequest(model_digest(net), spec)
    operator = "pix.case_centric.token_fitness"
    invalid = _check(source, net, request, operator)
    if invalid is not None:
        return invalid
    replay = replay_traces(source, net, spec.replay)
    evidence = replay.value
    assert evidence is not None
    items = []
    scores = []
    for trace in evidence.traces:
        completed = trace.status == "completed"
        score = _token_score(trace.counts) if completed else None
        fitting = (
            (
                trace.counts.missing == trace.counts.remaining == 0
                and trace.log_deviation_count == 0
                and trace.final_reached
            )
            if completed
            else None
        )
        if score is not None:
            scores.append(score)
        items.append(
            TraceTokenFitness(
                trace.object_id,
                "search_limit"
                if not completed
                else "computed"
                if score is not None
                else "undefined_denominator",
                _ratio(score),
                fitting,
                trace.counts,
                trace.log_deviation_count,
            )
        )
    pooled = (
        _token_score(evidence.completed_counts) if evidence.completed_count else None
    )
    mean = sum(scores, Fraction()) / len(scores) if scores else None
    complete = not evidence.limited_count
    fitting_count = sum(item.strictly_fitting is True for item in items)
    value = TokenFitness(
        request.model_digest,
        tuple(items),
        evidence.trace_count,
        evidence.completed_count,
        len(scores),
        evidence.limited_count,
        evidence.completed_counts,
        _ratio(pooled),
        _ratio(pooled) if complete else None,
        _ratio(mean),
        _ratio(mean) if len(scores) == len(items) and items else None,
        fitting_count,
        (fitting_count, len(items)) if complete and items else None,
        evidence,
    )
    return _result(
        operator,
        None,
        request,
        replay.status,
        value,
        source.issues + replay.issues,
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class AlignmentFitnessSpec:
    alignment: AlignmentSpec = AlignmentSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.alignment, AlignmentSpec):
            raise TypeError("alignment must be AlignmentSpec")
        if (
            self.alignment.log_move_cost <= 0
            or self.alignment.model_move_cost <= 0
            or self.alignment.synchronous_move_cost
            or self.alignment.silent_move_cost
        ):
            raise ValueError(
                "fitness requires positive visible deviation costs and zero synchronous/silent costs"
            )


@dataclass(frozen=True, slots=True)
class AlignmentFitnessRequest:
    model_digest: str
    parameters: AlignmentFitnessSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TraceAlignmentFitness:
    case_id: str
    status: str
    alignment_cost: int | None
    best_worst_cost: int | None
    fitness_ratio: Ratio | None


@dataclass(frozen=True, slots=True)
class AlignmentFitness:
    model_digest: str
    traces: tuple[TraceAlignmentFitness, ...]
    model_completion_status: str
    shortest_model_completion_cost: int | None
    requested_count: int
    defined_count: int
    completed_cost_sum: int
    completed_best_worst_sum: int
    completed_log_fitness_ratio: Ratio | None
    whole_log_fitness_ratio: Ratio | None
    mean_defined_trace_fitness_ratio: Ratio | None
    whole_mean_trace_fitness_ratio: Ratio | None
    alignment_evidence: AlignmentSet
    model_completion_evidence: TraceAlignment
    profile: str = "one_minus_cost_over_log_deletion_plus_shortest_model_completion"


def measure_alignment_fitness(
    log: CaseInput,
    net: PetriNet,
    spec: AlignmentFitnessSpec = AlignmentFitnessSpec(),
) -> ComputationResult[AlignmentFitness]:
    """Normalize optimal costs by deleting the trace plus completing the model.

    This gives an upper-bound cost for every accepting alignment. An accepted
    empty trace with denominator zero scores one; an empty *population* has no
    score. An empty model language or bounded-out model completion has no best-
    worst normalizer. Case means and pooled denominator weights are both given.
    """
    if not isinstance(spec, AlignmentFitnessSpec):
        raise TypeError("spec must be AlignmentFitnessSpec")
    source = as_case_traces(log)
    request = AlignmentFitnessRequest(model_digest(net), spec)
    operator = "pix.case_centric.alignment_fitness"
    invalid = _check(source, net, request, operator)
    if invalid is not None:
        return invalid
    aligned = align_traces(source, net, spec.alignment)
    evidence = aligned.value
    assert evidence is not None and source.value is not None
    empty = ObjectTrace("__normalization_empty_trace__", source.value.object_type, ())
    baseline = _align(empty, net, spec.alignment)
    normalizer = baseline.cost if baseline.status == "optimal" else None
    items, scores = [], []
    total_cost = total_worst = 0
    for trace in evidence.alignments:
        worst = (
            len(trace.event_ids) * spec.alignment.log_move_cost + normalizer
            if normalizer is not None
            else None
        )
        score = None
        if trace.status == "optimal" and worst is not None:
            assert trace.cost is not None
            score = Fraction(worst - trace.cost, worst) if worst else Fraction(1)
            total_cost += trace.cost
            total_worst += worst
            scores.append(score)
        items.append(
            TraceAlignmentFitness(
                trace.object_id,
                trace.status if normalizer is not None else "model_" + baseline.status,
                trace.cost,
                worst,
                _ratio(score),
            )
        )
    pooled = (
        (
            Fraction(total_worst - total_cost, total_worst)
            if total_worst
            else Fraction(1)
        )
        if scores
        else None
    )
    mean = sum(scores, Fraction()) / len(scores) if scores else None
    complete = len(scores) == len(items)
    value = AlignmentFitness(
        request.model_digest,
        tuple(items),
        baseline.status,
        normalizer,
        len(items),
        len(scores),
        total_cost,
        total_worst,
        _ratio(pooled),
        _ratio(pooled) if complete else None,
        _ratio(mean),
        _ratio(mean) if complete else None,
        evidence,
        baseline,
    )
    issues = list(source.issues + aligned.issues)
    if normalizer is None:
        issues.append(
            ComputeIssue(
                "fitness_normalizer_unavailable",
                "No proven finite model-completion cost: " + baseline.status,
            )
        )
    status = (
        ComputeStatus.PARTIAL
        if baseline.status == "search_limit" or aligned.status is ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED
    )
    return _result(
        operator,
        None,
        request,
        status,
        value,
        tuple(issues),
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class ETPrecisionSpec:
    """Prefix extensions weigh nonempty prefixes; root weighs every case.

    token: deterministic shortest-silent replay without token repair.
    alignment: all stop markings minimizing the number of silent firings, with
    synchronous firings cost zero. Both take full silent closure for enabled
    visible label sets. Neither counts termination as an escaping edge.
    """

    method: Literal["token", "alignment"] = "alignment"
    max_states: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.method not in ("token", "alignment"):
            raise ValueError("method must be token or alignment")
        if type(self.max_states) is not int or self.max_states < 1:
            raise ValueError("max_states must be a positive integer")


@dataclass(frozen=True, slots=True)
class ETPrecisionRequest:
    model_digest: str
    parameters: ETPrecisionSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ETPrefixEvidence:
    prefix: tuple[str, ...]
    case_ids: tuple[str, ...]
    weight: int
    observed_labels: tuple[str, ...]
    status: Literal["computed", "unfit", "search_limit"]
    stop_markings: tuple[tuple[tuple[str, int], ...], ...] | None
    minimum_silent_firings: int | None
    enabled_labels: tuple[str, ...] | None
    escaping_labels: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class ETPrecision:
    model_digest: str
    method: str
    prefixes: tuple[ETPrefixEvidence, ...]
    requested_case_count: int
    computed_prefix_count: int
    unfit_prefix_count: int
    limited_prefix_count: int
    computed_weight: int
    unfit_weight: int
    limited_weight: int
    weighted_enabled: int
    weighted_escaping: int
    computed_prefix_ratio: Ratio | None
    whole_population_ratio: Ratio | None
    profile: str = (
        "visible_label_escaping_edges_root_all_cases_nonempty_extension_occurrences"
    )


def _aligned_prefix(net: PetriNet, prefix: tuple[str, ...], cap: int):
    """Dijkstra in prefix-position × marking, collecting ALL optimal goals."""
    serial = count()
    initial = (0, net.initial_marking)
    queue = [(0, next(serial), initial)]
    best = {initial: 0}
    settled = set()
    optimum = None
    stops = set()
    labels = {t.id: t.activity for t in net.transitions}
    while queue:
        cost, _, state = heappop(queue)
        if state in settled or cost != best[state]:
            continue
        if optimum is not None and cost > optimum:
            break
        if len(settled) >= cap:
            return None, None, "search_limit"
        settled.add(state)
        position, marking = state
        if position == len(prefix):
            optimum = cost
            stops.add(marking)
            continue
        for transition in enabled_transitions(net, marking):
            label = labels[transition]
            if label is not None and label != prefix[position]:
                continue
            following = (
                position + int(label is not None),
                fire(net, marking, transition),
            )
            candidate = cost + int(label is None)
            if following not in best or candidate < best[following]:
                best[following] = candidate
                heappush(queue, (candidate, next(serial), following))
    return stops, optimum, "computed" if stops else "unfit"


def _token_prefix(net: PetriNet, prefix: tuple[str, ...], cap: int):
    marking = net.initial_marking
    silent_count = 0
    for activity in prefix:
        closure = _silent_closure(net, marking, cap, activity)
        if closure.limited:
            return None, None, "search_limit"
        if closure.choice is None:
            return set(), None, "unfit"
        before, path, transition = closure.choice
        assert transition is not None
        silent_count += len(path)
        marking = fire(net, before, transition)
    return {marking}, silent_count, "computed"


def _enabled_labels(net: PetriNet, stops: set[Marking], cap: int):
    seen = set(stops)
    if len(seen) > cap:
        return None
    queue = deque(sorted(stops, key=lambda marking: marking.tokens))
    labels = {t.id: t.activity for t in net.transitions}
    visible = set()
    while queue:
        marking = queue.popleft()
        for transition in enabled_transitions(net, marking):
            if labels[transition] is not None:
                visible.add(labels[transition])
            else:
                after = fire(net, marking, transition)
                if after not in seen:
                    if len(seen) >= cap:
                        return None
                    seen.add(after)
                    queue.append(after)
    return tuple(sorted(visible))


def measure_et_precision(
    log: CaseInput,
    net: PetriNet,
    spec: ETPrecisionSpec = ETPrecisionSpec(),
) -> ComputationResult[ETPrecision]:
    """Compute occurrence-weighted escaping edges with a named replay policy.

    Unfit prefixes are reported separately, never silently treated as complete
    coverage. A zero denominator remains undefined (PM4Py defaults it to one).
    Align-ET needs no claimed soundness; dead-end enabled labels still count.
    """
    if not isinstance(spec, ETPrecisionSpec):
        raise TypeError("spec must be ETPrecisionSpec")
    source = as_case_traces(log)
    request = ETPrecisionRequest(model_digest(net), spec)
    operator = "pix.case_centric.et_precision"
    invalid = _check(source, net, request, operator)
    if invalid is not None:
        return invalid
    assert source.value is not None
    visits: dict[tuple[str, ...], list[str]] = {(): []}
    observed: dict[tuple[str, ...], set[str]] = {(): set()}
    for trace in source.value.traces:
        sequence = tuple(event.activity for event in trace.events)
        visits[()].append(trace.object_id)
        if sequence:
            observed[()].add(sequence[0])
        for position in range(1, len(sequence)):
            prefix = sequence[:position]
            visits.setdefault(prefix, []).append(trace.object_id)
            observed.setdefault(prefix, set()).add(sequence[position])
    if not source.value.traces:
        visits.clear()
    prefixes = []
    issues = list(source.issues)
    for prefix in sorted(visits, key=lambda item: (len(item), item)):
        solver = _token_prefix if spec.method == "token" else _aligned_prefix
        stops, cost, status = solver(net, prefix, spec.max_states)
        labels = (
            _enabled_labels(net, stops, spec.max_states)
            if status == "computed"
            else None
        )
        if status == "computed" and labels is None:
            status = "search_limit"
        if status != "computed":
            issues.append(
                ComputeIssue(
                    "et_precision_" + status,
                    "Prefix excluded from the computed-prefix denominator",
                    ("prefix",) + prefix,
                )
            )
        prefixes.append(
            ETPrefixEvidence(
                prefix,
                tuple(visits[prefix]),
                len(visits[prefix]),
                tuple(sorted(observed[prefix])),
                status,
                tuple(sorted(marking.tokens for marking in stops))
                if stops is not None
                else None,
                cost,
                labels,
                tuple(sorted(set(labels) - observed[prefix]))
                if labels is not None
                else None,
            )
        )
    computed = [item for item in prefixes if item.status == "computed"]
    unfit = [item for item in prefixes if item.status == "unfit"]
    limited = [item for item in prefixes if item.status == "search_limit"]
    denominator = sum(item.weight * len(item.enabled_labels) for item in computed)
    escaping = sum(item.weight * len(item.escaping_labels) for item in computed)
    ratio = (denominator - escaping, denominator) if denominator else None
    value = ETPrecision(
        request.model_digest,
        spec.method,
        tuple(prefixes),
        len(source.value.traces),
        len(computed),
        len(unfit),
        len(limited),
        sum(x.weight for x in computed),
        sum(x.weight for x in unfit),
        sum(x.weight for x in limited),
        denominator,
        escaping,
        ratio,
        ratio if not unfit and not limited else None,
    )
    return _result(
        operator,
        None,
        request,
        ComputeStatus.PARTIAL if unfit or limited else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


@dataclass(frozen=True, slots=True)
class GeneralizationSpec:
    replay: ReplaySpec = ReplaySpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.replay, ReplaySpec):
            raise TypeError("replay must be ReplaySpec")


@dataclass(frozen=True, slots=True)
class GeneralizationRequest:
    model_digest: str
    parameters: GeneralizationSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TransitionFrequency:
    transition_id: str
    activity: str | None
    firing_count: int
    inverse_sqrt_penalty: float


@dataclass(frozen=True, slots=True)
class TokenGeneralization:
    model_digest: str
    requested_case_count: int
    completed_case_count: int
    limited_case_count: int
    transitions: tuple[TransitionFrequency, ...]
    completed_score: float | None
    whole_population_score: float | None
    replay_evidence: ReplaySet
    profile: str = (
        "all_transition_ids_including_silent_completed_replays_including_repairs"
    )


def measure_token_generalization(
    log: CaseInput,
    net: PetriNet,
    spec: GeneralizationSpec = GeneralizationSpec(),
) -> ComputationResult[TokenGeneralization]:
    """1 - mean(1/sqrt(firings)); an unseen transition contributes penalty 1.

    Frequencies distinguish transition IDs, including duplicate visible labels
    and silent transitions. Repaired completed replays participate explicitly.
    Empty completed case/transition populations have no score.
    """
    if not isinstance(spec, GeneralizationSpec):
        raise TypeError("spec must be GeneralizationSpec")
    source = as_case_traces(log)
    request = GeneralizationRequest(model_digest(net), spec)
    operator = "pix.case_centric.token_generalization"
    invalid = _check(source, net, request, operator)
    if invalid is not None:
        return invalid
    replay = replay_traces(source, net, spec.replay)
    evidence = replay.value
    assert evidence is not None
    frequencies = Counter(
        step.transition_id
        for trace in evidence.traces
        if trace.status == "completed"
        for step in trace.steps
        if step.transition_id is not None
    )
    transitions = tuple(
        TransitionFrequency(
            t.id,
            t.activity,
            frequencies[t.id],
            1 / sqrt(frequencies[t.id]) if frequencies[t.id] else 1.0,
        )
        for t in net.transitions
    )
    score = (
        (1 - sum(item.inverse_sqrt_penalty for item in transitions) / len(transitions))
        if transitions and evidence.completed_count
        else None
    )
    value = TokenGeneralization(
        request.model_digest,
        evidence.trace_count,
        evidence.completed_count,
        evidence.limited_count,
        transitions,
        score,
        score if not evidence.limited_count else None,
        evidence,
    )
    return _result(
        operator,
        None,
        request,
        replay.status,
        value,
        source.issues + replay.issues,
        source_digest=source.source_digest,
        parent_computation_ids=_parents(source),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.token_fitness": (
        "case-token-fitness",
        TokenFitnessRequest,
        TokenFitness,
    ),
    "pix.case_centric.alignment_fitness": (
        "case-alignment-fitness",
        AlignmentFitnessRequest,
        AlignmentFitness,
    ),
    "pix.case_centric.et_precision": (
        "case-et-precision",
        ETPrecisionRequest,
        ETPrecision,
    ),
    "pix.case_centric.token_generalization": (
        "case-token-generalization",
        GeneralizationRequest,
        TokenGeneralization,
    ),
}

__all__ = (
    "TokenFitnessSpec",
    "TokenFitnessRequest",
    "TraceTokenFitness",
    "TokenFitness",
    "measure_token_fitness",
    "AlignmentFitnessSpec",
    "AlignmentFitnessRequest",
    "TraceAlignmentFitness",
    "AlignmentFitness",
    "measure_alignment_fitness",
    "ETPrecisionSpec",
    "ETPrecisionRequest",
    "ETPrefixEvidence",
    "ETPrecision",
    "measure_et_precision",
    "GeneralizationSpec",
    "GeneralizationRequest",
    "TransitionFrequency",
    "TokenGeneralization",
    "measure_token_generalization",
)
