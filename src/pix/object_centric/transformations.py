"""Auditable OCEL transformations, with immutable plans and checked materialization.

Canonical source facts are never mutated. Deduplication, merging and explosion
are explicit derived views; every source event retains a target-ID lineage.
Object histories, E2O qualifiers and O2O facts survive unless a selected policy
explicitly changes that dimension. No PM4Py/OCPA runtime dependency is used.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime
from hashlib import sha256
from typing import ClassVar

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
)
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    build,
    canonical_digest,
)


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _selection(value, name):
    if value is not None and (
        not isinstance(value, tuple) or not all(isinstance(v, str) for v in value)
    ):
        raise TypeError(f"{name} must be a tuple of strings or None")


def _collision(value):
    if value not in ("reject", "suffix"):
        raise ValueError("id_collision must be reject or suffix")


@dataclass(frozen=True, slots=True)
class OCELDeduplicationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.deduplicate.spec"
    mode: str = "exact_events"
    preserve_orphaned_events: bool = True

    def __post_init__(self):
        if self.mode not in ("exact_events", "qualified_participation"):
            raise ValueError("unknown deduplication mode")
        if type(self.preserve_orphaned_events) is not bool:
            raise TypeError("preserve_orphaned_events must be Boolean")


@dataclass(frozen=True, slots=True)
class OCELMergeSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.merge_events.spec"
    grouping: str = "activity_timestamp"
    attribute_policy: str = "require_equal"
    id_prefix: str = "pix:merged:"
    id_collision: str = "reject"

    def __post_init__(self):
        if self.grouping not in ("activity_timestamp", "shared_object_components"):
            raise ValueError("unknown merge grouping")
        if self.attribute_policy not in ("require_equal", "union_nonconflicting"):
            raise ValueError("unknown event attribute policy")
        _text(self.id_prefix, "id_prefix")
        _collision(self.id_collision)


@dataclass(frozen=True, slots=True)
class OCELAttributePromotionSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.promote_attribute.spec"
    attribute: str
    object_type: str
    activities: tuple[str, ...] | None = None
    type_policy: str = "split_primitive_types"
    qualifier: str = "pix:promoted"
    id_prefix: str = "pix:attribute:"
    id_collision: str = "reject"
    missing: str = "skip"
    remove_event_attribute: bool = False
    reuse_compatible_type: bool = False

    def __post_init__(self):
        _text(self.attribute, "attribute")
        _text(self.object_type, "object_type")
        _text(self.id_prefix, "id_prefix")
        _selection(self.activities, "activities")
        if not isinstance(self.qualifier, str):
            raise TypeError("qualifier must be text")
        if self.type_policy not in ("split_primitive_types", "require_uniform"):
            raise ValueError("unknown type policy")
        if self.missing not in ("skip", "reject"):
            raise ValueError("missing must be skip or reject")
        for value in (self.remove_event_attribute, self.reuse_compatible_type):
            if type(value) is not bool:
                raise TypeError("promotion flags must be Boolean")
        _collision(self.id_collision)


@dataclass(frozen=True, slots=True)
class OCELExplodeSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.explode.spec"
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    id_prefix: str = "pix:exploded:"
    id_collision: str = "reject"
    isolated_events: str = "preserve"

    def __post_init__(self):
        _selection(self.object_types, "object_types")
        _selection(self.qualifiers, "qualifiers")
        _text(self.id_prefix, "id_prefix")
        _collision(self.id_collision)
        if self.isolated_events not in ("preserve", "drop"):
            raise ValueError("isolated_events must be preserve or drop")


@dataclass(frozen=True, slots=True)
class OCELParentChildSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.parent_child.spec"
    child_type: str
    parent_type: str
    attribute: str = "parent_id"
    qualifiers: tuple[str, ...] | None = None
    assignment: str = "unique_parent"
    output: str = "attribute_history"
    relation_qualifier: str = "pix:parent"

    def __post_init__(self):
        _text(self.child_type, "child_type")
        _text(self.parent_type, "parent_type")
        _text(self.attribute, "attribute")
        if self.child_type == self.parent_type:
            raise ValueError("parent and child types must differ")
        _selection(self.qualifiers, "qualifiers")
        if self.assignment not in ("unique_parent", "temporal"):
            raise ValueError("unknown parent assignment policy")
        if self.output not in ("attribute_history", "o2o", "both"):
            raise ValueError("unknown parent reference output")
        if not isinstance(self.relation_qualifier, str):
            raise TypeError("relation_qualifier must be text")


@dataclass(frozen=True, slots=True)
class EventLineage:
    source_event_id: str
    target_event_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PromotedObject:
    object_id: str
    object_type: str
    source_event_ids: tuple[str, ...]
    source_attribute: str
    value_type: str
    value_lexical: str
    first_observation: datetime


@dataclass(frozen=True, slots=True)
class ParentAssignment:
    child_id: str
    parent_id: str
    time: datetime
    witness_event_ids: tuple[str, ...]
    history_added: bool


@dataclass(frozen=True, slots=True)
class OCELTransformation:
    operation: str
    target_digest: str
    event_lineage: tuple[EventLineage, ...]
    promoted_objects: tuple[PromotedObject, ...]
    parent_assignments: tuple[ParentAssignment, ...]
    added_e2o: tuple[E2O, ...]
    removed_e2o: tuple[E2O, ...]
    added_o2o: tuple[O2O, ...]
    added_object_types: tuple[str, ...]
    modified_object_types: tuple[str, ...]
    skipped_event_ids: tuple[str, ...]
    source_event_count: int
    target_event_count: int
    source_object_count: int
    target_object_count: int


class _CannotTransform(Exception):
    def __init__(self, code, message, at=()):
        self.issue = ComputeIssue(code, message, at)


def _key(value):
    return json.dumps(
        _identity_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _fresh_id(prefix, identity, occupied, policy):
    candidate = prefix + sha256(_key(identity).encode("utf-8")).hexdigest()
    if candidate not in occupied:
        occupied.add(candidate)
        return candidate
    if policy == "reject":
        raise _CannotTransform(
            "generated_id_collision",
            "Generated identifier already exists; source is unchanged.",
            (candidate,),
        )
    index = 1
    while f"{candidate}:{index}" in occupied:
        index += 1
    candidate = f"{candidate}:{index}"
    occupied.add(candidate)
    return candidate


def _validated(
    source, *, events=None, objects=None, e2o=None, o2o=None, object_types=None
):
    built = build(
        event_types=source.event_types,
        object_types=source.object_types if object_types is None else object_types,
        events=source.events if events is None else events,
        objects=source.objects if objects is None else objects,
        e2o=source.e2o if e2o is None else e2o,
        o2o=source.o2o if o2o is None else o2o,
    )
    if built.ocel is None:
        raise _CannotTransform(
            "invalid_derived_ocel",
            "Derived OCEL did not pass canonical validation.",
            tuple(issue.code for issue in built.report.errors),
        )
    return replace(built.ocel, import_info=source.import_info)


def _evidence(source, target, operation, mapping, promoted=(), parents=(), skipped=()):
    source_types = {t.name: t for t in source.object_types}
    return OCELTransformation(
        operation,
        canonical_digest(target).identifier,
        tuple(
            EventLineage(event.id, tuple(sorted(mapping[event.id])))
            for event in source.events
        ),
        tuple(promoted),
        tuple(parents),
        tuple(
            sorted(
                set(target.e2o) - set(source.e2o),
                key=lambda r: (r.event, r.object, r.qualifier),
            )
        ),
        tuple(
            sorted(
                set(source.e2o) - set(target.e2o),
                key=lambda r: (r.event, r.object, r.qualifier),
            )
        ),
        tuple(
            sorted(
                set(target.o2o) - set(source.o2o),
                key=lambda r: (r.source, r.target, r.qualifier),
            )
        ),
        tuple(t.name for t in target.object_types if t.name not in source_types),
        tuple(
            t.name
            for t in target.object_types
            if t.name in source_types and t != source_types[t.name]
        ),
        tuple(sorted(skipped)),
        len(source.events),
        len(target.events),
        len(source.objects),
        len(target.objects),
    )


def _deduplicate(context, spec):
    source = context.log
    mapping = {e.id: {e.id} for e in source.events}
    if spec.mode == "exact_events":
        groups = defaultdict(list)
        for event in source.events:
            incidence = tuple(
                sorted((r.object, r.qualifier) for r in context.e2o_by_event[event.id])
            )
            groups[_key((event.type, event.time, event.attributes, incidence))].append(
                event
            )
        retained = set()
        for group in groups.values():
            representative = min(e.id for e in group)
            retained.add(representative)
            for event in group:
                mapping[event.id] = {representative}
        events = tuple(e for e in source.events if e.id in retained)
        relations = tuple(r for r in source.e2o if r.event in retained)
    else:
        representatives, relations = {}, []
        source_has_relation = {r.event for r in source.e2o}
        equivalent_targets = defaultdict(set)
        for relation in sorted(
            source.e2o, key=lambda r: (r.event, r.object, r.qualifier)
        ):
            event = context.events_by_id[relation.event]
            identity = _key(
                (
                    event.type,
                    event.time,
                    event.attributes,
                    relation.object,
                    relation.qualifier,
                )
            )
            if identity not in representatives:
                representatives[identity] = relation.event
                relations.append(relation)
            equivalent_targets[relation.event].add(representatives[identity])
        retained = {r.event for r in relations}
        events = tuple(
            e
            for e in source.events
            if spec.preserve_orphaned_events
            or e.id not in source_has_relation
            or e.id in retained
        )
        event_ids = {e.id for e in events}
        for event in source.events:
            mapping[event.id] = (
                {event.id} if event.id in event_ids else set()
            ) | equivalent_targets[event.id]
    target = _validated(source, events=events, e2o=relations)
    return target, _evidence(source, target, "deduplicate", mapping)


def _merge(context, spec):
    source = context.log
    buckets = defaultdict(list)
    for event in source.events:
        buckets[(event.type, event.time)].append(event)
    groups = []
    for bucket in buckets.values():
        if spec.grouping == "activity_timestamp":
            groups.append(bucket)
            continue
        parents = {e.id: e.id for e in bucket}

        def find(event_id):
            while parents[event_id] != event_id:
                parents[event_id] = parents[parents[event_id]]
                event_id = parents[event_id]
            return event_id

        by_object = defaultdict(list)
        for event in bucket:
            for relation in context.e2o_by_event[event.id]:
                by_object[relation.object].append(event.id)
        for ids in by_object.values():
            anchor = ids[0]
            for event_id in ids[1:]:
                left, right = find(anchor), find(event_id)
                parents[max(left, right)] = min(left, right)
        components = defaultdict(list)
        for event in bucket:
            components[find(event.id)].append(event)
        groups.extend(components.values())
    occupied, events, mapping = set(context.events_by_id), [], {}
    for group in sorted(groups, key=lambda items: min(e.id for e in items)):
        if len(group) == 1:
            events.append(group[0])
            mapping[group[0].id] = {group[0].id}
            continue
        attributes = {}
        if (
            spec.attribute_policy == "require_equal"
            and len({_key(e.attributes) for e in group}) != 1
        ):
            raise _CannotTransform(
                "event_attribute_conflict",
                "Merged events must have identical attributes under require_equal.",
                tuple(sorted(e.id for e in group)),
            )
        for event in group:
            for attribute in event.attributes:
                if attribute.name in attributes and _key(
                    attributes[attribute.name].value
                ) != _key(attribute.value):
                    raise _CannotTransform(
                        "event_attribute_conflict",
                        "Conflicting typed values cannot be merged without information loss.",
                        (attribute.name,) + tuple(sorted(e.id for e in group)),
                    )
                attributes[attribute.name] = attribute
        ids = tuple(sorted(e.id for e in group))
        identifier = _fresh_id(
            spec.id_prefix,
            (group[0].type, group[0].time, ids),
            occupied,
            spec.id_collision,
        )
        events.append(
            Event(identifier, group[0].type, group[0].time, tuple(attributes.values()))
        )
        for event in group:
            mapping[event.id] = {identifier}
    relations = {
        E2O(next(iter(mapping[r.event])), r.object, r.qualifier) for r in source.e2o
    }
    target = _validated(source, events=events, e2o=relations)
    return target, _evidence(source, target, "merge_events", mapping)


def _value_type(value):
    if isinstance(value, bool):
        return ValueType.BOOLEAN, "true" if value else "false"
    if isinstance(value, int):
        return ValueType.INTEGER, str(value)
    if isinstance(value, float):
        return ValueType.FLOAT, value.hex()
    if isinstance(value, datetime):
        return ValueType.TIME, value.isoformat(timespec="microseconds")
    return ValueType.STRING, value


def _promote(context, spec):
    source = context.log
    if spec.activities is not None and set(spec.activities) - {
        t.name for t in source.event_types
    }:
        raise _CannotTransform(
            "unknown_activity", "Promotion selection contains undeclared activity."
        )
    values, skipped = defaultdict(list), []
    for event in source.events:
        if spec.activities is not None and event.type not in spec.activities:
            continue
        attribute = next(
            (a for a in event.attributes if a.name == spec.attribute), None
        )
        if attribute is None:
            if spec.missing == "reject":
                raise _CannotTransform(
                    "promotion_attribute_missing",
                    "Selected event has no promotion attribute.",
                    (event.id, spec.attribute),
                )
            skipped.append(event.id)
            continue
        kind, lexical = _value_type(attribute.value)
        values[(kind, lexical)].append((event, attribute.value))
    kinds = {key[0] for key in values}
    if spec.type_policy == "require_uniform" and len(kinds) > 1:
        raise _CannotTransform(
            "mixed_promotion_types",
            "A uniform OCEL object attribute cannot contain multiple primitive types.",
        )
    declarations = {t.name: t for t in source.object_types}
    occupied, objects, relations, evidence = (
        set(context.objects_by_id),
        list(source.objects),
        set(source.e2o),
        [],
    )
    promoted_events = set()
    for (kind, lexical), observations in sorted(
        values.items(), key=lambda item: (item[0][0].value, item[0][1])
    ):
        type_name = (
            spec.object_type + "::" + kind.value
            if spec.type_policy == "split_primitive_types"
            else spec.object_type
        )
        declaration = ObjectType(type_name, (Attribute("value", kind),))
        if type_name in declarations:
            if not spec.reuse_compatible_type and type_name in {
                t.name for t in source.object_types
            }:
                raise _CannotTransform(
                    "promotion_type_collision",
                    "Promoted object type already exists; explicit compatible reuse is required.",
                    (type_name,),
                )
            if declarations[type_name] != declaration:
                raise _CannotTransform(
                    "promotion_type_collision",
                    "Promoted value declaration is incompatible with existing object type.",
                    (type_name,),
                )
        else:
            declarations[type_name] = declaration
        identifier = _fresh_id(
            spec.id_prefix,
            (type_name, kind.value, lexical),
            occupied,
            spec.id_collision,
        )
        first = min(event.time for event, _ in observations)
        objects.append(
            Object(
                identifier, type_name, (ObjectAttr("value", observations[0][1], first),)
            )
        )
        ids = tuple(sorted(event.id for event, _ in observations))
        promoted_events.update(ids)
        relations.update(E2O(event_id, identifier, spec.qualifier) for event_id in ids)
        evidence.append(
            PromotedObject(
                identifier, type_name, ids, spec.attribute, kind.value, lexical, first
            )
        )
    events = tuple(
        replace(
            e, attributes=tuple(a for a in e.attributes if a.name != spec.attribute)
        )
        if spec.remove_event_attribute and e.id in promoted_events
        else e
        for e in source.events
    )
    target = _validated(
        source,
        events=events,
        objects=objects,
        e2o=relations,
        object_types=declarations.values(),
    )
    return target, _evidence(
        source,
        target,
        "promote_attribute",
        {e.id: {e.id} for e in source.events},
        evidence,
        skipped=skipped,
    )


def _explode(context, spec):
    source = context.log
    if spec.object_types is not None and set(spec.object_types) - set(
        context.objects_by_type
    ):
        raise _CannotTransform(
            "unknown_object_type",
            "Explosion selection contains undeclared object type.",
        )
    occupied, events, relations, mapping = set(context.events_by_id), [], [], {}
    for event in source.events:
        original = context.e2o_by_event[event.id]
        selected = {
            r.object
            for r in original
            if (
                spec.object_types is None
                or context.objects_by_id[r.object].type in spec.object_types
            )
            and (spec.qualifiers is None or r.qualifier in spec.qualifiers)
        }
        mapping[event.id] = set()
        for object_id in sorted(selected):
            identifier = _fresh_id(
                spec.id_prefix, (event.id, object_id), occupied, spec.id_collision
            )
            events.append(replace(event, id=identifier))
            # Selection chooses participants; every original role for that pair survives.
            relations.extend(
                E2O(identifier, r.object, r.qualifier)
                for r in original
                if r.object == object_id
            )
            mapping[event.id].add(identifier)
        residual = [r for r in original if r.object not in selected]
        if residual or (not original and spec.isolated_events == "preserve"):
            events.append(event)
            relations.extend(residual)
            mapping[event.id].add(event.id)
    target = _validated(source, events=events, e2o=relations)
    return target, _evidence(source, target, "explode", mapping)


def _parent_child(context, spec):
    source = context.log
    if (
        spec.child_type not in context.objects_by_type
        or spec.parent_type not in context.objects_by_type
    ):
        raise _CannotTransform(
            "unknown_object_type", "Parent/child type must be declared."
        )
    candidates = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))
    for event in source.events:
        objects = {
            r.object
            for r in context.e2o_by_event[event.id]
            if spec.qualifiers is None or r.qualifier in spec.qualifiers
        }
        parents = {
            o for o in objects if context.objects_by_id[o].type == spec.parent_type
        }
        children = {
            o for o in objects if context.objects_by_id[o].type == spec.child_type
        }
        for child in children:
            for parent in parents:
                candidates[child][event.time][parent].add(event.id)
    declarations = {t.name: t for t in source.object_types}
    if candidates and spec.output in ("attribute_history", "both"):
        declaration = declarations[spec.child_type]
        existing = next(
            (a for a in declaration.attributes if a.name == spec.attribute), None
        )
        if existing is not None and existing.type is not ValueType.STRING:
            raise _CannotTransform(
                "parent_attribute_type_conflict",
                "Parent references require a string object attribute.",
                (spec.child_type, spec.attribute),
            )
        if existing is None:
            declarations[spec.child_type] = replace(
                declaration,
                attributes=declaration.attributes
                + (Attribute(spec.attribute, ValueType.STRING),),
            )
    assignments, objects, relations = [], [], set(source.o2o)
    for obj in source.objects:
        observations = candidates.get(obj.id, {})
        parent_ids = {parent for row in observations.values() for parent in row}
        existing_parent_ids = {
            relation.target
            for relation in source.o2o
            if relation.source == obj.id
            and relation.qualifier == spec.relation_qualifier
            and context.objects_by_id[relation.target].type == spec.parent_type
        }
        if (
            spec.assignment == "unique_parent"
            and parent_ids
            and len(parent_ids | existing_parent_ids) > 1
        ):
            raise _CannotTransform(
                "ambiguous_parent",
                "Co-participation and existing qualified O2O disagree under unique_parent policy.",
                (obj.id,) + tuple(sorted(parent_ids | existing_parent_ids)),
            )
        history = list(obj.attributes)
        for time, row in sorted(observations.items()):
            if len(row) > 1:
                raise _CannotTransform(
                    "simultaneous_parent_conflict",
                    "Multiple parents at one timestamp cannot form a single as-of value.",
                    (obj.id,) + tuple(sorted(row)),
                )
            parent = next(iter(row))
            added = False
            if spec.output in ("attribute_history", "both"):
                exact = [
                    a for a in history if a.name == spec.attribute and a.time == time
                ]
                if exact and exact[0].value != parent:
                    raise _CannotTransform(
                        "parent_history_collision",
                        "Existing object history conflicts at the proposed timestamp.",
                        (obj.id, spec.attribute, time.isoformat()),
                    )
                earlier = [
                    a for a in history if a.name == spec.attribute and a.time <= time
                ]
                current = max(earlier, key=lambda a: a.time).value if earlier else None
                if spec.assignment == "unique_parent" and any(
                    a.name == spec.attribute and a.value != parent for a in history
                ):
                    raise _CannotTransform(
                        "parent_history_conflict",
                        "Existing parent history contradicts unique-parent inference.",
                        (obj.id, spec.attribute),
                    )
                if current != parent:
                    history.append(ObjectAttr(spec.attribute, parent, time))
                    added = True
            if spec.output in ("o2o", "both"):
                relations.add(O2O(obj.id, parent, spec.relation_qualifier))
            assignments.append(
                ParentAssignment(
                    obj.id, parent, time, tuple(sorted(row[parent])), added
                )
            )
        objects.append(replace(obj, attributes=tuple(history)))
    target = _validated(
        source, objects=objects, o2o=relations, object_types=declarations.values()
    )
    return target, _evidence(
        source,
        target,
        "parent_child",
        {e.id: {e.id} for e in source.events},
        parents=assignments,
    )


def _plan(log, spec, expected_type, operator, execute):
    if not isinstance(spec, expected_type):
        raise TypeError(f"spec must be {expected_type.__name__}")
    context, issues = _prepare(log)
    if context is None:
        return _result(operator, None, spec, ComputeStatus.INVALID_INPUT, None, issues)
    try:
        _, evidence = execute(context, spec)
    except _CannotTransform as exc:
        return _result(
            operator, context, spec, ComputeStatus.UNAVAILABLE, None, (exc.issue,)
        )
    return _result(operator, context, spec, ComputeStatus.COMPUTED, evidence)


def deduplicate_ocel(
    log: OCEL | ComputationContext,
    spec: OCELDeduplicationSpec = OCELDeduplicationSpec(),
) -> ComputationResult[OCELTransformation]:
    """Plan exact event or qualifier-preserving participation deduplication.

    Keys retain complete typed event attributes. Identical observation does not
    prove duplicate real behavior; this operator creates an explicit chosen view.
    """
    return _plan(
        log, spec, OCELDeduplicationSpec, "pix.object_centric.deduplicate", _deduplicate
    )


def merge_ocel_events(
    log: OCEL | ComputationContext, spec: OCELMergeSpec = OCELMergeSpec()
) -> ComputationResult[OCELTransformation]:
    """Merge same-activity/time events, optionally by shared-object components.

    Shared-object components are transitive; not every pair necessarily shares
    an object. Conflicting attributes never silently choose a representative.
    """
    return _plan(log, spec, OCELMergeSpec, "pix.object_centric.merge_events", _merge)


def promote_event_attribute(
    log: OCEL | ComputationContext, spec: OCELAttributePromotionSpec
) -> ComputationResult[OCELTransformation]:
    """Promote typed values to objects; zero, False and empty text remain distinct."""
    return _plan(
        log,
        spec,
        OCELAttributePromotionSpec,
        "pix.object_centric.promote_attribute",
        _promote,
    )


def explode_ocel(
    log: OCEL | ComputationContext, spec: OCELExplodeSpec = OCELExplodeSpec()
) -> ComputationResult[OCELTransformation]:
    """Clone one event per selected object, retaining every original E2O role."""
    return _plan(log, spec, OCELExplodeSpec, "pix.object_centric.explode", _explode)


def infer_parent_child_references(
    log: OCEL | ComputationContext, spec: OCELParentChildSpec
) -> ComputationResult[OCELTransformation]:
    """Infer co-participation parent candidates under explicit uniqueness/history rules.

    This is a derived interpretation, not evidence that co-participation proves
    real-world parenthood. O2O is untimed; observation times remain in the plan.
    """
    return _plan(
        log, spec, OCELParentChildSpec, "pix.object_centric.parent_child", _parent_child
    )


_OPERATORS = {
    "pix.object_centric.deduplicate": (OCELDeduplicationSpec, _deduplicate),
    "pix.object_centric.merge_events": (OCELMergeSpec, _merge),
    "pix.object_centric.promote_attribute": (OCELAttributePromotionSpec, _promote),
    "pix.object_centric.explode": (OCELExplodeSpec, _explode),
    "pix.object_centric.parent_child": (OCELParentChildSpec, _parent_child),
}


def materialize_ocel_transformation(
    source: OCEL | ComputationContext, result: ComputationResult[OCELTransformation]
) -> OCEL:
    """Verify source, request identity and every evidence field before replay.

    No encoded module names or callable names are evaluated. The operation is
    selected from a static allowlist, recomputed and globally validated.
    """
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id not in _OPERATORS
    ):
        raise TypeError("expected a native OCEL transformation result")
    spec_type, execute = _OPERATORS[result.operator_id]
    if (
        not isinstance(result.spec, spec_type)
        or not isinstance(result.value, OCELTransformation)
        or result.status is not ComputeStatus.COMPUTED
    ):
        raise ValueError("materialization requires a computed matching plan")
    context, issues = _prepare(source)
    if context is None or context.source_digest != result.source_digest:
        raise ValueError(f"source cannot match transformation plan: {issues}")
    try:
        target, evidence = execute(context, result.spec)
    except _CannotTransform as exc:
        raise ValueError("transformation is no longer valid") from exc
    expected = _result(
        result.operator_id, context, result.spec, ComputeStatus.COMPUTED, evidence
    )
    if expected != result:
        raise ValueError("transformation identity or evidence was altered")
    return target


RESULT_SCHEMAS = {
    operator: (
        operator.rsplit(".", 1)[-1].replace("_", "-"),
        spec_type,
        OCELTransformation,
    )
    for operator, (spec_type, _) in _OPERATORS.items()
}

__all__ = (
    "OCELDeduplicationSpec",
    "OCELMergeSpec",
    "OCELAttributePromotionSpec",
    "OCELExplodeSpec",
    "OCELParentChildSpec",
    "EventLineage",
    "PromotedObject",
    "ParentAssignment",
    "OCELTransformation",
    "deduplicate_ocel",
    "merge_ocel_events",
    "promote_event_attribute",
    "explode_ocel",
    "infer_parent_child_references",
    "materialize_ocel_transformation",
)
