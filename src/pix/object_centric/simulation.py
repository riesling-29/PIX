"""Native OCPN and causal-net playout over an explicit finite object universe.

Exhaustive mode enumerates firing paths, retaining object identity and silent
steps. Sampled mode chooses uniformly among *concrete enabled bindings*, not
uniformly among transition names. Bounds never turn an unfinished run into an
accepted run or a deadlock. In particular a silent loop can have a later exit.

The payload is simulation evidence, not an OCEL: the model provides neither
timestamps nor E2O qualifiers, so these facts are not invented. Event IDs are
local to a run. Objects are declared by the model and cannot be created here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from random import Random
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.compute.model_semantics import fire_binding, model_digest
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.contracts.models import Binding, ObjectCentricPetriNet, ObjectMarking
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.models import (
    CausalFiring,
    ObjectCentricCausalNet,
    causal_firing_objects,
    causal_net_digest,
    enumerate_enabled_causal_bindings,
    fire_causal_binding,
)

OBJECT_PLAYOUT_OPERATOR_ID = "pix.object_centric.playout_ocpn"
CAUSAL_PLAYOUT_OPERATOR_ID = "pix.object_centric.playout_causal_net"


@dataclass(frozen=True, slots=True)
class ObjectPlayoutSpec:
    """Path bounds; max_states counts initial and fired marking occurrences.

    max_silent_steps limits consecutive silent steps and resets after a visible
    event. An accepting marking terminates immediately, even if it has outgoing
    bindings. A binding cap truncates exhaustive enumeration; sampled mode
    stops instead of sampling from a biased prefix of the enabled bindings.
    """

    SPEC_TYPE: ClassVar[str] = "pix.object_playout.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    mode: str = "sampled"
    seed: int = 0
    samples: int = 100
    max_states: int = 10000
    max_visible_events: int = 100
    max_steps: int = 1000
    max_silent_steps: int = 100
    max_bindings_per_marking: int = 1000

    def __post_init__(self) -> None:
        if self.mode not in ("sampled", "exhaustive"):
            raise ValueError("mode must be sampled or exhaustive")
        for name in (
            "seed",
            "samples",
            "max_states",
            "max_visible_events",
            "max_steps",
            "max_silent_steps",
            "max_bindings_per_marking",
        ):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"{name} must be an integer")
            minimum = 0 if name in ("max_visible_events", "max_silent_steps") else 1
            if name != "seed" and value < minimum:
                raise ValueError(f"{name} must be at least {minimum}")


@dataclass(frozen=True, slots=True)
class ObjectPlayoutStep:
    index: int
    binding: Binding
    activity: str | None
    before: ObjectMarking
    after: ObjectMarking
    event_id: str | None
    event_objects: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ObjectPlayoutRun:
    """A terminal run or an explicitly unfinished prefix.

    Outcomes: accepted, deadlock, state_limit, step_limit, visible_limit,
    silent_limit, binding_limit, candidate_limit. A blocked binding has not been fired.
    omitted_binding_count is an exact local omitted count, or None when a
    candidate-search cutoff prevents counting; it never counts all unseen
    descendants. Different run IDs can share the same prefix.
    """

    run_id: str
    outcome: str
    steps: tuple[ObjectPlayoutStep, ...]
    final_marking: ObjectMarking
    visible_event_count: int
    blocked_binding: Binding | None = None
    omitted_binding_count: int | None = 0


@dataclass(frozen=True, slots=True)
class ObjectPlayout:
    mode: str
    choice_profile: str
    objects: tuple[tuple[str, str], ...]
    runs: tuple[ObjectPlayoutRun, ...]
    generated_states: int
    requested_samples: int | None
    unstarted_samples: int
    accepted_count: int
    deadlock_count: int
    cutoff_count: int
    enumeration_complete: bool
    sampling_complete: bool


@dataclass(frozen=True, slots=True)
class CausalPlayoutSpec(ObjectPlayoutSpec):
    """Genuine marker-group causal firing, with bounded candidate examination."""

    SPEC_TYPE: ClassVar[str] = "pix.causal_playout.spec"
    max_candidates_per_marking: int = 100000

    def __post_init__(self) -> None:
        ObjectPlayoutSpec.__post_init__(self)
        if not isinstance(self.max_candidates_per_marking, int) or isinstance(
            self.max_candidates_per_marking, bool
        ):
            raise TypeError("max_candidates_per_marking must be an integer")
        if self.max_candidates_per_marking < 1:
            raise ValueError("max_candidates_per_marking must be positive")


@dataclass(frozen=True, slots=True)
class CausalPlayoutStep(ObjectPlayoutStep):
    binding: CausalFiring


@dataclass(frozen=True, slots=True)
class CausalPlayoutRun(ObjectPlayoutRun):
    steps: tuple[CausalPlayoutStep, ...]
    blocked_binding: CausalFiring | None = None


@dataclass(frozen=True, slots=True)
class CausalPlayout(ObjectPlayout):
    runs: tuple[CausalPlayoutRun, ...]


@dataclass(frozen=True, slots=True)
class _Node:
    marking: ObjectMarking
    steps: tuple[ObjectPlayoutStep, ...] = ()
    visible: int = 0
    silent: int = 0


def playout_ocpn(
    net: ObjectCentricPetriNet,
    spec: ObjectPlayoutSpec = ObjectPlayoutSpec(),
) -> ComputationResult[ObjectPlayout]:
    """Enumerate or sample native OCPN runs with exact binding evidence.

    COMPUTED in sampled mode means all requested sampled runs terminated; it
    does not certify language coverage. exhaustive enumeration_complete is
    true only when every reachable path terminated without any cutoff. These
    semantics use exact final marking equality, including residual tokens.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be an ObjectCentricPetriNet")
    if type(spec) is not ObjectPlayoutSpec:
        raise TypeError("spec must be an ObjectPlayoutSpec")

    def enumerate_choices(marking):
        return enumerate_enabled_bindings(
            net,
            marking,
            max_bindings=spec.max_bindings_per_marking,
        )

    def participation(binding):
        return tuple(
            sorted(
                (object_id, object_type)
                for object_type, object_ids in binding.objects
                for object_id in object_ids
            )
        )

    return _execute_playout(
        net,
        spec,
        enumerate_choices,
        lambda marking, binding: fire_binding(net, marking, binding),
        participation,
        ObjectPlayoutStep,
        ObjectPlayoutRun,
        ObjectPlayout,
        OBJECT_PLAYOUT_OPERATOR_ID,
        model_digest(net),
    )


