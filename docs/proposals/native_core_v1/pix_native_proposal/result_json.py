"""Versioned analytical result output, separate from OCEL log serialization."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from math import isfinite

from .compute import (
    DFG_OPERATOR_ID,
    TRACE_OPERATOR_ID,
    ComputationResult,
    ComputeStatus,
    DirectlyFollowsGraph,
    TraceSet,
)

RESULT_FORMAT = "pix.analysis-result"
RESULT_VERSION = "0.1.0-proposal.1"


def _encode(value: object) -> object:
    if isinstance(value, Enum):
        return _encode(value.value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("non-finite result values are not supported")
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("result timestamps must be timezone-aware")
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if isinstance(value, tuple):
        return [_encode(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _encode(getattr(value, field.name)) for field in fields(value)}
    raise TypeError(f"unsupported analytical value: {type(value).__name__}")


def result_document(result: ComputationResult) -> dict[str, object]:
    """Build the proposed wire document for the two implemented result kinds.

    This is an output format proposal, not an OCEL 2.0 document or a general
    object serializer. Loading persisted models/results is not implemented here.
    Adding new operator payloads requires an explicit schema/version decision.
    """
    if not isinstance(result, ComputationResult):
        raise TypeError("result must be ComputationResult")
    payload_types = {
        TRACE_OPERATOR_ID: ("object-traces", TraceSet),
        DFG_OPERATOR_ID: ("object-dfg", DirectlyFollowsGraph),
    }
    if result.operator_id not in payload_types:
        raise ValueError("unsupported operator result schema")
    payload_kind, payload_type = payload_types[result.operator_id]
    if result.status is ComputeStatus.COMPUTED:
        if not isinstance(result.value, payload_type):
            raise TypeError("computed payload does not match the operator schema")
    elif result.value is not None:
        raise ValueError("non-computed result must not contain a success payload")

    return {
        "format": RESULT_FORMAT,
        "version": RESULT_VERSION,
        "payload_kind": payload_kind,
        "computation": _encode(result),
    }


def result_json_bytes(result: ComputationResult) -> bytes:
    """Serialize deterministic UTF-8 JSON; this is not a canonical OCEL digest."""
    return json.dumps(
        result_document(result),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
