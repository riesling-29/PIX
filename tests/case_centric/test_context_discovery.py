"""Independent frequency enumeration and hand-conditioned DFG populations."""

import itertools
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.context_discovery import (
    RESULT_SCHEMAS,
    ActivityTriple,
    ActivityTripleSpec,
    AttributedSequenceRelation,
    CaseAttributeDFGSpec,
    CaseAttributeValue,
    ContextWitness,
    discover_activity_triples,
    discover_case_attribute_dfg,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
)


def log_of(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{i}",
                tuple(
                    CaseEvent(
                        f"event-{i}-{j}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for j, activity in enumerate(sequence)
                ),
            )
            for i, sequence in enumerate(sequences)
        )
    )


def with_case_attributes(source, attributes):
    return replace(
        source,
        traces=tuple(
            replace(trace, attributes=values)
            for trace, values in zip(source.traces, attributes)
        ),
    )


def edge(output, *activities):
    return next(row for row in output.value.edges if row.activities == activities)


def bins(row, key):
    return next(
        distribution.bins for distribution in row.attributes if distribution.key == key
    )


def values(rows):
    return {
        (row.value.type, row.value.value_json) if row.value else None: (
            row.occurrence_count,
            row.case_count,
            row.case_ids,
        )
        for row in rows
    }


def test_consecutive_triples_count_overlaps_repetition_and_distinct_cases():
    source = log_of(("A", "B", "A", "B", "A"), ("A", "B", "A"), ("A", "B"), ())
    output = discover_activity_triples(source)
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.case_ids == ("case-0", "case-1", "case-2", "case-3")
    assert output.value.eligible_case_ids == ("case-0", "case-1")
    assert output.value.event_count == 10
    assert output.value.occurrence_count == 4
    first, second = output.value.triples
    assert first.activities == ("A", "B", "A")
    assert (first.occurrence_count, first.case_count) == (3, 2)
    assert first.witnesses == (
        ContextWitness("case-0", ("event-0-0", "event-0-1", "event-0-2"), 0),
        ContextWitness("case-0", ("event-0-2", "event-0-3", "event-0-4"), 2),
        ContextWitness("case-1", ("event-1-0", "event-1-1", "event-1-2"), 0),
    )
    assert second.activities == ("B", "A", "B")
    assert (second.occurrence_count, second.case_count) == (1, 1)
    assert output.parent_computation_ids


def test_triples_do_not_bridge_cases_and_do_not_require_timestamps():
    output = discover_activity_triples(log_of(("A", "B"), ("C", "D"), (), ("E",)))
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.triples == ()
    assert output.value.occurrence_count == 0
    assert output.value.eligible_case_ids == ()


def test_triples_exhaustive_binary_sequences_match_independent_zip_counter():
    sequences = tuple(
        sequence
        for length in range(7)
        for sequence in itertools.product(("A", "B"), repeat=length)
    )
    expected = Counter()
    for sequence in sequences:
        expected.update(zip(sequence, sequence[1:], sequence[2:]))
    output = discover_activity_triples(log_of(*sequences))
    assert {
        row.activities: row.occurrence_count for row in output.value.triples
    } == expected
    for row in output.value.triples:
        expected_cases = sum(
            row.activities in set(zip(sequence, sequence[1:], sequence[2:]))
            for sequence in sequences
        )
        assert row.case_count == expected_cases


def test_source_order_retained_when_timestamps_descend_and_custom_activity_key_is_selected():
    source = log_of(("ignored", "ignored", "ignored"))
    times = (3, 2, 1)
    events = tuple(
        replace(
            event,
            attributes=(
                CaseAttribute("operation", "string", activity),
                CaseAttribute(
                    "time:timestamp",
                    "date",
                    datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=time),
                ),
            ),
        )
        for event, activity, time in zip(
            source.traces[0].events, ("A", "B", "C"), times
        )
    )
    source = replace(source, traces=(replace(source.traces[0], events=events),))
    output = discover_activity_triples(
        source, ActivityTripleSpec(trace_spec=CaseTraceSpec(activity_key="operation"))
    )
    assert output.value.triples[0].activities == ("A", "B", "C")


