"""Native case-centric organizational calculations with explicit populations.

No upstream package is imported. Source order defines handover, not causality.
Missing resource events retain their positions: A, missing, B is never rewritten
to A, B. Temporal profiles use half-open intervals and preserve duplicate work.
Names describe PIX formulas; documented upstream defects are not emulated.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite, sqrt
from typing import ClassVar

from pix.compute._common import _result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseEvent, CaseLog, case_log_digest


def _key(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _unit(value: object, name: str) -> None:
    if type(value) not in (int, float) or not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be finite and between zero and one")


def _names(values: object, name: str) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    for value in values:
        _key(value, name)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must not contain duplicates")


def _text(log: CaseLog, event: CaseEvent, key: str) -> str | None:
    attribute = log.attribute(event, key)
    return (
        attribute.value
        if attribute is not None
        and attribute.type in ("string", "id")
        and attribute.value.strip()
        else None
    )


def _date(log: CaseLog, event: CaseEvent, key: str) -> datetime | None:
    attribute = log.attribute(event, key)
    if (
        attribute is None
        or attribute.type != "date"
        or attribute.value.utcoffset() is None
    ):
        return None
    return attribute.value.astimezone(timezone.utc)


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _finish(log, spec, operator, value, issues=()):
    return _result(
        operator,
        None,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
        source_digest=case_log_digest(log),
    )


def _invalid(log, spec, operator, exc):
    return _result(
        operator,
        None,
        spec,
        ComputeStatus.INVALID_INPUT,
        None,
        (ComputeIssue("ambiguous_attribute", str(exc)),),
        source_digest=case_log_digest(log),
    )


def _check(log, spec, expected):
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, expected):
        raise TypeError(f"spec must be {expected.__name__}")


@dataclass(frozen=True, slots=True)
class SocialNetworkSpec:
    """Metric normalization: handover/all valid pair weight; together and
    subcontracting/all cases; joint activities/Pearson or cosine.

    Other normalizations: raw, cases, opportunities (including missing resource
    positions), source (outgoing edge sum), max_abs (largest raw absolute value).
    Handover distance d weighs beta**(d-1); a subcontracting return at distance d
    weighs beta**(d-2) for EACH intervening occurrence. max_distance=None searches
    the whole case. A zero beta retains direct handover / distance-two returns.
    """

    metric: str = "handover"
    resource_key: str = "org:resource"
    activity_key: str = "concept:name"
    normalization: str = "metric"
    include_self: bool = False
    beta: float = 0.0
    max_distance: int | None = 2
    similarity: str = "pearson"
    resources: tuple[str, ...] = ()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.metric not in (
            "handover",
            "working_together",
            "subcontracting",
            "joint_activities",
        ):
            raise ValueError("unsupported social network metric")
        if self.normalization not in (
            "metric",
            "raw",
            "cases",
            "opportunities",
            "source",
            "max_abs",
        ):
            raise ValueError("unsupported network normalization")
        if self.metric == "joint_activities" and self.normalization not in (
            "metric",
            "raw",
            "max_abs",
        ):
            raise ValueError("similarity supports metric, raw or max_abs normalization")
        if self.normalization == "source" and self.metric not in (
            "handover",
            "subcontracting",
        ):
            raise ValueError("source normalization requires a directed metric")
        if self.similarity not in ("pearson", "cosine"):
            raise ValueError("similarity must be pearson or cosine")
        if type(self.include_self) is not bool:
            raise TypeError("include_self must be bool")
        _unit(self.beta, "beta")
        object.__setattr__(self, "beta", float(self.beta))
        if self.max_distance is not None and (
            type(self.max_distance) is not int or self.max_distance < 1
        ):
            raise ValueError("max_distance must be positive int or None")
        if self.metric == "subcontracting" and self.max_distance == 1:
            raise ValueError("subcontracting needs return distance at least two")
        _key(self.resource_key, "resource_key")
        _key(self.activity_key, "activity_key")
        _names(self.resources, "resources")


@dataclass(frozen=True, slots=True)
class NetworkEdge:
    source: str
    target: str
    raw_weight: float | None
    weight: float | None
    observation_count: int
    denominator: float | None


@dataclass(frozen=True, slots=True)
class NetworkPayload:
    metric: str
    normalization: str
    directed: bool
    resources: tuple[str, ...]
    activities: tuple[str, ...]
    edges: tuple[NetworkEdge, ...]
    case_count: int
    event_count: int
    missing_resource_count: int
    missing_activity_count: int
    opportunity_weight: float
    eligible_pair_weight: float


def discover_social_network(
    log: CaseLog, spec: SocialNetworkSpec = SocialNetworkSpec()
) -> ComputationResult[NetworkPayload]:
    """Weighted resource relations; undefined constant-vector similarity is None.

    Undirected metrics store each unordered pair once in lexical orientation.
    Activity counts are collected only for joint activities. Missing fields
    required by the selected calculation make it partial.
    """
    _check(log, spec, SocialNetworkSpec)
    operator = "pix.case_centric.discover_social_network"
    resources = set(spec.resources)
    activities = set()
    vectors = defaultdict(Counter)
    sequences = []
    missing_resource = missing_activity = event_count = 0
    try:
        for trace in log.traces:
            sequence = []
            for event in trace.events:
                resource = _text(log, event, spec.resource_key)
                activity = (
                    _text(log, event, spec.activity_key)
                    if spec.metric == "joint_activities"
                    else None
                )
                event_count += 1
                missing_resource += resource is None
                missing_activity += (
                    spec.metric == "joint_activities" and activity is None
                )
                sequence.append(resource)
                if resource is not None:
                    resources.add(resource)
                if activity is not None:
                    activities.add(activity)
                if resource is not None and activity is not None:
                    vectors[resource][activity] += 1
            sequences.append(sequence)
    except ValueError as exc:
        return _invalid(log, spec, operator, exc)
    nodes = tuple(sorted(resources))
    alphabet = tuple(sorted(activities))
    raw = defaultdict(float)
    counts = Counter()
    opportunity = eligible = 0.0
    if spec.metric in ("handover", "subcontracting"):
        for sequence in sequences:
            for i, first in enumerate(sequence):
                limit = (
                    len(sequence)
                    if spec.max_distance is None
                    else min(len(sequence), i + spec.max_distance + 1)
                )
                for k in range(i + (1 if spec.metric == "handover" else 2), limit):
                    distance = k - i
                    power = distance - (1 if spec.metric == "handover" else 2)
                    weight = float(spec.beta**power)
                    if not weight:
                        continue
                    if spec.metric == "handover":
                        opportunity += weight
                        last = sequence[k]
                        if first is None or last is None:
                            continue
                        eligible += weight
                        if spec.include_self or first != last:
                            raw[first, last] += weight
                            counts[first, last] += 1
                    else:
                        for j in range(i + 1, k):
                            opportunity += weight
                            middle, last = sequence[j], sequence[k]
                            if first is None or middle is None or last is None:
                                continue
                            eligible += weight
                            if first == last and (spec.include_self or first != middle):
                                raw[first, middle] += weight
                                counts[first, middle] += 1
    elif spec.metric == "working_together":
        opportunity = float(len(sequences))
        eligible = float(sum(any(item is not None for item in s) for s in sequences))
        for sequence in sequences:
            participants = sorted(set(sequence) - {None})
            for i, first in enumerate(participants):
                for last in participants[i if spec.include_self else i + 1 :]:
                    raw[first, last] += 1.0
                    counts[first, last] += 1
    else:
        for i, first in enumerate(nodes):
            for last in nodes[i if spec.include_self else i + 1 :]:
                left = [float(vectors[first][a]) for a in alphabet]
                right = [float(vectors[last][a]) for a in alphabet]
                if spec.similarity == "pearson" and alphabet:
                    ml, mr = sum(left) / len(left), sum(right) / len(right)
                    left, right = [x - ml for x in left], [x - mr for x in right]
                norm = sqrt(sum(x * x for x in left) * sum(x * x for x in right))
                dot = sum(x * y for x, y in zip(left, right))
                raw[first, last] = max(-1.0, min(1.0, dot / norm)) if norm else None
                counts[first, last] = len(alphabet)
                opportunity += 1
                eligible += bool(norm)
    normalization = spec.normalization
    if normalization == "metric":
        normalization = (
            "eligible_pairs"
            if spec.metric == "handover"
            else "raw"
            if spec.metric == "joint_activities"
            else "cases"
        )
    maximum = max((abs(w) for w in raw.values() if w is not None), default=0.0)
    outgoing = defaultdict(float)
    for (first, _), weight in raw.items():
        if weight is not None:
            outgoing[first] += weight
    edges = []
    for (first, last), weight in sorted(raw.items()):
        denominator = {
            "raw": 1.0,
            "eligible_pairs": eligible,
            "cases": float(len(sequences)),
            "opportunities": opportunity,
            "source": outgoing[first],
            "max_abs": maximum,
        }[normalization]
        edges.append(
            NetworkEdge(
                first,
                last,
                weight,
                _ratio(weight, denominator) if weight is not None else None,
                counts[first, last],
                denominator,
            )
        )
    issues = []
    if missing_resource:
        issues.append(
            ComputeIssue(
                "missing_resource",
                f"{missing_resource} event positions lack a usable resource; no sequence bridging was performed.",
            )
        )
    if spec.metric == "joint_activities" and missing_activity:
        issues.append(
            ComputeIssue(
                "missing_activity",
                f"{missing_activity} events lack a usable activity; feature counts have incomplete coverage.",
            )
        )
    undefined = sum(edge.weight is None for edge in edges)
    if undefined:
        issues.append(
            ComputeIssue(
                "undefined_weight",
                f"{undefined} edges have a zero normalization denominator or zero-variance/norm vector.",
            )
        )
    payload = NetworkPayload(
        spec.metric,
        normalization,
        spec.metric in ("handover", "subcontracting"),
        nodes,
        alphabet,
        tuple(edges),
        len(sequences),
        event_count,
        missing_resource,
        missing_activity,
        opportunity,
        eligible,
    )
    return _finish(log, spec, operator, payload, issues)


@dataclass(frozen=True, slots=True)
class RoleDiscoverySpec:
    resource_key: str = "org:resource"
    activity_key: str = "concept:name"
    threshold: float = 0.65
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _key(self.resource_key, "resource_key")
        _key(self.activity_key, "activity_key")
        _unit(self.threshold, "threshold")
        object.__setattr__(self, "threshold", float(self.threshold))


@dataclass(frozen=True, slots=True)
class OrganizationalRole:
    activities: tuple[str, ...]
    resource_counts: tuple[tuple[str, int], ...]
    event_count: int


@dataclass(frozen=True, slots=True)
class RoleMerge:
    left: tuple[str, ...]
    right: tuple[str, ...]
    similarity: float


@dataclass(frozen=True, slots=True)
class RoleSet:
    roles: tuple[OrganizationalRole, ...]
    merges: tuple[RoleMerge, ...]
    event_count: int
    eligible_event_count: int
    missing_resource_count: int
    missing_activity_count: int
    unsupported_activities: tuple[str, ...]


def discover_roles(
    log: CaseLog, spec: RoleDiscoverySpec = RoleDiscoverySpec()
) -> ComputationResult[RoleSet]:
    """Agglomerate activity roles using normalized multiset Jaccard similarity.

    A merge requires similarity > threshold, strictly. Counts are summed before
    re-normalizing. Equal maxima use activity first-appearance order; resource
    names never choose a merge. Activities without resources remain singleton.
    """
    _check(log, spec, RoleDiscoverySpec)
    operator = "pix.case_centric.discover_roles"
    profiles = {}
    missing_resource = missing_activity = events = eligible = 0
    try:
        for trace in log.traces:
            for event in trace.events:
                resource = _text(log, event, spec.resource_key)
                activity = _text(log, event, spec.activity_key)
                events += 1
                missing_resource += resource is None
                missing_activity += activity is None
                if activity is not None:
                    profiles.setdefault(activity, Counter())
                    if resource is not None:
                        profiles[activity][resource] += 1
                        eligible += 1
    except ValueError as exc:
        return _invalid(log, spec, operator, exc)
    roles = [((activity,), counts) for activity, counts in profiles.items()]
    merges = []
    while len(roles) > 1:
        best = None
        for i, (_, left) in enumerate(roles):
            for j in range(i + 1, len(roles)):
                right = roles[j][1]
                nl, nr = sum(left.values()), sum(right.values())
                if not nl or not nr:
                    continue
                keys = left.keys() | right.keys()
                # Integer cross-products give the same ratio as two L1 vectors.
                intersection = sum(min(left[r] * nr, right[r] * nl) for r in keys)
                union = sum(max(left[r] * nr, right[r] * nl) for r in keys)
                score = intersection / union
                if score > spec.threshold and (best is None or score > best[0]):
                    best = score, i, j
        if best is None:
            break
        score, i, j = best
        left, right = roles[i], roles[j]
        merges.append(RoleMerge(left[0], right[0], score))
        roles[i] = (left[0] + right[0], left[1] + right[1])
        del roles[j]
    issues = []
    if missing_resource or missing_activity:
        issues.append(
            ComputeIssue(
                "incomplete_role_population",
                f"{missing_resource} missing resources and {missing_activity} missing activities; {eligible}/{events} events contribute to role vectors.",
            )
        )
    payload = RoleSet(
        tuple(
            OrganizationalRole(
                tuple(activities), tuple(sorted(counts.items())), sum(counts.values())
            )
            for activities, counts in roles
        ),
        tuple(merges),
        events,
        eligible,
        missing_resource,
        missing_activity,
        tuple(activity for activity, counts in profiles.items() if not counts),
    )
    return _finish(log, spec, operator, payload, issues)


@dataclass(frozen=True, slots=True)
class OrganizationalGroup:
    name: str
    resources: tuple[str, ...]

    def __post_init__(self):
        _key(self.name, "group name")
        _names(self.resources, "group resources")


@dataclass(frozen=True, slots=True)
class OrganizationDiagnosticsSpec:
    groups: tuple[OrganizationalGroup, ...] = ()
    resource_key: str = "org:resource"
    activity_key: str = "concept:name"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _key(self.resource_key, "resource_key")
        _key(self.activity_key, "activity_key")
        if not isinstance(self.groups, tuple) or any(
            not isinstance(g, OrganizationalGroup) for g in self.groups
        ):
            raise TypeError("groups must be a tuple of OrganizationalGroup")
        if len({g.name for g in self.groups}) != len(self.groups):
            raise ValueError("group names must be unique")


@dataclass(frozen=True, slots=True)
class GroupActivityDiagnostic:
    group: str
    activity: str
    event_count: int
    group_event_count: int
    activity_event_count: int
    member_count: int
    active_member_count: int
    focus: float | None
    stake: float | None
    coverage: float | None
    member_counts: tuple[tuple[str, int], ...]
    member_contribution: tuple[tuple[str, float | None], ...]


@dataclass(frozen=True, slots=True)
class DiagnosticsPayload:
    activities: tuple[str, ...]
    diagnostics: tuple[GroupActivityDiagnostic, ...]
    group_resource_event_shares: tuple[
        tuple[str, tuple[tuple[str, float | None], ...]], ...
    ]
    event_count: int
    missing_resource_count: int
    missing_activity_count: int
    overlapping_resources: tuple[str, ...]


def measure_organization(
    log: CaseLog, spec: OrganizationDiagnosticsSpec = OrganizationDiagnosticsSpec()
) -> ComputationResult[DiagnosticsPayload]:
    """Focus=n(g,a)/n(g,*), stake=n(g,a)/n(*,a), coverage=active/declared members.

    Missing resource events still enter the global activity denominator; missing
    activity events still enter a known member's group denominator. Overlapping
    groups are evaluated independently, never forced to sum to one.
    """
    _check(log, spec, OrganizationDiagnosticsSpec)
    operator = "pix.case_centric.measure_organization"
    activity_counts, resource_counts, matrix = Counter(), Counter(), Counter()
    missing_resource = missing_activity = events = 0
    try:
        for trace in log.traces:
            for event in trace.events:
                resource = _text(log, event, spec.resource_key)
                activity = _text(log, event, spec.activity_key)
                events += 1
                missing_resource += resource is None
                missing_activity += activity is None
                if resource is not None:
                    resource_counts[resource] += 1
                if activity is not None:
                    activity_counts[activity] += 1
                if resource is not None and activity is not None:
                    matrix[resource, activity] += 1
    except ValueError as exc:
        return _invalid(log, spec, operator, exc)
    diagnostics, shares = [], []
    membership = Counter(r for g in spec.groups for r in g.resources)
    for group in spec.groups:
        total = sum(resource_counts[r] for r in group.resources)
        shares.append(
            (
                group.name,
                tuple((r, _ratio(resource_counts[r], total)) for r in group.resources),
            )
        )
        for activity in sorted(activity_counts):
            counts = tuple((r, matrix[r, activity]) for r in group.resources)
            number = sum(c for _, c in counts)
            active = sum(c > 0 for _, c in counts)
            diagnostics.append(
                GroupActivityDiagnostic(
                    group.name,
                    activity,
                    number,
                    total,
                    activity_counts[activity],
                    len(group.resources),
                    active,
                    _ratio(number, total),
                    _ratio(number, activity_counts[activity]),
                    _ratio(active, len(group.resources)),
                    counts,
                    tuple((r, _ratio(c, number)) for r, c in counts),
                )
            )
    issues = []
    if missing_resource or missing_activity:
        issues.append(
            ComputeIssue(
                "incomplete_organization_population",
                f"{missing_resource} missing resources and {missing_activity} missing activities; global/group denominators retain independently usable facts.",
            )
        )
    return _finish(
        log,
        spec,
        operator,
        DiagnosticsPayload(
            tuple(sorted(activity_counts)),
            tuple(diagnostics),
            tuple(shares),
            events,
            missing_resource,
            missing_activity,
            tuple(sorted(r for r, n in membership.items() if n > 1)),
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class ResourceProfileSpec:
    resource_key: str = "org:resource"
    activity_key: str = "concept:name"
    timestamp_key: str = "time:timestamp"
    start_timestamp_key: str = "start:timestamp"
    start_policy: str = "explicit"
    window_start: datetime | None = None
    window_end: datetime | None = None
    resources: tuple[str, ...] = ()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in (
            "resource_key",
            "activity_key",
            "timestamp_key",
            "start_timestamp_key",
        ):
            _key(getattr(self, name), name)
        if self.start_policy not in ("explicit", "previous_event"):
            raise ValueError("start_policy must be explicit or previous_event")
        _names(self.resources, "resources")
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("both window boundaries are required")
        for value in (self.window_start, self.window_end):
            if value is not None and (
                not isinstance(value, datetime) or value.utcoffset() is None
            ):
                raise ValueError("window timestamps must be timezone-aware")
        if self.window_start is not None:
            object.__setattr__(
                self, "window_start", self.window_start.astimezone(timezone.utc)
            )
            object.__setattr__(
                self, "window_end", self.window_end.astimezone(timezone.utc)
            )
        if self.window_start is not None and self.window_start >= self.window_end:
            raise ValueError("window must have positive duration")


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    resource: str
    event_count: int
    activity_counts: tuple[tuple[str, int], ...]
    event_fraction: float | None
    participated_case_count: int
    completed_case_count: int
    completed_case_fraction: float | None
    case_participation_fraction: float | None
    coworker_count: int
    coworker_fraction: float | None
    activity_duration_count: int
    mean_activity_duration_seconds: float | None
    observed_case_span_count: int
    mean_observed_case_span_seconds: float | None
    interval_count: int
    inferred_interval_count: int
    effort_seconds: float
    busy_seconds: float
    multitasking_seconds: float
    peak_concurrent_activities: int
    average_workload: float | None
    busy_average_workload: float | None
    multitasking_fraction: float | None


@dataclass(frozen=True, slots=True)
class ResourceInteraction:
    left: str
    right: str
    shared_case_count: int
    case_fraction: float | None


@dataclass(frozen=True, slots=True)
class ResourceProfiles:
    profiles: tuple[ResourceProfile, ...]
    interactions: tuple[ResourceInteraction, ...]
    event_count: int
    selected_event_count: int
    selected_case_count: int
    completed_case_population: int
    missing_resource_count: int
    missing_activity_count: int
    missing_completion_count: int
    missing_start_count: int
    invalid_interval_count: int
    incomplete_case_time_count: int
    workload_window_start: datetime | None
    workload_window_end: datetime | None
    workload_window_seconds: float | None


def _occupancy(intervals, start, end):
    """Integrate event multiplicity over [start,end), retaining duplicate intervals."""
    if start is None or end is None:
        return 0, 0.0, 0.0, 0.0, 0
    changes = Counter()
    number = 0
    for left, right, _ in intervals:
        left, right = max(left, start), min(right, end)
        if left < right:
            changes[left] += 1
            changes[right] -= 1
            number += 1
    active = peak = 0
    effort = busy = multi = 0.0
    previous = start
    for instant, delta in sorted(changes.items()):
        duration = (instant - previous).total_seconds()
        effort += active * duration
        busy += duration if active else 0.0
        multi += duration if active >= 2 else 0.0
        active += delta
        peak = max(peak, active)
        previous = instant
    return number, effort, busy, multi, peak


def measure_resource_profiles(
    log: CaseLog, spec: ResourceProfileSpec = ResourceProfileSpec()
) -> ComputationResult[ResourceProfiles]:
    """Counts, cooperation and observed temporal occupation for every resource.

    Completion selection uses [window_start,window_end); no window selects all
    events for nontemporal counts. A complete case-time population requires every
    event to have a usable completion. Its observed span is max(end)-min(end), not
    service time. Case completion means the last OBSERVED timestamp, not an asserted
    business terminal state. Workload=sum clipped durations/window duration;
    busy workload=sum durations/union busy time; multitasking=time(n>=2)/time(n>=1).
    An omitted window uses the global observed interval extent, including idle
    time between observed intervals. Explicit resources include zero-work members.
    """
    _check(log, spec, ResourceProfileSpec)
    operator = "pix.case_centric.measure_resource_profiles"
    nodes = set(spec.resources)
    event_counts, activity_counts = Counter(), defaultdict(Counter)
    intervals, durations, spans = (
        defaultdict(list),
        defaultdict(list),
        defaultdict(list),
    )
    participated, completed = defaultdict(set), defaultdict(set)
    selected_participants = []
    events = selected_events = selected_cases = complete_population = 0
    missing_resource = missing_activity = missing_end = missing_start = invalid = (
        incomplete_cases
    ) = 0

    def selected(instant):
        return spec.window_start is None or (
            instant is not None and spec.window_start <= instant < spec.window_end
        )

    try:
        for trace in log.traces:
            case_resources, case_selected_resources, endings = set(), set(), []
            case_has_selected = False
            previous_end = None
            for event in trace.events:
                resource = _text(log, event, spec.resource_key)
                activity = _text(log, event, spec.activity_key)
                end = _date(log, event, spec.timestamp_key)
                start = _date(log, event, spec.start_timestamp_key)
                start_fact = log.attribute(event, spec.start_timestamp_key)
                events += 1
                missing_resource += resource is None
                missing_activity += activity is None
                missing_end += end is None
                if end is not None:
                    endings.append(end)
                if resource is not None:
                    nodes.add(resource)
                    case_resources.add(resource)
                if selected(end):
                    selected_events += 1
                    case_has_selected = True
                    if resource is not None:
                        event_counts[resource] += 1
                        case_selected_resources.add(resource)
                        participated[resource].add(trace.id)
                        if activity is not None:
                            activity_counts[resource][activity] += 1
                inferred = False
                if (
                    start is None
                    and start_fact is None
                    and spec.start_policy == "previous_event"
                ):
                    start = previous_end
                    inferred = start is not None
                if resource is not None:
                    if start is None:
                        missing_start += 1
                    elif end is not None:
                        if start > end:
                            invalid += 1
                        else:
                            intervals[resource].append((start, end, inferred))
                            if selected(end):
                                durations[resource].append(
                                    (end - start).total_seconds()
                                )
                previous_end = end  # Missing event times never bridge a gap.
            if case_has_selected:
                selected_cases += 1
                selected_participants.append(case_selected_resources)
            if trace.events and len(endings) != len(trace.events):
                incomplete_cases += 1
            if (
                trace.events
                and len(endings) == len(trace.events)
                and selected(max(endings))
            ):
                complete_population += 1
                for resource in case_resources:
                    completed[resource].add(trace.id)
                    spans[resource].append(
                        (max(endings) - min(endings)).total_seconds()
                    )
    except ValueError as exc:
        return _invalid(log, spec, operator, exc)
    all_intervals = [
        item for resource_intervals in intervals.values() for item in resource_intervals
    ]
    start = spec.window_start
    end = spec.window_end
    if start is None and all_intervals:
        start = min(item[0] for item in all_intervals)
        end = max(item[1] for item in all_intervals)
    window_seconds = (end - start).total_seconds() if start is not None else None
    interaction_counts, coworkers = Counter(), defaultdict(set)
    for participants in selected_participants:
        ordered = sorted(participants)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                interaction_counts[left, right] += 1
                coworkers[left].add(right)
                coworkers[right].add(left)
    profiles = []
    for resource in sorted(nodes):
        number, effort, busy, multi, peak = _occupancy(intervals[resource], start, end)
        inferred = sum(
            flag and start is not None and max(left, start) < min(right, end)
            for left, right, flag in intervals[resource]
        )
        duration_values, span_values = durations[resource], spans[resource]
        profiles.append(
            ResourceProfile(
                resource,
                event_counts[resource],
                tuple(sorted(activity_counts[resource].items())),
                _ratio(event_counts[resource], selected_events),
                len(participated[resource]),
                len(completed[resource]),
                _ratio(len(completed[resource]), complete_population),
                _ratio(len(participated[resource]), selected_cases),
                len(coworkers[resource]),
                _ratio(len(coworkers[resource]), len(nodes) - 1),
                len(duration_values),
                _ratio(sum(duration_values), len(duration_values)),
                len(span_values),
                _ratio(sum(span_values), len(span_values)),
                number,
                inferred,
                effort,
                busy,
                multi,
                peak,
                _ratio(effort, window_seconds) if window_seconds is not None else None,
                _ratio(effort, busy),
                _ratio(multi, busy),
            )
        )
    interactions = tuple(
        ResourceInteraction(a, b, count, _ratio(count, selected_cases))
        for (a, b), count in sorted(interaction_counts.items())
    )
    issues = []
    for code, number, message in (
        ("missing_resource", missing_resource, "events lack a usable resource"),
        ("missing_activity", missing_activity, "events lack a usable activity"),
        (
            "missing_completion",
            missing_end,
            "events lack timezone-aware completion timestamps",
        ),
        (
            "missing_start",
            missing_start,
            "resource events have no usable selected start",
        ),
        ("invalid_interval", invalid, "resource intervals have start after completion"),
        (
            "incomplete_case_time",
            incomplete_cases,
            "nonempty cases have incomplete completion times",
        ),
    ):
        if number:
            issues.append(
                ComputeIssue(
                    code,
                    f"{number} {message}; affected temporal populations are explicit in the payload.",
                )
            )
    return _finish(
        log,
        spec,
        operator,
        ResourceProfiles(
            tuple(profiles),
            interactions,
            events,
            selected_events,
            selected_cases,
            complete_population,
            missing_resource,
            missing_activity,
            missing_end,
            missing_start,
            invalid,
            incomplete_cases,
            start,
            end,
            window_seconds,
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class AttributeNetworkSpec:
    """Forward attribute links, then node/edge grouping and duration aggregation.

    No in/out keys means native case identity; both keys select string/id event
    values and may link events across cases. `first` chooses the first matching
    future event before testing node attributes, so missing nodes never redirect
    a link. Timestamp ties use source order explicitly, not a causal inference.
    A fixed-offset weekly business calendar is optional; slots count seconds from
    Monday 00:00. Named-zone DST calendars are outside this profile.
    """

    source_node_key: str = "org:resource"
    target_node_key: str = "org:resource"
    edge_key: str = "concept:name"
    edge_reference: str = "source"
    out_key: str | None = None
    in_key: str | None = None
    order: str = "source"
    timestamp_key: str = "time:timestamp"
    selection: str = "first"
    include_performance: bool = True
    weekly_slots: tuple[tuple[int, int], ...] | None = None
    calendar_utc_offset_minutes: int = 0
    excluded_dates: tuple[str, ...] = ()
    max_links: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("source_node_key", "target_node_key", "edge_key", "timestamp_key"):
            _key(getattr(self, name), name)
        if (self.out_key is None) != (self.in_key is None):
            raise ValueError("both in_key and out_key are required for attribute joins")
        if self.out_key is not None:
            _key(self.out_key, "out_key")
            _key(self.in_key, "in_key")
        if self.order not in ("source", "timestamp") or self.selection not in (
            "first",
            "all",
        ):
            raise ValueError("unsupported link ordering or selection")
        if self.edge_reference not in ("source", "target"):
            raise ValueError("edge_reference must be source or target")
        if type(self.include_performance) is not bool:
            raise TypeError("include_performance must be bool")
        if type(self.max_links) is not int or self.max_links < 1:
            raise ValueError("max_links must be positive int")
        if (
            type(self.calendar_utc_offset_minutes) is not int
            or abs(self.calendar_utc_offset_minutes) >= 1440
        ):
            raise ValueError(
                "calendar offset must be integer minutes strictly within 24 hours"
            )
        _names(self.excluded_dates, "excluded_dates")
        for date in self.excluded_dates:
            parsed = datetime.strptime(date, "%Y-%m-%d")
            if parsed.date().isoformat() != date:
                raise ValueError("excluded dates must use YYYY-MM-DD")
        if self.weekly_slots is not None:
            if not isinstance(self.weekly_slots, tuple):
                raise TypeError("weekly_slots must be a tuple")
            for slot in self.weekly_slots:
                if (
                    not isinstance(slot, tuple)
                    or len(slot) != 2
                    or any(type(v) is not int for v in slot)
                    or not 0 <= slot[0] < slot[1] <= 604800
                ):
                    raise ValueError(
                        "weekly slots must be integer half-open second ranges in one week"
                    )
            ordered = sorted(self.weekly_slots)
            if any(left[1] > right[0] for left, right in zip(ordered, ordered[1:])):
                raise ValueError("weekly slots must not overlap")
        elif self.excluded_dates or self.calendar_utc_offset_minutes:
            raise ValueError("calendar options require weekly_slots")


@dataclass(frozen=True, slots=True)
class AttributeLink:
    source_event: str
    target_event: str
    source_node: str
    target_node: str
    edge_value: str
    duration_seconds: float | None


@dataclass(frozen=True, slots=True)
class AttributeNetworkEdge:
    source: str
    target: str
    edge_value: str
    count: int
    timed_count: int
    mean_seconds: float | None
    total_seconds: float | None
    minimum_seconds: float | None
    maximum_seconds: float | None


@dataclass(frozen=True, slots=True)
class AttributeNetwork:
    edges: tuple[AttributeNetworkEdge, ...]
    links: tuple[AttributeLink, ...]
    event_count: int
    candidate_link_count: int
    missing_link_attribute_count: int
    excluded_node_or_edge_link_count: int
    unavailable_duration_count: int
    timestamp_tie_count: int


def _business_duration(start, end, spec):
    if spec.weekly_slots is None:
        return (end - start).total_seconds()
    anchor = datetime(1970, 1, 5, tzinfo=timezone.utc)
    offset = spec.calendar_utc_offset_minutes * 60000000

    def microseconds(delta):
        return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds

    left = microseconds(start - anchor) + offset
    right = microseconds(end - anchor) + offset
    slots = tuple((a * 1000000, b * 1000000) for a, b in spec.weekly_slots)
    weekly_total = sum(b - a for a, b in slots)

    def accumulated(instant):
        weeks, remainder = divmod(instant, 604800000000)
        return weeks * weekly_total + sum(
            max(0, min(remainder, b) - a) for a, b in slots
        )

    value = accumulated(right) - accumulated(left)
    for date in spec.excluded_dates:
        day = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        day_left = microseconds(day - anchor)
        a, b = max(left, day_left), min(right, day_left + 86400000000)
        if a < b:
            value -= accumulated(b) - accumulated(a)
    return value / 1000000


def discover_attribute_network(
    log: CaseLog, spec: AttributeNetworkSpec = AttributeNetworkSpec()
) -> ComputationResult[AttributeNetwork]:
    """Join forward event outputs to inputs, retaining event-pair witnesses.

    A timestamp ordering request with missing timestamps returns unavailable;
    frequency-only source ordering does not require timestamps. A link budget
    failure returns no truncated network and reports the bound explicitly.
    """
    _check(log, spec, AttributeNetworkSpec)
    operator = "pix.case_centric.discover_attribute_network"
    records, missing_link, times = [], 0, []
    try:
        for trace in log.traces:
            for event in trace.events:
                out = _text(log, event, spec.out_key) if spec.out_key else trace.id
                into = _text(log, event, spec.in_key) if spec.in_key else trace.id
                instant = (
                    _date(log, event, spec.timestamp_key)
                    if spec.include_performance or spec.order == "timestamp"
                    else None
                )
                missing_link += out is None or into is None
                records.append((event, out, into, instant))
                if instant is not None:
                    times.append(instant)
        if spec.order == "timestamp":
            if len(times) != len(records):
                return _result(
                    operator,
                    None,
                    spec,
                    ComputeStatus.UNAVAILABLE,
                    None,
                    (
                        ComputeIssue(
                            "unknown_timestamp_order",
                            f"{len(records) - len(times)} event timestamps are unusable; a global timestamp order cannot be established.",
                        ),
                    ),
                    source_digest=case_log_digest(log),
                )
            records.sort(key=lambda row: row[3])  # stable: source order breaks ties
        positions = defaultdict(list)
        for i, (_, _, into, _) in enumerate(records):
            if into is not None:
                positions[into].append(i)
        candidates = excluded = unavailable = 0
        links = []
        aggregates = defaultdict(list)
        for i, (source, out, _, source_time) in enumerate(records):
            if out is None:
                continue
            targets = positions[out]
            offset = bisect_right(targets, i)
            stop = (
                min(offset + 1, len(targets))
                if spec.selection == "first"
                else len(targets)
            )
            for target_position in range(offset, stop):
                j = targets[target_position]
                candidates += 1
                if candidates > spec.max_links:
                    return _result(
                        operator,
                        None,
                        spec,
                        ComputeStatus.UNAVAILABLE,
                        None,
                        (
                            ComputeIssue(
                                "link_budget_exceeded",
                                f"Forward attribute links exceed max_links={spec.max_links}; no incomplete network is returned.",
                            ),
                        ),
                        source_digest=case_log_digest(log),
                    )
                target, _, _, target_time = records[j]
                a = _text(log, source, spec.source_node_key)
                b = _text(log, target, spec.target_node_key)
                label = _text(
                    log,
                    source if spec.edge_reference == "source" else target,
                    spec.edge_key,
                )
                if a is None or b is None or label is None:
                    excluded += 1
                    continue
                duration = None
                if spec.include_performance:
                    if (
                        source_time is None
                        or target_time is None
                        or target_time < source_time
                    ):
                        unavailable += 1
                    else:
                        duration = _business_duration(source_time, target_time, spec)
                links.append(AttributeLink(source.id, target.id, a, b, label, duration))
                aggregates[a, b, label].append(duration)
    except ValueError as exc:
        return _invalid(log, spec, operator, exc)
    edges = []
    for (a, b, label), values in sorted(aggregates.items()):
        durations = [v for v in values if v is not None]
        edges.append(
            AttributeNetworkEdge(
                a,
                b,
                label,
                len(values),
                len(durations),
                _ratio(sum(durations), len(durations)),
                sum(durations) if durations else None,
                min(durations) if durations else None,
                max(durations) if durations else None,
            )
        )
    issues = []
    for code, number in (
        ("missing_link_attribute", missing_link),
        ("missing_node_or_edge_attribute", excluded),
        ("unavailable_link_duration", unavailable),
    ):
        if number:
            issues.append(
                ComputeIssue(
                    code,
                    f"{number} affected events/links; population counts are retained.",
                )
            )
    return _finish(
        log,
        spec,
        operator,
        AttributeNetwork(
            tuple(edges),
            tuple(links),
            len(records),
            candidates,
            missing_link,
            excluded,
            unavailable,
            len(times) - len(set(times)),
        ),
        issues,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.discover_social_network": (
        "case_social_network",
        SocialNetworkSpec,
        NetworkPayload,
    ),
    "pix.case_centric.discover_roles": (
        "case_organizational_roles",
        RoleDiscoverySpec,
        RoleSet,
    ),
    "pix.case_centric.measure_organization": (
        "case_organization_diagnostics",
        OrganizationDiagnosticsSpec,
        DiagnosticsPayload,
    ),
    "pix.case_centric.measure_resource_profiles": (
        "case_resource_profiles",
        ResourceProfileSpec,
        ResourceProfiles,
    ),
    "pix.case_centric.discover_attribute_network": (
        "case_attribute_network",
        AttributeNetworkSpec,
        AttributeNetwork,
    ),
}

__all__ = [
    "SocialNetworkSpec",
    "NetworkEdge",
    "NetworkPayload",
    "discover_social_network",
    "RoleDiscoverySpec",
    "OrganizationalRole",
    "RoleMerge",
    "RoleSet",
    "discover_roles",
    "OrganizationalGroup",
    "OrganizationDiagnosticsSpec",
    "GroupActivityDiagnostic",
    "DiagnosticsPayload",
    "measure_organization",
    "ResourceProfileSpec",
    "ResourceProfile",
    "ResourceInteraction",
    "ResourceProfiles",
    "measure_resource_profiles",
    "AttributeNetworkSpec",
    "AttributeLink",
    "AttributeNetworkEdge",
    "AttributeNetwork",
    "discover_attribute_network",
]
