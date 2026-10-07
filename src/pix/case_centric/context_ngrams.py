"""Contextual activity n-grams backed by the existing native feature encoder.

Documents are explicit CaseLog traces in recorded order. OCEL callers must first
choose an object/execution projection and its linearization. Tokens use typed
JSON tuples, never separator concatenation. All occurrence counts are exact;
only returned occurrence evidence may be capped, with explicit diagnostics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

from pix.case_centric.features import (
    FeatureMatrix,
    FeatureModel,
    FeatureSpec,
    _category,
    fit_features,
    transform_features,
)
from pix.compute._common import _result
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_log_digest
from pix.event_log.adapters import _activity


@dataclass(frozen=True, slots=True)
class ContextNGramSpec:
    encoding: str = "count"
    ngram_min: int = 1
    ngram_max: int = 3
    token_attributes: tuple[str, ...] = ()
    missing: str = "reject"
    normalize_l2: bool = False
    min_document_frequency: int = 1
    trace_spec: CaseTraceSpec = CaseTraceSpec()
    max_occurrences: int = 1_000_000
    max_vocabulary: int = 100_000
    max_matrix_cells: int = 5_000_000
    max_evidence: int = 10_000

    def __post_init__(self):
        self.feature_spec()
        if not isinstance(self.trace_spec, CaseTraceSpec):
            raise TypeError("trace_spec must be CaseTraceSpec")
        if (
            not isinstance(self.token_attributes, tuple)
            or any(not isinstance(x, str) or not x for x in self.token_attributes)
            or len(set(self.token_attributes)) != len(self.token_attributes)
        ):
            raise ValueError("token_attributes must be unique nonempty strings")
        if self.missing not in ("reject", "tag"):
            raise ValueError("missing must be reject or tag")
        for name in (
            "max_occurrences",
            "max_vocabulary",
            "max_matrix_cells",
            "max_evidence",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "max_evidence" else 1):
                raise ValueError(f"invalid {name}")

    def feature_spec(self):
        return FeatureSpec(
            encoding=self.encoding,
            ngram_min=self.ngram_min,
            ngram_max=self.ngram_max,
            min_document_frequency=self.min_document_frequency,
            normalize_activity_l2=self.normalize_l2,
        )


@dataclass(frozen=True, slots=True)
class ContextNGramFitRequest:
    parameters: ContextNGramSpec
    training_case_ids: tuple[str, ...] | None = None

    def __post_init__(self):
        if not isinstance(self.parameters, ContextNGramSpec):
            raise TypeError("parameters must be ContextNGramSpec")
        ids = self.training_case_ids
        if ids is not None:
            if (
                not isinstance(ids, tuple)
                or any(not isinstance(x, str) or not x for x in ids)
                or len(set(ids)) != len(ids)
            ):
                raise ValueError("training_case_ids must be unique strings")
            object.__setattr__(self, "training_case_ids", tuple(sorted(ids)))


@dataclass(frozen=True, slots=True)
class ContextNGramModel:
    parameters: ContextNGramSpec
    feature_model: FeatureModel
    training_source_digest: str

    def __post_init__(self):
        if not isinstance(self.parameters, ContextNGramSpec) or not isinstance(
            self.feature_model, FeatureModel
        ):
            raise TypeError("invalid contextual model")
        if self.feature_model.parameters != self.parameters.feature_spec():
            raise ValueError("feature model disagrees with contextual parameters")
        if (
            not isinstance(self.training_source_digest, str)
            or not self.training_source_digest
        ):
            raise ValueError("training source digest required")


@dataclass(frozen=True, slots=True)
class ContextNGramRequest:
    fitted_model: ContextNGramModel

    def __post_init__(self):
        if not isinstance(self.fitted_model, ContextNGramModel):
            raise TypeError("fitted_model must be ContextNGramModel")


@dataclass(frozen=True, slots=True)
class NGramOccurrence:
    case_id: str
    terms: tuple[str, ...]
    event_ids: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("case identity required")
        for value in (self.terms, self.event_ids):
            if (
                not isinstance(value, tuple)
                or not value
                or any(not isinstance(x, str) or not x for x in value)
            ):
                raise ValueError("nonempty terms and event IDs required")
        if len(self.terms) != len(self.event_ids):
            raise ValueError("one event ID per term required")


@dataclass(frozen=True, slots=True)
class ContextNGramMatrix:
    matrix: FeatureMatrix
    occurrences: tuple[NGramOccurrence, ...]
    occurrence_count: int
    omitted_evidence_count: int

    def __post_init__(self):
        if not isinstance(self.matrix, FeatureMatrix):
            raise TypeError("matrix must be FeatureMatrix")
        if not isinstance(self.occurrences, tuple) or not all(
            isinstance(x, NGramOccurrence) for x in self.occurrences
        ):
            raise TypeError("occurrences must contain NGramOccurrence")
        if any(
            type(x) is not int or x < 0
            for x in (self.occurrence_count, self.omitted_evidence_count)
        ):
            raise ValueError("invalid occurrence counts")
        if len(self.occurrences) + self.omitted_evidence_count != self.occurrence_count:
            raise ValueError("evidence coverage disagrees with occurrence count")
        if not {o.case_id for o in self.occurrences} <= {
            r.case_id for r in self.matrix.rows
        }:
            raise ValueError("unknown evidence case")


class _Limit(ValueError):
    pass


def _windows(trace, spec):
    for n in range(spec.ngram_min, min(spec.ngram_max, len(trace.events)) + 1):
        for start in range(len(trace.events) - n + 1):
            yield trace.events[start : start + n]


def _project(log, spec):
    traces, vocabulary, occurrence_count = [], set(), 0
    for trace in log.traces:
        events = []
        for event in trace.events:
            activity = _activity(log, event, spec.trace_spec)
            parts = []
            for key in spec.token_attributes:
                attribute = log.attribute(event, key)
                encoded = _category(attribute)
                if encoded is None and spec.missing == "reject":
                    raise ValueError(
                        f"event {event.id!r} lacks token attribute {key!r}"
                    )
                parts.append(
                    (key, json.loads(encoded) if encoded is not None else ["missing"])
                )
            token = (
                activity
                if not parts
                else json.dumps(
                    [activity, parts],
                    ensure_ascii=False,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            events.append(
                CaseEvent(event.id, (CaseAttribute("concept:name", "string", token),))
            )
        projected = CaseTrace(trace.id, tuple(events))
        for window in _windows(projected, spec):
            occurrence_count += 1
            if occurrence_count > spec.max_occurrences:
                raise _Limit("ngram occurrence limit exceeded")
            vocabulary.add(tuple(e.activity for e in window))
            if len(vocabulary) > spec.max_vocabulary:
                raise _Limit("ngram vocabulary limit exceeded")
        traces.append(projected)
    return CaseLog(tuple(traces))


def _out(operator, log, request, value=None, issues=(), status=ComputeStatus.COMPUTED):
    return _result(
        operator,
        None,
        request,
        status,
        value,
        tuple(issues),
        source_digest=case_log_digest(log),
    )


def fit_context_ngrams(
    log: CaseLog, spec: ContextNGramSpec = ContextNGramSpec(), *, training_case_ids=None
) -> ComputationResult[ContextNGramModel]:
    request = ContextNGramFitRequest(spec, training_case_ids)
    operator = "pix.case_centric.fit_context_ngrams"
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    try:
        selected = (
            set(request.training_case_ids)
            if request.training_case_ids is not None
            else {t.id for t in log.traces}
        )
        if selected - {t.id for t in log.traces}:
            raise ValueError("unknown training case ID")
        training = replace(log, traces=tuple(t for t in log.traces if t.id in selected))
        projected = _project(training, spec)
        fitted = fit_features(projected, spec.feature_spec())
        if fitted.value is None:
            return _out(
                operator, log, request, issues=fitted.issues, status=fitted.status
            )
        if len(fitted.value.columns) * len(training.traces) > spec.max_matrix_cells:
            raise _Limit("ngram matrix cell limit exceeded")
        return _out(
            operator,
            log,
            request,
            ContextNGramModel(spec, fitted.value, case_log_digest(training)),
        )
    except ValueError as error:
        return _out(
            operator,
            log,
            request,
            issues=(
                ComputeIssue(
                    "ngram_limit"
                    if isinstance(error, _Limit)
                    else "invalid_ngram_input",
                    str(error),
                ),
            ),
            status=ComputeStatus.UNAVAILABLE
            if isinstance(error, _Limit)
            else ComputeStatus.INVALID_INPUT,
        )


def transform_context_ngrams(
    log: CaseLog, fitted_model: ContextNGramModel
) -> ComputationResult[ContextNGramMatrix]:
    request = ContextNGramRequest(fitted_model)
    operator = "pix.case_centric.transform_context_ngrams"
    if not isinstance(log, CaseLog):
        raise TypeError("log must be CaseLog")
    spec = fitted_model.parameters
    try:
        if (
            len(log.traces) * len(fitted_model.feature_model.columns)
            > spec.max_matrix_cells
        ):
            raise _Limit("ngram matrix cell limit exceeded")
        projected = _project(log, spec)
        matrix = transform_features(projected, fitted_model.feature_model)
        if matrix.value is None:
            return _out(
                operator, log, request, issues=matrix.issues, status=matrix.status
            )
        evidence, total = [], 0
        for trace in projected.traces:
            for window in _windows(trace, spec):
                total += 1
                if len(evidence) < spec.max_evidence:
                    evidence.append(
                        NGramOccurrence(
                            trace.id,
                            tuple(e.activity for e in window),
                            tuple(e.id for e in window),
                        )
                    )
        omitted = total - len(evidence)
        issues = matrix.issues + (
            (
                ComputeIssue(
                    "evidence_truncated",
                    f"{omitted} occurrence witnesses omitted; feature counts are not truncated",
                ),
            )
            if omitted
            else ()
        )
        value = ContextNGramMatrix(matrix.value, tuple(evidence), total, omitted)
        return _out(
            operator,
            log,
            request,
            value,
            issues,
            ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED,
        )
    except ValueError as error:
        return _out(
            operator,
            log,
            request,
            issues=(
                ComputeIssue(
                    "ngram_limit"
                    if isinstance(error, _Limit)
                    else "invalid_ngram_input",
                    str(error),
                ),
            ),
            status=ComputeStatus.UNAVAILABLE
            if isinstance(error, _Limit)
            else ComputeStatus.INVALID_INPUT,
        )


RESULT_SCHEMAS = {
    "pix.case_centric.fit_context_ngrams": (
        "case-context-ngram-model",
        ContextNGramFitRequest,
        ContextNGramModel,
    ),
    "pix.case_centric.transform_context_ngrams": (
        "case-context-ngram-matrix",
        ContextNGramRequest,
        ContextNGramMatrix,
    ),
}

__all__ = [
    "ContextNGramSpec",
    "ContextNGramFitRequest",
    "ContextNGramModel",
    "ContextNGramRequest",
    "NGramOccurrence",
    "ContextNGramMatrix",
    "fit_context_ngrams",
    "transform_context_ngrams",
]