def test_shared_classifier_contract_resolves_global_event_defaults():
    source = log_of(("A", "B", "A"))
    source = replace(
        source,
        classifiers=(
            CaseClassifier("qualified", ("concept:name", "lifecycle:transition")),
        ),
        globals=(
            CaseGlobal(
                "event", (CaseAttribute("lifecycle:transition", "string", "complete"),)
            ),
        ),
    )
    spec = ActivityTripleSpec(CaseTraceSpec(classifier="qualified"))
    output = discover_activity_triples(source, spec)
    assert output.value.triples[0].activities == (
        '[["string","A"],["string","complete"]]',
        '[["string","B"],["string","complete"]]',
        '[["string","A"],["string","complete"]]',
    )


def test_triple_bound_returns_no_truncated_counts_and_input_failure_is_preserved():
    source = log_of(("A", "A", "A", "A"))
    limited = discover_activity_triples(source, ActivityTripleSpec(max_witnesses=1))
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None
    assert (
        discover_activity_triples(
            source, ActivityTripleSpec(max_witnesses=2)
        ).value.occurrence_count
        == 2
    )
    invalid = CaseLog((CaseTrace("c", (CaseEvent("e"),)),))
    assert discover_activity_triples(invalid).status is ComputeStatus.UNAVAILABLE


def test_case_attribute_dfg_counts_occurrences_not_one_vote_per_case():
    source = with_case_attributes(
        log_of(("A", "B", "A", "B"), ("A", "B"), ("A", "B")),
        (
            (CaseAttribute("creator", "string", "red"),),
            (CaseAttribute("creator", "string", "red"),),
            (CaseAttribute("creator", "string", "blue"),),
        ),
    )
    output = discover_case_attribute_dfg(
        source, CaseAttributeDFGSpec(("creator",), include_nodes=True)
    )
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.event_count == 8
    assert output.value.edge_occurrence_count == 5
    relation = edge(output, "A", "B")
    assert (relation.occurrence_count, relation.case_count) == (4, 3)
    assert values(bins(relation, "creator")) == {
        ("string", '"red"'): (3, 2, ("case-0", "case-1")),
        ("string", '"blue"'): (1, 1, ("case-2",)),
    }
    backwards = edge(output, "B", "A")
    assert values(bins(backwards, "creator")) == {
        ("string", '"red"'): (1, 1, ("case-0",))
    }
    nodes = {row.activities: row for row in output.value.nodes}
    assert values(bins(nodes[("A",)], "creator"))[("string", '"red"')][:2] == (3, 2)
    assert nodes[("A",)].occurrence_count == 4
    assert nodes[("B",)].occurrence_count == 4


def test_self_loop_edges_preserve_distinct_event_ids_and_case_count():
    source = with_case_attributes(
        log_of(("A", "A", "A")), ((CaseAttribute("x", "int", 1),),)
    )
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    row = edge(output, "A", "A")
    assert row.occurrence_count == 2
    assert row.case_count == 1
    assert tuple(witness.start_position for witness in row.witnesses) == (0, 1)
    assert row.witnesses[0].event_ids != row.witnesses[1].event_ids


def test_case_attribute_globals_resolve_without_overriding_recorded_values():
    source = log_of(("A", "B"), ("A", "B"))
    source = replace(
        source,
        globals=(CaseGlobal("trace", (CaseAttribute("x", "string", "global"),)),),
        traces=(
            source.traces[0],
            replace(
                source.traces[1], attributes=(CaseAttribute("x", "string", "local"),)
            ),
        ),
    )
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    assert values(bins(edge(output, "A", "B"), "x")) == {
        ("string", '"global"'): (1, 1, ("case-0",)),
        ("string", '"local"'): (1, 1, ("case-1",)),
    }


