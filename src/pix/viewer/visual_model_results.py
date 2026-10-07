"""Explicit discovery/conversion result adapters preserving diagnostic evidence.

Only enumerated output payload classes are accepted. A field called ``model``
on a request or arbitrary object is not sufficient. Supplied guarantees remain
reported claims; rendering them does not establish soundness or equivalence.
"""

from __future__ import annotations

import json
from dataclasses import replace

from pix.case_centric.alpha import AlphaDiscovery
from pix.case_centric.bpmn_conversion import BPMNConversion
from pix.case_centric.decision_mining import DataPetriNetMining
from pix.case_centric.dfg_conversion import DFGConversion
from pix.case_centric.discovery import LocalProcessModel, LocalProcessModelDiscovery
from pix.case_centric.genetic_miner import GeneticDiscovery
from pix.case_centric.heuristics_conversion import HeuristicsConversion
from pix.case_centric.marking_equation import SynchronousProduct
from pix.case_centric.model_analysis import ModelDecomposition, ModelReduction
from pix.case_centric.model_conversion import TreeBPMNConversion, TreePOWLConversion
from pix.case_centric.models_extended import RegionDiscovery
from pix.case_centric.powl import POWLDiscovery
from pix.case_centric.split_miner import SplitDiscovery
from pix.case_centric.tree_reduction import TreeReduction
from pix.case_centric.wfnet_conversion import WfNetConversion
from pix.contracts.models import OCPNDiscoveryPayload
from pix.object_centric.model_integration import (
    EnhancedObjectCentricPetriNet,
    ObjectTypePetriNet,
    OCPNDecomposition,
)
from pix.object_centric.models import (
    ObjectModelConversion,
    ObjectModelTransformation,
    ObjectReduction,
)
from pix.results import _decode, _encode
from pix.viewer.visual_contracts import TablePanel
from pix.viewer.visual_model_adapters import model_panels


def _cell(value):
    if value is None or type(value) in (str, int, float, bool):
        return value
    encoded = _encode(value)
    if encoded is None or type(encoded) in (str, int, float, bool):
        return encoded
    return json.dumps(
        encoded,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _table(identifier, title, columns, rows, description=""):
    return TablePanel(
        identifier,
        title,
        tuple(columns),
        tuple(tuple(_cell(value) for value in row) for row in rows),
        description=description
        + " Nested structures are inert JSON text, not executable expressions.",
    )


def _records(identifier, title, records, columns, description=""):
    """Columns are explicitly enumerated per accepted result schema."""
    return _table(
        identifier,
        title,
        columns,
        (tuple(getattr(row, name) for name in columns) for row in records),
        description,
    )


def _summary(value, fields):
    return _table(
        "result_summary",
        "Reported discovery or conversion diagnostics",
        ("field", "value"),
        (
            ("payload_type", type(value).__name__),
            *((name, getattr(value, name)) for name in fields),
        ),
        "These fields are supplied result diagnostics. The viewer does not infer extra soundness, fitness, optimality or reference-equivalence guarantees.",
    )


def _finish(model, panels):
    if model is None:
        graphs = (
            _table(
                "model_availability",
                "Model unavailable",
                ("model_available", "meaning"),
                (
                    (
                        False,
                        "This result contains no model. Inspect its reported diagnostics and refusal conditions.",
                    ),
                ),
            ),
        )
    else:
        graphs = model_panels(model)
        if graphs is None:
            raise TypeError("recognized result contains an unsupported model type")
    return model, (*graphs, *panels)


def _extra_model(model, prefix, title):
    panels = model_panels(model)
    if panels is None:
        raise TypeError("additional result model is not supported")
    return tuple(
        replace(panel, id=prefix + ":" + panel.id, title=title + " — " + panel.title)
        for panel in panels
    )


def _split(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "profile",
                    "trace_count",
                    "empty_trace_count",
                    "frequency_threshold",
                    "short_loops",
                    "unresolved_gateway_nodes",
                    "interval_comparisons",
                    "connectivity_edge_visits",
                    "soundness",
                    "reference_equivalence",
                ),
            ),
            _table(
                "split_activities",
                "Activity identity mapping",
                ("node_id", "activity"),
                value.activities,
            ),
            _records(
                "split_edges",
                "Retained and removed edge evidence",
                value.edges,
                ("source", "target", "count", "retained", "reason"),
            ),
            _records(
                "split_concurrency",
                "Concurrency selection evidence",
                value.concurrency,
                (
                    "left",
                    "right",
                    "forward_count",
                    "reverse_count",
                    "overlap_count",
                    "selected",
                    "reason",
                ),
            ),
        ),
    )


