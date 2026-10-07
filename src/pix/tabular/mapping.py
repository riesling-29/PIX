"""Immutable, explicit semantic mappings for flat event tables.

No column names, object types, relation roles, null markers, or list encodings
are inferred. ``ObjectColumn.attributes`` describe static initial values (OCEL
time zero); conflicting assignments are rejected.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass


def _text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonblank text")


def _choice(value: str, field: str, choices: tuple[str, ...]) -> None:
    if value not in choices:
        raise ValueError(f"{field} must be one of {choices}")


@dataclass(frozen=True, slots=True)
class AttributeColumn:
    """Map a named column to a typed attribute, with explicit absence policy.

    ``missing`` handles absent record keys; ``null`` handles Python None and
    exact ``null_values`` tokens. Null preservation is available only in native
    case logs; OCEL has no null primitive. Empty strings are ordinary strings
    unless explicitly listed in ``null_values``.
    """

    column: str
    type: str
    name: str | None = None
    null_values: tuple[str, ...] = ()
    missing: str = "error"
    null: str = "error"

    def __post_init__(self) -> None:
        _text(self.column, "column")
        if self.name is not None:
            _text(self.name, "name")
        aliases = {"int": "integer", "date": "time", "bool": "boolean"}
        object.__setattr__(self, "type", aliases.get(self.type, self.type))
        _choice(self.type, "type", ("string", "integer", "float", "boolean", "time"))
        _choice(self.missing, "missing", ("error", "omit"))
        _choice(self.null, "null", ("error", "omit", "preserve"))
        if not isinstance(self.null_values, tuple) or not all(
            isinstance(value, str) for value in self.null_values
        ):
            raise TypeError("null_values must be a tuple of strings")

    @property
    def key(self) -> str:
        return self.column if self.name is None else self.name


def _attributes(value: object, field: str, reserved: tuple[str, ...] = ()) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, AttributeColumn) for item in value
    ):
        raise TypeError(f"{field} must be a tuple of AttributeColumn")
    names = [item.key for item in value]
    if len(names) != len(set(names)) or set(names).intersection(reserved):
        raise ValueError(f"{field} has duplicate or reserved attribute names")


@dataclass(frozen=True, slots=True)
class ObjectColumn:
    """Map object IDs with one explicitly declared type and relation qualifier.

    ``encoding`` is scalar, separator, or json. A separator is required only
    for separator encoding. JSON encoding also accepts native lists/tuples in
    record inputs. ``id_policy='integer'`` explicitly permits integer numeric
    cells; the default accepts only text and preserves leading zeroes.
    """

    column: str
    object_type: str
    qualifier: str
    encoding: str = "scalar"
    separator: str | None = None
    id_policy: str = "text"
    null_values: tuple[str, ...] = ()
    attributes: tuple[AttributeColumn, ...] = ()

    def __post_init__(self) -> None:
        _text(self.column, "column")
        _text(self.object_type, "object_type")
        if not isinstance(self.qualifier, str):
            raise TypeError(
                "qualifier must be a string (including an explicit empty role)"
            )
        _choice(self.encoding, "encoding", ("scalar", "separator", "json"))
        _choice(self.id_policy, "id_policy", ("text", "integer"))
        if self.encoding == "separator":
            if not isinstance(self.separator, str) or not self.separator:
                raise ValueError("separator encoding requires a nonempty separator")
        elif self.separator is not None:
            raise ValueError("separator is only valid for separator encoding")
        if not isinstance(self.null_values, tuple) or not all(
            isinstance(value, str) for value in self.null_values
        ):
            raise TypeError("null_values must be a tuple of strings")
        _attributes(self.attributes, "attributes")
        if any(attr.null == "preserve" for attr in self.attributes):
            raise ValueError("OCEL cannot preserve null attribute values")


@dataclass(frozen=True, slots=True)
class CaseTableMapping:
    """Map one row per case event; case order is first source occurrence.

    Event order is source order unless ``order='timestamp'`` explicitly opts
    into stable timestamp sorting (ties retain source order). When no event ID
    column is supplied, positional internal IDs are disclosed in provenance;
    they do not claim to be source event identities.
    """

    case_id: str
    activity: str
    timestamp: str | None = None
    event_id: str | None = None
    case_attributes: tuple[AttributeColumn, ...] = ()
    event_attributes: tuple[AttributeColumn, ...] = ()
    order: str = "source"
    id_policy: str = "text"
    timestamp_policy: str = "require_timezone"

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _text(self.activity, "activity")
        for field in ("timestamp", "event_id"):
            value = getattr(self, field)
            if value is not None:
                _text(value, field)
        _attributes(self.case_attributes, "case_attributes", ("concept:name",))
        _attributes(
            self.event_attributes,
            "event_attributes",
            ("concept:name", "time:timestamp", "identity:id"),
        )
        _choice(self.order, "order", ("source", "timestamp"))
        _choice(self.id_policy, "id_policy", ("text", "integer"))
        _choice(
            self.timestamp_policy,
            "timestamp_policy",
            ("require_timezone", "assume_utc"),
        )
        if self.order == "timestamp" and self.timestamp is None:
            raise ValueError("timestamp order requires a timestamp column")

    @property
    def fingerprint(self) -> str:
        return mapping_fingerprint(self)


@dataclass(frozen=True, slots=True)
class OCELTableMapping:
    """Map repeated flat event rows to qualified OCEL event/object relations.

    Repeated event IDs group only if activity, timestamp and event attributes
    agree. Repeated E2O facts fail unless ``duplicate_relations='deduplicate'``
    explicitly opts into a disclosed removal. Different qualifiers survive.
    """

    event_id: str
    activity: str
    timestamp: str
    objects: tuple[ObjectColumn, ...]
    event_attributes: tuple[AttributeColumn, ...] = ()
    id_policy: str = "text"
    timestamp_policy: str = "require_timezone"
    duplicate_relations: str = "error"

    def __post_init__(self) -> None:
        for field in ("event_id", "activity", "timestamp"):
            _text(getattr(self, field), field)
        if not isinstance(self.objects, tuple) or not all(
            isinstance(value, ObjectColumn) for value in self.objects
        ):
            raise TypeError("objects must be a tuple of ObjectColumn")
        _attributes(self.event_attributes, "event_attributes")
        if any(attr.null == "preserve" for attr in self.event_attributes):
            raise ValueError("OCEL cannot preserve null attribute values")
        _choice(self.id_policy, "id_policy", ("text", "integer"))
        _choice(
            self.timestamp_policy,
            "timestamp_policy",
            ("require_timezone", "assume_utc"),
        )
        _choice(
            self.duplicate_relations, "duplicate_relations", ("error", "deduplicate")
        )
        schemas: dict[str, dict[str, str]] = {}
        for obj in self.objects:
            schema = schemas.setdefault(obj.object_type, {})
            for attr in obj.attributes:
                if attr.key in schema and schema[attr.key] != attr.type:
                    raise ValueError(
                        "Conflicting attribute types for the same object type"
                    )
                schema[attr.key] = attr.type

    @property
    def fingerprint(self) -> str:
        return mapping_fingerprint(self)


def mapping_fingerprint(mapping: CaseTableMapping | OCELTableMapping) -> str:
    """SHA-256 of versioned semantic configuration, independent of data rows."""
    if not isinstance(mapping, (CaseTableMapping, OCELTableMapping)):
        raise TypeError("mapping must be CaseTableMapping or OCELTableMapping")
    document = {
        "version": 1,
        "kind": type(mapping).__name__,
        "mapping": asdict(mapping),
    }
    data = json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


__all__ = [
    "AttributeColumn",
    "CaseTableMapping",
    "ObjectColumn",
    "OCELTableMapping",
    "mapping_fingerprint",
]
