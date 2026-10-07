"""Replay-conditioned operational populations, without causal-effect claims.

A cutoff is a count of unique events in the replay's explicit lexical
topological order, not a wall-clock time. The snapshot is immediately after
that event: silent steps leading to a later event and terminal finalization
are excluded. Even a repair-free snapshot is a model-inferred state conditional
on the supplied initial marking and selected bindings, never an observation of
the world's actual state.

Supplied replay envelopes are reexecuted against the source and model before
use. A digest is an identity check, not a proof of a valid execution. Population
differences are scenario minus baseline, not effects caused by an action.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.model_semantics import model_digest
from pix.contracts.models import ObjectCentricPetriNet, ObjectMarking, _integer, _text
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.actions import (
    StructuralActionImpact,
    StructuralActionImpactSpec,
    TypedStructuralImpact,
    structural_action_impact,
)
from pix.object_centric.conformance import (
    ObjectReplay,
    ObjectReplaySpec,
    replay_object_log,
)
from pix.ocel import OCEL

OPERATOR_ID = "pix.object_centric.assess_operational_impact"
_EVIDENCE = ("observed_binding", "inferred_silent", "repaired", "unknown")
_INTERPRETATION = "model_inferred_population_difference_not_causal_effect"


def _ids(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in value:
        _text(item, name)
    if tuple(sorted(set(value))) != value:
        raise ValueError(f"{name} must contain sorted unique IDs")


def _signed(value: object, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")


@dataclass(frozen=True, slots=True)
class OperationalImpactSpec:
    """Compare two event-prefix cutoffs on one verified replay.

    ``scenario_event_count=None`` means the complete scheduled event population,
    not only the prefix processed before a search limit. Cutoffs may be supplied
    in either order. No change to the model and no action execution is performed.
    """

    replay_spec: ObjectReplaySpec
    changed_transition_ids: tuple[str, ...]
    baseline_event_count: int = 0
    scenario_event_count: int | None = None
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.operational_impact.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.replay_spec, ObjectReplaySpec):
            raise TypeError("replay_spec must be ObjectReplaySpec")
        normalized = StructuralActionImpactSpec(self.changed_transition_ids)
        object.__setattr__(
            self, "changed_transition_ids", normalized.changed_transition_ids
        )
        _integer(self.baseline_event_count, "baseline_event_count", minimum=0)
        if self.scenario_event_count is not None:
            _integer(self.scenario_event_count, "scenario_event_count", minimum=0)


@dataclass(frozen=True, slots=True)
class OperationalImpactRequest:
    model_digest: str
    parameters: OperationalImpactSpec
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.operational_impact.request"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _text(self.model_digest, "model_digest")
        if not isinstance(self.parameters, OperationalImpactSpec):
            raise TypeError("parameters must be OperationalImpactSpec")


@dataclass(frozen=True, slots=True)
class PopulationEvidence:
    """Distinct objects, not token multiplicities or E2O relationship counts.

    ``observed_binding`` means the selected observed events justify the model
    state without silent or repaired predecessors, conditional on the initial
    marking. Unknown objects are candidates whose presence in this region is
    unknown; they are not counted as known occupants. A known empty population
    has four empty tuples; an unknown population explicitly lists candidates.
    """

    observed_binding_object_ids: tuple[str, ...] = ()
    inferred_silent_object_ids: tuple[str, ...] = ()
    repaired_object_ids: tuple[str, ...] = ()
    unknown_object_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for category in _EVIDENCE:
            name = f"{category}_object_ids"
            values = getattr(self, name)
            _ids(values, name)
            if seen.intersection(values):
                raise ValueError("population evidence categories must be disjoint")
            seen.update(values)

    @property
    def known_object_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                self.observed_binding_object_ids
                + self.inferred_silent_object_ids
                + self.repaired_object_ids
            )
        )

    @property
    def total_object_count(self) -> int | None:
        return None if self.unknown_object_ids else len(self.known_object_ids)


def _region_population(
    population: PopulationEvidence,
    marking: ObjectMarking | None,
    places: set[str],
) -> PopulationEvidence:
    known = (
        {token.object_id for token in marking.tokens if token.place_id in places}
        if marking is not None
        else set()
    )
    # Unknown objects may occupy any selected place of their type; repaired
    # witness locations cannot establish their absence from an affected region.
    return PopulationEvidence(
        *(
            tuple(
                identity
                for identity in getattr(population, f"{category}_object_ids")
                if identity in known
            )
            for category in _EVIDENCE[:3]
        ),
        population.unknown_object_ids if places else (),
    )


@dataclass(frozen=True, slots=True)
class TypedOperationalPopulation:
    object_type: str
    all_objects: PopulationEvidence
    prior: PopulationEvidence
    posterior: PopulationEvidence

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        for name in ("all_objects", "prior", "posterior"):
            if not isinstance(getattr(self, name), PopulationEvidence):
                raise TypeError(f"{name} must be PopulationEvidence")
        for category in _EVIDENCE:
            name = f"{category}_object_ids"
            universe = set(getattr(self.all_objects, name))
            if (
                not set(getattr(self.prior, name)) <= universe
                or not set(getattr(self.posterior, name)) <= universe
            ):
                raise ValueError("region evidence must belong to the typed universe")


@dataclass(frozen=True, slots=True)
class OperationalSnapshot:
    """The retained witness marking can contain synthetic state.

    ``binding_justified_marking`` is available only for a complete, silent-free,
    repair-free, deviation-free prefix of a completed replay. It remains a
    conditional model inference. A partial replay never obtains this label,
    even when the requested prefix happens to precede the search limit.
    """

    event_count: int
    processed_event_ids: tuple[str, ...]
    unprocessed_event_ids: tuple[str, ...]
    evidence: Literal[
        "observed_binding", "inferred_silent", "repaired", "unknown", "partial"
    ]
    witness_marking: ObjectMarking | None
    binding_justified_marking: ObjectMarking | None
    silent_binding_count: int
    inserted_token_count: int
    deviation_event_ids: tuple[str, ...]
    typed: tuple[TypedOperationalPopulation, ...]

    def __post_init__(self) -> None:
        for name in ("event_count", "silent_binding_count", "inserted_token_count"):
            _integer(getattr(self, name), name, minimum=0)
        if self.evidence not in (*_EVIDENCE, "partial"):
            raise ValueError("unknown snapshot evidence classification")
        for name in ("processed_event_ids", "unprocessed_event_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple")
            for item in values:
                _text(item, name)
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must contain unique event IDs")
        if set(self.processed_event_ids) & set(self.unprocessed_event_ids):
            raise ValueError("processed and unprocessed events must be disjoint")
        if self.event_count != len(self.processed_event_ids) + len(
            self.unprocessed_event_ids
        ):
            raise ValueError("event coverage disagrees with requested cutoff")
        _ids(self.deviation_event_ids, "deviation_event_ids")
        if not set(self.deviation_event_ids) <= set(self.processed_event_ids):
            raise ValueError("deviation must belong to processed events")
        for name in ("witness_marking", "binding_justified_marking"):
            if getattr(self, name) is not None and not isinstance(
                getattr(self, name), ObjectMarking
            ):
                raise TypeError(f"{name} must be ObjectMarking or None")
        if self.unprocessed_event_ids and self.witness_marking is not None:
            raise ValueError("an unprocessed cutoff cannot have a witness marking")
        if not self.unprocessed_event_ids and self.witness_marking is None:
            raise ValueError("a processed cutoff must retain its witness marking")
        justified = self.evidence == "observed_binding"
        if justified != (self.binding_justified_marking is not None):
            raise ValueError("marking justification disagrees with evidence")
        if justified and (
            self.binding_justified_marking != self.witness_marking
            or self.silent_binding_count
            or self.inserted_token_count
            or self.deviation_event_ids
            or self.unprocessed_event_ids
        ):
            raise ValueError(
                "observed-binding marking has synthetic or unknown evidence"
            )
        unknown = bool(self.unprocessed_event_ids or self.deviation_event_ids)
        if (self.evidence == "unknown") != unknown:
            raise ValueError("unknown classification disagrees with event coverage")
        if self.evidence == "inferred_silent" and (
            not self.silent_binding_count or self.inserted_token_count
        ):
            raise ValueError("silent classification disagrees with witness counts")
        if self.evidence == "repaired" and not self.inserted_token_count:
            raise ValueError("repair classification requires inserted tokens")
        if not self.processed_event_ids and (
            self.silent_binding_count
            or self.inserted_token_count
            or self.deviation_event_ids
        ):
            raise ValueError(
                "a zero-event prefix cannot include future silent or repaired steps"
            )
        if not isinstance(self.typed, tuple) or any(
            not isinstance(row, TypedOperationalPopulation) for row in self.typed
        ):
            raise TypeError("typed must contain TypedOperationalPopulation")
        _ids(tuple(row.object_type for row in self.typed), "object types")
        objects: set[str] = set()
        for row in self.typed:
            ids = set(
                row.all_objects.known_object_ids + row.all_objects.unknown_object_ids
            )
            if objects.intersection(ids):
                raise ValueError("objects cannot occur in multiple types")
            objects.update(ids)
            if (
                row.all_objects.inferred_silent_object_ids
                and not self.silent_binding_count
            ):
                raise ValueError("silent population requires a silent witness step")
            if row.all_objects.repaired_object_ids and not self.inserted_token_count:
                raise ValueError("repaired population requires inserted tokens")
            if row.all_objects.unknown_object_ids and not unknown:
                raise ValueError("unknown population requires unknown event evidence")
            if self.unprocessed_event_ids and row.all_objects.known_object_ids:
                raise ValueError("an unprocessed cutoff cannot place known objects")
        if (
            self.witness_marking is not None
            and not {token.object_id for token in self.witness_marking.tokens}
            <= objects
        ):
            raise ValueError(
                "witness marking contains an object outside the population"
            )


@dataclass(frozen=True, slots=True)
class PopulationDelta:
    """Scenario minus baseline; total/gained/lost are unknown if either is unknown."""

    observed_binding_count: int
    inferred_silent_count: int
    repaired_count: int
    total_count: int | None
    gained_object_ids: tuple[str, ...] | None
    lost_object_ids: tuple[str, ...] | None
    unknown_object_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "observed_binding_count",
            "inferred_silent_count",
            "repaired_count",
        ):
            _signed(getattr(self, name), name)
        _ids(self.unknown_object_ids, "unknown_object_ids")
        unknown = bool(self.unknown_object_ids)
        for name in ("total_count", "gained_object_ids", "lost_object_ids"):
            if (getattr(self, name) is None) != unknown:
                raise ValueError(
                    "unknown populations cannot have exact total differences"
                )
        if not unknown:
            _signed(self.total_count, "total_count")
            _ids(self.gained_object_ids, "gained_object_ids")
            _ids(self.lost_object_ids, "lost_object_ids")
            if set(self.gained_object_ids) & set(self.lost_object_ids):
                raise ValueError("gained and lost objects must be disjoint")
            if self.total_count != len(self.gained_object_ids) - len(
                self.lost_object_ids
            ):
                raise ValueError(
                    "population count delta disagrees with membership delta"
                )
            if self.total_count != (
                self.observed_binding_count
                + self.inferred_silent_count
                + self.repaired_count
            ):
                raise ValueError(
                    "population count delta disagrees with evidence deltas"
                )


@dataclass(frozen=True, slots=True)
class TypedOperationalDelta:
    object_type: str
    prior: PopulationDelta
    posterior: PopulationDelta

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        if not isinstance(self.prior, PopulationDelta) or not isinstance(
            self.posterior, PopulationDelta
        ):
            raise TypeError("prior and posterior must be PopulationDelta")


def _delta(before: PopulationEvidence, after: PopulationEvidence) -> PopulationDelta:
    unknown = tuple(sorted(set(before.unknown_object_ids + after.unknown_object_ids)))
    left, right = set(before.known_object_ids), set(after.known_object_ids)
    return PopulationDelta(
        *(
            len(getattr(after, f"{category}_object_ids"))
            - len(getattr(before, f"{category}_object_ids"))
            for category in _EVIDENCE[:3]
        ),
        None if unknown else len(right) - len(left),
        None if unknown else tuple(sorted(right - left)),
        None if unknown else tuple(sorted(left - right)),
        unknown,
    )


@dataclass(frozen=True, slots=True)
class OperationalImpact:
    model_digest: str
    replay_computation_id: str
    replay_status: Literal["completed", "limited"]
    replay_event_order: tuple[str, ...]
    structural: StructuralActionImpact
    baseline: OperationalSnapshot
    scenario: OperationalSnapshot
    typed_deltas: tuple[TypedOperationalDelta, ...]
    cutoff_semantics: str = "event_prefix_after_visible_step_before_future_silent_steps"
    interpretation: str = _INTERPRETATION

    def __post_init__(self) -> None:
        _text(self.model_digest, "model_digest")
        _text(self.replay_computation_id, "replay_computation_id")
        if self.replay_status not in ("completed", "limited"):
            raise ValueError("unknown replay status")
        if not isinstance(self.replay_event_order, tuple):
            raise TypeError("replay_event_order must be a tuple")
        for item in self.replay_event_order:
            _text(item, "replay event ID")
        if len(set(self.replay_event_order)) != len(self.replay_event_order):
            raise ValueError("replay event order must contain unique IDs")
        if not isinstance(self.structural, StructuralActionImpact):
            raise TypeError("structural must be StructuralActionImpact")
        for name in ("baseline", "scenario"):
            value = getattr(self, name)
            if not isinstance(value, OperationalSnapshot):
                raise TypeError(f"{name} must be OperationalSnapshot")
            if (
                value.processed_event_ids + value.unprocessed_event_ids
                != (self.replay_event_order[: value.event_count])
            ):
                raise ValueError("snapshot must be a prefix of the replay event order")
            if (
                self.replay_status == "limited"
                and value.binding_justified_marking is not None
            ):
                raise ValueError(
                    "partial replay cannot certify an observed-binding marking"
                )
            if self.replay_status == "completed" and (
                value.evidence == "partial" or value.unprocessed_event_ids
            ):
                raise ValueError("completed replay cannot have an unprocessed cutoff")
        if any(
            row.prior_marked_object_ids is not None
            or row.posterior_marked_object_ids is not None
            for row in self.structural.typed
        ):
            raise ValueError(
                "structural topology must not assert evidence-free populations"
            )
        kinds = tuple(row.object_type for row in self.structural.typed)
        if any(
            tuple(row.object_type for row in snapshot.typed) != kinds
            for snapshot in (self.baseline, self.scenario)
        ):
            raise ValueError("typed snapshots must match structural object types")
        _ids(kinds, "structural object types")
        stops = {
            len(snapshot.processed_event_ids)
            for snapshot in (self.baseline, self.scenario)
            if snapshot.unprocessed_event_ids
        }
        if stops and (
            len(stops) != 1
            or any(
                snapshot.processed_event_ids
                != self.replay_event_order[: min(snapshot.event_count, min(stops))]
                for snapshot in (self.baseline, self.scenario)
            )
        ):
            raise ValueError("snapshots disagree on the replay stop position")
        if (
            self.baseline.event_count == self.scenario.event_count
            and self.baseline != self.scenario
        ):
            raise ValueError("equal cutoffs must have equal snapshots")
        early, late = sorted(
            (self.baseline, self.scenario), key=lambda row: row.event_count
        )
        if (
            early.silent_binding_count > late.silent_binding_count
            or early.inserted_token_count > late.inserted_token_count
            or not set(early.deviation_event_ids) <= set(late.deviation_event_ids)
        ):
            raise ValueError("prefix witness evidence must accumulate monotonically")
        if tuple(
            (
                row.object_type,
                tuple(
                    sorted(
                        row.all_objects.known_object_ids
                        + row.all_objects.unknown_object_ids
                    )
                ),
            )
            for row in self.baseline.typed
        ) != tuple(
            (
                row.object_type,
                tuple(
                    sorted(
                        row.all_objects.known_object_ids
                        + row.all_objects.unknown_object_ids
                    )
                ),
            )
            for row in self.scenario.typed
        ):
            raise ValueError("snapshot object universes disagree")
        for before, after in zip(early.typed, late.typed):
            before_categories = {
                identity: index
                for index, category in enumerate(_EVIDENCE)
                for identity in getattr(before.all_objects, f"{category}_object_ids")
            }
            if any(
                before_categories[identity] > index
                for index, category in enumerate(_EVIDENCE)
                for identity in getattr(after.all_objects, f"{category}_object_ids")
            ):
                raise ValueError("later prefix cannot erase uncertain object evidence")
        for snapshot in (self.baseline, self.scenario):
            for row, topology in zip(snapshot.typed, self.structural.typed):
                for region in ("prior", "posterior"):
                    expected = _region_population(
                        row.all_objects,
                        snapshot.witness_marking,
                        set(getattr(topology, f"{region}_place_ids")),
                    )
                    if getattr(row, region) != expected:
                        raise ValueError(
                            "regional populations disagree with witness and topology"
                        )
        expected = tuple(
            TypedOperationalDelta(
                left.object_type,
                _delta(left.prior, right.prior),
                _delta(left.posterior, right.posterior),
            )
            for left, right in zip(self.baseline.typed, self.scenario.typed)
        )
        if self.typed_deltas != expected:
            raise ValueError("population deltas disagree with snapshots")
        if (
            self.cutoff_semantics
            != ("event_prefix_after_visible_step_before_future_silent_steps")
            or self.interpretation != _INTERPRETATION
        ):
            raise ValueError("unknown operational impact interpretation")


def _snapshot(
    replay: ObjectReplay, count: int, topology: StructuralActionImpact
) -> OperationalSnapshot:
    requested_ids = replay.event_order[:count]
    processed = requested_ids[: replay.processed_event_count]
    unprocessed = requested_ids[len(processed) :]
    objects = dict(replay.scope.selected_objects)
    evidence = {identity: "observed_binding" for identity in objects}
    events = {event.event_id: event for event in replay.scope.events}
    prefix = [replay.steps[0]]
    found = 0
    for step in replay.steps[1:]:
        if found == len(processed):
            break
        prefix.append(step)
        if step.event_id is not None:
            found += 1
    silent_count = inserted_count = 0
    deviations = []
    for step in prefix[1:]:
        inserted_count += len(step.inserted_tokens)
        if step.kind == "log_deviation":
            deviations.append(step.event_id)
            for _, ids in events[step.event_id].objects:
                for identity in ids:
                    evidence[identity] = "unknown"
        elif step.binding is not None:
            ids = tuple(
                identity for _, group in step.binding.objects for identity in group
            )
            category = max((_EVIDENCE.index(evidence[i]) for i in ids), default=0)
            if step.kind == "silent":
                silent_count += 1
                category = max(category, 1)
            if step.inserted_tokens:
                category = max(category, 2)
            for identity in ids:
                evidence[identity] = _EVIDENCE[category]
    if unprocessed:
        marking = None
        evidence = dict.fromkeys(objects, "unknown")
    else:
        marking = ObjectMarking(prefix[-1].marking_after)
    if unprocessed or deviations:
        summary = "unknown"
    elif replay.status == "limited":
        summary = "partial"
    elif inserted_count:
        summary = "repaired"
    elif silent_count:
        summary = "inferred_silent"
    else:
        summary = "observed_binding"

    def population(kind):
        candidates = {
            identity for identity, item_kind in objects.items() if item_kind == kind
        }
        return PopulationEvidence(
            *(
                tuple(
                    sorted(
                        identity
                        for identity in candidates
                        if evidence[identity] == category
                    )
                )
                for category in _EVIDENCE
            )
        )

    typed = []
    for row in topology.typed:
        universe = population(row.object_type)
        typed.append(
            TypedOperationalPopulation(
                row.object_type,
                universe,
                _region_population(universe, marking, set(row.prior_place_ids)),
                _region_population(universe, marking, set(row.posterior_place_ids)),
            )
        )
    return OperationalSnapshot(
        count,
        processed,
        unprocessed,
        summary,
        marking,
        marking if summary == "observed_binding" else None,
        silent_count,
        inserted_count,
        tuple(sorted(deviations)),
        tuple(typed),
    )


def assess_operational_impact(
    log: OCEL | ComputationContext,
    net: ObjectCentricPetriNet,
    spec: OperationalImpactSpec,
    *,
    replay: ComputationResult[ObjectReplay] | None = None,
) -> ComputationResult[OperationalImpact]:
    """Verify replay, then compare typed populations at two explicit cutoffs.

    An optional replay is always reexecuted and compared in full, including
    request/source/model identity and every witness step. A structurally valid
    but forged result is rejected. Silent or repaired states remain inspectable
    but cannot be presented as observed-binding markings. Unknown positions
    have ``None`` total deltas, never a fabricated zero.
    """
    if not isinstance(net, ObjectCentricPetriNet):
        raise TypeError("net must be ObjectCentricPetriNet")
    if not isinstance(spec, OperationalImpactSpec):
        raise TypeError("spec must be OperationalImpactSpec")
    request = OperationalImpactRequest(model_digest(net), spec)
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OPERATOR_ID, None, request, ComputeStatus.INVALID_INPUT, None, issues
        )
    topology_result = structural_action_impact(
        net, StructuralActionImpactSpec(spec.changed_transition_ids)
    )
    verified = replay_object_log(context, net, spec.replay_spec)
    if replay is not None and (
        not isinstance(replay, ComputationResult) or replay != verified
    ):
        return _result(
            OPERATOR_ID,
            context,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "replay_verification_failed",
                    "Replay does not match reexecution against source, model and request",
                ),
            ),
        )
    if verified.value is None:
        return _result(
            OPERATOR_ID,
            context,
            request,
            verified.status,
            None,
            verified.issues,
            parent_computation_ids=(verified.computation_id,),
        )
    value = verified.value
    scenario_count = (
        len(value.event_order)
        if spec.scenario_event_count is None
        else spec.scenario_event_count
    )
    if max(spec.baseline_event_count, scenario_count) > len(value.event_order):
        return _result(
            OPERATOR_ID,
            context,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "cutoff_out_of_range", "Cutoff exceeds scheduled event population"
                ),
            ),
            parent_computation_ids=(verified.computation_id,),
        )
    topology = topology_result.value
    # A model may explicitly retain isolated concrete objects of a type with no
    # places. Keep them in the population universe, with empty affected regions.
    absent_types = {kind for _, kind in value.scope.selected_objects} - {
        row.object_type for row in topology.typed
    }
    if absent_types:
        topology = replace(
            topology,
            typed=tuple(
                sorted(
                    topology.typed
                    + tuple(
                        TypedStructuralImpact(kind, (), (), (), (), (), None, None)
                        for kind in absent_types
                    ),
                    key=lambda row: row.object_type,
                )
            ),
        )
    baseline = _snapshot(value, spec.baseline_event_count, topology)
    scenario = _snapshot(value, scenario_count, topology)
    deltas = tuple(
        TypedOperationalDelta(
            before.object_type,
            _delta(before.prior, after.prior),
            _delta(before.posterior, after.posterior),
        )
        for before, after in zip(baseline.typed, scenario.typed)
    )
    payload = OperationalImpact(
        model_digest(net),
        verified.computation_id,
        value.status,
        value.event_order,
        topology,
        baseline,
        scenario,
        deltas,
    )
    issues = verified.issues
    unknown_population = any(
        snapshot.evidence == "unknown" for snapshot in (baseline, scenario)
    )
    if unknown_population:
        issues += (
            ComputeIssue(
                "unknown_operational_population",
                "Unprocessed or unmapped events leave population positions unknown",
            ),
        )
    return _result(
        OPERATOR_ID,
        context,
        request,
        ComputeStatus.PARTIAL
        if value.status == "limited" or unknown_population
        else ComputeStatus.COMPUTED,
        payload,
        issues,
        parent_computation_ids=(verified.computation_id,),
    )


def validate_operational_impact_result(result: ComputationResult) -> None:
    """Validate persisted redundant facts; this does not prove source/model truth."""
    if not isinstance(result, ComputationResult) or result.operator_id != OPERATOR_ID:
        raise TypeError("expected an operational impact ComputationResult")
    if not isinstance(result.spec, OperationalImpactRequest):
        raise TypeError("operational impact requires OperationalImpactRequest")
    if result.value is None:
        return
    value = result.value
    if not isinstance(value, OperationalImpact):
        raise TypeError("operational impact payload must be OperationalImpact")
    spec = result.spec.parameters
    if result.spec.model_digest != value.model_digest:
        raise ValueError("request and payload model identities disagree")
    if result.parent_computation_ids != (value.replay_computation_id,):
        raise ValueError("parent identity disagrees with verified replay reference")
    scenario_count = (
        len(value.replay_event_order)
        if spec.scenario_event_count is None
        else spec.scenario_event_count
    )
    if (value.baseline.event_count, value.scenario.event_count) != (
        spec.baseline_event_count,
        scenario_count,
    ):
        raise ValueError("snapshot cutoffs disagree with request")
    if value.structural.changed_transition_ids != spec.changed_transition_ids:
        raise ValueError("changed transitions disagree with request")
    partial = value.replay_status == "limited" or any(
        snapshot.evidence == "unknown" for snapshot in (value.baseline, value.scenario)
    )
    expected = ComputeStatus.PARTIAL if partial else ComputeStatus.COMPUTED
    if result.status is not expected:
        raise ValueError("result status disagrees with replay and population coverage")


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "object-operational-impact",
        OperationalImpactRequest,
        OperationalImpact,
    )
}

__all__ = (
    "OperationalImpactSpec",
    "OperationalImpactRequest",
    "PopulationEvidence",
    "TypedOperationalPopulation",
    "OperationalSnapshot",
    "PopulationDelta",
    "TypedOperationalDelta",
    "OperationalImpact",
    "assess_operational_impact",
    "validate_operational_impact_result",
)
