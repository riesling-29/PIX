"""Native case/event encodings and supervised-learning data preparation.

This module defines PIX profiles, not neural embedding approximations. Vocabulary
and smooth IDF are fitted only on the selected cases. The transform never learns
from its input. Counts use source-order activity n-grams; TF-IDF uses raw term
counts and ``log((1 + documents) / (1 + document_frequency)) + 1``. Optional L2
normalization applies to the activity block, not numerical or categorical fields.

Temporal event features see the observed prefix only. Future next/remaining-time
labels live in separate target records. Trace attributes are deliberately absent
from prefix inputs because an XES trace attribute need not have existed at start.
No trained predictor, Word2Vec/Doc2Vec/Transformer, or external runtime is implied.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
from math import floor, isfinite, sqrt
from math import log as natural_log
from typing import ClassVar, Literal

from pix.compute._common import _result
from pix.compute.conformance import align_traces
from pix.compute.model_semantics import model_digest
from pix.compute.replay import replay_traces
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import PetriNet
from pix.contracts.replay import ReplaySpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseLog, case_log_digest, case_traces
from pix.event_log.model import CaseAttribute, CaseEvent


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _integer(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _strings(value: object, name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in value:
        _text(item, name)
    if len(value) != len(set(value)):
        raise ValueError(f"{name} must be unique")


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    """One document is a whole case or one event, according to ``level``.

    The selected scalar attributes are taken at that same level, resolving XES
    globals through CaseLog.attribute. Missing numeric values remain None;
    missing/unknown categories are all-zero with separate row diagnostics.
    """

    level: Literal["trace", "event"] = "trace"
    encoding: Literal["count", "binary", "tfidf"] = "count"
    ngram_min: int = 1
    ngram_max: int = 1
    min_document_frequency: int = 1
    normalize_activity_l2: bool = False
    include_activity: bool = True
    numeric_attributes: tuple[str, ...] = ()
    categorical_attributes: tuple[str, ...] = ()
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.level not in ("trace", "event"):
            raise ValueError("level must be trace or event")
        if self.encoding not in ("count", "binary", "tfidf"):
            raise ValueError("encoding must be count, binary, or tfidf")
        _integer(self.ngram_min, "ngram_min", 1)
        _integer(self.ngram_max, "ngram_max", self.ngram_min)
        _integer(self.min_document_frequency, "min_document_frequency", 1)
        if self.level == "event" and self.ngram_max != 1:
            raise ValueError(
                "an event document contains one activity; ngrams require trace level"
            )
        for name in ("normalize_activity_l2", "include_activity"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        _strings(self.numeric_attributes, "numeric_attributes")
        _strings(self.categorical_attributes, "categorical_attributes")
        if set(self.numeric_attributes) & set(self.categorical_attributes):
            raise ValueError("an attribute cannot be both numeric and categorical")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")


@dataclass(frozen=True, slots=True)
class FeatureFitRequest:
    parameters: FeatureSpec
    training_case_ids: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, FeatureSpec):
            raise TypeError("parameters must be FeatureSpec")
        if self.training_case_ids is not None:
            _strings(self.training_case_ids, "training_case_ids")
            object.__setattr__(
                self, "training_case_ids", tuple(sorted(self.training_case_ids))
            )


@dataclass(frozen=True, slots=True)
class FeatureColumn:
    """Structured coordinates avoid collisions between labels and attribute keys."""

    kind: Literal["activity_ngram", "numeric", "categorical", "temporal", "diagnostic"]
    key: str
    terms: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in (
            "activity_ngram",
            "numeric",
            "categorical",
            "temporal",
            "diagnostic",
        ):
            raise ValueError("unknown feature column kind")
        _text(self.key, "feature key")
        if not isinstance(self.terms, tuple) or not all(
            isinstance(x, str) for x in self.terms
        ):
            raise TypeError("feature terms must be a tuple of strings")
        if self.kind == "activity_ngram" and not self.terms:
            raise ValueError("activity ngram must have terms")
        if self.kind == "categorical" and len(self.terms) != 1:
            raise ValueError("categorical column must have one type-tagged value")
        if self.kind not in ("activity_ngram", "categorical") and self.terms:
            raise ValueError("scalar feature columns do not have terms")


def _fitted_digest(model: FeatureModel) -> str:
    values = asdict(model)
    values.pop("model_digest")
    encoded = json.dumps(
        values,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return (
        "pix.case-feature-model.v1:sha256:"
        + sha256(encoded.encode("utf-8")).hexdigest()
    )


@dataclass(frozen=True, slots=True)
class FeatureModel:
    parameters: FeatureSpec
    columns: tuple[FeatureColumn, ...]
    weights: tuple[float, ...]
    document_count: int
    training_case_ids: tuple[str, ...]
    training_source_digest: str
    model_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.parameters, FeatureSpec):
            raise TypeError("parameters must be FeatureSpec")
        if not isinstance(self.columns, tuple) or not all(
            isinstance(x, FeatureColumn) for x in self.columns
        ):
            raise TypeError("columns must be a tuple of FeatureColumn")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("feature columns must be unique")
        if not isinstance(self.weights, tuple) or len(self.weights) != len(
            self.columns
        ):
            raise ValueError("one weight is required per column")
        if any(type(x) is not float or not isfinite(x) or x <= 0 for x in self.weights):
            raise ValueError("weights must be positive finite floats")
        _integer(self.document_count, "document_count")
        _strings(self.training_case_ids, "training_case_ids")
        _text(self.training_source_digest, "training_source_digest")
        if self.model_digest != _fitted_digest(self):
            raise ValueError("fitted feature model digest does not match its facts")
        spec = self.parameters
        if spec.level == "trace" and self.document_count != len(self.training_case_ids):
            raise ValueError(
                "trace feature training requires one document per selected case"
            )
        ngram_columns = tuple(
            column for column in self.columns if column.kind == "activity_ngram"
        )
        numeric_columns = tuple(
            FeatureColumn("numeric", key) for key in spec.numeric_attributes
        )
        category_columns = []
        for key in spec.categorical_attributes:
            levels = sorted(
                column.terms[0]
                for column in self.columns
                if column.kind == "categorical" and column.key == key
            )
            for level in levels:
                try:
                    pair = json.loads(level)
                    if not isinstance(pair, list) or len(pair) != 2:
                        raise ValueError("invalid category coordinate")
                    canonical = _category(CaseAttribute(key, pair[0], pair[1]))
                    if canonical != level or canonical is None:
                        raise ValueError("noncanonical category coordinate")
                except (ValueError, TypeError) as error:
                    raise ValueError(
                        "categorical coordinates must be canonical typed scalar values"
                    ) from error
            category_columns.extend(
                FeatureColumn("categorical", key, (level,)) for level in levels
            )
        expected_columns = ngram_columns + numeric_columns + tuple(category_columns)
        if self.columns != expected_columns:
            raise ValueError(
                "feature column kinds, keys, or order disagree with the fitted specification"
            )
        if ngram_columns != tuple(
            sorted(ngram_columns, key=lambda column: column.terms)
        ):
            raise ValueError("activity vocabulary must be sorted")
        if ngram_columns and not spec.include_activity:
            raise ValueError("activity columns require include_activity")
        if any(
            column.key != "activity"
            or not spec.ngram_min <= len(column.terms) <= spec.ngram_max
            or any(not term.strip() for term in column.terms)
            for column in ngram_columns
        ):
            raise ValueError("ngram coordinates disagree with the fitted specification")
        if self.document_count == 0 and (ngram_columns or category_columns):
            raise ValueError(
                "an empty training corpus cannot learn activity or category coordinates"
            )
        for column, weight in zip(self.columns, self.weights):
            if column.kind != "activity_ngram" or spec.encoding != "tfidf":
                if weight != 1.0:
                    raise ValueError("non-TFIDF coordinates must have unit weight")
            elif not 1 <= weight <= natural_log(1 + self.document_count) + 1:
                raise ValueError("IDF weight is outside the smooth-IDF training range")


@dataclass(frozen=True, slots=True)
class FeatureTransformRequest:
    fitted_model: FeatureModel

    def __post_init__(self) -> None:
        if not isinstance(self.fitted_model, FeatureModel):
            raise TypeError("fitted_model must be FeatureModel")

    @property
    def model_digest(self) -> str:
        return self.fitted_model.model_digest


@dataclass(frozen=True, slots=True)
class FeatureRow:
    case_id: str
    event_id: str | None
    values: tuple[float | None, ...]
    unknown_term_count: int = 0
    missing_attributes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        if self.event_id is not None:
            _text(self.event_id, "event_id")
        if not isinstance(self.values, tuple) or any(
            x is not None and (type(x) is not float or not isfinite(x))
            for x in self.values
        ):
            raise ValueError("feature values must be finite floats or None")
        _integer(self.unknown_term_count, "unknown_term_count")
        _strings(self.missing_attributes, "missing_attributes")


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    level: Literal["trace", "event"]
    columns: tuple[FeatureColumn, ...]
    rows: tuple[FeatureRow, ...]
    model_digest: str | None = None

    def __post_init__(self) -> None:
        if self.level not in ("trace", "event"):
            raise ValueError("level must be trace or event")
        if not isinstance(self.columns, tuple) or not all(
            isinstance(x, FeatureColumn) for x in self.columns
        ):
            raise TypeError("columns must be FeatureColumn tuples")
        if len(set(self.columns)) != len(self.columns):
            raise ValueError("columns must be unique")
        if not isinstance(self.rows, tuple) or not all(
            isinstance(x, FeatureRow) for x in self.rows
        ):
            raise TypeError("rows must be FeatureRow tuples")
        if any(len(row.values) != len(self.columns) for row in self.rows):
            raise ValueError("feature row width must equal the number of columns")
        keys = [(row.case_id, row.event_id) for row in self.rows]
        if len(set(keys)) != len(keys):
            raise ValueError("feature row identities must be unique")
        if any((row.event_id is None) != (self.level == "trace") for row in self.rows):
            raise ValueError("event identity must match matrix level")
        if self.model_digest is not None:
            _text(self.model_digest, "model_digest")


def _result_for(operator, source, spec, value, issues=(), *, invalid=False, parents=()):
    return _result(
        operator,
        None,
        spec,
        ComputeStatus.INVALID_INPUT
        if invalid
        else ComputeStatus.PARTIAL
        if issues
        else ComputeStatus.COMPUTED,
        value,
        tuple(issues),
        source_digest=source,
        parent_computation_ids=parents,
    )


def _source(log: CaseLog) -> str:
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    return case_log_digest(log)


def _project(log: CaseLog, spec: CaseTraceSpec):
    projected = case_traces(log, spec)
    if projected.status is not ComputeStatus.COMPUTED:
        raise ValueError("; ".join(issue.message for issue in projected.issues))
    return {
        trace.object_id: tuple(event.activity for event in trace.events)
        for trace in projected.value.traces
    }


def _documents(log: CaseLog, spec: FeatureSpec):
    activities = _project(log, spec.trace_spec) if spec.include_activity else {}
    for trace in log.traces:
        labels = activities.get(trace.id, ())
        if spec.level == "trace":
            yield trace.id, None, trace, labels
        else:
            for index, event in enumerate(trace.events):
                yield (
                    trace.id,
                    event.id,
                    event,
                    (labels[index],) if spec.include_activity else (),
                )


def _ngrams(labels: tuple[str, ...], spec: FeatureSpec):
    return Counter(
        tuple(labels[index : index + size])
        for size in range(spec.ngram_min, min(spec.ngram_max, len(labels)) + 1)
        for index in range(len(labels) - size + 1)
    )


def _category(attribute: CaseAttribute | None) -> str | None:
    if attribute is None or attribute.type == "null":
        return None
    if attribute.type not in ("string", "id", "int", "float", "boolean"):
        raise ValueError(
            "categorical attributes require string, id, numeric, or boolean scalar values"
        )
    if attribute.type == "float" and not isfinite(attribute.value):
        raise ValueError("nonfinite categorical attribute")
    return json.dumps(
        (attribute.type, attribute.value),
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def _numeric(attribute: CaseAttribute | None) -> float | None:
    if attribute is None or attribute.type == "null":
        return None
    if attribute.type not in ("int", "float"):
        raise ValueError("numeric features require int or float attributes")
    try:
        value = float(attribute.value)
    except OverflowError as error:
        raise ValueError(
            "numeric attribute cannot be represented as a finite float"
        ) from error
    if not isfinite(value):
        raise ValueError("nonfinite numeric attribute")
    return value


def fit_features(
    log: CaseLog,
    spec: FeatureSpec = FeatureSpec(),
    *,
    training_case_ids: tuple[str, ...] | None = None,
) -> ComputationResult[FeatureModel]:
    """Fit activity vocabulary, categories and IDF exclusively on selected cases.

    None means all cases in the supplied training log. An explicit empty tuple
    means zero training cases. Held-out malformed attributes are not read.
    """
    source = _source(log)
    request = FeatureFitRequest(spec, training_case_ids)
    try:
        selected = (
            set(request.training_case_ids)
            if request.training_case_ids is not None
            else {trace.id for trace in log.traces}
        )
        unknown = selected - {trace.id for trace in log.traces}
        if unknown:
            raise ValueError(f"unknown training case IDs: {sorted(unknown)!r}")
        training = replace(
            log, traces=tuple(trace for trace in log.traces if trace.id in selected)
        )
        document_count = 0
        frequency = Counter()
        categories = {key: set() for key in spec.categorical_attributes}
        for _, _, item, labels in _documents(training, spec):
            document_count += 1
            frequency.update(_ngrams(labels, spec).keys())
            for key in categories:
                value = _category(training.attribute(item, key))
                if value is not None:
                    categories[key].add(value)
            for key in spec.numeric_attributes:
                _numeric(training.attribute(item, key))
        vocabulary = sorted(
            terms
            for terms, count in frequency.items()
            if count >= spec.min_document_frequency
        )
        columns = tuple(
            FeatureColumn("activity_ngram", "activity", terms) for terms in vocabulary
        )
        weights = tuple(
            float(natural_log((1 + document_count) / (1 + frequency[terms])) + 1)
            if spec.encoding == "tfidf"
            else 1.0
            for terms in vocabulary
        )
        columns += tuple(
            FeatureColumn("numeric", key) for key in spec.numeric_attributes
        )
        weights += (1.0,) * len(spec.numeric_attributes)
        for key in spec.categorical_attributes:
            levels = sorted(categories[key])
            columns += tuple(
                FeatureColumn("categorical", key, (level,)) for level in levels
            )
            weights += (1.0,) * len(levels)
        # Compute identity before construction without weakening model validation.
        facts = dict(
            parameters=asdict(spec),
            columns=[asdict(column) for column in columns],
            weights=weights,
            document_count=document_count,
            training_case_ids=tuple(sorted(selected)),
            training_source_digest=case_log_digest(training),
        )
        digest = (
            "pix.case-feature-model.v1:sha256:"
            + sha256(
                json.dumps(
                    facts,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                ).encode("utf-8")
            ).hexdigest()
        )
        model = FeatureModel(
            spec,
            columns,
            weights,
            document_count,
            tuple(sorted(selected)),
            case_log_digest(training),
            digest,
        )
    except (ValueError, OverflowError) as error:
        return _result_for(
            "pix.case_centric.fit_features",
            source,
            request,
            None,
            (ComputeIssue("invalid_feature_training_data", str(error)),),
            invalid=True,
        )
    return _result_for("pix.case_centric.fit_features", source, request, model)


def transform_features(
    log: CaseLog, fitted_model: FeatureModel
) -> ComputationResult[FeatureMatrix]:
    """Apply a fixed model; unseen terms/categories cannot alter the feature space."""
    source = _source(log)
    request = FeatureTransformRequest(fitted_model)
    spec = fitted_model.parameters
    vocabulary = {
        column.terms
        for column in fitted_model.columns
        if column.kind == "activity_ngram"
    }
    known_categories = {
        (column.key, column.terms[0])
        for column in fitted_model.columns
        if column.kind == "categorical"
    }
    rows, issues = [], []
    try:
        for case_id, event_id, item, labels in _documents(log, spec):
            counts = _ngrams(labels, spec)
            numeric = {
                key: _numeric(log.attribute(item, key))
                for key in spec.numeric_attributes
            }
            categorical = {
                key: _category(log.attribute(item, key))
                for key in spec.categorical_attributes
            }
            missing = tuple(
                key
                for key in (*spec.numeric_attributes, *spec.categorical_attributes)
                if (numeric if key in numeric else categorical)[key] is None
            )
            unknown = sum(
                count for terms, count in counts.items() if terms not in vocabulary
            )
            unknown += sum(
                value is not None and (key, value) not in known_categories
                for key, value in categorical.items()
            )
            values = []
            for column, weight in zip(fitted_model.columns, fitted_model.weights):
                if column.kind == "activity_ngram":
                    count = counts[column.terms]
                    values.append(
                        float(bool(count))
                        if spec.encoding == "binary"
                        else float(count) * weight
                    )
                elif column.kind == "numeric":
                    values.append(numeric[column.key])
                else:
                    values.append(float(categorical[column.key] == column.terms[0]))
            activity_width = len(vocabulary)
            if spec.normalize_activity_l2:
                norm = sqrt(sum(value * value for value in values[:activity_width]))
                if norm:
                    values[:activity_width] = [
                        value / norm for value in values[:activity_width]
                    ]
            rows.append(FeatureRow(case_id, event_id, tuple(values), unknown, missing))
            at = (case_id,) if event_id is None else (case_id, event_id)
            if missing:
                issues.append(
                    ComputeIssue(
                        "missing_feature_attribute",
                        "No value was imputed for: " + ", ".join(missing),
                        at,
                    )
                )
            if unknown:
                issues.append(
                    ComputeIssue(
                        "out_of_vocabulary",
                        f"{unknown} term occurrences or category values were outside the fixed training vocabulary",
                        at,
                    )
                )
    except (ValueError, OverflowError) as error:
        return _result_for(
            "pix.case_centric.transform_features",
            source,
            request,
            None,
            (ComputeIssue("invalid_feature_transform_data", str(error)),),
            invalid=True,
        )
    return _result_for(
        "pix.case_centric.transform_features",
        source,
        request,
        FeatureMatrix(
            spec.level, fitted_model.columns, tuple(rows), fitted_model.model_digest
        ),
        issues,
    )


@dataclass(frozen=True, slots=True)
class TemporalFeatureSpec:
    timestamp_key: str = "time:timestamp"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _text(self.timestamp_key, "timestamp_key")


def _timestamp(log: CaseLog, event: CaseEvent, key: str) -> datetime | None:
    attribute = log.attribute(event, key)
    if attribute is None or attribute.type != "date":
        return None
    value = attribute.value
    return value if value.tzinfo is not None and value.utcoffset() is not None else None


def _seconds(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    # Subtract UTC instants even when both values share a DST-aware tzinfo.
    # Subtracting offsets AFTER the wall-time difference also handles valid
    # year-1/year-9999 dates whose UTC representation is outside datetime's range.
    value = (
        (end.replace(tzinfo=None) - start.replace(tzinfo=None))
        - (end.utcoffset() - start.utcoffset())
    ).total_seconds()
    return value if value >= 0 else None


def temporal_features(
    log: CaseLog, spec: TemporalFeatureSpec = TemporalFeatureSpec()
) -> ComputationResult[FeatureMatrix]:
    """Event position and prefix elapsed/gap times; local calendar fields explicit.

    No future event or case endpoint is accessed to construct an event row.
    Negative/missing time differences are unknown, never absolute-valued or sorted.
    """
    source = _source(log)
    if not isinstance(spec, TemporalFeatureSpec):
        raise TypeError("spec must be TemporalFeatureSpec")
    columns = tuple(
        FeatureColumn("temporal", key)
        for key in (
            "event_position",
            "elapsed_seconds",
            "previous_gap_seconds",
            "local_hour",
            "local_weekday",
            "utc_offset_seconds",
        )
    )
    rows, issues = [], []
    try:
        for trace in log.traces:
            first = previous = None
            for index, event in enumerate(trace.events):
                current = _timestamp(log, event, spec.timestamp_key)
                if index == 0:
                    first = current
                elapsed = _seconds(first, current)
                gap = (
                    _seconds(previous, current)
                    if index
                    else (0.0 if current is not None else None)
                )
                values = (
                    float(index + 1),
                    elapsed,
                    gap,
                    float(current.hour) if current else None,
                    float(current.weekday()) if current else None,
                    current.utcoffset().total_seconds() if current else None,
                )
                rows.append(FeatureRow(trace.id, event.id, values))
                if elapsed is None or gap is None:
                    issues.append(
                        ComputeIssue(
                            "unknown_temporal_feature",
                            "Missing, timezone-naive, or decreasing observed timestamps; affected values remain None",
                            (trace.id, event.id),
                        )
                    )
                previous = current
    except ValueError as error:
        return _result_for(
            "pix.case_centric.temporal_features",
            source,
            spec,
            None,
            (ComputeIssue("ambiguous_temporal_attribute", str(error)),),
            invalid=True,
        )
    return _result_for(
        "pix.case_centric.temporal_features",
        source,
        spec,
        FeatureMatrix("event", columns, tuple(rows)),
        issues,
    )


@dataclass(frozen=True, slots=True)
class PrefixSpec:
    min_length: int = 1
    max_length: int | None = None
    include_complete: bool = True
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_prefixes: int = 100000
    max_total_prefix_events: int = 1000000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.min_length, "min_length")
        if self.max_length is not None:
            _integer(self.max_length, "max_length", self.min_length)
        if type(self.include_complete) is not bool:
            raise TypeError("include_complete must be bool")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        _integer(self.max_prefixes, "max_prefixes", 1)
        _integer(self.max_total_prefix_events, "max_total_prefix_events", 1)


@dataclass(frozen=True, slots=True)
class PrefixInput:
    case_id: str
    length: int
    event_ids: tuple[str, ...]
    activities: tuple[str, ...]
    elapsed_seconds: float | None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _integer(self.length, "length")
        _strings(self.event_ids, "event_ids")
        if not isinstance(self.activities, tuple) or not all(
            isinstance(x, str) and x for x in self.activities
        ):
            raise ValueError("activities must be a tuple of labels")
        if len(self.event_ids) != self.length or len(self.activities) != self.length:
            raise ValueError(
                "prefix length must match its event and activity sequences"
            )
        if self.elapsed_seconds is not None and (
            type(self.elapsed_seconds) is not float
            or not isfinite(self.elapsed_seconds)
            or self.elapsed_seconds < 0
        ):
            raise ValueError("elapsed_seconds must be nonnegative finite float or None")


@dataclass(frozen=True, slots=True)
class PredictionTarget:
    case_id: str
    prefix_length: int
    next_activity: str | None
    is_terminal: bool
    next_time_seconds: float | None
    remaining_time_seconds: float | None

    def __post_init__(self) -> None:
        _text(self.case_id, "case_id")
        _integer(self.prefix_length, "prefix_length")
        if self.next_activity is not None:
            _text(self.next_activity, "next_activity")
        if type(self.is_terminal) is not bool or self.is_terminal != (
            self.next_activity is None
        ):
            raise ValueError("terminal target must have no next activity")
        for name in ("next_time_seconds", "remaining_time_seconds"):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not float or not isfinite(value) or value < 0
            ):
                raise ValueError(f"{name} must be nonnegative finite float or None")
        if self.is_terminal and self.next_time_seconds is not None:
            raise ValueError("terminal prefix has no next-time target")


@dataclass(frozen=True, slots=True)
class PrefixDataset:
    inputs: tuple[PrefixInput, ...]
    targets: tuple[PredictionTarget, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, tuple) or not all(
            isinstance(x, PrefixInput) for x in self.inputs
        ):
            raise TypeError("inputs must be PrefixInput tuples")
        if not isinstance(self.targets, tuple) or not all(
            isinstance(x, PredictionTarget) for x in self.targets
        ):
            raise TypeError("targets must be PredictionTarget tuples")
        keys = tuple((x.case_id, x.length) for x in self.inputs)
        if len(set(keys)) != len(keys) or keys != tuple(
            (x.case_id, x.prefix_length) for x in self.targets
        ):
            raise ValueError(
                "inputs and targets require matching, unique case/prefix identities"
            )


def prefix_dataset(
    log: CaseLog, spec: PrefixSpec = PrefixSpec()
) -> ComputationResult[PrefixDataset]:
    """Materialize prefixes and separate future targets; split CASES before use.

    With a zero-length prefix there is no observed clock origin, so next-time and
    remaining-time targets are unknown. Terminal next activity/time is None with
    an explicit terminal flag, never a string that can collide with an activity.
    """
    source = _source(log)
    if not isinstance(spec, PrefixSpec):
        raise TypeError("spec must be PrefixSpec")
    inputs, targets, issues = [], [], []
    prefix_count = total_prefix_events = 0
    for trace in log.traces:
        end = len(trace.events) - (0 if spec.include_complete else 1)
        if spec.max_length is not None:
            end = min(end, spec.max_length)
        count = max(0, end - spec.min_length + 1)
        prefix_count += count
        total_prefix_events += count * (spec.min_length + end) // 2
    if (
        prefix_count > spec.max_prefixes
        or total_prefix_events > spec.max_total_prefix_events
    ):
        return _result(
            "pix.case_centric.prefix_dataset",
            None,
            spec,
            ComputeStatus.UNAVAILABLE,
            None,
            (
                ComputeIssue(
                    "prefix_materialization_limit",
                    "Requested complete prefix dataset exceeds max_prefixes or max_total_prefix_events; no truncated training dataset is returned",
                ),
            ),
            source_digest=source,
        )
    try:
        activities = _project(log, spec.trace_spec)
        for trace in log.traces:
            times = tuple(
                _timestamp(log, event, spec.trace_spec.timestamp_key)
                for event in trace.events
            )
            size = len(trace.events)
            end = size if spec.include_complete else size - 1
            if spec.max_length is not None:
                end = min(end, spec.max_length)
            for length in range(spec.min_length, end + 1):
                current = times[length - 1] if length else None
                elapsed = _seconds(times[0], current) if length else None
                terminal = length == size
                next_time = None if terminal else _seconds(current, times[length])
                remaining = _seconds(current, times[-1]) if size else None
                inputs.append(
                    PrefixInput(
                        trace.id,
                        length,
                        tuple(event.id for event in trace.events[:length]),
                        activities[trace.id][:length],
                        elapsed,
                    )
                )
                targets.append(
                    PredictionTarget(
                        trace.id,
                        length,
                        None if terminal else activities[trace.id][length],
                        terminal,
                        next_time,
                        remaining,
                    )
                )
                if length and (
                    elapsed is None
                    or remaining is None
                    or (not terminal and next_time is None)
                ):
                    issues.append(
                        ComputeIssue(
                            "unknown_prediction_time",
                            "Missing, timezone-naive, or decreasing timestamps; unknown times remain None",
                            (trace.id, str(length)),
                        )
                    )
    except ValueError as error:
        return _result_for(
            "pix.case_centric.prefix_dataset",
            source,
            spec,
            None,
            (ComputeIssue("invalid_prefix_data", str(error)),),
            invalid=True,
        )
    return _result_for(
        "pix.case_centric.prefix_dataset",
        source,
        spec,
        PrefixDataset(tuple(inputs), tuple(targets)),
        issues,
    )


@dataclass(frozen=True, slots=True)
class CaseSplitSpec:
    train_fraction: float = 0.8
    validation_fraction: float = 0.0
    seed: str = "pix-case-split-v1"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        for name in ("train_fraction", "validation_fraction"):
            value = getattr(self, name)
            if type(value) is not float or not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be a finite float in [0, 1]")
        if (
            Fraction(str(self.train_fraction)) + Fraction(str(self.validation_fraction))
            > 1
        ):
            raise ValueError("train and validation fractions must sum to <= 1")
        _text(self.seed, "seed")


@dataclass(frozen=True, slots=True)
class CaseSplit:
    train_case_ids: tuple[str, ...]
    validation_case_ids: tuple[str, ...]
    test_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("train_case_ids", "validation_case_ids", "test_case_ids"):
            _strings(getattr(self, name), name)
        all_ids = self.train_case_ids + self.validation_case_ids + self.test_case_ids
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("a case cannot belong to more than one split")


def split_cases(
    log: CaseLog, spec: CaseSplitSpec = CaseSplitSpec()
) -> ComputationResult[CaseSplit]:
    """Hash-rank case IDs; exact floor(n * fraction) sizes, remainder goes to test.

    Source-order invariant for a fixed population, independent of activities and
    future labels. Adding cases may change assignments because sizes are exact.
    The split is not stratified and does not prevent temporal distribution shift.
    """
    source = _source(log)
    if not isinstance(spec, CaseSplitSpec):
        raise TypeError("spec must be CaseSplitSpec")

    def rank(case_id):
        encoded = json.dumps(
            (spec.seed, case_id), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        return sha256(encoded).digest(), case_id

    ids = sorted((trace.id for trace in log.traces), key=rank)
    # Interpret the public decimal fractions exactly; 100 * 0.29 must not lose
    # one case because binary floating-point multiplication yields 28.999999...
    train_end = floor(len(ids) * Fraction(str(spec.train_fraction)))
    validation_end = train_end + floor(
        len(ids) * Fraction(str(spec.validation_fraction))
    )
    value = CaseSplit(
        tuple(sorted(ids[:train_end])),
        tuple(sorted(ids[train_end:validation_end])),
        tuple(sorted(ids[validation_end:])),
    )
    return _result_for("pix.case_centric.split_cases", source, spec, value)


@dataclass(frozen=True, slots=True)
class TemporalWindowSpec:
    """Fixed UTC-anchored half-open windows, with retrospective case aggregates.

    An event is assigned by its completion timestamp. Each represented case
    contributes once to the window's case averages, even when it has many events.
    A case's span and service values use the ENTIRE supplied case; these are
    retrospective descriptive features and must not be treated as online inputs.
    Calendar month/week rules and lifecycle pairing are not implied.
    """

    width_seconds: int = 86400
    anchor: datetime = datetime(1970, 1, 1, tzinfo=timezone.utc)
    timestamp_key: str = "time:timestamp"
    start_timestamp_key: str | None = None
    resource_key: str = "org:resource"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    include_empty_windows: bool = False
    max_windows: int = 100000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        _integer(self.width_seconds, "width_seconds", 1)
        _integer(self.max_windows, "max_windows", 1)
        if (
            not isinstance(self.anchor, datetime)
            or self.anchor.tzinfo is None
            or self.anchor.utcoffset() is None
        ):
            raise ValueError("anchor must be a timezone-aware datetime")
        for name in ("timestamp_key", "resource_key"):
            _text(getattr(self, name), name)
        if self.start_timestamp_key is not None:
            _text(self.start_timestamp_key, "start_timestamp_key")
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if type(self.include_empty_windows) is not bool:
            raise TypeError("include_empty_windows must be bool")


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    index: int
    start: datetime
    end: datetime
    event_ids: tuple[str, ...]
    case_ids: tuple[str, ...]
    unique_activities: int
    unique_resources: int
    resource_known_events: int
    resources_complete_case_count: int
    repeated_activity_events: int
    mean_events_per_case: float | None
    mean_cases_per_resource: float | None
    mean_resources_per_case: float | None
    mean_case_observed_span_seconds: float | None
    observed_span_case_count: int
    mean_case_service_sum_seconds: float | None
    service_case_count: int
    mean_case_nonservice_span_seconds: float | None
    nonservice_case_count: int
    mean_case_interarrival_seconds: float | None
    interarrival_case_count: int
    mean_case_interfinish_seconds: float | None
    interfinish_case_count: int

    def __post_init__(self) -> None:
        if type(self.index) is not int:
            raise TypeError("window index must be int")
        if any(
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
            for value in (self.start, self.end)
        ):
            raise ValueError("window boundaries must be aware datetime")
        if _seconds(self.start, self.end) in (None, 0.0):
            raise ValueError("window end must be after start")
        _strings(self.event_ids, "event_ids")
        _strings(self.case_ids, "case_ids")
        for name in (
            "unique_activities",
            "unique_resources",
            "resource_known_events",
            "resources_complete_case_count",
            "repeated_activity_events",
            "observed_span_case_count",
            "service_case_count",
            "nonservice_case_count",
            "interarrival_case_count",
            "interfinish_case_count",
        ):
            _integer(getattr(self, name), name)
        for name in (
            "mean_events_per_case",
            "mean_cases_per_resource",
            "mean_resources_per_case",
            "mean_case_observed_span_seconds",
            "mean_case_service_sum_seconds",
            "mean_case_nonservice_span_seconds",
            "mean_case_interarrival_seconds",
            "mean_case_interfinish_seconds",
        ):
            value = getattr(self, name)
            if value is not None and (
                type(value) is not float or not isfinite(value) or value < 0
            ):
                raise ValueError(f"{name} must be finite nonnegative float or None")
        if self.resource_known_events > len(
            self.event_ids
        ) or self.repeated_activity_events > len(self.event_ids):
            raise ValueError("window event counts exceed their population")
        for name in (
            "resources_complete_case_count",
            "observed_span_case_count",
            "service_case_count",
            "nonservice_case_count",
            "interarrival_case_count",
            "interfinish_case_count",
        ):
            if getattr(self, name) > len(self.case_ids):
                raise ValueError(
                    "window metric case denominator exceeds its population"
                )


@dataclass(frozen=True, slots=True)
class TemporalWindowSet:
    windows: tuple[TemporalWindow, ...]
    requested_event_count: int
    assigned_event_count: int
    excluded_event_ids: tuple[str, ...]
    retrospective_case_aggregates: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.windows, tuple) or not all(
            isinstance(x, TemporalWindow) for x in self.windows
        ):
            raise TypeError("windows must be TemporalWindow tuples")
        _integer(self.requested_event_count, "requested_event_count")
        _integer(self.assigned_event_count, "assigned_event_count")
        _strings(self.excluded_event_ids, "excluded_event_ids")
        indexes = tuple(window.index for window in self.windows)
        if indexes != tuple(sorted(set(indexes))):
            raise ValueError("windows require unique increasing indices")
        included = tuple(
            event_id for window in self.windows for event_id in window.event_ids
        )
        if len(included) != len(set(included)) or set(included) & set(
            self.excluded_event_ids
        ):
            raise ValueError("event coverage must be disjoint")
        if (
            len(included) != self.assigned_event_count
            or self.assigned_event_count + len(self.excluded_event_ids)
            != self.requested_event_count
        ):
            raise ValueError("temporal window event counts do not conserve coverage")
        if self.retrospective_case_aggregates is not True:
            raise ValueError("whole-case window aggregates are retrospective")


def _instant_microseconds(value: datetime) -> int:
    difference = value.replace(tzinfo=None) - datetime(1970, 1, 1)
    difference -= value.utcoffset()
    return (
        difference.days * 86400 + difference.seconds
    ) * 1000000 + difference.microseconds


def temporal_window_features(
    log: CaseLog, spec: TemporalWindowSpec = TemporalWindowSpec()
) -> ComputationResult[TemporalWindowSet]:
    """Compute window counts, resource relations and case-weighted time features.

    Rework means excess occurrences of each activity within each case/window.
    Case arrival/finish gaps are differences of sorted observed case boundaries;
    the first case's gap is unknown, not zero. Service SUM may exceed span for
    overlapping work. Nonservice span subtracts the UNION of observed service
    intervals, so it is not the same calculation as span minus service SUM.
    Missing values retain None and explicit valid-case denominators. Resource
    cardinalities use known observations; mean resources per case uses only cases
    whose events in this window ALL have observed resources. Equal case boundary
    instants are ordered by case ID; the first gap is unknown and later tied gaps
    are zero. This is an aggregation convention, not evidence of causal order.
    """
    source = _source(log)
    if not isinstance(spec, TemporalWindowSpec):
        raise TypeError("spec must be TemporalWindowSpec")
    issues, excluded, groups, case_times = [], [], {}, {}
    try:
        activities = _project(log, spec.trace_spec)
        anchor_us = _instant_microseconds(spec.anchor)
        width_us = spec.width_seconds * 1000000
        for trace in log.traces:
            completions, starts, intervals = [], [], []
            all_completion_times = all_start_times = True
            for event, activity in zip(trace.events, activities[trace.id]):
                completion = _timestamp(log, event, spec.timestamp_key)
                start = (
                    _timestamp(log, event, spec.start_timestamp_key)
                    if spec.start_timestamp_key
                    else None
                )
                end_us = (
                    _instant_microseconds(completion)
                    if completion is not None
                    else None
                )
                start_us = _instant_microseconds(start) if start is not None else None
                all_completion_times &= end_us is not None
                all_start_times &= (
                    start_us is not None and end_us is not None and start_us <= end_us
                )
                if end_us is not None:
                    completions.append(end_us)
                if start_us is not None:
                    starts.append(start_us)
                if start_us is not None and end_us is not None and start_us <= end_us:
                    intervals.append((start_us, end_us))
                if end_us is None:
                    excluded.append(event.id)
                    issues.append(
                        ComputeIssue(
                            "window_timestamp_unknown",
                            "Event cannot be assigned to a time window without an aware completion timestamp",
                            (trace.id, event.id),
                        )
                    )
                    continue
                resource = _category(log.attribute(event, spec.resource_key))
                if resource is None:
                    issues.append(
                        ComputeIssue(
                            "window_resource_unknown",
                            "Resource cardinalities use only known resource observations",
                            (trace.id, event.id),
                        )
                    )
                index = (end_us - anchor_us) // width_us
                groups.setdefault(index, []).append(
                    (event.id, trace.id, activity, resource)
                )
            arrival = finish = span = service = nonservice = None
            if trace.events and all_completion_times:
                finish = max(completions)
                # No start column means observed completion-to-completion span.
                if spec.start_timestamp_key is None or all_start_times:
                    arrival = (
                        min(starts) if spec.start_timestamp_key else min(completions)
                    )
                    span = (finish - arrival) / 1000000
                if spec.start_timestamp_key and all_start_times:
                    service = sum(end - begin for begin, end in intervals) / 1000000
                    merged = []
                    for begin, end in sorted(intervals):
                        if merged and begin <= merged[-1][1]:
                            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                        else:
                            merged.append((begin, end))
                    occupied = sum(end - begin for begin, end in merged) / 1000000
                    nonservice = max(0.0, span - occupied)
            if trace.events and (
                not all_completion_times
                or (spec.start_timestamp_key and not all_start_times)
            ):
                issues.append(
                    ComputeIssue(
                        "window_case_time_unknown",
                        "Whole-case metrics require every selected interval boundary; affected case metrics remain unknown",
                        (trace.id,),
                    )
                )
            case_times[trace.id] = [
                arrival,
                finish,
                span,
                service,
                nonservice,
                None,
                None,
            ]
        for boundary, destination in ((0, 5), (1, 6)):
            previous = None
            for instant, case_id in sorted(
                (values[boundary], case_id)
                for case_id, values in case_times.items()
                if values[boundary] is not None
            ):
                if previous is not None:
                    case_times[case_id][destination] = (instant - previous) / 1000000
                previous = instant
        indexes = sorted(groups)
        if spec.include_empty_windows and indexes:
            window_count = indexes[-1] - indexes[0] + 1
            if window_count > spec.max_windows:
                return _result(
                    "pix.case_centric.temporal_window_features",
                    None,
                    spec,
                    ComputeStatus.UNAVAILABLE,
                    None,
                    (
                        ComputeIssue(
                            "window_materialization_limit",
                            "Requested range exceeds max_windows; no partial window series is returned",
                        ),
                    ),
                    source_digest=source,
                )
            indexes = range(indexes[0], indexes[-1] + 1)
        if len(indexes) > spec.max_windows:
            return _result(
                "pix.case_centric.temporal_window_features",
                None,
                spec,
                ComputeStatus.UNAVAILABLE,
                None,
                (
                    ComputeIssue(
                        "window_materialization_limit",
                        "Requested windows exceed max_windows",
                    ),
                ),
                source_digest=source,
            )
        windows = []
        anchor_utc = spec.anchor.astimezone(timezone.utc)
        for index in indexes:
            entries = groups.get(index, ())
            case_ids = tuple(sorted({entry[1] for entry in entries}))
            resource_cases, case_resources, case_activities, case_event_counts = (
                {},
                {},
                {},
                Counter(),
            )
            for _, case_id, activity, resource in entries:
                case_activities.setdefault(case_id, set()).add(activity)
                case_event_counts[case_id] += 1
                case_resources.setdefault(case_id, set())
                if resource is not None:
                    resource_cases.setdefault(resource, set()).add(case_id)
                    case_resources[case_id].add(resource)
            resource_incomplete_cases = {
                case_id for _, case_id, _, resource in entries if resource is None
            }
            resource_complete_cases = set(case_ids) - resource_incomplete_cases

            def average_metric(column):
                values = [
                    case_times[case_id][column]
                    for case_id in case_ids
                    if case_times[case_id][column] is not None
                ]
                return (sum(values) / len(values) if values else None), len(values)

            start = anchor_utc + timedelta(seconds=index * spec.width_seconds)
            end = start + timedelta(seconds=spec.width_seconds)
            metrics = tuple(
                item for column in range(2, 7) for item in average_metric(column)
            )
            windows.append(
                TemporalWindow(
                    index,
                    start,
                    end,
                    tuple(entry[0] for entry in entries),
                    case_ids,
                    len({entry[2] for entry in entries}),
                    len(resource_cases),
                    sum(entry[3] is not None for entry in entries),
                    len(resource_complete_cases),
                    sum(
                        case_event_counts[case_id] - len(case_activities[case_id])
                        for case_id in case_ids
                    ),
                    len(entries) / len(case_ids) if case_ids else None,
                    sum(len(cases) for cases in resource_cases.values())
                    / len(resource_cases)
                    if resource_cases
                    else None,
                    sum(
                        len(case_resources[case_id])
                        for case_id in resource_complete_cases
                    )
                    / len(resource_complete_cases)
                    if resource_complete_cases
                    else None,
                    *metrics,
                )
            )
    except (ValueError, OverflowError) as error:
        return _result_for(
            "pix.case_centric.temporal_window_features",
            source,
            spec,
            None,
            (ComputeIssue("invalid_temporal_window_data", str(error)),),
            invalid=True,
        )
    requested = sum(len(trace.events) for trace in log.traces)
    payload = TemporalWindowSet(
        tuple(windows), requested, requested - len(excluded), tuple(excluded)
    )
    return _result_for(
        "pix.case_centric.temporal_window_features", source, spec, payload, issues
    )


@dataclass(frozen=True, slots=True)
class ModelFeatureSpec:
    method: Literal["alignment", "token_replay"] = "alignment"
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    alignment: AlignmentSpec = AlignmentSpec()
    replay: ReplaySpec = ReplaySpec()
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self) -> None:
        if self.method not in ("alignment", "token_replay"):
            raise ValueError("method must be alignment or token_replay")
        for name, kind in (
            ("trace_spec", CaseTraceSpec),
            ("alignment", AlignmentSpec),
            ("replay", ReplaySpec),
        ):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")


@dataclass(frozen=True, slots=True)
class ModelFeatureRequest:
    model_digest: str
    parameters: ModelFeatureSpec

    def __post_init__(self) -> None:
        _text(self.model_digest, "model_digest")
        if not isinstance(self.parameters, ModelFeatureSpec):
            raise TypeError("parameters must be ModelFeatureSpec")


def model_features(
    log: CaseLog, net: PetriNet, spec: ModelFeatureSpec = ModelFeatureSpec()
) -> ComputationResult[FeatureMatrix]:
    """Encode completed native alignment/replay diagnostics against a fixed net.

    Alignment uses the selected cost profile, not normalized fitness. Limited or
    unreachable rows retain None rather than treating a prefix as a completed
    case. The supplied net must itself be trained without held-out cases if the
    features are used in an evaluation pipeline; this function does not fit it.
    """
    source = _source(log)
    if not isinstance(spec, ModelFeatureSpec):
        raise TypeError("spec must be ModelFeatureSpec")
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    request = ModelFeatureRequest(model_digest(net), spec)
    traces = case_traces(log, spec.trace_spec)
    if traces.status is not ComputeStatus.COMPUTED:
        return _result_for(
            "pix.case_centric.model_features",
            source,
            request,
            None,
            traces.issues,
            invalid=True,
            parents=(traces.computation_id,),
        )
    result = (
        align_traces(traces, net, spec.alignment)
        if spec.method == "alignment"
        else replay_traces(traces, net, spec.replay)
    )
    parents = (result.computation_id,)
    if result.value is None:
        return _result(
            "pix.case_centric.model_features",
            None,
            request,
            result.status,
            None,
            result.issues,
            source_digest=source,
            parent_computation_ids=parents,
        )
    rows, issues = [], []

    def numbers(values, case_id):
        encoded = []
        for value in values:
            try:
                converted = float(value)
            except OverflowError:
                converted = None
            if converted is not None and not isfinite(converted):
                converted = None
            encoded.append(converted)
        if any(value is None for value in encoded):
            issues.append(
                ComputeIssue(
                    "unrepresentable_model_feature",
                    "An exact model diagnostic cannot be represented as a finite float; affected feature values remain None",
                    (case_id,),
                )
            )
        return tuple(encoded)

    if spec.method == "alignment":
        keys = (
            "alignment_cost",
            "synchronous_moves",
            "log_moves",
            "model_moves",
            "silent_moves",
        )
        for row in result.value.alignments:
            if row.status == "optimal":
                counts = Counter(move.kind for move in row.moves)
                values = numbers(
                    (
                        row.cost,
                        *(
                            counts[kind]
                            for kind in ("synchronous", "log", "model", "silent")
                        ),
                    ),
                    row.object_id,
                )
            else:
                values = (None,) * len(keys)
                issues.append(
                    ComputeIssue(
                        "incomplete_model_feature",
                        f"Alignment is {row.status}; completed feature values are unknown",
                        (row.object_id,),
                    )
                )
            rows.append(FeatureRow(row.object_id, None, values))
    else:
        keys = (
            "missing_tokens",
            "remaining_tokens",
            "consumed_tokens",
            "produced_tokens",
            "log_deviations",
        )
        for row in result.value.traces:
            if row.status == "completed":
                values = numbers(
                    (
                        row.counts.missing,
                        row.counts.remaining,
                        row.counts.consumed,
                        row.counts.produced,
                        row.log_deviation_count,
                    ),
                    row.object_id,
                )
            else:
                values = (None,) * len(keys)
                issues.append(
                    ComputeIssue(
                        "incomplete_model_feature",
                        "Replay is limited; completed feature values are unknown",
                        (row.object_id,),
                    )
                )
            rows.append(FeatureRow(row.object_id, None, values))
    columns = tuple(FeatureColumn("diagnostic", key) for key in keys)
    return _result_for(
        "pix.case_centric.model_features",
        source,
        request,
        FeatureMatrix("trace", columns, tuple(rows), request.model_digest),
        issues,
        parents=parents,
    )


RESULT_SCHEMAS = {
    "pix.case_centric.fit_features": (
        "case-feature-model",
        FeatureFitRequest,
        FeatureModel,
    ),
    "pix.case_centric.transform_features": (
        "case-feature-matrix",
        FeatureTransformRequest,
        FeatureMatrix,
    ),
    "pix.case_centric.temporal_features": (
        "case-temporal-features",
        TemporalFeatureSpec,
        FeatureMatrix,
    ),
    "pix.case_centric.prefix_dataset": (
        "case-prefix-dataset",
        PrefixSpec,
        PrefixDataset,
    ),
    "pix.case_centric.split_cases": ("case-learning-split", CaseSplitSpec, CaseSplit),
    "pix.case_centric.temporal_window_features": (
        "case-temporal-window-features",
        TemporalWindowSpec,
        TemporalWindowSet,
    ),
    "pix.case_centric.model_features": (
        "case-model-features",
        ModelFeatureRequest,
        FeatureMatrix,
    ),
}

__all__ = [
    "FeatureSpec",
    "FeatureFitRequest",
    "FeatureColumn",
    "FeatureModel",
    "FeatureTransformRequest",
    "FeatureRow",
    "FeatureMatrix",
    "fit_features",
    "transform_features",
    "TemporalFeatureSpec",
    "temporal_features",
    "PrefixSpec",
    "PrefixInput",
    "PredictionTarget",
    "PrefixDataset",
    "prefix_dataset",
    "CaseSplitSpec",
    "CaseSplit",
    "split_cases",
    "ModelFeatureSpec",
    "ModelFeatureRequest",
    "model_features",
    "TemporalWindowSpec",
    "TemporalWindow",
    "TemporalWindowSet",
    "temporal_window_features",
]
