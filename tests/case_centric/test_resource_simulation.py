"""Independent schedule arithmetic, calendar and censored-cohort counterexamples."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.lifecycle import pair_lifecycle_events
from pix.case_centric.resource_simulation import (
    ResourceComparisonSpec,
    ResourceDurationFitSpec,
    ResourcePool,
    ResourceSimulationSpec,
    compare_resource_scenarios,
    fit_resource_durations,
    simulate_resources,
)
from pix.case_centric.simulation import CaseArrival, DurationDistribution, FIFOInput
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace
from pix.results import result_from_json, result_json_bytes


def jobs(*routes, arrivals=None):
    return FIFOInput(
        tuple(
            CaseArrival(f"j{i}", arrivals[i] if arrivals else 0, tuple(route))
            for i, route in enumerate(routes)
        )
    )


def spec(capacity=1, **kwargs):
    return ResourceSimulationSpec(
        (("A", (("R", 1),)),),
        (ResourcePool("R", capacity),),
        (("A", DurationDistribution("fixed", 2)),),
        **kwargs,
    )


def run(data, configuration):
    return simulate_resources(data, configuration).value.repetitions[0]


def test_fifo_hand_oracle_two_jobs_completion_two_four_and_waiting_zero_two():
    result = simulate_resources(jobs("A", "A"), spec())
    assert result.status is ComputeStatus.COMPUTED
    output = result.value.repetitions[0]
    assert [event.completion_seconds for event in output.events] == [2, 4]
    assert [event.waiting_seconds for event in output.events] == [0, 2]
    assert [case.completion_seconds for case in output.cases] == [2, 4]
    assert output.mean_completed_flow_seconds == 3
    assert output.throughput_per_second == 0.5
    assert output.complete


def test_capacity_two_and_atomic_multi_resource_acquisition():
    assert [e.completion_seconds for e in run(jobs("A", "A"), spec(2)).events] == [2, 2]
    config = ResourceSimulationSpec(
        (("A", (("R", 1), ("S", 1))), ("B", (("S", 1), ("R", 1)))),
        (ResourcePool("R", 1), ResourcePool("S", 1)),
        (
            ("A", DurationDistribution("fixed", 2)),
            ("B", DurationDistribution("fixed", 3)),
        ),
    )
    output = run(jobs("AB", "BA"), config)
    assert output.complete
    assert [
        (e.case_id, e.activity, e.start_seconds, e.completion_seconds)
        for e in output.events
    ] == [
        ("j0", "A", 0, 2),
        ("j1", "B", 2, 5),
        ("j0", "B", 5, 8),
        ("j1", "A", 8, 10),
    ]


def test_infeasible_older_request_does_not_hold_or_reserve_one_of_two_pools():
    config = ResourceSimulationSpec(
        (("A", (("R", 1), ("S", 1))), ("B", (("R", 1),))),
        (ResourcePool("R", 1), ResourcePool("S", 1, ((5, 10),))),
        (
            ("A", DurationDistribution("fixed", 2)),
            ("B", DurationDistribution("fixed", 2)),
        ),
    )
    output = run(jobs("A", "B"), config)
    assert [(e.activity, e.start_seconds) for e in output.events] == [
        ("B", 0),
        ("A", 5),
    ]


def test_no_future_reservation_reordering_when_a_ready_job_waits_for_shift():
    config = replace(spec(), resource_pools=(ResourcePool("R", 1, ((5, 20),)),))
    output = run(jobs("A", "A", arrivals=(0, 1)), config)
    assert [(e.case_id, e.start_seconds) for e in output.events] == [
        ("j0", 5),
        ("j1", 7),
    ]


def test_calendar_cross_boundary_delays_whole_operation_without_preemption():
    config = replace(spec(), resource_pools=(ResourcePool("R", 1, ((0, 1), (3, 7))),))
    output = run(jobs("A", "A"), config)
    assert [e.start_seconds for e in output.events] == [3, 5]
    assert [e.completion_seconds for e in output.events] == [5, 7]
    assert ResourcePool("R", 1, ((2, 3), (0, 2))).availability_windows == ((0.0, 3.0),)


def test_calendar_intersection_requires_both_resources_for_entire_operation():
    config = ResourceSimulationSpec(
        (("A", (("R", 1), ("S", 1))),),
        (
            ResourcePool("R", 1, ((0, 3), (5, 10))),
            ResourcePool("S", 1, ((2, 6), (7, 12))),
        ),
        (("A", DurationDistribution("fixed", 2)),),
    )
    assert run(jobs("A"), config).events[0].start_seconds == 7


@pytest.mark.parametrize(
    "windows,expected",
    [((), "no_common_calendar_window"), (((0, 1),), "no_common_calendar_window")],
)
def test_exhausted_calendar_retains_deadlocked_case(windows, expected):
    result = simulate_resources(
        jobs("A"), replace(spec(), resource_pools=(ResourcePool("R", 1, windows),))
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.repetitions[0].cases[0].reason == expected
    assert result.value.repetitions[0].cases[0].completion_seconds is None
    assert result.value.repetitions[0].events == ()


def test_demand_above_capacity_is_explicit_infeasibility_not_partial_acquisition():
    config = replace(spec(), activity_requirements=(("A", (("R", 2),)),))
    output = run(jobs("A"), config)
    assert output.cases[0].reason == "demand_exceeds_capacity"
    assert output.events == ()


def test_horizon_keeps_running_waiting_future_and_empty_cases():
    data = jobs("A", "A", "A", "", arrivals=(0, 0, 10, 0))
    output = run(data, spec(horizon_seconds=1))
    assert len(output.cases) == 4
    assert [row.status for row in output.cases] == ["horizon_limit"] * 3 + ["completed"]
    assert output.events[0].planned_completion_seconds == 2
    assert output.events[0].completion_seconds is None
    assert output.observation_end_seconds == 1
    assert output.completed_case_count == 1
    assert output.mean_completed_flow_seconds == 0


def test_completion_at_horizon_included_and_next_operation_remains_censored():
    output = run(jobs("AA"), spec(horizon_seconds=2))
    assert output.events[0].completion_seconds == 2
    assert output.cases[0].completed_operations == 1
    assert output.cases[0].status == "horizon_limit"


def test_limit_does_not_drop_undispatched_jobs_and_no_false_success():
    output = run(jobs("AA", "A"), spec(max_dispatches=1))
    assert len(output.cases) == 2
    assert not output.complete
    assert all(case.status == "dispatch_limit" for case in output.cases)
    assert output.cases[0].completed_operations == 1


def test_zero_duration_calendar_boundary_and_unresourced_operation():
    config = replace(
        spec(),
        activity_durations=(("A", DurationDistribution()),),
        resource_pools=(ResourcePool("R", 1, ((0, 2),)),),
    )
    output = run(jobs("AA", "A", arrivals=(0, 2)), config)
    assert output.cases[0].completion_seconds == 0
    assert output.cases[1].reason == "no_common_calendar_window"
    free = replace(config, activity_requirements=(("A", ()),), resource_pools=())
    assert run(jobs("AA"), free).cases[0].completion_seconds == 0


def test_empty_input_has_no_fabricated_rate_or_mean():
    output = run(FIFOInput(()), spec())
    assert output.complete and output.completed_case_count == 0
    assert output.mean_completed_flow_seconds is None
    assert output.throughput_per_second is None


def test_seeded_durations_are_deterministic_and_identity_covers_seed():
    config = replace(
        spec(),
        repetitions=3,
        seed=123,
        activity_durations=(("A", DurationDistribution("exponential", 2)),),
    )
    data = jobs("AA", "A")
    assert simulate_resources(data, config) == simulate_resources(data, config)
    other = simulate_resources(data, replace(config, seed=124))
    assert other.computation_id != simulate_resources(data, config).computation_id
    assert other.value != simulate_resources(data, config).value


def test_common_random_numbers_remain_matched_across_capacity_and_dispatch_order():
    config = replace(
        spec(), activity_durations=(("A", DurationDistribution("uniform", 1, 3)),)
    )
    comparison = ResourceComparisonSpec(
        (
            ("baseline", config),
            ("extra", replace(config, resource_pools=(ResourcePool("R", 2),))),
        ),
        seed=123,
        repetitions=3,
    )
    result = compare_resource_scenarios(jobs("AA", "AA"), comparison)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.cohort_case_ids == ("j0", "j1")
    assert result.value.common_random_numbers
    for index in range(3):
        left, right = [
            scenario.result.repetitions[index] for scenario in result.value.scenarios
        ]

        def draw(output):
            return {
                (e.case_id, e.event_index): e.sampled_service_seconds
                for e in output.events
            }

        assert draw(left) == draw(right)
        assert right.mean_completed_flow_seconds < left.mean_completed_flow_seconds
    assert all(
        delta.paired_completed_case_ids == ("j0", "j1")
        for delta in result.value.differences
    )


def test_comparison_reports_paired_completed_cohort_and_preserves_censored_cases():
    baseline = spec(horizon_seconds=2)
    comparison = ResourceComparisonSpec(
        (
            ("base", baseline),
            ("more", replace(baseline, resource_pools=(ResourcePool("R", 2),))),
        )
    )
    result = compare_resource_scenarios(jobs("A", "A"), comparison)
    assert result.status is ComputeStatus.PARTIAL
    difference = result.value.differences[0]
    assert difference.completed_count_difference == 1
    assert difference.paired_completed_case_ids == ("j0",)
    assert difference.mean_paired_flow_difference_seconds == 0
    assert len(result.value.scenarios[0].result.repetitions[0].cases) == 2


def test_independent_scenario_streams_explicit_and_different():
    config = replace(
        spec(), activity_durations=(("A", DurationDistribution("uniform", 1, 3)),)
    )
    comparison = ResourceComparisonSpec(
        (("x", config), ("y", config)), common_random_numbers=False
    )
    output = compare_resource_scenarios(jobs("A"), comparison).value
    assert not output.common_random_numbers
    assert output.scenarios[0].effective_seed != output.scenarios[1].effective_seed
    assert output.scenarios[0].result != output.scenarios[1].result


@pytest.mark.parametrize("capacity", [0, -1, True, 1.5])
def test_invalid_capacity_rejected(capacity):
    with pytest.raises(ValueError):
        ResourcePool("R", capacity)


@pytest.mark.parametrize(
    "windows", [((1, 1),), ((2, 1),), ((0, 3), (2, 4)), ((0, float("inf")),)]
)
def test_invalid_calendar_rejected(windows):
    with pytest.raises(ValueError):
        ResourcePool("R", 1, windows)


def test_missing_resource_or_duration_is_not_silently_defaulted():
    with pytest.raises(ValueError, match="unknown"):
        replace(spec(), resource_pools=())
    with pytest.raises(ValueError, match="duration"):
        simulate_resources(jobs("A"), replace(spec(), activity_durations=()))
    with pytest.raises(ValueError, match="resources"):
        simulate_resources(jobs("B"), spec())


def test_specs_validate_horizon_seed_duplicate_and_input_types():
    for changes in (
        {"seed": True},
        {"horizon_seconds": -1},
        {"max_dispatches": 0},
        {"repetitions": 0},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(spec(), **changes)
    with pytest.raises(ValueError, match="duplicate"):
        replace(spec(), resource_pools=(ResourcePool("R", 1), ResourcePool("R", 2)))
    with pytest.raises(ValueError, match="horizon"):
        ResourceComparisonSpec((("x", spec()), ("y", spec(horizon_seconds=1))))
    with pytest.raises(TypeError):
        simulate_resources(None, spec())
    with pytest.raises(FrozenInstanceError):
        spec().seed = 1


def lifecycle_result(seconds, *, missing=False, orphan=False):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = []
    for i, duration in enumerate(seconds):
        for transition, offset in (("start", 0), ("complete", duration)):
            attrs = (
                CaseAttribute("concept:name", "string", "A"),
                CaseAttribute("lifecycle:transition", "string", transition),
            )
            if not missing:
                attrs += (
                    CaseAttribute(
                        "time:timestamp", "date", start + timedelta(seconds=offset)
                    ),
                )
            events.append(CaseEvent(f"{i}-{transition}", attrs))
    if orphan:
        events.append(
            CaseEvent(
                "orphan",
                (
                    CaseAttribute("concept:name", "string", "B"),
                    CaseAttribute("lifecycle:transition", "string", "start"),
                ),
            )
        )
    return pair_lifecycle_events(CaseLog((CaseTrace("c", tuple(events)),)))


def test_fit_uses_observed_service_mean_and_labels_distribution_assumption():
    pairing = lifecycle_result((2, 4))
    result = fit_resource_durations(pairing, ResourceDurationFitSpec("exponential"))
    row = result.value.activities[0]
    assert row.observed_count == 2 and row.observed_mean_seconds == 3
    assert row.assumed_distribution == DurationDistribution("exponential", 3)
    assert "assumed" in result.value.interpretation
    assert result.parent_computation_ids == (pairing.computation_id,)


def test_fit_missing_and_unmatched_lifecycle_are_never_fabricated_zero():
    result = fit_resource_durations(lifecycle_result((2,), missing=True, orphan=True))
    assert result.status is ComputeStatus.PARTIAL
    row = result.value.activities[0]
    assert row.observed_mean_seconds is None and row.assumed_distribution is None
    assert row.unknown_duration_count == 1
    assert result.value.unmatched_source_event_count == 1


def test_zero_mean_exponential_unfittable_but_fixed_zero_is_explicit():
    pairing = lifecycle_result((0,))
    result = fit_resource_durations(pairing, ResourceDurationFitSpec("exponential"))
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.activities[0].assumed_distribution is None
    assert (
        fit_resource_durations(pairing).value.activities[0].assumed_distribution
        == DurationDistribution()
    )


def test_suspend_resume_elapsed_span_is_not_silently_fitted_as_service_time():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = tuple(
        CaseEvent(
            str(index),
            (
                CaseAttribute("concept:name", "string", "A"),
                CaseAttribute("lifecycle:transition", "string", transition),
                CaseAttribute(
                    "time:timestamp", "date", base + timedelta(seconds=second)
                ),
            ),
        )
        for index, (transition, second) in enumerate(
            (
                ("start", 0),
                ("suspend", 10),
                ("resume", 90),
                ("complete", 100),
                ("start", 110),
                ("complete", 112),
            )
        )
    )
    pairing = pair_lifecycle_events(CaseLog((CaseTrace("case", events),)))
    result = fit_resource_durations(pairing)
    row = result.value.activities[0]
    assert result.status is ComputeStatus.PARTIAL
    assert row.observed_count == 1
    assert row.unknown_duration_count == 1
    assert row.observed_mean_seconds == 2
    assert row.assumed_distribution == DurationDistribution("fixed", 2)
    assert result.value.unmatched_source_event_count == 2
    assert "interrupted_service_interval" in {issue.code for issue in result.issues}


def test_multiple_units_are_not_collapsed_to_one_resource_token():
    configuration = replace(spec(3), activity_requirements=(("A", (("R", 2),)),))
    output = run(jobs("A", "A"), configuration)
    assert [event.completion_seconds for event in output.events] == [2, 4]
    assert all(event.requirements == (("R", 2),) for event in output.events)


@pytest.mark.parametrize("operator", ["simulation", "comparison", "fit"])
def test_registered_result_roundtrip_preserves_nested_cases_and_assumptions(operator):
    if operator == "simulation":
        result = simulate_resources(jobs("AA", "A"), spec(horizon_seconds=1))
    elif operator == "comparison":
        result = compare_resource_scenarios(
            jobs("A", "A"),
            ResourceComparisonSpec(
                (("base", spec()), ("more", spec(2))), common_random_numbers=False
            ),
        )
    else:
        result = fit_resource_durations(
            lifecycle_result((2, 4)), ResourceDurationFitSpec("exponential")
        )
    assert result_from_json(result_json_bytes(result)) == result
