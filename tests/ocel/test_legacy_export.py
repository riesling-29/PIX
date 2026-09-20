import gzip
import json
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventType,
    Object,
    ObjectAttr,
    ObjectType,
    ValueType,
)
from pix.ocel.export import LegacyLossError, export_ocel1_json
from pix.ocel.ingest.formats.legacy import load_json
from pix.ocel.model import OCEL_EPOCH

T = datetime(2026, 9, 18, tzinfo=timezone.utc)


def example():
    return OCEL(
        event_types=(EventType("A"),),
        object_types=(ObjectType("order", (Attribute("state", ValueType.STRING),)),),
        events=(Event("e1", "A", T),),
        objects=(Object("o1", "order", (ObjectAttr("state", "open", OCEL_EPOCH),)),),
        e2o=(E2O("e1", "o1", ""),),
    )


def test_representable_legacy_roundtrip_and_independent_json_shape(tmp_path):
    path = tmp_path / "example.jsonocel.gz"
    result = export_ocel1_json(example(), path)
    assert result.losses == ()
    assert result.source_digest == result.exported_digest
    assert load_json(path)[0].valid
    document = json.loads(gzip.decompress(path.read_bytes()))
    assert document["ocel:events"]["e1"]["ocel:omap"] == ["o1"]
    assert document["ocel:objects"]["o1"]["ocel:ovmap"] == {"state": "open"}


def test_history_and_qualifiers_require_opt_in_and_receipt(tmp_path):
    data = example()
    data = replace(
        data,
        objects=(
            replace(
                data.objects[0],
                attributes=data.objects[0].attributes
                + (ObjectAttr("state", "done", T),),
            ),
        ),
        e2o=(E2O("e1", "o1", "used"),),
    )
    path = tmp_path / "keep.jsonocel"
    path.write_bytes(b"old")
    with pytest.raises(LegacyLossError) as caught:
        export_ocel1_json(data, path, overwrite=True)
    assert {x.code for x in caught.value.losses} >= {
        "object_history_collapsed",
        "qualifier_omitted",
    }
    assert path.read_bytes() == b"old"
    result = export_ocel1_json(data, path, allow_loss=True, overwrite=True)
    assert result.source_digest != result.exported_digest
    assert (
        json.loads(path.read_bytes())["ocel:objects"]["o1"]["ocel:ovmap"]["state"]
        == "done"
    )


def test_unused_event_schema_is_not_silently_lost(tmp_path):
    data = replace(example(), event_types=(EventType("A"), EventType("unused")))
    with pytest.raises(LegacyLossError) as caught:
        export_ocel1_json(data, tmp_path / "loss.jsonocel")
    assert "schema_reconstructed" in {x.code for x in caught.value.losses}
