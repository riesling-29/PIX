import copy
import gzip
import hashlib
import json
from datetime import datetime, timezone

import pytest

from pix.ocel import ImportFormat, ImportStatus, import_ocel
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.formats.common import AdapterFailure
from pix.ocel.ingest.formats.legacy import load_json, load_xml
from pix.ocel.model import OCEL_EPOCH, ValueType


def _document():
    return {
        "ocel:global-log": {
            "ocel:version": "1.0",
            "ocel:ordering": "timestamp",
            "ocel:object-types": ["order", "unused"],
            "ocel:attribute-names": ["amount", "status"],
        },
        "ocel:global-event": {"ocel:activity": "__INVALID__"},
        "ocel:global-object": {"ocel:type": "__INVALID__"},
        "ocel:events": {
            "source-e1": {
                "ocel:activity": "create",
                "ocel:timestamp": "2026-09-12T12:00:00+09:00",
                "ocel:omap": ["source-o1"],
                "ocel:vmap": {"amount": 12.5},
            },
            "orphan-event": {
                "ocel:activity": "check",
                "ocel:timestamp": "2026-09-12T03:00:00Z",
                "ocel:omap": [],
            },
        },
        "ocel:objects": {
            "source-o1": {"ocel:type": "order", "ocel:ovmap": {"status": "new"}},
            "orphan-object": {"ocel:type": "order"},
        },
    }


def _json(tmp_path, document=None, *, compressed=False):
    path = tmp_path / ("legacy.jsonocel.gz" if compressed else "legacy.jsonocel")
    content = json.dumps(_document() if document is None else document).encode()
    path.write_bytes(gzip.compress(content) if compressed else content)
    return load_json(path)


def _xml_text(attributes="", object_attributes=""):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<log>
  <global scope="log">
    <string key="version" value="1.0"/>
    <string key="ordering" value="timestamp"/>
    <list key="object-types"><string key="object-type" value="order"/>
      <string key="object-type" value="unused"/></list>
    <list key="attribute-names"/>
  </global>
  <global scope="event"><string key="ocel:activity" value="__INVALID__"/></global>
  <global scope="object"><string key="ocel:type" value="__INVALID__"/></global>
  <events><event>
    <string key="id" value="source-e1"/>
    <string key="activity" value="create"/>
    <date key="timestamp" value="2026-09-12T12:00:00+09:00"/>
    <list key="omap"><string key="object-id" value="source-o1"/></list>
    <list key="vmap">{attributes}</list>
  </event></events>
  <objects><object><string key="id" value="source-o1"/>
    <string key="type" value="order"/><list key="ovmap">{object_attributes}</list>
  </object></objects>
