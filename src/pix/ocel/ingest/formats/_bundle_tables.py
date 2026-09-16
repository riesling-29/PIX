"""Strict metadata-typed CSV and optional Parquet table decoding."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

from pix.ocel.ingest.contract import ImportStage, ImportStatus
from pix.ocel.ingest.formats.common import (
    AdapterFailure,
    _map_time,
    _MappingContext,
    mapping_failure,
    schema_failure,
    syntax_failure,
)
from pix.ocel.model import OCEL_EPOCH, Value

_INTEGER = re.compile(r"[+-]?[0-9]+")
_FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_TIME = re.compile(
    r"(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{8})[Tt]"
    r"(?P<clock>[0-9]{2}:[0-9]{2}(?::[0-9]{2})?|[0-9]{4}(?:[0-9]{2})?)"
    r"(?P<fraction>[.,][0-9]+)?(?:Z|[+-][0-9]{2}(?::?[0-9]{2})?)"
)


def _csv_records(text: str, name: str) -> Iterator[list[str]]:
    """Read RFC 4180 without process-global csv.field_size_limit state."""
    state = "start"
    index = 0
    start = 0
    row: list[str] = []

    def field(end: int) -> str:
        raw = text[start:end]
        return raw[1:-1].replace('""', '"') if raw.startswith('"') else raw

    while index < len(text):
        char = text[index]
        if state == "quoted":
            if char == '"':
                state = "closed"
        elif state == "closed" and char == '"':
            state = "quoted"
        elif char in "\r\n":
            row.append(field(index))
            yield row
            row = []
            if char == "\r":
                if index + 1 >= len(text) or text[index + 1] != "\n":
                    raise syntax_failure(
                        "invalid_bundle_csv", "Use LF or CRLF rows.", (name,)
                    )
                index += 1
            state = "start"
            start = index + 1
        elif char == ",":
            row.append(field(index))
            state = "start"
            start = index + 1
        elif char == '"' and state == "start":
            state = "quoted"
        elif char == '"' or state == "closed":
            raise syntax_failure("invalid_bundle_csv", "Invalid CSV quoting.", (name,))
        else:
            state = "plain"
        index += 1
    if state == "quoted":
        raise syntax_failure("invalid_bundle_csv", "Unterminated CSV quote.", (name,))
    if start < len(text) or row:
        row.append(field(len(text)))
        yield row


def _columns(names: list[str], expected: dict[str, str], name: str) -> None:
    if len(names) != len(set(names)):
        raise schema_failure(
            "duplicate_bundle_column",
            "Table has repeated column names.",
            (name,),
        )
    if set(names) != set(expected):
        raise schema_failure(
            "invalid_bundle_columns",
            f"Columns differ from metadata: missing={sorted(set(expected) - set(names))}, "
            f"unexpected={sorted(set(names) - set(expected))}.",
            (name,),
        )


def _csv_value(
    value: str, kind: str, at: tuple[str, ...], context: _MappingContext
) -> Value:
    if kind == "string":
        return value
    if kind == "time":
        match = _TIME.fullmatch(value)
        if match is None:
            raise mapping_failure(
                "invalid_bundle_timestamp",
                "Expected an ISO 8601 timestamp with timezone.",
                at,
            )
        if match["fraction"] and len(match["clock"].replace(":", "")) != 6:
            raise mapping_failure(
                "invalid_bundle_timestamp",
                "Fractional timestamps require explicit seconds to avoid fractional-minute ambiguity.",
                at,
            )
        return _map_time(value, at, context)
    if kind == "integer" and _INTEGER.fullmatch(value):
        try:
            return int(value)
        except ValueError as exc:
            raise mapping_failure(
                "integer_out_of_range", "Integer conversion limit exceeded.", at
            ) from exc
    if kind == "float" and _FLOAT.fullmatch(value):
        number = float(value)
        if math.isfinite(number):
            return number
    if kind == "boolean" and value in {"true", "false"}:
        return value == "true"
    raise mapping_failure(
        "invalid_bundle_value",
        f"Value does not match declared {kind} encoding.",
        at,
    )


def csv_rows(
    data: bytes,
    *,
    name: str,
    columns: dict[str, str],
    attributes: set[str],
    context: _MappingContext,
) -> tuple[list[dict[str, Any]], int]:
    try:
        text = data.decode("utf-8")
        rows = _csv_records(text, name)
        header = next(rows, [])
        _columns(header, columns, name)
        result = []
        missing = 0
        for index, row in enumerate(rows, 2):
            at = (name, str(index))
            if len(row) != len(header):
                raise schema_failure(
                    "invalid_bundle_row_width", "CSV row width differs from header.", at
                )
            record = {}
            for column, value in zip(header, row):
                if column in attributes and value == "":
                    record[column] = None
                    missing += 1
                else:
                    record[column] = _csv_value(
                        value, columns[column], at + (column,), context
                    )
            result.append(record)
        return result, missing
    except UnicodeDecodeError as exc:
        raise syntax_failure(
            "invalid_bundle_utf8", "CSV must be UTF-8.", (name,)
        ) from exc


def parquet_modules() -> tuple[Any, Any]:
    """Import optional native dependencies only for declared Parquet bundles."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise AdapterFailure(
            status=ImportStatus.UNSUPPORTED,
            stage=ImportStage.SOURCE,
            code="dependency_unavailable",
            message="Parquet bundles require the optional dependency: install pix[parquet].",
        ) from exc
    return pa, pq


