"""Shared identity and input handling without global state or mutable caches."""

from __future__ import annotations

from typing import TypeVar

from pix.compute.context import ComputationContext, InvalidOCELInput
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.ocel import OCEL

OPERATOR_VERSION = "1.0.0"
T = TypeVar("T")


def _result(
    operator_id: str,
    context: ComputationContext | None,
    spec: object,
    status: ComputeStatus,
    value: T | None,
    issues: tuple[ComputeIssue, ...] = (),
    *,
    parent_computation_ids: tuple[str, ...] = (),
    operator_version: str = OPERATOR_VERSION,
    source_digest: str | None = None,
) -> ComputationResult[T]:
    if context is not None:
        if source_digest is not None and source_digest != context.source_digest:
            raise ValueError("explicit source digest does not match context")
        source_digest = context.source_digest
    computation_id = computation_identity(
        operator_id, operator_version, source_digest, spec, parent_computation_ids
    )
    return ComputationResult(
        operator_id,
        operator_version,
        source_digest,
        spec,
        status,
        value,
        issues,
        computation_id,
        parent_computation_ids,
    )


def _prepare(
    log: OCEL | ComputationContext,
) -> tuple[ComputationContext | None, tuple[ComputeIssue, ...]]:
    if isinstance(log, ComputationContext):
        return log, ()
    if not isinstance(log, OCEL):
        return None, (ComputeIssue("invalid_log_type", "Expected OCEL or context"),)
    try:
        return ComputationContext(log), ()
    except InvalidOCELInput as exc:
        return None, tuple(
            ComputeIssue(issue.code, issue.message, issue.at)
            for issue in exc.report.errors
        )


def _derived_result(
    operator_id: str,
    source_digest: str | None,
    spec: object,
    status: ComputeStatus,
    value: T | None,
    issues: tuple[ComputeIssue, ...] = (),
    *,
    parent_computation_ids: tuple[str, ...] = (),
    operator_version: str = OPERATOR_VERSION,
) -> ComputationResult[T]:
    return _result(
        operator_id,
        None,
        spec,
        status,
        value,
        issues,
        parent_computation_ids=parent_computation_ids,
        operator_version=operator_version,
        source_digest=source_digest,
    )
