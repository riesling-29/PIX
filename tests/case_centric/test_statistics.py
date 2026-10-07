"""Independent small-input oracles for native case statistics profiles."""

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from itertools import combinations, product

import pytest

from pix.case_centric.statistics import (
    AttributeStatisticsSpec,
    CasePerformanceSpec,
    ChaoticActivitySpec,
    EventDistributionSpec,
    FrequentSequenceSpec,
    IntervalRelationSpec,
    NumericAttributeSpec,
    PerformanceSpectrumSpec,
    ProcessCubeSpec,
    StatisticsSpec,
    build_process_cube,
    discover_chaotic_activities,
    discover_frequent_sequences,
    discover_interval_eventually_follows,
    discover_performance_spectrum,
    measure_attributes,
    measure_case_performance,
    measure_event_distribution,
    measure_numeric_attribute,
    measure_statistics,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import (
    CaseAttribute,
    CaseClassifier,
    CaseEvent,
    CaseGlobal,
    CaseLog,
    CaseTrace,
    case_log_digest,
    case_traces,
)

BASE = datetime(2025, 1, 1, tzinfo=timezone.utc)


def event(identifier, activity, complete=None, start=None, extra=()):
    return CaseEvent(
        identifier,
        (
            CaseAttribute("concept:name", "string", activity),
            *(
                (
                    CaseAttribute(
                        "time:timestamp", "date", BASE + timedelta(seconds=complete)
                    ),
                )
                if complete is not None
                else ()
            ),
            *(
                (CaseAttribute("start", "date", BASE + timedelta(seconds=start)),)
                if start is not None
                else ()
            ),
            *extra,
        ),
    )


def simple_log(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                str(i), tuple(event(f"{i}:{j}", a, j) for j, a in enumerate(sequence))
            )
            for i, sequence in enumerate(sequences)
        )
    )


def test_frequencies_boundaries_variants_empty_cases_and_rework_are_distinct():
    result = measure_statistics(simple_log("ABA", "ABA", "B", ""))
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    assert (value.case_count, value.event_count, value.empty_case_ids) == (4, 7, ("3",))
    a, b = value.activities
    assert (a.activity, a.event_count, a.case_ids) == ("A", 4, ("0", "1"))
    assert a.start_case_ids == a.end_case_ids == a.rework_case_ids == ("0", "1")
    assert a.repeated_event_count == 2
    assert a.positions == ((0, 2), (2, 2))
    assert b.rework_case_ids == ()
    assert b.positions == ((0, 1), (1, 2))
    assert [
        (v.activities, v.count, v.probability, v.cumulative_coverage)
        for v in value.variants
    ] == [(("A", "B", "A"), 2, 0.5, 0.5), ((), 1, 0.25, 0.75), (("B",), 1, 0.25, 1.0)]


def test_sequence_relations_do_not_sort_reversed_or_tied_timestamps():
    log = CaseLog(
        (CaseTrace("c", (event("z", "B", 20), event("a", "A", 0), event("b", "A", 0))),)
    )
    value = measure_statistics(log).value
    assert {
        (r.source, r.target): r.occurrence_count for r in value.directly_follows
    } == {("B", "A"): 1, ("A", "A"): 1}
    assert {
        (r.source, r.target): r.occurrence_count for r in value.eventually_follows
    } == {("B", "A"): 2, ("A", "A"): 1}
    first = measure_statistics(
        log, StatisticsSpec(eventually_mode="first_per_source_activity")
    ).value
    assert (
        next(r for r in first.eventually_follows if r.source == "B").occurrence_count
        == 1
    )


def test_pair_counts_have_event_and_case_witnesses():
    value = measure_statistics(simple_log("AAA", "AA")).value
    relation = value.eventually_follows[0]
    assert (relation.occurrence_count, relation.case_count) == (4, 2)
    assert [(w.source_event_id, w.target_event_id) for w in relation.witnesses] == [
        ("0:0", "0:1"),
        ("0:0", "0:2"),
        ("0:1", "0:2"),
        ("1:0", "1:1"),
    ]


