"""Deliberate primitive conversions shared by both table mapping targets."""

from __future__ import annotations

import math
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import mapping_failure
from pix.tabular.mapping import AttributeColumn

OMIT = object()
_TIME = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.(\d+))?(?:Z|[+-](\d{2}):(\d{2}))?\Z"
)


@dataclass
class ConversionContext:
    timestamp_policy: str
    counts: dict[str, int] = field(default_factory=dict)

    def count(self, code: str) -> None:
        self.counts[code] = self.counts.get(code, 0) + 1

    def transformations(self) -> tuple[Transformation, ...]:
        messages = {
            "integer_identifier": "Converted numeric identifiers to decimal text by explicit integer ID policy.",
            "timezone_assumed_utc": "Assumed UTC for timezone-free values by explicit timestamp policy.",
            "timezone_to_utc": "Normalized timezone-aware values to UTC without changing their instants.",
            "float_conversion": "Converted explicitly float-typed values to finite IEEE-754 binary64; decimal spelling is retained only in source evidence.",
            "attribute_null_omitted": "Omitted null attribute values by explicit column policy.",
            "attribute_missing_omitted": "Omitted missing attribute values by explicit column policy.",
        }
        return tuple(
            Transformation(code=code, message=messages[code], count=count)
            for code, count in sorted(self.counts.items())
        )


def cell(row: dict[str, object], column: str, at: tuple[str, ...]) -> object:
    if column not in row:
        raise mapping_failure(
            "missing_column", f"Missing required column {column!r}.", at + (column,)
        )
    return row[column]


def identifier(
    value: object, policy: str, context: ConversionContext, at: tuple[str, ...]
) -> str:
    if isinstance(value, str) and value.strip():
        return str.__str__(value)
    if policy == "integer" and not isinstance(value, bool):
        if isinstance(value, int):
            result = _integer_text(value, at)
            context.count("integer_identifier")
            return result
        if (
            isinstance(value, Decimal)
            and value.is_finite()
            and value == value.to_integral_value()
        ):
            result = _integer_text(_integer(value, at), at)
            context.count("integer_identifier")
            return result
        if (
            isinstance(value, float)
            and math.isfinite(value)
            and value.is_integer()
            and abs(value) <= 2**53
        ):
            context.count("integer_identifier")
            return str(int(value))
    raise mapping_failure(
        "invalid_identifier",
        "Identifiers must be nonblank text; numeric IDs require explicit integer policy and exact representability.",
        at,
    )


def _integer(value: object, at: tuple[str, ...]) -> int:
    # Avoid expanding a compact Decimal exponent beyond Python's configured
    # integer text limit; parsing strings observes the same interpreter limit.
    limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
    if isinstance(value, Decimal) and limit and value.adjusted() >= limit:
        raise mapping_failure(
            "integer_representation_limit",
            "Integer exceeds the interpreter's configured decimal digit limit.",
            at,
        )
    try:
        return int.__int__(value) if isinstance(value, int) else int(value)
    except (ValueError, OverflowError) as exc:
        raise mapping_failure("integer_representation_limit", str(exc), at) from exc


def _integer_text(value: int, at: tuple[str, ...]) -> str:
    try:
        return str(int.__int__(value))
    except ValueError as exc:
        raise mapping_failure("integer_representation_limit", str(exc), at) from exc


def text_value(value: object, at: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise mapping_failure("invalid_text", "Activity must be nonblank text.", at)
    return str.__str__(value)


def timestamp(
    value: object, context: ConversionContext, at: tuple[str, ...]
) -> datetime:
    if isinstance(value, str):
        match = _TIME.fullmatch(value)
        if match is None:
            raise mapping_failure(
                "invalid_timestamp",
                "Timestamp must be an ISO datetime with seconds.",
                at,
            )
        fraction = match.group(1)
        if match.group(2) is not None and (
            int(match.group(2)) > 23 or int(match.group(3)) > 59
        ):
            raise mapping_failure(
                "invalid_timestamp", "Timestamp UTC offset is outside ISO bounds.", at
            )
        if fraction and len(fraction) > 6 and any(char != "0" for char in fraction[6:]):
            raise mapping_failure(
                "timestamp_precision_loss",
                "Timestamp precision exceeds Python microseconds; no truncation was applied.",
                at,
            )
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise mapping_failure("invalid_timestamp", str(exc), at) from exc
    if not isinstance(value, datetime):
        raise mapping_failure(
            "invalid_timestamp",
            "Timestamp must be an ISO datetime or datetime value.",
            at,
        )
    if type(value) is not datetime:
        raise mapping_failure(
            "unsupported_datetime_type",
            "Datetime subclasses may carry additional precision; provide an exact ISO timestamp or a native datetime after explicit conversion.",
            at,
        )
    if value.tzinfo is None or value.utcoffset() is None:
        if context.timestamp_policy != "assume_utc":
            raise mapping_failure(
                "timezone_required",
                "Timestamp has no timezone; supply one or explicitly select assume_utc.",
                at,
            )
        context.count("timezone_assumed_utc")
        value = value.replace(tzinfo=timezone.utc)
    elif value.utcoffset().total_seconds() != 0:
        context.count("timezone_to_utc")
    try:
        return value.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise mapping_failure(
            "timestamp_overflow",
            "UTC timestamp is outside the supported datetime range.",
            at,
        ) from exc


def attribute_value(
    row: dict[str, object],
    mapping: AttributeColumn,
    context: ConversionContext,
    at: tuple[str, ...],
) -> object:
    at = at + (mapping.column,)
    if mapping.column not in row:
        if mapping.missing == "omit":
            context.count("attribute_missing_omitted")
            return OMIT
        raise mapping_failure(
            "missing_column", f"Missing attribute column {mapping.column!r}.", at
        )
    value = row[mapping.column]
    if value is None or (isinstance(value, str) and value in mapping.null_values):
        if mapping.null == "omit":
            context.count("attribute_null_omitted")
            return OMIT
        if mapping.null == "preserve":
            return None
        raise mapping_failure(
            "null_attribute", "Null attribute requires an explicit null policy.", at
        )
    kind = mapping.type
    if kind == "string" and isinstance(value, str):
        return str.__str__(value)
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if value == "true":
            return True
        if value == "false":
            return False
    if kind == "integer" and not isinstance(value, bool):
        if isinstance(value, int):
            return _integer(value, at)
        if isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value):
            return _integer(value, at)
        if (
            isinstance(value, Decimal)
            and value.is_finite()
            and value == value.to_integral_value()
        ):
            return _integer(value, at)
        if (
            isinstance(value, float)
            and math.isfinite(value)
            and value.is_integer()
            and abs(value) <= 2**53
        ):
            return int(value)
    if (
        kind == "float"
        and isinstance(value, (str, int, float, Decimal))
        and not isinstance(value, bool)
    ):
        try:
            converted = float(value)
        except (ValueError, OverflowError, InvalidOperation):
            converted = math.nan
        if math.isfinite(converted):
            if not isinstance(value, float):
                context.count("float_conversion")
            return converted
    if kind == "time":
        return timestamp(value, context, at)
    raise mapping_failure(
        "invalid_attribute_value", f"Value does not match declared {kind!r} type.", at
    )