def test_missing_null_empty_string_and_internal_case_identity_remain_distinct():
    source = with_case_attributes(
        log_of(*[("A", "B")] * 4),
        (
            (),
            (CaseAttribute("concept:name", "null"),),
            (CaseAttribute("concept:name", "string", ""),),
            (CaseAttribute("concept:name", "string", "case-0"),),
        ),
    )
    output = discover_case_attribute_dfg(source)
    assert output.status is ComputeStatus.PARTIAL
    assert values(bins(edge(output, "A", "B"), "concept:name")) == {
        None: (1, 1, ("case-0",)),
        ("null", "null"): (1, 1, ("case-1",)),
        ("string", '""'): (1, 1, ("case-2",)),
        ("string", '"case-0"'): (1, 1, ("case-3",)),
    }
    assert (
        len(
            [issue for issue in output.issues if issue.code == "missing_case_attribute"]
        )
        == 1
    )


def test_all_missing_attributes_keep_edges_and_optional_nodes_in_topology():
    output = discover_case_attribute_dfg(
        log_of(("A", "B"), ("C",)), CaseAttributeDFGSpec(include_nodes=True)
    )
    assert output.status is ComputeStatus.PARTIAL
    assert edge(output, "A", "B").attributes[0].bins[0].value is None
    assert tuple(row.activities for row in output.value.nodes) == (
        ("A",),
        ("B",),
        ("C",),
    )
    assert output.value.nodes[-1].attributes[0].bins[0].case_ids == ("case-1",)


def test_nonexistent_attributes_on_cases_without_requested_relations_do_not_make_coverage_partial():
    output = discover_case_attribute_dfg(log_of((), ("A",)))
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.edges == output.value.nodes == ()
    assert output.value.case_ids == ("case-0", "case-1")


def test_empty_attribute_selection_keeps_unannotated_counts_and_no_missing_issues():
    output = discover_case_attribute_dfg(
        log_of(("A", "B")), CaseAttributeDFGSpec(case_attributes=())
    )
    assert output.status is ComputeStatus.COMPUTED
    assert edge(output, "A", "B").attributes == ()


@pytest.mark.parametrize("where", ["recorded", "global"])
def test_duplicate_selected_case_attribute_keys_are_invalid(where):
    source = log_of(("A", "B"))
    duplicates = (CaseAttribute("x", "int", 1), CaseAttribute("x", "int", 2))
    if where == "recorded":
        source = with_case_attributes(source, (duplicates,))
    else:
        source = replace(source, globals=(CaseGlobal("trace", duplicates),))
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    assert output.status is ComputeStatus.INVALID_INPUT
    assert output.value is None
    assert output.issues[-1].code == "invalid_case_attribute"


def test_typed_values_do_not_conflate_boolean_integer_float_or_string():
    attributes = tuple(
        (CaseAttribute("x", kind, value),)
        for kind, value in (
            ("boolean", True),
            ("int", 1),
            ("float", 1.0),
            ("string", "1"),
            ("id", "1"),
        )
    )
    source = with_case_attributes(log_of(*[("A", "B")] * len(attributes)), attributes)
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    rows = bins(edge(output, "A", "B"), "x")
    assert len(rows) == 5
    assert {(row.value.type, row.value.value_json) for row in rows} == {
        ("boolean", "true"),
        ("int", '"0x1"'),
        ("float", '"0x1.0000000000000p+0"'),
        ("string", '"1"'),
        ("id", '"1"'),
    }


def test_primitive_metadata_and_numeric_lexical_spellings_do_not_split_value_bins():
    a = CaseAttribute("x", "int", 1, lexical="01")
    b = CaseAttribute(
        "x",
        "int",
        1,
        children=(CaseAttribute("metadata", "string", "different"),),
        lexical="1",
    )
    source = with_case_attributes(log_of(("A", "B"), ("A", "B")), ((a,), (b,)))
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    assert len(bins(edge(output, "A", "B"), "x")) == 1
    assert bins(edge(output, "A", "B"), "x")[0].case_count == 2


def test_date_categories_group_equal_instants_without_utc_datetime_range_overflow():
    utc = datetime(2026, 1, 1, tzinfo=timezone.utc)
    korea = utc.astimezone(timezone(timedelta(hours=9)))
    local = utc.replace(tzinfo=None)
    boundary = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=9)))
    attrs = tuple(
        (CaseAttribute("x", "date", time),) for time in (utc, korea, local, boundary)
    )
    source = with_case_attributes(log_of(*[("A", "B")] * len(attrs)), attrs)
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    rows = bins(edge(output, "A", "B"), "x")
    assert len(rows) == 3
    assert sorted(row.case_count for row in rows) == [1, 1, 2]


