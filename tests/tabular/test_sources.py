"""Source parsing must preserve raw evidence and reject ambiguous tables."""

from __future__ import annotations

import builtins
import gzip
import hashlib
import io
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from xml.etree import ElementTree

import pytest

from pix.ocel.ingest.contract import ImportStage, ImportStatus
from pix.tabular.source import TableSourceError, load_table


def test_csv_preserves_text_quotes_multiline_and_raw_evidence(tmp_path: Path) -> None:
    raw = b'id,description,quantity\r\n001,"a,b\r\n""quoted""",02\r\n'
    source = tmp_path / "events.csv"
    source.write_bytes(raw)
    result = load_table(source)
    assert result.fields == ("id", "description", "quantity")
    assert result.rows == (
        {"id": "001", "description": 'a,b\r\n"quoted"', "quantity": "02"},
    )
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.size == len(raw)
    assert result.kind == "csv"
    assert result.source == str(source)


@pytest.mark.parametrize("suffix", [".tsv", ".tsv.gz"])
def test_tsv_and_gzip_identify_original_bytes(tmp_path: Path, suffix: str) -> None:
    raw = "id\tname\n001\t한글\n".encode()
    if suffix.endswith(".gz"):
        raw = gzip.compress(raw, mtime=0)
    source = tmp_path / f"events{suffix}"
    source.write_bytes(raw)
    result = load_table(source)
    assert result.rows == ({"id": "001", "name": "한글"},)
    assert result.kind == "tsv"
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.size == len(raw)
    assert bool(result.transformations) == suffix.endswith(".gz")


@pytest.mark.parametrize(
    ("text", "code", "status"),
    [
        ("", "missing_header", ImportStatus.SCHEMA_INVALID),
        ("a,a\n1,2", "duplicate_header", ImportStatus.SCHEMA_INVALID),
        ("a, \n1,2", "blank_header", ImportStatus.SCHEMA_INVALID),
        ("a,b\n1", "row_width_mismatch", ImportStatus.SCHEMA_INVALID),
        ("a,b\n1,2,3", "row_width_mismatch", ImportStatus.SCHEMA_INVALID),
        ("a,b\n\n", "row_width_mismatch", ImportStatus.SCHEMA_INVALID),
        ('a,b\n"open,2', "csv_invalid", ImportStatus.SYNTAX_INVALID),
        ('a,b\nx"y,2', "csv_invalid", ImportStatus.SYNTAX_INVALID),
        ('a,b\n"x"y,2', "csv_invalid", ImportStatus.SYNTAX_INVALID),
    ],
)
def test_csv_failures_retain_evidence(
    tmp_path: Path,
    text: str,
    code: str,
    status: ImportStatus,
) -> None:
    raw = text.encode()
    source = tmp_path / "bad.csv"
    source.write_bytes(raw)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == code
    assert failure.value.status is status
    assert failure.value.source == str(source)
    assert failure.value.kind == "csv"
    assert failure.value.sha256 == hashlib.sha256(raw).hexdigest()
    assert failure.value.size == len(raw)


