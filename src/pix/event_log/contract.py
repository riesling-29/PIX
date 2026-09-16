"""Diagnostic case-log import transactions; valid storage need not be analyzable."""

from __future__ import annotations

from dataclasses import dataclass

from pix.event_log.model import CaseLog, _text, _tuple
from pix.ocel.ingest.contract import ImportIssue, ImportStatus, Transformation
from pix.ocel.report import Level


@dataclass(frozen=True, slots=True)
class CaseImportResult:
    source: str
    format: str
    status: ImportStatus
    candidate: CaseLog | None
    import_issues: tuple[ImportIssue, ...] = ()
    transformations: tuple[Transformation, ...] = ()
    source_sha256: str | None = None
    source_size: int | None = None

    def __post_init__(self) -> None:
        _text(self.source, "source")
        _text(self.format, "format")
        if not isinstance(self.status, ImportStatus):
            raise TypeError("status must be ImportStatus")
        _tuple(self.import_issues, ImportIssue, "import_issues")
        _tuple(self.transformations, Transformation, "transformations")
        if self.status is ImportStatus.VALID:
            if not isinstance(self.candidate, CaseLog):
                raise ValueError("valid import requires CaseLog")
            if any(issue.level is Level.ERROR for issue in self.import_issues):
                raise ValueError("valid import cannot have error issues")
        elif self.candidate is not None or not any(
            i.level is Level.ERROR for i in self.import_issues
        ):
            raise ValueError("failed case import requires errors and no candidate")
        if self.source_sha256 is not None and (
            len(self.source_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.source_sha256)
        ):
            raise ValueError("source_sha256 must be lowercase SHA-256")
        if self.source_size is not None and (
            type(self.source_size) is not int or self.source_size < 0
        ):
            raise ValueError("source_size must be nonnegative int")

    @property
    def valid(self) -> bool:
        return self.status is ImportStatus.VALID

    @property
    def case_log(self) -> CaseLog | None:
        return self.candidate if self.valid else None

    def require_case_log(self) -> CaseLog:
        if self.case_log is None:
            raise CaseImportError(self)
        return self.case_log

    def summary(self) -> str:
        return f"CaseImportResult(status={self.status.value}, format={self.format})"

    def describe(self) -> dict[str, object]:
        return {
            "source": self.source,
            "format": self.format,
            "status": self.status.value,
            "valid": self.valid,
            "sourceSha256": self.source_sha256,
            "sourceSize": self.source_size,
            "issues": tuple(
                {
                    "stage": i.stage.value,
                    "code": i.code,
                    "message": i.message,
                    "level": i.level.value,
                    "at": i.at,
                }
                for i in self.import_issues
            ),
            "candidate": self.candidate.describe() if self.candidate else None,
            "transformations": tuple(
                {"code": t.code, "message": t.message, "at": t.at, "count": t.count}
                for t in self.transformations
            ),
        }


class CaseImportError(ValueError):
    def __init__(self, result: CaseImportResult) -> None:
        self.result = result
        super().__init__(result.summary())
