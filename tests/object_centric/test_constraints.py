"""Independent closed-log truth tables and object/activation population oracles."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.contracts.result import ComputeStatus
from pix.object_centric.constraints import (
    AAEdge,
    ActivityNode,
    AOAEdge,
    ConstraintGraphSpec,
    ControlFlowEdge,
    E2OQualifierSpec,
    FormulaNode,
    O2OQualifierSpec,
    OAEdge,
    ObjectRelationEdge,
    ObjectRuleMetricSpec,
    ObjectTypeNode,
    PerformanceEdge,
    PerformanceObservation,
    evaluate_constraint_graph,
    evaluate_e2o_qualifiers,
    evaluate_o2o_qualifiers,
    measure_rule_metric,
    performance_observations,
)
from pix.object_centric.relations import OCELScalar
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def log_for(*traces):
    events, objects, e2o = [], [], []
    for index, trace in enumerate(traces):
        object_id = f"o{index}"
        objects.append(Object(object_id, "order"))
        for position, label in enumerate(trace):
            event_id = f"e{index}-{position}"
            events.append(Event(event_id, label, ORIGIN + timedelta(seconds=position)))
            e2o.extend(
                (E2O(event_id, object_id, "flow"), E2O(event_id, object_id, "audit"))
            )
    return OCEL(
        (EventType("A"), EventType("B"), EventType("X")),
        (ObjectType("order"),),
        tuple(events),
        tuple(objects),
        tuple(e2o),
        (),
    )


def metric(log, relation, **kwargs):
    target = (
        None
        if relation
        in (
            "existence",
            "non_existence",
            "absent",
            "present",
            "singular",
            "multiple",
            "cardinality",
        )
        else "B"
    )
    result = measure_rule_metric(
        log, ObjectRuleMetricSpec("order", "A", relation, target, **kwargs)
    )
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


@pytest.mark.parametrize(
    "relation,predicate",
    (
        ("existence", lambda a, b: a),
        ("non_existence", lambda a, b: not a),
        ("coexistence", lambda a, b: a == b),
        ("exclusive", lambda a, b: not (a and b)),
        ("choice", lambda a, b: a or b),
        ("xor_choice", lambda a, b: a != b),
    ),
)
def test_exhaustive_boolean_truth_oracle_includes_isolated_objects(relation, predicate):
    traces = ((), ("A",), ("B",), ("A", "B"))
    result = metric(log_for(*traces), relation)
    expected = tuple(predicate("A" in trace, "B" in trace) for trace in traces)
    assert tuple(row.satisfied for row in result.witnesses) == expected
    assert (result.numerator, result.denominator, result.metric) == (
        sum(expected),
        4,
        sum(expected) / 4,
    )


@pytest.mark.parametrize(
    "relation", ("followed_by", "directly_followed_by", "precedence", "block")
)
def test_all_small_traces_against_quantified_position_oracle(relation):
    traces = tuple(
        trace
        for length in range(5)
        for trace in product(("A", "B", "X"), repeat=length)
    )
    result = metric(log_for(*traces), relation)
    by_id = {row.object_id: row.satisfied for row in result.witnesses}
    for i, trace in enumerate(traces):
        apos = [j for j, label in enumerate(trace) if label == "A"]
        bpos = [j for j, label in enumerate(trace) if label == "B"]
        if relation == "followed_by":
            expected = all(any(b > a for b in bpos) for a in apos)
        elif relation == "directly_followed_by":
            expected = all(a + 1 in bpos for a in apos)
        elif relation == "precedence":
            expected = all(any(a < b for a in apos) for b in bpos)
        else:
            expected = all(not any(b > a for b in bpos) for a in apos)
        assert by_id[f"o{i}"] == expected, (trace, relation)


@pytest.mark.parametrize(
    "relation", ("followed_by", "directly_followed_by", "precedence", "block")
)
def test_first_occurrence_explicit_legacy_semantics(relation):
    traces = tuple(
        trace
        for length in range(5)
        for trace in product(("A", "B", "X"), repeat=length)
    )
    result = metric(log_for(*traces), relation, occurrence_profile="first_occurrence")
    by_id = {row.object_id: row.satisfied for row in result.witnesses}
    for i, trace in enumerate(traces):
        a = next((j for j, label in enumerate(trace) if label == "A"), None)
        b = next((j for j, label in enumerate(trace) if label == "B"), None)
        if relation == "precedence":
            expected = b is None or (a is not None and a < b)
        elif relation == "block":
            expected = a is None or b is None or b < a
        elif relation == "followed_by":
            expected = a is None or (b is not None and a < b)
        else:
            expected = a is None or (b is not None and a + 1 == b)
        assert by_id[f"o{i}"] == expected, (trace, relation)


def test_profiles_diverge_on_late_activation_and_early_target():
    log = log_for("ABA", "BABA", "X", "")
    every = metric(log, "followed_by")
    first = metric(log, "followed_by", occurrence_profile="first_occurrence")
    assert (every.numerator, every.denominator) == (2, 4)
    assert (first.numerator, first.denominator) == (3, 4)
    activated = metric(log, "followed_by", population="activations")
    assert (activated.numerator, activated.denominator) == (2, 4)
    assert all(row.activation_event_id for row in activated.witnesses)
    assert (
        metric(log_for("", "X"), "followed_by", population="activations").metric is None
    )
    assert metric(log_for("", "X"), "followed_by").metric == 1


def test_same_activity_is_strictly_later_event_every_activation():
    log = log_for("AA")
    spec = ObjectRuleMetricSpec(
        "order", "A", "followed_by", "A", population="activations"
    )
    every = measure_rule_metric(log, spec).value
    assert [row.satisfied for row in every.witnesses] == [True, False]
    first = measure_rule_metric(
        log, replace(spec, occurrence_profile="first_occurrence")
    ).value
    assert first.numerator == 0 and first.denominator == 1


def test_no_objects_no_fake_zero_support():
    result = metric(log_for(), "existence")
    assert (result.numerator, result.denominator, result.metric) == (0, 0, None)


def test_selected_roles_do_not_multiply_participation_or_activations():
    log = log_for("AB", "AB")
    all_roles = metric(log, "followed_by", population="activations")
    flow = metric(log, "followed_by", population="activations", qualifiers=("flow",))
    assert all_roles.witnesses == flow.witnesses
    assert all_roles.denominator == 2
    assert metric(log, "existence", qualifiers=()).numerator == 0


def test_object_participation_population_is_events_and_counts_unique_objects():
    base = log_for("AA", "A")
    log = replace(
        base,
        e2o=(
            E2O("e0-0", "o0", "flow"),
            E2O("e0-0", "o0", "audit"),
            E2O("e0-0", "o1", "flow"),
            E2O("e0-1", "o1", "flow"),
        ),
    )
    for relation, numerator in (
        ("absent", 1),
        ("present", 2),
        ("singular", 1),
        ("multiple", 1),
    ):
        value = metric(log, relation, population="events")
        assert (value.numerator, value.denominator) == (numerator, 3)
    value = metric(log, "cardinality", population="events", min_count=1, max_count=2)
    assert value.numerator == 2
    assert (
        metric(log, "multiple", population="events", qualifiers=("audit",)).numerator
        == 0
    )


def test_ties_rejected_only_for_ordered_relations():
    base = log_for("AB")
    log = replace(
        base, events=tuple(replace(event, time=ORIGIN) for event in base.events)
    )
    query = ObjectRuleMetricSpec("order", "A", "followed_by", "B")
    result = measure_rule_metric(log, query)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "ambiguous_event_order"
    result = measure_rule_metric(log, replace(query, tie_policy="event_id"))
    assert result.value.metric == 1
    assert result.issues[0].code == "event_id_order_assumption"
    assert metric(log, "existence").metric == 1


@pytest.mark.parametrize(
    "operator,threshold,expected",
    (
        ("<", 0.5, False),
        ("<=", 0.5, True),
        (">", 0.5, False),
        (">=", 0.5, True),
        ("=", 0.5, True),
        ("==", 0.5, True),
        ("!=", 0.5, False),
        ("<=", 0.75, True),
        ("<=", 0.25, False),
    ),
)
def test_graph_comparator_boundary_including_upstream_less_equal_counterexample(
    operator, threshold, expected
):
    spec = ConstraintGraphSpec(
        oa_edges=(
            OAEdge(
                "presence",
                ObjectTypeNode("order"),
                ActivityNode("A"),
                "exist",
                operator,
                threshold,
            ),
        )
    )
    result = evaluate_constraint_graph(log_for("A", ""), spec)
    (row,) = result.value.edges
    assert row.metric == 0.5 and row.condition_met is expected


def test_graph_all_six_edge_families_and_exact_population():
    a, b, order = ActivityNode("A"), ActivityNode("B"), ObjectTypeNode("order")
    formula = FormulaNode("waiting", "<=", 6, "mean", unit="microseconds")
    spec = ConstraintGraphSpec(
        oa_edges=(OAEdge("oa", order, a, "exist", ">=", 0.5),),
        aa_edges=(AAEdge("aa", a, b, formula),),
        aoa_edges=(AOAEdge("aoa", a, order, b, "directlyCause", "=", 1),),
        cf_edges=(ControlFlowEdge("cf", a, b, "order", "causal", 0.9),),
        object_edges=(ObjectRelationEdge("or", order, a, "singular", 0.9),),
        performance_edges=(PerformanceEdge("perf", formula, a),),
        observations=(
            PerformanceObservation(
                "s1", "A", "waiting", 2, "microseconds", source_computation_id="parent"
            ),
            PerformanceObservation(
                "s2", "A", "waiting", 10, "microseconds", source_computation_id="parent"
            ),
            PerformanceObservation("wrong_unit", "A", "waiting", 900, "seconds"),
        ),
    )
    result = evaluate_constraint_graph(log_for("AB", ""), spec)
    assert result.status is ComputeStatus.COMPUTED
    rows = {row.family: row for row in result.value.edges}
    assert set(rows) == {"OA", "AA", "AOA", "CF", "OR", "PERF"}
    assert (rows["AOA"].numerator, rows["AOA"].denominator) == (2, 2)
    assert (rows["CF"].numerator, rows["CF"].denominator) == (1, 1)
    assert (rows["PERF"].metric, rows["PERF"].denominator) == (6, 2)
    assert rows["AA"].metric == 6
    assert all(row.condition_met for row in result.value.edges)
    assert result.parent_computation_ids == ("parent",)
    different = replace(
        spec,
        observations=(replace(spec.observations[0], value=3),) + spec.observations[1:],
    )
    assert (
        evaluate_constraint_graph(log_for("AB", ""), different).computation_id
        != result.computation_id
    )


@pytest.mark.parametrize(
    "aggregation,expected",
    (("mean", 5), ("min", 2), ("max", 10), ("sum", 15), ("median", 3), ("count", 3)),
)
def test_performance_aggregations_and_empty_denominator(aggregation, expected):
    formula = FormulaNode("flow", "=", expected, aggregation, "order", "microseconds")
    spec = ConstraintGraphSpec(
        performance_edges=(PerformanceEdge("p", formula, ActivityNode("A")),),
        observations=tuple(
            PerformanceObservation(str(i), "A", "flow", v, "microseconds", "order")
            for i, v in enumerate((2, 3, 10))
        ),
    )
    result = evaluate_constraint_graph(log_for(), spec).value
    assert result.edges[0].metric == expected
    assert result.triggered_edge_ids == ("p",)
    empty = evaluate_constraint_graph(log_for(), replace(spec, observations=())).value
    assert empty.edges[0].metric is None and empty.edges[0].condition_met is None
    assert empty.unknown_edge_ids == ("p",)


def test_cf_strengths_do_not_claim_causality_and_preserve_different_denominators():
    a, b = ActivityNode("A"), ActivityNode("B")
    spec = ConstraintGraphSpec(
        cf_edges=tuple(
            ControlFlowEdge(label, a, a if label == "skip" else b, "order", label, 0)
            for label in ("causal", "concur", "choice", "skip")
        )
    )
    rows = {
        row.edge_id: row
        for row in evaluate_constraint_graph(
            log_for("AB", "BA", "A", "B", ""), spec
        ).value.edges
    }
    assert (rows["causal"].numerator, rows["causal"].denominator) == (1, 2)
    assert (rows["concur"].numerator, rows["concur"].denominator) == (2, 2)
    assert (rows["choice"].numerator, rows["choice"].denominator) == (2, 6)
    assert (rows["skip"].numerator, rows["skip"].denominator) == (2, 5)
    assert all(
        row.metric is None
        for row in evaluate_constraint_graph(log_for(), spec).value.edges
    )


@pytest.mark.parametrize("aggregation", ("mean", "median", "sum"))
def test_large_finite_samples_do_not_overflow_intermediate_aggregate(aggregation):
    formula = FormulaNode("flow", "=", 10**308, aggregation)
    spec = ConstraintGraphSpec(
        performance_edges=(PerformanceEdge("p", formula, ActivityNode("A")),),
        observations=(
            PerformanceObservation("a", "A", "flow", 1e308, "microseconds"),
            PerformanceObservation("b", "A", "flow", 1e308, "microseconds"),
        ),
    )
    result = evaluate_constraint_graph(log_for(), spec)
    assert result.status is ComputeStatus.COMPUTED
    value = result.value.edges[0].metric
    assert value == (int(1e308) * 2 if aggregation == "sum" else int(1e308))


def test_native_performance_bridge_keeps_unknowns_and_definition_provenance():
    from pix.object_centric.performance import OCPerformanceSpec, measure_performance

    log = log_for("AB")
    performance = measure_performance(log, OCPerformanceSpec(metrics=("flow",)))
    observations = performance_observations(log, performance)
    assert len(observations) == 2
    assert [row.activity for row in observations] == ["A", "B"]
    assert observations[0].value is None and observations[0].reason
    assert observations[1].value == 1_000_000
    assert all(
        row.source_computation_id == performance.computation_id for row in observations
    )
    with pytest.raises(ValueError):
        performance_observations(log_for("BA"), performance)
    non_event = measure_performance(
        log, OCPerformanceSpec(metrics=("activity_frequency",), object_type="order")
    )
    with pytest.raises(ValueError, match="event-anchored"):
        performance_observations(log, non_event)


def test_incomplete_performance_population_is_unknown_unless_explicit_known_only():
    formula = FormulaNode("flow", "<", 4)
    observations = (
        PerformanceObservation("known", "A", "flow", 3, "microseconds"),
        PerformanceObservation(
            "unknown", "A", "flow", None, "microseconds", reason="missing_predecessor"
        ),
    )
    spec = ConstraintGraphSpec(
        performance_edges=(PerformanceEdge("p", formula, ActivityNode("A")),),
        observations=observations,
    )
    result = evaluate_constraint_graph(log_for(), spec)
    assert result.status is ComputeStatus.PARTIAL
    row = result.value.edges[0]
    assert row.metric is None and row.condition_met is None and row.unknown_count == 1
    known_spec = replace(
        spec,
        performance_edges=(
            PerformanceEdge(
                "p", replace(formula, missing_policy="known_only"), ActivityNode("A")
            ),
        ),
    )
    result = evaluate_constraint_graph(log_for(), known_spec)
    assert result.status is ComputeStatus.PARTIAL
    row = result.value.edges[0]
    assert (
        row.metric == 3
        and row.denominator == 1
        and row.unknown_count == 1
        and row.condition_met is True
    )


def test_support_comparison_uses_exact_counts_not_rounded_display_ratio():
    # binary float 1/3 is slightly LESS than mathematical 1/3, so exact support
    # is greater, despite the displayed float having the same Python value.
    edge = OAEdge("p", ObjectTypeNode("order"), ActivityNode("A"), "exist", ">", 1 / 3)
    row = evaluate_constraint_graph(
        log_for("A", "", ""), ConstraintGraphSpec(oa_edges=(edge,))
    ).value.edges[0]
    assert row.metric == 1 / 3 and row.condition_met is True


def test_graph_keeps_known_results_with_ambiguous_order_row():
    base = log_for("AB")
    log = replace(
        base, events=tuple(replace(event, time=ORIGIN) for event in base.events)
    )
    a, b, order = ActivityNode("A"), ActivityNode("B"), ObjectTypeNode("order")
    spec = ConstraintGraphSpec(
        oa_edges=(OAEdge("known", order, a, "exist", "=", 1),),
        aoa_edges=(AOAEdge("unknown", a, order, b, "cause", "=", 1),),
    )
    result = evaluate_constraint_graph(log, spec)
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.triggered_edge_ids == ("known",)
    assert result.value.unknown_edge_ids == ("unknown",)


def qualifier_log():
    return OCEL(
        (EventType("A"),),
        (
            ObjectType(
                "order",
                (
                    Attribute("state", ValueType.STRING),
                    Attribute("flag", ValueType.BOOLEAN),
                ),
            ),
            ObjectType("item"),
        ),
        (
            Event("a", "A", ORIGIN + timedelta(seconds=2)),
            Event("b", "A", ORIGIN + timedelta(seconds=4)),
        ),
        (
            Object(
                "o",
                "order",
                (
                    ObjectAttr("state", "open", ORIGIN),
                    ObjectAttr("state", "closed", ORIGIN + timedelta(seconds=3)),
                    ObjectAttr("flag", True, ORIGIN),
                ),
            ),
            Object("missing", "order"),
            Object("i", "item"),
        ),
        (
            E2O("a", "o", "owner"),
            E2O("a", "o", "audit"),
            E2O("a", "i", "item"),
            E2O("a", "missing", "owner"),
            E2O("b", "o", "owner"),
            E2O("b", "i", "item"),
        ),
        (O2O("o", "i", "contains"), O2O("o", "i", "audit")),
    )


def test_e2o_event_asof_never_uses_future_assignment_missing_is_unknown():
    log = qualifier_log()
    spec = E2OQualifierSpec(
        "A", "order", "owner", "state", (OCELScalar("string", text_value="open"),)
    )
    result = evaluate_e2o_qualifiers(log, spec).value
    assert (
        result.population,
        result.allowed_count,
        result.forbidden_count,
        result.unknown_count,
    ) == (3, 1, 1, 1)
    assert result.known_allowed_fraction == 0.5
    observed = [row for row in result.witnesses if row.source_object_id == "o"]
    assert [row.value.text_value for row in observed] == ["open", "closed"]
    latest = evaluate_e2o_qualifiers(
        log, replace(spec, attribute_profile="latest_observed")
    ).value
    assert (latest.allowed_count, latest.forbidden_count, latest.unknown_count) == (
        0,
        2,
        1,
    )
    assert latest.profile == "latest_observed"


def test_typed_attribute_permission_does_not_confuse_true_and_one_or_zero_and_missing():
    spec = E2OQualifierSpec(
        "A", "order", "owner", "flag", (OCELScalar("integer", integer_value=1),)
    )
    result = evaluate_e2o_qualifiers(qualifier_log(), spec).value
    assert result.allowed_count == 0 and result.forbidden_count == 2
    typed = replace(spec, permitted_values=(OCELScalar("boolean", boolean_value=True),))
    assert evaluate_e2o_qualifiers(qualifier_log(), typed).value.allowed_count == 2
    none = replace(spec, qualifier="unobserved")
    assert (
        evaluate_e2o_qualifiers(qualifier_log(), none).value.known_allowed_fraction
        is None
    )


def test_o2o_multi_roles_directed_relation_and_missing_pair():
    spec = O2OQualifierSpec("A", "order", "item", ("contains",))
    result = evaluate_o2o_qualifiers(qualifier_log(), spec).value
    assert result.population == 3  # duplicate E2O role does not multiply o->i
    assert result.allowed_count == 0 and result.forbidden_count == 3
    any_allowed = evaluate_o2o_qualifiers(
        qualifier_log(), replace(spec, qualifier_policy="any")
    ).value
    assert any_allowed.allowed_count == 2 and any_allowed.forbidden_count == 1
    both_allowed = evaluate_o2o_qualifiers(
        qualifier_log(), replace(spec, allowed_qualifiers=("audit", "contains"))
    ).value
    assert both_allowed.allowed_count == 2
    reverse = replace(
        spec, source_type="item", target_type="order", qualifier_policy="any"
    )
    assert evaluate_o2o_qualifiers(qualifier_log(), reverse).value.allowed_count == 0


def test_unknown_type_is_not_zero_and_missing_activity_is_empty_population():
    spec = ObjectRuleMetricSpec("unknown", "A", "existence")
    assert measure_rule_metric(log_for("A"), spec).status is ComputeStatus.UNAVAILABLE
    assert metric(log_for("X"), "absent", population="events").metric is None


@pytest.mark.parametrize(
    "kwargs",
    (
        {"population": "activations"},
        {"min_count": True},
        {"max_count": -1},
        {"target": "B"},
        {"occurrence_profile": "any"},
        {"qualifiers": ["flow"]},
    ),
)
def test_invalid_contracts_fail_explicitly(kwargs):
    with pytest.raises((ValueError, TypeError)):
        ObjectRuleMetricSpec("order", "A", "existence", **kwargs)


def test_immutable_graph_and_spec_reject_undefined_labels_and_duplicate_ids():
    a, order = ActivityNode("A"), ObjectTypeNode("order")
    with pytest.raises(ValueError):
        OAEdge("unknown", order, a, "rediness", "=", 0)
    edge = OAEdge("same", order, a, "exist", "=", 1)
    with pytest.raises(ValueError):
        ConstraintGraphSpec(oa_edges=(edge, edge))
    with pytest.raises(TypeError):
        ConstraintGraphSpec(observations=[])
    with pytest.raises(ValueError):
        FormulaNode("flow", "<=", float("nan"))
    with pytest.raises(ValueError):
        PerformanceObservation("x", "A", "flow", True, "microseconds")


def test_four_result_schemas_are_serializable_roundtrips():
    # Exercise the public registry as well as nested dataclass decoding.
    from pix.results import result_from_json, result_json_bytes

    values = (
        measure_rule_metric(
            log_for("AB"), ObjectRuleMetricSpec("order", "A", "followed_by", "B")
        ),
        evaluate_constraint_graph(
            log_for("AB"),
            ConstraintGraphSpec(
                oa_edges=(
                    OAEdge(
                        "oa",
                        ObjectTypeNode("order"),
                        ActivityNode("A"),
                        "exist",
                        "=",
                        1,
                    ),
                ),
                aoa_edges=(
                    AOAEdge(
                        "aoa",
                        ActivityNode("A"),
                        ObjectTypeNode("order"),
                        ActivityNode("B"),
                        "cause",
                        "=",
                        1,
                    ),
                ),
                performance_edges=(
                    PerformanceEdge(
                        "perf", FormulaNode("flow", "<=", 4), ActivityNode("A")
                    ),
                ),
                observations=(
                    PerformanceObservation("s", "A", "flow", 3, "microseconds"),
                ),
            ),
        ),
        evaluate_e2o_qualifiers(
            qualifier_log(), E2OQualifierSpec("A", "order", "owner", "state", ())
        ),
        evaluate_o2o_qualifiers(
            qualifier_log(), O2OQualifierSpec("A", "order", "item", ("contains",))
        ),
    )
    for value in values:
        assert result_from_json(result_json_bytes(value)) == value


def test_nested_contract_decoder_preserves_numeric_types_before_publication():
    from pix.results import _decode, _encode

    spec = ConstraintGraphSpec(
        oa_edges=(
            OAEdge("oa", ObjectTypeNode("order"), ActivityNode("A"), "exist", "=", 1),
        ),
        performance_edges=(
            PerformanceEdge("p", FormulaNode("flow", "=", 3.5), ActivityNode("A")),
        ),
        observations=(PerformanceObservation("s", "A", "flow", 3, "microseconds"),),
    )
    decoded = _decode(_encode(spec), ConstraintGraphSpec)
    assert decoded == spec
    assert type(decoded.oa_edges[0].threshold) is int
    assert type(decoded.performance_edges[0].source.threshold) is float
    assert type(decoded.observations[0].value) is int
