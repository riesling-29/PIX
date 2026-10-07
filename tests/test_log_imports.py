"""Public import routing, native-model boundaries and shared-parser regressions."""

import gzip
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import replace
from hashlib import sha256

import pytest

from pix import import_log, read_log
from pix.api import CaseTableMapping, CaseTraceSpec, case_traces
from pix.event_log import CaseImportError, CaseImportResult, CaseLog
from pix.ocel import ImportFormat, ImportStatus, OCELImportError, import_ocel
from pix.results import result_document, result_from_json, result_json_bytes

XES = """<?xml version="1.0" encoding="UTF-8"?>
<log xes.version="1.0"><trace><event>
<string key="concept:name" value="A"/>
</event></trace><trace/></log>"""
MXML = """<WorkflowLog><Process id="p"><ProcessInstance id="c">
<AuditTrailEntry><WorkflowModelElement>A</WorkflowModelElement>
<EventType>complete</EventType></AuditTrailEntry>
</ProcessInstance></Process></WorkflowLog>"""


@pytest.mark.parametrize("kind,xml", [("xes", XES), ("mxml", MXML)])
@pytest.mark.parametrize("suffix", [".xml", ".data", ".xml.gz"])
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_case_content_dispatch_preserves_native_type(
    tmp_path, kind, xml, suffix, encoding
):
    data = xml.replace(
        'encoding="UTF-8"',
        'encoding="UTF-16"' if encoding == "utf-16" else 'encoding="UTF-8"',
    ).encode(encoding)
    path = tmp_path / ("source" + suffix)
    path.write_bytes(gzip.compress(data) if suffix.endswith(".gz") else data)
    result = import_log(path)
    assert isinstance(result, CaseImportResult)
    assert result.valid, result.describe()
    assert result.format == kind
    assert isinstance(read_log(path), CaseLog)
    assert result.source_sha256 == sha256(path.read_bytes()).hexdigest()
    assert result.source_size == path.stat().st_size
    native_only = import_ocel(path)
    assert native_only.status is ImportStatus.UNSUPPORTED
    assert native_only.import_issues[0].code == "case_log_requires_native_import"


def test_explicit_format_does_not_silently_switch_models(tmp_path):
    path = tmp_path / "source.xml"
    path.write_text(XES, encoding="utf-8")
    result = import_log(path, format="ocel20-xml")
    assert not result.valid
    assert result.format is ImportFormat.OCEL20_XML
    with pytest.raises(OCELImportError):
        read_log(path, format="ocel20-xml")
    path.write_text("<log><trace>", encoding="utf-8")
    with pytest.raises(CaseImportError):
        read_log(path, format="xes")


@pytest.mark.parametrize("suffix", [".csv", ".tsv", ".xlsx"])
def test_generic_tables_require_domain_mapping(tmp_path, suffix):
    path = tmp_path / ("business" + suffix)
    path.write_bytes(b"case,task\nc,A\n")
    result = import_log(path)
    assert result.status is ImportStatus.UNSUPPORTED
    assert result.import_issues[0].code == "table_mapping_required"
    assert result.source_sha256 == sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("format,delimiter", [("csv", ","), ("table-tsv", "\t")])
def test_mapping_format_override_reaches_table_source(tmp_path, format, delimiter):
    path = tmp_path / "business.data"
    path.write_text(f"case{delimiter}task\nc{delimiter}A\n", encoding="utf-8")
    result = import_log(path, format=format, mapping=CaseTableMapping("case", "task"))
    assert result.valid, result.describe()
    trace = case_traces(result.require_case_log()).value.traces[0]
    assert trace.events[0].activity == "A"
    assert trace.events[0].time is None


def test_records_and_file_share_native_case_facts(tmp_path):
    path = tmp_path / "business.csv"
    path.write_text("case,task\nc,A\nc,B\n", encoding="utf-8")
    mapping = CaseTableMapping("case", "task")
    file_log = read_log(path, mapping=mapping)
    rows_log = read_log(
        [{"case": "c", "task": "A"}, {"case": "c", "task": "B"}],
        mapping=mapping,
    )
    assert file_log.traces == rows_log.traces
    assert file_log.source != rows_log.source


def _resign(document):
    body = {k: v for k, v in document.items() if k != "document_digest"}
    data = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    document["document_digest"] = (
        "pix.analysis-result.v1:sha256:" + sha256(data).hexdigest()
    )
    return json.dumps(document)


