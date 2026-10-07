"""Immutable contracts for explicitly versioned, noise-free trace discovery.

``pix.inductive_cut.v1`` is a conservative native algorithm, not a claim of
equivalence to the Inductive Miner reference algorithms. ``pix.im.v1`` is PIX's
complete log-based IM profile: formal cuts with plain sequence and a documented
fallthrough order. Neither name aliases IMf, IMd, or a PM4Py release.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal

TreeOperator = Literal["activity", "tau", "sequence", "xor", "parallel", "loop"]


@dataclass(frozen=True, slots=True)
class DiscoverySpec:
    """Trace-input discovery; no DFG conversion or frequency filtering.

    Both miners retain observed traces. This does not establish precision or
    recover the generating process. A reported flower fallback admits arbitrary
    strings of its alphabet: the conservative profile excludes epsilon, while
    ``pix.im.v1`` includes epsilon. ``max_depth`` is an explicit search
    boundary: exhaustion returns unavailable, not a partially discovered tree.
    """

    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    algorithm: str = "pix.inductive_cut.v1"
    noise_threshold: float = 0.0
    max_depth: int = 128

    def __post_init__(self) -> None:
        if not isinstance(self.algorithm, str):
            raise TypeError("algorithm must be text")
        if self.algorithm not in ("pix.inductive_cut.v1", "pix.im.v1"):
            raise ValueError(
                "supported algorithms are pix.inductive_cut.v1 and pix.im.v1"
            )
        if isinstance(self.noise_threshold, bool) or not isinstance(
            self.noise_threshold, (int, float)
        ):
            raise TypeError("noise_threshold must be a number")
        if self.noise_threshold != 0:
            raise ValueError("only noise_threshold=0 is implemented")
        object.__setattr__(self, "noise_threshold", 0.0)
        if isinstance(self.max_depth, bool) or not isinstance(self.max_depth, int):
            raise TypeError("max_depth must be int")
        if not 1 <= self.max_depth <= 128:
            raise ValueError("max_depth must be between 1 and 128")


@dataclass(frozen=True, slots=True)
class ProcessTree:
    """Block-structured behavior with explicit silent and loop semantics.

    Sequence preserves child order; XOR selects one child; parallel shuffles
    all child behaviors. A binary loop has language ``do (redo do)*``. Activity
    labels are display/behavior labels, not unique transition identities.
    """

    operator: TreeOperator
    activity: str | None = None
    children: tuple[ProcessTree, ...] = ()

    def __post_init__(self) -> None:
        if self.operator not in (
            "activity",
            "tau",
            "sequence",
            "xor",
            "parallel",
            "loop",
        ):
            raise ValueError("unsupported process-tree operator")
        if not isinstance(self.children, tuple) or not all(
            isinstance(child, ProcessTree) for child in self.children
        ):
            raise TypeError("children must be a tuple of ProcessTree")
        if self.operator == "activity":
            if not isinstance(self.activity, str):
                raise TypeError("activity leaf requires a text label")
            if not self.activity.strip():
                raise ValueError("activity label must not be blank")
            try:
                self.activity.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("activity must be valid UTF-8 text") from exc
        elif self.activity is not None:
            raise ValueError("only activity leaves may have an activity label")
        if self.operator in ("activity", "tau"):
            if self.children:
                raise ValueError("leaf nodes cannot have children")
        elif self.operator == "loop":
            if len(self.children) != 2:
                raise ValueError("loop requires exactly (do, redo) children")
        elif len(self.children) < 2:
            raise ValueError("composite operators require at least two children")


__all__ = ("DiscoverySpec", "ProcessTree", "TreeOperator")
