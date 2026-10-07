"""Hand-counted Heuristics Miner examples, including interval counterexamples."""

from datetime import datetime, timedelta, timezone

import pytest

from pix.case_centric.heuristics import HeuristicsSpec, discover_heuristics
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.result import ComputeStatus
from pix.event_log.adapters import case_traces
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def _log(*sequences):
    return CaseLog(
        tuple(
            CaseTrace(
                str(index),
                tuple(
                    CaseEvent(
                        f"{index}:{position}",
                        (CaseAttribute("concept:name", "string", activity),),
                    )
                    for position, activity in enumerate(sequence)
                ),
            )
            for index, sequence in enumerate(sequences)
        )
    )


def _interval_log(*sequences, start_key="start_timestamp"):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CaseLog(
        tuple(
            CaseTrace(
                str(index),
                tuple(
                    CaseEvent(
                        f"{index}:{position}",
                        (
                            CaseAttribute("concept:name", "string", activity),
                            CaseAttribute(
                                start_key, "date", origin + timedelta(seconds=start)
                            ),
                            CaseAttribute(
                                "time:timestamp",
                                "date",
                                origin + timedelta(seconds=end),
                            ),
                        ),
                    )
                    for position, (activity, start, end) in enumerate(sequence)
                ),
            )
            for index, sequence in enumerate(sequences)
        )
    )


def _dependency(net, source, target):
    return next(
        row for row in net.dependencies if (row.source, row.target) == (source, target)
    )


def _binding(net, activity, direction):
    return next(
        row.alternatives
        for row in net.bindings
        if (row.activity, row.direction) == (activity, direction)
    )


def test_direct_counts_and_dependency_use_frequencies_not_distinct_traces():
    result = discover_heuristics(_log("AB", "AB", "AB", "BA"))
    assert result.status == ComputeStatus.COMPUTED
    net = result.value
    assert [
        (row.activity, row.count, row.start_count, row.end_count)
        for row in net.activities
    ] == [("A", 4, 3, 1), ("B", 4, 1, 3)]
    assert _dependency(net, "A", "B").measure == pytest.approx(2 / 5)
    assert _dependency(net, "B", "A").measure == pytest.approx(-2 / 5)
    assert net.edges == ()


def test_classic_dependency_threshold_is_inclusive():
    net = discover_heuristics(
        _log("AB"), HeuristicsSpec(dependency_threshold=0.5)
    ).value
    assert net.edges == (("A", "B"),)
    assert _binding(net, "A", "output") == (("B",),)
    assert (
        discover_heuristics(
            _log("AB"), HeuristicsSpec(dependency_threshold=0.50001)
        ).value.edges
        == ()
    )


def test_self_loop_and_length_two_loop_have_explicit_evidence():
    net = discover_heuristics(
        _log("AAAA", "BABAB"), HeuristicsSpec(dependency_threshold=0.9)
    ).value
    loops = {row.activities: row for row in net.short_loops}
    assert loops[("A",)].occurrences == 3
    assert loops[("A",)].measure == 0.75
    assert not loops[("A",)].selected
    assert loops[("A", "B")].occurrences == 3
    assert loops[("A", "B")].measure == 0.75
    assert loops[("A", "B")].selected
    assert net.edges == (("A", "B"), ("B", "A"))


def test_minimum_count_prevents_loop_edges_from_bypassing_filter():
    net = discover_heuristics(_log("ABA"), HeuristicsSpec(min_edge_count=2)).value
    assert not net.edges
    assert net.short_loops[0].measure == 0.5
    assert not net.short_loops[0].selected


def test_classic_parallel_branch_and_join_hand_counts():
    # Four observations of each branch ordering. A->B and A->C each occur 4
    # times; B->C and C->B each occur 4 times. AND at A and D is 8 / 9.
    net = discover_heuristics(_log(*(["ABCD", "ACBD"] * 4))).value
    rows = {(row.activity, row.direction): row for row in net.and_pairs}
    assert rows["A", "output"].numerator == 8
    assert rows["A", "output"].denominator == 9
    assert rows["A", "output"].measure == pytest.approx(8 / 9)
    assert rows["D", "input"].measure == pytest.approx(8 / 9)
    assert _binding(net, "A", "output") == (("B", "C"),)
    assert _binding(net, "D", "input") == (("B", "C"),)


def test_exclusive_choice_is_two_singleton_alternatives():
    net = discover_heuristics(_log("ABD", "ACD", "ABD", "ACD")).value
    assert _binding(net, "A", "output") == (("B",), ("C",))
    assert _binding(net, "D", "input") == (("B",), ("C",))
    assert all(row.measure == 0 and not row.selected for row in net.and_pairs)