def _ocpn_discovery(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "event_scope",
                    "cardinality_scope",
                    "joint_cardinality_guarantee",
                    "fitting_guarantee",
                ),
            ),
            _records(
                "cardinality_profiles",
                "Observed object cardinality profiles",
                value.cardinality_profiles,
                (
                    "activity",
                    "object_type",
                    "histogram",
                    "arc_kind",
                    "min_objects",
                    "max_objects",
                ),
                "Histogram entries are (object count, event frequency). Observed min/max intervals do not assert support for unseen joint combinations.",
            ),
            _records(
                "type_projections",
                "Per-type discovery provenance",
                value.projections,
                (
                    "object_type",
                    "trace_computation_id",
                    "discovery_computation_id",
                    "model_digest",
                    "object_count",
                    "isolated_object_ids",
                ),
            ),
            _records(
                "transition_sources",
                "Local to merged transition identities",
                value.transition_sources,
                ("object_type", "local_transition_id", "merged_transition_id"),
            ),
            _table(
                "observed_bindings",
                "Observed event bindings",
                ("event_id", "activity", "transition_id", "objects"),
                (
                    (r.event_id, r.activity, r.binding.transition_id, r.binding.objects)
                    for r in value.observed_event_bindings
                ),
            ),
            _table(
                "fitting_witness",
                "Ordered accepting witness",
                ("step_index", "event_id", "transition_id", "objects"),
                (
                    (i, r.event_id, r.binding.transition_id, r.binding.objects)
                    for i, r in enumerate(value.fitting_witness)
                ),
                "Null event IDs identify silent steps. The witness concerns this finite object universe and these observations, not global soundness.",
            ),
        ),
    )


def _alpha(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "variant",
                    "length_one_activities",
                    "length_two_pairs",
                    "candidate_count",
                    "relation_checks",
                ),
            ),
            _table(
                "alpha_relations",
                "Alpha relation evidence",
                ("relation", "source", "target"),
                (
                    (kind, a, b)
                    for kind, pairs in (
                        ("causal", value.causal_pairs),
                        ("parallel", value.parallel_pairs),
                    )
                    for a, b in pairs
                ),
                "These are the discovery profile's relations, not an additional model soundness check.",
            ),
            _records(
                "alpha_places",
                "Maximal place construction",
                value.maximal_places,
                ("place_id", "input_transition_ids", "output_transition_ids"),
            ),
        ),
    )


def _powl(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "profile",
                    "trace_count",
                    "variant_count",
                    "order_checks",
                    "model_node_count",
                    "generalization_rules",
                ),
            ),
            _records(
                "powl_branches",
                "POWL branch evidence",
                value.branches,
                ("rule", "observed_variants", "activities", "order"),
            ),
            *_extra_model(
                value.petri_net, "powl_accepting_net", "POWL accepting-net conversion"
            ),
        ),
    )


def _region(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "alphabet",
                    "enumerated_assignments",
                    "feasible_regions",
                    "optimizer_states",
                    "objective_arc_weight",
                    "objective_place_count",
                    "optimal_within_bounds",
                    "all_targets_separated",
                ),
            ),
            _records(
                "regions",
                "Integer-region incidence and separation evidence",
                value.regions,
                (
                    "initial",
                    "final",
                    "consume",
                    "produce",
                    "blocked_target_ids",
                    "arc_weight_cost",
                ),
                "Consume/produce vectors use the reported alphabet order. Optimality, when reported, is restricted to configured search bounds.",
            ),
            _table(
                "separation_targets",
                "Region separation targets",
                ("target_index", "prefix", "next_activity", "separated"),
                (
                    (i, r.prefix, r.next_activity, r.separated)
                    for i, r in enumerate(value.separation_targets)
                ),
            ),
        ),
    )


