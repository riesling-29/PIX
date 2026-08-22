import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pix.ocel import (
    ImportFormat,
    ImportStatus,
    OCELImportError,
    TimezoneAssumptionWarning,
    import_ocel,
    read_ocel,
)


def _document() -> dict[str, object]:
    return {
        "eventTypes": [
            {
                "name": "create",
                "attributes": [{"name": "amount", "type": "float"}],
            }
        ],
        "objectTypes": [
            {
                "name": "order",
                "attributes": [{"name": "status", "type": "string"}],
            }
        ],
        "events": [
            {
                "id": "e1",
                "type": "create",
                "time": "2026-08-22T10:00:00Z",
                "attributes": [{"name": "amount", "value": 12.5}],
                "relationships": [
                    {"objectId": "o1", "qualifier": "target"},
                    {"objectId": "o1", "qualifier": "audit"},
                ],
            }
        ],
        "objects": [
            {
                "id": "o1",
                "type": "order",
                "attributes": [
                    {
                        "name": "status",
                        "value": "new",
                        "time": "1970-01-01T00:00:00Z",
                    }
                ],
                "relationships": [
                    {"objectId": "o2", "qualifier": "parent"}
                ],
            },
            {
                "id": "o2",
                "type": "order",
                "attributes": [],
                "relationships": [],
            },
        ],
    }


def _write_json(path: Path, document: object | None = None) -> None:
    path.write_text(
        json.dumps(_document() if document is None else document),
        encoding="utf-8",
    )


def _write_xml(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<log>
  <object-types>
    <object-type name="order"><attributes>
      <attribute name="status" type="string"/>
    </attributes></object-type>
  </object-types>
  <event-types>
    <event-type name="create"><attributes>
      <attribute name="amount" type="float"/>
    </attributes></event-type>
  </event-types>
  <objects>
    <object id="o1" type="order">
      <attributes>
        <attribute name="status" time="1970-01-01T00:00:00Z">new</attribute>
      </attributes>
      <objects><relationship object-id="o2" qualifier="parent"/></objects>
    </object>
    <object id="o2" type="order"><attributes/><objects/></object>
  </objects>
  <events>
    <event id="e1" type="create" time="2026-08-22T10:00:00Z">
      <attributes><attribute name="amount">12.5</attribute></attributes>
      <objects>
        <relationship object-id="o1" qualifier="target"/>
        <relationship object-id="o1" qualifier="audit"/>
      </objects>
    </event>
  </events>
</log>
""",
        encoding="utf-8",
    )


def _write_sqlite(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
CREATE TABLE event_map_type (ocel_type TEXT, ocel_type_map TEXT);
CREATE TABLE object_map_type (ocel_type TEXT, ocel_type_map TEXT);
CREATE TABLE event (ocel_id TEXT, ocel_type TEXT);
CREATE TABLE object (ocel_id TEXT, ocel_type TEXT);
CREATE TABLE event_object (
    ocel_event_id TEXT, ocel_object_id TEXT, ocel_qualifier TEXT
);
CREATE TABLE object_object (
    ocel_source_id TEXT, ocel_target_id TEXT, ocel_qualifier TEXT
);
CREATE TABLE event_create (
    ocel_id TEXT, ocel_time TIMESTAMP, amount REAL
);
CREATE TABLE object_order (
    ocel_id TEXT,
    ocel_time TIMESTAMP,
    ocel_changed_field TEXT,
    status TEXT
);
INSERT INTO event_map_type VALUES ('create', 'create');
INSERT INTO object_map_type VALUES ('order', 'order');
INSERT INTO event VALUES ('e1', 'create');
INSERT INTO object VALUES ('o1', 'order'), ('o2', 'order');
INSERT INTO event_create VALUES (
    'e1', '2026-08-22T10:00:00Z', 12.5
);
INSERT INTO object_order VALUES
    ('o1', '1970-01-01T00:00:00Z', NULL, 'new'),
    ('o2', '1970-01-01T00:00:00Z', NULL, NULL);
INSERT INTO event_object VALUES
    ('e1', 'o1', 'target'),
    ('e1', 'o1', 'audit');
INSERT INTO object_object VALUES ('o1', 'o2', 'parent');
"""
        )
        connection.commit()
    finally:
        connection.close()


