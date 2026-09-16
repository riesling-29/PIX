"""Native sequence and DFG conformance with explicit finite search contracts.

Log-to-log alignment minimizes weighted edit distance, retaining every nearest
reference case and one deterministic edit witness per reference. DFG alignment
minimizes log/model move cost over the full DFG language by graph-product
Dijkstra, including cycles. A DFG is an accepting activity graph, not a Petri
net: concurrency and token semantics are not inferred from its edges.

The two bounded-language operators optimize *only* accepted DFG sequences up to
the supplied length. They do not assert an unbounded Petri-net anti/multi-
alignment guarantee, normalized distance, or equivalence to another library.
"""

from __future__ import annotations

from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count
from typing import ClassVar, Literal

from pix.case_centric._input import as_case_traces as _traces
from pix.compute._common import _result
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _labels(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not all(
        isinstance(label, str) and label.strip() for label in value
    ):
        raise TypeError(f"{name} must be a tuple of nonblank strings")
    return tuple(sorted(set(value)))


@dataclass(frozen=True, slots=True)
class SequenceAlignmentSpec:
    """Edit costs; None forbids substitution; max_cells bounds each pair.

    A substitution consumes both unlike activities in one move. A match costs
    zero. An insertion is a model move; a deletion is a log move. No averaging
    or normalization is implicit. max_cells includes the DP boundary row/column.
    """

    log_move_cost: int = 1
    model_move_cost: int = 1
    substitution_cost: int | None = 1
    max_cells: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.log_move_cost, "log_move_cost")
        _integer(self.model_move_cost, "model_move_cost")
        if self.substitution_cost is not None:
            _integer(self.substitution_cost, "substitution_cost")
        _integer(self.max_cells, "max_cells", 1)


@dataclass(frozen=True, slots=True)
class SequenceAlignmentRequest:
    reference_computation_id: str | None
    parameters: SequenceAlignmentSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class EditMove:
    kind: Literal["synchronous", "log", "model", "substitution"]
    log_event_id: str | None
    log_activity: str | None
    model_activity: str | None
    reference_event_id: str | None
    cost: int


@dataclass(frozen=True, slots=True)
class ReferenceAlignment:
    reference_case_id: str
    cost: int
    moves: tuple[EditMove, ...]


@dataclass(frozen=True, slots=True)
class SequenceTraceAlignment:
    case_id: str
    status: Literal["optimal", "search_limit", "empty_reference"]
    best_known_cost: int | None
    nearest_references: tuple[ReferenceAlignment, ...]
    evaluated_references: int
    limited_references: int


@dataclass(frozen=True, slots=True)
class SequenceAlignmentSet:
    traces: tuple[SequenceTraceAlignment, ...]
    reference_case_count: int
    optimal_count: int
    limited_count: int


@dataclass(frozen=True, slots=True)
class DFGAlignmentModel:
    """Accepted words start in starts, follow edges and end in ends.

    A one-activity word is accepted when that activity belongs to both starts
    and ends. Empty-word acceptance is controlled solely by accepts_empty, not
    inferred from missing edges, empty logs or missing boundary annotations.
    """

    activities: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    starts: tuple[str, ...]
    ends: tuple[str, ...]
    accepts_empty: bool = False

    def __post_init__(self) -> None:
        for name in ("activities", "starts", "ends"):
            object.__setattr__(self, name, _labels(getattr(self, name), name))
        labels = set(self.activities)
        if not set(self.starts + self.ends).issubset(labels):
            raise ValueError("starts and ends must be declared activities")
        if not isinstance(self.edges, tuple) or not all(
            isinstance(edge, tuple)
            and len(edge) == 2
            and all(isinstance(label, str) for label in edge)
            for edge in self.edges
        ):
            raise TypeError("edges must be a tuple of string pairs")
        if any(left not in labels or right not in labels for left, right in self.edges):
            raise ValueError("edge endpoints must be declared activities")
        object.__setattr__(self, "edges", tuple(sorted(set(self.edges))))
        if type(self.accepts_empty) is not bool:
            raise TypeError("accepts_empty must be bool")


