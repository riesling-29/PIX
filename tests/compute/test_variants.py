"""Exact variant contracts and hand-checkable incidence counterexamples."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.executions import discover_executions
from pix.compute.variants import _canonical_form, _Graph, _refine, discover_variants
from pix.contracts.execution import (
    EventOrderEdge,
    ExecutionEvent,
    ExecutionObject,
    ExecutionRelation,
    ExecutionSet,
    ExecutionSpec,
    ProcessExecution,
    VariantSpec,
)
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

BASE = datetime(2026, 9, 9, tzinfo=timezone.utc)


def execution(
    name,
    rows,
    *,
    activities=None,
    types=None,
    qualifier="participant",
    boundary=(),
    leading=None,
    isolated=(),
):
    """Small ordered execution fixture; rows list participating object IDs."""
    event_ids = tuple(f"{name}:e{index}" for index in range(len(rows)))
    object_ids = sorted(set().union(*(set(row) for row in rows), set(isolated)))
    types = types or {}
    objects = tuple(ExecutionObject(oid, types.get(oid, "T")) for oid in object_ids)
    edges = []
    for obj in objects:
        if obj.id in boundary:
            continue
        positions = [eid for eid, row in zip(event_ids, rows) if obj.id in row]
        edges.extend(
            EventOrderEdge(a, b, obj.id) for a, b in zip(positions, positions[1:])
        )
    return ProcessExecution(
        execution_id=name,
        leading_object_id=leading,
        events=tuple(
            ExecutionEvent(
                eid,
                activities[index] if activities else "A",
                BASE + timedelta(minutes=index),
            )
            for index, eid in enumerate(event_ids)
        ),
        objects=tuple(obj for obj in objects if obj.id not in boundary),
        boundary_objects=tuple(obj for obj in objects if obj.id in boundary),
        relations=tuple(
            ExecutionRelation(eid, oid, qualifier)
            for eid, row in zip(event_ids, rows)
            for oid in sorted(row)
        ),
        excluded_relations=(),
        order_edges=tuple(edges),
        order_status="complete",
        order_ties=(),
    )


def parent(*executions, parent_id="extraction:one", source="source:one"):
    payload = ExecutionSet(
        executions=tuple(executions),
        event_memberships=(),
        object_memberships=(),
        unassigned_event_ids=(),
        unassigned_object_ids=(),
        isolated_event_ids=(),
        isolated_object_ids=(),
        excluded_object_ids=(),
        overlapping_event_ids=(),
        overlapping_object_ids=(),
        unique_event_count=0,
        event_membership_count=0,
        unique_object_count=0,
        object_membership_count=0,
    )
    return ComputationResult(
        operator_id="pix.extract_executions",
        operator_version="1.0.0",
        source_digest=source,
        spec=ExecutionSpec(method="connected_components"),
        status=ComputeStatus.COMPUTED,
        value=payload,
        issues=(),
        computation_id=parent_id,
        parent_computation_ids=(),
    )


def value(*executions, spec=None):
    result = discover_variants(parent(*executions), spec or VariantSpec())
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def test_global_object_identity_distinguishes_domain_example_l_and_m():
    left = execution("L", ({"x", "a"}, {"x", "b"}, {"x", "c"}))
    right = execution("M", ({"x", "a"}, {"x", "y"}, {"y", "c"}))
    renamed = execution("renamed", ({"q", "z"}, {"q", "r"}, {"q", "s"}))
    variants = value(left, right, renamed).variants
    assert sorted(group.frequency for group in variants) == [1, 2]
    assert next(group for group in variants if group.frequency == 2).execution_ids == (
        "L",
        "renamed",
    )


def test_source_record_permutation_does_not_change_equivalence():
    first = execution("a", ({"x", "y"}, {"x"}), activities=("A", "B"))
    shuffled = replace(
        first,
        execution_id="b",
        events=first.events[::-1],
        objects=first.objects[::-1],
        relations=first.relations[::-1],
        order_edges=first.order_edges[::-1],
    )
    assert value(first, shuffled).variants[0].frequency == 2


def test_repeated_activities_preserve_selected_order():
    aba = execution("aba", ({"x"},) * 3, activities=("A", "B", "A"))
    aab = execution("aab", ({"x"},) * 3, activities=("A", "A", "B"))
    assert len(value(aba, aab).variants) == 2


@pytest.mark.parametrize("role", ["", "recipient"])
def test_qualified_incidence_is_part_of_equivalence(role):
    first = execution("first", ({"x"},))
    other = execution("other", ({"y"},), qualifier=role)
    assert len(value(first, other).variants) == 2


def test_multiple_qualifiers_are_not_collapsed():
    first = execution("first", ({"x"},))
    other = replace(
        first,
        execution_id="other",
        relations=first.relations
        + (ExecutionRelation(first.events[0].id, "x", "owner"),),
    )
    assert len(value(first, other).variants) == 2


def test_object_type_is_part_of_equivalence():
    first = execution("first", ({"x"},), types={"x": "order"})
    other = execution("other", ({"y"},), types={"y": "shipment"})
    assert len(value(first, other).variants) == 2


def test_isolated_events_are_preserved():
    first = execution("first", ({"x"},))
    other = execution("other", ({"x"}, set()))
    assert len(value(first, other).variants) == 2


def test_isolated_inside_objects_are_preserved():
    first = execution("first", ({"x"},))
    other = execution("other", ({"x"},), isolated=("y",))
    assert len(value(first, other).variants) == 2


def test_boundary_scope_role_is_preserved():
    first = execution("first", ({"x", "y"},), boundary=("y",))
    other = execution("other", ({"x", "y"},))
    assert len(value(first, other).variants) == 2


def test_only_active_boundary_objects_affect_equivalence():
    first = execution("first", ({"x"},))
    other = replace(
        first,
        execution_id="other",
        boundary_objects=(ExecutionObject("outside", "T"),),
        excluded_relations=(
            ExecutionRelation(first.events[0].id, "outside", "hidden"),
        ),
    )
    assert value(first, other).variants[0].frequency == 2


def test_leading_anchor_role_cannot_be_swapped_between_structural_positions():
    first = execution("first", ({"x", "y"}, {"x"}), leading="x")
    other = execution("other", ({"x", "y"}, {"x"}), leading="y")
    assert len(value(first, other).variants) == 2


def test_edge_direction_is_preserved():
    first = execution("first", ({"x"}, {"x"}), activities=("A", "B"))
    edge = first.order_edges[0]
    other = replace(
        first,
        execution_id="other",
        order_edges=(
            EventOrderEdge(edge.target_event, edge.source_event, edge.object_id),
        ),
    )
    assert len(value(first, other).variants) == 2


def test_absolute_time_and_tie_annotation_are_excluded():
    first = execution("first", ({"x"}, {"x"}), activities=("A", "B"))
    other = replace(
        first,
        execution_id="other",
        events=tuple(
            replace(event, time=event.time + timedelta(days=30))
            for event in first.events
        ),
        order_edges=tuple(replace(edge, tie_broken=True) for edge in first.order_edges),
    )
    assert value(first, other).variants[0].frequency == 2


def test_canonicalizer_preserves_ternary_order_correlation():
    # Relation-codec test, not an OCEL fixture: these partial orders intentionally
    # isolate the object coordinate from the flattened event-edge projection.
    labels = tuple(("event", activity) for activity in "ABCD") + (
        ("object", "T"),
        ("object", "T"),
    )
    incidence = tuple(("e2o", "", (event, obj)) for event in range(4) for obj in (4, 5))
    left = ((0, 1, 4), (1, 2, 4), (0, 2, 5), (2, 3, 5))
    right = ((0, 1, 4), (2, 3, 4), (0, 2, 5), (1, 2, 5))
    assert sorted((a, b) for a, b, _ in left) == sorted((a, b) for a, b, _ in right)
    l_graph = _Graph(labels, incidence + tuple(("order", "", row) for row in left))
    r_graph = _Graph(labels, incidence + tuple(("order", "", row) for row in right))
    assert _canonical_form(l_graph, 100)[0] != _canonical_form(r_graph, 100)[0]


def test_refinement_collision_is_resolved_by_full_canonical_search():
    labels = (("event", "A"),) * 4 + (("object", "T"),) * 4
    cycle = ((0, 4), (0, 5), (1, 5), (1, 6), (2, 6), (2, 7), (3, 7), (3, 4))
    squares = ((0, 4), (0, 5), (1, 4), (1, 5), (2, 6), (2, 7), (3, 6), (3, 7))
    left = _Graph(labels, tuple(("e2o", "", pair) for pair in cycle))
    right = _Graph(labels, tuple(("e2o", "", pair) for pair in squares))
    assert tuple(map(len, _refine(left))) == tuple(map(len, _refine(right))) == (4, 4)
    assert _canonical_form(left, 576)[0] != _canonical_form(right, 576)[0]


def test_symmetric_search_limit_returns_no_partial_exact_groups():
    easy = execution("a_easy", ({"x"},))
    symmetric = execution("z_hard", ({"a", "b", "c", "d", "e"},))
    result = discover_variants(
        parent(easy, symmetric), VariantSpec(max_search_states=5)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "limit_exceeded"


def test_search_budget_is_shared_across_executions():
    first = execution("first", ({"x"},))
    other = execution("other", ({"y"},))
    result = discover_variants(parent(first, other), VariantSpec(max_search_states=1))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_search_can_complete_exactly_at_budget():
    symmetric = execution("two", ({"x", "y"},))
    result = value(symmetric, spec=VariantSpec(max_search_states=2))
    assert result.exact is True
    assert result.search_states == 2


@pytest.mark.parametrize("change", ["parent", "source", "spec"])
def test_artifact_identity_includes_provenance_and_spec(change):
    first = execution("first", ({"x"},))
    left_parent = parent(first)
    right_parent = parent(
        first,
        parent_id="extraction:two" if change == "parent" else "extraction:one",
        source="source:two" if change == "source" else "source:one",
    )
    left = discover_variants(left_parent, VariantSpec())
    right = discover_variants(
        right_parent,
        VariantSpec(max_search_states=10) if change == "spec" else VariantSpec(),
    )
    assert (
        left.value.variants[0].canonical_signature
        == right.value.variants[0].canonical_signature
    )
    assert left.value.variants[0].variant_id != right.value.variants[0].variant_id
    assert left.computation_id != right.computation_id
    assert right.parent_computation_ids == (right_parent.computation_id,)


def test_unavailable_order_refuses_variant_computation():
    first = replace(execution("first", ({"x"},)), order_status="unavailable")
    result = discover_variants(parent(first), VariantSpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "order_unavailable"
    assert result.value is None


def test_failed_parent_does_not_become_empty_success():
    failed = replace(
        parent(),
        status=ComputeStatus.UNAVAILABLE,
        value=None,
        issues=(ComputeIssue("input_unavailable", "Fixture failed."),),
    )
    result = discover_variants(failed, VariantSpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "parent_not_complete"
    assert result.issues[1:] == failed.issues
    assert result.parent_computation_ids == (failed.computation_id,)


def test_invalid_ocel_source_remains_invalid_with_original_relation_diagnostic():
    log = OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("Order"),),
        events=(Event("e", "A", BASE),),
        objects=(Object("O", "Order"),),
        e2o=(E2O("missing-event", "O", "owner"),),
    )
    extracted = discover_executions(log, ExecutionSpec("connected_components"))
    assert extracted.status is ComputeStatus.INVALID_INPUT
    assert extracted.issues
    result = discover_variants(extracted, VariantSpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None
    assert result.issues[0].code == "parent_not_complete"
    assert "invalid_input" in result.issues[0].message
    assert result.issues[1:] == extracted.issues
    assert result.source_digest is result.computation_id is None
    assert result.parent_computation_ids == ()


def test_unknown_object_type_keeps_original_selection_diagnostic_and_identity():
    log = OCEL(object_types=(ObjectType("Order"),))
    extracted = discover_executions(
        log, ExecutionSpec("connected_components", object_types=("Unknown",))
    )
    assert extracted.status is ComputeStatus.UNAVAILABLE
    result = discover_variants(extracted, VariantSpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "parent_not_complete"
    assert result.issues[1:] == extracted.issues
    assert result.issues[1].code == "unknown_object_type"
    assert "Unknown" in result.issues[1].message
    assert result.parent_computation_ids == (extracted.computation_id,)
    assert result.source_digest == extracted.source_digest


def test_partial_extraction_cannot_produce_exact_groups_and_keeps_coverage_issue():
    partial = replace(
        parent(execution("partial", ({"x"},))),
        status=ComputeStatus.PARTIAL,
        issues=(
            ComputeIssue("incomplete_membership", "One execution was not extracted."),
        ),
    )
    result = discover_variants(partial, VariantSpec())
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert result.issues[0].code == "parent_not_complete"
    assert "partial" in result.issues[0].message
    assert result.issues[1:] == partial.issues
    assert result.parent_computation_ids == (partial.computation_id,)


def test_empty_successful_execution_set_has_zero_groups():
    result = value()
    assert result.variants == ()
    assert result.execution_count == result.search_states == 0


@pytest.mark.parametrize(
    "method", ["connected_components", "leading_object_nearest_type"]
)
def test_canonical_log_to_execution_to_variant_keeps_parent_provenance(method):
    log = OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("Order"),),
        events=tuple(
            Event(
                f"e{index}",
                "A" if index % 2 == 0 else "B",
                BASE + timedelta(minutes=index),
            )
            for index in range(4)
        ),
        objects=(Object("O1", "Order"), Object("O2", "Order")),
        e2o=tuple(
            E2O(f"e{index}", "O1" if index < 2 else "O2", "owner") for index in range(4)
        ),
    )
    extraction_spec = ExecutionSpec(
        method,
        leading_object_type="Order"
        if method == "leading_object_nearest_type"
        else None,
    )
    extracted = discover_executions(log, extraction_spec)
    result = discover_variants(extracted, VariantSpec())
    assert result.status is ComputeStatus.COMPUTED
    assert result.parent_computation_ids == (extracted.computation_id,)
    assert result.source_digest == extracted.source_digest
    assert len(result.value.variants) == 1
    assert result.value.variants[0].frequency == 2
    assert set(result.value.variants[0].execution_ids) == {
        item.execution_id for item in extracted.value.executions
    }


def test_real_timestamp_tie_requires_explicit_order_before_exact_variants():
    log = OCEL(
        event_types=(EventType("A"), EventType("B")),
        object_types=(ObjectType("Order"),),
        events=(Event("a", "A", BASE), Event("b", "B", BASE)),
        objects=(Object("O", "Order"),),
        e2o=(E2O("a", "O", ""), E2O("b", "O", "")),
    )
    ambiguous = discover_executions(log, ExecutionSpec("connected_components"))
    rejected = discover_variants(ambiguous, VariantSpec())
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.value is None
    assert rejected.issues[0].code == "order_unavailable"
    assert rejected.issues[1:] == ambiguous.issues
    assert any(issue.code == "ambiguous_event_order" for issue in rejected.issues)
    assert rejected.parent_computation_ids == (ambiguous.computation_id,)
    explicit = discover_executions(
        log, ExecutionSpec("connected_components", tie_policy="event_id")
    )
    result = discover_variants(explicit, VariantSpec())
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.variants[0].frequency == 1


def test_missing_relation_endpoint_is_invalid_input():
    first = execution("first", ({"x"},))
    malformed = replace(first, relations=(ExecutionRelation("missing", "x", ""),))
    result = discover_variants(parent(malformed), VariantSpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "invalid_execution_graph"


def test_duplicate_execution_identifiers_are_invalid_input():
    first = execution("first", ({"x"},))
    result = discover_variants(parent(first, first), VariantSpec())
    assert result.status is ComputeStatus.INVALID_INPUT


@pytest.mark.parametrize("shape", ["missing", "branch", "cycle", "disconnected_cycle"])
def test_complete_order_requires_one_path_through_all_object_events(shape):
    first = execution("first", ({"x"},) * 4)
    events = tuple(event.id for event in first.events)
    pairs = {
        "missing": (),
        "branch": ((0, 1), (0, 2), (2, 3)),
        "cycle": ((0, 1), (1, 2), (2, 3), (3, 0)),
        "disconnected_cycle": ((0, 1), (2, 3), (3, 2)),
    }[shape]
    malformed = replace(
        first,
        order_edges=tuple(
            EventOrderEdge(events[source], events[target], "x")
            for source, target in pairs
        ),
    )
    result = discover_variants(parent(malformed), VariantSpec())
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "invalid_execution_graph"
    assert result.value is None


@pytest.mark.parametrize(
    "kwargs,error",
    [
        ({"max_search_states": 0}, ValueError),
        ({"max_search_states": True}, TypeError),
        ({"equivalence": "hash_only"}, ValueError),
    ],
)
def test_variant_spec_rejects_unsupported_or_unbounded_requests(kwargs, error):
    with pytest.raises(error):
        VariantSpec(**kwargs)
