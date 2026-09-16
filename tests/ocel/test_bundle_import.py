"""Typed bundle imports preserve meaning and reject ambiguous/unreadable sources."""

from __future__ import annotations

import builtins
import csv
import hashlib
import io
import json
import os
import stat
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.contract import ImportStatus
from pix.ocel.ingest.formats import _bundle_source, bundled
from pix.ocel.ingest.formats.common import AdapterFailure, ValueEncoding, map_document
from pix.ocel.model import OCEL_EPOCH


def _metadata(storage: str = "csv") -> dict:
    return {
        "ocelVersion": "2.0",
        "bundleFormatVersion": "1.0",
        "storageFormat": storage,
        "eventTypes": {
            " create / 주문 ": {
                "file": f"arbitrary/events.{storage}",
                "attributes": [
                    {"name": name, "type": kind}
                    for name, kind in (
                        ("amount", "float"),
                        ("count", "integer"),
                        ("flag", "boolean"),
                        ("checked", "time"),
                        ("memo", "string"),
                    )
                ],
            }
        },
        "objectTypes": {
            "order": {
                "file": f"elsewhere/items.{storage}",
                "changesFile": f"history.{storage}",
                "attributes": [
                    {"name": "status", "type": "string"},
                    {"name": "qty", "type": "integer"},
                ],
            }
        },
        "relations": {"e2o": f"e2o.{storage}", "o2o": f"o2o.{storage}"},
    }


def _files() -> dict[str, bytes]:
    return {
        "ocel-meta.json": json.dumps(_metadata(), ensure_ascii=False).encode(),
        "arbitrary/events.csv": (
            "memo,ocel_id,ocel_time,amount,count,flag,checked\r\n"
            '"  comma, and ""quote""\nkept  ",e1,2026-01-01T10:00:00+09:00,1.25,-2,true,2026-01-01T01:00:00Z\r\n'
            ",orphan-event,2026-01-01T02:00:00Z,,,,\r\n"
        ).encode(),
        "elsewhere/items.csv": b"ocel_id,status,qty\no1,new,1\no2,linked,2\norphan,,\n",
        "history.csv": b"ocel_id,ocel_time,ocel_changed_field,status,qty\no1,2026-01-02T00:00:00Z,status,done,\n",
        "e2o.csv": b"ocel_event_id,ocel_object_id,ocel_qualifier\ne1,o1,used\ne1,o1,audit\n",
        "o2o.csv": b"ocel_source_id,ocel_target_id,ocel_qualifier\no1,o2,parent\n",
    }


def _write(tmp_path: Path, files: dict[str, bytes], *, archive: bool = False) -> Path:
    if archive:
        path = tmp_path / "sample.ocel.zip"
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as output:
            for name, data in files.items():
                info = zipfile.ZipInfo(name)
                # ZipInfo normalizes backslashes on Windows; test actual raw names.
                info.filename = name
                output.writestr(info, data)
    else:
        path = tmp_path / "bundle"
        path.mkdir()
        for name, data in files.items():
            target = path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return path


def _failure(path: Path, code: str) -> AdapterFailure:
    with pytest.raises(AdapterFailure) as caught:
        bundled.load(path)
    assert caught.value.code == code
    return caught.value


