"""Verified CSV/Parquet ZIP bundles for the existing bundle-1.0 reader profile."""

from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pix._publication import FilePublication, publish_bytes
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.formats.bundled import load
from pix.ocel.model import OCEL, OCEL_EPOCH


@dataclass(frozen=True, slots=True)
class BundleExport:
    publication: FilePublication
    storage: str
    source_digest: str
    roundtrip_digest: str
    profile: str = "pix.ocel20.bundle-1.0.v1"


def _table(columns, attrs, rows, storage):
    if storage == "csv":

        def value(v, column):
            if v is None:
                return ""
            if v == "" and column in attrs:
                raise ValueError(
                    "CSV bundle cannot distinguish an empty string attribute from a missing value; use Parquet"
                )
            if isinstance(v, datetime):
                return (
                    v.astimezone(timezone.utc)
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)

        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows([value(row.get(c), c) for c in columns] for row in rows)
        return stream.getvalue().encode("utf-8")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as error:
        raise ValueError("Parquet export requires pix[parquet]") from error
    kinds = {
        "string": pa.string(),
        "integer": pa.int64(),
        "float": pa.float64(),
        "boolean": pa.bool_(),
        "time": pa.timestamp("us", tz="UTC"),
    }
    schema = pa.schema(
        [
            pa.field(name, kinds[kind], nullable=name in attrs)
            for name, kind in columns.items()
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink, compression="NONE", use_dictionary=False, version="2.6")
    return sink.getvalue().to_pybytes()


def _files(log, storage):
    metadata = {
        "ocelVersion": "2.0",
        "bundleFormatVersion": "1.0",
        "storageFormat": storage,
        "eventTypes": {},
        "objectTypes": {},
        "relations": {"e2o": f"e2o.{storage}", "o2o": f"o2o.{storage}"},
    }
    files = {}
    for index, kind in enumerate(sorted(log.event_types, key=lambda t: t.name)):
        attrs = {
            a.name: a.type.value for a in sorted(kind.attributes, key=lambda a: a.name)
        }
        base = {"ocel_id": "string", "ocel_time": "time"}
        if set(attrs) & set(base):
            raise ValueError("event attribute collides with bundle structural column")
        file = f"events/{index}.{storage}"
        metadata["eventTypes"][kind.name] = {
            "file": file,
            "attributes": [{"name": n, "type": t} for n, t in attrs.items()],
        }
        rows = [
            {
                "ocel_id": e.id,
                "ocel_time": e.time,
                **{a.name: a.value for a in e.attributes},
            }
            for e in sorted(log.events, key=lambda e: e.id)
            if e.type == kind.name
        ]
        files[file] = _table({**base, **attrs}, set(attrs), rows, storage)
    for index, kind in enumerate(sorted(log.object_types, key=lambda t: t.name)):
        attrs = {
            a.name: a.type.value for a in sorted(kind.attributes, key=lambda a: a.name)
        }
        if set(attrs) & {"ocel_id", "ocel_time", "ocel_changed_field"}:
            raise ValueError("object attribute collides with bundle structural column")
        file, changes = f"objects/{index}.{storage}", f"changes/{index}.{storage}"
        metadata["objectTypes"][kind.name] = {
            "file": file,
            "changesFile": changes,
            "attributes": [{"name": n, "type": t} for n, t in attrs.items()],
        }
        initial, updates = [], []
        for obj in sorted(log.objects, key=lambda o: o.id):
            if obj.type != kind.name:
                continue
            initial.append(
                {
                    "ocel_id": obj.id,
                    **{a.name: a.value for a in obj.attributes if a.time == OCEL_EPOCH},
                }
            )
            for a in sorted(obj.attributes, key=lambda a: (a.time, a.name)):
                if a.time != OCEL_EPOCH:
                    updates.append(
                        {
                            "ocel_id": obj.id,
                            "ocel_time": a.time,
                            "ocel_changed_field": a.name,
                            a.name: a.value,
                        }
                    )
        files[file] = _table(
            {"ocel_id": "string", **attrs}, set(attrs), initial, storage
        )
        files[changes] = _table(
            {
                "ocel_id": "string",
                "ocel_time": "time",
                "ocel_changed_field": "string",
                **attrs,
            },
            set(attrs),
            updates,
            storage,
        )
    files[f"e2o.{storage}"] = _table(
        {
            "ocel_event_id": "string",
            "ocel_object_id": "string",
            "ocel_qualifier": "string",
        },
        set(),
        [
            {
                "ocel_event_id": r.event,
                "ocel_object_id": r.object,
                "ocel_qualifier": r.qualifier,
            }
            for r in sorted(log.e2o, key=lambda r: (r.event, r.object, r.qualifier))
        ],
        storage,
    )
    files[f"o2o.{storage}"] = _table(
        {
            "ocel_source_id": "string",
            "ocel_target_id": "string",
            "ocel_qualifier": "string",
        },
        set(),
        [
            {
                "ocel_source_id": r.source,
                "ocel_target_id": r.target,
                "ocel_qualifier": r.qualifier,
            }
            for r in sorted(log.o2o, key=lambda r: (r.source, r.target, r.qualifier))
        ],
        storage,
    )
    files["ocel-meta.json"] = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, indent=2
    ).encode("utf-8")
    return files


def export_bundle(
    log: OCEL, path: str | Path, *, storage: str = "csv", overwrite: bool = False
) -> BundleExport:
    """Serialize ZIP, reimport and compare canonical identity before publication.

    CSV refuses empty string attribute values instead of turning them into null.
    Parquet preserves them but limits integers to signed int64. Type names never
    become filesystem paths. Empty types, histories, orphans and relations survive.
    """
    if not isinstance(log, OCEL):
        raise TypeError("log must be OCEL")
    if storage not in ("csv", "parquet"):
        raise ValueError("storage must be csv or parquet")
    source = canonical_digest(log).identifier
    files = _files(log, storage)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    payload = buffer.getvalue()
    with tempfile.TemporaryDirectory(prefix="pix-bundle-check-") as directory:
        check = Path(directory) / "verify.ocel.zip"
        check.write_bytes(payload)
        restored, _ = load(check)
        restored_digest = canonical_digest(restored.candidate).identifier
        if not restored.valid or source != restored_digest:
            raise ValueError("bundle roundtrip changed canonical facts")
    publication = publish_bytes(
        payload, path, overwrite=overwrite, prefix=".pix-bundle-"
    )
    return BundleExport(publication, storage, source, restored_digest)


__all__ = ["BundleExport", "export_bundle"]
