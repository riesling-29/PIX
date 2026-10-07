"""Object-centric views preserving incidence, populations and observed evidence.

These adapters never discover order, replay a model, repair an OCEL, or replace an
unknown observation with zero. Layout layers and replay steps are display axes;
only timestamp panels claim measured clock time. Repeated lane appearances share
an explicit semantic event identity and do not multiply event or alignment cost.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256

from pix.case_centric.interleavings import InterleavingSet
from pix.case_centric.interleavings_ocel import (
    InterleavingsOCELConversion,
    InterleavingsOCELReport,
)
from pix.contracts.analysis import ObjectCentricDFG
from pix.contracts.execution import (
    ExecutionSet,
    ExecutionVariant,
    ProcessExecution,
    VariantSet,
)
from pix.contracts.object_conformance import ObjectAlignment, ObjectLogScope
from pix.contracts.result import ComputationResult
from pix.object_centric.conformance import FlattenedReplay, ObjectReplay
from pix.object_centric.constraints import (
    AAEdge,
    ActivityNode,
    AOAEdge,
    ConstraintGraphEvaluation,
    ConstraintGraphSpec,
    FormulaNode,
    ObjectRuleMetric,
    ObjectTypeNode,
    PerformanceEdge,
    QualifierConformance,
)
from pix.object_centric.cube import CubePlan
from pix.object_centric.performance import OCPerformance, OCReplayPerformance
from pix.object_centric.relations import (
    ETOTGraph,
    ObjectGraph,
    ObjectRelations,
    OTGGraph,
)
from pix.object_centric.statistics import ObjectStatistics
from pix.object_centric.temporal_summary import TemporalSummary
from pix.ocel import OCEL, validate
from pix.viewer.visual_contracts import (
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


def _id(kind, *parts):
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"oc-{kind}-" + sha256(encoded.encode("utf-8")).hexdigest()


def _json(value):
    """Lossless scalar text for a specifically labelled evidence collection."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _iso(value):
    return None if value is None else value.isoformat()


def _seconds(value):
    delta = value.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (
        delta.days * 86400_000000 + delta.seconds * 1_000000 + delta.microseconds
    ) / 1_000000


def _fields(**values):
    return tuple(VisualField(key, val) for key, val in values.items())


def _node(kind, identity, label=None, group=None, **details):
    return VisualNode(
        _id(kind, identity),
        identity if label is None else label,
        kind,
        group,
        details=_fields(**{f"{kind}_id": identity, **details}),
    )


def _table(identity, title, columns, rows, description=""):
    return TablePanel(identity, title, tuple(columns), tuple(rows), description)


def _scope_graph(scope: ObjectLogScope, identity="oc-scope"):
    nodes = tuple(_node("event", e.event_id, e.activity) for e in scope.events)
    nodes += tuple(
        _node("object", oid, group=otype, object_type=otype)
        for oid, otype in scope.selected_objects
    )
    edges = []
    for event in scope.events:
        for eid, oid, qualifier in event.relations:
            edges.append(
                VisualEdge(
                    _id("scope-e2o", eid, oid, qualifier),
                    _id("event", eid),
                    _id("object", oid),
                    qualifier,
                    "e2o",
                    details=_fields(qualifier=qualifier),
                )
            )
    edges.extend(
        VisualEdge(
            _id(
                "precedence", p.predecessor_event_id, p.successor_event_id, p.object_id
            ),
            _id("event", p.predecessor_event_id),
            _id("event", p.successor_event_id),
            p.object_id,
            "object_precedence",
            details=_fields(object_id=p.object_id),
        )
        for p in scope.precedence
    )
    return GraphPanel(
        identity,
        "Joint event/object scope",
        nodes,
        tuple(edges),
        description=f"One node per source event; E2O roles remain separate. "
        f"Only supplied object precedence is drawn. Excluded objects: "
        f"{scope.excluded_object_count}; excluded relations: {scope.excluded_relation_count}.",
    )


def _observed_lanes(events, objects, relations, identity, title):
    """Display observed instants; no event completion is treated as its start."""
    event_map = {event.id: event for event in events}
    object_types = {obj.id: obj.type for obj in objects}
    roles = defaultdict(list)
    for relation in relations:
        roles[(relation.event, relation.object)].append(relation.qualifier)
    lanes = tuple(
        TimelineLane(_id("lane", obj.id), obj.id, obj.type)
        for obj in sorted(objects, key=lambda obj: obj.id)
    )
    items = []
    for (eid, oid), qualifiers in sorted(roles.items()):
        event = event_map[eid]
        activity = event.type if hasattr(event, "type") else event.activity
        items.append(
            TimelineItem(
                _id("appearance", identity, eid, oid),
                _id("lane", oid),
                _seconds(event.time),
                _seconds(event.time),
                activity,
                group=object_types[oid],
                details=_fields(
                    event_id=eid,
                    semantic_event_id=_id("event", eid),
                    object_id=oid,
                    qualifiers=_json(sorted(qualifiers)),
                    observed_time=_iso(event.time),
                ),
            )
        )
    related = {eid for eid, _ in roles}
    orphans = tuple(
        event
        for event in sorted(events, key=lambda event: event.id)
        if event.id not in related
    )
    if orphans:
        orphan_lane = _id("lane-unassigned", identity)
        lanes += (TimelineLane(orphan_lane, "Events without selected objects"),)
        items.extend(
            TimelineItem(
                _id("appearance-unassigned", identity, event.id),
                orphan_lane,
                _seconds(event.time),
                _seconds(event.time),
                event.type if hasattr(event, "type") else event.activity,
                details=_fields(
                    event_id=event.id,
                    semantic_event_id=_id("event", event.id),
                    observed_time=_iso(event.time),
                ),
            )
            for event in orphans
        )
    return TimelinePanel(
        identity,
        title,
        lanes,
        tuple(items),
        "timestamp",
        "seconds",
        "Each item is an observed instant, not a duration. A shared event appears "
        "on each participating lane with the same semantic_event_id. Qualifiers "
        "do not create extra appearances. Ties remain simultaneous; exact ISO "
        "timestamps in details are authoritative over display coordinates.",
    )


