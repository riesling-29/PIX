"""Complete per-group sequence frequencies and variant-count prefix selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from pix.case_centric._trace_variants import ranked_activity_variants
from pix.case_centric.trace_comparison import (
    TraceGroup,
    _attribute_groups,
    _strings,
    _text,
)
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest, case_traces


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def top_variant_count(variant_count: int, percent: int) -> int:
    """Ceiling of a percentage of distinct variants, never case coverage."""
    _integer(variant_count, "variant_count")
    _integer(percent, "percent")
    if percent > 100:
        raise ValueError("percent must be in 0..100")
    return (variant_count * percent + 99) // 100


@dataclass(frozen=True, slots=True)
class TraceCatalogSpec:
    top_variant_percent: int = 20
    max_variants: int = 10_000
    max_events: int = 1_000_000
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        top_variant_count(0, self.top_variant_percent)
        _integer(self.max_variants, "max_variants", 1)
        _integer(self.max_events, "max_events", 1)
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class TraceCatalogRequest:
    groups: tuple[TraceGroup, ...]
    group_attribute: str | None
    parameters: TraceCatalogSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TraceVariant:
    id: str
    group_id: str
    rank: int
    activities: tuple[str, ...]
    case_ids: tuple[str, ...]
    example_case_id: str
    event_ids: tuple[str, ...]
    cumulative_case_count: int

    @property
    def frequency(self):
        return len(self.case_ids)


@dataclass(frozen=True, slots=True)
class TraceCatalogGroup:
    id: str
    name: str
    case_ids: tuple[str, ...]
    variant_ids: tuple[str, ...]
    selected_variant_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TraceVariantCatalog:
    groups: tuple[TraceCatalogGroup, ...]
    variants: tuple[TraceVariant, ...]
    source_case_count: int
    unassigned_case_ids: tuple[str, ...]
    top_variant_percent: int

    def __post_init__(self):
        top_variant_count(0, self.top_variant_percent)
        _integer(self.source_case_count, "source_case_count")
        for name, cls in (("groups", TraceCatalogGroup), ("variants", TraceVariant)):
            values = getattr(self, name)
            if type(values) is not tuple or any(type(v) is not cls for v in values):
                raise TypeError(f"unsupported {name}")
        _strings(self.unassigned_case_ids, "unassigned case IDs")
        groups = {g.id: g for g in self.groups}
        variants = {v.id: v for v in self.variants}
        if len(groups) != len(self.groups) or len(variants) != len(self.variants):
            raise ValueError("duplicate identities")
        if len({g.name for g in self.groups}) != len(groups):
            raise ValueError("duplicate group names")
        population = list(self.unassigned_case_ids)
        declared = []
        for g in self.groups:
            _text(g.id, "group ID")
            _text(g.name, "group name")
            for name in ("case_ids", "variant_ids", "selected_variant_ids"):
                _strings(getattr(g, name), name)
            population.extend(g.case_ids)
            declared.extend(g.variant_ids)
            if (
                g.selected_variant_ids
                != g.variant_ids[
                    : top_variant_count(len(g.variant_ids), self.top_variant_percent)
                ]
            ):
                raise ValueError("selected variants differ from count prefix")
            members, words, keys, cumulative = [], [], [], 0
            for rank, vid in enumerate(g.variant_ids, 1):
                v = variants.get(vid)
                if v is None or v.group_id != g.id:
                    raise ValueError("invalid variant membership")
                _text(v.id, "variant ID")
                for name in ("activities", "case_ids", "event_ids"):
                    _strings(getattr(v, name), name)
                _integer(v.rank, "rank", 1)
                _integer(v.cumulative_case_count, "cumulative count")
                if not v.case_ids or v.example_case_id != min(v.case_ids):
                    raise ValueError("example case must be minimum actual member")
                if len(v.event_ids) != len(v.activities) or len(
                    set(v.event_ids)
                ) != len(v.event_ids):
                    raise ValueError("event identities differ from sequence")
                cumulative += v.frequency
                if v.rank != rank or v.cumulative_case_count != cumulative:
                    raise ValueError("invalid rank or cumulative count")
                members.extend(v.case_ids)
                words.append(v.activities)
                keys.append((-v.frequency, v.activities))
            if len(set(words)) != len(words) or keys != sorted(keys):
                raise ValueError("variants must be unique and frequency ranked")
            if len(members) != len(set(members)) or set(members) != set(g.case_ids):
                raise ValueError("variants must partition their group")
        if (
            len(population) != len(set(population))
            or len(population) != self.source_case_count
        ):
            raise ValueError("groups and unassigned must partition the source")
        if len(declared) != len(set(declared)) or set(declared) != set(variants):
            raise ValueError("variant membership differs from groups")


def catalog_trace_variants(
    log: CaseLog,
    groups: tuple[TraceGroup, ...] | None = None,
    *,
    group_attribute: str | None = None,
    spec: TraceCatalogSpec = TraceCatalogSpec(),
) -> ComputationResult[TraceVariantCatalog]:
    """List complete exact activity variants; select ceil(V*p/100) per group.

    Omitted grouping uses all cases. Missing attribute labels remain unassigned.
    This computes neither alignments nor a new representative selection algorithm.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, TraceCatalogSpec):
        raise TypeError("expected CaseLog and TraceCatalogSpec")
    if groups is not None and group_attribute is not None:
        raise ValueError("supply either groups or group_attribute")
    if groups is None:
        groups = (
            _attribute_groups(log, group_attribute)
            if group_attribute is not None
            else (TraceGroup("All cases", tuple(t.id for t in log.traces)),)
        )
    if type(groups) is not tuple or any(type(g) is not TraceGroup for g in groups):
        raise TypeError("groups must be a tuple of TraceGroup")
    if len({g.name for g in groups}) != len(groups):
        raise ValueError("group names must be unique")
    if any(g.representative_case_id is not None for g in groups):
        raise ValueError("catalog groups do not select a representative")
    source_ids = {t.id for t in log.traces}
    assigned = [cid for g in groups for cid in g.case_ids]
    if len(assigned) != len(set(assigned)) or not set(assigned) <= source_ids:
        raise ValueError("groups must be disjoint and contain known case IDs")
    request = TraceCatalogRequest(groups, group_attribute, spec)
    operator = "pix.case_centric.catalog_trace_variants"
    if sum(len(t.events) for t in log.traces) > spec.max_events:
        return _derived_result(
            operator,
            case_log_digest(log),
            request,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("event_limit", "Complete catalog exceeds max_events"),),
        )
    traces = case_traces(log, spec.trace_spec)

    def result(status, value, issues=()):
        return _derived_result(
            operator,
            traces.source_digest,
            request,
            status,
            value,
            traces.issues + issues,
            parent_computation_ids=(traces.computation_id,)
            if traces.computation_id
            else (),
        )

    if traces.status is not ComputeStatus.COMPUTED:
        return result(
            ComputeStatus.INVALID_INPUT
            if traces.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("incomplete_traces", "Complete ordered traces required"),),
        )
    by_id = {t.object_id: t for t in traces.value.traces}
    variants, summaries = [], []
    for i, group in enumerate(groups):
        gid, ids, cumulative = f"group:{i}", [], 0
        ranked = ranked_activity_variants(by_id, group.case_ids)
        if len(variants) + len(ranked) > spec.max_variants:
            return result(
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "variant_limit",
                        "Complete catalog exceeds max_variants; no truncated prefix returned",
                    ),
                ),
            )
        for rank, (word, members) in enumerate(ranked, 1):
            vid = f"{gid}/variant:{rank}"
            cumulative += len(members)
            variants.append(
                TraceVariant(
                    vid,
                    gid,
                    rank,
                    word,
                    members,
                    members[0],
                    tuple(e.event_id for e in by_id[members[0]].events),
                    cumulative,
                )
            )
            ids.append(vid)
        summaries.append(
            TraceCatalogGroup(
                gid,
                group.name,
                group.case_ids,
                tuple(ids),
                tuple(ids[: top_variant_count(len(ids), spec.top_variant_percent)]),
            )
        )
    return result(
        ComputeStatus.COMPUTED,
        TraceVariantCatalog(
            tuple(summaries),
            tuple(variants),
            len(source_ids),
            tuple(sorted(source_ids - set(assigned))),
            spec.top_variant_percent,
        ),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.catalog_trace_variants": (
        "case_trace_variant_catalog",
        TraceCatalogRequest,
        TraceVariantCatalog,
    ),
}

__all__ = (
    "TraceCatalogSpec",
    "TraceCatalogRequest",
    "TraceVariant",
    "TraceCatalogGroup",
    "TraceVariantCatalog",
    "catalog_trace_variants",
    "top_variant_count",
)
