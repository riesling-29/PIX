from __future__ import annotations

import dataclasses
import gzip
import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from enum import IntEnum

import pytest

from pix.event_log.contract import CaseImportError
from pix.ocel.build import build
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.contract import ImportFormat, ImportStatus, OCELImportError
from pix.ocel.model import E2O, Event, EventType, Object, ObjectType
from pix.tabular import (
    AttributeColumn,
    CaseTableMapping,
    ObjectColumn,
    OCELTableMapping,
    import_table,
    mapping_fingerprint,
    read_table,
)

T = "2026-01-01T10:00:00Z"


def case_mapping(**kwargs):
    return CaseTableMapping("case", "activity", **kwargs)


def ocel_mapping(**kwargs):
    return OCELTableMapping(
        "event",
        "activity",
        "time",
        kwargs.pop("objects", (ObjectColumn("order", "Order", "input"),)),
        **kwargs,
    )


def ocel_row(**kwargs):
    return {"event": "e1", "activity": "create", "time": T, "order": "001", **kwargs}


def test_case_csv_preserves_noncontiguous_source_order_and_attributes(tmp_path):
    path = tmp_path / "events.csv"
    path.write_text(
        "case,event,activity,time,owner,lifecycle,resource\n"
        "001,e1,start,2026-01-01T12:00:00Z,A,start,alice\n"
        "002,e2,start,2026-01-01T09:00:00Z,B,complete,bob\n"
        "001,e3,end,2026-01-01T10:00:00Z,A,complete,alice\n",
        encoding="utf-8",
    )
    mapping = case_mapping(
        timestamp="time",
        event_id="event",
        case_attributes=(AttributeColumn("owner", "string"),),
        event_attributes=(
            AttributeColumn("lifecycle", "string", "lifecycle:transition"),
            AttributeColumn("resource", "string", "org:resource"),
        ),
    )
    result = import_table(path, mapping)
    log = result.require_case_log()
    assert [trace.id for trace in log.traces] == ["001", "002"]
    assert [event.id for event in log.traces[0].events] == ["e1", "e3"]
    assert log.traces[0].attribute("owner").value == "A"
    assert log.traces[0].events[0].attribute("org:resource").value == "alice"
    assert log.traces[0].events[0].attribute("lifecycle:transition").value == "start"
    assert result.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.source_size == path.stat().st_size
    assert dict(log.metadata)["table_mapping_sha256"] == mapping.fingerprint
    assert any(
        mapping.fingerprint in change.message for change in result.transformations
    )


def test_timestamp_order_explicit_and_ties_stable():
    rows = [
        {"case": "c", "activity": "A", "time": "2026-01-02T00:00:00Z"},
        {"case": "c", "activity": "B", "time": T},
        {"case": "c", "activity": "C", "time": T},
    ]
    log = read_table(rows, case_mapping(timestamp="time", order="timestamp"))
    assert [event.activity for event in log.traces[0].events] == ["B", "C", "A"]
    assert [event.id for event in log.traces[0].events] == ["row:2", "row:3", "row:1"]
    assert log.source.format == "table-records"


@pytest.mark.parametrize(
    "rows,code",
    [
        (
            [
                {"case": "c", "activity": "A", "owner": "a"},
                {"case": "c", "activity": "B", "owner": "b"},
            ],
            "conflicting_case_attributes",
        ),
        (
            [
                {"case": "c", "activity": "A", "owner": "a"},
                {"case": "c", "activity": "B"},
            ],
            "missing_column",
        ),
    ],
)
def test_case_attribute_conflicts_not_overwritten(rows, code):
    result = import_table(
        rows, case_mapping(case_attributes=(AttributeColumn("owner", "string"),))
    )
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == code
    assert result.candidate is None
    assert result.source_sha256
    with pytest.raises(CaseImportError):
        result.require_case_log()


def test_case_duplicate_mapped_event_id_fails_globally():
    rows = [
        {"case": "a", "activity": "A", "id": "x"},
        {"case": "b", "activity": "A", "id": "x"},
    ]
    result = import_table(rows, case_mapping(event_id="id"))
    assert result.import_issues[0].code == "duplicate_event_id"


def test_case_without_timestamp_is_retained_without_fabricating_time():
    result = import_table([{"case": "c", "activity": "A"}], case_mapping())
    event = result.require_case_log().traces[0].events[0]
    assert event.timestamp is None
    assert event.attribute("identity:id") is None
    assert any(
        change.code == "positional_event_identity" for change in result.transformations
    )


