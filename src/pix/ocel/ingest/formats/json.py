"""Strict OCEL 2.0 JSON adapter."""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import BinaryIO

from pix.ocel.build import BuildResult
from pix.ocel.ingest.contract import Transformation
from pix.ocel.ingest.formats.common import (
    ValueEncoding,
    map_document,
    mapping_failure,
    schema_failure,
    syntax_failure,
)


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Parse and map one OCEL 2.0 JSON file."""

    try:
        with _open_binary(path) as stream:
            document = json.load(
                stream,
                parse_constant=_reject_nonfinite_number,
                parse_int=_parse_integer,
                object_pairs_hook=_unique_members,
            )
    except UnicodeDecodeError as exc:
        raise syntax_failure(
            "invalid_utf8",
            "OCEL JSON must be encoded as UTF-8.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise syntax_failure(
            "invalid_json",
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}.",
            (str(exc.lineno), str(exc.colno)),
        ) from exc
    except (OSError, EOFError) as exc:
        raise syntax_failure("unreadable_json", str(exc)) from exc

    return map_document(document, encoding=ValueEncoding.JSON)


def _open_binary(path: Path) -> BinaryIO:
    if path.name.lower().endswith(".gz"):
        return gzip.open(path, "rb")
    return path.open("rb")


def _reject_nonfinite_number(value: str) -> object:
    raise syntax_failure(
        "nonfinite_json_number",
        f"JSON numeric constant '{value}' is not permitted.",
    )


def _unique_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject even equal duplicate members before any record can be overwritten."""

    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise schema_failure(
                "duplicate_json_member",
                f"Repeated JSON member '{key}'.",
                (key,),
            )
        result[key] = value
    return result


def _parse_integer(value: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise mapping_failure(
            "integer_out_of_range",
            "JSON integer exceeds the supported interpreter conversion limit.",
        ) from exc


__all__ = ["load"]
