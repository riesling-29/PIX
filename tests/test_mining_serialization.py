"""Public codec integration for real native mining results and typed requests.

These are storage/provenance checks, not algorithm equivalence claims. Small
fixtures keep the integration independent of each algorithm's oracle tests.
"""

from dataclasses import is_dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from runpy import run_path

import pytest

from pix._mining_registry import mining_schemas
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
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import (
    Arc,
    Marking,
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    PetriNet,
    Place,
    Transition,
    TypedPlace,
)
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.object_centric import (
    actions as oc_actions,
)
from pix.object_centric import (
    advanced_filtering as oc_advanced_filtering,
)
from pix.object_centric import (
    conformance as oc_conformance,
)
from pix.object_centric import (
    constraints as oc_constraints,
)
from pix.object_centric import (
    cube as oc_cube,
)
from pix.object_centric import (
    discovery as oc_discovery,
)
from pix.object_centric import (
    enrichment as oc_enrichment,
)
from pix.object_centric import (
    equivalent_ocel as oc_equivalent_ocel,
)
from pix.object_centric import (
    features as oc_features,
)
from pix.object_centric import (
    filter_predicates as oc_filter_predicates,
)
from pix.object_centric import (
    filtering as oc_filtering,
)
from pix.object_centric import (
    graph_comparison as oc_graph_comparison,
)
from pix.object_centric import (
    legacy_discovery as oc_legacy_discovery,
)
from pix.object_centric import (
    model_integration as oc_model_integration,
)
from pix.object_centric import (
    models as oc_models,
)
from pix.object_centric import (
    performance as oc_performance,
)
from pix.object_centric import (
    relations as oc_relations,
)
from pix.object_centric import (
    simulation as oc_simulation,
)
from pix.object_centric import (
    statistics as oc_statistics,
)
from pix.object_centric import (
    temporal_summary as oc_temporal_summary,
)
from pix.object_centric import (
    transformations as oc_transformations,
)
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)
from pix.results import result_from_json, result_json_bytes

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
DATE_LOOKING_TEXT = "2026-01-01T00:00:00.000000Z"


@pytest.fixture
def codec_case_log():
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{i}",
                tuple(
                    CaseEvent(
                        f"event-{i}-{j}",
                        (
                            CaseAttribute("concept:name", "string", label),
                            CaseAttribute(
                                "time:timestamp", "date", ORIGIN + timedelta(seconds=j)
                            ),
                            CaseAttribute("org:resource", "string", "worker"),
                            CaseAttribute("amount", "int", j + 1),
                            CaseAttribute("date-text", "string", DATE_LOOKING_TEXT),
                        ),
                    )
                    for j, label in enumerate("AB")
                ),
            )
            for i in range(2)
        )
    )


@pytest.fixture
def codec_case_net():
    return PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("p", "a"), Arc("a", "q"), Arc("q", "b"), Arc("b", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )


def _roundtrip(result):
    blob = result_json_bytes(result)
    restored = result_from_json(blob)
    assert restored == result, result.operator_id
    assert restored.computation_id == result.computation_id
    assert result_json_bytes(restored) == blob
    return restored


def _sacofa_result(log):
    query = privacy.TraceVariantPrivacySpec(("A", "B"), max_trace_length=2, epsilon=6.0)
    return sacofa.anonymize_sacofa(
        log, sacofa.SACOFASpec(query, sacofa.SACOFASemantics(("A", "B", "__OTHER__")))
    )


def _pripel_result(log):
    release = sacofa.sacofa_release(_sacofa_result(log))
    bounded = replace(
        release,
        variants=tuple(
            replace(row, count=min(2, row.count)) for row in release.variants
        ),
    )
    return pripel.reconstruct_pripel_context(
        log,
        pripel.PripelSpec(
            bounded, ORIGIN, ORIGIN + timedelta(seconds=10), max_target_traces=32
        ),
    )


def _retrieval_result(log):
    fitted = features.fit_features(log).value
    matrix = features.transform_features(log, fitted)
    return embedding_retrieval.retrieve_embedding_neighbors(
        matrix, matrix, embedding_retrieval.EmbeddingRetrievalSpec(k=1)
    )


