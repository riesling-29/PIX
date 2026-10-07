"""Independent OCEL counts, arc witness evidence, and SAW counterexamples."""

from collections import Counter
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from itertools import product
from unittest.mock import patch

import pytest

from pix.compute.context import ComputationContext
from pix.compute.model_semantics import fire_binding
from pix.contracts.ocpn_discovery import OCPNDiscoverySpec
from pix.contracts.result import ComputeStatus
from pix.object_centric.discovery import (
    PROFILE,
    RESULT_SCHEMAS,
    SAWArcWeightDistribution,
    SAWDiscoverySpec,
    discover_saw_net,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def log_of(rows, objects):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(name) for name in sorted({row[1] for row in rows})),
        object_types=tuple(
            ObjectType(name) for name in sorted({kind for _, kind in objects})
        ),
        events=tuple(
            Event(eid, activity, origin + timedelta(seconds=i))
            for i, (eid, activity, _) in enumerate(rows)
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects),
        e2o=tuple(E2O(eid, oid, "flow") for eid, _, ids in rows for oid in ids),
    )


def request(types=("item",), **kwargs):
    return SAWDiscoverySpec(
        OCPNDiscoverySpec(types, "observed_range", "unique_activity", **kwargs)
    )


def checked(log, spec=None):
    result = discover_saw_net(log, spec or request())
    assert result.status is ComputeStatus.COMPUTED, result.issues
    value = result.value
    marking = value.model.initial_marking
    for step in value.discovery.fitting_witness:
        marking = fire_binding(value.model, marking, step.binding)
    assert marking == value.model.final_marking
    return result


def visible_rows(value, activity, kind):
    transitions = {t.id for t in value.model.transitions if t.activity == activity}
    return tuple(
        row
        for row in value.arc_distributions
        if row.transition_id in transitions and row.object_type == kind
    )


def test_join_then_split_uses_each_events_object_count_not_relation_or_total_tokens():
    log = log_of(
        (
            ("pack", "Pack", ("i1", "i2")),
            ("ship1", "Ship", ("i1",)),
            ("ship2", "Ship", ("i2",)),
        ),
        (("i1", "item"), ("i2", "item")),
    )
    value = checked(log).value
    pack = visible_rows(value, "Pack", "item")
    ship = visible_rows(value, "Ship", "item")
    assert len(pack) == len(ship) == 2
    assert all(row.histogram == ((2, 1),) and row.sample_count == 1 for row in pack)
    assert all(row.histogram == ((1, 2),) and row.sample_count == 2 for row in ship)
    assert pack[0].witness_indices == pack[1].witness_indices


def test_histogram_holes_have_zero_mass_not_uniform_range_mass():
    log = log_of(
        (("e1", "A", ("i1",)), ("e2", "A", ("i2", "i3", "i4"))),
        tuple((f"i{i}", "item") for i in range(1, 5)),
    )
    value = checked(log).value
    for row in visible_rows(value, "A", "item"):
        assert row.histogram == ((1, 1), (3, 1))
        assert row.support == (1, 3)
        assert row.probability(1) == row.probability(3) == Fraction(1, 2)
        assert row.probability(2) == 0
        assert row.expected_weight == 2
    assert all(
        arc.min_objects == 1 and arc.max_objects == 3 for arc in value.model.arcs
    )


def test_zero_participation_has_mass_and_correlated_types_are_not_independent():
    log = log_of(
        (("e1", "A", ("o1",)), ("e2", "A", ("i1",))),
        (("o1", "order"), ("i1", "item")),
    )
    value = checked(log, request(("item", "order"))).value
    assert value.probability_scope == "empirical_arc_marginals"
    assert value.joint_probability_policy == "not_inferred"
    for row in value.arc_distributions:
        assert row.histogram == ((0, 1), (1, 1))
        assert row.probability(0) == Fraction(1, 2)
    joint_counts = Counter(
        tuple(
            len(dict(observation.binding.objects).get(kind, ()))
            for kind in ("item", "order")
        )
        for observation in value.discovery.observed_event_bindings
    )
    assert joint_counts == {(0, 1): 1, (1, 0): 1}
    assert (0, 0) not in joint_counts  # multiplying marginal mass would invent this.


def test_duplicate_roles_are_unique_objects_and_qualifier_selection_changes_samples():
    log = log_of(
        (("e1", "A", ("i1",)), ("e2", "A", ("i2",))),
        (("i1", "item"), ("i2", "item")),
    )
    log = replace(log, e2o=(*log.e2o, E2O("e1", "i1", "audit")))
    all_roles = checked(log).value
    audit_only = checked(log, request(qualifiers=("audit",))).value
    assert all(
        row.histogram == ((1, 2),) for row in visible_rows(all_roles, "A", "item")
    )
    assert all(
        row.histogram == ((0, 1), (1, 1))
        for row in visible_rows(audit_only, "A", "item")
    )


def test_whole_log_orphan_event_retained_without_fabricating_an_arc():
    log = log_of((("e1", "A", ("i1",)), ("e2", "Orphan", ())), (("i1", "item"),))
    value = checked(log).value
    orphan = next(t for t in value.model.transitions if t.activity == "Orphan")
    assert not any(row.transition_id == orphan.id for row in value.arc_distributions)
    assert value.discovery.observed_event_bindings[-1].event_id == "e2"
    assert value.discovery.observed_event_bindings[-1].binding.objects == ()


