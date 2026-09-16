"""Native selectable miners: hand-counted objects and independent firing checks."""

from collections import Counter, deque
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from itertools import product
from unittest.mock import patch

import pytest

from pix.case_centric.alpha import AlphaSpec
from pix.case_centric.discovery import RelationDiscoverySpec
from pix.case_centric.inductive import InductiveSpec
from pix.compute.context import ComputationContext
from pix.contracts.case_log import CaseTraceSpec
from pix.contracts.discovery import ProcessTree
from pix.contracts.result import ComputeStatus
from pix.object_centric.legacy_discovery import (
    RESULT_SCHEMAS,
    OCPNByTypeDiscoverySpec,
    discover_ocpn_by_type,
)
from pix.ocel import E2O, OCEL, Event, EventType, Object, ObjectType


def log_of(rows, objects):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(EventType(a) for a in sorted({row[1] for row in rows})),
        object_types=tuple(
            ObjectType(kind) for kind in sorted({k for _, k in objects})
        ),
        events=tuple(
            Event(eid, act, origin + timedelta(seconds=i))
            for i, (eid, act, _) in enumerate(rows)
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects),
        e2o=tuple(E2O(eid, oid, "flow") for eid, _, ids in rows for oid in ids),
    )


def request(algorithm="im", types=("item",), **kwargs):
    return OCPNByTypeDiscoverySpec(
        types, "observed_range", "unique_activity", algorithm, **kwargs
    )


def checked(log, spec):
    result = discover_ocpn_by_type(log, spec)
    assert result.status is ComputeStatus.COMPUTED, result.issues
    value = result.value
    model = value.model
    # Independent multiset interpreter: do not call native enabled/fire helpers.
    marking = Counter((t.place_id, t.object_id) for t in model.initial_marking.tokens)
    kinds = {p.id: p.object_type for p in model.places}
    activities = {t.id: t.activity for t in model.transitions}
    observed = []
    for step in value.fitting_witness:
        binding = dict(step.binding.objects)
        consume, produce = Counter(), Counter()
        for arc in model.arcs:
            if arc.target == step.binding.transition_id:
                ids = binding[kinds[arc.source]]
                assert arc.min_objects <= len(ids) <= arc.max_objects
                consume.update((arc.source, oid) for oid in ids)
            elif arc.source == step.binding.transition_id:
                ids = binding[kinds[arc.target]]
                assert arc.min_objects <= len(ids) <= arc.max_objects
                produce.update((arc.target, oid) for oid in ids)
        assert all(marking[token] >= n for token, n in consume.items())
        marking.subtract(consume)
        marking.update(produce)
        marking = +marking
        if step.event_id is not None:
            observed.append(step.event_id)
            source = next(e for e in log.events if e.id == step.event_id)
            assert activities[step.binding.transition_id] == source.type
            allowed = spec.qualifiers
            expected = {
                r.object
                for r in log.e2o
                if r.event == source.id and (allowed is None or r.qualifier in allowed)
            }
            expected &= {oid for oid, _ in model.objects}
            assert {oid for ids in binding.values() for oid in ids} == expected
    assert marking == Counter(
        (t.place_id, t.object_id) for t in model.final_marking.tokens
    )
    assert observed == [e.id for e in sorted(log.events, key=lambda e: (e.time, e.id))]
    return result


@pytest.mark.parametrize("algorithm", ("alpha", "im", "dfg"))
def test_shared_visible_activity_and_typed_places(algorithm):
    log = log_of(
        (("e1", "A", ("i1", "o1")), ("e2", "B", ("i1", "o1"))),
        (("i1", "item"), ("o1", "order")),
    )
    result = checked(log, request(algorithm, ("order", "item")))
    model = result.value.model
    assert sorted(t.activity for t in model.transitions if t.activity is not None) == [
        "A",
        "B",
    ]
    assert {p.object_type for p in model.places} == {"item", "order"}
    assert (
        len(
            [
                s
                for s in result.value.transition_sources
                if s.merged_transition_id == "activity0"
            ]
        )
        == 2
    )
    assert all(p.histogram == ((1, 1),) for p in result.value.cardinality_profiles)