def _interleavings_ocel_result(log):
    right = replace(
        log,
        traces=tuple(
            replace(
                trace,
                events=tuple(
                    replace(
                        event,
                        attributes=tuple(
                            replace(
                                attribute,
                                value=attribute.value + timedelta(microseconds=500_000),
                            )
                            if attribute.key == "time:timestamp"
                            else attribute
                            for attribute in event.attributes
                        ),
                    )
                    for event in trace.events
                ),
            )
            for trace in log.traces
        ),
    )
    found = interleavings.discover_interleavings(
        log,
        right,
        interleavings.InterleavingSpec(
            (interleavings.CaseLink("case-0", "case-0"),), include_boundaries=False
        ),
    )
    return interleavings_ocel.from_interleavings(log, right, found).evidence


CASE_FACTORIES = (
    (
        "bpmn_conversion",
        lambda log, net: bpmn_conversion.bpmn_to_petri_net(
            split_miner.discover_split_miner(log)
        ),
    ),
    (
        "dfg_conversion",
        lambda log, net: dfg_conversion.dfg_to_petri_net(discovery.discover_dfg(log)),
    ),
    ("evaluation", lambda log, net: evaluation.evaluate_model(log, net)),
    (
        "stream_adapters",
        lambda log, net: stream_adapters.case_log_stream(
            log, stream_adapters.CaseLogStreamSpec("codec", close_cases=True)
        ),
    ),
    ("transformations", lambda log, net: transformations.sort_case_log(log)),
    (
        "tree_reduction",
        lambda log, net: tree_reduction.fold_process_tree(
            ProcessTree(
                "sequence", children=(ProcessTree("tau"), ProcessTree("activity", "A"))
            )
        ),
    ),
    ("wfnet_conversion", lambda log, net: wfnet_conversion.wfnet_to_process_tree(net)),
    ("interleavings_ocel", lambda log, net: _interleavings_ocel_result(log)),
    (
        "interleavings",
        lambda log, net: interleavings.discover_interleavings(
            log,
            log,
            interleavings.InterleavingSpec(
                (interleavings.CaseLink("case-0", "case-1"),)
            ),
        ),
    ),
    ("label_splitting", lambda log, net: label_splitting.fit_label_splitting(log)),
    (
        "link_analysis",
        lambda log, net: link_analysis.discover_link_analysis(
            log,
            link_analysis.LinkAnalysisSpec(
                out_key="concept:name", in_key="concept:name"
            ),
        ),
    ),
    (
        "model_conversion",
        lambda log, net: model_conversion.tree_to_bpmn(
            inductive.discover_inductive(log)
        ),
    ),
    (
        "approximate_alignment",
        lambda log, net: approximate_alignment.align_tandem_repeats(log, net),
    ),
    ("backwards_replay", lambda log, net: backwards_replay.replay_backwards(log, net)),
    (
        "conformance_approximation",
        lambda log, net: conformance_approximation.approximate_conformance(log, net),
    ),
    (
        "context_discovery",
        lambda log, net: context_discovery.discover_activity_triples(log),
    ),
    ("correlation", lambda log, net: correlation.discover_correlation(log)),
    (
        "tree_alignment",
        lambda log, net: tree_alignment.align_process_tree_dp(
            log, inductive.discover_inductive(log).value
        ),
    ),
    ("embedding_retrieval", lambda log, net: _retrieval_result(log)),
    ("sacofa", lambda log, net: _sacofa_result(log)),
    ("pripel", lambda log, net: _pripel_result(log)),
    ("advanced", lambda log, net: advanced.cluster_cases(log)),
    (
        "advanced_precision",
        lambda log, net: advanced_precision.measure_dfg_precision(
            log,
            sequence_alignment.DFGAlignmentModel(
                ("A", "B"), (("A", "B"),), ("A",), ("B",)
            ),
        ),
    ),
    (
        "alignment_search",
        lambda log, net: alignment_search.align_state_equation_astar(log, net),
    ),
    ("alpha", lambda log, net: alpha.discover_alpha(log)),
    ("conformance", lambda log, net: conformance.measure_token_fitness(log, net)),
    (
        "decision_mining",
        lambda log, net: decision_mining.extract_decision_table(
            log, net, decision_mining.DecisionTableSpec(())
        ),
    ),
    ("declarative", lambda log, net: declarative.discover_declare(log)),
    (
        "declarative_simulation",
        lambda log, net: declarative_simulation.generate_declare_language(
            declarative.DeclareModel(("A", "B"), ()),
            declarative_simulation.DeclareLanguageSpec(max_events=2),
        ),
    ),
    (
        "decomposed_alignment",
        lambda log, net: decomposed_alignment.align_decomposed(log, net),
    ),
    (
        "dfg_filtering",
        lambda log, net: dfg_filtering.filter_dfg(discovery.discover_dfg(log)),
    ),
    ("discovery", lambda log, net: discovery.discover_dfg(log)),
    (
        "embeddings",
        lambda log, net: embeddings.fit_embeddings(
            log, embeddings.EmbeddingSpec(dimensions=2, epochs=1, negative_samples=1)
        ),
    ),
    ("extended_discovery", lambda log, net: extended_discovery.discover_regions(log)),
    ("features", lambda log, net: features.fit_features(log)),
    (
        "filtering",
        lambda log, net: filtering.sample_cases(log, filtering.CaseSampleSpec(1)),
    ),
    (
        "genetic_miner",
        lambda log, net: genetic_miner.discover_genetic(
            log, genetic_miner.GeneticMinerSpec(generations=1)
        ),
    ),
    ("heuristics", lambda log, net: heuristics.discover_heuristics(log)),
    (
        "heuristics_conversion",
        lambda log, net: heuristics_conversion.heuristics_to_petri_net(
            heuristics.discover_heuristics(log)
        ),
    ),
    ("inductive", lambda log, net: inductive.discover_inductive(log)),
    (
        "lifecycle",
        lambda log, net: lifecycle.derive_adjacent_intervals(
            log,
            lifecycle.AdjacentIntervalSpec(
                None, endpoint_policy="completion_to_completion"
            ),
        ),
    ),
    ("model_analysis", lambda log, net: model_analysis.model_invariants(net)),
    (
        "marking_equation",
        lambda log, net: marking_equation.synchronous_product(
            net, marking_equation.SynchronousProductSpec(("A", "B"))
        ),
    ),
    (
        "model_discovery",
        lambda log, net: model_discovery.discover_model_footprints(net),
    ),
    ("organization", lambda log, net: organization.discover_social_network(log)),
    (
        "online_alignment",
        lambda log, net: online_alignment.build_online_alignment_proxy(
            online_alignment.OnlineAlignmentSpec(
                net,
                streaming.StreamingSpec("codec-online"),
                proxy_transition_sequences=(("a", "b"),),
            )
        ),
    ),
    (
        "pn_language_alignment",
        lambda log, net: pn_language_alignment.bounded_petri_net_anti_alignment(
            log, net, pn_language_alignment.BoundedPetriNetLanguageSpec(2)
        ),
    ),
    ("powl", lambda log, net: powl.discover_powl(log)),
    (
        "privacy",
        lambda log, net: privacy.anonymize_trace_variants(
            log, privacy.TraceVariantPrivacySpec(("A", "B"), max_trace_length=2)
        ),
    ),
    (
        "sequence_alignment",
        lambda log, net: sequence_alignment.align_log_to_log(log, log),
    ),
    ("simulation", lambda log, net: simulation.playout_petri_net(net)),
    ("split_miner", lambda log, net: split_miner.discover_split_miner(log)),
    ("statistics", lambda log, net: statistics.measure_attributes(log)),
    (
        "streaming",
        lambda log, net: streaming.CaseStream(
            streaming.StreamingSpec("codec")
        ).snapshot(),
    ),
    (
        "transformer_embeddings",
        lambda log, net: transformer_embeddings.transformer_embeddings(
            log,
            transformer_embeddings.TransformerEmbeddingSpec(
                "__missing_codec_checkpoint__"
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    "module,factory", CASE_FACTORIES, ids=[x[0] for x in CASE_FACTORIES]
)
def test_case_module_public_result_codec(
    module, factory, codec_case_log, codec_case_net
):
    result = factory(codec_case_log, codec_case_net)
    assert type(result.spec).__module__ == f"pix.case_centric.{module}"
    _roundtrip(result)


@pytest.fixture
def codec_object_log():
    return OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("T"),),
        events=(
            Event("e1", "A", ORIGIN),
            Event("e2", "B", ORIGIN + timedelta(seconds=1)),
        ),
        objects=(Object("o", "T"),),
        e2o=(E2O("e1", "o", "flow"), E2O("e2", "o", "flow")),
    )


@pytest.fixture
def codec_object_net():
    return ObjectCentricPetriNet(
        (TypedPlace("p", "T"), TypedPlace("q", "T"), TypedPlace("r", "T")),
        (Transition("a", "A"), Transition("b", "B")),
        (
            ObjectArc("p", "a"),
            ObjectArc("a", "q"),
            ObjectArc("q", "b"),
            ObjectArc("b", "r"),
        ),
        ObjectMarking((ObjectToken("p", "o"),)),
        ObjectMarking((ObjectToken("r", "o"),)),
        (("o", "T"),),
    )


OBJECT_FACTORIES = (
    (
        "advanced_filtering",
        lambda log, net: oc_advanced_filtering.sample_ocel(
            log, oc_advanced_filtering.OCSamplingSpec(1)
        ),
    ),
    ("cube", lambda log, net: oc_cube.unfold(log, oc_cube.UnfoldSpec("A", "T"))),
    ("transformations", lambda log, net: oc_transformations.deduplicate_ocel(log)),
    ("enrichment", lambda log, net: oc_enrichment.mark_lifecycle_qualifiers(log)),
    (
        "equivalent_ocel",
        lambda log, net: oc_equivalent_ocel.cluster_equivalent_ocel(
            log, oc_equivalent_ocel.EquivalentOCELSpec("T")
        ),
    ),
    (
        "filter_predicates",
        lambda log, net: oc_filter_predicates.evaluate_filter_predicates(
            log,
            oc_filter_predicates.OCFilterPredicateSpec(
                "object_lifecycle", lifecycle="start", activity="A"
            ),
        ),
    ),
    (
        "legacy_discovery",
        lambda log, net: oc_legacy_discovery.discover_ocpn_by_type(
            log,
            oc_legacy_discovery.OCPNByTypeDiscoverySpec(
                ("T",), "observed_range", "unique_activity"
            ),
        ),
    ),
    ("model_integration", lambda log, net: oc_model_integration.decompose_ocpn(net)),
    ("temporal_summary", lambda log, net: oc_temporal_summary.temporal_summary(log)),
    ("graph_comparison", lambda log, net: oc_graph_comparison.compare_ocdfgs(log, log)),
    (
        "actions",
        lambda log, net: oc_actions.schedule_actions(
            (oc_actions.ActionCandidate("act", 1),),
            oc_actions.ActionScheduleSpec(ORIGIN),
        ),
    ),
    (
        "conformance",
        lambda log, net: oc_conformance.replay_object_log(
            log, net, oc_conformance.ObjectReplaySpec(("T",))
        ),
    ),
    (
        "constraints",
        lambda log, net: oc_constraints.measure_rule_metric(
            log, oc_constraints.ObjectRuleMetricSpec("T", "A", "existence")
        ),
    ),
    (
        "discovery",
        lambda log, net: oc_discovery.discover_saw_net(
            log,
            oc_discovery.SAWDiscoverySpec(
                OCPNDiscoverySpec(("T",), "observed_range", "unique_activity")
            ),
        ),
    ),
    ("features", lambda log, net: oc_features.extract_object_features(log)),
    ("filtering", lambda log, net: oc_filtering.filter_ocel(log)),
    ("models", lambda log, net: oc_models.project_ocpn(net)),
    ("performance", lambda log, net: oc_performance.measure_performance(log)),
    ("relations", lambda log, net: oc_relations.discover_object_graph(log)),
    (
        "simulation",
        lambda log, net: oc_simulation.playout_ocpn(
            net, oc_simulation.ObjectPlayoutSpec(samples=1)
        ),
    ),
    ("statistics", lambda log, net: oc_statistics.object_statistics(log)),
)


@pytest.mark.parametrize(
    "module,factory", OBJECT_FACTORIES, ids=[x[0] for x in OBJECT_FACTORIES]
)
def test_object_module_public_result_codec(
    module, factory, codec_object_log, codec_object_net
):
    result = factory(codec_object_log, codec_object_net)
    assert type(result.spec).__module__ == f"pix.object_centric.{module}"
    _roundtrip(result)


def test_registry_only_allows_frozen_native_contracts():
    schemas = mining_schemas()
    assert schemas
    for operator, schema in schemas.items():
        assert operator.startswith(("pix.case_centric.", "pix.object_centric."))
        assert isinstance(schema, tuple) and len(schema) == 3
        kind, request, payload = schema
        assert isinstance(kind, str) and kind
        for contract in (request, payload):
            assert isinstance(contract, type) and is_dataclass(contract)
            assert contract.__dataclass_params__.frozen


def test_every_registered_native_module_has_a_live_codec_representative():
    represented = {f"pix.case_centric.{name}" for name, _ in CASE_FACTORIES}
    represented.update(f"pix.object_centric.{name}" for name, _ in OBJECT_FACTORIES)
    review = run_path(
        str(Path(__file__).resolve().parents[1] / "examples/models_w4_review.py")
    )
    for result in review["build_review_cases"]().values():
        _roundtrip(result)
        represented.add(type(result.spec).__module__)
    registered = {
        request.__module__
        for _, request, _ in mining_schemas().values()
        if request.__module__.startswith(("pix.case_centric.", "pix.object_centric."))
    }
    assert registered <= represented


@pytest.mark.parametrize(
    "factory",
    (
        lambda log: statistics.measure_numeric_attribute(
            log, statistics.NumericAttributeSpec("amount", grid=(0, 1), bandwidth=1)
        ),
        lambda log: embeddings.fit_embeddings(
            log,
            embeddings.EmbeddingSpec(
                dimensions=2, epochs=1, negative_samples=1, learning_rate=1
            ),
        ),
        lambda log: genetic_miner.discover_genetic(
            log,
            genetic_miner.GeneticMinerSpec(
                generations=1, crossover_rate=1, mutation_rate=0
            ),
        ),
        lambda log: privacy.anonymize_trace_variants(
            log,
            privacy.TraceVariantPrivacySpec(("A", "B"), max_trace_length=2, epsilon=1),
        ),
    ),
    ids=(
        "numeric-grid-bandwidth",
        "embedding-learning-rate",
        "genetic-probabilities",
        "privacy-epsilon",
    ),
)
def test_integer_accepted_real_options_preserve_request_identity(
    factory, codec_case_log
):
    _roundtrip(factory(codec_case_log))


def test_partial_and_unavailable_are_persistable(codec_case_log, codec_case_net):
    stream = streaming.CaseStream(streaming.StreamingSpec("partial-codec"))
    stream.ingest(streaming.StreamEvent("case", "event", 0, "A", ORIGIN))
    partial = stream.snapshot()
    assert partial.status is ComputeStatus.PARTIAL
    _roundtrip(partial)
    unavailable = advanced.cluster_cases(
        codec_case_log, advanced.CaseClusteringSpec(max_edit_cells=1)
    )
    assert unavailable.status is ComputeStatus.UNAVAILABLE
    _roundtrip(unavailable)


@pytest.mark.parametrize(
    "key,typed_value",
    (
        ("date-text", CaseAttribute("expected", "string", DATE_LOOKING_TEXT)),
        ("time:timestamp", CaseAttribute("expected", "date", ORIGIN)),
        ("amount", CaseAttribute("expected", "int", 1)),
    ),
    ids=("iso-looking-string", "actual-date", "integer"),
)
def test_case_attribute_conditions_preserve_recorded_types(
    codec_case_log, key, typed_value
):
    result = filtering.filter_case_log(
        codec_case_log,
        filtering.CaseFilterSpec(
            kind="event_attribute",
            attribute=filtering.AttributeCondition(key, values=(typed_value,)),
        ),
    )
    assert result.status is ComputeStatus.COMPUTED
    restored = _roundtrip(result)
    assert restored.spec.attribute.values[0].type == typed_value.type
    assert type(restored.spec.attribute.values[0].value) is type(typed_value.value)


def test_object_attribute_and_feature_cells_distinguish_dates_from_text():
    declarations = (
        Attribute("text", ValueType.STRING),
        Attribute("time", ValueType.TIME),
        Attribute("integer", ValueType.INTEGER),
        Attribute("boolean", ValueType.BOOLEAN),
    )
    values = (
        ("text", DATE_LOOKING_TEXT),
        ("time", ORIGIN),
        ("integer", 1),
        ("boolean", True),
    )
    log = OCEL(
        event_types=(EventType("A", declarations),),
        object_types=(ObjectType("T", declarations),),
        events=(
            Event(
                "e", "A", ORIGIN, tuple(EventAttr(key, value) for key, value in values)
            ),
        ),
        objects=(
            Object(
                "o", "T", tuple(ObjectAttr(key, value, ORIGIN) for key, value in values)
            ),
        ),
        e2o=(E2O("e", "o", "flow"),),
    )
    as_of = _roundtrip(
        oc_relations.object_attributes_as_of(
            log, oc_relations.AttributeAsOfSpec(ORIGIN)
        )
    )
    assert as_of.status is ComputeStatus.COMPUTED
    table = _roundtrip(
        oc_features.extract_object_features(
            log,
            oc_features.ObjectFeatureSpec(
                tuple(
                    oc_features.ObjectFeature("characteristic_value", attribute=key)
                    for key, _ in values
                )
            ),
        )
    )
    cells = table.value.rows[0].cells
    assert tuple(cell.kind for cell in cells) == ("text", "time", "integer", "boolean")
    assert cells[0].text == DATE_LOOKING_TEXT
    assert cells[1].time == ORIGIN and isinstance(cells[1].time, datetime)
    assert type(cells[2].integer) is int and type(cells[3].boolean) is bool


@pytest.fixture
def codec_decision_fit(codec_case_net):
    net = replace(
        codec_case_net,
        transitions=(*codec_case_net.transitions, Transition("c", "C")),
        arcs=(*codec_case_net.arcs, Arc("q", "c"), Arc("c", "r")),
    )
    log = CaseLog(
        tuple(
            CaseTrace(
                case_id,
                (
                    CaseEvent(
                        f"{case_id}-a",
                        (
                            CaseAttribute("concept:name", "string", "A"),
                            CaseAttribute("amount", "int", amount),
                        ),
                    ),
                    CaseEvent(
                        f"{case_id}-branch",
                        (CaseAttribute("concept:name", "string", branch),),
                    ),
                ),
            )
            for case_id, amount, branch in (("low", 1, "B"), ("high", 9, "C"))
        )
    )
    table = decision_mining.extract_decision_table(
        log,
        net,
        decision_mining.DecisionTableSpec(
            (decision_mining.DecisionFeatureSpec("amount", "amount"),)
        ),
    )
    assert table.status is ComputeStatus.COMPUTED
    return decision_mining.mine_data_petri_net(table, net)


def test_mined_data_petri_net_result_codec(codec_decision_fit):
    restored = _roundtrip(codec_decision_fit)
    assert restored.operator_id == "pix.case_centric.mine_data_petri_net"
    assert restored.status is ComputeStatus.COMPUTED
    assert restored.value.training_observation_count == 2


def test_data_guard_result_codec_has_true_false_and_unknown(codec_decision_fit):
    model = codec_decision_fit.value.model
    for amount, expected in ((1, "true"), (9, "false"), (None, "unknown")):
        result = decision_mining.evaluate_data_guards(
            model,
            Marking((("q", 1),)),
            "b",
            (decision_mining.DecisionFeatureValue("amount", amount),),
        )
        restored = _roundtrip(result)
        assert restored.operator_id == "pix.case_centric.evaluate_data_guards"
        assert restored.value.structurally_enabled
        assert restored.value.guard_state == expected


def test_extended_marking_equation_result_codec(codec_case_net):
    result = marking_equation.extended_marking_equation(
        codec_case_net,
        marking_equation.ExtendedMarkingEquationSpec(("A", "B"), split_indices=(1,)),
    )
    restored = _roundtrip(result)
    assert restored.operator_id == "pix.case_centric.extended_marking_equation"
    assert restored.status is ComputeStatus.COMPUTED
    assert restored.value.result.objective == (0, 1)
    assert restored.value.split_indices == (1,)
