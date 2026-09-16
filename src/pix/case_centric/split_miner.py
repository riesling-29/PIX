"""Native, explicitly bounded Split-Miner-style BPMN discovery.

``classic_bounded`` uses frequency imbalance, excluding observed ABA loops,
and a maximum-bottleneck path backbone. ``interval_bounded`` derives the
cover relation of explicit start/end intervals and positive-duration overlap;
its frequency percentile is fixed at one. Neither profile calls another
miner or an upstream package.

These are PIX profiles, not full Classic/SM2 compatibility. In particular:
* frequency quantiles use the nearest-rank definition;
* concurrency pruning preserves global source/sink reachability;
* local XOR/AND hierarchies are exact cograph decompositions, and prime
  relations are reported rather than force-merged;
* joins use the local predecessor relation, not RPST/SESE OR-join analysis;
* intervals must already be paired; no lifecycle pairing or SM2 OR heuristic
  is performed. Same-label simultaneous instances are unsupported.

The returned model is a BPMN control-flow graph. ``computed`` means the
declared profile finished, not soundness, upstream parity, or perfect fitness.
No BPMN DI/layout, inclusive/event gateways, conditions or message flows are
inferred. Short loops are retained explicitly as graph cycles.

Algorithm family: Augusto et al., Split Miner,
https://doi.org/10.1007/s10115-018-1214-x . The pinned PM4Py 2.7.23.8
source was inspected for scope; this implementation is independently written.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import timezone
from heapq import heappop, heappush
from itertools import combinations
from math import ceil, isfinite
from typing import ClassVar, Literal
from xml.etree.ElementTree import Element, SubElement, tostring

from pix.case_centric._input import as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseLog


@dataclass(frozen=True, slots=True)
class SplitMinerSpec:
    profile: Literal["classic_bounded", "interval_bounded"] = "classic_bounded"
    concurrency_epsilon: float = 0.1
    frequency_percentile: float | None = None
    start_timestamp_key: str = "start_timestamp"
    max_activities: int = 512
    max_interval_comparisons: int = 1_000_000
    max_connectivity_edge_visits: int = 2_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.profile not in ("classic_bounded", "interval_bounded"):
            raise ValueError("profile must be classic_bounded or interval_bounded")
        for name in ("concurrency_epsilon", "frequency_percentile"):
            value = getattr(self, name)
            if value is None and name == "frequency_percentile":
                continue
            if (
                type(value) not in (int, float)
                or not isfinite(value)
                or not 0 <= value <= 1
            ):
                raise ValueError(f"{name} must be finite and in [0, 1]")
            object.__setattr__(self, name, float(value))
        if self.profile == "interval_bounded" and self.frequency_percentile not in (
            None,
            1,
        ):
            raise ValueError("interval_bounded fixes frequency_percentile to 1")
        if self.profile == "interval_bounded" and self.concurrency_epsilon != 0.1:
            raise ValueError("concurrency_epsilon is a classic_bounded parameter")
        if (
            not isinstance(self.start_timestamp_key, str)
            or not self.start_timestamp_key.strip()
        ):
            raise ValueError("start_timestamp_key must be nonblank text")
        for name in (
            "max_activities",
            "max_interval_comparisons",
            "max_connectivity_edge_visits",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class SplitBPMNNode:
    id: str
    kind: Literal[
        "start_event", "end_event", "task", "exclusive_gateway", "parallel_gateway"
    ]
    activity: str | None = None
    direction: Literal["split", "join"] | None = None

    def __post_init__(self):
        _xml_id(self.id)
        kinds = {
            "start_event",
            "end_event",
            "task",
            "exclusive_gateway",
            "parallel_gateway",
        }
        if self.kind not in kinds:
            raise ValueError("unsupported BPMN node kind")
        if self.kind == "task":
            if not isinstance(self.activity, str) or not self.activity.strip():
                raise ValueError("BPMN tasks require nonblank activity labels")
        elif self.activity is not None:
            raise ValueError("only tasks may carry activity labels")
        gateway = self.kind.endswith("_gateway")
        if gateway and self.direction not in ("split", "join"):
            raise ValueError("gateways require a split/join direction")
        if not gateway and self.direction is not None:
            raise ValueError("only gateways may carry a split/join direction")


@dataclass(frozen=True, slots=True)
class SplitBPMNFlow:
    id: str
    source: str
    target: str

    def __post_init__(self):
        for value in (self.id, self.source, self.target):
            _xml_id(value)


@dataclass(frozen=True, slots=True)
class SplitBPMN:
    nodes: tuple[SplitBPMNNode, ...]
    flows: tuple[SplitBPMNFlow, ...]
    start_id: str
    end_id: str

    def __post_init__(self):
        if not isinstance(self.nodes, tuple) or not all(
            isinstance(node, SplitBPMNNode) for node in self.nodes
        ):
            raise TypeError("nodes must be a tuple of SplitBPMNNode")
        if not isinstance(self.flows, tuple) or not all(
            isinstance(flow, SplitBPMNFlow) for flow in self.flows
        ):
            raise TypeError("flows must be a tuple of SplitBPMNFlow")
        all_ids = [item.id for item in (*self.nodes, *self.flows)]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("node and flow IDs must be globally unique")
        by_id = {node.id: node for node in self.nodes}
        if self.start_id not in by_id or by_id[self.start_id].kind != "start_event":
            raise ValueError("start_id must identify a start event")
        if self.end_id not in by_id or by_id[self.end_id].kind != "end_event":
            raise ValueError("end_id must identify an end event")
        if (
            sum(n.kind == "start_event" for n in self.nodes) != 1
            or sum(n.kind == "end_event" for n in self.nodes) != 1
        ):
            raise ValueError(
                "this BPMN profile requires exactly one start and end event"
            )
        if any(
            flow.source not in by_id or flow.target not in by_id for flow in self.flows
        ):
            raise ValueError("flow endpoints must exist")
        incoming, outgoing = (
            Counter(f.target for f in self.flows),
            Counter(f.source for f in self.flows),
        )
        for node in self.nodes:
            degree = (incoming[node.id], outgoing[node.id])
            if node.kind == "start_event" and degree != (0, 1):
                raise ValueError(
                    "start event requires zero incoming and one outgoing flow"
                )
            if node.kind == "end_event" and degree != (1, 0):
                raise ValueError(
                    "end event requires one incoming and zero outgoing flows"
                )
            if node.kind == "task" and degree != (1, 1):
                raise ValueError(
                    "this BPMN profile gives each task one incoming/outgoing flow"
                )
            if node.direction == "split" and not (degree[0] == 1 and degree[1] >= 2):
                raise ValueError(
                    "split gateways require one incoming and at least two outgoing flows"
                )
            if node.direction == "join" and not (degree[0] >= 2 and degree[1] == 1):
                raise ValueError(
                    "join gateways require at least two incoming and one outgoing flow"
                )
        edges = {(flow.source, flow.target) for flow in self.flows}
        if len(edges) != len(self.flows):
            raise ValueError("duplicate sequence-flow endpoint pairs are unsupported")
        if not _connected(set(by_id), edges, self.start_id, self.end_id):
            raise ValueError("every node must lie on a start-to-end path")


def _xml_id(value):
    if (
        not isinstance(value, str)
        or re.fullmatch(r"[^\W\d][\w.-]*", value, re.UNICODE) is None
    ):
        raise ValueError("BPMN identifiers must be valid unqualified XML names")


@dataclass(frozen=True, slots=True)
class SplitEdge:
    """Endpoints are collision-safe task/event IDs, never synthetic labels."""

    source: str
    target: str
    count: int
    retained: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SplitConcurrency:
    left: str
    right: str
    forward_count: int
    reverse_count: int
    overlap_count: int
    selected: bool
    reason: str


@dataclass(frozen=True, slots=True)
class SplitDiscovery:
    model: SplitBPMN | None
    profile: str
    activities: tuple[tuple[str, str], ...]
    trace_count: int
    empty_trace_count: int
    frequency_threshold: int
    edges: tuple[SplitEdge, ...]
    concurrency: tuple[SplitConcurrency, ...]
    short_loops: tuple[tuple[str, ...], ...]
    unresolved_gateway_nodes: tuple[str, ...]
    interval_comparisons: int
    connectivity_edge_visits: int
    soundness: str = "not_checked"
    reference_equivalence: str = "partial_profile"


def _components(nodes, relation):
    remaining = set(nodes)
    groups = []
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        stack, group = [first], {first}
        while stack:
            current = stack.pop()
            linked = {
                n for n in remaining if (min(current, n), max(current, n)) in relation
            }
            remaining.difference_update(linked)
            stack.extend(sorted(linked, reverse=True))
            group.update(linked)
        groups.append(tuple(sorted(group)))
    return tuple(groups)


def _gateway_tree(nodes, parallel):
    """Unique relation decomposition up to associative gateway flattening.

    Leaf=("leaf", node). Non-leaf=("xor"|"and", children). A connected
    relation with connected complement is prime and has no exact XOR/AND tree.
    """
    nodes = tuple(sorted(nodes))
    if not nodes:
        raise ValueError("gateway decomposition needs at least one neighbour")
    agenda, pending, completed = [(nodes, False)], {}, {}
    while agenda:
        group, assembling = agenda.pop()
        if assembling:
            kind, components = pending.pop(group)
            completed[group] = (
                kind,
                tuple(completed.pop(child) for child in components),
            )
            continue
        if len(group) == 1:
            completed[group] = ("leaf", group[0])
            continue
        components = _components(group, parallel)
        kind = "xor"
        if len(components) == 1:
            complement = {
                pair for pair in combinations(group, 2) if pair not in parallel
            }
            components = _components(group, complement)
            kind = "and"
        if len(components) == 1:
            return None
        pending[group] = kind, components
        agenda.append((group, True))
        agenda.extend((child, False) for child in reversed(components))
    return completed[nodes]


def _reachable(seed, edges, reverse=False):
    adjacency = {}
    for left, right in edges:
        a, b = (right, left) if reverse else (left, right)
        adjacency.setdefault(a, set()).add(b)
    seen, stack = {seed}, [seed]
    while stack:
        for node in adjacency.get(stack.pop(), ()):
            if node not in seen:
                seen.add(node)
                stack.append(node)
    return seen


def _connected(nodes, edges, source, sink):
    return _reachable(source, edges) == nodes and _reachable(sink, edges, True) == nodes


def _backbone(weights, seed, reverse=False):
    """Dijkstra's max-min algebra; settled predecessors form an acyclic tree."""
    adjacency = {}
    for (left, right), weight in sorted(weights.items()):
        a, b = (right, left) if reverse else (left, right)
        adjacency.setdefault(a, []).append((b, weight, (left, right)))
    capacity = {seed: sum(weights.values()) + 1}
    agenda, settled, parents = [(-capacity[seed], seed)], set(), {}
    while agenda:
        negative_capacity, node = heappop(agenda)
        if node in settled:
            continue
        settled.add(node)
        for other, weight, edge in adjacency.get(node, ()):
            candidate = min(-negative_capacity, weight)
            if other not in settled and candidate > capacity.get(other, 0):
                capacity[other] = candidate
                parents[other] = edge
                heappush(agenda, (-candidate, other))
    return set(parents.values())