def test_interval_eventual_relation_orders_start_time_explicitly_and_counts_admissible_pairs():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("b", "B", 30, 20),
                    event("a", "A", 10, 0),
                    event("c", "C", 20, 10),
                ),
            ),
        )
    )
    spec = IntervalRelationSpec(start_attribute="start")
    value = discover_interval_eventually_follows(log, spec).value
    assert value.ordered_event_ids == (("c", ("a", "c", "b")),)
    assert {(r.source, r.target): r.occurrence_count for r in value.relations} == {
        ("A", "B"): 1,
        ("A", "C"): 1,
        ("C", "B"): 1,
    }
    first = discover_interval_eventually_follows(
        log, replace(spec, keep_first_following=True)
    ).value
    assert {(r.source, r.target) for r in first.relations} == {("A", "C"), ("C", "B")}
    assert measure_statistics(log).value.variants[0].activities == ("B", "A", "C")


def test_interval_eventual_relation_excludes_overlap_and_reports_missing():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("a", "A", 10, 0),
                    event("b", "B", 15, 5),
                    event("c", "C", 20, 10),
                    event("d", "D", 30),
                ),
            ),
        )
    )
    result = discover_interval_eventually_follows(
        log, IntervalRelationSpec(start_attribute="start")
    )
    assert result.status is ComputeStatus.PARTIAL
    assert (
        result.value.event_population,
        result.value.selected_event_count,
        result.value.candidate_pairs,
    ) == (4, 3, 3)
    assert result.value.excluded_event_ids == ("d",)
    assert {(r.source, r.target) for r in result.value.relations} == {("A", "C")}


def test_interval_eventual_relation_ties_point_events_and_budget():
    log = CaseLog((CaseTrace("c", (event("b", "B", 5), event("a", "A", 5))),))
    result = discover_interval_eventually_follows(log)
    assert result.status is ComputeStatus.COMPUTED
    assert {(r.source, r.target) for r in result.value.relations} == {("B", "A")}
    rejected = discover_interval_eventually_follows(
        log, IntervalRelationSpec(tie_policy="reject")
    )
    assert rejected.status is ComputeStatus.PARTIAL
    assert rejected.value.selected_event_count == 0
    assert rejected.value.excluded_event_ids == ("b", "a")
    limited = discover_interval_eventually_follows(
        simple_log("ABC"), IntervalRelationSpec(max_relation_pairs=1)
    )
    assert limited.status is ComputeStatus.UNAVAILABLE


def test_minimum_self_distance_zero_absence_and_all_minimum_witnesses():
    value = measure_statistics(simple_log("ABACA", "ADA", "EE", "Z")).value
    distances = {d.activity: d for d in value.minimum_self_distances}
    assert distances["A"].distance == 1
    assert distances["A"].intervening_activities == ("B", "C", "D")
    assert len(distances["A"].witnesses) == 3
    assert distances["E"].distance == 0
    assert distances["E"].intervening_activities == ()
    assert distances["Z"].distance is None
    assert distances["Z"].witnesses == ()


def test_statistics_provenance_and_replay_determinism():
    log = simple_log("BA", "AB")
    result = measure_statistics(log)
    assert result == measure_statistics(log)
    assert result.source_digest == case_log_digest(log)
    assert result.parent_computation_ids == (case_traces(log).computation_id,)
    assert (
        result.computation_id
        != measure_statistics(
            log, StatisticsSpec(eventually_mode="first_per_source_activity")
        ).computation_id
    )
    reordered = replace(log, traces=tuple(reversed(log.traces)))
    assert result.source_digest != measure_statistics(reordered).source_digest


def test_classifiers_and_global_activity_defaults():
    log = CaseLog(
        (CaseTrace("c", (CaseEvent("e", ()),)),),
        globals=(CaseGlobal("event", (CaseAttribute("concept:name", "string", "A"),)),),
    )
    assert measure_statistics(log).value.activities[0].activity == "A"
    log = replace(log, classifiers=(CaseClassifier("labels", ("concept:name",)),))
    result = measure_statistics(
        log, StatisticsSpec(trace_spec=CaseTraceSpec(classifier="labels"))
    )
    assert result.value.activities[0].activity == '[["string","A"]]'


