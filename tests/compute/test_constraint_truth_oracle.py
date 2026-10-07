"""Closed-trace constraint truth checked without reusing evaluator internals.

Every word over A/B/C of length zero through five becomes one real OCEL object.
Expected obligations are literal, quantified predicates over word positions.
This finite oracle is evidence for this domain, not a proof for arbitrary logs.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from pix.compute.constraints import evaluate_constraints
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.constraint import (
    ConstraintSpec,
    CountRule,
    NotCoexistenceRule,
    PrecedenceRule,
    ResponseRule,
    TimedResponseRule,
)
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType

ALPHABET = ("A", "B", "C")
WORDS = tuple(word for length in range(6) for word in product(ALPHABET, repeat=length))


@dataclass(frozen=True)
class TruthCase:
    rule_id: str
    kind: str
    activity: str
    target: str | None = None
    lower: int = 0
    upper: int | None = None
    selection: str | None = None

    def rule(self):
        if self.kind == "count":
            return CountRule(self.rule_id, self.activity, self.lower, self.upper)
        if self.kind == "response":
            return ResponseRule(self.rule_id, self.activity, self.target)
        if self.kind == "precedence":
            return PrecedenceRule(self.rule_id, self.activity, self.target)
        if self.kind == "not_coexistence":
            return NotCoexistenceRule(self.rule_id, self.activity, self.target)
        return TimedResponseRule(
            self.rule_id,
            self.activity,
            self.target,
            self.lower,
            self.upper,
            response_selection=self.selection,
        )


CASES = (
    tuple(
        TruthCase(
            f"count-{label}-{minimum}-{maximum}", "count", label, None, minimum, maximum
        )
        for label in ALPHABET
        for minimum in range(4)
        for maximum in (None, *range(minimum, 4))
    )
    + tuple(
        TruthCase(f"{kind}-{left}-{right}", kind, left, right)
        for kind in ("response", "precedence", "not_coexistence")
        for left, right in product(ALPHABET, repeat=2)
    )
    + tuple(
        TruthCase(
            f"timed-{left}-{right}-{minimum}-{maximum}-{selection}",
            "timed_response",
            left,
            right,
            minimum,
            maximum,
            selection,
        )
        for left, right in product(ALPHABET, repeat=2)
        for minimum, maximum in ((1, 2), (2, 2), (0, 0))
        for selection in ("any", "first")
    )
)


def _truth(case: TruthCase, word: tuple[str, ...]) -> tuple[tuple[bool, ...], bool]:
    """Return one truth value per obligation, and semantic vacuity.

    The predicates use positions, not timestamps parsed by production code.
    The fixture deliberately timestamps position i at exactly i microseconds.
    """
    positions = range(len(word))
    left = tuple(i for i in positions if word[i] == case.activity)
    right = tuple(i for i in positions if word[i] == case.target)
    if case.kind == "count":
        allowed = len(left) >= case.lower and (
            case.upper is None or len(left) <= case.upper
        )
        return (allowed,), False
    if case.kind == "not_coexistence":
        return (not (left and right),), False
    if case.kind == "response":
        return tuple(any(j > i for j in right) for i in left), not left
    if case.kind == "precedence":
        return tuple(any(i < j for i in left) for j in right), not right
    if case.selection == "any":
        return (
            tuple(
                any(j > i and case.lower <= j - i <= case.upper for j in right)
                for i in left
            ),
            not left,
        )
    # A target before the lower bound cannot be skipped under the first policy.
    return (
        tuple(
            any(
                j > i
                and case.lower <= j - i <= case.upper
                and not any(i < k < j for k in right)
                for j in right
            )
            for i in left
        ),
        not left,
    )


@pytest.fixture(scope="module")
def exhaustive_constraint_result():
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    events = []
    relations = []
    objects = []
    words_by_object = {}
    for number, word in enumerate(WORDS):
        object_id = f"word-{number:03d}"
        objects.append(Object(object_id, "case"))
        words_by_object[object_id] = word
        for position, activity in enumerate(word):
            event_id = f"{object_id}-event-{position}"
            events.append(
                Event(event_id, activity, origin + timedelta(microseconds=position))
            )
            relations.append(E2O(event_id, object_id, "observed"))
    log = OCEL(
        event_types=tuple(EventType(label) for label in ALPHABET),
        object_types=(ObjectType("case"),),
        objects=tuple(objects),
        events=tuple(events),
        e2o=tuple(relations),
    )
    source = reconstruct_traces(log, TraceSpec("case"))
    assert source.status is ComputeStatus.COMPUTED
    assert len(source.value.traces) == 364
    rules = tuple(case.rule() for case in CASES)
    assert all(rule.kind == case.kind for case, rule in zip(CASES, rules))
    spec = ConstraintSpec(rules, observation_policy="closed")
    result = evaluate_constraints(source, spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.object_type == "case"
    assert result.value.observation_policy == "closed"
    assert result.value.source_trace_computation_id == source.computation_id
    assert result.parent_computation_ids == (source.computation_id,)
    return result, words_by_object


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.rule_id)
def test_closed_observation_matches_exhaustive_word_truth(
    case, exhaustive_constraint_result
):
    result, words_by_object = exhaustive_constraint_result
    by_rule = {row.rule_id: row for row in result.value.rules}
    assert len(result.value.rules) == len(CASES)
    assert set(by_rule) == {item.rule_id for item in CASES}
    actual = by_rule[case.rule_id]
    assert actual.kind == case.kind
    assert actual.population == (
        "object_traces" if case.kind in ("count", "not_coexistence") else "activations"
    )
    by_object = {row.object_id: row for row in actual.traces}
    assert set(by_object) == set(words_by_object)
    assert len(actual.traces) == len(words_by_object)

    activation_count = fulfilled_count = violated_count = 0
    fulfilled_objects = violated_objects = vacuous_objects = 0
    for object_id, word in words_by_object.items():
        truth, vacuous = _truth(case, word)
        observed = by_object[object_id]
        fulfilled = sum(truth)
        violated = len(truth) - fulfilled
        description = f"{case.rule_id}, word={''.join(word)!r}"
        assert observed.activation_count == len(truth), description
        assert observed.fulfilled_count == fulfilled, description
        assert observed.violated_count == violated, description
        assert observed.pending_count == 0, description
        assert observed.vacuous is vacuous, description
        assert observed.status == ("violated" if violated else "fulfilled"), description
        assert len(observed.witnesses) == len(truth), description
        if case.kind in ("count", "not_coexistence"):
            activation_ids = (None,)
        else:
            activation_label = (
                case.target if case.kind == "precedence" else case.activity
            )
            activation_ids = tuple(
                f"{object_id}-event-{position}"
                for position, label in enumerate(word)
                if label == activation_label
            )
        expected_witness_statuses = {
            event_id: "fulfilled" if value else "violated"
            for event_id, value in zip(activation_ids, truth)
        }
        actual_witness_statuses = {
            witness.activation_event_id: witness.status
            for witness in observed.witnesses
        }
        assert actual_witness_statuses == expected_witness_statuses, description
        activation_count += len(truth)
        fulfilled_count += fulfilled
        violated_count += violated
        violated_objects += bool(violated)
        fulfilled_objects += not violated
        vacuous_objects += vacuous

    assert actual.activation_count == activation_count
    assert actual.fulfilled_count == fulfilled_count
    assert actual.violated_count == violated_count
    assert actual.pending_count == 0
    assert actual.fulfillment_ratio == (
        (fulfilled_count, activation_count) if activation_count else None
    )
    assert actual.object_count == 364
    assert actual.fulfilled_object_count == fulfilled_objects
    assert actual.violated_object_count == violated_objects
    assert actual.pending_object_count == 0
    assert actual.vacuous_object_count == vacuous_objects


def test_exhaustive_domain_contains_boundary_and_policy_counterexamples():
    """Keep the oracle's finite scope and distinguishing examples explicit."""
    assert len(WORDS) == len(set(WORDS)) == 364
    assert {
        length: sum(len(word) == length for word in WORDS) for length in range(6)
    } == {
        0: 1,
        1: 3,
        2: 9,
        3: 27,
        4: 81,
        5: 243,
    }
    any_case = TruthCase("any", "timed_response", "A", "B", 2, 2, "any")
    first_case = TruthCase("first", "timed_response", "A", "B", 2, 2, "first")
    assert _truth(any_case, tuple("ABBC"))[0] == (True,)
    assert _truth(first_case, tuple("ABBC"))[0] == (False,)
    assert _truth(TruthCase("self", "response", "A", "A"), ("A",))[0] == (False,)
    assert _truth(TruthCase("self", "precedence", "A", "A"), ("A",))[0] == (False,)