@dataclass(frozen=True, slots=True)
class DFGAlignmentSpec:
    log_move_cost: int = 1
    model_move_cost: int = 1
    max_states: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.log_move_cost, "log_move_cost")
        _integer(self.model_move_cost, "model_move_cost")
        _integer(self.max_states, "max_states", 1)


@dataclass(frozen=True, slots=True)
class DFGAlignmentRequest:
    model: DFGAlignmentModel
    parameters: DFGAlignmentSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DFGTraceAlignment:
    case_id: str
    status: Literal["optimal", "unreachable", "search_limit"]
    cost: int | None
    moves: tuple[EditMove, ...]
    settled_states: int
    discovered_states: int
    lower_bound_cost: int | None


@dataclass(frozen=True, slots=True)
class DFGAlignmentSet:
    traces: tuple[DFGTraceAlignment, ...]
    optimal_count: int
    unreachable_count: int
    limited_count: int


@dataclass(frozen=True, slots=True)
class BoundedDFGLanguageSpec:
    """Visible-word horizon and resource limits, not a bound on optimal cost.

    Anti objective: maximize minimum weighted edit distance to an observed case.
    Multi objective: minimize sum of weighted edit distances to *all* cases;
    duplicate cases keep their multiplicity. Costs are directed observed ->
    candidate word. Every tied optimal word is retained when enumeration ends.
    max_prefixes limits visited prefixes (including the empty prefix), while
    max_total_cells limits total DP cells across all candidate/case pairs.
    """

    max_length: int
    log_move_cost: int = 1
    model_move_cost: int = 1
    substitution_cost: int | None = 1
    max_prefixes: int = 100_000
    max_total_cells: int = 10_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.max_length, "max_length")
        _integer(self.log_move_cost, "log_move_cost")
        _integer(self.model_move_cost, "model_move_cost")
        if self.substitution_cost is not None:
            _integer(self.substitution_cost, "substitution_cost")
        _integer(self.max_prefixes, "max_prefixes", 1)
        _integer(self.max_total_cells, "max_total_cells", 1)


@dataclass(frozen=True, slots=True)
class BoundedDFGLanguageRequest:
    model: DFGAlignmentModel
    objective: Literal["anti_max_min", "multi_min_sum"]
    parameters: BoundedDFGLanguageSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class BoundedLanguageCandidate:
    activities: tuple[str, ...]
    objective_value: int
    case_distances: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class BoundedDFGLanguageAlignment:
    status: Literal["optimal_within_horizon", "empty_bounded_language", "search_limit"]
    candidates: tuple[BoundedLanguageCandidate, ...]
    evaluated_words: int
    visited_prefixes: int
    evaluated_cells: int
    observed_cases: int


def _complete(traces: ComputationResult[TraceSet]) -> bool:
    return traces.status is ComputeStatus.COMPUTED and isinstance(
        traces.value, TraceSet
    )


def _envelope(
    operator: str,
    traces: tuple[ComputationResult[TraceSet], ...],
    request: object,
    value: object,
    issues: tuple[ComputeIssue, ...] = (),
):
    failed = any(not _complete(item) for item in traces)
    if failed:
        status = (
            ComputeStatus.INVALID_INPUT
            if any(item.status is ComputeStatus.INVALID_INPUT for item in traces)
            else ComputeStatus.UNAVAILABLE
        )
        value = None
        issues = (
            ComputeIssue(
                "trace_result_unavailable", "Completed TraceSets are required"
            ),
        ) + tuple(issue for item in traces for issue in item.issues)
    else:
        status = ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED
        issues = tuple(issue for item in traces for issue in item.issues) + issues
    return _result(
        operator,
        None,
        request,
        status,
        value,
        issues,
        source_digest=traces[0].source_digest,
        parent_computation_ids=tuple(
            item.computation_id for item in traces if item.computation_id
        ),
    )


