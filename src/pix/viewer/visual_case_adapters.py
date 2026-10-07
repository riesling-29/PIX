"""Typed case-centric views of existing observations and calculation evidence.

Adapters never run mining, infer absent timestamps, or turn search limits into
negative facts. Model views (including footprints and transition systems) live
in ``visual_model_adapters``. Labels are data; escaping belongs to renderers.
"""

from __future__ import annotations

import json
from datetime import timezone

from pix.case_centric.advanced import DecisionTree
from pix.case_centric.alignment_search import SearchAlignmentSet
from pix.case_centric.approximate_alignment import ApproximateAlignmentSet
from pix.case_centric.declarative import FootprintConformance
from pix.case_centric.discovery import CaseRelationGraph, RelationDiscoverySpec
from pix.case_centric.organization import AttributeNetwork, NetworkPayload, RoleSet
from pix.case_centric.sequence_alignment import DFGAlignmentSet, SequenceAlignmentSet
from pix.case_centric.statistics import (
    AttributeStatistics,
    CasePerformance,
    CasePerformanceSpec,
    CaseStatistics,
    EventDistribution,
    EventDistributionSpec,
    IntervalEventuallyFollows,
    NumericAttributeSpec,
    NumericAttributeStatistics,
    PerformanceSpectrum,
    PerformanceSpectrumSpec,
    StatisticsSpec,
)
from pix.case_centric.tree_alignment import TreeAlignmentSet
from pix.contracts.conformance import AlignmentSet
from pix.contracts.replay import ReplaySet
from pix.contracts.result import ComputationResult
from pix.event_log.model import CaseLog

from .visual_contracts import (
    ChartPanel,
    ChartPoint,
    ChartSeries,
    GraphPanel,
    MatrixCell,
    MatrixPanel,
    TablePanel,
    TimelineItem,
    TimelineLane,
    TimelinePanel,
    VisualEdge,
    VisualField,
    VisualMetric,
    VisualNode,
)


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _fields(**values):
    return tuple(VisualField(name, value) for name, value in values.items())


def _metric(name, value, unit):
    return VisualMetric(name, value, unit)


def _relation_graph(value, source):
    starts, ends = dict(value.start_counts), dict(value.end_counts)
    counting = (
        source.spec.counting
        if source is not None and isinstance(source.spec, RelationDiscoverySpec)
        else "selected-count (counting request unavailable)"
    )
    identifiers = {
        name: f"activity:{index}"
        for index, (name, _) in enumerate(value.activity_counts)
    }
    return (
        GraphPanel(
            "case-relations",
            "Case " + value.relation.replace("_", " "),
            tuple(
                VisualNode(
                    identifiers[name],
                    name,
                    metrics=(
                        _metric("events", count, "events"),
                        _metric("starts", starts.get(name, 0), "cases"),
                        _metric("ends", ends.get(name, 0), "cases"),
                    ),
                )
                for name, count in value.activity_counts
            ),
            tuple(
                VisualEdge(
                    f"relation:{i}",
                    identifiers[e.source],
                    identifiers[e.target],
                    label=str(e.count),
                    kind=value.relation,
                    metrics=(
                        _metric("selected count", e.count, counting),
                        _metric("case count", e.case_count, "cases"),
                    ),
                )
                for i, e in enumerate(value.edges)
            ),
            description=f"Recorded trace order. Counting: {counting}. Edge counts are {'complete' if value.complete else 'lower bounds: event-pair budget exhausted'}. Activity and boundary counts cover the full input.",
        ),
        TablePanel(
            "case-relation-coverage",
            "Relation coverage",
            ("cases", "empty cases", "examined event pairs", "complete"),
            (
                (
                    value.trace_count,
                    value.empty_trace_count,
                    value.examined_event_pairs,
                    value.complete,
                ),
            ),
        ),
    )


def _interval_relations(value):
    activities = sorted(
        {name for edge in value.relations for name in (edge.source, edge.target)}
    )
    ids = {name: f"activity:{i}" for i, name in enumerate(activities)}
    return (
        GraphPanel(
            "interval-efg",
            "Interval eventually follows",
            tuple(VisualNode(ids[a], a) for a in activities),
            tuple(
                VisualEdge(
                    f"interval:{i}",
                    ids[e.source],
                    ids[e.target],
                    str(e.occurrence_count),
                    "interval_eventually_follows",
                    metrics=(
                        _metric("occurrences", e.occurrence_count, "event pairs"),
                        _metric("cases", e.case_count, "cases"),
                    ),
                    details=_fields(
                        witnesses=_json(
                            tuple(
                                (w.case_id, w.source_event_id, w.target_event_id)
                                for w in e.witnesses
                            )
                        )
                    ),
                )
                for i, e in enumerate(value.relations)
            ),
            description="Temporal admissibility from the calculation request; this is not recorded-order eventually follows. Nodes are relation endpoints only, not all selected activities.",
        ),
        TablePanel(
            "interval-efg-coverage",
            "Interval coverage",
            (
                "event population",
                "selected events",
                "excluded event IDs",
                "candidate pairs",
            ),
            (
                (
                    value.event_population,
                    value.selected_event_count,
                    _json(value.excluded_event_ids),
                    value.candidate_pairs,
                ),
            ),
        ),
    )


