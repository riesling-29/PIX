"""Explicit source-order projection of a native case log for classical mining."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class CaseTraceSpec:
    """Classifier selection does not sort events or invent event timestamps."""

    activity_key: str = "concept:name"
    timestamp_key: str = "time:timestamp"
    classifier: str | None = None
    object_type: str = "case"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("activity_key", "timestamp_key", "object_type"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonblank text")
        if self.classifier is not None and (
            not isinstance(self.classifier, str) or not self.classifier.strip()
        ):
            raise ValueError("classifier must be nonblank text or None")


__all__ = ["CaseTraceSpec"]