def test_encoding_bom_and_explicit_delimiter(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_bytes("\ufeffid;name\n001;é\n".encode("utf-16-le"))
    result = load_table(source, delimiter=";", encoding="utf-16-le")
    assert result.rows == ({"id": "001", "name": "é"},)
    assert result.transformations[0].code == "text_bom_removed"


@pytest.mark.parametrize("delimiter", ["", "::", '"', "\n", None, 1])
def test_invalid_delimiter_is_evidence_carrying(
    tmp_path: Path, delimiter: object
) -> None:
    source = tmp_path / "events.csv"
    source.write_bytes(b"a\n1\n")
    with pytest.raises(TableSourceError) as failure:
        load_table(source, delimiter=delimiter)  # type: ignore[arg-type]
    assert failure.value.code == "invalid_delimiter"
    assert failure.value.sha256 is not None


@pytest.mark.parametrize(
    ("filename", "raw", "options", "code"),
    [
        ("bad.csv.gz", b"bad gzip", {}, "gzip_invalid"),
        ("bad.csv", b"\xff", {}, "text_decode_failed"),
        ("bad.csv", b"a\n1", {"encoding": "not-a-codec"}, "invalid_encoding"),
        ("bad.csv", b"a\n1", {"encoding": "utf-8\x00"}, "invalid_encoding"),
        ("bad.csv", b"a\n1", {"sheet": "Sheet"}, "unexpected_sheet"),
        ("bad.bin", b"a\n1", {}, "unsupported_format"),
        ("bad.xlsx", b"bad workbook", {}, "xlsx_invalid"),
    ],
)
def test_other_file_failures_retain_evidence(
    tmp_path: Path,
    filename: str,
    raw: bytes,
    options: dict[str, object],
    code: str,
) -> None:
    if filename.endswith(".xlsx"):
        pytest.importorskip("openpyxl")
    source = tmp_path / filename
    source.write_bytes(raw)
    with pytest.raises(TableSourceError) as failure:
        load_table(source, **options)
    assert failure.value.code == code
    assert failure.value.sha256 == hashlib.sha256(raw).hexdigest()
    assert failure.value.size == len(raw)


def test_missing_file_has_no_fabricated_evidence(tmp_path: Path) -> None:
    with pytest.raises(TableSourceError) as failure:
        load_table(tmp_path / "missing.csv")
    assert failure.value.status is ImportStatus.UNAVAILABLE
    assert failure.value.stage is ImportStage.SOURCE
    assert failure.value.sha256 is None
    assert failure.value.size is None
    with pytest.raises(TableSourceError) as failure:
        load_table(tmp_path / "missing.data", format="table-csv")
    assert failure.value.kind == "csv"


@pytest.mark.parametrize("format", ["csv", "table-csv", "CSV", ".csv"])
def test_explicit_csv_format_takes_precedence_over_suffix(
    tmp_path: Path,
    format: str,
) -> None:
    source = tmp_path / "table.data"
    source.write_text("id\n001\n")
    assert load_table(source, format=format).rows == ({"id": "001"},)


def test_explicit_tsv_and_gzip_without_recognized_table_extension(
    tmp_path: Path,
) -> None:
    source = tmp_path / "table.data.gz"
    source.write_bytes(gzip.compress(b"id\tname\n001\ta\n", mtime=0))
    result = load_table(source, format="table-tsv")
    assert result.kind == "tsv"
    assert result.rows == ({"id": "001", "name": "a"},)


@pytest.mark.parametrize("format", ["records", "table-records", "unknown", "", 1])
def test_explicit_incompatible_file_format_retains_evidence(
    tmp_path: Path,
    format: object,
) -> None:
    source = tmp_path / "table.csv"
    source.write_bytes(b"id\n001\n")
    with pytest.raises(TableSourceError) as failure:
        load_table(source, format=format)  # type: ignore[arg-type]
    assert failure.value.status is ImportStatus.MAPPING_INVALID
    assert failure.value.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_explicit_records_and_incompatible_formats_retain_evidence() -> None:
    rows = [{"id": "001"}]
    table = load_table(rows, format="table-records")
    assert table == load_table(rows)
    for format in ("csv", "table-xlsx", "unknown"):
        with pytest.raises(TableSourceError) as failure:
            load_table(rows, format=format)
        assert failure.value.status is ImportStatus.MAPPING_INVALID
        assert failure.value.sha256 == table.sha256


def test_records_union_keeps_absent_keys_absent_and_snapshots_lists() -> None:
    nested: list[object] = ["a", ["b"]]
    records = [{"a": 1, "nested": nested}, {"b": None}, {}]
    result = load_table(iter(records))
    nested.append("changed")
    assert result.fields == ("a", "nested", "b")
    assert result.rows == ({"a": 1, "nested": ["a", ["b"]]}, {"b": None}, {})
    assert result.kind == "records"
    assert result.source == "memory:records"


def test_records_hash_ignores_mapping_order_but_preserves_types_and_row_order() -> None:
    stamp = datetime(2026, 9, 12, tzinfo=timezone.utc)
    first = load_table([{"a": date(2026, 9, 12), "b": [Decimal("1.20"), stamp]}])
    second = load_table([{"b": [Decimal("1.20"), stamp], "a": date(2026, 9, 12)}])
    assert first.sha256 == second.sha256
    assert first.size == second.size
    hashes = {
        load_table([{"a": value}]).sha256 for value in (1, 1.0, True, "1", Decimal("1"))
    }
    assert len(hashes) == 5
    assert (
        load_table([{"a": 1}, {"a": 2}]).sha256
        != load_table([{"a": 2}, {"a": 1}]).sha256
    )
    assert load_table([{}]).sha256 != load_table([{"a": None}]).sha256
    assert load_table([]).fields == ()
    assert load_table([]).rows == ()
    assert load_table([{"a": (1, "b")}]).rows == ({"a": (1, "b")},)
    assert load_table([{"a": [1]}]).sha256 != load_table([{"a": (1,)}]).sha256


@pytest.mark.parametrize(
    "source",
    [
        None,
        b"csv",
        {"a": 1},
        [1],
        [{"": 1}],
        [{" ": 1}],
        [{1: "a"}],
        [{"a": object()}],
        [{"a": float("nan")}],
        [{"a": Decimal("Infinity")}],
        [{"a": {"nested": "dict"}}],
    ],
)
def test_invalid_records_fail_without_repr_fingerprints(source: object) -> None:
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.source == "memory:records"
    assert failure.value.kind == "records"
    assert failure.value.sha256 is None
    assert failure.value.size is None


def test_cyclic_cells_and_broken_iterators_are_diagnostic() -> None:
    cell: list[object] = []
    cell.append(cell)
    with pytest.raises(TableSourceError, match="cyclic"):
        load_table([{"a": cell}])

    def broken():
        yield {"a": 1}
        raise RuntimeError("source broke")

    with pytest.raises(TableSourceError) as failure:
        load_table(broken())
    assert failure.value.code == "records_unreadable"

    class BrokenIterable:
        def __iter__(self):
            raise RuntimeError("cannot start source")

    with pytest.raises(TableSourceError) as failure:
        load_table(BrokenIterable())
    assert failure.value.code == "records_unreadable"


def _workbook(tmp_path: Path, rows: list[list[object]]) -> tuple[object, Path]:
    openpyxl = pytest.importorskip("openpyxl")
    workbook = openpyxl.Workbook()
    for row in rows:
        workbook.active.append(row)
    source = tmp_path / "table.xlsx"
    return workbook, source


def test_xlsx_retains_native_types_and_sheet_selection(tmp_path: Path) -> None:
    stamp = datetime(2026, 9, 12, 12, 30)
    workbook, source = _workbook(tmp_path, [["id", "time", "flag"], [1, stamp, False]])
    workbook.create_sheet("Other").append(["id"])
    workbook.save(source)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "sheet_required"
    assert failure.value.sha256 is not None
    result = load_table(source, sheet=0)
    assert result.rows == ({"id": 1, "time": stamp, "flag": False},)
    assert result == load_table(source, sheet="Sheet")
    assert load_table(source, sheet="Other").rows == ()


def test_explicit_xlsx_and_explicit_csv_do_not_override_each_other(
    tmp_path: Path,
) -> None:
    workbook, source = _workbook(tmp_path, [["id"], [1]])
    workbook.save(source)
    alternate = tmp_path / "workbook.data"
    alternate.write_bytes(source.read_bytes())
    assert load_table(alternate, format="table-xlsx").rows == ({"id": 1},)
    with pytest.raises(TableSourceError) as failure:
        load_table(source, format="csv")
    assert failure.value.kind == "csv"
    assert failure.value.status is ImportStatus.SYNTAX_INVALID


@pytest.mark.parametrize(
    ("rows", "code"),
    [
        ([["a", "a"], [1, 2]], "duplicate_header"),
        ([["a", None], [1, 2]], "invalid_header"),
        ([["a", " "], [1, 2]], "blank_header"),
        ([["a", ""], [1, None]], "blank_header"),
        ([["a"], ["=1+1"]], "xlsx_formula"),
        ([["a"], ["#DIV/0!"]], "xlsx_cell_error"),
        ([["a"], [1], [None], [2]], "xlsx_empty_row"),
        ([], "missing_header"),
    ],
)
def test_xlsx_rejects_ambiguous_or_derived_cells(
    tmp_path: Path,
    rows: list[list[object]],
    code: str,
) -> None:
    workbook, source = _workbook(tmp_path, rows)
    workbook.save(source)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == code
    assert failure.value.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_xlsx_merged_cells_are_rejected(tmp_path: Path) -> None:
    workbook, source = _workbook(tmp_path, [["a", "b"], [1, 2]])
    workbook.active.merge_cells("A2:B2")
    workbook.save(source)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_merged_cells"


def test_xlsx_formula_with_cached_value_is_still_rejected(tmp_path: Path) -> None:
    workbook, source = _workbook(tmp_path, [["a"], ["=1+1"]])
    workbook.save(source)
    replacement = io.BytesIO()
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(replacement, "w") as output,
    ):
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(b"<v></v>", b"<v>2</v>")
            output.writestr(entry, content)
    source.write_bytes(replacement.getvalue())
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_formula"