def test_mixed_per_type_kernels_have_distinct_parent_identities():
    log = log_of(
        (("e1", "A", ("i1", "o1", "r1")), ("e2", "B", ("i1", "o1", "r1"))),
        (("i1", "item"), ("o1", "order"), ("r1", "request")),
    )
    spec = request(
        "im",
        ("item", "order", "request"),
        type_algorithms=(("order", "alpha"), ("item", "dfg")),
    )
    result = checked(log, spec)
    assert len(result.parent_computation_ids) == 6
    assert len({p.model_digest for p in result.value.projections}) == 3
    assert len({p.discovery_computation_id for p in result.value.projections}) == 3
    codes = [i.message for i in result.issues if i.code == "local_discovery_profile"]
    assert {message.split()[0] for message in codes} == {"alpha", "im", "dfg"}


@pytest.mark.parametrize("algorithm", ("alpha", "im", "dfg"))
def test_histogram_zero_one_three_qualifier_deduplication_and_orphans(algorithm):
    log = log_of(
        (
            ("e1", "A", ("i1",)),
            ("e2", "A", ("i2", "i3", "i4")),
            ("e3", "A", ()),
            ("e4", "Orphan", ()),
        ),
        tuple((f"i{i}", "item") for i in range(1, 5)),
    )
    log = replace(log, e2o=(*log.e2o, E2O("e1", "i1", "other")))
    result = checked(log, request(algorithm))
    profiles = {p.activity: p for p in result.value.cardinality_profiles}
    assert profiles["A"].histogram == ((0, 1), (1, 1), (3, 1))
    assert profiles["A"].arc_kind == "variable"
    assert profiles["Orphan"].histogram == ((0, 1),)
    assert result.value.observed_event_bindings[-1].binding.objects == ()
    assert {
        "zero_participation_events",
        "zero_incidence_activities",
        "cardinality_interval_generalization",
    } <= {i.code for i in result.issues}


@pytest.mark.parametrize("algorithm", ("im", "dfg"))
def test_isolated_objects_and_empty_event_population_accept_silent_run(algorithm):
    log = log_of((), (("i1", "item"), ("i2", "item")))
    result = checked(log, request(algorithm))
    assert result.value.projections[0].isolated_object_ids == ("i1", "i2")
    assert result.value.observed_event_bindings == ()
    assert len(result.value.fitting_witness) == 2


def test_alpha_empty_trace_rejection_is_not_replaced_by_another_miner():
    log = log_of((("e1", "A", ("i1",)),), (("i1", "item"), ("i2", "item")))
    result = discover_ocpn_by_type(log, request("alpha"))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "local_discovery_not_computed" in {i.code for i in result.issues}
    checked(log, request("dfg"))


def test_alpha_short_loop_nonfit_is_not_reported_as_a_fitting_net():
    log = log_of((("e1", "A", ("i1",)), ("e2", "A", ("i1",))), (("i1", "item"),))
    result = discover_ocpn_by_type(log, request("alpha"))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "local_trace_not_fitting" in {i.code for i in result.issues}
    checked(log, request("dfg"))


@pytest.mark.parametrize("algorithm", ("alpha", "im", "dfg"))
def test_split_and_join_with_zero_participation_of_one_type(algorithm):
    log = log_of(
        (
            ("e1", "A", ("i1", "i2", "o1")),
            ("e2", "B", ("i1", "o1")),
            ("e3", "B", ("i2",)),
            ("e4", "C", ("i1", "i2", "o1")),
        ),
        (("i1", "item"), ("i2", "item"), ("o1", "order")),
    )
    result = checked(log, request(algorithm, ("item", "order")))
    rows = {(p.activity, p.object_type): p for p in result.value.cardinality_profiles}
    assert rows["A", "item"].histogram == ((2, 1),)
    assert rows["B", "order"].histogram == ((0, 1), (1, 1))
    assert rows["C", "item"].histogram == ((2, 1),)


