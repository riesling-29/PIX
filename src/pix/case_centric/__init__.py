"""Case-centric native process mining; source sequence remains explicit.

Domain modules provide separate calculation profiles. New calculations are not
implicitly applied to object-centric data: select a projection explicitly.
"""

from importlib import import_module

from pix.case_centric._input import CaseInput
from pix.contracts.case_log import CaseTraceSpec
from pix.event_log import CaseLog, case_traces

_MODULES = (
    "coverability",
    "decision_evaluation",
    "drift_evaluation",
    "extended_nets",
    "feature_dataset",
    "maximal_decomposition",
    "model_labels",
    "powl_conversion",
    "resource_simulation",
    "revisable_stream",
    "timed_playout",
    "tree_bordered",
    "trie_conversion",
    "bpmn_conversion",
    "dfg_conversion",
    "evaluation",
    "interleavings",
    "interleavings_ocel",
    "label_splitting",
    "link_analysis",
    "model_conversion",
    "stream_adapters",
    "transformations",
    "tree_reduction",
    "wfnet_conversion",
    "advanced",
    "advanced_precision",
    "alignment_search",
    "alpha",
    "approximate_alignment",
    "backwards_replay",
    "conformance",
    "conformance_approximation",
    "context_discovery",
    "correlation",
    "declarative",
    "declarative_simulation",
    "decision_mining",
    "decomposed_alignment",
    "dfg_filtering",
    "discovery",
    "embeddings",
    "embedding_retrieval",
    "execution",
    "extended_discovery",
    "features",
    "filtering",
    "genetic_miner",
    "heuristics",
    "heuristics_conversion",
    "inductive",
    "lifecycle",
    "marking_equation",
    "model_analysis",
    "model_discovery",
    "organization",
    "online_alignment",
    "pn_language_alignment",
    "powl",
    "privacy",
    "pripel",
    "sacofa",
    "sequence_alignment",
    "simulation",
    "split_miner",
    "statistics",
    "streaming",
    "transformer_embeddings",
    "tree_alignment",
)
_FUNCTIONS = {
    "discover_dfg": "discovery",
    "discover_efg": "discovery",
    "discover_footprints": "discovery",
    "discover_inductive": "inductive",
    "discover_inductive_strict": "inductive",
    "discover_alpha": "alpha",
    "discover_alpha_plus": "alpha",
    "discover_heuristics": "heuristics",
    "align_traces": "execution",
    "replay_traces": "execution",
    "measure_prefix_precision": "execution",
    "measure_statistics": "statistics",
    "filter_case_log": "filtering",
}


def __getattr__(name: str):
    """Load only explicitly exposed modules; optional ML remains lazy."""
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
    "CaseInput",
    "CaseLog",
    "CaseTraceSpec",
    "case_traces",
    *_MODULES,
    *_FUNCTIONS,
)
