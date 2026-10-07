"""Cutoff-safe case learning datasets, censoring and indivisible case splits.

An observation includes source-order events at or before its UTC instant. A
recorded last event is never treated as a completion fact. Explicit follow-up
records supply the independently known observation endpoint and completion.
Chronological splitting uses whole recorded case intervals, merging overlap and
ties; callers must include target availability in ``case_available_until`` when
labels become available after the last event. Fractions allocate indivisible
blocks, not individual cases. These profiles do not train a predictor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
from math import floor
from typing import ClassVar, Literal

from pix.case_centric.features import (
    CaseSplit,
    CaseSplitSpec,
    FeatureColumn,
    FeatureMatrix,
    FeatureModel,
    FeatureSpec,
    PrefixInput,
    _category,
    _instant_microseconds,
    _integer,
    _project,
    _result_for,
    _seconds,
    _source,
    _strings,
    _text,
    fit_features,
    transform_features,
)
from pix.compute._common import _result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseEvent, CaseLog, find_attribute


def _aware(value: object, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError(f"{name} must be a timezone-aware datetime")


def _typed_tuple(value: object, kind: type, name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(x, kind) for x in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _event_time(log: CaseLog, event: CaseEvent, key: str) -> datetime:
    # Resolve only the clock key. Unobserved activity/feature attributes must not
    # be inspected, including malformed attributes on otherwise timed events.
    value = find_attribute(event.attributes, key)
    if value is None:
        value = find_attribute(
            tuple(a for g in log.globals if g.scope == "event" for a in g.attributes),
            key,
        )
    if value is None or value.type != "date":
        raise ValueError(f"event {event.id!r} requires an aware {key!r}")
    _aware(value.value, f"event {event.id!r} timestamp")
    return value.value


@dataclass(frozen=True, slots=True)
class ObservationSpec:
    observed_at: datetime
    label_horizon_seconds: int | None = None
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_observed_events: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _aware(self.observed_at, "observed_at")
        if self.label_horizon_seconds is not None:
            _integer(self.label_horizon_seconds, "label_horizon_seconds")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        _integer(self.max_observed_events, "max_observed_events", 1)


@dataclass(frozen=True, slots=True)
class CaseFollowUp:
    """No completion observed through ``observed_until`` means right censoring."""

    case_id: str
    observed_until: datetime
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _aware(self.observed_until, "observed_until")
        if self.completed_at is not None:
            _aware(self.completed_at, "completed_at")
            if _instant_microseconds(self.completed_at) > _instant_microseconds(
                self.observed_until
            ):
                raise ValueError("completion cannot be after the follow-up endpoint")


@dataclass(frozen=True, slots=True)
class ObservationRequest:
    parameters: ObservationSpec
    follow_up: tuple[CaseFollowUp, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, ObservationSpec):
            raise TypeError("parameters must be ObservationSpec")
        _typed_tuple(self.follow_up, CaseFollowUp, "follow_up")
        if len({x.case_id for x in self.follow_up}) != len(self.follow_up):
            raise ValueError("follow-up case IDs must be unique")
        object.__setattr__(
            self, "follow_up", tuple(sorted(self.follow_up, key=lambda x: x.case_id))
        )


@dataclass(frozen=True, slots=True)
class ObservationSample:
    prefix: PrefixInput
    observed_at: datetime
    elapsed_at_observation_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.prefix, PrefixInput) or not self.prefix.length:
            raise ValueError("observation sample requires a nonempty PrefixInput")
        _aware(self.observed_at, "observed_at")
        value = self.elapsed_at_observation_seconds
        if type(value) is not float or not 0 <= value < float("inf"):
            raise ValueError(
                "elapsed observation time must be a finite nonnegative float"
            )


@dataclass(frozen=True, slots=True)
class CensoredPredictionTarget:
    case_id: str
    next_status: Literal["observed", "terminal", "censored", "horizon"]
    next_activity: str | None
    next_time_seconds: float | None
    completion_status: Literal["completed", "censored", "horizon_survived"]
    remaining_time_seconds: float | None
    is_complete_at_observation: bool
    follow_up_seconds: float

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        if self.next_status not in ("observed", "terminal", "censored", "horizon"):
            raise ValueError("invalid next-event status")
        if self.completion_status not in ("completed", "censored", "horizon_survived"):
            raise ValueError("invalid completion status")
        if self.next_activity is not None:
            _text(self.next_activity, "next_activity")
        if (self.next_status == "observed") != (self.next_activity is not None):
            raise ValueError("only an observed next event has an activity")
        if (self.next_status == "observed") != (self.next_time_seconds is not None):
            raise ValueError("only an observed next event has a time target")
        if self.next_status == "observed" and self.next_time_seconds <= 0:
            raise ValueError(
                "an unobserved next event must occur strictly after the inclusive cutoff"
            )
        if (self.completion_status == "completed") != (
            self.remaining_time_seconds is not None
        ):
            raise ValueError("only observed completion has a remaining-time target")
        if self.next_status == "terminal" and self.completion_status != "completed":
            raise ValueError("terminal requires observed completion")
        if self.next_status == "censored" and self.completion_status != "censored":
            raise ValueError("censored next-event status requires censored follow-up")
        if (
            self.next_status == "horizon"
            and self.completion_status != "horizon_survived"
        ):
            raise ValueError(
                "horizon next-event status requires survival through the horizon"
            )
        if type(self.is_complete_at_observation) is not bool:
            raise TypeError("is_complete_at_observation must be bool")
        if self.is_complete_at_observation and (
            self.next_status != "terminal" or self.remaining_time_seconds != 0.0
        ):
            raise ValueError(
                "an already completed observation must be terminal with zero remaining time"
            )
        for name in (
            "next_time_seconds",
            "remaining_time_seconds",
            "follow_up_seconds",
        ):
            value = getattr(self, name)
            if value is None:
                if name == "follow_up_seconds":
                    raise ValueError("follow_up_seconds cannot be missing")
            elif type(value) is not float or not 0 <= value < float("inf"):
                raise ValueError(f"{name} must be a finite nonnegative float or None")
        if any(
            value is not None and value > self.follow_up_seconds
            for value in (self.next_time_seconds, self.remaining_time_seconds)
        ):
            raise ValueError("a target cannot occur beyond available follow-up")
        if (
            self.next_time_seconds is not None
            and self.remaining_time_seconds is not None
            and self.next_time_seconds > self.remaining_time_seconds
        ):
            raise ValueError("the next event cannot occur after explicit completion")
        if (
            self.completion_status == "completed"
            and (self.remaining_time_seconds == 0.0) != self.is_complete_at_observation
        ):
            raise ValueError(
                "zero remaining time must identify completion by the observation cutoff"
            )


@dataclass(frozen=True, slots=True)
class ObservationDataset:
    samples: tuple[ObservationSample, ...]
    targets: tuple[CensoredPredictionTarget, ...]
    excluded_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _typed_tuple(self.samples, ObservationSample, "samples")
        _typed_tuple(self.targets, CensoredPredictionTarget, "targets")
        _strings(self.excluded_case_ids, "excluded_case_ids")
        ids = tuple(x.prefix.case_id for x in self.samples)
        if len(ids) != len(set(ids)) or ids != tuple(x.case_id for x in self.targets):
            raise ValueError(
                "samples and targets require matching unique case identities"
            )
        if set(ids) & set(self.excluded_case_ids):
            raise ValueError("included and excluded cases must be disjoint")


def _window_events(log: CaseLog, events: tuple[CaseEvent, ...], key: str, end_us: int):
    selected, times = [], []
    passed = False
    previous = None
    for event in events:
        time = _event_time(log, event, key)
        instant = _instant_microseconds(time)
        if instant > end_us:
            passed = True
            continue
        if passed or (previous is not None and instant < previous):
            raise ValueError(
                "observed timestamps must form a nondecreasing source-order prefix"
            )
        selected.append(event)
        times.append(time)
        previous = instant
    return tuple(selected), tuple(times)


def _cutoff_log(log: CaseLog, spec: ObservationSpec):
    observed, excluded, times = [], [], {}
    total = 0
    cutoff = _instant_microseconds(spec.observed_at)
    for trace in log.traces:
        events, observed_times = _window_events(
            log, trace.events, spec.trace_spec.timestamp_key, cutoff
        )
        total += len(events)
        if total > spec.max_observed_events:
            raise OverflowError(
                "observed prefix exceeds max_observed_events; no truncated dataset is returned"
            )
        if events:
            observed.append(replace(trace, events=events, attributes=()))
            times[trace.id] = observed_times
        else:
            excluded.append(trace.id)
    # Trace/log attributes have no availability time and are not online inputs.
    # Discard the original file digest as it includes the unobserved suffix.
    return (
        replace(
            log,
            traces=tuple(observed),
            attributes=(),
            metadata=(),
            source=None,
            globals=tuple(g for g in log.globals if g.scope == "event"),
        ),
        tuple(sorted(excluded)),
        times,
    )


def _failure(operator, source, request, error, *, parents=()):
    limited = isinstance(error, OverflowError)
    return _result(
        operator,
        None,
        request,
        ComputeStatus.UNAVAILABLE if limited else ComputeStatus.INVALID_INPUT,
        None,
        (
            ComputeIssue(
                "dataset_materialization_limit" if limited else "invalid_dataset_data",
                str(error),
            ),
        ),
        source_digest=source,
        parent_computation_ids=parents,
    )


def observation_dataset(
    log: CaseLog,
    spec: ObservationSpec,
    *,
    follow_up: tuple[CaseFollowUp, ...],
) -> ComputationResult[ObservationDataset]:
    """One prefix per case seen by cutoff, with separate follow-up targets.

    All times are compared as UTC instants, boundaries are inclusive, and target
    durations begin at the observation cutoff (not its last event). Censoring is
    a valid target status, not a computation failure. Events beyond the label
    horizon do not supply target activities. Clockless events cannot be safely
    classified as past/future and make the input invalid.
    """
    source = _source(log)
    request = ObservationRequest(spec, follow_up)
    operator = "pix.case_centric.observation_dataset"
    try:
        snapshot, excluded, times = _cutoff_log(log, spec)
        activity = _project(snapshot, spec.trace_spec)
        by_case = {x.case_id: x for x in request.follow_up}
        traces = {x.id: x for x in log.traces}
        unknown = set(by_case) - set(traces)
        if unknown:
            raise ValueError(f"unknown follow-up case IDs: {sorted(unknown)!r}")
        cutoff = _instant_microseconds(spec.observed_at)
        horizon = (
            None
            if spec.label_horizon_seconds is None
            else cutoff + spec.label_horizon_seconds * 1000000
        )
        samples, targets = [], []
        for trace in snapshot.traces:
            state = by_case.get(trace.id)
            if state is None:
                raise ValueError(f"missing explicit follow-up for case {trace.id!r}")
            available = _instant_microseconds(state.observed_until)
            if available < cutoff:
                raise ValueError("follow-up cannot precede the observation cutoff")
            end = min(available, horizon) if horizon is not None else available
            label_events, label_times = _window_events(
                log, traces[trace.id].events, spec.trace_spec.timestamp_key, end
            )
            completion = (
                None
                if state.completed_at is None
                else _instant_microseconds(state.completed_at)
            )
            # A supplied completion fact conflicts with any event recorded up to
            # the explicit follow-up endpoint, even outside the label horizon.
            if completion is not None:
                known_events, known_times = _window_events(
                    log,
                    traces[trace.id].events,
                    spec.trace_spec.timestamp_key,
                    available,
                )
                if known_events and _instant_microseconds(known_times[-1]) > completion:
                    raise ValueError(
                        "an observed event occurs after explicit case completion"
                    )
            length = len(trace.events)
            prefix = PrefixInput(
                trace.id,
                length,
                tuple(x.id for x in trace.events),
                activity[trace.id],
                _seconds(times[trace.id][0], times[trace.id][-1]),
            )
            samples.append(
                ObservationSample(
                    prefix,
                    spec.observed_at,
                    _seconds(times[trace.id][0], spec.observed_at),
                )
            )
            completed = completion is not None and completion <= end
            completion_status = (
                "completed"
                if completed
                else "horizon_survived"
                if horizon is not None and available >= horizon
                else "censored"
            )
            next_activity = next_time = None
            if len(label_events) > length:
                next_event = label_events[length]
                target_log = replace(
                    snapshot, traces=(replace(trace, events=(next_event,)),)
                )
                next_activity = _project(target_log, spec.trace_spec)[trace.id][0]
                next_time = _seconds(spec.observed_at, label_times[length])
                next_status = "observed"
            else:
                next_status = (
                    "terminal"
                    if completed
                    else "horizon"
                    if completion_status == "horizon_survived"
                    else "censored"
                )
            targets.append(
                CensoredPredictionTarget(
                    trace.id,
                    next_status,
                    next_activity,
                    next_time,
                    completion_status,
                    max(0.0, (completion - cutoff) / 1000000) if completed else None,
                    completion is not None and completion <= cutoff,
                    (end - cutoff) / 1000000,
                )
            )
    except (ValueError, OverflowError) as error:
        return _failure(operator, source, request, error)
    return _result_for(
        operator,
        source,
        request,
        ObservationDataset(tuple(samples), tuple(targets), excluded),
    )


@dataclass(frozen=True, slots=True)
class CaseAvailability:
    case_id: str
    available_until: datetime

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _aware(self.available_until, "available_until")


@dataclass(frozen=True, slots=True)
class LeakageSplitSpec:
    """Fractions count atomic groups; group size may make case ratios differ.

    Requested nonzero partitions each receive at least one block by default.
    Remaining boundaries use floor(n * fraction), constrained by that minimum.
    Chronology is strict: the latest training availability is earlier than the
    earliest later-partition event. Equal-time and overlapping groups coalesce.
    """

    strategy: Literal["grouped_hash", "chronological"] = "grouped_hash"
    train_fraction: float = 0.8
    validation_fraction: float = 0.0
    shared_case_groups: tuple[tuple[str, ...], ...] = ()
    case_available_until: tuple[CaseAvailability, ...] = ()
    timestamp_key: str = "time:timestamp"
    seed: str = "pix-leakage-split-v1"
    require_nonempty: bool = True
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.strategy not in ("grouped_hash", "chronological"):
            raise ValueError("strategy must be grouped_hash or chronological")
        CaseSplitSpec(self.train_fraction, self.validation_fraction, self.seed)
        _text(self.timestamp_key, "timestamp_key")
        if type(self.require_nonempty) is not bool:
            raise TypeError("require_nonempty must be bool")
        _typed_tuple(self.shared_case_groups, tuple, "shared_case_groups")
        for group in self.shared_case_groups:
            _strings(group, "shared case group")
            if not group:
                raise ValueError("shared case groups cannot be empty")
        object.__setattr__(
            self,
            "shared_case_groups",
            tuple(sorted(set(tuple(sorted(g)) for g in self.shared_case_groups))),
        )
        _typed_tuple(
            self.case_available_until, CaseAvailability, "case_available_until"
        )
        if len({x.case_id for x in self.case_available_until}) != len(
            self.case_available_until
        ):
            raise ValueError("case availability identities must be unique")
        if self.strategy != "chronological" and self.case_available_until:
            raise ValueError(
                "case availability applies only to chronological splitting"
            )
        object.__setattr__(
            self,
            "case_available_until",
            tuple(sorted(self.case_available_until, key=lambda x: x.case_id)),
        )


@dataclass(frozen=True, slots=True)
class LeakageSafeSplit:
    partitions: CaseSplit
    atomic_case_groups: tuple[tuple[str, ...], ...]
    partition_group_counts: tuple[int, int, int]

    def __post_init__(self) -> None:
        if not isinstance(self.partitions, CaseSplit):
            raise TypeError("partitions must be CaseSplit")
        _typed_tuple(self.atomic_case_groups, tuple, "atomic_case_groups")
        for group in self.atomic_case_groups:
            _strings(group, "atomic case group")
            if not group:
                raise ValueError("atomic groups cannot be empty")
        flat = tuple(case for group in self.atomic_case_groups for case in group)
        _strings(flat, "grouped case IDs")
        if (
            not isinstance(self.partition_group_counts, tuple)
            or len(self.partition_group_counts) != 3
        ):
            raise ValueError("three partition group counts are required")
        for count in self.partition_group_counts:
            _integer(count, "partition group count")
        if sum(self.partition_group_counts) != len(self.atomic_case_groups):
            raise ValueError("partition group counts must conserve groups")
        offset = 0
        for count, ids in zip(
            self.partition_group_counts,
            (
                self.partitions.train_case_ids,
                self.partitions.validation_case_ids,
                self.partitions.test_case_ids,
            ),
        ):
            expected = {
                case
                for group in self.atomic_case_groups[offset : offset + count]
                for case in group
            }
            if expected != set(ids):
                raise ValueError(
                    "partition case IDs disagree with their indivisible groups"
                )
            offset += count


def leakage_safe_split(
    log: CaseLog, spec: LeakageSplitSpec = LeakageSplitSpec()
) -> ComputationResult[LeakageSafeSplit]:
    """Split transitive shared-case groups, optionally by nonoverlapping time.

    ``UNAVAILABLE`` means the requested nonempty partitions cannot all exist
    without splitting an indivisible block. No approximate unsafe split is
    returned. Grouped hash is deterministic for a fixed population and seed.
    Chronological guarantees concern supplied timestamps and availability facts,
    not unrecorded external dependencies or later unknown labels.
    """
    source = _source(log)
    if not isinstance(spec, LeakageSplitSpec):
        raise TypeError("spec must be LeakageSplitSpec")
    operator = "pix.case_centric.leakage_safe_split"
    try:
        parent = {trace.id: trace.id for trace in log.traces}

        def root(case):
            while parent[case] != case:
                parent[case] = parent[parent[case]]
                case = parent[case]
            return case

        for group in spec.shared_case_groups:
            if set(group) - set(parent):
                raise ValueError("shared groups reference unknown case IDs")
            for case in group[1:]:
                a, b = root(group[0]), root(case)
                parent[max(a, b)] = min(a, b)
        groups = {}
        for case in parent:
            groups.setdefault(root(case), []).append(case)
        blocks = [tuple(sorted(group)) for group in groups.values()]
        if spec.strategy == "grouped_hash":

            def rank(group):
                encoded = json.dumps(
                    (spec.seed, group), ensure_ascii=False, separators=(",", ":")
                ).encode()
                return sha256(encoded).digest(), group

            blocks.sort(key=rank)
        else:
            availability = {
                x.case_id: x.available_until for x in spec.case_available_until
            }
            if set(availability) - set(parent):
                raise ValueError("availability references unknown case IDs")
            intervals = {}
            for trace in log.traces:
                if not trace.events:
                    raise ValueError("empty cases have no chronological interval")
                times = tuple(
                    _instant_microseconds(_event_time(log, event, spec.timestamp_key))
                    for event in trace.events
                )
                start, end = min(times), max(times)
                if trace.id in availability:
                    known_until = _instant_microseconds(availability[trace.id])
                    if known_until < end:
                        raise ValueError(
                            "case availability cannot precede its last recorded event"
                        )
                    end = known_until
                intervals[trace.id] = start, end
            timed = sorted(
                (
                    min(intervals[x][0] for x in group),
                    max(intervals[x][1] for x in group),
                    group,
                )
                for group in blocks
            )
            merged = []
            for start, end, group in timed:
                if merged and start <= merged[-1][1]:
                    old_start, old_end, old_group = merged[-1]
                    merged[-1] = (
                        old_start,
                        max(end, old_end),
                        tuple(sorted(old_group + group)),
                    )
                else:
                    merged.append((start, end, group))
            blocks = [group for _, _, group in merged]
        fractions = (
            Fraction(str(spec.train_fraction)),
            Fraction(str(spec.validation_fraction)),
        )
        fractions += (1 - sum(fractions),)
        minimum = tuple(int(value > 0 and spec.require_nonempty) for value in fractions)
        if len(blocks) < sum(minimum):
            return _result(
                operator,
                None,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "indivisible_split",
                        "Too few independent time/shared-object blocks for the requested nonempty partitions",
                    ),
                ),
                source_digest=source,
            )
        train = min(
            max(floor(len(blocks) * fractions[0]), minimum[0]),
            len(blocks) - sum(minimum[1:]),
        )
        validation = min(
            max(floor(len(blocks) * fractions[1]), minimum[1]),
            len(blocks) - train - minimum[2],
        )
        if fractions[2] == 0:
            if fractions[1] == 0:
                train = len(blocks)
            validation = len(blocks) - train
        counts = train, validation, len(blocks) - train - validation
        cuts = (0, train, train + validation, len(blocks))
        ids = tuple(
            tuple(sorted(case for group in blocks[begin:end] for case in group))
            for begin, end in zip(cuts, cuts[1:])
        )
        value = LeakageSafeSplit(CaseSplit(*ids), tuple(blocks), counts)
    except ValueError as error:
        return _failure(operator, source, spec, error)
    return _result_for(operator, source, spec, value)


@dataclass(frozen=True, slots=True)
class ObservationEncoderSpec:
    observation: ObservationSpec
    features: FeatureSpec = FeatureSpec()
    numeric_units: tuple[tuple[str, str], ...] = ()
    max_feature_cells: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.max_feature_cells, "max_feature_cells", 1)
        if not isinstance(self.observation, ObservationSpec) or not isinstance(
            self.features, FeatureSpec
        ):
            raise TypeError("encoder requires ObservationSpec and FeatureSpec")
        if self.features.trace_spec != self.observation.trace_spec:
            raise ValueError(
                "encoder and observation must use the same trace projection"
            )
        if self.features.level == "trace" and (
            self.features.numeric_attributes or self.features.categorical_attributes
        ):
            raise ValueError(
                "trace attribute availability is unknown; choose event-level attributes"
            )
        _typed_tuple(self.numeric_units, tuple, "numeric_units")
        for pair in self.numeric_units:
            if len(pair) != 2:
                raise ValueError("numeric_units entries require attribute key and unit")
            _text(pair[0], "numeric attribute key")
            _text(pair[1], "numeric attribute unit")
            if pair[0] not in self.features.numeric_attributes:
                raise ValueError(
                    "numeric unit key must be an encoded numeric attribute"
                )
        if len({pair[0] for pair in self.numeric_units}) != len(self.numeric_units):
            raise ValueError("numeric unit keys must be unique")
        object.__setattr__(self, "numeric_units", tuple(sorted(self.numeric_units)))


@dataclass(frozen=True, slots=True)
class ObservationEncoderRequest:
    parameters: ObservationEncoderSpec
    training_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, ObservationEncoderSpec):
            raise TypeError("parameters must be ObservationEncoderSpec")
        _strings(self.training_case_ids, "training_case_ids")
        object.__setattr__(
            self, "training_case_ids", tuple(sorted(self.training_case_ids))
        )


@dataclass(frozen=True, slots=True)
class ObservationEncoder:
    parameters: ObservationEncoderSpec
    fitted_model: FeatureModel

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, ObservationEncoderSpec) or not isinstance(
            self.fitted_model, FeatureModel
        ):
            raise TypeError("encoder requires its typed parameters and FeatureModel")
        if self.fitted_model.parameters != self.parameters.features:
            raise ValueError(
                "fitted feature parameters disagree with the observation encoder"
            )


@dataclass(frozen=True, slots=True)
class ObservationTransformRequest:
    encoder: ObservationEncoder

    def __post_init__(self) -> None:
        if not isinstance(self.encoder, ObservationEncoder):
            raise TypeError("encoder must be ObservationEncoder")


@dataclass(frozen=True, slots=True)
class MaskedObservationMatrix:
    matrix: FeatureMatrix
    known_masks: tuple[tuple[bool, ...], ...]
    excluded_case_ids: tuple[str, ...]
    column_units: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.matrix, FeatureMatrix):
            raise TypeError("matrix must be FeatureMatrix")
        if not isinstance(self.column_units, tuple) or len(self.column_units) != len(
            self.matrix.columns
        ):
            raise ValueError("one unit declaration is required per feature column")
        for unit in self.column_units:
            _text(unit, "feature unit")
        _typed_tuple(self.known_masks, tuple, "known_masks")
        if len(self.known_masks) != len(self.matrix.rows):
            raise ValueError("one known mask is required per row")
        for row, mask in zip(self.matrix.rows, self.known_masks):
            if len(mask) != len(row.values) or any(
                type(value) is not bool for value in mask
            ):
                raise ValueError("known masks must contain one bool per column")
            if mask != tuple(value is not None for value in row.values):
                raise ValueError(
                    "unknown values must remain None, never be imputed as zero"
                )
        _strings(self.excluded_case_ids, "excluded_case_ids")
        if set(self.excluded_case_ids) & {row.case_id for row in self.matrix.rows}:
            raise ValueError("excluded cases cannot have matrix rows")


def fit_observation_encoder(
    log: CaseLog, spec: ObservationEncoderSpec, *, training_case_ids: tuple[str, ...]
) -> ComputationResult[ObservationEncoder]:
    """Fit existing activity/ngram/IDF and event encoders on train cutoffs only.

    Training IDs are mandatory and an explicit empty selection remains empty.
    Held-out clocks and attributes are not read. Original trace attributes and
    source-file metadata cannot enter fitted facts. Event globals are treated as
    caller-declared timeless defaults, not time-varying observed attributes.
    """
    source = _source(log)
    request = ObservationEncoderRequest(spec, training_case_ids)
    operator = "pix.case_centric.fit_observation_encoder"
    try:
        selected = set(request.training_case_ids)
        if selected - {trace.id for trace in log.traces}:
            raise ValueError("training selection references unknown case IDs")
        training = replace(
            log, traces=tuple(trace for trace in log.traces if trace.id in selected)
        )
        snapshot, excluded, _ = _cutoff_log(training, spec.observation)
        if excluded:
            raise ValueError(
                "selected training cases have no events observed at the cutoff"
            )
        fitted = fit_features(
            snapshot, spec.features, training_case_ids=request.training_case_ids
        )
        if fitted.value is None:
            return _result(
                operator,
                None,
                request,
                fitted.status,
                None,
                fitted.issues,
                source_digest=source,
                parent_computation_ids=(fitted.computation_id,),
            )
        value = ObservationEncoder(spec, fitted.value)
    except (ValueError, OverflowError) as error:
        return _failure(operator, source, request, error)
    return _result_for(
        operator, source, request, value, parents=(fitted.computation_id,)
    )


def transform_observations(
    log: CaseLog, encoder: ObservationEncoder
) -> ComputationResult[MaskedObservationMatrix]:
    """Apply fixed training columns; missing and unseen categories retain None.

    Each known category produces a valid one-hot zero/one block. An unknown or
    missing category produces a None block with false masks; numerical None is
    also retained. Unseen activities have their existing out-of-vocabulary count
    and do not add coordinates. Column order and weights cannot change here.
    """
    source = _source(log)
    request = ObservationTransformRequest(encoder)
    operator = "pix.case_centric.transform_observations"
    parents = ()
    try:
        snapshot, excluded, _ = _cutoff_log(log, encoder.parameters.observation)
        row_count = (
            len(snapshot.traces)
            if encoder.parameters.features.level == "trace"
            else sum(len(trace.events) for trace in snapshot.traces)
        )
        if (
            row_count * max(1, len(encoder.fitted_model.columns))
            > encoder.parameters.max_feature_cells
        ):
            raise OverflowError(
                "observation matrix exceeds max_feature_cells; no partial matrix is returned"
            )
        transformed = transform_features(snapshot, encoder.fitted_model)
        parents = (transformed.computation_id,)
        if transformed.value is None:
            return _result(
                operator,
                None,
                request,
                transformed.status,
                None,
                transformed.issues,
                source_digest=source,
                parent_computation_ids=parents,
            )
        matrix = transformed.value
        events = {
            event.id: event for trace in snapshot.traces for event in trace.events
        }
        vocabulary = {
            (column.key, column.terms[0])
            for column in matrix.columns
            if column.kind == "categorical"
        }
        rows = []
        for row in matrix.rows:
            unknown_keys = set(row.missing_attributes)
            if row.event_id is not None:
                for key in encoder.parameters.features.categorical_attributes:
                    category = _category(snapshot.attribute(events[row.event_id], key))
                    if category is None or (key, category) not in vocabulary:
                        unknown_keys.add(key)
            values = tuple(
                None
                if column.kind == "categorical" and column.key in unknown_keys
                else value
                for column, value in zip(matrix.columns, row.values)
            )
            rows.append(replace(row, values=values))
        matrix = replace(matrix, rows=tuple(rows))
        units = dict(encoder.parameters.numeric_units)
        activity_unit = (
            "l2_normalized"
            if encoder.parameters.features.normalize_activity_l2
            else "tfidf_weight"
            if encoder.parameters.features.encoding == "tfidf"
            else "indicator"
            if encoder.parameters.features.encoding == "binary"
            else "occurrences"
        )
        column_units = tuple(
            units.get(column.key, "unspecified")
            if column.kind == "numeric"
            else "indicator"
            if column.kind == "categorical"
            else activity_unit
            for column in matrix.columns
        )
        value = MaskedObservationMatrix(
            matrix,
            tuple(tuple(x is not None for x in row.values) for row in matrix.rows),
            excluded,
            column_units,
        )
    except (ValueError, OverflowError) as error:
        return _failure(operator, source, request, error, parents=parents)
    return _result_for(
        operator, source, request, value, transformed.issues, parents=parents
    )


@dataclass(frozen=True, slots=True)
class CaseSequenceSpec:
    length: int
    padding: Literal["left", "right"] = "right"
    truncation: Literal["error", "oldest"] = "error"
    max_cells: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.length, "length", 1)
        _integer(self.max_cells, "max_cells", 1)
        if self.padding not in ("left", "right"):
            raise ValueError("padding must be left or right")
        if self.truncation not in ("error", "oldest"):
            raise ValueError("truncation must be error or oldest")


@dataclass(frozen=True, slots=True)
class CaseSequenceRequest:
    encoder: ObservationEncoder
    parameters: CaseSequenceSpec

    def __post_init__(self) -> None:
        if not isinstance(self.encoder, ObservationEncoder) or not isinstance(
            self.parameters, CaseSequenceSpec
        ):
            raise TypeError(
                "sequence request requires ObservationEncoder and CaseSequenceSpec"
            )
        if self.encoder.parameters.features.level != "event":
            raise ValueError("case sequences require an event-level encoder")


@dataclass(frozen=True, slots=True)
class CaseSequenceRow:
    case_id: str
    event_ids: tuple[str | None, ...]
    values: tuple[tuple[float | None, ...], ...]
    event_mask: tuple[bool, ...]
    known_masks: tuple[tuple[bool, ...], ...]
    unknown_term_counts: tuple[int | None, ...]
    truncated_event_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _typed_tuple(self.values, tuple, "values")
        _typed_tuple(self.known_masks, tuple, "known_masks")
        if not isinstance(self.unknown_term_counts, tuple):
            raise TypeError("unknown_term_counts must be a tuple")
        if not isinstance(self.event_ids, tuple) or not isinstance(
            self.event_mask, tuple
        ):
            raise TypeError("event_ids and event_mask must be tuples")
        if (
            len(
                {
                    len(self.event_ids),
                    len(self.values),
                    len(self.event_mask),
                    len(self.known_masks),
                    len(self.unknown_term_counts),
                }
            )
            != 1
        ):
            raise ValueError(
                "sequence identities, values and masks must have equal length"
            )
        actual = tuple(x for x in self.event_ids if x is not None)
        _strings(actual, "sequence event IDs")
        _strings(self.truncated_event_ids, "truncated_event_ids")
        if set(actual) & set(self.truncated_event_ids):
            raise ValueError("retained and truncated events must be disjoint")
        for event_id, values, present, known, unknown_count in zip(
            self.event_ids,
            self.values,
            self.event_mask,
            self.known_masks,
            self.unknown_term_counts,
        ):
            if type(present) is not bool or present != (event_id is not None):
                raise ValueError("event mask must identify actual events, not padding")
            if any(
                value is not None
                and (
                    type(value) is not float or not -float("inf") < value < float("inf")
                )
                for value in values
            ):
                raise ValueError("sequence values must be finite floats or None")
            if any(type(value) is not bool for value in known) or known != tuple(
                value is not None for value in values
            ):
                raise ValueError(
                    "known masks must distinguish actual zero from missing values"
                )
            if not present and any(value is not None for value in values):
                raise ValueError("padding must contain only None values")
            if present:
                _integer(unknown_count, "unknown_term_count")
            elif unknown_count is not None:
                raise ValueError("padding has no unknown-term observation")


@dataclass(frozen=True, slots=True)
class CaseSequenceTensor:
    columns: tuple[FeatureColumn, ...]
    rows: tuple[CaseSequenceRow, ...]
    model_digest: str
    sequence_length: int
    excluded_case_ids: tuple[str, ...]
    column_units: tuple[str, ...]

    def __post_init__(self) -> None:
        _typed_tuple(self.columns, FeatureColumn, "columns")
        if not isinstance(self.column_units, tuple) or len(self.column_units) != len(
            self.columns
        ):
            raise ValueError("one unit declaration is required per tensor column")
        for unit in self.column_units:
            _text(unit, "feature unit")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("sequence columns must be unique")
        _typed_tuple(self.rows, CaseSequenceRow, "rows")
        _text(self.model_digest, "model_digest")
        _integer(self.sequence_length, "sequence_length", 1)
        _strings(self.excluded_case_ids, "excluded_case_ids")
        _strings(tuple(row.case_id for row in self.rows), "sequence case IDs")
        _strings(
            tuple(
                event
                for row in self.rows
                for event in row.event_ids
                if event is not None
            ),
            "all sequence event IDs",
        )
        if set(self.excluded_case_ids) & {row.case_id for row in self.rows}:
            raise ValueError("excluded cases cannot have sequences")
        if any(
            len(row.values) != self.sequence_length
            or any(len(values) != len(self.columns) for values in row.values)
            for row in self.rows
        ):
            raise ValueError("sequence tensor dimensions must agree with its schema")


def encode_case_sequences(
    log: CaseLog, encoder: ObservationEncoder, spec: CaseSequenceSpec
) -> ComputationResult[CaseSequenceTensor]:
    """Pad cutoff event rows without conflating padding, missing values and zero.

    By default a sequence longer than the requested length is unavailable, not
    silently truncated. Explicit ``truncation='oldest'`` keeps recent events and
    records dropped identities; this intentional data reduction returns PARTIAL.
    ``max_cells`` bounds both the event-matrix intermediate and padded tensor;
    preflight runs before materializing either numeric structure.
    """
    source = _source(log)
    request = CaseSequenceRequest(encoder, spec)
    operator = "pix.case_centric.encode_case_sequences"
    try:
        snapshot, _, _ = _cutoff_log(log, encoder.parameters.observation)
        width = max(1, len(encoder.fitted_model.columns))
        if (
            max(
                len(snapshot.traces) * spec.length,
                sum(len(trace.events) for trace in snapshot.traces),
            )
            * width
            > spec.max_cells
        ):
            raise OverflowError(
                "sequence tensor or intermediate event matrix exceeds max_cells; neither is materialized"
            )
    except (ValueError, OverflowError) as error:
        return _failure(operator, source, request, error)
    del snapshot
    transformed = transform_observations(log, encoder)
    parents = (transformed.computation_id,)
    if transformed.value is None:
        return _result(
            operator,
            None,
            request,
            transformed.status,
            None,
            transformed.issues,
            source_digest=source,
            parent_computation_ids=parents,
        )
    matrix = transformed.value.matrix
    groups = {}
    for row, mask in zip(matrix.rows, transformed.value.known_masks):
        groups.setdefault(row.case_id, []).append((row, mask))
    if len(groups) * spec.length * max(1, len(matrix.columns)) > spec.max_cells:
        return _failure(
            operator,
            source,
            request,
            OverflowError(
                "sequence tensor exceeds max_cells; no partial tensor is returned"
            ),
            parents=parents,
        )
    issues, rows = list(transformed.issues), []
    for case_id, entries in groups.items():
        dropped = ()
        if len(entries) > spec.length:
            if spec.truncation == "error":
                return _result(
                    operator,
                    None,
                    request,
                    ComputeStatus.UNAVAILABLE,
                    None,
                    (
                        ComputeIssue(
                            "sequence_length_exceeded",
                            "A case sequence exceeds the requested length; choose explicit truncation or increase length",
                            (case_id,),
                        ),
                    ),
                    source_digest=source,
                    parent_computation_ids=parents,
                )
            dropped = tuple(row.event_id for row, _ in entries[: -spec.length])
            entries = entries[-spec.length :]
            issues.append(
                ComputeIssue(
                    "sequence_oldest_truncated",
                    "Oldest observed events were explicitly dropped; identities remain recorded",
                    (case_id,),
                )
            )
        event_ids = tuple(row.event_id for row, _ in entries)
        values = tuple(row.values for row, _ in entries)
        masks = tuple(mask for _, mask in entries)
        unknown_counts = tuple(row.unknown_term_count for row, _ in entries)
        count = spec.length - len(entries)
        padding_values = ((None,) * len(matrix.columns),) * count
        padding_masks = ((False,) * len(matrix.columns),) * count
        if spec.padding == "left":
            event_ids, values, masks = (
                (None,) * count + event_ids,
                padding_values + values,
                padding_masks + masks,
            )
            unknown_counts = (None,) * count + unknown_counts
        else:
            event_ids, values, masks = (
                event_ids + (None,) * count,
                values + padding_values,
                masks + padding_masks,
            )
            unknown_counts = unknown_counts + (None,) * count
        rows.append(
            CaseSequenceRow(
                case_id,
                event_ids,
                values,
                tuple(event is not None for event in event_ids),
                masks,
                unknown_counts,
                dropped,
            )
        )
    value = CaseSequenceTensor(
        matrix.columns,
        tuple(rows),
        matrix.model_digest,
        spec.length,
        transformed.value.excluded_case_ids,
        transformed.value.column_units,
    )
    return _result_for(operator, source, request, value, tuple(issues), parents=parents)


RESULT_SCHEMAS = {
    "pix.case_centric.observation_dataset": (
        "case-observation-dataset",
        ObservationRequest,
        ObservationDataset,
    ),
    "pix.case_centric.leakage_safe_split": (
        "case-leakage-safe-split",
        LeakageSplitSpec,
        LeakageSafeSplit,
    ),
    "pix.case_centric.fit_observation_encoder": (
        "case-observation-encoder",
        ObservationEncoderRequest,
        ObservationEncoder,
    ),
    "pix.case_centric.transform_observations": (
        "case-masked-observations",
        ObservationTransformRequest,
        MaskedObservationMatrix,
    ),
    "pix.case_centric.encode_case_sequences": (
        "case-sequence-tensor",
        CaseSequenceRequest,
        CaseSequenceTensor,
    ),
}

__all__ = [
    "ObservationSpec",
    "CaseFollowUp",
    "ObservationRequest",
    "ObservationSample",
    "CensoredPredictionTarget",
    "ObservationDataset",
    "observation_dataset",
    "CaseAvailability",
    "LeakageSplitSpec",
    "LeakageSafeSplit",
    "leakage_safe_split",
    "ObservationEncoderSpec",
    "ObservationEncoderRequest",
    "ObservationEncoder",
    "ObservationTransformRequest",
    "MaskedObservationMatrix",
    "fit_observation_encoder",
    "transform_observations",
    "CaseSequenceSpec",
    "CaseSequenceRequest",
    "CaseSequenceRow",
    "CaseSequenceTensor",
    "encode_case_sequences",
]
