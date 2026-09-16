"""Reversible OCEL OLAP type refinements over immutable canonical facts.

Drill-down fixes an object's subtype from an explicitly selected as-of attribute
snapshot. Unfold refines event types by qualified participation in an object
type; it does not duplicate events. Their inverses require the forward evidence,
not a guess from a display-name prefix. No event, attribute history, or relation
fact is dropped. Native OCEL type declarations remain valid after each change.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.analysis import E2OEvidence, _text
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
    computation_identity,
)
from pix.object_centric.relations import (
    AttributeAsOfSpec,
    OCELScalar,
    object_attributes_as_of,
)
from pix.ocel import OCEL, EventType, ObjectType, build

DRILL_DOWN_OPERATOR_ID = "pix.object_centric.drill_down"
ROLL_UP_OPERATOR_ID = "pix.object_centric.roll_up"
UNFOLD_OPERATOR_ID = "pix.object_centric.unfold"
FOLD_OPERATOR_ID = "pix.object_centric.fold"


@dataclass(frozen=True, slots=True)
class DrillDownSpec:
    """Fix subtypes at inclusive ``as_of``; future assignments remain history.

    Missing values have no observed assignment at/before that time. Empty text
    also remains unsplit, matching the source OLAP definition. Zero and False
    are defined values. ``retain_parent`` keeps unknown objects and reports
    partial classification; ``reject`` declines the transformation.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_type: str
    attribute: str
    as_of: datetime
    missing_policy: Literal["retain_parent", "reject"] = "retain_parent"

    def __post_init__(self) -> None:
        _text(self.object_type, "object_type")
        _text(self.attribute, "attribute")
        if not isinstance(self.as_of, datetime):
            raise TypeError("as_of must be datetime")
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of requires timezone")
        object.__setattr__(self, "as_of", self.as_of.astimezone(timezone.utc))
        if self.missing_policy not in ("retain_parent", "reject"):
            raise ValueError("unknown missing_policy")


@dataclass(frozen=True, slots=True)
class UnfoldSpec:
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    event_type: str
    object_type: str
    qualifiers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        _text(self.event_type, "event_type")
        _text(self.object_type, "object_type")
        if self.qualifiers is not None:
            if not isinstance(self.qualifiers, tuple):
                raise TypeError("qualifiers must be a tuple or None")
            for qualifier in self.qualifiers:
                _text(qualifier, "qualifier", blank=True)
            object.__setattr__(self, "qualifiers", tuple(sorted(set(self.qualifiers))))


@dataclass(frozen=True, slots=True)
class CubeTypeChange:
    entity: Literal["object", "event"]
    entity_id: str
    before_type: str
    after_type: str
    attribute_value: OCELScalar | None = None
    assigned_at: datetime | None = None
    relations: tuple[E2OEvidence, ...] = ()

    def __post_init__(self) -> None:
        if self.entity not in ("object", "event"):
            raise ValueError("entity must be object or event")
        for field in ("entity_id", "before_type", "after_type"):
            _text(getattr(self, field), field)
        if self.before_type == self.after_type:
            raise ValueError("a type change must change the type")
        if (self.attribute_value is None) != (self.assigned_at is None):
            raise ValueError("attribute value and assignment timestamp must coexist")
        if self.attribute_value is not None and not isinstance(
            self.attribute_value, OCELScalar
        ):
            raise TypeError("attribute_value must be OCELScalar")
        if self.assigned_at is not None and (
            not isinstance(self.assigned_at, datetime)
            or self.assigned_at.tzinfo is None
            or self.assigned_at.utcoffset() is None
        ):
            raise ValueError("assignment time must be timezone-aware")
        if not isinstance(self.relations, tuple) or any(
            not isinstance(r, E2OEvidence) for r in self.relations
        ):
            raise TypeError("relations must be a tuple of E2OEvidence")


@dataclass(frozen=True, slots=True)
class CubeUnclassified:
    object_id: str
    reason: Literal["no_assignment_as_of", "empty_attribute_value"]

    def __post_init__(self) -> None:
        _text(self.object_id, "object_id")
        if self.reason not in ("no_assignment_as_of", "empty_attribute_value"):
            raise ValueError("unknown classification reason")


