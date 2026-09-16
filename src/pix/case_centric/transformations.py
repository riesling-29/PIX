"""Native case-log transformations with verifiable plans and separate raw facts.

Analytical results contain immutable lineage/encoded facts, never raw non-finite
XES values. Materializers recompute the exact plan before touching source facts.
Timestamp order, synthetic boundaries and linked cases are explicitly analytical
constructions; none establishes causality or changes the original source logs.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from typing import ClassVar

from pix.case_centric.interleavings import CaseLink
from pix.compute._common import _derived_result
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
)
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_log_digest
from pix.event_log.adapters import _facts


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _choice(value, choices, name):
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}")


def _texts(values, name):
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in values:
        _text(item, name)
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


def _check(log, spec, expected):
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, expected):
        raise TypeError(f"spec must be {expected.__name__}")


def _encoded(value):
    return json.dumps(
        _facts(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


def _id(kind, *parts):
    return (
        "pix:" + kind + ":" + sha256(_encoded(tuple(parts)).encode("utf-8")).hexdigest()
    )


def _result(operator, log, spec, value=None, issues=(), status=None):
    return _derived_result(
        operator,
        case_log_digest(log),
        spec,
        status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        tuple(issues),
    )


def _failed(operator, log, spec, code, message, status=ComputeStatus.INVALID_INPUT):
    return _result(
        operator, log, spec, issues=(ComputeIssue(code, message),), status=status
    )


def _time(log, event, key):
    attribute = log.attribute(event, key)
    if (
        attribute is None
        or attribute.type != "date"
        or attribute.value.utcoffset() is None
    ):
        return None
    try:
        return attribute.value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        return None


def _same_evidence(actual, expected):
    """Type-tagged equality rejects bool-as-int and other Python equality aliases."""
    try:
        return _identity_value(actual) == _identity_value(expected)
    except (TypeError, ValueError):
        return False


@dataclass(frozen=True, slots=True)
class CaseSortSpec:
    """Declared scalar sort; no arbitrary callable is hidden in result identity.

    Null placement is independent of ascending/descending direction. Equal known
    keys keep source order, use ascending identity, or reject as requested. Empty
    cases are preserved and placed explicitly when cases are sorted by first key.
    """

    key: str = "time:timestamp"
    key_type: str = "timestamp"
    reverse: bool = False
    nulls: str = "reject"
    ties: str = "source"
    case_order: str = "source"
    empty_cases: str = "last"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _text(self.key, "key")
        _choice(self.key_type, ("timestamp", "string", "number"), "key_type")
        _choice(self.nulls, ("reject", "first", "last"), "nulls")
        _choice(self.ties, ("source", "id", "reject"), "ties")
        _choice(self.case_order, ("source", "first_event"), "case_order")
        _choice(self.empty_cases, ("first", "last"), "empty_cases")
        if type(self.reverse) is not bool:
            raise TypeError("reverse must be bool")


@dataclass(frozen=True, slots=True)
class OrderTie:
    scope: str
    owner: str
    ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseOrder:
    source_case_id: str
    event_ids: tuple[str, ...]
    source_positions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CaseSortPlan:
    cases: tuple[CaseOrder, ...]
    unavailable_key_event_ids: tuple[str, ...]
    ties: tuple[OrderTie, ...]
    empty_case_ids: tuple[str, ...]
    event_count: int


def _sort_key(log, event, spec):
    attribute = log.attribute(event, spec.key)
    if spec.key_type == "timestamp":
        return _time(log, event, spec.key)
    if attribute is None:
        return None
    if spec.key_type == "string":
        return attribute.value if attribute.type in ("string", "id") else None
    if attribute.type in ("int", "float") and (
        attribute.type == "int" or isfinite(attribute.value)
    ):
        return attribute.value
    return None


def _ordered(records, spec, scope, owner, tie_keys=None):
    # A record is (identity, key, payload). Preserve unknown positions as evidence.
    known = [record for record in records if record[1] is not None]
    unknown = [record for record in records if record[1] is None]
    by_key = defaultdict(list)
    for identity, key, _ in known:
        by_key[key].append(identity)
    ties = tuple(
        OrderTie(scope, owner, tuple(ids)) for ids in by_key.values() if len(ids) > 1
    )
    if unknown and spec.nulls == "reject":
        raise LookupError(f"{scope} {owner!r}: {len(unknown)} unusable sort keys")
    if ties and spec.ties == "reject":
        raise LookupError(
            f"{scope} {owner!r}: equal sort keys have no selected tie order"
        )
    if spec.ties == "id":
        known.sort(
            key=lambda record: (
                tie_keys[record[0]] if tie_keys is not None else record[0]
            )
        )
    known.sort(key=lambda record: record[1], reverse=spec.reverse)
    return (unknown + known if spec.nulls == "first" else known + unknown), ties


def sort_case_log(
    log: CaseLog, spec: CaseSortSpec = CaseSortSpec()
) -> ComputationResult[CaseSortPlan]:
    _check(log, spec, CaseSortSpec)
    operator = "pix.case_centric.sort_case_log"
    cases, missing, ties = [], [], []
    case_keys = {}
    try:
        for trace in log.traces:
            records = [
                (event.id, _sort_key(log, event, spec), i)
                for i, event in enumerate(trace.events)
            ]
            missing.extend(identity for identity, key, _ in records if key is None)
            ordered, current_ties = _ordered(records, spec, "event", trace.id)
            ties.extend(current_ties)
            cases.append(
                CaseOrder(
                    trace.id, tuple(r[0] for r in ordered), tuple(r[2] for r in ordered)
                )
            )
            case_keys[trace.id] = ordered[0][1] if ordered else None
        empty = tuple(trace.id for trace in log.traces if not trace.events)
        if spec.case_order == "first_event":
            nonempty = [
                (case.source_case_id, case_keys[case.source_case_id], case)
                for case in cases
                if case.event_ids
            ]
            ordered, current_ties = _ordered(nonempty, spec, "case", "log")
            ties.extend(current_ties)
            empty_cases = [case for case in cases if not case.event_ids]
            cases = (
                [*empty_cases, *(r[2] for r in ordered)]
                if spec.empty_cases == "first"
                else [*(r[2] for r in ordered), *empty_cases]
            )
    except LookupError as exc:
        return _failed(
            operator,
            log,
            spec,
            "order_unavailable",
            str(exc),
            ComputeStatus.UNAVAILABLE,
        )
    except ValueError as exc:
        return _failed(operator, log, spec, "ambiguous_attribute", str(exc))
    issues = (
        (
            ComputeIssue(
                "placed_unknown_keys",
                f"{len(missing)} event keys were explicitly placed {spec.nulls}; this does not establish their temporal order.",
            ),
        )
        if missing
        else ()
    )
    return _result(
        operator,
        log,
        spec,
        CaseSortPlan(
            tuple(cases),
            tuple(missing),
            tuple(ties),
            empty,
            sum(len(trace.events) for trace in log.traces),
        ),
        issues,
    )


def materialize_case_sort(
    log: CaseLog, plan: ComputationResult[CaseSortPlan]
) -> CaseLog:
    if (
        not isinstance(plan, ComputationResult)
        or plan.operator_id != "pix.case_centric.sort_case_log"
        or not isinstance(plan.value, CaseSortPlan)
    ):
        raise ValueError("expected an available case sort plan")
    if not _same_evidence(plan, sort_case_log(log, plan.spec)):
        raise ValueError(
            "sort plan does not match source, request and calculated order"
        )
    traces = {trace.id: trace for trace in log.traces}
    return replace(
        log,
        traces=tuple(
            replace(
                traces[row.source_case_id],
                events=tuple(
                    traces[row.source_case_id].events[i] for i in row.source_positions
                ),
            )
            for row in plan.value.cases
        ),
    )


@dataclass(frozen=True, slots=True)
class CaseGraphSpec:
    include_directly_follows: bool = True
    event_attribute_nodes: tuple[str, ...] = ()
    case_attribute_nodes: tuple[str, ...] = ()
    attribute_identity: str = "key_value"
    include_effective_properties: bool = True
    max_nodes: int = 1000000
    max_edges: int = 3000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _texts(self.event_attribute_nodes, "event_attribute_nodes")
        _texts(self.case_attribute_nodes, "case_attribute_nodes")
        _choice(self.attribute_identity, ("key_value", "value"), "attribute_identity")
        if (
            type(self.include_directly_follows) is not bool
            or type(self.include_effective_properties) is not bool
        ):
            raise TypeError("graph inclusion settings must be bool")
        for name in ("max_nodes", "max_edges"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class GraphProperty:
    key: str
    type: str
    fact_encoding: str


@dataclass(frozen=True, slots=True)
class CaseGraphNode:
    id: str
    kind: str
    source_case_id: str | None
    source_event_id: str | None
    attribute_key: str | None
    value_type: str | None
    value_encoding: str | None
    properties: tuple[GraphProperty, ...]


@dataclass(frozen=True, slots=True)
class CaseGraphEdge:
    source: str
    target: str
    kind: str
    attribute_key: str | None = None


@dataclass(frozen=True, slots=True)
class CaseEventGraph:
    nodes: tuple[CaseGraphNode, ...]
    edges: tuple[CaseGraphEdge, ...]
    case_count: int
    event_count: int
    missing_selected_attributes: tuple[tuple[str, str, str], ...]


def case_log_to_graph(
    log: CaseLog, spec: CaseGraphSpec = CaseGraphSpec()
) -> ComputationResult[CaseEventGraph]:
    """Typed event/case/attribute multirelations, independent of graph backends.

    Type and kind namespaces prevent cases/events/values from colliding. Selected
    scalar attribute nodes ignore lexical spelling but distinguish int/bool/float;
    complete original nested facts remain in owner properties as tagged encoding.
    Non-finite floats are strings inside that encoding, never JSON NaN values.
    """
    _check(log, spec, CaseGraphSpec)
    operator = "pix.case_centric.case_log_to_graph"
    nodes, edges, missing = {}, [], []

    def add_node(node):
        nodes.setdefault(node.id, node)
        if len(nodes) > spec.max_nodes:
            raise OverflowError("graph node bound exceeded")

    def add_edge(edge):
        edges.append(edge)
        if len(edges) > spec.max_edges:
            raise OverflowError("graph edge bound exceeded")

    def properties(item):
        attributes = (
            log.effective_attributes(item)
            if spec.include_effective_properties
            else item.attributes
        )
        return tuple(GraphProperty(a.key, a.type, _encoded(a)) for a in attributes)

    def attribute_nodes(item, node_id, selected, scope):
        for key in selected:
            attribute = log.attribute(item, key)
            if attribute is None:
                missing.append((scope, item.id, key))
                continue
            if attribute.type in ("list", "container"):
                value = _encoded(replace(attribute, key="", lexical=None))
            else:
                value = _encoded(attribute.value)
            key_part = key if spec.attribute_identity == "key_value" else ""
            identity = _id("attribute", key_part, attribute.type, value)
            add_node(
                CaseGraphNode(
                    identity,
                    "attribute",
                    None,
                    None,
                    key if spec.attribute_identity == "key_value" else None,
                    attribute.type,
                    value,
                    (),
                )
            )
            add_edge(CaseGraphEdge(node_id, identity, "attribute", key))

    try:
        for trace in log.traces:
            case_id = _id("case-node", trace.id)
            add_node(
                CaseGraphNode(
                    case_id, "case", trace.id, None, None, None, None, properties(trace)
                )
            )
            attribute_nodes(trace, case_id, spec.case_attribute_nodes, "case")
            previous = None
            for event in trace.events:
                event_id = _id("event-node", event.id)
                add_node(
                    CaseGraphNode(
                        event_id,
                        "event",
                        trace.id,
                        event.id,
                        None,
                        None,
                        None,
                        properties(event),
                    )
                )
                add_edge(CaseGraphEdge(event_id, case_id, "belongs_to"))
                if previous is not None and spec.include_directly_follows:
                    add_edge(CaseGraphEdge(previous, event_id, "directly_follows"))
                attribute_nodes(event, event_id, spec.event_attribute_nodes, "event")
                previous = event_id
    except OverflowError as exc:
        return _failed(
            operator,
            log,
            spec,
            "graph_budget_exceeded",
            str(exc),
            ComputeStatus.UNAVAILABLE,
        )
    except ValueError as exc:
        return _failed(operator, log, spec, "ambiguous_attribute", str(exc))
    issues = (
        (
            ComputeIssue(
                "missing_selected_attribute",
                f"{len(missing)} selected attribute facts are absent; owning event/case nodes remain.",
            ),
        )
        if missing
        else ()
    )
    return _result(
        operator,
        log,
        spec,
        CaseEventGraph(
            tuple(nodes.values()),
            tuple(edges),
            len(log.traces),
            sum(len(t.events) for t in log.traces),
            tuple(missing),
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class BoundarySpec:
    activity_key: str = "concept:name"
    timestamp_key: str = "time:timestamp"
    start_activity: str = "__PIX_START__"
    end_activity: str = "__PIX_END__"
    timestamp_policy: str = "none"
    offset_microseconds: int = 1000000
    missing_timestamp: str = "reject"
    empty_cases: str = "insert"
    activity_collision: str = "reject"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("activity_key", "timestamp_key", "start_activity", "end_activity"):
            _text(getattr(self, name), name)
        if (
            self.activity_key == self.timestamp_key
            or self.start_activity == self.end_activity
        ):
            raise ValueError("activity/time keys and start/end labels must be distinct")
        if "pix:synthetic" in (self.activity_key, self.timestamp_key):
            raise ValueError("pix:synthetic is reserved for boundary provenance")
        _choice(
            self.timestamp_policy, ("none", "endpoint", "outside"), "timestamp_policy"
        )
        _choice(self.missing_timestamp, ("reject", "omit"), "missing_timestamp")
        _choice(self.empty_cases, ("insert", "preserve", "reject"), "empty_cases")
        _choice(self.activity_collision, ("reject", "allow"), "activity_collision")
        if type(self.offset_microseconds) is not int or self.offset_microseconds <= 0:
            raise ValueError("offset_microseconds must be a positive integer")


@dataclass(frozen=True, slots=True)
class BoundaryEvent:
    id: str
    kind: str
    activity: str
    timestamp: datetime | None


@dataclass(frozen=True, slots=True)
class BoundaryCase:
    source_case_id: str
    source_event_ids: tuple[str, ...]
    start: BoundaryEvent | None
    end: BoundaryEvent | None


@dataclass(frozen=True, slots=True)
class BoundaryPlan:
    cases: tuple[BoundaryCase, ...]
    original_event_count: int
    synthetic_event_count: int
    unavailable_boundary_times: tuple[tuple[str, str], ...]
    colliding_activity_event_ids: tuple[str, ...]


def insert_case_boundaries(
    log: CaseLog, spec: BoundarySpec = BoundarySpec()
) -> ComputationResult[BoundaryPlan]:
    """Plan explicitly synthetic events around source order; times are assumptions.

    `endpoint` copies timestamps of the first/last source events only; it never
    searches interior events for substitutes. `outside` subtracts/adds
    the declared offset to first/last source timestamps (not min/max timestamps).
    Empty cases have no observed timestamp to offset and follow missing policy.
    """
    _check(log, spec, BoundarySpec)
    operator = "pix.case_centric.insert_case_boundaries"
    existing = {event.id for trace in log.traces for event in trace.events}
    digest = case_log_digest(log)
    rows, missing, collisions = [], [], []
    try:
        # Detect ambiguous global defaults even when only empty cases are present.
        log.effective_attributes(CaseEvent("__boundary_default_probe__"))
        for trace in log.traces:
            for event in trace.events:
                attribute = log.attribute(event, spec.activity_key)
                if (
                    attribute is not None
                    and attribute.type == "string"
                    and attribute.value in (spec.start_activity, spec.end_activity)
                ):
                    collisions.append(event.id)
            if not trace.events and spec.empty_cases == "reject":
                return _failed(
                    operator, log, spec, "empty_case", f"Case {trace.id!r} is empty"
                )
            if not trace.events and spec.empty_cases == "preserve":
                rows.append(BoundaryCase(trace.id, (), None, None))
                continue
            boundary_events = []
            for kind, label, source in (
                (
                    "start",
                    spec.start_activity,
                    trace.events[0] if trace.events else None,
                ),
                ("end", spec.end_activity, trace.events[-1] if trace.events else None),
            ):
                timestamp = None
                if spec.timestamp_policy != "none":
                    timestamp = (
                        _time(log, source, spec.timestamp_key) if source else None
                    )
                    if timestamp is not None and spec.timestamp_policy == "outside":
                        try:
                            timestamp += timedelta(
                                microseconds=spec.offset_microseconds
                                * (-1 if kind == "start" else 1)
                            )
                        except OverflowError:
                            timestamp = None
                    if timestamp is None:
                        missing.append((trace.id, kind))
                identity = _id("synthetic-boundary", digest, trace.id, kind, spec)
                # Also handle a malicious original ID exactly matching the generated one.
                while identity in existing:
                    identity += ":synthetic"
                existing.add(identity)
                boundary_events.append(BoundaryEvent(identity, kind, label, timestamp))
            rows.append(
                BoundaryCase(
                    trace.id, tuple(e.id for e in trace.events), *boundary_events
                )
            )
    except ValueError as exc:
        return _failed(operator, log, spec, "ambiguous_attribute", str(exc))
    if collisions and spec.activity_collision == "reject":
        return _failed(
            operator,
            log,
            spec,
            "boundary_activity_collision",
            f"{len(collisions)} original events use a synthetic boundary label",
        )
    if missing and spec.missing_timestamp == "reject":
        return _failed(
            operator,
            log,
            spec,
            "boundary_timestamp_unavailable",
            f"{len(missing)} synthetic boundary timestamps cannot be derived",
            ComputeStatus.UNAVAILABLE,
        )
    issues = (
        (
            ComputeIssue(
                "omitted_synthetic_timestamp",
                f"{len(missing)} synthetic timestamps were omitted by policy.",
            ),
        )
        if missing
        else ()
    )
    return _result(
        operator,
        log,
        spec,
        BoundaryPlan(
            tuple(rows),
            sum(len(t.events) for t in log.traces),
            sum(row.start is not None for row in rows) * 2,
            tuple(missing),
            tuple(collisions),
        ),
        issues,
    )


def materialize_case_boundaries(
    log: CaseLog, plan: ComputationResult[BoundaryPlan]
) -> CaseLog:
    if (
        not isinstance(plan, ComputationResult)
        or plan.operator_id != "pix.case_centric.insert_case_boundaries"
        or not isinstance(plan.value, BoundaryPlan)
    ):
        raise ValueError("expected an available boundary plan")
    if not _same_evidence(plan, insert_case_boundaries(log, plan.spec)):
        raise ValueError(
            "boundary plan does not match source, request and calculated lineage"
        )
    spec = plan.spec
    default_keys = {
        attribute.key
        for group in log.globals
        if group.scope == "event"
        for attribute in group.attributes
    }

    def synthetic(item):
        # Null is an explicit analytical override, not a recorded source value.
        overrides = [
            CaseAttribute(key, "null")
            for key in sorted(
                default_keys - {spec.activity_key, spec.timestamp_key, "pix:synthetic"}
            )
        ]
        overrides.append(CaseAttribute(spec.activity_key, "string", item.activity))
        if item.timestamp is not None:
            overrides.append(CaseAttribute(spec.timestamp_key, "date", item.timestamp))
        elif spec.timestamp_key in default_keys:
            overrides.append(CaseAttribute(spec.timestamp_key, "null"))
        overrides.append(
            CaseAttribute("pix:synthetic", "string", "boundary:" + item.kind)
        )
        return CaseEvent(item.id, tuple(overrides))

    output = []
    for trace, row in zip(log.traces, plan.value.cases):
        if row.start is None:
            output.append(trace)
        else:
            output.append(
                replace(
                    trace,
                    events=(synthetic(row.start), *trace.events, synthetic(row.end)),
                )
            )
    return replace(log, traces=tuple(output))


@dataclass(frozen=True, slots=True)
class CaseMergeSpec:
    """Insert related right-case occurrences into every retained left case.

    Duplicate relation rows reject by default; `repeat` retains their multiplicity
    explicitly. Unlinked right cases may be excluded (reference direction) or
    retained as separate derived cases. Every result occurrence has a new ID.
    Timestamp ties='id' uses original side/case/event/relation occurrence identity,
    independently of generated IDs or computational resource bounds.
    """

    case_links: tuple[CaseLink, ...] = ()
    order: str = "timestamp"
    left_timestamp_key: str = "time:timestamp"
    right_timestamp_key: str = "time:timestamp"
    nulls: str = "reject"
    ties: str = "source"
    duplicate_links: str = "reject"
    unlinked_right: str = "exclude"
    max_output_events: int = 1000000
    max_output_cases: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.case_links, tuple) or not all(
            isinstance(link, CaseLink) for link in self.case_links
        ):
            raise TypeError("case_links must be a tuple of CaseLink")
        _choice(self.order, ("source", "timestamp"), "order")
        _choice(self.nulls, ("reject", "first", "last"), "nulls")
        _choice(self.ties, ("source", "id", "reject"), "ties")
        _choice(self.duplicate_links, ("reject", "repeat"), "duplicate_links")
        _choice(self.unlinked_right, ("exclude", "retain"), "unlinked_right")
        for name in ("left_timestamp_key", "right_timestamp_key"):
            _text(getattr(self, name), name)
        for name in ("max_output_events", "max_output_cases"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.duplicate_links == "reject" and len(set(self.case_links)) != len(
            self.case_links
        ):
            raise ValueError("duplicate relation rows require duplicate_links='repeat'")


@dataclass(frozen=True, slots=True)
class MergedEventOccurrence:
    output_event_id: str
    source_side: str
    source_case_id: str
    source_event_id: str
    source_position: int
    relation_index: int | None


@dataclass(frozen=True, slots=True)
class MergedCase:
    output_case_id: str
    owner_side: str
    owner_case_id: str
    source_cases: tuple[tuple[str, str], ...]
    events: tuple[MergedEventOccurrence, ...]


@dataclass(frozen=True, slots=True)
class CaseMergePlan:
    left_digest: str
    right_digest: str
    cases: tuple[MergedCase, ...]
    excluded_right_case_ids: tuple[str, ...]
    left_event_count: int
    right_event_count: int
    output_event_count: int
    unique_source_event_count: int
    duplicated_occurrence_count: int
    unavailable_timestamp_occurrences: tuple[str, ...]
    ties: tuple[OrderTie, ...]


@dataclass(frozen=True, slots=True)
class MergedCaseLog:
    """Derived facts plus both intact source environments and exact merge evidence.

    The derived log expands each source's effective defaults, then has no global
    defaults. This prevents one side's globals from inventing facts on the other.
    Original raw attributes/defaults/classifiers/source metadata remain available
    intact on left_source/right_source; materialized events retain original nested
    CaseAttribute objects and lexical fields. This raw-fact bundle is deliberately
    not an analytical ComputationResult payload.
    """

    log: CaseLog
    left_source: CaseLog
    right_source: CaseLog
    plan: ComputationResult[CaseMergePlan]


def merge_linked_cases(
    left: CaseLog, right: CaseLog, spec: CaseMergeSpec = CaseMergeSpec()
) -> ComputationResult[CaseMergePlan]:
    _check(left, spec, CaseMergeSpec)
    if not isinstance(right, CaseLog):
        raise TypeError("right must be CaseLog")
    operator = "pix.case_centric.merge_linked_cases"
    left_digest, right_digest = case_log_digest(left), case_log_digest(right)
    digest = _id("case-merge-source", left_digest, right_digest)

    def finish(value=None, issues=(), status=None):
        return _derived_result(
            operator,
            digest,
            spec,
            status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
            value,
            tuple(issues),
        )

    sources = {"left": left, "right": right}
    traces = {
        "left": {t.id: t for t in left.traces},
        "right": {t.id: t for t in right.traces},
    }
    links_by_left = defaultdict(list)
    linked_right = set()
    for i, link in enumerate(spec.case_links):
        if (
            link.left_case_id not in traces["left"]
            or link.right_case_id not in traces["right"]
        ):
            return finish(
                issues=(
                    ComputeIssue(
                        "unknown_case_link",
                        f"Relation row {i} references an unknown left/right case",
                    ),
                ),
                status=ComputeStatus.INVALID_INPUT,
            )
        links_by_left[link.left_case_id].append((i, link.right_case_id))
        linked_right.add(link.right_case_id)
    owners = [("left", trace.id) for trace in left.traces]
    if spec.unlinked_right == "retain":
        owners.extend(
            ("right", trace.id)
            for trace in right.traces
            if trace.id not in linked_right
        )
    if len(owners) > spec.max_output_cases:
        return finish(
            issues=(
                ComputeIssue(
                    "merge_case_budget_exceeded",
                    "Output case count exceeds max_output_cases",
                ),
            ),
            status=ComputeStatus.UNAVAILABLE,
        )
    # Count before constructing duplicated event records; never allocate a relation Cartesian table.
    expected_events = sum(len(trace.events) for trace in left.traces)
    expected_events += sum(
        len(traces["right"][link.right_case_id].events) for link in spec.case_links
    )
    if spec.unlinked_right == "retain":
        expected_events += sum(
            len(trace.events) for trace in right.traces if trace.id not in linked_right
        )
    if expected_events > spec.max_output_events:
        return finish(
            issues=(
                ComputeIssue(
                    "merge_event_budget_exceeded",
                    f"{expected_events} output occurrences exceed max_output_events={spec.max_output_events}",
                ),
            ),
            status=ComputeStatus.UNAVAILABLE,
        )
    rows, missing, ties = [], [], []
    used_source_events = set()
    sort_spec = CaseSortSpec(nulls=spec.nulls, ties=spec.ties)
    try:
        for owner_side, owner_id in owners:
            output_case_id = _id("merged-case", digest, spec, owner_side, owner_id)
            incoming = [(owner_side, owner_id, None)]
            if owner_side == "left":
                incoming.extend(
                    ("right", case_id, relation_index)
                    for relation_index, case_id in links_by_left[owner_id]
                )
            records, tie_keys = [], {}
            for side, case_id, relation_index in incoming:
                source_log, trace = sources[side], traces[side][case_id]
                # Validate conflicting defaults before publication/materialization.
                source_log.effective_attributes(trace)
                for position, event in enumerate(trace.events):
                    source_log.effective_attributes(event)
                    identity = _id(
                        "merged-event",
                        output_case_id,
                        side,
                        case_id,
                        event.id,
                        relation_index,
                    )
                    occurrence = MergedEventOccurrence(
                        identity, side, case_id, event.id, position, relation_index
                    )
                    tie_keys[identity] = (
                        side,
                        case_id,
                        event.id,
                        -1 if relation_index is None else relation_index,
                    )
                    timestamp = (
                        _time(
                            source_log,
                            event,
                            spec.left_timestamp_key
                            if side == "left"
                            else spec.right_timestamp_key,
                        )
                        if spec.order == "timestamp"
                        else None
                    )
                    if spec.order == "timestamp" and timestamp is None:
                        missing.append(identity)
                    records.append((identity, timestamp, occurrence))
                    used_source_events.add((side, event.id))
            if spec.order == "timestamp":
                records, current_ties = _ordered(
                    records, sort_spec, "merged_case", output_case_id, tie_keys
                )
                ties.extend(current_ties)
            rows.append(
                MergedCase(
                    output_case_id,
                    owner_side,
                    owner_id,
                    tuple(
                        dict.fromkeys((side, case_id) for side, case_id, _ in incoming)
                    ),
                    tuple(record[2] for record in records),
                )
            )
    except LookupError as exc:
        return finish(
            issues=(ComputeIssue("merge_order_unavailable", str(exc)),),
            status=ComputeStatus.UNAVAILABLE,
        )
    except ValueError as exc:
        return finish(
            issues=(ComputeIssue("ambiguous_attribute", str(exc)),),
            status=ComputeStatus.INVALID_INPUT,
        )
    issues = (
        (
            ComputeIssue(
                "placed_unknown_merge_timestamps",
                f"{len(missing)} timestamp occurrences placed {spec.nulls} by policy; no temporal order claim.",
            ),
        )
        if missing
        else ()
    )
    return finish(
        CaseMergePlan(
            left_digest,
            right_digest,
            tuple(rows),
            tuple(
                trace.id
                for trace in right.traces
                if trace.id not in linked_right and spec.unlinked_right == "exclude"
            ),
            sum(len(t.events) for t in left.traces),
            sum(len(t.events) for t in right.traces),
            expected_events,
            len(used_source_events),
            expected_events - len(used_source_events),
            tuple(missing),
            tuple(ties),
        ),
        issues,
    )


def materialize_merged_cases(
    left: CaseLog, right: CaseLog, plan: ComputationResult[CaseMergePlan]
) -> MergedCaseLog:
    if (
        not isinstance(plan, ComputationResult)
        or plan.operator_id != "pix.case_centric.merge_linked_cases"
        or not isinstance(plan.value, CaseMergePlan)
    ):
        raise ValueError("expected an available linked-case merge plan")
    if not _same_evidence(plan, merge_linked_cases(left, right, plan.spec)):
        raise ValueError(
            "merge plan does not match both sources, relation multiplicity and request"
        )
    sources = {"left": left, "right": right}
    traces = {
        "left": {t.id: t for t in left.traces},
        "right": {t.id: t for t in right.traces},
    }
    output = []
    for row in plan.value.cases:
        owner_log = sources[row.owner_side]
        owner_trace = traces[row.owner_side][row.owner_case_id]
        events = []
        for occurrence in row.events:
            source_log = sources[occurrence.source_side]
            source_trace = traces[occurrence.source_side][occurrence.source_case_id]
            original = source_trace.events[occurrence.source_position]
            events.append(
                CaseEvent(
                    occurrence.output_event_id,
                    source_log.effective_attributes(original),
                )
            )
        output.append(
            CaseTrace(
                row.output_case_id,
                tuple(events),
                owner_log.effective_attributes(owner_trace),
            )
        )
    # Conflicting classifier names are namespaced; all original definitions stay intact in source logs.
    classifiers = tuple(
        replace(c, name=side + ":" + c.name)
        for side, source in sources.items()
        for c in source.classifiers
    )
    extensions = tuple(dict.fromkeys((*left.extensions, *right.extensions)))
    attributes = (
        CaseAttribute("pix:merge:left:log", "container", children=left.attributes),
        CaseAttribute("pix:merge:right:log", "container", children=right.attributes),
    )
    metadata = (
        ("pix:derived", "linked-case-merge"),
        ("pix:left_digest", plan.value.left_digest),
        ("pix:right_digest", plan.value.right_digest),
        *(("left:" + key, value) for key, value in left.metadata),
        *(("right:" + key, value) for key, value in right.metadata),
    )
    derived = CaseLog(
        tuple(output),
        attributes=attributes,
        globals=(),
        extensions=extensions,
        classifiers=classifiers,
        metadata=metadata,
        source=None,
    )
    return MergedCaseLog(derived, left, right, plan)


RESULT_SCHEMAS = {
    "pix.case_centric.sort_case_log": ("case-sort-plan", CaseSortSpec, CaseSortPlan),
    "pix.case_centric.case_log_to_graph": (
        "case-event-graph",
        CaseGraphSpec,
        CaseEventGraph,
    ),
    "pix.case_centric.insert_case_boundaries": (
        "case-boundary-plan",
        BoundarySpec,
        BoundaryPlan,
    ),
    "pix.case_centric.merge_linked_cases": (
        "case-merge-plan",
        CaseMergeSpec,
        CaseMergePlan,
    ),
}

__all__ = [
    "CaseSortSpec",
    "OrderTie",
    "CaseOrder",
    "CaseSortPlan",
    "sort_case_log",
    "materialize_case_sort",
    "CaseGraphSpec",
    "GraphProperty",
    "CaseGraphNode",
    "CaseGraphEdge",
    "CaseEventGraph",
    "case_log_to_graph",
    "BoundarySpec",
    "BoundaryEvent",
    "BoundaryCase",
    "BoundaryPlan",
    "insert_case_boundaries",
    "materialize_case_boundaries",
    "CaseMergeSpec",
    "MergedEventOccurrence",
    "MergedCase",
    "CaseMergePlan",
    "MergedCaseLog",
    "merge_linked_cases",
    "materialize_merged_cases",
]