def _edit(
    left: tuple[str, ...],
    right: tuple[str, ...],
    spec: SequenceAlignmentSpec,
    left_ids: tuple[str, ...] = (),
    right_ids: tuple[str, ...] = (),
):
    """Weighted DP; callers enforce the cell budget before allocating."""
    n, m = len(left), len(right)
    costs = [[0] * (m + 1) for _ in range(n + 1)]
    moves = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        costs[i][0], moves[i][0] = i * spec.log_move_cost, "log"
    for j in range(1, m + 1):
        costs[0][j], moves[0][j] = j * spec.model_move_cost, "model"
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            options = []
            if left[i - 1] == right[j - 1]:
                options.append((costs[i - 1][j - 1], 0, "synchronous"))
            elif spec.substitution_cost is not None:
                options.append(
                    (costs[i - 1][j - 1] + spec.substitution_cost, 1, "substitution")
                )
            options.extend(
                (
                    (costs[i - 1][j] + spec.log_move_cost, 2, "log"),
                    (costs[i][j - 1] + spec.model_move_cost, 3, "model"),
                )
            )
            costs[i][j], _, moves[i][j] = min(options)
    witness = []
    i, j = n, m
    while i or j:
        kind = moves[i][j]
        consume_left, consume_right = kind != "model", kind != "log"
        event_id = left_ids[i - 1] if consume_left and left_ids else None
        reference_id = right_ids[j - 1] if consume_right and right_ids else None
        activity = left[i - 1] if consume_left else None
        reference = right[j - 1] if consume_right else None
        ni, nj = i - int(consume_left), j - int(consume_right)
        witness.append(
            EditMove(
                kind,
                event_id,
                activity,
                reference,
                reference_id,
                costs[i][j] - costs[ni][nj],
            )
        )
        i, j = ni, nj
    return costs[n][m], tuple(reversed(witness))


def align_log_to_log(
    log: CaseLog | ComputationResult[TraceSet],
    reference: CaseLog | ComputationResult[TraceSet],
    spec: SequenceAlignmentSpec = SequenceAlignmentSpec(),
) -> ComputationResult[SequenceAlignmentSet]:
    """Align each case to all closest reference cases; no case is dropped.

    An empty reference population yields explicit empty_reference outcomes.
    Limited comparisons retain evaluated incumbents without claiming that the
    nearest-reference ties or global optimum have been established.
    """
    if not isinstance(spec, SequenceAlignmentSpec):
        raise TypeError("spec must be SequenceAlignmentSpec")
    traces, refs = _traces(log), _traces(reference)
    request = SequenceAlignmentRequest(refs.computation_id, spec)
    operator = "pix.case_centric.align_log_to_log"
    if not _complete(traces) or not _complete(refs):
        return _envelope(operator, (traces, refs), request, None)
    results = []
    for trace in traces.value.traces:
        left = tuple(event.activity for event in trace.events)
        left_ids = tuple(event.event_id for event in trace.events)
        best, nearest, limited, evaluated = None, [], 0, 0
        for ref in refs.value.traces:
            right = tuple(event.activity for event in ref.events)
            if (len(left) + 1) * (len(right) + 1) > spec.max_cells:
                limited += 1
                continue
            cost, witness = _edit(
                left,
                right,
                spec,
                left_ids,
                tuple(event.event_id for event in ref.events),
            )
            evaluated += 1
            candidate = ReferenceAlignment(ref.object_id, cost, witness)
            if best is None or cost < best:
                best, nearest = cost, [candidate]
            elif cost == best:
                nearest.append(candidate)
        status = (
            "search_limit"
            if limited
            else ("optimal" if evaluated else "empty_reference")
        )
        results.append(
            SequenceTraceAlignment(
                trace.object_id, status, best, tuple(nearest), evaluated, limited
            )
        )
    issues = tuple(
        ComputeIssue(
            "sequence_alignment_cell_limit",
            "Nearest-reference optimality is unknown",
            ("case", item.case_id),
        )
        for item in results
        if item.status == "search_limit"
    )
    value = SequenceAlignmentSet(
        tuple(results),
        len(refs.value.traces),
        sum(item.status == "optimal" for item in results),
        sum(item.status == "search_limit" for item in results),
    )
    return _envelope(operator, (traces, refs), request, value, issues)