@dataclass(frozen=True, slots=True)
class CubePlan:
    """Source-bound relabeling sidecar; canonical facts stay in the OCEL."""

    operation: Literal["drill_down", "roll_up", "unfold", "fold"]
    output_digest: str
    changes: tuple[CubeTypeChange, ...]
    added_object_types: tuple[ObjectType, ...] = ()
    added_event_types: tuple[EventType, ...] = ()
    removed_object_types: tuple[ObjectType, ...] = ()
    removed_event_types: tuple[EventType, ...] = ()
    unclassified: tuple[CubeUnclassified, ...] = ()

    def __post_init__(self) -> None:
        if self.operation not in ("drill_down", "roll_up", "unfold", "fold"):
            raise ValueError("unknown cube operation")
        _text(self.output_digest, "output_digest")
        for name, kind in (
            ("changes", CubeTypeChange),
            ("added_object_types", ObjectType),
            ("added_event_types", EventType),
            ("removed_object_types", ObjectType),
            ("removed_event_types", EventType),
            ("unclassified", CubeUnclassified),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(v, kind) for v in values
            ):
                raise TypeError(f"{name} must be a tuple of {kind.__name__}")
        keys = tuple((change.entity, change.entity_id) for change in self.changes)
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate entity changes")
        if len({entry.object_id for entry in self.unclassified}) != len(
            self.unclassified
        ):
            raise ValueError("duplicate unclassified objects")


@dataclass(frozen=True, slots=True)
class CubeInverseSpec:
    """Validated forward evidence is part of the inverse request identity."""

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    forward_spec: DrillDownSpec | UnfoldSpec
    forward_plan: CubePlan
    forward_source_digest: str
    forward_computation_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.forward_spec, (DrillDownSpec, UnfoldSpec)):
            raise TypeError("forward_spec must describe drill_down or unfold")
        if not isinstance(self.forward_plan, CubePlan):
            raise TypeError("forward_plan must be CubePlan")
        _text(self.forward_source_digest, "forward_source_digest")
        _text(self.forward_computation_id, "forward_computation_id")
        expected = (
            "drill_down" if isinstance(self.forward_spec, DrillDownSpec) else "unfold"
        )
        if self.forward_plan.operation != expected:
            raise ValueError("forward plan and request operation differ")


