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
    validate,
)

T0 = datetime(2026, 8, 8, 10, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(hours=1)


def _valid_ocel() -> OCEL:
    return OCEL(
        event_types=(
            EventType(
                "create",
                (
                    Attribute(
                        "amount",
                        ValueType.FLOAT,
                    ),
                    Attribute(
                        "count",
                        ValueType.INTEGER,
                    ),
                    Attribute(
                        "active",
                        ValueType.BOOLEAN,
                    ),
                    Attribute(
                        "recorded_at",
                        ValueType.TIME,
                    ),
                ),
            ),
        ),
        object_types=(
            ObjectType(
                "order",
                (
                    Attribute(
                        "status",
                        ValueType.STRING,
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
                        100.0,
                    ),
                    EventAttr(
                        "count",
                        1,
                    ),
                    EventAttr(
                        "active",
                        True,
                    ),
                    EventAttr(
                        "recorded_at",
                        T0,
                    ),
                ),
            ),
        ),
        objects=(
            Object(
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
            ),
        ),
        e2o=(
            E2O(
                "e1",
                "o1",
                "order",
            ),
        ),
    )


def test_valid_ocel_has_empty_report() -> None:
    report = validate(_valid_ocel())

    assert report.valid
    assert report.issues == ()


def test_empty_ocel_is_valid() -> None:
    report = validate(OCEL())

    assert report.valid
    assert report.issues == ()


def test_validate_requires_ocel() -> None:
    with pytest.raises(
        TypeError,
        match="ocel must be OCEL",
    ):
        validate(
            object()  # type: ignore[arg-type]
        )


def test_duplicate_event_type_is_reported() -> None:
    log = OCEL(
        event_types=(
            EventType("create"),
            EventType("create"),
        ),
    )

    report = validate(log)

    assert report.has("duplicate_event_type")
    assert not report.valid


def test_duplicate_object_type_is_reported() -> None:
    log = OCEL(
        object_types=(
            ObjectType("order"),
            ObjectType("order"),
        ),
    )

    report = validate(log)

    assert report.has("duplicate_object_type")
    assert not report.valid


def test_duplicate_event_id_is_reported() -> None:
    log = OCEL(
        event_types=(EventType("create"),),
        events=(
            Event(
                "e1",
                "create",
                T0,
            ),
            Event(
                "e1",
                "create",
                T1,
            ),
        ),
    )

    report = validate(log)

    assert report.has("duplicate_event_id")


def test_duplicate_object_id_is_reported() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o1",
                "order",
            ),
            Object(
                "o1",
                "order",
            ),
        ),
    )

    report = validate(log)

    assert report.has("duplicate_object_id")


def test_undeclared_event_type_is_reported() -> None:
    log = OCEL(
        events=(
            Event(
                "e1",
                "create",
                T0,
            ),
        ),
    )

    report = validate(log)

    assert report.has("undeclared_event_type")


def test_undeclared_object_type_is_reported() -> None:
    log = OCEL(
        objects=(
            Object(
                "o1",
                "order",
            ),
        ),
    )

    report = validate(log)

    assert report.has("undeclared_object_type")


def test_undeclared_event_attribute_is_reported() -> None:
    log = OCEL(
        event_types=(EventType("create"),),
        events=(
            Event(
                "e1",
                "create",
                T0,
                (
                    EventAttr(
                        "resource",
                        "alice",
                    ),
                ),
            ),
        ),
    )

    report = validate(log)

    assert report.has("undeclared_event_attribute")


def test_undeclared_object_attribute_is_reported() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr(
                        "status",
                        "created",
                        T0,
                    ),
                ),
            ),
        ),
    )

    report = validate(log)

    assert report.has("undeclared_object_attribute")


@pytest.mark.parametrize(
    ("expected", "value"),
    (
        (
            ValueType.STRING,
            1,
        ),
        (
            ValueType.TIME,
            "2026-08-08T10:00:00Z",
        ),
        (
            ValueType.INTEGER,
            True,
        ),
        (
            ValueType.FLOAT,
            1,
        ),
        (
            ValueType.BOOLEAN,
            1,
        ),
    ),
)
def test_event_attribute_type_mismatch_is_exact(
    expected: ValueType,
    value: object,
) -> None:
    log = OCEL(
        event_types=(
            EventType(
                "create",
                (
                    Attribute(
                        "value",
                        expected,
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
                        "value",
                        value,  # type: ignore[arg-type]
                    ),
                ),
            ),
        ),
    )

    report = validate(log)

    assert report.has("event_attribute_type_mismatch")