def _social(value):
    ids = {name: f"resource:{i}" for i, name in enumerate(value.resources)}
    return (
        GraphPanel(
            "social-network",
            "Resource social network",
            tuple(VisualNode(ids[name], name, "resource") for name in value.resources),
            tuple(
                VisualEdge(
                    f"social:{i}",
                    ids[e.source],
                    ids[e.target],
                    "unknown" if e.weight is None else str(e.weight),
                    "resource_relation",
                    value.directed,
                    (
                        _metric(
                            "weight", e.weight, value.metric + ":" + value.normalization
                        ),
                        _metric("raw weight", e.raw_weight, value.metric + ":raw"),
                        _metric("observations", e.observation_count, "observations"),
                        _metric("denominator", e.denominator, "metric denominator"),
                    ),
                )
                for i, e in enumerate(value.edges)
            ),
            layout="force",
            description=f"Metric: {value.metric}; normalization: {value.normalization}; directed: {value.directed}. Negative weights and unknown denominators are retained.",
        ),
        TablePanel(
            "social-coverage",
            "Social network coverage",
            (
                "cases",
                "events",
                "missing resource",
                "missing activity",
                "opportunity weight",
                "eligible pair weight",
            ),
            (
                (
                    value.case_count,
                    value.event_count,
                    value.missing_resource_count,
                    value.missing_activity_count,
                    value.opportunity_weight,
                    value.eligible_pair_weight,
                ),
            ),
        ),
    )


def _roles(value):
    resources = sorted({r for role in value.roles for r, _ in role.resource_counts})
    resource_ids = {r: f"resource:{i}" for i, r in enumerate(resources)}
    nodes = [VisualNode(resource_ids[r], r, "resource") for r in resources]
    edges = []
    for i, role in enumerate(value.roles):
        node_id = f"role:{i}"
        nodes.append(
            VisualNode(
                node_id,
                f"Role {i + 1}",
                "role",
                metrics=(_metric("events", role.event_count, "events"),),
                details=_fields(activities=_json(role.activities)),
            )
        )
        for j, (resource, count) in enumerate(role.resource_counts):
            edges.append(
                VisualEdge(
                    f"role-member:{i}:{j}",
                    resource_ids[resource],
                    node_id,
                    str(count),
                    "role_membership",
                    False,
                    (_metric("events", count, "events"),),
                )
            )
    return (
        GraphPanel(
            "roles",
            "Discovered organizational roles",
            tuple(nodes),
            tuple(edges),
            "bipartite",
            "Resource-to-role membership. Role activities are preserved in the inspector; roles do not imply permissions.",
        ),
        TablePanel(
            "role-coverage",
            "Role discovery coverage",
            (
                "events",
                "eligible events",
                "missing resource",
                "missing activity",
                "unsupported activities",
            ),
            (
                (
                    value.event_count,
                    value.eligible_event_count,
                    value.missing_resource_count,
                    value.missing_activity_count,
                    _json(value.unsupported_activities),
                ),
            ),
        ),
        TablePanel(
            "role-merges",
            "Role merge evidence",
            ("left activities", "right activities", "similarity"),
            tuple((_json(m.left), _json(m.right), m.similarity) for m in value.merges),
            "Calculated normalized multiset Jaccard similarities.",
        ),
    )


def _attribute_network(value):
    names = sorted({x for e in value.edges for x in (e.source, e.target)})
    ids = {name: f"attribute:{i}" for i, name in enumerate(names)}
    return (
        GraphPanel(
            "attribute-network",
            "Attribute network",
            tuple(VisualNode(ids[n], n, "attribute") for n in names),
            tuple(
                VisualEdge(
                    f"attribute-edge:{i}",
                    ids[e.source],
                    ids[e.target],
                    e.edge_value,
                    "attribute_relation",
                    metrics=(
                        _metric("links", e.count, "links"),
                        _metric("timed links", e.timed_count, "links"),
                        _metric("mean duration", e.mean_seconds, "seconds"),
                        _metric("total duration", e.total_seconds, "seconds"),
                        _metric("minimum duration", e.minimum_seconds, "seconds"),
                        _metric("maximum duration", e.maximum_seconds, "seconds"),
                    ),
                )
                for i, e in enumerate(value.edges)
            ),
            description="Each edge label retains a separate parallel relation. Duration aggregates cover timed links only; business-time policy is in the source request.",
        ),
        TablePanel(
            "attribute-network-coverage",
            "Attribute network coverage",
            (
                "events",
                "candidate links",
                "missing link attributes",
                "excluded node/edge links",
                "unknown durations",
                "timestamp ties",
            ),
            (
                (
                    value.event_count,
                    value.candidate_link_count,
                    value.missing_link_attribute_count,
                    value.excluded_node_or_edge_link_count,
                    value.unavailable_duration_count,
                    value.timestamp_tie_count,
                ),
            ),
        ),
    )


