"""Public facade for explicit native analysis, OCEL I/O and result persistence."""

from pix._publication import FilePublication
from pix.compute.conformance import align_traces
from pix.compute.constraints import evaluate_constraints
from pix.compute.context import ComputationContext
from pix.compute.dfg import discover_dfg
from pix.compute.discovery import discover_process_tree, process_tree_to_petri_net
from pix.compute.executions import discover_executions
from pix.compute.model_semantics import (
    enabled_transitions,
    fire,
    fire_binding,
    is_binding_enabled,
    is_enabled,
    is_final,
    is_object_final,
    model_digest,
)
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.compute.object_conformance import align_object_log
from pix.compute.object_context import measure_object_context
from pix.compute.ocdfg import discover_ocdfg
from pix.compute.ocpn_discovery import discover_ocpn
from pix.compute.precision import measure_prefix_precision
from pix.compute.replay import replay_traces
from pix.compute.temporal import measure_temporal
from pix.compute.trace import reconstruct_traces
from pix.compute.variants import discover_variants
from pix.contracts.analysis import OCDFGSpec, TemporalSpec, TraceSpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.constraint import (
    ConstraintSpec,
    CountRule,
    NotCoexistenceRule,
    PrecedenceRule,
    ResponseRule,
    TimedResponseRule,
)
from pix.contracts.discovery import DiscoverySpec, ProcessTree
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.contracts.object_conformance import ObjectAlignmentSpec
from pix.contracts.object_context import ObjectContextSpec
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.precision import PrefixPrecisionSpec
from pix.contracts.replay import ReplaySpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.engine import (
    DFGRequest,
    ExecutionRequest,
    OCDFGRequest,
    TemporalRequest,
    TraceRequest,
    VariantRequest,
    compute,
)
from pix.models import (
    ModelArtifact,
    model_document,
    model_from_json,
    model_json_bytes,
    read_model,
    write_model,
)
from pix.ocel import export_ocel, import_ocel, read_ocel
from pix.results import (
    read_result,
    result_document,
    result_from_json,
    result_json_bytes,
    write_result,
)

__all__ = [
    "ConstraintSpec",
    "CountRule",
    "NotCoexistenceRule",
    "ObjectAlignmentSpec",
    "ObjectContextSpec",
    "OCPNDiscoverySpec",
    "PrecedenceRule",
    "PrefixPrecisionSpec",
    "ResponseRule",
    "TimedResponseRule",
    "align_object_log",
    "discover_ocpn",
    "enumerate_enabled_bindings",
    "evaluate_constraints",
    "measure_object_context",
    "measure_prefix_precision",
    "FilePublication",
    "ModelArtifact",
    "model_document",
    "model_from_json",
    "model_json_bytes",
    "read_model",
    "write_model",
    "AlignmentSpec",
    "ComputationContext",
    "ComputationResult",
    "ComputeIssue",
    "ComputeStatus",
    "DFGRequest",
    "DiscoverySpec",
    "ExecutionRequest",
    "ExecutionSpec",
    "OCDFGRequest",
    "OCDFGSpec",
    "ProcessTree",
    "ReplaySpec",
    "TemporalRequest",
    "TemporalSpec",
    "TraceRequest",
    "TraceSpec",
    "VariantRequest",
    "VariantSpec",
    "align_traces",
    "compute",
    "discover_dfg",
    "discover_executions",
    "discover_ocdfg",
    "discover_process_tree",
    "discover_variants",
    "enabled_transitions",
    "export_ocel",
    "fire",
    "fire_binding",
    "import_ocel",
    "is_binding_enabled",
    "is_enabled",
    "is_final",
    "is_object_final",
    "measure_temporal",
    "model_digest",
    "process_tree_to_petri_net",
    "read_ocel",
    "read_result",
    "reconstruct_traces",
    "replay_traces",
    "result_document",
    "result_from_json",
    "result_json_bytes",
    "write_result",
]
