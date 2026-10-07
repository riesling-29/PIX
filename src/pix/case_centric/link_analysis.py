"""Typed event-to-event output/input links with bounded exact reachability.

The input is a CaseLog; links may cross cases. Equal timestamps are ordered by
flattened input position, never event identity. Forward means strict sorted
position, not strictly increasing clock time. Closure includes nonempty cycles
and carries one shortest, input-order-deterministic path per reachable pair.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import ClassVar

from pix.compute._common import _result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseLog, case_log_digest

OPERATOR_ID = "pix.case_centric.link_analysis"


@dataclass(frozen=True, slots=True)
class LinkAnalysisSpec:
    """Output/input scopes select event, trace or internal case identity.

    Attribute scopes resolve XES global defaults. case_id uses the containing
    CaseTrace.id as a typed id value, ignoring its selected key. No trace name
    or attribute is silently projected into the event's recorded attributes.

    Missing, null, nonfinite, compound and naive-date endpoint values cannot
    participate in equality; diagnostics identify each excluded endpoint. A
    missing or invalid sorting timestamp invalidates the whole calculation.
    keep_first_occurrence selects the first eligible target before propagation.
    Budgets govern events, emitted pairs, adjacency insertions plus traversal
    steps, and total event occurrences in all returned path witnesses.
    """

    out_key: str = "out"
    in_key: str = "in"
    out_scope: str = "event"
    in_scope: str = "event"
    timestamp_key: str = "time:timestamp"
    look_forward: bool = True
    keep_first_occurrence: bool = False
    propagate: bool = False
    max_events: int = 10_000
    max_links: int = 100_000
    max_work: int = 1_000_000
    max_witness_events: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("out_key", "in_key", "timestamp_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonblank text")
        for name in ("look_forward", "keep_first_occurrence", "propagate"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        for name in ("out_scope", "in_scope"):
            if getattr(self, name) not in ("event", "trace", "case_id"):
                raise ValueError(f"{name} must be event, trace or case_id")
        for name in ("max_events", "max_links", "max_work", "max_witness_events"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class LinkEventReference:
    event_id: str
    trace_id: str
    trace_index: int
    event_index: int
    source_index: int
    order_index: int
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class LinkEndpointExclusion:
    event_id: str
    direction: str
    scope: str
    key: str
    reason: str


@dataclass(frozen=True, slots=True)
class EventLink:
    source_event_id: str
    target_event_id: str
    source_order: int
    target_order: int
    direct: bool
    path_event_ids: tuple[str, ...]
    path_orders: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LinkAnalysisPayload:
    """Complete relation on eligible typed endpoints; no original values copied.

    candidate_pair_count precedes keep-first; direct_link_count follows it.
    events always contains every source event, including ineligible endpoints.
    Excluded endpoints can make the eligible-population result PARTIAL even
    though every reachable pair within that population was computed exactly.
    """

    events: tuple[LinkEventReference, ...]
    links: tuple[EventLink, ...]
    exclusions: tuple[LinkEndpointExclusion, ...]
    candidate_pair_count: int
    direct_link_count: int
    propagated_link_count: int
    work_count: int
    witness_event_count: int


class _LimitReached(Exception):
    def __init__(self, name, observed, limit):
        self.issue = ComputeIssue(
            "link_analysis_limit",
            f"{name} requires {observed}, exceeding limit {limit}; no relation returned",
            (name,),
        )


def _limit(name: str, observed: int, limit: int) -> None:
    if observed > limit:
        raise _LimitReached(name, observed, limit)


def _token(attribute: CaseAttribute | None):
    if attribute is None:
        return None, "missing"
    kind, value = attribute.type, attribute.value
    if kind == "null":
        return None, "null"
    if kind in ("list", "container"):
        return None, "compound"
    if kind == "float" and not isfinite(value):
        return None, "nonfinite"
    if kind == "date":
        if value.utcoffset() is None:
            return None, "naive_date"
        try:
            value = value.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            return None, "invalid_date"
    # The tag prevents Python's True == 1 == 1.0 from conflating XES types.
    # Finite floats use numeric equality, including -0.0 == +0.0.
    return (kind, value), None


def _path(predecessors, endpoint):
    result = []
    while endpoint is not None:
        result.append(endpoint)
        endpoint = predecessors[endpoint]
    return tuple(reversed(result))


def discover_link_analysis(
    log: CaseLog, spec: LinkAnalysisSpec = LinkAnalysisSpec()
) -> ComputationResult[LinkAnalysisPayload]:
    """Link events when typed out(source) equals typed in(target).

    Distinct cases are not an implicit filtering boundary. Event IDs are
    evidence labels only; case_id scope explicitly selects trace IDs as keys.
    Without forward filtering, self-links and links back in time are retained.
    Propagation computes the transitive closure, never a reflexive closure:
    self pairs arise only from a direct self-link or a nonempty cycle.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, LinkAnalysisSpec):
        raise TypeError("spec must be LinkAnalysisSpec")
    digest = case_log_digest(log)

    def finish(status, value=None, issues=()):
        return _result(
            OPERATOR_ID,
            None,
            spec,
            status,
            value,
            tuple(issues),
            source_digest=digest,
        )

    exclusions = []
    rows = []
    try:
        count = sum(len(trace.events) for trace in log.traces)
        _limit("max_events", count, spec.max_events)
        for trace_index, trace in enumerate(log.traces):
            trace_attrs = (
                {a.key: a for a in log.effective_attributes(trace)}
                if "trace" in (spec.out_scope, spec.in_scope)
                else {}
            )
            for event_index, event in enumerate(trace.events):
                # Resolve once to detect ambiguity even among default attributes.
                attrs = {a.key: a for a in log.effective_attributes(event)}
                timestamp = attrs.get(spec.timestamp_key)
                if timestamp is None or timestamp.type != "date":
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "invalid_link_timestamp",
                                "Every event needs a timezone-aware date for global order",
                                (event.id, spec.timestamp_key),
                            ),
                        ),
                    )
                if timestamp.value.utcoffset() is None:
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "invalid_link_timestamp",
                                "Sorting timestamp is timezone-naive",
                                (event.id, spec.timestamp_key),
                            ),
                        ),
                    )
                try:
                    instant = timestamp.value.astimezone(timezone.utc)
                except (OverflowError, ValueError):
                    return finish(
                        ComputeStatus.INVALID_INPUT,
                        issues=(
                            ComputeIssue(
                                "invalid_link_timestamp",
                                "Sorting timestamp cannot be represented in UTC",
                                (event.id, spec.timestamp_key),
                            ),
                        ),
                    )
                keys = []
                for direction, scope, key in (
                    ("out", spec.out_scope, spec.out_key),
                    ("in", spec.in_scope, spec.in_key),
                ):
                    if scope == "case_id":
                        token, reason = ("id", trace.id), None
                    else:
                        selected = attrs if scope == "event" else trace_attrs
                        token, reason = _token(selected.get(key))
                    keys.append(token)
                    if reason:
                        exclusions.append(
                            LinkEndpointExclusion(
                                event.id, direction, scope, key, reason
                            )
                        )
                rows.append(
                    (
                        instant,
                        len(rows),
                        trace_index,
                        event_index,
                        trace.id,
                        event.id,
                        keys,
                    )
                )
        rows.sort(key=lambda row: (row[0], row[1]))
        events = tuple(
            LinkEventReference(row[5], row[4], row[2], row[3], row[1], rank, row[0])
            for rank, row in enumerate(rows)
        )
        buckets = {}
        for rank, row in enumerate(rows):
            incoming = row[6][1]
            if incoming is not None:
                buckets.setdefault(incoming, []).append(rank)

        adjacency = []
        candidates = direct_count = work = 0
        for source, row in enumerate(rows):
            targets = buckets.get(row[6][0], ())
            start = bisect_right(targets, source) if spec.look_forward else 0
            candidates += len(targets) - start
            stop = (
                min(start + 1, len(targets))
                if spec.keep_first_occurrence
                else len(targets)
            )
            size = stop - start
            direct_count += size
            work += size
            _limit("max_links", direct_count, spec.max_links)
            _limit("max_work", work, spec.max_work)
            adjacency.append(tuple(targets[start:stop]))

        links = []
        witness_count = 0

        def append(source, target, path, direct):
            links.append(
                EventLink(
                    events[source].event_id,
                    events[target].event_id,
                    source,
                    target,
                    direct,
                    tuple(events[i].event_id for i in path),
                    path,
                )
            )

        for source, direct_targets in enumerate(adjacency):
            if not spec.propagate:
                for target in direct_targets:
                    witness_count += 2
                    _limit("max_witness_events", witness_count, spec.max_witness_events)
                    append(source, target, (source, target), True)
                continue
            # First discovery in BFS selects a shortest path. Neighbors retain
            # global input-stable order; neither dict/set nor IDs choose a tie.
            predecessors = {source: None}
            distances = {source: 0}
            queue = deque([source])
            reached = {}
            while queue:
                current = queue.popleft()
                for target in adjacency[current]:
                    work += 1
                    _limit("max_work", work, spec.max_work)
                    if target in reached:
                        continue
                    length = distances[current] + 2
                    _limit("max_links", len(links) + len(reached) + 1, spec.max_links)
                    witness_count += length
                    _limit("max_witness_events", witness_count, spec.max_witness_events)
                    reached[target] = current
                    if target != source:
                        predecessors[target] = current
                        distances[target] = distances[current] + 1
                        queue.append(target)
            direct_set = set(direct_targets)
            for target in sorted(reached):
                # A self pair must append the source to a nonempty cycle path.
                path = _path(predecessors, reached[target]) + (target,)
                append(source, target, path, target in direct_set)
        issues = ()
        if exclusions:
            issues = (
                ComputeIssue(
                    "ineligible_link_endpoints",
                    f"{len(exclusions)} endpoints excluded; see payload exclusions",
                ),
            )
        return finish(
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
            LinkAnalysisPayload(
                events,
                tuple(links),
                tuple(exclusions),
                candidates,
                direct_count,
                len(links) - direct_count,
                work,
                witness_count,
            ),
            issues,
        )
    except _LimitReached as exc:
        return finish(ComputeStatus.UNAVAILABLE, issues=(exc.issue,))
    except ValueError as exc:
        return finish(
            ComputeStatus.INVALID_INPUT,
            issues=(ComputeIssue("ambiguous_link_attribute", str(exc)),),
        )


RESULT_SCHEMAS = {
    OPERATOR_ID: ("case_link_analysis", LinkAnalysisSpec, LinkAnalysisPayload),
}

__all__ = [
    "LinkAnalysisSpec",
    "LinkEventReference",
    "LinkEndpointExclusion",
    "EventLink",
    "LinkAnalysisPayload",
    "discover_link_analysis",
]
