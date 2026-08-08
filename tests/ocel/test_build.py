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
    build,
)

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

T0 = datetime(
    2026,
    8,
    8,
    10,
    0,
    tzinfo=UTC,
)
T1 = T0 + timedelta(hours=1)

LOCAL_T0 = datetime(
    2026,
    8,
    8,
    21,
    0,
    tzinfo=KST,
)
UTC_T0 = datetime(
    2026,
    8,
    8,
    12,
    0,
    tzinfo=UTC,
)


def test_empty_build_is_valid() -> None:
    result = build()

    assert result.valid
    assert result.report.valid
    assert result.candidate == OCEL()
    assert result.ocel == result.candidate


def test_build_accepts_iterables_and_is_deterministic() -> None:
    event_types = (
        EventType("b"),
        EventType("a"),
    )
    object_types = (
        ObjectType("z"),
        ObjectType("x"),
    )

    events = (
        Event(
            "e2",
            "b",
            T1,
        ),
        Event(
            "e1",
            "a",
            T0,
        ),
    )
    objects = (
        Object(
            "o2",
            "z",
        ),
        Object(
            "o1",
            "x",
        ),
    )

    first = build(
        event_types=event_types,
        object_types=object_types,
        events=events,
        objects=objects,
    )

    second = build(
        event_types=(item for item in reversed(event_types)),
        object_types=(item for item in reversed(object_types)),
        events=(item for item in reversed(events)),
        objects=(item for item in reversed(objects)),
    )

    assert first.valid
    assert second.valid
    assert first.candidate == second.candidate
    assert first.report == second.report


def test_build_canonicalizes_nested_collection_order() -> None:
    event_type = EventType(
        "create",
        (
            Attribute(
                "resource",
                ValueType.STRING,
            ),
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
            Attribute(
                "owner",
                ValueType.STRING,
            ),
        ),
    )

    event = Event(
        "e1",
        "create",
        T0,
        (
            EventAttr(
                "resource",
                "alice",
            ),
            EventAttr(
                "amount",
                100.0,
            ),
        ),
    )
    obj = Object(
        "o1",
        "order",
        (
            ObjectAttr(
                "status",
                "approved",
                T1,
            ),
            ObjectAttr(
                "status",
                "created",
                OCEL_EPOCH,
            ),
            ObjectAttr(
                "owner",
                "alice",
                OCEL_EPOCH,
            ),
        ),
    )

    result = build(
        event_types=(event_type,),
        object_types=(object_type,),
        events=(event,),
        objects=(obj,),
    )

    assert result.valid

    assert tuple(
        attribute.name for attribute in result.candidate.event_types[0].attributes
    ) == (
        "amount",
        "resource",
    )

    assert tuple(
        attribute.name for attribute in result.candidate.object_types[0].attributes
    ) == (
        "owner",
        "status",
    )

    assert tuple(
        attribute.name for attribute in result.candidate.events[0].attributes
    ) == (
        "amount",
        "resource",
    )

    assert tuple(
        (
            attribute.name,
            attribute.time,
        )
        for attribute in result.candidate.objects[0].attributes
    ) == (
        (
            "owner",
            OCEL_EPOCH,
        ),
        (
            "status",
            OCEL_EPOCH,
        ),
        (
            "status",
            T1,
        ),
    )


def test_build_normalizes_all_datetime_representations_to_utc() -> None:
    event_type = EventType(
        "create",
        (
            Attribute(
                "recorded_at",
                ValueType.TIME,
            ),
        ),
    )
    object_type = ObjectType(
        "order",
        (
            Attribute(
                "recorded_at",
                ValueType.TIME,
            ),
        ),
    )

    event = Event(
        "e1",
        "create",
        LOCAL_T0,
        (
            EventAttr(
                "recorded_at",
                LOCAL_T0,
            ),
        ),
    )
    obj = Object(
        "o1",
        "order",
        (
            ObjectAttr(
                "recorded_at",
                LOCAL_T0,
                LOCAL_T0,
            ),
        ),
    )

    result = build(
        event_types=(event_type,),
        object_types=(object_type,),
        events=(event,),
        objects=(obj,),
    )

    assert result.valid

    built_event = result.candidate.events[0]
    built_object_attr = result.candidate.objects[0].attributes[0]

    assert built_event.time == UTC_T0
    assert built_event.time.tzinfo is UTC

    assert built_event.attributes[0].value == UTC_T0
    assert built_event.attributes[0].value.tzinfo is UTC

    assert built_object_attr.time == UTC_T0
    assert built_object_attr.time.tzinfo is UTC

    assert built_object_attr.value == UTC_T0
    assert built_object_attr.value.tzinfo is UTC


