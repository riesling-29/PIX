from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    OCEL_EPOCH,
    Attribute,
    CanonicalizationError,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    canonical_bytes,
    canonical_digest,
)

UTC = timezone.utc
KST = timezone(timedelta(hours=9))
T0 = datetime(2026, 8, 22, 1, 0, tzinfo=UTC)
GOLDEN_ROOT = Path(__file__).with_name("golden") / "canonical_v1"


def _representative(*, reverse: bool = False, tz=UTC) -> OCEL:
    event_attributes = (
        Attribute("amount", ValueType.FLOAT),
        Attribute("approved", ValueType.BOOLEAN),
    )
    object_attributes = (Attribute("status", ValueType.STRING),)
    event_values = (
        EventAttr("amount", 100.0),
        EventAttr("approved", True),
    )

    event_types = (EventType("create", event_attributes),)
    object_types = (ObjectType("order", object_attributes),)
    events = (
        Event(
            "e1",
            "create",
            T0.astimezone(tz),
            event_values,
        ),
    )
    objects = (
        Object(
            "o1",
            "order",
            (ObjectAttr("status", "created", OCEL_EPOCH),),
        ),
    )
    e2o = (E2O("e1", "o1", "item"),)

    if reverse:
        event_types = (
            EventType("create", tuple(reversed(event_attributes))),
        )
        event_values = tuple(reversed(event_values))
        events = (
            Event(
                "e1",
                "create",
                T0.astimezone(tz),
                event_values,
            ),
        )

    return OCEL(
        event_types=event_types,
        object_types=object_types,
        events=events,
        objects=objects,
        e2o=e2o,
    )


def _golden_bytes(name: str) -> bytes:
    # Text fixtures keep one repository newline; canonical bytes do not.
    value = (GOLDEN_ROOT / name).read_bytes()
    if value.endswith(b"\r\n"):
        return value[:-2]

    return value.removesuffix(b"\n")


def test_empty_ocel_matches_v1_golden_vector() -> None:
    serialized = canonical_bytes(OCEL())
    digest = canonical_digest(OCEL())

    assert serialized == _golden_bytes("empty.json")
    assert digest.hexdigest == (GOLDEN_ROOT / "empty.sha256").read_text(
        encoding="ascii"
    ).strip()


def test_representative_ocel_matches_v1_golden_vector() -> None:
    ocel = _representative()

    assert canonical_bytes(ocel) == _golden_bytes("representative.json")
    assert canonical_digest(ocel).hexdigest == (
        GOLDEN_ROOT / "representative.sha256"
    ).read_text(encoding="ascii").strip()


def test_collection_order_and_timezone_do_not_change_identity() -> None:
    canonical = _representative(tz=UTC)
    reordered = _representative(reverse=True, tz=KST)

    assert canonical_bytes(canonical) == canonical_bytes(reordered)
    assert canonical_digest(canonical) == canonical_digest(reordered)


def test_serializer_does_not_mutate_input() -> None:
    ocel = _representative(reverse=True, tz=KST)
    before = ocel

    canonical_bytes(ocel)

    assert ocel == before


def _single_value(value_type: ValueType, value: object) -> OCEL:
    return OCEL(
        event_types=(
            EventType(
                "observe",
                (Attribute("value", value_type),),
            ),
        ),
        events=(
            Event(
                "e1",
                "observe",
                T0,
                (EventAttr("value", value),),
            ),
        ),
    )


def test_primitive_value_types_have_distinct_identity() -> None:
    datasets = (
        _single_value(ValueType.INTEGER, 1),
        _single_value(ValueType.FLOAT, 1.0),
        _single_value(ValueType.BOOLEAN, True),
        _single_value(ValueType.STRING, "1"),
    )

    digests = {canonical_digest(dataset).hexdigest for dataset in datasets}

    assert len(digests) == len(datasets)


def test_unicode_is_not_silently_normalized() -> None:
    composed = _single_value(ValueType.STRING, "\u00e9")
    decomposed = _single_value(ValueType.STRING, "e\u0301")

    assert canonical_digest(composed) != canonical_digest(decomposed)


def test_disconnected_entities_are_part_of_identity() -> None:
    connected = _representative()
    disconnected = OCEL(
        event_types=connected.event_types + (EventType("audit"),),
        object_types=connected.object_types,
        events=connected.events + (Event("e2", "audit", T0),),
        objects=connected.objects,
        e2o=connected.e2o,
    )

    assert canonical_digest(connected) != canonical_digest(disconnected)


def test_qualifier_is_part_of_identity() -> None:
    item = _representative()
    owner = OCEL(
        event_types=item.event_types,
        object_types=item.object_types,
        events=item.events,
        objects=item.objects,
        e2o=(E2O("e1", "o1", "owner"),),
    )

    assert canonical_digest(item) != canonical_digest(owner)


def test_object_history_and_relations_are_order_independent() -> None:
    object_type = ObjectType(
        "order",
        (
            Attribute("status", ValueType.STRING),
            Attribute("amount", ValueType.INTEGER),
        ),
    )
    first = Object(
        "o1",
        "order",
        (
            ObjectAttr("status", "created", OCEL_EPOCH),
            ObjectAttr("amount", 1, T0),
        ),
    )
    second = Object(
        "o2",
        "order",
        (ObjectAttr("status", "created", OCEL_EPOCH),),
    )
    forward = OCEL(
        object_types=(object_type,),
        objects=(first, second),
        o2o=(
            O2O("o1", "o2", "parent"),
            O2O("o2", "o1", "child"),
        ),
    )
    reverse = OCEL(
        object_types=(
            ObjectType("order", tuple(reversed(object_type.attributes))),
        ),
        objects=(
            second,
            Object("o1", "order", tuple(reversed(first.attributes))),
        ),
        o2o=tuple(reversed(forward.o2o)),
    )

    assert canonical_bytes(forward) == canonical_bytes(reverse)


def test_invalid_candidate_cannot_receive_canonical_identity() -> None:
    invalid = OCEL(
        event_types=(EventType("create"),),
        events=(
            Event("e1", "create", T0),
            Event("e1", "create", T0),
        ),
    )

    with pytest.raises(CanonicalizationError) as raised:
        canonical_digest(invalid)

    assert raised.value.report.has("duplicate_event_id")


def test_canonical_bytes_require_ocel() -> None:
    with pytest.raises(TypeError, match="ocel must be OCEL"):
        canonical_bytes("not-ocel")  # type: ignore[arg-type]