def _ocel(value):
    report = validate(value)
    if not report.valid:
        raise ValueError("cannot visualize invalid OCEL incidence")
    nodes = tuple(
        _node("event", event.id, event.type, observed_time=_iso(event.time))
        for event in sorted(value.events, key=lambda e: e.id)
    )
    nodes += tuple(
        _node("object", obj.id, group=obj.type, object_type=obj.type)
        for obj in sorted(value.objects, key=lambda o: o.id)
    )
    edges = tuple(
        VisualEdge(
            _id("e2o", row.event, row.object, row.qualifier),
            _id("event", row.event),
            _id("object", row.object),
            row.qualifier,
            "e2o",
            details=_fields(qualifier=row.qualifier),
        )
        for row in sorted(value.e2o, key=lambda r: (r.event, r.object, r.qualifier))
    )
    edges += tuple(
        VisualEdge(
            _id("o2o", row.source, row.target, row.qualifier),
            _id("object", row.source),
            _id("object", row.target),
            row.qualifier,
            "o2o",
            details=_fields(qualifier=row.qualifier),
        )
        for row in sorted(value.o2o, key=lambda r: (r.source, r.target, r.qualifier))
    )
    schemas = {
        (kind, declaration.name): {
            attr.name: attr.type.value for attr in declaration.attributes
        }
        for kind, declarations in (
            ("event", value.event_types),
            ("object", value.object_types),
        )
        for declaration in declarations
    }
    attrs = []
    for entity, rows in (("event", value.events), ("object", value.objects)):
        for row in rows:
            for attr in row.attributes:
                attrs.append(
                    (
                        entity,
                        row.id,
                        attr.name,
                        _iso(attr.value)
                        if isinstance(attr.value, datetime)
                        else attr.value,
                        _iso(attr.time) if entity == "object" else None,
                        schemas[entity, row.type][attr.name],
                    )
                )
    return (
        GraphPanel(
            "ocel-incidence",
            "OCEL qualified incidence",
            nodes,
            edges,
            layout="bipartite",
            description="Event and object IDs occupy separate namespaces. "
            "Parallel E2O/O2O qualifiers and directed O2O are retained. No event order is inferred.",
        ),
        _observed_lanes(
            value.events,
            value.objects,
            value.e2o,
            "ocel-time",
            "Observed event instants",
        ),
        _table(
            "ocel-attributes",
            "Event attributes and object attribute history",
            (
                "entity_kind",
                "entity_id",
                "attribute",
                "value",
                "assigned_at",
                "declared_type",
            ),
            sorted(attrs, key=lambda row: (row[0], row[1], row[2], row[4] or "")),
            "Object assignment time is not an event. No as-of value or attribute carry-forward is inferred.",
        ),
        _table(
            "ocel-schema",
            "Declared OCEL entity and attribute types",
            ("entity_kind", "entity_type", "attribute", "declared_type"),
            (
                (kind, name, attr, typ)
                for (kind, name), attributes in sorted(schemas.items())
                for attr, typ in (
                    sorted(attributes.items()) if attributes else ((None, None),)
                )
            ),
            "Declarations without observations remain visible here; they are not fabricated event/object instances.",
        ),
    )


def _object_graph(value):
    nodes = tuple(
        _node("object", n.object_id, group=n.object_type, object_type=n.object_type)
        for n in value.nodes
    )
    edges = tuple(
        VisualEdge(
            _id("object-relation", value.spec.kind, e.source, e.target),
            _id("object", e.source),
            _id("object", e.target),
            value.spec.kind,
            value.spec.kind,
            value.directed,
            (VisualMetric("witness_events", len(e.event_ids), "distinct_events"),),
            _fields(event_ids=_json(e.event_ids)),
        )
        for e in value.edges
    )
    return (
        GraphPanel(
            "oc-object-graph",
            f"Object {value.spec.kind} graph",
            nodes,
            edges,
            description=f"Observed relation; not real-world causality. Qualifiers: "
            f"{_json(value.spec.qualifiers)}; tie policy: {value.spec.tie_policy}.",
        ),
    )


def _object_relations(value):
    ids = sorted({i for row in value.relations for i in (row.source, row.target)})
    return (
        GraphPanel(
            "oc-object-relations",
            "Explicit qualified object relations",
            tuple(_node("object", i) for i in ids),
            tuple(
                VisualEdge(
                    _id("o2o", r.source, r.target, r.qualifier),
                    _id("object", r.source),
                    _id("object", r.target),
                    r.qualifier,
                    "o2o",
                    details=_fields(qualifier=r.qualifier),
                )
                for r in value.relations
            ),
            description="Stored O2O direction and qualifiers; object types are unavailable in this payload.",
        ),
    )


def _etot(value):
    nodes = tuple(_node("activity", a) for a in value.activities)
    nodes += tuple(_node("object_type", t, group=t) for t in value.object_types)
    edges = tuple(
        VisualEdge(
            _id("etot", e.activity, e.object_type),
            _id("activity", e.activity),
            _id("object_type", e.object_type),
            kind="activity_object_type",
            metrics=(VisualMetric("frequency", e.frequency, value.spec.frequency),),
        )
        for e in value.edges
    )
    return (
        GraphPanel(
            "oc-etot",
            "Activity / object-type participation",
            nodes,
            edges,
            "bipartite",
            f"Frequency unit: {value.spec.frequency}; selected qualifiers: "
            f"{_json(value.spec.qualifiers)}. Declared but unobserved nodes: "
            f"{value.spec.include_declared_types}.",
        ),
    )


def _otg(value):
    edges = tuple(
        VisualEdge(
            _id("otg", e.source_type, e.relation, e.target_type),
            _id("object_type", e.source_type),
            _id("object_type", e.target_type),
            e.relation,
            e.relation,
            e.relation in ("descendants", "inheritance"),
            (
                VisualMetric(
                    "object_pairs", e.object_pair_count, "distinct_object_pairs"
                ),
            ),
        )
        for e in value.edges
    )
    return (
        GraphPanel(
            "oc-otg",
            "Object-type relation graph",
            tuple(_node("object_type", t, group=t) for t in value.object_types),
            edges,
            description=f"Object pair counts remain separate by relation kind. Undirected "
            f"orientation policy: {value.spec.undirected_orientation}; ties: {value.spec.tie_policy}.",
        ),
    )


