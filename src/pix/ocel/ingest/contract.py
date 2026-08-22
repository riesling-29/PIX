"""Evidence-preserving contracts for OCEL importers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pix.ocel.canonical import CanonicalDigest, canonical_digest
from pix.ocel.model import OCEL
from pix.ocel.report import Level, Report
from pix.ocel.validate import validate


class ImportFormat(str, Enum):
    """Supported external OCEL representations."""

    OCEL20_JSON = "ocel20-json"
    OCEL20_XML = "ocel20-xml"
    OCEL20_SQLITE = "ocel20-sqlite"


class ImportStatus(str, Enum):
    """Terminal state of one source import transaction."""

    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    SYNTAX_INVALID = "syntax_invalid"
    SCHEMA_INVALID = "schema_invalid"
    MAPPING_INVALID = "mapping_invalid"
    SEMANTIC_INVALID = "semantic_invalid"
    VALID = "valid"


class ImportStage(str, Enum):
    """Import stage that produced one source-facing issue."""

    SOURCE = "source"
    SYNTAX = "syntax"
    SCHEMA = "schema"
    MAPPING = "mapping"
    SEMANTIC = "semantic"
    PROFILE = "profile"


def _require_text(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    if not value.strip():
        raise ValueError(f"{field} must not be empty")


def _require_location(value: object, field: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")

    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"every item in {field} must be str")


def _require_sha256(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field} must be lowercase SHA-256 hexadecimal")


@dataclass(frozen=True, slots=True)
class ImportIssue:
    """One source, syntax, mapping, or profile issue."""

    stage: ImportStage
    code: str
    message: str
    level: Level = Level.ERROR
    at: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.stage, ImportStage):
            raise TypeError("ImportIssue.stage must be ImportStage")

        _require_text(self.code, "ImportIssue.code")
        _require_text(self.message, "ImportIssue.message")

        if not isinstance(self.level, Level):
            raise TypeError("ImportIssue.level must be Level")

        _require_location(self.at, "ImportIssue.at")


@dataclass(frozen=True, slots=True)
class Transformation:
    """One disclosed representation change made during import."""

    code: str
    message: str
    at: tuple[str, ...] = ()
    count: int | None = None

    def __post_init__(self) -> None:
        _require_text(self.code, "Transformation.code")
        _require_text(self.message, "Transformation.message")
        _require_location(self.at, "Transformation.at")
        if self.count is not None:
            if isinstance(self.count, bool) or not isinstance(self.count, int):
                raise TypeError("Transformation.count must be int or None")
            if self.count < 0:
                raise ValueError("Transformation.count must not be negative")


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Immutable result of one future source import transaction.

    ``candidate`` preserves a fully parsed OCEL even when semantic validation
    fails. ``ocel`` exposes it only for a valid import. Syntax-invalid,
    unsupported, and unavailable sources do not produce an OCEL candidate.
    """

    source: str
    format: ImportFormat | None
    status: ImportStatus
    candidate: OCEL | None
    import_issues: tuple[ImportIssue, ...] = ()
    semantic_report: Report | None = None
    transformations: tuple[Transformation, ...] = ()
    source_sha256: str | None = None
    source_size: int | None = None
    canonical_digest: CanonicalDigest | None = None

    def __post_init__(self) -> None:
        _require_text(self.source, "ImportResult.source")

        if self.format is not None and not isinstance(self.format, ImportFormat):
            raise TypeError("ImportResult.format must be ImportFormat or None")

        if not isinstance(self.status, ImportStatus):
            raise TypeError("ImportResult.status must be ImportStatus")

        if self.candidate is not None and not isinstance(self.candidate, OCEL):
            raise TypeError("ImportResult.candidate must be OCEL or None")

        self._require_tuple(
            self.import_issues,
            ImportIssue,
            "ImportResult.import_issues",
        )
        self._require_tuple(
            self.transformations,
            Transformation,
            "ImportResult.transformations",
        )

        if self.semantic_report is not None and not isinstance(
            self.semantic_report, Report
        ):
            raise TypeError("ImportResult.semantic_report must be Report or None")

        if self.source_sha256 is not None:
            _require_sha256(self.source_sha256, "ImportResult.source_sha256")

        if self.source_size is not None:
            if not isinstance(self.source_size, int):
                raise TypeError("ImportResult.source_size must be int or None")
            if self.source_size < 0:
                raise ValueError("ImportResult.source_size must not be negative")

        if self.canonical_digest is not None and not isinstance(
            self.canonical_digest, CanonicalDigest
        ):
            raise TypeError(
                "ImportResult.canonical_digest must be CanonicalDigest or None"
            )

        self._validate_status_invariants()

    @staticmethod
    def _require_tuple(
        value: object,
        item_type: type[object],
        field: str,
    ) -> None:
        if not isinstance(value, tuple):
            raise TypeError(f"{field} must be a tuple")

        if not all(isinstance(item, item_type) for item in value):
            raise TypeError(
                f"every item in {field} must be {item_type.__name__}"
            )

    def _validate_status_invariants(self) -> None:
        error_issues = tuple(
            issue for issue in self.import_issues if issue.level is Level.ERROR
        )

        if self.status is ImportStatus.VALID:
            if self.candidate is None:
                raise ValueError("valid import requires candidate")
            if self.semantic_report is None or not self.semantic_report.valid:
                raise ValueError("valid import requires valid semantic report")
            if self.canonical_digest is None:
                raise ValueError("valid import requires canonical digest")
            if error_issues:
                raise ValueError("valid import cannot contain error import issues")
            if self.semantic_report != validate(self.candidate):
                raise ValueError("semantic report must describe candidate")
            if self.canonical_digest != canonical_digest(self.candidate):
                raise ValueError("canonical digest must identify candidate")
            return

        if self.canonical_digest is not None:
            raise ValueError("non-valid import cannot have canonical digest")

        if self.status is ImportStatus.SEMANTIC_INVALID:
            if self.candidate is None:
                raise ValueError("semantic-invalid import requires candidate")
            if self.semantic_report is None or self.semantic_report.valid:
                raise ValueError(
                    "semantic-invalid import requires invalid semantic report"
                )
            if self.semantic_report != validate(self.candidate):
                raise ValueError("semantic report must describe candidate")
            return

        if self.candidate is not None:
            raise ValueError(
                "pre-semantic import failures "
                "cannot have candidate"
            )

        if self.semantic_report is not None:
            raise ValueError(
                "import without candidate cannot have semantic report"
            )

        if not error_issues:
            raise ValueError("non-semantic import failure requires error issue")

    @property
    def valid(self) -> bool:
        return self.status is ImportStatus.VALID

    @property
    def ocel(self) -> OCEL | None:
        if self.valid:
            return self.candidate

        return None

    def require_ocel(self) -> OCEL:
        """Return the valid OCEL or raise an error carrying this result."""

        ocel = self.ocel
        if ocel is None:
            raise OCELImportError(self)
        return ocel

    def describe(self) -> dict[str, object]:
        """Return a stable result description suitable for people and AI."""

        description: dict[str, object] = {
            "source": self.source,
            "format": self.format.value if self.format is not None else None,
            "status": self.status.value,
            "valid": self.valid,
            "sourceSha256": self.source_sha256,
            "sourceSize": self.source_size,
            "canonicalDigest": (
                self.canonical_digest.identifier
                if self.canonical_digest is not None
                else None
            ),
            "issues": tuple(
                {
                    "stage": issue.stage.value,
                    "level": issue.level.value,
                    "code": issue.code,
                    "message": issue.message,
                    "at": issue.at,
                }
                for issue in self.import_issues
            ),
            "semanticIssues": tuple(
                {
                    "level": issue.level.value,
                    "code": issue.code,
                    "message": issue.message,
                    "at": issue.at,
                }
                for issue in (
                    self.semantic_report.issues
                    if self.semantic_report is not None
                    else ()
                )
            ),
            "transformations": tuple(
                {
                    "code": value.code,
                    "message": value.message,
                    "at": value.at,
                    "count": value.count,
                }
                for value in self.transformations
            ),
        }
        if self.candidate is not None:
            description["candidate"] = self.candidate.describe()
        return description

    def summary(self) -> str:
        """Return a compact human-readable import summary."""

        detail = self.candidate.summary() if self.candidate is not None else "no OCEL"
        return (
            f"ImportResult(status={self.status.value}, "
            f"format={self.format.value if self.format else 'unknown'}, {detail})"
        )


class OCELImportError(ValueError):
    """Raised by convenience readers when an import did not produce an OCEL."""

    def __init__(self, result: ImportResult) -> None:
        if not isinstance(result, ImportResult):
            raise TypeError("result must be ImportResult")
        super().__init__(result.summary())
        self.result = result


__all__ = [
    "ImportFormat",
    "ImportIssue",
    "ImportResult",
    "ImportStage",
    "ImportStatus",
    "OCELImportError",
    "Transformation",
]
