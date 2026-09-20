"""Attribute-preserving object-to-case projection, with explicit linearization.

Shared events create distinct case occurrences. Their source IDs, participation
and object histories remain available; projection is not lossless OCEL storage.
The complete immutable source is retained in the conversion receipt.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.ocel import OCEL, canonical_digest
from pix.ocel.validate import validate


@dataclass(frozen=True, slots=True)
class ObjectCaseProjectionSpec:
    object_type: str
    tie_policy: str = "reject"
    event_attribute_prefix: str = "event:"

    def __post_init__(self):
        if not isinstance(self.object_type, str) or not self.object_type.strip():
            raise ValueError("object_type must be nonblank text")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if (
            not isinstance(self.event_attribute_prefix, str)
            or not self.event_attribute_prefix
        ):
            raise ValueError("event_attribute_prefix must be nonempty text")


@dataclass(frozen=True, slots=True)
class ObjectCaseProjection:
    source: OCEL
    spec: ObjectCaseProjectionSpec
    case_log: CaseLog
    occurrence_source_ids: tuple[tuple[str, str], ...]
    excluded_event_ids: tuple[str, ...]
    tied_object_ids: tuple[str, ...]


def _attr(name, value):
    kind = {
        str: "string",
        int: "int",
        float: "float",
        bool: "boolean",
        datetime: "date",
    }[type(value)]
    return CaseAttribute(name, kind, value)


def project_object_cases(
    log: OCEL, spec: ObjectCaseProjectionSpec
) -> ObjectCaseProjection:
    """Project one declared object type. Ties require an explicit chosen policy.

    Event attributes are prefixed. Object histories use ordered list records rather
    than pretending an evolving value is a static case attribute. An event linked
    through multiple qualifiers occurs once per object and retains all qualifiers.
    """
    if not isinstance(log, OCEL) or not isinstance(spec, ObjectCaseProjectionSpec):
        raise TypeError("expected OCEL and ObjectCaseProjectionSpec")
    report = validate(log)
    if report.errors:
        raise ValueError("invalid OCEL: " + "; ".join(i.message for i in report.errors))
    if spec.object_type not in {t.name for t in log.object_types}:
        raise ValueError("unknown object type")
    by_object, participation = defaultdict(set), defaultdict(list)
    for rel in log.e2o:
        by_object[rel.object].add(rel.event)
        participation[rel.event].append(rel)
    events = {e.id: e for e in log.events}
    traces, lineage, ties, used = [], [], [], set()
    for obj in sorted(log.objects, key=lambda o: o.id):
        if obj.type != spec.object_type:
            continue
        selected = sorted(
            (events[e] for e in by_object[obj.id]),
            key=lambda e: (e.time.astimezone(timezone.utc), e.id),
        )
        times = [e.time.astimezone(timezone.utc) for e in selected]
        if len(times) != len(set(times)):
            if spec.tie_policy == "reject":
                raise ValueError(
                    f"object {obj.id!r} has simultaneous events; choose a tie policy"
                )
            ties.append(obj.id)
        output = []
        for event in selected:
            identifier = json.dumps(
                [obj.id, event.id], ensure_ascii=False, separators=(",", ":")
            )
            attrs = (
                _attr("concept:name", event.type),
                _attr("time:timestamp", event.time),
                _attr("pix:source_event_id", event.id),
                CaseAttribute(
                    "pix:participation",
                    "list",
                    values=tuple(
                        CaseAttribute(
                            "relation",
                            "container",
                            children=(
                                _attr("object", rel.object),
                                _attr("qualifier", rel.qualifier),
                            ),
                        )
                        for rel in sorted(
                            participation[event.id],
                            key=lambda r: (r.object, r.qualifier),
                        )
                    ),
                ),
            ) + tuple(
                _attr(spec.event_attribute_prefix + a.name, a.value)
                for a in event.attributes
            )
            if len({a.key for a in attrs}) != len(attrs):
                raise ValueError(
                    "event attribute prefix collides with projection metadata"
                )
            output.append(CaseEvent(identifier, attrs))
            lineage.append((identifier, event.id))
            used.add(event.id)
        history = CaseAttribute(
            "pix:object_history",
            "list",
            values=tuple(
                CaseAttribute(
                    "change",
                    "container",
                    children=(
                        _attr("name", a.name),
                        _attr("time", a.time),
                        _attr("value", a.value),
                    ),
                )
                for a in sorted(obj.attributes, key=lambda a: (a.time, a.name))
            ),
        )
        traces.append(
            CaseTrace(
                obj.id,
                tuple(output),
                (
                    _attr("concept:name", obj.id),
                    _attr("pix:object_type", obj.type),
                    history,
                ),
            )
        )
    projected = CaseLog(
        tuple(traces),
        attributes=(
            _attr("pix:ocel_digest", canonical_digest(log).identifier),
            _attr("pix:projection_order", "timestamp/" + spec.tie_policy),
        ),
    )
    return ObjectCaseProjection(
        log,
        spec,
        projected,
        tuple(lineage),
        tuple(sorted(set(events) - used)),
        tuple(ties),
    )


__all__ = ["ObjectCaseProjectionSpec", "ObjectCaseProjection", "project_object_cases"]
