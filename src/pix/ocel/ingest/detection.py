"""Content-based family detection without interpreting or repairing a log.

Detection is only routing. The selected adapter owns syntax and semantic checks.
Malformed or ambiguous OCEL content falls back to the OCEL 2.0 adapter so that
its existing diagnostics are retained. Explicit format selection bypasses this.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from xml.etree import ElementTree as ET

from pix.ocel.ingest.formats._sqlite_source import standalone_database_issue


def detect_log_family(path: Path) -> str | None:
    """Recognize OCEL versions, XES, MXML and declared bundle containers."""
    if path.is_dir():
        return "ocel21-bundle" if (path / "ocel-meta.json").is_file() else None
    name = path.name.lower()
    if name.endswith((".ocel.zip", ".ocel.csv", ".ocel.csv.gz")):
        return "ocel21-bundle" if name.endswith(".zip") else "ocel21-csv"
    if name.endswith((".xes", ".xes.gz")):
        return "xes"
    if name.endswith((".mxml", ".mxml.gz")):
        return "mxml"
    try:
        opener = gzip.open if name.endswith(".gz") else open
        with opener(path, "rb") as stream:
            prefix = stream.read(4096)
            if prefix.startswith(b"SQLite format 3\x00"):
                return _sqlite_family(path)
            if prefix.startswith(b"PK\x03\x04"):
                return None  # Generic ZIP/XLSX requires its own explicit route.
            stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
            while not stripped and prefix:
                prefix = stream.read(4096)
                stripped = prefix.lstrip(b" \t\r\n")
            if stripped.startswith(b"{"):
                # OCEL1 root keys all start with ocel:. Decode just the first
                # key rather than loading the document a second time.
                text = stripped[1:].lstrip()
                while len(text) < 1024 * 1024:
                    try:
                        key, _ = json.JSONDecoder().raw_decode(text.decode("utf-8"))
                        return (
                            "ocel10-json"
                            if isinstance(key, str) and key.startswith("ocel:")
                            else "ocel20-json"
                        )
                    except (ValueError, UnicodeDecodeError):
                        more = stream.read(4096)
                        if not more:
                            break
                        text += more
                return "ocel20-json"
            if stripped.startswith(b"["):
                return "ocel20-json"
            if stripped.startswith(b"<") or prefix.startswith(
                (b"\xff\xfe", b"\xfe\xff")
            ):
                return _xml_family(prefix, stream)
    except (OSError, EOFError, ValueError):
        return None
    return None


def _sqlite_family(path: Path) -> str:
    if standalone_database_issue(path) is not None:
        # A sniff must not create sidecars or inspect a state absent from the
        # single-file source digest. The adapter returns the explicit issue.
        return "ocel20-sqlite"
    try:
        with closing(
            sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        ) as db:
            tables = {
                row[0].lower()
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        if {"events", "objects", "relations"} <= tables and not {
            "event",
            "object",
            "event_object",
        } <= tables:
            return "ocel10-sqlite"
    except sqlite3.Error:
        pass
    return "ocel20-sqlite"


def _xml_family(prefix: bytes, stream: object) -> str:
    parser = ET.XMLPullParser(events=("start",))
    seen = 0
    carry = b""
    ocel_container = False
    possible_xes = False
    chunk = prefix
    try:
        while chunk and seen < 64:
            guard = (carry + chunk).upper().replace(b"\x00", b"")
            if b"<!DOCTYPE" in guard or b"<!ENTITY" in guard:
                return "ocel20-xml"  # Never expand declarations during routing.
            carry = chunk[-32:]
            parser.feed(chunk)
            for _, element in parser.read_events():
                seen += 1
                tag = element.tag.rsplit("}", 1)[-1]
                if seen == 1:
                    if tag in {"ProcessMining", "WorkflowLog"}:
                        return "mxml"
                    if tag != "log":
                        return "ocel20-xml"
                    if (
                        "xes.version" in element.attrib
                        or "xes.features" in element.attrib
                    ):
                        return "xes"
                    if "xes" in element.tag.lower():
                        return "xes"
                elif tag in {"trace", "classifier", "extension"}:
                    return "xes"
                elif tag == "global" and element.attrib.get("scope") in {
                    "log",
                    "object",
                }:
                    return "ocel10-xml"
                elif element.attrib.get("key", "").startswith("ocel:"):
                    return "ocel10-xml"
                elif tag in {"event-types", "object-types"}:
                    return "ocel20-xml"
                elif tag in {"events", "objects"}:
                    ocel_container = True
                elif tag == "event":
                    if "type" in element.attrib:
                        return "ocel20-xml"
                    if ocel_container:
                        return "ocel10-xml"
                    possible_xes = True
                elif tag == "object" and ocel_container:
                    return "ocel20-xml" if "type" in element.attrib else "ocel10-xml"
                elif tag in {"string", "date", "int", "float", "boolean", "id"}:
                    possible_xes = True
            chunk = stream.read(4096)
    except (ET.ParseError, OSError, EOFError):
        pass
    return "xes" if possible_xes else "ocel20-xml"


__all__ = ["detect_log_family"]
