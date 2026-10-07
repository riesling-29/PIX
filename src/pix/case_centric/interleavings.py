"""Strict timestamp crossings between linked case logs, with source witnesses.

Adjacent timestamp segments cross when L0 < R0 < L1 < R1 (LR), or
R0 < L0 < R1 < L1 (RL). The reference's asymmetric endpoint choice is
explicit: LR selects L0 -> R0; RL selects R1 -> L1. These are temporal
candidates, never evidence of causality. Optional logical infinite boundaries
replace artificial timestamp/event rows; no fictitious source identity exists.

The sweep visits adjacent segments without materializing a Cartesian join.
Bounds fail closed: no truncated set is published as a complete calculation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import ClassVar

from pix.compute._common import _result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class CaseLink:
    """Explicit relation between internal case identities in distinct inputs."""

    left_case_id: str
    right_case_id: str

    def __post_init__(self):
        _text(self.left_case_id, "left_case_id")
        _text(self.right_case_id, "right_case_id")


@dataclass(frozen=True, slots=True)
class InterleavingSpec:
    case_links: tuple[CaseLink, ...] = ()
    left_timestamp_key: str = "time:timestamp"
    right_timestamp_key: str = "time:timestamp"
    left_activity_key: str = "concept:name"
    right_activity_key: str = "concept:name"
    include_boundaries: bool = True
    max_case_links: int = 100000
    max_events: int = 1000000
    max_steps: int = 2000000
    max_witnesses: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.case_links, tuple) or not all(
            isinstance(link, CaseLink) for link in self.case_links
        ):
            raise TypeError("case_links must be a tuple of CaseLink")
        if len(set(self.case_links)) != len(self.case_links):
            raise ValueError("duplicate case links are not permitted")
        for name in (
            "left_timestamp_key",
            "right_timestamp_key",
            "left_activity_key",
            "right_activity_key",
        ):
            _text(getattr(self, name), name)
        if type(self.include_boundaries) is not bool:
            raise TypeError("include_boundaries must be bool")
        for name in ("max_case_links", "max_events", "max_steps", "max_witnesses"):
            _positive(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class InterleavingPoint:
    side: str
    case_id: str
    event_id: str | None
    source_position: int | None
    activity: str | None
    timestamp: datetime | None
    boundary: str | None = None

    def __post_init__(self):
        if self.side not in ("left", "right"):
            raise ValueError("side must be left or right")
        _text(self.case_id, "case_id")
        if self.boundary is not None:
            if self.boundary not in ("start", "end"):
                raise ValueError("boundary must be start or end")
            if any(
                value is not None
                for value in (
                    self.event_id,
                    self.source_position,
                    self.activity,
                    self.timestamp,
                )
            ):
                raise ValueError("logical boundaries have no fabricated source facts")
        else:
            _text(self.event_id, "event_id")
            if type(self.source_position) is not int or self.source_position < 0:
                raise ValueError("source_position must be nonnegative integer")
            if self.activity is not None:
                _text(self.activity, "activity")
            if (
                not isinstance(self.timestamp, datetime)
                or self.timestamp.utcoffset() is None
            ):
                raise ValueError("timestamp must be an aware datetime")


def _before(left, right):
    if left.boundary == "start":
        return right.boundary != "start"
    if right.boundary == "end":
        return left.boundary != "end"
    if left.boundary == "end" or right.boundary == "start":
        return False
    return left.timestamp < right.timestamp


@dataclass(frozen=True, slots=True)
class InterleavingWitness:
    left_case_id: str
    right_case_id: str
    direction: str
    left_segment: tuple[InterleavingPoint, InterleavingPoint]
    right_segment: tuple[InterleavingPoint, InterleavingPoint]
    source: InterleavingPoint
    target: InterleavingPoint
    elapsed_seconds: float | None

    def __post_init__(self):
        _text(self.left_case_id, "left_case_id")
        _text(self.right_case_id, "right_case_id")
        for name, side, case_id in (
            ("left_segment", "left", self.left_case_id),
            ("right_segment", "right", self.right_case_id),
        ):
            segment = getattr(self, name)
            if (
                not isinstance(segment, tuple)
                or len(segment) != 2
                or not all(
                    isinstance(point, InterleavingPoint)
                    and point.side == side
                    and point.case_id == case_id
                    for point in segment
                )
            ):
                raise ValueError(f"{name} must contain two matching source points")
        l0, l1 = self.left_segment
        r0, r1 = self.right_segment
        if self.direction == "LR":
            crossing, source, target = (l0, r0, l1, r1), l0, r0
        elif self.direction == "RL":
            crossing, source, target = (r0, l0, r1, l1), r1, l1
        else:
            raise ValueError("direction must be LR or RL")
        if not all(_before(a, b) for a, b in zip(crossing, crossing[1:])):
            raise ValueError("segments must satisfy the strict crossing definition")
        if (self.source, self.target) != (source, target):
            raise ValueError("selected endpoints do not match the direction profile")
        expected = (
            (target.timestamp - source.timestamp).total_seconds()
            if source.timestamp is not None and target.timestamp is not None
            else None
        )
        if self.elapsed_seconds != expected:
            raise ValueError("elapsed_seconds must describe the selected endpoints")


@dataclass(frozen=True, slots=True)
class InterleavingSet:
    left_digest: str
    right_digest: str
    case_links: tuple[CaseLink, ...]
    witnesses: tuple[InterleavingWitness, ...]
    steps: int
    linked_event_count: int

    def __post_init__(self):
        for name in ("left_digest", "right_digest"):
            digest = getattr(self, name)
            prefix = "pix.case-log.v1:sha256:"
            if (
                not isinstance(digest, str)
                or not digest.startswith(prefix)
                or len(digest) != len(prefix) + 64
                or any(char not in "0123456789abcdef" for char in digest[len(prefix) :])
            ):
                raise ValueError(f"{name} must be a SHA-256 digest")
        if (
            not isinstance(self.case_links, tuple)
            or not all(isinstance(link, CaseLink) for link in self.case_links)
            or len(set(self.case_links)) != len(self.case_links)
        ):
            raise ValueError("case_links must contain unique CaseLink values")
        links = set(self.case_links)
        if not isinstance(self.witnesses, tuple) or not all(
            isinstance(w, InterleavingWitness)
            and CaseLink(w.left_case_id, w.right_case_id) in links
            for w in self.witnesses
        ):
            raise ValueError("witnesses must belong to a selected case link")
        for name in ("steps", "linked_event_count"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


def linked_logs_digest(left_digest: str, right_digest: str) -> str:
    """Digest with side-sensitive framing; equal input IDs never merge sides."""
    return sha256(
        json.dumps(
            ["pix.linked-case-logs.v1", left_digest, right_digest],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def validate_interleaving_result(result: ComputationResult) -> None:
    """Check redundant persisted request facts, without claiming source parity.

    The full source logs are required to independently establish completeness.
    The OCEL projection re-runs the request before consuming its witnesses.
    """
    if result.operator_id != "pix.case_centric.discover_interleavings":
        raise ValueError("unexpected interleaving operator")
    spec, value = result.spec, result.value
    if not isinstance(spec, InterleavingSpec):
        raise TypeError("interleaving request type differs")
    if value is None:
        return
    if not isinstance(value, InterleavingSet):
        raise TypeError("interleaving payload type differs")
    if (
        linked_logs_digest(value.left_digest, value.right_digest)
        != result.source_digest
    ):
        raise ValueError("interleaving payload and source identity disagree")
    if value.case_links != spec.case_links:
        raise ValueError("interleaving payload and selected case links disagree")
    if (
        len(value.case_links) > spec.max_case_links
        or value.linked_event_count > spec.max_events
        or value.steps > spec.max_steps
        or len(value.witnesses) > spec.max_witnesses
    ):
        raise ValueError("interleaving payload exceeds requested bounds")
    if len(value.witnesses) > value.steps:
        raise ValueError("each crossing requires a segment comparison")
    if len(set(value.witnesses)) != len(value.witnesses):
        raise ValueError("duplicate interleaving witness")
    observed = {}
    missing_labels = False
    for witness in value.witnesses:
        for point in (*witness.left_segment, *witness.right_segment):
            if point.boundary is not None:
                if not spec.include_boundaries:
                    raise ValueError("logical boundaries were not requested")
                continue
            key = point.side, point.event_id
            if key in observed and observed[key] != point:
                raise ValueError("source event facts disagree across witnesses")
            observed[key] = point
            missing_labels |= point.activity is None
    if len(observed) > value.linked_event_count:
        raise ValueError("witness population exceeds selected events")
    if result.status is ComputeStatus.COMPUTED and (result.issues or missing_labels):
        raise ValueError("incomplete temporal labels require partial status")


def discover_interleavings(
    left: CaseLog,
    right: CaseLog,
    spec: InterleavingSpec = InterleavingSpec(),
) -> ComputationResult[InterleavingSet]:
    """Find strict segment crossings for explicit links, without mutating inputs.

    Timestamp order is stable by source position, never by renamed event IDs.
    Missing/naive/ambiguous timestamps invalidate the selected population rather
    than silently bridging a missing event. Missing activities retain temporal
    witnesses and return PARTIAL; raw attributes are never copied into results.
    Unlinked cases remain part of source identity but are not the population.
    """
    if not isinstance(left, CaseLog) or not isinstance(right, CaseLog):
        raise TypeError("left and right must be CaseLog")
    if not isinstance(spec, InterleavingSpec):
        raise TypeError("spec must be InterleavingSpec")
    left_digest, right_digest = case_log_digest(left), case_log_digest(right)
    digest = linked_logs_digest(left_digest, right_digest)
    operator = "pix.case_centric.discover_interleavings"

    def finish(status, value=None, issues=()):
        result = _result(
            operator, None, spec, status, value, tuple(issues), source_digest=digest
        )
        validate_interleaving_result(result)
        return result

    if len(spec.case_links) > spec.max_case_links:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "interleaving_case_link_limit",
                    "Case links exceed max_case_links; no truncated set returned",
                ),
            ),
        )
    cases = {
        "left": {trace.id: trace for trace in left.traces},
        "right": {trace.id: trace for trace in right.traces},
    }
    selected = {"left": set(), "right": set()}
    for link in spec.case_links:
        for side, case_id in (
            ("left", link.left_case_id),
            ("right", link.right_case_id),
        ):
            if case_id not in cases[side]:
                return finish(
                    ComputeStatus.INVALID_INPUT,
                    issues=(
                        ComputeIssue(
                            "unknown_linked_case",
                            "Case link references an absent internal case ID",
                            (side, case_id),
                        ),
                    ),
                )
            selected[side].add(case_id)
    event_count = sum(
        len(cases[side][case_id].events)
        for side in selected
        for case_id in selected[side]
    )
    if event_count > spec.max_events:
        return finish(
            ComputeStatus.UNAVAILABLE,
            issues=(
                ComputeIssue(
                    "interleaving_event_limit",
                    "Selected events exceed max_events; no truncated set returned",
                ),
            ),
        )
    points, issues = {}, []
    for side, log in (("left", left), ("right", right)):
        for trace in log.traces:
            if trace.id not in selected[side]:
                continue
            ordered = []
            for position, event in enumerate(trace.events):
                try:
                    timestamp = log.attribute(
                        event, getattr(spec, f"{side}_timestamp_key")
                    )
                    activity = log.attribute(
                        event, getattr(spec, f"{side}_activity_key")
                    )
                except ValueError as exc:
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "ambiguous_attribute",
                                str(exc),
                                (side, trace.id, event.id),
                            ),
                        ),
                    )
                if (
                    timestamp is None
                    or timestamp.type != "date"
                    or timestamp.value.utcoffset() is None
                ):
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "invalid_interleaving_time",
                                "Every selected event needs an aware timestamp",
                                (side, trace.id, event.id),
                            ),
                        ),
                    )
                label = (
                    activity.value
                    if (
                        activity is not None
                        and activity.type in ("string", "id")
                        and activity.value.strip()
                    )
                    else None
                )
                if label is None:
                    issues.append(
                        ComputeIssue(
                            "missing_interleaving_activity",
                            "Temporal witness retained without an activity label",
                            (side, trace.id, event.id),
                        )
                    )
                try:
                    utc_time = timestamp.value.astimezone(timezone.utc)
                except (OverflowError, ValueError):
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "invalid_interleaving_time",
                                "Selected timestamp cannot be represented in UTC",
                                (side, trace.id, event.id),
                            ),
                        ),
                    )
                ordered.append(
                    InterleavingPoint(
                        side,
                        trace.id,
                        event.id,
                        position,
                        label,
                        utc_time,
                    )
                )
            ordered.sort(key=lambda point: (point.timestamp, point.source_position))
            if ordered and spec.include_boundaries:
                ordered = [
                    InterleavingPoint(side, trace.id, None, None, None, None, "start"),
                    *ordered,
                    InterleavingPoint(side, trace.id, None, None, None, None, "end"),
                ]
            points[side, trace.id] = ordered
    witnesses, steps = [], 0
    for link in spec.case_links:
        ls, rs = points["left", link.left_case_id], points["right", link.right_case_id]
        i = j = 0
        while i + 1 < len(ls) and j + 1 < len(rs):
            steps += 1
            if steps > spec.max_steps:
                return finish(
                    ComputeStatus.UNAVAILABLE,
                    issues=(
                        ComputeIssue(
                            "interleaving_step_limit",
                            "Segment sweep exceeds max_steps; no truncated set returned",
                        ),
                    ),
                )
            l0, l1, r0, r1 = ls[i], ls[i + 1], rs[j], rs[j + 1]
            direction = None
            if _before(l0, r0) and _before(r0, l1) and _before(l1, r1):
                direction, source, target = "LR", l0, r0
            elif _before(r0, l0) and _before(l0, r1) and _before(r1, l1):
                direction, source, target = "RL", r1, l1
            if direction is not None:
                if len(witnesses) >= spec.max_witnesses:
                    return finish(
                        ComputeStatus.UNAVAILABLE,
                        issues=(
                            ComputeIssue(
                                "interleaving_witness_limit",
                                "Witnesses exceed max_witnesses; no truncated set returned",
                            ),
                        ),
                    )
                elapsed = (
                    (target.timestamp - source.timestamp).total_seconds()
                    if target.timestamp is not None and source.timestamp is not None
                    else None
                )
                witnesses.append(
                    InterleavingWitness(
                        link.left_case_id,
                        link.right_case_id,
                        direction,
                        (l0, l1),
                        (r0, r1),
                        source,
                        target,
                        elapsed,
                    )
                )
            if _before(l1, r1):
                i += 1
            elif _before(r1, l1):
                j += 1
            else:
                i += 1
                j += 1
    payload = InterleavingSet(
        left_digest,
        right_digest,
        spec.case_links,
        tuple(witnesses),
        steps,
        event_count,
    )
    return finish(
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED, payload, issues
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_interleavings": (
        "case_interleavings",
        InterleavingSpec,
        InterleavingSet,
    ),
}

__all__ = [
    "CaseLink",
    "InterleavingSpec",
    "InterleavingPoint",
    "InterleavingWitness",
    "InterleavingSet",
    "discover_interleavings",
]