def test_build_does_not_mutate_input_objects() -> None:
    event = Event(
        "e1",
        "create",
        LOCAL_T0,
    )

    result = build(
        event_types=(EventType("create"),),
        events=(event,),
    )

    assert result.valid

    assert event.time == LOCAL_T0
    assert event.time.utcoffset() == timedelta(hours=9)

    assert result.candidate.events[0].time == UTC_T0
    assert result.candidate.events[0] is not event


def test_duplicate_event_ids_are_preserved_and_invalid() -> None:
    first = Event(
        "e1",
        "create",
        T0,
    )
    second = Event(
        "e1",
        "create",
        T1,
    )

    result = build(
        event_types=(EventType("create"),),
        events=(
            second,
            first,
        ),
    )

    assert not result.valid
    assert result.ocel is None

    assert len(result.candidate.events) == 2
    assert result.report.has("duplicate_event_id")


def test_duplicate_relations_are_preserved_and_invalid() -> None:
    e2o = E2O(
        "e1",
        "o1",
        "item",
    )
    o2o = O2O(
        "o1",
        "o2",
        "parent",
    )

    result = build(
        event_types=(EventType("create"),),
        object_types=(ObjectType("order"),),
        events=(
            Event(
                "e1",
                "create",
                T0,
            ),
        ),
        objects=(
            Object(
                "o1",
                "order",
            ),
            Object(
                "o2",
                "order",
            ),
        ),
        e2o=(
            e2o,
            e2o,
        ),
        o2o=(
            o2o,
            o2o,
        ),
    )

    assert not result.valid
    assert result.ocel is None

    assert len(result.candidate.e2o) == 2
    assert len(result.candidate.o2o) == 2

    assert result.report.has("duplicate_e2o")
    assert result.report.has("duplicate_o2o")


def test_dangling_relation_is_preserved_in_candidate() -> None:
    relation = E2O(
        "missing-event",
        "o1",
        "item",
    )

    result = build(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o1",
                "order",
            ),
        ),
        e2o=(relation,),
    )

    assert not result.valid
    assert result.ocel is None

    assert result.candidate.e2o == (relation,)
    assert result.report.has("dangling_e2o_event")


def test_different_qualifiers_are_preserved_as_distinct_relations() -> None:
    result = build(
        event_types=(EventType("create"),),
        object_types=(ObjectType("order"),),
        events=(
            Event(
                "e1",
                "create",
                T0,
            ),
        ),
        objects=(
            Object(
                "o1",
                "order",
            ),
            Object(
                "o2",
                "order",
            ),
        ),
        e2o=(
            E2O(
                "e1",
                "o1",
                "target",
            ),
            E2O(
                "e1",
                "o1",
                "item",
            ),
        ),
        o2o=(
            O2O(
                "o1",
                "o2",
                "reference",
            ),
            O2O(
                "o1",
                "o2",
                "parent",
            ),
        ),
    )

    assert result.valid

    assert result.candidate.e2o == (
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
    )

    assert result.candidate.o2o == (
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
    )


def test_disconnected_event_and_object_are_preserved() -> None:
    event = Event(
        "e1",
        "create",
        T0,
    )
    obj = Object(
        "o1",
        "order",
    )

    result = build(
        event_types=(EventType("create"),),
        object_types=(ObjectType("order"),),
        events=(event,),
        objects=(obj,),
    )

    assert result.valid

    assert result.candidate.events == (event,)
    assert result.candidate.objects == (obj,)
    assert result.candidate.e2o == ()
    assert result.candidate.o2o == ()


def test_builder_does_not_widen_integer_to_float() -> None:
    result = build(
        event_types=(
            EventType(
                "create",
                (
                    Attribute(
                        "amount",
                        ValueType.FLOAT,
                    ),
                ),
            ),
        ),
        events=(
            Event(
                "e1",
                "create",
                T0,
                (
                    EventAttr(
                        "amount",
                        1,
                    ),
                ),
            ),
        ),
    )

    assert not result.valid
    assert result.ocel is None

    value = result.candidate.events[0].attributes[0].value

    assert type(value) is int
    assert result.report.has("event_attribute_type_mismatch")


def test_builder_does_not_trim_or_coerce_identifiers() -> None:
    event_type = EventType(
        " create ",
    )
    event = Event(
        " e1 ",
        " create ",
        T0,
    )

    result = build(
        event_types=(event_type,),
        events=(event,),
    )

    assert result.valid

    assert result.candidate.event_types[0].name == " create "
    assert result.candidate.events[0].id == " e1 "
    assert result.candidate.events[0].type == " create "


def test_build_rejects_wrong_component_types() -> None:
    with pytest.raises(
        TypeError,
        match="every item in events must be Event",
    ):
        build(
            events=(
                Object(
                    "o1",
                    "order",
                ),
            ),  # type: ignore[arg-type]
        )

    with pytest.raises(
        TypeError,
        match="every item in e2o must be E2O",
    ):
        build(
            e2o=(
                O2O(
                    "o1",
                    "o2",
                    "parent",
                ),
            ),  # type: ignore[arg-type]
        )
