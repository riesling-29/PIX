"""Native case/event selection with source-order witnesses and explicit unknowns.

Selection is an analytical view. ``materialize_case_selection`` applies the view
to its digest-matched native source, retaining metadata and unmodified facts.
Missing data does not satisfy a negative predicate; it remains unknown.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from math import isfinite
from random import Random
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_log_digest
from pix.event_log.adapters import _activity


def _choice(value: str, allowed: tuple[str, ...], name: str) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {allowed}")


def _texts(value: object, name: str, *, nonempty: bool = False) -> None:
    if (
        not isinstance(value, tuple)
        or not all(isinstance(item, str) and item for item in value)
        or (nonempty and not value)
    ):
        raise ValueError(f"{name} must be a tuple of nonempty strings")


def _number(value: object, name: str) -> None:
    if value is not None and (
        type(value) not in (int, float)
        or (isinstance(value, float) and not isfinite(value))
    ):
        raise ValueError(f"{name} must be a finite number or None")


@dataclass(frozen=True, slots=True)
class FilterScalar:
    """Disjoint typed fields keep ISO-looking strings distinct from real dates.

    AttributeCondition accepts native CaseAttribute inputs and normalizes them
    to this comparison value; source attributes themselves are never modified.
    """

    type: str
    text_value: str | None = None
    date_value: datetime | None = None
    int_value: int | None = None
    float_value: float | None = None
    bool_value: bool | None = None

    def __post_init__(self) -> None:
        selected = {
            "string": "text_value",
            "id": "text_value",
            "date": "date_value",
            "int": "int_value",
            "float": "float_value",
            "boolean": "bool_value",
            "null": None,
        }
        if self.type not in selected:
            raise ValueError("unsupported filter scalar type")
        field = selected[self.type]
        kinds = {
            "text_value": str,
            "date_value": datetime,
            "int_value": int,
            "float_value": float,
            "bool_value": bool,
        }
        for name, kind in kinds.items():
            value = getattr(self, name)
            if name == field:
                if type(value) is not kind:
                    raise TypeError(
                        f"{self.type} filter scalar requires {kind.__name__}"
                    )
            elif value is not None:
                raise ValueError("filter scalar has a value in an inactive typed field")
        if self.float_value is not None and not isfinite(self.float_value):
            raise ValueError("nonfinite attribute comparison is unsupported")
        if self.date_value is not None:
            if self.date_value.utcoffset() is None:
                raise ValueError("date comparison requires timezone-aware values")
            try:
                object.__setattr__(
                    self, "date_value", self.date_value.astimezone(timezone.utc)
                )
            except (ValueError, OverflowError) as exc:
                raise ValueError("date comparison value exceeds UTC range") from exc

    @property
    def value(self) -> str | datetime | int | float | bool | None:
        name = {
            "string": "text_value",
            "id": "text_value",
            "date": "date_value",
            "int": "int_value",
            "float": "float_value",
            "boolean": "bool_value",
            "null": None,
        }[self.type]
        return None if name is None else getattr(self, name)


def _comparison_scalar(attribute: CaseAttribute | FilterScalar) -> FilterScalar:
    if isinstance(attribute, FilterScalar):
        return attribute
    if (
        not isinstance(attribute, CaseAttribute)
        or attribute.children
        or attribute.values
    ):
        raise ValueError("values must be scalar CaseAttribute or FilterScalar values")
    name = {
        "string": "text_value",
        "id": "text_value",
        "date": "date_value",
        "int": "int_value",
        "float": "float_value",
        "boolean": "bool_value",
        "null": None,
    }.get(attribute.type)
    if attribute.type not in (
        "string",
        "id",
        "date",
        "int",
        "float",
        "boolean",
        "null",
    ):
        raise ValueError("values must be primitive scalar attributes")
    return FilterScalar(attribute.type, **({name: attribute.value} if name else {}))


@dataclass(frozen=True, slots=True)
class AttributeCondition:
    """Scalar equality respects the recorded XES type, including int vs boolean.

    Numeric ranges explicitly admit int and float, but never boolean. Presence
    means a recorded or global-default key exists; null is a present value.
    """

    key: str
    operator: str = "equals"
    values: tuple[FilterScalar | CaseAttribute, ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str):
            raise TypeError("key must be text")
        _choice(self.operator, ("equals", "numeric_range", "present"), "operator")
        if not isinstance(self.values, tuple):
            raise TypeError("values must be an immutable tuple")
        object.__setattr__(
            self, "values", tuple(_comparison_scalar(item) for item in self.values)
        )
        _number(self.minimum, "minimum")
        _number(self.maximum, "maximum")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum exceeds maximum")
        if self.operator == "equals" and not self.values:
            raise ValueError("equals requires at least one typed value")
        if self.values and self.operator != "equals":
            raise ValueError("typed values only apply to equals")
        if (
            self.minimum is not None or self.maximum is not None
        ) and self.operator != "numeric_range":
            raise ValueError("numeric bounds only apply to numeric_range")


@dataclass(frozen=True, slots=True)
class CaseFilterSpec:
    """Selection contract, independent of dataframe/stream backends.

    All ranges are closed. Order is native source order. Frequency denominators
    include all source cases/events, including cases with unknown attributes.
    A variant is the entire activity tuple. Top-k ties may expand k; cumulative
    coverage includes the group crossing the threshold (0 selects none).
    """

    kind: str = "activity"
    mode: str = "cases"
    activities: tuple[str, ...] = ()
    pattern: tuple[str, ...] = ()
    attribute: AttributeCondition | None = None
    variants: tuple[tuple[str, ...], ...] = ()
    minimum: int | float | None = None
    maximum: int | float | None = None
    time_start: datetime | None = None
    time_end: datetime | None = None
    time_mode: str = "contained"
    quantifier: str = "any"
    positive: bool = True
    empty_cases: str = "preserve"
    unknown: str = "exclude"
    adjacency: str = "original"
    project_activities: tuple[str, ...] = ()
    resource_key: str = "org:resource"
    resource_policy: str = "disjoint"
    frequency_unit: str = "cases"
    top_k: int | None = None
    cumulative_coverage: int | float | None = None
    include_ties: bool = True
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        kinds = (
            "activity",
            "start",
            "end",
            "event_attribute",
            "case_attribute",
            "attribute_frequency",
            "variants",
            "variant_frequency",
            "length",
            "duration",
            "rework",
            "directly_follows",
            "eventually_follows",
            "sequence",
            "prefix",
            "suffix",
            "time",
            "path_duration",
            "four_eyes",
            "different_resources",
            "case_limit",
        )
        _choice(self.kind, kinds, "kind")
        _choice(self.mode, ("cases", "events"), "mode")
        _choice(self.quantifier, ("any", "all"), "quantifier")
        _choice(self.empty_cases, ("preserve", "drop"), "empty_cases")
        _choice(self.unknown, ("exclude", "include", "error"), "unknown")
        _choice(self.adjacency, ("original", "projected"), "adjacency")
        _choice(
            self.time_mode, ("contained", "intersects", "start", "end"), "time_mode"
        )
        _choice(
            self.resource_policy, ("disjoint", "exists_difference"), "resource_policy"
        )
        _choice(self.frequency_unit, ("cases", "events"), "frequency_unit")
        for name in ("activities", "pattern", "project_activities"):
            _texts(getattr(self, name), name)
        if not isinstance(self.variants, tuple):
            raise TypeError("variants must be a tuple")
        for variant in self.variants:
            _texts(variant, "variant")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        for name in ("positive", "include_ties"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if not isinstance(self.resource_key, str) or not self.resource_key:
            raise ValueError("resource_key must be nonempty")
        if self.mode == "events" and self.kind not in (
            "activity",
            "event_attribute",
            "attribute_frequency",
            "time",
        ):
            raise ValueError("event selection requires an event-level predicate")
        if self.kind in (
            "event_attribute",
            "case_attribute",
            "attribute_frequency",
        ) and not isinstance(self.attribute, AttributeCondition):
            raise ValueError("attribute predicate is required")
        if self.attribute is not None and not isinstance(
            self.attribute, AttributeCondition
        ):
            raise TypeError("attribute must be AttributeCondition")
        if (
            self.kind
            in (
                "directly_follows",
                "eventually_follows",
                "sequence",
                "prefix",
                "suffix",
                "path_duration",
                "four_eyes",
            )
            and not self.pattern
        ):
            raise ValueError("pattern is required")
        if (
            self.kind
            in ("directly_follows", "eventually_follows", "path_duration", "four_eyes")
            and len(self.pattern) != 2
        ):
            raise ValueError("this predicate requires a two-activity pattern")
        for name in ("minimum", "maximum", "cumulative_coverage"):
            _number(getattr(self, name), name)
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum exceeds maximum")
        if (
            self.cumulative_coverage is not None
            and not 0 <= self.cumulative_coverage <= 1
        ):
            raise ValueError("cumulative_coverage must be between 0 and 1")
        if self.top_k is not None and (type(self.top_k) is not int or self.top_k < 0):
            raise ValueError("top_k must be a nonnegative integer")
        for name in ("time_start", "time_end"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, datetime) or value.utcoffset() is None
            ):
                raise ValueError(f"{name} must be timezone-aware")
            if value is not None:
                try:
                    object.__setattr__(self, name, value.astimezone(timezone.utc))
                except (OverflowError, ValueError) as exc:
                    raise ValueError(f"{name} exceeds UTC range") from exc
        if (
            self.time_start is not None
            and self.time_end is not None
            and self.time_start > self.time_end
        ):
            raise ValueError("time_start exceeds time_end")
        if self.kind == "case_limit" and self.top_k is None:
            raise ValueError("case_limit requires top_k")
        if self.project_activities and self.kind not in (
            "directly_follows",
            "eventually_follows",
            "sequence",
            "path_duration",
            "prefix",
            "suffix",
        ):
            raise ValueError("project_activities applies only to path predicates")
        if self.top_k is not None and self.kind not in (
            "variant_frequency",
            "case_limit",
        ):
            raise ValueError("top_k only applies to variant_frequency or case_limit")
        if self.cumulative_coverage is not None and self.kind != "variant_frequency":
            raise ValueError("cumulative_coverage only applies to variant_frequency")
        if (self.minimum is not None or self.maximum is not None) and self.kind not in (
            "attribute_frequency",
            "variant_frequency",
            "length",
            "duration",
            "rework",
            "path_duration",
        ):
            raise ValueError("minimum/maximum are not used by this predicate")
        if (
            self.time_start is not None or self.time_end is not None
        ) and self.kind != "time":
            raise ValueError("time bounds only apply to the time predicate")
        if self.attribute is not None and self.kind not in (
            "event_attribute",
            "case_attribute",
            "attribute_frequency",
        ):
            raise ValueError("attribute condition is not used by this predicate")
        if self.variants and self.kind != "variants":
            raise ValueError("variants only applies to explicit variant selection")
        if self.quantifier == "all" and self.kind not in (
            "activity",
            "event_attribute",
            "attribute_frequency",
            "rework",
            "path_duration",
        ):
            raise ValueError("quantifier is not used by this predicate")
        if self.time_mode != "contained" and (
            self.kind != "time" or self.mode != "cases"
        ):
            raise ValueError("time_mode selects case-span time semantics")
        if self.frequency_unit != "cases" and self.kind != "attribute_frequency":
            raise ValueError("frequency_unit only applies to attribute_frequency")
        if self.kind in ("attribute_frequency", "variant_frequency") and any(
            bound is not None and not 0 <= bound <= 1
            for bound in (self.minimum, self.maximum)
        ):
            raise ValueError("frequency bounds must be between 0 and 1")
        if self.activities and self.kind not in (
            "activity",
            "start",
            "end",
            "rework",
            "different_resources",
        ):
            raise ValueError("activities is not used by this predicate")
        if self.pattern and self.kind not in (
            "directly_follows",
            "eventually_follows",
            "sequence",
            "prefix",
            "suffix",
            "path_duration",
            "four_eyes",
        ):
            raise ValueError("pattern is not used by this predicate")
        if self.quantifier != "any" and self.mode != "cases":
            raise ValueError("quantifier combines event predicates at case level")
        if self.adjacency != "original" and self.kind not in (
            "directly_follows",
            "eventually_follows",
            "sequence",
            "prefix",
            "suffix",
            "path_duration",
        ):
            raise ValueError("adjacency is not used by this predicate")
        if not self.include_ties and self.kind != "variant_frequency":
            raise ValueError("include_ties only applies to variant_frequency")
        if self.resource_policy != "disjoint" and self.kind != "four_eyes":
            raise ValueError("resource_policy only applies to four_eyes")
        if self.resource_key != "org:resource" and self.kind not in (
            "four_eyes",
            "different_resources",
        ):
            raise ValueError("resource_key is not used by this predicate")


@dataclass(frozen=True, slots=True)
class SelectionWitness:
    source_case_id: str
    event_ids: tuple[str, ...]
    positions: tuple[int, ...]
    value: float | None = None
    uncertain_event_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CaseSelectionEntry:
    source_case_id: str
    output_case_id: str
    event_ids: tuple[str, ...]
    source_positions: tuple[int, ...]
    output_event_ids: tuple[str, ...]
    bridged_adjacencies: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CaseSelection:
    entries: tuple[CaseSelectionEntry, ...]
    excluded_case_ids: tuple[str, ...]
    unknown_case_ids: tuple[str, ...]
    unknown_event_ids: tuple[str, ...]
    witnesses: tuple[SelectionWitness, ...]
    source_case_count: int
    source_event_count: int
    selected_source_case_count: int
    selected_event_count: int


def _range(value: float, minimum: float | None, maximum: float | None) -> bool:
    return (minimum is None or value >= minimum) and (
        maximum is None or value <= maximum
    )


def _time(log: CaseLog, event: CaseEvent, key: str) -> datetime | None:
    attr = log.attribute(event, key)
    if attr is None or attr.type != "date" or attr.value.utcoffset() is None:
        return None
    # Datetimes sharing a tzinfo object otherwise subtract wall-clock values
    # across DST transitions; comparisons must use elapsed UTC instants.
    try:
        return attr.value.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _attribute_matches(
    log: CaseLog, item: CaseEvent | CaseTrace, condition: AttributeCondition
) -> bool | None:
    attr = log.attribute(item, condition.key)
    if condition.operator == "present":
        return attr is not None
    if attr is None:
        return None
    if condition.operator == "numeric_range":
        if attr.type not in ("int", "float") or (
            attr.type == "float" and not isfinite(attr.value)
        ):
            return None
        return _range(attr.value, condition.minimum, condition.maximum)
    if attr.type not in ("string", "id", "date", "int", "float", "boolean", "null"):
        return None
    if isinstance(attr.value, float) and not isfinite(attr.value):
        return None
    if isinstance(attr.value, datetime) and attr.value.utcoffset() is None:
        return None
    if attr.type == "date":
        try:
            stamp = attr.value.astimezone(timezone.utc)
        except (OverflowError, ValueError):
            return None
        return any(
            value.type == "date" and stamp == value.value.astimezone(timezone.utc)
            for value in condition.values
        )
    return any(
        attr.type == value.type and attr.value == value.value
        for value in condition.values
    )


def _combine(values: tuple[bool | None, ...], quantifier: str) -> bool | None:
    # Empty event populations never imply universal business-rule compliance.
    if not values:
        return False
    if quantifier == "any" and True in values:
        return True
    if quantifier == "all" and False in values:
        return False
    if None in values:
        return None
    return quantifier == "all"


def _entry(
    trace: CaseTrace, positions: tuple[int, ...], output_id: str | None = None
) -> CaseSelectionEntry:
    ids = tuple(trace.events[pos].id for pos in positions)
    result_id = trace.id if output_id is None else output_id
    output_ids = (
        ids
        if output_id is None
        else tuple(f"{output_id}:event:{i}" for i in range(len(ids)))
    )
    bridged = tuple(
        (trace.events[a].id, trace.events[b].id)
        for a, b in zip(positions, positions[1:])
        if b != a + 1
    )
    return CaseSelectionEntry(trace.id, result_id, ids, positions, output_ids, bridged)


def _frequency_selection(
    counts: Counter, denominator: int, spec: CaseFilterSpec
) -> set:
    ranked = sorted(counts, key=lambda key: (-counts[key], key))
    if spec.top_k is not None:
        if spec.top_k == 0:
            ranked = []
        elif spec.top_k < len(ranked):
            boundary = counts[ranked[spec.top_k - 1]]
            ranked = [
                key
                for i, key in enumerate(ranked)
                if i < spec.top_k or (spec.include_ties and counts[key] == boundary)
            ]
    if spec.cumulative_coverage is not None:
        chosen, cumulative, last = [], 0, None
        for key in ranked:
            if cumulative >= spec.cumulative_coverage * denominator and not (
                spec.include_ties and last is not None and counts[key] == last
            ):
                break
            chosen.append(key)
            cumulative += counts[key]
            last = counts[key]
        ranked = chosen
    return {
        key
        for key in ranked
        if _range(
            counts[key] / denominator if denominator else 0.0,
            spec.minimum,
            spec.maximum,
        )
    }


def filter_case_log(
    log: CaseLog, spec: CaseFilterSpec = CaseFilterSpec(kind="length")
) -> ComputationResult[CaseSelection]:
    """Select full cases or event slices; unknown predicates retain diagnostics.

    ``four_eyes`` compares the resource sets of two present activities, without
    assuming a pairing between repeated occurrences. ``exists_difference`` is
    existential; ``disjoint`` demands no shared resource. ``different_resources``
    requires at least two observed resources for at least one selected activity.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, CaseFilterSpec):
        raise TypeError("expected CaseLog and CaseFilterSpec")
    digest = case_log_digest(log)
    labels: dict[str, tuple[str | None, ...]] = {}
    issues: list[ComputeIssue] = []
    unknown_events: set[str] = set()
    unknown_cases: set[str] = set()
    witnesses: list[SelectionWitness] = []
    selections: list[CaseSelectionEntry] = []

    def unknown_event(trace: CaseTrace, event: CaseEvent, message: str) -> None:
        unknown_events.add(event.id)
        issues.append(
            ComputeIssue(
                "unknown_filter_value", message, ("case", trace.id, "event", event.id)
            )
        )

    activity_kinds = {
        "activity",
        "start",
        "end",
        "variants",
        "variant_frequency",
        "rework",
        "directly_follows",
        "eventually_follows",
        "sequence",
        "prefix",
        "suffix",
        "path_duration",
        "four_eyes",
        "different_resources",
    }
    if spec.kind in activity_kinds:
        if (
            spec.trace_spec.classifier is not None
            and len(
                tuple(
                    classifier
                    for classifier in log.classifiers
                    if classifier.name == spec.trace_spec.classifier
                    and classifier.scope == "event"
                )
            )
            != 1
        ):
            return _derived_result(
                "pix.case_centric.filter",
                digest,
                spec,
                ComputeStatus.INVALID_INPUT,
                None,
                (
                    ComputeIssue(
                        "invalid_classifier",
                        "Classifier must select exactly one declared event classifier",
                    ),
                ),
            )
        for trace in log.traces:
            row = []
            for event in trace.events:
                try:
                    row.append(_activity(log, event, spec.trace_spec))
                except ValueError as exc:
                    row.append(None)
                    unknown_event(trace, event, str(exc))
            labels[trace.id] = tuple(row)

    allowed_variants = set(spec.variants)
    if spec.kind == "variant_frequency":
        counts = Counter(row for row in labels.values() if None not in row)
        allowed_variants = _frequency_selection(counts, len(log.traces), spec)
    attribute_frequency: bool | None = None
    if spec.kind == "attribute_frequency":
        values = []
        for trace in log.traces:
            row = []
            for event in trace.events:
                try:
                    row.append(_attribute_matches(log, event, spec.attribute))
                except ValueError as exc:
                    row.append(None)
                    unknown_event(trace, event, str(exc))
            values.extend(
                row
                if spec.frequency_unit == "events"
                else (_combine(tuple(row), "any"),)
            )
        denominator = len(values)
        lower = values.count(True) / denominator if denominator else 0.0
        upper = (
            (values.count(True) + values.count(None)) / denominator
            if denominator
            else 0.0
        )
        lower_ok = _range(lower, spec.minimum, spec.maximum)
        upper_ok = _range(upper, spec.minimum, spec.maximum)
        if lower_ok and upper_ok:
            attribute_frequency = True
        elif (spec.minimum is not None and upper < spec.minimum) or (
            spec.maximum is not None and lower > spec.maximum
        ):
            attribute_frequency = False
        else:
            attribute_frequency = None

    def event_predicate(
        trace: CaseTrace, event: CaseEvent, position: int
    ) -> bool | None:
        if spec.kind == "activity":
            activity = labels[trace.id][position]
            return None if activity is None else activity in spec.activities
        if spec.kind in ("event_attribute", "attribute_frequency"):
            matched = _attribute_matches(log, event, spec.attribute)
            if spec.kind == "attribute_frequency":
                if attribute_frequency is False or matched is False:
                    return False
                if attribute_frequency is None or matched is None:
                    return None
            return matched
        timestamp = _time(log, event, spec.trace_spec.timestamp_key)
        if timestamp is None:
            return None
        return (spec.time_start is None or timestamp >= spec.time_start) and (
            spec.time_end is None or timestamp <= spec.time_end
        )

    def case_predicate(trace: CaseTrace, index: int) -> bool | None:
        if spec.kind == "case_limit":
            return index < spec.top_k
        if spec.kind == "length":
            return _range(len(trace.events), spec.minimum, spec.maximum)
        if spec.kind == "case_attribute":
            return _attribute_matches(log, trace, spec.attribute)
        if spec.kind in ("activity", "event_attribute", "attribute_frequency"):
            values = []
            for pos, event in enumerate(trace.events):
                try:
                    answer = event_predicate(trace, event, pos)
                except ValueError:
                    answer = None
                if answer is None:
                    unknown_event(
                        trace,
                        event,
                        "Predicate attribute is missing, ambiguous or ineligible",
                    )
                values.append(answer)
            return _combine(tuple(values), spec.quantifier)
        if spec.kind in ("duration", "time"):
            if not trace.events:
                return None
            times = tuple(
                _time(log, event, spec.trace_spec.timestamp_key)
                for event in trace.events
            )
            if None in times:
                for event, timestamp in zip(trace.events, times):
                    if timestamp is None:
                        unknown_event(
                            trace, event, "Timestamp is missing or not timezone-aware"
                        )
                return None
            start, end = min(times), max(times)
            if spec.kind == "duration":
                return _range((end - start).total_seconds(), spec.minimum, spec.maximum)
            if spec.time_mode in ("start", "end"):
                stamp = start if spec.time_mode == "start" else end
                return (spec.time_start is None or stamp >= spec.time_start) and (
                    spec.time_end is None or stamp <= spec.time_end
                )
            if spec.time_mode == "contained":
                return (spec.time_start is None or start >= spec.time_start) and (
                    spec.time_end is None or end <= spec.time_end
                )
            return (spec.time_end is None or start <= spec.time_end) and (
                spec.time_start is None or end >= spec.time_start
            )
        acts = labels[trace.id]
        if spec.kind in ("start", "end"):
            if not acts:
                return False
            value = acts[0 if spec.kind == "start" else -1]
            return None if value is None else value in spec.activities
        if spec.kind in ("variants", "variant_frequency"):
            if spec.kind == "variant_frequency" and any(
                None in row for row in labels.values()
            ):
                # Unresolved variants can change rankings and frequency bounds.
                return None
            return None if None in acts else acts in allowed_variants
        if spec.kind == "rework":
            if None in acts:
                return None
            counts = Counter(acts)
            # Counts are activity occurrences, not occurrences minus one.
            return _combine(
                tuple(
                    _range(counts[activity], spec.minimum, spec.maximum)
                    for activity in spec.activities
                ),
                spec.quantifier,
            )
        if spec.kind in ("four_eyes", "different_resources"):
            selected = spec.pattern if spec.kind == "four_eyes" else spec.activities
            resources = {activity: set() for activity in selected}
            missing = False
            for event, activity in zip(trace.events, acts):
                if activity is None:
                    missing = True
                if activity not in resources:
                    continue
                resource = log.attribute(event, spec.resource_key)
                if resource is None or resource.type not in ("string", "id", "int"):
                    missing = True
                    unknown_event(
                        trace, event, "Resource identity is missing or ineligible"
                    )
                else:
                    resources[activity].add((resource.type, resource.value))
            if spec.kind == "different_resources":
                answer = any(len(values) >= 2 for values in resources.values())
                return True if answer else None if missing else False
            left, right = (resources[activity] for activity in spec.pattern)
            if spec.resource_policy == "disjoint":
                if left & right:
                    return False
                if missing:
                    return None
                return bool(left and right)
            if any(a != b for a in left for b in right):
                return True
            return None if missing else False
        positions = tuple(
            i
            for i, activity in enumerate(acts)
            if not spec.project_activities or activity in spec.project_activities
        )
        view = tuple(acts[i] for i in positions)
        pattern = spec.pattern
        matches: list[tuple[int, ...]] = []
        if spec.kind == "eventually_follows":
            matches = [
                (positions[i], positions[j])
                for i, activity in enumerate(view)
                for j in range(i + 1, len(view))
                if activity == pattern[0] and view[j] == pattern[1]
            ]
        else:
            length = len(pattern)
            for i in range(max(0, len(view) - length + 1)):
                occurrence = positions[i : i + length]
                if view[i : i + length] != pattern:
                    continue
                if spec.adjacency == "original" and any(
                    b != a + 1 for a, b in zip(occurrence, occurrence[1:])
                ):
                    continue
                if spec.kind == "prefix" and i != 0:
                    continue
                if spec.kind == "suffix" and i + length != len(view):
                    continue
                matches.append(occurrence)
        outcomes: list[bool | None] = []
        for occurrence in matches:
            value = None
            outcome = True
            uncertain_positions = []
            if spec.project_activities and spec.kind != "eventually_follows":
                first, last = occurrence[0], occurrence[-1]
                if spec.kind == "prefix":
                    first = 0
                if spec.kind == "suffix":
                    last = len(acts) - 1
                uncertain_positions = [
                    pos for pos in range(first, last + 1) if acts[pos] is None
                ]
                if uncertain_positions:
                    outcome = None
            if spec.kind == "path_duration":
                left = _time(
                    log, trace.events[occurrence[0]], spec.trace_spec.timestamp_key
                )
                right = _time(
                    log, trace.events[occurrence[-1]], spec.trace_spec.timestamp_key
                )
                if left is None or right is None or right < left:
                    outcome = None
                    for pos in occurrence:
                        unknown_event(
                            trace,
                            trace.events[pos],
                            "Path timestamp is missing, naive or reversed",
                        )
                else:
                    value = (right - left).total_seconds()
                    if outcome is not None:
                        outcome = _range(value, spec.minimum, spec.maximum)
            outcomes.append(outcome)
            witnesses.append(
                SelectionWitness(
                    trace.id,
                    tuple(trace.events[pos].id for pos in occurrence),
                    occurrence,
                    value,
                    tuple(trace.events[pos].id for pos in uncertain_positions),
                )
            )
        if spec.kind == "path_duration":
            answer = _combine(tuple(outcomes), spec.quantifier)
            if spec.quantifier == "all" and None in acts and answer is not False:
                return None
            return None if not matches and None in acts else answer
        if True in outcomes:
            return True
        if None in outcomes:
            return None
        return None if None in acts else False

    for index, trace in enumerate(log.traces):
        if spec.mode == "events":
            selected = []
            for position, event in enumerate(trace.events):
                try:
                    answer = event_predicate(trace, event, position)
                except ValueError as exc:
                    answer = None
                    unknown_event(trace, event, str(exc))
                if answer is None:
                    unknown_cases.add(trace.id)
                    unknown_event(trace, event, "Event predicate cannot be evaluated")
                    keep = spec.unknown == "include"
                else:
                    keep = answer if spec.positive else not answer
                if keep:
                    selected.append(position)
            if selected or spec.empty_cases == "preserve":
                selections.append(_entry(trace, tuple(selected)))
        else:
            try:
                answer = case_predicate(trace, index)
            except ValueError as exc:
                answer = None
                issues.append(
                    ComputeIssue("unknown_filter_value", str(exc), ("case", trace.id))
                )
            if answer is None:
                unknown_cases.add(trace.id)
                issues.append(
                    ComputeIssue(
                        "unknown_case_predicate",
                        "Case predicate cannot be evaluated",
                        ("case", trace.id),
                    )
                )
                keep = spec.unknown == "include"
            else:
                keep = answer if spec.positive else not answer
            if keep and (trace.events or spec.empty_cases == "preserve"):
                selections.append(_entry(trace, tuple(range(len(trace.events)))))
    # Event diagnostics can be present even when existential truth is known.
    unique_issues = tuple(dict.fromkeys(issues))
    if spec.unknown == "error" and unique_issues:
        return _derived_result(
            "pix.case_centric.filter",
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            unique_issues,
        )
    chosen_cases = {entry.source_case_id for entry in selections}
    payload = CaseSelection(
        tuple(selections),
        tuple(trace.id for trace in log.traces if trace.id not in chosen_cases),
        tuple(trace.id for trace in log.traces if trace.id in unknown_cases),
        tuple(
            event.id
            for trace in log.traces
            for event in trace.events
            if event.id in unknown_events
        ),
        tuple(witnesses),
        len(log.traces),
        sum(len(trace.events) for trace in log.traces),
        len(chosen_cases),
        sum(len(entry.event_ids) for entry in selections),
    )
    return _derived_result(
        "pix.case_centric.filter",
        digest,
        spec,
        ComputeStatus.PARTIAL if unique_issues else ComputeStatus.COMPUTED,
        payload,
        unique_issues,
    )


