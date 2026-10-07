"""Explicit observational policies for native projection-based OCPN discovery."""

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class OCPNDiscoverySpec:
    """Whole-log events, selected object universe, and explicit merge policies.

    ``observed_range`` converts observed marginal cardinality support to its
    closed integer interval. It permits unobserved intermediate counts and
    combinations across types, and is not a normative process constraint.
    ``unique_activity`` refuses multiple local transitions with one activity.
    """

    object_types: tuple[str, ...]
    cardinality_policy: str
    merge_policy: str
    qualifiers: tuple[str, ...] | None = None
    tie_policy: str = "reject"
    classic_algorithm: str = "pix.inductive_cut.v1"
    max_depth: int = 128
    max_fitting_states_per_object: int = 10000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if not isinstance(self.object_types, tuple) or not all(
            isinstance(item, str) for item in self.object_types
        ):
            raise TypeError("object_types must be a tuple of strings")
        if not self.object_types or any(not item.strip() for item in self.object_types):
            raise ValueError("object_types must select nonblank type names")
        if len(set(self.object_types)) != len(self.object_types):
            raise ValueError("object_types must be unique")
        for item in self.object_types:
            item.encode("utf-8")
        object.__setattr__(self, "object_types", tuple(sorted(self.object_types)))
        if self.qualifiers is not None:
            if not isinstance(self.qualifiers, tuple) or not all(
                isinstance(item, str) for item in self.qualifiers
            ):
                raise TypeError("qualifiers must be None or a tuple of strings")
            if len(set(self.qualifiers)) != len(self.qualifiers):
                raise ValueError("qualifiers must be unique")
            for item in self.qualifiers:
                item.encode("utf-8")
            object.__setattr__(self, "qualifiers", tuple(sorted(self.qualifiers)))
        if self.cardinality_policy != "observed_range":
            raise ValueError("only the explicit observed_range policy is supported")
        if self.merge_policy != "unique_activity":
            raise ValueError("only the explicit unique_activity merge is supported")
        if self.tie_policy not in ("reject", "event_id"):
            raise ValueError("tie_policy must be reject or event_id")
        if self.classic_algorithm not in ("pix.inductive_cut.v1", "pix.im.v1"):
            raise ValueError("unsupported native classic discovery algorithm")
        for name in ("max_depth", "max_fitting_states_per_object"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value < 1:
                raise ValueError(f"{name} must be positive")
        if self.max_depth > 128:
            raise ValueError("max_depth must not exceed 128")


__all__ = ("OCPNDiscoverySpec",)
