"""Independent hand oracles for numeric OC predictive monitoring contracts."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import nan

import pytest

from pix.compute._common import _derived_result
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.object_centric.features import (
    ObjectFeature,
    ObjectFeatureCell,
    ObjectFeatureEncodedRow,
    ObjectFeatureFitSpec,
    ObjectFeatureGraph,
    ObjectFeatureRow,
    ObjectFeatureSpec,
    ObjectFeatureSplitSpec,
    ObjectFeatureTable,
    ObjectFeatureTransformSpec,
    extract_object_features,
    fit_object_feature_encoder,
    split_object_features,
    transform_object_features,
)
from pix.object_centric.learning import (
    ObjectFeatureInverseSpec,
    ObjectFeatureStep,
    ObjectKStepSpec,
    ObjectRegressionEvaluationSpec,
    ObjectRegressionFitSpec,
    ObjectRegressionPredictSpec,
    build_object_k_step_dataset,
    evaluate_object_regression,
    fit_object_regression,
    inverse_transform_object_features,
    predict_object_regression,
    validate_learning_result,
)
from pix.ocel import (
    E2O,
    OCEL,
    Attribute,
    Event,
    EventAttr,
    EventType,
    Object,
    ObjectType,
    ValueType,
)

BASE = datetime(2026, 9, 17, tzinfo=timezone.utc)


def cell(value, role="input"):
    if value is None:
        return ObjectFeatureCell("unknown", role, reason="not_observed")
    if isinstance(value, str):
        return ObjectFeatureCell("text", role, text=value)
    if isinstance(value, bool):
        return ObjectFeatureCell("boolean", role, boolean=value)
    return ObjectFeatureCell("real", role, real=float(value))


def row(execution, sequence, values, *, minute=None, object_id=None):
    identifier = f"{execution}:row:{sequence}"
    return ObjectFeatureRow(
        identifier,
        execution,
        identifier,
        None,
        BASE + timedelta(minutes=sequence if minute is None else minute),
        (identifier,),
        (object_id or f"object:{execution}",),
        tuple(values),
    )


def source(rows, graphs=(), features=None, source_digest="learning-source"):
    rows = tuple(rows)
    features = features or tuple(
        ObjectFeature("event_attribute", attribute=f"value-{i}")
        for i in range(len(rows[0].cells))
    )
    unknown = sum(c.kind == "unknown" for r in rows for c in r.cells)
    target = sum(
        c.kind != "unknown" and c.role == "target" for r in rows for c in r.cells
    )
    observed = sum(
        c.kind != "unknown" and c.role == "input" for r in rows for c in r.cells
    )
    value = ObjectFeatureTable(
        "event",
        features,
        rows,
        tuple(graphs),
        observed,
        target,
        unknown,
        "definition-learning",
    )
    return _derived_result(
        "pix.object_centric.features",
        source_digest,
        ObjectFeatureSpec(features),
        ComputeStatus.COMPUTED,
        value,
    )


def regression_source(
    *, missing_train=False, missing_test=False, missing_target=False, test_bias=0
):
    rows = []
    points = ((0, 0), (1, 0), (0, 1), (2, 1), (4, 2), (3, 1))
    for i, (x, z) in enumerate(points):
        y = 2 * x + 3 * z + 5 + (test_bias if i >= 4 else 0)
        rows.append(
            row(
                f"case-{i}",
                0,
                (
                    cell(
                        None
                        if missing_train and i == 3 or missing_test and i == 5
                        else x
                    ),
                    cell(z),
                    cell(None, "target"),
                ),
            )
        )
        rows.append(
            row(
                f"case-{i}",
                1,
                (
                    cell(0),
                    cell(0),
                    cell(None if missing_target and i == 5 else y, "target"),
                ),
            )
        )
    return source(rows)


def regression_dataset(**kwargs):
    return build_object_k_step_dataset(
        regression_source(**kwargs), ObjectKStepSpec(1, (0, 1), (2,))
    )


def sample_ids(dataset, executions):
    return tuple(
        s.sample_id for s in dataset.value.samples if s.execution_id in executions
    )


def fitted(dataset):
    return fit_object_regression(
        dataset,
        ObjectRegressionFitSpec(sample_ids(dataset, {f"case-{i}" for i in range(4)})),
    )


def predicted(dataset, model=None):
    return predict_object_regression(
        dataset,
        model or fitted(dataset),
        ObjectRegressionPredictSpec(sample_ids(dataset, {"case-4", "case-5"})),
    )


def test_k_window_is_chronological_not_hash_or_identifier_order():
    rows = (
        row("case", 2, (cell(30),)),
        row("case", 0, (cell(10),)),
        row("case", 3, (cell(40),)),
        row("case", 1, (cell(20),)),
    )
    result = build_object_k_step_dataset(source(rows), ObjectKStepSpec(2, (0,), (0,)))
    assert result.status is ComputeStatus.COMPUTED
    assert [
        tuple(step.values for step in sample.inputs) for sample in result.value.samples
    ] == [((10.0,), (20.0,)), ((20.0,), (30.0,))]
    assert [sample.targets for sample in result.value.samples] == [(30.0,), (40.0,)]
    assert result.value.samples[0].target_row_ids == ("case:row:2",)


def test_ties_are_one_group_with_all_row_and_event_identities():
    rows = (
        row("case", 5, (cell(8),), minute=0),
        row("case", 1, (cell(2),), minute=0),
        row("case", 9, (cell(20),), minute=2),
    )
    result = build_object_k_step_dataset(source(rows), ObjectKStepSpec(1, (0,), (0,)))
    sample = result.value.samples[0]
    assert len(result.value.samples) == 1
    assert sample.inputs[0].values == (5.0,)
    assert sample.inputs[0].row_ids == ("case:row:1", "case:row:5")
    assert sample.inputs[0].event_ids == sample.inputs[0].row_ids
    assert sample.target_time > sample.inputs[0].time


def test_tied_missing_cell_does_not_average_observed_subset():
    rows = (
        row("case", 0, (cell(8),)),
        row("case", 1, (cell(None),), minute=0),
        row("case", 2, (cell(20),)),
    )
    result = build_object_k_step_dataset(source(rows), ObjectKStepSpec(1, (0,), (0,)))
    assert result.value.samples[0].inputs[0].values == (None,)
    assert result.value.samples[0].inputs[0].reasons == ("group_contains_unknown",)
    assert result.value.unknown_input_count == 1
    assert result.status is ComputeStatus.PARTIAL


def test_k_horizon_counts_timestamp_groups_and_padding_is_unknown():
    rows = tuple(row("case", i, (cell(i),), minute=i * 100) for i in range(4))
    result = build_object_k_step_dataset(
        source(rows), ObjectKStepSpec(3, (0,), (0,), horizon=2, padding="left_unknown")
    )
    assert len(result.value.samples) == 2
    first = result.value.samples[0]
    assert first.targets == (2.0,)
    assert [s.padded for s in first.inputs] == [True, True, False]
    assert first.inputs[0].values == (None,)
    assert first.inputs[0].row_ids == ()
    assert result.value.unknown_input_count == 3
    none = build_object_k_step_dataset(
        source(rows), ObjectKStepSpec(3, (0,), (0,), horizon=2)
    )
    assert none.value.samples == ()
    assert none.status is ComputeStatus.PARTIAL


def test_appending_future_cannot_change_previous_input_values_or_sample_ids():
    rows = tuple(row("case", i, (cell(i),)) for i in range(4))
    earlier = build_object_k_step_dataset(source(rows), ObjectKStepSpec(2, (0,), (0,)))
    later = build_object_k_step_dataset(
        source(rows + (row("case", 99, (cell(1e9),)),)), ObjectKStepSpec(2, (0,), (0,))
    )
    assert [(s.sample_id, s.inputs, s.targets) for s in earlier.value.samples] == [
        (s.sample_id, s.inputs, s.targets) for s in later.value.samples[:2]
    ]


def test_retrospective_target_is_rejected_as_input_in_any_row():
    rows = (row("case", 0, (cell(9, "target"),)), row("case", 1, (cell(10),)))
    result = build_object_k_step_dataset(source(rows), ObjectKStepSpec(1, (0,), (0,)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "target_in_input_window"


def test_unknown_and_non_numeric_inputs_are_masks_not_zero():
    rows = (
        row("case", 0, (cell("r1"), cell(None))),
        row("case", 1, (cell("r2"), cell(0))),
    )
    result = build_object_k_step_dataset(source(rows), ObjectKStepSpec(1, (0, 1), (1,)))
    assert result.value.samples[0].inputs[0].values == (None, None)
    assert result.value.samples[0].targets == (0.0,)


def test_missing_execution_or_time_is_counted_and_excluded():
    good = (row("case", 0, (cell(1),)), row("case", 1, (cell(2),)))
    bad = replace(row("bad", 0, (cell(1),)), time=None)
    result = build_object_k_step_dataset(
        source(good + (bad,)), ObjectKStepSpec(1, (0,), (0,))
    )
    assert result.value.excluded_row_ids == (bad.row_id,)
    assert result.status is ComputeStatus.PARTIAL


def test_partition_is_bound_to_exact_source_and_preserves_whole_executions():
    original = regression_source()
    partition = split_object_features(original, ObjectFeatureSplitSpec(0.5))
    result = build_object_k_step_dataset(
        original, ObjectKStepSpec(1, (0, 1), (2,)), partition=partition
    )
    assert {s.partition for s in result.value.samples} == {"train", "test"}
    assert all(
        set(s.target_row_ids) <= set(partition.value.train_row_ids)
        for s in result.value.samples
        if s.partition == "train"
    )
    changed = replace(original, source_digest="other-source")
    wrong = build_object_k_step_dataset(
        changed, ObjectKStepSpec(1, (0, 1), (2,)), partition=partition
    )
    assert wrong.status is ComputeStatus.INVALID_INPUT


def test_shared_boundary_object_rejects_unprotected_partition():
    rows = tuple(
        row(execution, i, (cell(i),))
        for execution in ("left", "right")
        for i in range(2)
    )
    graphs = tuple(
        ObjectFeatureGraph(
            execution,
            (),
            ("boundary-only",),
            tuple(r.row_id for r in rows if r.execution_id == execution),
            (),
            "ordered",
        )
        for execution in ("left", "right")
    )
    original = source(rows, graphs)
    partition = split_object_features(
        original, ObjectFeatureSplitSpec(0.5, group_shared_entities=False)
    )
    result = build_object_k_step_dataset(
        original, ObjectKStepSpec(1, (0,), (0,)), partition=partition
    )
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "partition_entity_leakage"
    grouped = split_object_features(original)
    protected = build_object_k_step_dataset(
        original, ObjectKStepSpec(1, (0,), (0,)), partition=grouped
    )
    assert all(s.partition == "train" for s in protected.value.samples)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"k": 0},
        {"k": True},
        {"horizon": 0},
        {"padding": "zeros"},
        {"input_feature_indices": (0, 0)},
        {"target_feature_indices": ()},
    ],
)
def test_invalid_k_step_spec(kwargs):
    parameters = dict(k=1, input_feature_indices=(0,), target_feature_indices=(1,))
    parameters.update(kwargs)
    with pytest.raises((ValueError, TypeError)):
        ObjectKStepSpec(**parameters)


def test_invalid_feature_dimensions_are_explicit():
    original = source((row("case", 0, (cell(1),)), row("case", 1, (cell(2),))))
    index = build_object_k_step_dataset(original, ObjectKStepSpec(1, (1,), (0,)))
    assert index.status is ComputeStatus.INVALID_INPUT
    malformed = replace(
        original,
        value=replace(
            original.value,
            rows=(replace(original.value.rows[0], cells=()), original.value.rows[1]),
        ),
    )
    assert (
        build_object_k_step_dataset(malformed, ObjectKStepSpec(1, (0,), (0,))).status
        is ComputeStatus.INVALID_INPUT
    )


def test_inverse_uses_training_statistics_and_does_not_restore_excluded_targets():
    rows = tuple(
        row("case", i, (cell(value), cell(99, "target")))
        for i, value in enumerate((2, 4, 100))
    )
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows[:2]))
    )
    transformed = transform_object_features(original, encoder)
    restored = inverse_transform_object_features(transformed, encoder)
    assert [r.cells[0].real for r in restored.value.rows] == [2, 4, 100]
    assert all(
        r.cells[1].kind == "unknown" and r.cells[1].role == "target"
        for r in restored.value.rows
    )
    assert restored.value.excluded_target_count == 3
    assert restored.value.unknown_value_count == 0
    assert encoder.value.columns[0].mean == 3
    assert encoder.value.columns[0].scale == 1


def test_inverse_constant_column_and_missing_value_keep_original_semantics():
    rows = tuple(
        row("case", i, (cell(value),)) for i, value in enumerate((4, 4, 9, None))
    )
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows[:2]))
    )
    restored = inverse_transform_object_features(
        transform_object_features(original, encoder), encoder
    )
    assert [r.cells[0].real for r in restored.value.rows[:3]] == [4, 4, 9]
    assert restored.value.rows[-1].cells[0].reason == "not_observed"
    assert restored.value.unknown_value_count == 1


@pytest.mark.parametrize("encoding", ["one_hot", "ordinal"])
def test_inverse_categories_and_unseen_categories(encoding):
    rows = tuple(
        row("case", i, (cell(value),)) for i, value in enumerate(("a", "b", "unseen"))
    )
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows[:2]), encoding)
    )
    restored = inverse_transform_object_features(
        transform_object_features(original, encoder), encoder
    )
    assert [r.cells[0].text for r in restored.value.rows[:2]] == ["a", "b"]
    assert restored.value.rows[2].cells[0].reason == "unseen_category"


@pytest.mark.parametrize("values", [(0.0, 0.0), (1.0, 1.0), (0.5, 0.5)])
def test_inverse_ambiguous_one_hot_is_unknown(values):
    rows = (row("case", 0, (cell("a"),)), row("case", 1, (cell("b"),)))
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows))
    )
    transformed = transform_object_features(original, encoder)
    corrupted = replace(
        transformed,
        value=replace(
            transformed.value,
            rows=(ObjectFeatureEncodedRow(rows[0].row_id, values, (None, None)),),
        ),
    )
    restored = inverse_transform_object_features(corrupted, encoder)
    assert restored.value.rows[0].cells[0].reason == "ambiguous_categorical_inverse"


def test_inverse_rejects_wrong_encoder_wrong_dimensions_and_unknown_ids():
    original = regression_source()
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec((original.value.rows[0].row_id,))
    )
    transformed = transform_object_features(original, encoder)
    other = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec((original.value.rows[2].row_id,))
    )
    assert (
        inverse_transform_object_features(transformed, other).status
        is ComputeStatus.INVALID_INPUT
    )
    short = replace(
        transformed,
        value=replace(
            transformed.value, rows=(replace(transformed.value.rows[0], values=()),)
        ),
    )
    assert (
        inverse_transform_object_features(short, encoder).status
        is ComputeStatus.INVALID_INPUT
    )
    assert (
        inverse_transform_object_features(
            transformed, encoder, ObjectFeatureInverseSpec(("missing",))
        ).status
        is ComputeStatus.INVALID_INPUT
    )


def test_native_qr_hand_oracle_multi_feature_and_heldout_mae():
    dataset = regression_dataset(test_bias=3)
    model = fitted(dataset)
    assert model.status is ComputeStatus.COMPUTED
    assert model.value.coefficients[0] == pytest.approx((2, 3))
    assert model.value.intercepts == pytest.approx((5,))
    assert model.value.rank == model.value.parameter_count == 3
    predictions = predicted(dataset, model)
    assert [r.values[0] for r in predictions.value.rows] == pytest.approx([19, 14])
    evaluation = evaluate_object_regression(predictions, dataset)
    assert evaluation.value.targets[0].mean_absolute_error == pytest.approx(3)
    assert evaluation.value.targets[0].evaluated_count == 2
    assert evaluation.value.sample_count == 2


def test_training_complete_case_exclusion_is_counted():
    dataset = regression_dataset(missing_train=True)
    model = fitted(dataset)
    assert model.status is ComputeStatus.PARTIAL
    assert len(model.value.used_sample_ids) == 3
    assert len(model.value.excluded_sample_ids) == 1
    assert model.value.coefficients[0] == pytest.approx((2, 3))


def test_heldout_feature_or_target_changes_cannot_refit_model():
    dataset = regression_dataset()
    baseline = fitted(dataset)
    changed = regression_dataset(test_bias=1000000)
    trained = fitted(changed)
    assert trained.value == baseline.value
    before = predicted(dataset, baseline)
    after = predicted(changed, baseline)
    assert [r.values for r in after.value.rows] == [r.values for r in before.value.rows]
    assert evaluate_object_regression(after, changed).value.targets[
        0
    ].mean_absolute_error == pytest.approx(1000000)


def test_prediction_and_target_missing_counts_use_observed_pair_denominator():
    dataset = regression_dataset(missing_test=True, missing_target=True)
    predictions = predicted(dataset)
    evaluation = evaluate_object_regression(predictions, dataset)
    error = evaluation.value.targets[0]
    assert predictions.status is ComputeStatus.PARTIAL
    assert error.evaluated_count == 1
    assert error.unknown_prediction_count == 1
    assert error.unknown_target_count == 1
    assert error.excluded_count == 1
    assert error.mean_absolute_error == pytest.approx(0, abs=1e-12)
    assert evaluation.status is ComputeStatus.PARTIAL


def test_prediction_never_uses_target_values_as_inputs():
    dataset = regression_dataset(missing_target=True)
    predictions = predicted(dataset)
    assert all(row.values[0] is not None for row in predictions.value.rows)
    assert predictions.status is ComputeStatus.COMPUTED


def test_regression_rejects_shared_execution_and_boundary_object_holdout():
    dataset = regression_dataset()
    model = fitted(dataset)
    same_train = predict_object_regression(
        dataset,
        model,
        ObjectRegressionPredictSpec((dataset.value.samples[0].sample_id,)),
    )
    assert same_train.issues[0].code == "prediction_entity_leakage"
    # The object did not occur in either k-window but belongs to the graph scope.
    scopes = list(dataset.value.execution_scopes)
    scopes[4] = replace(
        scopes[4],
        object_ids=scopes[4].object_ids + (model.value.train_object_ids[0],),
    )
    changed = replace(
        dataset, value=replace(dataset.value, execution_scopes=tuple(scopes))
    )
    overlapping = predicted(changed, model)
    assert overlapping.issues[0].code == "prediction_entity_leakage"


def test_training_predictions_are_available_for_diagnostics_but_not_heldout_mae():
    dataset = regression_dataset()
    model = fitted(dataset)
    predictions = predict_object_regression(
        dataset,
        model,
        ObjectRegressionPredictSpec(model.value.train_sample_ids, allow_training=True),
    )
    assert predictions.value.entity_disjoint_holdout is False
    assert (
        evaluate_object_regression(predictions, dataset).status
        is ComputeStatus.INVALID_INPUT
    )


def test_unknown_training_or_prediction_ids_are_rejected():
    dataset = regression_dataset()
    assert (
        fit_object_regression(dataset, ObjectRegressionFitSpec(("absent",))).status
        is ComputeStatus.INVALID_INPUT
    )
    assert (
        predict_object_regression(
            dataset, fitted(dataset), ObjectRegressionPredictSpec(("absent",))
        ).status
        is ComputeStatus.INVALID_INPUT
    )


def test_schema_includes_feature_definitions_and_prevents_positional_mixup():
    original = regression_source()
    dataset = build_object_k_step_dataset(original, ObjectKStepSpec(1, (0, 1), (2,)))
    changed_features = (
        ObjectFeature("event_attribute", attribute="different"),
    ) + original.value.features[1:]
    changed = replace(
        original, value=replace(original.value, features=changed_features)
    )
    mismatch = build_object_k_step_dataset(changed, ObjectKStepSpec(1, (0, 1), (2,)))
    assert (
        predict_object_regression(
            mismatch,
            fitted(dataset),
            ObjectRegressionPredictSpec(sample_ids(mismatch, {"case-4"})),
        )
        .issues[0]
        .code
        == "regression_schema_mismatch"
    )


def test_rank_deficiency_and_too_few_observations_are_unavailable():
    dataset = regression_dataset()
    too_few = fit_object_regression(
        dataset, ObjectRegressionFitSpec((dataset.value.samples[0].sample_id,))
    )
    assert too_few.status is ComputeStatus.UNAVAILABLE
    assert too_few.issues[0].code == "insufficient_complete_training_samples"
    samples = tuple(
        replace(
            sample,
            inputs=(
                replace(
                    sample.inputs[0],
                    values=(sample.inputs[0].values[0], 2 * sample.inputs[0].values[0]),
                ),
            ),
        )
        for sample in dataset.value.samples
    )
    collinear = replace(dataset, value=replace(dataset.value, samples=samples))
    singular = fitted(collinear)
    assert singular.status is ComputeStatus.UNAVAILABLE
    assert singular.issues[0].code == "rank_deficient_design"


def test_no_intercept_and_multi_target_regression_oracle():
    rows = []
    for i, x in enumerate((1, 2, 3, 4)):
        rows.extend(
            (
                row(f"case-{i}", 0, (cell(x), cell(0), cell(0))),
                row(f"case-{i}", 1, (cell(0), cell(2 * x), cell(5 * x))),
            )
        )
    dataset = build_object_k_step_dataset(
        source(rows), ObjectKStepSpec(1, (0,), (1, 2))
    )
    model = fit_object_regression(
        dataset,
        ObjectRegressionFitSpec(
            sample_ids(dataset, {"case-0", "case-1", "case-2"}), fit_intercept=False
        ),
    )
    assert model.value.coefficients[0] == pytest.approx((2,))
    assert model.value.coefficients[1] == pytest.approx((5,))
    assert model.value.intercepts == (0, 0)
    predictions = predict_object_regression(
        dataset, model, ObjectRegressionPredictSpec(sample_ids(dataset, {"case-3"}))
    )
    assert predictions.value.rows[0].values == pytest.approx((8, 20))
    assert [
        t.mean_absolute_error
        for t in evaluate_object_regression(predictions, dataset).value.targets
    ] == pytest.approx((0, 0), abs=1e-12)


def test_test_partition_cannot_fit_even_if_requested_explicitly():
    original = regression_source()
    partition = split_object_features(original, ObjectFeatureSplitSpec(0.5))
    dataset = build_object_k_step_dataset(
        original, ObjectKStepSpec(1, (0, 1), (2,)), partition=partition
    )
    test_ids = tuple(
        s.sample_id for s in dataset.value.samples if s.partition == "test"
    )
    assert (
        fit_object_regression(dataset, ObjectRegressionFitSpec(test_ids)).issues[0].code
        == "test_sample_in_training"
    )


def test_empty_or_all_unknown_heldout_mae_is_unavailable_not_zero():
    dataset = regression_dataset(missing_test=True)
    model = fitted(dataset)
    for ids in ((), sample_ids(dataset, {"case-5"})):
        predictions = predict_object_regression(
            dataset, model, ObjectRegressionPredictSpec(ids)
        )
        result = evaluate_object_regression(predictions, dataset)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None


def test_evaluation_rejects_a_different_dataset_parent():
    dataset = regression_dataset()
    predictions = predicted(dataset)
    other = replace(dataset, computation_id="another-dataset")
    assert (
        evaluate_object_regression(predictions, other).issues[0].code
        == "evaluation_source_mismatch"
    )


@pytest.mark.parametrize(
    "factory",
    [
        lambda: ObjectRegressionFitSpec(()),
        lambda: ObjectRegressionFitSpec(("x", "x")),
        lambda: ObjectRegressionFitSpec(("x",), rank_tolerance=nan),
        lambda: ObjectRegressionPredictSpec(("x", "x")),
        lambda: ObjectRegressionEvaluationSpec("accuracy"),
        lambda: ObjectFeatureStep(BASE, ("row",), ("event",), (nan,), (None,)),
    ],
)
def test_invalid_learning_contracts(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()


def test_real_ocel_feature_pipeline_uses_canonical_events_and_no_ml_backend():
    events, objects, links = [], [], []
    for i in range(5):
        objects.append(Object(f"order-{i}", "order"))
        for step, amount in enumerate((i, 2 * i + 1)):
            identifier = f"e-{i}-{step}"
            events.append(
                Event(
                    identifier,
                    "observe",
                    BASE + timedelta(minutes=step),
                    (EventAttr("amount", amount),),
                )
            )
            links.append(E2O(identifier, f"order-{i}", "flow"))
    log = OCEL(
        event_types=(EventType("observe", (Attribute("amount", ValueType.INTEGER),)),),
        object_types=(ObjectType("order"),),
        events=tuple(events),
        objects=tuple(objects),
        e2o=tuple(links),
    )
    features = extract_object_features(
        log,
        ObjectFeatureSpec((ObjectFeature("characteristic_value", attribute="amount"),)),
    )
    dataset = build_object_k_step_dataset(features, ObjectKStepSpec(1, (0,), (0,)))
    ordered = sorted(
        dataset.value.samples, key=lambda sample: sample.inputs[0].values[0]
    )
    model = fit_object_regression(
        dataset, ObjectRegressionFitSpec(tuple(s.sample_id for s in ordered[:4]))
    )
    predictions = predict_object_regression(
        dataset, model, ObjectRegressionPredictSpec((ordered[4].sample_id,))
    )
    assert model.value.coefficients[0] == pytest.approx((2,))
    assert model.value.intercepts == pytest.approx((1,))
    assert predictions.value.rows[0].values == pytest.approx((9,))
    assert evaluate_object_regression(predictions, dataset).value.targets[
        0
    ].mean_absolute_error == pytest.approx(0, abs=1e-12)


def test_result_round_trip_after_registry_integration():
    from pix.results import result_from_json, result_json_bytes

    original = regression_source()
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in original.value.rows[:4]))
    )
    inverse = inverse_transform_object_features(
        transform_object_features(original, encoder, ObjectFeatureTransformSpec()),
        encoder,
    )
    dataset = regression_dataset()
    model = fitted(dataset)
    predictions = predicted(dataset, model)
    evaluation = evaluate_object_regression(predictions, dataset)
    for result in (inverse, dataset, model, predictions, evaluation):
        assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "change,code",
    [
        ({"mode": "mystery"}, "invalid_encoder_mode"),
        ({"category_encoding": "mystery"}, "invalid_categorical_encoder"),
        ({"categories": ()}, "invalid_categorical_encoder"),
        ({"categories": ("untyped",)}, "invalid_categorical_encoder"),
        ({"categories": ("text:a", "text:a")}, "invalid_categorical_encoder"),
        ({"categories": None}, "invalid_categorical_encoder"),
        ({"feature_index": 9}, "invalid_encoder_dimensions"),
    ],
)
def test_inverse_rejects_malformed_encoder_before_interpreting_columns(change, code):
    rows = (row("case", 0, (cell("a"),)), row("case", 1, (cell("b"),)))
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows))
    )
    transformed = transform_object_features(original, encoder)
    bad_encoder = replace(
        encoder,
        value=replace(
            encoder.value, columns=(replace(encoder.value.columns[0], **change),)
        ),
    )
    result = inverse_transform_object_features(transformed, bad_encoder)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == code


def test_inverse_cannot_change_fitted_training_identity_or_category_policy():
    rows = (row("case", 0, (cell("a"),)), row("case", 1, (cell("b"),)))
    original = source(rows)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in rows))
    )
    transformed = transform_object_features(original, encoder)
    changed_request = replace(
        encoder, spec=replace(encoder.spec, categorical_encoding="ordinal")
    )
    result = inverse_transform_object_features(transformed, changed_request)
    assert result.issues[0].code == "encoder_fit_metadata_mismatch"


@pytest.mark.parametrize(
    "field,value", [("mean", True), ("scale", -1.0), ("scale", None)]
)
def test_inverse_requires_finite_nonnegative_numeric_training_parameters(field, value):
    original = source((row("case", 0, (cell(2),)), row("case", 1, (cell(4),))))
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in original.value.rows))
    )
    transformed = transform_object_features(original, encoder)
    changed = replace(
        encoder,
        value=replace(
            encoder.value,
            columns=(replace(encoder.value.columns[0], **{field: value}),),
        ),
    )
    result = inverse_transform_object_features(transformed, changed)
    assert result.issues[0].code == "invalid_numeric_encoder"


def test_forged_diagnostic_holdout_flag_is_rejected_before_mae():
    dataset = regression_dataset()
    model = fitted(dataset)
    diagnostics = predict_object_regression(
        dataset,
        model,
        ObjectRegressionPredictSpec(model.value.train_sample_ids, allow_training=True),
    )
    forged = replace(
        diagnostics, value=replace(diagnostics.value, entity_disjoint_holdout=True)
    )
    assert (
        evaluate_object_regression(forged, dataset).issues[0].code
        == "heldout_evaluation_required"
    )
    with pytest.raises(ValueError, match="held-out claim"):
        validate_learning_result(forged)


@pytest.mark.parametrize("tamper", ["rows", "model_parent", "fit_request"])
def test_redundant_prediction_and_fit_metadata_cannot_be_relabelled(tamper):
    dataset = regression_dataset()
    model = fitted(dataset)
    predictions = predicted(dataset, model)
    if tamper == "fit_request":
        altered = replace(model, spec=replace(model.spec, rank_tolerance=1e-6))
        result = predicted(dataset, altered)
        assert result.issues[0].code == "regression_fit_metadata_mismatch"
    else:
        value = (
            replace(predictions.value, rows=tuple(reversed(predictions.value.rows)))
            if tamper == "rows"
            else replace(predictions.value, model_computation_id="different-model")
        )
        altered = replace(predictions, value=value)
        assert (
            evaluate_object_regression(altered, dataset).issues[0].code
            == "prediction_metadata_mismatch"
        )
    with pytest.raises(ValueError):
        validate_learning_result(altered)


@pytest.mark.parametrize(
    "tamper", ["window", "sample_identity", "parents", "profile", "issues", "status"]
)
def test_k_step_result_validator_rejects_inconsistent_persisted_evidence(tamper):
    dataset = regression_dataset(missing_test=True)
    if tamper == "window":
        altered = replace(dataset, spec=replace(dataset.spec, horizon=2))
    elif tamper == "sample_identity":
        samples = (
            replace(dataset.value.samples[0], sample_id="other"),
        ) + dataset.value.samples[1:]
        altered = replace(dataset, value=replace(dataset.value, samples=samples))
    elif tamper == "parents":
        altered = replace(dataset, parent_computation_ids=())
    elif tamper == "profile":
        altered = replace(dataset, value=replace(dataset.value, profile="invented"))
    elif tamper == "issues":
        altered = replace(dataset, issues=(ComputeIssue("no_k_step_samples", "false"),))
    else:
        altered = replace(dataset, status=ComputeStatus.COMPUTED)
    with pytest.raises(ValueError):
        validate_learning_result(altered)


def test_inverse_selection_and_evaluation_population_match_persisted_requests():
    original = regression_source()
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in original.value.rows[:4]))
    )
    inverse = inverse_transform_object_features(
        transform_object_features(original, encoder), encoder
    )
    with pytest.raises(ValueError, match="requested selection"):
        validate_learning_result(replace(inverse, spec=ObjectFeatureInverseSpec(())))
    dataset = regression_dataset()
    evaluation = evaluate_object_regression(predicted(dataset), dataset)
    with pytest.raises(ValueError, match="evaluated sample identities"):
        validate_learning_result(
            replace(
                evaluation, value=replace(evaluation.value, evaluated_sample_ids=())
            )
        )


def test_public_codec_checks_learning_evidence_in_addition_to_dataclass_shape():
    from pix.results import result_json_bytes

    dataset = regression_dataset()
    predictions = predicted(dataset)
    forged = replace(
        predictions, value=replace(predictions.value, entity_disjoint_holdout=False)
    )
    with pytest.raises(ValueError, match="held-out claim"):
        result_json_bytes(forged)


def test_learning_failure_envelopes_remain_serializable_without_fabricated_values():
    from pix.results import result_from_json, result_json_bytes

    original = regression_source()
    dataset = regression_dataset()
    model = fitted(dataset)
    encoder = fit_object_feature_encoder(
        original, ObjectFeatureFitSpec(tuple(r.row_id for r in original.value.rows[:4]))
    )
    transformed = transform_object_features(original, encoder)
    empty = predict_object_regression(dataset, model, ObjectRegressionPredictSpec(()))
    failures = (
        build_object_k_step_dataset(original, ObjectKStepSpec(1, (99,), (0,))),
        inverse_transform_object_features(
            transformed, encoder, ObjectFeatureInverseSpec(("missing",))
        ),
        fit_object_regression(dataset, ObjectRegressionFitSpec(("missing",))),
        predict_object_regression(
            dataset, model, ObjectRegressionPredictSpec(("missing",))
        ),
        evaluate_object_regression(empty, dataset),
    )
    for result in failures:
        assert result.value is None
        validate_learning_result(result)
        assert result_from_json(result_json_bytes(result)) == result