</log>"""


def _xml(tmp_path, text=None, *, compressed=False):
    path = tmp_path / ("legacy.xmlocel.gz" if compressed else "legacy.xmlocel")
    content = (_xml_text() if text is None else text).encode()
    path.write_bytes(gzip.compress(content) if compressed else content)
    return load_xml(path)


@pytest.mark.parametrize("compressed", [False, True])
def test_json_migrates_records_without_dropping_orphans(tmp_path, compressed):
    result, transformations = _json(tmp_path, compressed=compressed)
    assert result.valid
    log = result.candidate
    assert {event.id for event in log.events} == {"source-e1", "orphan-event"}
    assert {obj.id for obj in log.objects} == {"source-o1", "orphan-object"}
    assert {typ.name for typ in log.object_types} == {"order", "unused"}
    assert log.e2o[0].qualifier == ""
    obj = next(obj for obj in log.objects if obj.id == "source-o1")
    assert obj.attributes[0].time == OCEL_EPOCH
    assert obj.attributes[0].value == "new"
    assert log.events[0].time == datetime(2026, 9, 12, 3, tzinfo=timezone.utc)
    assert not log.o2o
    changes = {item.code: item for item in transformations}
    assert changes["legacy_empty_qualifier"].count == 1
    assert changes["legacy_timeless_object_attributes"].count == 1
    assert changes["legacy_type_inference"].count == 2
    assert changes["timezone_to_utc"].count == 1


@pytest.mark.parametrize("compressed", [False, True])
def test_xml_preserves_all_explicit_primitive_types(tmp_path, compressed):
    attributes = """<int key="n" value="9007199254740993"/>
      <float key="f" value="1.25"/><boolean key="b" value="true"/>
      <string key="s" value="2026-01-01T00:00:00Z"/>
      <date key="t" value="2026-01-01T01:00:00+01:00"/>"""
    result, transformations = _xml(
        tmp_path,
        _xml_text(attributes, '<boolean key="b" value="0"/>'),
        compressed=compressed,
    )
    assert result.valid
    values = {attr.name: attr.value for attr in result.candidate.events[0].attributes}
    assert values == {
        "n": 9007199254740993,
        "f": 1.25,
        "b": True,
        "s": "2026-01-01T00:00:00Z",
        "t": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    assert type(values["n"]) is int
    assert type(values["b"]) is bool
    assert result.candidate.objects[0].attributes[0].value is False
    assert result.candidate.objects[0].attributes[0].time == OCEL_EPOCH
    assert {typ.name for typ in result.candidate.object_types} == {"order", "unused"}
    assert "legacy_type_inference" in {item.code for item in transformations}


@pytest.mark.parametrize(
    "value, expected",
    [
        (True, ValueType.BOOLEAN),
        (False, ValueType.BOOLEAN),
        (9007199254740993, ValueType.INTEGER),
        (1.0, ValueType.FLOAT),
        ("", ValueType.STRING),
        ("2026-01-01T00:00:00Z", ValueType.STRING),
    ],
)
def test_json_type_inference_preserves_native_primitive(tmp_path, value, expected):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:vmap"] = {"value": value}
    result, _ = _json(tmp_path, doc)
    event_type = next(
        typ for typ in result.candidate.event_types if typ.name == "create"
    )
    assert event_type.attributes[0].type is expected
    event = next(event for event in result.candidate.events if event.id == "source-e1")
    assert event.attributes[0].value == value
    assert type(event.attributes[0].value) is type(value)


@pytest.mark.parametrize("value", [None, [], {}, [1], {"nested": True}, float("inf")])
def test_json_unsupported_values_fail_instead_of_stringifying(tmp_path, value):
    doc = _document()
    doc["ocel:objects"]["source-o1"]["ocel:ovmap"] = {"value": value}
    with pytest.raises(AdapterFailure) as caught:
        _json(tmp_path, doc)
    assert caught.value.code in {
        "unsupported_legacy_attribute",
        "nonfinite_json_number",
    }


@pytest.mark.parametrize("pair", [(1, 1.0), (True, 1), (1, "1"), ("1", False)])
def test_type_conflicts_within_type_fail_without_coercion(tmp_path, pair):
    doc = _document()
    for identifier, value in zip(("source-o1", "orphan-object"), pair):
        doc["ocel:objects"][identifier]["ocel:ovmap"] = {"same": value}
    with pytest.raises(AdapterFailure) as caught:
        _json(tmp_path, doc)
    assert caught.value.code == "legacy_attribute_type_conflict"


def test_same_attribute_name_can_have_different_types_for_different_types(tmp_path):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:vmap"] = {"shared": 1}
    doc["ocel:events"]["orphan-event"]["ocel:vmap"] = {"shared": "1"}
    assert _json(tmp_path, doc)[0].valid


def test_dangling_reference_preserves_candidate_without_synthetic_object(tmp_path):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:omap"] = ["missing"]
    result, _ = _json(tmp_path, doc)
    assert not result.valid
    assert result.candidate.e2o[0].object == "missing"
    assert {obj.id for obj in result.candidate.objects} == {
        "source-o1",
        "orphan-object",
    }
    assert result.report.errors


@pytest.mark.parametrize(
    "references", [None, "o1", [1], [""], ["source-o1", "source-o1"]]
)
def test_invalid_reference_shapes_and_duplicates_fail(tmp_path, references):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:omap"] = references
    with pytest.raises(AdapterFailure):
        _json(tmp_path, doc)


@pytest.mark.parametrize("field", ["ocel:activity", "ocel:timestamp", "ocel:omap"])
def test_missing_required_event_fields_are_not_invented(tmp_path, field):
    doc = _document()
    doc.pop("ocel:global-event")
    del doc["ocel:events"]["source-e1"][field]
    with pytest.raises(AdapterFailure) as caught:
        _json(tmp_path, doc)
    assert caught.value.code == "missing_required_member"


def test_source_global_defaults_are_applied_and_disclosed(tmp_path):
    doc = _document()
    doc["ocel:global-event"] = {"ocel:activity": "explicit-default"}
    del doc["ocel:events"]["source-e1"]["ocel:activity"]
    result, transformations = _json(tmp_path, doc)
    event = next(event for event in result.candidate.events if event.id == "source-e1")
    assert event.type == "explicit-default"
    assert (
        next(
            item for item in transformations if item.code == "legacy_defaults_applied"
        ).count
        == 1
    )


@pytest.mark.parametrize(
    "metadata",
    [
        {"ocel:version": "2.0"},
        {"ocel:version": []},
        {"ocel:ordering": "arbitrary"},
        {"ocel:object-types": ["order", "order"]},
        {"ocel:object-types": "order"},
        {"ocel:attribute-names": [5]},
        {"ocel:extra": 1},
    ],
)
def test_metadata_is_validated_even_for_empty_logs(tmp_path, metadata):
    with pytest.raises(AdapterFailure):
        _json(
            tmp_path,
            {"ocel:global-log": metadata, "ocel:events": {}, "ocel:objects": {}},
        )


def test_ocpa_single_string_metadata_arrays_are_explicitly_unwrapped(tmp_path):
    doc = _document()
    doc["ocel:global-log"]["ocel:version"] = ["1.0"]
    doc["ocel:global-log"]["ocel:ordering"] = ["timestamp"]
    result, transformations = _json(tmp_path, doc)
    assert result.valid
    assert (
        len(
            [
                item
                for item in transformations
                if item.code == "legacy_metadata_scalar_array"
            ]
        )
        == 2
    )


def test_declared_unused_attribute_is_disclosed_without_inventing_type(tmp_path):
    doc = {
        "ocel:events": {},
        "ocel:objects": {},
        "ocel:global-log": {
            "ocel:attribute-names": ["unused"],
            "ocel:object-types": ["unused-type"],
        },
    }
    result, transformations = _json(tmp_path, doc)
    assert result.valid
    assert result.candidate.object_types[0].name == "unused-type"
    assert not result.candidate.object_types[0].attributes
    assert "legacy_unused_attribute_names" in {item.code for item in transformations}


def test_empty_logs_work_with_missing_optional_metadata(tmp_path):
    json_result, _ = _json(tmp_path, {"ocel:events": {}, "ocel:objects": {}})
    xml_result, _ = _xml(tmp_path, "<log><events/><objects/></log>")
    assert json_result.valid and xml_result.valid
    assert canonical_digest(json_result.candidate) == canonical_digest(
        xml_result.candidate
    )


@pytest.mark.parametrize(
    "source",
    [
        '{"ocel:events":{},"ocel:events":{},"ocel:objects":{}}',
        '{"ocel:events":{"e":{},"e":{}},"ocel:objects":{}}',
        '{"ocel:events":{},"ocel:objects":{"o":{"ocel:ovmap":{"n":1,"n":1}}}}',
    ],
)
def test_duplicate_json_keys_never_overwrite_records(tmp_path, source):
    path = tmp_path / "duplicates.jsonocel"
    path.write_text(source)
    with pytest.raises(AdapterFailure) as caught:
        load_json(path)
    assert caught.value.code == "duplicate_json_member"


def test_inner_json_id_must_match_preserved_outer_id(tmp_path):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:id"] = "other"
    with pytest.raises(AdapterFailure) as caught:
        _json(tmp_path, doc)
    assert caught.value.code == "conflicting_legacy_id"


@pytest.mark.parametrize(
    "mutation, code",
    [
        (
            lambda text: text.replace("<events>", "<events/><events>"),
            "duplicate_xml_member",
        ),
        (
            lambda text: text.replace(
                '<string key="id" value="source-e1"/>',
                '<string key="id" value="source-e1"/><string key="ocel:id" value="source-e1"/>',
            ),
            "duplicate_xml_member",
        ),
        (
            lambda text: text.replace(
                '<list key="vmap"></list>',
                '<list key="vmap"><int key="n" value="1"/><int key="n" value="1"/></list>',
            ),
            "duplicate_xml_member",
        ),
        (
            lambda text: text.replace(
                "</event></events>",
                "</event>"
                + text.split("<events>")[1].split("</events>")[0]
                + "</events>",
            ),
            "duplicate_legacy_id",
        ),
        (
            lambda text: text.replace('<string key="id" value="source-e1"/>', ""),
            "missing_required_member",
        ),
        (
            lambda text: text.replace(
                '<date key="timestamp"', '<string key="timestamp"'
            ),
            "unexpected_xml_element",
        ),
        (
            lambda text: text.replace(
                '<list key="vmap"></list>',
                '<list key="vmap"><list key="nested"/></list>',
            ),
            "unsupported_legacy_attribute",
        ),
        (
            lambda text: text.replace("<log>", '<log xmlns:unused="urn:invalid">'),
            "unsupported_xml_namespace",
        ),
        (
            lambda text: text.replace("<events>", "<events>not-whitespace"),
            "unexpected_xml_text",
        ),
    ],
)
def test_xml_structure_and_duplicate_validation(tmp_path, mutation, code):
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, mutation(_xml_text()))
    assert caught.value.code == code


@pytest.mark.parametrize(
    "tag,value",
    [("int", "1.5"), ("boolean", "True"), ("float", "NaN"), ("date", "nonsense")],
)
def test_invalid_xml_primitive_lexemes_fail(tmp_path, tag, value):
    with pytest.raises(AdapterFailure):
        _xml(tmp_path, _xml_text(f'<{tag} key="value" value="{value}"/>'))


@pytest.mark.parametrize(
    "declaration",
    [
        "<!DOCTYPE log>",
        '<!DOCTYPE log SYSTEM "file:///sensitive">',
        '<!DOCTYPE log [<!ENTITY x "expanded">]>',
    ],
)
@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_xml_dtd_and_entities_are_rejected_before_expansion(
    tmp_path, declaration, encoding
):
    text = f'<?xml version="1.0" encoding="{encoding}"?>{declaration}<log><events/><objects/></log>'
    path = tmp_path / "unsafe.xmlocel"
    path.write_bytes(text.encode(encoding))
    with pytest.raises(AdapterFailure) as caught:
        load_xml(path)
    assert caught.value.code == "forbidden_xml_dtd"


def test_inference_is_deterministic_under_source_order_permutations(tmp_path):
    doc = _document()
    other = copy.deepcopy(doc)
    other["ocel:events"] = dict(reversed(list(other["ocel:events"].items())))
    other["ocel:objects"] = dict(reversed(list(other["ocel:objects"].items())))
    first, _ = _json(tmp_path, doc)
    second, _ = _json(tmp_path, other)
    assert canonical_digest(first.candidate) == canonical_digest(second.candidate)


@pytest.mark.parametrize(
    "loader,name", [(load_json, "legacy.jsonocel.gz"), (load_xml, "legacy.xmlocel.gz")]
)
def test_corrupt_gzip_returns_structured_failure(tmp_path, loader, name):
    path = tmp_path / name
    path.write_bytes(b"not gzip")
    with pytest.raises(AdapterFailure):
        loader(path)


@pytest.mark.parametrize(
    "loader,name", [(load_json, "bad.jsonocel.gz"), (load_xml, "bad.xmlocel.gz")]
)
def test_corrupt_deflate_payload_returns_structured_failure(tmp_path, loader, name):
    path = tmp_path / name
    path.write_bytes(bytes.fromhex("1f8b080000000000000307") + bytes(8))
    with pytest.raises(AdapterFailure) as caught:
        loader(path)
    assert caught.value.code.startswith("unreadable_")


def test_unknown_xml_encoding_returns_structured_failure(tmp_path):
    with pytest.raises(AdapterFailure) as caught:
        _xml(
            tmp_path,
            '<?xml version="1.0" encoding="not-an-encoding"?><log><events/><objects/></log>',
        )
    assert caught.value.code == "invalid_xml_encoding"


def test_xml_float_does_not_accept_python_underscore_syntax(tmp_path):
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, _xml_text('<float key="n" value="1_2"/>'))
    assert caught.value.code == "float_required"


def test_xml_type_conflict_does_not_coerce_date_to_string(tmp_path):
    text = _xml_text('<date key="n" value="2026-01-01T00:00:00Z"/>')
    first = text.split("<events>")[1].split("</events>")[0]
    second = first.replace('value="source-e1"', 'value="other-e"').replace(
        '<date key="n"', '<string key="n"'
    )
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, text.replace("</events>", second + "</events>"))
    assert caught.value.code == "legacy_attribute_type_conflict"


def test_xml_defaults_apply_without_inventing_identifiers(tmp_path):
    text = _xml_text().replace('<string key="activity" value="create"/>', "")
    text = text.replace('value="__INVALID__"', 'value="default-type"')
    result, changes = _xml(tmp_path, text)
    assert result.candidate.events[0].id == "source-e1"
    assert result.candidate.events[0].type == "default-type"
    assert "legacy_defaults_applied" in {item.code for item in changes}


def test_xml_dangling_reference_preserved_without_synthetic_record(tmp_path):
    text = _xml_text().replace(
        '<string key="object-id" value="source-o1"/>',
        '<string key="object-id" value="missing"/>',
    )
    result, _ = _xml(tmp_path, text)
    assert not result.valid
    assert result.candidate.e2o[0].object == "missing"
    assert [obj.id for obj in result.candidate.objects] == ["source-o1"]


def test_json_xml_equivalent_primitive_content_has_same_canonical_digest(tmp_path):
    doc = _document()
    del doc["ocel:events"]["orphan-event"]
    del doc["ocel:objects"]["orphan-object"]
    json_result, _ = _json(tmp_path, doc)
    xml_result, _ = _xml(
        tmp_path,
        _xml_text(
            '<float key="amount" value="12.5"/>', '<string key="status" value="new"/>'
        ),
    )
    assert canonical_digest(json_result.candidate) == canonical_digest(
        xml_result.candidate
    )


def test_xml_predefined_entities_preserve_literal_text(tmp_path):
    result, _ = _xml(tmp_path, _xml_text('<string key="s" value="a&amp;b&lt;c"/>'))
    assert result.candidate.events[0].attributes[0].value == "a&b<c"


def test_xml_gzip_still_rejects_entity_declarations(tmp_path):
    text = '<!DOCTYPE log [<!ENTITY x "value">]><log><events/><objects/></log>'
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, text, compressed=True)
    assert caught.value.code == "forbidden_xml_dtd"


def test_submicrosecond_timestamps_fail_without_truncation(tmp_path):
    doc = _document()
    doc["ocel:events"]["source-e1"]["ocel:timestamp"] = "2026-01-01T00:00:00.0000001Z"
    with pytest.raises(AdapterFailure) as caught:
        _json(tmp_path, doc)
    assert caught.value.code == "timestamp_precision_loss"


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize(
    "kind,expected",
    [("json", ImportFormat.OCEL10_JSON), ("xml", ImportFormat.OCEL10_XML)],
)
def test_public_reader_auto_detects_legacy_and_preserves_source_evidence(
    tmp_path, compressed, kind, expected
):
    path = tmp_path / (f"input.{kind}ocel" + (".gz" if compressed else ""))
    source = (json.dumps(_document()) if kind == "json" else _xml_text()).encode()
    source = gzip.compress(source) if compressed else source
    path.write_bytes(source)
    result = import_ocel(path)
    assert result.status is ImportStatus.VALID
    assert result.format is expected
    assert result.source_sha256 == hashlib.sha256(source).hexdigest()
    assert result.source_size == len(source)
    assert result.canonical_digest is not None
    assert "source-e1" in {event.id for event in result.candidate.events}
    assert "legacy_ocel1_migration" in {item.code for item in result.transformations}


def test_xml_numeric_whitespace_follows_source_datatype_collapse(tmp_path):
    attrs = '<int key="n" value=" 12 "/><boolean key="b" value=" true "/><float key="f" value=" 1.25 "/>'
    result, _ = _xml(tmp_path, _xml_text(attrs))
    assert {
        attr.name: attr.value for attr in result.candidate.events[0].attributes
    } == {
        "n": 12,
        "b": True,
        "f": 1.25,
    }


def test_xml_integer_rejects_unicode_digit_coercion(tmp_path):
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, _xml_text('<int key="n" value="&#xFF11;&#xFF12;"/>'))
    assert caught.value.code == "integer_required"


@pytest.mark.parametrize("value", ["1e-999", "-1e-999", "0.0000001e-999"])
def test_nonzero_json_float_underflow_is_never_silently_zeroed(tmp_path, value):
    path = tmp_path / "underflow.jsonocel"
    path.write_text(
        json.dumps(_document()).replace('"amount": 12.5', f'"amount": {value}')
    )
    with pytest.raises(AdapterFailure) as caught:
        load_json(path)
    assert caught.value.code == "float_precision_loss"


def test_nonzero_xml_float_underflow_is_never_silently_zeroed(tmp_path):
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, _xml_text('<float key="n" value="1e-999"/>'))
    assert caught.value.code == "float_precision_loss"


def test_zero_float_with_extreme_exponent_is_not_underflow(tmp_path):
    result, _ = _xml(tmp_path, _xml_text('<float key="n" value="0e-999"/>'))
    assert result.candidate.events[0].attributes[0].value == 0.0


@pytest.mark.parametrize("value", ["2026-01-01", "2026-W01-1", "2026-01-01X00:00:00Z"])
def test_xml_dates_require_explicit_calendar_clock_without_invented_midnight(
    tmp_path, value
):
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, _xml_text(f'<date key="t" value="{value}"/>'))
    assert caught.value.code == "invalid_timestamp"


def test_xml_event_timestamp_requires_clock(tmp_path):
    text = _xml_text().replace("2026-09-12T12:00:00+09:00", "2026-09-12")
    with pytest.raises(AdapterFailure) as caught:
        _xml(tmp_path, text)
    assert caught.value.code == "invalid_timestamp"