def playout_causal_net(
    net: ObjectCentricCausalNet,
    spec: CausalPlayoutSpec = CausalPlayoutSpec(),
) -> ComputationResult[CausalPlayout]:
    """Playout native causal obligations and alternative marker-group firings.

    No OCPN conversion is involved. Consumption and production retain each
    channel selection and chosen input/output alternative. Candidate-search
    exhaustion is explicitly unknown, including when no enabled binding was
    found before the budget. The explicit initial and final obligation markings
    are authoritative; no activity-name START_/END_ convention is inferred.
    """
    if not isinstance(net, ObjectCentricCausalNet):
        raise TypeError("net must be an ObjectCentricCausalNet")
    if type(spec) is not CausalPlayoutSpec:
        raise TypeError("spec must be a CausalPlayoutSpec")

    def enumerate_choices(marking):
        return enumerate_enabled_causal_bindings(
            net,
            marking,
            max_bindings=spec.max_bindings_per_marking,
            max_candidates=spec.max_candidates_per_marking,
        )

    return _execute_playout(
        net,
        spec,
        enumerate_choices,
        lambda marking, binding: fire_causal_binding(net, marking, binding),
        lambda binding: causal_firing_objects(net, binding),
        CausalPlayoutStep,
        CausalPlayoutRun,
        CausalPlayout,
        CAUSAL_PLAYOUT_OPERATOR_ID,
        causal_net_digest(net),
    )


