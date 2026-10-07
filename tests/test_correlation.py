"""Mathematical oracles for native correlation matrices and transportation."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from itertools import permutations, product

import pytest

from pix.case_centric.correlation import (
    CorrelationEvent,
    CorrelationSpec,
    _transport,
    _Work,
    discover_correlation,
)
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log import CaseAttribute, CaseEvent, CaseLog, CaseTrace, case_traces

TIME = datetime(2026, 1, 1, tzinfo=timezone.utc)


def event(identifier, activity, complete, start=None, case=None):
    return CorrelationEvent(
        identifier,
        activity,
        TIME + timedelta(seconds=complete) if complete is not None else None,
        TIME + timedelta(seconds=start) if start is not None else None,
        case,
    )


def cell(model, source, target):
    return next(
        c
        for c in model.cells
        if (c.source_activity, c.target_activity) == (source, target)
    )


def test_case_free_input_has_no_fabricated_cases_and_reports_required_reverse_edge():
    observations = (event("a", "A", 0), event("b", "B", 1))
    result = discover_correlation(observations)
    assert result.status is ComputeStatus.COMPUTED
    model = result.value
    assert model.activities == (("A", 1), ("B", 1))
    assert {
        (e.source_activity, e.target_activity): e.estimated_frequency
        for e in model.edges
    } == {("A", "B"): 1, ("B", "A"): 1}
    assert model.objective == (100_000_000_001, 1)
    assert model.penalty_flow == 1
    assert cell(model, "A", "B").duration_seconds == (1, 1)
    assert cell(model, "B", "A").duration_seconds is None
    assert result.parent_computation_ids == ()
    assert observations[0].case_id is observations[1].case_id is None
    assert "estimated_penalty_edges" in {i.code for i in result.issues}


def test_greedy_duration_selects_reverse_lifo_and_keeps_matching_identity():
    value = discover_correlation(
        (event("a0", "A", 0), event("a9", "A", 9), event("b", "B", 10))
    ).value
    ab = cell(value, "A", "B")
    assert (ab.precedence, ab.duration_seconds, ab.matching_method) == (
        (1, 1),
        (1, 1),
        "reverse_lifo",
    )
    assert [(w.source_event_id, w.target_event_id) for w in ab.duration_witnesses] == [
        ("a9", "b")
    ]
    assert value.transported_occurrences == 3
    for activity, count in value.activities:
        assert (
            sum(
                e.estimated_frequency
                for e in value.edges
                if e.source_activity == activity
            )
            == count
        )
        assert (
            sum(
                e.estimated_frequency
                for e in value.edges
                if e.target_activity == activity
            )
            == count
        )


def test_precedence_counts_all_pairs_even_nested_intervals():
    observations = (
        event("outer", "A", 10, 0),
        event("inner", "A", 2, 1),
        event("b3", "B", 3),
        event("b11", "B", 11),
    )
    ab = cell(discover_correlation(observations).value, "A", "B")
    assert (ab.preceding_pair_count, ab.compared_pair_count, ab.precedence) == (
        3,
        4,
        (3, 4),
    )
    assert ab.duration_seconds == (1, 1)
    assert ab.cost == (2, 3)


def test_classic_and_supplied_trace_populations_are_different():
    observations = (
        event("a0", "A", 0, case="c0"),
        event("b1", "B", 1, case="c0"),
        event("a100", "A", 100, case="c1"),
        event("b101", "B", 101, case="c1"),
    )
    classic = discover_correlation(observations).value
    trace = discover_correlation(
        observations, CorrelationSpec(variant="trace_based")
    ).value
    assert cell(classic, "A", "B").precedence == (3, 4)
    assert cell(trace, "A", "B").precedence == (1, 1)
    assert trace.groups == (("a0", "b1"), ("a100", "b101"))
    assert cell(trace, "A", "B").duration_seconds == (1, 1)


def test_trace_based_duration_pools_matches_before_choosing_direction():
    observations = (
        event("a0", "A", 0, case="c0"),
        event("a9", "A", 9, case="c0"),
        event("b10", "B", 10, case="c0"),
        event("a20", "A", 20, case="c1"),
        event("b21", "B", 21, case="c1"),
        event("b30", "B", 30, case="c1"),
    )
    ab = cell(
        discover_correlation(
            observations, CorrelationSpec(variant="trace_based")
        ).value,
        "A",
        "B",
    )
    # FIFO gaps10,1 and reverse gaps1,10 both mean5.5. Picking per-case minima
    # then averaging would incorrectly return1.
    assert ab.duration_seconds == (11, 2)
    assert ab.matching_method == "fifo"
    assert ab.precedence == (1, 1)


def test_split_uses_unweighted_group_probability_and_maximum_duration():
    observations = (
        event("a0", "A", 0),
        event("b1", "B", 1),
        event("a10", "A", 10),
        event("b15", "B", 15),
        event("x", "X", 20),
    )
    result = discover_correlation(
        observations, CorrelationSpec(variant="classic_split", split_size=2)
    )
    ab = cell(result.value, "A", "B")
    assert ab.precedence == (2, 3)
    assert (ab.preceding_pair_count, ab.compared_pair_count) == (2, 2)
    assert ab.duration_seconds == (5, 1)
    assert ab.duration_witnesses[0].source_event_id == "a10"


def test_split_source_and_completion_order_are_explicit_distinct_requests():
    observations = (
        event("a", "A", 0),
        event("b", "B", 10),
        event("c", "C", 1),
        event("d", "D", 11),
    )
    spec = CorrelationSpec(variant="classic_split", split_size=2)
    original = discover_correlation(observations, spec)
    ordered = discover_correlation(
        observations, replace(spec, split_order="completion_start")
    )
    assert original.value.groups == (("a", "b"), ("c", "d"))
    assert ordered.value.groups == (("a", "c"), ("b", "d"))
    assert cell(original.value, "A", "B").precedence == (1, 2)
    assert cell(ordered.value, "A", "B").precedence == (0, 1)
    assert original.source_digest == ordered.source_digest
    assert original.computation_id != ordered.computation_id


def test_exact_matching_preserves_max_cardinality_not_minimum_average_subset():
    observations = (
        event("a0", "A", 0),
        event("a9", "A", 9),
        event("b10", "B", 10),
        event("b20", "B", 20),
    )
    ab = cell(
        discover_correlation(
            observations, CorrelationSpec(duration_matching="exact_max_cardinality")
        ).value,
        "A",
        "B",
    )
    assert len(ab.duration_witnesses) == 2
    assert ab.duration_seconds == (21, 2)
    assert sum(Fraction(*w.seconds) for w in ab.duration_witnesses) == 21


def test_matching_boundary_and_strict_precedence_do_not_get_conflated():
    observations = (event("a", "A", 1), event("b", "B", 1))
    strict = cell(discover_correlation(observations).value, "A", "B")
    inclusive = cell(
        discover_correlation(
            observations,
            CorrelationSpec(
                duration_matching="exact_max_cardinality", matching_boundary="inclusive"
            ),
        ).value,
        "A",
        "B",
    )
    assert strict.precedence == inclusive.precedence == (0, 1)
    assert strict.duration_seconds is None
    assert inclusive.duration_seconds == (0, 1)
    assert inclusive.penalty_applied


def test_transport_residual_reverse_edges_repair_greedy_assignment():
    costs = ((Fraction(1), Fraction(2)), (Fraction(2), Fraction(100)))
    sent, objective, flows = _transport((1, 1), (1, 1), costs, _Work(CorrelationSpec()))
    assert sent == 2
    assert objective == 4
    assert flows == ((0, 1, 1), (1, 0, 1))


def test_incomplete_transport_maximizes_cardinality_before_minimizing_cost():
    costs = (
        (Fraction(0), None, Fraction(2)),
        (None, None, None),
        (Fraction(1), None, None),
    )
    sent, objective, flows = _transport(
        (1, 1, 1), (1, 1, 1), costs, _Work(CorrelationSpec())
    )
    assert (sent, objective) == (2, Fraction(3))
    assert flows == ((0, 2, 1), (2, 0, 1))


@pytest.mark.parametrize("size", [1, 2, 3])
def test_exact_transport_objective_against_exhaustive_assignment_oracle(size):
    # Independent brute-force permutation oracle, with fractional costs/ties.
    for offset in range(6):
        costs = tuple(
            tuple(
                Fraction((i * 7 + j * 11 + offset * i * j) % 13, (i + j) % 3 + 1)
                for j in range(size)
            )
            for i in range(size)
        )
        expected = min(
            sum((costs[i][p[i]] for i in range(size)), Fraction())
            for p in permutations(range(size))
        )
        sent, objective, _ = _transport(
            (1,) * size, (1,) * size, costs, _Work(CorrelationSpec())
        )
        assert sent == size
        assert objective == expected


def test_transport_integer_capacities_against_exhaustive_matrix_oracle():
    supply, demand = (2, 1), (1, 2)
    costs = ((Fraction(5), Fraction(1)), (Fraction(2), Fraction(7)))
    feasible = []
    for values in product(range(3), repeat=4):
        a, b, c, d = values
        if (a + b, c + d) == supply and (a + c, b + d) == demand:
            feasible.append(
                a * costs[0][0] + b * costs[0][1] + c * costs[1][0] + d * costs[1][1]
            )
    sent, objective, flows = _transport(supply, demand, costs, _Work(CorrelationSpec()))
    assert sent == 3
    assert objective == min(feasible) == 4
    assert all(type(amount) is int for _, _, amount in flows)


@pytest.mark.parametrize("variant", ["classic", "classic_split", "trace_based"])
def test_empty_input_is_computed_without_division_or_fake_events(variant):
    result = discover_correlation((), CorrelationSpec(variant=variant))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.activities == result.value.edges == result.value.cells == ()
    assert result.value.objective == (0, 1)
    assert result.value.transported_occurrences == 0


def test_unavailable_evidence_and_explicit_work_limits():
    observations = (event("a", "A", 0), event("b", "B", 1))
    for source, spec, issue in (
        (
            observations,
            CorrelationSpec(variant="trace_based"),
            "case_membership_required",
        ),
        (
            (event("missing", "A", None),),
            CorrelationSpec(),
            "invalid_correlation_interval",
        ),
        (
            (event("reverse", "A", 1, 2),),
            CorrelationSpec(),
            "invalid_correlation_interval",
        ),
        (observations, CorrelationSpec(max_events=1), "correlation_resource_limit"),
        (
            observations,
            CorrelationSpec(max_pair_evaluations=1),
            "correlation_resource_limit",
        ),
        (
            observations,
            CorrelationSpec(max_augmentations=1),
            "correlation_resource_limit",
        ),
        (
            observations,
            CorrelationSpec(max_relaxations=1),
            "correlation_resource_limit",
        ),
        (
            observations,
            CorrelationSpec(max_group_cells=1),
            "correlation_resource_limit",
        ),
    ):
        result = discover_correlation(source, spec)
        assert result.status is ComputeStatus.UNAVAILABLE
        assert result.value is None
        assert issue in {x.code for x in result.issues}


def test_case_log_custom_classifier_and_times_keep_actual_parent_identity():
    def raw(identifier, activity, time):
        return CaseEvent(
            identifier,
            (
                CaseAttribute("task", "string", activity),
                CaseAttribute("end", "date", TIME + timedelta(seconds=time)),
            ),
        )

    log = CaseLog((CaseTrace("c", (raw("a", "A", 0), raw("b", "B", 1))),))
    trace_spec = CaseTraceSpec(activity_key="task", timestamp_key="end")
    result = discover_correlation(
        log, CorrelationSpec(variant="trace_based", trace_spec=trace_spec)
    )
    assert result.status is ComputeStatus.COMPUTED
    parent = case_traces(log, trace_spec)
    assert result.source_digest == parent.source_digest
    assert result.parent_computation_ids == (parent.computation_id,)
    assert result.value.groups == (("a", "b"),)


def test_explicit_start_attribute_missing_is_not_treated_as_point_event():
    raw = CaseEvent(
        "a",
        (
            CaseAttribute("concept:name", "string", "A"),
            CaseAttribute("time:timestamp", "date", TIME),
        ),
    )
    log = CaseLog((CaseTrace("c", (raw,)),))
    result = discover_correlation(log, CorrelationSpec(start_attribute="start"))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert "missing_correlation_start" in {x.code for x in result.issues}


def test_event_identity_timezone_and_fractional_seconds_are_preserved():
    local = timezone(timedelta(hours=9))
    observations = (
        CorrelationEvent("a", "A", TIME.astimezone(local)),
        CorrelationEvent("b", "B", TIME + timedelta(microseconds=3)),
    )
    result = discover_correlation(observations)
    assert cell(result.value, "A", "B").duration_seconds == (3, 1_000_000)
    assert discover_correlation(observations) == result
    utc_equivalent = (replace(observations[0], completion=TIME), observations[1])
    assert discover_correlation(utc_equivalent).source_digest == result.source_digest
    with pytest.raises(ValueError, match="unique"):
        discover_correlation((observations[0], observations[0]))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CorrelationSpec(variant="unknown"),
        lambda: CorrelationSpec(duration_matching="unknown"),
        lambda: CorrelationSpec(penalty_cost=(1, 0)),
        lambda: CorrelationSpec(max_events=True),
        lambda: CorrelationSpec(split_size=0),
        lambda: CorrelationEvent("a", "A", datetime(2026, 1, 1)),
    ],
)
def test_invalid_contracts_fail_before_computation(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()
