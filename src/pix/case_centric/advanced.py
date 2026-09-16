"""Native finite case clustering, transport, decision rules and drift tests.

Profiles are explicit: no imported mining implementation, pretrained model or
causal inference is hidden behind these operators. Cases retain recorded order
for drift; clustering and learned rules use deterministic case-id tie breaks.
Caller-supplied feature vectors must already describe the information available
at the decision time. A learner cannot certify that an external feature was not
measured after the outcome.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from itertools import combinations
from math import comb, fsum, isfinite, sqrt
from random import Random
from typing import ClassVar, Literal

from pix.contracts.analysis import TraceSet
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.event_log import CaseLog, case_traces


def _int(value: object, name: str, minimum: int = 0) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")


def _real(value: object, name: str) -> None:
    if type(value) not in (int, float) or (
        type(value) is float and not isfinite(value)
    ):
        raise ValueError(f"{name} must be a finite real number")


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonblank text")


def _hash(value: object) -> str:
    content = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    return "pix.case_advanced.v1:sha256:" + sha256(content).hexdigest()


def _result(operator, source, spec, value=None, issues=(), parents=(), status=None):
    status = status or (
        ComputeStatus.COMPUTED if value is not None else ComputeStatus.UNAVAILABLE
    )
    return ComputationResult(
        operator,
        "1.0.0",
        source,
        spec,
        status,
        value,
        issues,
        computation_identity(operator, "1.0.0", source, spec, parents),
        parents,
    )


def _traces(log):
    if isinstance(log, CaseLog):
        return case_traces(log)
    if isinstance(log, ComputationResult) and (
        log.value is None or isinstance(log.value, TraceSet)
    ):
        return log
    raise TypeError("expected CaseLog or ComputationResult[TraceSet]")


def _words(traces):
    return tuple(
        (trace.object_id, tuple(event.activity for event in trace.events))
        for trace in traces.value.traces
    )


def _unusable(traces, operator, spec):
    if traces.status is ComputeStatus.COMPUTED and traces.value is not None:
        return None
    return _result(
        operator,
        traces.source_digest,
        spec,
        issues=traces.issues
        or (
            ComputeIssue(
                "incomplete_case_projection", "A complete case projection is required"
            ),
        ),
        parents=(traces.computation_id,) if traces.computation_id else (),
        status=ComputeStatus.INVALID_INPUT,
    )


def _combined_failure(traces, operator, spec, source, parents):
    issues = []
    for index, trace in enumerate(traces):
        if trace is not None and (
            trace.status is not ComputeStatus.COMPUTED or trace.value is None
        ):
            originals = trace.issues or (
                ComputeIssue(
                    "incomplete_case_projection",
                    "A complete case projection is required",
                ),
            )
            issues.extend(
                ComputeIssue(
                    issue.code, issue.message, ("operand", str(index)) + issue.at
                )
                for issue in originals
            )
    if issues:
        return _result(
            operator,
            source,
            spec,
            issues=tuple(issues),
            parents=parents,
            status=ComputeStatus.INVALID_INPUT,
        )
    return None


def _edit(left, right):
    """Unit insertion/deletion/substitution Levenshtein cost, linear memory."""
    row = list(range(len(right) + 1))
    for i, first in enumerate(left, 1):
        following = [i]
        for j, second in enumerate(right, 1):
            following.append(
                min(row[j] + 1, following[-1] + 1, row[j - 1] + (first != second))
            )
        row = following
    return row[-1]


@dataclass(frozen=True, slots=True)
class CaseVector:
    case_id: str
    values: tuple[int | float, ...]

    def __post_init__(self):
        _text(self.case_id, "case_id")
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple")
        for value in self.values:
            _real(value, "feature")


@dataclass(frozen=True, slots=True)
class CaseClusteringSpec:
    cluster_count: int = 2
    distance: Literal["edit", "normalized_edit", "dfg_cosine", "euclidean"] = (
        "normalized_edit"
    )
    linkage: Literal["single", "complete", "average"] = "average"
    max_pairs: int = 100_000
    max_edit_cells: int = 10_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _int(self.cluster_count, "cluster_count", 1)
        _int(self.max_pairs, "max_pairs", 1)
        _int(self.max_edit_cells, "max_edit_cells", 1)
        if self.distance not in ("edit", "normalized_edit", "dfg_cosine", "euclidean"):
            raise ValueError("unknown clustering distance")
        if self.linkage not in ("single", "complete", "average"):
            raise ValueError("unknown linkage")


@dataclass(frozen=True, slots=True)
class ClusteringRequest:
    parameters: CaseClusteringSpec
    vectors: tuple[CaseVector, ...]
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class ClusterMerge:
    left: tuple[str, ...]
    right: tuple[str, ...]
    distance: float


@dataclass(frozen=True, slots=True)
class CaseClustering:
    clusters: tuple[tuple[str, ...], ...]
    merges: tuple[ClusterMerge, ...]
    pair_distances: tuple[tuple[str, str, float], ...]


def _vectors(vectors, case_ids):
    if not isinstance(vectors, tuple) or not all(
        isinstance(item, CaseVector) for item in vectors
    ):
        raise TypeError("vectors must be a tuple of CaseVector")
    mapping = {item.case_id: item.values for item in vectors}
    if len(mapping) != len(vectors) or set(mapping) != set(case_ids):
        raise ValueError("vectors must contain every selected case exactly once")
    if len({len(value) for value in mapping.values()}) > 1:
        raise ValueError("feature vectors must have equal dimensions")
    return mapping


def _distance(left, right, metric, vectors=None, left_id=None, right_id=None):
    if metric in ("edit", "normalized_edit"):
        cost = _edit(left, right)
        return float(
            cost if metric == "edit" else Fraction(cost, max(len(left), len(right), 1))
        )
    if metric == "euclidean":
        # hypot avoids intermediate squares overflowing when the norm is finite.
        from math import hypot

        try:
            value = hypot(
                *(
                    first - second
                    for first, second in zip(vectors[left_id], vectors[right_id])
                )
            )
        except OverflowError as exc:
            raise ValueError(
                "Euclidean distance is not representable as a finite float"
            ) from exc
        if not isfinite(value):
            raise ValueError(
                "Euclidean distance is not representable as a finite float"
            )
        return value
    first, second = Counter(zip(left, left[1:])), Counter(zip(right, right[1:]))
    if not first or not second:
        return 0.0 if not first and not second else 1.0
    numerator = sum(value * second[key] for key, value in first.items())
    denominator = sqrt(sum(value * value for value in first.values())) * sqrt(
        sum(value * value for value in second.values())
    )
    return max(0.0, min(1.0, 1.0 - numerator / denominator))


def _agglomerate(ids, distances, cluster_count, linkage):
    clusters, merges = [(item,) for item in sorted(ids)], []
    while len(clusters) > cluster_count:
        candidates = []
        for a, b in combinations(clusters, 2):
            values = [distances[tuple(sorted((i, j)))] for i in a for j in b]
            cost = (
                min(values)
                if linkage == "single"
                else max(values)
                if linkage == "complete"
                else fsum(value / len(values) for value in values)
            )
            candidates.append((cost, a, b))
        cost, a, b = min(candidates)
        merges.append(ClusterMerge(a, b, cost))
        clusters = sorted(
            [part for part in clusters if part != a and part != b]
            + [tuple(sorted(a + b))]
        )
    return tuple(clusters), tuple(merges)


def cluster_cases(
    log: CaseLog | ComputationResult[TraceSet],
    spec: CaseClusteringSpec = CaseClusteringSpec(),
    *,
    vectors: tuple[CaseVector, ...] = (),
) -> ComputationResult[CaseClustering]:
    """Agglomerative clustering over cases, with weighted UPGMA average linkage.

    Every case retains its multiplicity. Ties are resolved by sorted case IDs.
    DFG cosine uses edge counts only: empty and single-event cases both have an
    empty edge vector. It deliberately does not invent a boundary similarity.
    Caller vectors receive no fitted scaling or automatic attribute selection.
    """
    if not isinstance(spec, CaseClusteringSpec):
        raise TypeError("spec must be CaseClusteringSpec")
    if not isinstance(vectors, tuple) or not all(
        isinstance(v, CaseVector) for v in vectors
    ):
        raise TypeError("vectors must be a tuple of CaseVector")
    request = ClusteringRequest(
        spec, tuple(sorted(vectors, key=lambda item: item.case_id))
    )
    traces, operator = _traces(log), "pix.case_centric.cluster_cases"
    failure = _unusable(traces, operator, request)
    if failure:
        return failure
    words = dict(_words(traces))
    source, parents = traces.source_digest, (traces.computation_id,)
    if not words:
        return _result(
            operator,
            source,
            request,
            issues=(ComputeIssue("empty_population", "Clustering requires cases"),),
            parents=parents,
        )
    if spec.cluster_count > len(words):
        raise ValueError("cluster_count exceeds the number of cases")
    ids = tuple(sorted(words))
    matrix = _vectors(vectors, ids) if spec.distance == "euclidean" else None
    if vectors and matrix is None:
        raise ValueError("vectors are accepted only for euclidean distance")
    pair_count = len(ids) * (len(ids) - 1) // 2
    weights = tuple(len(words[case_id]) + 1 for case_id in ids)
    cells = (
        (sum(weights) ** 2 - sum(weight * weight for weight in weights)) // 2
        if spec.distance.endswith("edit")
        else 0
    )
    if pair_count > spec.max_pairs or cells > spec.max_edit_cells:
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue(
                    "clustering_resource_limit",
                    "Exact distance matrix was not computed",
                ),
            ),
            parents=parents,
        )
    distances = {
        (a, b): _distance(words[a], words[b], spec.distance, matrix, a, b)
        for a, b in combinations(ids, 2)
    }
    clusters, merges = _agglomerate(ids, distances, spec.cluster_count, spec.linkage)
    value = CaseClustering(
        clusters,
        merges,
        tuple((a, b, distance) for (a, b), distance in sorted(distances.items())),
    )
    return _result(operator, source, request, value, parents=parents)


@dataclass(frozen=True, slots=True)
class CaseAttributeClusteringSpec:
    """Group traces by a primitive case attribute, then cluster the sublogs.

    mean_edit/mean_normalized_edit averages all cross-group case pairs with
    observed multiplicity. dfg_cosine compares aggregated edge-count profiles.
    Average linkage gives each original attribute group equal weight, independent
    of its trace count. These are explicit PIX distances, not PM DMM aliases.
    """

    attribute_key: str
    cluster_count: int = 2
    distance: Literal["mean_edit", "mean_normalized_edit", "dfg_cosine"] = (
        "mean_normalized_edit"
    )
    linkage: Literal["single", "complete", "average"] = "average"
    max_case_pairs: int = 100_000
    max_edit_cells: int = 10_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        _text(self.attribute_key, "attribute_key")
        for name in ("cluster_count", "max_case_pairs", "max_edit_cells"):
            _int(getattr(self, name), name, 1)
        if self.distance not in ("mean_edit", "mean_normalized_edit", "dfg_cosine"):
            raise ValueError("unknown group distance")
        if self.linkage not in ("single", "complete", "average"):
            raise ValueError("unknown linkage")


@dataclass(frozen=True, slots=True)
class CaseAttributeGroup:
    group_id: str
    attribute_type: str
    attribute_value: str
    case_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CaseAttributeClustering:
    groups: tuple[CaseAttributeGroup, ...]
    clusters: tuple[tuple[str, ...], ...]
    case_clusters: tuple[tuple[str, ...], ...]
    merges: tuple[ClusterMerge, ...]
    group_distances: tuple[tuple[str, str, float], ...]


def cluster_case_attribute_groups(
    log: CaseLog, spec: CaseAttributeClusteringSpec
) -> ComputationResult[CaseAttributeClustering]:
    """Attribute values define sublog leaves; no missing-value imputation."""
    if not isinstance(log, CaseLog) or not isinstance(
        spec, CaseAttributeClusteringSpec
    ):
        raise TypeError("expected CaseLog and CaseAttributeClusteringSpec")
    traces, operator = (
        case_traces(log),
        "pix.case_centric.cluster_case_attribute_groups",
    )
    failure = _unusable(traces, operator, spec)
    if failure:
        return failure
    words, grouped, definitions = dict(_words(traces)), {}, {}
    for trace in log.traces:
        attribute = log.attribute(trace, spec.attribute_key)
        if attribute is None or attribute.type not in (
            "string",
            "id",
            "int",
            "float",
            "boolean",
            "date",
            "null",
        ):
            raise ValueError(
                f"case {trace.id!r} lacks an unambiguous primitive grouping attribute"
            )
        if type(attribute.value) is float and not isfinite(attribute.value):
            raise ValueError("group attribute must be finite")
        # A typed value prevents the groups 1, true and '1' from collapsing.
        encoded = json.dumps(
            attribute.value.isoformat()
            if attribute.type == "date"
            else attribute.value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        group_id = attribute.type + ":" + encoded
        definitions[group_id] = (attribute.type, encoded)
        grouped.setdefault(group_id, []).append(trace.id)
    source, parents = traces.source_digest, (traces.computation_id,)
    if not grouped:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue("empty_population", "Attribute clustering requires cases"),
            ),
            parents=parents,
        )
    if spec.cluster_count > len(grouped):
        raise ValueError("cluster_count exceeds the number of attribute groups")
    grouped = {group: tuple(sorted(cases)) for group, cases in sorted(grouped.items())}
    required_pairs, required_cells = 0, 0
    if spec.distance != "dfg_cosine":
        counts = tuple(len(cases) for cases in grouped.values())
        weights = tuple(
            sum(len(words[case_id]) + 1 for case_id in cases)
            for cases in grouped.values()
        )
        required_pairs = (
            sum(counts) ** 2 - sum(count * count for count in counts)
        ) // 2
        required_cells = (
            sum(weights) ** 2 - sum(weight * weight for weight in weights)
        ) // 2
    else:
        required_pairs = len(grouped) * (len(grouped) - 1) // 2
    if required_pairs > spec.max_case_pairs or required_cells > spec.max_edit_cells:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "group_clustering_resource_limit",
                    "Sublog distance matrix was not computed",
                ),
            ),
            parents=parents,
        )
    distances = {}
    profiles = (
        {
            group: sum(
                (Counter(zip(words[case_id], words[case_id][1:])) for case_id in cases),
                Counter(),
            )
            for group, cases in grouped.items()
        }
        if spec.distance == "dfg_cosine"
        else {}
    )
    for a, b in combinations(grouped, 2):
        if spec.distance != "dfg_cosine":
            size = len(grouped[a]) * len(grouped[b])
            distances[a, b] = fsum(
                _distance(
                    words[i],
                    words[j],
                    "edit" if spec.distance == "mean_edit" else "normalized_edit",
                )
                / size
                for i in grouped[a]
                for j in grouped[b]
            )
        else:
            left, right = profiles[a], profiles[b]
            if not left or not right:
                distances[a, b] = 0.0 if not left and not right else 1.0
            else:
                dot = sum(count * right[key] for key, count in left.items())
                norm = sqrt(sum(count * count for count in left.values())) * sqrt(
                    sum(count * count for count in right.values())
                )
                distances[a, b] = max(0.0, min(1.0, 1.0 - dot / norm))
    clusters, merges = _agglomerate(
        tuple(grouped), distances, spec.cluster_count, spec.linkage
    )
    groups = tuple(
        CaseAttributeGroup(group, *definitions[group], cases)
        for group, cases in grouped.items()
    )
    case_clusters = tuple(
        tuple(sorted(case_id for group in cluster for case_id in grouped[group]))
        for cluster in clusters
    )
    value = CaseAttributeClustering(
        groups,
        clusters,
        case_clusters,
        merges,
        tuple((a, b, cost) for (a, b), cost in sorted(distances.items())),
    )
    return _result(operator, source, spec, value, parents=parents)


@dataclass(frozen=True, slots=True)
class CaseRetrievalSpec:
    neighbors: int = 1
    normalized: bool = True
    include_boundary_ties: bool = True
    max_pairs: int = 100_000
    max_edit_cells: int = 10_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("neighbors", "max_pairs", "max_edit_cells"):
            _int(getattr(self, name), name, 1)
        for name in ("normalized", "include_boundary_ties"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class CaseRetrievalRequest:
    reference_computation_id: str | None
    parameters: CaseRetrievalSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class CaseNeighbor:
    case_id: str
    distance: float


@dataclass(frozen=True, slots=True)
class RetrievedCase:
    query_case_id: str
    neighbors: tuple[CaseNeighbor, ...]


@dataclass(frozen=True, slots=True)
class CaseRetrieval:
    queries: tuple[RetrievedCase, ...]
    reference_count: int


def retrieve_similar_cases(
    query, reference, spec: CaseRetrievalSpec = CaseRetrievalSpec()
) -> ComputationResult[CaseRetrieval]:
    """Exact nearest observed sequences by edit distance; no predictive claim."""
    if not isinstance(spec, CaseRetrievalSpec):
        raise TypeError("spec must be CaseRetrievalSpec")
    left, right = _traces(query), _traces(reference)
    request, operator = (
        CaseRetrievalRequest(right.computation_id, spec),
        "pix.case_centric.retrieve_similar_cases",
    )
    source = (
        _hash((left.source_digest, right.source_digest))
        if left.source_digest is not None and right.source_digest is not None
        else None
    )
    parents = tuple(
        trace.computation_id for trace in (left, right) if trace.computation_id
    )
    failure = _combined_failure((left, right), operator, request, source, parents)
    if failure:
        return failure
    queries, references = _words(left), _words(right)
    if not references:
        return _result(
            operator,
            source,
            request,
            issues=(ComputeIssue("empty_reference", "No reference cases exist"),),
            parents=parents,
        )
    cells = sum(len(word) + 1 for _, word in queries) * sum(
        len(word) + 1 for _, word in references
    )
    if len(queries) * len(references) > spec.max_pairs or cells > spec.max_edit_cells:
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue("retrieval_resource_limit", "Distances were not computed"),
            ),
            parents=parents,
        )
    rows = []
    for query_id, word in queries:
        scores = sorted(
            (
                _distance(
                    word, other, "normalized_edit" if spec.normalized else "edit"
                ),
                ref_id,
            )
            for ref_id, other in references
        )
        limit = min(spec.neighbors, len(scores))
        boundary = scores[limit - 1][0]
        selected = (
            scores
            if limit == len(scores)
            else scores[:limit]
            if not spec.include_boundary_ties
            else [item for item in scores if item[0] <= boundary]
        )
        rows.append(
            RetrievedCase(
                query_id, tuple(CaseNeighbor(ref_id, cost) for cost, ref_id in selected)
            )
        )
    return _result(
        operator,
        source,
        request,
        CaseRetrieval(tuple(rows), len(references)),
        parents=parents,
    )


@dataclass(frozen=True, slots=True)
class RationalValue:
    numerator: int
    denominator: int = 1

    def __post_init__(self):
        if type(self.numerator) is not int:
            raise TypeError("numerator must be int")
        _int(self.denominator, "denominator", 1)
        fraction = Fraction(self.numerator, self.denominator)
        object.__setattr__(self, "numerator", fraction.numerator)
        object.__setattr__(self, "denominator", fraction.denominator)

    def as_fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)


def _rational(value):
    value = Fraction(value)
    return RationalValue(value.numerator, value.denominator)


@dataclass(frozen=True, slots=True)
class CaseProfileClusteringSpec:
    """Lloyd K-means on activity and directly-follows occurrence counts.

    Deterministic farthest-first initialization and exact rational centroids
    define the PIX profile; no sklearn initialization or global optimum parity
    is asserted. Feature vocabulary is fitted only to the supplied population.
    No feature scaling is implicit. Empty clusters retain their prior centroid.
    """

    cluster_count: int = 2
    include_activities: bool = True
    include_dfg: bool = True
    max_iterations: int = 100
    max_feature_values: int = 1_000_000
    max_distance_evaluations: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in (
            "cluster_count",
            "max_iterations",
            "max_feature_values",
            "max_distance_evaluations",
        ):
            _int(getattr(self, name), name, 1)
        for name in ("include_activities", "include_dfg"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if not self.include_activities and not self.include_dfg:
            raise ValueError("at least one profile feature family must be enabled")


@dataclass(frozen=True, slots=True)
class ProfileColumn:
    kind: Literal["activity", "directly_follows"]
    activity: str
    target: str | None


@dataclass(frozen=True, slots=True)
class CaseProfileCluster:
    cluster_id: int
    case_ids: tuple[str, ...]
    centroid: tuple[RationalValue, ...]


@dataclass(frozen=True, slots=True)
class CaseProfileClustering:
    columns: tuple[ProfileColumn, ...]
    clusters: tuple[CaseProfileCluster, ...]
    inertia: RationalValue
    iterations: int
    distance_evaluations: int
    converged: bool
    initialization_case_ids: tuple[str, ...]


def cluster_case_profiles(
    log, spec: CaseProfileClusteringSpec = CaseProfileClusteringSpec()
) -> ComputationResult[CaseProfileClustering]:
    """Fit count-profile K-means with a finite, inspectable Lloyd iteration."""
    if not isinstance(spec, CaseProfileClusteringSpec):
        raise TypeError("spec must be CaseProfileClusteringSpec")
    traces, operator = _traces(log), "pix.case_centric.cluster_case_profiles"
    failure = _unusable(traces, operator, spec)
    if failure:
        return failure
    words = tuple(sorted(_words(traces)))
    source, parents = traces.source_digest, (traces.computation_id,)
    columns = []
    if spec.include_activities:
        columns.extend(
            ProfileColumn("activity", activity, None)
            for activity in sorted({activity for _, word in words for activity in word})
        )
    if spec.include_dfg:
        columns.extend(
            ProfileColumn("directly_follows", a, b)
            for a, b in sorted(
                {pair for _, word in words for pair in zip(word, word[1:])}
            )
        )
    if not words:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue("empty_population", "Profile clustering requires cases"),
            ),
            parents=parents,
        )
    if len(words) * len(columns) > spec.max_feature_values:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "profile_feature_limit", "Profile matrix was not allocated"
                ),
            ),
            parents=parents,
        )
    points = []
    for case_id, word in words:
        activities, edges = Counter(word), Counter(zip(word, word[1:]))
        points.append(
            (
                case_id,
                tuple(
                    activities[column.activity]
                    if column.kind == "activity"
                    else edges[column.activity, column.target]
                    for column in columns
                ),
            )
        )
    if len({point for _, point in points}) < spec.cluster_count:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "insufficient_distinct_profiles",
                    "Requested clusters exceed the number of distinct count profiles",
                ),
            ),
            parents=parents,
        )
    evaluations = 0

    def squared(first, second):
        return sum(
            ((Fraction(a) - Fraction(b)) ** 2 for a, b in zip(first, second)),
            Fraction(),
        )

    # Initialization distance work is budgeted too. A deterministic farthest
    # point makes this an explicit profile rather than a hidden random seed.
    centers = [tuple(Fraction(value) for value in points[0][1])]
    initial_ids = [points[0][0]]
    while len(centers) < spec.cluster_count:
        required = len(points) * len(centers)
        if evaluations + required > spec.max_distance_evaluations:
            return _result(
                operator,
                source,
                spec,
                issues=(
                    ComputeIssue(
                        "profile_initialization_limit", "Initialization did not finish"
                    ),
                ),
                parents=parents,
            )
        scores = [
            (min(squared(point, center) for center in centers), case_id, point)
            for case_id, point in points
        ]
        evaluations += required
        _, chosen_id, chosen = min(scores, key=lambda item: (-item[0], item[1]))
        initial_ids.append(chosen_id)
        centers.append(tuple(Fraction(value) for value in chosen))
    assignment, iterations, converged = None, 0, False
    while iterations < spec.max_iterations:
        required = len(points) * len(centers)
        if evaluations + required > spec.max_distance_evaluations:
            break
        following = tuple(
            min(
                range(len(centers)),
                key=lambda index: (squared(point, centers[index]), index),
            )
            for _, point in points
        )
        evaluations += required
        updated = []
        for index, prior in enumerate(centers):
            members = [
                point
                for (_, point), cluster in zip(points, following)
                if cluster == index
            ]
            updated.append(
                tuple(
                    Fraction(sum(point[column] for point in members), len(members))
                    for column in range(len(columns))
                )
                if members
                else prior
            )
        converged = following == assignment
        assignment, centers = following, updated
        iterations += 1
        if converged:
            break
    if assignment is None:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "profile_assignment_limit", "No complete assignment was computed"
                ),
            ),
            parents=parents,
        )
    clusters = tuple(
        CaseProfileCluster(
            index,
            tuple(
                case_id
                for (case_id, _), cluster in zip(points, assignment)
                if cluster == index
            ),
            tuple(_rational(coordinate) for coordinate in center),
        )
        for index, center in enumerate(centers)
    )
    inertia = sum(
        (
            squared(point, centers[cluster])
            for (_, point), cluster in zip(points, assignment)
        ),
        Fraction(),
    )
    value = CaseProfileClustering(
        tuple(columns),
        clusters,
        _rational(inertia),
        iterations,
        evaluations,
        converged,
        tuple(initial_ids),
    )
    issues = (
        ()
        if converged
        else (
            ComputeIssue(
                "profile_iteration_limit",
                "A fitted partition exists but Lloyd convergence was not established within the budget",
            ),
        )
    )
    return _result(
        operator,
        source,
        spec,
        value,
        issues,
        parents,
        ComputeStatus.COMPUTED if converged else ComputeStatus.PARTIAL,
    )


@dataclass(frozen=True, slots=True)
class LanguageEntry:
    activities: tuple[str, ...]
    mass: RationalValue

    def __post_init__(self):
        if not isinstance(self.activities, tuple):
            raise TypeError("activities must be a tuple")
        for activity in self.activities:
            _text(activity, "activity")
        if not isinstance(self.mass, RationalValue) or self.mass.numerator < 0:
            raise ValueError("mass must be a nonnegative RationalValue")


@dataclass(frozen=True, slots=True)
class StochasticLanguage:
    entries: tuple[LanguageEntry, ...]

    def __post_init__(self):
        if not isinstance(self.entries, tuple) or not all(
            isinstance(item, LanguageEntry) for item in self.entries
        ):
            raise TypeError("entries must be a tuple of LanguageEntry")
        counts = {}
        for item in self.entries:
            counts[item.activities] = (
                counts.get(item.activities, Fraction()) + item.mass.as_fraction()
            )
        object.__setattr__(
            self,
            "entries",
            tuple(
                LanguageEntry(word, _rational(mass))
                for word, mass in sorted(counts.items())
                if mass
            ),
        )


@dataclass(frozen=True, slots=True)
class LanguageDistanceSpec:
    normalized_edit: bool = True
    normalize_mass: bool = True
    max_pairs: int = 10_000
    max_edit_cells: int = 10_000_000
    max_augmentations: int = 100_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in ("max_pairs", "max_edit_cells", "max_augmentations"):
            _int(getattr(self, name), name, 1)
        for name in ("normalized_edit", "normalize_mass"):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")


@dataclass(frozen=True, slots=True)
class LanguageDistanceRequest:
    left: StochasticLanguage
    right: StochasticLanguage
    parameters: LanguageDistanceSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class TransportFlow:
    source: tuple[str, ...]
    target: tuple[str, ...]
    mass: RationalValue
    unit_cost: RationalValue


@dataclass(frozen=True, slots=True)
class LanguageDistance:
    status: Literal["optimal", "resource_limit"]
    distance: RationalValue | None
    transported_mass: RationalValue
    partial_transport_cost: RationalValue
    flows: tuple[TransportFlow, ...]
    augmentations: int


def _language(data):
    if isinstance(data, StochasticLanguage):
        return data, None
    traces = _traces(data)
    if traces.status is not ComputeStatus.COMPUTED or traces.value is None:
        return StochasticLanguage(()), traces
    counts = Counter(word for _, word in _words(traces))
    return StochasticLanguage(
        tuple(
            LanguageEntry(word, RationalValue(count))
            for word, count in sorted(counts.items())
        )
    ), traces


def compare_stochastic_languages(
    left, right, spec: LanguageDistanceSpec = LanguageDistanceSpec()
) -> ComputationResult[LanguageDistance]:
    """Exact balanced optimal transport with rational masses and edit costs.

    Native residual-network shortest augmenting paths can reroute earlier flow;
    greedy nearest-pair matching cannot. Bellman-Ford handles negative reverse
    edges without float tolerances. A budget interruption returns a partial
    transport witness, never an EMD estimate or an optimality assertion.
    """
    if not isinstance(spec, LanguageDistanceSpec):
        raise TypeError("spec must be LanguageDistanceSpec")
    first, first_trace = _language(left)
    second, second_trace = _language(right)
    request, operator = (
        LanguageDistanceRequest(first, second, spec),
        "pix.case_centric.compare_stochastic_languages",
    )
    source = _hash(
        tuple(
            tuple(
                (entry.activities, entry.mass.numerator, entry.mass.denominator)
                for entry in lang.entries
            )
            for lang in (first, second)
        )
    )
    if any(
        trace is not None and trace.source_digest is None
        for trace in (first_trace, second_trace)
    ):
        source = None
    parents = tuple(
        trace.computation_id
        for trace in (first_trace, second_trace)
        if trace is not None and trace.computation_id
    )
    failure = _combined_failure(
        (first_trace, second_trace), operator, request, source, parents
    )
    if failure:
        return failure
    if not first.entries or not second.entries:
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue(
                    "empty_language", "Both languages require positive total mass"
                ),
            ),
            parents=parents,
        )
    sums = [
        sum((entry.mass.as_fraction() for entry in lang.entries), Fraction())
        for lang in (first, second)
    ]
    if not spec.normalize_mass and any(total != 1 for total in sums):
        raise ValueError(
            "normalize_mass=False requires each language to sum exactly to one"
        )
    sizes = len(first.entries), len(second.entries)
    if (
        sizes[0] * sizes[1] > spec.max_pairs
        or sum(
            (len(a.activities) + 1) * (len(b.activities) + 1)
            for a in first.entries
            for b in second.entries
        )
        > spec.max_edit_cells
    ):
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue(
                    "transport_resource_limit", "Cost matrix was not computed"
                ),
            ),
            parents=parents,
        )
    n, m = sizes
    sink, count = n + m + 1, n + m + 2
    graph = [[] for _ in range(count)]

    def edge(a, b, capacity, cost):
        forward = [b, len(graph[b]), capacity, cost]
        backward = [a, len(graph[a]), Fraction(), -cost]
        graph[a].append(forward)
        graph[b].append(backward)
        return forward

    for i, entry in enumerate(first.entries):
        edge(0, i + 1, entry.mass.as_fraction() / sums[0], Fraction())
    tracked = []
    for i, a in enumerate(first.entries):
        for j, b in enumerate(second.entries):
            cost = Fraction(
                _edit(a.activities, b.activities),
                max(len(a.activities), len(b.activities), 1)
                if spec.normalized_edit
                else 1,
            )
            forward = edge(i + 1, n + j + 1, Fraction(1), cost)
            tracked.append((a.activities, b.activities, forward, cost))
    for j, entry in enumerate(second.entries):
        edge(n + j + 1, sink, entry.mass.as_fraction() / sums[1], Fraction())
    transported, augmentations = Fraction(), 0
    while transported < 1 and augmentations < spec.max_augmentations:
        distances, predecessor = [None] * count, [None] * count
        distances[0] = Fraction()
        for _ in range(count - 1):
            changed = False
            for node in range(count):
                if distances[node] is None:
                    continue
                for index, item in enumerate(graph[node]):
                    target, _, capacity, cost = item
                    candidate = distances[node] + cost
                    if capacity > 0 and (
                        distances[target] is None or candidate < distances[target]
                    ):
                        distances[target], predecessor[target] = (
                            candidate,
                            (node, index),
                        )
                        changed = True
            if not changed:
                break
        if predecessor[sink] is None:
            raise RuntimeError(
                "balanced complete transport graph unexpectedly infeasible"
            )
        amount, node = 1 - transported, sink
        while node:
            previous, index = predecessor[node]
            amount = min(amount, graph[previous][index][2])
            node = previous
        node = sink
        while node:
            previous, index = predecessor[node]
            item = graph[previous][index]
            item[2] -= amount
            graph[node][item[1]][2] += amount
            node = previous
        transported += amount
        augmentations += 1
    flows = tuple(
        TransportFlow(a, b, _rational(1 - forward[2]), _rational(cost))
        for a, b, forward, cost in tracked
        if forward[2] != 1
    )
    total_cost = sum(
        (flow.mass.as_fraction() * flow.unit_cost.as_fraction() for flow in flows),
        Fraction(),
    )
    complete = transported == 1
    value = LanguageDistance(
        "optimal" if complete else "resource_limit",
        _rational(total_cost) if complete else None,
        _rational(transported),
        _rational(total_cost),
        flows,
        augmentations,
    )
    issues = (
        ()
        if complete
        else (
            ComputeIssue(
                "transport_augmentation_limit",
                "Transport is incomplete; the EMD is unknown",
            ),
        )
    )
    return _result(
        operator,
        source,
        request,
        value,
        issues,
        parents,
        ComputeStatus.COMPUTED if complete else ComputeStatus.PARTIAL,
    )


@dataclass(frozen=True, slots=True)
class DecisionExample:
    case_id: str
    features: tuple[int | float, ...]
    target: str

    def __post_init__(self):
        _text(self.case_id, "case_id")
        _text(self.target, "target")
        if not isinstance(self.features, tuple):
            raise TypeError("features must be a tuple")
        for value in self.features:
            _real(value, "feature")


@dataclass(frozen=True, slots=True)
class DecisionTreeSpec:
    feature_names: tuple[str, ...]
    max_depth: int = 8
    min_leaf: int = 1
    min_gain: int | float = 0.0
    max_examples: int = 10_000
    max_split_evaluations: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        if not isinstance(self.feature_names, tuple):
            raise TypeError("feature_names must be a tuple")
        for name in self.feature_names:
            _text(name, "feature name")
        if len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature names must be unique")
        for name in ("max_depth", "min_leaf", "max_examples", "max_split_evaluations"):
            _int(getattr(self, name), name, 0 if name == "max_depth" else 1)
        if self.max_depth > 256:
            raise ValueError("max_depth exceeds this profile's recursion bound of 256")
        _real(self.min_gain, "min_gain")
        if self.min_gain < 0 or self.min_gain > 1:
            raise ValueError("min_gain must lie between zero and one")


@dataclass(frozen=True, slots=True)
class DecisionTreeRequest:
    examples: tuple[DecisionExample, ...]
    parameters: DecisionTreeSpec
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"


@dataclass(frozen=True, slots=True)
class DecisionNode:
    id: int
    sample_count: int
    class_counts: tuple[tuple[str, int], ...]
    prediction: str
    feature_index: int | None
    threshold: int | float | None
    left: int | None
    right: int | None
    stop_reason: str | None


@dataclass(frozen=True, slots=True)
class GuardCondition:
    feature_index: int
    feature_name: str
    operator: Literal["<=", ">"]
    threshold: int | float


@dataclass(frozen=True, slots=True)
class DecisionGuard:
    conditions: tuple[GuardCondition, ...]
    prediction: str
    support: int
    correct_training_examples: int


@dataclass(frozen=True, slots=True)
class DecisionTree:
    feature_names: tuple[str, ...]
    training_case_ids: tuple[str, ...]
    training_digest: str
    nodes: tuple[DecisionNode, ...]
    guards: tuple[DecisionGuard, ...]
    training_correct: int
    training_count: int
    split_evaluations: int
    status: Literal["fitted", "resource_limit"]

    def __post_init__(self):
        if not isinstance(self.feature_names, tuple) or not isinstance(
            self.training_case_ids, tuple
        ):
            raise TypeError("tree feature/sample IDs must be tuples")
        for value in self.feature_names + self.training_case_ids:
            _text(value, "tree feature/sample ID")
        if len(set(self.feature_names)) != len(self.feature_names) or len(
            set(self.training_case_ids)
        ) != len(self.training_case_ids):
            raise ValueError("tree feature/sample IDs must be unique")
        _text(self.training_digest, "training_digest")
        _int(self.training_count, "training_count", 1)
        _int(self.training_correct, "training_correct")
        _int(self.split_evaluations, "split_evaluations")
        if (
            self.status not in ("fitted", "resource_limit")
            or len(self.training_case_ids) != self.training_count
        ):
            raise ValueError("tree status/training population is inconsistent")
        if (
            not isinstance(self.nodes, tuple)
            or not self.nodes
            or not all(isinstance(node, DecisionNode) for node in self.nodes)
        ):
            raise ValueError("decision tree needs typed nonempty nodes")
        if not isinstance(self.guards, tuple) or not all(
            isinstance(guard, DecisionGuard) for guard in self.guards
        ):
            raise TypeError("tree guards must be a tuple of DecisionGuard")
        if self.nodes[0].sample_count != self.training_count:
            raise ValueError("tree root count differs from the training population")
        for index, node in enumerate(self.nodes):
            if type(node.id) is not int or node.id != index:
                raise ValueError("tree node IDs must match contiguous storage indices")
            _int(node.sample_count, "node sample_count", 1)
            if not isinstance(node.class_counts, tuple) or not all(
                isinstance(pair, tuple) and len(pair) == 2 for pair in node.class_counts
            ):
                raise ValueError("node class counts must be label/count pairs")
            labels = []
            for label, count in node.class_counts:
                _text(label, "class label")
                _int(count, "class count", 1)
                labels.append(label)
            if (
                len(set(labels)) != len(labels)
                or sum(count for _, count in node.class_counts) != node.sample_count
                or node.prediction not in labels
            ):
                raise ValueError("node class counts/prediction are inconsistent")
        stack, seen, expected_guards = [(0, ())], set(), []
        while stack:
            index, path = stack.pop()
            if index in seen:
                raise ValueError("decision tree contains a cycle or shared subtree")
            seen.add(index)
            node = self.nodes[index]
            if node.feature_index is None:
                if any(
                    value is not None
                    for value in (node.threshold, node.left, node.right)
                ) or not isinstance(node.stop_reason, str):
                    raise ValueError("leaf node has inconsistent split/stop fields")
                expected_guards.append(
                    DecisionGuard(
                        path,
                        node.prediction,
                        node.sample_count,
                        dict(node.class_counts)[node.prediction],
                    )
                )
                continue
            if type(node.feature_index) is not int or not 0 <= node.feature_index < len(
                self.feature_names
            ):
                raise ValueError("tree feature index is outside its schema")
            _real(node.threshold, "tree threshold")
            if node.stop_reason is not None or any(
                type(child) is not int or not 0 <= child < len(self.nodes)
                for child in (node.left, node.right)
            ):
                raise ValueError("split node has invalid child/stop fields")
            combined = Counter(dict(self.nodes[node.left].class_counts)) + Counter(
                dict(self.nodes[node.right].class_counts)
            )
            if dict(combined) != dict(node.class_counts):
                raise ValueError(
                    "child class counts do not conserve the parent population"
                )
            name = self.feature_names[node.feature_index]
            stack.append(
                (
                    node.right,
                    path
                    + (GuardCondition(node.feature_index, name, ">", node.threshold),),
                )
            )
            stack.append(
                (
                    node.left,
                    path
                    + (GuardCondition(node.feature_index, name, "<=", node.threshold),),
                )
            )
        if len(seen) != len(self.nodes) or tuple(expected_guards) != self.guards:
            raise ValueError("tree guard paths or node reachability are inconsistent")
        if self.training_correct != sum(
            guard.correct_training_examples for guard in self.guards
        ):
            raise ValueError("tree training accuracy does not match its leaf counts")


def _gini(examples):
    counts = Counter(item.target for item in examples)
    n = len(examples)
    return Fraction(1) - sum(
        (Fraction(count * count, n * n) for count in counts.values()), Fraction()
    )


def mine_decision_tree(
    log, examples: tuple[DecisionExample, ...], spec: DecisionTreeSpec
) -> ComputationResult[DecisionTree]:
    """Deterministic numeric CART with explicit targets and training population.

    One supplied example per selected case; no automatic alignment-to-decision
    extraction, imputation, feature scaling or holdout fit. Zero-gain splits are
    permitted when min_gain=0, allowing XOR to be represented at depth two.
    A threshold is the greatest observed value on the left, avoiding midpoint
    overflow and false promises about unobserved numeric values.
    """
    if not isinstance(spec, DecisionTreeSpec):
        raise TypeError("spec must be DecisionTreeSpec")
    if not isinstance(examples, tuple) or not all(
        isinstance(item, DecisionExample) for item in examples
    ):
        raise TypeError("examples must be a tuple of DecisionExample")
    examples = tuple(sorted(examples, key=lambda item: item.case_id))
    if len({item.case_id for item in examples}) != len(examples):
        raise ValueError("training examples must have unique case IDs")
    if any(len(item.features) != len(spec.feature_names) for item in examples):
        raise ValueError("feature dimensions must match feature_names")
    traces, operator = _traces(log), "pix.case_centric.mine_decision_tree"
    request = DecisionTreeRequest(examples, spec)
    failure = _unusable(traces, operator, request)
    if failure:
        return failure
    population = {case_id for case_id, _ in _words(traces)}
    if not {item.case_id for item in examples}.issubset(population):
        raise ValueError("training examples contain cases outside the supplied log")
    parents, source = (traces.computation_id,), traces.source_digest
    if not examples:
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue(
                    "empty_training_population", "Decision training requires examples"
                ),
            ),
            parents=parents,
        )
    if len(examples) > spec.max_examples:
        return _result(
            operator,
            source,
            request,
            issues=(
                ComputeIssue("decision_example_limit", "No training was performed"),
            ),
            parents=parents,
        )
    nodes, guards, evaluations, limited = [], [], 0, False

    def grow(items, depth, path):
        nonlocal evaluations, limited
        index = len(nodes)
        counts = tuple(sorted(Counter(item.target for item in items).items()))
        prediction = min(counts, key=lambda pair: (-pair[1], pair[0]))[0]
        node = DecisionNode(
            index, len(items), counts, prediction, None, None, None, None, None
        )
        nodes.append(node)
        reason = (
            "pure"
            if len(counts) == 1
            else "max_depth"
            if depth >= spec.max_depth
            else None
        )
        best = None
        if reason is None:
            impurity = _gini(items)
            for feature in range(len(spec.feature_names)):
                values = sorted({item.features[feature] for item in items})
                for threshold in values[:-1]:
                    left = tuple(
                        item for item in items if item.features[feature] <= threshold
                    )
                    right = tuple(
                        item for item in items if item.features[feature] > threshold
                    )
                    if min(len(left), len(right)) < spec.min_leaf:
                        continue
                    if evaluations >= spec.max_split_evaluations:
                        limited, reason = True, "resource_limit"
                        break
                    evaluations += 1
                    gain = (
                        impurity
                        - Fraction(len(left), len(items)) * _gini(left)
                        - Fraction(len(right), len(items)) * _gini(right)
                    )
                    candidate = (-gain, feature, threshold, left, right)
                    if best is None or candidate[:3] < best[:3]:
                        best = candidate
                if reason == "resource_limit":
                    break
            if reason is None and (best is None or -best[0] < Fraction(spec.min_gain)):
                reason = "no_eligible_split"
        if reason is not None:
            nodes[index] = DecisionNode(
                index, len(items), counts, prediction, None, None, None, None, reason
            )
            guards.append(
                DecisionGuard(path, prediction, len(items), dict(counts)[prediction])
            )
            return index
        _, feature, threshold, left, right = best
        left_index = grow(
            left,
            depth + 1,
            path
            + (GuardCondition(feature, spec.feature_names[feature], "<=", threshold),),
        )
        right_index = grow(
            right,
            depth + 1,
            path
            + (GuardCondition(feature, spec.feature_names[feature], ">", threshold),),
        )
        nodes[index] = DecisionNode(
            index,
            len(items),
            counts,
            prediction,
            feature,
            threshold,
            left_index,
            right_index,
            None,
        )
        return index

    grow(examples, 0, ())
    training_digest = _hash(
        (
            spec.feature_names,
            tuple((item.case_id, item.features, item.target) for item in examples),
        )
    )
    value = DecisionTree(
        spec.feature_names,
        tuple(item.case_id for item in examples),
        training_digest,
        tuple(nodes),
        tuple(guards),
        sum(guard.correct_training_examples for guard in guards),
        len(examples),
        evaluations,
        "resource_limit" if limited else "fitted",
    )
    issues = (
        (
            ComputeIssue(
                "decision_split_limit",
                "Some nodes retain majority leaves; the requested tree search was interrupted",
            ),
        )
        if limited
        else ()
    )
    return _result(
        operator,
        source,
        request,
        value,
        issues,
        parents,
        ComputeStatus.PARTIAL if limited else ComputeStatus.COMPUTED,
    )


@dataclass(frozen=True, slots=True)
class DecisionPrediction:
    case_id: str
    prediction: str
    leaf_id: int
    training_class_counts: tuple[tuple[str, int], ...]


def predict_decision_tree(
    model: DecisionTree, vectors: tuple[CaseVector, ...]
) -> tuple[DecisionPrediction, ...]:
    """Apply a fixed trained tree without changing vocabulary or split points."""
    if not isinstance(model, DecisionTree):
        raise TypeError("model must be DecisionTree")
    if not isinstance(vectors, tuple) or not all(
        isinstance(item, CaseVector) for item in vectors
    ):
        raise TypeError("vectors must be a tuple of CaseVector")
    if len({item.case_id for item in vectors}) != len(vectors):
        raise ValueError("prediction case IDs must be unique")
    if not model.nodes or any(
        node.id != index for index, node in enumerate(model.nodes)
    ):
        raise ValueError("tree node IDs must match their contiguous storage indices")
    for node in model.nodes:
        if node.feature_index is None:
            if (
                node.left is not None
                or node.right is not None
                or node.threshold is not None
            ):
                raise ValueError("leaf nodes cannot contain split fields")
        elif (
            type(node.feature_index) is not int
            or not 0 <= node.feature_index < len(model.feature_names)
            or type(node.left) is not int
            or type(node.right) is not int
            or not 0 <= node.left < len(model.nodes)
            or not 0 <= node.right < len(model.nodes)
        ):
            raise ValueError("tree has invalid split indices")
        else:
            _real(node.threshold, "threshold")
    result = []
    for item in vectors:
        if len(item.values) != len(model.feature_names):
            raise ValueError("prediction dimensions differ from the training schema")
        node = model.nodes[0]
        visited = set()
        while node.feature_index is not None:
            if node.id in visited:
                raise ValueError("tree contains a cycle")
            visited.add(node.id)
            node = model.nodes[
                node.left
                if item.values[node.feature_index] <= node.threshold
                else node.right
            ]
        result.append(
            DecisionPrediction(
                item.case_id, node.prediction, node.id, node.class_counts
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True)
class BoseDriftSpec:
    """Eventually-follows Relation Type Counts and adjacent-window tests.

    Cases use supplied source order, not inferred chronology. Alphabet is fitted
    to the complete analysis population, making this an offline diagnostic.
    Exact tests enumerate labelled subset assignments; Monte Carlo uses a local
    fixed seed and (extreme+1)/(samples+1), unlike PM's uncorrected estimator.
    p-values are unadjusted across overlapping windows, not causal evidence.
    """

    sublog_size: int = 50
    window_size: int = 8
    permutation_mode: Literal["exact", "monte_carlo"] = "exact"
    permutations: int = 999
    seed: int = 0
    threshold: int | float = 0.05
    max_points: int = 5
    keep_leftover: bool = True
    max_permutation_evaluations: int = 1_000_000
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    def __post_init__(self):
        for name in (
            "sublog_size",
            "window_size",
            "permutations",
            "max_permutation_evaluations",
        ):
            _int(getattr(self, name), name, 1)
        _int(self.max_points, "max_points")
        if type(self.seed) is not int:
            raise TypeError("seed must be int")
        if self.permutation_mode not in ("exact", "monte_carlo"):
            raise ValueError("unknown permutation mode")
        if type(self.keep_leftover) is not bool:
            raise TypeError("keep_leftover must be bool")
        _real(self.threshold, "threshold")
        if not 0 <= self.threshold <= 1:
            raise ValueError("threshold must be between zero and one")


@dataclass(frozen=True, slots=True)
class RelationCountSublog:
    case_ids: tuple[str, ...]
    feature_values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DriftWindow:
    boundary_sublog_index: int
    boundary_case_index: int
    boundary_case_id: str
    squared_mean_distance: RationalValue
    p_value: RationalValue
    permutations_evaluated: int
    selected: bool


@dataclass(frozen=True, slots=True)
class BoseDriftAnalysis:
    activities: tuple[str, ...]
    feature_columns: tuple[tuple[str, str], ...]
    sublogs: tuple[RelationCountSublog, ...]
    windows: tuple[DriftWindow, ...]
    selected_boundaries: tuple[int, ...]
    omitted_case_ids: tuple[str, ...]
    p_value_adjustment: str


def _relation_counts(words, alphabet):
    occurrence, follows = Counter(), Counter()
    for word in words:
        occurrence.update(set(word))
        pairs, seen = set(), set()
        for activity in word:
            pairs.update((prior, activity) for prior in seen)
            seen.add(activity)
        follows.update(pairs)
    values = []
    for target in alphabet:
        always = sum(
            occurrence[source] > 0 and follows[source, target] == occurrence[source]
            for source in alphabet
        )
        sometimes = sum(
            0 < follows[source, target] < occurrence[source] for source in alphabet
        )
        values.extend((always, sometimes, len(alphabet) - always - sometimes))
    return tuple(values)


def _mean_difference(vectors, selected):
    indices = set(selected)
    n, remainder = len(indices), len(vectors) - len(indices)
    return sum(
        (
            Fraction(sum(vectors[i][column] for i in indices), n)
            - Fraction(
                sum(
                    vector[column]
                    for i, vector in enumerate(vectors)
                    if i not in indices
                ),
                remainder,
            )
        )
        ** 2
        for column in range(len(vectors[0]))
    )


def detect_bose_drift(
    log, spec: BoseDriftSpec = BoseDriftSpec()
) -> ComputationResult[BoseDriftAnalysis]:
    """RC-feature permutation diagnostic inspired by the Bose profile.

    Returns all evaluated windows with feature and boundary witnesses. No drift
    'truth', detection power, family-wise error guarantee or change timestamp is
    inferred from a p-value. A repeated identical population gives p=1.
    """
    if not isinstance(spec, BoseDriftSpec):
        raise TypeError("spec must be BoseDriftSpec")
    traces, operator = _traces(log), "pix.case_centric.detect_bose_drift"
    failure = _unusable(traces, operator, spec)
    if failure:
        return failure
    words = _words(traces)
    source, parents = traces.source_digest, (traces.computation_id,)
    alphabet = tuple(sorted({activity for _, word in words for activity in word}))
    chunks = [
        words[i : i + spec.sublog_size] for i in range(0, len(words), spec.sublog_size)
    ]
    omitted = ()
    if chunks and len(chunks[-1]) < spec.sublog_size and not spec.keep_leftover:
        omitted = tuple(case_id for case_id, _ in chunks.pop())
    sublogs = tuple(
        RelationCountSublog(
            tuple(case_id for case_id, _ in chunk),
            _relation_counts((word for _, word in chunk), alphabet),
        )
        for chunk in chunks
    )
    count = max(0, len(sublogs) - 2 * spec.window_size + 1)
    if count == 0:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "insufficient_drift_windows",
                    "Two complete adjacent windows are required",
                ),
            ),
            parents=parents,
        )
    per_window = (
        comb(2 * spec.window_size, spec.window_size)
        if spec.permutation_mode == "exact"
        else spec.permutations
    )
    if per_window * count > spec.max_permutation_evaluations:
        return _result(
            operator,
            source,
            spec,
            issues=(
                ComputeIssue(
                    "drift_permutation_limit",
                    "No p-values were computed under the requested budget",
                ),
            ),
            parents=parents,
        )
    rows = []
    rng = Random(spec.seed)
    for boundary in range(spec.window_size, len(sublogs) - spec.window_size + 1):
        vectors = tuple(
            item.feature_values
            for item in sublogs[
                boundary - spec.window_size : boundary + spec.window_size
            ]
        )
        observed = Fraction(_mean_difference(vectors, range(spec.window_size)))
        assignments = (
            combinations(range(len(vectors)), spec.window_size)
            if spec.permutation_mode == "exact"
            else (
                tuple(rng.sample(range(len(vectors)), spec.window_size))
                for _ in range(spec.permutations)
            )
        )
        extreme = sum(
            _mean_difference(vectors, selected) >= observed for selected in assignments
        )
        p_value = (
            Fraction(extreme, per_window)
            if spec.permutation_mode == "exact"
            else Fraction(extreme + 1, per_window + 1)
        )
        rows.append(
            DriftWindow(
                boundary,
                boundary * spec.sublog_size,
                sublogs[boundary].case_ids[0],
                _rational(observed),
                _rational(p_value),
                per_window,
                False,
            )
        )
    ranked = sorted(
        (row for row in rows if row.p_value.as_fraction() < Fraction(spec.threshold)),
        key=lambda row: (row.p_value.as_fraction(), row.boundary_sublog_index),
    )[: spec.max_points]
    selected = {row.boundary_sublog_index for row in ranked}
    rows = tuple(
        DriftWindow(
            row.boundary_sublog_index,
            row.boundary_case_index,
            row.boundary_case_id,
            row.squared_mean_distance,
            row.p_value,
            row.permutations_evaluated,
            row.boundary_sublog_index in selected,
        )
        for row in rows
    )
    value = BoseDriftAnalysis(
        alphabet,
        tuple(
            (activity, relation)
            for activity in alphabet
            for relation in ("always", "sometimes", "never")
        ),
        sublogs,
        rows,
        tuple(sorted(selected)),
        omitted,
        "none",
    )
    return _result(operator, source, spec, value, parents=parents)


RESULT_SCHEMAS = {
    "pix.case_centric.cluster_cases": (
        "case_clustering",
        ClusteringRequest,
        CaseClustering,
    ),
    "pix.case_centric.cluster_case_attribute_groups": (
        "case_attribute_clustering",
        CaseAttributeClusteringSpec,
        CaseAttributeClustering,
    ),
    "pix.case_centric.cluster_case_profiles": (
        "case_profile_clustering",
        CaseProfileClusteringSpec,
        CaseProfileClustering,
    ),
    "pix.case_centric.retrieve_similar_cases": (
        "case_retrieval",
        CaseRetrievalRequest,
        CaseRetrieval,
    ),
    "pix.case_centric.compare_stochastic_languages": (
        "case_language_distance",
        LanguageDistanceRequest,
        LanguageDistance,
    ),
    "pix.case_centric.mine_decision_tree": (
        "case_decision_tree",
        DecisionTreeRequest,
        DecisionTree,
    ),
    "pix.case_centric.detect_bose_drift": (
        "case_bose_drift",
        BoseDriftSpec,
        BoseDriftAnalysis,
    ),
}

__all__ = (
    "CaseVector",
    "CaseClusteringSpec",
    "ClusteringRequest",
    "ClusterMerge",
    "CaseClustering",
    "cluster_cases",
    "CaseAttributeClusteringSpec",
    "CaseAttributeGroup",
    "CaseAttributeClustering",
    "cluster_case_attribute_groups",
    "CaseProfileClusteringSpec",
    "ProfileColumn",
    "CaseProfileCluster",
    "CaseProfileClustering",
    "cluster_case_profiles",
    "CaseRetrievalSpec",
    "CaseRetrievalRequest",
    "CaseNeighbor",
    "RetrievedCase",
    "CaseRetrieval",
    "retrieve_similar_cases",
    "RationalValue",
    "LanguageEntry",
    "StochasticLanguage",
    "LanguageDistanceSpec",
    "LanguageDistanceRequest",
    "TransportFlow",
    "LanguageDistance",
    "compare_stochastic_languages",
    "DecisionExample",
    "DecisionTreeSpec",
    "DecisionTreeRequest",
    "DecisionNode",
    "GuardCondition",
    "DecisionGuard",
    "DecisionTree",
    "DecisionPrediction",
    "mine_decision_tree",
    "predict_decision_tree",
    "BoseDriftSpec",
    "RelationCountSublog",
    "DriftWindow",
    "BoseDriftAnalysis",
    "detect_bose_drift",
)
