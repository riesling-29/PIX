"""Unified log import that preserves native OCEL or case-centric semantics.

XES/MXML are not silently converted to OCEL. Generic business tables require a
mapping; a filename cannot identify their case notion or object relationships.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Mapping

if TYPE_CHECKING:
    from pix.event_log import CaseImportResult, CaseLog
    from pix.ocel import OCEL, ImportFormat, ImportResult
    from pix.tabular import CaseTableMapping, OCELTableMapping


def import_log(
    source: str | os.PathLike[str] | Iterable[Mapping[str, object]],
    *,
    format: ImportFormat | str | None = None,
    mapping: CaseTableMapping | OCELTableMapping | None = None,
    sheet: str | int | None = None,
    delimiter: str | None = None,
    encoding: str = "utf-8",
) -> ImportResult | CaseImportResult:
    """Return a typed result with diagnostics and source identity.

    Format chooses a parser, never an OCEL↔case conversion. For tabular inputs,
    the explicit mapping determines which native data model is produced.
    """
    from pix.ocel.ingest.contract import ImportFormat
    from pix.ocel.ingest.detection import detect_log_family
    from pix.ocel.ingest.reader import import_ocel

    requested = format.value if isinstance(format, ImportFormat) else format
    if requested is not None:
        if not isinstance(requested, str):
            raise TypeError("format must be text, ImportFormat, or None")
        requested = requested.strip().lower().lstrip(".")
    table_formats = {
        "csv",
        "tsv",
        "xlsx",
        "excel",
        "table-csv",
        "table-tsv",
        "table-xlsx",
        "table-records",
        "records",
    }
    if mapping is not None:
        if requested is not None and requested not in table_formats:
            raise ValueError("a table mapping cannot be applied to a log serialization")
        from pix.tabular import import_table

        if delimiter is None:
            is_tsv = requested in {"tsv", "table-tsv"} or (
                isinstance(source, (str, os.PathLike))
                and os.fspath(source).lower().endswith((".tsv", ".tsv.gz"))
            )
            delimiter = "\t" if is_tsv else ","
        return import_table(
            source,
            mapping,
            format=requested,
            sheet=sheet,
            delimiter=delimiter,
            encoding=encoding,
        )
    if sheet is not None or delimiter is not None or encoding != "utf-8":
        raise ValueError("tabular reading options require an explicit mapping")
    if not isinstance(source, (str, os.PathLike)):
        raise ValueError("in-memory rows require an explicit table mapping")
    path_text = os.fspath(source)
    if not isinstance(path_text, str) or not path_text.strip():
        raise ValueError("source must be a nonblank text path")
    path = Path(path_text)
    if requested in table_formats or (
        requested is None
        and path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz", ".xlsx"))
        and not path.name.lower().endswith((".ocel.csv", ".ocel.csv.gz"))
    ):
        return _mapping_required(path)
    family = requested or detect_log_family(path)
    if family in ("xes", "xes.gz"):
        from pix.event_log import import_xes

        return import_xes(path)
    if family in ("mxml", "mxml.gz"):
        from pix.event_log import import_mxml

        return import_mxml(path)
    return import_ocel(path, format=requested)


def read_log(
    source: str | os.PathLike[str] | Iterable[Mapping[str, object]],
    *,
    format: ImportFormat | str | None = None,
    mapping: CaseTableMapping | OCELTableMapping | None = None,
    sheet: str | int | None = None,
    delimiter: str | None = None,
    encoding: str = "utf-8",
) -> OCEL | CaseLog:
    """Return a valid immutable native log or raise its evidence-carrying error."""
    from pix.ocel import ImportResult, TimezoneAssumptionWarning

    result = import_log(
        source,
        format=format,
        mapping=mapping,
        sheet=sheet,
        delimiter=delimiter,
        encoding=encoding,
    )
    if isinstance(result, ImportResult):
        log = result.require_ocel()
        for issue in log.warnings:
            if issue.code == "timezone_assumed_utc":
                warnings.warn(issue.message, TimezoneAssumptionWarning, stacklevel=2)
        return log
    return result.require_case_log()


def _mapping_required(path: Path) -> ImportResult:
    from pix.ocel.ingest.contract import ImportStage, ImportStatus
    from pix.ocel.ingest.reader import _failure, _source_evidence

    digest, size = None, None
    try:
        if path.is_file():
            digest, size, _ = _source_evidence(path)
    except OSError:
        pass
    return _failure(
        source=str(path),
        format=None,
        status=ImportStatus.UNSUPPORTED,
        stage=ImportStage.PROFILE,
        code="table_mapping_required",
        message="Choose CaseTableMapping or OCELTableMapping explicitly; "
        "PIX does not infer case IDs, activities, timestamps, or object relationships.",
        source_sha256=digest,
        source_size=size,
    )


__all__ = ["import_log", "read_log"]