def _statistics(value):
    return (
        ChartPanel(
            "activity-frequency",
            "Activity frequency",
            "bar",
            (
                ChartSeries(
                    "events",
                    tuple(
                        ChartPoint(
                            a.activity,
                            a.event_count,
                            _fields(
                                case_count=len(a.case_ids),
                                repeated_events=a.repeated_event_count,
                            ),
                        )
                        for a in value.activities
                    ),
                ),
            ),
            x_label="Activity",
            y_label="Event count",
            y_unit="events",
        ),
        ChartPanel(
            "variant-frequency",
            "Variant frequency",
            "bar",
            (
                ChartSeries(
                    "cases",
                    tuple(
                        ChartPoint(
                            f"Variant {i + 1}",
                            v.count,
                            _fields(
                                activities=_json(v.activities),
                                case_ids=_json(v.case_ids),
                                probability=v.probability,
                                cumulative_coverage=v.cumulative_coverage,
                            ),
                        )
                        for i, v in enumerate(value.variants)
                    ),
                ),
            ),
            x_label="Variant",
            y_label="Case count",
            y_unit="cases",
            description="Empty variants remain present. Probabilities and cumulative coverage are supplied by the computation.",
        ),
        TablePanel(
            "case-statistics-coverage",
            "Case population",
            ("cases", "events", "empty case IDs"),
            ((value.case_count, value.event_count, _json(value.empty_case_ids)),),
        ),
    )


def _performance(value):
    names = sorted({a for p in value.variant_paths for a in (p.source, p.target)})
    ids = {a: f"activity:{i}" for i, a in enumerate(names)}
    return (
        ChartPanel(
            "case-duration",
            "Observed case durations",
            "bar",
            (
                ChartSeries(
                    "duration",
                    tuple(
                        ChartPoint(
                            c.case_id,
                            c.duration_seconds,
                            _fields(
                                status=c.status,
                                start=c.start.isoformat() if c.start else None,
                                end=c.end.isoformat() if c.end else None,
                            ),
                        )
                        for c in value.cases
                    ),
                ),
            ),
            x_label="Case",
            y_label="Observed duration",
            y_unit="seconds",
            description="Unknown durations stay null. Durations are observed case intervals, not inferred service time.",
        ),
        GraphPanel(
            "performance-dfg",
            "Path timing by variant and position",
            tuple(VisualNode(ids[a], a) for a in names),
            tuple(
                VisualEdge(
                    f"path:{i}",
                    ids[p.source],
                    ids[p.target],
                    "unknown" if p.summary.mean is None else f"{p.summary.mean} s",
                    "variant_path",
                    metrics=(
                        _metric("mean duration", p.summary.mean, "seconds"),
                        _metric("samples", p.summary.count, "observations"),
                        _metric("unknown samples", p.unknown_count, "observations"),
                    ),
                    details=_fields(
                        variant=_json(p.variant),
                        position=p.position,
                        samples=_json(p.samples),
                    ),
                )
                for i, p in enumerate(value.variant_paths)
            ),
            description="Parallel edges remain separate for each variant and path position. Means are supplied measurements; no hidden cross-variant aggregation.",
        ),
        TablePanel(
            "service-observations",
            "Observed service intervals",
            ("case", "event", "activity", "start", "end", "seconds", "status"),
            tuple(
                (
                    s.case_id,
                    s.event_id,
                    s.activity,
                    s.start.isoformat() if s.start else None,
                    s.end.isoformat() if s.end else None,
                    s.seconds,
                    s.status,
                )
                for s in value.services
            ),
        ),
        TablePanel(
            "performance-coverage",
            "Duration coverage",
            (
                "eligible cases",
                "duration observations",
                "unknown case durations",
                "busy union seconds",
                "cycle denominator",
                "busy union / complete service cases (seconds)",
            ),
            (
                (
                    value.eligible_case_count,
                    value.duration_summary.count,
                    sum(c.duration_seconds is None for c in value.cases),
                    value.busy_union_seconds,
                    value.cycle_denominator,
                    value.cycle_seconds,
                ),
            ),
        ),
    )


def _numeric(value, source):
    request = (
        source.spec
        if source is not None and isinstance(source.spec, NumericAttributeSpec)
        else None
    )
    key = request.key if request else "attribute (request unavailable)"
    return (
        ChartPanel(
            "numeric-observations",
            "Numeric attribute observations",
            "scatter",
            (
                ChartSeries(
                    "observed values",
                    tuple(
                        ChartPoint(
                            f"Observation {i + 1}",
                            x,
                            _fields(case_id=case_id, entity_id=entity_id),
                        )
                        for i, (case_id, entity_id, x) in enumerate(value.observations)
                    ),
                ),
            ),
            x_label="Observation",
            y_label=key,
            y_unit="attribute units (unspecified)",
        ),
        ChartPanel(
            "numeric-kde",
            "Gaussian kernel density",
            "line",
            (
                ChartSeries(
                    "density", tuple(ChartPoint(x, y) for x, y in value.gaussian_kde)
                ),
            ),
            x_type="number",
            x_label=key,
            y_label="Density",
            x_unit="attribute units (unspecified)",
            y_unit="inverse attribute units",
            description=f"Uses the computed grid and density without fitting or resampling. Bandwidth: {request.bandwidth if request else 'request unavailable'}. Null density is unknown.",
        ),
        TablePanel(
            "numeric-coverage",
            "Numeric observation coverage",
            ("population", "observed", "unknown entity IDs"),
            ((value.population, value.summary.count, _json(value.unknown_entity_ids)),),
        ),
    )


