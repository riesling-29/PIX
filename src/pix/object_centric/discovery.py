"""Observed stochastic arc-weight discovery over a verified native OCPN.

For a visible transition, every whole-log event with its activity is one sample,
including events with zero objects of an incident type. Different E2O qualifiers
do not multiply an object's participation. A silent transition is instead sampled
at each concrete silent step in the attached accepting binding witness; these
samples are witness dependent, not silently associated with a nearby event.

This profile differs from PM4Py's per-type token replay/event-ID aggregation.
Exact marginal frequencies are descriptive estimates, not independent arc choice
probabilities, a transition-selection policy, or generalized stochastic semantics.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from fractions import Fraction
from typing import ClassVar

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.ocpn_discovery import discover_ocpn
from pix.contracts.models import (
    ObjectCentricPetriNet,
    OCPNDiscoveryPayload,
    _integer,
    _text,
    _tuple,
)
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

OPERATOR_ID = "pix.object_centric.discover_saw_net"
PROFILE = "pix.observed_saw.v1"


@dataclass(frozen=True, slots=True)
class SAWDiscoverySpec:
    """Explicit discovery policies; only observed fitting witnesses are supported.

    The nested request makes the selected object universe, qualifier policy,
    ordering, local discovery algorithm, and search limits part of the result
    identity. Failure to establish its accepting witness prevents SAW discovery.
    """

    ocpn_spec: OCPNDiscoverySpec
    profile: str = PROFILE
    SPEC_TYPE: ClassVar[str] = "pix.observed_saw.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.ocpn_spec, OCPNDiscoverySpec):
            raise TypeError("ocpn_spec must be OCPNDiscoverySpec")
        if self.profile != PROFILE:
            raise ValueError(f"only {PROFILE} is supported")


@dataclass(frozen=True, slots=True)
class SAWArcWeightDistribution:
    """A finite empirical measure, with the exact sample denominator.

    Histogram entries are (arc weight, sample count), not min/max intervals.
    witness_indices refer to the enclosing discovery's fitting_witness. For a
    unit-incidence OCPN arc the weight is the number of distinct bound objects
    of the incident place type. No observations means an unknown distribution.
    """

    source: str
    target: str
    transition_id: str
    object_type: str
    sample_basis: str
    histogram: tuple[tuple[int, int], ...]
    sample_count: int
    witness_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        for name in ("source", "target", "transition_id", "object_type"):
            _text(getattr(self, name), name)
        if self.sample_basis not in ("activity_events", "silent_witness_steps"):
            raise ValueError("unsupported sample_basis")
        _integer(self.sample_count, "sample_count", minimum=0)
        _tuple(self.histogram, tuple, "histogram")
        weights = set()
        for row in self.histogram:
            if len(row) != 2:
                raise ValueError("histogram entries must be (weight, sample_count)")
            _integer(row[0], "weight", minimum=0)
            _integer(row[1], "weight sample_count")
            if row[0] in weights:
                raise ValueError("duplicate histogram weight")
            weights.add(row[0])
        if sum(count for _, count in self.histogram) != self.sample_count:
            raise ValueError("histogram denominator differs from sample_count")
        _tuple(self.witness_indices, int, "witness_indices")
        for index in self.witness_indices:
            _integer(index, "witness_index", minimum=0)
        if len(self.witness_indices) != self.sample_count:
            raise ValueError("witness sample count differs from denominator")
        if tuple(sorted(set(self.witness_indices))) != self.witness_indices:
            raise ValueError("witness_indices must be unique and ascending")
        object.__setattr__(self, "histogram", tuple(sorted(self.histogram)))

    @property
    def support(self) -> tuple[int, ...]:
        return tuple(weight for weight, _ in self.histogram)

    def probability(self, weight: int) -> Fraction | None:
        """Exact empirical mass; None denotes absence of observations."""
        _integer(weight, "weight", minimum=0)
        if not self.sample_count:
            return None
        return Fraction(dict(self.histogram).get(weight, 0), self.sample_count)

    @property
    def expected_weight(self) -> Fraction | None:
        if not self.sample_count:
            return None
        return Fraction(
            sum(weight * count for weight, count in self.histogram),
            self.sample_count,
        )


def _arc_distributions(
    discovery: OCPNDiscoveryPayload,
) -> tuple[SAWArcWeightDistribution, ...]:
    model = discovery.model
    place_types = {place.id: place.object_type for place in model.places}
    activities = {
        transition.id: transition.activity for transition in model.transitions
    }
    indices: dict[str, list[int]] = defaultdict(list)
    counts: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
    for index, step in enumerate(discovery.fitting_witness):
        transition = step.binding.transition_id
        indices[transition].append(index)
        for object_type, object_ids in step.binding.objects:
            counts[transition, object_type][len(object_ids)] += 1
    distributions = []
    for arc in model.arcs:
        incoming = arc.source in place_types
        place_id = arc.source if incoming else arc.target
        transition = arc.target if incoming else arc.source
        object_type = place_types[place_id]
        distributions.append(
            SAWArcWeightDistribution(
                arc.source,
                arc.target,
                transition,
                object_type,
                "activity_events"
                if activities[transition] is not None
                else "silent_witness_steps",
                tuple(sorted(counts[transition, object_type].items())),
                len(indices[transition]),
                tuple(indices[transition]),
            )
        )
    return tuple(sorted(distributions, key=lambda row: (row.source, row.target)))


@dataclass(frozen=True, slots=True)
class StochasticArcWeightNet:
    """OCPN structure with exact observed arc-weight distributions and evidence.

    Equal samples on incident arcs are correlated by their witness indices. The
    attached event bindings retain joint observations, but this model does not
    infer the probability of unobserved combinations or multiply marginals.
    Zero-incidence activities remain present in discovery even with no arcs.
    The OCPN's observed min/max bounds do not add support to these histograms.
    """

    discovery: OCPNDiscoveryPayload
    arc_distributions: tuple[SAWArcWeightDistribution, ...]
    profile: str = PROFILE
    probability_scope: str = "empirical_arc_marginals"
    joint_probability_policy: str = "not_inferred"
    silent_sampling_policy: str = "concrete_fitting_witness_steps"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.discovery, OCPNDiscoveryPayload):
            raise TypeError("discovery must be OCPNDiscoveryPayload")
        _tuple(self.arc_distributions, SAWArcWeightDistribution, "arc_distributions")
        for name, required in (
            ("profile", PROFILE),
            ("probability_scope", "empirical_arc_marginals"),
            ("joint_probability_policy", "not_inferred"),
            ("silent_sampling_policy", "concrete_fitting_witness_steps"),
        ):
            if getattr(self, name) != required:
                raise ValueError(f"unsupported {name}")
        actual = tuple(
            sorted(self.arc_distributions, key=lambda row: (row.source, row.target))
        )
        if actual != _arc_distributions(self.discovery):
            raise ValueError("arc distributions differ from fitting witness evidence")
        object.__setattr__(self, "arc_distributions", actual)

    @property
    def model(self) -> ObjectCentricPetriNet:
        """Underlying executable OCPN, with its own observed-range semantics."""
        return self.discovery.model


def discover_saw_net(
    log: OCEL | ComputationContext, spec: SAWDiscoverySpec
) -> ComputationResult[StochasticArcWeightNet]:
    """Discover exact observed arc-weight distributions without upstream runtime.

    Computed means that a whole-log accepting binding witness exists and its
    empirical counts are attached. It does not mean PM4Py semantic parity, model
    soundness, or stochastic/generalization guarantees beyond those observations.
    """
    if not isinstance(spec, SAWDiscoverySpec):
        raise TypeError("spec must be SAWDiscoverySpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OPERATOR_ID, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    discovered = discover_ocpn(context, spec.ocpn_spec)
    parents = (discovered.computation_id,) if discovered.computation_id else ()
    if discovered.status is not ComputeStatus.COMPUTED:
        return _result(
            OPERATOR_ID,
            context,
            spec,
            discovered.status,
            None,
            (
                *discovered.issues,
                ComputeIssue(
                    "saw_fitting_not_established",
                    "Arc-weight distributions require a complete checked OCPN binding witness",
                ),
            ),
            parent_computation_ids=parents,
        )
    value = StochasticArcWeightNet(
        discovered.value, _arc_distributions(discovered.value)
    )
    result_issues = [
        *discovered.issues,
        ComputeIssue(
            "empirical_marginals_only",
            "Exact arc frequencies do not define independent arc choices, transition probabilities, or unobserved joint behavior",
        ),
    ]
    if any(
        row.sample_basis == "silent_witness_steps" for row in value.arc_distributions
    ):
        result_issues.append(
            ComputeIssue(
                "witness_dependent_silent_weights",
                "Silent arc samples are concrete steps of this accepting witness, not event-aligned cardinality observations",
            )
        )
    unobserved = tuple(
        f"{row.source}->{row.target}"
        for row in value.arc_distributions
        if not row.sample_count
    )
    if unobserved:
        result_issues.append(
            ComputeIssue(
                "unobserved_arc_weights",
                "No empirical distribution is available for arcs with no witnessed firing",
                ("arcs", *unobserved),
            )
        )
    return _result(
        OPERATOR_ID,
        context,
        spec,
        ComputeStatus.COMPUTED,
        value,
        tuple(result_issues),
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("observed-saw-net", SAWDiscoverySpec, StochasticArcWeightNet),
}

__all__ = (
    "SAWDiscoverySpec",
    "SAWArcWeightDistribution",
    "StochasticArcWeightNet",
    "discover_saw_net",
    "RESULT_SCHEMAS",
)
