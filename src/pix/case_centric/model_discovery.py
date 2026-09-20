"""Footprints of native Petri nets and process trees, with reachability evidence.

The ``reachable`` profile describes executable prefixes, including deadlocking
branches. ``accepting`` retains only paths that can reach the exact final
marking. Symmetric visible adjacency is called ``parallel`` for footprint
compatibility; it is not itself concurrency. Actual commuting transition pairs
are reported separately. Search limits never turn missing observations into
negative facts.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from itertools import combinations

from pix.case_centric.model_analysis import Reachability, ReachabilitySpec, reachability
from pix.case_centric.powl import POWLNode, powl_to_petri_net
from pix.compute._common import _derived_result
from pix.compute.discovery import process_tree_to_petri_net
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


@dataclass(frozen=True, slots=True)
class ModelFootprintSpec:
    behavior: str = "reachable"
    max_states: int = 10_000
    max_tokens: int = 1000
    max_analysis_steps: int = 1_000_000

    def __post_init__(self):
        if self.behavior not in ("reachable", "accepting"):
            raise ValueError("behavior must be reachable or accepting")
        for name in ("max_states", "max_tokens", "max_analysis_steps"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class ModelFootprintRequest:
    model_digest: str | None
    parameters: ModelFootprintSpec


@dataclass(frozen=True, slots=True)
class ModelRelationWitness:
    source_activity: str
    target_activity: str
    source_state: int
    first_transition_id: str
    silent_transition_ids: tuple[str, ...]
    second_transition_id: str


@dataclass(frozen=True, slots=True)
class CommutingWitness:
    source_state: int
    transition_ids: tuple[str, str]
    activities: tuple[str, str]
    common_target: Marking


@dataclass(frozen=True, slots=True)
class ModelFootprints:
    model_kind: str
    model_digest: str
    behavior: str
    declared_activities: tuple[str, ...]
    activities: tuple[str, ...]
    inactive_activities: tuple[str, ...] | None
    directly_follows: tuple[tuple[str, str], ...]
    sequence: tuple[tuple[str, str], ...] | None
    parallel: tuple[tuple[str, str], ...]
    unrelated: tuple[tuple[str, str], ...] | None
    self_succession: tuple[str, ...]
    commuting_pairs: tuple[tuple[str, str], ...]
    start_activities: tuple[str, ...]
    end_activities: tuple[str, ...]
    accepts_empty_trace: bool | None
    accepted_language_exists: bool | None
    minimum_trace_length: int | None
    minimum_length_proven: bool
    always_activities: tuple[str, ...] | None
    reachability: Reachability
    relation_witnesses: tuple[ModelRelationWitness, ...]
    commuting_witnesses: tuple[CommutingWitness, ...]
    complete: bool
    analysis_steps: int


class _AnalysisLimit(Exception):
    pass


def discover_model_footprints(
    model: PetriNet | ProcessTree | POWLNode | ComputationResult,
    spec: ModelFootprintSpec = ModelFootprintSpec(),
) -> ComputationResult[ModelFootprints]:
    """Discover finite reachable-state footprints, retaining explicit bounds.

    A found shortest accepting path is an upper bound until reachability and
    shortest-path exploration finish. ``None`` for a negative/property field
    means unknown or undefined, never a false result. Process trees use PIX's
    semantics-preserving native conversion, retaining distinct duplicate leaves.
    A discovery result containing a native ``.model`` is also accepted.
    """
    if not isinstance(spec, ModelFootprintSpec):
        raise TypeError("spec must be ModelFootprintSpec")
    parent = model if isinstance(model, ComputationResult) else None
    parent_ids = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    issues = parent.issues if parent is not None else ()
    if parent is not None:
        if parent.value is None:
            return _derived_result(
                "pix.case_centric.discover_model_footprints",
                parent.source_digest,
                ModelFootprintRequest(None, spec),
                parent.status,
                None,
                issues,
                parent_computation_ids=parent_ids,
            )
        model = parent.value
        if not isinstance(model, (PetriNet, ProcessTree, POWLNode)):
            model = getattr(model, "model", None)
    if not isinstance(model, (PetriNet, ProcessTree, POWLNode)):
        raise TypeError(
            "model must be a native PetriNet, ProcessTree, POWLNode or a result containing one"
        )
    if isinstance(model, (ProcessTree, POWLNode)):
        from pix.models import model_document

        original_digest = model_document(model)["model_digest"]
        kind = "process-tree" if isinstance(model, ProcessTree) else "powl"
        net = (
            process_tree_to_petri_net(model)
            if isinstance(model, ProcessTree)
            else powl_to_petri_net(model)
        )
    else:
        original_digest = model_digest(model)
        kind, net = "petri-net", model
    request = ModelFootprintRequest(original_digest, spec)
    reached = reachability(net, ReachabilitySpec(spec.max_states, spec.max_tokens))
    graph = reached.value
    assert graph is not None
    parent_ids += (reached.computation_id,)
    issues += reached.issues
    source_digest = parent.source_digest if parent is not None else original_digest
    labels = {t.id: t.activity for t in net.transitions}
    declared = tuple(sorted({a for a in labels.values() if a is not None}))
    outgoing, incoming = defaultdict(list), defaultdict(list)
    for edge in graph.edges:
        outgoing[edge.source].append(edge)
        incoming[edge.target].append(edge)
    # Backward membership provides a concrete path to the final marking even
    # when the whole forward frontier is unfinished.
    coreachable = set()
    steps, limited = 0, False
    activities, starts, ends, relations, commuting = set(), set(), set(), {}, {}
    empty, min_length, minimum_proven, always, unrelated_pairs = (
        None,
        None,
        False,
        None,
        None,
    )
    final = graph.final_state
    acceptance = True if final is not None else False if graph.complete else None
    membership_complete, shortest_complete = False, False

    def tick():
        nonlocal steps
        steps += 1
        if steps > spec.max_analysis_steps:
            raise _AnalysisLimit

    try:
        agenda = [final] if final is not None else []
        coreachable.update(agenda)
        while agenda:
            state = agenda.pop()
            tick()
            for edge in incoming[state]:
                tick()
                if edge.source not in coreachable:
                    coreachable.add(edge.source)
                    agenda.append(edge.source)
        membership_complete = True
        eligible = (
            set(range(len(graph.markings)))
            if spec.behavior == "reachable"
            else coreachable
        )
        selected_edges = tuple(
            e for e in graph.edges if e.source in eligible and e.target in eligible
        )
        selected_outgoing = defaultdict(list)
        for edge in selected_edges:
            tick()
            selected_outgoing[edge.source].append(edge)
            if labels[edge.transition_id] is not None:
                activities.add(labels[edge.transition_id])
        # 0/1 shortest path counts visible events and permits arbitrary silent
        # cycles. It operates on the entire reached graph, not only footprints.
        if graph.initial_admitted:
            distance = {0: 0}
            queue = deque([0])
            while queue:
                state = queue.popleft()
                tick()
                for edge in outgoing[state]:
                    tick()
                    weight = labels[edge.transition_id] is not None
                    candidate = distance[state] + int(weight)
                    if candidate < distance.get(edge.target, float("inf")):
                        distance[edge.target] = candidate
                        (queue.append if weight else queue.appendleft)(edge.target)
                        if edge.target == final:
                            min_length = candidate
            if final == 0:
                min_length = 0
            shortest_complete = True
            minimum_proven = min_length is not None and (
                graph.complete or min_length == 0
            )

        closure_cache = {}

        def silent_closure(start):
            if start not in closure_cache:
                paths = {start: None}
                pending = deque([start])
                while pending:
                    state = pending.popleft()
                    tick()
                    for edge in selected_outgoing[state]:
                        tick()
                        if (
                            labels[edge.transition_id] is None
                            and edge.target not in paths
                        ):
                            paths[edge.target] = (state, edge.transition_id)
                            pending.append(edge.target)
                closure_cache[start] = paths
            return closure_cache[start]

        def silent_path(paths, target):
            path = []
            while paths[target] is not None:
                tick()
                target, transition_id = paths[target]
                path.append(transition_id)
            return tuple(reversed(path))

        initial_closure = (
            silent_closure(0) if graph.initial_admitted and 0 in eligible else {}
        )
        empty = True if final in initial_closure else False if graph.complete else None
        for state in initial_closure:
            for edge in selected_outgoing[state]:
                tick()
                if labels[edge.transition_id] is not None:
                    starts.add(labels[edge.transition_id])
        for edge in selected_edges:
            activity = labels[edge.transition_id]
            if activity is None:
                continue
            closure = silent_closure(edge.target)
            if final in closure:
                ends.add(activity)
            for state in closure:
                for second in selected_outgoing[state]:
                    tick()
                    second_activity = labels[second.transition_id]
                    if second_activity is not None:
                        pair = (activity, second_activity)
                        if pair not in relations:
                            relations[pair] = ModelRelationWitness(
                                activity,
                                second_activity,
                                edge.source,
                                edge.transition_id,
                                silent_path(closure, state),
                                second.transition_id,
                            )
        # Distinguish actual same-marking commuting transitions from merely
        # bidirectional traces (for example a serial two-activity loop).
        marking_ids = {m: i for i, m in enumerate(graph.markings)}
        for state in sorted(eligible):
            visible = tuple(
                t for t in graph.enabled_transition_ids[state] if labels[t] is not None
            )
            for left, right in combinations(visible, 2):
                tick()
                left_state = fire(net, graph.markings[state], left)
                right_state = fire(net, graph.markings[state], right)
                if right not in enabled_transitions(
                    net, left_state
                ) or left not in enabled_transitions(net, right_state):
                    continue
                after_lr, after_rl = (
                    fire(net, left_state, right),
                    fire(net, right_state, left),
                )
                if after_lr != after_rl:
                    continue
                if (
                    spec.behavior == "accepting"
                    and marking_ids.get(after_lr) not in coreachable
                ):
                    continue
                pair = tuple(sorted((labels[left], labels[right])))
                if pair not in commuting:
                    commuting[pair] = CommutingWitness(
                        state, (left, right), pair, after_lr
                    )
        # Intersection dataflow computes labels appearing on every accepting
        # path. Fixed points handle cycles without enumerating trace languages.
        if graph.complete and final is not None:
            mandatory = [set(declared) for _ in graph.markings]
            mandatory[0] = set()
            pending = deque(range(len(graph.markings)))
            queued = set(pending)
            while pending:
                state = pending.popleft()
                queued.remove(state)
                tick()
                for edge in outgoing[state]:
                    tick()
                    activity = labels[edge.transition_id]
                    offered = mandatory[state] | (
                        {activity} if activity is not None else set()
                    )
                    refined = mandatory[edge.target] & offered
                    if refined != mandatory[edge.target]:
                        mandatory[edge.target] = refined
                        if edge.target not in queued:
                            queued.add(edge.target)
                            pending.append(edge.target)
            always = tuple(sorted(mandatory[final]))
        if graph.complete:
            negatives = []
            for left, right in combinations(sorted(activities), 2):
                tick()
                if (left, right) not in relations and (right, left) not in relations:
                    negatives.append((left, right))
            unrelated_pairs = tuple(negatives)
    except _AnalysisLimit:
        limited = True
        issues += (
            ComputeIssue(
                "footprint_analysis_limit",
                "Analysis budget exhausted. Returned relations are positive witnesses; negative relation sets and universal properties are unknown.",
            ),
        )
    complete = graph.complete and not limited
    symmetric = tuple(
        sorted((a, b) for a, b in relations if a != b and (b, a) in relations)
    )
    sequence = (
        tuple(sorted((a, b) for a, b in relations if (b, a) not in relations))
        if complete
        else None
    )
    unrelated = unrelated_pairs if complete else None
    if not membership_complete:
        activities = set()
    value = ModelFootprints(
        kind,
        original_digest,
        spec.behavior,
        declared,
        tuple(sorted(activities)),
        tuple(a for a in declared if a not in activities) if complete else None,
        tuple(sorted(relations)),
        sequence,
        symmetric,
        unrelated,
        tuple(sorted(a for a, b in relations if a == b)),
        tuple(sorted(commuting)),
        tuple(sorted(starts)),
        tuple(sorted(ends)),
        empty,
        acceptance,
        min_length,
        minimum_proven and shortest_complete,
        always,
        graph,
        tuple(relations[p] for p in sorted(relations)),
        tuple(commuting[p] for p in sorted(commuting)),
        complete,
        min(steps, spec.max_analysis_steps),
    )
    partial = not complete or (
        parent is not None and parent.status == ComputeStatus.PARTIAL
    )
    return _derived_result(
        "pix.case_centric.discover_model_footprints",
        source_digest,
        request,
        ComputeStatus.PARTIAL if partial else ComputeStatus.COMPUTED,
        value,
        issues,
        parent_computation_ids=parent_ids,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_model_footprints": (
        "case-model-footprints",
        ModelFootprintRequest,
        ModelFootprints,
    ),
}

__all__ = (
    "ModelFootprintSpec",
    "ModelFootprintRequest",
    "ModelRelationWitness",
    "CommutingWitness",
    "ModelFootprints",
    "discover_model_footprints",
)
