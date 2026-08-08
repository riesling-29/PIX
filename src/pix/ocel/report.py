"""Validation report contracts for the PIX OCEL data model.

This module describes semantic validation results only.

It does not contain file-source locations, importer diagnostics,
rejected source records, normalization policies, or repair logic.
Those responsibilities belong to later ingestion layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Level(str, Enum):
    """Severity level of a semantic validation issue."""

    ERROR = "error"
    WARNING = "warning"


def _require_text(value: object, field: str) -> None:
    """Require a non-blank string without coercion."""

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    if not value.strip():
        raise ValueError(f"{field} must not be empty")


def _require_tuple(
    value: object,
    item_type: type[object],
    field: str,
) -> None:
    """Require an immutable tuple containing one expected item type."""

    if not isinstance(value, tuple):
        raise TypeError(f"{field} must be a tuple")

    if not all(isinstance(item, item_type) for item in value):
        raise TypeError(f"every item in {field} must be {item_type.__name__}")


@dataclass(frozen=True, slots=True)
class Issue:
    """One semantic issue found in an OCEL dataset.

    ``at`` identifies a semantic location inside the OCEL data model.

    Examples:

        ("event", "e1")
        ("object", "o1")
        ("event_type", "create")
        ("event", "e1", "attribute", "amount")
        ("e2o", "e1", "o1", "item")

    It is intentionally not a source-file location such as a CSV row,
    JSON pointer, XML path, or SQLite row id.
    """

    code: str
    message: str
    level: Level = Level.ERROR
    at: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.code, "Issue.code")
        _require_text(self.message, "Issue.message")

        if not isinstance(self.level, Level):
            raise TypeError("Issue.level must be Level")

        _require_tuple(
            self.at,
            str,
            "Issue.at",
        )


@dataclass(frozen=True, slots=True)
class Report:
    """Immutable collection of OCEL semantic validation issues."""

    issues: tuple[Issue, ...] = ()

    def __post_init__(self) -> None:
        _require_tuple(
            self.issues,
            Issue,
            "Report.issues",
        )

    @property
    def valid(self) -> bool:
        """Whether the report contains no validation errors."""

        return not any(issue.level is Level.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[Issue, ...]:
        """Return only error-level issues."""

        return tuple(issue for issue in self.issues if issue.level is Level.ERROR)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        """Return only warning-level issues."""

        return tuple(issue for issue in self.issues if issue.level is Level.WARNING)

    def has(self, code: str) -> bool:
        """Return whether the report contains an issue with the given code."""

        _require_text(code, "code")

        return any(issue.code == code for issue in self.issues)


__all__ = [
    "Issue",
    "Level",
    "Report",
]