def _expected():
    types = _metadata()
    document = {
        "eventTypes": [
            {"name": key, "attributes": value["attributes"]}
            for key, value in types["eventTypes"].items()
        ],
        "objectTypes": [
            {"name": key, "attributes": value["attributes"]}
            for key, value in types["objectTypes"].items()
        ],
        "events": [
            {
                "id": "e1",
                "type": " create / 주문 ",
                "time": "2026-01-01T01:00:00Z",
                "attributes": [
                    {"name": "memo", "value": '  comma, and "quote"\nkept  '},
                    {"name": "amount", "value": 1.25},
                    {"name": "count", "value": -2},
                    {"name": "flag", "value": True},
                    {"name": "checked", "value": "2026-01-01T01:00:00Z"},
                ],
                "relationships": [
                    {"objectId": "o1", "qualifier": "used"},
                    {"objectId": "o1", "qualifier": "audit"},
                ],
            },
            {
                "id": "orphan-event",
                "type": " create / 주문 ",
                "time": "2026-01-01T02:00:00Z",
            },
        ],
        "objects": [
            {
                "id": "o1",
                "type": "order",
                "attributes": [
                    {"name": "status", "value": "new", "time": "1970-01-01T00:00:00Z"},
                    {"name": "qty", "value": 1, "time": "1970-01-01T00:00:00Z"},
                    {"name": "status", "value": "done", "time": "2026-01-02T00:00:00Z"},
                ],
                "relationships": [{"objectId": "o2", "qualifier": "parent"}],
            },
            {
                "id": "o2",
                "type": "order",
                "attributes": [
                    {
                        "name": "status",
                        "value": "linked",
                        "time": "1970-01-01T00:00:00Z",
                    },
                    {"name": "qty", "value": 2, "time": "1970-01-01T00:00:00Z"},
                ],
            },
            {"id": "orphan", "type": "order"},
        ],
    }
    return map_document(document, encoding=ValueEncoding.JSON)[0].candidate


@pytest.mark.parametrize("archive", [False, True])
def test_csv_preserves_types_history_whitespace_relations_and_orphans(
    tmp_path, archive
):
    result, changes = bundled.load(_write(tmp_path, _files(), archive=archive))
    assert result.valid
    assert result.candidate == _expected()
    assert len(result.candidate.e2o) == 2
    assert result.candidate.objects[0].attributes[0].time == OCEL_EPOCH
    assert {item.code for item in changes} == {
        "bundle_specification_profile",
        "timezone_to_utc",
        "bundle_csv_empty_attributes_missing",
    }


def test_zip_directory_equivalence_and_manifest_definition(tmp_path):
    files = _files()
    directory = _write(tmp_path, files)
    archive = _write(tmp_path, files, archive=True)
    assert canonical_digest(bundled.load(directory)[0].candidate) == canonical_digest(
        bundled.load(archive)[0].candidate
    )
    digest, size, magic = bundled.source_evidence(directory)
    expected = hashlib.sha256(b"PIX-OCEL-BUNDLE-MANIFEST-v1\0")
    for name in sorted(files):
        encoded = name.encode()
        expected.update(len(encoded).to_bytes(8, "big") + encoded)
        expected.update(len(files[name]).to_bytes(8, "big") + files[name])
    assert digest == expected.hexdigest()
    assert size == sum(map(len, files.values()))
    assert magic == b"OCEL-BUNDLE\0"
    for path in directory.rglob("*"):
        os.utime(path, (1_000_000, 1_000_000))
    (directory / "empty-directory").mkdir()
    assert bundled.source_evidence(directory) == (digest, size, magic)
    (directory / "e2o.csv").write_bytes(files["e2o.csv"] + b"\n")
    assert bundled.source_evidence(directory)[0] != digest


def test_safe_unlisted_file_is_disclosed_and_part_of_directory_evidence(tmp_path):
    files = _files()
    directory = _write(tmp_path, files)
    before = bundled.source_evidence(directory)
    (directory / "README.txt").write_bytes(b"documentation")
    result, changes = bundled.load(directory)
    assert result.valid
    ignored = next(
        item for item in changes if item.code == "bundle_unlisted_entries_ignored"
    )
    assert ignored.at == ("README.txt",) and ignored.count == 1
    assert bundled.source_evidence(directory) != before


