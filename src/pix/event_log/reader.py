"""Native XES XML/gzip reader with a deliberately bounded preservation profile.

Profile: case-based XES with string/date/int/float/boolean/id/list and the
historical OpenXES container extension; namespace-free or xes-standard.org
namespace. Standard declarations, globals, classifier keys, root metadata,
attribute hierarchy and source trace/event order are retained. Comments and
XML formatting are not data and are not retained; this is not byte roundtrip
or full XSD validation. A source hash identifies the original bytes.

Compatibility details: xes.version may be omitted; classifier scope defaults
to event, quoted keys use single/double quotes without backslash escapes;
list requires a final attribute-free values wrapper. XML namespace declarations
are retained on the root; nested redeclarations fail rather than disappear.
Container is a historical compatibility type, not in the cited IEEE 2016 XSD.
Duplicate keys outside ordered list values are rejected as ambiguous.

XML 1.0 only, maximum depth 128; dates must fit Python datetime exactly
(years 1..9999, microseconds, optional timezone). Unsupported dates, XML 1.1,
free-standing log events and unpreserved structures fail explicitly. DTDs,
entity declarations, external references and processing instructions are
rejected by parser callbacks, including UTF-16 input. No external loads occur.
The parser streams 64 KiB input chunks and releases processed event/trace XML;
the returned immutable log necessarily occupies memory for all accepted facts.

Primary sources: IEEE Task Force XES definition and its published XSD:
https://www.tf-pm.org/resources/xes-standard/for-researchers/ieee-1849-2016-xes/definition
https://www.tf-pm.org/upload/1581071084733.xsd
This profile makes no conformance claim to the complete IEEE 1849-2023 text.
"""

from __future__ import annotations

import gzip
import re
import shlex
import zlib
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import replace
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import BinaryIO
from xml.etree import ElementTree as ET
from xml.parsers import expat

from pix.event_log.contract import CaseImportResult
from pix.event_log.model import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseExtension,
    CaseGlobal,
    CaseLog,
    CaseSource,
    CaseTrace,
)
from pix.ocel.ingest.contract import (
    ImportIssue,
    ImportStage,
    ImportStatus,
    Transformation,
)
from pix.ocel.report import Level

_ATTRIBUTES = {"string", "date", "int", "float", "boolean", "id", "list", "container"}
_NAMESPACES = {"", "http://www.xes-standard.org/", "http://www.xes-standard.org"}
_DATE = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.([0-9]+))?(?:Z|[+-][0-9]{2}:[0-9]{2})?\Z"
)
_FLOAT = re.compile(
    r"[+-]?(?:(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|INF)|NaN\Z"
)


class CaseFormatError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: ImportStatus = ImportStatus.SCHEMA_INVALID,
        stage: ImportStage = ImportStage.SCHEMA,
    ) -> None:
        super().__init__(message)
        self.code, self.status, self.stage = code, status, stage


def _safe_elements(stream: BinaryIO) -> Iterator[tuple[str, ET.Element]]:
    """Expat builds only queued chunks; hostile declarations never expand."""
    parser = expat.ParserCreate(namespace_separator="}")
    builder = ET.TreeBuilder()
    queue: deque[tuple[str, ET.Element]] = deque()
    depth = 0
    namespaces: list[tuple[str, str]] = []

    def reject(*args: object) -> None:
        raise CaseFormatError(
            "unsafe_xml",
            "DTD/entities/external loads/processing instructions are prohibited",
            status=ImportStatus.SYNTAX_INVALID,
            stage=ImportStage.SYNTAX,
        )

    def declaration(version: str, encoding: str | None, standalone: int) -> None:
        if version != "1.0":
            raise CaseFormatError(
                "unsupported_xml_version",
                "Only XML 1.0 is supported",
                status=ImportStatus.UNSUPPORTED,
            )

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > 128:
            raise CaseFormatError(
                "xml_depth_limit",
                "XML exceeds depth 128",
                status=ImportStatus.UNSUPPORTED,
            )
        attributes = {"{" + k if "}" in k else k: v for k, v in attributes.items()}
        for prefix, uri in namespaces:
            attributes["xmlns" + (":" + prefix if prefix else "")] = uri
        namespaces.clear()
        element = builder.start("{" + name if "}" in name else name, attributes)
        queue.append(("start", element))

    def end(name: str) -> None:
        nonlocal depth
        element = builder.end("{" + name if "}" in name else name)
        queue.append(("end", element))
        depth -= 1

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = builder.data
    parser.XmlDeclHandler = declaration
    parser.StartNamespaceDeclHandler = lambda prefix, uri: namespaces.append(
        (prefix or "", uri or "")
    )
    parser.StartDoctypeDeclHandler = reject
    parser.EntityDeclHandler = reject
    parser.ExternalEntityRefHandler = reject
    parser.ProcessingInstructionHandler = reject
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    while chunk := stream.read(65536):
        parser.Parse(chunk, False)
        while queue:
            yield queue.popleft()
    parser.Parse(b"", True)
    while queue:
        yield queue.popleft()


