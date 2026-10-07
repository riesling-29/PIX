"""Compact CSV conformance/profile and source-preservation regressions."""

import csv
import gzip
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.contract import ImportStage, ImportStatus
from pix.ocel.ingest.formats.common import AdapterFailure, ValueEncoding, map_document
from pix.ocel.ingest.formats.compact import COMPACT_PROFILE, load
from pix.ocel.model import OCEL_EPOCH, ValueType

STAMP = "2026-09-09T10:00:00Z"
LATER = "2026-09-10T10:00:00Z"
LAST = "2026-09-11T10:00:00Z"
HEADER = ["id", "activity", "timestamp", "ot:Order"]


def _csv(header: list[str], rows: list[list[str]]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def _write(
    tmp_path: Path, rows: list[list[str]], header: list[str] | None = None
) -> Path:
    path = tmp_path / "sample.ocel.csv"
    path.write_bytes(_csv(HEADER if header is None else header, rows))
    return path


def _fail(path: Path, stage: ImportStage, code: str) -> AdapterFailure:
    with pytest.raises(AdapterFailure) as failure:
        load(path)
    assert failure.value.stage is stage
    assert failure.value.code == code
    return failure.value


def test_all_row_kinds_equal_ocel20_document_and_digest(tmp_path: Path) -> None:
    label = "http://host/a/{b}#c"
    note = 'hello,\n"world"'
    path = _write(
        tmp_path,
        [
            ["", "", "", 'o1{"state":"new"}', "i0", "", ""],
            [
                "e1",
                "create",
                STAMP,
                "o1#ordered/o1#audited",
                "i1#item" + json.dumps({"price": 10.5, "label": label}),
                "10.5",
                note,
            ],
            ["o1", "O2O", LATER, "", 'i1#contains{"price":11.5}', "", ""],
            ["", "", LAST, 'o1{"state":"done"}', "", "", ""],
            ["e2", "finish", LAST, "", "", "", ""],
        ],
        ["id", "activity", "timestamp", "ot:Order", "ot:Item", "total", "note"],
    )
    expected = {
        "eventTypes": [
            {
                "name": "create",
                "attributes": [
                    {"name": "total", "type": "float"},
                    {"name": "note", "type": "string"},
                ],
            },
            {"name": "finish", "attributes": []},
        ],
        "objectTypes": [
            {"name": "Order", "attributes": [{"name": "state", "type": "string"}]},
            {
                "name": "Item",
                "attributes": [
                    {"name": "price", "type": "float"},
                    {"name": "label", "type": "string"},
                ],
            },
        ],
        "events": [
            {
                "id": "e1",
                "type": "create",
                "time": STAMP,
                "attributes": [
                    {"name": "total", "value": 10.5},
                    {"name": "note", "value": note},
                ],
                "relationships": [
                    {"objectId": "o1", "qualifier": "ordered"},
                    {"objectId": "o1", "qualifier": "audited"},
                    {"objectId": "i1", "qualifier": "item"},
                ],
            },
            {"id": "e2", "type": "finish", "time": LAST},
        ],
        "objects": [
            {
                "id": "o1",
                "type": "Order",
                "attributes": [
                    {"name": "state", "value": "new", "time": OCEL_EPOCH.isoformat()},
                    {"name": "state", "value": "done", "time": LAST},
                ],
                "relationships": [{"objectId": "i1", "qualifier": "contains"}],
            },
            {"id": "i0", "type": "Item"},
            {
                "id": "i1",
                "type": "Item",
                "attributes": [
                    {"name": "price", "value": 10.5, "time": STAMP},
                    {"name": "price", "value": 11.5, "time": LATER},
                    {"name": "label", "value": label, "time": STAMP},
                ],
            },
        ],
    }
    actual, transformations = load(path)
    equivalent, _ = map_document(expected, encoding=ValueEncoding.JSON)

    assert actual.valid and equivalent.valid
    assert actual.candidate == equivalent.candidate
    assert canonical_digest(actual.candidate) == canonical_digest(equivalent.candidate)
    assert actual.candidate.info().disconnected_event_count == 1
    assert actual.candidate.info().objects_without_e2o_count == 1
    assert any(COMPACT_PROFILE in item.message for item in transformations)
    assert any(
        item.code == "compact_object_attribute_bases" for item in transformations
    )


@pytest.mark.parametrize(
    ("values", "kind", "expected"),
    [
        (["1", "2"], ValueType.INTEGER, [1, 2]),
        (["1", "2.5"], ValueType.FLOAT, [1.0, 2.5]),
        (["true", "FALSE"], ValueType.BOOLEAN, [True, False]),
        (
            [STAMP, LATER],
            ValueType.TIME,
            [
                datetime(2026, 9, 9, 10, tzinfo=timezone.utc),
                datetime(2026, 9, 10, 10, tzinfo=timezone.utc),
            ],
        ),
        (["9", "word"], ValueType.STRING, ["9", "word"]),
        (["007", "+5"], ValueType.STRING, ["007", "+5"]),
        (["1.50", "1e3"], ValueType.STRING, ["1.50", "1e3"]),
        (["9223372036854775808", "2"], ValueType.STRING, ["9223372036854775808", "2"]),
        (["9007199254740993", "1.5"], ValueType.STRING, ["9007199254740993", "1.5"]),
        (["1e+20", "2.5"], ValueType.FLOAT, [1e20, 2.5]),
    ],
)
def test_event_inference_uses_whole_column_across_types(
    tmp_path: Path,
    values: list[str],
    kind: ValueType,
    expected: list[object],
) -> None:
    path = _write(
        tmp_path,
        [
            ["e1", "A", STAMP, "", values[0]],
            ["e2", "B", LATER, "", values[1]],
        ],
        HEADER + ["value"],
    )
    result, _ = load(path)

    assert result.valid
    assert [item.attributes[0].type for item in result.candidate.event_types] == [
        kind,
        kind,
    ]
    assert [item.attributes[0].value for item in result.candidate.events] == expected


def test_object_scopes_and_native_json_primitive_identity(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            [
                "",
                "",
                "",
                'o{"a":true,"b":1.0,"empty":"","big":9223372036854775808}',
                'p{"a":42,"b":"007"}',
            ]
        ],
        HEADER + ["ot:Other"],
    )
    result, _ = load(path)
    schemas = {
        item.name: {a.name: a.type for a in item.attributes}
        for item in result.candidate.object_types
    }
    assert schemas["Order"] == {
        "a": ValueType.BOOLEAN,
        "b": ValueType.FLOAT,
        "empty": ValueType.STRING,
        "big": ValueType.INTEGER,
    }
    assert schemas["Other"] == {"a": ValueType.INTEGER, "b": ValueType.STRING}
    assert {a.name: a.value for a in result.candidate.get_object("o").attributes}[
        "empty"
    ] == ""


