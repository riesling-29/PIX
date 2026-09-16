"""Streaming import of historical, case-centric MXML logs.

The vocabulary follows the original TU/e ``WorkflowLog.xsd``:
https://processmining.org/old-version/files/WorkflowLog.xsd

This loss-preserving profile accepts missing event fields and does not require
schema child order. It never invents activities, lifecycle transitions or times.
``Data`` remains a ``mxml:data`` container, and process metadata is retained in
``mxml:processes`` with positional trace affiliations. Unknown fields fail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from os import PathLike
from typing import BinaryIO
from xml.etree import ElementTree as ET

from pix.event_log.contract import CaseImportResult
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.event_log.reader import (
    CaseFormatError,
    _load_xml,
    _parse_date,
    _safe_elements,
)

_XSI = "{http://www.w3.org/2001/XMLSchema-instance}"
_CHILDREN = {
    "WorkflowLog": {"Data", "Source", "Process"},
    "Source": {"Data"},
    "Process": {"Data", "ProcessInstance"},
    "ProcessInstance": {"Data", "AuditTrailEntry"},
    "AuditTrailEntry": {
        "Data",
        "WorkflowModelElement",
        "EventType",
        "Timestamp",
        "Originator",
    },
    "Data": {"Attribute"},
    "Attribute": set(),
    "WorkflowModelElement": set(),
    "EventType": set(),
    "Timestamp": set(),
    "Originator": set(),
}
_ATTRIBUTES = {
    "WorkflowLog": {
        "description",
        _XSI + "noNamespaceSchemaLocation",
        _XSI + "schemaLocation",
    },
    "Source": {"program"},
    "Process": {"id", "description"},
    "ProcessInstance": {"id", "description"},
    "EventType": {"unknowntype"},
    "Attribute": {"name"},
}
_REQUIRED = {
    "Source": "program",
    "Process": "id",
    "ProcessInstance": "id",
    "Attribute": "name",
}
_REPEATED = {"Process", "ProcessInstance", "AuditTrailEntry", "Attribute"}
_LEAVES = {"Attribute", "WorkflowModelElement", "EventType", "Timestamp", "Originator"}
_EVENT_KEYS = {
    "WorkflowModelElement": "concept:name",
    "EventType": "lifecycle:transition",
    "Timestamp": "time:timestamp",
    "Originator": "org:resource",
}
_EVENT_TYPES = {
    "schedule",
    "assign",
    "withdraw",
    "reassign",
    "start",
    "suspend",
    "resume",
    "pi_abort",
    "ate_abort",
    "complete",
    "autoskip",
    "manualskip",
    "unknown",
}


@dataclass
class _Frame:
    element: ET.Element
    attributes: list[CaseAttribute] = field(default_factory=list)
    events: list[CaseEvent] = field(default_factory=list)
    seen: set[str] = field(default_factory=set)
    last_child: ET.Element | None = None
    index: int = 0


def _invalid(code: str, message: str) -> None:
    raise CaseFormatError("mxml." + code, message)


def _whitespace(value: str | None, location: str) -> None:
    if value is not None and value.strip():
        _invalid("unexpected_text", f"Unexpected text in {location}: {value!r}")


def _release_child(frame: _Frame) -> None:
    """Release a parsed child only once its trailing text has arrived."""
    child = frame.last_child
    if child is not None:
        _whitespace(child.tail, f"{frame.element.tag} after {child.tag}")
        frame.element.remove(child)
        child.clear()
        frame.last_child = None


def _metadata(element: ET.Element) -> list[CaseAttribute]:
    attributes = []
    for key, value in element.attrib.items():
        if element.tag == "Attribute" and key == "name":
            continue
        if element.tag == "ProcessInstance" and key == "id":
            name = "concept:name"
        elif key.startswith(_XSI):
            name = "mxml:xsi:" + key[len(_XSI) :]
        else:
            name = "mxml:" + key
        attributes.append(CaseAttribute(name, "string", value))
    return attributes


def _start(element: ET.Element, parent: _Frame | None) -> _Frame:
    tag = element.tag
    if parent is None:
        if tag != "WorkflowLog":
            _invalid("root", "MXML root must be WorkflowLog without a namespace")
    else:
        parent_tag = parent.element.tag
        if tag not in _CHILDREN[parent_tag]:
            _invalid("unknown_element", f"Unsupported {tag!r} inside {parent_tag}")
        if tag in parent.seen and tag not in _REPEATED:
            _invalid("duplicate_element", f"Repeated {tag} inside {parent_tag}")
        parent.seen.add(tag)
    # The safe parser exposes namespace declarations so their source metadata
    # can be retained. They are declarations, not unknown vocabulary fields.
    declarations = {
        key for key in element.attrib if key == "xmlns" or key.startswith("xmlns:")
    }
    unknown = element.attrib.keys() - _ATTRIBUTES.get(tag, set()) - declarations
    if unknown:
        _invalid(
            "unknown_attribute", f"Unsupported attributes in {tag}: {sorted(unknown)}"
        )
    required = _REQUIRED.get(tag)
    if required is not None and required not in element.attrib:
        _invalid("missing_attribute", f"{tag} requires attribute {required!r}")
    metadata = _metadata(element)
    if tag == "Data" and metadata:
        # Data allows arbitrary user keys. A typed container distinguishes XML
        # declarations from user strings even when their names are identical.
        metadata = [
            CaseAttribute("mxml:xmlAttributes", "container", children=tuple(metadata))
        ]
    return _Frame(element, attributes=metadata)


def _leaf(frame: _Frame) -> CaseAttribute:
    element = frame.element
    tag = element.tag
    value = element.text or ""
    if tag == "Attribute":
        return CaseAttribute(
            element.attrib["name"], "string", value, children=tuple(frame.attributes)
        )
    key = _EVENT_KEYS[tag]
    if tag == "Timestamp":
        return CaseAttribute(
            key,
            "date",
            _parse_date(value),
            children=tuple(frame.attributes),
            lexical=value,
        )
    if tag == "EventType" and value not in _EVENT_TYPES:
        _invalid("event_type", f"Unsupported EventType value: {value!r}")
    return CaseAttribute(key, "string", value, children=tuple(frame.attributes))


def _parse_mxml(stream: BinaryIO) -> CaseLog:
    stack: list[_Frame] = []
    traces: list[CaseTrace] = []
    processes: list[CaseAttribute] = []
    result: CaseLog | None = None
    for event, element in _safe_elements(stream):
        if event == "start":
            parent = stack[-1] if stack else None
            if parent is not None:
                _release_child(parent)
            frame = _start(element, parent)
            if element.tag == "Process":
                frame.index = len(processes)
                frame.attributes.insert(
                    0, CaseAttribute("mxml:index", "int", frame.index)
                )
            elif element.tag == "ProcessInstance":
                frame.index = len(traces)
                assert parent is not None
                frame.attributes.insert(
                    0, CaseAttribute("mxml:processIndex", "int", parent.index)
                )
            stack.append(frame)
            continue

        frame = stack.pop()
        _release_child(frame)
        tag = element.tag
        parent = stack[-1] if stack else None
        if tag in _LEAVES:
            assert parent is not None
            parent.attributes.append(_leaf(frame))
        else:
            _whitespace(element.text, tag)
            if tag == "Data":
                assert parent is not None
                parent.attributes.append(
                    CaseAttribute(
                        "mxml:data", "container", children=tuple(frame.attributes)
                    )
                )
            elif tag == "Source":
                assert parent is not None
                parent.attributes.append(
                    CaseAttribute(
                        "mxml:source", "container", children=tuple(frame.attributes)
                    )
                )
            elif tag == "AuditTrailEntry":
                assert parent is not None
                parent.events.append(
                    CaseEvent(
                        f"event:{parent.index}:{len(parent.events)}",
                        tuple(frame.attributes),
                    )
                )
            elif tag == "ProcessInstance":
                traces.append(
                    CaseTrace(
                        f"trace:{frame.index}",
                        tuple(frame.events),
                        tuple(frame.attributes),
                    )
                )
            elif tag == "Process":
                processes.append(
                    CaseAttribute(
                        "mxml:process", "container", children=tuple(frame.attributes)
                    )
                )
            elif tag == "WorkflowLog":
                if processes:
                    frame.attributes.append(
                        CaseAttribute("mxml:processes", "list", values=tuple(processes))
                    )
                result = CaseLog(tuple(traces), attributes=tuple(frame.attributes))
        if parent is not None:
            parent.last_child = element
    if result is None:
        _invalid("root", "MXML document has no WorkflowLog")
    return result


def import_mxml(path: str | PathLike[str]) -> CaseImportResult:
    """Import plain or gzip MXML with structured errors and byte provenance."""
    return _load_xml(path, "mxml", _parse_mxml)


def read_mxml(path: str | PathLike[str]) -> CaseLog:
    """Read a valid MXML log, or raise ``CaseImportError`` with its result."""
    return import_mxml(path).require_case_log()


__all__ = ["import_mxml", "read_mxml"]
