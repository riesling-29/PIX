"""Native case-centric relation, state, batch and local-model discovery.

All behavioral order is the input trace order. Timestamps are used only by
batch discovery, which requires explicit observed intervals. Local process
models use an explicitly bounded tree-language search and projected-window
support; its metrics are not aliases of another library's alignment metrics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations, product
from math import isfinite

from pix.case_centric._input import as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseLog


def _positive(value: object, name: str, minimum: int = 1) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _finish(parent, operator, spec, payload, issues=(), *, partial=False):
    if parent.value is None:
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            parent.status,
            None,
            parent.issues,
            parent_computation_ids=(parent.computation_id,)
            if parent.computation_id
            else (),
        )
    return _derived_result(
        operator,
        parent.source_digest,
        spec,
        ComputeStatus.PARTIAL
        if partial or parent.status == ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED,
        payload,
        parent.issues + issues,
        parent_computation_ids=(parent.computation_id,)
        if parent.computation_id
        else (),
    )


@dataclass(frozen=True, slots=True)
class RelationDiscoverySpec:
    """Event-pair multiplicity or one contribution per case/activity pair."""

    counting: str = "occurrences"
    max_event_pairs: int = 1_000_000

    def __post_init__(self):
        if self.counting not in ("occurrences", "cases"):
            raise ValueError("counting must be occurrences or cases")
        _positive(self.max_event_pairs, "max_event_pairs")


@dataclass(frozen=True, slots=True)
class RelationEdge:
    source: str
    target: str
    count: int
    case_count: int


@dataclass(frozen=True, slots=True)
class CaseRelationGraph:
    relation: str
    activity_counts: tuple[tuple[str, int], ...]
    edges: tuple[RelationEdge, ...]
    start_counts: tuple[tuple[str, int], ...]
    end_counts: tuple[tuple[str, int], ...]
    trace_count: int
    empty_trace_count: int
    examined_event_pairs: int
    complete: bool


def _relations(log, spec, trace_spec, eventual):
    if not isinstance(spec, RelationDiscoverySpec):
        raise TypeError("spec must be RelationDiscoverySpec")
    parent = as_case_traces(log, trace_spec)
    operator = (
        "pix.case_centric.discover_efg" if eventual else "pix.case_centric.discover_dfg"
    )
    if parent.value is None:
        return _finish(parent, operator, spec, None)
    counts, starts, ends, edges, cases = (
        Counter(),
        Counter(),
        Counter(),
        Counter(),
        Counter(),
    )
    empty, examined, complete = 0, 0, True
    for trace in parent.value.traces:
        acts = tuple(e.activity for e in trace.events)
        counts.update(acts)
        if acts:
            starts[acts[0]] += 1
            ends[acts[-1]] += 1
        else:
            empty += 1
    for trace in parent.value.traces:
        acts = tuple(e.activity for e in trace.events)
        pairs = (
            ((i, j) for i in range(len(acts)) for j in range(i + 1, len(acts)))
            if eventual
            else ((i, i + 1) for i in range(len(acts) - 1))
        )
        seen = set()
        for i, j in pairs:
            if examined == spec.max_event_pairs:
                complete = False
                break
            examined += 1
            pair = (acts[i], acts[j])
            edges[pair] += 1
            seen.add(pair)
        cases.update(seen)
        if not complete:
            break
    payload = CaseRelationGraph(
        "eventually_follows" if eventual else "directly_follows",
        tuple(sorted(counts.items())),
        tuple(
            RelationEdge(
                a,
                b,
                (edges if spec.counting == "occurrences" else cases)[(a, b)],
                cases[(a, b)],
            )
            for a, b in sorted(edges)
        ),
        tuple(sorted(starts.items())),
        tuple(sorted(ends.items())),
        len(parent.value.traces),
        empty,
        examined,
        complete,
    )
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "event_pair_limit",
                "Edge counts are lower bounds; the pair budget was exhausted. Activity and boundary counts cover the whole input.",
            ),
        )
    )
    return _finish(parent, operator, spec, payload, issues, partial=not complete)


def discover_dfg(
    log: CaseLog | ComputationResult[TraceSet],
    spec: RelationDiscoverySpec = RelationDiscoverySpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Count adjacent activity pairs in source order, including repeated labels."""
    return _relations(log, spec, trace_spec, False)


