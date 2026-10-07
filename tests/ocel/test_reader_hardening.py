"""Source-loss regressions for the OCEL reader structural and mapping profiles."""

import gzip
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from pix.ocel import ImportStatus, import_ocel

STAMP = "2026-09-09T10:00:00Z"


def _document() -> dict:
    return {
        "eventTypes": [
            {
                "name": "A",
                "attributes": [
                    {"name": "clock", "type": "time"},
                    {"name": "number", "type": "float"},
                    {"name": "text", "type": "string"},
                ],
            }
        ],
        "objectTypes": [
            {
                "name": "Order",
                "attributes": [
                    {"name": "clock", "type": "time"},
                ],
            }
        ],
        "events": [
            {
                "id": "e1",
                "type": "A",
                "time": STAMP,
                "attributes": [
                    {"name": "clock", "value": STAMP},
                    {"name": "number", "value": 1.5},
                    {"name": "text", "value": "hello"},
                ],
                "relationships": [{"objectId": "o1", "qualifier": ""}],
            }
        ],
        "objects": [
            {
                "id": "o1",
                "type": "Order",
                "attributes": [{"name": "clock", "time": STAMP, "value": STAMP}],
                "relationships": [{"objectId": "o2", "qualifier": "parent"}],
            },
            {"id": "o2", "type": "Order", "attributes": [], "relationships": []},
        ],
    }


def _xml(document: dict | None = None, relation_tag: str = "relobj") -> str:
    document = _document() if document is None else document
    root = ET.Element("log")
    for kind in ("object", "event"):
        container = ET.SubElement(root, f"{kind}-types")
        for declaration in document[f"{kind}Types"]:
            node = ET.SubElement(container, f"{kind}-type", name=declaration["name"])
            attributes = ET.SubElement(node, "attributes")
            for attribute in declaration["attributes"]:
                ET.SubElement(attributes, "attribute", attribute)
    for kind in ("object", "event"):
        container = ET.SubElement(root, f"{kind}s")
        for record in document[f"{kind}s"]:
            fields = {key: record[key] for key in ("id", "type")}
            if kind == "event":
                fields["time"] = record["time"]
            node = ET.SubElement(container, kind, fields)
            attributes = ET.SubElement(node, "attributes")
            for attribute in record["attributes"]:
                fields = {"name": attribute["name"]}
                if kind == "object":
                    fields["time"] = attribute["time"]
                leaf = ET.SubElement(attributes, "attribute", fields)
                value = attribute["value"]
                leaf.text = (
                    str(value).lower() if isinstance(value, bool) else str(value)
                )
            relationships = ET.SubElement(node, "objects")
            for relation in record["relationships"]:
                ET.SubElement(
                    relationships,
                    relation_tag,
                    {
                        "object-id": relation["objectId"],
                        "qualifier": relation["qualifier"],
                    },
                )
    return ET.tostring(root, encoding="unicode")


def _write_document(path: Path, document: dict) -> None:
    text = _xml(document) if path.suffix == ".xml" else json.dumps(document)
    path.write_text(text, encoding="utf-8")


def _sqlite(path: Path, timestamp: str = STAMP) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
CREATE TABLE event_map_type (ocel_type TEXT, ocel_type_map TEXT);
CREATE TABLE object_map_type (ocel_type TEXT, ocel_type_map TEXT);
CREATE TABLE event (ocel_id TEXT, ocel_type TEXT);
CREATE TABLE object (ocel_id TEXT, ocel_type TEXT);
CREATE TABLE event_object (ocel_event_id TEXT, ocel_object_id TEXT, ocel_qualifier TEXT);
CREATE TABLE object_object (ocel_source_id TEXT, ocel_target_id TEXT, ocel_qualifier TEXT);
CREATE TABLE event_a (ocel_id TEXT, ocel_time TIMESTAMP);
CREATE TABLE object_order (ocel_id TEXT, ocel_time TIMESTAMP, ocel_changed_field TEXT);
INSERT INTO event_map_type VALUES ('A', 'a');
INSERT INTO object_map_type VALUES ('Order', 'order');
INSERT INTO event VALUES ('e1', 'A');
INSERT INTO object VALUES ('o1', 'Order'), ('o2', 'Order');
INSERT INTO object_order VALUES ('o1', '1970-01-01T00:00:00Z', NULL),
                                ('o2', '1970-01-01T00:00:00Z', NULL);