@pytest.mark.parametrize(
    "name",
    [
        "../escape.csv",
        "/root.csv",
        "C:/drive.csv",
        "C:drive.csv",
        "a\\b.csv",
        "a/../b.csv",
        "a//b.csv",
        "./b.csv",
    ],
)
def test_unsafe_declared_paths_rejected(tmp_path, name):
    files = _files()
    meta = _metadata()
    meta["relations"]["e2o"] = name
    files["ocel-meta.json"] = json.dumps(meta).encode()
    _failure(_write(tmp_path, files, archive=True), "unsafe_bundle_path")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "C:/absolute", "a\\b"])
def test_unsafe_unlisted_archive_members_rejected(tmp_path, name):
    files = _files()
    files[name] = b"unlisted"
    _failure(_write(tmp_path, files, archive=True), "unsafe_bundle_path")


def test_duplicate_and_symlink_archive_entries(tmp_path):
    archive = _write(tmp_path, _files(), archive=True)
    with pytest.warns(UserWarning), zipfile.ZipFile(archive, "a") as output:
        output.writestr("e2o.csv", b"duplicate")
    _failure(archive, "duplicate_bundle_member")
    archive = _write(tmp_path, _files(), archive=True)
    link = zipfile.ZipInfo("link")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "a") as output:
        output.writestr(link, "outside")
    _failure(archive, "bundle_symlink_forbidden")


def test_directory_symlink_not_followed(tmp_path):
    directory = _write(tmp_path, _files())
    try:
        (directory / "link").symlink_to(tmp_path)
    except OSError:
        pytest.skip("OS does not grant symlink creation")
    _failure(directory, "bundle_symlink_forbidden")
    with pytest.raises(AdapterFailure, match="symlinks"):
        bundled.source_evidence(directory)


def test_truncated_archive_and_size_policy(tmp_path, monkeypatch):
    archive = _write(tmp_path, _files(), archive=True)
    data = archive.read_bytes()
    archive.write_bytes(data[:-30])
    _failure(archive, "unreadable_bundle")
    directory = _write(tmp_path, _files())
    monkeypatch.setattr(_bundle_source, "MAX_BUNDLE_BYTES", 50)
    _failure(directory, "bundle_resource_limit")


@pytest.mark.parametrize(
    "replacement,code",
    [
        (b"ocel_id,status,status\no1,new,1\n", "duplicate_bundle_column"),
        (b"ocel_id,status,qty,extra\no1,new,1,x\n", "invalid_bundle_columns"),
        (b"ocel_id,status\no1,new\n", "invalid_bundle_columns"),
        (b"ocel_id,status,qty\no1,new\n", "invalid_bundle_row_width"),
        (b'ocel_id,status,qty\no1,un"quoted,1\n', "invalid_bundle_csv"),
        (b'ocel_id,status,qty\no1,"quoted" garbage,1\n', "invalid_bundle_csv"),
        (b"ocel_id,status,qty\ro1,new,1\r", "invalid_bundle_csv"),
        (b"ocel_id,status,qty\no1,\xff,1\n", "invalid_bundle_utf8"),
        (b"ocel_id,status,qty\no1,new,1.0\n", "invalid_bundle_value"),
    ],
)
def test_invalid_csv_tables(tmp_path, replacement, code):
    files = _files()
    files["elsewhere/items.csv"] = replacement
    _failure(_write(tmp_path, files), code)


@pytest.mark.parametrize(
    "old,new,code",
    [
        (b",true,", b",1,", "invalid_bundle_value"),
        (b",1.25,", b",NaN,", "invalid_bundle_value"),
        (b",1.25,", b",1e999,", "invalid_bundle_value"),
        (b",-2,", b", 2,", "invalid_bundle_value"),
        (b"10:00:00+09:00", b"10:00:00", "invalid_bundle_timestamp"),
        (b"10:00:00+09:00", b"10:00:00.0000001+09:00", "timestamp_precision_loss"),
    ],
)
def test_csv_lexical_types_and_precision(tmp_path, old, new, code):
    files = _files()
    files["arbitrary/events.csv"] = files["arbitrary/events.csv"].replace(old, new)
    _failure(_write(tmp_path, files), code)


