"""Explicit enabled-prefix precision contracts; independent of model libraries.

This is PIX's executable-prefix metric, not an ETConformance compatibility
claim. Enabled transitions leading only to dead ends still count as behavior.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields
from typing import ClassVar, Literal

MarkingSnapshot = tuple[tuple[str, int], ...]


def _count(value: object, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must not be negative")


def _texts(value: object, name: str, *, unique: bool = False) -> None:
    if not isinstance(value, tuple) or not all(
        isinstance(item, str) and item for item in value
    ):
        raise TypeError(f"{name} must be a tuple of nonempty strings")
    if unique and value != tuple(sorted(set(value))):
        raise ValueError(f"{name} must be sorted and unique")


def _ratio(value: object, name: str) -> None:
    if value is None:
        return
    if not isinstance(value, tuple) or len(value) != 2:
        raise TypeError(f"{name} must be an integer pair or None")
    for item in value:
        _count(item, name)
    if value[1] == 0 or value[0] > value[1]:
        raise ValueError(f"{name} requires 0 <= numerator <= positive denominator")


@dataclass(frozen=True, slots=True)
class PrefixPrecisionSpec:
    """Select completion semantics explicitly, and bound each epsilon closure.

    ``include`` weights a prefix by every trace visiting it, including traces
    ending there, and treats termination as a separate possible observation.
    ``exclude`` weights only continuing visits and omits the termination option.
    Empty event populations do not define a precision score under either policy.
    """

    terminal_policy: Literal["include", "exclude"]
    max_markings_per_prefix: int = 10000
    weighting: Literal["prefix_occurrences"] = "prefix_occurrences"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.terminal_policy not in ("include", "exclude"):
            raise ValueError("terminal_policy must be 'include' or 'exclude'")
        if self.weighting != "prefix_occurrences":
            raise ValueError("weighting must be 'prefix_occurrences'")
        value = self.max_markings_per_prefix
        if not isinstance(value, int) or isinstance(value, bool):
            raise TypeError("max_markings_per_prefix must be an integer")
        if value < 1:
            raise ValueError("max_markings_per_prefix must be at least one")


@dataclass(frozen=True, slots=True)
class PrefixPrecisionRequest:
    model_digest: str
    parameters: PrefixPrecisionSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class PrefixPrecisionEvidence:
    """One unique activity prefix and its exact or explicitly missing evidence.

    ``enabled_labels`` is a union over ALL reachable markings after silent
    closure, not enabled transition IDs or just one alignment. ``None`` denotes
    unknown state-space evidence; an empty tuple is a proven empty label set.
    Completion booleans are independent of arbitrary user activity strings.
    """

    prefix: tuple[str, ...]
    occurrence_object_ids: tuple[str, ...]
    completed_object_ids: tuple[str, ...]
    visit_count: int
    extension_count: int
    completion_count: int
    weight: int
    observed_labels: tuple[str, ...]
    observed_termination: bool
    status: Literal[
        "computed",
        "unfit_prefix",
        "unfit_observation",
        "search_limit",
        "upstream_search_limit",
        "excluded_terminal_policy",
    ]
    reachable_markings: tuple[MarkingSnapshot, ...] | None
    explored_markings_count: int
    enabled_labels: tuple[str, ...] | None
    enabled_termination: bool | None
    escaping_labels: tuple[str, ...] | None
    escaping_termination: bool | None
    missing_observed_labels: tuple[str, ...] | None
    missing_observed_termination: bool | None
    enabled_option_count: int | None
    escaping_option_count: int | None
    weighted_retained_options: int | None
    weighted_enabled_options: int | None

    def __post_init__(self) -> None:
        """Check evidence arithmetic only, without rediscovering model behavior."""
        _texts(self.prefix, "prefix")
        _texts(self.occurrence_object_ids, "occurrence_object_ids")
        _texts(self.completed_object_ids, "completed_object_ids")
        _texts(self.observed_labels, "observed_labels", unique=True)
        for name in (
            "visit_count",
            "extension_count",
            "completion_count",
            "weight",
            "explored_markings_count",
        ):
            _count(getattr(self, name), name)
        if self.visit_count != len(
            self.occurrence_object_ids
        ) or self.completion_count != len(self.completed_object_ids):
            raise ValueError("prefix population counts must match object evidence")
        if self.visit_count != self.extension_count + self.completion_count:
            raise ValueError(
                "prefix visits must partition into extensions and completions"
            )
        if Counter(self.completed_object_ids) - Counter(self.occurrence_object_ids):
            raise ValueError("completed objects must occur at the prefix")
        if not isinstance(self.observed_termination, bool):
            raise TypeError("observed_termination must be bool")
        if bool(self.observed_labels) != bool(self.extension_count):
            raise ValueError("observed labels require and cover extending occurrences")
        known = self.status in ("computed", "unfit_prefix", "unfit_observation")
        unknown = self.status in (
            "search_limit",
            "upstream_search_limit",
            "excluded_terminal_policy",
        )
        if not known and not unknown:
            raise ValueError("unknown prefix evidence status")
        if (self.status == "excluded_terminal_policy") != (self.weight == 0):
            raise ValueError("only policy-excluded prefixes have zero weight")
        option_fields = (
            "enabled_labels",
            "enabled_termination",
            "escaping_labels",
            "escaping_termination",
            "missing_observed_labels",
            "missing_observed_termination",
            "enabled_option_count",
            "escaping_option_count",
        )
        if unknown:
            if self.reachable_markings is not None or any(
                getattr(self, name) is not None for name in option_fields
            ):
                raise ValueError(
                    "unknown closure cannot contain complete option evidence"
                )
            if self.status != "search_limit" and self.explored_markings_count:
                raise ValueError("unexplored prefixes cannot claim explored markings")
        else:
            if not isinstance(self.reachable_markings, tuple):
                raise TypeError("known reachable markings must be a tuple")
            for marking in self.reachable_markings:
                if not isinstance(marking, tuple):
                    raise TypeError("marking snapshots must be tuples")
                names = []
                for token in marking:
                    if (
                        not isinstance(token, tuple)
                        or len(token) != 2
                        or not isinstance(token[0], str)
                        or not token[0]
                    ):
                        raise TypeError("marking token must be a (place, count) pair")
                    _count(token[1], "marking count")
                    if not token[1]:
                        raise ValueError("marking counts must be positive")
                    names.append(token[0])
                if names != sorted(set(names)):
                    raise ValueError("marking places must be sorted and unique")
            if self.reachable_markings != tuple(sorted(set(self.reachable_markings))):
                raise ValueError("reachable markings must be sorted and unique")
            if len(self.reachable_markings) != self.explored_markings_count:
                raise ValueError("known closure size must match explored marking count")
            for name in (
                "enabled_labels",
                "escaping_labels",
                "missing_observed_labels",
            ):
                _texts(getattr(self, name), name, unique=True)
            for name in (
                "enabled_termination",
                "escaping_termination",
                "missing_observed_termination",
            ):
                if not isinstance(getattr(self, name), bool):
                    raise TypeError(f"{name} must be bool for known closures")
            enabled = set(self.enabled_labels)
            observed = set(self.observed_labels)
            if self.escaping_labels != tuple(
                sorted(enabled - observed)
            ) or self.missing_observed_labels != tuple(sorted(observed - enabled)):
                raise ValueError(
                    "escaping and missing labels must match enabled/observed sets"
                )
            if self.escaping_termination != (
                self.enabled_termination and not self.observed_termination
            ) or self.missing_observed_termination != (
                self.observed_termination and not self.enabled_termination
            ):
                raise ValueError("termination difference evidence is inconsistent")
            _count(self.enabled_option_count, "enabled_option_count")
            _count(self.escaping_option_count, "escaping_option_count")
            if self.enabled_option_count != len(enabled) + int(
                self.enabled_termination
            ) or self.escaping_option_count != len(self.escaping_labels) + int(
                self.escaping_termination
            ):
                raise ValueError(
                    "option counts must match label and termination evidence"
                )
            missing = bool(
                self.missing_observed_labels or self.missing_observed_termination
            )
            if self.status == "computed" and (not self.reachable_markings or missing):
                raise ValueError(
                    "computed prefix must have reachable markings and no missing observation"
                )
            if self.status == "unfit_prefix" and (
                self.reachable_markings or enabled or self.enabled_termination
            ):
                raise ValueError("unfit prefix must have an empty reachable closure")
            if self.status == "unfit_observation" and (
                not self.reachable_markings or not missing
            ):
                raise ValueError(
                    "unfit observation requires reachable prefix and missing observation"
                )
        if self.status == "computed":
            _count(self.weighted_retained_options, "weighted_retained_options")
            _count(self.weighted_enabled_options, "weighted_enabled_options")
            if (
                self.weighted_enabled_options != self.weight * self.enabled_option_count
                or self.weighted_retained_options
                != self.weight
                * (self.enabled_option_count - self.escaping_option_count)
            ):
                raise ValueError("weighted option arithmetic is inconsistent")
        elif (
            self.weighted_retained_options is not None
            or self.weighted_enabled_options is not None
        ):
            raise ValueError("excluded prefixes must not contribute weighted options")


@dataclass(frozen=True, slots=True)
class PrefixPrecisionCoverage:
    trace_count: int
    empty_trace_count: int
    event_occurrence_count: int
    requested_prefixes: int
    computed_prefixes: int
    unfit_prefixes: int
    search_limited_prefixes: int
    policy_excluded_prefixes: int
    requested_occurrences: int
    computed_occurrences: int
    unfit_occurrences: int
    search_limited_occurrences: int

    def __post_init__(self) -> None:
        for field in fields(self):
            _count(getattr(self, field.name), field.name)
        if self.empty_trace_count > self.trace_count:
            raise ValueError("empty traces cannot exceed the trace population")
        if (
            self.requested_prefixes
            != self.computed_prefixes
            + self.unfit_prefixes
            + self.search_limited_prefixes
        ):
            raise ValueError("requested prefixes must partition by computation status")
        if (
            self.requested_occurrences
            != self.computed_occurrences
            + self.unfit_occurrences
            + self.search_limited_occurrences
        ):
            raise ValueError(
                "requested occurrences must partition by computation status"
            )


@dataclass(frozen=True, slots=True)
class PrefixPrecision:
    """Exact integer aggregates, with subset and whole-population scores apart.

    For eligible, computed prefixes p, D=sum(w_p * |M_p|),
    N=sum(w_p * (|M_p| - |M_p \\ O_p|)); termination is an independent
    option only under ``include``. No denominator is replaced by one.
    ``completed_ratio`` covers just computed prefixes; ``whole_log_ratio``
    exists only with complete coverage. Neither exists for an empty event
    population or zero denominator. Ratios retain the raw integer sums.
    """

    object_type: str
    model_digest: str
    source_trace_computation_id: str
    terminal_policy: Literal["include", "exclude"]
    weighting: Literal["prefix_occurrences"]
    prefixes: tuple[PrefixPrecisionEvidence, ...]
    coverage: PrefixPrecisionCoverage
    metric_status: Literal["computed", "partial", "unavailable"]
    completed_numerator: int
    completed_denominator: int
    completed_ratio: tuple[int, int] | None
    whole_log_ratio: tuple[int, int] | None
    metric_profile: str = "pix.enabled_prefix_precision.v1"

    def __post_init__(self) -> None:
        """Validate finite stored evidence; do not rerun reachability or fitting."""
        if (
            self.terminal_policy not in ("include", "exclude")
            or self.weighting != "prefix_occurrences"
        ):
            raise ValueError("unsupported precision policy or weighting")
        if self.metric_profile != "pix.enabled_prefix_precision.v1":
            raise ValueError("unsupported precision metric profile")
        if not isinstance(self.prefixes, tuple) or not all(
            isinstance(item, PrefixPrecisionEvidence) for item in self.prefixes
        ):
            raise TypeError("prefixes must contain PrefixPrecisionEvidence")
        if not isinstance(self.coverage, PrefixPrecisionCoverage):
            raise TypeError("coverage must be PrefixPrecisionCoverage")
        keys = tuple(item.prefix for item in self.prefixes)
        if keys != tuple(sorted(set(keys), key=lambda item: (len(item), item))):
            raise ValueError("prefixes must be unique and ordered by length and labels")
        by_prefix = {item.prefix: item for item in self.prefixes}
        children: dict[tuple[str, ...], list[PrefixPrecisionEvidence]] = {}
        for item in self.prefixes:
            if item.prefix:
                if item.prefix[:-1] not in by_prefix:
                    raise ValueError("prefix evidence must include every parent")
                children.setdefault(item.prefix[:-1], []).append(item)
            expected_weight = (
                item.visit_count
                if self.terminal_policy == "include"
                else item.extension_count
            )
            if item.weight != expected_weight:
                raise ValueError(
                    "prefix weight must follow the declared terminal policy"
                )
            expected_end = (
                bool(item.completion_count) and self.terminal_policy == "include"
            )
            if item.observed_termination != expected_end:
                raise ValueError(
                    "observed termination must follow policy and completion population"
                )
            if self.terminal_policy == "exclude" and item.enabled_termination not in (
                None,
                False,
            ):
                raise ValueError("excluded termination must not become a model option")
        for item in self.prefixes:
            successors = children.get(item.prefix, ())
            if item.extension_count != sum(child.visit_count for child in successors):
                raise ValueError("prefix extension counts must match child visits")
            if item.observed_labels != tuple(
                sorted(child.prefix[-1] for child in successors)
            ):
                raise ValueError("observed labels must match stored child prefixes")
            child_objects = Counter(
                object_id
                for child in successors
                for object_id in child.occurrence_object_ids
            )
            if Counter(item.occurrence_object_ids) != child_objects + Counter(
                item.completed_object_ids
            ):
                raise ValueError(
                    "prefix object populations must partition into children and completions"
                )
        computed = tuple(item for item in self.prefixes if item.status == "computed")
        unfit = tuple(
            item
            for item in self.prefixes
            if item.status in ("unfit_prefix", "unfit_observation")
        )
        limited = tuple(
            item
            for item in self.prefixes
            if item.status in ("search_limit", "upstream_search_limit")
        )
        root = by_prefix.get(())
        expected_coverage = PrefixPrecisionCoverage(
            root.visit_count if root else 0,
            root.completion_count if root else 0,
            sum(item.extension_count for item in self.prefixes),
            sum(item.weight > 0 for item in self.prefixes),
            len(computed),
            len(unfit),
            len(limited),
            sum(item.status == "excluded_terminal_policy" for item in self.prefixes),
            sum(item.weight for item in self.prefixes),
            sum(item.weight for item in computed),
            sum(item.weight for item in unfit),
            sum(item.weight for item in limited),
        )
        if self.coverage != expected_coverage:
            raise ValueError("precision coverage must match prefix evidence")
        _count(self.completed_numerator, "completed_numerator")
        _count(self.completed_denominator, "completed_denominator")
        if self.completed_numerator != sum(
            item.weighted_retained_options for item in computed
        ) or self.completed_denominator != sum(
            item.weighted_enabled_options for item in computed
        ):
            raise ValueError(
                "precision aggregate sums must match computed prefix contributions"
            )
        _ratio(self.completed_ratio, "completed_ratio")
        _ratio(self.whole_log_ratio, "whole_log_ratio")
        ratio = (
            (self.completed_numerator, self.completed_denominator)
            if self.completed_denominator and self.coverage.event_occurrence_count
            else None
        )
        incomplete = bool(unfit or limited)
        if self.completed_ratio != ratio:
            raise ValueError(
                "completed ratio must match exact sums and event population"
            )
        if self.whole_log_ratio != (None if incomplete else ratio):
            raise ValueError("whole-log ratio requires complete prefix coverage")
        status = (
            "unavailable" if ratio is None else "partial" if incomplete else "computed"
        )
        if self.metric_status != status:
            raise ValueError("metric status must match ratio availability and coverage")


__all__ = (
    "PrefixPrecision",
    "PrefixPrecisionCoverage",
    "PrefixPrecisionEvidence",
    "PrefixPrecisionRequest",
    "PrefixPrecisionSpec",
)
