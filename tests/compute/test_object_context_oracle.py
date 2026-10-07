"""Independent finite-position oracle for concrete-object prefix metrics.

The oracle explores literal (event subset, two token positions) states. It does
not call PIX scope, binding, firing, or reachability helpers, and does not use an
uncapped PIX result as the expectation for capped results. The fixtures cover
silent cycles, duplicate activity labels, joint and independent participation,
empty-participation model transitions, and nonfitting observed prefixes.

This finite unit-incidence family does not establish correctness for arbitrary
variable cardinalities or infinite token-producing silent reachability.
"""

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from pix.compute.object_context import measure_object_context
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.object_context import ObjectContextSpec
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


@dataclass(frozen=True)
class LiteralTransition:
    activity: str | None
    x: tuple[int, int] | None = None
    y: tuple[int, int] | None = None

    @property
    def participants(self):
        return int(self.x is not None) + 2 * int(self.y is not None)


@dataclass(frozen=True)
class LiteralEvent:
    activity: str
    participants: int


@dataclass(frozen=True)
class FiniteCase:
    place_counts: tuple[int, int]
    transitions: tuple[LiteralTransition, ...]
    events: tuple[LiteralEvent, ...]
    initial: tuple[int, int]


@dataclass(frozen=True)
class LiteralContext:
    observed: frozenset[tuple[str, int]]
    modeled: frozenset[tuple[str, int]]
    positions: frozenset[tuple[int, int]]
    next_indices: tuple[int, ...]


def _case(seed):
    rng = Random(93822 + seed)
    counts = (rng.randrange(1, 4), rng.randrange(1, 4))
    transitions = []
    for _ in range(rng.randrange(1, 9)):
        bits = rng.randrange(4)
        transitions.append(
            LiteralTransition(
                rng.choice(("A", "B", None)),
                (rng.randrange(counts[0]), rng.randrange(counts[0]))
                if bits & 1
                else None,
                (rng.randrange(counts[1]), rng.randrange(counts[1]))
                if bits & 2
                else None,
            )
        )
    events = tuple(
        LiteralEvent(rng.choice(("A", "B", "C")), rng.randrange(1, 4))
        for _ in range(rng.randrange(1, 6))
    )
    return FiniteCase(
        counts,
        tuple(transitions),
        events,
        (rng.randrange(counts[0]), rng.randrange(counts[1])),
    )


def _inputs(case):
    """Convert literal fixtures using public input contracts only."""
    log = OCEL(
        object_types=(ObjectType("X"), ObjectType("Y")),
        event_types=tuple(
            EventType(activity)
            for activity in sorted({event.activity for event in case.events})
        ),
        objects=(Object("x", "X"), Object("y", "Y")),
        events=tuple(
            Event(
                f"e{index}",
                event.activity,
                datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=index),
            )
            for index, event in enumerate(case.events)
        ),
        e2o=tuple(
            E2O(f"e{index}", object_id, "")
            for index, event in enumerate(case.events)
            for bit, object_id in ((1, "x"), (2, "y"))
            if event.participants & bit
        ),
    )
    arcs = []
    for index, transition in enumerate(case.transitions):
        for prefix, incidence in (("x", transition.x), ("y", transition.y)):
            if incidence is not None:
                source, target = incidence
                arcs.extend(
                    (
                        ObjectArc(f"{prefix}{source}", f"t{index}"),
                        ObjectArc(f"t{index}", f"{prefix}{target}"),
                    )
                )
    net = ObjectCentricPetriNet(
        places=tuple(
            TypedPlace(f"{prefix}{index}", kind)
            for prefix, kind, count in (
                ("x", "X", case.place_counts[0]),
                ("y", "Y", case.place_counts[1]),
            )
            for index in range(count)
        ),
        transitions=tuple(
            Transition(f"t{index}", transition.activity)
            for index, transition in enumerate(case.transitions)
        ),
        arcs=tuple(arcs),
        initial_marking=ObjectMarking(
            (
                ObjectToken(f"x{case.initial[0]}", "x"),
                ObjectToken(f"y{case.initial[1]}", "y"),
            )
        ),
        # This is intentionally arbitrary: terminal acceptance is excluded by
        # the metric profile, including in the independent expectation.
        final_marking=ObjectMarking((ObjectToken("x0", "x"), ObjectToken("y0", "y"))),
        objects=(("x", "X"), ("y", "Y")),
    )
    return log, net


def _oracle(case):
    """Exhaustively search a finite product without PIX computational helpers."""
    events = case.events
    next_indices = {}
    for subset in range(1 << len(events)):
        # Reject a subset if a consumed event has an earlier unconsumed event
        # on either of its concrete objects. No implementation downset helper
        # or predecessor relation is used to establish this population.
        if any(
            subset >> index & 1
            and any(
                not subset >> before & 1
                and events[index].participants & events[before].participants
                for before in range(index)
            )
            for index in range(len(events))
        ):
            continue
        next_indices[subset] = tuple(
            index
            for index, event in enumerate(events)
            if not subset >> index & 1
            and all(
                subset >> before & 1
                or not event.participants & events[before].participants
                for before in range(index)
            )
        )

    initial = (0, case.initial)
    queue = deque((initial,))
    visited = {initial}
    modeled = defaultdict(set)
    while queue:
        subset, positions = queue.popleft()
        for transition in case.transitions:
            if (transition.x and transition.x[0] != positions[0]) or (
                transition.y and transition.y[0] != positions[1]
            ):
                continue
            following = (
                transition.x[1] if transition.x else positions[0],
                transition.y[1] if transition.y else positions[1],
            )
            if transition.activity is None:
                successors = ((subset, following),)
            else:
                behavior = (transition.activity, transition.participants)
                if transition.participants:
                    modeled[subset].add(behavior)
                successors = tuple(
                    (subset | 1 << index, following)
                    for index in next_indices[subset]
                    if (events[index].activity, events[index].participants) == behavior
                )
            for successor in successors:
                if successor not in visited:
                    visited.add(successor)
                    queue.append(successor)

    contexts = {
        subset: LiteralContext(
            frozenset(
                (events[index].activity, events[index].participants)
                for index in indices
            ),
            frozenset(modeled[subset]),
            frozenset(positions for mask, positions in visited if mask == subset),
            indices,
        )
        for subset, indices in next_indices.items()
        if indices
    }
    return contexts, len(next_indices)