def test_alpha_parallel_branches_are_a_real_alpha_net():
    rows = tuple(
        (f"{oid}-{i}", a, (oid,))
        for oid, word in (("i1", "ABCD"), ("i2", "ACBD"))
        for i, a in enumerate(word)
    )
    log = log_of(rows, (("i1", "item"), ("i2", "item")))
    model = checked(log, request("alpha")).value.model
    start = next(t.id for t in model.transitions if t.activity == "A")
    join = next(t.id for t in model.transitions if t.activity == "D")
    assert len([a for a in model.arcs if a.source == start]) == 2
    assert len([a for a in model.arcs if a.target == join]) == 2
    assert len(model.transitions) == 4


def test_ambiguous_local_labels_are_not_merged_into_a_different_language(monkeypatch):
    import pix.object_centric.legacy_discovery as module

    original = module.discover_inductive

    def duplicate_local_model(traces, spec):
        discovered = original(traces, spec)
        # The accepting sequence A,A has two visible transition identities.
        # Merging them creates a different, generally disabled net.
        tree = ProcessTree(
            "sequence",
            children=(ProcessTree("activity", "A"), ProcessTree("activity", "A")),
        )
        return replace(discovered, value=tree)

    monkeypatch.setattr(module, "discover_inductive", duplicate_local_model)
    log = log_of((("e1", "A", ("i1",)), ("e2", "A", ("i1",))), (("i1", "item"),))
    result = discover_ocpn_by_type(log, request("im"))
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert result.issues[-1].code == "ambiguous_activity_merge"


@pytest.mark.parametrize("algorithm", ("alpha", "im", "dfg"))
def test_state_limit_is_unknown_and_can_be_resolved_with_more_budget(algorithm):
    log = log_of((("e1", "A", ("i1",)), ("e2", "B", ("i1",))), (("i1", "item"),))
    result = discover_ocpn_by_type(
        log, request(algorithm, max_fitting_states_per_object=1)
    )
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert "fitting_search_unknown" in {i.code for i in result.issues}
    assert "local_trace_not_fitting" not in {i.code for i in result.issues}
    checked(log, request(algorithm, max_fitting_states_per_object=100))


def test_partial_dfg_cannot_produce_a_complete_ocpn():
    log = log_of(
        (("e1", "A", ("i1",)), ("e2", "B", ("i1",)), ("e3", "C", ("i1",))),
        (("i1", "item"),),
    )
    result = discover_ocpn_by_type(
        log, request("dfg", dfg_spec=RelationDiscoverySpec(max_event_pairs=1))
    )
    assert result.status is ComputeStatus.UNAVAILABLE and result.value is None
    assert {"event_pair_limit", "local_discovery_not_computed"} <= {
        i.code for i in result.issues
    }


def test_ordering_ties_require_explicit_policy():
    log = log_of((("e1", "A", ("i1",)), ("e2", "B", ("i1",))), (("i1", "item"),))
    log = replace(
        log, events=(log.events[0], replace(log.events[1], time=log.events[0].time))
    )
    result = discover_ocpn_by_type(log, request("dfg"))
    assert result.status is ComputeStatus.UNAVAILABLE
    resolved = checked(log, request("dfg", tie_policy="event_id"))
    assert "event_id_tie_break" in {i.code for i in resolved.issues}


def test_qualifier_filter_retains_unselected_events_and_objects_as_isolated():
    log = log_of((("e1", "A", ("i1",)),), (("i1", "item"),))
    result = checked(log, request("dfg", qualifiers=()))
    assert result.value.projections[0].isolated_object_ids == ("i1",)
    assert result.value.observed_event_bindings[0].binding.objects == ()


