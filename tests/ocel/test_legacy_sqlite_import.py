"""Independent tiny fixtures for the classic PM4Py SQLite compatibility reader."""

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from pix.ocel import ImportFormat, ImportStatus, import_ocel
from pix.ocel.ingest.formats.common import AdapterFailure
from pix.ocel.ingest.formats.legacy_sqlite import load
from pix.ocel.model import OCEL_EPOCH, ValueType

_TIME = "2026-08-22T10:00:00Z"


def _write(path: Path) -> Path:
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE EVENTS (
                "ocel:eid" TEXT, "ocel:activity" TEXT, "ocel:timestamp" TIMESTAMP,
                "amount" INTEGER, "rate" REAL, "title" TEXT, "unused" TEXT
            );
            CREATE TABLE OBJECTS (
                "ocel:oid" TEXT, "ocel:type" TEXT, "status" TEXT
            );
            CREATE TABLE RELATIONS (
                "ocel:eid" TEXT, "ocel:activity" TEXT, "ocel:timestamp" TIMESTAMP,
                "ocel:oid" TEXT, "ocel:type" TEXT
            );
        """)
        connection.executemany(
            "INSERT INTO EVENTS VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("e1", "create", _TIME, 7, 1.25, "2026-01-01", None),
                ("e-orphan", "create", _TIME, None, None, None, None),
            ],
        )
        connection.executemany(
            "INSERT INTO OBJECTS VALUES (?, ?, ?)",
            [
                ("o1", "order", "new"),
                ("o-orphan", "order", None),
            ],
        )
        connection.execute(
            "INSERT INTO RELATIONS VALUES (?, ?, ?, ?, ?)",
            ("e1", "create", _TIME, "o1", "order"),
        )
    return path


def _execute(path: Path, sql: str, parameters: tuple[object, ...] = ()) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(sql, parameters)


def _equivalent() -> dict[str, object]:
    return {
        "eventTypes": [
            {
                "name": "create",
                "attributes": [
                    {"name": "amount", "type": "integer"},
                    {"name": "rate", "type": "float"},
                    {"name": "title", "type": "string"},
                ],
            }
        ],
        "objectTypes": [
            {
                "name": "order",
                "attributes": [
                    {"name": "status", "type": "string"},
                ],
            }
        ],
        "events": [
            {
                "id": "e1",
                "type": "create",
                "time": _TIME,
                "attributes": [
                    {"name": "amount", "value": 7},
                    {"name": "rate", "value": 1.25},
                    {"name": "title", "value": "2026-01-01"},
                ],
                "relationships": [{"objectId": "o1", "qualifier": ""}],
            },
            {"id": "e-orphan", "type": "create", "time": _TIME},
        ],
        "objects": [
            {
                "id": "o1",
                "type": "order",
                "attributes": [
                    {"name": "status", "value": "new", "time": "1970-01-01T00:00:00Z"},
                ],
            },
            {"id": "o-orphan", "type": "order"},
        ],
    }


def test_classic_matches_independent_ocel2_and_keeps_orphans(tmp_path: Path) -> None:
    path = _write(tmp_path / "source # encoded.sqlite")
    expected_path = tmp_path / "equivalent.jsonocel"
    expected_path.write_text(json.dumps(_equivalent()), encoding="utf-8")
    source_bytes = path.read_bytes()
    source_files = set(tmp_path.iterdir())

    actual, expected = import_ocel(path), import_ocel(expected_path)

    assert actual.valid and expected.valid
    assert actual.format is ImportFormat.OCEL10_SQLITE
    assert actual.canonical_digest == expected.canonical_digest
    assert actual.candidate == expected.candidate
    assert actual.source_sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert path.read_bytes() == source_bytes
    assert set(tmp_path.iterdir()) == source_files
    assert {event.id for event in actual.require_ocel().events} == {"e1", "e-orphan"}
    assert {obj.id for obj in actual.require_ocel().objects} == {"o1", "o-orphan"}
    assert all(link.qualifier == "" for link in actual.require_ocel().e2o)
    assert actual.require_ocel().objects[1].attributes[0].time == OCEL_EPOCH


def test_assumptions_and_null_missingness_are_disclosed(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    result = import_ocel(path, format="ocel10-sqlite")
    assert result.valid
    transformations = result.transformations
    counts = {item.code: item.count for item in transformations}
    assert counts["legacy_empty_qualifier"] == 1
    assert counts["legacy_timeless_object_attributes"] == 1
    assert counts["legacy_type_inference"] == 4
    nulls = {
        item.at: item.count
        for item in transformations
        if item.code == "legacy_sqlite_null_attributes_omitted"
    }
    assert nulls == {
        ("EVENTS", "amount"): 1,
        ("EVENTS", "rate"): 1,
        ("EVENTS", "title"): 1,
        ("EVENTS", "unused"): 2,
        ("OBJECTS", "status"): 1,
    }
    schema = {
        attr.name: attr.type for attr in result.require_ocel().event_types[0].attributes
    }
    assert schema == {
        "amount": ValueType.INTEGER,
        "rate": ValueType.FLOAT,
        "title": ValueType.STRING,
    }


@pytest.mark.parametrize(
    "timestamp", ["2026-08-22T19:00:00+09:00", "2026-08-22 10:00:00"]
)
def test_relation_timestamps_compare_instants_and_disclose_assumptions(
    tmp_path: Path,
    timestamp: str,
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'UPDATE RELATIONS SET "ocel:timestamp" = ?', (timestamp,))
    result = import_ocel(path)
    assert result.valid
    assert any(
        item.at == ("RELATIONS", "ocel:timestamp") for item in result.transformations
    )


@pytest.mark.parametrize("table", ["EVENTS", "OBJECTS", "RELATIONS"])
def test_missing_required_tables_are_structured(tmp_path: Path, table: str) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, f'DROP TABLE "{table}"')
    result = import_ocel(path, format="ocel10-sqlite")
    assert result.status is ImportStatus.SCHEMA_INVALID
    assert result.import_issues[0].code == "missing_legacy_sqlite_table"


@pytest.mark.parametrize(
    "table,column",
    [
        ("EVENTS", "ocel:eid"),
        ("EVENTS", "ocel:activity"),
        ("OBJECTS", "ocel:oid"),
        ("RELATIONS", "ocel:type"),
    ],
)
def test_fixed_column_case_is_exact(tmp_path: Path, table: str, column: str) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, f'ALTER TABLE "{table}" RENAME COLUMN "{column}" TO "temporary"')
    _execute(
        path, f'ALTER TABLE "{table}" RENAME COLUMN "temporary" TO "{column.upper()}"'
    )
    result = import_ocel(path, format="ocel10-sqlite")
    assert result.status is ImportStatus.SCHEMA_INVALID
    assert result.import_issues[0].code == "missing_legacy_sqlite_column"


def test_table_names_follow_sqlite_case_semantics(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    for table in ("EVENTS", "OBJECTS", "RELATIONS"):
        _execute(path, f'ALTER TABLE "{table}" RENAME TO "temporary"')
        _execute(path, f'ALTER TABLE "temporary" RENAME TO "{table.lower()}"')
    assert import_ocel(path).valid


@pytest.mark.parametrize("table", ["EVENTS", "OBJECTS"])
def test_duplicate_entity_ids_are_never_merged(tmp_path: Path, table: str) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, f'INSERT INTO "{table}" SELECT * FROM "{table}" LIMIT 1')
    result = import_ocel(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "duplicate_legacy_sqlite_id"


def test_duplicate_relations_reach_semantic_validator(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, "INSERT INTO RELATIONS SELECT * FROM RELATIONS")
    result = import_ocel(path)
    assert result.status is ImportStatus.SEMANTIC_INVALID
    assert len(result.candidate.e2o) == 2
    assert "duplicate_e2o" in {issue.code for issue in result.semantic_report.issues}


@pytest.mark.parametrize(
    "column,value",
    [
        ("ocel:activity", "different"),
        ("ocel:type", "different"),
        ("ocel:timestamp", "2026-08-22T10:00:01Z"),
        ("ocel:activity", None),
    ],
)
def test_contradictory_relation_facts_fail(
    tmp_path: Path, column: str, value: object
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, f'UPDATE RELATIONS SET "{column}" = ?', (value,))
    result = import_ocel(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "contradictory_legacy_sqlite_relation"


@pytest.mark.parametrize("column", ["ocel:eid", "ocel:oid"])
def test_absent_relation_endpoints_fail_without_dropping_links(
    tmp_path: Path, column: str
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, f'UPDATE RELATIONS SET "{column}" = ?', ("absent",))
    result = import_ocel(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "dangling_legacy_sqlite_relation"


@pytest.mark.parametrize("first,second", [(1, 1.5), (1, "1"), (1.0, "text")])
def test_observed_types_must_not_conflict(
    tmp_path: Path, first: object, second: object
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "mixed"')
    _execute(path, 'UPDATE EVENTS SET mixed = ? WHERE "ocel:eid" = ?', (first, "e1"))
    _execute(
        path, 'UPDATE EVENTS SET mixed = ? WHERE "ocel:eid" = ?', (second, "e-orphan")
    )
    result = import_ocel(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "legacy_attribute_type_conflict"


def test_same_attribute_name_can_have_different_types_per_activity(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "mixed"')
    _execute(path, 'UPDATE EVENTS SET mixed = 1 WHERE "ocel:eid" = ?', ("e1",))
    _execute(
        path,
        'UPDATE EVENTS SET mixed = ?, "ocel:activity" = ? WHERE "ocel:eid" = ?',
        ("text", "different", "e-orphan"),
    )
    assert import_ocel(path).valid


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), b"blob"])
def test_unrepresentable_attribute_values_fail(tmp_path: Path, value: object) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "unsafe"')
    _execute(path, 'UPDATE EVENTS SET unsafe = ? WHERE "ocel:eid" = ?', (value, "e1"))
    result = import_ocel(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "unsupported_legacy_sqlite_attribute"


def test_quoted_attribute_names_and_source_ids_are_preserved(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    name = 'odd"; DROP TABLE OBJECTS; --'
    quoted = '"' + name.replace('"', '""') + '"'
    _execute(path, f"ALTER TABLE EVENTS ADD COLUMN {quoted} TEXT")
    _execute(
        path, f'UPDATE EVENTS SET {quoted} = ? WHERE "ocel:eid" = ?', ("value", "e1")
    )
    _execute(
        path,
        'UPDATE EVENTS SET "ocel:eid" = ? WHERE "ocel:eid" = ?',
        ("사건 ' 001", "e1"),
    )
    _execute(path, 'UPDATE RELATIONS SET "ocel:eid" = ?', ("사건 ' 001",))
    result = import_ocel(path)
    assert result.valid
    event = next(
        item for item in result.require_ocel().events if item.id == "사건 ' 001"
    )
    assert next(attr.value for attr in event.attributes if attr.name == name) == "value"
    assert len(result.require_ocel().objects) == 2


def test_unicode_attribute_names_are_case_sensitive(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "Ä" TEXT')
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "ä" TEXT')
    _execute(
        path,
        'UPDATE EVENTS SET "Ä" = ?, "ä" = ? WHERE "ocel:eid" = ?',
        ("upper", "lower", "e1"),
    )
    result = import_ocel(path)
    assert result.valid
    event = next(event for event in result.require_ocel().events if event.id == "e1")
    values = {attr.name: attr.value for attr in event.attributes}
    assert values["Ä"] == "upper"
    assert values["ä"] == "lower"


def test_sql_boolean_declaration_does_not_invent_a_boolean_type(tmp_path: Path) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "flag" BOOLEAN')
    _execute(path, 'UPDATE EVENTS SET flag = 1 WHERE "ocel:eid" = ?', ("e1",))
    result = import_ocel(path)
    assert result.valid
    declaration = next(
        attr
        for attr in result.require_ocel().event_types[0].attributes
        if attr.name == "flag"
    )
    assert declaration.type is ValueType.INTEGER


def test_ignored_extra_tables_views_and_relation_columns_are_explicit(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    _execute(path, 'CREATE TABLE "metadata" (value TEXT)')
    _execute(path, 'CREATE VIEW "unread" AS SELECT no_such_function(1)')
    _execute(path, 'ALTER TABLE RELATIONS ADD COLUMN "ocel:qualifier" TEXT')
    _execute(
        path, 'UPDATE RELATIONS SET "ocel:qualifier" = ?', ("not-in-classic-model",)
    )
    result = import_ocel(path)
    assert result.valid
    omitted = {
        item.at
        for item in result.transformations
        if item.code == "legacy_sqlite_extra_content_not_preserved"
    }
    assert omitted == {("metadata",), ("unread",), ("RELATIONS", "ocel:qualifier")}
    assert result.require_ocel().e2o[0].qualifier == ""


@pytest.mark.parametrize("kind", ["view", "virtual", "generated"])
def test_unsafe_or_computed_core_schema_is_rejected(tmp_path: Path, kind: str) -> None:
    path = _write(tmp_path / "classic.sqlite")
    if kind == "generated":
        _execute(path, 'ALTER TABLE EVENTS ADD COLUMN "computed" AS (amount + 1)')
    else:
        _execute(path, "DROP TABLE EVENTS")
        if kind == "view":
            _execute(path, 'CREATE VIEW EVENTS AS SELECT 1 AS "ocel:eid"')
        else:
            _execute(path, 'CREATE VIRTUAL TABLE EVENTS USING fts5("ocel:eid")')
    result = import_ocel(path, format="ocel10-sqlite")
    assert result.status is ImportStatus.SCHEMA_INVALID
    assert result.import_issues[0].code.startswith("unsupported_legacy_sqlite_")


def test_without_rowid_tables_are_supported(tmp_path: Path) -> None:
    path = tmp_path / "classic.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE EVENTS ("ocel:eid" TEXT PRIMARY KEY, "ocel:activity" TEXT,
                                 "ocel:timestamp" TEXT) WITHOUT ROWID;
            CREATE TABLE OBJECTS ("ocel:oid" TEXT PRIMARY KEY, "ocel:type" TEXT) WITHOUT ROWID;
            CREATE TABLE RELATIONS ("ocel:eid" TEXT, "ocel:activity" TEXT,
                "ocel:timestamp" TEXT, "ocel:oid" TEXT, "ocel:type" TEXT,
                PRIMARY KEY ("ocel:eid", "ocel:oid")) WITHOUT ROWID;
        """)
    result = import_ocel(path)
    assert result.valid
    assert result.require_ocel().events == ()


