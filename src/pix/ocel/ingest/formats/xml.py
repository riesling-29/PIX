"""Streaming reader for the explicit PIX no-namespace OCEL 2.0 XML profile.

The four root sections are required exactly once, in any order. Optional
attributes/objects containers occur at most once. Relationships use ``relobj``
or the legacy ``relationship`` alias, consistently across the whole document;
both require object-id and qualifier. This is structural profile validation,
not a claim of conformance to the separately published reference XSD.
"""

from __future__ import annotations

import gzip
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree as ET

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    ValueEncoding,
    map_document,
    schema_failure,
    syntax_failure,
)

XML_PROFILE = "pix.ocel20-xml.no-namespace.v1"


@dataclass(frozen=True)
class _Rule:
    attributes: frozenset[str] = frozenset()
    repeated: frozenset[str] = frozenset()
    required: frozenset[str] = frozenset()
    text_value: bool = False


@dataclass
class _Frame:
    element: ET.Element
    path: tuple[str, ...]
    rule: _Rule
    counts: dict[str, int] = field(default_factory=dict)


def _profile_rules() -> dict[tuple[str, ...], _Rule]:
    sections = frozenset({"object-types", "event-types", "objects", "events"})
    rules = {("log",): _Rule(required=sections)}
    for kind in ("event", "object"):
        type_container = ("log", f"{kind}-types")
        type_path = type_container + (f"{kind}-type",)
        rules[type_container] = _Rule(repeated=frozenset({f"{kind}-type"}))
        rules[type_path] = _Rule(attributes=frozenset({"name"}))
        rules[type_path + ("attributes",)] = _Rule(repeated=frozenset({"attribute"}))
        rules[type_path + ("attributes", "attribute")] = _Rule(
            attributes=frozenset({"name", "type"})
        )
        container = ("log", f"{kind}s")
        record = container + (kind,)
        rules[container] = _Rule(repeated=frozenset({kind}))
        rules[record] = _Rule(
            attributes=frozenset({"id", "type", "time"})
            if kind == "event"
            else frozenset({"id", "type"}),
        )
        rules[record + ("attributes",)] = _Rule(repeated=frozenset({"attribute"}))
        rules[record + ("attributes", "attribute")] = _Rule(
            attributes=frozenset({"name", "time"})
            if kind == "object"
            else frozenset({"name"}),
            text_value=True,
        )
        rules[record + ("objects",)] = _Rule(
            repeated=frozenset({"relobj", "relationship"}),
        )
        for tag in ("relobj", "relationship"):
            rules[record + ("objects", tag)] = _Rule(
                attributes=frozenset({"object-id", "qualifier"})
            )
    return rules


