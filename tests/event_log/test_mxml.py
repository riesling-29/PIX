"""MXML preservation and rejection regressions, independent of PM4Py."""

import gzip
import hashlib
from datetime import datetime, timedelta, timezone
from io import BytesIO

import pytest

from pix.event_log.contract import CaseImportError
from pix.event_log.model import find_attribute
from pix.event_log.mxml import _parse_mxml, import_mxml, read_mxml
from pix.ocel.ingest.contract import ImportStatus


def _write(tmp_path, xml, name="log.mxml"):
    path = tmp_path / name
    path.write_text(xml, encoding="utf-8")
    return path


def _wrap(body):
    return (
        '<WorkflowLog><Process id="p"><ProcessInstance id="case">'
        + body
        + "</ProcessInstance></Process></WorkflowLog>"
    )


def _attribute(attributes, key):
    value = find_attribute(attributes, key)
    assert value is not None
    return value


def test_full_hierarchy_and_source_bytes_are_retained(tmp_path):
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<WorkflowLog xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
 xsi:noNamespaceSchemaLocation="WorkflowLog.xsd" description="original log">
 <Data><Attribute name="log label">한글 &amp; text</Attribute></Data>
 <Source program="Recorder"><Data><Attribute name="version">1.2</Attribute></Data></Source>
 <Process id="invoice" description="invoices">
  <Data><Attribute name="owner">finance</Attribute></Data>
  <ProcessInstance id="duplicate" description="a case">
   <Data><Attribute name="amount">010</Attribute><Attribute name="amount">020</Attribute></Data>
   <AuditTrailEntry>
    <Data><Attribute name="concept:name">extra field</Attribute><Attribute name="empty"/></Data>
    <WorkflowModelElement>Approve</WorkflowModelElement>
    <EventType unknowntype="business milestone">unknown</EventType>
    <Timestamp>2020-02-03T04:05:06.123456+05:30</Timestamp>
    <Originator>operator</Originator>
   </AuditTrailEntry>
  </ProcessInstance>
  <ProcessInstance id="duplicate"/>
 </Process>
 <Process id="invoice"><ProcessInstance id="duplicate"><AuditTrailEntry/></ProcessInstance></Process>