def test_and_bindings_use_maximal_cliques_not_transitive_connected_groups():
    # At A, B AND C and C AND D hold, but B AND D does not. A connected-
    # component shortcut would incorrectly invent the three-way binding BCD.
    sequences = ["AB", "AC", "AD", "BC", "CB", "CD", "DC"] * 3
    net = discover_heuristics(_log(*sequences)).value
    assert _binding(net, "A", "output") == (("B", "C"), ("C", "D"))


def test_activity_filter_retains_exclusion_evidence_and_singletons():
    net = discover_heuristics(
        _log("A", "A", "B"), HeuristicsSpec(min_activity_count=2)
    ).value
    assert [row.activity for row in net.activities] == ["A"]
    assert [(row.activity, row.count) for row in net.excluded_activities] == [("B", 1)]
    assert net.edges == ()


def test_relative_noise_cleaning_uses_both_endpoints_incident_maximum():
    net = discover_heuristics(
        _log(*(["AC"] * 10 + ["DB"] * 10 + ["AB"])),
        HeuristicsSpec(dfg_noise_threshold=0.2),
    ).value
    assert [(r.source, r.target, r.count) for r in net.precleaned_edges] == [
        ("A", "B", 1)
    ]
    assert ("A", "B") not in net.edges
    assert ("A", "C") in net.edges and ("D", "B") in net.edges


def test_empty_traces_and_empty_log_are_distinct_observed_facts():
    net = discover_heuristics(_log("", "A", "")).value
    assert net.trace_count == 3 and net.empty_trace_count == 2
    empty = discover_heuristics(_log()).value
    assert empty.trace_count == empty.empty_trace_count == 0
    assert empty.activities == empty.edges == empty.bindings == ()


def test_missing_timestamp_is_allowed_for_classic():
    result = discover_heuristics(_log("AB"))
    assert result.status == ComputeStatus.COMPUTED
    assert any(row.code == "unknown_timestamp" for row in result.issues)


def test_interval_overlap_changes_dependency_and_and_measure():
    log = _interval_log(
        [("A", 0, 1), ("B", 2, 5), ("C", 3, 6), ("D", 7, 8)],
        [("A", 0, 1), ("C", 2, 5), ("B", 3, 6), ("D", 7, 8)],
    )
    net = discover_heuristics(log, HeuristicsSpec(profile="plusplus")).value
    assert net.profile == "pix.heuristics.interval.v1"
    assert [(r.source, r.target, r.count) for r in net.overlaps] == [("B", "C", 2)]
    assert net.edges == (("A", "B"), ("A", "C"), ("B", "D"), ("C", "D"))
    assert _dependency(net, "A", "B").measure == 1
    assert _binding(net, "A", "output") == (("B", "C"),)
    split = next(row for row in net.and_pairs if row.activity == "A")
    assert (split.numerator, split.denominator, split.measure) == (2, 2, 1.0)
    # Join has four incoming follows observations but only two overlaps.
    join = next(row for row in net.and_pairs if row.activity == "D")
    assert join.measure == 0.5 and not join.selected


def test_interval_first_following_is_not_every_later_event():
    net = discover_heuristics(
        _interval_log([("A", 0, 1), ("B", 2, 3), ("C", 4, 5)]),
        HeuristicsSpec(profile="plusplus"),
    ).value
    assert [(r.source, r.target, r.count) for r in net.follows] == [
        ("A", "B", 1),
        ("B", "C", 1),
    ]


def test_interval_concurrency_is_pairwise_not_transitive():
    net = discover_heuristics(
        _interval_log([("A", 0, 10), ("B", 1, 2), ("C", 3, 4)]),
        HeuristicsSpec(profile="plusplus"),
    ).value
    assert [(r.source, r.target, r.count) for r in net.overlaps] == [
        ("A", "B", 1),
        ("A", "C", 1),
    ]
    assert [(r.source, r.target, r.count) for r in net.follows] == [("B", "C", 1)]


def test_result_is_deterministic_without_collapsing_duplicate_cases():
    log = _log("ACD", "ABD", "ACD")
    first = discover_heuristics(log)
    assert first == discover_heuristics(log)
    reverse_order = CaseLog(tuple(reversed(log.traces)))
    assert discover_heuristics(reverse_order).value == first.value
    assert next(row.count for row in first.value.activities if row.activity == "C") == 2


def test_strict_and_closed_overlap_have_different_touching_boundary():
    log = _interval_log([("A", 0, 1), ("B", 1, 2)])
    strict = discover_heuristics(log, HeuristicsSpec(profile="plusplus")).value
    closed = discover_heuristics(
        log, HeuristicsSpec(profile="plusplus", overlap_policy="closed")
    ).value
    assert strict.overlaps == ()
    assert _dependency(strict, "A", "B").measure == 1.0
    assert _dependency(closed, "A", "B").measure == 0.5
    assert strict.edges == (("A", "B"),) and closed.edges == ()