def _ocdfg(value):
    events, objects = defaultdict(set), defaultdict(set)
    occurrences = Counter()
    edges, rows, boundaries = [], [], []
    for graph in value.graphs:
        for a in graph.activities:
            events[a.activity].update(a.distinct_event_ids)
            objects[a.activity].update(a.object_ids)
            occurrences[a.activity] += a.event_occurrence_count
        for e in graph.edges:
            pairs = {(w.source_event_id, w.target_event_id) for w in e.evidence}
            obj_ids = {w.object_id for w in e.evidence}
            if (len(pairs), len(obj_ids), len(e.evidence)) != (
                e.event_pair_count,
                e.unique_object_count,
                e.occurrence_count,
            ):
                raise ValueError("OCDFG counts disagree with retained witnesses")
            edge_id = _id(
                "ocdfg", graph.object_type, e.source_activity, e.target_activity
            )
            edges.append(
                VisualEdge(
                    edge_id,
                    _id("activity", e.source_activity),
                    _id("activity", e.target_activity),
                    graph.object_type,
                    "object_directly_follows",
                    metrics=(
                        VisualMetric(
                            "event_pairs", e.event_pair_count, "distinct_event_pairs"
                        ),
                        VisualMetric(
                            "objects", e.unique_object_count, "distinct_objects"
                        ),
                        VisualMetric(
                            "occurrences",
                            e.occurrence_count,
                            "object_trace_occurrences",
                        ),
                    ),
                    details=_fields(object_type=graph.object_type),
                )
            )
            rows.extend(
                (
                    edge_id,
                    graph.object_type,
                    w.source_event_id,
                    w.target_event_id,
                    w.object_id,
                    _json(tuple(r.qualifier for r in w.source_relations)),
                    _json(tuple(r.qualifier for r in w.target_relations)),
                )
                for w in e.evidence
            )
        for direction, counts in (("start", graph.starts), ("end", graph.ends)):
            boundaries.extend(
                (graph.object_type, direction, b.activity, w.object_id, w.event_id)
                for b in counts
                for w in b.evidence
            )
        boundaries.extend(
            (graph.object_type, "empty_object", None, oid, None)
            for oid in graph.empty_object_ids
        )
    nodes = tuple(
        VisualNode(
            _id("activity", a),
            a,
            metrics=(
                VisualMetric("events", len(events[a]), "distinct_events"),
                VisualMetric("objects", len(objects[a]), "distinct_objects"),
                VisualMetric("occurrences", occurrences[a], "object_trace_occurrences"),
            ),
            details=_fields(
                event_ids=_json(sorted(events[a])), object_ids=_json(sorted(objects[a]))
            ),
        )
        for a in sorted(events)
    )
    return (
        GraphPanel(
            "oc-dfg",
            "Object-centric directly-follows graph",
            nodes,
            tuple(edges),
            description="Activity nodes share source events across types. Parallel edges retain "
            "object type. Distinct event pairs, distinct objects and trace occurrences are separate "
            "units. Directly-follows does not establish causality.",
        ),
        _table(
            "oc-dfg-witnesses",
            "Directly-follows witnesses",
            (
                "edge_id",
                "object_type",
                "source_event",
                "target_event",
                "object_id",
                "source_qualifiers",
                "target_qualifiers",
            ),
            rows,
        ),
        _table(
            "oc-dfg-boundaries",
            "Start/end and empty-object evidence",
            ("object_type", "boundary", "activity", "object_id", "event_id"),
            boundaries,
        ),
    )


def _execution(value):
    prefix = _id("execution", value.execution_id)
    nodes = tuple(
        _node("event", e.id, e.activity, observed_time=_iso(e.time))
        for e in value.events
    )
    nodes += tuple(
        _node(
            "object",
            o.id,
            group=o.type,
            object_type=o.type,
            scope="selected",
            leading=o.id == value.leading_object_id,
        )
        for o in value.objects
    )
    nodes += tuple(
        _node("object", o.id, group=o.type, object_type=o.type, scope="boundary")
        for o in value.boundary_objects
    )
    edges = tuple(
        VisualEdge(
            _id("execution-e2o", r.event, r.object, r.qualifier),
            _id("event", r.event),
            _id("object", r.object),
            r.qualifier,
            "e2o",
            details=_fields(qualifier=r.qualifier),
        )
        for r in value.relations
    )
    edges += tuple(
        VisualEdge(
            _id("execution-order", r.source_event, r.target_event, r.object_id),
            _id("event", r.source_event),
            _id("event", r.target_event),
            r.object_id,
            "object_precedence",
            details=_fields(object_id=r.object_id, tie_broken=r.tie_broken),
        )
        for r in value.order_edges
    )
    graph = GraphPanel(
        prefix + "-incidence",
        "Execution " + value.execution_id,
        nodes,
        edges,
        description=f"Order status: {value.order_status}. Event tuple order is ID storage "
        "order, not process order. Boundary objects are identified in node details.",
    )
    # A rank exists only for a complete acyclic supplied order relation. Never
    # linearly sort incomparable events, and never guess an unresolved order.
    panels = [
        graph,
        _observed_lanes(
            value.events,
            value.objects + value.boundary_objects,
            value.relations,
            prefix + "-time",
            "Execution observed instants",
        ),
    ]
    if value.order_status == "complete":
        ranks = {e.id: 0 for e in value.events}
        incoming = {e.id: set() for e in value.events}
        outgoing = defaultdict(set)
        for edge in value.order_edges:
            incoming[edge.target_event].add(edge.source_event)
            outgoing[edge.source_event].add(edge.target_event)
        ready = sorted(e for e, parents in incoming.items() if not parents)
        visited = 0
        while ready:
            eid = ready.pop()
            visited += 1
            for child in sorted(outgoing[eid]):
                ranks[child] = max(ranks[child], ranks[eid] + 1)
                incoming[child].remove(eid)
                if not incoming[child]:
                    ready.append(child)
        if visited != len(value.events):
            raise ValueError("execution order graph must be acyclic for lanes")
        observed = panels[1]
        items = tuple(
            TimelineItem(
                item.id + "-rank",
                item.lane,
                ranks[dict((d.name, d.value) for d in item.details)["event_id"]],
                ranks[dict((d.name, d.value) for d in item.details)["event_id"]],
                item.label,
                item.group,
                item.status,
                item.details,
            )
            for item in observed.items
        )
        panels.append(
            TimelinePanel(
                prefix + "-chevrons",
                "Object execution lanes",
                observed.lanes,
                items,
                "relative",
                "precedence_layers",
                "Chevron position is longest-path rank of supplied precedence edges, "
                "not elapsed time. Incomparable events can share a layer; equal layers "
                "do not prove simultaneity. Shared appearances retain one semantic event ID. "
                "Explicit tie-break conventions remain marked on graph edges.",
            )
        )
    panels.extend(
        (
            _table(
                prefix + "-ties",
                "Unresolved execution order ties",
                ("object_id", "event_ids", "observed_time"),
                (
                    (tie.object_id, _json(tie.event_ids), _iso(tie.time))
                    for tie in value.order_ties
                ),
            ),
            _table(
                prefix + "-excluded",
                "Excluded execution relations",
                ("event_id", "object_id", "qualifier"),
                ((r.event, r.object, r.qualifier) for r in value.excluded_relations),
                "Excluded relations are evidence of the extraction boundary; they are not selected edges.",
            ),
        )
    )
    return tuple(panels)