def _genetic(value):
    return _finish(
        value.model,
        (
            _summary(
                value,
                (
                    "profile",
                    "stop_reason",
                    "evaluated_models",
                    "rejected_models",
                    "crossover_changes",
                    "mutation_changes",
                    "optimality_proven",
                ),
            ),
            _records(
                "genetic_objective",
                "Reported genetic objective components",
                (value.objective,),
                (
                    "score",
                    "observed_case_acceptance",
                    "empirical_language_precision",
                    "inverse_node_count",
                    "accepted_cases",
                    "total_cases",
                    "accepted_observed_variants",
                    "language_size",
                    "node_count",
                ),
            ),
            _records(
                "genetic_generations",
                "Genetic search history",
                value.history,
                (
                    "generation",
                    "best_score",
                    "mean_score",
                    "distinct_models",
                    "evaluated_models",
                    "rejected_models",
                    "crossover_changes",
                    "mutation_changes",
                ),
            ),
            _table(
                "genetic_language",
                "Finite language and rejected observed variants",
                ("kind", "activities"),
                (
                    (kind, word)
                    for kind, words in (
                        ("model_language", value.language),
                        ("rejected_observation", value.rejected_observed_variants),
                    )
                    for word in words
                ),
            ),
        ),
    )


_ADAPTERS = {
    SplitDiscovery: _split,
    OCPNDiscoveryPayload: _ocpn_discovery,
    AlphaDiscovery: _alpha,
    POWLDiscovery: _powl,
    RegionDiscovery: _region,
    GeneticDiscovery: _genetic,
}


# Each row is an explicitly accepted output type, scalar diagnostic field list,
# and table schemas. The final boolean selects dataclass records versus tuples.
_CONVERSIONS = {
    HeuristicsConversion: (
        ("profile", "source_model_digest"),
        (
            (
                "activity_transitions",
                "Activity to visible-transition mapping",
                ("activity", "transition_id"),
                False,
            ),
            (
                "edge_places",
                "Dependency edge to place mapping",
                ("source", "target", "place_id"),
                True,
            ),
            (
                "binding_transitions",
                "Binding alternative to transition mapping",
                ("activity", "direction", "members", "transition_id"),
                True,
            ),
        ),
    ),
    BPMNConversion: (
        ("profile", "source_model_digest", "soundness", "reference_equivalence"),
        (
            (
                "flow_places",
                "BPMN flow to Petri place mapping",
                ("flow_id", "place_id"),
                True,
            ),
            (
                "node_transitions",
                "BPMN node to Petri transition mapping",
                ("node_id", "transition_id", "incoming_flow_ids", "outgoing_flow_ids"),
                True,
            ),
        ),
    ),
    DFGConversion: (
        (
            "profile",
            "source_model_digest",
            "input_kind",
            "projected_object_type",
            "allows_empty_trace",
        ),
        (
            (
                "activity_places",
                "Activity place occurrences",
                ("activity", "place_ids"),
                False,
            ),
            (
                "activity_transitions",
                "Activity transition occurrences",
                ("activity", "transition_ids"),
                False,
            ),
            (
                "routes",
                "Route transitions and boundary endpoints",
                ("source", "target", "transition_id"),
                True,
            ),
        ),
    ),
    TreePOWLConversion: (
        ("source_model_digest",),
        (
            (
                "steps",
                "Structural conversion rules by occurrence path",
                ("tree_path", "rule"),
                True,
            ),
        ),
    ),
    TreeBPMNConversion: (
        ("source_model_digest",),
        (
            (
                "steps",
                "Structural conversion rules by occurrence path",
                ("tree_path", "rule"),
                True,
            ),
            (
                "activity_nodes",
                "Tree occurrence to BPMN activity node mapping",
                ("tree_path", "node_id"),
                False,
            ),
        ),
    ),
    TreeReduction: (
        (
            "source_model_digest",
            "reduced_model_digest",
            "guarantee",
            "input_node_count",
            "output_node_count",
            "changed",
        ),
        (
            (
                "rewrites",
                "Applied tree rewrite evidence",
                (
                    "source_path",
                    "rule",
                    "before_structure_digest",
                    "after_structure_digest",
                    "removed_activities",
                    "epsilon_leaf_paths",
                ),
                True,
            ),
        ),
    ),
    ModelReduction: (
        ("original_model_digest", "reduced_model_digest", "preservation"),
        (
            (
                "steps",
                "Applied Petri net reduction steps",
                ("rule", "removed_node", "retained_node"),
                True,
            ),
        ),
    ),
    ObjectModelTransformation: (
        (
            "removed_place_ids",
            "removed_transition_ids",
            "removed_arc_endpoints",
            "hidden_transition_ids",
            "behavioral_guarantee",
            "boundary_note",
        ),
        (
            (
                "place_mapping",
                "Object-place transformation ledger",
                ("source_place", "target_place"),
                False,
            ),
        ),
    ),
    ObjectReduction: (
        ("fixed_point_reached", "guarantee", "not_preserved"),
        (
            (
                "steps",
                "Object-centric reduction conditions and steps",
                (
                    "rule",
                    "removed_place_ids",
                    "removed_transition_ids",
                    "place_mapping",
                    "sufficient_condition",
                ),
                True,
            ),
            (
                "original_to_reduced_places",
                "Original to reduced place ledger",
                ("source_place", "target_place"),
                False,
            ),
        ),
    ),
    DataPetriNetMining: (
        (
            "training_case_ids",
            "training_observation_count",
            "excluded_training_observation_count",
            "tree_computation_ids",
        ),
        (),
    ),
    SynchronousProduct: (
        ("source_model_digest", "trace"),
        (
            (
                "transitions",
                "Log/model/synchronous move identity and rational cost",
                (
                    "transition_id",
                    "move_kind",
                    "trace_index",
                    "model_transition_id",
                    "cost",
                ),
                True,
            ),
        ),
    ),
}