def _parse_date(value: str) -> datetime:
    match = _DATE.fullmatch(value)
    if match is None:
        raise CaseFormatError(
            "invalid_date",
            "date must be an ISO XML dateTime in the supported year range",
        )
    fraction = match.group(1) or ""
    if len(fraction) > 6 and any(digit != "0" for digit in fraction[6:]):
        raise CaseFormatError(
            "unsupported_time_precision",
            "Date precision exceeds microseconds; no truncation is allowed",
            status=ImportStatus.UNSUPPORTED,
        )
    if re.search(r"[+-][0-9]{2}:[0-9]{2}$", value):
        hours, minutes = int(value[-5:-3]), int(value[-2:])
        if minutes > 59 or hours > 14 or (hours == 14 and minutes):
            raise CaseFormatError(
                "invalid_date", "XML timezone offset must be within -14:00..+14:00"
            )
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CaseFormatError("invalid_date", str(exc)) from exc


def _tag(element: ET.Element) -> str:
    tag = element.tag
    namespace, local = tag[1:].split("}", 1) if tag.startswith("{") else ("", tag)
    if namespace not in _NAMESPACES:
        raise CaseFormatError(
            "unsupported_namespace",
            f"Unknown XES namespace {namespace!r}",
            status=ImportStatus.UNSUPPORTED,
        )
    return local


def _shape(
    element: ET.Element, required: set[str], optional: set[str] | None = None
) -> None:
    allowed = required | (optional or set())
    if set(element.attrib) - allowed or required - set(element.attrib):
        raise CaseFormatError(
            "invalid_element_attributes",
            f"Unexpected or missing XML attributes on {_tag(element)!r}",
        )
    if (element.text or "").strip() or (element.tail or "").strip():
        raise CaseFormatError(
            "unexpected_xml_text", f"Unexpected text in {_tag(element)!r}"
        )


def _attributes(elements: list[ET.Element]) -> tuple[CaseAttribute, ...]:
    attributes = tuple(_attribute(element) for element in elements)
    keys = tuple(a.key for a in attributes)
    if len(set(keys)) != len(keys):
        raise CaseFormatError(
            "duplicate_attribute",
            "Duplicate attribute keys outside ordered list values are ambiguous",
        )
    return attributes


def _attribute(element: ET.Element) -> CaseAttribute:
    kind = _tag(element)
    if kind not in _ATTRIBUTES:
        raise CaseFormatError(
            "unknown_xes_element",
            f"Unpreserved XES element {kind!r}",
            status=ImportStatus.UNSUPPORTED,
        )
    complex_ = kind in ("list", "container")
    _shape(element, {"key"} if complex_ else {"key", "value"})
    lexical = element.get("value")
    value: object = lexical
    try:
        if kind == "date":
            value = _parse_date(lexical)
        elif kind == "int":
            if not re.fullmatch(r"[+-]?[0-9]+", lexical):
                raise ValueError("int must use the XML integer lexical form")
            value = int(lexical)
            if not -(2**63) <= value < 2**63:
                raise ValueError("XES int is signed 64-bit xs:long")
        elif kind == "float":
            if not _FLOAT.fullmatch(lexical):
                raise ValueError("float must use the XML double lexical form")
            value = float(lexical)
        elif kind == "boolean":
            if lexical not in ("true", "false", "1", "0"):
                raise ValueError("boolean must be true, false, 1 or 0")
            value = lexical in ("true", "1")
    except CaseFormatError:
        raise
    except (TypeError, ValueError) as exc:
        raise CaseFormatError("invalid_attribute_value", str(exc)) from exc
    children = list(element)
    values: tuple[CaseAttribute, ...] = ()
    if kind == "list":
        wrappers = [e for e in children if _tag(e) == "values"]
        if len(wrappers) != 1 or children[-1] is not wrappers[0]:
            raise CaseFormatError(
                "invalid_list", "list requires one final values element"
            )
        wrapper = wrappers[0]
        _shape(wrapper, set())
        values = tuple(_attribute(item) for item in wrapper)
        children.remove(wrapper)
    return CaseAttribute(
        element.attrib["key"], kind, value, _attributes(children), values, lexical
    )