def test_empty_cells_do_not_invent_values_or_schemas(tmp_path: Path) -> None:
    path = _write(tmp_path, [["e", "A", STAMP, "", ""]], HEADER + ["unused"])
    result, _ = load(path)
    assert result.candidate.event_types[0].attributes == ()
    assert result.candidate.events[0].attributes == ()
    assert result.candidate.object_types[0].name == "Order"


def test_empty_log_retains_object_types_from_header(tmp_path: Path) -> None:
    result, _ = load(_write(tmp_path, []))
    assert result.candidate.object_types[0].name == "Order"


def test_attribute_rows_can_declare_objects_without_assignments(tmp_path: Path) -> None:
    result, _ = load(_write(tmp_path, [["", "", STAMP, ""], ["", "", STAMP, "o/p{}"]]))
    assert result.valid
    assert [obj.id for obj in result.candidate.objects] == ["o", "p"]
    assert all(obj.attributes == () for obj in result.candidate.objects)
    assert result.candidate.e2o == result.candidate.o2o == ()


def test_timed_history_retains_first_time_and_original_order_is_irrelevant(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        [
            ["", "", LATER, 'o{"a":2}'],
            ["", "", "1969-01-01T00:00:00Z", 'o{"a":1}'],
        ],
    )
    result, _ = load(path)
    attrs = result.candidate.get_object("o").attributes
    assert [a.value for a in attrs] == [1, 2]
    assert attrs[0].time == datetime(1969, 1, 1, tzinfo=timezone.utc)


