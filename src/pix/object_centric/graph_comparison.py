"""OCDFG structural and measure conformance with explicit comparison profiles.

``reference_untyped`` implements the pinned PM4Py 2.7.23.8 comparison formula:
global activities, untyped activity-pair flows, missing-only structural penalties,
and absolute count-difference threshold violations. Flow event-pair counts are
summed over object types. It can hide a flow moved to the wrong object type.

``typed_symmetric`` keeps object type on activities and flows, includes object
type nodes, and penalizes both missing and additional structure. This is a PIX
definition, not silently presented as the reference formula. Neither profile is
alignment fitness. All contributions and exact weighted fractions are exposed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import isfinite
from typing import Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import ObjectCentricDFG, OCDFGSpec
from pix.contracts.result import (
    ComputationResult,
    ComputeStatus,
    _identity_value,
)
from pix.ocel import OCEL


def _number(value: object, name: str) -> None:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a finite nonnegative number")
    if isinstance(value, float) and not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if value < 0:
        raise ValueError(f"{name} must not be negative")


def _names(values: object, name: str, *, blank: bool = False) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) for value in values
    ):
        raise TypeError(f"{name} must be a tuple of strings")
    if not blank and any(not value.strip() for value in values):
        raise ValueError(f"{name} cannot contain blank names")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class OCDFGComparisonSpec:
    profile: Literal["typed_symmetric", "reference_untyped"] = "typed_symmetric"
    activity_measure: Literal["events", "objects", "occurrences"] = "events"
    flow_measure: Literal["event_pairs", "objects", "occurrences"] = "event_pairs"
    activity_threshold: int | float = 0
    flow_threshold: int | float = 0
    activity_structure_weight: int | float = 1
    flow_structure_weight: int | float = 1
    activity_measure_weight: int | float = 1
    flow_measure_weight: int | float = 1
    object_type_weight: int | float | None = None
    zero_domain: Literal["undefined", "one"] = "undefined"
    object_types: tuple[str, ...] | None = None
    qualifiers: tuple[str, ...] | None = None
    tie_policy: Literal["reject", "event_id"] = "reject"

    def __post_init__(self) -> None:
        if self.profile not in ("typed_symmetric", "reference_untyped"):
            raise ValueError("unknown comparison profile")
        if self.activity_measure not in ("events", "objects", "occurrences"):
            raise ValueError("unknown activity measure")
        if self.flow_measure not in ("event_pairs", "objects", "occurrences"):
            raise ValueError("unknown flow measure")
        if self.object_type_weight is None:
            object.__setattr__(
                self,
                "object_type_weight",
                1 if self.profile == "typed_symmetric" else 0,
            )
        for name in (
            "activity_threshold",
            "flow_threshold",
            "activity_structure_weight",
            "flow_structure_weight",
            "activity_measure_weight",
            "flow_measure_weight",
            "object_type_weight",
        ):
            _number(getattr(self, name), name)
        if self.profile == "reference_untyped" and (
            self.activity_measure != "events"
            or self.flow_measure != "event_pairs"
            or self.object_type_weight != 0
        ):
            raise ValueError(
                "reference_untyped uses events/event_pairs and zero type weight"
            )
        if self.zero_domain not in ("undefined", "one"):
            raise ValueError("zero_domain must be undefined or one")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        for name in ("object_types", "qualifiers"):
            values = getattr(self, name)
            if values is not None:
                _names(values, name, blank=name == "qualifiers")
                object.__setattr__(self, name, tuple(sorted(values)))


@dataclass(frozen=True, slots=True)
class OCDFGActivityMeasure:
    object_type: str | None
    activity: str
    events: int
    objects: int
    occurrences: int


@dataclass(frozen=True, slots=True)
class OCDFGFlowMeasure:
    object_type: str
    source_activity: str
    target_activity: str
    event_pairs: int
    objects: int
    occurrences: int


@dataclass(frozen=True, slots=True)
class OCDFGComparisonSnapshot:
    activity_universe: Literal["source_events", "graph_participation"]
    object_types: tuple[str, ...]
    activities: tuple[OCDFGActivityMeasure, ...]
    global_activities: tuple[OCDFGActivityMeasure, ...]
    flows: tuple[OCDFGFlowMeasure, ...]


@dataclass(frozen=True, slots=True)
class OCDFGComparisonRequest:
    parameters: OCDFGComparisonSpec
    observed_digest: str | None
    normative_digest: str | None


@dataclass(frozen=True, slots=True)
class OCDFGMeasureDifference:
    key: tuple[str | None, ...]
    observed: int
    normative: int
    absolute_difference: int
    exceeds_threshold: bool


@dataclass(frozen=True, slots=True)
class WeightedGraphScore:
    """Exact penalty and denominator after decimal interpretation of float weights."""

    penalty_numerator: int
    penalty_denominator: int
    normalization_numerator: int
    normalization_denominator: int
    score_numerator: int | None
    score_denominator: int | None
    zero_domain: bool

    def __post_init__(self) -> None:
        for name in ("penalty_numerator", "normalization_numerator"):
            _count(getattr(self, name), name)
        for name in ("penalty_denominator", "normalization_denominator"):
            _count(getattr(self, name), name, positive=True)
        penalty = Fraction(self.penalty_numerator, self.penalty_denominator)
        normalization = Fraction(
            self.normalization_numerator, self.normalization_denominator
        )
        if penalty > normalization:
            raise ValueError("penalty cannot exceed its normalization")
        if type(self.zero_domain) is not bool or self.zero_domain != (
            normalization == 0
        ):
            raise ValueError("zero-domain marker disagrees with normalization")
        if (self.score_numerator is None) != (self.score_denominator is None):
            raise ValueError(
                "score numerator and denominator must both be present or absent"
            )
        if self.score_numerator is None:
            if normalization:
                raise ValueError("nonempty normalization must have a score")
            return
        _count(self.score_numerator, "score_numerator")
        _count(self.score_denominator, "score_denominator", positive=True)
        score = Fraction(self.score_numerator, self.score_denominator)
        expected = 1 - penalty / normalization if normalization else Fraction(1)
        if score != expected or not 0 <= score <= 1:
            raise ValueError("score is inconsistent with penalty and normalization")

    @property
    def value(self) -> float | None:
        if self.score_numerator is None:
            return None
        return self.score_numerator / self.score_denominator


@dataclass(frozen=True, slots=True)
class OCDFGComparison:
    observed: OCDFGComparisonSnapshot
    normative: OCDFGComparisonSnapshot
    missing_object_types: tuple[str, ...]
    additional_object_types: tuple[str, ...]
    missing_activities: tuple[tuple[str | None, ...], ...]
    additional_activities: tuple[tuple[str | None, ...], ...]
    missing_flows: tuple[tuple[str | None, ...], ...]
    additional_flows: tuple[tuple[str | None, ...], ...]
    activity_differences: tuple[OCDFGMeasureDifference, ...]
    flow_differences: tuple[OCDFGMeasureDifference, ...]
    type_structural_defects: int
    activity_structural_defects: int
    flow_structural_defects: int
    activity_measure_defects: int
    flow_measure_defects: int
    object_type_domain_count: int
    activity_domain_count: int
    flow_domain_count: int
    score: WeightedGraphScore


def _digest(value: object, kind: str) -> str:
    data = json.dumps(
        _identity_value(value),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"pix.{kind}.v1:sha256:" + sha256(data).hexdigest()


def _count(value: object, name: str, *, positive: bool = False) -> None:
    if type(value) is not int or value < (1 if positive else 0):
        raise ValueError(
            f"{name} must be a {'positive' if positive else 'nonnegative'} integer"
        )


def _snapshot(
    graph: ObjectCentricDFG, source_events: tuple[tuple[str, str], ...] | None
) -> OCDFGComparisonSnapshot:
    """Validate the native graph's retained counts against occurrence evidence."""
    if not isinstance(graph.graphs, tuple):
        raise TypeError("OCDFG layers must be immutable")
    layer_types = tuple(layer.object_type for layer in graph.graphs)
    _names(layer_types, "OCDFG layer types")
    global_events: dict[str, set[str]] = defaultdict(set)
    global_objects: dict[str, set[str]] = defaultdict(set)
    global_occurrences: dict[str, int] = defaultdict(int)
    event_activity: dict[str, str] = {}
    object_type: dict[str, str] = {}
    global_successors: dict[str, set[str]] = defaultdict(set)
    typed_activities = []
    flows = []
    occupied_types = []
    for layer in graph.graphs:
        _count(layer.object_count, "object count")
        _names(layer.empty_object_ids, "empty object IDs")
        activity_names = tuple(row.activity for row in layer.activities)
        _names(activity_names, "activity names")
        rows = {row.activity: row for row in layer.activities}
        layer_objects = set(layer.empty_object_ids)
        if layer.object_count:
            occupied_types.append(layer.object_type)
        for row in layer.activities:
            _names(row.distinct_event_ids, "activity event IDs")
            _names(row.object_ids, "activity object IDs")
            _count(row.event_occurrence_count, "activity occurrences", positive=True)
            if not row.distinct_event_ids or not row.object_ids:
                raise ValueError("positive activity requires event and object evidence")
            if (
                not max(len(row.distinct_event_ids), len(row.object_ids))
                <= row.event_occurrence_count
                <= len(row.distinct_event_ids) * len(row.object_ids)
            ):
                raise ValueError("activity occurrence count violates incidence bounds")
            if set(row.object_ids) & set(layer.empty_object_ids):
                raise ValueError("isolated object participates in an activity")
            for event_id in row.distinct_event_ids:
                if (
                    event_id in event_activity
                    and event_activity[event_id] != row.activity
                ):
                    raise ValueError("event ID appears under different activities")
                event_activity[event_id] = row.activity
            layer_objects.update(row.object_ids)
            global_events[row.activity].update(row.distinct_event_ids)
            global_objects[row.activity].update(row.object_ids)
            global_occurrences[row.activity] += row.event_occurrence_count
            typed_activities.append(
                OCDFGActivityMeasure(
                    layer.object_type,
                    row.activity,
                    len(row.distinct_event_ids),
                    len(row.object_ids),
                    row.event_occurrence_count,
                )
            )
        if len(layer_objects) != layer.object_count:
            raise ValueError(
                "object count disagrees with participating and isolated object IDs"
            )
        for object_id in layer_objects:
            if object_id in object_type and object_type[object_id] != layer.object_type:
                raise ValueError("object ID appears in multiple type layers")
            object_type[object_id] = layer.object_type
        edge_keys = set()
        incidences: dict[str, set[tuple[str, str]]] = defaultdict(set)
        successors: dict[tuple[str, str], str] = {}
        predecessors: dict[tuple[str, str], str] = {}
        for edge in layer.edges:
            key = edge.source_activity, edge.target_activity
            if key in edge_keys or edge.object_type != layer.object_type:
                raise ValueError("duplicate edge or incompatible object type")
            edge_keys.add(key)
            if any(activity not in rows for activity in key):
                raise ValueError("flow references undeclared activity")
            unique_occurrences = set()
            pairs = set()
            objects = set()
            for evidence in edge.evidence:
                occurrence = (
                    evidence.object_id,
                    evidence.source_event_id,
                    evidence.target_event_id,
                )
                if (
                    occurrence in unique_occurrences
                    or evidence.source_event_id == evidence.target_event_id
                ):
                    raise ValueError("duplicate or reflexive event occurrence")
                unique_occurrences.add(occurrence)
                global_successors[evidence.source_event_id].add(
                    evidence.target_event_id
                )
                source_node = evidence.object_id, evidence.source_event_id
                target_node = evidence.object_id, evidence.target_event_id
                if (
                    source_node in successors
                    and successors[source_node] != evidence.target_event_id
                ):
                    raise ValueError(
                        "one object-event has multiple directly-following successors"
                    )
                if (
                    target_node in predecessors
                    and predecessors[target_node] != evidence.source_event_id
                ):
                    raise ValueError(
                        "one object-event has multiple directly-following predecessors"
                    )
                successors[source_node] = evidence.target_event_id
                predecessors[target_node] = evidence.source_event_id
                for activity, event_id in (
                    (edge.source_activity, evidence.source_event_id),
                    (edge.target_activity, evidence.target_event_id),
                ):
                    if (
                        event_id not in rows[activity].distinct_event_ids
                        or evidence.object_id not in rows[activity].object_ids
                    ):
                        raise ValueError(
                            "flow occurrence is outside its activity evidence"
                        )
                    incidences[activity].add((evidence.object_id, event_id))
                for event_id, relations in (
                    (evidence.source_event_id, evidence.source_relations),
                    (evidence.target_event_id, evidence.target_relations),
                ):
                    if not relations or any(
                        relation.event != event_id
                        or relation.object != evidence.object_id
                        for relation in relations
                    ):
                        raise ValueError(
                            "flow occurrence has inconsistent qualified relation evidence"
                        )
                    if len(set(relations)) != len(relations):
                        raise ValueError("duplicate qualified relation evidence")
                pairs.add((evidence.source_event_id, evidence.target_event_id))
                objects.add(evidence.object_id)
            for actual, expected in (
                (edge.event_pair_count, len(pairs)),
                (edge.unique_object_count, len(objects)),
                (edge.occurrence_count, len(unique_occurrences)),
            ):
                _count(actual, "flow count", positive=True)
                if actual != expected:
                    raise ValueError("flow count disagrees with occurrence evidence")
            flows.append(
                OCDFGFlowMeasure(
                    layer.object_type,
                    *key,
                    len(pairs),
                    len(objects),
                    len(unique_occurrences),
                )
            )
        boundaries: list[dict[str, str]] = []
        for boundary_rows in (layer.starts, layer.ends):
            _names(tuple(row.activity for row in boundary_rows), "boundary activities")
            boundary: dict[str, str] = {}
            for row in boundary_rows:
                if row.activity not in rows or not row.evidence:
                    raise ValueError("boundary requires declared activity and evidence")
                for evidence in row.evidence:
                    if evidence.object_id in boundary:
                        raise ValueError("object has duplicate lifecycle boundaries")
                    if (
                        evidence.object_id not in rows[row.activity].object_ids
                        or evidence.event_id
                        not in rows[row.activity].distinct_event_ids
                    ):
                        raise ValueError("boundary is outside activity evidence")
                    boundary[evidence.object_id] = evidence.event_id
                    incidences[row.activity].add(
                        (evidence.object_id, evidence.event_id)
                    )
            boundaries.append(boundary)
        participating_objects = layer_objects - set(layer.empty_object_ids)
        starts, ends = boundaries
        if set(starts) != participating_objects or set(ends) != participating_objects:
            raise ValueError("each participating object needs one start and one end")
        events_per_object: dict[str, set[str]] = defaultdict(set)
        for activity, row in rows.items():
            observed = incidences[activity]
            if (
                row.event_occurrence_count != len(observed)
                or set(row.distinct_event_ids) != {event for obj, event in observed}
                or set(row.object_ids) != {obj for obj, event in observed}
            ):
                raise ValueError(
                    "activity count disagrees with edge and boundary incidence evidence"
                )
            for object_id, event_id in observed:
                events_per_object[object_id].add(event_id)
        for object_id in participating_objects:
            if (object_id, starts[object_id]) in predecessors or (
                object_id,
                ends[object_id],
            ) in successors:
                raise ValueError(
                    "boundary events disagree with predecessor/successor structure"
                )
            event_id = starts[object_id]
            visited = set()
            while event_id is not None:
                if event_id in visited:
                    raise ValueError("object event sequence contains a cycle")
                visited.add(event_id)
                following = successors.get((object_id, event_id))
                if following is None and event_id != ends[object_id]:
                    raise ValueError("object path does not finish at its end boundary")
                event_id = following
            if visited != events_per_object[object_id]:
                raise ValueError("object event evidence is not one complete path")
    # One source event has one timestamp/order position shared across objects.
    # Individually valid object paths may still impose contradictory global order.
    indegree = dict.fromkeys(event_activity, 0)
    for targets in global_successors.values():
        for target in targets:
            indegree[target] += 1
    ready = [event_id for event_id, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ready:
        event_id = ready.pop()
        visited_count += 1
        for target in global_successors.get(event_id, ()):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
    if visited_count != len(indegree):
        raise ValueError("object paths impose a cyclic global event order")
    if source_events is not None:
        orphan_events: dict[str, set[str]] = defaultdict(set)
        for event_id, name in source_events:
            global_events.setdefault(name, set())
            global_objects.setdefault(name, set())
            global_occurrences.setdefault(name, 0)
            if event_id not in global_events[name]:
                orphan_events[name].add(event_id)
        # Corrected typed profile explicitly keeps events with no selected E2O.
        # They have event mass but no objects or event-object occurrences.
        # Reference global rows intentionally remain E2O-derived, including zero.
        typed_activities.extend(
            OCDFGActivityMeasure(None, name, len(events), 0, 0)
            for name, events in sorted(orphan_events.items())
        )
    return OCDFGComparisonSnapshot(
        "source_events" if source_events is not None else "graph_participation",
        tuple(sorted(occupied_types)),
        tuple(
            sorted(
                typed_activities,
                key=lambda row: (
                    row.object_type is not None,
                    row.object_type or "",
                    row.activity,
                ),
            )
        ),
        tuple(
            OCDFGActivityMeasure(
                None,
                name,
                len(global_events[name]),
                len(global_objects[name]),
                global_occurrences[name],
            )
            for name in sorted(global_events)
        ),
        tuple(
            sorted(
                flows,
                key=lambda row: (
                    row.object_type,
                    row.source_activity,
                    row.target_activity,
                ),
            )
        ),
    )


def _prepare_graph(
    value: OCEL | ComputationContext | ObjectCentricDFG, spec: OCDFGComparisonSpec
):
    if isinstance(value, ObjectCentricDFG):
        if spec.object_types is not None or spec.qualifiers is not None:
            raise ValueError(
                "graph inputs are already projected; selectors require an OCEL source"
            )
        return _snapshot(value, None), _digest(value, "ocdfg-input"), (), ()
    context, issues = _prepare(value)
    if context is None:
        return None, None, issues, ()
    selected = (
        tuple(sorted(context.objects_by_type))
        if spec.object_types is None
        else spec.object_types
    )
    if not selected:
        graph = ObjectCentricDFG(())
        parents = ()
    else:
        result = discover_ocdfg(
            context, OCDFGSpec(selected, spec.qualifiers, spec.tie_policy)
        )
        if result.value is None:
            return None, context.source_digest, result.issues, ()
        graph = result.value
        parents = (result.computation_id,)
    return (
        _snapshot(graph, tuple((event.id, event.type) for event in context.log.events)),
        context.source_digest,
        (),
        parents,
    )


def _measures(snapshot: OCDFGComparisonSnapshot, spec: OCDFGComparisonSpec):
    typed = spec.profile == "typed_symmetric"
    rows = snapshot.activities if typed else snapshot.global_activities
    activities = {
        (row.object_type, row.activity) if typed else (row.activity,): getattr(
            row, spec.activity_measure
        )
        for row in rows
    }
    flows: dict[tuple[str, ...], int] = defaultdict(int)
    for row in snapshot.flows:
        key = (
            (row.object_type, row.source_activity, row.target_activity)
            if typed
            else (row.source_activity, row.target_activity)
        )
        flows[key] += getattr(row, spec.flow_measure)
    return activities, dict(flows)


def _sort(keys):
    return tuple(
        sorted(
            keys,
            key=lambda key: tuple((value is not None, value or "") for value in key),
        )
    )


def _differences(observed, normative, threshold):
    return tuple(
        OCDFGMeasureDifference(
            key,
            observed.get(key, 0),
            normative.get(key, 0),
            abs(observed.get(key, 0) - normative.get(key, 0)),
            abs(observed.get(key, 0) - normative.get(key, 0)) > threshold,
        )
        for key in _sort(observed.keys() | normative.keys())
    )


def compare_ocdfgs(
    observed: OCEL | ComputationContext | ObjectCentricDFG,
    normative: OCEL | ComputationContext | ObjectCentricDFG,
    spec: OCDFGComparisonSpec = OCDFGComparisonSpec(),
) -> ComputationResult[OCDFGComparison]:
    """Compare native OCDFG evidence or derive it from validated canonical OCEL.

    Raw OCEL keeps every source activity label, even if it has no selected E2O.
    Native graph inputs can only expose participating activity labels; their
    snapshot records this smaller universe. Empty declared types without objects
    are excluded from the type domain. Graph count/evidence contradictions are
    rejected. Negative/nonfinite weights are rejected rather than score-clamped.

    A penalty triggers only when absolute difference STRICTLY exceeds threshold.
    Float weights are interpreted through their decimal string, then calculated
    as exact rational numbers. Undefined normalization (including all-zero
    weights) stays undefined unless zero_domain='one' is explicitly selected.
    """
    if not isinstance(spec, OCDFGComparisonSpec):
        raise TypeError("spec must be OCDFGComparisonSpec")
    left, left_digest, left_issues, left_parents = _prepare_graph(observed, spec)
    right, right_digest, right_issues, right_parents = _prepare_graph(normative, spec)
    request = OCDFGComparisonRequest(spec, left_digest, right_digest)
    if left is None or right is None:
        issues = left_issues + right_issues
        return _result(
            "pix.object_centric.compare_ocdfgs",
            None,
            request,
            ComputeStatus.INVALID_INPUT
            if left_digest is None or right_digest is None
            else ComputeStatus.UNAVAILABLE,
            None,
            issues,
            source_digest=None
            if left_digest is None or right_digest is None
            else _digest(request, "ocdfg-comparison-input"),
        )
    acts_left, flows_left = _measures(left, spec)
    acts_right, flows_right = _measures(right, spec)
    missing_activities = _sort(acts_right.keys() - acts_left.keys())
    additional_activities = _sort(acts_left.keys() - acts_right.keys())
    missing_flows = _sort(flows_right.keys() - flows_left.keys())
    additional_flows = _sort(flows_left.keys() - flows_right.keys())
    missing_types = tuple(sorted(set(right.object_types) - set(left.object_types)))
    additional_types = tuple(sorted(set(left.object_types) - set(right.object_types)))
    activity_differences = _differences(acts_left, acts_right, spec.activity_threshold)
    flow_differences = _differences(flows_left, flows_right, spec.flow_threshold)
    symmetric = spec.profile == "typed_symmetric"
    type_defects = len(missing_types) + len(additional_types) if symmetric else 0
    activity_defects = len(missing_activities) + (
        len(additional_activities) if symmetric else 0
    )
    flow_defects = len(missing_flows) + (len(additional_flows) if symmetric else 0)
    activity_measure_defects = sum(
        row.exceeds_threshold for row in activity_differences
    )
    flow_measure_defects = sum(row.exceeds_threshold for row in flow_differences)
    type_domain = len(set(left.object_types) | set(right.object_types))
    activity_domain = len(acts_left.keys() | acts_right.keys())
    flow_domain = len(flows_left.keys() | flows_right.keys())
    weights = tuple(
        Fraction(str(getattr(spec, name)))
        for name in (
            "object_type_weight",
            "activity_structure_weight",
            "flow_structure_weight",
            "activity_measure_weight",
            "flow_measure_weight",
        )
    )
    defects = (
        type_defects,
        activity_defects,
        flow_defects,
        activity_measure_defects,
        flow_measure_defects,
    )
    domains = (type_domain, activity_domain, flow_domain, activity_domain, flow_domain)
    penalty = sum(
        (weight * count for weight, count in zip(weights, defects)), Fraction()
    )
    normalization = sum(
        (weight * count for weight, count in zip(weights, domains)), Fraction()
    )
    score = (
        1 - penalty / normalization
        if normalization
        else (Fraction(1) if spec.zero_domain == "one" else None)
    )
    if score is not None and not 0 <= score <= 1:
        raise AssertionError(
            "nonnegative bounded defect counts must yield a score in [0,1]"
        )
    value = OCDFGComparison(
        left,
        right,
        missing_types,
        additional_types,
        missing_activities,
        additional_activities,
        missing_flows,
        additional_flows,
        activity_differences,
        flow_differences,
        type_defects,
        activity_defects,
        flow_defects,
        activity_measure_defects,
        flow_measure_defects,
        type_domain,
        activity_domain,
        flow_domain,
        WeightedGraphScore(
            penalty.numerator,
            penalty.denominator,
            normalization.numerator,
            normalization.denominator,
            None if score is None else score.numerator,
            None if score is None else score.denominator,
            not normalization,
        ),
    )
    return _result(
        "pix.object_centric.compare_ocdfgs",
        None,
        request,
        ComputeStatus.COMPUTED,
        value,
        source_digest=_digest(request, "ocdfg-comparison-input"),
        parent_computation_ids=left_parents + right_parents,
    )


RESULT_SCHEMAS = {
    "pix.object_centric.compare_ocdfgs": (
        "ocdfg-comparison",
        OCDFGComparisonRequest,
        OCDFGComparison,
    )
}

__all__ = [
    "OCDFGComparisonSpec",
    "OCDFGActivityMeasure",
    "OCDFGFlowMeasure",
    "OCDFGComparisonSnapshot",
    "OCDFGComparisonRequest",
    "OCDFGMeasureDifference",
    "WeightedGraphScore",
    "OCDFGComparison",
    "compare_ocdfgs",
]
