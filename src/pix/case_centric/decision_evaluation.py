"""Train-only feature encoding and case/group-separated decision evaluation.

Categorical vocabularies are fitted on eligible training occurrences only.
Missing values and unknown categories are exposed as masks, never silently
interpreted as observed zeroes. Evaluation excludes those rows and reports their
coverage cost. External features remain a caller declaration: this module cannot
certify that an externally supplied value existed before the decision outcome.
The numeric conformance-table adapter retains the upstream prefix safeguards.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction
from hashlib import sha256
from math import isfinite
from typing import ClassVar, Literal

from pix.case_centric.advanced import (
    CaseVector,
    DecisionExample,
    DecisionTree,
    DecisionTreeSpec,
    RationalValue,
    mine_decision_tree,
    predict_decision_tree,
)
from pix.case_centric.decision_mining import DecisionTable
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseLog, CaseTrace, case_traces


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _strings(value, name):
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    for item in value:
        _text(item, name)
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must be unique")


def _ratio(numerator, denominator):
    if denominator == 0:
        return None
    value = Fraction(numerator, denominator)
    return RationalValue(value.numerator, value.denominator)


def _digest(value):
    content = json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "pix.decision-evaluation.v1:sha256:" + sha256(content).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluationFeature:
    name: str
    kind: Literal["numeric", "categorical"]

    def __post_init__(self):
        _text(self.name, "feature name")
        if self.kind not in ("numeric", "categorical"):
            raise ValueError("feature kind must be numeric or categorical")


@dataclass(frozen=True, slots=True)
class DecisionEvaluationRow:
    row_id: str
    case_id: str
    values: tuple[int | float | str | None, ...]
    target: str | None
    group_ids: tuple[str, ...] = ()
    exclusion_reasons: tuple[str, ...] = ()

    def __post_init__(self):
        _text(self.row_id, "row_id")
        _text(self.case_id, "case_id")
        if self.target is not None:
            _text(self.target, "target")
        _strings(self.group_ids, "group_ids")
        _strings(self.exclusion_reasons, "exclusion_reasons")
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple")
        for value in self.values:
            if value is not None and not (
                type(value) in (int, str) or type(value) is float and isfinite(value)
            ):
                raise ValueError("values must be finite numbers, strings or None")


def _validate_rows(rows, features):
    if not isinstance(rows, tuple) or not all(
        isinstance(row, DecisionEvaluationRow) for row in rows
    ):
        raise TypeError("rows must be a tuple of DecisionEvaluationRow")
    if not isinstance(features, tuple) or not all(
        isinstance(feature, EvaluationFeature) for feature in features
    ):
        raise TypeError("features must be a tuple of EvaluationFeature")
    _strings(tuple(feature.name for feature in features), "feature names")
    _strings(tuple(row.row_id for row in rows), "row IDs")
    for row in rows:
        if len(row.values) != len(features):
            raise ValueError("row dimensions differ from the feature schema")
        for value, feature in zip(row.values, features):
            if value is not None and (
                (feature.kind == "numeric" and type(value) not in (int, float))
                or (feature.kind == "categorical" and type(value) is not str)
            ):
                raise ValueError(f"invalid value type for feature {feature.name}")


@dataclass(frozen=True, slots=True)
class DecisionEncoder:
    features: tuple[EvaluationFeature, ...]
    categories: tuple[tuple[str, ...], ...]
    columns: tuple[str, ...]
    training_row_ids: tuple[str, ...]
    training_case_ids: tuple[str, ...]

    def __post_init__(self):
        _validate_rows((), self.features)
        if not isinstance(self.categories, tuple) or len(self.categories) != len(
            self.features
        ):
            raise ValueError("categories must align with the feature schema")
        for feature, categories in zip(self.features, self.categories):
            if (
                not isinstance(categories, tuple)
                or not all(type(category) is str for category in categories)
                or len(set(categories)) != len(categories)
            ):
                raise ValueError("categories must be unique strings")
            if feature.kind == "numeric" and categories:
                raise ValueError("numeric features cannot contain categories")
        for name in ("columns", "training_row_ids", "training_case_ids"):
            _strings(getattr(self, name), name)
        if self.columns != _columns(self.features, self.categories):
            raise ValueError("encoded columns differ from the fitted schema")


def _columns(features, categories):
    # JSON tuples disambiguate feature/category punctuation without collisions.
    return tuple(
        json.dumps((feature.name, category), ensure_ascii=False)
        for feature, vocabulary in zip(features, categories)
        for category in (vocabulary if feature.kind == "categorical" else (None,))
    )


def fit_decision_encoder(rows, features, training_case_ids) -> DecisionEncoder:
    """Fit only complete, eligible, labelled training rows, before seeing test data."""
    _validate_rows(rows, features)
    _strings(training_case_ids, "training_case_ids")
    selected = set(training_case_ids)
    if not selected.issubset({row.case_id for row in rows}):
        raise ValueError("encoder training selection contains unknown case IDs")
    training = tuple(
        row
        for row in rows
        if row.case_id in selected
        and row.target is not None
        and not row.exclusion_reasons
        and None not in row.values
    )
    categories = tuple(
        tuple(sorted({row.values[index] for row in training}))
        if feature.kind == "categorical"
        else ()
        for index, feature in enumerate(features)
    )
    return DecisionEncoder(
        features,
        categories,
        _columns(features, categories),
        tuple(sorted(row.row_id for row in training)),
        tuple(sorted({row.case_id for row in training})),
    )


@dataclass(frozen=True, slots=True)
class EncodedDecisionRow:
    row_id: str
    case_id: str
    values: tuple[int | float, ...]
    missing_mask: tuple[bool, ...]
    unknown_category_mask: tuple[bool, ...]


def encode_decision_rows(encoder, rows) -> tuple[EncodedDecisionRow, ...]:
    """Transform with a fixed vocabulary; masks are in original feature order."""
    if not isinstance(encoder, DecisionEncoder):
        raise TypeError("encoder must be DecisionEncoder")
    _validate_rows(rows, encoder.features)
    result = []
    for row in rows:
        values, missing, unknown = [], [], []
        for value, feature, categories in zip(
            row.values, encoder.features, encoder.categories
        ):
            missing.append(value is None)
            unknown.append(
                feature.kind == "categorical"
                and value is not None
                and value not in categories
            )
            if feature.kind == "numeric":
                values.append(0 if value is None else value)
            else:
                values.extend(int(value == category) for category in categories)
        result.append(
            EncodedDecisionRow(
                row.row_id, row.case_id, tuple(values), tuple(missing), tuple(unknown)
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class DecisionEvaluationSpec:
    features: tuple[EvaluationFeature, ...]
    training_case_ids: tuple[str, ...]
    test_case_ids: tuple[str, ...]
    max_depth: int = 8
    min_leaf: int = 1
    min_gain: int | float = 0.0
    max_examples: int = 10_000
    max_split_evaluations: int = 1_000_000
    max_rows: int = 100_000
    max_encoded_values: int = 2_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _validate_rows((), self.features)
        for name in ("training_case_ids", "test_case_ids"):
            _strings(getattr(self, name), name)
            object.__setattr__(self, name, tuple(sorted(getattr(self, name))))
        if set(self.training_case_ids) & set(self.test_case_ids):
            raise ValueError("training and test case IDs overlap")
        DecisionTreeSpec(
            (),
            self.max_depth,
            self.min_leaf,
            self.min_gain,
            self.max_examples,
            self.max_split_evaluations,
        )
        for name in ("max_rows", "max_encoded_values"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class DecisionEvaluationRequest:
    rows: tuple[DecisionEvaluationRow, ...]
    parameters: DecisionEvaluationSpec
    evidence_payload_digest: str | None = None
    place_id: str | None = None
    upstream_omitted_row_count: int = 0
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class EvaluatedDecision:
    row_id: str
    case_id: str
    actual: str | None
    prediction: str | None
    reasons: tuple[str, ...]
    missing_mask: tuple[bool, ...]
    unknown_category_mask: tuple[bool, ...]


@dataclass(frozen=True, slots=True)
class DecisionConfusion:
    actual: str
    predicted: str
    count: int


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    encoder: DecisionEncoder
    tree: DecisionTree
    training_case_ids: tuple[str, ...]
    test_case_ids: tuple[str, ...]
    excluded_training_row_ids: tuple[str, ...]
    test_rows: tuple[EvaluatedDecision, ...]
    confusion: tuple[DecisionConfusion, ...]
    scored_row_count: int
    correct_row_count: int
    scored_case_ids: tuple[str, ...]
    fully_scored_case_ids: tuple[str, ...]
    missing_test_case_ids: tuple[str, ...]
    occurrence_accuracy: RationalValue | None
    case_balanced_accuracy: RationalValue | None
    occurrence_coverage: RationalValue | None
    retained_occurrence_coverage: RationalValue | None
    coverage_population_complete: bool
    upstream_omitted_row_count: int
    case_coverage: RationalValue | None
    tree_computation_id: str


def _result(source, request, parents, value=None, issues=(), status=None):
    operator = "pix.case_centric.evaluate_decision_tree"
    return ComputationResult(
        operator,
        "1.0.0",
        source,
        request,
        status
        or (ComputeStatus.COMPUTED if value is not None else ComputeStatus.UNAVAILABLE),
        value,
        issues,
        computation_identity(operator, "1.0.0", source, request, parents),
        parents,
    )


def _evaluate(source, parents, case_ids, request, upstream_issues=()):
    rows, spec = request.rows, request.parameters
    _validate_rows(rows, spec.features)
    training_ids, test_ids = set(spec.training_case_ids), set(spec.test_case_ids)
    if not (training_ids | test_ids | {row.case_id for row in rows}).issubset(case_ids):
        raise ValueError("split or observation contains cases outside the population")
    train_groups = {
        group for row in rows if row.case_id in training_ids for group in row.group_ids
    }
    test_groups = {
        group for row in rows if row.case_id in test_ids for group in row.group_ids
    }
    if train_groups & test_groups:
        raise ValueError("training and test cases share group IDs")
    if len(rows) > spec.max_rows:
        return _result(
            source,
            request,
            parents,
            issues=upstream_issues
            + (
                ComputeIssue(
                    "decision_evaluation_row_limit", "No rows were encoded or fitted"
                ),
            ),
        )
    # IDs missing any observation are kept in coverage, not passed as fit rows.
    encoder = fit_decision_encoder(
        rows,
        spec.features,
        tuple(sorted(training_ids & {row.case_id for row in rows})),
    )
    if len(rows) * len(encoder.columns) > spec.max_encoded_values:
        return _result(
            source,
            request,
            parents,
            issues=upstream_issues
            + (
                ComputeIssue(
                    "decision_encoding_limit",
                    "No encoded matrix was allocated or fitted",
                ),
            ),
        )
    encoded = {row.row_id: row for row in encode_decision_rows(encoder, rows)}
    fitting_ids = set(encoder.training_row_ids)
    training = tuple(row for row in rows if row.row_id in fitting_ids)
    tree_spec = DecisionTreeSpec(
        encoder.columns,
        spec.max_depth,
        spec.min_leaf,
        spec.min_gain,
        spec.max_examples,
        spec.max_split_evaluations,
    )
    fitted = mine_decision_tree(
        CaseLog(tuple(CaseTrace(row.row_id) for row in training)),
        tuple(
            DecisionExample(row.row_id, encoded[row.row_id].values, row.target)
            for row in training
        ),
        tree_spec,
    )
    parents = parents + ((fitted.computation_id,) if fitted.computation_id else ())
    if fitted.value is None:
        return _result(source, request, parents, issues=upstream_issues + fitted.issues)
    observations, predict_rows = [], []
    for row in rows:
        if row.case_id not in test_ids:
            continue
        vector = encoded[row.row_id]
        reasons = list(row.exclusion_reasons)
        if row.target is None:
            reasons.append("unknown_outcome")
        reasons.extend(
            "missing_feature:" + feature.name
            for feature, missing in zip(spec.features, vector.missing_mask)
            if missing
        )
        reasons.extend(
            "unknown_category:" + feature.name
            for feature, unknown in zip(spec.features, vector.unknown_category_mask)
            if unknown
        )
        observations.append((row, vector, tuple(dict.fromkeys(reasons))))
        if not reasons:
            predict_rows.append(CaseVector(row.row_id, vector.values))
    predicted = {
        prediction.case_id: prediction.prediction
        for prediction in predict_decision_tree(fitted.value, tuple(predict_rows))
    }
    tested = tuple(
        EvaluatedDecision(
            row.row_id,
            row.case_id,
            row.target,
            predicted.get(row.row_id),
            reasons,
            vector.missing_mask,
            vector.unknown_category_mask,
        )
        for row, vector, reasons in observations
    )
    scored = tuple(row for row in tested if row.prediction is not None)
    counts = Counter((row.actual, row.prediction) for row in scored)
    case_total = Counter(row.case_id for row in tested)
    case_scored = Counter(row.case_id for row in scored)
    case_correct = Counter(
        row.case_id for row in scored if row.actual == row.prediction
    )
    average = (
        sum(
            (
                Fraction(case_correct[case], count)
                for case, count in case_scored.items()
            ),
            Fraction(),
        )
        / len(case_scored)
        if case_scored
        else None
    )
    missing_cases = tuple(sorted(test_ids - set(case_total)))
    correct = sum(case_correct.values())
    value = DecisionEvaluation(
        encoder,
        fitted.value,
        spec.training_case_ids,
        spec.test_case_ids,
        tuple(
            sorted(
                row.row_id
                for row in rows
                if row.case_id in training_ids and row.row_id not in fitting_ids
            )
        ),
        tested,
        tuple(
            DecisionConfusion(a, p, count) for (a, p), count in sorted(counts.items())
        ),
        len(scored),
        correct,
        tuple(sorted(case_scored)),
        tuple(
            sorted(
                case for case, count in case_total.items() if case_scored[case] == count
            )
        )
        if not request.upstream_omitted_row_count
        else (),
        missing_cases,
        _ratio(correct, len(scored)),
        None
        if average is None
        else RationalValue(average.numerator, average.denominator),
        _ratio(len(scored), len(tested))
        if not request.upstream_omitted_row_count
        else None,
        _ratio(len(scored), len(tested)),
        not bool(request.upstream_omitted_row_count),
        request.upstream_omitted_row_count,
        _ratio(len(case_scored), len(test_ids)),
        fitted.computation_id,
    )
    issues = list(upstream_issues + fitted.issues)
    if len(scored) != len(tested) or missing_cases:
        issues.append(
            ComputeIssue(
                "heldout_coverage",
                "Some held-out cases or decision rows were not scored",
            )
        )
    if value.excluded_training_row_ids or not training_ids.issubset(
        encoder.training_case_ids
    ):
        issues.append(
            ComputeIssue(
                "training_coverage",
                "Some selected training cases or rows were not fitted",
            )
        )
    if not test_ids:
        issues.append(
            ComputeIssue("empty_test_population", "No held-out cases were selected")
        )
    if request.upstream_omitted_row_count:
        issues.append(
            ComputeIssue(
                "decision_population_unknown",
                "Upstream omitted rows have no case/place allocation; full occurrence coverage and case completeness are unknown",
            )
        )
    return _result(
        source,
        request,
        parents,
        value,
        tuple(issues),
        ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
    )


def evaluate_decision_tree(
    log: CaseLog, rows: tuple[DecisionEvaluationRow, ...], spec: DecisionEvaluationSpec
) -> ComputationResult[DecisionEvaluation]:
    """Fit CART on training cases; evaluate held-out decision occurrences.

    Split IDs are explicit, with no random or chronological split implied. All
    occurrences of each case remain together. Shared caller-declared groups
    (for example an OC object or process execution) across the two sets reject
    the split, including groups attached to excluded observations. Occurrence
    accuracy weights decisions equally; case-balanced accuracy averages each
    scored case's accuracy. An unseen *observed* target is scored as an error;
    an unavailable target (None) is excluded. No causal claim is made.
    """
    if not isinstance(log, CaseLog) or not isinstance(spec, DecisionEvaluationSpec):
        raise TypeError("expected CaseLog and DecisionEvaluationSpec")
    _validate_rows(rows, spec.features)
    rows = tuple(sorted(rows, key=lambda row: row.row_id))
    traces = case_traces(log)
    request = DecisionEvaluationRequest(rows, spec)
    parents = (traces.computation_id,) if traces.computation_id else ()
    if traces.status is not ComputeStatus.COMPUTED:
        return _result(traces.source_digest, request, parents, issues=traces.issues)
    return _evaluate(
        traces.source_digest,
        parents,
        {trace.object_id for trace in traces.value.traces},
        request,
    )


def decision_rows_from_table(table: DecisionTable, place_id: str):
    """Retain numeric upstream features, original case IDs and exclusion reasons."""
    if not isinstance(table, DecisionTable):
        raise TypeError("table must be DecisionTable")
    if place_id not in {point.place_id for point in table.decision_points}:
        raise ValueError("unknown decision place")
    return tuple(
        DecisionEvaluationRow(
            row.row_id,
            row.case_id,
            tuple(feature.value for feature in row.features),
            row.transition_id,
            exclusion_reasons=row.reasons,
        )
        for row in table.observations
        if row.place_id == place_id
    )


def evaluate_decision_table(
    table: ComputationResult[DecisionTable], place_id: str, spec: DecisionEvaluationSpec
) -> ComputationResult[DecisionEvaluation]:
    """Evaluate one structural choice place while preserving witness provenance.

    With truncated upstream observations, retained-row scores remain available.
    Full occurrence coverage and fully scored cases cannot be established: the
    table's omission count does not identify the affected cases or choice places.
    """
    if not isinstance(table, ComputationResult) or not isinstance(
        spec, DecisionEvaluationSpec
    ):
        raise TypeError("expected a decision-table result and DecisionEvaluationSpec")
    _text(place_id, "place_id")
    if table.operator_id != "pix.case_centric.extract_decision_table":
        raise ValueError("unexpected decision-table operator")
    if table.computation_id != computation_identity(
        table.operator_id,
        table.operator_version,
        table.source_digest,
        table.spec,
        table.parent_computation_ids,
    ):
        raise ValueError("decision-table computation identity is inconsistent")
    parents = (table.computation_id,) if table.computation_id else ()
    if table.value is None:
        return _result(
            table.source_digest,
            DecisionEvaluationRequest((), spec, place_id=place_id),
            parents,
            issues=table.issues,
        )
    rows = decision_rows_from_table(table.value, place_id)
    expected = tuple(
        EvaluationFeature(feature.name, "numeric") for feature in table.value.features
    )
    if spec.features != expected:
        raise ValueError(
            "evaluation feature schema differs from numeric decision table"
        )
    request = DecisionEvaluationRequest(
        tuple(sorted(rows, key=lambda row: row.row_id)),
        spec,
        _digest(asdict(table.value)),
        place_id,
        table.value.omitted_row_count,
    )
    return _evaluate(
        table.source_digest, parents, set(table.value.case_ids), request, table.issues
    )


RESULT_SCHEMAS = {
    "pix.case_centric.evaluate_decision_tree": (
        "case_decision_evaluation",
        DecisionEvaluationRequest,
        DecisionEvaluation,
    ),
}

__all__ = (
    "EvaluationFeature",
    "DecisionEvaluationRow",
    "DecisionEncoder",
    "EncodedDecisionRow",
    "DecisionEvaluationSpec",
    "DecisionEvaluationRequest",
    "EvaluatedDecision",
    "DecisionConfusion",
    "DecisionEvaluation",
    "fit_decision_encoder",
    "encode_decision_rows",
    "evaluate_decision_tree",
    "decision_rows_from_table",
    "evaluate_decision_table",
)