def test_plus_threshold_is_strict_and_no_classic_selfloop_fallback():
    log = _interval_log([("A", 0, 1), ("A", 2, 3)])
    net = discover_heuristics(
        log, HeuristicsSpec(profile="plusplus", dependency_threshold=0)
    ).value
    assert _dependency(net, "A", "A").measure == 0
    assert net.edges == net.short_loops == ()


def test_plus_missing_starts_unavailable_and_never_imputed():
    result = discover_heuristics(_log("AB"), HeuristicsSpec(profile="plusplus"))
    assert result.status == ComputeStatus.UNAVAILABLE and result.value is None
    assert any(issue.code == "interval_input_unavailable" for issue in result.issues)


def test_plus_trace_projection_lacks_start_evidence():
    traces = case_traces(_interval_log([("A", 0, 1), ("B", 2, 3)]))
    result = discover_heuristics(traces, HeuristicsSpec(profile="plusplus"))
    assert result.status == ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "interval_source_required"


def test_reversed_interval_is_unavailable():
    result = discover_heuristics(
        _interval_log([("A", 2, 1)]), HeuristicsSpec(profile="plusplus")
    )
    assert result.status == ComputeStatus.UNAVAILABLE
    assert "starts after" in result.issues[-1].message


def test_custom_observed_start_attribute_and_source_boundary_semantics():
    # The interval relation is A->B, while source boundaries deliberately stay
    # B then A. The net exposes both facts instead of silently sorting CaseLog.
    log = _interval_log([("B", 3, 4), ("A", 0, 1)], start_key="observed:start")
    net = discover_heuristics(
        log, HeuristicsSpec(profile="plusplus", start_timestamp_key="observed:start")
    ).value
    assert net.edges == (("A", "B"),)
    assert [(r.activity, r.start_count, r.end_count) for r in net.activities] == [
        ("A", 0, 1),
        ("B", 1, 0),
    ]


def test_prepared_trace_parent_and_identity_are_preserved():
    log = _log("AB")
    prepared = case_traces(log)
    direct = discover_heuristics(log)
    derived = discover_heuristics(prepared)
    assert direct == derived
    assert direct.source_digest == prepared.source_digest
    assert direct.parent_computation_ids == (prepared.computation_id,)
    changed = discover_heuristics(prepared, HeuristicsSpec(dependency_threshold=0.7))
    assert changed.computation_id != direct.computation_id
    with pytest.raises(ValueError, match="trace_spec"):
        discover_heuristics(prepared, trace_spec=CaseTraceSpec())


def test_failed_projection_is_not_reported_as_empty_success():
    log = CaseLog((CaseTrace("1", (CaseEvent("e"),)),))
    result = discover_heuristics(log)
    assert result.status == ComputeStatus.UNAVAILABLE and result.value is None


def test_explicit_binding_search_limit_prevents_partial_success():
    result = discover_heuristics(
        _log("ABCD"), HeuristicsSpec(max_binding_search_states=1)
    )
    assert result.status == ComputeStatus.UNAVAILABLE and result.value is None
    assert result.issues[-1].code == "binding_search_limit"


@pytest.mark.parametrize(
    "field",
    [
        "dependency_threshold",
        "and_threshold",
        "loop_two_threshold",
        "dfg_noise_threshold",
    ],
)
@pytest.mark.parametrize("value", [0, 1])
def test_integer_thresholds_normalize_before_identity_and_codec(
    field, value, monkeypatch
):
    from pix import results
    from pix.case_centric.heuristics import RESULT_SCHEMAS

    # This checks the module's registered contract independently of when the
    # application-wide schema integration lands; it does not claim integration.
    registered = {**results._schemas(), **RESULT_SCHEMAS}
    monkeypatch.setattr(results, "_schemas", lambda: registered)
    integer_spec = HeuristicsSpec(**{field: value})
    float_spec = HeuristicsSpec(**{field: float(value)})
    assert type(getattr(integer_spec, field)) is float
    log = _log("AB", "AB", "ACB")
    integer_result = discover_heuristics(log, integer_spec)
    float_result = discover_heuristics(log, float_spec)
    assert integer_result.computation_id == float_result.computation_id
    assert (
        results.result_from_json(results.result_json_bytes(integer_result))
        == integer_result
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dependency_threshold": float("nan")},
        {"dependency_threshold": True},
        {"dependency_threshold": 10**400},
        {"and_threshold": -0.01},
        {"loop_two_threshold": 1.1},
        {"min_activity_count": 0},
        {"min_edge_count": False},
        {"max_binding_search_states": 0},
        {"profile": "fake"},
        {"start_timestamp_key": " "},
        {"overlap_policy": "point"},
        {"profile": "plusplus", "dfg_noise_threshold": 0.1},
    ],
)
def test_invalid_parameters_fail_at_request_boundary(kwargs):
    with pytest.raises(ValueError):
        HeuristicsSpec(**kwargs)
