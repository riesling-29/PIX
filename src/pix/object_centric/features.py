"""Native, explicit OCEL feature extraction and predictive-data encodings.

Rows retain execution membership; overlapping executions are never silently
averaged. Strict timestamp prefixes exclude every tied event by default. A
through-timestamp profile is available for retrospective OCPA-style prefixes.
Durations are exact integer microseconds. Unknown observations remain missing;
full-execution labels never enter the fitted input encoder.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from math import isfinite, sqrt
from typing import ClassVar

from pix.compute._common import _derived_result, _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.executions import _leading_scopes, _order_evidence, discover_executions
from pix.contracts.execution import ExecutionSpec
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.ocel import OCEL


@dataclass(frozen=True, slots=True)
class ObjectFeature:
    """One named feature; parameters are explicit rather than arbitrary callables.

    ``value`` parameterizes resource/object/activity indicator functions; raw
    attribute extraction preserves Boolean, integer, text and time types.
    Aggregation is strict: one missing/non-numeric sample yields unknown.
    """

    name: str
    activity: str | None = None
    object_type: str | None = None
    attribute: str | None = None
    value: str | None = None
    aggregation: str = "mean"
    horizon_microseconds: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("feature name must be nonempty text")
        for field in (self.activity, self.object_type, self.attribute, self.value):
            if field is not None and not isinstance(field, str):
                raise TypeError("feature parameters must be text or None")
        if self.aggregation not in ("sum", "mean", "minimum", "maximum", "count"):
            raise ValueError("unsupported aggregation")
        if self.horizon_microseconds is not None and (
            type(self.horizon_microseconds) is not int or self.horizon_microseconds < 0
        ):
            raise ValueError("horizon must be nonnegative integer microseconds")


@dataclass(frozen=True, slots=True)
class ObjectFeatureSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.features.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    features: tuple[ObjectFeature, ...] = (ObjectFeature("number_of_objects"),)
    granularity: str = "event"
    execution: ExecutionSpec = ExecutionSpec("connected_components")
    prefix_policy: str = "strict_before"
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.features, tuple)
            or not self.features
            or not all(isinstance(f, ObjectFeature) for f in self.features)
        ):
            raise ValueError("features must be a nonempty tuple of ObjectFeature")
        if len(set(self.features)) != len(self.features):
            raise ValueError("duplicate feature requests")
        if self.granularity not in (
            "event",
            "object",
            "event_object_prefix",
            "execution",
        ):
            raise ValueError("unsupported feature granularity")
        if not isinstance(self.execution, ExecutionSpec):
            raise TypeError("execution must be ExecutionSpec")
        if self.prefix_policy not in ("strict_before", "through_timestamp"):
            raise ValueError("unsupported prefix policy")
        if self.as_of is not None and (
            not isinstance(self.as_of, datetime)
            or self.as_of.tzinfo is None
            or self.as_of.utcoffset() is None
        ):
            raise ValueError("as_of must have a timezone")


@dataclass(frozen=True, slots=True)
class ObjectFeatureCell:
    """Exactly typed value fields avoid lossy JSON primitive union decoding."""

    kind: str
    role: str = "input"
    integer: int | None = None
    real: float | None = None
    text: str | None = None
    boolean: bool | None = None
    time: datetime | None = None
    items: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self):
        fields = {
            "integer": self.integer,
            "real": self.real,
            "text": self.text,
            "boolean": self.boolean,
            "time": self.time,
        }
        if self.role not in ("input", "target") or self.kind not in (
            *fields,
            "items",
            "unknown",
        ):
            raise ValueError("invalid feature value kind or role")
        for name, value in fields.items():
            if (name == self.kind) != (value is not None):
                raise ValueError(
                    "feature cell must populate only its declared typed field"
                )
        if self.kind == "integer" and type(self.integer) is not int:
            raise TypeError("integer required")
        if self.kind == "real" and (
            type(self.real) is not float or not isfinite(self.real)
        ):
            raise TypeError("finite float required")
        if self.kind == "text" and not isinstance(self.text, str):
            raise TypeError("text required")
        if self.kind == "boolean" and type(self.boolean) is not bool:
            raise TypeError("Boolean required")
        if self.kind == "time" and (
            not isinstance(self.time, datetime)
            or self.time.tzinfo is None
            or self.time.utcoffset() is None
        ):
            raise TypeError("aware time required")
        if not isinstance(self.items, tuple) or not all(
            isinstance(v, str) for v in self.items
        ):
            raise TypeError("items must be a string tuple")
        if self.kind != "items" and self.items:
            raise ValueError("items require items kind")
        if self.kind == "unknown" and (
            not isinstance(self.reason, str) or not self.reason
        ):
            raise ValueError("unknown requires a reason")
        if self.kind != "unknown" and self.reason is not None:
            raise ValueError("known values cannot have a missingness reason")


@dataclass(frozen=True, slots=True)
class ObjectFeatureRow:
    row_id: str
    execution_id: str | None
    event_id: str | None
    object_id: str | None
    time: datetime | None
    event_members: tuple[str, ...]
    object_members: tuple[str, ...]
    cells: tuple[ObjectFeatureCell, ...]
    activity: str | None = None


@dataclass(frozen=True, slots=True)
class ObjectFeatureGraph:
    execution_id: str
    event_ids: tuple[str, ...]
    object_ids: tuple[str, ...]
    row_ids: tuple[str, ...]
    edges: tuple[tuple[str, str, str], ...]
    order_status: str


@dataclass(frozen=True, slots=True)
class ObjectFeatureTable:
    granularity: str
    features: tuple[ObjectFeature, ...]
    rows: tuple[ObjectFeatureRow, ...]
    graphs: tuple[ObjectFeatureGraph, ...]
    observed_cell_count: int
    target_cell_count: int
    unknown_cell_count: int
    definition_id: str
    profile: str = "unique_participation_per_execution_microseconds"


def _cell(
    value: object, role: str = "input", reason: str | None = None
) -> ObjectFeatureCell:
    if value is None:
        return ObjectFeatureCell(
            "unknown", role, reason=reason or "observation_missing"
        )
    if isinstance(value, bool):
        return ObjectFeatureCell("boolean", role, boolean=value)
    if isinstance(value, int):
        return ObjectFeatureCell("integer", role, integer=value)
    if isinstance(value, float):
        if not isfinite(value):
            return _cell(None, role, "non_finite_number")
        return ObjectFeatureCell("real", role, real=value)
    if isinstance(value, str):
        return ObjectFeatureCell("text", role, text=value)
    if isinstance(value, datetime):
        return ObjectFeatureCell("time", role, time=value)
    if isinstance(value, tuple) and all(isinstance(v, str) for v in value):
        return ObjectFeatureCell("items", role, items=value)
    return _cell(None, role, "unsupported_value_type")


def _us(delta: timedelta) -> int:
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _attr(event: object, name: str | None) -> object:
    return next((a.value for a in event.attributes if a.name == name), None)


def _asof(obj: object, name: str | None, time: datetime | None) -> object:
    if time is None:
        return None
    values = [a for a in obj.attributes if a.name == name and a.time <= time]
    return max(values, key=lambda a: a.time).value if values else None


def _aggregate(values: list[object], operation: str) -> object:
    if operation == "count":
        return len(values) if all(v is not None for v in values) else None
    if not values or any(type(v) not in (int, float) for v in values):
        return None
    try:
        if operation == "sum":
            return sum(values)
        if operation == "minimum":
            return min(values)
        if operation == "maximum":
            return max(values)
        return sum(values) / len(values)
    except OverflowError:
        return None


def _seconds_start(event: object, attribute: str | None) -> datetime | None:
    start = _attr(event, attribute)
    return start if isinstance(start, datetime) and start <= event.time else None


def _row_id(parts: tuple[str, ...]) -> str:
    # Length delimiting prevents ambiguous concatenated entity IDs.
    payload = "".join(f"{len(part)}:{part}" for part in parts)
    return "feature:" + sha256(payload.encode()).hexdigest()


def _prefix(events: list[object], time: datetime, policy: str) -> list[object]:
    return [
        e
        for e in events
        if e.time < time or (policy == "through_timestamp" and e.time == time)
    ]


EVENT_FEATURES = (
    "number_of_objects",
    "event_activity",
    "service_time",
    "event_identity",
    "event_type_count",
    "preceding_activities",
    "previous_activity_count",
    "current_activities",
    "agg_previous_char_values",
    "preceding_char_values",
    "characteristic_value",
    "current_resource_workload",
    "current_total_workload",
    "event_resource",
    "current_total_object_count",
    "previous_object_count",
    "previous_type_count",
    "event_objects",
    "execution_duration",
    "elapsed_time",
    "remaining_time",
    "lagging_time",
    "pooling_time",
    "waiting_time",
    "sojourn_time",
    "synchronization_time",
    "flow_time",
    "activity",
    "timestamp",
    "object_ids",
    "prefix_event_count",
    "start_object_type_count",
    "end_object_type_count",
    "new_interactions",
    "calendar_year",
    "calendar_month",
    "calendar_day",
    "calendar_weekday",
    "calendar_hour",
    "related_object_attribute",
)
EXECUTION_FEATURES = (
    "number_of_events",
    "number_of_ending_events",
    "throughput_time",
    "execution",
    "number_of_objects",
    "unique_activities",
    "number_of_starting_events",
    "delta_last_event",
    "service_time",
    "avg_service_time",
)
OBJECT_FEATURES = (
    "number_of_events",
    "unique_activities",
    "activity_count",
    "lifecycle_duration",
    "first_activity",
    "last_activity",
    "object_attribute",
    "object_type",
    "interaction_count",
    "interaction_type_count",
    "descendant_count",
    "ascendant_count",
    "cobirth_count",
    "codeath_count",
    "work_in_progress",
    "lifecycle_start",
    "lifecycle_end",
    "degree_centrality",
    "activity_pair_count",
    "inheritance_in_count",
    "inheritance_out_count",
    "related_event_attribute",
    "last_activity_attribute",
    "neighbor_object_attribute",
)
PREFIX_FEATURES = (
    "prefix_event_count",
    "previous_activity_count",
    "elapsed_time",
    "object_attribute",
    "object_type",
    "agg_previous_char_values",
    "last_activity",
    "activity",
    "timestamp",
)


def _event_value(
    request,
    event,
    events,
    predecessors,
    edges,
    ctx,
    spec,
    object_events,
    event_objects,
    target_events,
):
    name, time = request.name, event.time
    if (
        name
        in (
            "event_activity",
            "preceding_activities",
            "previous_activity_count",
            "current_activities",
        )
        and request.activity is None
    ):
        return _cell(None, reason="activity_parameter_required")
    if name in ("event_objects", "event_resource") and request.value is None:
        return _cell(None, reason="value_parameter_required")
    if (
        name
        in (
            "event_type_count",
            "previous_type_count",
            "pooling_time",
            "lagging_time",
            "start_object_type_count",
            "end_object_type_count",
        )
        and request.object_type is None
    ):
        return _cell(None, reason="object_type_parameter_required")
    previous = _prefix(events, time, spec.prefix_policy)
    previous_ids = {e.id for e in previous}
    participants = event_objects[event.id]

    def typed(ids):
        return {
            object_id
            for object_id in ids
            if request.object_type is None
            or ctx.objects_by_id[object_id].type == request.object_type
        }

    times = [e.time for e in events]
    role = (
        "target"
        if name in ("execution_duration", "remaining_time", "end_object_type_count")
        else "input"
    )
    if name == "number_of_objects":
        value = len(participants)
    elif name == "event_activity":
        value = int(event.type == request.activity)
    elif name == "activity":
        value = event.type
    elif name == "timestamp":
        value = time
    elif name.startswith("calendar_"):
        component = name[len("calendar_") :]
        if component not in ("year", "month", "day", "weekday", "hour"):
            return _cell(None, reason="unsupported_feature")
        # Context normalizes to UTC; calendar components therefore use UTC.
        value = time.weekday() if component == "weekday" else getattr(time, component)
    elif name == "event_identity":
        value = 1
    elif name == "event_type_count":
        value = len(typed(participants))
    elif name == "object_ids":
        value = tuple(sorted(participants))
    elif name == "event_objects":
        value = int(request.value in participants)
    elif name == "prefix_event_count":
        value = len(previous)
    elif name == "previous_activity_count":
        value = sum(e.type == request.activity for e in previous)
    elif name == "preceding_activities":
        if predecessors is None:
            return _cell(None, reason="ambiguous_event_order")
        value = sum(e.type == request.activity for e in predecessors)
    elif name == "current_activities":
        if edges is None:
            return _cell(None, reason="ambiguous_event_order")
        non_sinks = {a for a, b, _ in edges if a in previous_ids and b in previous_ids}
        value = int(
            any(e.type == request.activity and e.id not in non_sinks for e in previous)
        )
    elif name in ("characteristic_value", "event_resource"):
        value = _attr(event, request.attribute)
        if name == "event_resource" and value is not None:
            value = int(value == request.value)
    elif name in ("agg_previous_char_values", "preceding_char_values"):
        source = previous if name == "agg_previous_char_values" else predecessors
        if source is None:
            return _cell(None, reason="ambiguous_event_order")
        value = _aggregate(
            [_attr(e, request.attribute) for e in source], request.aggregation
        )
    elif name in ("previous_object_count", "previous_type_count"):
        ids = {o for e in previous for o in event_objects[e.id]}
        value = len(typed(ids) if name == "previous_type_count" else ids)
    elif name in (
        "current_resource_workload",
        "current_total_workload",
        "current_total_object_count",
    ):
        if request.horizon_microseconds is None:
            return _cell(None, reason="horizon_required")
        # These are trailing completion counts, not in-flight workload estimates.
        recent = [
            e
            for e in _prefix(list(ctx.log.events), time, spec.prefix_policy)
            if _us(time - e.time) <= request.horizon_microseconds
        ]
        if name == "current_resource_workload":
            resource = _attr(event, request.attribute)
            if resource is None:
                return _cell(None, reason="resource_missing")
            if any(_attr(e, request.attribute) is None for e in recent):
                return _cell(None, reason="historical_resource_coverage_incomplete")
            value = sum(_attr(e, request.attribute) == resource for e in recent)
        elif name == "current_total_workload":
            value = len(recent)
        else:
            value = len({o for e in recent for o in event_objects[e.id]})
    elif name in ("execution_duration", "elapsed_time", "remaining_time"):
        if name == "execution_duration":
            value = _us(
                max(e.time for e in target_events) - min(e.time for e in target_events)
            )
        elif name == "elapsed_time":
            value = _us(time - min(times)) if times else None
        else:
            value = _us(max(e.time for e in target_events) - time)
    elif name == "service_time":
        start = _seconds_start(event, request.attribute)
        value = _us(time - start) if start is not None else None
    elif name in (
        "flow_time",
        "sojourn_time",
        "waiting_time",
        "synchronization_time",
        "pooling_time",
        "lagging_time",
    ):
        if predecessors is None:
            return _cell(None, reason="ambiguous_event_order")
        if not predecessors:
            return _cell(None, reason="predecessor_arrival_unobserved")
        arrival = [e.time for e in predecessors]
        if name == "flow_time":
            value = _us(time - min(arrival))
        elif name == "sojourn_time":
            value = _us(time - max(arrival))
        elif name == "synchronization_time":
            value = _us(max(arrival) - min(arrival))
        elif name == "waiting_time":
            start = _seconds_start(event, request.attribute)
            value = (
                _us(start - max(arrival))
                if start is not None and start >= max(arrival)
                else None
            )
        else:
            type_arrival = defaultdict(list)
            for pred in predecessors:
                # Attribute predecessor arrivals to the actual shared arc objects.
                shared = {o for a, b, o in edges if a == pred.id and b == event.id}
                for o in shared:
                    type_arrival[ctx.objects_by_id[o].type].append(pred.time)
            selected = type_arrival.get(request.object_type, [])
            if not selected:
                return _cell(None, reason="object_type_arrival_unobserved")
            if name == "pooling_time":
                value = _us(max(selected) - min(selected))
            else:
                value = _us(max(selected) - min(max(v) for v in type_arrival.values()))
    elif name in ("start_object_type_count", "end_object_type_count"):
        selected = typed(participants)
        endpoint = min if name == "start_object_type_count" else max
        value = sum(
            time == endpoint(ctx.events_by_id[e].time for e in object_events[o])
            for o in selected
        )
    elif name == "new_interactions":
        pairs = {(a, b) for a in participants for b in participants if a < b}
        old_pairs = set()
        for e in ctx.log.events:
            if e.time < time:
                ids = event_objects[e.id]
                old_pairs.update((a, b) for a in ids for b in ids if a < b)
        value = len(pairs - old_pairs)
    elif name == "related_object_attribute":
        value = _aggregate(
            [
                _asof(ctx.objects_by_id[o], request.attribute, time)
                for o in sorted(typed(participants))
            ],
            request.aggregation,
        )
    else:
        return _cell(None, reason="unsupported_feature")
    return _cell(value, role)


def _execution_value(request, execution, events, ctx, edges):
    name, role = request.name, "target"
    if name == "number_of_events":
        value = len(events)
    elif name == "execution":
        value = 1
    elif name == "number_of_objects":
        value = len(execution.objects)
    elif name == "unique_activities":
        value = len({e.type for e in events})
    elif name in ("number_of_starting_events", "number_of_ending_events"):
        if edges is None:
            return _cell(None, role, "ambiguous_event_order")
        used = {edge[1 if name == "number_of_starting_events" else 0] for edge in edges}
        value = sum(e.id not in used for e in events)
    elif name in ("throughput_time", "delta_last_event"):
        if not events:
            return _cell(None, role, "empty_execution")
        times = sorted(e.time for e in events)
        value = (
            _us(times[-1] - times[0])
            if name == "throughput_time"
            else (_us(times[-1] - times[-2]) if len(times) > 1 else 0)
        )
    elif name in ("service_time", "avg_service_time"):
        starts = [_seconds_start(e, request.attribute) for e in events]
        if not events or any(t is None for t in starts):
            return _cell(None, role, "incomplete_service_coverage")
        values = [_us(e.time - t) for e, t in zip(events, starts)]
        value = sum(values) if name == "service_time" else sum(values) / len(values)
    else:
        return _cell(None, role, "unsupported_feature")
    return _cell(value, role)


def _object_value(request, obj, events, ctx, spec, object_events, event_objects):
    name = request.name
    role = "input" if spec.as_of is not None else "target"
    if name == "object_attribute":
        # An unbounded history query would silently choose a future value.
        return _cell(
            _asof(obj, request.attribute, spec.as_of),
            role,
            "as_of_required" if spec.as_of is None else "attribute_unobserved",
        )
    if name == "object_type":
        return _cell(obj.type, "input")
    if name == "number_of_events":
        value = len(events)
    elif name == "unique_activities":
        value = len({e.type for e in events})
    elif name == "activity_count":
        value = sum(e.type == request.activity for e in events)
    elif name == "lifecycle_duration":
        value = (
            _us(max(e.time for e in events) - min(e.time for e in events))
            if events
            else None
        )
    elif name == "lifecycle_start":
        value = min((e.time for e in events), default=None)
    elif name == "lifecycle_end":
        value = max((e.time for e in events), default=None)
    elif name == "activity_pair_count":
        if request.activity is None or request.value is None:
            return _cell(None, role, "activity_and_successor_required")
        ordered = sorted(events, key=lambda e: (e.time, e.id))
        if any(a.time == b.time for a, b in zip(ordered, ordered[1:])):
            return _cell(None, role, "ambiguous_event_order")
        value = sum(
            a.type == request.activity and b.type == request.value
            for a, b in zip(ordered, ordered[1:])
        )
    elif name in ("related_event_attribute", "last_activity_attribute"):
        selected = [
            e for e in events if request.activity is None or e.type == request.activity
        ]
        if name == "last_activity_attribute" and selected:
            latest = max(e.time for e in selected)
            selected = [e for e in selected if e.time == latest]
        value = _aggregate(
            [_attr(e, request.attribute) for e in selected], request.aggregation
        )
    elif name in ("first_activity", "last_activity"):
        if not events:
            value = None
        else:
            endpoint = (min if name == "first_activity" else max)(
                e.time for e in events
            )
            value = tuple(sorted({e.type for e in events if e.time == endpoint}))
    elif name in (
        "interaction_count",
        "interaction_type_count",
        "degree_centrality",
        "neighbor_object_attribute",
    ):
        neighbors = {o for e in events for o in event_objects[e.id] if o != obj.id}
        if name == "interaction_type_count":
            neighbors = {
                o for o in neighbors if ctx.objects_by_id[o].type == request.object_type
            }
        if name == "neighbor_object_attribute":
            if spec.as_of is None:
                return _cell(None, role, "as_of_required")
            value = _aggregate(
                [
                    _asof(ctx.objects_by_id[o], request.attribute, spec.as_of)
                    for o in sorted(neighbors)
                ],
                request.aggregation,
            )
        elif name == "degree_centrality":
            population = sum(
                (
                    spec.execution.object_types is None
                    or o.type in spec.execution.object_types
                )
                and (
                    spec.as_of is None
                    or any(
                        ctx.events_by_id[e].time <= spec.as_of
                        for e in object_events[o.id]
                    )
                    or any(a.time <= spec.as_of for a in o.attributes)
                )
                for o in ctx.log.objects
            )
            value = len(neighbors) / (population - 1) if population > 1 else 0.0
        else:
            value = len(neighbors)
    elif name in (
        "descendant_count",
        "ascendant_count",
        "cobirth_count",
        "codeath_count",
        "work_in_progress",
        "inheritance_in_count",
        "inheritance_out_count",
    ):
        if not events:
            return _cell(None, role, "lifecycle_unobserved")
        start, end = min(e.time for e in events), max(e.time for e in events)
        own_ids = {e.id for e in events}
        count = 0
        for other in ctx.log.objects:
            if other.id == obj.id or (
                request.object_type is not None and other.type != request.object_type
            ):
                continue
            other_events = [
                ctx.events_by_id[e]
                for e in object_events[other.id]
                if spec.as_of is None or ctx.events_by_id[e].time <= spec.as_of
            ]
            if not other_events:
                continue
            a, b = min(e.time for e in other_events), max(e.time for e in other_events)
            shared = own_ids & {e.id for e in other_events}
            if name == "work_in_progress":
                matches = a <= end and start <= b
            elif name == "cobirth_count":
                matches = any(ctx.events_by_id[e].time == start == a for e in shared)
            elif name == "codeath_count":
                matches = any(ctx.events_by_id[e].time == end == b for e in shared)
            elif name == "inheritance_out_count":
                matches = not (start == end == a == b) and any(
                    ctx.events_by_id[e].time == end == a for e in shared
                )
            elif name == "inheritance_in_count":
                matches = not (start == end == a == b) and any(
                    ctx.events_by_id[e].time == start == b for e in shared
                )
            elif name == "descendant_count":
                matches = start < a and any(
                    ctx.events_by_id[e].time == a for e in shared
                )
            else:
                matches = a < start and any(
                    ctx.events_by_id[e].time == start for e in shared
                )
            count += matches
        value = count + (1 if name == "work_in_progress" else 0)
    else:
        return _cell(None, role, "unsupported_feature")
    return _cell(value, role)


def _prefix_value(request, obj, event, events, spec):
    previous = _prefix(events, event.time, spec.prefix_policy)
    if request.name == "prefix_event_count":
        value = len(previous)
    elif request.name == "previous_activity_count":
        value = sum(e.type == request.activity for e in previous)
    elif request.name == "elapsed_time":
        value = _us(event.time - min(e.time for e in previous)) if previous else None
    elif request.name == "object_attribute":
        value = _asof(obj, request.attribute, event.time)
    elif request.name == "object_type":
        value = obj.type
    elif request.name == "activity":
        value = event.type
    elif request.name == "timestamp":
        value = event.time
    elif request.name == "agg_previous_char_values":
        value = _aggregate(
            [_attr(e, request.attribute) for e in previous], request.aggregation
        )
    elif request.name == "last_activity":
        value = (
            tuple(
                sorted(
                    {
                        e.type
                        for e in previous
                        if e.time == max(p.time for p in previous)
                    }
                )
            )
            if previous
            else None
        )
    else:
        return _cell(None, reason="unsupported_feature")
    return _cell(value)


OBJECT_FEATURES_OPERATOR_ID = "pix.object_centric.features"


def _observed_scope(event, execution, ctx, spec, object_events, event_objects):
    """Derive event-time incidence scopes before reading any prefix feature.

    A future joining event must not make formerly independent past executions
    available to a prefix. In strict mode, other equal-timestamp events are also
    excluded. The current event's own participation is known at observation.
    """
    allowed = {
        e.id
        for e in ctx.log.events
        if e.time < event.time
        or e.id == event.id
        or (spec.prefix_policy == "through_timestamp" and e.time == event.time)
    }
    bounded = {o: ids & allowed for o, ids in object_events.items()}
    if execution.leading_object_id is None:
        scope, objects, frontier = {event.id}, set(), {event.id}
        while frontier:
            next_objects = {o for e in frontier for o in event_objects[e]} - objects
            objects.update(next_objects)
            neighbors = {e for o in next_objects for e in bounded[o]}
            frontier = neighbors - scope
            scope.update(frontier)
    else:
        selected = {
            o.id
            for o in ctx.log.objects
            if spec.execution.object_types is None
            or o.type in spec.execution.object_types
        }
        scopes = _leading_scopes(ctx, spec.execution, selected, bounded, event_objects)
        scope, objects, _ = next(
            s for s in scopes if s[2] == execution.leading_object_id
        )
        if event.id not in scope:
            return [], None
    ordered, ties = _order_evidence(
        ctx, spec.execution, {o: bounded[o] & scope for o in objects}
    )
    if spec.execution.tie_policy == "reject" and any(ties.values()):
        edges = None
    else:
        edges = tuple(
            (e.source_event, e.target_event, e.object_id)
            for o in sorted(ordered)
            for e in ordered[o]
        )
    return [ctx.events_by_id[e] for e in sorted(scope)], edges


def extract_object_features(
    log: OCEL | ComputationContext, spec: ObjectFeatureSpec = ObjectFeatureSpec()
) -> ComputationResult[ObjectFeatureTable]:
    """Extract four granularities without dependencies on PM4Py, OCPA or pandas.

    ``as_of`` restricts observed rows/attributes, but full-log execution extraction
    is a retrospective cohort definition, not a streaming case-assignment claim.
    Execution rows and full-future event labels have role ``target``.
    """
    if not isinstance(spec, ObjectFeatureSpec):
        raise TypeError("spec must be ObjectFeatureSpec")
    ctx, issues = _prepare(log)
    if ctx is None:
        return _result(
            OBJECT_FEATURES_OPERATOR_ID,
            None,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            issues,
        )
    extracted = discover_executions(ctx, spec.execution)
    if extracted.value is None:
        return _result(
            OBJECT_FEATURES_OPERATOR_ID,
            ctx,
            spec,
            extracted.status,
            None,
            extracted.issues,
        )
    selected_types, qualifiers = spec.execution.object_types, spec.execution.qualifiers
    relations = [
        r
        for r in ctx.log.e2o
        if (
            selected_types is None or ctx.objects_by_id[r.object].type in selected_types
        )
        and (qualifiers is None or r.qualifier in qualifiers)
    ]
    object_events = {o.id: set() for o in ctx.log.objects}
    event_objects = {e.id: set() for e in ctx.log.events}
    for rel in relations:
        object_events[rel.object].add(rel.event)
        event_objects[rel.event].add(rel.object)
    rows, graphs = [], []
    if spec.granularity == "object":
        for obj in ctx.log.objects:
            if selected_types is not None and obj.type not in selected_types:
                continue
            if spec.as_of is not None and not (
                any(
                    ctx.events_by_id[e].time <= spec.as_of
                    for e in object_events[obj.id]
                )
                or any(a.time <= spec.as_of for a in obj.attributes)
            ):
                # A bare declaration does not establish when this object existed.
                continue
            events = [
                ctx.events_by_id[e]
                for e in sorted(object_events[obj.id])
                if spec.as_of is None or ctx.events_by_id[e].time <= spec.as_of
            ]
            row_id = _row_id(("object", obj.id))
            rows.append(
                ObjectFeatureRow(
                    row_id,
                    None,
                    None,
                    obj.id,
                    spec.as_of,
                    tuple(e.id for e in events),
                    (obj.id,),
                    tuple(
                        _object_value(
                            f, obj, events, ctx, spec, object_events, event_objects
                        )
                        for f in spec.features
                    ),
                )
            )
    else:
        for execution in extracted.value.executions:
            all_events = [ctx.events_by_id[e.id] for e in execution.events]
            events = [
                e for e in all_events if spec.as_of is None or e.time <= spec.as_of
            ]
            event_ids = tuple(sorted(e.id for e in events))
            object_ids = tuple(
                sorted(
                    {
                        o.id
                        for o in execution.objects + execution.boundary_objects
                        if spec.as_of is None
                        or any(
                            ctx.events_by_id[e].time <= spec.as_of
                            for e in object_events[o.id]
                        )
                        or any(
                            a.time <= spec.as_of
                            for a in ctx.objects_by_id[o.id].attributes
                        )
                    }
                )
            )
            edges = tuple(
                (e.source_event, e.target_event, e.object_id)
                for e in execution.order_edges
                if e.source_event in event_ids and e.target_event in event_ids
            )
            graph_edges = edges if execution.order_status == "complete" else None
            member_rows = []
            if spec.granularity == "execution":
                row_id = _row_id(("execution", execution.execution_id))
                member_rows.append(row_id)
                rows.append(
                    ObjectFeatureRow(
                        row_id,
                        execution.execution_id,
                        None,
                        None,
                        max((e.time for e in events), default=None),
                        event_ids,
                        object_ids,
                        tuple(
                            _execution_value(f, execution, events, ctx, graph_edges)
                            for f in spec.features
                        ),
                    )
                )
            for event in [] if spec.granularity == "execution" else events:
                if spec.granularity == "event":
                    observed_events, observed_edges = _observed_scope(
                        event, execution, ctx, spec, object_events, event_objects
                    )
                    predecessors = (
                        None
                        if observed_edges is None
                        else [
                            ctx.events_by_id[p]
                            for p in sorted(
                                {a for a, b, _ in observed_edges if b == event.id}
                            )
                        ]
                    )
                    row_id = _row_id(("event", execution.execution_id, event.id))
                    member_rows.append(row_id)
                    cells = tuple(
                        _event_value(
                            f,
                            event,
                            observed_events,
                            predecessors,
                            observed_edges,
                            ctx,
                            spec,
                            object_events,
                            event_objects,
                            all_events,
                        )
                        for f in spec.features
                    )
                    rows.append(
                        ObjectFeatureRow(
                            row_id,
                            execution.execution_id,
                            event.id,
                            None,
                            event.time,
                            (event.id,),
                            tuple(sorted(event_objects[event.id])),
                            cells,
                            activity=event.type,
                        )
                    )
                else:
                    for object_id in sorted(
                        event_objects[event.id] & {o.id for o in execution.objects}
                    ):
                        obj = ctx.objects_by_id[object_id]
                        lifecycle = [
                            ctx.events_by_id[e] for e in object_events[object_id]
                        ]
                        row_id = _row_id(
                            (
                                "event_object_prefix",
                                execution.execution_id,
                                event.id,
                                object_id,
                            )
                        )
                        member_rows.append(row_id)
                        rows.append(
                            ObjectFeatureRow(
                                row_id,
                                execution.execution_id,
                                event.id,
                                object_id,
                                event.time,
                                (event.id,),
                                (object_id,),
                                tuple(
                                    _prefix_value(f, obj, event, lifecycle, spec)
                                    for f in spec.features
                                ),
                                activity=event.type,
                            )
                        )
            graphs.append(
                ObjectFeatureGraph(
                    execution.execution_id,
                    event_ids,
                    object_ids,
                    tuple(member_rows),
                    edges if graph_edges is not None else (),
                    execution.order_status,
                )
            )
    rows = tuple(sorted(rows, key=lambda r: r.row_id))
    unknown = sum(c.kind == "unknown" for r in rows for c in r.cells)
    targets = sum(
        c.role == "target" and c.kind != "unknown" for r in rows for c in r.cells
    )
    observed = sum(
        c.role == "input" and c.kind != "unknown" for r in rows for c in r.cells
    )
    issue_list = list(extracted.issues)
    if unknown:
        issue_list.append(
            ComputeIssue(
                "unknown_feature_cells",
                f"{unknown} cells have explicit missingness reasons; no zero imputation.",
            )
        )
    definition = computation_identity(
        "pix.object_centric.feature_definition",
        "1.0.0",
        "definition",
        replace(spec, as_of=None),
        (),
    )
    payload = ObjectFeatureTable(
        spec.granularity,
        spec.features,
        rows,
        tuple(graphs),
        observed,
        targets,
        unknown,
        definition,
    )
    return _result(
        OBJECT_FEATURES_OPERATOR_ID,
        ctx,
        spec,
        ComputeStatus.PARTIAL if unknown else ComputeStatus.COMPUTED,
        payload,
        tuple(issue_list),
        parent_computation_ids=(extracted.computation_id,),
    )


@dataclass(frozen=True, slots=True)
class ObjectFeatureEncodingSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_encoding.spec"
    mode: str = "sequence"
    window_microseconds: int | None = None
    origin: datetime | None = None

    def __post_init__(self):
        if self.mode not in ("tabular", "sequence", "graph", "time_window"):
            raise ValueError("unsupported encoding mode")
        if self.mode == "time_window":
            if (
                type(self.window_microseconds) is not int
                or self.window_microseconds < 1
            ):
                raise ValueError("positive window_microseconds required")
            if (
                not isinstance(self.origin, datetime)
                or self.origin.tzinfo is None
                or self.origin.utcoffset() is None
            ):
                raise ValueError("aware window origin required")
        elif self.window_microseconds is not None or self.origin is not None:
            raise ValueError("window parameters require time_window mode")


@dataclass(frozen=True, slots=True)
class ObjectFeatureGroup:
    group_id: str
    execution_id: str | None
    timestamp: datetime | None
    row_ids: tuple[str, ...]
    numeric_means: tuple[float | None, ...]
    numeric_coverage: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ObjectFeatureEncoding:
    mode: str
    features: tuple[ObjectFeature, ...]
    rows: tuple[ObjectFeatureRow, ...]
    groups: tuple[ObjectFeatureGroup, ...]
    graphs: tuple[ObjectFeatureGraph, ...]
    row_ids: tuple[str, ...]


def _table(result):
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id
        not in (OBJECT_FEATURES_OPERATOR_ID, "pix.object_centric.feature_aggregation")
        or not isinstance(result.value, ObjectFeatureTable)
    ):
        raise TypeError("expected successful extract_object_features result")
    return result.value


@dataclass(frozen=True, slots=True)
class ObjectFeatureAggregationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_aggregation.spec"
    relation: str
    aggregation: str = "mean"
    feature_indices: tuple[int, ...] | None = None
    source_activity: str | None = None
    last_source_time_only: bool = False
    weighting: str = "unique_entity"

    def __post_init__(self):
        if self.relation not in (
            "event_to_object",
            "object_to_event",
            "object_interaction",
        ):
            raise ValueError("unsupported relation")
        if self.aggregation not in ("minimum", "maximum", "sum", "mean", "count"):
            raise ValueError("unsupported aggregation")
        if self.feature_indices is not None and (
            not isinstance(self.feature_indices, tuple)
            or not all(type(v) is int and v >= 0 for v in self.feature_indices)
        ):
            raise TypeError("feature_indices must be nonnegative integer tuple or None")
        if self.feature_indices is not None and len(set(self.feature_indices)) != len(
            self.feature_indices
        ):
            raise ValueError("duplicate feature index")
        if self.source_activity is not None and not isinstance(
            self.source_activity, str
        ):
            raise TypeError("source_activity must be text or None")
        if type(self.last_source_time_only) is not bool:
            raise TypeError("last_source_time_only must be Boolean")
        if self.weighting not in ("unique_entity", "membership"):
            raise ValueError("unsupported weighting")


def aggregate_object_features(
    source: ComputationResult[ObjectFeatureTable],
    target: ComputationResult[ObjectFeatureTable],
    spec: ObjectFeatureAggregationSpec,
) -> ComputationResult[ObjectFeatureTable]:
    """Compose related event/object/interaction-neighbor numeric features.

    This covers PM4Py's related-events, last-related-activity, related-objects and
    graph-neighbor feature aggregation families without fixing feature columns.
    Unknown or conflicting per-execution values remain unknown. Retrospective
    source summaries propagate target role when attached to an earlier event.
    """
    if not isinstance(spec, ObjectFeatureAggregationSpec):
        raise TypeError("invalid aggregation spec")
    sources, targets = _table(source), _table(target)
    parents = (source.computation_id, target.computation_id)
    operator = "pix.object_centric.feature_aggregation"

    def invalid(code, message):
        return _derived_result(
            operator,
            target.source_digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue(code, message),),
            parent_computation_ids=parents,
        )

    if source.source_digest != target.source_digest:
        return invalid(
            "feature_source_mismatch",
            "Relations require feature tables from the same canonical source.",
        )
    expected = {
        "event_to_object": ("event", "object"),
        "object_to_event": ("object", "event"),
        "object_interaction": ("object", "object"),
    }
    if (sources.granularity, targets.granularity) != expected[spec.relation]:
        return invalid(
            "feature_granularity_mismatch",
            "Source and target granularities do not match relation.",
        )
    indices = (
        spec.feature_indices
        if spec.feature_indices is not None
        else tuple(range(len(sources.features)))
    )
    if any(index >= len(sources.features) for index in indices):
        return invalid(
            "unknown_feature_index", "Feature index exceeds source table columns."
        )
    rows = []
    for target_row in targets.rows:
        related = []
        for source_row in sources.rows:
            if (
                spec.source_activity is not None
                and source_row.activity != spec.source_activity
            ):
                continue
            if spec.relation == "event_to_object":
                matches = source_row.event_id in target_row.event_members
            elif spec.relation == "object_to_event":
                matches = source_row.object_id in target_row.object_members
            else:
                matches = source_row.object_id != target_row.object_id and bool(
                    set(source_row.event_members) & set(target_row.event_members)
                )
            if matches:
                related.append(source_row)
        if spec.last_source_time_only and related:
            known_times = [r.time for r in related if r.time is not None]
            related = [r for r in related if known_times and r.time == max(known_times)]
        cells = []
        for index in indices:
            role = (
                "target"
                if any(
                    r.cells[index].role == "target"
                    or (
                        target_row.time is not None
                        and (r.time is None or r.time > target_row.time)
                    )
                    for r in related
                )
                else "input"
            )
            grouped = defaultdict(list)
            for row in related:
                identity = (
                    (
                        row.event_id
                        if spec.relation == "event_to_object"
                        else row.object_id
                    )
                    if spec.weighting == "unique_entity"
                    else row.row_id
                )
                grouped[identity].append(row.cells[index])
            if any(len(set(values)) > 1 for values in grouped.values()):
                cells.append(
                    _cell(None, role, "conflicting_execution_membership_values")
                )
                continue
            observations = [values[0] for values in grouped.values()]
            if any(cell.kind == "unknown" for cell in observations):
                cells.append(_cell(None, role, "source_feature_unknown"))
                continue
            value = _aggregate(
                [_number(cell) for cell in observations], spec.aggregation
            )
            cells.append(_cell(value, role, "numeric_source_observation_required"))
        rows.append(
            ObjectFeatureRow(
                target_row.row_id,
                target_row.execution_id,
                target_row.event_id,
                target_row.object_id,
                target_row.time,
                target_row.event_members,
                target_row.object_members,
                tuple(cells),
                target_row.activity,
            )
        )
    unknown = sum(c.kind == "unknown" for r in rows for c in r.cells)
    target_count = sum(
        c.kind != "unknown" and c.role == "target" for r in rows for c in r.cells
    )
    observed = sum(
        c.kind != "unknown" and c.role == "input" for r in rows for c in r.cells
    )
    issues = (
        (
            ComputeIssue(
                "unknown_feature_cells",
                f"{unknown} related feature cells remain unknown.",
            ),
        )
        if unknown
        else ()
    )
    definition = computation_identity(
        "pix.object_centric.feature_definition",
        "1.0.0",
        "definition",
        spec,
        (sources.definition_id, targets.definition_id),
    )
    value = ObjectFeatureTable(
        targets.granularity,
        tuple(sources.features[i] for i in indices),
        tuple(rows),
        targets.graphs,
        observed,
        target_count,
        unknown,
        definition,
        "related_feature_aggregation",
    )
    return _derived_result(
        operator,
        target.source_digest,
        spec,
        ComputeStatus.PARTIAL if unknown else ComputeStatus.COMPUTED,
        value,
        issues,
        parent_computation_ids=parents,
    )


def _number(cell):
    if cell.kind == "integer":
        return cell.integer
    if cell.kind == "real":
        return cell.real
    return None


def encode_object_features(
    result: ComputationResult[ObjectFeatureTable],
    spec: ObjectFeatureEncodingSpec = ObjectFeatureEncodingSpec(),
) -> ComputationResult[ObjectFeatureEncoding]:
    """Sequences keep ties in timestamp groups; windows are [start, end).

    Window aggregation includes input numeric cells only and reports observed
    sample counts. Rows remain recoverable through IDs; targets are not averaged.
    """
    if not isinstance(spec, ObjectFeatureEncodingSpec):
        raise TypeError("invalid encoding spec")
    table = _table(result)
    grouped = defaultdict(list)
    issues = []
    for row in table.rows:
        if spec.mode in ("sequence", "time_window") and row.time is None:
            issues.append(
                ComputeIssue(
                    "row_time_missing",
                    "Row cannot enter temporal encoding",
                    (row.row_id,),
                )
            )
            continue
        if spec.mode == "sequence":
            key = (row.execution_id or row.object_id or "", row.time)
        elif spec.mode == "time_window":
            index = _us(row.time - spec.origin) // spec.window_microseconds
            key = ("window", index)
        else:
            key = (row.row_id, None)
        grouped[key].append(row)
    groups = []
    for key, members in sorted(
        grouped.items(),
        key=lambda pair: (pair[0][0], pair[0][1] if pair[0][1] is not None else ""),
    ):
        if spec.mode == "time_window":
            timestamp = spec.origin + timedelta(
                microseconds=key[1] * spec.window_microseconds
            )
            execution_id = None
        else:
            timestamp = members[0].time
            execution_id = members[0].execution_id
        means, coverage = [], []
        for i in range(len(table.features)):
            values = [
                _number(r.cells[i])
                for r in members
                if r.cells[i].role == "input" and _number(r.cells[i]) is not None
            ]
            try:
                mean = sum(values) / len(values) if values else None
            except OverflowError:
                mean = None
            if mean is not None and not isfinite(mean):
                mean = None
            means.append(mean)
            coverage.append(len(values) if mean is not None else 0)
        ids = tuple(sorted(r.row_id for r in members))
        groups.append(
            ObjectFeatureGroup(
                _row_id(ids),
                execution_id,
                timestamp,
                ids,
                tuple(means),
                tuple(coverage),
            )
        )
    payload = ObjectFeatureEncoding(
        spec.mode,
        table.features,
        table.rows,
        tuple(groups),
        table.graphs if spec.mode == "graph" else (),
        tuple(r.row_id for r in table.rows),
    )
    return _derived_result(
        "pix.object_centric.feature_encoding",
        result.source_digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        tuple(issues),
        parent_computation_ids=(result.computation_id,),
    )


@dataclass(frozen=True, slots=True)
class ObjectFeatureSplitSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_split.spec"
    train_fraction: float = 0.8
    seed: str = "0"
    group_shared_entities: bool = True

    def __post_init__(self):
        if (
            type(self.train_fraction) not in (int, float)
            or not isfinite(self.train_fraction)
            or not 0 < self.train_fraction < 1
        ):
            raise ValueError("train_fraction must be strictly between 0 and 1")
        if not isinstance(self.seed, str):
            raise TypeError("seed must be text")
        if type(self.group_shared_entities) is not bool:
            raise TypeError("group_shared_entities must be bool")


@dataclass(frozen=True, slots=True)
class ObjectFeaturePartition:
    train_row_ids: tuple[str, ...]
    test_row_ids: tuple[str, ...]
    train_execution_ids: tuple[str, ...]
    test_execution_ids: tuple[str, ...]
    shared_event_ids: tuple[str, ...]
    shared_object_ids: tuple[str, ...]
    independent_group_count: int
    requested_train_fraction: float
    actual_train_fraction: float | None


def split_object_features(
    result: ComputationResult[ObjectFeatureTable],
    spec: ObjectFeatureSplitSpec = ObjectFeatureSplitSpec(),
) -> ComputationResult[ObjectFeaturePartition]:
    """Partition whole executions, optionally joining shared-event/object groups.

    One connected component cannot provide an independent train/test experiment;
    it remains entirely in train and the limitation is explicit.
    """
    if not isinstance(spec, ObjectFeatureSplitSpec):
        raise TypeError("invalid split spec")
    table = _table(result)
    parent = {r.row_id: r.row_id for r in table.rows}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    owners = {}
    for row in table.rows:
        keys = [("execution", row.execution_id)] if row.execution_id is not None else []
        if spec.group_shared_entities:
            keys += [("event", e) for e in row.event_members] + [
                ("object", o) for o in row.object_members
            ]
        for key in keys:
            if key in owners:
                union(row.row_id, owners[key])
            else:
                owners[key] = row.row_id
    # Boundary objects still create dependence, even if omitted from individual
    # prefix cells. Use every extracted graph's complete selected object scope.
    if spec.group_shared_entities:
        for graph in table.graphs:
            present = [r for r in graph.row_ids if r in parent]
            if not present:
                continue
            for key in [("event", e) for e in graph.event_ids] + [
                ("object", o) for o in graph.object_ids
            ]:
                if key in owners:
                    union(present[0], owners[key])
                else:
                    owners[key] = present[0]
    components = defaultdict(list)
    for row in table.rows:
        components[find(row.row_id)].append(row)
    groups = sorted(
        components.values(),
        key=lambda g: sha256(
            (spec.seed + "|" + min(r.row_id for r in g)).encode()
        ).hexdigest(),
    )
    count = len(groups)
    train_count = (
        max(1, min(count - 1, int(count * spec.train_fraction))) if count > 1 else count
    )
    train = [r for group in groups[:train_count] for r in group]
    test = [r for group in groups[train_count:] for r in group]

    def members(rows, field):
        return {v for row in rows for v in getattr(row, field)}

    shared_events = members(train, "event_members") & members(test, "event_members")
    shared_objects = members(train, "object_members") & members(test, "object_members")
    # Expand leakage reports to execution graph scopes, not just target rows.
    train_exec = {r.execution_id for r in train if r.execution_id is not None}
    test_exec = {r.execution_id for r in test if r.execution_id is not None}
    for field, shared in (("event_ids", shared_events), ("object_ids", shared_objects)):
        left = {
            v
            for g in table.graphs
            if g.execution_id in train_exec
            for v in getattr(g, field)
        }
        right = {
            v
            for g in table.graphs
            if g.execution_id in test_exec
            for v in getattr(g, field)
        }
        shared.update(left & right)
    issues = []
    if count < 2:
        issues.append(
            ComputeIssue(
                "insufficient_independent_groups",
                "Fewer than two independent groups; no independent test partition.",
            )
        )
    if shared_events or shared_objects:
        issues.append(
            ComputeIssue(
                "partition_entity_leakage",
                "Train and test share reported events or objects.",
            )
        )
    payload = ObjectFeaturePartition(
        tuple(sorted(r.row_id for r in train)),
        tuple(sorted(r.row_id for r in test)),
        tuple(sorted(train_exec)),
        tuple(sorted(test_exec)),
        tuple(sorted(shared_events)),
        tuple(sorted(shared_objects)),
        count,
        spec.train_fraction,
        len(train) / len(table.rows) if table.rows else None,
    )
    return _derived_result(
        "pix.object_centric.feature_split",
        result.source_digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        tuple(issues),
        parent_computation_ids=(result.computation_id,),
    )


@dataclass(frozen=True, slots=True)
class ObjectFeatureFitSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_fit.spec"
    train_row_ids: tuple[str, ...]
    categorical_encoding: str = "one_hot"

    def __post_init__(self):
        if (
            not isinstance(self.train_row_ids, tuple)
            or not self.train_row_ids
            or not all(isinstance(v, str) for v in self.train_row_ids)
        ):
            raise ValueError("nonempty training row ID tuple required")
        if len(set(self.train_row_ids)) != len(self.train_row_ids):
            raise ValueError("duplicate training row ID")
        if self.categorical_encoding not in ("one_hot", "ordinal"):
            raise ValueError("categorical encoding must be one_hot or ordinal")
        object.__setattr__(self, "train_row_ids", tuple(sorted(self.train_row_ids)))


@dataclass(frozen=True, slots=True)
class ObjectFeatureColumnModel:
    feature_index: int
    mode: str
    observed_train_count: int
    mean: float | None
    scale: float | None
    categories: tuple[str, ...]
    category_encoding: str = "one_hot"


@dataclass(frozen=True, slots=True)
class ObjectFeatureEncoder:
    features: tuple[ObjectFeature, ...]
    granularity: str
    definition_id: str
    train_row_ids: tuple[str, ...]
    columns: tuple[ObjectFeatureColumnModel, ...]


def _category(cell):
    if cell.kind == "text":
        return "text:" + cell.text
    if cell.kind == "boolean":
        return "boolean:true" if cell.boolean else "boolean:false"
    return None


def fit_object_feature_encoder(
    result: ComputationResult[ObjectFeatureTable], spec: ObjectFeatureFitSpec
) -> ComputationResult[ObjectFeatureEncoder]:
    """Fit numeric population standardization/category vocabularies on train only.

    Labels, IDs, datetime and set-valued cells are never accidentally encoded as
    inputs. Unsupported or mixed columns carry unavailable coverage explicitly.
    """
    if not isinstance(spec, ObjectFeatureFitSpec):
        raise TypeError("invalid fit spec")
    table = _table(result)
    rows = {r.row_id: r for r in table.rows}
    if set(spec.train_row_ids) - set(rows):
        return _derived_result(
            "pix.object_centric.feature_fit",
            result.source_digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "unknown_training_row",
                    "Training IDs must belong to source feature table.",
                ),
            ),
            parent_computation_ids=(result.computation_id,),
        )
    columns, issues = [], []
    for index in range(len(table.features)):
        cells = [rows[r].cells[index] for r in spec.train_row_ids]
        if any(c.role == "target" for c in cells):
            columns.append(
                ObjectFeatureColumnModel(index, "target_excluded", 0, None, None, ())
            )
            continue
        known = [c for c in cells if c.kind != "unknown"]
        if known and all(_number(c) is not None for c in known):
            try:
                values = [float(_number(c)) for c in known]
                mean = sum(values) / len(values)
                scale = sqrt(sum((v - mean) ** 2 for v in values) / len(values))
                if not isfinite(mean) or not isfinite(scale):
                    raise OverflowError
                columns.append(
                    ObjectFeatureColumnModel(
                        index, "numeric", len(known), mean, scale, ()
                    )
                )
                continue
            except OverflowError:
                pass
        elif known and all(_category(c) is not None for c in known):
            columns.append(
                ObjectFeatureColumnModel(
                    index,
                    "categorical",
                    len(known),
                    None,
                    None,
                    tuple(sorted({_category(c) for c in known})),
                    spec.categorical_encoding,
                )
            )
            continue
        columns.append(
            ObjectFeatureColumnModel(index, "unavailable", 0, None, None, ())
        )
        issues.append(
            ComputeIssue(
                "encoder_column_unavailable",
                "No supported homogeneous training observations.",
                (str(index),),
            )
        )
    payload = ObjectFeatureEncoder(
        table.features,
        table.granularity,
        table.definition_id,
        spec.train_row_ids,
        tuple(columns),
    )
    return _derived_result(
        "pix.object_centric.feature_fit",
        result.source_digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        tuple(issues),
        parent_computation_ids=(result.computation_id,),
    )


@dataclass(frozen=True, slots=True)
class ObjectFeatureTransformSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_transform.spec"
    row_ids: tuple[str, ...] | None = None

    def __post_init__(self):
        if self.row_ids is not None and (
            not isinstance(self.row_ids, tuple)
            or not all(isinstance(v, str) for v in self.row_ids)
        ):
            raise TypeError("row_ids must be tuple of strings or None")
        if self.row_ids is not None and len(set(self.row_ids)) != len(self.row_ids):
            raise ValueError("duplicate row ID")


@dataclass(frozen=True, slots=True)
class ObjectFeatureEncodedRow:
    row_id: str
    values: tuple[float | None, ...]
    reasons: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class ObjectFeatureEncodedTable:
    rows: tuple[ObjectFeatureEncodedRow, ...]
    train_row_ids: tuple[str, ...]
    unknown_value_count: int
    columns: tuple[tuple[int, str | None], ...]


def transform_object_features(
    result: ComputationResult[ObjectFeatureTable],
    fitted: ComputationResult[ObjectFeatureEncoder],
    spec: ObjectFeatureTransformSpec = ObjectFeatureTransformSpec(),
) -> ComputationResult[ObjectFeatureEncodedTable]:
    """Apply frozen train statistics; unseen categories and missing data stay None."""
    if not isinstance(spec, ObjectFeatureTransformSpec):
        raise TypeError("invalid transform spec")
    table = _table(result)
    if (
        not isinstance(fitted, ComputationResult)
        or fitted.operator_id != "pix.object_centric.feature_fit"
        or not isinstance(fitted.value, ObjectFeatureEncoder)
    ):
        raise TypeError("expected fitted feature encoder result")
    parents = (result.computation_id, fitted.computation_id)
    if (
        fitted.value.features != table.features
        or fitted.value.granularity != table.granularity
        or fitted.value.definition_id != table.definition_id
    ):
        return _derived_result(
            "pix.object_centric.feature_transform",
            result.source_digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "encoder_feature_mismatch",
                    "Fitted feature definitions differ from input.",
                ),
            ),
            parent_computation_ids=parents,
        )
    ids = {r.row_id for r in table.rows}
    if spec.row_ids is not None and set(spec.row_ids) - ids:
        return _derived_result(
            "pix.object_centric.feature_transform",
            result.source_digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "unknown_transform_row",
                    "Selected rows must belong to source feature table.",
                ),
            ),
            parent_computation_ids=parents,
        )
    encoded, unknown = [], 0
    output_columns = tuple(
        (model.feature_index, category)
        for model in fitted.value.columns
        for category in (
            model.categories
            if model.mode == "categorical" and model.category_encoding == "one_hot"
            else (None,)
        )
    )
    for row in table.rows:
        if spec.row_ids is not None and row.row_id not in spec.row_ids:
            continue
        values, reasons = [], []
        for cell, model in zip(row.cells, fitted.value.columns):
            value, reason = None, None
            if cell.role == "target" or model.mode == "target_excluded":
                reason = "target_excluded"
            elif cell.kind == "unknown":
                reason = cell.reason or "missing_observation"
            elif model.mode == "numeric":
                number = _number(cell)
                if number is None:
                    reason = "incompatible_value_type"
                else:
                    try:
                        value = (float(number) - model.mean) / (
                            model.scale if model.scale else 1.0
                        )
                        if not isfinite(value):
                            value, reason = None, "non_finite_transformation"
                    except OverflowError:
                        reason = "non_finite_transformation"
            elif model.mode == "categorical":
                category = _category(cell)
                if category in model.categories:
                    value = float(model.categories.index(category))
                else:
                    reason = "unseen_category"
            else:
                reason = "encoder_column_unavailable"
            if model.mode == "categorical" and model.category_encoding == "one_hot":
                if value is None:
                    width = len(model.categories)
                    values.extend([None] * width)
                    reasons.extend([reason] * width)
                    if reason != "target_excluded":
                        unknown += width
                else:
                    values.extend(
                        float(_category(cell) == category)
                        for category in model.categories
                    )
                    reasons.extend([None] * len(model.categories))
                continue
            if value is None and reason != "target_excluded":
                unknown += 1
            values.append(value)
            reasons.append(reason)
        encoded.append(
            ObjectFeatureEncodedRow(row.row_id, tuple(values), tuple(reasons))
        )
    issues = (
        (
            ComputeIssue(
                "unencoded_feature_values",
                f"{unknown} values remain unknown; no imputation.",
            ),
        )
        if unknown
        else ()
    )
    payload = ObjectFeatureEncodedTable(
        tuple(encoded), fitted.value.train_row_ids, unknown, output_columns
    )
    return _derived_result(
        "pix.object_centric.feature_transform",
        result.source_digest,
        spec,
        ComputeStatus.PARTIAL if unknown else ComputeStatus.COMPUTED,
        payload,
        issues,
        parent_computation_ids=parents,
    )


RESULT_SCHEMAS = {
    OBJECT_FEATURES_OPERATOR_ID: (
        "object-features",
        ObjectFeatureSpec,
        ObjectFeatureTable,
    ),
    "pix.object_centric.feature_encoding": (
        "object-feature-encoding",
        ObjectFeatureEncodingSpec,
        ObjectFeatureEncoding,
    ),
    "pix.object_centric.feature_split": (
        "object-feature-split",
        ObjectFeatureSplitSpec,
        ObjectFeaturePartition,
    ),
    "pix.object_centric.feature_fit": (
        "object-feature-fit",
        ObjectFeatureFitSpec,
        ObjectFeatureEncoder,
    ),
    "pix.object_centric.feature_transform": (
        "object-feature-transform",
        ObjectFeatureTransformSpec,
        ObjectFeatureEncodedTable,
    ),
    "pix.object_centric.feature_aggregation": (
        "object-feature-aggregation",
        ObjectFeatureAggregationSpec,
        ObjectFeatureTable,
    ),
}

__all__ = (
    "ObjectFeature",
    "ObjectFeatureSpec",
    "ObjectFeatureCell",
    "ObjectFeatureRow",
    "ObjectFeatureGraph",
    "ObjectFeatureTable",
    "ObjectFeatureEncodingSpec",
    "ObjectFeatureGroup",
    "ObjectFeatureEncoding",
    "ObjectFeatureSplitSpec",
    "ObjectFeaturePartition",
    "ObjectFeatureFitSpec",
    "ObjectFeatureColumnModel",
    "ObjectFeatureEncoder",
    "ObjectFeatureTransformSpec",
    "ObjectFeatureEncodedRow",
    "ObjectFeatureEncodedTable",
    "extract_object_features",
    "encode_object_features",
    "split_object_features",
    "fit_object_feature_encoder",
    "transform_object_features",
    "EVENT_FEATURES",
    "EXECUTION_FEATURES",
    "OBJECT_FEATURES",
    "PREFIX_FEATURES",
    "OBJECT_FEATURES_OPERATOR_ID",
    "ObjectFeatureAggregationSpec",
    "aggregate_object_features",
)
