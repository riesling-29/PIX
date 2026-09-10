"""Explicit native operator requests over a shared validated OCEL context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from pix.compute.context import ComputationContext, InvalidOCELInput
from pix.compute.dfg import discover_dfg
from pix.compute.executions import discover_executions
from pix.compute.ocdfg import discover_ocdfg
from pix.compute.temporal import measure_temporal
from pix.compute.trace import reconstruct_traces
from pix.compute.variants import discover_variants
from pix.contracts.analysis import OCDFGSpec, TemporalSpec, TraceSpec
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.contracts.result import ComputationResult
from pix.ocel.model import OCEL


@dataclass(frozen=True, slots=True)
class TraceRequest:
    spec: TraceSpec

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TraceSpec):
            raise TypeError("TraceRequest.spec must be TraceSpec")


@dataclass(frozen=True, slots=True)
class DFGRequest:
    spec: TraceSpec

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TraceSpec):
            raise TypeError("DFGRequest.spec must be TraceSpec")


@dataclass(frozen=True, slots=True)
class OCDFGRequest:
    spec: OCDFGSpec

    def __post_init__(self) -> None:
        if not isinstance(self.spec, OCDFGSpec):
            raise TypeError("OCDFGRequest.spec must be OCDFGSpec")


@dataclass(frozen=True, slots=True)
class TemporalRequest:
    spec: TemporalSpec

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TemporalSpec):
            raise TypeError("TemporalRequest.spec must be TemporalSpec")


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    spec: ExecutionSpec

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ExecutionSpec):
            raise TypeError("ExecutionRequest.spec must be ExecutionSpec")


@dataclass(frozen=True, slots=True)
class VariantRequest:
    execution_spec: ExecutionSpec
    variant_spec: VariantSpec

    def __post_init__(self) -> None:
        if not isinstance(self.execution_spec, ExecutionSpec):
            raise TypeError("VariantRequest.execution_spec must be ExecutionSpec")
        if not isinstance(self.variant_spec, VariantSpec):
            raise TypeError("VariantRequest.variant_spec must be VariantSpec")


ComputeRequest: TypeAlias = (
    TraceRequest
    | DFGRequest
    | OCDFGRequest
    | TemporalRequest
    | ExecutionRequest
    | VariantRequest
)
_REQUEST_TYPES = (
    TraceRequest,
    DFGRequest,
    OCDFGRequest,
    TemporalRequest,
    ExecutionRequest,
    VariantRequest,
)


def compute(
    log: OCEL, *, requests: tuple[ComputeRequest, ...]
) -> tuple[ComputationResult, ...]:
    """Compute requested analyses in order, retaining each result's status.

    A context normalizes and validates the source once. This function does not
    infer a case notion, choose a mining backend, mutate OCEL, or report a batch
    success when an individual operation could not be completed. Model discovery
    and conformance consume trace results through their own explicit APIs.
    """
    if not isinstance(log, OCEL):
        raise TypeError("log must be OCEL")
    if not isinstance(requests, tuple):
        raise TypeError("requests must be a tuple")
    if not requests:
        raise ValueError("at least one explicit request is required")
    if any(type(request) not in _REQUEST_TYPES for request in requests):
        raise TypeError("unsupported computation request")
    source: OCEL | ComputationContext
    try:
        source = ComputationContext.build(log)
    except InvalidOCELInput:
        source = log
    results: list[ComputationResult] = []
    for request in requests:
        if isinstance(request, TraceRequest):
            result = reconstruct_traces(source, request.spec)
        elif isinstance(request, DFGRequest):
            result = discover_dfg(source, request.spec)
        elif isinstance(request, OCDFGRequest):
            result = discover_ocdfg(source, request.spec)
        elif isinstance(request, TemporalRequest):
            result = measure_temporal(source, request.spec)
        elif isinstance(request, ExecutionRequest):
            result = discover_executions(source, request.spec)
        else:
            executions = discover_executions(source, request.execution_spec)
            result = discover_variants(executions, request.variant_spec)
        results.append(result)
    return tuple(results)


__all__ = [
    "ComputeRequest",
    "DFGRequest",
    "ExecutionRequest",
    "OCDFGRequest",
    "TemporalRequest",
    "TraceRequest",
    "VariantRequest",
    "compute",
]