def test_unknown_and_empty_selected_type_do_not_disappear():
    log = log_of((), (("i1", "item"),))
    result = discover_ocpn_by_type(log, request(types=("missing",)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "unknown_object_type"
    empty = replace(log, object_types=(*log.object_types, ObjectType("empty")))
    result = discover_ocpn_by_type(empty, request(types=("item", "empty")))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.issues[-1].code == "empty_type_population"


def test_context_and_input_permutation_have_stable_result_identity():
    log = log_of((("e1", "A", ("i1",)), ("e2", "B", ("i1",))), (("i1", "item"),))
    first = checked(log, request("dfg"))
    second = discover_ocpn_by_type(ComputationContext(log), request("dfg"))
    permuted = replace(
        log, events=tuple(reversed(log.events)), e2o=tuple(reversed(log.e2o))
    )
    third = checked(permuted, request("dfg"))
    assert first == second == third
    assert first.computation_id != checked(log, request("im")).computation_id


def _accepts_one_object(model, activities):
    """Independent finite-state oracle for the one-token DFG construction."""
    initial = tuple(sorted(t.place_id for t in model.initial_marking.tokens))
    final = tuple(sorted(t.place_id for t in model.final_marking.tokens))
    queue, seen = deque([(0, initial)]), {(0, initial)}
    while queue:
        position, marking = queue.popleft()
        if position == len(activities) and marking == final:
            return True
        for transition in model.transitions:
            nxt = position
            if transition.activity is not None:
                if nxt == len(activities) or activities[nxt] != transition.activity:
                    continue
                nxt += 1
            before = Counter(a.source for a in model.arcs if a.target == transition.id)
            after = Counter(a.target for a in model.arcs if a.source == transition.id)
            current = Counter(marking)
            if any(current[p] < n for p, n in before.items()):
                continue
            successor = (nxt, tuple(sorted((current - before + after).elements())))
            if successor not in seen:
                seen.add(successor)
                queue.append(successor)
    return False


def test_dfg_net_language_matches_graph_paths_including_repetitions():
    # Observed A,B,A,C yields starts={A}, ends={C}, edges={AB,BA,AC}.
    log = log_of(
        tuple((f"e{i}", a, ("i1",)) for i, a in enumerate("ABAC")), (("i1", "item"),)
    )
    model = checked(log, request("dfg")).value.model
    assert len([t for t in model.transitions if t.activity == "A"]) == 1
    for length in range(6):
        for word in product("ABC", repeat=length):
            expected = (
                bool(word)
                and word[0] == "A"
                and word[-1] == "C"
                and all(
                    pair in {("A", "B"), ("B", "A"), ("A", "C")}
                    for pair in zip(word, word[1:])
                )
            )
            assert _accepts_one_object(model, word) == expected, word


@pytest.mark.parametrize(
    "kwargs",
    (
        {"default_algorithm": "fake"},
        {"type_algorithms": (("item", "fake"),)},
        {"type_algorithms": (("missing", "im"),)},
        {"type_algorithms": (("item", "im"), ("item", "dfg"))},
        {"type_algorithms": [("item", "im")]},
        {"type_algorithms": (("item",),)},
        {"alpha_spec": AlphaSpec(variant="plus")},
        {"inductive_spec": InductiveSpec(variant="imf")},
        {
            "inductive_spec": InductiveSpec(
                trace_spec=CaseTraceSpec(activity_key="other")
            )
        },
        {"alpha_spec": None},
        {"inductive_spec": None},
        {"dfg_spec": None},
        {"max_fitting_states_per_object": True},
        {"max_fitting_states_per_object": 0},
    ),
)
def test_invalid_spec_is_rejected(kwargs):
    with pytest.raises((TypeError, ValueError)):
        OCPNByTypeDiscoverySpec(
            ("item",), "observed_range", "unique_activity", **kwargs
        )


def test_immutable_spec_schema_and_invalid_log():
    spec = request("dfg")
    with pytest.raises(FrozenInstanceError):
        spec.default_algorithm = "alpha"
    assert (
        RESULT_SCHEMAS["pix.object_centric.discover_ocpn_by_type"][1]
        is OCPNByTypeDiscoverySpec
    )
    assert discover_ocpn_by_type(None, spec).status is ComputeStatus.INVALID_INPUT
    with pytest.raises(TypeError):
        discover_ocpn_by_type(None, None)


def test_result_round_trip_keeps_nested_kernel_specs_and_checked_witness():
    from pix import results

    log = log_of(
        (("e1", "A", ("i1", "o1")), ("e2", "B", ("i1", "o1"))),
        (("i1", "item"), ("o1", "order")),
    )
    result = checked(
        log, request("dfg", ("item", "order"), type_algorithms=(("order", "alpha"),))
    )
    with patch.object(results, "_schemas", return_value=RESULT_SCHEMAS):
        restored = results.result_from_json(results.result_json_bytes(result))
    assert restored == result
