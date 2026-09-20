"""Verified XES/gzip exchange for the native reader's preservation profile.

Source-position IDs and source-file provenance are not XES attributes. A file
receipt records their positional mapping; stored attributes (including any
identity:id) are never replaced by internal IDs. Null has no XES representation
and is refused. This is semantic exchange, not original XML byte reproduction.
"""

from __future__ import annotations

import gzip
import io
import math
import shlex
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.parsers.expat import ExpatError

from pix._publication import CleanupIssue, publish_bytes
from pix.event_log.adapters import case_log_digest
from pix.event_log.model import CaseAttribute, CaseLog, CaseSource
from pix.event_log.reader import _attribute, _parse_xes


class CaseExportError(ValueError):
    """The requested log cannot be exchanged without undeclared changes."""


@dataclass(frozen=True, slots=True)
class CaseXESExport:
    path: str
    sha256: str
    size: int
    source_digest: str
    trace_ids: tuple[tuple[str, str], ...]
    event_ids: tuple[tuple[str, str], ...]
    profile: str = "pix.xes-preservation.v1"
    cleanup_issues: tuple[CleanupIssue, ...] = ()


def _attribute_facts(a):
    value = a.value
    if a.type == "float":
        value = value.hex()
    elif a.type == "date":
        value = value.isoformat()
    return (
        a.key,
        a.type,
        value,
        tuple(_attribute_facts(x) for x in a.children),
        tuple(_attribute_facts(x) for x in a.values),
    )


def _facts(log):
    def attrs(seq):
        return tuple(_attribute_facts(a) for a in seq)

    return (
        tuple(
            (attrs(t.attributes), tuple(attrs(e.attributes) for e in t.events))
            for t in log.traces
        ),
        attrs(log.attributes),
        tuple((g.scope, attrs(g.attributes)) for g in log.globals),
        log.extensions,
        tuple((c.name, c.keys, c.scope) for c in log.classifiers),
        tuple(sorted(log.metadata)),
    )


def _element(a: CaseAttribute, depth=0):
    if depth > 100:
        raise CaseExportError("attribute nesting exceeds export depth 100")
    if a.type == "null":
        raise CaseExportError(f"XES cannot represent null attribute {a.key!r}")
    fields = {"key": a.key}
    if a.type not in ("list", "container"):
        value = a.lexical
        if value is None:
            if a.type == "date":
                value = a.value.isoformat()
            elif a.type == "boolean":
                value = "true" if a.value else "false"
            elif a.type == "float":
                value = (
                    "NaN"
                    if math.isnan(a.value)
                    else "INF"
                    if a.value == math.inf
                    else "-INF"
                    if a.value == -math.inf
                    else repr(a.value)
                )
            else:
                value = str(a.value)
        fields["value"] = value
    element = ET.Element(a.type, fields)
    element.extend(_element(child, depth + 1) for child in a.children)
    if a.type == "list":
        ET.SubElement(element, "values").extend(
            _element(child, depth + 1) for child in a.values
        )
    # A stale lexical value must not replace the stored typed value.
    if _attribute_facts(_attribute(element)) != _attribute_facts(a):
        raise CaseExportError(f"lexical value disagrees with attribute {a.key!r}")
    return element


def _keys(classifier):
    if classifier.lexical is not None:
        lexer = shlex.shlex(classifier.lexical, posix=True)
        lexer.whitespace_split, lexer.commenters, lexer.escape = True, "", ""
        if tuple(lexer) != classifier.keys:
            raise CaseExportError("classifier lexical keys disagree with stored keys")
        return classifier.lexical
    tokens = []
    for key in classifier.keys:
        if "'" not in key:
            tokens.append("'" + key + "'")
        elif '"' not in key:
            tokens.append('"' + key + '"')
        else:
            # Adjacent quoted segments are concatenated by the XES key lexer.
            tokens.append('"\'"'.join("'" + part + "'" for part in key.split("'")))
    return " ".join(tokens)


def xes_bytes(log: CaseLog, *, compressed: bool = False) -> bytes:
    """Serialize and verify typed facts before returning deterministic bytes."""
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    if type(compressed) is not bool:
        raise TypeError("compressed must be bool")
    if len(dict(log.metadata)) != len(log.metadata):
        raise CaseExportError("duplicate root metadata keys")
    try:
        root = ET.Element("log", dict(log.metadata))
        for ext in log.extensions:
            ET.SubElement(
                root, "extension", name=ext.name, prefix=ext.prefix, uri=ext.uri
            )
        for g in log.globals:
            ET.SubElement(root, "global", scope=g.scope).extend(
                _element(a) for a in g.attributes
            )
        for c in log.classifiers:
            ET.SubElement(root, "classifier", name=c.name, keys=_keys(c), scope=c.scope)
        root.extend(_element(a) for a in log.attributes)
        for trace in log.traces:
            node = ET.SubElement(root, "trace")
            node.extend(_element(a) for a in trace.attributes)
            for event in trace.events:
                ET.SubElement(node, "event").extend(
                    _element(a) for a in event.attributes
                )
        data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
        restored = _parse_xes(io.BytesIO(data))
        if _facts(restored) != _facts(log):
            raise CaseExportError("XES roundtrip changed stored facts")
    except (ValueError, TypeError, ET.ParseError, ExpatError) as error:
        if isinstance(error, CaseExportError):
            raise
        raise CaseExportError(str(error)) from error
    return gzip.compress(data, mtime=0) if compressed else data


def read_xes_bytes(data: bytes) -> CaseLog:
    """Read supplied bytes without acquiring files or contacting external systems."""
    from dataclasses import replace

    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    payload = gzip.decompress(data) if data.startswith(b"\x1f\x8b") else data
    log = _parse_xes(io.BytesIO(payload))
    return replace(
        log, source=CaseSource("<bytes>", "xes", sha256(data).hexdigest(), len(data))
    )


def write_xes(
    log: CaseLog, path: str | Path, *, overwrite: bool = False
) -> CaseXESExport:
    """Publish verified bytes atomically; existing destinations require overwrite."""
    if type(overwrite) is not bool:
        raise TypeError("overwrite must be bool")
    target = Path(path)
    data = xes_bytes(log, compressed=target.suffix.lower() == ".gz")
    publication = publish_bytes(data, target, overwrite=overwrite, prefix=".pix-xes-")
    return CaseXESExport(
        str(target),
        sha256(data).hexdigest(),
        len(data),
        case_log_digest(log),
        tuple((t.id, f"trace:{i}") for i, t in enumerate(log.traces)),
        tuple(
            (e.id, f"event:{i}:{j}")
            for i, t in enumerate(log.traces)
            for j, e in enumerate(t.events)
        ),
        cleanup_issues=publication.cleanup_issues,
    )


__all__ = [
    "CaseExportError",
    "CaseXESExport",
    "xes_bytes",
    "read_xes_bytes",
    "write_xes",
]