INSERT INTO event_object VALUES ('e1', 'o1', 'target');
INSERT INTO object_object VALUES ('o1', 'o2', 'parent');
""")
        connection.execute("INSERT INTO event_a VALUES (?, ?)", ("e1", timestamp))


def _failure(path: Path, status: ImportStatus, code: str) -> None:
    result = import_ocel(path)
    assert result.status is status
    assert result.import_issues[0].code == code
    assert result.candidate is None
    assert result.canonical_digest is None
    assert result.source_sha256 is not None
    assert result.source_size == path.stat().st_size


@pytest.mark.parametrize(
    "before,after",
    [
        ('"events":', '"events": [], "events":'),
        ('"id": "e1"', '"id": "e1", "id": "e1"'),
        ('"id": "e1"', '"id": "lost", "id": "e1"'),
        ('"value": 1.5', '"value": 1.5, "value": 1.5'),
        ('"qualifier": ""', '"qualifier": "lost", "qualifier": ""'),
    ],
)
def test_duplicate_json_members_never_overwrite_source(
    tmp_path: Path, before: str, after: str
) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text(json.dumps(_document()).replace(before, after), encoding="utf-8")
    _failure(path, ImportStatus.SCHEMA_INVALID, "duplicate_json_member")


@pytest.mark.parametrize(
    "before,after,code",
    [
        ("<log>", '<log xmlns="urn:other">', "unsupported_xml_namespace"),
        ("<log>", '<log xmlns:unused="urn:other">', "unsupported_xml_namespace"),
        ("<log>", '<log xmlns:x="urn:other" x:extra="1">', "unsupported_xml_namespace"),
        ("<log>", '<log extra="1">', "unexpected_xml_attribute"),
        ("<events>", '<events extra="1">', "unexpected_xml_attribute"),
        (
            '<event-type name="A">',
            '<event-type name="A" extra="1">',
            "unexpected_xml_attribute",
        ),
        ('<event id="e1"', '<event extra="1" id="e1"', "unexpected_xml_attribute"),
        (
            '<attribute name="number">',
            '<attribute name="number" extra="1">',
            "unexpected_xml_attribute",
        ),
        (
            '<relobj object-id="o2"',
            '<relobj extra="1" object-id="o2"',
            "unexpected_xml_attribute",
        ),
        (' qualifier="parent"', "", "missing_xml_attribute"),
        ("<events>", "<events><wrapper/>", "unexpected_xml_element"),
        ("<log>", '<log><event id="bad"/>', "unexpected_xml_element"),
        ("hello", "hello<extra/>", "unexpected_xml_element"),
        ("<events>", "<events>lost text", "unexpected_xml_text"),
        ("</event>", "</event>lost text", "unexpected_xml_text"),
        ("</event>", "</event>" + " " * 17000 + "lost text", "unexpected_xml_text"),
        ("</events>", "</events><events/>", "duplicate_xml_container"),
        ("</event>", "<attributes/></event>", "duplicate_xml_container"),
        ("</event>", "<objects/></event>", "duplicate_xml_container"),
        (
            '<relobj object-id="o1"',
            '<relationship object-id="o1"',
            "mixed_xml_relation_dialect",
        ),
    ],
)
def test_xml_rejects_every_unrepresented_structure(
    tmp_path: Path, before: str, after: str, code: str
) -> None:
    path = tmp_path / "invalid.xml"
    assert before in _xml()
    path.write_text(_xml().replace(before, after, 1), encoding="utf-8")
    _failure(path, ImportStatus.SCHEMA_INVALID, code)


@pytest.mark.parametrize(
    "section", ["object-types", "event-types", "objects", "events"]
)
def test_xml_requires_each_root_section(tmp_path: Path, section: str) -> None:
    tree = ET.fromstring(_xml())
    tree.remove(tree.find(section))
    path = tmp_path / "missing.xml"
    path.write_text(ET.tostring(tree, encoding="unicode"), encoding="utf-8")
    _failure(path, ImportStatus.SCHEMA_INVALID, "missing_xml_container")


def test_xml_alias_and_reordered_optional_containers_preserve_semantics(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / "standard.xml", tmp_path / "legacy.xml"]
    paths[0].write_text(_xml(), encoding="utf-8")
    tree = ET.fromstring(_xml(relation_tag="relationship"))
    tree[:] = list(reversed(tree))
    for element in tree.iter():
        for child in list(element):
            if child.tag in {"attributes", "objects"} and not len(child):
                element.remove(child)
    paths[1].write_text(ET.tostring(tree, encoding="unicode"), encoding="utf-8")
    standard, legacy = (import_ocel(path) for path in paths)
    assert standard.valid and legacy.valid
    assert standard.canonical_digest == legacy.canonical_digest
    assert len(legacy.ocel.e2o) == 1 and len(legacy.ocel.o2o) == 1
    alias = next(
        t for t in legacy.transformations if t.code == "legacy_xml_relationship_alias"
    )
    assert alias.count == 2
    assert "reference XSD not run" in legacy.transformations[-1].message


def test_xml_value_text_and_character_references_are_not_stripped(
    tmp_path: Path,
) -> None:
    path = tmp_path / "text.xml"
    path.write_text(
        _xml().replace("hello", "  first\n\tsecond&#13;  "), encoding="utf-8"
    )
    result = import_ocel(path)
    assert result.valid
    assert next(
        a.value for a in result.ocel.events[0].attributes if a.name == "text"
    ) == ("  first\n\tsecond\r  ")


@pytest.mark.parametrize("format", ["json", "xml"])
@pytest.mark.parametrize(
    "location", ["event", "event_value", "object_time", "object_value"]
)
@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-09T10:00:00.1234567Z",
        "2026-09-09T10:00:00,0000001Z",
        "2026-09-09T10:00:00+01:00:00.0000001",
        "2026-09-09T10:00:00-00:00:00,0000001",
    ],
)
def test_sub_microsecond_clock_and_offset_precision_are_rejected(
    tmp_path: Path, format: str, location: str, timestamp: str
) -> None:
    document = _document()
    if location == "event":
        document["events"][0]["time"] = timestamp
    elif location == "event_value":
        document["events"][0]["attributes"][0]["value"] = timestamp
    else:
        key = "time" if location == "object_time" else "value"
        document["objects"][0]["attributes"][0][key] = timestamp
    path = tmp_path / f"precision.{format}"
    _write_document(path, document)
    _failure(path, ImportStatus.MAPPING_INVALID, "timestamp_precision_loss")


@pytest.mark.parametrize("format", ["json", "xml", "sqlite"])
@pytest.mark.parametrize(
    "timestamp,expected",
    [
        ("2026-09-09T10:00:00.123456000Z", "2026-09-09T10:00:00.123456+00:00"),
        ("2026-09-09T10:00:00,123456000Z", "2026-09-09T10:00:00.123456+00:00"),
        ("2026-09-09T10:00:00+00:00:00.000001000", "2026-09-09T09:59:59.999999+00:00"),
        ("2026-09-09T10:00:00-00:00:00.000001000", "2026-09-09T10:00:00.000001+00:00"),
        ("2026-09-09T10:00:00+01:00:00.000001000", "2026-09-09T08:59:59.999999+00:00"),
        ("2026-09-09T10:00:00.1Z", "2026-09-09T10:00:00.100000+00:00"),
        ("2026-09-09T10:00:00,12Z", "2026-09-09T10:00:00.120000+00:00"),
        ("2026-09-09T10:00:00.1234Z", "2026-09-09T10:00:00.123400+00:00"),
        ("2026-09-09T10:00:00,12345Z", "2026-09-09T10:00:00.123450+00:00"),
        ("2026-09-09T10:00:00+00:00:00,1", "2026-09-09T09:59:59.900000+00:00"),
        ("2026-09-09T10:00:00-01:00:00,12", "2026-09-09T11:00:00.120000+00:00"),
        ("20260909T100000,123456000+010000,1", "2026-09-09T09:00:00.023456+00:00"),
    ],
)
def test_representable_fractions_preserve_exact_utc_instant(
    tmp_path: Path, format: str, timestamp: str, expected: str
) -> None:
    path = tmp_path / f"precision.{format}"
    if format == "sqlite":
        _sqlite(path, timestamp)
    else:
        document = _document()
        document["events"][0]["time"] = timestamp
        _write_document(path, document)
    result = import_ocel(path)
    assert result.valid
    assert result.ocel.events[0].time == datetime.fromisoformat(expected)
    assert result.ocel.events[0].time.tzinfo == timezone.utc


@pytest.mark.parametrize("format", ["json", "xml", "sqlite"])
@pytest.mark.parametrize(
    "timestamp,code",
    [
        ("0001-01-01T00:00:00+01:00", "timestamp_out_of_range"),
        ("9999-12-31T23:59:59-01:00", "timestamp_out_of_range"),
        ("2026-09-09T10:00:00.0000001Z", "timestamp_precision_loss"),
    ],
)
def test_timestamp_failures_are_import_results_not_exceptions(
    tmp_path: Path, format: str, timestamp: str, code: str
) -> None:
    path = tmp_path / f"timestamp.{format}"
    if format == "sqlite":
        _sqlite(path, timestamp)
    else:
        document = _document()
        document["events"][0]["time"] = timestamp
        _write_document(path, document)
    _failure(path, ImportStatus.MAPPING_INVALID, code)


def test_hyphen_datetime_separator_is_not_mistaken_for_an_offset(
    tmp_path: Path,
) -> None:
    document = _document()
    document["events"][0]["time"] = "2026-09-09-10:00:00.5"
    path = tmp_path / "separator.json"
    _write_document(path, document)
    result = import_ocel(path)
    assert result.valid
    assert result.ocel.events[0].time == datetime(
        2026, 9, 9, 10, 0, 0, 500000, tzinfo=timezone.utc
    )
    assert any(t.code == "timezone_assumed_utc" for t in result.transformations)


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-09-09T10:00:00.Z",
        "2026-09-09T10:00:00,+00:00",
        "2026-09-09T10:00:00.1.2Z",
        "2026-09-09T10:00:00+01:00:00.",
        "2026-09-09T10:00:00.1234567garbage",
        "2026-09-09T10:00:00+01:00:00,1garbage",
        "2026-09-09T10:00:00.1ZZ",
        "2026-09-09T10:00:00.1Zgarbage",
        "2026-09-09T10:00:00.1+01:0203",
        "2026-09-09T10:00:00.1+0102:03",
        "2026-09-09T10:0000.1Z",
        "2026-09-09T1000:00.1Z",
    ],
)
def test_fraction_compatibility_does_not_repair_malformed_timestamps(
    tmp_path: Path, timestamp: str
) -> None:
    document = _document()
    document["events"][0]["time"] = timestamp
    path = tmp_path / "malformed-fraction.json"
    _write_document(path, document)
    _failure(path, ImportStatus.MAPPING_INVALID, "invalid_timestamp")


@pytest.mark.parametrize("table", ["event_object", "object_object"])
@pytest.mark.parametrize("source", ["absent", None])
def test_sqlite_missing_relation_sources_are_never_discarded(
    tmp_path: Path, table: str, source: str | None
) -> None:
    path = tmp_path / "source.sqlite"
    _sqlite(path)
    with sqlite3.connect(path) as connection:
        connection.execute(f"INSERT INTO {table} VALUES (?, 'o1', 'lost')", (source,))
    _failure(path, ImportStatus.MAPPING_INVALID, "missing_sqlite_relation_source")


@pytest.mark.parametrize(
    "table,code",
    [("event_object", "dangling_e2o_object"), ("object_object", "dangling_o2o_target")],
)
def test_sqlite_missing_targets_remain_in_semantic_failure_candidate(
    tmp_path: Path, table: str, code: str
) -> None:
    path = tmp_path / "target.sqlite"
    _sqlite(path)
    with sqlite3.connect(path) as connection:
        column = "ocel_object_id" if table == "event_object" else "ocel_target_id"
        connection.execute(f"UPDATE {table} SET {column} = 'absent'")
    result = import_ocel(path)
    assert result.status is ImportStatus.SEMANTIC_INVALID
    assert result.semantic_report.has(code)
    assert result.candidate is not None and result.canonical_digest is None
    assert len(result.candidate.e2o) == 1 and len(result.candidate.o2o) == 1


@pytest.mark.parametrize("character", ["\u00a0", "\u0085", "\u2003"])
@pytest.mark.parametrize("before", ["<events>", "</event>"])
def test_xml_only_xml_whitespace_is_ignored_between_elements(
    tmp_path: Path, character: str, before: str
) -> None:
    path = tmp_path / "whitespace.xml"
    path.write_text(_xml().replace(before, before + character), encoding="utf-8")
    _failure(path, ImportStatus.SCHEMA_INVALID, "unexpected_xml_text")


@pytest.mark.parametrize(
    "table,column", [("event_a", "ocel_time"), ("object_order", "ocel_changed_field")]
)
def test_sqlite_fixed_columns_are_checked_even_for_unused_types(
    tmp_path: Path, table: str, column: str
) -> None:
    path = tmp_path / "columns.sqlite"
    _sqlite(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM event")
        connection.execute("DELETE FROM object")
        connection.execute("DELETE FROM event_object")
        connection.execute("DELETE FROM object_object")
        connection.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
    _failure(path, ImportStatus.SCHEMA_INVALID, "missing_sqlite_column")


def test_numeric_overflow_and_unicode_are_mapping_failures(tmp_path: Path) -> None:
    path = tmp_path / "overflow.json"
    document = _document()
    document["events"][0]["attributes"][1]["value"] = 10**400
    _write_document(path, document)
    _failure(path, ImportStatus.MAPPING_INVALID, "float_out_of_range")
    document = _document()
    document["events"][0]["attributes"].append(
        {"name": "undeclared", "value": "\ud800"}
    )
    _write_document(path, document)
    _failure(path, ImportStatus.MAPPING_INVALID, "invalid_unicode")


@pytest.mark.skipif(
    not hasattr(sys, "get_int_max_str_digits"), reason="Python before 3.11"
)
@pytest.mark.parametrize("format", ["json", "xml"])
def test_integer_conversion_limit_is_a_mapping_failure(
    tmp_path: Path, format: str
) -> None:
    limit = sys.get_int_max_str_digits()
    if not limit:
        pytest.skip("Interpreter integer conversion limit disabled")
    document = _document()
    document["eventTypes"][0]["attributes"][1]["type"] = "integer"
    document["events"][0]["attributes"][1]["value"] = 987
    content = json.dumps(document) if format == "json" else _xml(document)
    path = tmp_path / f"integer.{format}"
    path.write_text(content.replace("987", "9" * (limit + 1)), encoding="utf-8")
    _failure(path, ImportStatus.MAPPING_INVALID, "integer_out_of_range")


@pytest.mark.parametrize(
    "format,content,status,code",
    [
        (
            "json",
            '{"events": [], "events": []}',
            ImportStatus.SCHEMA_INVALID,
            "duplicate_json_member",
        ),
        (
            "xml",
            "<log><unknown/></log>",
            ImportStatus.SCHEMA_INVALID,
            "unexpected_xml_element",
        ),
    ],
)
def test_compressed_sources_use_the_same_strict_profile(
    tmp_path: Path, format: str, content: str, status: ImportStatus, code: str
) -> None:
    path = tmp_path / f"strict.{format}.gz"
    path.write_bytes(gzip.compress(content.encode("utf-8")))
    _failure(path, status, code)