def test_ocel_hand_known_canonical_equivalence_shared_and_repeated_events():
    rows = [ocel_row(), ocel_row(order="002"), ocel_row(event="e2", activity="close")]
    result = import_table(rows, ocel_mapping())
    expected = build(
        event_types=(EventType("create"), EventType("close")),
        object_types=(ObjectType("Order"),),
        events=(
            Event("e1", "create", datetime(2026, 1, 1, 10, tzinfo=timezone.utc)),
            Event("e2", "close", datetime(2026, 1, 1, 10, tzinfo=timezone.utc)),
        ),
        objects=(Object("001", "Order"), Object("002", "Order")),
        e2o=(
            E2O("e1", "001", "input"),
            E2O("e1", "002", "input"),
            E2O("e2", "001", "input"),
        ),
    ).ocel
    assert result.require_ocel() == expected
    assert result.canonical_digest == canonical_digest(expected)
    assert result.format is ImportFormat.TABLE_RECORDS
    assert any(
        change.code == "repeated_event_rows_grouped" and change.count == 1
        for change in result.transformations
    )


@pytest.mark.parametrize(
    "change", [{"activity": "other"}, {"time": "2026-01-01T11:00:00Z"}, {"amount": "2"}]
)
def test_repeated_ocel_event_facts_must_agree(change):
    result = import_table(
        [ocel_row(amount="1"), ocel_row(order="002", amount="1", **change)]
        if "amount" not in change
        else [ocel_row(amount="1"), ocel_row(order="002", **change)],
        ocel_mapping(event_attributes=(AttributeColumn("amount", "integer"),)),
    )
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "conflicting_event"


def test_duplicate_relations_require_explicit_policy():
    rows = [ocel_row(), ocel_row()]
    failed = import_table(rows, ocel_mapping())
    assert failed.import_issues[0].code == "duplicate_e2o"
    with pytest.raises(OCELImportError):
        failed.require_ocel()
    result = import_table(rows, ocel_mapping(duplicate_relations="deduplicate"))
    assert len(result.require_ocel().e2o) == 1
    assert any(
        change.code == "duplicate_e2o_deduplicated" and change.count == 1
        for change in result.transformations
    )


def test_same_relation_with_different_qualifier_preserved():
    mapping = ocel_mapping(
        objects=(
            ObjectColumn("order", "Order", "input"),
            ObjectColumn("order", "Order", "output"),
        )
    )
    assert {
        relation.qualifier for relation in read_table([ocel_row()], mapping).e2o
    } == {"input", "output"}


def test_global_object_type_conflict_is_error():
    mapping = ocel_mapping(
        objects=(ObjectColumn("order", "Order", ""), ObjectColumn("item", "Item", ""))
    )
    result = import_table([ocel_row(item="001")], mapping)
    assert result.import_issues[0].code == "conflicting_object_type"


@pytest.mark.parametrize(
    "encoding,raw,separator",
    [
        ("separator", "001|002", "|"),
        ("json", '["001","002"]', None),
        ("json", ["001", "002"], None),
    ],
)
def test_explicit_object_list_encoding(encoding, raw, separator):
    mapping = ocel_mapping(
        objects=(
            ObjectColumn(
                "order", "Order", "contains", encoding=encoding, separator=separator
            ),
        )
    )
    ocel = read_table([ocel_row(order=raw)], mapping)
    assert {obj.id for obj in ocel.objects} == {"001", "002"}


def test_scalar_object_id_does_not_guess_list_encoding():
    ocel = read_table([ocel_row(order="001|002")], ocel_mapping())
    assert ocel.objects[0].id == "001|002"


@pytest.mark.parametrize(
    "raw", ['["001", null]', '{"x":"001"}', '["001", ""]', "invalid"]
)
def test_malformed_object_lists_fail(raw):
    mapping = ocel_mapping(
        objects=(ObjectColumn("order", "Order", "", encoding="json"),)
    )
    assert not import_table([ocel_row(order=raw)], mapping).valid


def test_static_object_attributes_preserved_and_conflicts_fail():
    mapping = ocel_mapping(
        objects=(
            ObjectColumn(
                "order", "Order", "", attributes=(AttributeColumn("owner", "string"),)
            ),
        )
    )
    result = import_table([ocel_row(owner="alice")], mapping)
    assert result.require_ocel().objects[0].attributes[0].value == "alice"
    assert any(
        change.code == "static_object_attributes" for change in result.transformations
    )
    failed = import_table(
        [ocel_row(owner="alice"), ocel_row(event="e2", owner="bob")], mapping
    )
    assert failed.import_issues[0].code == "conflicting_object_attributes"


