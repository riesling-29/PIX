"""Public, evidence-preserving OCEL import orchestration."""

from __future__ import annotations

import hashlib
import os
import warnings as runtime_warnings
from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Callable, TypeAlias

from pix.ocel.build import BuildResult
from pix.ocel.canonical import canonical_digest
from pix.ocel.ingest.contract import (
    ImportFormat,
    ImportIssue,
    ImportResult,
    ImportStage,
    ImportStatus,
    Transformation,
)
from pix.ocel.ingest.detection import detect_log_family
from pix.ocel.ingest.formats import json as json_adapter
from pix.ocel.ingest.formats import sqlite as sqlite_adapter
from pix.ocel.ingest.formats import xml as xml_adapter
from pix.ocel.ingest.formats.common import AdapterFailure
from pix.ocel.metadata import OCELImportInfo, OCELWarning, TimezoneInfo
from pix.ocel.model import OCEL
from pix.ocel.report import Level

Source: TypeAlias = str | os.PathLike[str]
Loader: TypeAlias = Callable[[Path], tuple[BuildResult, tuple[Transformation, ...]]]

_LOADERS: dict[ImportFormat, Loader] = {
    ImportFormat.OCEL20_JSON: json_adapter.load,
    ImportFormat.OCEL20_XML: xml_adapter.load,
    ImportFormat.OCEL20_SQLITE: sqlite_adapter.load,
}
_EXTENDED_LOADERS = {
    ImportFormat.OCEL10_JSON: ("legacy", "load_json"),
    ImportFormat.OCEL10_XML: ("legacy", "load_xml"),
    ImportFormat.OCEL10_SQLITE: ("legacy_sqlite", "load"),
    ImportFormat.OCEL21_CSV: ("compact", "load"),
    ImportFormat.OCEL21_BUNDLE: ("bundled", "load"),
}
_FORMAT_ALIASES = {
    "json": ImportFormat.OCEL20_JSON,
    "jsonocel": ImportFormat.OCEL20_JSON,
    "ocel-json": ImportFormat.OCEL20_JSON,
    "ocel20-json": ImportFormat.OCEL20_JSON,
    "xml": ImportFormat.OCEL20_XML,
    "xmlocel": ImportFormat.OCEL20_XML,
    "ocel-xml": ImportFormat.OCEL20_XML,
    "ocel20-xml": ImportFormat.OCEL20_XML,
    "sqlite": ImportFormat.OCEL20_SQLITE,
    "sqlite3": ImportFormat.OCEL20_SQLITE,
    "ocel-sqlite": ImportFormat.OCEL20_SQLITE,
    "ocel20-sqlite": ImportFormat.OCEL20_SQLITE,
    "ocel10-json": ImportFormat.OCEL10_JSON,
    "ocel1-json": ImportFormat.OCEL10_JSON,
    "ocel10-xml": ImportFormat.OCEL10_XML,
    "ocel1-xml": ImportFormat.OCEL10_XML,
    "ocel10-sqlite": ImportFormat.OCEL10_SQLITE,
    "ocel1-sqlite": ImportFormat.OCEL10_SQLITE,
    "ocel21-csv": ImportFormat.OCEL21_CSV,
    "ocel.csv": ImportFormat.OCEL21_CSV,
    "ocel21-bundle": ImportFormat.OCEL21_BUNDLE,
    "ocel.zip": ImportFormat.OCEL21_BUNDLE,
}


class TimezoneAssumptionWarning(UserWarning):
    """A reader warning that timezone-free source values were assumed UTC."""


