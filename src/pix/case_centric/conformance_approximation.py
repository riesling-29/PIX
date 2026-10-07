"""Subset-selection conformance approximation with executable witnesses.

Selected observed variants are aligned exactly; their accepting model runs are
reused for other cases through insertion/deletion edit alignment. Simulation
can supply accepting runs instead. This is an actual representative-subset
algorithm, not exact alignment of every case under an approximation label.

The certified PIX cost profile is log=model=1, synchronous=silent=0. Cost
intervals follow language-distance bounds and replayed accepting witnesses.
Fitness intervals require the exact shortest accepted visible-word length.
PM4Py's positive silent tie-breaking cost and point estimates are not implied.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from random import Random
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.sequence_alignment import SequenceAlignmentSpec, _edit
from pix.compute._common import _result
from pix.compute.conformance import _align
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.analysis import ObjectTrace, TraceSet
from pix.contracts.conformance import AlignmentMove, AlignmentSpec, TraceAlignment
from pix.contracts.models import PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

Word = tuple[str, ...]
Ratio = tuple[int, int]


def _integer(value, name, minimum=1):
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")


def _ratio(value: Fraction) -> Ratio:
    return value.numerator, value.denominator


@dataclass(frozen=True, slots=True)
class SubsetConformanceSpec:
    """Deterministic variant selection and explicit work limits.

    subset_size is capped by distinct observed variants, including simulation.
    Frequency and k-medoids objectives retain original case multiplicities.
    max_distance_cells caps one DP table; max_total_distance_cells caps all
    newly computed tables, including selection and bound calculations. Reused
    distances and equal-word comparisons require no additional DP cells.
    """

    selection_method: Literal["frequency", "random", "k_medoids", "simulation"] = (
        "frequency"
    )
    subset_size: int = 1
    random_seed: int = 0
    k_medoids_max_iterations: int = 10
    max_alignment_states: int = 10_000
    max_distance_cells: int = 1_000_000
    max_total_distance_cells: int = 10_000_000
    simulation_max_steps: int = 100
    simulation_max_attempts: int = 100
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.selection_method not in (
            "frequency",
            "random",
            "k_medoids",
            "simulation",
        ):
            raise ValueError("unknown selection_method")
        for name in (
            "subset_size",
            "k_medoids_max_iterations",
            "max_alignment_states",
            "max_distance_cells",
            "max_total_distance_cells",
            "simulation_max_steps",
            "simulation_max_attempts",
        ):
            _integer(getattr(self, name), name)
        _integer(self.random_seed, "random_seed", minimum=0)


@dataclass(frozen=True, slots=True)
class SubsetConformanceRequest:
    model_digest: str
    parameters: SubsetConformanceSpec
    profile: str = "subset_edit_distance_unit_visible_zero_silent"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ConformanceRepresentative:
    index: int
    source_variant: Word | None
    source_case_ids: tuple[str, ...]
    frequency: int
    status: Literal["optimal", "search_limit", "unreachable", "simulated"]
    visible_word: Word | None
    transition_ids: tuple[str, ...] | None
    exact_cost: int | None
    alignment_evidence: TraceAlignment | None


@dataclass(frozen=True, slots=True)
class ApproximationSelection:
    method: str
    requested_size: int
    effective_size: int
    selected_variants: tuple[Word, ...]
    status: Literal[
        "completed",
        "iteration_limit",
        "distance_limit",
        "simulation_limit",
        "not_required",
    ]
    iterations: int
    simulation_attempts: int


@dataclass(frozen=True, slots=True)
class ApproximationBoundEvidence:
    kind: Literal[
        "unknown_activities",
        "shortest_word_length",
        "representative_lipschitz",
        "selected_exact",
    ]
    lower_bound_cost: int
    representative_index: int | None = None
    edit_distance: int | None = None


@dataclass(frozen=True, slots=True)
class ApproximationDeviations:
    insertions: tuple[tuple[str, int], ...]
    deletions: tuple[tuple[str, int], ...]
    synchronous: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class ApproximateTraceAlignment:
    case_id: str
    activities: Word
    status: Literal[
        "exact", "bounded", "search_limit", "unreachable", "invalid_witness"
    ]
    lower_bound_cost: int | None
    upper_bound_cost: int | None
    exact_cost: int | None
    fitness_lower_ratio: Ratio | None
    fitness_upper_ratio: Ratio | None
    normalization_denominator: int | None
    moves: tuple[AlignmentMove, ...]
    representative_index: int | None
    witness_validated: bool
    lower_bound_evidence: tuple[ApproximationBoundEvidence, ...]
    deviations: ApproximationDeviations


@dataclass(frozen=True, slots=True)
class SubsetConformanceApproximation:
    model_digest: str
    selection: ApproximationSelection
    representatives: tuple[ConformanceRepresentative, ...]
    shortest_model_alignment: TraceAlignment | None
    shortest_visible_length: int | None
    traces: tuple[ApproximateTraceAlignment, ...]
    unique_variant_count: int
    exact_case_count: int
    bounded_case_count: int
    unresolved_case_count: int
    unreachable_case_count: int
    lower_cost_sum: int | None
    upper_cost_sum: int | None
    mean_fitness_lower_ratio: Ratio | None
    mean_fitness_upper_ratio: Ratio | None
    pooled_fitness_lower_ratio: Ratio | None
    pooled_fitness_upper_ratio: Ratio | None
    distance_cells: int
    limited_distance_pairs: int
    model_search_count: int
    profile: str = "subset_edit_distance_unit_visible_zero_silent"


class _Distances:
    def __init__(self, spec):
        self.spec = spec
        self.cells = 0
        self.cache = {}
        self.limited = set()

    def compare(self, left, right):
        key = left, right
        if key in self.cache:
            return self.cache[key]
        if left == right:
            result = 0, ("synchronous",) * len(left)
        else:
            cells = (len(left) + 1) * (len(right) + 1)
            if (
                cells > self.spec.max_distance_cells
                or self.cells + cells > self.spec.max_total_distance_cells
            ):
                self.limited.add(key)
                return None
            cost, moves = _edit(
                left, right, SequenceAlignmentSpec(substitution_cost=None)
            )
            self.cells += cells
            result = cost, tuple(move.kind for move in moves)
        self.cache[key] = result
        return result

    def distance(self, left, right):
        if (right, left) in self.cache:
            return self.cache[right, left][0]
        result = self.compare(left, right)
        return None if result is None else result[0]


def _select(frequencies, size, spec, distances):
    ranked = sorted(frequencies, key=lambda word: (-frequencies[word], word))
    if spec.selection_method == "random":
        return (
            tuple(Random(spec.random_seed).sample(sorted(frequencies), size)),
            "completed",
            0,
        )
    medoids = tuple(ranked[:size])
    if spec.selection_method != "k_medoids" or size == len(frequencies):
        return medoids, "completed", 0
    for iteration in range(1, spec.k_medoids_max_iterations + 1):
        clusters = {medoid: [] for medoid in medoids}
        for word in sorted(frequencies):
            options = [(distances.distance(word, medoid), medoid) for medoid in medoids]
            if any(distance is None for distance, _ in options):
                return medoids, "distance_limit", iteration
            clusters[min(options)[1]].append(word)
        updated = []
        for medoid, cluster in clusters.items():
            objectives = []
            for candidate in cluster:
                pairs = [
                    (frequencies[word], distances.distance(candidate, word))
                    for word in cluster
                ]
                if any(distance is None for _, distance in pairs):
                    return medoids, "distance_limit", iteration
                objectives.append(
                    (sum(weight * distance for weight, distance in pairs), candidate)
                )
            updated.append(min(objectives)[1] if objectives else medoid)
        updated = tuple(updated)
        if updated == medoids:
            return medoids, "completed", iteration
        medoids = updated
    return medoids, "iteration_limit", spec.k_medoids_max_iterations


def _simulate(net, size, spec):
    rng = Random(spec.random_seed)
    activities = {t.id: t.activity for t in net.transitions}
    representatives, seen = [], set()
    attempts = 0
    for _ in range(spec.simulation_max_attempts):
        attempts += 1
        marking, path = net.initial_marking, []
        for _ in range(spec.simulation_max_steps):
            if marking == net.final_marking:
                break
            enabled = enabled_transitions(net, marking)
            if not enabled:
                break
            transition = rng.choice(enabled)
            path.append(transition)
            marking = fire(net, marking, transition)
        if marking != net.final_marking:
            continue
        word = tuple(activities[t] for t in path if activities[t] is not None)
        if word in seen:
            continue
        seen.add(word)
        representatives.append(
            ConformanceRepresentative(
                len(representatives),
                None,
                (),
                0,
                "simulated",
                word,
                tuple(path),
                None,
                None,
            )
        )
        if len(representatives) == size:
            return tuple(representatives), "completed", attempts
    return tuple(representatives), "simulation_limit", attempts


def _realize(trace, net, path, operations):
    """Materialize an edit script on an accepting full transition sequence.

    Every transition occurrence is retained, including repeated IDs and silent
    moves. Original event occurrence IDs are consumed once in source order.
    """
    activities = {t.id: t.activity for t in net.transitions}
    marking, cursor, position, moves = net.initial_marking, 0, 0, []

    def model_move(kind, transition, event=None):
        nonlocal marking
        before = marking
        activity = activities[transition]
        if kind == "synchronous" and (event is None or event.activity != activity):
            raise ValueError("synchronous label differs from event")
        if (kind == "silent") != (activity is None):
            raise ValueError("silent/visible move kind differs from transition")
        marking = fire(net, marking, transition)
        moves.append(
            AlignmentMove(
                kind,
                None if event is None else event.event_id,
                transition,
                activity,
                int(kind == "model"),
                before.tokens,
                marking.tokens,
            )
        )

    for kind in operations:
        if kind == "log":
            if position >= len(trace.events):
                raise ValueError("edit script consumes too many events")
            event = trace.events[position]
            position += 1
            moves.append(
                AlignmentMove(
                    "log",
                    event.event_id,
                    None,
                    event.activity,
                    1,
                    marking.tokens,
                    marking.tokens,
                )
            )
            continue
        if kind not in ("synchronous", "model"):
            raise ValueError("edit script uses unsupported operation")
        while cursor < len(path) and activities[path[cursor]] is None:
            model_move("silent", path[cursor])
            cursor += 1
        if cursor == len(path):
            raise ValueError("edit script exceeds representative model word")
        event = None
        if kind == "synchronous":
            if position >= len(trace.events):
                raise ValueError("edit script consumes too many events")
            event = trace.events[position]
            position += 1
        model_move(kind, path[cursor], event)
        cursor += 1
    while cursor < len(path):
        if activities[path[cursor]] is not None:
            raise ValueError("edit script leaves a visible model transition")
        model_move("silent", path[cursor])
        cursor += 1
    if position != len(trace.events) or marking != net.final_marking:
        raise ValueError(
            "witness does not consume the case and reach exact final marking"
        )
    return tuple(moves)


def _path(net, alignment):
    path = tuple(
        move.transition_id for move in alignment.moves if move.transition_id is not None
    )
    activities = {t.id: t.activity for t in net.transitions}
    return path, tuple(activities[t] for t in path if activities[t] is not None)


def _deviations(moves):
    counters = {kind: Counter() for kind in ("model", "log", "synchronous")}
    for move in moves:
        if move.kind in counters:
            counters[move.kind][move.activity] += 1
    return ApproximationDeviations(
        *(tuple(sorted(counters[kind].items())) for kind in counters)
    )


def approximate_conformance(
    log: CaseInput,
    net: PetriNet,
    spec: SubsetConformanceSpec = SubsetConformanceSpec(),
) -> ComputationResult[SubsetConformanceApproximation]:
    """Return certified cost intervals and executable representative alignments.

    The lower bound combines unknown activity deletions, minimum model-word
    length and exact observed-anchor costs minus observed-word edit distance.
    A selected exact alignment is an equality anchor. Other cases are exact
    only if their bounds coincide; no midpoint is named a measured fitness.
    Mean-case fitness and pooled-denominator fitness are distinct aggregates.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be a PetriNet")
    if not isinstance(spec, SubsetConformanceSpec):
        raise TypeError("spec must be SubsetConformanceSpec")
    source = as_case_traces(log)
    request = SubsetConformanceRequest(model_digest(net), spec)
    parents = (source.computation_id,) if source.computation_id is not None else ()
    issues = []

    def result(status, value):
        return _result(
            "pix.case_centric.subset_conformance_approximation",
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
        issues.append(
            ComputeIssue("trace_result_unavailable", "A completed TraceSet is required")
        )
        return result(
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
        )
    cases = source.value.traces
    by_word = {}
    for trace in cases:
        by_word.setdefault(tuple(event.activity for event in trace.events), []).append(
            trace
        )
    frequencies = {word: len(group) for word, group in by_word.items()}
    size = min(spec.subset_size, len(by_word))
    distances = _Distances(spec)
    shortest = None
    shortest_length = None
    shortest_path = None
    representatives = ()
    selection = ApproximationSelection(
        spec.selection_method, spec.subset_size, size, (), "not_required", 0, 0
    )
    searches = 0
    alignment_spec = AlignmentSpec(max_states=spec.max_alignment_states)
    if cases:
        shortest = _align(
            ObjectTrace("shortest-model-word", source.value.object_type, ()),
            net,
            alignment_spec,
        )
        searches += 1
        if shortest.status == "optimal":
            shortest_path, shortest_word = _path(net, shortest)
            shortest_length = len(shortest_word)
        elif shortest.status == "search_limit":
            issues.append(
                ComputeIssue(
                    "subset_shortest_model_search_limit",
                    "Shortest accepted word is unknown; fitness normalization is unavailable",
                )
            )
        if shortest.status != "unreachable":
            if spec.selection_method == "simulation":
                representatives, state, attempts = _simulate(net, size, spec)
                selection = ApproximationSelection(
                    spec.selection_method,
                    spec.subset_size,
                    size,
                    (),
                    state,
                    0,
                    attempts,
                )
            else:
                selected, state, iterations = _select(
                    frequencies, size, spec, distances
                )
                selection = ApproximationSelection(
                    spec.selection_method,
                    spec.subset_size,
                    size,
                    selected,
                    state,
                    iterations,
                    0,
                )
                selected_results = []
                for word in selected:
                    # Reuse the already solved empty trace, but keep the actual
                    # selected case identity in its local evidence.
                    trace = by_word[word][0]
                    if not word:
                        aligned = TraceAlignment(
                            trace.object_id,
                            (),
                            shortest.status,
                            shortest.moves,
                            shortest.cost,
                            shortest.settled_states,
                            shortest.discovered_states,
                            shortest.lower_bound_cost,
                        )
                    else:
                        aligned = _align(trace, net, alignment_spec)
                        searches += 1
                    path, visible = (
                        _path(net, aligned)
                        if aligned.status == "optimal"
                        else (None, None)
                    )
                    selected_results.append(
                        ConformanceRepresentative(
                            len(selected_results),
                            word,
                            tuple(item.object_id for item in by_word[word]),
                            frequencies[word],
                            aligned.status,
                            visible,
                            path,
                            aligned.cost,
                            aligned,
                        )
                    )
                representatives = tuple(selected_results)
            if selection.status != "completed":
                issues.append(
                    ComputeIssue(
                        "subset_selection_limit",
                        f"Representative selection ended with {selection.status}; retained representatives remain usable",
                    )
                )
            if any(rep.status == "search_limit" for rep in representatives):
                issues.append(
                    ComputeIssue(
                        "subset_representative_search_limit",
                        "Some selected variants lack completed exact alignments",
                    )
                )

    model_unreachable = shortest is not None and shortest.status == "unreachable"
    if any(rep.status == "unreachable" for rep in representatives):
        # Reachability does not depend on the log when arbitrary log/model
        # moves are allowed. A finite exhausted search proves empty language.
        if shortest_path is not None:
            raise RuntimeError(
                "unreachable representative contradicts accepting model path"
            )
        model_unreachable = True
    labels = {t.activity for t in net.transitions if t.activity is not None}
    exact_reps = {
        rep.source_variant: rep for rep in representatives if rep.status == "optimal"
    }
    bounds_by_word = {}
    for word in by_word:
        evidence = [
            ApproximationBoundEvidence(
                "unknown_activities", sum(activity not in labels for activity in word)
            )
        ]
        if shortest is not None and shortest.lower_bound_cost is not None:
            evidence.append(
                ApproximationBoundEvidence(
                    "shortest_word_length",
                    max(0, shortest.lower_bound_cost - len(word)),
                )
            )
        rep = exact_reps.get(word)
        if rep is not None:
            evidence.append(
                ApproximationBoundEvidence(
                    "selected_exact", rep.exact_cost, rep.index, 0
                )
            )
        else:
            for anchor in exact_reps.values():
                distance = distances.distance(word, anchor.source_variant)
                if distance is not None:
                    evidence.append(
                        ApproximationBoundEvidence(
                            "representative_lipschitz",
                            max(0, anchor.exact_cost - distance),
                            anchor.index,
                            distance,
                        )
                    )
        bounds_by_word[word] = tuple(evidence)

    outputs = []
    for trace in cases:
        word = tuple(event.activity for event in trace.events)
        if model_unreachable:
            outputs.append(
                ApproximateTraceAlignment(
                    trace.object_id,
                    word,
                    "unreachable",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    (),
                    None,
                    False,
                    (),
                    _deviations(()),
                )
            )
            continue
        lower_evidence = bounds_by_word[word]
        lower = max(item.lower_bound_cost for item in lower_evidence)
        upper, best_moves, best_rep = None, (), None
        invalid = False

        def candidate(path, operations, expected, representative_index):
            nonlocal upper, best_moves, best_rep, invalid
            try:
                moves = _realize(trace, net, path, operations)
                cost = sum(move.cost for move in moves)
                if cost != expected:
                    raise ValueError(
                        "materialized witness cost differs from edit/selected cost"
                    )
            except (ValueError, KeyError) as error:
                invalid = True
                issues.append(
                    ComputeIssue(
                        "subset_invalid_witness", str(error), ("case", trace.object_id)
                    )
                )
                return
            if upper is None or cost < upper:
                upper, best_moves, best_rep = cost, moves, representative_index

        exact_rep = exact_reps.get(word)
        if exact_rep is not None:
            operations = tuple(
                move.kind
                for move in exact_rep.alignment_evidence.moves
                if move.kind != "silent"
            )
            candidate(
                exact_rep.transition_ids,
                operations,
                exact_rep.exact_cost,
                exact_rep.index,
            )
        else:
            if shortest_path is not None:
                candidate(
                    shortest_path,
                    ("log",) * len(word) + ("model",) * shortest_length,
                    len(word) + shortest_length,
                    None,
                )
            for representative in representatives:
                if representative.transition_ids is None:
                    continue
                edit = distances.compare(word, representative.visible_word)
                if edit is not None:
                    candidate(
                        representative.transition_ids,
                        edit[1],
                        edit[0],
                        representative.index,
                    )
        if upper is not None and lower > upper:
            raise RuntimeError("lower bound exceeds a validated accepting witness")
        exact = upper is not None and lower == upper and not invalid
        denominator = (
            len(word) + shortest_length if shortest_length is not None else None
        )
        fitness_lower = fitness_upper = None
        if denominator is not None:
            if denominator == 0 and upper is not None:
                fitness_lower = fitness_upper = (1, 1)
            elif upper is not None:
                fitness_lower = _ratio(
                    max(Fraction(), 1 - Fraction(upper, denominator))
                )
                fitness_upper = _ratio(1 - Fraction(lower, denominator))
        outputs.append(
            ApproximateTraceAlignment(
                trace.object_id,
                word,
                "invalid_witness"
                if invalid
                else "exact"
                if exact
                else "bounded"
                if upper is not None
                else "search_limit",
                lower,
                upper,
                lower if exact else None,
                fitness_lower,
                fitness_upper,
                denominator,
                best_moves,
                best_rep,
                upper is not None,
                lower_evidence,
                _deviations(best_moves),
            )
        )
    if distances.limited:
        issues.append(
            ComputeIssue(
                "subset_edit_distance_limit",
                "Some distance calculations exceeded cell budgets; bounds use completed calculations only",
            )
        )
    if any(item.status == "search_limit" for item in outputs):
        issues.append(
            ComputeIssue(
                "subset_no_complete_representative",
                "No executable representative path was available for some cases",
            )
        )
    lower_sum = (
        sum(item.lower_bound_cost for item in outputs)
        if all(item.lower_bound_cost is not None for item in outputs)
        else None
    )
    upper_sum = (
        sum(item.upper_bound_cost for item in outputs)
        if all(item.upper_bound_cost is not None for item in outputs)
        else None
    )
    mean_lower = mean_upper = pooled_lower = pooled_upper = None
    if (
        outputs
        and lower_sum is not None
        and upper_sum is not None
        and all(
            item.fitness_lower_ratio is not None
            and item.fitness_upper_ratio is not None
            for item in outputs
        )
    ):
        mean_lower = _ratio(
            sum((Fraction(*item.fitness_lower_ratio) for item in outputs), Fraction())
            / len(outputs)
        )
        mean_upper = _ratio(
            sum((Fraction(*item.fitness_upper_ratio) for item in outputs), Fraction())
            / len(outputs)
        )
        denominator = sum(item.normalization_denominator for item in outputs)
        if denominator == 0:
            pooled_lower = pooled_upper = (1, 1)
        else:
            pooled_lower = _ratio(max(Fraction(), 1 - Fraction(upper_sum, denominator)))
            pooled_upper = _ratio(1 - Fraction(lower_sum, denominator))
    value = SubsetConformanceApproximation(
        request.model_digest,
        selection,
        representatives,
        shortest,
        shortest_length,
        tuple(outputs),
        len(by_word),
        sum(item.status == "exact" for item in outputs),
        sum(item.status == "bounded" for item in outputs),
        sum(item.status in ("search_limit", "invalid_witness") for item in outputs),
        sum(item.status == "unreachable" for item in outputs),
        lower_sum,
        upper_sum,
        mean_lower,
        mean_upper,
        pooled_lower,
        pooled_upper,
        distances.cells,
        len(distances.limited),
        searches,
    )
    return result(ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED, value)


RESULT_SCHEMAS = {
    "pix.case_centric.subset_conformance_approximation": (
        "case-subset-conformance-approximation",
        SubsetConformanceRequest,
        SubsetConformanceApproximation,
    ),
}

__all__ = (
    "SubsetConformanceSpec",
    "SubsetConformanceRequest",
    "ConformanceRepresentative",
    "ApproximationSelection",
    "ApproximationBoundEvidence",
    "ApproximationDeviations",
    "ApproximateTraceAlignment",
    "SubsetConformanceApproximation",
    "approximate_conformance",
)