def _configured_conversion(value):
    diagnostics, table_specs = _CONVERSIONS[type(value)]
    tables = [_summary(value, diagnostics)]
    for field, title, columns, records in table_specs:
        data = getattr(value, field)
        if records:
            description = (
                "Cost is the exact (numerator, denominator) pair. These are available move constructions, not an executed alignment or its fitness."
                if type(value) is SynchronousProduct
                else ""
            )
            tables.append(
                _records("conversion_" + field, title, data, columns, description)
            )
        else:
            tables.append(_table("conversion_" + field, title, columns, data))
    return _finish(value.model, tuple(tables))


def _wfnet(value):
    panels = [
        _summary(
            value,
            (
                "profile",
                "source_model_digest",
                "complete",
                "remaining_place_ids",
                "remaining_transition_ids",
                "pattern_checks",
            ),
        ),
        _records(
            "wfnet_reductions",
            "Workflow-net structural reductions",
            value.reductions,
            (
                "rule",
                "transition_ids",
                "original_transition_ids",
                "removed_place_ids",
                "replacement_transition_id",
                "input_place_ids",
                "output_place_ids",
                "tree",
            ),
        ),
    ]
    if value.certificate is None:
        panels.append(
            _table(
                "language_certificate",
                "Language certificate unavailable",
                ("certificate_available",),
                ((False,),),
                "No certificate is supplied. Missing evidence is not an equivalence claim.",
            )
        )
    else:
        certificate = value.certificate
        panels.append(
            _table(
                "language_certificate",
                "Reported workflow conversion certificate",
                ("field", "value"),
                (
                    ("source_model_digest", certificate.source_model_digest),
                    ("converted_model_digest", certificate.converted_model_digest),
                    (
                        "comparison_computation_id",
                        certificate.comparison_computation_id,
                    ),
                    *(
                        (name, getattr(certificate.comparison, name))
                        for name in (
                            "method",
                            "equivalent",
                            "similarity",
                            "distinguishing_trace",
                            "accepted_by",
                            "compared_product_states",
                            "complete",
                            "left_reachability_complete",
                            "right_reachability_complete",
                        )
                    ),
                ),
                "The comparison result and its bounds are retained; rendering does not rerun equivalence checking.",
            )
        )
    return _finish(value.model, tuple(panels))


def _model_decomposition(value):
    if len(value.components) != len(value.component_node_ids):
        raise ValueError("decomposition component models and identity ledgers disagree")
    panels = [
        _summary(value, ("composition",)),
        _table(
            "decomposition_components",
            "Component identity ledger",
            ("component_index", "node_ids"),
            enumerate(value.component_node_ids),
            "The document contains separate component models, not a newly inferred aggregate model.",
        ),
    ]
    for index, model in enumerate(value.components):
        panels.extend(_extra_model(model, f"component_{index}", f"Component {index}"))
    return None, tuple(panels)


def _object_conversion(value):
    if value.ocpn is not None and value.causal_net is not None:
        raise ValueError("object model conversion must identify a single target model")
    model = value.ocpn if value.ocpn is not None else value.causal_net
    if (model is None and value.exact) or (model is not None and value.refusal_reasons):
        raise ValueError(
            "object conversion target contradicts its refusal or exactness claim"
        )
    return _finish(
        model,
        (
            _summary(value, ("profile", "exact", "loss_report", "refusal_reasons")),
            _table(
                "transition_mapping",
                "Source transition to target occurrences",
                ("source_transition_id", "target_transition_ids"),
                value.transition_mapping,
            ),
        ),
    )


