"""Native OCEL sampling and conditional projection over explicit populations.

Selection evidence identifies original events, objects and qualified relations.
Materialization verifies the full request and uses the native OCEL projector;
no analytical result embeds an OCEL or rewrites observed timestamps/history.
Execution membership, exact incidence variants and activity sequences remain
different populations. Object sampling may cut shared-event relations, which is
explicitly controlled by the projection policy and reported in the result.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from fractions import Fraction
from hashlib import sha256
from math import isfinite
from random import Random
from typing import ClassVar

from pix.compute._common import _prepare, _result
from pix.compute.executions import discover_executions
from pix.compute.variants import discover_variants
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.filter_predicates import (
    OCFilterPredicateSpec,
    evaluate_filter_predicates,
)
from pix.object_centric.filtering import (
    OCELFilterResult,
    OCELFilterSpec,
    filter_ocel,
    materialize_sublog,
)
from pix.ocel import OCEL, build


def _choice(value, choices, name):
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}")


def _strings(value, name, *, optional=False):
    if optional and value is None:
        return
    if (
        not isinstance(value, tuple)
        or any(not isinstance(item, str) or not item for item in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{name} must be a tuple of distinct nonempty strings")


def _count(value, name, *, optional=False):
    if optional and value is None:
        return
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _ratio(value, name):
    if value is not None and (
        type(value) not in (int, float) or not 0 <= value <= 1 or not isfinite(value)
    ):
        raise ValueError(f"{name} must be between 0 and 1")


def _range(value, minimum, maximum):
    return (minimum is None or value >= minimum) and (
        maximum is None or value <= maximum
    )


def _bounds(minimum, maximum, name):
    _count(minimum, f"minimum_{name}", optional=True)
    _count(maximum, f"maximum_{name}", optional=True)
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError(f"minimum_{name} exceeds maximum_{name}")


@dataclass(frozen=True, slots=True)
class OCProjectionPolicy:
    """Objects are selected seeds, all peers of selected events, or all source objects.

    For event selectors, seeds already contain every related object. For object
    selectors, any/all/retain controls which events are selected BEFORE optional
    peer expansion. ``retain`` includes unrelated events deliberately. Full
    source object history and surviving O2O qualifiers are always preserved.
    """

    object_retention: str = "selected"
    object_event_policy: str = "any"
    isolated_objects: str = "retain"

    def __post_init__(self):
        _choice(
            self.object_retention, ("selected", "associated", "all"), "object_retention"
        )
        _choice(
            self.object_event_policy, ("any", "all", "retain"), "object_event_policy"
        )
        _choice(self.isolated_objects, ("retain", "drop"), "isolated_objects")


@dataclass(frozen=True, slots=True)
class OCFrequencyRule:
    """Absolute/share thresholds intersect a ranked top-k/coverage prefix.

    Shares use total contributions in the named population. ``at_least`` stops
    at >= coverage; ``exceed`` preserves the OCPA strict > convention. Thus
    zero selects none under at_least and the first group under exceed. Ties are
    lexical unless include_ties expands the cutoff. No automatic heuristic is
    hidden behind these parameters.
    """

    minimum_count: int | None = None
    maximum_count: int | None = None
    minimum_share: int | float | None = None
    maximum_share: int | float | None = None
    top_k: int | None = None
    coverage: int | float | None = None
    coverage_boundary: str = "at_least"
    include_ties: bool = True

    def __post_init__(self):
        _bounds(self.minimum_count, self.maximum_count, "count")
        _count(self.top_k, "top_k", optional=True)
        for name in ("minimum_share", "maximum_share", "coverage"):
            _ratio(getattr(self, name), name)
        if (
            self.minimum_share is not None
            and self.maximum_share is not None
            and self.minimum_share > self.maximum_share
        ):
            raise ValueError("minimum_share exceeds maximum_share")
        _choice(self.coverage_boundary, ("at_least", "exceed"), "coverage_boundary")
        if type(self.include_ties) is not bool:
            raise TypeError("include_ties must be bool")


@dataclass(frozen=True, slots=True)
class OCSamplingSpec:
    count: int
    unit: str = "events"
    seed: int = 0
    execution_spec: ExecutionSpec = ExecutionSpec("connected_components")
    include_isolated_objects: bool = True
    maximum_events: int | None = None
    maximum_objects: int | None = None
    maximum_relations: int | None = None
    overflow: str = "error"
    projection: OCProjectionPolicy = OCProjectionPolicy()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _count(self.count, "count")
        if type(self.seed) is not int:
            raise TypeError("seed must be int")
        _choice(self.unit, ("events", "objects", "components"), "unit")
        _choice(self.overflow, ("error", "clip"), "overflow")
        if (
            not isinstance(self.execution_spec, ExecutionSpec)
            or self.execution_spec.method != "connected_components"
        ):
            raise ValueError(
                "component sampling requires connected_components extraction"
            )
        if not isinstance(self.projection, OCProjectionPolicy):
            raise TypeError("projection must be OCProjectionPolicy")
        if type(self.include_isolated_objects) is not bool:
            raise TypeError("include_isolated_objects must be bool")
        for name in ("maximum_events", "maximum_objects", "maximum_relations"):
            _count(getattr(self, name), name, optional=True)
            if self.unit != "components" and getattr(self, name) is not None:
                raise ValueError("size limits apply to component eligibility")


@dataclass(frozen=True, slots=True)
class OCFrequencyFilterSpec:
    entity: str = "activity"
    rule: OCFrequencyRule = OCFrequencyRule()
    counting: str = "unique_event_objects"
    qualifiers: tuple[str, ...] | None = None
    object_types: tuple[str, ...] | None = None
    positive: bool = True
    unknown: str = "exclude"
    projection: OCProjectionPolicy = OCProjectionPolicy()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _choice(self.entity, ("activity", "object", "object_type"), "entity")
        _choice(self.counting, ("unique_event_objects", "relations"), "counting")
        _choice(self.unknown, ("exclude", "include", "error"), "unknown")
        _strings(self.object_types, "object_types", optional=True)
        if self.qualifiers is not None and (
            not isinstance(self.qualifiers, tuple)
            or any(not isinstance(item, str) for item in self.qualifiers)
        ):
            raise TypeError("qualifiers must be a tuple of strings")
        if self.entity == "activity" and (
            self.qualifiers is not None
            or self.object_types is not None
            or self.counting != "unique_event_objects"
        ):
            raise ValueError(
                "activity frequency counts unique source events without relation scope"
            )
        if not isinstance(self.rule, OCFrequencyRule) or not isinstance(
            self.projection, OCProjectionPolicy
        ):
            raise TypeError("rule/projection has the wrong type")
        if type(self.positive) is not bool:
            raise TypeError("positive must be bool")


@dataclass(frozen=True, slots=True)
class OCTypeActivityRule:
    object_type: str
    activities: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.object_type, str) or not self.object_type:
            raise ValueError("object_type must be nonempty")
        _strings(self.activities, "activities")


@dataclass(frozen=True, slots=True)
class OCTypeCardinality:
    object_type: str
    minimum: int = 0
    maximum: int | None = None

    def __post_init__(self):
        if not isinstance(self.object_type, str) or not self.object_type:
            raise ValueError("object_type must be nonempty")
        _count(self.minimum, "minimum")
        _bounds(self.minimum, self.maximum, "cardinality")


@dataclass(frozen=True, slots=True)
class OCStructureFilterSpec:
    """Whitelist filtering is E2O-level; cardinality/endpoints select events.

    Earliest/latest means observed participation, not physical creation/death.
    reject/all/event_id define how a boundary timestamp tie is treated. The
    lexical event_id option is reproducibility evidence, never causality.
    """

    mode: str = "cardinality"
    cardinalities: tuple[OCTypeCardinality, ...] = ()
    allowed: tuple[OCTypeActivityRule, ...] = ()
    object_type: str | None = None
    qualifiers: tuple[str, ...] | None = None
    counting: str = "unique_objects"
    tie_policy: str = "reject"
    positive: bool = True
    unknown: str = "exclude"
    keep_unrelated_events: bool = False
    projection: OCProjectionPolicy = OCProjectionPolicy()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _choice(
            self.mode,
            ("cardinality", "activity_type_matching", "start_events", "end_events"),
            "mode",
        )
        _choice(self.counting, ("unique_objects", "relations"), "counting")
        _choice(self.tie_policy, ("reject", "all", "event_id"), "tie_policy")
        _choice(self.unknown, ("exclude", "include", "error"), "unknown")
        for name, kind in (
            ("cardinalities", OCTypeCardinality),
            ("allowed", OCTypeActivityRule),
        ):
            values = getattr(self, name)
            if (
                not isinstance(values, tuple)
                or not all(isinstance(value, kind) for value in values)
                or len({value.object_type for value in values}) != len(values)
            ):
                raise ValueError(f"{name} requires distinct typed rules")
        if self.mode in ("start_events", "end_events"):
            if not isinstance(self.object_type, str) or not self.object_type:
                raise ValueError("boundary filter requires object_type")
        elif self.object_type is not None:
            raise ValueError("object_type applies to boundary filters")
        if self.allowed and self.mode != "activity_type_matching":
            raise ValueError("allowed only applies to activity/type matching")
        if self.cardinalities and self.mode != "cardinality":
            raise ValueError("cardinalities only apply to cardinality filtering")
        if self.counting != "unique_objects" and self.mode != "cardinality":
            raise ValueError("counting only applies to cardinality filtering")
        if self.tie_policy != "reject" and self.mode not in (
            "start_events",
            "end_events",
        ):
            raise ValueError("tie_policy only applies to observed boundaries")
        if self.keep_unrelated_events and self.mode != "activity_type_matching":
            raise ValueError(
                "keep_unrelated_events only applies to the relation whitelist"
            )
        if self.qualifiers is not None and (
            not isinstance(self.qualifiers, tuple)
            or any(not isinstance(item, str) for item in self.qualifiers)
        ):
            raise TypeError("qualifiers must be a tuple of strings")
        if not isinstance(self.projection, OCProjectionPolicy):
            raise TypeError("projection must be OCProjectionPolicy")
        if (
            type(self.positive) is not bool
            or type(self.keep_unrelated_events) is not bool
        ):
            raise TypeError("positive and keep_unrelated_events must be bool")


@dataclass(frozen=True, slots=True)
class OCExecutionFilterSpec:
    """Conditions select complete membership sets, not flattened case traces.

    Conditions are conjunctive: count ranges plus required objects/types/activities.
    Components can include eventless source objects as explicit singleton groups.
    Exact variants use the native incidence equivalence; sequences use an
    explicitly selected timestamp linearization and a separate tie policy.
    """

    mode: str = "conditions"
    execution_spec: ExecutionSpec = ExecutionSpec("connected_components")
    variant_spec: VariantSpec = VariantSpec()
    execution_ids: tuple[str, ...] = ()
    variant_ids: tuple[str, ...] = ()
    sequences: tuple[tuple[str, ...], ...] = ()
    sequence_ties: str = "reject"
    object_ids: tuple[str, ...] = ()
    object_types: tuple[str, ...] = ()
    activities: tuple[str, ...] = ()
    minimum_events: int | None = None
    maximum_events: int | None = None
    minimum_objects: int | None = None
    maximum_objects: int | None = None
    minimum_relations: int | None = None
    maximum_relations: int | None = None
    minimum_duration_us: int | None = None
    maximum_duration_us: int | None = None
    frequency: OCFrequencyRule = OCFrequencyRule()
    include_isolated_objects: bool = True
    positive: bool = True
    unknown: str = "exclude"
    projection: OCProjectionPolicy = OCProjectionPolicy()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _choice(
            self.mode,
            (
                "conditions",
                "execution_ids",
                "variant_ids",
                "variant_frequency",
                "sequence",
            ),
            "mode",
        )
        _choice(self.sequence_ties, ("reject", "event_id"), "sequence_ties")
        _choice(self.unknown, ("exclude", "include", "error"), "unknown")
        if not isinstance(self.execution_spec, ExecutionSpec) or not isinstance(
            self.variant_spec, VariantSpec
        ):
            raise TypeError("execution_spec/variant_spec has the wrong type")
        if not isinstance(self.projection, OCProjectionPolicy) or not isinstance(
            self.frequency, OCFrequencyRule
        ):
            raise TypeError("projection/frequency has the wrong type")
        for name in (
            "execution_ids",
            "variant_ids",
            "object_ids",
            "object_types",
            "activities",
        ):
            _strings(getattr(self, name), name)
        if not isinstance(self.sequences, tuple):
            raise TypeError("sequences must be a tuple")
        for sequence in self.sequences:
            if not isinstance(sequence, tuple) or any(
                not isinstance(activity, str) or not activity for activity in sequence
            ):
                raise ValueError("sequences must contain activity tuples")
        for stem in ("events", "objects", "relations", "duration_us"):
            _bounds(
                getattr(self, "minimum_" + stem), getattr(self, "maximum_" + stem), stem
            )
        if (
            type(self.positive) is not bool
            or type(self.include_isolated_objects) is not bool
        ):
            raise TypeError("positive and include_isolated_objects must be bool")
        if self.mode != "conditions" and (
            self.object_ids
            or self.object_types
            or self.activities
            or any(
                getattr(self, prefix + stem) is not None
                for prefix in ("minimum_", "maximum_")
                for stem in ("events", "objects", "relations", "duration_us")
            )
        ):
            raise ValueError("membership conditions only apply to conditions mode")
        if self.execution_ids and self.mode != "execution_ids":
            raise ValueError("execution_ids only applies to execution_ids mode")
        if self.variant_ids and self.mode != "variant_ids":
            raise ValueError("variant_ids only applies to variant_ids mode")
        if self.sequences and self.mode != "sequence":
            raise ValueError("sequences only applies to sequence mode")
        if self.frequency != OCFrequencyRule() and self.mode != "variant_frequency":
            raise ValueError("frequency only applies to variant_frequency mode")


@dataclass(frozen=True, slots=True)
class OCPredicateFilterSpec:
    predicate: OCFilterPredicateSpec
    projection: OCProjectionPolicy = OCProjectionPolicy()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.predicate, OCFilterPredicateSpec) or not isinstance(
            self.projection, OCProjectionPolicy
        ):
            raise TypeError("predicate/projection has the wrong type")


@dataclass(frozen=True, slots=True, order=True)
class OCRelationSelection:
    event_id: str
    object_id: str
    qualifier: str


@dataclass(frozen=True, slots=True)
class OCSelectionDecision:
    entity_kind: str
    entity_id: str
    selected: bool
    reason: str
    count: int | None = None
    denominator: int | None = None
    event_ids: tuple[str, ...] = ()
    object_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OCSelectionGroup:
    id: str
    source: str
    event_ids: tuple[str, ...]
    object_ids: tuple[str, ...]
    relation_count: int


@dataclass(frozen=True, slots=True)
class OCAdvancedFilterResult:
    selection_unit: str
    selection_spec: OCELFilterSpec
    selection: OCELFilterResult
    seed_event_ids: tuple[str, ...]
    seed_object_ids: tuple[str, ...]
    retained_relations: tuple[OCRelationSelection, ...]
    decisions: tuple[OCSelectionDecision, ...]
    selected_execution_ids: tuple[str, ...] = ()
    selected_variant_ids: tuple[str, ...] = ()
    groups: tuple[OCSelectionGroup, ...] = ()
    overlapping_event_ids: tuple[str, ...] = ()
    overlapping_object_ids: tuple[str, ...] = ()
    unknown_event_ids: tuple[str, ...] = ()
    unknown_object_ids: tuple[str, ...] = ()
    unknown_execution_ids: tuple[str, ...] = ()
    population_count: int = 0
    dropped_e2o_count: int = 0

    @property
    def selected_event_ids(self):
        return self.selection.selected_event_ids

    @property
    def selected_object_ids(self):
        return self.selection.selected_object_ids


def _invalid(
    operator,
    context,
    spec,
    code,
    message,
    *,
    issues=(),
    parents=(),
    status=ComputeStatus.INVALID_INPUT,
):
    return _result(
        operator,
        context,
        spec,
        status,
        None,
        tuple(issues) + (ComputeIssue(code, message),),
        parent_computation_ids=parents,
    )


def _prepare_request(log, spec, expected, operator):
    if not isinstance(spec, expected):
        raise TypeError(f"spec must be {expected.__name__}")
    context, issues = _prepare(log)
    if context is None:
        return None, _result(
            operator, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    return context, None


def _objects_for_events(context, events):
    return {
        relation.object for event in events for relation in context.e2o_by_event[event]
    }


def _project(
    context,
    operator,
    spec,
    policy,
    unit,
    events,
    objects,
    decisions=(),
    *,
    parents=(),
    issues=(),
    partial=False,
    relation_mask=None,
    executions=(),
    variants=(),
    groups=(),
    unknown_events=(),
    unknown_objects=(),
    unknown_executions=(),
    population=0,
):
    seed_events, seed_objects = set(events), set(objects)
    if unit == "objects":
        events = set()
        for event in context.log.events:
            related = {relation.object for relation in context.e2o_by_event[event.id]}
            if (
                policy.object_event_policy == "retain"
                or (policy.object_event_policy == "any" and related & objects)
                or (
                    policy.object_event_policy == "all"
                    and related
                    and related <= objects
                )
            ):
                events.add(event.id)
    else:
        events = set(events)
    objects = set(objects)
    if policy.object_retention == "all":
        objects = set(context.objects_by_id)
    elif policy.object_retention == "associated":
        objects |= _objects_for_events(context, events)
    mask = (
        None
        if relation_mask is None
        else {
            relation
            for relation in relation_mask
            if relation.event_id in events and relation.object_id in objects
        }
    )
    if mask is not None and policy.isolated_objects == "drop":
        objects &= {relation.object_id for relation in mask}
    projection_spec = OCELFilterSpec(
        event_ids=tuple(sorted(events)),
        object_ids=tuple(sorted(objects)),
        object_event_policy="retain",
        isolated_objects=policy.isolated_objects,
        history_policy="preserve_all",
    )
    base = filter_ocel(context, projection_spec)
    if base.value is None:
        return _result(
            operator,
            context,
            spec,
            base.status,
            None,
            tuple(issues) + base.issues,
            parent_computation_ids=tuple(parents)
            + ((base.computation_id,) if base.computation_id else ()),
        )
    final_events, final_objects = (
        set(base.value.selected_event_ids),
        set(base.value.selected_object_ids),
    )
    relations = tuple(
        sorted(
            OCRelationSelection(relation.event, relation.object, relation.qualifier)
            for relation in context.log.e2o
            if relation.event in final_events
            and relation.object in final_objects
            and (
                mask is None
                or OCRelationSelection(
                    relation.event, relation.object, relation.qualifier
                )
                in mask
            )
        )
    )
    chosen_groups = [group for group in groups if group.id in executions]
    event_memberships = Counter(
        event for group in chosen_groups for event in group.event_ids
    )
    object_memberships = Counter(
        obj for group in chosen_groups for obj in group.object_ids
    )
    value = OCAdvancedFilterResult(
        unit,
        projection_spec,
        base.value,
        tuple(sorted(seed_events)),
        tuple(sorted(seed_objects)),
        relations,
        tuple(decisions),
        tuple(sorted(executions)),
        tuple(sorted(variants)),
        tuple(groups),
        tuple(sorted(event for event, count in event_memberships.items() if count > 1)),
        tuple(sorted(obj for obj, count in object_memberships.items() if count > 1)),
        tuple(sorted(unknown_events)),
        tuple(sorted(unknown_objects)),
        tuple(sorted(unknown_executions)),
        population,
        len(context.log.e2o) - len(relations),
    )
    all_issues = tuple(dict.fromkeys((*issues, *base.issues)))
    return _result(
        operator,
        context,
        spec,
        ComputeStatus.PARTIAL if partial else ComputeStatus.COMPUTED,
        value,
        all_issues,
        parent_computation_ids=tuple(dict.fromkeys((*parents, base.computation_id))),
    )


def _groups(context, extraction, include_isolated):
    parent = discover_executions(context, extraction)
    if parent.value is None:
        return parent, ()
    groups = []
    for execution in parent.value.executions:
        events = tuple(sorted(event.id for event in execution.events))
        objects = tuple(sorted(obj.id for obj in execution.objects))
        event_set, object_set = set(events), set(objects)
        relations = sum(
            relation.event in event_set and relation.object in object_set
            for relation in context.log.e2o
        )
        groups.append(
            OCSelectionGroup(
                execution.execution_id, "native_execution", events, objects, relations
            )
        )
    if include_isolated and extraction.method == "connected_components":
        selected_types = (
            set(context.objects_by_type)
            if extraction.object_types is None
            else set(extraction.object_types)
        )
        for obj in context.log.objects:
            if obj.type in selected_types and not context.e2o_by_object[obj.id]:
                identity = sha256(
                    (context.source_digest + "\0" + obj.id).encode()
                ).hexdigest()
                groups.append(
                    OCSelectionGroup(
                        "pix.isolated-object-component:" + identity,
                        "isolated_object",
                        (),
                        (obj.id,),
                        0,
                    )
                )
    return parent, tuple(sorted(groups, key=lambda group: group.id))


def _rank(counts, rule):
    ranked = sorted(counts, key=lambda entity: (-counts[entity], entity))
    total = sum(counts.values())
    length = len(ranked) if rule.top_k is None else min(rule.top_k, len(ranked))
    if rule.include_ties and length:
        while (
            length < len(ranked)
            and counts[ranked[length]] == counts[ranked[length - 1]]
        ):
            length += 1
    candidates = ranked[:length]
    if rule.coverage is not None:
        target = Fraction(str(rule.coverage)) * total
        cumulative, selected_length = 0, 0
        while selected_length < len(candidates):
            stop = (
                cumulative >= target
                if rule.coverage_boundary == "at_least"
                else cumulative > target
            )
            if stop:
                break
            cumulative += counts[candidates[selected_length]]
            selected_length += 1
        if rule.include_ties and selected_length:
            while (
                selected_length < len(candidates)
                and counts[candidates[selected_length]]
                == counts[candidates[selected_length - 1]]
            ):
                selected_length += 1
        candidates = candidates[:selected_length]
    chosen, unknown = set(), set()
    for entity in candidates:
        count = counts[entity]
        if not _range(count, rule.minimum_count, rule.maximum_count):
            continue
        if total == 0 and (
            rule.minimum_share is not None or rule.maximum_share is not None
        ):
            unknown.add(entity)
        elif _range(
            Fraction(count, total) if total else 0,
            Fraction(str(rule.minimum_share))
            if rule.minimum_share is not None
            else None,
            Fraction(str(rule.maximum_share))
            if rule.maximum_share is not None
            else None,
        ):
            chosen.add(entity)
    return chosen, unknown, total


def sample_ocel(log, spec: OCSamplingSpec):
    """Sample events, objects or complete eligible native component scopes."""
    operator = "pix.object_centric.sample_ocel"
    context, failure = _prepare_request(log, spec, OCSamplingSpec, operator)
    if failure is not None:
        return failure
    groups, parents, issues, partial = (), (), (), False
    if spec.unit == "events":
        population = tuple(sorted(context.events_by_id))
    elif spec.unit == "objects":
        population = tuple(sorted(context.objects_by_id))
    else:
        parent, groups = _groups(
            context, spec.execution_spec, spec.include_isolated_objects
        )
        parents = (parent.computation_id,)
        issues, partial = parent.issues, parent.status is ComputeStatus.PARTIAL
        if parent.value is None:
            return _result(
                operator,
                context,
                spec,
                parent.status,
                None,
                issues,
                parent_computation_ids=parents,
            )
        population = tuple(
            group.id
            for group in groups
            if _range(len(group.event_ids), None, spec.maximum_events)
            and _range(len(group.object_ids), None, spec.maximum_objects)
            and _range(group.relation_count, None, spec.maximum_relations)
        )
    if spec.count > len(population) and spec.overflow == "error":
        return _invalid(
            operator,
            context,
            spec,
            "sample_exceeds_population",
            "Sample count exceeds the eligible population",
            issues=issues,
            parents=parents,
        )
    size = min(spec.count, len(population))
    selected = set(Random(spec.seed).sample(population, size))
    if size != spec.count:
        issues += (
            ComputeIssue(
                "sample_count_clipped",
                "Explicit clip policy reduced count to eligible population size",
            ),
        )
    decisions = tuple(
        OCSelectionDecision(
            spec.unit,
            entity,
            entity in selected,
            "sampled" if entity in selected else "not_sampled",
        )
        for entity in population
    )
    executions = ()
    if spec.unit == "events":
        events, objects, unit = (
            selected,
            _objects_for_events(context, selected),
            "events",
        )
    elif spec.unit == "objects":
        events, objects, unit = set(), selected, "objects"
    else:
        executions = selected
        events = {
            event
            for group in groups
            if group.id in selected
            for event in group.event_ids
        }
        objects = {
            obj for group in groups if group.id in selected for obj in group.object_ids
        }
        unit = "executions"
        decisions += tuple(
            OCSelectionDecision(
                "components",
                group.id,
                False,
                "ineligible_size",
                len(group.event_ids),
                None,
                group.event_ids,
                group.object_ids,
            )
            for group in groups
            if group.id not in population
        )
    return _project(
        context,
        operator,
        spec,
        spec.projection,
        unit,
        events,
        objects,
        decisions,
        parents=parents,
        issues=issues,
        partial=partial,
        executions=executions,
        groups=groups,
        population=len(population),
    )


def filter_ocel_frequency(log, spec: OCFrequencyFilterSpec = OCFrequencyFilterSpec()):
    """Filter activity events or object/object-type participation frequencies."""
    operator = "pix.object_centric.filter_frequency"
    context, failure = _prepare_request(log, spec, OCFrequencyFilterSpec, operator)
    if failure is not None:
        return failure
    if spec.object_types is not None and not set(spec.object_types) <= set(
        context.objects_by_type
    ):
        return _invalid(
            operator,
            context,
            spec,
            "unknown_object_type",
            "Object type selection contains undeclared types",
        )
    if spec.entity == "activity":
        counts = Counter(event.type for event in context.log.events)
        eligible_objects = set()
    else:
        eligible_objects = {
            obj.id
            for obj in context.log.objects
            if spec.object_types is None or obj.type in spec.object_types
        }
        relations = [
            relation
            for relation in context.log.e2o
            if relation.object in eligible_objects
            and (spec.qualifiers is None or relation.qualifier in spec.qualifiers)
        ]
        records = [(relation.event, relation.object) for relation in relations]
        if spec.counting == "unique_event_objects":
            records = sorted(set(records))
        if spec.entity == "object":
            counts = Counter({obj: 0 for obj in sorted(eligible_objects)})
            counts.update(obj for _, obj in records)
        else:
            types = (
                set(context.objects_by_type)
                if spec.object_types is None
                else set(spec.object_types)
            )
            counts = Counter({kind: 0 for kind in sorted(types)})
            counts.update(context.objects_by_id[obj].type for _, obj in records)
    chosen, unknown, total = _rank(counts, spec.rule)
    if not spec.positive:
        chosen = set(counts) - chosen - unknown
    if unknown and spec.unknown == "error":
        return _invalid(
            operator,
            context,
            spec,
            "unknown_frequency_share",
            "Zero participation denominator cannot define a frequency share",
        )
    if spec.unknown == "include":
        chosen |= unknown
    issues = (
        (
            ComputeIssue(
                "unknown_frequency_share",
                "Zero participation denominator leaves requested shares unknown",
            ),
        )
        if unknown
        else ()
    )
    decisions = tuple(
        OCSelectionDecision(
            spec.entity,
            entity,
            entity in chosen,
            "unknown_share" if entity in unknown else "frequency_condition",
            count,
            total,
        )
        for entity, count in sorted(counts.items())
    )
    if spec.entity == "activity":
        events = {event.id for event in context.log.events if event.type in chosen}
        objects, unit = _objects_for_events(context, events), "events"
        unknown_events = {
            event.id for event in context.log.events if event.type in unknown
        }
        unknown_objects = set()
    else:
        objects = {
            obj.id
            for obj in context.log.objects
            if obj.id in eligible_objects
            and (obj.id if spec.entity == "object" else obj.type) in chosen
        }
        unknown_objects = {
            obj.id
            for obj in context.log.objects
            if obj.id in eligible_objects
            and (obj.id if spec.entity == "object" else obj.type) in unknown
        }
        events, unit, unknown_events = set(), "objects", set()
    return _project(
        context,
        operator,
        spec,
        spec.projection,
        unit,
        events,
        objects,
        decisions,
        issues=issues,
        partial=bool(unknown),
        unknown_events=unknown_events,
        unknown_objects=unknown_objects,
        population=len(counts),
    )


def filter_ocel_structure(log, spec: OCStructureFilterSpec = OCStructureFilterSpec()):
    """Select E2O whitelist, per-event typed cardinality or observed boundaries."""
    operator = "pix.object_centric.filter_structure"
    context, failure = _prepare_request(log, spec, OCStructureFilterSpec, operator)
    if failure is not None:
        return failure
    selected_types = {
        rule.object_type for rule in (*spec.allowed, *spec.cardinalities)
    } | ({spec.object_type} if spec.object_type else set())
    if not selected_types <= set(context.objects_by_type):
        return _invalid(
            operator,
            context,
            spec,
            "unknown_object_type",
            "Structure predicate references an undeclared object type",
        )
    declared_activities = {kind.name for kind in context.log.event_types}
    if any(not set(rule.activities) <= declared_activities for rule in spec.allowed):
        return _invalid(
            operator,
            context,
            spec,
            "unknown_activity",
            "Activity whitelist references an undeclared event type",
        )
    relations = [
        relation
        for relation in context.log.e2o
        if spec.qualifiers is None or relation.qualifier in spec.qualifiers
    ]
    decisions, issues, unknown_events, unknown_objects = [], [], set(), set()
    relation_mask = None
    if spec.mode == "activity_type_matching":
        allowed = {rule.object_type: set(rule.activities) for rule in spec.allowed}
        relation_mask = set()
        for relation in relations:
            activity, kind = (
                context.events_by_id[relation.event].type,
                context.objects_by_id[relation.object].type,
            )
            matched = activity in allowed.get(kind, set())
            selected = matched if spec.positive else not matched
            if selected:
                relation_mask.add(
                    OCRelationSelection(
                        relation.event, relation.object, relation.qualifier
                    )
                )
            identity = f"{len(relation.event)}:{relation.event}{len(relation.object)}:{relation.object}{len(relation.qualifier)}:{relation.qualifier}"
            decisions.append(
                OCSelectionDecision(
                    "relation",
                    identity,
                    selected,
                    "activity_type_whitelist",
                    None,
                    None,
                    (relation.event,),
                    (relation.object,),
                )
            )
        events = {relation.event_id for relation in relation_mask}
        objects = {relation.object_id for relation in relation_mask}
        if spec.keep_unrelated_events:
            events |= {
                event.id
                for event in context.log.events
                if not context.e2o_by_event[event.id]
            }
    elif spec.mode == "cardinality":
        events = set()
        by_event = {event.id: [] for event in context.log.events}
        for relation in relations:
            by_event[relation.event].append(relation)
        for event in context.log.events:
            counts = Counter()
            for kind in selected_types:
                relevant = [
                    relation
                    for relation in by_event[event.id]
                    if context.objects_by_id[relation.object].type == kind
                ]
                counts[kind] = (
                    len({relation.object for relation in relevant})
                    if spec.counting == "unique_objects"
                    else len(relevant)
                )
            matched = all(
                _range(counts[rule.object_type], rule.minimum, rule.maximum)
                for rule in spec.cardinalities
            )
            selected = matched if spec.positive else not matched
            if selected:
                events.add(event.id)
            for rule in spec.cardinalities:
                identity = f"{len(event.id)}:{event.id}{len(rule.object_type)}:{rule.object_type}"
                decisions.append(
                    OCSelectionDecision(
                        "event_cardinality",
                        identity,
                        selected,
                        "typed_cardinality",
                        counts[rule.object_type],
                        None,
                        (event.id,),
                        tuple(
                            sorted(
                                {
                                    relation.object
                                    for relation in by_event[event.id]
                                    if context.objects_by_id[relation.object].type
                                    == rule.object_type
                                }
                            )
                        ),
                    )
                )
        objects = _objects_for_events(context, events)
    else:
        boundary_events = set()
        for obj in context.objects_by_type[spec.object_type]:
            event_ids = {
                relation.event
                for relation in context.e2o_by_object[obj.id]
                if spec.qualifiers is None or relation.qualifier in spec.qualifiers
            }
            if not event_ids:
                decisions.append(
                    OCSelectionDecision("object", obj.id, False, "no_observed_events")
                )
                continue
            boundary = (min if spec.mode == "start_events" else max)(
                context.events_by_id[event].time for event in event_ids
            )
            tied = sorted(
                event
                for event in event_ids
                if context.events_by_id[event].time == boundary
            )
            if len(tied) > 1 and spec.tie_policy == "reject":
                unknown_events.update(tied)
                unknown_objects.add(obj.id)
                issues.append(
                    ComputeIssue(
                        "ambiguous_observed_boundary",
                        "Equal timestamps do not establish a unique observed boundary",
                        ("object", obj.id),
                    )
                )
                decisions.append(
                    OCSelectionDecision(
                        "object",
                        obj.id,
                        spec.unknown == "include",
                        "unknown_boundary_tie",
                        len(tied),
                        None,
                        tuple(tied),
                        (obj.id,),
                    )
                )
            else:
                chosen = (
                    tied
                    if spec.tie_policy == "all"
                    else (tied[:1] if spec.mode == "start_events" else tied[-1:])
                )
                boundary_events.update(chosen)
                if len(tied) > 1 and spec.tie_policy == "event_id":
                    issues.append(
                        ComputeIssue(
                            "lexical_boundary_order",
                            "Event ID breaks a timestamp tie without asserting causality",
                            ("object", obj.id),
                        )
                    )
                decisions.append(
                    OCSelectionDecision(
                        "object",
                        obj.id,
                        True,
                        "observed_boundary",
                        len(tied),
                        None,
                        tuple(chosen),
                        (obj.id,),
                    )
                )
        # Event membership is existential across objects: a unique boundary
        # witness settles true even when another participating object ties.
        unknown_events -= boundary_events
        if unknown_events and spec.unknown == "error":
            return _invalid(
                operator,
                context,
                spec,
                "unknown_boundary",
                "Boundary tie policy forbids a complete event selection",
                issues=issues,
            )
        events = (
            boundary_events
            if spec.positive
            else set(context.events_by_id) - boundary_events - unknown_events
        )
        if spec.unknown == "include":
            events |= unknown_events
        objects = _objects_for_events(context, events)
    return _project(
        context,
        operator,
        spec,
        spec.projection,
        "events",
        events,
        objects,
        decisions,
        issues=tuple(issues),
        partial=bool(unknown_events),
        relation_mask=relation_mask,
        unknown_events=unknown_events,
        unknown_objects=unknown_objects,
        population=len(relations)
        if spec.mode == "activity_type_matching"
        else len(context.log.events),
    )


def filter_ocel_executions(log, spec: OCExecutionFilterSpec = OCExecutionFilterSpec()):
    """Select membership scopes, exact variants or explicit activity linearizations."""
    operator = "pix.object_centric.filter_executions"
    context, failure = _prepare_request(log, spec, OCExecutionFilterSpec, operator)
    if failure is not None:
        return failure
    if (
        not set(spec.object_ids) <= set(context.objects_by_id)
        or not set(spec.object_types) <= set(context.objects_by_type)
        or not set(spec.activities) <= {kind.name for kind in context.log.event_types}
    ):
        return _invalid(
            operator,
            context,
            spec,
            "unknown_scope_selector",
            "Execution condition references an unknown source entity/type/activity",
        )
    parent, groups = _groups(
        context,
        spec.execution_spec,
        spec.include_isolated_objects
        and spec.mode not in ("variant_ids", "variant_frequency"),
    )
    parents = [parent.computation_id]
    issues = list(parent.issues)
    if parent.value is None:
        return _result(
            operator,
            context,
            spec,
            parent.status,
            None,
            parent.issues,
            parent_computation_ids=tuple(parents),
        )
    group_ids = {group.id for group in groups}
    if not set(spec.execution_ids) <= group_ids:
        return _invalid(
            operator,
            context,
            spec,
            "unknown_execution_id",
            "Execution ID is not part of the requested extraction",
            parents=tuple(parents),
        )
    selected_variants, chosen, unknown, decisions = set(), set(), set(), []
    if spec.mode in ("variant_ids", "variant_frequency"):
        variant_parent = discover_variants(parent, spec.variant_spec)
        parents.append(variant_parent.computation_id)
        if variant_parent.value is None:
            return _result(
                operator,
                context,
                spec,
                variant_parent.status,
                None,
                variant_parent.issues,
                parent_computation_ids=tuple(parents),
            )
        counts = {
            variant.variant_id: variant.frequency
            for variant in variant_parent.value.variants
        }
        if not set(spec.variant_ids) <= set(counts):
            return _invalid(
                operator,
                context,
                spec,
                "unknown_variant_id",
                "Variant ID is not part of the requested exact grouping",
                parents=tuple(parents),
            )
        if spec.mode == "variant_frequency":
            selected_variants, unknown_variants, denominator = _rank(
                counts, spec.frequency
            )
        else:
            selected_variants, unknown_variants, denominator = (
                set(spec.variant_ids),
                set(),
                sum(counts.values()),
            )
        if not spec.positive:
            selected_variants = set(counts) - selected_variants - unknown_variants
        if unknown_variants and spec.unknown == "error":
            return _invalid(
                operator,
                context,
                spec,
                "unknown_variant_share",
                "Variant frequency denominator is unknown",
                parents=tuple(parents),
            )
        if spec.unknown == "include":
            selected_variants |= unknown_variants
        for variant in variant_parent.value.variants:
            if variant.variant_id in selected_variants:
                chosen.update(variant.execution_ids)
            if variant.variant_id in unknown_variants:
                unknown.update(variant.execution_ids)
            decisions.append(
                OCSelectionDecision(
                    "variant",
                    variant.variant_id,
                    variant.variant_id in selected_variants,
                    "exact_incidence_variant",
                    variant.frequency,
                    denominator,
                )
            )
    else:
        for group in groups:
            if spec.mode == "execution_ids":
                matched = group.id in spec.execution_ids
            elif spec.mode == "sequence":
                ordered = sorted(
                    (context.events_by_id[event] for event in group.event_ids),
                    key=lambda event: (event.time, event.id),
                )
                tied = len({event.time for event in ordered}) != len(ordered)
                # A timestamp tie cannot change the activity multiset. Empty
                # or incompatible allowed sets are therefore known false.
                candidates = tuple(
                    sequence
                    for sequence in spec.sequences
                    if Counter(sequence) == Counter(event.type for event in ordered)
                )
                if not candidates:
                    matched = False
                elif tied and spec.sequence_ties == "reject":
                    matched = None
                else:
                    matched = tuple(event.type for event in ordered) in candidates
                    if tied:
                        issues.append(
                            ComputeIssue(
                                "lexical_execution_sequence",
                                "Timestamp ties are linearized by event ID without asserting causality",
                                ("execution", group.id),
                            )
                        )
            else:
                matched = (
                    _range(
                        len(group.event_ids), spec.minimum_events, spec.maximum_events
                    )
                    and _range(
                        len(group.object_ids),
                        spec.minimum_objects,
                        spec.maximum_objects,
                    )
                    and _range(
                        group.relation_count,
                        spec.minimum_relations,
                        spec.maximum_relations,
                    )
                    and set(spec.object_ids) <= set(group.object_ids)
                    and set(spec.object_types)
                    <= {context.objects_by_id[obj].type for obj in group.object_ids}
                    and set(spec.activities)
                    <= {context.events_by_id[event].type for event in group.event_ids}
                )
                if matched and (
                    spec.minimum_duration_us is not None
                    or spec.maximum_duration_us is not None
                ):
                    times = [
                        context.events_by_id[event].time for event in group.event_ids
                    ]
                    if not times:
                        matched = None
                    else:
                        delta = max(times) - min(times)
                        duration = (
                            delta.days * 86400 + delta.seconds
                        ) * 1_000_000 + delta.microseconds
                        matched = _range(
                            duration, spec.minimum_duration_us, spec.maximum_duration_us
                        )
            if matched is None:
                unknown.add(group.id)
                selected = spec.unknown == "include"
                issues.append(
                    ComputeIssue(
                        "unknown_execution_predicate",
                        "Selected ordering or duration cannot be established",
                        ("execution", group.id),
                    )
                )
            else:
                selected = matched if spec.positive else not matched
            if selected:
                chosen.add(group.id)
            decisions.append(
                OCSelectionDecision(
                    "execution",
                    group.id,
                    selected,
                    "unknown" if matched is None else spec.mode,
                    len(group.event_ids),
                    None,
                    group.event_ids,
                    group.object_ids,
                )
            )
    if unknown and spec.unknown == "error":
        return _invalid(
            operator,
            context,
            spec,
            "unknown_execution_selection",
            "Unknown execution predicates are disallowed",
            parents=tuple(parents),
            issues=issues,
        )
    selected_groups = [group for group in groups if group.id in chosen]
    events = {event for group in selected_groups for event in group.event_ids}
    objects = {obj for group in selected_groups for obj in group.object_ids}
    return _project(
        context,
        operator,
        spec,
        spec.projection,
        "executions",
        events,
        objects,
        decisions,
        parents=tuple(parents),
        issues=tuple(issues),
        partial=bool(unknown) or parent.status is ComputeStatus.PARTIAL,
        executions=chosen,
        variants=selected_variants,
        groups=groups,
        unknown_executions=unknown,
        population=len(groups),
    )


def filter_ocel_by_predicate(log, spec: OCPredicateFilterSpec):
    """Materializable typed attribute/as-of/lifecycle/performance selection."""
    operator = "pix.object_centric.filter_by_predicate"
    context, failure = _prepare_request(log, spec, OCPredicateFilterSpec, operator)
    if failure is not None:
        return failure
    parent = evaluate_filter_predicates(context, spec.predicate)
    parents = (parent.computation_id,) if parent.computation_id else ()
    if parent.value is None:
        return _result(
            operator,
            context,
            spec,
            parent.status,
            None,
            parent.issues,
            parent_computation_ids=parents,
        )
    events, objects = (
        set(parent.value.selected_event_ids),
        set(parent.value.selected_object_ids),
    )
    if parent.value.selection_unit == "events":
        objects |= _objects_for_events(context, events)
    decisions = tuple(
        OCSelectionDecision(
            item.entity_kind,
            item.entity_id,
            item.selected,
            item.reason,
            None,
            None,
            item.witness_event_ids,
            (item.entity_id,) if item.entity_kind == "object" else (),
        )
        for item in parent.value.decisions
    )
    return _project(
        context,
        operator,
        spec,
        spec.projection,
        parent.value.selection_unit,
        events,
        objects,
        decisions,
        parents=parents,
        issues=parent.issues,
        partial=parent.status is ComputeStatus.PARTIAL,
        unknown_events=parent.value.unknown_event_ids,
        unknown_objects=parent.value.unknown_object_ids,
        population=len(parent.value.decisions),
    )


def materialize_advanced_sublog(
    source, result: ComputationResult[OCAdvancedFilterResult]
) -> OCEL:
    """Verify every advanced decision, then preserve surviving canonical facts."""
    if not isinstance(result, ComputationResult) or not isinstance(
        result.value, OCAdvancedFilterResult
    ):
        raise TypeError("result must be an available advanced OCEL selection")
    context, issues = _prepare(source)
    if context is None:
        raise ValueError(f"invalid source: {issues}")
    if result.source_digest != context.source_digest:
        raise ValueError("source digest differs from selection")
    functions = {
        "pix.object_centric.sample_ocel": sample_ocel,
        "pix.object_centric.filter_frequency": filter_ocel_frequency,
        "pix.object_centric.filter_structure": filter_ocel_structure,
        "pix.object_centric.filter_executions": filter_ocel_executions,
        "pix.object_centric.filter_by_predicate": filter_ocel_by_predicate,
    }
    function = functions.get(result.operator_id)
    if function is None or function(context, result.spec) != result:
        raise ValueError(
            "advanced selection identity or evidence does not match request"
        )
    base = filter_ocel(context, result.value.selection_spec)
    if base.value != result.value.selection:
        raise ValueError("projection evidence does not match advanced selection")
    projected = materialize_sublog(context, base)
    allowed = set(result.value.retained_relations)
    relations = tuple(
        relation
        for relation in projected.e2o
        if OCRelationSelection(relation.event, relation.object, relation.qualifier)
        in allowed
    )
    built = build(
        event_types=projected.event_types,
        object_types=projected.object_types,
        events=projected.events,
        objects=projected.objects,
        e2o=relations,
        o2o=projected.o2o,
    )
    if built.ocel is None:
        raise ValueError("advanced projection is not valid canonical OCEL")
    return replace(built.ocel, import_info=context.log.import_info)


RESULT_SCHEMAS = {
    "pix.object_centric.sample_ocel": (
        "ocel-sample",
        OCSamplingSpec,
        OCAdvancedFilterResult,
    ),
    "pix.object_centric.filter_frequency": (
        "ocel-frequency-selection",
        OCFrequencyFilterSpec,
        OCAdvancedFilterResult,
    ),
    "pix.object_centric.filter_structure": (
        "ocel-structure-selection",
        OCStructureFilterSpec,
        OCAdvancedFilterResult,
    ),
    "pix.object_centric.filter_executions": (
        "ocel-execution-selection",
        OCExecutionFilterSpec,
        OCAdvancedFilterResult,
    ),
    "pix.object_centric.filter_by_predicate": (
        "ocel-predicate-selection",
        OCPredicateFilterSpec,
        OCAdvancedFilterResult,
    ),
}

__all__ = [
    "OCProjectionPolicy",
    "OCFrequencyRule",
    "OCSamplingSpec",
    "OCFrequencyFilterSpec",
    "OCTypeActivityRule",
    "OCTypeCardinality",
    "OCStructureFilterSpec",
    "OCExecutionFilterSpec",
    "OCPredicateFilterSpec",
    "OCRelationSelection",
    "OCSelectionDecision",
    "OCSelectionGroup",
    "OCAdvancedFilterResult",
    "sample_ocel",
    "filter_ocel_frequency",
    "filter_ocel_structure",
    "filter_ocel_executions",
    "filter_ocel_by_predicate",
    "materialize_advanced_sublog",
]
