"""Explicit serialization allowlist for native mining domains.

Only modules named in this source are loaded. Serialized documents cannot
request module imports, callable lookups, or registration of new result types.
"""

from __future__ import annotations


def mining_schemas() -> dict[str, tuple[str, type, type]]:
    from pix.case_centric import (
        advanced,
        advanced_precision,
        alignment_search,
        alpha,
        approximate_alignment,
        backwards_replay,
        bpmn_conversion,
        conformance,
        conformance_approximation,
        context_discovery,
        correlation,
        decision_mining,
        declarative,
        declarative_simulation,
        decomposed_alignment,
        dfg_conversion,
        dfg_filtering,
        discovery,
        embedding_retrieval,
        embeddings,
        evaluation,
        extended_discovery,
        features,
        filtering,
        genetic_miner,
        heuristics,
        heuristics_conversion,
        inductive,
        interleavings,
        interleavings_ocel,
        label_splitting,
        lifecycle,
        link_analysis,
        marking_equation,
        model_analysis,
        model_conversion,
        model_discovery,
        online_alignment,
        organization,
        pn_language_alignment,
        powl,
        pripel,
        privacy,
        sacofa,
        sequence_alignment,
        simulation,
        split_miner,
        statistics,
        stream_adapters,
        streaming,
        transformations,
        transformer_embeddings,
        tree_alignment,
        tree_reduction,
        wfnet_conversion,
    )
    from pix.object_centric import (
        actions as object_actions,
    )
    from pix.object_centric import (
        advanced_filtering as object_advanced_filtering,
    )
    from pix.object_centric import (
        conformance as object_conformance,
    )
    from pix.object_centric import (
        constraints as object_constraints,
    )
    from pix.object_centric import (
        cube as object_cube,
    )
    from pix.object_centric import (
        discovery as object_discovery,
    )
    from pix.object_centric import (
        enrichment as object_enrichment,
    )
    from pix.object_centric import (
        equivalent_ocel as object_equivalent_ocel,
    )
    from pix.object_centric import (
        features as object_features,
    )
    from pix.object_centric import (
        filter_predicates as object_filter_predicates,
    )
    from pix.object_centric import (
        filtering as object_filtering,
    )
    from pix.object_centric import (
        graph_comparison as object_graph_comparison,
    )
    from pix.object_centric import (
        legacy_discovery as object_legacy_discovery,
    )
    from pix.object_centric import (
        model_integration as object_model_integration,
    )
    from pix.object_centric import (
        models as object_models,
    )
    from pix.object_centric import (
        performance as object_performance,
    )
    from pix.object_centric import (
        relations as object_relations,
    )
    from pix.object_centric import (
        simulation as object_simulation,
    )
    from pix.object_centric import (
        statistics as object_statistics,
    )
    from pix.object_centric import (
        temporal_summary as object_temporal_summary,
    )
    from pix.object_centric import (
        transformations as object_transformations,
    )

    modules = (
        object_advanced_filtering,
        bpmn_conversion,
        dfg_conversion,
        evaluation,
        interleavings,
        interleavings_ocel,
        label_splitting,
        link_analysis,
        model_conversion,
        stream_adapters,
        transformations,
        tree_reduction,
        wfnet_conversion,
        object_cube,
        object_enrichment,
        object_equivalent_ocel,
        object_filter_predicates,
        object_legacy_discovery,
        object_model_integration,
        object_temporal_summary,
        object_transformations,
        advanced,
        advanced_precision,
        alignment_search,
        alpha,
        approximate_alignment,
        backwards_replay,
        conformance,
        conformance_approximation,
        context_discovery,
        correlation,
        declarative,
        declarative_simulation,
        decision_mining,
        decomposed_alignment,
        dfg_filtering,
        discovery,
        embeddings,
        embedding_retrieval,
        extended_discovery,
        features,
        filtering,
        genetic_miner,
        heuristics,
        heuristics_conversion,
        inductive,
        lifecycle,
        marking_equation,
        model_analysis,
        model_discovery,
        organization,
        online_alignment,
        pn_language_alignment,
        powl,
        privacy,
        pripel,
        sacofa,
        sequence_alignment,
        simulation,
        split_miner,
        statistics,
        streaming,
        transformer_embeddings,
        tree_alignment,
        object_actions,
        object_conformance,
        object_constraints,
        object_discovery,
        object_features,
        object_filtering,
        object_graph_comparison,
        object_models,
        object_performance,
        object_relations,
        object_simulation,
        object_statistics,
    )
    schemas: dict[str, tuple[str, type, type]] = {}
    for module in modules:
        for operator, schema in module.RESULT_SCHEMAS.items():
            if operator in schemas:
                raise RuntimeError(f"duplicate mining result operator: {operator}")
            if not operator.startswith(("pix.case_centric.", "pix.object_centric.")):
                raise RuntimeError(f"invalid mining result namespace: {operator}")
            if len(schema) != 3:
                raise RuntimeError(f"invalid mining result schema: {operator}")
            schemas[operator] = schema
    return schemas


__all__ = ("mining_schemas",)