def _frequency_filter(weights, nodes, source, sink, percentile, protected):
    best = set()
    for node in sorted(nodes):
        incoming = [edge for edge in weights if edge[1] == node and edge[0] != node]
        outgoing = [edge for edge in weights if edge[0] == node and edge[1] != node]
        for choices in (incoming, outgoing):
            if choices:
                best.add(max(choices, key=lambda edge: (weights[edge], edge)))
    ranked = sorted(weights[edge] for edge in best)
    threshold = ranked[max(0, ceil(len(ranked) * percentile) - 1)] if ranked else 0
    backbone = _backbone(weights, source) | _backbone(weights, sink, True)
    kept = (
        {edge for edge, count in weights.items() if count >= threshold}
        | backbone
        | protected
    )
    return kept, threshold, backbone


def _make_bpmn(labels, kept, concurrent, source, sink):
    identifiers = {i: f"split_task_{i}" for i in range(len(labels))}
    identifiers.update({source: "split_start", sink: "split_end"})
    nodes = [
        SplitBPMNNode(identifiers[i], "task", label) for i, label in enumerate(labels)
    ]
    nodes.extend(
        (
            SplitBPMNNode(identifiers[source], "start_event"),
            SplitBPMNNode(identifiers[sink], "end_event"),
        )
    )
    links, outgoing_ports, incoming_ports, unresolved = set(), {}, {}, []
    for center in sorted(identifiers):
        for direction, neighbours in (
            ("split", sorted(b for a, b in kept if a == center)),
            ("join", sorted(a for a, b in kept if b == center)),
        ):
            ports = {}
            if len(neighbours) <= 1:
                ports = {n: identifiers[center] for n in neighbours}
            else:
                tree = _gateway_tree(neighbours, concurrent)
                if tree is None:
                    unresolved.append(f"{identifiers[center]}:{direction}")
                    continue
                serial, render_stack = 0, [(tree, identifiers[center])]
                while render_stack:
                    item, parent = render_stack.pop()
                    kind, content = item
                    if kind == "leaf":
                        ports[content] = parent
                        continue
                    gate = f"split_gateway_{direction}_{center}_{serial}"
                    serial += 1
                    nodes.append(
                        SplitBPMNNode(
                            gate,
                            "exclusive_gateway"
                            if kind == "xor"
                            else "parallel_gateway",
                            direction=direction,
                        )
                    )
                    links.add(
                        (parent, gate) if direction == "split" else (gate, parent)
                    )
                    render_stack.extend((child, gate) for child in reversed(content))
            (outgoing_ports if direction == "split" else incoming_ports)[center] = ports
    if unresolved:
        return None, tuple(unresolved)
    for a, b in kept:
        links.add((outgoing_ports[a][b], incoming_ports[b][a]))
    flows = tuple(
        SplitBPMNFlow(f"split_flow_{i}", a, b) for i, (a, b) in enumerate(sorted(links))
    )
    return SplitBPMN(
        tuple(sorted(nodes, key=lambda node: node.id)),
        flows,
        identifiers[source],
        identifiers[sink],
    ), ()


