"""Exact timestamp groups with explicit event and relation counting populations.

PM4Py 2.7.23.8 ``ocel_temporal_summary`` groups relation rows: an activity
therefore occurs once per qualified E2O row, not once per event. PIX retains
both counts and their evidence. Timestamp equality never implies causality.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.analysis import _text
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import OCEL

TEMPORAL_SUMMARY_OPERATOR_ID = "pix.object_centric.temporal_summary"


@dataclass(frozen=True, slots=True)
class TemporalSummarySpec:
    """Select activities and relation roles/types without inventing occurrences.

    None selects all, () selects none. Object types and qualifiers filter E2O
    relations only. ``all_selected_events`` retains events left without selected
    relations; ``selected_participating_events`` retains only events with at
    least one selected relation, matching the reference's relation population.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    activities: tuple[str, ...] | None = None
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    event_population: Literal[
        "all_selected_events", "selected_participating_events"
    ] = "all_selected_events"

    def __post_init__(self) -> None:
        for name in ("activities", "object_types", "qualifiers"):
            values = getattr(self, name)
            if values is None:
                continue
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be a tuple of strings or None")
            for value in values:
                _text(value, name, blank=name == "qualifiers")
            object.__setattr__(self, name, tuple(sorted(set(values))))
        if self.event_population not in (
            "all_selected_events",
            "selected_participating_events",
        ):
            raise ValueError("unknown event population")


@dataclass(frozen=True, slots=True)
class TemporalParticipation:
    """One distinct event/object pair, with all selected qualifying roles."""

    event_id: str
    object_id: str
    object_type: str
    qualifiers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TemporalBucket:
    """One exact UTC instant; identifier sorting is presentation, not ordering.

    activity_counts counts distinct events. relation_activity_counts counts
    qualified E2O rows. object_type_counts counts distinct objects in this bucket;
    participation_count counts distinct (event, object) pairs. The same object
    may participate in several simultaneous events without becoming new objects.
    """

    time: datetime
    event_ids: tuple[str, ...]
    event_count: int
    activities: tuple[str, ...]
    activity_counts: tuple[tuple[str, int], ...]
    object_ids: tuple[str, ...]
    object_count: int
    object_type_counts: tuple[tuple[str, int], ...]
    participation_count: int
    e2o_relation_count: int
    qualifier_relation_counts: tuple[tuple[str, int], ...]
    relation_activity_counts: tuple[tuple[str, int], ...]
    events_without_selected_relations: tuple[str, ...]
    participations: tuple[TemporalParticipation, ...]


@dataclass(frozen=True, slots=True)
class TemporalSummary:
    counting_profile: str
    event_population: str
    source_event_count: int
    selected_event_count: int
    participating_event_count: int
    object_count: int
    participation_count: int
    e2o_relation_count: int
    buckets: tuple[TemporalBucket, ...]


def temporal_summary(
    log: OCEL | ComputationContext,
    spec: TemporalSummarySpec = TemporalSummarySpec(),
) -> ComputationResult[TemporalSummary]:
    """Group exact observed timestamps; preserve tied events and orphan events.

    Canonical UTC normalization happens in the shared context. No floating-point
    timestamp conversion, time rounding, row-order tie breaking, or EOG is used.
    Empty input/selection produces an empty summary with zero population counts.
    """

    if not isinstance(spec, TemporalSummarySpec):
        raise TypeError("spec must be TemporalSummarySpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            TEMPORAL_SUMMARY_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    if spec.object_types is not None:
        missing = set(spec.object_types) - set(context.objects_by_type)
        if missing:
            return _result(
                TEMPORAL_SUMMARY_OPERATOR_ID,
                context,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                tuple(
                    ComputeIssue(
                        "unknown_object_type",
                        "Selected object type is not declared",
                        ("object_types", name),
                    )
                    for name in sorted(missing)
                ),
            )
    activities = None if spec.activities is None else frozenset(spec.activities)
    object_types = None if spec.object_types is None else frozenset(spec.object_types)
    qualifiers = None if spec.qualifiers is None else frozenset(spec.qualifiers)
    selected = {
        e.id: e
        for e in context.log.events
        if activities is None or e.type in activities
    }
    by_pair: dict[tuple[str, str], list[str]] = defaultdict(list)
    for relation in context.log.e2o:
        if relation.event not in selected:
            continue
        if (
            object_types is not None
            and context.objects_by_id[relation.object].type not in object_types
        ):
            continue
        if qualifiers is not None and relation.qualifier not in qualifiers:
            continue
        by_pair[relation.event, relation.object].append(relation.qualifier)
    participations_by_event: dict[str, list[TemporalParticipation]] = defaultdict(list)
    for (event_id, object_id), roles in sorted(by_pair.items()):
        participations_by_event[event_id].append(
            TemporalParticipation(
                event_id,
                object_id,
                context.objects_by_id[object_id].type,
                tuple(sorted(roles)),
            )
        )
    if spec.event_population == "selected_participating_events":
        selected = {
            key: value
            for key, value in selected.items()
            if key in participations_by_event
        }

    groups: dict[datetime, list[str]] = defaultdict(list)
    for event in selected.values():
        groups[event.time].append(event.id)
    buckets = []
    all_objects: set[str] = set()
    for timestamp, group in sorted(groups.items()):
        event_ids = tuple(sorted(group))
        participants = tuple(
            p for event_id in event_ids for p in participations_by_event[event_id]
        )
        object_ids = tuple(sorted({p.object_id for p in participants}))
        all_objects.update(object_ids)
        event_activities = Counter(selected[event_id].type for event_id in event_ids)
        relation_activities: Counter[str] = Counter()
        role_counts: Counter[str] = Counter()
        for pair in participants:
            relation_activities[selected[pair.event_id].type] += len(pair.qualifiers)
            role_counts.update(pair.qualifiers)
        buckets.append(
            TemporalBucket(
                timestamp,
                event_ids,
                len(event_ids),
                tuple(sorted(event_activities)),
                tuple(sorted(event_activities.items())),
                object_ids,
                len(object_ids),
                tuple(
                    sorted(
                        Counter(
                            context.objects_by_id[o].type for o in object_ids
                        ).items()
                    )
                ),
                len(participants),
                sum(role_counts.values()),
                tuple(sorted(role_counts.items())),
                tuple(sorted(relation_activities.items())),
                tuple(
                    event_id
                    for event_id in event_ids
                    if not participations_by_event[event_id]
                ),
                participants,
            )
        )
    payload = TemporalSummary(
        "exact_timestamp_distinct_events_and_qualified_relations",
        spec.event_population,
        len(context.log.events),
        len(selected),
        sum(bool(participations_by_event[e]) for e in selected),
        len(all_objects),
        sum(b.participation_count for b in buckets),
        sum(b.e2o_relation_count for b in buckets),
        tuple(buckets),
    )
    return _result(
        TEMPORAL_SUMMARY_OPERATOR_ID, context, spec, ComputeStatus.COMPUTED, payload
    )


RESULT_SCHEMAS = {
    TEMPORAL_SUMMARY_OPERATOR_ID: (
        "object-centric-temporal-summary",
        TemporalSummarySpec,
        TemporalSummary,
    ),
}

__all__ = (
    "TEMPORAL_SUMMARY_OPERATOR_ID",
    "TemporalSummarySpec",
    "TemporalParticipation",
    "TemporalBucket",
    "TemporalSummary",
    "temporal_summary",
)
