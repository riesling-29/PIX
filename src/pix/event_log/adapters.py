"""Explicit case-log projections, with source facts and mapping retained.

``case_traces`` uses file/row sequence as its ordering evidence. It never sorts
by time and does not require event times for discovery/replay. ``to_ocel`` is
stricter: all event times must have timezones and event/trace attributes must
be primitive. The conversion result keeps the complete native source alongside
the projected OCEL, including metadata which OCEL has no native place to store.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from hashlib import sha256
from math import isfinite

from pix.compute._common import _result
from pix.contracts.analysis import E2OEvidence, ObjectTrace, TraceEvent, TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, _text, find_attribute
from pix.ocel.build import build
from pix.ocel.ingest.contract import ImportIssue, ImportStage, Transformation
from pix.ocel.model import (
    E2O,
    OCEL,
    OCEL_EPOCH,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)


def _facts(value: object) -> object:
    if isinstance(value, datetime):
        return ["date", value.isoformat(timespec="microseconds")]
    if isinstance(value, float):
        return ["float", value.hex()]
    if is_dataclass(value):
        return [
            type(value).__name__,
            [
                [field.name, _facts(getattr(value, field.name))]
                for field in fields(value)
                if not (isinstance(value, CaseLog) and field.name == "source")
            ],
        ]
    if isinstance(value, tuple):
        return [_facts(item) for item in value]
    return value


def case_log_digest(log: CaseLog) -> str:
    """Versioned ordered native-facts identity, excluding source filesystem path."""
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    data = json.dumps(
        _facts(log), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return "pix.case-log.v1:sha256:" + sha256(data).hexdigest()


def _activity(log: CaseLog, event: CaseEvent, spec: CaseTraceSpec) -> str:
    keys = (spec.activity_key,)
    if spec.classifier is not None:
        classifiers = tuple(
            c
            for c in log.classifiers
            if c.name == spec.classifier and c.scope == "event"
        )
        if len(classifiers) != 1:
            raise ValueError(
                "classifier must select exactly one declared event classifier"
            )
        keys = classifiers[0].keys
    values: list[object] = []
    for key in keys:
        attribute = log.attribute(event, key)
        if attribute is None or attribute.type not in (
            "string",
            "id",
            "int",
            "float",
            "boolean",
            "date",
        ):
            raise ValueError(
                f"event {event.id!r} lacks primitive classifier/activity attribute {key!r}"
            )
        if isinstance(attribute.value, float) and not isfinite(attribute.value):
            raise ValueError("nonfinite classifier value")
        if spec.classifier is None:
            if attribute.type != "string" or not attribute.value.strip():
                raise ValueError("activity must be a nonblank string")
            return attribute.value
        values.append([attribute.type, _facts(attribute.value)])
    # A type-tagged tuple cannot conflate ('a+b','c') and ('a','b+c').
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def case_traces(
    log: CaseLog, spec: CaseTraceSpec = CaseTraceSpec()
) -> ComputationResult[TraceSet]:
    """Project selected primitive values in source order for discovery/replay.

    Nested metadata on the selected primitive is retained in the native source;
    it is not part of its scalar classifier value. No timestamps are invented.
    """
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if not isinstance(spec, CaseTraceSpec):
        raise TypeError("spec must be CaseTraceSpec")
    digest = case_log_digest(log)
    issues = [
        ComputeIssue(
            "source_sequence",
            "Trace/event order is the source sequence; it is not a claim of timestamp or causal order",
        )
    ]
    traces: list[ObjectTrace] = []
    try:
        if (
            spec.classifier is not None
            and len(
                tuple(
                    c
                    for c in log.classifiers
                    if c.name == spec.classifier and c.scope == "event"
                )
            )
            != 1
        ):
            raise ValueError(
                "classifier must select exactly one declared event classifier"
            )
        for trace in log.traces:
            events: list[TraceEvent] = []
            for event in trace.events:
                activity = _activity(log, event, spec)
                attribute = log.attribute(event, spec.timestamp_key)
                time = (
                    attribute.value
                    if attribute is not None and attribute.type == "date"
                    else None
                )
                if time is not None and time.utcoffset() is None:
                    time = None
                if time is None:
                    issues.append(
                        ComputeIssue(
                            "unknown_timestamp",
                            "No timezone-aware timestamp is available; source facts remain in CaseLog",
                            ("trace", trace.id, "event", event.id),
                        )
                    )
                events.append(
                    TraceEvent(
                        event.id,
                        activity,
                        time,
                        (E2OEvidence(event.id, trace.id, "case"),),
                    )
                )
            traces.append(ObjectTrace(trace.id, spec.object_type, tuple(events)))
    except ValueError as exc:
        return _result(
            "pix.case_traces",
            None,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (ComputeIssue("case_mapping_unavailable", str(exc)),),
            source_digest=digest,
        )
    return _result(
        "pix.case_traces",
        None,
        spec,
        ComputeStatus.COMPUTED,
        TraceSet(spec.object_type, tuple(traces)),
        tuple(issues),
        source_digest=digest,
    )


@dataclass(frozen=True, slots=True)
class CaseOCELMapping:
    case_object_type: str = "case"
    activity_key: str = "concept:name"
    timestamp_key: str = "time:timestamp"
    qualifier: str = "case"

    def __post_init__(self) -> None:
        for field in ("case_object_type", "activity_key", "timestamp_key"):
            _text(getattr(self, field), field)
        _text(self.qualifier, "qualifier", blank=True)


@dataclass(frozen=True, slots=True)
class CaseOCELConversion:
    """The full native source is the provenance sidecar of the OCEL projection."""

    source_log: CaseLog
    source_digest: str
    mapping: CaseOCELMapping
    candidate: OCEL | None
    issues: tuple[ImportIssue, ...] = ()
    transformations: tuple[Transformation, ...] = ()

    @property
    def valid(self) -> bool:
        return self.candidate is not None and not self.issues

    @property
    def ocel(self) -> OCEL | None:
        return self.candidate if self.valid else None

    def require_ocel(self) -> OCEL:
        if self.ocel is None:
            raise CaseConversionError(self)
        return self.ocel


class CaseConversionError(ValueError):
    def __init__(self, result: CaseOCELConversion) -> None:
        self.result = result
        super().__init__(
            "CaseLog cannot be represented by the requested primitive OCEL mapping"
        )


_OCEL_TYPES = {
    "string": ValueType.STRING,
    "id": ValueType.STRING,
    "int": ValueType.INTEGER,
    "date": ValueType.TIME,
    "float": ValueType.FLOAT,
    "boolean": ValueType.BOOLEAN,
}


def _primitive(attribute: CaseAttribute) -> Attribute:
    if attribute.type not in _OCEL_TYPES or attribute.children or attribute.values:
        raise ValueError(
            f"attribute {attribute.key!r} ({attribute.type}) cannot be flattened into OCEL"
        )
    if isinstance(attribute.value, datetime) and attribute.value.utcoffset() is None:
        raise ValueError(f"attribute {attribute.key!r} has no timezone")
    if isinstance(attribute.value, float) and not isfinite(attribute.value):
        raise ValueError(f"attribute {attribute.key!r} is nonfinite")
    return Attribute(attribute.key, _OCEL_TYPES[attribute.type])


def to_ocel(
    log: CaseLog, mapping: CaseOCELMapping = CaseOCELMapping()
) -> CaseOCELConversion:
    """Explicitly map each trace to one case object; fail instead of dropping facts.

    Source trace attributes become initial object values at OCEL time zero.
    This is OCEL's initial-value convention, not an observed event timestamp.
    XES ID values map to OCEL string; original types and lexical forms, globals,
    classifiers, log metadata and order remain in ``result.source_log``.
    """
    if not isinstance(log, CaseLog) or not isinstance(mapping, CaseOCELMapping):
        raise TypeError("to_ocel requires CaseLog and CaseOCELMapping")
    digest = case_log_digest(log)
    schemas: dict[str, dict[str, Attribute]] = {}
    object_schema: dict[str, Attribute] = {}
    events: list[Event] = []
    objects: list[Object] = []
    relations: list[E2O] = []
    at: tuple[str, ...] = ()

    def register(
        schema: dict[str, Attribute], attributes: tuple[CaseAttribute, ...]
    ) -> None:
        for attribute in attributes:
            declaration = _primitive(attribute)
            if attribute.key in schema and schema[attribute.key] != declaration:
                raise ValueError(f"conflicting types for attribute {attribute.key!r}")
            schema[attribute.key] = declaration

    try:
        for trace in log.traces:
            at = ("trace", trace.id)
            attributes = log.effective_attributes(trace)
            register(object_schema, attributes)
            objects.append(
                Object(
                    trace.id,
                    mapping.case_object_type,
                    tuple(ObjectAttr(a.key, a.value, OCEL_EPOCH) for a in attributes),
                )
            )
            for event in trace.events:
                at = ("trace", trace.id, "event", event.id)
                attributes = log.effective_attributes(event)
                activity = find_attribute(attributes, mapping.activity_key)
                time = find_attribute(attributes, mapping.timestamp_key)
                if (
                    activity is None
                    or activity.type != "string"
                    or not activity.value.strip()
                ):
                    raise ValueError("event requires a nonblank string activity")
                if (
                    time is None
                    or time.type != "date"
                    or time.value.utcoffset() is None
                ):
                    raise ValueError(
                        "event requires a timezone-aware timestamp; time will not be fabricated"
                    )
                register(schemas.setdefault(activity.value, {}), attributes)
                events.append(
                    Event(
                        event.id,
                        activity.value,
                        time.value,
                        tuple(EventAttr(a.key, a.value) for a in attributes),
                    )
                )
                relations.append(E2O(event.id, trace.id, mapping.qualifier))
        built = build(
            event_types=tuple(
                EventType(k, tuple(v.values())) for k, v in schemas.items()
            ),
            object_types=(
                ObjectType(mapping.case_object_type, tuple(object_schema.values())),
            ),
            events=events,
            objects=objects,
            e2o=relations,
        )
        if not built.valid:
            raise ValueError(
                "Projected OCEL failed semantic validation: "
                + "; ".join(i.message for i in built.report.errors)
            )
    except (TypeError, ValueError) as exc:
        return CaseOCELConversion(
            log,
            digest,
            mapping,
            None,
            (
                ImportIssue(
                    ImportStage.MAPPING, "case_to_ocel_unrepresentable", str(exc), at=at
                ),
            ),
        )
    transformations = (
        Transformation(
            "case_objects",
            "Every trace becomes one case object, including empty traces",
            count=len(objects),
        ),
        Transformation(
            "initial_object_attributes",
            "Trace attributes use OCEL time zero as initial values; no event timestamps are invented",
        ),
        Transformation(
            "native_provenance_sidecar",
            "Original hierarchy, log metadata, global defaults, classifiers, lexical forms and source sequence remain in source_log",
        ),
        Transformation(
            "id_as_string",
            "Primitive XES id attributes become OCEL string attributes; source types remain in source_log",
        ),
    )
    return CaseOCELConversion(
        log, digest, mapping, built.ocel, transformations=transformations
    )
