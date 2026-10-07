"""Hand-computed encodings, withheld-data isolation, prefix timing and model witnesses."""

import json
from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timedelta, timezone, tzinfo
from hashlib import sha256
from math import log, sqrt

import pytest

from pix.case_centric.features import (
    RESULT_SCHEMAS,
    CaseSplitSpec,
    FeatureColumn,
    FeatureSpec,
    ModelFeatureSpec,
    PrefixSpec,
    TemporalWindowSpec,
    fit_features,
    model_features,
    prefix_dataset,
    split_cases,
    temporal_features,
    temporal_window_features,
    transform_features,
)
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.replay import ReplaySpec
from pix.contracts.result import ComputeStatus
from pix.event_log.model import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
)

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def attribute(key, value):
    kind = {
        str: "string",
        int: "int",
        bool: "boolean",
        float: "float",
        datetime: "date",
        type(None): "null",
    }[type(value)]
    return CaseAttribute(key, kind, value)


def log_of(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                f"case-{i}",
                tuple(
                    CaseEvent(
                        f"e-{i}-{j}",
                        (
                            attribute("concept:name", activity),
                            attribute(
                                "time:timestamp", ORIGIN + timedelta(seconds=j * 10)
                            ),
                        ),
                    )
                    for j, activity in enumerate(sequence)
                ),
            )
            for i, sequence in enumerate(sequences)
        )
    )


def model(log_input, spec=FeatureSpec(), **kwargs):
    result = fit_features(log_input, spec, **kwargs)
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def matrix(log_input, spec=FeatureSpec()):
    result = transform_features(log_input, model(log_input, spec))
    assert result.status is ComputeStatus.COMPUTED, result.issues
    return result.value


def columns(value):
    return tuple(column.terms for column in value.columns)


