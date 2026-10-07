from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.business_time import (
    BusinessCalendar,
    WorkingInterval,
    weekly_business_calendar,
)
from pix.case_centric.path_performance import (
    PathPerformanceSpec,
    measure_path_performance,
)
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute as A
from pix.event_log import CaseEvent, CaseLog, CaseTrace
from pix.results import result_from_json, result_json_bytes

T = datetime(2026, 9, 18, tzinfo=timezone.utc)


def source():
    return CaseLog(
        (
            CaseTrace(
                "one",
                tuple(
                    CaseEvent(
                        str(i),
                        (
                            A("concept:name", "string", label),
                            A("time:timestamp", "date", T + timedelta(seconds=seconds)),
                        ),
                    )
                    for i, (label, seconds) in enumerate(zip("ABAB", (0, 10, 12, 32)))
                ),
            ),
        )
    )


def test_dfg_aggregates_and_variant_occurrences_are_not_conflated():
    result = measure_path_performance(source())
    ab = next(e for e in result.value.edges if e.source == "A")
    assert ab.occurrence_count == 2
    assert ab.duration.mean == 15
    assert ab.duration.median == 15
    assert ab.duration.population_stddev == 5
    variant = measure_path_performance(
        source(), PathPerformanceSpec(grouping="variant_position")
    )
    assert [
        (e.source_position, e.duration.mean)
        for e in variant.value.edges
        if e.source == "A"
    ] == [(0, 10), (2, 20)]
    assert result_from_json(result_json_bytes(variant)) == variant


def test_business_time_keeps_coverage_and_witnesses():
    calendar = BusinessCalendar(
        T,
        T + timedelta(seconds=40),
        (WorkingInterval(T + timedelta(seconds=5), T + timedelta(seconds=15)),),
    )
    result = measure_path_performance(source(), PathPerformanceSpec(calendar=calendar))
    assert [w.seconds for w in result.value.witnesses] == [5, 2, 3]
    assert result_from_json(result_json_bytes(result)) == result
    short = replace(calendar, coverage_end=T + timedelta(seconds=20))
    result = measure_path_performance(source(), PathPerformanceSpec(calendar=short))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.witnesses[-1].exclusion == "calendar_coverage"
    closed = measure_path_performance(
        source(), PathPerformanceSpec(calendar=replace(calendar, windows=()))
    )
    assert all(w.seconds == 0.0 for w in closed.value.witnesses)
    assert result_from_json(result_json_bytes(closed)) == closed


def test_negative_missing_and_evidence_caps_are_explicit():
    log = source()
    events = list(log.traces[0].events)
    events[1] = replace(
        events[1],
        attributes=(
            events[1].attributes[0],
            A("time:timestamp", "date", T - timedelta(seconds=1)),
        ),
    )
    log = replace(log, traces=(replace(log.traces[0], events=tuple(events)),))
    assert (
        measure_path_performance(log).value.witnesses[0].exclusion
        == "negative_duration"
    )
    assert (
        measure_path_performance(log, PathPerformanceSpec(negative="reject")).status
        is ComputeStatus.INVALID_INPUT
    )
    assert (
        measure_path_performance(log, PathPerformanceSpec(negative="signed"))
        .value.witnesses[0]
        .seconds
        == -1
    )
    capped = measure_path_performance(source(), PathPerformanceSpec(max_witnesses=0))
    assert capped.value.omitted_witnesses == 3
    assert capped.value.edges[0].duration.count == 2


def test_dst_real_elapsed_time_and_holiday_exclusion():
    # UTC horizons correspond to local midnight-to-midnight on DST transitions.
    for start, end, hours in (
        (
            datetime(2026, 3, 8, 5, tzinfo=timezone.utc),
            datetime(2026, 3, 9, 4, tzinfo=timezone.utc),
            23,
        ),
        (
            datetime(2026, 11, 1, 4, tzinfo=timezone.utc),
            datetime(2026, 11, 2, 5, tzinfo=timezone.utc),
            25,
        ),
    ):
        cal = weekly_business_calendar(
            start, end, timezone_name="America/New_York", slots=((6, 0, 1440),)
        )
        assert cal.seconds(start, end) == hours * 3600
    empty = weekly_business_calendar(
        T,
        T + timedelta(days=1),
        timezone_name="UTC",
        slots=((4, 0, 1440),),
        holidays=("2026-09-18",),
    )
    assert empty.seconds(T, T + timedelta(days=1)) == 0


def test_ambiguous_nonexistent_and_overlapping_windows():
    start = datetime(2026, 11, 1, 4, tzinfo=timezone.utc)
    end = start + timedelta(hours=25)
    with pytest.raises(ValueError, match="ambiguous"):
        weekly_business_calendar(
            start, end, timezone_name="America/New_York", slots=((6, 90, 120),)
        )
    a = weekly_business_calendar(
        start,
        end,
        timezone_name="America/New_York",
        slots=((6, 90, 120),),
        ambiguous="earliest",
    )
    b = weekly_business_calendar(
        start,
        end,
        timezone_name="America/New_York",
        slots=((6, 90, 120),),
        ambiguous="latest",
    )
    assert a.seconds(start, end) - b.seconds(start, end) == 3600
    with pytest.raises(ValueError, match="nonexistent"):
        weekly_business_calendar(
            datetime(2026, 3, 8, 5, tzinfo=timezone.utc),
            datetime(2026, 3, 9, 4, tzinfo=timezone.utc),
            timezone_name="America/New_York",
            slots=((6, 150, 180),),
        )
    cal = weekly_business_calendar(
        T,
        T + timedelta(days=1),
        timezone_name="UTC",
        slots=((4, 60, 180), (4, 120, 240)),
    )
    assert cal.seconds(T, T + timedelta(days=1)) == 3 * 3600