def _attributes(value):
    keys = sorted({f.key for f in value.frequencies})
    panels = []
    for i, key in enumerate(keys):
        panels.append(
            ChartPanel(
                f"attribute-count:{i}",
                f"Attribute frequency: {key}",
                "bar",
                (
                    ChartSeries(
                        "occurrences",
                        tuple(
                            ChartPoint(
                                f.value_json,
                                f.occurrence_count,
                                _fields(
                                    case_count=len(f.case_ids),
                                    entity_ids=_json(f.entity_ids),
                                ),
                            )
                            for f in value.frequencies
                            if f.key == key
                        ),
                    ),
                ),
                x_label="Typed attribute value (JSON)",
                y_label="Occurrences",
                y_unit="attribute occurrences",
                description=f"Scope: {value.scope}. Typed values retain their JSON type tags.",
            )
        )
    panels.append(
        TablePanel(
            "attribute-coverage",
            "Attribute coverage",
            ("key", "population", "observed", "missing"),
            tuple((c.key, c.population, c.observed, c.missing) for c in value.coverage),
        )
    )
    return tuple(panels)


def _event_distribution(value, source):
    request = (
        source.spec
        if source is not None and isinstance(source.spec, EventDistributionSpec)
        else None
    )
    description = (
        f"Calendar granularity: {request.granularity}; fixed UTC offset minutes: {request.utc_offset_minutes}. ISO weekdays are 1=Monday through 7=Sunday."
        if request
        else "Bin keys are preserved. Calendar granularity and UTC offset are unknown without the original request."
    )
    return (
        ChartPanel(
            "event-distribution",
            "Observed event distribution",
            "bar",
            (
                ChartSeries(
                    "events",
                    tuple(
                        ChartPoint(
                            b.key,
                            len(b.event_ids),
                            _fields(
                                case_count=len(b.case_ids), event_ids=_json(b.event_ids)
                            ),
                        )
                        for b in value.bins
                    ),
                ),
            ),
            x_label="Calendar bin",
            y_label="Observed events",
            y_unit="events",
            description=description + " Unlisted bins are not synthesized as zero.",
        ),
        TablePanel(
            "event-distribution-coverage",
            "Timestamp coverage",
            ("events", "observed timestamps", "unknown event IDs"),
            (
                (
                    value.event_count,
                    value.observed_count,
                    _json(value.unknown_event_ids),
                ),
            ),
        ),
    )


def _spectrum(value, source):
    request = (
        source.spec
        if source is not None and isinstance(source.spec, PerformanceSpectrumSpec)
        else None
    )
    activities = request.activities if request else ()
    return (
        ChartPanel(
            "performance-spectrum",
            "Performance spectrum",
            "line",
            tuple(
                ChartSeries(
                    f"Occurrence {i + 1}: {p.case_id}",
                    tuple(
                        ChartPoint(
                            time.astimezone(timezone.utc).isoformat(),
                            position,
                            _fields(
                                case_id=p.case_id,
                                event_id=p.event_ids[position],
                                activity=activities[position]
                                if position < len(activities)
                                else None,
                            ),
                        )
                        for position, time in enumerate(p.times)
                    ),
                )
                for i, p in enumerate(value.points)
            ),
            x_type="time",
            x_label="Observed timestamp (UTC)",
            y_label="Selected activity position",
            x_unit="UTC",
            y_unit="sequence position",
            description="One polyline per matched occurrence, preserving supplied order and repeated cases. Activity axis: "
            + (_json(activities) if request else "request unavailable; positions only")
            + ". No sampling.",
        ),
        TablePanel(
            "spectrum-coverage",
            "Spectrum coverage",
            ("cases", "matched occurrences", "unknown occurrences", "displayed paths"),
            (
                (
                    value.case_count,
                    value.matched_occurrences,
                    value.unknown_occurrences,
                    len(value.points),
                ),
            ),
        ),
    )


