"""Native OCEL participation and observed lifecycle statistics.

The counting profile is unique (event, object) participation after qualifier
selection. Different E2O roles never multiply an event or object observation;
qualified E2O counts are reported separately. Convergence/divergence use the
PM4Py diagnostic threshold (median > 1), on this unique participation profile.
PM4Py 2.7.23.8 instead groups relation rows, so multi-role inputs can differ.

Lifecycle boundaries retain every event tied at the first/last timestamp. They
are observations, not inferred creation/death times or a causal event sequence.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.analysis import _text
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL


@dataclass(frozen=True, slots=True)
class ObjectStatisticsSpec:
    """None selects all declared types/all qualifiers; () selects none."""

    SPEC_TYPE: ClassVar[str] = "pix.object_centric.object_statistics.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        for name in ("object_types", "qualifiers"):
            values = getattr(self, name)
            if values is None:
                continue
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple of strings or None")
            for value in values:
                _text(value, name, blank=name == "qualifiers")
            object.__setattr__(self, name, tuple(sorted(set(values))))


@dataclass(frozen=True, slots=True)
class CountDistribution:
    """Exact count distribution; mean is total/sample_count if nonempty.

    Histogram pairs are (observed_count, number_of_samples). Median is the
    exact median_numerator/median_denominator; an empty sample has None/0.
    """

    sample_count: int
    total: int
    minimum: int | None
    maximum: int | None
    median_numerator: int | None
    median_denominator: int
    histogram: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class ObjectLifecycleStatistics:
    object_id: str
    object_type: str
    event_ids: tuple[str, ...]
    event_count: int
    e2o_relation_count: int
    activity_counts: tuple[tuple[str, int], ...]
    first_time: datetime | None
    last_time: datetime | None
    first_event_ids: tuple[str, ...]
    last_event_ids: tuple[str, ...]
    duration_microseconds: int | None


@dataclass(frozen=True, slots=True)
class ObjectTypeStatistics:
    object_type: str
    object_count: int
    participating_object_count: int
    participating_event_count: int
    unique_participation_count: int
    e2o_relation_count: int
    isolated_object_ids: tuple[str, ...]
    events_per_object: CountDistribution
    lifecycle_duration_microseconds: CountDistribution


@dataclass(frozen=True, slots=True)
class EventActivityStatistics:
    activity: str
    source_event_count: int
    participating_event_count: int
    participating_object_count: int
    unique_participation_count: int
    e2o_relation_count: int


@dataclass(frozen=True, slots=True)
class ActivityObjectTypeStatistics:
    """Positive participation samples only; absent pairs are omitted.

    Each events_per_object_counts pair identifies an object and its number of
    distinct events of this activity. objects_per_event_counts identifies an
    event and its number of distinct objects of this type. Neither includes
    zeros. ANY > 1 witnesses are distinct from the median > 1 diagnostics.
    """

    activity: str
    object_type: str
    event_count: int
    object_count: int
    unique_participation_count: int
    e2o_relation_count: int
    events_per_object_counts: tuple[tuple[str, int], ...]
    objects_per_event_counts: tuple[tuple[str, int], ...]
    events_per_object: CountDistribution
    objects_per_event: CountDistribution
    divergence_median_gt_one: bool
    convergence_median_gt_one: bool
    any_object_repeats_activity: bool
    any_event_has_multiple_same_type_objects: bool


@dataclass(frozen=True, slots=True)
class ObjectStatistics:
    counting_profile: str
    source_event_count: int
    object_count: int
    participating_object_count: int
    participating_event_count: int
    unique_participation_count: int
    e2o_relation_count: int
    isolated_object_ids: tuple[str, ...]
    qualifier_relation_counts: tuple[tuple[str, int], ...]
    objects: tuple[ObjectLifecycleStatistics, ...]
    object_types: tuple[ObjectTypeStatistics, ...]
    activities: tuple[EventActivityStatistics, ...]
    activity_object_types: tuple[ActivityObjectTypeStatistics, ...]


def _distribution(values: tuple[int, ...]) -> CountDistribution:
    if not values:
        return CountDistribution(0, 0, None, None, None, 0, ())
    ordered = sorted(values)
    size = len(ordered)
    if size % 2:
        median_numerator, median_denominator = ordered[size // 2], 1
    else:
        median_numerator = ordered[size // 2 - 1] + ordered[size // 2]
        median_denominator = 2
    return CountDistribution(
        size,
        sum(ordered),
        ordered[0],
        ordered[-1],
        median_numerator,
        median_denominator,
        tuple(sorted(Counter(ordered).items())),
    )


def _median_gt_one(distribution: CountDistribution) -> bool:
    return (
        distribution.median_numerator is not None
        and distribution.median_numerator > distribution.median_denominator
    )


OBJECT_STATISTICS_OPERATOR_ID = "pix.object_centric.object_statistics"


def object_statistics(
    log: OCEL | ComputationContext,
    spec: ObjectStatisticsSpec = ObjectStatisticsSpec(),
) -> ComputationResult[ObjectStatistics]:
    """Count selected participation, with exact durations and tied boundaries.

    All source events remain in the source activity census. Participation fields
    only count relations in the selected object-type/qualifier view. Selected
    objects with no such relation remain as isolates. O2O edges do not count as
    E2O participation. Isolate duration is unknown (None), not zero.
    """

    if not isinstance(spec, ObjectStatisticsSpec):
        raise TypeError("spec must be ObjectStatisticsSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            OBJECT_STATISTICS_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    selected_types = (
        tuple(sorted(context.objects_by_type))
        if spec.object_types is None
        else spec.object_types
    )
    unknown = tuple(
        name for name in selected_types if name not in context.objects_by_type
    )
    if unknown:
        return _result(
            OBJECT_STATISTICS_OPERATOR_ID,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(
                ComputeIssue("unknown_object_type", f"Undeclared object type: {name}")
                for name in unknown
            ),
        )
    type_set = set(selected_types)
    objects = tuple(
        sorted(
            (obj for obj in context.log.objects if obj.type in type_set),
            key=lambda obj: obj.id,
        )
    )
    selected_ids = {obj.id for obj in objects}
    qualifiers = None if spec.qualifiers is None else set(spec.qualifiers)
    relations = tuple(
        relation
        for relation in context.log.e2o
        if relation.object in selected_ids
        and (qualifiers is None or relation.qualifier in qualifiers)
    )
    events_by_object: dict[str, set[str]] = {obj.id: set() for obj in objects}
    objects_by_event: dict[str, set[str]] = defaultdict(set)
    relation_counts = Counter()
    pair_relation_counts = Counter()
    for relation in relations:
        events_by_object[relation.object].add(relation.event)
        objects_by_event[relation.event].add(relation.object)
        relation_counts[relation.object] += 1
        pair_relation_counts[
            (
                context.events_by_id[relation.event].type,
                context.objects_by_id[relation.object].type,
            )
        ] += 1

    lifecycles = []
    per_pair_objects: dict[tuple[str, str], Counter] = defaultdict(Counter)
    per_pair_events: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for obj in objects:
        event_ids = tuple(sorted(events_by_object[obj.id]))
        events = tuple(context.events_by_id[event_id] for event_id in event_ids)
        first_time = min((event.time for event in events), default=None)
        last_time = max((event.time for event in events), default=None)
        duration = None
        if first_time is not None and last_time is not None:
            delta = last_time - first_time
            duration = (
                delta.days * 86400 + delta.seconds
            ) * 1_000_000 + delta.microseconds
        lifecycles.append(
            ObjectLifecycleStatistics(
                obj.id,
                obj.type,
                event_ids,
                len(event_ids),
                relation_counts[obj.id],
                tuple(sorted(Counter(event.type for event in events).items())),
                first_time,
                last_time,
                tuple(event.id for event in events if event.time == first_time),
                tuple(event.id for event in events if event.time == last_time),
                duration,
            )
        )
        for event in events:
            key = (event.type, obj.type)
            per_pair_objects[key][obj.id] += 1
            per_pair_events[key][event.id] += 1

    pair_stats = []
    for activity, object_type in sorted(per_pair_objects):
        key = (activity, object_type)
        object_counts = tuple(sorted(per_pair_objects[key].items()))
        event_counts = tuple(sorted(per_pair_events[key].items()))
        events_per_object = _distribution(tuple(count for _, count in object_counts))
        objects_per_event = _distribution(tuple(count for _, count in event_counts))
        pair_stats.append(
            ActivityObjectTypeStatistics(
                activity,
                object_type,
                len(event_counts),
                len(object_counts),
                events_per_object.total,
                pair_relation_counts[key],
                object_counts,
                event_counts,
                events_per_object,
                objects_per_event,
                _median_gt_one(events_per_object),
                _median_gt_one(objects_per_event),
                any(count > 1 for _, count in object_counts),
                any(count > 1 for _, count in event_counts),
            )
        )

    type_stats = []
    for object_type in selected_types:
        rows = tuple(row for row in lifecycles if row.object_type == object_type)
        linked_events = {event_id for row in rows for event_id in row.event_ids}
        type_stats.append(
            ObjectTypeStatistics(
                object_type,
                len(rows),
                sum(row.event_count > 0 for row in rows),
                len(linked_events),
                sum(row.event_count for row in rows),
                sum(row.e2o_relation_count for row in rows),
                tuple(row.object_id for row in rows if not row.event_ids),
                _distribution(tuple(row.event_count for row in rows)),
                _distribution(
                    tuple(
                        row.duration_microseconds
                        for row in rows
                        if row.duration_microseconds is not None
                    )
                ),
            )
        )

    source_activities = Counter(event.type for event in context.log.events)
    activity_stats = []
    for activity in sorted(source_activities):
        rows = tuple(row for row in pair_stats if row.activity == activity)
        linked_events = {
            event_id for row in rows for event_id, _ in row.objects_per_event_counts
        }
        linked_objects = {
            object_id for row in rows for object_id, _ in row.events_per_object_counts
        }
        activity_stats.append(
            EventActivityStatistics(
                activity,
                source_activities[activity],
                len(linked_events),
                len(linked_objects),
                sum(row.unique_participation_count for row in rows),
                sum(row.e2o_relation_count for row in rows),
            )
        )
    payload = ObjectStatistics(
        "unique_event_object_participation",
        len(context.log.events),
        len(objects),
        sum(bool(ids) for ids in events_by_object.values()),
        len(objects_by_event),
        sum(len(ids) for ids in events_by_object.values()),
        len(relations),
        tuple(obj.id for obj in objects if not events_by_object[obj.id]),
        tuple(sorted(Counter(relation.qualifier for relation in relations).items())),
        tuple(lifecycles),
        tuple(type_stats),
        tuple(activity_stats),
        tuple(pair_stats),
    )
    return _result(
        OBJECT_STATISTICS_OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, payload
    )


RESULT_SCHEMAS = {
    OBJECT_STATISTICS_OPERATOR_ID: (
        "object-statistics",
        ObjectStatisticsSpec,
        ObjectStatistics,
    ),
}

__all__ = (
    "ObjectStatisticsSpec",
    "ObjectStatistics",
    "ObjectLifecycleStatistics",
    "ObjectTypeStatistics",
    "EventActivityStatistics",
    "ActivityObjectTypeStatistics",
    "CountDistribution",
    "object_statistics",
    "OBJECT_STATISTICS_OPERATOR_ID",
)
