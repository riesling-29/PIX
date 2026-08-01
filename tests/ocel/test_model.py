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