class _IntervalLimit(Exception):
    pass


class _UnsupportedInterval(Exception):
    pass


def _interval_relation(log, traces, numbers, source, sink, spec, trace_spec):
    weights, overlaps = Counter(), Counter()
    loops_one, loops_two = set(), set()
    examined = 0
    raw_events = {event.id: event for trace in log.traces for event in trace.events}
    for trace in traces:
        observations = []
        for event in trace.events:
            raw = raw_events[event.event_id]
            start, end = (
                log.attribute(raw, spec.start_timestamp_key),
                log.attribute(raw, trace_spec.timestamp_key),
            )
            if any(
                attr is None or attr.type != "date" or attr.value.utcoffset() is None
                for attr in (start, end)
            ):
                raise ValueError(
                    "interval_bounded requires explicit timezone-aware start/end attributes"
                )
            start_time, end_time = (
                start.value.astimezone(timezone.utc),
                end.value.astimezone(timezone.utc),
            )
            if start_time > end_time:
                raise ValueError("observed interval starts after it ends")
            observations.append((start_time, end_time, numbers[event.activity]))
        if not observations:
            weights[source, sink] += 1
            continue
        precedence = set()
        for i, (start, end, activity) in enumerate(observations):
            for j, (other_start, other_end, other) in enumerate(observations):
                if i == j:
                    continue
                examined += 1
                if examined > spec.max_interval_comparisons:
                    raise _IntervalLimit
                if end <= other_start and (
                    end < other_end or start < other_start or i < j
                ):
                    precedence.add((i, j))
                if i < j and max(start, other_start) < min(end, other_end):
                    if activity == other:
                        raise _UnsupportedInterval(
                            "same-activity overlapping instances require a different model profile"
                        )
                    overlaps[min(activity, other), max(activity, other)] += 1
        before = {i: set() for i in range(len(observations))}
        after = {i: set() for i in range(len(observations))}
        for i, j in precedence:
            after[i].add(j)
            before[j].add(i)
        for i, (_, _, activity) in enumerate(observations):
            if not before[i]:
                weights[source, activity] += 1
            if not after[i]:
                weights[activity, sink] += 1
        cover_after = {i: set() for i in range(len(observations))}
        for i, j in sorted(precedence):
            # Charge the actual candidate tests; do not hide a cubic phase
            # behind the quadratic pair counter.
            middle = False
            for candidate in sorted(after[i]):
                examined += 1
                if examined > spec.max_interval_comparisons:
                    raise _IntervalLimit
                if candidate in before[j]:
                    middle = True
                    break
            if not middle:
                cover_after[i].add(j)
                weights[observations[i][2], observations[j][2]] += 1
                if observations[i][2] == observations[j][2]:
                    loops_one.add(observations[i][2])
        for i, successors in cover_after.items():
            for j in successors:
                for k in cover_after[j]:
                    examined += 1
                    if examined > spec.max_interval_comparisons:
                        raise _IntervalLimit
                    a, b, c = observations[i][2], observations[j][2], observations[k][2]
                    if a == c and a != b:
                        loops_two.add(tuple(sorted((a, b))))
    return weights, overlaps, examined, loops_one, loops_two


