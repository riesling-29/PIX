"""Small native dispatcher with typed requests and a shared validated context."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from pix.ocel import OCEL

from .compute import (
    ComputationContext,
    ComputationResult,
    DirectlyFollowsGraph,
    InvalidOCELInput,
    TraceSet,
    TraceSpec,
    discover_dfg,
    reconstruct_traces,
)


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


ComputeRequest: TypeAlias = TraceRequest | DFGRequest
NativeResult: TypeAlias = (
    ComputationResult[TraceSet] | ComputationResult[DirectlyFollowsGraph]
)


def compute(
    log: OCEL,
    *,
    requests: tuple[ComputeRequest, ...],
) -> tuple[NativeResult, ...]:
    """Evaluate exactly the requested operators, in caller-specified order.

    A non-empty request tuple is required. Every result carries its own status;
    this function does not turn a batch containing failures into one success.
    No result cache or dynamically loaded backend is installed by this proposal.
    """
    if not isinstance(log, OCEL):
        raise TypeError("log must be an OCEL")
    if not isinstance(requests, tuple):
        raise TypeError("requests must be a tuple")
    if not requests:
        raise ValueError("at least one explicit computation request is required")
    if any(type(request) not in (TraceRequest, DFGRequest) for request in requests):
        raise TypeError("every request must be TraceRequest or DFGRequest")

    source: OCEL | ComputationContext
    try:
        source = ComputationContext.build(log)
    except InvalidOCELInput:
        # Public operators produce their own invalid-input evidence. Never build
        # an index which drops invalid source records to make it look valid.
        source = log

    results: list[NativeResult] = []
    for request in requests:
        if isinstance(request, TraceRequest):
            results.append(reconstruct_traces(source, request.spec))
        else:
            results.append(discover_dfg(source, request.spec))
    return tuple(results)