def test_ambiguous_activity_does_not_produce_partial_counts():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event(
                        "e", "A", extra=(CaseAttribute("concept:name", "string", "B"),)
                    ),
                ),
            ),
        )
    )
    result = measure_statistics(log)
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_duplicate_event_identity_is_rejected_by_caselog():
    e = event("same", "A")
    with pytest.raises(ValueError, match="identities"):
        CaseLog((CaseTrace("c", (e, e)),))


def test_relation_limit_refuses_incomplete_exact_counts():
    result = measure_statistics(
        simple_log("ABCD"), StatisticsSpec(max_relation_pairs=2)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert "relation_limit" in {i.code for i in result.issues}


def test_empty_log_has_no_fabricated_variants_or_denominator():
    stats = measure_statistics(CaseLog()).value
    assert stats.case_count == stats.event_count == 0
    assert stats.variants == stats.minimum_self_distances == ()
    temporal = measure_case_performance(CaseLog()).value
    assert temporal.cycle_seconds is temporal.duration_summary.mean is None
    assert temporal.cycle_denominator == 0


def test_complete_busy_union_includes_last_interval_and_explicit_denominator():
    log = CaseLog(
        (
            CaseTrace("c1", (event("a", "A", 10, 0), event("b", "B", 20, 5))),
            CaseTrace("c2", (event("c", "A", 30, 20),)),
        )
    )
    result = measure_case_performance(log, CasePerformanceSpec(start_attribute="start"))
    value = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert (value.busy_union_seconds, value.cycle_denominator, value.cycle_seconds) == (
        30.0,
        2,
        15.0,
    )
    assert [x.duration_seconds for x in value.cases] == [10.0, 0.0]
    assert value.arrival_gaps == (("c1", "c2", 20.0),)
    assert value.completion_gaps == (("c1", "c2", 10.0),)
    assert [
        (p.source_event_id, p.target_event_id, p.overlap_seconds)
        for p in value.concurrent_intervals
    ] == [("a", "b", 5.0)]
    assert dict(value.service_summaries)["A"].mean == 10.0
    assert dict(value.service_summaries)["B"].mean == 15.0


def test_busy_union_single_interval_and_disjoint_last_interval_regression():
    for log, expected in [
        (CaseLog((CaseTrace("c", (event("e", "A", 10, 0),)),)), 10.0),
        (
            CaseLog(
                (CaseTrace("c", (event("e1", "A", 10, 0), event("e2", "B", 30, 20))),)
            ),
            20.0,
        ),
    ]:
        value = measure_case_performance(
            log, CasePerformanceSpec(start_attribute="start")
        ).value
        assert value.busy_union_seconds == expected
        assert value.cycle_seconds == expected


def test_interval_endpoint_policy_and_point_intervals():
    log = CaseLog(
        (
            CaseTrace("c1", (event("a", "A", 0), event("b", "B", 10))),
            CaseTrace("c2", (event("c", "C", 10), event("d", "D", 20))),
            CaseTrace("point", (event("p", "P", 10),)),
        )
    )
    strict = measure_case_performance(log).value
    inclusive = measure_case_performance(
        log, CasePerformanceSpec(overlap_boundary="inclusive")
    ).value
    assert all(c.overlapping_case_ids == () for c in strict.cases)
    assert inclusive.cases[0].overlapping_case_ids == ("c2", "point")
    assert inclusive.cases[2].overlapping_case_ids == ("c1", "c2")
    assert strict.cycle_seconds is strict.busy_union_seconds is None


def test_duration_missing_nonmonotonic_and_empty_coverage():
    log = CaseLog(
        (
            CaseTrace("missing", (event("m1", "A", 0), event("m2", "B"))),
            CaseTrace("reverse", (event("r1", "A", 20), event("r2", "B", 10))),
            CaseTrace("equal", (event("t1", "A", 5), event("t2", "B", 5))),
            CaseTrace("empty"),
        )
    )
    result = measure_case_performance(log)
    assert result.status is ComputeStatus.PARTIAL
    assert [c.status for c in result.value.cases] == [
        "missing_timestamp",
        "nonmonotonic_timestamps",
        "observed",
        "empty_case",
    ]
    assert [c.duration_seconds for c in result.value.cases] == [None, None, 0.0, None]
    assert result.value.eligible_case_count == 1
    assert result.value.duration_summary.count == 1
    assert result.value.arrival_summary.mean is None
    assert result.value.variant_paths[0].unknown_count == 2
    assert result.value.variant_paths[0].summary.mean == 0.0


def test_service_missing_reversed_and_unknown_cycle_population():
    log = CaseLog(
        (
            CaseTrace("bad", (event("a", "A", 5, 10), event("b", "B", 20))),
            CaseTrace("good", (event("c", "A", 10, 0),)),
        )
    )
    result = measure_case_performance(log, CasePerformanceSpec(start_attribute="start"))
    assert result.status is ComputeStatus.PARTIAL
    assert [s.status for s in result.value.services] == [
        "reversed_interval",
        "missing_interval",
        "observed",
    ]
    assert result.value.cycle_denominator == 1
    assert result.value.cycle_seconds == 10.0
    assert dict(result.value.service_summaries)["B"].mean is None


def test_variant_path_positions_preserve_repeated_edges():
    value = measure_case_performance(simple_log("ABAB", "ABAB")).value
    assert [
        (p.source, p.target, p.position, p.summary.count) for p in value.variant_paths
    ] == [("A", "B", 0, 2), ("B", "A", 1, 2), ("A", "B", 2, 2)]


def test_naive_completion_does_not_create_duration():
    raw = CaseEvent(
        "e",
        (
            CaseAttribute("concept:name", "string", "A"),
            CaseAttribute("time:timestamp", "date", datetime(2025, 1, 1)),
        ),
    )
    result = measure_case_performance(CaseLog((CaseTrace("c", (raw,)),)))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.cases[0].duration_seconds is None


def test_dst_fold_uses_absolute_time_without_sorting_trace_events():
    class FoldZone(tzinfo):
        def utcoffset(self, dt):
            return timedelta(hours=-5 if dt.fold else -4)

        def dst(self, dt):
            return timedelta(hours=0 if dt.fold else 1)

    zone = FoldZone()
    first = datetime(2025, 11, 2, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)

    def timed(identifier, label, timestamp, start=None):
        return CaseEvent(
            identifier,
            (
                CaseAttribute("concept:name", "string", label),
                CaseAttribute("time:timestamp", "date", timestamp),
                *((CaseAttribute("start", "date", start),) if start else ()),
            ),
        )

    log = CaseLog(
        (
            CaseTrace(
                "c", (timed("a", "A", first, first), timed("b", "B", second, first))
            ),
        )
    )
    performance = measure_case_performance(
        log, CasePerformanceSpec(start_attribute="start")
    ).value
    assert performance.cases[0].duration_seconds == 3600.0
    assert performance.services[1].seconds == 3600.0
    assert performance.variant_paths[0].summary.mean == 3600.0
    spectrum = discover_performance_spectrum(
        log, PerformanceSpectrumSpec(("A", "B"))
    ).value
    assert (
        spectrum.points[0].times[1] - spectrum.points[0].times[0]
    ).total_seconds() == 3600.0


def test_attribute_types_null_missing_and_lexical_values_are_distinct():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event(
                        "a",
                        "A",
                        extra=(CaseAttribute("value", "int", 1, lexical="01"),),
                    ),
                    event(
                        "b", "B", extra=(CaseAttribute("value", "int", 1, lexical="1"),)
                    ),
                    event("c", "C", extra=(CaseAttribute("value", "string", "1"),)),
                    event("d", "D", extra=(CaseAttribute("value", "null"),)),
                    event("e", "E"),
                ),
            ),
        )
    )
    value = measure_attributes(log, AttributeStatisticsSpec(keys=("value",))).value
    assert value.coverage[0].observed == 4
    assert value.coverage[0].missing == 1
    assert sorted(f.occurrence_count for f in value.frequencies) == [1, 1, 2]
    repeated = next(f for f in value.frequencies if f.occurrence_count == 2)
    assert repeated.case_ids == ("c",)
    assert repeated.entity_ids == ("a", "b")