def _executions(value):
    panels = [
        _table(
            "oc-execution-populations",
            "Execution populations",
            ("population", "count", "unit"),
            (
                ("unique_events", value.unique_event_count, "distinct_events"),
                (
                    "event_memberships",
                    value.event_membership_count,
                    "execution_memberships",
                ),
                ("unique_objects", value.unique_object_count, "distinct_objects"),
                (
                    "object_memberships",
                    value.object_membership_count,
                    "execution_memberships",
                ),
            ),
            "Overlapping executions do not create new events or objects.",
        )
    ]
    panels.append(
        _table(
            "oc-execution-membership",
            "Execution membership and exclusions",
            ("population", "entity_id", "execution_ids"),
            [
                ("event", m.entity_id, _json(m.execution_ids))
                for m in value.event_memberships
            ]
            + [
                ("object", m.entity_id, _json(m.execution_ids))
                for m in value.object_memberships
            ]
            + [
                (name, entity_id, None)
                for name in (
                    "unassigned_event_ids",
                    "unassigned_object_ids",
                    "isolated_event_ids",
                    "isolated_object_ids",
                    "excluded_object_ids",
                    "overlapping_event_ids",
                    "overlapping_object_ids",
                )
                for entity_id in getattr(value, name)
            ],
        )
    )
    for execution in value.executions:
        panels.extend(_execution(execution))
    return tuple(panels)


def _variants(value):
    variants = value.variants if isinstance(value, VariantSet) else (value,)
    return (
        ChartPanel(
            "oc-variants",
            "Object-centric variant frequencies",
            "bar",
            (
                ChartSeries(
                    "executions",
                    tuple(ChartPoint(v.variant_id, v.frequency) for v in variants),
                ),
            ),
            y_unit="execution_memberships",
            x_label="Variant",
            y_label="Executions",
            description="Exact incidence equivalence. Membership count is not a count of unique events.",
        ),
        _table(
            "oc-variant-members",
            "Variant membership and representative",
            (
                "variant_id",
                "frequency",
                "representative_execution",
                "execution_ids",
                "canonical_signature",
            ),
            (
                (
                    v.variant_id,
                    v.frequency,
                    v.representative_execution_id,
                    _json(v.execution_ids),
                    v.canonical_signature,
                )
                for v in variants
            ),
            "This payload contains no representative event/object graph; a signature cannot reconstruct "
            "chevrons. Visualize the corresponding ProcessExecution for lanes.",
        ),
    )


def _alignment(value):
    rows, items = [], []
    for i, move in enumerate(value.moves):
        objects = tuple((typ, oid) for typ, ids in move.objects for oid in ids)
        rows.append(
            (
                i,
                move.kind,
                move.event_id,
                move.transition_id,
                move.activity,
                move.cost,
                move.weight,
                _json(move.objects),
                _json(move.before_marking),
                _json(move.after_marking),
            )
        )
        lanes = objects or ((None, None),)
        for typ, oid in lanes:
            items.append(
                TimelineItem(
                    _id("alignment-appearance", i, oid),
                    _id("alignment-lane", oid),
                    i,
                    i,
                    move.activity or move.transition_id or move.kind,
                    typ,
                    move.kind,
                    _fields(
                        semantic_move_id=_id("alignment-move", i),
                        event_id=move.event_id,
                        transition_id=move.transition_id,
                        object_id=oid,
                        cost_ownership="single move row; lane appearance does not add cost",
                    ),
                )
            )
    groups = dict(value.scope.selected_objects)
    groups.update(
        {oid: typ for move in value.moves for typ, ids in move.objects for oid in ids}
    )
    lanes = tuple(
        TimelineLane(_id("alignment-lane", oid), oid, typ)
        for oid, typ in sorted(groups.items())
    )
    if any(not any(ids for _, ids in m.objects) for m in value.moves):
        lanes += (
            TimelineLane(_id("alignment-lane", None), "Moves with no selected objects"),
        )
    return (
        _scope_graph(value.scope),
        _table(
            "oc-alignment-status",
            "Joint alignment status",
            (
                "status",
                "cost",
                "lower_bound_cost",
                "cost_unit",
                "settled_states",
                "discovered_states",
            ),
            (
                (
                    value.status,
                    value.cost,
                    value.lower_bound_cost,
                    value.cost_unit,
                    value.settled_states,
                    value.discovered_states,
                ),
            ),
            "Search-limited or unreachable results do not imply a fitting path; missing costs remain unknown.",
        ),
        _table(
            "oc-alignment-moves",
            "One row per joint alignment move",
            (
                "step",
                "kind",
                "event_id",
                "transition_id",
                "activity",
                "cost",
                "weight",
                "objects_by_type",
                "before_tokens",
                "after_tokens",
            ),
            rows,
            f"Cost unit: {value.cost_unit}. A shared synchronous move is counted once.",
        ),
        TimelinePanel(
            "oc-alignment-lanes",
            "Joint alignment object lanes",
            lanes,
            tuple(items),
            "relative",
            "alignment_steps",
            "Horizontal position is joint move index, not time. "
            "Repeated lane appearances reference one semantic_move_id; cost is only in the move table.",
        ),
    )


def _token_rows(tokens):
    return _json(tuple((t.place_id, t.object_id) for t in tokens))


def _replay(value):
    return (
        _scope_graph(value.scope),
        _table(
            "oc-replay-status",
            "Joint replay coverage and token fitness",
            (
                "status",
                "processed_events",
                "scheduled_events",
                "token_fitness",
                "fitting",
                "final_reached",
                "limit_reason",
            ),
            (
                (
                    value.status,
                    value.processed_event_count,
                    len(value.event_order),
                    value.token_fitness,
                    value.fitting,
                    value.final_reached,
                    value.limit_reason,
                ),
            ),
            f"Replay profile: {value.profile}. Token repair and incomplete search do not certify conformance.",
        ),
        _table(
            "oc-replay-steps",
            "Joint replay token evidence",
            (
                "step",
                "kind",
                "event_id",
                "transition_id",
                "objects_by_type",
                "before_tokens",
                "inserted_tokens",
                "consumed_tokens",
                "produced_tokens",
                "after_tokens",
                "deviation_reason",
            ),
            (
                (
                    i,
                    s.kind,
                    s.event_id,
                    s.binding.transition_id if s.binding else None,
                    _json(s.binding.objects) if s.binding else None,
                    _token_rows(s.marking_before),
                    _token_rows(s.inserted_tokens),
                    _token_rows(s.consumed_tokens),
                    _token_rows(s.produced_tokens),
                    _token_rows(s.marking_after),
                    s.deviation_reason,
                )
                for i, s in enumerate(value.steps)
            ),
            "Token snapshots retain multiplicity. Step index is replay order, not measured time.",
        ),
    )


