"""Immutable case-log facts, independently of analysis eligibility.

IDs identify source positions/entities, never an inferred process identity.
Attributes preserve type, original lexical values and ordered nested structure.
Global defaults are resolved on request; they never overwrite recorded facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

CaseValue: TypeAlias = str | datetime | int | float | bool | None


def _text(value: object, field: str, *, blank: bool = False) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be str")
    if not blank and not value.strip():
        raise ValueError(f"{field} must not be blank")


def _tuple(value: object, item_type: type, field: str) -> None:
    if not isinstance(value, tuple) or not all(isinstance(x, item_type) for x in value):
        raise TypeError(f"{field} must be a tuple of {item_type.__name__}")


@dataclass(frozen=True, slots=True)
class CaseAttribute:
    """An XES-shaped value; list values and nested metadata remain distinct.

    ``null`` is available to tabular adapters, but is not an XES XML type.
    Non-finite doubles are valid stored XES values, ineligible for OCEL.
    """

    key: str
    type: str
    value: CaseValue = None
    children: tuple[CaseAttribute, ...] = ()
    values: tuple[CaseAttribute, ...] = ()
    lexical: str | None = None

    def __post_init__(self) -> None:
        _text(self.key, "attribute key", blank=True)
        _tuple(self.children, CaseAttribute, "children")
        _tuple(self.values, CaseAttribute, "values")
        kinds = {
            "string": str,
            "id": str,
            "date": datetime,
            "int": int,
            "float": float,
            "boolean": bool,
            "list": type(None),
            "container": type(None),
            "null": type(None),
        }
        if self.type not in kinds:
            raise ValueError(f"unsupported case attribute type {self.type!r}")
        if type(self.value) is not kinds[self.type]:
            raise TypeError(
                f"{self.type} attribute requires {kinds[self.type].__name__}"
            )
        if self.type != "list" and self.values:
            raise ValueError("only list attributes may contain ordered values")
        if self.lexical is not None:
            _text(self.lexical, "lexical", blank=True)


def find_attribute(
    attributes: tuple[CaseAttribute, ...], key: str
) -> CaseAttribute | None:
    """Return an unambiguous attribute without choosing among duplicate keys."""
    found = tuple(attribute for attribute in attributes if attribute.key == key)
    if len(found) > 1:
        raise ValueError(f"ambiguous attribute key {key!r}")
    return found[0] if found else None


@dataclass(frozen=True, slots=True)
class CaseEvent:
    id: str
    attributes: tuple[CaseAttribute, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "event id")
        _tuple(self.attributes, CaseAttribute, "event attributes")

    def attribute(self, key: str) -> CaseAttribute | None:
        return find_attribute(self.attributes, key)

    @property
    def activity(self) -> str | None:
        attribute = self.attribute("concept:name")
        return (
            attribute.value
            if attribute is not None and attribute.type == "string"
            else None
        )

    @property
    def timestamp(self) -> datetime | None:
        attribute = self.attribute("time:timestamp")
        return (
            attribute.value
            if attribute is not None and attribute.type == "date"
            else None
        )


@dataclass(frozen=True, slots=True)
class CaseTrace:
    id: str
    events: tuple[CaseEvent, ...] = ()
    attributes: tuple[CaseAttribute, ...] = ()

    def __post_init__(self) -> None:
        _text(self.id, "trace id")
        _tuple(self.events, CaseEvent, "events")
        _tuple(self.attributes, CaseAttribute, "trace attributes")

    def attribute(self, key: str) -> CaseAttribute | None:
        return find_attribute(self.attributes, key)


@dataclass(frozen=True, slots=True)
class CaseGlobal:
    scope: str
    attributes: tuple[CaseAttribute, ...] = ()

    def __post_init__(self) -> None:
        if self.scope not in ("trace", "event"):
            raise ValueError("global scope must be trace or event")
        _tuple(self.attributes, CaseAttribute, "global attributes")


@dataclass(frozen=True, slots=True)
class CaseExtension:
    name: str
    prefix: str
    uri: str

    def __post_init__(self) -> None:
        for field in ("name", "prefix", "uri"):
            _text(getattr(self, field), field)


@dataclass(frozen=True, slots=True)
class CaseClassifier:
    name: str
    keys: tuple[str, ...]
    scope: str = "event"
    lexical: str | None = None

    def __post_init__(self) -> None:
        _text(self.name, "classifier name")
        _tuple(self.keys, str, "classifier keys")
        if not self.keys or any(not key for key in self.keys):
            raise ValueError("classifier requires nonempty keys")
        if self.scope not in ("event", "trace"):
            raise ValueError("classifier scope must be trace or event")
        if self.lexical is not None:
            _text(self.lexical, "classifier lexical keys", blank=True)


@dataclass(frozen=True, slots=True)
class CaseSource:
    source: str
    format: str
    sha256: str
    size: int

    def __post_init__(self) -> None:
        _text(self.source, "source")
        _text(self.format, "format")
        if len(self.sha256) != 64 or any(
            x not in "0123456789abcdef" for x in self.sha256
        ):
            raise ValueError("source sha256 must be lowercase hexadecimal SHA-256")
        if type(self.size) is not int or self.size < 0:
            raise ValueError("source size must be nonnegative int")


@dataclass(frozen=True, slots=True)
class CaseLog:
    traces: tuple[CaseTrace, ...] = ()
    attributes: tuple[CaseAttribute, ...] = ()
    globals: tuple[CaseGlobal, ...] = ()
    extensions: tuple[CaseExtension, ...] = ()
    classifiers: tuple[CaseClassifier, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    source: CaseSource | None = None

    def __post_init__(self) -> None:
        for field, item_type in (
            ("traces", CaseTrace),
            ("attributes", CaseAttribute),
            ("globals", CaseGlobal),
            ("extensions", CaseExtension),
            ("classifiers", CaseClassifier),
            ("metadata", tuple),
        ):
            _tuple(getattr(self, field), item_type, field)
        if any(
            len(pair) != 2 or not all(isinstance(x, str) for x in pair)
            for pair in self.metadata
        ):
            raise TypeError("metadata must contain string key/value pairs")
        if self.source is not None and not isinstance(self.source, CaseSource):
            raise TypeError("source must be CaseSource or None")
        ids = tuple(trace.id for trace in self.traces)
        event_ids = tuple(event.id for trace in self.traces for event in trace.events)
        if len(set(ids)) != len(ids) or len(set(event_ids)) != len(event_ids):
            raise ValueError("trace and event internal identities must each be unique")

    def effective_attributes(
        self, item: CaseTrace | CaseEvent
    ) -> tuple[CaseAttribute, ...]:
        """Resolve defaults without inserting them into the recorded hierarchy."""
        if not isinstance(item, (CaseTrace, CaseEvent)):
            raise TypeError("item must be CaseTrace or CaseEvent")
        scope = "trace" if isinstance(item, CaseTrace) else "event"
        defaults = tuple(
            a for g in self.globals if g.scope == scope for a in g.attributes
        )
        for key in {a.key for a in (*defaults, *item.attributes)}:
            find_attribute(defaults, key)
            find_attribute(item.attributes, key)
        recorded = {a.key for a in item.attributes}
        return tuple(a for a in defaults if a.key not in recorded) + item.attributes

    def attribute(self, item: CaseTrace | CaseEvent, key: str) -> CaseAttribute | None:
        return find_attribute(self.effective_attributes(item), key)

    def describe(self) -> dict[str, object]:
        return {
            "kind": "case_log",
            "traceCount": len(self.traces),
            "eventCount": sum(len(trace.events) for trace in self.traces),
            "emptyTraceCount": sum(not trace.events for trace in self.traces),
            "sourceFormat": self.source.format if self.source else None,
        }

    def summary(self) -> str:
        return f"CaseLog(traces={len(self.traces)}, events={sum(len(t.events) for t in self.traces)})"