def _dotted(value):
    lanes, items, missing = [], [], []
    for i, case in enumerate(value.traces):
        lane = f"case:{i}"
        lanes.append(TimelineLane(lane, case.id))
        for j, event in enumerate(case.events):
            # A global timestamp is a default, not an event time observation.
            dates = tuple(a for a in event.attributes if a.key == "time:timestamp")
            names = tuple(a for a in event.attributes if a.key == "concept:name")
            activity = (
                names[0].value
                if len(names) == 1 and names[0].type == "string"
                else None
            )
            if (
                len(dates) != 1
                or dates[0].type != "date"
                or dates[0].value.utcoffset() is None
            ):
                missing.append(
                    (
                        case.id,
                        event.id,
                        j,
                        activity,
                        "missing, ambiguous, non-date, or timezone-naive recorded timestamp",
                    )
                )
                continue
            time = dates[0].value
            items.append(
                TimelineItem(
                    f"event:{i}:{j}",
                    lane,
                    time.timestamp(),
                    time.timestamp(),
                    activity if activity is not None else event.id,
                    status="observed",
                    details=_fields(
                        event_id=event.id,
                        case_id=case.id,
                        source_position=j,
                        activity=activity,
                        timestamp=time.isoformat(),
                    ),
                )
            )
    return (
        TimelinePanel(
            "dotted-chart",
            "Recorded event timestamps",
            tuple(lanes),
            tuple(items),
            "timestamp",
            "seconds",
            f"One dot per observed event, lanes in source case order; positions do not assert behavioral order. Coincident dots retain distinct IDs. Displayed {len(items)} events; {len(missing)} have unavailable recorded time. Empty case lanes remain present. Global timestamp defaults are not observations.",
        ),
        TablePanel(
            "dotted-unavailable",
            "Events without usable recorded time",
            ("case", "event", "source position", "activity", "reason"),
            tuple(missing),
        ),
    )


def _footprint_conformance(value, source):
    observed, allowed = set(value.observed_relations), set(value.allowed_relations)
    activities = set(a for pair in observed | allowed for a in pair)
    activities.update(
        a for v in value.violations for a in (v.source, v.target) if a is not None
    )
    # The reference alphabet also retains isolated activities, when supplied.
    from pix.case_centric.declarative import FootprintConformanceRequest

    if source is not None and isinstance(source.spec, FootprintConformanceRequest):
        activities.update(source.spec.model.activities)
    axes = tuple(sorted(activities))
    cells = []
    for a in axes:
        for b in axes:
            state = (
                "matched"
                if (a, b) in observed & allowed
                else "violation"
                if (a, b) in observed
                else "unobserved"
                if (a, b) in allowed
                else "absent"
            )
            cells.append(
                MatrixCell(
                    a,
                    b,
                    {
                        "matched": "=",
                        "violation": "!",
                        "unobserved": "○",
                        "absent": "#",
                    }[state],
                    state,
                    _fields(observed=(a, b) in observed, allowed=(a, b) in allowed),
                )
            )
    return (
        MatrixPanel(
            "footprint-conformance",
            "Footprint relation comparison",
            axes,
            axes,
            tuple(cells),
            _fields(
                matched="=: observed and allowed",
                violation="!: observed but not allowed",
                unobserved="○: allowed but not observed",
                absent="#: neither observed nor allowed",
            ),
            description="Ordered relation-set comparison. This is not a frequency-weighted score. Boundary, minimum-length and mandatory-activity violations are listed separately.",
        ),
        TablePanel(
            "footprint-violations",
            "All footprint violations",
            ("kind", "source", "target", "case"),
            tuple((v.kind, v.source, v.target, v.case_id) for v in value.violations),
        ),
        TablePanel(
            "footprint-scores",
            "Relation-set quality",
            (
                "cases",
                "matched relations",
                "relation fitness",
                "relation precision",
                "profile",
            ),
            (
                (
                    value.case_count,
                    value.matched_relation_count,
                    value.relation_fitness,
                    value.relation_precision,
                    value.profile,
                ),
            ),
            "Null scores retain undefined denominators.",
        ),
    )


def _decision_tree(value):
    nodes, edges = [], []
    for node in value.nodes:
        leaf = node.feature_index is None
        label = (
            node.prediction
            if leaf
            else f"{value.feature_names[node.feature_index]} ≤ {node.threshold}"
        )
        nodes.append(
            VisualNode(
                f"decision:{node.id}",
                label,
                "decision_leaf" if leaf else "decision_split",
                metrics=(
                    _metric("training samples", node.sample_count, "training cases"),
                ),
                details=_fields(
                    prediction=node.prediction,
                    class_counts=_json(node.class_counts),
                    stop_reason=node.stop_reason,
                ),
            )
        )
        if not leaf:
            for branch, child, operator in (
                ("left", node.left, "≤"),
                ("right", node.right, ">"),
            ):
                edges.append(
                    VisualEdge(
                        f"branch:{node.id}:{branch}",
                        f"decision:{node.id}",
                        f"decision:{child}",
                        f"{operator} {node.threshold}",
                        "decision_branch",
                    )
                )
    return (
        GraphPanel(
            "decision-tree",
            "Decision tree",
            tuple(nodes),
            tuple(edges),
            "tree",
            f"Training status: {value.status}. Branches are explicit numeric comparisons; leaf predictions and class counts are training evidence, not validated predictive accuracy.",
        ),
        TablePanel(
            "decision-training",
            "Decision training evidence",
            (
                "training cases",
                "correct training cases",
                "split evaluations",
                "status",
                "training digest",
            ),
            (
                (
                    value.training_count,
                    value.training_correct,
                    value.split_evaluations,
                    value.status,
                    value.training_digest,
                ),
            ),
        ),
    )


def _rational(value):
    return None if value is None else f"{value[0]}/{value[1]}"