</WorkflowLog>"""
    path = _write(tmp_path, xml)
    result = import_mxml(path)
    assert result.status is ImportStatus.VALID
    log = result.require_case_log()
    assert [trace.id for trace in log.traces] == ["trace:0", "trace:1", "trace:2"]
    assert [trace.attribute("concept:name").value for trace in log.traces] == [
        "duplicate",
        "duplicate",
        "duplicate",
    ]
    assert [trace.attribute("mxml:processIndex").value for trace in log.traces] == [
        0,
        0,
        1,
    ]
    assert log.traces[1].events == ()
    assert log.traces[2].events[0].id == "event:2:0"
    assert _attribute(log.attributes, "mxml:description").value == "original log"
    assert (
        _attribute(log.attributes, "mxml:xsi:noNamespaceSchemaLocation").value
        == "WorkflowLog.xsd"
    )
    assert _attribute(log.attributes, "mxml:data").children[0].value == "한글 & text"
    source = _attribute(log.attributes, "mxml:source")
    assert _attribute(source.children, "mxml:program").value == "Recorder"
    assert _attribute(source.children, "mxml:data").children[0].value == "1.2"
    processes = _attribute(log.attributes, "mxml:processes").values
    assert len(processes) == 2
    assert _attribute(processes[0].children, "mxml:id").value == "invoice"
    assert _attribute(processes[0].children, "mxml:description").value == "invoices"
    assert _attribute(processes[0].children, "mxml:data").children[0].value == "finance"
    trace = log.traces[0]
    assert trace.attribute("mxml:description").value == "a case"
    assert [(a.key, a.value) for a in trace.attribute("mxml:data").children] == [
        ("amount", "010"),
        ("amount", "020"),
    ]
    event = trace.events[0]
    assert event.id == "event:0:0"
    assert event.activity == "Approve"
    assert event.attribute("mxml:data").children[0].value == "extra field"
    assert event.attribute("mxml:data").children[1].value == ""
    lifecycle = event.attribute("lifecycle:transition")
    assert lifecycle.value == "unknown"
    assert lifecycle.children[0].key == "mxml:unknowntype"
    assert lifecycle.children[0].value == "business milestone"
    assert event.timestamp == datetime(
        2020, 2, 3, 4, 5, 6, 123456, timezone(timedelta(hours=5, minutes=30))
    )
    assert (
        event.attribute("time:timestamp").lexical == "2020-02-03T04:05:06.123456+05:30"
    )
    assert event.attribute("org:resource").value == "operator"
    assert log.source.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert log.source.sha256 == result.source_sha256
    assert log.source.size == len(path.read_bytes()) == result.source_size
    assert log.source.format == "mxml"


def test_gzip_provenance_identifies_compressed_file(tmp_path):
    raw = _wrap(
        "<AuditTrailEntry><WorkflowModelElement>A</WorkflowModelElement></AuditTrailEntry>"
    ).encode()
    compressed = gzip.compress(raw, mtime=0)
    path = tmp_path / "log.mxml.gz"
    path.write_bytes(compressed)
    log = read_mxml(path)
    assert log.traces[0].events[0].activity == "A"
    assert log.source.sha256 == hashlib.sha256(compressed).hexdigest()
    assert log.source.size == len(compressed)


def test_missing_fields_empty_containers_and_text_are_not_invented(tmp_path):
    path = _write(
        tmp_path,
        _wrap("""<Data/>
      <AuditTrailEntry><Data/></AuditTrailEntry>
      <AuditTrailEntry><WorkflowModelElement>  A  </WorkflowModelElement><Originator/></AuditTrailEntry>
      <AuditTrailEntry><Timestamp>2020-02-03T04:05:06</Timestamp></AuditTrailEntry>"""),
    )
    trace = read_mxml(path).traces[0]
    assert trace.attribute("mxml:data").children == ()
    missing, text, naive = trace.events
    assert missing.activity is None and missing.timestamp is None
    assert missing.attribute("lifecycle:transition") is None
    assert missing.attribute("mxml:data").children == ()
    assert text.activity == "  A  "
    assert text.attribute("org:resource").value == ""
    assert naive.timestamp.tzinfo is None
    assert naive.activity is None


def test_reordered_known_children_preserve_historical_input(tmp_path):
    xml = _wrap("""<AuditTrailEntry><Originator>Alice</Originator>
      <EventType>complete</EventType><WorkflowModelElement>A</WorkflowModelElement>
      <Timestamp>2020-01-01T00:00:00Z</Timestamp><Data/></AuditTrailEntry>""")
    event = read_mxml(_write(tmp_path, xml)).traces[0].events[0]
    assert event.activity == "A"
    assert event.attribute("lifecycle:transition").value == "complete"
    assert event.timestamp == datetime(2020, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "xml, code",
    [
        ("<log/>", "root"),
        ('<WorkflowLog xmlns="urn:foreign"/>', "root"),
        ("<WorkflowLog><Unknown/></WorkflowLog>", "unknown_element"),
        ('<WorkflowLog unexpected="payload"/>', "unknown_attribute"),
        (
            '<WorkflowLog><Source program="A" extra="B"/></WorkflowLog>',
            "unknown_attribute",
        ),
        (
            '<WorkflowLog><Process id="p" modelReference="urn:p"/></WorkflowLog>',
            "unknown_attribute",
        ),
        (_wrap('<AuditTrailEntry id="lost"/>'), "unknown_attribute"),
        (
            _wrap('<AuditTrailEntry><Timestamp extra="lost"/></AuditTrailEntry>'),
            "unknown_attribute",
        ),
        (
            _wrap(
                '<AuditTrailEntry><Data><Attribute name="x" type="int">1</Attribute></Data></AuditTrailEntry>'
            ),
            "unknown_attribute",
        ),
        (
            _wrap(
                "<AuditTrailEntry><WorkflowModelElement><Nested/></WorkflowModelElement></AuditTrailEntry>"
            ),
            "unknown_element",
        ),
        (
            _wrap(
                "<AuditTrailEntry><WorkflowModelElement>A</WorkflowModelElement><WorkflowModelElement>B</WorkflowModelElement></AuditTrailEntry>"
            ),
            "duplicate_element",
        ),
        (
            _wrap("<AuditTrailEntry><Data/><Data/></AuditTrailEntry>"),
            "duplicate_element",
        ),
        (
            _wrap("<AuditTrailEntry><EventType>custom</EventType></AuditTrailEntry>"),
            "event_type",
        ),
        ("<WorkflowLog><Source/></WorkflowLog>", "missing_attribute"),
        ("<WorkflowLog><Process/></WorkflowLog>", "missing_attribute"),
        (
            '<WorkflowLog><Process id="p"><ProcessInstance/></Process></WorkflowLog>',
            "missing_attribute",
        ),
        (_wrap("<Data><Attribute>lost name</Attribute></Data>"), "missing_attribute"),
        ('<WorkflowLog>lost<Process id="p"/></WorkflowLog>', "unexpected_text"),
        ('<WorkflowLog><Process id="p"/>lost</WorkflowLog>', "unexpected_text"),
        (
            _wrap(
                "<AuditTrailEntry><WorkflowModelElement>A</WorkflowModelElement>lost<EventType>complete</EventType></AuditTrailEntry>"
            ),
            "unexpected_text",
        ),
    ],
)
def test_unsupported_content_fails_without_partial_candidate(tmp_path, xml, code):
    result = import_mxml(_write(tmp_path, xml))
    assert result.status is ImportStatus.SCHEMA_INVALID
    assert result.candidate is None
    assert result.import_issues[0].code == "mxml." + code


@pytest.mark.parametrize(
    "xml",
    [
        _wrap(
            "<AuditTrailEntry><Timestamp>not a timestamp</Timestamp></AuditTrailEntry>"
        ),
        _wrap(
            "<AuditTrailEntry><Timestamp>2020-02-30T00:00:00Z</Timestamp></AuditTrailEntry>"
        ),
        '<!DOCTYPE WorkflowLog [<!ENTITY x "expanded">]><WorkflowLog description="&x;"/>',
        '<!DOCTYPE WorkflowLog SYSTEM "file:///unavailable"><WorkflowLog/>',
        _wrap("<AuditTrailEntry/>")[:-2],
        _wrap("<AuditTrailEntry/>") + "<broken>",
    ],
)
def test_invalid_dates_entities_and_truncated_documents_fail_atomically(tmp_path, xml):
    path = _write(tmp_path, xml)
    result = import_mxml(path)
    assert not result.valid
    assert result.candidate is None
    with pytest.raises(CaseImportError) as caught:
        read_mxml(path)
    assert not caught.value.result.valid


def test_small_chunks_preserve_order_and_detect_delayed_tail_text():
    class TinyStream(BytesIO):
        def read(self, size=-1):
            return super().read(1 if size < 0 else min(size, 1))

    events = "".join(
        "<AuditTrailEntry><WorkflowModelElement>"
        + str(index)
        + "</WorkflowModelElement></AuditTrailEntry>"
        for index in range(200)
    )
    log = _parse_mxml(TinyStream(_wrap(events).encode()))
    assert [event.activity for event in log.traces[0].events] == [
        str(i) for i in range(200)
    ]
    assert log.traces[0].events[-1].id == "event:0:199"
    invalid = _wrap("<AuditTrailEntry/>late tail<AuditTrailEntry/>").encode()
    with pytest.raises(ValueError, match="Unexpected text"):
        _parse_mxml(TinyStream(invalid))


def test_empty_processes_retain_metadata_and_duplicate_labels(tmp_path):
    xml = '<WorkflowLog><Process id="p" description="first"/><Process id="p"/></WorkflowLog>'
    log = read_mxml(_write(tmp_path, xml))
    assert log.traces == ()
    processes = _attribute(log.attributes, "mxml:processes").values
    assert [item.children[0].value for item in processes] == [0, 1]
    assert [_attribute(item.children, "mxml:id").value for item in processes] == [
        "p",
        "p",
    ]


@pytest.mark.parametrize("offset", ["+00:60", "-00:60", "+23:59", "+14:01", "-14:01"])
def test_invalid_xml_timezone_offsets_are_not_normalized(tmp_path, offset):
    xml = _wrap(
        "<AuditTrailEntry><Timestamp>2020-01-01T00:00:00"
        + offset
        + "</Timestamp></AuditTrailEntry>"
    )
    result = import_mxml(_write(tmp_path, xml))
    assert result.status is ImportStatus.SCHEMA_INVALID
    assert result.candidate is None
    assert result.import_issues[0].code == "invalid_date"


def test_namespace_declarations_on_leaf_elements_are_preserved(tmp_path):
    xml = _wrap("""<AuditTrailEntry>
      <Data><Attribute xmlns:meta="urn:annotation" name="x">y</Attribute></Data>
      <Timestamp xmlns:clock="urn:clock">2020-01-01T00:00:00Z</Timestamp>
      <WorkflowModelElement xmlns:activity="urn:activity">A</WorkflowModelElement>
    </AuditTrailEntry>""")
    event = read_mxml(_write(tmp_path, xml)).traces[0].events[0]
    data = event.attribute("mxml:data").children[0]
    assert data.children[0].key == "mxml:xmlns:meta"
    assert data.children[0].value == "urn:annotation"
    assert event.attribute("time:timestamp").children[0].value == "urn:clock"
    assert event.attribute("concept:name").children[0].value == "urn:activity"


def test_data_xml_declarations_cannot_be_confused_with_user_keys(tmp_path):
    declared = read_mxml(
        _write(
            tmp_path,
            _wrap("""
      <Data xmlns:p="urn:one"><Attribute name="mxml:xmlns:p">urn:two</Attribute></Data>
    """),
            "declared.mxml",
        )
    )
    user_only = read_mxml(
        _write(
            tmp_path,
            _wrap("""
      <Data><Attribute name="mxml:xmlns:p">urn:one</Attribute>
      <Attribute name="mxml:xmlns:p">urn:two</Attribute></Data>
    """),
            "user.mxml",
        )
    )
    with_declaration = declared.traces[0].attribute("mxml:data")
    without_declaration = user_only.traces[0].attribute("mxml:data")
    assert with_declaration != without_declaration
    namespace = with_declaration.children[0]
    assert namespace.key == "mxml:xmlAttributes"
    assert namespace.type == "container"
    assert namespace.children[0].value == "urn:one"
    assert with_declaration.children[1].value == "urn:two"
    assert all(attribute.type == "string" for attribute in without_declaration.children)
