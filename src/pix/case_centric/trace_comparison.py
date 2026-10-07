"""Labelled groups, observed representatives and bounded pairwise alignments.

Representatives are actual cases, not a synthetic average sequence. Exact
activity tuples define variants. Frequency ties use activity tuple then case ID.
Every candidate-to-reference comparison is computed independently; arranging
them around one reference does not claim optimal multiple-sequence alignment.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import ClassVar

from pix.case_centric.sequence_alignment import EditMove, SequenceAlignmentSpec, _edit
from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_traces


def _text(value, name):
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _strings(value, name):
    if type(value) is not tuple or any(type(x) is not str for x in value):
        raise TypeError(f"{name} must be a tuple of strings")


@dataclass(frozen=True, slots=True)
class TraceGroup:
    name: str
    case_ids: tuple[str, ...]
    representative_case_id: str | None = None

    def __post_init__(self):
        _text(self.name, "group name")
        _strings(self.case_ids, "case IDs")
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("duplicate case IDs in group")
        object.__setattr__(self, "case_ids", tuple(sorted(self.case_ids)))
        if self.representative_case_id is not None:
            if self.representative_case_id not in self.case_ids:
                raise ValueError("manual representative must belong to its group")


@dataclass(frozen=True, slots=True)
class TraceComparisonSpec:
    candidates_per_group: int = 3
    reference_group: str | None = None
    alignment: SequenceAlignmentSpec = SequenceAlignmentSpec()
    max_total_cells: int = 4_000_000
    max_candidates: int = 64
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("candidates_per_group", "max_total_cells", "max_candidates"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.reference_group is not None:
            _text(self.reference_group, "reference group")
        if not isinstance(self.alignment, SequenceAlignmentSpec):
            raise TypeError("alignment must be SequenceAlignmentSpec")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class TraceComparisonRequest:
    groups: tuple[TraceGroup, ...]
    group_attribute: str | None
    parameters: TraceComparisonSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TraceRepresentative:
    id: str
    group_id: str
    case_id: str
    activities: tuple[str, ...]
    event_ids: tuple[str, ...]
    member_case_ids: tuple[str, ...]
    rank: int
    selection: str

    @property
    def frequency(self):
        return len(self.member_case_ids)


@dataclass(frozen=True, slots=True)
class TraceComparisonGroup:
    id: str
    name: str
    case_ids: tuple[str, ...]
    variant_count: int
    candidate_ids: tuple[str, ...]
    selected_candidate_id: str | None


@dataclass(frozen=True, slots=True)
class RepresentativeAlignment:
    candidate_id: str
    reference_id: str
    status: str
    cost: int | None
    moves: tuple[EditMove, ...]


@dataclass(frozen=True, slots=True)
class TraceGroupComparison:
    groups: tuple[TraceComparisonGroup, ...]
    candidates: tuple[TraceRepresentative, ...]
    alignments: tuple[RepresentativeAlignment, ...]
    reference_group_id: str
    source_case_count: int
    unassigned_case_ids: tuple[str, ...]

    def __post_init__(self):
        for name, cls in (
            ("groups", TraceComparisonGroup),
            ("candidates", TraceRepresentative),
            ("alignments", RepresentativeAlignment),
        ):
            values = getattr(self, name)
            if type(values) is not tuple or any(type(x) is not cls for x in values):
                raise TypeError(f"{name} contains an unsupported value")
        groups = {g.id: g for g in self.groups}
        candidates = {c.id: c for c in self.candidates}
        if len(groups) != len(self.groups) or len(groups) < 2:
            raise ValueError("at least two uniquely identified groups are required")
        if len({g.name for g in self.groups}) != len(groups):
            raise ValueError("group names must be unique")
        if len(candidates) != len(self.candidates):
            raise ValueError("representative IDs must be unique")
        if self.reference_group_id not in groups:
            raise ValueError("reference group is not declared")
        if type(self.source_case_count) is not int or self.source_case_count < 0:
            raise ValueError("invalid source population")
        _strings(self.unassigned_case_ids, "unassigned case IDs")
        members = list(self.unassigned_case_ids)
        declared = []
        for group in self.groups:
            _text(group.id, "group ID")
            _text(group.name, "group name")
            _strings(group.case_ids, "group case IDs")
            _strings(group.candidate_ids, "candidate IDs")
            members.extend(group.case_ids)
            declared.extend(group.candidate_ids)
            if type(group.variant_count) is not int or not (
                len(group.candidate_ids) <= group.variant_count <= len(group.case_ids)
            ):
                raise ValueError("invalid variant coverage")
            if bool(group.case_ids) != bool(group.candidate_ids):
                raise ValueError("nonempty groups require representative candidates")
            if group.selected_candidate_id not in group.candidate_ids + (None,):
                raise ValueError("selected representative is not in group")
            if group.candidate_ids and group.selected_candidate_id is None:
                raise ValueError("nonempty group requires a selected representative")
        if len(members) != len(set(members)) or len(members) != self.source_case_count:
            raise ValueError("groups and unassigned cases must partition the source")
        if len(declared) != len(set(declared)) or set(declared) != set(candidates):
            raise ValueError("candidate membership differs from groups")
        variant_members = defaultdict(set)
        for c in self.candidates:
            _text(c.id, "representative ID")
            _strings(c.activities, "activities")
            _strings(c.event_ids, "event IDs")
            _strings(c.member_case_ids, "variant case IDs")
            g = groups.get(c.group_id)
            if g is None or c.id not in g.candidate_ids:
                raise ValueError("representative has an invalid group")
            if c.case_id not in c.member_case_ids or not set(c.member_case_ids) <= set(
                g.case_ids
            ):
                raise ValueError("representative membership differs from its group")
            if len(c.member_case_ids) != len(set(c.member_case_ids)) or variant_members[
                g.id
            ].intersection(c.member_case_ids):
                raise ValueError("candidate variants must have disjoint memberships")
            variant_members[g.id].update(c.member_case_ids)
            if len(c.activities) != len(c.event_ids) or len(set(c.event_ids)) != len(
                c.event_ids
            ):
                raise ValueError("representative event identities differ from sequence")
            if type(c.rank) is not int or not 1 <= c.rank <= g.variant_count:
                raise ValueError("invalid variant rank")
            if c.selection not in ("frequency", "manual"):
                raise ValueError("unknown representative selection")
        expected = {
            (c.id, r.id)
            for c in self.candidates
            for r in self.candidates
            if c.group_id != r.group_id
        }
        keys = [(a.candidate_id, a.reference_id) for a in self.alignments]
        if len(keys) != len(set(keys)) or set(keys) != expected:
            raise ValueError(
                "every cross-group candidate pair needs an explicit outcome"
            )
        for a in self.alignments:
            if a.status not in ("optimal", "cell_limit"):
                raise ValueError("unknown alignment outcome")
            if type(a.moves) is not tuple or any(
                type(m) is not EditMove for m in a.moves
            ):
                raise TypeError("alignment moves must be EditMove values")
            if a.status == "cell_limit":
                if a.cost is not None or a.moves:
                    raise ValueError(
                        "limited comparisons cannot claim a cost or witness"
                    )
                continue
            if type(a.cost) is not int or a.cost < 0:
                raise ValueError("invalid alignment cost")
            left, right = candidates[a.candidate_id], candidates[a.reference_id]
            for m in a.moves:
                if type(m.cost) is not int or m.cost < 0:
                    raise ValueError("invalid move cost")
                if m.kind not in ("synchronous", "substitution", "log", "model"):
                    raise ValueError("unknown move")
                if (m.log_activity is None) != (m.kind == "model") or (
                    m.model_activity is None
                ) != (m.kind == "log"):
                    raise ValueError("move sides do not match its kind")
                if (m.log_event_id is None) != (m.kind == "model") or (
                    m.reference_event_id is None
                ) != (m.kind == "log"):
                    raise ValueError("move identities do not match its kind")
                if m.kind == "synchronous" and (
                    m.log_activity != m.model_activity or m.cost
                ):
                    raise ValueError("invalid synchronous move")
                if m.kind == "substitution" and m.log_activity == m.model_activity:
                    raise ValueError("substitution must change the activity")
            for values, names, key in (
                (left.activities, left.event_ids, "log"),
                (right.activities, right.event_ids, "model"),
            ):
                seen = tuple(
                    getattr(m, key + "_activity")
                    for m in a.moves
                    if getattr(m, key + "_activity") is not None
                )
                ids = tuple(
                    (m.log_event_id if key == "log" else m.reference_event_id)
                    for m in a.moves
                    if getattr(m, key + "_activity") is not None
                )
                if seen != values or ids != names:
                    raise ValueError(
                        "alignment witness does not reconstruct its representatives"
                    )
            if sum(m.cost for m in a.moves) != a.cost:
                raise ValueError("alignment cost differs from witness")


def _attribute_groups(log, key):
    _text(key, "group_attribute")
    grouped = defaultdict(list)
    kinds = {}
    for trace in log.traces:
        attr = log.attribute(trace, key)
        if attr is None or attr.type == "null":
            continue
        if attr.type not in ("string", "boolean", "int"):
            raise ValueError(
                "group attributes must be string, boolean or int; use explicit groups otherwise"
            )
        name = str(attr.value).lower() if attr.type == "boolean" else str(attr.value)
        _text(name, "group attribute value")
        if name in kinds and kinds[name] != attr.type:
            raise ValueError("ambiguous typed group labels; use explicit groups")
        kinds[name] = attr.type
        grouped[name].append(trace.id)
    return tuple(TraceGroup(name, tuple(ids)) for name, ids in sorted(grouped.items()))


def compare_trace_groups(
    log: CaseLog,
    groups: tuple[TraceGroup, ...] | None = None,
    *,
    group_attribute: str | None = None,
    spec: TraceComparisonSpec = TraceComparisonSpec(),
) -> ComputationResult[TraceGroupComparison]:
    """Compare labelled case groups using observed frequent/manual candidates.

    Supply explicit disjoint groups, or one case-attribute name. Missing labels
    remain unassigned. The browser may switch among the retained candidates and
    reference groups, using only the pairwise witnesses computed here. Raw OCEL
    is intentionally rejected: project to cases explicitly first.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, TraceComparisonSpec):
        raise TypeError("expected CaseLog and TraceComparisonSpec")
    if (groups is None) == (group_attribute is None):
        raise ValueError("supply either groups or group_attribute")
    if groups is None:
        groups = _attribute_groups(log, group_attribute)
    if type(groups) is not tuple or any(type(g) is not TraceGroup for g in groups):
        raise TypeError("groups must be a tuple of TraceGroup")
    if len(groups) < 2 or len({g.name for g in groups}) != len(groups):
        raise ValueError("supply at least two uniquely named groups")
    if spec.reference_group is not None and spec.reference_group not in {
        g.name for g in groups
    }:
        raise ValueError("reference group is not declared")
    source_ids = {t.id for t in log.traces}
    assigned = [cid for g in groups for cid in g.case_ids]
    if len(assigned) != len(set(assigned)) or not set(assigned) <= source_ids:
        raise ValueError("groups must be disjoint and contain known case IDs")
    traces = case_traces(log, spec.trace_spec)
    request = TraceComparisonRequest(groups, group_attribute, spec)

    def result(status, value, issues=()):
        return _derived_result(
            "pix.case_centric.compare_trace_groups",
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
            (
                ComputeIssue(
                    "incomplete_traces", "Complete ordered case traces are required"
                ),
            ),
        )
    by_id = {t.object_id: t for t in traces.value.traces}
    candidates, summaries, issues = [], [], []
    for index, group in enumerate(groups):
        gid = f"group:{index}"
        variants = defaultdict(list)
        for cid in group.case_ids:
            variants[tuple(e.activity for e in by_id[cid].events)].append(cid)
        ordered = sorted(variants, key=lambda word: (-len(variants[word]), word))
        retained = ordered[: spec.candidates_per_group]
        manual_word = None
        if group.representative_case_id is not None:
            manual_word = tuple(
                e.activity for e in by_id[group.representative_case_id].events
            )
            if manual_word not in retained:
                retained[-1:] = [manual_word]
        if len(candidates) + len(retained) > spec.max_candidates:
            return result(
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "candidate_limit",
                        "Reduce groups/candidates_per_group or explicitly raise max_candidates",
                    ),
                ),
            )
        ids, selected = [], None
        for word in retained:
            rank = ordered.index(word) + 1
            cid = (
                group.representative_case_id
                if word == manual_word
                else min(variants[word])
            )
            candidate = TraceRepresentative(
                f"{gid}/variant:{rank}",
                gid,
                cid,
                word,
                tuple(e.event_id for e in by_id[cid].events),
                tuple(sorted(variants[word])),
                rank,
                "manual" if word == manual_word else "frequency",
            )
            candidates.append(candidate)
            ids.append(candidate.id)
            if selected is None or word == manual_word:
                selected = candidate.id
        summaries.append(
            TraceComparisonGroup(
                gid, group.name, group.case_ids, len(variants), tuple(ids), selected
            )
        )
        if not ids:
            issues.append(
                ComputeIssue(
                    "empty_group", f"Group {group.name!r} has no cases", (gid,)
                )
            )
    if len(candidates) > spec.max_candidates:
        return result(
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "candidate_limit",
                    "Reduce groups/candidates_per_group or explicitly raise max_candidates",
                ),
            ),
        )
    alignments, used, limited = [], 0, 0
    for candidate in candidates:
        for reference in candidates:
            if candidate.group_id == reference.group_id:
                continue
            cells = (len(candidate.activities) + 1) * (len(reference.activities) + 1)
            if cells > spec.alignment.max_cells or used + cells > spec.max_total_cells:
                alignments.append(
                    RepresentativeAlignment(
                        candidate.id, reference.id, "cell_limit", None, ()
                    )
                )
                limited += 1
                continue
            cost, moves = _edit(
                candidate.activities,
                reference.activities,
                spec.alignment,
                candidate.event_ids,
                reference.event_ids,
            )
            alignments.append(
                RepresentativeAlignment(
                    candidate.id, reference.id, "optimal", cost, moves
                )
            )
            used += cells
    if limited:
        issues.append(
            ComputeIssue(
                "alignment_cell_limit",
                f"{limited} directed candidate pairs were not computed; their costs remain unknown",
            )
        )
    reference_id = next(
        (g.id for g in summaries if g.name == spec.reference_group), summaries[0].id
    )
    value = TraceGroupComparison(
        tuple(summaries),
        tuple(candidates),
        tuple(alignments),
        reference_id,
        len(source_ids),
        tuple(sorted(source_ids - set(assigned))),
    )
    return result(
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.compare_trace_groups": (
        "case_trace_group_comparison",
        TraceComparisonRequest,
        TraceGroupComparison,
    ),
}

__all__ = (
    "TraceGroup",
    "TraceComparisonSpec",
    "TraceComparisonRequest",
    "TraceRepresentative",
    "TraceComparisonGroup",
    "RepresentativeAlignment",
    "TraceGroupComparison",
    "compare_trace_groups",
)
