"""Independent XES fixtures exercise preservation, parser failure and eligibility."""

import gzip
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO

import pytest

from pix.event_log import (
    CaseAttribute,
    CaseEvent,
    CaseImportError,
    CaseLog,
    CaseTrace,
    import_xes,
    read_xes,
)
from pix.event_log.reader import CaseFormatError, _parse_xes
from pix.ocel.ingest.contract import ImportStatus


def write(tmp_path, xml, *, compressed=False):
    path = tmp_path / ("log.xes.gz" if compressed else "log.xes")
    data = xml.encode() if isinstance(xml, str) else xml
    path.write_bytes(gzip.compress(data) if compressed else data)
    return path


@pytest.mark.parametrize("compressed", [False, True])
def test_hierarchy_globals_metadata_identity_order(tmp_path, compressed):
    path = write(
        tmp_path,
        """<log xes.version="1.0" creator="fixture">
      <extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>
      <global scope="event"><string key="concept:name" value="default"/>
        <string key="lifecycle:transition" value="complete"/></global>
      <global scope="trace"><string key="owner" value="global-owner"/></global>
      <classifier name="Activity lifecycle" keys="concept:name lifecycle:transition"/>
      <classifier name="Case name" keys="concept:name" scope="trace"/>
      <string key="concept:name" value="original-log"/>
      <trace><string key="concept:name" value="duplicate"/>
        <event><string key="concept:name" value="B"/>
          <date key="time:timestamp" value="2024-01-01T00:00:00Z"/>
          <string key="org:resource" value="Alice"/>
          <string key="org:role" value="clerk"/>
          <string key="org:group" value="A"/></event>
        <event><date key="time:timestamp" value="2024-01-01T00:00:00Z"/></event>
      </trace>
      <trace><string key="concept:name" value="duplicate"/></trace>
      <trace/>
    </log>""",
        compressed=compressed,
    )
    result = import_xes(path)
    assert result.valid
    log = result.require_case_log()
    assert [t.id for t in log.traces] == ["trace:0", "trace:1", "trace:2"]
    assert [e.id for e in log.traces[0].events] == ["event:0:0", "event:0:1"]
    first, second = log.traces[0].events
    assert first.activity == "B" and second.activity is None
    assert log.attribute(second, "concept:name").value == "default"
    assert log.attribute(first, "lifecycle:transition").value == "complete"
    assert log.attribute(log.traces[0], "owner").value == "global-owner"
    assert first.attribute("org:resource").value == "Alice"
    assert log.traces[1].events == log.traces[2].events == ()
    assert log.classifiers[1].scope == "trace"
    assert log.classifiers[0].keys == ("concept:name", "lifecycle:transition")
    assert dict(log.metadata)["creator"] == "fixture"
    assert log.extensions[0].prefix == "concept"
    assert result.source_sha256 == sha256(path.read_bytes()).hexdigest()
    assert result.source_size == len(path.read_bytes())
    assert log.source.sha256 == result.source_sha256
    assert first.timestamp == datetime(2024, 1, 1, tzinfo=timezone.utc)


def test_recursive_typed_attributes_no_flattening(tmp_path):
    log = read_xes(
        write(
            tmp_path,
            """<log><trace><event>
      <string key="concept:name" value="A"><string key="language" value="en"/></string>
      <list key="ordered"><string key="description" value="meta"/><values>
        <int key="item" value="+002"/><boolean key="item" value="0"/>
        <container key="item"><id key="identity:id" value="abc-123"/>
          <float key="weight" value="1.25e1"/></container>
      </values></list>
      <float key="not-number" value="NaN"/>
      <date key="local" value="2024-01-01T00:00:00.123456000"/>
    </event></trace></log>""",
        )
    )
    event = log.traces[0].events[0]
    ordered = event.attribute("ordered")
    assert ordered.type == "list" and ordered.value is None
    assert ordered.children[0].value == "meta"
    assert [a.key for a in ordered.values] == ["item", "item", "item"]
    assert ordered.values[0].value == 2 and ordered.values[0].lexical == "+002"
    assert ordered.values[1].value is False
    assert ordered.values[2].children[0].type == "id"
    assert ordered.values[2].children[1].value == 12.5
    assert event.attribute("local").lexical.endswith(".123456000")
    assert event.attribute("local").value.tzinfo is None
    assert event.attribute("concept:name").children[0].value == "en"
    with pytest.raises(FrozenInstanceError):
        ordered.key = "changed"


def test_missing_activity_time_are_valid_storage(tmp_path):
    result = import_xes(write(tmp_path, "<log><trace><event/></trace></log>"))
    assert (
        result.valid and result.require_case_log().traces[0].events[0].timestamp is None
    )
    assert {issue.code for issue in result.import_issues} == {
        "missing_activity",
        "missing_timestamp",
    }
    assert result.describe()["candidate"]["eventCount"] == 1