def test_attribute_missing_requested_key_in_empty_population():
    value = measure_attributes(
        CaseLog(), AttributeStatisticsSpec(keys=("absent",))
    ).value
    assert value.coverage[0].population == value.coverage[0].missing == 0
    assert value.frequencies == ()


def test_attribute_analytics_do_not_require_activity_labels_and_use_source_identity():
    raw = CaseEvent(
        "e", (CaseAttribute("resource", "string", "r"), CaseAttribute("cost", "int", 5))
    )
    log = CaseLog((CaseTrace("c", (raw,)),))
    attribute = measure_attributes(log, AttributeStatisticsSpec(keys=("resource",)))
    numeric = measure_numeric_attribute(log, NumericAttributeSpec("cost"))
    cube = build_process_cube(
        log, ProcessCubeSpec("resource", "cost", scope="event", numeric_key="cost")
    )
    for result in (attribute, numeric, cube):
        assert result.status is ComputeStatus.COMPUTED
        assert result.parent_computation_ids == ()
        assert result.source_digest == case_log_digest(log)
    assert numeric.value.summary.mean == 5.0
    assert cube.value.cells[0].numeric_summary.mean == 5.0


def test_duplicate_case_attributes_are_ambiguous_not_first_value():
    log = CaseLog(
        (
            CaseTrace(
                "c", (), (CaseAttribute("x", "int", 1), CaseAttribute("x", "int", 2))
            ),
        )
    )
    result = measure_attributes(log, AttributeStatisticsSpec(scope="case"))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert "ambiguous_attribute" in {i.code for i in result.issues}


