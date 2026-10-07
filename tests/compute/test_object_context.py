"""Domain counterexamples and an independent finite-state metric oracle."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import permutations

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


def _log(rows, objects=(("o1", "item"),), *, simultaneous=False):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OCEL(
        event_types=tuple(
            EventType(activity)
            for activity in sorted({activity for _, activity, _ in rows})
        ),
        object_types=tuple(
            ObjectType(kind) for kind in sorted({kind for _, kind in objects})
        ),
        objects=tuple(Object(oid, kind) for oid, kind in objects),
        events=tuple(
            Event(eid, activity, base + timedelta(seconds=0 if simultaneous else index))
            for index, (eid, activity, _) in enumerate(rows)
        ),
        e2o=tuple(E2O(eid, oid, "") for eid, _, ids in rows for oid in ids),
    )


def _net(edges, *, initial="p0", final="p2", objects=(("o1", "item"),)):
    """One-token state machine; activity may be None for silent."""
    places = {initial, final} | {
        place for _, _, source, target in edges for place in (source, target)
    }
    return ObjectCentricPetriNet(
        tuple(TypedPlace(place, "item") for place in places),
        tuple(Transition(tid, activity) for tid, activity, _, _ in edges),
        tuple(
            arc
            for tid, _, source, target in edges
            for arc in (ObjectArc(source, tid), ObjectArc(tid, target))
        ),
        ObjectMarking(tuple(ObjectToken(initial, oid) for oid, _ in objects)),
        ObjectMarking(tuple(ObjectToken(final, oid) for oid, _ in objects)),
        objects,
    )


def _evaluate(rows, edges, **parameters):
    return measure_object_context(
        _log(rows), _net(edges), ObjectContextSpec(("item",), **parameters)
    )


def test_exact_sequence_and_digest_provenance():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (("a", "A", "p0", "p1"), ("b", "B", "p1", "p2")),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.full_scope_fitness_ratio == (2, 2)
    assert result.value.full_scope_precision_ratio == (2, 2)
    assert result.value.coverage.requested_contexts == 2
    assert result.value.coverage.enumerated_log_states == 3
    assert result.value.coverage.terminal_prefix_count == 1
    assert result.source_digest and result.computation_id
    assert result.spec.model_digest == result.value.model_digest
    assert result.parent_computation_ids == ()


def test_extra_enabled_behavior_reduces_precision_only():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (("a", "A", "p0", "p1"), ("x", "X", "p0", "p0"), ("b", "B", "p1", "p2")),
    )
    assert result.value.full_scope_fitness_ratio == (2, 2)
    assert result.value.full_scope_precision_ratio == (2, 3)


def test_nonfitting_prefix_has_zero_fitness_and_no_invented_marking():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (("b", "B", "p0", "p1"), ("a", "A", "p1", "p2")),
    )
    assert result.value.full_scope_fitness_ratio == (0, 2)
    assert result.value.full_scope_precision_ratio == (0, 1)
    assert result.value.contexts[1].model_behaviors == ()
    assert result.value.contexts[1].precision_ratio is None


def test_all_nonfit_and_no_model_behavior_has_unavailable_precision():
    result = _evaluate((("e1", "A", ("o1",)),), ())
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.full_scope_fitness_ratio == (0, 1)
    assert result.value.full_scope_precision_ratio is None


def test_all_fitting_markings_and_duplicate_labels_are_preserved():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (
            ("a1", "A", "p0", "p1"),
            ("a2", "A", "p0", "p3"),
            ("b", "B", "p1", "p2"),
            ("c", "C", "p3", "p2"),
        ),
    )
    assert result.value.contexts[1].reachable_model_states == 2
    assert result.value.full_scope_fitness_ratio == (2, 2)
    assert result.value.full_scope_precision_ratio == (2, 3)


def test_silent_closure_before_and_after_visible_prefix():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (
            ("tau0", None, "p0", "p3"),
            ("a", "A", "p3", "p1"),
            ("tau1", None, "p1", "p4"),
            ("b", "B", "p4", "p2"),
        ),
    )
    assert result.value.full_scope_fitness_ratio == (2, 2)
    assert result.value.full_scope_precision_ratio == (2, 2)
    assert [row.reachable_model_states for row in result.value.contexts] == [2, 2]


def test_silent_cycle_terminates_on_exact_marking_equality():
    result = _evaluate(
        (("e1", "A", ("o1",)),),
        (
            ("tau0", None, "p0", "p1"),
            ("tau1", None, "p1", "p0"),
            ("a", "A", "p1", "p2"),
        ),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.contexts[0].reachable_model_states == 2


def test_independent_events_all_downsets_but_no_linearization_weight():
    objects = (("o1", "item"), ("o2", "item"))
    log = _log((("e1", "A", ("o1",)), ("e2", "A", ("o2",))), objects, simultaneous=True)
    result = measure_object_context(
        log,
        _net((("a", "A", "p0", "p2"),), objects=objects),
        ObjectContextSpec(("item",)),
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.coverage.enumerated_log_states == 4
    assert result.value.coverage.requested_contexts == 3
    assert result.value.full_scope_fitness_ratio == (4, 4)
    assert result.value.full_scope_precision_ratio == (4, 4)
    assert len({row.context_id for row in result.value.contexts}) == 3
    assert all(len(row.histories) == 2 for row in result.value.contexts)


def test_shared_event_and_exact_binding_count_once():
    objects = (("o1", "item"), ("o2", "item"))
    log = _log((("e1", "A", ("o1", "o2")),), objects)
    net = _net((("a", "A", "p0", "p2"),), objects=objects)
    net = replace(
        net,
        arcs=tuple(ObjectArc(arc.source, arc.target, True, 1, 2) for arc in net.arcs),
    )
    result = measure_object_context(log, net, ObjectContextSpec(("item",)))
    assert result.value.full_scope_fitness_ratio == (1, 1)
    assert result.value.full_scope_precision_ratio == (1, 3)
    assert len(result.value.contexts[0].observed_behaviors) == 1
    assert len(result.value.contexts[0].model_behaviors) == 3


def test_jointly_inconsistent_objects_do_not_pass_label_only_comparison():
    objects = (("o1", "item"), ("o2", "item"))
    log = _log((("e1", "A", ("o1", "o2")),), objects)
    net = _net((("a", "A", "p0", "p2"),), objects=objects)
    result = measure_object_context(log, net, ObjectContextSpec(("item",)))
    assert result.value.full_scope_fitness_ratio == (0, 1)
    assert result.value.full_scope_precision_ratio == (0, 2)


def test_joint_input_places_require_the_same_actual_object_not_token_counts():
    objects = (("o1", "item"), ("o2", "item"))
    log = _log((("e1", "A", ("o1",)),), objects)
    net = ObjectCentricPetriNet(
        (TypedPlace("left", "item"), TypedPlace("right", "item")),
        (Transition("a", "A"),),
        (ObjectArc("left", "a"), ObjectArc("right", "a")),
        ObjectMarking((ObjectToken("left", "o1"), ObjectToken("right", "o2"))),
        ObjectMarking(),
        objects,
    )
    result = measure_object_context(log, net, ObjectContextSpec(("item",)))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.full_scope_fitness_ratio == (0, 1)
    assert result.value.full_scope_precision_ratio is None
    assert result.value.contexts[0].model_behaviors == ()


def test_optional_empty_type_binding_group_matches_observed_nonempty_participants():
    log = _log((("e1", "A", ("o1",)),))
    log = replace(log, object_types=log.object_types + (ObjectType("optional"),))
    net = _net((("a", "A", "p0", "p2"),))
    net = replace(
        net,
        places=net.places + (TypedPlace("optional-place", "optional"),),
        arcs=net.arcs + (ObjectArc("a", "optional-place", True, 0, 1),),
    )
    result = measure_object_context(log, net, ObjectContextSpec(("item", "optional")))
    assert result.value.full_scope_fitness_ratio == (1, 1)
    assert result.value.full_scope_precision_ratio == (1, 1)
    assert result.value.contexts[0].model_behaviors[0].objects == (("item", ("o1",)),)


def test_terminal_model_behavior_and_final_marking_not_scored():
    result = _evaluate(
        (("e1", "A", ("o1",)),), (("a", "A", "p0", "p1"), ("x", "X", "p1", "p2"))
    )
    assert result.value.full_scope_fitness_ratio == (1, 1)
    assert result.value.full_scope_precision_ratio == (1, 1)
    assert result.spec.parameters.termination == "excluded"


def test_no_participant_event_and_model_behavior_same_scope_exclusion():
    log = _log((("e0", "X", ()), ("e1", "A", ("o1",))))
    net = _net((("a", "A", "p0", "p2"),))
    net = replace(net, transitions=net.transitions + (Transition("x", "X"),))
    result = measure_object_context(log, net, ObjectContextSpec(("item",)))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.coverage.excluded_event_ids == ("e0",)
    assert result.value.full_scope_precision_ratio == (1, 1)
    assert len(result.value.contexts[0].model_behaviors) == 1
    assert "context_events_outside_participant_scope" in {
        issue.code for issue in result.issues
    }


def test_empty_population_has_no_fabricated_zero_or_one():
    result = measure_object_context(_log(()), _net(()), ObjectContextSpec(("item",)))
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.full_scope_fitness_ratio is None
    assert result.value.full_scope_precision_ratio is None
    assert result.value.coverage.requested_contexts == 0
    assert result.value.coverage.terminal_prefix_count == 1


def test_isolated_objects_part_of_context_and_model_scope():
    objects = (("o1", "item"), ("o2", "item"))
    log = _log((("e1", "A", ("o1",)),), objects)
    result = measure_object_context(
        log,
        _net((("a", "A", "p0", "p2"),), objects=objects),
        ObjectContextSpec(("item",)),
    )
    assert len(result.value.contexts[0].histories) == 2
    assert result.value.full_scope_precision_ratio == (1, 2)


def test_wrong_model_universe_is_unavailable():
    log = _log((("e1", "A", ("o1",)),))
    net = _net((("a", "A", "p0", "p2"),), objects=(("other", "item"),))
    result = measure_object_context(log, net, ObjectContextSpec(("item",)))
    assert result.status is ComputeStatus.UNAVAILABLE
    assert result.value is None


def test_same_object_timestamp_ties_need_explicit_policy():
    log = _log((("e1", "A", ("o1",)), ("e2", "B", ("o1",))), simultaneous=True)
    net = _net((("a", "A", "p0", "p1"), ("b", "B", "p1", "p2")))
    assert (
        measure_object_context(log, net, ObjectContextSpec(("item",))).status
        is ComputeStatus.UNAVAILABLE
    )
    result = measure_object_context(
        log, net, ObjectContextSpec(("item",), tie_policy="event_id")
    )
    assert result.value.full_scope_fitness_ratio == (2, 2)


def test_qualifier_projection_retains_selected_object_universe():
    log = _log((("e1", "A", ("o1",)), ("e2", "B", ("o1",))))
    log = replace(log, e2o=(E2O("e1", "o1", "selected"), E2O("e2", "o1", "excluded")))
    result = measure_object_context(
        log,
        _net((("a", "A", "p0", "p2"),)),
        ObjectContextSpec(("item",), qualifiers=("selected",)),
    )
    assert result.value.coverage.excluded_event_ids == ("e2",)
    assert result.value.coverage.excluded_relation_count == 1
    assert result.value.full_scope_fitness_ratio == (1, 1)


def test_duplicate_qualifiers_do_not_duplicate_participants():
    log = _log((("e1", "A", ("o1",)),))
    log = replace(log, e2o=log.e2o + (E2O("e1", "o1", "other"),))
    result = measure_object_context(
        log, _net((("a", "A", "p0", "p2"),)), ObjectContextSpec(("item",))
    )
    assert result.value.full_scope_fitness_ratio == (1, 1)


def test_log_limit_reports_unknown_population_not_zero_missing_contexts():
    result = _evaluate(
        (("e1", "A", ("o1",)), ("e2", "B", ("o1",))),
        (("a", "A", "p0", "p1"), ("b", "B", "p1", "p2")),
        max_log_states=1,
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.coverage.requested_contexts is None
    assert result.value.coverage.completed_contexts == 0
    assert result.value.full_scope_fitness_ratio is None
    assert result.value.full_scope_precision_ratio is None


def test_binding_limit_cannot_publish_partial_behavior_set_as_score():
    result = _evaluate(
        (("e1", "A", ("o1",)),),
        (("a", "A", "p0", "p2"), ("x", "X", "p0", "p2")),
        max_bindings=1,
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.contexts[0].enabled_binding_candidate_count == 2
    assert result.value.full_scope_precision_ratio is None
    assert result.value.contexts[0].precision_ratio is None
    assert "binding_limit" in result.value.contexts[0].limit_reasons


def test_context_limit_taints_descendants_but_retains_completed_ancestors():
    rows = (("e1", "A", ("o1",)), ("e2", "B", ("o1",)), ("e3", "C", ("o1",)))
    edges = (
        ("a", "A", "p0", "p1"),
        ("b", "B", "p1", "p3"),
        ("c", "C", "p3", "p2"),
        ("tau", None, "p1", "p1"),
    )
    net = _net(edges)
    net = replace(
        net,
        places=net.places + (TypedPlace("growth", "item"),),
        arcs=net.arcs + (ObjectArc("tau", "growth"),),
    )
    result = measure_object_context(
        _log(rows), net, ObjectContextSpec(("item",), max_context_states=1)
    )
    assert result.status is ComputeStatus.PARTIAL
    assert result.value.coverage.completed_contexts == 1
    assert result.value.complete_context_fitness_ratio == (1, 1)
    assert result.value.full_scope_fitness_ratio is None
    assert "context_state_limit" in result.value.contexts[1].limit_reasons
    assert "ancestor_context_incomplete" in result.value.contexts[2].limit_reasons


def test_invalid_input_preserves_original_issue():
    result = measure_object_context("wrong", _net(()), ObjectContextSpec(("item",)))
    assert result.status is ComputeStatus.INVALID_INPUT
    assert result.issues[0].code == "invalid_log_type"


@pytest.mark.parametrize(
    "parameters",
    [
        {"object_types": ()},
        {"object_types": ["item"]},
        {"max_log_states": 0},
        {"max_context_states": True},
        {"max_bindings": -1},
        {"weighting": "event_mean"},
        {"termination": "include"},
        {"tie_policy": "arbitrary"},
        {"scope": "whole_log"},
        {"participant_policy": "all"},
        {"profile": "ocpa"},
        {"qualifiers": "x"},
    ],
)
def test_parameters_do_not_accept_implicit_semantic_substitutions(parameters):
    with pytest.raises((TypeError, ValueError)):
        ObjectContextSpec(**({"object_types": ("item",)} | parameters))


def _independent_oracle(rows, edges, object_ids):
    """Enumerate all topological permutations and state-machine transitions.

    No production downset, binding, firing, or context helper is used. A state
    machine location per object independently describes this bounded net class.
    """
    before = {
        (i, j)
        for i in range(len(rows))
        for j in range(i + 1, len(rows))
        if set(rows[i][2]) & set(rows[j][2])
    }
    observations = {}
    states = {}

    def closure(markings):
        markings = set(markings)
        todo = list(markings)
        while todo:
            marking = todo.pop()
            for position in range(len(object_ids)):
                for _, activity, source, target in edges:
                    if activity is None and marking[position] == source:
                        following = (
                            marking[:position] + (target,) + marking[position + 1 :]
                        )
                        if following not in markings:
                            markings.add(following)
                            todo.append(following)
        return markings

    for order in permutations(range(len(rows))):
        positions = {index: position for position, index in enumerate(order)}
        if any(positions[left] > positions[right] for left, right in before):
            continue
        prefix = frozenset()
        reachable = closure({("p0",) * len(object_ids)})
        for index in order:
            _, activity, ids = rows[index]
            observations.setdefault(prefix, set()).add((activity, tuple(ids)))
            states.setdefault(prefix, set()).update(reachable)
            following = set()
            if len(ids) == 1:
                position = object_ids.index(ids[0])
                for marking in reachable:
                    for _, label, source, target in edges:
                        if label == activity and marking[position] == source:
                            following.add(
                                marking[:position] + (target,) + marking[position + 1 :]
                            )
            reachable = closure(following)
            prefix = prefix | {index}
    intersection = log_count = model_count = 0
    for prefix, observed in observations.items():
        modeled = {
            (activity, (object_ids[position],))
            for marking in states[prefix]
            for position in range(len(object_ids))
            for _, activity, source, _ in edges
            if activity is not None and marking[position] == source
        }
        intersection += len(observed & modeled)
        log_count += len(observed)
        model_count += len(modeled)
    return (intersection, log_count), (
        intersection,
        model_count,
    ) if model_count else None


@pytest.mark.parametrize("seed", range(30))
def test_small_finite_models_against_independent_linearization_oracle(seed):
    import random

    randomizer = random.Random(seed)
    object_ids = ("o1", "o2")
    objects = tuple((oid, "item") for oid in object_ids)
    rows = tuple(
        (f"e{index}", randomizer.choice(("A", "B")), (randomizer.choice(object_ids),))
        for index in range(4)
    )
    edges = tuple(
        (
            f"t{index}",
            randomizer.choice(("A", "B", "X", None)),
            randomizer.choice(("p0", "p1", "p2")),
            randomizer.choice(("p0", "p1", "p2")),
        )
        for index in range(5)
    )
    expected_fit, expected_precision = _independent_oracle(rows, edges, object_ids)
    result = measure_object_context(
        _log(rows, objects), _net(edges, objects=objects), ObjectContextSpec(("item",))
    )
    assert result.status is ComputeStatus.COMPUTED
    assert result.value.full_scope_fitness_ratio == expected_fit
    assert result.value.full_scope_precision_ratio == expected_precision


def test_result_codec_round_trip_preserves_detailed_scope_and_evidence():
    from pix.results import result_from_json, result_json_bytes

    result = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),))
    assert result_from_json(result_json_bytes(result)) == result


@pytest.mark.parametrize(
    "field", ("full_scope_fitness_ratio", "full_scope_precision_ratio")
)
def test_partial_metric_contract_cannot_claim_a_full_scope_score(field):
    result = _evaluate(
        (("e1", "A", ("o1",)),),
        (("a", "A", "p0", "p2"), ("x", "X", "p0", "p2")),
        max_bindings=1,
    )
    assert result.status is ComputeStatus.PARTIAL
    with pytest.raises(ValueError, match="full-scope"):
        replace(result.value, **{field: (1, 1)})


@pytest.mark.parametrize(
    "field", ("full_scope_fitness_ratio", "full_scope_precision_ratio")
)
def test_redigested_partial_metric_json_cannot_claim_a_full_scope_score(field):
    import json
    from hashlib import sha256

    from pix.results import result_document, result_from_json

    result = _evaluate(
        (("e1", "A", ("o1",)),),
        (("a", "A", "p0", "p2"), ("x", "X", "p0", "p2")),
        max_bindings=1,
    )
    document = result_document(result)
    document["computation"]["value"][field] = [1, 1]
    body = {key: value for key, value in document.items() if key != "document_digest"}
    encoded = json.dumps(
        body, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode()
    document["document_digest"] = (
        "pix.analysis-result.v1:sha256:" + sha256(encoded).hexdigest()
    )
    with pytest.raises(ValueError):
        result_from_json(json.dumps(document))


@pytest.mark.parametrize(
    "changes",
    (
        {"source_event_count": -1},
        {"selected_event_count": True},
        {"excluded_event_ids": ("e0",)},
        {"excluded_event_ids": ("e0", "e0"), "source_event_count": 3},
        {"completed_contexts": 0},
        {"enumerated_log_states": 3},
        {"requested_contexts": None},
        {"log_enumeration_complete": False},
    ),
)
def test_coverage_rejects_negative_unknown_or_unbalanced_population(changes):
    result = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),))
    with pytest.raises((ValueError, TypeError)):
        replace(result.value.coverage, **changes)


@pytest.mark.parametrize(
    "changes",
    (
        {"fitness_ratio": (0, 1)},
        {"precision_ratio": (1, 2)},
        {"matching_behaviors": ()},
        {"complete": False},
        {"limit_reasons": ("binding_limit",)},
        {"reachable_model_states": 0},
        {"enabled_binding_candidate_count": 0},
        {"consumed_event_ids": ("e1",)},
    ),
)
def test_context_contract_rejects_scores_inconsistent_with_evidence(changes):
    result = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),))
    with pytest.raises((ValueError, TypeError)):
        replace(result.value.contexts[0], **changes)


@pytest.mark.parametrize(
    "changes",
    (
        {"complete_context_intersection_count": 0},
        {"complete_context_observed_count": 2},
        {"complete_context_model_count": -1},
        {"complete_context_fitness_ratio": (2, 2)},
        {"complete_context_precision_ratio": None},
        {"contexts": ()},
        {"selected_objects": (("other", "item"),)},
    ),
)
def test_metric_contract_rejects_aggregate_counts_disagreeing_with_contexts(changes):
    result = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),))
    with pytest.raises((ValueError, TypeError)):
        replace(result.value, **changes)


def test_valid_partial_diagnostics_and_empty_denominators_still_round_trip():
    from pix.results import result_from_json, result_json_bytes

    results = (
        _evaluate(
            (("e1", "A", ("o1",)),),
            (("a", "A", "p0", "p2"), ("x", "X", "p0", "p2")),
            max_bindings=1,
        ),
        _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),), max_log_states=1),
        _evaluate((), ()),
        _evaluate((("e1", "A", ("o1",)),), ()),
    )
    for result in results:
        assert result_from_json(result_json_bytes(result)) == result


def test_behavior_participant_order_cannot_duplicate_semantic_behavior():
    from pix.contracts.object_context import ObjectContextBehavior

    canonical = ObjectContextBehavior("A", (("X", ("x1", "x2")), ("Y", ("y",))))
    reordered = ObjectContextBehavior("A", (("Y", ("y",)), ("X", ("x2", "x1"))))
    assert reordered == canonical
    row = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),)).value.contexts[
        0
    ]
    with pytest.raises(ValueError, match="duplicates"):
        replace(row, model_behaviors=(canonical, reordered))


def test_distinct_context_labels_cannot_duplicate_the_same_observed_downset():
    value = _evaluate((("e1", "A", ("o1",)),), (("a", "A", "p0", "p2"),)).value
    row = value.contexts[0]
    duplicate = replace(row, context_id="different display identifier")
    coverage = replace(
        value.coverage,
        requested_contexts=2,
        enumerated_contexts=2,
        completed_contexts=2,
        enumerated_log_states=3,
    )
    with pytest.raises(ValueError, match="downset"):
        replace(
            value,
            contexts=(row, duplicate),
            coverage=coverage,
            complete_context_intersection_count=2,
            complete_context_observed_count=2,
            complete_context_model_count=2,
            complete_context_fitness_ratio=(2, 2),
            complete_context_precision_ratio=(2, 2),
            full_scope_fitness_ratio=(2, 2),
            full_scope_precision_ratio=(2, 2),
        )