def test_backslash_reference_escapes_and_json_delimiters(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        [
            [
                "e",
                "A",
                STAMP,
                r"a\/b\#c\{d\\e#q\/\#\{\\"
                + json.dumps({"url": "a/b#c{d}", "quote": 'a"/b'}),
            ]
        ],
    )
    result, _ = load(path)
    obj = result.candidate.get_object("a/b#c{d\\e")
    assert result.candidate.e2o[0].qualifier == "q/#{\\"
    assert {a.name: a.value for a in obj.attributes} == {
        "url": "a/b#c{d}",
        "quote": 'a"/b',
    }


def test_bracketed_reference_is_one_literal_id_without_list_evaluation(
    tmp_path: Path,
) -> None:
    literal = "['o1', 'o2']"
    result, _ = load(_write(tmp_path, [["e", "A", STAMP, literal]]))
    assert [obj.id for obj in result.candidate.objects] == [literal]
    assert len(result.candidate.e2o) == 1


def test_gzip_truncation_is_a_structured_syntax_failure(tmp_path: Path) -> None:
    path = tmp_path / "sample.ocel.csv.gz"
    path.write_bytes(gzip.compress(_csv(HEADER, [["e", "A", STAMP, "o"]]))[:-6])
    _fail(path, ImportStage.SYNTAX, "unreadable_compact_csv")


def test_pre4_whitespace_rules_are_disclosed_without_trimming_attributes(
    tmp_path: Path,
) -> None:
    path = _write(
        tmp_path,
        [[" e ", " A ", f" {STAMP} ", ' o # q {" key ":" value "}', " text "]],
        ["id", "activity", "timestamp", "ot: Order ", "note"],
    )
    result, transformations = load(path)
    assert result.candidate.events[0].id == "e"
    assert result.candidate.events[0].type == "A"
    assert result.candidate.events[0].attributes[0].value == " text "
    assert result.candidate.objects[0].type == " Order "
    assert result.candidate.objects[0].attributes[0].name == " key "
    assert result.candidate.objects[0].attributes[0].value == " value "
    assert result.candidate.e2o[0].qualifier == "q"
    assert (
        next(
            t for t in transformations if t.code == "compact_control_fields_stripped"
        ).count
        == 5
    )


@pytest.mark.parametrize(
    "source_row",
    [
        ["o", "o2o", "", "p"],
        ["o", "o2o", "", "o/p"],
    ],
)
def test_o2o_source_requires_earlier_row_reference(
    tmp_path: Path, source_row: list[str]
) -> None:
    _fail(
        _write(tmp_path, [source_row, ["", "", "", "o"]]),
        ImportStage.MAPPING,
        "unknown_compact_o2o_source",
    )


def test_conflicting_object_types_fail(tmp_path: Path) -> None:
    _fail(
        _write(tmp_path, [["", "", "", "o", "o"]], HEADER + ["ot:Other"]),
        ImportStage.MAPPING,
        "conflicting_compact_object_type",
    )


@pytest.mark.parametrize(
    "rows",
    [
        [["", "", STAMP, 'o{"a":1}'], ["", "", STAMP, 'o{"a":2}']],
        [["", "", "", 'o{"a":1}'], ["", "", "", 'o{"a":1}']],
        [
            ["", "", STAMP, 'o{"a":1}'],
            ["", "", "2026-09-09T19:00:00+09:00", 'o{"a":1}'],
        ],
        [["", "", "", 'o{"a":1}'], ["", "", "1970-01-01T00:00:00Z", 'o{"a":2}']],
    ],
)
def test_tied_assignments_fail_without_overwrite(
    tmp_path: Path, rows: list[list[str]]
) -> None:
    _fail(
        _write(tmp_path, rows), ImportStage.MAPPING, "tied_compact_attribute_assignment"
    )


