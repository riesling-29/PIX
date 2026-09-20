"""Finite, immutable business-calendar snapshots with explicit UTC coverage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _utc(value):
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValueError("calendar timestamps must be timezone aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class WorkingInterval:
    start: datetime
    end: datetime

    def __post_init__(self):
        object.__setattr__(self, "start", _utc(self.start))
        object.__setattr__(self, "end", _utc(self.end))
        if self.start >= self.end:
            raise ValueError("working interval must have positive duration")


@dataclass(frozen=True, slots=True)
class BusinessCalendar:
    coverage_start: datetime
    coverage_end: datetime
    windows: tuple[WorkingInterval, ...]
    description: str = "explicit UTC windows"

    def __post_init__(self):
        object.__setattr__(self, "coverage_start", _utc(self.coverage_start))
        object.__setattr__(self, "coverage_end", _utc(self.coverage_end))
        if self.coverage_start >= self.coverage_end:
            raise ValueError("calendar coverage must have positive duration")
        if not isinstance(self.description, str):
            raise TypeError("description must be text")
        if not isinstance(self.windows, tuple) or any(
            not isinstance(w, WorkingInterval) for w in self.windows
        ):
            raise TypeError("windows must contain WorkingInterval")
        previous = self.coverage_start
        for w in self.windows:
            if not previous <= w.start < w.end <= self.coverage_end:
                raise ValueError(
                    "windows must be ordered, disjoint, and inside coverage"
                )
            previous = w.end

    def seconds(self, start: datetime, end: datetime) -> float:
        start, end = _utc(start), _utc(end)
        if not self.coverage_start <= start <= end <= self.coverage_end:
            raise ValueError(
                "observation lies outside calendar coverage or is reversed"
            )
        return sum(
            (
                (min(end, w.end) - max(start, w.start)).total_seconds()
                for w in self.windows
                if w.start < end and w.end > start
            ),
            0.0,
        )


def weekly_business_calendar(
    start: datetime,
    end: datetime,
    *,
    timezone_name: str,
    slots: tuple[tuple[int, int, int], ...],
    holidays: tuple[str, ...] = (),
    ambiguous: str = "reject",
    max_days: int = 36600,
) -> BusinessCalendar:
    """Freeze local weekly slots (weekday, start/end minutes) into UTC intervals.

    Dates excluded as holidays are ISO local dates. Slots may end at minute 1440.
    Nonexistent boundary times are rejected; ambiguous times require earliest/latest
    or rejection. Full-day DST windows count actual 23/25-hour elapsed time. The
    returned UTC snapshot is independent of future timezone-database changes.
    """
    start, end = _utc(start), _utc(end)
    if start >= end:
        raise ValueError("end must be after start")
    if type(max_days) is not int or max_days < 1:
        raise ValueError("max_days must be positive")
    if ambiguous not in ("reject", "earliest", "latest"):
        raise ValueError("invalid ambiguous boundary policy")
    if not isinstance(slots, tuple) or any(
        not isinstance(s, tuple)
        or len(s) != 3
        or any(type(v) is not int for v in s)
        or not (0 <= s[0] <= 6 and 0 <= s[1] < s[2] <= 1440)
        for s in slots
    ):
        raise ValueError("slots must be weekday/start-minute/end-minute tuples")
    if not isinstance(holidays, tuple) or any(not isinstance(d, str) for d in holidays):
        raise TypeError("holidays must be ISO date strings")
    from datetime import date

    for day in holidays:
        if date.fromisoformat(day).isoformat() != day:
            raise ValueError("holiday must use YYYY-MM-DD")
    try:
        zone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as error:
        raise ValueError(
            "unknown/unavailable timezone; install tzdata when the system has no IANA database"
        ) from error
    first, last = start.astimezone(zone).date(), end.astimezone(zone).date()
    count = (last - first).days + 1
    if count > max_days:
        raise ValueError("calendar day limit exceeded")

    def resolve(local):
        candidates = sorted(
            {
                local.replace(tzinfo=zone, fold=f).astimezone(timezone.utc)
                for f in (0, 1)
                if local.replace(tzinfo=zone, fold=f)
                .astimezone(timezone.utc)
                .astimezone(zone)
                .replace(tzinfo=None)
                == local
            }
        )
        if not candidates:
            raise ValueError(f"nonexistent local calendar boundary {local}")
        if len(candidates) > 1 and ambiguous == "reject":
            raise ValueError(f"ambiguous local calendar boundary {local}")
        return candidates[-1] if ambiguous == "latest" else candidates[0]

    intervals = []
    for offset in range(count):
        day = first + timedelta(days=offset)
        if day.isoformat() in holidays:
            continue
        midnight = datetime.combine(day, time())
        for weekday, left, right in slots:
            if weekday != day.weekday():
                continue
            a, b = (
                resolve(midnight + timedelta(minutes=left)),
                resolve(midnight + timedelta(minutes=right)),
            )
            if a >= b:
                raise ValueError(
                    "calendar boundary policy produces nonpositive interval"
                )
            a, b = max(a, start), min(b, end)
            if a < b:
                intervals.append((a, b))
    merged = []
    for a, b in sorted(intervals):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return BusinessCalendar(
        start,
        end,
        tuple(WorkingInterval(a, b) for a, b in merged),
        f"weekly:{timezone_name}; ambiguous={ambiguous}; frozen UTC snapshot",
    )


__all__ = ["WorkingInterval", "BusinessCalendar", "weekly_business_calendar"]
