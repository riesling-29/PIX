"""Independent source-ID oracles for native case-centric selection."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone, tzinfo
from itertools import product

import pytest

from pix.case_centric.filtering import (
    AttributeCondition,
    CaseFilterSpec,
    CaseSampleSpec,
    CaseSliceSpec,
    filter_case_log,
    materialize_case_selection,
    sample_cases,
    slice_cases,
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
    case_traces,
)
from pix.results import result_from_json, result_json_bytes

BASE = datetime(2026, 9, 15, tzinfo=timezone.utc)


def event(identifier, activity, minute=None, resource=None, extra=()):
    attrs = (
        () if activity is None else (CaseAttribute("concept:name", "string", activity),)
    )
    if minute is not None:
        attrs += (
            CaseAttribute("time:timestamp", "date", BASE + timedelta(minutes=minute)),
        )
    if resource is not None:
        attrs += (CaseAttribute("org:resource", "string", resource),)
    return CaseEvent(identifier, attrs + extra)


def log_for(*rows):
    return CaseLog(
        tuple(
            CaseTrace(
                f"c{i}",
                tuple(
                    event(f"c{i}e{j}", activity, j) for j, activity in enumerate(row)
                ),
            )
            for i, row in enumerate(rows)
        )
    )


def selected(result):
    assert result.value is not None, result.issues
    return tuple(entry.source_case_id for entry in result.value.entries)


def selected_events(result):
    assert result.value is not None, result.issues
    return tuple(entry.event_ids for entry in result.value.entries)


@pytest.mark.parametrize(
    "kind,kwargs,expected",
    [
        ("activity", {"activities": ("A",)}, ("c0", "c1", "c3")),
        ("start", {"activities": ("A",)}, ("c0", "c3")),
        ("end", {"activities": ("A",)}, ("c1",)),
        ("variants", {"variants": (("A", "B"), ())}, ("c0", "c2")),
        ("length", {"minimum": 2, "maximum": 2}, ("c0", "c1")),
        ("rework", {"activities": ("A",), "minimum": 2}, ("c3",)),
        ("directly_follows", {"pattern": ("A", "B")}, ("c0", "c3")),
        ("eventually_follows", {"pattern": ("B", "A")}, ("c1", "c3")),
        ("sequence", {"pattern": ("B", "A", "C")}, ("c3",)),
        ("prefix", {"pattern": ("A", "B")}, ("c0", "c3")),
        ("suffix", {"pattern": ("A", "C")}, ("c3",)),
        ("case_limit", {"top_k": 2}, ("c0", "c1")),
    ],
)
def test_case_predicate_expected_ids(kind, kwargs, expected):
    log = log_for("AB", "BA", "", "ABAC", "CCC")
    result = filter_case_log(log, CaseFilterSpec(kind=kind, **kwargs))
    assert result.status is ComputeStatus.COMPUTED
    assert selected(result) == expected
    negative = filter_case_log(log, CaseFilterSpec(kind=kind, positive=False, **kwargs))
    assert selected(negative) == tuple(
        trace.id for trace in log.traces if trace.id not in expected
    )


def test_event_view_preserves_metadata_original_facts_and_bridged_adjacency():
    source = CaseSource("private.xes", "xes", "0" * 64, 100)
    log = replace(
        log_for("AXB", "XX", ""),
        attributes=(CaseAttribute("x", "float", float("nan"), lexical="NaN"),),
        globals=(CaseGlobal("event", (CaseAttribute("region", "string", "KR"),)),),
        metadata=(("source_order", "recorded"),),
        source=source,
    )
    before = case_log_digest(log)
    result = filter_case_log(log, CaseFilterSpec(mode="events", activities=("A", "B")))
    assert selected_events(result) == (("c0e0", "c0e2"), (), ())
    assert result.value.entries[0].bridged_adjacencies == (("c0e0", "c0e2"),)
    view = materialize_case_selection(log, result)
    assert view.attributes is log.attributes
    assert view.globals is log.globals
    assert view.metadata is log.metadata
    assert view.source is source
    assert view.traces[0].events[0] is log.traces[0].events[0]
    assert case_log_digest(log) == before
    assert result.source_digest == before
    assert result.value.selected_event_count == 2
    dropped = filter_case_log(
        log, CaseFilterSpec(mode="events", activities=("A", "B"), empty_cases="drop")
    )
    assert selected(dropped) == ("c0",)


def test_original_and_projected_adjacency_have_distinct_witnesses():
    log = log_for("AXB", "AB", "AXAB")
    common = dict(
        kind="directly_follows", pattern=("A", "B"), project_activities=("A", "B")
    )
    original = filter_case_log(log, CaseFilterSpec(**common))
    projected = filter_case_log(log, CaseFilterSpec(**common, adjacency="projected"))
    assert selected(original) == ("c1", "c2")
    assert selected(projected) == ("c0", "c1", "c2")
    assert projected.value.witnesses[0].positions == (0, 2)
    assert selected_events(projected)[0] == ("c0e0", "c0e1", "c0e2")
    assert projected.computation_id != original.computation_id


@pytest.mark.parametrize(
    "kind,word",
    [
        ("directly_follows", ("A", None, "B")),
        ("prefix", (None, "A", "B")),
        ("suffix", ("A", "B", None)),
    ],
)
def test_projected_unknown_activity_cannot_be_silently_removed(kind, word):
    log = log_for(word)
    result = filter_case_log(
        log,
        CaseFilterSpec(
            kind=kind,
            pattern=("A", "B"),
            project_activities=("A", "B", "C"),
            adjacency="projected",
        ),
    )
    assert selected(result) == ()
    assert result.value.unknown_case_ids == ("c0",)
    assert result.value.witnesses[0].uncertain_event_ids


def test_all_short_traces_against_string_language_oracle():
    # Language membership provides an oracle independent of the path enumerator.
    words = tuple(
        "".join(word) for size in range(5) for word in product("ABX", repeat=size)
    )
    log = log_for(*words)
    original = filter_case_log(
        log, CaseFilterSpec(kind="directly_follows", pattern=("A", "B"))
    )
    projected = filter_case_log(
        log,
        CaseFilterSpec(
            kind="directly_follows",
            pattern=("A", "B"),
            project_activities=("A", "B"),
            adjacency="projected",
        ),
    )
    eventual = filter_case_log(
        log, CaseFilterSpec(kind="eventually_follows", pattern=("A", "B"))
    )
    assert selected(original) == tuple(
        f"c{i}" for i, word in enumerate(words) if "AB" in word
    )
    assert selected(projected) == tuple(
        f"c{i}" for i, word in enumerate(words) if "AB" in word.replace("X", "")
    )
    assert selected(eventual) == tuple(
        f"c{i}"
        for i, word in enumerate(words)
        if "A" in word and "B" in word[word.index("A") + 1 :]
    )


def test_typed_attribute_equality_range_defaults_and_null():
    values = (
        CaseAttribute("value", "int", 1),
        CaseAttribute("value", "boolean", True),
        CaseAttribute("value", "float", 1.0),
        CaseAttribute("value", "string", "1"),
        CaseAttribute("value", "null"),
    )
    log = CaseLog(
        tuple(
            CaseTrace(f"c{i}", (event(f"e{i}", "A", extra=(value,)),))
            for i, value in enumerate(values)
        )
    )
    integer = AttributeCondition(
        "value", values=(CaseAttribute("ignored_key", "int", 1),)
    )
    assert selected(
        filter_case_log(log, CaseFilterSpec(kind="event_attribute", attribute=integer))
    ) == ("c0",)
    numeric = AttributeCondition("value", "numeric_range", minimum=1, maximum=1)
    result = filter_case_log(
        log, CaseFilterSpec(kind="event_attribute", attribute=numeric)
    )
    assert selected(result) == ("c0", "c2")
    assert result.status is ComputeStatus.PARTIAL
    null = AttributeCondition("value", values=(CaseAttribute("value", "null"),))
    assert selected(
        filter_case_log(log, CaseFilterSpec(kind="event_attribute", attribute=null))
    ) == ("c4",)
    global_log = replace(
        log_for("A"),
        globals=(CaseGlobal("event", (CaseAttribute("value", "int", 1),)),),
    )
    assert selected(
        filter_case_log(
            global_log, CaseFilterSpec(kind="event_attribute", attribute=integer)
        )
    ) == ("c0",)
    huge = CaseAttribute("value", "int", 10**400)
    huge_log = CaseLog((CaseTrace("large", (event("huge", "A", extra=(huge,)),)),))
    assert selected(
        filter_case_log(
            huge_log,
            CaseFilterSpec(
                kind="event_attribute",
                attribute=AttributeCondition("value", "numeric_range", minimum=10**399),
            ),
        )
    ) == ("large",)


def test_case_attribute_is_not_an_event_attribute():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (event("e", "A", extra=(CaseAttribute("v", "string", "event"),)),),
                (CaseAttribute("v", "string", "case"),),
            ),
        )
    )
    cond = AttributeCondition("v", values=(CaseAttribute("v", "string", "case"),))
    assert selected(
        filter_case_log(log, CaseFilterSpec(kind="case_attribute", attribute=cond))
    ) == ("c",)
    assert (
        selected(
            filter_case_log(log, CaseFilterSpec(kind="event_attribute", attribute=cond))
        )
        == ()
    )


@pytest.mark.parametrize("positive", [True, False])
def test_unknowns_do_not_become_negative_matches(positive):
    log = log_for((None,), "A", "B")
    result = filter_case_log(log, CaseFilterSpec(activities=("A",), positive=positive))
    assert selected(result) == (("c1",) if positive else ("c2",))
    assert result.value.unknown_case_ids == ("c0",)
    assert result.value.unknown_event_ids == ("c0e0",)
    included = filter_case_log(
        log, CaseFilterSpec(activities=("A",), positive=positive, unknown="include")
    )
    assert "c0" in selected(included)
    strict = filter_case_log(
        log, CaseFilterSpec(activities=("A",), positive=positive, unknown="error")
    )
    assert strict.status is ComputeStatus.INVALID_INPUT
    assert strict.value is None


def test_duplicate_attribute_is_unknown_without_choosing_first():
    duplicate = (CaseAttribute("v", "int", 1), CaseAttribute("v", "int", 2))
    log = CaseLog((CaseTrace("c", (event("e", "A", extra=duplicate),)),))
    result = filter_case_log(
        log,
        CaseFilterSpec(
            kind="event_attribute",
            attribute=AttributeCondition("v", values=(duplicate[0],)),
        ),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert selected(result) == ()


def test_any_all_quantifiers_and_no_vacuous_empty_compliance():
    log = log_for("AB", "AA", "", ("A", None))
    any_result = filter_case_log(log, CaseFilterSpec(activities=("A",)))
    all_result = filter_case_log(
        log, CaseFilterSpec(activities=("A",), quantifier="all")
    )
    assert selected(any_result) == ("c0", "c1", "c3")
    assert selected(all_result) == ("c1",)
    assert all_result.value.unknown_case_ids == ("c3",)


def test_named_classifier_respects_typed_compound_identity():
    log = replace(
        log_for("AB", "BA"), classifiers=(CaseClassifier("act", ("concept:name",)),)
    )
    trace_spec = CaseTraceSpec(classifier="act")
    traces = case_traces(log, trace_spec)
    label = traces.value.traces[0].events[0].activity
    result = filter_case_log(
        log, CaseFilterSpec(kind="start", activities=(label,), trace_spec=trace_spec)
    )
    assert selected(result) == ("c0",)


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        ({"top_k": 1}, ("c0", "c1", "c2", "c3")),
        ({"top_k": 1, "include_ties": False}, ("c0", "c1")),
        ({"top_k": 0}, ()),
        ({"minimum": 0.4}, ("c0", "c1", "c2", "c3")),
        ({"maximum": 0.2}, ("c4",)),
        ({"cumulative_coverage": 0}, ()),
        ({"cumulative_coverage": 0.4}, ("c0", "c1", "c2", "c3")),
        ({"cumulative_coverage": 0.4, "include_ties": False}, ("c0", "c1")),
        ({"cumulative_coverage": 0.9}, ("c0", "c1", "c2", "c3", "c4")),
    ],
)
def test_variant_frequency_fixed_counts_and_tie_policy(kwargs, expected):
    result = filter_case_log(
        log_for("A", "A", "B", "B", "C"),
        CaseFilterSpec(kind="variant_frequency", **kwargs),
    )
    assert selected(result) == expected


def test_unknown_variant_cannot_silently_change_rank_denominator():
    log = log_for("A", "B", (None,))
    result = filter_case_log(log, CaseFilterSpec(kind="variant_frequency", top_k=1))
    assert selected(result) == ()
    assert result.value.unknown_case_ids == ("c0", "c1", "c2")


def test_attribute_frequency_counts_cases_or_events_explicitly():
    value = CaseAttribute("v", "string", "yes")
    other = CaseAttribute("v", "string", "no")
    log = CaseLog(
        (
            CaseTrace(
                "many", tuple(event(f"a{i}", "A", extra=(value,)) for i in range(3))
            ),
            CaseTrace("one", (event("b", "B", extra=(other,)),)),
        )
    )
    condition = AttributeCondition("v", values=(value,))
    cases = filter_case_log(
        log,
        CaseFilterSpec(kind="attribute_frequency", attribute=condition, minimum=0.6),
    )
    events = filter_case_log(
        log,
        CaseFilterSpec(
            kind="attribute_frequency",
            attribute=condition,
            minimum=0.6,
            frequency_unit="events",
        ),
    )
    assert selected(cases) == ()
    assert selected(events) == ("many",)


def test_attribute_frequency_unknown_denominator_reports_partial():
    condition = AttributeCondition("v", values=(CaseAttribute("v", "int", 1),))
    log = CaseLog(
        (
            CaseTrace(
                "known", (event("yes", "A", extra=(CaseAttribute("v", "int", 1),)),)
            ),
            CaseTrace("unknown", (event("missing", "A"),)),
        )
    )
    result = filter_case_log(
        log,
        CaseFilterSpec(kind="attribute_frequency", attribute=condition, minimum=0.75),
    )
    assert selected(result) == ()
    assert result.value.unknown_case_ids == ("known", "unknown")


@pytest.mark.parametrize(
    "time_mode,expected",
    [
        ("contained", ("within",)),
        ("intersects", ("within", "cross", "touch")),
        ("start", ("within", "touch")),
        ("end", ("within",)),
    ],
)
def test_time_window_observed_span_and_closed_boundaries(time_mode, expected):
    log = CaseLog(
        tuple(
            CaseTrace(
                case_id,
                (event(case_id + "a", "A", start), event(case_id + "b", "B", end)),
            )
            for case_id, start, end in (
                ("within", 2, 8),
                ("cross", 0, 15),
                ("touch", 10, 12),
                ("outside", 20, 30),
            )
        )
    )
    result = filter_case_log(
        log,
        CaseFilterSpec(
            kind="time",
            time_start=BASE + timedelta(minutes=2),
            time_end=BASE + timedelta(minutes=10),
            time_mode=time_mode,
        ),
    )
    assert selected(result) == expected


def test_duration_is_observed_span_and_event_slice_is_separate():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("late", "A", 10),
                    event("early", "B", 0),
                    event("middle", "C", 5),
                ),
            ),
        )
    )
    duration = filter_case_log(
        log, CaseFilterSpec(kind="duration", minimum=600, maximum=600)
    )
    assert selected(duration) == ("c",)
    sliced = filter_case_log(
        log,
        CaseFilterSpec(
            kind="time", mode="events", time_start=BASE + timedelta(minutes=5)
        ),
    )
    assert selected_events(sliced) == (("late", "middle"),)
    assert selected_events(filter_case_log(log, CaseFilterSpec(kind="length"))) == (
        ("late", "early", "middle"),
    )


def test_path_durations_are_occurrence_specific_and_reversed_is_unknown():
    log = CaseLog(
        (
            CaseTrace(
                "good",
                (
                    event("a1", "A", 0),
                    event("b1", "B", 3),
                    event("a2", "A", 10),
                    event("b2", "B", 11),
                ),
            ),
            CaseTrace("bad", (event("bada", "A", 10), event("badb", "B", 0))),
        )
    )
    any_result = filter_case_log(
        log, CaseFilterSpec(kind="path_duration", pattern=("A", "B"), minimum=120)
    )
    all_result = filter_case_log(
        log,
        CaseFilterSpec(
            kind="path_duration", pattern=("A", "B"), minimum=120, quantifier="all"
        ),
    )
    assert selected(any_result) == ("good",)
    assert selected(all_result) == ()
    assert any_result.value.unknown_case_ids == ("bad",)
    assert tuple(w.value for w in any_result.value.witnesses) == (180.0, 60.0, None)


def test_all_path_durations_unresolved_activity_can_hide_a_violating_path():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("a", "A", 0),
                    event("b", "B", 1),
                    event("unknown", None, 2),
                    event("last", "B", 100),
                ),
            ),
        )
    )
    result = filter_case_log(
        log,
        CaseFilterSpec(
            kind="path_duration", pattern=("A", "B"), maximum=120, quantifier="all"
        ),
    )
    assert selected(result) == ()
    assert result.value.unknown_case_ids == ("c",)


def test_dst_fold_uses_elapsed_instants_for_range_duration_and_equality():
    class FoldZone(tzinfo):
        def utcoffset(self, dt):
            return timedelta(hours=0 if dt.fold else 1)

        def dst(self, dt):
            return timedelta(0)

    zone = FoldZone()
    first = datetime(2026, 10, 25, 1, 45, tzinfo=zone, fold=0)
    last = datetime(2026, 10, 25, 1, 15, tzinfo=zone, fold=1)
    same_wall_other_instant = datetime(2026, 10, 25, 1, 45, tzinfo=zone, fold=1)
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event(
                        "a",
                        "A",
                        extra=(CaseAttribute("time:timestamp", "date", first),),
                    ),
                    event(
                        "b", "B", extra=(CaseAttribute("time:timestamp", "date", last),)
                    ),
                ),
            ),
        )
    )
    duration = filter_case_log(
        log, CaseFilterSpec(kind="duration", minimum=1800, maximum=1800)
    )
    assert selected(duration) == ("c",)
    bounded = filter_case_log(
        log, CaseFilterSpec(kind="time", time_start=first, time_end=last)
    )
    assert selected(bounded) == ("c",)
    equality = filter_case_log(
        log,
        CaseFilterSpec(
            kind="event_attribute",
            attribute=AttributeCondition(
                "time:timestamp",
                values=(CaseAttribute("t", "date", same_wall_other_instant),),
            ),
        ),
    )
    assert selected(equality) == ()


def test_missing_and_naive_time_are_not_zero_durations():
    log = CaseLog(
        (
            CaseTrace("missing", (event("m", "A"),)),
            CaseTrace(
                "naive",
                (
                    event(
                        "n",
                        "A",
                        extra=(
                            CaseAttribute(
                                "time:timestamp", "date", datetime(2026, 1, 1)
                            ),
                        ),
                    ),
                ),
            ),
        )
    )
    result = filter_case_log(
        log, CaseFilterSpec(kind="duration", maximum=0, positive=False)
    )
    assert selected(result) == ()
    assert result.value.unknown_case_ids == ("missing", "naive")


def test_utc_overflow_and_invalid_classifier_are_explicit():
    extreme = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=1)))
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event(
                        "a",
                        "A",
                        extra=(CaseAttribute("time:timestamp", "date", extreme),),
                    ),
                ),
            ),
        )
    )
    duration = filter_case_log(log, CaseFilterSpec(kind="duration", minimum=0))
    assert duration.status is ComputeStatus.PARTIAL
    assert selected(duration) == ()
    with pytest.raises(ValueError, match="UTC"):
        CaseFilterSpec(kind="time", time_start=extreme)
    with pytest.raises(ValueError, match="UTC"):
        AttributeCondition("t", values=(CaseAttribute("t", "date", extreme),))
    classifier = CaseTraceSpec(classifier="does-not-exist")
    invalid = filter_case_log(
        CaseLog(), CaseFilterSpec(activities=("A",), trace_spec=classifier)
    )
    assert invalid.status is ComputeStatus.INVALID_INPUT
    invalid_slice = slice_cases(
        CaseLog(), CaseSliceSpec(kind="prefix", end_activity="A", trace_spec=classifier)
    )
    assert invalid_slice.status is ComputeStatus.INVALID_INPUT


def test_default_filter_is_an_explicit_empty_activity_selection():
    assert selected(filter_case_log(log_for("A"), CaseFilterSpec())) == ()


def test_four_eyes_sets_and_missing_resource_are_explicit():
    log = CaseLog(
        tuple(
            CaseTrace(
                name,
                tuple(
                    event(f"{name}{i}", activity, resource=resource)
                    for i, (activity, resource) in enumerate(pairs)
                ),
            )
            for name, pairs in (
                ("different", (("A", "r1"), ("B", "r2"))),
                ("shared", (("A", "r1"), ("B", "r1"), ("B", "r2"))),
                ("missing", (("A", "r1"), ("B", None))),
                ("absent", (("A", "r1"),)),
            )
        )
    )
    disjoint = filter_case_log(
        log, CaseFilterSpec(kind="four_eyes", pattern=("A", "B"))
    )
    exists = filter_case_log(
        log,
        CaseFilterSpec(
            kind="four_eyes", pattern=("A", "B"), resource_policy="exists_difference"
        ),
    )
    assert selected(disjoint) == ("different",)
    assert selected(exists) == ("different", "shared")
    assert disjoint.value.unknown_case_ids == ("missing",)
    distinct = filter_case_log(
        log, CaseFilterSpec(kind="different_resources", activities=("B",))
    )
    assert selected(distinct) == ("shared",)


@pytest.mark.parametrize(
    "spec,positions",
    [
        (CaseSliceSpec(kind="prefix", end_activity="B"), ((0, 1, 2),)),
        (
            CaseSliceSpec(
                kind="prefix", end_activity="B", occurrence="last", include_end=False
            ),
            ((0, 1, 2, 3, 4),),
        ),
        (
            CaseSliceSpec(kind="suffix", start_activity="A", occurrence="last"),
            ((3, 4, 5),),
        ),
        (
            CaseSliceSpec(
                kind="suffix",
                start_activity="A",
                occurrence="first",
                include_start=False,
            ),
            ((1, 2, 3, 4, 5),),
        ),
        (
            CaseSliceSpec(
                kind="between", start_activity="A", end_activity="B", occurrence="all"
            ),
            ((0, 1, 2), (3, 4, 5)),
        ),
        (
            CaseSliceSpec(
                kind="between",
                start_activity="A",
                end_activity="B",
                include_start=False,
                include_end=False,
            ),
            ((1,),),
        ),
        (CaseSliceSpec(kind="split", start_activity="A"), ((0, 1, 2), (3, 4, 5))),
        (
            CaseSliceSpec(kind="consecutive_activity"),
            ((0,), (1,), (2,), (3,), (4,), (5,)),
        ),
    ],
)
def test_slicing_expected_positions_and_source_lineage(spec, positions):
    log = log_for("AXBAYB")
    result = slice_cases(log, spec)
    assert tuple(entry.source_positions for entry in result.value.entries) == positions
    view = materialize_case_selection(log, result)
    assert (
        len({event.id for trace in view.traces for event in trace.events})
        == result.value.selected_event_count
    )
    assert tuple(
        tuple(event.activity for event in trace.events) for trace in view.traces
    ) == tuple(
        tuple(log.traces[0].events[i].activity for i in section)
        for section in positions
    )
    assert result.computation_id == slice_cases(log, spec).computation_id


def test_overlapping_segments_have_distinct_output_ids():
    log = log_for("AAB")
    result = slice_cases(
        log,
        CaseSliceSpec(
            kind="between", start_activity="A", end_activity="B", occurrence="all"
        ),
    )
    assert selected_events(result) == (("c0e0", "c0e1", "c0e2"), ("c0e1", "c0e2"))
    view = materialize_case_selection(log, result)
    assert len({event.id for trace in view.traces for event in trace.events}) == 5
    assert result.value.selected_source_case_count == 1


def test_consecutive_and_timestamp_groups_retain_all_facts():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("a", "A", 0),
                    event("b", "A", 0),
                    event("c", "B", 0),
                    event("d", "A", 1),
                ),
            ),
        )
    )
    consecutive = slice_cases(log, CaseSliceSpec(kind="consecutive_activity"))
    timestamps = slice_cases(log, CaseSliceSpec(kind="timestamp_groups"))
    assert selected_events(consecutive) == (("a", "b"), ("c",), ("d",))
    assert selected_events(timestamps) == (("a", "b", "c"), ("d",))


def test_empty_slices_and_unknown_boundaries():
    log = log_for("A", "", (None,))
    spec = CaseSliceSpec(
        kind="prefix", end_activity="A", include_end=False, empty_cases="preserve"
    )
    result = slice_cases(log, spec)
    assert selected_events(result) == ((), ())
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.unknown_case_ids == ("c2",)
    strict = slice_cases(log, replace(spec, unknown="error"))
    assert strict.status is ComputeStatus.INVALID_INPUT


def test_immutable_results_identity_and_source_validation():
    log = log_for("AB")
    spec = CaseFilterSpec(kind="length", minimum=1)
    result = filter_case_log(log, spec)
    assert result == filter_case_log(log, spec)
    assert (
        result.computation_id
        != filter_case_log(log, replace(spec, minimum=2)).computation_id
    )
    with pytest.raises(FrozenInstanceError):
        result.value.selected_event_count = 1
    with pytest.raises(FrozenInstanceError):
        spec.minimum = 2
    with pytest.raises(ValueError, match="digest"):
        materialize_case_selection(log_for("AC"), result)
    malformed_entry = replace(result.value.entries[0], source_positions=(1, 0))
    malformed_result = replace(
        result, value=replace(result.value, entries=(malformed_entry,))
    )
    with pytest.raises(ValueError, match="order"):
        materialize_case_selection(log, malformed_result)


def test_policy_inconsistent_but_position_valid_selection_is_rejected():
    log = log_for("AB")
    result = filter_case_log(log, CaseFilterSpec(activities=("A",), mode="events"))
    entry = replace(
        result.value.entries[0],
        event_ids=("c0e1",),
        output_event_ids=("c0e1",),
        source_positions=(1,),
    )
    forged = replace(result, value=replace(result.value, entries=(entry,)))
    with pytest.raises(ValueError, match="policy"):
        materialize_case_selection(log, forged)


def test_seeded_case_sampling_size_reproducibility_and_source_order():
    log = log_for("A", "B", "C", "D", "")
    spec = CaseSampleSpec(count=2, seed=0)
    result = sample_cases(log, spec)
    assert selected(result) == ("c3", "c4")
    assert result == sample_cases(log, spec)
    assert (
        result.computation_id != sample_cases(log, replace(spec, seed=1)).computation_id
    )
    assert tuple(
        trace.id for trace in materialize_case_selection(log, result).traces
    ) == ("c3", "c4")
    eligible = sample_cases(log, CaseSampleSpec(count=4, empty_cases="drop"))
    assert selected(eligible) == ("c0", "c1", "c2", "c3")
    invalid = sample_cases(log, CaseSampleSpec(count=5, empty_cases="drop"))
    assert invalid.status is ComputeStatus.INVALID_INPUT
    assert invalid.value is None


def test_event_sampling_global_population_and_empty_case_policy():
    log = log_for("ABC", "DE", "")
    spec = CaseSampleSpec(count=2, unit="events", seed=0)
    result = sample_cases(log, spec)
    assert selected_events(result) == ((), ("c1e0", "c1e1"), ())
    compact = sample_cases(log, replace(spec, empty_cases="drop"))
    assert selected_events(compact) == (("c1e0", "c1e1"),)
    assert result.value.selected_event_count == 2
    assert (
        materialize_case_selection(log, compact).traces[0].events
        == log.traces[1].events
    )
    zero = sample_cases(log, CaseSampleSpec(count=0, unit="events", empty_cases="drop"))
    assert selected_events(zero) == ()
    assert (
        sample_cases(log, replace(spec, count=6)).status is ComputeStatus.INVALID_INPUT
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"count": -1},
        {"count": True},
        {"count": 0, "seed": True},
        {"count": 1, "unit": "eventually"},
    ],
)
def test_sampling_invalid_contract(kwargs):
    with pytest.raises((TypeError, ValueError)):
        CaseSampleSpec(**kwargs)


def test_unsupported_frequency_options_are_rejected():
    condition = AttributeCondition("v", values=(CaseAttribute("v", "int", 1),))
    with pytest.raises(ValueError, match="top_k"):
        CaseFilterSpec(kind="attribute_frequency", attribute=condition, top_k=0)
    with pytest.raises(ValueError, match="cumulative_coverage"):
        CaseFilterSpec(
            kind="attribute_frequency", attribute=condition, cumulative_coverage=0
        )


@pytest.mark.parametrize(
    "attribute",
    [
        CaseAttribute("v", "string", "2026-09-15T00:00:00Z"),
        CaseAttribute("v", "id", "123"),
        CaseAttribute("v", "date", BASE),
        CaseAttribute("v", "int", 1),
        CaseAttribute("v", "float", 1.0),
        CaseAttribute("v", "boolean", True),
        CaseAttribute("v", "null"),
    ],
)
def test_typed_comparison_values_roundtrip_without_date_string_guessing(attribute):
    log = CaseLog((CaseTrace("c", (event("e", "A", extra=(attribute,)),)),))
    result = filter_case_log(
        log,
        CaseFilterSpec(
            kind="event_attribute",
            attribute=AttributeCondition("v", values=(attribute,)),
        ),
    )
    restored = result_from_json(result_json_bytes(result))
    assert restored == result
    scalar = restored.spec.attribute.values[0]
    assert scalar.type == attribute.type
    assert type(scalar.value) is type(attribute.value)
    assert (
        materialize_case_selection(log, restored).traces[0].events[0]
        is log.traces[0].events[0]
    )


@pytest.mark.parametrize(
    "spec",
    [
        CaseFilterSpec(kind="length", minimum=0, maximum=2),
        CaseFilterSpec(
            kind="variant_frequency", minimum=0, maximum=1, cumulative_coverage=1
        ),
        CaseFilterSpec(
            kind="event_attribute",
            attribute=AttributeCondition("n", "numeric_range", minimum=1, maximum=2),
        ),
    ],
)
def test_integer_bounds_keep_types_and_request_identity_through_persistence(spec):
    log = CaseLog(
        (CaseTrace("c", (event("e", "A", extra=(CaseAttribute("n", "int", 1),)),)),)
    )
    result = filter_case_log(log, spec)
    assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": "unknown"},
        {"mode": "bad"},
        {"kind": "length", "mode": "events"},
        {"kind": "event_attribute"},
        {"kind": "four_eyes", "pattern": ("A",)},
        {"activities": ("A",), "minimum": 3, "maximum": 2},
        {"activities": ("A",), "minimum": float("nan")},
        {"activities": ("A",), "top_k": True},
        {"activities": ("A",), "cumulative_coverage": 1.1},
        {"activities": ("A",), "time_start": datetime(2026, 1, 1)},
        {"activities": ("A",), "positive": 1},
        {"activities": ["A"]},
        {"activities": ("A",), "adjacency": "implicit"},
    ],
)
def test_invalid_specs_fail_before_calculation(kwargs):
    with pytest.raises((TypeError, ValueError)):
        CaseFilterSpec(**kwargs)