def _parse_xes(stream: BinaryIO) -> CaseLog:
    stack: list[ET.Element] = []
    traces: list[CaseTrace] = []
    events: list[CaseEvent] = []
    attributes: list[CaseAttribute] = []
    globals_: list[CaseGlobal] = []
    extensions: list[CaseExtension] = []
    classifiers: list[CaseClassifier] = []
    metadata: tuple[tuple[str, str], ...] = ()
    detached: ET.Element | None = None
    for action, element in _safe_elements(stream):
        if detached is not None and (detached.tail or "").strip():
            raise CaseFormatError(
                "unexpected_xml_text", "Unexpected text between XES elements"
            )
        tag = _tag(element)
        if action == "start":
            if not stack:
                if tag != "log":
                    raise CaseFormatError("invalid_xes_root", "XES requires a log root")
                metadata = tuple(element.attrib.items())
            stack.append(element)
            continue
        parent = _tag(stack[-2]) if len(stack) > 1 else None
        if tag == "event" and parent == "trace":
            _shape(element, set())
            events.append(
                CaseEvent(
                    f"event:{len(traces)}:{len(events)}", _attributes(list(element))
                )
            )
            stack[-2].remove(element)
            detached = element
        elif tag == "trace" and parent == "log":
            _shape(element, set())
            traces.append(
                CaseTrace(
                    f"trace:{len(traces)}", tuple(events), _attributes(list(element))
                )
            )
            events.clear()
            stack[-2].remove(element)
            detached = element
        elif parent == "log":
            if tag in _ATTRIBUTES:
                attributes.append(_attribute(element))
            elif tag == "extension":
                _shape(element, {"name", "prefix", "uri"})
                if len(element):
                    raise CaseFormatError(
                        "invalid_extension", "extension cannot contain children"
                    )
                extensions.append(CaseExtension(**element.attrib))
            elif tag == "global":
                _shape(element, {"scope"})
                globals_.append(
                    CaseGlobal(element.attrib["scope"], _attributes(list(element)))
                )
            elif tag == "classifier":
                _shape(element, {"name", "keys"}, {"scope"})
                if len(element):
                    raise CaseFormatError(
                        "invalid_classifier", "classifier cannot contain children"
                    )
                lexical = element.attrib["keys"]
                lexer = shlex.shlex(lexical, posix=True)
                lexer.whitespace_split, lexer.commenters, lexer.escape = True, "", ""
                keys = tuple(lexer)
                classifiers.append(
                    CaseClassifier(
                        element.attrib["name"],
                        keys,
                        element.get("scope", "event"),
                        lexical,
                    )
                )
            else:
                raise CaseFormatError(
                    "unsupported_log_element",
                    f"Unpreserved log element {tag!r}; free-standing events have no case",
                    status=ImportStatus.UNSUPPORTED,
                )
            stack[-2].remove(element)
            detached = element
        elif tag == "log" and parent is None:
            if (element.text or "").strip() or (element.tail or "").strip():
                raise CaseFormatError(
                    "unexpected_xml_text", "Log cannot contain character data"
                )
        stack.pop()
    if detached is not None and (detached.tail or "").strip():
        raise CaseFormatError(
            "unexpected_xml_text", "Unexpected text after XES element"
        )
    log = CaseLog(
        tuple(traces),
        tuple(attributes),
        tuple(globals_),
        tuple(extensions),
        tuple(classifiers),
        metadata,
    )
    # Detect ambiguous defaults even in an empty log.
    log.effective_attributes(CaseEvent("_check"))
    log.effective_attributes(CaseTrace("_check"))
    if len({a.key for a in log.attributes}) != len(log.attributes):
        raise CaseFormatError("duplicate_attribute", "Duplicate log attribute keys")
    return log


