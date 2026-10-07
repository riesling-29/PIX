from collections import deque

import pytest

from pix.case_centric.alpha import discover_alpha
from pix.case_centric.model_discovery import (
    ModelFootprintSpec,
    discover_model_footprints,
)
from pix.contracts.discovery import ProcessTree
from pix.contracts.models import Arc, Marking, PetriNet, Place, Transition
from pix.contracts.result import ComputeStatus
from pix.event_log.model import CaseAttribute, CaseEvent, CaseLog, CaseTrace


def leaf(a):
    return ProcessTree("activity", a)


def tree(op, *children):
    return ProcessTree(op, children=tuple(children))


def report(model, **kwargs):
    return discover_model_footprints(model, ModelFootprintSpec(**kwargs))


def test_sequence_tree_full_model_properties():
    result = report(tree("sequence", leaf("A"), leaf("B"), leaf("C")))
    model = result.value
    assert result.status == ComputeStatus.COMPUTED
    assert model.complete
    assert model.directly_follows == (("A", "B"), ("B", "C"))
    assert model.sequence == model.directly_follows
    assert model.parallel == model.commuting_pairs == ()
    assert model.start_activities == ("A",)
    assert model.end_activities == ("C",)
    assert model.minimum_trace_length == 3
    assert model.minimum_length_proven
    assert model.accepted_language_exists
    assert model.accepts_empty_trace is False
    assert model.always_activities == ("A", "B", "C")


def test_xor_enabled_competition_is_not_commuting_concurrency():
    model = report(tree("xor", leaf("A"), leaf("B"))).value
    assert model.directly_follows == ()
    assert model.unrelated == (("A", "B"),)
    assert model.commuting_pairs == ()
    assert model.start_activities == model.end_activities == ("A", "B")
    assert model.always_activities == ()


def test_parallel_has_commuting_witness_and_both_adjacencies():
    model = report(tree("parallel", leaf("A"), leaf("B"))).value
    assert model.parallel == (("A", "B"), ("B", "A"))
    assert model.commuting_pairs == (("A", "B"),)
    assert len(model.commuting_witnesses) == 1
    assert model.minimum_trace_length == 2
    assert model.always_activities == ("A", "B")


def test_serial_loop_bidirection_is_not_actual_concurrency():
    model = report(tree("loop", leaf("A"), leaf("B"))).value
    assert model.parallel == (("A", "B"), ("B", "A"))
    assert model.commuting_pairs == ()
    assert model.always_activities == ("A",)
    assert model.start_activities == model.end_activities == ("A",)
    assert model.minimum_trace_length == 1


def test_silent_optional_branch_preserves_minimum_and_mandatory_label():
    model = report(
        tree("sequence", tree("xor", ProcessTree("tau"), leaf("A")), leaf("B"))
    ).value
    assert model.start_activities == ("A", "B")
    assert model.end_activities == ("B",)
    assert model.minimum_trace_length == 1
    assert model.always_activities == ("B",)
    assert model.directly_follows == (("A", "B"),)


def test_duplicate_activity_leaves_keep_concurrent_transition_identity():
    model = report(tree("parallel", leaf("A"), leaf("A"))).value
    assert model.declared_activities == ("A",)
    assert model.self_succession == ("A",)
    assert model.commuting_pairs == (("A", "A"),)
    witness = model.commuting_witnesses[0]
    assert witness.transition_ids[0] != witness.transition_ids[1]
    assert model.minimum_trace_length == 2


def test_tau_only_has_epsilon_and_no_activity():
    model = report(ProcessTree("tau")).value
    assert model.accepts_empty_trace is True
    assert model.minimum_trace_length == 0
    assert model.minimum_length_proven
    assert model.activities == model.always_activities == ()


def dead_branch_net():
    return PetriNet(
        (Place("p"), Place("q"), Place("sink"), Place("dead")),
        (
            Transition("a", "A"),
            Transition("b", "B"),
            Transition("x", "X"),
            Transition("unreachable", "Z"),
        ),
        (
            Arc("p", "a"),
            Arc("a", "q"),
            Arc("q", "b"),
            Arc("b", "sink"),
            Arc("p", "x"),
            Arc("x", "dead"),
            Arc("sink", "unreachable", 2),
            Arc("unreachable", "sink", 2),
        ),
        Marking((("p", 1),)),
        Marking((("sink", 1),)),
    )


def test_reachable_and_accepting_profiles_distinguish_deadlocking_branch():
    net = dead_branch_net()
    prefixes = report(net).value
    accepted = report(net, behavior="accepting").value
    assert prefixes.activities == ("A", "B", "X")
    assert prefixes.inactive_activities == ("Z",)
    assert prefixes.start_activities == ("A", "X")
    assert accepted.activities == ("A", "B")
    assert accepted.inactive_activities == ("X", "Z")
    assert accepted.start_activities == ("A",)
    assert prefixes.always_activities == accepted.always_activities == ("A", "B")


def test_unreachable_acceptance_is_false_only_after_complete_search():
    net = PetriNet(
        (Place("p"), Place("q")),
        (Transition("a", "A"),),
        (Arc("p", "a"), Arc("a", "p")),
        Marking((("p", 1),)),
        Marking((("q", 1),)),
    )
    model = report(net).value
    assert model.accepted_language_exists is False
    assert model.minimum_trace_length is None
    assert model.always_activities is None  # undefined on an empty accepted language
    assert model.self_succession == ("A",)
    accepted = report(net, behavior="accepting").value
    assert accepted.activities == ()


