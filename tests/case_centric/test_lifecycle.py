"""Hand-checkable lifecycle pairs, missing-evidence counterexamples and lineage."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo

import pytest

from pix.case_centric.lifecycle import (
    AdjacentIntervalSpec,
    LifecycleSpec,
    derive_adjacent_intervals,
    pair_lifecycle_events,
    restore_lifecycle_events,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseSource,
    CaseTrace,
    case_log_digest,
)

BASE = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)


def event(
    identity, lifecycle="start", minute=0, activity="A", *, extra=(), timestamp=None
):
    attributes = []
    if activity is not None:
        attributes.append(CaseAttribute("concept:name", "string", activity))
    if lifecycle is not None:
        attributes.append(CaseAttribute("lifecycle:transition", "string", lifecycle))
    if minute is not None:
        attributes.append(
            CaseAttribute("time:timestamp", "date", BASE + timedelta(minutes=minute))
        )
    elif timestamp is not None:
        attributes.append(CaseAttribute("time:timestamp", "date", timestamp))
    return CaseEvent(identity, tuple(attributes) + extra)


def log_of(*events):
    return CaseLog((CaseTrace("case", tuple(events)),))


def pairs(result):
    return [
        (row.start_event_id, row.complete_event_id, row.service_seconds)
        for row in result.value.intervals
    ]


def test_sequential_repetition_and_interleaving_are_paired_per_activity_per_case():
    log = CaseLog(
        (
            CaseTrace(
                "left",
                (
                    event("a1", "start", 0),
                    event("b1", "start", 1, "B"),
                    event("a2", "complete", 3),
                    event("b2", "complete", 6, "B"),
                    event("a3", "start", 7),
                    event("a4", "complete", 8),
                ),
            ),
            CaseTrace("right", (event("a5", "start", 1), event("a6", "complete", 2))),
            CaseTrace("empty"),
        )
    )
    result = pair_lifecycle_events(log)
    assert result.status is ComputeStatus.COMPUTED
    assert pairs(result) == [
        ("a1", "a2", 180.0),
        ("b1", "b2", 300.0),
        ("a3", "a4", 60.0),
        ("a5", "a6", 60.0),
    ]
    assert result.value.trace_ids == ("left", "right", "empty")
    assert result.value.source_event_count == 8
    assert result.value.unmatched == ()
    assert result.source_digest == case_log_digest(log)


@pytest.mark.parametrize(
    "events",
    [
        (
            event("s1"),
            event("s2"),
            event("c1", "complete", 1),
            event("c2", "complete", 2),
        ),
        (
            event("s1"),
            event("s2"),
            event("c1", "complete", 1),
            event("s3", "start", 2),
            event("c2", "complete", 3),
            event("c3", "complete", 4),
        ),
        (event("s1"), event("s2"), event("c1", "complete", 1)),
    ],
)
def test_default_concurrent_component_is_entirely_unmatched(events):
    result = pair_lifecycle_events(log_of(*events))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.intervals == ()
    assert [item.event_id for item in result.value.unmatched] == [
        item.id for item in events
    ]
    assert {item.reason for item in result.value.unmatched} == {"ambiguous_overlap"}


def test_closed_ambiguous_component_does_not_poison_a_later_unique_pair():
    result = pair_lifecycle_events(
        log_of(
            event("s1"),
            event("s2"),
            event("c1", "complete", 1),
            event("c2", "complete", 2),
            event("s3", "start", 3),
            event("c3", "complete", 4),
        )
    )
    assert pairs(result) == [("s3", "c3", 60.0)]
    assert len(result.value.unmatched) == 4


@pytest.mark.parametrize(
    "policy,expected",
    [
        ("fifo", [("s1", "c1", 600.0), ("s2", "c2", 1080.0)]),
        ("lifo", [("s1", "c2", 1200.0), ("s2", "c1", 480.0)]),
    ],
)
def test_explicit_fifo_and_lifo_have_different_hand_calculated_pairs(policy, expected):
    log = log_of(
        event("s1", "start", 0),
        event("s2", "start", 2),
        event("c1", "complete", 10),
        event("c2", "complete", 20),
    )
    result = pair_lifecycle_events(log, LifecycleSpec(pairing_policy=policy))
    assert result.status is ComputeStatus.COMPUTED
    assert pairs(result) == expected
    assert result.spec.pairing_policy == policy


def test_instance_attribute_resolves_concurrency_without_fifo_assumption():
    def item(identity, transition, minute, instance, kind="string"):
        return event(
            identity,
            transition,
            minute,
            extra=(CaseAttribute("instance", kind, instance),),
        )

    log = log_of(
        item("s1", "start", 0, "x"),
        item("s2", "start", 2, "y"),
        item("c2", "complete", 3, "y"),
        item("c1", "complete", 5, "x"),
    )
    result = pair_lifecycle_events(
        log, LifecycleSpec(pairing_policy="instance", instance_key="instance")
    )
    assert result.status is ComputeStatus.COMPUTED
    assert pairs(result) == [("s1", "c1", 300.0), ("s2", "c2", 60.0)]
    assert len({row.instance_value for row in result.value.intervals}) == 2


def test_instance_type_is_part_of_key_and_duplicate_instance_overlap_is_unresolved():
    spec = LifecycleSpec(pairing_policy="instance", instance_key="instance")

    def item(identity, transition, kind, value):
        return event(
            identity, transition, extra=(CaseAttribute("instance", kind, value),)
        )

    typed = pair_lifecycle_events(
        log_of(
            item("s1", "start", "int", 1),
            item("s2", "start", "string", "1"),
            item("c2", "complete", "string", "1"),
            item("c1", "complete", "int", 1),
        ),
        spec,
    )
    assert pairs(typed) == [("s1", "c1", 0.0), ("s2", "c2", 0.0)]
    duplicate = pair_lifecycle_events(
        log_of(
            item("s1", "start", "int", 1),
            item("s2", "start", "int", 1),
            item("c1", "complete", "int", 1),
            item("c2", "complete", "int", 1),
        ),
        spec,
    )
    assert duplicate.value.intervals == ()
    assert {row.reason for row in duplicate.value.unmatched} == {"ambiguous_overlap"}


@pytest.mark.parametrize(
    "attribute",
    [
        None,
        CaseAttribute("instance", "null"),
        CaseAttribute("instance", "float", float("nan")),
        CaseAttribute("instance", "list"),
    ],
)
def test_missing_or_nonprimitive_instance_never_falls_back_to_activity(attribute):
    extra = () if attribute is None else (attribute,)
    result = pair_lifecycle_events(
        log_of(event("s", extra=extra), event("c", "complete", extra=extra)),
        LifecycleSpec(pairing_policy="instance", instance_key="instance"),
    )
    assert not result.value.intervals
    assert [row.reason for row in result.value.unmatched] == [
        "missing_or_invalid_instance"
    ] * 2


def test_orphans_unknown_transitions_missing_activity_and_missing_transition_are_evidenced():
    log = log_of(
        event("orphan", "complete"),
        event("unknown", "suspend"),
        event("noactivity", activity=None),
        event("notransition", None),
        event("open"),
    )
    result = pair_lifecycle_events(log)
    assert result.status is ComputeStatus.PARTIAL
    assert [row.reason for row in result.value.unmatched] == [
        "unmatched_complete",
        "unsupported_lifecycle_transition",
        "invalid_activity",
        "missing_or_invalid_lifecycle_transition",
        "unmatched_start",
    ]
    assert result.value.source_event_count == 5
    assert restore_lifecycle_events(result, log) == log


@pytest.mark.parametrize(
    "start,complete,code",
    [
        (event("s", minute=None), event("c", "complete", 1), "start_missing_timestamp"),
        (
            event("s", minute=None, timestamp=datetime(2026, 1, 1, 9)),
            event("c", "complete", 1),
            "start_naive_timestamp",
        ),
        (event("s", minute=2), event("c", "complete", 1), "negative_service_interval"),
        (
            event("s"),
            event(
                "c",
                "complete",
                None,
                extra=(CaseAttribute("time:timestamp", "string", "bad"),),
            ),
            "complete_invalid_timestamp_type",
        ),
    ],
)
def test_invalid_or_missing_time_keeps_pair_but_never_fabricates_service(
    start, complete, code
):
    result = pair_lifecycle_events(log_of(start, complete))
    assert result.status is ComputeStatus.PARTIAL
    (interval,) = result.value.intervals
    assert interval.start_event_id == "s" and interval.complete_event_id == "c"
    assert interval.service_seconds is None
    assert code in interval.time_issue_codes
    assert code in {issue.code for issue in result.issues}


def test_source_order_is_not_repaired_using_timestamps():
    result = pair_lifecycle_events(
        log_of(event("c", "complete", 5), event("s", "start", 0))
    )
    assert not result.value.intervals
    assert [row.reason for row in result.value.unmatched] == [
        "unmatched_complete",
        "unmatched_start",
    ]


def test_elapsed_time_uses_utc_even_across_offset_change():
    start = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=2)))
    end = datetime(2026, 10, 25, 2, 30, tzinfo=timezone(timedelta(hours=1)))
    result = pair_lifecycle_events(
        log_of(
            event("s", minute=None, timestamp=start),
            event("c", "complete", minute=None, timestamp=end),
        )
    )
    assert pairs(result) == [("s", "c", 3600.0)]


def test_output_timestamps_are_utc_across_a_fold_in_one_timezone_object():
    class FoldZone(tzinfo):
        def utcoffset(self, dt):
            return timedelta(hours=1 if dt.fold else 2)

        def dst(self, dt):
            return timedelta(0)

    zone = FoldZone()
    start = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=0)
    complete = datetime(2026, 10, 25, 2, 30, tzinfo=zone, fold=1)
    log = log_of(
        event("s", minute=None, timestamp=start),
        event("c", "complete", minute=None, timestamp=complete),
    )
    result = pair_lifecycle_events(log)
    (interval,) = result.value.intervals
    assert interval.service_seconds == 3600.0
    assert interval.start_time == datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc)
    assert interval.complete_time == datetime(2026, 10, 25, 1, 30, tzinfo=timezone.utc)
    assert interval.start_time.tzinfo is interval.complete_time.tzinfo is timezone.utc
    assert restore_lifecycle_events(result, log).traces[0].events[0].timestamp is start


def test_timestamp_that_cannot_be_represented_in_utc_is_explicitly_unknown():
    start = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    result = pair_lifecycle_events(
        log_of(event("s", minute=None, timestamp=start), event("c", "complete", 1))
    )
    (interval,) = result.value.intervals
    assert interval.start_time is None and interval.service_seconds is None
    assert "start_timestamp_out_of_range" in interval.time_issue_codes


def test_explicit_classifier_transition_and_timestamp_keys_preserve_source_records():
    def mapped(identity, transition, minute):
        return CaseEvent(
            identity,
            (
                CaseAttribute("task", "string", "Pack"),
                CaseAttribute("region", "int", 7),
                CaseAttribute("transition", "string", transition),
                CaseAttribute("observed", "date", BASE + timedelta(minutes=minute)),
            ),
        )

    log = CaseLog(
        (CaseTrace("case", (mapped("s", "begin", 0), mapped("c", "end", 3))),),
        classifiers=(CaseClassifier("compound", ("task", "region")),),
    )
    spec = LifecycleSpec(
        CaseTraceSpec(classifier="compound", timestamp_key="observed"),
        transition_key="transition",
        start_value="begin",
        complete_value="end",
    )
    result = pair_lifecycle_events(log, spec)
    assert pairs(result) == [("s", "c", 180.0)]
    assert result.value.intervals[0].activity == '[["string","Pack"],["int",7]]'
    assert restore_lifecycle_events(result, log) == log


def test_classifier_that_includes_lifecycle_is_not_silently_rewritten():
    log = replace(
        log_of(event("s"), event("c", "complete", 1)),
        classifiers=(
            CaseClassifier("combined", ("concept:name", "lifecycle:transition")),
        ),
    )
    result = pair_lifecycle_events(
        log, LifecycleSpec(CaseTraceSpec(classifier="combined"))
    )
    assert result.value.intervals == ()
    assert len(result.value.unmatched) == 2


def test_empty_log_and_empty_traces_have_known_zero_counts():
    for log in (CaseLog(), CaseLog((CaseTrace("empty"),))):
        result = pair_lifecycle_events(log)
        assert result.status is ComputeStatus.COMPUTED
        assert result.value.source_event_count == 0
        assert restore_lifecycle_events(result, log) == log


def test_missing_classifier_is_invalid_even_for_empty_log():
    spec = LifecycleSpec(CaseTraceSpec(classifier="undeclared"))
    result = pair_lifecycle_events(CaseLog(), spec)
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.value is None


def test_source_sidecar_retains_nested_nonfinite_lexical_metadata_and_globals():
    nested = CaseAttribute(
        "list", "list", values=(CaseAttribute("x", "int", 1, lexical="01"),)
    )
    log = replace(
        log_of(
            event("s", extra=(nested, CaseAttribute("nan", "float", float("nan")))),
            event("c", "complete", 1),
        ),
        attributes=(CaseAttribute("log", "container", children=(nested,)),),
        globals=(CaseGlobal("event", (CaseAttribute("resource", "string", "R"),)),),
        metadata=(("creator", "independent test"),),
        source=CaseSource("fixture.xes", "xes", "a" * 64, 42),
    )
    result = pair_lifecycle_events(log)
    restored = restore_lifecycle_events(result, log)
    assert restored == log
    assert restored is not log
    assert restored.traces[0].events[0] is log.traces[0].events[0]
    assert restored.traces[0].events[0].attributes[-2].values[0].lexical == "01"


def test_changed_sidecar_and_tampered_result_are_rejected():
    log = log_of(event("s"), event("c", "complete", 1))
    result = pair_lifecycle_events(log)
    with pytest.raises(ValueError, match="digest"):
        restore_lifecycle_events(result, log_of(event("s"), event("c", "complete", 2)))
    forged = replace(
        result,
        value=replace(
            result.value,
            intervals=(replace(result.value.intervals[0], activity="Forged"),),
        ),
    )
    with pytest.raises(ValueError, match="evidence"):
        restore_lifecycle_events(forged, log)


def test_policy_and_source_order_change_identity_and_payloads_are_frozen():
    log = log_of(
        event("s1"), event("s2"), event("c1", "complete", 1), event("c2", "complete", 2)
    )
    default = pair_lifecycle_events(log)
    fifo = pair_lifecycle_events(log, LifecycleSpec(pairing_policy="fifo"))
    lifo = pair_lifecycle_events(log, LifecycleSpec(pairing_policy="lifo"))
    assert len({item.computation_id for item in (default, fifo, lifo)}) == 3
    assert fifo == pair_lifecycle_events(log, LifecycleSpec(pairing_policy="fifo"))
    reordered = replace(
        log,
        traces=(replace(log.traces[0], events=tuple(reversed(log.traces[0].events))),),
    )
    assert pair_lifecycle_events(reordered).source_digest != default.source_digest
    with pytest.raises(FrozenInstanceError):
        fifo.value.intervals[0].service_seconds = 2.0
    with pytest.raises(FrozenInstanceError):
        fifo.spec.pairing_policy = "lifo"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pairing_policy": "automatic"},
        {"pairing_policy": "instance"},
        {"instance_key": "instance"},
        {"start_value": "complete"},
        {"trace_spec": None},
        {"transition_key": ""},
    ],
)
def test_invalid_pairing_contract_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        LifecycleSpec(**kwargs)


def test_adjacent_paths_use_explicit_start_and_completion_endpoints():
    log = log_of(
        event("A", "complete", 5),
        event(
            "B",
            "complete",
            15,
            "B",
            extra=(CaseAttribute("start", "date", BASE + timedelta(minutes=10)),),
        ),
        event(
            "C",
            "complete",
            25,
            "C",
            extra=(CaseAttribute("start", "date", BASE + timedelta(minutes=20)),),
        ),
    )
    result = derive_adjacent_intervals(log, AdjacentIntervalSpec("start"))
    assert result.status is ComputeStatus.COMPUTED
    assert [
        (row.source_event_id, row.target_event_id, row.duration_seconds)
        for row in result.value.intervals
    ] == [("A", "B", 300.0), ("B", "C", 300.0)]
    completions = derive_adjacent_intervals(
        log, AdjacentIntervalSpec(None, endpoint_policy="completion_to_completion")
    )
    assert [row.duration_seconds for row in completions.value.intervals] == [
        600.0,
        600.0,
    ]
    assert completions.computation_id != result.computation_id


@pytest.mark.parametrize(
    "start,code",
    [
        (None, "target_missing_timestamp"),
        (BASE + timedelta(minutes=4), "negative_adjacent_interval"),
        (datetime(2026, 1, 1, 9, 10), "target_naive_timestamp"),
    ],
)
def test_adjacent_missing_or_invalid_start_never_uses_completion_fallback(start, code):
    extra = () if start is None else (CaseAttribute("start", "date", start),)
    result = derive_adjacent_intervals(
        log_of(event("A", "complete", 5), event("B", "complete", 15, "B", extra=extra)),
        AdjacentIntervalSpec("start"),
    )
    assert result.status is ComputeStatus.PARTIAL
    (interval,) = result.value.intervals
    assert interval.duration_seconds is None
    assert code in interval.issue_codes


def test_adjacent_source_order_does_not_bridge_missing_activity_or_case_boundaries():
    log = CaseLog(
        (
            CaseTrace(
                "one",
                (
                    event("a", "complete", 0),
                    event("unknown", "complete", 1, activity=None),
                    event("b", "complete", 2),
                ),
            ),
            CaseTrace("two", (event("c"),)),
        )
    )
    result = derive_adjacent_intervals(
        log, AdjacentIntervalSpec(None, endpoint_policy="completion_to_completion")
    )
    assert result.status is ComputeStatus.PARTIAL
    assert [
        (row.source_event_id, row.target_event_id) for row in result.value.intervals
    ] == [("a", "unknown"), ("unknown", "b")]
    assert result.value.intervals[0].target_activity is None
    assert result.value.intervals[1].source_activity is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start_timestamp_key": None},
        {"start_timestamp_key": ""},
        {"start_timestamp_key": "start", "endpoint_policy": "automatic"},
        {"start_timestamp_key": "start", "endpoint_policy": "completion_to_completion"},
    ],
)
def test_adjacent_endpoint_contract_requires_explicit_choice(kwargs):
    with pytest.raises(ValueError):
        AdjacentIntervalSpec(**kwargs)


def test_adjacent_invalid_classifier_and_empty_case():
    spec = AdjacentIntervalSpec("start", CaseTraceSpec(classifier="missing"))
    assert (
        derive_adjacent_intervals(CaseLog(), spec).status is ComputeStatus.INVALID_INPUT
    )
    result = derive_adjacent_intervals(
        CaseLog((CaseTrace("empty"),)), AdjacentIntervalSpec("start")
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.intervals == () and result.value.trace_ids == ("empty",)
