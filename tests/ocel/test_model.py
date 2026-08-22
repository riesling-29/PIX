from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    OCEL_EPOCH,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)

T0 = datetime(2026, 7, 28, 9, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)


def test_canonical_model_preserves_ocel_semantics() -> None:
    event_type = EventType(
        "create order",
        (
            Attribute(
                "amount",
                ValueType.FLOAT,
            ),
        ),
    )
    object_type = ObjectType(
        "order",
        (
            Attribute(
                "status",
                ValueType.STRING,
            ),
        ),
    )

    related_event = Event(
        "e1",
        "create order",
        T0,
        (
            EventAttr(
                "amount",
                1200.0,
            ),
        ),
    )
    disconnected_event = Event(
        "e2",
        "create order",
        T1,
    )

    related_object = Object(
        "o1",
        "order",
        (
            ObjectAttr(
                "status",
                "created",
                OCEL_EPOCH,
            ),
            ObjectAttr(
                "status",
                "approved",
                T1,
            ),
        ),
    )
    disconnected_object = Object(
        "o2",
        "order",
    )

    log = OCEL(
        event_types=(event_type,),
        object_types=(object_type,),
        events=(
            related_event,
            disconnected_event,
        ),
        objects=(
            related_object,
            disconnected_object,
        ),
        e2o=(
            E2O(
                "e1",
                "o1",
                "item",
            ),
            E2O(
                "e1",
                "o1",
                "target",
            ),
        ),
        o2o=(
            O2O(
                "o1",
                "o2",
                "parent",
            ),
            O2O(
                "o1",
                "o2",
                "reference",
            ),
        ),
    )

    assert log.events == (
        related_event,
        disconnected_event,
    )
    assert log.objects == (
        related_object,
        disconnected_object,
    )

    assert {relation.qualifier for relation in log.e2o} == {
        "item",
        "target",
    }

    assert {relation.qualifier for relation in log.o2o} == {
        "parent",
        "reference",
    }

    assert related_object.attributes[0].time == OCEL_EPOCH
    assert related_object.attributes[1].time == T1


def test_model_is_frozen() -> None:
    event = Event(
        "e1",
        "create",
        T0,
    )

    with pytest.raises(FrozenInstanceError):
        event.id = "changed"  # type: ignore[misc]


def test_collection_fields_require_tuples() -> None:
    with pytest.raises(
        TypeError,
        match="Event.attributes must be a tuple",
    ):
        Event(
            "e1",
            "create",
            T0,
            [],  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="OCEL.events must be a tuple",
    ):
        OCEL(
            events=[],  # type: ignore[arg-type]
        )


def test_event_requires_timezone_aware_time() -> None:
    with pytest.raises(
        ValueError,
        match="timezone",
    ):
        Event(
            "e1",
            "create",
            datetime(2026, 7, 28, 9, 0),
        )


def test_time_attribute_values_require_timezone() -> None:
    with pytest.raises(
        ValueError,
        match="timezone",
    ):
        EventAttr(
            "recorded_at",
            datetime(2026, 7, 28, 9, 0),
        )


def test_event_attribute_names_must_be_unique() -> None:
    with pytest.raises(
        ValueError,
        match="Event attribute names",
    ):
        Event(
            "e1",
            "create",
            T0,
            (
                EventAttr(
                    "amount",
                    1,
                ),
                EventAttr(
                    "amount",
                    2,
                ),
            ),
        )


def test_object_history_allows_same_name_at_different_times() -> None:
    obj = Object(
        "o1",
        "order",
        (
            ObjectAttr(
                "status",
                "created",
                OCEL_EPOCH,
            ),
            ObjectAttr(
                "status",
                "approved",
                T1,
            ),
        ),
    )

    assert len(obj.attributes) == 2


def test_object_history_rejects_same_name_at_same_time() -> None:
    with pytest.raises(
        ValueError,
        match="Object attribute assignments",
    ):
        Object(
            "o1",
            "order",
            (
                ObjectAttr(
                    "status",
                    "created",
                    T0,
                ),
                ObjectAttr(
                    "status",
                    "approved",
                    T0,
                ),
            ),
        )


def test_canonical_values_reject_null_and_containers() -> None:
    with pytest.raises(
        TypeError,
        match="EventAttr.value",
    ):
        EventAttr(
            "missing",
            None,  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="EventAttr.value",
    ):
        EventAttr(
            "payload",
            {"x": 1},  # type: ignore[arg-type]
        )


def test_float_values_must_be_finite() -> None:
    with pytest.raises(
        ValueError,
        match="finite",
    ):
        EventAttr(
            "amount",
            float("nan"),
        )


def test_ids_and_type_names_must_not_be_blank() -> None:
    with pytest.raises(
        ValueError,
        match="Event.id",
    ):
        Event(
            "   ",
            "create",
            T0,
        )

    with pytest.raises(
        ValueError,
        match="ObjectType.name",
    ):
        ObjectType("")


def test_qualifier_must_be_a_string_but_may_be_empty() -> None:
    relation = E2O(
        "e1",
        "o1",
        "",
    )

    assert relation.qualifier == ""

    with pytest.raises(
        TypeError,
        match="E2O.qualifier",
    ):
        E2O(
            "e1",
            "o1",
            1,  # type: ignore[arg-type]
        )


def test_ocel_information_and_queries_preserve_relation_evidence() -> None:
    log = OCEL(
        event_types=(EventType("create"), EventType("approve")),
        object_types=(ObjectType("order"),),
        events=(
            Event("e1", "create", T0),
            Event("e2", "approve", T1),
            Event("e3", "approve", T1),
        ),
        objects=(Object("o1", "order"), Object("o2", "order")),
        e2o=(
            E2O("e1", "o1", "target"),
            E2O("e1", "o1", "audit"),
            E2O("e2", "o1", "target"),
        ),
        o2o=(
            O2O("o1", "o2", "parent"),
            O2O("o2", "o1", "reference"),
        ),
    )

    assert log.get_event("e1").type == "create"
    assert log.get_object("o1").type == "order"
    assert tuple(event.id for event in log.events_by_type("approve")) == (
        "e2",
        "e3",
    )
    assert tuple(obj.id for obj in log.objects_for_event("e1")) == ("o1",)
    assert tuple(event.id for event in log.events_for_object("o1")) == (
        "e1",
        "e2",
    )
    assert len(log.e2o_for_event("e1")) == 2
    assert len(log.e2o_for_event("e1", qualifier="audit")) == 1
    assert log.outgoing_o2o("o1")[0].target == "o2"
    assert log.incoming_o2o("o1")[0].source == "o2"

    info = log.info()
    assert info.event_count == 3
    assert info.object_count == 2
    assert info.event_counts_by_type == (("approve", 2), ("create", 1))
    assert info.disconnected_event_count == 1
    assert info.objects_without_e2o_count == 1
    assert log.describe()["earliestEventTime"] == "2026-07-28T09:00:00Z"
    assert log.summary() == (
        "OCEL(events=3, objects=2, event_types=2, object_types=1, "
        "e2o=3, o2o=2)"
    )


def test_ocel_id_queries_reject_missing_or_ambiguous_entities() -> None:
    with pytest.raises(KeyError, match="unknown event id"):
        OCEL().get_event("missing")

    duplicate = OCEL(events=(Event("e1", "create", T0),) * 2)
    with pytest.raises(ValueError, match="not unique"):
        duplicate.get_event("e1")
