"""Add qualified OCEL relations from explicit observational graph/lifecycle rules.

The analytical result contains a verifiable addition plan, never a duplicate raw
log. Materialization re-evaluates the plan against the exact canonical source.
Derived relations are observations; first/last mean first/last *observed* events,
not real-world creation/destruction. Every source fact and metadata is retained.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar, Literal

from pix.compute._common import _prepare, _result
from pix.compute.context import ComputationContext
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.object_centric.relations import ObjectGraphSpec, discover_object_graph
from pix.ocel import E2O, O2O, OCEL, build, canonical_digest

GRAPH_OPERATOR = "pix.object_centric.enrich_object_relations"
LIFECYCLE_OPERATOR = "pix.object_centric.mark_lifecycle_qualifiers"


def _text(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be blank")


def _choice(value: object, name: str, choices: tuple[str, ...]) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if value not in choices:
        raise ValueError(f"{name} must be one of {choices}")


def _strings(value: object, name: str, *, blank: bool = False) -> None:
    if not isinstance(value, tuple) or not all(isinstance(x, str) for x in value):
        raise TypeError(f"{name} must be a tuple of strings")
    if not blank and any(not x.strip() for x in value):
        raise ValueError(f"{name} must not contain blank strings")
    if value != tuple(sorted(set(value))):
        raise ValueError(f"{name} must be sorted and unique")


@dataclass(frozen=True, slots=True)
class ObjectRelationEnrichmentSpec:
    """Map observed graph edges to directed O2O facts with a dedicated qualifier.

    Directed graphs keep their direction. For an undirected graph ``both`` adds
    both orientations; ``lexical`` adds smaller-ID -> larger-ID only, a storage
    convention with no causal meaning. Isolates are kept, or explicitly reject
    the request; no source object is ever dropped. Under ``skip_identical`` an
    existing candidate triple is retained. Any existing output-qualifier triple
    outside the candidate set rejects the request under either collision policy,
    preventing unrelated source facts from silently acquiring a derived meaning.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    graph: ObjectGraphSpec = ObjectGraphSpec()
    qualifier: str = "pix:observed_object_relation"
    undirected: Literal["both", "lexical"] = "both"
    collision: Literal["reject", "skip_identical"] = "reject"
    isolated_objects: Literal["retain", "reject"] = "retain"

    def __post_init__(self) -> None:
        if not isinstance(self.graph, ObjectGraphSpec):
            raise TypeError("graph must be ObjectGraphSpec")
        _text(self.qualifier, "qualifier")
        _choice(self.undirected, "undirected", ("both", "lexical"))
        _choice(self.collision, "collision", ("reject", "skip_identical"))
        _choice(self.isolated_objects, "isolated_objects", ("retain", "reject"))


