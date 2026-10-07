"""Immutable, domain-neutral envelopes for native calculation results."""

from __future__ import annotations

import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from math import isfinite
from typing import Generic, TypeVar


class ComputeStatus(str, Enum):
    COMPUTED = "computed"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INVALID_INPUT = "invalid_input"


def _immutable(value: object) -> bool:
    if isinstance(value, Enum):
        return _immutable(value.value)
    if value is None or isinstance(value, (str, int, bool, datetime)):
        return True
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, tuple):
        return all(_immutable(item) for item in value)
    if is_dataclass(value) and not isinstance(value, type):
        return bool(value.__dataclass_params__.frozen) and all(
            _immutable(getattr(value, field.name)) for field in fields(value)
        )
    return False


@dataclass(frozen=True, slots=True)
class ComputeIssue:
    code: str
    message: str
    at: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code:
            raise ValueError("issue code must be nonempty text")
        if not isinstance(self.message, str):
            raise TypeError("issue message must be text")
        if not isinstance(self.at, tuple) or not all(
            isinstance(p, str) for p in self.at
        ):
            raise TypeError("issue path must be a tuple of strings")


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ComputationResult(Generic[T]):
    """A value and its request identity, or explicit unavailability evidence.

    Source identity covers canonical facts; request identity additionally covers
    operator, parameter contract, parameters, and all parent computations.
    """

    operator_id: str
    operator_version: str
    source_digest: str | None
    spec: object
    status: ComputeStatus
    value: T | None
    issues: tuple[ComputeIssue, ...]
    computation_id: str | None
    parent_computation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.operator_id, str) or not self.operator_id:
            raise ValueError("operator_id must be nonempty text")
        if not isinstance(self.operator_version, str) or not self.operator_version:
            raise ValueError("operator_version must be nonempty text")
        if not is_dataclass(self.spec) or isinstance(self.spec, type):
            raise TypeError("spec must be a frozen dataclass instance")
        if not _immutable(self.spec):
            raise TypeError("spec must contain immutable, finite values")
        if not isinstance(self.status, ComputeStatus):
            raise TypeError("status must be ComputeStatus")
        if not isinstance(self.issues, tuple) or not all(
            isinstance(issue, ComputeIssue) for issue in self.issues
        ):
            raise TypeError("issues must be a tuple of ComputeIssue")
        if not isinstance(self.parent_computation_ids, tuple) or not all(
            isinstance(item, str) and item for item in self.parent_computation_ids
        ):
            raise TypeError("parent_computation_ids must be a tuple of identities")
        for name in ("source_digest", "computation_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise TypeError(f"{name} must be nonempty text or None")
        if self.status in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL):
            if self.value is None or self.source_digest is None:
                raise ValueError("computed result requires value and source identity")
            if self.status is ComputeStatus.PARTIAL and not self.issues:
                raise ValueError("partial result requires explicit coverage issues")
            if not _immutable(self.value):
                raise TypeError("computed value must contain immutable, finite values")
        elif self.value is not None or not self.issues:
            raise ValueError("failed result requires issues and no value")
        if (self.source_digest is None) != (self.computation_id is None):
            raise ValueError("source and computation identities must coexist")


def _identity_value(value: object) -> object:
    """Use disjoint type tags, including nested parameter types, without coercion."""
    if isinstance(value, Enum):
        return [
            "enum",
            f"{type(value).__module__}.{type(value).__qualname__}",
            _identity_value(value.value),
        ]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("identity timestamp requires a timezone")
        return [
            "datetime",
            value.astimezone(timezone.utc).isoformat(timespec="microseconds"),
        ]
    if is_dataclass(value) and not isinstance(value, type):
        kind = type(value)
        return [
            "dataclass",
            getattr(kind, "SPEC_TYPE", f"{kind.__module__}.{kind.__qualname__}"),
            getattr(kind, "SCHEMA_VERSION", "1.0.0"),
            {
                field.name: _identity_value(getattr(value, field.name))
                for field in fields(value)
            },
        ]
    if isinstance(value, tuple):
        return ["tuple", [_identity_value(item) for item in value]]
    if isinstance(value, float):
        return ["float", value.hex()]
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", value]
    if isinstance(value, str):
        return ["str", value]
    raise TypeError(f"Unsupported identity parameter: {type(value).__name__}")


def computation_identity(
    operator_id: str,
    operator_version: str,
    source_digest: str | None,
    spec: object,
    parent_computation_ids: tuple[str, ...] = (),
) -> str | None:
    """Pure request identity shared by computation and persisted-result validation."""
    for name, text in (
        ("operator_id", operator_id),
        ("operator_version", operator_version),
    ):
        if not isinstance(text, str) or not text:
            raise TypeError(f"{name} must be nonempty text")
    if source_digest is not None and (
        not isinstance(source_digest, str) or not source_digest
    ):
        raise TypeError("source_digest must be nonempty text or None")
    if not is_dataclass(spec) or isinstance(spec, type) or not _immutable(spec):
        raise TypeError("spec must be an immutable finite dataclass instance")
    if not isinstance(parent_computation_ids, tuple) or not all(
        isinstance(item, str) and item for item in parent_computation_ids
    ):
        raise TypeError("parent_computation_ids must be a tuple of identities")
    if source_digest is None:
        return None
    spec_type = type(spec)
    request = {
        "identity_schema": "pix.computation.v1",
        "operator_id": operator_id,
        "operator_version": operator_version,
        "source_digest": source_digest,
        "parameter_type": getattr(
            spec_type, "SPEC_TYPE", f"{spec_type.__module__}.{spec_type.__qualname__}"
        ),
        "parameter_schema_version": getattr(spec_type, "SCHEMA_VERSION", "1.0.0"),
        "parameters": _identity_value(spec),
        "parent_computation_ids": parent_computation_ids,
    }
    encoded = json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "pix.computation.v1:sha256:" + sha256(encoded).hexdigest()


__all__ = ("ComputationResult", "ComputeIssue", "ComputeStatus", "computation_identity")