def _behaviors(rows):
    """Inspect all reported participant identities, not just their cardinality."""
    masks = {("X", ("x",)): 1, ("Y", ("y",)): 2}
    return frozenset(
        (row.activity, sum(masks[entry] for entry in row.objects)) for row in rows
    )


def _ratio(numerator, denominator):
    return (numerator, denominator) if denominator else None


def _assert_complete_row(case, subset, row, expected):
    assert row.complete
    assert row.limit_reasons == ()
    assert _behaviors(row.observed_behaviors) == expected.observed
    assert _behaviors(row.model_behaviors) == expected.modeled
    assert _behaviors(row.matching_behaviors) == expected.observed & expected.modeled
    assert row.reachable_model_states == len(expected.positions)
    assert row.next_event_ids == tuple(f"e{i}" for i in expected.next_indices)
    assert tuple(
        (history.object_id, history.object_type, history.activities)
        for history in row.histories
    ) == tuple(
        (
            object_id,
            kind,
            tuple(
                event.activity
                for index, event in enumerate(case.events)
                if subset >> index & 1 and event.participants & bit
            ),
        )
        for bit, object_id, kind in ((1, "x", "X"), (2, "y", "Y"))
    )
    matching = len(expected.observed & expected.modeled)
    assert row.fitness_ratio == _ratio(matching, len(expected.observed))
    assert row.precision_ratio == _ratio(matching, len(expected.modeled))


def _assert_aggregate(value, expected_contexts, completed_subsets):
    completed = [expected_contexts[subset] for subset in completed_subsets]
    matching = sum(len(row.observed & row.modeled) for row in completed)
    observed = sum(len(row.observed) for row in completed)
    modeled = sum(len(row.modeled) for row in completed)
    assert value.complete_context_intersection_count == matching
    assert value.complete_context_observed_count == observed
    assert value.complete_context_model_count == modeled
    assert value.complete_context_fitness_ratio == _ratio(matching, observed)
    assert value.complete_context_precision_ratio == _ratio(matching, modeled)


def _subset(row):
    return sum(1 << int(event_id[1:]) for event_id in row.consumed_event_ids)


@pytest.mark.parametrize("seed", range(400))
def test_context_metrics_match_independent_finite_product(seed):
    case = _case(seed)
    expected, log_state_count = _oracle(case)
    result = measure_object_context(*_inputs(case), ObjectContextSpec(("X", "Y")))
    assert result.status is ComputeStatus.COMPUTED
    value = result.value
    rows = {_subset(row): row for row in value.contexts}
    assert len(rows) == len(value.contexts)
    assert len({row.context_id for row in value.contexts}) == len(value.contexts)
    assert set(rows) == set(expected)
    for subset, row in rows.items():
        _assert_complete_row(case, subset, row, expected[subset])
    _assert_aggregate(value, expected, rows)
    assert value.coverage.requested_contexts == len(expected)
    assert value.coverage.completed_contexts == len(expected)
    assert value.coverage.enumerated_log_states == log_state_count
    assert value.coverage.terminal_prefix_count == 1
    assert value.full_scope_fitness_ratio == value.complete_context_fitness_ratio
    assert value.full_scope_precision_ratio == value.complete_context_precision_ratio


@pytest.mark.parametrize("seed", range(200))
@pytest.mark.parametrize(
    "bound_name", ("max_log_states", "max_context_states", "max_bindings")
)
@pytest.mark.parametrize("cap", (1, 2))
def test_capped_context_claims_remain_valid_against_finite_oracle(
    seed, bound_name, cap
):
    case = _case(seed)
    expected, _ = _oracle(case)
    result = measure_object_context(
        *_inputs(case), ObjectContextSpec(("X", "Y"), **{bound_name: cap})
    )
    value = result.value
    rows = {_subset(row): row for row in value.contexts}
    assert len(rows) == len(value.contexts)
    completed = []
    for subset, row in rows.items():
        assert subset in expected
        if row.complete:
            _assert_complete_row(case, subset, row, expected[subset])
            completed.append(subset)
        else:
            assert row.limit_reasons
            assert row.fitness_ratio is None
            assert row.precision_ratio is None
    _assert_aggregate(value, expected, completed)
    assert value.coverage.completed_contexts == len(completed)
    assert value.coverage.incomplete_contexts == len(rows) - len(completed)
    if result.status is ComputeStatus.COMPUTED:
        assert set(rows) == set(expected)
        assert len(completed) == len(expected)
        assert value.full_scope_fitness_ratio == value.complete_context_fitness_ratio
        assert (
            value.full_scope_precision_ratio == value.complete_context_precision_ratio
        )
    else:
        assert result.status is ComputeStatus.PARTIAL
        assert value.full_scope_fitness_ratio is None
        assert value.full_scope_precision_ratio is None