@pytest.mark.parametrize("namespace", ["", ' xmlns="http://www.xes-standard.org/"'])
def test_namespace_and_classifier_quoted_keys(tmp_path, namespace):
    log = read_xes(
        write(
            tmp_path,
            f"""<log{namespace}>
        <classifier name="Quoted" keys="'key with space' org:resource"/>
        <trace><event><string key="key with space" value="A"/></event></trace></log>""",
        )
    )
    assert log.classifiers[0].keys == ("key with space", "org:resource")
    assert log.classifiers[0].lexical == "'key with space' org:resource"


@pytest.mark.parametrize(
    "xml,status",
    [
        ("<log><trace></log>", "syntax_invalid"),
        ('<!DOCTYPE log [<!ENTITY name "value">]><log/>', "syntax_invalid"),
        ('<!DOCTYPE log SYSTEM "file:///C:/secret"><log/>', "syntax_invalid"),
        ("<?sideeffect data?><log/>", "syntax_invalid"),
        ('<?xml version="1.1"?><log/>', "unsupported"),
        ("<log><event/></log>", "unsupported"),
        ("<log><unknown/></log>", "unsupported"),
        ('<log xmlns="https://unknown.test"><trace/></log>', "unsupported"),
        ('<log><trace extra="1"/></log>', "schema_invalid"),
        (
            '<log><trace><event><string key="x" value="a" extra="b"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><string key="x"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><int key="x" value="9223372036854775808"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><boolean key="x" value="yes"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><date key="x" value="2020-01-01T00:00:00+00:60"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><date key="x" value="2020-01-01T00:00:00.1234567Z"/></event></trace></log>',
            "unsupported",
        ),
        ('<log><trace><event><list key="x"/></event></trace></log>', "schema_invalid"),
        (
            '<log><trace><event><container key="x" value="lost"/></event></trace></log>',
            "schema_invalid",
        ),
        (
            '<log><trace><event><string key="x" value="a"/><string key="x" value="b"/></event></trace></log>',
            "schema_invalid",
        ),
        ('<log><global scope="something"/></log>', "schema_invalid"),
        ('<log><classifier name="bad" keys="\'unterminated"/></log>', "schema_invalid"),
        (
            '<log><extension name="C" prefix="c" uri="u"><string key="x" value="lost"/></extension></log>',
            "schema_invalid",
        ),
        ("<log>lost<trace/></log>", "schema_invalid"),
    ],
)
def test_fail_closed(tmp_path, xml, status):
    path = write(tmp_path, xml)
    result = import_xes(path)
    assert result.status.value == status, result.describe()
    assert result.case_log is None and result.candidate is None
    assert result.source_sha256 == sha256(path.read_bytes()).hexdigest()
    with pytest.raises(CaseImportError) as error:
        read_xes(path)
    assert error.value.result.status == result.status


def test_utf16_entity_declarations_are_rejected(tmp_path):
    raw = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE log [<!ENTITY a "bad">]><log/>'.encode(
        "utf-16"
    )
    assert import_xes(write(tmp_path, raw)).status is ImportStatus.SYNTAX_INVALID


@pytest.mark.parametrize("data", [b"not gzip", gzip.compress(b"<log/>")[:-3]])
def test_malformed_gzip(tmp_path, data):
    path = tmp_path / "log.xes.gz"
    path.write_bytes(data)
    assert import_xes(path).status is ImportStatus.SYNTAX_INVALID


def test_unavailable_and_depth_bound(tmp_path):
    result = import_xes(tmp_path / "absent.xes")
    assert result.status is ImportStatus.UNAVAILABLE and result.source_sha256 is None
    xml = (
        "<log><trace><event>"
        + '<container key="x">' * 130
        + "</container>" * 130
        + "</event></trace></log>"
    )
    assert import_xes(write(tmp_path, xml)).status is ImportStatus.UNSUPPORTED


def test_delayed_tail_cannot_disappear_between_chunks():
    class Tiny(BytesIO):
        def read(self, size=-1):
            return super().read(1)

    for data in (
        b"<log><trace><event/>lost<event/></trace></log>",
        b"<log><trace/>lost</log>",
    ):
        with pytest.raises(CaseFormatError, match="text"):
            _parse_xes(Tiny(data))


def test_model_rejects_mutability_bad_types_and_duplicate_ids():
    with pytest.raises(TypeError):
        CaseLog(traces=[])
    with pytest.raises(TypeError):
        CaseAttribute("x", "int", True)
    with pytest.raises(TypeError):
        CaseAttribute("x", "string", "s", children=[])
    trace = CaseTrace("t", (CaseEvent("e"),))
    with pytest.raises(ValueError, match="identities"):
        CaseLog((trace, replace(trace, id="t2")))
    with pytest.raises(ValueError, match="identities"):
        CaseLog((CaseTrace("t"), CaseTrace("t")))
