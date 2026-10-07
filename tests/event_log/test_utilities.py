from dataclasses import replace

import pytest

from pix.event_log import CaseAttribute as A
from pix.event_log import (
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
    case_log_from_activity_text,
    event_attribute_sequences,
)


def test_activity_text_keeps_empty_cases_and_label_delimiters_without_timestamps():
    log = case_log_from_activity_text('[["검토, 승인", "A → B"], []]')
    assert len(log.traces) == 2
    assert [e.activity for e in log.traces[0].events] == ["검토, 승인", "A → B"]
    assert log.traces[1].events == ()
    assert all(e.timestamp is None for t in log.traces for e in t.events)
    assert log == case_log_from_activity_text('[["검토, 승인", "A → B"], []]')


@pytest.mark.parametrize("text", ['["ABC"]', "[[1]]", '[[""]]', '{"case": []}', "null"])
def test_invalid_activity_shapes_are_rejected(text):
    with pytest.raises(ValueError):
        case_log_from_activity_text(text)


def test_attribute_sequences_preserve_missing_null_nested_and_global_values():
    nested = A("x", "list", values=(A("k", "int", 2),))
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    CaseEvent("one", (nested,)),
                    CaseEvent("two", (A("x", "null"),)),
                    CaseEvent("three"),
                ),
            ),
            CaseTrace("empty"),
        ),
        globals=(CaseGlobal("event", (A("x", "boolean", False),)),),
    )
    result = event_attribute_sequences(log, "x")
    assert result.sequences[0].event_ids == ("one", "two", "three")
    assert result.sequences[0].attributes == (
        nested,
        A("x", "null"),
        A("x", "boolean", False),
    )
    assert result.sequences[1].attributes == ()
    raw = event_attribute_sequences(log, "x", resolve_globals=False)
    assert raw.sequences[0].attributes[-1] is None
    assert result.source_digest == raw.source_digest
    assert (
        event_attribute_sequences(replace(log, globals=()), "x")
        .sequences[0]
        .attributes[-1]
        is None
    )


def test_input_size_limits():
    with pytest.raises(ValueError, match="event limit"):
        case_log_from_activity_text('[["A","B"]]', max_events=1)
    with pytest.raises(ValueError, match="byte limit"):
        case_log_from_activity_text('[["A"]]', max_bytes=2)