def test_frequent_sequence_support_is_per_case_not_occurrence():
    log = simple_log("AAAB", "ACB", "")
    gap = discover_frequent_sequences(
        log, FrequentSequenceSpec(min_case_support=2)
    ).value
    lookup = {x.activities: x for x in gap.sequences}
    assert lookup[("A", "B")].case_support == 2
    assert lookup[("A", "B")].case_coverage == pytest.approx(2 / 3)
    assert lookup[("A", "B")].first_matches[0].event_ids == ("0:0", "0:3")
    contiguous = discover_frequent_sequences(
        log, FrequentSequenceSpec(min_case_support=2, contiguous=True)
    ).value
    assert ("A", "B") not in {x.activities for x in contiguous.sequences}


@pytest.mark.parametrize("contiguous", [False, True])
def test_frequent_sequence_exactness_against_exhaustive_position_oracle(contiguous):
    sequences = [p for n in range(4) for p in product("AB", repeat=n)]
    log = simple_log(*sequences)
    expected = {}
    for case, sequence in enumerate(sequences):
        seen = set()
        for width in range(1, 4):
            for indices in combinations(range(len(sequence)), width):
                if contiguous and indices != tuple(
                    range(indices[0], indices[0] + width)
                ):
                    continue
                seen.add(tuple(sequence[i] for i in indices))
        for label in seen:
            expected.setdefault(label, set()).add(str(case))
    result = discover_frequent_sequences(
        log, FrequentSequenceSpec(max_length=3, contiguous=contiguous)
    )
    assert result.status is ComputeStatus.COMPUTED
    actual = {
        x.activities: {m.case_id for m in x.first_matches}
        for x in result.value.sequences
    }
    assert actual == expected


