"""Object-centric native process mining over canonical OCEL facts.

Shared events, qualified participation, and concrete object bindings remain
distinct from the case-centric projections exposed by ``pix.case_centric``.
"""

from importlib import import_module

from pix.compute.context import ComputationContext
from pix.compute.executions import discover_executions
from pix.compute.object_bindings import enumerate_enabled_bindings
from pix.compute.object_conformance import align_object_log
from pix.compute.object_context import measure_object_context
from pix.compute.ocdfg import discover_ocdfg
from pix.compute.ocpn_discovery import discover_ocpn
from pix.compute.trace import reconstruct_traces
from pix.compute.variants import discover_variants
from pix.contracts.analysis import OCDFGSpec, TraceSpec
from pix.contracts.execution import ExecutionSpec, VariantSpec
from pix.ocel import OCEL

_MODULES = (
    "advanced_filtering",
    "cube",
    "enrichment",
    "equivalent_ocel",
    "filter_predicates",
    "legacy_discovery",
    "model_integration",
    "temporal_summary",
    "transformations",
    "actions",
    "conformance",
    "constraints",
    "discovery",
    "features",
    "filtering",
    "models",
    "performance",
    "relations",
    "simulation",
    "statistics",
    "graph_comparison",
)
_FUNCTIONS = {
    "discover_saw_net": "discovery",
    "discover_object_graph": "relations",
    "discover_etot": "relations",
    "discover_otg": "relations",
    "object_statistics": "statistics",
    "filter_ocel": "filtering",
    "replay_object_log": "conformance",
    "replay_flattened_object_log": "conformance",
    "measure_performance": "performance",
    "measure_replay_performance": "performance",
}


def __getattr__(name: str):
    if name in _MODULES:
        value = import_module(f"{__name__}.{name}")
    elif name in _FUNCTIONS:
        value = getattr(import_module(f"{__name__}.{_FUNCTIONS[name]}"), name)
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = (
    "OCEL",
    "ComputationContext",
    "OCDFGSpec",
    "TraceSpec",
    "ExecutionSpec",
    "VariantSpec",
    "discover_ocdfg",
    "discover_ocpn",
    "discover_executions",
    "discover_variants",
    "reconstruct_traces",
    "enumerate_enabled_bindings",
    "align_object_log",
    "measure_object_context",
    *_MODULES,
    *_FUNCTIONS,
)