def test_state_limit_retains_positive_witnesses_but_no_negative_relations():
    model = tree("sequence", leaf("A"), leaf("B"), leaf("C"))
    result = report(model, max_states=3)
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.directly_follows == (("A", "B"),)
    assert result.value.sequence is None
    assert result.value.unrelated is None
    assert result.value.inactive_activities is None
    assert result.value.accepted_language_exists is None
    assert result.value.always_activities is None


def test_analysis_limit_is_not_reported_as_a_complete_empty_footprint():
    result = report(tree("sequence", leaf("A"), leaf("B")), max_analysis_steps=1)
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.sequence is None
    assert result.value.always_activities is None
    assert result.value.complete is False
    assert "footprint_analysis_limit" in {i.code for i in result.issues}


def test_over_token_limit_initial_marking_stays_unknown():
    net = PetriNet((Place("p"),), (), (), Marking((("p", 2),)), Marking((("p", 2),)))
    result = report(net, max_tokens=1)
    assert result.status == ComputeStatus.PARTIAL
    assert result.value.accepted_language_exists is None
    assert result.value.accepts_empty_trace is None


def test_model_identity_spec_and_discovery_parent_are_retained():
    log = CaseLog(
        (
            CaseTrace(
                "case",
                tuple(
                    CaseEvent(f"e{i}", (CaseAttribute("concept:name", "string", a),))
                    for i, a in enumerate("AB")
                ),
            ),
        )
    )
    parent = discover_alpha(log)
    result = report(parent)
    assert result.source_digest == parent.source_digest
    assert parent.computation_id in result.parent_computation_ids
    assert result.value.directly_follows == (("A", "B"),)
    assert result.computation_id != report(parent, behavior="accepting").computation_id


def test_failed_discovery_propagates_without_inventing_model():
    parent = discover_alpha(CaseLog())
    result = report(parent)
    assert result.value is None
    assert result.status == parent.status
    assert result.parent_computation_ids == (parent.computation_id,)


@pytest.mark.parametrize("max_states", [2, 100])
def test_model_footprints_complete_and_partial_codec_roundtrip(monkeypatch, max_states):
    from pix import results
    from pix.case_centric.model_discovery import RESULT_SCHEMAS

    original = results._schemas
    monkeypatch.setattr(results, "_schemas", lambda: {**original(), **RESULT_SCHEMAS})
    result = report(tree("parallel", leaf("A"), leaf("B")), max_states=max_states)
    assert results.result_from_json(results.result_json_bytes(result)) == result


def independent_accepting_words(net, max_visible=5):
    """Independent dense-vector Petri semantics, not production firing helpers."""
    places = tuple(p.id for p in net.places)
    index = {p: i for i, p in enumerate(places)}
    initial = tuple(dict(net.initial_marking.tokens).get(p, 0) for p in places)
    final = tuple(dict(net.final_marking.tokens).get(p, 0) for p in places)
    agenda, seen, accepted = deque([(initial, ())]), {(initial, ())}, set()
    while agenda:
        marking, word = agenda.popleft()
        if marking == final:
            accepted.add(word)
        for transition in net.transitions:
            inputs = {
                index[a.source]: a.weight for a in net.arcs if a.target == transition.id
            }
            outputs = {
                index[a.target]: a.weight for a in net.arcs if a.source == transition.id
            }
            if not all(marking[i] >= w for i, w in inputs.items()):
                continue
            extended = word + (
                (transition.activity,) if transition.activity is not None else ()
            )
            if len(extended) > max_visible:
                continue
            after = tuple(
                v - inputs.get(i, 0) + outputs.get(i, 0) for i, v in enumerate(marking)
            )
            if (after, extended) not in seen:
                seen.add((after, extended))
                agenda.append((after, extended))
    return accepted


@pytest.mark.parametrize(
    "value",
    [
        tree("sequence", leaf("A"), leaf("B")),
        tree("xor", leaf("A"), leaf("B")),
        tree("parallel", leaf("A"), leaf("B")),
        tree("loop", leaf("A"), leaf("B")),
        tree("sequence", tree("xor", ProcessTree("tau"), leaf("A")), leaf("B")),
    ],
)
def test_model_relations_and_minimum_match_independent_small_accepted_language(value):
    from pix.compute.discovery import process_tree_to_petri_net

    words = independent_accepting_words(process_tree_to_petri_net(value))
    footprints = report(value, behavior="accepting").value
    assert footprints.directly_follows == tuple(
        sorted({pair for word in words for pair in zip(word, word[1:])})
    )
    assert footprints.minimum_trace_length == min(map(len, words))
    assert footprints.always_activities == tuple(
        sorted(set.intersection(*(set(w) for w in words)))
    )


def test_weighted_arcs_and_silent_cycle_relation_witness_replays():
    net = PetriNet(
        tuple(Place(p) for p in ("p", "q", "r", "s")),
        (
            Transition("a", "A"),
            Transition("tau"),
            Transition("cycle"),
            Transition("b", "B"),
        ),
        (
            Arc("p", "a", 2),
            Arc("a", "q", 3),
            Arc("q", "tau", 3),
            Arc("tau", "r", 2),
            Arc("r", "cycle", 2),
            Arc("cycle", "r", 2),
            Arc("r", "b", 2),
            Arc("b", "s"),
        ),
        Marking((("p", 2),)),
        Marking((("s", 1),)),
    )
    model = report(net).value
    assert model.directly_follows == (("A", "B"),)
    assert model.relation_witnesses[0].silent_transition_ids == ("tau",)
    assert model.minimum_trace_length == 2
    assert independent_accepting_words(net) == {("A", "B")}


@pytest.mark.parametrize(
    "kwargs", [{"behavior": "foo"}, {"max_states": True}, {"max_analysis_steps": 0}]
)
def test_bad_parameters(kwargs):
    with pytest.raises(ValueError):
        ModelFootprintSpec(**kwargs)
