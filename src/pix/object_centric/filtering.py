"""Immutable OCEL sublogs with explicit object closure and history semantics.

This operator projects canonical facts. It does not infer process executions or
turn an untimed O2O relation into a temporal relation.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.analysis import _text
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL, Object, ObjectAttr, build

FILTER_OCEL_OPERATOR_ID = "pix.object_centric.filter_ocel"


@dataclass(frozen=True, slots=True)
class OCELFilterSpec:
    """Conjunctive selection followed by explicitly requested O2O expansion.

    ``None`` means unrestricted; an empty selection selects nothing. IDs and
    types are intersected to obtain object seeds. O2O closure can deliberately
    add objects of other types; selectors constrain seeds, not the expansion.
    Activity names are OCEL event-type names. Unknown IDs/types are unavailable
    rather than silently interpreted as an empty selection.

    Object selectors affect candidate events only when at least one object
    selector is supplied. ``any`` requires at least one retained object; ``all``
    requires a nonempty E2O set wholly within the retained objects; ``retain``
    keeps every candidate event, including events with no remaining E2O.
    ``drop`` isolated objects removes objects without retained E2O, including
    closure-added objects. O2O participation alone does not prevent that drop.

    The event window is closed: [start, end]. ``window_with_prior`` keeps each
    attribute's latest assignment strictly before start, together with all
    assignments inside the window. Original assignment times are preserved.
    This preserves as-of values inside the window without retaining later
    assignments. ``preserve_all`` retains the complete object history.
    With no bound, that side of the history is unrestricted. O2O is untimed.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    event_ids: tuple[str, ...] | None = None
    activities: tuple[str, ...] | None = None
    object_ids: tuple[str, ...] | None = None
    object_types: tuple[str, ...] | None = None
    object_event_policy: Literal["any", "all", "retain"] = "any"
    isolated_objects: Literal["retain", "drop"] = "retain"
    o2o_depth: int = 0
    o2o_direction: Literal["both", "outbound", "inbound"] = "both"
    start: datetime | None = None
    end: datetime | None = None
    history_policy: Literal["window_with_prior", "preserve_all"] = "window_with_prior"

    def __post_init__(self) -> None:
        for name in ("event_ids", "activities", "object_ids", "object_types"):
            values = getattr(self, name)
            if values is not None:
                if not isinstance(values, tuple):
                    raise TypeError(f"{name} must be a tuple of strings or None")
                for value in values:
                    _text(value, name)
                object.__setattr__(self, name, tuple(sorted(set(values))))
        for name, choices in (
            ("object_event_policy", ("any", "all", "retain")),
            ("isolated_objects", ("retain", "drop")),
            ("o2o_direction", ("both", "outbound", "inbound")),
            ("history_policy", ("window_with_prior", "preserve_all")),
        ):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
            if getattr(self, name) not in choices:
                raise ValueError(f"{name} must be one of {choices}")
        if type(self.o2o_depth) is not int:
            raise TypeError("o2o_depth must be an integer")
        if self.o2o_depth < 0:
            raise ValueError("o2o_depth must not be negative")
        for name in ("start", "end"):
            value = getattr(self, name)
            if value is not None:
                if not isinstance(value, datetime):
                    raise TypeError(f"{name} must be an aware datetime or None")
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError(f"{name} must include a timezone")
                object.__setattr__(self, name, value.astimezone(timezone.utc))
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start must be no later than end")


