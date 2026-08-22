"""Contracts for versioned PIX OCEL canonical representations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pix.ocel.report import Report


class CanonicalVersion(str, Enum):
    """Immutable identifier for one canonical byte representation."""

    V1 = "pix.ocel.canonical.v1"


CURRENT_CANONICAL_VERSION = CanonicalVersion.V1


@dataclass(frozen=True, slots=True)
class CanonicalDigest:
    """Content digest over one versioned canonical OCEL representation."""

    version: CanonicalVersion
    algorithm: str
    hexdigest: str

    def __post_init__(self) -> None:
        if not isinstance(self.version, CanonicalVersion):
            raise TypeError("CanonicalDigest.version must be CanonicalVersion")

        if self.algorithm != "sha256":
            raise ValueError("CanonicalDigest.algorithm must be 'sha256'")

        if not isinstance(self.hexdigest, str):
            raise TypeError("CanonicalDigest.hexdigest must be a string")

        if len(self.hexdigest) != 64:
            raise ValueError(
                "CanonicalDigest.hexdigest must contain 64 hexadecimal characters"
            )

        if any(character not in "0123456789abcdef" for character in self.hexdigest):
            raise ValueError(
                "CanonicalDigest.hexdigest must be lowercase hexadecimal"
            )

    @property
    def identifier(self) -> str:
        """Return a self-describing digest identifier."""

        return f"{self.version.value}:{self.algorithm}:{self.hexdigest}"


class CanonicalizationError(ValueError):
    """Raised when an invalid OCEL cannot receive canonical identity."""

    def __init__(self, report: Report) -> None:
        if not isinstance(report, Report):
            raise TypeError("report must be Report")

        super().__init__(
            "OCEL is not semantically valid and cannot receive canonical identity"
        )
        self.report = report


__all__ = [
    "CURRENT_CANONICAL_VERSION",
    "CanonicalDigest",
    "CanonicalVersion",
    "CanonicalizationError",
]