def test_structured_attribute_values_preserve_order_and_type_without_unhashable_keys():
    first = CaseAttribute(
        "x",
        "list",
        values=(
            CaseAttribute("item", "int", 1),
            CaseAttribute("item", "boolean", True),
        ),
    )
    second = replace(first, values=first.values[::-1])
    third = CaseAttribute("x", "container", children=(CaseAttribute("item", "int", 1),))
    source = with_case_attributes(
        log_of(*[("A", "B")] * 3), ((first,), (second,), (third,))
    )
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    assert output.status is ComputeStatus.COMPUTED
    assert len(bins(edge(output, "A", "B"), "x")) == 3


def test_nonfinite_float_attributes_are_typed_categories_not_numeric_aggregations():
    attrs = tuple(
        (CaseAttribute("x", "float", value),)
        for value in (float("nan"), float("inf"), -float("inf"))
    )
    source = with_case_attributes(log_of(*[("A", "B")] * 3), attrs)
    output = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    assert output.status is ComputeStatus.COMPUTED
    assert {row.value.value_json for row in bins(edge(output, "A", "B"), "x")} == {
        '"nan"',
        '"inf"',
        '"-inf"',
    }


def test_case_attribute_limits_bound_both_witnesses_and_attribute_expansion():
    source = log_of(("A", "B", "C"))
    witness_limit = CaseAttributeDFGSpec(case_attributes=(), max_witnesses=1)
    assert (
        discover_case_attribute_dfg(source, witness_limit).status
        is ComputeStatus.UNAVAILABLE
    )
    annotation_limit = CaseAttributeDFGSpec(
        case_attributes=("x", "y"), max_annotation_occurrences=3
    )
    assert (
        discover_case_attribute_dfg(source, annotation_limit).status
        is ComputeStatus.UNAVAILABLE
    )
    include_node_limit = CaseAttributeDFGSpec(
        case_attributes=(), include_nodes=True, max_witnesses=4
    )
    assert (
        discover_case_attribute_dfg(source, include_node_limit).status
        is ComputeStatus.UNAVAILABLE
    )
    assert (
        discover_case_attribute_dfg(
            source, replace(include_node_limit, max_witnesses=5)
        ).status
        is ComputeStatus.COMPUTED
    )


def test_request_and_source_changes_change_identity_and_payload_is_frozen():
    source = with_case_attributes(
        log_of(("A", "B", "C")), ((CaseAttribute("x", "int", 1),),)
    )
    base = discover_case_attribute_dfg(source, CaseAttributeDFGSpec(("x",)))
    include_nodes = discover_case_attribute_dfg(
        source, CaseAttributeDFGSpec(("x",), include_nodes=True)
    )
    changed_source = with_case_attributes(source, ((CaseAttribute("x", "int", 2),),))
    changed = discover_case_attribute_dfg(changed_source, CaseAttributeDFGSpec(("x",)))
    assert (
        len({base.computation_id, include_nodes.computation_id, changed.computation_id})
        == 3
    )
    assert base.source_digest != changed.source_digest
    with pytest.raises(FrozenInstanceError):
        base.value.event_count = 0


@pytest.mark.parametrize(
    "type_name,encoded",
    [
        ("int", '"01"'),
        ("int", "1"),
        ("float", "1.0"),
        ("float", '"1.0"'),
        ("boolean", "1"),
        ("null", '"null"'),
        ("string", "null"),
        ("date", '["naive","2026-01-01T00:00:00+00:00"]'),
        ("list", "[1]"),
        ("container", '[["x",["int",1]]]'),
    ],
)
def test_malformed_typed_attribute_contracts_are_rejected(type_name, encoded):
    with pytest.raises((ValueError, TypeError)):
        CaseAttributeValue(type_name, encoded)


