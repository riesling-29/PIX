"""Exercise new import paths against an isolated, installed PIX interpreter.

Run ``python -I check_import_wheel.py --output PATH`` from outside the checkout
after installing the wheel in a clean environment. Add ``--with-extras`` when
the ``imports`` extra is installed. Fixtures are constructed here using only
the standard library; optional libraries are used solely in the extras checks.
This is a packaging/integration smoke, not a format-conformance certification.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import sqlite3
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pix
from pix.api import (
    CaseLog,
    CaseTableMapping,
    ComputeStatus,
    DiscoverySpec,
    ObjectColumn,
    OCELTableMapping,
    case_log_digest,
    case_traces,
    discover_process_tree,
    export_ocel,
    process_tree_to_petri_net,
    read_result,
    replay_traces,
    to_ocel,
    write_result,
)
from pix.ocel import OCEL, ImportStatus, canonical_digest

STAMP = "2026-09-12T09:00:00Z"
LATER = "2026-09-12T09:01:00Z"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def csv_bytes(header: tuple[str, ...], rows: list[tuple]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


def write_files(directory: Path, files: dict[str, bytes]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        target = directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return directory


def bundle_files(storage: str = "csv") -> dict[str, bytes]:
    metadata = {
        "ocelVersion": "2.0",
        "bundleFormatVersion": "1.0",
        "storageFormat": storage,
        "eventTypes": {
            activity: {"file": f"{activity}.{storage}", "attributes": []}
            for activity in ("A", "B")
        },
        "objectTypes": {
            "Order": {
                "file": f"objects.{storage}",
                "changesFile": f"changes.{storage}",
                "attributes": [],
            }
        },
        "relations": {"e2o": f"e2o.{storage}", "o2o": f"o2o.{storage}"},
    }
    files = {
        "ocel-meta.json": json.dumps(metadata).encode(),
        "A.csv": csv_bytes(("ocel_id", "ocel_time"), [("e1", STAMP)]),
        "B.csv": csv_bytes(("ocel_id", "ocel_time"), [("e2", LATER)]),
        "objects.csv": csv_bytes(("ocel_id",), [("o1",), ("orphan",)]),
        "changes.csv": csv_bytes(("ocel_id", "ocel_time", "ocel_changed_field"), []),
        "e2o.csv": csv_bytes(
            ("ocel_event_id", "ocel_object_id", "ocel_qualifier"),
            [("e1", "o1", ""), ("e2", "o1", "")],
        ),
        "o2o.csv": csv_bytes(
            ("ocel_source_id", "ocel_target_id", "ocel_qualifier"), []
        ),
    }
    if storage == "parquet":
        # These placeholders reach the dependency check before table decoding.
        return {
            name.removesuffix(".csv") + ".parquet"
            if name.endswith(".csv")
            else name: b"PAR1" if name.endswith(".csv") else content
            for name, content in files.items()
        }
    return files


def legacy_files(directory: Path) -> list[Path]:
    document = {
        "ocel:global-log": {
            "ocel:version": "1.0",
            "ocel:object-types": ["Order"],
            "ocel:attribute-names": [],
        },
        "ocel:events": {
            key: {
                "ocel:activity": activity,
                "ocel:timestamp": timestamp,
                "ocel:omap": ["o1"],
                "ocel:vmap": {},
            }
            for key, activity, timestamp in (("e1", "A", STAMP), ("e2", "B", LATER))
        },
        "ocel:objects": {
            key: {"ocel:type": "Order", "ocel:ovmap": {}} for key in ("o1", "orphan")
        },
    }
    json_path = directory / "legacy.json"
    json_path.write_text(json.dumps(document), encoding="utf-8")
    events = "".join(
        f'<event><string key="id" value="{key}"/>'
        f'<string key="activity" value="{activity}"/>'
        f'<date key="timestamp" value="{timestamp}"/>'
        '<list key="omap"><string key="object-id" value="o1"/></list>'
        '<list key="vmap"/></event>'
        for key, activity, timestamp in (("e1", "A", STAMP), ("e2", "B", LATER))
    )
    objects = "".join(
        f'<object><string key="id" value="{key}"/>'
        '<string key="type" value="Order"/><list key="ovmap"/></object>'
        for key in ("o1", "orphan")
    )
    xml_path = directory / "legacy.xml"
    xml_path.write_text(
        f"<log><events>{events}</events><objects>{objects}</objects></log>",
        encoding="utf-8",
    )
    sqlite_path = directory / "legacy.sqlite"
    with sqlite3.connect(sqlite_path) as connection:
        # Rerunning this smoke only resets its own fixed-name fixture tables.
        connection.executescript("""
            DROP TABLE IF EXISTS EVENTS;
            DROP TABLE IF EXISTS OBJECTS;
            DROP TABLE IF EXISTS RELATIONS;
            CREATE TABLE EVENTS (
                "ocel:eid" TEXT, "ocel:activity" TEXT, "ocel:timestamp" TEXT);
            CREATE TABLE OBJECTS ("ocel:oid" TEXT, "ocel:type" TEXT);
            CREATE TABLE RELATIONS (
                "ocel:eid" TEXT, "ocel:activity" TEXT, "ocel:timestamp" TEXT,
                "ocel:oid" TEXT, "ocel:type" TEXT);
        """)
        connection.executemany(
            "INSERT INTO EVENTS VALUES (?, ?, ?)",
            [("e1", "A", STAMP), ("e2", "B", LATER)],
        )
        connection.executemany(
            "INSERT INTO OBJECTS VALUES (?, ?)", [("o1", "Order"), ("orphan", "Order")]
        )
        connection.executemany(
            "INSERT INTO RELATIONS VALUES (?, ?, ?, ?, ?)",
            [("e1", "A", STAMP, "o1", "Order"), ("e2", "B", LATER, "o1", "Order")],
        )
    return [json_path, xml_path, sqlite_path]


def parquet_files() -> dict[str, bytes]:
    import pyarrow as pa
    import pyarrow.parquet as pq

    files = bundle_files("parquet")
    for name, data in bundle_files().items():
        if not name.endswith(".csv"):
            continue
        reader = csv.DictReader(io.StringIO(data.decode(), newline=""))
        schema = pa.schema(
            [
                pa.field(
                    key,
                    pa.timestamp("us", tz="UTC") if key == "ocel_time" else pa.string(),
                    nullable=False,
                )
                for key in reader.fieldnames
            ]
        )
        records = [
            {
                key: datetime.fromisoformat(value.replace("Z", "+00:00"))
                if key == "ocel_time"
                else value
                for key, value in row.items()
            }
            for row in reader
        ]
        sink = pa.BufferOutputStream()
        pq.write_table(pa.Table.from_pylist(records, schema=schema), sink)
        files[name.removesuffix(".csv") + ".parquet"] = sink.getvalue().to_pybytes()
    return files


def smoke(output: Path, with_extras: bool) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    fixtures = output / "fixtures"
    fixtures.mkdir(exist_ok=True)
    checks: dict[str, object] = {}

    def record(
        name, result, *, expected_code=None, expected_status=ImportStatus.UNSUPPORTED
    ):
        require(result.source_sha256 is not None, f"{name}: source hash absent")
        require(result.source_size is not None, f"{name}: source byte size absent")
        if expected_code is None:
            require(result.valid, f"{name}: {result.describe()}")
        else:
            require(result.status is expected_status, f"{name}: wrong status")
            require(
                expected_code in {issue.code for issue in result.import_issues},
                f"{name}: missing {expected_code}: {result.describe()}",
            )
        candidate = result.candidate
        checks[name] = {
            "status": result.status.value,
            "format": result.format,
            "source_sha256": result.source_sha256,
            "source_size": result.source_size,
            "issues": [issue.code for issue in result.import_issues],
            "transformations": [item.code for item in result.transformations],
            "native_digest": str(canonical_digest(candidate))
            if isinstance(candidate, OCEL)
            else case_log_digest(candidate)
            if isinstance(candidate, CaseLog)
            else None,
        }
        return candidate

    # OCEL serializations encode the same facts, including an unreferenced object.
    reference = None
    for path in legacy_files(fixtures):
        result = pix.import_log(path)
        log = record("legacy_" + path.suffix[1:], result)
        require(len(log.events) == 2 and len(log.objects) == 2, "legacy entity loss")
        require(len(log.e2o) == 2, "legacy relation loss")
        require(
            all(edge.qualifier == "" for edge in log.e2o), "legacy qualifier invention"
        )
        if reference is None:
            reference = canonical_digest(log)
        require(canonical_digest(log) == reference, "legacy dialects disagree")

    compact = fixtures / "sample.ocel.csv"
    compact.write_bytes(
        csv_bytes(
            ("id", "activity", "timestamp", "ot:Order"),
            [
                ("", "", "", "orphan"),
                ("e1", "A", STAMP, "o1"),
                ("e2", "B", LATER, "o1"),
            ],
        )
    )
    compact_log = record("compact_csv", pix.import_log(compact))
    require(canonical_digest(compact_log) == reference, "compact changed facts")
    files = bundle_files()
    directory = write_files(fixtures / "csv-bundle", files)
    archive = fixtures / "sample.ocel.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
        for name, content in reversed(tuple(files.items())):
            zipped.writestr(zipfile.ZipInfo(name), content)
    for name, path in (("bundle_directory", directory), ("bundle_zip", archive)):
        result = pix.import_log(path)
        require(
            canonical_digest(record(name, result)) == reference, f"{name} changed facts"
        )
    require(
        checks["bundle_directory"]["source_sha256"]
        != checks["bundle_zip"]["source_sha256"],
        "directory and ZIP byte evidence unexpectedly conflated",
    )

    # Source order and empty traces survive even without event timestamps.
    xes = fixtures / "untimed.xes.gz"
    xes.write_bytes(
        gzip.compress(
            b'<log xes.version="1.0"><classifier name="Activity" keys="concept:name"/>'
            b'<trace><string key="concept:name" value="source-case"/>'
            b'<event><string key="concept:name" value="B"/></event>'
            b'<event><string key="concept:name" value="A"/></event></trace><trace/></log>',
            mtime=0,
        )
    )
    native = record("xes_gzip", pix.import_log(xes))
    require(isinstance(pix.read_log(xes), CaseLog), "read_log implicitly projected XES")
    require(native.classifiers[0].keys == ("concept:name",), "classifier lost")
    traces = case_traces(native)
    require(traces.status is ComputeStatus.COMPUTED, "native traces unavailable")
    require(
        [event.activity for event in traces.value.traces[0].events] == ["B", "A"],
        "source order changed",
    )
    require(
        all(event.time is None for event in traces.value.traces[0].events),
        "timestamp invented",
    )
    require(traces.value.traces[1].events == (), "empty trace dropped")
    tree = discover_process_tree(traces, DiscoverySpec(algorithm="pix.im.v1"))
    require(tree.status is ComputeStatus.COMPUTED, "native discovery failed")
    replay = replay_traces(traces, process_tree_to_petri_net(tree.value))
    require(replay.status is ComputeStatus.COMPUTED, "native replay failed")
    counts = replay.value.completed_counts
    require(
        counts.missing == counts.remaining == 0,
        "native discovered model replay mismatch",
    )
    result_path = output / "native-traces.result.json"
    write_result(traces, result_path, overwrite=True)
    require(read_result(result_path) == traces, "native result roundtrip failed")
    require(not to_ocel(native).valid, "untimed projection invented OCEL time")
    checks["native_case_pipeline"] = {
        "status": "passed",
        "trace_count": 2,
        "unknown_timestamps": 2,
        "discovery": "pix.im.v1",
        "replay_missing": counts.missing,
        "replay_remaining": counts.remaining,
        "result_roundtrip": True,
        "untimed_ocel_projection_rejected": True,
    }
    mxml = fixtures / "workflow.xml"
    mxml.write_text(
        '<WorkflowLog><Process id="p"><ProcessInstance id="source-case">'
        "<AuditTrailEntry><WorkflowModelElement>A</WorkflowModelElement>"
        f"<EventType>complete</EventType><Timestamp>{STAMP}</Timestamp>"
        "</AuditTrailEntry></ProcessInstance></Process></WorkflowLog>",
        encoding="utf-8",
    )
    mxml_log = record("mxml_content_detection", pix.import_log(mxml))
    require(
        case_traces(mxml_log).value.traces[0].events[0].activity == "A",
        "MXML activity changed",
    )

    rows = [
        {"case": "c1", "event": "e1", "activity": "A", "time": STAMP},
        {"case": "c1", "event": "e2", "activity": "B", "time": LATER},
    ]
    mapping = CaseTableMapping("case", "activity", "time", event_id="event")
    table = fixtures / "business.data"
    table.write_bytes(csv_bytes(tuple(rows[0]), [tuple(row.values()) for row in rows]))
    mapped = record(
        "mapped_csv_override", pix.import_log(table, format="csv", mapping=mapping)
    )
    tsv = fixtures / "business.tsv.gz"
    tsv.write_bytes(
        gzip.compress(
            (
                "case\tevent\tactivity\ttime\nc1\te1\tA\t"
                + STAMP
                + "\nc1\te2\tB\t"
                + LATER
                + "\n"
            ).encode(),
            mtime=0,
        )
    )
    mapped_tsv = record("mapped_tsv_gzip", pix.import_log(tsv, mapping=mapping))
    mapped_records = record(
        "mapped_records", pix.import_log(iter(rows), mapping=mapping)
    )
    for candidate in (mapped_tsv, mapped_records):
        require(
            [
                (e.activity, e.time)
                for e in case_traces(candidate).value.traces[0].events
            ]
            == [
                ("A", datetime.fromisoformat(STAMP.replace("Z", "+00:00"))),
                ("B", datetime.fromisoformat(LATER.replace("Z", "+00:00"))),
            ],
            "table representation changed event facts",
        )
    record(
        "unmapped_table", pix.import_log(tsv), expected_code="table_mapping_required"
    )
    object_mapping = OCELTableMapping(
        "event", "activity", "time", (ObjectColumn("case", "Order", "member"),)
    )
    object_log = record(
        "mapped_ocel_records", pix.import_log(rows, mapping=object_mapping)
    )
    require(
        len(object_log.events) == 2 and len(object_log.objects) == 1,
        "OCEL table mapping failed",
    )
    require(
        {edge.qualifier for edge in object_log.e2o} == {"member"},
        "mapped qualifier lost",
    )
    projection = to_ocel(mapped)
    require(
        projection.valid and projection.source_log is mapped,
        "explicit projection lost source sidecar",
    )
    projected = projection.require_ocel()
    for encoding, suffix in (("json", "json"), ("xml", "xml"), ("sqlite", "sqlite")):
        destination = output / f"projected.{suffix}"
        export_ocel(projected, destination, format=encoding, overwrite=True)
        restored = record("projected_ocel20_" + encoding, pix.import_log(destination))
        require(
            canonical_digest(restored) == canonical_digest(projected),
            "projected export roundtrip changed facts",
        )

    require(
        not any(
            name.split(".")[0]
            in {
                "pm4py",
                "ocpa",
                "pandas",
                "networkx",
                "graphviz",
                "openpyxl",
                "pyarrow",
            }
            for name in sys.modules
        ),
        "core import/analysis eagerly loaded an optional or replacement dependency",
    )
    checks["core_optional_imports"] = {"status": "passed", "loaded": []}
    xlsx = fixtures / "business.xlsx"
    if with_extras:
        import openpyxl

        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = "Events"
        worksheet.append(tuple(rows[0]))
        for row in rows:
            worksheet.append(tuple(row.values()))
        workbook.save(xlsx)
        workbook.close()
        excel_log = record(
            "mapped_xlsx", pix.import_log(xlsx, mapping=mapping, sheet="Events")
        )
        require(len(excel_log.traces[0].events) == 2, "XLSX event loss")
        parquet = write_files(fixtures / "parquet-bundle", parquet_files())
        parquet_log = record("bundle_parquet", pix.import_log(parquet))
        require(
            canonical_digest(parquet_log) == reference, "Parquet bundle changed facts"
        )
    else:
        for name in ("openpyxl", "pyarrow"):
            require(
                importlib.util.find_spec(name) is None,
                f"Core-only check requires {name} to be absent",
            )
        xlsx.write_bytes(b"PK\x03\x04")
        record(
            "xlsx_dependency_absent",
            pix.import_log(xlsx, mapping=mapping),
            expected_code="xlsx_dependency_unavailable",
            expected_status=ImportStatus.UNAVAILABLE,
        )
        parquet = write_files(fixtures / "parquet-bundle", bundle_files("parquet"))
        record(
            "parquet_dependency_absent",
            pix.import_log(parquet),
            expected_code="dependency_unavailable",
        )
    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-extras", action="store_true")
    args = parser.parse_args()
    require(bool(sys.flags.isolated), "Run this smoke with python -I")
    require(pix.__version__ == "0.5.0", "Unexpected PIX version")
    output = args.output.resolve()
    checks = smoke(output, args.with_extras)
    script = Path(__file__).resolve()
    evidence = {
        "status": "passed",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "version": pix.__version__,
        "python": sys.version,
        "interpreter": sys.executable,
        "isolated": bool(sys.flags.isolated),
        "working_directory": str(Path.cwd()),
        "installed_pix": str(Path(pix.__file__).resolve()),
        "installed_distributions": sorted(
            {
                f"{dist.metadata['Name']}=={dist.version}"
                for dist in importlib.metadata.distributions()
            }
        ),
        "with_extras": args.with_extras,
        "smoke_script": {
            "path": str(script),
            "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
        },
        "checks": checks,
        "scope": "Installed-package import integration smoke; format conformance and algorithm suites are separate.",
    }
    evidence_path = output / "import-evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "status": "passed",
                "check_count": len(checks),
                "evidence": str(evidence_path),
            }
        )
    )


if __name__ == "__main__":
    main()