def _name(parent: str, operation: str, discriminator: object) -> str:
    encoded = json.dumps(
        _identity_value((parent, operation, discriminator)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return f"{parent}::pix.{operation}:" + sha256(encoded).hexdigest()


def _apply(
    context: ComputationContext,
    changes: tuple[CubeTypeChange, ...],
    added_objects: tuple[ObjectType, ...] = (),
    added_events: tuple[EventType, ...] = (),
    removed_objects: tuple[ObjectType, ...] = (),
    removed_events: tuple[EventType, ...] = (),
) -> ComputationContext:
    source = context.log
    object_changes = {c.entity_id: c for c in changes if c.entity == "object"}
    event_changes = {c.entity_id: c for c in changes if c.entity == "event"}
    for change in changes:
        entities = (
            context.objects_by_id if change.entity == "object" else context.events_by_id
        )
        if (
            change.entity_id not in entities
            or entities[change.entity_id].type != change.before_type
        ):
            raise ValueError("cube type-change witness differs from source")

    object_types = {t.name: t for t in source.object_types}
    event_types = {t.name: t for t in source.event_types}
    for declared, removed, added in (
        (object_types, removed_objects, added_objects),
        (event_types, removed_events, added_events),
    ):
        for item in removed:
            if declared.get(item.name) != item:
                raise ValueError("cube removed declaration differs from source")
            del declared[item.name]
        for item in added:
            if item.name in declared:
                raise ValueError("cube type name collides with existing declaration")
            declared[item.name] = item
    built = build(
        object_types=tuple(object_types.values()),
        event_types=tuple(event_types.values()),
        objects=tuple(
            replace(o, type=object_changes[o.id].after_type)
            if o.id in object_changes
            else o
            for o in source.objects
        ),
        events=tuple(
            replace(e, type=event_changes[e.id].after_type)
            if e.id in event_changes
            else e
            for e in source.events
        ),
        e2o=source.e2o,
        o2o=source.o2o,
    )
    if built.ocel is None:
        raise ValueError("cube relabeling violates canonical OCEL constraints")
    return ComputationContext(replace(built.ocel, import_info=source.import_info))


def _forward(context: ComputationContext, spec: DrillDownSpec | UnfoldSpec):
    changes = []
    objects = {}
    events = {}
    missing = []
    issues = []
    parents = ()
    object_declarations = {t.name: t for t in context.log.object_types}
    event_declarations = {t.name: t for t in context.log.event_types}
    if spec.object_type not in object_declarations:
        return (
            None,
            None,
            (ComputeIssue("unknown_object_type", "Selected type is not declared"),),
            parents,
        )
    if isinstance(spec, DrillDownSpec):
        declaration = object_declarations[spec.object_type]
        if spec.attribute not in {a.name for a in declaration.attributes}:
            return (
                None,
                None,
                (
                    ComputeIssue(
                        "unknown_object_attribute",
                        "Attribute is not declared for selected type",
                    ),
                ),
                parents,
            )
        snapshot = object_attributes_as_of(
            context,
            AttributeAsOfSpec(
                spec.as_of,
                tuple(o.id for o in context.objects_by_type[spec.object_type]),
                (spec.attribute,),
                True,
            ),
        )
        parents = (snapshot.computation_id,)
        for observation in snapshot.value.values:
            if observation.value is None or (
                observation.value.kind == "string"
                and observation.value.text_value == ""
            ):
                reason = (
                    "no_assignment_as_of"
                    if observation.value is None
                    else "empty_attribute_value"
                )
                missing.append(CubeUnclassified(observation.object_id, reason))
                issues.append(
                    ComputeIssue(
                        reason,
                        "Object keeps parent type without a defined snapshot value",
                        ("object", observation.object_id, "attribute", spec.attribute),
                    )
                )
                continue
            grouping_value = observation.value
            if grouping_value.kind == "float" and grouping_value.float_value == 0:
                grouping_value = replace(grouping_value, float_value=0.0)
            target = _name(
                spec.object_type, "drill_down", (spec.attribute, grouping_value)
            )
            if target in object_declarations:
                return (
                    None,
                    None,
                    (
                        ComputeIssue(
                            "type_name_collision", "Generated subtype already exists"
                        ),
                    ),
                    parents,
                )
            objects[target] = ObjectType(target, declaration.attributes)
            changes.append(
                CubeTypeChange(
                    "object",
                    observation.object_id,
                    spec.object_type,
                    target,
                    observation.value,
                    observation.assigned_at,
                )
            )
        if missing and spec.missing_policy == "reject":
            return None, None, tuple(issues), parents
        operation = "drill_down"
    else:
        if spec.event_type not in event_declarations:
            return (
                None,
                None,
                (
                    ComputeIssue(
                        "unknown_event_type", "Selected event type is not declared"
                    ),
                ),
                parents,
            )
        evidence = {}
        allowed = None if spec.qualifiers is None else set(spec.qualifiers)
        for relation in context.log.e2o:
            if (
                context.events_by_id[relation.event].type == spec.event_type
                and context.objects_by_id[relation.object].type == spec.object_type
                and (allowed is None or relation.qualifier in allowed)
            ):
                evidence.setdefault(relation.event, []).append(
                    E2OEvidence(relation.event, relation.object, relation.qualifier)
                )
        if evidence:
            target = _name(spec.event_type, "unfold", spec.object_type)
            if target in event_declarations:
                return (
                    None,
                    None,
                    (
                        ComputeIssue(
                            "type_name_collision",
                            "Generated activity subtype already exists",
                        ),
                    ),
                    parents,
                )
            events[target] = EventType(
                target, event_declarations[spec.event_type].attributes
            )
            for event_id, records in sorted(evidence.items()):
                changes.append(
                    CubeTypeChange(
                        "event",
                        event_id,
                        spec.event_type,
                        target,
                        relations=tuple(
                            sorted(
                                records, key=lambda r: (r.event, r.object, r.qualifier)
                            )
                        ),
                    )
                )
        operation = "unfold"
    changes = tuple(sorted(changes, key=lambda c: (c.entity, c.entity_id)))
    objects = tuple(objects[name] for name in sorted(objects))
    events = tuple(events[name] for name in sorted(events))
    output = _apply(context, changes, objects, events)
    plan = CubePlan(
        operation,
        output.source_digest,
        changes,
        objects,
        events,
        unclassified=tuple(missing),
    )
    return output, plan, tuple(issues), parents


def _forward_result(log, spec, operator):
    context, issues = _prepare(log)
    if context is None:
        return _result(operator, None, spec, ComputeStatus.INVALID_INPUT, None, issues)
    _, plan, issues, parents = _forward(context, spec)
    status = (
        ComputeStatus.UNAVAILABLE
        if plan is None
        else (ComputeStatus.PARTIAL if plan.unclassified else ComputeStatus.COMPUTED)
    )
    return _result(
        operator, context, spec, status, plan, issues, parent_computation_ids=parents
    )


def drill_down(
    log: OCEL | ComputationContext, spec: DrillDownSpec
) -> ComputationResult[CubePlan]:
    """Plan object-type refinement using the inclusive as-of attribute snapshot."""
    if not isinstance(spec, DrillDownSpec):
        raise TypeError("spec must be DrillDownSpec")
    return _forward_result(log, spec, DRILL_DOWN_OPERATOR_ID)


def unfold(
    log: OCEL | ComputationContext, spec: UnfoldSpec
) -> ComputationResult[CubePlan]:
    """Plan event-type refinement by qualified object-type participation.

    Multiple matching objects or qualifiers produce one renamed event, with all
    qualifying relation evidence. Every original relation remains in the OCEL.
    """
    if not isinstance(spec, UnfoldSpec):
        raise TypeError("spec must be UnfoldSpec")
    return _forward_result(log, spec, UNFOLD_OPERATOR_ID)


def _inverse(context: ComputationContext, spec: CubeInverseSpec):
    forward = spec.forward_plan
    if forward.output_digest != context.source_digest:
        raise ValueError("source digest differs from forward output")
    changes = tuple(
        replace(c, before_type=c.after_type, after_type=c.before_type)
        for c in forward.changes
    )
    restored = _apply(
        context,
        changes,
        removed_objects=forward.added_object_types,
        removed_events=forward.added_event_types,
    )
    if restored.source_digest != spec.forward_source_digest:
        raise ValueError("restored source digest differs from forward source")
    expected = (
        drill_down(restored, spec.forward_spec)
        if isinstance(spec.forward_spec, DrillDownSpec)
        else unfold(restored, spec.forward_spec)
    )
    if (
        expected.value != forward
        or expected.computation_id != spec.forward_computation_id
    ):
        raise ValueError("forward plan does not reproduce from restored source")
    operation = "roll_up" if isinstance(spec.forward_spec, DrillDownSpec) else "fold"
    plan = CubePlan(
        operation,
        restored.source_digest,
        changes,
        removed_object_types=forward.added_object_types,
        removed_event_types=forward.added_event_types,
    )
    return restored, plan


def _inverse_result(log, spec, operator):
    context, issues = _prepare(log)
    if context is None:
        return _result(operator, None, spec, ComputeStatus.INVALID_INPUT, None, issues)
    parents = (spec.forward_computation_id,)
    try:
        _, plan = _inverse(context, spec)
    except ValueError as error:
        return _result(
            operator,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("invalid_cube_provenance", str(error)),),
            parent_computation_ids=parents,
        )
    return _result(
        operator,
        context,
        spec,
        ComputeStatus.COMPUTED,
        plan,
        parent_computation_ids=parents,
    )


def _inverse_spec(forward, kind):
    if not isinstance(forward, ComputationResult):
        raise TypeError("forward must be a ComputationResult")
    operator = DRILL_DOWN_OPERATOR_ID if kind is DrillDownSpec else UNFOLD_OPERATOR_ID
    if (
        forward.operator_id != operator
        or not isinstance(forward.spec, kind)
        or not isinstance(forward.value, CubePlan)
        or forward.status not in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL)
    ):
        raise ValueError("inverse requires matching successful forward cube evidence")
    if (
        computation_identity(
            forward.operator_id,
            forward.operator_version,
            forward.source_digest,
            forward.spec,
            forward.parent_computation_ids,
        )
        != forward.computation_id
    ):
        raise ValueError("forward request identity is inconsistent")
    return CubeInverseSpec(
        forward.spec, forward.value, forward.source_digest, forward.computation_id
    )