def discover_split_miner(
    log: CaseLog | ComputationResult[TraceSet],
    spec: SplitMinerSpec = SplitMinerSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[SplitDiscovery]:
    """Discover an independently defined bounded BPMN profile with witnesses."""
    if not isinstance(spec, SplitMinerSpec):
        raise TypeError("spec must be SplitMinerSpec")
    parent = as_case_traces(log, trace_spec)
    operator = "pix.case_centric.discover_split_miner"
    issues = list(parent.issues)

    def finish(status, value=None, code=None, message=None):
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            status,
            value,
            tuple(issues) + ((ComputeIssue(code, message),) if code else ()),
            parent_computation_ids=(parent.computation_id,)
            if parent.computation_id
            else (),
        )

    if parent.value is None:
        return finish(parent.status)
    if spec.profile == "interval_bounded" and not isinstance(log, CaseLog):
        return finish(
            ComputeStatus.UNAVAILABLE,
            code="interval_source_required",
            message="Interval discovery needs the original CaseLog attributes",
        )
    traces = tuple(
        tuple(event.activity for event in trace.events) for trace in parent.value.traces
    )
    if not traces:
        return finish(
            ComputeStatus.UNAVAILABLE, code="empty_log", message="No observed cases"
        )
    if any(not isinstance(a, str) or not a.strip() for trace in traces for a in trace):
        return finish(
            ComputeStatus.INVALID_INPUT,
            code="invalid_activity",
            message="Activity labels must be nonblank strings",
        )
    labels = tuple(sorted({a for trace in traces for a in trace}))
    if len(labels) > spec.max_activities:
        return finish(
            ComputeStatus.UNAVAILABLE,
            code="activity_limit",
            message="Activity limit exceeded; no model returned",
        )
    numbers = {label: i for i, label in enumerate(labels)}
    source, sink = len(labels), len(labels) + 1
    nodes = set(range(len(labels) + 2))
    encoded = tuple(tuple(numbers[a] for a in trace) for trace in traces)
    loops_one = {a for trace in encoded for a, b in zip(trace, trace[1:]) if a == b}
    loops_two = {
        tuple(sorted((a, b)))
        for trace in encoded
        for a, b, c in zip(trace, trace[1:], trace[2:])
        if a == c and a != b
    }
    weights, overlaps, examined = Counter(), Counter(), 0
    if spec.profile == "interval_bounded":
        try:
            weights, overlaps, examined, loops_one, loops_two = _interval_relation(
                log, parent.value.traces, numbers, source, sink, spec, trace_spec
            )
        except _IntervalLimit:
            return finish(
                ComputeStatus.UNAVAILABLE,
                code="interval_comparison_limit",
                message="Interval comparison budget exceeded; no truncated graph returned",
            )
        except ValueError as exc:
            return finish(
                ComputeStatus.INVALID_INPUT, code="invalid_interval", message=str(exc)
            )
        except _UnsupportedInterval as exc:
            return finish(
                ComputeStatus.UNAVAILABLE,
                code="unsupported_interval_pattern",
                message=str(exc),
            )
    else:
        for trace in encoded:
            augmented = (source, *trace, sink)
            weights.update(zip(augmented, augmented[1:]))
    original = dict(weights)
    concurrent, candidates, connectivity_visits = set(), [], 0
    for a, b in combinations(range(len(labels)), 2):
        forward, reverse, overlap = (
            weights.get((a, b), 0),
            weights.get((b, a), 0),
            overlaps.get((a, b), 0),
        )
        if spec.profile == "interval_bounded":
            if overlap:
                # Aggregate causal and concurrent evidence can conflict when
                # activities repeat or have different roles across cases.
                selected = not forward and not reverse
                if selected:
                    concurrent.add((a, b))
                candidates.append(
                    (
                        a,
                        b,
                        forward,
                        reverse,
                        overlap,
                        selected,
                        "observed_overlap"
                        if selected
                        else "mixed_causal_overlap_evidence",
                    )
                )
            continue
        if not forward or not reverse:
            continue
        if (a, b) in loops_two:
            candidates.append(
                (a, b, forward, reverse, 0, False, "observed_length_two_loop")
            )
            continue
        balanced = (
            abs(forward - reverse) / (forward + reverse) < spec.concurrency_epsilon
        )
        drop = (
            {(a, b), (b, a)}
            if balanced
            else ({(a, b)} if forward < reverse else {(b, a)})
        )
        # Two adjacency constructions and two reachability traversals inspect
        # at most four times the candidate edge count. Charge this upper bound
        # before constructing/traversing the candidate graph.
        connectivity_visits += 4 * (len(weights) - len(drop))
        if connectivity_visits > spec.max_connectivity_edge_visits:
            return finish(
                ComputeStatus.UNAVAILABLE,
                code="connectivity_budget",
                message="Concurrency connectivity budget exceeded; no truncated graph returned",
            )
        if _connected(nodes, set(weights) - drop, source, sink):
            for edge in drop:
                del weights[edge]
            if balanced:
                concurrent.add((a, b))
            reason = (
                "balanced_bidirectional" if balanced else "weaker_direction_removed"
            )
        else:
            reason = "global_connectivity_guard"
        candidates.append((a, b, forward, reverse, 0, (a, b) in concurrent, reason))
    if any(row[-1] == "mixed_causal_overlap_evidence" for row in candidates):
        issues.append(
            ComputeIssue(
                "mixed_interval_relation",
                "Some labels have both causal and overlap evidence; those pairs are not classified as parallel",
            )
        )
    protected = {
        edge
        for edge in weights
        if edge[0] == edge[1] or tuple(sorted(edge)) in loops_two
    }
    percentile = spec.frequency_percentile
    if percentile is None:
        percentile = 1.0 if spec.profile == "interval_bounded" else 0.4
    kept, threshold, backbone = _frequency_filter(
        weights, nodes, source, sink, percentile, protected
    )
    model, unresolved = _make_bpmn(labels, kept, concurrent, source, sink)
    identifiers = {i: f"split_task_{i}" for i in range(len(labels))}
    identifiers.update({source: "split_start", sink: "split_end"})
    edge_rows = []
    for (a, b), count in sorted(original.items()):
        edge = (a, b)
        reason = (
            "concurrency_or_imbalance"
            if edge not in weights
            else "frequency_filtered"
            if edge not in kept
            else "short_loop"
            if edge in protected
            else "widest_path_backbone"
            if edge in backbone
            else "frequency_threshold"
        )
        edge_rows.append(
            SplitEdge(identifiers[a], identifiers[b], count, edge in kept, reason)
        )
    payload = SplitDiscovery(
        model,
        spec.profile,
        tuple((identifiers[i], label) for i, label in enumerate(labels)),
        len(traces),
        sum(not trace for trace in traces),
        threshold,
        tuple(edge_rows),
        tuple(
            SplitConcurrency(labels[a], labels[b], f, r, o, selected, reason)
            for a, b, f, r, o, selected, reason in candidates
        ),
        tuple((labels[a],) for a in sorted(loops_one))
        + tuple((labels[a], labels[b]) for a, b in sorted(loops_two)),
        unresolved,
        examined,
        connectivity_visits,
    )
    issues.append(
        ComputeIssue(
            "bounded_split_profile",
            "Local XOR/AND gateway discovery completed; full Classic/SM2 semantics, RPST/SESE joins and soundness are not certified",
        )
    )
    if unresolved:
        return finish(
            ComputeStatus.PARTIAL,
            payload,
            "prime_gateway_relation",
            "A local relation has no exact XOR/AND decomposition; graph diagnostics returned without a guessed BPMN model",
        )
    status = (
        ComputeStatus.PARTIAL
        if parent.status == ComputeStatus.PARTIAL
        or any(row[-1] == "mixed_causal_overlap_evidence" for row in candidates)
        else ComputeStatus.COMPUTED
    )
    return finish(status, payload)