def test_frequent_sequence_candidate_limit_and_empty_input():
    result = discover_frequent_sequences(
        simple_log("ABC"), FrequentSequenceSpec(max_candidates=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None
    assert discover_frequent_sequences(CaseLog()).value.sequences == ()


def test_process_cube_counts_missing_cell_and_numeric_population():
    log = CaseLog(
        (
            CaseTrace(
                "c1",
                (),
                (
                    CaseAttribute("x", "string", "west"),
                    CaseAttribute("y", "int", 1),
                    CaseAttribute("n", "int", 10),
                ),
            ),
            CaseTrace(
                "c2",
                (),
                (
                    CaseAttribute("x", "string", "west"),
                    CaseAttribute("y", "int", 1),
                    CaseAttribute("n", "int", 20),
                ),
            ),
            CaseTrace("c3", (), (CaseAttribute("x", "string", "west"),)),
        )
    )
    result = build_process_cube(log, ProcessCubeSpec("x", "y", numeric_key="n"))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.population == 3
    assert sum(len(c.entity_ids) for c in result.value.cells) == 3
    missing, observed = result.value.cells
    assert missing.y_value_json is None
    assert missing.numeric_unknown == 1
    assert missing.numeric_summary.mean is None
    assert observed.case_ids == ("c1", "c2")
    assert observed.numeric_summary.mean == 15.0


def test_numeric_gaussian_kde_matches_closed_form_and_population():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("a", "A", extra=(CaseAttribute("x", "float", 0.0),)),
                    event("b", "B", extra=(CaseAttribute("x", "float", 2.0),)),
                    event("c", "C"),
                ),
            ),
        )
    )
    result = measure_numeric_attribute(
        log, NumericAttributeSpec("x", grid=(0.0, 1.0), bandwidth=1.0)
    )
    value = result.value
    assert result.status is ComputeStatus.PARTIAL
    assert value.population == 3
    assert value.unknown_entity_ids == ("c",)
    assert (
        value.summary.mean
        == value.summary.median
        == value.summary.population_stddev
        == 1.0
    )
    assert value.gaussian_kde[0][1] == pytest.approx(
        (1 + math.exp(-2)) / (2 * math.sqrt(2 * math.pi))
    )
    assert value.gaussian_kde[1][1] == pytest.approx(
        math.exp(-0.5) / math.sqrt(2 * math.pi)
    )


def test_numeric_empty_nonnumeric_nonfinite_and_huge_integer():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("a", "A", extra=(CaseAttribute("x", "float", math.inf),)),
                    event("b", "B", extra=(CaseAttribute("x", "boolean", True),)),
                    event("c", "C", extra=(CaseAttribute("x", "int", 10**1000),)),
                ),
            ),
        )
    )
    result = measure_numeric_attribute(
        log, NumericAttributeSpec("x", grid=(0.0,), bandwidth=1.0)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.summary.count == 0
    assert result.value.summary.mean is None
    assert result.value.gaussian_kde == ((0.0, None),)
    assert result.value.unknown_entity_ids == ("a", "b", "c")


def test_numeric_large_finite_values_do_not_overflow_mean():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                tuple(
                    event(str(i), "A", extra=(CaseAttribute("x", "float", 1e308),))
                    for i in range(2)
                ),
            ),
        )
    )
    value = measure_numeric_attribute(log, NumericAttributeSpec("x")).value
    assert value.summary.mean == 1e308
    assert (
        value.summary.median
        == value.summary.first_quartile
        == value.summary.third_quartile
        == 1e308
    )
    assert value.summary.total is None


@pytest.mark.parametrize(
    "samples, expected_total, expected_mean, expected_median",
    [
        ((1e308, 1e-100, -1e308), 1e-100, 1e-100 / 3, 1e-100),
        ((-1e308, 1e-100, 1e-100, 1e308), 2e-100, 0.5e-100, 1e-100),
        ((1e308, 1e308, -1e308, -1e308), 0.0, 0.0, 0.0),
    ],
)
def test_numeric_cancellation_preserves_small_centers(
    samples, expected_total, expected_mean, expected_median
):
    log = CaseLog(
        (
            CaseTrace(
                "c",
                tuple(
                    event(str(i), "A", extra=(CaseAttribute("x", "float", sample),))
                    for i, sample in enumerate(samples)
                ),
            ),
        )
    )
    summary = measure_numeric_attribute(log, NumericAttributeSpec("x")).value.summary
    assert summary.total == pytest.approx(expected_total, rel=1e-14, abs=0)
    assert summary.mean == pytest.approx(expected_mean, rel=1e-14, abs=0)
    assert summary.median == expected_median


def test_numeric_quartiles_use_explicit_linear_rank_definition():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                tuple(
                    event(
                        str(i), "A", extra=(CaseAttribute("x", "float", float(i * 10)),)
                    )
                    for i in range(4)
                ),
            ),
        )
    )
    summary = measure_numeric_attribute(log, NumericAttributeSpec("x")).value.summary
    assert (summary.first_quartile, summary.median, summary.third_quartile) == (
        7.5,
        15.0,
        22.5,
    )