def import_ocel(
    source: Source,
    *,
    format: ImportFormat | str | None = None,
) -> ImportResult:
    """Import an OCEL source and preserve all available diagnostic evidence."""

    source_text = os.fspath(source)
    if not isinstance(source_text, str):
        raise TypeError("source must resolve to a string path")
    if not source_text.strip():
        raise ValueError("source must not be empty")

    requested_format = _normalize_format(format)
    path = Path(source_text)
    inferred_format = requested_format or _format_from_name(path.name)
    is_bundle_directory = path.is_dir() and (
        requested_format is ImportFormat.OCEL21_BUNDLE
        or (requested_format is None and (path / "ocel-meta.json").is_file())
    )
    if is_bundle_directory:
        inferred_format = ImportFormat.OCEL21_BUNDLE
    if not path.is_file() and not is_bundle_directory:
        return _failure(
            source=source_text,
            format=inferred_format,
            status=ImportStatus.UNAVAILABLE,
            stage=ImportStage.SOURCE,
            code="source_unavailable",
            message="Source path does not identify a readable file.",
        )

    try:
        if is_bundle_directory:
            bundled = import_module("pix.ocel.ingest.formats.bundled")
            source_sha256, source_size, magic = bundled.source_evidence(path)
        else:
            source_sha256, source_size, magic = _source_evidence(path)
    except AdapterFailure as exc:
        return _failure(
            source=source_text,
            format=inferred_format,
            status=exc.status,
            stage=exc.stage,
            code=exc.code,
            message=str(exc),
            at=exc.at,
        )
    except OSError as exc:
        return _failure(
            source=source_text,
            format=inferred_format,
            status=ImportStatus.UNAVAILABLE,
            stage=ImportStage.SOURCE,
            code="source_unreadable",
            message=str(exc),
        )

    detected_format = inferred_format or _format_from_magic(magic)
    if requested_format is None:
        family = detect_log_family(path)
        if family in ("xes", "mxml"):
            return _failure(
                source=source_text,
                format=None,
                status=ImportStatus.UNSUPPORTED,
                stage=ImportStage.PROFILE,
                code="case_log_requires_native_import",
                message="Use pix.io.read_log or pix.event_log for case-centric logs; "
                "OCEL conversion is an explicit operation.",
                source_sha256=source_sha256,
                source_size=source_size,
            )
        if family is not None:
            detected_format = ImportFormat(family)
    if detected_format not in _LOADERS and detected_format not in _EXTENDED_LOADERS:
        return _failure(
            source=source_text,
            format=None,
            status=ImportStatus.UNSUPPORTED,
            stage=ImportStage.SOURCE,
            code="unsupported_format",
            message="Source is not a supported OCEL file. Generic tables require "
            "an explicit mapping through pix.io.import_log or pix.tabular.",
            source_sha256=source_sha256,
            source_size=source_size,
        )

    try:
        if detected_format in _LOADERS:
            loader = _LOADERS[detected_format]
        else:
            module, function = _EXTENDED_LOADERS[detected_format]
            loader = getattr(
                import_module(f"pix.ocel.ingest.formats.{module}"), function
            )
        build_result, transformations = loader(path)
    except AdapterFailure as exc:
        return _failure(
            source=source_text,
            format=detected_format,
            status=exc.status,
            stage=exc.stage,
            code=exc.code,
            message=str(exc),
            at=exc.at,
            source_sha256=source_sha256,
            source_size=source_size,
        )

    import_issues, read_warnings = _timezone_warnings(transformations)
    import_info = _import_info(
        source=source_text,
        format=detected_format,
        source_sha256=source_sha256,
        transformations=transformations,
        warnings=read_warnings,
    )
    candidate = replace(build_result.candidate, import_info=import_info)

    if not build_result.valid:
        return ImportResult(
            source=source_text,
            format=detected_format,
            status=ImportStatus.SEMANTIC_INVALID,
            candidate=candidate,
            import_issues=import_issues,
            semantic_report=build_result.report,
            transformations=transformations,
            source_sha256=source_sha256,
            source_size=source_size,
        )

    return ImportResult(
        source=source_text,
        format=detected_format,
        status=ImportStatus.VALID,
        candidate=candidate,
        import_issues=import_issues,
        semantic_report=build_result.report,
        transformations=transformations,
        source_sha256=source_sha256,
        source_size=source_size,
        canonical_digest=canonical_digest(candidate),
    )


def read_ocel(
    source: Source,
    *,
    format: ImportFormat | str | None = None,
) -> OCEL:
    """Return a valid canonical OCEL or raise an evidence-carrying error."""

    ocel = import_ocel(source, format=format).require_ocel()
    for warning in ocel.warnings:
        if warning.code == "timezone_assumed_utc":
            runtime_warnings.warn(
                warning.message,
                TimezoneAssumptionWarning,
                stacklevel=2,
            )
    return ocel


def _normalize_format(value: ImportFormat | str | None) -> ImportFormat | None:
    if value is None or isinstance(value, ImportFormat):
        return value
    if not isinstance(value, str):
        raise TypeError("format must be ImportFormat, str, or None")
    normalized = value.strip().lower().lstrip(".")
    try:
        return _FORMAT_ALIASES[normalized]
    except KeyError as exc:
        supported = ", ".join(item.value for item in ImportFormat)
        raise ValueError(
            f"unsupported format '{value}'; expected one of: {supported}"
        ) from exc


