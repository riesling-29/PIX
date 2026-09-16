"""Loss-explicit OCEL 1 JSON/XML migration into the immutable OCEL 2 model.

The OCEL 1 specification and its no-namespace XML serialization are described
at https://ocel-standard.org/1.0/specification.pdf. JSON native primitive types
and XML typed elements determine schemas independently for each activity/object
type. No strings are guessed to be dates, and conflicting types are not coerced.
Legacy metadata is validated and its omission from canonical data is disclosed.
"""

from __future__ import annotations

import gzip
import json
import math
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree as ET

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    ValueEncoding,
    _map_value,
    _MappingContext,
    _require_keys,
    _require_list,
    _require_mapping,
    _require_nonblank_text,
    _require_text,
    map_document,
    mapping_failure,
    schema_failure,
    syntax_failure,
)
from pix.ocel.ingest.formats.json import (
    _parse_integer,
    _reject_nonfinite_number,
    _unique_members,
)
from pix.ocel.model import OCEL_EPOCH, ValueType

_EVENT_FIELDS = {"ocel:id", "ocel:activity", "ocel:timestamp", "ocel:omap", "ocel:vmap"}
_OBJECT_FIELDS = {"ocel:id", "ocel:type", "ocel:ovmap"}
_LOG_FIELDS = {
    "ocel:version",
    "ocel:ordering",
    "ocel:attribute-names",
    "ocel:object-types",
}
_ROOT_FIELDS = {
    "ocel:global-log",
    "ocel:global-event",
    "ocel:global-object",
    "ocel:events",
    "ocel:objects",
}
_XML_TYPES = {
    "string": "string",
    "date": "time",
    "int": "integer",
    "float": "float",
    "boolean": "boolean",
}
_XML_FLOAT = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_XML_INTEGER = re.compile(r"[+-]?[0-9]+")
_XML_TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:[.,][0-9]+)?(?:Z|[+-][0-9]{2}:?[0-9]{2}"
    r"(?::?[0-9]{2}(?:[.,][0-9]+)?)?)?"
)


@dataclass(frozen=True)
class _XMLValue:
    type: str
    value: str