@pytest.mark.parametrize("original_value", [1, "=1+1"])
@pytest.mark.parametrize("default_content_type", [False, True])
def test_xlsx_duplicate_cell_cannot_hide_original_value(
    tmp_path: Path,
    original_value: object,
    default_content_type: bool,
) -> None:
    workbook, source = _workbook(tmp_path, [["a"], [original_value]])
    workbook.save(source)
    replacement = io.BytesIO()
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(replacement, "w") as output,
    ):
        for entry in original.infolist():
            content = original.read(entry.filename)
            if default_content_type and entry.filename == "[Content_Types].xml":
                content_types = ElementTree.fromstring(content)
                for node in list(content_types):
                    if node.attrib.get("PartName") == "/xl/worksheets/sheet1.xml":
                        sheet_type = node.attrib["ContentType"]
                        content_types.remove(node)
                for node in content_types:
                    if node.attrib.get("Extension") == "xml":
                        node.set("ContentType", sheet_type)
                content = ElementTree.tostring(content_types)
            if entry.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(
                    b"</row></sheetData>",
                    b'<c r="A2" t="n"><v>999</v></c></row></sheetData>',
                )
            output.writestr(entry, content)
    source.write_bytes(replacement.getvalue())
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_duplicate_cell"
    assert failure.value.status is ImportStatus.SYNTAX_INVALID
    assert failure.value.sha256 == hashlib.sha256(source.read_bytes()).hexdigest()


