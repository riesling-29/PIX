"""Case-log entry points for the existing native execution kernels.

The original operator IDs are preserved: these adapters change input ergonomics,
not the alignment, replay, or precision definitions.
"""

from pix.case_centric._input import CaseInput, as_case_traces
from pix.compute.conformance import align_traces as _align
from pix.compute.precision import measure_prefix_precision as _precision
from pix.compute.replay import replay_traces as _replay
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.conformance import AlignmentSet, AlignmentSpec
from pix.contracts.models import PetriNet
from pix.contracts.precision import PrefixPrecision, PrefixPrecisionSpec
from pix.contracts.replay import ReplaySet, ReplaySpec
from pix.contracts.result import ComputationResult


def align_traces(
    data: CaseInput,
    net: PetriNet,
    spec: AlignmentSpec = AlignmentSpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[AlignmentSet]:
    """Align case sequences using the native bounded optimal-search kernel."""
    return _align(as_case_traces(data, trace_spec), net, spec)


def replay_traces(
    data: CaseInput,
    net: PetriNet,
    spec: ReplaySpec = ReplaySpec(),
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[ReplaySet]:
    """Replay source-ordered case traces with explicit token-repair evidence."""
    return _replay(as_case_traces(data, trace_spec), net, spec)


def measure_prefix_precision(
    data: CaseInput,
    net: PetriNet,
    spec: PrefixPrecisionSpec,
    *,
    trace_spec: CaseTraceSpec = CaseTraceSpec(),
) -> ComputationResult[PrefixPrecision]:
    """Use the existing PIX prefix-precision definition and coverage rules."""
    return _precision(as_case_traces(data, trace_spec), net, spec)


__all__ = (
    "AlignmentSpec",
    "ReplaySpec",
    "PrefixPrecisionSpec",
    "align_traces",
    "replay_traces",
    "measure_prefix_precision",
)
