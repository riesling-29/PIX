"""Observation policies, evidence, contract boundaries, and invalid inputs."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from pix.compute.constraints import evaluate_constraints
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import E2OEvidence, TraceSpec
from pix.contracts.constraint import (
    ConstraintSpec,
    CountRule,
    NotCoexistenceRule,
    PrecedenceRule,
    ResponseRule,
    TimedResponseRule,
)
from pix.contracts.result import ComputeIssue, ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _traces(*words, times=None, tie_policy="reject", qualifiers=None):
    events = tuple(
        Event(
            f"e{case}_{index}",
            label,
            ORIGIN + timedelta(microseconds=index if times is None else times[index]),
        )
        for case, word in enumerate(words)
        for index, label in enumerate(word)
    )
    log = OCEL(
        event_types=tuple(EventType(label) for label in sorted(set("".join(words)))),
        object_types=(ObjectType("case"),),
        events=events,
        objects=tuple(Object(f"o{case}", "case") for case in range(len(words))),
        e2o=tuple(
            E2O(event.id, "o" + event.id[1:].split("_")[0], "flow") for event in events
        ),
    )
    return reconstruct_traces(log, TraceSpec("case", qualifiers, tie_policy))


def _evaluate(word, rule, policy="closed", **kwargs):
    return evaluate_constraints(
        _traces(word, **kwargs), ConstraintSpec((rule,), policy)
    )


def _row(result):
    assert result.value is not None
    return result.value.rules[0].traces[0]


@pytest.mark.parametrize(
    "rule,word,policy,expected",
    [
        (CountRule("r", "A", 1), "", "open", "pending"),
        (CountRule("r", "A", 1), "", "closed", "violated"),
        (CountRule("r", "A", 1), "A", "open", "fulfilled"),
        (CountRule("r", "A", 1, 1), "A", "open", "pending"),
        (CountRule("r", "A", 1, 1), "A", "closed", "fulfilled"),
        (CountRule("r", "A", 0, 1), "AA", "open", "violated"),
        (CountRule("r", "A", 0, 0), "", "open", "pending"),
        (CountRule("r", "A", 0, 0), "", "closed", "fulfilled"),
        (CountRule("r", "A", 0, 0), "A", "open", "violated"),
        (CountRule("r", "A", 0), "", "open", "fulfilled"),
        (ResponseRule("r", "A", "B"), "A", "open", "pending"),
        (ResponseRule("r", "A", "B"), "A", "closed", "violated"),
        (ResponseRule("r", "A", "B"), "AB", "open", "fulfilled"),
        (ResponseRule("r", "A", "B"), "BA", "open", "pending"),
        (PrecedenceRule("r", "A", "B"), "B", "open", "violated"),
        (PrecedenceRule("r", "A", "B"), "BA", "open", "violated"),
        (PrecedenceRule("r", "A", "B"), "AB", "open", "fulfilled"),
        (NotCoexistenceRule("r", "A", "B"), "A", "open", "pending"),
        (NotCoexistenceRule("r", "A", "B"), "A", "closed", "fulfilled"),
        (NotCoexistenceRule("r", "A", "B"), "AB", "open", "violated"),
        (NotCoexistenceRule("r", "A", "A"), "A", "open", "violated"),
        (NotCoexistenceRule("r", "A", "A"), "", "open", "pending"),
    ],
)
def test_explicit_observation_policy(rule, word, policy, expected):
    result = _evaluate(word, rule, policy)
    row = _row(result)
    assert row.status == expected
    assert result.status is (
        ComputeStatus.PARTIAL if expected == "pending" else ComputeStatus.COMPUTED
    )
    assert (
        row.fulfilled_count + row.violated_count + row.pending_count
        == row.activation_count
    )
    assert result.value.observation_policy == policy


@pytest.mark.parametrize("selection", ["any", "first"])
@pytest.mark.parametrize(
    "delay,expected",
    [(9, "violated"), (10, "fulfilled"), (20, "fulfilled"), (21, "violated")],
)
def test_timed_inclusive_microsecond_boundaries(selection, delay, expected):
    result = _evaluate(
        "AB", TimedResponseRule("r", "A", "B", 10, 20, selection), times=(0, delay)
    )
    assert _row(result).status == expected
    if expected == "fulfilled" or selection == "first":
        assert _row(result).witnesses[0].elapsed_microseconds == delay


@pytest.mark.parametrize(
    "selection,expected", [("any", "fulfilled"), ("first", "violated")]
)
@pytest.mark.parametrize("policy", ["open", "closed"])
def test_first_target_is_not_an_existential_target(selection, expected, policy):
    result = _evaluate(
        "ABB",
        TimedResponseRule("r", "A", "B", 10, 20, selection),
        policy,
        times=(0, 5, 10),
    )
    witness = _row(result).witnesses[0]
    assert witness.status == expected
    assert witness.evidence_event_ids == (
        "e0_0",
        "e0_2" if selection == "any" else "e0_1",
    )
    assert witness.elapsed_microseconds == (10 if selection == "any" else 5)


@pytest.mark.parametrize(
    "delay,expected", [(19, "pending"), (20, "pending"), (21, "violated")]
)
@pytest.mark.parametrize("selection", ["any", "first"])
def test_open_deadline_requires_prefix_strictly_past_upper_bound(
    delay, expected, selection
):
    result = _evaluate(
        "AC",
        TimedResponseRule("r", "A", "B", 10, 20, selection),
        "open",
        times=(0, delay),
    )
    assert _row(result).status == expected
    if expected == "violated":
        assert _row(result).witnesses[0].evidence_event_ids == ("e0_0", "e0_1")
        assert (
            _row(result).witnesses[0].reason
            == "observed_prefix_passed_response_deadline"
        )


def test_open_any_target_too_early_remains_pending_until_deadline():
    rule = TimedResponseRule("r", "A", "B", 10, 20, "any")
    assert _row(_evaluate("AB", rule, "open", times=(0, 5))).status == "pending"
    assert _row(_evaluate("ABC", rule, "open", times=(0, 5, 21))).status == "violated"


@pytest.mark.parametrize(
    "rule",
    [
        ResponseRule("r", "A", "A"),
        PrecedenceRule("r", "A", "A"),
        TimedResponseRule("r", "A", "A", 0, 5, "any"),
    ],
)
def test_self_label_requires_a_distinct_event_occurrence(rule):
    result = _evaluate("AA", rule)
    row = _row(result)
    assert (row.fulfilled_count, row.violated_count) == (1, 1)
    fulfilled = next(w for w in row.witnesses if w.status == "fulfilled")
    assert fulfilled.evidence_event_ids == ("e0_0", "e0_1")
    assert fulfilled.activation_event_id == (
        "e0_1" if isinstance(rule, PrecedenceRule) else "e0_0"
    )
    assert _row(_evaluate("A", rule)).violated_count == 1


def test_one_response_may_fulfill_several_activations():
    result = _evaluate("AAB", ResponseRule("r", "A", "B"))
    row = _row(result)
    assert row.fulfilled_count == 2
    assert [w.evidence_event_ids for w in row.witnesses] == [
        ("e0_0", "e0_2"),
        ("e0_1", "e0_2"),
    ]
    assert result.value.rules[0].fulfillment_ratio == (2, 2)


def test_precedence_chooses_latest_prior_witness():
    row = _row(_evaluate("AAB", PrecedenceRule("r", "A", "B")))
    assert row.witnesses[0].evidence_event_ids == ("e0_1", "e0_2")
    assert row.witnesses[0].elapsed_microseconds == 1


@pytest.mark.parametrize(
    "rule",
    [
        ResponseRule("r", "A", "B"),
        PrecedenceRule("r", "A", "B"),
        TimedResponseRule("r", "A", "B", 0, 5, "any"),
    ],
)
@pytest.mark.parametrize("policy", ["open", "closed"])
def test_zero_observed_activations_are_vacuous_not_a_synthetic_ratio(rule, policy):
    result = _evaluate("", rule, policy)
    aggregate = result.value.rules[0]
    assert aggregate.fulfillment_ratio is None
    assert aggregate.activation_count == 0
    assert aggregate.fulfilled_object_count == aggregate.vacuous_object_count == 1
    assert _row(result).status == "fulfilled" and _row(result).vacuous
    assert _row(result).witnesses == ()


def test_empty_selected_population_is_separate_from_one_empty_object():
    rules = (CountRule("exists", "A", 1), ResponseRule("respond", "A", "B"))
    result = evaluate_constraints(_traces(), ConstraintSpec(rules, "closed"))
    assert result.status is ComputeStatus.COMPUTED
    assert any(issue.code == "empty_population" for issue in result.issues)
    for aggregate in result.value.rules:
        assert aggregate.object_count == aggregate.activation_count == 0
        assert aggregate.fulfillment_ratio is None and aggregate.traces == ()
    nonempty = evaluate_constraints(_traces(""), ConstraintSpec(rules, "closed"))
    assert nonempty.value.rules[0].activation_count == 1
    assert nonempty.value.rules[0].violated_count == 1
    assert nonempty.value.rules[1].activation_count == 0


def test_obligation_and_object_populations_are_not_mixed():
    result = evaluate_constraints(
        _traces("AAB", "A", ""), ConstraintSpec((ResponseRule("r", "A", "B"),), "open")
    )
    aggregate = result.value.rules[0]
    assert result.status is ComputeStatus.PARTIAL
    assert (
        aggregate.activation_count,
        aggregate.fulfilled_count,
        aggregate.pending_count,
    ) == (3, 2, 1)
    assert aggregate.fulfillment_ratio == (2, 3)
    assert (
        aggregate.object_count,
        aggregate.fulfilled_object_count,
        aggregate.pending_object_count,
    ) == (3, 2, 1)
    assert aggregate.vacuous_object_count == 1


def test_violated_object_may_still_have_pending_obligations():
    result = _evaluate("ABA", TimedResponseRule("r", "A", "B", 2, 3, "first"), "open")
    row = _row(result)
    assert row.status == "violated"
    assert (row.violated_count, row.pending_count) == (1, 1)
    assert result.status is ComputeStatus.PARTIAL


def test_ordered_equal_timestamps_expose_convention_and_zero_elapsed():
    source = _traces("AB", times=(0, 0), tie_policy="event_id")
    result = evaluate_constraints(
        source,
        ConstraintSpec((TimedResponseRule("r", "A", "B", 0, 0, "any"),), "closed"),
    )
    assert _row(result).fulfilled_count == 1
    assert _row(result).witnesses[0].elapsed_microseconds == 0
    assert any(issue.code == "event_id_order_assumption" for issue in result.issues)
    assert result.parent_computation_ids == (source.computation_id,)
    rejected = _evaluate("AB", ResponseRule("r", "A", "B"), times=(0, 0))
    assert rejected.status is ComputeStatus.UNAVAILABLE
    assert any(issue.code == "ambiguous_event_order" for issue in rejected.issues)


def test_tied_prior_target_does_not_fulfill_later_activation():
    result = _evaluate(
        "BA",
        TimedResponseRule("r", "A", "B", 0, 0, "any"),
        times=(0, 0),
        tie_policy="event_id",
    )
    assert _row(result).violated_count == 1


def test_qualified_trace_selection_and_lineage_are_preserved():
    source = _traces("AB", qualifiers=())
    result = evaluate_constraints(
        source, ConstraintSpec((CountRule("r", "A", 1),), "closed")
    )
    assert _row(result).violated_count == 1
    assert _row(result).witnesses[0].evidence_event_ids == ()
    assert result.source_digest == source.source_digest
    assert result.value.source_trace_computation_id == source.computation_id
    assert result.parent_computation_ids == (source.computation_id,)


@pytest.mark.parametrize(
    "upstream,expected",
    [
        (ComputeStatus.INVALID_INPUT, ComputeStatus.INVALID_INPUT),
        (ComputeStatus.UNAVAILABLE, ComputeStatus.UNAVAILABLE),
        (ComputeStatus.PARTIAL, ComputeStatus.UNAVAILABLE),
    ],
)
def test_incomplete_upstream_preserves_errors_and_rejects_subset(upstream, expected):
    original = _traces("AB")
    issue = ComputeIssue("original_error", "Specific original error", ("object", "o0"))
    source = replace(
        original,
        status=upstream,
        value=original.value if upstream is ComputeStatus.PARTIAL else None,
        issues=(issue,),
    )
    result = evaluate_constraints(
        source, ConstraintSpec((ResponseRule("r", "A", "B"),), "closed")
    )
    assert result.status is expected and result.value is None
    assert issue in result.issues
    assert result.parent_computation_ids == (source.computation_id,)


def test_wrong_function_argument_types_fail_explicitly():
    with pytest.raises(TypeError):
        evaluate_constraints(None, ConstraintSpec((CountRule("r", "A"),), "closed"))
    with pytest.raises(TypeError):
        evaluate_constraints(_traces("A"), None)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda source: replace(source, operator_id="other"),
        lambda source: replace(source, spec=CountRule("x", "A")),
        lambda source: replace(
            source, value=replace(source.value, object_type="wrong")
        ),
        lambda source: replace(
            source, value=replace(source.value, traces=source.value.traces * 2)
        ),
        lambda source: replace(
            source,
            value=replace(
                source.value,
                traces=(replace(source.value.traces[0], object_type="wrong"),),
            ),
        ),
        lambda source: replace(
            source,
            value=replace(
                source.value,
                traces=(
                    replace(
                        source.value.traces[0],
                        events=source.value.traces[0].events[::-1],
                    ),
                ),
            ),
        ),
        lambda source: replace(
            source,
            value=replace(
                source.value,
                traces=(
                    replace(
                        source.value.traces[0], events=source.value.traces[0].events * 2
                    ),
                ),
            ),
        ),
        lambda source: _mutate_first_event(source, activity=""),
        lambda source: _mutate_first_event(source, event_id=""),
        lambda source: _mutate_first_event(source, time=ORIGIN.replace(tzinfo=None)),
        lambda source: _mutate_first_event(
            source, time=ORIGIN.astimezone(timezone(timedelta(hours=1)))
        ),
        lambda source: _mutate_first_event(source, relations=()),
        lambda source: _mutate_first_event(
            source, relations=(E2OEvidence("wrong", "o0", "flow"),)
        ),
        lambda source: _mutate_first_event(
            source, relations=(E2OEvidence("e0_0", "wrong", "flow"),)
        ),
    ],
)
def test_malformed_trace_payload_is_invalid_input(mutation):
    result = evaluate_constraints(
        mutation(_traces("AB")),
        ConstraintSpec((ResponseRule("r", "A", "B"),), "closed"),
    )
    assert result.status is ComputeStatus.INVALID_INPUT and result.value is None


def _mutate_first_event(source, **changes):
    trace = source.value.traces[0]
    trace = replace(
        trace, events=(replace(trace.events[0], **changes), *trace.events[1:])
    )
    return replace(source, value=replace(source.value, traces=(trace,)))


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CountRule("", "A"),
        lambda: CountRule("r", ""),
        lambda: CountRule("r", "A", -1),
        lambda: CountRule("r", "A", True),
        lambda: CountRule("r", "A", 0, False),
        lambda: CountRule("r", "A", 2, 1),
        lambda: CountRule("r", "A", kind="response"),
        lambda: ResponseRule("r", "A", "B", kind="precedence"),
        lambda: PrecedenceRule("r", "A", "B", kind="response"),
        lambda: NotCoexistenceRule("r", "A", "B", kind="response"),
        lambda: ResponseRule("r", "A", ""),
        lambda: TimedResponseRule("r", "A", "B", -1, 10, "any"),
        lambda: TimedResponseRule("r", "A", "B", 0, False, "any"),
        lambda: TimedResponseRule("r", "A", "B", 0.5, 10, "any"),
        lambda: TimedResponseRule("r", "A", "B", 5, 4, "any"),
        lambda: TimedResponseRule("r", "A", "B", 0, 10, "nearest"),
        lambda: TimedResponseRule("r", "A", "B", 0, 10, "any", kind="response"),
        lambda: ConstraintSpec((), "closed"),
        lambda: ConstraintSpec([CountRule("r", "A")], "closed"),
        lambda: ConstraintSpec((CountRule("r", "A"),), "infer"),
        lambda: ConstraintSpec(
            (CountRule("r", "A"), ResponseRule("r", "A", "B")), "closed"
        ),
    ],
)
def test_contract_rejects_ambiguous_or_invalid_parameters(factory):
    with pytest.raises((ValueError, TypeError)):
        factory()


def test_observation_and_timed_selection_have_no_implicit_default():
    with pytest.raises(TypeError):
        ConstraintSpec((CountRule("r", "A"),))
    with pytest.raises(TypeError):
        TimedResponseRule("r", "A", "B", 0, 10)


def test_contract_immutability_and_policy_identity():
    rule = ResponseRule("r", "A", "B")
    with pytest.raises(FrozenInstanceError):
        rule.activity = "C"
    source = _traces("A")
    closed = evaluate_constraints(source, ConstraintSpec((rule,), "closed"))
    opened = evaluate_constraints(source, ConstraintSpec((rule,), "open"))
    assert closed.computation_id != opened.computation_id
    assert _evaluate("AB", rule).computation_id == _evaluate("AB", rule).computation_id


def test_huge_time_window_is_exact_and_cannot_overflow_datetime():
    result = _evaluate("AB", TimedResponseRule("r", "A", "B", 0, 10**100, "any"))
    assert _row(result).fulfilled_count == 1
    assert _row(result).witnesses[0].elapsed_microseconds == 1


def test_distinct_rule_ids_preserve_request_order_and_exact_labels():
    result = evaluate_constraints(
        _traces("AB"),
        ConstraintSpec((CountRule("z", "a", 1), CountRule("a", "A", 1)), "closed"),
    )
    assert [rule.rule_id for rule in result.value.rules] == ["z", "a"]
    assert result.value.rules[0].violated_count == 1
    assert result.value.rules[1].fulfilled_count == 1