def _alignment_views(value):
    # Explicit normalization per concrete contract; no introspection fallback.
    records = []
    references = {}
    if isinstance(value, AlignmentSet):
        for trace in value.alignments:
            records.append(
                (
                    trace.object_id,
                    trace.status,
                    trace.cost,
                    trace.lower_bound_cost,
                    tuple(
                        (
                            m.kind,
                            m.activity if m.kind in ("synchronous", "log") else None,
                            m.activity if m.kind in ("synchronous", "model") else None,
                            m.event_id,
                            m.transition_id,
                            m.cost,
                        )
                        for m in trace.moves
                    ),
                )
            )
    elif isinstance(value, (TreeAlignmentSet, ApproximateAlignmentSet)):
        for trace in value.traces:
            approximate = isinstance(value, ApproximateAlignmentSet)
            cost = trace.cost_upper_bound if approximate else trace.cost
            lower = trace.certified_lower_bound if approximate else None
            records.append(
                (
                    trace.case_id,
                    trace.status,
                    cost,
                    lower,
                    tuple(
                        (
                            m.kind,
                            m.activity if m.kind in ("synchronous", "log") else None,
                            m.activity if m.kind in ("synchronous", "model") else None,
                            m.event_id,
                            m.transition_id if approximate else _json(m.node_path),
                            m.cost,
                        )
                        for m in trace.moves
                    ),
                )
            )
    elif isinstance(value, SearchAlignmentSet):
        for trace in value.traces:
            records.append(
                (
                    trace.case_id,
                    trace.status,
                    _rational(trace.cost),
                    _rational(trace.lower_bound_cost),
                    tuple(
                        (
                            m.kind,
                            m.activity if m.kind in ("synchronous", "log") else None,
                            m.activity if m.kind in ("synchronous", "model") else None,
                            m.event_id,
                            m.transition_id,
                            _rational(cost),
                        )
                        for m, cost in zip(trace.moves, trace.step_costs, strict=True)
                    ),
                )
            )
    elif isinstance(value, DFGAlignmentSet):
        for trace in value.traces:
            records.append(
                (
                    trace.case_id,
                    trace.status,
                    trace.cost,
                    trace.lower_bound_cost,
                    tuple(
                        (
                            m.kind,
                            m.log_activity,
                            m.model_activity,
                            m.log_event_id,
                            m.reference_event_id,
                            m.cost,
                        )
                        for m in trace.moves
                    ),
                )
            )
    elif isinstance(value, SequenceAlignmentSet):
        for trace in value.traces:
            if not trace.nearest_references:
                records.append(
                    (trace.case_id, trace.status, trace.best_known_cost, None, ())
                )
            for ref in trace.nearest_references:
                references[len(records)] = ref.reference_case_id
                records.append(
                    (
                        trace.case_id,
                        trace.status,
                        ref.cost,
                        None,
                        tuple(
                            (
                                m.kind,
                                m.log_activity,
                                m.model_activity,
                                m.log_event_id,
                                m.reference_event_id,
                                m.cost,
                            )
                            for m in ref.moves
                        ),
                    )
                )
    else:
        return None
    lanes, items, summary, moves = [], [], [], []
    for index, (case_id, status, cost, lower, steps) in enumerate(records):
        summary.append((case_id, status, cost, lower, len(steps)))
        for side in ("log", "model"):
            lanes.append(
                TimelineLane(
                    f"alignment:{index}:{side}",
                    case_id + " / " + side,
                    f"alignment:{index}",
                )
            )
        for position, (
            kind,
            log_activity,
            model_activity,
            event_id,
            model_id,
            step_cost,
        ) in enumerate(steps):
            moves.append(
                (
                    case_id,
                    position,
                    kind,
                    log_activity,
                    model_activity,
                    event_id,
                    model_id,
                    step_cost,
                    index,
                    references.get(index),
                )
            )
            for side, activity in (("log", log_activity), ("model", model_activity)):
                label = (
                    activity
                    if activity is not None
                    else "τ (silent)"
                    if side == "model" and kind == "silent"
                    else "∅ (gap)"
                )
                items.append(
                    TimelineItem(
                        f"alignment:{index}:{position}:{side}",
                        f"alignment:{index}:{side}",
                        position,
                        position + 1,
                        label,
                        kind,
                        kind,
                        _fields(
                            move_kind=kind,
                            activity=activity,
                            event_id=event_id,
                            model_id=model_id,
                            cost=step_cost,
                            alignment_row=index,
                            case_id=case_id,
                            reference_case_id=references.get(index),
                        ),
                    )
                )
    panels = (
        TimelinePanel(
            "alignments",
            "Log / model move comparison",
            tuple(lanes),
            tuple(items),
            "relative",
            "move index",
            "Paired lanes preserve each case and each move, including empty paths. Gap and silent markers are display notation; actual activity stays in details. Status and costs are listed below. Search-limited witnesses are not declared optimal.",
        ),
        TablePanel(
            "alignment-status",
            "Alignment status and cost",
            (
                "case ID",
                "status",
                "cost or upper bound",
                "lower bound",
                "moves",
            ),
            tuple(summary),
            "Cost units are the input cost profile. Approximate witnesses show upper bounds; rational search costs remain exact numerator/denominator strings. Empty paths are not dropped.",
        ),
        TablePanel(
            "alignment-moves",
            "Alignment move evidence",
            (
                "case ID",
                "position",
                "kind",
                "log activity",
                "model activity",
                "event ID",
                "model/reference ID",
                "move cost",
                "alignment row",
                "reference case ID",
            ),
            tuple(moves),
        ),
    )
    if isinstance(value, SequenceAlignmentSet):
        panels += (
            TablePanel(
                "alignment-references",
                "Compared case identities",
                ("alignment row", "case ID", "reference case ID"),
                tuple(
                    (i, record[0], references.get(i))
                    for i, record in enumerate(records)
                ),
                "Case and reference IDs remain separate even when labels contain separators. Each tied nearest reference retains its own comparison row.",
            ),
        )
    return panels


