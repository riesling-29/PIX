"""Native BPMN control-flow to accepting Petri-net conversion.

The supported source is the existing ``SplitBPMN`` XOR/AND profile: one plain
start/end event, explicitly directed exclusive/parallel gateways, and tasks
with one incoming/outgoing sequence flow. XOR chooses one outgoing edge and
merges each incoming token independently; AND creates/consumes one token on
every incident edge. Activities execute atomically. Duplicate activity labels
keep distinct transition identities. Cycles are retained without unfolding.

One source token starts a single process instance. Acceptance requires exactly
one sink token and no leftover tokens. A connected graph may still deadlock,
leave tokens, or be unbounded: conversion does not certify soundness or fitness.
No inclusive/event gateways, conditions, subprocesses, interrupting events,
message/data/time semantics, or multi-instance tasks are inferred. These
features cannot be represented by SplitBPMN and are rejected by its contract.

The PM4Py 2.7.23.8 BPMN converter was inspected for scope. This implementation
uses independent direct sequence-flow incidence, with deterministic IDs and
unreduced node/flow witnesses; no upstream package is imported or executed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pix.case_centric.split_miner import SplitBPMN
from pix.compute._common import _derived_result
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

OPERATOR_ID = "pix.case_centric.bpmn_to_petri_net"
PROFILE = "pix.xor-and-bpmn.token-flow.v1"


@dataclass(frozen=True, slots=True)
class BPMNConversionSpec:
    """Construction budgets; exceeding either returns no incomplete net."""

    max_net_nodes: int = 200_000
    max_net_arcs: int = 1_000_000
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.BPMNConversionSpec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for field in ("max_net_nodes", "max_net_arcs"):
            if type(getattr(self, field)) is not int or getattr(self, field) < 1:
                raise ValueError(f"{field} must be a positive integer")


@dataclass(frozen=True, slots=True)
class BPMNConversionRequest:
    """Input-model identity supplements an inherited source-log identity."""

    model_digest: str | None
    parameters: BPMNConversionSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.BPMNConversionRequest"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class BPMNFlowPlace:
    flow_id: str
    place_id: str


@dataclass(frozen=True, slots=True)
class BPMNNodeTransition:
    """One transition and its consumed/produced source-model flow IDs.

    Start/end transitions additionally touch the external source/sink place,
    respectively. Exclusive gateways have several rows; tasks have exactly one.
    """

    node_id: str
    transition_id: str
    incoming_flow_ids: tuple[str, ...]
    outgoing_flow_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BPMNConversion:
    model: PetriNet
    profile: str
    source_model_digest: str
    flow_places: tuple[BPMNFlowPlace, ...]
    node_transitions: tuple[BPMNNodeTransition, ...]
    soundness: str = "not_checked"
    reference_equivalence: str = "unverified"


def bpmn_to_petri_net(
    model: SplitBPMN | ComputationResult,
    spec: BPMNConversionSpec = BPMNConversionSpec(),
) -> ComputationResult[BPMNConversion]:
    """Compile explicit XOR/AND token-flow semantics without model discovery.

    A bare SplitBPMN or a computation containing it, directly or as ``.model``,
    is accepted. Parent identity/issues/status are retained; a PARTIAL source
    is never promoted to COMPUTED. Native model artifact digests include the
    original node and flow records; reordering input records changes that
    artifact identity, while the constructed net remains deterministic.
    """
    if not isinstance(spec, BPMNConversionSpec):
        raise TypeError("spec must be BPMNConversionSpec")
    parent = model if isinstance(model, ComputationResult) else None
    if parent is None and type(model) is not SplitBPMN:
        raise TypeError("model must be SplitBPMN or a computation containing it")
    source = parent.source_digest if parent is not None else None
    parents = (
        (parent.computation_id,) if parent is not None and parent.computation_id else ()
    )
    inherited = parent.issues if parent is not None else ()
    digest = None

    def result(status, value=None, issues=()):
        if (
            value is not None
            and status is ComputeStatus.COMPUTED
            and parent is not None
        ):
            if parent.status is ComputeStatus.PARTIAL:
                status = ComputeStatus.PARTIAL
        return _derived_result(
            OPERATOR_ID,
            source,
            BPMNConversionRequest(digest, spec),
            status,
            value,
            inherited + tuple(issues),
            parent_computation_ids=parents,
        )

    if parent is not None:
        if parent.value is None:
            return result(parent.status)
        model = parent.value
        if type(model) is not SplitBPMN:
            model = getattr(model, "model", None)
    if type(model) is not SplitBPMN:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_bpmn_model",
                    "Result must contain the native SplitBPMN control-flow model",
                ),
            ),
        )

    try:
        # The model codec revalidates all nested records and its graph contract;
        # it also rejects unsupported subclasses or forged mutable fields.
        from pix.models import model_document

        digest = model_document(model)["model_digest"]
        if parent is None:
            source = digest
    except (TypeError, ValueError, UnicodeError) as exc:
        return result(
            ComputeStatus.INVALID_INPUT,
            issues=(
                ComputeIssue(
                    "invalid_bpmn_model",
                    str(exc),
                ),
            ),
        )

    nodes = tuple(sorted(model.nodes, key=lambda node: node.id))
    flows = tuple(sorted(model.flows, key=lambda flow: flow.id))
    incoming = {node.id: [] for node in nodes}
    outgoing = {node.id: [] for node in nodes}
    for flow in flows:
        incoming[flow.target].append(flow.id)
        outgoing[flow.source].append(flow.id)

    transition_count, arc_count = 0, 0
    for node in nodes:
        before, after = incoming[node.id], outgoing[node.id]
        if node.kind == "exclusive_gateway":
            alternatives = len(after) if node.direction == "split" else len(before)
            transition_count += alternatives
            arc_count += 2 * alternatives
        else:
            transition_count += 1
            arc_count += len(before) + len(after) + int(node.kind.endswith("_event"))
    node_count = len(flows) + 2 + transition_count
    if node_count > spec.max_net_nodes or arc_count > spec.max_net_arcs:
        return result(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "bpmn_conversion_limit",
                    "Complete construction exceeds max_net_nodes or max_net_arcs; no partial net was returned",
                ),
            ),
        )

    source_place, sink_place = "b:p:source", "b:p:sink"
    place_ids = {flow.id: f"b:p:flow:{i}" for i, flow in enumerate(flows)}
    places = (
        Place(source_place),
        Place(sink_place),
        *(Place(p) for p in place_ids.values()),
    )
    transitions, arcs, witnesses = [], [], []

    for number, node in enumerate(nodes):
        before, after = tuple(incoming[node.id]), tuple(outgoing[node.id])
        if node.kind == "exclusive_gateway" and node.direction == "split":
            alternatives = tuple((before, (flow,)) for flow in after)
        elif node.kind == "exclusive_gateway":
            alternatives = tuple(((flow,), after) for flow in before)
        else:
            alternatives = ((before, after),)
        for alternative, (inputs, outputs) in enumerate(alternatives):
            transition_id = f"b:t:node:{number}:{alternative}"
            transitions.append(Transition(transition_id, node.activity))
            arcs.extend(Arc(place_ids[flow], transition_id) for flow in inputs)
            arcs.extend(Arc(transition_id, place_ids[flow]) for flow in outputs)
            if node.kind == "start_event":
                arcs.append(Arc(source_place, transition_id))
            elif node.kind == "end_event":
                arcs.append(Arc(transition_id, sink_place))
            witnesses.append(
                BPMNNodeTransition(node.id, transition_id, inputs, outputs)
            )

    net = PetriNet(
        tuple(places),
        tuple(transitions),
        tuple(arcs),
        Marking(((source_place, 1),)),
        Marking(((sink_place, 1),)),
    )
    payload = BPMNConversion(
        net,
        PROFILE,
        digest,
        tuple(BPMNFlowPlace(flow.id, place_ids[flow.id]) for flow in flows),
        tuple(witnesses),
    )
    return result(
        ComputeStatus.COMPUTED,
        payload,
        (
            ComputeIssue(
                "bpmn_token_flow_profile",
                "Explicit XOR/AND token-flow semantics were converted; soundness, boundedness, log fitness and upstream parity are not certified",
            ),
        ),
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("bpmn-conversion", BPMNConversionRequest, BPMNConversion),
}

__all__ = (
    "BPMNConversionSpec",
    "BPMNConversionRequest",
    "BPMNFlowPlace",
    "BPMNNodeTransition",
    "BPMNConversion",
    "bpmn_to_petri_net",
)