def test_numeric_density_overflow_and_kernel_work_limit():
    log = CaseLog(
        (CaseTrace("c", (event("e", "A", extra=(CaseAttribute("x", "float", 0.0),)),)),)
    )
    result = measure_numeric_attribute(
        log, NumericAttributeSpec("x", grid=(0.0,), bandwidth=5e-324)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.gaussian_kde == ((0.0, None),)
    limited = measure_numeric_attribute(
        log,
        NumericAttributeSpec(
            "x", grid=(0.0, 1.0), bandwidth=1.0, max_kernel_evaluations=1
        ),
    )
    assert limited.status is ComputeStatus.UNAVAILABLE


def test_kde_scaled_differences_and_log_density_preserve_representable_tails():
    def density(sample, grid, bandwidth):
        log = CaseLog(
            (
                CaseTrace(
                    "c",
                    (event("e", "A", extra=(CaseAttribute("x", "float", sample),)),),
                ),
            )
        )
        return measure_numeric_attribute(
            log, NumericAttributeSpec("x", grid=(grid,), bandwidth=bandwidth)
        ).value.gaussian_kde[0][1]

    assert density(-1e308, 1e308, 1e308) == pytest.approx(
        5.3990966513188e-310, rel=1e-12, abs=0
    )
    assert density(0.0, 0.0, 3e-309) == pytest.approx(1.3298076013381091e308)
    # Individual exp(-800) underflows, but division by a tiny bandwidth does not.
    expected = math.exp(-800 - math.log(1e-308) - 0.5 * math.log(2 * math.pi))
    assert density(0.0, 4e-307, 1e-308) == pytest.approx(expected, rel=1e-12, abs=0)


def test_spectrum_projected_source_and_subsequence_semantics():
    log = simple_log("AXB", "AAB")
    projected = discover_performance_spectrum(
        log, PerformanceSpectrumSpec(("A", "B"))
    ).value
    assert [x.event_ids for x in projected.points] == [("0:0", "0:2"), ("1:1", "1:2")]
    source = discover_performance_spectrum(
        log, PerformanceSpectrumSpec(("A", "B"), match_mode="source_contiguous")
    ).value
    assert [x.event_ids for x in source.points] == [("1:1", "1:2")]
    subseq = discover_performance_spectrum(
        log, PerformanceSpectrumSpec(("A", "B"), match_mode="subsequence")
    ).value
    assert [x.event_ids for x in subseq.points] == [
        ("0:0", "0:2"),
        ("1:0", "1:2"),
        ("1:1", "1:2"),
    ]


def test_spectrum_timestamp_coverage_and_budget():
    log = CaseLog((CaseTrace("c", (event("a", "A", 5), event("b", "B", 0))),))
    result = discover_performance_spectrum(log, PerformanceSpectrumSpec(("A", "B")))
    assert result.status is ComputeStatus.PARTIAL
    assert (
        result.value.matched_occurrences,
        result.value.unknown_occurrences,
        result.value.points,
    ) == (1, 1, ())
    limited = discover_performance_spectrum(
        simple_log("ABAB"), PerformanceSpectrumSpec(("A", "B"), max_matches=1)
    )
    assert limited.status is ComputeStatus.UNAVAILABLE
    assert limited.value is None


def test_chaotic_entropy_hand_oracle_and_neighbor_bridging():
    result = discover_chaotic_activities(
        simple_log("AB", "AC"), ChaoticActivitySpec(alpha=0.0)
    )
    value = result.value
    assert value.raw_total_entropy == 1.0
    metrics = {a.activity: a for a in value.activities}
    assert (
        metrics["A"].raw_entropy,
        metrics["A"].entropy_gain,
        metrics["A"].score,
    ) == (1.0, 1.0, 1.0)
    assert (
        metrics["B"].raw_entropy
        == metrics["B"].entropy_gain
        == metrics["B"].score
        == 0.0
    )
    assert value.activities[0].activity == "A"


def test_chaotic_empty_default_alpha_and_boundary_labels_do_not_collide():
    assert discover_chaotic_activities(CaseLog()).value.activities == ()
    assert discover_chaotic_activities(CaseLog()).value.alpha_used is None
    normal = discover_chaotic_activities(simple_log(("A", "B"), ("A", "C"))).value
    renamed = discover_chaotic_activities(
        simple_log(("START", "END"), ("START", "other"))
    ).value
    assert normal.alpha_used == pytest.approx(1 / 3)
    assert sorted(x.score for x in normal.activities) == pytest.approx(
        sorted(x.score for x in renamed.activities)
    )


def test_chaotic_large_smoothing_is_finite_uniform_limit():
    result = discover_chaotic_activities(
        simple_log("AB"), ChaoticActivitySpec(alpha=1e308)
    )
    assert result.status is ComputeStatus.COMPUTED
    assert all(
        a.smoothed_entropy == pytest.approx(2 * math.log2(3))
        for a in result.value.activities
    )


def test_statistics_public_codec_normalizes_accepted_integer_parameters():
    from pix.results import result_from_json, result_json_bytes

    log = CaseLog(
        (CaseTrace("c", (event("e", "A", extra=(CaseAttribute("x", "int", 1),)),)),)
    )
    spec = NumericAttributeSpec("x", grid=(0, 1), bandwidth=1)
    assert spec.grid == (0.0, 1.0)
    assert all(type(x) is float for x in spec.grid)
    assert type(spec.bandwidth) is float
    for result in (
        measure_numeric_attribute(log, spec),
        discover_chaotic_activities(CaseLog()),
        discover_chaotic_activities(log, ChaoticActivitySpec(alpha=0)),
    ):
        assert result_from_json(result_json_bytes(result)) == result


def test_chaotic_work_guard_precedes_entropy_computation(monkeypatch):
    from pix.case_centric import statistics

    def forbidden(*args):
        raise AssertionError("Preflight should prevent entropy evaluation")

    monkeypatch.setattr(statistics, "_neighborhood_entropies", forbidden)
    result = discover_chaotic_activities(
        simple_log("AB"), ChaoticActivitySpec(max_activity_event_product=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE


def test_event_calendar_bins_offset_unknown_coverage_and_source_order():
    log = CaseLog(
        (
            CaseTrace(
                "c",
                (
                    event("last", "A", 3600),
                    event("first", "B", -3600),
                    event("missing", "C"),
                ),
            ),
        )
    )
    utc = measure_event_distribution(log)
    assert utc.status is ComputeStatus.PARTIAL
    assert [(b.key, b.event_ids) for b in utc.value.bins] == [
        ("2024-12-31", ("first",)),
        ("2025-01-01", ("last",)),
    ]
    assert utc.value.observed_count == 2
    assert utc.value.unknown_event_ids == ("missing",)
    local = measure_event_distribution(
        log, EventDistributionSpec(utc_offset_minutes=540)
    ).value
    assert local.bins[0].event_ids == ("last", "first")
    assert local.bins[0].key == "2025-01-01"
    weekdays = measure_event_distribution(
        log, EventDistributionSpec(granularity="weekday")
    ).value
    assert [b.key for b in weekdays.bins] == ["2", "3"]


@pytest.mark.parametrize(
    "factory",
    [
        lambda: StatisticsSpec(eventually_mode="invalid"),
        lambda: StatisticsSpec(max_relation_pairs=0),
        lambda: CasePerformanceSpec(overlap_boundary="arbitrary"),
        lambda: FrequentSequenceSpec(min_case_support=0),
        lambda: FrequentSequenceSpec(contiguous=1),
        lambda: NumericAttributeSpec("x", grid=(0.0,)),
        lambda: NumericAttributeSpec("x", bandwidth=0.0),
        lambda: NumericAttributeSpec("x", grid=(math.nan,), bandwidth=1.0),
        lambda: PerformanceSpectrumSpec(("A",)),
        lambda: ChaoticActivitySpec(alpha=-1.0),
    ],
)
def test_invalid_specifications_are_rejected(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()