def _replay(value):
    lanes, items, summary, details = [], [], [], []
    for i, trace in enumerate(value.traces):
        for side in ("log", "model"):
            lanes.append(
                TimelineLane(
                    f"replay:{i}:{side}", trace.object_id + " / " + side, f"replay:{i}"
                )
            )
        summary.append(
            (
                trace.object_id,
                trace.status,
                trace.event_count,
                trace.processed_event_count,
                trace.log_deviation_count,
                trace.counts.missing,
                trace.counts.remaining,
                trace.final_reached,
                trace.limit_reason,
            )
        )
        for j, step in enumerate(trace.steps):
            details.append(
                (
                    trace.object_id,
                    j,
                    step.kind,
                    step.event_id,
                    step.transition_id,
                    _json(step.inserted_tokens),
                    _json(step.consumed_tokens),
                    _json(step.produced_tokens),
                    _json(step.marking_before),
                    _json(step.marking_after),
                )
            )
            for side in ("log", "model"):
                activity = (
                    step.activity
                    if (side == "log" and step.event_id is not None)
                    or (side == "model" and step.kind == "visible")
                    else None
                )
                label = (
                    activity
                    if activity is not None
                    else "τ (silent)"
                    if side == "model" and step.kind == "silent"
                    else step.kind
                    if step.kind in ("initial", "finalize")
                    else "∅ (gap)"
                )
                items.append(
                    TimelineItem(
                        f"replay:{i}:{j}:{side}",
                        f"replay:{i}:{side}",
                        j,
                        j + 1,
                        label,
                        step.kind,
                        step.kind,
                        _fields(
                            kind=step.kind,
                            activity=activity,
                            event_id=step.event_id,
                            transition_id=step.transition_id,
                            inserted_tokens=_json(step.inserted_tokens),
                        ),
                    )
                )
    return (
        TimelinePanel(
            "token-replay",
            "Token replay steps",
            tuple(lanes),
            tuple(items),
            "relative",
            "replay step",
            "Heuristic token replay, not optimal alignment. Initial/final token accounting and silent steps remain visible. Completed procedure does not imply a fitting trace; token insertion is explicit.",
        ),
        TablePanel(
            "replay-status",
            "Replay status",
            (
                "case",
                "status",
                "events",
                "processed events",
                "log deviations",
                "missing tokens",
                "remaining tokens",
                "final reached",
                "limit reason",
            ),
            tuple(summary),
        ),
        TablePanel(
            "replay-evidence",
            "Replay token evidence",
            (
                "case",
                "step",
                "kind",
                "event ID",
                "transition ID",
                "inserted tokens",
                "consumed tokens",
                "produced tokens",
                "marking before",
                "marking after",
            ),
            tuple(details),
        ),
        TablePanel(
            "replay-coverage",
            "Replay population",
            ("requested", "completed", "limited", "excluded", "unprocessed events"),
            (
                (
                    value.trace_count,
                    value.completed_count,
                    value.limited_count,
                    value.excluded_count,
                    value.unprocessed_event_count,
                ),
            ),
        ),
    )


def case_panels(value, *, source=None):
    """Return typed panels for supported case results, or ``None``.

    ``source`` may be the original result to retain request-only choices. A
    mismatched envelope is rejected instead of attaching another cost/calendar
    policy. Missing envelopes are explicitly described where they matter.
    """
    if source is not None:
        if not isinstance(source, ComputationResult):
            raise TypeError("source must be the original ComputationResult")
        if source.value != value:
            raise ValueError("source value does not match visualization input")
    if isinstance(value, CaseRelationGraph):
        return _relation_graph(value, source)
    if isinstance(value, IntervalEventuallyFollows):
        return _interval_relations(value)
    if isinstance(value, NetworkPayload):
        return _social(value)
    if isinstance(value, RoleSet):
        return _roles(value)
    if isinstance(value, AttributeNetwork):
        return _attribute_network(value)
    if isinstance(value, CaseStatistics):
        return _statistics(value)
    if isinstance(value, CasePerformance):
        return _performance(value)
    if isinstance(value, NumericAttributeStatistics):
        return _numeric(value, source)
    if isinstance(value, AttributeStatistics):
        return _attributes(value)
    if isinstance(value, EventDistribution):
        return _event_distribution(value, source)
    if isinstance(value, PerformanceSpectrum):
        return _spectrum(value, source)
    if isinstance(value, CaseLog):
        return _dotted(value)
    if isinstance(value, FootprintConformance):
        return _footprint_conformance(value, source)
    if isinstance(value, DecisionTree):
        return _decision_tree(value)
    if isinstance(value, ReplaySet):
        return _replay(value)
    return _alignment_views(value)


