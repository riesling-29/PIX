"""Native POWL representation, discovery profiles, and accepting-net conversion.

The language has activity/tau leaves, exclusive choice, do(redo do)* loops,
and strict partial orders over submodels. An order edge requires the entire
predecessor submodel to finish before the successor starts; unrelated
submodels may interleave. The representation follows the original POWL
language, not the later choice-graph extension:
https://publications.rwth-aachen.de/record/1002225/files/1002225.pdf

Discovery is PIX's explicit profile, not an implementation claim for PM4Py's
BruteForce, Maximal, or IM POWL variants. ``exact_variants`` retains exactly the
observed finite language. ``observed_order`` groups single-occurrence traces
by alphabet, preserves their common precedence, and generalizes observed
primitive repetitions to positive loops. Other traces retain exact branches.
Observed order is not proof of causality or of complete concurrency evidence.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import ClassVar, Literal

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus


def _positive(value: object, name: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class POWLNode:
    """Immutable occurrence tree; equal labels do not merge model occurrences.

    ``order`` contains pairs of child indices. An acyclic generating relation
    is accepted and normalized to its strict transitive closure. Child order
    determines identity, but not extra precedence. XOR/partial-order nodes
    require at least two children; loop children are exactly (do, redo).
    """

    kind: Literal["activity", "tau", "xor", "loop", "partial_order"]
    activity: str | None = None
    children: tuple[POWLNode, ...] = ()
    order: tuple[tuple[int, int], ...] = ()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.kind not in ("activity", "tau", "xor", "loop", "partial_order"):
            raise ValueError("unsupported POWL node kind")
        if not isinstance(self.children, tuple) or not all(
            isinstance(c, POWLNode) for c in self.children
        ):
            raise TypeError("children must be a tuple of POWLNode occurrences")
        if not isinstance(self.order, tuple):
            raise TypeError("order must be a tuple")
        if self.kind == "activity":
            if not isinstance(self.activity, str) or not self.activity.strip():
                raise ValueError("activity must be nonblank text")
            self.activity.encode("utf-8")
        elif self.activity is not None:
            raise ValueError("only activity leaves carry activity labels")
        if self.kind in ("activity", "tau") and self.children:
            raise ValueError("leaves cannot have children")
        if self.kind in ("xor", "partial_order") and len(self.children) < 2:
            raise ValueError("xor and partial_order require at least two children")
        if self.kind == "loop" and len(self.children) != 2:
            raise ValueError("loop requires exactly do and redo children")
        if self.kind != "partial_order":
            if self.order:
                raise ValueError("only partial_order carries an ordering relation")
            return
        size = len(self.children)
        reachable = [0] * size
        for edge in self.order:
            if (
                not isinstance(edge, tuple)
                or len(edge) != 2
                or any(type(i) is not int or not 0 <= i < size for i in edge)
            ):
                raise ValueError("order edges must reference two child indices")
            reachable[edge[0]] |= 1 << edge[1]
        for via in range(size):
            for source in range(size):
                if reachable[source] & (1 << via):
                    reachable[source] |= reachable[via]
        if any(row & (1 << i) for i, row in enumerate(reachable)):
            raise ValueError("partial order must be acyclic and irreflexive")
        object.__setattr__(
            self,
            "order",
            tuple(
                (i, j)
                for i, row in enumerate(reachable)
                for j in range(size)
                if row & (1 << j)
            ),
        )


@dataclass(frozen=True, slots=True)
class POWLConversionSpec:
    max_model_nodes: int = 20_000
    max_depth: int = 128
    max_net_nodes: int = 200_000
    max_net_arcs: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("max_model_nodes", "max_depth", "max_net_nodes", "max_net_arcs"):
            _positive(getattr(self, name), name)
        if self.max_depth > 128:
            raise ValueError(
                "max_depth cannot exceed the supported recursive conversion depth 128"
            )


class POWLResourceLimit(ValueError):
    """The requested complete conversion/discovery exceeded an explicit bound."""


def _shape(model: POWLNode, spec: POWLConversionSpec) -> int:
    pending = [(model, 1)]
    count = 0
    while pending:
        node, depth = pending.pop()
        count += 1
        if count > spec.max_model_nodes or depth > spec.max_depth:
            raise POWLResourceLimit("POWL model node or depth bound exceeded")
        pending.extend((child, depth + 1) for child in node.children)
    return count


def powl_to_petri_net(
    model: POWLNode, spec: POWLConversionSpec = POWLConversionSpec()
) -> PetriNet:
    """Construct an accepting unit-arc net, or raise without returning a prefix.

    The construction retains explicit entry/exit boundaries. Partial-order
    branches receive one start permission and predecessor-completion tokens;
    the final join consumes one completion token from every branch. This
    permits interleaving inside unrelated submodels, not just atomic blocks.
    """
    if not isinstance(model, POWLNode) or not isinstance(spec, POWLConversionSpec):
        raise TypeError("expected POWLNode and POWLConversionSpec")
    _shape(model, spec)
    places: list[Place] = []
    transitions: list[Transition] = []
    arcs: list[Arc] = []

    def place() -> str:
        if len(places) + len(transitions) >= spec.max_net_nodes:
            raise POWLResourceLimit("Petri-net node bound exceeded")
        name = f"powl:p:{len(places)}"
        places.append(Place(name))
        return name

    def step(
        inputs: tuple[str, ...], outputs: tuple[str, ...], label: str | None = None
    ) -> None:
        if len(places) + len(transitions) >= spec.max_net_nodes:
            raise POWLResourceLimit("Petri-net node bound exceeded")
        if len(arcs) + len(inputs) + len(outputs) > spec.max_net_arcs:
            raise POWLResourceLimit("Petri-net arc bound exceeded")
        name = f"powl:t:{len(transitions)}"
        transitions.append(Transition(name, label))
        arcs.extend(Arc(p, name) for p in inputs)
        arcs.extend(Arc(name, p) for p in outputs)

    def build(node: POWLNode, source: str, sink: str) -> None:
        if node.kind in ("activity", "tau"):
            step((source,), (sink,), node.activity)
            return
        boundaries = tuple((place(), place()) for _ in node.children)
        for child, (start, end) in zip(node.children, boundaries):
            build(child, start, end)
        if node.kind == "xor":
            for start, end in boundaries:
                step((source,), (start,))
                step((end,), (sink,))
        elif node.kind == "loop":
            (do_start, do_end), (redo_start, redo_end) = boundaries
            step((source,), (do_start,))
            step((do_end,), (sink,))
            step((do_end,), (redo_start,))
            step((redo_end,), (do_start,))
        else:
            size = len(boundaries)
            permissions = tuple(place() for _ in range(size))
            completed = tuple(place() for _ in range(size))
            # Using all closure edges remains language-equivalent and avoids a
            # cubic transitive-reduction pass. Every edge token is consumed.
            edges = {(a, b): place() for a, b in node.order}
            incoming: dict[int, list[str]] = defaultdict(list)
            outgoing: dict[int, list[str]] = defaultdict(list)
            for (a, b), edge_place in edges.items():
                incoming[b].append(edge_place)
                outgoing[a].append(edge_place)
            step((source,), permissions)
            for i, (start, end) in enumerate(boundaries):
                step((permissions[i], *incoming[i]), (start,))
                step((end,), (completed[i], *outgoing[i]))
            step(completed, (sink,))

    source, sink = place(), place()
    build(model, source, sink)
    return PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking(((source, 1),)),
        Marking(((sink, 1),)),
    )


@dataclass(frozen=True, slots=True)
class POWLDiscoverySpec:
    """Discovery bounds and profile; infer_repetition affects observed_order only."""

    variant: Literal["observed_order", "exact_variants"] = "observed_order"
    infer_repetition: bool = True
    max_traces: int = 100_000
    max_events: int = 1_000_000
    max_order_checks: int = 2_000_000
    conversion: POWLConversionSpec = POWLConversionSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.variant not in ("observed_order", "exact_variants"):
            raise ValueError("unsupported PIX POWL discovery profile")
        if type(self.infer_repetition) is not bool:
            raise TypeError("infer_repetition must be boolean")
        if not isinstance(self.conversion, POWLConversionSpec):
            raise TypeError("conversion must be POWLConversionSpec")
        for name in ("max_traces", "max_events", "max_order_checks"):
            _positive(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class POWLBranchEvidence:
    rule: Literal["exact_word", "common_precedence", "primitive_repetition"]
    observed_variants: tuple[tuple[str, ...], ...]
    activities: tuple[str, ...]
    order: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class POWLDiscovery:
    model: POWLNode
    petri_net: PetriNet
    profile: str
    trace_count: int
    variant_count: int
    branches: tuple[POWLBranchEvidence, ...]
    order_checks: int
    model_node_count: int
    generalization_rules: tuple[str, ...]


def _word(word: tuple[str, ...]) -> POWLNode:
    children = tuple(POWLNode("activity", a) for a in word)
    if not children:
        return POWLNode("tau")
    if len(children) == 1:
        return children[0]
    return POWLNode(
        "partial_order",
        children=children,
        order=tuple((i, i + 1) for i in range(len(children) - 1)),
    )


def _primitive(word: tuple[str, ...]) -> tuple[str, ...]:
    """Linear prefix-function primitive root; no substring-period enumeration."""
    if not word:
        return word
    prefix = [0] * len(word)
    for i in range(1, len(word)):
        j = prefix[i - 1]
        while j and word[i] != word[j]:
            j = prefix[j - 1]
        if word[i] == word[j]:
            j += 1
        prefix[i] = j
    length = len(word) - prefix[-1]
    return word[:length] if len(word) % length == 0 else word


def discover_powl(
    log: CaseInput,
    spec: POWLDiscoverySpec = POWLDiscoverySpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[POWLDiscovery]:
    """Discover an explicit POWL profile with complete observed-language cover.

    No traces means unavailable, not an invented empty process. Empty traces
    are retained as tau branches. Frequency is recorded but does not filter
    behavior. A bound aborts the complete discovery; no truncated model is
    presented as a successful result.
    """
    if not isinstance(spec, POWLDiscoverySpec):
        raise TypeError("spec must be POWLDiscoverySpec")
    parent = as_case_traces(log, trace_spec)

    def result(status, value=None, issues=()):
        return _derived_result(
            "pix.case_centric.discover_powl",
            parent.source_digest,
            spec,
            status,
            value,
            parent.issues + issues,
            parent_computation_ids=(parent.computation_id,)
            if parent.computation_id
            else (),
        )

    if parent.value is None:
        return result(parent.status)
    traces = parent.value.traces
    if not traces:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "no_traces", "POWL discovery requires at least one observed case"
                ),
            ),
        )
    if (
        len(traces) > spec.max_traces
        or sum(len(t.events) for t in traces) > spec.max_events
    ):
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "powl_input_limit", "Trace or event bound exceeded before discovery"
                ),
            ),
        )
    words = tuple(sorted({tuple(e.activity for e in trace.events) for trace in traces}))
    branches: list[POWLNode] = []
    evidence: list[POWLBranchEvidence] = []
    generalizations: set[str] = set()
    checks = 0
    built_nodes = 0

    def reserve(nodes: int) -> None:
        nonlocal built_nodes
        built_nodes += nodes
        if built_nodes > spec.conversion.max_model_nodes:
            raise POWLResourceLimit(
                "POWL model node bound exceeded while building branches"
            )

    def word_node(word):
        reserve(len(word) + 1 if len(word) > 1 else 1)
        # Every strict sequence pair becomes a relation place with two arcs.
        # Check before constructing its quadratic transitive closure.
        if len(word) * (len(word) - 1) > spec.conversion.max_net_arcs:
            raise POWLResourceLimit("Sequence relation exceeds Petri-net arc bound")
        return _word(word)

    def exact(word):
        branches.append(word_node(word))
        evidence.append(POWLBranchEvidence("exact_word", (word,), word))

    try:
        if spec.variant == "exact_variants":
            for word in words:
                exact(word)
        else:
            remaining = set(words)
            if spec.infer_repetition:
                roots: dict[tuple[str, ...], list[tuple[str, ...]]] = defaultdict(list)
                for word in words:
                    if word:
                        roots[_primitive(word)].append(word)
                for root, group in sorted(roots.items()):
                    if any(len(word) > len(root) for word in group):
                        reserve(2)
                        branches.append(
                            POWLNode(
                                "loop", children=(word_node(root), POWLNode("tau"))
                            )
                        )
                        evidence.append(
                            POWLBranchEvidence(
                                "primitive_repetition", tuple(group), root
                            )
                        )
                        generalizations.add("positive_primitive_repetition")
                        remaining.difference_update(group)
            groups: dict[tuple[str, ...], list[tuple[str, ...]]] = defaultdict(list)
            for word in sorted(remaining):
                if word and len(word) == len(set(word)):
                    groups[tuple(sorted(word))].append(word)
                else:
                    exact(word)
            for alphabet, group in sorted(groups.items()):
                if len(group) == 1:
                    exact(group[0])
                    continue
                required_checks = len(group) * len(alphabet) * (len(alphabet) - 1)
                if checks + required_checks > spec.max_order_checks:
                    raise POWLResourceLimit(
                        "Common-precedence comparison bound exceeded"
                    )
                checks += required_checks
                positions = [{a: i for i, a in enumerate(word)} for word in group]
                order = tuple(
                    (i, j)
                    for i, a in enumerate(alphabet)
                    for j, b in enumerate(alphabet)
                    if i != j and all(p[a] < p[b] for p in positions)
                )
                reserve(len(alphabet) + 1)
                branches.append(
                    POWLNode(
                        "partial_order",
                        children=tuple(POWLNode("activity", a) for a in alphabet),
                        order=order,
                    )
                )
                evidence.append(
                    POWLBranchEvidence(
                        "common_precedence", tuple(group), alphabet, order
                    )
                )
                generalizations.add("linear_extensions_of_common_precedence")
        model = (
            branches[0]
            if len(branches) == 1
            else POWLNode("xor", children=tuple(branches))
        )
        node_count = _shape(model, spec.conversion)
        net = powl_to_petri_net(model, spec.conversion)
    except POWLResourceLimit as exc:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(ComputeIssue("powl_resource_limit", str(exc)),),
        )
    payload = POWLDiscovery(
        model,
        net,
        f"pix.powl.{spec.variant}.v1",
        len(traces),
        len(words),
        tuple(evidence),
        checks,
        node_count,
        tuple(sorted(generalizations)),
    )
    status = (
        ComputeStatus.PARTIAL
        if parent.status is ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED
    )
    return result(
        status,
        payload,
        (
            ComputeIssue(
                "powl_profile",
                "PIX discovery profile; upstream discovery-variant equivalence and log completeness are not certified",
            ),
        ),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_powl": (
        "powl_discovery",
        POWLDiscoverySpec,
        POWLDiscovery,
    ),
}

__all__ = (
    "POWLNode",
    "POWLConversionSpec",
    "POWLResourceLimit",
    "POWLDiscoverySpec",
    "POWLBranchEvidence",
    "POWLDiscovery",
    "powl_to_petri_net",
    "discover_powl",
)
