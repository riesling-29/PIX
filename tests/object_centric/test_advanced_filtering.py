"""Independent selection/relationship oracles for native OCEL projection."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.context import ComputationContext
from pix.compute.executions import discover_executions
from pix.contracts.execution import ExecutionSpec
from pix.contracts.result import ComputeStatus
from pix.object_centric.advanced_filtering import (
    OCExecutionFilterSpec,
    OCFrequencyFilterSpec,
    OCFrequencyRule,
    OCPredicateFilterSpec,
    OCProjectionPolicy,
    OCRelationSelection,
    OCSamplingSpec,
    OCStructureFilterSpec,
    OCTypeActivityRule,
    OCTypeCardinality,
    filter_ocel_by_predicate,
    filter_ocel_executions,
    filter_ocel_frequency,
    filter_ocel_structure,
    materialize_advanced_sublog,
    sample_ocel,
)
from pix.object_centric.filter_predicates import OCFilterPredicateSpec
from pix.object_centric.performance import OCPerformanceSpec
from pix.object_centric.relations import OCELScalar
from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    OCELImportInfo,
    TimezoneInfo,
    ValueType,
    canonical_digest,
    validate,
)
from pix.results import read_result, result_from_json, result_json_bytes, write_result

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)
DAY_US = 86_400_000_000


def fixture():
    return OCEL(
        event_types=(
            EventType("A", (Attribute("amount", ValueType.INTEGER),)),
            EventType("B"),
            EventType("C"),
            EventType("Orphan"),
        ),
        object_types=(
            ObjectType("order", (Attribute("state", ValueType.STRING),)),
            ObjectType("item"),
            ObjectType("unused"),
        ),
        events=(
            Event("e1", "A", BASE, (EventAttr("amount", 10),)),
            Event("e2", "B", BASE + timedelta(days=1)),
            Event("e3", "A", BASE + timedelta(days=10), (EventAttr("amount", 20),)),
            Event("e4", "C", BASE + timedelta(days=11)),
            Event("orphan", "Orphan", BASE + timedelta(days=3)),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr("state", "old", BASE - timedelta(days=1)),
                    ObjectAttr("state", "running", BASE + timedelta(days=1)),
                    ObjectAttr("state", "done", BASE + timedelta(days=20)),
                ),
            ),
            Object("o2", "order"),
            Object("i1", "item"),
            Object("i2", "item"),
            Object("u", "unused"),
        ),
        e2o=(
            E2O("e1", "o1", "input"),
            E2O("e2", "o1", "input"),
            E2O("e2", "o1", "audit"),
            E2O("e2", "i1", "output"),
            E2O("e3", "o2", "input"),
            E2O("e3", "i2", "input"),
            E2O("e4", "o2", "input"),
        ),
        o2o=(O2O("o1", "o2", "related"), O2O("u", "i1", "link")),
        import_info=OCELImportInfo(
            "fixture", "ocel-json", "fixture-digest", TimezoneInfo()
        ),
    )


def selected(result, events, objects=None, *, status=ComputeStatus.COMPUTED):
    assert result.status is status, result.issues
    assert result.value.selected_event_ids == tuple(sorted(events))
    if objects is not None:
        assert result.value.selected_object_ids == tuple(sorted(objects))
    return result.value


def whitelist(**kwargs):
    return OCStructureFilterSpec(
        "activity_type_matching",
        allowed=(
            OCTypeActivityRule("order", ("A",)),
            OCTypeActivityRule("item", ("B",)),
        ),
        **kwargs,
    )


def tied_fixture():
    return OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("order"),),
        events=(Event("a", "A", BASE), Event("z", "B", BASE)),
        objects=(Object("o", "order"), Object("p", "order")),
        e2o=(E2O("a", "o", ""), E2O("z", "o", ""), E2O("a", "p", "")),
    )


def test_event_sample_seed_and_source_reordering_are_deterministic():
    source = fixture()
    request = OCSamplingSpec(2, seed=0)
    result = sample_ocel(source, request)
    value = selected(result, {"e4", "orphan"}, {"o2"})
    assert value.seed_event_ids == ("e4", "orphan")
    assert value.population_count == 5
    reordered = replace(
        source,
        events=source.events[::-1],
        objects=source.objects[::-1],
        e2o=source.e2o[::-1],
    )
    assert sample_ocel(reordered, request) == result
    assert sample_ocel(ComputationContext(source), request) == result


@pytest.mark.parametrize(
    "policy,events,objects",
    [
        (OCProjectionPolicy(), {"e3", "e4"}, {"o2", "u"}),
        (OCProjectionPolicy("associated"), {"e3", "e4"}, {"o2", "i2", "u"}),
        (OCProjectionPolicy(object_event_policy="all"), {"e4"}, {"o2", "u"}),
        (OCProjectionPolicy("associated", "all"), {"e4"}, {"o2", "u"}),
        (
            OCProjectionPolicy(object_event_policy="retain"),
            {"e1", "e2", "e3", "e4", "orphan"},
            {"o2", "u"},
        ),
        (OCProjectionPolicy(isolated_objects="drop"), {"e3", "e4"}, {"o2"}),
    ],
)
def test_object_sample_projection_is_explicit_before_peer_expansion(
    policy, events, objects
):
    result = sample_ocel(
        fixture(), OCSamplingSpec(2, "objects", seed=0, projection=policy)
    )
    value = selected(result, events, objects)
    assert value.seed_object_ids == ("o2", "u")
    projected = materialize_advanced_sublog(fixture(), result)
    assert {event.id for event in projected.events} == events
    assert {obj.id for obj in projected.objects} == objects


def test_component_sample_keeps_orphans_and_isolated_objects_without_using_o2o():
    source = fixture()
    result = sample_ocel(source, OCSamplingSpec(4, "components"))
    value = selected(
        result, {"e1", "e2", "e3", "e4", "orphan"}, {"o1", "o2", "i1", "i2", "u"}
    )
    assert {
        (group.event_ids, group.object_ids, group.relation_count)
        for group in value.groups
    } == {
        (("e1", "e2"), ("i1", "o1"), 4),
        (("e3", "e4"), ("i2", "o2"), 3),
        (("orphan",), (), 0),
        ((), ("u",), 0),
    }
    assert len(value.selected_execution_ids) == 4
    assert canonical_digest(
        materialize_advanced_sublog(source, result)
    ) == canonical_digest(source)


@pytest.mark.parametrize(
    "limits,events,objects,count",
    [
        ({"maximum_events": 0}, set(), {"u"}, 1),
        ({"maximum_objects": 0}, {"orphan"}, set(), 1),
        ({"maximum_relations": 3}, {"e3", "e4", "orphan"}, {"o2", "i2", "u"}, 3),
        (
            {"include_isolated_objects": False},
            {"e1", "e2", "e3", "e4", "orphan"},
            {"o1", "o2", "i1", "i2"},
            3,
        ),
    ],
)
def test_component_eligibility_limits_are_counted_on_source_memberships(
    limits, events, objects, count
):
    result = sample_ocel(
        fixture(), OCSamplingSpec(99, "components", overflow="clip", **limits)
    )
    value = selected(result, events, objects)
    assert value.population_count == count
    assert len(value.selected_execution_ids) == count
    assert any(issue.code == "sample_count_clipped" for issue in result.issues)


def test_sampling_zero_and_oversize_are_distinct_outcomes():
    selected(sample_ocel(fixture(), OCSamplingSpec(0)), set(), set())
    invalid = sample_ocel(fixture(), OCSamplingSpec(6))
    assert invalid.status is ComputeStatus.INVALID_INPUT
    assert invalid.value is None
    assert invalid.issues[0].code == "sample_exceeds_population"


@pytest.mark.parametrize(
    "rule,events",
    [
        (OCFrequencyRule(minimum_count=2), {"e1", "e3"}),
        (OCFrequencyRule(coverage=0.4, include_ties=False), {"e1", "e3"}),
        (
            OCFrequencyRule(
                coverage=0.4, coverage_boundary="exceed", include_ties=False
            ),
            {"e1", "e2", "e3"},
        ),
        (
            OCFrequencyRule(coverage=0.4, coverage_boundary="exceed"),
            {"e1", "e2", "e3", "e4", "orphan"},
        ),
        (OCFrequencyRule(coverage=0), set()),
        (OCFrequencyRule(coverage=0, coverage_boundary="exceed"), {"e1", "e3"}),
        (OCFrequencyRule(top_k=0), set()),
        (OCFrequencyRule(top_k=2, include_ties=False), {"e1", "e2", "e3"}),
        (OCFrequencyRule(top_k=2), {"e1", "e2", "e3", "e4", "orphan"}),
        (OCFrequencyRule(top_k=1, maximum_count=1), set()),
    ],
)
def test_activity_frequency_absolute_coverage_and_rank_intersection(rule, events):
    value = selected(
        filter_ocel_frequency(fixture(), OCFrequencyFilterSpec(rule=rule)), events
    )
    assert {
        decision.entity_id: (decision.count, decision.denominator)
        for decision in value.decisions
    } == {"A": (2, 5), "B": (1, 5), "C": (1, 5), "Orphan": (1, 5)}


@pytest.mark.parametrize(
    "counting,events,objects,counts,total",
    [
        ("unique_event_objects", set(), set(), {"order": 4, "item": 2, "unused": 0}, 6),
        (
            "relations",
            {"e1", "e2", "e3", "e4"},
            {"o1", "o2"},
            {"order": 5, "item": 2, "unused": 0},
            7,
        ),
    ],
)
def test_type_frequency_qualified_rows_and_unique_participation_differ(
    counting, events, objects, counts, total
):
    value = selected(
        filter_ocel_frequency(
            fixture(),
            OCFrequencyFilterSpec(
                "object_type", OCFrequencyRule(minimum_share=0.7), counting=counting
            ),
        ),
        events,
        objects,
    )
    assert {
        decision.entity_id: decision.count for decision in value.decisions
    } == counts
    assert {decision.denominator for decision in value.decisions} == {total}


def test_object_frequency_analysis_scope_does_not_delete_source_qualifiers():
    result = filter_ocel_frequency(
        fixture(),
        OCFrequencyFilterSpec(
            "object", OCFrequencyRule(minimum_count=2), qualifiers=("input",)
        ),
    )
    value = selected(result, {"e1", "e2", "e3", "e4"}, {"o1", "o2"})
    assert OCRelationSelection("e2", "o1", "audit") in value.retained_relations
    assert {decision.entity_id: decision.count for decision in value.decisions} == {
        "o1": 2,
        "o2": 2,
        "i1": 0,
        "i2": 1,
        "u": 0,
    }
    assert any(
        relation.qualifier == "audit"
        for relation in materialize_advanced_sublog(fixture(), result).e2o
    )


@pytest.mark.parametrize("positive", [True, False])
@pytest.mark.parametrize("unknown", ["exclude", "include", "error"])
def test_zero_frequency_denominator_is_unknown_even_under_negation(positive, unknown):
    spec = OCFrequencyFilterSpec(
        "object",
        OCFrequencyRule(minimum_share=0),
        object_types=("unused",),
        positive=positive,
        unknown=unknown,
    )
    result = filter_ocel_frequency(fixture(), spec)
    if unknown == "error":
        assert result.status is ComputeStatus.INVALID_INPUT and result.value is None
    else:
        value = selected(
            result,
            set(),
            {"u"} if unknown == "include" else set(),
            status=ComputeStatus.PARTIAL,
        )
        assert value.unknown_object_ids == ("u",)


@pytest.mark.parametrize(
    "rules,counting,events",
    [
        (
            (OCTypeCardinality("order", 1), OCTypeCardinality("item", 1)),
            "unique_objects",
            {"e2", "e3"},
        ),
        ((OCTypeCardinality("order", 2),), "unique_objects", set()),
        ((OCTypeCardinality("order", 2),), "relations", {"e2"}),
        ((OCTypeCardinality("order", 0, 0),), "unique_objects", {"orphan"}),
    ],
)
def test_cardinality_counts_are_typed_and_deduplicate_qualified_incidence(
    rules, counting, events
):
    selected(
        filter_ocel_structure(
            fixture(), OCStructureFilterSpec(cardinalities=rules, counting=counting)
        ),
        events,
    )


def test_relation_whitelist_materialization_never_reintroduces_dropped_e2o():
    source = fixture()
    digest = canonical_digest(source)
    result = filter_ocel_structure(source, whitelist())
    value = selected(result, {"e1", "e2", "e3"}, {"o1", "i1", "o2"})
    expected = {("e1", "o1", "input"), ("e2", "i1", "output"), ("e3", "o2", "input")}
    assert {
        (row.event_id, row.object_id, row.qualifier) for row in value.retained_relations
    } == expected
    assert value.dropped_e2o_count == 4
    # Native endpoint projection loses 2; the additional whitelist loses 2 more.
    assert value.selection.dropped_e2o_count == 2
    projected = materialize_advanced_sublog(source, result)
    assert {(row.event, row.object, row.qualifier) for row in projected.e2o} == expected
    assert projected.o2o == (O2O("o1", "o2", "related"),)
    assert projected.event_types == ComputationContext(source).log.event_types
    assert projected.object_types == ComputationContext(source).log.object_types
    assert projected.import_info == source.import_info
    assert (
        next(obj for obj in projected.objects if obj.id == "o1").attributes
        == source.objects[0].attributes
    )
    assert canonical_digest(source) == digest
    assert not validate(projected).errors


def test_whitelist_relation_scope_and_orphan_policy_are_explicit():
    result = filter_ocel_structure(
        fixture(), whitelist(qualifiers=("input",), keep_unrelated_events=True)
    )
    value = selected(result, {"e1", "e3", "orphan"}, {"o1", "o2"})
    assert len(value.retained_relations) == 2
    negated = filter_ocel_structure(fixture(), whitelist(positive=False))
    selected(negated, {"e2", "e3", "e4"}, {"o1", "o2", "i2"})


def test_all_objects_retention_does_not_restore_whitelist_cut_relations():
    source = fixture()
    result = filter_ocel_structure(
        source, whitelist(projection=OCProjectionPolicy("all"))
    )
    value = selected(result, {"e1", "e2", "e3"}, {"o1", "o2", "i1", "i2", "u"})
    assert len(value.retained_relations) == 3
    assert set(materialize_advanced_sublog(source, result).o2o) == set(source.o2o)


@pytest.mark.parametrize(
    "mode,events", [("start_events", {"e1", "e3"}), ("end_events", {"e2", "e4"})]
)
def test_boundaries_are_observed_participation_endpoints(mode, events):
    selected(
        filter_ocel_structure(
            fixture(), OCStructureFilterSpec(mode, object_type="order")
        ),
        events,
    )


@pytest.mark.parametrize(
    "mode,tie_policy,events",
    [
        ("start_events", "all", {"a", "z"}),
        ("end_events", "all", {"a", "z"}),
        ("start_events", "event_id", {"a"}),
        ("end_events", "event_id", {"a", "z"}),
    ],
)
def test_boundary_lexical_end_chooses_highest_id_without_causal_claim(
    mode, tie_policy, events
):
    result = filter_ocel_structure(
        tied_fixture(),
        OCStructureFilterSpec(mode, object_type="order", tie_policy=tie_policy),
    )
    selected(result, events)
    assert bool(result.issues) == (tie_policy == "event_id")


@pytest.mark.parametrize("positive", [True, False])
@pytest.mark.parametrize("unknown", ["exclude", "include", "error"])
def test_known_boundary_witness_wins_over_other_objects_ambiguity(positive, unknown):
    result = filter_ocel_structure(
        tied_fixture(),
        OCStructureFilterSpec(
            "start_events", object_type="order", positive=positive, unknown=unknown
        ),
    )
    if unknown == "error":
        assert result.status is ComputeStatus.INVALID_INPUT
    else:
        expected = {"a"} if positive else set()
        if unknown == "include":
            expected.add("z")
        value = selected(result, expected, status=ComputeStatus.PARTIAL)
        assert value.unknown_event_ids == ("z",)
        assert value.unknown_object_ids == ("o",)


@pytest.mark.parametrize(
    "conditions,events,objects",
    [
        ({"minimum_objects": 2}, {"e1", "e2", "e3", "e4"}, {"o1", "o2", "i1", "i2"}),
        ({"maximum_events": 0}, set(), {"u"}),
        ({"object_ids": ("o1",)}, {"e1", "e2"}, {"o1", "i1"}),
        ({"object_types": ("item",), "activities": ("C",)}, {"e3", "e4"}, {"o2", "i2"}),
        ({"minimum_relations": 4}, {"e1", "e2"}, {"o1", "i1"}),
        ({"maximum_objects": 0}, {"orphan"}, set()),
        (
            {"object_ids": ("o1",), "positive": False},
            {"e3", "e4", "orphan"},
            {"o2", "i2", "u"},
        ),
    ],
)
def test_execution_conditions_select_complete_membership_sets(
    conditions, events, objects
):
    selected(
        filter_ocel_executions(fixture(), OCExecutionFilterSpec(**conditions)),
        events,
        objects,
    )


@pytest.mark.parametrize("unknown", ["exclude", "include", "error"])
def test_duration_is_exact_observed_span_with_eventless_unknown(unknown):
    result = filter_ocel_executions(
        fixture(),
        OCExecutionFilterSpec(
            minimum_duration_us=DAY_US, maximum_duration_us=DAY_US, unknown=unknown
        ),
    )
    if unknown == "error":
        assert result.status is ComputeStatus.INVALID_INPUT
    else:
        expected_objects = {"o1", "o2", "i1", "i2"} | (
            {"u"} if unknown == "include" else set()
        )
        value = selected(
            result,
            {"e1", "e2", "e3", "e4"},
            expected_objects,
            status=ComputeStatus.PARTIAL,
        )
        assert len(value.unknown_execution_ids) == 1
        assert next(
            group
            for group in value.groups
            if group.id == value.unknown_execution_ids[0]
        ).object_ids == ("u",)


def test_execution_id_is_bound_to_source_and_requested_extraction():
    source = fixture()
    parent = discover_executions(source, ExecutionSpec("connected_components"))
    target = next(
        execution.execution_id
        for execution in parent.value.executions
        if {event.id for event in execution.events} == {"e1", "e2"}
    )
    result = filter_ocel_executions(
        source, OCExecutionFilterSpec("execution_ids", execution_ids=(target,))
    )
    selected(result, {"e1", "e2"}, {"o1", "i1"})
    assert result.parent_computation_ids[0] == parent.computation_id
    invalid = filter_ocel_executions(
        source,
        OCExecutionFilterSpec(
            "execution_ids",
            execution_ids=(target,),
            execution_spec=ExecutionSpec("connected_components", qualifiers=("input",)),
        ),
    )
    assert invalid.status is ComputeStatus.INVALID_INPUT


def variant_fixture():
    return OCEL(
        event_types=(EventType("A"), EventType("B"), EventType("C")),
        object_types=(ObjectType("order"), ObjectType("item")),
        events=(
            Event("a1", "A", BASE),
            Event("b1", "B", BASE + timedelta(seconds=1)),
            Event("a2", "A", BASE + timedelta(days=1)),
            Event("b2", "B", BASE + timedelta(days=1, seconds=1)),
            Event("c", "C", BASE + timedelta(days=2)),
        ),
        objects=(
            Object("o1", "order"),
            Object("o2", "order"),
            Object("i1", "item"),
            Object("i2", "item"),
            Object("isolated", "order"),
        ),
        e2o=(
            E2O("a1", "o1", ""),
            E2O("b1", "o1", ""),
            E2O("b1", "i1", ""),
            E2O("a2", "o2", ""),
            E2O("b2", "o2", ""),
            E2O("b2", "i2", ""),
        ),
    )


def test_exact_variant_frequency_uses_native_incidence_equivalence():
    source = variant_fixture()
    result = filter_ocel_executions(
        source,
        OCExecutionFilterSpec(
            "variant_frequency", frequency=OCFrequencyRule(minimum_count=2)
        ),
    )
    value = selected(result, {"a1", "b1", "a2", "b2"}, {"o1", "o2", "i1", "i2"})
    assert value.population_count == 3  # Eventless objects are not silently variants.
    assert len(value.selected_execution_ids) == 2
    assert len(value.selected_variant_ids) == 1
    assert sorted(decision.count for decision in value.decisions) == [1, 2]
    assert {decision.denominator for decision in value.decisions} == {3}
    target = value.selected_variant_ids[0]
    selected(
        filter_ocel_executions(
            source, OCExecutionFilterSpec("variant_ids", variant_ids=(target,))
        ),
        {"a1", "b1", "a2", "b2"},
    )
    selected(
        filter_ocel_executions(
            source,
            OCExecutionFilterSpec("variant_ids", variant_ids=(target,), positive=False),
        ),
        {"c"},
        set(),
    )


def test_same_activity_sequence_is_not_claimed_to_be_an_exact_variant():
    source = variant_fixture()
    source = replace(
        source,
        e2o=tuple(relation for relation in source.e2o if relation.object != "i2"),
    )
    sequence = filter_ocel_executions(
        source, OCExecutionFilterSpec("sequence", sequences=(("A", "B"),))
    )
    selected(sequence, {"a1", "b1", "a2", "b2"})
    exact = filter_ocel_executions(
        source,
        OCExecutionFilterSpec(
            "variant_frequency", frequency=OCFrequencyRule(minimum_count=2)
        ),
    )
    selected(exact, set(), set())


def test_variant_ids_are_checked_and_unavailable_order_is_not_an_empty_selection():
    invalid = filter_ocel_executions(
        fixture(), OCExecutionFilterSpec("variant_ids", variant_ids=("unseen",))
    )
    assert invalid.status is ComputeStatus.INVALID_INPUT and invalid.value is None
    unavailable = filter_ocel_executions(
        tied_fixture(), OCExecutionFilterSpec("variant_frequency")
    )
    assert unavailable.status is ComputeStatus.UNAVAILABLE and unavailable.value is None


@pytest.mark.parametrize("unknown", ["exclude", "include", "error"])
def test_sequence_timestamp_tie_is_explicit_unknown(unknown):
    result = filter_ocel_executions(
        tied_fixture(),
        OCExecutionFilterSpec("sequence", sequences=(("A", "B"),), unknown=unknown),
    )
    if unknown == "error":
        assert result.status is ComputeStatus.INVALID_INPUT
    else:
        value = selected(
            result,
            {"a", "z"} if unknown == "include" else set(),
            status=ComputeStatus.PARTIAL,
        )
        assert len(value.unknown_execution_ids) == 1


def test_sequence_explicit_lexical_policy_reports_total_order_choice():
    result = filter_ocel_executions(
        tied_fixture(),
        OCExecutionFilterSpec(
            "sequence",
            sequences=(("A", "B"),),
            sequence_ties="event_id",
            execution_spec=ExecutionSpec("connected_components", tie_policy="event_id"),
        ),
    )
    selected(result, {"a", "z"}, {"o", "p"})
    assert any(issue.code == "lexical_execution_sequence" for issue in result.issues)


@pytest.mark.parametrize("sequences", [(), (("A",),), (("C", "C"),)])
@pytest.mark.parametrize("unknown", ["exclude", "include", "error"])
def test_impossible_sequence_membership_is_false_despite_timestamp_ties(
    sequences, unknown
):
    result = filter_ocel_executions(
        tied_fixture(),
        OCExecutionFilterSpec("sequence", sequences=sequences, unknown=unknown),
    )
    # Native extraction records its incomplete ordering as an issue, but the
    # activity-multiset proof makes this selection fully decidable.
    value = selected(result, set(), set())
    assert value.unknown_execution_ids == ()
    assert result_from_json(result_json_bytes(result)) == result


def test_cardinality_witness_identifiers_cannot_collide_on_colon_names():
    source = OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("c"), ObjectType("b:c")),
        events=(Event("a:b", "A", BASE), Event("a", "A", BASE + timedelta(seconds=1))),
        objects=(Object("o", "c"), Object("p", "b:c")),
        e2o=(E2O("a:b", "o", ""), E2O("a", "p", "")),
    )
    result = filter_ocel_structure(
        source,
        OCStructureFilterSpec(
            cardinalities=(OCTypeCardinality("c"), OCTypeCardinality("b:c"))
        ),
    )
    value = selected(result, {"a", "a:b"}, {"o", "p"})
    assert len({decision.entity_id for decision in value.decisions}) == 4
    assert result_from_json(result_json_bytes(result)) == result


def test_leading_object_overlap_is_reported_and_materialization_deduplicates():
    source = OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("order"), ObjectType("item")),
        events=(
            Event("e1", "A", BASE),
            Event("e2", "A", BASE + timedelta(seconds=1)),
            Event("e3", "B", BASE + timedelta(seconds=2)),
        ),
        objects=(Object("o1", "order"), Object("o2", "order"), Object("item", "item")),
        e2o=(
            E2O("e1", "o1", ""),
            E2O("e1", "item", ""),
            E2O("e2", "o2", ""),
            E2O("e2", "item", ""),
            E2O("e3", "item", ""),
        ),
    )
    result = filter_ocel_executions(
        source,
        OCExecutionFilterSpec(
            execution_spec=ExecutionSpec(
                "leading_object_nearest_type", leading_object_type="order"
            )
        ),
    )
    value = selected(result, {"e1", "e2", "e3"}, {"o1", "o2", "item"})
    assert len(value.selected_execution_ids) == 2
    assert value.overlapping_event_ids == ("e1", "e2", "e3")
    assert value.overlapping_object_ids == ("item",)
    assert canonical_digest(
        materialize_advanced_sublog(source, result)
    ) == canonical_digest(source)


def test_attribute_predicate_wrapper_preserves_typed_parent_and_unknowns():
    result = filter_ocel_by_predicate(
        fixture(),
        OCPredicateFilterSpec(
            OCFilterPredicateSpec(
                "event_attribute",
                attribute="amount",
                comparison="numeric_range",
                minimum=OCELScalar("integer", integer_value=15),
            )
        ),
    )
    value = selected(result, {"e3"}, {"o2", "i2"}, status=ComputeStatus.PARTIAL)
    assert value.unknown_event_ids == ("e2", "e4", "orphan")
    assert len(result.parent_computation_ids) == 2
    assert materialize_advanced_sublog(fixture(), result).events[0].attributes == (
        EventAttr("amount", 20),
    )


def test_fixed_asof_predicate_selects_objects_without_trimming_future_history():
    result = filter_ocel_by_predicate(
        fixture(),
        OCPredicateFilterSpec(
            OCFilterPredicateSpec(
                "object_attribute",
                attribute="state",
                as_of=BASE + timedelta(days=2),
                value=OCELScalar("string", text_value="running"),
                object_types=("order",),
            )
        ),
    )
    selected(result, {"e1", "e2"}, {"o1"}, status=ComputeStatus.PARTIAL)
    projected = materialize_advanced_sublog(fixture(), result)
    assert projected.objects[0].attributes[-1] == ObjectAttr(
        "state", "done", BASE + timedelta(days=20)
    )
    assert projected.import_info == fixture().import_info


def test_lifecycle_and_performance_predicates_materialize_real_source_facts():
    lifecycle = filter_ocel_by_predicate(
        fixture(),
        OCPredicateFilterSpec(
            OCFilterPredicateSpec(
                "object_lifecycle",
                lifecycle="contains",
                activity="C",
                object_types=("order",),
            )
        ),
    )
    selected(lifecycle, {"e3", "e4"}, {"o2"})
    performance = filter_ocel_by_predicate(
        fixture(),
        OCPredicateFilterSpec(
            OCFilterPredicateSpec(
                "performance",
                comparison="numeric_range",
                minimum=OCELScalar("integer", integer_value=1),
                performance_spec=OCPerformanceSpec(
                    metrics=("object_frequency",), object_type="order"
                ),
            )
        ),
    )
    selected(performance, {"e1", "e2", "e3", "e4"}, {"o1", "o2", "i1", "i2"})
    assert (
        materialize_advanced_sublog(fixture(), performance).e2o
        == ComputationContext(fixture()).log.e2o
    )


@pytest.mark.parametrize("tamper", ["relations", "parents", "source", "decisions"])
def test_materializer_rejects_forged_or_stale_evidence(tamper):
    source = fixture()
    result = filter_ocel_structure(source, whitelist())
    if tamper == "relations":
        result = replace(
            result,
            value=replace(
                result.value,
                retained_relations=result.value.retained_relations
                + (OCRelationSelection("e2", "o1", "audit"),),
            ),
        )
    elif tamper == "parents":
        result = replace(result, parent_computation_ids=())
    elif tamper == "decisions":
        result = replace(result, value=replace(result.value, decisions=()))
    else:
        source = replace(source, o2o=())
    with pytest.raises(ValueError):
        materialize_advanced_sublog(source, result)


def test_spec_identity_changes_for_explicit_semantics_and_is_frozen():
    source = fixture()
    spec = OCSamplingSpec(0)
    first = sample_ocel(source, spec)
    second = sample_ocel(source, replace(spec, seed=99))
    assert first.value == second.value
    assert first.computation_id != second.computation_id
    with pytest.raises(FrozenInstanceError):
        spec.count = 4


@pytest.mark.parametrize(
    "factory",
    [
        lambda: OCSamplingSpec(-1),
        lambda: OCSamplingSpec(True),
        lambda: OCSamplingSpec(1, seed=True),
        lambda: OCSamplingSpec(1, maximum_events=2),
        lambda: OCFrequencyRule(minimum_count=2, maximum_count=1),
        lambda: OCFrequencyRule(minimum_share=float("nan")),
        lambda: OCFrequencyRule(coverage=1.01),
        lambda: OCFrequencyRule(coverage=10**500),
        lambda: OCFrequencyRule(include_ties=1),
        lambda: OCFrequencyFilterSpec(qualifiers=()),
        lambda: OCStructureFilterSpec("start_events"),
        lambda: OCTypeCardinality("order", minimum=None),
        lambda: OCStructureFilterSpec(keep_unrelated_events=True),
        lambda: OCStructureFilterSpec(
            "start_events", object_type="order", counting="relations"
        ),
        lambda: OCStructureFilterSpec(tie_policy="all"),
        lambda: OCStructureFilterSpec(
            cardinalities=(OCTypeCardinality("order"), OCTypeCardinality("order"))
        ),
        lambda: OCExecutionFilterSpec("sequence", minimum_events=2),
        lambda: OCExecutionFilterSpec("conditions", execution_ids=("unused",)),
        lambda: OCProjectionPolicy(object_event_policy="vacuous_all"),
        lambda: OCPredicateFilterSpec("untyped"),
    ],
)
def test_invalid_specs_fail_before_calculation(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()


@pytest.mark.parametrize(
    "function,spec",
    [
        (sample_ocel, OCSamplingSpec(0)),
        (filter_ocel_frequency, OCFrequencyFilterSpec()),
        (filter_ocel_structure, OCStructureFilterSpec()),
        (filter_ocel_executions, OCExecutionFilterSpec()),
        (
            filter_ocel_by_predicate,
            OCPredicateFilterSpec(
                OCFilterPredicateSpec(
                    "event_attribute", attribute="amount", comparison="present"
                )
            ),
        ),
    ],
)
def test_invalid_source_is_not_successful_empty_selection(function, spec):
    source = replace(fixture(), e2o=(E2O("missing", "o1", ""),))
    result = function(source, spec)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None and result.source_digest is None


@pytest.mark.parametrize(
    "function,spec",
    [
        (sample_ocel, OCSamplingSpec(0, "components")),
        (filter_ocel_frequency, OCFrequencyFilterSpec()),
        (filter_ocel_structure, OCStructureFilterSpec()),
        (filter_ocel_executions, OCExecutionFilterSpec()),
        (filter_ocel_executions, OCExecutionFilterSpec("variant_frequency")),
        (
            filter_ocel_by_predicate,
            OCPredicateFilterSpec(
                OCFilterPredicateSpec(
                    "event_attribute", attribute="amount", comparison="present"
                )
            ),
        ),
    ],
)
def test_empty_valid_log_has_successful_reproducible_empty_selection(function, spec):
    source = OCEL()
    result = function(source, spec)
    selected(result, set(), set())
    assert result_from_json(result_json_bytes(result)) == result
    assert canonical_digest(
        materialize_advanced_sublog(source, result)
    ) == canonical_digest(source)


@pytest.mark.parametrize(
    "function,spec",
    [
        (sample_ocel, OCSamplingSpec(1, "components")),
        (
            filter_ocel_frequency,
            OCFrequencyFilterSpec(rule=OCFrequencyRule(minimum_share=0.4)),
        ),
        (filter_ocel_structure, whitelist()),
        (
            filter_ocel_executions,
            OCExecutionFilterSpec(
                "variant_frequency", frequency=OCFrequencyRule(coverage=1)
            ),
        ),
        (filter_ocel_executions, OCExecutionFilterSpec(minimum_duration_us=DAY_US)),
        (
            filter_ocel_by_predicate,
            OCPredicateFilterSpec(
                OCFilterPredicateSpec(
                    "object_attribute",
                    attribute="state",
                    as_of=BASE,
                    value=OCELScalar("string", text_value="old"),
                )
            ),
        ),
        (sample_ocel, OCSamplingSpec(100)),
    ],
)
def test_actual_file_roundtrip_retains_result_and_materialization_identity(
    tmp_path, function, spec
):
    source = fixture()
    result = function(source, spec)
    wire = result_json_bytes(result)
    restored = result_from_json(wire)
    assert restored == result
    path = tmp_path / "selection.pix-result.json"
    write_result(result, path)
    assert read_result(path) == result
    if result.value is not None:
        assert canonical_digest(
            materialize_advanced_sublog(source, restored)
        ) == canonical_digest(materialize_advanced_sublog(source, result))