def roll_up(
    log: OCEL | ComputationContext, forward: ComputationResult[CubePlan]
) -> ComputationResult[CubePlan]:
    """Plan exact inverse of a source-bound drill-down; no prefix-name guessing."""
    return _inverse_result(
        log, _inverse_spec(forward, DrillDownSpec), ROLL_UP_OPERATOR_ID
    )


def fold(
    log: OCEL | ComputationContext, forward: ComputationResult[CubePlan]
) -> ComputationResult[CubePlan]:
    """Plan exact inverse of unfold, preserving pre-existing activity names."""
    return _inverse_result(log, _inverse_spec(forward, UnfoldSpec), FOLD_OPERATOR_ID)


def materialize_cube(
    source: OCEL | ComputationContext, result: ComputationResult[CubePlan]
) -> OCEL:
    """Re-evaluate a persisted plan against its exact source before materializing.

    Forward and inverse evidence, request identity and output digest must match.
    A changed intermediate log must not be silently rolled back with a stale
    sidecar. The returned log retains original import metadata and all raw facts.
    """
    if not isinstance(result, ComputationResult) or not isinstance(
        result.value, CubePlan
    ):
        raise TypeError("result must be a successful cube ComputationResult")
    context, issues = _prepare(source)
    if context is None:
        raise ValueError(f"invalid cube source: {issues}")
    if result.source_digest != context.source_digest:
        raise ValueError("source digest does not match cube result")
    if isinstance(result.spec, DrillDownSpec):
        expected = drill_down(context, result.spec)
        output, _, _, _ = _forward(context, result.spec)
    elif isinstance(result.spec, UnfoldSpec):
        expected = unfold(context, result.spec)
        output, _, _, _ = _forward(context, result.spec)
    elif isinstance(result.spec, CubeInverseSpec):
        operator = (
            ROLL_UP_OPERATOR_ID
            if isinstance(result.spec.forward_spec, DrillDownSpec)
            else FOLD_OPERATOR_ID
        )
        expected = _inverse_result(context, result.spec, operator)
        output, _ = _inverse(context, result.spec)
    else:
        raise ValueError("unrecognized cube request")
    if expected != result or output is None:
        raise ValueError("cube request identity or transformation evidence differs")
    return output.log


RESULT_SCHEMAS = {
    DRILL_DOWN_OPERATOR_ID: ("ocel-drill-down", DrillDownSpec, CubePlan),
    ROLL_UP_OPERATOR_ID: ("ocel-roll-up", CubeInverseSpec, CubePlan),
    UNFOLD_OPERATOR_ID: ("ocel-unfold", UnfoldSpec, CubePlan),
    FOLD_OPERATOR_ID: ("ocel-fold", CubeInverseSpec, CubePlan),
}

__all__ = (
    "DrillDownSpec",
    "UnfoldSpec",
    "CubeTypeChange",
    "CubeUnclassified",
    "CubePlan",
    "CubeInverseSpec",
    "drill_down",
    "roll_up",
    "unfold",
    "fold",
    "materialize_cube",
)
