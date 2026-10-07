"""Proposed regression tests for PIX commit 5ef88a2.

Review attachment: all four failures reproduced on 5ef88a2 before correction.
Run in an environment containing the pinned PIX checkout and pytest.

Tests 1 and 4 exercise absolute-time semantics around DST folds.
Tests 2 and 3 propose canonical-equivalence invariants for the DERIVED CaseLog;
they intentionally do not compare the source-preserving projection receipt.

These tests do not modify source files or contact external services.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pix.event_log import case_log_digest
from pix.object_centric.case_projection import (
    ObjectCaseProjectionSpec,
    project_object_cases,
)
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
    canonical_digest,
)

UTC = timezone.utc
T = datetime(2026, 9, 20, 0, 0, tzinfo=UTC)


def _log() -> OCEL:
    return OCEL(
        event_types=(
            EventType(
                "A",
                (
                    Attribute("x", ValueType.STRING),
                    Attribute("y", ValueType.STRING),
                ),
            ),
        ),
        object_types=(ObjectType("order"),),
        events=(
            Event(
                "e1",
                "A",
                T,
                (
                    EventAttr("x", "left"),
                    EventAttr("y", "right"),
                ),
            ),
        ),
        objects=(Object("o1", "order"),),
        e2o=(E2O("e1", "o1", "participant"),),
    )


def _project(log: OCEL):
    return project_object_cases(log, ObjectCaseProjectionSpec("order")).case_log


def test_distinct_fold_instants_are_not_duplicate_object_assignments():
    zone = ZoneInfo("America/New_York")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    second = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
    assert first.astimezone(UTC) != second.astimezone(UTC)
    # Both values are valid aware times allowed by ObjectAttr's contract.
    obj = Object(
        "o1",
        "order",
        (
            ObjectAttr("status", "before", first),
            ObjectAttr("status", "after", second),
        ),
    )
    assert len(obj.attributes) == 2


def test_canonical_equivalent_attribute_order_has_same_projected_identity():
    original = _log()
    reordered = replace(
        original,
        events=(
            replace(original.events[0], attributes=original.events[0].attributes[::-1]),
        ),
    )
    assert (
        canonical_digest(original).identifier == canonical_digest(reordered).identifier
    )
    assert case_log_digest(_project(original)) == case_log_digest(_project(reordered))


def test_canonical_equivalent_offset_has_same_projected_identity():
    original = _log()
    other_offset = replace(
        original,
        events=(
            replace(
                original.events[0], time=T.astimezone(timezone(timedelta(hours=9)))
            ),
        ),
    )
    assert (
        canonical_digest(original).identifier
        == canonical_digest(other_offset).identifier
    )
    assert case_log_digest(_project(original)) == case_log_digest(
        _project(other_offset)
    )


def test_projected_object_history_is_ordered_by_absolute_time():
    zone = ZoneInfo("America/New_York")
    earlier = datetime(2026, 11, 1, 1, 50, tzinfo=zone, fold=0)  # 05:50 UTC
    later = datetime(2026, 11, 1, 1, 10, tzinfo=zone, fold=1)  # 06:10 UTC
    # Different attribute names avoid conflating this test with test 1.
    original = replace(
        _log(),
        object_types=(
            ObjectType(
                "order",
                (
                    Attribute("status", ValueType.STRING),
                    Attribute("priority", ValueType.STRING),
                ),
            ),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr("status", "earlier", earlier),
                    ObjectAttr("priority", "later", later),
                ),
            ),
        ),
    )
    history = _project(original).traces[0].attribute("pix:object_history")
    assert history is not None
    times = tuple(
        next(child.value for child in item.children if child.key == "time").astimezone(
            UTC
        )
        for item in history.values
    )
    assert times == (earlier.astimezone(UTC), later.astimezone(UTC))