@pytest.mark.parametrize(
    "replacement,code",
    [
        (b"o1,1970-01-01T00:00:00Z,status,done,", "epoch_bundle_change"),
        (b"absent,2026-01-02T00:00:00Z,status,done,", "invalid_bundle_change_source"),
        (b"o1,2026-01-02T00:00:00Z,unknown,done,", "unknown_changed_field"),
        (b"o1,2026-01-02T00:00:00Z,status,,", "missing_bundle_change_value"),
        (b"o1,2026-01-02T00:00:00Z,status,done,3", "ambiguous_bundle_change"),
    ],
)
def test_invalid_changes_never_silently_dropped(tmp_path, replacement, code):
    files = _files()
    files["history.csv"] = (
        files["history.csv"].splitlines()[0] + b"\n" + replacement + b"\n"
    )
    _failure(_write(tmp_path, files), code)


def test_dangling_relations_and_duplicate_events_preserved_for_semantics(tmp_path):
    files = _files()
    files["e2o.csv"] += b"absent-event,absent-object,missing\n"
    files["o2o.csv"] += b"absent-source,absent-target,missing\n"
    files["arbitrary/events.csv"] += b",orphan-event,2026-01-01T02:00:00Z,,,,\n"
    result, _ = bundled.load(_write(tmp_path, files))
    assert not result.valid
    assert len(result.candidate.events) == 3
    assert len(result.candidate.e2o) == 3
    assert len(result.candidate.o2o) == 2


def _parquet_files() -> dict[str, bytes]:
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    files = _files()
    meta = _metadata("parquet")
    output = {"ocel-meta.json": json.dumps(meta, ensure_ascii=False).encode()}
    csv_meta = _metadata()
    typed_tables = []
    for kind in ("event", "object"):
        for item in csv_meta[f"{kind}Types"].values():
            attrs = {attr["name"]: attr["type"] for attr in item["attributes"]}
            fixed = {"ocel_id": "string"}
            if kind == "event":
                fixed["ocel_time"] = "time"
            typed_tables.append((item["file"], fixed, attrs))
            if kind == "object":
                typed_tables.append(
                    (
                        item["changesFile"],
                        {**fixed, "ocel_time": "time", "ocel_changed_field": "string"},
                        attrs,
                    )
                )
    typed_tables.extend(
        [
            (
                "e2o.csv",
                {
                    name: "string"
                    for name in ("ocel_event_id", "ocel_object_id", "ocel_qualifier")
                },
                {},
            ),
            (
                "o2o.csv",
                {
                    name: "string"
                    for name in ("ocel_source_id", "ocel_target_id", "ocel_qualifier")
                },
                {},
            ),
        ]
    )
    arrow_types = {
        "string": pa.string(),
        "integer": pa.int64(),
        "float": pa.float64(),
        "boolean": pa.bool_(),
        "time": pa.timestamp("us", tz="UTC"),
    }
    converters = {
        "string": str,
        "integer": int,
        "float": float,
        "boolean": lambda value: value == "true",
        "time": lambda value: datetime.fromisoformat(
            value.replace("Z", "+00:00")
        ).astimezone(timezone.utc),
    }
    for name, fixed, attrs in typed_tables:
        kinds = {**fixed, **attrs}
        schema = pa.schema(
            [
                pa.field(column, arrow_types[kind], nullable=column in attrs)
                for column, kind in kinds.items()
            ]
        )
        records = []
        for record in csv.DictReader(io.StringIO(files[name].decode(), newline="")):
            records.append(
                {
                    key: None
                    if value == "" and key in attrs
                    else converters[kinds[key]](value)
                    for key, value in record.items()
                }
            )
        sink = pa.BufferOutputStream()
        pq.write_table(pa.Table.from_pylist(records, schema=schema), sink)
        output[name.removesuffix(".csv") + ".parquet"] = sink.getvalue().to_pybytes()
    return output


