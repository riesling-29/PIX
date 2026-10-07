"""Occurrence-based DFG and variant-position timing with auditable calendars."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import timezone

from pix.case_centric.business_time import BusinessCalendar
from pix.case_centric.statistics import NumericSummary, _summary
from pix.compute._common import _result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest
from pix.event_log.adapters import _activity


@dataclass(frozen=True, slots=True)
class PathPerformanceSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    target_timestamp_key: str | None = None
    grouping: str = "activity_pair"
    calendar: BusinessCalendar | None = None
    negative: str = "exclude"
    max_witnesses: int = 10000

    def __post_init__(self):
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if self.target_timestamp_key is not None and (
            not isinstance(self.target_timestamp_key, str)
            or not self.target_timestamp_key
        ):
            raise ValueError("target_timestamp_key must be nonempty text")
        if self.grouping not in ("activity_pair", "variant_position"):
            raise ValueError("unknown grouping")
        if self.calendar is not None and not isinstance(
            self.calendar, BusinessCalendar
        ):
            raise TypeError("calendar must be BusinessCalendar")
        if self.negative not in ("exclude", "signed", "reject"):
            raise ValueError("unknown negative-duration policy")
        if type(self.max_witnesses) is not int or self.max_witnesses < 0:
            raise ValueError("max_witnesses must be nonnegative")


@dataclass(frozen=True, slots=True)
class PathWitness:
    case_id: str
    source_event_id: str
    target_event_id: str
    source_position: int
    seconds: float | None
    exclusion: str | None


@dataclass(frozen=True, slots=True)
class PathPerformanceEdge:
    source: str
    target: str
    variant: tuple[str, ...] | None
    source_position: int | None
    occurrence_count: int
    excluded_count: int
    duration: NumericSummary

    def __post_init__(self):
        if (
            type(self.occurrence_count) is not int
            or type(self.excluded_count) is not int
            or not 0 <= self.excluded_count <= self.occurrence_count
        ):
            raise ValueError("invalid path counts")
        if self.duration.count + self.excluded_count != self.occurrence_count:
            raise ValueError("duration population differs from eligible paths")


@dataclass(frozen=True, slots=True)
class PathPerformance:
    edges: tuple[PathPerformanceEdge, ...]
    witnesses: tuple[PathWitness, ...]
    total_pairs: int
    omitted_witnesses: int
    duration_unit: str = "seconds"

    def __post_init__(self):
        if self.total_pairs != sum(e.occurrence_count for e in self.edges):
            raise ValueError("total pairs differ from edge population")
        if (
            self.omitted_witnesses < 0
            or len(self.witnesses) + self.omitted_witnesses != self.total_pairs
        ):
            raise ValueError("invalid witness coverage")


def _timestamp(log, event, key):
    attr = log.attribute(event, key)
    if (
        attr is None
        or attr.type != "date"
        or attr.value.tzinfo is None
        or attr.value.utcoffset() is None
    ):
        return None
    return attr.value.astimezone(timezone.utc)


def measure_path_performance(
    log: CaseLog, spec: PathPerformanceSpec = PathPerformanceSpec()
):
    """Default complete→complete gaps; optional target start changes the meaning.

    Source order defines adjacency. A negative gap may indicate overlap or bad
    ordering and is never silently absolutized. Calendar coverage failures are
    excluded with a diagnostic, not treated as zero business time.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, PathPerformanceSpec):
        raise TypeError("expected CaseLog and PathPerformanceSpec")
    groups, witnesses, issues, total = defaultdict(list), [], [], 0
    try:
        for trace in log.traces:
            variant = tuple(_activity(log, e, spec.trace_spec) for e in trace.events)
            for index, (source, target) in enumerate(
                zip(trace.events, trace.events[1:])
            ):
                total += 1
                start = _timestamp(log, source, spec.trace_spec.timestamp_key)
                end = _timestamp(
                    log,
                    target,
                    spec.target_timestamp_key or spec.trace_spec.timestamp_key,
                )
                duration, exclusion = None, None
                if start is None or end is None:
                    exclusion = "unknown_timestamp"
                else:
                    negative = end < start
                    if negative and spec.negative == "reject":
                        raise ValueError("negative path duration")
                    if negative and spec.negative == "exclude":
                        exclusion = "negative_duration"
                    elif spec.calendar is None:
                        duration = (end - start).total_seconds()
                    else:
                        try:
                            duration = spec.calendar.seconds(
                                min(start, end), max(start, end)
                            ) * (-1 if negative else 1)
                        except ValueError:
                            exclusion = "calendar_coverage"
                key = (
                    variant[index],
                    variant[index + 1],
                    variant if spec.grouping == "variant_position" else (),
                    index if spec.grouping == "variant_position" else -1,
                )
                groups[key].append(duration)
                if exclusion:
                    issues.append(
                        ComputeIssue(
                            exclusion,
                            "Path excluded from duration statistics",
                            (trace.id, source.id, target.id),
                        )
                    )
                if len(witnesses) < spec.max_witnesses:
                    witnesses.append(
                        PathWitness(
                            trace.id, source.id, target.id, index, duration, exclusion
                        )
                    )
        edges = tuple(
            PathPerformanceEdge(
                a,
                b,
                variant or None,
                index if index >= 0 else None,
                len(values),
                sum(v is None for v in values),
                _summary(v for v in values if v is not None),
            )
            for (a, b, variant, index), values in sorted(groups.items())
        )
        omitted = total - len(witnesses)
        if omitted:
            issues.append(
                ComputeIssue(
                    "witnesses_truncated",
                    f"{omitted} path witnesses omitted; aggregates include all eligible pairs",
                )
            )
        value = PathPerformance(edges, tuple(witnesses), total, omitted)
        status = ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED
    except (ValueError, OverflowError) as error:
        value, status = None, ComputeStatus.INVALID_INPUT
        issues = [ComputeIssue("invalid_path_performance", str(error))]
    return _result(
        "pix.case_centric.measure_path_performance",
        None,
        spec,
        status,
        value,
        tuple(issues),
        source_digest=case_log_digest(log),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.measure_path_performance": (
        "case-path-performance",
        PathPerformanceSpec,
        PathPerformance,
    )
}
__all__ = [
    "PathPerformanceSpec",
    "PathWitness",
    "PathPerformanceEdge",
    "PathPerformance",
    "measure_path_performance",
]