def load_json(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Load a JSON-OCEL 1 document, optionally compressed with gzip."""
    try:
        with _open_binary(path) as stream:
            document = json.load(
                stream,
                object_pairs_hook=_unique_members,
                parse_int=_parse_integer,
                parse_float=_parse_float,
                parse_constant=_reject_nonfinite_number,
            )
    except UnicodeDecodeError as exc:
        raise syntax_failure("invalid_utf8", "OCEL JSON has invalid encoding.") from exc
    except json.JSONDecodeError as exc:
        raise syntax_failure(
            "invalid_json",
            f"Invalid JSON: {exc.msg}.",
            (str(exc.lineno), str(exc.colno)),
        ) from exc
    except (OSError, EOFError, zlib.error) as exc:
        raise syntax_failure("unreadable_json", str(exc)) from exc
    except RecursionError as exc:
        raise syntax_failure(
            "excessive_json_nesting", "JSON nesting is too deep."
        ) from exc
    return _migrate(document, encoding=ValueEncoding.JSON)


class _SafeTreeBuilder(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        # A parser callback, not a byte-pattern scan: covers UTF-16 and chunk splits.
        raise syntax_failure("forbidden_xml_dtd", "OCEL XML must not declare a DTD.")

    def start_ns(self, prefix: str, uri: str) -> None:
        if uri:
            raise schema_failure(
                "unsupported_xml_namespace", "Legacy XML requires no namespaces."
            )


def load_xml(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Load no-namespace XML-OCEL 1; DTD/entity declarations are forbidden."""
    try:
        with _open_binary(path) as stream:
            root = ET.parse(
                stream, parser=ET.XMLParser(target=_SafeTreeBuilder())
            ).getroot()
    except ET.ParseError as exc:
        raise syntax_failure("invalid_xml", f"Invalid XML: {exc}.") from exc
    except (LookupError, UnicodeError) as exc:
        raise syntax_failure(
            "invalid_xml_encoding", "Unsupported or invalid XML encoding."
        ) from exc
    except (OSError, EOFError, zlib.error) as exc:
        raise syntax_failure("unreadable_xml", str(exc)) from exc
    _xml_shape(root, "log", set(), ("log",))
    document: dict[str, object] = {}
    for child in root:
        at = ("log", child.tag)
        if child.tag == "global":
            _xml_shape(child, "global", {"scope"}, at)
            scope = child.get("scope")
            if scope not in {"log", "event", "object"}:
                raise schema_failure("invalid_xml_scope", "Unknown global scope.", at)
            key = f"ocel:global-{scope}"
            _insert(document, key, _xml_fields(child, scope, at), at)
        elif child.tag in {"events", "objects"}:
            _xml_shape(child, child.tag, set(), at)
            kind = child.tag[:-1]
            records: dict[str, object] = {}
            for index, record in enumerate(child):
                record_at = at + (str(index),)
                _xml_shape(record, kind, set(), record_at)
                values = _xml_fields(record, kind, record_at)
                if "ocel:id" not in values:
                    raise schema_failure(
                        "missing_required_member",
                        "Each XML record requires an id.",
                        record_at,
                    )
                identifier = _require_nonblank_text(
                    values["ocel:id"], record_at + ("id",)
                )
                _insert(
                    records, identifier, values, record_at, code="duplicate_legacy_id"
                )
            _insert(document, f"ocel:{child.tag}", records, at)
        else:
            raise schema_failure("unexpected_xml_element", "Unexpected root child.", at)
    return _migrate(document, encoding=ValueEncoding.XML)


def _open_binary(path: Path) -> BinaryIO:
    return (
        gzip.open(path, "rb") if path.name.lower().endswith(".gz") else path.open("rb")
    )


def _migrate(
    document: object, *, encoding: ValueEncoding
) -> tuple[BuildResult, tuple[Transformation, ...]]:
    root = _require_mapping(document, ())
    _require_keys(
        root, required={"ocel:events", "ocel:objects"}, allowed=_ROOT_FIELDS, at=()
    )
    transformations: list[Transformation] = [
        Transformation(
            code="legacy_ocel1_migration",
            message=(
                "Migrated OCEL 1 records with source identifiers preserved. "
                "No object-object relationships or object change history are asserted; "
                "canonical ordering does not retain source record order."
            ),
        )
    ]
    metadata = _require_mapping(root.get("ocel:global-log", {}), ("ocel:global-log",))
    _require_keys(
        metadata, required=set(), allowed=_LOG_FIELDS, at=("ocel:global-log",)
    )
    metadata = dict(metadata)
    for name in ("ocel:version", "ocel:ordering"):
        if isinstance(metadata.get(name), list):
            values = metadata[name]
            if len(values) != 1:
                raise schema_failure(
                    "invalid_legacy_metadata",
                    "Metadata scalar arrays must have exactly one string.",
                    ("ocel:global-log", name),
                )
            metadata[name] = _require_text(values[0], ("ocel:global-log", name, "0"))
            transformations.append(
                Transformation(
                    code="legacy_metadata_scalar_array",
                    message="Unwrapped an OCPA-compatible single-string metadata array.",
                    at=("ocel:global-log", name),
                    count=1,
                )
            )
    if "ocel:version" in metadata:
        version = _require_text(
            metadata["ocel:version"], ("ocel:global-log", "ocel:version")
        )
        if version not in {"1.0", "0.1"}:
            raise schema_failure(
                "unsupported_legacy_version", "Expected OCEL 1.0 or 0.1 metadata."
            )
    if "ocel:ordering" in metadata:
        ordering = _require_text(
            metadata["ocel:ordering"], ("ocel:global-log", "ocel:ordering")
        )
        if ordering != "timestamp":
            raise mapping_failure(
                "unsupported_legacy_ordering",
                "Only timestamp ordering can be migrated.",
            )
    declared_types = _names(
        metadata.get("ocel:object-types", []), ("ocel:global-log", "ocel:object-types")
    )
    declared_attributes = _names(
        metadata.get("ocel:attribute-names", []),
        ("ocel:global-log", "ocel:attribute-names"),
    )
    defaults: dict[str, dict[str, object]] = {}
    for kind, allowed in (("event", _EVENT_FIELDS), ("object", _OBJECT_FIELDS)):
        at = (f"ocel:global-{kind}",)
        values = _require_mapping(root.get(at[0], {}), at)
        _require_keys(values, required=set(), allowed=allowed, at=at)
        _validate_defaults(values, at)
        defaults[kind] = values
    for name in sorted(
        root.keys() & {"ocel:global-log", "ocel:global-event", "ocel:global-object"}
    ):
        transformations.append(
            Transformation(
                code="legacy_metadata_not_preserved",
                message=(
                    "Validated legacy metadata/default declarations. Declared object "
                    "types are retained and applicable defaults materialized; the original "
                    "catalogue, version, ordering and defaults are not canonical data."
                ),
                at=(name,),
            )
        )

    schemas: dict[str, dict[str, dict[str, str]]] = {
        "event": {},
        "object": {name: {} for name in declared_types},
    }
    output: dict[str, list[dict[str, object]]] = {"events": [], "objects": []}
    relation_count = 0
    object_attribute_count = 0
    default_count = 0
    observed_names: set[str] = set()
    for kind, allowed in (("event", _EVENT_FIELDS), ("object", _OBJECT_FIELDS)):
        section = f"ocel:{kind}s"
        records = _require_mapping(root[section], (section,))
        for identifier, raw in records.items():
            at = (section, identifier)
            _require_nonblank_text(identifier, at)
            record = _require_mapping(raw, at)
            _require_keys(record, required=set(), allowed=allowed, at=at)
            if "ocel:id" in record and record["ocel:id"] != identifier:
                raise schema_failure(
                    "conflicting_legacy_id", "Record id disagrees with its map key.", at
                )
            values = dict(record)
            # Source IDs always come from record keys, never a global id default.
            for name, value in defaults[kind].items():
                if name != "ocel:id" and name not in values:
                    values[name] = value
                    default_count += 1
            type_key = "ocel:activity" if kind == "event" else "ocel:type"
            required = (
                {type_key, "ocel:timestamp", "ocel:omap"}
                if kind == "event"
                else {type_key}
            )
            _require_keys(values, required=required, allowed=allowed, at=at)
            type_name = _require_nonblank_text(values[type_key], at + (type_key,))
            schema = schemas[kind].setdefault(type_name, {})
            attribute_key = "ocel:vmap" if kind == "event" else "ocel:ovmap"
            attributes = _require_mapping(
                values.get(attribute_key, {}), at + (attribute_key,)
            )
            mapped_attributes: list[dict[str, object]] = []
            for name, raw_value in attributes.items():
                attr_at = at + (attribute_key, name)
                _require_nonblank_text(name, attr_at)
                value_type, value = _attribute(raw_value, attr_at)
                previous = schema.get(name)
                if previous is not None and previous != value_type:
                    raise mapping_failure(
                        "legacy_attribute_type_conflict",
                        f"{kind.title()} type '{type_name}' attribute '{name}' has "
                        f"both {previous} and {value_type} values; no coercion is applied.",
                        attr_at,
                    )
                schema[name] = value_type
                observed_names.add(name)
                mapped: dict[str, object] = {"name": name, "value": value}
                if kind == "object":
                    mapped["time"] = OCEL_EPOCH.isoformat()
                    object_attribute_count += 1
                mapped_attributes.append(mapped)
            mapped_record: dict[str, object] = {
                "id": identifier,
                "type": type_name,
                "attributes": mapped_attributes,
            }
            if kind == "event":
                mapped_record["time"] = values["ocel:timestamp"]
                references = _names(values["ocel:omap"], at + ("ocel:omap",))
                mapped_record["relationships"] = [
                    {"objectId": name, "qualifier": ""} for name in references
                ]
                relation_count += len(references)
            output[f"{kind}s"].append(mapped_record)
    for kind in ("event", "object"):
        output[f"{kind}Types"] = [
            {
                "name": name,
                "attributes": [
                    {"name": attr, "type": value_type}
                    for attr, value_type in sorted(schema.items())
                ],
            }
            for name, schema in sorted(schemas[kind].items())
        ]
    transformations.append(
        Transformation(
            code="legacy_type_inference",
            message=(
                "Inferred schemas per activity/object type from JSON native primitive "
                "types or XML typed elements; strings remain strings and mixed types "
                "are rejected without numeric widening."
            ),
            count=sum(
                len(schema) for group in schemas.values() for schema in group.values()
            ),
        )
    )
    for code, count, message in (
        (
            "legacy_empty_qualifier",
            relation_count,
            "Mapped unqualified OCEL 1 event-object links with empty qualifiers; no role is inferred.",
        ),
        (
            "legacy_timeless_object_attributes",
            object_attribute_count,
            "Mapped timeless OCEL 1 object attributes to OCEL_EPOCH (1970-01-01T00:00:00Z); this is not an observed change time.",
        ),
        (
            "legacy_defaults_applied",
            default_count,
            "Materialized explicitly declared global defaults for missing record fields.",
        ),
        (
            "legacy_unused_attribute_names",
            len(set(declared_attributes) - observed_names),
            "Unused global attribute names have no type/owner and cannot be represented in canonical schemas.",
        ),
    ):
        if count:
            transformations.append(
                Transformation(code=code, count=count, message=message)
            )
    result, mapped_transformations = map_document(output, encoding=encoding)
    return result, tuple(transformations) + mapped_transformations


def _validate_defaults(values: dict[str, object], at: tuple[str, ...]) -> None:
    for key, value in values.items():
        if key in {"ocel:vmap", "ocel:ovmap"}:
            for name, attribute in _require_mapping(value, at + (key,)).items():
                _require_nonblank_text(name, at + (key, name))
                _attribute(attribute, at + (key, name))
        elif key == "ocel:omap":
            _names(value, at + (key,))
        else:
            # Placeholder defaults such as __INVALID__ are valid metadata strings;
            # timestamp parsing is required if the default is actually used.
            _require_text(value, at + (key,))


def _attribute(value: object, at: tuple[str, ...]) -> tuple[str, object]:
    if isinstance(value, _XMLValue):
        text = value.value if value.type == "string" else value.value.strip(" \t\r\n")
        if value.type == "integer" and _XML_INTEGER.fullmatch(text) is None:
            raise mapping_failure(
                "integer_required", "Expected an ASCII XML integer value.", at
            )
        if value.type == "float" and _XML_FLOAT.fullmatch(text) is None:
            raise mapping_failure(
                "float_required", "Expected a finite XML double value.", at
            )
        if value.type == "time":
            _xml_time(text, at)
        mapped = _map_value(
            text, ValueType(value.type), at, _MappingContext(ValueEncoding.XML)
        )
        if value.type == "float":
            _reject_underflow(text, mapped, at)
        return value.type, text
    if isinstance(value, bool):
        return "boolean", value
    if isinstance(value, int):
        return "integer", value
    if isinstance(value, float) and math.isfinite(value):
        return "float", value
    if isinstance(value, str):
        return "string", _require_text(value, at)
    raise mapping_failure(
        "unsupported_legacy_attribute",
        "Legacy attributes must be finite primitive non-null values; nested values "
        "cannot be represented without loss.",
        at,
    )


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise mapping_failure(
            "float_out_of_range", "JSON float is outside finite binary64 range."
        )
    _reject_underflow(text, value, ())
    return value


def _reject_underflow(text: str, value: object, at: tuple[str, ...]) -> None:
    mantissa = re.split("[eE]", text, maxsplit=1)[0]
    if value == 0 and any(digit in "123456789" for digit in mantissa):
        raise mapping_failure(
            "float_precision_loss",
            "A nonzero source float would underflow to zero.",
            at,
        )


def _xml_time(text: str, at: tuple[str, ...]) -> None:
    if _XML_TIME.fullmatch(text) is None:
        raise mapping_failure(
            "invalid_timestamp",
            "XML dates require a calendar date and explicit clock time.",
            at,
        )


def _names(value: object, at: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for index, raw in enumerate(_require_list(value, at)):
        name = _require_nonblank_text(raw, at + (str(index),))
        if name in seen:
            raise schema_failure(
                "duplicate_legacy_list_value",
                "Repeated set member.",
                at + (str(index),),
            )
        seen.add(name)
        result.append(name)
    return result


def _insert(
    target: dict[str, object],
    key: str,
    value: object,
    at: tuple[str, ...],
    *,
    code: str = "duplicate_xml_member",
) -> None:
    if key in target:
        raise schema_failure(code, f"Repeated member '{key}'.", at)
    target[key] = value


def _xml_shape(
    element: ET.Element, tag: str, attributes: set[str], at: tuple[str, ...]
) -> None:
    if element.tag != tag:
        raise schema_failure("unexpected_xml_element", f"Expected '{tag}'.", at)
    if set(element.attrib) != attributes:
        raise schema_failure(
            "invalid_xml_attributes",
            f"Expected XML attributes {sorted(attributes)}.",
            at,
        )
    if (element.text or "").strip() or (element.tail or "").strip():
        raise schema_failure(
            "unexpected_xml_text", "XML values must use the value attribute.", at
        )


def _xml_fields(
    element: ET.Element, kind: str, at: tuple[str, ...]
) -> dict[str, object]:
    result: dict[str, object] = {}
    allowed = (
        _LOG_FIELDS
        if kind == "log"
        else _EVENT_FIELDS
        if kind == "event"
        else _OBJECT_FIELDS
    )
    for child in element:
        raw_key = child.get("key", "")
        key = raw_key if raw_key.startswith("ocel:") else f"ocel:{raw_key}"
        child_at = at + (raw_key,)
        if key not in allowed:
            raise schema_failure(
                "unexpected_legacy_field", f"Unsupported field '{raw_key}'.", child_at
            )
        if key in {"ocel:vmap", "ocel:ovmap"}:
            value: object = _xml_attributes(child, child_at)
        elif key in {"ocel:omap", "ocel:object-types", "ocel:attribute-names"}:
            _xml_shape(child, "list", {"key"}, child_at)
            item_key = {
                "ocel:omap": "object-id",
                "ocel:object-types": "object-type",
                "ocel:attribute-names": "attribute-name",
            }[key]
            names: list[str] = []
            for index, item in enumerate(child):
                item_at = child_at + (str(index),)
                _xml_shape(item, "string", {"key", "value"}, item_at)
                if len(item) or item.get("key") not in {item_key, f"ocel:{item_key}"}:
                    raise schema_failure(
                        "invalid_xml_list_item", "Unexpected list entry shape.", item_at
                    )
                names.append(item.attrib["value"])
            value = names
        else:
            expected = "date" if key == "ocel:timestamp" else "string"
            if (
                key == "ocel:timestamp"
                and element.tag == "global"
                and child.tag == "string"
            ):
                expected = "string"
            _xml_shape(child, expected, {"key", "value"}, child_at)
            if len(child):
                raise schema_failure(
                    "unexpected_xml_element",
                    "Scalar fields cannot contain children.",
                    child_at,
                )
            value = child.attrib["value"]
            if expected == "date":
                value = value.strip(" \t\r\n")
                _xml_time(value, child_at)
        _insert(result, key, value, child_at)
    return result


def _xml_attributes(element: ET.Element, at: tuple[str, ...]) -> dict[str, object]:
    if element.tag not in {"list", "map"}:
        raise schema_failure(
            "invalid_xml_attribute_map", "Expected an attribute list/map.", at
        )
    _xml_shape(element, element.tag, {"key"}, at)
    result: dict[str, object] = {}
    for child in element:
        name = child.get("key", "")
        attr_at = at + (name,)
        if child.tag not in _XML_TYPES or len(child):
            raise mapping_failure(
                "unsupported_legacy_attribute",
                "Expected a primitive typed XML attribute.",
                attr_at,
            )
        _xml_shape(child, child.tag, {"key", "value"}, attr_at)
        _insert(
            result,
            name,
            _XMLValue(_XML_TYPES[child.tag], child.attrib["value"]),
            attr_at,
        )
    return result


__all__ = ["load_json", "load_xml"]