def materialize_case_selection(
    log: CaseLog, selection: ComputationResult[CaseSelection]
) -> CaseLog:
    """Apply validated lineage to its source; retain attributes and source metadata.

    Segmented outputs have new deterministic identities. Their original case and
    event identities remain in the selection. Event filtering preserves IDs.
    """
    if not isinstance(log, CaseLog) or not isinstance(selection, ComputationResult):
        raise TypeError("expected CaseLog and selection result")
    if selection.operator_id not in RESULT_SCHEMAS or not isinstance(
        selection.value, CaseSelection
    ):
        raise ValueError("result is not an available case selection")
    if selection.source_digest != case_log_digest(log):
        raise ValueError("selection source digest does not match log")
    if selection.operator_id == "pix.case_centric.filter":
        expected = filter_case_log(log, selection.spec)
    elif selection.operator_id == "pix.case_centric.slice":
        expected = slice_cases(log, selection.spec)
    else:
        expected = sample_cases(log, selection.spec)
    if selection != expected:
        raise ValueError(
            "selection lineage does not match its source, order and policy"
        )
    sources = {trace.id: trace for trace in log.traces}
    output = []
    for entry in selection.value.entries:
        source = sources.get(entry.source_case_id)
        if source is None or not (
            len(entry.event_ids)
            == len(entry.source_positions)
            == len(entry.output_event_ids)
        ):
            raise ValueError("invalid selection lineage")
        if any(
            type(pos) is not int or pos < 0 or pos >= len(source.events)
            for pos in entry.source_positions
        ):
            raise ValueError("invalid source position")
        if tuple(sorted(set(entry.source_positions))) != entry.source_positions:
            raise ValueError("selection must preserve source order without duplicates")
        if (
            tuple(source.events[pos].id for pos in entry.source_positions)
            != entry.event_ids
        ):
            raise ValueError("selection event identities do not match source positions")
        events = tuple(
            source.events[pos]
            if source.events[pos].id == event_id
            else replace(source.events[pos], id=event_id)
            for pos, event_id in zip(entry.source_positions, entry.output_event_ids)
        )
        output.append(replace(source, id=entry.output_case_id, events=events))
    return replace(log, traces=tuple(output))