def _flattened(value):
    return (
        _scope_graph(value.scope),
        _table(
            "oc-flat-replay",
            "Per-object projected replay",
            (
                "object_id",
                "object_type",
                "status",
                "event_occurrences",
                "token_fitness",
                "missing",
                "remaining",
                "consumed",
                "produced",
            ),
            (
                (
                    r.object_id,
                    r.object_type,
                    r.replay.status,
                    r.replay.event_count,
                    r.token_fitness,
                    r.replay.counts.missing,
                    r.replay.counts.remaining,
                    r.replay.counts.consumed,
                    r.replay.counts.produced,
                )
                for r in value.objects
            ),
            f"{value.source_event_count} distinct source events produce "
            f"{value.projected_event_occurrence_count} projected occurrences. "
            f"Completed objects: {value.completed_count}; limited: {value.limited_count}. "
            "These are independent projections, not proof of a jointly executable object binding.",
        ),
        _table(
            "oc-flat-unrepresented",
            "Events absent from projections",
            ("event_id",),
            ((eid,) for eid in value.unrepresented_event_ids),
        ),
    )


def _formula_label(node):
    return f"{node.aggregation}({node.measure}) {node.comparator} {node.threshold} {node.unit}"


def _constraint_spec(value):
    nodes, edges = {}, []

    def add(node):
        if isinstance(node, ActivityNode):
            visual = _node("activity", node.name)
        elif isinstance(node, ObjectTypeNode):
            visual = _node("object_type", node.name, group=node.name)
        elif isinstance(node, FormulaNode):
            key = _json(
                (
                    node.measure,
                    node.comparator,
                    node.threshold,
                    node.aggregation,
                    node.object_type,
                    node.unit,
                    node.missing_policy,
                )
            )
            visual = _node(
                "formula",
                key,
                _formula_label(node),
                measure=node.measure,
                comparator=node.comparator,
                threshold=node.threshold,
                aggregation=node.aggregation,
                object_type=node.object_type,
                unit=node.unit,
                missing_policy=node.missing_policy,
            )
        else:
            raise TypeError("unsupported constraint node")
        nodes[visual.id] = visual
        return visual.id

    for family in (
        "oa_edges",
        "aa_edges",
        "aoa_edges",
        "cf_edges",
        "object_edges",
        "performance_edges",
    ):
        for edge in getattr(value, family):
            source, target = add(edge.source), add(edge.target)
            details = {"constraint_id": edge.id, "family": family}
            if isinstance(edge, (AAEdge, PerformanceEdge)):
                formula = edge.formula if isinstance(edge, AAEdge) else edge.source
                label = _formula_label(formula)
                details.update(
                    measure=formula.measure,
                    unit=formula.unit,
                    aggregation=formula.aggregation,
                    missing_policy=formula.missing_policy,
                    object_type=formula.object_type,
                )
                if isinstance(edge, AAEdge):
                    formula_id = add(formula)
                    edges.append(
                        VisualEdge(
                            _id("constraint-formula", edge.id),
                            source,
                            formula_id,
                            "source activity measurement",
                            "formula_annotation",
                        )
                    )
                    details["metric_scope"] = (
                        "source activity; not source-to-target duration"
                    )
            else:
                label = f"{edge.label} {edge.operator} {edge.threshold}"
                details.update(
                    relation=edge.label,
                    comparator=edge.operator,
                    threshold=edge.threshold,
                )
                if hasattr(edge, "object_type"):
                    details["object_type"] = edge.object_type
            if isinstance(edge, AOAEdge):
                middle = add(edge.inner)
                details["object_type"] = edge.inner.name
                edges.append(
                    VisualEdge(
                        _id("constraint-scope", edge.id),
                        source,
                        middle,
                        "quantified object type",
                        "constraint_scope",
                        details=_fields(constraint_id=edge.id),
                    )
                )
            edges.append(
                VisualEdge(
                    _id("constraint", edge.id),
                    source,
                    target,
                    label,
                    family,
                    details=_fields(**details),
                )
            )
    return (
        GraphPanel(
            "oc-constraints",
            "Object-centric constraint graph",
            tuple(nodes.values()),
            tuple(edges),
            description=f"Occurrence profile: {value.occurrence_profile}; tie policy: "
            f"{value.tie_policy}; qualifiers: {_json(value.qualifiers)}. Graph rules are conditions, "
            "not observed causality. Activity/object-type/formula identities are distinct.",
        ),
    )


def _constraint_evaluation(value, source):
    panels = ()
    if source is not None and isinstance(source.spec, ConstraintGraphSpec):
        panels = _constraint_spec(source.spec)
    return panels + (
        _table(
            "oc-constraint-evaluations",
            "Constraint condition evaluations",
            (
                "edge_id",
                "family",
                "metric",
                "numerator",
                "denominator",
                "condition_met",
                "unknown_count",
                "witness_ids",
                "reason",
            ),
            (
                (
                    e.edge_id,
                    e.family,
                    e.metric,
                    e.numerator,
                    e.denominator,
                    e.condition_met,
                    e.unknown_count,
                    _json(e.witness_ids),
                    e.reason,
                )
                for e in value.edges
            ),
            "condition_met means the stated predicate triggered; it does not automatically "
            "mean pass or fail. Null is unknown. Definitions and metric units belong to "
            "the source ConstraintGraphSpec; a raw evaluation cannot reconstruct them.",
        ),
    )


def _rule(value):
    return (
        _table(
            "oc-rule",
            "Object relation rule witnesses",
            (
                "unit_id",
                "object_id",
                "activation_event",
                "satisfied",
                "event_ids",
                "object_ids",
            ),
            (
                (
                    w.unit_id,
                    w.object_id,
                    w.activation_event_id,
                    w.satisfied,
                    _json(w.event_ids),
                    _json(w.object_ids),
                )
                for w in value.witnesses
            ),
            f"Relation: {value.relation}; population: {value.population}; profile: "
            f"{value.occurrence_profile}; numerator/denominator: {value.numerator}/{value.denominator}; "
            f"metric: {value.metric if value.metric is not None else 'unknown'}.",
        ),
    )


