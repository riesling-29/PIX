"""Native Alpha and Alpha+ accepting-net discovery, without upstream runtimes.

Alpha enumerates maximal nonempty causal pairs, not a process-tree fallback.
Alpha+ uses the two-sided ABA/BAB relation and removes/restores length-one
loops. Definitions: de Medeiros et al., *Process mining: extending the alpha
algorithm to mine short loops*, definitions 3.3 and 4.4:
https://pure.tue.nl/ws/files/1864325/576199.pdf

The default ``exact`` loop attachment is definition 4.4. ``containing`` is an
explicit alternative matching the containment rule in the pinned PM4Py
2.7.23.8 Alpha+ implementation. Those rules need not coincide outside the
paper's assumptions. Artificial start/end transitions are retained in Alpha+;
their identities cannot collide with visible activity labels. No soundness,
log-completeness, noise tolerance or arbitrary-log fitness is certified.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, Literal

from pix.compute._common import _derived_result
from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseLog


@dataclass(frozen=True, slots=True)
class AlphaSpec:
    """Resource limits abort discovery rather than return a truncated net.

    Classic Alpha rejects empty traces, for which its standard source/sink
    construction has no accepting path. Alpha+ accepts them through its
    explicit artificial-boundary construction. Trace multiplicities have no
    effect on either relation-based miner.
    """

    SPEC_TYPE: ClassVar[str] = "pix.case_centric.AlphaSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    variant: Literal["classic", "plus"] = "classic"
    loop_attachment: Literal["exact", "containing"] = "exact"
    max_activities: int = 1024
    max_candidates: int = 100_000
    max_checks: int = 2_000_000

    def __post_init__(self) -> None:
        if self.variant not in ("classic", "plus"):
            raise ValueError("variant must be classic or plus")
        if self.loop_attachment not in ("exact", "containing"):
            raise ValueError("loop_attachment must be exact or containing")
        if self.variant == "classic" and self.loop_attachment != "exact":
            raise ValueError("loop_attachment only applies to Alpha+")
        for field in ("max_activities", "max_candidates", "max_checks"):
            value = getattr(self, field)
            if type(value) is not int or value < 1:
                raise ValueError(f"{field} must be a positive integer")


@dataclass(frozen=True, slots=True)
class AlphaPlace:
    """A maximal-pair witness; IDs refer to transitions in the returned net."""

    place_id: str
    input_transition_ids: tuple[str, ...]
    output_transition_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AlphaDiscovery:
    model: PetriNet
    variant: str
    causal_pairs: tuple[tuple[str, str], ...]
    parallel_pairs: tuple[tuple[str, str], ...]
    maximal_places: tuple[AlphaPlace, ...]
    length_one_activities: tuple[str, ...]
    length_two_pairs: tuple[tuple[str, str], ...]
    candidate_count: int
    relation_checks: int


class _LimitExceeded(Exception):
    pass


def _maximal_pairs(
    alphabet: tuple[int, ...],
    follows: set[tuple[int, int]],
    causal: set[tuple[int, int]],
    spec: AlphaSpec,
) -> tuple[tuple[tuple[frozenset[int], frozenset[int]], ...], int, int]:
    """Enumerate exactly by single-member extensions of causal singleton pairs.

    Every valid pair has a valid singleton ancestor, so this closure visits
    every valid pair. A pair is maximal iff it admits no single extension.
    Consequently no quadratic all-pairs maximality pass is needed.
    """
    candidates: list[tuple[frozenset[int], frozenset[int]]] = []
    seen: set[tuple[frozenset[int], frozenset[int]]] = set()
    checks = 0

    def tick() -> None:
        nonlocal checks
        checks += 1
        if checks > spec.max_checks:
            raise _LimitExceeded("max_checks exceeded during pair enumeration")

    def insert(pair: tuple[frozenset[int], frozenset[int]]) -> None:
        if pair not in seen:
            if len(seen) >= spec.max_candidates:
                raise _LimitExceeded("max_candidates exceeded during pair enumeration")
            seen.add(pair)
            candidates.append(pair)

    def sharp(a: int, b: int) -> bool:
        tick()
        return (a, b) not in follows and (b, a) not in follows

    for a, b in sorted(causal):
        if sharp(a, a) and sharp(b, b):
            insert((frozenset((a,)), frozenset((b,))))
    maximal = []
    cursor = 0
    while cursor < len(candidates):
        left, right = candidates[cursor]
        cursor += 1
        extended = False
        for item in alphabet:
            tick()
            if item not in left and sharp(item, item):
                unrelated = all(sharp(item, other) for other in sorted(left))
                causes = True
                if unrelated:
                    for other in sorted(right):
                        tick()
                        if (item, other) not in causal:
                            causes = False
                            break
                    if causes:
                        insert((left | {item}, right))
                        extended = True
            if item not in right and sharp(item, item):
                unrelated = all(sharp(item, other) for other in sorted(right))
                causes = True
                if unrelated:
                    for other in sorted(left):
                        tick()
                        if (other, item) not in causal:
                            causes = False
                            break
                    if causes:
                        insert((left, right | {item}))
                        extended = True
        if not extended:
            maximal.append((left, right))
    maximal.sort(key=lambda pair: (tuple(sorted(pair[0])), tuple(sorted(pair[1]))))
    return tuple(maximal), len(candidates), checks


def discover_alpha(
    log: CaseLog | ComputationResult[TraceSet],
    spec: AlphaSpec = AlphaSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[AlphaDiscovery]:
    """Discover Alpha/Alpha+ from source-ordered cases or an explicit TraceSet.

    A ``computed`` result means the specified construction finished. It does
    not mean the discovered net accepts every observed trace. Input projection
    issues and the parent computation identity remain attached to the result.
    """
    from pix.case_centric._input import as_case_traces

    if not isinstance(spec, AlphaSpec):
        raise TypeError("spec must be AlphaSpec")
    parent = as_case_traces(log, trace_spec)
    parents = (parent.computation_id,) if parent.computation_id else ()
    issues = list(parent.issues)

    def result(status, value=None, extra=()):
        return _derived_result(
            "pix.case_centric.discover_alpha",
            parent.source_digest,
            spec,
            status,
            value,
            (*issues, *extra),
            parent_computation_ids=parents,
        )

    if parent.value is None:
        return result(
            parent.status,
            extra=(
                ComputeIssue(
                    "trace_input_unavailable", "Discovery needs available case traces"
                ),
            ),
        )
    raw = tuple(
        tuple(event.activity for event in trace.events) for trace in parent.value.traces
    )
    if not raw:
        return result(
            ComputeStatus.UNAVAILABLE,
            extra=(ComputeIssue("empty_log", "No observed cases are available"),),
        )
    if any(not isinstance(a, str) or not a.strip() for trace in raw for a in trace):
        return result(
            ComputeStatus.INVALID_INPUT,
            extra=(
                ComputeIssue(
                    "invalid_activity", "Alpha needs nonblank activity strings"
                ),
            ),
        )
    labels = tuple(sorted({a for trace in raw for a in trace}))
    if len(labels) > spec.max_activities:
        return result(
            ComputeStatus.UNAVAILABLE,
            extra=(
                ComputeIssue(
                    "activity_limit", "max_activities exceeded; no model was returned"
                ),
            ),
        )
    if spec.variant == "classic" and any(not trace for trace in raw):
        return result(
            ComputeStatus.UNAVAILABLE,
            extra=(
                ComputeIssue(
                    "empty_trace_unsupported",
                    "Classic Alpha cannot represent epsilon with its standard source/sink construction",
                ),
            ),
        )
    numbers = {label: index for index, label in enumerate(labels)}
    traces = tuple(tuple(numbers[a] for a in trace) for trace in raw)
    all_follows = {(a, b) for trace in traces for a, b in zip(trace, trace[1:])}
    loops_one = {a for a, b in all_follows if a == b}
    ids = {index: f"alpha:t:{index}" for index in range(len(labels))}
    transitions = [Transition(ids[index], label) for index, label in enumerate(labels)]
    if spec.variant == "plus":
        start, end = len(labels), len(labels) + 1
        ids.update({start: "alpha:tau:start", end: "alpha:tau:end"})
        transitions.extend((Transition(ids[start]), Transition(ids[end])))
        augmented = tuple((start, *trace, end) for trace in traces)
        all_follows = {(a, b) for trace in augmented for a, b in zip(trace, trace[1:])}
        traces = tuple(
            tuple(a for a in trace if a not in loops_one) for trace in augmented
        )
    else:
        if loops_one or any(
            a == c and a != b
            for trace in traces
            for a, b, c in zip(trace, trace[1:], trace[2:])
        ):
            issues.append(
                ComputeIssue(
                    "classic_short_loop_limitation",
                    "Classic Alpha does not reconstruct short loops; output fitness is not certified",
                )
            )
    alphabet = tuple(sorted({a for trace in traces for a in trace}))
    follows = {(a, b) for trace in traces for a, b in zip(trace, trace[1:])}
    triangles = {
        (a, b)
        for trace in traces
        for a, b, c in zip(trace, trace[1:], trace[2:])
        if a == c and a != b
    }
    square = (
        {(a, b) for a, b in triangles if (b, a) in triangles}
        if spec.variant == "plus"
        else set()
    )
    causal = {(a, b) for a, b in follows if (b, a) not in follows or (a, b) in square}
    parallel = {
        (a, b)
        for a, b in follows
        if a != b and (b, a) in follows and (a, b) not in square
    }
    if spec.variant == "plus" and triangles - square:
        issues.append(
            ComputeIssue(
                "one_sided_short_loop_evidence",
                "Some ABA observations have no BAB counterpart; Alpha+ loop completeness is not established",
            )
        )
    try:
        maximal, candidate_count, checks = _maximal_pairs(
            alphabet, follows, causal, spec
        )
    except _LimitExceeded as exc:
        return result(
            ComputeStatus.UNAVAILABLE,
            extra=(ComputeIssue("candidate_limit", str(exc)),),
        )
    places = [Place("alpha:source"), Place("alpha:sink")]
    arcs = set()
    for activity in {trace[0] for trace in traces}:
        arcs.add(Arc("alpha:source", ids[activity]))
    for activity in {trace[-1] for trace in traces}:
        arcs.add(Arc(ids[activity], "alpha:sink"))
    witnesses = []
    for index, (left, right) in enumerate(maximal):
        place_id = f"alpha:p:{index}"
        places.append(Place(place_id))
        in_ids = tuple(ids[a] for a in sorted(left))
        out_ids = tuple(ids[b] for b in sorted(right))
        arcs.update(Arc(a, place_id) for a in in_ids)
        arcs.update(Arc(place_id, b) for b in out_ids)
        witnesses.append(AlphaPlace(place_id, in_ids, out_ids))
    if spec.variant == "plus":
        for activity in sorted(loops_one):
            before = {a for a, b in all_follows if b == activity and a not in loops_one}
            after = {b for a, b in all_follows if a == activity and b not in loops_one}
            left, right = frozenset(before - after), frozenset(after - before)
            matches = (
                [
                    index
                    for index, (a, b) in enumerate(maximal)
                    if (
                        left == a and right == b
                        if spec.loop_attachment == "exact"
                        else left <= a and right <= b
                    )
                ]
                if left and right
                else []
            )
            if not matches:
                return result(
                    ComputeStatus.UNAVAILABLE,
                    extra=(
                        ComputeIssue(
                            "alpha_plus_unresolved_loop_context",
                            "No maximal place matches this length-one loop context under the requested attachment rule",
                            (labels[activity],),
                        ),
                    ),
                )
            for index in matches:
                place_id = witnesses[index].place_id
                arcs.add(Arc(place_id, ids[activity]))
                arcs.add(Arc(ids[activity], place_id))
    model = PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking((("alpha:source", 1),)),
        Marking((("alpha:sink", 1),)),
    )
    issues.append(
        ComputeIssue(
            "rediscoverability_not_certified",
            "The construction does not certify a complete log, structured workflow-net assumptions, soundness, or fitness",
        )
    )
    payload = AlphaDiscovery(
        model,
        spec.variant,
        tuple(sorted((ids[a], ids[b]) for a, b in causal)),
        tuple(sorted((ids[a], ids[b]) for a, b in parallel)),
        tuple(witnesses),
        tuple(labels[a] for a in sorted(loops_one)),
        tuple(sorted((labels[a], labels[b]) for a, b in square if a < b)),
        candidate_count,
        checks,
    )
    status = (
        ComputeStatus.PARTIAL
        if parent.status is ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED
    )
    return result(status, payload)


def discover_alpha_plus(
    log: CaseLog | ComputationResult[TraceSet],
    spec: AlphaSpec = AlphaSpec(variant="plus"),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[AlphaDiscovery]:
    """Alpha+ convenience entry point; all other spec fields remain explicit."""
    if not isinstance(spec, AlphaSpec):
        raise TypeError("spec must be AlphaSpec")
    return discover_alpha(log, replace(spec, variant="plus"), trace_spec=trace_spec)


RESULT_SCHEMAS = {
    "pix.case_centric.discover_alpha": ("alpha-discovery", AlphaSpec, AlphaDiscovery),
}

__all__ = (
    "AlphaSpec",
    "AlphaPlace",
    "AlphaDiscovery",
    "discover_alpha",
    "discover_alpha_plus",
)