@dataclass(frozen=True, slots=True)
class LifecycleQualifierSpec:
    """Mark qualified-incidence first/last observations without replacing roles.

    ``None`` selects every original E2O qualifier; ``()`` selects none. Repeated
    qualifiers for the same event/object count as one observation. Boundary ties
    reject by default; interior ties do not affect endpoints. ``all_tied`` marks
    every event at the boundary; ``event_id`` picks the smallest ID at first and
    largest ID at last. A singleton receives both distinct qualifiers. Isolated
    means no selected E2O, even when the object has unselected E2O or O2O facts.
    Collision semantics are the same dedicated-qualifier rules as graph addition.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    qualifiers: tuple[str, ...] | None = None
    first_qualifier: str = "pix:first_observed"
    last_qualifier: str = "pix:last_observed"
    tie_policy: Literal["reject", "all_tied", "event_id"] = "reject"
    collision: Literal["reject", "skip_identical"] = "reject"
    isolated_objects: Literal["retain", "reject"] = "retain"

    def __post_init__(self) -> None:
        if self.qualifiers is not None:
            if not isinstance(self.qualifiers, tuple) or not all(
                isinstance(x, str) for x in self.qualifiers
            ):
                raise TypeError("qualifiers must be a tuple of strings or None")
            object.__setattr__(self, "qualifiers", tuple(sorted(set(self.qualifiers))))
        _text(self.first_qualifier, "first_qualifier")
        _text(self.last_qualifier, "last_qualifier")
        if self.first_qualifier == self.last_qualifier:
            raise ValueError("first and last qualifiers must be distinct")
        _choice(self.tie_policy, "tie_policy", ("reject", "all_tied", "event_id"))
        _choice(self.collision, "collision", ("reject", "skip_identical"))
        _choice(self.isolated_objects, "isolated_objects", ("retain", "reject"))


@dataclass(frozen=True, slots=True)
class ObjectRelationWitness:
    relation: O2O
    event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.relation, O2O):
            raise TypeError("relation must be O2O")
        _strings(self.event_ids, "event_ids")
        if not self.event_ids:
            raise ValueError("graph relation requires an event witness")


@dataclass(frozen=True, slots=True)
class LifecycleRelationWitness:
    relation: E2O
    boundary: Literal["first", "last"]
    boundary_event_ids: tuple[str, ...]
    source_qualifiers: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.relation, E2O):
            raise TypeError("relation must be E2O")
        _choice(self.boundary, "boundary", ("first", "last"))
        _strings(self.boundary_event_ids, "boundary_event_ids")
        _strings(self.source_qualifiers, "source_qualifiers", blank=True)
        if self.relation.event not in self.boundary_event_ids:
            raise ValueError("marked event must belong to its observed boundary")
        if not self.source_qualifiers:
            raise ValueError("lifecycle marking requires source incidence")


def _key(witness: ObjectRelationWitness | LifecycleRelationWitness):
    relation = witness.relation
    if isinstance(relation, O2O):
        return relation.source, relation.target, relation.qualifier
    return relation.event, relation.object, relation.qualifier


@dataclass(frozen=True, slots=True)
class OCELRelationEnrichment:
    """Only additions, retained identical candidates, witnesses and target ID."""

    target_digest: str
    added_o2o: tuple[ObjectRelationWitness, ...] = ()
    existing_o2o: tuple[ObjectRelationWitness, ...] = ()
    added_e2o: tuple[LifecycleRelationWitness, ...] = ()
    existing_e2o: tuple[LifecycleRelationWitness, ...] = ()
    isolated_object_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.target_digest, "target_digest")
        _strings(self.isolated_object_ids, "isolated_object_ids")
        for name, kind in (
            ("added_o2o", ObjectRelationWitness),
            ("existing_o2o", ObjectRelationWitness),
            ("added_e2o", LifecycleRelationWitness),
            ("existing_e2o", LifecycleRelationWitness),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(
                isinstance(x, kind) for x in values
            ):
                raise TypeError(f"{name} has an invalid witness collection")
            keys = tuple(_key(x) for x in values)
            if keys != tuple(sorted(set(keys))):
                raise ValueError(f"{name} relations must be sorted and unique")
        for added, existing in (
            (self.added_o2o, self.existing_o2o),
            (self.added_e2o, self.existing_e2o),
        ):
            if {_key(x) for x in added} & {_key(x) for x in existing}:
                raise ValueError("added and existing relations must be disjoint")


def _build(source: OCEL, added_o2o: tuple, added_e2o: tuple) -> OCEL:
    built = build(
        event_types=source.event_types,
        object_types=source.object_types,
        events=source.events,
        objects=source.objects,
        e2o=source.e2o + tuple(x.relation for x in added_e2o),
        o2o=source.o2o + tuple(x.relation for x in added_o2o),
    )
    if built.ocel is None:
        raise ValueError("relation additions did not produce valid canonical OCEL")
    return replace(built.ocel, import_info=source.import_info)


def _collisions(candidates: tuple, original: tuple, qualifiers: set[str], policy: str):
    wanted = {x.relation for x in candidates}
    occupied = {x for x in original if x.qualifier in qualifiers}
    unrelated = occupied - wanted
    repeated = occupied & wanted
    issues = []
    for relation in sorted(unrelated, key=lambda x: (x.qualifier, repr(x))):
        issues.append(
            ComputeIssue(
                "output_qualifier_conflict",
                "Output qualifier already labels a source relation outside the derived candidate set",
                (relation.qualifier, repr(relation)),
            )
        )
    if policy == "reject":
        for relation in sorted(repeated, key=lambda x: (x.qualifier, repr(x))):
            issues.append(
                ComputeIssue(
                    "existing_relation_collision",
                    "Derived relation already exists; choose skip_identical to retain it",
                    (relation.qualifier, repr(relation)),
                )
            )
    return (
        tuple(x for x in candidates if x.relation not in occupied),
        tuple(x for x in candidates if x.relation in occupied),
        tuple(issues),
    )


def _isolate_issues(isolated: tuple[str, ...], policy: str):
    if policy == "retain":
        return ()
    return tuple(
        ComputeIssue(
            "isolated_object",
            "Object has no incidence in the selected enrichment profile",
            (obj,),
        )
        for obj in isolated
    )


def enrich_object_relations(
    log: OCEL | ComputationContext,
    spec: ObjectRelationEnrichmentSpec = ObjectRelationEnrichmentSpec(),
) -> ComputationResult[OCELRelationEnrichment]:
    """Plan graph-derived O2O additions; materialize explicitly to obtain OCEL."""
    if not isinstance(spec, ObjectRelationEnrichmentSpec):
        raise TypeError("spec must be ObjectRelationEnrichmentSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            GRAPH_OPERATOR, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    graph = discover_object_graph(context, spec.graph)
    if graph.status is not ComputeStatus.COMPUTED:
        return _result(GRAPH_OPERATOR, context, spec, graph.status, None, graph.issues)
    candidates = []
    incident = set()
    for edge in graph.value.edges:
        incident.update((edge.source, edge.target))
        pairs = [(edge.source, edge.target)]
        if not graph.value.directed:
            pair = tuple(sorted((edge.source, edge.target)))
            pairs = [pair]
            if spec.undirected == "both":
                pairs.append((pair[1], pair[0]))
        for source, target in pairs:
            candidates.append(
                ObjectRelationWitness(
                    O2O(source, target, spec.qualifier), edge.event_ids
                )
            )
    isolated = tuple(sorted(set(context.objects_by_id) - incident))
    added, existing, collisions = _collisions(
        tuple(sorted(candidates, key=_key)),
        context.log.o2o,
        {spec.qualifier},
        spec.collision,
    )
    failures = _isolate_issues(isolated, spec.isolated_objects) + collisions
    if failures:
        return _result(
            GRAPH_OPERATOR,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            graph.issues + failures,
        )
    target = _build(context.log, added, ())
    value = OCELRelationEnrichment(
        canonical_digest(target).identifier,
        added_o2o=added,
        existing_o2o=existing,
        isolated_object_ids=isolated,
    )
    return _result(
        GRAPH_OPERATOR, context, spec, ComputeStatus.COMPUTED, value, graph.issues
    )


def mark_lifecycle_qualifiers(
    log: OCEL | ComputationContext,
    spec: LifecycleQualifierSpec = LifecycleQualifierSpec(),
) -> ComputationResult[OCELRelationEnrichment]:
    """Plan additional first/last observed E2O roles using selected incidence."""
    if not isinstance(spec, LifecycleQualifierSpec):
        raise TypeError("spec must be LifecycleQualifierSpec")
    context, issues = _prepare(log)
    if context is None:
        return _result(
            LIFECYCLE_OPERATOR, None, spec, ComputeStatus.INVALID_INPUT, None, issues
        )
    allowed = None if spec.qualifiers is None else set(spec.qualifiers)
    isolated = []
    candidates = []
    failures = []
    warnings = []
    for obj in sorted(context.objects_by_id):
        incidence: dict[str, set[str]] = {}
        for relation in context.e2o_by_object[obj]:
            if allowed is None or relation.qualifier in allowed:
                incidence.setdefault(relation.event, set()).add(relation.qualifier)
        if not incidence:
            isolated.append(obj)
            continue
        times = {event: context.events_by_id[event].time for event in incidence}
        for boundary, endpoint, qualifier in (
            ("first", min(times.values()), spec.first_qualifier),
            ("last", max(times.values()), spec.last_qualifier),
        ):
            tied = tuple(
                sorted(event for event, time in times.items() if time == endpoint)
            )
            selected = tied
            if len(tied) > 1:
                if spec.tie_policy == "reject":
                    failures.append(
                        ComputeIssue(
                            "ambiguous_lifecycle_boundary",
                            "Multiple selected events share the observed boundary timestamp",
                            (obj, boundary, *tied),
                        )
                    )
                    continue
                if spec.tie_policy == "event_id":
                    selected = (tied[0] if boundary == "first" else tied[-1],)
                    warnings.append(
                        ComputeIssue(
                            "timestamp_tie_broken",
                            "Event-ID order selects a boundary; it is not causal evidence",
                            (obj, boundary, *tied),
                        )
                    )
            for event in selected:
                candidates.append(
                    LifecycleRelationWitness(
                        E2O(event, obj, qualifier),
                        boundary,
                        tied,
                        tuple(sorted(incidence[event])),
                    )
                )
    isolated = tuple(isolated)
    failures.extend(_isolate_issues(isolated, spec.isolated_objects))
    added, existing, collisions = _collisions(
        tuple(sorted(candidates, key=_key)),
        context.log.e2o,
        {spec.first_qualifier, spec.last_qualifier},
        spec.collision,
    )
    failures.extend(collisions)
    if failures:
        return _result(
            LIFECYCLE_OPERATOR,
            context,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            tuple(warnings + failures),
        )
    target = _build(context.log, (), added)
    value = OCELRelationEnrichment(
        canonical_digest(target).identifier,
        added_e2o=added,
        existing_e2o=existing,
        isolated_object_ids=isolated,
    )
    return _result(
        LIFECYCLE_OPERATOR,
        context,
        spec,
        ComputeStatus.COMPUTED,
        value,
        tuple(warnings),
    )


def materialize_enriched_ocel(
    source: OCEL | ComputationContext,
    result: ComputationResult[OCELRelationEnrichment],
) -> OCEL:
    """Recompute the exact plan and identity, then build and validate the OCEL.

    Metadata is excluded from canonical identity and comes from the supplied
    source, as in other PIX materializers. The result is not an authenticity
    signature: deterministic recomputation protects semantic applicability.
    """
    if not isinstance(result, ComputationResult):
        raise TypeError("result must be ComputationResult")
    operators = {
        GRAPH_OPERATOR: (ObjectRelationEnrichmentSpec, enrich_object_relations),
        LIFECYCLE_OPERATOR: (LifecycleQualifierSpec, mark_lifecycle_qualifiers),
    }
    if (
        result.operator_id not in operators
        or result.status is not ComputeStatus.COMPUTED
        or not isinstance(result.value, OCELRelationEnrichment)
    ):
        raise ValueError("result must be a computed OCEL enrichment result")
    kind, operator = operators[result.operator_id]
    if not isinstance(result.spec, kind):
        raise ValueError("enrichment result has an incompatible specification")
    context, issues = _prepare(source)
    if context is None:
        raise ValueError(f"cannot materialize invalid source: {issues}")
    if result.source_digest != context.source_digest:
        raise ValueError("source digest does not match enrichment result")
    expected = operator(context, result.spec)
    if expected != result:
        raise ValueError("enrichment identity or relation evidence does not match")
    target = _build(context.log, result.value.added_o2o, result.value.added_e2o)
    if canonical_digest(target).identifier != result.value.target_digest:
        raise ValueError(
            "materialized target digest does not match enrichment evidence"
        )
    return target


RESULT_SCHEMAS = {
    GRAPH_OPERATOR: (
        "ocel-object-relation-enrichment",
        ObjectRelationEnrichmentSpec,
        OCELRelationEnrichment,
    ),
    LIFECYCLE_OPERATOR: (
        "ocel-lifecycle-qualifier-enrichment",
        LifecycleQualifierSpec,
        OCELRelationEnrichment,
    ),
}

__all__ = (
    "ObjectRelationEnrichmentSpec",
    "LifecycleQualifierSpec",
    "ObjectRelationWitness",
    "LifecycleRelationWitness",
    "OCELRelationEnrichment",
    "enrich_object_relations",
    "mark_lifecycle_qualifiers",
    "materialize_enriched_ocel",
)
