"""Evidence-preserving conversion of explicitly mapped tables."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

from pix.event_log.contract import CaseImportResult
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseSource, CaseTrace
from pix.ocel.build import build
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.contract import (
    ImportFormat,
    ImportIssue,
    ImportResult,
    ImportStatus,
    Transformation,
)
from pix.ocel.ingest.formats.common import AdapterFailure, mapping_failure
from pix.ocel.metadata import OCELImportInfo, OCELWarning, TimezoneInfo
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
from pix.tabular.mapping import (
    AttributeColumn,
    CaseTableMapping,
    ObjectColumn,
    OCELTableMapping,
)
from pix.tabular.source import TableData, TableSourceError, load_table
from pix.tabular.values import (
    OMIT,
    ConversionContext,
    attribute_value,
    cell,
    identifier,
    text_value,
    timestamp,
)

_FORMATS = {
    "csv": ImportFormat.TABLE_CSV,
    "tsv": ImportFormat.TABLE_TSV,
    "xlsx": ImportFormat.TABLE_XLSX,
    "records": ImportFormat.TABLE_RECORDS,
}


def import_table(
    source: object,
    mapping: CaseTableMapping | OCELTableMapping,
    *,
    format: str | None = None,
    sheet: str | int | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> CaseImportResult | ImportResult:
    """Import CSV/TSV/gzip, optional XLSX, or iterable mapping records.

    Mapping errors produce an evidence-carrying result. Invalid mapping object
    construction and invalid API argument types raise directly. Read-only
    database query results can be passed as iterable dictionaries; PIX neither
    connects to databases nor executes SQL through this entry point.
    """
    if not isinstance(mapping, (CaseTableMapping, OCELTableMapping)):
        raise TypeError("mapping must be CaseTableMapping or OCELTableMapping")
    disclosure = Transformation(
        code="table_mapping",
        message=f"Applied explicit {type(mapping).__name__} v1; mapping SHA-256 {mapping.fingerprint}.",
    )
    try:
        table = load_table(
            source, format=format, sheet=sheet, delimiter=delimiter, encoding=encoding
        )
    except TableSourceError as exc:
        return _failure(
            mapping,
            source=exc.source,
            kind=exc.kind,
            status=exc.status,
            issue=ImportIssue(exc.stage, exc.code, str(exc), at=exc.at),
            sha256=exc.sha256,
            size=exc.size,
            transformations=(disclosure,),
        )
    transformations = [*table.transformations, disclosure]
    context = ConversionContext(mapping.timestamp_policy)
    try:
        _validate_headers(table, mapping, transformations)
        if isinstance(mapping, CaseTableMapping):
            candidate = _case_log(table, mapping, context, transformations)
            return CaseImportResult(
                source=table.source,
                format=f"table-{table.kind}",
                status=ImportStatus.VALID,
                candidate=candidate,
                transformations=tuple(transformations) + context.transformations(),
                source_sha256=table.sha256,
                source_size=table.size,
            )
        result = _ocel(table, mapping, context, transformations)
    except AdapterFailure as exc:
        return _failure(
            mapping,
            source=table.source,
            kind=table.kind,
            status=exc.status,
            issue=ImportIssue(exc.stage, exc.code, str(exc), at=exc.at),
            sha256=table.sha256,
            size=table.size,
            transformations=tuple(transformations) + context.transformations(),
        )
    return result


def read_table(
    source: object,
    mapping: CaseTableMapping | OCELTableMapping,
    *,
    format: str | None = None,
    sheet: str | int | None = None,
    delimiter: str = ",",
    encoding: str = "utf-8",
) -> CaseLog | OCEL:
    """Return a valid native case log or OCEL; failures carry import evidence."""
    result = import_table(
        source,
        mapping,
        format=format,
        sheet=sheet,
        delimiter=delimiter,
        encoding=encoding,
    )
    if isinstance(result, CaseImportResult):
        return result.require_case_log()
    return result.require_ocel()


def _failure(
    mapping: CaseTableMapping | OCELTableMapping,
    *,
    source: str,
    kind: str | None,
    status: ImportStatus,
    issue: ImportIssue,
    sha256: str | None,
    size: int | None,
    transformations: tuple[Transformation, ...],
) -> CaseImportResult | ImportResult:
    arguments = dict(
        source=source,
        status=status,
        candidate=None,
        import_issues=(issue,),
        source_sha256=sha256,
        source_size=size,
        transformations=transformations,
    )
    if isinstance(mapping, CaseTableMapping):
        return CaseImportResult(format=f"table-{kind or 'unknown'}", **arguments)
    return ImportResult(format=_FORMATS.get(kind), **arguments)


def _columns(mapping: CaseTableMapping | OCELTableMapping) -> tuple[set[str], set[str]]:
    required = {mapping.activity}
    used = set(required)
    if mapping.timestamp is not None:
        required.add(mapping.timestamp)
    if mapping.event_id is not None:
        required.add(mapping.event_id)
    attrs = list(mapping.event_attributes)
    if isinstance(mapping, CaseTableMapping):
        required.add(mapping.case_id)
        attrs.extend(mapping.case_attributes)
    else:
        for obj in mapping.objects:
            required.add(obj.column)
            attrs.extend(obj.attributes)
    used.update(required)
    for attr in attrs:
        used.add(attr.column)
        if attr.missing == "error":
            required.add(attr.column)
    return required, used


def _validate_headers(
    table: TableData,
    mapping: CaseTableMapping | OCELTableMapping,
    transformations: list[Transformation],
) -> None:
    required, used = _columns(mapping)
    # An empty record iterator has no schema to check and describes an empty log.
    missing = (
        required - set(table.fields)
        if table.fields or table.kind != "records"
        else set()
    )
    if missing:
        raise mapping_failure(
            "missing_column", f"Mapped columns absent from source: {sorted(missing)!r}."
        )
    ignored = set(table.fields) - used
    if ignored:
        transformations.append(
            Transformation(
                code="unmapped_columns",
                message=f"Columns not selected by the explicit mapping: {sorted(ignored)!r}.",
                count=len(ignored),
            )
        )


def _case_attributes(
    row: dict[str, object],
    mappings: tuple[AttributeColumn, ...],
    context: ConversionContext,
    at: tuple[str, ...],
) -> tuple[CaseAttribute, ...]:
    result = []
    aliases = {"integer": "int", "time": "date"}
    for mapping in mappings:
        value = attribute_value(row, mapping, context, at)
        if value is OMIT:
            continue
        kind = "null" if value is None else aliases.get(mapping.type, mapping.type)
        raw = row[mapping.column]
        result.append(
            CaseAttribute(
                key=mapping.key,
                type=kind,
                value=value,
                lexical=raw if isinstance(raw, str) else None,
            )
        )
    return tuple(result)


def _case_log(
    table: TableData,
    mapping: CaseTableMapping,
    context: ConversionContext,
    transformations: list[Transformation],
) -> CaseLog:
    traces: dict[str, list[CaseEvent]] = {}
    trace_attrs: dict[str, tuple[CaseAttribute, ...]] = {}
    event_ids: set[str] = set()
    for index, row in enumerate(table.rows):
        at = ("rows", str(index))
        case_id = identifier(
            cell(row, mapping.case_id, at),
            mapping.id_policy,
            context,
            at + (mapping.case_id,),
        )
        activity = text_value(cell(row, mapping.activity, at), at + (mapping.activity,))
        event_id = (
            identifier(
                cell(row, mapping.event_id, at),
                mapping.id_policy,
                context,
                at + (mapping.event_id,),
            )
            if mapping.event_id is not None
            else f"row:{index + 1}"
        )
        if event_id in event_ids:
            raise mapping_failure(
                "duplicate_event_id", f"Duplicate case event ID {event_id!r}.", at
            )
        event_ids.add(event_id)
        attrs = _case_attributes(row, mapping.case_attributes, context, at)
        if case_id in trace_attrs and _case_facts(trace_attrs[case_id]) != _case_facts(
            attrs
        ):
            raise mapping_failure(
                "conflicting_case_attributes",
                f"Repeated case {case_id!r} has conflicting attributes (including missing/null facts).",
                at,
            )
        trace_attrs.setdefault(case_id, attrs)
        event_attrs = [CaseAttribute("concept:name", "string", activity)]
        if mapping.timestamp is not None:
            raw = cell(row, mapping.timestamp, at)
            time = timestamp(raw, context, at + (mapping.timestamp,))
            event_attrs.append(
                CaseAttribute(
                    "time:timestamp",
                    "date",
                    time,
                    lexical=raw if isinstance(raw, str) else None,
                )
            )
        if mapping.event_id is not None:
            event_attrs.append(CaseAttribute("identity:id", "string", event_id))
        event_attrs.extend(_case_attributes(row, mapping.event_attributes, context, at))
        traces.setdefault(case_id, []).append(CaseEvent(event_id, tuple(event_attrs)))
    if mapping.event_id is None:
        transformations.append(
            Transformation(
                code="positional_event_identity",
                message="Assigned internal row:<1-based data row> identities; these are not claimed source event IDs.",
                count=len(table.rows),
            )
        )
    if mapping.order == "timestamp":
        for events in traces.values():
            events.sort(
                key=lambda event: next(
                    attr.value
                    for attr in event.attributes
                    if attr.key == "time:timestamp"
                )
            )
        order_message = "Cases follow first source occurrence; events are stably sorted by timestamp, retaining source order on ties."
    else:
        order_message = "Cases follow first source occurrence; each case retains source event order, including noncontiguous source rows."
    transformations.append(
        Transformation(
            code="case_event_order", message=order_message, count=len(table.rows)
        )
    )
    return CaseLog(
        traces=tuple(
            CaseTrace(
                case_id,
                tuple(events),
                (
                    CaseAttribute("concept:name", "string", case_id),
                    *trace_attrs[case_id],
                ),
            )
            for case_id, events in traces.items()
        ),
        metadata=(
            ("table_mapping_sha256", mapping.fingerprint),
            ("table_source_kind", table.kind),
            ("table_event_order", mapping.order),
        ),
        source=CaseSource(
            table.source, f"table-{table.kind}", table.sha256, table.size
        ),
    )


def _case_facts(
    attributes: tuple[CaseAttribute, ...],
) -> tuple[tuple[str, str, object], ...]:
    # Original lexical spelling remains on the first assignment, but agreeing
    # typed values such as 1 and +1 do not manufacture a conflict.
    return tuple((attr.key, attr.type, attr.value) for attr in attributes)


def _object_ids(
    row: dict[str, object],
    mapping: ObjectColumn,
    context: ConversionContext,
    at: tuple[str, ...],
) -> tuple[str, ...]:
    raw = cell(row, mapping.column, at)
    at = at + (mapping.column,)
    if raw is None or (isinstance(raw, str) and raw in mapping.null_values):
        return ()
    if mapping.encoding == "scalar":
        values = (raw,)
    elif mapping.encoding == "separator":
        if not isinstance(raw, str):
            raise mapping_failure(
                "invalid_object_list", "Separator encoding requires a string cell.", at
            )
        values = raw.split(mapping.separator)
    else:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw, parse_float=Decimal)
            except (ValueError, RecursionError) as exc:
                raise mapping_failure(
                    "invalid_object_list", "Invalid JSON object-ID list.", at
                ) from exc
        if not isinstance(raw, (list, tuple)):
            raise mapping_failure(
                "invalid_object_list",
                "JSON object encoding requires an explicit list.",
                at,
            )
        values = raw
    return tuple(
        identifier(value, mapping.id_policy, context, at + (str(index),))
        for index, value in enumerate(values)
    )


def _ocel(
    table: TableData,
    mapping: OCELTableMapping,
    context: ConversionContext,
    transformations: list[Transformation],
) -> ImportResult:
    events: dict[str, Event] = {}
    object_types: dict[str, dict[str, Attribute]] = {}
    objects: dict[str, tuple[str, dict[str, ObjectAttr]]] = {}
    relations: dict[E2O, None] = {}
    grouped = deduplicated = 0
    for obj_mapping in mapping.objects:
        schema = object_types.setdefault(obj_mapping.object_type, {})
        schema.update(
            {
                attr.key: Attribute(attr.key, ValueType(attr.type))
                for attr in obj_mapping.attributes
            }
        )
    event_schema = tuple(
        Attribute(attr.key, ValueType(attr.type)) for attr in mapping.event_attributes
    )
    for index, row in enumerate(table.rows):
        at = ("rows", str(index))
        event_id = identifier(
            cell(row, mapping.event_id, at),
            mapping.id_policy,
            context,
            at + (mapping.event_id,),
        )
        activity = text_value(cell(row, mapping.activity, at), at + (mapping.activity,))
        time = timestamp(
            cell(row, mapping.timestamp, at), context, at + (mapping.timestamp,)
        )
        attributes = []
        for attr in mapping.event_attributes:
            value = attribute_value(row, attr, context, at)
            if value is not OMIT:
                attributes.append(EventAttr(attr.key, value))
        event = Event(event_id, activity, time, tuple(attributes))
        if event_id in events:
            if events[event_id] != event:
                raise mapping_failure(
                    "conflicting_event",
                    f"Repeated event {event_id!r} has conflicting facts.",
                    at,
                )
            grouped += 1
        else:
            events[event_id] = event
        for obj_mapping in mapping.objects:
            ids = _object_ids(row, obj_mapping, context, at)
            obj_attrs = []
            for attr in obj_mapping.attributes:
                value = attribute_value(row, attr, context, at)
                if value is not OMIT:
                    obj_attrs.append(ObjectAttr(attr.key, value, OCEL_EPOCH))
            if not ids and obj_attrs:
                raise mapping_failure(
                    "orphan_object_attributes",
                    "Object attributes have values but their mapped object ID cell is empty.",
                    at + (obj_mapping.column,),
                )
            for object_id in ids:
                if (
                    object_id in objects
                    and objects[object_id][0] != obj_mapping.object_type
                ):
                    raise mapping_failure(
                        "conflicting_object_type",
                        f"Global object ID {object_id!r} occurs with different types.",
                        at,
                    )
                _, facts = objects.setdefault(object_id, (obj_mapping.object_type, {}))
                for attr in obj_attrs:
                    if attr.name in facts and facts[attr.name] != attr:
                        raise mapping_failure(
                            "conflicting_object_attributes",
                            f"Object {object_id!r} has conflicting static attribute {attr.name!r}.",
                            at,
                        )
                    facts[attr.name] = attr
                relation = E2O(event_id, object_id, obj_mapping.qualifier)
                if relation in relations:
                    if mapping.duplicate_relations == "error":
                        raise mapping_failure(
                            "duplicate_e2o",
                            "Duplicate event/object/qualifier fact; choose explicit deduplicate policy to collapse it.",
                            at,
                        )
                    deduplicated += 1
                relations[relation] = None
    if grouped:
        transformations.append(
            Transformation(
                code="repeated_event_rows_grouped",
                message="Grouped repeated event rows only after verifying all mapped event facts agree.",
                count=grouped,
            )
        )
    if deduplicated:
        transformations.append(
            Transformation(
                code="duplicate_e2o_deduplicated",
                message="Removed repeated identical event/object/qualifier facts by explicit deduplicate policy.",
                count=deduplicated,
            )
        )
    if any(obj.attributes for obj in mapping.objects):
        transformations.append(
            Transformation(
                code="static_object_attributes",
                message="Mapped ObjectColumn.attributes as static initial values at the OCEL epoch; conflicting values are rejected.",
            )
        )
    result = build(
        event_types=tuple(
            EventType(name, event_schema)
            for name in dict.fromkeys(event.type for event in events.values())
        ),
        object_types=tuple(
            ObjectType(name, tuple(attrs.values()))
            for name, attrs in object_types.items()
        ),
        events=tuple(events.values()),
        objects=tuple(
            Object(object_id, kind, tuple(attrs.values()))
            for object_id, (kind, attrs) in objects.items()
        ),
        e2o=tuple(relations),
    )
    all_transformations = tuple(transformations) + context.transformations()
    warnings = tuple(
        OCELWarning(item.code, item.message, item.count or 0)
        for item in all_transformations
        if item.code == "timezone_assumed_utc"
    )
    timezone_info = TimezoneInfo(
        source_type="mapped table timestamps",
        normalized_offset_count=context.counts.get("timezone_to_utc", 0),
        assumed_utc_count=context.counts.get("timezone_assumed_utc", 0),
    )
    candidate = replace(
        result.candidate,
        import_info=OCELImportInfo(
            table.source, f"table-{table.kind}", table.sha256, timezone_info, warnings
        ),
    )
    return ImportResult(
        source=table.source,
        format=_FORMATS[table.kind],
        status=ImportStatus.VALID if result.valid else ImportStatus.SEMANTIC_INVALID,
        candidate=candidate,
        semantic_report=result.report,
        transformations=all_transformations,
        source_sha256=table.sha256,
        source_size=table.size,
        canonical_digest=canonical_digest(candidate) if result.valid else None,
    )


__all__ = ["import_table", "read_table"]
