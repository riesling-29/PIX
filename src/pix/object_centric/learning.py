"""Native numeric support for object-centric predictive monitoring.

K means distinct timestamp groups, not an invented total order of tied events.
Within a group numeric observations are averaged only when every selected cell
is observed. Targets are strictly after the last input timestamp. Entity-disjoint
evaluation is not a claim of causal independence: upstream global-context
features and retrospective execution discovery still require domain review.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import fsum, hypot, isfinite
from typing import ClassVar

from pix.compute._common import _derived_result
from pix.contracts.result import (
    ComputationResult,
    ComputeIssue,
    ComputeStatus,
    computation_identity,
)
from pix.object_centric.features import (
    ObjectFeature,
    ObjectFeatureCell,
    ObjectFeatureEncodedTable,
    ObjectFeatureEncoder,
    ObjectFeatureFitSpec,
    ObjectFeaturePartition,
    ObjectFeatureTable,
    _table,
)


def _ids(value, name, *, nonempty=False):
    if (
        not isinstance(value, tuple)
        or (nonempty and not value)
        or not all(isinstance(v, str) and v for v in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{name} must contain unique nonempty string IDs")


def _indices(value, name):
    if (
        not isinstance(value, tuple)
        or not value
        or not all(type(v) is int and v >= 0 for v in value)
        or len(set(value)) != len(value)
    ):
        raise ValueError(f"{name} must contain unique nonnegative indices")


def _masked(values, reasons):
    if not isinstance(values, tuple) or not isinstance(reasons, tuple):
        raise TypeError("values and reasons must be tuples")
    if len(values) != len(reasons):
        raise ValueError("value and missingness dimensions differ")
    for value, reason in zip(values, reasons):
        if value is None:
            if not isinstance(reason, str) or not reason:
                raise ValueError("missing numeric values require a reason")
        elif type(value) is not float or not isfinite(value) or reason is not None:
            raise ValueError("observed values must be finite floats without a reason")


def _aware(time):
    return (
        isinstance(time, datetime)
        and time.tzinfo is not None
        and time.utcoffset() is not None
    )


def _expected(result, operator, kind):
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id != operator
        or not isinstance(result.value, kind)
    ):
        raise TypeError(f"expected successful {operator} result")
    return result.value


def _output(operator, source, spec, parents, value=None, issues=(), status=None):
    result = _derived_result(
        operator,
        source.source_digest,
        spec,
        status or (ComputeStatus.PARTIAL if issues else ComputeStatus.COMPUTED),
        value,
        tuple(issues),
        parent_computation_ids=tuple(parent.computation_id for parent in parents),
    )
    validate_learning_result(result)
    return result


def _failure(operator, source, spec, parents, code, message, *, unavailable=False):
    return _output(
        operator,
        source,
        spec,
        parents,
        issues=(ComputeIssue(code, message),),
        status=ComputeStatus.UNAVAILABLE
        if unavailable
        else ComputeStatus.INVALID_INPUT,
    )


@dataclass(frozen=True, slots=True)
class ObjectKStepSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.k_step_dataset.spec"
    k: int
    input_feature_indices: tuple[int, ...]
    target_feature_indices: tuple[int, ...]
    horizon: int = 1
    padding: str = "none"

    def __post_init__(self):
        for name in ("k", "horizon"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        _indices(self.input_feature_indices, "input_feature_indices")
        _indices(self.target_feature_indices, "target_feature_indices")
        if self.padding not in ("none", "left_unknown"):
            raise ValueError("padding must be none or left_unknown")


@dataclass(frozen=True, slots=True)
class ObjectFeatureStep:
    time: datetime | None
    row_ids: tuple[str, ...]
    event_ids: tuple[str, ...]
    values: tuple[float | None, ...]
    reasons: tuple[str | None, ...]
    padded: bool = False

    def __post_init__(self):
        _ids(self.row_ids, "row_ids")
        _ids(self.event_ids, "event_ids")
        _masked(self.values, self.reasons)
        if type(self.padded) is not bool:
            raise TypeError("padded must be Boolean")
        if self.padded:
            if (
                self.time is not None
                or self.row_ids
                or self.event_ids
                or any(v is not None for v in self.values)
            ):
                raise ValueError("padding cannot contain observed rows or values")
        elif not _aware(self.time) or not self.row_ids:
            raise ValueError("an observed step requires timestamp and row identities")


@dataclass(frozen=True, slots=True)
class ObjectKStepSample:
    sample_id: str
    execution_id: str
    inputs: tuple[ObjectFeatureStep, ...]
    target_time: datetime
    target_row_ids: tuple[str, ...]
    targets: tuple[float | None, ...]
    target_reasons: tuple[str | None, ...]
    event_members: tuple[str, ...]
    object_members: tuple[str, ...]
    partition: str = "unassigned"

    def __post_init__(self):
        _ids((self.sample_id,), "sample_id", nonempty=True)
        _ids((self.execution_id,), "execution_id", nonempty=True)
        if (
            not isinstance(self.inputs, tuple)
            or not self.inputs
            or not all(isinstance(v, ObjectFeatureStep) for v in self.inputs)
        ):
            raise ValueError("nonempty input step tuple required")
        _ids(self.target_row_ids, "target_row_ids", nonempty=True)
        _ids(self.event_members, "event_members")
        _ids(self.object_members, "object_members")
        _masked(self.targets, self.target_reasons)
        if not _aware(self.target_time):
            raise ValueError("target_time must have a timezone")
        observed = [step.time for step in self.inputs if not step.padded]
        if (
            not observed
            or observed != sorted(set(observed))
            or observed[-1] >= self.target_time
        ):
            raise ValueError("inputs must precede targets in strict timestamp order")
        if any(step.padded for step in self.inputs[len(self.inputs) - len(observed) :]):
            raise ValueError("padding must precede observed steps")
        if self.partition not in ("train", "test", "unassigned"):
            raise ValueError("invalid sample partition")
        input_ids = tuple(key for step in self.inputs for key in step.row_ids)
        _ids(input_ids, "input row IDs")
        if set(input_ids) & set(self.target_row_ids):
            raise ValueError("input and future target row identities must be disjoint")


@dataclass(frozen=True, slots=True)
class ObjectLearningScope:
    """Complete execution scope, stored once rather than copied into each window."""

    execution_id: str
    event_ids: tuple[str, ...]
    object_ids: tuple[str, ...]

    def __post_init__(self):
        _ids((self.execution_id,), "execution_id")
        _ids(self.event_ids, "event_ids")
        _ids(self.object_ids, "object_ids")


@dataclass(frozen=True, slots=True)
class ObjectKStepDataset:
    features: tuple[ObjectFeature, ...]
    definition_id: str
    schema_id: str
    k: int
    horizon: int
    input_feature_indices: tuple[int, ...]
    target_feature_indices: tuple[int, ...]
    padding: str
    samples: tuple[ObjectKStepSample, ...]
    execution_scopes: tuple[ObjectLearningScope, ...]
    excluded_row_ids: tuple[str, ...]
    unknown_input_count: int
    unknown_target_count: int
    profile: str = "strict_timestamp_groups_strict_numeric_mean"

    def __post_init__(self):
        ObjectKStepSpec(
            self.k,
            self.input_feature_indices,
            self.target_feature_indices,
            self.horizon,
            self.padding,
        )
        if not isinstance(self.features, tuple) or not all(
            isinstance(f, ObjectFeature) for f in self.features
        ):
            raise TypeError("features must be an ObjectFeature tuple")
        if max(self.input_feature_indices + self.target_feature_indices) >= len(
            self.features
        ):
            raise ValueError("feature index exceeds named feature schema")
        if not isinstance(self.samples, tuple) or not all(
            isinstance(s, ObjectKStepSample) for s in self.samples
        ):
            raise TypeError("samples must be an ObjectKStepSample tuple")
        _ids(tuple(s.sample_id for s in self.samples), "sample_ids")
        _ids(self.excluded_row_ids, "excluded_row_ids")
        for name in ("unknown_input_count", "unknown_target_count"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not isinstance(self.execution_scopes, tuple) or not all(
            isinstance(scope, ObjectLearningScope) for scope in self.execution_scopes
        ):
            raise TypeError("execution_scopes must contain ObjectLearningScope values")
        _ids(
            tuple(scope.execution_id for scope in self.execution_scopes),
            "execution scope IDs",
        )
        scope_ids = {scope.execution_id for scope in self.execution_scopes}
        scope_map = {scope.execution_id: scope for scope in self.execution_scopes}
        for sample in self.samples:
            if sample.execution_id not in scope_ids:
                raise ValueError(
                    "every sample must retain its complete execution scope"
                )
            scope = scope_map[sample.execution_id]
            if set(sample.event_members) - set(scope.event_ids) or set(
                sample.object_members
            ) - set(scope.object_ids):
                raise ValueError(
                    "sample members must belong to complete execution scope"
                )
            if (
                len(sample.inputs) != self.k
                or len(sample.targets) != len(self.target_feature_indices)
                or any(
                    len(step.values) != len(self.input_feature_indices)
                    for step in sample.inputs
                )
            ):
                raise ValueError("sample dimensions differ from feature schema")
        if self.unknown_input_count != sum(
            v is None for s in self.samples for step in s.inputs for v in step.values
        ):
            raise ValueError("incorrect unknown input count")
        if self.unknown_target_count != sum(
            v is None for s in self.samples for v in s.targets
        ):
            raise ValueError("incorrect unknown target count")


@dataclass(frozen=True, slots=True)
class _KStepSchema:
    features: tuple[ObjectFeature, ...]
    granularity: str
    profile: str
    window: ObjectKStepSpec


def _scope(table, rows):
    executions = {r.execution_id for r in rows if r.execution_id is not None}
    events = {v for row in rows for v in row.event_members}
    objects = {v for row in rows for v in row.object_members}
    for graph in table.graphs:
        if graph.execution_id in executions:
            events.update(graph.event_ids)
            objects.update(graph.object_ids)
    return executions, events, objects


def _group_values(rows, indices):
    values, reasons = [], []
    for index in indices:
        cells = [r.cells[index] for r in rows]
        if any(c.kind == "unknown" for c in cells):
            values.append(None)
            reasons.append("group_contains_unknown")
            continue
        if any(c.kind not in ("integer", "real") for c in cells):
            values.append(None)
            reasons.append("numeric_observations_required")
            continue
        try:
            numbers = [
                float(c.integer if c.kind == "integer" else c.real) for c in cells
            ]
            value = fsum(v / len(numbers) for v in numbers)
            if not isfinite(value):
                raise OverflowError
        except (OverflowError, ValueError):
            value, reason = None, "non_finite_group_mean"
        else:
            reason = None
        values.append(value)
        reasons.append(reason)
    return tuple(values), tuple(reasons)


def build_object_k_step_dataset(
    result: ComputationResult[ObjectFeatureTable],
    spec: ObjectKStepSpec,
    *,
    partition: ComputationResult[ObjectFeaturePartition] | None = None,
) -> ComputationResult[ObjectKStepDataset]:
    """Create sliding k-group windows and horizon-separated numeric targets.

    Ties remain one timestamp group with all row/event identities. No padding is
    the default; optional left padding is explicitly unknown and masked. The
    same feature may appear as a historical input and a future target. A cell
    already marked as retrospective ``target`` can never enter an input window.
    """
    if not isinstance(spec, ObjectKStepSpec):
        raise TypeError("invalid k-step spec")
    table = _table(result)
    operator = "pix.object_centric.k_step_dataset"
    parents = (result,) if partition is None else (result, partition)

    def invalid(code, message):
        return _failure(operator, result, spec, parents, code, message)

    if max(spec.input_feature_indices + spec.target_feature_indices) >= len(
        table.features
    ):
        return invalid(
            "unknown_feature_index", "A selected feature index exceeds source columns."
        )
    if len({r.row_id for r in table.rows}) != len(table.rows) or any(
        len(r.cells) != len(table.features) for r in table.rows
    ):
        return invalid(
            "invalid_feature_dimensions",
            "Rows must have unique IDs and match named columns.",
        )
    roles = {}
    if partition is not None:
        split = _expected(
            partition, "pix.object_centric.feature_split", ObjectFeaturePartition
        )
        if (
            partition.source_digest != result.source_digest
            or result.computation_id not in partition.parent_computation_ids
        ):
            return invalid(
                "partition_source_mismatch",
                "Partition must derive from this exact feature table.",
            )
        train, test = set(split.train_row_ids), set(split.test_row_ids)
        if train & test or train | test != {r.row_id for r in table.rows}:
            return invalid(
                "invalid_partition_rows",
                "Train/test must partition the source rows exactly once.",
            )
        left = _scope(table, [r for r in table.rows if r.row_id in train])
        right = _scope(table, [r for r in table.rows if r.row_id in test])
        if any(a & b for a, b in zip(left, right)):
            return invalid(
                "partition_entity_leakage",
                "Train and test share executions, events or boundary objects.",
            )
        roles = {r: "train" for r in train} | {r: "test" for r in test}
    grouped = defaultdict(lambda: defaultdict(list))
    excluded, issues = [], []
    for row in table.rows:
        if not _aware(row.time) or not row.execution_id:
            excluded.append(row.row_id)
            continue
        grouped[row.execution_id][row.time].append(row)
    if excluded:
        issues.append(
            ComputeIssue(
                "sequence_identity_or_time_missing",
                "Rows without execution identity or aware time cannot form temporal samples.",
                tuple(sorted(excluded)),
            )
        )
    samples, scopes = [], []
    graph_events, graph_objects = defaultdict(set), defaultdict(set)
    for graph in table.graphs:
        graph_events[graph.execution_id].update(graph.event_ids)
        graph_objects[graph.execution_id].update(graph.object_ids)
    for execution, timestamps in sorted(grouped.items()):
        groups = [
            tuple(sorted(rows, key=lambda row: row.row_id))
            for _, rows in sorted(timestamps.items())
        ]
        all_rows = [row for group in groups for row in group]
        events = {v for row in all_rows for v in row.event_members}
        objects = {v for row in all_rows for v in row.object_members}
        events.update(graph_events[execution])
        objects.update(graph_objects[execution])
        scopes.append(
            ObjectLearningScope(
                execution, tuple(sorted(events)), tuple(sorted(objects))
            )
        )
        for end in range(len(groups) - spec.horizon):
            start = end - spec.k + 1
            if start < 0 and spec.padding == "none":
                continue
            selected = groups[max(0, start) : end + 1]
            if any(
                row.cells[i].role == "target"
                for group in selected
                for row in group
                for i in spec.input_feature_indices
            ):
                return invalid(
                    "target_in_input_window",
                    "Retrospective target-role cells cannot be predictive inputs.",
                )
            steps = [
                ObjectFeatureStep(
                    None,
                    (),
                    (),
                    (None,) * len(spec.input_feature_indices),
                    ("left_padding",) * len(spec.input_feature_indices),
                    True,
                )
                for _ in range(max(0, -start))
            ]
            for rows in selected:
                values, reasons = _group_values(rows, spec.input_feature_indices)
                steps.append(
                    ObjectFeatureStep(
                        rows[0].time,
                        tuple(r.row_id for r in rows),
                        tuple(
                            sorted({r.event_id for r in rows if r.event_id is not None})
                        ),
                        values,
                        reasons,
                    )
                )
            target = groups[end + spec.horizon]
            values, reasons = _group_values(target, spec.target_feature_indices)
            target_ids = tuple(r.row_id for r in target)
            identity = (
                execution,
                tuple(step.row_ids for step in steps),
                target_ids,
                spec.input_feature_indices,
                spec.target_feature_indices,
                spec.horizon,
                spec.padding,
            )
            sample_id = sha256(repr(identity).encode("utf-8")).hexdigest()
            window_rows = [row for group in selected for row in group] + list(target)
            samples.append(
                ObjectKStepSample(
                    sample_id,
                    execution,
                    tuple(steps),
                    target[0].time,
                    target_ids,
                    values,
                    reasons,
                    tuple(
                        sorted({v for row in window_rows for v in row.event_members})
                    ),
                    tuple(
                        sorted({v for row in window_rows for v in row.object_members})
                    ),
                    roles.get(target_ids[0], "unassigned"),
                )
            )
    unknown_inputs = sum(
        v is None for s in samples for step in s.inputs for v in step.values
    )
    unknown_targets = sum(v is None for s in samples for v in s.targets)
    if unknown_inputs or unknown_targets:
        issues.append(
            ComputeIssue(
                "unknown_dataset_values",
                f"{unknown_inputs} input and {unknown_targets} target values remain unknown; no imputation.",
            )
        )
    if not samples:
        issues.append(
            ComputeIssue(
                "no_k_step_samples",
                "No execution contains an eligible input and future target window.",
            )
        )
    schema_id = computation_identity(
        "pix.object_centric.k_step_schema",
        "1.0.0",
        "feature-schema",
        _KStepSchema(table.features, table.granularity, table.profile, spec),
        (table.definition_id,),
    )
    value = ObjectKStepDataset(
        table.features,
        table.definition_id,
        schema_id,
        spec.k,
        spec.horizon,
        spec.input_feature_indices,
        spec.target_feature_indices,
        spec.padding,
        tuple(samples),
        tuple(scopes),
        tuple(sorted(excluded)),
        unknown_inputs,
        unknown_targets,
    )
    return _output(operator, result, spec, parents, value, issues)


@dataclass(frozen=True, slots=True)
class ObjectFeatureInverseSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.feature_inverse.spec"
    row_ids: tuple[str, ...] | None = None

    def __post_init__(self):
        if self.row_ids is not None:
            _ids(self.row_ids, "row_ids")


@dataclass(frozen=True, slots=True)
class ObjectFeatureInverseRow:
    row_id: str
    cells: tuple[ObjectFeatureCell, ...]

    def __post_init__(self):
        _ids((self.row_id,), "row_id")
        if not isinstance(self.cells, tuple) or not all(
            isinstance(c, ObjectFeatureCell) for c in self.cells
        ):
            raise TypeError("cells must be an ObjectFeatureCell tuple")


@dataclass(frozen=True, slots=True)
class ObjectFeatureInverseTable:
    features: tuple[ObjectFeature, ...]
    definition_id: str
    rows: tuple[ObjectFeatureInverseRow, ...]
    unknown_value_count: int
    excluded_target_count: int
    profile: str = "numeric_float_reconstruction_frozen_training_statistics"

    def __post_init__(self):
        if not isinstance(self.features, tuple) or not all(
            isinstance(f, ObjectFeature) for f in self.features
        ):
            raise TypeError("features must be an ObjectFeature tuple")
        if not isinstance(self.rows, tuple) or not all(
            isinstance(r, ObjectFeatureInverseRow) for r in self.rows
        ):
            raise TypeError("rows must be an inverse row tuple")
        _ids(tuple(row.row_id for row in self.rows), "row_ids")
        if any(len(row.cells) != len(self.features) for row in self.rows):
            raise ValueError("inverse row dimensions differ from named features")
        if self.unknown_value_count != sum(
            c.kind == "unknown" and c.role == "input"
            for row in self.rows
            for c in row.cells
        ):
            raise ValueError("incorrect unknown inverse value count")
        if self.excluded_target_count != sum(
            c.role == "target" for row in self.rows for c in row.cells
        ):
            raise ValueError("incorrect excluded target count")


def inverse_transform_object_features(
    encoded: ComputationResult[ObjectFeatureEncodedTable],
    fitted: ComputationResult[ObjectFeatureEncoder],
    spec: ObjectFeatureInverseSpec = ObjectFeatureInverseSpec(),
) -> ComputationResult[ObjectFeatureInverseTable]:
    """Undo frozen training transforms; numeric reconstruction returns floats.

    Original integer dtype/precision is not retained by the existing encoder.
    Excluded targets stay excluded. One-hot and ordinal categories are decoded
    only when their representations are unambiguous; no guessing or refitting.
    """
    if not isinstance(spec, ObjectFeatureInverseSpec):
        raise TypeError("invalid inverse transform spec")
    table = _expected(
        encoded, "pix.object_centric.feature_transform", ObjectFeatureEncodedTable
    )
    encoder = _expected(fitted, "pix.object_centric.feature_fit", ObjectFeatureEncoder)
    operator, parents = "pix.object_centric.feature_inverse", (encoded, fitted)

    def invalid(code, message):
        return _failure(operator, encoded, spec, parents, code, message)

    if len(encoder.columns) != len(encoder.features) or tuple(
        m.feature_index for m in encoder.columns
    ) != tuple(range(len(encoder.features))):
        return invalid(
            "invalid_encoder_dimensions",
            "Encoder must have one ordered model per original feature.",
        )
    for model in encoder.columns:
        if model.mode not in (
            "numeric",
            "categorical",
            "target_excluded",
            "unavailable",
        ):
            return invalid(
                "invalid_encoder_mode", "Encoder column mode is unsupported."
            )
        if model.mode == "numeric" and (
            type(model.mean) not in (float, int)
            or type(model.scale) not in (float, int)
            or not isfinite(model.mean)
            or not isfinite(model.scale)
            or model.scale < 0
        ):
            return invalid(
                "invalid_numeric_encoder",
                "Numeric encoder requires finite mean and nonnegative scale.",
            )
        if model.mode == "categorical" and (
            model.category_encoding not in ("one_hot", "ordinal")
            or not model.categories
            or not isinstance(model.categories, tuple)
            or any(
                not isinstance(v, str)
                or not (v.startswith("text:") or v in ("boolean:true", "boolean:false"))
                for v in model.categories
            )
            or len(set(model.categories)) != len(model.categories)
        ):
            return invalid(
                "invalid_categorical_encoder",
                "Categorical encoder requires unique typed categories and one_hot or ordinal encoding.",
            )
    if (
        not isinstance(fitted.spec, ObjectFeatureFitSpec)
        or fitted.spec.train_row_ids != encoder.train_row_ids
        or any(
            model.mode == "categorical"
            and model.category_encoding != fitted.spec.categorical_encoding
            for model in encoder.columns
        )
    ):
        return invalid(
            "encoder_fit_metadata_mismatch",
            "Encoder training identities and category policy must match its request.",
        )
    columns = tuple(
        (m.feature_index, category)
        for m in encoder.columns
        for category in (
            m.categories
            if m.mode == "categorical" and m.category_encoding == "one_hot"
            else (None,)
        )
    )
    if (
        len(encoded.parent_computation_ids) != 2
        or fitted.computation_id != encoded.parent_computation_ids[1]
        or encoder.train_row_ids != table.train_row_ids
        or columns != table.columns
    ):
        return invalid(
            "encoder_transform_mismatch",
            "Encoded columns and training identity must match the exact fitted encoder.",
        )
    ids = {row.row_id for row in table.rows}
    if len(ids) != len(table.rows) or (
        spec.row_ids is not None and set(spec.row_ids) - ids
    ):
        return invalid(
            "unknown_inverse_row",
            "Selected rows must be unique and present in the encoded table.",
        )
    output, unknown, excluded = [], 0, 0
    for row in table.rows:
        if len(row.values) != len(columns) or len(row.reasons) != len(columns):
            return invalid(
                "invalid_encoded_dimensions",
                "Encoded values/reasons must match named output columns.",
            )
        try:
            _masked(row.values, row.reasons)
        except (ValueError, TypeError):
            return invalid(
                "invalid_encoded_values",
                "Encoded values must be finite and preserve explicit missingness.",
            )
        if spec.row_ids is not None and row.row_id not in spec.row_ids:
            continue
        cells, offset = [], 0
        for model in encoder.columns:
            width = (
                len(model.categories)
                if model.mode == "categorical" and model.category_encoding == "one_hot"
                else 1
            )
            values, reasons = (
                row.values[offset : offset + width],
                row.reasons[offset : offset + width],
            )
            offset += width
            reason, cell = None, None
            if model.mode == "target_excluded" or "target_excluded" in reasons:
                cells.append(
                    ObjectFeatureCell("unknown", "target", reason="target_excluded")
                )
                excluded += 1
                continue
            if any(v is None for v in values):
                reason = next(reason for reason in reasons if reason is not None)
            elif model.mode == "numeric":
                if (
                    model.mean is None
                    or model.scale is None
                    or not isfinite(model.mean)
                    or not isfinite(model.scale)
                    or model.scale < 0
                ):
                    return invalid(
                        "invalid_numeric_encoder",
                        "Numeric encoder requires finite mean and nonnegative scale.",
                    )
                value = values[0] * (model.scale or 1.0) + model.mean
                if isfinite(value):
                    cell = ObjectFeatureCell("real", real=float(value))
                else:
                    reason = "non_finite_inverse"
            elif model.mode == "categorical":
                if model.category_encoding == "one_hot":
                    index = (
                        values.index(1.0)
                        if values
                        and all(v in (0.0, 1.0) for v in values)
                        and sum(values) == 1.0
                        else None
                    )
                else:
                    index = (
                        int(values[0])
                        if values
                        and values[0] == int(values[0])
                        and 0 <= values[0] < len(model.categories)
                        else None
                    )
                if index is None:
                    reason = "ambiguous_categorical_inverse"
                else:
                    category = model.categories[index]
                    if category.startswith("text:"):
                        cell = ObjectFeatureCell("text", text=category[5:])
                    elif category in ("boolean:true", "boolean:false"):
                        cell = ObjectFeatureCell(
                            "boolean", boolean=category == "boolean:true"
                        )
                    else:
                        reason = "unsupported_category_type"
            else:
                reason = "encoder_column_unavailable"
            if cell is None:
                cell = ObjectFeatureCell(
                    "unknown", reason=reason or "inverse_unavailable"
                )
                unknown += 1
            cells.append(cell)
        output.append(ObjectFeatureInverseRow(row.row_id, tuple(cells)))
    issues = (
        (
            ComputeIssue(
                "unknown_inverse_values",
                f"{unknown} input feature values cannot be reconstructed.",
            ),
        )
        if unknown
        else ()
    )
    value = ObjectFeatureInverseTable(
        encoder.features, encoder.definition_id, tuple(output), unknown, excluded
    )
    return _output(operator, encoded, spec, parents, value, issues)


@dataclass(frozen=True, slots=True)
class ObjectRegressionFitSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.regression_fit.spec"
    train_sample_ids: tuple[str, ...]
    fit_intercept: bool = True
    rank_tolerance: float = 1e-12

    def __post_init__(self):
        _ids(self.train_sample_ids, "train_sample_ids", nonempty=True)
        object.__setattr__(
            self, "train_sample_ids", tuple(sorted(self.train_sample_ids))
        )
        if type(self.fit_intercept) is not bool:
            raise TypeError("fit_intercept must be Boolean")
        if (
            type(self.rank_tolerance) not in (float, int)
            or not isfinite(self.rank_tolerance)
            or not 0 < self.rank_tolerance < 1
        ):
            raise ValueError("rank_tolerance must be strictly between zero and one")


@dataclass(frozen=True, slots=True)
class ObjectLinearRegression:
    schema_id: str
    input_columns: tuple[tuple[int, int], ...]
    target_feature_indices: tuple[int, ...]
    coefficients: tuple[tuple[float, ...], ...]
    intercepts: tuple[float, ...]
    train_sample_ids: tuple[str, ...]
    used_sample_ids: tuple[str, ...]
    excluded_sample_ids: tuple[str, ...]
    train_execution_ids: tuple[str, ...]
    train_event_ids: tuple[str, ...]
    train_object_ids: tuple[str, ...]
    rank: int
    parameter_count: int
    fit_intercept: bool
    rank_tolerance: float
    profile: str = "native_scaled_reorthogonalized_qr_complete_case_ols"

    def __post_init__(self):
        for name in (
            "train_sample_ids",
            "used_sample_ids",
            "excluded_sample_ids",
            "train_execution_ids",
            "train_event_ids",
            "train_object_ids",
        ):
            _ids(getattr(self, name), name)
        if set(self.used_sample_ids) & set(self.excluded_sample_ids) or set(
            self.used_sample_ids
        ) | set(self.excluded_sample_ids) != set(self.train_sample_ids):
            raise ValueError(
                "used/excluded samples must partition requested training samples"
            )
        if (
            len(self.coefficients) != len(self.target_feature_indices)
            or len(self.intercepts) != len(self.coefficients)
            or any(len(row) != len(self.input_columns) for row in self.coefficients)
        ):
            raise ValueError("regression coefficient dimensions differ from schema")
        if any(
            type(v) is not float or not isfinite(v)
            for row in self.coefficients
            for v in row
        ) or any(type(v) is not float or not isfinite(v) for v in self.intercepts):
            raise ValueError("regression coefficients must be finite")
        if (
            self.parameter_count != len(self.input_columns) + int(self.fit_intercept)
            or self.rank != self.parameter_count
            or len(self.used_sample_ids) < self.parameter_count
        ):
            raise ValueError("only full-rank determined regressions are available")


def _flatten(sample):
    return tuple(value for step in sample.inputs for value in step.values)


def _sample_scope(table, samples):
    executions = {s.execution_id for s in samples}
    events = {v for s in samples for v in s.event_members}
    objects = {v for s in samples for v in s.object_members}
    for scope in table.execution_scopes:
        if scope.execution_id in executions:
            events.update(scope.event_ids)
            objects.update(scope.object_ids)
    return executions, events, objects


def _qr_solve(x, y, tolerance):
    """Column-scaled, twice orthogonalized QR; reject numerical rank deficiency."""
    columns = [list(column) for column in zip(*x)]
    norms = [hypot(*column) for column in columns]
    if any(not isfinite(norm) for norm in norms):
        raise OverflowError("column norms exceed finite numeric range")
    if any(norm == 0 for norm in norms):
        return None
    q, r = [], [[0.0] * len(columns) for _ in columns]
    for j, column in enumerate(columns):
        vector = [value / norms[j] for value in column]
        for _ in range(2):
            for i, basis in enumerate(q):
                projection = fsum(a * b for a, b in zip(basis, vector))
                r[i][j] += projection
                vector = [a - projection * b for a, b in zip(vector, basis)]
        norm = hypot(*vector)
        if norm <= tolerance or not isfinite(norm):
            return None
        r[j][j] = norm
        q.append([v / norm for v in vector])
    coefficients = []
    for target in zip(*y):
        qty = [fsum(a * b for a, b in zip(basis, target)) for basis in q]
        beta = [0.0] * len(columns)
        for i in reversed(range(len(columns))):
            beta[i] = (
                qty[i] - fsum(r[i][j] * beta[j] for j in range(i + 1, len(columns)))
            ) / r[i][i]
        coefficients.append(tuple(beta[i] / norms[i] for i in range(len(columns))))
    return tuple(coefficients)


def fit_object_regression(
    dataset: ComputationResult[ObjectKStepDataset],
    spec: ObjectRegressionFitSpec,
) -> ComputationResult[ObjectLinearRegression]:
    """Fit explicit training samples only, without automatic scaling/refitting.

    Missing input or target rows are excluded and counted. Rank-deficient or
    underdetermined designs return UNAVAILABLE; no silent pseudoinverse/ridge.
    Targets retain their original units, e.g. microseconds for duration features.
    """
    if not isinstance(spec, ObjectRegressionFitSpec):
        raise TypeError("invalid regression fit spec")
    table = _expected(dataset, "pix.object_centric.k_step_dataset", ObjectKStepDataset)
    operator, parents = "pix.object_centric.regression_fit", (dataset,)

    def fail(code, message, unavailable=False):
        return _failure(
            operator, dataset, spec, parents, code, message, unavailable=unavailable
        )

    rows = {s.sample_id: s for s in table.samples}
    if set(spec.train_sample_ids) - set(rows):
        return fail(
            "unknown_training_sample", "Training sample IDs must belong to the dataset."
        )
    selected = [rows[key] for key in spec.train_sample_ids]
    if any(s.partition == "test" for s in selected):
        return fail("test_sample_in_training", "Held-out samples cannot fit a model.")
    used = [s for s in selected if all(v is not None for v in _flatten(s) + s.targets)]
    used_ids = {s.sample_id for s in used}
    excluded = tuple(s.sample_id for s in selected if s.sample_id not in used_ids)
    columns = tuple(
        (lag - table.k + 1, index)
        for lag in range(table.k)
        for index in table.input_feature_indices
    )
    width = len(columns) + int(spec.fit_intercept)
    if len(used) < width:
        return fail(
            "insufficient_complete_training_samples",
            f"{len(used)} complete samples for {width} parameters; {len(excluded)} excluded.",
            True,
        )
    x = [((1.0,) if spec.fit_intercept else ()) + _flatten(s) for s in used]
    y = [s.targets for s in used]
    try:
        beta = _qr_solve(x, y, spec.rank_tolerance)
    except (OverflowError, ValueError, ZeroDivisionError):
        return fail(
            "non_finite_regression",
            "Numeric range prevents finite native QR regression.",
            True,
        )
    if beta is None:
        return fail(
            "rank_deficient_design",
            "Training design is numerically rank deficient at the requested tolerance.",
            True,
        )
    if any(not isfinite(v) for row in beta for v in row):
        return fail(
            "non_finite_regression",
            "Native QR produced coefficients outside finite numeric range.",
            True,
        )
    coefficients = tuple(row[1:] if spec.fit_intercept else row for row in beta)
    intercepts = tuple(row[0] if spec.fit_intercept else 0.0 for row in beta)
    train_execution_ids, train_event_ids, train_object_ids = _sample_scope(
        table, selected
    )
    value = ObjectLinearRegression(
        table.schema_id,
        columns,
        table.target_feature_indices,
        coefficients,
        intercepts,
        spec.train_sample_ids,
        tuple(s.sample_id for s in used),
        excluded,
        tuple(sorted(train_execution_ids)),
        tuple(sorted(train_event_ids)),
        tuple(sorted(train_object_ids)),
        width,
        width,
        spec.fit_intercept,
        spec.rank_tolerance,
    )
    issues = (
        (
            ComputeIssue(
                "incomplete_training_samples",
                f"Excluded {len(excluded)} samples with missing inputs or targets.",
                excluded,
            ),
        )
        if excluded
        else ()
    )
    return _output(operator, dataset, spec, parents, value, issues)


@dataclass(frozen=True, slots=True)
class ObjectRegressionPredictSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.regression_predict.spec"
    sample_ids: tuple[str, ...]
    allow_training: bool = False

    def __post_init__(self):
        _ids(self.sample_ids, "sample_ids")
        if type(self.allow_training) is not bool:
            raise TypeError("allow_training must be Boolean")


@dataclass(frozen=True, slots=True)
class ObjectRegressionPrediction:
    sample_id: str
    values: tuple[float | None, ...]
    reasons: tuple[str | None, ...]

    def __post_init__(self):
        _ids((self.sample_id,), "sample_id")
        _masked(self.values, self.reasons)


@dataclass(frozen=True, slots=True)
class ObjectRegressionPredictions:
    schema_id: str
    model_computation_id: str
    rows: tuple[ObjectRegressionPrediction, ...]
    target_feature_indices: tuple[int, ...]
    unknown_value_count: int
    entity_disjoint_holdout: bool

    def __post_init__(self):
        if not isinstance(self.rows, tuple) or not all(
            isinstance(r, ObjectRegressionPrediction) for r in self.rows
        ):
            raise TypeError("rows must be a prediction tuple")
        _ids(tuple(r.sample_id for r in self.rows), "sample_ids")
        if any(len(r.values) != len(self.target_feature_indices) for r in self.rows):
            raise ValueError("prediction target dimensions differ")
        if self.unknown_value_count != sum(
            v is None for row in self.rows for v in row.values
        ):
            raise ValueError("incorrect unknown prediction count")
        if type(self.entity_disjoint_holdout) is not bool:
            raise TypeError("entity_disjoint_holdout must be Boolean")


def predict_object_regression(
    dataset: ComputationResult[ObjectKStepDataset],
    fitted: ComputationResult[ObjectLinearRegression],
    spec: ObjectRegressionPredictSpec,
) -> ComputationResult[ObjectRegressionPredictions]:
    """Apply frozen coefficients and check execution/event/object disjointness.

    IDs are treated as globally meaningful across input logs; a shared ID is
    conservatively considered dependence. ``allow_training`` enables diagnostics
    but explicitly disables the held-out MAE contract.
    """
    if not isinstance(spec, ObjectRegressionPredictSpec):
        raise TypeError("invalid prediction spec")
    table = _expected(dataset, "pix.object_centric.k_step_dataset", ObjectKStepDataset)
    model = _expected(
        fitted, "pix.object_centric.regression_fit", ObjectLinearRegression
    )
    operator, parents = "pix.object_centric.regression_predict", (dataset, fitted)

    def invalid(code, message):
        return _failure(operator, dataset, spec, parents, code, message)

    if (
        not isinstance(fitted.spec, ObjectRegressionFitSpec)
        or model.train_sample_ids != fitted.spec.train_sample_ids
        or model.fit_intercept != fitted.spec.fit_intercept
        or model.rank_tolerance != fitted.spec.rank_tolerance
    ):
        return invalid(
            "regression_fit_metadata_mismatch",
            "Model training metadata must agree with its fitted request.",
        )

    columns = tuple(
        (lag - table.k + 1, index)
        for lag in range(table.k)
        for index in table.input_feature_indices
    )
    if (
        model.schema_id != table.schema_id
        or model.input_columns != columns
        or model.target_feature_indices != table.target_feature_indices
    ):
        return invalid(
            "regression_schema_mismatch",
            "Input feature definitions, lag order and target schema must match training.",
        )
    rows = {s.sample_id: s for s in table.samples}
    if set(spec.sample_ids) - set(rows):
        return invalid(
            "unknown_prediction_sample", "Prediction IDs must belong to the dataset."
        )
    selected = [rows[key] for key in spec.sample_ids]
    if not spec.allow_training:
        train_samples, train_exec = (
            set(model.train_sample_ids),
            set(model.train_execution_ids),
        )
        train_events, train_objects = (
            set(model.train_event_ids),
            set(model.train_object_ids),
        )
        executions, events, objects = _sample_scope(table, selected)
        if (
            any(s.sample_id in train_samples for s in selected)
            or train_exec & executions
            or train_events & events
            or train_objects & objects
        ):
            return invalid(
                "prediction_entity_leakage",
                "Held-out prediction shares training sample, execution, event or boundary object identities.",
            )
    output, unknown = [], 0
    for sample in selected:
        x = _flatten(sample)
        values, reasons = [], []
        for intercept, coefficients in zip(model.intercepts, model.coefficients):
            value, reason = None, None
            if any(v is None for v in x):
                reason = "prediction_input_unknown"
            else:
                try:
                    value = fsum((intercept, *(a * b for a, b in zip(coefficients, x))))
                    if not isfinite(value):
                        raise OverflowError
                except (OverflowError, ValueError):
                    value, reason = None, "non_finite_prediction"
            unknown += value is None
            values.append(value)
            reasons.append(reason)
        output.append(
            ObjectRegressionPrediction(sample.sample_id, tuple(values), tuple(reasons))
        )
    issues = (
        (
            ComputeIssue(
                "unknown_predictions",
                f"{unknown} target predictions are unknown; no implicit imputation or refitting.",
            ),
        )
        if unknown
        else ()
    )
    value = ObjectRegressionPredictions(
        table.schema_id,
        fitted.computation_id,
        tuple(output),
        table.target_feature_indices,
        unknown,
        not spec.allow_training,
    )
    return _output(operator, dataset, spec, parents, value, issues)


@dataclass(frozen=True, slots=True)
class ObjectRegressionEvaluationSpec:
    SPEC_TYPE: ClassVar[str] = "pix.object_centric.regression_evaluation.spec"
    metric: str = "mean_absolute_error"

    def __post_init__(self):
        if self.metric != "mean_absolute_error":
            raise ValueError("only mean_absolute_error is supported")


@dataclass(frozen=True, slots=True)
class ObjectRegressionTargetError:
    feature_index: int
    mean_absolute_error: float | None
    evaluated_count: int
    unknown_prediction_count: int
    unknown_target_count: int
    excluded_count: int

    def __post_init__(self):
        for name in (
            "feature_index",
            "evaluated_count",
            "unknown_prediction_count",
            "unknown_target_count",
            "excluded_count",
        ):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if (self.mean_absolute_error is None) != (self.evaluated_count == 0):
            raise ValueError("MAE is unknown exactly when no targets were evaluated")
        if self.mean_absolute_error is not None and (
            not isfinite(self.mean_absolute_error) or self.mean_absolute_error < 0
        ):
            raise ValueError("MAE must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class ObjectRegressionEvaluation:
    sample_count: int
    targets: tuple[ObjectRegressionTargetError, ...]
    evaluated_sample_ids: tuple[str, ...]
    profile: str = "entity_disjoint_holdout_mae_per_target_original_units"

    def __post_init__(self):
        if type(self.sample_count) is not int or self.sample_count < 0:
            raise ValueError("sample_count must be nonnegative integer")
        if (
            not isinstance(self.targets, tuple)
            or not self.targets
            or not all(isinstance(t, ObjectRegressionTargetError) for t in self.targets)
        ):
            raise TypeError("targets must be a nonempty error tuple")
        if len({t.feature_index for t in self.targets}) != len(self.targets):
            raise ValueError("duplicate evaluation target")
        if any(
            t.evaluated_count + t.excluded_count != self.sample_count
            or t.unknown_prediction_count > t.excluded_count
            or t.unknown_target_count > t.excluded_count
            for t in self.targets
        ):
            raise ValueError("evaluation counts do not match population")
        _ids(self.evaluated_sample_ids, "evaluated_sample_ids")
        if len(self.evaluated_sample_ids) > self.sample_count:
            raise ValueError("evaluated identities exceed population")


def evaluate_object_regression(
    predictions: ComputationResult[ObjectRegressionPredictions],
    dataset: ComputationResult[ObjectKStepDataset],
    spec: ObjectRegressionEvaluationSpec = ObjectRegressionEvaluationSpec(),
) -> ComputationResult[ObjectRegressionEvaluation]:
    """Report held-out MAE per target and explicit observed/unknown denominators."""
    if not isinstance(spec, ObjectRegressionEvaluationSpec):
        raise TypeError("invalid evaluation spec")
    values = _expected(
        predictions,
        "pix.object_centric.regression_predict",
        ObjectRegressionPredictions,
    )
    table = _expected(dataset, "pix.object_centric.k_step_dataset", ObjectKStepDataset)
    operator, parents = (
        "pix.object_centric.regression_evaluation",
        (predictions, dataset),
    )

    def fail(code, message, unavailable=False):
        return _failure(
            operator, dataset, spec, parents, code, message, unavailable=unavailable
        )

    if (
        not isinstance(predictions.spec, ObjectRegressionPredictSpec)
        or predictions.spec.allow_training
        or not values.entity_disjoint_holdout
    ):
        return fail(
            "heldout_evaluation_required",
            "Training-enabled predictions cannot be reported as held-out MAE.",
        )
    if (
        len(predictions.parent_computation_ids) != 2
        or predictions.parent_computation_ids[1] != values.model_computation_id
        or tuple(row.sample_id for row in values.rows) != predictions.spec.sample_ids
    ):
        return fail(
            "prediction_metadata_mismatch",
            "Prediction identities and model provenance must agree with the request.",
        )
    if (
        predictions.source_digest != dataset.source_digest
        or dataset.computation_id not in predictions.parent_computation_ids
        or values.schema_id != table.schema_id
        or values.target_feature_indices != table.target_feature_indices
    ):
        return fail(
            "evaluation_source_mismatch",
            "Targets must come from the exact dataset used for these predictions.",
        )
    rows = {s.sample_id: s for s in table.samples}
    if any(row.sample_id not in rows for row in values.rows):
        return fail(
            "unknown_evaluation_sample",
            "Prediction identities must match target sample identities.",
        )
    errors, evaluated, issues = [], set(), []
    for position, index in enumerate(values.target_feature_indices):
        deviations, missing_predictions, missing_targets, excluded = [], 0, 0, 0
        for row in values.rows:
            prediction, target = (
                row.values[position],
                rows[row.sample_id].targets[position],
            )
            missing_predictions += prediction is None
            missing_targets += target is None
            if prediction is None or target is None:
                excluded += 1
                continue
            error = abs(prediction - target)
            if not isfinite(error):
                return fail(
                    "non_finite_error",
                    "Absolute error exceeds finite numeric range.",
                    True,
                )
            deviations.append(error)
            evaluated.add(row.sample_id)
        mae = fsum(v / len(deviations) for v in deviations) if deviations else None
        errors.append(
            ObjectRegressionTargetError(
                index,
                mae,
                len(deviations),
                missing_predictions,
                missing_targets,
                excluded,
            )
        )
        if excluded or not deviations:
            issues.append(
                ComputeIssue(
                    "incomplete_evaluation_target",
                    f"Target {index}: evaluated {len(deviations)}, excluded {excluded}; MAE is unknown without observed pairs.",
                )
            )
    if not any(error.evaluated_count for error in errors):
        return fail(
            "no_observed_evaluation_pairs",
            f"No observed pairs among {len(values.rows)} samples; per-target unknown predictions/targets: "
            + ", ".join(
                f"{error.feature_index}={error.unknown_prediction_count}/{error.unknown_target_count}"
                for error in errors
            )
            + ". Held-out MAE is unavailable.",
            True,
        )
    value = ObjectRegressionEvaluation(
        len(values.rows), tuple(errors), tuple(sorted(evaluated))
    )
    return _output(operator, dataset, spec, parents, value, issues)


def validate_learning_result(result: ComputationResult) -> None:
    """Check persisted redundant contracts without claiming to replay training.

    This binds the payload to its request, parent references, coverage and named
    profile. Source rows, fitted coefficients and entity disjointness still need
    the original parent results for independent recomputation; a result envelope
    alone cannot prove those facts.
    """
    if (
        not isinstance(result, ComputationResult)
        or result.operator_id not in RESULT_SCHEMAS
    ):
        raise TypeError("expected an object-centric learning ComputationResult")
    _, request_type, value_type = RESULT_SCHEMAS[result.operator_id]
    if not isinstance(result.spec, request_type):
        raise TypeError("learning request type differs from the operator")
    parent_counts = (
        (1, 2)
        if request_type is ObjectKStepSpec
        else ((1,) if request_type is ObjectRegressionFitSpec else (2,))
    )
    if len(result.parent_computation_ids) not in parent_counts:
        raise ValueError("learning parent count differs from the operator contract")
    if result.value is None:
        return
    if not isinstance(result.value, value_type):
        raise TypeError("learning payload type differs from the operator")
    value, spec = result.value, result.spec
    if (
        hasattr(value, "profile")
        and value.profile != value_type.__dataclass_fields__["profile"].default
    ):
        raise ValueError("unsupported learning payload profile")
    expected_issues = []
    if isinstance(value, ObjectKStepDataset):
        if (
            ObjectKStepSpec(
                value.k,
                value.input_feature_indices,
                value.target_feature_indices,
                value.horizon,
                value.padding,
            )
            != spec
        ):
            raise ValueError("k-step payload and requested window disagree")
        if value.padding == "none" and any(
            step.padded for sample in value.samples for step in sample.inputs
        ):
            raise ValueError("unpadded k-step request cannot contain padding")
        for sample in value.samples:
            identity = (
                sample.execution_id,
                tuple(step.row_ids for step in sample.inputs),
                sample.target_row_ids,
                value.input_feature_indices,
                value.target_feature_indices,
                value.horizon,
                value.padding,
            )
            if sample.sample_id != sha256(repr(identity).encode("utf-8")).hexdigest():
                raise ValueError("k-step sample identity disagrees with its window")
        if value.excluded_row_ids:
            expected_issues.append("sequence_identity_or_time_missing")
        if value.unknown_input_count or value.unknown_target_count:
            expected_issues.append("unknown_dataset_values")
        if not value.samples:
            expected_issues.append("no_k_step_samples")
    elif isinstance(value, ObjectFeatureInverseTable):
        if spec.row_ids is not None and set(spec.row_ids) != {
            row.row_id for row in value.rows
        }:
            raise ValueError("inverse rows differ from the requested selection")
        if value.unknown_value_count:
            expected_issues.append("unknown_inverse_values")
    elif isinstance(value, ObjectLinearRegression):
        if (value.train_sample_ids, value.fit_intercept, value.rank_tolerance) != (
            spec.train_sample_ids,
            spec.fit_intercept,
            spec.rank_tolerance,
        ):
            raise ValueError("regression training metadata disagrees with the request")
        if not spec.fit_intercept and any(v != 0.0 for v in value.intercepts):
            raise ValueError("intercept-free regression cannot contain an intercept")
        if value.excluded_sample_ids:
            expected_issues.append("incomplete_training_samples")
    elif isinstance(value, ObjectRegressionPredictions):
        if tuple(row.sample_id for row in value.rows) != spec.sample_ids:
            raise ValueError("prediction rows differ from the requested order")
        if value.entity_disjoint_holdout != (not spec.allow_training):
            raise ValueError("held-out claim disagrees with training permission")
        if result.parent_computation_ids[1] != value.model_computation_id:
            raise ValueError("prediction model identity disagrees with its parent")
        if value.unknown_value_count:
            expected_issues.append("unknown_predictions")
    elif isinstance(value, ObjectRegressionEvaluation):
        if not any(target.evaluated_count for target in value.targets):
            raise ValueError("evaluation without observed pairs must be unavailable")
        # The IDs form the union of observed samples across target dimensions.
        # Per-target overlap is not retained, so only union bounds are provable.
        if not (
            max(target.evaluated_count for target in value.targets)
            <= len(value.evaluated_sample_ids)
            <= sum(target.evaluated_count for target in value.targets)
        ):
            raise ValueError("evaluated sample identities disagree with target counts")
        expected_issues.extend(
            "incomplete_evaluation_target"
            for target in value.targets
            if target.excluded_count or not target.evaluated_count
        )
    if tuple(issue.code for issue in result.issues) != tuple(expected_issues):
        raise ValueError("learning issues disagree with payload coverage")
    expected_status = (
        ComputeStatus.PARTIAL if expected_issues else ComputeStatus.COMPUTED
    )
    if result.status is not expected_status:
        raise ValueError("learning status disagrees with payload coverage")


RESULT_SCHEMAS = {
    "pix.object_centric.k_step_dataset": (
        "object-k-step-dataset",
        ObjectKStepSpec,
        ObjectKStepDataset,
    ),
    "pix.object_centric.feature_inverse": (
        "object-feature-inverse",
        ObjectFeatureInverseSpec,
        ObjectFeatureInverseTable,
    ),
    "pix.object_centric.regression_fit": (
        "object-linear-regression",
        ObjectRegressionFitSpec,
        ObjectLinearRegression,
    ),
    "pix.object_centric.regression_predict": (
        "object-regression-predictions",
        ObjectRegressionPredictSpec,
        ObjectRegressionPredictions,
    ),
    "pix.object_centric.regression_evaluation": (
        "object-regression-evaluation",
        ObjectRegressionEvaluationSpec,
        ObjectRegressionEvaluation,
    ),
}

__all__ = (
    "ObjectKStepSpec",
    "ObjectFeatureStep",
    "ObjectKStepSample",
    "ObjectLearningScope",
    "ObjectKStepDataset",
    "ObjectFeatureInverseSpec",
    "ObjectFeatureInverseRow",
    "ObjectFeatureInverseTable",
    "ObjectRegressionFitSpec",
    "ObjectLinearRegression",
    "ObjectRegressionPredictSpec",
    "ObjectRegressionPrediction",
    "ObjectRegressionPredictions",
    "ObjectRegressionEvaluationSpec",
    "ObjectRegressionTargetError",
    "ObjectRegressionEvaluation",
    "build_object_k_step_dataset",
    "inverse_transform_object_features",
    "fit_object_regression",
    "predict_object_regression",
    "evaluate_object_regression",
    "validate_learning_result",
)
