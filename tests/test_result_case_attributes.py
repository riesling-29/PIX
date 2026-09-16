"""Typed XES values embedded in native analytical result contracts."""

from datetime import datetime, timezone

import pytest

from pix.event_log import CaseAttribute
from pix.results import _decode, _encode


@pytest.mark.parametrize(
    "kind,value",
    [
        ("string", "2026-09-15T00:00:00.000000Z"),
        ("id", "2026-09-15T00:00:00.000000Z"),
        ("date", datetime(2026, 9, 15, tzinfo=timezone.utc)),
        ("int", 7),
        ("float", 7.0),
        ("boolean", False),
        ("null", None),
    ],
)
def test_xes_discriminator_preserves_value_type(kind, value):
    attribute = CaseAttribute("value", kind, value)
    recovered = _decode(_encode(attribute), CaseAttribute)
    assert recovered == attribute
    assert type(recovered.value) is type(value)


def test_nested_xes_dates_and_strings_remain_distinct():
    attribute = CaseAttribute(
        "nested",
        "list",
        values=(
            CaseAttribute("date", "date", datetime(2026, 9, 15, tzinfo=timezone.utc)),
            CaseAttribute("string", "string", "2026-09-15T00:00:00.000000Z"),
        ),
    )
    assert _decode(_encode(attribute), CaseAttribute) == attribute


@pytest.mark.parametrize(
    "kind,value",
    [("date", "arbitrary"), ("int", True), ("float", 1), ("unknown", None)],
)
def test_declared_xes_type_cannot_be_silently_coerced(kind, value):
    record = _encode(CaseAttribute("value", "null"))
    record.update(type=kind, value=value)
    with pytest.raises((TypeError, ValueError)):
        _decode(record, CaseAttribute)