def _object_type_projection(value):
    return _finish(
        value.petri_net,
        (
            _summary(
                value,
                (
                    "object_type",
                    "object_ids",
                    "start_transition_ids",
                    "end_transition_ids",
                ),
            ),
            _table(
                "concrete_markings",
                "Concrete object marking ledger",
                ("marking", "place_id", "object_id"),
                (
                    (kind, token.place_id, token.object_id)
                    for kind, marking in (
                        ("initial", value.concrete_initial_marking),
                        ("final", value.concrete_final_marking),
                    )
                    for token in marking.tokens
                ),
                "Ordinary projected tokens do not carry object identity. The ledger preserves concrete tokens and their multiplicity.",
            ),
            _records(
                "arc_cardinalities",
                "Object-incidence cardinality ledger",
                value.arc_cardinalities,
                ("source", "target", "variable", "min_objects", "max_objects"),
                "The ordinary net has unit arcs. Object-selection cardinality remains explicit in this ledger and must not be inferred from ordinary arc weights.",
            ),
        ),
    )


def _ocpn_decomposition(value):
    panels = [
        _summary(
            value,
            (
                "source_model_digest",
                "shared_transition_ids",
                "activity_labels",
                "projected_semantic_losses",
                "reconstruction_guarantee",
            ),
        ),
        _records(
            "unattached_transitions",
            "Transitions without selected type incidence",
            value.unattached_transitions,
            ("id", "activity"),
        ),
    ]
    for index, projection in enumerate(value.per_type):
        _, projected_panels = _object_type_projection(projection)
        panels.extend(
            replace(
                panel,
                id=f"type_{index}:" + panel.id,
                title=f"{projection.object_type} — " + panel.title,
            )
            for panel in projected_panels
        )
    return None, tuple(panels)


def _enhanced_ocpn(value):
    replay, performance = value.replay, value.performance
    measurements = performance.measurements
    return _finish(
        value.model,
        (
            _summary(value, ("profile", "unassigned_performance_event_ids")),
            _records(
                "transition_diagnostics",
                "Transition replay and performance diagnostics",
                value.transition_diagnostics,
                (
                    "transition_id",
                    "activity",
                    "firing_step_indices",
                    "observed_event_ids",
                    "consumed_token_count",
                    "produced_token_count",
                    "inserted_token_count",
                    "metrics",
                ),
            ),
            _table(
                "replay_summary",
                "Joint replay population and outcome",
                ("field", "value"),
                (
                    (name, getattr(replay, name))
                    for name in (
                        "model_digest",
                        "scope",
                        "status",
                        "event_order",
                        "processed_event_count",
                        "log_deviation_count",
                        "counts",
                        "token_fitness",
                        "fitting",
                        "final_reached",
                        "ending_marking",
                        "limit_reason",
                        "profile",
                    )
                ),
                "Inserted tokens are repair evidence, not conforming behavior. Unknown fitting or fitness remains null.",
            ),
            _table(
                "replay_steps",
                "Ordered joint replay steps",
                (
                    "step_index",
                    "kind",
                    "event_id",
                    "transition_id",
                    "objects",
                    "marking_before",
                    "marking_after",
                    "inserted_tokens",
                    "consumed_tokens",
                    "produced_tokens",
                    "deviation_reason",
                ),
                (
                    (
                        i,
                        r.kind,
                        r.event_id,
                        r.binding.transition_id if r.binding else None,
                        r.binding.objects if r.binding else None,
                        r.marking_before,
                        r.marking_after,
                        r.inserted_tokens,
                        r.consumed_tokens,
                        r.produced_tokens,
                        r.deviation_reason,
                    )
                    for i, r in enumerate(replay.steps)
                ),
            ),
            _records(
                "replay_searches",
                "Silent-search completeness and bounds",
                replay.searches,
                ("event_id", "state_count", "exhaustive", "limit_reason"),
            ),
            _table(
                "performance_policy",
                "Timed-token policy and population",
                ("field", "value"),
                (
                    *(
                        (name, getattr(performance, name))
                        for name in (
                            "model_digest",
                            "replay_status",
                            "profile",
                            "token_selection",
                            "silent_policy",
                        )
                    ),
                    ("measurement_profile", measurements.profile),
                    ("object_type", measurements.object_type),
                    ("selected_event_ids", measurements.selected_event_ids),
                ),
            ),
            _records(
                "performance_summaries",
                "Known and unknown performance populations",
                measurements.summaries,
                (
                    "metric",
                    "unit",
                    "population_count",
                    "known_count",
                    "unknown_count",
                    "total",
                    "minimum",
                    "maximum",
                    "mean_numerator",
                    "mean_denominator",
                ),
                "Mean is the exact numerator/denominator ratio over known samples. Unknown samples are retained in population counts.",
            ),
            _records(
                "performance_samples",
                "Per-observation performance evidence",
                (
                    sample
                    for summary in measurements.summaries
                    for sample in summary.samples
                ),
                (
                    "metric",
                    "unit",
                    "event_id",
                    "object_id",
                    "object_type",
                    "value",
                    "reason",
                    "completion_time",
                    "explicit_start_time",
                    "related_object_ids",
                    "reference_event_ids",
                    "evidence",
                    "type_selection_relations",
                ),
            ),
            _records(
                "token_inputs",
                "Event input-token population",
                performance.token_inputs,
                ("event_id", "step_index", "known_count", "unknown_count", "reason"),
            ),
            _table(
                "token_arrivals",
                "Timed token lineage",
                (
                    "event_id",
                    "token_serial",
                    "place_id",
                    "object_id",
                    "object_type",
                    "arrival_time",
                    "origin",
                    "produced_step",
                    "source_event_ids",
                    "unknown_reason",
                ),
                (
                    (
                        row.event_id,
                        a.token_serial,
                        a.place_id,
                        a.object_id,
                        a.object_type,
                        a.arrival_time,
                        a.origin,
                        a.produced_step,
                        a.source_event_ids,
                        a.unknown_reason,
                    )
                    for row in performance.token_inputs
                    for a in row.arrivals
                ),
                "Unknown initial/injected token clocks remain null. Tokens sharing place/object IDs remain distinct through their serial and production step.",
            ),
        ),
    )