def _format_from_name(name: str) -> ImportFormat | None:
    lowered = name.lower()
    if lowered.endswith((".ocel.csv", ".ocel.csv.gz")):
        return ImportFormat.OCEL21_CSV
    if lowered.endswith(".ocel.zip"):
        return ImportFormat.OCEL21_BUNDLE
    if lowered.endswith((".json", ".jsonocel", ".json.gz", ".jsonocel.gz")):
        return ImportFormat.OCEL20_JSON
    if lowered.endswith((".xml", ".xmlocel", ".xml.gz", ".xmlocel.gz")):
        return ImportFormat.OCEL20_XML
    if lowered.endswith((".sqlite", ".sqlite3", ".db")):
        return ImportFormat.OCEL20_SQLITE
    return None


def _format_from_magic(value: bytes) -> ImportFormat | None:
    if value.startswith(b"SQLite format 3\x00"):
        return ImportFormat.OCEL20_SQLITE
    stripped = value.lstrip()
    if stripped.startswith((b"{", b"[")):
        return ImportFormat.OCEL20_JSON
    if stripped.startswith(b"<"):
        return ImportFormat.OCEL20_XML
    return None


def _source_evidence(path: Path) -> tuple[str, int, bytes]:
    digest = hashlib.sha256()
    size = 0
    magic = b""
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            if not magic:
                magic = chunk[:64]
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size, magic


def _timezone_warnings(
    transformations: tuple[Transformation, ...],
) -> tuple[tuple[ImportIssue, ...], tuple[OCELWarning, ...]]:
    assumed_count = _transformation_count(
        transformations,
        "timezone_assumed_utc",
    )
    if not assumed_count:
        return (), ()
    message = (
        f"Assumed UTC for {assumed_count} timestamp values that did not contain "
        "timezone information. Inspect log.timezone_info for details."
    )
    return (
        (
            ImportIssue(
                stage=ImportStage.PROFILE,
                code="timezone_assumed_utc",
                message=message,
                level=Level.WARNING,
            ),
        ),
        (
            OCELWarning(
                code="timezone_assumed_utc",
                message=message,
                count=assumed_count,
            ),
        ),
    )


def _import_info(
    *,
    source: str,
    format: ImportFormat,
    source_sha256: str,
    transformations: tuple[Transformation, ...],
    warnings: tuple[OCELWarning, ...],
) -> OCELImportInfo:
    normalized_count = _transformation_count(
        transformations,
        "timezone_to_utc",
    )
    legacy_count = _transformation_count(
        transformations,
        "legacy_timestamp_parsed",
    )
    assumed_count = _transformation_count(
        transformations,
        "timezone_assumed_utc",
    )
    if assumed_count and (normalized_count or legacy_count):
        source_type = "MIXED_WITH_ASSUMED_UTC"
    elif assumed_count:
        source_type = "ASSUMED_UTC"
    elif legacy_count:
        source_type = "LEGACY_OFFSET_AWARE"
    elif normalized_count:
        source_type = "OFFSET_AWARE"
    else:
        source_type = "UTC"
    return OCELImportInfo(
        source=source,
        format=format.value,
        source_sha256=source_sha256,
        timezone=TimezoneInfo(
            source_type=source_type,
            normalized_offset_count=normalized_count,
            legacy_offset_count=legacy_count,
            assumed_utc_count=assumed_count,
        ),
        warnings=warnings,
    )


def _transformation_count(
    transformations: tuple[Transformation, ...],
    code: str,
) -> int:
    return sum(value.count or 0 for value in transformations if value.code == code)


def _failure(
    *,
    source: str,
    format: ImportFormat | None,
    status: ImportStatus,
    stage: ImportStage,
    code: str,
    message: str,
    at: tuple[str, ...] = (),
    source_sha256: str | None = None,
    source_size: int | None = None,
) -> ImportResult:
    return ImportResult(
        source=source,
        format=format,
        status=status,
        candidate=None,
        import_issues=(
            ImportIssue(
                stage=stage,
                code=code,
                message=message,
                at=at,
            ),
        ),
        source_sha256=source_sha256,
        source_size=source_size,
    )


__all__ = [
    "Source",
    "TimezoneAssumptionWarning",
    "import_ocel",
    "read_ocel",
]