def test_duplicate_event_rows_and_relationships_survive_to_semantic_validation(
    tmp_path: Path,
) -> None:
    path = _write(tmp_path, [["e", "A", STAMP, "o#x/o#x"], ["e", "A", STAMP, ""]])
    result, _ = load(path)
    assert not result.valid
    assert len(result.candidate.events) == 2
    assert len(result.candidate.e2o) == 2
    assert {issue.code for issue in result.report.issues} >= {
        "duplicate_event_id",
        "duplicate_e2o",
    }


def test_duplicate_o2o_relationships_are_not_dropped(tmp_path: Path) -> None:
    path = _write(tmp_path, [["", "", "", "o/p"], ["o", "o2o", "", "p#x/p#x"]])
    result, _ = load(path)
    assert len(result.candidate.o2o) == 2
    assert "duplicate_o2o" in {issue.code for issue in result.report.issues}


@pytest.mark.parametrize(
    ("cell", "stage", "code"),
    [
        ('o{"x":null}', ImportStage.MAPPING, "unsupported_compact_null"),
        ('o{"x":[]}', ImportStage.SCHEMA, "nonprimitive_compact_attribute"),
        ('o{"x":{}}', ImportStage.SCHEMA, "nonprimitive_compact_attribute"),
        ('o{"x":1,"x":1}', ImportStage.SCHEMA, "duplicate_compact_json_member"),
        ('o{"x":NaN}', ImportStage.SYNTAX, "nonfinite_compact_json_number"),
        ('o{"x":1e9999}', ImportStage.MAPPING, "nonfinite_compact_attribute"),
        ('o{"x":1', ImportStage.SYNTAX, "invalid_compact_json"),
        ("o/", ImportStage.SCHEMA, "invalid_compact_object_reference"),
        ("/o", ImportStage.SCHEMA, "invalid_compact_object_reference"),
        ("o//p", ImportStage.SCHEMA, "invalid_compact_object_reference"),
        ("o#q#r", ImportStage.SCHEMA, "invalid_compact_object_reference"),
        ("o{}tail", ImportStage.SCHEMA, "invalid_compact_object_reference"),
        ("o\\", ImportStage.SCHEMA, "invalid_compact_reference_escape"),
        (r"o\n", ImportStage.SCHEMA, "invalid_compact_reference_escape"),
    ],
)
def test_reference_failures_have_structured_stages(
    tmp_path: Path,
    cell: str,
    stage: ImportStage,
    code: str,
) -> None:
    failure = _fail(_write(tmp_path, [["e", "A", STAMP, cell]]), stage, code)
    assert failure.at[:2] == ("rows", "2")


@pytest.mark.parametrize(
    ("rows", "stage", "code"),
    [
        ([["e", "", STAMP, "o"]], ImportStage.SCHEMA, "invalid_compact_row_kind"),
        ([["e", "A", "", "o"]], ImportStage.SCHEMA, "invalid_compact_row_kind"),
        (
            [["", "", "", "o#q"]],
            ImportStage.SCHEMA,
            "compact_qualifier_without_relation",
        ),
        (
            [["", "", STAMP, 'o#q{"x":1}']],
            ImportStage.MAPPING,
            "compact_qualifier_without_relation",
        ),
        (
            [["", "", "", "o"], ["o", "o2o", "", 'p{"x":1}']],
            ImportStage.SCHEMA,
            "missing_compact_attribute_time",
        ),
    ],
)
def test_invalid_row_kinds_and_unpreservable_fields(
    tmp_path: Path,
    rows: list[list[str]],
    stage: ImportStage,
    code: str,
) -> None:
    _fail(_write(tmp_path, rows), stage, code)


def test_non_event_attribute_cells_are_not_silently_ignored(tmp_path: Path) -> None:
    _fail(
        _write(tmp_path, [["", "", "", "o", "not an event"]], HEADER + ["note"]),
        ImportStage.SCHEMA,
        "compact_attributes_without_event",
    )