def split_bpmn_xml(model: SplitBPMN) -> str:
    """Serialize the computed BPMN control-flow graph, without layout/DI."""
    if not isinstance(model, SplitBPMN):
        raise TypeError("model must be SplitBPMN")
    node_ids = [node.id for node in model.nodes]
    if (
        len(set(node_ids)) != len(node_ids)
        or model.start_id not in node_ids
        or model.end_id not in node_ids
    ):
        raise ValueError("model must have distinct nodes and existing start/end nodes")
    flow_ids = [flow.id for flow in model.flows]
    if len(set(flow_ids)) != len(flow_ids) or set(flow_ids) & set(node_ids):
        raise ValueError("flow and node IDs must be globally unique")
    if any(
        flow.source not in node_ids or flow.target not in node_ids
        for flow in model.flows
    ):
        raise ValueError("flow endpoints must exist")
    namespace = "http://www.omg.org/spec/BPMN/20100524/MODEL"

    def tag(value):
        return f"{{{namespace}}}{value}"

    definitions = Element(
        tag("definitions"), {"targetNamespace": "https://pix.local/bpmn"}
    )
    process_id = "split_process"
    while process_id in set(node_ids) | set(flow_ids):
        process_id += "_"
    process = SubElement(
        definitions, tag("process"), {"id": process_id, "isExecutable": "false"}
    )
    kinds = {
        "task": "task",
        "start_event": "startEvent",
        "end_event": "endEvent",
        "exclusive_gateway": "exclusiveGateway",
        "parallel_gateway": "parallelGateway",
    }
    for node in model.nodes:
        attrs = {"id": node.id}
        if node.activity is not None:
            attrs["name"] = node.activity
        if node.direction:
            attrs["gatewayDirection"] = (
                "Diverging" if node.direction == "split" else "Converging"
            )
        element = SubElement(process, tag(kinds[node.kind]), attrs)
        for flow in model.flows:
            if flow.target == node.id:
                SubElement(element, tag("incoming")).text = flow.id
            if flow.source == node.id:
                SubElement(element, tag("outgoing")).text = flow.id
    for flow in model.flows:
        SubElement(
            process,
            tag("sequenceFlow"),
            {"id": flow.id, "sourceRef": flow.source, "targetRef": flow.target},
        )
    return tostring(definitions, encoding="unicode", xml_declaration=True)


RESULT_SCHEMAS = {
    "pix.case_centric.discover_split_miner": (
        "split-discovery",
        SplitMinerSpec,
        SplitDiscovery,
    ),
}

__all__ = (
    "SplitMinerSpec",
    "SplitBPMNNode",
    "SplitBPMNFlow",
    "SplitBPMN",
    "SplitEdge",
    "SplitConcurrency",
    "SplitDiscovery",
    "discover_split_miner",
    "split_bpmn_xml",
)
