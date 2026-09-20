import gzip
import math
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

import pytest

from pix.event_log import (
    CaseAttribute as A,
)
from pix.event_log import (
    CaseClassifier,
    CaseEvent,
    CaseExportError,
    CaseExtension,
    CaseGlobal,
    CaseLog,
    CaseTrace,
    read_xes,
    read_xes_bytes,
    write_xes,
    xes_bytes,
)


def example():
    return CaseLog(
        traces=(
            CaseTrace(
                "order-1",
                (
                    CaseEvent(
                        "click-1",
                        (
                            A("concept:name", "string", "열기 & <확인>"),
                            A(
                                "time:timestamp",
                                "date",
                                datetime(
                                    2026, 9, 18, tzinfo=timezone(timedelta(hours=9))
                                ),
                            ),
                            A("cost", "float", -0.0),
                            A(
                                "items",
                                "list",
                                children=(A("meta", "boolean", True),),
                                values=(A("same", "int", 1), A("same", "int", 2)),
                            ),
                        ),
                    ),
                ),
                (A("concept:name", "string", "주문1"),),
            ),
            CaseTrace("empty"),
        ),
        attributes=(A("creator", "string", "PIX"),),
        globals=(CaseGlobal("event", (A("org:resource", "string", "agent"),)),),
        extensions=(
            CaseExtension(
                "Concept", "concept", "http://www.xes-standard.org/concept.xesext"
            ),
        ),
        classifiers=(CaseClassifier("Activity", ("concept:name", "tool name")),),
        metadata=(("xes.version", "1.0"), ("xmlns", "http://www.xes-standard.org/")),
    )


def test_preserves_nested_values_globals_empty_trace_and_unicode(tmp_path):
    log = example()
    path = tmp_path / "log.xes"
    receipt = write_xes(log, path)
    restored = read_xes(path)
    assert len(restored.traces) == 2
    assert restored.traces[1].events == ()
    event = restored.traces[0].events[0]
    assert event.activity == "열기 & <확인>"
    assert event.timestamp.isoformat() == "2026-09-18T00:00:00+09:00"
    assert event.attribute("items").values[1].value == 2
    assert restored.attribute(event, "org:resource").value == "agent"
    assert restored.classifiers[0].keys == ("concept:name", "tool name")
    assert receipt.event_ids == (("click-1", "event:0:0"),)
    assert receipt.trace_ids == (("order-1", "trace:0"), ("empty", "trace:1"))
    assert math.copysign(1, event.attribute("cost").value) == -1
    # Inspect emitted syntax independently of the native reader.
    root = ET.fromstring(path.read_bytes())
    assert root.tag == "{http://www.xes-standard.org/}log"
    assert root.find("{*}trace/{*}event/{*}string").get("value") == "열기 & <확인>"


def test_deterministic_gzip_and_bytes(tmp_path):
    raw = xes_bytes(example())
    packed = xes_bytes(example(), compressed=True)
    assert packed == xes_bytes(example(), compressed=True)
    assert gzip.decompress(packed) == raw
    assert read_xes_bytes(packed).traces[0].events[0].activity == "열기 & <확인>"
    path = tmp_path / "log.xes.gz"
    write_xes(example(), path)
    assert read_xes(path).traces[0].events[0].activity == "열기 & <확인>"


@pytest.mark.parametrize(
    "attribute",
    [
        A("x", "null"),
        A("x", "int", 2**63),
        A("x", "int", 2, lexical="3"),
        A("x", "string", "bad\x00value"),
    ],
)
def test_unrepresentable_or_inconsistent_values_do_not_touch_destination(
    attribute, tmp_path
):
    path = tmp_path / "keep.xes"
    path.write_bytes(b"original")
    with pytest.raises((CaseExportError, ValueError)):
        write_xes(CaseLog(attributes=(attribute,)), path, overwrite=True)
    assert path.read_bytes() == b"original"


def test_existing_file_requires_explicit_overwrite(tmp_path):
    path = tmp_path / "keep.xes"
    path.write_bytes(b"original")
    with pytest.raises(FileExistsError):
        write_xes(example(), path)
    assert path.read_bytes() == b"original"
    write_xes(example(), path, overwrite=True)
    assert len(read_xes(path).traces) == 2
    assert not list(tmp_path.glob(".pix-xes-*"))


def test_quote_keys_nonfinite_and_lexical_preservation():
    key = "a ' b \" c"
    log = CaseLog(
        attributes=(
            A("n", "float", float("nan")),
            A("i", "float", float("inf")),
            A("x", "int", 3, lexical="+003"),
        ),
        classifiers=(CaseClassifier("quoted", (key, "a\\b")),),
    )
    restored = read_xes_bytes(xes_bytes(log))
    assert restored.classifiers[0].keys == (key, "a\\b")
    assert restored.attributes[2].lexical == "+003"
    assert math.isnan(restored.attributes[0].value)


def test_bytes_reader_rejects_dtd():
    with pytest.raises(ValueError, match="DTD"):
        read_xes_bytes(b'<!DOCTYPE log [<!ENTITY x "evil">]><log/>')
