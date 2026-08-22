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
    syntax_failure,
)


def load(path: Path) -> tuple[BuildResult, tuple[Transformation, ...]]:
    """Parse and map one OCEL 2.0 JSON file."""

    try:
        with _open_binary(path) as stream:
            document = json.load(
                stream,
                parse_constant=_reject_nonfinite_number,
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


__all__ = ["load"]