@dataclass(frozen=True, slots=True)
class OCELFilterResult:
    """Selection evidence; materialize against the identified original OCEL.

    Attribute values are not copied into this analytical result. This avoids
    duplicating logs or ambiguously encoding TIME attributes as JSON strings.
    ``history_assignments_removed`` counts trimmed facts of retained objects;
    attributes belonging to dropped objects are not included in that count.
    """

    selected_event_ids: tuple[str, ...]
    selected_object_ids: tuple[str, ...]
    dropped_event_ids: tuple[str, ...]
    dropped_object_ids: tuple[str, ...]
    seed_object_ids: tuple[str, ...]
    closure_added_object_ids: tuple[str, ...]
    dropped_e2o_count: int
    dropped_o2o_count: int
    history_assignments_removed: int

    def __post_init__(self) -> None:
        for name in (
            "selected_event_ids",
            "selected_object_ids",
            "dropped_event_ids",
            "dropped_object_ids",
            "seed_object_ids",
            "closure_added_object_ids",
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple")
            for value in values:
                _text(value, name)
            if tuple(sorted(set(values))) != values:
                raise ValueError(f"{name} must be sorted and unique")
        for name in (
            "dropped_e2o_count",
            "dropped_o2o_count",
            "history_assignments_removed",
        ):
            if type(getattr(self, name)) is not int:
                raise TypeError(f"{name} must be an integer")
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if set(self.selected_event_ids) & set(self.dropped_event_ids):
            raise ValueError("selected and dropped events must be disjoint")
        if set(self.selected_object_ids) & set(self.dropped_object_ids):
            raise ValueError("selected and dropped objects must be disjoint")
        if set(self.seed_object_ids) & set(self.closure_added_object_ids):
            raise ValueError("closure additions must not include seed objects")
        available = set(self.selected_object_ids) | set(self.dropped_object_ids)
        expanded = set(self.seed_object_ids) | set(self.closure_added_object_ids)
        if not expanded <= available or not set(self.selected_object_ids) <= expanded:
            raise ValueError("object closure evidence is inconsistent")


def _selection_issues(
    context: ComputationContext, spec: OCELFilterSpec
) -> tuple[ComputeIssue, ...]:
    issues = []
    for field, available, code in (
        ("event_ids", set(context.events_by_id), "unknown_event_id"),
        ("object_ids", set(context.objects_by_id), "unknown_object_id"),
        (
            "activities",
            {item.name for item in context.log.event_types},
            "unknown_activity",
        ),
        ("object_types", set(context.objects_by_type), "unknown_object_type"),
    ):
        selection = getattr(spec, field)
        if selection is not None:
            for identifier in sorted(set(selection) - available):
                issues.append(
                    ComputeIssue(
                        code,
                        f"Unknown {field} entry {identifier!r}",
                        (field, identifier),
                    )
                )
    return tuple(issues)


def _object_closure(
    context: ComputationContext, seeds: set[str], spec: OCELFilterSpec
) -> set[str]:
    selected = set(seeds)
    if not spec.o2o_depth or not seeds:
        return selected
    neighbors: dict[str, set[str]] = defaultdict(set)
    for relation in context.log.o2o:
        if spec.o2o_direction in ("both", "outbound"):
            neighbors[relation.source].add(relation.target)
        if spec.o2o_direction in ("both", "inbound"):
            neighbors[relation.target].add(relation.source)
    frontier = set(seeds)
    for _ in range(spec.o2o_depth):
        following = {
            target for source in frontier for target in neighbors[source]
        } - selected
        if not following:
            break
        selected.update(following)
        frontier = following
    return selected


def _history(obj: Object, spec: OCELFilterSpec) -> Object:
    if spec.history_policy == "preserve_all" or (
        spec.start is None and spec.end is None
    ):
        return obj
    prior: dict[str, ObjectAttr] = {}
    inside: list[ObjectAttr] = []
    for assignment in obj.attributes:
        if spec.end is not None and assignment.time > spec.end:
            continue
        if spec.start is not None and assignment.time < spec.start:
            if (
                assignment.name not in prior
                or assignment.time > prior[assignment.name].time
            ):
                prior[assignment.name] = assignment
        else:
            inside.append(assignment)
    attributes = tuple(
        sorted((*prior.values(), *inside), key=lambda item: (item.name, item.time))
    )
    return replace(obj, attributes=attributes)


def filter_ocel(
    log: OCEL | ComputationContext,
    spec: OCELFilterSpec = OCELFilterSpec(),
) -> ComputationResult[OCELFilterResult]:
    """Compute selection evidence without copying OCEL attribute values.

    Call ``materialize_sublog(source, result)`` for the immutable canonical OCEL
    projection. Expanding objects never expands the explicit event/time
    selection. Missing as-of assignments remain missing, not null or inferred.
    """
    if not isinstance(spec, OCELFilterSpec):
        raise TypeError("spec must be OCELFilterSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            FILTER_OCEL_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    issues = _selection_issues(context, spec)
    if issues:
        return _result(
            FILTER_OCEL_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            issues,
        )
    _, value = _select(context, spec)
    return _result(
        FILTER_OCEL_OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, value
    )


def _select(
    context: ComputationContext, spec: OCELFilterSpec
) -> tuple[OCEL, OCELFilterResult]:
    """Evaluate a validated request, retaining typed source facts internally."""
    source = context.log
    allowed_ids = None if spec.object_ids is None else set(spec.object_ids)
    allowed_types = None if spec.object_types is None else set(spec.object_types)
    seeds = {
        obj.id
        for obj in source.objects
        if (allowed_ids is None or obj.id in allowed_ids)
        and (allowed_types is None or obj.type in allowed_types)
    }
    selected_objects = _object_closure(context, seeds, spec)
    closure_added = selected_objects - seeds
    event_ids = None if spec.event_ids is None else set(spec.event_ids)
    activities = None if spec.activities is None else set(spec.activities)
    object_selection = spec.object_ids is not None or spec.object_types is not None
    selected_events = []
    for event in source.events:
        if event_ids is not None and event.id not in event_ids:
            continue
        if activities is not None and event.type not in activities:
            continue
        if spec.start is not None and event.time < spec.start:
            continue
        if spec.end is not None and event.time > spec.end:
            continue
        if object_selection and spec.object_event_policy != "retain":
            related = {relation.object for relation in context.e2o_by_event[event.id]}
            if spec.object_event_policy == "any" and not related & selected_objects:
                continue
            if spec.object_event_policy == "all" and (
                not related or not related <= selected_objects
            ):
                continue
        selected_events.append(event)
    retained_events = {event.id for event in selected_events}
    relations = tuple(
        relation
        for relation in source.e2o
        if relation.event in retained_events and relation.object in selected_objects
    )
    if spec.isolated_objects == "drop":
        selected_objects.intersection_update(relation.object for relation in relations)
    retained_source_objects = tuple(
        obj for obj in source.objects if obj.id in selected_objects
    )
    objects = tuple(_history(obj, spec) for obj in retained_source_objects)
    o2o = tuple(
        relation
        for relation in source.o2o
        if relation.source in selected_objects and relation.target in selected_objects
    )
    filtered = replace(
        source, events=tuple(selected_events), objects=objects, e2o=relations, o2o=o2o
    )
    value = OCELFilterResult(
        selected_event_ids=tuple(sorted(retained_events)),
        selected_object_ids=tuple(sorted(selected_objects)),
        dropped_event_ids=tuple(sorted(set(context.events_by_id) - retained_events)),
        dropped_object_ids=tuple(sorted(set(context.objects_by_id) - selected_objects)),
        seed_object_ids=tuple(sorted(seeds)),
        closure_added_object_ids=tuple(sorted(closure_added)),
        dropped_e2o_count=len(source.e2o) - len(relations),
        dropped_o2o_count=len(source.o2o) - len(o2o),
        history_assignments_removed=sum(
            len(obj.attributes) for obj in retained_source_objects
        )
        - sum(len(obj.attributes) for obj in objects),
    )
    return filtered, value


def materialize_sublog(
    source: OCEL | ComputationContext,
    result: ComputationResult[OCELFilterResult],
) -> OCEL:
    """Materialize a filter result against its exact canonical input facts.

    Source digest, operator/version, request identity, and every selection
    evidence field are verified by evaluating the request again. A persisted
    result cannot be applied to another log, a changed request, or altered
    evidence. The returned OCEL is built and globally validated through the
    canonical builder. All type declarations and original import metadata are
    retained. E2O/O2O preserve qualifiers when both endpoints survive. Untimed
    O2O relations remain untimed, and object history retains its original types.
    """
    if not isinstance(result, ComputationResult):
        raise TypeError("result must be ComputationResult")
    if (
        result.operator_id != FILTER_OCEL_OPERATOR_ID
        or not isinstance(result.spec, OCELFilterSpec)
        or not isinstance(result.value, OCELFilterResult)
        or result.status is not ComputeStatus.COMPUTED
    ):
        raise ValueError("result must be a computed OCEL filter result")
    context, issues = _prepare(source)
    if context is None:
        raise ValueError(f"cannot materialize invalid source: {issues}")
    if result.source_digest != context.source_digest:
        raise ValueError("source digest does not match filter result")
    if _selection_issues(context, result.spec):
        raise ValueError("filter request contains unknown source entities")
    filtered, expected_value = _select(context, result.spec)
    expected = _result(
        FILTER_OCEL_OPERATOR_ID,
        context,
        result.spec,
        ComputeStatus.COMPUTED,
        expected_value,
    )
    if result != expected:
        raise ValueError("filter request identity or selection evidence does not match")
    built = build(
        event_types=filtered.event_types,
        object_types=filtered.object_types,
        events=filtered.events,
        objects=filtered.objects,
        e2o=filtered.e2o,
        o2o=filtered.o2o,
    )
    if built.ocel is None:
        raise ValueError("filter projection did not produce valid canonical OCEL")
    return replace(built.ocel, import_info=context.log.import_info)


RESULT_SCHEMAS = {
    FILTER_OCEL_OPERATOR_ID: ("ocel-filter", OCELFilterSpec, OCELFilterResult),
}

__all__ = ["OCELFilterSpec", "OCELFilterResult", "filter_ocel", "materialize_sublog"]