@pytest.mark.parametrize("archive", [False, True])
def test_real_parquet_matches_csv_and_json(tmp_path, archive):
    result, changes = bundled.load(_write(tmp_path, _parquet_files(), archive=archive))
    assert result.valid
    assert result.candidate == _expected()
    assert [item.code for item in changes] == ["bundle_specification_profile"]


def test_missing_optional_dependency_is_structured(tmp_path, monkeypatch):
    files = {
        name.removesuffix(".csv") + ".parquet": b"PAR1"
        for name in _files()
        if name.endswith(".csv")
    }
    files["ocel-meta.json"] = json.dumps(_metadata("parquet")).encode()
    original_import = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ModuleNotFoundError("simulated optional dependency absent")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    failure = _failure(_write(tmp_path, files), "dependency_unavailable")
    assert failure.status is ImportStatus.UNSUPPORTED


@pytest.mark.parametrize(
    "case",
    [
        "int32",
        "float32",
        "nullable_fixed",
        "required_attribute",
        "string_timestamp",
        "nanoseconds",
        "naive_timestamp",
    ],
)
def test_parquet_schema_mismatches(tmp_path, case):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    files = _parquet_files()
    name = "arbitrary/events.parquet"
    table = pq.read_table(pa.BufferReader(files[name]))
    fields = list(table.schema)
    replacements = {
        "int32": ("count", pa.int32(), True),
        "float32": ("amount", pa.float32(), True),
        "nullable_fixed": ("ocel_id", pa.string(), True),
        "required_attribute": ("memo", pa.string(), False),
        "string_timestamp": ("ocel_time", pa.string(), False),
        "nanoseconds": ("ocel_time", pa.timestamp("ns", tz="UTC"), False),
        "naive_timestamp": ("ocel_time", pa.timestamp("us"), False),
    }
    column, dtype, nullable = replacements[case]
    index = table.schema.get_field_index(column)
    fields[index] = pa.field(column, dtype, nullable=nullable)
    if case == "required_attribute":
        values = pa.array(["memo", ""], type=pa.string())
    else:
        values = table[column].cast(dtype)
    modified = table.set_column(index, fields[index], values)
    sink = pa.BufferOutputStream()
    pq.write_table(modified, sink)
    files[name] = sink.getvalue().to_pybytes()
    _failure(_write(tmp_path, files), "invalid_bundle_parquet_schema")


def test_parquet_corruption_is_structured(tmp_path):
    files = _parquet_files()
    files["arbitrary/events.parquet"] = b"PAR1truncated"
    _failure(_write(tmp_path, files), "invalid_bundle_parquet")


@pytest.mark.parametrize(
    "change,code",
    [
        ("version", "unsupported_bundle_version"),
        ("storage", "unsupported_bundle_storage"),
        ("primitive", "unsupported_attribute_type"),
        ("duplicate_attr", "duplicate_attribute_declaration"),
        ("reserved", "reserved_bundle_attribute"),
        ("duplicate_path", "duplicate_bundle_table"),
        ("missing_file", "missing_bundle_member"),
        ("mixed", "mixed_bundle_storage"),
        ("unknown_meta", "unexpected_member"),
    ],
)
def test_metadata_schema_is_authoritative(tmp_path, change, code):
    files = _files()
    meta = _metadata()
    event = next(iter(meta["eventTypes"].values()))
    if change == "version":
        meta["bundleFormatVersion"] = "2.0"
    elif change == "storage":
        meta["storageFormat"] = "tsv"
    elif change == "primitive":
        event["attributes"][0]["type"] = "date"
    elif change == "duplicate_attr":
        event["attributes"].append(event["attributes"][0])
    elif change == "reserved":
        event["attributes"][0]["name"] = "ocel_time"
    elif change == "duplicate_path":
        meta["relations"]["o2o"] = meta["relations"]["e2o"]
    elif change == "missing_file":
        event["file"] = "absent.csv"
    elif change == "mixed":
        event["file"] = "table.parquet"
    else:
        meta["unexpected"] = True
    files["ocel-meta.json"] = json.dumps(meta).encode()
    _failure(_write(tmp_path, files), code)


