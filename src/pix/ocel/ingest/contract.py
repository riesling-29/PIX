"""Evidence-preserving contracts for future OCEL importers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pix.ocel.canonical import CanonicalDigest
from pix.ocel.model import OCEL
from pix.ocel.report import Level, Report


class ImportStatus(str, Enum):
    """Terminal state of one source import transaction."""

    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    SYNTAX_INVALID = "syntax_invalid"
    SEMANTIC_INVALID = "semantic_invalid"
    VALID = "valid"


class ImportStage(str, Enum):
    """Import stage that produced one source-facing issue."""

    SOURCE = "source"
    SYNTAX = "syntax"
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

    def __post_init__(self) -> None:
        _require_text(self.code, "Transformation.code")
        _require_text(self.message, "Transformation.message")
        _require_location(self.at, "Transformation.at")


@dataclass(frozen=True, slots=True)
class ImportResult:
    """Immutable result of one future source import transaction.

    ``candidate`` preserves a fully parsed OCEL even when semantic validation
    fails. ``ocel`` exposes it only for a valid import. Syntax-invalid,
    unsupported, and unavailable sources do not produce an OCEL candidate.
    """

    source: str
    format: str | None
    status: ImportStatus
    candidate: OCEL | None
    import_issues: tuple[ImportIssue, ...] = ()
    semantic_report: Report | None = None
    transformations: tuple[Transformation, ...] = ()
    source_sha256: str | None = None
    canonical_digest: CanonicalDigest | None = None

    def __post_init__(self) -> None:
        _require_text(self.source, "ImportResult.source")

        if self.format is not None:
            _require_text(self.format, "ImportResult.format")

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
            return

        if self.candidate is not None:
            raise ValueError(
                "unavailable, unsupported, and syntax-invalid imports "
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


__all__ = [
    "ImportIssue",
    "ImportResult",
    "ImportStage",
    "ImportStatus",
    "Transformation",
]