def test_typed_primitives_precision_and_empty_string():
    row = {
        "case": "001",
        "activity": "A",
        "integer": "900719925474099312345",
        "float": "1.25",
        "boolean": "false",
        "empty": "",
        "date": "2026-01-01T09:00:00+09:00",
    }
    mapping = case_mapping(
        event_attributes=tuple(
            AttributeColumn(name, kind)
            for name, kind in (
                ("integer", "integer"),
                ("float", "float"),
                ("boolean", "boolean"),
                ("empty", "string"),
                ("date", "time"),
            )
        )
    )
    result = import_table([row], mapping)
    event = result.require_case_log().traces[0].events[0]
    assert event.attribute("integer").value == 900719925474099312345
    assert event.attribute("float").value == 1.25
    assert event.attribute("boolean").value is False
    assert event.attribute("empty").value == ""
    assert event.attribute("date").value == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert event.attribute("integer").lexical == "900719925474099312345"


def test_null_and_missing_are_separate_explicit_policies():
    mapping = case_mapping(
        event_attributes=(
            AttributeColumn(
                "value",
                "string",
                missing="omit",
                null="preserve",
                null_values=("NULL",),
            ),
        )
    )
    log = read_table(
        [
            {"case": "c", "activity": "A"},
            {"case": "c", "activity": "B", "value": None},
            {"case": "c", "activity": "C", "value": "NULL"},
        ],
        mapping,
    )
    assert log.traces[0].events[0].attribute("value") is None
    assert log.traces[0].events[1].attribute("value").type == "null"
    assert log.traces[0].events[2].attribute("value").lexical == "NULL"


def test_ocel_null_requires_omit_and_default_does_not_hide_it():
    rows = [ocel_row(amount=None)]
    assert (
        import_table(
            rows, ocel_mapping(event_attributes=(AttributeColumn("amount", "integer"),))
        )
        .import_issues[0]
        .code
        == "null_attribute"
    )
    assert (
        not read_table(
            rows,
            ocel_mapping(
                event_attributes=(AttributeColumn("amount", "integer", null="omit"),)
            ),
        )
        .events[0]
        .attributes
    )
    with pytest.raises(ValueError, match="null"):
        ocel_mapping(
            event_attributes=(AttributeColumn("amount", "integer", null="preserve"),)
        )


@pytest.mark.parametrize(
    "raw,code",
    [
        ("2026-01-01T00:00:00.123456789Z", "timestamp_precision_loss"),
        ("2026-01-01T00:00:00", "timezone_required"),
        ("yesterday", "invalid_timestamp"),
    ],
)
def test_no_timestamp_precision_or_timezone_guessing(raw, code):
    result = import_table([ocel_row(time=raw)], ocel_mapping())
    assert result.import_issues[0].code == code


def test_explicit_naive_timezone_assumption_disclosed():
    result = import_table(
        [ocel_row(time=datetime(2026, 1, 1))],
        ocel_mapping(timestamp_policy="assume_utc"),
    )
    assert result.require_ocel().events[0].time.tzinfo is timezone.utc
    assert result.ocel.timezone_info.assumed_utc_count == 1
    assert any(
        change.code == "timezone_assumed_utc" for change in result.transformations
    )


@pytest.mark.parametrize("raw", [1, 1.0, Decimal("1")])
def test_numeric_identifiers_require_policy(raw):
    assert (
        import_table([{"case": raw, "activity": "A"}], case_mapping())
        .import_issues[0]
        .code
        == "invalid_identifier"
    )
    result = import_table(
        [{"case": raw, "activity": "A"}], case_mapping(id_policy="integer")
    )
    assert result.require_case_log().traces[0].id == "1"
    assert any(change.code == "integer_identifier" for change in result.transformations)


def test_gzip_csv_raw_provenance_and_leading_zeros(tmp_path):
    path = tmp_path / "source.csv.gz"
    raw = gzip.compress(b"case,activity\n0001,A\n")
    path.write_bytes(raw)
    result = import_table(path, case_mapping())
    assert result.require_case_log().traces[0].id == "0001"
    assert result.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.source_size == len(raw)


def test_excel_actual_numeric_and_timezone_mapping(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["case", "activity", "time"])
    sheet.append([1, "A", datetime(2026, 1, 1)])
    path = tmp_path / "source.xlsx"
    workbook.save(path)
    assert (
        import_table(path, case_mapping(timestamp="time")).import_issues[0].code
        == "invalid_identifier"
    )
    result = import_table(
        path,
        case_mapping(
            timestamp="time", id_policy="integer", timestamp_policy="assume_utc"
        ),
    )
    assert result.require_case_log().traces[0].events[0].timestamp == datetime(
        2026, 1, 1, tzinfo=timezone.utc
    )


