"""Hand-counted graph layers, repeated paths, and preserved relation evidence."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.ocdfg import discover_ocdfg
from pix.contracts.analysis import OCDFGSpec
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, O2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def shared_repeating_log() -> OCEL:
    """O1/O2 share one A→B; O1 repeats it later; parcel P1 shares first only."""

    return OCEL(
        event_types=(EventType("A"), EventType("B"), EventType("Check")),
        object_types=(ObjectType("order"), ObjectType("parcel"), ObjectType("unused")),
        events=tuple(
            Event(event_id, activity, ORIGIN + timedelta(seconds=index))
            for index, (event_id, activity) in enumerate(
                (
                    ("a1", "A"),
                    ("b1", "B"),
                    ("a2", "A"),
                    ("b2", "B"),
                    ("check", "Check"),
                )
            )
        ),
        objects=(
            Object("o1", "order"),
            Object("o2", "order"),
            Object("o3", "order"),
            Object("isolated", "order"),
            Object("p1", "parcel"),
        ),
        e2o=(
            E2O("a1", "o1", "flow"),
            E2O("a1", "o1", "audit"),
            E2O("b1", "o1", "flow"),
            E2O("a2", "o1", "flow"),
            E2O("b2", "o1", "flow"),
            E2O("a1", "o2", "flow"),
            E2O("b1", "o2", "flow"),
            E2O("a1", "p1", "flow"),
            E2O("b1", "p1", "flow"),
            E2O("check", "o3", "audit"),
        ),
        o2o=(O2O("o1", "o3", "related"),),
    )


def test_shared_and_repeated_pairs_distinguish_all_three_count_units():
    log = shared_repeating_log()
    shared_only = replace(
        log,
        events=tuple(event for event in log.events if event.id in ("a1", "b1")),
        e2o=tuple(relation for relation in log.e2o if relation.event in ("a1", "b1")),
    )
    shared_edge = (
        discover_ocdfg(shared_only, OCDFGSpec(("order",))).value.graphs[0].edges[0]
    )
    assert (
        shared_edge.event_pair_count,
        shared_edge.unique_object_count,
        shared_edge.occurrence_count,
    ) == (1, 2, 2)

    result = discover_ocdfg(log, OCDFGSpec(("order",)))
    assert result.status is ComputeStatus.COMPUTED
    graph = result.value.graphs[0]
    ab = next(edge for edge in graph.edges if edge.source_activity == "A")
    assert (ab.event_pair_count, ab.unique_object_count, ab.occurrence_count) == (
        2,
        2,
        3,
    )
    assert {
        (item.object_id, item.source_event_id, item.target_event_id)
        for item in ab.evidence
    } == {("o1", "a1", "b1"), ("o2", "a1", "b1"), ("o1", "a2", "b2")}
    first = next(
        item
        for item in ab.evidence
        if item.object_id == "o1" and item.source_event_id == "a1"
    )
    assert {relation.qualifier for relation in first.source_relations} == {
        "flow",
        "audit",
    }


def test_selected_type_layers_preserve_boundaries_isolates_and_unique_events():
    result = discover_ocdfg(
        shared_repeating_log(),
        OCDFGSpec(("unused", "parcel", "order")),
    )
    assert [graph.object_type for graph in result.value.graphs] == [
        "order",
        "parcel",
        "unused",
    ]
    order, parcel, unused = result.value.graphs
    assert order.object_count == 4
    assert order.empty_object_ids == ("isolated",)
    assert {
        item.activity: item.event_occurrence_count for item in order.activities
    } == {
        "A": 3,
        "B": 3,
        "Check": 1,
    }
    assert {item.activity: item.distinct_event_ids for item in order.activities}[
        "A"
    ] == ("a1", "a2")
    assert {item.activity: len(item.evidence) for item in order.starts} == {
        "A": 2,
        "Check": 1,
    }
    assert {item.activity: len(item.evidence) for item in order.ends} == {
        "B": 2,
        "Check": 1,
    }
    assert [(edge.source_activity, edge.target_activity) for edge in order.edges] == [
        ("A", "B"),
        ("B", "A"),
    ]
    assert parcel.edges[0].occurrence_count == 1
    assert parcel.edges[0].object_type == "parcel"
    assert unused.object_count == 0
    assert (unused.activities, unused.edges, unused.starts, unused.ends) == (
        (),
        (),
        (),
        (),
    )


def test_qualifier_view_preserves_excluded_objects_but_does_not_create_o2o_edges():
    result = discover_ocdfg(
        shared_repeating_log(),
        OCDFGSpec(("order",), qualifiers=("flow",)),
    )
    order = result.value.graphs[0]
    assert order.empty_object_ids == ("isolated", "o3")
    assert {item.activity for item in order.activities} == {"A", "B"}
    assert all(
        relation.qualifier == "flow"
        for edge in order.edges
        for evidence in edge.evidence
        for relation in evidence.source_relations
    )


def test_selecting_no_qualifiers_is_not_the_same_as_selecting_all():
    result = discover_ocdfg(
        shared_repeating_log(),
        OCDFGSpec(("order",), qualifiers=()),
    )
    order = result.value.graphs[0]
    assert order.empty_object_ids == ("isolated", "o1", "o2", "o3")
    assert (order.activities, order.edges, order.starts, order.ends) == ((), (), (), ())


def test_unknown_type_rejects_whole_multitype_request_instead_of_partial_graph():
    result = discover_ocdfg(
        shared_repeating_log(),
        OCDFGSpec(("order", "undeclared")),
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert any(issue.code == "unknown_object_type" for issue in result.issues)


def test_ambiguous_selected_type_rejects_whole_graph_until_policy_explicit():
    base = shared_repeating_log()
    events = tuple(
        replace(event, time=ORIGIN) if event.id == "b1" else event
        for event in base.events
    )
    log = replace(base, events=events)
    rejected = discover_ocdfg(log, OCDFGSpec(("order", "parcel")))
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.value is None
    computed = discover_ocdfg(
        log, OCDFGSpec(("order", "parcel"), tie_policy="event_id")
    )
    assert computed.status is ComputeStatus.COMPUTED
    assert computed.value.graphs[0].edges[0].occurrence_count == 3


def test_input_permutations_and_equivalent_type_selections_preserve_full_result():
    log = shared_repeating_log()
    first = discover_ocdfg(log, OCDFGSpec(("order", "parcel")))
    reversed_log = replace(
        log,
        events=log.events[::-1],
        objects=log.objects[::-1],
        e2o=log.e2o[::-1],
        event_types=log.event_types[::-1],
        object_types=log.object_types[::-1],
    )
    second = discover_ocdfg(reversed_log, OCDFGSpec(("parcel", "order", "order")))
    assert first == second
    assert len(first.parent_computation_ids) == 2


def test_invalid_input_is_not_an_empty_computed_graph():
    result = discover_ocdfg(None, OCDFGSpec(("order",)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.source_digest is None


def test_request_requires_an_ocdfg_spec():
    with pytest.raises(TypeError):
        discover_ocdfg(shared_repeating_log(), None)