@dataclass(frozen=True, slots=True)
class CaseSliceSpec:
    """Boundary slicing; every occurrence is a separate, provenance-backed case.

    ``between`` pairs each start with the first strictly later end and therefore
    may overlap. ``first``/``last``/``all`` choose from those candidate intervals.
    Split includes its boundary in the next segment; an initial empty segment is
    retained only under ``empty_cases='preserve'``. No time ordering is inferred.
    """

    kind: str = "prefix"
    start_activity: str | None = None
    end_activity: str | None = None
    occurrence: str = "first"
    include_start: bool = True
    include_end: bool = True
    empty_cases: str = "drop"
    unknown: str = "exclude"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _choice(
            self.kind,
            (
                "prefix",
                "suffix",
                "between",
                "split",
                "consecutive_activity",
                "timestamp_groups",
            ),
            "kind",
        )
        _choice(self.occurrence, ("first", "last", "all"), "occurrence")
        _choice(self.empty_cases, ("preserve", "drop"), "empty_cases")
        _choice(self.unknown, ("exclude", "error"), "unknown")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        for field in ("start_activity", "end_activity"):
            value = getattr(self, field)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{field} must be nonempty text")
        if self.kind in ("suffix", "between", "split") and self.start_activity is None:
            raise ValueError("start_activity is required")
        if self.kind in ("prefix", "between") and self.end_activity is None:
            raise ValueError("end_activity is required")
        if type(self.include_start) is not bool or type(self.include_end) is not bool:
            raise TypeError("include_start and include_end must be bool")


