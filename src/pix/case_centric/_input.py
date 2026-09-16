"""Preserve the identity and ordering policy of case-based calculations."""

from __future__ import annotations

from pix.contracts.analysis import TraceSet
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult
from pix.event_log import CaseLog, case_traces

CaseInput = CaseLog | ComputationResult[TraceSet]


def as_case_traces(
    data: CaseInput, spec: CaseTraceSpec = CaseTraceSpec()
) -> ComputationResult[TraceSet]:
    """Resolve raw case logs or retain an already identified trace projection.

    The default spec requests no re-projection of an existing result. A nondefault
    spec must match its recorded spec; it cannot silently change the classifier or
    ordering of a trace projection. Failed results keep their issues and identity.
    """
    if not isinstance(spec, CaseTraceSpec):
        raise TypeError("spec must be CaseTraceSpec")
    if isinstance(data, CaseLog):
        return case_traces(data, spec)
    if not isinstance(data, ComputationResult):
        raise TypeError("expected CaseLog or ComputationResult[TraceSet]")
    if data.value is not None and not isinstance(data.value, TraceSet):
        raise TypeError("computation result must contain a TraceSet")
    if spec != CaseTraceSpec() and data.spec != spec:
        raise ValueError("cannot re-project existing traces using a different spec")
    return data


__all__ = ("CaseInput", "as_case_traces")