def _qualifiers(value):
    return (
        _table(
            "oc-qualifier-conformance",
            "Qualified relation conformance",
            (
                "event_id",
                "source_object",
                "target_object",
                "qualifiers",
                "attribute_value",
                "attribute_type",
                "assigned_at",
                "allowed",
                "reason",
            ),
            (
                (
                    w.event_id,
                    w.source_object_id,
                    w.target_object_id,
                    _json(w.qualifiers),
                    _scalar_ocel(w.value),
                    w.value.kind if w.value else None,
                    _iso(w.assigned_at),
                    w.allowed,
                    w.reason,
                )
                for w in value.witnesses
            ),
            f"Relation kind: {value.relation_kind}; profile: {value.profile}. Population: "
            f"{value.population}; allowed: {value.allowed_count}; forbidden: {value.forbidden_count}; "
            f"unknown: {value.unknown_count}. Unknown is not forbidden or allowed.",
        ),
    )


def _scalar_ocel(value):
    if value is None:
        return None
    item = value.native_value
    return _iso(item) if isinstance(item, datetime) else item


def _performance(value):
    panels = [
        _table(
            "oc-performance-summary",
            "Object-centric performance populations",
            (
                "metric",
                "unit",
                "population",
                "known",
                "unknown",
                "total",
                "minimum",
                "maximum",
                "mean_numerator",
                "mean_denominator",
            ),
            (
                (
                    s.metric,
                    s.unit,
                    s.population_count,
                    s.known_count,
                    s.unknown_count,
                    s.total,
                    s.minimum,
                    s.maximum,
                    s.mean_numerator,
                    s.mean_denominator,
                )
                for s in value.summaries
            ),
            f"Profile: {value.profile}. Exact rational means retain their denominator. "
            "Lifecycle observations are not replay token arrivals; unknown samples remain explicit.",
        )
    ]
    rows, observed, evidence_rows = [], {}, []
    for summary in value.summaries:
        for i, s in enumerate(summary.samples):
            rows.append(
                (
                    s.metric,
                    s.unit,
                    i,
                    s.event_id,
                    s.object_id,
                    s.object_type,
                    s.value,
                    s.reason,
                    _iso(s.completion_time),
                    _iso(s.explicit_start_time),
                    _json(s.related_object_ids),
                    _json(s.reference_event_ids),
                )
            )
            for w in s.evidence:
                evidence_rows.append(
                    (
                        s.metric,
                        i,
                        w.kind,
                        w.object_id,
                        w.source_event_id,
                        w.target_event_id,
                        _iso(w.source_time),
                        _iso(w.target_time),
                        _json(tuple(r.qualifier for r in w.source_relations)),
                        _json(tuple(r.qualifier for r in w.target_relations)),
                    )
                )
                for eid, time in (
                    (w.source_event_id, w.source_time),
                    (w.target_event_id, w.target_time),
                ):
                    key = (w.object_id, eid)
                    if key in observed and observed[key][1] != time:
                        raise ValueError(
                            "performance evidence has conflicting event timestamps"
                        )
                    observed[key] = (w.object_type, time)
    panels += [
        _table(
            "oc-performance-samples",
            "Performance samples",
            (
                "metric",
                "unit",
                "sample_index",
                "event_id",
                "object_id",
                "object_type",
                "value",
                "unknown_reason",
                "completion_time",
                "explicit_start_time",
                "related_objects",
                "reference_events",
            ),
            rows,
        ),
        _table(
            "oc-performance-evidence",
            "Observed timing evidence",
            (
                "metric",
                "sample_index",
                "kind",
                "object_id",
                "source_event",
                "target_event",
                "source_time",
                "target_time",
                "source_qualifiers",
                "target_qualifiers",
            ),
            evidence_rows,
        ),
    ]
    if observed:
        types = {oid: typ for (oid, _), (typ, _) in observed.items()}
        panels.append(
            TimelinePanel(
                "oc-performance-times",
                "Observed timing evidence by object",
                tuple(
                    TimelineLane(_id("lane", oid), oid, typ)
                    for oid, typ in sorted(types.items())
                ),
                tuple(
                    TimelineItem(
                        _id("performance-appearance", oid, eid),
                        _id("lane", oid),
                        _seconds(time),
                        _seconds(time),
                        eid,
                        typ,
                        details=_fields(
                            event_id=eid,
                            semantic_event_id=_id("event", eid),
                            observed_time=_iso(time),
                        ),
                    )
                    for (oid, eid), (typ, time) in sorted(observed.items())
                ),
                "timestamp",
                "seconds",
                "Only timestamp observations retained in the calculation evidence are shown. "
                "No service interval, initial-token time or missing sample time is invented.",
            )
        )
    return tuple(panels)


def _replay_performance(value):
    return _performance(value.measurements) + (
        _table(
            "oc-token-arrivals",
            "Replay token clock ledger",
            (
                "event_id",
                "step",
                "serial",
                "place_id",
                "object_id",
                "object_type",
                "arrival_time",
                "origin",
                "produced_step",
                "source_events",
                "unknown_reason",
            ),
            (
                (
                    i.event_id,
                    i.step_index,
                    t.token_serial,
                    t.place_id,
                    t.object_id,
                    t.object_type,
                    _iso(t.arrival_time),
                    t.origin,
                    t.produced_step,
                    _json(t.source_event_ids),
                    t.unknown_reason,
                )
                for i in value.token_inputs
                for t in i.arrivals
            ),
            f"Replay status: {value.replay_status}; token policy: {value.token_selection}; silent policy: "
            f"{value.silent_policy}. Missing/initial token times remain unknown; token serials retain multiplicity.",
        ),
        _table(
            "oc-token-input-coverage",
            "Token input coverage",
            ("event_id", "step", "known", "unknown", "reason"),
            (
                (i.event_id, i.step_index, i.known_count, i.unknown_count, i.reason)
                for i in value.token_inputs
            ),
        ),
    )


