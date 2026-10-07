"""Independent finite-graph oracle for native trace alignment.

Each generated net carries exactly one token. The reference product graph uses
integer place indices and direct transition tuples, without PIX firing or
alignment internals. Bellman--Ford supplies expected costs independently of the
production Dijkstra search. Fixed seeds make every failing case reproducible.
"""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from random import Random

import pytest

from pix.compute.conformance import align_traces
from pix.compute.trace import reconstruct_traces
from pix.contracts.analysis import TraceSpec
from pix.contracts.conformance import AlignmentSpec
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def _traces(*sequences):
    activities = sorted({activity for sequence in sequences for activity in sequence})
    events = []
    relations = []
    for object_index, sequence in enumerate(sequences):
        for event_index, activity in enumerate(sequence):
            event_id = f"e{object_index}_{event_index}"
            events.append(
                Event(
                    event_id,
                    activity,
                    datetime(2026, 1, 1, tzinfo=timezone.utc)
                    + timedelta(seconds=event_index),
                )
            )
            relations.append(E2O(event_id, f"o{object_index}", ""))
    return reconstruct_traces(
        OCEL(
            object_types=(ObjectType("case"),),
            event_types=tuple(EventType(activity) for activity in activities),
            objects=tuple(Object(f"o{i}", "case") for i in range(len(sequences))),
            events=tuple(events),
            e2o=tuple(relations),
        ),
        TraceSpec("case"),
    )


def _net(place_count, edges, initial, final):
    return PetriNet(
        tuple(Place(f"p{i}") for i in range(place_count)),
        tuple(
            Transition(f"t{i}", activity) for i, (_, _, activity) in enumerate(edges)
        ),
        tuple(
            arc
            for i, (source, target, _) in enumerate(edges)
            for arc in (
                Arc(f"p{source}", f"t{i}"),
                Arc(f"t{i}", f"p{target}"),
            )
        ),
        Marking(((f"p{initial}", 1),)),
        Marking(((f"p{final}", 1),)),
    )


def _oracle(place_count, edges, sequence, initial, final, spec):
    vertices = [
        (position, place)
        for position in range(len(sequence) + 1)
        for place in range(place_count)
    ]
    product_edges = []
    for position, place in vertices:
        if position < len(sequence):
            product_edges.append(
                ((position, place), (position + 1, place), spec.log_move_cost)
            )
        for source, target, activity in edges:
            if source != place:
                continue
            product_edges.append(
                (
                    (position, place),
                    (position, target),
                    spec.silent_move_cost if activity is None else spec.model_move_cost,
                )
            )
            if (
                activity is not None
                and position < len(sequence)
                and activity == sequence[position]
            ):
                product_edges.append(
                    (
                        (position, place),
                        (position + 1, target),
                        spec.synchronous_move_cost,
                    )
                )

    distances = {(0, initial): 0}
    for _ in range(len(vertices) - 1):
        changed = False
        for source, target, cost in product_edges:
            if source not in distances:
                continue
            candidate = distances[source] + cost
            if target not in distances or candidate < distances[target]:
                distances[target] = candidate
                changed = True
        if not changed:
            break
    return distances.get((len(sequence), final))


def _assert_path(alignment, edges, sequence, initial, final, spec):
    transitions = {f"t{i}": edge for i, edge in enumerate(edges)}
    place = initial
    position = 0
    cost = 0
    for move in alignment.moves:
        assert move.before_marking == ((f"p{place}", 1),)
        if move.kind == "log":
            assert move.transition_id is None
            assert move.activity == sequence[position]
            assert move.cost == spec.log_move_cost
        else:
            source, target, activity = transitions[move.transition_id]
            assert source == place
            place = target
            assert move.activity == activity
            if move.kind == "synchronous":
                assert activity is not None and activity == sequence[position]
                assert move.cost == spec.synchronous_move_cost
            elif move.kind == "silent":
                assert activity is None
                assert move.cost == spec.silent_move_cost
            else:
                assert move.kind == "model" and activity is not None
                assert move.cost == spec.model_move_cost
        if move.kind in ("synchronous", "log"):
            assert move.event_id == f"e0_{position}"
            position += 1
        else:
            assert move.event_id is None
        assert move.after_marking == ((f"p{place}", 1),)
        cost += move.cost
    assert position == len(sequence)
    assert place == final
    assert cost == alignment.cost
    assert alignment.event_ids == tuple(f"e0_{i}" for i in range(len(sequence)))


@pytest.mark.parametrize("case_index", range(300))
def test_seeded_finite_nets_match_independent_bellman_ford(case_index):
    rng = Random(93281 + case_index)
    place_count = rng.randrange(1, 5)
    edges = tuple(
        (
            rng.randrange(place_count),
            rng.randrange(place_count),
            rng.choice((None, "A", "B")),
        )
        for _ in range(rng.randrange(0, 9))
    )
    sequence = tuple(rng.choice(("A", "B", "X")) for _ in range(rng.randrange(0, 5)))
    initial, final = rng.randrange(place_count), rng.randrange(place_count)
    state_count = place_count * (len(sequence) + 1)
    spec = AlignmentSpec(
        log_move_cost=rng.randrange(0, 5),
        model_move_cost=rng.randrange(0, 5),
        silent_move_cost=rng.randrange(0, 5),
        synchronous_move_cost=rng.randrange(0, 5),
        max_states=state_count,
    )
    expected = _oracle(place_count, edges, sequence, initial, final, spec)
    source = _traces(sequence)
    net = _net(place_count, edges, initial, final)
    result = align_traces(source, net, spec)
    alignment = result.value.alignments[0]
    assert result.status is ComputeStatus.COMPUTED
    assert alignment.cost == expected
    assert alignment.status == ("unreachable" if expected is None else "optimal")
    assert alignment.settled_states <= state_count
    if expected is not None:
        assert alignment.lower_bound_cost == expected
        _assert_path(alignment, edges, sequence, initial, final, spec)
    else:
        assert alignment.moves == ()
        assert alignment.lower_bound_cost is None

    for bound in (1, 2, 3):
        bounded_spec = replace(spec, max_states=bound)
        bounded_result = align_traces(source, net, bounded_spec)
        bounded = bounded_result.value.alignments[0]
        assert bounded.settled_states <= bound
        if bounded.status == "optimal":
            assert bounded_result.status is ComputeStatus.COMPUTED
            assert bounded.cost == expected
            _assert_path(bounded, edges, sequence, initial, final, bounded_spec)
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


def test_nonzero_partial_cost_covers_only_optimal_alignment():
    result = align_traces(
        _traces(("X",), ("X", "X")),
        _net(1, (), 0, 0),
        AlignmentSpec(max_states=2),
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.coverage.requested == 2
    assert result.value.coverage.optimal == 1
    assert result.value.coverage.search_limit == 1
    assert result.value.completed_cost_sum == 1
    assert result.value.mean_completed_cost_ratio == (1, 1)
    assert result.value.total_cost is None
    assert result.value.alignments[1].lower_bound_cost == 2


def test_fractional_mean_retains_exact_numerator_and_population():
    result = align_traces(_traces((), ("X",)), _net(1, (), 0, 0))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.coverage.optimal == 2
    assert result.value.completed_cost_sum == 1
    assert result.value.total_cost == 1
    assert result.value.mean_completed_cost_ratio == (1, 2)