def test_xlsx_duplicate_row_cannot_silently_overwrite_cells(tmp_path: Path) -> None:
    workbook, source = _workbook(tmp_path, [["a"], [1]])
    workbook.save(source)
    replacement = io.BytesIO()
    with (
        zipfile.ZipFile(source) as original,
        zipfile.ZipFile(replacement, "w") as output,
    ):
        for entry in original.infolist():
            content = original.read(entry.filename)
            if entry.filename == "xl/worksheets/sheet1.xml":
                content = content.replace(
                    b"</sheetData>",
                    b'<row r="2"><c r="A2" t="n"><v>999</v></c></row></sheetData>',
                )
            output.writestr(entry, content)
    source.write_bytes(replacement.getvalue())
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_duplicate_row"


def test_xlsx_literal_formula_text_and_small_style_padding(tmp_path: Path) -> None:
    workbook, source = _workbook(tmp_path, [["a"], ["=literal"]])
    workbook.active["A2"].data_type = "s"
    workbook.active["D10"].number_format = "0.00"
    workbook.save(source)
    assert load_table(source).rows == ({"a": "=literal"},)


def test_xlsx_excessive_dimensions_fail_before_rectangle_allocation(
    tmp_path: Path,
) -> None:
    workbook, source = _workbook(tmp_path, [["a"], [1]])
    workbook.active["XFD1048576"].number_format = "0.00"
    workbook.save(source)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_dimensions_exceeded"
    assert failure.value.status is ImportStatus.UNSUPPORTED
    assert failure.value.sha256 is not None


@pytest.mark.parametrize("sheet", [-1, 2, "absent", True, 1.5])
def test_xlsx_invalid_sheet_selections_keep_evidence(
    tmp_path: Path, sheet: object
) -> None:
    workbook, source = _workbook(tmp_path, [["a"], [1]])
    workbook.save(source)
    with pytest.raises(TableSourceError) as failure:
        load_table(source, sheet=sheet)  # type: ignore[arg-type]
    assert failure.value.status is ImportStatus.MAPPING_INVALID
    assert failure.value.sha256 is not None


def test_records_invalid_sheet_option_retains_canonical_source_evidence() -> None:
    rows = [{"a": 1}]
    with pytest.raises(TableSourceError) as failure:
        load_table(rows, sheet="Sheet")
    assert failure.value.code == "unexpected_sheet"
    assert failure.value.sha256 == load_table(rows).sha256


def test_openpyxl_is_optional_and_loaded_only_for_xlsx(
    tmp_path: Path, monkeypatch
) -> None:
    original = builtins.__import__

    def without_openpyxl(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("optional package absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_openpyxl)
    source = tmp_path / "table.xlsx"
    source.write_bytes(b"workbook source")
    assert load_table([{"a": 1}]).rows == ({"a": 1},)
    csv_source = tmp_path / "table.csv"
    csv_source.write_text("a\n1\n")
    assert load_table(csv_source).rows == ({"a": "1"},)
    with pytest.raises(TableSourceError) as failure:
        load_table(source)
    assert failure.value.code == "xlsx_dependency_unavailable"
    assert failure.value.sha256 is not None