@pytest.mark.parametrize(
    ("payload", "stage", "code"),
    [
        (b"", ImportStage.SCHEMA, "missing_compact_header"),
        (
            b"id,activity,timestamp,id\r\n",
            ImportStage.SCHEMA,
            "duplicate_compact_header",
        ),
        (b"activity,id,timestamp\r\n", ImportStage.SCHEMA, "invalid_compact_header"),
        (b"id,activity,timestamp,ot:\r\n", ImportStage.SCHEMA, "blank_compact_header"),
        (b"id,activity,timestamp\r\ne,A\r\n", ImportStage.SCHEMA, "compact_row_width"),
        (
            b'id,activity,timestamp\r\ne"x,A,t\r\n',
            ImportStage.SYNTAX,
            "invalid_compact_csv",
        ),
        (
            b'id,activity,timestamp\r\n"e"tail,A,t\r\n',
            ImportStage.SYNTAX,
            "invalid_compact_csv",
        ),
        (
            b'id,activity,timestamp\r\n"e,A,t\r\n',
            ImportStage.SYNTAX,
            "invalid_compact_csv",
        ),
        (b"id,activity,timestamp\r\ne,\xff,t\r\n", ImportStage.SYNTAX, "invalid_utf8"),
        (b"id,activity,timestamp\re,A,t\r", ImportStage.SYNTAX, "invalid_compact_csv"),
    ],
)
def test_csv_and_header_failures(
    tmp_path: Path, payload: bytes, stage: ImportStage, code: str
) -> None:
    path = tmp_path / "bad.ocel.csv"
    path.write_bytes(payload)
    _fail(path, stage, code)


@pytest.mark.parametrize(
    "time", ["2026-09-09T10:00:00.0000001Z", "2026-09-09T10:00:00.1234567Z"]
)
def test_submicrosecond_timestamps_fail(tmp_path: Path, time: str) -> None:
    _fail(
        _write(tmp_path, [["e", "A", time, ""]]),
        ImportStage.MAPPING,
        "timestamp_precision_loss",
    )


@pytest.mark.parametrize(
    "time", ["2026-09-09T10:30.5Z", "20260909T1030.5Z", "2026-09-09T10.5Z"]
)
def test_fractional_minutes_hours_are_rejected_without_changing_the_time(
    tmp_path: Path, time: str
) -> None:
    _fail(
        _write(tmp_path, [["e", "A", time, ""]]),
        ImportStage.MAPPING,
        "invalid_compact_timestamp",
    )


def test_inferred_timestamp_attribute_precision_is_not_silently_truncated(
    tmp_path: Path,
) -> None:
    _fail(
        _write(tmp_path, [["", "", "", 'o{"a":"2026-09-09T10:00:00.0000001Z"}']]),
        ImportStage.MAPPING,
        "timestamp_precision_loss",
    )


def test_timezone_required_and_exact_extra_zero_precision_supported(
    tmp_path: Path,
) -> None:
    _fail(
        _write(tmp_path, [["e", "A", "2026-09-09T10:00:00", ""]]),
        ImportStage.MAPPING,
        "invalid_compact_timestamp",
    )
    path = _write(
        tmp_path, [["e", "A", "2026-09-09T19:00:00.1234560+09:00", 'o{"x":1}']]
    )
    result, transformations = load(path)
    assert result.candidate.events[0].time.microsecond == 123456
    assert (
        result.candidate.objects[0].attributes[0].time
        == result.candidate.events[0].time
    )
    assert next(t for t in transformations if t.code == "timezone_to_utc").count == 2


def test_unicode_and_gzip_are_equivalent(tmp_path: Path) -> None:
    path = _write(tmp_path, [["사건", "처리", STAMP, '물건#대상{"설명":"서울/부산"}']])
    compressed = tmp_path / "sample.ocel.csv.gz"
    compressed.write_bytes(gzip.compress(path.read_bytes()))
    plain, _ = load(path)
    zipped, _ = load(compressed)
    assert plain.candidate == zipped.candidate
    compressed.write_bytes(b"not gzip")
    failure = _fail(compressed, ImportStage.SYNTAX, "unreadable_compact_csv")
    assert failure.status is ImportStatus.SYNTAX_INVALID
