"""Small, hand-checkable OCEL for complete native analysis pipelines."""

from datetime import datetime, timedelta, timezone

import pytest

from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


@pytest.fixture
def native_log() -> OCEL:
    base = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    rows = (
        ("e1", 0, "Create", ("O1",)),
        ("e2", 1, "Create", ("O2",)),
        ("e3", 5, "Pack", ("O1", "O2", "P1")),
        ("e4", 10, "Ship", ("O1", "O2", "P1", "R1")),
        ("e5", 20, "Create", ("O3",)),
        ("e6", 30, "Ship", ("O3", "P2", "R1")),
        ("e7", 35, "Check", ("P2",)),
    )
    return OCEL(
        event_types=tuple(
            EventType(name) for name in ("Create", "Pack", "Ship", "Check")
        ),
        object_types=tuple(
            ObjectType(name) for name in ("Order", "Package", "Resource")
        ),
        events=tuple(
            Event(eid, activity, base + timedelta(minutes=minute))
            for eid, minute, activity, _ in rows
        ),
        objects=tuple(
            Object(oid, kind)
            for oid, kind in (
                ("O1", "Order"),
                ("O2", "Order"),
                ("O3", "Order"),
                ("P1", "Package"),
                ("P2", "Package"),
                ("R1", "Resource"),
            )
        ),
        e2o=tuple(
            E2O(eid, oid, "participates")
            for eid, _, _, objects in rows
            for oid in objects
        ),
    )