def _execute_playout(
    net,
    spec,
    enumerate_choices,
    fire_choice,
    participation,
    step_contract,
    run_contract,
    payload_contract,
    operator_id,
    source_digest,
):
    """Shared bounded traversal; model-specific binding semantics stay separate."""
    labels = {transition.id: transition.activity for transition in net.transitions}
    rng = Random(spec.seed)
    runs: list[ObjectPlayoutRun] = []
    generated = 0
    unstarted = 0

    def finish(
        node: _Node,
        outcome: str,
        blocked=None,
        omitted: int | None = 0,
    ) -> None:
        runs.append(
            run_contract(
                f"run:{len(runs):06d}",
                outcome,
                node.steps,
                node.marking,
                node.visible,
                blocked,
                omitted,
            )
        )

    repetitions = spec.samples if spec.mode == "sampled" else 1
    for repetition in range(repetitions):
        if generated >= spec.max_states:
            unstarted = repetitions - repetition
            break
        generated += 1
        pending = [_Node(net.initial_marking)]
        while pending:
            node = pending.pop()
            if node.marking == net.final_marking:
                finish(node, "accepted")
                continue
            enabled = enumerate_choices(node.marking)
            if enabled.candidate_count == 0 and enabled.complete:
                finish(node, "deadlock")
                continue
            if len(node.steps) >= spec.max_steps:
                finish(node, "step_limit", omitted=enabled.candidate_count)
                continue
            if not enabled.complete:
                if enabled.candidate_count is None:
                    finish(node, "candidate_limit", omitted=None)
                else:
                    finish(
                        node,
                        "binding_limit",
                        omitted=(
                            enabled.candidate_count
                            if spec.mode == "sampled"
                            else enabled.candidate_count - len(enabled.bindings)
                        ),
                    )
                if spec.mode == "sampled":
                    continue
            bindings = enabled.bindings
            if spec.mode == "sampled":
                bindings = (rng.choice(bindings),)
            children = []
            for position, binding in enumerate(bindings):
                activity = labels[binding.transition_id]
                if activity is not None and node.visible >= spec.max_visible_events:
                    finish(node, "visible_limit", binding, 1)
                    continue
                if activity is None and node.silent >= spec.max_silent_steps:
                    finish(node, "silent_limit", binding, 1)
                    continue
                if generated >= spec.max_states:
                    finish(node, "state_limit", omitted=len(bindings) - position)
                    break
                following = fire_choice(node.marking, binding)
                event_objects = participation(binding) if activity is not None else ()
                step = step_contract(
                    len(node.steps),
                    binding,
                    activity,
                    node.marking,
                    following,
                    f"e{node.visible:06d}" if activity is not None else None,
                    event_objects,
                )
                children.append(
                    _Node(
                        following,
                        node.steps + (step,),
                        node.visible + (activity is not None),
                        node.silent + 1 if activity is None else 0,
                    )
                )
                generated += 1
            pending.extend(reversed(children))

    outcomes = Counter(run.outcome for run in runs)
    cutoffs = sum(
        count
        for outcome, count in outcomes.items()
        if outcome not in ("accepted", "deadlock")
    )
    issues = tuple(
        ComputeIssue(
            f"object_playout_{outcome}",
            f"{count} run prefixes stopped at {outcome}; successors are unknown",
        )
        for outcome, count in sorted(outcomes.items())
        if outcome not in ("accepted", "deadlock")
    )
    if unstarted:
        issues += (
            ComputeIssue(
                "object_playout_unstarted_samples",
                f"{unstarted} requested samples were not started because max_states was reached",
            ),
        )
    payload = payload_contract(
        spec.mode,
        "uniform_concrete_enabled_binding"
        if spec.mode == "sampled"
        else "all_concrete_paths",
        net.objects,
        tuple(runs),
        generated,
        spec.samples if spec.mode == "sampled" else None,
        unstarted,
        outcomes["accepted"],
        outcomes["deadlock"],
        cutoffs,
        spec.mode == "exhaustive" and not issues,
        spec.mode == "sampled" and not issues,
    )
    return _derived_result(
        operator_id,
        source_digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        issues,
    )


RESULT_SCHEMAS = {
    OBJECT_PLAYOUT_OPERATOR_ID: ("object-playout", ObjectPlayoutSpec, ObjectPlayout),
    CAUSAL_PLAYOUT_OPERATOR_ID: ("causal-playout", CausalPlayoutSpec, CausalPlayout),
}

__all__ = (
    "ObjectPlayoutSpec",
    "ObjectPlayoutStep",
    "ObjectPlayoutRun",
    "ObjectPlayout",
    "playout_ocpn",
    "OBJECT_PLAYOUT_OPERATOR_ID",
    "CausalPlayoutSpec",
    "CausalPlayoutStep",
    "CausalPlayoutRun",
    "CausalPlayout",
    "playout_causal_net",
    "CAUSAL_PLAYOUT_OPERATOR_ID",
)
