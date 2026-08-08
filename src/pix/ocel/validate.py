"""Dataset-wide semantic validation for the PIX OCEL data model.

Validation is read-only.

This module does not normalize, coerce, sort, merge, repair, infer, or remove
OCEL data. It reports semantic violations in an already constructed OCEL
instance.

Local value-shape invariants belong to model.py.
Import and source-file diagnostics belong to later ingestion layers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from pix.ocel.model import (
    OCEL,
    EventType,
    ObjectType,
    Value,
    ValueType,
)
from pix.ocel.report import Issue, Report


def validate(ocel: OCEL) -> Report:
    """Validate dataset-wide OCEL semantics without modifying the input.

    The returned report is deterministic: semantically identical collections
    of issues are returned in a stable order independent of input tuple order.

    This function checks:

    - unique event-type names;
    - unique object-type names;
    - unique event IDs;
    - unique object IDs;
    - event/object references to declared types;
    - attribute declarations for each entity type;
    - exact canonical value-type compatibility;
    - E2O referential integrity;
    - O2O referential integrity;
    - exact duplicate E2O relations;
    - exact duplicate O2O relations.

    It intentionally does not require events or objects to participate in a
    relation. Disconnected entities are valid OCEL data.
    """

    if not isinstance(ocel, OCEL):
        raise TypeError("ocel must be OCEL")

    issues: list[Issue] = []

    event_type_groups = _group_event_types(ocel.event_types)
    object_type_groups = _group_object_types(ocel.object_types)

    event_types = _validate_event_types(
        event_type_groups,
        issues,
    )
    object_types = _validate_object_types(
        object_type_groups,
        issues,
    )

    _validate_entity_ids(
        ocel,
        issues,
    )

    _validate_events(
        ocel,
        declared_types=set(event_type_groups),
        unique_types=event_types,
        issues=issues,
    )
    _validate_objects(
        ocel,
        declared_types=set(object_type_groups),
        unique_types=object_types,
        issues=issues,
    )

    _validate_e2o(
        ocel,
        issues,
    )
    _validate_o2o(
        ocel,
        issues,
    )

    return Report(
        issues=tuple(
            sorted(
                issues,
                key=_issue_key,
            )
        )
    )


def _group_event_types(
    values: tuple[EventType, ...],
) -> dict[str, list[EventType]]:
    groups: dict[str, list[EventType]] = defaultdict(list)

    for value in values:
        groups[value.name].append(value)

    return dict(groups)


def _group_object_types(
    values: tuple[ObjectType, ...],
) -> dict[str, list[ObjectType]]:
    groups: dict[str, list[ObjectType]] = defaultdict(list)

    for value in values:
        groups[value.name].append(value)

    return dict(groups)


def _validate_event_types(
    groups: dict[str, list[EventType]],
    issues: list[Issue],
) -> dict[str, EventType]:
    """Return only unambiguous event-type declarations."""

    result: dict[str, EventType] = {}

    for name in sorted(groups):
        declarations = groups[name]

        if len(declarations) > 1:
            issues.append(
                Issue(
                    code="duplicate_event_type",
                    message=f"Event type '{name}' is declared more than once.",
                    at=("event_type", name),
                )
            )
            continue

        result[name] = declarations[0]

    return result


def _validate_object_types(
    groups: dict[str, list[ObjectType]],
    issues: list[Issue],
) -> dict[str, ObjectType]:
    """Return only unambiguous object-type declarations."""

    result: dict[str, ObjectType] = {}

    for name in sorted(groups):
        declarations = groups[name]

        if len(declarations) > 1:
            issues.append(
                Issue(
                    code="duplicate_object_type",
                    message=f"Object type '{name}' is declared more than once.",
                    at=("object_type", name),
                )
            )
            continue

        result[name] = declarations[0]

    return result


def _validate_entity_ids(
    ocel: OCEL,
    issues: list[Issue],
) -> None:
    for event_id in _duplicates(tuple(event.id for event in ocel.events)):
        issues.append(
            Issue(
                code="duplicate_event_id",
                message=f"Event id '{event_id}' occurs more than once.",
                at=("event", event_id),
            )
        )

    for object_id in _duplicates(tuple(obj.id for obj in ocel.objects)):
        issues.append(
            Issue(
                code="duplicate_object_id",
                message=f"Object id '{object_id}' occurs more than once.",
                at=("object", object_id),
            )
        )


def _validate_events(
    ocel: OCEL,
    *,
    declared_types: set[str],
    unique_types: dict[str, EventType],
    issues: list[Issue],
) -> None:
    for event in ocel.events:
        if event.type not in declared_types:
            issues.append(
                Issue(
                    code="undeclared_event_type",
                    message=(
                        f"Event '{event.id}' refers to undeclared "
                        f"event type '{event.type}'."
                    ),
                    at=("event", event.id, "type"),
                )
            )
            continue

        event_type = unique_types.get(event.type)

        # A duplicated type declaration is already an error. Do not select
        # one schema arbitrarily and produce secondary schema diagnostics.
        if event_type is None:
            continue

        schema = {attribute.name: attribute.type for attribute in event_type.attributes}

        for attribute in event.attributes:
            expected = schema.get(attribute.name)

            if expected is None:
                issues.append(
                    Issue(
                        code="undeclared_event_attribute",
                        message=(
                            f"Event '{event.id}' has undeclared attribute "
                            f"'{attribute.name}' for event type '{event.type}'."
                        ),
                        at=(
                            "event",
                            event.id,
                            "attribute",
                            attribute.name,
                        ),
                    )
                )
                continue

            actual = _value_type(attribute.value)

            if actual is not expected:
                issues.append(
                    Issue(
                        code="event_attribute_type_mismatch",
                        message=(
                            f"Event '{event.id}' attribute '{attribute.name}' "
                            f"requires '{expected.value}' but contains "
                            f"'{actual.value}'."
                        ),
                        at=(
                            "event",
                            event.id,
                            "attribute",
                            attribute.name,
                        ),
                    )
                )


def _validate_objects(
    ocel: OCEL,
    *,
    declared_types: set[str],
    unique_types: dict[str, ObjectType],
    issues: list[Issue],
) -> None:
    for obj in ocel.objects:
        if obj.type not in declared_types:
            issues.append(
                Issue(
                    code="undeclared_object_type",
                    message=(
                        f"Object '{obj.id}' refers to undeclared "
                        f"object type '{obj.type}'."
                    ),
                    at=("object", obj.id, "type"),
                )
            )
            continue

        object_type = unique_types.get(obj.type)

        # A duplicated type declaration is already an error. Do not select
        # one schema arbitrarily.
        if object_type is None:
            continue

        schema = {
            attribute.name: attribute.type for attribute in object_type.attributes
        }

        for attribute in obj.attributes:
            expected = schema.get(attribute.name)

            if expected is None:
                issues.append(
                    Issue(
                        code="undeclared_object_attribute",
                        message=(
                            f"Object '{obj.id}' has undeclared attribute "
                            f"'{attribute.name}' for object type '{obj.type}'."
                        ),
                        at=(
                            "object",
                            obj.id,
                            "attribute",
                            attribute.name,
                        ),
                    )
                )
                continue

            actual = _value_type(attribute.value)

            if actual is not expected:
                issues.append(
                    Issue(
                        code="object_attribute_type_mismatch",
                        message=(
                            f"Object '{obj.id}' attribute '{attribute.name}' "
                            f"requires '{expected.value}' but contains "
                            f"'{actual.value}'."
                        ),
                        at=(
                            "object",
                            obj.id,
                            "attribute",
                            attribute.name,
                        ),
                    )
                )


def _validate_e2o(
    ocel: OCEL,
    issues: list[Issue],
) -> None:
    event_ids = {event.id for event in ocel.events}
    object_ids = {obj.id for obj in ocel.objects}

    for relation in ocel.e2o:
        location = (
            "e2o",
            relation.event,
            relation.object,
            relation.qualifier,
        )

        if relation.event not in event_ids:
            issues.append(
                Issue(
                    code="dangling_e2o_event",
                    message=(f"E2O refers to unknown event '{relation.event}'."),
                    at=location,
                )
            )

        if relation.object not in object_ids:
            issues.append(
                Issue(
                    code="dangling_e2o_object",
                    message=(f"E2O refers to unknown object '{relation.object}'."),
                    at=location,
                )
            )

    for relation in _duplicates(ocel.e2o):
        issues.append(
            Issue(
                code="duplicate_e2o",
                message=(
                    "E2O relation "
                    f"('{relation.event}', '{relation.object}', "
                    f"'{relation.qualifier}') occurs more than once."
                ),
                at=(
                    "e2o",
                    relation.event,
                    relation.object,
                    relation.qualifier,
                ),
            )
        )


def _validate_o2o(
    ocel: OCEL,
    issues: list[Issue],
) -> None:
    object_ids = {obj.id for obj in ocel.objects}

    for relation in ocel.o2o:
        location = (
            "o2o",
            relation.source,
            relation.target,
            relation.qualifier,
        )

        if relation.source not in object_ids:
            issues.append(
                Issue(
                    code="dangling_o2o_source",
                    message=(
                        f"O2O refers to unknown source object '{relation.source}'."
                    ),
                    at=location,
                )
            )

        if relation.target not in object_ids:
            issues.append(
                Issue(
                    code="dangling_o2o_target",
                    message=(
                        f"O2O refers to unknown target object '{relation.target}'."
                    ),
                    at=location,
                )
            )

    for relation in _duplicates(ocel.o2o):
        issues.append(
            Issue(
                code="duplicate_o2o",
                message=(
                    "O2O relation "
                    f"('{relation.source}', '{relation.target}', "
                    f"'{relation.qualifier}') occurs more than once."
                ),
                at=(
                    "o2o",
                    relation.source,
                    relation.target,
                    relation.qualifier,
                ),
            )
        )


def _value_type(value: Value) -> ValueType:
    """Return the exact canonical OCEL value type.

    No numeric widening is performed. In particular, INTEGER does not satisfy
    FLOAT, and BOOLEAN does not satisfy INTEGER.
    """

    if isinstance(value, datetime):
        return ValueType.TIME

    # bool must be checked before int because bool is a subclass of int.
    if isinstance(value, bool):
        return ValueType.BOOLEAN

    if isinstance(value, int):
        return ValueType.INTEGER

    if isinstance(value, float):
        return ValueType.FLOAT

    if isinstance(value, str):
        return ValueType.STRING

    # model.py prevents unsupported canonical values from reaching this point.
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _duplicates(
    values: tuple[object, ...],
) -> tuple[object, ...]:
    """Return each duplicated value exactly once in deterministic order."""

    counts: dict[object, int] = {}

    for value in values:
        counts[value] = counts.get(value, 0) + 1

    duplicates = [value for value, count in counts.items() if count > 1]

    return tuple(
        sorted(
            duplicates,
            key=repr,
        )
    )


def _issue_key(
    issue: Issue,
) -> tuple[str, tuple[str, ...], str, str]:
    return (
        issue.code,
        issue.at,
        issue.message,
        issue.level.value,
    )


__all__ = [
    "validate",
]
