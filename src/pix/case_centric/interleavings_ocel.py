"""Project two native case logs and verified interleavings to a derived OCEL.

An interleaving is a candidate cross-case association, not a causal assertion.
Every real source event retains its own-case relation. LR adds the left source
event to the right target case; RL does the reverse. Logical boundary points
never become fabricated events or cross associations.

The immutable analytical envelope contains evidence only. Both raw CaseLogs
remain separate sidecars so nested attributes, nonfinite values, lexical forms,
global defaults and metadata survive even when OCEL projection is unavailable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest
from pix.event_log.adapters import CaseOCELMapping, to_ocel
from pix.ocel.build import build
from pix.ocel.canonical import canonical_digest
from pix.ocel.model import E2O, OCEL, Attribute, EventType

OPERATOR_ID = "pix.case_centric.from_interleavings"


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _tuple(value: object, kind: type, name: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(v, kind) for v in value):
        raise TypeError(f"{name} must be a tuple of {kind.__name__}")


def _scoped(side: str, kind: str, identifier: str) -> str:
    return "pix.interleavings:" + json.dumps(
        [side, kind, identifier], ensure_ascii=False, separators=(",", ":")
    )


@dataclass(frozen=True, slots=True)
class InterleavingsOCELSpec:
    left_object_type: str = "left_case"
    right_object_type: str = "right_case"
    own_case_qualifier: str = "case"
    cross_case_qualifier: str = "interleaving_candidate"
    event_type_scope: str = "shared"
    max_events: int = 1_000_000
    max_objects: int = 1_000_000
    max_relations: int = 3_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in (
            "left_object_type",
            "right_object_type",
            "own_case_qualifier",
            "cross_case_qualifier",
        ):
            _text(getattr(self, name), name)
        if self.left_object_type == self.right_object_type:
            raise ValueError("left and right object types must differ")
        if self.own_case_qualifier == self.cross_case_qualifier:
            raise ValueError("own-case and candidate cross-case qualifiers must differ")
        if self.event_type_scope not in ("shared", "side"):
            raise ValueError("event_type_scope must be shared or side")
        for name in ("max_events", "max_objects", "max_relations"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class InterleavingEntityIdentity:
    side: str
    source_id: str
    ocel_id: str

    def __post_init__(self) -> None:
        if self.side not in ("left", "right"):
            raise ValueError("side must be left or right")
        _text(self.source_id, "source_id")
        _text(self.ocel_id, "ocel_id")


@dataclass(frozen=True, slots=True)
class InterleavingCrossAssociation:
    event_id: str
    object_id: str
    qualifier: str
    witness_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        for name in ("event_id", "object_id", "qualifier"):
            _text(getattr(self, name), name)
        if (
            not isinstance(self.witness_indices, tuple)
            or not self.witness_indices
            or any(type(i) is not int or i < 0 for i in self.witness_indices)
            or tuple(sorted(set(self.witness_indices))) != self.witness_indices
        ):
            raise ValueError(
                "witness_indices must be distinct ordered nonnegative ints"
            )


@dataclass(frozen=True, slots=True)
class InterleavingsOCELReport:
    left_digest: str
    right_digest: str
    ocel_digest: str
    event_identities: tuple[InterleavingEntityIdentity, ...]
    object_identities: tuple[InterleavingEntityIdentity, ...]
    event_type_identities: tuple[InterleavingEntityIdentity, ...]
    cross_associations: tuple[InterleavingCrossAssociation, ...]
    witness_count: int
    skipped_boundary_witness_indices: tuple[int, ...]
    own_case_relation_count: int
    transformations: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("left_digest", "right_digest", "ocel_digest"):
            _text(getattr(self, name), name)
        for name in ("event_identities", "object_identities", "event_type_identities"):
            items = getattr(self, name)
            _tuple(items, InterleavingEntityIdentity, name)
            if len({(i.side, i.source_id) for i in items}) != len(items):
                raise ValueError(f"{name} source identities must be unique per side")
            if name != "event_type_identities" and len(
                {i.ocel_id for i in items}
            ) != len(items):
                raise ValueError(f"{name} OCEL identities must be unique")
        _tuple(
            self.cross_associations, InterleavingCrossAssociation, "cross_associations"
        )
        _tuple(self.transformations, str, "transformations")
        for name in ("witness_count", "own_case_relation_count"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative int")
        skipped = self.skipped_boundary_witness_indices
        if (
            not isinstance(skipped, tuple)
            or any(type(i) is not int or i < 0 for i in skipped)
            or tuple(sorted(set(skipped))) != skipped
        ):
            raise ValueError(
                "skipped boundary witness indices must be ordered unique ints"
            )
        disposition = [
            i for item in self.cross_associations for i in item.witness_indices
        ]
        disposition.extend(skipped)
        if sorted(disposition) != list(range(self.witness_count)):
            raise ValueError("each witness must have exactly one disposition")
        if self.own_case_relation_count != len(self.event_identities):
            raise ValueError("every event must retain exactly one own-case relation")
        events = {item.ocel_id for item in self.event_identities}
        objects = {item.ocel_id for item in self.object_identities}
        relations = set()
        for association in self.cross_associations:
            if (
                association.event_id not in events
                or association.object_id not in objects
            ):
                raise ValueError(
                    "cross association must reference mapped source entities"
                )
            key = (association.event_id, association.object_id, association.qualifier)
            if key in relations:
                raise ValueError("duplicate cross association")
            relations.add(key)


@dataclass(frozen=True, slots=True)
class InterleavingsOCELConversion:
    """Derived data plus retained native sources; only evidence is serialized.

    ``ocel`` may be available with PARTIAL evidence when the verified upstream
    interleaving calculation was partial or boundary associations were skipped.
    """

    left_log: CaseLog
    right_log: CaseLog
    candidate: OCEL | None
    evidence: ComputationResult[InterleavingsOCELReport]

    def __post_init__(self) -> None:
        if not isinstance(self.left_log, CaseLog) or not isinstance(
            self.right_log, CaseLog
        ):
            raise TypeError("left_log and right_log must be CaseLog")
        if not isinstance(self.evidence, ComputationResult) or (
            self.evidence.operator_id != OPERATOR_ID
            or not isinstance(self.evidence.spec, InterleavingsOCELSpec)
        ):
            raise TypeError("evidence must be an interleavings OCEL computation")
        if self.candidate is None:
            if self.evidence.value is not None:
                raise ValueError("evidence value requires a candidate OCEL")
        else:
            if not isinstance(self.candidate, OCEL) or not isinstance(
                self.evidence.value, InterleavingsOCELReport
            ):
                raise TypeError("candidate requires OCEL projection evidence")
            if (
                canonical_digest(self.candidate).identifier
                != self.evidence.value.ocel_digest
            ):
                raise ValueError("candidate digest differs from projection evidence")
            if (
                case_log_digest(self.left_log) != self.evidence.value.left_digest
                or case_log_digest(self.right_log) != self.evidence.value.right_digest
            ):
                raise ValueError("source sidecars differ from projection evidence")

    @property
    def ocel(self) -> OCEL | None:
        return self.candidate

    @property
    def complete(self) -> bool:
        return self.evidence.status is ComputeStatus.COMPUTED

    def require_ocel(self) -> OCEL:
        if self.candidate is None:
            raise ValueError(
                "interleavings cannot be represented by the requested OCEL mapping"
            )
        return self.candidate


def from_interleavings(
    left: CaseLog,
    right: CaseLog,
    interleavings: ComputationResult,
    spec: InterleavingsOCELSpec = InterleavingsOCELSpec(),
) -> InterleavingsOCELConversion:
    """Project verified temporal interleavings without merging source identities.

    The parent request is recomputed on both original CaseLogs and must match
    exactly, including status, witnesses, issues and request identity. Hashes
    alone are not accepted as proof that supplied witnesses are correct.

    Shared event types preserve activity names. Incompatible declarations fail
    explicitly; ``event_type_scope='side'`` is an explicit alternative. Missing
    event timestamps and nonprimitive event/trace attributes also fail instead
    of producing a lossy OCEL. The complete native sources remain available.
    """
    # Delayed import avoids coupling native interleaving discovery to OCEL I/O.
    from pix.case_centric.interleavings import (
        InterleavingSpec,
        discover_interleavings,
        linked_logs_digest,
    )

    if not isinstance(left, CaseLog) or not isinstance(right, CaseLog):
        raise TypeError("left and right must be CaseLog")
    if not isinstance(spec, InterleavingsOCELSpec):
        raise TypeError("spec must be InterleavingsOCELSpec")
    if not isinstance(interleavings, ComputationResult) or not isinstance(
        interleavings.spec, InterleavingSpec
    ):
        raise TypeError("interleavings must be a computation with InterleavingSpec")
    left_digest, right_digest = case_log_digest(left), case_log_digest(right)
    source_digest = linked_logs_digest(left_digest, right_digest)
    expected = discover_interleavings(left, right, interleavings.spec)
    parents = ()

    def fail(status: ComputeStatus, issues: tuple[ComputeIssue, ...]):
        return InterleavingsOCELConversion(
            left,
            right,
            None,
            _derived_result(
                OPERATOR_ID,
                source_digest,
                spec,
                status,
                None,
                issues,
                parent_computation_ids=parents,
            ),
        )

    if interleavings != expected:
        return fail(
            ComputeStatus.INVALID_INPUT,
            (
                ComputeIssue(
                    "interleaving_evidence_mismatch",
                    "Supplied interleavings do not equal recomputation on both native sources",
                ),
            ),
        )
    if expected.computation_id is not None:
        parents = (expected.computation_id,)
    if expected.value is None:
        return fail(
            expected.status,
            (
                *expected.issues,
                ComputeIssue("interleavings_unavailable", "Parent has no witnesses"),
            ),
        )
    event_count = sum(
        len(trace.events) for log in (left, right) for trace in log.traces
    )
    object_count = len(left.traces) + len(right.traces)
    candidate_count = len(
        {
            (
                witness.source.side,
                witness.source.event_id,
                witness.target.side,
                witness.target.case_id,
            )
            for witness in expected.value.witnesses
            if witness.source.boundary is None and witness.target.boundary is None
        }
    )
    for label, actual, limit in (
        ("event", event_count, spec.max_events),
        ("object", object_count, spec.max_objects),
        ("relation", event_count + candidate_count, spec.max_relations),
    ):
        if actual > limit:
            return fail(
                ComputeStatus.UNAVAILABLE,
                (
                    ComputeIssue(
                        f"interleavings_ocel_{label}_limit",
                        f"Whole-input {label} population {actual} exceeds limit {limit}; no truncated OCEL was produced",
                    ),
                ),
            )
    parent_spec = expected.spec
    projections = (
        (
            "left",
            to_ocel(
                left,
                CaseOCELMapping(
                    spec.left_object_type,
                    parent_spec.left_activity_key,
                    parent_spec.left_timestamp_key,
                    spec.own_case_qualifier,
                ),
            ),
        ),
        (
            "right",
            to_ocel(
                right,
                CaseOCELMapping(
                    spec.right_object_type,
                    parent_spec.right_activity_key,
                    parent_spec.right_timestamp_key,
                    spec.own_case_qualifier,
                ),
            ),
        ),
    )
    errors = tuple(
        ComputeIssue(issue.code, issue.message, (side, *issue.at))
        for side, projection in projections
        for issue in projection.issues
    )
    if errors:
        return fail(ComputeStatus.UNAVAILABLE, errors)
    schemas: dict[str, dict[str, Attribute]] = {}
    event_types, events, objects, object_types, relations = [], [], [], [], []
    event_ids, object_ids, type_ids = [], [], []
    for side, projection in projections:
        ocel = projection.require_ocel()
        for kind in ocel.event_types:
            name = (
                kind.name
                if spec.event_type_scope == "shared"
                else _scoped(side, "activity", kind.name)
            )
            type_ids.append(InterleavingEntityIdentity(side, kind.name, name))
            schema = schemas.setdefault(name, {})
            for declaration in kind.attributes:
                if (
                    declaration.name in schema
                    and schema[declaration.name] != declaration
                ):
                    return fail(
                        ComputeStatus.UNAVAILABLE,
                        (
                            ComputeIssue(
                                "cross_log_event_schema_conflict",
                                "Shared activity attribute declarations conflict; choose explicit side scope or revise source mapping",
                                (
                                    side,
                                    "activity",
                                    kind.name,
                                    "attribute",
                                    declaration.name,
                                ),
                            ),
                        ),
                    )
                schema[declaration.name] = declaration
        object_types.extend(ocel.object_types)
        for event in ocel.events:
            event_id = _scoped(side, "event", event.id)
            event_ids.append(InterleavingEntityIdentity(side, event.id, event_id))
            activity = (
                event.type
                if spec.event_type_scope == "shared"
                else _scoped(side, "activity", event.type)
            )
            events.append(replace(event, id=event_id, type=activity))
        for obj in ocel.objects:
            object_id = _scoped(side, "case", obj.id)
            object_ids.append(InterleavingEntityIdentity(side, obj.id, object_id))
            objects.append(replace(obj, id=object_id))
        relations.extend(
            E2O(
                _scoped(side, "event", r.event),
                _scoped(side, "case", r.object),
                r.qualifier,
            )
            for r in ocel.e2o
        )
    own_count = len(relations)
    cross: dict[tuple[str, str], list[int]] = {}
    skipped = []
    for index, witness in enumerate(expected.value.witnesses):
        if witness.source.boundary is not None or witness.target.boundary is not None:
            skipped.append(index)
            continue
        event_id = _scoped(witness.source.side, "event", witness.source.event_id)
        object_id = _scoped(witness.target.side, "case", witness.target.case_id)
        cross.setdefault((event_id, object_id), []).append(index)
    associations = tuple(
        InterleavingCrossAssociation(
            event_id, object_id, spec.cross_case_qualifier, tuple(indices)
        )
        for (event_id, object_id), indices in sorted(cross.items())
    )
    relations.extend(E2O(a.event_id, a.object_id, a.qualifier) for a in associations)
    event_types.extend(
        EventType(name, tuple(schema.values())) for name, schema in schemas.items()
    )
    built = build(
        event_types=event_types,
        object_types=object_types,
        events=events,
        objects=objects,
        e2o=relations,
    )
    if not built.valid:
        return fail(
            ComputeStatus.UNAVAILABLE,
            tuple(
                ComputeIssue(issue.code, issue.message, issue.at)
                for issue in built.report.errors
            ),
        )
    candidate = built.ocel
    issues = list(expected.issues)
    issues.append(
        ComputeIssue(
            "candidate_cross_case_associations",
            "Cross-case relations describe temporal interleaving candidates, not proven causality",
        )
    )
    if skipped:
        issues.append(
            ComputeIssue(
                "boundary_associations_omitted",
                f"{len(skipped)} witnesses have logical boundary endpoints; no synthetic events or cross relations were created",
            )
        )
    report = InterleavingsOCELReport(
        left_digest,
        right_digest,
        canonical_digest(candidate).identifier,
        tuple(event_ids),
        tuple(object_ids),
        tuple(type_ids),
        associations,
        len(expected.value.witnesses),
        tuple(skipped),
        own_count,
        (
            "native_sidecars: both complete CaseLogs retain hierarchy, lexical values, globals, classifiers, metadata and source order",
            "side_scoped_ids: source event and case identities remain distinct across logs",
            "initial_object_attributes: trace attributes use the OCEL epoch as initial values, not observation times",
            "id_as_string: XES id attribute declarations become OCEL strings; native types remain in the source sidecars",
            "global_defaults: effective primitive defaults are projected without mutating recorded source facts",
            "candidate_relations: LR source left event to target right case; RL source right event to target left case",
            "duplicate_relations: identical candidate E2O facts collapse while all witness indices remain available",
            "event_type_scope:" + spec.event_type_scope,
        ),
    )
    status = (
        ComputeStatus.PARTIAL
        if skipped or expected.status is ComputeStatus.PARTIAL
        else ComputeStatus.COMPUTED
    )
    evidence = _derived_result(
        OPERATOR_ID,
        source_digest,
        spec,
        status,
        report,
        tuple(issues),
        parent_computation_ids=parents,
    )
    return InterleavingsOCELConversion(left, right, candidate, evidence)


RESULT_SCHEMAS = {
    OPERATOR_ID: (
        "interleavings-ocel-report",
        InterleavingsOCELSpec,
        InterleavingsOCELReport,
    )
}

__all__ = [
    "InterleavingsOCELSpec",
    "InterleavingEntityIdentity",
    "InterleavingCrossAssociation",
    "InterleavingsOCELReport",
    "InterleavingsOCELConversion",
    "from_interleavings",
]