def _profile(log: CaseLog) -> tuple[ImportIssue, ...]:
    missing_activity = missing_time = naive_time = 0
    for trace in log.traces:
        for event in trace.events:
            activity = log.attribute(event, "concept:name")
            time = log.attribute(event, "time:timestamp")
            missing_activity += (
                activity is None
                or activity.type != "string"
                or not activity.value.strip()
            )
            missing_time += time is None or time.type != "date"
            naive_time += (
                time is not None
                and time.type == "date"
                and time.value.utcoffset() is None
            )
    return tuple(
        ImportIssue(
            ImportStage.PROFILE, code, f"{count} events: {message}", Level.WARNING
        )
        for code, count, message in (
            (
                "missing_activity",
                missing_activity,
                "no usable concept:name; choose a classifier or activity mapping",
            ),
            (
                "missing_timestamp",
                missing_time,
                "time unknown; sequence analysis can retain source order",
            ),
            (
                "naive_timestamp",
                naive_time,
                "timezone unknown; OCEL conversion requires explicit timezone-aware data",
            ),
        )
        if count
    )


def _load_xml(
    path: str | Path, format: str, parse: Callable[[BinaryIO], CaseLog]
) -> CaseImportResult:
    path = Path(path)
    digest: str | None = None
    size: int | None = None
    try:
        # Same open file descriptor for evidence and parse avoids a pathname
        # replacement race; compare the stream bytes again after parsing.
        with path.open("rb") as raw:
            hash_ = sha256()
            size = 0
            while chunk := raw.read(65536):
                hash_.update(chunk)
                size += len(chunk)
            digest = hash_.hexdigest()
            raw.seek(0)
            magic = raw.read(2)
            raw.seek(0)
            compressed = magic == b"\x1f\x8b" or path.suffix.lower() == ".gz"
            if compressed:
                with gzip.GzipFile(fileobj=raw) as stream:
                    log = parse(stream)
            else:
                log = parse(raw)
            raw.seek(0)
            check = sha256()
            while chunk := raw.read(65536):
                check.update(chunk)
            if check.hexdigest() != digest:
                raise CaseFormatError(
                    "source_changed",
                    "Source changed during import",
                    status=ImportStatus.UNAVAILABLE,
                    stage=ImportStage.SOURCE,
                )
        source = CaseSource(str(path), format, digest, size)
        log = replace(log, source=source)
        return CaseImportResult(
            str(path),
            format,
            ImportStatus.VALID,
            log,
            _profile(log),
            (
                Transformation(
                    "positional_identity",
                    "Internal trace/event IDs preserve source positions; source name/id attributes remain separate",
                ),
            ),
            digest,
            size,
        )
    except CaseFormatError as exc:
        status, issue = exc.status, ImportIssue(exc.stage, exc.code, str(exc))
    except (expat.ExpatError, gzip.BadGzipFile, EOFError, zlib.error) as exc:
        status, issue = (
            ImportStatus.SYNTAX_INVALID,
            ImportIssue(ImportStage.SYNTAX, "invalid_xml_or_gzip", str(exc)),
        )
    except OSError as exc:
        status, issue = (
            ImportStatus.UNAVAILABLE,
            ImportIssue(ImportStage.SOURCE, "source_unavailable", str(exc)),
        )
    except (TypeError, ValueError) as exc:
        status, issue = (
            ImportStatus.SCHEMA_INVALID,
            ImportIssue(ImportStage.SCHEMA, "invalid_case_structure", str(exc)),
        )
    return CaseImportResult(
        str(path),
        format,
        status,
        None,
        (issue,),
        source_sha256=digest,
        source_size=size,
    )


def import_xes(path: str | Path) -> CaseImportResult:
    """Read XES loss-aware storage facts or a diagnostic failure transaction."""
    return _load_xml(path, "xes", _parse_xes)


def read_xes(path: str | Path) -> CaseLog:
    """Return a stored CaseLog; missing time/activity are reported by import_xes."""
    return import_xes(path).require_case_log()
