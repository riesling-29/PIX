"""Explicit model-family capabilities, separate from persistence registration.

Entries describe this PIX release's APIs, not promises for every instance.
``via_conversion`` requires the named conversion to succeed; callers must inspect
its status and resource limits. No implicit conversion or dependency fallback is
performed. A persisted stochastic/declarative model is not thereby executable
by ordinary Petri-net algorithms. Entry points are import paths, never evaluated
from input or persisted data.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Literal

Support = Literal["direct", "via_conversion", "unsupported"]


@dataclass(frozen=True, slots=True)
class ModelOperationCapability:
    support: Support
    entrypoints: tuple[str, ...] = ()
    conversion_entrypoints: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    model_kind: str
    python_type: str
    semantic_profile: str
    persistence: ModelOperationCapability
    activity_labels: ModelOperationCapability
    firing: ModelOperationCapability
    conversion: ModelOperationCapability
    alignment: ModelOperationCapability
    reachability: ModelOperationCapability
    analysis_entrypoints: tuple[str, ...] = ()


def _direct(*paths, limitations=()):
    return ModelOperationCapability("direct", paths, (), limitations)


def _unsupported(*limitations):
    return ModelOperationCapability("unsupported", limitations=limitations)


def _via(operation, *conversions, limitations=()):
    return ModelOperationCapability(
        "via_conversion",
        operation.entrypoints,
        conversions,
        operation.limitations + limitations,
    )


_PERSISTENCE = _direct(
    "pix.models.model_document",
    "pix.models.write_model",
    "pix.models.read_model",
    limitations=(
        "Native PIX JSON; persistence does not certify soundness or execution support.",
    ),
)
_LABELS = _direct(
    "pix.case_centric.model_labels.activity_labels",
    "pix.case_centric.model_labels.rename_activity_labels",
    limitations=(
        "Occurrence IDs are retained; changing labels changes visible behavior.",
    ),
)
_NO_LABELS = _unsupported(
    "No occurrence-safe activity-label adapter for this model family."
)
_PN_FIRING = _direct("pix.compute.model_semantics.fire")
_PN_ALIGNMENT = _direct(
    "pix.case_centric.execution.align_traces",
    limitations=(
        "Weighted P/T semantics; bounded search may return partial/unavailable evidence.",
    ),
)
_PN_REACHABILITY = _direct(
    "pix.case_centric.model_analysis.reachability",
    limitations=(
        "Exact finite graph only when the frontier is exhausted; caps are not unboundedness proofs.",
    ),
)
_OC_FIRING = _direct(
    "pix.compute.model_semantics.fire_binding",
    limitations=(
        "Unit-incidence object bindings and the declared finite object universe.",
    ),
)
_OC_ALIGNMENT = _direct(
    "pix.compute.object_conformance.align_object_log",
    limitations=(
        "Joint bindings under finite object universe and explicit search budgets.",
    ),
)
_OC_REACHABILITY = _direct(
    "pix.object_centric.models.analyze_ocpn_soundness",
    limitations=(
        "Returns object marking/edge evidence; complete only if bounded frontier is exhausted.",
    ),
)
_NO_EXECUTION = _unsupported(
    "This family has no native firing, alignment or reachability API."
)
_NO_CONVERSION = _unsupported(
    "No supported conversion API for this family; extracting a base model need not preserve all semantics."
)


def _row(
    kind,
    path,
    profile,
    *,
    labels=_NO_LABELS,
    firing=_NO_EXECUTION,
    conversion=_NO_CONVERSION,
    alignment=_NO_EXECUTION,
    reachability=_NO_EXECUTION,
    analysis=(),
):
    return ModelCapabilities(
        kind,
        path,
        profile,
        _PERSISTENCE,
        labels,
        firing,
        conversion,
        alignment,
        reachability,
        analysis,
    )


_TREE_PN = "pix.compute.discovery.process_tree_to_petri_net"
_HEURISTICS_PN = "pix.case_centric.heuristics_conversion.heuristics_to_petri_net"
_POWL_PN = "pix.case_centric.powl.powl_to_petri_net"
_BPMN_PN = "pix.case_centric.bpmn_conversion.bpmn_to_petri_net"
_CAUSAL_OC = "pix.object_centric.models.causal_net_to_ocpn"
_CAUSAL_LIMIT = (
    "Only representable channel groups; independent/disjoint selections may be refused.",
)
_CONVERSION_LIMIT = (
    "Explicit conversion must succeed within its supported profile and resource limits.",
)

_CATALOG = (
    _row(
        "petri-net",
        "pix.contracts.models.PetriNet",
        "weighted-place-transition",
        labels=_LABELS,
        firing=_PN_FIRING,
        conversion=_direct(
            "pix.case_centric.wfnet_conversion.wfnet_to_process_tree",
            limitations=(
                "Restricted reducible workflow-net conversion; unsupported instances are refused.",
            ),
        ),
        alignment=_PN_ALIGNMENT,
        reachability=_PN_REACHABILITY,
    ),
    _row(
        "object-centric-petri-net",
        "pix.contracts.models.ObjectCentricPetriNet",
        "unit-incidence-concrete-object-universe",
        labels=_LABELS,
        firing=_OC_FIRING,
        conversion=_direct(
            "pix.object_centric.models.ocpn_to_causal_net",
            "pix.object_centric.model_integration.decompose_ocpn",
            limitations=(
                "Causal conversion is profile-limited. Per-type decomposition needs its synchronization ledger for reconstruction.",
            ),
        ),
        alignment=_OC_ALIGNMENT,
        reachability=_OC_REACHABILITY,
    ),
    _row(
        "process-tree",
        "pix.contracts.discovery.ProcessTree",
        "block-structured-tree",
        labels=_LABELS,
        firing=_via(_PN_FIRING, _TREE_PN),
        conversion=_direct(
            _TREE_PN,
            "pix.case_centric.model_conversion.tree_to_powl",
            "pix.case_centric.model_conversion.tree_to_bpmn",
        ),
        alignment=_direct(
            "pix.case_centric.tree_alignment.align_process_tree_dp",
            limitations=(
                "Native bounded tree DP; loop and state budgets remain explicit.",
            ),
        ),
        reachability=_via(_PN_REACHABILITY, _TREE_PN),
    ),
    _row(
        "heuristics-net",
        "pix.case_centric.heuristics.HeuristicsNet",
        "pix.heuristics-net.v1",
        firing=_via(_PN_FIRING, _HEURISTICS_PN, limitations=_CONVERSION_LIMIT),
        conversion=_direct(
            _HEURISTICS_PN,
            limitations=(
                "Explicit XOR-of-AND bindings; frequencies are not stochastic weights.",
            ),
        ),
        alignment=_via(_PN_ALIGNMENT, _HEURISTICS_PN, limitations=_CONVERSION_LIMIT),
        reachability=_via(
            _PN_REACHABILITY, _HEURISTICS_PN, limitations=_CONVERSION_LIMIT
        ),
    ),
    _row(
        "footprint-model",
        "pix.case_centric.discovery.FootprintModel",
        "pix.observed-log-footprints.v1",
        analysis=("pix.case_centric.declarative.check_footprints",),
    ),
    _row(
        "transition-system",
        "pix.case_centric.discovery.TransitionSystem",
        "pix.observed-context-state-graph.v1",
        conversion=_direct(
            "pix.case_centric.trie_conversion.trie_to_petri_net",
            limitations=(
                "Only full-prefix tries with validated frequency conservation; general or windowed context graphs are refused. Frequencies remain evidence, not probabilities or arc weights.",
            ),
        ),
        reachability=_unsupported(
            "Observed context graph; merged contexts may introduce unobserved paths. No executable-model reachability API."
        ),
    ),
    _row(
        "declare-model",
        "pix.case_centric.declarative.DeclareModel",
        "pix.finite-trace-declare.v1",
        analysis=(
            "pix.case_centric.declarative.check_declare",
            "pix.case_centric.declarative_simulation.generate_declare_language",
        ),
        reachability=_unsupported(
            "Bounded finite-word generation exists but is not general reachability or an unbounded language proof."
        ),
    ),
    _row(
        "log-skeleton",
        "pix.case_centric.declarative.LogSkeleton",
        "pix.activation-log-skeleton.v1",
        analysis=("pix.case_centric.declarative.check_log_skeleton",),
    ),
    _row(
        "temporal-profile",
        "pix.case_centric.declarative.TemporalProfile",
        "pix.occurrence-temporal-profile.v1",
        analysis=("pix.case_centric.declarative.check_temporal_profile",),
    ),
    _row(
        "powl",
        "pix.case_centric.powl.POWLNode",
        "pix.original-powl.v1",
        labels=_LABELS,
        firing=_via(_PN_FIRING, _POWL_PN, limitations=_CONVERSION_LIMIT),
        conversion=_direct(
            _POWL_PN,
            limitations=(
                "Original POWL activity/tau/XOR/loop/partial-order profile, not choice graphs.",
            ),
        ),
        alignment=_via(_PN_ALIGNMENT, _POWL_PN, limitations=_CONVERSION_LIMIT),
        reachability=_via(_PN_REACHABILITY, _POWL_PN, limitations=_CONVERSION_LIMIT),
    ),
    _row(
        "bpmn-control-flow",
        "pix.case_centric.split_miner.SplitBPMN",
        "pix.xor-and-bpmn.v1",
        labels=_LABELS,
        firing=_via(_PN_FIRING, _BPMN_PN, limitations=_CONVERSION_LIMIT),
        conversion=_direct(
            _BPMN_PN,
            limitations=(
                "XOR/AND and plain atomic tasks/events; no message, condition, timer or inclusive-gateway semantics.",
            ),
        ),
        alignment=_via(_PN_ALIGNMENT, _BPMN_PN, limitations=_CONVERSION_LIMIT),
        reachability=_via(_PN_REACHABILITY, _BPMN_PN, limitations=_CONVERSION_LIMIT),
    ),
    _row(
        "object-centric-causal-net",
        "pix.object_centric.models.ObjectCentricCausalNet",
        "pix.finite_object_obligation_net.v1",
        firing=_direct("pix.object_centric.models.fire_causal_binding"),
        conversion=_direct(_CAUSAL_OC, limitations=_CAUSAL_LIMIT),
        alignment=_via(_OC_ALIGNMENT, _CAUSAL_OC, limitations=_CAUSAL_LIMIT),
        reachability=_via(_OC_REACHABILITY, _CAUSAL_OC, limitations=_CAUSAL_LIMIT),
    ),
    _row(
        "stochastic-arc-weight-net",
        "pix.object_centric.discovery.StochasticArcWeightNet",
        "pix.observed_saw.v1",
        firing=_unsupported(
            "Empirical arc marginals are not a stochastic firing law. Extracting .model exposes only its ordinary OCPN behavior."
        ),
        alignment=_unsupported(
            "Underlying OCPN alignment ignores empirical arc distributions; no distribution-aware alignment API."
        ),
        reachability=_unsupported(
            "Underlying OCPN analysis is not probabilistic reachability for the SAW model."
        ),
    ),
    _row(
        "data-petri-net",
        "pix.case_centric.decision_mining.DataPetriNet",
        "pix.typed-numeric-decision-guards.v1",
        firing=_direct(
            "pix.case_centric.decision_mining.fire_data_transition",
            limitations=(
                "Numeric feature guards; missing/unknown inputs do not enable firing.",
            ),
        ),
        alignment=_unsupported(
            "Extracting .base discards guards. Ordinary PN alignment is not guarded alignment."
        ),
        reachability=_unsupported(
            "No data-state reachability API; ordinary PN reachability discards guards."
        ),
        analysis=("pix.case_centric.decision_mining.evaluate_data_guards",),
    ),
    _row(
        "reset-inhibitor-net",
        "pix.case_centric.extended_nets.ResetInhibitorNet",
        "pix.exclusive-input-reset-inhibitor.v1",
        firing=_direct(
            "pix.case_centric.extended_nets.fire_reset_inhibitor",
            limitations=(
                "Pre-marking inhibitors; consume ordinary inputs, reset places, then produce outputs.",
            ),
        ),
        alignment=_unsupported(
            "Ordinary P/T alignment does not implement reset/inhibitor semantics."
        ),
        reachability=_unsupported(
            "Ordinary P/T reachability rejects this model; extracting .base would discard special arcs."
        ),
    ),
    _row(
        "stochastic-petri-net",
        "pix.case_centric.extended_nets.StochasticPetriNet",
        "pix.weighted-choice-serial-duration.v1",
        firing=_direct(
            "pix.case_centric.extended_nets.sample_stochastic_step",
            limitations=(
                "This step API samples relative enabled-transition weights and serial durations; concurrent reservation timing is a separate playout profile, not GSPN race/priority semantics.",
            ),
        ),
        alignment=_unsupported(
            "No probability/time-aware alignment; ordinary base-net alignment omits stochastic annotations."
        ),
        reachability=_unsupported(
            "No stochastic reachability or CTMC solver; ordinary base-net reachability omits probability and time."
        ),
        analysis=(
            "pix.case_centric.extended_nets.stochastic_transition_probabilities",
            "pix.case_centric.timed_playout.playout_timed_petri_net",
        ),
    ),
)


def list_model_capabilities() -> tuple[ModelCapabilities, ...]:
    """Return immutable declarations for the model families of this release."""
    return _CATALOG


def model_capabilities(model_or_type: object) -> ModelCapabilities:
    """Look up an exact PIX model type or instance; never infer from field shape.

    ``ModelArtifact`` is unwrapped without changing its model. Subclasses and
    look-alike external dataclasses are deliberately not accepted. Model modules
    are imported lazily, keeping this catalog safe for codec registration.
    """
    from pix.models import ModelArtifact

    if isinstance(model_or_type, ModelArtifact):
        model_or_type = model_or_type.model
    kind = model_or_type if isinstance(model_or_type, type) else type(model_or_type)
    path = f"{kind.__module__}.{kind.__qualname__}"
    for row in _CATALOG:
        if row.python_type == path:
            module, name = path.rsplit(".", 1)
            if getattr(import_module(module), name) is kind:
                return row
    raise TypeError("model has no explicitly registered capability contract")


__all__ = [
    "ModelCapabilities",
    "ModelOperationCapability",
    "list_model_capabilities",
    "model_capabilities",
]
