"""Contextual activity splitting with reproducible training and application.

The native profile implements edit-distance graphs and weighted greedy
modularity, not connected-component clustering. All original event facts stay
in their original attributes; a separately materialized attribute carries the
derived classification. Upstream packages are neither imported nor executed.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, replace
from fractions import Fraction
from math import isfinite
from typing import ClassVar

from pix.compute._common import _result
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    _identity_value,
)
from pix.event_log import CaseAttribute, CaseClassifier, CaseLog, case_log_digest

Activity = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextualLabelSplittingSpec:
    activity_keys: tuple[str, ...] = ("concept:name",)
    classifier: str | None = None
    prefix_length: int = 2
    suffix_length: int = 2
    min_similarity: float = 0.0
    distance: str = "concatenated"
    target_activities: tuple[Activity, ...] = ()
    output_key: str = "pix:contextual:activity"
    max_contexts: int = 512
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.activity_keys, tuple) or not self.activity_keys:
            raise TypeError("activity_keys must be a nonempty tuple")
        for key in (*self.activity_keys, self.output_key):
            if not isinstance(key, str) or not key.strip():
                raise ValueError("attribute keys must be nonblank strings")
        if len(set(self.activity_keys)) != len(self.activity_keys):
            raise ValueError("activity_keys must be unique")
        if self.classifier is not None and (
            not isinstance(self.classifier, str) or not self.classifier.strip()
        ):
            raise ValueError("classifier must be nonblank text or None")
        for name in ("prefix_length", "suffix_length", "max_contexts"):
            value = getattr(self, name)
            if type(value) is not int or value < (1 if name == "max_contexts" else 0):
                raise ValueError(f"{name} must be an integer in its valid range")
        if (
            type(self.min_similarity) not in (int, float)
            or not isfinite(self.min_similarity)
            or not 0 <= self.min_similarity <= 1
        ):
            raise ValueError("min_similarity must be finite and in [0, 1]")
        if self.distance not in ("concatenated", "sided"):
            raise ValueError("distance must be concatenated or sided")
        if not isinstance(self.target_activities, tuple) or any(
            not isinstance(activity, tuple)
            or not activity
            or any(not isinstance(part, str) or not part.strip() for part in activity)
            for activity in self.target_activities
        ):
            raise TypeError("target_activities must contain nonempty string tuples")
        if len(set(self.target_activities)) != len(self.target_activities):
            raise ValueError("target_activities must be unique")


@dataclass(frozen=True, slots=True)
class LabelSplittingApplySpec:
    unseen_context: str = "retain"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if self.unseen_context not in ("retain", "error"):
            raise ValueError("unseen_context must be retain or error")


@dataclass(frozen=True, slots=True)
class LabelSplittingApplyRequest:
    application: LabelSplittingApplySpec
    training: ContextualLabelSplittingSpec
    training_source_digest: str
    training_computation_id: str
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ContextWindow:
    prefix: tuple[Activity, ...]
    suffix: tuple[Activity, ...]


@dataclass(frozen=True, slots=True)
class LabelContext:
    id: int
    activity: Activity
    prefix: tuple[Activity, ...]
    suffix: tuple[Activity, ...]
    event_ids: tuple[str, ...]
    windows: tuple[ContextWindow, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextSimilarity:
    left: int
    right: int
    numerator: int
    denominator: int


@dataclass(frozen=True, slots=True)
class LabelCluster:
    id: int
    activity: Activity
    context_ids: tuple[int, ...]
    event_count: int
    derived_label: str


@dataclass(frozen=True, slots=True)
class LabelLineage:
    case_id: str
    event_id: str
    event_index: int
    original: Activity | None
    prefix: tuple[Activity, ...]
    suffix: tuple[Activity, ...]
    context_id: int | None
    cluster_id: int | None
    derived_label: str | None
    disposition: str


@dataclass(frozen=True, slots=True)
class LabelSplittingModel:
    classifier_keys: tuple[str, ...]
    contexts: tuple[LabelContext, ...]
    edges: tuple[ContextSimilarity, ...]
    clusters: tuple[LabelCluster, ...]
    lineage: tuple[LabelLineage, ...]
    event_count: int
    eligible_count: int
    excluded_count: int


@dataclass(frozen=True, slots=True)
class AppliedLabelSplitting:
    classifier_keys: tuple[str, ...]
    output_key: str
    lineage: tuple[LabelLineage, ...]
    event_count: int
    known_count: int
    unseen_count: int
    excluded_count: int


def _label(activity: Activity, cluster: int | None) -> str:
    # A tagged tuple is injective across scalar/composite and unknown labels.
    # Even an input activity that LOOKS like this JSON is encoded as data.
    return json.dumps(
        ["pix.contextual.v1", list(activity), cluster],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _edit(left: tuple[Activity, ...], right: tuple[Activity, ...]) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b))
            )
        previous = current
    return previous[-1]


def _similarity(left: LabelContext, right: LabelContext, distance: str) -> Fraction:
    if distance == "concatenated":
        a, b = left.prefix + left.suffix, right.prefix + right.suffix
        length, edits = max(len(a), len(b)), _edit(a, b)
    else:
        length = max(len(left.prefix), len(right.prefix)) + max(
            len(left.suffix), len(right.suffix)
        )
        edits = _edit(left.prefix, right.prefix) + _edit(left.suffix, right.suffix)
    return Fraction(length - edits, length) if length else Fraction(1)


def _communities(
    contexts: tuple[LabelContext, ...], edges: tuple[ContextSimilarity, ...]
):
    """Global weighted greedy modularity, deterministic lexicographic ties.

    Delta Q = w(A,B)/m - degree(A)*degree(B)/(2*m*m). Degrees are
    ORIGINAL graph weighted degrees. Only adjacent communities may merge;
    zero-gain merges are accepted, negative gains stop. Isolates stay singleton.
    Fractions remove floating-point threshold and tie ambiguity.
    """
    communities = {context.id: (context.id,) for context in contexts}
    weights = {
        (edge.left, edge.right): Fraction(edge.numerator, edge.denominator)
        for edge in edges
    }
    degrees = {context.id: Fraction(0) for context in contexts}
    mass = sum(weights.values(), Fraction(0))
    if not mass:
        return tuple(communities.values())
    for (left, right), weight in weights.items():
        degrees[left] += weight
        degrees[right] += weight
    while weights:
        candidates = (
            (weight / mass - degrees[a] * degrees[b] / (2 * mass * mass), a, b)
            for (a, b), weight in weights.items()
        )
        gain, left, right = min(
            candidates,
            key=lambda row: (-row[0], communities[row[1]], communities[row[2]]),
        )
        if gain < 0:
            break
        communities[left] = tuple(sorted(communities[left] + communities.pop(right)))
        degrees[left] += degrees.pop(right)
        del weights[(left, right)]
        for other in tuple(communities):
            if other == left:
                continue
            old = tuple(sorted((right, other)))
            new = tuple(sorted((left, other)))
            if old in weights:
                weights[new] = weights.get(new, Fraction(0)) + weights.pop(old)
    return tuple(sorted(communities.values()))


def _keys(log: CaseLog, spec: ContextualLabelSplittingSpec) -> tuple[str, ...]:
    if spec.classifier is None:
        keys = spec.activity_keys
    else:
        classifiers = tuple(
            c
            for c in log.classifiers
            if c.name == spec.classifier and c.scope == "event"
        )
        if len(classifiers) != 1:
            raise ValueError("classifier must identify exactly one event classifier")
        keys = classifiers[0].keys
        if len(set(keys)) != len(keys):
            raise ValueError("classifier keys must be unique")
    if spec.output_key in keys:
        raise ValueError("output_key must differ from every source classification key")
    if any(len(activity) != len(keys) for activity in spec.target_activities):
        raise ValueError("target_activities must match the classifier arity")
    return keys


def _scan(log: CaseLog, spec: ContextualLabelSplittingSpec, keys: tuple[str, ...]):
    rows, issues = [], []
    if any(
        attribute.key == spec.output_key
        for global_ in log.globals
        if global_.scope == "event"
        for attribute in global_.attributes
    ):
        raise ValueError("output_key already exists as an event global default")
    for trace in log.traces:
        activities = []
        for event in trace.events:
            if log.attribute(event, spec.output_key) is not None:
                raise ValueError(
                    "output_key already exists; materialization never overwrites facts"
                )
            attributes = tuple(log.attribute(event, key) for key in keys)
            valid = all(
                a is not None and a.type in ("string", "id") and a.value.strip()
                for a in attributes
            )
            activities.append(tuple(a.value for a in attributes) if valid else None)
        for index, (event, activity) in enumerate(zip(trace.events, activities)):
            prefix = tuple(activities[max(0, index - spec.prefix_length) : index])
            suffix = tuple(activities[index + 1 : index + 1 + spec.suffix_length])
            if activity is None:
                disposition = "missing_activity"
            elif spec.target_activities and activity not in spec.target_activities:
                disposition = "not_targeted"
            elif None in prefix or None in suffix:
                disposition = "incomplete_context"
            else:
                disposition = "eligible"
            if disposition == "not_targeted" and (None in prefix or None in suffix):
                prefix, suffix = (), ()
            if disposition in ("missing_activity", "incomplete_context"):
                issues.append(
                    ComputeIssue(
                        disposition,
                        "Missing, blank or nontext classification; source positions are preserved",
                        (trace.id, event.id),
                    )
                )
                prefix, suffix = (), ()
            rows.append(
                LabelLineage(
                    trace.id,
                    event.id,
                    index,
                    activity,
                    prefix,
                    suffix,
                    None,
                    None,
                    None,
                    disposition,
                )
            )
    return tuple(rows), tuple(issues)


def _context_key(activity, prefix, suffix, distance):
    # In the reference profile, the boundary between before/after is discarded
    # for NODE IDENTITY as well as distance. Keep observed windows separately.
    if distance == "concatenated":
        return activity, prefix + suffix, ()
    return activity, prefix, suffix


def _finish(log, spec, operator, value, issues=(), parents=(), status=None):
    return _result(
        operator,
        None,
        spec,
        status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        tuple(issues),
        source_digest=case_log_digest(log),
        parent_computation_ids=parents,
    )


def fit_label_splitting(
    log: CaseLog, spec: ContextualLabelSplittingSpec = ContextualLabelSplittingSpec()
) -> ComputationResult[LabelSplittingModel]:
    """Fit contextual communities without mutating or embedding a raw CaseLog."""
    if not isinstance(log, CaseLog) or not isinstance(
        spec, ContextualLabelSplittingSpec
    ):
        raise TypeError("expected CaseLog and ContextualLabelSplittingSpec")
    try:
        keys = _keys(log, spec)
        lineage, issues = _scan(log, spec, keys)
    except ValueError as exc:
        return _finish(
            log,
            spec,
            "pix.case_centric.fit_label_splitting",
            None,
            (ComputeIssue("invalid_classification", str(exc)),),
            status=ComputeStatus.INVALID_INPUT,
        )
    occurrences = defaultdict(list)
    windows = defaultdict(set)
    for row in lineage:
        if row.disposition == "eligible":
            key = _context_key(row.original, row.prefix, row.suffix, spec.distance)
            occurrences[key].append(row.event_id)
            windows[key].add((row.prefix, row.suffix))
    if len(occurrences) > spec.max_contexts:
        return _finish(
            log,
            spec,
            "pix.case_centric.fit_label_splitting",
            None,
            (
                ComputeIssue(
                    "context_limit",
                    f"{len(occurrences)} unique contexts exceed max_contexts={spec.max_contexts}; no model was fitted",
                ),
            ),
            status=ComputeStatus.UNAVAILABLE,
        )
    contexts = tuple(
        LabelContext(
            i,
            key[0],
            min(windows[key])[0],
            min(windows[key])[1],
            tuple(sorted(occurrences[key])),
            tuple(
                ContextWindow(prefix, suffix) for prefix, suffix in sorted(windows[key])
            ),
        )
        for i, key in enumerate(sorted(occurrences))
    )
    edges = []
    threshold = Fraction(str(spec.min_similarity))
    for i, left in enumerate(contexts):
        for right in contexts[i + 1 :]:
            if left.activity == right.activity:
                weight = _similarity(left, right, spec.distance)
                if weight > threshold:
                    edges.append(
                        ContextSimilarity(
                            left.id, right.id, weight.numerator, weight.denominator
                        )
                    )
    edge_tuple = tuple(edges)
    groups = defaultdict(list)
    for community in _communities(contexts, edge_tuple):
        activity = contexts[community[0]].activity
        groups[activity].append(community)
    clusters = []
    for activity in sorted(groups):
        ordered = sorted(
            groups[activity],
            key=lambda ids: (-sum(len(contexts[i].event_ids) for i in ids), ids),
        )
        for rank, ids in enumerate(ordered):
            # An unsplit activity uses a null cluster tag, exactly as an unseen
            # retained activity does. A genuinely split class uses integer rank.
            clusters.append(
                LabelCluster(
                    len(clusters),
                    activity,
                    ids,
                    sum(len(contexts[i].event_ids) for i in ids),
                    _label(activity, rank if len(ordered) > 1 else None),
                )
            )
    cluster_by_context = {i: c for c in clusters for i in c.context_ids}
    context_by_key = {
        _context_key(c.activity, c.prefix, c.suffix, spec.distance): c for c in contexts
    }
    fitted_rows = []
    for row in lineage:
        if row.disposition == "eligible":
            context = context_by_key[
                _context_key(row.original, row.prefix, row.suffix, spec.distance)
            ]
            cluster = cluster_by_context[context.id]
            row = replace(
                row,
                context_id=context.id,
                cluster_id=cluster.id,
                derived_label=cluster.derived_label,
                disposition="fitted",
            )
        elif row.disposition == "not_targeted":
            row = replace(row, derived_label=_label(row.original, None))
        fitted_rows.append(row)
    excluded = sum(
        row.disposition in ("missing_activity", "incomplete_context") for row in lineage
    )
    model = LabelSplittingModel(
        keys,
        contexts,
        edge_tuple,
        tuple(clusters),
        tuple(fitted_rows),
        len(lineage),
        sum(row.disposition == "eligible" for row in lineage),
        excluded,
    )
    return _finish(log, spec, "pix.case_centric.fit_label_splitting", model, issues)


def _validate_fit(training_log: CaseLog, fitted: ComputationResult) -> None:
    if not isinstance(fitted, ComputationResult) or not isinstance(
        fitted.spec, ContextualLabelSplittingSpec
    ):
        raise TypeError("fitted must be a label-splitting fit result")
    if fitted.status not in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL):
        raise ValueError("a successful fitted model is required")
    if _identity_value(fitted) != _identity_value(
        fit_label_splitting(training_log, fitted.spec)
    ):
        raise ValueError(
            "fit evidence does not exactly match training source and request"
        )


def apply_label_splitting(
    log: CaseLog,
    fitted: ComputationResult[LabelSplittingModel],
    *,
    training_log: CaseLog,
    spec: LabelSplittingApplySpec = LabelSplittingApplySpec(),
) -> ComputationResult[AppliedLabelSplitting]:
    """Apply EXACT learned contexts; unseen contexts never get nearest labels.

    training_log is required to validate the complete fitted evidence, because a
    request digest alone does not authenticate a result payload. Both logs stay
    external to the immutable result. Missing contexts remain explicit.
    """
    if (
        not isinstance(log, CaseLog)
        or not isinstance(training_log, CaseLog)
        or not isinstance(spec, LabelSplittingApplySpec)
    ):
        raise TypeError("expected CaseLog inputs and LabelSplittingApplySpec")
    _validate_fit(training_log, fitted)
    request = LabelSplittingApplyRequest(
        spec, fitted.spec, fitted.source_digest, fitted.computation_id
    )
    parents = (fitted.computation_id,)
    model = fitted.value
    try:
        keys = _keys(log, fitted.spec)
        if keys != model.classifier_keys:
            raise ValueError(
                "application classifier keys differ from fitted classifier"
            )
        lineage, issues = _scan(log, fitted.spec, keys)
    except ValueError as exc:
        return _finish(
            log,
            request,
            "pix.case_centric.apply_label_splitting",
            None,
            (ComputeIssue("invalid_classification", str(exc)),),
            parents,
            ComputeStatus.INVALID_INPUT,
        )
    contexts = {
        _context_key(c.activity, c.prefix, c.suffix, fitted.spec.distance): c
        for c in model.contexts
    }
    clusters = {i: c for c in model.clusters for i in c.context_ids}
    known_activities = {c.activity for c in model.contexts}
    result_rows, issue_list = [], list(issues)
    known = unseen = 0
    for row in lineage:
        if row.disposition == "eligible":
            context = contexts.get(
                _context_key(row.original, row.prefix, row.suffix, fitted.spec.distance)
            )
            if context is not None:
                cluster = clusters[context.id]
                row = replace(
                    row,
                    context_id=context.id,
                    cluster_id=cluster.id,
                    derived_label=cluster.derived_label,
                    disposition="known",
                )
                known += 1
            else:
                disposition = (
                    "unseen_context"
                    if row.original in known_activities
                    else "unseen_activity"
                )
                row = replace(
                    row,
                    derived_label=_label(row.original, None),
                    disposition=disposition,
                )
                issue_list.append(
                    ComputeIssue(
                        disposition,
                        "No exact fitted context; original classification retained in a tagged label",
                        (row.case_id, row.event_id),
                    )
                )
                unseen += 1
        elif row.disposition == "not_targeted":
            row = replace(row, derived_label=_label(row.original, None))
        result_rows.append(row)
    if unseen and spec.unseen_context == "error":
        return _finish(
            log,
            request,
            "pix.case_centric.apply_label_splitting",
            None,
            issue_list,
            parents,
            ComputeStatus.INVALID_INPUT,
        )
    excluded = sum(
        row.disposition in ("missing_activity", "incomplete_context")
        for row in result_rows
    )
    value = AppliedLabelSplitting(
        keys,
        fitted.spec.output_key,
        tuple(result_rows),
        len(result_rows),
        known,
        unseen,
        excluded,
    )
    return _finish(
        log,
        request,
        "pix.case_centric.apply_label_splitting",
        value,
        issue_list,
        parents,
    )


def materialize_label_splitting(
    log: CaseLog,
    fitted: ComputationResult[LabelSplittingModel],
    applied: ComputationResult[AppliedLabelSplitting],
    *,
    training_log: CaseLog,
) -> CaseLog:
    """Return a derived CaseLog only after exact source/request/evidence replay."""
    if not isinstance(applied, ComputationResult) or not isinstance(
        applied.spec, LabelSplittingApplyRequest
    ):
        raise TypeError("applied must be a label-splitting application result")
    if applied.status not in (ComputeStatus.COMPUTED, ComputeStatus.PARTIAL):
        raise ValueError("successful application evidence is required")
    expected = apply_label_splitting(
        log, fitted, training_log=training_log, spec=applied.spec.application
    )
    if _identity_value(expected) != _identity_value(applied):
        raise ValueError(
            "application evidence does not exactly match source, model and request"
        )
    value = applied.value
    by_event = {row.event_id: row for row in value.lineage}
    traces = tuple(
        replace(
            trace,
            events=tuple(
                replace(
                    event,
                    attributes=event.attributes
                    + (
                        CaseAttribute(
                            value.output_key, "string", by_event[event.id].derived_label
                        ),
                    ),
                )
                if by_event[event.id].derived_label is not None
                else event
                for event in trace.events
            ),
        )
        for trace in log.traces
    )
    existing_names = {classifier.name for classifier in log.classifiers}
    name = "PIX contextual activity"
    suffix = 2
    while name in existing_names:
        name = f"PIX contextual activity {suffix}"
        suffix += 1
    classifier = CaseClassifier(name, (value.output_key,))
    return replace(
        log,
        traces=traces,
        classifiers=log.classifiers + (classifier,),
        metadata=log.metadata
        + (
            ("pix:contextual:fit", fitted.computation_id),
            ("pix:contextual:application", applied.computation_id),
            ("pix:contextual:source", applied.source_digest),
        ),
    )


RESULT_SCHEMAS = {
    "pix.case_centric.fit_label_splitting": (
        "label_splitting_model",
        ContextualLabelSplittingSpec,
        LabelSplittingModel,
    ),
    "pix.case_centric.apply_label_splitting": (
        "applied_label_splitting",
        LabelSplittingApplyRequest,
        AppliedLabelSplitting,
    ),
}

__all__ = (
    "ContextualLabelSplittingSpec",
    "LabelSplittingApplySpec",
    "LabelSplittingApplyRequest",
    "LabelContext",
    "ContextWindow",
    "ContextSimilarity",
    "LabelCluster",
    "LabelLineage",
    "LabelSplittingModel",
    "AppliedLabelSplitting",
    "fit_label_splitting",
    "apply_label_splitting",
    "materialize_label_splitting",
)
