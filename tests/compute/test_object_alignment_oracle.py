"""Independent finite-product oracle for joint object-centric alignment.

Generated fixtures have one concrete token per object, two object types and a
finite number of places. The oracle builds the entire Cartesian product of event
subsets and the two token positions, then runs Bellman--Ford. Neither expected
costs nor returned-path checks call PIX firing, binding or alignment internals.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from itertools import product
from random import Random

import pytest

from pix.compute.object_conformance import align_object_log
from pix.contracts.models import (
    ObjectArc,
    ObjectCentricPetriNet,
    ObjectMarking,
    ObjectToken,
    Transition,
    TypedPlace,
)
from pix.contracts.object_conformance import ObjectAlignmentSpec
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
    final: tuple[int, int]


def _groups(participants):
    return tuple(
        (object_type, (object_id,))
        for bit, object_type, object_id in ((1, "X", "x"), (2, "Y", "y"))
        if participants & bit
    )


def _snapshot(positions):
    return ((f"x{positions[0]}", "x"), (f"y{positions[1]}", "y"))


def _inputs(case):
    """Translate literal fixtures into public PIX input contracts only."""
    log = OCEL(
        object_types=(ObjectType("X"), ObjectType("Y")),
        event_types=tuple(
            EventType(activity)
            for activity in sorted({e.activity for e in case.events})
        ),
        objects=(Object("x", "X"), Object("y", "Y")),
        events=tuple(
            Event(
                f"e{i}",
                event.activity,
                datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i),
            )
            for i, event in enumerate(case.events)
        ),
        e2o=tuple(
            E2O(f"e{i}", object_id, "")
            for i, event in enumerate(case.events)
            for bit, object_id in ((1, "x"), (2, "y"))
            if event.participants & bit
        ),
    )
    arcs = []
    for i, transition in enumerate(case.transitions):
        for prefix, incidence in (("x", transition.x), ("y", transition.y)):
            if incidence is not None:
                source, target = incidence
                arcs.extend(
                    (
                        ObjectArc(f"{prefix}{source}", f"t{i}"),
                        ObjectArc(f"t{i}", f"{prefix}{target}"),
                    )
                )
    net = ObjectCentricPetriNet(
        places=tuple(
            TypedPlace(f"{prefix}{i}", object_type)
            for prefix, object_type, count in (
                ("x", "X", case.place_counts[0]),
                ("y", "Y", case.place_counts[1]),
            )
            for i in range(count)
        ),
        transitions=tuple(
            Transition(f"t{i}", transition.activity)
            for i, transition in enumerate(case.transitions)
        ),
        arcs=tuple(arcs),
        initial_marking=ObjectMarking(
            tuple(ObjectToken(place, obj) for place, obj in _snapshot(case.initial))
        ),
        final_marking=ObjectMarking(
            tuple(ObjectToken(place, obj) for place, obj in _snapshot(case.final))
        ),
        objects=(("x", "X"), ("y", "Y")),
    )
    return log, net


def _predecessors(events):
    # All earlier events sharing an object precede this event. Taking all earlier
    # ancestors rather than only direct predecessors gives the same downsets.
    return tuple(
        sum(
            1 << previous
            for previous in range(current)
            if events[previous].participants & event.participants
        )
        for current, event in enumerate(events)
    )


def _weight(participants, spec):
    return 1 if spec.cost_mode == "event" else participants.bit_count()


def _literal_target(transition, positions):
    incidences = (transition.x, transition.y)
    if any(
        incidence is not None and incidence[0] != position
        for incidence, position in zip(incidences, positions)
    ):
        return None
    return tuple(
        position if incidence is None else incidence[1]
        for incidence, position in zip(incidences, positions)
    )


def _oracle(case, spec):
    """Solve a literal finite graph, without importing any PIX search helper."""
    vertices = tuple(
        product(
            range(1 << len(case.events)),
            range(case.place_counts[0]),
            range(case.place_counts[1]),
        )
    )
    predecessors = _predecessors(case.events)
    edges = []
    for state in vertices:
        consumed, x, y = state
        ready = tuple(
            i
            for i in range(len(case.events))
            if not consumed & (1 << i) and consumed & predecessors[i] == predecessors[i]
        )
        for i in ready:
            edges.append(
                (
                    state,
                    (consumed | (1 << i), x, y),
                    spec.log_move_cost * _weight(case.events[i].participants, spec),
                )
            )
        for transition in case.transitions:
            target = _literal_target(transition, (x, y))
            if target is None:
                continue
            model_cost = (
                spec.silent_move_cost
                if transition.activity is None
                else spec.model_move_cost
            ) * _weight(transition.participants, spec)
            edges.append((state, (consumed, *target), model_cost))
            for i in ready:
                event = case.events[i]
                if (
                    transition.activity is not None
                    and transition.activity == event.activity
                    and transition.participants == event.participants
                ):
                    edges.append(
                        (
                            state,
                            (consumed | (1 << i), *target),
                            spec.synchronous_move_cost
                            * _weight(event.participants, spec),
                        )
                    )
    distances = {(0, *case.initial): 0}
    for _ in range(len(vertices) - 1):
        changed = False
        for source, target, cost in edges:
            if source not in distances:
                continue
            candidate = distances[source] + cost
            if target not in distances or candidate < distances[target]:
                distances[target] = candidate
                changed = True
        if not changed:
            break
    return distances.get(((1 << len(case.events)) - 1, *case.final))


def _assert_path(case, spec, alignment):
    """Check concrete token changes and event ordering using only literal data."""
    positions = case.initial
    consumed = 0
    total_cost = 0
    predecessors = _predecessors(case.events)
    for move in alignment.moves:
        assert move.before_marking == _snapshot(positions)
        event = None
        if move.kind in ("log", "synchronous"):
            assert move.event_id is not None
            index = int(move.event_id.removeprefix("e"))
            assert 0 <= index < len(case.events)
            assert not consumed & (1 << index)
            assert consumed & predecessors[index] == predecessors[index]
            event = case.events[index]
            consumed |= 1 << index
        else:
            assert move.event_id is None
        if move.kind == "log":
            assert move.transition_id is None
            assert event is not None
            participants = event.participants
            assert move.activity == event.activity
            base_cost = spec.log_move_cost
        else:
            assert move.transition_id is not None
            index = int(move.transition_id.removeprefix("t"))
            assert 0 <= index < len(case.transitions)
            transition = case.transitions[index]
            target = _literal_target(transition, positions)
            assert target is not None
            positions = target
            participants = transition.participants
            assert move.activity == transition.activity
            if move.kind == "synchronous":
                assert event is not None
                assert transition.activity == event.activity
                assert participants == event.participants
                base_cost = spec.synchronous_move_cost
            elif move.kind == "silent":
                assert transition.activity is None
                base_cost = spec.silent_move_cost
            else:
                assert move.kind == "model"
                assert transition.activity is not None
                base_cost = spec.model_move_cost
        assert move.objects == _groups(participants)
        assert move.weight == _weight(participants, spec)
        assert move.cost == base_cost * move.weight
        assert move.after_marking == _snapshot(positions)
        total_cost += move.cost
    assert consumed == (1 << len(case.events)) - 1
    assert positions == case.final
    assert total_cost == alignment.cost


@pytest.mark.parametrize("cost_mode", ("event", "object"))
@pytest.mark.parametrize("case_index", range(96))
def test_seeded_joint_products_match_independent_bellman_ford(case_index, cost_mode):
    rng = Random(270319 + case_index)
    counts = (rng.randrange(1, 4), rng.randrange(1, 4))
    transitions = []
    for _ in range(rng.randrange(0, 9)):
        participants = rng.randrange(4)
        transitions.append(
            LiteralTransition(
                rng.choice((None, "A", "B")),
                (rng.randrange(counts[0]), rng.randrange(counts[0]))
                if participants & 1
                else None,
                (rng.randrange(counts[1]), rng.randrange(counts[1]))
                if participants & 2
                else None,
            )
        )
    case = FiniteCase(
        counts,
        tuple(transitions),
        tuple(
            LiteralEvent(rng.choice(("A", "B", "unknown")), rng.randrange(4))
            for _ in range(rng.randrange(5))
        ),
        (rng.randrange(counts[0]), rng.randrange(counts[1])),
        (rng.randrange(counts[0]), rng.randrange(counts[1])),
    )
    state_count = counts[0] * counts[1] * (1 << len(case.events))
    spec = ObjectAlignmentSpec(
        object_types=("X", "Y"),
        cost_mode=cost_mode,
        log_move_cost=rng.randrange(4),
        model_move_cost=rng.randrange(4),
        silent_move_cost=rng.randrange(4),
        synchronous_move_cost=rng.randrange(4),
        max_states=state_count,
        max_bindings=10000,
    )
    log, net = _inputs(case)
    expected = _oracle(case, spec)
    result = align_object_log(log, net, spec)
    alignment = result.value
    assert result.status is ComputeStatus.COMPUTED
    assert alignment.status == ("unreachable" if expected is None else "optimal")
    assert alignment.cost == expected
    assert alignment.settled_states <= state_count
    if expected is None:
        assert alignment.moves == ()
        assert alignment.lower_bound_cost is None
    else:
        assert alignment.lower_bound_cost == expected
        _assert_path(case, spec, alignment)

    for bound in (1, 2):
        bounded_spec = replace(spec, max_states=bound)
        bounded_result = align_object_log(log, net, bounded_spec)
        bounded = bounded_result.value
        assert bounded.settled_states <= bound
        if bounded.status == "optimal":
            assert bounded_result.status is ComputeStatus.COMPUTED
            assert bounded.cost == expected
            _assert_path(case, bounded_spec, bounded)
        elif bounded.status == "unreachable":
            assert bounded_result.status is ComputeStatus.COMPUTED
            assert expected is None
        else:
            assert bounded.status == "search_limit"
            assert bounded_result.status is ComputeStatus.PARTIAL
            assert bounded.settled_states == bound
            assert bounded.cost is None
            assert bounded.moves == ()
            assert bounded.lower_bound_cost is not None
            assert bounded.lower_bound_cost >= 0
            if expected is not None:
                assert bounded.lower_bound_cost <= expected


def test_typewise_fitting_choices_do_not_imply_one_joint_fitting_binding():
    # X can accept A through t0, Y through t1. Those choices refer to different
    # shared transitions. A joint execution needs a visible repair B or C.
    case = FiniteCase(
        (3, 3),
        (
            LiteralTransition("A", (0, 1), (0, 2)),
            LiteralTransition("A", (0, 2), (0, 1)),
            LiteralTransition("B", (2, 1)),
            LiteralTransition("C", y=(2, 1)),
        ),
        (LiteralEvent("A", 3),),
        (0, 0),
        (1, 1),
    )
    x_accepting = {
        i for i, t in enumerate(case.transitions) if t.activity == "A" and t.x == (0, 1)
    }
    y_accepting = {
        i for i, t in enumerate(case.transitions) if t.activity == "A" and t.y == (0, 1)
    }
    assert x_accepting == {0}
    assert y_accepting == {1}
    assert not x_accepting & y_accepting
    spec = ObjectAlignmentSpec(object_types=("X", "Y"))
    assert _oracle(case, spec) == 1
    result = align_object_log(*_inputs(case), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.cost == 1
    assert sum(move.kind == "synchronous" for move in result.value.moves) == 1
    assert sum(move.kind == "model" for move in result.value.moves) == 1
    _assert_path(case, spec, result.value)


def test_independent_events_can_commute_across_global_timestamp_order():
    case = FiniteCase(
        (3, 3),
        (
            LiteralTransition("A", (1, 2)),
            LiteralTransition("B", y=(0, 1)),
            LiteralTransition(None, (0, 1), (1, 2)),
        ),
        (LiteralEvent("A", 1), LiteralEvent("B", 2)),
        (0, 0),
        (2, 2),
    )
    spec = ObjectAlignmentSpec(object_types=("X", "Y"))
    assert _oracle(case, spec) == 0
    result = align_object_log(*_inputs(case), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.cost == 0
    assert tuple(m.event_id for m in result.value.moves if m.event_id) == ("e1", "e0")
    _assert_path(case, spec, result.value)


@pytest.mark.parametrize(("cost_mode", "expected"), (("event", 1), ("object", 2)))
def test_shared_event_is_consumed_once_with_an_explicit_cost_weight(
    cost_mode, expected
):
    case = FiniteCase(
        (2, 2),
        (LiteralTransition("A", (0, 1), (0, 1)),),
        (LiteralEvent("A", 3),),
        (0, 0),
        (1, 1),
    )
    spec = ObjectAlignmentSpec(
        object_types=("X", "Y"),
        cost_mode=cost_mode,
        log_move_cost=5,
        model_move_cost=5,
        synchronous_move_cost=1,
    )
    assert _oracle(case, spec) == expected
    result = align_object_log(*_inputs(case), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.cost == expected
    assert len(result.value.moves) == 1
    assert result.value.moves[0].kind == "synchronous"
    _assert_path(case, spec, result.value)


@pytest.mark.parametrize(("cost_mode", "expected"), (("event", 1), ("object", 0)))
def test_zero_object_log_move_has_explicit_zero_object_weight(cost_mode, expected):
    case = FiniteCase((1, 1), (), (LiteralEvent("unmatched", 0),), (0, 0), (0, 0))
    spec = ObjectAlignmentSpec(object_types=("X", "Y"), cost_mode=cost_mode)
    assert _oracle(case, spec) == expected
    result = align_object_log(*_inputs(case), spec)
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.cost == expected
    assert len(result.value.moves) == 1
    assert result.value.moves[0].kind == "log"
    # A zero minimum cost in the object profile can still contain a deviation.
    _assert_path(case, spec, result.value)