def _dfg_trace(
    trace: ObjectTrace, model: DFGAlignmentModel, spec: DFGAlignmentSpec
) -> DFGTraceAlignment:
    successors = {
        label: tuple(right for left, right in model.edges if left == label)
        for label in model.activities
    }
    initial = (0, None)
    distance, parents, settled = {initial: 0}, {}, set()
    serial, heap = count(), [(0, 0, initial)]
    next(serial)

    def finish(status, state=None, cost=None, lower=None):
        witness = []
        while state is not None and state != initial:
            state, move = parents[state]
            witness.append(move)
        return DFGTraceAlignment(
            trace.object_id,
            status,
            cost,
            tuple(reversed(witness)),
            len(settled),
            len(distance),
            lower,
        )

    while heap:
        cost, _, state = heappop(heap)
        if state in settled or distance[state] != cost:
            continue
        if len(settled) >= spec.max_states:
            return finish("search_limit", lower=cost)
        settled.add(state)
        position, last = state
        if position == len(trace.events) and (
            last in model.ends or (last is None and model.accepts_empty)
        ):
            return finish("optimal", state, cost, cost)
        choices = []
        event = trace.events[position] if position < len(trace.events) else None
        for activity in model.starts if last is None else successors[last]:
            if event is not None and activity == event.activity:
                choices.append(
                    (
                        (position + 1, activity),
                        EditMove(
                            "synchronous", event.event_id, activity, activity, None, 0
                        ),
                    )
                )
            choices.append(
                (
                    (position, activity),
                    EditMove("model", None, None, activity, None, spec.model_move_cost),
                )
            )
        if event is not None:
            choices.append(
                (
                    (position + 1, last),
                    EditMove(
                        "log",
                        event.event_id,
                        event.activity,
                        None,
                        None,
                        spec.log_move_cost,
                    ),
                )
            )
        for following, move in choices:
            candidate = cost + move.cost
            if following not in distance or candidate < distance[following]:
                distance[following], parents[following] = candidate, (state, move)
                heappush(heap, (candidate, next(serial), following))
    return finish("unreachable")


def align_dfg(
    log: CaseLog | ComputationResult[TraceSet],
    model: DFGAlignmentModel,
    spec: DFGAlignmentSpec = DFGAlignmentSpec(),
) -> ComputationResult[DFGAlignmentSet]:
    """Exact graph-product Dijkstra; finite-frontier exhaustion proves absence.

    A search limit proves neither unreachability nor optimality. Matches cost
    zero; mismatches require a log and a model move, never a hidden substitution.
    """
    if not isinstance(model, DFGAlignmentModel):
        raise TypeError("model must be DFGAlignmentModel")
    if not isinstance(spec, DFGAlignmentSpec):
        raise TypeError("spec must be DFGAlignmentSpec")
    traces, request = _traces(log), DFGAlignmentRequest(model, spec)
    operator = "pix.case_centric.align_dfg"
    if not _complete(traces):
        return _envelope(operator, (traces,), request, None)
    results = tuple(_dfg_trace(trace, model, spec) for trace in traces.value.traces)
    issues = tuple(
        ComputeIssue(
            "dfg_alignment_search_limit",
            "Optimality is unknown",
            ("case", item.case_id),
        )
        for item in results
        if item.status == "search_limit"
    )
    value = DFGAlignmentSet(
        results,
        sum(item.status == "optimal" for item in results),
        sum(item.status == "unreachable" for item in results),
        sum(item.status == "search_limit" for item in results),
    )
    return _envelope(operator, (traces,), request, value, issues)