@pytest.mark.parametrize("version", ["1.0.0", "1.1.0"])
def test_case_trace_result_cannot_claim_old_nonnullable_schema(tmp_path, version):
    path = tmp_path / "source.xes"
    path.write_text(XES, encoding="utf-8")
    traces = case_traces(read_log(path), CaseTraceSpec())
    assert result_from_json(result_json_bytes(traces)) == traces
    doc = result_document(traces)
    doc["version"] = version
    with pytest.raises(ValueError, match="case trace results require"):
        result_from_json(_resign(doc))


def test_ocel_trace_envelope_still_requires_event_times(native_log):
    from pix.api import TraceSpec, reconstruct_traces

    original = reconstruct_traces(native_log, TraceSpec("Order"))
    first = original.value.traces[0]
    untimed = replace(first.events[0], time=None)
    changed = replace(first, events=(untimed, *first.events[1:]))
    payload = replace(original.value, traces=(changed, *original.value.traces[1:]))
    with pytest.raises(ValueError, match="timestamp"):
        result_document(replace(original, value=payload))


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-09-09T12:30.5Z",
        "2026-09-09T12.5Z",
        "2026-09-09T1230,5Z",
        "2026-09-09T12:30:00+01:30.5",
        "2026-09-09",
        "2026-W37-3T12:30:00Z",
        "2026-09-09T12:30:00+01:99",
        "2026-09-09T12:30:00+00:00:60",
        "Wed Sep 09 2026 12:30:00 GMT+0160",
    ],
)
def test_shared_timestamp_mapper_does_not_fabricate_precision(tmp_path, stamp):
    path = tmp_path / "source.json"
    path.write_text(
        json.dumps(
            {
                "eventTypes": [{"name": "A"}],
                "objectTypes": [],
                "objects": [],
                "events": [{"id": "e", "type": "A", "time": stamp}],
            }
        ),
        encoding="utf-8",
    )
    result = import_log(path)
    assert result.status is ImportStatus.MAPPING_INVALID
    assert result.import_issues[0].code == "invalid_timestamp"


@pytest.mark.parametrize("format", [None, "ocel20-sqlite", "ocel10-sqlite"])
@pytest.mark.parametrize("boundary", ["wal", "sidecar"])
def test_sqlite_routing_never_opens_journalled_source(
    tmp_path, monkeypatch, format, boundary
):
    path = tmp_path / "source.sqlite"
    with closing(sqlite3.connect(path)) as db:
        db.execute("CREATE TABLE example (id TEXT)")
    if boundary == "wal":
        data = bytearray(path.read_bytes())
        data[18:20] = bytes([2, 2])
        path.write_bytes(data)
    else:
        path.with_name(path.name + "-wal").write_bytes(b"source sidecar")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}

    def forbidden(*args, **kwargs):
        pytest.fail("journalled source was opened during routing/import")

    monkeypatch.setattr(sqlite3, "connect", forbidden)
    result = import_log(path, format=format)
    assert result.status in {ImportStatus.UNSUPPORTED, ImportStatus.SCHEMA_INVALID}
    assert "journal" in result.import_issues[0].code
    assert {p.name: p.read_bytes() for p in tmp_path.iterdir()} == before


def test_public_facade_keeps_optional_and_reference_libraries_unloaded():
    probe = """
import sys
import pix.api
for name in ("pm4py", "ocpa", "pandas", "openpyxl", "pyarrow"):
    assert name not in sys.modules, name
"""
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_legacy_global_primitives_do_not_prematurely_select_xes(tmp_path):
    path = tmp_path / "source.xml"
    path.write_text(
        """<log><global scope="event">
        <string key="activity" value="default"/></global>
        <events><event><string key="id" value="e"/>
        <date key="timestamp" value="2026-09-09T12:00:00Z"/>
        <list key="omap"/><list key="vmap"/>
        </event></events><objects/></log>""",
        encoding="utf-8",
    )
    result = import_log(path)
    assert result.valid, result.describe()
    assert result.format is ImportFormat.OCEL10_XML
    assert result.require_ocel().events[0].type == "default"


def test_sqlite_detection_and_adapter_close_connections(
    tmp_path, monkeypatch, native_log
):
    from pix.ocel import export_ocel

    path = tmp_path / "source.sqlite"
    export_ocel(native_log, path, format="sqlite")
    connect = sqlite3.connect
    connections = []

    def tracked(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", tracked)
    assert import_log(path).valid
    assert connections
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
            connection.execute("SELECT 1")
