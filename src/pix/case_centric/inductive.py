"""Native frequency-aware inductive discovery with explicit PIX profiles.

These profiles share XOR, plain-sequence, parallel and do/redo cut kernels with
PIX's existing IM implementation. They are not aliases for a PM4Py release:
optional-block strict-sequence merging is not performed. ``imf`` preserves case
multiplicities, tries original cuts before a filtered-DFG retry, and projects
the original weighted traces at the selected cut. ``imd`` recurses on graphs,
never on invented traces. Filtering is not a promise that the original log fits.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _result
from pix.compute.discovery import (
    _components,
    _im_loop_groups,
    _im_parallel_groups,
    _node,
    _sequence_groups,
)
from pix.contracts.analysis import (
    DirectlyFollowsGraph,
    ObjectTrace,
    TraceEvent,
    TraceSet,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

_PROFILES = {
    "im": "pix.im.weighted.v1",
    "imf": "pix.imf.filtered_dfg.v1",
    "imd": "pix.imd.dfg.v1",
}


@dataclass(frozen=True, slots=True)
class InductiveSpec:
    """Select a documented profile, not an upstream release-equivalence claim.

    Noise filtering is available only for ``imf``. The named ``flower`` policy
    admits all finite strings (including epsilon) after other fallthroughs fail;
    ``unavailable`` instead returns no model. Limits never trigger a flower.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    variant: Literal["im", "imf", "imd"] = "im"
    noise_threshold: float = 0.0
    fallback: Literal["flower", "unavailable"] = "flower"
    max_depth: int = 128
    max_nodes: int = 20000
    trace_spec: CaseTraceSpec = CaseTraceSpec()

    def __post_init__(self) -> None:
        if self.variant not in _PROFILES:
            raise ValueError("variant must be im, imf or imd")
        if isinstance(self.noise_threshold, bool) or not isinstance(
            self.noise_threshold, (int, float)
        ):
            raise TypeError("noise_threshold must be a finite number")
        if not isfinite(self.noise_threshold) or not 0 <= self.noise_threshold <= 1:
            raise ValueError("noise_threshold must be between zero and one")
        if self.variant != "imf" and self.noise_threshold:
            raise ValueError("noise filtering is defined only for imf")
        object.__setattr__(self, "noise_threshold", float(self.noise_threshold))
        if self.fallback not in ("flower", "unavailable"):
            raise ValueError("fallback must be flower or unavailable")
        for name, maximum in (("max_depth", 128), ("max_nodes", 1000000)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if not 1 <= value <= maximum:
                raise ValueError(f"{name} must be between 1 and {maximum}")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


_Trace = tuple[str, ...]
_Log = Counter[_Trace]


@dataclass
class _Graph:
    alphabet: set[str]
    edges: Counter[tuple[str, str]]
    starts: Counter[str]
    ends: Counter[str]
    skip: bool = False


def _from_log(log: _Log) -> _Graph:
    edges: Counter[tuple[str, str]] = Counter()
    starts: Counter[str] = Counter()
    ends: Counter[str] = Counter()
    alphabet: set[str] = set()
    for trace, count in log.items():
        alphabet.update(trace)
        if trace:
            starts[trace[0]] += count
            ends[trace[-1]] += count
            for edge in zip(trace, trace[1:]):
                edges[edge] += count
    return _Graph(alphabet, edges, starts, ends, bool(log.get(())))


def _cut(graph: _Graph) -> tuple[str, tuple[set[str], ...]] | None:
    alphabet, edges = graph.alphabet, set(graph.edges)
    xor = tuple(_components(alphabet, lambda a, b: (a, b) in edges or (b, a) in edges))
    if len(xor) > 1:
        return "xor", xor
    sequence = tuple(_sequence_groups(alphabet, edges))
    if len(sequence) > 1:
        return "sequence", sequence
    parallel = _im_parallel_groups(alphabet, edges, set(graph.starts), set(graph.ends))
    if len(parallel) > 1:
        return "parallel", parallel
    loop = _im_loop_groups(alphabet, edges, set(graph.starts), set(graph.ends))
    if loop:
        # Mine one redo alphabet; its internal XOR is itself discovered.
        return "loop", (loop[0], set().union(*loop[1:]))
    return None


def _projection(log: _Log, group: set[str]) -> _Log:
    result: _Log = Counter()
    for trace, count in log.items():
        result[tuple(a for a in trace if a in group)] += count
    return result


def _split_log(
    log: _Log, operator: str, groups: tuple[set[str], ...]
) -> tuple[_Log, ...]:
    parts: tuple[_Log, ...] = tuple(Counter() for _ in groups)
    for trace, count in log.items():
        if operator == "xor":
            # A filtered graph may admit a cut contradicted by the input trace.
            # Assign to maximum retained event count, with lexical group ties.
            selected = max(
                range(len(groups)),
                key=lambda i: (sum(a in groups[i] for a in trace), -i),
            )
            parts[selected][tuple(a for a in trace if a in groups[selected])] += count
        elif operator == "sequence":
            begin = 0
            previous: set[str] = set()
            for index, group in enumerate(groups):
                # Earliest minimum edit cost boundary: retain current-group
                # events, penalize future groups, ignore already assigned ones.
                score = best = 0
                stop = begin
                for position in range(begin, len(trace)):
                    if trace[position] in group:
                        score -= 1
                    elif trace[position] not in previous:
                        score += 1
                    if score < best:
                        best, stop = score, position + 1
                parts[index][tuple(a for a in trace[begin:stop] if a in group)] += count
                begin = stop
                previous.update(group)
        elif operator == "parallel":
            for part, group in zip(parts, groups):
                part[tuple(a for a in trace if a in group)] += count
        else:
            begin = 0
            if not trace:
                parts[0][()] += count
                continue
            for position in range(1, len(trace) + 1):
                if position == len(trace) or (trace[position] in groups[0]) != (
                    trace[begin] in groups[0]
                ):
                    index = 0 if trace[begin] in groups[0] else 1
                    parts[index][trace[begin:position]] += count
                    begin = position
            if trace[0] not in groups[0] or trace[-1] not in groups[0]:
                parts[0][()] += count
    return parts


def _split_graph(
    graph: _Graph, operator: str, groups: tuple[set[str], ...]
) -> tuple[_Graph, ...]:
    membership = {a: i for i, group in enumerate(groups) for a in group}
    result = []
    for index, group in enumerate(groups):
        edges = Counter(
            {edge: count for edge, count in graph.edges.items() if set(edge) <= group}
        )
        starts = Counter({a: n for a, n in graph.starts.items() if a in group})
        ends = Counter({a: n for a, n in graph.ends.items() if a in group})
        skip = False
        if operator in ("sequence", "loop"):
            for (source, target), count in graph.edges.items():
                if source not in group and target in group:
                    starts[target] += count
                if source in group and target not in group:
                    ends[source] += count
            if operator == "sequence":
                skip = (
                    any(membership[a] > index for a in graph.starts)
                    or any(membership[a] < index for a in graph.ends)
                    or any(
                        membership[a] < index < membership[b] for a, b in graph.edges
                    )
                )
            elif index == 1:
                # A body end -> body start edge witnesses an empty redo.
                skip = any(
                    a in graph.ends and b in graph.starts for a, b in graph.edges
                )
                # Redo boundary frequencies derive from crossing arcs, not
                # activity labels invented as unit-frequency start events.
        result.append(_Graph(set(group), edges, starts, ends, skip))
    return tuple(result)


class _Boundary(Exception):
    def __init__(self, code: str, message: str, path: tuple[str, ...]):
        self.issue = ComputeIssue(code, message, path)


def _check_tree_bounds(tree: ProcessTree, spec: InductiveSpec) -> None:
    """Fallthroughs can emit several nodes in one recursive subproblem."""
    pending = [(tree, 0)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if depth >= spec.max_depth or count > spec.max_nodes:
            raise _Boundary(
                "inductive_limit",
                "Discovered tree exceeds explicit node/depth limits; no model returned",
                (),
            )
        pending.extend((child, depth + 1) for child in node.children)


class _Miner:
    def __init__(self, spec: InductiveSpec, issues: list[ComputeIssue]):
        self.spec, self.issues, self.nodes = spec, issues, 0

    def visit(self, path: tuple[str, ...]) -> None:
        self.nodes += 1
        if len(path) >= self.spec.max_depth or self.nodes > self.spec.max_nodes:
            raise _Boundary(
                "inductive_limit",
                "Explicit recursive depth/node limit exceeded; no model returned",
                path,
            )

    def flower(self, alphabet: set[str], path: tuple[str, ...]) -> ProcessTree:
        if self.spec.fallback == "unavailable":
            raise _Boundary(
                "inductive_no_cut",
                "No supported cut/fallthrough and flower fallback is disabled",
                path,
            )
        self.issues.append(
            ComputeIssue(
                "inductive_flower",
                "Named flower fallback admits every finite string over the subtree alphabet, including epsilon",
                path,
            )
        )
        return _node(
            "loop",
            (
                ProcessTree("tau"),
                _node(
                    "xor", tuple(ProcessTree("activity", a) for a in sorted(alphabet))
                ),
            ),
        )

    def filter(self, graph: _Graph, path: tuple[str, ...]) -> _Graph:
        threshold = self.spec.noise_threshold
        outgoing = dict(graph.ends)
        for (source, _), count in graph.edges.items():
            outgoing[source] = max(outgoing.get(source, 0), count)
        edges = Counter(
            {
                edge: count
                for edge, count in graph.edges.items()
                if count > threshold * outgoing[edge[0]]
            }
        )
        maximum_start = max(graph.starts.values(), default=0)
        starts = Counter(
            {
                a: count
                for a, count in graph.starts.items()
                if count >= threshold * maximum_start
            }
        )
        removed = tuple(
            (a, b, graph.edges[a, b]) for a, b in sorted(set(graph.edges) - set(edges))
        )
        removed_starts = tuple(
            (a, graph.starts[a]) for a in sorted(set(graph.starts) - set(starts))
        )
        if removed or removed_starts:
            self.issues.append(
                ComputeIssue(
                    "inductive_dfg_filter",
                    f"Removed edges {removed!r} and starts {removed_starts!r}; weighted source traces remain available for projection, not deleted as whole cases",
                    path,
                )
            )
        return _Graph(set(graph.alphabet), edges, starts, Counter(graph.ends))

    def log(self, log: _Log, path: tuple[str, ...] = ()) -> ProcessTree:
        self.visit(path)
        empty = log.get((), 0)
        nonempty = Counter({trace: n for trace, n in log.items() if trace and n})
        if not nonempty:
            return ProcessTree("tau")
        if empty:
            retain = (
                self.spec.variant != "imf"
                or empty > self.spec.noise_threshold * sum(log.values())
            )
            if retain:
                return _node(
                    "xor", (ProcessTree("tau"), self.log(nonempty, (*path, "nonempty")))
                )
            self.issues.append(
                ComputeIssue(
                    "inductive_empty_filter",
                    f"Excluded {empty} empty projected traces of {sum(log.values())}; equality at noise threshold is excluded",
                    path,
                )
            )
            log = nonempty
        graph = _from_log(log)
        if len(graph.alphabet) == 1 and all(len(trace) == 1 for trace in log):
            return ProcessTree("activity", next(iter(graph.alphabet)))
        cut = _cut(graph)
        if cut is None and self.spec.variant == "imf" and self.spec.noise_threshold:
            filtered = self.filter(graph, path)
            cut = _cut(filtered)
            if cut is not None:
                self.issues.append(
                    ComputeIssue(
                        "inductive_filtered_cut",
                        f"Selected {cut[0]} after DFG filtering; no fitness claim for the original population",
                        path,
                    )
                )
        if cut is not None:
            operator, groups = cut
            parts = _split_log(log, operator, groups)
            return _node(
                operator,
                tuple(
                    self.log(part, (*path, f"{operator}:{i}"))
                    for i, part in enumerate(parts)
                ),
            )
        for activity in sorted(graph.alphabet):
            if all(trace.count(activity) == 1 for trace in log):
                self.issues.append(
                    ComputeIssue(
                        "inductive_activity_once",
                        f"Activity {activity!r} occurs once in every projected trace",
                        path,
                    )
                )
                return _node(
                    "parallel",
                    (
                        ProcessTree("activity", activity),
                        self.log(
                            _projection(log, graph.alphabet - {activity}),
                            (*path, "activity_once"),
                        ),
                    ),
                )
        for activity in sorted(graph.alphabet):
            remaining = _projection(log, graph.alphabet - {activity})
            if () not in remaining and _cut(_from_log(remaining)) is not None:
                self.issues.append(
                    ComputeIssue(
                        "inductive_activity_concurrent",
                        f"Removing {activity!r} exposes a structural cut",
                        path,
                    )
                )
                return _node(
                    "parallel",
                    (
                        self.log(
                            _projection(log, {activity}), (*path, "concurrent:selected")
                        ),
                        self.log(remaining, (*path, "concurrent:rest")),
                    ),
                )
        for strict in (True, False):
            parts: _Log = Counter()
            split = False
            for trace, count in log.items():
                begin = 0
                for position in range(1, len(trace)):
                    if trace[position] in graph.starts and (
                        not strict or trace[position - 1] in graph.ends
                    ):
                        parts[trace[begin:position]] += count
                        begin, split = position, True
                parts[trace[begin:]] += count
            if split:
                self.issues.append(
                    ComputeIssue(
                        "inductive_tau_loop",
                        "Applied strict tau-loop"
                        if strict
                        else "Applied general tau-loop",
                        path,
                    )
                )
                return _node(
                    "loop", (self.log(parts, (*path, "tau_loop")), ProcessTree("tau"))
                )
        return self.flower(graph.alphabet, path)

    def graph(self, graph: _Graph, path: tuple[str, ...] = ()) -> ProcessTree:
        self.visit(path)
        if not graph.alphabet:
            return ProcessTree("tau")
        if graph.skip:
            nonempty = _Graph(graph.alphabet, graph.edges, graph.starts, graph.ends)
            return _node(
                "xor", (ProcessTree("tau"), self.graph(nonempty, (*path, "nonempty")))
            )
        if len(graph.alphabet) == 1 and not graph.edges:
            return ProcessTree("activity", next(iter(graph.alphabet)))
        cut = _cut(graph)
        if cut:
            operator, groups = cut
            return _node(
                operator,
                tuple(
                    self.graph(part, (*path, f"{operator}:{i}"))
                    for i, part in enumerate(_split_graph(graph, operator, groups))
                ),
            )
        return self.flower(graph.alphabet, path)


def _envelope(
    parent: ComputationResult,
    spec: InductiveSpec,
    status: ComputeStatus,
    value=None,
    issues=(),
):
    return _result(
        "pix.case_centric.discover_inductive",
        None,
        spec,
        status,
        value,
        tuple(issues),
        source_digest=parent.source_digest,
        parent_computation_ids=(parent.computation_id,)
        if parent.computation_id
        else (),
    )


def discover_inductive(
    data: CaseInput, spec: InductiveSpec = InductiveSpec()
) -> ComputationResult[ProcessTree]:
    """Mine case traces with native weighted IM, filtered IMf, or graph IMd.

    Case order/classifier selection is delegated to the explicit trace spec.
    Empty population is unavailable; a population of empty cases mines tau.
    Every trace copy contributes its frequency throughout log recursion.
    """
    if not isinstance(spec, InductiveSpec):
        raise TypeError("spec must be InductiveSpec")
    parent = as_case_traces(data, spec.trace_spec)
    if parent.status is not ComputeStatus.COMPUTED:
        status = (
            ComputeStatus.INVALID_INPUT
            if parent.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE
        )
        return _envelope(
            parent,
            spec,
            status,
            issues=(
                *parent.issues,
                ComputeIssue(
                    "upstream_not_computed", "Complete case traces are required"
                ),
            ),
        )
    try:
        traces = parent.value
        if not isinstance(traces, TraceSet) or not isinstance(traces.traces, tuple):
            raise TypeError("expected immutable TraceSet")
        ids = set()
        log: _Log = Counter()
        for trace in traces.traces:
            if not isinstance(trace, ObjectTrace) or not isinstance(
                trace.events, tuple
            ):
                raise TypeError("expected immutable ObjectTrace")
            if (
                not isinstance(trace.object_id, str)
                or not trace.object_id.strip()
                or trace.object_id in ids
            ):
                raise ValueError("case identity must be nonempty and unique")
            if trace.object_type != traces.object_type:
                raise ValueError("trace type differs from TraceSet")
            ids.add(trace.object_id)
            for event in trace.events:
                if not isinstance(event, TraceEvent):
                    raise TypeError("expected TraceEvent")
                ProcessTree("activity", event.activity)
            log[tuple(event.activity for event in trace.events)] += 1
    except (ValueError, TypeError, AttributeError) as exc:
        return _envelope(
            parent,
            spec,
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_inductive_input", str(exc)),),
        )
    if not log:
        return _envelope(
            parent,
            spec,
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("empty_population", "No cases are available"),),
        )
    issues = [
        *parent.issues,
        ComputeIssue(
            "inductive_profile",
            f"Profile {_PROFILES[spec.variant]}; plain-sequence cuts, no pinned-release equivalence claim",
        ),
    ]
    miner = _Miner(spec, issues)
    try:
        tree = miner.graph(_from_log(log)) if spec.variant == "imd" else miner.log(log)
        _check_tree_bounds(tree, spec)
    except _Boundary as exc:
        return _envelope(
            parent, spec, ComputeStatus.UNAVAILABLE, issues=(*issues, exc.issue)
        )
    return _envelope(parent, spec, ComputeStatus.COMPUTED, tree, issues)


def discover_inductive_dfg(
    data: ComputationResult[DirectlyFollowsGraph],
    spec: InductiveSpec = InductiveSpec(variant="imd"),
) -> ComputationResult[ProcessTree]:
    """Mine a frequency DFG directly; empty-object evidence supplies skip state.

    This input cannot recover correlations that the original traces contained.
    Frequency counts must describe occurrences, not distinct source events.
    """
    if not isinstance(spec, InductiveSpec) or spec.variant != "imd":
        raise ValueError("direct DFG input requires an imd InductiveSpec")
    if not isinstance(data, ComputationResult):
        raise TypeError("data must be ComputationResult[DirectlyFollowsGraph]")
    if data.status is not ComputeStatus.COMPUTED:
        status = (
            ComputeStatus.INVALID_INPUT
            if data.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE
        )
        return _envelope(
            data,
            spec,
            status,
            issues=(
                *data.issues,
                ComputeIssue("upstream_not_computed", "Complete DFG required"),
            ),
        )
    try:
        value = data.value
        if not isinstance(value, DirectlyFollowsGraph):
            raise TypeError("expected DirectlyFollowsGraph")
        if (
            isinstance(value.object_count, bool)
            or not isinstance(value.object_count, int)
            or value.object_count < 0
        ):
            raise ValueError("object_count must be a nonnegative integer")
        alphabet = {item.activity for item in value.activities}
        if len(alphabet) != len(value.activities):
            raise ValueError("duplicate activity")
        for activity in alphabet:
            ProcessTree("activity", activity)
        occurrences = {}
        for item in value.activities:
            count = item.event_occurrence_count
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise ValueError("activity occurrence count must be a positive integer")
            occurrences[item.activity] = count
        edges: Counter[tuple[str, str]] = Counter()
        for edge in value.edges:
            pair = (edge.source_activity, edge.target_activity)
            if not set(pair) <= alphabet or pair in edges:
                raise ValueError("unknown endpoint or duplicate edge")
            if (
                isinstance(edge.occurrence_count, bool)
                or not isinstance(edge.occurrence_count, int)
                or edge.occurrence_count <= 0
            ):
                raise ValueError("edge count must be a positive integer")
            edges[pair] = edge.occurrence_count
        starts = Counter({item.activity: len(item.evidence) for item in value.starts})
        ends = Counter({item.activity: len(item.evidence) for item in value.ends})
        if len(starts) != len(value.starts) or len(ends) != len(value.ends):
            raise ValueError("duplicate start/end activity entry")
        if not set(starts) <= alphabet or not set(ends) <= alphabet:
            raise ValueError("unknown start/end activity")
        if alphabet and (
            not starts
            or not ends
            or any(n <= 0 for n in (*starts.values(), *ends.values()))
        ):
            raise ValueError("nonempty DFG needs observed start/end boundaries")
        boundaries = []
        for entries in (value.starts, value.ends):
            ids = set()
            for entry in entries:
                for witness in entry.evidence:
                    if (
                        not isinstance(witness.object_id, str)
                        or not witness.object_id.strip()
                        or witness.object_id in ids
                    ):
                        raise ValueError(
                            "boundary case identities must be nonempty and unique"
                        )
                    if (
                        not isinstance(witness.event_id, str)
                        or not witness.event_id.strip()
                    ):
                        raise ValueError("boundary event identity must be nonempty")
                    ids.add(witness.object_id)
            boundaries.append(ids)
        empty_ids = set()
        for identity in value.empty_object_ids:
            if (
                not isinstance(identity, str)
                or not identity.strip()
                or identity in empty_ids
            ):
                raise ValueError("empty case identities must be nonempty and unique")
            empty_ids.add(identity)
        if boundaries[0] != boundaries[1] or empty_ids & boundaries[0]:
            raise ValueError("start/end populations must agree and exclude empty cases")
        if len(boundaries[0]) + len(empty_ids) != value.object_count:
            raise ValueError(
                "boundary and empty evidence must cover the declared case population"
            )
        incoming = Counter()
        outgoing = Counter()
        for (source, target), count in edges.items():
            incoming[target] += count
            outgoing[source] += count
        for activity, count in occurrences.items():
            if (
                count != starts[activity] + incoming[activity]
                or count != ends[activity] + outgoing[activity]
            ):
                raise ValueError(
                    "DFG occurrence counts violate start/incoming or end/outgoing flow conservation"
                )
        if value.object_count <= 0:
            return _envelope(
                data,
                spec,
                ComputeStatus.UNAVAILABLE,
                issues=(ComputeIssue("empty_population", "DFG contains no cases"),),
            )
        graph = _Graph(alphabet, edges, starts, ends, bool(value.empty_object_ids))
    except (ValueError, TypeError, AttributeError) as exc:
        return _envelope(
            data,
            spec,
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("invalid_inductive_dfg", str(exc)),),
        )
    issues = [
        *data.issues,
        ComputeIssue(
            "inductive_profile",
            "Profile pix.imd.dfg.v1; graph-only correlations, plain sequence, observed crossing-arc boundary counts",
        ),
    ]
    try:
        tree = _Miner(spec, issues).graph(graph)
        _check_tree_bounds(tree, spec)
    except _Boundary as exc:
        return _envelope(
            data, spec, ComputeStatus.UNAVAILABLE, issues=(*issues, exc.issue)
        )
    return _envelope(data, spec, ComputeStatus.COMPUTED, tree, issues)


RESULT_SCHEMAS = {
    "pix.case_centric.discover_inductive": ("process_tree", InductiveSpec, ProcessTree)
}

__all__ = ("InductiveSpec", "discover_inductive", "discover_inductive_dfg")