@pytest.mark.parametrize(
    "data,code",
    [
        (b'{"eventTypes":{},"eventTypes":{}}', "duplicate_json_member"),
        (b'{"value":NaN}', "nonfinite_json_number"),
        (b"not-json", "invalid_bundle_metadata"),
        ('{"hello": "세계"}'.encode("utf-16"), "invalid_bundle_metadata"),
    ],
)
def test_invalid_metadata_json(tmp_path, data, code):
    files = _files()
    files["ocel-meta.json"] = data
    _failure(_write(tmp_path, files), code)


def test_empty_tables_and_empty_qualifier(tmp_path):
    files = _files()
    files["history.csv"] = files["history.csv"].splitlines()[0] + b"\n"
    files["e2o.csv"] = files["e2o.csv"].replace(b",used", b",")
    result, _ = bundled.load(_write(tmp_path, files))
    assert result.valid
    assert result.candidate.e2o[0].qualifier == ""
    assert all(
        attr.time == OCEL_EPOCH
        for obj in result.candidate.objects
        for attr in obj.attributes
    )


def test_csv_literal_null_and_zero_padding_precision(tmp_path):
    files = _files()
    files["elsewhere/items.csv"] = files["elsewhere/items.csv"].replace(b"new", b"null")
    files["arbitrary/events.csv"] = files["arbitrary/events.csv"].replace(
        b"10:00:00+09:00", b"10:00:00.123456000+09:00"
    )
    result, _ = bundled.load(_write(tmp_path, files))
    assert result.valid
    assert result.candidate.events[0].time.microsecond == 123456
    assert any(
        attr.value == "null"
        for obj in result.candidate.objects
        for attr in obj.attributes
    )


def test_csv_does_not_load_optional_dependency(tmp_path, monkeypatch):
    original_import = builtins.__import__

    def forbidden(name, *args, **kwargs):
        if name == "pyarrow" or name.startswith("pyarrow."):
            pytest.fail("CSV attempted to import optional Parquet dependency")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", forbidden)
    assert bundled.load(_write(tmp_path, _files()))[0].valid