def test_read_ocel_returns_valid_canonical_result(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    _write_json(path)

    result = import_ocel(path)

    assert result.status is ImportStatus.VALID
    assert result.format is ImportFormat.OCEL20_JSON
    assert result.source_size == path.stat().st_size
    assert result.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.canonical_digest is not None
    assert result.describe()["candidate"]["eventCount"] == 1
    assert read_ocel(path) == result.ocel
    assert read_ocel(path).e2o_for_event("e1", qualifier="audit")


def test_equivalent_formats_have_one_canonical_digest(tmp_path: Path) -> None:
    json_path = tmp_path / "sample.jsonocel"
    xml_path = tmp_path / "sample.xmlocel"
    sqlite_path = tmp_path / "sample.sqlite"
    _write_json(json_path)
    _write_xml(xml_path)
    _write_sqlite(sqlite_path)

    results = tuple(
        import_ocel(path) for path in (json_path, xml_path, sqlite_path)
    )

    assert all(result.valid for result in results)
    assert {result.canonical_digest for result in results} == {
        results[0].canonical_digest
    }
    assert {result.candidate for result in results} == {results[0].candidate}


def test_format_can_be_detected_from_content_or_overridden(tmp_path: Path) -> None:
    path = tmp_path / "sample.data"
    _write_json(path)

    assert import_ocel(path).format is ImportFormat.OCEL20_JSON
    assert read_ocel(path, format="json") == read_ocel(path)


@pytest.mark.parametrize(
    ("content", "status", "code"),
    (
        ("{", ImportStatus.SYNTAX_INVALID, "invalid_json"),
        ("{}", ImportStatus.SCHEMA_INVALID, "missing_required_member"),
    ),
)
def test_json_failures_are_classified(
    tmp_path: Path,
    content: str,
    status: ImportStatus,
    code: str,
) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")

    result = import_ocel(path)

    assert result.status is status
    assert result.candidate is None
    assert result.import_issues[0].code == code


def test_naive_timestamp_is_assumed_utc_and_exposed_on_log(tmp_path: Path) -> None:
    document = _document()
    document["events"][0]["time"] = "2026-08-22T10:00:00"
    path = tmp_path / "naive.json"
    _write_json(path, document)

    result = import_ocel(path)

    assert result.status is ImportStatus.VALID
    assert result.import_issues[0].code == "timezone_assumed_utc"
    assert result.transformations[-1].code == "timezone_assumed_utc"
    assert result.transformations[-1].count == 1
    assert result.ocel is not None
    assert result.ocel.timezone_type == "UTC"
    assert result.ocel.timezone_info.source_type == "ASSUMED_UTC"
    assert result.ocel.timezone_info.assumed_utc_count == 1
    assert result.ocel.warnings[0].count == 1
    assert result.ocel.import_info is not None
    assert result.ocel.describe()["timezoneType"] == "UTC"

    with pytest.warns(TimezoneAssumptionWarning, match="Assumed UTC for 1"):
        log = read_ocel(path)
    assert log.events[0].time.isoformat() == "2026-08-22T10:00:00+00:00"


def test_invalid_timestamp_remains_a_mapping_failure(tmp_path: Path) -> None:
    document = _document()
    document["events"][0]["time"] = "not a timestamp"
    path = tmp_path / "invalid.json"
    _write_json(path, document)

    result = import_ocel(path)

    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "invalid_timestamp"
    assert result.semantic_report is None


def test_legacy_timestamp_with_explicit_offset_is_normalized(tmp_path: Path) -> None:
    path = tmp_path / "legacy.xml"
    _write_xml(path)
    content = path.read_text(encoding="utf-8").replace(
        "1970-01-01T00:00:00Z",
        "Thu Jan 01 1970 01:00:00 GMT+0100 "
        "(Central European Standard Time)",
    )
    path.write_text(content, encoding="utf-8")

    log = read_ocel(path)

    assert log.timezone_type == "UTC"
    assert log.timezone_info.source_type == "LEGACY_OFFSET_AWARE"
    assert log.timezone_info.legacy_offset_count == 1
    assert log.timezone_info.normalized_offset_count == 1
    assert not log.warnings
    assert log.get_object("o1").attributes[0].time.isoformat() == (
        "1970-01-01T00:00:00+00:00"
    )


def test_semantic_failure_preserves_candidate_and_report(tmp_path: Path) -> None:
    document = _document()
    document["events"][0]["relationships"][0]["objectId"] = "missing"
    path = tmp_path / "invalid.json"
    _write_json(path, document)

    result = import_ocel(path)

    assert result.status is ImportStatus.SEMANTIC_INVALID
    assert result.candidate is not None
    assert result.semantic_report is not None
    assert result.semantic_report.has("dangling_e2o_object")
    assert result.canonical_digest is None
    with pytest.raises(OCELImportError) as captured:
        read_ocel(path)
    assert captured.value.result == result


def test_unavailable_and_unsupported_sources_are_evidence_results(
    tmp_path: Path,
) -> None:
    missing = import_ocel(tmp_path / "missing.json")
    assert missing.status is ImportStatus.UNAVAILABLE
    assert missing.format is ImportFormat.OCEL20_JSON

    path = tmp_path / "sample.bin"
    path.write_bytes(b"not an OCEL")
    unsupported = import_ocel(path)
    assert unsupported.status is ImportStatus.UNSUPPORTED
    assert unsupported.source_sha256 is not None
    assert unsupported.source_size == len(b"not an OCEL")