def variant_duration_panels(
    statistics,
    performance,
    *,
    statistics_source=None,
    performance_source=None,
):
    """Join verified variant membership with observed case/path durations.

    Matching source digests alone do not establish matching classifiers. Both
    calculation envelopes and equal trace selections are mandatory here. The
    view uses ordinal activity positions; geometry does not encode elapsed time.
    """
    if not isinstance(statistics, CaseStatistics) or not isinstance(
        performance, CasePerformance
    ):
        raise TypeError("variant durations require CaseStatistics and CasePerformance")
    for envelope, value, spec_type in (
        (statistics_source, statistics, StatisticsSpec),
        (performance_source, performance, CasePerformanceSpec),
    ):
        if (
            not isinstance(envelope, ComputationResult)
            or envelope.value != value
            or not isinstance(envelope.spec, spec_type)
        ):
            raise ValueError("matching original computation envelopes are required")
    if (
        not statistics_source.source_digest
        or statistics_source.source_digest != performance_source.source_digest
    ):
        raise ValueError("variant and duration source digests must agree")
    if statistics_source.spec.trace_spec != performance_source.spec.trace_spec:
        raise ValueError("variant and duration trace selections/classifiers must agree")
    memberships = tuple(
        case for variant in statistics.variants for case in variant.case_ids
    )
    cases = {case.case_id: case for case in performance.cases}
    if (
        len(memberships) != statistics.case_count
        or len(set(memberships)) != len(memberships)
        or len(cases) != len(performance.cases)
        or set(memberships) != set(cases)
        or any(v.count != len(v.case_ids) for v in statistics.variants)
    ):
        raise ValueError("variant and duration case populations must agree exactly")
    paths = {(p.variant, p.position): p for p in performance.variant_paths}
    expected = {
        (v.activities, position)
        for v in statistics.variants
        for position in range(len(v.activities) - 1)
    }
    if len(paths) != len(performance.variant_paths) or set(paths) != expected:
        raise ValueError("variant and timing path positions must agree")
    panels, rows = [], []
    for index, variant in enumerate(statistics.variants):
        nodes = tuple(
            VisualNode(
                f"variant:{index}:position:{position}",
                activity,
                metrics=(_metric("variant frequency", variant.count, "cases"),),
                details=_fields(position=position),
            )
            for position, activity in enumerate(variant.activities)
        )
        if not nodes:
            nodes = (
                VisualNode(
                    f"variant:{index}:empty",
                    "ε (empty variant)",
                    "empty_variant",
                    metrics=(_metric("variant frequency", variant.count, "cases"),),
                ),
            )
        edges = []
        for position, (a, b) in enumerate(
            zip(variant.activities, variant.activities[1:])
        ):
            timing = paths[(variant.activities, position)]
            if (timing.source, timing.target) != (a, b) or any(
                s[0] not in variant.case_ids for s in timing.samples
            ):
                raise ValueError(
                    "path timing evidence conflicts with variant membership"
                )
            if (
                timing.summary.count != len(timing.samples)
                or len({sample[0] for sample in timing.samples}) != len(timing.samples)
                or timing.summary.count + timing.unknown_count != variant.count
            ):
                raise ValueError(
                    "path timing coverage conflicts with variant frequency"
                )
            edges.append(
                VisualEdge(
                    f"variant:{index}:path:{position}",
                    nodes[position].id,
                    nodes[position + 1].id,
                    "unknown"
                    if timing.summary.mean is None
                    else f"{timing.summary.mean} s",
                    "variant_path",
                    metrics=(
                        _metric("mean completion gap", timing.summary.mean, "seconds"),
                        _metric("known gaps", timing.summary.count, "observations"),
                        _metric("unknown gaps", timing.unknown_count, "observations"),
                    ),
                    details=_fields(samples=_json(timing.samples)),
                )
            )
        panels.append(
            GraphPanel(
                f"variant-duration:{index}",
                f"Variant {index + 1} — {variant.count} cases",
                nodes,
                tuple(edges),
                description="Activity positions remain distinct, including repeated labels. Edge labels are computed mean completion gaps in seconds. Equal visual spacing is ordinal, not elapsed time. No sampling or top-N exclusion.",
            )
        )
        for case_id in variant.case_ids:
            case = cases[case_id]
            rows.append(
                (
                    index + 1,
                    _json(variant.activities),
                    case_id,
                    case.duration_seconds,
                    case.status,
                )
            )
    panels.append(
        TablePanel(
            "variant-case-durations",
            "Variant membership and observed case duration",
            ("variant", "activities", "case", "duration seconds", "status"),
            tuple(rows),
            "All cases are shown once. Null duration is unknown; empty cases remain explicit. These are case intervals, not sums of averaged path durations.",
        )
    )
    return tuple(panels)


__all__ = ("case_panels", "variant_duration_panels")