def test_parquet_empty_string_is_distinct_from_null(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    files = _parquet_files()
    name = "elsewhere/items.parquet"
    table = pq.ParquetFile(pa.BufferReader(files[name])).read()
    index = table.schema.get_field_index("status")
    table = table.set_column(
        index, table.schema.field(index), pa.array(["new", "", None], type=pa.string())
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    files[name] = sink.getvalue().to_pybytes()
    result, _ = bundled.load(_write(tmp_path, files))
    assert result.valid
    objects = {obj.id: obj for obj in result.candidate.objects}
    assert any(
        attr.name == "status" and attr.value == "" for attr in objects["o2"].attributes
    )
    assert not objects["orphan"].attributes


def test_parquet_timestamp_outside_canonical_range(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    files = _parquet_files()
    name = "arbitrary/events.parquet"
    table = pq.ParquetFile(pa.BufferReader(files[name])).read()
    index = table.schema.get_field_index("ocel_time")
    values = pa.array([2**63 - 1, 0], type=pa.int64()).cast(
        pa.timestamp("us", tz="UTC")
    )
    table = table.set_column(index, table.schema.field(index), values)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    files[name] = sink.getvalue().to_pybytes()
    _failure(_write(tmp_path, files), "timestamp_out_of_range")


@pytest.mark.parametrize("clock", [b"12:30.5Z", b"1230,5Z"])
def test_fractional_minutes_never_mapped_as_fractional_seconds(tmp_path, clock):
    files = _files()
    replacement = clock if b"," not in clock else b'"2026-01-01T' + clock + b'"'
    if b"," in clock:
        files["arbitrary/events.csv"] = files["arbitrary/events.csv"].replace(
            b"2026-01-01T10:00:00+09:00", replacement
        )
    else:
        files["arbitrary/events.csv"] = files["arbitrary/events.csv"].replace(
            b"10:00:00+09:00", replacement
        )
    _failure(_write(tmp_path, files), "invalid_bundle_timestamp")


def test_csv_large_string_ignores_process_global_csv_field_limit(tmp_path, monkeypatch):
    files = _files()
    value = b"x" * 200_000
    files["elsewhere/items.csv"] = files["elsewhere/items.csv"].replace(b"new", value)
    prior = csv.field_size_limit(16)
    try:
        result, _ = bundled.load(_write(tmp_path, files))
        assert result.valid
        assert any(
            attr.value == value.decode()
            for obj in result.candidate.objects
            for attr in obj.attributes
        )
    finally:
        csv.field_size_limit(prior)


def test_damaged_deflate_member_is_structured(tmp_path):
    path = tmp_path / "damaged.ocel.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as output:
        for name, data in _files().items():
            output.writestr(name, data)
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("ocel-meta.json")
    raw = bytearray(path.read_bytes())
    start = info.header_offset + 30 + len(info.filename.encode()) + len(info.extra)
    raw[start] = 0xFF  # reserved DEFLATE block type
    path.write_bytes(raw)
    _failure(path, "unreadable_bundle")


def test_open_handle_identity_checked_before_read(tmp_path, monkeypatch):
    directory = _write(tmp_path, _files())
    outside = tmp_path / "outside"
    outside.write_bytes(b"X" * (directory / "ocel-meta.json").stat().st_size)
    with _bundle_source.BundleSource(directory) as source:
        original_open = os.open

        def substitute(path, flags, *args, **kwargs):
            return original_open(outside, flags, *args, **kwargs)

        monkeypatch.setattr(os, "open", substitute)
        with pytest.raises(AdapterFailure) as caught:
            source.read("ocel-meta.json")
        assert caught.value.code == "bundle_changed"


@pytest.mark.parametrize("dictionary", [False, True])
def test_physical_parquet_utf8_accepts_arrow_large_or_dictionary_string(
    tmp_path, dictionary
):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    files = _parquet_files()
    name = "elsewhere/items.parquet"
    table = pq.ParquetFile(pa.BufferReader(files[name])).read()
    index = table.schema.get_field_index("ocel_id")
    dtype = pa.dictionary(pa.int32(), pa.string()) if dictionary else pa.large_string()
    table = table.set_column(
        index, pa.field("ocel_id", dtype, nullable=False), table["ocel_id"].cast(dtype)
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    files[name] = sink.getvalue().to_pybytes()
    result, _ = bundled.load(_write(tmp_path, files))
    assert result.valid
    assert result.candidate == _expected()


def test_public_directory_and_archive_results(tmp_path):
    from pix.ocel import ImportFormat, import_ocel

    directory = _write(tmp_path, _files())
    archive = _write(tmp_path, _files(), archive=True)
    directory_result = import_ocel(directory)
    archive_result = import_ocel(archive)
    assert directory_result.valid and archive_result.valid
    assert directory_result.format is ImportFormat.OCEL21_BUNDLE
    assert directory_result.canonical_digest == archive_result.canonical_digest
    assert directory_result.source_sha256 == bundled.source_evidence(directory)[0]
    assert (
        archive_result.source_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows reparse-point contract")
def test_directory_junction_is_rejected_on_windows(tmp_path):
    import _winapi

    directory = _write(tmp_path, _files())
    outside = tmp_path / "outside"
    outside.mkdir()
    _winapi.CreateJunction(str(outside), str(directory / "junction"))
    _failure(directory, "bundle_symlink_forbidden")