def discover_efg(
    log: CaseLog | ComputationResult[TraceSet],
    spec: RelationDiscoverySpec = RelationDiscoverySpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Count all strictly ordered event-position pairs, not only nearest matches."""
    return _relations(log, spec, trace_spec, True)


@dataclass(frozen=True, slots=True)
class FootprintSpec:
    max_activity_pairs: int = 1_000_000

    def __post_init__(self):
        _positive(self.max_activity_pairs, "max_activity_pairs")


@dataclass(frozen=True, slots=True)
class FootprintModel:
    activities: tuple[str, ...]
    directly_follows: tuple[tuple[str, str], ...]
    causal: tuple[tuple[str, str], ...]
    parallel: tuple[tuple[str, str], ...]
    unrelated: tuple[tuple[str, str], ...]
    start_activities: tuple[str, ...]
    end_activities: tuple[str, ...]
    loop_activities: tuple[str, ...]
    minimum_trace_length: int | None
    empty_trace_count: int


def discover_footprints(
    log: CaseLog | ComputationResult[TraceSet],
    spec: FootprintSpec = FootprintSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Alpha footprint: asymmetric succession, symmetric succession, and neither.

    ``parallel`` contains both directions for distinct labels. It is observed
    bidirectional adjacency, not proof of concurrency. Self succession is in
    ``loop_activities``; unrelated pairs are canonical unordered pairs.
    """
    if not isinstance(spec, FootprintSpec):
        raise TypeError("spec must be FootprintSpec")
    parent = as_case_traces(log, trace_spec)
    if parent.value is None:
        return _finish(parent, "pix.case_centric.discover_footprints", spec, None)
    traces = [tuple(e.activity for e in t.events) for t in parent.value.traces]
    activities = tuple(sorted({a for t in traces for a in t}))
    if len(activities) * (len(activities) - 1) // 2 > spec.max_activity_pairs:
        return _derived_result(
            "pix.case_centric.discover_footprints",
            parent.source_digest,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            parent.issues
            + (
                ComputeIssue(
                    "activity_pair_limit", "Complete footprint exceeds the pair budget."
                ),
            ),
            parent_computation_ids=(parent.computation_id,),
        )
    follows = {p for t in traces for p in zip(t, t[1:])}
    model = FootprintModel(
        activities,
        tuple(sorted(follows)),
        tuple(sorted((a, b) for a, b in follows if (b, a) not in follows)),
        tuple(sorted((a, b) for a, b in follows if a != b and (b, a) in follows)),
        tuple(
            (a, b)
            for a, b in combinations(activities, 2)
            if (a, b) not in follows and (b, a) not in follows
        ),
        tuple(sorted({t[0] for t in traces if t})),
        tuple(sorted({t[-1] for t in traces if t})),
        tuple(a for a in activities if (a, a) in follows),
        min(map(len, traces), default=None),
        sum(not t for t in traces),
    )
    return _finish(parent, "pix.case_centric.discover_footprints", spec, model)


@dataclass(frozen=True, slots=True)
class TransitionSystemSpec:
    view: str = "sequence"
    direction: str = "past"
    window: int | None = 2
    max_states: int = 100_000
    max_context_items: int = 1_000_000

    def __post_init__(self):
        if self.view not in ("sequence", "set", "multiset"):
            raise ValueError("view must be sequence, set or multiset")
        if self.direction not in ("past", "future"):
            raise ValueError("direction must be past or future")
        if self.window is not None:
            _positive(self.window, "window", 0)
        _positive(self.max_states, "max_states")
        _positive(self.max_context_items, "max_context_items")


@dataclass(frozen=True, slots=True)
class StateNode:
    id: str
    context: tuple[str, ...]
    visits: int
    initial_count: int
    final_count: int


@dataclass(frozen=True, slots=True)
class StateEdge:
    source: str
    target: str
    activity: str
    occurrence_count: int


@dataclass(frozen=True, slots=True)
class TransitionSystem:
    states: tuple[StateNode, ...]
    transitions: tuple[StateEdge, ...]
    trace_count: int
    complete: bool


def _state_graph(parent, spec, operator):
    if parent.value is None:
        return _finish(parent, operator, spec, None)
    visits, initial, final, edges = Counter(), Counter(), Counter(), Counter()
    complete, covered, stored_items = True, 0, 0
    for trace in parent.value.traces:
        acts = tuple(e.activity for e in trace.events)
        contexts = []
        novel, context_items = set(), 0
        for position in range(len(acts) + 1):
            left = max(0, position - spec.window) if spec.window is not None else 0
            right = (
                min(len(acts), position + spec.window)
                if spec.window is not None
                else len(acts)
            )
            context = (
                acts[left:position]
                if spec.direction == "past"
                else acts[position:right]
            )
            if spec.view == "set":
                context = tuple(sorted(set(context)))
            elif spec.view == "multiset":
                context = tuple(sorted(context))
            if context not in visits and context not in novel:
                novel.add(context)
                context_items += len(context)
            if (
                len(visits) + len(novel) > spec.max_states
                or stored_items + context_items > spec.max_context_items
            ):
                complete = False
                break
            contexts.append(context)
        if not complete:
            break
        stored_items += context_items
        visits.update(contexts)
        initial[contexts[0]] += 1
        final[contexts[-1]] += 1
        edges.update(
            (contexts[i], contexts[i + 1], activity) for i, activity in enumerate(acts)
        )
        covered += 1
    ids = {c: f"s{i}" for i, c in enumerate(sorted(visits))}
    payload = TransitionSystem(
        tuple(
            StateNode(ids[c], c, visits[c], initial[c], final[c])
            for c in sorted(visits)
        ),
        tuple(
            StateEdge(ids[a], ids[b], label, count)
            for (a, b, label), count in sorted(edges.items())
        ),
        covered,
        complete,
    )
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "state_limit",
                f"State/context budget exhausted. Only {covered} whole traces were incorporated; later traces were not incorporated.",
            ),
        )
    )
    return _finish(parent, operator, spec, payload, issues, partial=not complete)