def sequence_net():
    return PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("a", "A"), Transition("b", "B")),
        (Arc("p", "a"), Arc("a", "q"), Arc("q", "b"), Arc("b", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )


def test_activity_count_and_binary_have_hand_computed_values_including_empty_case():
    source = log_of(("A", "B", "A"), ("B",), ())
    counted = matrix(source)
    assert columns(counted) == (("A",), ("B",))
    assert tuple(row.values for row in counted.rows) == (
        (2.0, 1.0),
        (0.0, 1.0),
        (0.0, 0.0),
    )
    binary = matrix(source, FeatureSpec(encoding="binary"))
    assert tuple(row.values for row in binary.rows) == (
        (1.0, 1.0),
        (0.0, 1.0),
        (0.0, 0.0),
    )


def test_ngrams_keep_order_and_label_boundaries_without_delimiter_collision():
    source = log_of(("A B", "C"), ("A", "B C"), ("A", "B", "A", "B"))
    value = matrix(source, FeatureSpec(ngram_min=2, ngram_max=2))
    assert columns(value) == (("A", "B"), ("A", "B C"), ("A B", "C"), ("B", "A"))
    assert value.rows[0].values == (0.0, 0.0, 1.0, 0.0)
    assert value.rows[1].values == (0.0, 1.0, 0.0, 0.0)
    assert value.rows[2].values == (2.0, 0.0, 0.0, 1.0)
    assert matrix(source, FeatureSpec(ngram_min=10**8, ngram_max=10**9)).columns == ()


def test_smooth_tfidf_counts_empty_documents_and_optional_l2_only_activity_block():
    source = log_of(("A", "A", "B"), ("B",), ())
    value = matrix(source, FeatureSpec(encoding="tfidf"))
    idf_a, idf_b = log(4 / 2) + 1, log(4 / 3) + 1
    assert value.rows[0].values == pytest.approx((2 * idf_a, idf_b))
    assert value.rows[1].values == pytest.approx((0, idf_b))
    assert value.rows[2].values == (0.0, 0.0)
    normalized = matrix(
        source, FeatureSpec(encoding="tfidf", normalize_activity_l2=True)
    )
    norm = sqrt((2 * idf_a) ** 2 + idf_b**2)
    assert normalized.rows[0].values == pytest.approx((2 * idf_a / norm, idf_b / norm))
    assert normalized.rows[1].values == (0.0, 1.0)
    assert normalized.rows[2].values == (0.0, 0.0)


def test_event_encoding_uses_event_documents_not_case_document_frequency():
    source = log_of(("A", "A", "B"), ("B",), ())
    fitted = model(source, FeatureSpec(level="event", encoding="tfidf"))
    assert fitted.document_count == 4
    assert fitted.weights == pytest.approx((log(5 / 3) + 1, log(5 / 3) + 1))
    output = transform_features(source, fitted).value
    assert len(output.rows) == 4
    assert output.rows[0].event_id == "e-0-0"
    assert output.rows[0].values == pytest.approx((log(5 / 3) + 1, 0))


def test_fit_case_subset_does_not_read_held_out_activities_categories_or_numeric_values():
    source = log_of(("A",), ("FUTURE_SECRET",))
    train = replace(
        source.traces[0],
        attributes=(attribute("risk", "normal"), attribute("cost", 12)),
    )
    test = replace(
        source.traces[1],
        attributes=(attribute("risk", "future"), attribute("cost", float("inf"))),
    )
    source = replace(source, traces=(train, test))
    spec = FeatureSpec(
        encoding="tfidf", categorical_attributes=("risk",), numeric_attributes=("cost",)
    )
    fitted = model(source, spec, training_case_ids=("case-0",))
    assert fitted.document_count == 1
    assert fitted.training_case_ids == ("case-0",)
    assert columns(fitted) == (("A",), (), ('["string","normal"]',))
    assert fitted.weights == (1.0, 1.0, 1.0)
    modified_test = replace(
        test, attributes=(attribute("risk", "different"), attribute("cost", "invalid"))
    )
    modified = replace(source, traces=(train, modified_test))
    assert (
        model(modified, spec, training_case_ids=("case-0",)).model_digest
        == fitted.model_digest
    )


def test_unknown_transform_categories_and_terms_are_reported_without_refitting():
    train = log_of(("A", "B"))
    test = log_of(("A", "FUTURE", "FUTURE"))
    fitted = model(train)
    output = transform_features(test, fitted)
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[0].values == (1.0, 0.0)
    assert output.value.rows[0].unknown_term_count == 2
    assert output.value.model_digest == fitted.model_digest
    assert columns(fitted) == (("A",), ("B",))


def test_minimum_document_frequency_counts_documents_not_repetition():
    source = log_of(("A", "A", "A", "B"), ("B",))
    fitted = model(source, FeatureSpec(min_document_frequency=2))
    assert columns(fitted) == (("B",),)
    output = transform_features(source, fitted)
    assert output.value.rows[0].values == (1.0,)
    assert output.value.rows[0].unknown_term_count == 3


def test_trace_numeric_categorical_defaults_and_explicit_values_are_distinct():
    source = log_of(("A",), ("A",))
    source = replace(
        source,
        globals=(CaseGlobal("trace", (attribute("cost", 2), attribute("flag", True))),),
        traces=(
            source.traces[0],
            replace(
                source.traces[1],
                attributes=(attribute("cost", 0), attribute("flag", 1)),
            ),
        ),
    )
    value = matrix(
        source,
        FeatureSpec(
            numeric_attributes=("cost",),
            categorical_attributes=("flag",),
            normalize_activity_l2=True,
        ),
    )
    assert columns(value) == (("A",), (), ('["boolean",true]',), ('["int",1]',))
    assert value.rows[0].values == (1.0, 2.0, 1.0, 0.0)
    assert value.rows[1].values == (1.0, 0.0, 0.0, 1.0)


def test_event_attributes_resolve_event_globals_and_do_not_read_trace_attributes():
    source = log_of(("A", "B"))
    source = replace(
        source,
        globals=(CaseGlobal("event", (attribute("load", 4),)),),
        traces=(replace(source.traces[0], attributes=(attribute("load", 99),)),),
    )
    value = matrix(source, FeatureSpec(level="event", numeric_attributes=("load",)))
    assert value.rows[0].values[-1] == value.rows[1].values[-1] == 4.0


def test_missing_values_keep_none_and_missing_indicator_while_unknown_category_is_separate():
    source = log_of(("A",), ("A",), ("A",))
    source = replace(
        source,
        traces=(
            replace(
                source.traces[0],
                attributes=(attribute("x", 3), attribute("kind", "known")),
            ),
            source.traces[1],
            replace(source.traces[2], attributes=(attribute("kind", "unknown"),)),
        ),
    )
    fitted = model(
        source,
        FeatureSpec(numeric_attributes=("x",), categorical_attributes=("kind",)),
        training_case_ids=("case-0",),
    )
    output = transform_features(source, fitted)
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[1].values == (1.0, None, 0.0)
    assert output.value.rows[1].missing_attributes == ("x", "kind")
    assert output.value.rows[1].unknown_term_count == 0
    assert output.value.rows[2].missing_attributes == ("x",)
    assert output.value.rows[2].unknown_term_count == 1


@pytest.mark.parametrize("duplicate_scope", ["recorded", "global"])
def test_duplicate_attribute_keys_are_rejected_instead_of_arbitrarily_selected(
    duplicate_scope,
):
    source = log_of(("A",))
    attributes = (attribute("x", 1), attribute("x", 2))
    if duplicate_scope == "recorded":
        source = replace(
            source, traces=(replace(source.traces[0], attributes=attributes),)
        )
    else:
        source = replace(source, globals=(CaseGlobal("trace", attributes),))
    output = fit_features(source, FeatureSpec(numeric_attributes=("x",)))
    assert output.status is ComputeStatus.INVALID_INPUT
    assert "ambiguous" in output.issues[0].message


def test_attribute_only_features_do_not_require_activity_mapping():
    source = CaseLog((CaseTrace("c", (CaseEvent("e"),), (attribute("x", 7),)),))
    value = matrix(
        source, FeatureSpec(include_activity=False, numeric_attributes=("x",))
    )
    assert value.rows[0].values == (7.0,)


@pytest.mark.parametrize("value", [float("inf"), float("nan"), "7", True, 10**1000])
def test_numeric_feature_rejects_nonfinite_or_non_numeric_values(value):
    source = log_of(("A",))
    source = replace(
        source, traces=(replace(source.traces[0], attributes=(attribute("x", value),)),)
    )
    output = fit_features(source, FeatureSpec(numeric_attributes=("x",)))
    assert output.status is ComputeStatus.INVALID_INPUT


def test_zero_cases_explicit_empty_training_and_zero_vocabulary_remain_well_defined():
    fitted = model(CaseLog(), FeatureSpec(encoding="tfidf"))
    assert fitted.document_count == 0
    assert fitted.columns == fitted.weights == fitted.training_case_ids == ()
    assert transform_features(CaseLog(), fitted).value.rows == ()
    empty = model(log_of(("A",)), training_case_ids=())
    assert empty.document_count == 0
    output = transform_features(log_of(("A",)), empty)
    assert output.value.rows[0].values == ()
    assert output.value.rows[0].unknown_term_count == 1


def test_unknown_training_case_is_invalid_and_duplicate_selection_is_rejected():
    assert (
        fit_features(log_of(("A",)), training_case_ids=("absent",)).status
        is ComputeStatus.INVALID_INPUT
    )
    with pytest.raises(ValueError):
        fit_features(log_of(("A",)), training_case_ids=("case-0", "case-0"))


def test_model_identity_covers_training_facts_not_just_vocabulary_and_is_immutable():
    original = model(log_of(("A", "B")))
    changed = model(log_of(("A", "A", "B")))
    assert original.columns == changed.columns
    assert original.model_digest != changed.model_digest
    with pytest.raises(FrozenInstanceError):
        original.document_count = 99
    with pytest.raises(ValueError, match="digest"):
        replace(original, weights=(2.0, 1.0))
    a = transform_features(log_of(("A",)), original)
    b = transform_features(log_of(("A",)), changed)
    assert a.computation_id != b.computation_id


def test_classifier_is_shared_with_native_case_projection_and_preserves_type_tags():
    source = log_of(("A", "A"))
    source = replace(
        source,
        classifiers=(
            CaseClassifier("with_lifecycle", ("concept:name", "lifecycle:transition")),
        ),
        globals=(
            CaseGlobal("event", (attribute("lifecycle:transition", "complete"),)),
        ),
    )
    from pix.contracts.case_log import CaseTraceSpec

    value = matrix(
        source, FeatureSpec(trace_spec=CaseTraceSpec(classifier="with_lifecycle"))
    )
    assert value.rows[0].values == (2.0,)
    assert value.columns[0].terms == ('[["string","A"],["string","complete"]]',)


def test_temporal_event_features_are_hand_computed_and_do_not_include_future_end():
    output = temporal_features(log_of(("A", "B", "C")))
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.rows[0].values == (1.0, 0.0, 0.0, 0.0, 3.0, 0.0)
    assert output.value.rows[1].values[:3] == (2.0, 10.0, 10.0)
    assert output.value.rows[2].values[:3] == (3.0, 20.0, 10.0)
    shortened = temporal_features(log_of(("A", "B")))
    assert output.value.rows[:2] == shortened.value.rows


def test_temporal_times_compare_instants_and_report_local_calendar_with_offset():
    source = log_of(("A", "B"))
    events = source.traces[0].events
    events = (
        replace(
            events[0],
            attributes=(
                attribute("concept:name", "A"),
                attribute(
                    "time:timestamp",
                    datetime(2026, 1, 1, 9, tzinfo=timezone(timedelta(hours=9))),
                ),
            ),
        ),
        replace(
            events[1],
            attributes=(
                attribute("concept:name", "B"),
                attribute(
                    "time:timestamp", datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
                ),
            ),
        ),
    )
    source = replace(source, traces=(replace(source.traces[0], events=events),))
    value = temporal_features(source).value
    assert value.rows[0].values[3:] == (9.0, 3.0, 32400.0)
    assert value.rows[1].values[:3] == (2.0, 60.0, 60.0)


def test_shared_dst_timezone_fold_uses_utc_elapsed_time_for_features_and_targets():
    class FoldTimezone(tzinfo):
        def utcoffset(self, value):
            return timedelta(hours=-5 if value.fold else -4)

        def dst(self, value):
            return timedelta(hours=0 if value.fold else 1)

    shared_zone = FoldTimezone()
    source = log_of(("A", "B"))
    instants = (
        datetime(2026, 11, 1, 1, 30, tzinfo=shared_zone, fold=0),
        datetime(2026, 11, 1, 1, 45, tzinfo=shared_zone, fold=1),
    )
    events = tuple(
        replace(
            event,
            attributes=(
                attribute("concept:name", event.activity),
                attribute("time:timestamp", instant),
            ),
        )
        for event, instant in zip(source.traces[0].events, instants)
    )
    source = replace(source, traces=(replace(source.traces[0], events=events),))
    assert temporal_features(source).value.rows[1].values[:3] == (2.0, 4500.0, 4500.0)
    targets = prefix_dataset(source).value.targets
    assert targets[0].next_time_seconds == targets[0].remaining_time_seconds == 4500.0


def test_valid_datetime_boundary_does_not_require_representable_utc_datetime():
    source = log_of(("A", "B"))
    offset = timezone(timedelta(hours=2))
    instants = (
        datetime(1, 1, 1, 0, tzinfo=offset),
        datetime(1, 1, 1, 1, tzinfo=offset),
    )
    events = tuple(
        replace(
            event,
            attributes=(
                attribute("concept:name", event.activity),
                attribute("time:timestamp", instant),
            ),
        )
        for event, instant in zip(source.traces[0].events, instants)
    )
    source = replace(source, traces=(replace(source.traces[0], events=events),))
    assert temporal_features(source).value.rows[1].values[:3] == (2.0, 3600.0, 3600.0)


def test_missing_and_decreasing_timestamps_remain_unknown_and_do_not_reorder_events():
    source = log_of(("A", "B", "C"))
    events = source.traces[0].events
    events = (
        events[0],
        replace(events[1], attributes=(attribute("concept:name", "B"),)),
        replace(
            events[2],
            attributes=(
                attribute("concept:name", "C"),
                attribute("time:timestamp", ORIGIN - timedelta(seconds=1)),
            ),
        ),
    )
    source = replace(source, traces=(replace(source.traces[0], events=events),))
    output = temporal_features(source)
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[1].values == (2.0, None, None, None, None, None)
    assert output.value.rows[2].values[:3] == (3.0, None, None)
    assert tuple(row.event_id for row in output.value.rows) == tuple(
        event.id for event in events
    )


def test_prefix_inputs_and_future_labels_have_hand_computed_separate_values():
    output = prefix_dataset(log_of(("A", "B", "C")), PrefixSpec(min_length=0))
    assert output.status is ComputeStatus.COMPUTED
    inputs, targets = output.value.inputs, output.value.targets
    assert tuple(item.activities for item in inputs) == (
        (),
        ("A",),
        ("A", "B"),
        ("A", "B", "C"),
    )
    assert tuple(item.elapsed_seconds for item in inputs) == (None, 0.0, 10.0, 20.0)
    assert tuple(item.next_activity for item in targets) == ("A", "B", "C", None)
    assert tuple(item.next_time_seconds for item in targets) == (None, 10.0, 10.0, None)
    assert tuple(item.remaining_time_seconds for item in targets) == (
        None,
        20.0,
        10.0,
        0.0,
    )
    assert tuple(item.is_terminal for item in targets) == (False, False, False, True)
    assert not hasattr(inputs[0], "next_activity")
    assert not hasattr(inputs[0], "remaining_time_seconds")


def test_prefix_inputs_do_not_change_when_future_activity_time_or_case_attributes_change():
    first = log_of(("A", "B", "C"))
    second = log_of(("A", "B", "FUTURE_SECRET"))
    trace = second.traces[0]
    event = replace(
        trace.events[-1],
        attributes=(
            attribute("concept:name", "FUTURE_SECRET"),
            attribute("time:timestamp", ORIGIN + timedelta(days=300)),
        ),
    )
    second = replace(
        second,
        traces=(
            replace(
                trace,
                events=trace.events[:-1] + (event,),
                attributes=(attribute("outcome", "FUTURE"),),
            ),
        ),
    )
    a, b = (
        prefix_dataset(first, PrefixSpec(max_length=2)).value,
        prefix_dataset(second, PrefixSpec(max_length=2)).value,
    )
    assert a.inputs == b.inputs
    assert a.targets != b.targets


def test_empty_case_terminal_flag_is_not_an_activity_string_and_next_time_is_absent():
    source = log_of((), ("<END>",))
    output = prefix_dataset(source, PrefixSpec(min_length=0))
    assert output.value.targets[0].is_terminal
    assert output.value.targets[0].next_activity is None
    assert output.value.targets[1].next_activity == "<END>"
    assert not output.value.targets[1].is_terminal
    assert output.value.targets[0].remaining_time_seconds is None
    assert (
        len(prefix_dataset(source, PrefixSpec(include_complete=False)).value.inputs)
        == 0
    )


def test_case_splitting_is_case_disjoint_repeatable_source_order_invariant_and_seed_sensitive():
    source = log_of(*[("A", "B")] * 20)
    spec = CaseSplitSpec(0.5, 0.25, "example")
    value = split_cases(source, spec).value
    assert tuple(
        map(len, (value.train_case_ids, value.validation_case_ids, value.test_case_ids))
    ) == (10, 5, 5)
    assert not set(value.train_case_ids) & set(value.test_case_ids)
    assert set(
        value.train_case_ids + value.validation_case_ids + value.test_case_ids
    ) == {trace.id for trace in source.traces}
    assert split_cases(replace(source, traces=source.traces[::-1]), spec).value == value
    assert split_cases(source, replace(spec, seed="another")).value != value
    fitted = model(source, training_case_ids=value.train_case_ids)
    assert set(fitted.training_case_ids) == set(value.train_case_ids)
    assert split_cases(CaseLog()).value.train_case_ids == ()


def test_split_decimal_fraction_does_not_lose_case_due_to_binary_roundoff():
    source = log_of(*[("A",)] * 100)
    result = split_cases(source, CaseSplitSpec(train_fraction=0.29))
    assert len(result.value.train_case_ids) == 29
    assert len(result.value.test_case_ids) == 71


def interval_log(*traces):
    """Each event is activity, start seconds, completion seconds, resource."""
    return CaseLog(
        tuple(
            CaseTrace(
                f"c-{i}",
                tuple(
                    CaseEvent(
                        f"event-{i}-{j}",
                        (
                            attribute("concept:name", activity),
                            attribute("start", ORIGIN + timedelta(seconds=start)),
                            attribute(
                                "time:timestamp", ORIGIN + timedelta(seconds=end)
                            ),
                            attribute("org:resource", resource),
                        ),
                    )
                    for j, (activity, start, end, resource) in enumerate(trace)
                ),
            )
            for i, trace in enumerate(traces)
        )
    )


def test_window_features_use_case_weighted_metrics_and_hand_counted_relations():
    source = interval_log(
        (("A", 0, 2, "R1"), ("A", 5, 8, "R2"), ("B", 9, 12, "R1")),
        (("A", 1, 3, "R1"), ("C", 6, 7, "R1")),
    )
    output = temporal_window_features(
        source,
        TemporalWindowSpec(
            width_seconds=10, anchor=ORIGIN, start_timestamp_key="start"
        ),
    )
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.retrospective_case_aggregates
    assert output.value.requested_event_count == output.value.assigned_event_count == 5
    first, second = output.value.windows
    assert first.index == 0
    assert first.start == ORIGIN
    assert first.end == ORIGIN + timedelta(seconds=10)
    assert len(first.event_ids) == 4
    assert first.case_ids == ("c-0", "c-1")
    assert (
        first.unique_activities,
        first.unique_resources,
        first.resource_known_events,
    ) == (2, 2, 4)
    assert first.repeated_activity_events == 1
    assert first.mean_events_per_case == 2.0
    assert first.mean_cases_per_resource == first.mean_resources_per_case == 1.5
    assert first.resources_complete_case_count == 2
    assert (first.mean_case_observed_span_seconds, first.observed_span_case_count) == (
        9.0,
        2,
    )
    assert (first.mean_case_service_sum_seconds, first.service_case_count) == (5.5, 2)
    assert (first.mean_case_nonservice_span_seconds, first.nonservice_case_count) == (
        3.5,
        2,
    )
    assert (first.mean_case_interarrival_seconds, first.interarrival_case_count) == (
        1.0,
        1,
    )
    assert (first.mean_case_interfinish_seconds, first.interfinish_case_count) == (
        5.0,
        1,
    )
    assert second.case_ids == ("c-0",)
    assert second.mean_case_observed_span_seconds == 12.0
    assert second.mean_case_service_sum_seconds == 8.0
    assert second.mean_case_nonservice_span_seconds == 4.0


def test_window_service_sum_and_nonservice_union_are_distinct_under_parallel_overlap():
    source = interval_log((("A", 0, 8, "R1"), ("B", 3, 10, "R2")))
    output = temporal_window_features(
        source,
        TemporalWindowSpec(
            width_seconds=20, anchor=ORIGIN, start_timestamp_key="start"
        ),
    )
    row = output.value.windows[0]
    assert row.mean_case_observed_span_seconds == 10.0
    assert row.mean_case_service_sum_seconds == 15.0
    assert row.mean_case_nonservice_span_seconds == 0.0


def test_window_without_explicit_start_retains_unknown_service_instead_of_zero():
    source = interval_log((("A", 0, 2, "R1"), ("B", 3, 8, "R1")))
    row = temporal_window_features(
        source, TemporalWindowSpec(width_seconds=10, anchor=ORIGIN)
    ).value.windows[0]
    assert row.mean_case_observed_span_seconds == 6.0
    assert row.mean_case_service_sum_seconds is None
    assert row.service_case_count == 0
    assert row.mean_case_nonservice_span_seconds is None
    assert row.nonservice_case_count == 0
    assert row.mean_case_interarrival_seconds is None
    assert row.interarrival_case_count == 0


def test_window_boundaries_are_exact_half_open_and_allow_negative_indices_and_empty_windows():
    source = interval_log(
        (
            ("A", -2, -1, "R1"),
            ("B", 0, 9.999999, "R1"),
            ("C", 0, 10, "R1"),
            ("D", 0, 30, "R1"),
        )
    )
    spec = TemporalWindowSpec(
        width_seconds=10, anchor=ORIGIN, include_empty_windows=True
    )
    output = temporal_window_features(source, spec)
    assert tuple(window.index for window in output.value.windows) == (-1, 0, 1, 2, 3)
    assert tuple(len(window.event_ids) for window in output.value.windows) == (
        1,
        1,
        1,
        0,
        1,
    )
    empty = output.value.windows[3]
    assert empty.case_ids == ()
    assert empty.mean_events_per_case is None
    assert empty.mean_case_observed_span_seconds is None
    assert (
        temporal_window_features(source, replace(spec, max_windows=3)).status
        is ComputeStatus.UNAVAILABLE
    )


def test_window_missing_timestamp_retains_coverage_and_unknown_case_denominators():
    source = interval_log((("A", 0, 2, "R1"), ("B", 3, 8, "R1")))
    first, second = source.traces[0].events
    first = replace(first, attributes=(attribute("concept:name", "A"),))
    source = replace(
        source, traces=(replace(source.traces[0], events=(first, second)),)
    )
    output = temporal_window_features(
        source, TemporalWindowSpec(width_seconds=10, anchor=ORIGIN)
    )
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.assigned_event_count == 1
    assert output.value.excluded_event_ids == (first.id,)
    row = output.value.windows[0]
    assert row.mean_case_observed_span_seconds is None
    assert row.observed_span_case_count == 0


def test_window_missing_resources_exposes_observation_count_and_does_not_invent_resource():
    source = log_of(("A", "A"))
    output = temporal_window_features(
        source, TemporalWindowSpec(width_seconds=20, anchor=ORIGIN)
    )
    assert output.status is ComputeStatus.PARTIAL
    row = output.value.windows[0]
    assert row.unique_resources == row.resource_known_events == 0
    assert row.mean_cases_per_resource is None
    assert row.mean_resources_per_case is None
    assert row.resources_complete_case_count == 0
    assert row.repeated_activity_events == 1


def test_known_finish_times_survive_missing_starts_and_resource_denominator_excludes_unknown_cases():
    source = interval_log((("A", 0, 2, "R"),), (("A", 1, 3, "R"),), (("A", 4, 5, "R"),))
    middle = source.traces[1].events[0]
    middle = replace(
        middle,
        attributes=tuple(
            a for a in middle.attributes if a.key not in ("start", "org:resource")
        ),
    )
    source = replace(
        source,
        traces=(
            source.traces[0],
            replace(source.traces[1], events=(middle,)),
            source.traces[2],
        ),
    )
    output = temporal_window_features(
        source,
        TemporalWindowSpec(
            width_seconds=10, anchor=ORIGIN, start_timestamp_key="start"
        ),
    )
    assert output.status is ComputeStatus.PARTIAL
    row = output.value.windows[0]
    assert row.mean_case_interfinish_seconds == 1.5
    assert row.interfinish_case_count == 2
    assert row.mean_resources_per_case == 1.0
    assert row.resources_complete_case_count == 2
    assert row.mean_case_service_sum_seconds == 1.5
    assert row.service_case_count == 2


def test_zero_log_and_empty_cases_do_not_generate_time_windows():
    output = temporal_window_features(log_of(()))
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.windows == ()
    assert output.value.requested_event_count == output.value.assigned_event_count == 0


def test_prefix_materialization_limit_returns_no_truncated_training_dataset():
    source = log_of(("A", "B", "C", "D"))
    a = prefix_dataset(source, PrefixSpec(max_prefixes=3))
    b = prefix_dataset(source, PrefixSpec(max_total_prefix_events=9))
    assert a.status is b.status is ComputeStatus.UNAVAILABLE
    assert a.value is b.value is None
    assert (
        prefix_dataset(
            source, PrefixSpec(max_prefixes=4, max_total_prefix_events=10)
        ).status
        is ComputeStatus.COMPUTED
    )


def test_alignment_features_encode_exact_move_counts_and_model_identity():
    source = log_of(("A", "B"), ("A", "X", "B"))
    output = model_features(source, sequence_net())
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.rows[0].values == (0.0, 2.0, 0.0, 0.0, 0.0)
    assert output.value.rows[1].values == (1.0, 2.0, 1.0, 0.0, 0.0)
    assert output.value.model_digest == output.spec.model_digest
    assert len(output.parent_computation_ids) == 1
    changed = model_features(
        source,
        sequence_net(),
        ModelFeatureSpec(alignment=AlignmentSpec(log_move_cost=3)),
    )
    assert changed.value.rows[1].values[0] == 3.0
    assert changed.computation_id != output.computation_id


def test_token_features_use_complete_accounting_and_log_deviation_values():
    output = model_features(
        log_of(("A", "B"), ("A", "X", "B")),
        sequence_net(),
        ModelFeatureSpec(method="token_replay"),
    )
    assert output.status is ComputeStatus.COMPUTED
    assert output.value.rows[0].values == (0.0, 0.0, 3.0, 3.0, 0.0)
    assert output.value.rows[1].values == (0.0, 0.0, 3.0, 3.0, 1.0)


def test_limited_alignment_does_not_encode_incomplete_prefix_as_complete_case():
    output = model_features(
        log_of(("A", "B")),
        sequence_net(),
        ModelFeatureSpec(alignment=AlignmentSpec(max_states=1)),
    )
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[0].values == (None,) * 5
    assert output.issues[0].code == "incomplete_model_feature"


def test_limited_token_replay_does_not_encode_incomplete_prefix_as_complete_case():
    net = PetriNet(
        (Place("p"), Place("q"), Place("r")),
        (Transition("s", None), Transition("a", "A")),
        (Arc("p", "s"), Arc("s", "q"), Arc("q", "a"), Arc("a", "r")),
        Marking((("p", 1),)),
        Marking((("r", 1),)),
    )
    output = model_features(
        log_of(("A",)),
        net,
        ModelFeatureSpec(method="token_replay", replay=ReplaySpec(silent_max_states=1)),
    )
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[0].values == (None,) * 5


def test_unrepresentable_exact_model_cost_is_unknown_with_explicit_feature_issue():
    empty_accepting_net = PetriNet((), (), (), Marking(), Marking())
    output = model_features(
        log_of(("A",)),
        empty_accepting_net,
        ModelFeatureSpec(alignment=AlignmentSpec(log_move_cost=10**400)),
    )
    assert output.status is ComputeStatus.PARTIAL
    assert output.value.rows[0].values == (None, 0.0, 1.0, 0.0, 0.0)
    assert output.issues[0].code == "unrepresentable_model_feature"


@pytest.mark.parametrize(
    "new_columns,new_weights",
    [
        ((FeatureColumn("numeric", "absent"),), (1.0,)),
        ((FeatureColumn("temporal", "unknown"),), (1.0,)),
        (
            (
                FeatureColumn("activity_ngram", "activity", ("B",)),
                FeatureColumn("activity_ngram", "activity", ("A",)),
            ),
            (1.0, 1.0),
        ),
        ((FeatureColumn("activity_ngram", "activity", ("A",)),), (2.0,)),
        ((FeatureColumn("activity_ngram", "activity", ("A", "B")),), (1.0,)),
    ],
)
def test_rehashed_models_still_validate_semantics_not_just_digest(
    new_columns, new_weights
):
    original = model(log_of(("A", "B")))
    values = asdict(original)
    values.pop("model_digest")
    values.update(
        columns=[asdict(column) for column in new_columns], weights=new_weights
    )
    digest = (
        "pix.case-feature-model.v1:sha256:"
        + sha256(
            json.dumps(
                values,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
    )
    with pytest.raises(ValueError):
        replace(original, columns=new_columns, weights=new_weights, model_digest=digest)


@pytest.mark.parametrize(
    "factory,kwargs",
    [
        (FeatureSpec, {"ngram_min": 0}),
        (FeatureSpec, {"ngram_min": 3, "ngram_max": 2}),
        (FeatureSpec, {"level": "event", "ngram_max": 2}),
        (FeatureSpec, {"encoding": "bert"}),
        (FeatureSpec, {"numeric_attributes": ("x", "x")}),
        (FeatureSpec, {"numeric_attributes": ("x",), "categorical_attributes": ("x",)}),
        (FeatureSpec, {"min_document_frequency": True}),
        (CaseSplitSpec, {"train_fraction": 0.9, "validation_fraction": 0.2}),
        (CaseSplitSpec, {"train_fraction": float("nan")}),
        (CaseSplitSpec, {"train_fraction": True}),
        (PrefixSpec, {"min_length": -1}),
        (PrefixSpec, {"min_length": 5, "max_length": 2}),
    ],
)
def test_invalid_algorithm_parameters_are_rejected(factory, kwargs):
    with pytest.raises((TypeError, ValueError)):
        factory(**kwargs)


def test_all_feature_results_round_trip_through_registered_contracts(monkeypatch):
    import pix.results as persistence

    original_schemas = persistence._schemas
    monkeypatch.setattr(
        persistence, "_schemas", lambda: original_schemas() | RESULT_SCHEMAS
    )
    source = log_of(("A", "B"), ("B",))
    fitted = fit_features(source, FeatureSpec(encoding="tfidf"))
    results = (
        fitted,
        transform_features(source, fitted.value),
        temporal_features(source),
        prefix_dataset(source),
        split_cases(source),
        model_features(source, sequence_net()),
        model_features(source, sequence_net(), ModelFeatureSpec(method="token_replay")),
        temporal_window_features(
            source, TemporalWindowSpec(width_seconds=20, anchor=ORIGIN)
        ),
    )
    for result in results:
        assert (
            persistence.result_from_json(persistence.result_json_bytes(result))
            == result
        )