def _temporal(value):
    units = (
        ("event_count", "distinct_events"),
        ("object_count", "distinct_objects"),
        ("participation_count", "distinct_event_object_pairs"),
        ("e2o_relation_count", "qualified_e2o_rows"),
    )
    panels = [
        ChartPanel(
            "oc-time-" + metric,
            "Temporal " + metric.replace("_", " "),
            "bar",
            (
                ChartSeries(
                    unit,
                    tuple(
                        ChartPoint(_iso(b.time), getattr(b, metric))
                        for b in value.buckets
                    ),
                ),
            ),
            x_type="time",
            x_label="Observed UTC instant",
            y_label=metric,
            x_unit="ISO8601",
            y_unit=unit,
            description=f"Exact timestamp buckets, not intervals. Population: {value.event_population}. "
            "Tied events remain in the same bucket; distinct objects must not be summed across buckets.",
        )
        for metric, unit in units
    ]
    panels.append(
        _table(
            "oc-time-population",
            "Temporal selected population",
            ("population", "count", "unit"),
            (
                ("source_events", value.source_event_count, "distinct_events"),
                ("selected_events", value.selected_event_count, "distinct_events"),
                (
                    "participating_events",
                    value.participating_event_count,
                    "distinct_events",
                ),
                ("objects", value.object_count, "distinct_objects"),
                (
                    "participations",
                    value.participation_count,
                    "distinct_event_object_pairs",
                ),
                ("qualified_relations", value.e2o_relation_count, "qualified_e2o_rows"),
            ),
            f"Counting profile: {value.counting_profile}; event population: {value.event_population}. "
            "These are whole-selected-population counts; distinct objects can recur across buckets.",
        )
    )
    panels.append(
        _table(
            "oc-time-participations",
            "Temporal participation witnesses",
            ("time", "event_id", "object_id", "object_type", "qualifiers"),
            (
                (
                    _iso(b.time),
                    p.event_id,
                    p.object_id,
                    p.object_type,
                    _json(p.qualifiers),
                )
                for b in value.buckets
                for p in b.participations
            ),
        )
    )
    panels.append(
        _table(
            "oc-time-orphans",
            "Events without selected relations",
            ("time", "event_id"),
            (
                (_iso(b.time), eid)
                for b in value.buckets
                for eid in b.events_without_selected_relations
            ),
        )
    )
    return tuple(panels)


def _cube(value):
    panels = []
    for entity in ("event", "object"):
        changes = tuple(c for c in value.changes if c.entity == entity)
        counts = Counter((c.before_type, c.after_type) for c in changes)
        rows = tuple(sorted({a for a, _ in counts}))
        columns = tuple(sorted({b for _, b in counts}))
        panels.append(
            MatrixPanel(
                "oc-cube-" + entity,
                f"Cube {value.operation}: {entity} type changes",
                rows,
                columns,
                tuple(
                    MatrixCell(a, b, counts.get((a, b), 0))
                    for a in rows
                    for b in columns
                ),
                (
                    VisualField(
                        "value",
                        "Number of explicitly changed entities; zero means no recorded change for this pair.",
                    ),
                ),
                "changed_" + entity + "s",
                "This is a type-relabeling plan matrix, not a multidimensional "
                "event-count cube. Unchanged entities are not in this payload; totals are not source population totals.",
            )
        )
    panels += [
        _table(
            "oc-cube-evidence",
            "Cube entity changes and classification evidence",
            (
                "entity",
                "entity_id",
                "before_type",
                "after_type",
                "attribute_type",
                "attribute_value",
                "assigned_at",
                "qualified_relations",
            ),
            (
                (
                    c.entity,
                    c.entity_id,
                    c.before_type,
                    c.after_type,
                    c.attribute_value.kind if c.attribute_value else None,
                    _scalar_ocel(c.attribute_value),
                    _iso(c.assigned_at),
                    _json(tuple((r.event, r.object, r.qualifier) for r in c.relations)),
                )
                for c in value.changes
            ),
        ),
        _table(
            "oc-cube-unclassified",
            "Unclassified objects",
            ("object_id", "reason"),
            ((r.object_id, r.reason) for r in value.unclassified),
        ),
    ]
    return tuple(panels)


def _statistics(value):
    rows = tuple(
        (
            a.activity,
            a.object_type,
            a.event_count,
            a.object_count,
            a.unique_participation_count,
            a.e2o_relation_count,
            a.any_object_repeats_activity,
            a.any_event_has_multiple_same_type_objects,
        )
        for a in value.activity_object_types
    )
    return (
        _table(
            "oc-stat-populations",
            "OCEL population counts",
            ("population", "count", "unit"),
            (
                ("source_events", value.source_event_count, "distinct_events"),
                ("objects", value.object_count, "distinct_objects"),
                (
                    "participating_events",
                    value.participating_event_count,
                    "distinct_events",
                ),
                (
                    "participating_objects",
                    value.participating_object_count,
                    "distinct_objects",
                ),
                (
                    "participations",
                    value.unique_participation_count,
                    "distinct_event_object_pairs",
                ),
                ("qualified_relations", value.e2o_relation_count, "qualified_e2o_rows"),
            ),
            f"Counting profile: {value.counting_profile}. Shared participation does not duplicate source events.",
        ),
        _table(
            "oc-stat-activity-type",
            "Activity/object-type participation",
            (
                "activity",
                "object_type",
                "events",
                "objects",
                "event_object_pairs",
                "qualified_relations",
                "any_repeated_activity_per_object",
                "any_multiple_objects_per_event",
            ),
            rows,
            "Only positive participation pairs are included. Counts of events/objects are distinct per row.",
        ),
        _table(
            "oc-stat-lifecycles",
            "Object lifecycle observations",
            (
                "object_id",
                "object_type",
                "events",
                "qualified_relations",
                "first_time",
                "last_time",
                "duration_microseconds",
                "first_events",
                "last_events",
            ),
            (
                (
                    o.object_id,
                    o.object_type,
                    o.event_count,
                    o.e2o_relation_count,
                    _iso(o.first_time),
                    _iso(o.last_time),
                    o.duration_microseconds,
                    _json(o.first_event_ids),
                    _json(o.last_event_ids),
                )
                for o in value.objects
            ),
            "Duration is last minus first observed timestamp, not active service time. Eventless objects retain nulls.",
        ),
    )