def test_invalid_database_and_invalid_utf8_are_structured(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.sqlite"
    malformed.write_bytes(b"not SQLite")
    with pytest.raises(AdapterFailure) as failure:
        load(malformed)
    assert failure.value.code == "invalid_sqlite"
    path = _write(tmp_path / "invalid-utf8.sqlite")
    _execute(path, "UPDATE EVENTS SET title = CAST(x'80' AS TEXT)")
    result = import_ocel(path)
    assert result.status is ImportStatus.SYNTAX_INVALID
    assert result.import_issues[0].code == "invalid_sqlite"


def test_readonly_loader_does_not_create_a_missing_database(tmp_path: Path) -> None:
    path = tmp_path / "absent.sqlite"
    with pytest.raises(AdapterFailure) as failure:
        load(path)
    assert failure.value.code == "invalid_sqlite"
    assert not path.exists()


def test_wrong_explicit_sqlite_dialect_is_not_silently_reinterpreted(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    result = import_ocel(path, format="ocel20-sqlite")
    assert result.format is ImportFormat.OCEL20_SQLITE
    assert result.status is ImportStatus.SCHEMA_INVALID


def test_wal_mode_is_rejected_before_connection_without_creating_sidecars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write(tmp_path / "classic.sqlite")
    connection = sqlite3.connect(path)
    try:
        assert connection.execute("PRAGMA journal_mode = WAL").fetchone()[0] == "wal"
    finally:
        connection.close()
    before = {item.name: item.read_bytes() for item in tmp_path.iterdir()}

    def forbidden_connection(*args: object, **kwargs: object) -> None:
        pytest.fail("WAL input must be rejected before connecting")

    monkeypatch.setattr(sqlite3, "connect", forbidden_connection)
    with pytest.raises(AdapterFailure) as failure:
        load(path)
    assert failure.value.code == "unsupported_legacy_sqlite_journal"
    assert {item.name: item.read_bytes() for item in tmp_path.iterdir()} == before


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_journal_sidecars_are_not_ignored(tmp_path: Path, suffix: str) -> None:
    path = _write(tmp_path / "classic.sqlite")
    sidecar = path.with_name(path.name + suffix)
    sidecar.write_bytes(b"source sidecar must be retained")
    before = {item.name: item.read_bytes() for item in tmp_path.iterdir()}
    with pytest.raises(AdapterFailure) as failure:
        load(path)
    assert failure.value.code == "unsupported_legacy_sqlite_journal"
    assert {item.name: item.read_bytes() for item in tmp_path.iterdir()} == before
