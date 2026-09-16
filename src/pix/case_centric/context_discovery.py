"""Consecutive activity triples and case-attribute conditioned DFG statistics.

The pinned PM4Py FREQ_TRIPLES variant counts consecutive triples at every source
position. CASE_ATTRIBUTES counts each edge occurrence (and optionally each node
occurrence), not one vote per distinct case. PIX retains both occurrence and case
counts with exact source witnesses. Missing attributes remain explicit bins, and
edges without an observed selected attribute are retained in the topology.

CaseLog.attribute resolves recorded values and XES globals. Attribute grouping is
typed: bool/int/float/string do not collapse, null is distinct from absence, and
lexical spellings do not split equal values. Structured values preserve ordered
children; primitive metadata is not part of the scalar value. This is a PIX
extension beyond the reference's dictionary-key representation. No upstream
library is imported, executed, or needed at runtime.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseLog, case_traces


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _strings(
    value: object, name: str, *, unique: bool = True, blank: bool = False
) -> None:
    if not isinstance(value, tuple) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{name} must be a tuple of strings")
    if not blank and any(not item.strip() for item in value):
        raise ValueError(f"{name} must contain nonblank strings")
    if unique and len(set(value)) != len(value):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class ActivityTripleSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_witnesses: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        _integer(self.max_witnesses, "max_witnesses", 1)


@dataclass(frozen=True, slots=True)
class ContextWitness:
    case_id: str
    event_ids: tuple[str, ...]
    start_position: int

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id.strip():
            raise ValueError("case_id must be nonblank text")
        _strings(self.event_ids, "event_ids")
        if len(self.event_ids) not in (1, 2, 3):
            raise ValueError("a context witness has one, two, or three events")
        _integer(self.start_position, "start_position")


def _validate_witnesses(activities, witnesses, occurrence_count, case_count):
    _strings(activities, "activities", unique=False)
    if not isinstance(witnesses, tuple) or not all(
        isinstance(witness, ContextWitness) for witness in witnesses
    ):
        raise TypeError("witnesses must be ContextWitness tuples")
    _integer(occurrence_count, "occurrence_count", 1)
    _integer(case_count, "case_count", 1)
    if any(len(witness.event_ids) != len(activities) for witness in witnesses):
        raise ValueError("witness arity must match the activity tuple")
    if occurrence_count != len(witnesses) or case_count != len(
        {witness.case_id for witness in witnesses}
    ):
        raise ValueError("occurrence and case counts must match their witnesses")
    keys = tuple((witness.case_id, witness.start_position) for witness in witnesses)
    if len(set(keys)) != len(keys):
        raise ValueError("a relation cannot count one source occurrence twice")


def _witness_positions(rows):
    """Validate consistent activity/event identity at every observed case position."""
    positions, identities = {}, {}
    for row in rows:
        for witness in row.witnesses:
            for offset, (event_id, activity) in enumerate(
                zip(witness.event_ids, row.activities)
            ):
                position = (witness.case_id, witness.start_position + offset)
                observed = (event_id, activity)
                if position in positions and positions[position] != observed:
                    raise ValueError(
                        "overlapping witnesses disagree on event identity or activity"
                    )
                if event_id in identities and identities[event_id] != position:
                    raise ValueError(
                        "event identity appears at different source positions"
                    )
                positions[position] = observed
                identities[event_id] = position
    return positions


def _complete_relation_lengths(rows, width):
    """All observed consecutive windows imply a contiguous range starting at zero."""
    starts = defaultdict(set)
    for row in rows:
        for witness in row.witnesses:
            starts[witness.case_id].add(witness.start_position)
    lengths = {}
    for case_id, values in starts.items():
        if min(values) != 0 or len(values) != max(values) + 1:
            raise ValueError(
                "complete context relation evidence must cover consecutive source positions"
            )
        lengths[case_id] = max(values) + width
    return lengths


@dataclass(frozen=True, slots=True)
class ActivityTriple:
    activities: tuple[str, str, str]
    occurrence_count: int
    case_count: int
    witnesses: tuple[ContextWitness, ...]

    def __post_init__(self) -> None:
        if len(self.activities) != 3:
            raise ValueError("activity triples contain exactly three labels")
        _validate_witnesses(
            self.activities, self.witnesses, self.occurrence_count, self.case_count
        )


@dataclass(frozen=True, slots=True)
class ActivityTripleSet:
    case_ids: tuple[str, ...]
    event_count: int
    eligible_case_ids: tuple[str, ...]
    occurrence_count: int
    triples: tuple[ActivityTriple, ...]

    def __post_init__(self) -> None:
        _strings(self.case_ids, "case_ids")
        _strings(self.eligible_case_ids, "eligible_case_ids")
        _integer(self.event_count, "event_count")
        _integer(self.occurrence_count, "occurrence_count")
        if not isinstance(self.triples, tuple) or not all(
            isinstance(row, ActivityTriple) for row in self.triples
        ):
            raise TypeError("triples must be ActivityTriple tuples")
        if not set(self.eligible_case_ids) <= set(self.case_ids):
            raise ValueError("eligible cases must be in the requested population")
        if self.occurrence_count != sum(row.occurrence_count for row in self.triples):
            raise ValueError(
                "triple frequencies must conserve the occurrence population"
            )
        labels = tuple(row.activities for row in self.triples)
        if labels != tuple(sorted(set(labels))):
            raise ValueError("activity triple rows must be unique and sorted")
        witnesses = tuple(witness for row in self.triples for witness in row.witnesses)
        if {witness.case_id for witness in witnesses} != set(self.eligible_case_ids):
            raise ValueError("eligible case coverage must match triple witnesses")
        if len(
            {(witness.case_id, witness.start_position) for witness in witnesses}
        ) != len(witnesses):
            raise ValueError("triple source occurrences must be disjoint between rows")
        _witness_positions(self.triples)
        lengths = _complete_relation_lengths(self.triples, 3)
        minimum_events = sum(lengths.values())
        maximum_events = minimum_events + 2 * (len(self.case_ids) - len(lengths))
        if not minimum_events <= self.event_count <= maximum_events:
            raise ValueError(
                "event population disagrees with complete triple witness positions"
            )


def _finish(parent, operator, spec, value=None, issues=(), *, status=None):
    parents = (parent.computation_id,) if parent.computation_id else ()
    if parent.value is None:
        return _derived_result(
            operator,
            parent.source_digest,
            spec,
            parent.status,
            None,
            parent.issues,
            parent_computation_ids=parents,
        )
    selected_status = status or (
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED
    )
    return _derived_result(
        operator,
        parent.source_digest,
        spec,
        selected_status,
        value,
        parent.issues + tuple(issues),
        parent_computation_ids=parents,
    )


def discover_activity_triples(
    log: CaseLog, spec: ActivityTripleSpec = ActivityTripleSpec()
) -> ComputationResult[ActivityTripleSet]:
    """Count every overlapping source-order length-three window within each case."""
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, ActivityTripleSpec):
        raise TypeError("spec must be ActivityTripleSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_activity_triples"
    if parent.value is None:
        return _finish(parent, operator, spec)
    occurrence_count = sum(
        max(0, len(trace.events) - 2) for trace in parent.value.traces
    )
    if occurrence_count > spec.max_witnesses:
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "context_witness_limit",
                    "Complete triple witnesses exceed max_witnesses; no truncated frequency table is returned",
                ),
            ),
            status=ComputeStatus.UNAVAILABLE,
        )
    groups = defaultdict(list)
    for trace in parent.value.traces:
        for index in range(len(trace.events) - 2):
            events = trace.events[index : index + 3]
            groups[tuple(event.activity for event in events)].append(
                ContextWitness(
                    trace.object_id, tuple(event.event_id for event in events), index
                )
            )
    triples = tuple(
        ActivityTriple(
            activities,
            len(witnesses),
            len({witness.case_id for witness in witnesses}),
            tuple(witnesses),
        )
        for activities, witnesses in sorted(groups.items())
    )
    payload = ActivityTripleSet(
        tuple(trace.object_id for trace in parent.value.traces),
        sum(len(trace.events) for trace in parent.value.traces),
        tuple(
            trace.object_id for trace in parent.value.traces if len(trace.events) >= 3
        ),
        occurrence_count,
        triples,
    )
    return _finish(parent, operator, spec, payload)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _attribute_value(attribute: CaseAttribute):
    kind, value = attribute.type, attribute.value
    if kind == "int":
        return hex(value)
    if kind == "float":
        return value.hex()
    if kind == "date":
        offset = value.utcoffset()
        if offset is None:
            return ["naive", value.isoformat(timespec="microseconds")]
        difference = value.replace(tzinfo=None) - datetime(1970, 1, 1) - offset
        microseconds = (
            difference.days * 86400 + difference.seconds
        ) * 1000000 + difference.microseconds
        return ["utc_microseconds", hex(microseconds)]
    if kind in ("list", "container"):
        children = attribute.values if kind == "list" else attribute.children
        return [
            [child.key, [child.type, _attribute_value(child)]] for child in children
        ]
    return value


def _validate_attribute_value(kind, value, depth=0):
    if depth > 128:
        raise ValueError("attribute value exceeds structural depth limit")
    if kind in ("string", "id"):
        valid = isinstance(value, str)
    elif kind == "int":
        valid = isinstance(value, str) and hex(int(value, 16)) == value
    elif kind == "float":
        valid = isinstance(value, str) and float.fromhex(value).hex() == value
    elif kind == "boolean":
        valid = type(value) is bool
    elif kind == "null":
        valid = value is None
    elif kind == "date":
        valid = (
            isinstance(value, list)
            and len(value) == 2
            and all(isinstance(part, str) for part in value)
        )
        if valid and value[0] == "utc_microseconds":
            valid = hex(int(value[1], 16)) == value[1]
        elif valid and value[0] == "naive":
            date = datetime.fromisoformat(value[1])
            valid = (
                date.utcoffset() is None
                and date.isoformat(timespec="microseconds") == value[1]
            )
        else:
            valid = False
    elif kind in ("list", "container"):
        valid = isinstance(value, list)
        if valid:
            for member in value:
                if (
                    not isinstance(member, list)
                    or len(member) != 2
                    or not isinstance(member[0], str)
                    or not isinstance(member[1], list)
                    or len(member[1]) != 2
                ):
                    valid = False
                    break
                _validate_attribute_value(member[1][0], member[1][1], depth + 1)
    else:
        valid = False
    if not valid:
        raise ValueError("invalid typed case attribute representation")


@dataclass(frozen=True, slots=True)
class CaseAttributeValue:
    type: str
    value_json: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, str) or not isinstance(self.value_json, str):
            raise TypeError("typed value requires string type and value_json")
        value = json.loads(self.value_json)
        _validate_attribute_value(self.type, value)
        if _json(value) != self.value_json:
            raise ValueError("typed value JSON must be canonical")


@dataclass(frozen=True, slots=True)
class CaseAttributeBin:
    value: CaseAttributeValue | None
    occurrence_count: int
    case_count: int
    case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.value is not None and not isinstance(self.value, CaseAttributeValue):
            raise TypeError("value must be CaseAttributeValue or None (absent)")
        _integer(self.occurrence_count, "occurrence_count", 1)
        _integer(self.case_count, "case_count", 1)
        _strings(self.case_ids, "case_ids")
        if (
            self.case_count != len(self.case_ids)
            or self.occurrence_count < self.case_count
        ):
            raise ValueError("attribute bin counts disagree with the case population")


@dataclass(frozen=True, slots=True)
class CaseAttributeDistribution:
    key: str
    bins: tuple[CaseAttributeBin, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.key, str):
            raise TypeError("attribute key must be str")
        if not isinstance(self.bins, tuple) or not all(
            isinstance(item, CaseAttributeBin) for item in self.bins
        ):
            raise TypeError("bins must be CaseAttributeBin tuples")
        values = tuple(item.value for item in self.bins)
        if len(set(values)) != len(values):
            raise ValueError("attribute values must have unique bins")
        cases = tuple(case_id for item in self.bins for case_id in item.case_ids)
        if len(set(cases)) != len(cases):
            raise ValueError("a case has one value or one missing bin for an attribute")


@dataclass(frozen=True, slots=True)
class AttributedSequenceRelation:
    activities: tuple[str, ...]
    occurrence_count: int
    case_count: int
    witnesses: tuple[ContextWitness, ...]
    attributes: tuple[CaseAttributeDistribution, ...]

    def __post_init__(self) -> None:
        if len(self.activities) not in (1, 2):
            raise ValueError(
                "attributed relations have one node or two edge activities"
            )
        _validate_witnesses(
            self.activities, self.witnesses, self.occurrence_count, self.case_count
        )
        if not isinstance(self.attributes, tuple) or not all(
            isinstance(item, CaseAttributeDistribution) for item in self.attributes
        ):
            raise TypeError("attributes must be CaseAttributeDistribution tuples")
        if len({item.key for item in self.attributes}) != len(self.attributes):
            raise ValueError("relation attribute keys must be unique")
        counts = defaultdict(int)
        for witness in self.witnesses:
            counts[witness.case_id] += 1
        for distribution in self.attributes:
            if {
                case_id for item in distribution.bins for case_id in item.case_ids
            } != set(counts):
                raise ValueError("attribute bins must cover every relation case")
            for item in distribution.bins:
                if item.occurrence_count != sum(
                    counts[case_id] for case_id in item.case_ids
                ):
                    raise ValueError(
                        "attribute frequency must count actual relation occurrences"
                    )


@dataclass(frozen=True, slots=True)
class CaseAttributeDFGSpec:
    case_attributes: tuple[str, ...] = ("concept:name",)
    include_nodes: bool = False
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_witnesses: int = 1000000
    max_annotation_occurrences: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _strings(self.case_attributes, "case_attributes", blank=True)
        if type(self.include_nodes) is not bool:
            raise TypeError("include_nodes must be bool")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        _integer(self.max_witnesses, "max_witnesses", 1)
        _integer(self.max_annotation_occurrences, "max_annotation_occurrences", 1)


@dataclass(frozen=True, slots=True)
class CaseAttributeDFG:
    case_ids: tuple[str, ...]
    event_count: int
    edge_occurrence_count: int
    case_attributes: tuple[str, ...]
    nodes_included: bool
    edges: tuple[AttributedSequenceRelation, ...]
    nodes: tuple[AttributedSequenceRelation, ...]

    def __post_init__(self) -> None:
        _strings(self.case_ids, "case_ids")
        _strings(self.case_attributes, "case_attributes", blank=True)
        _integer(self.event_count, "event_count")
        _integer(self.edge_occurrence_count, "edge_occurrence_count")
        if type(self.nodes_included) is not bool:
            raise TypeError("nodes_included must be bool")
        if not self.nodes_included and self.nodes:
            raise ValueError("node annotations were not requested")
        selected_cases = set(self.case_ids)
        for rows, arity in ((self.edges, 2), (self.nodes, 1)):
            if not isinstance(rows, tuple) or not all(
                isinstance(row, AttributedSequenceRelation) for row in rows
            ):
                raise TypeError("relations must be AttributedSequenceRelation tuples")
            keys = tuple(row.activities for row in rows)
            if keys != tuple(sorted(set(keys))) or any(
                len(key) != arity for key in keys
            ):
                raise ValueError(
                    "relation rows require unique sorted labels and correct arity"
                )
            witnesses = tuple(witness for row in rows for witness in row.witnesses)
            if any(witness.case_id not in selected_cases for witness in witnesses):
                raise ValueError("witness case not in requested population")
            if len(
                {(witness.case_id, witness.start_position) for witness in witnesses}
            ) != len(witnesses):
                raise ValueError(
                    "source occurrences must be disjoint between relation rows"
                )
            if any(
                tuple(item.key for item in row.attributes) != self.case_attributes
                for row in rows
            ):
                raise ValueError("every relation must contain the selected attributes")
        if self.edge_occurrence_count != sum(
            row.occurrence_count for row in self.edges
        ):
            raise ValueError("edge counts must conserve the observed edge population")
        if self.nodes_included and self.event_count != sum(
            row.occurrence_count for row in self.nodes
        ):
            raise ValueError("node counts must conserve the observed event population")
        _witness_positions(self.edges + self.nodes)
        edge_lengths = _complete_relation_lengths(self.edges, 2)
        if self.nodes_included:
            node_lengths = _complete_relation_lengths(self.nodes, 1)
            expected_edge_lengths = {
                case_id: length
                for case_id, length in node_lengths.items()
                if length >= 2
            }
            if edge_lengths != expected_edge_lengths:
                raise ValueError(
                    "complete node and edge evidence disagree on case lengths"
                )
        else:
            minimum_events = sum(edge_lengths.values())
            maximum_events = minimum_events + len(self.case_ids) - len(edge_lengths)
            if not minimum_events <= self.event_count <= maximum_events:
                raise ValueError(
                    "event population disagrees with complete edge witness positions"
                )


def discover_case_attribute_dfg(
    log: CaseLog, spec: CaseAttributeDFGSpec = CaseAttributeDFGSpec()
) -> ComputationResult[CaseAttributeDFG]:
    """Annotate observed edges/nodes with occurrence and distinct-case histograms.

    The default case attribute is the recorded/global ``concept:name``; internal
    trace identity is never substituted when that business attribute is absent.
    Missing bins are explicit and produce PARTIAL coverage. Known null is a typed
    value, not missing. Repeated edges in one case increase occurrence_count but
    not case_count. Scalar metadata/lexical spellings do not affect grouping.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, CaseAttributeDFGSpec):
        raise TypeError("spec must be CaseAttributeDFGSpec")
    parent = case_traces(log, spec.trace_spec)
    operator = "pix.case_centric.discover_case_attribute_dfg"
    if parent.value is None:
        return _finish(parent, operator, spec)
    event_count = sum(len(trace.events) for trace in parent.value.traces)
    edge_count = sum(max(0, len(trace.events) - 1) for trace in parent.value.traces)
    witness_count = edge_count + (event_count if spec.include_nodes else 0)
    if (
        witness_count > spec.max_witnesses
        or witness_count * len(spec.case_attributes) > spec.max_annotation_occurrences
    ):
        return _finish(
            parent,
            operator,
            spec,
            issues=(
                ComputeIssue(
                    "context_witness_limit",
                    "Complete attributed relation witnesses/annotations exceed their limits; no truncated histogram is returned",
                ),
            ),
            status=ComputeStatus.UNAVAILABLE,
        )
    issues, attributes, edges, nodes = [], {}, defaultdict(list), defaultdict(list)
    try:
        for raw_trace, trace in zip(log.traces, parent.value.traces):
            values = {}
            for key in spec.case_attributes:
                attribute = log.attribute(raw_trace, key)
                value = (
                    CaseAttributeValue(
                        attribute.type, _json(_attribute_value(attribute))
                    )
                    if attribute is not None
                    else None
                )
                values[key] = value
                if value is None and (
                    len(trace.events) >= 2 or (spec.include_nodes and trace.events)
                ):
                    issues.append(
                        ComputeIssue(
                            "missing_case_attribute",
                            "Selected case attribute is absent; affected relation occurrences remain in explicit missing bins",
                            (trace.object_id, key),
                        )
                    )
            attributes[trace.object_id] = values
            for index in range(len(trace.events) - 1):
                pair = trace.events[index : index + 2]
                edges[tuple(event.activity for event in pair)].append(
                    ContextWitness(
                        trace.object_id, tuple(event.event_id for event in pair), index
                    )
                )
            if spec.include_nodes:
                for index, event in enumerate(trace.events):
                    nodes[(event.activity,)].append(
                        ContextWitness(trace.object_id, (event.event_id,), index)
                    )
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return _finish(
            parent,
            operator,
            spec,
            issues=(ComputeIssue("invalid_case_attribute", str(error)),),
            status=ComputeStatus.INVALID_INPUT,
        )

    def build(groups):
        rows = []
        for labels, witnesses in sorted(groups.items()):
            distributions = []
            for key in spec.case_attributes:
                bins = defaultdict(list)
                for witness in witnesses:
                    bins[attributes[witness.case_id][key]].append(witness.case_id)
                ordered_bins = sorted(
                    bins,
                    key=lambda value: (
                        value is not None,
                        value.type if value else "",
                        value.value_json if value else "",
                    ),
                )
                distributions.append(
                    CaseAttributeDistribution(
                        key,
                        tuple(
                            CaseAttributeBin(
                                value,
                                len(bins[value]),
                                len(set(bins[value])),
                                tuple(sorted(set(bins[value]))),
                            )
                            for value in ordered_bins
                        ),
                    )
                )
            rows.append(
                AttributedSequenceRelation(
                    labels,
                    len(witnesses),
                    len({witness.case_id for witness in witnesses}),
                    tuple(witnesses),
                    tuple(distributions),
                )
            )
        return tuple(rows)

    payload = CaseAttributeDFG(
        tuple(trace.object_id for trace in parent.value.traces),
        event_count,
        edge_count,
        spec.case_attributes,
        spec.include_nodes,
        build(edges),
        build(nodes),
    )
    return _finish(parent, operator, spec, payload, issues)


RESULT_SCHEMAS = {
    "pix.case_centric.discover_activity_triples": (
        "case-activity-triples",
        ActivityTripleSpec,
        ActivityTripleSet,
    ),
    "pix.case_centric.discover_case_attribute_dfg": (
        "case-attribute-dfg",
        CaseAttributeDFGSpec,
        CaseAttributeDFG,
    ),
}

__all__ = [
    "ActivityTripleSpec",
    "ContextWitness",
    "ActivityTriple",
    "ActivityTripleSet",
    "discover_activity_triples",
    "CaseAttributeValue",
    "CaseAttributeBin",
    "CaseAttributeDistribution",
    "AttributedSequenceRelation",
    "CaseAttributeDFGSpec",
    "CaseAttributeDFG",
    "discover_case_attribute_dfg",
]