def test_mapping_frozen_validation_and_semantic_fingerprint():
    mapping = case_mapping()
    with pytest.raises(dataclasses.FrozenInstanceError):
        mapping.activity = "other"
    assert mapping.fingerprint == mapping_fingerprint(case_mapping())
    assert mapping.fingerprint != case_mapping(id_policy="integer").fingerprint
    assert AttributeColumn("x", "int") == AttributeColumn("x", "integer")
    with pytest.raises(TypeError):
        case_mapping(event_attributes=[AttributeColumn("x", "string")])
    with pytest.raises(ValueError):
        case_mapping(order="timestamp")
    with pytest.raises(ValueError):
        ObjectColumn("x", "X", "", encoding="separator")
    with pytest.raises(ValueError):
        case_mapping(event_attributes=(AttributeColumn("x", "string", "concept:name"),))


def test_missing_mapping_never_inferred():
    with pytest.raises(TypeError, match="mapping"):
        import_table([{"case": "c", "activity": "A"}], None)


def test_empty_records_and_unmapped_columns_disclosure():
    assert not read_table([], case_mapping()).traces
    assert not read_table([], ocel_mapping()).events
    result = import_table(
        [{"case": "c", "activity": "A", "secret": "unselected"}], case_mapping()
    )
    assert any(
        change.code == "unmapped_columns" and "secret" in change.message
        for change in result.transformations
    )


@pytest.mark.parametrize(
    "value,kind",
    [
        (True, "integer"),
        ("1", "boolean"),
        ("1.0", "integer"),
        ("inf", "float"),
        (123, "string"),
    ],
)
def test_declared_types_reject_semantic_coercion(value, kind):
    result = import_table(
        [{"case": "c", "activity": "A", "value": value}],
        case_mapping(event_attributes=(AttributeColumn("value", kind),)),
    )
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "invalid_attribute_value"


@pytest.mark.parametrize(
    "raw,expected",
    [("[9007199254740993.0]", "9007199254740993"), ("[1.0000000000000001]", None)],
)
def test_json_numeric_ids_never_round_before_integrality_check(raw, expected):
    mapping = ocel_mapping(
        objects=(
            ObjectColumn("order", "Order", "", encoding="json", id_policy="integer"),
        )
    )
    result = import_table([ocel_row(order=raw)], mapping)
    if expected is None:
        assert result.import_issues[0].code == "invalid_identifier"
    else:
        assert result.require_ocel().objects[0].id == expected


@pytest.mark.parametrize("offset", ["+00:99", "-01:60", "+24:00"])
def test_invalid_timezone_offset_is_not_silently_normalized(offset):
    result = import_table(
        [ocel_row(time=f"2026-01-01T10:00:00{offset}")], ocel_mapping()
    )
    assert result.import_issues[0].code == "invalid_timestamp"


def test_integer_representation_limit_returns_evidence(tmp_path):
    import sys

    limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
    if not limit:
        pytest.skip("Interpreter does not enforce an integer representation limit")
    path = tmp_path / "large.csv"
    path.write_text(
        "case,activity,value\nc,A," + "1" * (limit + 1) + "\n", encoding="utf-8"
    )
    result = import_table(
        path, case_mapping(event_attributes=(AttributeColumn("value", "integer"),))
    )
    assert result.import_issues[0].code == "integer_representation_limit"
    assert result.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    result = import_table(
        [{"case": Decimal(f"1e{limit}"), "activity": "A"}],
        case_mapping(id_policy="integer"),
    )
    assert result.import_issues[0].code == "integer_representation_limit"


def test_scalar_subclasses_normalized_and_datetime_subclasses_rejected():
    class Label(str):
        pass

    class Count(IntEnum):
        ONE = 1

    class PreciseDatetime(datetime):
        pass

    mapping = case_mapping(
        event_attributes=(
            AttributeColumn("count", "integer"),
            AttributeColumn("label", "string"),
        )
    )
    log = read_table(
        [
            {
                "case": Label("001"),
                "activity": Label("A"),
                "count": Count.ONE,
                "label": Label("plain"),
            }
        ],
        mapping,
    )
    event = log.traces[0].events[0]
    assert type(event.activity) is str
    assert type(event.attribute("count").value) is int
    assert type(event.attribute("label").value) is str
    result = import_table(
        [
            {
                "case": "001",
                "activity": "A",
                "time": PreciseDatetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ],
        case_mapping(timestamp="time"),
    )
    assert result.import_issues[0].code == "unsupported_datetime_type"


def test_explicit_table_format_honored_over_suffix(tmp_path):
    path = tmp_path / "events.data"
    path.write_text("case,activity\n001,A\n", encoding="utf-8")
    assert read_table(path, case_mapping(), format="csv").traces[0].id == "001"
    assert read_table(path, case_mapping(), format="table-csv").traces[0].id == "001"
    assert not import_table(path, case_mapping(), format="xlsx").valid
    assert not import_table(
        [{"case": "001", "activity": "A"}], case_mapping(), format="csv"
    ).valid