def slice_cases(log: CaseLog, spec: CaseSliceSpec) -> ComputationResult[CaseSelection]:
    """Extract ordered segments with fresh IDs and complete original-ID lineage."""
    if not isinstance(log, CaseLog) or not isinstance(spec, CaseSliceSpec):
        raise TypeError("expected CaseLog and CaseSliceSpec")
    digest = case_log_digest(log)
    entries, issues, unknown_cases, unknown_events = [], [], [], []
    if (
        spec.kind != "timestamp_groups"
        and spec.trace_spec.classifier is not None
        and len(
            tuple(
                classifier
                for classifier in log.classifiers
                if classifier.name == spec.trace_spec.classifier
                and classifier.scope == "event"
            )
        )
        != 1
    ):
        return _derived_result(
            "pix.case_centric.slice",
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "invalid_classifier",
                    "Classifier must select exactly one declared event classifier",
                ),
            ),
        )
    for trace in log.traces:
        try:
            if spec.kind == "timestamp_groups":
                keys = tuple(
                    _time(log, event, spec.trace_spec.timestamp_key)
                    for event in trace.events
                )
                if None in keys:
                    raise ValueError(
                        "timestamp grouping requires timezone-aware timestamps"
                    )
            else:
                keys = tuple(
                    _activity(log, event, spec.trace_spec) for event in trace.events
                )
        except ValueError as exc:
            unknown_cases.append(trace.id)
            unknown_events.extend(event.id for event in trace.events)
            issues.append(
                ComputeIssue("unknown_slice_boundary", str(exc), ("case", trace.id))
            )
            continue
        segments: list[tuple[int, ...]] = []
        if spec.kind in ("consecutive_activity", "timestamp_groups"):
            begin = 0
            for i in range(1, len(keys) + 1):
                if i == len(keys) or keys[i] != keys[begin]:
                    segments.append(tuple(range(begin, i)))
                    begin = i
        elif spec.kind == "prefix":
            segments = [
                tuple(range(0, i + int(spec.include_end)))
                for i, key in enumerate(keys)
                if key == spec.end_activity
            ]
        elif spec.kind == "suffix":
            segments = [
                tuple(range(i + int(not spec.include_start), len(keys)))
                for i, key in enumerate(keys)
                if key == spec.start_activity
            ]
        elif spec.kind == "between":
            for i, key in enumerate(keys):
                if key == spec.start_activity:
                    end = next(
                        (
                            j
                            for j in range(i + 1, len(keys))
                            if keys[j] == spec.end_activity
                        ),
                        None,
                    )
                    if end is not None:
                        segments.append(
                            tuple(
                                range(
                                    i + int(not spec.include_start),
                                    end + int(spec.include_end),
                                )
                            )
                        )
        else:
            boundaries = [i for i, key in enumerate(keys) if key == spec.start_activity]
            starts = [0, *boundaries]
            ends = [*boundaries, len(keys)]
            segments = [tuple(range(a, b)) for a, b in zip(starts, ends)]
        if spec.kind not in ("split", "consecutive_activity", "timestamp_groups"):
            if spec.occurrence == "first":
                segments = segments[:1]
            elif spec.occurrence == "last":
                segments = segments[-1:]
        if not trace.events and spec.empty_cases == "preserve":
            segments = [()]
        for index, positions in enumerate(segments):
            if not positions and spec.empty_cases == "drop":
                continue
            # Full source digest prevents identity reuse for changed facts.
            identity = sha256(
                f"{digest}\0{trace.id}\0{spec!r}\0{index}".encode()
            ).hexdigest()
            entries.append(_entry(trace, positions, f"pix.slice:{identity}"))
    if issues and spec.unknown == "error":
        return _derived_result(
            "pix.case_centric.slice",
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            tuple(issues),
        )
    selected = {entry.source_case_id for entry in entries}
    payload = CaseSelection(
        tuple(entries),
        tuple(trace.id for trace in log.traces if trace.id not in selected),
        tuple(unknown_cases),
        tuple(unknown_events),
        (),
        len(log.traces),
        sum(len(trace.events) for trace in log.traces),
        len(selected),
        sum(len(entry.event_ids) for entry in entries),
    )
    return _derived_result(
        "pix.case_centric.slice",
        digest,
        spec,
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        payload,
        tuple(issues),
    )


