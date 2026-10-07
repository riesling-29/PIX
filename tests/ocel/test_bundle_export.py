import io
import json
import zipfile
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pix.ocel import (
    E2O,
    O2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)
from pix.ocel.canonical import canonical_digest
from pix.ocel.export.bundle import export_bundle
from pix.ocel.ingest.formats.bundled import load
from pix.ocel.model import OCEL_EPOCH

T = datetime(2026, 9, 18, tzinfo=timezone.utc)


def example():
    return OCEL(
        event_types=(
            EventType(
                "click / 주문",
                (
                    Attribute("note", ValueType.STRING),
                    Attribute("flag", ValueType.BOOLEAN),
                ),
            ),
            EventType("unused"),
        ),
        object_types=(ObjectType("order", (Attribute("status", ValueType.STRING),)),),
        events=(
            Event(
                "e1",
                "click / 주문",
                T,
                (EventAttr("note", 'a,"b"\nline'), EventAttr("flag", False)),
            ),
            Event("orphan", "click / 주문", T),
        ),
        objects=(
            Object(
                "o1",
                "order",
                (
                    ObjectAttr("status", "new", OCEL_EPOCH),
                    ObjectAttr("status", "done", T),
                ),
            ),
            Object("o2", "order"),
        ),
        e2o=(E2O("e1", "o1", ""), E2O("e1", "o1", "audit")),
        o2o=(O2O("o1", "o2", "related"),),
    )


@pytest.mark.parametrize("storage", ["csv", "parquet"])
def test_bundle_preserves_full_canonical_facts_and_metadata(tmp_path, storage):
    if storage == "parquet":
        pytest.importorskip("pyarrow")
    path = tmp_path / "log.ocel.zip"
    receipt = export_bundle(example(), path, storage=storage)
    assert receipt.source_digest == receipt.roundtrip_digest
    restored, _ = load(path)
    assert canonical_digest(restored.candidate) == canonical_digest(example())
    with zipfile.ZipFile(path) as archive:
        meta = json.loads(archive.read("ocel-meta.json"))
        assert meta["eventTypes"]["click / 주문"]["file"] == f"events/0.{storage}"
        assert len(archive.namelist()) == 7
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        export_bundle(example(), path, storage=storage)
    assert path.read_bytes() == before
    export_bundle(example(), path, storage=storage, overwrite=True)
    assert path.read_bytes() == before


def test_empty_string_requires_parquet_and_preserves_old_destination(tmp_path):
    data = example()
    data = replace(
        data,
        events=(
            replace(data.events[0], attributes=(EventAttr("note", ""),)),
            data.events[1],
        ),
    )
    path = tmp_path / "log.ocel.zip"
    path.write_bytes(b"keep")
    with pytest.raises(ValueError, match="empty string"):
        export_bundle(data, path, overwrite=True)
    assert path.read_bytes() == b"keep"
    pytest.importorskip("pyarrow")
    export_bundle(data, path, storage="parquet", overwrite=True)
    assert canonical_digest(load(path)[0].candidate) == canonical_digest(data)


def test_empty_log_exports_valid_empty_tables(tmp_path):
    path = tmp_path / "empty.ocel.zip"
    export_bundle(OCEL(), path)
    assert load(path)[0].valid
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as archive:
        assert (
            archive.read("e2o.csv").decode()
            == "ocel_event_id,ocel_object_id,ocel_qualifier\n"
        )