def _interleavings(value):
    nodes, edges, points, segments = {}, [], {}, set()

    def point_id(point):
        return _id(
            "interleaving-point",
            point.side,
            point.case_id,
            point.event_id,
            point.boundary,
        )

    for witness in value.witnesses:
        for segment in (witness.left_segment, witness.right_segment):
            for point in segment:
                pid = point_id(point)
                points[pid] = point
                nodes[pid] = VisualNode(
                    pid,
                    point.activity
                    if point.activity is not None
                    else point.boundary or point.event_id,
                    "logical_boundary" if point.boundary else "event",
                    point.side,
                    details=_fields(
                        side=point.side,
                        case_id=point.case_id,
                        event_id=point.event_id,
                        source_position=point.source_position,
                        observed_time=_iso(point.timestamp),
                        activity=point.activity,
                        boundary=point.boundary,
                    ),
                )
            segments.add((point_id(segment[0]), point_id(segment[1])))
    edges.extend(
        VisualEdge(
            _id("interleaving-segment", a, b),
            a,
            b,
            "witness segment",
            "within_process_segment",
        )
        for a, b in sorted(segments)
    )
    edges.extend(
        VisualEdge(
            _id("interleaving-cross", i),
            point_id(w.source),
            point_id(w.target),
            w.direction,
            "cross_process_candidate",
            metrics=(VisualMetric("elapsed", w.elapsed_seconds, "seconds"),),
            details=_fields(
                witness_index=i,
                left_case_id=w.left_case_id,
                right_case_id=w.right_case_id,
            ),
        )
        for i, w in enumerate(value.witnesses)
    )
    lane_keys = sorted({(p.side, p.case_id) for p in points.values()})
    return (
        GraphPanel(
            "oc-interleavings",
            "Cross-process interleaving witnesses",
            tuple(nodes.values()),
            tuple(edges),
            description="Left and right source namespaces remain separate even when IDs/labels agree. "
            "Within-process segments and directed cross-process candidates are different edge kinds. "
            "Only witness segments are available; this is not either complete source DFG. Logical "
            "start/end boundaries contain no fabricated events or timestamps.",
        ),
        TimelinePanel(
            "oc-interleavings-time",
            "Observed interleaving points",
            tuple(
                TimelineLane(
                    _id("interleaving-lane", side, cid), f"{side}: {cid}", side
                )
                for side, cid in lane_keys
            ),
            tuple(
                TimelineItem(
                    pid,
                    _id("interleaving-lane", p.side, p.case_id),
                    _seconds(p.timestamp),
                    _seconds(p.timestamp),
                    p.activity or p.event_id,
                    p.side,
                    details=_fields(
                        side=p.side,
                        case_id=p.case_id,
                        event_id=p.event_id,
                        observed_time=_iso(p.timestamp),
                    ),
                )
                for pid, p in points.items()
                if p.timestamp is not None
            ),
            "timestamp",
            "seconds",
            "Logical boundaries are omitted from the clock axis. Crossings are observed candidates, "
            "not causality, permissions, or proof that the cases are one process.",
        ),
        _table(
            "oc-interleaving-links",
            "Explicit selected case links",
            ("left_case_id", "right_case_id"),
            ((link.left_case_id, link.right_case_id) for link in value.case_links),
            f"Left source: {value.left_digest}; right source: {value.right_digest}. "
            f"Selected event population: {value.linked_event_count}; witnesses: {len(value.witnesses)}.",
        ),
    )


def _interleavings_report(value):
    event_nodes = tuple(
        _node(
            "event",
            i.ocel_id,
            i.source_id,
            i.side,
            source_id=i.source_id,
            source_side=i.side,
        )
        for i in value.event_identities
    )
    object_nodes = tuple(
        _node(
            "object",
            i.ocel_id,
            i.source_id,
            i.side,
            source_id=i.source_id,
            source_side=i.side,
        )
        for i in value.object_identities
    )
    edges = tuple(
        VisualEdge(
            _id("interleaving-association", a.event_id, a.object_id, a.qualifier),
            _id("event", a.event_id),
            _id("object", a.object_id),
            a.qualifier,
            "cross_case_candidate",
            metrics=(
                VisualMetric(
                    "witnesses", len(a.witness_indices), "interleaving_witnesses"
                ),
            ),
            details=_fields(
                qualifier=a.qualifier, witness_indices=_json(a.witness_indices)
            ),
        )
        for a in value.cross_associations
    )
    return (
        GraphPanel(
            "oc-interleaving-projection",
            "Interleaving OCEL cross-case associations",
            event_nodes + object_nodes,
            edges,
            "bipartite",
            "Cross-association evidence only. Original source IDs remain side-qualified. The report "
            "alone does not contain each event's own-case membership or complete OCEL facts.",
        ),
        _table(
            "oc-interleaving-dispositions",
            "Skipped boundary associations",
            ("witness_index",),
            ((i,) for i in value.skipped_boundary_witness_indices),
            f"Total witnesses: {value.witness_count}; own-case E2O count: {value.own_case_relation_count}. "
            f"Derived OCEL digest: {value.ocel_digest}. Boundary witnesses cannot become synthetic OCEL events.",
        ),
    )


def _interleavings_conversion(value):
    if value.candidate is None:
        return (
            _table(
                "oc-interleaving-unavailable",
                "Interleaving conversion unavailable",
                ("code", "message"),
                ((issue.code, issue.message) for issue in value.evidence.issues),
            ),
        )
    return _ocel(value.candidate) + _interleavings_report(value.evidence.value)


def object_panels(value, *, source=None):
    """Return explicit OC domain panels or ``None`` for an unsupported payload.

    ``source`` is the original result envelope when available, supplying rule
    definitions. The caller owns top-level provenance/status presentation.
    """
    if source is not None and not isinstance(source, ComputationResult):
        raise TypeError("source must be the original ComputationResult or None")
    if source is not None and source.value != value:
        raise ValueError("source envelope value differs from the visualized value")
    dispatch = (
        (OCEL, _ocel),
        (ObjectGraph, _object_graph),
        (ObjectRelations, _object_relations),
        (ETOTGraph, _etot),
        (OTGGraph, _otg),
        (ObjectCentricDFG, _ocdfg),
        (ProcessExecution, _execution),
        (ExecutionSet, _executions),
        (VariantSet, _variants),
        (ExecutionVariant, _variants),
        (ObjectAlignment, _alignment),
        (ObjectReplay, _replay),
        (FlattenedReplay, _flattened),
        (ConstraintGraphSpec, _constraint_spec),
        (ObjectRuleMetric, _rule),
        (QualifierConformance, _qualifiers),
        (OCPerformance, _performance),
        (OCReplayPerformance, _replay_performance),
        (TemporalSummary, _temporal),
        (CubePlan, _cube),
        (ObjectStatistics, _statistics),
        (InterleavingSet, _interleavings),
        (InterleavingsOCELReport, _interleavings_report),
        (InterleavingsOCELConversion, _interleavings_conversion),
    )
    if isinstance(value, ConstraintGraphEvaluation):
        return _constraint_evaluation(value, source)
    for kind, adapter in dispatch:
        if isinstance(value, kind):
            return adapter(value)
    return None


__all__ = ("object_panels",)