def test_redundant_histogram_and_triple_counts_are_validated_against_witnesses():
    triple = discover_activity_triples(log_of(("A", "A", "A", "A"))).value.triples[0]
    with pytest.raises(ValueError):
        replace(triple, occurrence_count=1)
    output = discover_case_attribute_dfg(log_of(("A", "B", "A", "B")))
    row = edge(output, "A", "B")
    distribution = row.attributes[0]
    with pytest.raises(ValueError):
        replace(
            row,
            attributes=(
                replace(
                    distribution,
                    bins=(replace(distribution.bins[0], occurrence_count=1),),
                ),
            ),
        )


def test_zero_count_invented_observed_topology_rows_are_rejected():
    with pytest.raises(ValueError):
        ActivityTriple(("A", "B", "C"), 0, 0, ())
    with pytest.raises(ValueError):
        AttributedSequenceRelation(("A", "B"), 0, 0, (), ())


@pytest.mark.parametrize("event_count", [0, 2, 4, 1000])
def test_population_event_count_is_reconciled_with_complete_context_positions(
    event_count,
):
    triples = discover_activity_triples(log_of(("A", "B", "C"))).value
    attributed = discover_case_attribute_dfg(log_of(("A", "B", "C"))).value
    with pytest.raises(ValueError, match="event population"):
        replace(triples, event_count=event_count)
    with pytest.raises(ValueError, match="event population"):
        replace(attributed, event_count=event_count)


def test_overlapping_triple_witnesses_must_agree_on_source_event_identity():
    payload = discover_activity_triples(log_of(("A", "A", "A", "A"))).value
    row = payload.triples[0]
    first, second = row.witnesses
    second = replace(second, event_ids=("invented-event", *second.event_ids[1:]))
    changed = replace(row, witnesses=(first, second))
    with pytest.raises(ValueError, match="overlapping"):
        replace(payload, triples=(changed,))


def test_complete_triple_witnesses_cannot_skip_source_positions():
    payload = discover_activity_triples(log_of(("A", "B", "C"))).value
    row = payload.triples[0]
    changed = replace(row, witnesses=(replace(row.witnesses[0], start_position=4),))
    with pytest.raises(ValueError, match="consecutive source positions"):
        replace(payload, triples=(changed,))


def test_included_node_population_requires_every_induced_edge_position():
    payload = discover_case_attribute_dfg(
        log_of(("A", "B", "C")),
        CaseAttributeDFGSpec(case_attributes=(), include_nodes=True),
    ).value
    with pytest.raises(ValueError, match="node and edge"):
        replace(payload, edges=(), edge_occurrence_count=0)


@pytest.mark.parametrize(
    "spec",
    [
        lambda: ActivityTripleSpec(max_witnesses=0),
        lambda: ActivityTripleSpec(max_witnesses=True),
        lambda: CaseAttributeDFGSpec(case_attributes=("x", "x")),
        lambda: CaseAttributeDFGSpec(include_nodes=1),
        lambda: CaseAttributeDFGSpec(max_annotation_occurrences=0),
    ],
)
def test_invalid_specifications_fail_early(spec):
    with pytest.raises((ValueError, TypeError)):
        spec()


def test_context_results_round_trip_with_typed_values_missing_and_limited_results(
    monkeypatch,
):
    import pix.results as persistence

    original = persistence._schemas
    monkeypatch.setattr(persistence, "_schemas", lambda: original() | RESULT_SCHEMAS)
    source = with_case_attributes(
        log_of(("A", "B", "A", "B"), ("A", "B")), ((CaseAttribute("x", "int", 1),), ())
    )
    results = (
        discover_activity_triples(source),
        discover_activity_triples(source, ActivityTripleSpec(max_witnesses=1)),
        discover_case_attribute_dfg(
            source, CaseAttributeDFGSpec(("x",), include_nodes=True)
        ),
        discover_case_attribute_dfg(
            source, CaseAttributeDFGSpec(("x",), max_witnesses=1)
        ),
    )
    for result in results:
        assert (
            persistence.result_from_json(persistence.result_json_bytes(result))
            == result
        )
