"""Single-case membership using exact unit-deviation alignment semantics."""

from __future__ import annotations

from dataclasses import dataclass

from pix.compute._common import _result
from pix.compute.conformance import align_traces
from pix.compute.discovery import process_tree_to_petri_net
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.conformance import AlignmentSpec, TraceAlignment
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import PetriNet
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest, case_traces
from pix.models import model_document


@dataclass(frozen=True, slots=True)
class TraceFitSpec:
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_states: int = 10000

    def __post_init__(self):
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if type(self.max_states) is not int or self.max_states < 1:
            raise ValueError("max_states must be positive")


@dataclass(frozen=True, slots=True)
class TraceFitRequest:
    model_digest: str
    parameters: TraceFitSpec


@dataclass(frozen=True, slots=True)
class TraceFit:
    case_id: str
    fitting: bool | None
    reason: str
    alignment: TraceAlignment

    def __post_init__(self):
        if self.case_id != self.alignment.object_id:
            raise ValueError("case identity differs from alignment")
        expected = (
            None
            if self.alignment.status == "search_limit"
            else self.alignment.status == "optimal" and self.alignment.cost == 0
        )
        if self.fitting is not expected:
            raise ValueError("membership disagrees with exact alignment evidence")
        if (
            self.reason
            != {
                "search_limit": "unknown_search_limit",
                "unreachable": "no_accepting_alignment",
                "optimal": "accepted" if expected else "positive_deviation_cost",
            }[self.alignment.status]
        ):
            raise ValueError("membership reason differs from alignment evidence")


def check_trace_fit(
    log: CaseLog, model: PetriNet | ProcessTree, spec: TraceFitSpec = TraceFitSpec()
):
    """Return true/false/unknown; never mistake search exhaustion for nonfitness.

    Exactly one case (possibly with zero events) is required. Log/model deviations
    cost one and synchronous/silent moves cost zero, so zero optimal cost means
    language membership. Arbitrary user costs cannot redefine this Boolean test.
    """
    if (
        not isinstance(log, CaseLog)
        or not isinstance(model, (PetriNet, ProcessTree))
        or not isinstance(spec, TraceFitSpec)
    ):
        raise TypeError("expected CaseLog, PetriNet/ProcessTree and TraceFitSpec")
    request = TraceFitRequest(model_document(model)["model_digest"], spec)
    source = case_log_digest(log)
    operator = "pix.case_centric.check_trace_fit"
    if len(log.traces) != 1:
        return _result(
            operator,
            None,
            request,
            ComputeStatus.INVALID_INPUT,
            None,
            (ComputeIssue("single_case_required", "Select exactly one case"),),
            source_digest=source,
        )
    traces = case_traces(log, spec.trace_spec)
    if traces.value is None:
        return _result(
            operator,
            None,
            request,
            traces.status,
            None,
            traces.issues,
            source_digest=source,
        )
    net = process_tree_to_petri_net(model) if isinstance(model, ProcessTree) else model
    aligned = align_traces(traces, net, AlignmentSpec(max_states=spec.max_states))
    if aligned.value is None:
        return _result(
            operator,
            None,
            request,
            aligned.status,
            None,
            aligned.issues,
            source_digest=source,
            parent_computation_ids=(aligned.computation_id,),
        )
    trace = aligned.value.alignments[0]
    fitting = (
        None
        if trace.status == "search_limit"
        else trace.status == "optimal" and trace.cost == 0
    )
    reason = {
        "search_limit": "unknown_search_limit",
        "unreachable": "no_accepting_alignment",
        "optimal": "accepted" if fitting else "positive_deviation_cost",
    }[trace.status]
    issues = aligned.issues
    if fitting is None and not issues:
        issues = (ComputeIssue("search_limit", "Trace membership remains unknown"),)
    return _result(
        operator,
        None,
        request,
        ComputeStatus.PARTIAL if fitting is None else ComputeStatus.COMPUTED,
        TraceFit(trace.object_id, fitting, reason, trace),
        issues,
        source_digest=source,
        parent_computation_ids=(aligned.computation_id,),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.check_trace_fit": (
        "case-single-trace-fit",
        TraceFitRequest,
        TraceFit,
    )
}
__all__ = ["TraceFitSpec", "TraceFitRequest", "TraceFit", "check_trace_fit"]