def _local_model(value):
    return _finish(
        value.tree,
        (
            _summary(
                value,
                (
                    "frequency",
                    "case_support",
                    "confidence",
                    "activity_coverage",
                    "bounded_language_fit",
                    "prefix_determinism",
                    "language_word_count",
                    "language_is_complete",
                ),
            ),
            _records(
                "local_occurrences",
                "Matched local-model occurrence witnesses",
                value.occurrences,
                ("case_id", "event_ids", "activities"),
                "Frequency belongs to the supplied local model as a whole. It is not a per-node or per-edge frequency annotation. Language-fit denominators are bounded by the discovery profile.",
            ),
        ),
    )


def _local_discovery(value):
    panels = [
        _summary(
            value,
            (
                "candidates_evaluated",
                "candidates_skipped_for_language_limit",
                "search_complete",
                "matched_model_count",
            ),
        )
    ]
    for index, model in enumerate(value.models):
        _, model_views = _local_model(model)
        panels.extend(
            replace(
                panel,
                id=f"local_{index}:" + panel.id,
                title=f"Local model {index} — " + panel.title,
            )
            for panel in model_views
        )
    if not value.models:
        panels.append(
            _table(
                "local_models",
                "No local model returned",
                ("returned_model_count",),
                ((0,),),
                "No model in this result is not proof that no local behavior exists; inspect search completeness and frequency thresholds.",
            )
        )
    return None, tuple(panels)


_ADAPTERS.update(
    {
        WfNetConversion: _wfnet,
        ModelDecomposition: _model_decomposition,
        ObjectModelConversion: _object_conversion,
        ObjectTypePetriNet: _object_type_projection,
        OCPNDecomposition: _ocpn_decomposition,
        EnhancedObjectCentricPetriNet: _enhanced_ocpn,
        LocalProcessModel: _local_model,
        LocalProcessModelDiscovery: _local_discovery,
    }
)


def model_result_view(value):
    """Return (primary model or None, model/evidence panels) for typed outputs."""
    adapter = (
        _configured_conversion
        if type(value) in _CONVERSIONS
        else _ADAPTERS.get(type(value))
    )
    if adapter is None:
        return None
    normalized = _decode(_encode(value), type(value))
    if normalized != value:
        raise ValueError("model result does not preserve its typed contract")
    return adapter(value)


__all__ = ("model_result_view",)