def test_object_attribute_type_mismatch_is_reported() -> None:
    log = OCEL(
        object_types=(
            ObjectType(
                "order",
                (
                    Attribute(
                        "amount",
                        ValueType.FLOAT,
                    ),
                ),
            ),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr(
                        "amount",
                        "100",
                        T0,
                    ),
                ),
            ),
        ),
    )

    report = validate(log)

    assert report.has("object_attribute_type_mismatch")


def test_declared_attribute_is_not_mandatory() -> None:
    log = OCEL(
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
            ),
        ),
    )

    report = validate(log)

    assert report.valid


def test_dangling_e2o_event_is_reported() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o1",
                "order",
            ),
        ),
        e2o=(
            E2O(
                "missing",
                "o1",
                "order",
            ),
        ),
    )

    report = validate(log)

    assert report.has("dangling_e2o_event")


def test_dangling_e2o_object_is_reported() -> None:
    log = OCEL(
        event_types=(EventType("create"),),
        events=(
            Event(
                "e1",
                "create",
                T0,
            ),
        ),
        e2o=(
            E2O(
                "e1",
                "missing",
                "order",
            ),
        ),
    )

    report = validate(log)

    assert report.has("dangling_e2o_object")


def test_e2o_can_report_both_missing_endpoints() -> None:
    log = OCEL(
        e2o=(
            E2O(
                "missing-event",
                "missing-object",
                "order",
            ),
        ),
    )

    report = validate(log)

    assert report.has("dangling_e2o_event")
    assert report.has("dangling_e2o_object")
    assert len(report.errors) == 2


def test_dangling_o2o_source_is_reported() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o2",
                "order",
            ),
        ),
        o2o=(
            O2O(
                "missing",
                "o2",
                "parent",
            ),
        ),
    )

    report = validate(log)

    assert report.has("dangling_o2o_source")


def test_dangling_o2o_target_is_reported() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
        objects=(
            Object(
                "o1",
                "order",
            ),
        ),
        o2o=(
            O2O(
                "o1",
                "missing",
                "parent",
            ),
        ),
    )

    report = validate(log)

    assert report.has("dangling_o2o_target")


def test_exact_duplicate_e2o_is_reported() -> None:
    relation = E2O(
        "e1",
        "o1",
        "item",
    )

    log = OCEL(
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
        ),
        e2o=(
            relation,
            relation,
        ),
    )

    report = validate(log)

    assert report.has("duplicate_e2o")


def test_exact_duplicate_o2o_is_reported() -> None:
    relation = O2O(
        "o1",
        "o2",
        "parent",
    )

    log = OCEL(
        object_types=(ObjectType("order"),),
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
        o2o=(
            relation,
            relation,
        ),
    )

    report = validate(log)

    assert report.has("duplicate_o2o")


def test_same_e2o_endpoints_with_different_qualifiers_are_valid() -> None:
    log = OCEL(
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
    )

    report = validate(log)

    assert report.valid
    assert not report.has("duplicate_e2o")


def test_same_o2o_endpoints_with_different_qualifiers_are_valid() -> None:
    log = OCEL(
        object_types=(ObjectType("order"),),
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

    report = validate(log)

    assert report.valid
    assert not report.has("duplicate_o2o")


def test_disconnected_event_and_object_are_valid() -> None:
    log = OCEL(
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
        ),
    )

    report = validate(log)

    assert report.valid


def test_duplicate_type_does_not_select_arbitrary_schema() -> None:
    log = OCEL(
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
            EventType(
                "create",
                (
                    Attribute(
                        "resource",
                        ValueType.STRING,
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
                        100.0,
                    ),
                ),
            ),
        ),
    )

    report = validate(log)

    assert report.has("duplicate_event_type")
    assert not report.has("undeclared_event_attribute")
    assert not report.has("event_attribute_type_mismatch")


def test_validation_report_order_is_deterministic() -> None:
    first = OCEL(
        event_types=(
            EventType("b"),
            EventType("b"),
            EventType("a"),
            EventType("a"),
        ),
        events=(
            Event(
                "e2",
                "missing-b",
                T1,
            ),
            Event(
                "e1",
                "missing-a",
                T0,
            ),
        ),
    )

    second = OCEL(
        event_types=tuple(reversed(first.event_types)),
        events=tuple(reversed(first.events)),
    )

    assert validate(first) == validate(second)