def discover_transition_system(
    log: CaseLog | ComputationResult[TraceSet],
    spec: TransitionSystemSpec = TransitionSystemSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    if not isinstance(spec, TransitionSystemSpec):
        raise TypeError("spec must be TransitionSystemSpec")
    return _state_graph(
        as_case_traces(log, trace_spec),
        spec,
        "pix.case_centric.discover_transition_system",
    )


@dataclass(frozen=True, slots=True)
class PrefixTreeSpec:
    max_states: int = 100_000
    max_context_items: int = 1_000_000

    def __post_init__(self):
        _positive(self.max_states, "max_states")
        _positive(self.max_context_items, "max_context_items")


def discover_prefix_tree(
    log: CaseLog | ComputationResult[TraceSet],
    spec: PrefixTreeSpec = PrefixTreeSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Frequency annotated prefix acceptor. Final counts retain empty traces."""
    if not isinstance(spec, PrefixTreeSpec):
        raise TypeError("spec must be PrefixTreeSpec")
    parent = as_case_traces(log, trace_spec)
    intermediate = _state_graph(
        parent,
        TransitionSystemSpec(
            window=None,
            max_states=spec.max_states,
            max_context_items=spec.max_context_items,
        ),
        "pix.case_centric.discover_transition_system",
    )
    return _derived_result(
        "pix.case_centric.discover_prefix_tree",
        parent.source_digest,
        spec,
        intermediate.status,
        intermediate.value,
        intermediate.issues,
        parent_computation_ids=(parent.computation_id,)
        if parent.computation_id
        else (),
    )


@dataclass(frozen=True, slots=True)
class BatchDiscoverySpec:
    resource_key: str = "org:resource"
    start_key: str = "start_timestamp"
    end_key: str = "time:timestamp"
    merge_distance_seconds: float = 0.0
    minimum_batch_size: int = 2

    def __post_init__(self):
        for key in (self.resource_key, self.start_key, self.end_key):
            if not isinstance(key, str) or not key:
                raise ValueError("attribute keys must be nonempty strings")
        if (
            isinstance(self.merge_distance_seconds, bool)
            or not isinstance(self.merge_distance_seconds, (float, int))
            or not isfinite(self.merge_distance_seconds)
            or self.merge_distance_seconds < 0
        ):
            raise ValueError("merge distance must be finite and nonnegative")
        object.__setattr__(
            self, "merge_distance_seconds", float(self.merge_distance_seconds)
        )
        _positive(self.minimum_batch_size, "minimum_batch_size", 2)


@dataclass(frozen=True, slots=True)
class BatchInterval:
    case_id: str
    event_id: str
    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class EventBatch:
    activity: str
    resource: str
    kind: str
    start: datetime
    end: datetime
    intervals: tuple[BatchInterval, ...]
    has_positive_gap: bool


@dataclass(frozen=True, slots=True)
class BatchDiscovery:
    batches: tuple[EventBatch, ...]
    examined_events: int


def discover_batches(
    log: CaseLog,
    spec: BatchDiscoverySpec = BatchDiscoverySpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Activity/resource interval components, with the five Martin batch labels.

    Near but disjoint intervals may be merged when requested. Such a component
    has ``has_positive_gap=True``; the reference's residual ``concurrent``
    label does not by itself establish temporal overlap.
    """
    if not isinstance(log, CaseLog):
        raise TypeError(
            "batch discovery requires CaseLog with interval/resource attributes"
        )
    if not isinstance(spec, BatchDiscoverySpec):
        raise TypeError("spec must be BatchDiscoverySpec")
    parent = as_case_traces(log, trace_spec)
    operator = "pix.case_centric.discover_batches"
    if parent.value is None:
        return _finish(parent, operator, spec, None)
    activities = {e.event_id: e.activity for t in parent.value.traces for e in t.events}
    grouped = defaultdict(list)
    try:
        for trace in log.traces:
            for event in trace.events:
                resource, start, end = (
                    log.attribute(event, key)
                    for key in (spec.resource_key, spec.start_key, spec.end_key)
                )
                if (
                    resource is None
                    or resource.type not in ("string", "id")
                    or not resource.value
                ):
                    raise ValueError(f"event {event.id}: missing textual resource")
                if any(
                    x is None or x.type != "date" or x.value.utcoffset() is None
                    for x in (start, end)
                ):
                    raise ValueError(
                        f"event {event.id}: missing timezone-aware start/end"
                    )
                if end.value < start.value:
                    raise ValueError(f"event {event.id}: end precedes start")
                grouped[(activities[event.id], resource.value)].append(
                    BatchInterval(trace.id, event.id, start.value, end.value)
                )
    except ValueError as exc:
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            parent.issues + (ComputeIssue("batch_attributes_unavailable", str(exc)),),
            parent_computation_ids=(parent.computation_id,),
        )
    batches = []
    for (activity, resource), intervals in sorted(grouped.items()):
        components = []
        running = []
        right = None
        for interval in sorted(intervals, key=lambda x: (x.start, x.end, x.event_id)):
            if (
                right is not None
                and (interval.start - right).total_seconds()
                > spec.merge_distance_seconds
            ):
                components.append(running)
                running, right = [], None
            running.append(interval)
            right = max(right, interval.end) if right is not None else interval.end
        if running:
            components.append(running)
        for component in components:
            if len(component) < spec.minimum_batch_size:
                continue
            starts, ends = {e.start for e in component}, {e.end for e in component}
            kind = (
                "simultaneous"
                if len(starts) == len(ends) == 1
                else "batching_at_start"
                if len(starts) == 1
                else "batching_at_end"
                if len(ends) == 1
                else "sequential"
                if all(a.end == b.start for a, b in zip(component, component[1:]))
                else "concurrent"
            )
            right = component[0].end
            gap = False
            for event in component[1:]:
                gap |= event.start > right
                right = max(right, event.end)
            batches.append(
                EventBatch(
                    activity,
                    resource,
                    kind,
                    min(starts),
                    max(ends),
                    tuple(component),
                    gap,
                )
            )
    return _finish(
        parent, operator, spec, BatchDiscovery(tuple(batches), len(activities))
    )


@dataclass(frozen=True, slots=True)
class LocalProcessModelSpec:
    """Finite search over binary trees and projected contiguous occurrences.

    Loop languages and long finite languages are evaluated only up to the
    explicit event-length bound. ``bounded_language_fit`` uses that finite
    denominator; ``prefix_determinism`` uses its language-prefix choices.
    """

    selected_activities: tuple[str, ...] | None = None
    operators: tuple[str, ...] = ("sequence", "xor", "parallel", "loop")
    max_leaves: int = 3
    max_word_length: int = 6
    max_candidates: int = 1000
    max_language_words: int = 1000
    max_language_expansions: int = 100_000
    minimum_frequency: int = 1
    maximum_models: int = 100

    def __post_init__(self):
        if self.selected_activities is not None:
            if not isinstance(self.selected_activities, tuple) or any(
                not isinstance(a, str) or not a.strip()
                for a in self.selected_activities
            ):
                raise ValueError(
                    "selected activities must be a tuple of nonblank strings"
                )
            object.__setattr__(
                self,
                "selected_activities",
                tuple(sorted(set(self.selected_activities))),
            )
        if (
            not isinstance(self.operators, tuple)
            or not self.operators
            or any(
                o not in ("sequence", "xor", "parallel", "loop") for o in self.operators
            )
        ):
            raise ValueError("operators must select sequence/xor/parallel/loop")
        object.__setattr__(self, "operators", tuple(sorted(set(self.operators))))
        for key in (
            "max_leaves",
            "max_word_length",
            "max_candidates",
            "max_language_words",
            "max_language_expansions",
            "minimum_frequency",
            "maximum_models",
        ):
            _positive(getattr(self, key), key)
        if self.max_leaves > 10 or self.max_word_length > 128:
            raise ValueError("max_leaves <= 10 and max_word_length <= 128 are required")


@dataclass(frozen=True, slots=True)
class LocalOccurrence:
    case_id: str
    event_ids: tuple[str, ...]
    activities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LocalProcessModel:
    tree: ProcessTree
    frequency: int
    case_support: int
    confidence: float
    activity_coverage: float
    bounded_language_fit: float
    prefix_determinism: float
    language_word_count: int
    language_is_complete: bool
    occurrences: tuple[LocalOccurrence, ...]


@dataclass(frozen=True, slots=True)
class LocalProcessModelDiscovery:
    models: tuple[LocalProcessModel, ...]
    candidates_evaluated: int
    candidates_skipped_for_language_limit: int
    search_complete: bool
    matched_model_count: int


class _LanguageLimit(Exception):
    pass


def _language(tree, bound, limit, expansion_limit=100_000, work=None):
    if work is None:
        work = [0]

    def tick():
        work[0] += 1
        if work[0] > expansion_limit:
            raise _LanguageLimit

    def checked(words):
        result = set()
        for word in words:
            tick()
            if len(word) <= bound:
                result.add(word)
                if len(result) > limit:
                    raise _LanguageLimit
        return result

    def shuffle(left, right):
        tick()
        if not left:
            yield right
        elif not right:
            yield left
        else:
            for tail in shuffle(left[1:], right):
                yield (left[0],) + tail
            for tail in shuffle(left, right[1:]):
                yield (right[0],) + tail

    if tree.operator == "activity":
        return {(tree.activity,)}, True
    left, lc = _language(tree.children[0], bound, limit, expansion_limit, work)
    right, rc = _language(tree.children[1], bound, limit, expansion_limit, work)
    if tree.operator == "xor":
        return checked(iter(left | right)), lc and rc
    if tree.operator in ("sequence", "parallel"):
        complete = (
            lc and rc and all(len(a) + len(b) <= bound for a, b in product(left, right))
        )

        def merged():
            for a, b in product(left, right):
                tick()
                if len(a) + len(b) <= bound:
                    if tree.operator == "sequence":
                        yield a + b
                    else:
                        yield from shuffle(a, b)

        words = merged()
        return checked(words), complete
    words, frontier = set(left), set(left)
    while frontier:

        def extended():
            for a, b, c in product(frontier, right, left):
                tick()
                if len(a) + len(b) + len(c) <= bound:
                    yield a + b + c

        extension = checked(extended())
        frontier = extension - words
        words.update(frontier)
        if len(words) > limit:
            raise _LanguageLimit
    return words, False


def _candidate_trees(activities, spec):
    levels = {1: [ProcessTree("activity", a) for a in activities]}
    yield from levels[1]
    for size in range(2, spec.max_leaves + 1):
        level, seen = [], set()
        for split in range(1, size):
            for left, right in product(levels[split], levels[size - split]):
                for op in spec.operators:
                    children = (left, right)
                    if op in ("parallel", "xor"):
                        children = tuple(sorted(children, key=repr))
                    if op == "xor" and left == right:
                        continue
                    tree = ProcessTree(op, children=children)
                    if tree not in seen:
                        seen.add(tree)
                        level.append(tree)
                        yield tree
        levels[size] = level


def _local_support(tree, words, complete, traces, global_counts):
    agenda, alphabet = [tree], set()
    while agenda:
        node = agenda.pop()
        if node.operator == "activity":
            alphabet.add(node.activity)
        else:
            agenda.extend(node.children)
    lengths = sorted({len(word) for word in words})
    matched, used, observed, cases = [], Counter(), set(), set()
    for trace in traces:
        events = tuple(e for e in trace.events if e.activity in alphabet)
        acts = tuple(e.activity for e in events)
        # Maximize covered events, then non-overlapping executions, then prefer
        # earliest/shortest executions by stable tuple order. No event reuse.
        best = [(0, 0, ()) for _ in range(len(events) + 1)]
        for i in range(len(events) - 1, -1, -1):
            options = [best[i + 1]]
            for length in lengths:
                j = i + length
                if j <= len(events) and acts[i:j] in words:
                    n, covered, windows = best[j]
                    options.append((n + 1, covered + length, ((i, j),) + windows))
            best[i] = min(options, key=lambda x: (-x[1], -x[0], x[2]))
        for i, j in best[0][2]:
            selected = events[i:j]
            matched.append(
                LocalOccurrence(
                    trace.object_id, tuple(e.event_id for e in selected), acts[i:j]
                )
            )
            used.update(acts[i:j])
            observed.add(acts[i:j])
            cases.add(trace.object_id)
    ratios = [used[a] / global_counts[a] for a in alphabet if global_counts[a]]
    confidence = (
        len(ratios) / sum(1 / x for x in ratios) if ratios and all(ratios) else 0.0
    )
    prefixes = defaultdict(set)
    for word in words:
        for i, a in enumerate(word):
            prefixes[word[:i]].add(a)
        prefixes[word].add(None)
    choices = [
        len(prefixes[o.activities[:i]])
        for o in matched
        for i in range(len(o.activities) + 1)
    ]
    total_events = sum(global_counts.values())
    return LocalProcessModel(
        tree,
        len(matched),
        len(cases),
        confidence,
        sum(global_counts[a] for a in alphabet) / total_events if total_events else 0.0,
        len(observed) / len(words) if words else 0.0,
        len(choices) / sum(choices) if choices else 0.0,
        len(words),
        complete,
        tuple(matched),
    )


def discover_local_process_models(
    log: CaseLog | ComputationResult[TraceSet],
    spec: LocalProcessModelSpec = LocalProcessModelSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
):
    """Enumerate bounded sequence/XOR/parallel/loop candidates and exact windows.

    Window matches are contiguous after projection onto a model's activities.
    The optimum is maximum matched event count, then nonoverlapping occurrence
    count. This explicit profile does not claim reference alignment equivalence.
    """
    if not isinstance(spec, LocalProcessModelSpec):
        raise TypeError("spec must be LocalProcessModelSpec")
    parent = as_case_traces(log, trace_spec)
    operator = "pix.case_centric.discover_local_process_models"
    if parent.value is None:
        return _finish(parent, operator, spec, None)
    counts = Counter(e.activity for t in parent.value.traces for e in t.events)
    activities = (
        tuple(sorted(counts))
        if spec.selected_activities is None
        else spec.selected_activities
    )
    if not set(activities) <= set(counts):
        raise ValueError("selected activities must occur in the input")
    models, evaluated, skipped, complete = [], 0, 0, True
    for tree in _candidate_trees(activities, spec):
        if evaluated + skipped == spec.max_candidates:
            complete = False
            break
        try:
            language, language_complete = _language(
                tree,
                spec.max_word_length,
                spec.max_language_words,
                spec.max_language_expansions,
            )
        except _LanguageLimit:
            skipped += 1
            continue
        model = _local_support(
            tree, language, language_complete, parent.value.traces, counts
        )
        evaluated += 1
        if model.frequency >= spec.minimum_frequency:
            models.append(model)
    models.sort(
        key=lambda m: (
            -m.frequency,
            -m.confidence,
            -m.bounded_language_fit,
            repr(m.tree),
        )
    )
    payload = LocalProcessModelDiscovery(
        tuple(models[: spec.maximum_models]),
        evaluated,
        skipped,
        complete and not skipped,
        len(models),
    )
    issues = []
    if not complete:
        issues.append(
            ComputeIssue(
                "candidate_limit",
                "Candidate enumeration stopped at the explicit budget; ranking covers evaluated candidates only.",
            )
        )
    if skipped:
        issues.append(
            ComputeIssue(
                "language_limit",
                f"{skipped} candidate languages exceeded the word/expansion budget and were not scored.",
            )
        )
    return _finish(parent, operator, spec, payload, tuple(issues), partial=bool(issues))


RESULT_SCHEMAS = {
    "pix.case_centric.discover_dfg": (
        "case-dfg",
        RelationDiscoverySpec,
        CaseRelationGraph,
    ),
    "pix.case_centric.discover_efg": (
        "case-efg",
        RelationDiscoverySpec,
        CaseRelationGraph,
    ),
    "pix.case_centric.discover_footprints": (
        "case-footprints",
        FootprintSpec,
        FootprintModel,
    ),
    "pix.case_centric.discover_transition_system": (
        "case-transition-system",
        TransitionSystemSpec,
        TransitionSystem,
    ),
    "pix.case_centric.discover_prefix_tree": (
        "case-prefix-tree",
        PrefixTreeSpec,
        TransitionSystem,
    ),
    "pix.case_centric.discover_batches": (
        "case-batches",
        BatchDiscoverySpec,
        BatchDiscovery,
    ),
    "pix.case_centric.discover_local_process_models": (
        "case-local-process-models",
        LocalProcessModelSpec,
        LocalProcessModelDiscovery,
    ),
}

__all__ = [
    "RelationDiscoverySpec",
    "RelationEdge",
    "CaseRelationGraph",
    "FootprintSpec",
    "FootprintModel",
    "TransitionSystemSpec",
    "StateNode",
    "StateEdge",
    "TransitionSystem",
    "PrefixTreeSpec",
    "BatchDiscoverySpec",
    "BatchInterval",
    "EventBatch",
    "BatchDiscovery",
    "LocalProcessModelSpec",
    "LocalOccurrence",
    "LocalProcessModel",
    "LocalProcessModelDiscovery",
    "discover_dfg",
    "discover_efg",
    "discover_footprints",
    "discover_transition_system",
    "discover_prefix_tree",
    "discover_batches",
    "discover_local_process_models",
]
