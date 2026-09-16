"""Compose native case-centric quality metrics without inventing missing scores.

Every log-based metric receives the same identified TraceSet. Only its score
for that whole source population is eligible: completed subsets from different
calculations are never silently mixed. Metric weights express a caller's
preference, not a validated objective measure of model quality.

Unlike the pinned reference aggregate, weights and missing-value policy are
validated, individual specs are retained, and each child result keeps its own
identity, population and issues. No upstream implementation is executed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from math import fsum
from typing import ClassVar

from pix.case_centric._input import CaseInput, as_case_traces
from pix.case_centric.conformance import (
    AlignmentFitnessSpec,
    ETPrecisionSpec,
    GeneralizationSpec,
    TokenFitnessSpec,
    measure_alignment_fitness,
    measure_et_precision,
    measure_token_fitness,
    measure_token_generalization,
)
from pix.case_centric.model_analysis import ComplexitySpec, model_complexity
from pix.compute._common import _result
from pix.compute.model_semantics import model_digest
from pix.contracts.analysis import TraceSet
from pix.contracts.models import PetriNet
from pix.contracts.result import ComputationResult, ComputeIssue, ComputeStatus

Ratio = tuple[int, int]
_METRICS = ("fitness", "precision", "generalization", "simplicity")


@dataclass(frozen=True, slots=True)
class EvaluationSpec:
    """Select profiles and exact nonnegative weights; zero disables a metric.

    ``require_all`` withholds the weighted score if any enabled metric is
    undefined. ``renormalize_defined`` averages only defined enabled metrics,
    labels that narrower scope, and retains missing metrics as issues.
    Simplicity is a model statistic; its population is the whole model.
    """

    fitness_method: str = "token"
    fitness_aggregation: str = "pooled"
    token_fitness: TokenFitnessSpec = TokenFitnessSpec()
    alignment_fitness: AlignmentFitnessSpec = AlignmentFitnessSpec()
    precision: ETPrecisionSpec = ETPrecisionSpec(method="token")
    generalization: GeneralizationSpec = GeneralizationSpec()
    simplicity: ComplexitySpec = ComplexitySpec()
    weights: tuple[tuple[str, Ratio], ...] = tuple((name, (1, 1)) for name in _METRICS)
    missing_metric_policy: str = "require_all"
    population_policy: str = "whole_source"
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.evaluation.spec"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.fitness_method not in ("token", "alignment"):
            raise ValueError("fitness_method must be token or alignment")
        if self.fitness_aggregation not in ("pooled", "case_mean"):
            raise ValueError("fitness_aggregation must be pooled or case_mean")
        for name, kind in (
            ("token_fitness", TokenFitnessSpec),
            ("alignment_fitness", AlignmentFitnessSpec),
            ("precision", ETPrecisionSpec),
            ("generalization", GeneralizationSpec),
            ("simplicity", ComplexitySpec),
        ):
            if not isinstance(getattr(self, name), kind):
                raise TypeError(f"{name} must be {kind.__name__}")
        if self.missing_metric_policy not in ("require_all", "renormalize_defined"):
            raise ValueError(
                "missing_metric_policy must be require_all or renormalize_defined"
            )
        if self.population_policy != "whole_source":
            raise ValueError("only whole_source population is supported")
        if not isinstance(self.weights, tuple):
            raise TypeError("weights must be a tuple of metric/rational pairs")
        weights = {}
        for row in self.weights:
            if not isinstance(row, tuple) or len(row) != 2:
                raise TypeError("weight row must be (metric, rational)")
            name, ratio = row
            if name not in _METRICS or name in weights:
                raise ValueError("weight metric must be known and unique")
            if (
                not isinstance(ratio, tuple)
                or len(ratio) != 2
                or not all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in ratio
                )
            ):
                raise TypeError("weight must be an integer numerator/denominator pair")
            if ratio[0] < 0 or ratio[1] <= 0:
                raise ValueError(
                    "weight requires nonnegative numerator and positive denominator"
                )
            weights[name] = Fraction(*ratio)
        if set(weights) != set(_METRICS):
            raise ValueError("weights must name all four metrics; use zero to disable")
        if not any(weights.values()):
            raise ValueError("at least one metric must have positive weight")
        object.__setattr__(
            self,
            "weights",
            tuple(
                (name, (weights[name].numerator, weights[name].denominator))
                for name in _METRICS
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluationRequest:
    model_digest: str
    parameters: EvaluationSpec
    SPEC_TYPE: ClassVar[str] = "pix.case_centric.evaluation.request"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class QualityMetric:
    name: str
    state: str
    profile: str
    score: float | None
    exact_ratio: Ratio | None
    requested_weight: Ratio
    effective_weight: Ratio
    population: str
    requested_case_count: int | None
    completed_case_count: int | None
    observation_unit: str
    observation_counts: tuple[tuple[str, int], ...]
    operator_id: str | None
    operator_version: str | None
    source_digest: str | None
    computation_id: str | None
    parent_computation_ids: tuple[str, ...]
    result_status: ComputeStatus | None
    issues: tuple[ComputeIssue, ...]


@dataclass(frozen=True, slots=True)
class ModelEvaluation:
    model_digest: str
    trace_computation_id: str
    case_ids: tuple[str, ...]
    population_policy: str
    metrics: tuple[QualityMetric, ...]
    weighted_score: float | None
    weighted_score_ratio: Ratio | None
    weighted_score_scope: str
    fitness_precision_fscore: Ratio | None
    included_metrics: tuple[str, ...]
    undefined_metrics: tuple[str, ...]
    disabled_metrics: tuple[str, ...]
    included_weight: Ratio
    requested_weight: Ratio


def _pair(value: Fraction) -> Ratio:
    return value.numerator, value.denominator


def _row(name, child, score, profile, weight, requested, completed, unit, counts):
    ratio = score if isinstance(score, tuple) else None
    number = float(Fraction(*score)) if ratio is not None else score
    return QualityMetric(
        name,
        "defined" if score is not None else "undefined",
        profile,
        number,
        ratio,
        weight,
        (0, 1),
        "whole_model" if name == "simplicity" else "whole_source",
        requested,
        completed,
        unit,
        counts,
        child.operator_id,
        child.operator_version,
        child.source_digest,
        child.computation_id,
        child.parent_computation_ids,
        child.status,
        child.issues,
    )


def evaluate_model(
    log: CaseInput, net: PetriNet, spec: EvaluationSpec = EvaluationSpec()
) -> ComputationResult[ModelEvaluation]:
    """Compute explicitly profiled quality metrics and their declared aggregate.

    Fitness/precision F-score is defined only when both metrics are enabled and
    defined; their simultaneous zero scores produce zero. It is independent of
    the four-way weighted score. Unknown metrics never become numeric zero.
    """
    if not isinstance(net, PetriNet):
        raise TypeError("net must be PetriNet")
    if not isinstance(spec, EvaluationSpec):
        raise TypeError("spec must be EvaluationSpec")
    source = as_case_traces(log)
    request = EvaluationRequest(model_digest(net), spec)
    parents = (source.computation_id,) if source.computation_id is not None else ()
    if source.status is not ComputeStatus.COMPUTED or not isinstance(
        source.value, TraceSet
    ):
        return _result(
            "pix.case_centric.evaluate_model",
            None,
            request,
            ComputeStatus.INVALID_INPUT
            if source.status is ComputeStatus.INVALID_INPUT
            else ComputeStatus.UNAVAILABLE,
            None,
            source.issues
            + (
                ComputeIssue(
                    "trace_result_unavailable",
                    "Completed common source traces are required.",
                ),
            ),
            source_digest=source.source_digest,
            parent_computation_ids=parents,
        )
    rows = []
    weights = dict(spec.weights)
    for name in _METRICS:
        weight = weights[name]
        if weight[0] == 0:
            rows.append(
                QualityMetric(
                    name,
                    "disabled",
                    "disabled",
                    None,
                    None,
                    weight,
                    (0, 1),
                    "not_evaluated",
                    None,
                    None,
                    "not_evaluated",
                    (),
                    None,
                    None,
                    None,
                    None,
                    (),
                    None,
                    (),
                )
            )
            continue
        if name == "fitness":
            child = (
                measure_token_fitness(source, net, spec.token_fitness)
                if spec.fitness_method == "token"
                else measure_alignment_fitness(source, net, spec.alignment_fitness)
            )
            value = child.value
            score = (
                value.whole_log_fitness_ratio
                if spec.fitness_aggregation == "pooled"
                else value.whole_mean_trace_fitness_ratio
            )
            row = _row(
                name,
                child,
                score,
                value.profile + ":" + spec.fitness_aggregation,
                weight,
                value.requested_count,
                value.completed_count
                if spec.fitness_method == "token"
                else value.defined_count,
                "pooled_token_balances"
                if spec.fitness_aggregation == "pooled"
                and spec.fitness_method == "token"
                else "pooled_alignment_normalizers"
                if spec.fitness_aggregation == "pooled"
                else "cases",
                (("defined_cases", value.defined_count),),
            )
        elif name == "precision":
            child = measure_et_precision(source, net, spec.precision)
            value = child.value
            row = _row(
                name,
                child,
                value.whole_population_ratio,
                value.profile + ":" + value.method,
                weight,
                value.requested_case_count,
                None,
                "occurrence_weighted_prefix_enabled_labels",
                (
                    ("computed_prefixes", value.computed_prefix_count),
                    ("unfit_prefixes", value.unfit_prefix_count),
                    ("limited_prefixes", value.limited_prefix_count),
                    ("computed_prefix_weight", value.computed_weight),
                    ("weighted_enabled", value.weighted_enabled),
                    ("weighted_escaping", value.weighted_escaping),
                ),
            )
        elif name == "generalization":
            child = measure_token_generalization(source, net, spec.generalization)
            value = child.value
            row = _row(
                name,
                child,
                value.whole_population_score,
                value.profile,
                weight,
                value.requested_case_count,
                value.completed_case_count,
                "all_model_transition_ids_from_completed_replay_frequencies",
                (
                    ("model_transitions", len(value.transitions)),
                    ("limited_cases", value.limited_case_count),
                ),
            )
        else:
            child = model_complexity(net, spec.simplicity)
            value = child.value
            # This selected structural score needs no reachability proof.
            # Any issue from other complexity diagnostics remains attached.
            row = _row(
                name,
                child,
                value.arc_degree_simplicity,
                "arc_degree_incidence_count_baseline_k",
                weight,
                None,
                None,
                "whole_model_nodes_and_arcs",
                (
                    ("places", value.place_count),
                    ("transitions", value.transition_count),
                    ("arcs", value.arc_count),
                ),
            )
        expected_source = (
            request.model_digest if name == "simplicity" else source.source_digest
        )
        if child.source_digest != expected_source:
            raise ValueError("metric source identity differs from the shared input")
        parents += (child.computation_id,)
        rows.append(row)
    defined = tuple(row.name for row in rows if row.state == "defined")
    undefined = tuple(row.name for row in rows if row.state == "undefined")
    disabled = tuple(row.name for row in rows if row.state == "disabled")
    included_total = sum((Fraction(*weights[name]) for name in defined), Fraction())
    requested_total = sum((Fraction(*ratio) for _, ratio in spec.weights), Fraction())
    aggregate_defined = bool(defined) and (
        not undefined or spec.missing_metric_policy == "renormalize_defined"
    )
    included = defined if aggregate_defined else ()
    if aggregate_defined:
        rows = [
            replace(
                row,
                effective_weight=_pair(
                    Fraction(*row.requested_weight) / included_total
                ),
            )
            if row.state == "defined"
            else row
            for row in rows
        ]
        average = fsum(
            row.score * float(Fraction(*row.effective_weight))
            for row in rows
            if row.state == "defined"
        )
        exact = (
            sum(
                (
                    Fraction(*row.exact_ratio) * Fraction(*row.effective_weight)
                    for row in rows
                    if row.state == "defined"
                ),
                Fraction(),
            )
            if all(
                row.exact_ratio is not None for row in rows if row.state == "defined"
            )
            else None
        )
        scope = "all_enabled_metrics" if not undefined else "defined_metrics_only"
    else:
        average, exact, scope = None, None, "undefined"
    scores = {row.name: row.exact_ratio for row in rows if row.state == "defined"}
    harmonic = None
    if scores.get("fitness") is not None and scores.get("precision") is not None:
        fitness, precision = (
            Fraction(*scores["fitness"]),
            Fraction(*scores["precision"]),
        )
        harmonic = _pair(
            2 * fitness * precision / (fitness + precision)
            if fitness + precision
            else Fraction()
        )
    issues = source.issues + tuple(
        ComputeIssue(issue.code, issue.message, (row.name,) + issue.at)
        for row in rows
        for issue in row.issues
    )
    issues += tuple(
        ComputeIssue(
            "undefined_quality_metric", "No whole-source score is defined.", (name,)
        )
        for name in undefined
    )
    partial = bool(undefined) or any(
        row.result_status is ComputeStatus.PARTIAL for row in rows
    )
    if partial and not issues:
        issues = (
            ComputeIssue(
                "partial_quality_evidence", "A child calculation is incomplete."
            ),
        )
    value = ModelEvaluation(
        request.model_digest,
        source.computation_id,
        tuple(trace.object_id for trace in source.value.traces),
        spec.population_policy,
        tuple(rows),
        average,
        None if exact is None else _pair(exact),
        scope,
        harmonic,
        included,
        undefined,
        disabled,
        _pair(included_total if aggregate_defined else Fraction()),
        _pair(requested_total),
    )
    return _result(
        "pix.case_centric.evaluate_model",
        None,
        request,
        ComputeStatus.PARTIAL if partial else ComputeStatus.COMPUTED,
        value,
        issues,
        source_digest=source.source_digest,
        parent_computation_ids=tuple(dict.fromkeys(parents)),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.evaluate_model": (
        "case-model-evaluation",
        EvaluationRequest,
        ModelEvaluation,
    ),
}

__all__ = (
    "EvaluationSpec",
    "EvaluationRequest",
    "QualityMetric",
    "ModelEvaluation",
    "evaluate_model",
)