def _bounded_language(log, model, spec, objective):
    if not isinstance(model, DFGAlignmentModel):
        raise TypeError("model must be DFGAlignmentModel")
    if not isinstance(spec, BoundedDFGLanguageSpec):
        raise TypeError("spec must be BoundedDFGLanguageSpec")
    traces = _traces(log)
    operator = "pix.case_centric.bounded_dfg_" + (
        "anti_alignment" if objective == "anti_max_min" else "multi_alignment"
    )
    request = BoundedDFGLanguageRequest(model, objective, spec)
    if not _complete(traces):
        return _envelope(operator, (traces,), request, None)
    if not traces.value.traces:
        return _result(
            operator,
            None,
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "empty_observed_population",
                    "The objective requires at least one observed case",
                ),
            ),
            source_digest=traces.source_digest,
            parent_computation_ids=(traces.computation_id,),
        )
    observed = tuple(
        (trace.object_id, tuple(event.activity for event in trace.events))
        for trace in traces.value.traces
    )
    successors = {
        label: tuple(right for left, right in model.edges if left == label)
        for label in model.activities
    }
    edit_spec = SequenceAlignmentSpec(
        spec.log_move_cost,
        spec.model_move_cost,
        spec.substitution_cost,
        spec.max_total_cells,
    )
    stack, best, candidates = [()], None, []
    visited, evaluated, cells, limited = 0, 0, 0, False
    while stack:
        if visited >= spec.max_prefixes:
            limited = True
            break
        word = stack.pop()
        visited += 1
        accepted = (not word and model.accepts_empty) or (
            bool(word) and word[-1] in model.ends
        )
        if accepted:
            required = sum(
                (len(values) + 1) * (len(word) + 1) for _, values in observed
            )
            if cells + required > spec.max_total_cells:
                limited = True
                break
            distances = tuple(
                (case_id, _edit(values, word, edit_spec)[0])
                for case_id, values in observed
            )
            cells += required
            evaluated += 1
            score = (
                min(value for _, value in distances)
                if objective == "anti_max_min"
                else sum(value for _, value in distances)
            )
            candidate = BoundedLanguageCandidate(word, score, distances)
            better = best is None or (
                score > best if objective == "anti_max_min" else score < best
            )
            if better:
                best, candidates = score, [candidate]
            elif score == best:
                candidates.append(candidate)
        if len(word) < spec.max_length:
            following = model.starts if not word else successors[word[-1]]
            stack.extend(word + (label,) for label in reversed(following))
    status = (
        "search_limit"
        if limited
        else ("optimal_within_horizon" if evaluated else "empty_bounded_language")
    )
    value = BoundedDFGLanguageAlignment(
        status,
        tuple(sorted(candidates, key=lambda item: item.activities)),
        evaluated,
        visited,
        cells,
        len(observed),
    )
    issues = (
        (
            ComputeIssue(
                "bounded_language_search_limit",
                "Only incumbent candidates are known; bounded optimality and complete ties are unknown",
            ),
        )
        if limited
        else ()
    )
    return _envelope(operator, (traces,), request, value, issues)


def bounded_dfg_anti_alignment(
    log: CaseLog | ComputationResult[TraceSet],
    model: DFGAlignmentModel,
    spec: BoundedDFGLanguageSpec,
) -> ComputationResult[BoundedDFGLanguageAlignment]:
    """Maximize minimum directed edit distance, only within the DFG horizon."""
    return _bounded_language(log, model, spec, "anti_max_min")


def bounded_dfg_multi_alignment(
    log: CaseLog | ComputationResult[TraceSet],
    model: DFGAlignmentModel,
    spec: BoundedDFGLanguageSpec,
) -> ComputationResult[BoundedDFGLanguageAlignment]:
    """Minimize sum of directed edit distances, only within the DFG horizon."""
    return _bounded_language(log, model, spec, "multi_min_sum")


RESULT_SCHEMAS = {
    "pix.case_centric.align_log_to_log": (
        "case_sequence_alignment_set",
        SequenceAlignmentRequest,
        SequenceAlignmentSet,
    ),
    "pix.case_centric.align_dfg": (
        "case_dfg_alignment_set",
        DFGAlignmentRequest,
        DFGAlignmentSet,
    ),
    "pix.case_centric.bounded_dfg_anti_alignment": (
        "case_bounded_dfg_language_alignment",
        BoundedDFGLanguageRequest,
        BoundedDFGLanguageAlignment,
    ),
    "pix.case_centric.bounded_dfg_multi_alignment": (
        "case_bounded_dfg_language_alignment",
        BoundedDFGLanguageRequest,
        BoundedDFGLanguageAlignment,
    ),
}

__all__ = (
    "SequenceAlignmentSpec",
    "SequenceAlignmentRequest",
    "EditMove",
    "ReferenceAlignment",
    "SequenceTraceAlignment",
    "SequenceAlignmentSet",
    "DFGAlignmentModel",
    "DFGAlignmentSpec",
    "DFGAlignmentRequest",
    "DFGTraceAlignment",
    "DFGAlignmentSet",
    "BoundedDFGLanguageSpec",
    "BoundedDFGLanguageRequest",
    "BoundedLanguageCandidate",
    "BoundedDFGLanguageAlignment",
    "align_log_to_log",
    "align_dfg",
    "bounded_dfg_anti_alignment",
    "bounded_dfg_multi_alignment",
)
