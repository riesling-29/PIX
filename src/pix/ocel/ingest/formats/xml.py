"""Streaming OCEL 2.0 XML adapter."""

from __future__ import annotations

import gzip
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


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Parse and map one OCEL 2.0 XML file with bounded tree memory."""

    document: dict[str, list[object]] = {
        "eventTypes": [],
        "objectTypes": [],
        "events": [],
        "objects": [],
    }
    root_seen = False
    try:
        with _open_binary(path) as stream:
            for action, element in ET.iterparse(
                stream,
                events=("start", "end"),
            ):
                if not root_seen:
                    root_seen = True
                    if _local_name(element.tag) != "log":
                        raise schema_failure(
                            "invalid_xml_root",
                            "OCEL XML root element must be 'log'.",
                        )
                if action != "end":
                    continue
                tag = _local_name(element.tag)
                if tag == "event-type":
                    document["eventTypes"].append(_parse_type(element))
                    element.clear()
                elif tag == "object-type":
                    document["objectTypes"].append(_parse_type(element))
                    element.clear()
                elif tag == "event":
                    document["events"].append(_parse_event(element))
                    element.clear()
                elif tag == "object":
                    document["objects"].append(_parse_object(element))
                    element.clear()
    except ET.ParseError as exc:
        position = getattr(exc, "position", None)
        at = tuple(str(value) for value in position) if position else ()
        raise syntax_failure("invalid_xml", f"Invalid XML: {exc}.", at) from exc
    except (OSError, EOFError) as exc:
        raise syntax_failure("unreadable_xml", str(exc)) from exc

    return map_document(document, encoding=ValueEncoding.XML)


def _parse_type(element: ET.Element) -> dict[str, object]:
    attributes = []
    for child in element.iter():
        if _local_name(child.tag) != "attribute":
            continue
        attributes.append(
            {"name": child.get("name"), "type": child.get("type")}
        )
    return {"name": element.get("name"), "attributes": attributes}


def _parse_event(element: ET.Element) -> dict[str, object]:
    return {
        "id": element.get("id"),
        "type": element.get("type"),
        "time": element.get("time"),
        "attributes": _parse_attributes(element, object_attributes=False),
        "relationships": _parse_relationships(element),
    }


def _parse_object(element: ET.Element) -> dict[str, object]:
    return {
        "id": element.get("id"),
        "type": element.get("type"),
        "attributes": _parse_attributes(element, object_attributes=True),
        "relationships": _parse_relationships(element),
    }


def _parse_attributes(
    element: ET.Element,
    *,
    object_attributes: bool,
) -> list[dict[str, object]]:
    attributes: list[dict[str, object]] = []
    for container in element:
        if _local_name(container.tag) != "attributes":
            continue
        for child in container:
            if _local_name(child.tag) != "attribute":
                continue
            attribute: dict[str, object] = {
                "name": child.get("name"),
                "value": child.text or "",
            }
            if object_attributes:
                attribute["time"] = child.get("time")
            attributes.append(attribute)
    return attributes


def _parse_relationships(element: ET.Element) -> list[dict[str, object]]:
    relationships: list[dict[str, object]] = []
    for container in element:
        if _local_name(container.tag) != "objects":
            continue
        for child in container:
            if _local_name(child.tag) not in {"relationship", "relobj"}:
                continue
            relationships.append(
                {
                    "objectId": child.get("object-id"),
                    "qualifier": child.get("qualifier"),
                }
            )
    return relationships


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _open_binary(path: Path) -> BinaryIO:
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rb")
    return path.open("rb")


__all__ = ["load"]