def test_silent_parallel_split_counts_each_binding_not_adjacent_visible_events():
    log = log_of(
        (
            ("a1", "A", ("i1",)),
            ("b1", "B", ("i1",)),
            ("c1", "C", ("i1",)),
            ("d1", "D", ("i1",)),
            ("a2", "A", ("i2",)),
            ("c2", "C", ("i2",)),
            ("b2", "B", ("i2",)),
            ("d2", "D", ("i2",)),
        ),
        (("i1", "item"), ("i2", "item")),
    )
    result = checked(log)
    value = result.value
    silent = tuple(
        row
        for row in value.arc_distributions
        if row.sample_basis == "silent_witness_steps"
    )
    assert silent
    for row in silent:
        assert row.histogram == ((1, 2),)
        for index in row.witness_indices:
            assert value.discovery.fitting_witness[index].event_id is None
    assert "witness_dependent_silent_weights" in {issue.code for issue in result.issues}


def test_isolated_objects_have_silent_evidence_instead_of_visible_samples():
    log = log_of((("e", "A", ("i1",)),), (("i1", "item"), ("i2", "item")))
    value = checked(log).value
    assert all(row.histogram == ((1, 1),) for row in visible_rows(value, "A", "item"))
    assert any(
        step.event_id is None and ("item", ("i2",)) in step.binding.objects
        for step in value.discovery.fitting_witness
    )


def test_no_observation_is_unknown_and_zero_weight_observation_is_not_unknown():
    empty = SAWArcWeightDistribution(
        "p", "t", "t", "item", "silent_witness_steps", (), 0, ()
    )
    zero = SAWArcWeightDistribution(
        "p", "t", "t", "item", "activity_events", ((0, 1),), 1, (0,)
    )
    assert empty.support == ()
    assert empty.probability(0) is empty.expected_weight is None
    assert zero.probability(0) == 1 and zero.expected_weight == 0


def test_exhaustive_small_populations_match_raw_unique_e2o_count_oracle():
    # 27 independently hand-enumerable cases; each event has 0, 1, or 2 objects.
    for cardinalities in product(range(3), repeat=3):
        rows, objects = [], []
        for index, count in enumerate(cardinalities):
            ids = tuple(f"i{index}_{j}" for j in range(count))
            objects.extend((oid, "item") for oid in ids)
            rows.append((f"e{index}", "A", ids))
        if not objects:
            objects.append(("isolated", "item"))
        value = checked(log_of(rows, objects)).value
        expected = tuple(sorted(Counter(cardinalities).items()))
        distributions = visible_rows(value, "A", "item")
        if any(cardinalities):
            assert distributions
            assert all(
                row.histogram == expected and row.sample_count == 3
                for row in distributions
            )
        else:
            assert not distributions
            assert value.discovery.cardinality_profiles[0].histogram == ((0, 3),)


def test_identity_context_input_and_immutability():
    log = log_of((("e", "A", ("i1",)),), (("i1", "item"),))
    first = checked(log)
    second = discover_saw_net(ComputationContext(log), request())
    assert first == second
    assert len(first.parent_computation_ids) == 1
    with pytest.raises(FrozenInstanceError):
        first.value.profile = "pm4py.classic"
    with pytest.raises(ValueError, match="only"):
        replace(request(), profile="pm4py.classic")
    assert first.value.profile == PROFILE


def test_unavailable_parent_and_invalid_input_do_not_create_partial_distributions():
    invalid = discover_saw_net(object(), request())
    assert invalid.status is ComputeStatus.INVALID_INPUT and invalid.value is None
    log = log_of((("e", "A", ("i1",)),), (("i1", "item"),))
    result = discover_saw_net(log, request(("missing",)))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "saw_fitting_not_established" in {issue.code for issue in result.issues}
    assert "unknown_object_type" in {issue.code for issue in result.issues}
    tied = log_of((("e1", "A", ("i1",)), ("e2", "B", ("i1",))), (("i1", "item"),))
    tied = replace(
        tied, events=(tied.events[0], replace(tied.events[1], time=tied.events[0].time))
    )
    assert discover_saw_net(tied, request()).status is ComputeStatus.UNAVAILABLE
    checked(tied, request(tie_policy="event_id"))


@pytest.mark.parametrize(
    "change",
    [
        {"sample_count": 2},
        {"histogram": ((1, 0),)},
        {"histogram": ((True, 1),)},
        {"histogram": ((1, 1), (1, 1)), "sample_count": 2, "witness_indices": (0, 1)},
        {"witness_indices": (True,)},
        {"sample_basis": "nearby_event"},
    ],
)
def test_distribution_contract_rejects_invalid_counts_and_basis(change):
    base = SAWArcWeightDistribution(
        "p", "t", "t", "item", "activity_events", ((1, 1),), 1, (0,)
    )
    with pytest.raises((TypeError, ValueError)):
        replace(base, **change)


def test_payload_rejects_correctly_normalized_but_forged_arc_histogram():
    value = checked(log_of((("e", "A", ("i1",)),), (("i1", "item"),))).value
    forged = replace(value.arc_distributions[0], histogram=((5, 1),))
    with pytest.raises(ValueError, match="witness evidence"):
        replace(value, arc_distributions=(forged, *value.arc_distributions[1:]))
    with pytest.raises(ValueError, match="witness evidence"):
        replace(value, arc_distributions=value.arc_distributions[:-1])
    with pytest.raises(ValueError, match="joint_probability_policy"):
        replace(value, joint_probability_policy="independent")


def test_result_round_trip_preserves_nested_request_and_finite_certificate():
    from pix import results

    result = checked(log_of((("e", "A", ("i1",)),), (("i1", "item"),)))
    with patch.object(results, "_schemas", return_value=RESULT_SCHEMAS):
        restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result
    assert restored.value.arc_distributions[0].probability(1) == 1