@dataclass(frozen=True, slots=True)
class CaseSampleSpec:
    """Uniform sampling without replacement, returned in original source order."""

    count: int
    unit: str = "cases"
    seed: int = 0
    empty_cases: str = "preserve"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if type(self.count) is not int or self.count < 0:
            raise ValueError("count must be a nonnegative integer")
        if type(self.seed) is not int:
            raise TypeError("seed must be an integer")
        _choice(self.unit, ("cases", "events"), "unit")
        _choice(self.empty_cases, ("preserve", "drop"), "empty_cases")


def sample_cases(
    log: CaseLog, spec: CaseSampleSpec
) -> ComputationResult[CaseSelection]:
    """Draw source cases or globally sampled events; preserve all original facts.

    For case sampling, ``empty_cases='drop'`` removes empty cases from the
    population before drawing. For event sampling it controls whether cases
    containing zero sampled events remain as empty output cases. Count overflow
    is invalid input, never an implicit clipped sample.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, CaseSampleSpec):
        raise TypeError("expected CaseLog and CaseSampleSpec")
    digest = case_log_digest(log)
    if spec.unit == "cases":
        population = tuple(
            i
            for i, trace in enumerate(log.traces)
            if trace.events or spec.empty_cases == "preserve"
        )
    else:
        population = tuple(
            (i, j)
            for i, trace in enumerate(log.traces)
            for j in range(len(trace.events))
        )
    if spec.count > len(population):
        return _derived_result(
            "pix.case_centric.sample",
            digest,
            spec,
            ComputeStatus.INVALID_INPUT,
            None,
            (
                ComputeIssue(
                    "sample_exceeds_population",
                    "Sample count exceeds the eligible source population",
                ),
            ),
        )
    chosen = set(Random(spec.seed).sample(population, spec.count))
    entries = []
    for i, trace in enumerate(log.traces):
        if spec.unit == "cases":
            if i in chosen:
                entries.append(_entry(trace, tuple(range(len(trace.events)))))
        else:
            positions = tuple(j for j in range(len(trace.events)) if (i, j) in chosen)
            if positions or spec.empty_cases == "preserve":
                entries.append(_entry(trace, positions))
    selected = {entry.source_case_id for entry in entries}
    value = CaseSelection(
        tuple(entries),
        tuple(trace.id for trace in log.traces if trace.id not in selected),
        (),
        (),
        (),
        len(log.traces),
        sum(len(trace.events) for trace in log.traces),
        len(selected),
        sum(len(entry.event_ids) for entry in entries),
    )
    return _derived_result(
        "pix.case_centric.sample", digest, spec, ComputeStatus.COMPUTED, value
    )


RESULT_SCHEMAS = {
    "pix.case_centric.filter": ("case-selection", CaseFilterSpec, CaseSelection),
    "pix.case_centric.slice": ("case-segments", CaseSliceSpec, CaseSelection),
    "pix.case_centric.sample": ("case-sample", CaseSampleSpec, CaseSelection),
}

__all__ = [
    "FilterScalar",
    "AttributeCondition",
    "CaseFilterSpec",
    "CaseSliceSpec",
    "CaseSampleSpec",
    "CaseSelection",
    "CaseSelectionEntry",
    "SelectionWitness",
    "filter_case_log",
    "slice_cases",
    "materialize_case_selection",
    "sample_cases",
]
