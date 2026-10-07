"""Source-facing metadata attached to a read OCEL without changing identity."""

from __future__ import annotations

from dataclasses import dataclass


def _require_nonnegative(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an integer")
    if value < 0:
        raise ValueError(f"{field} must not be negative")


@dataclass(frozen=True, slots=True)
class OCELWarning:
    """One aggregated warning retained on an imported OCEL."""

    code: str
    message: str
    count: int

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("OCELWarning.code must be a nonblank string")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("OCELWarning.message must be a nonblank string")
        _require_nonnegative(self.count, "OCELWarning.count")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class TimezoneInfo:
    """How source timestamps became the canonical UTC representation."""

    canonical_timezone: str = "UTC"
    source_type: str = "UTC"
    normalized_offset_count: int = 0
    legacy_offset_count: int = 0
    assumed_utc_count: int = 0

    def __post_init__(self) -> None:
        if self.canonical_timezone != "UTC":
            raise ValueError("canonical_timezone must be UTC")
        if not isinstance(self.source_type, str) or not self.source_type.strip():
            raise ValueError("source_type must be a nonblank string")
        for field, value in (
            ("normalized_offset_count", self.normalized_offset_count),
            ("legacy_offset_count", self.legacy_offset_count),
            ("assumed_utc_count", self.assumed_utc_count),
        ):
            _require_nonnegative(value, field)

    @property
    def assumption_used(self) -> bool:
        return self.assumed_utc_count > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "canonicalTimezone": self.canonical_timezone,
            "sourceType": self.source_type,
            "normalizedOffsetCount": self.normalized_offset_count,
            "legacyOffsetCount": self.legacy_offset_count,
            "assumedUtcCount": self.assumed_utc_count,
            "assumptionUsed": self.assumption_used,
        }


@dataclass(frozen=True, slots=True)
class OCELImportInfo:
    """Non-canonical provenance available on an OCEL returned by a reader."""

    source: str
    format: str
    source_sha256: str
    timezone: TimezoneInfo
    warnings: tuple[OCELWarning, ...] = ()

    def __post_init__(self) -> None:
        for field, value in (
            ("source", self.source),
            ("format", self.format),
            ("source_sha256", self.source_sha256),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a nonblank string")
        if not isinstance(self.timezone, TimezoneInfo):
            raise TypeError("timezone must be TimezoneInfo")
        if not isinstance(self.warnings, tuple) or not all(
            isinstance(value, OCELWarning) for value in self.warnings
        ):
            raise TypeError("warnings must be a tuple of OCELWarning")

    def to_dict(self) -> dict[str, object]:
        return {
            "source": self.source,
            "format": self.format,
            "sourceSha256": self.source_sha256,
            "timezone": self.timezone.to_dict(),
            "warnings": tuple(value.to_dict() for value in self.warnings),
        }


__all__ = ["OCELImportInfo", "OCELWarning", "TimezoneInfo"]
