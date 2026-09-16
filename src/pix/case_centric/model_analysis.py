"""Native, evidence-bearing analysis of accepting weighted P/T nets.

Reachability is exact only when its finite frontier is exhausted. Search caps
never certify unboundedness or unsoundness. Workflow soundness here is the
classical one-token workflow-net property (option to complete, proper
completion, no dead transitions), not termination of every possible run.

The reduction rules below preserve accepted visible languages; they do not
preserve transition identities, token statistics, or stochastic probabilities.
Structural comparison deliberately identifies nodes by ID, while language
comparison uses epsilon-NFA semantics and is independent of those IDs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import ClassVar

from pix.case_centric._model_algebra import (
    AlgebraInvariants,
    MarkingEquationReport,
)
from pix.case_centric._model_algebra import (
    incidence_matrix as _incidence_matrix,
)
from pix.case_centric._model_algebra import (
    invariants as _invariants,
)
from pix.case_centric._model_algebra import (
    marking_equation as _marking_equation,
)
from pix.compute._common import _result
from pix.compute.model_semantics import enabled_transitions, fire, model_digest
from pix.contracts.models import Marking, PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _positive(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")


def _net(net: PetriNet) -> None:
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")


@dataclass(frozen=True, slots=True)
class ReachabilitySpec:
    """Caps count admitted distinct markings and total tokens per marking."""

    max_states: int = 10000
    max_tokens: int = 1000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.reachability.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _positive(self.max_states, "max_states")
        _positive(self.max_tokens, "max_tokens")


@dataclass(frozen=True, slots=True)
class ReachabilityEdge:
    source: int
    transition_id: str
    target: int


@dataclass(frozen=True, slots=True)
class ReachabilityBoundary:
    """A real executable edge whose target was not admitted under the caps."""

    source: int
    transition_id: str
    marking: Marking
    reason: str


@dataclass(frozen=True, slots=True)
class Reachability:
    model_digest: str
    markings: tuple[Marking, ...]
    edges: tuple[ReachabilityEdge, ...]
    enabled_transition_ids: tuple[tuple[str, ...], ...]
    boundary: tuple[ReachabilityBoundary, ...]
    complete: bool
    initial_admitted: bool
    final_state: int | None
    max_observed_tokens: int


def _explore(net: PetriNet, spec: ReachabilitySpec) -> Reachability:
    initial_tokens = sum(count for _, count in net.initial_marking.tokens)
    if initial_tokens > spec.max_tokens:
        return Reachability(
            model_digest(net), (), (), (), (), False, False, None, initial_tokens
        )
    markings = [net.initial_marking]
    indices = {net.initial_marking: 0}
    edges: list[ReachabilityEdge] = []
    boundary: list[ReachabilityBoundary] = []
    enabled_rows: list[tuple[str, ...]] = []
    cursor = 0
    maximum = initial_tokens
    while cursor < len(markings):
        marking = markings[cursor]
        enabled = enabled_transitions(net, marking)
        enabled_rows.append(enabled)
        for transition in enabled:
            after = fire(net, marking, transition)
            total = sum(count for _, count in after.tokens)
            maximum = max(maximum, total)
            if after not in indices:
                reason = None
                if total > spec.max_tokens:
                    reason = "max_tokens"
                elif len(markings) >= spec.max_states:
                    reason = "max_states"
                if reason is not None:
                    boundary.append(
                        ReachabilityBoundary(cursor, transition, after, reason)
                    )
                    continue
                indices[after] = len(markings)
                markings.append(after)
            edges.append(ReachabilityEdge(cursor, transition, indices[after]))
        cursor += 1
    return Reachability(
        model_digest(net),
        tuple(markings),
        tuple(edges),
        tuple(enabled_rows),
        tuple(boundary),
        not boundary,
        True,
        indices.get(net.final_marking),
        maximum,
    )


def _search_issues(graph: Reachability) -> tuple[ComputeIssue, ...]:
    if graph.complete:
        return ()
    reasons = sorted({row.reason for row in graph.boundary})
    if not graph.initial_admitted:
        reasons.append("initial_exceeds_max_tokens")
    return tuple(
        ComputeIssue(reason, "Reachability frontier is incomplete; no global proof.")
        for reason in reasons
    )


def reachability(
    net: PetriNet, spec: ReachabilitySpec = ReachabilitySpec()
) -> ComputationResult[Reachability]:
    _net(net)
    if not isinstance(spec, ReachabilitySpec):
        raise TypeError("spec must be ReachabilitySpec")
    value = _explore(net, spec)
    issues = _search_issues(value)
    return _result(
        "pix.case_centric.reachability",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class WorkflowNetSpec:
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.workflow_net.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class WorkflowNetStructure:
    source_places: tuple[str, ...]
    sink_places: tuple[str, ...]
    nodes_off_source_sink_paths: tuple[str, ...]
    graph_is_workflow_net: bool
    accepting_markings_are_workflow_markings: bool
    is_accepting_workflow_net: bool


def _closure(seeds, adjacency):
    seen = set(seeds)
    pending = list(seen)
    while pending:
        for target in adjacency.get(pending.pop(), ()):
            if target not in seen:
                seen.add(target)
                pending.append(target)
    return seen


def _workflow(net: PetriNet) -> WorkflowNetStructure:
    nodes = {place.id for place in net.places} | {t.id for t in net.transitions}
    outgoing = {node: set() for node in nodes}
    incoming = {node: set() for node in nodes}
    for arc in net.arcs:
        outgoing[arc.source].add(arc.target)
        incoming[arc.target].add(arc.source)
    sources = tuple(place.id for place in net.places if not incoming[place.id])
    sinks = tuple(place.id for place in net.places if not outgoing[place.id])
    connected = _closure(sources, outgoing) & _closure(sinks, incoming)
    off = tuple(sorted(nodes - connected))
    structural = len(sources) == 1 and len(sinks) == 1 and not off
    marking_match = (
        structural
        and net.initial_marking == Marking(((sources[0], 1),))
        and net.final_marking == Marking(((sinks[0], 1),))
    )
    return WorkflowNetStructure(
        sources, sinks, off, structural, marking_match, structural and marking_match
    )


def check_workflow_net(net: PetriNet) -> ComputationResult[WorkflowNetStructure]:
    """Check unique source/sink places and every node on a source-to-sink path."""
    _net(net)
    return _result(
        "pix.case_centric.workflow_net",
        None,
        WorkflowNetSpec(),
        ComputeStatus.COMPUTED,
        _workflow(net),
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class SoundnessDiagnostics:
    structure: WorkflowNetStructure
    reachability: Reachability
    sound: bool | None
    option_to_complete: bool | None
    proper_completion: bool | None
    no_dead_transitions: bool | None
    dead_transition_ids: tuple[str, ...]
    unobserved_transition_ids: tuple[str, ...]
    noncompleting_states: tuple[int, ...]
    improper_completion_states: tuple[int, ...]
    deadlock_states: tuple[int, ...]
    bounded: bool | None
    assessment: str


def check_soundness(
    net: PetriNet, spec: ReachabilitySpec = ReachabilitySpec()
) -> ComputationResult[SoundnessDiagnostics]:
    """Three-valued finite-state proof with concrete refutations when available.

    A reachable non-final deadlock or final-marking cover with residual tokens
    refutes its property even if another branch exceeds a search cap. Other
    negative reachability claims require the entire graph to be complete.
    """
    _net(net)
    if not isinstance(spec, ReachabilitySpec):
        raise TypeError("spec must be ReachabilitySpec")
    structure = _workflow(net)
    graph = _explore(net, spec)
    reverse = {index: set() for index in range(len(graph.markings))}
    for edge in graph.edges:
        reverse[edge.target].add(edge.source)
    completing = _closure(
        () if graph.final_state is None else (graph.final_state,), reverse
    )
    deadlocks = tuple(
        index
        for index, enabled in enumerate(graph.enabled_transition_ids)
        if not enabled and index != graph.final_state
    )
    noncompleting = (
        tuple(index for index in range(len(graph.markings)) if index not in completing)
        if graph.complete
        else deadlocks
    )
    option = not noncompleting if graph.complete else False if deadlocks else None
    final = dict(net.final_marking.tokens)
    improper = tuple(
        index
        for index, marking in enumerate(graph.markings)
        if marking != net.final_marking
        and all(
            dict(marking.tokens).get(place, 0) >= count
            for place, count in final.items()
        )
    )
    proper = False if improper else True if graph.complete else None
    observed = {tid for row in graph.enabled_transition_ids for tid in row}
    unseen = tuple(t.id for t in net.transitions if t.id not in observed)
    dead = unseen if graph.complete else ()
    no_dead = not unseen if graph.complete else True if not unseen else None
    properties = (option, proper, no_dead)
    if not structure.is_accepting_workflow_net:
        sound = False
        assessment = "not_an_accepting_workflow_net"
    elif any(item is False for item in properties):
        sound = False
        assessment = "refuted"
    elif all(item is True for item in properties):
        sound = True
        assessment = "proven_finite"
    else:
        sound = None
        assessment = "unknown_search_limit"
    value = SoundnessDiagnostics(
        structure,
        graph,
        sound,
        option,
        proper,
        no_dead,
        dead,
        unseen,
        noncompleting,
        improper,
        deadlocks,
        True if graph.complete else None,
        assessment,
    )
    issues = _search_issues(graph)
    return _result(
        "pix.case_centric.soundness",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class ComplexitySpec:
    """Arc degrees count incidence arcs, not multiplicity; k must be finite."""

    k: float = 2.0
    reachability: ReachabilitySpec = ReachabilitySpec()
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.model_complexity.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.k, (int, float)) or isinstance(self.k, bool):
            raise TypeError("k must be a number")
        if not isfinite(self.k):
            raise ValueError("k must be finite")
        if not isinstance(self.reachability, ReachabilitySpec):
            raise TypeError("reachability must be ReachabilitySpec")
        object.__setattr__(self, "k", float(self.k))


@dataclass(frozen=True, slots=True)
class ModelComplexity:
    place_count: int
    transition_count: int
    arc_count: int
    total_arc_weight: int
    mean_arc_degree: float
    arc_degree_simplicity: float
    extended_cardoso: int
    extended_cyclomatic: int | None
    reachability_states: int
    reachability_distinct_state_edges: int
    reachability_scc_count: int | None
    reachability_complete: bool


def _scc_count(count: int, pairs: set[tuple[int, int]]) -> int:
    """Iterative Kosaraju; avoids recursion depth depending on state count."""
    out = {index: set() for index in range(count)}
    reverse = {index: set() for index in range(count)}
    for source, target in pairs:
        out[source].add(target)
        reverse[target].add(source)
    seen: set[int] = set()
    order: list[int] = []
    for node in range(count):
        if node in seen:
            continue
        stack = [(node, False)]
        while stack:
            current, exiting = stack.pop()
            if exiting:
                order.append(current)
            elif current not in seen:
                seen.add(current)
                stack.append((current, True))
                stack.extend(
                    (target, False)
                    for target in sorted(out[current], reverse=True)
                    if target not in seen
                )
    seen.clear()
    components = 0
    for node in reversed(order):
        if node not in seen:
            components += 1
            seen.add(node)
            pending = [node]
            while pending:
                for target in reverse[pending.pop()]:
                    if target not in seen:
                        seen.add(target)
                        pending.append(target)
    return components


def model_complexity(
    net: PetriNet, spec: ComplexitySpec = ComplexitySpec()
) -> ComputationResult[ModelComplexity]:
    _net(net)
    if not isinstance(spec, ComplexitySpec):
        raise TypeError("spec must be ComplexitySpec")
    total_nodes = len(net.places) + len(net.transitions)
    mean = 2 * len(net.arcs) / total_nodes if total_nodes else 0.0
    postsets = {
        t.id: tuple(arc.target for arc in net.arcs if arc.source == t.id)
        for t in net.transitions
    }
    cardoso = sum(
        len({postsets[arc.target] for arc in net.arcs if arc.source == place.id})
        for place in net.places
    )
    graph = _explore(net, spec.reachability)
    pairs = {(edge.source, edge.target) for edge in graph.edges}
    sccs = _scc_count(len(graph.markings), pairs) if graph.complete else None
    cyclomatic = None if sccs is None else len(pairs) - len(graph.markings) + sccs
    value = ModelComplexity(
        len(net.places),
        len(net.transitions),
        len(net.arcs),
        sum(arc.weight for arc in net.arcs),
        mean,
        1 / (1 + max(mean - spec.k, 0)),
        cardoso,
        cyclomatic,
        len(graph.markings),
        len(pairs),
        sccs,
        graph.complete,
    )
    issues = _search_issues(graph)
    return _result(
        "pix.case_centric.model_complexity",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class ReductionSpec:
    rules: tuple[str, ...] = (
        "silent_identity",
        "duplicate_transition",
        "duplicate_place",
    )
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.reduce_model.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        allowed = {"silent_identity", "duplicate_transition", "duplicate_place"}
        if not isinstance(self.rules, tuple) or not all(
            isinstance(rule, str) for rule in self.rules
        ):
            raise TypeError("rules must be a tuple of rule names")
        if len(set(self.rules)) != len(self.rules) or any(
            rule not in allowed for rule in self.rules
        ):
            raise ValueError("rules must be unique supported proven rules")


@dataclass(frozen=True, slots=True)
class ReductionStep:
    rule: str
    removed_node: str
    retained_node: str | None


@dataclass(frozen=True, slots=True)
class ModelReduction:
    original_model_digest: str
    reduced_model_digest: str
    model: PetriNet
    steps: tuple[ReductionStep, ...]
    preservation: str


def _remove(net: PetriNet, node: str) -> PetriNet:
    return PetriNet(
        tuple(place for place in net.places if place.id != node),
        tuple(t for t in net.transitions if t.id != node),
        tuple(arc for arc in net.arcs if node not in (arc.source, arc.target)),
        Marking(tuple(row for row in net.initial_marking.tokens if row[0] != node)),
        Marking(tuple(row for row in net.final_marking.tokens if row[0] != node)),
    )


def reduce_model(
    net: PetriNet, spec: ReductionSpec = ReductionSpec()
) -> ComputationResult[ModelReduction]:
    """Apply only local rules with an accepted-visible-language proof.

    Silent identity transitions leave their whole marking unchanged. Duplicate
    transitions have identical activity and weighted incidence. Duplicate places
    have equal initial/final counts and equal weighted incidence, so induction
    over firings keeps their token counts equal and one constraint is redundant.
    """
    _net(net)
    if not isinstance(spec, ReductionSpec):
        raise TypeError("spec must be ReductionSpec")
    current = net
    steps: list[ReductionStep] = []
    changed = True
    while changed:
        changed = False
        for rule in spec.rules:
            signatures = {}
            nodes = current.places if rule == "duplicate_place" else current.transitions
            for node in nodes:
                pre = tuple(
                    (a.source, a.weight) for a in current.arcs if a.target == node.id
                )
                post = tuple(
                    (a.target, a.weight) for a in current.arcs if a.source == node.id
                )
                retained = None
                if rule == "silent_identity":
                    if node.activity is not None or pre != post:
                        continue
                else:
                    if rule == "duplicate_place":
                        signature = (
                            pre,
                            post,
                            dict(current.initial_marking.tokens).get(node.id, 0),
                            dict(current.final_marking.tokens).get(node.id, 0),
                        )
                    else:
                        signature = (pre, post, node.activity)
                    if signature not in signatures:
                        signatures[signature] = node.id
                        continue
                    retained = signatures[signature]
                current = _remove(current, node.id)
                steps.append(ReductionStep(rule, node.id, retained))
                changed = True
                break
            if changed:
                break
    value = ModelReduction(
        model_digest(net),
        model_digest(current),
        current,
        tuple(steps),
        "accepted_visible_language",
    )
    return _result(
        "pix.case_centric.reduce_model",
        None,
        spec,
        ComputeStatus.COMPUTED,
        value,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class DecompositionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.decompose_model.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ModelDecomposition:
    components: tuple[PetriNet, ...]
    component_node_ids: tuple[tuple[str, ...], ...]
    composition: str


def decompose_model(net: PetriNet) -> ComputationResult[ModelDecomposition]:
    """Weak-component decomposition; accepting language is their shuffle product.

    This does not claim SESE/RPST, S-components, or maximal decomposability.
    Isolated places and transitions are retained as components.
    """
    _net(net)
    nodes = {place.id for place in net.places} | {t.id for t in net.transitions}
    adjacency = {node: set() for node in nodes}
    for arc in net.arcs:
        adjacency[arc.source].add(arc.target)
        adjacency[arc.target].add(arc.source)
    groups = []
    remaining = set(nodes)
    while remaining:
        group = _closure((min(remaining),), adjacency)
        groups.append(tuple(sorted(group)))
        remaining.difference_update(group)
    components = []
    for group in groups:
        selected = set(group)
        components.append(
            PetriNet(
                tuple(p for p in net.places if p.id in selected),
                tuple(t for t in net.transitions if t.id in selected),
                tuple(a for a in net.arcs if a.source in selected),
                Marking(
                    tuple(
                        row for row in net.initial_marking.tokens if row[0] in selected
                    )
                ),
                Marking(
                    tuple(row for row in net.final_marking.tokens if row[0] in selected)
                ),
            )
        )
    value = ModelDecomposition(
        tuple(components), tuple(groups), "independent_shuffle_product"
    )
    return _result(
        "pix.case_centric.decompose_model",
        None,
        DecompositionSpec(),
        ComputeStatus.COMPUTED,
        value,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class ModelComparisonSpec:
    """Language equivalence is exact only for two completely explored finite nets."""

    method: str = "language"
    reachability: ReachabilitySpec = ReachabilitySpec()
    max_product_states: int = 10000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.compare_models.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.method not in ("language", "label_set", "identity_structure"):
            raise ValueError(
                "method must be language, label_set, or identity_structure"
            )
        if not isinstance(self.reachability, ReachabilitySpec):
            raise TypeError("reachability must be ReachabilitySpec")
        _positive(self.max_product_states, "max_product_states")


@dataclass(frozen=True, slots=True)
class ModelComparisonRequest:
    other_model_digest: str
    parameters: ModelComparisonSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.compare_models.request"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ModelComparison:
    method: str
    equivalent: bool | None
    similarity: tuple[int, int] | None
    distinguishing_trace: tuple[str, ...] | None
    accepted_by: str | None
    compared_product_states: int
    complete: bool
    left_reachability_complete: bool | None
    right_reachability_complete: bool | None


def _automaton(net: PetriNet, graph: Reachability):
    labels = {t.id: t.activity for t in net.transitions}
    silent = {index: set() for index in range(len(graph.markings))}
    moves: dict[tuple[int, str], set[int]] = {}
    for edge in graph.edges:
        label = labels[edge.transition_id]
        if label is None:
            silent[edge.source].add(edge.target)
        else:
            moves.setdefault((edge.source, label), set()).add(edge.target)
    return silent, moves


def _language_compare(left: PetriNet, right: PetriNet, spec: ModelComparisonSpec):
    a, b = _explore(left, spec.reachability), _explore(right, spec.reachability)
    if not a.complete or not b.complete:
        value = ModelComparison(
            "language", None, None, None, None, 0, False, a.complete, b.complete
        )
        return value, (
            ComputeIssue(
                "reachability_limit",
                "Language comparison requires complete finite state graphs.",
            ),
        )
    silent_a, moves_a = _automaton(left, a)
    silent_b, moves_b = _automaton(right, b)
    alphabet = sorted(
        {
            t.activity
            for net in (left, right)
            for t in net.transitions
            if t.activity is not None
        }
    )
    initial = (frozenset(_closure((0,), silent_a)), frozenset(_closure((0,), silent_b)))
    pending = deque((initial,))
    # Store parent links, not a copy of each increasingly long visible prefix.
    parents = {initial: None}
    while pending:
        current = pending.popleft()
        states_a, states_b = current
        accept_a, accept_b = a.final_state in states_a, b.final_state in states_b
        if accept_a != accept_b:
            trace = []
            path = current
            while parents[path] is not None:
                path, label = parents[path]
                trace.append(label)
            return ModelComparison(
                "language",
                False,
                None,
                tuple(reversed(trace)),
                "left" if accept_a else "right",
                len(parents),
                True,
                True,
                True,
            ), ()
        for label in alphabet:
            successors_a = {
                target
                for state in states_a
                for target in moves_a.get((state, label), ())
            }
            successors_b = {
                target
                for state in states_b
                for target in moves_b.get((state, label), ())
            }
            after = (
                frozenset(_closure(successors_a, silent_a)),
                frozenset(_closure(successors_b, silent_b)),
            )
            if after in parents:
                continue
            if len(parents) >= spec.max_product_states:
                value = ModelComparison(
                    "language", None, None, None, None, len(parents), False, True, True
                )
                return value, (
                    ComputeIssue(
                        "product_state_limit",
                        "Equivalence search did not exhaust its frontier.",
                    ),
                )
            parents[after] = (current, label)
            pending.append(after)
    return ModelComparison(
        "language", True, None, None, None, len(parents), True, True, True
    ), ()


def _structure_tokens(net: PetriNet):
    return (
        {("place", p.id) for p in net.places}
        | {("transition", t.id, t.activity) for t in net.transitions}
        | {("arc", a.source, a.target, a.weight) for a in net.arcs}
        | {("initial", place, count) for place, count in net.initial_marking.tokens}
        | {("final", place, count) for place, count in net.final_marking.tokens}
    )


def compare_models(
    left: PetriNet, right: PetriNet, spec: ModelComparisonSpec = ModelComparisonSpec()
) -> ComputationResult[ModelComparison]:
    """Compare label sets, node-ID-sensitive structure, or accepted languages.

    Jaccard(empty, empty)=1 is explicit for set metrics. A label/structure score
    does not assert behavioral equivalence. Language equivalence retains all
    silent and duplicate-label alternatives and may cover infinite languages
    provided the underlying marking graphs are finite and fully enumerated.
    """
    _net(left)
    _net(right)
    if not isinstance(spec, ModelComparisonSpec):
        raise TypeError("spec must be ModelComparisonSpec")
    request = ModelComparisonRequest(model_digest(right), spec)
    issues = ()
    if spec.method == "language":
        value, issues = _language_compare(left, right, spec)
    else:
        if spec.method == "label_set":
            a = {t.activity for t in left.transitions if t.activity is not None}
            b = {t.activity for t in right.transitions if t.activity is not None}
        else:
            a, b = _structure_tokens(left), _structure_tokens(right)
        similarity = Fraction(len(a & b), len(a | b)) if a | b else Fraction(1)
        value = ModelComparison(
            spec.method,
            None,
            (similarity.numerator, similarity.denominator),
            None,
            None,
            0,
            True,
            None,
            None,
        )
    return _result(
        "pix.case_centric.compare_models",
        None,
        request,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(left),
    )


@dataclass(frozen=True, slots=True)
class IncidenceSpec:
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.incidence.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ModelIncidence:
    place_ids: tuple[str, ...]
    transition_ids: tuple[str, ...]
    output_minus_input: tuple[tuple[int, ...], ...]


def model_incidence(net: PetriNet) -> ComputationResult[ModelIncidence]:
    """Exact weighted output-minus-input matrix in stable node-ID order."""
    _net(net)
    value = ModelIncidence(*_incidence_matrix(net))
    return _result(
        "pix.case_centric.incidence",
        None,
        IncidenceSpec(),
        ComputeStatus.COMPUTED,
        value,
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class InvariantsSpec:
    """A rational-space basis; not a positive cone or integer-lattice basis."""

    kind: str = "place"
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.invariants.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.kind not in ("place", "transition"):
            raise ValueError("kind must be place or transition")


def model_invariants(
    net: PetriNet, spec: InvariantsSpec = InvariantsSpec()
) -> ComputationResult[AlgebraInvariants]:
    """Primitive integer vectors spanning the complete rational nullspace."""
    _net(net)
    if not isinstance(spec, InvariantsSpec):
        raise TypeError("spec must be InvariantsSpec")
    return _result(
        "pix.case_centric.invariants",
        None,
        spec,
        ComputeStatus.COMPUTED,
        _invariants(net, spec.kind),
        source_digest=model_digest(net),
    )


@dataclass(frozen=True, slots=True)
class MarkingEquationSpec:
    """Exact nonnegative rational LP; unspecified transition costs equal one.

    All costs are (numerator, denominator) pairs. Cost and marking choices are
    part of the computation identity. None uses the model's accepting marking.
    The cap counts column bases, including singular candidates.
    """

    initial: Marking | None = None
    target: Marking | None = None
    transition_costs: tuple[tuple[str, tuple[int, int]], ...] = ()
    max_bases: int = 100000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.marking_equation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("initial", "target"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Marking):
                raise TypeError(f"{name} must be Marking or None")
        _positive(self.max_bases, "max_bases")
        if not isinstance(self.transition_costs, tuple):
            raise TypeError("transition_costs must be a tuple")
        normalized = []
        seen = set()
        for row in self.transition_costs:
            if not isinstance(row, tuple) or len(row) != 2:
                raise TypeError("cost entries must be (transition_id, rational_pair)")
            transition, pair = row
            if not isinstance(transition, str) or not transition.strip():
                raise TypeError("cost transition IDs must be nonempty strings")
            if transition in seen:
                raise ValueError("duplicate cost transition ID")
            if (
                not isinstance(pair, tuple)
                or len(pair) != 2
                or not all(
                    isinstance(item, int) and not isinstance(item, bool)
                    for item in pair
                )
            ):
                raise TypeError(
                    "cost must be a pair of integer numerator and denominator"
                )
            if pair[0] < 0 or pair[1] <= 0:
                raise ValueError(
                    "cost requires nonnegative numerator and positive denominator"
                )
            exact = Fraction(*pair)
            normalized.append((transition, (exact.numerator, exact.denominator)))
            seen.add(transition)
        object.__setattr__(self, "transition_costs", tuple(sorted(normalized)))


def marking_equation_bound(
    net: PetriNet, spec: MarkingEquationSpec = MarkingEquationSpec()
) -> ComputationResult[MarkingEquationReport]:
    """Exact rational relaxation lower bound, never a reachability certificate.

    Infeasibility disproves a firing sequence between these markings. Feasibility
    alone does not prove integrality, an enabled ordering, or an executable path.
    Cap exhaustion exposes no proven objective, only a possible LP incumbent.
    """
    _net(net)
    if not isinstance(spec, MarkingEquationSpec):
        raise TypeError("spec must be MarkingEquationSpec")
    value = _marking_equation(
        net, spec.initial, spec.target, dict(spec.transition_costs), spec.max_bases
    )
    issues = (
        (
            ComputeIssue(
                "max_bases",
                "LP optimum is unknown because basis enumeration was capped.",
            ),
        )
        if value.status == "unknown"
        else ()
    )
    return _result(
        "pix.case_centric.marking_equation",
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=model_digest(net),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.reachability": (
        "case-reachability",
        ReachabilitySpec,
        Reachability,
    ),
    "pix.case_centric.workflow_net": (
        "case-workflow-net",
        WorkflowNetSpec,
        WorkflowNetStructure,
    ),
    "pix.case_centric.soundness": (
        "case-soundness",
        ReachabilitySpec,
        SoundnessDiagnostics,
    ),
    "pix.case_centric.model_complexity": (
        "case-model-complexity",
        ComplexitySpec,
        ModelComplexity,
    ),
    "pix.case_centric.reduce_model": (
        "case-model-reduction",
        ReductionSpec,
        ModelReduction,
    ),
    "pix.case_centric.decompose_model": (
        "case-model-decomposition",
        DecompositionSpec,
        ModelDecomposition,
    ),
    "pix.case_centric.compare_models": (
        "case-model-comparison",
        ModelComparisonRequest,
        ModelComparison,
    ),
    "pix.case_centric.incidence": ("case-incidence", IncidenceSpec, ModelIncidence),
    "pix.case_centric.invariants": (
        "case-invariants",
        InvariantsSpec,
        AlgebraInvariants,
    ),
    "pix.case_centric.marking_equation": (
        "case-marking-equation",
        MarkingEquationSpec,
        MarkingEquationReport,
    ),
}

__all__ = (
    "ReachabilitySpec",
    "Reachability",
    "ReachabilityEdge",
    "ReachabilityBoundary",
    "WorkflowNetStructure",
    "WorkflowNetSpec",
    "SoundnessDiagnostics",
    "ComplexitySpec",
    "ModelComplexity",
    "ReductionSpec",
    "ReductionStep",
    "ModelReduction",
    "DecompositionSpec",
    "ModelDecomposition",
    "ModelComparisonSpec",
    "ModelComparisonRequest",
    "ModelComparison",
    "reachability",
    "check_workflow_net",
    "check_soundness",
    "model_complexity",
    "reduce_model",
    "decompose_model",
    "compare_models",
    "IncidenceSpec",
    "ModelIncidence",
    "model_incidence",
    "InvariantsSpec",
    "AlgebraInvariants",
    "model_invariants",
    "MarkingEquationSpec",
    "MarkingEquationReport",
    "marking_equation_bound",
)
