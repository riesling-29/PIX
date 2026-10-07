"""Hand-checkable extraction contracts, independent of upstream libraries."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.executions import discover_executions
from pix.contracts.execution import ExecutionSpec
from pix.contracts.result import ComputeStatus
from pix.ocel.model import E2O, O2O, OCEL, Event, EventType, Object, ObjectType

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def log_from(rows, object_types, *, extra_objects=(), o2o=()):
    """Rows: event ID, activity, minute offset, qualified object pairs."""
    objects = dict(object_types)
    objects.update(extra_objects)
    return OCEL(
        event_types=tuple(EventType(item) for item in sorted({row[1] for row in rows})),
        object_types=tuple(ObjectType(item) for item in sorted(set(objects.values()))),
        events=tuple(
            Event(row[0], row[1], BASE + timedelta(minutes=row[2])) for row in rows
        ),
        objects=tuple(Object(item, kind) for item, kind in sorted(objects.items())),
        e2o=tuple(E2O(row[0], item, role) for row in rows for item, role in row[3]),
        o2o=tuple(o2o),
    )


def joint_shipment():
    return log_from(
        (
            ("e1", "Receive", 0, (("O1", ""),)),
            ("e2", "Receive", 1, (("O2", ""),)),
            ("e3", "Pack", 2, (("O1", ""), ("I1", ""))),
            ("e4", "Pack", 3, (("O2", ""), ("I2", ""))),
            ("e5", "Ship", 4, (("I1", ""), ("I2", ""), ("S", ""))),
            ("e6", "Delivered", 5, (("S", ""),)),
        ),
        {"O1": "Order", "O2": "Order", "I1": "Item", "I2": "Item", "S": "Shipment"},
    )


def test_joint_shipment_components_cover_six_events_once():
    result = discover_executions(
        joint_shipment(), ExecutionSpec("connected_components")
    )
    assert result.status is ComputeStatus.COMPUTED
    assert len(result.value.executions) == 1
    assert result.value.unique_event_count == result.value.event_membership_count == 6
    assert result.value.overlapping_event_ids == ()
    assert result.value.unassigned_object_ids == ()


def test_leading_order_execution_overlap_and_boundary_are_explicit():
    result = discover_executions(
        joint_shipment(),
        ExecutionSpec("leading_object_nearest_type", leading_object_type="Order"),
    )
    data = result.value
    assert len(data.executions) == 2
    assert data.unique_event_count == 6
    assert data.event_membership_count == 8
    assert data.overlapping_event_ids == ("e5", "e6")
    assert data.overlapping_object_ids == ("S",)
    by_anchor = {item.leading_object_id: item for item in data.executions}
    assert {item.id for item in by_anchor["O1"].events} == {"e1", "e3", "e5", "e6"}
    assert {item.id for item in by_anchor["O1"].objects} == {"O1", "I1", "S"}
    assert {item.id for item in by_anchor["O1"].boundary_objects} == {"I2"}
    assert any(
        item.event == "e5" and item.object == "I2" for item in by_anchor["O1"].relations
    )
    assert all(item.object_id != "I2" for item in by_anchor["O1"].order_edges)


def test_resource_type_selection_changes_connectivity_and_identity():
    log = log_from(
        (
            ("a", "A", 0, (("O1", ""), ("R", ""))),
            ("b", "B", 1, (("O2", ""), ("R", ""))),
        ),
        {"O1": "Order", "O2": "Order", "R": "Resource"},
    )
    all_types = discover_executions(log, ExecutionSpec("connected_components"))
    orders = discover_executions(log, ExecutionSpec("connected_components", ("Order",)))
    assert len(all_types.value.executions) == 1
    assert len(orders.value.executions) == 2
    assert orders.value.excluded_object_ids == ("R",)
    assert orders.value.unassigned_object_ids == ("R",)
    assert all_types.computation_id != orders.computation_id
    assert len(orders.value.executions[0].excluded_relations) == 1


def test_multiple_qualifiers_preserved_without_duplicate_memberships():
    log = log_from(
        (
            ("a", "A", 0, (("O", "payer"), ("O", "approver"))),
            ("b", "B", 1, (("O", "payer"),)),
        ),
        {"O": "Order"},
    )
    result = discover_executions(log, ExecutionSpec("connected_components"))
    scope = result.value.executions[0]
    assert len(scope.relations) == 3
    assert len(scope.order_edges) == 1
    assert result.value.event_membership_count == 2
    filtered = discover_executions(
        log, ExecutionSpec("connected_components", qualifiers=("approver",))
    )
    assert len(filtered.value.executions) == 2
    assert filtered.value.isolated_event_ids == ("b",)


def test_no_qualifiers_and_empty_qualifier_are_distinct_selections():
    log = log_from(
        (("a", "A", 0, (("O", ""),)), ("b", "B", 1, (("O", ""),))),
        {"O": "Order"},
    )
    none = discover_executions(
        log, ExecutionSpec("connected_components", qualifiers=())
    )
    empty = discover_executions(
        log, ExecutionSpec("connected_components", qualifiers=("",))
    )
    assert len(none.value.executions) == 2
    assert len(empty.value.executions) == 1
    assert none.computation_id != empty.computation_id


def test_o2o_never_implicitly_merges_executions():
    log = log_from(
        (("a", "A", 0, (("O1", ""),)), ("b", "B", 1, (("O2", ""),))),
        {"O1": "Order", "O2": "Order"},
        o2o=(O2O("O1", "O2", "related"),),
    )
    result = discover_executions(log, ExecutionSpec("connected_components"))
    assert len(result.value.executions) == 2
    leading = discover_executions(
        log, ExecutionSpec("leading_object_nearest_type", leading_object_type="Order")
    )
    assert all(len(item.objects) == 1 for item in leading.value.executions)


def test_isolated_event_and_eventless_object_are_not_lost():
    log = log_from((("alone", "A", 0, ()),), {"unused": "Order"})
    connected = discover_executions(log, ExecutionSpec("connected_components"))
    assert len(connected.value.executions) == 1
    assert connected.value.isolated_event_ids == ("alone",)
    assert connected.value.isolated_object_ids == ("unused",)
    assert connected.value.unassigned_object_ids == ("unused",)
    leading = discover_executions(
        log, ExecutionSpec("leading_object_nearest_type", leading_object_type="Order")
    )
    assert len(leading.value.executions) == 1
    assert leading.value.executions[0].events == ()
    assert leading.value.unassigned_event_ids == ("alone",)
    assert leading.value.unassigned_object_ids == ()


def test_timestamps_do_not_invent_order_for_tied_object():
    log = log_from(
        (("a", "A", 0, (("O", ""),)), ("b", "B", 0, (("O", ""),))),
        {"O": "Order"},
    )
    result = discover_executions(log, ExecutionSpec("connected_components"))
    assert result.status is ComputeStatus.COMPUTED
    execution = result.value.executions[0]
    assert execution.order_status == "unavailable"
    assert execution.order_edges == ()
    assert execution.order_ties[0].event_ids == ("a", "b")
    assert result.issues[0].code == "ambiguous_event_order"
    resolved = discover_executions(
        log, ExecutionSpec("connected_components", tie_policy="event_id")
    )
    edge = resolved.value.executions[0].order_edges[0]
    assert (edge.source_event, edge.target_event, edge.tie_broken) == ("a", "b", True)
    assert resolved.value.executions[0].order_status == "complete"


def test_equal_times_across_distinct_objects_do_not_fail_order():
    log = log_from(
        (("a", "A", 0, (("O1", ""),)), ("b", "B", 0, (("O2", ""),))),
        {"O1": "Order", "O2": "Order"},
    )
    result = discover_executions(log, ExecutionSpec("connected_components"))
    assert all(item.order_status == "complete" for item in result.value.executions)


def test_input_permutations_and_spec_selection_order_are_deterministic():
    log = joint_shipment()
    shuffled = replace(
        log,
        events=tuple(reversed(log.events)),
        objects=tuple(reversed(log.objects)),
        e2o=tuple(reversed(log.e2o)),
    )
    first = discover_executions(
        log, ExecutionSpec("connected_components", ("Order", "Item"))
    )
    second = discover_executions(
        shuffled, ExecutionSpec("connected_components", ("Item", "Order"))
    )
    assert first == second
    with pytest.raises(FrozenInstanceError):
        first.value.executions = ()


def test_empty_dataset_and_empty_type_selection():
    empty = discover_executions(OCEL(), ExecutionSpec("connected_components"))
    assert empty.status is ComputeStatus.COMPUTED
    assert empty.value.executions == ()
    assert empty.value.unique_event_count == 0
    none = discover_executions(
        joint_shipment(), ExecutionSpec("connected_components", ())
    )
    assert len(none.value.executions) == 6
    assert none.value.unique_object_count == 0


def test_unknown_type_is_unavailable_and_invalid_log_is_invalid_input():
    result = discover_executions(
        joint_shipment(), ExecutionSpec("connected_components", ("Unknown",))
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[0].code == "unknown_object_type"
    bad = replace(joint_shipment(), e2o=(E2O("missing", "O1", ""),))
    invalid = discover_executions(bad, ExecutionSpec("connected_components"))
    assert invalid.status is ComputeStatus.INVALID_INPUT
    assert invalid.value is None


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"method": "default"}, ValueError),
        ({"method": "leading_object_nearest_type"}, TypeError),
        (
            {"method": "connected_components", "leading_object_type": "Order"},
            ValueError,
        ),
        (
            {
                "method": "leading_object_nearest_type",
                "leading_object_type": "Order",
                "object_types": (),
            },
            ValueError,
        ),
        ({"method": "connected_components", "qualifiers": [""]}, TypeError),
        ({"method": "connected_components", "qualifiers": ("\ud800",)}, ValueError),
        ({"method": "connected_components", "tie_policy": "input_order"}, ValueError),
    ],
)
def test_spec_rejects_undefined_or_mutable_policies(kwargs, error):
    with pytest.raises(error):
        ExecutionSpec(**kwargs)


def test_nearest_type_includes_all_objects_at_first_depth_only():
    log = log_from(
        (
            ("a", "A", 0, (("O1", ""), ("I1", ""), ("I2", ""))),
            ("b", "B", 1, (("I1", ""), ("S", ""))),
            ("c", "C", 2, (("S", ""), ("I3", ""), ("O2", ""))),
        ),
        {
            "O1": "Order",
            "O2": "Order",
            "I1": "Item",
            "I2": "Item",
            "I3": "Item",
            "S": "Shipment",
        },
    )
    result = discover_executions(
        log, ExecutionSpec("leading_object_nearest_type", leading_object_type="Order")
    )
    scope = next(
        item for item in result.value.executions if item.leading_object_id == "O1"
    )
    assert {item.id for item in scope.objects} == {"O1", "I1", "I2", "S"}
    assert {item.id for item in scope.boundary_objects} == {"I3", "O2"}
    assert {item.id for item in scope.events} == {"a", "b", "c"}


def test_leading_boundary_and_filtered_roles_keep_separate_evidence():
    log = joint_shipment()
    log = replace(log, e2o=log.e2o + (E2O("e5", "S", "observer"),))
    result = discover_executions(
        log,
        ExecutionSpec(
            "leading_object_nearest_type",
            qualifiers=("",),
            leading_object_type="Order",
        ),
    )
    execution = next(
        item for item in result.value.executions if item.leading_object_id == "O1"
    )
    assert {
        (item.event, item.object, item.qualifier)
        for item in execution.excluded_relations
    } == {("e5", "S", "observer")}
    assert any(
        item.object == "I2" and item.event == "e5" for item in execution.relations
    )
    memberships = {
        item.entity_id: item.execution_ids for item in result.value.object_memberships
    }
    assert execution.execution_id not in memberships["I2"]
    assert result.value.object_membership_count == 6


def test_public_execution_payload_rejects_mutable_collections():
    value = discover_executions(
        joint_shipment(), ExecutionSpec("connected_components")
    ).value
    with pytest.raises(TypeError, match="executions must be a tuple"):
        replace(value, executions=list(value.executions))
    with pytest.raises(TypeError, match="relations must be a tuple"):
        replace(value.executions[0], relations=list(value.executions[0].relations))
    with pytest.raises(TypeError, match="must be an integer"):
        replace(value, unique_event_count=True)