def parquet_rows(
    data: bytes,
    *,
    name: str,
    columns: dict[str, str],
    attributes: set[str],
) -> list[dict[str, Any]]:
    pa, pq = parquet_modules()
    try:
        # ParquetFile reads exactly this buffer, without dataset/path discovery.
        parquet = pq.ParquetFile(pa.BufferReader(data))
        schema = parquet.schema_arrow
        _columns(schema.names, columns, name)
        for field in schema:
            kind = columns[field.name]
            primitive = {
                "string": pa.string(),
                "integer": pa.int64(),
                "float": pa.float64(),
                "boolean": pa.bool_(),
            }
            if kind == "time":
                matches = (
                    pa.types.is_timestamp(field.type)
                    and field.type.unit == "us"
                    and field.type.tz is not None
                )
            elif kind == "string":
                arrow_type = field.type
                if pa.types.is_dictionary(arrow_type):
                    arrow_type = arrow_type.value_type
                matches = pa.types.is_string(arrow_type) or pa.types.is_large_string(
                    arrow_type
                )
            else:
                matches = field.type == primitive[kind]
            if not matches or field.nullable != (field.name in attributes):
                raise schema_failure(
                    "invalid_bundle_parquet_schema",
                    f"Column '{field.name}' has incompatible type or nullability.",
                    (name, field.name),
                )
            physical = parquet.schema.column(schema.get_field_index(field.name))
            expected_physical = {
                "string": "BYTE_ARRAY",
                "integer": "INT64",
                "float": "DOUBLE",
                "boolean": "BOOLEAN",
                "time": "INT64",
            }[kind]
            if physical.physical_type != expected_physical:
                raise schema_failure(
                    "invalid_bundle_parquet_schema",
                    "Wrong Parquet physical type.",
                    (name, field.name),
                )
            logical = json.loads(physical.logical_type.to_json())
            if kind == "time" and (
                logical.get("Type") != "Timestamp"
                or logical.get("isAdjustedToUTC") is not True
                or logical.get("timeUnit") != "microseconds"
            ):
                raise schema_failure(
                    "invalid_bundle_parquet_schema",
                    "Timestamp must be UTC-adjusted MICROS.",
                    (name, field.name),
                )
            if kind == "string" and logical.get("Type") != "String":
                raise schema_failure(
                    "invalid_bundle_parquet_schema",
                    "Strings require the UTF-8 logical type.",
                    (name, field.name),
                )
        table = parquet.read(use_threads=False)
        # Use integer epoch micros to avoid a tzdata/pytz dependency on Windows.
        # No float conversion and no Arrow/pandas nanosecond truncation occur.
        time_columns = [column for column, kind in columns.items() if kind == "time"]
        for column in time_columns:
            index = table.schema.get_field_index(column)
            table = table.set_column(index, column, table[column].cast(pa.int64()))
        result = table.to_pylist()
        for index, record in enumerate(result, 1):
            for column in time_columns:
                if record[column] is not None:
                    try:
                        record[column] = OCEL_EPOCH + timedelta(
                            microseconds=record[column]
                        )
                    except OverflowError as exc:
                        raise mapping_failure(
                            "timestamp_out_of_range",
                            "Timestamp outside canonical datetime range.",
                            (name, str(index), column),
                        ) from exc
            for column, value in record.items():
                at = (name, str(index), column)
                if value is None:
                    if column not in attributes:
                        raise mapping_failure(
                            "null_bundle_fixed_value",
                            "Fixed columns cannot be null.",
                            at,
                        )
                elif isinstance(value, float) and not math.isfinite(value):
                    raise mapping_failure(
                        "invalid_bundle_value", "Float must be finite.", at
                    )
                elif isinstance(value, datetime) and (
                    value.tzinfo is None or value.utcoffset() is None
                ):
                    raise mapping_failure(
                        "invalid_bundle_timestamp", "Timestamp timezone required.", at
                    )
        return result
    except AdapterFailure:
        raise
    except (pa.ArrowException, OSError, ValueError, OverflowError) as exc:
        raise syntax_failure(
            "invalid_bundle_parquet", f"Unreadable Parquet table: {exc}.", (name,)
        ) from exc
