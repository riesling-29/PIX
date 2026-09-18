"""Bounded, dependency-free XML parsing for explicit model exchange profiles.

XML input is UTF-8 only. DTDs, entities, processing instructions and foreign
semantics are never resolved. Byte, element and nesting budgets apply before
constructing the complete XML tree; no network or filesystem entity access is
performed. A successful import identifies a supported profile, not conformance
to every feature in a format's standard.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, NoReturn
from xml.etree import ElementTree as ET


@dataclass(frozen=True, slots=True)
class XMLLimits:
    max_bytes: int = 16 * 1024 * 1024
    max_elements: int = 200_000
    max_depth: int = 128

    def __post_init__(self):
        for name in ("max_bytes", "max_elements", "max_depth"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.max_depth > 128:
            raise ValueError("max_depth must not exceed 128")


class ModelIOError(ValueError):
    """Import/export refusal with a machine-readable cause and source element."""

    def __init__(self, message, *, format, code="unsupported_feature", element=""):
        self.format = format
        self.code = code
        self.element = element
        location = f" ({element})" if element else ""
        super().__init__(f"{format}: {message}{location}")


@dataclass(frozen=True, slots=True)
class ParsedModel:
    """Model plus source/profile evidence; use ``.model`` for calculations.

    ``source_ids`` retains format-only identities absent from native contracts.
    ``metadata`` holds explicitly documented nonbehavioral source information.
    ``presentation_ignored`` names source display elements intentionally omitted.
    Exporting the wrapper may preserve more serialization metadata than exporting
    only ``.model``. Neither operation is a byte-for-byte XML roundtrip.
    """

    model: Any
    format: str
    profile: str
    format_version: str
    source_sha256: str
    profile_version: str = "1.0.0"
    source_ids: tuple[tuple[str, str], ...] = ()
    presentation_ignored: tuple[str, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()


def fail(format, message, element="", code="unsupported_feature") -> NoReturn:
    raise ModelIOError(message, format=format, code=code, element=element)


def _bytes(source: bytes | str, format="XML") -> bytes:
    if isinstance(source, str):
        try:
            return source.encode("utf-8")
        except UnicodeError as error:
            fail(format, str(error), code="invalid_xml")
    if not isinstance(source, bytes):
        raise TypeError("XML payload must be bytes or str")
    return source


def source_digest(source: bytes | str) -> str:
    return sha256(_bytes(source)).hexdigest()


def parse_xml(source: bytes | str, format: str, limits: XMLLimits):
    if not isinstance(limits, XMLLimits):
        raise TypeError("limits must be XMLLimits")
    payload = _bytes(source, format)
    if len(payload) > limits.max_bytes:
        fail(format, "XML byte limit exceeded", code="resource_limit")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeError:
        fail(format, "only UTF-8 XML is supported", code="unsupported_encoding")
    if "\x00" in text:
        fail(
            format,
            "UTF-8 XML must not contain NUL characters",
            code="unsupported_encoding",
        )
    declaration = re.match(r"\s*<\?xml\b[^?]*\?>", text)
    if declaration:
        encoding = re.search(r"encoding\s*=\s*['\"]([^'\"]+)['\"]", declaration[0])
        if encoding and encoding[1].lower() not in ("utf-8", "utf8", "us-ascii"):
            fail(format, "only UTF-8 XML is supported", code="unsupported_encoding")
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        fail(format, "DTDs and entity declarations are forbidden", code="unsafe_xml")

    class BoundedBuilder(ET.TreeBuilder):
        depth = 0
        count = 0

        def start(self, tag, attrs):
            self.depth += 1
            self.count += 1
            if self.depth > limits.max_depth or self.count > limits.max_elements:
                fail(
                    format, "XML depth or element limit exceeded", code="resource_limit"
                )
            return super().start(tag, attrs)

        def end(self, tag):
            element = super().end(tag)
            self.depth -= 1
            return element

        def doctype(self, name, pubid, system):
            fail(format, "DTDs are forbidden", code="unsafe_xml")

        def pi(self, target, text=None):
            fail(format, "processing instructions are unsupported", element=target)

    try:
        return ET.fromstring(payload, parser=ET.XMLParser(target=BoundedBuilder()))
    except ET.ParseError as error:
        fail(format, str(error), code="invalid_xml")


def local(element) -> str:
    tag = element.tag if hasattr(element, "tag") else element
    return tag.rsplit("}", 1)[-1]


def strict(element, allowed_attrs, allowed_children, format):
    """Check exact attributes and child local names; callers check namespaces."""
    for attr in element.attrib:
        if attr not in allowed_attrs:
            fail(format, f"unsupported attribute {attr!r}", element=local(element))
    for child in element:
        if local(child) not in allowed_children:
            fail(format, "unsupported source element", element=local(child))
        if child.tail and child.tail.strip():
            fail(format, "mixed XML text is unsupported", element=local(element))
    if (
        element.text
        and element.text.strip()
        and (len(element) or local(element) not in ("text", "incoming", "outgoing"))
    ):
        fail(format, "mixed XML text is unsupported", element=local(element))


def integer(text, format, element, min=0):
    if text is None or re.fullmatch(r"\+?[0-9]+", text.strip()) is None:
        fail(format, "expected an integer", element=element, code="invalid_value")
    # Avoid unbounded integer work even where Python's own guard is disabled.
    if len(text.strip().lstrip("+")) > 1000:
        fail(
            format,
            "integer digit limit exceeded",
            element=element,
            code="resource_limit",
        )
    number = int(text)
    if number < min:
        fail(
            format,
            f"integer must be at least {min}",
            element=element,
            code="invalid_value",
        )
    return number


def xml_bytes(root, format="XML") -> bytes:
    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # XML normalizes literal carriage returns in text to LF. ElementTree emits
    # character references for CR in attributes, but not in text content. Use
    # references there too so activity labels retain their exact characters.
    payload = payload.replace(b"\r", b"&#13;")
    # ElementTree serializes some forbidden XML characters without refusing them.
    # Reparse before publication so an accepted writer can always be read back.
    parse_xml(payload, format, XMLLimits())
    return payload
