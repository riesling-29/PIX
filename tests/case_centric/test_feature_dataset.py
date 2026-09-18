"""Independent witnesses for observation, censoring and leakage-safe encoding."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.feature_dataset import (
    RESULT_SCHEMAS,
    CaseAvailability,
    CaseFollowUp,
    CaseSequenceSpec,
    CensoredPredictionTarget,
    LeakageSplitSpec,
    ObservationEncoderSpec,
    ObservationSpec,
    encode_case_sequences,
    fit_observation_encoder,
    leakage_safe_split,
    observation_dataset,
    transform_observations,
)
from pix.case_centric.features import FeatureSpec
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def at(second):
    return BASE + timedelta(seconds=second)


def event(identity, second, activity="A", *, category=None, number=None):
    attributes = [CaseAttribute("concept:name", "string", activity)]
    if second is not None:
        attributes.append(CaseAttribute("time:timestamp", "date", at(second)))
    if category is not None:
        attributes.append(CaseAttribute("category", "string", category))
    if number is not None:
        attributes.append(CaseAttribute("number", "int", number))
    return CaseEvent(identity, tuple(attributes))


def log(*cases):
    return CaseLog(
        tuple(CaseTrace(identity, tuple(events)) for identity, events in cases)
    )


def computed(result):
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def test_cutoff_is_inclusive_and_target_clock_is_cutoff_not_last_event():
    source = log(("c", (event("a", 0), event("b", 5, "B"), event("c", 10, "C"))))
    value = computed(
        observation_dataset(
            source,
            ObservationSpec(at(8)),
            follow_up=(CaseFollowUp("c", at(30), at(25)),),
        )
    )
    assert value.samples[0].prefix.event_ids == ("a", "b")
    assert value.samples[0].prefix.elapsed_seconds == 5.0
    assert value.samples[0].elapsed_at_observation_seconds == 8.0
    target = value.targets[0]
    assert (target.next_activity, target.next_time_seconds) == ("C", 2.0)
    assert target.remaining_time_seconds == 17.0
    assert target.completion_status == "completed"
    boundary = computed(
        observation_dataset(
            source,
            ObservationSpec(at(5)),
            follow_up=(CaseFollowUp("c", at(30), at(25)),),
        )
    )
    assert boundary.samples[0].prefix.event_ids == ("a", "b")


def test_last_event_is_not_evidence_of_completion_or_zero_remaining_time():
    source = log(("c", (event("a", 0), event("b", 20, "B"))))
    spec = ObservationSpec(at(20))
    censored = computed(
        observation_dataset(source, spec, follow_up=(CaseFollowUp("c", at(30)),))
    )
    completed = computed(
        observation_dataset(
            source, spec, follow_up=(CaseFollowUp("c", at(30), at(30)),)
        )
    )
    assert censored.samples == completed.samples
    assert censored.targets[0].next_status == "censored"
    assert censored.targets[0].remaining_time_seconds is None
    assert censored.targets[0].completion_status == "censored"
    assert completed.targets[0].next_status == "terminal"
    assert completed.targets[0].remaining_time_seconds == 10.0
    assert not completed.targets[0].is_complete_at_observation


@pytest.mark.parametrize(
    "follow_until,complete,status,remaining",
    [
        (8, None, "censored", None),
        (10, None, "horizon_survived", None),
        (15, 15, "horizon_survived", None),
        (15, 10, "completed", 5.0),
    ],
)
def test_horizon_distinguishes_censored_survival_and_observed_completion(
    follow_until, complete, status, remaining
):
    source = log(("c", (event("a", 0),)))
    state = CaseFollowUp(
        "c", at(follow_until), at(complete) if complete is not None else None
    )
    value = computed(
        observation_dataset(
            source, ObservationSpec(at(5), label_horizon_seconds=5), follow_up=(state,)
        )
    )
    assert value.targets[0].completion_status == status
    assert value.targets[0].remaining_time_seconds == remaining
    assert value.targets[0].follow_up_seconds == min(follow_until, 10) - 5


def test_terminal_at_cutoff_has_explicit_zero_and_horizon_zero_is_valid():
    source = log(("c", (event("a", 0), event("b", 5, "B"))))
    target = computed(
        observation_dataset(
            source,
            ObservationSpec(at(5), 0),
            follow_up=(CaseFollowUp("c", at(5), at(5)),),
        )
    ).targets[0]
    assert target.is_complete_at_observation
    assert target.remaining_time_seconds == 0.0
    assert target.next_time_seconds is None
    assert target.next_status == "terminal"


def test_future_activities_and_bad_feature_values_do_not_change_observed_inputs():
    observed = event("a", 0, "A", category="red", number=3)
    future = event("b", 20, "SECRET", category="secret")
    corrupt = replace(
        future,
        attributes=future.attributes
        + (
            CaseAttribute("number", "list"),
            CaseAttribute("number", "string", "duplicate"),
        ),
    )
    before = log(("c", (observed, future)))
    after = log(("c", (observed, corrupt, event("d", 30, "NEW"))))
    spec = ObservationSpec(at(5), 5)
    follow = (CaseFollowUp("c", at(10)),)
    a, b = (
        observation_dataset(before, spec, follow_up=follow),
        observation_dataset(after, spec, follow_up=follow),
    )
    assert computed(a) == computed(b)
    assert a.source_digest != b.source_digest
    encoding = ObservationEncoderSpec(
        spec,
        FeatureSpec(
            level="event",
            encoding="tfidf",
            numeric_attributes=("number",),
            categorical_attributes=("category",),
        ),
    )
    first = computed(
        fit_observation_encoder(before, encoding, training_case_ids=("c",))
    )
    second = computed(
        fit_observation_encoder(after, encoding, training_case_ids=("c",))
    )
    assert first == second
    assert all("SECRET" not in column.terms for column in first.fitted_model.columns)
    assert computed(transform_observations(before, first)) == computed(
        transform_observations(after, first)
    )


def test_unobserved_activity_may_be_missing_without_invalidating_cutoff_or_encoder():
    unknown = CaseEvent("future", (CaseAttribute("time:timestamp", "date", at(20)),))
    source = log(("c", (event("past", 0), unknown)))
    spec = ObservationSpec(at(5), 5)
    computed(observation_dataset(source, spec, follow_up=(CaseFollowUp("c", at(10)),)))
    computed(
        fit_observation_encoder(
            source, ObservationEncoderSpec(spec), training_case_ids=("c",)
        )
    )


@pytest.mark.parametrize(
    "events",
    [
        (event("a", 0), event("b", 30), event("c", 20)),
        (event("a", 20), event("b", 10)),
        (event("a", None),),
        (
            CaseEvent(
                "a", (CaseAttribute("time:timestamp", "date", datetime(2026, 1, 1)),)
            ),
        ),
    ],
)
def test_cutoff_never_sorts_or_guesses_unknown_event_availability(events):
    result = observation_dataset(
        log(("c", events)),
        ObservationSpec(at(25)),
        follow_up=(CaseFollowUp("c", at(40)),),
    )
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


@pytest.mark.parametrize(
    "follow",
    [
        (),
        (CaseFollowUp("c", at(4)),),
        (CaseFollowUp("unknown", at(10)),),
        (CaseFollowUp("c", at(20), at(4)),),
    ],
)
def test_missing_earlier_unknown_or_contradictory_follow_up_is_invalid(follow):
    source = log(("c", (event("a", 0), event("b", 5))))
    result = observation_dataset(source, ObservationSpec(at(5)), follow_up=follow)
    assert result.status is ComputeStatus.INVALID_INPUT


def test_future_and_empty_cases_are_explicitly_excluded_not_zero_vectors():
    source = log(
        ("known", (event("a", 0),)), ("future", (event("b", 10),)), ("empty", ())
    )
    value = computed(
        observation_dataset(
            source, ObservationSpec(at(5)), follow_up=(CaseFollowUp("known", at(5)),)
        )
    )
    assert tuple(x.prefix.case_id for x in value.samples) == ("known",)
    assert value.excluded_case_ids == ("empty", "future")


def test_equal_utc_instants_are_included_regardless_of_local_timezone():
    offset = timezone(timedelta(hours=9))
    source = log(("c", (event("a", 0),)))
    spec = ObservationSpec(BASE.astimezone(offset))
    value = computed(
        observation_dataset(source, spec, follow_up=(CaseFollowUp("c", BASE),))
    )
    assert value.samples[0].prefix.event_ids == ("a",)
    assert value.samples[0].elapsed_at_observation_seconds == 0.0


def test_materialization_limit_never_returns_a_truncated_training_sample():
    source = log(("c", (event("a", 0), event("b", 1))))
    spec = ObservationSpec(at(5), max_observed_events=1)
    result = observation_dataset(source, spec, follow_up=(CaseFollowUp("c", at(5)),))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def cases_for_split():
    return log(*((f"c{i}", (event(f"e{i}", i * 10),)) for i in range(6)))


def test_shared_groups_are_transitive_and_source_order_invariant():
    source = cases_for_split()
    spec = LeakageSplitSpec(
        train_fraction=0.5, shared_case_groups=(("c0", "c1"), ("c1", "c2"))
    )
    first = computed(leakage_safe_split(source, spec))
    reordered = replace(source, traces=source.traces[::-1])
    second = computed(
        leakage_safe_split(
            reordered, replace(spec, shared_case_groups=(("c2", "c1"), ("c1", "c0")))
        )
    )
    assert first == second
    assert ("c0", "c1", "c2") in first.atomic_case_groups
    partitions = (
        first.partitions.train_case_ids,
        first.partitions.validation_case_ids,
        first.partitions.test_case_ids,
    )
    assert sum(set(("c0", "c1", "c2")) <= set(ids) for ids in partitions) == 1
    assert sorted(x for ids in partitions for x in ids) == [f"c{i}" for i in range(6)]


def test_chronological_split_merges_intervals_not_just_case_start_order():
    source = log(
        ("a", (event("a1", 1), event("a2", 10))),
        ("b", (event("b1", 5), event("b2", 6))),
        ("c", (event("c1", 11), event("c2", 12))),
    )
    value = computed(
        leakage_safe_split(
            source, LeakageSplitSpec(strategy="chronological", train_fraction=0.5)
        )
    )
    assert value.atomic_case_groups == (("a", "b"), ("c",))
    assert value.partitions.train_case_ids == ("a", "b")
    assert value.partitions.test_case_ids == ("c",)


def test_shared_case_group_interval_absorbs_unlinked_cases_between_its_endpoints():
    source = cases_for_split()
    spec = LeakageSplitSpec(
        strategy="chronological", train_fraction=0.5, shared_case_groups=(("c0", "c3"),)
    )
    value = computed(leakage_safe_split(source, spec))
    assert value.atomic_case_groups == (("c0", "c1", "c2", "c3"), ("c4",), ("c5",))


def test_equal_time_boundary_and_late_label_availability_cannot_cross_partitions():
    source = log(
        ("a", (event("a1", 0),)), ("b", (event("b1", 10),)), ("c", (event("c1", 20),))
    )
    spec = LeakageSplitSpec(
        strategy="chronological",
        train_fraction=0.5,
        case_available_until=(CaseAvailability("a", at(10)),),
    )
    value = computed(leakage_safe_split(source, spec))
    assert value.atomic_case_groups == (("a", "b"), ("c",))
    impossible = leakage_safe_split(
        source, replace(spec, case_available_until=(CaseAvailability("a", at(20)),))
    )
    assert impossible.status is ComputeStatus.UNAVAILABLE
    assert impossible.value is None
    assert impossible.issues[0].code == "indivisible_split"


def test_three_nonempty_partitions_are_created_only_if_three_blocks_exist():
    source = cases_for_split()
    spec = LeakageSplitSpec(
        strategy="chronological", train_fraction=0.8, validation_fraction=0.1
    )
    value = computed(leakage_safe_split(source, spec))
    assert value.partition_group_counts == (4, 1, 1)
    too_small = replace(source, traces=source.traces[:2])
    assert leakage_safe_split(too_small, spec).status is ComputeStatus.UNAVAILABLE


@pytest.mark.parametrize(
    "train,validation,counts",
    [
        (0.8, 0.2, (4, 2, 0)),
        (1.0, 0.0, (6, 0, 0)),
        (0.0, 1.0, (0, 6, 0)),
        (0.0, 0.0, (0, 0, 6)),
    ],
)
def test_zero_fraction_partitions_do_not_receive_rounding_remainders(
    train, validation, counts
):
    value = computed(
        leakage_safe_split(
            cases_for_split(),
            LeakageSplitSpec(train_fraction=train, validation_fraction=validation),
        )
    )
    assert value.partition_group_counts == counts


@pytest.mark.parametrize(
    "spec",
    [
        LeakageSplitSpec(shared_case_groups=(("missing", "c0"),)),
        LeakageSplitSpec(
            strategy="chronological",
            case_available_until=(CaseAvailability("c1", at(0)),),
        ),
        LeakageSplitSpec(
            strategy="chronological",
            case_available_until=(CaseAvailability("missing", at(30)),),
        ),
    ],
)
def test_invalid_group_and_availability_references_do_not_produce_splits(spec):
    assert (
        leakage_safe_split(cases_for_split(), spec).status
        is ComputeStatus.INVALID_INPUT
    )


def test_group_hash_does_not_consult_case_clocks_but_chronology_requires_them():
    source = log(("a", (event("a1", None),)), ("b", ()))
    computed(leakage_safe_split(source))
    assert (
        leakage_safe_split(source, LeakageSplitSpec(strategy="chronological")).status
        is ComputeStatus.INVALID_INPUT
    )


def event_encoder(source, *, train=("train",), cutoff=10):
    spec = ObservationEncoderSpec(
        ObservationSpec(at(cutoff)),
        FeatureSpec(
            level="event",
            numeric_attributes=("number",),
            categorical_attributes=("category",),
        ),
    )
    return computed(fit_observation_encoder(source, spec, training_case_ids=train))


def test_train_only_schema_unknown_masks_and_real_zero_are_distinct():
    source = log(
        (
            "train",
            (
                event("a", 0, "A", number=0, category="red"),
                event("b", 1, "B", number=5, category="blue"),
                event("future", 30, "SECRET", category="future"),
            ),
        ),
        (
            "test",
            (event("u", 0, "UNSEEN", category="new"), event("v", 1, "A", number=0)),
        ),
    )
    encoder = event_encoder(source)
    assert encoder.fitted_model.training_case_ids == ("train",)
    assert encoder.fitted_model.document_count == 2
    assert tuple(column.terms for column in encoder.fitted_model.columns[:2]) == (
        ("A",),
        ("B",),
    )
    result = transform_observations(source, encoder)
    assert result.status is ComputeStatus.PARTIAL
    value = result.value
    assert value.matrix.columns == encoder.fitted_model.columns
    a, b, u, v = value.matrix.rows
    assert a.values == (1.0, 0.0, 0.0, 0.0, 1.0)
    assert value.known_masks[0] == (True,) * 5
    assert u.values == (0.0, 0.0, None, None, None)
    assert value.known_masks[2] == (True, True, False, False, False)
    assert v.values == (1.0, 0.0, 0.0, None, None)
    assert u.unknown_term_count == 2
    assert b.values[2] == 5.0


def test_held_out_invalid_clocks_are_never_read_during_fit():
    source = log(("train", (event("a", 0),)), ("test", (event("bad", None),)))
    spec = ObservationEncoderSpec(ObservationSpec(at(5)))
    value = computed(
        fit_observation_encoder(source, spec, training_case_ids=("train",))
    )
    assert value.fitted_model.document_count == 1
    empty = computed(fit_observation_encoder(source, spec, training_case_ids=()))
    assert empty.fitted_model.document_count == 0
    assert empty.fitted_model.columns == ()


def test_trace_attributes_are_rejected_without_an_availability_contract():
    with pytest.raises(ValueError, match="availability"):
        ObservationEncoderSpec(
            ObservationSpec(at(5)), FeatureSpec(numeric_attributes=("outcome",))
        )


def test_event_sequences_distinguish_padding_unknowns_and_known_zero():
    source = log(
        (
            "train",
            (
                event("a", 0, number=0, category="red"),
                event("b", 1, number=5, category="blue"),
            ),
        ),
        ("test", (event("u", 0, category="unknown"),)),
    )
    encoder = event_encoder(source)
    result = encode_case_sequences(
        source, encoder, CaseSequenceSpec(length=3, padding="left")
    )
    assert result.status is ComputeStatus.PARTIAL
    train, test = result.value.rows
    assert train.event_ids == (None, "a", "b")
    assert train.event_mask == (False, True, True)
    assert train.values[0] == (None,) * len(result.value.columns)
    assert train.known_masks[0] == (False,) * len(result.value.columns)
    assert train.values[1][1] == 0.0
    assert train.known_masks[1][1]
    assert test.event_mask == (False, False, True)
    assert test.known_masks[-1] == (True, False, False, False)
    assert test.values[-1] == (1.0, None, None, None)
    assert train.unknown_term_counts == (None, 0, 0)
    assert test.unknown_term_counts == (None, None, 1)
    assert result.value.column_units == (
        "occurrences",
        "unspecified",
        "indicator",
        "indicator",
    )


def test_numeric_units_are_explicit_and_survive_sequence_encoding():
    source = log(("train", (event("a", 0, number=5),)))
    spec = ObservationEncoderSpec(
        ObservationSpec(at(5)),
        FeatureSpec(level="event", numeric_attributes=("number",)),
        numeric_units=(("number", "seconds"),),
    )
    encoder = computed(
        fit_observation_encoder(source, spec, training_case_ids=("train",))
    )
    matrix = computed(transform_observations(source, encoder))
    assert matrix.column_units == ("occurrences", "seconds")
    tensor = computed(encode_case_sequences(source, encoder, CaseSequenceSpec(2)))
    assert tensor.column_units == matrix.column_units


def test_sequence_unseen_activity_is_retained_even_when_all_known_counts_are_zero():
    source = log(("train", (event("a", 0),)), ("test", (event("b", 0, "NEW"),)))
    spec = ObservationEncoderSpec(ObservationSpec(at(5)), FeatureSpec(level="event"))
    encoder = computed(
        fit_observation_encoder(source, spec, training_case_ids=("train",))
    )
    value = encode_case_sequences(source, encoder, CaseSequenceSpec(2)).value
    test = value.rows[1]
    assert test.values == ((0.0,), (None,))
    assert test.known_masks == ((True,), (False,))
    assert test.unknown_term_counts == (1, None)


def test_dense_matrix_and_sequence_limits_are_checked_before_feature_allocation(
    monkeypatch,
):
    import pix.case_centric.feature_dataset as dataset

    source = log(("train", (event("a", 0), event("b", 1, "B"), event("c", 2, "C"))))
    spec = ObservationEncoderSpec(ObservationSpec(at(5)), FeatureSpec(level="event"))
    encoder = computed(
        fit_observation_encoder(source, spec, training_case_ids=("train",))
    )

    def must_not_transform(*args, **kwargs):
        raise AssertionError("numeric feature allocation was reached despite the limit")

    monkeypatch.setattr(dataset, "transform_features", must_not_transform)
    limited = replace(encoder, parameters=replace(spec, max_feature_cells=8))
    assert transform_observations(source, limited).status is ComputeStatus.UNAVAILABLE
    # The final truncated tensor is only 3 cells, but the intermediate is 9.
    result = encode_case_sequences(
        source, encoder, CaseSequenceSpec(1, truncation="oldest", max_cells=8)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


@pytest.mark.parametrize(
    "next_time,remaining,already_complete",
    [
        (8.0, 3.0, False),
        (0.0, 3.0, False),
        (1.0, 0.0, False),
    ],
)
def test_prediction_target_contract_rejects_events_outside_case_lifetime(
    next_time, remaining, already_complete
):
    with pytest.raises(ValueError):
        CensoredPredictionTarget(
            "c",
            "observed",
            "B",
            next_time,
            "completed",
            remaining,
            already_complete,
            10.0,
        )


def test_sequence_truncation_is_explicit_and_retains_dropped_identity():
    source = log(
        (
            "train",
            (
                event("a", 0, number=1, category="x"),
                event("b", 1, number=2, category="x"),
            ),
        )
    )
    encoder = event_encoder(source)
    rejected = encode_case_sequences(source, encoder, CaseSequenceSpec(1))
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert rejected.value is None
    shortened = encode_case_sequences(
        source, encoder, CaseSequenceSpec(1, truncation="oldest")
    )
    assert shortened.status is ComputeStatus.PARTIAL
    assert shortened.value.rows[0].event_ids == ("b",)
    assert shortened.value.rows[0].truncated_event_ids == ("a",)
    limited = encode_case_sequences(source, encoder, CaseSequenceSpec(10**8))
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None


def test_sequence_default_right_padding_and_empty_schema_still_enforce_cell_limit():
    source = log(("train", (event("a", 0),)))
    spec = ObservationEncoderSpec(
        ObservationSpec(at(5)), FeatureSpec(level="event", include_activity=False)
    )
    encoder = computed(
        fit_observation_encoder(source, spec, training_case_ids=("train",))
    )
    value = computed(encode_case_sequences(source, encoder, CaseSequenceSpec(2)))
    assert value.rows[0].event_ids == ("a", None)
    assert value.rows[0].values == ((), ())
    assert (
        encode_case_sequences(
            source, encoder, CaseSequenceSpec(11, max_cells=10)
        ).status
        is ComputeStatus.UNAVAILABLE
    )


def test_new_results_round_trip_with_typed_dates_models_masks_and_censoring(
    monkeypatch,
):
    import pix.results as persistence

    monkeypatch.setattr(persistence, "_schemas", lambda: RESULT_SCHEMAS)
    source = log(
        ("train", (event("a", 0, number=0, category="x"),)), ("test", (event("b", 10),))
    )
    spec = ObservationEncoderSpec(
        ObservationSpec(at(10)),
        FeatureSpec(level="event", numeric_attributes=("number",)),
    )
    fitted = fit_observation_encoder(source, spec, training_case_ids=("train",))
    results = (
        observation_dataset(
            source,
            spec.observation,
            follow_up=(
                CaseFollowUp("train", at(15), at(15)),
                CaseFollowUp("test", at(10)),
            ),
        ),
        leakage_safe_split(source, LeakageSplitSpec(strategy="chronological")),
        fitted,
        transform_observations(source, fitted.value),
        encode_case_sequences(source, fitted.value, CaseSequenceSpec(3)),
    )
    for result in results:
        assert (
            persistence.result_from_json(persistence.result_json_bytes(result))
            == result
        )
        with pytest.raises(FrozenInstanceError):
            name = fields(result.value)[0].name
            setattr(result.value, name, getattr(result.value, name))


@pytest.mark.parametrize(
    "factory,kwargs",
    [
        (ObservationSpec, {"observed_at": datetime(2026, 1, 1)}),
        (ObservationSpec, {"observed_at": BASE, "label_horizon_seconds": -1}),
        (ObservationSpec, {"observed_at": BASE, "max_observed_events": True}),
        (
            CaseFollowUp,
            {"case_id": "c", "observed_until": at(1), "completed_at": at(2)},
        ),
        (LeakageSplitSpec, {"shared_case_groups": (("a", "a"),)}),
        (LeakageSplitSpec, {"shared_case_groups": ((),)}),
        (LeakageSplitSpec, {"train_fraction": 0.9, "validation_fraction": 0.2}),
        (LeakageSplitSpec, {"case_available_until": (CaseAvailability("c", BASE),)}),
        (CaseSequenceSpec, {"length": 0}),
        (CaseSequenceSpec, {"length": 1, "truncation": "silent"}),
    ],
)
def test_invalid_specs_are_rejected(factory, kwargs):
    with pytest.raises((ValueError, TypeError)):
        factory(**kwargs)