_RULES = _profile_rules()
_RECORDS = {
    ("log", "event-types", "event-type"): "eventTypes",
    ("log", "object-types", "object-type"): "objectTypes",
    ("log", "events", "event"): "events",
    ("log", "objects", "object"): "objects",
}


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Validate every XML path before mapping, releasing completed record trees."""

    document: dict[str, list[object]] = {name: [] for name in _RECORDS.values()}
    stack: list[_Frame] = []
    pending: tuple[_Frame, ET.Element | None] | None = None
    relation_tag: str | None = None
    alias_count = 0
    try:
        with _open_binary(path) as stream:
            for action, element in ET.iterparse(
                stream, events=("start", "end", "start-ns")
            ):
                if action == "start-ns":
                    if element[1]:
                        raise schema_failure(
                            "unsupported_xml_namespace",
                            "The XML profile does not support namespace declarations.",
                            stack[-1].path if stack else (),
                        )
                    continue
                # Tail text may arrive after an element's end event, especially
                # at parser chunk boundaries. Inspect it only at the next event.
                if pending is not None:
                    _finish_tail(*pending)
                    pending = None
                if action == "start":
                    frame = _start_element(element, stack)
                    stack.append(frame)
                    if element.tag in {"relobj", "relationship"}:
                        if relation_tag is not None and relation_tag != element.tag:
                            raise schema_failure(
                                "mixed_xml_relation_dialect",
                                "Use either relobj or relationship consistently.",
                                frame.path,
                            )
                        relation_tag = element.tag
                        alias_count += element.tag == "relationship"
                    continue

                frame = stack.pop()
                _finish_element(frame)
                section = _RECORDS.get(frame.path)
                parent = None
                if section is not None:
                    if section.endswith("Types"):
                        record = _parse_type(element)
                    else:
                        record = _parse_record(element, is_event=section == "events")
                    document[section].append(record)
                    parent = stack[-1].element
                pending = frame, parent
            if pending is not None:
                _finish_tail(*pending)
    except ET.ParseError as exc:
        position = getattr(exc, "position", None)
        at = tuple(str(value) for value in position) if position else ()
        raise syntax_failure("invalid_xml", f"Invalid XML: {exc}.", at) from exc
    except (OSError, EOFError) as exc:
        raise syntax_failure("unreadable_xml", str(exc)) from exc

    result, transformations = map_document(document, encoding=ValueEncoding.XML)
    profile = Transformation(
        code="xml_structural_profile",
        message=f"Validated structural profile {XML_PROFILE}; reference XSD not run.",
    )
    if alias_count:
        transformations += (
            Transformation(
                code="legacy_xml_relationship_alias",
                message="Mapped legacy relationship elements using object-id/qualifier.",
                count=alias_count,
            ),
        )
    return result, transformations + (profile,)


def _start_element(element: ET.Element, stack: list[_Frame]) -> _Frame:
    path = (stack[-1].path if stack else ()) + (element.tag,)
    if "}" in element.tag or any("}" in key for key in element.attrib):
        raise schema_failure(
            "unsupported_xml_namespace", "The XML profile requires no namespaces.", path
        )
    if not stack and element.tag != "log":
        raise schema_failure("invalid_xml_root", "OCEL XML root must be 'log'.", path)
    rule = _RULES.get(path)
    if rule is None:
        raise schema_failure(
            "unexpected_xml_element", "Element is not allowed at this XML path.", path
        )
    if stack:
        parent = stack[-1]
        count = parent.counts.get(element.tag, 0) + 1
        parent.counts[element.tag] = count
        if count > 1 and element.tag not in parent.rule.repeated:
            raise schema_failure(
                "duplicate_xml_container", "This XML child may occur only once.", path
            )
    missing = rule.attributes.difference(element.attrib)
    unexpected = set(element.attrib).difference(rule.attributes)
    if missing:
        raise schema_failure(
            "missing_xml_attribute",
            f"Missing XML attributes: {', '.join(sorted(missing))}.",
            path,
        )
    if unexpected:
        raise schema_failure(
            "unexpected_xml_attribute",
            f"Unexpected XML attributes: {', '.join(sorted(unexpected))}.",
            path,
        )
    return _Frame(element, path, rule)


def _finish_element(frame: _Frame) -> None:
    missing = frame.rule.required.difference(frame.counts)
    if missing:
        raise schema_failure(
            "missing_xml_container",
            f"Missing XML sections: {', '.join(sorted(missing))}.",
            frame.path,
        )
    if not frame.rule.text_value and (frame.element.text or "").strip(" \t\r\n"):
        raise schema_failure(
            "unexpected_xml_text",
            "Only attribute value elements may contain text.",
            frame.path,
        )


def _finish_tail(frame: _Frame, parent: ET.Element | None) -> None:
    if (frame.element.tail or "").strip(" \t\r\n"):
        raise schema_failure(
            "unexpected_xml_text",
            "Mixed text between XML elements is not supported.",
            frame.path,
        )
    if parent is not None:
        parent.remove(frame.element)
        frame.element.clear()


def _parse_type(element: ET.Element) -> dict[str, object]:
    return {
        "name": element.get("name"),
        "attributes": [
            dict(child.attrib) for child in element.findall("attributes/attribute")
        ],
    }


def _parse_record(element: ET.Element, *, is_event: bool) -> dict[str, object]:
    attributes: list[dict[str, object]] = []
    for child in element.findall("attributes/attribute"):
        attribute: dict[str, object] = {
            "name": child.get("name"),
            "value": child.text or "",
        }
        if not is_event:
            attribute["time"] = child.get("time")
        attributes.append(attribute)
    record: dict[str, object] = {
        "id": element.get("id"),
        "type": element.get("type"),
        "attributes": attributes,
        "relationships": [
            {"objectId": child.get("object-id"), "qualifier": child.get("qualifier")}
            for child in element.findall("objects/*")
        ],
    }
    if is_event:
        record["time"] = element.get("time")
    return record


def _open_binary(path: Path) -> BinaryIO:
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rb")
    return path.open("rb")


__all__ = ["XML_PROFILE", "load"]
